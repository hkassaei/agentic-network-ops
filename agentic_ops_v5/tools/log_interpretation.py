"""Log interpretation — semantic meaning of log messages from the ontology."""

from __future__ import annotations
import json as _json


async def interpret_log_message(message: str, source: str = "") -> str:
    """Look up the semantic meaning of a log message in the network ontology.

    Returns matching patterns with actual meaning, common misinterpretations,
    and diagnostic implications.

    Args:
        message: The log message text to interpret.
        source: Optional container name that produced the log (e.g. "amf", "icscf").
    """
    try:
        from network_ontology.query import OntologyClient
        client = OntologyClient()
        matches = client.interpret_log(message, source=source or None)
        client.close()
        if not matches:
            return "No matching log pattern found in ontology."
        results = []
        for m in matches:
            results.append({
                "pattern": m.get("pattern"),
                "meaning": m.get("meaning"),
                "is_benign": m.get("is_benign", False),
                "does_NOT_mean": m.get("does_not_mean", []),
                "actual_implication": m.get("actual_implication", ""),
            })
        return _json.dumps(results, indent=2, default=str)
    except ImportError:
        return "ERROR: network_ontology package not installed."
    except Exception as e:
        return f"ERROR: Log interpretation failed: {e}"
