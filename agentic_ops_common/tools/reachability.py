"""Reachability — RTT measurement, listener checks, traffic control inspection."""

from __future__ import annotations
from ._common import _t, _get_deps


async def measure_rtt(container: str, target_ip: str) -> str:
    """Measure round-trip time (RTT) from a container to a target IP.

    Normal Docker bridge RTT is <1ms. Elevated RTT (>10ms) indicates
    abnormal latency or congestion.

    Compositional structure of the reading. A measure_rtt result is a
    function of the source container's networking stack, every link
    and intermediate hop on the path, and the target container's
    networking stack. A deviation from healthy (elevated latency or
    packet loss) is the sum of contributions from every element on
    that path — the reading alone is structurally ambiguous about
    which element produced it.

    Disambiguation requires a comparison. To attribute a deviation
    to a specific element, take a second measurement whose path
    shares some elements with the first and differs in others.
    Elements common to both paths cancel out of the comparison; the
    differing elements are what the comparison localizes. Without
    such a comparison, a single reading cannot, in general, name the
    responsible element.

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
