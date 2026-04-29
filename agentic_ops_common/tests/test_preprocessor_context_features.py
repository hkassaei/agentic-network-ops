"""Unit tests for the 3 operational-context features added to
`MetricPreprocessor.process()` (ADR anomaly_model_overflagging.md, Option 1).

The trees in HalfSpaceTrees can only learn conditional-on-state behavior
if the model receives a snapshot's operational state as part of its
feature vector. These tests verify the preprocessor encodes that state
correctly under each of the 4 (calls × registration) combinations the
multi-phase trainer targets.
"""

from __future__ import annotations

from agentic_ops_common.anomaly.preprocessor import (
    EXPECTED_FEATURE_KEYS,
    MetricPreprocessor,
)


# Build a minimally-realistic raw_metrics payload for one snapshot.
# Counter values are absolute; the preprocessor's sliding window converts
# them to rates by comparing against earlier snapshots.
def _raw_snapshot(
    *,
    dialog_active: int = 0,
    register_count: int = 0,
    icscf_uar_replies: int = 0,
    scscf_mar_replies: int = 0,
) -> dict:
    return {
        "amf": {"ran_ue": 2, "gnb": 1},
        "smf": {
            "fivegs_smffunction_sm_sessionnbr": 4,
            "bearers_active": 4,
        },
        "upf": {
            "fivegs_ep_n3_gtp_indatapktn3upf": 0,
            "fivegs_ep_n3_gtp_outdatapktn3upf": 0,
        },
        "pcscf": {
            "ims_usrloc_pcscf:registered_contacts": 2,
            "core:rcv_requests_register": register_count,
            "dialog_ng:active": dialog_active,
        },
        "icscf": {
            "ims_icscf:uar_replies_received": icscf_uar_replies,
            "cdp:replies_received": 0,
        },
        "scscf": {
            "ims_auth:mar_replies_received": scscf_mar_replies,
            "cdp:replies_received": 0,
        },
    }


def _prime_preprocessor(pp: MetricPreprocessor, base_snapshot: dict, t0: float) -> None:
    """Feed a base snapshot at t0, then a duplicate at t0+5 to seed the
    sliding-window history. After this, rates can be computed against the
    stable base for subsequent snapshots."""
    pp.process(base_snapshot, timestamp=t0)
    pp.process(base_snapshot, timestamp=t0 + 5)


# ============================================================================
# Phase C — idle-registered: calls_active=0, registration=0, cx_active=0
# ============================================================================

def test_phase_c_idle_registered_all_context_zero():
    pp = MetricPreprocessor()
    base = _raw_snapshot()
    _prime_preprocessor(pp, base, t0=1000.0)

    features = pp.process(_raw_snapshot(), timestamp=1010.0)

    assert features["context.calls_active"] == 0.0
    assert features["context.registration_in_progress"] == 0.0
    assert features["context.cx_active"] == 0.0


# ============================================================================
# Phase B — registration burst: calls=0, reg=1, cx=1
# ============================================================================

def test_phase_b_registration_burst():
    pp = MetricPreprocessor()
    base = _raw_snapshot(register_count=0, icscf_uar_replies=0)
    _prime_preprocessor(pp, base, t0=1000.0)

    # Counters advance: registers + UAR replies happened in this window
    features = pp.process(
        _raw_snapshot(register_count=10, icscf_uar_replies=10),
        timestamp=1010.0,
    )

    assert features["context.calls_active"] == 0.0
    assert features["context.registration_in_progress"] == 1.0
    assert features["context.cx_active"] == 1.0


# ============================================================================
# Phase D — active call: calls=1, reg=0, cx=0
# (Cx counters quiet during call hold; only the dialog_ng:active gauge
# is non-zero.)
# ============================================================================

def test_phase_d_active_call_only_calls_active_set():
    pp = MetricPreprocessor()
    base = _raw_snapshot(dialog_active=1)
    _prime_preprocessor(pp, base, t0=1000.0)

    features = pp.process(_raw_snapshot(dialog_active=1), timestamp=1010.0)

    assert features["context.calls_active"] == 1.0
    assert features["context.registration_in_progress"] == 0.0
    assert features["context.cx_active"] == 0.0


# ============================================================================
# Phase E — call + register: calls=1, reg=1, cx=1
# ============================================================================

def test_phase_e_call_plus_register_all_context_set():
    pp = MetricPreprocessor()
    base = _raw_snapshot(dialog_active=1, register_count=0, scscf_mar_replies=0)
    _prime_preprocessor(pp, base, t0=1000.0)

    # During Phase E both a call is held AND a re-register is in-flight,
    # bumping both rcv_requests_register and the S-CSCF MAR replies counter.
    features = pp.process(
        _raw_snapshot(dialog_active=1, register_count=5, scscf_mar_replies=5),
        timestamp=1010.0,
    )

    assert features["context.calls_active"] == 1.0
    assert features["context.registration_in_progress"] == 1.0
    assert features["context.cx_active"] == 1.0


# ============================================================================
# All 3 context features must appear in EXPECTED_FEATURE_KEYS so the
# save-coverage guard refuses to persist a model that didn't train on them.
# ============================================================================

def test_context_features_listed_in_expected_keys():
    assert "context.calls_active" in EXPECTED_FEATURE_KEYS
    assert "context.registration_in_progress" in EXPECTED_FEATURE_KEYS
    assert "context.cx_active" in EXPECTED_FEATURE_KEYS
