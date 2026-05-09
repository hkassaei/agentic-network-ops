"""Path-walk types + Protocol-compliance tests.

Per Phase 1 of ADR `path_anchored_probe_planning_for_transport_layer_faults.md`.
Asserts:
  - Every shipped HopProber implements the runtime-checkable HopProber Protocol.
  - The registry covers every lab hop_kind.
  - HopAttribution variants discriminate via their `kind` literal.
  - PathWalkReport.first_attributed_hop / is_localized work as documented.
"""

from __future__ import annotations

from agentic_ops_common.path_walk import (
    CleanHop,
    DockerBridgeProber,
    DropsAttributedHere,
    DropsAttributedToInboundLink,
    Hop,
    HopAttribution,
    HopProber,
    HopRecord,
    InconclusiveHop,
    KernelHopProber,
    LatencyAtHop,
    PathWalkReport,
)
from agentic_ops_common.path_walk.probers.registry import (
    all_probers_for_kind,
    prober_for_kind,
    registered_kinds,
)


# ---------------------------------------------------------------------------
# HopProber protocol compliance
# ---------------------------------------------------------------------------


def test_kernel_hop_prober_satisfies_hop_prober_protocol():
    """Runtime-checkable Protocol — KernelHopProber must satisfy it."""
    assert isinstance(KernelHopProber(), HopProber)


def test_docker_bridge_prober_satisfies_hop_prober_protocol():
    assert isinstance(DockerBridgeProber(), HopProber)


def test_kernel_hop_prober_supported_kinds():
    assert KernelHopProber().supported_kinds == ("container",)


def test_docker_bridge_prober_supported_kinds():
    assert DockerBridgeProber().supported_kinds == ("docker_bridge",)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_registry_covers_lab_hop_kinds():
    """Lab probers cover the two kinds the docker_open5gs deployment uses."""
    kinds = registered_kinds()
    assert "container" in kinds
    assert "docker_bridge" in kinds


def test_registry_dispatches_to_kernel_for_container():
    prober = prober_for_kind("container")
    assert isinstance(prober, KernelHopProber)


def test_registry_dispatches_to_bridge_for_docker_bridge():
    prober = prober_for_kind("docker_bridge")
    assert isinstance(prober, DockerBridgeProber)


def test_registry_raises_on_unknown_kind():
    """Unregistered hop kind is a topology-authoring bug, not a runtime gap.

    The walker treats a KeyError here as a configuration error
    surfaced explicitly. Carrier-grade kinds (l2_switch, etc.) raise
    until their probers land in follow-up ADRs.
    """
    import pytest
    with pytest.raises(KeyError):
        prober_for_kind("l3_router")  # type: ignore[arg-type]


def test_registry_all_probers_returns_list():
    """all_probers_for_kind returns a list — single-prober kinds today,
    multi-prober kinds in future deployments."""
    probers = all_probers_for_kind("container")
    assert isinstance(probers, list)
    assert len(probers) >= 1


# ---------------------------------------------------------------------------
# HopAttribution discrimination
# ---------------------------------------------------------------------------


def test_clean_hop_kind_literal():
    assert CleanHop().kind == "clean"


def test_drops_attributed_here_kind_literal():
    a = DropsAttributedHere(
        counter_kind="qdisc_netem",
        dropped_pkts=42,
        dropped_pct=0.30,
        evidence="test",
    )
    assert a.kind == "drops_attributed_here"
    assert a.counter_kind == "qdisc_netem"
    assert a.dropped_pkts == 42


def test_drops_attributed_to_inbound_link_kind_literal():
    a = DropsAttributedToInboundLink(
        observed_loss_pct=0.30,
        tx_rate=100.0,
        rx_rate=70.0,
        evidence="test",
    )
    assert a.kind == "drops_attributed_to_inbound_link"


def test_latency_at_hop_kind_literal():
    a = LatencyAtHop(
        observed_delay_ms=100.0,
        counter_kind="qdisc_netem_delay",
        evidence="test",
    )
    assert a.kind == "latency_at_hop"


def test_inconclusive_hop_kind_literal():
    a = InconclusiveHop(reason="tool_unavailable")
    assert a.kind == "inconclusive"


# ---------------------------------------------------------------------------
# PathWalkReport accessors
# ---------------------------------------------------------------------------


def _hop(node: str, kind: str = "container") -> Hop:
    return Hop(node=node, kind=kind, iface="eth0")  # type: ignore[arg-type]


def _record(node: str, attribution: HopAttribution) -> HopRecord:
    return HopRecord(hop=_hop(node), attribution=attribution, prober="test")


def test_first_attributed_hop_finds_drops():
    report = PathWalkReport(
        flow_id="test",
        direction="uplink",
        anchor_ts=None,
        window_seconds=5,
        hops=[
            _record("a", CleanHop()),
            _record("b", CleanHop()),
            _record("c", DropsAttributedHere(
                counter_kind="qdisc_netem",
                dropped_pkts=10,
                dropped_pct=0.30,
                evidence="t",
            )),
            _record("d", CleanHop()),
        ],
    )
    assert report.is_localized
    assert report.first_attributed_hop is not None
    assert report.first_attributed_hop.hop.node == "c"


def test_first_attributed_hop_finds_latency():
    report = PathWalkReport(
        flow_id="t", direction="uplink", anchor_ts=None, window_seconds=5,
        hops=[
            _record("a", CleanHop()),
            _record("b", LatencyAtHop(
                observed_delay_ms=100.0,
                counter_kind="qdisc_netem_delay",
                evidence="t",
            )),
        ],
    )
    assert report.is_localized
    assert report.first_attributed_hop.hop.node == "b"


def test_first_attributed_hop_finds_link_drop():
    report = PathWalkReport(
        flow_id="t", direction="uplink", anchor_ts=None, window_seconds=5,
        hops=[
            _record("a", CleanHop()),
            _record("b", DropsAttributedToInboundLink(
                observed_loss_pct=0.30,
                tx_rate=100.0, rx_rate=70.0,
                evidence="t",
            )),
        ],
    )
    assert report.is_localized
    assert report.first_attributed_hop.hop.node == "b"


def test_first_attributed_hop_returns_none_when_clean():
    report = PathWalkReport(
        flow_id="t", direction="uplink", anchor_ts=None, window_seconds=5,
        hops=[_record("a", CleanHop()), _record("b", CleanHop())],
    )
    assert not report.is_localized
    assert report.first_attributed_hop is None


def test_inconclusive_hop_does_not_count_as_localization():
    """An inconclusive hop is not an attribution. The walker's null-
    localization branch fires when every hop is clean OR inconclusive."""
    report = PathWalkReport(
        flow_id="t", direction="uplink", anchor_ts=None, window_seconds=5,
        hops=[
            _record("a", CleanHop()),
            _record("b", InconclusiveHop(reason="tool_unavailable")),
        ],
    )
    assert not report.is_localized
    assert report.first_attributed_hop is None
