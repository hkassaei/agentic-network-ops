"""Kamailio state — runtime inspection via kamcmd."""

from __future__ import annotations
from ._common import _t, _get_deps


async def run_kamcmd(container: str, command: str) -> str:
    """Run a kamcmd command inside a Kamailio container to inspect runtime state.

    Args:
        container: Kamailio container ('pcscf', 'icscf', or 'scscf').
        command: kamcmd command. Examples:
            - cdp.list_peers — Diameter peer connections and state
            - ulscscf.showimpu sip:imsi@domain — S-CSCF registration lookup
            - stats.get_statistics all — all stats
    """
    return await _t.run_kamcmd(_get_deps(), container, command)
