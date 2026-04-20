"""Correlation engine — consumes fired events, produces ranked hypotheses.

See docs/ADR/alarm_correlation_engine.md for the design.
"""

from .engine import correlate, correlate_episode
from .models import CorrelationHypothesis, CorrelationResult

__all__ = [
    "correlate",
    "correlate_episode",
    "CorrelationHypothesis",
    "CorrelationResult",
]
