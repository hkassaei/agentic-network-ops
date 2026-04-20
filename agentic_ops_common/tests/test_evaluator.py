"""Integration tests for the trigger evaluator end-to-end.

These tests exercise the loader + DSL + evaluator + event store as a unit.
They feed synthetic metric history and verify that the right events fire.
"""

import textwrap
from pathlib import Path

import pytest

from agentic_ops_common.metric_kb import (
    EvaluationContext,
    EventStore,
    evaluate,
    load_kb,
)


# ============================================================================
# Fixtures: synthetic KB + event store
# ============================================================================

KB_YAML = textwrap.dedent("""
    metrics:
      amf:
        layer: core
        metrics:
          ran_ue:
            source: prometheus
            type: gauge
            unit: count
            plane: control
            description: "Count of RAN-attached UEs."
            healthy:
              scale_independent: false
              invariant: "Equals configured UE pool size."
            event_triggers:
              - id: core.amf.ran_ue_sudden_drop
                trigger: "dropped_by(current, prior_stable(window='5m'), 0.2)"
                clear_condition: "current >= 0.9 * prior_stable(window='5m')"
                local_meaning: "Sharp drop in attached UEs."
                magnitude_captured:
                  - current_value
                  - prior_stable_value
                  - delta_absolute
                  - delta_percent
                  - first_observed_at
              - id: core.amf.ran_ue_full_loss
                trigger: "current == 0 and prior_stable(window='5m') > 0 and not (phase == 'startup')"
                clear_condition: "current > 0"
                local_meaning: "Zero UEs attached when prior was non-zero."
                magnitude_captured: [current_value, first_observed_at]
      icscf:
        layer: ims
        metrics:
          cdp_avg_response_time:
            source: kamcmd
            type: gauge
            unit: ms
            plane: control
            description: "I-CSCF Diameter response time."
            healthy:
              scale_independent: true
              typical_range: [30, 100]
            event_triggers:
              - id: ims.icscf.cdp_latency_elevated
                trigger: "sustained_gt(200, min_duration='60s')"
                clear_condition: "sustained_lt(150, min_duration='60s')"
                local_meaning: "Elevated Diameter response time at I-CSCF."
                magnitude_captured: [current_value, first_observed_at]
""")


@pytest.fixture
def kb(tmp_path: Path):
    p = tmp_path / "metrics.yaml"
    p.write_text(KB_YAML)
    return load_kb(p)


@pytest.fixture
def store(tmp_path: Path):
    s = EventStore(tmp_path / "events.db")
    yield s
    s.close()


def _make_history(metric: str, value: float, now: float, length_s: float = 300, step_s: float = 5) -> dict:
    """Build a synthetic flat history for one metric."""
    return {metric: [(now - i * step_s, value) for i in range(int(length_s / step_s), 0, -1)]}


def _make_drop_history(metric: str, baseline: float, current: float,
                       now: float, drop_at_s: float = 60) -> dict:
    """History where metric was at baseline until `drop_at_s` seconds ago,
    then dropped to current.
    """
    step = 5.0
    series = []
    for i in range(60, 0, -1):
        t = now - i * step
        v = baseline if t < now - drop_at_s else current
        series.append((t, v))
    return {metric: series}


# ============================================================================
# Basic firing
# ============================================================================

def test_sudden_drop_triggers_event(kb, store):
    now = 1000.0
    eval_ctx = EvaluationContext(
        episode_id="ep_test_1",
        eval_time=now,
        history=_make_drop_history("core.amf.ran_ue", baseline=10.0, current=2.0, now=now),
        current_values={"core.amf.ran_ue": 2.0},
    )
    fired = evaluate(kb, eval_ctx, store)
    assert any(e.event_type == "core.amf.ran_ue_sudden_drop" for e in fired)

    # Verify payload
    evt = next(e for e in fired if e.event_type == "core.amf.ran_ue_sudden_drop")
    assert evt.magnitude_payload["current_value"] == 2.0
    assert evt.magnitude_payload["prior_stable_value"] == 10.0
    assert evt.magnitude_payload["delta_absolute"] == -8.0
    assert evt.magnitude_payload["delta_percent"] == pytest.approx(-80.0)


def test_no_drop_no_trigger(kb, store):
    now = 1000.0
    eval_ctx = EvaluationContext(
        episode_id="ep_test_2",
        eval_time=now,
        history=_make_history("core.amf.ran_ue", value=10.0, now=now),
        current_values={"core.amf.ran_ue": 10.0},
    )
    fired = evaluate(kb, eval_ctx, store)
    assert not any(e.event_type == "core.amf.ran_ue_sudden_drop" for e in fired)


def test_full_loss_triggers_when_not_startup(kb, store):
    now = 1000.0
    eval_ctx = EvaluationContext(
        episode_id="ep_test_3",
        eval_time=now,
        phase="steady_state",
        history=_make_drop_history("core.amf.ran_ue", 10.0, 0.0, now),
        current_values={"core.amf.ran_ue": 0.0},
    )
    fired = evaluate(kb, eval_ctx, store)
    types = {e.event_type for e in fired}
    assert "core.amf.ran_ue_full_loss" in types


def test_full_loss_suppressed_during_startup(kb, store):
    now = 1000.0
    eval_ctx = EvaluationContext(
        episode_id="ep_test_4",
        eval_time=now,
        phase="startup",
        history=_make_drop_history("core.amf.ran_ue", 10.0, 0.0, now),
        current_values={"core.amf.ran_ue": 0.0},
    )
    fired = evaluate(kb, eval_ctx, store)
    types = {e.event_type for e in fired}
    assert "core.amf.ran_ue_full_loss" not in types


def test_sustained_elevated_latency_triggers(kb, store):
    """I-CSCF response time at 500ms for the whole window should fire."""
    now = 1000.0
    eval_ctx = EvaluationContext(
        episode_id="ep_test_5",
        eval_time=now,
        history=_make_history("ims.icscf.cdp_avg_response_time", 500.0, now),
        current_values={"ims.icscf.cdp_avg_response_time": 500.0},
    )
    fired = evaluate(kb, eval_ctx, store)
    assert any(e.event_type == "ims.icscf.cdp_latency_elevated" for e in fired)


def test_brief_spike_does_not_trigger_sustained(kb, store):
    """Spike for just the last 10 seconds — sustained() requires 60s."""
    now = 1000.0
    history = {"ims.icscf.cdp_avg_response_time": []}
    for i in range(60, 0, -1):
        t = now - i * 5
        v = 500.0 if i <= 2 else 50.0  # spike only in last 10 seconds
        history["ims.icscf.cdp_avg_response_time"].append((t, v))
    eval_ctx = EvaluationContext(
        episode_id="ep_test_6",
        eval_time=now,
        history=history,
        current_values={"ims.icscf.cdp_avg_response_time": 500.0},
    )
    fired = evaluate(kb, eval_ctx, store)
    assert not any(e.event_type == "ims.icscf.cdp_latency_elevated" for e in fired)


# ============================================================================
# Persistence across evaluations
# ============================================================================

def test_event_not_refired_while_active(kb, store):
    """Once fired, an event should not fire again until cleared."""
    now = 1000.0
    ctx = EvaluationContext(
        episode_id="ep_test_7",
        eval_time=now,
        history=_make_drop_history("core.amf.ran_ue", 10.0, 2.0, now),
        current_values={"core.amf.ran_ue": 2.0},
    )
    evaluate(kb, ctx, store)
    assert store.count(episode_id="ep_test_7") >= 1

    # Second evaluation at same state — shouldn't produce duplicate
    ctx2 = EvaluationContext(
        episode_id="ep_test_7",
        eval_time=now + 10,
        history=_make_drop_history("core.amf.ran_ue", 10.0, 2.0, now + 10),
        current_values={"core.amf.ran_ue": 2.0},
    )
    fired2 = evaluate(kb, ctx2, store)
    assert not any(e.event_type == "core.amf.ran_ue_sudden_drop" for e in fired2)


def test_event_cleared_when_recovered(kb, store):
    """After clear_condition is met, the event is marked cleared."""
    now = 1000.0
    # Initial drop — fires
    ctx1 = EvaluationContext(
        episode_id="ep_test_8",
        eval_time=now,
        history=_make_drop_history("core.amf.ran_ue", 10.0, 0.0, now),
        current_values={"core.amf.ran_ue": 0.0},
    )
    evaluate(kb, ctx1, store)
    active_before = store.get_events(
        episode_id="ep_test_8", include_cleared=False,
    )
    full_loss_events = [e for e in active_before
                        if e.event_type == "core.amf.ran_ue_full_loss"]
    assert len(full_loss_events) == 1

    # Recovery — current > 0
    ctx2 = EvaluationContext(
        episode_id="ep_test_8",
        eval_time=now + 100,
        history=_make_history("core.amf.ran_ue", 10.0, now + 100),
        current_values={"core.amf.ran_ue": 10.0},
    )
    evaluate(kb, ctx2, store)

    active_after = store.get_events(
        episode_id="ep_test_8", include_cleared=False,
    )
    full_loss_active = [e for e in active_after
                        if e.event_type == "core.amf.ran_ue_full_loss"]
    assert len(full_loss_active) == 0  # was cleared


# ============================================================================
# Episode scoping
# ============================================================================

def test_episodes_isolated(kb, store):
    now = 1000.0
    for ep in ["ep_alpha", "ep_beta"]:
        ctx = EvaluationContext(
            episode_id=ep,
            eval_time=now,
            history=_make_drop_history("core.amf.ran_ue", 10.0, 2.0, now),
            current_values={"core.amf.ran_ue": 2.0},
        )
        evaluate(kb, ctx, store)

    alpha = store.get_events(episode_id="ep_alpha")
    beta = store.get_events(episode_id="ep_beta")
    assert len(alpha) == len(beta) >= 1


# ============================================================================
# Dry run
# ============================================================================

def test_dry_run_does_not_persist(kb, store):
    now = 1000.0
    ctx = EvaluationContext(
        episode_id="ep_dry",
        eval_time=now,
        history=_make_drop_history("core.amf.ran_ue", 10.0, 2.0, now),
        current_values={"core.amf.ran_ue": 2.0},
    )
    fired = evaluate(kb, ctx, store, dry_run=True)
    assert len(fired) >= 1
    assert store.count(episode_id="ep_dry") == 0


# ============================================================================
# Metric scoping
# ============================================================================

def test_metric_ids_scoping(kb, store):
    now = 1000.0
    ctx = EvaluationContext(
        episode_id="ep_scope",
        eval_time=now,
        history={
            **_make_drop_history("core.amf.ran_ue", 10.0, 2.0, now),
            **_make_history("ims.icscf.cdp_avg_response_time", 500.0, now),
        },
        current_values={
            "core.amf.ran_ue": 2.0,
            "ims.icscf.cdp_avg_response_time": 500.0,
        },
    )
    # Only evaluate ran_ue
    fired = evaluate(kb, ctx, store, metric_ids=["core.amf.ran_ue"])
    types = {e.event_type for e in fired}
    assert "core.amf.ran_ue_sudden_drop" in types
    assert "ims.icscf.cdp_latency_elevated" not in types
