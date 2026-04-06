"""
ChaosDirector — the top-level orchestrator for chaos episodes.

Wires together all Phase agents into a SequentialAgent:
  1. BaselineCollector           → captures pre-fault state
  2. CallSetupAgent              → establishes VoNR call (if user_plane scenario)
  3. FaultInjector               → injects faults per scenario
  4. ControlPlaneTrafficAgent    → forces SIP re-register (if control_plane scenario)
  5. FaultPropagationVerifier    → waits N seconds, verifies fault manifested
  6. ChallengeAgent              → invokes the RCA agent (v1.5/v3/v4/v5)
  7. Healer                      → reverses all faults
  8. CallTeardownAgent           → hangs up the VoNR call
  9. EpisodeRecorder             → writes episode JSON

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
from .agents.control_plane_traffic import ControlPlaneTrafficAgent
from .agents.fault_injector import FaultInjector
from .agents.observation_traffic import ObservationTrafficAgent
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
    control_plane_traffic = ControlPlaneTrafficAgent()
    fault_verifier = create_fault_propagation_verifier()
    observation_traffic = ObservationTrafficAgent()
    challenge_agent = ChallengeAgent()
    healer = Healer(registry=reg)
    call_teardown = CallTeardownAgent()
    episode_recorder = EpisodeRecorder()

    # Pipeline: baseline → [call_setup] → inject → [cp_traffic] → verify →
    #           [observation_traffic] → [challenge] → heal → [call_teardown] → record
    return SequentialAgent(
        name="ChaosDirector",
        description=(
            "Orchestrates a complete chaos episode: "
            "baseline → [call_setup] → inject → [cp_traffic] → verify → "
            "[observation_traffic] → [challenge] → heal → [call_teardown] → record."
        ),
        sub_agents=[
            baseline_collector,
            call_setup,
            fault_injector,
            control_plane_traffic,
            fault_verifier,
            observation_traffic,
            challenge_agent,
            healer,
            call_teardown,
            episode_recorder,
        ],
    )


# -------------------------------------------------------------------------
# Pre-check: verify stack health before starting a scenario
# Delegates to the shared stack_health module.
# -------------------------------------------------------------------------

async def _pre_check_stack_health() -> bool:
    """Verify the stack is healthy before starting a chaos scenario."""
    import sys
    from pathlib import Path
    repo_root = str(Path(__file__).resolve().parents[1])
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    from common.stack_health import check_stack_health
    return await check_stack_health(purpose="running chaos scenario")


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
