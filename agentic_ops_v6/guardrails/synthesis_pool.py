"""Decision E sub-component — Synthesis candidate-pool aggregator.

Pure-Python aggregator that walks the post-Phase-5 verdict tree and
computes a `CandidatePool`: the set of NFs that should be considered as
diagnosis candidates by Synthesis. Two contributors:

  * Every hypothesis with verdict NOT_DISPROVEN — its `primary_suspect_nf`
    is a *survivor* candidate.
  * Every NF named in DISPROVEN verdicts' `alternative_suspects` lists
    that meets a corroboration threshold — *promoted* candidate.

Promotion thresholds:

  1. **Cross-corroboration** — NF appears in `alternative_suspects` of
     ≥2 disproven verdicts. This is the strongest signal because two
     independent Investigators converging on the same alt-suspect is
     hard to fabricate.
  2. **Single-strong-cite** — NF appears in `alternative_suspects` of
     ≥1 disproven verdict AND its name appears in that verdict's
     `reasoning` text. This catches the Part-I 17:58 case where one
     Investigator named pcscf in `alternative_suspects` AND wrote
     about pcscf in the reasoning, while two other Investigators were
     silent on pcscf.

The pool is ranked: NOT_DISPROVEN survivors first (tiebreak by
explanatory_fit if the parent hypothesis is supplied), then promoted
suspects by cross-corroboration count, then by single-strong-cite
status, then alphabetically as a final tiebreak.

The aggregator is the input to two downstream behaviors:

  * Pool injection into Synthesis prompt — Synthesis sees the ranked
    pool and is prompt-instructed to diagnose from it.
  * Bounded re-investigation — when the pool contains ≥1 promoted
    suspect but zero NOT_DISPROVEN survivors, the orchestrator runs
    one extra IG → Investigator cycle on the top-ranked promoted
    suspect to produce a structurally-clean verdict that Synthesis
    can ratify with calibrated confidence.

PR 5 ships the aggregator + bounded re-investigation. Strict
post-emit pool-membership validation on Synthesis output is deferred
until Synthesis is converted to structured output (separate refactor).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from ..models import DiagnosisReport, Hypothesis, InvestigatorVerdict
from .base import GuardrailResult, GuardrailVerdict


@dataclass
class CandidatePoolMember:
    """One entry in the candidate pool.

    `kind` is "survivor" for NOT_DISPROVEN-derived members, "promoted"
    for alt_suspect-derived members. `cite_count` is the number of
    disproven verdicts that named this NF in alternative_suspects.
    `strong_cited_in` is the list of hypothesis_ids whose verdict
    reasoning text mentioned this NF by name.
    `survivor_hypothesis_id` is set only for survivors.
    """
    nf: str
    kind: str  # "survivor" | "promoted"
    cite_count: int = 0
    strong_cited_in: list[str] = field(default_factory=list)
    survivor_hypothesis_id: str = ""
    survivor_explanatory_fit: float = 0.0


@dataclass
class CandidatePool:
    """The full ranked pool plus convenience properties."""
    members: list[CandidatePoolMember] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.members

    @property
    def has_survivor(self) -> bool:
        return any(m.kind == "survivor" for m in self.members)

    @property
    def survivors(self) -> list[CandidatePoolMember]:
        return [m for m in self.members if m.kind == "survivor"]

    @property
    def promoted(self) -> list[CandidatePoolMember]:
        return [m for m in self.members if m.kind == "promoted"]

    @property
    def needs_reinvestigation(self) -> bool:
        """True iff the pool has ≥1 promoted suspect but no survivors.

        This is the trigger for the orchestrator's bounded
        re-investigation cycle. Empty pools and pools with at least one
        survivor don't need re-investigation: empty → Synthesis writes
        inconclusive with the prose rule; survivor present → Synthesis
        ratifies the survivor normally.
        """
        return not self.has_survivor and bool(self.promoted)

    @property
    def top_promoted(self) -> CandidatePoolMember | None:
        promoted = self.promoted
        return promoted[0] if promoted else None

    def render_for_prompt(self) -> str:
        """Render the pool as plain text for Synthesis prompt injection.

        Format chosen to be unambiguous and short — Synthesis reads
        thousands of lines of context already; this stays compact while
        making the structural claim ("here is the verified candidate
        list, pick from it") visually prominent.
        """
        if not self.members:
            return (
                "(empty — no NOT_DISPROVEN survivors and no NF crossed "
                "the alt-suspect corroboration threshold)"
            )
        lines: list[str] = []
        for m in self.members:
            if m.kind == "survivor":
                lines.append(
                    f"- `{m.nf}` (SURVIVOR — hypothesis "
                    f"{m.survivor_hypothesis_id}, fit={m.survivor_explanatory_fit:.2f})"
                )
            else:
                bits = [f"cited in {m.cite_count} DISPROVEN verdict(s)"]
                if m.strong_cited_in:
                    bits.append(
                        f"named in reasoning of {sorted(m.strong_cited_in)}"
                    )
                lines.append(f"- `{m.nf}` (PROMOTED — {'; '.join(bits)})")
        return "\n".join(lines)


def compute_candidate_pool(
    verdicts: list[InvestigatorVerdict],
    hypotheses: list[Hypothesis] | None = None,
) -> CandidatePool:
    """Walk the verdict tree and return the ranked candidate pool.

    `hypotheses` is optional and used only to look up `explanatory_fit`
    on survivor members (for tiebreak ranking). If not supplied,
    survivor fit defaults to 0.0 — which still preserves the survivor /
    promoted ordering, just makes the survivor-side tiebreak alphabetical.
    """
    fit_by_id: dict[str, float] = {}
    if hypotheses:
        fit_by_id = {h.id: h.explanatory_fit for h in hypotheses}

    survivors: list[CandidatePoolMember] = []
    # alt_suspect counters across DISPROVEN verdicts only
    cite_count: Counter[str] = Counter()
    strong_cites: dict[str, list[str]] = {}

    for v in verdicts:
        if v.verdict == "NOT_DISPROVEN":
            survivors.append(CandidatePoolMember(
                nf=_nf_from_verdict(v, hypotheses),
                kind="survivor",
                survivor_hypothesis_id=v.hypothesis_id,
                survivor_explanatory_fit=fit_by_id.get(v.hypothesis_id, 0.0),
            ))
        elif v.verdict == "DISPROVEN":
            for alt in v.alternative_suspects:
                alt_norm = alt.strip().lower()
                if not alt_norm:
                    continue
                cite_count[alt_norm] += 1
                # Strong-cite check: alt_suspect name appears in
                # reasoning text. Substring match is sufficient — we
                # already know `alt` was emitted by the LLM as an alt
                # suspect, and case-insensitive substring catches the
                # common rendering variants.
                if alt_norm in (v.reasoning or "").lower():
                    strong_cites.setdefault(alt_norm, []).append(v.hypothesis_id)

    # Build promoted members. A NF promotes if it crosses the
    # cross-corroboration threshold (≥2 mentions) OR has a strong cite
    # in at least one verdict.
    promoted: list[CandidatePoolMember] = []
    survivor_nfs = {m.nf for m in survivors}
    for nf, count in cite_count.items():
        if nf in survivor_nfs:
            # Already a survivor — don't double-count as promoted.
            continue
        strong_in = strong_cites.get(nf, [])
        if count >= 2 or strong_in:
            promoted.append(CandidatePoolMember(
                nf=nf,
                kind="promoted",
                cite_count=count,
                strong_cited_in=strong_in,
            ))

    # Rank survivors by fit desc, then by NF name asc.
    survivors.sort(key=lambda m: (-m.survivor_explanatory_fit, m.nf))
    # Rank promoted by cite_count desc, then strong-cite count desc,
    # then NF name asc.
    promoted.sort(
        key=lambda m: (-m.cite_count, -len(m.strong_cited_in), m.nf)
    )

    return CandidatePool(members=survivors + promoted)


def _nf_from_verdict(
    v: InvestigatorVerdict,
    hypotheses: list[Hypothesis] | None,
) -> str:
    """Resolve the primary_suspect_nf for a verdict.

    Three resolution paths:
      1. **Re-investigation verdicts** (hypothesis_id starts with
         `h_promoted_<nf>`): the synthetic Hypothesis is NOT in the
         caller-supplied `original_hypotheses` list (it's built fresh
         in `_run_bounded_reinvestigation`). Extract the NF from the
         id suffix. This is the path Decision E's re-investigation
         flow takes after PR 5.
      2. **Original hypotheses** (id matches a parent hypothesis):
         look up `primary_suspect_nf` on the parent.
      3. **Fallback** — id doesn't match any known shape: return a
         `<unknown:...>` placeholder. This degrades gracefully (the
         pool still composes for ranking purposes) but flags the
         resolution failure visibly.

    Pre-PR-9.5 bug: re-investigation verdicts fell through to the
    placeholder branch because the caller passes only the original
    hypothesis list, not the synthetic one. The pool then carried
    `<unknown:h_promoted_upf>` as a survivor NF instead of `upf`,
    which broke the pool-membership guardrail downstream.
    """
    # Path 1: re-investigation verdict (synthetic id pattern).
    if v.hypothesis_id.startswith("h_promoted_"):
        return v.hypothesis_id[len("h_promoted_"):]

    # Path 2: original hypothesis lookup.
    if hypotheses:
        for h in hypotheses:
            if h.id == v.hypothesis_id:
                return h.primary_suspect_nf

    # Path 3: fallback.
    return f"<unknown:{v.hypothesis_id}>"


# ============================================================================
# PR 5.5b — Synthesis pool-membership guardrail
# ============================================================================


def lint_synthesis_pool_membership(
    report: DiagnosisReport,
    pool: CandidatePool,
) -> GuardrailResult[DiagnosisReport]:
    """Validate that Synthesis's `primary_suspect_nf` is in the candidate pool.

    Three branches:
      * Empty pool → Synthesis must emit `verdict_kind == "inconclusive"`
        and `primary_suspect_nf is None`. Anything else is REJECT.
      * Non-empty pool, `verdict_kind in ("confirmed", "promoted")` →
        `primary_suspect_nf` MUST be a pool member's `nf`. REJECT
        otherwise.
      * Non-empty pool, `verdict_kind == "inconclusive"` → permitted
        (Synthesis can choose to commit nothing despite a non-empty
        pool when evidence is too weak). Pass.

    The rejection reason lists the pool members and the offending NF so
    Synthesis's resample can pick correctly. Returns PASS / REJECT only;
    no REPAIR path (the value Synthesis emits is the LLM's judgment —
    the runner asks for a fresh judgment rather than us silently
    rewriting).
    """
    pool_nfs = [m.nf for m in pool.members]
    pool_nfs_set = set(pool_nfs)

    # Empty pool branch
    if not pool_nfs_set:
        if report.verdict_kind != "inconclusive":
            return GuardrailResult(
                verdict=GuardrailVerdict.REJECT,
                output=report,
                reason=(
                    "The candidate pool is empty (no NOT_DISPROVEN survivors "
                    "and no NF crossed the alt-suspect corroboration "
                    "threshold). With an empty pool, the only valid output "
                    f"is `verdict_kind=\"inconclusive\"` with "
                    f"`primary_suspect_nf=null`. You emitted "
                    f"`verdict_kind=\"{report.verdict_kind}\"` "
                    f"with `primary_suspect_nf={report.primary_suspect_nf!r}` "
                    "— that is not a permissible diagnosis given the "
                    "evidence. Re-emit with `verdict_kind=\"inconclusive\"` "
                    "and `primary_suspect_nf=null`; aggregate the "
                    "DISPROVEN Investigators' alternative_suspects in the "
                    "explanation as next leads for the human operator."
                ),
                notes={
                    "pool_size": 0,
                    "submitted_nf": report.primary_suspect_nf,
                    "submitted_verdict_kind": report.verdict_kind,
                },
            )
        return GuardrailResult(verdict=GuardrailVerdict.PASS, output=report)

    # Non-empty pool, inconclusive — permitted (rare but legitimate).
    if report.verdict_kind == "inconclusive":
        return GuardrailResult(verdict=GuardrailVerdict.PASS, output=report)

    # Non-empty pool, confirmed/promoted — primary_suspect_nf must be in pool.
    submitted = report.primary_suspect_nf
    if submitted in pool_nfs_set:
        return GuardrailResult(verdict=GuardrailVerdict.PASS, output=report)

    return GuardrailResult(
        verdict=GuardrailVerdict.REJECT,
        output=report,
        reason=(
            f"You emitted `primary_suspect_nf={submitted!r}` with "
            f"`verdict_kind=\"{report.verdict_kind}\"`, but {submitted!r} "
            "is NOT in the candidate pool computed deterministically by "
            "the Decision E aggregator (Phase 6.5). The pool is the "
            "verified set of NFs you are allowed to diagnose:\n\n"
            f"{pool.render_for_prompt()}\n\n"
            "Pick a pool member as `primary_suspect_nf`. If you genuinely "
            "believe none of the pool members is the right answer, set "
            "`verdict_kind=\"inconclusive\"` and `primary_suspect_nf=null` "
            "rather than naming an NF outside the pool — the orchestrator "
            "ran a bounded re-investigation already if this was an "
            "all-DISPROVEN tree, so the pool reflects the strongest "
            "structural answer the pipeline can derive."
        ),
        notes={
            "pool_size": len(pool_nfs),
            "pool_nfs": pool_nfs,
            "submitted_nf": submitted,
            "submitted_verdict_kind": report.verdict_kind,
        },
    )
