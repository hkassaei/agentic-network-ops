"""
Data models for the v5 deterministic backbone investigation system.

Phase outputs:
  Phase 0   → TriageReport (raw radiograph)
  Phase 0.5 → OntologyDiagnosis + InvestigationPlan (deterministic, no LLM)
  Phase 1   → InvestigationResult (unified investigator finding)
  Phase 2   → Diagnosis (final, backward-compatible with v1/GUI)

Observability:
  InvestigationTrace → per-phase token/timing breakdown
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


# -------------------------------------------------------------------------
# Phase 0: Triage (same as v4 — data collection)
# -------------------------------------------------------------------------

class TriageReport(BaseModel):
    stack_phase: str
    data_plane_status: str
    control_plane_status: str
    ims_status: str
    anomalies: list[str] = Field(default_factory=list)
    metrics_summary: dict = Field(default_factory=dict)


# -------------------------------------------------------------------------
# Phase 1 (v5 redesign): NetworkAnalystAgent output
# -------------------------------------------------------------------------

class LayerRating(str, Enum):
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"


class LayerStatus(BaseModel):
    """Health status for one network layer."""
    rating: LayerRating = Field(
        description="GREEN (healthy), YELLOW (degraded), or RED (failed)")
    evidence: list[str] = Field(
        default_factory=list,
        description=(
            "Specific metric values, log excerpts, or tool outputs backing "
            "this rating. REQUIRED when rating is YELLOW or RED."
        ),
    )
    note: str = Field(
        default="",
        description="One-line human-readable summary of the layer's state")


class SuspectComponent(BaseModel):
    """A component flagged for deeper investigation."""
    name: str = Field(
        description="Container name, e.g. 'amf', 'upf', 'pcscf', 'nr_gnb'")
    confidence: str = Field(
        description="Suspicion level: 'low', 'medium', or 'high'")
    reason: str = Field(
        description=(
            "Why this component is suspect, with specific evidence "
            "(metric values, log lines, tool outputs)"
        ),
    )


class NetworkAnalysis(BaseModel):
    """Structured assessment produced by the NetworkAnalystAgent (Phase 1).

    Merges the former TriageAgent (data collection) and AnomalyDetectorAgent
    (ontology-guided analysis) into a single agent that must:
      1. Collect data via mandatory tool calls
      2. Compare against ontology baselines
      3. Rate each layer with evidence
      4. Identify suspect components and direct the investigation
    """
    summary: str = Field(
        description="One-sentence overview of overall network health")
    layer_status: dict[str, LayerStatus] = Field(
        description=(
            "Health rating per layer. Keys MUST be: 'infrastructure', "
            "'ran', 'core', 'ims'. Every layer MUST be rated."
        ),
    )
    suspect_components: list[SuspectComponent] = Field(
        default_factory=list,
        description=(
            "Components flagged for deeper investigation. Empty list if "
            "all layers are GREEN."
        ),
    )
    investigation_hint: str = Field(
        description=(
            "Directional hint for the Investigator about where to look "
            "and what to prioritize. 1-3 sentences."
        ),
    )
    tools_called: list[str] = Field(
        default_factory=list,
        description="Names of tools actually invoked during this assessment")


# -------------------------------------------------------------------------
# Phase 2: Final Diagnosis (backward-compatible with v1/GUI)
# -------------------------------------------------------------------------

class TimelineEvent(BaseModel):
    timestamp: str
    container: str
    event: str


class Diagnosis(BaseModel):
    summary: str
    timeline: list[TimelineEvent] = Field(default_factory=list)
    root_cause: str
    affected_components: list[str] = Field(default_factory=list)
    recommendation: str
    confidence: str = "low"
    explanation: str = ""


# -------------------------------------------------------------------------
# Investigation Trace (observability)
# -------------------------------------------------------------------------

# Trace models moved to agentic_ops_common.models.trace (Phase 0 refactor).
# Re-exported here for backward compatibility with v5 callers.
from agentic_ops_common.models.trace import (  # noqa: F401,E402
    TokenBreakdown,
    ToolCallTrace,
    PhaseTrace,
    InvestigationTrace,
)
