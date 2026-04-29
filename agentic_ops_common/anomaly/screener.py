"""AnomalyScreener — statistical anomaly detection using PyOD ECOD.

Replaced river HalfSpaceTrees with PyOD ECOD on 2026-04-28 for the
reasons documented in `docs/ADR/anomaly_detector_replace_river_with_pyod.md`.

Architecture:
  - 4 state buckets keyed by (calls_active, registration_in_progress)
    drawn from the preprocessor's `context.*` features. Each bucket has
    its own ECOD model fit at finalize time on bucket-specific training
    data, giving the screener conditional reasoning ("a quiet GTP rate
    is healthy when no calls are active, anomalous mid-call").
  - Static training: every training sample is permanently retained.
    The river tumbling-window forgetting that previously caused
    brittleness across retrains is gone.
  - Per-feature attribution falls out of ECOD's empirical CDF math:
    `model.O[-1]` after `decision_function()` is a per-feature outlier
    score for the inference sample. We sort by that to pick the top-K
    flagged metrics.

Lifecycle:
  1. Construct: `screener = AnomalyScreener()`
  2. Train: call `screener.learn(features)` once per training sample.
  3. Finalize: call `screener.finalize_training()` once at the end of
     training. Fits the per-bucket ECODs and derives per-bucket
     overall-anomaly thresholds.
  4. Score: call `screener.score(features, liveness=...)` for runtime
     samples. Returns an `AnomalyReport`.

This is NOT an ADK Agent — it's a plain Python class that the
AnomalyScreenerAgent (BaseAgent) wraps for pipeline integration.
"""

from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np
from pyod.models.ecod import ECOD

log = logging.getLogger("anomaly.screener")

# Minimum training samples (across the whole screener, not per bucket)
# before scoring is allowed.
_MIN_TRAINING_SAMPLES = 10

# Minimum samples per state bucket before that bucket gets a fitted
# ECOD model. Below this, the bucket is left unfit and runtime samples
# routed to it fall back to the default bucket. ECOD's empirical CDFs
# need a reasonable training count to give meaningful tail probabilities.
_MIN_BUCKET_SAMPLES = 30

# Top-K features to report as flags from a single anomalous score.
_TOP_K_FLAGS = 10

# Percentile of the in-bucket training-score distribution that becomes
# the runtime anomaly cutoff for that bucket. 99 = a snapshot must look
# more anomalous than 99% of the training samples to fire.
_TRAINING_PERCENTILE_FOR_THRESHOLD = 99.0

# Severity cutoffs on the per-feature ECOD outlier score (the values
# in `model.O`). The score is `-log(tail_probability)` per feature, so:
#   2 ≈ tail prob 0.135    (~1.5σ for Gaussian-like)
#   4 ≈ tail prob 0.0183   (~2.4σ)
#   8 ≈ tail prob 0.000335 (~3.6σ)
# These are starting values; they can be tuned during validation.
_SEVERITY_HIGH = 8.0
_SEVERITY_MEDIUM = 4.0

# =========================================================================
# Silent-failure severity escalation thresholds
# ADR: anomaly_training_zero_pollution.md
# =========================================================================
# When a metric's current value is 0 but its learned mean is substantially
# non-zero AND the feature is marked "live" (underlying counter advanced
# recently), severity is escalated to HIGH regardless of the per-feature
# outlier score. The per-metric-type floor filters out features whose
# mean is too small to be considered a load-bearing liveness signal.
_MIN_ACTIVE_MEAN_TIME_MS = 10.0  # response-time / duration metrics
_MIN_ACTIVE_MEAN_RATE = 0.01     # rate metrics (events per UE per window)


# =========================================================================
# State-bucket layout
# =========================================================================
# Buckets are keyed by (calls_active, registration_in_progress) — both
# binary, so 4 total. We deliberately do NOT split on cx_active too,
# because cx_active is highly correlated with registration_in_progress
# (a re-register triggers Cx exchanges) so an 8-way split would
# fragment training data without adding distinct conditional regions.
# ADR: anomaly_detector_replace_river_with_pyod.md, "How state-conditioning
# fits in".
_STATE_BUCKETS: tuple[tuple[int, int], ...] = (
    (0, 0),  # idle-registered (Phase C in the trainer)
    (0, 1),  # registration burst, no call (Phase B)
    (1, 0),  # active call, no signaling (Phase D)
    (1, 1),  # call + register (Phase E)
)

# Default bucket used when a runtime sample lands in a bucket that had
# no fitted model (e.g. its (calls × reg) combination wasn't trained).
# (0, 0) is the most common steady-state bucket and a reasonable default.
_DEFAULT_BUCKET: tuple[int, int] = (0, 0)


def _is_temporal_feature(key: str) -> bool:
    """Temporal features are response-time averages + the derived register time."""
    return "avg_response_time" in key or "register_time_ms" in key


@dataclass
class FlagKBContext:
    """KB-derived semantic context for a flagged metric.

    Populated by `agentic_ops_common.metric_kb.flag_enrichment.enrich_report`
    after the screener scores a snapshot. Carries the metric's authored
    meaning so downstream agents can interpret the deviation instead of
    guessing from the metric name.
    """
    kb_metric_id: str  # e.g. "ims.pcscf.avg_register_time_ms"
    display_name: Optional[str] = None
    unit: Optional[str] = None
    what_it_signals: Optional[str] = None
    direction_meaning: Optional[str] = None  # meaning.spike / .drop / .zero
    typical_range: Optional[tuple[float, float]] = None
    invariant: Optional[str] = None
    pre_existing_noise: Optional[str] = None


@dataclass
class AnomalyFlag:
    """A single flagged metric anomaly."""
    metric: str
    component: str
    current: float
    learned_normal: float
    anomaly_score: float
    severity: str  # HIGH, MEDIUM, LOW
    direction: str  # spike, drop, shift
    kb_context: Optional[FlagKBContext] = None


@dataclass
class AnomalyReport:
    """Output of the anomaly screener."""
    flags: list[AnomalyFlag] = field(default_factory=list)
    overall_score: float = 0.0
    threshold: float = 0.0
    training_samples: int = 0
    model_ready: bool = False
    bucket: Optional[tuple[int, int]] = None  # which (calls, reg) bucket scored

    def to_prompt_text(self) -> str:
        """Render as text suitable for injection into the NetworkAnalyst prompt.

        Each flag is rendered as a short semantic block rather than just a
        row in a bare numeric table. When KB context is attached (see
        `metric_kb.flag_enrichment.enrich_report`) the render includes the
        metric's authored meaning, its direction-specific interpretation,
        and its healthy range — so the NA sees *what the deviation means*,
        not only *what numbers moved*.
        """
        if not self.flags:
            return "No anomalies detected by the statistical screener."

        lines = []
        bucket_str = (
            f"context bucket {self.bucket}" if self.bucket is not None else "global"
        )
        lines.append(
            f"**ANOMALY DETECTED.** Overall anomaly score: {self.overall_score:.2f} "
            f"(per-bucket threshold: {self.threshold:.2f}, {bucket_str}, "
            f"trained on {self.training_samples} healthy snapshots). "
            f"The current metric pattern is statistically different from the learned "
            f"healthy baseline. Something in the network has changed."
        )
        lines.append("")
        lines.append(
            "The following metrics deviate from their learned-healthy baseline. "
            "Treat each as a semantic observation (meaning + numbers), not a number "
            "alone — the KB's interpretation is the authoritative reading.\n"
        )
        for f in sorted(self.flags, key=lambda x: -x.anomaly_score):
            lines.extend(_render_flag(f))
            lines.append("")

        return "\n".join(lines)

    def to_dict_list(self) -> list[dict[str, Any]]:
        """Serialize flags to a list of dicts for state passing."""
        out: list[dict[str, Any]] = []
        for f in self.flags:
            d: dict[str, Any] = {
                "metric": f.metric,
                "component": f.component,
                "current": f.current,
                "learned_normal": f.learned_normal,
                "anomaly_score": round(f.anomaly_score, 3),
                "severity": f.severity,
                "direction": f.direction,
            }
            if f.kb_context is not None:
                c = f.kb_context
                d["kb_context"] = {
                    "kb_metric_id": c.kb_metric_id,
                    "display_name": c.display_name,
                    "unit": c.unit,
                    "what_it_signals": c.what_it_signals,
                    "direction_meaning": c.direction_meaning,
                    "typical_range": (
                        list(c.typical_range) if c.typical_range else None
                    ),
                    "invariant": c.invariant,
                    "pre_existing_noise": c.pre_existing_noise,
                }
            out.append(d)
        return out


def _render_flag(f: "AnomalyFlag") -> list[str]:
    """Render one flag as a semantic block for the NA prompt."""
    curr = f"{f.current:.2f}" if isinstance(f.current, float) else str(f.current)
    norm = (
        f"{f.learned_normal:.2f}"
        if isinstance(f.learned_normal, float)
        else str(f.learned_normal)
    )
    name = f"`{f.component}.{f.metric}`"
    ctx = f.kb_context

    if ctx is None:
        return [
            f"- **{name}** — current **{curr}** vs learned baseline **{norm}** "
            f"({f.severity}, {f.direction}). *(No KB context available — "
            f"interpret from the metric name.)*"
        ]

    display = f" ({ctx.display_name})" if ctx.display_name else ""
    unit = f" {ctx.unit}" if ctx.unit else ""
    header = (
        f"- **{name}**{display} — current **{curr}{unit}** vs learned baseline "
        f"**{norm}{unit}** ({f.severity}, {f.direction})"
    )
    lines = [header]

    if ctx.what_it_signals:
        lines.append(f"    - **What it measures:** {ctx.what_it_signals.strip()}")
    if ctx.direction_meaning:
        label = {
            "spike": "Spike means",
            "drop": "Drop means",
            "zero": "Zero means",
            "shift": "Shift means",
        }.get(f.direction, "Deviation means")
        lines.append(f"    - **{label}:** {ctx.direction_meaning.strip()}")
    if ctx.typical_range:
        lo, hi = ctx.typical_range
        unit_s = f" {ctx.unit}" if ctx.unit else ""
        lines.append(
            f"    - **Healthy typical range:** {lo:g}–{hi:g}{unit_s}"
        )
    if ctx.invariant:
        lines.append(f"    - **Healthy invariant:** {ctx.invariant.strip()}")
    if ctx.pre_existing_noise:
        lines.append(
            f"    - **Known noise:** {ctx.pre_existing_noise.strip()}"
        )
    return lines


def _bucket_key_for(features: dict[str, float]) -> tuple[int, int]:
    """Compute the (calls_active, registration_in_progress) bucket key.

    Uses the binary `context.*` features emitted by the preprocessor.
    Robust to absent or non-binary values: anything > 0 is treated as 1,
    anything else as 0 (so a partial feature dict during early-training
    snapshots doesn't blow up).
    """
    ca = 1 if features.get("context.calls_active", 0) > 0.5 else 0
    ri = 1 if features.get("context.registration_in_progress", 0) > 0.5 else 0
    return (ca, ri)


class AnomalyScreener:
    """Statistical anomaly detection using PyOD ECOD with state-bucketing.

    Usage:
        screener = AnomalyScreener()

        # Training phase (healthy state)
        for snapshot in healthy_snapshots:
            screener.learn(snapshot)
        screener.finalize_training()

        # Scoring phase (during investigation)
        report = screener.score(current_snapshot)
        print(report.to_prompt_text())
    """

    def __init__(self) -> None:
        # Per-bucket training feature matrices. Filled by `learn()`,
        # consumed by `finalize_training()` to fit each bucket's ECOD.
        self._bucket_X: dict[tuple[int, int], list[list[float]]] = {
            b: [] for b in _STATE_BUCKETS
        }
        # Per-bucket fitted models. Set in `finalize_training()`. None
        # for buckets with too few training samples.
        self._bucket_models: dict[tuple[int, int], Optional[ECOD]] = {
            b: None for b in _STATE_BUCKETS
        }
        # Per-bucket runtime anomaly cutoff, derived from the bucket's
        # training-score distribution at finalize time.
        self._bucket_thresholds: dict[tuple[int, int], float] = {
            b: 0.0 for b in _STATE_BUCKETS
        }
        # Locked feature-key order. Set on the first `learn()` call so
        # the matrix columns are consistent across training and scoring.
        # Sorted alphabetically for stability.
        self._feature_keys_ordered: Optional[list[str]] = None
        # Per-feature running list of training values. Used to compute
        # `learned_normal` for each flag (the "what was the typical
        # value?" column the NA prompt shows). Maintained across all
        # buckets, not bucket-specific — `learned_normal` is a sanity-
        # check value for the operator, not used by the model itself.
        self._feature_means: dict[str, list[float]] = {}
        # Total samples accumulated across all buckets.
        self._training_samples = 0
        # finalize_training() called?
        self._fitted = False

    # ------------------------------------------------------------------
    # Read-only properties
    # ------------------------------------------------------------------

    @property
    def is_trained(self) -> bool:
        """True iff finalize_training() has been called and the screener
        has at least the minimum training samples. Until both conditions
        hold, `score()` returns an empty report."""
        return self._fitted and self._training_samples >= _MIN_TRAINING_SAMPLES

    @property
    def training_samples(self) -> int:
        return self._training_samples

    @property
    def feature_keys(self) -> list[str]:
        """Sorted list of feature keys the screener has been trained on.

        Derived from `_feature_means` (populated on every learn() call)
        — the union of every feature seen in any training sample. The
        save-coverage guard reads this to refuse persistence when the
        trained set diverges from `EXPECTED_FEATURE_KEYS`.
        """
        return sorted(self._feature_means.keys())

    @property
    def bucket_sample_counts(self) -> dict[tuple[int, int], int]:
        """Sample count per state bucket. Read by the trainer's
        per-bucket coverage gate to enforce ≥ N samples per bucket."""
        return {b: len(self._bucket_X[b]) for b in _STATE_BUCKETS}

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------

    def learn(self, features: dict[str, float]) -> None:
        """Accumulate one training sample. Call repeatedly during the
        baseline collection phase. Routes the sample to the bucket
        matching its current operational context.

        Does NOT fit the model — that happens at `finalize_training()`.
        """
        # Lock the feature-key column order on the first sample. Every
        # subsequent learn() and score() builds vectors in this same
        # order so ECOD sees a consistent column layout.
        if self._feature_keys_ordered is None:
            self._feature_keys_ordered = sorted(features.keys())

        # Build the feature row. Missing keys default to 0.0; this only
        # matters for the very first few snapshots, when the
        # preprocessor's sliding-window-rate pipeline hasn't filled
        # enough history to emit temporal features. By the time
        # _MIN_BUCKET_SAMPLES are accumulated, every feature emits
        # consistently.
        x = [float(features.get(k, 0.0)) for k in self._feature_keys_ordered]

        bucket = _bucket_key_for(features)
        self._bucket_X[bucket].append(x)

        # Track per-feature running list across all buckets. Used only
        # for the `learned_normal` field in flags (a sanity-check value
        # for the operator, not consumed by the model).
        for k, v in features.items():
            if k not in self._feature_means:
                self._feature_means[k] = []
            self._feature_means[k].append(float(v))

        self._training_samples += 1
        if self._training_samples % 30 == 0:
            log.info(
                "Trainer: %d samples, bucket sizes: %s",
                self._training_samples, self.bucket_sample_counts,
            )

    def finalize_training(self) -> None:
        """Fit ECOD on each bucket's accumulated training data and derive
        per-bucket runtime anomaly cutoffs. Call exactly once after the
        last `learn()` and before any `score()`.

        Idempotent — calling twice re-fits from the same accumulated
        data. Buckets with fewer than `_MIN_BUCKET_SAMPLES` are skipped
        (logged as warnings); runtime samples that route to those
        buckets fall back to the default bucket at score time.
        """
        if self._feature_keys_ordered is None:
            log.warning("finalize_training() called with no training samples.")
            self._fitted = True
            return

        for bucket in _STATE_BUCKETS:
            X = self._bucket_X[bucket]
            n = len(X)
            if n < _MIN_BUCKET_SAMPLES:
                log.warning(
                    "Bucket %s has only %d samples (<%d minimum); ECOD not "
                    "fitted for this bucket. Runtime samples routing to %s "
                    "will fall back to the default bucket.",
                    bucket, n, _MIN_BUCKET_SAMPLES, bucket,
                )
                self._bucket_models[bucket] = None
                self._bucket_thresholds[bucket] = 0.0
                continue

            X_arr = np.asarray(X, dtype=float)
            model = ECOD()
            model.fit(X_arr)
            # Derive the runtime anomaly cutoff from the bucket's own
            # training-score distribution. Anything more anomalous than
            # the 99th percentile of training fires.
            train_scores = model.decision_function(X_arr)
            self._bucket_thresholds[bucket] = float(
                np.percentile(train_scores, _TRAINING_PERCENTILE_FOR_THRESHOLD)
            )
            self._bucket_models[bucket] = model
            log.info(
                "Bucket %s: ECOD fit on %d samples, cutoff=%.3f (p%g of training).",
                bucket, n, self._bucket_thresholds[bucket],
                _TRAINING_PERCENTILE_FOR_THRESHOLD,
            )

        self._fitted = True
        log.info(
            "AnomalyScreener finalized. Bucket sizes: %s. "
            "Cutoffs: %s.",
            self.bucket_sample_counts,
            {b: round(t, 3) for b, t in self._bucket_thresholds.items()},
        )

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def score(
        self,
        features: dict[str, float],
        liveness: dict[str, bool] | None = None,
    ) -> AnomalyReport:
        """Score a runtime feature dict, returning flagged anomalies.

        Routes by current operational context to the matching per-bucket
        ECOD model. Returns an empty report (no flags) if the bucket
        score is below the bucket's training-derived threshold, or if
        the screener hasn't been finalized.
        """
        report = AnomalyReport(
            training_samples=self._training_samples,
            model_ready=self.is_trained,
        )

        if not self.is_trained:
            log.warning(
                "Anomaly model not ready (samples=%d, fitted=%s, min=%d).",
                self._training_samples, self._fitted, _MIN_TRAINING_SAMPLES,
            )
            return report

        # Route by operational context.
        bucket = _bucket_key_for(features)
        model = self._bucket_models.get(bucket)
        if model is None:
            log.warning(
                "No fitted model for bucket %s — falling back to %s.",
                bucket, _DEFAULT_BUCKET,
            )
            bucket = _DEFAULT_BUCKET
            model = self._bucket_models[bucket]
            if model is None:
                log.error(
                    "Default bucket %s also unfit — cannot score. "
                    "This means training was severely under-coverage.",
                    bucket,
                )
                return report

        report.bucket = bucket
        report.threshold = self._bucket_thresholds[bucket]

        # Build runtime feature vector in the locked column order.
        assert self._feature_keys_ordered is not None  # _fitted guarantees this
        x = np.asarray(
            [[float(features.get(k, 0.0)) for k in self._feature_keys_ordered]],
            dtype=float,
        )
        overall = float(model.decision_function(x)[0])
        report.overall_score = overall

        if overall < report.threshold:
            log.info(
                "Score %.3f below bucket %s threshold %.3f — no anomalies.",
                overall, bucket, report.threshold,
            )
            return report

        log.info(
            "Score %.3f ABOVE bucket %s threshold %.3f — attributing flags.",
            overall, bucket, report.threshold,
        )

        # ECOD's per-feature outlier scores for the inference sample
        # are the LAST row of `model.O` after `decision_function()`.
        # See pyod/models/ecod.py — `O` is a (n_train + n_inference,
        # n_features) matrix; we score one sample at a time so it's the
        # last row.
        per_feature = model.O[-1]
        report.flags = self._attribute_anomalies(features, per_feature, liveness)
        return report

    def _attribute_anomalies(
        self,
        features: dict[str, float],
        per_feature_scores: np.ndarray,
        liveness: dict[str, bool] | None = None,
    ) -> list[AnomalyFlag]:
        """Build flag list from ECOD's per-feature outlier scores.

        Top-K features by per-feature ECOD score → flagged. Direction
        (spike/drop/shift) is derived by comparing the runtime value to
        the cross-bucket learned mean. Severity is binned from the per-
        feature ECOD score with the silent-failure escalation rule
        applied on top (ADR: anomaly_training_zero_pollution.md).
        """
        assert self._feature_keys_ordered is not None

        candidates: list[tuple[float, str, float, float]] = []
        for i, key in enumerate(self._feature_keys_ordered):
            score = float(per_feature_scores[i])
            if score <= 0:
                continue
            current = float(features.get(key, 0.0))
            mean_values = self._feature_means.get(key, [])
            learned_mean = (
                sum(mean_values) / len(mean_values) if mean_values else 0.0
            )
            candidates.append((score, key, current, learned_mean))

        # Top K by per-feature outlier score.
        candidates.sort(key=lambda x: -x[0])
        flags: list[AnomalyFlag] = []
        for score, key, current, learned_mean in candidates[:_TOP_K_FLAGS]:
            parts = key.split(".", 1)
            component = parts[0] if len(parts) > 1 else "unknown"
            metric_name = parts[1] if len(parts) > 1 else key

            # Direction: relative to learned mean. Same logic as before.
            if learned_mean > 0 and current > learned_mean * 1.5:
                direction = "spike"
            elif learned_mean > 0 and current < learned_mean * 0.5:
                direction = "drop"
            elif learned_mean == 0 and current > 0:
                direction = "spike"
            else:
                direction = "shift"

            # Severity from per-feature ECOD score.
            if score >= _SEVERITY_HIGH:
                severity = "HIGH"
            elif score >= _SEVERITY_MEDIUM:
                severity = "MEDIUM"
            else:
                severity = "LOW"

            # Silent-failure escalation (ADR: anomaly_training_zero_pollution.md).
            # Same rule as before: a metric going to exactly 0 while its
            # learned mean is well above the active-signal floor, AND the
            # subsystem was active in the recent past, is categorically
            # different from "value drifted." Force HIGH.
            if (
                liveness is not None
                and current == 0.0
                and liveness.get(key, False)
            ):
                is_temporal = _is_temporal_feature(key)
                floor = (
                    _MIN_ACTIVE_MEAN_TIME_MS if is_temporal
                    else _MIN_ACTIVE_MEAN_RATE
                )
                if learned_mean > floor:
                    severity = "HIGH"

            flags.append(AnomalyFlag(
                metric=metric_name,
                component=component,
                current=round(current, 4),
                learned_normal=round(learned_mean, 4),
                anomaly_score=round(score, 3),
                severity=severity,
                direction=direction,
            ))

        flags.sort(key=lambda f: -f.anomaly_score)
        return flags

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Reset the screener to a freshly-constructed state.

        Used by re-training pipelines that want to clear all accumulated
        training data and start over. The on-disk persisted model is
        unaffected.
        """
        self.__init__()
