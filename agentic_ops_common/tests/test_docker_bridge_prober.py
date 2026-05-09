"""DockerBridgeProber parsers + attribution logic.

Per Phase 1 of ADR `path_anchored_probe_planning_for_transport_layer_faults.md`.

The prober's actual `nsenter -t 1 -n` execution requires host
privilege and is verified by the Phase 1.11 integration runbook,
not here. These unit tests exercise the parsers and the attribution
logic with synthetic command outputs.
"""

from __future__ import annotations

import asyncio
from typing import Optional

import pytest

from agentic_ops_common.path_walk import (
    DockerBridgeProber,
    DropsAttributedHere,
    Hop,
    HopAttribution,
    InconclusiveHop,
)
from agentic_ops_common.path_walk.probers.docker_bridge import (
    _parse_conntrack_drops,
    _parse_iptables_forward_drops,
)


# ---------------------------------------------------------------------------
# iptables FORWARD parser
# ---------------------------------------------------------------------------


_IPTABLES_FORWARD_NO_DROPS = """\
Chain FORWARD (policy ACCEPT 0 packets, 0 bytes)
 pkts bytes target     prot opt in     out     source               destination
   42  3024 ACCEPT     all  --  *      *       0.0.0.0/0            0.0.0.0/0
"""


_IPTABLES_FORWARD_RANDOM_DROP = """\
Chain FORWARD (policy ACCEPT 100 packets, 12000 bytes)
 pkts bytes target     prot opt in     out     source               destination
   42  3024 ACCEPT     all  --  *      *       0.0.0.0/0            0.0.0.0/0
   18  1296 DROP       all  --  *      *       0.0.0.0/0            0.0.0.0/0  statistic mode random probability 0.30000000000
"""


_IPTABLES_FORWARD_REJECT_RULE = """\
Chain FORWARD (policy ACCEPT 0 packets, 0 bytes)
 pkts bytes target     prot opt in     out     source               destination
    7   504 REJECT     all  --  *      *       0.0.0.0/0            0.0.0.0/0  reject-with icmp-port-unreachable
"""


_IPTABLES_FORWARD_DROP_POLICY = """\
Chain FORWARD (policy DROP 5 packets, 320 bytes)
 pkts bytes target     prot opt in     out     source               destination
    0     0 ACCEPT     all  --  *      *       0.0.0.0/0            0.0.0.0/0
"""


def test_iptables_no_drops():
    total, evidence = _parse_iptables_forward_drops(_IPTABLES_FORWARD_NO_DROPS)
    assert total == 0
    assert "no DROP/REJECT rules with traffic" in evidence


def test_iptables_random_drop_30pct():
    """The exact attack from the bridge_loss generalization scenario:
    `iptables -A FORWARD -m statistic --mode random --probability 0.3 -j DROP`."""
    total, evidence = _parse_iptables_forward_drops(_IPTABLES_FORWARD_RANDOM_DROP)
    assert total == 18
    assert "DROP" in evidence
    assert "pkts=18" in evidence


def test_iptables_reject_counts_as_drop():
    total, evidence = _parse_iptables_forward_drops(_IPTABLES_FORWARD_REJECT_RULE)
    assert total == 7
    assert "REJECT" in evidence


def test_iptables_drop_policy_counts():
    """A DROP policy on the chain is a drop attribution too."""
    total, evidence = _parse_iptables_forward_drops(_IPTABLES_FORWARD_DROP_POLICY)
    assert total == 5
    assert "policy=DROP" in evidence


def test_iptables_zero_pkt_drop_rule_does_not_count():
    """A DROP rule with 0 packet matches isn't an attribution — the
    rule exists but has no traffic. Avoids false positives on dormant
    firewall rules."""
    output = """\
Chain FORWARD (policy ACCEPT 0 packets, 0 bytes)
 pkts bytes target     prot opt in     out     source               destination
    0     0 DROP       all  --  *      *       0.0.0.0/0            0.0.0.0/0
"""
    total, _ = _parse_iptables_forward_drops(output)
    assert total == 0


# ---------------------------------------------------------------------------
# conntrack parser
# ---------------------------------------------------------------------------


_CONNTRACK_HEALTHY = """\
cpu=0   found=0 invalid=2 ignore=0 insert=0 insert_failed=0 drop=0 early_drop=0 error=0 search_restart=0
cpu=1   found=0 invalid=0 ignore=0 insert=0 insert_failed=0 drop=0 early_drop=0 error=0 search_restart=0
"""


_CONNTRACK_DROPS = """\
cpu=0   found=12 invalid=2 ignore=0 insert=8 insert_failed=3 drop=42 early_drop=0 error=0 search_restart=0
cpu=1   found=8 invalid=0 ignore=0 insert=4 insert_failed=1 drop=18 early_drop=0 error=0 search_restart=0
"""


def test_conntrack_healthy():
    total, evidence = _parse_conntrack_drops(_CONNTRACK_HEALTHY)
    assert total == 0
    assert "0 drops, 0 insert_failed" in evidence


def test_conntrack_drops_summed_across_cpus():
    total, evidence = _parse_conntrack_drops(_CONNTRACK_DROPS)
    # drop: 42 + 18 = 60; insert_failed: 3 + 1 = 4; total: 64
    assert total == 64
    assert "60 drops" in evidence
    assert "4 insert_failed" in evidence


# ---------------------------------------------------------------------------
# Prober attribution logic — mocking the host_netns runner
# ---------------------------------------------------------------------------


def _bridge_hop() -> Hop:
    return Hop(node="docker_open5gs_default", kind="docker_bridge",
               iface="br-docker_open5gs")


def _patch_host_netns(monkeypatch, responder):
    """Replace _run_in_host_netns with a stub that delegates to
    `responder(cmd) -> (rc, output)` so we can drive the prober without
    actually entering a network namespace."""
    from agentic_ops_common.path_walk.probers import docker_bridge

    async def _stub(cmd: str) -> tuple[int, str]:
        result = responder(cmd)
        return result

    monkeypatch.setattr(docker_bridge, "_run_in_host_netns", _stub)


def test_bridge_prober_clean_when_no_drops(monkeypatch):
    def responder(cmd: str) -> tuple[int, str]:
        if "iptables" in cmd:
            return (0, _IPTABLES_FORWARD_NO_DROPS)
        if "conntrack" in cmd:
            return (0, _CONNTRACK_HEALTHY)
        if "bridge" in cmd:
            return (0, "1: br-test state forwarding")
        raise AssertionError(f"unexpected: {cmd}")

    _patch_host_netns(monkeypatch, responder)

    prober = DockerBridgeProber()
    attribution = asyncio.run(prober.probe(_bridge_hop(), 5, None))
    assert attribution.kind == "clean"


def test_bridge_prober_attributes_iptables_drop(monkeypatch):
    def responder(cmd: str) -> tuple[int, str]:
        if "iptables" in cmd:
            return (0, _IPTABLES_FORWARD_RANDOM_DROP)
        if "conntrack" in cmd:
            return (0, _CONNTRACK_HEALTHY)
        raise AssertionError(f"unexpected: {cmd}")

    _patch_host_netns(monkeypatch, responder)

    prober = DockerBridgeProber()
    attribution = asyncio.run(prober.probe(_bridge_hop(), 5, None))
    assert attribution.kind == "drops_attributed_here"
    assert isinstance(attribution, DropsAttributedHere)
    assert attribution.counter_kind == "iptables_drop"
    assert attribution.dropped_pkts == 18


def test_bridge_prober_attributes_conntrack_drop(monkeypatch):
    def responder(cmd: str) -> tuple[int, str]:
        if "iptables" in cmd:
            return (0, _IPTABLES_FORWARD_NO_DROPS)
        if "conntrack" in cmd:
            return (0, _CONNTRACK_DROPS)
        if "bridge" in cmd:
            return (0, "ok")
        raise AssertionError(f"unexpected: {cmd}")

    _patch_host_netns(monkeypatch, responder)

    prober = DockerBridgeProber()
    attribution = asyncio.run(prober.probe(_bridge_hop(), 5, None))
    assert attribution.kind == "drops_attributed_here"
    assert isinstance(attribution, DropsAttributedHere)
    assert attribution.counter_kind == "conntrack_drop"
    assert attribution.dropped_pkts == 64


def test_bridge_prober_inconclusive_when_iptables_missing(monkeypatch):
    def responder(cmd: str) -> tuple[int, str]:
        if "iptables" in cmd:
            return (1, "iptables: command not found")
        raise AssertionError(f"unexpected: {cmd}")

    _patch_host_netns(monkeypatch, responder)

    prober = DockerBridgeProber()
    attribution = asyncio.run(prober.probe(_bridge_hop(), 5, None))
    assert attribution.kind == "inconclusive"
    assert isinstance(attribution, InconclusiveHop)
    assert attribution.reason == "tool_unavailable"


def test_bridge_prober_clean_when_conntrack_missing_but_iptables_clean(monkeypatch):
    """conntrack is optional — its absence shouldn't flip the verdict
    to inconclusive when iptables already reported clean."""
    def responder(cmd: str) -> tuple[int, str]:
        if "iptables" in cmd:
            return (0, _IPTABLES_FORWARD_NO_DROPS)
        if "conntrack" in cmd:
            return (1, "conntrack: command not found")
        if "bridge" in cmd:
            return (0, "ok")
        raise AssertionError(f"unexpected: {cmd}")

    _patch_host_netns(monkeypatch, responder)

    prober = DockerBridgeProber()
    attribution = asyncio.run(prober.probe(_bridge_hop(), 5, None))
    assert attribution.kind == "clean"


def test_bridge_prober_rejects_wrong_hop_kind(monkeypatch):
    def responder(cmd: str) -> tuple[int, str]:
        raise AssertionError("should not call host netns for wrong-kind hop")

    _patch_host_netns(monkeypatch, responder)

    prober = DockerBridgeProber()
    bad_hop = Hop(node="rtpengine", kind="container", iface="eth0")
    attribution = asyncio.run(prober.probe(bad_hop, 5, None))
    assert attribution.kind == "inconclusive"
    assert isinstance(attribution, InconclusiveHop)
    assert attribution.reason == "unsupported_hop_kind"
