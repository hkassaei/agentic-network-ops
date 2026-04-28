"""Unit tests for the v6 orchestrator's pure-Python helpers.

Tests the parts that don't require an LLM / ADK runtime: hypothesis
ranking + capping, NA/plan parsing, diagnosis rendering when no
hypotheses available.
"""

from __future__ import annotations

import json

import pytest

from agentic_ops_v6.models import (
    FalsificationPlan,
    FalsificationPlanSet,
    Hypothesis,
    NetworkAnalystReport,
    InvestigatorVerdict,
)
from agentic_ops_v6.orchestrator import (
    MAX_PARALLEL_INVESTIGATORS,
    _parse_network_analysis,
    _parse_plan_set,
    _pretty_print_na_report,
    _rank_and_cap_hypotheses,
    _render_no_hypotheses_diagnosis,
)


# ============================================================================
# Hypothesis ranking
# ============================================================================

def test_rank_drops_untestable():
    # The schema now requires `falsification_probes` to be non-empty,
    # so a probe-less Hypothesis can't be constructed via normal
    # validation. The orchestrator's defensive filter still exists
    # in case the empty-sentinel path (model_construct) lets one
    # through. Test that the filter still drops it.
    h_testable = Hypothesis(
        id="h1", statement="testable", primary_suspect_nf="amf",
        explanatory_fit=0.9,
        falsification_probes=["probe1"],
    )
    h_untestable = Hypothesis.model_construct(
        id="h2", statement="untestable", primary_suspect_nf="amf",
        explanatory_fit=0.99, falsification_probes=[], specificity="moderate",
        supporting_events=[],
    )
    ranked = _rank_and_cap_hypotheses([h_testable, h_untestable])
    assert len(ranked) == 1
    assert ranked[0].id == "h1"


def test_rank_orders_by_fit():
    hypotheses = [
        Hypothesis(
            id="h1", statement="low_fit", primary_suspect_nf="amf",
            explanatory_fit=0.3,
            falsification_probes=["probe1", "probe2"],
        ),
        Hypothesis(
            id="h2", statement="high_fit", primary_suspect_nf="icscf",
            explanatory_fit=0.9,
            falsification_probes=["probe1"],
        ),
    ]
    ranked = _rank_and_cap_hypotheses(hypotheses)
    assert [h.id for h in ranked] == ["h2", "h1"]


def test_rank_caps_at_max():
    hypotheses = [
        Hypothesis(
            id=f"h{i}", statement=f"h{i}", primary_suspect_nf="amf",
            explanatory_fit=0.9 - i * 0.1,
            falsification_probes=["p"],
        )
        for i in range(5)  # 5 hypotheses
    ]
    ranked = _rank_and_cap_hypotheses(hypotheses)
    assert len(ranked) == MAX_PARALLEL_INVESTIGATORS


def test_rank_tiebreaks_on_probe_count():
    """Equal fit — more probes wins."""
    hypotheses = [
        Hypothesis(
            id="h_few", statement="few probes", primary_suspect_nf="amf",
            explanatory_fit=0.5,
            falsification_probes=["p1"],
        ),
        Hypothesis(
            id="h_many", statement="many probes", primary_suspect_nf="icscf",
            explanatory_fit=0.5,
            falsification_probes=["p1", "p2", "p3"],
        ),
    ]
    ranked = _rank_and_cap_hypotheses(hypotheses)
    assert ranked[0].id == "h_many"


def test_rank_tiebreaks_on_specificity():
    """Equal fit + probes — specific beats moderate beats vague."""
    hypotheses = [
        Hypothesis(
            id="h_vague", statement="x", primary_suspect_nf="amf",
            explanatory_fit=0.5, falsification_probes=["p"],
            specificity="vague",
        ),
        Hypothesis(
            id="h_specific", statement="x", primary_suspect_nf="amf",
            explanatory_fit=0.5, falsification_probes=["p"],
            specificity="specific",
        ),
    ]
    ranked = _rank_and_cap_hypotheses(hypotheses)
    assert ranked[0].id == "h_specific"


# ============================================================================
# Parsing
# ============================================================================

def test_parse_network_analysis_from_dict():
    data = {
        "summary": "All layers check",
        "layer_status": {"core": {"rating": "green", "note": "fine"}},
        "hypotheses": [
            {
                "id": "h1",
                "statement": "A",
                "primary_suspect_nf": "amf",
                "explanatory_fit": 0.7,
                "falsification_probes": ["p"],
                "specificity": "specific",
            }
        ],
    }
    report = _parse_network_analysis(data)
    assert report.summary == "All layers check"
    assert len(report.hypotheses) == 1


def test_parse_network_analysis_from_json_string():
    # Tightened schema requires `summary` non-empty and `hypotheses`
    # min_length=1, so the fixture supplies a minimal valid hypothesis.
    data = {
        "summary": "X",
        "layer_status": {},
        "hypotheses": [
            {
                "id": "h1",
                "statement": "test",
                "primary_suspect_nf": "amf",
                "falsification_probes": ["p"],
            }
        ],
    }
    report = _parse_network_analysis(json.dumps(data))
    assert report.summary == "X"
    assert len(report.hypotheses) == 1


def test_parse_network_analysis_handles_garbage():
    """Bad input should yield the empty sentinel, not crash."""
    report = _parse_network_analysis("not a json string")
    # Sentinel uses model_construct, sets summary to an unparseable
    # message and `hypotheses=[]` so downstream skips Phase 4 cleanly.
    assert "unparseable" in report.summary
    assert report.hypotheses == []


def test_parse_network_analysis_handles_schema_violation():
    """Empty hypotheses list violates the new min_length=1 constraint —
    helper must catch and return the empty sentinel rather than crash."""
    report = _parse_network_analysis({"summary": "x", "hypotheses": []})
    assert report.hypotheses == []
    # Summary should reflect that something went wrong, not be ""
    assert report.summary != ""


def test_parse_network_analysis_handles_none():
    """Missing input → empty sentinel (orchestrator's first-call case)."""
    report = _parse_network_analysis(None)
    assert report.hypotheses == []
    assert report.summary != ""


def test_parse_plan_set_from_dict():
    # The schema now requires >= 2 probes per plan and a recognized NF.
    # Use a minimally-valid shape so this test stays focused on the
    # dict->model deserialization path, not on schema constraints
    # (those are covered by tests in test_wiring.py).
    probe = {
        "tool": "measure_rtt",
        "args_hint": "amf → icscf",
        "expected_if_hypothesis_holds": "100% loss",
        "falsifying_observation": "clean RTT",
    }
    data = {"plans": [
        {
            "hypothesis_id": "h1",
            "hypothesis_statement": "test",
            "primary_suspect_nf": "amf",
            "probes": [probe, probe],
            "notes": "",
        },
    ]}
    ps = _parse_plan_set(data)
    assert len(ps.plans) == 1
    assert ps.plans[0].hypothesis_id == "h1"
    assert len(ps.plans[0].probes) == 2


def test_parse_plan_set_empty_on_missing():
    # `_parse_plan_set(None)` must still give the orchestrator an
    # iterable `.plans` it can treat as "no plan generated" without
    # blowing up on the tightened schema's min_length=1 constraint.
    # The sentinel uses model_construct to bypass validation.
    ps = _parse_plan_set(None)
    assert ps.plans == []


def test_parse_plan_set_empty_on_invalid_input():
    # IG flop case: state contains something non-parseable. The helper
    # must swallow the error and return the empty sentinel, exactly as
    # for the None case, so Phase 5 can proceed.
    ps = _parse_plan_set("not-valid-json {")
    assert ps.plans == []
    ps = _parse_plan_set({"plans": "malformed"})
    assert ps.plans == []


# ============================================================================
# Rendering
# ============================================================================

def test_pretty_print_na_report_includes_all_hypotheses():
    hs = [
        Hypothesis(
            id="h1", statement="first hyp", primary_suspect_nf="amf",
            explanatory_fit=0.9, falsification_probes=["p1", "p2"],
        ),
        Hypothesis(
            id="h2", statement="second hyp", primary_suspect_nf="icscf",
            explanatory_fit=0.6, falsification_probes=["p3"],
        ),
    ]
    # NA report must include the hypotheses to satisfy schema (min_length=1).
    na = NetworkAnalystReport(summary="summary text", hypotheses=hs)
    text = _pretty_print_na_report(na, hs)
    assert "first hyp" in text
    assert "second hyp" in text
    assert "summary text" in text
    assert "h1" in text and "h2" in text


def test_no_hypotheses_diagnosis_is_structured():
    """The no-hypotheses fallback produces valid markdown fields. The
    NA sentinel uses model_construct because the live schema requires
    >= 1 hypothesis; this test exercises the rendering of that
    sentinel."""
    na = NetworkAnalystReport.model_construct(
        summary="saw nothing", layer_status={}, hypotheses=[],
    )
    text = _render_no_hypotheses_diagnosis(na)
    assert "**summary**" in text
    assert "**root_cause**" in text
    assert "**confidence**: low" in text
