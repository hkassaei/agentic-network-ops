"""v6-specific structured models.

The NetworkAnalyst, InstructionGenerator, Investigator, and Synthesis
agents all produce structured Pydantic outputs. Defined here in one place
so the orchestrator can parse and pass them between phases.

Shared trace models (InvestigationTrace, PhaseTrace, etc.) live in
agentic_ops_common.models; v6 re-exports them here for caller convenience.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field

# Re-export common trace models
from agentic_ops_common.models import (  # noqa: F401
    InvestigationTrace,
    PhaseTrace,
    TokenBreakdown,
    ToolCallTrace,
)


# ============================================================================
# NetworkAnalyst output
# ============================================================================

class LayerStatus(BaseModel):
    """One layer's health in the NA's report."""
    rating: Literal["green", "yellow", "red"] = "green"
    evidence: list[str] = Field(default_factory=list)
    note: str = ""


class Hypothesis(BaseModel):
    """A candidate root-cause hypothesis.

    Ranked by explanatory_fit first, testability second, specificity third.
    Hypotheses without any identifiable falsification probes are DROPPED by
    the orchestrator (testable=False won't be investigated).
    """
    id: str = Field(..., description="short unique id within this episode, e.g. 'h1'")
    statement: str = Field(..., description="specific-mechanism claim, 1-2 sentences")
    primary_suspect_nf: str = Field(..., description="the NF this hypothesis implicates")
    supporting_events: list[str] = Field(
        default_factory=list,
        description="event_type ids observed that support this hypothesis",
    )
    explanatory_fit: float = Field(
        0.0, ge=0.0, le=1.0,
        description="0-1 estimate of how well this hypothesis explains observations",
    )
    falsification_probes: list[str] = Field(
        default_factory=list,
        description="concrete probes that would disprove this; empty = drop",
    )
    specificity: Literal["specific", "moderate", "vague"] = "moderate"


class NetworkAnalystReport(BaseModel):
    """NA output: layer assessment + ranked hypotheses."""
    summary: str
    layer_status: dict[str, LayerStatus] = Field(default_factory=dict)
    hypotheses: list[Hypothesis] = Field(default_factory=list)


# ============================================================================
# CorrelationAnalyzer output (Python-only, no LLM)
# ============================================================================

class CorrelationAnalysis(BaseModel):
    """Wrap the correlation engine's output for agent consumption."""
    episode_id: str
    events_considered: int
    top_statement: Optional[str] = None
    top_primary_nf: Optional[str] = None
    top_explanatory_fit: float = 0.0
    hypotheses_text: str = ""  # rendered text for LLM prompt injection


# ============================================================================
# InstructionGenerator output
# ============================================================================

class FalsificationProbe(BaseModel):
    """One concrete probe the Investigator should run."""
    tool: str = Field(..., description="the tool name, e.g. 'measure_rtt'")
    args_hint: str = Field("", description="natural-language arg guidance")
    expected_if_hypothesis_holds: str
    falsifying_observation: str


class FalsificationPlan(BaseModel):
    """Plan for falsifying ONE hypothesis.

    Produced by the InstructionGenerator, one per hypothesis the NA proposed.
    """
    hypothesis_id: str
    hypothesis_statement: str
    primary_suspect_nf: str
    probes: list[FalsificationProbe] = Field(
        default_factory=list,
        description="minimum 2, target 3",
    )
    notes: str = ""


class FalsificationPlanSet(BaseModel):
    """The full set of per-hypothesis plans the orchestrator will fan out."""
    plans: list[FalsificationPlan] = Field(default_factory=list)


# ============================================================================
# Investigator output (per sub-agent)
# ============================================================================

class ProbeResult(BaseModel):
    """Outcome of one probe."""
    probe_description: str
    tool_call: str = ""                     # what was called
    observation: str = ""                    # what was observed (with [EVIDENCE: ...])
    compared_to_expected: Literal[
        "CONSISTENT", "CONTRADICTS", "AMBIGUOUS"
    ] = "AMBIGUOUS"
    commentary: str = ""


class InvestigatorVerdict(BaseModel):
    """Single sub-Investigator's falsification verdict for ONE hypothesis."""
    hypothesis_id: str
    hypothesis_statement: str
    verdict: Literal["DISPROVEN", "NOT_DISPROVEN", "INCONCLUSIVE"]
    reasoning: str
    probes_executed: list[ProbeResult] = Field(default_factory=list)
    alternative_suspects: list[str] = Field(
        default_factory=list,
        description="populated when verdict == DISPROVEN",
    )


# ============================================================================
# Synthesis output
# ============================================================================

class DiagnosisReport(BaseModel):
    """Final NOC-ready diagnosis produced by Synthesis."""
    summary: str
    root_cause: str
    root_cause_confidence: Literal["high", "medium", "low"]
    affected_components: list[dict] = Field(default_factory=list)
    timeline: list[str] = Field(default_factory=list)
    recommendation: str
    explanation: str
