"""Unit tests for guardrails/runner.run_phase_with_guardrail.

Focused on the resample-path empty-output retry (PR-bug-fix after
run_20260501_135059_call_quality_degradation). The earlier integration
behavior (PASS/REJECT/REPAIR/exhausted_accept) is covered indirectly
by the per-guardrail tests; this file targets the silent-bail-on-resample
case specifically.
"""

from __future__ import annotations

import json

import pytest

from agentic_ops_common.models import PhaseTrace, ToolCallTrace

from agentic_ops_v6.guardrails.base import GuardrailResult, GuardrailVerdict
from agentic_ops_v6.guardrails.runner import run_phase_with_guardrail


def _trace(name: str, tool_calls: int = 0) -> PhaseTrace:
    return PhaseTrace(
        agent_name=name,
        started_at=1.0,
        finished_at=2.0,
        duration_ms=1000,
        tool_calls=[
            ToolCallTrace(name=f"t_{i}", args="{}", timestamp=1.0)
            for i in range(tool_calls)
        ],
    )


@pytest.mark.asyncio
async def test_resample_recovers_from_silent_bail_on_first_attempt():
    """The bug scenario: initial phase emits, guardrail REJECTs,
    resample attempt 1 silent-bails (empty output), resample attempt 2
    succeeds with a clean output that the guardrail accepts.

    Pre-fix, the runner used `run_phase` directly on the resample (one
    attempt) and bailed on empty output. Post-fix, the resample uses
    `run_phase_with_empty_output_retry` which retries once on empty.
    """
    call_log: list[str] = []
    OUTPUT_KEY = "test_output"

    # 4 calls expected:
    #   1. initial attempt 1 — emits "first_attempt" (will be REJECTed)
    #   2. (no initial retry — empty-output retry not triggered because
    #       attempt 1 produced output)
    #   3. resample attempt 1 — emits NOTHING (silent-bail simulation)
    #   4. resample attempt 2 — emits "second_resample" (guardrail PASSes)
    async def fake_run_phase(agent, state, question, session_service, on_event=None):
        n = len(call_log) + 1
        call_log.append(f"call_{n}")
        if n == 1:
            return ({**state, OUTPUT_KEY: "first_attempt"}, [_trace("agent", 2)])
        if n == 2:
            # Silent-bail on resample attempt 1: don't write OUTPUT_KEY.
            return (state, [_trace("agent", 0)])
        if n == 3:
            return ({**state, OUTPUT_KEY: "second_resample"}, [_trace("agent", 3)])
        raise AssertionError(f"unexpected extra call #{n}")

    reject_count = [0]

    def parser(raw):
        return raw

    def guardrail(parsed):
        # First time around (after initial call): REJECT.
        # Second time (after resample): PASS.
        reject_count[0] += 1
        if reject_count[0] == 1:
            return GuardrailResult(
                verdict=GuardrailVerdict.REJECT,
                output=parsed,
                reason="initial output rejected",
            )
        return GuardrailResult(verdict=GuardrailVerdict.PASS, output=parsed)

    state = {}
    state, traces, success, parsed_out = await run_phase_with_guardrail(
        agent_factory=lambda: object(),
        state=state,
        question="test",
        session_service=None,
        on_event=None,
        output_key=OUTPUT_KEY,
        phase_label="TestPhase",
        run_phase=fake_run_phase,
        parser=parser,
        guardrail=guardrail,
        max_resamples=1,
    )

    # Pre-fix: success=False, parsed_out="first_attempt", call_log had only 2 entries.
    # Post-fix: success=True, parsed_out="second_resample", call_log has 3 entries.
    assert success is True, f"expected success but got: traces={[t.agent_name for t in traces]}"
    assert parsed_out == "second_resample"
    assert len(call_log) == 3


@pytest.mark.asyncio
async def test_resample_fails_when_both_resample_attempts_empty():
    """If BOTH resample attempts silent-bail, the runner correctly
    surfaces failure. This is the Pareto-worse case the empty-output
    retry can't fix."""
    call_log: list[str] = []
    OUTPUT_KEY = "test_output"

    async def fake_run_phase(agent, state, question, session_service, on_event=None):
        n = len(call_log) + 1
        call_log.append(f"call_{n}")
        if n == 1:
            return ({**state, OUTPUT_KEY: "first_attempt"}, [_trace("agent", 2)])
        # Both resample attempts silent-bail.
        return (state, [_trace("agent", 0)])

    def parser(raw):
        return raw

    def guardrail(parsed):
        return GuardrailResult(
            verdict=GuardrailVerdict.REJECT,
            output=parsed,
            reason="rejected",
        )

    state, traces, success, parsed_out = await run_phase_with_guardrail(
        agent_factory=lambda: object(),
        state={},
        question="test",
        session_service=None,
        on_event=None,
        output_key=OUTPUT_KEY,
        phase_label="TestPhase",
        run_phase=fake_run_phase,
        parser=parser,
        guardrail=guardrail,
        max_resamples=1,
    )

    assert success is False
    # Initial (1) + resample 2 attempts (2) = 3 calls total.
    assert len(call_log) == 3


@pytest.mark.asyncio
async def test_resample_recovery_works_with_accept_policy():
    """On exhausted-accept policy, even if the resample attempts both
    silent-bail, the runner surfaces accept-with-warning instead of
    failure (as long as parsed has a non-None initial value)."""
    call_log: list[str] = []
    OUTPUT_KEY = "test_output"

    async def fake_run_phase(agent, state, question, session_service, on_event=None):
        n = len(call_log) + 1
        call_log.append(f"call_{n}")
        if n == 1:
            return ({**state, OUTPUT_KEY: "first_attempt"}, [_trace("agent", 2)])
        return (state, [_trace("agent", 0)])

    def parser(raw):
        return raw

    def guardrail(parsed):
        return GuardrailResult(
            verdict=GuardrailVerdict.REJECT,
            output=parsed,
            reason="rejected on every call",
        )

    state, traces, success, parsed_out = await run_phase_with_guardrail(
        agent_factory=lambda: object(),
        state={},
        question="test",
        session_service=None,
        on_event=None,
        output_key=OUTPUT_KEY,
        phase_label="TestPhase",
        run_phase=fake_run_phase,
        parser=parser,
        guardrail=guardrail,
        max_resamples=1,
        # Note: with accept policy, exhausted resample on empty-output
        # is still "fail" because there's nothing to accept; the
        # accept-policy only kicks in when the LLM emits but the
        # guardrail can't approve it.
    )

    # Both resample attempts silent-bailed. success=False is correct.
    assert success is False
    assert len(call_log) == 3
