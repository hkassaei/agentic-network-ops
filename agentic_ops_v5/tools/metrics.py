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


async def query_prometheus(query: str) -> str:
    """Query Prometheus for 5G core NF metrics using PromQL.

    Args:
        query: PromQL query string.
    """
    return await _t.query_prometheus(_get_deps(), query)
