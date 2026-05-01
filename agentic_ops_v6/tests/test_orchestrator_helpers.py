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


# ============================================================================
# Sub-Investigator state plumbing — regression for the
# "Context variable not found: anomaly_screener_snapshot_ts" crash that
# took out all 3 sub-Investigators in
# run_20260429_233451_call_quality_degradation. The orchestrator's
# top-level state initialized the sentinel keys, but
# `_run_parallel_investigators` built a fresh `sub_state` dict that
# omitted them, so the prompt template
# `{anomaly_screener_snapshot_ts}` failed to resolve.
# ============================================================================

def test_run_parallel_investigators_signature_carries_anomaly_timestamps():
    """The function must accept the three anomaly-window timestamps as
    forwardable kwargs. Locks in the contract that the orchestrator
    can pass them through to sub-state."""
    import inspect

    from agentic_ops_v6.orchestrator import _run_parallel_investigators

    sig = inspect.signature(_run_parallel_investigators)
    for name in (
        "anomaly_window_start_ts",
        "anomaly_window_end_ts",
        "anomaly_screener_snapshot_ts",
    ):
        assert name in sig.parameters, (
            f"_run_parallel_investigators must accept {name} so the "
            f"investigator prompt's `{{{name}}}` template can resolve"
        )


# ============================================================================
# Phase 5 fan-out audit — surfaces silent plan-drops + NF mismatches
# ============================================================================
#
# Regression for run_20260430_013055_gnb_radio_link_failure: NA produced
# 1 hypothesis (h1 nr_gnb), IG produced 3 plans (h1, h2, h3 — re-anchored
# on the correlation engine's hypotheses, all targeting amf instead of
# nr_gnb). Orchestrator silently dropped 2 plans and ran the remaining
# investigator against a cross-NF-mismatched plan. None of this was
# logged. The audit added in `_run_parallel_investigators` records all
# three failure modes both to the live log AND as a Phase5FanOutAudit
# trace in the recorded report.

@pytest.mark.asyncio
async def test_fan_out_audit_records_clean_run_with_all_matched(monkeypatch):
    """When NA and IG agree on hypothesis ids and NF targets, the
    audit records a clean summary with output_summary='all matched'."""
    from agentic_ops_v6 import orchestrator as orch

    async def fake_run_phase(agent, state, question, session_service, on_event=None):
        verdict = {
            "hypothesis_id": state["hypothesis_id"],
            "hypothesis_statement": state["hypothesis_statement"],
            "verdict": "INCONCLUSIVE",
            "reasoning": "stub",
        }
        return ({**state, "investigator_verdict": json.dumps(verdict)}, [])

    monkeypatch.setattr(orch, "_run_phase", fake_run_phase)
    monkeypatch.setattr(orch, "create_investigator_agent", lambda name=None: object())

    h = Hypothesis(
        id="h1", statement="UPF drop", primary_suspect_nf="upf",
        falsification_probes=["p1"],
    )
    probe = {
        "tool": "get_dp_quality_gauges", "args_hint": "x",
        "expected_if_hypothesis_holds": "y", "falsifying_observation": "z",
    }
    plan = FalsificationPlan(
        hypothesis_id="h1", hypothesis_statement="UPF drop",
        primary_suspect_nf="upf", probes=[probe, probe],
    )
    all_phases: list = []

    await orch._run_parallel_investigators(
        hypotheses=[h], plans=[plan],
        network_analysis_text="na", session_service=None,
        all_phases=all_phases,
    )

    audit_traces = [t for t in all_phases if t.agent_name == "Phase5FanOutAudit"]
    assert len(audit_traces) == 1
    assert audit_traces[0].output_summary == "all matched"


@pytest.mark.asyncio
async def test_fan_out_audit_flags_silently_dropped_plans(monkeypatch):
    """Reproduces the gnb-run pattern: NA produces 1 hypothesis (h1),
    IG produces 3 plans (h1, h2, h3). Plans h2 and h3 have no matching
    hypothesis and were silently dropped before this audit was added.
    The audit must surface both dropped ids."""
    from agentic_ops_v6 import orchestrator as orch

    async def fake_run_phase(agent, state, question, session_service, on_event=None):
        verdict = {
            "hypothesis_id": state["hypothesis_id"],
            "hypothesis_statement": state["hypothesis_statement"],
            "verdict": "INCONCLUSIVE",
            "reasoning": "stub",
        }
        return ({**state, "investigator_verdict": json.dumps(verdict)}, [])

    monkeypatch.setattr(orch, "_run_phase", fake_run_phase)
    monkeypatch.setattr(orch, "create_investigator_agent", lambda name=None: object())

    h = Hypothesis(
        id="h1", statement="gNB down", primary_suspect_nf="nr_gnb",
        falsification_probes=["p1"],
    )
    probe = {
        "tool": "get_network_status", "args_hint": "x",
        "expected_if_hypothesis_holds": "y", "falsifying_observation": "z",
    }
    plans = [
        FalsificationPlan(
            hypothesis_id=hid, hypothesis_statement=stmt,
            primary_suspect_nf="nr_gnb", probes=[probe, probe],
        )
        for hid, stmt in [
            ("h1", "gNB down"), ("h2", "extra plan"), ("h3", "another extra"),
        ]
    ]
    all_phases: list = []

    await orch._run_parallel_investigators(
        hypotheses=[h], plans=plans,
        network_analysis_text="na", session_service=None,
        all_phases=all_phases,
    )

    audit_traces = [t for t in all_phases if t.agent_name == "Phase5FanOutAudit"]
    assert len(audit_traces) == 1
    summary = audit_traces[0].output_summary
    assert "DROPPED PLANS" in summary
    assert "h2" in summary and "h3" in summary
    assert "h1" not in summary.split("DROPPED PLANS")[1]  # h1 is matched


@pytest.mark.asyncio
async def test_fan_out_audit_flags_nf_mismatch(monkeypatch):
    """The other half of the gnb-run pattern: hypothesis names nr_gnb
    but the matching plan targets amf. The audit surfaces the
    mismatch so the recorded report makes the cross-NF probe pairing
    visible."""
    from agentic_ops_v6 import orchestrator as orch

    async def fake_run_phase(agent, state, question, session_service, on_event=None):
        verdict = {
            "hypothesis_id": state["hypothesis_id"],
            "hypothesis_statement": state["hypothesis_statement"],
            "verdict": "INCONCLUSIVE",
            "reasoning": "stub",
        }
        return ({**state, "investigator_verdict": json.dumps(verdict)}, [])

    monkeypatch.setattr(orch, "_run_phase", fake_run_phase)
    monkeypatch.setattr(orch, "create_investigator_agent", lambda name=None: object())

    h = Hypothesis(
        id="h1", statement="gNB down", primary_suspect_nf="nr_gnb",
        falsification_probes=["p1"],
    )
    probe = {
        "tool": "get_network_status", "args_hint": "x",
        "expected_if_hypothesis_holds": "y", "falsifying_observation": "z",
    }
    plan = FalsificationPlan(
        hypothesis_id="h1", hypothesis_statement="Total RAN outage",
        primary_suspect_nf="amf",  # mismatch with hypothesis's nr_gnb
        probes=[probe, probe],
    )
    all_phases: list = []

    await orch._run_parallel_investigators(
        hypotheses=[h], plans=[plan],
        network_analysis_text="na", session_service=None,
        all_phases=all_phases,
    )

    audit_traces = [t for t in all_phases if t.agent_name == "Phase5FanOutAudit"]
    assert len(audit_traces) == 1
    summary = audit_traces[0].output_summary
    assert "NF MISMATCH" in summary
    assert "nr_gnb" in summary and "amf" in summary
    assert "h1" in summary


@pytest.mark.asyncio
async def test_sub_investigator_state_includes_anomaly_timestamps(monkeypatch):
    """End-to-end: _run_parallel_investigators must seed the three
    timestamp keys into each sub-Investigator's session state so the
    prompt template resolves. We stub the underlying `_run_phase` to
    capture the `sub_state` dict it's called with and assert the keys
    are present."""
    from agentic_ops_v6 import orchestrator as orch

    captured_states: list[dict] = []

    async def fake_run_phase(agent, state, question, session_service, on_event=None):
        captured_states.append(dict(state))
        # Return a verdict the orchestrator's parser will accept.
        verdict = {
            "hypothesis_id": state["hypothesis_id"],
            "hypothesis_statement": state["hypothesis_statement"],
            "verdict": "INCONCLUSIVE",
            "reasoning": "stub",
        }
        return ({**state, "investigator_verdict": json.dumps(verdict)}, [])

    monkeypatch.setattr(orch, "_run_phase", fake_run_phase)
    monkeypatch.setattr(
        orch, "create_investigator_agent",
        lambda name=None: object(),  # placeholder; not exercised by stub
    )

    h = Hypothesis(
        id="h1",
        statement="UPF transient drop",
        primary_suspect_nf="upf",
        fit=0.9,
        specificity="specific",
        supporting_event_ids=[],
        falsification_probes=["check N3 vs N6"],
    )
    probe = {
        "tool": "get_dp_quality_gauges",
        "args_hint": "window_seconds=60",
        "expected_if_hypothesis_holds": "x",
        "falsifying_observation": "y",
    }
    plan = FalsificationPlan(
        hypothesis_id="h1",
        hypothesis_statement="UPF transient drop",
        primary_suspect_nf="upf",
        probes=[probe, probe],  # >= 2 required
        notes="",
    )

    await orch._run_parallel_investigators(
        hypotheses=[h],
        plans=[plan],
        network_analysis_text="na",
        session_service=None,  # not used by the stub
        all_phases=[],
        anomaly_window_start_ts=1777505000.0,
        anomaly_window_end_ts=1777505030.0,
        anomaly_screener_snapshot_ts=1777505020.0,
    )

    assert len(captured_states) == 1
    state = captured_states[0]
    assert state["anomaly_window_start_ts"] == 1777505000.0
    assert state["anomaly_window_end_ts"] == 1777505030.0
    assert state["anomaly_screener_snapshot_ts"] == 1777505020.0


# ============================================================================
# Bug fix (PR 9.5) — min-tool-call guardrail aggregates across retries
# ============================================================================


@pytest.mark.asyncio
async def test_min_tool_call_aggregates_across_retry_attempts(monkeypatch):
    """Pre-PR-9.5 bug: when an Investigator's first attempt produced
    empty output (0 tool calls) and the retry succeeded with ≥2 tool
    calls, the min-tool-call guardrail used `next(...)` over the trace
    list and grabbed the FIRST matching trace (the failed-empty
    attempt). It then forced INCONCLUSIVE despite the retry's
    successful probes.

    This test simulates that exact scenario: stub `_run_phase` to
    return an empty-output trace on attempt 1 and a 3-tool-call trace
    on attempt 2. Verify the guardrail does NOT force INCONCLUSIVE.

    Caught by run_20260501_042127_call_quality_degradation: h1's
    Investigator made 0 calls on attempt 1 + 3 on attempt 2 but was
    incorrectly forced INCONCLUSIVE.
    """
    from agentic_ops_common.models import PhaseTrace, ToolCallTrace
    from agentic_ops_v6 import orchestrator as orch

    call_count = [0]

    async def fake_run_phase(agent, state, question, session_service, on_event=None):
        call_count[0] += 1
        agent_name = "InvestigatorAgent_h1"
        if call_count[0] == 1:
            # Attempt 1: empty-output silent-bail. _run_phase returns
            # successfully but doesn't write the output_key. The retry
            # helper should detect this and try again.
            trace = PhaseTrace(
                agent_name=agent_name,
                started_at=0.0,
                finished_at=0.0,
                duration_ms=0,
                tool_calls=[],  # 0 tool calls
            )
            # Don't write investigator_verdict — the empty-output
            # detector will see a missing key and trigger retry.
            return (state, [trace])
        # Attempt 2: real verdict + 3 tool calls
        verdict = {
            "hypothesis_id": state["hypothesis_id"],
            "hypothesis_statement": state["hypothesis_statement"],
            "verdict": "NOT_DISPROVEN",
            "reasoning": "stub retry success",
        }
        trace = PhaseTrace(
            agent_name=agent_name,
            started_at=1.0,
            finished_at=2.0,
            duration_ms=1000,
            tool_calls=[
                ToolCallTrace(name=f"probe_{i}", args="{}", timestamp=1.0)
                for i in range(3)
            ],
        )
        new_state = {**state, "investigator_verdict": json.dumps(verdict)}
        return (new_state, [trace])

    monkeypatch.setattr(orch, "_run_phase", fake_run_phase)
    monkeypatch.setattr(
        orch, "create_investigator_agent",
        lambda name=None: object(),
    )

    h = Hypothesis(
        id="h1",
        statement="UPF transient drop",
        primary_suspect_nf="upf",
        explanatory_fit=0.9,
        specificity="specific",
        supporting_events=[],
        falsification_probes=["check N3 vs N6"],
    )
    probe = {
        "tool": "get_dp_quality_gauges",
        "args_hint": "window_seconds=60",
        "expected_if_hypothesis_holds": "x",
        "falsifying_observation": "y",
    }
    plan = FalsificationPlan(
        hypothesis_id="h1",
        hypothesis_statement="UPF transient drop",
        primary_suspect_nf="upf",
        probes=[probe, probe],
        notes="",
    )

    verdicts = await orch._run_parallel_investigators(
        hypotheses=[h],
        plans=[plan],
        network_analysis_text="na",
        session_service=None,
        all_phases=[],
    )

    # The retry succeeded with 3 tool calls. Aggregated count is
    # 0 + 3 = 3, which is >= MIN_TOOL_CALLS_PER_INVESTIGATOR (2).
    # The guardrail should NOT force INCONCLUSIVE.
    assert len(verdicts) == 1
    assert verdicts[0].verdict == "NOT_DISPROVEN"
    assert "Mechanical guardrail" not in verdicts[0].reasoning


# ============================================================================
# PR 5.5b — Diagnosis report parsing + markdown rendering
# ============================================================================


def test_parse_diagnosis_report_from_dict():
    from agentic_ops_v6.orchestrator import _parse_diagnosis_report

    raw = {
        "summary": "test",
        "root_cause": "UPF is the source",
        "root_cause_confidence": "high",
        "primary_suspect_nf": "upf",
        "verdict_kind": "confirmed",
        "affected_components": [{"name": "upf", "role": "Root Cause"}],
        "timeline": ["event 1", "event 2"],
        "recommendation": "verify",
        "explanation": "because",
    }
    report = _parse_diagnosis_report(raw)
    assert report.primary_suspect_nf == "upf"
    assert report.verdict_kind == "confirmed"


def test_parse_diagnosis_report_from_json_string():
    from agentic_ops_v6.orchestrator import _parse_diagnosis_report

    raw = (
        '{"summary":"s","root_cause":"r","root_cause_confidence":"low",'
        '"primary_suspect_nf":null,"verdict_kind":"inconclusive",'
        '"affected_components":[],"timeline":[],"recommendation":"r",'
        '"explanation":"e"}'
    )
    report = _parse_diagnosis_report(raw)
    assert report.primary_suspect_nf is None
    assert report.verdict_kind == "inconclusive"


def test_parse_diagnosis_report_handles_none():
    from agentic_ops_v6.orchestrator import _parse_diagnosis_report

    report = _parse_diagnosis_report(None)
    # Sentinel: inconclusive + None — the only valid empty-pool combo.
    assert report.verdict_kind == "inconclusive"
    assert report.primary_suspect_nf is None


def test_parse_diagnosis_report_handles_garbage():
    from agentic_ops_v6.orchestrator import _parse_diagnosis_report

    report = _parse_diagnosis_report("not json {{{")
    assert report.verdict_kind == "inconclusive"


def test_parse_diagnosis_report_handles_schema_violation():
    """Unknown NF on `primary_suspect_nf` → ValidationError → sentinel."""
    from agentic_ops_v6.orchestrator import _parse_diagnosis_report

    raw = {
        "summary": "s",
        "root_cause": "r",
        "root_cause_confidence": "high",
        "primary_suspect_nf": "not_a_real_nf",
        "verdict_kind": "confirmed",
        "recommendation": "r",
        "explanation": "e",
    }
    report = _parse_diagnosis_report(raw)
    assert report.verdict_kind == "inconclusive"  # fell back to sentinel


def test_render_diagnosis_report_to_markdown_full_report():
    from agentic_ops_v6.models import DiagnosisReport
    from agentic_ops_v6.orchestrator import _render_diagnosis_report_to_markdown

    report = DiagnosisReport(
        summary="Severe data plane failure at UPF.",
        root_cause="UPF is dropping packets.",
        root_cause_confidence="high",
        primary_suspect_nf="upf",
        verdict_kind="confirmed",
        affected_components=[
            {"name": "upf", "role": "Root Cause"},
            {"name": "rtpengine", "role": "Symptomatic"},
        ],
        timeline=["UPF activity collapsed", "RTPEngine reports loss"],
        recommendation="Check UPF interfaces.",
        explanation="The h1 Investigator found packet drop at UPF.",
    )
    md = _render_diagnosis_report_to_markdown(report)
    # Required sections present
    assert "### causes" in md
    assert "**summary**" in md
    assert "**timeline**" in md
    assert "**root_cause**" in md
    assert "**affected_components**" in md
    assert "**recommendation**" in md
    assert "**confidence**" in md
    assert "**verdict_kind**" in md
    assert "**explanation**" in md
    # Content propagated correctly
    assert "Severe data plane failure" in md
    assert "primary_suspect_nf: `upf`" in md
    assert "1. UPF activity collapsed" in md
    assert "2. RTPEngine reports loss" in md
    assert "`upf`: Root Cause" in md
    assert "`rtpengine`: Symptomatic" in md


def test_render_diagnosis_report_to_markdown_inconclusive():
    from agentic_ops_v6.models import DiagnosisReport
    from agentic_ops_v6.orchestrator import _render_diagnosis_report_to_markdown

    report = DiagnosisReport(
        summary="Insufficient evidence.",
        root_cause="Inconclusive",
        root_cause_confidence="low",
        primary_suspect_nf=None,
        verdict_kind="inconclusive",
        affected_components=[],
        timeline=[],
        recommendation="Manual investigation.",
        explanation="All hypotheses disproven.",
    )
    md = _render_diagnosis_report_to_markdown(report)
    assert "**timeline**: []" in md
    assert "**affected_components**: []" in md
    # No primary_suspect_nf line when the field is None
    assert "primary_suspect_nf:" not in md
    assert "verdict_kind**: inconclusive" in md


# ============================================================================
# PR 6 — Multi-shot Investigator consensus integration
# ============================================================================


@pytest.mark.asyncio
async def test_multi_shot_two_agreeing_shots_produces_consensus(monkeypatch):
    """Stub _run_phase to return the SAME verdict on both calls; verify
    the reconciled output is the consensus verdict with merged
    reasoning ('Multi-shot consensus' marker)."""
    from agentic_ops_common.models import PhaseTrace, ToolCallTrace
    from agentic_ops_v6 import orchestrator as orch

    call_count = [0]

    async def fake_run_phase(agent, state, question, session_service, on_event=None):
        call_count[0] += 1
        agent_name = "InvestigatorAgent_h1"
        verdict = {
            "hypothesis_id": "h1",
            "hypothesis_statement": "UPF transient drop",
            "verdict": "NOT_DISPROVEN",
            "reasoning": f"shot {call_count[0]}: UPF dropping packets",
            "alternative_suspects": [],
        }
        trace = PhaseTrace(
            agent_name=agent_name,
            started_at=float(call_count[0]),
            finished_at=float(call_count[0]) + 1.0,
            duration_ms=1000,
            tool_calls=[
                ToolCallTrace(name="get_dp_quality_gauges", args="{}", timestamp=1.0),
                ToolCallTrace(name="measure_rtt", args="{}", timestamp=1.0),
            ],
        )
        return ({**state, "investigator_verdict": json.dumps(verdict)}, [trace])

    monkeypatch.setattr(orch, "_run_phase", fake_run_phase)
    monkeypatch.setattr(
        orch, "create_investigator_agent",
        lambda name=None: object(),
    )

    h = Hypothesis(
        id="h1", statement="UPF transient drop", primary_suspect_nf="upf",
        explanatory_fit=0.9, specificity="specific",
        supporting_events=[], falsification_probes=["check N3 vs N6"],
    )
    probe = {
        "tool": "get_dp_quality_gauges", "args_hint": "window_seconds=60",
        "expected_if_hypothesis_holds": "x", "falsifying_observation": "y",
    }
    plan = FalsificationPlan(
        hypothesis_id="h1", hypothesis_statement="UPF transient drop",
        primary_suspect_nf="upf", probes=[probe, probe], notes="",
    )

    verdicts = await orch._run_parallel_investigators(
        hypotheses=[h], plans=[plan], network_analysis_text="na",
        session_service=None, all_phases=[],
    )

    # Two LLM calls happened (multi-shot fired).
    assert call_count[0] == 2
    assert len(verdicts) == 1
    v = verdicts[0]
    assert v.verdict == "NOT_DISPROVEN"
    # Merged reasoning marker present
    assert "Multi-shot consensus" in v.reasoning
    assert "shot 1:" in v.reasoning.lower()
    assert "shot 2:" in v.reasoning.lower()


@pytest.mark.asyncio
async def test_multi_shot_disagreement_forces_inconclusive(monkeypatch):
    """Stub returns DISPROVEN on shot 1 and NOT_DISPROVEN on shot 2.
    Reconciler must force INCONCLUSIVE."""
    from agentic_ops_common.models import PhaseTrace, ToolCallTrace
    from agentic_ops_v6 import orchestrator as orch

    call_count = [0]

    async def fake_run_phase(agent, state, question, session_service, on_event=None):
        call_count[0] += 1
        agent_name = "InvestigatorAgent_h1"
        if call_count[0] == 1:
            verdict_text = "DISPROVEN"
            reasoning = "shot 1 says probes contradict"
            alt_suspects = ["upf"]
        else:
            verdict_text = "NOT_DISPROVEN"
            reasoning = "shot 2 says probes are consistent"
            alt_suspects = []
        verdict = {
            "hypothesis_id": "h1",
            "hypothesis_statement": "test",
            "verdict": verdict_text,
            "reasoning": reasoning,
            "alternative_suspects": alt_suspects,
        }
        trace = PhaseTrace(
            agent_name=agent_name,
            started_at=float(call_count[0]),
            finished_at=float(call_count[0]) + 1.0,
            duration_ms=1000,
            tool_calls=[
                ToolCallTrace(name="get_dp_quality_gauges", args="{}", timestamp=1.0),
                ToolCallTrace(name="measure_rtt", args="{}", timestamp=1.0),
            ],
        )
        return ({**state, "investigator_verdict": json.dumps(verdict)}, [trace])

    monkeypatch.setattr(orch, "_run_phase", fake_run_phase)
    monkeypatch.setattr(
        orch, "create_investigator_agent",
        lambda name=None: object(),
    )

    h = Hypothesis(
        id="h1", statement="test", primary_suspect_nf="upf",
        explanatory_fit=0.9, specificity="specific",
        supporting_events=[], falsification_probes=["p"],
    )
    probe = {
        "tool": "get_dp_quality_gauges", "args_hint": "x",
        "expected_if_hypothesis_holds": "x", "falsifying_observation": "y",
    }
    plan = FalsificationPlan(
        hypothesis_id="h1", hypothesis_statement="test",
        primary_suspect_nf="upf", probes=[probe, probe], notes="",
    )

    verdicts = await orch._run_parallel_investigators(
        hypotheses=[h], plans=[plan], network_analysis_text="na",
        session_service=None, all_phases=[],
    )

    assert call_count[0] == 2
    assert verdicts[0].verdict == "INCONCLUSIVE"
    assert "DISAGREEMENT" in verdicts[0].reasoning
    # Disagreement preserves alt_suspects from BOTH shots
    assert "upf" in verdicts[0].alternative_suspects


@pytest.mark.asyncio
async def test_multi_shot_short_circuits_on_inconclusive_first_shot(monkeypatch):
    """If shot 1 returned INCONCLUSIVE, the orchestrator must skip
    shot 2 to save the LLM call."""
    from agentic_ops_common.models import PhaseTrace, ToolCallTrace
    from agentic_ops_v6 import orchestrator as orch

    call_count = [0]

    async def fake_run_phase(agent, state, question, session_service, on_event=None):
        call_count[0] += 1
        agent_name = "InvestigatorAgent_h1"
        verdict = {
            "hypothesis_id": "h1",
            "hypothesis_statement": "test",
            "verdict": "INCONCLUSIVE",
            "reasoning": "couldn't run probes",
        }
        trace = PhaseTrace(
            agent_name=agent_name,
            started_at=1.0, finished_at=2.0, duration_ms=1000,
            tool_calls=[
                ToolCallTrace(name="get_dp_quality_gauges", args="{}", timestamp=1.0),
                ToolCallTrace(name="measure_rtt", args="{}", timestamp=1.0),
            ],
        )
        return ({**state, "investigator_verdict": json.dumps(verdict)}, [trace])

    monkeypatch.setattr(orch, "_run_phase", fake_run_phase)
    monkeypatch.setattr(
        orch, "create_investigator_agent",
        lambda name=None: object(),
    )

    h = Hypothesis(
        id="h1", statement="test", primary_suspect_nf="upf",
        explanatory_fit=0.9, specificity="specific",
        supporting_events=[], falsification_probes=["p"],
    )
    probe = {
        "tool": "get_dp_quality_gauges", "args_hint": "x",
        "expected_if_hypothesis_holds": "x", "falsifying_observation": "y",
    }
    plan = FalsificationPlan(
        hypothesis_id="h1", hypothesis_statement="test",
        primary_suspect_nf="upf", probes=[probe, probe], notes="",
    )

    verdicts = await orch._run_parallel_investigators(
        hypotheses=[h], plans=[plan], network_analysis_text="na",
        session_service=None, all_phases=[],
    )

    # Only ONE LLM call (short-circuit fired).
    assert call_count[0] == 1
    assert verdicts[0].verdict == "INCONCLUSIVE"


@pytest.mark.asyncio
async def test_multi_shot_disabled_falls_back_to_single_shot(monkeypatch):
    """Setting MULTI_SHOT_INVESTIGATORS=False reverts to single-shot
    behavior — useful for cost-bound runs."""
    from agentic_ops_common.models import PhaseTrace, ToolCallTrace
    from agentic_ops_v6 import orchestrator as orch

    monkeypatch.setattr(orch, "MULTI_SHOT_INVESTIGATORS", False)

    call_count = [0]

    async def fake_run_phase(agent, state, question, session_service, on_event=None):
        call_count[0] += 1
        verdict = {
            "hypothesis_id": "h1", "hypothesis_statement": "test",
            "verdict": "NOT_DISPROVEN", "reasoning": "single shot",
        }
        trace = PhaseTrace(
            agent_name="InvestigatorAgent_h1",
            started_at=1.0, finished_at=2.0, duration_ms=1000,
            tool_calls=[
                ToolCallTrace(name="x", args="{}", timestamp=1.0),
                ToolCallTrace(name="y", args="{}", timestamp=1.0),
            ],
        )
        return ({**state, "investigator_verdict": json.dumps(verdict)}, [trace])

    monkeypatch.setattr(orch, "_run_phase", fake_run_phase)
    monkeypatch.setattr(
        orch, "create_investigator_agent", lambda name=None: object(),
    )

    h = Hypothesis(
        id="h1", statement="test", primary_suspect_nf="upf",
        explanatory_fit=0.9, specificity="specific",
        supporting_events=[], falsification_probes=["p"],
    )
    probe = {
        "tool": "get_dp_quality_gauges", "args_hint": "x",
        "expected_if_hypothesis_holds": "x", "falsifying_observation": "y",
    }
    plan = FalsificationPlan(
        hypothesis_id="h1", hypothesis_statement="test",
        primary_suspect_nf="upf", probes=[probe, probe], notes="",
    )

    verdicts = await orch._run_parallel_investigators(
        hypotheses=[h], plans=[plan], network_analysis_text="na",
        session_service=None, all_phases=[],
    )

    assert call_count[0] == 1
    assert verdicts[0].verdict == "NOT_DISPROVEN"
    # Reasoning is the single-shot raw text — no "Multi-shot consensus"
    # marker because reconciler took the single_shot path.
    assert "Multi-shot consensus" not in verdicts[0].reasoning
