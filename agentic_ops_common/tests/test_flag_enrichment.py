"""Tests for KB-based enrichment of anomaly-screener flags.

Each test creates a tiny in-memory AnomalyReport with a synthetic flag,
runs `enrich_report` against the real project KB, and verifies the flag
picks up the expected semantic fields.
"""

from __future__ import annotations

import pytest

from agentic_ops_common.anomaly.screener import (
    AnomalyFlag,
    AnomalyReport,
    FlagKBContext,
)
from agentic_ops_common.metric_kb import (
    enrich_anomaly_report,
    load_kb,
)


@pytest.fixture(scope="module")
def kb():
    return load_kb()


def _report_with(flag: AnomalyFlag) -> AnomalyReport:
    return AnomalyReport(flags=[flag], overall_score=0.9, model_ready=True)


def test_derived_pcscf_avg_register_time_ms_enriched(kb):
    """A flagged `derived.pcscf_avg_register_time_ms` should get KB context."""
    flag = AnomalyFlag(
        metric="pcscf_avg_register_time_ms",
        component="derived",
        current=0.0,
        learned_normal=248.0,
        anomaly_score=7.5,
        severity="HIGH",
        direction="drop",
    )
    report = _report_with(flag)
    enrich_anomaly_report(report, kb)

    ctx = report.flags[0].kb_context
    assert isinstance(ctx, FlagKBContext)
    assert ctx.kb_metric_id == "ims.pcscf.avg_register_time_ms"
    assert ctx.unit == "ms"
    assert ctx.what_it_signals  # non-empty
    # Healthy typical range should load
    assert ctx.typical_range == (150.0, 350.0)


def test_flag_with_unknown_metric_gets_no_context(kb):
    flag = AnomalyFlag(
        metric="totally_fake_metric",
        component="nonexistent",
        current=1.0,
        learned_normal=0.0,
        anomaly_score=5.0,
        severity="HIGH",
        direction="spike",
    )
    report = _report_with(flag)
    enrich_anomaly_report(report, kb)
    assert report.flags[0].kb_context is None


def test_drop_direction_prefers_zero_meaning_when_available(kb):
    """If KB has `meaning.zero`, a `drop` flag picks that reading up."""
    flag = AnomalyFlag(
        metric="pcscf_avg_register_time_ms",
        component="derived",
        current=0.0,
        learned_normal=248.0,
        anomaly_score=7.5,
        severity="HIGH",
        direction="drop",
    )
    report = _report_with(flag)
    enrich_anomaly_report(report, kb)
    ctx = report.flags[0].kb_context
    assert ctx is not None
    # The metric defines meaning.zero — that should win over meaning.drop.
    entry = kb.get_metric("ims.pcscf.avg_register_time_ms")
    assert ctx.direction_meaning == entry.meaning.zero


def test_prompt_text_renders_kb_context(kb):
    flag = AnomalyFlag(
        metric="pcscf_avg_register_time_ms",
        component="derived",
        current=0.0,
        learned_normal=248.0,
        anomaly_score=7.5,
        severity="HIGH",
        direction="drop",
    )
    report = _report_with(flag)
    enrich_anomaly_report(report, kb)
    text = report.to_prompt_text()
    # Semantic lines must show up, not just a numeric table row.
    assert "What it measures" in text
    # Healthy range should render with the KB numbers.
    assert "Healthy typical range" in text
    # Units on the numeric values.
    assert "ms" in text


def test_prompt_text_no_kb_context_falls_back(kb):
    flag = AnomalyFlag(
        metric="unknown_metric",
        component="derived",
        current=1.0,
        learned_normal=0.0,
        anomaly_score=3.0,
        severity="MEDIUM",
        direction="spike",
    )
    report = _report_with(flag)
    enrich_anomaly_report(report, kb)  # leaves kb_context None
    text = report.to_prompt_text()
    # Falls back to the "interpret from the metric name" advisory.
    assert "No KB context available" in text


def test_to_dict_list_carries_kb_context(kb):
    flag = AnomalyFlag(
        metric="pcscf_avg_register_time_ms",
        component="derived",
        current=0.0,
        learned_normal=248.0,
        anomaly_score=7.5,
        severity="HIGH",
        direction="drop",
    )
    report = _report_with(flag)
    enrich_anomaly_report(report, kb)
    dicts = report.to_dict_list()
    assert "kb_context" in dicts[0]
    kc = dicts[0]["kb_context"]
    assert kc["kb_metric_id"] == "ims.pcscf.avg_register_time_ms"
    assert kc["typical_range"] == [150.0, 350.0]
