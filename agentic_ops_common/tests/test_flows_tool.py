"""Tests for agent-facing flow query tools.

These tests mock the underlying `network_ontology.query.OntologyClient`
so they don't require a running Neo4j — the tools themselves are thin
wrappers over that client, and the wrapper behavior (JSON serialization,
error handling) is what we care about here.
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
    assert "seeded" in result  # hint about re-seeding


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
    assert "list_flows()" in result  # points at discovery tool


def test_get_flows_through_component_returns_json():
    from agentic_ops_common.tools import flows as flows_tool

    fake_client = MagicMock()
    fake_client.get_flows_through_component.return_value = [
        {"flow_id": "vonr_call_setup", "flow_name": "VoNR Call Setup",
         "step_order": 2, "step_label": "N5 App Session Create (orig)"},
        {"flow_id": "ims_registration", "flow_name": "IMS Registration",
         "step_order": 9, "step_label": "N5 App Session Create"},
    ]
    _install_fake_client_module(fake_client)

    result = asyncio.run(flows_tool.get_flows_through_component("pcscf"))
    parsed = json.loads(result)
    assert isinstance(parsed, list)
    assert len(parsed) == 2
    assert all("flow_id" in row for row in parsed)
    fake_client.get_flows_through_component.assert_called_once_with("pcscf")


def test_get_flows_through_component_empty_is_helpful():
    from agentic_ops_common.tools import flows as flows_tool

    fake_client = MagicMock()
    fake_client.get_flows_through_component.return_value = []
    _install_fake_client_module(fake_client)

    result = asyncio.run(
        flows_tool.get_flows_through_component("mysterious_nf")
    )
    assert "No flows found" in result
    assert "mysterious_nf" in result


def test_errors_are_caught_and_returned_as_strings():
    """Tool should never raise; always return a string result."""
    from agentic_ops_common.tools import flows as flows_tool

    fake_client = MagicMock()
    fake_client.get_all_flows.side_effect = RuntimeError("neo4j unavailable")
    _install_fake_client_module(fake_client)

    result = asyncio.run(flows_tool.list_flows())
    assert isinstance(result, str)
    assert "ERROR" in result
    assert "neo4j unavailable" in result


def test_ontology_package_missing_is_handled():
    from agentic_ops_common.tools import flows as flows_tool

    # Simulate ImportError by removing the module
    saved = sys.modules.pop("network_ontology.query", None)
    saved_parent = sys.modules.pop("network_ontology", None)
    try:
        with patch.dict(sys.modules, {"network_ontology.query": None}):
            result = asyncio.run(flows_tool.list_flows())
            assert "ERROR" in result
            assert "network_ontology" in result
    finally:
        if saved is not None:
            sys.modules["network_ontology.query"] = saved
        if saved_parent is not None:
            sys.modules["network_ontology"] = saved_parent


def test_tools_exported_from_package():
    """All three wrappers are re-exported from agentic_ops_common.tools."""
    from agentic_ops_common import tools
    assert hasattr(tools, "list_flows")
    assert hasattr(tools, "get_flow")
    assert hasattr(tools, "get_flows_through_component")
    assert "list_flows" in tools.__all__
    assert "get_flow" in tools.__all__
    assert "get_flows_through_component" in tools.__all__
