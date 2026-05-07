"""The Investigator prompt must teach the LLM how to handle
PROBE_TOOL_UNAVAILABLE results — otherwise the gating in
agentic_ops/tools.py is wasted (the LLM sees an unfamiliar string and
defaults to AMBIGUOUS, which is exactly the silent-non-evidence path
the ADR is closing).

Cheap string-match insurance, not a behavioral test. If the prompt
gets rewritten in a way that drops the rule, this fails before merge.

See docs/ADR/nf_container_diagnostic_tooling.md.
"""

from __future__ import annotations

from pathlib import Path


_PROMPT = (
    Path(__file__).resolve().parents[1]
    / "prompts"
    / "investigator.md"
).read_text()


def test_prompt_mentions_token_and_outcome():
    assert "PROBE_TOOL_UNAVAILABLE" in _PROMPT, (
        "Investigator prompt does not mention the PROBE_TOOL_UNAVAILABLE "
        "token. Without it the LLM cannot map the gating signal from "
        "agentic_ops/tools.py to ProbeResult.outcome='tool_unavailable'."
    )
    assert "tool_unavailable" in _PROMPT, (
        "Investigator prompt does not mention outcome='tool_unavailable'. "
        "The LLM needs explicit teaching to populate this enum value."
    )


def test_prompt_says_tool_unavailable_is_not_evidence():
    """The prompt must tell the LLM not to count tool_unavailable
    probes as CONSISTENT or CONTRADICTS — otherwise the confidence-cap
    filter is fighting the LLM rather than reinforcing it."""
    lower = _PROMPT.lower()
    # Look for any of these phrasings that capture the rule. If the
    # prompt is rewritten with new wording, update one of these
    # substrings to match.
    candidates = [
        "do not count it as consistent",
        "do not count it as contradicts",
        "do not count tool_unavailable",
        "tool-unavailable probes do not produce evidence",
    ]
    assert any(c in lower for c in candidates), (
        "Investigator prompt does not state that tool_unavailable "
        "probes must not count as evidence. One of these substrings "
        f"must appear: {candidates}"
    )
