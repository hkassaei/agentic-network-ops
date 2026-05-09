"""Output sanitizer that strips internal-mechanism references from
LLM-emitted artifacts.

Purpose: a structural backstop against any artifact (an IG plan note, an
Investigator reasoning text, a Synthesis explanation) that mentions the
project's internal validator taxonomy — Decision-letter labels, A1/A2
sub-check names, references to "linter feedback" or "guardrail", named
ADRs, or pipeline phase numbers. Those identifiers are engineer-facing;
they must never reach the user-facing report.

Composition:
- Used as a final post-emit check in the NA / IG / Synthesis guardrail
  chains (after the substantive guardrails have already passed).
- On REJECT, the runner resamples the agent with a deliberately
  *content-blind* feedback string that does not name the offending
  phrase (so the resample feedback itself cannot teach the LLM the
  taxonomy). On second REJECT, the runner's
  `on_guardrail_exhausted="accept"` policy logs a warning and accepts.
"""

from __future__ import annotations

import re

from ..models import (
    DiagnosisReport,
    FalsificationPlanSet,
    NetworkAnalystReport,
)
from .base import GuardrailResult, GuardrailVerdict


# Regex over LLM-emitted prose. Word boundaries pin us to whole-token
# hits (so e.g. "Adriatic" does not match "ADR" and "amf" does not
# match "A1"). Flags are case-insensitive so "Decision a" / "decision A"
# also fire.
LEAK_PATTERN: re.Pattern[str] = re.compile(
    r"\b(?:"
    r"Decision\s+[A-Z]"           # "Decision A", "Decision G"
    r"|A[0-9]+"                   # "A1", "A2", any future Ax sub-check
    r"|D[0-9]+"                   # "D1", any Dx tag
    r"|linter\s+(?:feedback|rejection|warning)"
    r"|guardrail"                 # bare or with adjective
    r"|ADR\s+[A-Za-z_][\w/.\-]*"  # "ADR foo_bar.md", "ADR_some_name"
    r"|Phase\s+[0-9]"             # "Phase 5", "Phase 6.5"
    r"|PR\s*[0-9]"                # "PR 4", "PR5.5b"
    r"|sub-check\s+[A-Z][0-9]?"   # "sub-check A1"
    r")\b",
    re.IGNORECASE,
)


# Content-blind feedback. Deliberately does NOT name what was leaked, so
# the rejection cannot teach the LLM the taxonomy by example.
_CONTENT_BLIND_FEEDBACK = (
    "Your artifact contains references to internal implementation "
    "mechanisms. Rewrite using domain terms only — describe what the "
    "plan / hypothesis / diagnosis DOES, not how it was produced or "
    "validated. Do not reference any rejection process, validation "
    "step, or pipeline phase in your output."
)


def _scan(text: str | None) -> bool:
    """True iff `text` contains any leak-pattern hit."""
    if not text:
        return False
    return bool(LEAK_PATTERN.search(text))


def sanitize_na_report(
    report: NetworkAnalystReport,
) -> GuardrailResult[NetworkAnalystReport]:
    """Reject if NA's prose fields leak internal taxonomy."""
    leaky_fields: list[str] = []
    if _scan(report.summary):
        leaky_fields.append("summary")
    for h in report.hypotheses:
        if _scan(h.statement):
            leaky_fields.append(f"hypotheses[{h.id}].statement")
    if leaky_fields:
        return GuardrailResult(
            verdict=GuardrailVerdict.REJECT,
            output=report,
            reason=_CONTENT_BLIND_FEEDBACK,
            notes={"leaky_fields": leaky_fields},
        )
    return GuardrailResult(verdict=GuardrailVerdict.PASS, output=report)


def sanitize_plan_set(
    plan_set: FalsificationPlanSet,
) -> GuardrailResult[FalsificationPlanSet]:
    """Reject if any IG plan's prose fields leak internal taxonomy."""
    leaky_fields: list[str] = []
    for plan in plan_set.plans:
        if _scan(plan.notes):
            leaky_fields.append(f"plans[{plan.hypothesis_id}].notes")
        if _scan(plan.hypothesis_statement):
            leaky_fields.append(
                f"plans[{plan.hypothesis_id}].hypothesis_statement"
            )
        for idx, probe in enumerate(plan.probes):
            if _scan(probe.expected_if_hypothesis_holds):
                leaky_fields.append(
                    f"plans[{plan.hypothesis_id}].probes[{idx}]."
                    "expected_if_hypothesis_holds"
                )
            if _scan(probe.falsifying_observation):
                leaky_fields.append(
                    f"plans[{plan.hypothesis_id}].probes[{idx}]."
                    "falsifying_observation"
                )
    if leaky_fields:
        return GuardrailResult(
            verdict=GuardrailVerdict.REJECT,
            output=plan_set,
            reason=_CONTENT_BLIND_FEEDBACK,
            notes={"leaky_fields": leaky_fields},
        )
    return GuardrailResult(verdict=GuardrailVerdict.PASS, output=plan_set)


def sanitize_diagnosis_report(
    report: DiagnosisReport,
) -> GuardrailResult[DiagnosisReport]:
    """Reject if Synthesis's user-facing fields leak internal taxonomy."""
    leaky_fields: list[str] = []
    if _scan(report.summary):
        leaky_fields.append("summary")
    if _scan(report.explanation):
        leaky_fields.append("explanation")
    if _scan(report.recommendation):
        leaky_fields.append("recommendation")
    if _scan(report.root_cause):
        leaky_fields.append("root_cause")
    if leaky_fields:
        return GuardrailResult(
            verdict=GuardrailVerdict.REJECT,
            output=report,
            reason=_CONTENT_BLIND_FEEDBACK,
            notes={"leaky_fields": leaky_fields},
        )
    return GuardrailResult(verdict=GuardrailVerdict.PASS, output=report)
