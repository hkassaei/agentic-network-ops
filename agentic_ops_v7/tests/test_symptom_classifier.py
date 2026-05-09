"""SymptomClassifier — KB-driven classifier tests.

These tests exercise the screener→classifier boundary in the format the
real `AnomalyScreener` produces, which is what the previous (deleted)
fixture-driven tests did NOT do — and which is why the classifier's
`flag.component='derived'` failure mode shipped to production.

The screener, by construction, splits each preprocessor feature key on
the first `.` and emits:

    feature `derived.rtpengine_loss_ratio`
        -> AnomalyFlag(component='derived', metric='rtpengine_loss_ratio')

    feature `normalized.upf.gtp_indatapktn3upf_per_ue`
        -> AnomalyFlag(component='normalized', metric='upf.gtp_indatapktn3upf_per_ue')

Phase 0's `enrich_anomaly_report` then resolves those preprocessor keys
to canonical KB ids (`ims.rtpengine.loss_ratio`,
`core.upf.gtp_indatapktn3upf_per_ue`) and stashes them on
`flag.kb_context.kb_metric_id`. The classifier reads `kb_context` to
look up each flag's KB entry and route on its `fault_layer` field.

Every test below builds flags in the SCREENER'S FORMAT, runs them
through the actual `enrich_anomaly_report`, then asserts what the
classifier returns. That round-trip is the contract that broke last
time, so it's the contract under test.
"""

from __future__ import annotations

import json

import pytest

from agentic_ops_common.anomaly.screener import AnomalyFlag, AnomalyReport
from agentic_ops_common.metric_kb import enrich_anomaly_report, load_kb
from agentic_ops_v7.symptom_classifier import classify


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _flag(feature_key: str, *, current: float, learned_normal: float,
          direction: str, score: float = 1.0,
          severity: str = "MEDIUM") -> AnomalyFlag:
    """Build an `AnomalyFlag` in the SCREENER's actual emission format.

    Mimics `agentic_ops_common.anomaly.screener.AnomalyScreener._extract_flags`,
    which splits on the first `.`:

        feature_key='derived.rtpengine_loss_ratio'
            -> component='derived', metric='rtpengine_loss_ratio'
    """
    parts = feature_key.split(".", 1)
    component = parts[0] if len(parts) > 1 else "unknown"
    metric_name = parts[1] if len(parts) > 1 else feature_key
    return AnomalyFlag(
        metric=metric_name, component=component,
        current=current, learned_normal=learned_normal,
        anomaly_score=score, severity=severity, direction=direction,
    )


def _classify_with_real_enrichment(flags: list[AnomalyFlag]):
    """Run the actual Phase 0 enrichment, then classify.

    This is the round-trip that production follows. Tests that bypass
    `enrich_anomaly_report` aren't testing the classifier's contract;
    they're testing an idealized input the screener doesn't produce.
    """
    report = AnomalyReport(
        flags=flags, overall_score=10.0, threshold=5.0,
        training_samples=300, model_ready=True,
    )
    kb = load_kb()
    enrich_anomaly_report(report, kb)
    return classify(report, kb)


# ---------------------------------------------------------------------------
# The originally-failing scenario — rtpengine 30% tc-netem loss
# ---------------------------------------------------------------------------


def test_rtpengine_30pct_loss_routes_to_path_walker():
    """ADR worked example 1, in screener-actual format.

    The flags below are the exact metrics the v6 chaos run flagged
    in `agentic_ops_v6/docs/agent_logs/run_20260506_132418_call_quality_degradation.md`,
    in the format the screener actually emits — namespaced under
    `derived.` and `normalized.` rather than the NF-name format the
    old fixtures used.

    The contract: at least one transport-bucket flag must surface, so
    the orchestrator routes through the path-walk pipeline. Anything
    less and we are back to v6's "rtpengine.errors_per_second is zero
    therefore rtpengine is healthy" misdiagnosis.
    """
    classification = _classify_with_real_enrichment([
        _flag("derived.rtpengine_loss_ratio",
              current=25.67, learned_normal=0.0, direction="spike", score=2.0),
        _flag("normalized.upf.gtp_indatapktn3upf_per_ue",
              current=3.39, learned_normal=1.45, direction="spike", score=1.0),
        _flag("normalized.upf.gtp_outdatapktn3upf_per_ue",
              current=3.26, learned_normal=1.45, direction="spike", score=1.0),
        _flag("normalized.icscf.core:rcv_requests_invite_per_ue",
              current=0.01, learned_normal=0.0, direction="spike", score=0.6),
        _flag("normalized.pcscf.core:rcv_requests_invite_per_ue",
              current=0.03, learned_normal=0.0, direction="spike", score=0.6),
    ])

    transport_metrics = {
        f"{fb.flag.component}.{fb.flag.metric}"
        for fb in classification.transport_flags
    }
    assert "derived.rtpengine_loss_ratio" in transport_metrics, (
        "rtpengine.loss_ratio must bucket as transport — it's KB-labeled "
        "transport and was the load-bearing signal in worked example 1. "
        f"\nGot bucketing: {classification.rationale}"
    )
    assert classification.label in ("transport_layer", "mixed"), (
        f"label must route through path-walker; got {classification.label}. "
        f"Rationale:\n{classification.rationale}"
    )


# ---------------------------------------------------------------------------
# Each KB fault_layer label routes to its bucket
# ---------------------------------------------------------------------------


def test_kb_transport_label_routes_to_transport_bucket():
    """A KB-labeled `transport` metric, in screener format, must land in
    the transport bucket. This is the v7-design-intent test."""
    classification = _classify_with_real_enrichment([
        _flag("derived.rtpengine_loss_ratio",
              current=10.0, learned_normal=0.0, direction="spike"),
    ])
    assert classification.label == "transport_layer"
    assert len(classification.transport_flags) == 1
    assert "transport" in classification.transport_flags[0].reason


def test_kb_application_label_routes_to_application_bucket():
    """A KB-labeled `application` metric (e.g. AMF authfail) routes
    application_layer — the path-walker stays out of the way."""
    classification = _classify_with_real_enrichment([
        _flag("normalized.amf.fivegs_amffunction_amf_authfail",
              current=5.0, learned_normal=0.0, direction="spike"),
    ])
    assert classification.label == "application_layer"
    assert len(classification.application_flags) == 1


def test_kb_mixed_label_routes_to_ambiguous_bucket():
    """A KB-labeled `mixed` metric (e.g. icscf register rate) goes into
    the ambiguous bucket → verdict `mixed` → path-walker runs first
    and falls through if it finds nothing."""
    classification = _classify_with_real_enrichment([
        _flag("normalized.icscf.core:rcv_requests_register_per_ue",
              current=0.0, learned_normal=0.05, direction="drop"),
    ])
    assert classification.label == "mixed"
    assert len(classification.ambiguous_flags) == 1
    assert "mixed" in classification.ambiguous_flags[0].reason


# ---------------------------------------------------------------------------
# Verdict combinations
# ---------------------------------------------------------------------------


def test_transport_plus_application_yields_mixed():
    """Both a transport and an application signal load-bearing → mixed."""
    classification = _classify_with_real_enrichment([
        _flag("derived.rtpengine_loss_ratio",
              current=10.0, learned_normal=0.0, direction="spike"),
        _flag("normalized.amf.fivegs_amffunction_amf_authfail",
              current=5.0, learned_normal=0.0, direction="spike"),
    ])
    assert classification.label == "mixed"
    assert len(classification.transport_flags) == 1
    assert len(classification.application_flags) == 1


def test_pure_transport_yields_transport_layer():
    """Multiple transport-bucket flags with no application signal →
    transport_layer."""
    classification = _classify_with_real_enrichment([
        _flag("derived.rtpengine_loss_ratio",
              current=10.0, learned_normal=0.0, direction="spike"),
        _flag("normalized.upf.gtp_outdatapktn3upf_per_ue",
              current=0.5, learned_normal=5.0, direction="drop"),
    ])
    assert classification.label == "transport_layer"
    assert len(classification.transport_flags) == 2


def test_pure_application_yields_application_layer():
    """Application-only signals → application_layer (path-walker skipped)."""
    classification = _classify_with_real_enrichment([
        _flag("normalized.amf.fivegs_amffunction_amf_authfail",
              current=5.0, learned_normal=0.0, direction="spike"),
        _flag("normalized.scscf.ims_registrar_scscf:rejected_regs",
              current=3.0, learned_normal=0.0, direction="spike"),
    ])
    assert classification.label == "application_layer"
    assert len(classification.application_flags) == 2


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_none_report_routes_application_layer():
    """No screener output at all → default to application_layer (no
    symptom for the path-walker to localize)."""
    classification = classify(None, load_kb())
    assert classification.label == "application_layer"
    assert "no anomaly flags" in classification.rationale.lower()


def test_empty_flags_routes_application_layer():
    """Screener ran but found nothing → application_layer."""
    empty = AnomalyReport(
        flags=[], overall_score=0.0, threshold=0.0,
        training_samples=300, model_ready=True,
    )
    classification = classify(empty, load_kb())
    assert classification.label == "application_layer"


def test_unmappable_feature_key_falls_to_ambiguous():
    """A feature key that `enrich_anomaly_report` can't map to a KB id
    AND whose (component, metric) doesn't resolve as a legacy NF.metric
    pair should land in the ambiguous bucket — not crash, not get
    silently dropped."""
    classification = _classify_with_real_enrichment([
        _flag("totally_made_up.nonexistent_metric",
              current=99.0, learned_normal=1.0, direction="spike"),
    ])
    assert classification.label == "mixed"  # ambiguous-only -> mixed
    assert len(classification.ambiguous_flags) == 1
    assert "no KB" in classification.ambiguous_flags[0].reason


# ---------------------------------------------------------------------------
# Backward compatibility — direct (NF, metric) construction
# ---------------------------------------------------------------------------


def test_legacy_nf_metric_format_still_resolves():
    """Callers that build AnomalyFlag with `component=<NF-name>` (i.e.
    bypassing the screener) must still resolve to the correct KB entry
    via the fallback NF.metric lookup. This keeps non-screener callers
    (other tests, ad-hoc tools) working without forcing them through
    `enrich_anomaly_report`."""
    flag = AnomalyFlag(
        metric="loss_ratio", component="rtpengine",
        current=10.0, learned_normal=0.0,
        anomaly_score=2.0, severity="MEDIUM", direction="spike",
    )
    report = AnomalyReport(
        flags=[flag], overall_score=10.0, threshold=5.0,
        training_samples=300, model_ready=True,
    )
    # Note: NO enrich_anomaly_report — testing the fallback path.
    classification = classify(report, load_kb())
    assert classification.label == "transport_layer"
    assert len(classification.transport_flags) == 1


# ---------------------------------------------------------------------------
# Structural invariants
# ---------------------------------------------------------------------------


def test_every_flag_lands_in_exactly_one_bucket():
    """Bucketed total must equal input total — no drops, no duplicates."""
    flags = [
        _flag("derived.rtpengine_loss_ratio",
              current=10.0, learned_normal=0.0, direction="spike"),
        _flag("normalized.amf.fivegs_amffunction_amf_authfail",
              current=5.0, learned_normal=0.0, direction="spike"),
        _flag("normalized.icscf.core:rcv_requests_register_per_ue",
              current=0.0, learned_normal=0.05, direction="drop"),
        _flag("totally_made_up.nonexistent_metric",
              current=99.0, learned_normal=1.0, direction="spike"),
    ]
    classification = _classify_with_real_enrichment(flags)
    bucketed = (
        len(classification.transport_flags)
        + len(classification.application_flags)
        + len(classification.ambiguous_flags)
    )
    assert bucketed == len(flags)


def test_classification_is_json_serializable():
    """Phase 0.5 persists the classification into episode metadata as
    JSON. The to_dict form must round-trip cleanly."""
    classification = _classify_with_real_enrichment([
        _flag("derived.rtpengine_loss_ratio",
              current=10.0, learned_normal=0.0, direction="spike"),
    ])
    payload = classification.to_dict()
    rendered = json.dumps(payload)  # would raise on non-serializable values
    parsed = json.loads(rendered)
    assert parsed["label"] == "transport_layer"
    assert parsed["flag_counts"]["transport"] == 1


def test_rationale_cites_kb_label_for_every_flag():
    """The rationale is what an operator audits. It must name the KB
    label that drove each flag's bucket — otherwise the verdict is
    opaque even when correct."""
    classification = _classify_with_real_enrichment([
        _flag("derived.rtpengine_loss_ratio",
              current=10.0, learned_normal=0.0, direction="spike"),
        _flag("normalized.amf.fivegs_amffunction_amf_authfail",
              current=5.0, learned_normal=0.0, direction="spike"),
    ])
    rationale = classification.rationale
    assert "KB-labeled transport" in rationale
    assert "KB-labeled application" in rationale
    assert "rtpengine.loss_ratio" in rationale
    assert "amf" in rationale.lower() and "authfail" in rationale


# ---------------------------------------------------------------------------
# KB-coverage smoke test — every NF block has at least one labeled metric.
# ---------------------------------------------------------------------------


def test_kb_has_fault_layer_on_every_metric():
    """The classifier reads `fault_layer` from KB. If a metric in the KB
    doesn't have one set, an episode that flags it gets ambiguous —
    silently routing to the path-walker fallback. This test pins the
    invariant: every metric must be labeled.

    If you add a new metric to `network_ontology/data/metrics.yaml`,
    label it `transport` / `application` / `mixed` per the rubric in
    `agentic_ops_common/metric_kb/models.py:FaultLayer`. Don't relax
    this test — that's how we end up routing transport faults through
    the application-layer pipeline again.
    """
    kb = load_kb()
    unlabeled: list[str] = []
    for nf, block in kb.metrics.items():
        for metric_name, entry in block.metrics.items():
            if entry.fault_layer is None:
                unlabeled.append(f"{nf}.{metric_name}")
    assert not unlabeled, (
        f"{len(unlabeled)} metric(s) in the KB have no `fault_layer` "
        f"label: {unlabeled[:10]}{'...' if len(unlabeled) > 10 else ''}"
    )
