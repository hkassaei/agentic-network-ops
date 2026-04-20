"""Trigger evaluator — the orchestrator that ties everything together.

Given a loaded KB, a snapshot of recent metric history, and a target episode,
evaluates each metric's event_triggers and writes fired events to the store.

Entrypoint: `evaluate(...)` — called by the chaos framework at baseline,
fault injection, observation ticks, and end-of-observation per the v6 plan.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from .event_dsl import DSLEvaluationError, eval_trigger
from .event_store import EventStore, FiredEvent
from .loader import load_kb
from .metric_context import InMemoryMetricContext, MetricContext
from .models import EventTrigger, MetricEntry, MetricsKB

log = logging.getLogger("metric_kb.evaluator")


# ----------------------------------------------------------------------------
# Inputs
# ----------------------------------------------------------------------------

@dataclass
class MetricSnapshot:
    """A single-point metric sample in time."""
    metric_id: str           # fully qualified <layer>.<nf>.<metric>
    value: float
    timestamp: float


@dataclass
class EvaluationContext:
    """Bundle of state passed to evaluate().

    `history` is keyed by metric_id -> list[(t, v)] oldest-first.
    `current_values` is the latest value per metric_id.
    `baselines` is the trained baseline mean per metric_id (optional).
    """
    episode_id: str
    eval_time: float
    phase: str = "steady_state"
    history: dict[str, list[tuple[float, float]]] = field(default_factory=dict)
    current_values: dict[str, float] = field(default_factory=dict)
    baselines: dict[str, float] = field(default_factory=dict)


# ----------------------------------------------------------------------------
# Evaluator
# ----------------------------------------------------------------------------

def evaluate(
    kb: MetricsKB,
    eval_ctx: EvaluationContext,
    store: EventStore,
    *,
    metric_ids: Optional[list[str]] = None,
    dry_run: bool = False,
) -> list[FiredEvent]:
    """Evaluate event triggers across the KB and persist fired events.

    Args:
        kb: Loaded metric knowledge base.
        eval_ctx: The evaluation input bundle (episode, time, history, values).
        store: Event store to write fired events to.
        metric_ids: If provided, only evaluate triggers for these metrics.
                    Otherwise evaluate all.
        dry_run: If True, don't write to the store. Returns the events that
                 WOULD have fired.

    Returns:
        List of fired events (in the order they were fired).
    """
    fired: list[FiredEvent] = []

    for nf_name, nf_block in kb.metrics.items():
        for metric_name, entry in nf_block.metrics.items():
            full_id = f"{nf_block.layer.value}.{nf_name}.{metric_name}"

            if metric_ids and full_id not in metric_ids:
                continue

            if full_id not in eval_ctx.current_values:
                # No current value available — skip; can't evaluate triggers
                # that reference `current`.
                continue

            ctx = InMemoryMetricContext(
                metric_id_=full_id,
                history=eval_ctx.history,
                current_values=eval_ctx.current_values,
                eval_time_=eval_ctx.eval_time,
                phase_=eval_ctx.phase,
                baselines=eval_ctx.baselines,
            )

            for trigger in entry.event_triggers:
                if _already_active(store, trigger.id, eval_ctx.episode_id):
                    # Trigger already fired and not cleared — check whether
                    # the clear_condition has been met.
                    if trigger.clear_condition:
                        try:
                            cleared = eval_trigger(trigger.clear_condition, ctx)
                        except DSLEvaluationError as e:
                            log.warning(
                                "Clear condition error for %s: %s", trigger.id, e,
                            )
                            cleared = False
                        if cleared:
                            _mark_trigger_cleared(store, trigger.id,
                                                  eval_ctx.episode_id,
                                                  eval_ctx.eval_time)
                    continue

                # Trigger is not active — evaluate trigger expression
                try:
                    should_fire = eval_trigger(trigger.trigger, ctx)
                except DSLEvaluationError as e:
                    log.warning(
                        "Trigger DSL error for %s on %s: %s — skipping",
                        trigger.id, full_id, e,
                    )
                    continue

                if should_fire:
                    event = _build_event(
                        trigger, entry, nf_name, full_id, eval_ctx, ctx,
                    )
                    if not dry_run:
                        store.insert(event)
                    fired.append(event)
                    log.info(
                        "Event fired: %s (episode=%s, t=%.1f)",
                        trigger.id, eval_ctx.episode_id, eval_ctx.eval_time,
                    )

    return fired


def _already_active(
    store: EventStore, event_type: str, episode_id: str,
) -> bool:
    """Has this event type already fired in this episode and not yet cleared?"""
    latest = store.latest_event_of_type(event_type, episode_id=episode_id)
    return latest is not None and latest.cleared_at is None


def _mark_trigger_cleared(
    store: EventStore, event_type: str, episode_id: str, cleared_at: float,
) -> None:
    latest = store.latest_event_of_type(event_type, episode_id=episode_id)
    if latest and latest.id is not None and latest.cleared_at is None:
        store.mark_cleared(latest.id, cleared_at)
        log.info("Event cleared: %s (episode=%s)", event_type, episode_id)


def _build_event(
    trigger: EventTrigger,
    entry: MetricEntry,
    nf_name: str,
    metric_id: str,
    eval_ctx: EvaluationContext,
    ctx: MetricContext,
) -> FiredEvent:
    """Build the FiredEvent payload.

    The `magnitude_captured` list names what fields the event should carry.
    Supported payload keys:
        current_value        — ctx.current
        prior_stable_value   — prior_stable over 5m window
        delta_absolute       — current - prior_stable
        delta_percent        — (current - prior_stable) / prior_stable * 100
        first_observed_at    — eval_ctx.eval_time
        baseline_mean        — trained baseline if available
        active_sessions_at_event — rtpengine.active_sessions if present
    Any other key in the list is captured as-is from current_values if available.
    """
    from .event_dsl import prior_stable
    payload: dict[str, Any] = {}
    current = ctx.current

    prior = None
    for key in trigger.magnitude_captured:
        if key == "current_value":
            payload["current_value"] = current
        elif key == "prior_stable_value":
            if prior is None:
                prior = prior_stable(ctx, window="5m")
            payload["prior_stable_value"] = prior
        elif key == "delta_absolute":
            if prior is None:
                prior = prior_stable(ctx, window="5m")
            payload["delta_absolute"] = current - prior
        elif key == "delta_percent":
            if prior is None:
                prior = prior_stable(ctx, window="5m")
            payload["delta_percent"] = (
                (current - prior) / prior * 100.0 if prior else None
            )
        elif key == "first_observed_at":
            payload["first_observed_at"] = eval_ctx.eval_time
        elif key == "baseline_mean":
            payload["baseline_mean"] = ctx.baseline_mean()
        elif key == "active_sessions_at_event":
            payload["active_sessions_at_event"] = eval_ctx.current_values.get(
                "ims.rtpengine.active_sessions"
            )
        else:
            # Try to fetch as a named metric
            if key in eval_ctx.current_values:
                payload[key] = eval_ctx.current_values[key]
            else:
                payload[key] = None

    return FiredEvent(
        event_type=trigger.id,
        source_metric=metric_id,
        source_nf=nf_name,
        timestamp=eval_ctx.eval_time,
        magnitude_payload=payload,
        episode_id=eval_ctx.episode_id,
    )
