"""Phase runner with optional post-emit guardrail.

`run_phase_with_guardrail` extends `run_phase_with_empty_output_retry`
with a deterministic post-emit guardrail step. The composed flow is:

  1. Run the phase (with the existing empty-output retry).
  2. Parse the typed output.
  3. Run the guardrail.
     PASS    → return parsed output.
     REPAIR  → return the guardrail's repaired output.
     REJECT  → resample once with `result.reason` injected into the
               agent's session state for the prompt to read; re-parse;
               re-run the guardrail.

When the resample budget is exhausted on a still-REJECT result, the
caller picks the policy via `on_guardrail_exhausted`:

  * `"fail"` (default) — surfaced as `success=False`; caller writes a
    sentinel into `state[output_key]`. Right for guardrails whose
    failure means the downstream pipeline cannot meaningfully continue.
  * `"accept"` — surfaced as `success=True` with the last-emitted
    output, plus a structured warning (synthetic PhaseTrace AND a
    `guardrail_warnings` list appended to state). Right for guardrails
    whose failure means downstream sees a less-than-ideal-but-usable
    output (e.g. the NA hypothesis-statement linter — a mechanism-scoped
    statement is worse than a clean one but better than no NA report
    at all).

Each guardrail outcome is captured as a synthetic PhaseTrace so the
recorder surfaces every check the same way it surfaces phase outputs.
The resample budget defaults to 1; raising it requires an explicit
caller decision.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Literal

from google.adk.sessions import InMemorySessionService

from agentic_ops_common.models import PhaseTrace

from .base import GuardrailResult, GuardrailVerdict
from .empty_output import (
    RunPhaseFn,
    output_present,
    run_phase_with_empty_output_retry,
)

log = logging.getLogger("v6.guardrails.runner")


# Key the guardrail-driven resample writes its rejection reason into.
# The agent's prompt template can read it as `{guardrail_rejection_reason}`
# to incorporate the reason into the next attempt.
GUARDRAIL_REASON_KEY = "guardrail_rejection_reason"

# Top-level state key carrying structured warnings the recorder surfaces in
# the episode log. Each entry is one dict per exhausted-accept guardrail
# outcome. Always a list (initialized lazily by the runner) so callers and
# the recorder can iterate without checking presence.
GUARDRAIL_WARNINGS_KEY = "guardrail_warnings"


async def run_phase_with_guardrail(
    agent_factory: Callable[[], Any],
    state: dict[str, Any],
    question: str,
    session_service: InMemorySessionService,
    on_event,
    output_key: str,
    phase_label: str,
    *,
    run_phase: RunPhaseFn,
    parser: Callable[[Any], Any] | None = None,
    guardrail: Callable[[Any], GuardrailResult] | None = None,
    max_resamples: int = 1,
    on_guardrail_exhausted: Literal["fail", "accept"] = "fail",
) -> tuple[dict[str, Any], list[PhaseTrace], bool, Any]:
    """Run a phase with empty-output retry and an optional post-emit guardrail.

    Returns:
        (state, combined_traces, success, parsed_output)

    `success` is False if the empty-output retry exhausted both attempts,
    OR if every guardrail-driven resample was REJECTed AND
    `on_guardrail_exhausted="fail"`. With `on_guardrail_exhausted="accept"`
    a still-rejected resample returns `success=True` carrying the last
    parsed output, plus a structured warning entry appended to
    `state[GUARDRAIL_WARNINGS_KEY]` for the recorder.

    Caller is responsible for writing a phase-appropriate sentinel into
    `state[output_key]` on success=False (matches the existing
    `run_phase_with_empty_output_retry` contract).

    `parsed_output` is the parser's output on the final accepted state
    (or `None` if no parser was supplied; or the parser's output on a
    failed run, which is typically a sentinel).
    """
    state, combined_traces, success = await run_phase_with_empty_output_retry(
        agent_factory=agent_factory,
        state=state,
        question=question,
        session_service=session_service,
        on_event=on_event,
        output_key=output_key,
        phase_label=phase_label,
        run_phase=run_phase,
    )

    parsed = parser(state.get(output_key)) if parser else None

    # No guardrail or empty-output already failed → return as-is. With
    # `guardrail is None` this branch makes the helper a transparent
    # superset of `run_phase_with_empty_output_retry`.
    if guardrail is None or not success:
        return state, combined_traces, success, parsed

    resamples_used = 0
    while True:
        try:
            result = guardrail(parsed)
        except Exception as e:
            log.error(
                "%s guardrail raised %s — treating as PASS to avoid masking bugs",
                phase_label, e, exc_info=True,
            )
            _append_guardrail_trace(
                combined_traces, phase_label,
                verdict="error", reason=f"guardrail raised: {e}",
            )
            return state, combined_traces, success, parsed

        _append_guardrail_trace(
            combined_traces, phase_label,
            verdict=result.verdict.value, reason=result.reason,
        )

        if result.verdict is GuardrailVerdict.PASS:
            return state, combined_traces, success, parsed

        if result.verdict is GuardrailVerdict.REPAIR:
            return state, combined_traces, success, result.output

        # REJECT — resample once (or up to max_resamples).
        if resamples_used >= max_resamples:
            if on_guardrail_exhausted == "accept":
                log.warning(
                    "%s guardrail rejected output and resample budget (%d) "
                    "is exhausted; ACCEPTING with structured warning per "
                    "policy. Reason on final attempt: %s",
                    phase_label, max_resamples, result.reason,
                )
                _append_guardrail_trace(
                    combined_traces, phase_label,
                    verdict="exhausted_accepted",
                    reason=result.reason,
                )
                _append_warning(
                    state,
                    phase_label=phase_label,
                    attempts=resamples_used + 1,
                    reason=result.reason,
                    notes=result.notes,
                )
                return state, combined_traces, success, parsed
            log.error(
                "%s guardrail rejected output and resample budget (%d) is "
                "exhausted; surfacing as failure.",
                phase_label, max_resamples,
            )
            return state, combined_traces, False, parsed

        resamples_used += 1
        log.warning(
            "%s guardrail REJECT — resampling (%d/%d). Reason: %s",
            phase_label, resamples_used, max_resamples, result.reason,
        )
        # Inject the rejection reason into session state so the agent's
        # prompt template can read it on the next attempt.
        state[GUARDRAIL_REASON_KEY] = result.reason
        # Drop the previous output_key so empty-output retry can detect
        # an actual emit on the resample.
        state.pop(output_key, None)

        try:
            new_state, new_traces = await run_phase(
                agent_factory(), state, question, session_service, on_event,
            )
            state = new_state
            combined_traces.extend(new_traces)
        except Exception as e:
            log.error(
                "%s resample %d failed: %s",
                phase_label, resamples_used, e, exc_info=True,
            )
            return state, combined_traces, False, parsed

        if not output_present(state, output_key):
            log.error(
                "%s resample %d produced empty output; surfacing as failure.",
                phase_label, resamples_used,
            )
            return state, combined_traces, False, parsed

        parsed = parser(state.get(output_key)) if parser else None
        # Loop re-runs the guardrail on the resampled output.


def _append_guardrail_trace(
    traces: list[PhaseTrace],
    phase_label: str,
    *,
    verdict: str,
    reason: str,
) -> None:
    """Synthesize a PhaseTrace entry for a guardrail outcome.

    Same pattern the orchestrator already uses for the Phase 5 fan-out
    audit: a zero-duration synthetic trace whose agent_name names the
    guardrail and whose output_summary carries the verdict + reason.
    """
    now = time.time()
    summary = verdict if not reason else f"{verdict}: {reason}"
    traces.append(PhaseTrace(
        agent_name=f"{phase_label}__guardrail",
        started_at=now,
        finished_at=now,
        duration_ms=0,
        output_summary=summary,
    ))


def _append_warning(
    state: dict[str, Any],
    *,
    phase_label: str,
    attempts: int,
    reason: str,
    notes: dict[str, Any],
) -> None:
    """Append a structured warning entry to `state[GUARDRAIL_WARNINGS_KEY]`.

    Surfaces in the episode log alongside the synthetic PhaseTrace so a
    reader can see WHY the linter / calibrator / etc. accepted a
    less-than-ideal output rather than only seeing the trace entry.

    Each entry is a flat dict so the recorder can render it as a row
    without recursive walking. `notes` from the GuardrailResult is
    nested in case a guardrail wants to expose structured per-flag
    detail (e.g. the linter's per-hypothesis hits dict).
    """
    warnings = state.setdefault(GUARDRAIL_WARNINGS_KEY, [])
    warnings.append({
        "phase": phase_label,
        "attempts": attempts,
        "reason": reason,
        "notes": dict(notes) if notes else {},
    })
