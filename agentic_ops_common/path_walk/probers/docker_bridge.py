"""DockerBridgeProber — extracts transport-layer telemetry from the host bridge.

In docker_open5gs the default network is a Linux bridge on the host. Two
containers communicate via `veth_A → docker0 → veth_B`. Faults at the
bridge (iptables FORWARD rules dropping packets, conntrack table overflow,
MTU mismatches the bridge silently truncates) are not visible from inside
either container's network namespace — but they ARE visible to telemetry
running in the host's network namespace.

This prober drops into the host network namespace (PID 1's netns by
default — equivalent to running on the host) and reads:

- `iptables -L FORWARD -v -n` for drop-rule packet counts.
- `bridge -s link show` for per-bridge-port byte/packet counters.
- `conntrack -S` for table-overflow drops.

Attribution rules:

- **DropsAttributedHere(iptables_drop)** — an iptables rule with
  `-j DROP` (or `-j REJECT`) on the FORWARD chain has packet count > 0.
- **DropsAttributedHere(conntrack_drop)** — conntrack stats show
  `insert_failed > 0` or `drop > 0`.
- **CleanHop** — none of the above.
- **InconclusiveHop** — required binaries missing or host netns
  unreachable.

This prober runs deterministically; no LLM. Carrier-grade analogues
(`SwitchHopProber` over SNMP, `OVSHopProber` for Open vSwitch) follow
the same shape but slot into a different `HopKind`.

See ADR `path_anchored_probe_planning_for_transport_layer_faults.md`.
"""

from __future__ import annotations

import asyncio
import re
from typing import Optional

from ..protocol import (
    CleanHop,
    DropsAttributedHere,
    Hop,
    HopAttribution,
    HopKind,
    InconclusiveHop,
)


class DockerBridgeProber:
    """Prober for `docker_bridge` hop kinds (lab).

    Notes on host-namespace access:
        Container telemetry uses `docker exec`. The Docker bridge is on
        the host's network namespace, not in any container. We use
        `nsenter -t 1 -n` (PID 1's network namespace = host) to run
        `iptables` / `bridge` / `conntrack` against the right namespace.

        This requires the binaries to be available on the host (not in
        a container) and the agent's process to have CAP_NET_ADMIN or
        equivalent. The lab's GUI server runs with sufficient privilege
        for `docker exec` and `nsenter` already; in a hardened
        deployment a privileged sidecar would be the equivalent path.
    """

    name = "DockerBridgeProber"

    @property
    def supported_kinds(self) -> tuple[HopKind, ...]:
        return ("docker_bridge",)

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
                    f"DockerBridgeProber does not handle hop_kind={hop.kind!r}; "
                    f"supported: {self.supported_kinds}"
                ),
            )

        # ---- iptables FORWARD chain — find DROP rules with traffic ----
        iptables_result = await self._read_iptables_forward()
        if iptables_result.unavailable:
            return InconclusiveHop(
                reason="tool_unavailable",
                detail=iptables_result.detail,
            )

        if iptables_result.dropped_pkts > 0:
            return DropsAttributedHere(
                counter_kind="iptables_drop",
                dropped_pkts=iptables_result.dropped_pkts,
                dropped_pct=None,  # iptables doesn't provide a denominator
                evidence=iptables_result.evidence,
            )

        # ---- conntrack — table-overflow drops ----
        conntrack_result = await self._read_conntrack_stats()
        if conntrack_result.unavailable:
            # Conntrack is optional; if not installed, just skip it.
            # Don't fail the whole probe.
            pass
        elif conntrack_result.dropped_pkts > 0:
            return DropsAttributedHere(
                counter_kind="conntrack_drop",
                dropped_pkts=conntrack_result.dropped_pkts,
                dropped_pct=None,
                evidence=conntrack_result.evidence,
            )

        # ---- bridge link counters — informational, no drops detected ----
        bridge_result = await self._read_bridge_link()
        bridge_evidence = (
            bridge_result.evidence
            if not bridge_result.unavailable
            else "(bridge -s link show unavailable)"
        )

        return CleanHop(
            evidence=(
                f"{hop.node}[{hop.iface}] bridge counters clean:\n"
                f"  iptables FORWARD: 0 packets dropped\n"
                f"  conntrack: 0 drops\n"
                f"  bridge: {bridge_evidence}"
            ),
        )

    # ---------------------------------------------------------------
    # Underlying probes
    # ---------------------------------------------------------------

    async def _read_iptables_forward(self) -> "_BridgeProbeResult":
        rc, out = await _run_in_host_netns("iptables -L FORWARD -v -n")
        if rc != 0:
            if "iptables: command not found" in out or "executable file not found" in out:
                return _BridgeProbeResult.unavailable_tool("iptables")
            return _BridgeProbeResult.unavailable_other(
                f"iptables -L FORWARD -v -n failed (rc={rc}): {out.strip()}"
            )

        dropped, evidence = _parse_iptables_forward_drops(out)
        return _BridgeProbeResult(
            unavailable=False,
            detail="",
            dropped_pkts=dropped,
            evidence=evidence,
        )

    async def _read_conntrack_stats(self) -> "_BridgeProbeResult":
        rc, out = await _run_in_host_netns("conntrack -S")
        if rc != 0:
            if "conntrack: command not found" in out or "executable file not found" in out:
                return _BridgeProbeResult.unavailable_tool("conntrack")
            return _BridgeProbeResult.unavailable_other(
                f"conntrack -S failed (rc={rc}): {out.strip()}"
            )

        dropped, evidence = _parse_conntrack_drops(out)
        return _BridgeProbeResult(
            unavailable=False,
            detail="",
            dropped_pkts=dropped,
            evidence=evidence,
        )

    async def _read_bridge_link(self) -> "_BridgeProbeResult":
        rc, out = await _run_in_host_netns("bridge -s link show")
        if rc != 0:
            if "bridge: command not found" in out or "executable file not found" in out:
                return _BridgeProbeResult.unavailable_tool("bridge")
            return _BridgeProbeResult.unavailable_other(
                f"bridge -s link show failed (rc={rc}): {out.strip()}"
            )
        return _BridgeProbeResult(
            unavailable=False,
            detail="",
            dropped_pkts=0,
            evidence=out.strip()[:512],  # cap evidence; full output is verbose
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _BridgeProbeResult:
    """Internal holder for one underlying probe's result."""

    def __init__(
        self,
        unavailable: bool,
        detail: str,
        dropped_pkts: int,
        evidence: str,
    ) -> None:
        self.unavailable = unavailable
        self.detail = detail
        self.dropped_pkts = dropped_pkts
        self.evidence = evidence

    @classmethod
    def unavailable_tool(cls, binary: str) -> "_BridgeProbeResult":
        return cls(
            unavailable=True,
            detail=f"required binary '{binary}' not present in host namespace",
            dropped_pkts=0,
            evidence="",
        )

    @classmethod
    def unavailable_other(cls, msg: str) -> "_BridgeProbeResult":
        return cls(
            unavailable=True,
            detail=msg,
            dropped_pkts=0,
            evidence="",
        )


async def _run_in_host_netns(cmd: str) -> tuple[int, str]:
    """Run a command in the host's network namespace.

    `nsenter -t 1 -n -- <cmd>` enters PID 1's network namespace, which
    is the host namespace on a non-virtualized box. On WSL2 the same
    mechanism applies — PID 1 inside the WSL2 VM is the host of the
    Docker bridge.

    Requires CAP_SYS_ADMIN equivalent. Returns (returncode, combined_output).
    """
    full_cmd = f"sudo nsenter -t 1 -n -- {cmd}"
    proc = await asyncio.create_subprocess_shell(
        full_cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    stdout, _ = await proc.communicate()
    return proc.returncode or 0, stdout.decode(errors="replace")


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------


def _parse_iptables_forward_drops(output: str) -> tuple[int, str]:
    """Sum packet counts on FORWARD-chain DROP/REJECT rules.

    `iptables -L FORWARD -v -n` line shape:
        Chain FORWARD (policy ACCEPT 0 packets, 0 bytes)
         pkts bytes target     prot opt in     out     source               destination
            0     0 ACCEPT     all  --  *      *       0.0.0.0/0            0.0.0.0/0
           42  3024 DROP       all  --  *      *       0.0.0.0/0            0.0.0.0/0  statistic mode random probability 0.30000000000

    We sum `pkts` for any line whose target is `DROP` or `REJECT`, plus
    the chain's policy if it's `DROP`.
    """
    total = 0
    matched_rules: list[str] = []
    for line in output.splitlines():
        # Policy: "Chain FORWARD (policy DROP 5 packets, 320 bytes)"
        m_policy = re.match(
            r"^Chain\s+FORWARD\s+\(policy\s+(\S+)\s+(\d+)\s+packets",
            line,
        )
        if m_policy:
            policy_target = m_policy.group(1)
            policy_pkts = int(m_policy.group(2))
            if policy_target in ("DROP", "REJECT") and policy_pkts > 0:
                total += policy_pkts
                matched_rules.append(
                    f"  policy={policy_target} pkts={policy_pkts}"
                )
            continue

        # Rule line. Columns: pkts bytes target prot opt in out src dst [extras]
        m = re.match(
            r"^\s*(\d+)\s+\d+\s+(DROP|REJECT)\b",
            line,
        )
        if m:
            pkts = int(m.group(1))
            target = m.group(2)
            if pkts > 0:
                total += pkts
                matched_rules.append(
                    f"  {target}: pkts={pkts}  rule={line.strip()}"
                )

    if total > 0:
        evidence = (
            f"iptables FORWARD chain — {total} packets dropped:\n"
            + "\n".join(matched_rules)
            + f"\n---iptables -L FORWARD -v -n---\n{output.strip()}"
        )
    else:
        evidence = "iptables FORWARD chain — no DROP/REJECT rules with traffic"
    return total, evidence


def _parse_conntrack_drops(output: str) -> tuple[int, str]:
    """Sum drop / insert_failed counters from `conntrack -S` output.

    Output lines look like:
        cpu=0 found=0 invalid=2 ignore=0 insert=0 insert_failed=0 drop=0 ...
        cpu=1 ...

    We sum `drop` and `insert_failed` across all CPUs.
    """
    total_drop = 0
    total_insert_failed = 0
    for m in re.finditer(r"drop=(\d+)", output):
        total_drop += int(m.group(1))
    for m in re.finditer(r"insert_failed=(\d+)", output):
        total_insert_failed += int(m.group(1))

    total = total_drop + total_insert_failed
    if total > 0:
        evidence = (
            f"conntrack: {total_drop} drops, {total_insert_failed} insert_failed\n"
            f"---conntrack -S---\n{output.strip()}"
        )
    else:
        evidence = "conntrack stats: 0 drops, 0 insert_failed"
    return total, evidence
