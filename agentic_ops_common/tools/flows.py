"""Flow queries — protocol-flow lookup from the ontology.

Pairs with `causal_reasoning.py`: causal chains are the *reverse index*
(symptom → candidate failure) used by NA for hypothesis generation;
flows are the *forward mechanism walk* used by the Investigator for
falsification. Both layers read from the Neo4j-loaded network ontology
(`network_ontology/data/flows.yaml` after re-seeding).

These are thin wrappers over `OntologyClient.get_all_flows`,
`get_flow`, and `get_flows_through_component`. JSON-serialized output
mirrors the shape the causal-chain tools return so agents can consume
both through the same pattern.

See ADR: docs/ADR/flow-based-causal-chain-reasoning.md
"""

from __future__ import annotations

import json as _json


async def list_flows() -> str:
    """List every protocol flow in the ontology.

    Returns a JSON list where each entry has: id, name, use_case,
    display_order, step_count. Use this to discover which flows exist
    before reaching for `get_flow(flow_id)` — the agent should not
    invent flow ids.

    Typical flow ids in this stack: `ue_registration`, `ims_registration`,
    `vonr_call_setup`, `vonr_call_teardown`, `pdu_session_establishment`,
    `ue_deregistration`, `diameter_cx_authentication`.
    """
    try:
        from network_ontology.query import OntologyClient
        client = OntologyClient()
        flows = client.get_all_flows()
        client.close()
        if not flows:
            return "No flows found in the ontology. (Has the ontology been seeded?)"
        return _json.dumps(flows, indent=2, default=str)
    except ImportError:
        return "ERROR: network_ontology package not installed."
    except Exception as e:
        return f"ERROR: Flow listing failed: {e}"


async def get_flow(flow_id: str) -> str:
    """Get a protocol flow with all its ordered steps.

    Each step carries: order, from, to, via, protocol, interface, label,
    description, detail, failure_modes, metrics_to_watch. Use this to
    walk the mechanism of a procedure when verifying a hypothesis — for
    each step, the `failure_modes` enumerate the actual error branches
    the implementation takes, and the `metrics_to_watch` tell you which
    counters / gauges reflect that step's behavior.

    Args:
        flow_id: Flow id from `list_flows()` (e.g. `"vonr_call_setup"`).
    """
    try:
        from network_ontology.query import OntologyClient
        client = OntologyClient()
        flow = client.get_flow(flow_id)
        client.close()
        if not flow:
            return f"No flow found with id '{flow_id}'. Use list_flows() to see available flows."
        return _json.dumps(flow, indent=2, default=str)
    except ImportError:
        return "ERROR: network_ontology package not installed."
    except Exception as e:
        return f"ERROR: Flow query failed: {e}"


async def get_flows_through_component(component: str) -> str:
    """List every flow that passes through a given network function, with step positions.

    Returned entries carry: flow_id, flow_name, step_order, step_label.
    Use this to answer "which procedures touch this NF, and where in
    each procedure?" — i.e. what's downstream (or upstream) if the NF
    fails.

    Args:
        component: Container / NF name (e.g. `"pcscf"`, `"upf"`,
            `"pyhss"`, `"nr_gnb"`). The same name you'd pass to
            `get_network_status` or tool calls.
    """
    try:
        from network_ontology.query import OntologyClient
        client = OntologyClient()
        rows = client.get_flows_through_component(component)
        client.close()
        if not rows:
            return f"No flows found that pass through component '{component}'."
        return _json.dumps(rows, indent=2, default=str)
    except ImportError:
        return "ERROR: network_ontology package not installed."
    except Exception as e:
        return f"ERROR: Flow-through-component query failed: {e}"
