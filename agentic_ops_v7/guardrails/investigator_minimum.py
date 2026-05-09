"""Force INCONCLUSIVE on sub-Investigators that didn't probe enough.

A sub-Investigator that emits a verdict after fewer than the configured
minimum number of tool calls has produced an LLM judgment without
adequate evidence. The orchestrator discards the self-reported verdict
and substitutes an INCONCLUSIVE verdict whose reasoning explicitly
names the guardrail that fired.

This mirrors a long-standing recurring failure where Gemini emits a
confident DISPROVEN / NOT_DISPROVEN verdict after one tool call (or
zero, in fabricated-citation runs). Tool-call count is a deterministic
signal — the count comes from the agent's own PhaseTrace, not from
self-report — so the guardrail is robust to whatever the LLM claims in
its reasoning text.

PR 1 lifts the check out of the orchestrator with no semantic change.
The minimum (currently 2) and the reasoning string match the
pre-extraction version byte-for-byte.
"""

from __future__ import annotations

import logging

from ..models import InvestigatorVerdict

log = logging.getLogger("v6.guardrails.investigator_minimum")


# Minimum tool calls a sub-Investigator must make before its
# self-reported verdict is trusted. Below this, the verdict is forced
# to INCONCLUSIVE.
MIN_TOOL_CALLS_PER_INVESTIGATOR = 2


def apply_min_tool_call_guardrail(
    verdict: InvestigatorVerdict,
    *,
    agent_name: str,
    tool_call_count: int,
    hypothesis_id: str,
    hypothesis_statement: str,
    min_required: int = MIN_TOOL_CALLS_PER_INVESTIGATOR,
) -> InvestigatorVerdict:
    """Return either `verdict` unchanged or a forced-INCONCLUSIVE
    verdict if `tool_call_count` is below `min_required`.

    The forced-INCONCLUSIVE verdict carries the same `hypothesis_id`
    and `hypothesis_statement` so downstream consumers see a
    well-formed verdict object even when the substitution fires.
    """
    if tool_call_count >= min_required:
        return verdict

    log.warning(
        "Sub-Investigator %s made %d tool calls (<%d) — "
        "forcing verdict to INCONCLUSIVE",
        agent_name, tool_call_count, min_required,
    )
    return InvestigatorVerdict(
        hypothesis_id=hypothesis_id,
        hypothesis_statement=hypothesis_statement,
        verdict="INCONCLUSIVE",
        reasoning=(
            f"Mechanical guardrail: {agent_name} made only "
            f"{tool_call_count} tool call(s); minimum is "
            f"{min_required}. "
            "Self-reported output was discarded."
        ),
    )
