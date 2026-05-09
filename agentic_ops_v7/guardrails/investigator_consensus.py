"""Decision C — Multi-shot Investigator consensus reconciliation.

Single-shot LLM verdicts are samples from a distribution. Two runs of
the same plan can produce DISPROVEN and NOT_DISPROVEN respectively,
both with high confidence in their own reasoning. Pre-PR-6 the pipeline
ratified whichever roll happened to fire and Synthesis wrote
high-confidence diagnoses on what was fundamentally a coin-flip outcome.

Decision C runs each Investigator twice on the same plan and reconciles
the verdicts:

    * Both DISPROVEN     → DISPROVEN, with the union of alternative_suspects
                            and merged reasoning naming both shots.
    * Both NOT_DISPROVEN → NOT_DISPROVEN, with merged reasoning. The
                            union-of-probe-interpretations recommendation
                            in the ADR is captured by concatenating both
                            shots' reasoning text — the underlying
                            ProbeResult lists are kept from shot 1 since
                            they're identical-by-plan.
    * Disagreement       → INCONCLUSIVE, with reasoning that names the
                            disagreement and quotes both shots' core
                            reasoning so a human auditor can adjudicate.
    * Any INCONCLUSIVE   → INCONCLUSIVE (short-circuit; the orchestrator
                            also short-circuits *before* shot 2 if shot 1
                            already returned INCONCLUSIVE — saves the
                            second LLM call).

The reconciler is variance-reduction, not bias correction. If both
shots are systematically biased (same wrong interpretation), they'll
agree and the bad verdict rides through. Decisions D / A2 / G / H
target the bias side; this targets variance.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..models import InvestigatorVerdict, ProbeResult


# Maximum length of each shot's reasoning text included in the
# disagreement-reconciliation note. Keeps the rendered explanation
# readable without truncating away the load-bearing logic.
_REASONING_QUOTE_MAX_CHARS = 600


@dataclass
class ReconciliationResult:
    """Output of reconcile_verdicts. Carries the merged verdict plus
    structured metadata for the recorder/observer."""
    verdict: InvestigatorVerdict
    kind: str  # "single_shot" | "agreement" | "disagreement" | "inconclusive_pass_through"
    shot_count: int
    short_circuited: bool = False  # True iff shot 2 was skipped


def reconcile_verdicts(
    shots: list[InvestigatorVerdict],
    short_circuited: bool = False,
) -> ReconciliationResult:
    """Reconcile 1 or 2 InvestigatorVerdicts into a single verdict.

    Single-shot input passes through unchanged (legacy single-shot
    callers + INCONCLUSIVE short-circuit). Two-shot input is reconciled
    per the rules in the module docstring.
    """
    if not shots:
        # Defensive — caller should never pass empty.
        raise ValueError("reconcile_verdicts requires at least 1 shot")

    if len(shots) == 1:
        return ReconciliationResult(
            verdict=shots[0],
            kind=(
                "inconclusive_pass_through"
                if shots[0].verdict == "INCONCLUSIVE"
                else "single_shot"
            ),
            shot_count=1,
            short_circuited=short_circuited,
        )

    if len(shots) > 2:
        # Future-proofing — for now we ship 2-shot only. Reject extra
        # shots to surface plumbing bugs early.
        raise ValueError(
            f"reconcile_verdicts received {len(shots)} shots; "
            "only 1 or 2 are currently supported"
        )

    s1, s2 = shots[0], shots[1]

    # Any INCONCLUSIVE → INCONCLUSIVE (with merged reasoning).
    if "INCONCLUSIVE" in (s1.verdict, s2.verdict):
        return ReconciliationResult(
            verdict=_merge_inconclusive(s1, s2),
            kind="agreement" if s1.verdict == s2.verdict else "disagreement",
            shot_count=2,
        )

    # Agreement on DISPROVEN or NOT_DISPROVEN.
    if s1.verdict == s2.verdict:
        return ReconciliationResult(
            verdict=_merge_agreement(s1, s2),
            kind="agreement",
            shot_count=2,
        )

    # Disagreement: one DISPROVEN, one NOT_DISPROVEN. Force INCONCLUSIVE.
    return ReconciliationResult(
        verdict=_make_disagreement_verdict(s1, s2),
        kind="disagreement",
        shot_count=2,
    )


def _merge_agreement(
    s1: InvestigatorVerdict, s2: InvestigatorVerdict,
) -> InvestigatorVerdict:
    """Build a merged verdict for two agreeing shots.

    Reasoning is concatenated (shot 1 + " | shot 2: " + shot 2). The
    union of alternative_suspects is taken (case-insensitive
    deduplication, preserving shot 1's casing where overlapping).
    `probes_executed` is kept from shot 1 since the plan is identical
    across shots and the probe DESCRIPTIONS are the same; only the
    OBSERVATION values can differ between shots, but the reasoning
    text already captures any divergence.
    """
    return InvestigatorVerdict(
        hypothesis_id=s1.hypothesis_id,
        hypothesis_statement=s1.hypothesis_statement,
        verdict=s1.verdict,
        reasoning=(
            f"[Multi-shot consensus — both shots returned {s1.verdict}.]\n\n"
            f"Shot 1: {s1.reasoning}\n\n"
            f"Shot 2: {s2.reasoning}"
        ),
        probes_executed=s1.probes_executed,
        alternative_suspects=_merge_alt_suspects(
            s1.alternative_suspects, s2.alternative_suspects,
        ),
    )


def _merge_inconclusive(
    s1: InvestigatorVerdict, s2: InvestigatorVerdict,
) -> InvestigatorVerdict:
    """Build a merged verdict when at least one shot was INCONCLUSIVE.

    Always returns verdict='INCONCLUSIVE' because INCONCLUSIVE+anything
    means we don't have a confident reading. Reasoning explains which
    shot(s) were INCONCLUSIVE and why.
    """
    s1_label = "INCONCLUSIVE" if s1.verdict == "INCONCLUSIVE" else s1.verdict
    s2_label = "INCONCLUSIVE" if s2.verdict == "INCONCLUSIVE" else s2.verdict
    return InvestigatorVerdict(
        hypothesis_id=s1.hypothesis_id,
        hypothesis_statement=s1.hypothesis_statement,
        verdict="INCONCLUSIVE",
        reasoning=(
            f"[Multi-shot consensus — at least one shot returned "
            f"INCONCLUSIVE (shot 1: {s1_label}, shot 2: {s2_label}). "
            "Treating the combined verdict as INCONCLUSIVE because "
            "INCONCLUSIVE on either shot means we lack confident "
            "evidence to commit.]\n\n"
            f"Shot 1: {s1.reasoning}\n\n"
            f"Shot 2: {s2.reasoning}"
        ),
        probes_executed=s1.probes_executed or s2.probes_executed or [],
        alternative_suspects=_merge_alt_suspects(
            s1.alternative_suspects, s2.alternative_suspects,
        ),
    )


def _make_disagreement_verdict(
    s1: InvestigatorVerdict, s2: InvestigatorVerdict,
) -> InvestigatorVerdict:
    """Build the forced-INCONCLUSIVE verdict for a disagreement.

    Names both shot verdicts explicitly so a human auditor reading the
    episode log can adjudicate. The alternative_suspects union is
    preserved because either shot's named alt-suspect is potentially
    valuable — Decision E's pool aggregator will use them to compose
    the candidate pool downstream.
    """
    s1_quote = _truncate(s1.reasoning, _REASONING_QUOTE_MAX_CHARS)
    s2_quote = _truncate(s2.reasoning, _REASONING_QUOTE_MAX_CHARS)
    reasoning = (
        f"[Multi-shot consensus — DISAGREEMENT. Shot 1 returned "
        f"{s1.verdict}; shot 2 returned {s2.verdict}. Two independent "
        "samples of the same Investigator on the same plan reached "
        "opposite conclusions. The reconciler forces verdict to "
        "INCONCLUSIVE because we cannot trust either shot in "
        "isolation when the underlying LLM judgment is unstable.]\n\n"
        f"Shot 1 ({s1.verdict}): {s1_quote}\n\n"
        f"Shot 2 ({s2.verdict}): {s2_quote}"
    )
    return InvestigatorVerdict(
        hypothesis_id=s1.hypothesis_id,
        hypothesis_statement=s1.hypothesis_statement,
        verdict="INCONCLUSIVE",
        reasoning=reasoning,
        probes_executed=s1.probes_executed,
        alternative_suspects=_merge_alt_suspects(
            s1.alternative_suspects, s2.alternative_suspects,
        ),
    )


def _merge_alt_suspects(
    a: list[str], b: list[str],
) -> list[str]:
    """Case-insensitive union, preserving order: A's entries first,
    then B's entries that aren't already in A (case-insensitive)."""
    seen_lower: set[str] = set()
    out: list[str] = []
    for entry in (a or []) + (b or []):
        norm = entry.strip()
        if not norm:
            continue
        key = norm.lower()
        if key in seen_lower:
            continue
        seen_lower.add(key)
        out.append(norm)
    return out


def _truncate(text: str, max_chars: int) -> str:
    """Truncate `text` to `max_chars`, appending a `…` marker."""
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars - 1].rstrip() + "…"
