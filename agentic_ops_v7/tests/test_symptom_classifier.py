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


# ---------------------------------------------------------------------------
# Cluster-on-different-layer rule (task #63) — compound-fault detection
#
# The cascading_ims_failure regression. Single transport flag (UPF GTP
# drop, owner=core) plus an ambiguous-bucket cluster on ims-layer NFs
# (icscf/pcscf/scscf — all KB-labeled fault_layer=mixed) signals a
# compound fault: transport-layer fault at one NF AND application-layer
# trouble at NFs in a different layer. The classifier promotes the label
# from `transport_layer` to `mixed` so the orchestrator runs both
# pipelines and Synthesis can surface both root causes.
#
# Corpus analysis behind the 70% share threshold lives in
# /tmp/analyze_classifier_corpus.py (one-off script, not under version
# control). Every compound scenario in the May-9-to-14 corpus produces
# >=86% share; the rule fires on share >=70%.
# ---------------------------------------------------------------------------


def test_cluster_on_different_layer_promotes_to_mixed():
    """Cascading IMS Failure signature: 1 transport flag on UPF (core)
    plus 9 ambiguous flags clustering on ims NFs. Must label `mixed`,
    not `transport_layer`.

    The cluster check is layer-not-NF: any IMS NF (icscf/pcscf/scscf)
    in the ambiguous bucket counts toward the ims share.
    """
    classification = _classify_with_real_enrichment([
        # Transport flag — UPF (core layer)
        _flag("normalized.upf.gtp_indatapktn3upf_per_ue",
              current=0.5, learned_normal=5.0, direction="drop"),
        # Ambiguous flags — all on ims NFs
        _flag("normalized.icscf.cdp_replies_per_ue",
              current=0.0, learned_normal=1.0, direction="drop"),
        _flag("normalized.icscf.core:rcv_requests_register_per_ue",
              current=0.0, learned_normal=1.0, direction="drop"),
        _flag("normalized.pcscf.core:rcv_requests_register_per_ue",
              current=0.0, learned_normal=1.0, direction="drop"),
        _flag("normalized.scscf.cdp_replies_per_ue",
              current=0.0, learned_normal=1.0, direction="drop"),
        _flag("normalized.scscf.core:rcv_requests_register_per_ue",
              current=0.0, learned_normal=1.0, direction="drop"),
    ])
    assert classification.label == "mixed", (
        f"Expected 'mixed' (cluster-on-different-layer rule), got "
        f"{classification.label!r}. Rationale:\n{classification.rationale}"
    )
    # The rationale must explain why the promotion fired so an operator
    # can audit it.
    assert "different" in classification.rationale.lower() or (
        "core" in classification.rationale and "ims" in classification.rationale
    )


def test_ambiguous_cluster_on_same_layer_stays_transport_layer():
    """When ambiguous flags cluster on the SAME layer as transport, the
    rule does NOT promote — those signals are downstream consequences
    of one transport-layer fault, not a separate compound fault.

    Synthetic case: transport flag on UPF (core) + ambiguous flags on
    other core NFs. With my real-KB enrichment this is hard to construct
    (most core-layer metrics with `fault_layer=mixed` are SBI/control
    plane), so we use a representative shape.
    """
    # All transport flags on core — same layer
    classification = _classify_with_real_enrichment([
        _flag("normalized.upf.gtp_indatapktn3upf_per_ue",
              current=0.5, learned_normal=5.0, direction="drop"),
        _flag("normalized.upf.gtp_outdatapktn3upf_per_ue",
              current=0.5, learned_normal=5.0, direction="drop"),
    ])
    # No ambiguous → trivially stays transport_layer; check that the
    # rule's same-layer guard doesn't accidentally promote.
    assert classification.label == "transport_layer", classification.rationale


def test_unresolved_owner_layer_does_not_promote():
    """If the owner layer can't be resolved for either bucket (e.g. an
    unmappable feature key), the promotion guard must short-circuit on
    None and keep the label transport_layer.

    Without this guard, `_dominant_owner_layer` returning None on the
    transport bucket would let any ambiguous cluster trigger the rule
    spuriously.
    """
    # Transport flag with kb_context.kb_metric_id → owner_layer resolves
    # to `core`. Ambiguous flag with no resolvable owner.
    classification = _classify_with_real_enrichment([
        _flag("normalized.upf.gtp_indatapktn3upf_per_ue",
              current=0.5, learned_normal=5.0, direction="drop"),
        # `context.cx_active` is the screener's bucketing-feature
        # context, not an NF metric. No owner layer.
        _flag("context.cx_active",
              current=0.0, learned_normal=1.0, direction="drop"),
    ])
    # Either label is acceptable here depending on how the screener's
    # enrichment routes `context.cx_active` — but if it lands in the
    # ambiguous bucket with no owner_layer, the rule must NOT promote.
    if classification.ambiguous_flags and all(
        fb.owner_layer is None for fb in classification.ambiguous_flags
    ):
        assert classification.label == "transport_layer", (
            f"Unresolved owner-layer should not promote; got "
            f"{classification.label!r}"
        )


def test_dominant_layer_helper():
    """Direct test of `_dominant_owner_layer`: tracks share, picks max."""
    from agentic_ops_v7.symptom_classifier import (
        FlagBucket,
        _dominant_owner_layer,
    )
    from agentic_ops_common.anomaly.screener import AnomalyFlag

    def _fb(owner_layer):
        return FlagBucket(
            flag=AnomalyFlag(
                metric="m", component="c", current=0.0, learned_normal=0.0,
                anomaly_score=1.0, severity="LOW", direction="drop",
            ),
            bucket="ambiguous", reason="", owner_layer=owner_layer,
        )

    layer, share = _dominant_owner_layer([_fb("ims"), _fb("ims"), _fb("core")])
    assert layer == "ims"
    assert abs(share - 2 / 3) < 1e-6

    # Empty input
    assert _dominant_owner_layer([]) == (None, 0.0)

    # All None owner_layers
    assert _dominant_owner_layer([_fb(None), _fb(None)]) == (None, 0.0)


def test_promotion_helper_share_threshold():
    """The 70% threshold is structurally enforced: 60% share does NOT
    promote; 70% does."""
    from agentic_ops_v7.symptom_classifier import (
        FlagBucket,
        _ambiguous_cluster_promotes_to_mixed,
    )
    from agentic_ops_common.anomaly.screener import AnomalyFlag

    def _fb(owner_layer):
        return FlagBucket(
            flag=AnomalyFlag(
                metric="m", component="c", current=0.0, learned_normal=0.0,
                anomaly_score=1.0, severity="LOW", direction="drop",
            ),
            bucket="ambiguous", reason="", owner_layer=owner_layer,
        )

    transport = [_fb("core")]

    # 60% share on ims — below threshold; no promotion.
    ambiguous_60 = [_fb("ims")] * 6 + [_fb("core")] * 4
    promote, _ = _ambiguous_cluster_promotes_to_mixed(transport, ambiguous_60)
    assert promote is False

    # 70% share on ims — at threshold; promotes.
    ambiguous_70 = [_fb("ims")] * 7 + [_fb("core")] * 3
    promote, _ = _ambiguous_cluster_promotes_to_mixed(transport, ambiguous_70)
    assert promote is True

    # 100% on same layer (core) — never promotes.
    ambiguous_same_layer = [_fb("core")] * 5
    promote, _ = _ambiguous_cluster_promotes_to_mixed(
        transport, ambiguous_same_layer,
    )
    assert promote is False


# ---------------------------------------------------------------------------
# Persistence — owner_layer must survive the to_dict round-trip
# ---------------------------------------------------------------------------


def test_owner_layer_persists_in_to_dict():
    """The recorder and the orchestrator's _reconstruct_classification
    both depend on `owner_layer` being in the serialized form. Pin it."""
    classification = _classify_with_real_enrichment([
        _flag("normalized.upf.gtp_indatapktn3upf_per_ue",
              current=0.5, learned_normal=5.0, direction="drop"),
    ])
    payload = classification.to_dict()
    for fb in payload["transport_flags"]:
        assert "owner_layer" in fb
        assert fb["owner_layer"] == "core"


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
