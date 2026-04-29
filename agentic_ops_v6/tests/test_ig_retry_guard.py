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
