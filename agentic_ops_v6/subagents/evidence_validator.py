"""EvidenceValidator — v6 version, per-sub-Investigator citation checking.

v6 spawns N sub-Investigators in parallel. Each has its own tool-call
trace and citation set. This validator checks every sub-Investigator's
citations against its own trace, produces per-agent verdicts, then
aggregates into an overall verdict for Synthesis.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger("v6.evidence_validator")

# Regex matches [EVIDENCE: tool_name(...) -> "..."]
_EVIDENCE_RE = re.compile(
    r"\[EVIDENCE:\s*([\w_]+)\s*\("
)


@dataclass
class PerAgentValidation:
    agent_name: str
    tool_calls_made: int
    citations_found: int
    citations_matched: int
    citations_unmatched: int
    verdict: str  # clean | has_warnings | severe
    confidence: str  # high | medium | low | none
    notes: list[str] = field(default_factory=list)


@dataclass
class EvidenceValidationResult:
    overall_verdict: str
    overall_confidence: str
    per_agent: list[PerAgentValidation] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_verdict": self.overall_verdict,
            "overall_confidence": self.overall_confidence,
            "per_agent": [
                {
                    "agent_name": p.agent_name,
                    "tool_calls_made": p.tool_calls_made,
                    "citations_found": p.citations_found,
                    "citations_matched": p.citations_matched,
                    "citations_unmatched": p.citations_unmatched,
                    "verdict": p.verdict,
                    "confidence": p.confidence,
                    "notes": p.notes,
                }
                for p in self.per_agent
            ],
            "summary": self.summary,
        }


def validate_evidence(
    phase_traces: list[dict],
    investigator_outputs: list[dict],
) -> EvidenceValidationResult:
    """Validate evidence citations across all sub-Investigators.

    Args:
        phase_traces: list of serialized PhaseTrace dicts, including each
            sub-Investigator's tool_calls list.
        investigator_outputs: list of investigator verdict dicts. Each must
            carry its own `agent_name` (or hypothesis_id) + rendered text
            including [EVIDENCE: ...] citations if any were produced.

    Returns:
        EvidenceValidationResult with per-agent and overall verdicts.
    """
    per_agent: list[PerAgentValidation] = []

    # Index phase traces by agent name for quick lookup
    traces_by_agent: dict[str, dict] = {}
    for t in phase_traces:
        name = t.get("agent_name", "")
        if name:
            traces_by_agent.setdefault(name, t)

    for inv in investigator_outputs:
        agent_name = inv.get("agent_name", "UnknownInvestigator")
        trace = traces_by_agent.get(agent_name, {})
        tools_called = {
            tc.get("name", "")
            for tc in trace.get("tool_calls", [])
            if tc.get("name")
        }
        tool_call_count = len(trace.get("tool_calls", []))

        # Extract citations from investigator's rendered text
        text = _render_investigator_text(inv)
        cited_tools = _EVIDENCE_RE.findall(text)
        citations_found = len(cited_tools)
        citations_matched = sum(1 for t in cited_tools if t in tools_called)
        citations_unmatched = citations_found - citations_matched

        notes: list[str] = []
        if tool_call_count == 0:
            verdict = "severe"
            confidence = "none"
            notes.append("ZERO tool calls — all citations fabricated")
        elif citations_unmatched > 0 and citations_unmatched >= citations_matched:
            verdict = "severe"
            confidence = "low"
            notes.append(f"{citations_unmatched}/{citations_found} citations unmatched")
        elif citations_unmatched > 0:
            verdict = "has_warnings"
            confidence = "medium"
            notes.append(f"{citations_unmatched}/{citations_found} citations unmatched")
        elif tool_call_count < 2:
            verdict = "has_warnings"
            confidence = "medium"
            notes.append(f"only {tool_call_count} tool call (below minimum of 2)")
        else:
            verdict = "clean"
            confidence = "high"

        per_agent.append(PerAgentValidation(
            agent_name=agent_name,
            tool_calls_made=tool_call_count,
            citations_found=citations_found,
            citations_matched=citations_matched,
            citations_unmatched=citations_unmatched,
            verdict=verdict,
            confidence=confidence,
            notes=notes,
        ))

    # Aggregate: worst sub-investigator's verdict becomes overall
    overall_verdict, overall_confidence = _aggregate_verdicts(per_agent)

    summary_lines = [
        f"Evidence validation across {len(per_agent)} sub-Investigator(s): "
        f"overall verdict={overall_verdict}, confidence={overall_confidence}.",
    ]
    for p in per_agent:
        summary_lines.append(
            f"  - {p.agent_name}: {p.tool_calls_made} tool calls, "
            f"{p.citations_matched}/{p.citations_found} citations verified "
            f"({p.verdict}, {p.confidence})"
            + (f" — {'; '.join(p.notes)}" if p.notes else "")
        )
    summary = "\n".join(summary_lines)

    return EvidenceValidationResult(
        overall_verdict=overall_verdict,
        overall_confidence=overall_confidence,
        per_agent=per_agent,
        summary=summary,
    )


def _render_investigator_text(inv: dict) -> str:
    """Best-effort render of an investigator's output as text."""
    if "raw_text" in inv:
        return str(inv["raw_text"])
    # Otherwise walk expected fields
    parts: list[str] = []
    for key in ("reasoning", "summary"):
        if inv.get(key):
            parts.append(str(inv[key]))
    for probe in inv.get("probes_executed", []) or []:
        if isinstance(probe, dict):
            for field_name in ("observation", "commentary"):
                if probe.get(field_name):
                    parts.append(str(probe[field_name]))
    return "\n".join(parts)


def _aggregate_verdicts(
    per_agent: list[PerAgentValidation],
) -> tuple[str, str]:
    if not per_agent:
        return "severe", "none"
    verdicts = {p.verdict for p in per_agent}
    confidences = {p.confidence for p in per_agent}

    if "severe" in verdicts:
        overall_v = "severe"
    elif "has_warnings" in verdicts:
        overall_v = "has_warnings"
    else:
        overall_v = "clean"

    # Confidence: tightest (lowest) wins
    order = ["none", "low", "medium", "high"]
    lowest = min((order.index(c) for c in confidences if c in order), default=0)
    overall_c = order[lowest]
    return overall_v, overall_c
