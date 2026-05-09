"""KernelHopProber — extracts transport-layer telemetry from a container's kernel.

For lab `container` hops, this prober runs `tc -s qdisc show` and
`ip -s link show` inside the container's network namespace via
`docker exec` and maps the structured output to a `HopAttribution`.

Attribution rules (in order):

1. **DropsAttributedHere** — `tc -s qdisc show` reports a netem qdisc
   with non-zero `dropped` packets, OR a tbf qdisc with drops, OR an
   interface counter (`rx_dropped`/`tx_dropped`) is non-zero with no
   qdisc explanation. The kernel is the source of truth; this is an
   exact attribution.
2. **LatencyAtHop** — `tc -s qdisc show` reports a netem qdisc with a
   `delay` parameter > 0 (and no drops). Captures injected latency
   faults.
3. **InconclusiveHop** — `tc` or `ip` not present in the container
   (caught by the toolbelt-preflight inside the wrappers), or the
   container is unreachable.
4. **CleanHop** — none of the above fired. The hop's local counters
   show no fault.

This prober deliberately does **not** read application-layer state —
no Kamailio counters, no Diameter session inspection. Those live in
the application-layer pipeline; the path walk's job is to ask the
kernel.

See ADR `path_anchored_probe_planning_for_transport_layer_faults.md`.
"""

from __future__ import annotations

from typing import Optional

from agentic_ops_common.tools.reachability import (
    get_interface_drops,
    get_qdisc_drops,
)

from ..protocol import (
    CleanHop,
    DropsAttributedHere,
    Hop,
    HopAttribution,
    HopKind,
    InconclusiveHop,
    LatencyAtHop,
)


class KernelHopProber:
    """Prober for `container` hop kinds (lab).

    For carrier deployments with bare-metal hosts running NFs, a
    sibling `HostKernelHopProber` would handle the `host_kernel` kind
    by skipping the `docker exec` prefix; that's a follow-up, not part
    of this Phase-1 implementation.
    """

    name = "KernelHopProber"

    @property
    def supported_kinds(self) -> tuple[HopKind, ...]:
        return ("container",)

    async def probe(
        self,
        hop: Hop,
        window_seconds: int,
        anchor_ts: Optional[float],
    ) -> HopAttribution:
        if hop.kind not in self.supported_kinds:
            return InconclusiveHop(
                reason="unsupported_hop_kind",
                detail=(
                    f"KernelHopProber does not handle hop_kind={hop.kind!r}; "
                    f"supported: {self.supported_kinds}"
                ),
            )

        # ---- 1. qdisc inspection ----
        q = await get_qdisc_drops(hop.node, hop.iface)
        if q.get("_error") == "tool_unavailable":
            return InconclusiveHop(
                reason="tool_unavailable",
                detail=(
                    f"required binary '{q.get('missing_binary')}' missing in "
                    f"container '{hop.node}'; see "
                    f"docs/ADR/nf_container_diagnostic_tooling.md"
                ),
            )
        if "_error" in q:
            return InconclusiveHop(
                reason="qdisc_probe_failed",
                detail=str(q.get("_error")),
            )

        qdisc_kind = q["qdisc_kind"]
        dropped_pkts = q["dropped_pkts"]
        sent_pkts = q["sent_pkts"]
        dropped_pct = q["dropped_pct"]
        loss_pct = q["loss_pct"]
        delay_ms = q["delay_ms"]

        # qdisc-level drops — the smoking-gun case for tc-netem loss
        # and tbf rate-cap drops.
        if dropped_pkts > 0:
            counter_kind = (
                "qdisc_netem" if qdisc_kind == "netem"
                else "qdisc_tbf" if qdisc_kind == "tbf"
                else f"qdisc_{qdisc_kind}"
            )
            return DropsAttributedHere(
                counter_kind=counter_kind,
                dropped_pkts=dropped_pkts,
                dropped_pct=dropped_pct,
                evidence=_format_qdisc_evidence(
                    hop, qdisc_kind, sent_pkts, dropped_pkts,
                    dropped_pct, loss_pct, q["raw"],
                ),
            )

        # netem `delay Nms` with no drops — pure latency injection.
        if qdisc_kind == "netem" and delay_ms is not None and delay_ms > 0:
            return LatencyAtHop(
                observed_delay_ms=delay_ms,
                counter_kind="qdisc_netem_delay",
                evidence=_format_qdisc_evidence(
                    hop, qdisc_kind, sent_pkts, dropped_pkts,
                    dropped_pct, loss_pct, q["raw"],
                ),
            )

        # ---- 2. interface-level inspection ----
        iface_stats = await get_interface_drops(hop.node, hop.iface)
        if iface_stats.get("_error") == "tool_unavailable":
            return InconclusiveHop(
                reason="tool_unavailable",
                detail=(
                    f"required binary '{iface_stats.get('missing_binary')}' "
                    f"missing in container '{hop.node}'"
                ),
            )
        if "_error" in iface_stats:
            return InconclusiveHop(
                reason="interface_probe_failed",
                detail=str(iface_stats.get("_error")),
            )

        # Interface-level drops with no qdisc explanation — typically
        # ring-buffer overrun (driver-level).
        if iface_stats["tx_dropped"] > 0 or iface_stats["rx_dropped"] > 0:
            tx_d = iface_stats["tx_dropped"]
            rx_d = iface_stats["rx_dropped"]
            return DropsAttributedHere(
                counter_kind="iface_dropped",
                dropped_pkts=tx_d + rx_d,
                dropped_pct=None,  # ip -s link doesn't give a denominator easily
                evidence=_format_iface_evidence(hop, iface_stats),
            )
        if iface_stats["tx_errors"] > 0 or iface_stats["rx_errors"] > 0:
            tx_e = iface_stats["tx_errors"]
            rx_e = iface_stats["rx_errors"]
            return DropsAttributedHere(
                counter_kind="iface_error",
                dropped_pkts=tx_e + rx_e,
                dropped_pct=None,
                evidence=_format_iface_evidence(hop, iface_stats),
            )

        # ---- 3. clean ----
        return CleanHop(
            evidence=(
                f"{hop.node}[{hop.iface}]: qdisc={qdisc_kind}, "
                f"sent={sent_pkts} dropped=0; "
                f"iface tx_pkts={iface_stats['tx_pkts']} rx_pkts={iface_stats['rx_pkts']} "
                f"tx_err=0 rx_err=0 tx_drop=0 rx_drop=0"
            ),
        )


def _format_qdisc_evidence(
    hop: Hop,
    qdisc_kind: str,
    sent_pkts: int,
    dropped_pkts: int,
    dropped_pct: Optional[float],
    loss_pct: Optional[float],
    raw: str,
) -> str:
    """Render the verbatim tc -s qdisc excerpt for the report.

    The raw output is the kernel's own words; we keep it intact so the
    operator (and future audits) can verify the attribution against the
    source-of-truth without hunting through logs.
    """
    pct_str = f"{dropped_pct * 100:.2f}%" if dropped_pct is not None else "n/a"
    loss_str = f", authored loss={loss_pct * 100:.0f}%" if loss_pct is not None else ""
    return (
        f"{hop.node}[{hop.iface}] qdisc={qdisc_kind}{loss_str}: "
        f"sent={sent_pkts} dropped={dropped_pkts} ({pct_str})\n"
        f"---tc -s qdisc show dev {hop.iface}---\n"
        f"{raw}"
    )


def _format_iface_evidence(hop: Hop, stats: dict) -> str:
    """Render the verbatim ip -s link excerpt for the report."""
    return (
        f"{hop.node}[{hop.iface}] interface counters:\n"
        f"  rx: pkts={stats['rx_pkts']} errors={stats['rx_errors']} "
        f"dropped={stats['rx_dropped']}\n"
        f"  tx: pkts={stats['tx_pkts']} errors={stats['tx_errors']} "
        f"dropped={stats['tx_dropped']}\n"
        f"---ip -s link show dev {hop.iface}---\n"
        f"{stats['raw']}"
    )
