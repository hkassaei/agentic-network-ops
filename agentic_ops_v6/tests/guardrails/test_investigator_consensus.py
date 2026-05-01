"""Unit tests for guardrails/investigator_consensus.reconcile_verdicts — Decision C, PR 6."""

from __future__ import annotations

import pytest

from agentic_ops_v6.guardrails.investigator_consensus import (
    ReconciliationResult,
    reconcile_verdicts,
)
from agentic_ops_v6.models import InvestigatorVerdict, ProbeResult


def _v(
    *,
    verdict: str,
    reasoning: str = "test reasoning",
    alt_suspects: list[str] | None = None,
    probes: list[ProbeResult] | None = None,
    hid: str = "h1",
) -> InvestigatorVerdict:
    return InvestigatorVerdict(
        hypothesis_id=hid,
        hypothesis_statement="test hypothesis",
        verdict=verdict,
        reasoning=reasoning,
        probes_executed=probes or [],
        alternative_suspects=alt_suspects or [],
    )


# ===========================================================================
# Single-shot pass-through
# ===========================================================================


def test_single_shot_passes_through_unchanged():
    s = _v(verdict="NOT_DISPROVEN", reasoning="UPF is the source.")
    result = reconcile_verdicts([s])
    assert result.kind == "single_shot"
    assert result.shot_count == 1
    assert result.verdict is s


def test_single_shot_inconclusive_marked_correctly():
    s = _v(verdict="INCONCLUSIVE", reasoning="not enough evidence")
    result = reconcile_verdicts([s])
    assert result.kind == "inconclusive_pass_through"
    assert result.shot_count == 1


def test_single_shot_with_short_circuit_flag_recorded():
    s = _v(verdict="INCONCLUSIVE")
    result = reconcile_verdicts([s], short_circuited=True)
    assert result.short_circuited is True


def test_zero_shots_raises():
    with pytest.raises(ValueError):
        reconcile_verdicts([])


def test_three_shots_raises():
    s = _v(verdict="NOT_DISPROVEN")
    with pytest.raises(ValueError):
        reconcile_verdicts([s, s, s])


# ===========================================================================
# Two-shot agreement
# ===========================================================================


def test_two_shot_agreement_not_disproven_merges_reasoning():
    s1 = _v(verdict="NOT_DISPROVEN", reasoning="UPF dropped packets at egress.")
    s2 = _v(verdict="NOT_DISPROVEN", reasoning="UPF egress imbalance confirmed.")
    result = reconcile_verdicts([s1, s2])
    assert result.kind == "agreement"
    assert result.verdict.verdict == "NOT_DISPROVEN"
    assert "Multi-shot consensus" in result.verdict.reasoning
    assert "both shots returned NOT_DISPROVEN" in result.verdict.reasoning
    assert "UPF dropped packets at egress." in result.verdict.reasoning
    assert "UPF egress imbalance confirmed." in result.verdict.reasoning


def test_two_shot_agreement_disproven_unions_alt_suspects():
    s1 = _v(
        verdict="DISPROVEN",
        alt_suspects=["upf"],
        reasoning="loss is at upf, not rtpengine",
    )
    s2 = _v(
        verdict="DISPROVEN",
        alt_suspects=["upf", "rtpengine"],
        reasoning="upf dropping; rtpengine processing has errors",
    )
    result = reconcile_verdicts([s1, s2])
    assert result.kind == "agreement"
    assert result.verdict.verdict == "DISPROVEN"
    assert sorted(result.verdict.alternative_suspects) == ["rtpengine", "upf"]


def test_two_shot_agreement_dedupes_alt_suspects_case_insensitive():
    s1 = _v(verdict="DISPROVEN", alt_suspects=["UPF"])
    s2 = _v(verdict="DISPROVEN", alt_suspects=["upf"])
    result = reconcile_verdicts([s1, s2])
    # First-seen casing wins (UPF), and the lowercase duplicate is
    # dropped.
    assert result.verdict.alternative_suspects == ["UPF"]


def test_two_shot_agreement_preserves_probes_from_shot_1():
    probes = [
        ProbeResult(
            probe_description="check egress",
            compared_to_expected="CONSISTENT",
        ),
    ]
    s1 = _v(verdict="NOT_DISPROVEN", probes=probes)
    s2 = _v(verdict="NOT_DISPROVEN", probes=[])
    result = reconcile_verdicts([s1, s2])
    assert result.verdict.probes_executed == probes


# ===========================================================================
# Two-shot disagreement
# ===========================================================================


def test_two_shot_disagreement_forces_inconclusive():
    s1 = _v(
        verdict="DISPROVEN",
        reasoning="UPF is the source, not the named NF.",
        alt_suspects=["upf"],
    )
    s2 = _v(
        verdict="NOT_DISPROVEN",
        reasoning="The named NF is consistent with the evidence.",
    )
    result = reconcile_verdicts([s1, s2])
    assert result.kind == "disagreement"
    assert result.verdict.verdict == "INCONCLUSIVE"
    assert "DISAGREEMENT" in result.verdict.reasoning
    # Both shot reasonings quoted in the disagreement note
    assert "UPF is the source" in result.verdict.reasoning
    assert "consistent with the evidence" in result.verdict.reasoning


def test_two_shot_disagreement_preserves_alt_suspects_union():
    """Even on disagreement, alt_suspects from both shots flow into
    Decision E's pool aggregator. Keeping the union maximizes the
    chance of catching the right NF downstream."""
    s1 = _v(verdict="DISPROVEN", alt_suspects=["upf", "rtpengine"])
    s2 = _v(verdict="NOT_DISPROVEN", alt_suspects=["pcscf"])  # unusual but possible
    result = reconcile_verdicts([s1, s2])
    assert result.verdict.verdict == "INCONCLUSIVE"
    assert sorted(result.verdict.alternative_suspects) == [
        "pcscf", "rtpengine", "upf",
    ]


def test_two_shot_disagreement_truncates_long_reasoning_in_quote():
    long_reasoning = "x" * 2000
    s1 = _v(verdict="DISPROVEN", reasoning=long_reasoning)
    s2 = _v(verdict="NOT_DISPROVEN", reasoning="short")
    result = reconcile_verdicts([s1, s2])
    # Truncation marker present
    assert "…" in result.verdict.reasoning
    # The full 2000-char string is NOT in the output
    assert long_reasoning not in result.verdict.reasoning


# ===========================================================================
# Two-shot with INCONCLUSIVE
# ===========================================================================


def test_two_shot_one_inconclusive_one_disproven_inconclusive():
    s1 = _v(verdict="INCONCLUSIVE", reasoning="couldn't run probes")
    s2 = _v(verdict="DISPROVEN", reasoning="probes contradict")
    result = reconcile_verdicts([s1, s2])
    assert result.verdict.verdict == "INCONCLUSIVE"
    assert result.kind == "disagreement"  # they disagreed in verdict
    assert "INCONCLUSIVE" in result.verdict.reasoning


def test_two_shot_both_inconclusive():
    s1 = _v(verdict="INCONCLUSIVE", reasoning="probes empty")
    s2 = _v(verdict="INCONCLUSIVE", reasoning="probes inconclusive too")
    result = reconcile_verdicts([s1, s2])
    assert result.verdict.verdict == "INCONCLUSIVE"
    assert result.kind == "agreement"


def test_two_shot_inconclusive_with_not_disproven_inconclusive():
    s1 = _v(verdict="NOT_DISPROVEN")
    s2 = _v(verdict="INCONCLUSIVE")
    result = reconcile_verdicts([s1, s2])
    # Even though shot 1 was confidently NOT_DISPROVEN, shot 2's
    # uncertainty wins. Variance reduction principle: if the same
    # plan can produce uncertainty on a second roll, we don't trust
    # the first.
    assert result.verdict.verdict == "INCONCLUSIVE"


# ===========================================================================
# Hypothesis identity preserved
# ===========================================================================


def test_reconciled_verdict_keeps_hypothesis_identity():
    """The reconciled verdict's hypothesis_id and statement come from
    shot 1 (both shots target the same hypothesis so this is just a
    consistency check)."""
    s1 = _v(verdict="NOT_DISPROVEN", hid="h2")
    s2 = _v(verdict="NOT_DISPROVEN", hid="h2")
    result = reconcile_verdicts([s1, s2])
    assert result.verdict.hypothesis_id == "h2"
    assert result.verdict.hypothesis_statement == "test hypothesis"
