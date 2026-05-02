"""Unit tests for guardrails/probe_selection — Decision B, PR 7.

Pure-Python tests over Pydantic-typed Hypothesis + in-memory MetricsKB
fixtures. No async, no Neo4j.
"""

from __future__ import annotations

import pytest

from agentic_ops_common.metric_kb.models import (
    Disambiguator,
    Healthy,
    Layer,
    Meaning,
    MetricEntry,
    MetricsKB,
    NFBlock,
    Probing,
    Source,
)
from agentic_ops_v6.guardrails.probe_selection import (
    ProbeCandidate,
    render_candidates_for_prompt,
    select_probes,
)
from agentic_ops_v6.models import Hypothesis


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def _metric(
    *,
    description: str = "test metric",
    probing_tool: str | None = None,
    probing_args: str = "",
    disambiguators: list[tuple[str, str]] | None = None,
    spike: str = "",
    drop: str = "",
    zero: str = "",
    typical: tuple[float, float] | None = None,
    invariant: str = "",
) -> MetricEntry:
    return MetricEntry.model_construct(
        description=description,
        source=Source.PROMETHEUS if hasattr(Source, "PROMETHEUS") else "prometheus",
        type="gauge",
        meaning=Meaning.model_construct(spike=spike, drop=drop, zero=zero) if (spike or drop or zero) else None,
        healthy=Healthy.model_construct(
            typical_range=typical, invariant=invariant or None,
        ),
        how_to_verify_live=Probing.model_construct(
            tool=probing_tool, args_hint=probing_args,
        ) if probing_tool else None,
        disambiguators=[
            Disambiguator.model_construct(metric=m, separates=s)
            for m, s in (disambiguators or [])
        ],
    )


def _kb(metrics_per_nf: dict[str, dict[str, MetricEntry]]) -> MetricsKB:
    return MetricsKB.model_construct(metrics={
        nf: NFBlock.model_construct(layer=Layer.CORE, metrics=metrics)
        for nf, metrics in metrics_per_nf.items()
    })


def _hyp(*, nf: str = "upf", hid: str = "h1") -> Hypothesis:
    return Hypothesis(
        id=hid, statement="test hypothesis", primary_suspect_nf=nf,
        supporting_events=["evt"], explanatory_fit=0.85,
        falsification_probes=["p"], specificity="specific",
    )


# ---------------------------------------------------------------------------
# Empty-case PASS
# ---------------------------------------------------------------------------


def test_select_empty_when_nf_not_in_kb():
    kb = _kb({})
    candidates = select_probes(_hyp(nf="upf"), kb)
    assert candidates == []


def test_select_empty_when_no_metrics_have_probing():
    """All metrics on the NF lack how_to_verify_live → empty list."""
    kb = _kb({
        "upf": {
            "no_probe_metric": _metric(description="x"),
        },
    })
    candidates = select_probes(_hyp(nf="upf"), kb)
    assert candidates == []


def test_select_empty_for_kb_coverage_gap_nf():
    """Mongo's 0% probing coverage produces an empty list — the
    empirical KB-coverage signal."""
    kb = _kb({
        "mongo": {
            "uncovered_metric": _metric(description="no probing"),
        },
    })
    candidates = select_probes(_hyp(nf="mongo"), kb)
    assert candidates == []


# ---------------------------------------------------------------------------
# Primary-NF candidates
# ---------------------------------------------------------------------------


def test_select_primary_metric_with_probing():
    kb = _kb({
        "upf": {
            "activity": _metric(
                description="UPF activity gauge",
                probing_tool="get_dp_quality_gauges",
                probing_args="window_seconds=60",
                drop="UPF dropped traffic",
                invariant="UPF active during calls",
            ),
        },
    })
    candidates = select_probes(_hyp(nf="upf"), kb)
    assert len(candidates) == 1
    c = candidates[0]
    assert c.tool == "get_dp_quality_gauges"
    assert c.args_hint == "window_seconds=60"
    assert c.via == "primary"
    assert c.source_metric == "upf.activity"
    # Expected text incorporates the meaning.drop authoring
    assert "UPF dropped traffic" in c.expected_if_hypothesis_holds
    # Falsifying text incorporates the invariant
    assert "UPF active during calls" in c.falsifying_observation


def test_select_filters_invalid_investigator_tool():
    """Tools not in the Investigator's _InvestigatorTool literal are
    silently dropped (the IG schema would reject them downstream)."""
    kb = _kb({
        "upf": {
            "metric_with_bogus_tool": _metric(
                description="x",
                probing_tool="nonexistent_tool",
                probing_args="x",
            ),
        },
    })
    candidates = select_probes(_hyp(nf="upf"), kb)
    assert candidates == []


def test_select_dedupes_by_tool_and_args_hint():
    """Two metrics that resolve to the same (tool, args_hint) collapse
    to one candidate. Different args_hints stay distinct."""
    kb = _kb({
        "upf": {
            "m1": _metric(
                description="x",
                probing_tool="get_dp_quality_gauges",
                probing_args="same",
            ),
            "m2": _metric(
                description="y",
                probing_tool="get_dp_quality_gauges",
                probing_args="same",  # identical → dedupe
            ),
            "m3": _metric(
                description="z",
                probing_tool="get_dp_quality_gauges",
                probing_args="different",  # different → kept
            ),
        },
    })
    candidates = select_probes(_hyp(nf="upf"), kb)
    args = sorted(c.args_hint for c in candidates)
    assert args == ["different", "same"]


# ---------------------------------------------------------------------------
# Disambiguator BFS
# ---------------------------------------------------------------------------


def test_select_walks_disambiguators_one_hop():
    """A primary metric's disambiguator points at a metric on a
    DIFFERENT NF (typical real-world case — discriminating from one
    NF requires reading another). The disambiguator-walk surfaces it
    even though it's not in the primary NF's block."""
    kb = _kb({
        "upf": {
            "primary": _metric(
                description="primary",
                probing_tool="get_dp_quality_gauges",
                probing_args="primary_args",
                disambiguators=[("rtpengine.disambig", "separates A from B")],
            ),
        },
        "rtpengine": {
            "disambig": _metric(
                description="disambiguator on different NF",
                probing_tool="get_diagnostic_metrics",
                probing_args="disambig_args",
            ),
        },
    })
    candidates = select_probes(_hyp(nf="upf"), kb)
    assert len(candidates) == 2
    primary_c = next(c for c in candidates if c.via == "primary")
    disambig_c = next(c for c in candidates if c.via.startswith("disambiguator"))
    assert primary_c.tool == "get_dp_quality_gauges"
    assert disambig_c.tool == "get_diagnostic_metrics"
    assert disambig_c.args_hint == "disambig_args"
    # Disambiguator candidates carry the `separates` hint in expected text
    assert "separates A from B" in disambig_c.expected_if_hypothesis_holds


def test_select_disambiguator_resolves_cross_nf_target():
    """Disambiguator can reference a metric on a DIFFERENT NF; the
    resolver finds it via the bare-name fallback."""
    kb = _kb({
        "rtpengine": {
            "loss_ratio": _metric(
                description="x",
                probing_tool="get_dp_quality_gauges",
                probing_args="rtpengine_loss",
                disambiguators=[("upf.gtp_in", "separates RTPEngine from UPF")],
            ),
        },
        "upf": {
            "gtp_in": _metric(
                description="UPF ingress",
                probing_tool="get_diagnostic_metrics",
                probing_args="upf_gtp_args",
            ),
        },
    })
    candidates = select_probes(_hyp(nf="rtpengine"), kb)
    args = {c.args_hint for c in candidates}
    assert "rtpengine_loss" in args
    assert "upf_gtp_args" in args


def test_select_skips_disambiguator_with_unresolvable_target():
    kb = _kb({
        "upf": {
            "primary": _metric(
                description="x",
                probing_tool="get_dp_quality_gauges",
                probing_args="x",
                disambiguators=[("nonexistent.metric", "x")],
            ),
        },
    })
    candidates = select_probes(_hyp(nf="upf"), kb)
    assert len(candidates) == 1  # only the primary; disambiguator dropped


# ---------------------------------------------------------------------------
# Candidate count cap
# ---------------------------------------------------------------------------


def test_select_caps_candidates_to_max():
    """Too many KB-rich metrics get truncated to max_candidates."""
    metrics = {
        f"m{i}": _metric(
            description=f"m{i}",
            probing_tool="get_dp_quality_gauges",
            probing_args=f"args_{i}",
        )
        for i in range(20)
    }
    kb = _kb({"upf": metrics})
    candidates = select_probes(_hyp(nf="upf"), kb, max_candidates=5)
    assert len(candidates) == 5


# ---------------------------------------------------------------------------
# Rendering for prompt injection
# ---------------------------------------------------------------------------


def test_render_empty_dict_returns_placeholder():
    assert "(no hypotheses)" in render_candidates_for_prompt({})


def test_render_empty_candidates_marks_kb_gap():
    """Empty candidate list per hypothesis renders as the explicit
    KB-coverage-gap message — IG reads this as license to free-form."""
    out = render_candidates_for_prompt({"h1": []})
    assert "h1" in out
    assert "no KB-authored probe candidates" in out
    assert "Free-form" in out


def test_render_includes_per_candidate_fields():
    c = ProbeCandidate(
        tool="measure_rtt",
        args_hint="from gnb to upf",
        expected_if_hypothesis_holds="loss observed",
        falsifying_observation="loss not observed",
        source_metric="upf.gtp_in",
        via="primary",
    )
    out = render_candidates_for_prompt({"h1": [c]})
    assert "measure_rtt" in out
    assert "from gnb to upf" in out
    assert "loss observed" in out
    assert "loss not observed" in out
    assert "upf.gtp_in" in out
    assert "primary" in out


def test_render_groups_by_hypothesis():
    c1 = ProbeCandidate(
        tool="get_network_status", args_hint="a",
        expected_if_hypothesis_holds="x", falsifying_observation="y",
        source_metric="upf.m1", via="primary",
    )
    c2 = ProbeCandidate(
        tool="check_process_listeners", args_hint="b",
        expected_if_hypothesis_holds="x", falsifying_observation="y",
        source_metric="rtpengine.m2", via="primary",
    )
    out = render_candidates_for_prompt({"h1": [c1], "h2": [c2]})
    assert "Candidates for `h1`" in out
    assert "Candidates for `h2`" in out
    assert "get_network_status" in out
    assert "check_process_listeners" in out


# ---------------------------------------------------------------------------
# Integration with the real KB (sanity check, not a unit test)
# ---------------------------------------------------------------------------


def test_real_kb_rtpengine_returns_rate_based_candidates():
    """Sanity: against the live KB, an RTPEngine hypothesis should
    surface rate-based / window-based probe candidates — the KB-curated
    alternative to cumulative-counter free-forming that bit the
    mongodb_gone h1 multi-shot disagreement."""
    from agentic_ops_common.metric_kb import load_kb
    kb = load_kb()
    candidates = select_probes(_hyp(nf="rtpengine"), kb)
    # We expect at least one candidate (rtpengine has 15% probing coverage)
    assert candidates
    # Args hints should reference rate-based or window-based reading
    args_text = " ".join(c.args_hint for c in candidates).lower()
    assert any(
        keyword in args_text
        for keyword in ("rate", "window", "per_second", "pps")
    ), (
        "Expected at least one rtpengine candidate to reference rate/window-"
        f"based reading; got: {args_text!r}"
    )


def test_real_kb_mongo_returns_empty():
    """Sanity: mongo's 0% coverage in the live KB produces an empty
    candidate list."""
    from agentic_ops_common.metric_kb import load_kb
    kb = load_kb()
    candidates = select_probes(_hyp(nf="mongo"), kb)
    assert candidates == []
