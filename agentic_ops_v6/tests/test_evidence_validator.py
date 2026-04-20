"""Tests for the v6 per-sub-Investigator evidence validator."""

from __future__ import annotations

from agentic_ops_v6.subagents.evidence_validator import validate_evidence


def _trace(agent_name: str, tool_calls: list[str]) -> dict:
    return {
        "agent_name": agent_name,
        "tool_calls": [{"name": t} for t in tool_calls],
    }


def _investigator_output(agent_name: str, raw_text: str) -> dict:
    return {"agent_name": agent_name, "raw_text": raw_text}


# ============================================================================
# Per-agent verdicts
# ============================================================================

def test_clean_verdict_when_tool_calls_match_citations():
    traces = [_trace("InvestigatorAgent_h1", ["measure_rtt", "get_nf_metrics", "check_process_listeners"])]
    output = _investigator_output(
        "InvestigatorAgent_h1",
        'ran three probes. [EVIDENCE: measure_rtt("pcscf", "172.22.0.19") -> "100% loss"] '
        '[EVIDENCE: get_nf_metrics("amf") -> "ran_ue=0"]'
    )
    result = validate_evidence(traces, [output])
    assert result.per_agent[0].verdict == "clean"
    assert result.overall_verdict == "clean"


def test_severe_when_zero_tool_calls():
    traces = [_trace("InvestigatorAgent_h1", [])]
    output = _investigator_output(
        "InvestigatorAgent_h1",
        'bogus citations: [EVIDENCE: measure_rtt("x") -> "something"]'
    )
    result = validate_evidence(traces, [output])
    assert result.per_agent[0].verdict == "severe"
    assert result.per_agent[0].confidence == "none"
    assert "ZERO tool calls" in result.per_agent[0].notes[0]


def test_severe_when_most_citations_unmatched():
    """Many fabricated citations with few real ones → severe."""
    traces = [_trace("InvestigatorAgent_h1", ["measure_rtt"])]
    output = _investigator_output(
        "InvestigatorAgent_h1",
        """
        [EVIDENCE: measure_rtt("a") -> "1"]
        [EVIDENCE: read_container_logs("b") -> "2"]
        [EVIDENCE: run_kamcmd("c") -> "3"]
        [EVIDENCE: search_logs("d") -> "4"]
        """
    )
    result = validate_evidence(traces, [output])
    # 3 unmatched >= 1 matched → severe
    assert result.per_agent[0].verdict == "severe"


def test_has_warnings_with_few_unmatched():
    traces = [_trace("InvestigatorAgent_h1",
                     ["measure_rtt", "get_nf_metrics", "check_process_listeners"])]
    output = _investigator_output(
        "InvestigatorAgent_h1",
        """
        [EVIDENCE: measure_rtt("a") -> "1"]
        [EVIDENCE: get_nf_metrics("b") -> "2"]
        [EVIDENCE: check_process_listeners("c") -> "3"]
        [EVIDENCE: read_container_logs("d") -> "one fabricated"]
        """
    )
    result = validate_evidence(traces, [output])
    assert result.per_agent[0].verdict == "has_warnings"


def test_has_warnings_when_below_min_tool_calls():
    """1 tool call is below the minimum of 2 → has_warnings."""
    traces = [_trace("InvestigatorAgent_h1", ["measure_rtt"])]
    output = _investigator_output(
        "InvestigatorAgent_h1",
        '[EVIDENCE: measure_rtt("x") -> "y"]'
    )
    result = validate_evidence(traces, [output])
    assert result.per_agent[0].verdict == "has_warnings"
    assert result.per_agent[0].confidence == "medium"


# ============================================================================
# Aggregation
# ============================================================================

def test_overall_worst_wins():
    """Overall verdict = worst per-agent verdict."""
    traces = [
        _trace("InvestigatorAgent_h1", ["measure_rtt", "get_nf_metrics"]),
        _trace("InvestigatorAgent_h2", []),  # zero calls = severe
    ]
    outputs = [
        _investigator_output(
            "InvestigatorAgent_h1",
            '[EVIDENCE: measure_rtt("x") -> "y"] '
            '[EVIDENCE: get_nf_metrics("z") -> "q"]'
        ),
        _investigator_output(
            "InvestigatorAgent_h2",
            '[EVIDENCE: measure_rtt("fake") -> "fake"]'
        ),
    ]
    result = validate_evidence(traces, outputs)
    assert result.overall_verdict == "severe"
    assert result.overall_confidence == "none"


def test_overall_confidence_takes_tightest_cap():
    """Per-agent confidences mixed → overall is tightest."""
    traces = [
        _trace("InvestigatorAgent_h1", ["measure_rtt", "get_nf_metrics"]),
        _trace("InvestigatorAgent_h2", ["check_process_listeners"]),
    ]
    outputs = [
        _investigator_output(
            "InvestigatorAgent_h1",
            '[EVIDENCE: measure_rtt("x") -> "y"] '
            '[EVIDENCE: get_nf_metrics("z") -> "q"]'
        ),
        _investigator_output(
            "InvestigatorAgent_h2",
            '[EVIDENCE: check_process_listeners("x") -> "y"]'
        ),
    ]
    result = validate_evidence(traces, outputs)
    # h1 = clean (high), h2 = has_warnings (medium). Overall confidence = medium.
    assert result.overall_confidence == "medium"


def test_summary_lists_each_sub_agent():
    traces = [
        _trace("InvestigatorAgent_h1", ["measure_rtt", "get_nf_metrics"]),
        _trace("InvestigatorAgent_h2", ["check_process_listeners", "run_kamcmd"]),
    ]
    outputs = [
        _investigator_output(
            "InvestigatorAgent_h1",
            '[EVIDENCE: measure_rtt("x") -> "y"] '
            '[EVIDENCE: get_nf_metrics("z") -> "q"]'
        ),
        _investigator_output(
            "InvestigatorAgent_h2",
            '[EVIDENCE: check_process_listeners("x") -> "y"] '
            '[EVIDENCE: run_kamcmd("z") -> "q"]'
        ),
    ]
    result = validate_evidence(traces, outputs)
    assert "InvestigatorAgent_h1" in result.summary
    assert "InvestigatorAgent_h2" in result.summary


def test_empty_inputs_produce_severe():
    result = validate_evidence([], [])
    assert result.overall_verdict == "severe"
    assert result.overall_confidence == "none"
