"""Metric Knowledge Base — structured semantic reference for raw NF metrics.

Purpose: agents reason about metric semantics, relationships, and event triggers
via a queryable knowledge base. Replaces/extends baselines.yaml.

See: docs/ADR/metric_knowledge_base_schema.md
"""

from .models import (
    MetricEntry,
    MetricsKB,
    NFBlock,
    Meaning,
    Healthy,
    StateCategory,
    EventTrigger,
    CorrelationHint,
    RelatedMetric,
    Disambiguator,
    Probing,
    Plane,
    Layer,
    MetricType,
    Source,
    RelationshipType,
)
from .loader import load_kb, validate_cross_references, KBLoadError
from .evaluator import evaluate, EvaluationContext, MetricSnapshot
from .event_store import EventStore, FiredEvent
from .feature_mapping import map_preprocessor_key_to_kb, NF_LAYER
from .flag_enrichment import enrich_report as enrich_anomaly_report

__all__ = [
    "MetricEntry",
    "MetricsKB",
    "NFBlock",
    "Meaning",
    "Healthy",
    "StateCategory",
    "EventTrigger",
    "CorrelationHint",
    "RelatedMetric",
    "Disambiguator",
    "Probing",
    "Plane",
    "Layer",
    "MetricType",
    "Source",
    "RelationshipType",
    "load_kb",
    "validate_cross_references",
    "KBLoadError",
    "evaluate",
    "EvaluationContext",
    "MetricSnapshot",
    "EventStore",
    "FiredEvent",
    "map_preprocessor_key_to_kb",
    "NF_LAYER",
    "enrich_anomaly_report",
]
