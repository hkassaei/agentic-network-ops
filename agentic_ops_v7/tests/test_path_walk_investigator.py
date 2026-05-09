"""PathWalkInvestigator — walker tests with mocked probers.

Per Phase 4 of ADR `path_anchored_probe_planning_for_transport_layer_faults.md`.
Mocks the prober registry to drive the walker with synthetic
HopAttribution outputs; asserts the walker localizes correctly,
preserves topology order, and handles edge cases.

The probers themselves were tested in Phase 1 against synthetic shell
output. This module tests the walker's composition logic.
"""

from __future__ import annotations

import asyncio

import pytest

from agentic_ops_common.path_walk import (
    CleanHop,
    DropsAttributedHere,
    DropsAttributedToInboundLink,
    Hop,
    HopAttribution,
    HopRecord,
    InconclusiveHop,
    LatencyAtHop,
    PathWalkReport,
)
from agentic_ops_v7.subagents import path_walk_investigator as walker_mod
from agentic_ops_v7.subagents.path_walk_investigator import walk_path


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


class _StubProber:
    """A synthetic HopProber that returns a pre-baked attribution."""

    def __init__(self, attribution: HopAttribution, kinds: tuple[str, ...]):
        self._attribution = attribution
        self._kinds = kinds
        self.call_count = 0

    @property
    def supported_kinds(self):
        return self._kinds

    async def probe(self, hop, window_seconds, anchor_ts):
        self.call_count += 1
        return self._attribution


def _patch_registry(monkeypatch, attribution_map: dict[str, HopAttribution]):
    """Replace prober_for_kind with a per-node lookup.

    `attribution_map[node_name]` returns the attribution for that
    node's probe. Default for unmapped nodes: CleanHop.
    """
    def _stub_prober_for_kind(kind):
        # Return a prober that looks up the next call's attribution
        # based on the hop's node — we do this via a closure that
        # holds the attribution_map.
        class _DispatchProber:
            @property
            def supported_kinds(self):
                return (kind,)

            async def probe(self, hop, window_seconds, anchor_ts):
                return attribution_map.get(hop.node, CleanHop(evidence=f"clean: {hop.node}"))

        return _DispatchProber()

    monkeypatch.setattr(walker_mod, "prober_for_kind", _stub_prober_for_kind)


def _disable_link_diff(monkeypatch):
    """Make the inter-hop diff a no-op for tests that don't care about it."""
    async def _noop(*args, **kwargs):
        return {"_error": "disabled in test"}
    monkeypatch.setattr(
        "agentic_ops_common.tools.reachability.get_link_rate_diff",
        _noop,
    )


def _vonr_media_hops() -> list[Hop]:
    """A minimal synthetic VoNR media hop list."""
    return [
        Hop(node="e2e_ue1", kind="container", iface="eth0"),
        Hop(node="bridge", kind="docker_bridge", iface="br0"),
        Hop(node="nr_gnb", kind="container", iface="eth0"),
        Hop(node="bridge", kind="docker_bridge", iface="br0"),
        Hop(node="upf", kind="container", iface="eth0"),
        Hop(node="bridge", kind="docker_bridge", iface="br0"),
        Hop(node="rtpengine", kind="container", iface="eth0"),
    ]


# ---------------------------------------------------------------------------
# Localization: hop attribution
# ---------------------------------------------------------------------------


def test_walker_localizes_qdisc_drop_at_rtpengine(monkeypatch):
    """The contract test scenario: rtpengine has a netem qdisc with
    drops. The walker must attribute to rtpengine and produce a
    `localized` report."""
    _disable_link_diff(monkeypatch)
    _patch_registry(monkeypatch, {
        "rtpengine": DropsAttributedHere(
            counter_kind="qdisc_netem",
            dropped_pkts=300,
            dropped_pct=0.30,
            evidence="qdisc netem ... loss 30% Sent 1000 pkt (dropped 300, ...)",
        ),
        # everything else clean
    })

    report = asyncio.run(walk_path(
        flow_id="vonr_media",
        hops=_vonr_media_hops(),
        anchor_ts=None,
    ))

    assert report.is_localized
    first = report.first_attributed_hop
    assert first is not None
    assert first.hop.node == "rtpengine"
    assert first.attribution.kind == "drops_attributed_here"
    assert isinstance(first.attribution, DropsAttributedHere)
    assert first.attribution.counter_kind == "qdisc_netem"
    assert first.attribution.dropped_pkts == 300


def test_walker_localizes_latency(monkeypatch):
    """netem delay produces LatencyAtHop, not DropsAttributedHere.
    The walker should still localize correctly."""
    _disable_link_diff(monkeypatch)
    _patch_registry(monkeypatch, {
        "rtpengine": LatencyAtHop(
            observed_delay_ms=100.0,
            counter_kind="qdisc_netem_delay",
            evidence="qdisc netem ... delay 100ms",
        ),
    })

    report = asyncio.run(walk_path("vonr_media", _vonr_media_hops()))
    assert report.is_localized
    assert report.first_attributed_hop.attribution.kind == "latency_at_hop"
    assert isinstance(report.first_attributed_hop.attribution, LatencyAtHop)
    assert report.first_attributed_hop.attribution.observed_delay_ms == 100.0


def test_walker_returns_first_attributed_in_topology_order(monkeypatch):
    """When two hops report drops, the walker's first_attributed_hop
    is the one earliest in topology order."""
    _disable_link_diff(monkeypatch)
    _patch_registry(monkeypatch, {
        "upf": DropsAttributedHere(
            counter_kind="qdisc_tbf", dropped_pkts=10,
            dropped_pct=0.10, evidence="upf tbf",
        ),
        "rtpengine": DropsAttributedHere(
            counter_kind="qdisc_netem", dropped_pkts=300,
            dropped_pct=0.30, evidence="rtpengine netem",
        ),
    })

    report = asyncio.run(walk_path("vonr_media", _vonr_media_hops()))
    assert report.first_attributed_hop is not None
    # upf comes before rtpengine in the hop list — even though
    # rtpengine drops more, upf is hit first.
    assert report.first_attributed_hop.hop.node == "upf"


def test_walker_returns_null_localization_when_all_clean(monkeypatch):
    """Every hop clean -> is_localized=False, first_attributed_hop=None."""
    _disable_link_diff(monkeypatch)
    _patch_registry(monkeypatch, {})  # all default to CleanHop

    report = asyncio.run(walk_path("vonr_media", _vonr_media_hops()))
    assert not report.is_localized
    assert report.first_attributed_hop is None


def test_walker_inconclusive_does_not_count_as_localization(monkeypatch):
    """An InconclusiveHop (e.g. tool_unavailable) is a probe gap, not
    an attribution. The walker must not mark the report as localized
    on inconclusive hops alone."""
    _disable_link_diff(monkeypatch)
    _patch_registry(monkeypatch, {
        "rtpengine": InconclusiveHop(
            reason="tool_unavailable",
            detail="tc binary missing",
        ),
    })

    report = asyncio.run(walk_path("vonr_media", _vonr_media_hops()))
    assert not report.is_localized
    assert report.first_attributed_hop is None
    # The inconclusive record should still be in the report so operators
    # can see the probe gap.
    inc_records = [
        r for r in report.hops
        if r.attribution.kind == "inconclusive"
    ]
    assert len(inc_records) == 1
    assert inc_records[0].hop.node == "rtpengine"


# ---------------------------------------------------------------------------
# Walk traversal correctness
# ---------------------------------------------------------------------------


def test_walker_visits_every_hop_in_order(monkeypatch):
    """Every hop in the input list gets a HopRecord in the output, in
    the same order. This guards against a future regression where the
    walker accidentally skips hops or reorders them."""
    _disable_link_diff(monkeypatch)
    _patch_registry(monkeypatch, {})

    hops = _vonr_media_hops()
    report = asyncio.run(walk_path("vonr_media", hops))
    assert len(report.hops) == len(hops)
    for input_hop, record in zip(hops, report.hops):
        assert record.hop.node == input_hop.node
        assert record.hop.kind == input_hop.kind
        assert record.hop.iface == input_hop.iface


def test_walker_records_prober_name(monkeypatch):
    """Each HopRecord carries the prober class name for traceability.
    The walker must populate this — operators audit which prober
    produced which attribution."""
    _disable_link_diff(monkeypatch)
    _patch_registry(monkeypatch, {})

    report = asyncio.run(walk_path("vonr_media", _vonr_media_hops()))
    for record in report.hops:
        assert record.prober, (
            f"empty prober name on hop {record.hop.node}"
        )


def test_walker_handles_prober_exception(monkeypatch):
    """A prober that raises should not crash the walk — the hop is
    recorded as InconclusiveHop with reason=prober_raised."""
    _disable_link_diff(monkeypatch)

    class _RaisingProber:
        @property
        def supported_kinds(self):
            return ("container",)

        async def probe(self, hop, window_seconds, anchor_ts):
            raise RuntimeError("simulated prober crash")

    monkeypatch.setattr(
        walker_mod, "prober_for_kind",
        lambda kind: _RaisingProber(),
    )

    report = asyncio.run(walk_path("vonr_media", _vonr_media_hops()))
    # Walk completed and emitted records for every hop.
    assert len(report.hops) == len(_vonr_media_hops())
    # Every hop is now Inconclusive.
    for record in report.hops:
        assert record.attribution.kind == "inconclusive"
        assert isinstance(record.attribution, InconclusiveHop)
        assert record.attribution.reason == "prober_raised"
        assert "simulated prober crash" in record.attribution.detail


def test_walker_handles_unregistered_kind(monkeypatch):
    """A hop whose kind has no registered prober is recorded as
    InconclusiveHop(reason='no_prober_registered'), not silently
    skipped. Topology authoring bugs are loud."""
    def _raising_for_kind(kind):
        raise KeyError(f"no prober for {kind}")

    monkeypatch.setattr(walker_mod, "prober_for_kind", _raising_for_kind)
    _disable_link_diff(monkeypatch)

    report = asyncio.run(walk_path("vonr_media", _vonr_media_hops()))
    for record in report.hops:
        assert record.attribution.kind == "inconclusive"
        assert isinstance(record.attribution, InconclusiveHop)
        assert record.attribution.reason == "no_prober_registered"


# ---------------------------------------------------------------------------
# Inter-hop link-rate-diff augmentation
# ---------------------------------------------------------------------------


def test_walker_attributes_link_drop_when_rate_diff_significant(monkeypatch):
    """When two adjacent CONTAINER hops are both clean but the
    link-rate-diff between them is significant, the walker attributes
    the loss to the inbound link of the second hop."""
    _patch_registry(monkeypatch, {})  # all clean

    # Mock get_link_rate_diff to return a 30% loss between upf and rtpengine.
    async def _fake_diff(container_a, iface_a, container_b, iface_b,
                         direction, window_seconds):
        if container_a == "upf" and container_b == "rtpengine":
            return {
                "direction": direction,
                "window_seconds": window_seconds,
                "tx_rate_pkts_per_s": 100.0,
                "rx_rate_pkts_per_s": 70.0,
                "diff_pkts_per_s": 30.0,
                "attributed_loss_pct": 0.30,
                "evidence": "upf->rtpengine: 100 tx, 70 rx, 30% loss",
            }
        return {
            "direction": direction,
            "window_seconds": window_seconds,
            "tx_rate_pkts_per_s": 0.0,
            "rx_rate_pkts_per_s": 0.0,
            "diff_pkts_per_s": 0.0,
            "attributed_loss_pct": None,
            "evidence": "no traffic",
        }
    monkeypatch.setattr(
        "agentic_ops_common.tools.reachability.get_link_rate_diff",
        _fake_diff,
    )

    # Use a 2-container hop list (no bridge) so the augmentation fires.
    hops = [
        Hop(node="upf", kind="container", iface="eth0"),
        Hop(node="rtpengine", kind="container", iface="eth0"),
    ]
    report = asyncio.run(walk_path("vonr_media", hops))

    # rtpengine should be attributed via inter-hop link diff.
    rt_record = next(r for r in report.hops if r.hop.node == "rtpengine")
    assert rt_record.attribution.kind == "drops_attributed_to_inbound_link"
    assert isinstance(rt_record.attribution, DropsAttributedToInboundLink)
    assert rt_record.attribution.observed_loss_pct == 0.30


def test_walker_ignores_link_diff_below_noise_floor(monkeypatch):
    """A 2% TX/RX imbalance is below the noise floor — should NOT
    attribute the link as dropping."""
    _patch_registry(monkeypatch, {})

    async def _fake_diff(*args, **kwargs):
        return {
            "tx_rate_pkts_per_s": 100.0,
            "rx_rate_pkts_per_s": 98.0,
            "attributed_loss_pct": 0.02,  # 2%, below 5% floor
            "evidence": "noise",
        }
    monkeypatch.setattr(
        "agentic_ops_common.tools.reachability.get_link_rate_diff",
        _fake_diff,
    )

    hops = [
        Hop(node="upf", kind="container", iface="eth0"),
        Hop(node="rtpengine", kind="container", iface="eth0"),
    ]
    report = asyncio.run(walk_path("vonr_media", hops))
    assert not report.is_localized


# ---------------------------------------------------------------------------
# Public entry validation
# ---------------------------------------------------------------------------


def test_walker_rejects_empty_hop_list():
    """An empty hop list is a resolver bug; the walker raises rather
    than silently producing an empty report."""
    with pytest.raises(ValueError, match="empty hop list"):
        asyncio.run(walk_path("vonr_media", [], anchor_ts=None))


def test_walker_emits_path_walk_report_with_metadata(monkeypatch):
    """The PathWalkReport carries flow_id, direction, anchor_ts,
    window_seconds — operators read these for context."""
    _disable_link_diff(monkeypatch)
    _patch_registry(monkeypatch, {})

    report = asyncio.run(walk_path(
        flow_id="vonr_media",
        hops=_vonr_media_hops(),
        anchor_ts=1234567890.0,
        window_seconds=10,
        direction="downlink",
    ))
    assert report.flow_id == "vonr_media"
    assert report.direction == "downlink"
    assert report.anchor_ts == 1234567890.0
    assert report.window_seconds == 10
