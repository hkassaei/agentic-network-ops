"""Tests for the event-trigger DSL evaluator."""

import pytest

from agentic_ops_common.metric_kb.event_dsl import (
    DSLEvaluationError,
    eval_trigger,
    dropped_by,
    increased_by,
    prior_stable,
    rate_of_change,
    no_prior_stable,
    value_at_time_ago,
)
from agentic_ops_common.metric_kb.metric_context import (
    InMemoryMetricContext,
    parse_duration_seconds,
)


# ============================================================================
# Duration parsing
# ============================================================================

def test_parse_duration_seconds():
    assert parse_duration_seconds("30s") == 30
    assert parse_duration_seconds("5m") == 300
    assert parse_duration_seconds("1h") == 3600
    assert parse_duration_seconds("1d") == 86400
    assert parse_duration_seconds("500ms") == 0.5
    assert parse_duration_seconds(60) == 60
    assert parse_duration_seconds("60") == 60


# ============================================================================
# Test-context fixtures
# ============================================================================

def make_stable_ctx(metric="core.amf.ran_ue", value=10.0, history_len=60, step=5.0):
    """Context where metric has been stable at `value` for the window."""
    now = 1000.0
    history = {metric: [(now - i * step, value) for i in range(history_len, 0, -1)]}
    return InMemoryMetricContext(
        metric_id_=metric,
        history=history,
        current_values={metric: value},
        eval_time_=now,
    )


def make_dropped_ctx(metric="core.amf.ran_ue", baseline=10.0, current=2.0,
                    history_len=60, step=5.0):
    """Context where metric was stable at baseline, then dropped to current."""
    now = 1000.0
    # Older points at baseline, recent points at current (last 60s at current)
    history = {metric: []}
    for i in range(history_len, 0, -1):
        t = now - i * step
        v = baseline if t < now - 60 else current
        history[metric].append((t, v))
    return InMemoryMetricContext(
        metric_id_=metric,
        history=history,
        current_values={metric: current},
        eval_time_=now,
    )


# ============================================================================
# Primitive predicate tests
# ============================================================================

def test_dropped_by_detects_drop():
    assert dropped_by(current=2.0, baseline=10.0, fraction=0.2) is True
    assert dropped_by(current=9.0, baseline=10.0, fraction=0.2) is False  # only 10% drop


def test_dropped_by_handles_zero_baseline():
    assert dropped_by(current=0.0, baseline=0.0, fraction=0.2) is False


def test_increased_by_detects_spike():
    assert increased_by(current=20.0, baseline=10.0, fraction=0.5) is True
    assert increased_by(current=11.0, baseline=10.0, fraction=0.5) is False


def test_increased_by_from_zero():
    # Special case: any increase from zero counts
    assert increased_by(current=0.5, baseline=0.0, fraction=0.5) is True


def test_prior_stable_returns_median():
    ctx = make_stable_ctx(value=10.0)
    assert prior_stable(ctx, window="5m") == 10.0


def test_prior_stable_empty_returns_zero():
    ctx = InMemoryMetricContext(
        metric_id_="foo.bar.baz",
        history={"foo.bar.baz": []},
        current_values={"foo.bar.baz": 0.0},
        eval_time_=1000.0,
    )
    assert prior_stable(ctx, window="5m") == 0.0


def test_rate_of_change_on_flat_series():
    ctx = make_stable_ctx(value=10.0)
    assert rate_of_change(ctx, window="5m") == 0.0


def test_rate_of_change_detects_drop():
    ctx = make_dropped_ctx(baseline=10.0, current=2.0, history_len=120)
    r = rate_of_change(ctx, window="5m")
    assert r < 0  # negative rate = dropping


def test_no_prior_stable_true_for_empty():
    ctx = InMemoryMetricContext(
        metric_id_="foo.bar.baz",
        history={"foo.bar.baz": []},
        current_values={"foo.bar.baz": 0.0},
        eval_time_=1000.0,
    )
    assert no_prior_stable(ctx, gt=0) is True


def test_no_prior_stable_false_for_stable_nonzero():
    ctx = make_stable_ctx(value=10.0)
    assert no_prior_stable(ctx, gt=0) is False


def test_value_at_time_ago_finds_point():
    ctx = make_stable_ctx(value=10.0)
    assert value_at_time_ago(ctx, offset="60s") == 10.0


# ============================================================================
# Full trigger expression evaluation
# ============================================================================

def test_simple_comparison_trigger():
    ctx = make_stable_ctx(value=10.0)
    assert eval_trigger("current == 10", ctx) is True
    assert eval_trigger("current > 5", ctx) is True
    assert eval_trigger("current < 5", ctx) is False


def test_current_equals_zero_trigger():
    ctx = InMemoryMetricContext(
        metric_id_="foo.bar.baz",
        history={"foo.bar.baz": [(900.0, 5.0), (1000.0, 0.0)]},
        current_values={"foo.bar.baz": 0.0},
        eval_time_=1000.0,
    )
    assert eval_trigger("current == 0", ctx) is True


def test_dropped_by_expression():
    ctx = make_dropped_ctx(baseline=10.0, current=2.0, history_len=120)
    # Drop from 10 to 2 = 80% drop, > 20% threshold
    expr = "dropped_by(current, prior_stable(window='5m'), 0.2)"
    assert eval_trigger(expr, ctx) is True


def test_compound_trigger_with_phase():
    ctx = make_dropped_ctx(baseline=10.0, current=0.0, history_len=120)
    # Current is zero, prior stable was nonzero, not startup
    expr = (
        "current == 0 and prior_stable(window='5m') > 0 "
        "and not (phase == 'startup')"
    )
    assert eval_trigger(expr, ctx) is True


def test_startup_phase_suppresses_fire():
    ctx = InMemoryMetricContext(
        metric_id_="core.amf.ran_ue",
        history={"core.amf.ran_ue": []},
        current_values={"core.amf.ran_ue": 0.0},
        eval_time_=1000.0,
        phase_="startup",
    )
    expr = "current == 0 and not (phase == 'startup')"
    assert eval_trigger(expr, ctx) is False


def test_related_metric_correlation():
    ctx = InMemoryMetricContext(
        metric_id_="core.amf.ran_ue",
        history={"core.amf.ran_ue": [(900.0, 10.0), (1000.0, 0.0)]},
        current_values={
            "core.amf.ran_ue": 0.0,
            "core.amf.gnb": 0.0,
        },
        eval_time_=1000.0,
    )
    expr = "current == 0 and related('core.amf.gnb') == 0"
    assert eval_trigger(expr, ctx) is True


def test_sustained_gt_triggers_on_consistent_high():
    # Metric sustained above 200 for the whole window
    now = 1000.0
    history = {"ims.icscf.cdp": [(now - i * 5, 500.0) for i in range(60, 0, -1)]}
    ctx = InMemoryMetricContext(
        metric_id_="ims.icscf.cdp",
        history=history,
        current_values={"ims.icscf.cdp": 500.0},
        eval_time_=now,
    )
    expr = "sustained_gt(200, min_duration='60s')"
    assert eval_trigger(expr, ctx) is True


def test_sustained_gt_false_when_recently_dropped():
    now = 1000.0
    # First 55s was above 200, last 5s was below
    history = {
        "ims.icscf.cdp": [
            (now - i * 5, 500.0 if i > 1 else 100.0)
            for i in range(60, 0, -1)
        ]
    }
    ctx = InMemoryMetricContext(
        metric_id_="ims.icscf.cdp",
        history=history,
        current_values={"ims.icscf.cdp": 100.0},
        eval_time_=now,
    )
    expr = "sustained_gt(200, min_duration='60s')"
    assert eval_trigger(expr, ctx) is False


def test_baseline_mean_available():
    ctx = InMemoryMetricContext(
        metric_id_="ims.icscf.cdp",
        history={"ims.icscf.cdp": [(900.0, 50.0), (1000.0, 100.0)]},
        current_values={"ims.icscf.cdp": 100.0},
        eval_time_=1000.0,
        baselines={"ims.icscf.cdp": 50.0},
    )
    assert eval_trigger("current > 1.5 * baseline_mean", ctx) is True


# ============================================================================
# Error paths
# ============================================================================

def test_unknown_function_raises():
    ctx = make_stable_ctx()
    with pytest.raises(DSLEvaluationError, match="Unknown symbol"):
        eval_trigger("nonexistent_function(current)", ctx)


def test_non_bool_result_raises():
    ctx = make_stable_ctx()
    with pytest.raises(DSLEvaluationError, match="must return bool"):
        eval_trigger("current + 1", ctx)


def test_unsafe_expressions_rejected():
    """simpleeval should reject attribute access by default."""
    ctx = make_stable_ctx()
    with pytest.raises(DSLEvaluationError):
        eval_trigger("current.__class__", ctx)
