"""measure_rtt sample-size calibration.

Per ADR `path_anchored_probe_planning_for_transport_layer_faults.md`,
the previous `-c 3` default had a 34% false-negative rate against a
30% loss fault and was the immediate cause of the 2026-05-06 rtpengine
mis-diagnosis.

The new derivation: `N = ceil(log(0.001) / log(1 - loss_threshold))`,
giving false-negative rate ≤ 0.001 against any true loss rate ≥
threshold.

This test pins the formula and is the hard CI gate against any future
reintroduction of `-c 3`.
"""

from __future__ import annotations

import math

import pytest

from agentic_ops.tools import measure_rtt_sample_size


@pytest.mark.parametrize(
    "threshold,expected",
    [
        (0.30, 20),    # ~2 s at -i 0.1 — 30% loss fault detection
        (0.10, 66),    # ~7 s — default
        (0.05, 135),   # ~14 s
        (0.01, 688),   # ~69 s — fine-grained loss detection
        (0.001, 6905), # ~690 s — production-quality fine loss
    ],
)
def test_sample_size_matches_formula(threshold: float, expected: int):
    """Sample size matches the formula's output exactly (ceil-rounded)."""
    n = measure_rtt_sample_size(threshold)
    assert n == expected
    # Sanity-check against the formula directly.
    formula_n = math.ceil(math.log(0.001) / math.log(1.0 - threshold))
    assert n == formula_n


def test_sample_size_at_30pct_is_at_least_20():
    """Hard guard: 30% threshold must produce at least 20 samples.

    The previous `-c 3` default produced false-negatives 34% of the
    time against a 30% loss fault. With N=20, P(0 drops | true=30%)
    = 0.7^20 ≈ 0.0008, well under 0.001. This test fails if anyone
    ever reintroduces a default that's too small.
    """
    assert measure_rtt_sample_size(0.30) >= 20


def test_sample_size_at_10pct_is_at_least_66():
    """Default threshold (0.10) must produce at least 66 samples."""
    assert measure_rtt_sample_size(0.10) >= 66


def test_sample_size_rejects_threshold_at_zero():
    """Loss threshold of 0 has no detection meaning (every probe should
    pass infinitely). Reject as a defensive guard."""
    with pytest.raises(ValueError):
        measure_rtt_sample_size(0.0)


def test_sample_size_rejects_threshold_at_one():
    """Threshold of 1 means 'detect 100% loss' — log(0) → -inf. Reject."""
    with pytest.raises(ValueError):
        measure_rtt_sample_size(1.0)


def test_sample_size_rejects_negative_threshold():
    with pytest.raises(ValueError):
        measure_rtt_sample_size(-0.1)


def test_sample_size_rejects_threshold_above_one():
    with pytest.raises(ValueError):
        measure_rtt_sample_size(1.5)


def test_sample_size_strictly_decreases_with_threshold():
    """Higher threshold → smaller sample size needed. Sanity check
    the formula's monotonicity."""
    thresholds = [0.30, 0.20, 0.10, 0.05, 0.01]
    sizes = [measure_rtt_sample_size(t) for t in thresholds]
    assert sizes == sorted(sizes)


def test_no_legacy_three_ping_in_realistic_range():
    """Hard gate against `-c 3` reintroduction at any realistic threshold.

    Realistic operational thresholds are 0.001 (production-quality
    fine loss) through 0.30 (chaos-injected coarse loss). In that
    whole range, no formula output should ever be 3 (the previous
    default that caused the 2026-05-06 rtpengine mis-diagnosis).
    Threshold ≥ 0.7 is mathematically allowed by the formula but
    operationally meaningless — those values aren't tested here.
    """
    for t in [0.001, 0.005, 0.01, 0.05, 0.10, 0.20, 0.30]:
        n = measure_rtt_sample_size(t)
        assert n != 3, (
            f"loss_threshold={t} produced N=3 — reintroduces the "
            f"previous default that was the cause of the 2026-05-06 "
            f"rtpengine mis-diagnosis. See ADR "
            f"path_anchored_probe_planning_for_transport_layer_faults.md."
        )
        assert n >= 20, (
            f"loss_threshold={t} produced N={n}; realistic thresholds "
            f"should require N≥20 for adequate detection power."
        )
