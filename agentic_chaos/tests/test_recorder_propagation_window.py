"""Recorder rendering tests for the verifier's new `propagation_window_seconds`
field.

Verifies that the markdown summary shows the operationally-meaningful
propagation window (time since first fault was injected) instead of the
misleading `wait_seconds: 0, elapsed_seconds: 0.0` pair the verifier
emits when the ObservationTrafficAgent already ran ahead of it.

Three rendering paths to cover:

  1. New shape, observation_phase_ran=True  → "Propagation window: 144s
     (ObservationTrafficAgent drove traffic for this window; verifier
     added wait=0s on top)"
  2. New shape, observation_phase_ran=False → "Propagation window: 30s
     (verifier wait=30s; no prior observation traffic)"
  3. Legacy shape (no `propagation_window_seconds` key) → fall back to
     the original "Wait: Ns / Actual elapsed: Ms" pair so older
     episode JSON files render the same as before.
"""

from __future__ import annotations

from agentic_chaos.recorder import _generate_markdown_summary


def _make_episode(verification: dict) -> dict:
    """Minimal valid episode dict with the verification block we want to render."""
    return {
        "scenario": {"name": "Test Scenario", "category": "compound"},
        "baseline": {"stack_phase": "ready", "container_status": {}},
        "faults": [],
        "observations": [],
        "resolution": {},
        "rca_label": {},
        "challenge_result": None,
        "fault_verification": verification,
        "timestamp": "2026-05-13T15:33:00+00:00",
        "duration_seconds": 0.0,
        "episode_id": "ep_test",
    }


# ---------------------------------------------------------------------------
# New shape — `propagation_window_seconds` present
# ---------------------------------------------------------------------------


def test_observation_phase_ran_renders_traffic_agent_note():
    """When ObservationTrafficAgent ran, the recorder explains where the
    propagation window came from (so the wait=0 doesn't look like a skip)."""
    verification = {
        "verdict": "inconclusive",
        "wait_seconds": 0,
        "elapsed_seconds": 0.0,
        "propagation_window_seconds": 144.0,
        "observation_phase_ran": True,
        "filtered_deltas": {},
        "raw_delta_node_count": 1,
    }
    md = _generate_markdown_summary(_make_episode(verification), agent_version="v7")
    assert "**Propagation window:** 144s" in md
    assert "ObservationTrafficAgent drove traffic for this window" in md
    assert "verifier added wait=0s on top" in md
    # Old fields should not appear when the new shape is present.
    assert "**Wait:** 0s" not in md
    assert "**Actual elapsed:** 0.0s" not in md


def test_observation_phase_did_not_run_renders_verifier_wait():
    """No prior traffic agent → verifier did its own wait. Output is
    explicit about that so the operator knows the source of the window."""
    verification = {
        "verdict": "not_observed",
        "wait_seconds": 30,
        "elapsed_seconds": 30.04,
        "propagation_window_seconds": 30.05,
        "observation_phase_ran": False,
        "filtered_deltas": {},
        "raw_delta_node_count": 0,
    }
    md = _generate_markdown_summary(_make_episode(verification), agent_version="v7")
    assert "**Propagation window:** 30s" in md
    assert "verifier wait=30s" in md
    assert "no prior observation traffic" in md


def test_propagation_window_rendered_for_confirmed_verdict():
    """The new field renders regardless of verdict — it's not gated on
    inconclusive/not_observed."""
    verification = {
        "verdict": "confirmed",
        "wait_seconds": 0,
        "elapsed_seconds": 0.0,
        "propagation_window_seconds": 145.13,
        "observation_phase_ran": True,
        "filtered_deltas": {"pyhss": {"ims_subscribers": {"baseline": 2, "delta": -2}}},
        "raw_delta_node_count": 5,
    }
    md = _generate_markdown_summary(_make_episode(verification), agent_version="v7")
    assert "**Propagation window:** 145s" in md
    assert "confirmed" in md


# ---------------------------------------------------------------------------
# Legacy shape — backwards compatibility
# ---------------------------------------------------------------------------


def test_legacy_shape_falls_back_to_wait_and_elapsed():
    """Older episode JSON files (pre-fix) don't have
    `propagation_window_seconds`. They should still render — but via the
    original two-line layout."""
    verification = {
        "verdict": "inconclusive",
        "wait_seconds": 30,
        "elapsed_seconds": 30.05,
        # No propagation_window_seconds key
        "filtered_deltas": {},
        "raw_delta_node_count": 1,
    }
    md = _generate_markdown_summary(_make_episode(verification), agent_version="v6")
    # Legacy lines should appear
    assert "**Wait:** 30s" in md
    assert "**Actual elapsed:** 30.05s" in md
    # New "Propagation window" prefix should NOT appear when the new
    # field is absent
    assert "**Propagation window:**" not in md


def test_propagation_window_none_falls_back_to_legacy():
    """If `propagation_window_seconds` is explicitly None (e.g., no
    parseable fault timestamp) the recorder falls back to the legacy
    pair so we never render a `None` value."""
    verification = {
        "verdict": "not_observed",
        "wait_seconds": 0,
        "elapsed_seconds": 0.0,
        "propagation_window_seconds": None,
        "observation_phase_ran": True,
        "filtered_deltas": {},
        "raw_delta_node_count": 0,
    }
    md = _generate_markdown_summary(_make_episode(verification), agent_version="v7")
    assert "**Wait:** 0s" in md
    assert "**Actual elapsed:** 0.0s" in md
    assert "**Propagation window:**" not in md
