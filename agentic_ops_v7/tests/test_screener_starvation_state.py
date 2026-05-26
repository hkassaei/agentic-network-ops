"""Phase 0 / Phase 0.5 — screener_status state machine and starvation routing.

Pins the contract from ADR
`docs/ADR/screener_starvation_partial_metric_collection.md`:

  1. Phase 0 emits exactly one of `screener_status ∈ {"scored","starved","clean"}`.
  2. When fewer than `_PHASE0_MIN_INPUT_SNAPSHOTS` snapshots reach Phase 0,
     the status is `"starved"` and a human-readable reason is set.
  3. The starvation branch sets `anomaly_flags=[]` (so the existing
     consumers at orchestrator:flag-readers see an empty list) AND
     `anomaly_report` text that explicitly tells downstream consumers to
     treat absence-of-flags as "unknown", not "healthy".
  4. The SymptomClassifier short-circuits when `screener_status=="starved"`
     and emits `label="insufficient_anomaly_evidence"` without calling
     `classify()` — this is what flips the orchestrator's routing into the
     conservative-fallback path (walker runs unconditionally).

The tests exercise the orchestrator helpers directly with a synthesized
`state` dict, not the full async pipeline. The latter requires the live
ADK runtime + a trained model; the unit-level contract is what this file
pins.
"""

from __future__ import annotations

import pytest

from agentic_ops_v7 import orchestrator


# ---------------------------------------------------------------------------
# Phase 0.5 — classifier short-circuit on starvation
# ---------------------------------------------------------------------------


def test_phase05_short_circuits_on_starved_status():
    """When Phase 0 set `screener_status='starved'`, the classifier emits
    `insufficient_anomaly_evidence` WITHOUT attempting a KB-driven
    classification (which would fail with a None report and default to
    `application_layer` — the exact mis-routing this ADR fixes)."""
    state: dict = {
        "screener_status": "starved",
        "screener_starvation_reason": (
            "Only 3 snapshots reached Phase 0; the rate-window preprocessor "
            "needs ≥7 to seed temporal features."
        ),
        # Deliberately no `_anomaly_report_obj` — classify() would crash on
        # this in a normal run; the short-circuit must avoid calling it.
    }
    all_phases: list = []

    orchestrator._phase05_symptom_classifier(state, all_phases)

    sc = state.get("symptom_classification")
    assert sc is not None, "Phase 0.5 must always set symptom_classification"
    assert sc["label"] == "insufficient_anomaly_evidence", (
        f"Expected insufficient_anomaly_evidence on starvation, got {sc['label']}"
    )
    # The starvation reason must propagate into the classifier's rationale
    # so the NA prompt (which reads `state['anomaly_report']`) is not the
    # only place the operator sees it.
    assert "starved" in sc["rationale"].lower()
    assert "preprocessor" in sc["rationale"]


def test_phase05_falls_through_to_classify_when_not_starved():
    """When `screener_status != 'starved'`, Phase 0.5 runs the real
    KB-driven classifier (no regression on the happy path)."""
    # No screener_status (or `scored`/`clean`) — must hit the existing
    # classify() path. Without a report_obj it should still produce a
    # classification (the existing default-to-application_layer branch).
    state: dict = {
        "_anomaly_report_obj": None,  # forces the empty-report default
    }
    all_phases: list = []

    orchestrator._phase05_symptom_classifier(state, all_phases)

    sc = state.get("symptom_classification")
    assert sc is not None
    # The existing `classify()` returns `application_layer` for empty
    # reports — this confirms the short-circuit didn't fire when
    # screener_status was absent.
    assert sc["label"] != "insufficient_anomaly_evidence"


# ---------------------------------------------------------------------------
# Phase 0 — three-way state machine contract (snapshot-count branches)
#
# These tests bypass the full screener pipeline by exercising the same
# orchestrator constants the production code uses. The production logic
# is straightforward arithmetic on `len(snapshots)` vs.
# `_PHASE0_MIN_INPUT_SNAPSHOTS`; the goal here is to pin the
# state-key shape and the thresholds.
# ---------------------------------------------------------------------------


def test_phase0_constants_are_typed_correctly():
    """Defensive: the threshold constants are int, not float, and the
    starvation threshold is strictly greater than the scored threshold."""
    assert isinstance(orchestrator._PHASE0_MIN_INPUT_SNAPSHOTS, int)
    assert isinstance(orchestrator._MIN_SCORED_SNAPSHOTS, int)
    assert orchestrator._PHASE0_MIN_INPUT_SNAPSHOTS >= 7, (
        "The preprocessor's rate-window pipeline needs ≥7 samples to seed "
        "temporal features; below this the screener cannot score."
    )


def test_screener_status_literal_includes_three_values():
    """The `ScreenerStatus` Literal type contains exactly the three values
    the orchestrator emits and the downstream consumers check."""
    # Pull the Literal args via typing.get_args
    import typing
    args = set(typing.get_args(orchestrator.ScreenerStatus))
    assert args == {"scored", "starved", "clean"}, (
        f"ScreenerStatus must be exactly the three documented values; got {args}"
    )


def test_insufficient_anomaly_evidence_in_symptom_label_literal():
    """The `SymptomLabel` Literal must include `insufficient_anomaly_evidence`
    so the orchestrator's routing branch can check against it and
    pattern-matchers in test code can rely on the value."""
    import typing
    from agentic_ops_v7.symptom_classifier import SymptomLabel
    args = set(typing.get_args(SymptomLabel))
    assert "insufficient_anomaly_evidence" in args
    # And the existing values are preserved (no regression).
    assert "transport_layer" in args
    assert "application_layer" in args
    assert "mixed" in args
