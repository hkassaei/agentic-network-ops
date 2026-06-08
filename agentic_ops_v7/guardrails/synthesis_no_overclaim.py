"""Synthesis `no_overclaim` guardrail — ADR `synthesis_undetected_fault_verdict.md`.

Enforces the binary invariant that drives the `undetected_fault` verdict:

  * If NO Investigator verdict is NOT_DISPROVEN (every hypothesis was
    DISPROVEN or INCONCLUSIVE), Synthesis MUST emit
    `verdict_kind == "undetected_fault"`. Emitting `confirmed` /
    `promoted` / `inconclusive` in this state is the **over-claim** the
    ADR is designed to prevent — the agent has no confirmed evidence
    to back a named culprit and must humbly defer to a human.

  * Conversely, if any Investigator verdict IS NOT_DISPROVEN, Synthesis
    MUST NOT emit `undetected_fault`. There is confirmed evidence on
    the table; the verdict must name what the pipeline found.

`localized` and `compound` are walker-evidence verdicts that don't
depend on hypothesis NOT_DISPROVEN status — they short-circuit PASS so
this guardrail doesn't interfere with the transport-layer / multi-fault
branches.

On REJECT, the rejection reason names the expected verdict_kind and
quotes the verdict tree so the resample picks correctly. Returns PASS
or REJECT only; no REPAIR (the verdict_kind is the LLM's judgment, not
something we silently rewrite).
"""

from __future__ import annotations

from ..models import DiagnosisReport, InvestigatorVerdict
from .base import GuardrailResult, GuardrailVerdict


def lint_synthesis_no_overclaim(
    report: DiagnosisReport,
    verdicts: list[InvestigatorVerdict],
) -> GuardrailResult[DiagnosisReport]:
    """Validate that Synthesis matched its verdict_kind to the evidence shape.

    Short-circuits PASS for walker-evidence verdicts (`localized`,
    `compound`) — those branches don't depend on hypothesis NOT_DISPROVEN
    status. For the application-layer verdict_kinds, enforces the binary
    rule above.
    """
    # Walker-evidence verdicts are gated by their own dedicated guardrails
    # (lint_synthesis_localized_consistency, lint_compound_verdict_consistency).
    if report.verdict_kind in ("localized", "compound"):
        return GuardrailResult(verdict=GuardrailVerdict.PASS, output=report)

    has_confirmed = any(v.verdict == "NOT_DISPROVEN" for v in verdicts)
    verdict_counts = {
        "NOT_DISPROVEN": sum(1 for v in verdicts if v.verdict == "NOT_DISPROVEN"),
        "DISPROVEN":     sum(1 for v in verdicts if v.verdict == "DISPROVEN"),
        "INCONCLUSIVE":  sum(1 for v in verdicts if v.verdict == "INCONCLUSIVE"),
    }
    notes = {
        "verdict_counts": verdict_counts,
        "submitted_verdict_kind": report.verdict_kind,
        "submitted_primary_suspect_nf": report.primary_suspect_nf,
    }

    if not has_confirmed:
        # No NOT_DISPROVEN hypothesis. Synthesis MUST emit undetected_fault.
        if report.verdict_kind == "undetected_fault":
            return GuardrailResult(
                verdict=GuardrailVerdict.PASS, output=report, notes=notes,
            )
        return GuardrailResult(
            verdict=GuardrailVerdict.REJECT,
            output=report,
            reason=(
                f"No Investigator verdict was NOT_DISPROVEN (counts: "
                f"NOT_DISPROVEN={verdict_counts['NOT_DISPROVEN']}, "
                f"DISPROVEN={verdict_counts['DISPROVEN']}, "
                f"INCONCLUSIVE={verdict_counts['INCONCLUSIVE']}). With no "
                f"confirmed hypothesis, the only valid verdict_kind is "
                f"`undetected_fault` — the agent's humble admission that "
                f"investigation completed without identifying a specific "
                f"fault. You emitted `verdict_kind=\"{report.verdict_kind}\"`"
                + (
                    f" with primary_suspect_nf={report.primary_suspect_nf!r}"
                    if report.primary_suspect_nf else ""
                ) + (
                    " — this is the 'over-claim' failure mode the no-overclaim "
                    "guardrail is designed to prevent. Re-emit with "
                    "`verdict_kind=\"undetected_fault\"`, "
                    "`primary_suspect_nf=null`, `affected_components=[]`, "
                    "`localization=null`, `additional_root_causes=[]`. "
                    "Surface the DISPROVEN Investigators' alternative_suspects "
                    "in the `explanation` field as next leads for the "
                    "human operator. See ADR "
                    "`synthesis_undetected_fault_verdict.md` for the "
                    "humble-admission framing."
                )
            ),
            notes=notes,
        )

    # At least one NOT_DISPROVEN. undetected_fault is invalid here —
    # the evidence shape supports naming a confirmed cause.
    if report.verdict_kind == "undetected_fault":
        return GuardrailResult(
            verdict=GuardrailVerdict.REJECT,
            output=report,
            reason=(
                f"At least one Investigator verdict is NOT_DISPROVEN "
                f"(count: {verdict_counts['NOT_DISPROVEN']}). With a "
                f"confirmed hypothesis on the table, the verdict_kind "
                f"must name what the pipeline found — `undetected_fault` "
                f"is the humble-admission branch reserved for the case "
                f"where NO hypothesis is NOT_DISPROVEN. Re-emit with "
                f"`verdict_kind=\"confirmed\"` (or `promoted`) and "
                f"populate `primary_suspect_nf` from the candidate pool."
            ),
            notes=notes,
        )

    return GuardrailResult(verdict=GuardrailVerdict.PASS, output=report, notes=notes)
