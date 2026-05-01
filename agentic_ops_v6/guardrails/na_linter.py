"""Decision D — NA hypothesis-statement linter.

Forbids mechanism-scoping language in `Hypothesis.statement`. Principle
#10 of the NA prompt already says the same thing in prose; this module
makes it mechanical.

Failure mode the linter prevents (per ADR Decision D and observed in
`run_20260430_020037_data_plane_degradation`):

    NA writes "UPF is dropping packets due to internal resource
    exhaustion or buffer overflow." NA correctly named UPF as the
    primary suspect, but pre-committed to a user-space mechanism. The
    Investigator queries UPF's resource metrics, sees them clean
    (because the actual fault is at the tc / kernel layer), and writes
    DISPROVEN. The right NF gets falsified on a layer mismatch.

The linter rejects any statement that contains a mechanism-scoping
phrase. The runner resamples NA once with the rejection reason
injected into session state; NA reads `{guardrail_rejection_reason}`
from its prompt and rewrites. On a second still-flagged emit, the
runner's `on_guardrail_exhausted="accept"` policy lets the imperfect
statement through with a structured warning rather than failing the
whole pipeline.

Design notes:

  * Word-boundary regex anchors on every pattern so legitimate uses
    don't false-positive (e.g. "the metric is internal to the NF" is
    NOT flagged, but "experiencing an internal fault" is).
  * Rejection reason includes a per-hypothesis bad/good example built
    from the offending hypothesis's `primary_suspect_nf` and
    `supporting_events`. The dynamic example is what actually changes
    NA's behavior on resample — a generic "rewrite without mechanism
    words" instruction has been in the prompt for weeks and hasn't
    been enough.
  * No LLM in the linter. Pure regex over Pydantic-typed fields.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..models import Hypothesis, NetworkAnalystReport
from ._mechanism_scope import BASE_PATTERNS, scan
from .base import GuardrailResult, GuardrailVerdict


@dataclass
class _HypothesisHits:
    """Per-hypothesis lint findings used to assemble the rejection reason."""
    hypothesis: Hypothesis
    hits: list[str]  # blocklist labels that fired on this statement


def lint_na_hypotheses(
    report: NetworkAnalystReport,
) -> GuardrailResult[NetworkAnalystReport]:
    """Lint every hypothesis statement against the mechanism-scoping
    blocklist. Return PASS when all clean, REJECT otherwise.

    The REJECT reason is assembled with a per-hypothesis breakdown:
    for each flagged hypothesis, list the hits that fired and a
    bad/good example correction grounded in that hypothesis's
    primary_suspect_nf + first supporting_event. NA's resample reads
    this from session state.
    """
    flagged: list[_HypothesisHits] = []
    for h in report.hypotheses:
        hits = _scan_statement(h.statement)
        if hits:
            flagged.append(_HypothesisHits(hypothesis=h, hits=hits))

    if not flagged:
        return GuardrailResult(
            verdict=GuardrailVerdict.PASS,
            output=report,
        )

    reason = _build_rejection_reason(flagged)
    notes = {
        "flagged_count": len(flagged),
        "per_hypothesis": [
            {
                "id": f.hypothesis.id,
                "primary_suspect_nf": f.hypothesis.primary_suspect_nf,
                "hits": f.hits,
            }
            for f in flagged
        ],
    }
    return GuardrailResult(
        verdict=GuardrailVerdict.REJECT,
        output=report,
        reason=reason,
        notes=notes,
    )


def _scan_statement(statement: str) -> list[str]:
    """Return the labels of every blocklist pattern that fires on the
    statement, in stable order. Empty list = clean."""
    return scan(statement, BASE_PATTERNS)


def _build_rejection_reason(flagged: list[_HypothesisHits]) -> str:
    """Assemble the per-hypothesis rejection feedback NA sees on resample.

    Includes:
      * The list of offending phrases per hypothesis (so NA knows which
        words to remove).
      * A dynamic bad/good example grounded in that hypothesis's NF +
        first supporting_event (so NA has a concrete shape to imitate).
      * The "where to put mechanism intuition instead" reminder.
    """
    parts: list[str] = [
        "Your previous NetworkAnalystReport was REJECTED by the post-NA "
        "hypothesis-statement linter. The linter forbids mechanism-scoping "
        "language in Hypothesis.statement (NA principle #10). When the "
        "statement names a HOW, the Investigator may correctly localize "
        "the fault to the named component and still disprove the "
        "hypothesis because the actual failure was at a different layer "
        "of the same component. The component was right; the adjective "
        "wasn't.",
        "",
    ]

    for f in flagged:
        h = f.hypothesis
        hit_lines = ", ".join(f"'{hit}'" for hit in f.hits)
        parts.append(
            f"Hypothesis `{h.id}` (primary_suspect_nf={h.primary_suspect_nf}) "
            f"contained mechanism-scoping phrase(s): {hit_lines}."
        )
        parts.append(
            f"  Offending statement: \"{h.statement}\""
        )
        parts.append(
            "  Required shape: \"<NF> is the source of <observable> "
            "[observed in <metric or event>].\""
        )
        bad, good = _build_example_correction(h)
        parts.append(f"  Example correction:")
        parts.append(f"    Bad:  \"{bad}\"")
        parts.append(f"    Good: \"{good}\"")
        parts.append("")

    parts.append(
        "Rewrite each flagged statement to name (a) the observable that's "
        "wrong and (b) the component the fault originates at, WITHOUT "
        "scoping the mechanism. If you have a strong mechanism intuition "
        "(e.g. 'likely kernel-layer drop, not user-space'), record it as "
        "a `falsification_probe` whose `args_hint` distinguishes that "
        "mechanism from sibling mechanisms at the same component — NOT "
        "in the statement."
    )

    return "\n".join(parts)


def _build_example_correction(h: Hypothesis) -> tuple[str, str]:
    """Return a (bad, good) example pair specific to this hypothesis.

    `bad` quotes the actual offending statement so NA sees its own
    output. `good` is a clean rewrite anchored on the NF + the first
    supporting_event (or a generic observable fallback if no
    supporting_events were emitted).
    """
    bad = h.statement
    nf = h.primary_suspect_nf
    if h.supporting_events:
        observable = f"observed in {h.supporting_events[0]}"
    else:
        observable = "named in the anomaly screener flags"
    good = f"{nf} is the source of the anomalous behavior {observable}."
    return bad, good
