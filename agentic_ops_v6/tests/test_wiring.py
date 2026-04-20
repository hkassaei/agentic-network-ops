"""Sanity tests: all v6 pieces wire up without LLM calls."""

from __future__ import annotations

import pytest

from agentic_ops_v6.subagents.network_analyst import create_network_analyst
from agentic_ops_v6.subagents.instruction_generator import create_instruction_generator
from agentic_ops_v6.subagents.investigator import create_investigator_agent
from agentic_ops_v6.subagents.synthesis import create_synthesis_agent
from agentic_ops_v6.subagents.ontology_consultation import create_ontology_consultation_agent


def test_network_analyst_constructible():
    agent = create_network_analyst()
    assert agent.name == "NetworkAnalystAgent"
    assert len(agent.tools) > 0


def test_instruction_generator_constructible():
    agent = create_instruction_generator()
    assert agent.name == "InstructionGeneratorAgent"


def test_investigator_constructible_with_custom_name():
    agent = create_investigator_agent(name="InvestigatorAgent_h1")
    assert agent.name == "InvestigatorAgent_h1"
    assert len(agent.tools) > 0


def test_synthesis_constructible():
    agent = create_synthesis_agent()
    assert agent.name == "SynthesisAgent"
    assert agent.tools == []  # pure synthesis


def test_ontology_consultation_constructible():
    agent = create_ontology_consultation_agent()
    assert agent.name == "OntologyConsultationAgent"
    assert len(agent.tools) > 0


def test_event_aggregator_handles_missing_store(tmp_path, monkeypatch):
    from agentic_ops_common.metric_kb import EventStore
    from agentic_ops_v6.subagents.event_aggregator import aggregate_episode_events
    # Call with no events in the default store
    store = EventStore(tmp_path / "empty.db")
    store.close()
    events, rendered = aggregate_episode_events(
        episode_id="nonexistent", store_path=tmp_path / "empty.db",
    )
    assert events == []
    assert "No events fired" in rendered


def test_correlation_analyzer_with_no_events():
    from agentic_ops_common.metric_kb import load_kb
    from agentic_ops_v6.subagents.correlation_analyzer import analyze_correlations
    kb = load_kb()
    result = analyze_correlations(kb, [], episode_id="empty_ep")
    assert result.events_considered == 0
    assert result.top_statement is None


def test_orchestrator_importable():
    """Make sure the orchestrator module itself imports cleanly."""
    from agentic_ops_v6.orchestrator import investigate  # noqa: F401
    from agentic_ops_v6.orchestrator import (
        MAX_PARALLEL_INVESTIGATORS,
        MIN_TOOL_CALLS_PER_INVESTIGATOR,
    )
    assert MAX_PARALLEL_INVESTIGATORS == 3
    assert MIN_TOOL_CALLS_PER_INVESTIGATOR == 2
