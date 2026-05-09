"""Localized synthesis — deterministic Synthesis for transport-layer verdicts.

When the orchestrator routes a `transport_layer` symptom through the
path walk and the walker returns a `PathWalkReport` with at least one
attributed hop, Synthesis becomes a deterministic Python step instead
of an LLM agent. The path walk's attribution IS the diagnosis; the
Synthesis layer's job is to render it into a `DiagnosisReport` that
matches the same shape the application-layer Synthesis emits.

This module deliberately does NOT use an LLM. Per ADR
`path_anchored_probe_planning_for_transport_layer_faults.md`, the
Synthesis output for a `localized` verdict is:

    verdict_kind:           "localized"
    primary_suspect_nf:     <hop.node where attribution fired>
    root_cause_confidence:  high (exact counter) | medium (link-diff)
    localization:           the verbatim transport-layer counter excerpt
    explanation:            walk-table showing every hop in topology
                            order with its attribution

A walk-table is what an operator reads to verify the diagnosis. It's
not a narrative essay; it's a per-hop bisection report with the
verbatim counter excerpt for the load-bearing hop.

For a path walk that returned `localization=null` (no hop attributed),
this module returns None — the orchestrator interprets that as "fall
back to the application-layer pipeline" (handles the `mixed` case
where the symptom turned out to be application-layer after all).
"""

from __future__ import annotations

from typing import Optional

from agentic_ops_common.path_walk import (
    DropsAttributedHere,
    DropsAttributedToInboundLink,
    HopRecord,
    InconclusiveHop,
    LatencyAtHop,
    PathWalkReport,
)

from ..models import DiagnosisReport, Localization
from ..symptom_classifier import SymptomClassification


def synthesize_localized(
    report: PathWalkReport,
    classification: SymptomClassification,
) -> Optional[DiagnosisReport]:
    """Render a `localized`-verdict DiagnosisReport from a PathWalkReport.

    Returns None when the walk produced no attribution — the caller
    (orchestrator) interprets this as "the path walk found nothing
    transport-layer; fall back to the application-layer pipeline."
    """
    attributed = report.first_attributed_hop
    if attributed is None:
        return None

    confidence = _confidence_for_attribution(attributed)
    primary_nf = attributed.hop.node
    localization = _attribution_to_localization(attributed)
    summary = _summary(attributed)
    root_cause = _root_cause(attributed)
    recommendation = _recommendation(attributed)
    explanation = _walk_table(report, attributed, classification)
    timeline = _timeline(report, attributed)

    return DiagnosisReport(
        summary=summary,
        root_cause=root_cause,
        root_cause_confidence=confidence,
        primary_suspect_nf=primary_nf,  # type: ignore[arg-type]
        verdict_kind="localized",
        affected_components=_affected_components(attributed),
        timeline=timeline,
        recommendation=recommendation,
        explanation=explanation,
        localization=localization,
    )


# ---------------------------------------------------------------------------
# Field renderers
# ---------------------------------------------------------------------------


def _confidence_for_attribution(record: HopRecord) -> str:
    """Map attribution kind → confidence.

    Exact-counter attributions (kernel qdisc, iptables packet count,
    optical BER, SNMP ifInDiscards) are the source of truth — `high`.
    Inter-hop rate-diff attributions are statistical at small windows
    — `medium`. Latency attributions are exact when authored as
    qdisc-delay; `high` for those, `medium` for measured queueing.
    Inconclusive walks shouldn't reach this function (caller filters).
    """
    a = record.attribution
    if isinstance(a, DropsAttributedHere):
        return "high"
    if isinstance(a, LatencyAtHop):
        # qdisc_netem_delay reads the authored ms value directly — exact.
        if a.counter_kind == "qdisc_netem_delay":
            return "high"
        return "medium"
    if isinstance(a, DropsAttributedToInboundLink):
        return "medium"
    return "low"


def _attribution_to_localization(record: HopRecord) -> Localization:
    """Convert the walker's HopAttribution variant into the
    Pydantic-model Localization used by DiagnosisReport."""
    a = record.attribution
    hop = record.hop

    if isinstance(a, DropsAttributedHere):
        return Localization(
            hop_node=hop.node, hop_kind=hop.kind, hop_iface=hop.iface,
            attribution_kind="drops_attributed_here",
            counter_kind=a.counter_kind,
            dropped_pkts=a.dropped_pkts,
            dropped_pct=a.dropped_pct,
            observed_delay_ms=None,
            evidence=a.evidence,
        )
    if isinstance(a, DropsAttributedToInboundLink):
        return Localization(
            hop_node=hop.node, hop_kind=hop.kind, hop_iface=hop.iface,
            attribution_kind="drops_attributed_to_inbound_link",
            counter_kind="link_rate_diff",
            dropped_pkts=int(round(a.tx_rate - a.rx_rate)),
            dropped_pct=a.observed_loss_pct,
            observed_delay_ms=None,
            evidence=a.evidence,
        )
    if isinstance(a, LatencyAtHop):
        return Localization(
            hop_node=hop.node, hop_kind=hop.kind, hop_iface=hop.iface,
            attribution_kind="latency_at_hop",
            counter_kind=a.counter_kind,
            dropped_pkts=0,
            dropped_pct=None,
            observed_delay_ms=a.observed_delay_ms,
            evidence=a.evidence,
        )
    # Should be unreachable — caller filters InconclusiveHop / CleanHop.
    return Localization(
        hop_node=hop.node, hop_kind=hop.kind, hop_iface=hop.iface,
        attribution_kind="drops_attributed_here",
        counter_kind="unknown",
        dropped_pkts=0, dropped_pct=None, observed_delay_ms=None,
        evidence="(unexpected attribution kind)",
    )


def _summary(record: HopRecord) -> str:
    a = record.attribution
    hop = record.hop
    if isinstance(a, DropsAttributedHere):
        return (
            f"Transport-layer fault localized to {hop.node}[{hop.iface}]: "
            f"{a.counter_kind} reports {a.dropped_pkts} packets dropped "
            f"({_pct(a.dropped_pct)})."
        )
    if isinstance(a, DropsAttributedToInboundLink):
        return (
            f"Transport-layer fault localized to the link entering "
            f"{hop.node}[{hop.iface}]: ~{_pct(a.observed_loss_pct)} loss "
            f"observed via inter-hop rate-diff."
        )
    if isinstance(a, LatencyAtHop):
        return (
            f"Transport-layer latency localized to {hop.node}[{hop.iface}]: "
            f"{a.observed_delay_ms:.0f}ms delay reported by {a.counter_kind}."
        )
    return f"Transport-layer fault localized to {hop.node}."


def _root_cause(record: HopRecord) -> str:
    a = record.attribution
    if isinstance(a, DropsAttributedHere):
        if a.counter_kind == "qdisc_netem":
            return (
                f"Kernel-level packet drop on {record.hop.node}'s egress: "
                f"tc netem qdisc dropping {_pct(a.dropped_pct)} of packets."
            )
        if a.counter_kind == "qdisc_tbf":
            return (
                f"Bandwidth cap on {record.hop.node}: "
                f"tc tbf qdisc dropped {a.dropped_pkts} over-rate packets."
            )
        if a.counter_kind == "iface_dropped":
            return (
                f"Interface-level drops on {record.hop.node}'s "
                f"{record.hop.iface} (likely NIC ring-buffer overrun)."
            )
        if a.counter_kind == "iface_error":
            return (
                f"Interface-level errors on {record.hop.node}'s "
                f"{record.hop.iface} (NIC fault)."
            )
        if a.counter_kind == "iptables_drop":
            return (
                f"iptables FORWARD chain dropping packets at the bridge "
                f"({record.hop.node})."
            )
        if a.counter_kind == "conntrack_drop":
            return (
                f"Conntrack table overflow at the bridge ({record.hop.node})."
            )
        return f"Transport-layer drops at {record.hop.node} ({a.counter_kind})."
    if isinstance(a, DropsAttributedToInboundLink):
        return (
            f"Loss on the link entering {record.hop.node} — neither "
            f"endpoint's local counters fired but TX/RX rate diff "
            f"shows {_pct(a.observed_loss_pct)} loss between hops."
        )
    if isinstance(a, LatencyAtHop):
        return (
            f"Queueing latency at {record.hop.node}: "
            f"{a.observed_delay_ms:.0f}ms ({a.counter_kind})."
        )
    return f"Transport-layer fault at {record.hop.node}."


def _recommendation(record: HopRecord) -> str:
    a = record.attribution
    hop = record.hop
    if isinstance(a, DropsAttributedHere) and a.counter_kind in (
        "qdisc_netem", "qdisc_tbf"
    ):
        return (
            f"Inspect tc qdisc on {hop.node}: "
            f"`docker exec {hop.node} tc -s qdisc show dev {hop.iface}`. "
            f"If the qdisc is from a chaos injection, run the heal "
            f"step. If it's authored, audit the configuration."
        )
    if isinstance(a, DropsAttributedHere) and a.counter_kind == "iface_dropped":
        return (
            f"Investigate NIC / ring buffer on {hop.node}: "
            f"`docker exec {hop.node} ip -s link show dev {hop.iface}`."
        )
    if isinstance(a, DropsAttributedHere) and a.counter_kind in (
        "iptables_drop", "conntrack_drop"
    ):
        return (
            f"Inspect host bridge state: "
            f"`sudo nsenter -t 1 -n iptables -L FORWARD -v -n` "
            f"and `sudo nsenter -t 1 -n conntrack -S`."
        )
    if isinstance(a, DropsAttributedToInboundLink):
        return (
            f"Inspect the link / bridge between hops carrying traffic into "
            f"{hop.node}: rate-diff suggests packets are being lost in the "
            f"transport between adjacent hops, not at either endpoint."
        )
    if isinstance(a, LatencyAtHop):
        return (
            f"Inspect tc qdisc on {hop.node} for an authored delay: "
            f"`docker exec {hop.node} tc qdisc show dev {hop.iface}`."
        )
    return f"Inspect {hop.node}'s transport-layer state."


def _walk_table(
    report: PathWalkReport,
    attributed: HopRecord,
    classification: SymptomClassification,
) -> str:
    """Render the path walk as a per-hop bisection report.

    Operators read this to verify the localization against the
    kernel's own words. Format:

        ## Transport-layer path walk — flow `<flow_id>`

        | hop | kind | iface | prober | attribution |
        | ... | ...  | ...   | ...    | ...         |

        ## Localization

        <hop's verbatim evidence — usually a `tc -s qdisc show` excerpt>

        ## Classifier rationale

        <classification rationale, for context>
    """
    lines: list[str] = []
    lines.append(f"## Transport-layer path walk — flow `{report.flow_id}`")
    lines.append("")
    lines.append(
        f"Walked {len(report.hops)} hop(s) in topology order. "
        f"First-attributed hop: **{attributed.hop.node}[{attributed.hop.iface}]** "
        f"({attributed.attribution.kind})."
    )
    lines.append("")

    lines.append("| # | hop | kind | iface | prober | attribution |")
    lines.append("|---|-----|------|-------|--------|-------------|")
    for i, rec in enumerate(report.hops):
        marker = " 🎯" if rec is attributed else ""
        a = rec.attribution
        attribution_summary = a.kind
        if isinstance(a, DropsAttributedHere):
            attribution_summary = (
                f"{a.kind} ({a.counter_kind}, {a.dropped_pkts} dropped"
                + (f", {_pct(a.dropped_pct)})" if a.dropped_pct is not None else ")")
            )
        elif isinstance(a, DropsAttributedToInboundLink):
            attribution_summary = (
                f"{a.kind} (~{_pct(a.observed_loss_pct)} loss)"
            )
        elif isinstance(a, LatencyAtHop):
            attribution_summary = (
                f"{a.kind} ({a.observed_delay_ms:.0f}ms)"
            )
        elif isinstance(a, InconclusiveHop):
            attribution_summary = f"{a.kind} ({a.reason})"
        lines.append(
            f"| {i + 1} | {rec.hop.node} | {rec.hop.kind} | "
            f"{rec.hop.iface} | {rec.prober} | "
            f"{attribution_summary}{marker} |"
        )

    lines.append("")
    lines.append("## Localization (verbatim evidence)")
    lines.append("")
    lines.append("```")
    lines.append(_get_evidence(attributed.attribution))
    lines.append("```")
    lines.append("")

    lines.append("## Classifier rationale")
    lines.append("")
    lines.append(classification.rationale)

    return "\n".join(lines)


def _affected_components(record: HopRecord) -> list[dict]:
    """Render the same `affected_components` list the application-layer
    Synthesis produces, but with the path-walk's hop named as Root Cause."""
    return [
        {
            "name": record.hop.node,
            "role": "Root Cause",
            "via": f"transport-layer attribution at {record.hop.kind} hop",
        },
    ]


def _timeline(
    report: PathWalkReport, attributed: HopRecord,
) -> list[str]:
    """A short timeline: walk start → attributed hop → walk end."""
    return [
        f"Path-walk started on flow `{report.flow_id}` "
        f"({len(report.hops)} hops in topology order).",
        f"Attribution fired at hop "
        f"`{attributed.hop.node}[{attributed.hop.iface}]` — "
        f"{attributed.attribution.kind}.",
        f"Walk completed; localization confidence: "
        f"{_confidence_for_attribution(attributed)}.",
    ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pct(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.1f}%"


def _get_evidence(attribution) -> str:
    """Pull the evidence string off any attribution variant."""
    return getattr(attribution, "evidence", "(no evidence available)")
