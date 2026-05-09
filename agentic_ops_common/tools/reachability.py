"""Reachability — RTT measurement, listener checks, traffic control inspection."""

from __future__ import annotations
from ._common import _t, _get_deps


async def measure_rtt(
    container: str,
    target_ip: str,
    loss_threshold: float = 0.10,
) -> str:
    """Measure round-trip time and packet loss from a container to a target IP.

    Normal Docker bridge RTT is <1ms. Elevated RTT (>10ms) indicates
    abnormal latency or congestion.

    Sample size is **derived from `loss_threshold`** so the probe is
    statistically capable of detecting the loss rate it claims to test for.
    Examples: `loss_threshold=0.30` -> 20 packets (~2 s); `0.10` -> 66
    packets (~7 s, default); `0.01` -> 688 packets (~69 s). The previous
    `-c 3` default is gone — see ADR
    `path_anchored_probe_planning_for_transport_layer_faults.md` for why.

    For exact, sample-size-free localization of kernel-level qdisc drops
    on a known path, prefer the path-walk probes
    (`agentic_ops_common.path_walk`) over `measure_rtt`. `measure_rtt` is
    the right tool when the question is "is this end-to-end path lossy at
    >= X%."

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
        loss_threshold: Detection-threshold for loss in (0, 1). Sample size
            is set so the probe almost-never (P <= 0.001) misses a true
            loss rate at or above this threshold. Default 0.10.
    """
    return await _t.measure_rtt(
        _get_deps(), container, target_ip, loss_threshold=loss_threshold,
    )


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


async def get_qdisc_drops(container: str, iface: str = "eth0") -> dict:
    """Read per-qdisc drop counters at a container's interface.

    Wraps `tc -s qdisc show dev <iface>`. For tc-netem `loss N%` faults
    this is the source of truth — exact kernel counter, no statistical
    sampling. Used by path-walk probers for transport-layer fault
    localization.

    Returns a structured dict; see `agentic_ops.tools.get_qdisc_drops`
    for the exact key set.

    Args:
        container: Container name.
        iface:     Interface name (default 'eth0' for the docker_open5gs lab).
    """
    return await _t.get_qdisc_drops(container, iface)


async def get_interface_drops(container: str, iface: str = "eth0") -> dict:
    """Read interface-level RX/TX drop and error counters.

    Wraps `ip -s link show dev <iface>`. Catches drops not associated
    with a qdisc (NIC ring-buffer overrun, transmission errors).

    Returns a structured dict; see `agentic_ops.tools.get_interface_drops`
    for the exact key set.

    Args:
        container: Container name.
        iface:     Interface name (default 'eth0').
    """
    return await _t.get_interface_drops(container, iface)


async def get_link_rate_diff(
    container_a: str,
    iface_a: str,
    container_b: str,
    iface_b: str,
    direction: str = "a_to_b",
    window_seconds: int = 5,
) -> dict:
    """Compare same-direction packet rates at two adjacent hops.

    Used by path-walk probers to attribute loss to a link (rather than
    to either endpoint hop). The implementation samples interface
    counters at t0 and t0+window_seconds and computes per-second rates.
    A meaningful TX > RX delta on the named direction means packets
    were dropped on the link between A and B.

    Returns a structured dict with `tx_rate`, `rx_rate`, `diff`,
    `attributed_loss_pct`, and a verbatim `evidence` string. See
    `agentic_ops.tools.get_link_rate_diff` for the full key set.
    """
    return await _t.get_link_rate_diff(
        container_a, iface_a, container_b, iface_b,
        direction=direction, window_seconds=window_seconds,
    )
