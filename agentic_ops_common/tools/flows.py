"""Flow queries — protocol-flow lookup from the ontology.

Two distinct tools, two distinct purposes — see ADR
`flows_tool_deployment_awareness.md`:

  - `get_canonical_flows_through_component(nf)` — STATIC ONTOLOGY LOOKUP.
    Returns reference procedure flows from `network_ontology/data/flows.yaml`
    with per-step failure modes inlined. Useful for hypothesis development
    and probe selection. Does NOT verify whether any returned flow is
    currently active in the deployment.

  - `get_active_flows_through_component(nf, at_time_ts, window_seconds)`
    — DEPLOYMENT-AWARE PROBE. Evaluates each canonical flow's
    `activity_indicator` Prometheus expression over the given window
    and returns the active/inactive partition. Use this when the
    question is "what is *actually* happening through this NF right now."

The previous single tool `get_flows_through_component` was renamed to
`get_canonical_flows_through_component` to make its scope unambiguous in
the agent's tool calls. No alias is provided; the rename is the point.

Pairs with `causal_reasoning.py`: causal chains are the *reverse index*
(symptom → candidate failure) used by NA for hypothesis generation;
flows are the *forward mechanism walk* used by the Investigator for
falsification. Both layers read from the Neo4j-loaded network ontology
(`network_ontology/data/flows.yaml` after re-seeding).
"""

from __future__ import annotations

import json as _json
import logging
from typing import Any

import httpx

_log = logging.getLogger("tools.flows")


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


async def get_canonical_flows_through_component(component: str) -> str:
    """Return canonical procedure flows from the network ontology that
    pass through the given NF.

    SOURCE: network_ontology/data/flows.yaml (static curated KB).
    SCOPE: This is a reference lookup. It does NOT verify whether any
           returned flow is currently active in the deployment. Use
           `get_active_flows_through_component` to determine live
           activity.

    Use this to: enumerate the procedures whose failure modes touch this
    NF, walk each flow's steps and metrics for hypothesis development,
    and identify which observable signals would change at each step.

    Do NOT use this to: claim a flow is currently executing, infer that
    UEs are currently in a specific call state, or assert traffic is
    flowing along a specific path right now. The output's `source` and
    `scope` fields are surfaced on every invocation as a safeguard
    against confusing canonical with live state.

    Output payload shape:
        {
          "source": "network_ontology",
          "scope": "canonical (NOT live deployment state)",
          "component": <nf>,
          "flows": [
            {"flow_id": ..., "flow_name": ..., "step_order": int,
             "step_label": ..., "failure_modes": [...]},
            ...
          ]
        }

    Args:
        component: Container / NF name (e.g. `"pcscf"`, `"upf"`,
            `"pyhss"`, `"nr_gnb"`). The same name you'd pass to
            `get_network_status` or tool calls.
    """
    try:
        from network_ontology.query import OntologyClient
        client = OntologyClient()
        rows = client.get_flows_through_component(component)
        # The Cypher query in OntologyClient does not currently return
        # the per-step failure_modes (it only returns flow_id, flow_name,
        # step_order, step_label). Enrich each row by fetching the
        # corresponding flow and reading the step's failure_modes.
        # Cached per flow_id within this call to avoid N round-trips.
        enriched_rows: list[dict[str, Any]] = []
        flow_cache: dict[str, dict[str, Any] | None] = {}
        for row in rows:
            flow_id = row.get("flow_id")
            if flow_id and flow_id not in flow_cache:
                flow_cache[flow_id] = client.get_flow(flow_id)
            failure_modes: list[str] = []
            flow_obj = flow_cache.get(flow_id) if flow_id else None
            if flow_obj:
                for step in flow_obj.get("steps", []):
                    if step.get("step_order") == row.get("step_order"):
                        fm = step.get("failure_modes") or []
                        # failure_modes may be list[str] or
                        # list[FailureModeStructured-as-dict]; render
                        # as strings for agent readability.
                        for entry in fm:
                            if isinstance(entry, str):
                                failure_modes.append(entry)
                            elif isinstance(entry, dict):
                                fm_id = entry.get("id") or entry.get("description") or _json.dumps(entry)
                                failure_modes.append(str(fm_id))
                            else:
                                failure_modes.append(str(entry))
                        break
            enriched_rows.append({**row, "failure_modes": failure_modes})
        client.close()
        payload = {
            "source": "network_ontology",
            "scope": "canonical (NOT live deployment state)",
            "component": component,
            "flows": enriched_rows,
        }
        if not enriched_rows:
            payload["note"] = (
                f"No flows in the ontology pass through component "
                f"'{component}'. Use list_flows() to see available flows, "
                f"or get_active_flows_through_component to ask which are "
                f"currently active in the deployment."
            )
        return _json.dumps(payload, indent=2, default=str)
    except ImportError:
        return "ERROR: network_ontology package not installed."
    except Exception as e:
        return f"ERROR: Canonical flow lookup failed: {e}"


async def get_active_flows_through_component(
    component: str,
    at_time_ts: float | None = None,
    window_seconds: int = 120,
) -> str:
    """Return canonical flows that are CURRENTLY active in the deployment.

    For each canonical flow that touches the named NF, this tool
    evaluates the flow's `activity_indicator` (a Prometheus expression
    authored in the KB — typically a rate of a specific 5G core counter,
    SIP method, or Diameter command) over the window
    `[at_time_ts - window_seconds, at_time_ts]`. A flow is "active" iff
    the indicator is strictly above its KB-authored `threshold_gt`.

    Output partitions flows three ways:
      - `active_flows`: indicator > threshold in the window.
      - `inactive_flows`: indicator <= threshold in the window.
      - `unknown_flows`: no `activity_indicator` authored in the KB
        for this flow. Reported explicitly so the LLM never reads
        "no activity" when the indicator simply isn't authored in this
        deployment.

    Use this when the question is "what is actually happening through
    this NF right now" — for example, before claiming a specific
    procedure is exhibiting a fault, or when ruling out a hypothesis
    whose flow is not active.

    Args:
        component: Container / NF name (e.g. `"pcscf"`).
        at_time_ts: Optional Unix timestamp to anchor the query at.
            When None (default), Prometheus evaluates "now". When set,
            Prometheus evaluates the rate window ending at that time —
            same anchoring semantics as `get_dp_quality_gauges`. Pass
            the orchestrator's `anomaly_screener_snapshot_ts` to
            anchor on the moment the screener flagged the anomaly.
        window_seconds: Lookback window for each indicator's rate()
            query. Default 120s. Values < 10 are clamped to 10.

    See ADR `flows_tool_deployment_awareness.md`.
    """
    window_seconds = max(10, int(window_seconds))
    try:
        from network_ontology.query import OntologyClient
        client = OntologyClient()
        rows = client.get_flows_through_component(component)
        # Group rows by flow so we can run one Prometheus query per
        # flow (the indicator is per-flow, not per-step).
        steps_by_flow: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            steps_by_flow.setdefault(row["flow_id"], []).append(row)
        # Pull each flow's full body to read the activity_indicator.
        flow_objs: dict[str, dict[str, Any] | None] = {
            fid: client.get_flow(fid) for fid in steps_by_flow
        }
        client.close()
    except ImportError:
        return "ERROR: network_ontology package not installed."
    except Exception as e:
        return f"ERROR: Ontology lookup failed: {e}"

    if not steps_by_flow:
        return _json.dumps({
            "source": "live (Prometheus over window)",
            "scope": "deployment activity",
            "component": component,
            "window_seconds": window_seconds,
            "at_time_ts": at_time_ts,
            "active_flows": [],
            "inactive_flows": [],
            "unknown_flows": [],
            "note": (
                f"No flows in the ontology pass through component "
                f"'{component}'. Use list_flows() to see available flows."
            ),
        }, indent=2, default=str)

    # Resolve Prometheus URL via the same dependency hook the data-plane
    # probe uses, so configuration is centralized.
    try:
        from agentic_ops_common.tools._common import _get_deps
        deps = _get_deps()
        prom_ip = deps.env.get("METRICS_IP", "172.22.0.36")
        prom_url = f"http://{prom_ip}:9090"
    except Exception as e:
        return f"ERROR: Prometheus dependency resolution failed: {e}"

    active_flows: list[dict[str, Any]] = []
    inactive_flows: list[dict[str, Any]] = []
    unknown_flows: list[dict[str, Any]] = []

    async with httpx.AsyncClient(timeout=5.0) as http:
        for flow_id, steps in steps_by_flow.items():
            flow_obj = flow_objs.get(flow_id) or {}
            indicator_expr = flow_obj.get("activity_indicator_expr")
            indicator_threshold = flow_obj.get("activity_indicator_threshold")
            indicator_description = flow_obj.get("activity_indicator_description")
            steps_touching_nf = [
                {"step_order": s.get("step_order"),
                 "step_label": s.get("step_label")}
                for s in steps
            ]
            entry: dict[str, Any] = {
                "flow_id": flow_id,
                "flow_name": (flow_obj.get("name")
                              or steps[0].get("flow_name", flow_id)),
                "steps_touching_nf": steps_touching_nf,
            }

            if not indicator_expr:
                # KB explicitly did not author an indicator for this
                # flow. Surface honestly — never silently treat as
                # "inactive."
                entry.update({
                    "active": None,
                    "indicator_expr": None,
                    "indicator_threshold": None,
                    "indicator_value": None,
                    "reason": (
                        "no activity_indicator authored in flows.yaml — "
                        "this flow's activity cannot be determined from "
                        "current Prometheus metrics. See ADR "
                        "flows_tool_deployment_awareness.md."
                    ),
                })
                unknown_flows.append(entry)
                continue

            # Substitute the window into the expression — same template
            # convention as data_plane.py.
            try:
                query = indicator_expr.format(w=window_seconds)
            except (KeyError, IndexError, ValueError):
                # Authoring error: the KB expression isn't a valid
                # `{w}`-template. Treat as unknown rather than crashing
                # the whole probe; a separate KB validation test would
                # catch this at PR time.
                entry.update({
                    "active": None,
                    "indicator_expr": indicator_expr,
                    "indicator_threshold": indicator_threshold,
                    "indicator_value": None,
                    "reason": (
                        "activity_indicator.expr is not a valid "
                        "{w}-template; treat as indicator-unauthored."
                    ),
                })
                unknown_flows.append(entry)
                continue

            value = await _prom_query(http, prom_url, query, at_time_ts)
            threshold = (
                float(indicator_threshold)
                if indicator_threshold is not None else 0.0
            )
            is_active = value is not None and value > threshold
            entry.update({
                "active": bool(is_active),
                "indicator_expr": indicator_expr,
                "indicator_threshold": threshold,
                "indicator_value": value,
                "indicator_description": indicator_description,
            })
            (active_flows if is_active else inactive_flows).append(entry)

    payload = {
        "source": "live (Prometheus over window)",
        "scope": "deployment activity",
        "component": component,
        "window_seconds": window_seconds,
        "at_time_ts": at_time_ts,
        "active_flows": active_flows,
        "inactive_flows": inactive_flows,
        "unknown_flows": unknown_flows,
    }
    return _json.dumps(payload, indent=2, default=str)


async def _prom_query(
    http: httpx.AsyncClient,
    url: str,
    query: str,
    at_time_ts: float | None,
) -> float | None:
    """Single PromQL instant query; returns scalar or None on no result.

    Mirrors `agentic_ops_common.tools.data_plane._prom_query` semantics
    so callers see consistent behavior across rate-windowed probes.
    Returns None (not 0) when the query returned no series — the caller
    needs to distinguish "indicator queried, value was 0" (clearly
    inactive) from "query failed / metric absent" (cannot conclude).
    """
    try:
        params: dict[str, str | float] = {"query": query}
        if at_time_ts is not None:
            params["time"] = at_time_ts
        resp = await http.get(f"{url}/api/v1/query", params=params)
        if resp.status_code != 200:
            _log.warning(
                "Prometheus HTTP %d for activity-indicator query: %s",
                resp.status_code, query[:80],
            )
            return None
        body = resp.json()
        results = body.get("data", {}).get("result", [])
        if not results:
            # No series matched. Distinct from value=0 — return None.
            return None
        return float(results[0]["value"][1])
    except Exception as e:
        _log.warning(
            "Activity-indicator query failed: %s — %s", query[:80], e
        )
        return None
