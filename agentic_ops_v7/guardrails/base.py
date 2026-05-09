"""Foundational types shared across guardrail modules.

Every post-emit guardrail returns one of three verdicts on the LLM agent's
output: PASS (use as-is), REPAIR (the guardrail produced a deterministically
rewritten output; use the rewritten version), or REJECT (discard and
resample the agent with the rejection reason injected into the prompt).

`GuardrailResult` carries the verdict, the (possibly-repaired) output, a
human-readable reason that is also used as the resample-prompt text on
REJECT, and a structured `notes` dict that the recorder surfaces in the
run report.

PR 1 ships the type scaffolding only; the orchestrator does not yet
consume `GuardrailResult` values. PR 2+ wire concrete guardrails into the
`run_phase_with_guardrail` helper and start producing these values.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Generic, TypeVar


class GuardrailVerdict(str, Enum):
    PASS = "pass"
    REPAIR = "repair"
    REJECT = "reject"


T = TypeVar("T")


@dataclass
class GuardrailResult(Generic[T]):
    verdict: GuardrailVerdict
    output: T
    reason: str = ""
    notes: dict[str, Any] = field(default_factory=dict)
