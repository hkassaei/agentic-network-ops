"""SymptomClassifier — KB-driven Phase 0.5 classifier over screener output.

Per ADR `path_anchored_probe_planning_for_transport_layer_faults.md`,
the classifier labels every screener output as one of:

    transport_layer    Load-bearing signal is a kernel/network-layer
                       fault (qdisc drop, NIC error, switch discard,
                       IPsec replay, BGP withdraw — anything below the
                       application's recv()/send() API).
    application_layer  Load-bearing signal is an NF-internal
                       application fault (stuck Diameter peer,
                       crashed process, misconfiguration, mis-
                       provisioned subscriber).
    mixed              Both signatures co-load-bearing, OR the
                       evidence is ambiguous between the two.

Bucketing is a single KB lookup per flag: read the metric's
`fault_layer` field (`transport` / `application` / `mixed`) and
bucket accordingly. The label travels with the metric in the KB
rather than being re-derived at runtime from heuristics, so the
classifier has no per-metric special cases and adding a new metric
to the KB automatically adds it to the classifier's vocabulary.

Final label:
    transport-bucket non-empty             -> transport_layer
    application-bucket non-empty, T==0     -> application_layer
    both T and A non-empty                 -> mixed
    only mixed/unknown flags               -> mixed
    no flags at all                        -> application_layer
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

from agentic_ops_common.anomaly.screener import AnomalyFlag, AnomalyReport
from agentic_ops_common.metric_kb import MetricsKB
from agentic_ops_common.metric_kb.models import FaultLayer, MetricEntry


SymptomLabel = Literal["transport_layer", "application_layer", "mixed"]
SignalBucket = Literal["transport", "application", "ambiguous"]


@dataclass(frozen=True)
class FlagBucket:
    """One classified anomaly flag plus the reason it landed in its bucket."""
    flag: AnomalyFlag
    bucket: SignalBucket
    reason: str


@dataclass(frozen=True)
class SymptomClassification:
    """The classifier's verdict for one screener output.

    Attributes:
        label:           transport_layer | application_layer | mixed.
        rationale:       One-paragraph human-readable explanation that
                         names the load-bearing metrics and the KB labels
                         that drove the verdict.
        transport_flags: Flags whose KB `fault_layer` is `transport`.
        application_flags: Flags whose KB `fault_layer` is `application`.
        ambiguous_flags: Flags whose KB `fault_layer` is `mixed`, plus
                         any flag whose KB entry could not be resolved
                         or had no `fault_layer` set.
    """
    label: SymptomLabel
    rationale: str
    transport_flags: list[FlagBucket] = field(default_factory=list)
    application_flags: list[FlagBucket] = field(default_factory=list)
    ambiguous_flags: list[FlagBucket] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serializable form for episode-log persistence.

        `kb_metric_id` is included per flag so `_reconstruct_classification`
        can rehydrate enough of `flag.kb_context` for the path resolver
        to recover the canonical (nf, metric_short) pair. Without it,
        the resolver falls back to (flag.component, flag.metric) which
        is the screener's `derived` / `normalized` namespace prefix,
        not an NF name — and every flow scores zero.
        """
        def _flag_dict(fb: FlagBucket) -> dict:
            kb_id = None
            if fb.flag.kb_context is not None:
                kb_id = fb.flag.kb_context.kb_metric_id
            return {
                "metric": fb.flag.metric,
                "component": fb.flag.component,
                "current": fb.flag.current,
                "learned_normal": fb.flag.learned_normal,
                "direction": fb.flag.direction,
                "severity": fb.flag.severity,
                "anomaly_score": round(fb.flag.anomaly_score, 3),
                "kb_metric_id": kb_id,
                "bucket": fb.bucket,
                "reason": fb.reason,
            }
        return {
            "label": self.label,
            "rationale": self.rationale,
            "flag_counts": {
                "transport": len(self.transport_flags),
                "application": len(self.application_flags),
                "ambiguous": len(self.ambiguous_flags),
            },
            "transport_flags": [_flag_dict(fb) for fb in self.transport_flags],
            "application_flags": [_flag_dict(fb) for fb in self.application_flags],
            "ambiguous_flags": [_flag_dict(fb) for fb in self.ambiguous_flags],
        }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def classify(report: Optional[AnomalyReport], kb: MetricsKB) -> SymptomClassification:
    """Classify a screener output as transport_layer / application_layer / mixed.

    Inputs:
        report: The screener's AnomalyReport. None or empty flags -> default
                to application_layer (nothing for the path walk to localize).
        kb:     The loaded MetricsKB; each flag is resolved to its KB entry
                via `flag.kb_context.kb_metric_id` (preferred, populated by
                Phase 0's `enrich_anomaly_report`) or a legacy NF.metric
                lookup. The entry's `fault_layer` field decides the bucket.

    Output: SymptomClassification with the label, rationale, and bucketed flags.
    """
    if report is None or not report.flags:
        return SymptomClassification(
            label="application_layer",
            rationale=(
                "No anomaly flags in the screener output. Nothing for the "
                "transport-layer path walk to localize; the orchestrator "
                "routes through the application-layer pipeline by default."
            ),
        )

    transport_flags: list[FlagBucket] = []
    application_flags: list[FlagBucket] = []
    ambiguous_flags: list[FlagBucket] = []

    for flag in report.flags:
        bucket, reason = _bucket_flag(flag, kb)
        record = FlagBucket(flag=flag, bucket=bucket, reason=reason)
        if bucket == "transport":
            transport_flags.append(record)
        elif bucket == "application":
            application_flags.append(record)
        else:
            ambiguous_flags.append(record)

    label, rationale = _decide_label(
        transport_flags, application_flags, ambiguous_flags,
    )
    return SymptomClassification(
        label=label,
        rationale=rationale,
        transport_flags=transport_flags,
        application_flags=application_flags,
        ambiguous_flags=ambiguous_flags,
    )


# ---------------------------------------------------------------------------
# Per-flag bucketing — one KB lookup, one branch on fault_layer
# ---------------------------------------------------------------------------


def _bucket_flag(flag: AnomalyFlag, kb: MetricsKB) -> tuple[SignalBucket, str]:
    """Bucket one flag by its KB-authored `fault_layer` label.

    No heuristics. The KB's `fault_layer` is the single source of truth.
    Flags whose KB entry can't be resolved, or whose entry has no
    `fault_layer` set, fall through to the ambiguous bucket — they
    contribute to a `mixed` verdict (path walker runs first; falls
    through to application-layer if it produces null localization).
    """
    entry, kb_metric_id = _resolve_kb_entry(flag, kb)
    direction = (flag.direction or "shift").lower()

    if entry is None:
        return ("ambiguous",
                f"no KB entry for {flag.component}.{flag.metric} — "
                f"classification ambiguous")

    if entry.fault_layer is None:
        return ("ambiguous",
                f"{kb_metric_id} has no `fault_layer` label in the KB — "
                f"classification ambiguous")

    label = entry.fault_layer
    label_str = label.value
    cite = kb_metric_id or f"{flag.component}.{flag.metric}"
    reason = (
        f"KB-labeled {label_str}: {cite} ({direction}, "
        f"score={flag.anomaly_score:.2f})"
    )

    if label is FaultLayer.TRANSPORT:
        return ("transport", reason)
    if label is FaultLayer.APPLICATION:
        return ("application", reason)
    # FaultLayer.MIXED -> the metric itself genuinely moves under either
    # kind of fault. Path walker runs first; falls through if null.
    return ("ambiguous", reason)


def _resolve_kb_entry(
    flag: AnomalyFlag, kb: MetricsKB,
) -> tuple[Optional[MetricEntry], Optional[str]]:
    """Resolve a flag to its KB entry.

    Preferred path: `flag.kb_context.kb_metric_id` (e.g.
    `ims.rtpengine.loss_ratio`), populated by Phase 0's
    `enrich_anomaly_report`. This is the canonical mapping that survives
    the screener's `derived` / `normalized` namespace prefixes — the
    failure mode that broke v7's first run.

    Fallback: `kb.metrics[flag.component][flag.metric]`. Works only when
    `flag.component` is already an NF name (e.g. `rtpengine`), which is
    the format hand-authored test fixtures use. Real screener output
    needs the kb_metric_id path.

    Returns (entry, kb_metric_id). `kb_metric_id` is the canonical id we
    found, or None if we fell back to the legacy lookup.
    """
    kb_id = None
    if flag.kb_context and flag.kb_context.kb_metric_id:
        kb_id = flag.kb_context.kb_metric_id
        entry = kb.get_metric(kb_id)
        if entry is not None:
            return entry, kb_id

    if flag.component and flag.metric:
        nf_block = kb.metrics.get(flag.component)
        if nf_block is not None:
            entry = nf_block.metrics.get(flag.metric)
            if entry is not None:
                return entry, f"{flag.component}.{flag.metric}"

    return None, kb_id


# ---------------------------------------------------------------------------
# Final-label decision
# ---------------------------------------------------------------------------


def _decide_label(
    transport: list[FlagBucket],
    application: list[FlagBucket],
    ambiguous: list[FlagBucket],
) -> tuple[SymptomLabel, str]:
    """Pick the final label and render a one-paragraph rationale.

    Decision table:
        only transport             -> transport_layer
        only application           -> application_layer
        both transport + app       -> mixed
        only ambiguous             -> mixed (path walk runs first; falls
                                            through to application-layer
                                            if it produces null localization)
        empty input                -> application_layer (caller short-circuits)
    """
    n_t, n_a, n_x = len(transport), len(application), len(ambiguous)

    if n_t > 0 and n_a == 0:
        label: SymptomLabel = "transport_layer"
        rationale = _render_rationale(
            label, transport, application, ambiguous,
            verdict_summary=(
                f"{n_t} transport-layer signal(s); no application-layer "
                f"smoking guns. Routes to the deterministic path walk "
                f"(see ADR path_anchored_probe_planning_for_transport_layer_faults.md)."
            ),
        )
        return label, rationale

    if n_a > 0 and n_t == 0:
        label = "application_layer"
        rationale = _render_rationale(
            label, transport, application, ambiguous,
            verdict_summary=(
                f"{n_a} application-layer signal(s); no transport-layer "
                f"signatures. Routes through the existing per-NF NA -> IG "
                f"-> Investigator -> Synthesis pipeline."
            ),
        )
        return label, rationale

    if n_t > 0 and n_a > 0:
        label = "mixed"
        rationale = _render_rationale(
            label, transport, application, ambiguous,
            verdict_summary=(
                f"Both transport-layer ({n_t}) and application-layer "
                f"({n_a}) signals are load-bearing. Path walk runs first; "
                f"falls through to the application-layer pipeline if the "
                f"walk produces null localization."
            ),
        )
        return label, rationale

    # Only ambiguous flags (n_t == 0 and n_a == 0 and n_x > 0)
    label = "mixed"
    rationale = _render_rationale(
        label, transport, application, ambiguous,
        verdict_summary=(
            f"{n_x} ambiguous signal(s) — KB labels them `mixed` or could "
            f"not be resolved. Path walk runs first to attempt deterministic "
            f"localization; falls through to the application-layer pipeline "
            f"if no hop attribution is found."
        ),
    )
    return label, rationale


def _render_rationale(
    label: SymptomLabel,
    transport: list[FlagBucket],
    application: list[FlagBucket],
    ambiguous: list[FlagBucket],
    verdict_summary: str,
) -> str:
    """Render the rationale as a single readable paragraph.

    Cites the load-bearing metrics in each bucket so an operator can
    audit the verdict against the original anomaly flags and the KB
    labels that drove the bucketing.
    """
    parts: list[str] = [f"label={label}. {verdict_summary}"]

    def _fmt(buckets: list[FlagBucket], header: str) -> str:
        if not buckets:
            return ""
        # Sort by anomaly score descending so the most load-bearing
        # are surfaced first.
        sorted_buckets = sorted(
            buckets, key=lambda fb: -fb.flag.anomaly_score,
        )
        items = []
        for fb in sorted_buckets[:5]:  # cap at 5 to keep paragraph readable
            items.append(
                f"{fb.flag.component}.{fb.flag.metric} "
                f"({fb.flag.direction}, score={fb.flag.anomaly_score:.2f}) "
                f"— {fb.reason}"
            )
        more = "" if len(sorted_buckets) <= 5 else f" [+{len(sorted_buckets) - 5} more]"
        return f"{header}: " + "; ".join(items) + more

    if transport:
        parts.append(_fmt(transport, "Transport signals"))
    if application:
        parts.append(_fmt(application, "Application signals"))
    if ambiguous:
        parts.append(_fmt(ambiguous, "Ambiguous signals"))

    return "\n\n".join(parts)
