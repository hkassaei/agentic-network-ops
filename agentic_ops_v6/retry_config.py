"""Shared HTTP retry configuration for v6 LlmAgents.

Per Google ADK guidance for handling 429 RESOURCE_EXHAUSTED:
https://google.github.io/adk-docs/agents/models/google-gemini/#error-code-429-resource_exhausted

Vertex AI returns 429 when a request exceeds the quota allocated for the
model in the active project / region. This is most common for us in
Phase 5, where the orchestrator fans out 1–3 InvestigatorAgent calls in
parallel — each consumes ~50–60k tokens with thinking — and the burst can
exceed per-minute quotas even when the per-day budget is fine.

We enable client-side retry with exponential backoff on every LlmAgent
that calls Gemini. The defaults handle transient quota exhaustion
gracefully without the orchestrator needing to know anything about it.

Failure modes to call out, since these aren't visible from the docs:
  - The retry is per-LLM-call. A multi-turn agent (NA, Investigator)
    that internally makes several LLM calls will retry each one
    independently — so a sustained quota burst can multiply the
    effective wall-clock cost of a phase.
  - 408 / 5xx are also retried by default. That's what we want for
    transient infrastructure issues, but it means we can't tell from
    the trace alone whether a slow phase was due to model latency or
    retried failures. If you need that signal, capture the per-attempt
    timing separately.
"""

from __future__ import annotations

from google.genai import types


# HTTP status codes that should trigger a retry. The Vertex AI defaults
# are (408, 429, 5xx) when this field is omitted; we declare them
# explicitly so future readers don't have to dig.
_RETRYABLE_STATUS_CODES: list[int] = [
    408,  # Request Timeout
    429,  # Too Many Requests / RESOURCE_EXHAUSTED
    500,  # Internal Server Error
    502,  # Bad Gateway
    503,  # Service Unavailable
    504,  # Gateway Timeout
]

# Total attempts including the initial call. With exp_base=2.0 and
# initial_delay=2.0s, the wait pattern is approximately:
#   attempt 1 → fail → wait ~2s
#   attempt 2 → fail → wait ~4s
#   attempt 3 → fail → wait ~8s
#   attempt 4 → fail → wait ~16s
#   attempt 5 → fail → give up
# Cumulative max wait is ~30s before giving up. Most 429s clear within
# 1–2 retries; the deeper backoff is insurance against a sustained
# quota burst from parallel investigators.
_DEFAULT_ATTEMPTS = 5


def make_retry_config() -> types.GenerateContentConfig:
    """Build a `GenerateContentConfig` whose only effect is enabling
    HTTP retries on transient errors.

    Pass the result to `LlmAgent(generate_content_config=...)`. Do NOT
    set `tools`, `system_instruction`, or `response_schema` on this
    config — ADK validates against those at agent-construction time
    and raises ValueError. They go on the LlmAgent itself.
    """
    return types.GenerateContentConfig(
        http_options=types.HttpOptions(
            retry_options=types.HttpRetryOptions(
                attempts=_DEFAULT_ATTEMPTS,
                initial_delay=2.0,
                max_delay=60.0,
                exp_base=2.0,
                jitter=1.0,
                http_status_codes=_RETRYABLE_STATUS_CODES,
            ),
        ),
    )
