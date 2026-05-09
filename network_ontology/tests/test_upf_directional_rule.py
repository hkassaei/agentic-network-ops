"""Tests for the pure-Python UPF directional-rule evaluator.

Per ADR `upf_directional_rates_in_dp_quality_gauges.md`. The
evaluator must:
  - Fire on the cumulative pair alone, with window_kind=cumulative.
  - Fire on the rate pair alone, with window_kind=rate.
  - Fire on BOTH (two verdicts, one per pair) when both pairs are
    in the observations dict.
  - Compute asymmetry as |in - out| / max(|in|, |out|) * 100.
  - Severity: high_temptation when asymmetry >= 30%, informational
    otherwise.
  - Be safe against missing-pair-half (no fire) and non-numeric
    values (no fire, no crash).
  - Load rule prose (rule:, implication:, examples:, invalidates:,
    priority:) from stack_rules.yaml so each verdict carries the
    same shape OntologyClient.check_stack_rules produces.

These tests are pure-Python, no Neo4j, no Prometheus.
"""

from __future__ import annotations

import pytest

from network_ontology.rules import evaluate_upf_directional_rule


# ----------------------------------------------------------------------
# Cumulative pair — fires from get_nf_metrics-style observations.
# ----------------------------------------------------------------------

def test_cumulative_pair_fires_with_window_kind_cumulative():
    verdicts = evaluate_upf_directional_rule({
        "fivegs_ep_n3_gtp_indatapktn3upf": 3423,
        "fivegs_ep_n3_gtp_outdatapktn3upf": 1267,
    })
    assert len(verdicts) == 1
    v = verdicts[0]
    assert v["window_kind"] == "cumulative"
    assert v["in_key"] == "fivegs_ep_n3_gtp_indatapktn3upf"
    assert v["out_key"] == "fivegs_ep_n3_gtp_outdatapktn3upf"
    assert v["in_total"] == 3423
    assert v["out_total"] == 1267


def test_cumulative_high_asymmetry_is_high_temptation():
    """63% asymmetry — the canonical failing-scenario value."""
    verdicts = evaluate_upf_directional_rule({
        "fivegs_ep_n3_gtp_indatapktn3upf": 3423,
        "fivegs_ep_n3_gtp_outdatapktn3upf": 1267,
    })
    v = verdicts[0]
    assert v["asymmetry_pct"] == 63.0
    assert v["severity"] == "high_temptation"


def test_cumulative_low_asymmetry_is_informational():
    """2% asymmetry — within-window consistency, but rule still fires."""
    verdicts = evaluate_upf_directional_rule({
        "fivegs_ep_n3_gtp_indatapktn3upf": 5000,
        "fivegs_ep_n3_gtp_outdatapktn3upf": 4900,
    })
    v = verdicts[0]
    assert v["asymmetry_pct"] == 2.0
    assert v["severity"] == "informational"


# ----------------------------------------------------------------------
# Rate pair — fires from get_dp_quality_gauges-style observations.
# ----------------------------------------------------------------------

def test_rate_pair_fires_with_window_kind_rate():
    verdicts = evaluate_upf_directional_rule({
        "upf_in_pps": 8.9, "upf_out_pps": 6.8,
    })
    assert len(verdicts) == 1
    v = verdicts[0]
    assert v["window_kind"] == "rate"
    assert v["in_key"] == "upf_in_pps"
    assert v["out_key"] == "upf_out_pps"
    assert v["in_total"] == 8.9
    assert v["out_total"] == 6.8


def test_rate_failing_scenario_is_informational_at_23_6_pct():
    """The canonical failing-scenario rate values from
    run_20260502_172113. 8.9 vs 6.8 is 23.6% asymmetry — below the
    30% threshold, so informational severity. The agent has been
    misreading this as 'UPF dropping ~24% of packets' for two months."""
    verdicts = evaluate_upf_directional_rule({
        "upf_in_pps": 8.9, "upf_out_pps": 6.8,
    })
    v = verdicts[0]
    assert v["asymmetry_pct"] == 23.6
    assert v["severity"] == "informational"
    # Verdict text must explicitly forbid reading this as loss.
    assert "loss" in v["verdict"].lower()
    assert "rate window" in v["verdict"]


def test_rate_high_asymmetry_is_high_temptation():
    """66.7% asymmetry — uplink-heavy data session shape."""
    verdicts = evaluate_upf_directional_rule({
        "upf_in_pps": 12.0, "upf_out_pps": 4.0,
    })
    v = verdicts[0]
    assert v["asymmetry_pct"] == 66.7
    assert v["severity"] == "high_temptation"


# ----------------------------------------------------------------------
# Both pairs — fires twice, once per window_kind.
# ----------------------------------------------------------------------

def test_both_pairs_fire_two_verdicts():
    """When both cumulative and rate pairs are present, BOTH verdicts
    fire — the agent benefits from seeing the analysis on both
    surfaces. Confirmed: cumulative first, rate second (deterministic
    order so consumers can rely on it)."""
    verdicts = evaluate_upf_directional_rule({
        "fivegs_ep_n3_gtp_indatapktn3upf": 3423,
        "fivegs_ep_n3_gtp_outdatapktn3upf": 1267,
        "upf_in_pps": 8.9, "upf_out_pps": 6.8,
    })
    assert len(verdicts) == 2
    kinds = [v["window_kind"] for v in verdicts]
    assert kinds == ["cumulative", "rate"]
    assert verdicts[0]["asymmetry_pct"] == 63.0
    assert verdicts[1]["asymmetry_pct"] == 23.6


def test_both_pairs_have_distinct_severity_and_in_keys():
    verdicts = evaluate_upf_directional_rule({
        "fivegs_ep_n3_gtp_indatapktn3upf": 100,
        "fivegs_ep_n3_gtp_outdatapktn3upf": 100,
        "upf_in_pps": 50.0, "upf_out_pps": 5.0,
    })
    cumulative, rate = verdicts
    assert cumulative["asymmetry_pct"] == 0.0
    assert cumulative["severity"] == "informational"
    assert rate["asymmetry_pct"] == 90.0
    assert rate["severity"] == "high_temptation"


# ----------------------------------------------------------------------
# Edge cases — missing halves and non-numeric values must NOT crash.
# ----------------------------------------------------------------------

def test_missing_one_of_cumulative_pair_does_not_fire():
    verdicts = evaluate_upf_directional_rule({
        "fivegs_ep_n3_gtp_indatapktn3upf": 100,
    })
    assert verdicts == []


def test_missing_one_of_rate_pair_does_not_fire():
    verdicts = evaluate_upf_directional_rule({
        "upf_in_pps": 8.9,
    })
    assert verdicts == []


def test_empty_observations_does_not_fire():
    assert evaluate_upf_directional_rule({}) == []


@pytest.mark.parametrize("bad_value", ["string", None, [1, 2], {"x": 1}, True])
def test_non_numeric_values_do_not_fire_or_crash(bad_value):
    """Defensive: a non-numeric value in any of the four observation
    keys must NOT crash and must NOT fire the verdict for that pair."""
    verdicts = evaluate_upf_directional_rule({
        "fivegs_ep_n3_gtp_indatapktn3upf": bad_value,
        "fivegs_ep_n3_gtp_outdatapktn3upf": bad_value,
        "upf_in_pps": bad_value,
        "upf_out_pps": bad_value,
    })
    assert verdicts == []


def test_zero_zero_pair_fires_with_zero_asymmetry():
    """Edge case: both values zero. asymmetry is defined as 0%; the
    rule still fires (educational value is always relevant — the
    point is to teach the agent that subtraction is invalid, not to
    only fire on suspicious shapes)."""
    verdicts = evaluate_upf_directional_rule({
        "upf_in_pps": 0.0, "upf_out_pps": 0.0,
    })
    assert len(verdicts) == 1
    v = verdicts[0]
    assert v["asymmetry_pct"] == 0.0
    assert v["severity"] == "informational"


# ----------------------------------------------------------------------
# Rule prose — loaded from stack_rules.yaml.
# ----------------------------------------------------------------------

def test_verdict_carries_rule_prose_from_yaml():
    """The verdict dict must include the prose fields (rule,
    implication, examples, invalidates, priority) loaded from
    stack_rules.yaml — same shape OntologyClient.check_stack_rules
    produces from Neo4j today."""
    verdicts = evaluate_upf_directional_rule({
        "upf_in_pps": 8.9, "upf_out_pps": 6.8,
    })
    v = verdicts[0]
    assert v["id"] == "upf_counters_are_directional"
    assert "rule" in v and isinstance(v["rule"], str) and len(v["rule"]) > 50
    assert "implication" in v
    assert "examples" in v and len(v["examples"]) >= 1
    assert "priority" in v


def test_verdict_carries_three_correct_methods():
    """The correct_methods list must always contain three entries:
    same-direction rate, RTCP loss_ratio, tc qdisc drops."""
    verdicts = evaluate_upf_directional_rule({
        "upf_in_pps": 8.9, "upf_out_pps": 6.8,
    })
    v = verdicts[0]
    methods = v["correct_methods"]
    assert len(methods) == 3
    text = " ".join(methods).lower()
    assert "same-direction" in text or "same direction" in text
    assert "rtcp" in text
    assert "tc qdisc" in text


def test_explicit_rule_prose_override_used_when_provided():
    """When a caller passes rule_prose explicitly (the
    OntologyClient delegation path passes Neo4j-loaded prose), the
    evaluator uses it instead of re-reading the YAML."""
    custom = {"id": "upf_counters_are_directional", "rule": "FROM-NEO4J"}
    verdicts = evaluate_upf_directional_rule(
        {"upf_in_pps": 8.9, "upf_out_pps": 6.8},
        rule_prose=custom,
    )
    assert verdicts[0]["rule"] == "FROM-NEO4J"
