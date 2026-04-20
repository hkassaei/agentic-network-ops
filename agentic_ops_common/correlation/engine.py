"""Correlation engine — MVP.

Consumes:
  - fired events from the SQLite event store (scoped by episode_id)
  - the metric KB (for correlates_with hints + disambiguators)

Produces:
  - ranked CorrelationHypothesis list with supporting events + discriminating
    probes for the Investigator

Algorithm (MVP, Phase 2):
  1. Build an index from the KB: for every fired event_id, which composite
     interpretations does it participate in, paired with which peer event_id?
  2. For each composite_interpretation, count how many of its constituent
     event_ids actually fired. If at least 2 of the constituents fired, OR
     a single constituent is the "sole possible explanation" for an event
     (i.e., that event has only one correlates_with entry), create a
     CorrelationHypothesis.
  3. Collect disambiguators from each supporting event's metric for
     testability scoring.
  4. Rank by (explanatory_fit DESC, testability DESC, event_count DESC).

Not in this MVP (deferred to later phases):
  - Operational-context suppression (Phase 5)
  - Blast radius projection (Phase 5)
  - Causal-chain reasoning from causal_chains.yaml (future enhancement)
  - Historical episode retrieval (Phase 6, Track 2 RAG)
"""

from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import Path
from typing import Optional

from ..metric_kb import EventStore, FiredEvent, KBLoadError, MetricsKB, load_kb

from .models import CorrelationHypothesis, CorrelationResult

log = logging.getLogger("correlation.engine")


# ----------------------------------------------------------------------------
# Main entrypoint
# ----------------------------------------------------------------------------

def correlate(
    kb: MetricsKB,
    events: list[FiredEvent],
    episode_id: str = "unknown",
) -> CorrelationResult:
    """Run the correlation engine over an event set.

    Args:
        kb: Loaded metric knowledge base.
        events: Fired events to correlate (typically all events for one
                episode). Event order does not matter — correlation is
                by event_id.
        episode_id: For reporting.

    Returns:
        A CorrelationResult with ranked hypotheses and unmatched events.
    """
    if not events:
        return CorrelationResult(episode_id=episode_id, events_considered=0)

    fired_event_ids = {e.event_type for e in events}
    events_by_id: dict[str, list[FiredEvent]] = defaultdict(list)
    for e in events:
        events_by_id[e.event_type].append(e)

    # Index KB: for each event_id → {composite_interpretation: [peer_event_ids]}
    # Constructed by scanning every event_trigger in the KB.
    participation: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for nf_block in kb.metrics.values():
        for metric in nf_block.metrics.values():
            for trigger in metric.event_triggers:
                for hint in trigger.correlates_with:
                    # The trigger's own event participates in the composite
                    # with the peer event named in the hint.
                    ci = hint.composite_interpretation
                    participation[trigger.id][ci].add(hint.event_id)
                    # Reverse direction so either end firing detects the hint.
                    participation[hint.event_id][ci].add(trigger.id)

    # Group fired events by the composite_interpretation they support.
    by_composite: dict[str, set[str]] = defaultdict(set)
    matched_event_ids: set[str] = set()

    for fired_id in fired_event_ids:
        # composite_interpretations this event participates in
        for ci, peer_ids in participation.get(fired_id, {}).items():
            # At least one peer must also have fired (pair-wise minimum)
            if any(peer in fired_event_ids for peer in peer_ids):
                by_composite[ci].add(fired_id)
                # Also include the peer that fired
                for peer in peer_ids:
                    if peer in fired_event_ids:
                        by_composite[ci].add(peer)
                matched_event_ids.add(fired_id)

    # Build hypotheses from composite groups
    hypotheses: list[CorrelationHypothesis] = []
    total_events = len(events)

    for ci, participating_ids in by_composite.items():
        supporting_events = [
            fe for eid in participating_ids
            for fe in events_by_id.get(eid, [])
        ]
        implicated_nfs = sorted({fe.source_nf for fe in supporting_events})
        # Pick primary NF = NF contributing most events to this hypothesis
        nf_counts: dict[str, int] = defaultdict(int)
        for fe in supporting_events:
            nf_counts[fe.source_nf] += 1
        primary_nf = max(nf_counts.items(), key=lambda kv: kv[1])[0] if nf_counts else None

        # Collect disambiguators from each supporting event's source metric
        discriminators: list[str] = []
        for fe in supporting_events:
            metric_entry = kb.get_metric(fe.source_metric)
            if metric_entry is None:
                continue
            for dis in metric_entry.disambiguators:
                if dis.metric not in discriminators:
                    discriminators.append(dis.metric)

        # Build falsification probe statements
        falsification_probes = _build_falsification_probes(
            supporting_events, kb,
        )

        h = CorrelationHypothesis(
            statement=ci,
            supporting_event_ids=sorted(participating_ids),
            supporting_event_objects=supporting_events,
            implicated_nfs=implicated_nfs,
            primary_nf=primary_nf,
            explanatory_fit=min(1.0, len(participating_ids) / max(1, total_events)),
            testability=len(discriminators),
            discriminating_metrics=discriminators,
            falsification_probes=falsification_probes,
        )
        hypotheses.append(h)

    # Rank: explanatory_fit DESC, testability DESC, event_count DESC
    hypotheses.sort(
        key=lambda h: (
            -h.explanatory_fit,
            -h.testability,
            -len(h.supporting_event_ids),
        )
    )

    unmatched = [e for e in events if e.event_type not in matched_event_ids]
    result = CorrelationResult(
        episode_id=episode_id,
        hypotheses=hypotheses,
        unmatched_events=unmatched,
        events_considered=total_events,
    )
    log.info(result.summary_line())
    return result


# ----------------------------------------------------------------------------
# Probe construction
# ----------------------------------------------------------------------------

def _build_falsification_probes(
    supporting_events: list[FiredEvent],
    kb: MetricsKB,
) -> list[str]:
    """Build human-readable falsification probes from supporting events.

    For each supporting event, fetch the `disambiguators` entries on the
    source metric's KB page and express them as "check <metric>: <separates>".
    """
    seen_pairs: set[tuple[str, str]] = set()
    probes: list[str] = []
    for fe in supporting_events:
        entry = kb.get_metric(fe.source_metric)
        if entry is None:
            continue
        for dis in entry.disambiguators:
            key = (dis.metric, dis.separates)
            if key in seen_pairs:
                continue
            seen_pairs.add(key)
            probes.append(f"Check {dis.metric} → {dis.separates}")
    return probes


# ----------------------------------------------------------------------------
# Convenience: load everything and correlate by episode_id
# ----------------------------------------------------------------------------

def correlate_episode(
    episode_id: str,
    kb: Optional[MetricsKB] = None,
    event_store_path: Optional[Path] = None,
) -> CorrelationResult:
    """Load events for an episode from the store and correlate.

    Convenience wrapper for callers that don't want to manage the KB + store
    lifecycle themselves.
    """
    if kb is None:
        try:
            kb = load_kb()
        except KBLoadError as e:
            log.warning("Cannot correlate — KB load failed: %s", e)
            return CorrelationResult(episode_id=episode_id)

    store = EventStore(event_store_path)
    try:
        events = store.get_events(episode_id=episode_id)
    finally:
        store.close()

    return correlate(kb, events, episode_id=episode_id)
