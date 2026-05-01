"""Empty-output detection + one-shot resample for LlmAgent phases.

ADK's `LlmAgent.__maybe_save_output_to_state` silently bails (returns
without raising, without writing `state[output_key]`) when Gemini emits a
final-response chunk whose text content is empty or whitespace-only. See
`agents/llm_agent.py` `if not result.strip(): return` in google-adk. The
`_run_phase` wrapper catches genuine exceptions but cannot detect that
silent-bail path. This module provides:

  * `output_present(state, key)` — generic detector.
  * `ig_output_present(state)` — IG-specific thin wrapper kept for the
    legacy test suite.
  * `run_phase_with_empty_output_retry(...)` — generic phase runner with
    one-shot resample on empty output.
  * `run_ig_with_retry(...)` — IG-specific wrapper that writes a
    structured sentinel into `state[IG_OUTPUT_KEY]` on double-failure
    so the recorder shows the failure verbatim and Phase 5 runs with
    `plans=[]` instead of fabricating citations from a missing key.

The `_run_phase` callable is injected as a parameter rather than imported,
to keep this module decoupled from orchestrator internals (and to make
the helpers trivially mockable in unit tests).
"""

from __future__ import annotations

import json
import logging
from typing import Any, Awaitable, Callable

from google.adk.sessions import InMemorySessionService

from agentic_ops_common.models import PhaseTrace

log = logging.getLogger("v6.guardrails.empty_output")


# Output keys each LlmAgent phase writes via its `output_key`. Constants
# kept here so the generic retry helper, the IG-specific wrapper, and the
# orchestrator agree on the exact key names. If a subagent's `output_key`
# changes, update the matching constant in the same commit.
NA_OUTPUT_KEY = "network_analysis"
IG_OUTPUT_KEY = "falsification_plan_set"
INVESTIGATOR_OUTPUT_KEY = "investigator_verdict"
SYNTHESIS_OUTPUT_KEY = "diagnosis"


# Type alias: the orchestrator's `_run_phase` signature. Parameterized
# here so this module does not import the orchestrator (avoids circular
# imports and lets the helpers be unit-tested with a stub runner).
RunPhaseFn = Callable[
    ...,
    Awaitable[tuple[dict[str, Any], list[PhaseTrace]]],
]


def output_present(state: dict, key: str) -> bool:
    """Did the named LlmAgent phase write a non-empty output to state?

    Treat "missing", "None", and "empty/whitespace string" as failure.
    A non-empty value is taken at face value here; downstream parsing
    in each phase does its own schema validation.
    """
    raw = state.get(key)
    if raw is None:
        return False
    if isinstance(raw, str):
        return bool(raw.strip())
    return True


def ig_output_present(state: dict) -> bool:
    """Backward-compat wrapper for the IG-specific tests. Prefer
    `output_present(state, IG_OUTPUT_KEY)` in new code."""
    return output_present(state, IG_OUTPUT_KEY)


async def run_phase_with_empty_output_retry(
    agent_factory,
    state: dict[str, Any],
    question: str,
    session_service: InMemorySessionService,
    on_event,
    output_key: str,
    phase_label: str,
    *,
    run_phase: RunPhaseFn,
) -> tuple[dict[str, Any], list[PhaseTrace], bool]:
    """Run an LlmAgent phase with one retry on empty-output silent-bail.

    Two failure modes are handled:
      1. `run_phase` raises an exception (genuine ADK / Gemini error).
      2. `run_phase` returns successfully but `state[output_key]` is
         unset / empty — the silent-bail path described in
         `output_present`. This is the failure shape originally
         observed in run_20260429_031341 (IG, Phase 4) and again in
         run_20260430_020337 (NA, Phase 3). Both runs were
         indistinguishable from success at the orchestrator level
         until this guard was generalized.

    Either failure triggers ONE retry. If both attempts fail, the
    function returns `success=False` and the caller is responsible
    for writing a phase-appropriate sentinel into `state[output_key]`
    so the recorder can surface the failure instead of silently
    flowing forward with an empty value.

    Why each retry creates a fresh agent via `agent_factory` rather
    than reusing the same instance: the IG retry experience showed
    that re-instantiation is consistently safer than re-running the
    same agent object (avoids any session-state side effects from
    the failed attempt).

    Returns:
      (state, combined_traces, success).

    `combined_traces` aggregates the traces from BOTH attempts so the
    recorder shows the retry attempt explicitly. Caller must extend
    its `all_phases` list and call `_accumulate_phase_traces` once
    (the helper does NOT, to keep coupling to the outer trace
    plumbing minimal).
    """
    combined_traces: list[PhaseTrace] = []

    # Attempt 1
    try:
        state, traces = await run_phase(
            agent_factory(), state, question, session_service, on_event,
        )
        combined_traces.extend(traces)
    except Exception as e:
        log.error("%s attempt 1 failed: %s", phase_label, e, exc_info=True)
        state.pop(output_key, None)

    if output_present(state, output_key):
        return state, combined_traces, True

    # Attempt 2 — same call, same prompt. The bug is non-deterministic
    # (Gemini sometimes emits a thinking-only final chunk that ADK
    # strips). A second roll usually succeeds.
    log.warning(
        "%s produced no output on attempt 1 — retrying once. "
        "ADK silently bails when Gemini emits an empty final-response "
        "chunk; see agents/llm_agent.py `if not result.strip(): return`.",
        phase_label,
    )
    try:
        state, traces = await run_phase(
            agent_factory(), state, question, session_service, on_event,
        )
        combined_traces.extend(traces)
    except Exception as e:
        log.error("%s attempt 2 failed: %s", phase_label, e, exc_info=True)
        state.pop(output_key, None)

    if output_present(state, output_key):
        return state, combined_traces, True

    log.error("%s produced no output on both attempts.", phase_label)
    return state, combined_traces, False


async def run_ig_with_retry(
    state: dict[str, Any],
    question: str,
    session_service: InMemorySessionService,
    on_event,
    all_phases: list[PhaseTrace],
    *,
    run_phase: RunPhaseFn,
    accumulate_traces: Callable[[dict, list[PhaseTrace]], None],
    create_instruction_generator: Callable[[], Any],
    parse_plan_set: Callable[[Any], Any],
    empty_plan_set: Callable[[], Any],
):
    """IG-specific wrapper around `run_phase_with_empty_output_retry`.

    On both-attempts-failed, writes the IG-specific sentinel into
    `state[IG_OUTPUT_KEY]` so the recorder shows the failure verbatim
    in Phase 4 of the report and downstream parsing treats it as an
    empty plan_set. Phase 5 then runs with no plan rather than with a
    silently-missing key that produces fabricated-citations verdicts.

    The IG-specific dependencies (agent factory, plan-set parser,
    sentinel constructor, trace accumulator) are injected to keep this
    module free of orchestrator imports.
    """
    state, traces, success = await run_phase_with_empty_output_retry(
        agent_factory=create_instruction_generator,
        state=state,
        question=question,
        session_service=session_service,
        on_event=on_event,
        output_key=IG_OUTPUT_KEY,
        phase_label="Phase 4 InstructionGenerator",
        run_phase=run_phase,
    )
    all_phases.extend(traces)
    accumulate_traces(state, traces)

    if success:
        return state, parse_plan_set(state.get(IG_OUTPUT_KEY))

    state[IG_OUTPUT_KEY] = json.dumps({
        "plans": [],
        "_orchestrator_note": (
            "InstructionGenerator produced empty output on two consecutive "
            "attempts. ADK's silent-bail on empty Gemini final-response "
            "(agents/llm_agent.py:__maybe_save_output_to_state) prevented "
            "the schema-validation error from surfacing. No falsification "
            "plan was generated; Phase 5 ran with no probes."
        ),
    })
    return state, empty_plan_set()
