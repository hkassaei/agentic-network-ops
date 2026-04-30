"""Tests for the anomaly-window timestamp plumbing in Phase 0.

Per ADR `dealing_with_temporality_3.md` Layer 1, the v6 orchestrator
must capture three canonical timestamps in session state when Phase 0
finds an anomaly:

  - `anomaly_window_start_ts` — earliest scored snapshot timestamp.
  - `anomaly_window_end_ts` — latest scored snapshot timestamp.
  - `anomaly_screener_snapshot_ts` — timestamp of the snapshot that
    produced the highest anomaly score.

Downstream phases (NA / IG / Investigator / Synthesis) use these as
the canonical "what time should I query?" reference. These tests
verify the orchestrator captures them correctly under the relevant
shapes of input.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from unittest.mock import patch

import pytest


@dataclass
class _MockReport:
    """Stand-in for AnomalyReport that the orchestrator's `best_report`
    handling needs. Only the attributes Phase 0 reads are populated."""
    overall_score: float
    flags: list = None  # type: ignore

    def __post_init__(self):
        if self.flags is None:
            self.flags = []

    def to_prompt_text(self) -> str:
        return f"score={self.overall_score}"

    def to_dict_list(self) -> list:
        return []


class _MockScreener:
    """Stand-in for AnomalyScreener with just the surface Phase 0 reads:
    `is_trained`, `training_samples`, `score(features, liveness)`.

    Each `score` call returns a report whose `overall_score` matches
    the next value in the configured sequence — letting the test
    control which snapshot becomes the `best_report`.
    """

    def __init__(self, scores: list[float]) -> None:
        self.is_trained = True
        self.training_samples = 100
        self._scores = list(scores)
        self._call = 0

    def score(self, features, liveness=None) -> _MockReport:
        s = self._scores[self._call]
        self._call += 1
        return _MockReport(overall_score=s)


def _mk_snap(
    *,
    timestamp: float,
    components: dict[str, dict[str, float]] | None = None,
) -> dict:
    """Build a snapshot in the shape Phase 0 expects:
    `{"_timestamp": ts, "<nf>": {"metrics": {...}}, ...}`.

    The actual feature derivation in this test is happening through a
    live `MetricPreprocessor`, so the components need to look enough
    like real metrics to keep the preprocessor happy.
    """
    if components is None:
        # Minimal-but-realistic IMS-registered baseline. Every counter
        # is constant across snapshots, so rates are 0 — the
        # preprocessor's emit-only-when-rate-can-be-computed logic will
        # gate the early snapshots out exactly the way real traffic
        # would. The screener's mock will then score whatever feature
        # vectors come through, regardless of values.
        components = {
            "amf": {"ran_ue": 2, "gnb": 1, "amf_session": 4},
            "smf": {"fivegs_smffunction_sm_sessionnbr": 4,
                    "bearers_active": 4},
            "upf": {"fivegs_upffunction_upf_sessionnbr": 4,
                    "fivegs_ep_n3_gtp_indatapktn3upf": 1000,
                    "fivegs_ep_n3_gtp_outdatapktn3upf": 1000},
            "pcscf": {"ims_usrloc_pcscf:registered_contacts": 2,
                      "dialog_ng:active": 0},
            "icscf": {},
            "scscf": {"ims_usrloc_scscf:active_contacts": 2},
        }
    return {
        "_timestamp": timestamp,
        **{name: {"metrics": metrics} for name, metrics in components.items()},
    }


# ============================================================================
# Happy path
# ============================================================================

@pytest.mark.asyncio
async def test_phase0_writes_three_timestamps_when_anomaly_found():
    """Given snapshots with known timestamps and a screener that scores
    above threshold on the 3rd scored sample, all three timestamps land
    in state and `anomaly_screener_snapshot_ts` matches the timestamp
    of the highest-scoring snapshot."""
    from agentic_ops_v6.orchestrator import _phase0_anomaly_screener

    # 10 snapshots, 5s apart. The first 6 are warmup (preprocessor
    # gate: `i < 6` produces empty feature dicts). Snapshots 6-9 score.
    base_ts = 1_700_000_000.0
    snapshots = [_mk_snap(timestamp=base_ts + i * 5.0) for i in range(10)]

    # Scores: only 4 calls (snapshots 6, 7, 8, 9). Highest is the third
    # call, i.e. snapshot index 8 (ts = base_ts + 40.0).
    mock_screener = _MockScreener(scores=[10.0, 20.0, 50.0, 30.0])

    state: dict[str, Any] = {}
    with patch(
        "anomaly_trainer.persistence.load_model",
        return_value=(mock_screener, None, {}),
    ):
        await _phase0_anomaly_screener(state, snapshots, all_phases=[])

    # All three timestamps must be present.
    assert "anomaly_window_start_ts" in state
    assert "anomaly_window_end_ts" in state
    assert "anomaly_screener_snapshot_ts" in state

    # Window covers the scored snapshots only (skips warmup), so start
    # is snapshot 6 and end is snapshot 9.
    assert state["anomaly_window_start_ts"] == base_ts + 30.0
    assert state["anomaly_window_end_ts"] == base_ts + 45.0

    # The highest-scoring snapshot is index 8 (ts = base_ts + 40).
    assert state["anomaly_screener_snapshot_ts"] == base_ts + 40.0


@pytest.mark.asyncio
async def test_phase0_screener_snapshot_ts_picks_max_score_tiebreak():
    """When two snapshots have the same overall_score, the FIRST one
    seen wins (the orchestrator's existing `>` comparison). Locking
    this behavior in so it doesn't silently flip to last-wins."""
    from agentic_ops_v6.orchestrator import _phase0_anomaly_screener

    base_ts = 2_000_000_000.0
    snapshots = [_mk_snap(timestamp=base_ts + i * 5.0) for i in range(8)]
    # Both scoring calls produce the same overall_score.
    mock_screener = _MockScreener(scores=[42.0, 42.0])

    state: dict[str, Any] = {}
    with patch(
        "anomaly_trainer.persistence.load_model",
        return_value=(mock_screener, None, {}),
    ):
        await _phase0_anomaly_screener(state, snapshots, all_phases=[])

    # Snapshot 6 scored first with 42.0; snapshot 7 also scored 42.0
    # but `>` rejects equal-score, so snapshot 6's timestamp wins.
    assert state["anomaly_screener_snapshot_ts"] == base_ts + 30.0


# ============================================================================
# Edge cases
# ============================================================================

@pytest.mark.asyncio
async def test_phase0_omits_timestamps_when_no_model_trained():
    """No trained model → Phase 0 returns early. Timestamps must not
    appear in state at all (so downstream code can `state.get(...)`
    and detect the absence cleanly)."""
    from agentic_ops_v6.orchestrator import _phase0_anomaly_screener

    class _UntrainedScreener:
        is_trained = False
        training_samples = 0

        def score(self, *args, **kwargs):
            raise AssertionError("untrained screener should not be scored")

    state: dict[str, Any] = {}
    with patch(
        "anomaly_trainer.persistence.load_model",
        return_value=(_UntrainedScreener(), None, {}),
    ):
        await _phase0_anomaly_screener(state, [], all_phases=[])

    assert "anomaly_window_start_ts" not in state
    assert "anomaly_window_end_ts" not in state
    assert "anomaly_screener_snapshot_ts" not in state


@pytest.mark.asyncio
async def test_phase0_omits_timestamps_when_no_snapshots_scored():
    """If every snapshot is filtered out by the rate-window warmup gate
    (fewer than 7 snapshots provided), no scoring happens, no
    `best_report` is produced, no timestamps land in state."""
    from agentic_ops_v6.orchestrator import _phase0_anomaly_screener

    base_ts = 3_000_000_000.0
    # Only 5 snapshots — all will be in the i < 6 warmup gate.
    snapshots = [_mk_snap(timestamp=base_ts + i * 5.0) for i in range(5)]
    mock_screener = _MockScreener(scores=[])  # never called

    state: dict[str, Any] = {}
    with patch(
        "anomaly_trainer.persistence.load_model",
        return_value=(mock_screener, None, {}),
    ):
        await _phase0_anomaly_screener(state, snapshots, all_phases=[])

    assert "anomaly_window_start_ts" not in state
    assert "anomaly_window_end_ts" not in state
    assert "anomaly_screener_snapshot_ts" not in state


@pytest.mark.asyncio
async def test_phase0_handles_snapshots_missing_timestamps():
    """Defensive: if a snapshot lacks `_timestamp`, the orchestrator
    must not crash. The snapshot still goes through preprocessing /
    scoring, but its timestamp can't contribute to the window. If
    NONE of the scored snapshots have a timestamp, the timestamps are
    absent from state — same behavior as the no-snapshots case."""
    from agentic_ops_v6.orchestrator import _phase0_anomaly_screener

    # 10 snapshots, none with a `_timestamp` field. Scoring will still
    # happen (preprocessor doesn't require timestamp; it falls back to
    # time.time() in places).
    components = {
        "amf": {"ran_ue": 2, "gnb": 1, "amf_session": 4},
        "smf": {"fivegs_smffunction_sm_sessionnbr": 4, "bearers_active": 4},
        "upf": {"fivegs_upffunction_upf_sessionnbr": 4,
                "fivegs_ep_n3_gtp_indatapktn3upf": 1000,
                "fivegs_ep_n3_gtp_outdatapktn3upf": 1000},
        "pcscf": {"ims_usrloc_pcscf:registered_contacts": 2,
                  "dialog_ng:active": 0},
        "icscf": {},
        "scscf": {"ims_usrloc_scscf:active_contacts": 2},
    }
    snapshots = [
        {name: {"metrics": metrics} for name, metrics in components.items()}
        for _ in range(10)
    ]
    mock_screener = _MockScreener(scores=[10.0, 20.0, 30.0, 40.0])

    state: dict[str, Any] = {}
    with patch(
        "anomaly_trainer.persistence.load_model",
        return_value=(mock_screener, None, {}),
    ):
        await _phase0_anomaly_screener(state, snapshots, all_phases=[])

    # Best report exists (the screener mock scored), but no timestamps
    # could be captured — the keys must be absent from state, not None.
    assert "anomaly_screener_snapshot_ts" not in state
    assert "anomaly_window_start_ts" not in state
    assert "anomaly_window_end_ts" not in state
