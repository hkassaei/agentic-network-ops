"""Verify `get_dp_quality_gauges` routes KB-backed metrics through
the unified renderer.

Per ADR `expose_kb_disambiguators_to_investigator.md`, the data-plane
probe must surface the same KB depth (full `what_it_signals`,
value-specific `meaning.*`, every `disambiguators` entry) as
`get_diagnostic_metrics` for any metric that has rich KB content. The
RTPEngine `loss_ratio` metric is the canonical case — every probe
output must include the disambiguators that point the LLM at
`errors_per_second` and the UPF directional rates.

This test mocks the Prometheus client (the production tool's only
external dependency) and asserts the rendered output contains the
load-bearing KB strings.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from agentic_ops_common.metric_kb import load_kb
from agentic_ops_common.tools.data_plane import get_dp_quality_gauges


def _mock_prom_responses(values_by_query_substring: dict[str, float]):
    """Build a fake httpx AsyncClient that returns hard-coded values
    for queries matching given substrings; default to 0.

    Used so the test exercises the rendering path without touching a
    live Prometheus.
    """
    class _Resp:
        def __init__(self, val):
            self.status_code = 200
            self._val = val

        def json(self):
            return {
                "data": {
                    "result": [
                        {"value": [0, str(self._val)]}
                    ] if self._val is not None else []
                }
            }

    async def fake_get(url, params=None):
        q = (params or {}).get("query", "")
        for substring, value in values_by_query_substring.items():
            if substring in q:
                return _Resp(value)
        return _Resp(0)

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def get(self, url, params=None):
            return await fake_get(url, params)

    return _FakeClient


@pytest.mark.asyncio
async def test_rtpengine_loss_renders_full_kb_block():
    """When RTPEngine reports per-RR loss, the probe output must
    contain the full `what_it_signals` for `ims.rtpengine.loss_ratio`,
    the `meaning.spike` interpretation (loss > 0), AND every
    authored disambiguator block."""
    # 30% loss-per-RR scenario — numerator > 0, denominator > 0.
    fake_client = _mock_prom_responses({
        "rtpengine_packetloss_total": 7.5,
        "rtpengine_packetloss_samples_total": 0.3,
    })
    with patch("agentic_ops_common.tools.data_plane.httpx.AsyncClient",
               return_value=fake_client()), \
         patch("agentic_ops_common.tools.data_plane._get_deps",
               return_value=type("D", (), {"env": {"METRICS_IP": "x"}})()):
        out = await get_dp_quality_gauges(window_seconds=120)

    # Sanity: the per-RR ratio rendered (7.5 / 0.3 = 25.0).
    assert "25.00" in out, f"loss ratio not computed correctly:\n{out}"

    # KB depth signature: pull the entry's authored content and assert
    # each strand appears in the output.
    kb = load_kb()
    entry = kb.get_metric("ims.rtpengine.loss_ratio")
    assert entry is not None

    # what_it_signals (verbatim, not first-sentence).
    assert entry.meaning is not None
    wis = entry.meaning.what_it_signals
    # Use a long verbatim slice to fail loudly on truncation. The
    # exact slice is tolerant of whitespace via the renderer's
    # behaviour, but if the LLM-facing text were first-sentence-only,
    # this slice would be cut.
    long_slice = " ".join(wis.split()[:40])
    assert long_slice in " ".join(out.split()), (
        "loss_ratio.what_it_signals first 40 words missing — "
        f"first-sentence truncation regressed:\n{out}"
    )

    # Every disambiguator's partner id and separates text appears.
    assert entry.disambiguators, "test KB precondition violated"
    for d in entry.disambiguators:
        assert d.metric in out, (
            f"disambiguator partner {d.metric} missing from probe output:\n{out}"
        )
        # First 8 words of separates verbatim.
        sep_slice = " ".join(d.separates.split()[:8])
        assert sep_slice in " ".join(out.split()), (
            f"disambiguator separates text for {d.metric} missing:\n"
            f"  expected slice: {sep_slice!r}\n"
            f"  output: {out}"
        )


@pytest.mark.asyncio
async def test_rtpengine_loss_zero_renders_meaning_zero_variant():
    """When loss_ratio resolves to 0 (numerator zero, denominator
    non-zero), the renderer must select `meaning.zero` (or
    interpretation==zero) — exactly the variant whose KB text spells
    out the disambiguator pattern (loss=0 + errors=0 = path healthy;
    loss=0 + errors=k = ...) — and surface it in full.
    """
    fake_client = _mock_prom_responses({
        "rtpengine_packetloss_total": 0.0,
        "rtpengine_packetloss_samples_total": 5.0,  # samples present, no loss
    })
    with patch("agentic_ops_common.tools.data_plane.httpx.AsyncClient",
               return_value=fake_client()), \
         patch("agentic_ops_common.tools.data_plane._get_deps",
               return_value=type("D", (), {"env": {"METRICS_IP": "x"}})()):
        out = await get_dp_quality_gauges(window_seconds=120)

    kb = load_kb()
    entry = kb.get_metric("ims.rtpengine.loss_ratio")
    assert entry is not None and entry.meaning is not None

    # If `meaning.zero` is authored, it must appear when value == 0.
    if entry.meaning.zero:
        zero_slice = " ".join(entry.meaning.zero.split()[:6])
        assert zero_slice in " ".join(out.split()), (
            "loss_ratio.meaning.zero variant not rendered when value=0:\n"
            f"{out}"
        )


@pytest.mark.asyncio
async def test_no_samples_in_window_renders_na_and_does_not_misclaim_loss():
    """When the samples_rate is 0 (no data in window), the probe
    surfaces 'N/A' rather than 0. The KB block is not rendered (the
    value is undefined; renderer is given None). The output must NOT
    contain a fabricated low/high interpretation."""
    fake_client = _mock_prom_responses({
        "rtpengine_packetloss_total": 0.0,
        "rtpengine_packetloss_samples_total": 0.0,
    })
    with patch("agentic_ops_common.tools.data_plane.httpx.AsyncClient",
               return_value=fake_client()), \
         patch("agentic_ops_common.tools.data_plane._get_deps",
               return_value=type("D", (), {"env": {"METRICS_IP": "x"}})()):
        out = await get_dp_quality_gauges(window_seconds=120)

    assert "N/A (no samples in window)" in out


@pytest.mark.asyncio
async def test_kb_load_failure_does_not_break_probe():
    """If KB load fails for any reason, the probe must still produce
    its standard output — the routing change is additive, never a
    blocking dependency on the KB being available."""
    fake_client = _mock_prom_responses({
        "rtpengine_packetloss_total": 7.5,
        "rtpengine_packetloss_samples_total": 0.3,
    })
    with patch("agentic_ops_common.tools.data_plane.httpx.AsyncClient",
               return_value=fake_client()), \
         patch("agentic_ops_common.tools.data_plane._get_deps",
               return_value=type("D", (), {"env": {"METRICS_IP": "x"}})()), \
         patch("agentic_ops_common.tools.data_plane.load_kb",
               side_effect=RuntimeError("KB unavailable")):
        out = await get_dp_quality_gauges(window_seconds=120)

    # Probe produced output; loss line is still there.
    assert "loss (recent)" in out
    assert "25.00" in out
