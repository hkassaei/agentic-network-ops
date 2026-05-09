"""End-to-end transport-layer pipeline test (classify → resolve → walk → synthesize).

Per Phase 4 of ADR `path_anchored_probe_planning_for_transport_layer_faults.md`.

Inputs are built in the SCREENER's actual emission format
(component='derived'/'normalized') and run through the real
`enrich_anomaly_report` before classifying. The walker stage uses
mocked probers — actually exercising tc-netem against a deployed
stack is the live runbook
`docs/runbooks/path_walk_phase4_live_contract_test.md`. This file
covers the wiring (classifier → resolver → walker → synthesis) end
to end against the same flag formats production sees.
"""

from __future__ import annotations

import asyncio

import pytest

from agentic_ops_common.anomaly.screener import AnomalyFlag, AnomalyReport
from agentic_ops_common.metric_kb import enrich_anomaly_report, load_kb
from agentic_ops_common.path_walk import (
    CleanHop,
    DropsAttributedHere,
    InconclusiveHop,
    LatencyAtHop,
)

from agentic_ops_v7.path_resolver import resolve_path
from agentic_ops_v7.subagents import path_walk_investigator as walker_mod
from agentic_ops_v7.subagents.localized_synthesis import synthesize_localized
from agentic_ops_v7.subagents.path_walk_investigator import walk_path
from agentic_ops_v7.symptom_classifier import classify, SymptomClassification


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _flag(feature_key: str, *, current: float, learned_normal: float,
          direction: str, score: float = 1.0,
          severity: str = "MEDIUM") -> AnomalyFlag:
    """Build an AnomalyFlag in the screener's actual emission format."""
    parts = feature_key.split(".", 1)
    component = parts[0] if len(parts) > 1 else "unknown"
    metric_name = parts[1] if len(parts) > 1 else feature_key
    return AnomalyFlag(
        metric=metric_name, component=component,
        current=current, learned_normal=learned_normal,
        anomaly_score=score, severity=severity, direction=direction,
    )


def _classify_real(flags: list[AnomalyFlag]) -> SymptomClassification:
    """Run the real Phase 0 enrichment + Phase 0.5 classification."""
    report = AnomalyReport(
        flags=flags, overall_score=10.0, threshold=5.0,
        training_samples=300, model_ready=True,
    )
    kb = load_kb()
    enrich_anomaly_report(report, kb)
    return classify(report, kb)


def _patch_probers_with_attribution_at(
    monkeypatch, target_node: str, attribution,
):
    """Replace prober_for_kind so probes at `target_node` return the
    given attribution; everything else returns CleanHop."""
    def _stub_prober_for_kind(kind):
        class _DispatchProber:
            @property
            def supported_kinds(self):
                return (kind,)

            async def probe(self, hop, window_seconds, anchor_ts):
                if hop.node == target_node:
                    return attribution
                return CleanHop(evidence=f"clean: {hop.node}")
        return _DispatchProber()
    monkeypatch.setattr(walker_mod, "prober_for_kind", _stub_prober_for_kind)

    async def _noop_diff(*args, **kwargs):
        return {"_error": "diff disabled in test"}
    monkeypatch.setattr(
        "agentic_ops_common.tools.reachability.get_link_rate_diff",
        _noop_diff,
    )


# ---------------------------------------------------------------------------
# ADR worked example 1 — rtpengine 30% loss
# ---------------------------------------------------------------------------


def test_rtpengine_30pct_loss_localizes_correctly(monkeypatch):
    """The originally-failing scenario: rtpengine 30% tc-netem loss must
    produce a `localized` verdict naming rtpengine. Inputs are in
    screener-actual format — the round-trip the broken classifier
    silently mishandled in the previous v7 run."""
    classification = _classify_real([
        _flag("derived.rtpengine_loss_ratio",
              current=25.67, learned_normal=0.0, direction="spike", score=2.0),
        _flag("normalized.upf.gtp_indatapktn3upf_per_ue",
              current=3.39, learned_normal=1.45, direction="spike", score=1.0),
        _flag("normalized.upf.gtp_outdatapktn3upf_per_ue",
              current=3.26, learned_normal=1.45, direction="spike", score=1.0),
    ])
    # Routes through the path-walker (transport_layer or mixed).
    assert classification.label in ("transport_layer", "mixed")

    resolved = resolve_path(classification)
    assert resolved is not None
    assert resolved.flow_id == "vonr_media"

    # Mock probers: rtpengine attributes 30% qdisc-netem drops.
    _patch_probers_with_attribution_at(
        monkeypatch, "rtpengine",
        DropsAttributedHere(
            counter_kind="qdisc_netem",
            dropped_pkts=300,
            dropped_pct=0.30,
            evidence=(
                "rtpengine[eth0] qdisc=netem, authored loss=30%: "
                "sent=1000 dropped=300 (30.00%)\n"
                "---tc -s qdisc show dev eth0---\n"
                "qdisc netem 8001: root refcnt 2 limit 1000 loss 30%\n"
                " Sent 60000 bytes 1000 pkt (dropped 300, ...)"
            ),
        ),
    )

    walk_report = asyncio.run(walk_path(
        flow_id=resolved.flow_id,
        hops=resolved.hops,
        anchor_ts=None,
    ))
    assert walk_report.is_localized
    assert walk_report.first_attributed_hop.hop.node == "rtpengine"

    diagnosis = synthesize_localized(walk_report, classification)
    assert diagnosis is not None
    assert diagnosis.verdict_kind == "localized"
    assert diagnosis.primary_suspect_nf == "rtpengine"
    assert diagnosis.root_cause_confidence == "high"

    # Localization payload carries the verbatim qdisc evidence.
    assert diagnosis.localization is not None
    assert diagnosis.localization.hop_node == "rtpengine"
    assert diagnosis.localization.counter_kind == "qdisc_netem"
    assert diagnosis.localization.dropped_pkts == 300
    assert "loss 30%" in diagnosis.localization.evidence
    assert "tc -s qdisc show" in diagnosis.localization.evidence

    # Walk-table shows in the explanation.
    assert "Transport-layer path walk" in diagnosis.explanation
    assert "rtpengine" in diagnosis.explanation
    assert "🎯" in diagnosis.explanation  # marker on the attributed hop


# ---------------------------------------------------------------------------
# ADR worked example 2 — P-CSCF 30% loss
# ---------------------------------------------------------------------------


def test_pcscf_30pct_loss_localizes_correctly(monkeypatch):
    """P-CSCF tc-netem partition: signaling-rate drops downstream and a
    REGISTER-time spike. Walker probes the SIP-path flow, finds qdisc
    drops at pcscf, synthesizes a `localized` verdict."""
    classification = _classify_real([
        _flag("derived.pcscf_avg_register_time_ms",
              current=2500.0, learned_normal=120.0, direction="spike", score=2.0),
        _flag("normalized.pcscf.core:rcv_requests_register_per_ue",
              current=0.0, learned_normal=0.05, direction="drop", score=1.5),
        _flag("normalized.icscf.core:rcv_requests_register_per_ue",
              current=0.0, learned_normal=0.05, direction="drop", score=1.5),
        _flag("normalized.scscf.core:rcv_requests_register_per_ue",
              current=0.0, learned_normal=0.05, direction="drop", score=1.5),
        _flag("normalized.scscf.mar_timeout_ratio",
              current=0.6, learned_normal=0.0, direction="spike", score=1.0),
    ])
    assert classification.label in ("transport_layer", "mixed")

    resolved = resolve_path(classification)
    assert resolved is not None
    walked = {h.node for h in resolved.hops}
    assert "pcscf" in walked

    _patch_probers_with_attribution_at(
        monkeypatch, "pcscf",
        DropsAttributedHere(
            counter_kind="qdisc_netem",
            dropped_pkts=180,
            dropped_pct=0.30,
            evidence="pcscf qdisc netem loss 30% dropped 180",
        ),
    )

    walk_report = asyncio.run(walk_path(
        flow_id=resolved.flow_id, hops=resolved.hops,
    ))
    assert walk_report.is_localized
    assert walk_report.first_attributed_hop.hop.node == "pcscf"

    diagnosis = synthesize_localized(walk_report, classification)
    assert diagnosis is not None
    assert diagnosis.verdict_kind == "localized"
    assert diagnosis.primary_suspect_nf == "pcscf"
    assert diagnosis.root_cause_confidence == "high"


# ---------------------------------------------------------------------------
# Generalization scenarios — different counter kinds
# ---------------------------------------------------------------------------


def test_upf_bandwidth_cap_localizes_via_qdisc_tbf(monkeypatch):
    """tc tbf rate cap drops over-rate packets. The walker's
    KernelHopProber emits DropsAttributedHere with counter_kind=qdisc_tbf,
    distinct from qdisc_netem so operators can tell fault classes apart."""
    classification = _classify_real([
        _flag("normalized.upf.gtp_indatapktn3upf_per_ue",
              current=0.5, learned_normal=5.0, direction="drop", score=2.0),
        _flag("normalized.upf.gtp_outdatapktn3upf_per_ue",
              current=0.5, learned_normal=5.0, direction="drop", score=2.0),
        _flag("normalized.upf.activity_during_calls",
              current=0.1, learned_normal=1.0, direction="drop", score=2.0),
    ])
    assert classification.label in ("transport_layer", "mixed")

    resolved = resolve_path(classification)
    assert resolved is not None
    walked = {h.node for h in resolved.hops}
    assert "upf" in walked

    _patch_probers_with_attribution_at(
        monkeypatch, "upf",
        DropsAttributedHere(
            counter_kind="qdisc_tbf",
            dropped_pkts=42,
            dropped_pct=None,  # tbf doesn't always have a clean denominator
            evidence=(
                "upf[eth0] qdisc=tbf: sent=120 dropped=42\n"
                "---tc -s qdisc show dev eth0---\n"
                "qdisc tbf 8002: root refcnt 2 rate 100Kbit burst 32Kb\n"
                " Sent 7680 bytes 120 pkt (dropped 42, ...)"
            ),
        ),
    )

    walk_report = asyncio.run(walk_path(resolved.flow_id, resolved.hops))
    assert walk_report.is_localized
    assert walk_report.first_attributed_hop.hop.node == "upf"

    diagnosis = synthesize_localized(walk_report, classification)
    assert diagnosis is not None
    assert diagnosis.verdict_kind == "localized"
    assert diagnosis.primary_suspect_nf == "upf"
    assert diagnosis.root_cause_confidence == "high"
    assert diagnosis.localization is not None
    assert diagnosis.localization.counter_kind == "qdisc_tbf"
    assert "tc" in diagnosis.recommendation.lower()


def test_rtpengine_latency_injection_localizes_via_latency_at_hop(monkeypatch):
    """netem delay 100ms produces LatencyAtHop, not drops. Synthesis
    still names rtpengine and reports high confidence (qdisc_netem_delay
    reads the authored delay value directly).

    The screener's only derived rtpengine feature is
    `derived.rtpengine_loss_ratio` — the closed feature set is in
    `agentic_ops_common/anomaly/preprocessor.py:EXPECTED_FEATURE_KEYS`.
    Under tc-netem delay-only, RTCP RRs can show modest loss when
    receiver jitter buffers underrun, so loss_ratio is a plausible
    load-bearing signal even for a delay scenario; combined with the
    UPF rate shifts it gives the resolver enough to pick vonr_media.
    The walker stage is mocked, so the exact metric pattern isn't
    load-bearing for what this test verifies (the LatencyAtHop ->
    synthesis path).
    """
    classification = _classify_real([
        _flag("derived.rtpengine_loss_ratio",
              current=10.0, learned_normal=0.0, direction="spike", score=2.0),
        _flag("normalized.upf.gtp_indatapktn3upf_per_ue",
              current=3.39, learned_normal=1.45, direction="spike", score=1.0),
        _flag("normalized.upf.gtp_outdatapktn3upf_per_ue",
              current=3.26, learned_normal=1.45, direction="spike", score=1.0),
    ])
    assert classification.label in ("transport_layer", "mixed")

    resolved = resolve_path(classification)
    assert resolved is not None
    walked = {h.node for h in resolved.hops}
    assert "rtpengine" in walked

    _patch_probers_with_attribution_at(
        monkeypatch, "rtpengine",
        LatencyAtHop(
            observed_delay_ms=100.0,
            counter_kind="qdisc_netem_delay",
            evidence=(
                "rtpengine[eth0] qdisc=netem: delay 100.0ms\n"
                "---tc -s qdisc show dev eth0---\n"
                "qdisc netem 8001: root refcnt 2 limit 1000 delay 100.0ms\n"
                " Sent 6000 bytes 100 pkt (dropped 0, ...)"
            ),
        ),
    )

    walk_report = asyncio.run(walk_path(
        flow_id=resolved.flow_id, hops=resolved.hops,
    ))
    diagnosis = synthesize_localized(walk_report, classification)
    assert diagnosis is not None
    assert diagnosis.verdict_kind == "localized"
    assert diagnosis.primary_suspect_nf == "rtpengine"
    assert diagnosis.root_cause_confidence == "high"
    assert diagnosis.localization is not None
    assert diagnosis.localization.attribution_kind == "latency_at_hop"
    assert diagnosis.localization.observed_delay_ms == 100.0
    assert "tc" in diagnosis.recommendation.lower()


# ---------------------------------------------------------------------------
# Null localization fallback
# ---------------------------------------------------------------------------


def test_null_localization_returns_none_for_synthesis(monkeypatch):
    """When no hop attributes a fault (e.g. an HSS-unresponsive scenario
    where the fault is application-layer at the peer rather than a
    kernel/network drop), synthesize_localized returns None so the
    orchestrator falls through to the application-layer pipeline."""
    classification = _classify_real([
        _flag("normalized.icscf.uar_timeout_ratio",
              current=0.7, learned_normal=0.0, direction="spike", score=2.0),
        _flag("normalized.scscf.mar_timeout_ratio",
              current=0.6, learned_normal=0.0, direction="spike", score=2.0),
        _flag("normalized.icscf.cdp_replies_per_ue",
              current=0.0, learned_normal=0.05, direction="drop", score=1.0),
    ])
    # Cx timeouts and reply drops are KB-labeled mixed -> walker runs first.
    assert classification.label in ("mixed", "transport_layer")

    resolved = resolve_path(classification)
    assert resolved is not None

    # All hops report clean — application-layer fault doesn't show up
    # at the kernel/network-element layer.
    _patch_probers_with_attribution_at(
        monkeypatch, "nonexistent_node",
        InconclusiveHop(reason="should_not_fire"),
    )

    walk_report = asyncio.run(walk_path(
        flow_id=resolved.flow_id, hops=resolved.hops,
    ))
    assert not walk_report.is_localized

    diagnosis = synthesize_localized(walk_report, classification)
    assert diagnosis is None  # caller falls through to app-layer pipeline


# ---------------------------------------------------------------------------
# Negative tests — application-layer faults must NOT classify transport_layer
#
# A `transport_layer` label routes to the path walk, which would burn
# docker-exec/nsenter probe calls for nothing. The label must be
# `application_layer` for these (or `mixed`, which falls through after
# null localization). Per the Phase 6 deliverable in the ADR:
# "the classifier doesn't false-positive on the application-layer scenario."
# ---------------------------------------------------------------------------


def test_amf_authfail_does_not_classify_transport_layer():
    """AMF auth-failure spike is a pure application-layer signal —
    must never route to the path walker."""
    classification = _classify_real([
        _flag("normalized.amf.fivegs_amffunction_amf_authfail",
              current=10.0, learned_normal=0.0, direction="spike", score=2.0),
    ])
    assert classification.label == "application_layer", (
        f"AMF authfail must classify application_layer; got "
        f"{classification.label}. Rationale:\n{classification.rationale}"
    )


def test_scscf_rejection_does_not_classify_transport_layer():
    """S-CSCF actively rejecting registrations is application — explicit
    rejection counters can't move under tc-netem."""
    classification = _classify_real([
        _flag("normalized.scscf.ims_registrar_scscf:rejected_regs",
              current=10.0, learned_normal=0.0, direction="spike", score=2.0),
        _flag("derived.scscf_registration_reject_ratio",
              current=0.5, learned_normal=0.0, direction="spike", score=2.0),
    ])
    assert classification.label == "application_layer", (
        f"S-CSCF reject signals must classify application_layer; got "
        f"{classification.label}. Rationale:\n{classification.rationale}"
    )
