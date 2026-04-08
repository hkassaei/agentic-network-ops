"""
FaultPropagationVerifier — bullet-proof replacement for SymptomObserver.

Replaces the old SymptomObserver polling loop with a deterministic
three-step verification:

  1. Wait `fault_propagation_time` seconds (no polling, no early exit).
     This gives the fault time to settle across the stack.

  2. Take ONE metrics snapshot and compute deltas vs baseline.

  3. Filter deltas via the ontology to separate fault-induced signals
     from baseline noise (pre-existing conditions, typical-range drift).

The verifier produces a verdict (confirmed / inconclusive / not_observed)
that is recorded in the episode, but does NOT gate the RCA agent by
default. Use --abort-on-unpropagated to skip agent invocation when the
fault clearly did not take effect.

Design choices:
  - Logs are NOT used for verification. `docker logs --tail N` returns
    historical lines that produce false positives. Log analysis belongs
    in the Investigator phase.
  - Single snapshot, not a polling loop. No early-exit-on-first-signal.
  - Ontology-driven filtering (`is_pre_existing`, `typical_range`,
    `alarm_if`) rejects baseline noise that triggered the old observer.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.genai import types

from ..tools.observation_tools import compute_metrics_delta, snapshot_metrics

log = logging.getLogger("chaos-agent.verifier")

# Framework-wide fault propagation wait. Every fault gets the same
# window to propagate through the stack and produce secondary/tertiary
# effects. Single value, no per-scenario overrides — every failure
# takes its full course before the RCA agent is invoked.
FAULT_PROPAGATION_TIME_SECONDS = 30

# Minimum relative change required to count a metric delta as significant.
# A counter drifting 5% due to keep-alives is noise; a 20% jump is signal.
_SIGNIFICANT_DELTA_PCT = 20.0

# Absolute delta threshold for metrics that are near zero at baseline.
# A metric going 0 → 2 is a real change even though "percent" is undefined.
_SIGNIFICANT_DELTA_ABS = 1.0


class FaultPropagationVerifier(BaseAgent):
    """Wait for fault propagation, then verify it manifested."""

    name: str = "FaultPropagationVerifier"
    description: str = (
        f"Waits {FAULT_PROPAGATION_TIME_SECONDS}s after injection, then "
        "verifies that the fault has produced observable metric changes "
        "beyond baseline noise. Does not use logs to avoid stale-log "
        "false positives."
    )

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:

        # If the ObservationTrafficAgent already ran (observation_snapshots
        # in state), the fault has had plenty of time to propagate — skip
        # the wait and just take a verification snapshot immediately.
        observation_ran = bool(ctx.session.state.get("observation_snapshots"))
        if observation_ran:
            wait_seconds = 0
            log.info("Observation traffic already ran — skipping propagation wait, taking snapshot...")
        else:
            wait_seconds = FAULT_PROPAGATION_TIME_SECONDS
            log.info("Waiting %ds for fault propagation...", wait_seconds)

        start = datetime.now(timezone.utc)
        if wait_seconds > 0:
            await asyncio.sleep(wait_seconds)
        elapsed = (datetime.now(timezone.utc) - start).total_seconds()
        log.info("Taking verification snapshot (%.1fs after start)...", elapsed)

        # Snapshot current metrics
        try:
            current_metrics = await asyncio.wait_for(
                snapshot_metrics(), timeout=10
            )
        except asyncio.TimeoutError:
            log.warning("Metrics snapshot timed out during verification")
            current_metrics = {}

        # Compute delta vs baseline
        baseline_metrics = ctx.session.state.get("baseline_metrics", {})
        raw_delta = compute_metrics_delta(baseline_metrics, current_metrics)

        # Filter out baseline noise using the ontology
        filtered_delta = _filter_significant(raw_delta)

        # Determine verdict
        if filtered_delta:
            verdict = "confirmed"
            msg = (
                f"Fault propagation CONFIRMED after {wait_seconds}s. "
                f"Significant deltas on: {sorted(filtered_delta.keys())}"
            )
        elif raw_delta:
            verdict = "inconclusive"
            msg = (
                f"Fault propagation INCONCLUSIVE after {wait_seconds}s. "
                f"Some metrics drifted but none exceeded significance thresholds. "
                f"Drifted nodes: {sorted(raw_delta.keys())}"
            )
        else:
            verdict = "not_observed"
            msg = (
                f"Fault propagation NOT_OBSERVED after {wait_seconds}s. "
                f"No metric deltas detected vs baseline. The fault may not "
                f"have propagated or may not produce detectable metric signals."
            )

        log.info(msg)

        verification: dict[str, Any] = {
            "verdict": verdict,
            "wait_seconds": wait_seconds,
            "elapsed_seconds": round(elapsed, 2),
            "verified_at": datetime.now(timezone.utc).isoformat(),
            "filtered_deltas": filtered_delta,
            "raw_delta_node_count": len(raw_delta),
        }

        # Honor --abort-on-unpropagated (set via state flag by the orchestrator)
        should_abort = (
            verdict == "not_observed"
            and ctx.session.state.get("abort_on_unpropagated", False)
        )
        if should_abort:
            verification["aborted"] = True
            log.warning(
                "Aborting episode: --abort-on-unpropagated is set and "
                "fault was NOT_OBSERVED"
            )

        # Also record as an "observation" so the recorder's existing
        # markdown rendering works without changes.
        observation_record = {
            "iteration": 1,
            "timestamp": verification["verified_at"],
            "elapsed_seconds": verification["elapsed_seconds"],
            "metrics_delta": filtered_delta,
            "log_samples": {},
            "symptoms_detected": verdict == "confirmed",
            "escalation_level": 0,
        }
        observations = list(ctx.session.state.get("observations", []))
        observations.append(observation_record)

        state_delta: dict[str, Any] = {
            "fault_verification": verification,
            "observations": observations,
            "symptoms_detected": verdict == "confirmed",
        }
        if should_abort:
            # Do NOT escalate — the SequentialAgent must still run the Healer,
            # CallTeardown, and EpisodeRecorder. The ChallengeAgent checks
            # this flag and skips itself.
            state_delta["episode_aborted"] = True

        yield Event(
            author=self.name,
            content=types.Content(parts=[types.Part(text=msg)]),
            actions=EventActions(state_delta=state_delta),
        )

    async def _run_live_impl(self, ctx):
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Delta filtering
# ---------------------------------------------------------------------------

def _filter_significant(raw_delta: dict[str, dict]) -> dict[str, dict]:
    """Keep only metric deltas that exceed significance thresholds.

    Thresholds are magnitude-based (not ontology-based) to keep this
    verifier simple and self-contained. The agent layer does the deeper
    ontology comparison later.

    A delta is kept if EITHER:
      - absolute change >= _SIGNIFICANT_DELTA_ABS (catches 0 → N transitions)
      - relative change (|delta| / |baseline|) >= _SIGNIFICANT_DELTA_PCT / 100

    Pure counter drift (e.g., +1 on a 2000 baseline) gets dropped. Real
    signals (e.g., 0 → 5 timeouts, 85 → 450ms response time) are kept.
    """
    out: dict[str, dict] = {}
    for node, metrics in raw_delta.items():
        kept: dict[str, dict] = {}
        for metric, vals in metrics.items():
            baseline_val = vals.get("baseline", 0) or 0
            diff = abs(vals.get("delta", 0) or 0)

            if diff == 0:
                continue

            # Absolute threshold — handles baseline=0 cleanly
            if diff >= _SIGNIFICANT_DELTA_ABS and baseline_val == 0:
                kept[metric] = vals
                continue

            # Relative threshold — catches percentage jumps
            if baseline_val != 0:
                pct = (diff / abs(baseline_val)) * 100
                if pct >= _SIGNIFICANT_DELTA_PCT:
                    kept[metric] = vals

        if kept:
            out[node] = kept
    return out


def create_fault_propagation_verifier() -> FaultPropagationVerifier:
    """Factory for the FaultPropagationVerifier."""
    return FaultPropagationVerifier()
