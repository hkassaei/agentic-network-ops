"""Tests for the snapshot-replay infrastructure.

Per ADR `dealing_with_temporality_3.md` Layer 3, container-state tools
can answer time-anchored queries by consulting the chaos framework's
`observation_snapshots` instead of querying live state. These tests
cover the matching helpers (find closest, extract metric) and the
contextvar plumbing that makes snapshots reachable from inside tools
without a signature change.
"""

from __future__ import annotations

import pytest

from agentic_ops_common.tools.snapshot_replay import (
    extract_metric_from_snapshot,
    extract_nf_metrics,
    find_closest_snapshot,
    get_observation_snapshots,
    set_observation_snapshots,
)


def _snap(ts: float, **components) -> dict:
    """Build a snapshot in the shape `MetricsCollector.collect()` produces."""
    return {
        "_timestamp": ts,
        **{nf: {"metrics": dict(metrics)} for nf, metrics in components.items()},
    }


# ============================================================================
# `find_closest_snapshot` — picks the snapshot nearest the requested time
# ============================================================================

def test_find_closest_returns_exact_match_when_present():
    """Trivial case: requesting a timestamp that's exactly one of the
    snapshots' timestamps returns that snapshot."""
    snaps = [_snap(100.0), _snap(105.0), _snap(110.0)]
    found = find_closest_snapshot(snaps, at_time_ts=105.0)
    assert found is not None
    assert found["_timestamp"] == 105.0


def test_find_closest_picks_nearest_when_no_exact_match():
    """Off-grid requests pick the nearest. ts=103 is closer to ts=105
    (drift 2) than to ts=100 (drift 3)."""
    snaps = [_snap(100.0), _snap(105.0), _snap(110.0)]
    found = find_closest_snapshot(snaps, at_time_ts=103.0)
    assert found is not None
    assert found["_timestamp"] == 105.0


def test_find_closest_returns_none_when_outside_drift_tolerance():
    """The matching is bounded: if the closest snapshot is more than
    `max_drift_seconds` away, return None. Caller surfaces this as
    "no historical data near requested time" — does NOT silently
    return a stale snapshot dressed as the requested moment."""
    # Snapshots at 100, 105, 110. Request ts=200 — the closest is 110,
    # 90s away. Default drift tolerance is 5s, so this is None.
    snaps = [_snap(100.0), _snap(105.0), _snap(110.0)]
    found = find_closest_snapshot(snaps, at_time_ts=200.0)
    assert found is None


def test_find_closest_respects_custom_drift_tolerance():
    """The drift tolerance is configurable. With a wide enough
    tolerance, a far-away snapshot is acceptable."""
    snaps = [_snap(100.0)]
    # Default: 5s — 50s away is too far.
    assert find_closest_snapshot(snaps, at_time_ts=150.0) is None
    # Custom 100s tolerance — same query now matches.
    found = find_closest_snapshot(snaps, at_time_ts=150.0, max_drift_seconds=100.0)
    assert found is not None
    assert found["_timestamp"] == 100.0


def test_find_closest_returns_none_for_empty_snapshots():
    """No snapshots → no match. Caller falls back to live data or
    surfaces the gap; it does not call this with an expectation of
    a result."""
    assert find_closest_snapshot([], at_time_ts=100.0) is None


def test_find_closest_skips_snapshots_with_no_timestamp():
    """Defensive: snapshots without a usable `_timestamp` are skipped
    silently. Shouldn't happen with well-formed observation data,
    but we don't want a single bad snapshot to break matching."""
    snaps = [
        {"amf": {"metrics": {"ran_ue": 2}}},  # no _timestamp
        _snap(100.0, amf={"ran_ue": 2}),
    ]
    found = find_closest_snapshot(snaps, at_time_ts=100.0)
    assert found is not None
    assert found["_timestamp"] == 100.0


# ============================================================================
# `extract_metric_from_snapshot` — single value extraction
# ============================================================================

def test_extract_metric_returns_value_from_metrics_wrapper():
    """The default snapshot shape has the `{"metrics": {...}}` wrapper
    that `MetricsCollector.collect()` produces."""
    snap = _snap(100.0, pcscf={"httpclient:connfail": 696, "dialog_ng:active": 0})
    assert extract_metric_from_snapshot(snap, "pcscf", "httpclient:connfail") == 696.0


def test_extract_metric_returns_value_from_flat_dict():
    """The function also accepts the flat `{key: value}` shape used
    in some places (e.g. parse_nf_metrics_text output before the
    chaos framework wraps it)."""
    snap = {
        "_timestamp": 100.0,
        "pcscf": {"httpclient:connfail": 696},
    }
    assert extract_metric_from_snapshot(snap, "pcscf", "httpclient:connfail") == 696.0


def test_extract_metric_returns_none_for_missing_nf():
    snap = _snap(100.0, pcscf={"x": 1})
    assert extract_metric_from_snapshot(snap, "icscf", "x") is None


def test_extract_metric_returns_none_for_missing_metric():
    snap = _snap(100.0, pcscf={"x": 1})
    assert extract_metric_from_snapshot(snap, "pcscf", "y") is None


def test_extract_metric_filters_non_numeric_values():
    """Snapshot may include non-numeric strings (badge text). Don't
    return them as if they were numeric values."""
    snap = _snap(100.0, pcscf={"x": 1, "badge": "2 reg"})
    assert extract_metric_from_snapshot(snap, "pcscf", "badge") is None
    assert extract_metric_from_snapshot(snap, "pcscf", "x") == 1.0


def test_extract_metric_rejects_bool_as_non_numeric():
    """Defensive: Python bools are subclasses of int, but should not
    be treated as numeric metric values. (Most metric collectors don't
    emit bools, but if any did this would silently coerce.)"""
    snap = _snap(100.0, pcscf={"flag": True})
    assert extract_metric_from_snapshot(snap, "pcscf", "flag") is None


# ============================================================================
# `extract_nf_metrics` — bulk extraction for one NF
# ============================================================================

def test_extract_nf_metrics_returns_all_numeric_values():
    snap = _snap(100.0, pcscf={
        "httpclient:connfail": 696,
        "dialog_ng:active": 0,
        "ims_usrloc_pcscf:registered_contacts": 2,
    })
    metrics = extract_nf_metrics(snap, "pcscf")
    assert metrics == {
        "httpclient:connfail": 696.0,
        "dialog_ng:active": 0.0,
        "ims_usrloc_pcscf:registered_contacts": 2.0,
    }


def test_extract_nf_metrics_filters_underscore_keys_and_non_numeric():
    snap = _snap(100.0, pcscf={
        "x": 1,
        "_internal": 999,
        "badge": "2 reg",
    })
    metrics = extract_nf_metrics(snap, "pcscf")
    # Underscore keys filtered (preprocessor convention), badge filtered
    # because non-numeric.
    assert metrics == {"x": 1.0}


def test_extract_nf_metrics_returns_empty_for_missing_nf():
    snap = _snap(100.0, pcscf={"x": 1})
    assert extract_nf_metrics(snap, "missing") == {}


# ============================================================================
# Contextvar plumbing
# ============================================================================

def test_get_observation_snapshots_default_empty():
    """Calling `get_observation_snapshots()` from a context where
    nothing has been set returns an empty list — never None or
    raises. This is what makes tools safe to call without coupling
    to the v6 orchestrator."""
    # Note: context isolation between tests is per-pytest's contextvar
    # behavior. We don't reset here because the previous test may have
    # set it, which is fine — the assertion is "no surprise".
    snaps = get_observation_snapshots()
    assert isinstance(snaps, list)


def test_set_and_get_observation_snapshots_round_trip():
    """The contextvar carries snapshots from set to get within the
    same context. This is what the v6 orchestrator's `investigate()`
    uses to make snapshots reachable from inside tool calls."""
    sample = [_snap(100.0, pcscf={"x": 1})]
    set_observation_snapshots(sample)
    assert get_observation_snapshots() == sample


def test_set_observation_snapshots_with_none_clears_to_empty_list():
    """Passing None or an empty list leaves the contextvar at empty —
    the orchestrator may legitimately want to clear between unrelated
    investigations (or when no chaos framework has supplied them)."""
    set_observation_snapshots([_snap(100.0, pcscf={"x": 1})])
    set_observation_snapshots(None)
    assert get_observation_snapshots() == []


def test_set_observation_snapshots_isolates_via_list_copy():
    """The setter takes a snapshot-list copy; mutating the input list
    after `set_observation_snapshots()` should NOT mutate what
    subsequent `get_observation_snapshots()` calls return. Locking
    this in so callers can't accidentally introduce shared-state
    bugs by clearing/reusing their input list."""
    inputs = [_snap(100.0, pcscf={"x": 1})]
    set_observation_snapshots(inputs)
    inputs.clear()  # external mutation
    after = get_observation_snapshots()
    assert len(after) == 1
    assert after[0]["_timestamp"] == 100.0
