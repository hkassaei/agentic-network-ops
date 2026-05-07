"""Tests for the agent-facing flow query tools.

Per ADR `flows_tool_deployment_awareness.md`, there are two distinct
component-scoped flow tools:

  - `get_canonical_flows_through_component(nf)` — KB lookup with
    failure_modes inlined; output payload carries `source` / `scope`
    fields stating "NOT live deployment state".
  - `get_active_flows_through_component(nf, at_time_ts, window_seconds)`
    — Prometheus-backed live-activity probe; partitions canonical
    flows into active / inactive / unknown.

These tests mock the underlying `network_ontology.query.OntologyClient`
(no Neo4j) and `httpx.AsyncClient` (no Prometheus). The wrappers
themselves — JSON serialization, error handling, payload shape — are
what we care about.
"""

from __future__ import annotations

import asyncio
import json
import sys
import types
from unittest.mock import MagicMock, patch


def _install_fake_client_module(client_instance):
    """Install a fake `network_ontology.query` module whose `OntologyClient`
    constructor returns `client_instance`. Avoids requiring a running Neo4j.

    Imports the real `network_ontology` package first so its `__path__`
    points at the actual source directory — tests that run later and
    import sibling submodules (e.g. `network_ontology.schema`) must
    still be able to find them. Only the `.query` submodule is stubbed.
    """
    import network_ontology  # ensure real package is in sys.modules
    fake_query = types.ModuleType("network_ontology.query")
    fake_query.OntologyClient = MagicMock(return_value=client_instance)
    sys.modules["network_ontology.query"] = fake_query
    return fake_query


# ============================================================================
# list_flows / get_flow — unchanged from pre-rename
# ============================================================================

def test_list_flows_returns_json():
    from agentic_ops_common.tools import flows as flows_tool

    fake_client = MagicMock()
    fake_client.get_all_flows.return_value = [
        {"id": "vonr_call_setup", "name": "VoNR Call Setup",
         "use_case": "vonr", "step_count": 12},
        {"id": "ims_registration", "name": "IMS Registration",
         "use_case": "vonr", "step_count": 9},
    ]
    _install_fake_client_module(fake_client)

    result = asyncio.run(flows_tool.list_flows())
    parsed = json.loads(result)
    assert isinstance(parsed, list)
    assert len(parsed) == 2
    assert parsed[0]["id"] == "vonr_call_setup"
    assert parsed[0]["step_count"] == 12
    fake_client.close.assert_called_once()


def test_list_flows_empty_result_is_helpful():
    from agentic_ops_common.tools import flows as flows_tool

    fake_client = MagicMock()
    fake_client.get_all_flows.return_value = []
    _install_fake_client_module(fake_client)

    result = asyncio.run(flows_tool.list_flows())
    assert "No flows found" in result
    assert "seeded" in result


def test_get_flow_returns_json():
    from agentic_ops_common.tools import flows as flows_tool

    fake_client = MagicMock()
    fake_client.get_flow.return_value = {
        "id": "vonr_call_setup",
        "name": "VoNR Call Setup",
        "steps": [
            {"step_order": 1, "label": "INVITE from UE1"},
            {"step_order": 2, "label": "N5 App Session Create (orig)"},
        ],
    }
    _install_fake_client_module(fake_client)

    result = asyncio.run(flows_tool.get_flow("vonr_call_setup"))
    parsed = json.loads(result)
    assert parsed["id"] == "vonr_call_setup"
    assert len(parsed["steps"]) == 2
    fake_client.get_flow.assert_called_once_with("vonr_call_setup")


def test_get_flow_missing_id_is_helpful():
    from agentic_ops_common.tools import flows as flows_tool

    fake_client = MagicMock()
    fake_client.get_flow.return_value = None
    _install_fake_client_module(fake_client)

    result = asyncio.run(flows_tool.get_flow("totally_bogus"))
    assert "No flow found with id 'totally_bogus'" in result
    assert "list_flows()" in result


# ============================================================================
# get_canonical_flows_through_component
# ============================================================================

def test_canonical_flows_payload_shape():
    """Payload must contain `source`, `scope`, `component`, `flows`,
    and the scope string must explicitly state 'NOT live deployment
    state'. This is the safeguard against the LLM confusing canonical
    with live."""
    from agentic_ops_common.tools import flows as flows_tool

    fake_client = MagicMock()
    fake_client.get_flows_through_component.return_value = [
        {"flow_id": "vonr_call_setup", "flow_name": "VoNR Call Setup",
         "step_order": 2, "step_label": "N5 App Session Create (orig)"},
        {"flow_id": "ims_registration", "flow_name": "IMS Registration",
         "step_order": 9, "step_label": "N5 App Session Create"},
    ]
    fake_client.get_flow.return_value = {
        "id": "vonr_call_setup", "name": "VoNR Call Setup",
        "steps": [{"step_order": 2, "failure_modes": ["PCF returns non-201"]}],
    }
    _install_fake_client_module(fake_client)

    result = asyncio.run(
        flows_tool.get_canonical_flows_through_component("pcscf")
    )
    parsed = json.loads(result)

    assert parsed["source"] == "network_ontology"
    assert "NOT live deployment state" in parsed["scope"]
    assert parsed["component"] == "pcscf"
    assert isinstance(parsed["flows"], list)
    assert len(parsed["flows"]) == 2
    fake_client.get_flows_through_component.assert_called_once_with("pcscf")


def test_canonical_flows_failure_modes_inlined_per_step():
    """Each row must carry a `failure_modes` list pulled from the
    matching step in the flow body. This saves the IG/Investigator a
    follow-up `get_flow(flow_id)` call when designing probes."""
    from agentic_ops_common.tools import flows as flows_tool

    fake_client = MagicMock()
    fake_client.get_flows_through_component.return_value = [
        {"flow_id": "vonr_call_setup", "flow_name": "VoNR Call Setup",
         "step_order": 2, "step_label": "N5 App Session Create (orig)"},
    ]
    fake_client.get_flow.return_value = {
        "id": "vonr_call_setup",
        "steps": [
            {"step_order": 1, "failure_modes": ["irrelevant"]},
            {"step_order": 2,
             "failure_modes": [
                 "PCF returns non-201 → P-CSCF sends SIP 412",
                 "SCP unreachable → P-CSCF logs 'connection refused'",
             ]},
        ],
    }
    _install_fake_client_module(fake_client)

    result = asyncio.run(
        flows_tool.get_canonical_flows_through_component("pcscf")
    )
    parsed = json.loads(result)
    row = parsed["flows"][0]
    assert "failure_modes" in row
    assert len(row["failure_modes"]) == 2
    assert "PCF returns non-201" in row["failure_modes"][0]


def test_canonical_flows_empty_includes_helpful_note():
    from agentic_ops_common.tools import flows as flows_tool

    fake_client = MagicMock()
    fake_client.get_flows_through_component.return_value = []
    _install_fake_client_module(fake_client)

    result = asyncio.run(
        flows_tool.get_canonical_flows_through_component("mysterious_nf")
    )
    parsed = json.loads(result)
    assert parsed["component"] == "mysterious_nf"
    assert parsed["flows"] == []
    assert "note" in parsed
    assert "list_flows()" in parsed["note"]
    assert "get_active_flows_through_component" in parsed["note"]


def test_canonical_flows_handles_structured_failure_modes():
    """failure_modes may be list[str] OR list[dict]; both must render
    cleanly without crashing."""
    from agentic_ops_common.tools import flows as flows_tool

    fake_client = MagicMock()
    fake_client.get_flows_through_component.return_value = [
        {"flow_id": "x", "flow_name": "X", "step_order": 1, "step_label": "L"},
    ]
    fake_client.get_flow.return_value = {
        "id": "x",
        "steps": [
            {"step_order": 1, "failure_modes": [
                {"id": "fm1", "description": "structured one"},
                "plain string two",
            ]},
        ],
    }
    _install_fake_client_module(fake_client)

    result = asyncio.run(
        flows_tool.get_canonical_flows_through_component("pcscf")
    )
    parsed = json.loads(result)
    fms = parsed["flows"][0]["failure_modes"]
    assert len(fms) == 2
    assert "fm1" in fms[0] or "structured one" in fms[0]
    assert "plain string two" in fms[1]


# ============================================================================
# get_active_flows_through_component
# ============================================================================

class _FakeProm:
    """Stand-in for httpx.AsyncClient.get(...) returning canned values
    keyed on Prometheus query substring."""

    def __init__(self, values_by_substring: dict[str, float | None]):
        self.values = values_by_substring
        self.calls: list[dict] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return None

    async def get(self, url, params=None):
        params = dict(params or {})
        self.calls.append({"url": url, "params": params})
        q = params.get("query", "")
        for substr, val in self.values.items():
            if substr in q:
                if val is None:
                    return _FakeResp([])
                return _FakeResp([{"value": [0, str(val)]}])
        return _FakeResp([])


class _FakeResp:
    def __init__(self, results):
        self.status_code = 200
        self._results = results

    def json(self):
        return {"data": {"result": self._results}}


def _install_active_flows_test_doubles(prom_values: dict[str, float | None]):
    """Wire up: OntologyClient stub + Prometheus stub + deps stub."""
    fake_client = MagicMock()
    fake_client.get_flows_through_component.return_value = [
        {"flow_id": "vonr_call_setup", "flow_name": "VoNR Call Setup",
         "step_order": 5, "step_label": "RTP from UE1 to UE2"},
        {"flow_id": "ims_registration", "flow_name": "IMS Registration",
         "step_order": 1, "step_label": "REGISTER from UE"},
        {"flow_id": "vonr_call_teardown", "flow_name": "VoNR Call Teardown",
         "step_order": 1, "step_label": "BYE from UE"},
    ]

    def fake_get_flow(fid):
        if fid == "vonr_call_setup":
            return {
                "id": "vonr_call_setup", "name": "VoNR Call Setup",
                "activity_indicator_expr":
                    "rate(fivegs_pcffunction_pa_policysmassoreq[{w}s])",
                "activity_indicator_threshold": 0.0,
                "activity_indicator_description": "PCF policy rate",
                "steps": [{"step_order": 5, "failure_modes": []}],
            }
        if fid == "ims_registration":
            return {
                "id": "ims_registration", "name": "IMS Registration",
                "activity_indicator_expr":
                    "rate(fivegs_amffunction_amf_authreq[{w}s])",
                "activity_indicator_threshold": 0.0,
                "activity_indicator_description": "AMF auth proxy",
                "steps": [{"step_order": 1, "failure_modes": []}],
            }
        if fid == "vonr_call_teardown":
            return {
                "id": "vonr_call_teardown", "name": "VoNR Call Teardown",
                "activity_indicator_expr": None,
                "activity_indicator_threshold": None,
                "activity_indicator_description": None,
                "steps": [{"step_order": 1, "failure_modes": []}],
            }
        return None

    fake_client.get_flow.side_effect = fake_get_flow
    _install_fake_client_module(fake_client)

    prom = _FakeProm(prom_values)
    return fake_client, prom


def test_active_flows_partitions_into_active_inactive_unknown():
    from agentic_ops_common.tools import flows as flows_tool

    _, prom = _install_active_flows_test_doubles({
        "fivegs_pcffunction_pa_policysmassoreq": 0.06,  # active
        "fivegs_amffunction_amf_authreq": 0.0,           # inactive
    })

    fake_deps = MagicMock()
    fake_deps.env = {"METRICS_IP": "test-ip"}
    with patch("agentic_ops_common.tools.flows.httpx.AsyncClient",
               return_value=prom), \
         patch("agentic_ops_common.tools._common._get_deps",
               return_value=fake_deps):
        result = asyncio.run(
            flows_tool.get_active_flows_through_component(
                "pcscf", at_time_ts=None, window_seconds=120
            )
        )
    parsed = json.loads(result)
    assert parsed["source"] == "live (Prometheus over window)"
    assert parsed["component"] == "pcscf"
    assert parsed["window_seconds"] == 120

    active_ids = [f["flow_id"] for f in parsed["active_flows"]]
    inactive_ids = [f["flow_id"] for f in parsed["inactive_flows"]]
    unknown_ids = [f["flow_id"] for f in parsed["unknown_flows"]]

    assert "vonr_call_setup" in active_ids
    assert "ims_registration" in inactive_ids
    assert "vonr_call_teardown" in unknown_ids


def test_active_flows_unknown_carries_explanatory_reason():
    """Flows without an authored activity_indicator must surface
    `active: null` and a non-empty `reason` field — the LLM should
    never read 'no activity' when the indicator simply isn't there."""
    from agentic_ops_common.tools import flows as flows_tool

    _, prom = _install_active_flows_test_doubles({
        "fivegs_pcffunction_pa_policysmassoreq": 0.0,
        "fivegs_amffunction_amf_authreq": 0.0,
    })

    fake_deps = MagicMock()
    fake_deps.env = {"METRICS_IP": "test-ip"}
    with patch("agentic_ops_common.tools.flows.httpx.AsyncClient",
               return_value=prom), \
         patch("agentic_ops_common.tools._common._get_deps",
               return_value=fake_deps):
        result = asyncio.run(
            flows_tool.get_active_flows_through_component(
                "pcscf", at_time_ts=None, window_seconds=120
            )
        )
    parsed = json.loads(result)
    teardown = next(
        f for f in parsed["unknown_flows"]
        if f["flow_id"] == "vonr_call_teardown"
    )
    assert teardown["active"] is None
    assert "reason" in teardown
    assert teardown["reason"]


def test_active_flows_passes_at_time_ts_to_prometheus():
    """When at_time_ts is provided, every Prometheus query must carry
    the matching `?time=` parameter so the rate window is anchored at
    the historical moment, not 'now'."""
    from agentic_ops_common.tools import flows as flows_tool

    _, prom = _install_active_flows_test_doubles({
        "fivegs_pcffunction_pa_policysmassoreq": 0.06,
        "fivegs_amffunction_amf_authreq": 0.0,
    })

    fake_deps = MagicMock()
    fake_deps.env = {"METRICS_IP": "test-ip"}
    with patch("agentic_ops_common.tools.flows.httpx.AsyncClient",
               return_value=prom), \
         patch("agentic_ops_common.tools._common._get_deps",
               return_value=fake_deps):
        asyncio.run(
            flows_tool.get_active_flows_through_component(
                "pcscf", at_time_ts=1_700_000_000.0, window_seconds=60
            )
        )
    # Every Prometheus call must carry `time=1700000000.0`.
    assert prom.calls
    for call in prom.calls:
        assert call["params"].get("time") == 1_700_000_000.0


def test_active_flows_empty_component_returns_empty_partitions():
    from agentic_ops_common.tools import flows as flows_tool

    fake_client = MagicMock()
    fake_client.get_flows_through_component.return_value = []
    _install_fake_client_module(fake_client)

    fake_deps = MagicMock()
    fake_deps.env = {"METRICS_IP": "test-ip"}
    with patch("agentic_ops_common.tools._common._get_deps",
               return_value=fake_deps):
        result = asyncio.run(
            flows_tool.get_active_flows_through_component(
                "no_such_nf", at_time_ts=None, window_seconds=120
            )
        )
    parsed = json.loads(result)
    assert parsed["active_flows"] == []
    assert parsed["inactive_flows"] == []
    assert parsed["unknown_flows"] == []
    assert "note" in parsed


def test_active_flows_window_clamped_to_minimum_10s():
    from agentic_ops_common.tools import flows as flows_tool

    fake_client = MagicMock()
    fake_client.get_flows_through_component.return_value = []
    _install_fake_client_module(fake_client)
    fake_deps = MagicMock()
    fake_deps.env = {"METRICS_IP": "test-ip"}
    with patch("agentic_ops_common.tools._common._get_deps",
               return_value=fake_deps):
        result = asyncio.run(
            flows_tool.get_active_flows_through_component(
                "any", at_time_ts=None, window_seconds=2
            )
        )
    assert json.loads(result)["window_seconds"] == 10


# ============================================================================
# Error paths
# ============================================================================

def test_canonical_flows_errors_are_caught_and_returned_as_strings():
    from agentic_ops_common.tools import flows as flows_tool

    fake_client = MagicMock()
    fake_client.get_flows_through_component.side_effect = RuntimeError(
        "neo4j unavailable"
    )
    _install_fake_client_module(fake_client)

    result = asyncio.run(
        flows_tool.get_canonical_flows_through_component("pcscf")
    )
    assert isinstance(result, str)
    assert "ERROR" in result
    assert "neo4j unavailable" in result


def test_active_flows_ontology_error_returned_as_string():
    from agentic_ops_common.tools import flows as flows_tool

    fake_client = MagicMock()
    fake_client.get_flows_through_component.side_effect = RuntimeError(
        "neo4j unavailable"
    )
    _install_fake_client_module(fake_client)

    result = asyncio.run(
        flows_tool.get_active_flows_through_component(
            "pcscf", at_time_ts=None, window_seconds=120
        )
    )
    assert "ERROR" in result
    assert "neo4j unavailable" in result


# ============================================================================
# No-legacy-name guard + export check
# ============================================================================

def test_legacy_agent_tool_name_is_removed():
    """The agent-tool surface no longer exposes the legacy name. The
    Cypher method on OntologyClient retains its name (gui/server.py
    uses it directly), but no agent-facing site may still bind the
    old tool. Per ADR `flows_tool_deployment_awareness.md` — hard cut,
    no alias."""
    from agentic_ops_common import tools

    # Live attribute was the agent tool; it must be gone.
    assert not hasattr(tools, "get_flows_through_component"), (
        "Legacy agent-tool attribute `get_flows_through_component` must "
        "not exist on agentic_ops_common.tools — use "
        "`get_canonical_flows_through_component` instead."
    )
    # Public __all__ must not advertise it.
    assert "get_flows_through_component" not in tools.__all__


def test_new_tools_exported_from_package():
    from agentic_ops_common import tools
    assert hasattr(tools, "get_canonical_flows_through_component")
    assert hasattr(tools, "get_active_flows_through_component")
    assert "get_canonical_flows_through_component" in tools.__all__
    assert "get_active_flows_through_component" in tools.__all__
    assert "list_flows" in tools.__all__
    assert "get_flow" in tools.__all__


def test_no_legacy_name_in_live_agent_code():
    """A grep-style guard: no live agent-facing source file under
    `agentic_ops_v6/` (excluding agent_logs / docs) and no live
    file in `agentic_ops_common/tools/` (excluding the Cypher-method
    docstring in flows.py) may reference the legacy agent-tool name.
    """
    import re
    from pathlib import Path

    repo = Path(__file__).resolve().parents[2]
    roots = [
        repo / "agentic_ops_v6" / "subagents",
        repo / "agentic_ops_v6" / "prompts",
        repo / "agentic_ops_v6" / "models.py",
        repo / "agentic_ops_v6" / "orchestrator.py",
    ]
    bad_refs: list[str] = []
    pat = re.compile(r"\bget_flows_through_component\b")
    for root in roots:
        if root.is_file():
            files = [root]
        elif root.is_dir():
            files = list(root.rglob("*.py")) + list(root.rglob("*.md"))
        else:
            continue
        for path in files:
            text = path.read_text(errors="replace")
            for m in pat.finditer(text):
                line_no = text[: m.start()].count("\n") + 1
                bad_refs.append(f"{path.relative_to(repo)}:{line_no}")
    assert not bad_refs, (
        "Legacy agent-tool name `get_flows_through_component` still "
        "appears in live agent-facing code:\n  "
        + "\n  ".join(bad_refs)
        + "\nReplace with `get_canonical_flows_through_component` or "
        "`get_active_flows_through_component` per ADR "
        "`flows_tool_deployment_awareness.md`."
    )
