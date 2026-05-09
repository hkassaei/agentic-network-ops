"""KernelHopProber attribution logic.

Per Phase 1 of ADR `path_anchored_probe_planning_for_transport_layer_faults.md`.

The prober's docker-exec'd telemetry is mocked at the
`get_qdisc_drops` / `get_interface_drops` boundary so we test the
attribution rules without touching real containers.
"""

from __future__ import annotations

import asyncio

import pytest

from agentic_ops_common.path_walk import (
    CleanHop,
    DropsAttributedHere,
    Hop,
    InconclusiveHop,
    KernelHopProber,
    LatencyAtHop,
)


def _hop(node: str = "rtpengine", iface: str = "eth0") -> Hop:
    return Hop(node=node, kind="container", iface=iface)


def _patch_probes(monkeypatch, qdisc_result: dict, iface_result: dict):
    """Replace the probe wrappers with stubs returning the supplied dicts."""
    from agentic_ops_common.path_walk.probers import kernel

    async def qdisc_stub(container, iface):
        return qdisc_result

    async def iface_stub(container, iface):
        return iface_result

    monkeypatch.setattr(kernel, "get_qdisc_drops", qdisc_stub)
    monkeypatch.setattr(kernel, "get_interface_drops", iface_stub)


# ---------------------------------------------------------------------------
# DropsAttributedHere via netem qdisc — the rtpengine 30% loss case
# ---------------------------------------------------------------------------


def test_kernel_prober_attributes_netem_loss(monkeypatch):
    """The exact attack from worked example 1: tc netem loss 30% on
    rtpengine egress. The prober must return drops_attributed_here
    with counter_kind=qdisc_netem and the authored loss percentage."""
    qdisc = {
        "qdisc_kind": "netem",
        "sent_pkts": 1000,
        "dropped_pkts": 300,
        "dropped_pct": 0.30,
        "loss_pct": 0.30,
        "delay_ms": None,
        "raw": "qdisc netem 8001: root refcnt 2 limit 1000 loss 30%\n Sent ... pkt (dropped 300, ...)",
    }
    iface = {
        "rx_bytes": 1, "rx_pkts": 1, "rx_errors": 0, "rx_dropped": 0,
        "tx_bytes": 1, "tx_pkts": 1, "tx_errors": 0, "tx_dropped": 0,
        "raw": "...",
    }
    _patch_probes(monkeypatch, qdisc, iface)

    prober = KernelHopProber()
    attribution = asyncio.run(prober.probe(_hop("rtpengine"), 5, None))

    assert attribution.kind == "drops_attributed_here"
    assert isinstance(attribution, DropsAttributedHere)
    assert attribution.counter_kind == "qdisc_netem"
    assert attribution.dropped_pkts == 300
    assert attribution.dropped_pct == 0.30
    assert "rtpengine[eth0]" in attribution.evidence
    assert "loss=30%" in attribution.evidence


# ---------------------------------------------------------------------------
# DropsAttributedHere via tbf rate cap
# ---------------------------------------------------------------------------


def test_kernel_prober_attributes_tbf_drops(monkeypatch):
    """tbf rate cap drops are also kernel-level. Different counter_kind."""
    qdisc = {
        "qdisc_kind": "tbf",
        "sent_pkts": 100,
        "dropped_pkts": 25,
        "dropped_pct": 0.25,
        "loss_pct": None,
        "delay_ms": None,
        "raw": "qdisc tbf 8002: root refcnt 2 rate 100Kbit ...",
    }
    iface = {
        "rx_bytes": 1, "rx_pkts": 1, "rx_errors": 0, "rx_dropped": 0,
        "tx_bytes": 1, "tx_pkts": 1, "tx_errors": 0, "tx_dropped": 0,
        "raw": "...",
    }
    _patch_probes(monkeypatch, qdisc, iface)

    prober = KernelHopProber()
    attribution = asyncio.run(prober.probe(_hop("upf"), 5, None))

    assert attribution.kind == "drops_attributed_here"
    assert isinstance(attribution, DropsAttributedHere)
    assert attribution.counter_kind == "qdisc_tbf"
    assert attribution.dropped_pkts == 25


# ---------------------------------------------------------------------------
# LatencyAtHop via netem delay
# ---------------------------------------------------------------------------


def test_kernel_prober_attributes_netem_delay(monkeypatch):
    """netem delay 100ms with NO drops. The prober must return
    latency_at_hop, not drops_attributed_here. This is the
    rtpengine_latency_injection generalization scenario."""
    qdisc = {
        "qdisc_kind": "netem",
        "sent_pkts": 100,
        "dropped_pkts": 0,
        "dropped_pct": 0.0,
        "loss_pct": None,
        "delay_ms": 100.0,
        "raw": "qdisc netem 8001: root refcnt 2 limit 1000 delay 100.0ms\n Sent 6240 bytes 100 pkt (dropped 0, ...)",
    }
    iface = {
        "rx_bytes": 1, "rx_pkts": 1, "rx_errors": 0, "rx_dropped": 0,
        "tx_bytes": 1, "tx_pkts": 1, "tx_errors": 0, "tx_dropped": 0,
        "raw": "...",
    }
    _patch_probes(monkeypatch, qdisc, iface)

    prober = KernelHopProber()
    attribution = asyncio.run(prober.probe(_hop("rtpengine"), 5, None))

    assert attribution.kind == "latency_at_hop"
    assert isinstance(attribution, LatencyAtHop)
    assert attribution.observed_delay_ms == 100.0
    assert attribution.counter_kind == "qdisc_netem_delay"


# ---------------------------------------------------------------------------
# Interface-level drops (no qdisc explanation)
# ---------------------------------------------------------------------------


def test_kernel_prober_attributes_iface_dropped(monkeypatch):
    """qdisc clean but interface counters report TX/RX drops —
    typically NIC ring-buffer overrun."""
    qdisc = {
        "qdisc_kind": "noqueue",
        "sent_pkts": 0,
        "dropped_pkts": 0,
        "dropped_pct": None,
        "loss_pct": None,
        "delay_ms": None,
        "raw": "qdisc noqueue 0: root refcnt 2",
    }
    iface = {
        "rx_bytes": 1000, "rx_pkts": 100, "rx_errors": 0, "rx_dropped": 5,
        "tx_bytes": 1000, "tx_pkts": 100, "tx_errors": 0, "tx_dropped": 7,
        "raw": "RX: ...\nTX: ...",
    }
    _patch_probes(monkeypatch, qdisc, iface)

    prober = KernelHopProber()
    attribution = asyncio.run(prober.probe(_hop("upf"), 5, None))

    assert attribution.kind == "drops_attributed_here"
    assert isinstance(attribution, DropsAttributedHere)
    assert attribution.counter_kind == "iface_dropped"
    assert attribution.dropped_pkts == 12  # 5 + 7


def test_kernel_prober_attributes_iface_error(monkeypatch):
    """qdisc + iface_dropped both clean, but TX/RX errors > 0."""
    qdisc = {
        "qdisc_kind": "fq_codel",
        "sent_pkts": 100,
        "dropped_pkts": 0,
        "dropped_pct": 0.0,
        "loss_pct": None,
        "delay_ms": None,
        "raw": "qdisc fq_codel ...",
    }
    iface = {
        "rx_bytes": 1000, "rx_pkts": 100, "rx_errors": 3, "rx_dropped": 0,
        "tx_bytes": 1000, "tx_pkts": 100, "tx_errors": 2, "tx_dropped": 0,
        "raw": "...",
    }
    _patch_probes(monkeypatch, qdisc, iface)

    prober = KernelHopProber()
    attribution = asyncio.run(prober.probe(_hop("upf"), 5, None))

    assert attribution.kind == "drops_attributed_here"
    assert isinstance(attribution, DropsAttributedHere)
    assert attribution.counter_kind == "iface_error"
    assert attribution.dropped_pkts == 5  # 3 + 2


# ---------------------------------------------------------------------------
# Clean
# ---------------------------------------------------------------------------


def test_kernel_prober_returns_clean_when_no_drops_or_errors(monkeypatch):
    qdisc = {
        "qdisc_kind": "fq_codel",
        "sent_pkts": 1000,
        "dropped_pkts": 0,
        "dropped_pct": 0.0,
        "loss_pct": None,
        "delay_ms": None,
        "raw": "qdisc fq_codel 0: root refcnt 2 ...",
    }
    iface = {
        "rx_bytes": 12345, "rx_pkts": 678, "rx_errors": 0, "rx_dropped": 0,
        "tx_bytes": 67890, "tx_pkts": 123, "tx_errors": 0, "tx_dropped": 0,
        "raw": "RX: ...\nTX: ...",
    }
    _patch_probes(monkeypatch, qdisc, iface)

    prober = KernelHopProber()
    attribution = asyncio.run(prober.probe(_hop("amf"), 5, None))

    assert attribution.kind == "clean"
    assert isinstance(attribution, CleanHop)
    assert "amf[eth0]" in attribution.evidence


# ---------------------------------------------------------------------------
# Inconclusive — toolbelt gap, container absent
# ---------------------------------------------------------------------------


def test_kernel_prober_inconclusive_when_tc_missing(monkeypatch):
    """Per the toolbelt ADR, missing tc surfaces as InconclusiveHop —
    NOT silently rebranded as clean."""
    qdisc = {
        "_error": "tool_unavailable",
        "missing_binary": "tc",
        "container": "rtpengine",
    }
    iface = {}  # not reached
    _patch_probes(monkeypatch, qdisc, iface)

    prober = KernelHopProber()
    attribution = asyncio.run(prober.probe(_hop("rtpengine"), 5, None))

    assert attribution.kind == "inconclusive"
    assert isinstance(attribution, InconclusiveHop)
    assert attribution.reason == "tool_unavailable"
    assert "tc" in attribution.detail


def test_kernel_prober_inconclusive_when_qdisc_probe_fails(monkeypatch):
    qdisc = {
        "_error": "tc qdisc show failed (rc=1): some error",
        "container": "rtpengine",
    }
    iface = {}
    _patch_probes(monkeypatch, qdisc, iface)

    prober = KernelHopProber()
    attribution = asyncio.run(prober.probe(_hop("rtpengine"), 5, None))

    assert attribution.kind == "inconclusive"
    assert isinstance(attribution, InconclusiveHop)
    assert attribution.reason == "qdisc_probe_failed"


def test_kernel_prober_inconclusive_when_iface_probe_fails(monkeypatch):
    qdisc = {
        "qdisc_kind": "fq_codel",
        "sent_pkts": 100,
        "dropped_pkts": 0,
        "dropped_pct": 0.0,
        "loss_pct": None,
        "delay_ms": None,
        "raw": "...",
    }
    iface = {
        "_error": "ip link show failed (rc=1): err",
        "container": "rtpengine",
    }
    _patch_probes(monkeypatch, qdisc, iface)

    prober = KernelHopProber()
    attribution = asyncio.run(prober.probe(_hop("rtpengine"), 5, None))

    assert attribution.kind == "inconclusive"
    assert isinstance(attribution, InconclusiveHop)
    assert attribution.reason == "interface_probe_failed"


def test_kernel_prober_rejects_wrong_hop_kind(monkeypatch):
    """KernelHopProber claims `container` only; bridge/switch hops
    must produce InconclusiveHop with reason=unsupported_hop_kind so
    the registry's misdispatch is visible."""
    def fail(*args, **kwargs):
        raise AssertionError("should not be reached for wrong-kind hop")

    from agentic_ops_common.path_walk.probers import kernel
    monkeypatch.setattr(kernel, "get_qdisc_drops", fail)
    monkeypatch.setattr(kernel, "get_interface_drops", fail)

    prober = KernelHopProber()
    bad_hop = Hop(node="docker0", kind="docker_bridge", iface="docker0")
    attribution = asyncio.run(prober.probe(bad_hop, 5, None))

    assert attribution.kind == "inconclusive"
    assert isinstance(attribution, InconclusiveHop)
    assert attribution.reason == "unsupported_hop_kind"
