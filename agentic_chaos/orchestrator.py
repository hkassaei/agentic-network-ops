"""
ChaosDirector — the top-level orchestrator for chaos episodes.

Wires together all Phase agents into a SequentialAgent:
  1. BaselineCollector           → captures pre-fault state
  2. CallSetupAgent              → establishes VoNR call (if scenario needs it)
  3. FaultInjector               → injects faults per scenario
  4. FaultPropagationVerifier    → waits N seconds, verifies fault manifested
  5. ChallengeAgent              → invokes the RCA agent (v1.5/v3/v4/v5)
  6. Healer                      → reverses all faults
  7. CallTeardownAgent           → hangs up the VoNR call
  8. EpisodeRecorder             → writes episode JSON

Usage:
    from agentic_chaos.orchestrator import run_scenario
    from agentic_chaos.models import Scenario, FaultSpec, FaultCategory, BlastRadius

    scenario = Scenario(
        name="P-CSCF Latency",
        description="Inject 500ms latency on P-CSCF",
        category=FaultCategory.NETWORK,
        blast_radius=BlastRadius.SINGLE_NF,
        faults=[FaultSpec(fault_type="network_latency", target="pcscf",
                          params={"delay_ms": 500})],
        expected_symptoms=["SIP REGISTER timeout"],
    )
    episode = await run_scenario(scenario)
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from google.adk.agents import SequentialAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from .agents.baseline import BaselineCollector
from .agents.call_setup import CallSetupAgent, CallTeardownAgent
from .agents.challenger import ChallengeAgent
from .agents.fault_injector import FaultInjector
from .agents.fault_propagation_verifier import create_fault_propagation_verifier
from .agents.healer import Healer
from .fault_registry import FaultRegistry
from .models import Scenario
from .recorder import EpisodeRecorder

log = logging.getLogger("chaos-orchestrator")

# Module-level registry singleton
_registry: FaultRegistry | None = None


def get_registry() -> FaultRegistry:
    """Get or create the module-level FaultRegistry singleton."""
    global _registry
    if _registry is None:
        _registry = FaultRegistry()
    return _registry


def create_chaos_director(
    registry: FaultRegistry | None = None,
) -> SequentialAgent:
    """Factory: create the ChaosDirector SequentialAgent.

    Args:
        registry: FaultRegistry instance. Uses singleton if None.

    Returns:
        A SequentialAgent ready to run a chaos episode.
    """
    reg = registry or get_registry()

    baseline_collector = BaselineCollector()
    call_setup = CallSetupAgent()
    fault_injector = FaultInjector(registry=reg)
    fault_verifier = create_fault_propagation_verifier()
    challenge_agent = ChallengeAgent()
    healer = Healer(registry=reg)
    call_teardown = CallTeardownAgent()
    episode_recorder = EpisodeRecorder()

    # Pipeline: baseline → [call_setup] → inject → verify → [challenge] → heal → [call_teardown] → record
    return SequentialAgent(
        name="ChaosDirector",
        description=(
            "Orchestrates a complete chaos episode: "
            "baseline → [call_setup] → inject → verify → [challenge] → heal → [call_teardown] → record."
        ),
        sub_agents=[
            baseline_collector,
            call_setup,
            fault_injector,
            fault_verifier,
            challenge_agent,
            healer,
            call_teardown,
            episode_recorder,
        ],
    )


# -------------------------------------------------------------------------
# Pre-check: verify stack health before starting a scenario
# -------------------------------------------------------------------------

# Critical metrics that must be at expected values for a healthy stack.
# Covers 5G attachment AND IMS registration — both must be healthy.
_HEALTH_CHECKS = {
    "ran_ue": {"expected": 2.0, "source": "amf", "description": "Connected UEs at AMF"},
    "gnb": {"expected": 1.0, "source": "amf", "description": "Connected gNBs at AMF"},
    "amf_session": {"expected": 4.0, "source": "amf", "description": "AMF sessions (2 UEs x 2 PDU)"},
    "fivegs_smffunction_sm_sessionnbr": {"expected": 4.0, "source": "smf", "description": "SMF PDU sessions"},
    "ims_usrloc_pcscf:registered_contacts": {"expected": 2.0, "source": "pcscf", "description": "UEs registered at P-CSCF"},
    "ims_usrloc_scscf:active_contacts": {"expected": 2.0, "source": "scscf", "description": "Active contacts at S-CSCF"},
}


async def _collect_health_metrics() -> dict[str, float]:
    """Collect key health metrics from the live network."""
    from .tools.observation_tools import snapshot_metrics
    all_metrics = await snapshot_metrics()

    # Extract the specific metrics we care about, from the right source
    health: dict[str, float] = {}
    for key, check in _HEALTH_CHECKS.items():
        source = check["source"]
        source_metrics = all_metrics.get(source, {}).get("metrics", {})
        if key in source_metrics:
            health[key] = source_metrics[key]
    return health


async def _auto_heal_stack() -> bool:
    """Attempt to auto-heal the stack by redeploying UEs."""
    import asyncio
    import subprocess

    log.info("Auto-heal: redeploying UEs...")
    try:
        proc = await asyncio.create_subprocess_exec(
            "bash", "scripts/deploy-ues.sh",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(_get_repo_root()),
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=180)

        if proc.returncode == 0:
            log.info("Auto-heal: UEs redeployed successfully")
            # Wait for UEs to attach to 5G and register with IMS
            # IMS registration can take up to 60s (Kamailio timers + Diameter auth)
            log.info("Auto-heal: waiting 60s for 5G attachment + IMS registration...")
            await asyncio.sleep(60)
            return True
        else:
            log.error("Auto-heal: deploy-ues.sh failed (exit %d): %s",
                      proc.returncode, stderr.decode(errors="replace")[-200:])
            return False
    except asyncio.TimeoutError:
        log.error("Auto-heal: deploy-ues.sh timed out after 180s")
        return False
    except Exception as e:
        log.error("Auto-heal failed: %s", e)
        return False


def _get_repo_root():
    """Get the repo root path."""
    from pathlib import Path
    return Path(__file__).resolve().parents[1]


async def _pre_check_stack_health() -> bool:
    """Verify the stack is healthy before starting a chaos scenario.

    Compares live metrics against expected baselines. If unhealthy,
    prompts the user for auto-heal or manual cleanup.
    """
    log.info("Pre-check: verifying stack health...")

    health = await _collect_health_metrics()
    if not health:
        log.warning("Pre-check: could not collect health metrics — proceeding anyway")
        return True

    # Check each metric against expected
    failures: list[str] = []
    for metric, check in _HEALTH_CHECKS.items():
        actual = health.get(metric)
        expected = check["expected"]
        if actual is None:
            failures.append(f"  {metric}: MISSING (expected {expected}) — {check['description']}")
        elif actual != expected:
            failures.append(f"  {metric}: {actual} (expected {expected}) — {check['description']}")

    if not failures:
        log.info("Pre-check: stack is healthy ✓")
        return True

    # Stack is unhealthy — report and prompt
    print()
    print("=" * 60)
    print("  STACK HEALTH CHECK FAILED")
    print("=" * 60)
    print()
    print("The following metrics are not at expected values:")
    for f in failures:
        print(f)
    print()
    print("This means the stack has residual issues from a previous test.")
    print("Running a scenario on an unhealthy stack will produce unreliable results.")
    print()
    print("Options:")
    print("  [a] Auto-heal: redeploy UEs and wait for registration")
    print("  [s] Skip: proceed anyway (results may be unreliable)")
    print("  [q] Quit: abort the scenario")
    print()

    while True:
        try:
            choice = input("Choose [a/s/q]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return False

        if choice == "a":
            healed = await _auto_heal_stack()
            if healed:
                # Re-check after healing
                health2 = await _collect_health_metrics()
                still_bad = []
                for metric, check in _HEALTH_CHECKS.items():
                    actual = health2.get(metric)
                    if actual != check["expected"]:
                        still_bad.append(f"  {metric}: {actual} (expected {check['expected']})")
                if still_bad:
                    print()
                    print("Auto-heal completed but some metrics are still unhealthy:")
                    for f in still_bad:
                        print(f)
                    print()
                    continue  # Ask again
                else:
                    log.info("Pre-check: stack is healthy after auto-heal ✓")
                    return True
            else:
                print("Auto-heal failed. Choose another option.")
                continue

        elif choice == "s":
            log.warning("Pre-check: proceeding with unhealthy stack (user chose skip)")
            return True

        elif choice == "q":
            log.info("Pre-check: scenario aborted by user")
            return False


async def run_scenario(
    scenario: Scenario,
    registry: FaultRegistry | None = None,
    agent_version: str = "v1.5",
    abort_on_unpropagated: bool = False,
) -> dict:
    """Run a complete chaos episode for the given scenario.

    This is the primary entry point for the chaos platform.

    Args:
        scenario: The Scenario to execute.
        registry: Optional FaultRegistry. Uses singleton if None.
        agent_version: Which troubleshooting agent to evaluate ("v1.5" or "v3").
        abort_on_unpropagated: If True, skip the RCA agent invocation when
            the FaultPropagationVerifier reports verdict='not_observed'.

    Returns:
        The complete episode dict.
    """
    reg = registry or get_registry()

    # Initialize registry if needed
    if not reg.is_initialized:
        await reg.initialize()
    reg.start_reaper()

    # Clean slate: heal any leftover faults from a previous run
    active = await reg.get_active_faults()
    if active:
        log.warning("Found %d active faults from a previous run — healing before starting", len(active))
        healed = await reg.heal_all(method="pre_run_cleanup")
        log.info("Pre-run cleanup: healed %d faults", healed)

    # Pre-check: verify the stack is healthy before starting
    health_ok = await _pre_check_stack_health()
    if not health_ok:
        return {"error": "Stack health check failed — episode aborted"}

    # Generate episode ID
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    slug = scenario.name.lower().replace(" ", "_").replace("-", "_")[:30]
    episode_id = f"ep_{ts}_{slug}"

    # Force challenge mode on — the whole point is agent evaluation
    scenario = scenario.model_copy(update={"challenge_mode": True})

    from .agents.fault_propagation_verifier import FAULT_PROPAGATION_TIME_SECONDS
    log.info(
        "Starting chaos episode: %s — %s (agent=%s, fault_propagation=%ds)",
        episode_id, scenario.name, agent_version,
        FAULT_PROPAGATION_TIME_SECONDS,
    )

    # Create the orchestrator
    director = create_chaos_director(registry=reg)

    # Set up ADK session with initial state
    session_service = InMemorySessionService()
    runner = Runner(
        agent=director,
        app_name="chaos_monkey",
        session_service=session_service,
    )

    session = await session_service.create_session(
        app_name="chaos_monkey",
        user_id="chaos_operator",
        state={
            "episode_id": episode_id,
            "scenario": scenario.model_dump(mode="json"),
            "agent_version": agent_version,
            "observations": [],
            "escalation_level": 0,
            "symptoms_detected": False,
            "abort_on_unpropagated": abort_on_unpropagated,
            # Temporal reasoning bootstrap: deliberately imprecise hint to
            # the RCA agent about how far back to look. Fixed at 300s
            # regardless of when the fault was injected — we do NOT leak
            # the real inject time to keep the agent's reasoning
            # production-portable. See docs/ADR/dealing_with_temporality_2.md.
            "anomaly_window_hint_seconds": 300,
        },
    )

    # Run the orchestrator
    events: list[str] = []
    async for event in runner.run_async(
        user_id="chaos_operator",
        session_id=session.id,
        new_message=types.Content(
            role="user",
            parts=[types.Part(text=f"Execute chaos scenario: {scenario.name}")],
        ),
    ):
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    log.info("[%s] %s", event.author, part.text)
                    events.append(f"[{event.author}] {part.text}")

    # Retrieve the final state
    final_session = await session_service.get_session(
        app_name="chaos_monkey",
        user_id="chaos_operator",
        session_id=session.id,
    )

    episode = final_session.state.get("episode", {})
    episode_path = final_session.state.get("episode_path", "")

    log.info("Episode complete: %s → %s", episode_id, episode_path)
    return episode
