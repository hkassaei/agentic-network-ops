"""Decision F — Synthesis confidence cap.

Synthesis emits a `root_cause_confidence` value in {high, medium, low}.
The LLM's choice of value is unreliable: it tends to claim `high` even
when the underlying probe evidence is weak (single CONSISTENT probe + a
contradicting probe, or no triangulation, or a forest of AMBIGUOUS
probes that didn't actually test the hypothesis). Decision F caps the
emitted confidence based on a deterministic evidence-strength score
derived from the structured probe-result fields the Investigator
already populates.

Per ADR Decision F, the strength enum and cap table:

    | Strongest verdict's evidence-strength | Max permitted confidence |
    |---------------------------------------|--------------------------|
    | STRONG                                | high                     |
    | MODERATE                              | medium                   |
    | WEAK                                  | low                      |
    | NONE                                  | inconclusive (forced)    |

The "strongest verdict" is the one that supports Synthesis's named
diagnosis:
    * `verdict_kind == "confirmed"` → the InvestigatorVerdict whose
      parent hypothesis named `report.primary_suspect_nf`.
    * `verdict_kind == "promoted"` → the CandidatePoolMember for the
      promoted NF; strength derived from `cite_count` +
      `strong_cited_in`.
    * `verdict_kind == "inconclusive"` → no cap needed; passes through.

The cap is REPAIR (silent rewrite + structured note appended to the
explanation), not REJECT. Per ADR Open Design Question: rewrite is
cheaper and the LLM's verdict choice itself is correct — only the
confidence rating gets corrected. The runner returns the repaired
DiagnosisReport.

Composes with PR 5.5b's `lint_synthesis_pool_membership`:
pool-membership runs first (REJECT path); if it PASSes, the cap runs
(REPAIR path). The orchestrator wires them as a combined closure.
"""

from __future__ import annotations

from typing import Literal

from ..models import DiagnosisReport, Hypothesis, InvestigatorVerdict
from .base import GuardrailResult, GuardrailVerdict
from .synthesis_pool import CandidatePool


EvidenceStrength = Literal["STRONG", "MODERATE", "WEAK", "NONE"]


# Cap table — `cap[strength]` is the maximum `root_cause_confidence`
# value Synthesis is allowed to claim. Values lower than the cap are
# accepted; values higher are downgraded to the cap.
_CAP: dict[str, str] = {
    "STRONG":   "high",
    "MODERATE": "medium",
    "WEAK":     "low",
    "NONE":     "low",  # NONE forces 'low' on the confidence enum;
                        # verdict_kind=inconclusive is enforced separately.
}


# Confidence ordering. `_CONF_ORDER[v]` returns rank; higher is more
# confident. `cap` operation: if emitted_rank > cap_rank, downgrade.
_CONF_ORDER: dict[str, int] = {
    "low": 0,
    "medium": 1,
    "high": 2,
}


def compute_evidence_strength_for_verdict(
    verdict: InvestigatorVerdict,
) -> EvidenceStrength:
    """Score one Investigator verdict from its `probes_executed` list.

    Inputs come from `ProbeResult.compared_to_expected` per probe:
        * CONSISTENT — supports the hypothesis
        * CONTRADICTS — refutes the hypothesis
        * AMBIGUOUS — couldn't determine

    Probes whose `outcome` is `tool_unavailable` or `error` are filtered
    out before scoring — they did not produce evidence at all (the
    target container was missing the required binary, or the tool
    failed for another structural reason). Counting them would let a
    verdict driven entirely by un-runnable probes claim STRONG
    evidence; see docs/ADR/nf_container_diagnostic_tooling.md.

    Strength rules (computed against the FILTERED probe list):
        * NONE — no probes at all OR more than half are AMBIGUOUS
          (the hypothesis didn't actually get tested).
        * WEAK — at least one CONTRADICTS, OR fewer than 2 CONSISTENT.
        * MODERATE — ≥2 CONSISTENT, 0 CONTRADICTS, but at least one
          AMBIGUOUS (some probes didn't fully support).
        * STRONG — ≥2 CONSISTENT, 0 CONTRADICTS, 0 AMBIGUOUS.

    INCONCLUSIVE-verdict probes get NONE regardless. DISPROVEN verdicts
    don't typically drive Synthesis confidence (they should be filtered
    out by the caller — only the surviving verdict drives the cap).
    """
    probes = [
        p for p in verdict.probes_executed
        if p.outcome not in ("tool_unavailable", "error")
    ]
    if not probes:
        return "NONE"

    consistent = sum(1 for p in probes if p.compared_to_expected == "CONSISTENT")
    contradicting = sum(1 for p in probes if p.compared_to_expected == "CONTRADICTS")
    ambiguous = sum(1 for p in probes if p.compared_to_expected == "AMBIGUOUS")
    total = len(probes)

    # NONE — too many AMBIGUOUS probes means the hypothesis wasn't
    # actually tested.
    if ambiguous / total > 0.5:
        return "NONE"

    # WEAK — any CONTRADICTS, OR fewer than 2 CONSISTENT.
    if contradicting > 0 or consistent < 2:
        return "WEAK"

    # MODERATE — ≥2 CONSISTENT, 0 CONTRADICTS, but some AMBIGUOUS.
    if ambiguous > 0:
        return "MODERATE"

    # STRONG — clean.
    return "STRONG"


def compute_evidence_strength_for_promoted(
    cite_count: int,
    strong_cited_count: int,
) -> EvidenceStrength:
    """Score a promoted candidate from cross-corroboration metrics.

    Promoted candidates don't have their own NOT_DISPROVEN verdict
    (otherwise they'd be survivors). Their evidential weight comes from
    how many DISPROVEN verdicts named them in `alternative_suspects`
    plus how many of those verdicts named them in their `reasoning`
    text (strong-cite).

    Rules:
        * STRONG — ≥3 cross-corroboration cites (very rare; would mean
          all three NA hypotheses' Investigators agreed on the same
          alt-suspect after disproving their own hypothesis).
        * MODERATE — ≥2 cross-corroboration cites OR ≥2 strong-cites
          (multiple Investigators named the NF in their reasoning).
        * WEAK — exactly 1 cross-corroboration cite with ≥1 strong-cite
          (the single-strong-cite promotion path).
        * NONE — fewer than that. Should not happen if the aggregator
          correctly filtered.
    """
    if cite_count >= 3:
        return "STRONG"
    if cite_count >= 2 or strong_cited_count >= 2:
        return "MODERATE"
    if cite_count >= 1 and strong_cited_count >= 1:
        return "WEAK"
    return "NONE"


def cap_synthesis_confidence(
    report: DiagnosisReport,
    verdicts: list[InvestigatorVerdict],
    hypotheses: list[Hypothesis],
    pool: CandidatePool,
) -> GuardrailResult[DiagnosisReport]:
    """Compute evidence-strength for the verdict supporting Synthesis's
    diagnosis, then cap `root_cause_confidence` if it exceeds the cap.

    Returns:
        REPAIR — confidence was downgraded; `output` is a new
            DiagnosisReport with the corrected value and an appended
            note in the `explanation` field.
        PASS  — confidence is at or below the cap; `output` is the
            original report unchanged.
    """
    # Inconclusive verdict_kind: no diagnosis, no cap needed.
    if report.verdict_kind == "inconclusive":
        return GuardrailResult(verdict=GuardrailVerdict.PASS, output=report)

    # Compute evidence-strength for the verdict supporting the diagnosis.
    strength: EvidenceStrength
    rationale: str
    if report.verdict_kind == "confirmed":
        # Find the surviving verdict that names the report's NF.
        relevant = _find_supporting_verdict(report, verdicts, hypotheses)
        if relevant is None:
            # Shouldn't happen if pool-membership guardrail ran first,
            # but defensive: treat as NONE.
            strength = "NONE"
            rationale = (
                "no Investigator verdict supports the diagnosed NF "
                "(this should have been blocked by pool membership)"
            )
        else:
            strength = compute_evidence_strength_for_verdict(relevant)
            rationale = _explain_verdict_strength(relevant, strength)
    elif report.verdict_kind == "promoted":
        # Find the pool member for the promoted NF.
        member = next(
            (m for m in pool.members
             if m.nf == report.primary_suspect_nf and m.kind == "promoted"),
            None,
        )
        if member is None:
            strength = "NONE"
            rationale = (
                "promoted diagnosis names an NF not in the candidate pool's "
                "promoted members (this should have been blocked by pool "
                "membership)"
            )
        else:
            strength = compute_evidence_strength_for_promoted(
                cite_count=member.cite_count,
                strong_cited_count=len(member.strong_cited_in),
            )
            rationale = (
                f"promoted via {member.cite_count} alt-suspect cite(s) "
                f"with {len(member.strong_cited_in)} strong-cite(s) "
                "in DISPROVEN verdict reasoning"
            )
    else:
        # Unknown verdict_kind — pass through.
        return GuardrailResult(verdict=GuardrailVerdict.PASS, output=report)

    # Compare emitted vs. cap.
    cap_value = _CAP[strength]
    emitted = report.root_cause_confidence
    emitted_rank = _CONF_ORDER.get(emitted, 0)
    cap_rank = _CONF_ORDER[cap_value]

    if emitted_rank <= cap_rank:
        # Already at or below cap. Pass through; record the strength
        # in notes so the recorder can surface it without modifying
        # the report.
        return GuardrailResult(
            verdict=GuardrailVerdict.PASS,
            output=report,
            notes={
                "evidence_strength": strength,
                "cap_value": cap_value,
                "emitted_value": emitted,
                "rationale": rationale,
                "applied": False,
            },
        )

    # Cap fires. REPAIR with downgraded confidence and explanation note.
    cap_note = (
        f"\n\n[Confidence cap applied: emitted '{emitted}' downgraded to "
        f"'{cap_value}' because evidence-strength is {strength} "
        f"({rationale}). Decision F — the LLM's confidence claim was "
        "deterministically corrected to match the underlying probe "
        "evidence; the diagnosed NF stands.]"
    )
    repaired = report.model_copy(update={
        "root_cause_confidence": cap_value,
        "explanation": (report.explanation or "") + cap_note,
    })
    return GuardrailResult(
        verdict=GuardrailVerdict.REPAIR,
        output=repaired,
        reason=(
            f"Synthesis emitted root_cause_confidence='{emitted}' but the "
            f"strongest supporting verdict's evidence-strength is "
            f"{strength} (max permitted: '{cap_value}'). Confidence "
            f"deterministically capped. Reason: {rationale}."
        ),
        notes={
            "evidence_strength": strength,
            "cap_value": cap_value,
            "emitted_value": emitted,
            "rationale": rationale,
            "applied": True,
        },
    )


def _find_supporting_verdict(
    report: DiagnosisReport,
    verdicts: list[InvestigatorVerdict],
    hypotheses: list[Hypothesis],
) -> InvestigatorVerdict | None:
    """Find the NOT_DISPROVEN verdict whose hypothesis names the
    diagnosed NF, OR a re-investigation verdict on the diagnosed NF.

    Re-investigation verdicts have `hypothesis_id` starting with
    `h_promoted_<nf>`; the synthetic hypothesis isn't in the
    `hypotheses` list, so we match on the id pattern as a fallback.
    """
    target_nf = report.primary_suspect_nf
    if target_nf is None:
        return None

    nf_by_hypothesis_id: dict[str, str] = {h.id: h.primary_suspect_nf for h in hypotheses}

    for v in verdicts:
        if v.verdict != "NOT_DISPROVEN":
            continue
        # Original hypothesis with this NF
        hyp_nf = nf_by_hypothesis_id.get(v.hypothesis_id)
        if hyp_nf == target_nf:
            return v
        # Re-investigation verdict on this NF
        if v.hypothesis_id == f"h_promoted_{target_nf}":
            return v
    return None


def _explain_verdict_strength(
    verdict: InvestigatorVerdict,
    strength: EvidenceStrength,
) -> str:
    """Render a short rationale string for the recorder / cap note.

    Probes excluded from the strength score (tool_unavailable / error)
    are counted separately so the rationale makes clear they were not
    silently dropped.
    """
    all_probes = verdict.probes_executed
    excluded = sum(1 for p in all_probes if p.outcome in ("tool_unavailable", "error"))
    probes = [p for p in all_probes if p.outcome not in ("tool_unavailable", "error")]
    consistent = sum(1 for p in probes if p.compared_to_expected == "CONSISTENT")
    contradicting = sum(1 for p in probes if p.compared_to_expected == "CONTRADICTS")
    ambiguous = sum(1 for p in probes if p.compared_to_expected == "AMBIGUOUS")
    total = len(probes)
    base = (
        f"verdict {verdict.hypothesis_id}: "
        f"{consistent}/{total} CONSISTENT, "
        f"{contradicting} CONTRADICTS, "
        f"{ambiguous} AMBIGUOUS"
    )
    if excluded:
        base += f" (+{excluded} excluded as tool_unavailable/error)"
    return base
