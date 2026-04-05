"""VoNR scope — components relevant to VoNR evaluation.

Queries the ontology for the set of containers that participate in the
VoNR signaling or data path (where `use_cases.vonr.enabled: true`).
Automatically excludes observability (Grafana, Prometheus), management
UIs (WebUI), and unused NFs (BSF, NSSF, SMSC).

RCA agents should use this tool to determine which containers to
actually evaluate — the state of excluded containers must NOT affect
the network health assessment.
"""

from __future__ import annotations
import json as _json


async def get_vonr_components() -> str:
    """Get the list of components in scope for VoNR RCA evaluation.

    Returns only containers where the ontology marks
    `use_cases.vonr.enabled: true`. Components EXCLUDED from the result
    (e.g. Grafana, Prometheus, WebUI, BSF, NSSF, SMSC) are observability
    or unused NFs — their health MUST NOT affect any layer rating.

    Use this tool at the start of every investigation to establish
    the set of containers you should actually consider.

    Returns a JSON list where each entry has:
      - name: container name (use this for tool calls)
      - label: display name
      - layer: infrastructure | ran | core | ims | ue
      - role: functional role
      - note: ontology rationale for VoNR participation
    """
    try:
        from network_ontology.query import OntologyClient
        client = OntologyClient()
        components = client.get_vonr_components()
        client.close()
        return _json.dumps(components, indent=2, default=str)
    except ImportError:
        return "ERROR: network_ontology package not installed."
    except Exception as e:
        return f"ERROR: VoNR scope query failed: {e}"
