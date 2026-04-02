"""Reachability — RTT measurement, listener checks, traffic control inspection."""

from __future__ import annotations
from ._common import _t, _get_deps


async def measure_rtt(container: str, target_ip: str) -> str:
    """Measure round-trip time (RTT) from a container to a target IP.

    Normal Docker bridge RTT is <1ms. Elevated RTT (>10ms) indicates
    abnormal latency or congestion.

    Args:
        container: Source container name (e.g. 'pcscf', 'icscf').
        target_ip: Target IP address to ping (e.g. '172.22.0.19').
    """
    return await _t.measure_rtt(_get_deps(), container, target_ip)


async def check_process_listeners(container: str) -> str:
    """Check what ports and protocols a container's processes are listening on.

    Args:
        container: Container name (e.g. 'pcscf', 'scscf', 'amf').
    """
    return await _t.check_process_listeners(_get_deps(), container)


async def check_tc_rules(container: str) -> str:
    """Check for active traffic control (tc) rules on a container's network interface.

    Detects injected latency (netem delay), packet loss (netem loss), bandwidth
    limits (tbf), or corruption.

    Args:
        container: Container name (e.g. 'pcscf', 'upf', 'scscf').
    """
    return await _t.check_tc_rules(_get_deps(), container)
