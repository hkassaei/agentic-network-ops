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

# Enumerated tool names the Investigator has access to. When the
# InstructionGenerator emits a falsification probe, the `tool` field is
# constrained to these exact strings at Gemini's structured-output
# decoding layer. This forecloses two Gemini failure modes observed in
# production: (a) emitting hallucinated tool names ("log_search",
# "tcpdump"), (b) emitting a probe with empty / plausible-prose values
# because every required field is a free string.
#
# MUST stay in exact sync with `create_investigator_agent().tools=[...]`
# in agentic_ops_v6/subagents/investigator.py. A regression test in
# agentic_ops_v6/tests/test_wiring.py asserts the two match. If the
# Investigator's tool list changes, update this literal in the same
# commit.
_InvestigatorTool = Literal[
    "measure_rtt",
    "check_process_listeners",
    "get_nf_metrics",
    "get_dp_quality_gauges",
    "get_network_status",
    "run_kamcmd",
    "read_running_config",
    "read_env_config",
    "query_subscriber",
    "list_flows",
    "get_flow",
    "get_flows_through_component",
    "get_causal_chain",
    "find_chains_by_observable_metric",
    "OntologyConsultationAgent",
]

# Enumerated NF names the agent may name as a primary suspect. Matches
# NF_LAYER in agentic_ops_common.metric_kb.feature_mapping — the same
# source of truth used by the flag-enrichment and raw-lookup paths.
# Constraining this field at the schema layer prevents Gemini from
# inventing NF names like "hss" or "proxy" and forces it to name a
# real component the rest of the pipeline can route to.
_KnownNF = Literal[
    "amf", "smf", "upf", "pcf", "ausf", "udm", "udr", "nrf",
    "pcscf", "icscf", "scscf", "pyhss", "rtpengine",
    "mongo", "mysql", "dns",
    "nr_gnb",
]


class FalsificationProbe(BaseModel):
    """One concrete probe the Investigator should run."""
    tool: _InvestigatorTool = Field(
        ..., description="Must be one of the Investigator's registered tools."
    )
    args_hint: str = Field("", description="natural-language arg guidance")
    expected_if_hypothesis_holds: str
    falsifying_observation: str


class FalsificationPlan(BaseModel):
    """Plan for falsifying ONE hypothesis.

    Produced by the InstructionGenerator, one per hypothesis the NA proposed.
    Schema-level requirements (enforced by Gemini's constrained decoder at
    generation time, not just Pydantic-side validation):
      - `primary_suspect_nf` must be a known NF name.
      - `probes` must have at least 2 entries and at most 4.
    These foreclose the "schema-valid but empty" short-circuit failure
    mode where Gemini would emit plans with zero probes or name an
    invented NF.
    """
    hypothesis_id: str
    hypothesis_statement: str
    primary_suspect_nf: _KnownNF
    probes: list[FalsificationProbe] = Field(
        ...,
        min_length=2,
        max_length=4,
        description="2–4 probes per plan (target 3).",
    )
    notes: str = ""


class FalsificationPlanSet(BaseModel):
    """The full set of per-hypothesis plans the orchestrator will fan out.

    Schema-level requirement: at least one plan. The Network Analyst is
    required to emit at least one hypothesis (upstream schema), so the
    IG always has at least one plan to produce. An empty `plans` list is
    a symptom of the `tools + output_schema` short-circuit and should
    not be silently accepted.
    """
    plans: list[FalsificationPlan] = Field(
        ...,
        min_length=1,
        description="One plan per NA hypothesis.",
    )


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
