"""Unit tests for guardrails/na_ranking — Decision H, PR 9.

Pure-Python tests over Pydantic-typed report + dict-shaped anomaly
flags. KB metadata is mocked via in-memory MetricEntry instances; no
YAML loads, no ADK runtime.
"""

from __future__ import annotations

import pytest

from agentic_ops_common.metric_kb.models import (
    Healthy,
    Layer,
    MetricEntry,
    MetricsKB,
    NFBlock,
)
from agentic_ops_v6.guardrails.base import GuardrailVerdict
from agentic_ops_v6.guardrails.na_ranking import (
    classify_flag_kind,
    get_known_nfs,
    lint_na_ranking_coverage,
)
from agentic_ops_v6.models import (
    Hypothesis,
    LayerStatus,
    NetworkAnalystReport,
)


KNOWN_NFS = get_known_nfs()


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def _hyp(*, hid: str, nf: str, fit: float = 0.85) -> Hypothesis:
    return Hypothesis(
        id=hid,
        statement=f"{nf} is the source of the anomaly.",
        primary_suspect_nf=nf,
        supporting_events=["evt"],
        explanatory_fit=fit,
        falsification_probes=["measure_rtt(x, y)"],
        specificity="specific",
    )


def _report(*, summary: str = "test summary", hyps: list[Hypothesis] | None = None) -> NetworkAnalystReport:
    return NetworkAnalystReport(
        summary=summary,
        layer_status={"core": LayerStatus(rating="red", note="test")},
        hypotheses=hyps or [_hyp(hid="h1", nf="upf")],
    )


def _flag(*, metric: str, component: str, severity: str = "MEDIUM",
          direction: str = "spike") -> dict:
    return {
        "metric": metric,
        "component": component,
        "current": 1.0,
        "learned_normal": 0.0,
        "anomaly_score": 1.5,
        "severity": severity,
        "direction": direction,
    }


# ---------------------------------------------------------------------------
# classify_flag_kind — heuristic
# ---------------------------------------------------------------------------


def test_classify_derived_with_known_nf_prefix_is_direct():
    """`derived.<nf>_*` is a direct measurement at <nf>."""
    assert classify_flag_kind(
        "derived.rtpengine_loss_ratio", None, KNOWN_NFS,
    ) == "direct"


def test_classify_normalized_with_known_nf_is_direct():
    assert classify_flag_kind(
        "normalized.icscf.cdp_replies_per_ue", None, KNOWN_NFS,
    ) == "direct"


def test_classify_during_substring_is_cross_layer():
    """`_during_` substring overrides any prefix match — it's a
    cross-layer signal even if the prefix names a single NF."""
    assert classify_flag_kind(
        "derived.upf_activity_during_calls", None, KNOWN_NFS,
    ) == "cross_layer"


def test_classify_consistency_substring_is_cross_layer():
    assert classify_flag_kind(
        "derived.cross_layer_consistency", None, KNOWN_NFS,
    ) == "cross_layer"


def test_classify_path_substring_is_cross_layer():
    assert classify_flag_kind(
        "derived.n3_path_loss", None, KNOWN_NFS,
    ) == "cross_layer"


def test_classify_unknown_prefix_defaults_to_derived():
    """Conservative default: anything outside the known prefix patterns
    doesn't earn direct-flag priority weight."""
    assert classify_flag_kind(
        "unknown.some_metric", None, KNOWN_NFS,
    ) == "derived"


def test_classify_kb_authored_overrides_heuristic():
    """An explicit `flag_kind` in the KB entry trumps the heuristic."""
    entry = MetricEntry.model_construct(
        source="prometheus",
        type="gauge",
        description="test",
        healthy=Healthy.model_construct(),
        flag_kind="cross_layer",
    )
    # Heuristic alone says direct; KB says cross_layer; KB wins.
    assert classify_flag_kind(
        "derived.rtpengine_loss_ratio", entry, KNOWN_NFS,
    ) == "cross_layer"


# ---------------------------------------------------------------------------
# lint_na_ranking_coverage — PASS paths
# ---------------------------------------------------------------------------


def test_pass_when_no_flags():
    report = _report()
    result = lint_na_ranking_coverage(report, [], None, KNOWN_NFS)
    assert result.verdict is GuardrailVerdict.PASS


def test_pass_when_only_derived_or_cross_layer_flags():
    """Cross-layer flags don't enforce ranking on any single NF."""
    report = _report(hyps=[_hyp(hid="h1", nf="upf", fit=0.85)])
    flags = [
        _flag(metric="derived.upf_activity_during_calls", component="upf"),
    ]
    result = lint_na_ranking_coverage(report, flags, None, KNOWN_NFS)
    assert result.verdict is GuardrailVerdict.PASS


def test_pass_when_direct_flag_nf_is_top_hypothesis():
    """rtpengine has direct flag; report ranks rtpengine at fit=0.9."""
    report = _report(hyps=[
        _hyp(hid="h1", nf="rtpengine", fit=0.9),
        _hyp(hid="h2", nf="upf", fit=0.5),
    ])
    flags = [
        _flag(metric="derived.rtpengine_loss_ratio", component="rtpengine"),
    ]
    result = lint_na_ranking_coverage(report, flags, None, KNOWN_NFS)
    assert result.verdict is GuardrailVerdict.PASS


def test_pass_when_demoted_with_reasoning_in_summary():
    """rtpengine has direct flag; not in any high-fit hypothesis; BUT
    summary names rtpengine + a demotion keyword."""
    report = _report(
        summary=(
            "The data plane is broken at upf. The rtpengine packet loss is "
            "treated as a downstream report, not a source signal."
        ),
        hyps=[_hyp(hid="h1", nf="upf", fit=0.9)],
    )
    flags = [
        _flag(metric="derived.rtpengine_loss_ratio", component="rtpengine"),
    ]
    result = lint_na_ranking_coverage(report, flags, None, KNOWN_NFS)
    assert result.verdict is GuardrailVerdict.PASS


# ---------------------------------------------------------------------------
# lint_na_ranking_coverage — REJECT paths
# ---------------------------------------------------------------------------


def test_reject_when_direct_flag_nf_demoted_below_threshold():
    """The call_quality_degradation pattern: rtpengine has direct
    flag, NA ranked rtpengine at h2 fit=0.6 (below the 0.80 threshold),
    no demotion reasoning in summary → REJECT."""
    report = _report(
        summary="The data plane is broken at upf and the upf is overloaded.",
        hyps=[
            _hyp(hid="h1", nf="upf", fit=0.9),
            _hyp(hid="h2", nf="rtpengine", fit=0.6),  # below threshold
            _hyp(hid="h3", nf="upf", fit=0.4),
        ],
    )
    flags = [
        _flag(metric="derived.rtpengine_loss_ratio", component="rtpengine"),
    ]
    result = lint_na_ranking_coverage(report, flags, None, KNOWN_NFS)
    assert result.verdict is GuardrailVerdict.REJECT
    assert "rtpengine" in result.reason
    assert "rtpengine_loss_ratio" in result.reason
    assert "0.60" in result.reason or "0.6" in result.reason
    notes = result.notes
    assert notes["findings_count"] == 1
    assert notes["per_finding"][0]["nf"] == "rtpengine"
    assert notes["per_finding"][0]["metric"] == "derived.rtpengine_loss_ratio"


def test_reject_at_fit_exactly_0_70_post_pr9_tightening():
    """`run_20260501_042127_call_quality_degradation` had rtpengine at
    exactly fit=0.70 with invented demotion reasoning in summary.
    Pre-tightening (threshold=0.70), path (a) passed at the boundary.
    Post-tightening (threshold=0.80), fit=0.70 falls below threshold.

    NOTE: this test exercises path (a) only. It uses a summary that
    DOES NOT include demotion keywords so path (b) cannot rescue.
    """
    report = _report(
        summary="The data plane is broken at upf.",
        hyps=[
            _hyp(hid="h1", nf="upf", fit=0.9),
            _hyp(hid="h2", nf="rtpengine", fit=0.70),  # exactly at old boundary
        ],
    )
    flags = [
        _flag(metric="derived.rtpengine_loss_ratio", component="rtpengine"),
    ]
    result = lint_na_ranking_coverage(report, flags, None, KNOWN_NFS)
    assert result.verdict is GuardrailVerdict.REJECT
    assert "0.70" in result.reason
    # The threshold is rendered as 0.80 in the rejection text.
    assert "0.80" in result.reason


def test_pass_at_fit_0_80_post_pr9_tightening():
    """fit=0.80 exactly meets the new threshold (>=) and passes."""
    report = _report(
        summary="upf is the source.",
        hyps=[
            _hyp(hid="h1", nf="upf", fit=0.9),
            _hyp(hid="h2", nf="rtpengine", fit=0.80),
        ],
    )
    flags = [
        _flag(metric="derived.rtpengine_loss_ratio", component="rtpengine"),
    ]
    result = lint_na_ranking_coverage(report, flags, None, KNOWN_NFS)
    assert result.verdict is GuardrailVerdict.PASS


def test_reject_when_direct_flag_nf_completely_missing():
    """rtpengine has direct flag; NA didn't include rtpengine in any
    hypothesis at all and didn't mention it in summary → REJECT."""
    report = _report(
        summary="The data plane is broken at upf.",
        hyps=[_hyp(hid="h1", nf="upf", fit=0.9)],
    )
    flags = [
        _flag(metric="derived.rtpengine_loss_ratio", component="rtpengine"),
    ]
    result = lint_na_ranking_coverage(report, flags, None, KNOWN_NFS)
    assert result.verdict is GuardrailVerdict.REJECT
    assert "rtpengine" in result.reason
    assert "not named" in result.reason or "below" in result.reason


def test_reject_when_summary_names_nf_but_no_demotion_keyword():
    """Bare presence of NF name in summary doesn't count without a
    demotion keyword."""
    report = _report(
        summary=(
            "The data plane shows multiple anomalies including "
            "rtpengine packet loss and upf activity collapse."
        ),
        hyps=[_hyp(hid="h1", nf="upf", fit=0.9)],
    )
    flags = [
        _flag(metric="derived.rtpengine_loss_ratio", component="rtpengine"),
    ]
    result = lint_na_ranking_coverage(report, flags, None, KNOWN_NFS)
    # rtpengine named but no demotion keyword → REJECT
    assert result.verdict is GuardrailVerdict.REJECT


def test_reject_when_demotion_keyword_present_but_for_different_nf():
    """Both NF name and demotion keyword must co-occur in summary —
    a demotion keyword for a different NF doesn't help."""
    report = _report(
        summary=(
            "pyhss is treated as a downstream observer; upf is the source."
        ),
        hyps=[_hyp(hid="h1", nf="upf", fit=0.9)],
    )
    flags = [
        _flag(metric="derived.rtpengine_loss_ratio", component="rtpengine"),
    ]
    result = lint_na_ranking_coverage(report, flags, None, KNOWN_NFS)
    # rtpengine not even named → REJECT
    assert result.verdict is GuardrailVerdict.REJECT


def test_reject_groups_multiple_findings():
    """Two direct flags on different NFs both fail coverage."""
    report = _report(
        summary="upf is the source.",
        hyps=[_hyp(hid="h1", nf="upf", fit=0.9)],
    )
    flags = [
        _flag(metric="derived.rtpengine_loss_ratio", component="rtpengine"),
        _flag(metric="normalized.pcscf.processing_time", component="pcscf"),
    ]
    result = lint_na_ranking_coverage(report, flags, None, KNOWN_NFS)
    assert result.verdict is GuardrailVerdict.REJECT
    assert result.notes["findings_count"] == 2
    nfs = {f["nf"] for f in result.notes["per_finding"]}
    assert nfs == {"rtpengine", "pcscf"}


# ---------------------------------------------------------------------------
# Replay run_20260501_032822 shape
# ---------------------------------------------------------------------------


def test_replay_call_quality_degradation_rejects_rtpengine_at_h2():
    """The actual run had rtpengine at h2 fit=0.6 with a direct flag.
    Decision H must REJECT and force NA to either bump rtpengine to
    h1 or include explicit demotion reasoning."""
    report = _report(
        summary=(
            "The network anomaly is primarily characterized by a severe "
            "data plane failure, where active calls have no corresponding "
            "media traffic, pointing to a fault in the UPF or the media "
            "path to the RTPEngine."
        ),
        hyps=[
            _hyp(hid="h1", nf="upf", fit=0.9),
            _hyp(hid="h2", nf="rtpengine", fit=0.6),
            _hyp(hid="h3", nf="upf", fit=0.4),
        ],
    )
    flags = [
        # The two flags from the actual run
        _flag(metric="derived.rtpengine_loss_ratio", component="rtpengine"),
        _flag(metric="derived.upf_activity_during_calls", component="upf"),
    ]
    result = lint_na_ranking_coverage(report, flags, None, KNOWN_NFS)
    assert result.verdict is GuardrailVerdict.REJECT
    # Only rtpengine should be flagged — upf has h1 at 0.9 (passes (a))
    # AND the derived.upf_activity_during_calls metric is cross_layer
    # (doesn't enforce coverage anyway).
    assert result.notes["findings_count"] == 1
    assert result.notes["per_finding"][0]["nf"] == "rtpengine"


# ---------------------------------------------------------------------------
# KB-authored override
# ---------------------------------------------------------------------------


def test_kb_authored_cross_layer_disables_coverage_check():
    """If the KB labels rtpengine_loss_ratio as cross_layer, it no
    longer enforces ranking — even though the heuristic would say
    direct."""
    rtpengine_block = NFBlock.model_construct(
        layer=Layer.IMS,
        metrics={
            "loss_ratio": MetricEntry.model_construct(
                source="derived",
                type="gauge",
                description="test",
                healthy=Healthy.model_construct(),
                flag_kind="cross_layer",  # explicit override
            ),
        },
    )
    kb = MetricsKB.model_construct(metrics={"rtpengine": rtpengine_block})

    report = _report(
        summary="upf is the source.",
        hyps=[_hyp(hid="h1", nf="upf", fit=0.9)],
    )
    flags = [
        # Note: metric_id format is `<source>.<rest>`; the KB lookup
        # uses get_metric which expects `<layer>.<nf>.<metric>` or
        # `<nf>.<metric>`. The `derived.rtpengine_loss_ratio` form
        # falls through KB lookup (returns None) so the heuristic
        # would classify it as direct. Use the layered name for the
        # KB-override path.
        _flag(metric="ims.rtpengine.loss_ratio", component="rtpengine"),
    ]
    result = lint_na_ranking_coverage(report, flags, kb, KNOWN_NFS)
    # KB says cross_layer → no coverage enforcement → PASS.
    assert result.verdict is GuardrailVerdict.PASS
