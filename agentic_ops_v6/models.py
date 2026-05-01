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
# Shared enumerated types — used by multiple agent schemas
# ============================================================================

# Enumerated NF names the agents may name as a primary suspect.
# Matches NF_LAYER in agentic_ops_common.metric_kb.feature_mapping —
# the same source of truth used by flag-enrichment and raw-lookup. Used
# by both `Hypothesis.primary_suspect_nf` (NetworkAnalyst output) and
# `FalsificationPlan.primary_suspect_nf` (InstructionGenerator output).
# Constraining at the schema layer (Gemini's constrained decoder) means
# the LLM cannot invent NF names like `hss` (legacy for `pyhss`) or
# `proxy`; it must commit to a real component the rest of the pipeline
# can route to.
#
# A drift-guard test in agentic_ops_v6/tests/test_wiring.py asserts
# this stays in sync with the canonical NF list. If someone adds an NF
# to the deployment, update both sides in the same commit.
_KnownNF = Literal[
    "amf", "smf", "upf", "pcf", "ausf", "udm", "udr", "nrf",
    "pcscf", "icscf", "scscf", "pyhss", "rtpengine",
    "mongo", "mysql", "dns",
    "nr_gnb",
]


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
    Schema-level requirements (enforced by Gemini's constrained decoder):
      - `primary_suspect_nf` must be a known NF name. Forecloses the
        "Gemini invents a fake NF" failure mode observed in past runs.
      - `falsification_probes` must contain at least 1 entry. The
        prompt already says "untestable hypotheses are DROPPED" — the
        schema makes that mechanical.
    """
    id: str = Field(..., description="short unique id within this episode, e.g. 'h1'")
    statement: str = Field(..., min_length=1, description="specific-mechanism claim, 1-2 sentences")
    primary_suspect_nf: _KnownNF = Field(..., description="the NF this hypothesis implicates")
    supporting_events: list[str] = Field(
        default_factory=list,
        description="event_type ids observed that support this hypothesis",
    )
    explanatory_fit: float = Field(
        0.0, ge=0.0, le=1.0,
        description="0-1 estimate of how well this hypothesis explains observations",
    )
    falsification_probes: list[str] = Field(
        ...,
        min_length=1,
        description="concrete probes that would disprove this; >= 1 required",
    )
    specificity: Literal["specific", "moderate", "vague"] = "moderate"


class NetworkAnalystReport(BaseModel):
    """NA output: layer assessment + ranked hypotheses.

    Schema-level requirements (enforced by Gemini's constrained decoder):
      - `summary` must be non-empty. An empty summary signals the
        Gemini `tools + output_schema` short-circuit that produced the
        Apr-28 `p_cscf_latency` regression.
      - `hypotheses` must contain 1–3 entries. The prompt caps at 3
        ("Cap: produce at most 3 hypotheses"); requiring at least 1
        prevents the empty-output failure mode where NA emits a
        hypotheses-less report and the orchestrator skips Phase 4
        entirely.
    """
    summary: str = Field(..., min_length=1)
    layer_status: dict[str, LayerStatus] = Field(default_factory=dict)
    hypotheses: list[Hypothesis] = Field(
        ...,
        min_length=1,
        max_length=3,
        description="1–3 ranked hypotheses (the orchestrator caps parallel investigators at 3).",
    )


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
    # `get_nf_metrics` was replaced with `get_diagnostic_metrics` per
    # ADR `get_diagnostic_metrics_tool.md`. The constrained-decoder
    # enum here gates what tool names the InstructionGenerator's plans
    # can reference; since IG can no longer ask the Investigator to
    # call get_nf_metrics, the literal must reflect that.
    "get_diagnostic_metrics",
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

# `_KnownNF` is defined once at module-top in the "Shared enumerated
# types" section and reused by both `Hypothesis.primary_suspect_nf`
# (NetworkAnalyst) and `FalsificationPlan.primary_suspect_nf` (IG).


class FalsificationProbe(BaseModel):
    """One concrete probe the Investigator should run.

    `conflates_with` exists because some probe readings are
    compositional — their value is a function of more than one
    element (directional path probes, request-response timings,
    throughput ratios across a boundary). A single reading from
    such a probe cannot, in general, identify which element owns a
    deviation. The IG must list the alternative explanations whose
    contribution would produce the same reading; the plan must then
    include a partner probe whose path shares some of those elements
    with the first and differs in the one the hypothesis names. The
    Investigator reads `conflates_with` and refuses to declare
    DISPROVEN on a compositional probe alone.
    """
    tool: _InvestigatorTool = Field(
        ..., description="Must be one of the Investigator's registered tools."
    )
    args_hint: str = Field("", description="natural-language arg guidance")
    expected_if_hypothesis_holds: str
    falsifying_observation: str
    conflates_with: list[str] = Field(
        default_factory=list,
        description=(
            "Alternative explanations whose contribution to this "
            "probe's reading is indistinguishable from the "
            "hypothesized cause. Required (non-empty) when the probe's "
            "reading composes contributions from more than one "
            "element. The plan must include a partner probe whose "
            "path differs in the element the hypothesis names so the "
            "comparison localizes. Empty means the probe's reading "
            "uniquely identifies the hypothesized cause."
        ),
    )


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
    """Final NOC-ready diagnosis produced by Synthesis.

    PR 5.5b converted Synthesis from plain-markdown to structured output
    so the candidate-pool membership constraint (Decision E) can be
    enforced mechanically. The orchestrator passes the populated
    DiagnosisReport through `lint_synthesis_pool_membership` and renders
    it back to markdown for the recorder/scorer via
    `_render_diagnosis_report_to_markdown`.

    `primary_suspect_nf` carries the typed root-cause NF. None iff
    `verdict_kind == "inconclusive"`. The pool-membership guardrail
    reads this field to validate Synthesis picked from the candidate
    pool computed in Phase 6.5.

    `verdict_kind` distinguishes the three branches Synthesis can land
    on:
      * `confirmed` — sole NOT_DISPROVEN survivor (Synthesis Case A) OR
        Decision E re-investigation produced NOT_DISPROVEN.
      * `promoted` — diagnosis derived from `alternative_suspects`
        cross-corroboration in an all-DISPROVEN tree (Synthesis Case D).
      * `inconclusive` — empty pool, or evidence too weak to commit.
    """
    summary: str
    root_cause: str
    root_cause_confidence: Literal["high", "medium", "low"]
    primary_suspect_nf: _KnownNF | None = Field(
        default=None,
        description=(
            "The NF Synthesis names as the root cause. MUST appear in "
            "the candidate pool (Decision E) when verdict_kind is "
            "'confirmed' or 'promoted'. None when verdict_kind is "
            "'inconclusive'."
        ),
    )
    verdict_kind: Literal["confirmed", "promoted", "inconclusive"] = Field(
        default="inconclusive",
        description=(
            "Which Synthesis branch the diagnosis came from. Drives "
            "downstream confidence calibration (Decision F) and pool "
            "membership validation (PR 5.5b)."
        ),
    )
    affected_components: list[dict] = Field(default_factory=list)
    timeline: list[str] = Field(default_factory=list)
    recommendation: str
    explanation: str
