"""NF metrics — Prometheus, kamcmd, RTPEngine, PyHSS, MongoDB snapshots."""

from __future__ import annotations
from ._common import _t, _get_deps


async def get_nf_metrics() -> str:
    """Get a full metrics snapshot across ALL network functions in one call.

    Collects from Prometheus (5G core), kamcmd (IMS Kamailio), RTPEngine,
    PyHSS, and MongoDB. This is the 'radiograph' — a quick health overview
    of the entire stack.
    """
    return await _t.get_nf_metrics(_get_deps())


async def query_prometheus(query: str, window_seconds: int | None = None) -> str:
    """Query Prometheus for 5G core NF metrics using PromQL.

    Args:
        query: PromQL query string. If it contains the placeholder token
            `{window}`, it will be substituted with `{window_seconds}s`.
            Example: `rate(rtpengine_packets_total[{window}])` with
            window_seconds=120 becomes `rate(rtpengine_packets_total[120s])`.
        window_seconds: Optional lookback window for rate/range queries.
            A typical starting value is 120 (2 minutes). Widen to 300 or
            900 only if nothing is found. If the query already contains an
            explicit range selector, this parameter is ignored.
    """
    return await _t.query_prometheus(_get_deps(), query, window_seconds=window_seconds)
