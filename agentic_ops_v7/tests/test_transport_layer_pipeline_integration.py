"""End-to-end transport-layer pipeline test (classify → resolve → walk → bundle).

Per Phase 4 of ADR `path_anchored_probe_planning_for_transport_layer_faults.md`.

Inputs are built in the SCREENER's actual emission format
(component='derived'/'normalized') and run through the real
`enrich_anomaly_report` before classifying. The walker stage uses
mocked probers — actually exercising tc-netem against a deployed
stack is the live runbook
`docs/runbooks/path_walk_phase4_live_contract_test.md`. This file
covers the deterministic wiring (classifier → resolver → walker → the
markdown bundle the unified Synthesis LLM consumes) end to end against
the same flag formats production sees.

Synthesis is now the v6 LLM agent extended with a localized-verdict
prompt branch (one Synthesis, four verdict_kinds — per the ADR's
"Synthesis gains a `localized` verdict-kind" prescription). Asserting
the LLM's structured output shape is a live-runbook concern, not a
unit test; instead we assert the markdown bundle the LLM reads (via
the `{path_walk_for_synthesis}` template substitution) contains the
load-bearing facts it needs to emit a correct localized verdict:
the attributed hop's name, its attribution kind, and the verbatim
counter excerpt from the kernel's own words.
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

from agentic_ops_v7.orchestrator import _render_path_walk_for_synthesis
from agentic_ops_v7.path_resolver import resolve_path
from agentic_ops_v7.subagents import path_walk_investigator as walker_mod
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
    classify, resolve, walk to rtpengine, and produce a synthesis bundle
    quoting the qdisc evidence so the LLM can emit a localized verdict
    naming rtpengine."""
    classification = _classify_real([
        _flag("derived.rtpengine_loss_ratio",
              current=25.67, learned_normal=0.0, direction="spike", score=2.0),
        _flag("normalized.upf.gtp_indatapktn3upf_per_ue",
              current=3.39, learned_normal=1.45, direction="spike", score=1.0),
        _flag("normalized.upf.gtp_outdatapktn3upf_per_ue",
              current=3.26, learned_normal=1.45, direction="spike", score=1.0),
    ])
    assert classification.label in ("transport_layer", "mixed")

    resolved = resolve_path(classification)
    assert resolved is not None
    assert resolved.flow_id == "vonr_media"

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

    # The LLM Synthesis consumes this bundle via `{path_walk_for_synthesis}`.
    # Assert the load-bearing facts are present so the LLM has what it
    # needs to emit verdict_kind=localized, primary_suspect_nf=rtpengine,
    # and explanation containing the verbatim counter excerpt.
    bundle = _render_path_walk_for_synthesis(walk_report, classification)
    assert "rtpengine" in bundle
    assert "qdisc_netem" in bundle
    assert "drops_attributed_here" in bundle
    assert "loss 30%" in bundle  # verbatim qdisc evidence
    assert "tc -s qdisc show" in bundle
    assert "🎯" in bundle  # marker on the attributed hop in the walk-table
    assert "Path walk" in bundle  # section header


# ---------------------------------------------------------------------------
# ADR worked example 2 — P-CSCF 30% loss
# ---------------------------------------------------------------------------


def test_pcscf_30pct_loss_localizes_correctly(monkeypatch):
    """P-CSCF tc-netem partition: signaling-rate drops downstream and a
    REGISTER-time spike. Walker probes the SIP-path flow, finds qdisc
    drops at pcscf; the synthesis bundle names pcscf as the attributed
    hop."""
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

    bundle = _render_path_walk_for_synthesis(walk_report, classification)
    assert "pcscf" in bundle
    assert "qdisc_netem" in bundle
    assert "loss 30%" in bundle
    assert "🎯" in bundle


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

    bundle = _render_path_walk_for_synthesis(walk_report, classification)
    assert "qdisc_tbf" in bundle
    assert "rate 100Kbit" in bundle  # verbatim tc-tbf evidence excerpt
    assert "upf" in bundle


def test_rtpengine_latency_injection_localizes_via_latency_at_hop(monkeypatch):
    """netem delay 100ms produces LatencyAtHop, not drops. The bundle
    surfaces the authored delay so the LLM emits high-confidence
    latency-attribution localized verdict.

    The screener's only derived rtpengine feature is
    `derived.rtpengine_loss_ratio` — the closed feature set is in
    `agentic_ops_common/anomaly/preprocessor.py:EXPECTED_FEATURE_KEYS`.
    Under tc-netem delay-only, RTCP RRs can show modest loss when
    receiver jitter buffers underrun, so loss_ratio is a plausible
    load-bearing signal even for a delay scenario; combined with the
    UPF rate shifts it gives the resolver enough to pick vonr_media.
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
    assert walk_report.is_localized
    assert walk_report.first_attributed_hop.hop.node == "rtpengine"

    bundle = _render_path_walk_for_synthesis(walk_report, classification)
    assert "latency_at_hop" in bundle
    assert "qdisc_netem_delay" in bundle
    assert "100" in bundle  # the delay value
    assert "delay 100.0ms" in bundle  # verbatim evidence


# ---------------------------------------------------------------------------
# Null localization fallback
# ---------------------------------------------------------------------------


def test_null_localization_does_not_engage_synthesis(monkeypatch):
    """When no hop attributes a fault (e.g. an HSS-unresponsive scenario
    where the fault is application-layer at the peer rather than a
    kernel/network drop), the walker returns is_localized=False and the
    orchestrator falls through to the application-layer pipeline. No
    synthesis bundle is produced for the localized branch."""
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
    # Under the unified Synthesis flow, the orchestrator skips Phase 7
    # entirely on the null-localization branch and falls through to
    # the application-layer pipeline. The bundle helper would still
    # produce a "no hop attributed" string if invoked, but the
    # orchestrator's `_phase06_transport_layer_route` returns None
    # before populating `state["path_walk_for_synthesis"]`.


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
