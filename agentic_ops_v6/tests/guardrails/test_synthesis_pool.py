"""Unit tests for guardrails/synthesis_pool.compute_candidate_pool — Decision E, PR 5.

The aggregator is pure Python over Pydantic-typed verdict / hypothesis
objects. No ADK runtime, no Gemini calls.
"""

from __future__ import annotations

from agentic_ops_v6.guardrails.synthesis_pool import (
    CandidatePool,
    compute_candidate_pool,
)
from agentic_ops_v6.models import Hypothesis, InvestigatorVerdict


# ---------------------------------------------------------------------------
# Test fixture builders
# ---------------------------------------------------------------------------

def _hypothesis(*, hid: str, nf: str, fit: float = 0.85) -> Hypothesis:
    return Hypothesis(
        id=hid,
        statement=f"{nf} is the source of the anomaly.",
        primary_suspect_nf=nf,
        supporting_events=["evt1"],
        explanatory_fit=fit,
        falsification_probes=["measure_rtt(x, y)"],
        specificity="specific",
    )


def _verdict(
    *,
    hid: str,
    verdict: str,
    alt_suspects: list[str] | None = None,
    reasoning: str = "",
) -> InvestigatorVerdict:
    return InvestigatorVerdict(
        hypothesis_id=hid,
        hypothesis_statement=f"hypothesis {hid}",
        verdict=verdict,
        reasoning=reasoning,
        alternative_suspects=alt_suspects or [],
    )


# ---------------------------------------------------------------------------
# Survivors
# ---------------------------------------------------------------------------

def test_single_not_disproven_survivor():
    hyps = [_hypothesis(hid="h1", nf="upf", fit=0.9)]
    verdicts = [_verdict(hid="h1", verdict="NOT_DISPROVEN")]
    pool = compute_candidate_pool(verdicts, hyps)
    assert pool.has_survivor
    assert not pool.needs_reinvestigation
    assert len(pool.survivors) == 1
    assert pool.survivors[0].nf == "upf"
    assert pool.survivors[0].survivor_hypothesis_id == "h1"


def test_multiple_survivors_ranked_by_fit():
    hyps = [
        _hypothesis(hid="h1", nf="upf", fit=0.5),
        _hypothesis(hid="h2", nf="rtpengine", fit=0.9),
        _hypothesis(hid="h3", nf="pcscf", fit=0.7),
    ]
    verdicts = [_verdict(hid=h.id, verdict="NOT_DISPROVEN") for h in hyps]
    pool = compute_candidate_pool(verdicts, hyps)
    assert len(pool.survivors) == 3
    # Sorted by fit desc
    assert [m.nf for m in pool.survivors] == ["rtpengine", "pcscf", "upf"]


def test_survivor_present_does_not_need_reinvestigation():
    hyps = [
        _hypothesis(hid="h1", nf="upf"),
        _hypothesis(hid="h2", nf="rtpengine"),
    ]
    verdicts = [
        _verdict(hid="h1", verdict="NOT_DISPROVEN"),
        _verdict(hid="h2", verdict="DISPROVEN", alt_suspects=["scscf", "scscf"]),
    ]
    pool = compute_candidate_pool(verdicts, hyps)
    assert pool.has_survivor
    assert not pool.needs_reinvestigation


# ---------------------------------------------------------------------------
# Promoted via cross-corroboration (≥2 mentions)
# ---------------------------------------------------------------------------

def test_cross_corroboration_promotes_alt_suspect():
    """The data-plane-degradation pattern: 2/3 disproven verdicts name UPF."""
    hyps = [
        _hypothesis(hid="h1", nf="pcf"),
        _hypothesis(hid="h2", nf="rtpengine"),
        _hypothesis(hid="h3", nf="pyhss"),
    ]
    verdicts = [
        _verdict(hid="h1", verdict="DISPROVEN", alt_suspects=["upf"]),
        _verdict(hid="h2", verdict="DISPROVEN", alt_suspects=["upf"]),
        _verdict(hid="h3", verdict="DISPROVEN", alt_suspects=["smf"]),
    ]
    pool = compute_candidate_pool(verdicts, hyps)
    assert not pool.has_survivor
    assert pool.needs_reinvestigation
    assert pool.top_promoted is not None
    assert pool.top_promoted.nf == "upf"
    assert pool.top_promoted.cite_count == 2
    # smf has only 1 mention and no strong cite — not promoted
    assert all(m.nf != "smf" for m in pool.promoted)


def test_promoted_ranking_by_cite_count():
    hyps = [
        _hypothesis(hid="h1", nf="pcf"),
        _hypothesis(hid="h2", nf="rtpengine"),
        _hypothesis(hid="h3", nf="pyhss"),
    ]
    verdicts = [
        _verdict(hid="h1", verdict="DISPROVEN", alt_suspects=["upf", "scscf"]),
        _verdict(hid="h2", verdict="DISPROVEN", alt_suspects=["upf", "scscf"]),
        _verdict(hid="h3", verdict="DISPROVEN", alt_suspects=["upf"]),
    ]
    pool = compute_candidate_pool(verdicts, hyps)
    nfs = [m.nf for m in pool.promoted]
    # upf cited 3x, scscf 2x → upf first
    assert nfs[0] == "upf"
    assert nfs[1] == "scscf"


# ---------------------------------------------------------------------------
# Promoted via single-strong-cite (1 mention + name in reasoning)
# ---------------------------------------------------------------------------

def test_single_strong_cite_promotes_alt_suspect():
    """The 17:58 P-CSCF case: only h1's verdict named pcscf in
    alternative_suspects AND wrote about pcscf in the reasoning."""
    hyps = [
        _hypothesis(hid="h1", nf="pcf"),
        _hypothesis(hid="h2", nf="pyhss"),
        _hypothesis(hid="h3", nf="scscf"),
    ]
    verdicts = [
        _verdict(
            hid="h1", verdict="DISPROVEN",
            alt_suspects=["pcscf"],
            reasoning=(
                "The discrepancy between P-CSCF's 696 connection failures "
                "and PCF's 18 received requests points to an issue at pcscf."
            ),
        ),
        _verdict(hid="h2", verdict="DISPROVEN", alt_suspects=["pcf"]),
        _verdict(hid="h3", verdict="DISPROVEN", alt_suspects=[]),
    ]
    pool = compute_candidate_pool(verdicts, hyps)
    assert pool.needs_reinvestigation
    assert pool.top_promoted is not None
    assert pool.top_promoted.nf == "pcscf"
    assert pool.top_promoted.cite_count == 1
    assert pool.top_promoted.strong_cited_in == ["h1"]


def test_single_mention_without_strong_cite_does_not_promote():
    hyps = [
        _hypothesis(hid="h1", nf="pcf"),
        _hypothesis(hid="h2", nf="pyhss"),
    ]
    verdicts = [
        _verdict(
            hid="h1", verdict="DISPROVEN",
            alt_suspects=["pcscf"],
            reasoning="The PCF metrics look clean.",  # no mention of pcscf
        ),
        _verdict(hid="h2", verdict="DISPROVEN", alt_suspects=[]),
    ]
    pool = compute_candidate_pool(verdicts, hyps)
    # pcscf has 1 mention, no strong cite, no cross-corroboration
    assert pool.is_empty


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_empty_verdicts_produces_empty_pool():
    pool = compute_candidate_pool([], [])
    assert pool.is_empty
    assert not pool.needs_reinvestigation


def test_all_disproven_no_alt_suspects_produces_empty_pool():
    hyps = [_hypothesis(hid="h1", nf="upf"), _hypothesis(hid="h2", nf="rtpengine")]
    verdicts = [
        _verdict(hid="h1", verdict="DISPROVEN", alt_suspects=[]),
        _verdict(hid="h2", verdict="DISPROVEN", alt_suspects=[]),
    ]
    pool = compute_candidate_pool(verdicts, hyps)
    assert pool.is_empty
    assert not pool.needs_reinvestigation


def test_inconclusive_verdicts_ignored():
    """INCONCLUSIVE verdicts contribute neither survivors nor alt_suspects."""
    hyps = [
        _hypothesis(hid="h1", nf="upf"),
        _hypothesis(hid="h2", nf="rtpengine"),
    ]
    verdicts = [
        _verdict(hid="h1", verdict="INCONCLUSIVE", alt_suspects=["pyhss"]),
        _verdict(hid="h2", verdict="DISPROVEN", alt_suspects=["pyhss"]),
    ]
    pool = compute_candidate_pool(verdicts, hyps)
    # Only 1 mention in DISPROVEN verdicts (h2); h1's INCONCLUSIVE is
    # ignored. No strong-cite either. Empty pool.
    assert pool.is_empty


def test_alt_suspect_already_a_survivor_not_double_counted():
    """If h1's primary_suspect_nf=upf is NOT_DISPROVEN AND h2's verdict
    names upf in alt_suspects, upf appears once as survivor, not twice."""
    hyps = [
        _hypothesis(hid="h1", nf="upf"),
        _hypothesis(hid="h2", nf="rtpengine"),
    ]
    verdicts = [
        _verdict(hid="h1", verdict="NOT_DISPROVEN"),
        _verdict(
            hid="h2", verdict="DISPROVEN",
            alt_suspects=["upf"],
            reasoning="The fault is at upf, not rtpengine.",
        ),
    ]
    pool = compute_candidate_pool(verdicts, hyps)
    assert len(pool.survivors) == 1
    assert pool.survivors[0].nf == "upf"
    assert all(m.nf != "upf" for m in pool.promoted)


def test_alt_suspect_normalization_handles_case():
    """The aggregator should match 'UPF' in alt_suspects against 'upf'
    in reasoning case-insensitively. Pool members store the lowercase
    form for consistency."""
    hyps = [
        _hypothesis(hid="h1", nf="pcf"),
        _hypothesis(hid="h2", nf="rtpengine"),
    ]
    verdicts = [
        _verdict(hid="h1", verdict="DISPROVEN", alt_suspects=["UPF"]),
        _verdict(hid="h2", verdict="DISPROVEN", alt_suspects=["upf"]),
    ]
    pool = compute_candidate_pool(verdicts, hyps)
    # Cross-corroboration: 2 mentions (case-insensitive) → promoted
    assert pool.top_promoted is not None
    assert pool.top_promoted.nf == "upf"
    assert pool.top_promoted.cite_count == 2


# ---------------------------------------------------------------------------
# render_for_prompt — the text Synthesis sees
# ---------------------------------------------------------------------------

def test_render_for_prompt_marks_survivors_and_promoted_distinctly():
    hyps = [
        _hypothesis(hid="h1", nf="upf", fit=0.9),
        _hypothesis(hid="h2", nf="rtpengine"),
        _hypothesis(hid="h3", nf="pyhss"),
    ]
    verdicts = [
        _verdict(hid="h1", verdict="NOT_DISPROVEN"),
        _verdict(hid="h2", verdict="DISPROVEN", alt_suspects=["scscf"]),
        _verdict(
            hid="h3", verdict="DISPROVEN",
            alt_suspects=["scscf"],
            reasoning="The S-CSCF interaction with scscf shows the issue.",
        ),
    ]
    pool = compute_candidate_pool(verdicts, hyps)
    text = pool.render_for_prompt()
    assert "SURVIVOR" in text
    assert "PROMOTED" in text
    assert "upf" in text
    assert "scscf" in text


def test_render_for_prompt_handles_empty_pool():
    pool = CandidatePool(members=[])
    text = pool.render_for_prompt()
    assert "empty" in text.lower()


# ---------------------------------------------------------------------------
# Replay actual run shapes
# ---------------------------------------------------------------------------

def test_replay_run_20260501_012613_promotes_upf():
    """The pre-PR-4 data-plane-degradation run had 3 DISPROVEN with:
        h1 alt: ['N3 transport network', 'N4 transport network']
        h2 alt: ['upf']
        h3 alt: ['upf', 'rtpengine']
    Expect: upf promoted (cited in 2 verdicts) as top."""
    hyps = [
        _hypothesis(hid="h1", nf="upf"),  # confusingly the disproved hyp also names upf
        _hypothesis(hid="h2", nf="rtpengine"),
        _hypothesis(hid="h3", nf="pyhss"),
    ]
    verdicts = [
        _verdict(
            hid="h1", verdict="DISPROVEN",
            alt_suspects=["N3 transport network", "N4 transport network"],
            reasoning="Loss is on the network paths to UPF.",
        ),
        _verdict(
            hid="h2", verdict="DISPROVEN",
            alt_suspects=["upf"],
            reasoning="The UPF's egress is dropping packets before rtpengine.",
        ),
        _verdict(
            hid="h3", verdict="DISPROVEN",
            alt_suspects=["upf", "rtpengine"],
            reasoning="A core network issue affecting upf is the likely cause.",
        ),
    ]
    pool = compute_candidate_pool(verdicts, hyps)
    assert pool.needs_reinvestigation
    assert pool.top_promoted is not None
    assert pool.top_promoted.nf == "upf"
    assert pool.top_promoted.cite_count == 2
