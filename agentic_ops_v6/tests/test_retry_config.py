"""Tests for the 429 retry configuration on v6 LlmAgents.

The retry mechanism that ADK actually honors is `Gemini.retry_options`
on the model wrapper passed to `LlmAgent(model=...)`. The earlier
`generate_content_config.http_options.retry_options` approach (Option 1
in Google's docs) round-trips through the request object but does not
affect retry behavior because ADK's api_client is built once with
retry_options taken from the Gemini wrapper. See
`agentic_ops_v6/retry_config.py` for the full reasoning.

These tests verify:
  1. `make_retry_model()` returns a `Gemini` instance with retry_options
     set to retry on 429 / 408 / 5xx with exponential backoff.
  2. Each of the 5 v6 LlmAgent factories wires a Gemini-with-retry as
     its model — guarding against silent regression where someone adds
     a new agent or refactors back to a bare model name string.
"""

from __future__ import annotations

import os

import pytest

# Tests in this module construct LlmAgents which require Vertex AI env
# vars at import time. Set sentinels so construction goes through.
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "test")
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "us-central1")
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")

from agentic_ops_v6.retry_config import make_retry_model


# ============================================================================
# `make_retry_model()` — the helper itself
# ============================================================================

def test_make_retry_model_returns_gemini_instance():
    from google.adk.models.google_llm import Gemini
    model = make_retry_model("gemini-2.5-pro")
    assert isinstance(model, Gemini), (
        f"expected Gemini instance, got {type(model).__name__}. "
        "ADK's retry path requires a Gemini model wrapper, NOT a "
        "GenerateContentConfig — see retry_config.py module docstring."
    )


def test_make_retry_model_carries_retry_options():
    """Without retry_options on the Gemini instance, ADK's api_client
    is built with retry disabled (the previous default). This is the
    single load-bearing assertion of the whole retry mechanism."""
    model = make_retry_model("gemini-2.5-pro")
    assert model.retry_options is not None, (
        "Gemini.retry_options is None — retry will not engage at all"
    )


def test_make_retry_model_retries_on_429_408_and_5xx():
    """Locks in the canonical retryable status set."""
    model = make_retry_model("gemini-2.5-pro")
    codes = model.retry_options.http_status_codes
    assert 429 in codes, "must retry on 429 RESOURCE_EXHAUSTED"
    assert 408 in codes
    assert {500, 502, 503, 504}.issubset(set(codes))


def test_make_retry_model_uses_exponential_backoff_with_enough_attempts():
    """Defaults must give a sustained quota burst time to clear.
    Less than 5 attempts is too few; less than ~30s cumulative wait
    is shorter than a typical Vertex AI quota window."""
    ro = make_retry_model("gemini-2.5-pro").retry_options
    assert ro.exp_base == 2.0, "expected exponential backoff with base 2"
    assert ro.initial_delay >= 1.0
    assert ro.max_delay >= 30.0
    assert ro.attempts >= 5, "fewer than 5 attempts is too few for sustained 429"


def test_make_retry_model_passes_through_model_name():
    """OntologyConsultationAgent uses gemini-2.5-flash; the rest use
    gemini-2.5-pro. The helper must respect the requested model name
    rather than hard-coding it."""
    pro = make_retry_model("gemini-2.5-pro")
    flash = make_retry_model("gemini-2.5-flash")
    assert pro.model == "gemini-2.5-pro"
    assert flash.model == "gemini-2.5-flash"


# ============================================================================
# Each v6 LlmAgent must wire the Gemini-with-retry model — guard against
# future additions silently shipping without it.
# ============================================================================

def test_network_analyst_uses_retry_model():
    from agentic_ops_v6.subagents.network_analyst import create_network_analyst
    _assert_uses_retry_model(create_network_analyst())


def test_instruction_generator_uses_retry_model():
    from agentic_ops_v6.subagents.instruction_generator import (
        create_instruction_generator,
    )
    _assert_uses_retry_model(create_instruction_generator())


def test_investigator_uses_retry_model():
    """Phase 5 fans out 1-3 of these in parallel; quota-fragile."""
    from agentic_ops_v6.subagents.investigator import create_investigator_agent
    _assert_uses_retry_model(create_investigator_agent())


def test_synthesis_uses_retry_model():
    from agentic_ops_v6.subagents.synthesis import create_synthesis_agent
    _assert_uses_retry_model(create_synthesis_agent())


def test_ontology_consultation_uses_retry_model():
    from agentic_ops_v6.subagents.ontology_consultation import (
        create_ontology_consultation_agent,
    )
    _assert_uses_retry_model(create_ontology_consultation_agent())


def _assert_uses_retry_model(agent) -> None:
    """Shared assertion: the agent's model is a Gemini instance with
    retry_options that retries on 429.

    A bare-string model field (e.g. `model="gemini-2.5-pro"`) makes
    ADK construct a default Gemini with `retry_options=None`, which is
    the silent-no-retry trap this whole module is preventing.
    """
    from google.adk.models.google_llm import Gemini

    model = agent.model
    assert isinstance(model, Gemini), (
        f"{agent.name} has model={model!r} (type {type(model).__name__}). "
        "Must be a Gemini instance from `make_retry_model(...)`. A bare "
        "model-name string makes ADK build the api_client with "
        "retry_options=None, so 429 errors crash the agent on first call."
    )
    ro = model.retry_options
    assert ro is not None, (
        f"{agent.name}'s Gemini wrapper has retry_options=None"
    )
    assert 429 in ro.http_status_codes, (
        f"{agent.name}'s retry_options does not retry on 429"
    )
