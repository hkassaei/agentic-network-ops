"""Symptom matching — match observations against ontology failure signatures and stack rules."""

from __future__ import annotations
import json as _json


async def match_symptoms(observations_json: str) -> str:
    """Match observed metrics/symptoms against known failure signatures in the ontology.

    Args:
        observations_json: JSON string with observed state. Example:
            '{"ran_ue": 0, "gnb": 0, "fivegs_smffunction_sm_sessionnbr": 4}'
    """
    try:
        observations = _json.loads(observations_json)
    except _json.JSONDecodeError:
        return "ERROR: observations_json must be valid JSON"
    try:
        from network_ontology.query import OntologyClient
        client = OntologyClient()
        matches = client.match_symptoms(observations)
        client.close()
        return _json.dumps(matches, indent=2, default=str)
    except ImportError:
        return "ERROR: network_ontology package not installed."
    except Exception as e:
        return f"ERROR: Symptom matching failed: {e}"


async def check_stack_rules(observations_json: str) -> str:
    """Check which protocol stack rules are triggered by current observations.

    Args:
        observations_json: JSON string of current observations.
    """
    try:
        observations = _json.loads(observations_json)
    except _json.JSONDecodeError:
        return "ERROR: observations_json must be valid JSON"
    try:
        from network_ontology.query import OntologyClient
        client = OntologyClient()
        rules = client.check_stack_rules(observations)
        client.close()
        return _json.dumps(rules, indent=2, default=str)
    except ImportError:
        return "ERROR: network_ontology package not installed."
    except Exception as e:
        return f"ERROR: Stack rules check failed: {e}"


async def compare_to_baseline(component: str, metrics_json: str) -> str:
    """Compare current metrics to the ontology baseline for a component.

    Returns only anomalies — metrics that deviate from expected values.

    Args:
        component: Component name (e.g. "amf", "upf", "pcscf").
        metrics_json: JSON string of current metric values, e.g. '{"ran_ue": 0}'.
    """
    try:
        metrics = _json.loads(metrics_json)
    except _json.JSONDecodeError:
        return "ERROR: metrics_json must be valid JSON"
    try:
        from network_ontology.query import OntologyClient
        client = OntologyClient()
        anomalies = client.compare_to_baseline(component, metrics)
        client.close()
        if not anomalies:
            return f"No anomalies detected for {component} — all metrics within baseline."
        return _json.dumps(anomalies, indent=2, default=str)
    except ImportError:
        return "ERROR: network_ontology package not installed."
    except Exception as e:
        return f"ERROR: Baseline comparison failed: {e}"
