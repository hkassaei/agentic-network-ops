"""AnomalyScreener — statistical anomaly detection using River + PyOD.

Primary detector: River HalfSpaceTrees (streaming, multivariate)
Secondary detector: PyOD ECOD (batch, zero hyperparameters)

The screener has two modes:
  1. Training (learn_one): feed healthy-state metric snapshots
  2. Scoring (score): score a new snapshot and return flagged anomalies

This is NOT an ADK Agent — it's a plain Python class that the
AnomalyScreenerAgent (BaseAgent) wraps for pipeline integration.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from typing import Any

from river import anomaly as river_anomaly

log = logging.getLogger("v5.anomaly.screener")

# Anomaly score threshold — scores above this are flagged.
# River HalfSpaceTrees scores are in [0, 1] where 1 = most anomalous.
_RIVER_THRESHOLD = 0.7

# Minimum training samples before scoring is meaningful
_MIN_TRAINING_SAMPLES = 10


@dataclass
class AnomalyFlag:
    """A single flagged metric anomaly."""
    metric: str
    component: str
    current: float
    learned_normal: float
    anomaly_score: float
    severity: str  # HIGH, MEDIUM, LOW
    direction: str  # spike, drop, flat_while_related_spiking


@dataclass
class AnomalyReport:
    """Output of the anomaly screener."""
    flags: list[AnomalyFlag] = field(default_factory=list)
    overall_score: float = 0.0
    training_samples: int = 0
    model_ready: bool = False

    def to_prompt_text(self) -> str:
        """Render as text suitable for injection into the NetworkAnalyst prompt."""
        if not self.flags:
            return "No anomalies detected by the statistical screener."

        lines = [
            "The following metrics were flagged as anomalous by the statistical "
            "anomaly detector. These MUST be reflected in your layer ratings:\n",
            "| Component | Metric | Current | Learned Normal | Severity |",
            "|-----------|--------|---------|---------------|----------|",
        ]
        for f in sorted(self.flags, key=lambda x: -x.anomaly_score):
            curr = f"{f.current:.2f}" if isinstance(f.current, float) else str(f.current)
            norm = f"{f.learned_normal:.2f}" if isinstance(f.learned_normal, float) else str(f.learned_normal)
            lines.append(f"| {f.component} | {f.metric} | {curr} | {norm} | {f.severity} |")

        lines.append(f"\nOverall anomaly score: {self.overall_score:.2f} "
                      f"(trained on {self.training_samples} healthy snapshots)")
        return "\n".join(lines)

    def to_dict_list(self) -> list[dict[str, Any]]:
        """Serialize flags to a list of dicts for state passing."""
        return [
            {
                "metric": f.metric,
                "component": f.component,
                "current": f.current,
                "learned_normal": f.learned_normal,
                "anomaly_score": round(f.anomaly_score, 3),
                "severity": f.severity,
                "direction": f.direction,
            }
            for f in self.flags
        ]


class AnomalyScreener:
    """Statistical anomaly detection using River HalfSpaceTrees.

    Usage:
        screener = AnomalyScreener()

        # Training phase (healthy state)
        for snapshot in healthy_snapshots:
            screener.learn(snapshot)

        # Scoring phase (during investigation)
        report = screener.score(current_snapshot)
        print(report.to_prompt_text())
    """

    def __init__(
        self,
        n_trees: int = 50,
        height: int = 15,
        window_size: int = 50,
        threshold: float = _RIVER_THRESHOLD,
    ) -> None:
        self._model = river_anomaly.HalfSpaceTrees(
            n_trees=n_trees,
            height=height,
            window_size=window_size,
            seed=42,
        )
        self._threshold = threshold
        self._training_samples = 0
        self._feature_means: dict[str, list[float]] = {}
        self._feature_keys: list[str] | None = None

    @property
    def is_trained(self) -> bool:
        return self._training_samples >= _MIN_TRAINING_SAMPLES

    @property
    def training_samples(self) -> int:
        return self._training_samples

    def learn(self, features: dict[str, float]) -> None:
        """Feed one healthy-state feature dict to the model.

        Call this repeatedly during the baseline collection phase.
        Uses River's streaming pattern: score_one() then learn_one()
        so the model builds proper reference mass profiles.
        Adds dither noise (~5% of value or ±0.05) to create meaningful
        variance for HalfSpaceTrees to build useful splits, especially
        when metrics are constant between polls in healthy idle state.
        """
        dithered = {}
        for k, v in features.items():
            noise = random.gauss(0, max(abs(v) * 0.05, 0.05))
            dithered[k] = v + noise

        # River streaming pattern: score before learn
        self._model.score_one(dithered)
        self._model.learn_one(dithered)
        self._training_samples += 1

        # Track per-feature running means for anomaly attribution
        for k, v in features.items():
            if k not in self._feature_means:
                self._feature_means[k] = []
            self._feature_means[k].append(v)

        if self._feature_keys is None:
            self._feature_keys = sorted(features.keys())

        if self._training_samples % 10 == 0:
            log.info("Anomaly model trained on %d samples (%d features)",
                     self._training_samples, len(features))

    def score(self, features: dict[str, float]) -> AnomalyReport:
        """Score a new feature dict and return flagged anomalies.

        Args:
            features: Preprocessed feature dict from MetricPreprocessor.

        Returns:
            AnomalyReport with flagged metrics and overall score.
        """
        report = AnomalyReport(
            training_samples=self._training_samples,
            model_ready=self.is_trained,
        )

        if not self.is_trained:
            log.warning("Anomaly model not ready (only %d samples, need %d)",
                        self._training_samples, _MIN_TRAINING_SAMPLES)
            return report

        # Overall anomaly score
        overall = self._model.score_one(features)
        report.overall_score = overall

        if overall < self._threshold:
            log.info("Anomaly score %.3f below threshold %.2f — no anomalies",
                     overall, self._threshold)
            return report

        log.info("Anomaly score %.3f ABOVE threshold %.2f — identifying features",
                 overall, self._threshold)

        # Identify which features contribute most via leave-one-out attribution
        flags = self._attribute_anomalies(features, overall)
        report.flags = flags

        return report

    def _attribute_anomalies(
        self,
        features: dict[str, float],
        overall_score: float,
    ) -> list[AnomalyFlag]:
        """Identify which features contribute most to the anomaly score.

        Uses leave-one-out: for each feature, replace it with its learned
        mean and re-score. Features whose removal drops the score most
        are the biggest contributors.
        """
        flags: list[AnomalyFlag] = []

        for key, current_value in features.items():
            # Get learned normal for this feature
            mean_values = self._feature_means.get(key, [])
            if not mean_values:
                continue
            learned_mean = sum(mean_values) / len(mean_values)

            # Skip features that haven't changed from normal
            if abs(current_value - learned_mean) < 0.01:
                continue

            # Leave-one-out: replace this feature with its mean, re-score
            modified = dict(features)
            modified[key] = learned_mean
            reduced_score = self._model.score_one(modified)

            # Contribution = how much the score drops when this feature is "fixed"
            contribution = overall_score - reduced_score

            if contribution > 0.05:  # meaningful contribution
                # Parse component from feature key: "pcscf.metric_name" → "pcscf"
                parts = key.split(".", 1)
                component = parts[0] if len(parts) > 1 else "unknown"
                metric_name = parts[1] if len(parts) > 1 else key

                # Determine direction
                if current_value > learned_mean * 1.5:
                    direction = "spike"
                elif current_value < learned_mean * 0.5 and learned_mean > 0:
                    direction = "drop"
                else:
                    direction = "shift"

                # Severity based on contribution
                if contribution > 0.2:
                    severity = "HIGH"
                elif contribution > 0.1:
                    severity = "MEDIUM"
                else:
                    severity = "LOW"

                flags.append(AnomalyFlag(
                    metric=metric_name,
                    component=component,
                    current=round(current_value, 4),
                    learned_normal=round(learned_mean, 4),
                    anomaly_score=round(contribution, 3),
                    severity=severity,
                    direction=direction,
                ))

        # Sort by anomaly score descending
        flags.sort(key=lambda f: -f.anomaly_score)
        return flags

    def reset(self) -> None:
        """Reset the model (e.g., for re-training on new baseline)."""
        self.__init__(threshold=self._threshold)
