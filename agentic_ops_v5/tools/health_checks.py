"""Health checks — component health protocols and disambiguation from the ontology."""

from __future__ import annotations
import json as _json


async def check_component_health(component: str) -> str:
    """Look up the health check protocol for a component from the ontology.

    Returns probes (ordered cheapest-first), healthy/degraded/down criteria,
    and disambiguation guidance for ambiguous scenarios.

    Args:
        component: Component name (e.g. "amf", "upf", "pcscf", "nr_gnb").
    """
    try:
        from network_ontology.query import OntologyClient
        client = OntologyClient()
        hc = client.get_healthcheck(component)
        client.close()
        if not hc:
            return f"No health check defined for component '{component}'."
        return _json.dumps(hc, indent=2, default=str)
    except ImportError:
        return "ERROR: network_ontology package not installed."
    except Exception as e:
        return f"ERROR: Health check query failed: {e}"


async def get_disambiguation(component: str, scenario: str) -> str:
    """Look up what a health check result means for an ambiguous scenario.

    Use this when symptoms could point to multiple failure modes. The ontology
    tells you: "if component X is healthy, the problem is Y; if unhealthy, the
    problem is Z."

    Args:
        component: Component name (e.g. "amf", "nr_gnb").
        scenario: Description of the ambiguous situation (e.g. "ran_ue = 0").
    """
    try:
        from network_ontology.query import OntologyClient
        client = OntologyClient()
        result = client.get_disambiguation(component, scenario)
        client.close()
        if not result:
            return f"No disambiguation found for {component} in scenario '{scenario}'."
        return _json.dumps(result, indent=2, default=str)
    except ImportError:
        return "ERROR: network_ontology package not installed."
    except Exception as e:
        return f"ERROR: Disambiguation query failed: {e}"
