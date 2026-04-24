"""Causal reasoning — failure chain lookup from the ontology.

Every causal chain exposes a "branch-first" structure:

- `observable_symptoms.immediate`: direct signals (container state,
  metric values) that fire within seconds of the root-cause failure.
- `observable_symptoms.cascading`: a list of **named branches**, each
  describing one downstream consequence path. Each branch carries:
    - `branch`: a short id for the path (e.g. `pcscf_n5_call_setup`,
      `hss_cx_unaffected`).
    - `condition` / `effect`: when the path fires and what it does.
    - `mechanism`: the actual code/protocol mechanism (grounded in
      our repo's Kamailio routes and Open5GS source).
    - `source_steps`: specific `flow_id.step_N` references into
      `flows.yaml` — call `get_flow(flow_id)` to see the step's
      failure_modes.
    - `observable_metrics`: concrete metrics that should deviate
      when this branch is firing.
    - `discriminating_from` (optional): how to tell this branch
      apart from a sibling branch with similar-looking symptoms.

**Negative branches are first-class.** A branch named like
`hss_cx_unaffected`, `data_plane_unaffected_during_blip`, or
`cx_unaffected` is an explicit anti-hallucination rule: it states
that a plausible-looking consequence does NOT actually follow, and
why. Treat negative branches as authoritative rule-outs.
"""

from __future__ import annotations
import json as _json


async def get_causal_chain(chain_id: str) -> str:
    """Get a specific causal failure chain by ID from the ontology.

    Returns a JSON object with chain metadata plus
    `observable_symptoms.{immediate,cascading}`, where cascading is
    the branch list described in the module docstring. Also includes
    the structured `diagnostic_approach` (list of tool-invocation
    hints) and, where authored, `hypothesis_testing`,
    `convergence_point`, and `does_not_mean`.

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

    Output shape is a list of chain objects with the same branch-first
    structure as `get_causal_chain`.

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


async def find_chains_by_observable_metric(metric: str) -> str:
    """Reverse lookup: find every causal-chain branch whose
    `observable_metrics` lists the given metric (or substring).

    Use this for "I see metric X deviating — which branches would
    produce that?" instead of scanning all chains manually. Substring
    match is case-insensitive, so either a bare name
    (`pcscf_sip_error_ratio`) or a qualified one
    (`derived.pcscf_sip_error_ratio`) works.

    Returns a JSON list where each entry carries the parent
    `chain_id`, the `branch` name, the `mechanism`, the branch's
    full `observable_metrics` list, and any `flow_steps` (resolved
    from `source_steps`) the branch is anchored to.

    Args:
        metric: A metric name or substring (e.g.
                `pcscf_sip_error_ratio`, `cdp:timeout`, `ran_ue`).
    """
    try:
        from network_ontology.query import OntologyClient
        client = OntologyClient()
        rows = client.find_chains_by_observable_metric(metric)
        client.close()
        if not rows:
            return (
                f"No causal-chain branches list '{metric}' as an observable. "
                "If you expected a match, try a bare metric name without the "
                "`derived.` prefix or check the spelling."
            )
        return _json.dumps(rows, indent=2, default=str)
    except ImportError:
        return "ERROR: network_ontology package not installed."
    except Exception as e:
        return f"ERROR: Reverse-lookup query failed: {e}"
