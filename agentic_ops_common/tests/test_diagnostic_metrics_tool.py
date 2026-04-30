"""Tests for `get_diagnostic_metrics` (Step 3: live mode).

The tool returns a curated, agent-facing per-NF view with two clearly-
labeled blocks: model features (auto-discovered from
EXPECTED_FEATURE_KEYS) and diagnostic supporting metrics (KB-tagged
agent_exposed=True). These tests cover the live-mode rendering path —
mocking out the snapshot collection and screener-load so the tests
are hermetic and fast.

Step 5 (time-aware mode) is tested separately when shipped.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from agentic_ops_common.tools.diagnostic_metrics import get_diagnostic_metrics


def _fake_snap_text(values_per_nf: dict[str, dict[str, float]]) -> str:
    """Render the same shape `parse_nf_metrics_text` would produce.

    `parse_nf_metrics_text` parses lines of the form:
        NF (via source):
          metric_key = value
    """
    lines: list[str] = []
    for nf, metrics in values_per_nf.items():
        lines.append(f"{nf.upper()} (via test):")
        for k, v in metrics.items():
            lines.append(f"  {k} = {v}")
    return "\n".join(lines)


def _baseline_snapshot() -> dict[str, dict[str, float]]:
    """A minimally-realistic IMS-registered snapshot. Constant counters
    (so rates compute as 0 over a 5s delta) keep the test focused on
    rendering rather than rate semantics."""
    return {
        "amf": {"ran_ue": 2, "gnb": 1, "amf_session": 4},
        "smf": {"fivegs_smffunction_sm_sessionnbr": 4, "bearers_active": 4},
        "upf": {
            "fivegs_upffunction_upf_sessionnbr": 4,
            "fivegs_ep_n3_gtp_indatapktn3upf": 1000,
            "fivegs_ep_n3_gtp_outdatapktn3upf": 1000,
        },
        "pcscf": {
            "ims_usrloc_pcscf:registered_contacts": 2,
            "dialog_ng:active": 0,
            "httpclient:connfail": 1400,
            "httpclient:connok": 0,
            "sl:4xx_replies": 0,
            "sl:5xx_replies": 0,
            "core:rcv_requests_register": 100,
            "core:rcv_requests_invite": 50,
        },
        "icscf": {
            "ims_icscf:uar_replies_received": 50,
            "ims_icscf:lir_replies_received": 50,
            "ims_icscf:uar_timeouts": 0,
            "ims_icscf:lir_timeouts": 0,
            "cdp:replies_received": 100,
            "cdp:timeout": 0,
        },
        "scscf": {
            "ims_usrloc_scscf:active_contacts": 2,
            "ims_auth:mar_timeouts": 0,
            "ims_auth:mar_replies_received": 50,
            "ims_registrar_scscf:sar_timeouts": 0,
            "ims_registrar_scscf:sar_replies_received": 50,
            "cdp:replies_received": 100,
            "cdp:timeout": 0,
        },
        "pcf": {
            "fivegs_pcffunction_pa_policyamassoreq": 10,
            "fivegs_pcffunction_pa_policyamassosucc": 10,
        },
    }


# ============================================================================
# Live-mode happy path
# ============================================================================

@pytest.mark.asyncio
async def test_returns_two_block_structure_per_nf():
    """The tool's output must contain a 'Model features' block AND a
    'Diagnostic supporting' block under each NF section."""
    raw = _baseline_snapshot()
    text = _fake_snap_text(raw)

    async def fake_get_nf_metrics():
        return text

    async def fake_sleep(_):
        return

    with patch(
        "agentic_ops_common.tools.get_nf_metrics",
        side_effect=fake_get_nf_metrics,
    ), patch(
        "agentic_ops_common.tools.diagnostic_metrics.asyncio.sleep",
        side_effect=fake_sleep,
    ), patch(
        "anomaly_trainer.persistence.load_model",
        return_value=(None, None, {}),
    ):
        out = await get_diagnostic_metrics()

    # Each tracked NF gets both block headers.
    for nf in ("PCSCF", "ICSCF", "SCSCF", "AMF", "SMF", "PCF"):
        assert nf in out, f"NF {nf} missing from output"
    assert "-- Model features --" in out
    assert "-- Diagnostic supporting --" in out


@pytest.mark.asyncio
async def test_supporting_block_includes_tagged_metrics():
    """Metrics tagged agent_exposed=True in the live KB show up in
    the supporting block. Spot-check the canonical members."""
    raw = _baseline_snapshot()
    text = _fake_snap_text(raw)

    async def fake_get_nf_metrics():
        return text

    async def fake_sleep(_):
        return

    with patch(
        "agentic_ops_common.tools.get_nf_metrics",
        side_effect=fake_get_nf_metrics,
    ), patch(
        "agentic_ops_common.tools.diagnostic_metrics.asyncio.sleep",
        side_effect=fake_sleep,
    ), patch(
        "anomaly_trainer.persistence.load_model",
        return_value=(None, None, {}),
    ):
        out = await get_diagnostic_metrics()

    # Canonical agent_exposed metrics from the KB.
    assert "httpclient:connfail = 1400" in out
    assert "httpclient:connok = 0" in out
    assert "sl:4xx_replies = 0" in out
    assert "ims_icscf:uar_timeouts = 0" in out
    assert "ims_auth:mar_timeouts = 0" in out
    assert "ims_registrar_scscf:sar_timeouts = 0" in out


@pytest.mark.asyncio
async def test_scale_dependent_metrics_render_presence_check_hint():
    """Metrics tagged with `tags: [scale_dependent]` get a special
    rendering note teaching the agent to read them as presence checks
    rather than absolute counts. Without this, agents have read e.g.
    `ran_ue = 2` as an authoritative deployment-size statement."""
    raw = _baseline_snapshot()
    text = _fake_snap_text(raw)

    async def fake_get_nf_metrics():
        return text

    async def fake_sleep(_):
        return

    with patch(
        "agentic_ops_common.tools.get_nf_metrics",
        side_effect=fake_get_nf_metrics,
    ), patch(
        "agentic_ops_common.tools.diagnostic_metrics.asyncio.sleep",
        side_effect=fake_sleep,
    ), patch(
        "anomaly_trainer.persistence.load_model",
        return_value=(None, None, {}),
    ):
        out = await get_diagnostic_metrics()

    # ran_ue, gnb, amf_session, sessionnbr are tagged scale_dependent.
    assert "Scale-dependent: read as a presence check" in out
    # The hint should appear under each scale-dependent metric's line —
    # at minimum, count >= 4 occurrences (one per tagged metric).
    assert out.count("Scale-dependent: read as a presence check") >= 4


@pytest.mark.asyncio
async def test_pre_existing_noise_surfaced_for_pcscf_connfail():
    """The P-CSCF httpclient:connfail metric carries known pre-
    existing-noise documentation in its KB entry (the SCP_BIND_IP
    placeholder baseline). The tool must surface this so the agent
    doesn't misread the elevated baseline as evidence of a fault."""
    raw = _baseline_snapshot()
    text = _fake_snap_text(raw)

    async def fake_get_nf_metrics():
        return text

    async def fake_sleep(_):
        return

    with patch(
        "agentic_ops_common.tools.get_nf_metrics",
        side_effect=fake_get_nf_metrics,
    ), patch(
        "agentic_ops_common.tools.diagnostic_metrics.asyncio.sleep",
        side_effect=fake_sleep,
    ), patch(
        "anomaly_trainer.persistence.load_model",
        return_value=(None, None, {}),
    ):
        out = await get_diagnostic_metrics()

    # The KB's pre_existing_noise text mentions SCP_BIND_IP — the
    # render layer pulls this onto a NOTE line.
    assert "SCP_BIND_IP" in out, (
        "P-CSCF httpclient:connfail's pre-existing-noise note was not "
        "surfaced; agents will misread the 1400 baseline as a fault."
    )


@pytest.mark.asyncio
async def test_nf_filter_restricts_output():
    """Passing nfs=['pcscf'] returns only that NF's section."""
    raw = _baseline_snapshot()
    text = _fake_snap_text(raw)

    async def fake_get_nf_metrics():
        return text

    async def fake_sleep(_):
        return

    with patch(
        "agentic_ops_common.tools.get_nf_metrics",
        side_effect=fake_get_nf_metrics,
    ), patch(
        "agentic_ops_common.tools.diagnostic_metrics.asyncio.sleep",
        side_effect=fake_sleep,
    ), patch(
        "anomaly_trainer.persistence.load_model",
        return_value=(None, None, {}),
    ):
        out = await get_diagnostic_metrics(nfs=["pcscf"])

    assert "PCSCF" in out
    assert "ICSCF" not in out
    assert "SCSCF" not in out
    assert "AMF" not in out


# ============================================================================
# Time-aware mode (Step 5) — historical replay against observation_snapshots
# ============================================================================

def _historical_snap(ts: float, raw: dict) -> dict:
    """Build a snapshot in the shape ObservationTrafficAgent writes."""
    return {
        "_timestamp": ts,
        **{nf: {"metrics": dict(metrics)} for nf, metrics in raw.items()},
    }


@pytest.mark.asyncio
async def test_at_time_ts_with_no_snapshots_surfaces_clear_message():
    """When the orchestrator hasn't pushed any snapshots into the
    contextvar, a time-anchored query cannot be answered. The tool
    must surface this explicitly — NEVER silently fall back to live
    data, since that defeats the time-anchoring contract."""
    from agentic_ops_common.tools.snapshot_replay import (
        set_observation_snapshots,
    )
    set_observation_snapshots([])

    out = await get_diagnostic_metrics(at_time_ts=1_700_000_000.0)
    assert "no observation_snapshots" in out
    assert "1700000000" in out


@pytest.mark.asyncio
async def test_at_time_ts_outside_window_surfaces_clear_message():
    """When the requested timestamp is outside the snapshot history's
    time range (or further than drift tolerance from any snapshot),
    surface the gap explicitly — show the operator what window the
    snapshots actually cover."""
    from agentic_ops_common.tools.snapshot_replay import (
        set_observation_snapshots,
    )
    raw = _baseline_snapshot()
    snapshots = [_historical_snap(1_000_000_000.0 + i * 5.0, raw) for i in range(5)]
    set_observation_snapshots(snapshots)

    # Request a ts that's far outside the window.
    out = await get_diagnostic_metrics(at_time_ts=2_000_000_000.0)
    assert "no snapshot within drift tolerance" in out
    # The window range is included in the message so the operator
    # knows what's available.
    assert "snapshot history covers" in out


@pytest.mark.asyncio
async def test_at_time_ts_with_matching_snapshot_renders_historical():
    """Happy path: a timestamp within the snapshot history returns
    the curated view derived from that historical state. Header
    surfaces the anchor."""
    from agentic_ops_common.tools.snapshot_replay import (
        set_observation_snapshots,
    )
    base_ts = 1_700_000_000.0
    raw = _baseline_snapshot()
    # 7+ snapshots so the preprocessor's rate window is populated.
    snapshots = [
        _historical_snap(base_ts + i * 5.0, raw) for i in range(8)
    ]
    set_observation_snapshots(snapshots)

    target_ts = base_ts + 30.0  # snapshot 6
    with patch(
        "anomaly_trainer.persistence.load_model",
        return_value=(None, None, {}),
    ):
        out = await get_diagnostic_metrics(at_time_ts=target_ts)

    # Header surfaces the anchor.
    assert f"anchored at ts={int(target_ts)}" in out
    # NOT in live mode.
    assert "live snapshot" not in out
    # Both blocks rendered for canonical NFs (the historical snapshot
    # has the same data, so all NFs show up).
    assert "PCSCF" in out
    assert "-- Model features --" in out
    assert "-- Diagnostic supporting --" in out
    # Supporting metrics from the matched snapshot land correctly.
    assert "httpclient:connfail = 1400" in out


@pytest.mark.asyncio
async def test_at_time_ts_does_not_call_live_get_nf_metrics():
    """Time-anchored mode must NOT make live snapshots of metrics —
    only consult the historical observation_snapshots. If we
    accidentally called live get_nf_metrics, that defeats the whole
    point of time-anchoring."""
    from agentic_ops_common.tools.snapshot_replay import (
        set_observation_snapshots,
    )
    base_ts = 1_700_000_000.0
    raw = _baseline_snapshot()
    snapshots = [_historical_snap(base_ts + i * 5.0, raw) for i in range(8)]
    set_observation_snapshots(snapshots)

    live_call_count = 0

    async def counting_get_nf_metrics():
        nonlocal live_call_count
        live_call_count += 1
        return ""

    async def fake_sleep(_):
        return

    with patch(
        "agentic_ops_common.tools.get_nf_metrics",
        side_effect=counting_get_nf_metrics,
    ), patch(
        "agentic_ops_common.tools.diagnostic_metrics.asyncio.sleep",
        side_effect=fake_sleep,
    ), patch(
        "anomaly_trainer.persistence.load_model",
        return_value=(None, None, {}),
    ):
        await get_diagnostic_metrics(at_time_ts=base_ts + 30.0)

    assert live_call_count == 0, (
        f"time-anchored mode called live get_nf_metrics {live_call_count} "
        f"time(s); it must consult observation_snapshots only."
    )


@pytest.mark.asyncio
async def test_live_mode_header_says_live_snapshot():
    """The header makes the live-vs-anchored distinction visible to
    the agent. Live mode must say 'live snapshot' so the agent knows
    what kind of evidence it's looking at."""
    raw = _baseline_snapshot()
    text = _fake_snap_text(raw)

    async def fake_get_nf_metrics():
        return text

    async def fake_sleep(_):
        return

    with patch(
        "agentic_ops_common.tools.get_nf_metrics",
        side_effect=fake_get_nf_metrics,
    ), patch(
        "agentic_ops_common.tools.diagnostic_metrics.asyncio.sleep",
        side_effect=fake_sleep,
    ), patch(
        "anomaly_trainer.persistence.load_model",
        return_value=(None, None, {}),
    ):
        out = await get_diagnostic_metrics()

    assert "live snapshot" in out
    assert "anchored at" not in out


# ============================================================================
# Public API surface
# ============================================================================

def test_get_diagnostic_metrics_exported_from_tools_package():
    """Step 4 wires this into the agent toolsets via
    `agentic_ops_common.tools.get_diagnostic_metrics`. Confirm the
    name is reachable from that path."""
    from agentic_ops_common import tools
    assert hasattr(tools, "get_diagnostic_metrics")
    assert tools.get_diagnostic_metrics is get_diagnostic_metrics
