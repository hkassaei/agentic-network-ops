"""Pydantic v2 models for the metric knowledge base.

Mirrors the YAML structure defined in docs/ADR/metric_knowledge_base_schema.md.
Loaders produce typed objects; validation runs at load time.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ============================================================================
# Enums
# ============================================================================

class Layer(str, Enum):
    """Where in the network hierarchy the NF sits.

    Must match components.yaml classification.
    """
    INFRASTRUCTURE = "infrastructure"
    RAN = "ran"
    CORE = "core"
    IMS = "ims"


class Plane(str, Enum):
    """What kind of traffic the METRIC (not the NF) reflects."""
    CONTROL = "control"
    USER = "user"
    MEDIA = "media"


class MetricType(str, Enum):
    GAUGE = "gauge"
    COUNTER = "counter"
    RATIO = "ratio"
    DERIVED = "derived"


class Source(str, Enum):
    PROMETHEUS = "prometheus"
    KAMCMD = "kamcmd"
    RTPENGINE_CTL = "rtpengine_ctl"
    MONGOSH = "mongosh"
    API = "api"
    DERIVED = "derived"


class RelationshipType(str, Enum):
    """Formal enum of relationship types (see ADR)."""
    COMPOSITE_OF = "composite_of"
    DERIVED_FROM = "derived_from"
    NORMALIZED_FROM = "normalized_from"
    CORRELATED_WITH = "correlated_with"
    DISCRIMINATOR_FOR = "discriminator_for"
    UPSTREAM_OF = "upstream_of"
    DOWNSTREAM_OF = "downstream_of"
    PEER_OF = "peer_of"


# ============================================================================
# Sub-blocks
# ============================================================================

class Meaning(BaseModel):
    """Interpretation of what the metric signals about its NF's responsibility."""
    model_config = ConfigDict(extra="forbid")

    what_it_signals: str = Field(..., description="3-5 sentences on semantic meaning")
    spike: Optional[str] = None
    drop: Optional[str] = None
    zero: Optional[str] = None
    steady_non_zero: Optional[str] = None


class Healthy(BaseModel):
    """Healthy expectations for this metric."""
    model_config = ConfigDict(extra="forbid")

    scale_independent: bool
    typical_range: Optional[tuple[float, float]] = None
    invariant: Optional[str] = None
    pre_existing_noise: Optional[str] = None

    @model_validator(mode="after")
    def _check_invariant(self) -> "Healthy":
        # scale_independent=False requires invariant
        # scale_independent=True: invariant optional (metric has no invariant because it's scale-free)
        if not self.scale_independent and not self.invariant:
            raise ValueError(
                "Healthy.invariant is required when scale_independent=False"
            )
        return self


class StateCategory(BaseModel):
    """Observation band (e.g., MOS tiers). Not severity."""
    model_config = ConfigDict(extra="forbid")

    name: str
    condition: str
    meaning: Optional[str] = None


class CorrelationHint(BaseModel):
    """Hint to the correlation engine about related events."""
    model_config = ConfigDict(extra="forbid")

    event_id: str
    composite_interpretation: str


class EventTrigger(BaseModel):
    """A condition that emits a structured event when satisfied.

    NOT an alarm. The correlation engine decides alarm severity with full
    operational context. The trigger only declares "this state transition
    occurred."
    """
    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., description="Globally unique: <layer>.<nf>.<event_name>")
    trigger: str = Field(..., description="Python-expression DSL string")
    clear_condition: Optional[str] = None
    persistence: Optional[str] = None  # e.g., "60s"
    local_meaning: str
    magnitude_captured: list[str] = Field(default_factory=list)
    correlates_with: list[CorrelationHint] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def _id_namespace(cls, v: str) -> str:
        parts = v.split(".")
        if len(parts) < 3:
            raise ValueError(
                f"Event id '{v}' must follow <layer>.<nf>.<event_name> namespace"
            )
        layer = parts[0]
        valid_layers = {"infrastructure", "ran", "core", "ims"}
        if layer not in valid_layers:
            raise ValueError(
                f"Event id '{v}' has invalid layer '{layer}'; "
                f"must be one of {sorted(valid_layers)}"
            )
        return v


class RelatedMetric(BaseModel):
    """A related metric with typed relationship."""
    model_config = ConfigDict(extra="forbid")

    metric: str
    relationship: RelationshipType
    use: Optional[str] = None


class Disambiguator(BaseModel):
    """A metric to check to discriminate between candidate hypotheses."""
    model_config = ConfigDict(extra="forbid")

    metric: str
    separates: str = Field(..., description="What hypotheses this discriminates")


class Probing(BaseModel):
    """How to verify the metric's state with agent tools."""
    model_config = ConfigDict(extra="forbid")

    tool: str
    args_hint: Optional[str] = None


# ============================================================================
# Metric entry
# ============================================================================

class MetricEntry(BaseModel):
    """A single metric entry in the KB."""
    model_config = ConfigDict(extra="forbid")

    # --- Identity ---
    display_name: Optional[str] = None
    source: Source
    type: MetricType
    unit: Optional[str] = None
    protocol: Optional[str] = None
    interface: Optional[str] = None
    plane: Optional[Plane] = None

    # --- Semantics ---
    description: str
    meaning: Optional[Meaning] = None

    # --- Healthy expectations ---
    healthy: Healthy

    # --- State categories ---
    state_categories: list[StateCategory] = Field(default_factory=list)

    # --- Event triggers ---
    event_triggers: list[EventTrigger] = Field(default_factory=list)

    # --- Relationships ---
    related_metrics: list[RelatedMetric] = Field(default_factory=list)
    composite_of: list[str] = Field(default_factory=list)
    feeds_model_features: list[str] = Field(default_factory=list)

    # --- Raw source names ---
    # Prometheus/kamcmd/RTPEngine raw names that feed this KB entry (or
    # whose diagnostic reading IS this KB entry). Populate when the KB
    # metric is a *derived* / *per-UE* / *rate* form of a raw counter —
    # so agent-facing tools can annotate raw counter values by pointing
    # at the correct derived KB entry, preventing misreads.
    raw_sources: list[str] = Field(default_factory=list)

    # --- Disambiguators ---
    disambiguators: list[Disambiguator] = Field(default_factory=list)

    # --- Probing ---
    how_to_verify_live: Optional[Probing] = None

    # --- Metadata ---
    applicable_use_cases: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    deprecated: bool = False


class NFBlock(BaseModel):
    """Metrics grouped under one NF (the NF owns them semantically)."""
    model_config = ConfigDict(extra="forbid")

    layer: Layer
    metrics: dict[str, MetricEntry]


class MetricsKB(BaseModel):
    """Root of the metric knowledge base."""
    model_config = ConfigDict(extra="forbid")

    metrics: dict[str, NFBlock]

    def get_metric(self, metric_id: str) -> Optional[MetricEntry]:
        """Look up a metric by its fully-qualified id `<layer>.<nf>.<metric>`.

        Supports `<nf>.<metric>` too (less strict) by scanning all NFs.
        """
        parts = metric_id.split(".")
        if len(parts) == 3:
            layer, nf, metric = parts
            nf_block = self.metrics.get(nf)
            if nf_block and nf_block.layer.value == layer:
                return nf_block.metrics.get(metric)
            return None
        elif len(parts) == 2:
            nf, metric = parts
            nf_block = self.metrics.get(nf)
            if nf_block:
                return nf_block.metrics.get(metric)
            return None
        return None

    def all_event_ids(self) -> set[str]:
        """Collect every declared event id across all metrics."""
        ids: set[str] = set()
        for nf_block in self.metrics.values():
            for metric in nf_block.metrics.values():
                for trigger in metric.event_triggers:
                    ids.add(trigger.id)
        return ids

    def all_metric_keys(self) -> set[str]:
        """Collect every fully-qualified metric key `<layer>.<nf>.<metric>`."""
        keys: set[str] = set()
        for nf_name, nf_block in self.metrics.items():
            for metric_name in nf_block.metrics.keys():
                keys.add(f"{nf_block.layer.value}.{nf_name}.{metric_name}")
        return keys
