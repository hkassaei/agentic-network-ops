"""Path-walk types and the HopProber protocol.

Per ADR `path_anchored_probe_planning_for_transport_layer_faults.md`,
the path-walk machinery localizes transport-layer faults by walking
the implicated topology in order and asking each hop's native
telemetry "did packets die here?"

This module defines the contract every prober implements and the
structured types the walker emits. Probers live in
`agentic_ops_common.path_walk.probers.*`; the walker (in
`agentic_ops_v7`) consumes them through the `HopProber` Protocol so
new hop kinds (SNMP, IPsec, optical, etc.) slot in without redesigning
the walker.

The contract:

    HopProber.probe(hop, window_seconds, anchor_ts) -> HopAttribution

Implementations:
    KernelHopProber    — `container`, `host_kernel`
    DockerBridgeProber — `docker_bridge`
    (future)           — `l2_switch`, `l3_router`, `vpn_gateway`,
                         `optical_segment`, `transit_segment`,
                         `firewall`, `load_balancer`, ...

`HopAttribution` is a closed enum (encoded as a discriminated union of
dataclasses + a `kind` literal). Anything outside the enum is a bug;
the walker rejects it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional, Protocol, Union, runtime_checkable


# ---------------------------------------------------------------------------
# Hop — a single point on the implicated topology
# ---------------------------------------------------------------------------

# Hop kinds the walker knows about. Lab implementations cover
# `container`, `host_kernel`, and `docker_bridge`. Carrier-grade
# kinds are reserved here so the registry's typing stays accurate
# even before a prober for that kind exists.
HopKind = Literal[
    # Lab
    "container",
    "host_kernel",
    "docker_bridge",
    # Carrier-grade (probers TBD per follow-up ADRs)
    "l2_switch",
    "l3_router",
    "wan_edge",
    "vpn_gateway",
    "optical_segment",
    "transit_segment",
    "firewall",
    "load_balancer",
    "dpi",
]


@dataclass(frozen=True)
class Hop:
    """One point on the implicated topology.

    `node` is the addressable identifier (container name, switch
    hostname, IPsec gateway id, etc.). `iface` is the interface or
    port at this hop; for kernel hops it's `eth0` etc., for switches
    it's a port like `eth1/3`, for vpn_gateway it might be the SA id.
    `metadata` carries hop-kind-specific extras (vendor, model,
    remote-AS, anything the prober wants).
    """
    node: str
    kind: HopKind
    iface: str = "eth0"
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# HopAttribution — closed enum of per-hop probe outcomes
# ---------------------------------------------------------------------------

# `compared_to_expected` semantics in the v6 Investigator are LLM-driven and
# can mis-read absent counters. The path walk's attributions are emitted by
# Python from structured counter reads; they are never AMBIGUOUS by accident.

@dataclass(frozen=True)
class CleanHop:
    """No drops, no errors, no anomalous latency at this hop."""
    kind: Literal["clean"] = "clean"
    evidence: str = ""


@dataclass(frozen=True)
class DropsAttributedHere:
    """Exact drop attribution at this hop's own counter.

    `counter_kind` says which native telemetry surfaced the drops:
        qdisc_netem    — `tc -s qdisc show` reports a netem qdisc
                          with non-zero `dropped`.
        qdisc_tbf      — same, but tbf rate-cap drops.
        qdisc_other    — some other qdisc with non-zero drops.
        iface_dropped  — `ip -s link show` TX/RX dropped > 0 with
                          no qdisc-level explanation.
        iface_error    — TX/RX errors > 0 (NIC-level fault).
        iptables_drop  — bridge-prober found an iptables rule with
                          packet count > 0 attributing to this hop.
        switch_discard — SNMP `ifInDiscards` / `ifOutDiscards` > 0.
        ipsec_replay   — IPsec SA's replay-failure counter advanced.
        optical_ber    — BER past threshold on this OCh.
        ...
    """
    counter_kind: str
    dropped_pkts: int
    dropped_pct: Optional[float]
    evidence: str  # verbatim counter excerpt
    kind: Literal["drops_attributed_here"] = "drops_attributed_here"


@dataclass(frozen=True)
class DropsAttributedToInboundLink:
    """Loss attributed to the link entering this hop.

    Used when the prober for hop N+1 reports clean local counters
    but TX(hop_N) > RX(hop_N+1) over the same window. The loss is
    on the link, not at either endpoint.
    """
    observed_loss_pct: float
    tx_rate: float
    rx_rate: float
    evidence: str
    kind: Literal["drops_attributed_to_inbound_link"] = "drops_attributed_to_inbound_link"


@dataclass(frozen=True)
class LatencyAtHop:
    """Anomalous queueing or processing latency at this hop.

    Sibling of `DropsAttributedHere` for `netem delay` and
    rate-cap-induced queueing. `observed_delay_ms` is the qdisc's
    authored delay (for tc netem) or the measured queueing delay.
    """
    observed_delay_ms: float
    counter_kind: str  # "qdisc_netem_delay" | "iface_queue_depth" | ...
    evidence: str
    kind: Literal["latency_at_hop"] = "latency_at_hop"


@dataclass(frozen=True)
class InconclusiveHop:
    """Probe could not run.

    `reason` carries the structured cause: `tool_unavailable`
    (binary missing per the toolbelt ADR), `container_absent`,
    `network_namespace_unreachable`, `snmp_unreachable`, etc.
    The walker surfaces this in the report; it never silently
    rebrands as `clean`.
    """
    reason: str
    detail: str = ""
    kind: Literal["inconclusive"] = "inconclusive"


HopAttribution = Union[
    CleanHop,
    DropsAttributedHere,
    DropsAttributedToInboundLink,
    LatencyAtHop,
    InconclusiveHop,
]


# ---------------------------------------------------------------------------
# PathWalkReport — the walker's structured output
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HopRecord:
    """Per-hop record. `hop` is the topology entry; `attribution`
    is the prober's verdict; `prober` names the implementation that
    produced it (for traceability)."""
    hop: Hop
    attribution: HopAttribution
    prober: str  # e.g. "KernelHopProber"


@dataclass(frozen=True)
class PathWalkReport:
    """Structured output of one path-walk investigation.

    Synthesis consumes this directly to emit a `localized` verdict.
    The walker never produces free-text reasoning — every claim in
    the report is backed by a structured `evidence` field on the
    hop attribution.
    """
    flow_id: str
    direction: str  # "uplink" | "downlink" | "both"
    hops: list[HopRecord]
    anchor_ts: Optional[float]
    window_seconds: int

    @property
    def first_attributed_hop(self) -> Optional[HopRecord]:
        """Return the first hop with a drop / latency attribution.

        Topology order. Used by Synthesis to pick the localization
        point. Returns None if the walk found no attributions
        (orchestrator falls back to application-layer pipeline).
        """
        for record in self.hops:
            kind = record.attribution.kind
            if kind in ("drops_attributed_here",
                        "drops_attributed_to_inbound_link",
                        "latency_at_hop"):
                return record
        return None

    @property
    def is_localized(self) -> bool:
        """True iff at least one hop attributed a fault."""
        return self.first_attributed_hop is not None


# ---------------------------------------------------------------------------
# HopProber — the contract
# ---------------------------------------------------------------------------


@runtime_checkable
class HopProber(Protocol):
    """Every prober implementation honors this single-method contract.

    `window_seconds` lets rate-based probes pick their sampling
    window. `anchor_ts` lets time-aware probes anchor at the
    moment the screener flagged the anomaly (per ADR
    `dealing_with_temporality_3.md`); pass None for live-mode probes.

    The Protocol is `runtime_checkable` so the registry can
    `isinstance(prober, HopProber)` at startup as a defence against
    a future prober class missing the method.
    """

    async def probe(
        self,
        hop: Hop,
        window_seconds: int,
        anchor_ts: Optional[float],
    ) -> HopAttribution:
        ...

    @property
    def supported_kinds(self) -> tuple[HopKind, ...]:
        """Hop kinds this prober handles. Used by the registry to
        dispatch and by the protocol-compliance test to assert
        coverage."""
        ...
