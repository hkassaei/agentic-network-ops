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


def _tool_name(t) -> str:
    """Return the runtime-callable name of a tool registered on an
    LlmAgent. Works for both bare async functions (name is __name__)
    and AgentTool wrappers (name is the wrapped agent's .name)."""
    # AgentTool has .agent, plain functions have __name__
    inner = getattr(t, "agent", None)
    if inner is not None:
        return inner.name
    return getattr(t, "__name__", getattr(t, "name", repr(t)))


def test_falsification_probe_tool_enum_matches_investigator_tools():
    """Regression guard — the `_InvestigatorTool` Literal in
    agentic_ops_v6/models.py must list every name Gemini's constrained
    decoder could receive as a legal `tool` value on a probe, and
    nothing else. It has to stay in exact sync with the Investigator's
    actual `tools=[...]` list.

    If this test fails: you edited the Investigator's tool registration
    without updating the Literal (or vice versa). Fix both in the same
    commit. See docs/ADR/falsifier_investigator_and_rag.md and the
    `_InvestigatorTool` comment in models.py.
    """
    import typing
    from agentic_ops_v6.models import FalsificationProbe

    agent = create_investigator_agent()
    registered = {_tool_name(t) for t in agent.tools}

    # Pull the Literal's allowed values off the FalsificationProbe schema
    tool_field = FalsificationProbe.model_fields["tool"]
    allowed = set(typing.get_args(tool_field.annotation))

    missing_from_literal = registered - allowed
    extra_in_literal = allowed - registered

    assert not missing_from_literal, (
        f"Investigator registers tool(s) that the FalsificationProbe "
        f"schema doesn't allow: {sorted(missing_from_literal)}. "
        f"Add them to `_InvestigatorTool` in agentic_ops_v6/models.py."
    )
    assert not extra_in_literal, (
        f"FalsificationProbe schema allows tool name(s) the Investigator "
        f"does NOT register: {sorted(extra_in_literal)}. Remove them "
        f"from `_InvestigatorTool` in agentic_ops_v6/models.py so "
        f"Gemini's constrained decoder cannot emit an unusable tool."
    )


def test_falsification_plan_requires_min_probes():
    """Schema-level enforcement — a plan with 0 or 1 probes must fail
    Pydantic validation. This is the core protection against the
    `tool_calls=0, llm_calls=1` short-circuit where Gemini would emit
    a plan with an empty `probes` list."""
    from agentic_ops_v6.models import FalsificationPlan, FalsificationProbe
    from pydantic import ValidationError

    good_probe = FalsificationProbe(
        tool="measure_rtt",
        expected_if_hypothesis_holds="x",
        falsifying_observation="y",
    )
    # zero probes
    with pytest.raises(ValidationError):
        FalsificationPlan(
            hypothesis_id="h1",
            hypothesis_statement="...",
            primary_suspect_nf="pcscf",
            probes=[],
        )
    # one probe — also below min
    with pytest.raises(ValidationError):
        FalsificationPlan(
            hypothesis_id="h1",
            hypothesis_statement="...",
            primary_suspect_nf="pcscf",
            probes=[good_probe],
        )
    # two probes — minimum allowed
    plan = FalsificationPlan(
        hypothesis_id="h1",
        hypothesis_statement="...",
        primary_suspect_nf="pcscf",
        probes=[good_probe, good_probe],
    )
    assert len(plan.probes) == 2


def test_falsification_plan_set_requires_min_plans():
    """Schema-level enforcement — an empty `plans` list must fail.
    This is what the previous (pre-hardening) schema silently accepted
    in 36% of Apr-24 batch runs."""
    from agentic_ops_v6.models import FalsificationPlanSet
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        FalsificationPlanSet(plans=[])


def test_falsification_probe_rejects_unknown_tool():
    """Gemini hallucinates tool names like `log_search` or `tcpdump`.
    The schema must reject them before the Investigator ever sees
    the plan."""
    from agentic_ops_v6.models import FalsificationProbe
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        FalsificationProbe(
            tool="log_search",  # not in the Literal
            expected_if_hypothesis_holds="x",
            falsifying_observation="y",
        )


def test_falsification_plan_rejects_unknown_nf():
    """Same rationale for `primary_suspect_nf`. Gemini sometimes names
    `hss` (legacy) or `proxy` (generic); the schema must reject those
    so the rest of the pipeline can't be asked to reason about an
    invented NF."""
    from agentic_ops_v6.models import FalsificationPlan, FalsificationProbe
    from pydantic import ValidationError

    probe = FalsificationProbe(
        tool="measure_rtt",
        expected_if_hypothesis_holds="x",
        falsifying_observation="y",
    )
    with pytest.raises(ValidationError):
        FalsificationPlan(
            hypothesis_id="h1",
            hypothesis_statement="...",
            primary_suspect_nf="hss",  # real name is pyhss
            probes=[probe, probe],
        )
