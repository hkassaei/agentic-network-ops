"""Recorder header rendering — "First attributed hop: <node>[<iface>]".

Pre-fix regression: the header read `first_hop["hop"]["node"]` because
the recorder assumed a nested HopRecord shape; the orchestrator's
`_path_walk_report_to_dict` actually serializes
`first_attributed_hop` as a flat `{node, kind, iface}` dict. Every
real episode rendered "First attributed hop: `?[?]`" — see
run_20260514_193941_cascading_ims_failure.md line 192 and the
follow-up run_20260514_214319 line 192.

This test exercises BOTH ends of the contract by reading the actual
orchestrator serializer's output instead of hand-crafting a fixture —
so if the producer side ever changes shape, this test fails loudly
instead of the recorder silently rendering `?` again.
"""

from __future__ import annotations

from dataclasses import dataclass

from agentic_chaos.recorder import _generate_markdown_summary
from agentic_ops_common.path_walk import (
    ContainerDeadHop,
    Hop,
    HopRecord,
    LatencyAtHop,
    PathWalkReport,
)
from agentic_ops_v7.orchestrator import _path_walk_report_to_dict


def _make_episode(path_walk_report_dict: dict) -> dict:
    """Minimal episode dict that exercises `_format_transport_layer_route`."""
    return {
        "scenario": {"name": "Test", "category": "compound"},
        "baseline": {"stack_phase": "ready", "container_status": {}},
        "faults": [],
        "observations": [],
        "resolution": {},
        "rca_label": {},
        "challenge_result": {
            "anomaly_report": "",
            "fired_events": "",
            "correlation_analysis": "",
            "network_analysis": "",
            "investigation_instruction": "",
            "investigation": "",
            "evidence_validation": "",
            "symptom_classification": {
                "label": "mixed",
                "flag_counts": {"transport": 1, "application": 0, "ambiguous": 9},
            },
            "prioritized_paths": {"flow_id": "ims_registration", "hops": [], "candidate_flows": []},
            "path_walk_report": path_walk_report_dict,
            "diagnosis_report": None,  # exercise the deliberate-fall-through branch
        },
        "timestamp": "2026-05-15T00:00:00+00:00",
        "duration_seconds": 0.0,
        "episode_id": "ep_test_first_hop_header",
    }


def test_header_renders_real_node_and_iface_not_question_marks():
    """End-to-end pin: the orchestrator's actual serializer feeds the
    recorder, which must render the node + iface in the header. Catches
    any future shape drift on either side of the contract."""
    walk_report = PathWalkReport(
        flow_id="ims_registration",
        direction="both",
        window_seconds=5,
        anchor_ts=None,
        hops=[
            HopRecord(
                hop=Hop(node="pyhss", kind="container", iface="eth0"),
                attribution=ContainerDeadHop(status="exited"),
                prober="KernelHopProber",
            ),
        ],
    )
    # Use the ACTUAL producer-side serializer — no hand-crafted dict.
    pw_dict = _path_walk_report_to_dict(walk_report)
    md = _generate_markdown_summary(_make_episode(pw_dict), agent_version="v7")
    assert "**First attributed hop:** `pyhss[eth0]`" in md
    # Negative: no question-mark sentinel for the node or iface.
    assert "?[?]" not in md


def test_header_handles_latency_attribution():
    """Same contract for `latency_at_hop` — different attribution kind,
    same flat-dict serialization."""
    walk_report = PathWalkReport(
        flow_id="ims_registration",
        direction="both",
        window_seconds=5,
        anchor_ts=None,
        hops=[
            HopRecord(
                hop=Hop(node="scscf", kind="container", iface="eth0"),
                attribution=LatencyAtHop(
                    observed_delay_ms=2000.0,
                    counter_kind="qdisc_netem_delay",
                    evidence="qdisc netem delay 2s",
                ),
                prober="KernelHopProber",
            ),
        ],
    )
    pw_dict = _path_walk_report_to_dict(walk_report)
    md = _generate_markdown_summary(_make_episode(pw_dict), agent_version="v7")
    assert "**First attributed hop:** `scscf[eth0]`" in md


def test_target_marker_lands_on_the_right_walk_row():
    """🎯 marker placement uses the same flat-dict path as the header.
    The pre-fix bug suppressed every marker; this test pins both."""
    walk_report = PathWalkReport(
        flow_id="ims_registration",
        direction="both",
        window_seconds=5,
        anchor_ts=None,
        hops=[
            HopRecord(
                hop=Hop(node="upf", kind="container", iface="eth0"),
                attribution=__import__(
                    "agentic_ops_common.path_walk", fromlist=["CleanHop"],
                ).CleanHop(),
                prober="KernelHopProber",
            ),
            HopRecord(
                hop=Hop(node="pyhss", kind="container", iface="eth0"),
                attribution=ContainerDeadHop(status="exited"),
                prober="KernelHopProber",
            ),
        ],
    )
    pw_dict = _path_walk_report_to_dict(walk_report)
    md = _generate_markdown_summary(_make_episode(pw_dict), agent_version="v7")
    assert "🎯" in md  # marker DID get rendered (legacy bug suppressed it)
    # Marker should be on the pyhss row, not upf
    pyhss_row_idx = md.find("`pyhss`")
    upf_row_idx = md.find("`upf`")
    target_idx = md.find("🎯")
    assert pyhss_row_idx >= 0 and target_idx >= 0
    # The 🎯 appears just before the `pyhss` token in the table cell
    # `| {marker}\`pyhss\` |` — so target_idx should be near pyhss_row_idx
    # and AFTER upf_row_idx.
    assert target_idx < pyhss_row_idx
    assert target_idx > upf_row_idx


def test_prioritized_candidates_table_includes_primary_with_marker():
    """ADR path_prioritizer_walks_all_candidates.md: when the walker walks
    multiple candidate flows, the "Prioritized Candidates Walked In Parallel"
    table must list EVERY walked flow — including the primary, marked
    `← primary`. The earlier rendering excluded the primary, so the table
    header said "probed N flows" but listed only N-1 rows. This pins that
    all N appear in one place.
    """
    primary = PathWalkReport(
        flow_id="ims_registration",
        direction="both",
        window_seconds=5,
        anchor_ts=None,
        hops=[
            HopRecord(
                hop=Hop(node="pcscf", kind="container", iface="eth0"),
                attribution=LatencyAtHop(
                    counter_kind="qdisc_netem_delay", observed_delay_ms=2000.0,
                    evidence="qdisc netem delay 2s",
                ),
                prober="KernelHopProber",
            ),
        ],
    )
    # Two alternatives: one null-localized, one localized.
    alt_null = PathWalkReport(
        flow_id="data_pdu_session_user_traffic",
        direction="both", window_seconds=5, anchor_ts=None,
        hops=[
            HopRecord(
                hop=Hop(node="upf", kind="container", iface="eth0"),
                attribution=__import__(
                    "agentic_ops_common.path_walk", fromlist=["CleanHop"],
                ).CleanHop(),
                prober="KernelHopProber",
            ),
        ],
    )
    alt_localized = PathWalkReport(
        flow_id="vonr_call_setup",
        direction="both", window_seconds=5, anchor_ts=None,
        hops=[
            HopRecord(
                hop=Hop(node="pcscf", kind="container", iface="eth0"),
                attribution=LatencyAtHop(
                    counter_kind="qdisc_netem_delay", observed_delay_ms=2000.0,
                    evidence="qdisc netem delay 2s",
                ),
                prober="KernelHopProber",
            ),
        ],
    )

    episode = _make_episode(_path_walk_report_to_dict(primary))
    episode["challenge_result"]["path_walk_all_reports"] = {
        "ims_registration": _path_walk_report_to_dict(primary),
        "data_pdu_session_user_traffic": _path_walk_report_to_dict(alt_null),
        "vonr_call_setup": _path_walk_report_to_dict(alt_localized),
    }
    md = _generate_markdown_summary(episode, agent_version="v7")

    # The header advertises 3 walked flows.
    assert "probed 3 candidate flows" in md
    # All three flows appear in the section (primary included).
    section = md[md.find("### Prioritized Candidates"):]
    assert "`ims_registration` ← primary" in section
    assert "`data_pdu_session_user_traffic`" in section
    assert "`vonr_call_setup`" in section
    # The primary's row shows its localization, not a dash.
    assert "← primary | ✅ localized | `pcscf[eth0]`" in section
