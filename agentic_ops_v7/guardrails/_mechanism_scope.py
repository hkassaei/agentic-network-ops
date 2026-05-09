"""Shared mechanism-scoping regex blocklist.

Decision D's NA hypothesis-statement linter and Decision A's sub-check A2
(IG-statement linter) both forbid mechanism-scoping language in
LLM-authored free-text fields. Same pattern set; different fields. This
module is the single source of truth for the regex patterns; each linter
imports `BASE_PATTERNS` and may extend it with its own domain-specific
additions.

Why a private module (leading underscore) rather than a public part of the
package: callers should always go through one of the two linter
entrypoints (`na_linter.lint_na_hypotheses` or
`ig_validator.lint_ig_plan`), not reach for the patterns directly. The
module name signals that intent.

Pattern ordering note: keep the most-specific phrases ahead of the bare
`internal` catch-all, so per-hit summaries read naturally
(e.g. "internal fault" reported before the more generic "internal" hit
is double-reported on the same span).
"""

from __future__ import annotations

import re

# Base mechanism-scoping patterns — applied verbatim by both NA's
# Hypothesis.statement linter and IG's expected/falsifying-observation
# linter. Word-boundary anchors avoid matching substrings inside unrelated
# words.
BASE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
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
    # `internal` last — the bare-word match catches "experiencing an
    # internal X" patterns the more-specific phrases above miss when X
    # varies.
    ("internal",
        re.compile(r"\binternal(?:ly)?\b", re.IGNORECASE)),
]


def scan(text: str, patterns: list[tuple[str, re.Pattern[str]]]) -> list[str]:
    """Return the labels of every pattern that fires on `text`, in stable
    order. Empty list = no hits."""
    return [label for label, pattern in patterns if pattern.search(text)]
