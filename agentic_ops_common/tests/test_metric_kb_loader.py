"""Tests for the metric KB pydantic loader and cross-reference validator."""

import textwrap
from pathlib import Path

import pytest
import yaml

from agentic_ops_common.metric_kb import (
    EventTrigger,
    KBLoadError,
    Layer,
    MetricEntry,
    MetricsKB,
    Plane,
    RelationshipType,
    Source,
    MetricType,
    load_kb,
    validate_cross_references,
)


# ============================================================================
# Minimal valid KB content
# ============================================================================

VALID_MIN_YAML = textwrap.dedent("""
    metrics:
      amf:
        layer: core
        metrics:
          ran_ue:
            source: prometheus
            type: gauge
            unit: count
            plane: control
            description: "Count of RAN-attached UEs."
            healthy:
              scale_independent: false
              invariant: "Equals configured UE pool size in healthy steady state."
""")


def _write_yaml(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "metrics.yaml"
    p.write_text(content)
    return p


# ============================================================================
# Load success
# ============================================================================

def test_load_minimal_valid_kb(tmp_path: Path):
    p = _write_yaml(tmp_path, VALID_MIN_YAML)
    kb = load_kb(p)

    assert "amf" in kb.metrics
    assert kb.metrics["amf"].layer is Layer.CORE
    assert "ran_ue" in kb.metrics["amf"].metrics
    entry = kb.metrics["amf"].metrics["ran_ue"]
    assert entry.type is MetricType.GAUGE
    assert entry.plane is Plane.CONTROL
    assert entry.healthy.scale_independent is False


def test_get_metric_by_fully_qualified_key(tmp_path: Path):
    p = _write_yaml(tmp_path, VALID_MIN_YAML)
    kb = load_kb(p)
    entry = kb.get_metric("core.amf.ran_ue")
    assert entry is not None
    assert entry.type is MetricType.GAUGE


def test_get_metric_by_shortform(tmp_path: Path):
    p = _write_yaml(tmp_path, VALID_MIN_YAML)
    kb = load_kb(p)
    entry = kb.get_metric("amf.ran_ue")
    assert entry is not None


def test_get_metric_missing_returns_none(tmp_path: Path):
    p = _write_yaml(tmp_path, VALID_MIN_YAML)
    kb = load_kb(p)
    assert kb.get_metric("core.amf.nonexistent") is None


def test_all_metric_keys(tmp_path: Path):
    p = _write_yaml(tmp_path, VALID_MIN_YAML)
    kb = load_kb(p)
    assert kb.all_metric_keys() == {"core.amf.ran_ue"}


# ============================================================================
# Validation failures
# ============================================================================

def test_missing_file_raises(tmp_path: Path):
    with pytest.raises(KBLoadError, match="not found"):
        load_kb(tmp_path / "does_not_exist.yaml")


def test_invalid_yaml_raises(tmp_path: Path):
    p = _write_yaml(tmp_path, "metrics:\n  amf:\n    layer: [unclosed")
    with pytest.raises(KBLoadError, match="YAML parse error"):
        load_kb(p)


def test_invalid_layer_rejected(tmp_path: Path):
    p = _write_yaml(tmp_path, textwrap.dedent("""
        metrics:
          amf:
            layer: not_a_real_layer
            metrics: {}
    """))
    with pytest.raises(KBLoadError, match="validation failed"):
        load_kb(p)


def test_invalid_plane_rejected(tmp_path: Path):
    p = _write_yaml(tmp_path, textwrap.dedent("""
        metrics:
          amf:
            layer: core
            metrics:
              ran_ue:
                source: prometheus
                type: gauge
                plane: wrong_value
                description: "X"
                healthy:
                  scale_independent: true
    """))
    with pytest.raises(KBLoadError, match="validation failed"):
        load_kb(p)


def test_scale_dependent_without_invariant_rejected(tmp_path: Path):
    p = _write_yaml(tmp_path, textwrap.dedent("""
        metrics:
          amf:
            layer: core
            metrics:
              ran_ue:
                source: prometheus
                type: gauge
                description: "X"
                healthy:
                  scale_independent: false
    """))
    with pytest.raises(KBLoadError, match="invariant is required"):
        load_kb(p)


def test_scale_independent_works_without_invariant(tmp_path: Path):
    p = _write_yaml(tmp_path, textwrap.dedent("""
        metrics:
          icscf:
            layer: ims
            metrics:
              cdp_latency:
                source: kamcmd
                type: gauge
                description: "X"
                healthy:
                  scale_independent: true
                  typical_range: [30, 100]
    """))
    kb = load_kb(p)
    assert kb.metrics["icscf"].metrics["cdp_latency"].healthy.scale_independent


def test_event_id_must_follow_namespace(tmp_path: Path):
    p = _write_yaml(tmp_path, textwrap.dedent("""
        metrics:
          amf:
            layer: core
            metrics:
              ran_ue:
                source: prometheus
                type: gauge
                description: "X"
                healthy:
                  scale_independent: true
                event_triggers:
                  - id: bad_flat_id
                    trigger: "current == 0"
                    local_meaning: "X"
    """))
    with pytest.raises(KBLoadError, match="namespace"):
        load_kb(p)


def test_event_id_invalid_layer_rejected(tmp_path: Path):
    p = _write_yaml(tmp_path, textwrap.dedent("""
        metrics:
          amf:
            layer: core
            metrics:
              ran_ue:
                source: prometheus
                type: gauge
                description: "X"
                healthy:
                  scale_independent: true
                event_triggers:
                  - id: WRONG_LAYER.amf.some_event
                    trigger: "current == 0"
                    local_meaning: "X"
    """))
    with pytest.raises(KBLoadError, match="invalid layer"):
        load_kb(p)


def test_unknown_field_rejected(tmp_path: Path):
    p = _write_yaml(tmp_path, textwrap.dedent("""
        metrics:
          amf:
            layer: core
            metrics:
              ran_ue:
                source: prometheus
                type: gauge
                description: "X"
                healthy:
                  scale_independent: true
                bogus_field: 42
    """))
    with pytest.raises(KBLoadError, match="validation failed"):
        load_kb(p)


def test_invalid_relationship_enum_rejected(tmp_path: Path):
    p = _write_yaml(tmp_path, textwrap.dedent("""
        metrics:
          amf:
            layer: core
            metrics:
              ran_ue:
                source: prometheus
                type: gauge
                description: "X"
                healthy:
                  scale_independent: true
                related_metrics:
                  - metric: core.amf.other
                    relationship: not_a_real_relationship
    """))
    with pytest.raises(KBLoadError, match="validation failed"):
        load_kb(p)


# ============================================================================
# Cross-reference validation
# ============================================================================

def test_dangling_composite_of_caught(tmp_path: Path):
    p = _write_yaml(tmp_path, textwrap.dedent("""
        metrics:
          amf:
            layer: core
            metrics:
              ran_ue:
                source: prometheus
                type: gauge
                description: "X"
                healthy:
                  scale_independent: true
                composite_of:
                  - core.amf.does_not_exist
    """))
    with pytest.raises(KBLoadError, match="composite_of references unknown"):
        load_kb(p)


def test_dangling_related_metric_caught(tmp_path: Path):
    p = _write_yaml(tmp_path, textwrap.dedent("""
        metrics:
          amf:
            layer: core
            metrics:
              ran_ue:
                source: prometheus
                type: gauge
                description: "X"
                healthy:
                  scale_independent: true
                related_metrics:
                  - metric: core.amf.does_not_exist
                    relationship: correlated_with
    """))
    with pytest.raises(KBLoadError, match="related_metrics references unknown"):
        load_kb(p)


def test_computed_expression_skipped_in_refs(tmp_path: Path):
    p = _write_yaml(tmp_path, textwrap.dedent("""
        metrics:
          amf:
            layer: core
            metrics:
              ran_ue:
                source: prometheus
                type: gauge
                description: "X"
                healthy:
                  scale_independent: true
                disambiguators:
                  - metric: "sum(ims.icscf.uar, ims.scscf.mar)"
                    separates: "X vs Y"
    """))
    # Should not raise — the computed expression is recognized and skipped
    kb = load_kb(p)
    assert kb is not None


def test_full_valid_kb_with_refs(tmp_path: Path):
    p = _write_yaml(tmp_path, textwrap.dedent("""
        metrics:
          amf:
            layer: core
            metrics:
              ran_ue:
                source: prometheus
                type: gauge
                unit: count
                plane: control
                description: "Count of RAN-attached UEs."
                meaning:
                  what_it_signals: "Direct RAN health indicator."
                  drop: "UEs losing attachment."
                  zero: "Total RAN failure."
                healthy:
                  scale_independent: false
                  invariant: "Equals configured UE pool size."
                event_triggers:
                  - id: core.amf.ran_ue_sudden_drop
                    trigger: "dropped_by(current, prior_stable(window='5m'), 0.2)"
                    local_meaning: "Sharp decrease in attached UEs."
                    magnitude_captured: [current_value, prior_stable_value]
                    correlates_with:
                      - event_id: core.amf.gnb_association_drop
                        composite_interpretation: "RAN failure"
                related_metrics:
                  - metric: core.amf.gnb
                    relationship: discriminator_for
                    use: "Distinguishes RAN vs AMF-side fault."
                disambiguators:
                  - metric: core.amf.gnb
                    separates: "RAN failure vs AMF attach issue."
              gnb:
                source: prometheus
                type: gauge
                description: "Count of connected gNBs."
                healthy:
                  scale_independent: false
                  invariant: "Equals configured gNB count."
    """))
    kb = load_kb(p)
    assert len(kb.metrics) == 1  # amf
    assert len(kb.metrics["amf"].metrics) == 2  # ran_ue, gnb
    assert kb.all_event_ids() == {"core.amf.ran_ue_sudden_drop"}
