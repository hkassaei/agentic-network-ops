"""v7-specific structured models.

The NetworkAnalyst, InstructionGenerator, Investigator, and Synthesis
agents all produce structured Pydantic outputs. Defined here in one place
so the orchestrator can parse and pass them between phases.

v7 carries its own copy of v6's models (per the v7 self-containment
rule — see `agentic_ops_v7/__init__.py`) extended with the path-walk
types `Localization` and the `localized` verdict_kind variant. The
underlying HopProber implementations and attribution dataclasses live
in `agentic_ops_common.path_walk`; this module's `Localization` is the
Pydantic-model surface Synthesis embeds in `DiagnosisReport`.

Shared trace models (InvestigationTrace, PhaseTrace, etc.) live in
agentic_ops_common.models; v7 re-exports them here for caller convenience.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

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

    Schema-level requirements:
      - `summary` must be non-empty.
      - `hypotheses` must contain 1–3 entries. The prompt caps at 3
        ("Cap: produce at most 3 hypotheses"); requiring at least 1
        prevents the empty-output failure mode where NA emits a
        hypotheses-less report and downstream stages have nothing to
        investigate.
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
    "get_canonical_flows_through_component",
    "get_active_flows_through_component",
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
    """Outcome of one probe.

    Two outcome fields, intentionally:

    - `compared_to_expected` — the LLM's judgment of evidence direction.
      CONSISTENT supports the hypothesis, CONTRADICTS refutes it,
      AMBIGUOUS means the probe ran but didn't speak to the hypothesis.

    - `outcome` — whether the probe actually produced a signal at all.
      Closed enum: consistent / contradicts / ambiguous /
      tool_unavailable / error. Only `tool_unavailable` and `error` are
      structurally meaningful today (they get filtered out of evidence-
      strength scoring); the other three mirror `compared_to_expected`
      and exist so the field can fully replace it in a follow-up.

    The Investigator prompt teaches the LLM to set
    `outcome="tool_unavailable"` whenever a tool result begins with
    `PROBE_TOOL_UNAVAILABLE:` (the contract from
    `agentic_ops/tools.py::_tool_unavailable`).
    """
    probe_description: str
    tool_call: str = ""                     # what was called
    observation: str = ""                    # what was observed (with [EVIDENCE: ...])
    compared_to_expected: Literal[
        "CONSISTENT", "CONTRADICTS", "AMBIGUOUS"
    ] = "AMBIGUOUS"
    outcome: Literal[
        "consistent", "contradicts", "ambiguous", "tool_unavailable", "error"
    ] = "ambiguous"
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

class RootCause(BaseModel):
    """One contributing root cause in a compound diagnosis.

    Mirror of the primary slot — suspect NF + layer + evidence pointer.
    Populated by the compound-verdict branch when the walker found
    transport-layer faults AND the application-layer pipeline produced
    a strong-evidence hypothesis whose `primary_suspect_nf` differs
    from the walker's primary attributed hop.

    Each entry must cite its evidence source so the
    `lint_compound_additional_causes` guardrail can verify the entry
    against a real artifact in the input bundle. Fabricated entries
    that point at nothing get REJECTed.

    See ADR `multi_fault_orchestration.md`.
    """
    model_config = ConfigDict(extra="forbid")

    primary_suspect_nf: _KnownNF = Field(
        ...,
        description="The NF this root cause implicates.",
    )
    fault_layer: Literal["transport", "application"] = Field(
        ...,
        description=(
            "Which layer of fault this root cause sits in. `transport` "
            "for walker-sourced kernel attributions, `application` for "
            "NA/Investigator-sourced application-layer hypotheses."
        ),
    )
    evidence_source: Literal["path_walk", "investigator", "anomaly_screener"] = Field(
        ...,
        description=(
            "Which artifact in the input bundle backs this entry. "
            "Verified by lint_compound_additional_causes."
        ),
    )
    evidence_summary: str = Field(
        ...,
        description=(
            "Short verbatim or near-verbatim excerpt from the evidence "
            "source. Operator-facing — appears in the rendered diagnosis."
        ),
    )
    confidence: Literal["high", "medium", "low"] = Field(
        ...,
        description="Synthesis's confidence in this contributing cause.",
    )


class AffectedComponent(BaseModel):
    """One entry in a DiagnosisReport's `affected_components` list.

    Strongly typed on purpose. The field was previously an untyped
    `list[dict]`, whose derived JSON schema declared an object with NO
    properties (`{"type": "object", "additionalProperties": true}`).
    Under the Synthesis agent's controlled generation, that gave Gemini
    no field-level constraint, so it routinely emitted an empty element
    `[{}]` (the prompt's prose asked for {name, role} but the schema
    didn't carry those keys). Declaring `name` and `role` as REQUIRED
    properties makes `{}` schema-invalid — controlled generation must
    populate them. This is the root-cause fix for the empty
    affected_components seen on the 5/26 upf_bandwidth_cap and
    mongodb_gone runs.
    """
    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        ...,
        description=(
            "The component this entry implicates — an NF name "
            "(e.g. `mongo`, `pcscf`) or, for a localized verdict, the "
            "walker's attributed hop node."
        ),
    )
    role: Literal["Root Cause", "Secondary", "Symptomatic"] = Field(
        ...,
        description=(
            "This component's role in the diagnosis. `Root Cause` for the "
            "primary (and each additional) root cause; `Secondary` / "
            "`Symptomatic` for downstream-affected NFs."
        ),
    )


class DiagnosisReport(BaseModel):
    """Final NOC-ready diagnosis produced by Synthesis.

    Synthesis emits structured output so the candidate-pool membership
    constraint can be enforced mechanically. The populated
    DiagnosisReport passes through pool-membership validation and is
    rendered back to markdown for the recorder/scorer.

    `primary_suspect_nf` carries the typed root-cause NF. None iff
    `verdict_kind == "inconclusive"`. The pool-membership check
    validates that Synthesis picked from the candidate pool of
    NOT_DISPROVEN suspects.

    `verdict_kind` distinguishes the four branches Synthesis can land
    on:
      * `confirmed` — a sole NOT_DISPROVEN survivor, or a bounded
        re-investigation produced NOT_DISPROVEN.
      * `promoted` — diagnosis derived from `alternative_suspects`
        cross-corroboration in an all-DISPROVEN tree.
      * `inconclusive` — empty pool, or evidence too weak to commit.
      * `localized` — v7 transport-layer-fault branch; path-walk
        produced a hop attribution. See ADR
        `path_anchored_probe_planning_for_transport_layer_faults.md`.
      * `compound` — both transport-layer (walker) AND application-layer
        (NA + Investigators) produced distinct evidence of separate root
        causes. The primary slot carries the most-localized cause
        (typically the walker's earliest attributed hop); the additional
        causes go in `additional_root_causes`. See ADR
        `multi_fault_orchestration.md`.
    """
    summary: str
    root_cause: str
    root_cause_confidence: Literal["high", "medium", "low"]
    primary_suspect_nf: _KnownNF | None = Field(
        default=None,
        description=(
            "The NF Synthesis names as the root cause. MUST appear in "
            "the candidate pool when verdict_kind is 'confirmed' or "
            "'promoted'. None when verdict_kind is 'inconclusive'."
        ),
    )
    verdict_kind: Literal[
        "confirmed", "promoted", "inconclusive", "localized", "compound",
    ] = Field(
        default="inconclusive",
        description=(
            "Which Synthesis branch the diagnosis came from. Drives "
            "downstream confidence calibration and pool membership "
            "validation. `localized` is the v7 transport-layer-fault "
            "branch (path-walk produced a hop attribution). `compound` "
            "is when walker AND application-layer both produced distinct "
            "evidence of separate root causes — see ADR "
            "multi_fault_orchestration.md."
        ),
    )
    affected_components: list[AffectedComponent] = Field(
        default_factory=list,
        description=(
            "Components implicated by this diagnosis, each with a typed "
            "`name` + `role`. Required `name`/`role` properties prevent "
            "the empty-element artifact the old `list[dict]` schema "
            "allowed. For `localized`: a single Root Cause entry naming "
            "the walker's hop node. For `confirmed`/`promoted`: the "
            "primary_suspect_nf as Root Cause plus any "
            "Secondary/Symptomatic NFs. For `compound`: one Root Cause "
            "per root cause plus downstream NFs."
        ),
    )
    timeline: list[str] = Field(default_factory=list)
    recommendation: str
    explanation: str
    localization: "Optional[Localization]" = Field(
        default=None,
        description=(
            "Populated when verdict_kind == 'localized' or 'compound': "
            "the path-walk's hop attribution carrying the verbatim "
            "transport-layer counter evidence for the primary slot. "
            "None for the application-layer verdict_kinds."
        ),
    )
    additional_root_causes: list[RootCause] = Field(
        default_factory=list,
        description=(
            "Populated when verdict_kind == 'compound': non-primary "
            "contributing root causes. Empty for every other verdict_kind. "
            "Verified by lint_compound_additional_causes — each entry's "
            "evidence_source must point at a real artifact in the input "
            "bundle. See ADR multi_fault_orchestration.md."
        ),
    )


# ============================================================================
# Path-walk types — v7's transport-layer pipeline
#
# These are deliberately re-exported / re-defined here (not imported from
# agentic_ops_common.path_walk) ONLY for the Pydantic-model surface that
# Synthesis needs in DiagnosisReport.localization. The walker, probers,
# and HopAttribution variants live in agentic_ops_common.path_walk and
# are imported via the tools façade — those imports are allowed because
# agentic_ops_common is shared infrastructure (see v7 self-containment
# rule in __init__.py).
# ============================================================================


class Localization(BaseModel):
    """The path-walk's structured attribution.

    Synthesis populates this on the `localized` verdict_kind. The fields
    mirror agentic_ops_common.path_walk.HopRecord but as a Pydantic
    model so it serializes cleanly into the DiagnosisReport.
    """
    hop_node: str = Field(
        ...,
        description="Container/switch/gateway name where the fault was localized.",
    )
    hop_kind: str = Field(
        ...,
        description="Hop kind: container | docker_bridge | l2_switch | etc.",
    )
    hop_iface: str = Field(
        ...,
        description="Interface or port at the hop where the fault counter advanced.",
    )
    attribution_kind: Literal[
        "drops_attributed_here",
        "drops_attributed_to_inbound_link",
        "latency_at_hop",
        "container_dead",
    ] = Field(
        ...,
        description="Which HopAttribution variant the walker produced.",
    )
    counter_kind: str = Field(
        default="",
        description=(
            "Native-telemetry counter that surfaced the fault: "
            "qdisc_netem | qdisc_tbf | iface_dropped | iface_error | "
            "iptables_drop | conntrack_drop | switch_discard | "
            "ipsec_replay | optical_ber | ..."
        ),
    )
    dropped_pkts: int = Field(
        default=0,
        description="Packets the kernel/element reported dropped at this hop.",
    )
    dropped_pct: float | None = Field(
        default=None,
        description="Drop fraction when computable; None when no denominator.",
    )
    observed_delay_ms: float | None = Field(
        default=None,
        description="Authored or measured delay for latency_at_hop; None otherwise.",
    )
    evidence: str = Field(
        ...,
        description=(
            "Verbatim transport-layer counter excerpt — the kernel's or "
            "network element's own words, kept intact so the operator "
            "can verify the attribution against the source of truth."
        ),
    )
