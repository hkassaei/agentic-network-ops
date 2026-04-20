"""
BaselineCollector — captures a pre-fault snapshot of the stack.

No LLM needed — purely deterministic. Calls observation tools to capture
metrics, container statuses, and stack phase. Clears any residual tc rules
from all containers before capturing the baseline to ensure a pristine state.
Writes result to session.state["baseline"].
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import AsyncGenerator

from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.genai import types

from ..tools.network_tools import clear_tc_rules
from ..tools.observation_tools import (
    determine_phase,
    snapshot_container_status,
    snapshot_metrics,
)

log = logging.getLogger("chaos-agent.baseline")

_BASELINE_TIMEOUT = 20  # seconds for entire baseline capture

# Containers that could have residual tc rules from previous runs
_TC_CLEANUP_TARGETS = [
    "upf", "pcscf", "icscf", "scscf", "pyhss", "rtpengine",
    "amf", "smf", "nr_gnb", "dns", "mongo", "mysql",
]


class BaselineCollector(BaseAgent):
    """Captures pre-fault metrics + container status snapshot."""

    name: str = "BaselineCollector"
    description: str = "Captures a baseline snapshot of the stack before fault injection."

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        # Clear residual tc rules from all containers before baseline capture.
        # Previous runs may have left tc netem rules if healing failed or the
        # process was interrupted. A clean baseline requires no tc rules.
        cleaned = 0
        for target in _TC_CLEANUP_TARGETS:
            try:
                await clear_tc_rules(target)
                cleaned += 1
            except Exception:
                pass  # container may not be running
        log.info("Pre-baseline tc cleanup: cleared %d/%d containers",
                 cleaned, len(_TC_CLEANUP_TARGETS))

        log.info("Capturing baseline snapshot...")

        metrics = await snapshot_metrics()
        try:
            statuses = await asyncio.wait_for(
                snapshot_container_status(), timeout=_BASELINE_TIMEOUT
            )
        except asyncio.TimeoutError:
            log.warning("Container status snapshot timed out")
            statuses = {}
        phase = determine_phase(statuses)

        baseline = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "stack_phase": phase,
            "container_status": statuses,
            "metrics": metrics,
        }

        nf_count = len([s for s in statuses.values() if s == "running"])
        metric_count = len(metrics)

        # Build a baseline "snapshot" matching the observation-snapshot format
        # so the trigger evaluator can use it for prior_stable(window=5m) context.
        import time as _time
        baseline_snapshot = dict(metrics)  # shallow copy of metrics per component
        baseline_snapshot["_timestamp"] = _time.time()

        yield Event(
            author=self.name,
            content=types.Content(
                parts=[types.Part(text=(
                    f"Baseline captured: phase={phase}, "
                    f"{nf_count} containers running, "
                    f"{metric_count} NFs with metrics"
                ))],
            ),
            # Store metrics in three shapes:
            #   - baseline: the structured episode-record form
            #   - baseline_metrics: flat form (FaultPropagationVerifier convenience)
            #   - baseline_metrics_snapshot: timestamp-tagged shape for the
            #     v6 trigger evaluator (feeds prior_stable queries)
            actions=EventActions(state_delta={
                "baseline": baseline,
                "baseline_metrics": metrics,
                "baseline_metrics_snapshot": baseline_snapshot,
            }),
        )

    async def _run_live_impl(self, ctx):
        raise NotImplementedError
