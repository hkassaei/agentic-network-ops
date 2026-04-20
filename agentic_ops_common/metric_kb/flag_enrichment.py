"""Enrich anomaly screener flags with KB semantic context.

The anomaly screener detects statistical deviations from a learned healthy
baseline, but its raw output is just (metric_name, current, learned_normal,
severity) — numbers without semantic meaning. This module looks each flag
up in the metric KB and attaches the authored `meaning` / `healthy` text so
the NetworkAnalyst reads semantic observations instead of bare numerics.

Architectural split:
  - Anomaly model = "which numbers are statistically unusual right now?"
  - Metric KB     = "what does a deviation on THIS metric mean?"
  - Events        = "is there a named pattern worth promoting to a hypothesis?"

This module is the bridge between the first two.
"""

from __future__ import annotations

import logging
from typing import Optional

from .feature_mapping import map_preprocessor_key_to_kb
from .models import MetricEntry, MetricsKB

log = logging.getLogger("metric_kb.flag_enrichment")


def enrich_report(report, kb: MetricsKB) -> None:
    """Populate each flag's `kb_context` in-place from the KB.

    Flags that can't be mapped to a KB entry are left as-is — the
    NA prompt falls back to a no-context render for them.

    Args:
        report: `AnomalyReport` whose `flags` will be enriched.
        kb: loaded MetricsKB.
    """
    # Imported lazily to avoid a circular import between the anomaly and
    # metric_kb packages (the KB doesn't depend on anomaly at module load).
    from agentic_ops_common.anomaly.screener import FlagKBContext

    for flag in report.flags:
        # Reconstruct the preprocessor feature key from (component, metric).
        # Screener splits at the first "." so these always roundtrip.
        fkey = f"{flag.component}.{flag.metric}"
        kb_id = map_preprocessor_key_to_kb(fkey)
        if kb_id is None:
            log.debug("No KB mapping for flag key %s", fkey)
            continue
        entry: Optional[MetricEntry] = kb.get_metric(kb_id)
        if entry is None:
            log.debug("KB has no entry for mapped id %s (from %s)", kb_id, fkey)
            continue

        flag.kb_context = FlagKBContext(
            kb_metric_id=kb_id,
            display_name=entry.display_name,
            unit=entry.unit,
            what_it_signals=_get_meaning(entry, "what_it_signals"),
            direction_meaning=_direction_meaning(entry, flag.direction),
            typical_range=(
                tuple(entry.healthy.typical_range)
                if entry.healthy and entry.healthy.typical_range
                else None
            ),
            invariant=entry.healthy.invariant if entry.healthy else None,
            pre_existing_noise=(
                entry.healthy.pre_existing_noise if entry.healthy else None
            ),
        )


def _get_meaning(entry: MetricEntry, field: str) -> Optional[str]:
    if entry.meaning is None:
        return None
    return getattr(entry.meaning, field, None)


def _direction_meaning(entry: MetricEntry, direction: str) -> Optional[str]:
    """Pick the best-fit `meaning.*` field for the observed direction.

    Direction values come from the screener: `spike`, `drop`, `shift`.
    A zero current value is handled by the screener as `drop` — but the
    KB's `meaning.zero` carries a more precise reading (e.g. "counter did
    not advance" vs "deviation below mean"), so we prefer `meaning.zero`
    when the metric went to literally zero.
    """
    if entry.meaning is None:
        return None
    # If we have a `zero` semantic and the flag direction is `drop`, the
    # zero reading is usually the more specific one. The caller (screener)
    # doesn't pass the current value through; we rely on the KB author to
    # write `drop` and `zero` such that either is a valid reading for a
    # drop to near-zero.
    if direction == "spike" and entry.meaning.spike:
        return entry.meaning.spike
    if direction == "drop":
        # Prefer the zero reading when present — drops to zero are the
        # common failure signature (silent counter, stalled pipeline).
        if entry.meaning.zero:
            return entry.meaning.zero
        if entry.meaning.drop:
            return entry.meaning.drop
    if direction == "shift" and entry.meaning.steady_non_zero:
        return entry.meaning.steady_non_zero
    # Fallback: any available meaning field
    return (
        entry.meaning.spike
        or entry.meaning.drop
        or entry.meaning.zero
        or entry.meaning.steady_non_zero
    )
