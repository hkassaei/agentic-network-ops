"""Decision H — NA direct-vs-derived ranking guardrail.

Failure mode (canonical example: `run_20260501_032822_call_quality_degradation`):
    NA mis-ranks when both a direct-measurement flag (e.g.
    `rtpengine_loss_ratio` — RTPEngine's own RTCP receiver-loss
    measurement) AND a derived/cross-layer flag (e.g.
    `upf_activity_during_calls` — a ratio of UPF traffic to IMS dialog
    count) fire on the same anomaly. NA gives the derived flag's NF
    higher fit; the wrong NF wins h1; survives investigation; Synthesis
    ratifies wrong NF with high confidence.

Decision H closes this by enforcing a deterministic post-NA check:
    For every Phase-0 flag classified as `direct`, the named NF must
    either (a) be the `primary_suspect_nf` of at least one ranked
    hypothesis with `explanatory_fit ≥ 0.7`, OR (b) be named in NA's
    `summary` field with explicit demotion reasoning (substring match
    on the NF name AND any of the demotion keywords below).

The classifier (`classify_flag_kind`) reads `MetricEntry.flag_kind` if
authored. Otherwise it falls back to a naming-pattern heuristic:
    * `_during_`, `_consistency`, `_consistent`, `_path_` substrings
      → cross_layer
    * `derived.<nf>_*` or `normalized.<nf>.*` where `<nf>` is a known
      NF name → direct
    * else → derived (conservative — unlabeled flags don't earn
      direct-flag priority weight)

Composes with Decision D (`lint_na_hypotheses`) in
`orchestrator.py` Phase 3: D runs first (mechanism-scoping blocklist);
H runs on D's PASS path. Either may REJECT independently.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional, get_args

from agentic_ops_common.metric_kb.models import MetricEntry, MetricsKB

from ..models import Hypothesis, NetworkAnalystReport
from .base import GuardrailResult, GuardrailVerdict


FlagKind = Literal["direct", "derived", "cross_layer"]


# Substrings in metric names that signal a cross-layer / composite
# reading. Order matters only for clarity in test failures.
_CROSS_LAYER_SUBSTRINGS: tuple[str, ...] = (
    "_during_",
    "_consistency",
    "_consistent",
    "_path_",
)


# Substring tokens in NA's `summary` text that indicate NA is
# explicitly demoting a directly-flagged NF (treating it as a reporter
# rather than a source). Detected together with the NF name itself.
_DEMOTION_KEYWORDS: tuple[str, ...] = (
    "demoted",
    "downstream",
    "observer",
    "reporter",
    "secondary",
    "ruled out",
    "observe",
    "reports",
    "consequence",
    "symptom",
)


# Threshold for "primary or co-primary hypothesis". Below this, the
# linter considers the NF demoted-without-reasoning. Tuned against
# observed runs: well-ranked primaries land at 0.85-0.90; the
# `run_20260501_032822_call_quality_degradation` mis-rank had
# rtpengine at 0.60.
_PRIMARY_FIT_THRESHOLD: float = 0.7


@dataclass
class FlagFinding:
    """One direct-flag finding for the rejection reason."""
    metric: str
    nf: str
    severity: str
    direction: str
    reason: str  # why this finding triggers REJECT


@dataclass
class RankingCoverageResult:
    """Structured output for the linter's REJECT branch."""
    findings: list[FlagFinding] = field(default_factory=list)
    direct_flags_seen: list[tuple[str, str]] = field(default_factory=list)  # (metric, nf)


def classify_flag_kind(
    metric_id: str,
    kb_entry: MetricEntry | None,
    known_nfs: tuple[str, ...],
) -> FlagKind:
    """Return the flag-kind classification for a metric.

    Resolution order:
        1. KB-authored `MetricEntry.flag_kind` (if present and non-None).
        2. Naming-pattern heuristic.

    The KB-authored path is preferred long-term; the heuristic is a
    bootstrap so the linter ships before all 108 metric entries are
    individually labeled.
    """
    if kb_entry is not None and kb_entry.flag_kind is not None:
        return kb_entry.flag_kind

    name = metric_id.lower()

    # Cross-layer signals trump direct-looking prefixes.
    for substring in _CROSS_LAYER_SUBSTRINGS:
        if substring in name:
            return "cross_layer"

    # `derived.<nf>_<rest>` — derived-namespace metric whose first
    # token after `derived.` matches a known NF → direct measurement
    # at that NF, just exposed as a derived rate / ratio.
    if name.startswith("derived."):
        rest = name[len("derived."):]
        # Try matching the longest NF prefix to handle NFs whose names
        # are themselves substrings of others (none today, but defensive).
        for nf in sorted(known_nfs, key=len, reverse=True):
            if rest.startswith(f"{nf}_") or rest == nf:
                return "direct"
        return "derived"

    # `normalized.<nf>.<rest>` — per-UE rate of an NF-owned metric.
    # Treat as direct: the metric still measures the named NF's own
    # behavior, just normalized for deployment scale.
    if name.startswith("normalized."):
        rest = name[len("normalized."):]
        first_segment = rest.split(".", 1)[0] if "." in rest else rest
        if first_segment in known_nfs:
            return "direct"
        return "derived"

    # Default — anything outside the known prefix patterns is derived
    # (conservative).
    return "derived"


def lint_na_ranking_coverage(
    report: NetworkAnalystReport,
    anomaly_flags: list[dict],
    kb: MetricsKB | None,
    known_nfs: tuple[str, ...],
) -> GuardrailResult[NetworkAnalystReport]:
    """Validate ranking coverage for every direct-flag NF.

    Rules per direct flag:
        Pass condition (a): the NF is the `primary_suspect_nf` of at
            least one ranked hypothesis with `explanatory_fit ≥ 0.7`.
        Pass condition (b): the NF name appears in NA's `summary` with
            at least one of the demotion keywords nearby (same string).

    REJECT if neither holds. The reason lists every offending direct
    flag with both quick-fix paths spelled out so NA's resample has
    a clear path forward.
    """
    if not anomaly_flags:
        return GuardrailResult(verdict=GuardrailVerdict.PASS, output=report)

    # Classify each anomaly flag and collect direct ones.
    direct_flags: list[tuple[str, str, dict]] = []  # (metric, nf, raw_dict)
    for flag in anomaly_flags:
        metric_id = flag.get("metric", "")
        nf = flag.get("component", "")
        if not metric_id or not nf:
            continue
        # Look up the metric in the KB. The metric_id format is
        # `<layer>.<nf>.<metric>` for normalized/raw metrics or
        # `derived.<metric>` for derived metrics. The KB.get_metric
        # helper handles both.
        kb_entry = kb.get_metric(metric_id) if kb is not None else None
        kind = classify_flag_kind(metric_id, kb_entry, known_nfs)
        if kind == "direct":
            direct_flags.append((metric_id, nf, flag))

    if not direct_flags:
        return GuardrailResult(verdict=GuardrailVerdict.PASS, output=report)

    # Build a map from primary_suspect_nf to max explanatory_fit across
    # the report's hypotheses.
    fit_by_nf: dict[str, float] = {}
    for h in report.hypotheses:
        prev = fit_by_nf.get(h.primary_suspect_nf, 0.0)
        if h.explanatory_fit > prev:
            fit_by_nf[h.primary_suspect_nf] = h.explanatory_fit

    summary_lower = (report.summary or "").lower()

    findings: list[FlagFinding] = []
    for metric_id, nf, flag in direct_flags:
        # Path (a): NF has a hypothesis with fit ≥ threshold.
        max_fit = fit_by_nf.get(nf, 0.0)
        if max_fit >= _PRIMARY_FIT_THRESHOLD:
            continue
        # Path (b): NF named in summary with demotion keyword.
        if _has_demotion_reasoning(summary_lower, nf):
            continue
        # Neither path holds → finding.
        if nf in fit_by_nf:
            reason = (
                f"named in a hypothesis with fit={max_fit:.2f} (below the "
                f"{_PRIMARY_FIT_THRESHOLD:.2f} primary-rank threshold) and "
                "not demoted with explicit reasoning in `summary`"
            )
        else:
            reason = (
                "not named as the `primary_suspect_nf` of any hypothesis "
                "and not mentioned in `summary` with demotion reasoning"
            )
        findings.append(FlagFinding(
            metric=metric_id,
            nf=nf,
            severity=flag.get("severity", "?"),
            direction=flag.get("direction", "?"),
            reason=reason,
        ))

    if not findings:
        return GuardrailResult(verdict=GuardrailVerdict.PASS, output=report)

    rejection_reason = _build_rejection_reason(findings, fit_by_nf)
    notes = {
        "findings_count": len(findings),
        "direct_flags_seen": [(m, n) for m, n, _ in direct_flags],
        "per_finding": [
            {
                "metric": f.metric,
                "nf": f.nf,
                "severity": f.severity,
                "direction": f.direction,
                "reason": f.reason,
            }
            for f in findings
        ],
    }
    return GuardrailResult(
        verdict=GuardrailVerdict.REJECT,
        output=report,
        reason=rejection_reason,
        notes=notes,
    )


def _has_demotion_reasoning(summary_lower: str, nf: str) -> bool:
    """Check if NA's summary names `nf` with at least one demotion keyword.

    The two must co-occur in the summary text — bare presence of the
    NF name without any demotion keyword does not count (NA might just
    be naming it as a relevant component); bare presence of a demotion
    keyword without the NF name doesn't count either (NA might be
    demoting a different NF).
    """
    nf_lower = nf.lower()
    if nf_lower not in summary_lower:
        return False
    return any(kw in summary_lower for kw in _DEMOTION_KEYWORDS)


def _build_rejection_reason(
    findings: list[FlagFinding],
    fit_by_nf: dict[str, float],
) -> str:
    """Assemble the per-finding rejection feedback NA sees on resample."""
    parts: list[str] = [
        "Your previous NetworkAnalystReport was REJECTED by the post-NA "
        "ranking-coverage linter (Decision H). The linter enforces:",
        "",
        "  Direct-measurement anomaly flags (metrics that measure the "
        "named NF's own state — e.g. `rtpengine_loss_ratio` is RTPEngine's "
        "RTCP-receiver-loss measurement) carry stronger evidential weight "
        "than derived / cross-layer flags. For every direct flag, the "
        "named NF MUST either:",
        "",
        f"    (a) be the `primary_suspect_nf` of at least one ranked "
        f"hypothesis with `explanatory_fit ≥ {_PRIMARY_FIT_THRESHOLD:.2f}`, OR",
        "",
        "    (b) be named in your `summary` field with explicit "
        "demotion reasoning (e.g. \"the rtpengine_loss_ratio flag was "
        "treated as a downstream report from RTPEngine because <evidence>\").",
        "",
        "The following direct flags failed coverage:",
        "",
    ]

    for f in findings:
        parts.append(
            f"  - Direct flag `{f.metric}` on NF `{f.nf}` "
            f"({f.severity}, {f.direction}): {f.reason}."
        )

    parts.extend([
        "",
        "Resample with EITHER:",
        f"  * a hypothesis whose `primary_suspect_nf` matches each flagged NF "
        f"with `explanatory_fit ≥ {_PRIMARY_FIT_THRESHOLD:.2f}`, OR",
        "  * a `summary` that names the NF and gives explicit reasoning for "
        "treating its direct flag as a downstream report (use words like "
        f"{', '.join(repr(k) for k in _DEMOTION_KEYWORDS[:5])}).",
        "",
        "Direct measurements at an NF are the strongest signal the screener "
        "produces. Derived / cross-layer flags involving the same NF often "
        "RIDE on the direct flag, not the other way around — the "
        "`upf_activity_during_calls` collapse on `run_20260501_032822` was "
        "a downstream consequence of the `rtpengine_loss_ratio` direct flag, "
        "not the other way around.",
    ])

    return "\n".join(parts)


def get_known_nfs() -> tuple[str, ...]:
    """Return the canonical NF list from the Hypothesis schema.

    Pulled fresh from the Pydantic Literal so the heuristic stays
    consistent with the rest of the pipeline (same single source of
    truth as Decision A2's per-NF patterns).
    """
    nf_field = Hypothesis.model_fields["primary_suspect_nf"]
    try:
        return tuple(get_args(nf_field.annotation))
    except Exception:
        # Defensive fallback — should never fire in practice.
        return ()
