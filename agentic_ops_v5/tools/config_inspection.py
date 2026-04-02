"""Config inspection — read config files from repo or running containers."""

from __future__ import annotations
from ._common import _t, _get_deps


async def read_config(component: str) -> str:
    """Read the configuration file for a network component from the repo.

    Args:
        component: One of: amf, smf, upf, pcscf, scscf, icscf, pyhss,
                   dns, dns-ims-zone, ueransim-gnb, ueransim-ue.
    """
    return await _t.read_config(_get_deps(), component)


async def read_running_config(container: str, grep: str | None = None) -> str:
    """Read the ACTUAL config from a running container (not the repo copy).

    Args:
        container: Container name (pcscf, icscf, scscf, amf, smf, upf).
        grep: Optional pattern to filter config lines (case-insensitive).
              ALWAYS use grep to avoid dumping entire config files.
    """
    return await _t.read_running_config(_get_deps(), container, grep)


async def read_env_config() -> str:
    """Read network topology, IPs, PLMN, and UE credentials from environment files."""
    return await _t.read_env_config(_get_deps())
