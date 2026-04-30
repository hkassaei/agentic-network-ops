"""Tests for the time-aware mode of `get_dp_quality_gauges`.

Per ADR `dealing_with_temporality_3.md` Layer 2, the tool now accepts
an optional `at_time_ts` parameter. When provided, Prometheus queries
are evaluated at that Unix timestamp (`?time=` in the API), letting
investigators ask "what did this look like at the moment the screener
flagged the anomaly?" instead of "what does it look like now?".

These tests also cover the related Layer-1-motivated rendering fix:
when no samples landed in the window (denominator rate is zero), the
tool now displays `N/A (no samples in window)` instead of `0` — the
collision that caused the disproven-by-stale-data verdict in
`run_20260429_163802_call_quality_degradation`.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch, AsyncMock

import pytest

from agentic_ops_common.tools.data_plane import (
    _ratio_or_no_data,
    get_dp_quality_gauges,
)


# ============================================================================
# `_ratio_or_no_data` — the no-samples rendering primitive
# ============================================================================

def test_ratio_or_no_data_returns_explicit_message_when_denominator_zero():
    """The collision-fix: when there are no samples in the window, do
    NOT render the ratio as 0 — render an explicit no-data message so
    the agent can't conflate "no media in window" with "media flowing
    cleanly with zero loss"."""
    result = _ratio_or_no_data(numerator=0.0, denominator=0.0)
    assert result == "N/A (no samples in window)"


def test_ratio_or_no_data_returns_explicit_message_for_negative_denominator():
    """Defensive: a negative samples_rate (shouldn't ever happen but
    might if Prometheus returns weird data) is also no-data."""
    result = _ratio_or_no_data(numerator=5.0, denominator=-1.0)
    assert result == "N/A (no samples in window)"


def test_ratio_or_no_data_returns_actual_ratio_when_samples_present():
    """The happy path — denominator > 0 → render the ratio."""
    result = _ratio_or_no_data(numerator=12.0, denominator=4.0)
    assert result == "3.00"


def test_ratio_or_no_data_renders_sub_unit_loss_at_2_decimals():
    """Spot-check decimal formatting: the loss feature is typically
    fractional (e.g. 0.5 packets lost per RR)."""
    assert _ratio_or_no_data(0.5, 5.0) == "0.10"


# ============================================================================
# `get_dp_quality_gauges` — at_time_ts plumbing
# ============================================================================

@pytest.mark.asyncio
async def test_get_dp_quality_gauges_passes_time_to_prom_query():
    """When `at_time_ts` is provided, every PromQL query gets the
    `?time=` parameter so Prometheus evaluates rate() against the
    historical window ending at that timestamp."""
    captured_calls: list[dict[str, Any]] = []

    async def fake_get(url, params=None):
        captured_calls.append({"url": url, "params": dict(params or {})})

        class _Resp:
            status_code = 200

            def json(self):
                return {"data": {"result": []}}

        return _Resp()

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def get(self, url, params=None):
            return await fake_get(url, params)

    with patch("agentic_ops_common.tools.data_plane.httpx.AsyncClient",
               return_value=_FakeClient()), \
         patch("agentic_ops_common.tools.data_plane._get_deps",
               return_value=type("D", (), {"env": {"METRICS_IP": "test-ip"}})()):
        out = await get_dp_quality_gauges(
            window_seconds=60,
            at_time_ts=1_700_000_000.0,
        )

    # Every Prometheus query must have carried the time anchor.
    assert captured_calls, "no Prometheus calls were made"
    for call in captured_calls:
        assert call["params"].get("time") == 1_700_000_000.0, (
            f"Prometheus call missing or wrong `time` param: {call}"
        )

    # Header must surface the anchor so the agent sees what it asked.
    assert "anchored at ts=1700000000" in out


@pytest.mark.asyncio
async def test_get_dp_quality_gauges_omits_time_param_in_live_mode():
    """`at_time_ts=None` (the default) must NOT add the `time` param
    — Prometheus then defaults to "now". This preserves backward
    compatibility for every existing caller that didn't pass the
    param."""
    captured_calls: list[dict[str, Any]] = []

    async def fake_get(url, params=None):
        captured_calls.append({"url": url, "params": dict(params or {})})

        class _Resp:
            status_code = 200

            def json(self):
                return {"data": {"result": []}}

        return _Resp()

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def get(self, url, params=None):
            return await fake_get(url, params)

    with patch("agentic_ops_common.tools.data_plane.httpx.AsyncClient",
               return_value=_FakeClient()), \
         patch("agentic_ops_common.tools.data_plane._get_deps",
               return_value=type("D", (), {"env": {"METRICS_IP": "test-ip"}})()):
        out = await get_dp_quality_gauges(window_seconds=60)

    assert captured_calls
    for call in captured_calls:
        assert "time" not in call["params"], (
            f"live-mode call leaked a `time` param: {call}"
        )

    # Header reads as live-mode, no anchor.
    assert "last 60s" in out
    assert "anchored at" not in out


@pytest.mark.asyncio
async def test_no_samples_renders_n_a_for_loss_mos_jitter():
    """The Layer-1 collision fix: when Prometheus returns 0 for both
    numerator and denominator (no samples in window), the rendered
    output must say `N/A (no samples in window)` instead of `0`."""

    async def fake_get(url, params=None):
        # Return 0 for every query — simulates the "no traffic in
        # window" case. With `_safe_div` this would have rendered as
        # `0` for loss/MOS/jitter; with `_ratio_or_no_data` it
        # renders as N/A.
        class _Resp:
            status_code = 200

            def json(self):
                return {"data": {"result": [{"value": [0, "0"]}]}}

        return _Resp()

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def get(self, url, params=None):
            return await fake_get(url, params)

    with patch("agentic_ops_common.tools.data_plane.httpx.AsyncClient",
               return_value=_FakeClient()), \
         patch("agentic_ops_common.tools.data_plane._get_deps",
               return_value=type("D", (), {"env": {"METRICS_IP": "test-ip"}})()):
        out = await get_dp_quality_gauges(window_seconds=60)

    # Loss / MOS / jitter all show "N/A" instead of 0.
    assert "loss (recent)  : N/A (no samples in window)" in out
    assert "MOS (recent)   : N/A (no samples in window)" in out
    assert "jitter (recent): N/A (no samples in window)" in out
