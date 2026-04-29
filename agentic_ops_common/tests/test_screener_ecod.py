"""Tests for the PyOD ECOD-based AnomalyScreener.

Replaced river HalfSpaceTrees on 2026-04-28 — see
`docs/ADR/anomaly_detector_replace_river_with_pyod.md`. These tests
cover the new contract:

  - Training samples accumulate into 4 state buckets keyed by
    `(calls_active, registration_in_progress)`.
  - `finalize_training()` fits a per-bucket ECOD and derives a
    per-bucket runtime anomaly cutoff. It is idempotent.
  - `score()` routes runtime samples to the matching bucket; falls
    back to the default bucket if the matching bucket is unfit.
  - Until `finalize_training()` is called, `score()` returns an empty
    report and `is_trained` is False.
  - Under-N buckets are skipped at finalize time (logged warning, not
    a hard failure).
"""

from __future__ import annotations

import random

import pytest

from agentic_ops_common.anomaly.screener import (
    AnomalyReport,
    AnomalyScreener,
)


# ============================================================================
# Helpers
# ============================================================================

def _healthy_sample(
    *,
    calls_active: int = 0,
    registration_in_progress: int = 0,
    cx_active: int = 0,
    rng: random.Random | None = None,
) -> dict[str, float]:
    """Build a synthetic but realistic-shaped training feature dict.

    Includes context features (which the screener routes on) and a
    handful of normal-range data features so the per-feature ECOD CDFs
    have something to fit.
    """
    r = rng or random.Random()
    return {
        "context.calls_active": float(calls_active),
        "context.registration_in_progress": float(registration_in_progress),
        "context.cx_active": float(cx_active),
        "icscf.cdp:average_response_time": 60.0 + r.gauss(0, 3),
        "scscf.ims_auth:mar_avg_response_time": 100.0 + r.gauss(0, 3),
        "derived.icscf_uar_timeout_ratio": 0.0,
        "normalized.icscf.core:rcv_requests_register_per_ue": (
            0.05 + r.gauss(0, 0.02) if registration_in_progress else 0.0
        ),
        "normalized.upf.gtp_indatapktn3upf_per_ue": (
            3.5 + r.gauss(0, 0.5) if calls_active else 0.0
        ),
        "normalized.pcscf.dialogs_per_ue": float(calls_active),
    }


def _train_balanced(screener: AnomalyScreener, samples_per_bucket: int = 40):
    """Fill all 4 buckets with healthy training samples."""
    r = random.Random(42)
    for ca in (0, 1):
        for ri in (0, 1):
            cx = ri  # cx_active correlates with registration in our trainer
            for _ in range(samples_per_bucket):
                screener.learn(_healthy_sample(
                    calls_active=ca, registration_in_progress=ri,
                    cx_active=cx, rng=r,
                ))


# ============================================================================
# Bucket routing
# ============================================================================

def test_learn_routes_samples_to_correct_bucket():
    """Samples should land in the bucket matching their context flags."""
    s = AnomalyScreener()
    r = random.Random(0)
    # 3 samples in (0,0); 5 in (0,1); 7 in (1,0); 11 in (1,1).
    counts = {(0, 0): 3, (0, 1): 5, (1, 0): 7, (1, 1): 11}
    for (ca, ri), n in counts.items():
        for _ in range(n):
            s.learn(_healthy_sample(
                calls_active=ca, registration_in_progress=ri,
                cx_active=ri, rng=r,
            ))
    assert s.bucket_sample_counts == counts


def test_bucket_key_treats_above_half_as_one():
    """`_bucket_key_for` clamps numeric context values to {0, 1} so a
    feature value drifting slightly above zero (numeric noise) doesn't
    silently flip routing."""
    from agentic_ops_common.anomaly.screener import _bucket_key_for
    assert _bucket_key_for({"context.calls_active": 0.0,
                            "context.registration_in_progress": 0.0}) == (0, 0)
    assert _bucket_key_for({"context.calls_active": 1.0,
                            "context.registration_in_progress": 0.0}) == (1, 0)
    assert _bucket_key_for({"context.calls_active": 0.49,
                            "context.registration_in_progress": 0.0}) == (0, 0)
    assert _bucket_key_for({"context.calls_active": 0.51,
                            "context.registration_in_progress": 0.0}) == (1, 0)
    # Missing keys default to 0.
    assert _bucket_key_for({}) == (0, 0)


# ============================================================================
# Pre-finalize behavior
# ============================================================================

def test_score_returns_empty_before_finalize():
    """Until `finalize_training()` is called, scoring must return an
    empty report — no flags can be produced because no ECOD is fit."""
    s = AnomalyScreener()
    _train_balanced(s, samples_per_bucket=40)
    assert not s.is_trained  # not yet finalized

    sample = _healthy_sample(calls_active=1, registration_in_progress=0)
    report = s.score(sample)
    assert report.flags == []
    assert report.model_ready is False


def test_score_returns_empty_when_too_few_samples():
    """Below the global minimum sample count, the screener stays unfit
    even after finalize."""
    s = AnomalyScreener()
    for _ in range(5):  # below _MIN_TRAINING_SAMPLES = 10
        s.learn(_healthy_sample())
    s.finalize_training()
    assert not s.is_trained
    assert s.score(_healthy_sample()).flags == []


# ============================================================================
# Finalize
# ============================================================================

def test_finalize_fits_each_bucket_and_derives_threshold():
    """After finalize, every bucket with ≥ _MIN_BUCKET_SAMPLES samples
    has a fitted ECOD and a non-zero per-bucket threshold."""
    s = AnomalyScreener()
    _train_balanced(s, samples_per_bucket=40)
    s.finalize_training()

    assert s.is_trained
    for bucket in ((0, 0), (0, 1), (1, 0), (1, 1)):
        assert s._bucket_models[bucket] is not None
        assert s._bucket_thresholds[bucket] > 0.0


def test_finalize_skips_under_trained_buckets():
    """Buckets below _MIN_BUCKET_SAMPLES are left unfit (model=None,
    threshold=0.0). Other buckets fit normally."""
    s = AnomalyScreener()
    r = random.Random(1)
    # (0,0) and (0,1) get 40 samples; (1,0) and (1,1) get only 5.
    for _ in range(40):
        s.learn(_healthy_sample(calls_active=0, registration_in_progress=0, rng=r))
        s.learn(_healthy_sample(calls_active=0, registration_in_progress=1, cx_active=1, rng=r))
    for _ in range(5):
        s.learn(_healthy_sample(calls_active=1, registration_in_progress=0, rng=r))
        s.learn(_healthy_sample(calls_active=1, registration_in_progress=1, cx_active=1, rng=r))

    s.finalize_training()

    assert s._bucket_models[(0, 0)] is not None
    assert s._bucket_models[(0, 1)] is not None
    assert s._bucket_models[(1, 0)] is None  # under-trained
    assert s._bucket_models[(1, 1)] is None  # under-trained


def test_finalize_is_idempotent():
    """Calling `finalize_training()` twice re-fits but doesn't crash
    or corrupt the screener. Models after second call are equivalent
    to those after first call (deterministic given the same input)."""
    s = AnomalyScreener()
    _train_balanced(s, samples_per_bucket=40)
    s.finalize_training()
    thresholds_first = dict(s._bucket_thresholds)

    s.finalize_training()  # should not crash
    thresholds_second = dict(s._bucket_thresholds)

    assert s.is_trained
    assert thresholds_first == thresholds_second


# ============================================================================
# Scoring
# ============================================================================

def test_healthy_sample_does_not_flag():
    """A runtime sample drawn from the same distribution as training
    should usually score below the bucket's training-derived threshold
    and produce no flags."""
    s = AnomalyScreener()
    _train_balanced(s, samples_per_bucket=80)
    s.finalize_training()

    r = random.Random(99)
    # Sample from each bucket; 4 of 4 should produce empty flag lists.
    for ca in (0, 1):
        for ri in (0, 1):
            sample = _healthy_sample(
                calls_active=ca, registration_in_progress=ri,
                cx_active=ri, rng=r,
            )
            report = s.score(sample)
            # The 99th-percentile threshold means ~1% of healthy samples
            # would still fire by definition. Don't assert flags == []
            # categorically; just assert flags either empty OR few-and-
            # low-severity.
            if report.flags:
                assert all(f.severity in ("LOW", "MEDIUM") for f in report.flags), (
                    f"healthy sample fired HIGH flags in bucket ({ca}, {ri}): "
                    f"{[f.metric for f in report.flags if f.severity == 'HIGH']}"
                )


def test_anomalous_sample_fires_flags():
    """A runtime sample with values clearly outside training distribution
    must produce flags."""
    s = AnomalyScreener()
    _train_balanced(s, samples_per_bucket=80)
    s.finalize_training()

    # Build a sample with absurdly out-of-range values in the same
    # bucket (1, 1). All response times spiked, all ratios spiked.
    sample = _healthy_sample(calls_active=1, registration_in_progress=1, cx_active=1)
    sample["icscf.cdp:average_response_time"] = 10000.0     # was ~60
    sample["scscf.ims_auth:mar_avg_response_time"] = 5000.0  # was ~100
    sample["derived.icscf_uar_timeout_ratio"] = 0.5          # was 0
    sample["normalized.icscf.core:rcv_requests_register_per_ue"] = 5.0  # was ~0.05

    report = s.score(sample)
    assert report.flags, "expected flags for grossly anomalous sample"
    # The most-flagged feature should be one of the spiked ones.
    top_metrics = {f"{f.component}.{f.metric}" for f in report.flags[:3]}
    spiked = {
        "icscf.cdp:average_response_time",
        "scscf.ims_auth:mar_avg_response_time",
        "derived.icscf_uar_timeout_ratio",
        "normalized.icscf.core:rcv_requests_register_per_ue",
    }
    assert top_metrics & spiked, (
        f"no spiked feature in top-3 flags: {top_metrics}"
    )


def test_score_routes_to_matching_bucket():
    """Score should route a runtime sample to the bucket matching its
    context flags, and the report should carry that bucket label."""
    s = AnomalyScreener()
    _train_balanced(s, samples_per_bucket=40)
    s.finalize_training()

    sample_idle = _healthy_sample(calls_active=0, registration_in_progress=0)
    sample_call = _healthy_sample(calls_active=1, registration_in_progress=0)
    assert s.score(sample_idle).bucket == (0, 0)
    assert s.score(sample_call).bucket == (1, 0)


def test_score_falls_back_to_default_when_bucket_unfit():
    """If a runtime sample's matching bucket has no fitted model
    (under-trained), scoring must fall back to the default bucket
    rather than crash."""
    s = AnomalyScreener()
    r = random.Random(2)
    # Train (0,0) only. The other 3 buckets stay empty.
    for _ in range(40):
        s.learn(_healthy_sample(calls_active=0, registration_in_progress=0, rng=r))
    s.finalize_training()

    # A sample with calls_active=1 routes to bucket (1, 0), which is
    # unfit. The screener should fall back to (0, 0).
    sample = _healthy_sample(calls_active=1, registration_in_progress=0)
    report = s.score(sample)
    assert report.bucket == (0, 0), (
        "expected fallback to default bucket when matching bucket unfit"
    )


# ============================================================================
# Public API surface stability
# ============================================================================

def test_feature_keys_includes_all_seen_keys():
    """`feature_keys` is the union of every key seen across all training
    samples, not the first sample's keys."""
    s = AnomalyScreener()
    s.learn({"context.calls_active": 0, "a": 1.0})
    s.learn({"context.calls_active": 0, "b": 2.0})  # b only here
    keys = s.feature_keys
    assert "a" in keys
    assert "b" in keys
    assert "context.calls_active" in keys


def test_training_samples_counts_across_all_buckets():
    s = AnomalyScreener()
    r = random.Random(3)
    for _ in range(7):
        s.learn(_healthy_sample(calls_active=0, registration_in_progress=0, rng=r))
    for _ in range(4):
        s.learn(_healthy_sample(calls_active=1, registration_in_progress=1, cx_active=1, rng=r))
    assert s.training_samples == 11


def test_reset_clears_all_state():
    s = AnomalyScreener()
    _train_balanced(s, samples_per_bucket=20)
    s.finalize_training()
    assert s.training_samples == 80
    assert s.is_trained

    s.reset()
    assert s.training_samples == 0
    assert not s.is_trained
    assert s.bucket_sample_counts == {(0, 0): 0, (0, 1): 0, (1, 0): 0, (1, 1): 0}


def test_anomaly_report_threshold_field_carries_bucket_threshold():
    """The report's `threshold` field is the bucket-specific runtime
    cutoff used to make the fire/no-fire decision. Used by the prompt
    rendering to show what threshold was applied."""
    s = AnomalyScreener()
    _train_balanced(s, samples_per_bucket=40)
    s.finalize_training()

    report = s.score(_healthy_sample(calls_active=0, registration_in_progress=0))
    assert report.threshold == s._bucket_thresholds[(0, 0)]
