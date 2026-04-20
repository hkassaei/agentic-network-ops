"""Integration test for chaos framework ↔ metric KB trigger evaluator.

Simulates a scenario: baseline + observation snapshots showing a RAN drop,
passes them through the chaos-side integration helper, verifies the right
events land in the SQLite event store with correct episode_id scoping.
"""

import time
from pathlib import Path

import pytest

from agentic_chaos.trigger_evaluator_integration import (
    _map_preprocessor_key_to_kb,
    evaluate_episode_events,
)


# ============================================================================
# Key-mapping unit tests
# ============================================================================

def test_mapping_plain_nf_metric():
    assert _map_preprocessor_key_to_kb("amf.ran_ue") == "core.amf.ran_ue"
    assert _map_preprocessor_key_to_kb("amf.gnb") == "core.amf.gnb"


def test_mapping_normalized_per_ue():
    assert _map_preprocessor_key_to_kb(
        "normalized.pcscf.dialogs_per_ue"
    ) == "ims.pcscf.dialogs_per_ue"
    assert _map_preprocessor_key_to_kb(
        "normalized.upf.gtp_indatapktn3upf_per_ue"
    ) == "core.upf.gtp_indatapktn3upf_per_ue"


def test_mapping_normalized_strips_core_prefix():
    assert _map_preprocessor_key_to_kb(
        "normalized.pcscf.core:rcv_requests_register_per_ue"
    ) == "ims.pcscf.rcv_requests_register_per_ue"


def test_mapping_derived_per_nf():
    assert _map_preprocessor_key_to_kb(
        "derived.pcscf_avg_register_time_ms"
    ) == "ims.pcscf.avg_register_time_ms"
    assert _map_preprocessor_key_to_kb(
        "derived.icscf_uar_timeout_ratio"
    ) == "ims.icscf.uar_timeout_ratio"


def test_mapping_derived_upf_activity():
    assert _map_preprocessor_key_to_kb(
        "derived.upf_activity_during_calls"
    ) == "core.upf.activity_during_calls"


def test_mapping_kamailio_group_metric_cdp_avg():
    assert _map_preprocessor_key_to_kb(
        "icscf.cdp:average_response_time"
    ) == "ims.icscf.cdp_avg_response_time"


def test_mapping_kamailio_group_metric_ims_response_time():
    assert _map_preprocessor_key_to_kb(
        "icscf.ims_icscf:uar_avg_response_time"
    ) == "ims.icscf.uar_avg_response_time"
    assert _map_preprocessor_key_to_kb(
        "scscf.ims_auth:mar_avg_response_time"
    ) == "ims.scscf.mar_avg_response_time"


def test_mapping_rtpengine_errors():
    assert _map_preprocessor_key_to_kb(
        "rtpengine.errors_per_second_(total)"
    ) == "ims.rtpengine.errors_per_second"


def test_mapping_returns_none_for_unknown_nf():
    assert _map_preprocessor_key_to_kb("fakenf.some_metric") is None
    assert _map_preprocessor_key_to_kb("normalized.fakenf.x") is None


# ============================================================================
# End-to-end integration: synthetic chaos snapshots → events in store
# ============================================================================

def _make_metric_snapshot(timestamp: float, **component_metrics) -> dict:
    """Build a chaos-format metric snapshot.

    component_metrics: {component_name: {metric_key: value, ...}, ...}
    Returns: {component_name: {"metrics": {...}, "badge": None, "source": "test"},
              "_timestamp": ts}
    """
    snapshot = {
        "_timestamp": timestamp,
    }
    for comp, metrics in component_metrics.items():
        snapshot[comp] = {
            "metrics": metrics,
            "badge": None,
            "source": "test",
        }
    return snapshot


def test_full_integration_ran_loss(tmp_path: Path):
    """Simulate a gNB kill: baseline shows healthy RAN, observation shows ran_ue=0."""
    now = time.time()
    baseline = _make_metric_snapshot(
        timestamp=now - 400,
        amf={"ran_ue": 2.0, "gnb": 1.0, "amf_session": 4.0},
        smf={"fivegs_smffunction_sm_sessionnbr": 4.0, "bearers_active": 4.0,
             "ues_active": 2.0},
        pcscf={"ims_usrloc_pcscf:registered_contacts": 2.0,
               "dialog_ng:active": 0.0},
        upf={"fivegs_upffunction_upf_sessionnbr": 4.0,
             "fivegs_ep_n3_gtp_indatapktn3upf": 1000.0,
             "fivegs_ep_n3_gtp_outdatapktn3upf": 1000.0},
    )

    # A stable pre-fault buildup
    observation_snapshots = []
    for i in range(5):
        observation_snapshots.append(_make_metric_snapshot(
            timestamp=now - 200 + i * 10,
            amf={"ran_ue": 2.0, "gnb": 1.0, "amf_session": 4.0},
            smf={"fivegs_smffunction_sm_sessionnbr": 4.0, "bearers_active": 4.0,
                 "ues_active": 2.0},
            pcscf={"ims_usrloc_pcscf:registered_contacts": 2.0,
                   "dialog_ng:active": 0.0},
            upf={"fivegs_upffunction_upf_sessionnbr": 4.0,
                 "fivegs_ep_n3_gtp_indatapktn3upf": 1000.0 + i * 100,
                 "fivegs_ep_n3_gtp_outdatapktn3upf": 1000.0 + i * 100},
        ))
    # Then RAN collapse
    for i in range(5):
        observation_snapshots.append(_make_metric_snapshot(
            timestamp=now - 140 + i * 10,
            amf={"ran_ue": 0.0, "gnb": 0.0, "amf_session": 0.0},
            smf={"fivegs_smffunction_sm_sessionnbr": 0.0, "bearers_active": 0.0,
                 "ues_active": 0.0},
            pcscf={"ims_usrloc_pcscf:registered_contacts": 2.0,  # pcscf cache
                   "dialog_ng:active": 0.0},
            upf={"fivegs_upffunction_upf_sessionnbr": 0.0,
                 "fivegs_ep_n3_gtp_indatapktn3upf": 1500.0,  # frozen
                 "fivegs_ep_n3_gtp_outdatapktn3upf": 1500.0},
        ))

    fired = evaluate_episode_events(
        episode_id="ep_ran_test",
        observation_snapshots=observation_snapshots,
        baseline_snapshot=baseline,
        event_store_path=tmp_path / "events.db",
    )
    fired_types = {e.event_type for e in fired}

    # We expect the RAN-related events to fire
    assert "core.amf.ran_ue_full_loss" in fired_types, f"got: {fired_types}"
    assert "core.amf.gnb_association_drop" in fired_types, f"got: {fired_types}"


def test_integration_noop_on_empty_snapshots(tmp_path: Path):
    """No snapshots → no events fired, no crash."""
    fired = evaluate_episode_events(
        episode_id="ep_empty",
        observation_snapshots=[],
        baseline_snapshot=None,
        event_store_path=tmp_path / "events.db",
    )
    assert fired == []


def test_integration_episode_id_scoping(tmp_path: Path):
    """Running two episodes keeps their events separate."""
    now = time.time()
    store_path = tmp_path / "events.db"

    def collapsed_snapshots():
        snaps = []
        for i in range(5):
            snaps.append(_make_metric_snapshot(
                timestamp=now - 50 + i * 10,
                amf={"ran_ue": 2.0, "gnb": 1.0, "amf_session": 4.0},
            ))
        for i in range(5):
            snaps.append(_make_metric_snapshot(
                timestamp=now + i * 10,
                amf={"ran_ue": 0.0, "gnb": 0.0, "amf_session": 0.0},
            ))
        return snaps

    evaluate_episode_events(
        episode_id="ep_A",
        observation_snapshots=collapsed_snapshots(),
        event_store_path=store_path,
    )
    evaluate_episode_events(
        episode_id="ep_B",
        observation_snapshots=collapsed_snapshots(),
        event_store_path=store_path,
    )

    # Both episodes should have had events; they should be scoped separately
    from agentic_ops_common.metric_kb import EventStore
    s = EventStore(store_path)
    try:
        a_events = s.get_events(episode_id="ep_A")
        b_events = s.get_events(episode_id="ep_B")
    finally:
        s.close()

    assert len(a_events) > 0
    assert len(b_events) > 0
    assert all(e.episode_id == "ep_A" for e in a_events)
    assert all(e.episode_id == "ep_B" for e in b_events)
