"""MetricContext — storage abstraction for trigger evaluation.

The DSL predicates (prior_stable, dropped_by, etc.) need access to:
  - current value of this metric (at evaluation time)
  - historical values of this metric over a window
  - current value of OTHER related metrics (for correlation predicates)
  - the lifecycle phase (startup / steady_state / draining)

This module defines the interface + two implementations:

  * InMemoryMetricContext — backed by a dict of (metric_id -> list[(t, v)]) time
    series. For testing; also used by the chaos framework when it wants to feed
    pre-collected snapshots.

  * PrometheusMetricContext — backed by Prometheus HTTP API. For production
    evaluation; queries `metric` at `time=now`, or `metric[window]` for ranges.

The MetricContext interface is deliberately narrow — predicates only need a
handful of operations. Everything else (rate computation, median filtering)
is implemented in the predicate layer from primitive history queries.
"""

from __future__ import annotations

import abc
import logging
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger("metric_kb.metric_context")

# ----------------------------------------------------------------------------
# Time parsing — DSL accepts '5m', '30s', '1h' strings
# ----------------------------------------------------------------------------

def parse_duration_seconds(s: str | float | int) -> float:
    """Parse a duration like '5m' or '30s' into seconds.

    Accepts numeric inputs (treated as seconds) for convenience.
    """
    if isinstance(s, (int, float)):
        return float(s)
    s = s.strip().lower()
    if s.endswith("ms"):
        return float(s[:-2]) / 1000.0
    if s.endswith("s"):
        return float(s[:-1])
    if s.endswith("m"):
        return float(s[:-1]) * 60.0
    if s.endswith("h"):
        return float(s[:-1]) * 3600.0
    if s.endswith("d"):
        return float(s[:-1]) * 86400.0
    # bare number treated as seconds
    return float(s)


# ----------------------------------------------------------------------------
# Interface
# ----------------------------------------------------------------------------

class MetricContext(abc.ABC):
    """Per-metric evaluation context passed to DSL predicates.

    For a single trigger evaluation, the context is bound to:
      - a focal metric (`metric_id`) whose current value is `current`
      - an evaluation timestamp (`eval_time`)
      - a lifecycle `phase`

    Predicates that need history call `get_history(window_seconds)`.
    Predicates that need cross-metric values call `related(other_metric_id)`.
    """

    @property
    @abc.abstractmethod
    def metric_id(self) -> str: ...

    @property
    @abc.abstractmethod
    def current(self) -> float: ...

    @property
    @abc.abstractmethod
    def eval_time(self) -> float:
        """Epoch seconds at which evaluation is anchored."""

    @property
    @abc.abstractmethod
    def phase(self) -> str: ...

    @abc.abstractmethod
    def get_history(self, window_seconds: float) -> list[tuple[float, float]]:
        """Return (timestamp, value) pairs within the last window_seconds
        relative to eval_time, inclusive. Ordered oldest-first."""

    @abc.abstractmethod
    def related(self, other_metric_id: str) -> Optional[float]:
        """Current value of another metric at eval_time, or None if unknown."""

    def baseline_mean(self) -> Optional[float]:
        """Healthy baseline mean (from trained model or KB).

        Default None; backends that have access to it may override.
        Predicates using `baseline_mean` in expressions tolerate None by
        returning False for comparisons.
        """
        return None


# ----------------------------------------------------------------------------
# In-memory implementation (for tests + chaos framework)
# ----------------------------------------------------------------------------

@dataclass
class InMemoryMetricContext(MetricContext):
    """Metric context backed by a dict of time series.

    ``history[metric_id]`` is a list of (timestamp, value) pairs, sorted by time.

    ``current_values[metric_id]`` is the authoritative current value at
    ``eval_time_`` (for the focal and related metrics).
    """

    metric_id_: str
    history: dict[str, list[tuple[float, float]]]
    current_values: dict[str, float]
    eval_time_: float
    phase_: str = "steady_state"
    baselines: dict[str, float] = field(default_factory=dict)

    @property
    def metric_id(self) -> str:
        return self.metric_id_

    @property
    def current(self) -> float:
        return self.current_values[self.metric_id_]

    @property
    def eval_time(self) -> float:
        return self.eval_time_

    @property
    def phase(self) -> str:
        return self.phase_

    def get_history(self, window_seconds: float) -> list[tuple[float, float]]:
        lo = self.eval_time_ - window_seconds
        series = self.history.get(self.metric_id_, [])
        return [(t, v) for (t, v) in series if lo <= t <= self.eval_time_]

    def related(self, other_metric_id: str) -> Optional[float]:
        return self.current_values.get(other_metric_id)

    def baseline_mean(self) -> Optional[float]:
        return self.baselines.get(self.metric_id_)
