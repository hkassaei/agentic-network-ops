"""
Data-path fault primitives — currently just the PMTU black-hole.

Per CDR-0001 §4: compound primitive that lowers the target's interface
MTU AND drops outbound ICMP "fragmentation-needed" replies. Path MTU
Discovery is defeated: large packets are silently lost, the sender
never learns to shrink them. Small packets (RTP voice) pass cleanly.

Heal restores the original MTU and flushes the iptables rule. Both
operations are recorded so heal is idempotent even on partial-injection
states.
"""

from __future__ import annotations

import logging
import re

from ._common import shell, validate_container
from .docker_tools import docker_get_pid

log = logging.getLogger("chaos-tools.datapath")


async def _resolve_pid(container: str) -> int:
    pid = await docker_get_pid(container)
    if pid is None:
        raise RuntimeError(f"Cannot get PID for container '{container}'")
    return pid


def _nsenter(pid: int) -> str:
    if not isinstance(pid, int) or pid <= 0:
        raise ValueError(f"Invalid PID: {pid}")
    return f"sudo nsenter -t {pid} -n"


async def _current_mtu(ns: str, iface: str) -> int | None:
    """Return the current MTU of `iface` inside the netns, or None on error."""
    rc, out = await shell(f"{ns} ip -o link show dev {iface}")
    if rc != 0:
        return None
    m = re.search(r"\bmtu\s+(\d+)", out)
    return int(m.group(1)) if m else None


async def inject_pmtu_blackhole(
    container: str,
    mtu: int = 1280,
    iface: str = "eth0",
) -> dict:
    """Create a PMTU black-hole on the target container's interface.

    Two operations applied as one unit:
      1) Lower the interface MTU.
      2) Drop outbound ICMP `fragmentation-needed` (IPv4) and
         `packet-too-big` (IPv6) so senders never learn to back off.

    Heal restores the original MTU and removes the iptables rules.
    Idempotent: re-running heal after a partial heal succeeds.

    Args:
        container: Target container.
        mtu: New MTU (default 1280 — well below the 1500 baseline,
            and below the ~1240 B SIP-INVITE-with-full-SDP threshold
            so signaling fails but voice RTP passes).
        iface: Interface to modify (default 'eth0').

    Returns:
        {success, mechanism, heal_cmd, pid, detail, original_mtu}
    """
    validate_container(container)
    if mtu < 576 or mtu > 9000:
        raise ValueError(f"mtu must be 576-9000, got {mtu}")
    if not re.match(r"^[a-zA-Z0-9_-]+$", iface):
        raise ValueError(f"Invalid iface: {iface!r}")

    pid = await _resolve_pid(container)
    ns = _nsenter(pid)

    # Snapshot original MTU for heal
    original_mtu = await _current_mtu(ns, iface)
    if original_mtu is None:
        return {
            "success": False,
            "mechanism": f"{ns} ip -o link show dev {iface}",
            "heal_cmd": "true",
            "detail": f"Could not read original MTU on {iface}",
        }

    # Step 1: lower MTU. Step 2: drop ICMP frag-needed (v4) +
    # packet-too-big (v6). Chained with `&&` — all-or-nothing.
    inject_steps = [
        f"{ns} ip link set dev {iface} mtu {mtu}",
        f"{ns} iptables -A OUTPUT -p icmp --icmp-type fragmentation-needed -j DROP",
        # IPv6 drop is best-effort — some kernels don't have ip6tables loaded
        f"{ns} sh -c 'ip6tables -A OUTPUT -p icmpv6 --icmpv6-type packet-too-big -j DROP 2>/dev/null || true'",
    ]
    mechanism = " && ".join(inject_steps)

    # Heal: reverse both operations. Use `|| true` on iptables -D so heal
    # is idempotent if the rule isn't actually present (e.g. partial inject).
    heal_steps = [
        f"{ns} ip link set dev {iface} mtu {original_mtu}",
        f"{ns} sh -c 'iptables -D OUTPUT -p icmp --icmp-type fragmentation-needed -j DROP 2>/dev/null || true'",
        f"{ns} sh -c 'ip6tables -D OUTPUT -p icmpv6 --icmpv6-type packet-too-big -j DROP 2>/dev/null || true'",
    ]
    heal_cmd = " && ".join(heal_steps)

    rc, output = await shell(mechanism)
    return {
        "success": rc == 0,
        "mechanism": mechanism,
        "heal_cmd": heal_cmd,
        "pid": pid,
        "detail": f"MTU {original_mtu} → {mtu} on {iface}; ICMP frag-needed dropped. {output}",
        "original_mtu": original_mtu,
    }


async def verify_pmtu_blackhole(
    container: str,
    iface: str = "eth0",
    expected_mtu: int = 1280,
) -> dict:
    """Verify both PMTU black-hole components are in place.

    Checks:
      1) Interface MTU equals expected_mtu.
      2) iptables OUTPUT chain contains the ICMP frag-needed DROP rule.

    Returns {verified, detail, current_mtu, ipt_rule_present}.
    """
    validate_container(container)
    pid = await _resolve_pid(container)
    ns = _nsenter(pid)

    current_mtu = await _current_mtu(ns, iface)
    rc, ipt_out = await shell(f"{ns} iptables -S OUTPUT")
    ipt_rule_present = (
        rc == 0 and "icmp-type fragmentation-needed" in ipt_out and "DROP" in ipt_out
    )

    verified = current_mtu == expected_mtu and ipt_rule_present
    detail = (
        f"MTU on {iface}: {current_mtu} (expected {expected_mtu}); "
        f"iptables drop rule present: {ipt_rule_present}"
    )
    return {
        "verified": verified,
        "detail": detail,
        "current_mtu": current_mtu,
        "ipt_rule_present": ipt_rule_present,
    }
