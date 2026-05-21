"""Deployment-config lookup — answer "what port serves X on this NF in this deployment?"

Targeted, structured lookup over the network ontology's deployment
metadata. Use this BEFORE asserting that a service is or is not bound
to a port: deployments routinely diverge from IANA-standard port
assignments, and training-corpus knowledge is not a safe substitute
for the actual configured value.

See ADR `docs/ADR/stack_config_tool_for_agents.md`.
"""

from __future__ import annotations
from ._common import _t, _get_deps


async def get_deployment_config(component: str) -> dict:
    """Return the deployment-configured values for one network component.

    Returns a structured dict:
        {
            "component": "pyhss",
            "container_name": "pyhss",
            "ip": "172.22.0.18",
            "ip_env_key": "PYHSS_IP",
            "listening_ports": [
                {
                    "port": 3875,
                    "transport": "tcp",
                    "purpose": {
                        "protocol": "diameter",
                        "interface": "cx",
                        "role": "server",
                    },
                    "source": "network/.env: PYHSS_BIND_PORT",
                },
                ...
            ],
            "config_files": ["network/.env", "network/pyhss/config.yaml"],
            "ontology_files": [
                "network_ontology/data/deployment.yaml",
                "network_ontology/data/deployment_metadata.yaml",
            ],
        }

    On unknown component: returns `{"_error": "...", "component": "..."}`.

    Whenever you cite a port number, container name, or IP in a
    hypothesis statement or probe interpretation, your reasoning must
    trace back to one of:
      - a `get_deployment_config` call (this tool),
      - a `read_env_config` call,
      - a `read_running_config` call, or
      - a value the probe itself returned.

    IANA-standard port numbers and training-corpus knowledge of
    common protocol bindings are NOT acceptable sources for assertions
    about THIS deployment.

    Args:
        component: Canonical NF name (pyhss, icscf, scscf, pcscf, mongo,
                   mysql, amf, smf, upf, ausf, udm, udr, pcf, nrf, scp,
                   rtpengine, dns, nr_gnb). Case-insensitive.
    """
    return await _t.get_deployment_config(_get_deps(), component)
