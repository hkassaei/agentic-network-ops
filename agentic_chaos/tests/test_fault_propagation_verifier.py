"""Tests for FaultPropagationVerifier — `propagation_window_seconds` field
and the helper that computes time-since-first-fault from `faults_injected`.

The verifier's pre-fix output rendered `wait_seconds: 0, elapsed_seconds: 0.0`
in the episode markdown whenever the ObservationTrafficAgent had already
driven traffic (the normal app-layer path), making it look like the
verifier skipped its job. The fix surfaces the real time-since-fault
window so an operator can see "the fault has been propagating for 144s,
during which the traffic agent generated traffic, and here's what we saw"
rather than the misleading 0s/0s pair.

Regression target: run_20260513_153832_cascading_ims_failure where the
verifier reported `wait_seconds=0, elapsed_seconds=0.0, raw_delta_node_count=1`
even though ~144s had elapsed since fault injection.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from agentic_chaos.agents.fault_propagation_verifier import (
    _propagation_window_since_first_fault,
)


# ---------------------------------------------------------------------------
# _propagation_window_since_first_fault
# ---------------------------------------------------------------------------


_NOW = datetime(2026, 5, 13, 15, 35, 26, tzinfo=timezone.utc)


def _fault(injected_at: str, *, success: bool = True) -> dict:
    return {
        "fault_type": "container_kill",
        "target": "pyhss",
        "injected_at": injected_at,
        "success": success,
    }


def test_window_uses_earliest_successful_fault():
    """Two faults, both successful — window is from the earlier one."""
    state = {
        "faults_injected": [
            _fault("2026-05-13T15:33:00.874552+00:00"),
            _fault("2026-05-13T15:33:02.492255+00:00"),
        ],
    }
    window = _propagation_window_since_first_fault(state, until=_NOW)
    assert window is not None
    # From 15:33:00.874552 to 15:35:26.000000 = ~145.13 seconds
    assert 145.0 < window < 145.2


def test_window_ignores_failed_faults():
    """A failed fault's timestamp should not anchor the window."""
    state = {
        "faults_injected": [
            _fault("2026-05-13T15:30:00+00:00", success=False),
            _fault("2026-05-13T15:33:00+00:00", success=True),
        ],
    }
    window = _propagation_window_since_first_fault(state, until=_NOW)
    assert window is not None
    # From 15:33:00 to 15:35:26 = 146 seconds
    assert 145.9 < window < 146.1


def test_window_none_when_no_faults_injected():
    """No faults in state → None (defensive; should not happen in normal flow)."""
    assert _propagation_window_since_first_fault({}, until=_NOW) is None
    assert _propagation_window_since_first_fault(
        {"faults_injected": []}, until=_NOW
    ) is None


def test_window_none_when_all_faults_failed():
    """Every fault failed → no anchor → None."""
    state = {
        "faults_injected": [
            _fault("2026-05-13T15:33:00+00:00", success=False),
            _fault("2026-05-13T15:33:02+00:00", success=False),
        ],
    }
    assert _propagation_window_since_first_fault(state, until=_NOW) is None


def test_window_skips_unparseable_timestamps():
    """A fault with a garbage `injected_at` is skipped, not crashed."""
    state = {
        "faults_injected": [
            _fault("not-a-timestamp"),
            _fault("2026-05-13T15:33:00+00:00"),
        ],
    }
    window = _propagation_window_since_first_fault(state, until=_NOW)
    assert window is not None
    assert 145.9 < window < 146.1


def test_window_skips_missing_timestamp_field():
    """A fault dict without `injected_at` is skipped."""
    state = {
        "faults_injected": [
            {"fault_type": "container_kill", "target": "pyhss", "success": True},
            _fault("2026-05-13T15:33:00+00:00"),
        ],
    }
    window = _propagation_window_since_first_fault(state, until=_NOW)
    assert window is not None
    assert 145.9 < window < 146.1


def test_window_tolerates_trailing_z_zulu_format():
    """`...Z` suffix (some serializers emit this) should parse cleanly."""
    state = {
        "faults_injected": [
            _fault("2026-05-13T15:33:00.000000Z"),
        ],
    }
    window = _propagation_window_since_first_fault(state, until=_NOW)
    assert window is not None
    assert 145.9 < window < 146.1


def test_window_handles_naive_timestamps_as_utc():
    """A timestamp without timezone info is treated as UTC (best-effort)."""
    state = {
        "faults_injected": [_fault("2026-05-13T15:33:00")],
    }
    window = _propagation_window_since_first_fault(state, until=_NOW)
    assert window is not None
    assert 145.9 < window < 146.1


def test_window_returns_none_for_malformed_state():
    """Non-list `faults_injected` returns None instead of crashing."""
    assert _propagation_window_since_first_fault(
        {"faults_injected": "oops not a list"}, until=_NOW
    ) is None
    assert _propagation_window_since_first_fault(
        {"faults_injected": None}, until=_NOW
    ) is None


def test_window_negative_when_until_precedes_injection():
    """Defensive: clock-skew or test data with `until` before the fault.

    The function doesn't clamp — it returns the signed difference. Caller
    is responsible for sanity-checking. We just verify no crash.
    """
    state = {
        "faults_injected": [_fault("2026-05-13T15:33:00+00:00")],
    }
    earlier = _NOW - timedelta(hours=1)
    window = _propagation_window_since_first_fault(state, until=earlier)
    assert window is not None
    assert window < 0  # ~-3600
