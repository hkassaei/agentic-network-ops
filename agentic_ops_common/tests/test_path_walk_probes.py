"""Path-walk probe wrapper parsers.

Tests the structured-output parsers in `agentic_ops/tools.py`:
    _parse_qdisc_kind, _parse_qdisc_pkt_counters,
    _parse_netem_loss_pct, _parse_netem_delay_ms,
    _parse_ip_link_stats_block

These are pure functions over text, so we test them directly with
fixture command outputs. The end-to-end probe (which docker-execs
into a real container) is verified by the Phase 1.11 integration
runbook against the live lab; that runbook isn't a unit test.

Per Phase 1 of ADR `path_anchored_probe_planning_for_transport_layer_faults.md`.
"""

from __future__ import annotations

import pytest

from agentic_ops.tools import (
    _parse_ip_link_stats_block,
    _parse_netem_delay_ms,
    _parse_netem_loss_pct,
    _parse_qdisc_kind,
    _parse_qdisc_pkt_counters,
)


# ---------------------------------------------------------------------------
# tc qdisc parsers
# ---------------------------------------------------------------------------


_TC_NETEM_LOSS_30 = """\
qdisc netem 8001: root refcnt 2 limit 1000 loss 30%
 Sent 6240 bytes 65 pkt (dropped 18, overlimits 0 requeues 0)
 backlog 0b 0p requeues 0
"""

_TC_NETEM_DELAY_100 = """\
qdisc netem 8001: root refcnt 2 limit 1000 delay 100.0ms
 Sent 6240 bytes 65 pkt (dropped 0, overlimits 0 requeues 0)
 backlog 0b 0p requeues 0
"""

_TC_TBF_RATE_CAP = """\
qdisc tbf 8002: root refcnt 2 rate 100Kbit burst 32Kb lat 400.0ms
 Sent 1024 bytes 12 pkt (dropped 4, overlimits 4 requeues 0)
 backlog 0b 0p requeues 0
"""

_TC_FQ_CODEL_HEALTHY = """\
qdisc fq_codel 0: root refcnt 2 limit 10240p flows 1024 quantum 1514 target 5.0ms
 Sent 1234567 bytes 8192 pkt (dropped 0, overlimits 0 requeues 0)
 backlog 0b 0p requeues 0
  maxpacket 256 drop_overlimit 0 new_flow_count 1 ecn_mark 0
  new_flows_len 0 old_flows_len 0
"""

_TC_NOQUEUE = """\
qdisc noqueue 0: root refcnt 2
"""


def test_parse_qdisc_kind_netem():
    assert _parse_qdisc_kind(_TC_NETEM_LOSS_30) == "netem"


def test_parse_qdisc_kind_tbf():
    assert _parse_qdisc_kind(_TC_TBF_RATE_CAP) == "tbf"


def test_parse_qdisc_kind_fq_codel():
    assert _parse_qdisc_kind(_TC_FQ_CODEL_HEALTHY) == "fq_codel"


def test_parse_qdisc_kind_noqueue():
    assert _parse_qdisc_kind(_TC_NOQUEUE) == "noqueue"


def test_parse_qdisc_kind_unknown_when_no_qdisc_line():
    assert _parse_qdisc_kind("nothing here") == "unknown"


def test_parse_qdisc_pkt_counters_netem_drops():
    sent, dropped = _parse_qdisc_pkt_counters(_TC_NETEM_LOSS_30)
    assert sent == 65
    assert dropped == 18


def test_parse_qdisc_pkt_counters_tbf_drops():
    sent, dropped = _parse_qdisc_pkt_counters(_TC_TBF_RATE_CAP)
    assert sent == 12
    assert dropped == 4


def test_parse_qdisc_pkt_counters_clean():
    sent, dropped = _parse_qdisc_pkt_counters(_TC_FQ_CODEL_HEALTHY)
    assert sent == 8192
    assert dropped == 0


def test_parse_qdisc_pkt_counters_returns_zeros_on_unrecognized_output():
    """If the `Sent N bytes M pkt (dropped K, ...)` line is missing
    (e.g. noqueue qdisc, or root output), return (0, 0)."""
    sent, dropped = _parse_qdisc_pkt_counters(_TC_NOQUEUE)
    assert (sent, dropped) == (0, 0)


def test_parse_netem_loss_pct():
    assert _parse_netem_loss_pct(_TC_NETEM_LOSS_30) == 0.30


def test_parse_netem_loss_pct_none_when_no_loss_param():
    assert _parse_netem_loss_pct(_TC_NETEM_DELAY_100) is None


def test_parse_netem_loss_pct_none_for_non_netem_qdisc():
    assert _parse_netem_loss_pct(_TC_TBF_RATE_CAP) is None


def test_parse_netem_delay_ms_from_canonical_ms_format():
    assert _parse_netem_delay_ms(_TC_NETEM_DELAY_100) == 100.0


def test_parse_netem_delay_ms_none_when_no_delay_param():
    assert _parse_netem_delay_ms(_TC_NETEM_LOSS_30) is None


# ---------------------------------------------------------------------------
# Multi-unit delay parsing — regression coverage for the auto-scaling
# behavior of `tc -s qdisc show`.
#
# `tc` auto-picks the time unit (us / ms / s / ns / ps) based on the
# magnitude of the delay (see iproute2's `__print_size_str` in
# lib/utils.c). A regex that hard-codes the `ms` suffix silently
# misses every delay >= 1 second. This was the HSS Unresponsive walker
# failure observed in run_20260512_121509_hss_unresponsive (60-second
# injection on pyhss was shown as `delay 60.0s`, the ms-only regex
# returned None, prober emitted CleanHop).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("raw,expected_ms", [
    # Sub-millisecond
    ("qdisc netem 8001: root refcnt 2 limit 1000 delay 500us", 0.5),
    ("qdisc netem 8001: root refcnt 2 limit 1000 delay 12.5us", 0.0125),
    ("qdisc netem 8001: root refcnt 2 limit 1000 delay 50ns",   5e-05),

    # Canonical millisecond format
    ("qdisc netem 8001: root refcnt 2 limit 1000 delay 100.0ms", 100.0),
    ("qdisc netem 8001: root refcnt 2 limit 1000 delay 100ms",   100.0),
    ("qdisc netem 8001: root refcnt 2 limit 1000 delay 999.9ms", 999.9),

    # Second-scale (the live HSS Unresponsive bug)
    ("qdisc netem 8001: root refcnt 2 limit 1000 delay 1.0s",    1000.0),
    ("qdisc netem 8001: root refcnt 2 limit 1000 delay 1.5s",    1500.0),
    ("qdisc netem 8001: root refcnt 2 limit 1000 delay 60.0s",   60000.0),
    ("qdisc netem 8001: root refcnt 2 limit 1000 delay 60s",     60000.0),

    # Delay with jitter — tc emits a second time value after the main
    # delay (e.g. `delay 100.0ms 25.0ms 50%`). The parser matches the
    # first one (the central delay), not the jitter.
    ("qdisc netem 8001: root refcnt 2 limit 1000 delay 100.0ms 25.0ms 50%", 100.0),
    ("qdisc netem 8001: root refcnt 2 limit 1000 delay 1.5s 100ms 25%",     1500.0),
])
def test_parse_netem_delay_ms_handles_all_tc_units(raw, expected_ms):
    """Pinned regression for the 60-second-injection-as-seconds case
    and all neighboring units the kernel might emit."""
    result = _parse_netem_delay_ms(raw)
    assert result is not None
    assert abs(result - expected_ms) < 1e-9, (
        f"raw={raw!r} expected={expected_ms} got={result}"
    )


def test_parse_netem_delay_ms_live_hss_unresponsive_regression():
    """Direct pin for the failure observed in
    run_20260512_121509_hss_unresponsive: 60-second outbound delay on
    pyhss, shown by `tc` as `delay 60.0s`. Pre-fix parser returned None
    and the walker emitted CleanHop instead of LatencyAtHop. Post-fix
    must return 60000.0."""
    raw = (
        "qdisc netem 800a: root refcnt 9 limit 1000 delay 60.0s\n"
        " Sent 0 bytes 0 pkt (dropped 0, overlimits 0 requeues 0)\n"
        " backlog 0b 0p requeues 0"
    )
    assert _parse_netem_delay_ms(raw) == 60000.0


@pytest.mark.parametrize("raw", [
    "qdisc fq_codel 0: root refcnt 2 limit 10240p flows 1024",
    "qdisc noqueue 0: root refcnt 2",
    "no qdisc here at all",
    "",
    "delay (a generic word)",  # the regex requires a numeric after delay
])
def test_parse_netem_delay_ms_returns_none_on_non_netem_output(raw):
    """Anything that isn't a `delay <number><unit>` shape returns None."""
    assert _parse_netem_delay_ms(raw) is None


# ---------------------------------------------------------------------------
# ip -s link parser
# ---------------------------------------------------------------------------


_IP_LINK_HEALTHY = """\
2: eth0@if152: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc noqueue state UP mode DEFAULT group default
    link/ether 02:42:ac:16:00:1d brd ff:ff:ff:ff:ff:ff link-netnsid 0
    RX:  bytes packets errors dropped  missed   mcast
        12345     678      0       0       0       0
    TX:  bytes packets errors dropped carrier collsns
        67890     123      0       0       0       0
"""

_IP_LINK_TX_DROPPED = """\
2: eth0@if152: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc noqueue state UP mode DEFAULT group default
    link/ether 02:42:ac:16:00:1d brd ff:ff:ff:ff:ff:ff link-netnsid 0
    RX:  bytes packets errors dropped  missed   mcast
        12345     678      0       0       0       0
    TX:  bytes packets errors dropped carrier collsns
        67890     123     12      45       0       0
"""


def test_parse_ip_link_rx_healthy():
    rx_bytes, rx_pkts, rx_errors, rx_dropped = _parse_ip_link_stats_block(_IP_LINK_HEALTHY, "RX")
    assert rx_bytes == 12345
    assert rx_pkts == 678
    assert rx_errors == 0
    assert rx_dropped == 0


def test_parse_ip_link_tx_healthy():
    tx_bytes, tx_pkts, tx_errors, tx_dropped = _parse_ip_link_stats_block(_IP_LINK_HEALTHY, "TX")
    assert tx_bytes == 67890
    assert tx_pkts == 123
    assert tx_errors == 0
    assert tx_dropped == 0


def test_parse_ip_link_tx_with_drops_and_errors():
    tx_bytes, tx_pkts, tx_errors, tx_dropped = _parse_ip_link_stats_block(_IP_LINK_TX_DROPPED, "TX")
    assert tx_bytes == 67890
    assert tx_pkts == 123
    assert tx_errors == 12
    assert tx_dropped == 45


def test_parse_ip_link_returns_zeros_on_missing_block():
    out = _parse_ip_link_stats_block("no rx or tx here", "RX")
    assert out == (0, 0, 0, 0)
