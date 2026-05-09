"""Shared HTTP retry configuration for v6 LlmAgents.

Per Google ADK guidance for handling 429 RESOURCE_EXHAUSTED:
https://google.github.io/adk-docs/agents/models/google-gemini/#error-code-429-resource_exhausted

Vertex AI returns 429 when a request exceeds the quota allocated for the
model in the active project / region. This is most common for us in
Phase 5, where the orchestrator fans out 1–3 InvestigatorAgent calls in
parallel — each consumes ~50–60k tokens with thinking — and the burst can
exceed per-minute quotas even when the per-day budget is fine.

## Why we use Option 2 (Gemini model instance), not Option 1 (config)

The ADK docs describe two mechanisms for enabling retry:

  Option 1: `generate_content_config.http_options.retry_options` on each
            agent.
  Option 2: `Gemini(retry_options=...)` model wrapper.

We use Option 2. Option 1 looks plausible but does not actually work:
  - ADK builds the api_client (`google.genai.Client`) once at first use,
    reading `retry_options` from the `Gemini` model wrapper field at
    construction time (see `google/adk/models/google_llm.py` lines
    298–319).
  - The genai SDK honors retry at the client level. Per-request
    http_options on `generate_content(config=...)` is processed but
    the retry behavior was already locked in when the Client was built.
  - Setting `agent.generate_content_config.http_options.retry_options`
    at agent-construction time therefore has no observable effect on
    actual retry behavior — even though it passes ADK's config
    validators and round-trips through the request object.

The smoking gun: the Apr-29 batch's `data_plane_degradation` run hit
429 RESOURCE_EXHAUSTED on InvestigatorAgent_h2 with `tool_calls=0,
llm_calls=0` (h2 absent from the per-phase breakdown). If retry had
engaged at all, h2 would have at least one billable call. It had none.

Option 2 is the path the ADK source explicitly documents in its own
`Gemini.retry_options` docstring sample. Use it.

## Backoff schedule

With the defaults below, on a sustained quota burst:
  attempt 1 → fail → wait ~2s
  attempt 2 → fail → wait ~4s
  attempt 3 → fail → wait ~8s
  attempt 4 → fail → wait ~16s
  attempt 5 → fail → wait ~32s
  attempt 6 → fail → wait ~60s (capped at max_delay)
  attempt 7 → fail → wait ~60s
  attempt 8 → fail → give up

Cumulative max wait: ~3 minutes before any single call gives up.
Phase 5 with 3 parallel investigators can survive a ~3-minute quota
burst from one investigator without losing the other two.
"""

from __future__ import annotations

from google.adk.models.google_llm import Gemini
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

# Total attempts including the initial call. Bumped from the previous
# (Option 1) value of 5 because parallel investigators can collectively
# sustain a quota burst longer than 30 seconds.
_DEFAULT_ATTEMPTS = 8


def _make_retry_options() -> types.HttpRetryOptions:
    return types.HttpRetryOptions(
        attempts=_DEFAULT_ATTEMPTS,
        initial_delay=2.0,
        max_delay=60.0,
        exp_base=2.0,
        jitter=1.0,
        http_status_codes=_RETRYABLE_STATUS_CODES,
    )


def make_retry_model(model_name: str = "gemini-2.5-pro") -> Gemini:
    """Build a `Gemini` model wrapper with retry on 429 / 408 / 5xx.

    Pass the result to `LlmAgent(model=...)`. The retry options are
    set on the underlying `google.genai.Client` at construction time —
    see module docstring for why this works and the per-request config
    path does not.
    """
    return Gemini(
        model=model_name,
        retry_options=_make_retry_options(),
    )
