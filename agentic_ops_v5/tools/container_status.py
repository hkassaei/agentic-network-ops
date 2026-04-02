"""Container status — running/exited/absent for all network containers."""

from __future__ import annotations
from ._common import _t, _get_deps


async def get_network_status() -> str:
    """Get the status of all network containers (running/exited/absent).

    Returns JSON with phase ('ready'/'partial'/'down') and per-container status.
    """
    return await _t.get_network_status(_get_deps())
