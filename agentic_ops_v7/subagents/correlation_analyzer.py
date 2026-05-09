"""CorrelationAnalyzer — runs the correlation engine over fired events.

Not an LLM. The correlation engine is deterministic; this wraps it for
consumption by downstream LLM agents (NA and IG) by formatting its output
as text for prompt injection.
"""

from __future__ import annotations

import logging

from agentic_ops_common.correlation import CorrelationResult, correlate
from agentic_ops_common.metric_kb import FiredEvent, MetricsKB

from ..models import CorrelationAnalysis

log = logging.getLogger("v6.correlation_analyzer")


def analyze_correlations(
    kb: MetricsKB,
    events: list[FiredEvent],
    episode_id: str,
) -> CorrelationAnalysis:
    """Run correlation and return a prompt-friendly summary."""
    result = correlate(kb, events, episode_id=episode_id)

    hypotheses_text = _render_correlation_result(result)

    top = result.top_hypothesis()
    return CorrelationAnalysis(
        episode_id=episode_id,
        events_considered=result.events_considered,
        top_statement=top.statement if top else None,
        top_primary_nf=top.primary_nf if top else None,
        top_explanatory_fit=top.explanatory_fit if top else 0.0,
        hypotheses_text=hypotheses_text,
    )


def _render_correlation_result(result: CorrelationResult) -> str:
    if not result.hypotheses:
        if result.events_considered == 0:
            return "No events fired — correlation engine had nothing to work with."
        return (
            f"{result.events_considered} events fired but no composite "
            f"hypothesis emerged. The events may be from independent faults "
            f"or lack registered correlation hints in the KB."
        )

    # Cap rendered output at top 3 hypotheses for consistency with the rest of
    # the pipeline (MAX_PARALLEL_INVESTIGATORS = 3). Correlation engine still
    # produces all matching composites internally, but only the top 3 are
    # shown to the NA as hints and included in the episode report.
    top_hypotheses = result.hypotheses[:3]
    total = len(result.hypotheses)
    suffix = f" (showing top 3 of {total})" if total > 3 else ""

    lines = [
        f"**Correlation engine produced {total} ranked composite hypotheses "
        f"from {result.events_considered} fired events{suffix}:**\n"
    ]
    for i, h in enumerate(top_hypotheses, 1):
        lines.append(
            f"### H{i}: {h.statement}"
        )
        lines.append(f"  - primary_nf: {h.primary_nf}")
        lines.append(f"  - explanatory_fit: {h.explanatory_fit:.2f} "
                     f"({len(h.supporting_event_ids)}/{result.events_considered} events)")
        lines.append(f"  - testability: {h.testability} "
                     f"({len(h.discriminating_metrics)} disambiguating metrics)")
        lines.append(f"  - supporting events: " + ", ".join(f"`{e}`" for e in h.supporting_event_ids))
        if h.discriminating_metrics:
            lines.append(f"  - probes to discriminate:")
            for probe in h.falsification_probes[:5]:
                lines.append(f"      - {probe}")
        lines.append("")

    if result.unmatched_events:
        lines.append(
            f"**{len(result.unmatched_events)} events unmatched by any composite "
            f"hypothesis** (may indicate gaps in the KB's correlates_with or "
            f"truly independent events):"
        )
        for e in result.unmatched_events:
            lines.append(f"  - `{e.event_type}` (nf: `{e.source_nf}`)")

    return "\n".join(lines)
