"""Shared stack health check utility.

Verifies the 5G SA + IMS stack is healthy by comparing live metrics against
expected baselines. Used by:
  - agentic_chaos/orchestrator.py (before running chaos scenarios)
  - anomaly_trainer/__main__.py (before training the anomaly model)

Provides auto-heal (redeploy UEs) and interactive prompting when the
stack is unhealthy.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

log = logging.getLogger("stack_health")

_REPO_ROOT = Path(__file__).resolve().parents[1]

# Critical metrics that must be at expected values for a healthy stack.
# Covers 5G attachment AND IMS registration — both must be healthy.
HEALTH_CHECKS = {
    "ran_ue": {"expected": 2.0, "source": "amf", "description": "Connected UEs at AMF"},
    "gnb": {"expected": 1.0, "source": "amf", "description": "Connected gNBs at AMF"},
    "amf_session": {"expected": 4.0, "source": "amf", "description": "AMF sessions (2 UEs x 2 PDU)"},
    "fivegs_smffunction_sm_sessionnbr": {"expected": 4.0, "source": "smf", "description": "SMF PDU sessions"},
    "ims_usrloc_pcscf:registered_contacts": {"expected": 2.0, "source": "pcscf", "description": "UEs registered at P-CSCF"},
    "ims_usrloc_scscf:active_contacts": {"expected": 2.0, "source": "scscf", "description": "Active contacts at S-CSCF"},
}


async def collect_health_metrics() -> dict[str, float]:
    """Collect key health metrics from the live network.

    Uses the chaos framework's observation_tools.snapshot_metrics() if
    available, otherwise falls back to v5 tools.
    """
    try:
        from agentic_chaos.tools.observation_tools import snapshot_metrics
        all_metrics = await snapshot_metrics()
    except ImportError:
        # Fallback: use v5 tools directly
        from agentic_ops_v5 import tools as v5_tools
        from agentic_ops_v5.anomaly.preprocessor import parse_nf_metrics_text
        text = await v5_tools.get_nf_metrics()
        raw = parse_nf_metrics_text(text)
        # Reshape to match snapshot_metrics format
        all_metrics = {comp: {"metrics": metrics} for comp, metrics in raw.items()}

    health: dict[str, float] = {}
    for key, check in HEALTH_CHECKS.items():
        source = check["source"]
        source_metrics = all_metrics.get(source, {}).get("metrics", {})
        if key in source_metrics:
            health[key] = source_metrics[key]
    return health


async def auto_heal_stack() -> bool:
    """Attempt to auto-heal the stack by redeploying UEs."""
    log.info("Auto-heal: redeploying UEs...")
    try:
        proc = await asyncio.create_subprocess_exec(
            "bash", "scripts/deploy-ues.sh",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(_REPO_ROOT),
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=180)

        if proc.returncode == 0:
            log.info("Auto-heal: UEs redeployed successfully")
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


async def check_stack_health(purpose: str = "operation") -> bool:
    """Verify the stack is healthy. Prompts user if unhealthy.

    Args:
        purpose: Description of what we're about to do (for log messages).
                 E.g., "chaos scenario", "anomaly model training".

    Returns:
        True if healthy (or user chose to proceed), False if user aborted.
    """
    log.info("Pre-check: verifying stack health...")

    health = await collect_health_metrics()
    if not health:
        log.warning("Pre-check: could not collect health metrics — proceeding anyway")
        return True

    failures: list[str] = []
    for metric, check in HEALTH_CHECKS.items():
        actual = health.get(metric)
        expected = check["expected"]
        if actual is None:
            failures.append(f"  {metric}: MISSING (expected {expected}) — {check['description']}")
        elif actual != expected:
            failures.append(f"  {metric}: {actual} (expected {expected}) — {check['description']}")

    if not failures:
        log.info("Pre-check: stack is healthy ✓")
        return True

    print()
    print("=" * 60)
    print("  STACK HEALTH CHECK FAILED")
    print("=" * 60)
    print()
    print("The following metrics are not at expected values:")
    for f in failures:
        print(f)
    print()
    print(f"The stack must be healthy before {purpose}.")
    print()
    print("Options:")
    print("  [a] Auto-heal: redeploy UEs and wait for registration")
    print("  [s] Skip: proceed anyway (results may be unreliable)")
    print("  [q] Quit: abort")
    print()

    while True:
        try:
            choice = input("Choose [a/s/q]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return False

        if choice == "a":
            healed = await auto_heal_stack()
            if healed:
                health2 = await collect_health_metrics()
                still_bad = []
                for metric, check in HEALTH_CHECKS.items():
                    actual = health2.get(metric)
                    if actual != check["expected"]:
                        still_bad.append(f"  {metric}: {actual} (expected {check['expected']})")
                if still_bad:
                    print()
                    print("Auto-heal completed but some metrics are still unhealthy:")
                    for f in still_bad:
                        print(f)
                    print()
                    continue
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
            log.info("Pre-check: aborted by user")
            return False
