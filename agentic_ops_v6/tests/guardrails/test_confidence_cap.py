"""Unit tests for guardrails/confidence_cap — Decision F, PR 3.

Pure-Python tests over Pydantic-typed verdict / probe / report objects.
"""

from __future__ import annotations

from agentic_ops_v6.guardrails.base import GuardrailVerdict
from agentic_ops_v6.guardrails.confidence_cap import (
    cap_synthesis_confidence,
    compute_evidence_strength_for_promoted,
    compute_evidence_strength_for_verdict,
)
from agentic_ops_v6.guardrails.synthesis_pool import (
    CandidatePool,
    CandidatePoolMember,
)
from agentic_ops_v6.models import (
    DiagnosisReport,
    Hypothesis,
    InvestigatorVerdict,
    ProbeResult,
)


# ===========================================================================
# Fixtures
# ===========================================================================


def _probe(verdict: str = "CONSISTENT") -> ProbeResult:
    return ProbeResult(
        probe_description="test probe",
        compared_to_expected=verdict,  # type: ignore
    )


def _verdict(
    *,
    hid: str = "h1",
    verdict: str = "NOT_DISPROVEN",
    probe_outcomes: list[str] | None = None,
) -> InvestigatorVerdict:
    probes = [_probe(o) for o in (probe_outcomes or [])]
    return InvestigatorVerdict(
        hypothesis_id=hid,
        hypothesis_statement=f"hypothesis {hid}",
        verdict=verdict,
        reasoning="test reasoning",
        probes_executed=probes,
    )


def _hypothesis(*, hid: str, nf: str) -> Hypothesis:
    return Hypothesis(
        id=hid,
        statement="test",
        primary_suspect_nf=nf,
        supporting_events=["evt"],
        explanatory_fit=0.8,
        falsification_probes=["p"],
        specificity="specific",
    )


def _report(
    *,
    nf: str | None = "upf",
    confidence: str = "high",
    verdict_kind: str = "confirmed",
) -> DiagnosisReport:
    return DiagnosisReport(
        summary="test summary",
        root_cause="test root cause",
        root_cause_confidence=confidence,  # type: ignore
        primary_suspect_nf=nf,  # type: ignore
        verdict_kind=verdict_kind,  # type: ignore
        affected_components=[],
        timeline=[],
        recommendation="test",
        explanation="test explanation",
    )


# ===========================================================================
# compute_evidence_strength_for_verdict
# ===========================================================================


def test_strength_strong_clean_probes():
    """≥2 CONSISTENT, 0 CONTRADICTS, 0 AMBIGUOUS → STRONG."""
    v = _verdict(probe_outcomes=["CONSISTENT", "CONSISTENT", "CONSISTENT"])
    assert compute_evidence_strength_for_verdict(v) == "STRONG"


def test_strength_moderate_with_one_ambiguous():
    """≥2 CONSISTENT, 0 CONTRADICTS, ≥1 AMBIGUOUS → MODERATE."""
    v = _verdict(probe_outcomes=["CONSISTENT", "CONSISTENT", "AMBIGUOUS"])
    assert compute_evidence_strength_for_verdict(v) == "MODERATE"


def test_strength_weak_on_contradicts():
    """Any CONTRADICTS → WEAK regardless of CONSISTENT count."""
    v = _verdict(probe_outcomes=["CONSISTENT", "CONSISTENT", "CONTRADICTS"])
    assert compute_evidence_strength_for_verdict(v) == "WEAK"


def test_strength_weak_with_too_few_consistent():
    """<2 CONSISTENT (and no CONTRADICTS) → WEAK."""
    v = _verdict(probe_outcomes=["CONSISTENT", "AMBIGUOUS"])
    assert compute_evidence_strength_for_verdict(v) == "WEAK"


def test_strength_none_majority_ambiguous():
    """>50% AMBIGUOUS → NONE."""
    v = _verdict(probe_outcomes=["AMBIGUOUS", "AMBIGUOUS", "CONSISTENT"])
    assert compute_evidence_strength_for_verdict(v) == "NONE"


def test_strength_none_no_probes():
    v = _verdict(probe_outcomes=[])
    assert compute_evidence_strength_for_verdict(v) == "NONE"


# ===========================================================================
# compute_evidence_strength_for_promoted
# ===========================================================================


def test_promoted_strong_three_cites():
    assert compute_evidence_strength_for_promoted(cite_count=3, strong_cited_count=0) == "STRONG"


def test_promoted_moderate_two_cites():
    assert compute_evidence_strength_for_promoted(cite_count=2, strong_cited_count=1) == "MODERATE"


def test_promoted_moderate_two_strong_cites():
    """Two strong-cites alone qualifies as MODERATE even with 1 cite_count."""
    assert compute_evidence_strength_for_promoted(cite_count=1, strong_cited_count=2) == "MODERATE"


def test_promoted_weak_single_strong_cite():
    """1 cite + 1 strong-cite is the single-strong-cite threshold path."""
    assert compute_evidence_strength_for_promoted(cite_count=1, strong_cited_count=1) == "WEAK"


def test_promoted_none_no_cites():
    assert compute_evidence_strength_for_promoted(cite_count=0, strong_cited_count=0) == "NONE"


# ===========================================================================
# cap_synthesis_confidence — main flow
# ===========================================================================


def test_cap_passes_inconclusive_unchanged():
    report = _report(nf=None, verdict_kind="inconclusive", confidence="low")
    result = cap_synthesis_confidence(report, [], [], CandidatePool(members=[]))
    assert result.verdict is GuardrailVerdict.PASS


def test_cap_passes_strong_evidence_at_high():
    """STRONG evidence + emitted high → no cap."""
    hyps = [_hypothesis(hid="h1", nf="upf")]
    verdicts = [_verdict(hid="h1", verdict="NOT_DISPROVEN",
                         probe_outcomes=["CONSISTENT", "CONSISTENT", "CONSISTENT"])]
    report = _report(nf="upf", confidence="high")
    result = cap_synthesis_confidence(report, verdicts, hyps, CandidatePool(members=[]))
    assert result.verdict is GuardrailVerdict.PASS
    assert result.notes["evidence_strength"] == "STRONG"
    assert result.notes["applied"] is False


def test_cap_repairs_high_to_medium_on_moderate_evidence():
    """MODERATE evidence + emitted high → REPAIR with confidence='medium'."""
    hyps = [_hypothesis(hid="h1", nf="upf")]
    verdicts = [_verdict(hid="h1", verdict="NOT_DISPROVEN",
                         probe_outcomes=["CONSISTENT", "CONSISTENT", "AMBIGUOUS"])]
    report = _report(nf="upf", confidence="high")
    result = cap_synthesis_confidence(report, verdicts, hyps, CandidatePool(members=[]))
    assert result.verdict is GuardrailVerdict.REPAIR
    assert result.output.root_cause_confidence == "medium"
    assert "Confidence cap applied" in result.output.explanation
    assert "MODERATE" in result.output.explanation
    assert result.notes["applied"] is True


def test_cap_repairs_high_to_low_on_weak_evidence():
    """WEAK evidence + emitted high → REPAIR with confidence='low'."""
    hyps = [_hypothesis(hid="h1", nf="upf")]
    verdicts = [_verdict(hid="h1", verdict="NOT_DISPROVEN",
                         probe_outcomes=["CONSISTENT", "CONTRADICTS"])]
    report = _report(nf="upf", confidence="high")
    result = cap_synthesis_confidence(report, verdicts, hyps, CandidatePool(members=[]))
    assert result.verdict is GuardrailVerdict.REPAIR
    assert result.output.root_cause_confidence == "low"
    assert "WEAK" in result.output.explanation


def test_cap_passes_low_emitted_below_cap():
    """Synthesis already emitted 'low' — no cap needed even on STRONG."""
    hyps = [_hypothesis(hid="h1", nf="upf")]
    verdicts = [_verdict(hid="h1", verdict="NOT_DISPROVEN",
                         probe_outcomes=["CONSISTENT", "CONSISTENT", "CONSISTENT"])]
    report = _report(nf="upf", confidence="low")
    result = cap_synthesis_confidence(report, verdicts, hyps, CandidatePool(members=[]))
    assert result.verdict is GuardrailVerdict.PASS


def test_cap_repairs_medium_to_low_on_weak():
    """Cap also fires when emitted is 'medium' but evidence is WEAK."""
    hyps = [_hypothesis(hid="h1", nf="upf")]
    verdicts = [_verdict(hid="h1", verdict="NOT_DISPROVEN",
                         probe_outcomes=["CONSISTENT", "CONTRADICTS"])]
    report = _report(nf="upf", confidence="medium")
    result = cap_synthesis_confidence(report, verdicts, hyps, CandidatePool(members=[]))
    assert result.verdict is GuardrailVerdict.REPAIR
    assert result.output.root_cause_confidence == "low"


# ===========================================================================
# cap_synthesis_confidence — promoted verdict_kind
# ===========================================================================


def test_cap_promoted_strong_passes_high():
    pool = CandidatePool(members=[
        CandidatePoolMember(nf="rtpengine", kind="promoted",
                            cite_count=3, strong_cited_in=["h1", "h2"]),
    ])
    report = _report(nf="rtpengine", verdict_kind="promoted", confidence="high")
    result = cap_synthesis_confidence(report, [], [], pool)
    assert result.verdict is GuardrailVerdict.PASS
    assert result.notes["evidence_strength"] == "STRONG"


def test_cap_promoted_weak_caps_high_to_low():
    """Single-strong-cite promoted → WEAK → high capped to low."""
    pool = CandidatePool(members=[
        CandidatePoolMember(nf="rtpengine", kind="promoted",
                            cite_count=1, strong_cited_in=["h1"]),
    ])
    report = _report(nf="rtpengine", verdict_kind="promoted", confidence="high")
    result = cap_synthesis_confidence(report, [], [], pool)
    assert result.verdict is GuardrailVerdict.REPAIR
    assert result.output.root_cause_confidence == "low"


# ===========================================================================
# Replay run_20260501_032822 — h1 should cap to medium
# ===========================================================================


def test_replay_call_quality_h1_caps_high_to_medium():
    """In the actual run, h1 had 1 AMBIGUOUS + 2 CONSISTENT probes →
    MODERATE strength → high caps to medium. The diagnosed NF (UPF)
    is still wrong (Decision H is needed for that), but at least the
    confidence isn't misleadingly high."""
    hyps = [_hypothesis(hid="h1", nf="upf")]
    verdicts = [_verdict(
        hid="h1", verdict="NOT_DISPROVEN",
        probe_outcomes=["AMBIGUOUS", "CONSISTENT", "CONSISTENT"],
    )]
    report = _report(nf="upf", confidence="high", verdict_kind="confirmed")
    result = cap_synthesis_confidence(report, verdicts, hyps, CandidatePool(members=[]))
    assert result.verdict is GuardrailVerdict.REPAIR
    assert result.output.root_cause_confidence == "medium"
    assert "MODERATE" in result.output.explanation


# ===========================================================================
# Edge cases
# ===========================================================================


def test_cap_handles_missing_supporting_verdict():
    """If pool-membership somehow let a non-pool NF through, the cap
    finds no supporting verdict and treats strength as NONE."""
    hyps = [_hypothesis(hid="h1", nf="upf")]
    verdicts = [_verdict(hid="h1", verdict="NOT_DISPROVEN",
                         probe_outcomes=["CONSISTENT", "CONSISTENT"])]
    # Report names rtpengine but no verdict supports it
    report = _report(nf="rtpengine", confidence="high")
    result = cap_synthesis_confidence(report, verdicts, hyps, CandidatePool(members=[]))
    assert result.verdict is GuardrailVerdict.REPAIR
    # NONE strength → caps to low
    assert result.output.root_cause_confidence == "low"


def test_cap_handles_reinvestigation_verdict():
    """Re-investigation verdicts have hypothesis_id like h_promoted_<nf>;
    the cap should find them when report.primary_suspect_nf matches."""
    hyps = [_hypothesis(hid="h1", nf="pcf")]  # original wasn't UPF
    verdicts = [
        _verdict(hid="h1", verdict="DISPROVEN", probe_outcomes=["CONTRADICTS"]),
        _verdict(
            hid="h_promoted_upf", verdict="NOT_DISPROVEN",
            probe_outcomes=["CONSISTENT", "CONSISTENT", "CONSISTENT"],
        ),
    ]
    report = _report(nf="upf", confidence="high")
    result = cap_synthesis_confidence(report, verdicts, hyps, CandidatePool(members=[]))
    assert result.verdict is GuardrailVerdict.PASS
    assert result.notes["evidence_strength"] == "STRONG"
