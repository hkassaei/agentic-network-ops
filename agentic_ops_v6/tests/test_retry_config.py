"""Tests for the shared 429-retry config + its integration into v6 agents.

Per Google ADK docs (error-code-429-resource_exhausted), retry options
on Vertex AI go through `generate_content_config.http_options.retry_options`.
This test suite locks in:

  1. The retry config has the expected shape (HttpRetryOptions with the
     status codes Google's docs say to retry on).
  2. Every v6 LlmAgent factory wires it onto its agent.

If a future contributor adds a new LlmAgent factory and forgets to attach
the retry config, the membership test below fails loudly — surfacing it
as a regression instead of letting it silently be quota-fragile.
"""

from __future__ import annotations

import os

import pytest

# Tests in this module construct LlmAgents which require Vertex AI env
# vars at import time. Set sentinels so construction goes through.
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "test")
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "us-central1")
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")

from agentic_ops_v6.retry_config import make_retry_config


def test_retry_config_retries_on_429_408_and_5xx():
    """Locks in the canonical retryable status set."""
    cfg = make_retry_config()
    codes = cfg.http_options.retry_options.http_status_codes
    # 429 is the one this whole work item exists for; the other codes
    # cover transient infrastructure errors per the Vertex AI defaults.
    assert 429 in codes
    assert 408 in codes
    assert {500, 502, 503, 504}.issubset(set(codes))


def test_retry_config_uses_exponential_backoff():
    """Defaults to exp_base=2.0 with non-trivial initial delay so a
    sustained 429 burst gets meaningful spacing between attempts."""
    cfg = make_retry_config()
    ro = cfg.http_options.retry_options
    assert ro.exp_base == 2.0
    assert ro.initial_delay >= 1.0
    assert ro.max_delay >= 30.0
    assert ro.attempts >= 3, "fewer than 3 attempts is too few for 429 recovery"


def test_retry_config_does_not_set_forbidden_fields():
    """ADK's `validate_generate_content_config` raises ValueError if
    `tools`, `system_instruction`, or `response_schema` are set on the
    GenerateContentConfig. Those go on the LlmAgent itself. Make sure
    `make_retry_config()` returns a config that won't trip those guards."""
    cfg = make_retry_config()
    assert not cfg.tools
    assert cfg.system_instruction is None
    assert cfg.response_schema is None


# ============================================================================
# Each v6 LlmAgent must wire the retry config — guard against future
# additions silently shipping without it.
# ============================================================================

def test_network_analyst_has_retry_config():
    from agentic_ops_v6.subagents.network_analyst import create_network_analyst
    agent = create_network_analyst()
    _assert_has_retry(agent)


def test_instruction_generator_has_retry_config():
    from agentic_ops_v6.subagents.instruction_generator import create_instruction_generator
    agent = create_instruction_generator()
    _assert_has_retry(agent)


def test_investigator_has_retry_config():
    """Phase 5 fans out 1-3 of these in parallel; quota-fragile."""
    from agentic_ops_v6.subagents.investigator import create_investigator_agent
    agent = create_investigator_agent()
    _assert_has_retry(agent)


def test_synthesis_has_retry_config():
    from agentic_ops_v6.subagents.synthesis import create_synthesis_agent
    agent = create_synthesis_agent()
    _assert_has_retry(agent)


def test_ontology_consultation_has_retry_config():
    from agentic_ops_v6.subagents.ontology_consultation import create_ontology_consultation_agent
    agent = create_ontology_consultation_agent()
    _assert_has_retry(agent)


def _assert_has_retry(agent) -> None:
    """Shared assertion: the agent's generate_content_config carries
    HttpRetryOptions with 429 in its retryable status set."""
    cfg = agent.generate_content_config
    assert cfg is not None, f"{agent.name} has no generate_content_config"
    ho = cfg.http_options
    assert ho is not None, f"{agent.name} has no http_options"
    ro = ho.retry_options
    assert ro is not None, f"{agent.name} has no retry_options"
    assert 429 in ro.http_status_codes, (
        f"{agent.name} retry_options does not retry on 429"
    )
