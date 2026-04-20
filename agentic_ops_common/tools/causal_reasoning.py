"""Causal reasoning — failure chain lookup from the ontology."""

from __future__ import annotations
import json as _json


async def get_causal_chain(chain_id: str) -> str:
    """Get a specific causal failure chain by ID from the ontology.

    Args:
        chain_id: Chain ID (e.g. "n2_connectivity_loss", "hss_unreachable").
    """
    try:
        from network_ontology.query import OntologyClient
        client = OntologyClient()
        chain = client.get_causal_chain(chain_id)
        client.close()
        if not chain:
            return f"No causal chain found with ID '{chain_id}'."
        return _json.dumps(chain, indent=2, default=str)
    except ImportError:
        return "ERROR: network_ontology package not installed."
    except Exception as e:
        return f"ERROR: Causal chain query failed: {e}"


async def get_causal_chain_for_component(component: str) -> str:
    """Get all causal failure chains triggered by a specific component failure.

    Args:
        component: Component name (e.g. "nr_gnb", "upf", "pcscf", "pyhss").
    """
    try:
        from network_ontology.query import OntologyClient
        client = OntologyClient()
        chains = client.get_causal_chain_for_component(component)
        client.close()
        if not chains:
            return f"No causal chains found for component '{component}'."
        return _json.dumps(chains, indent=2, default=str)
    except ImportError:
        return "ERROR: network_ontology package not installed."
    except Exception as e:
        return f"ERROR: Causal chain query failed: {e}"
