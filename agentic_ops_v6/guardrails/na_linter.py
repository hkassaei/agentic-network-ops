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

import re
from dataclasses import dataclass

from ..models import Hypothesis, NetworkAnalystReport
from .base import GuardrailResult, GuardrailVerdict


# Each (label, pattern) pair flags one class of mechanism-scoping
# phrase. Patterns are compiled with re.IGNORECASE. Word-boundary
# anchors avoid false positives on substring matches inside
# unrelated words. Order is rough: most-specific phrases first so
# the per-hypothesis hit list reads naturally.
_BLOCKLIST: list[tuple[str, re.Pattern[str]]] = [
    ("internal fault",
        re.compile(r"\binternal fault\b", re.IGNORECASE)),
    ("internal bug",
        re.compile(r"\binternal bug\b", re.IGNORECASE)),
    ("due to a bug",
        re.compile(r"\bdue to (?:a |the )?bug\b", re.IGNORECASE)),
    ("due to resource exhaustion",
        re.compile(
            r"\bdue to (?:a |the )?resource (?:exhaustion|issue|issues)\b",
            re.IGNORECASE,
        )),
    ("resource exhaustion",
        re.compile(r"\bresource exhaustion\b", re.IGNORECASE)),
    ("buffer overflow",
        re.compile(r"\bbuffer overflow\b", re.IGNORECASE)),
    ("due to overload",
        re.compile(r"\bdue to (?:overload|the overload|an overload)\b",
                   re.IGNORECASE)),
    ("overwhelmed by",
        re.compile(r"\boverwhelmed by\b", re.IGNORECASE)),
    ("flooded with",
        re.compile(r"\bflooded with\b", re.IGNORECASE)),
    ("due to a crash",
        re.compile(r"\bdue to (?:a |the )?crash\b", re.IGNORECASE)),
    ("crashed",
        re.compile(r"\bcrashed\b", re.IGNORECASE)),
    ("not running",
        re.compile(r"\bnot running\b", re.IGNORECASE)),
    ("not forwarding",
        re.compile(r"\bnot forwarding\b", re.IGNORECASE)),
    ("misconfigured",
        re.compile(r"\bmisconfigured\b", re.IGNORECASE)),
    ("due to misconfiguration",
        re.compile(r"\bdue to (?:a |the )?misconfiguration\b",
                   re.IGNORECASE)),
    ("due to a configuration error",
        re.compile(r"\bdue to (?:a |the )?configuration error\b",
                   re.IGNORECASE)),
    # `internal` last so the more-specific phrases above match first
    # in the per-hypothesis hit list. The bare-word match catches the
    # "experiencing an internal X" pattern that the more-specific
    # phrases miss when X varies.
    ("internal",
        re.compile(r"\binternal(?:ly)?\b", re.IGNORECASE)),
]


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
    return [label for label, pattern in _BLOCKLIST if pattern.search(statement)]


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
