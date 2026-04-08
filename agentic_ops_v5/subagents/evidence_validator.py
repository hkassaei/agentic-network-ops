"""Phase 5: EvidenceValidatorAgent — fact-check LLM claims against real tool calls.

Deterministic BaseAgent that runs between the InvestigatorAgent and the
SynthesisAgent. Cross-references every evidence claim produced by the
NetworkAnalystAgent and the InvestigatorAgent against the actual tool-call
log for those phases, and computes a confidence verdict that the
SynthesisAgent must honor.

Design rationale: LLMs under context pressure can fabricate tool citations
("[EVIDENCE: read_container_logs(...) -> 'tx_send(): No buffer space...']")
when the surrounding narrative already looks complete. Prompt warnings like
"every claim must cite a tool output" are soft constraints that stochastic
generation can violate. This validator is a hard check outside the LLM —
it parses the claimed tool names from the LLM's output and verifies each
one was actually invoked according to the orchestrator's phase trace.

The validator does NOT:
  - Call an LLM (pure text processing)
  - Block downstream phases (Synthesis always runs)
  - Attempt to interpret or correct the hallucinated content

The validator DOES:
  - Count total citations vs. matched citations
  - Detect the "Investigator made zero tool calls" failure mode directly
  - Produce a verdict (clean / has_warnings / severe) and a confidence level
    (high / medium / low / none) that Synthesis reads from session state
  - Provide a summary string the episode recorder can render in the report
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, AsyncGenerator

from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.genai import types
from pydantic import BaseModel, Field

log = logging.getLogger("v5.evidence_validator")


# ---------------------------------------------------------------------------
# Result models
# ---------------------------------------------------------------------------

class ClaimCheck(BaseModel):
    """A single evidence claim, with its validation outcome."""
    raw_text: str
    """The original claim string as the LLM wrote it."""
    claimed_tool: str
    """The tool name extracted from the claim."""
    source_phase: str
    """Which phase produced the claim (NetworkAnalystAgent or InvestigatorAgent)."""
    matched: bool
    """True if the claimed tool was actually invoked in its source phase."""
    match_reason: str
    """Plain-English reason for the match/mismatch verdict."""


class EvidenceValidationResult(BaseModel):
    """Output of the EvidenceValidatorAgent."""
    # Aggregate counts
    total_citations: int = 0
    matched: int = 0
    unmatched: int = 0

    # Per-phase claim checks
    network_analyst_claims: list[ClaimCheck] = Field(default_factory=list)
    investigator_claims: list[ClaimCheck] = Field(default_factory=list)

    # Layer-1 check: did the Investigator actually investigate?
    investigator_tool_call_count: int = 0
    investigator_made_zero_calls: bool = False

    # Verdicts consumed by the SynthesisAgent
    investigator_confidence: str = "high"
    """high | medium | low | none — reflects how much of the Investigator's
    output is backed by real tool calls."""

    verdict: str = "clean"
    """clean | has_warnings | severe — overall validation verdict."""

    summary: str = ""
    """Human-readable summary for the episode report and Synthesis prompt."""


# ---------------------------------------------------------------------------
# Extraction: claimed tool usage from LLM outputs
# ---------------------------------------------------------------------------

# Matches the Investigator's formal citation format:
#   [EVIDENCE: tool_name(args) -> "excerpt"]
#   [EVIDENCE: tool_name(args) -> excerpt]
_INVESTIGATOR_EVIDENCE_RE = re.compile(
    r"\[EVIDENCE:\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\(([^)]*)\)\s*->\s*(.+?)\]",
    re.DOTALL,
)

# Matches "... from tool_name" or "(tool_name)" or "via tool_name" in
# NetworkAnalyst evidence strings. Narrower than the Investigator's format
# because NA evidence is structured Pydantic text, not free-form citations.
_NETWORK_ANALYST_TOOL_REF_RE = re.compile(
    r"(?:from|via|per|using|\()\s*(get_[a-zA-Z_]+|check_[a-zA-Z_]+|compare_[a-zA-Z_]+|read_[a-zA-Z_]+|query_[a-zA-Z_]+|measure_[a-zA-Z_]+)",
)


def _extract_investigator_claims(investigation_text: str) -> list[tuple[str, str]]:
    """Parse [EVIDENCE: tool(args) -> excerpt] citations from Investigator text.

    Returns a list of (raw_citation_text, tool_name) tuples.
    """
    claims: list[tuple[str, str]] = []
    if not investigation_text:
        return claims

    for match in _INVESTIGATOR_EVIDENCE_RE.finditer(investigation_text):
        tool_name = match.group(1).strip()
        raw = match.group(0)
        claims.append((raw, tool_name))
    return claims


def _extract_network_analyst_claims(network_analysis: Any) -> list[tuple[str, str]]:
    """Parse tool references from NetworkAnalyst evidence strings.

    NetworkAnalyst output is a NetworkAnalysis Pydantic dict with
    layer_status[layer].evidence being a list of strings like:
      "ran_ue=0 from get_nf_metrics (expected: 2)"
      "UPF out packets/sec: 0.0 from get_dp_quality_gauges(window_seconds=60)"
    """
    claims: list[tuple[str, str]] = []
    if not network_analysis:
        return claims

    # Accept either a dict or a JSON string
    if isinstance(network_analysis, str):
        try:
            network_analysis = json.loads(network_analysis)
        except (json.JSONDecodeError, ValueError):
            # Fall back: treat the whole string as free text
            for m in _NETWORK_ANALYST_TOOL_REF_RE.finditer(network_analysis):
                claims.append((network_analysis[:200], m.group(1)))
            return claims

    if not isinstance(network_analysis, dict):
        return claims

    # Walk the layer_status → evidence lists
    layer_status = network_analysis.get("layer_status", {}) or {}
    for layer_name, layer in layer_status.items():
        if not isinstance(layer, dict):
            continue
        for evidence_str in (layer.get("evidence") or []):
            if not isinstance(evidence_str, str):
                continue
            for m in _NETWORK_ANALYST_TOOL_REF_RE.finditer(evidence_str):
                claims.append((evidence_str, m.group(1)))

    # Also walk suspect_components[].reason
    for suspect in network_analysis.get("suspect_components", []) or []:
        if not isinstance(suspect, dict):
            continue
        reason = suspect.get("reason", "")
        if not isinstance(reason, str):
            continue
        for m in _NETWORK_ANALYST_TOOL_REF_RE.finditer(reason):
            claims.append((reason, m.group(1)))

    return claims


# ---------------------------------------------------------------------------
# Cross-reference: real tool calls per phase
# ---------------------------------------------------------------------------

def _build_tools_called_per_phase(
    phase_traces: list[dict],
) -> dict[str, set[str]]:
    """Build {phase_name: {tool_name, ...}} from the phase trace list."""
    out: dict[str, set[str]] = {}
    for phase in phase_traces:
        if not isinstance(phase, dict):
            continue
        name = phase.get("agent_name", "")
        tool_calls = phase.get("tool_calls", []) or []
        tool_names = set()
        for tc in tool_calls:
            if isinstance(tc, dict):
                tn = tc.get("name", "")
                if tn:
                    tool_names.add(tn)
        if name:
            out[name] = tool_names
    return out


# ---------------------------------------------------------------------------
# Validation core
# ---------------------------------------------------------------------------

def _check_claims(
    claims: list[tuple[str, str]],
    tools_called_in_source: set[str],
    source_phase: str,
) -> list[ClaimCheck]:
    """Strict name-match validation of claims against tools called in their
    source phase."""
    checks: list[ClaimCheck] = []
    for raw, tool_name in claims:
        matched = tool_name in tools_called_in_source
        reason = (
            f"tool '{tool_name}' called in {source_phase} trace"
            if matched
            else f"tool '{tool_name}' NEVER called in {source_phase} trace — fabricated"
        )
        checks.append(ClaimCheck(
            raw_text=raw[:300],  # truncate very long evidence strings
            claimed_tool=tool_name,
            source_phase=source_phase,
            matched=matched,
            match_reason=reason,
        ))
    return checks


def _determine_confidence_and_verdict(
    investigator_tool_calls: int,
    investigator_citations: int,
    total_citations: int,
    unmatched: int,
) -> tuple[str, str]:
    """Derive (investigator_confidence, verdict) from the aggregate stats."""
    # Layer 1: zero tool calls — Investigator didn't investigate at all
    if investigator_tool_calls == 0:
        return "none", "severe"

    # Layer 2: Investigator called tools but produced zero formal citations.
    # The investigation is unverifiable — tool results exist but the
    # Investigator's narrative doesn't reference them traceably.
    if investigator_citations == 0 and investigator_tool_calls > 0:
        return "low", "has_warnings"

    # Layer 3: normal citation matching
    unmatched_ratio = unmatched / total_citations if total_citations else 0

    if unmatched == 0:
        return "high", "clean"
    if unmatched_ratio <= 0.25:
        return "medium", "has_warnings"
    if unmatched_ratio <= 0.5:
        return "low", "has_warnings"
    return "none", "severe"


def validate(
    network_analysis: Any,
    investigation_text: str,
    phase_traces: list[dict],
) -> EvidenceValidationResult:
    """Pure-function entry point. Validates LLM claims against phase traces.

    Args:
        network_analysis: The NetworkAnalystAgent's structured output (dict
            or JSON string). Its layer_status[].evidence strings are scanned
            for tool-name references.
        investigation_text: The InvestigatorAgent's free-form text output.
            Its [EVIDENCE: tool(args) -> "..."] citations are parsed.
        phase_traces: List of phase trace dicts (from the orchestrator's
            accumulated PhaseTrace list, serialized via .model_dump()).
            Each must contain agent_name and tool_calls.

    Returns:
        EvidenceValidationResult with per-claim outcomes and aggregate
        verdict/confidence fields.
    """
    tools_per_phase = _build_tools_called_per_phase(phase_traces)

    na_tools = tools_per_phase.get("NetworkAnalystAgent", set())
    inv_tools = tools_per_phase.get("InvestigatorAgent", set())

    # Extract claims
    na_claim_pairs = _extract_network_analyst_claims(network_analysis)
    inv_claim_pairs = _extract_investigator_claims(investigation_text)

    # Validate
    na_checks = _check_claims(na_claim_pairs, na_tools, "NetworkAnalystAgent")
    inv_checks = _check_claims(inv_claim_pairs, inv_tools, "InvestigatorAgent")

    total = len(na_checks) + len(inv_checks)
    matched = sum(1 for c in na_checks if c.matched) + sum(1 for c in inv_checks if c.matched)
    unmatched = total - matched

    inv_tool_count = len(inv_tools)
    inv_zero_calls = inv_tool_count == 0

    inv_citation_count = len(inv_checks)
    confidence, verdict = _determine_confidence_and_verdict(
        investigator_tool_calls=inv_tool_count,
        investigator_citations=inv_citation_count,
        total_citations=total,
        unmatched=unmatched,
    )

    # Build human-readable summary
    lines = []
    if inv_zero_calls:
        lines.append(
            "⚠️ CRITICAL: InvestigatorAgent made ZERO tool calls — "
            "no actual verification was performed."
        )
    elif inv_citation_count == 0 and inv_tool_count > 0:
        lines.append(
            f"⚠️ WARNING: InvestigatorAgent made {inv_tool_count} tool calls but "
            f"produced ZERO [EVIDENCE: ...] citations. The investigation narrative "
            f"is unverifiable — tool results exist but are not traceably referenced."
        )
    lines.append(
        f"Evidence validation: {matched}/{total} citations verified "
        f"({unmatched} unmatched). "
        f"Investigator: {inv_citation_count} citations from {inv_tool_count} tool calls."
    )
    lines.append(f"Verdict: {verdict}. Investigator confidence: {confidence}.")
    if unmatched > 0:
        unmatched_examples = [c for c in (na_checks + inv_checks) if not c.matched][:3]
        lines.append("Unmatched citations (sample):")
        for c in unmatched_examples:
            lines.append(
                f"  - [{c.source_phase}] claimed '{c.claimed_tool}' — {c.match_reason}"
            )

    summary = "\n".join(lines)

    return EvidenceValidationResult(
        total_citations=total,
        matched=matched,
        unmatched=unmatched,
        network_analyst_claims=na_checks,
        investigator_claims=inv_checks,
        investigator_tool_call_count=inv_tool_count,
        investigator_made_zero_calls=inv_zero_calls,
        investigator_confidence=confidence,
        verdict=verdict,
        summary=summary,
    )


# ---------------------------------------------------------------------------
# Agent wrapper
# ---------------------------------------------------------------------------

class EvidenceValidatorAgent(BaseAgent):
    """Deterministic fact-checker for LLM evidence claims."""

    name: str = "EvidenceValidatorAgent"
    description: str = (
        "Validates evidence citations from the NetworkAnalystAgent and "
        "InvestigatorAgent against the actual tool-call log. Produces a "
        "confidence verdict that the SynthesisAgent honors."
    )

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        state = ctx.session.state

        network_analysis = state.get("network_analysis")
        investigation_text = str(state.get("investigation", ""))
        phase_traces = state.get("phase_traces_so_far", []) or []

        log.info(
            "Validating evidence: %d phase traces, investigation_text=%d chars, "
            "network_analysis type=%s",
            len(phase_traces),
            len(investigation_text),
            type(network_analysis).__name__,
        )
        if phase_traces:
            for pt in phase_traces:
                agent = pt.get("agent_name", "?") if isinstance(pt, dict) else "?"
                tc = pt.get("tool_calls", []) if isinstance(pt, dict) else []
                log.info("  Phase trace: %s — %d tool calls", agent, len(tc))
        else:
            log.warning("  NO phase traces available — evidence validation will be limited")

        try:
            result = validate(
                network_analysis=network_analysis,
                investigation_text=investigation_text,
                phase_traces=phase_traces,
            )
        except Exception as e:
            log.error("Evidence validation failed: %s", e)
            result = EvidenceValidationResult(
                verdict="severe",
                investigator_confidence="none",
                summary=f"Evidence validation failed with error: {e}",
            )

        log.info(
            "Evidence verdict: %s (confidence=%s, %d/%d matched)",
            result.verdict, result.investigator_confidence,
            result.matched, result.total_citations,
        )

        yield Event(
            author=self.name,
            content=types.Content(parts=[types.Part(text=result.summary)]),
            actions=EventActions(state_delta={
                "evidence_validation": result.model_dump(),
                "investigator_confidence": result.investigator_confidence,
            }),
        )

    async def _run_live_impl(self, ctx):
        raise NotImplementedError


def create_evidence_validator() -> EvidenceValidatorAgent:
    """Factory for the EvidenceValidatorAgent."""
    return EvidenceValidatorAgent()
