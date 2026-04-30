"""Tests for the Phase 4 InstructionGenerator retry guard.

The orchestrator wraps `_run_phase(IG)` with `_run_ig_with_retry` to
patch ADK's silent-bail behavior on empty Gemini final-response chunks
(see `agents/llm_agent.py:__maybe_save_output_to_state` in google-adk).
These tests exercise the detection logic and the retry path without
needing a live Gemini call.
"""

from __future__ import annotations

import pytest

from agentic_ops_v6.orchestrator import (
    _IG_OUTPUT_KEY,
    _ig_output_present,
)


# ============================================================================
# `_ig_output_present` — the detector
# ============================================================================

def test_detector_treats_missing_key_as_failure():
    """No state write at all = silent-bail path. Must return False."""
    state: dict = {}
    assert _ig_output_present(state) is False


def test_detector_treats_none_as_failure():
    """Explicit None (e.g. from a `state.pop()` cleanup) = failure."""
    state = {_IG_OUTPUT_KEY: None}
    assert _ig_output_present(state) is False


def test_detector_treats_empty_string_as_failure():
    """ADK can leave an empty string in state if the output_schema
    short-circuit produced no content. Treat as failure."""
    state = {_IG_OUTPUT_KEY: ""}
    assert _ig_output_present(state) is False


def test_detector_treats_whitespace_only_string_as_failure():
    """Whitespace-only is the exact thing ADK's
    `if not result.strip(): return` is checking for. The detector
    must mirror the same semantics so a string that ADK *would have*
    bailed on still registers as failure here."""
    state = {_IG_OUTPUT_KEY: "   \n\t"}
    assert _ig_output_present(state) is False


def test_detector_treats_non_empty_json_string_as_success():
    """A real JSON payload from a successful IG run = success.
    Note: this test only validates the detector's job — content
    parseability is the downstream `_parse_plan_set` helper's
    responsibility."""
    state = {_IG_OUTPUT_KEY: '{"plans": [{"hypothesis_id": "h1"}]}'}
    assert _ig_output_present(state) is True


def test_detector_treats_dict_as_success():
    """ADK sometimes stores structured output as a dict rather than a
    JSON string. Both shapes should be treated the same way."""
    state = {_IG_OUTPUT_KEY: {"plans": [{"hypothesis_id": "h1"}]}}
    assert _ig_output_present(state) is True


def test_detector_treats_empty_dict_as_success_for_downstream_parse():
    """Edge case: a non-empty (truthy in `bool(...)` terms but containing
    no plans) value still gets through the detector — `_parse_plan_set`
    is the layer that decides whether the parsed payload is acceptable.
    This keeps the detector responsible only for "did ADK write
    something" vs. parsing semantics. An empty dict `{}` is technically
    "something was written" — even if downstream rejects it as
    schema-invalid."""
    state = {_IG_OUTPUT_KEY: {"some_partial_field": "x"}}
    assert _ig_output_present(state) is True


# ============================================================================
# Generic empty-output retry — applied to every LlmAgent phase
# ============================================================================
#
# After observing the same Gemini empty-final-response failure mode hit
# Phase 3 NetworkAnalyst (run_20260430_020337_call_quality_degradation =
# 15%), the IG-specific retry was generalized to a phase-agnostic helper.
# These tests cover the generic detector and the helper's behaviour on
# both attempts succeeding, the second succeeding after a first empty,
# and both failing.

def test_generic_detector_works_for_arbitrary_keys():
    """The generic `_output_present` is the workhorse used by every
    phase wrapper. The IG-specific `_ig_output_present` is a thin
    wrapper around it. Verify the generic form behaves identically
    across different keys (NA, Synthesis, Investigator)."""
    from agentic_ops_v6.orchestrator import (
        _NA_OUTPUT_KEY,
        _SYNTHESIS_OUTPUT_KEY,
        _INVESTIGATOR_OUTPUT_KEY,
        _output_present,
    )
    for key in (_NA_OUTPUT_KEY, _SYNTHESIS_OUTPUT_KEY, _INVESTIGATOR_OUTPUT_KEY):
        assert _output_present({}, key) is False
        assert _output_present({key: None}, key) is False
        assert _output_present({key: ""}, key) is False
        assert _output_present({key: "  \n  "}, key) is False
        assert _output_present({key: "non-empty"}, key) is True
        assert _output_present({key: {"any": "dict"}}, key) is True


@pytest.mark.asyncio
async def test_generic_retry_returns_success_when_first_attempt_writes_output(monkeypatch):
    """Happy path — the agent writes a non-empty value on the first
    attempt; helper returns success without re-running."""
    from agentic_ops_v6 import orchestrator as orch

    call_count = {"n": 0}

    async def fake_run_phase(agent, state, question, session_service, on_event=None):
        call_count["n"] += 1
        return ({**state, "diagnosis": '{"some": "payload"}'}, [])

    monkeypatch.setattr(orch, "_run_phase", fake_run_phase)

    state, traces, success = await orch._run_phase_with_empty_output_retry(
        agent_factory=lambda: object(),
        state={},
        question="q",
        session_service=None,
        on_event=None,
        output_key="diagnosis",
        phase_label="test phase",
    )
    assert success is True
    assert call_count["n"] == 1
    assert state["diagnosis"] == '{"some": "payload"}'


@pytest.mark.asyncio
async def test_generic_retry_succeeds_on_second_attempt_after_first_empty(monkeypatch):
    """The exact bug shape — first attempt silently bails (no state
    write); second attempt produces output. Verify the helper retries
    and returns success."""
    from agentic_ops_v6 import orchestrator as orch

    call_count = {"n": 0}

    async def fake_run_phase(agent, state, question, session_service, on_event=None):
        call_count["n"] += 1
        if call_count["n"] == 1:
            # ADK silent-bail: no state write on the output key.
            return (state, [])
        return ({**state, "diagnosis": '{"second": "attempt"}'}, [])

    monkeypatch.setattr(orch, "_run_phase", fake_run_phase)

    state, traces, success = await orch._run_phase_with_empty_output_retry(
        agent_factory=lambda: object(),
        state={},
        question="q",
        session_service=None,
        on_event=None,
        output_key="diagnosis",
        phase_label="test phase",
    )
    assert success is True
    assert call_count["n"] == 2
    assert state["diagnosis"] == '{"second": "attempt"}'


@pytest.mark.asyncio
async def test_generic_retry_returns_failure_when_both_attempts_empty(monkeypatch):
    """Both attempts silently bail. Helper returns success=False;
    caller is responsible for writing a phase-appropriate sentinel."""
    from agentic_ops_v6 import orchestrator as orch

    call_count = {"n": 0}

    async def fake_run_phase(agent, state, question, session_service, on_event=None):
        call_count["n"] += 1
        return (state, [])  # never writes the output key

    monkeypatch.setattr(orch, "_run_phase", fake_run_phase)

    state, traces, success = await orch._run_phase_with_empty_output_retry(
        agent_factory=lambda: object(),
        state={},
        question="q",
        session_service=None,
        on_event=None,
        output_key="diagnosis",
        phase_label="test phase",
    )
    assert success is False
    assert call_count["n"] == 2
    assert "diagnosis" not in state


@pytest.mark.asyncio
async def test_generic_retry_returns_failure_when_first_raises_and_second_empty(monkeypatch):
    """Mixed failure path: first attempt raises (genuine ADK / Gemini
    error), second attempt silent-bails. Helper still treats both as
    failure and returns success=False without raising."""
    from agentic_ops_v6 import orchestrator as orch

    call_count = {"n": 0}

    async def fake_run_phase(agent, state, question, session_service, on_event=None):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("simulated Gemini error")
        return (state, [])  # silent-bail

    monkeypatch.setattr(orch, "_run_phase", fake_run_phase)

    state, traces, success = await orch._run_phase_with_empty_output_retry(
        agent_factory=lambda: object(),
        state={},
        question="q",
        session_service=None,
        on_event=None,
        output_key="diagnosis",
        phase_label="test phase",
    )
    assert success is False
    assert call_count["n"] == 2


@pytest.mark.asyncio
async def test_generic_retry_recreates_agent_each_attempt(monkeypatch):
    """The factory is called fresh on each attempt — re-instantiation
    is intentional (avoids any session-state side effects from a
    failed first call)."""
    from agentic_ops_v6 import orchestrator as orch

    factory_calls = {"n": 0}
    run_calls = {"n": 0}

    def factory():
        factory_calls["n"] += 1
        return object()

    async def fake_run_phase(agent, state, question, session_service, on_event=None):
        run_calls["n"] += 1
        return (state, [])  # silent-bail both times

    monkeypatch.setattr(orch, "_run_phase", fake_run_phase)

    await orch._run_phase_with_empty_output_retry(
        agent_factory=factory,
        state={},
        question="q",
        session_service=None,
        on_event=None,
        output_key="diagnosis",
        phase_label="test phase",
    )
    assert factory_calls["n"] == 2
    assert run_calls["n"] == 2
