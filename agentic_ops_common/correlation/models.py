"""Data classes for correlation engine output.

See docs/ADR/alarm_correlation_engine.md for the overall design.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CorrelationHypothesis:
    """A candidate hypothesis explaining a subset of observed events.

    Produced by the correlation engine from event + KB `correlates_with` hints.
    Consumed by the v6 NetworkAnalyst as input material for its ranked
    hypothesis list (the NA may refine, combine, or discard).

    Fields:
      statement: the composite_interpretation text from the KB, verbatim.
          This is the engine's claim about what the co-fired events mean.
      supporting_event_ids: event_type ids (namespaced) that support this
          hypothesis.
      supporting_event_objects: the fired events themselves (for evidence).
      implicated_nfs: NFs named as sources of supporting events. A quick
          answer to "which components are involved?"
      primary_nf: best guess at the single NF most central to this hypothesis
          (highest event count across supporting events).
      explanatory_fit: fraction in [0, 1] of total fired events this
          hypothesis explains. Higher = more complete explanation.
      testability: count of disambiguator metrics available for supporting
          events. Higher = more probes the Investigator can run.
      discriminating_metrics: union of disambiguators from supporting events
          (metric_ids). These are what the Investigator should probe.
      falsification_probes: suggested probe statements ("fetch metric X, if
          value Y then H is disproven"). Drawn from the KB's disambiguators.
    """
    statement: str
    supporting_event_ids: list[str] = field(default_factory=list)
    supporting_event_objects: list = field(default_factory=list)  # list[FiredEvent]
    implicated_nfs: list[str] = field(default_factory=list)
    primary_nf: Optional[str] = None
    explanatory_fit: float = 0.0
    testability: int = 0
    discriminating_metrics: list[str] = field(default_factory=list)
    falsification_probes: list[str] = field(default_factory=list)

    def is_testable(self) -> bool:
        """A hypothesis is testable if at least one disambiguating probe exists."""
        return len(self.discriminating_metrics) > 0


@dataclass
class CorrelationResult:
    """Output of the correlation engine for one episode.

    Fields:
      episode_id: the episode these events and hypotheses belong to.
      hypotheses: ranked list (best first) of candidate hypotheses.
      unmatched_events: events that did not participate in any hypothesis
          (either no correlates_with hint, or the co-firing peer was absent).
      events_considered: total fired events the correlator processed.
    """
    episode_id: str
    hypotheses: list[CorrelationHypothesis] = field(default_factory=list)
    unmatched_events: list = field(default_factory=list)
    events_considered: int = 0

    def top_hypothesis(self) -> Optional[CorrelationHypothesis]:
        return self.hypotheses[0] if self.hypotheses else None

    def summary_line(self) -> str:
        if not self.hypotheses:
            return (
                f"Correlation (episode {self.episode_id}): "
                f"{self.events_considered} event(s) observed, no composite "
                f"hypothesis formed."
            )
        top = self.hypotheses[0]
        return (
            f"Correlation (episode {self.episode_id}): "
            f"top hypothesis \"{top.statement}\" "
            f"supported by {len(top.supporting_event_ids)}/"
            f"{self.events_considered} events, "
            f"fit={top.explanatory_fit:.2f}, testability={top.testability}"
        )
