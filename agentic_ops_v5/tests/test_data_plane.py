"""Unit tests for get_dp_quality_gauges — mocked Prometheus, no Docker."""

import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from agentic_ops_v5.tools.data_plane import (
    _prom_query,
    _safe_div,
    get_dp_quality_gauges,
    _QUERIES,
)


# ------------------------------------------------------------------ #
# _safe_div
# ------------------------------------------------------------------ #

class TestSafeDiv:
    def test_normal_division(self):
        assert _safe_div(10.0, 3.0) == 3.33

    def test_zero_denominator_returns_zero(self):
        assert _safe_div(42.0, 0.0) == 0

    def test_negative_denominator_returns_zero(self):
        assert _safe_div(10.0, -1.0) == 0

    def test_both_zero(self):
        assert _safe_div(0.0, 0.0) == 0

    def test_rounds_to_two_decimals(self):
        assert _safe_div(1.0, 3.0) == 0.33


# ------------------------------------------------------------------ #
# _prom_query
# ------------------------------------------------------------------ #

class TestPromQuery:
    @pytest.mark.asyncio
    async def test_returns_float_on_success(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "status": "success",
            "data": {"result": [{"value": [1234567890, "42.5"]}]},
        }
        client = AsyncMock()
        client.get = AsyncMock(return_value=mock_resp)

        result = await _prom_query(client, "http://prom:9090", "up")
        assert result == 42.5

    @pytest.mark.asyncio
    async def test_returns_zero_on_empty_result(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "status": "success",
            "data": {"result": []},
        }
        client = AsyncMock()
        client.get = AsyncMock(return_value=mock_resp)

        result = await _prom_query(client, "http://prom:9090", "nonexistent")
        assert result == 0

    @pytest.mark.asyncio
    async def test_returns_zero_on_http_error(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        client = AsyncMock()
        client.get = AsyncMock(return_value=mock_resp)

        result = await _prom_query(client, "http://prom:9090", "up")
        assert result == 0

    @pytest.mark.asyncio
    async def test_returns_zero_on_exception(self):
        client = AsyncMock()
        client.get = AsyncMock(side_effect=Exception("connection refused"))

        result = await _prom_query(client, "http://prom:9090", "up")
        assert result == 0


# ------------------------------------------------------------------ #
# Query definitions
# ------------------------------------------------------------------ #

class TestQueryDefinitions:
    def test_has_14_queries(self):
        assert len(_QUERIES) == 14

    def test_all_rtp_queries_use_30s_window(self):
        for key, q in _QUERIES.items():
            if "rate(" in q:
                assert "[30s]" in q, f"{key} missing [30s] window: {q}"

    def test_rtp_queries_present(self):
        assert "rtp_pps" in _QUERIES
        assert "rtp_bytes_ps" in _QUERIES
        assert "rtp_sessions" in _QUERIES
        assert "rtp_mos_rate" in _QUERIES
        assert "rtp_mos_samples_rate" in _QUERIES
        assert "rtp_loss_rate" in _QUERIES
        assert "rtp_loss_samples_rate" in _QUERIES
        assert "rtp_jitter_rate" in _QUERIES
        assert "rtp_jitter_samples_rate" in _QUERIES

    def test_upf_queries_present(self):
        assert "upf_in_pps" in _QUERIES
        assert "upf_out_pps" in _QUERIES
        assert "upf_in_bps" in _QUERIES
        assert "upf_out_bps" in _QUERIES
        assert "upf_sessions" in _QUERIES

    def test_upf_volume_queries_filter_by_qfi1(self):
        assert 'qfi="1"' in _QUERIES["upf_in_bps"]
        assert 'qfi="1"' in _QUERIES["upf_out_bps"]


# ------------------------------------------------------------------ #
# get_dp_quality_gauges — full integration with mocked Prometheus
# ------------------------------------------------------------------ #

def _make_prom_response(value: float) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "status": "success",
        "data": {"result": [{"value": [1234567890, str(value)]}]},
    }
    return resp


class TestGetDpQualityGauges:
    """Tests for the full tool with mocked Prometheus responses."""

    # Simulates a healthy active call
    _HEALTHY_CALL = {
        "rtp_pps": 98.5,
        "rtp_bytes_ps": 8192.0,       # 8 KB/s
        "rtp_sessions": 1.0,
        "rtp_mos_rate": 4.3,           # sum rate
        "rtp_mos_samples_rate": 1.0,   # sample rate → MOS = 4.3
        "rtp_loss_rate": 0.0,
        "rtp_loss_samples_rate": 1.0,  # loss = 0
        "rtp_jitter_rate": 1.2,
        "rtp_jitter_samples_rate": 1.0,  # jitter = 1.2
        "upf_in_pps": 52.0,
        "upf_out_pps": 51.8,
        "upf_in_bps": 8192.0,
        "upf_out_bps": 8100.0,
        "upf_sessions": 4.0,
    }

    # Simulates 30% packet loss on UPF
    _DEGRADED_CALL = {
        "rtp_pps": 54.2,
        "rtp_bytes_ps": 4416.0,
        "rtp_sessions": 1.0,
        "rtp_mos_rate": 3.1,
        "rtp_mos_samples_rate": 1.0,   # MOS = 3.1
        "rtp_loss_rate": 28.4,
        "rtp_loss_samples_rate": 1.0,  # loss = 28.4
        "rtp_jitter_rate": 4.7,
        "rtp_jitter_samples_rate": 1.0,  # jitter = 4.7
        "upf_in_pps": 52.0,
        "upf_out_pps": 36.5,
        "upf_in_bps": 8400.0,
        "upf_out_bps": 5836.0,
        "upf_sessions": 4.0,
    }

    # No active call
    _IDLE = {k: 0.0 for k in _HEALTHY_CALL}
    _IDLE["upf_sessions"] = 4.0  # sessions exist but no media

    def _mock_get(self, scenario: dict):
        """Return a side_effect function that maps PromQL queries to values."""
        keys = list(_QUERIES.keys())
        queries = list(_QUERIES.values())

        async def mock_get(url, params=None):
            q = params.get("query", "") if params else ""
            for i, prom_q in enumerate(queries):
                if q == prom_q:
                    return _make_prom_response(scenario[keys[i]])
            return _make_prom_response(0)

        return mock_get

    @pytest.mark.asyncio
    async def test_healthy_call(self):
        with patch("agentic_ops_v5.tools.data_plane._get_deps") as mock_deps:
            mock_deps.return_value = MagicMock(env={"METRICS_IP": "172.22.0.36"})
            with patch("httpx.AsyncClient") as MockClient:
                instance = AsyncMock()
                instance.get = self._mock_get(self._HEALTHY_CALL)
                instance.__aenter__ = AsyncMock(return_value=instance)
                instance.__aexit__ = AsyncMock(return_value=False)
                MockClient.return_value = instance

                result = await get_dp_quality_gauges()

        assert "RTPEngine:" in result
        assert "UPF:" in result
        assert "98.5" in result          # rtp pps
        assert "8.0 KB/s" in result      # rtp throughput (8192/1024)
        assert "MOS (recent)   : 4.3" in result
        assert "loss (recent)  : 0" in result
        assert "active sessions: 1" in result
        assert "in  packets/sec: 52.0" in result
        assert "out packets/sec: 51.8" in result

    @pytest.mark.asyncio
    async def test_degraded_call_shows_asymmetry(self):
        with patch("agentic_ops_v5.tools.data_plane._get_deps") as mock_deps:
            mock_deps.return_value = MagicMock(env={"METRICS_IP": "172.22.0.36"})
            with patch("httpx.AsyncClient") as MockClient:
                instance = AsyncMock()
                instance.get = self._mock_get(self._DEGRADED_CALL)
                instance.__aenter__ = AsyncMock(return_value=instance)
                instance.__aexit__ = AsyncMock(return_value=False)
                MockClient.return_value = instance

                result = await get_dp_quality_gauges()

        assert "54.2" in result           # reduced rtp pps
        assert "MOS (recent)   : 3.1" in result   # degraded MOS
        assert "loss (recent)  : 28.4" in result   # high loss
        # UPF asymmetry: in > out
        assert "in  packets/sec: 52.0" in result
        assert "out packets/sec: 36.5" in result

    @pytest.mark.asyncio
    async def test_idle_returns_zeros(self):
        with patch("agentic_ops_v5.tools.data_plane._get_deps") as mock_deps:
            mock_deps.return_value = MagicMock(env={"METRICS_IP": "172.22.0.36"})
            with patch("httpx.AsyncClient") as MockClient:
                instance = AsyncMock()
                instance.get = self._mock_get(self._IDLE)
                instance.__aenter__ = AsyncMock(return_value=instance)
                instance.__aexit__ = AsyncMock(return_value=False)
                MockClient.return_value = instance

                result = await get_dp_quality_gauges()

        assert "packets/sec    : 0" in result
        assert "MOS (recent)   : 0" in result
        assert "active sessions: 0" in result
        assert "active sessions: 4" in result  # UPF sessions still exist

    @pytest.mark.asyncio
    async def test_prometheus_unreachable(self):
        with patch("agentic_ops_v5.tools.data_plane._get_deps") as mock_deps:
            mock_deps.return_value = MagicMock(env={"METRICS_IP": "172.22.0.36"})
            with patch("httpx.AsyncClient") as MockClient:
                instance = AsyncMock()
                instance.__aenter__ = AsyncMock(
                    side_effect=Exception("connection refused"))
                MockClient.return_value = instance

                result = await get_dp_quality_gauges()

        assert "Data plane gauge error" in result
        assert "172.22.0.36" in result

    @pytest.mark.asyncio
    async def test_output_format_structure(self):
        with patch("agentic_ops_v5.tools.data_plane._get_deps") as mock_deps:
            mock_deps.return_value = MagicMock(env={"METRICS_IP": "172.22.0.36"})
            with patch("httpx.AsyncClient") as MockClient:
                instance = AsyncMock()
                instance.get = self._mock_get(self._HEALTHY_CALL)
                instance.__aenter__ = AsyncMock(return_value=instance)
                instance.__aexit__ = AsyncMock(return_value=False)
                MockClient.return_value = instance

                result = await get_dp_quality_gauges()

        lines = result.strip().splitlines()
        assert lines[0].startswith("Data Plane Quality Gauges (last 30s):")
        # Check both sections present
        assert any("RTPEngine:" in l for l in lines)
        assert any("UPF:" in l for l in lines)
        # Check all gauge labels present
        labels = [
            "packets/sec", "throughput", "MOS (recent)",
            "loss (recent)", "jitter (recent)", "active sessions",
            "in  packets/sec", "out packets/sec",
            "in  throughput", "out throughput",
        ]
        for label in labels:
            assert any(label in l for l in lines), f"Missing label: {label}"
