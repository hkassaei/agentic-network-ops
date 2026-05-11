"""PathResolver — flow + hop-list resolution tests.

Per Phase 4 of ADR `path_anchored_probe_planning_for_transport_layer_faults.md`.

Tests build flags in the SCREENER's actual emission format
(component='derived'/'normalized', metric=<remainder>) and run them
through the real `enrich_anomaly_report` before classifying and
resolving. That round-trip is the contract under test — it's the
boundary that the previous fixture-based tests bypassed, which is
why the original v7 run resolved the wrong flow on the rtpengine
30% loss case.
"""

from __future__ import annotations

import json

import pytest

from agentic_ops_common.anomaly.screener import AnomalyFlag, AnomalyReport
from agentic_ops_common.metric_kb import enrich_anomaly_report, load_kb
from agentic_ops_v7.path_resolver import resolve_path
from agentic_ops_v7.symptom_classifier import classify, SymptomClassification


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _flag(feature_key: str, *, current: float, learned_normal: float,
          direction: str, score: float = 1.0,
          severity: str = "MEDIUM") -> AnomalyFlag:
    """Build an `AnomalyFlag` in the SCREENER's actual emission format.

    The screener splits a feature key on the first `.`, so:
        feature_key='derived.rtpengine_loss_ratio'
            -> component='derived', metric='rtpengine_loss_ratio'
        feature_key='normalized.upf.gtp_indatapktn3upf_per_ue'
            -> component='normalized', metric='upf.gtp_indatapktn3upf_per_ue'
    """
    parts = feature_key.split(".", 1)
    component = parts[0] if len(parts) > 1 else "unknown"
    metric_name = parts[1] if len(parts) > 1 else feature_key
    return AnomalyFlag(
        metric=metric_name, component=component,
        current=current, learned_normal=learned_normal,
        anomaly_score=score, severity=severity, direction=direction,
    )


def _classify_real(flags: list[AnomalyFlag]) -> SymptomClassification:
    """Run enrichment + classification — the same path the orchestrator
    follows in production. Tests that bypass `enrich_anomaly_report`
    aren't testing what runs in production."""
    report = AnomalyReport(
        flags=flags, overall_score=10.0, threshold=5.0,
        training_samples=300, model_ready=True,
    )
    kb = load_kb()
    enrich_anomaly_report(report, kb)
    return classify(report, kb)


# ---------------------------------------------------------------------------
# Per-scenario flow resolution
# ---------------------------------------------------------------------------


def test_resolves_vonr_media_for_rtpengine_loss():
    """ADR worked example 1, in screener-actual format. The flags here
    mirror what `agentic_ops_v6/docs/agent_logs/run_20260506_132418_call_quality_degradation`
    fed the screener: rtpengine RTCP-loss spike + UPF N3 packet rate
    movement. Must resolve to `vonr_media` because that flow's
    observable_metrics name `rtpengine.loss_ratio`. The previous
    resolver tied this between vonr_media and data_pdu_session_user_traffic
    and lost the tie-break — the rtpengine metric-name boost wasn't
    firing because of the period-vs-underscore mismatch."""
    classification = _classify_real([
        _flag("derived.rtpengine_loss_ratio",
              current=25.67, learned_normal=0.0, direction="spike", score=2.0),
        _flag("normalized.upf.gtp_indatapktn3upf_per_ue",
              current=3.39, learned_normal=1.45, direction="spike", score=1.0),
        _flag("normalized.upf.gtp_outdatapktn3upf_per_ue",
              current=3.26, learned_normal=1.45, direction="spike", score=1.0),
    ])
    resolved = resolve_path(classification)
    assert resolved is not None
    assert resolved.flow_id == "vonr_media", (
        f"expected vonr_media, got {resolved.flow_id}. "
        f"Candidates: {resolved.candidate_flows}"
    )


def test_resolves_signaling_path_for_pcscf_loss():
    """ADR worked example 2: P-CSCF tc-netem partition. Signaling-rate
    drops at icscf and scscf REGISTER counters; latency spike at
    P-CSCF; SAR/MAR timeouts at scscf. Resolves to a SIP signaling
    flow — anything but vonr_media."""
    # Note the `derived.<nf>_<metric>` flat-key convention (underscore,
    # not dot) for derived metrics — that's the format the screener
    # actually emits.
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
    resolved = resolve_path(classification)
    assert resolved is not None
    assert resolved.flow_id != "vonr_media", (
        f"P-CSCF signaling fault should not resolve to vonr_media; "
        f"got {resolved.flow_id}. Candidates: {resolved.candidate_flows}"
    )
    # The walked path must include pcscf — that's the implicated NF.
    walked = {h.node for h in resolved.hops}
    assert "pcscf" in walked, (
        f"pcscf must appear on the walk for a P-CSCF symptom; walked: {walked}"
    )


def test_resolves_data_path_for_upf_outage():
    """UPF data plane outage: GTP packet rates drop, activity_during_calls
    collapses. Resolves to a data-path flow (data_pdu_session_user_traffic
    or vonr_media)."""
    classification = _classify_real([
        _flag("normalized.upf.gtp_indatapktn3upf_per_ue",
              current=0.0, learned_normal=5.0, direction="drop", score=2.0),
        _flag("normalized.upf.gtp_outdatapktn3upf_per_ue",
              current=0.0, learned_normal=5.0, direction="drop", score=2.0),
        _flag("normalized.upf.activity_during_calls",
              current=0.0, learned_normal=1.0, direction="drop", score=2.0),
    ])
    resolved = resolve_path(classification)
    assert resolved is not None
    assert resolved.flow_id in ("data_pdu_session_user_traffic", "vonr_media"), (
        f"UPF data-plane outage should resolve to a data-path flow; "
        f"got {resolved.flow_id}. Candidates: {resolved.candidate_flows}"
    )


def test_resolves_diameter_path_for_hss_unresponsive():
    """HSS unresponsive: Cx timeouts at icscf and scscf, no Diameter
    replies. Resolves to a flow walking the icscf↔pyhss↔scscf path."""
    classification = _classify_real([
        _flag("normalized.icscf.uar_timeout_ratio",
              current=0.7, learned_normal=0.0, direction="spike", score=2.0),
        _flag("normalized.icscf.lir_timeout_ratio",
              current=0.5, learned_normal=0.0, direction="spike", score=1.5),
        _flag("normalized.scscf.mar_timeout_ratio",
              current=0.6, learned_normal=0.0, direction="spike", score=2.0),
        _flag("normalized.icscf.cdp_replies_per_ue",
              current=0.0, learned_normal=0.05, direction="drop", score=1.0),
    ])
    resolved = resolve_path(classification)
    assert resolved is not None
    walked = {h.node for h in resolved.hops}
    assert "pyhss" in walked, (
        f"HSS-unresponsive symptom must walk pyhss; got walked={walked}, "
        f"flow={resolved.flow_id}"
    )


# ---------------------------------------------------------------------------
# Hop list shape
# ---------------------------------------------------------------------------


def test_inserts_bridge_hops_between_containers():
    """Every adjacent pair of container hops on the walk has a
    docker_bridge hop between them (per topology's
    `default_inter_container_bridge` rule)."""
    classification = _classify_real([
        _flag("derived.rtpengine_loss_ratio",
              current=10.0, learned_normal=0.0, direction="spike", score=2.0),
    ])
    resolved = resolve_path(classification)
    assert resolved is not None
    for i in range(len(resolved.hops) - 1):
        a = resolved.hops[i]
        b = resolved.hops[i + 1]
        if a.kind == "container" and b.kind == "container":
            pytest.fail(
                f"adjacent container hops without a bridge between them: "
                f"{a.node} -> {b.node} (index {i})"
            )


def test_walks_load_bearing_nf_on_resolved_path():
    """The implicated NF must appear on the walk — otherwise the
    walker can't probe the right interface and we'd repeat the failed
    run's misdiagnosis."""
    classification = _classify_real([
        _flag("derived.rtpengine_loss_ratio",
              current=10.0, learned_normal=0.0, direction="spike", score=2.0),
    ])
    resolved = resolve_path(classification)
    assert resolved is not None
    walked = {h.node for h in resolved.hops}
    assert "rtpengine" in walked, (
        f"rtpengine must appear on the walked path; walked: {walked}"
    )


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_returns_none_on_empty_classification():
    """When the classifier produced no flags, the resolver has nothing
    to score against and returns None — caller falls through to the
    application-layer pipeline."""
    empty = SymptomClassification(label="application_layer", rationale="no flags")
    assert resolve_path(empty) is None


def test_legacy_nf_metric_format_still_resolves():
    """Backward compatibility: if a caller builds AnomalyFlag with
    component=<NF-name> directly (bypassing the screener), the
    resolver's `_flag_nf_metric` falls back to (component, metric)
    and still produces the right NF identification.

    This keeps non-screener callers (ad-hoc tools, future tests)
    working without forcing them through `enrich_anomaly_report`.
    """
    flag = AnomalyFlag(
        metric="loss_ratio", component="rtpengine",
        current=10.0, learned_normal=0.0,
        anomaly_score=2.0, severity="MEDIUM", direction="spike",
    )
    report = AnomalyReport(
        flags=[flag], overall_score=10.0, threshold=5.0,
        training_samples=300, model_ready=True,
    )
    # NO enrichment — testing the fallback path.
    classification = classify(report, load_kb())
    resolved = resolve_path(classification)
    assert resolved is not None
    assert resolved.flow_id == "vonr_media"


# ---------------------------------------------------------------------------
# Serialization + auditability
# ---------------------------------------------------------------------------


def test_to_dict_serializable():
    """The resolved-path dict form persists into episode metadata as JSON."""
    classification = _classify_real([
        _flag("derived.rtpengine_loss_ratio",
              current=10.0, learned_normal=0.0, direction="spike", score=2.0),
    ])
    resolved = resolve_path(classification)
    assert resolved is not None
    payload = resolved.to_dict()
    rendered = json.dumps(payload)
    parsed = json.loads(rendered)
    assert parsed["flow_id"] == "vonr_media"
    assert parsed["hops"]
    assert "rationale" in parsed


def test_rationale_cites_chosen_flow():
    """Operators audit the rationale; it must name the chosen flow."""
    classification = _classify_real([
        _flag("derived.rtpengine_loss_ratio",
              current=10.0, learned_normal=0.0, direction="spike", score=2.0),
    ])
    resolved = resolve_path(classification)
    assert resolved is not None
    assert resolved.flow_id in resolved.rationale


def test_candidate_list_includes_runners_up():
    """Catches a future regression where the resolver short-circuits
    to one flow without considering others."""
    classification = _classify_real([
        _flag("derived.rtpengine_loss_ratio",
              current=10.0, learned_normal=0.0, direction="spike", score=2.0),
        _flag("normalized.upf.gtp_indatapktn3upf_per_ue",
              current=3.39, learned_normal=1.45, direction="spike", score=1.0),
    ])
    resolved = resolve_path(classification)
    assert resolved is not None
    assert len(resolved.candidate_flows) >= 2
    assert resolved.candidate_flows[0][0] == resolved.flow_id


# ---------------------------------------------------------------------------
# Decisive metric-name boost — the bug that lost the rtpengine episode
# ---------------------------------------------------------------------------


def test_rtpengine_loss_metric_decisively_boosts_vonr_media():
    """The rtpengine.loss_ratio flag must produce a metric-name boost
    against `vonr_media`'s observable_metrics blob (which names
    `rtpengine.loss_ratio` in dotted form). The previous bug:
    `_load_bearing_metrics` produced `rtpengine_loss_ratio` (underscore)
    because it read `flag.metric` raw from the screener output, and the
    underscore form didn't substring-match the period form in flows.yaml.
    Result: vonr_media tied with data_pdu_session_user_traffic at
    component-only score, lost the tie-break, and the wrong flow was
    walked.

    The fix: `_flag_nf_metric` recovers the canonical (nf, metric_short)
    pair from `kb_metric_id`, and `_load_bearing_metrics` emits both
    `loss_ratio` and `rtpengine.loss_ratio` forms so the substring
    matcher fires.
    """
    classification = _classify_real([
        _flag("derived.rtpengine_loss_ratio",
              current=10.0, learned_normal=0.0, direction="spike", score=2.0),
        _flag("normalized.upf.gtp_indatapktn3upf_per_ue",
              current=3.39, learned_normal=1.45, direction="spike", score=1.0),
        _flag("normalized.upf.gtp_outdatapktn3upf_per_ue",
              current=3.26, learned_normal=1.45, direction="spike", score=1.0),
    ])
    resolved = resolve_path(classification)
    assert resolved is not None
    by_id = dict(resolved.candidate_flows)
    vonr = by_id.get("vonr_media", 0)
    data_pdu = by_id.get("data_pdu_session_user_traffic", 0)
    assert vonr > data_pdu, (
        f"vonr_media must outscore data_pdu_session_user_traffic for an "
        f"rtpengine fault; got vonr={vonr}, data_pdu={data_pdu}. "
        f"Candidates: {resolved.candidate_flows}"
    )


# ---------------------------------------------------------------------------
# Round-trip preservation — the orchestrator's serialize → state → reconstruct
# path must preserve enough info for the resolver to keep working.
# ---------------------------------------------------------------------------


def test_classification_roundtrip_preserves_resolver_input():
    """The orchestrator persists `classification.to_dict()` to state, then
    `_reconstruct_classification` rehydrates a SymptomClassification
    that the path resolver consumes. The round-trip must keep enough
    information for the resolver to recover the canonical (nf, metric)
    pair — otherwise it falls back to (flag.component, flag.metric)
    which is the screener's `derived` / `normalized` namespace prefix
    and every flow scores zero.

    This is the bug found in run_20260509_135004_call_quality_degradation:
    classifier returned `transport_layer` correctly, but the resolver
    saw `{derived, normalized}` as load-bearing components after the
    round-trip and returned None — Phase 0.6 never ran the walker.

    The fix: `to_dict()` includes `kb_metric_id` per flag, and
    `_reconstruct_classification` rebuilds `flag.kb_context` from it.
    """
    import json

    from agentic_ops_v7.orchestrator import _reconstruct_classification

    classification = _classify_real([
        _flag("derived.rtpengine_loss_ratio",
              current=10.0, learned_normal=0.0, direction="spike", score=2.0),
        _flag("derived.upf_activity_during_calls",
              current=0.0, learned_normal=1.0, direction="drop", score=2.0),
        _flag("normalized.icscf.core:rcv_requests_register_per_ue",
              current=0.0, learned_normal=0.05, direction="drop", score=1.0),
        _flag("normalized.scscf.core:rcv_requests_register_per_ue",
              current=0.0, learned_normal=0.05, direction="drop", score=1.0),
    ])

    # Round-trip via JSON to mirror what the orchestrator's session-state
    # store does between Phase 0.5 and Phase 0.6.
    rehydrated = _reconstruct_classification(
        {"symptom_classification": json.loads(json.dumps(classification.to_dict()))}
    )
    assert rehydrated is not None

    # Resolver must still pick the right flow.
    resolved = resolve_path(rehydrated)
    assert resolved is not None, (
        "Resolver returned None after round-trip — `kb_metric_id` was "
        "almost certainly dropped during reconstruction, leaving the "
        "resolver with `derived` / `normalized` as the only NF names "
        "to score against (none of which match any flow)."
    )
    assert resolved.flow_id == "vonr_media", (
        f"Round-trip changed the resolver's pick. Pre-roundtrip went to "
        f"vonr_media; got {resolved.flow_id} after. "
        f"Candidates: {resolved.candidate_flows}"
    )

    # rtpengine must still be on the walk — that's what the walker
    # needs to probe to localize the qdisc fault.
    walked_nodes = {h.node for h in resolved.hops}
    assert "rtpengine" in walked_nodes, (
        f"rtpengine missing from walked hops after round-trip; "
        f"walked: {walked_nodes}"
    )


# ---------------------------------------------------------------------------
# F1.3 — Resolver regression tests for the 4 batch-broken cases.
#
# Per docs/work-plan-may-11.md ("Fix (1) — Implementation steps"), these
# four scenarios from the 2026-05-10 batch were mis-routed by the resolver
# (picking `data_pdu_session_user_traffic` instead of the implicated
# signaling / media flow). Each test loads the saved episode's
# symptom_classification, rehydrates it the way the orchestrator does,
# runs the real resolver, and asserts the right flow gets picked.
#
# These tests pin the F1 fix in place. If the resolver regresses on any
# of these scenarios, the test breaks loudly with which flow it picked
# instead.
# ---------------------------------------------------------------------------


import json
from pathlib import Path

from agentic_ops_common.anomaly.screener import FlagKBContext
from agentic_ops_v7.symptom_classifier import FlagBucket


def _rehydrate_classification(payload: dict) -> SymptomClassification:
    """Rehydrate a SymptomClassification from a saved episode's payload.

    Mirrors `agentic_ops_v7/orchestrator.py:_reconstruct_classification`
    — the round-trip the orchestrator runs in production. Critically
    preserves `flag.kb_context.kb_metric_id`, which is what
    `_flag_nf_metric` reads to recover the canonical (nf, metric) pair.
    """
    def _fb_list(key: str) -> list:
        out = []
        for f in payload.get(key, []) or []:
            kb_id = f.get("kb_metric_id")
            kb_context = (
                FlagKBContext(kb_metric_id=kb_id) if kb_id else None
            )
            flag = AnomalyFlag(
                metric=f.get("metric", ""),
                component=f.get("component", ""),
                current=f.get("current", 0.0),
                learned_normal=f.get("learned_normal", 0.0),
                anomaly_score=f.get("anomaly_score", 0.0),
                severity=f.get("severity", "LOW"),
                direction=f.get("direction", ""),
                kb_context=kb_context,
            )
            out.append(FlagBucket(
                flag=flag,
                bucket=f.get("bucket", "ambiguous"),
                reason=f.get("reason", ""),
            ))
        return out

    return SymptomClassification(
        label=payload["label"],
        rationale=payload.get("rationale", ""),
        transport_flags=_fb_list("transport_flags"),
        application_flags=_fb_list("application_flags"),
        ambiguous_flags=_fb_list("ambiguous_flags"),
    )


_REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_classification_from_episode(episode_rel_path: str) -> SymptomClassification:
    """Load symptom_classification from a saved chaos episode JSON."""
    episode_path = _REPO_ROOT / episode_rel_path
    data = json.loads(episode_path.read_text())
    payload = data["challenge_result"]["symptom_classification"]
    return _rehydrate_classification(payload)


# F1.3 — Resolver regression cases from the 2026-05-10 batch.
#
# Each tuple: (scenario_name, episode_relative_path, expected_flow_id,
#              xfail_reason_or_None).
#
# Three of the four "broken" batch cases are NOT fixable by resolver
# scoring alone — they're symptoms of B4 (screener over-flagging of UPF
# GTP metrics in registration-only state). When the screener emits two
# UPF GTP transport-bucket flags, both `data_pdu_session_user_traffic`
# and `vonr_media` get +10 from matching them in observable_metrics —
# the right signaling flow (`ims_registration`) has no UPF GTP in its
# observable_metrics and can't catch up. F1 cleans up the per-flag
# dedup and the bucket-affinity tie-break; the residual mis-routing
# is a screener-side problem.
_F1_BROKEN_CASES = [
    (
        "p_cscf_packet_loss",
        "agentic_ops_v7/docs/agent_logs/run_20260510_185152_p_cscf_packet_loss.json",
        "ims_registration",
        None,  # FIXED by F1 — only 1 UPF GTP transport flag, so the right
               # flow's 4-component overlap wins decisively.
    ),
    (
        "rtpengine_latency_injection",
        "agentic_ops_v7/docs/agent_logs/run_20260510_191148_rtpengine_latency_injection.json",
        "vonr_media",
        "Unfixable by F1 alone: rtpengine_loss_ratio was NOT flagged in "
        "this episode (the screener doesn't surface rtpengine signals "
        "under delay-only injection). With only over-flagged UPF GTP in "
        "the transport bucket, neither data_pdu nor vonr_media can be "
        "differentiated from each other on this resolver — both match "
        "the same UPF GTP observable_metrics. Needs B4 (screener over-"
        "flagging fix) or a rtpengine-specific delay feature.",
    ),
    (
        "p_cscf_latency",
        "agentic_ops_v7/docs/agent_logs/run_20260510_130115_p_cscf_latency.json",
        "ims_registration",
        "Unfixable by F1 alone: 2 UPF GTP transport flags give data_pdu "
        "and vonr_media +10 each via observable_metrics match. The right "
        "flow ims_registration has no UPF GTP in its observable_metrics "
        "and scores only on component overlap (8 with weight=2). "
        "Bumping component weight to 4+ would let ims_registration win "
        "BUT regresses the rtpengine-loss roundtrip test (vonr_call_teardown "
        "would then beat vonr_media on its CSCF component overlap). "
        "Needs B4 — when the screener stops over-flagging UPF GTP, the "
        "data_pdu transport boost goes away and ims_registration wins.",
    ),
    (
        "ims_network_partition",
        "agentic_ops_v7/docs/agent_logs/run_20260510_195908_ims_network_partition.json",
        "ims_registration",
        "Unfixable by F1 alone: same root cause as p_cscf_latency. 2 UPF "
        "GTP transport flags dominate; ims_registration scores only via "
        "component overlap and loses 8 vs 12.",
    ),
]


@pytest.mark.parametrize(
    "scenario,episode_path,expected_flow_id,xfail_reason",
    _F1_BROKEN_CASES,
    ids=[t[0] for t in _F1_BROKEN_CASES],
)
def test_f1_resolver_picks_right_flow_for_broken_batch_case(
    scenario: str, episode_path: str,
    expected_flow_id: str, xfail_reason,
    request,
):
    """F1 regression: after the resolver scoring + tie-break rework,
    each batch-broken case must route to its implicated flow rather
    than to `data_pdu_session_user_traffic`.

    The cases marked `xfail_reason` are documented as not-fixable by
    F1 alone (the resolver-scoring layer). Their xfail status flips
    to `xpassed` (which pytest reports loudly) once the underlying
    screener issue (B4) is fixed and the resolver can finally do its
    job — at which point remove the xfail mark.

    Running this test against the saved batch's symptom_classification
    is the operational answer to "would re-running the chaos batch
    produce a different resolver pick now that F1 has landed?"
    """
    if xfail_reason is not None:
        request.applymarker(pytest.mark.xfail(reason=xfail_reason, strict=True))

    classification = _load_classification_from_episode(episode_path)
    resolved = resolve_path(classification)

    assert resolved is not None, (
        f"{scenario}: resolver returned None — no flow scored above zero. "
        f"Investigate the load_bearing_components / metrics_by_bucket."
    )
    assert resolved.flow_id == expected_flow_id, (
        f"{scenario}: resolver picked `{resolved.flow_id}` instead of "
        f"`{expected_flow_id}`.\n"
        f"Candidates considered:\n"
        + "\n".join(
            f"  {fid}: {score}" for fid, score in resolved.candidate_flows[:5]
        )
        + f"\n\nF1 broke or hasn't landed yet. See "
        f"docs/work-plan-may-11.md → 'Fix (1) — Implementation steps'."
    )


# ---------------------------------------------------------------------------
# F1.5 — Regression tests for currently-passing scenarios.
#
# F1's scoring change could in principle regress the scenarios that
# CURRENTLY pass at 100%. The load-bearing regressions are the
# walker-localized cases — if F1 changes which flow the resolver
# picks, the walker walks the wrong flow and won't localize the fault.
#
# The null-localized cases (gnb_radio, amf_restart, cascading_ims_failure)
# get their 100% from the app-layer fall-through. Their resolver pick is
# operationally irrelevant; F1 is allowed to change it.
# ---------------------------------------------------------------------------


_F1_PASSING_LOCALIZED_CASES = [
    (
        "data_plane_degradation",
        "agentic_ops_v7/docs/agent_logs/run_20260510_183452_data_plane_degradation.json",
        "vonr_media",
    ),
    (
        "call_quality_degradation",
        "agentic_ops_v7/docs/agent_logs/run_20260510_190041_call_quality_degradation.json",
        "vonr_media",
    ),
    (
        "upf_bandwidth_cap",
        "agentic_ops_v7/docs/agent_logs/run_20260510_192948_upf_bandwidth_cap.json",
        "data_pdu_session_user_traffic",
    ),
]


@pytest.mark.parametrize(
    "scenario,episode_path,expected_flow_id",
    _F1_PASSING_LOCALIZED_CASES,
    ids=[t[0] for t in _F1_PASSING_LOCALIZED_CASES],
)
def test_f1_does_not_regress_currently_passing_localized_scenario(
    scenario: str, episode_path: str, expected_flow_id: str,
):
    """F1 regression: the walker-localized scenarios that scored 100% in
    the 2026-05-10 batch MUST keep their resolver pick. If F1 changes
    the chosen flow for one of these, the walker walks the wrong flow
    on the next run and the localization fails — i.e., the score drops.

    The 3 cases here are the scenarios where Phase 0.6's walker
    actually attributed a hop (`is_localized = True`). Their resolver
    pick is load-bearing for that attribution. The other 4 currently-
    passing scenarios (s_cscf_crash, gnb_radio, amf_restart,
    cascading_ims_failure) null-localized either by skipping Phase 0.6
    entirely or by falling through to the app-layer pipeline; F1 may
    change their resolver pick without affecting the score.
    """
    classification = _load_classification_from_episode(episode_path)
    resolved = resolve_path(classification)

    assert resolved is not None, (
        f"{scenario}: resolver returned None for a previously-passing "
        f"localized scenario — F1 has regressed."
    )
    assert resolved.flow_id == expected_flow_id, (
        f"{scenario}: F1 changed resolver pick from `{expected_flow_id}` "
        f"to `{resolved.flow_id}` — the walker won't reach the hop "
        f"where the fault is, and the 100% score for this scenario "
        f"will drop on the next batch run.\n"
        f"Candidates considered:\n"
        + "\n".join(
            f"  {fid}: {score}" for fid, score in resolved.candidate_flows[:5]
        )
    )
