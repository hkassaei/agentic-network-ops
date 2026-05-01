"""Unit tests for guardrails/ig_validator.lint_ig_plan — Decision A, PR 4.

A1 = partner-probe / triangulation coverage on compositional probes.
A2 = mechanism-scoping linter on expected_if_hypothesis_holds and
     falsifying_observation text.

Pure-Python tests over Pydantic-typed plan objects. No ADK runtime, no
Gemini calls.

The fan-out audit is tested separately in
test_orchestrator_helpers.py (predates the ig_validator module split).
"""

from __future__ import annotations

import pytest

from agentic_ops_v6.guardrails.base import GuardrailVerdict
from agentic_ops_v6.guardrails.ig_validator import lint_ig_plan
from agentic_ops_v6.models import (
    FalsificationPlan,
    FalsificationPlanSet,
    FalsificationProbe,
)


# ---------------------------------------------------------------------------
# Test fixture builders
# ---------------------------------------------------------------------------

def _probe(
    *,
    tool: str = "get_dp_quality_gauges",
    args_hint: str = "window_seconds=120",
    expected: str = "The metric stays at its healthy baseline.",
    falsifying: str = "The metric deviates from baseline.",
    conflates_with: list[str] | None = None,
) -> FalsificationProbe:
    return FalsificationProbe(
        tool=tool,
        args_hint=args_hint,
        expected_if_hypothesis_holds=expected,
        falsifying_observation=falsifying,
        conflates_with=conflates_with if conflates_with is not None else [],
    )


def _plan(
    *,
    hid: str = "h1",
    nf: str = "upf",
    statement: str = "test hypothesis statement",
    probes: list[FalsificationProbe] | None = None,
) -> FalsificationPlan:
    if probes is None:
        # Default = clean, two non-compositional probes (passes A1 + A2)
        probes = [_probe(), _probe()]
    return FalsificationPlan(
        hypothesis_id=hid,
        hypothesis_statement=statement,
        primary_suspect_nf=nf,
        probes=probes,
    )


def _plan_set(*plans: FalsificationPlan) -> FalsificationPlanSet:
    return FalsificationPlanSet(plans=list(plans))


# ---------------------------------------------------------------------------
# PASS path — clean plan
# ---------------------------------------------------------------------------

def test_clean_plan_passes():
    plan_set = _plan_set(_plan())
    result = lint_ig_plan(plan_set)
    assert result.verdict is GuardrailVerdict.PASS
    assert result.output is plan_set


def test_clean_compositional_pair_passes():
    """Two measure_rtt probes targeting the same NF from different sources,
    both with non-empty conflates_with → A1 partner-probe coverage met."""
    plan_set = _plan_set(_plan(probes=[
        _probe(
            tool="measure_rtt",
            args_hint="from='nr_gnb', to_ip='upf'",
            expected="Loss observed on the gNB→UPF path.",
            falsifying="Loss not observed on this path.",
            conflates_with=["the path between gNB and UPF", "gNB egress"],
        ),
        _probe(
            tool="measure_rtt",
            args_hint="from='amf', to_ip='upf'",
            expected="Loss observed on the AMF→UPF path.",
            falsifying="Loss not observed on this path.",
            conflates_with=["the path between AMF and UPF", "AMF egress"],
        ),
    ]))
    result = lint_ig_plan(plan_set)
    assert result.verdict is GuardrailVerdict.PASS


# ---------------------------------------------------------------------------
# A1 — Partner-probe coverage
# ---------------------------------------------------------------------------

def test_a1_compositional_probe_with_empty_conflates_with_rejects():
    plan_set = _plan_set(_plan(probes=[
        _probe(
            tool="measure_rtt",
            args_hint="from='nr_gnb', to_ip='upf'",
            conflates_with=[],
        ),
        _probe(),
    ]))
    result = lint_ig_plan(plan_set)
    assert result.verdict is GuardrailVerdict.REJECT
    findings = result.notes["per_probe"]
    assert len(findings) == 1
    assert findings[0]["missing_conflates_with"] is True
    assert findings[0]["no_partner_probe"] is False
    assert "[A1]" in result.reason
    assert "empty `conflates_with`" in result.reason


def test_a1_compositional_probe_without_partner_rejects():
    """One measure_rtt with conflates_with set, but no second compositional
    probe in the plan to disambiguate."""
    plan_set = _plan_set(_plan(probes=[
        _probe(
            tool="measure_rtt",
            args_hint="from='nr_gnb', to_ip='upf'",
            conflates_with=["the path between gNB and UPF"],
        ),
        _probe(tool="get_dp_quality_gauges"),  # not compositional
    ]))
    result = lint_ig_plan(plan_set)
    assert result.verdict is GuardrailVerdict.REJECT
    findings = result.notes["per_probe"]
    assert len(findings) == 1
    assert findings[0]["no_partner_probe"] is True
    assert "no partner probe" in result.reason.lower()


def test_a1_two_compositional_probes_with_conflates_with_pass():
    plan_set = _plan_set(_plan(probes=[
        _probe(
            tool="measure_rtt",
            args_hint="from='nr_gnb', to_ip='upf'",
            conflates_with=["the gNB→UPF path"],
        ),
        _probe(
            tool="measure_rtt",
            args_hint="from='amf', to_ip='upf'",
            conflates_with=["the AMF→UPF path"],
        ),
    ]))
    result = lint_ig_plan(plan_set)
    assert result.verdict is GuardrailVerdict.PASS


# ---------------------------------------------------------------------------
# A2 — IG-statement mechanism-scoping linter
# ---------------------------------------------------------------------------

def test_a2_internal_fault_in_falsifying_rejects():
    """The exact phrase from run_20260501_012613_data_plane_degradation."""
    plan_set = _plan_set(_plan(probes=[
        _probe(
            tool="measure_rtt",
            args_hint="from='nr_gnb', to_ip='upf'",
            expected="Low RTT and no packet loss.",
            falsifying=(
                "High RTT or packet loss, which would point to a transport "
                "network issue on the N3 path rather than a UPF-internal fault."
            ),
            conflates_with=["the gNB→UPF path"],
        ),
        _probe(
            tool="measure_rtt",
            args_hint="from='amf', to_ip='upf'",
            expected="Low RTT and no packet loss.",
            falsifying="No deviation observed.",
            conflates_with=["the AMF→UPF path"],
        ),
    ]))
    result = lint_ig_plan(plan_set)
    assert result.verdict is GuardrailVerdict.REJECT
    findings = result.notes["per_probe"]
    # Only the first probe's falsifying text is dirty; second is clean
    assert len(findings) == 1
    f = findings[0]
    assert f["probe_index"] == 0
    assert "upf-internal fault" in f["falsifying_hits"]
    assert "internal fault" in f["falsifying_hits"]
    assert "internal" in f["falsifying_hits"]
    assert "[A2]" in result.reason
    assert "UPF-internal fault" in result.reason


@pytest.mark.parametrize("bad_phrase", [
    "The drop is at the application-layer of UPF.",
    "process-level packet handling is broken.",
    "user-space-only loss.",
    "kernel-only drop pattern.",
    "transport-only path issue.",
    "RTPEngine has an internal fault.",
    "UPF crashed.",
    "PCSCF is not running.",
    "AMF is not forwarding.",
    "S-CSCF is misconfigured.",
])
def test_a2_various_mechanism_scope_phrases_reject(bad_phrase: str):
    plan_set = _plan_set(_plan(probes=[
        _probe(falsifying=bad_phrase),
        _probe(),
    ]))
    result = lint_ig_plan(plan_set)
    assert result.verdict is GuardrailVerdict.REJECT, (
        f"Expected REJECT for: {bad_phrase!r}"
    )


def test_a2_expected_field_also_scanned():
    plan_set = _plan_set(_plan(probes=[
        _probe(
            expected="UPF crashed and is no longer forwarding packets.",
            falsifying="Counter increments normally.",
        ),
        _probe(),
    ]))
    result = lint_ig_plan(plan_set)
    assert result.verdict is GuardrailVerdict.REJECT
    f = result.notes["per_probe"][0]
    assert f["expected_hits"]  # has hits
    assert not f["falsifying_hits"]  # clean


def test_a2_clean_text_does_not_false_positive():
    clean_phrases = [
        "Counter increments normally.",
        "The packet rate matches the baseline window.",
        "Loss is observed on a path that does not traverse UPF.",
    ]
    for phrase in clean_phrases:
        plan_set = _plan_set(_plan(probes=[
            _probe(falsifying=phrase),
            _probe(),
        ]))
        result = lint_ig_plan(plan_set)
        assert result.verdict is GuardrailVerdict.PASS, (
            f"Expected PASS for: {phrase!r}"
        )


# ---------------------------------------------------------------------------
# Combined A1 + A2 — multi-plan, multi-probe
# ---------------------------------------------------------------------------

def test_multi_plan_groups_findings_by_plan():
    plan_set = _plan_set(
        _plan(
            hid="h1", nf="upf",
            probes=[
                _probe(
                    tool="measure_rtt",
                    args_hint="from='nr_gnb', to_ip='upf'",
                    falsifying="High loss → UPF-internal fault.",
                    conflates_with=["gNB→UPF path"],
                ),
                _probe(
                    tool="measure_rtt",
                    args_hint="from='amf', to_ip='upf'",
                    conflates_with=["AMF→UPF path"],
                ),
            ],
        ),
        _plan(
            hid="h2", nf="rtpengine",
            probes=[_probe(), _probe()],  # clean
        ),
        _plan(
            hid="h3", nf="pyhss",
            probes=[
                _probe(
                    tool="measure_rtt",
                    args_hint="from='icscf', to_ip='pyhss'",
                    conflates_with=[],  # A1: empty conflates_with on compositional
                ),
                _probe(),
            ],
        ),
    )
    result = lint_ig_plan(plan_set)
    assert result.verdict is GuardrailVerdict.REJECT
    # Both flagged plans appear; clean plan does not
    assert "`h1`" in result.reason
    assert "`h3`" in result.reason
    assert "`h2`" not in result.reason
    # Two distinct findings, one per flagged plan
    assert result.notes["flagged_probes_count"] == 2


def test_reason_includes_per_probe_example_correction():
    plan_set = _plan_set(_plan(probes=[
        _probe(falsifying="UPF crashed."),
        _probe(),
    ]))
    result = lint_ig_plan(plan_set)
    assert result.verdict is GuardrailVerdict.REJECT
    # Bad example quotes the actual offending text
    assert "Bad:" in result.reason
    assert "UPF crashed." in result.reason
    # Good example is grounded on the plan's NF (upf)
    assert "Good:" in result.reason
    assert "upf" in result.reason.lower()


def test_reason_includes_a1_and_a2_explanation():
    """The rejection reason teaches IG about both sub-checks even when
    only one fired — IG benefits from seeing the full contract."""
    plan_set = _plan_set(_plan(probes=[
        _probe(falsifying="The N3 path has an internal fault."),
        _probe(),
    ]))
    result = lint_ig_plan(plan_set)
    assert "(A1)" in result.reason
    assert "(A2)" in result.reason


# ---------------------------------------------------------------------------
# Notes payload — recorder-friendly structure
# ---------------------------------------------------------------------------

def test_notes_structure_is_recorder_friendly():
    plan_set = _plan_set(_plan(probes=[
        _probe(
            tool="measure_rtt",
            args_hint="from='nr_gnb', to_ip='upf'",
            falsifying="UPF-internal fault.",
            conflates_with=[],
        ),
        _probe(),
    ]))
    result = lint_ig_plan(plan_set)
    assert isinstance(result.notes, dict)
    assert result.notes["flagged_probes_count"] == 1
    rows = result.notes["per_probe"]
    assert len(rows) == 1
    row = rows[0]
    assert row["plan_id"] == "h1"
    assert row["plan_nf"] == "upf"
    assert row["probe_index"] == 0
    assert row["tool"] == "measure_rtt"
    assert row["missing_conflates_with"] is True  # A1 finding
    assert row["falsifying_hits"]  # A2 finding
