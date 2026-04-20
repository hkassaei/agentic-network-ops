"""Tests for the SQLite event store."""

from pathlib import Path

import pytest

from agentic_ops_common.metric_kb.event_store import EventStore, FiredEvent


@pytest.fixture
def store(tmp_path: Path) -> EventStore:
    s = EventStore(tmp_path / "events.db")
    yield s
    s.close()


def test_insert_and_retrieve(store: EventStore):
    event = FiredEvent(
        event_type="core.amf.ran_ue_sudden_drop",
        source_metric="core.amf.ran_ue",
        source_nf="amf",
        timestamp=1000.0,
        magnitude_payload={"current": 0, "prior": 10},
        episode_id="ep_001",
    )
    event_id = store.insert(event)
    assert event_id is not None
    assert event.id == event_id

    events = store.get_events(episode_id="ep_001")
    assert len(events) == 1
    assert events[0].event_type == "core.amf.ran_ue_sudden_drop"
    assert events[0].magnitude_payload == {"current": 0, "prior": 10}


def test_filter_by_event_type(store: EventStore):
    store.insert(FiredEvent("core.amf.ran_ue_drop", "core.amf.ran_ue", "amf", 1000.0, episode_id="ep_001"))
    store.insert(FiredEvent("ims.icscf.cdp_spike", "ims.icscf.cdp", "icscf", 1001.0, episode_id="ep_001"))
    events = store.get_events(episode_id="ep_001", event_type="ims.icscf.cdp_spike")
    assert len(events) == 1
    assert events[0].source_nf == "icscf"


def test_filter_by_time_window(store: EventStore):
    for i, t in enumerate([900, 950, 1000, 1050]):
        store.insert(FiredEvent(
            event_type=f"ev_{i}",
            source_metric="m",
            source_nf="nf",
            timestamp=float(t),
            episode_id="ep_001",
        ))
    events = store.get_events(episode_id="ep_001", since=950, until=1000)
    assert len(events) == 2
    assert {e.event_type for e in events} == {"ev_1", "ev_2"}


def test_filter_by_source_nf(store: EventStore):
    store.insert(FiredEvent("e1", "core.amf.ran_ue", "amf", 1000.0, episode_id="ep_001"))
    store.insert(FiredEvent("e2", "ims.icscf.cdp", "icscf", 1001.0, episode_id="ep_001"))
    events = store.get_events(episode_id="ep_001", source_nf="icscf")
    assert len(events) == 1
    assert events[0].source_metric == "ims.icscf.cdp"


def test_mark_cleared(store: EventStore):
    eid = store.insert(FiredEvent("e1", "m", "nf", 1000.0, episode_id="ep_001"))
    store.mark_cleared(eid, 1005.0)
    cleared = store.get_events(episode_id="ep_001")[0]
    assert cleared.cleared_at == 1005.0


def test_include_cleared_filter(store: EventStore):
    e1 = store.insert(FiredEvent("e1", "m", "nf", 1000.0, episode_id="ep_001"))
    store.insert(FiredEvent("e2", "m", "nf", 1001.0, episode_id="ep_001"))
    store.mark_cleared(e1, 1005.0)
    all_events = store.get_events(episode_id="ep_001", include_cleared=True)
    active_only = store.get_events(episode_id="ep_001", include_cleared=False)
    assert len(all_events) == 2
    assert len(active_only) == 1
    assert active_only[0].event_type == "e2"


def test_episode_id_scoping(store: EventStore):
    store.insert(FiredEvent("e1", "m", "nf", 1000.0, episode_id="ep_A"))
    store.insert(FiredEvent("e1", "m", "nf", 1001.0, episode_id="ep_B"))
    a = store.get_events(episode_id="ep_A")
    b = store.get_events(episode_id="ep_B")
    assert len(a) == 1 and a[0].timestamp == 1000.0
    assert len(b) == 1 and b[0].timestamp == 1001.0


def test_latest_event_of_type(store: EventStore):
    store.insert(FiredEvent("e1", "m", "nf", 1000.0, episode_id="ep_001"))
    store.insert(FiredEvent("e1", "m", "nf", 1005.0, episode_id="ep_001"))
    latest = store.latest_event_of_type("e1", episode_id="ep_001")
    assert latest.timestamp == 1005.0


def test_count_scoped(store: EventStore):
    for i in range(5):
        store.insert(FiredEvent(f"e{i}", "m", "nf", 1000.0 + i, episode_id="ep_001"))
    for i in range(2):
        store.insert(FiredEvent(f"e{i}", "m", "nf", 2000.0 + i, episode_id="ep_002"))
    assert store.count(episode_id="ep_001") == 5
    assert store.count(episode_id="ep_002") == 2
    assert store.count() == 7


def test_payload_roundtrip(store: EventStore):
    payload = {"delta_percent": -80.5, "components": ["a", "b"], "flag": True}
    store.insert(FiredEvent(
        event_type="e1", source_metric="m", source_nf="nf",
        timestamp=1000.0, magnitude_payload=payload, episode_id="ep_001",
    ))
    e = store.get_events(episode_id="ep_001")[0]
    assert e.magnitude_payload == payload
