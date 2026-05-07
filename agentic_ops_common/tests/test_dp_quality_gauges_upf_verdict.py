"""Verify `get_dp_quality_gauges` renders the
upf_counters_are_directional rule's verdict inline in the UPF block.

Per ADR `upf_directional_rates_in_dp_quality_gauges.md`. The probe
must:
  - Compute upf_in_pps / upf_out_pps from Prometheus rate() queries.
  - Pass both to the pure evaluator.
  - Render the asymmetry %, severity, verdict text, and the three
    correct_methods inline next to the UPF in/out values, so the
    LLM cannot reach a loss conclusion from the asymmetry without
    seeing the prohibition.
  - Be resilient to evaluator-import failure (probe still emits the
    raw values; verdict line says "rule unavailable").
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest


def _mock_prom_responses(values_by_query_substring: dict[str, float]):
    """Build a fake httpx AsyncClient that returns hard-coded values
    for queries matching given substrings; default to 0."""
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
async def test_upf_block_contains_rule_verdict_for_failing_scenario():
    """The canonical failing-scenario rate values: 8.9 in / 6.8 out =
    23.6% asymmetry. The verdict must appear inline in the UPF block,
    severity=informational, with the three correct_methods rendered."""
    from agentic_ops_common.tools.data_plane import get_dp_quality_gauges

    fake_client = _mock_prom_responses({
        "fivegs_ep_n3_gtp_indatapktn3upf": 8.9,
        "fivegs_ep_n3_gtp_outdatapktn3upf": 6.8,
    })
    with patch("agentic_ops_common.tools.data_plane.httpx.AsyncClient",
               return_value=fake_client()), \
         patch("agentic_ops_common.tools.data_plane._get_deps",
               return_value=type("D", (), {"env": {"METRICS_IP": "x"}})()):
        out = await get_dp_quality_gauges(window_seconds=120)

    # The values themselves still appear.
    assert "in  packets/sec: 8.9" in out
    assert "out packets/sec: 6.8" in out

    # The new verdict block.
    assert "asymmetry      : 23.6%" in out
    assert "rule verdict" in out
    assert "upf_counters_are_directional" in out
    assert "severity=informational" in out
    assert "window_kind=rate" in out

    # The verdict text explicitly forbids loss inference.
    assert "DO NOT" in out or "never" in out.lower()

    # All three correct_methods are rendered.
    assert "Same-direction rate comparison" in out
    assert "RTCP-based voice quality" in out
    assert "tc qdisc" in out


@pytest.mark.asyncio
async def test_upf_block_high_asymmetry_renders_high_temptation_severity():
    """Mock 12.0 in / 4.0 out = 66.7% asymmetry → high_temptation."""
    from agentic_ops_common.tools.data_plane import get_dp_quality_gauges

    fake_client = _mock_prom_responses({
        "fivegs_ep_n3_gtp_indatapktn3upf": 12.0,
        "fivegs_ep_n3_gtp_outdatapktn3upf": 4.0,
    })
    with patch("agentic_ops_common.tools.data_plane.httpx.AsyncClient",
               return_value=fake_client()), \
         patch("agentic_ops_common.tools.data_plane._get_deps",
               return_value=type("D", (), {"env": {"METRICS_IP": "x"}})()):
        out = await get_dp_quality_gauges(window_seconds=120)

    assert "asymmetry      : 66.7%" in out
    assert "severity=high_temptation" in out
    # The high-temptation verdict text is louder.
    assert "HIGH" in out


@pytest.mark.asyncio
async def test_upf_block_zero_zero_still_renders_verdict():
    """Both upf_in_pps and upf_out_pps zero — verdict still fires
    (always-on educational pattern, asymmetry=0%)."""
    from agentic_ops_common.tools.data_plane import get_dp_quality_gauges

    fake_client = _mock_prom_responses({
        "fivegs_ep_n3_gtp_indatapktn3upf": 0.0,
        "fivegs_ep_n3_gtp_outdatapktn3upf": 0.0,
    })
    with patch("agentic_ops_common.tools.data_plane.httpx.AsyncClient",
               return_value=fake_client()), \
         patch("agentic_ops_common.tools.data_plane._get_deps",
               return_value=type("D", (), {"env": {"METRICS_IP": "x"}})()):
        out = await get_dp_quality_gauges(window_seconds=120)

    assert "asymmetry      : 0.0%" in out
    assert "severity=informational" in out
    assert "upf_counters_are_directional" in out


@pytest.mark.asyncio
async def test_upf_block_evaluator_unavailable_renders_fallback_line():
    """If `network_ontology.rules` is somehow unimportable at runtime
    (broken install, partial deploy), the probe must keep producing
    the raw in/out values and surface a single-line note explaining
    the rule's verdict isn't available — never crash, never silently
    drop the upf section."""
    from agentic_ops_common.tools import data_plane

    fake_client = _mock_prom_responses({
        "fivegs_ep_n3_gtp_indatapktn3upf": 8.9,
        "fivegs_ep_n3_gtp_outdatapktn3upf": 6.8,
    })

    # Force the evaluator's import inside _render_upf_directional_verdict
    # to fail by removing the module from sys.modules and patching the
    # importer to raise.
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "network_ontology.rules":
            raise ImportError("simulated import failure")
        return real_import(name, *args, **kwargs)

    with patch("agentic_ops_common.tools.data_plane.httpx.AsyncClient",
               return_value=fake_client()), \
         patch("agentic_ops_common.tools.data_plane._get_deps",
               return_value=type("D", (), {"env": {"METRICS_IP": "x"}})()), \
         patch("builtins.__import__", side_effect=fake_import):
        out = await data_plane.get_dp_quality_gauges(window_seconds=120)

    # Probe still emits values.
    assert "in  packets/sec: 8.9" in out
    assert "out packets/sec: 6.8" in out
    # Fallback line surfaced.
    assert "unavailable" in out.lower()
    assert "upf_counters_are_directional" in out


@pytest.mark.asyncio
async def test_correct_methods_appear_in_a_numbered_list():
    """The three correct_methods must render in a numbered list so
    the LLM reads them as a discrete options menu, not as prose."""
    from agentic_ops_common.tools.data_plane import get_dp_quality_gauges

    fake_client = _mock_prom_responses({
        "fivegs_ep_n3_gtp_indatapktn3upf": 8.9,
        "fivegs_ep_n3_gtp_outdatapktn3upf": 6.8,
    })
    with patch("agentic_ops_common.tools.data_plane.httpx.AsyncClient",
               return_value=fake_client()), \
         patch("agentic_ops_common.tools.data_plane._get_deps",
               return_value=type("D", (), {"env": {"METRICS_IP": "x"}})()):
        out = await get_dp_quality_gauges(window_seconds=120)

    # Numbered prefixes 1., 2., 3. each appear at least once.
    for n in ("1. ", "2. ", "3. "):
        assert n in out, f"missing numbered method {n!r} in output:\n{out}"
