"""Decision G — Mechanism-claim grounding (PR 8).

Decisions D and A2 enforce a known set of *layer-scoping* phrases
(`internal`, `due to overload`, `not forwarding`, etc.). Neither
catches NA *fabricating* a mechanism narrative whose words aren't on
those blocklists.

Canonical example (`run_20260501_022351_data_plane_degradation`,
post-PR-4): NA's h1 statement read *"The UPF is overloaded by a
massive GTP-U traffic storm on the N3 interface, causing extreme
packet loss."* The actual fault was tc-netem at the kernel layer.
"Traffic storm" appears nowhere in the metric semantics, the KB's
causal chains, or the supporting events — it's a confabulated
narrative invented to explain an 8x-of-the-wrong-baseline reading.

Decision G's PR 8 ship is the **simpler version** described in the
ADR: a regex blocklist of narrative-mechanism phrases, applied to
`Hypothesis.statement` post-Decisions D and H. REJECT-and-resample
with a constructive shape hint (no KB lookup). The optional KB-
grounding check that would emit "the KB authorizes mechanisms X / Y
for this metric" was deferred to keep the linter synchronous and
free of Neo4j coupling.

Pattern set is intentionally narrower than the ADR draft to limit
false positives. Bare words like `partition`, `cascading`,
`exhausted`, `storm` are excluded because they have legitimate
non-mechanism uses in this domain (3GPP partition events, "cascade
of REGISTERs", "exhaustion timer"). The patterns instead target
phrase-level narratives that are unambiguously mechanism claims
(`traffic storm`, `is overloaded by`, `network partition`,
`cascade failure`, etc.).

Composes with Decisions D and H in `_na_combined_guardrail` —
D runs first (mechanism scoping), H runs on D's PASS (direct-flag
ranking coverage), G runs on H's PASS (narrative fabrication).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..models import Hypothesis, NetworkAnalystReport
from .base import GuardrailResult, GuardrailVerdict


# Narrative-mechanism patterns. Distinct from `_mechanism_scope.py`
# (Decisions D / A2) — those target *layer-scoping* phrases like
# `internal`, `due to overload`. These target *invented narratives*
# that NA writes when the LLM's prior leaps from "metric X is
# elevated" to "the system is in failure mode Y".
_NARRATIVE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # Volume / load narratives
    ("traffic storm",
        re.compile(r"\btraffic storm\b", re.IGNORECASE)),
    ("packet storm",
        re.compile(r"\bpacket storm\b", re.IGNORECASE)),
    ("is overloaded by",
        re.compile(r"\bis overloaded by\b", re.IGNORECASE)),
    ("overload condition",
        re.compile(r"\boverload condition\b", re.IGNORECASE)),
    ("flooded by",
        re.compile(r"\bflooded by\b", re.IGNORECASE)),
    ("flooding from",
        re.compile(r"\bflooding from\b", re.IGNORECASE)),
    ("surge of",
        re.compile(r"\bsurge of\b", re.IGNORECASE)),
    ("spike-induced",
        re.compile(r"\bspike[\- ]induced\b", re.IGNORECASE)),

    # Congestion narratives
    ("congestive failure",
        re.compile(r"\bcongestive failure\b", re.IGNORECASE)),
    ("congestion event",
        re.compile(r"\bcongestion event\b", re.IGNORECASE)),

    # Partition narratives — phrase-level only, bare `partition` has
    # legitimate uses in 3GPP partition events.
    ("network partition",
        re.compile(r"\bnetwork partition\b", re.IGNORECASE)),
    ("partitioned from",
        re.compile(r"\bpartitioned from\b", re.IGNORECASE)),
    ("partitioned away",
        re.compile(r"\bpartitioned away\b", re.IGNORECASE)),

    # Cascade narratives — bare `cascading` has legitimate uses
    # ("cascade of REGISTERs"); only flag when claiming a failure mode.
    ("cascade failure",
        re.compile(r"\bcascade failure\b", re.IGNORECASE)),
    ("cascading failure",
        re.compile(r"\bcascading failure\b", re.IGNORECASE)),

    # Resource-exhaustion narratives
    ("running out of",
        re.compile(r"\brunning out of\b", re.IGNORECASE)),
    ("starvation",
        re.compile(r"\bstarvation\b", re.IGNORECASE)),

    # Catastrophic narratives
    ("meltdown",
        re.compile(r"\bmeltdown\b", re.IGNORECASE)),
    ("breakdown of",
        re.compile(r"\bbreakdown of\b", re.IGNORECASE)),
    ("system breakdown",
        re.compile(r"\bsystem breakdown\b", re.IGNORECASE)),
]


@dataclass
class _HypothesisHits:
    """Per-hypothesis findings for the rejection reason."""
    hypothesis: Hypothesis
    hits: list[str]


def lint_mechanism_grounding(
    report: NetworkAnalystReport,
) -> GuardrailResult[NetworkAnalystReport]:
    """Lint every hypothesis statement against the narrative-
    mechanism pattern set. PASS when all clean; REJECT with a
    constructive shape hint otherwise.

    The reason includes:
        * Per-hypothesis list of offending phrases.
        * The required statement shape (same as Decision D).
        * Guidance on where mechanism intuition can go instead
          (falsification probes, supporting_events grounded in KB).
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
    """Return the labels of every narrative pattern that fires on the
    statement, in stable order. Empty list = clean."""
    return [
        label for label, pattern in _NARRATIVE_PATTERNS
        if pattern.search(statement)
    ]


def _build_rejection_reason(flagged: list[_HypothesisHits]) -> str:
    """Assemble the per-hypothesis rejection feedback NA sees on
    resample."""
    parts: list[str] = [
        "Your previous NetworkAnalystReport was REJECTED by the post-NA "
        "mechanism-grounding linter (Decision G). The linter forbids "
        "narrative-mechanism claims that aren't grounded in observed "
        "evidence or KB-authored causal chains.",
        "",
        "Different from Decision D's layer-scoping check (which catches "
        "phrases like 'internal fault', 'due to overload'), this linter "
        "catches *invented narratives* — mechanism stories the LLM "
        "leaps to when it sees an elevated metric. Examples include "
        "'traffic storm', 'is overloaded by', 'network partition' (as "
        "a claimed mechanism, not the chaos scenario name), 'cascade "
        "failure', 'meltdown'. These are LLM priors, not measurements.",
        "",
    ]

    for f in flagged:
        h = f.hypothesis
        hit_lines = ", ".join(f"'{hit}'" for hit in f.hits)
        parts.append(
            f"Hypothesis `{h.id}` (primary_suspect_nf="
            f"{h.primary_suspect_nf}) contained narrative-mechanism "
            f"phrase(s): {hit_lines}."
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
        "Rewrite each flagged statement to name (a) the observable "
        "that's wrong and (b) the component the fault originates at, "
        "WITHOUT inventing a narrative mechanism. Mechanism intuition, "
        "if you have it, belongs in `falsification_probes` (where the "
        "Investigator can test it) or in `supporting_events` (where "
        "the KB metadata can corroborate it) — NOT in the statement "
        "as fact. Decision D says 'don't scope the HOW'; Decision G "
        "extends that: don't INVENT the HOW either."
    )

    return "\n".join(parts)


def _build_example_correction(h: Hypothesis) -> tuple[str, str]:
    """Return (bad, good) example pair for one hypothesis."""
    bad = h.statement
    nf = h.primary_suspect_nf
    if h.supporting_events:
        observable = f"observed in {h.supporting_events[0]}"
    else:
        observable = "named in the anomaly screener flags"
    good = f"{nf} is the source of the anomalous behavior {observable}."
    return bad, good
