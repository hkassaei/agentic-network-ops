"""Subscriber lookup — query 5G core (MongoDB) and IMS (PyHSS) subscriber data."""

from __future__ import annotations
from ._common import _t, _get_deps


async def query_subscriber(imsi: str, domain: str = "both") -> str:
    """Query subscriber data from 5G core (MongoDB) and/or IMS (PyHSS).

    Args:
        imsi: The subscriber's IMSI (e.g. '001011234567891').
        domain: 'core' for 5G only, 'ims' for IMS only, 'both' for both.
    """
    return await _t.query_subscriber(_get_deps(), imsi, domain)
