"""Event-trigger DSL — simpleeval-based expression evaluator.

Trigger strings in YAML are Python-expression syntax evaluated against a
bound MetricContext. Predicate functions are registered with simpleeval and
receive the context via a closure when the evaluator is constructed.

See: docs/ADR/metric_knowledge_base_schema.md (Event-trigger DSL and storage)

Registered predicates:
  Current-value predicates are native Python operators: ==, !=, >, <, >=, <=.

  Temporal:
    prior_stable(window='5m') -> float
    value_at_time_ago(offset='60s') -> float | None
    dropped_by(current, baseline, fraction) -> bool
    increased_by(current, baseline, fraction) -> bool
    sustained(predicate_result, min_duration='60s') -> bool
    persistence(min_duration='60s') -> bool  # shorthand for the full trigger
    rate_of_change(window='5m') -> float
    no_prior_stable(gt=0) -> bool

  Correlation:
    related(metric_id) -> float | None

  Identity (always available in namespace):
    current  — float, current value
    phase    — str, lifecycle phase
    baseline_mean — float or None
"""

from __future__ import annotations

import logging
import statistics
from typing import Callable, Optional

from simpleeval import EvalWithCompoundTypes, FunctionNotDefined, NameNotDefined

from .metric_context import MetricContext, parse_duration_seconds

log = logging.getLogger("metric_kb.event_dsl")


class DSLEvaluationError(Exception):
    """Raised when a trigger expression fails to evaluate."""


# ----------------------------------------------------------------------------
# Predicate implementations (pure functions of MetricContext)
# ----------------------------------------------------------------------------

def _filter_stable(series: list[tuple[float, float]]) -> list[float]:
    """Identify the 'stable' subset of a series.

    Simple heuristic: if median and mean are within 20% of each other, the
    series is already stable — return all values. Otherwise, return only
    values within 1 std of the median (rejecting outliers).

    This is used by prior_stable to avoid being thrown off by a single
    anomalous point at the start of the window.
    """
    if not series:
        return []
    values = [v for _, v in series]
    if len(values) <= 2:
        return values
    med = statistics.median(values)
    mean = statistics.mean(values)
    if med == 0:
        return values
    if abs(mean - med) / abs(med) < 0.2:
        return values
    std = statistics.pstdev(values)
    if std == 0:
        return values
    return [v for v in values if abs(v - med) <= std]


def prior_stable(ctx: MetricContext, window: str = "5m") -> float:
    """Median of the metric's stable values during the last window.

    Returns 0.0 if the window is empty (caller should guard with
    no_prior_stable if zero would be meaningful).
    """
    w = parse_duration_seconds(window)
    series = ctx.get_history(w)
    stable = _filter_stable(series)
    if not stable:
        return 0.0
    return statistics.median(stable)


def value_at_time_ago(ctx: MetricContext, offset: str = "60s") -> Optional[float]:
    """Metric value at (eval_time - offset), or None if not in history."""
    o = parse_duration_seconds(offset)
    target = ctx.eval_time - o
    series = ctx.get_history(o + 30)  # a bit of slack for sampling jitter
    if not series:
        return None
    # Find the closest point
    closest = min(series, key=lambda tv: abs(tv[0] - target))
    if abs(closest[0] - target) > 30:
        return None
    return closest[1]


def dropped_by(current: float, baseline: float, fraction: float) -> bool:
    """True if current is MORE than `fraction` below baseline."""
    if baseline <= 0:
        return False
    return (baseline - current) / baseline > fraction


def increased_by(current: float, baseline: float, fraction: float) -> bool:
    """True if current is MORE than `fraction` above baseline."""
    if baseline <= 0:
        return current > 0  # any increase from zero counts
    return (current - baseline) / baseline > fraction


def sustained(
    ctx: MetricContext,
    predicate_fn: Callable[[float], bool],
    min_duration: str = "60s",
) -> bool:
    """True if `predicate_fn(value)` has been true throughout the last
    min_duration seconds of history.
    """
    w = parse_duration_seconds(min_duration)
    series = ctx.get_history(w)
    if not series:
        return False
    # Require the series to span at least min_duration (approximately)
    span = series[-1][0] - series[0][0]
    if span < w * 0.8:
        return False  # insufficient history to confirm
    return all(predicate_fn(v) for _, v in series)


def persistence(ctx: MetricContext, min_duration: str = "60s") -> bool:
    """Convenience: the WHOLE trigger expression must have held true for
    min_duration. Implemented as a flag; the evaluator populates it.

    In practice, the trigger evaluator runs the expression over successive
    evaluations and tracks state persistence externally. This function
    exists primarily for expression authoring clarity; in Phase 1's
    stateless evaluation model, it returns True (persistence is enforced
    at the evaluator layer via the EventTrigger.persistence YAML field,
    not in-expression).
    """
    # In the stateless Phase 1 model, persistence is enforced at the
    # evaluator layer (by refusing to fire events until the trigger has
    # been true for N consecutive evaluations). This function is a no-op
    # placeholder that always returns True so expressions can reference
    # it for readability.
    return True


def rate_of_change(ctx: MetricContext, window: str = "5m") -> float:
    """First derivative of the metric over the window.

    Returns (last_value - first_value) / window_seconds, i.e., average rate.
    Zero if window is empty.
    """
    w = parse_duration_seconds(window)
    series = ctx.get_history(w)
    if len(series) < 2:
        return 0.0
    dt = series[-1][0] - series[0][0]
    if dt <= 0:
        return 0.0
    return (series[-1][1] - series[0][1]) / dt


def no_prior_stable(ctx: MetricContext, gt: float = 0.0, window: str = "30m") -> bool:
    """True if the metric has NEVER had a stable value greater than `gt`
    within the given window. Use to guard against false fires during
    startup or never-deployed states.
    """
    w = parse_duration_seconds(window)
    series = ctx.get_history(w)
    if not series:
        return True
    stable = _filter_stable(series)
    if not stable:
        return True
    med = statistics.median(stable)
    return med <= gt


# ----------------------------------------------------------------------------
# Evaluator
# ----------------------------------------------------------------------------

def make_evaluator(ctx: MetricContext) -> EvalWithCompoundTypes:
    """Build a simpleeval evaluator bound to the given MetricContext.

    Registers all predicates + identity values. Use `eval_trigger(expr, ctx)`
    for one-shot evaluation.
    """
    baseline = ctx.baseline_mean()
    names = {
        "current": ctx.current,
        "phase": ctx.phase,
        "baseline_mean": baseline if baseline is not None else float("nan"),
    }
    # Functions — closures over ctx where needed
    functions = {
        "prior_stable": lambda window="5m": prior_stable(ctx, window),
        "value_at_time_ago": lambda offset="60s": value_at_time_ago(ctx, offset),
        "dropped_by": dropped_by,
        "increased_by": increased_by,
        # sustained + persistence need the full bound evaluator; see below
        "rate_of_change": lambda window="5m": rate_of_change(ctx, window),
        "no_prior_stable": lambda gt=0.0, window="30m": no_prior_stable(ctx, gt, window),
        "related": ctx.related,
    }

    # sustained() is tricky — it takes a *predicate result* as first arg.
    # We support two shapes:
    #   sustained(current > 200, min_duration='60s')  — single bool, checks last-eval
    #     then verifies history via a different path (the current-value is
    #     already embedded).
    # In practice the most useful form is checking current against a threshold
    # sustained over history. We implement this by providing
    #   sustained_gt(threshold, min_duration='60s')
    #   sustained_lt(threshold, min_duration='60s')
    # and encourage authors to use those forms. The generic sustained() takes
    # a bool and returns a bool — caller must guard in their own expression.
    functions["sustained"] = lambda pred_result, min_duration="60s": bool(pred_result) and sustained(
        ctx, lambda v: pred_result, min_duration  # identity: if pred_result true for current, check history
    )
    functions["sustained_gt"] = lambda threshold, min_duration="60s": sustained(
        ctx, lambda v: v > threshold, min_duration
    )
    functions["sustained_lt"] = lambda threshold, min_duration="60s": sustained(
        ctx, lambda v: v < threshold, min_duration
    )
    functions["sustained_eq"] = lambda value, min_duration="60s": sustained(
        ctx, lambda v: v == value, min_duration
    )
    functions["persistence"] = lambda min_duration="60s": persistence(ctx, min_duration)

    return EvalWithCompoundTypes(names=names, functions=functions)


def eval_trigger(expression: str, ctx: MetricContext) -> bool:
    """Evaluate a trigger expression against a metric context.

    Returns bool. Raises DSLEvaluationError on parse or eval failure.
    """
    evaluator = make_evaluator(ctx)
    try:
        result = evaluator.eval(expression)
    except (FunctionNotDefined, NameNotDefined) as e:
        raise DSLEvaluationError(
            f"Unknown symbol in trigger expression: {e}"
        ) from e
    except Exception as e:
        raise DSLEvaluationError(
            f"Error evaluating trigger {expression!r}: {e}"
        ) from e

    if not isinstance(result, bool):
        raise DSLEvaluationError(
            f"Trigger expression must return bool; got {type(result).__name__}: "
            f"{expression!r}"
        )
    return result
