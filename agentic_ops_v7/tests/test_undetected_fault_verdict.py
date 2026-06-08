"""Tests for ADR `synthesis_undetected_fault_verdict.md`.

Covers:
  - Schema-level validator on DiagnosisReport for `undetected_fault`
  - `lint_synthesis_no_overclaim` guardrail behavior
  - `synthesis_pool` short-circuit for `undetected_fault`
  - Phase 8 (blast_radius) handling of empty-root-cause case with
    verdict_kind-aware narrator
  - `measure_rtt` and `get_network_status` OUT_OF_SCOPE responses
  - `OUT_OF_SCOPE_CONTAINERS` constant integrity
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agentic_ops_v7.blast_radius import (
    compute_blast_radius,
    render_template_narrative,
)
from agentic_ops_v7.guardrails.base import GuardrailVerdict
from agentic_ops_v7.guardrails.synthesis_no_overclaim import (
    lint_synthesis_no_overclaim,
)
from agentic_ops_v7.guardrails.synthesis_pool import (
    CandidatePool,
    lint_synthesis_pool_membership,
)
from agentic_ops_v7.models import (
    AffectedComponent,
    DiagnosisReport,
    InvestigatorVerdict,
    Localization,
    RootCause,
)


# =========================================================================
# Helpers
# =========================================================================

def _mk_verdict(hid: str, verdict: str) -> InvestigatorVerdict:
    return InvestigatorVerdict(
        hypothesis_id=hid,
        hypothesis_statement=f"{hid} is the source",
        verdict=verdict,
        reasoning="...",
    )


def _mk_undetected_report() -> DiagnosisReport:
    return DiagnosisReport(
        summary="Investigation completed without identifying a specific root cause.",
        root_cause="undetected — investigation completed without confirmation",
        root_cause_confidence="low",
        verdict_kind="undetected_fault",
        recommendation="Manual NOC review recommended.",
        explanation="All hypotheses were disproven or inconclusive.",
    )


def _mk_confirmed_report(nf: str = "upf") -> DiagnosisReport:
    return DiagnosisReport(
        summary=f"{nf} is the root cause.",
        root_cause=f"Packet loss at {nf}",
        root_cause_confidence="high",
        verdict_kind="confirmed",
        primary_suspect_nf=nf,
        affected_components=[AffectedComponent(name=nf, role="Root Cause")],
        recommendation="Inspect interface counters.",
        explanation="One hypothesis survived investigation.",
    )


# =========================================================================
# Schema-level validation on DiagnosisReport
# =========================================================================

class TestDiagnosisReportUndetectedFaultSchema:
    """The pydantic model_validator must reject malformed undetected_fault."""

    def test_valid_undetected_fault_accepted(self):
        r = _mk_undetected_report()
        assert r.verdict_kind == "undetected_fault"
        assert r.primary_suspect_nf is None
        assert r.affected_components == []
        assert r.localization is None
        assert r.additional_root_causes == []

    def test_undetected_fault_rejects_primary_suspect(self):
        with pytest.raises(ValidationError, match="primary_suspect_nf=None"):
            DiagnosisReport(
                summary="x", root_cause="x", root_cause_confidence="low",
                verdict_kind="undetected_fault",
                primary_suspect_nf="pyhss",
                recommendation="x", explanation="x",
            )

    def test_undetected_fault_rejects_affected_components(self):
        with pytest.raises(ValidationError, match="affected_components"):
            DiagnosisReport(
                summary="x", root_cause="x", root_cause_confidence="low",
                verdict_kind="undetected_fault",
                affected_components=[AffectedComponent(name="upf", role="Root Cause")],
                recommendation="x", explanation="x",
            )

    def test_undetected_fault_rejects_additional_root_causes(self):
        with pytest.raises(ValidationError, match="additional_root_causes"):
            DiagnosisReport(
                summary="x", root_cause="x", root_cause_confidence="low",
                verdict_kind="undetected_fault",
                additional_root_causes=[RootCause(
                    primary_suspect_nf="upf",
                    fault_layer="application",
                    evidence_source="investigator",
                    evidence_summary="x",
                    confidence="low",
                )],
                recommendation="x", explanation="x",
            )

    def test_existing_verdict_kinds_unaffected(self):
        # Existing verdicts continue to validate normally
        r = _mk_confirmed_report()
        assert r.verdict_kind == "confirmed"
        assert r.primary_suspect_nf == "upf"


# =========================================================================
# synthesis_no_overclaim guardrail
# =========================================================================

class TestSynthesisNoOverclaimGuardrail:

    def test_all_disproven_undetected_fault_passes(self):
        verdicts = [_mk_verdict("h1", "DISPROVEN"), _mk_verdict("h2", "INCONCLUSIVE")]
        report = _mk_undetected_report()
        r = lint_synthesis_no_overclaim(report, verdicts)
        assert r.verdict == GuardrailVerdict.PASS

    def test_all_disproven_promoted_rejected(self):
        """The exact failure mode from the forcing run."""
        verdicts = [
            _mk_verdict("h1", "DISPROVEN"),
            _mk_verdict("h2", "INCONCLUSIVE"),
            _mk_verdict("h3", "DISPROVEN"),
        ]
        report = DiagnosisReport(
            summary="x", root_cause="x", root_cause_confidence="low",
            verdict_kind="promoted", primary_suspect_nf="nr_gnb",
            recommendation="x", explanation="x",
        )
        r = lint_synthesis_no_overclaim(report, verdicts)
        assert r.verdict == GuardrailVerdict.REJECT
        assert "undetected_fault" in r.reason
        assert "no_overclaim" in r.reason or "over-claim" in r.reason.lower()

    def test_all_disproven_confirmed_rejected(self):
        verdicts = [_mk_verdict("h1", "DISPROVEN"), _mk_verdict("h2", "INCONCLUSIVE")]
        report = DiagnosisReport(
            summary="x", root_cause="x", root_cause_confidence="low",
            verdict_kind="confirmed", primary_suspect_nf="upf",
            recommendation="x", explanation="x",
        )
        r = lint_synthesis_no_overclaim(report, verdicts)
        assert r.verdict == GuardrailVerdict.REJECT

    def test_all_disproven_inconclusive_rejected(self):
        """The previous behavior (emitting inconclusive when nothing confirmed)
        is now rejected — undetected_fault is the only valid output."""
        verdicts = [_mk_verdict("h1", "DISPROVEN")]
        report = DiagnosisReport(
            summary="x", root_cause="x", root_cause_confidence="low",
            verdict_kind="inconclusive",
            recommendation="x", explanation="x",
        )
        r = lint_synthesis_no_overclaim(report, verdicts)
        assert r.verdict == GuardrailVerdict.REJECT

    def test_one_not_disproven_confirmed_passes(self):
        verdicts = [_mk_verdict("h1", "NOT_DISPROVEN"), _mk_verdict("h2", "DISPROVEN")]
        report = _mk_confirmed_report()
        r = lint_synthesis_no_overclaim(report, verdicts)
        assert r.verdict == GuardrailVerdict.PASS

    def test_one_not_disproven_undetected_fault_rejected(self):
        """undetected_fault is invalid when there IS a confirmed hypothesis."""
        verdicts = [_mk_verdict("h1", "NOT_DISPROVEN"), _mk_verdict("h2", "DISPROVEN")]
        report = _mk_undetected_report()
        r = lint_synthesis_no_overclaim(report, verdicts)
        assert r.verdict == GuardrailVerdict.REJECT
        assert "NOT_DISPROVEN" in r.reason

    def test_localized_short_circuits_pass(self):
        """Walker-evidence verdicts don't depend on hypothesis confirmation."""
        verdicts = [_mk_verdict("h1", "DISPROVEN")]  # all-disproven
        report = DiagnosisReport(
            summary="x", root_cause="x", root_cause_confidence="high",
            verdict_kind="localized", primary_suspect_nf="upf",
            localization=Localization(
                hop_node="upf", hop_kind="container", hop_iface="eth0",
                attribution_kind="drops_attributed_here",
                counter_kind="qdisc_netem",
                evidence="qdisc netem ... drop 30%",
            ),
            affected_components=[AffectedComponent(name="upf", role="Root Cause")],
            recommendation="x", explanation="x",
        )
        r = lint_synthesis_no_overclaim(report, verdicts)
        assert r.verdict == GuardrailVerdict.PASS, (
            "localized verdict_kind must short-circuit regardless of "
            "hypothesis verdicts (walker evidence is independent)"
        )

    def test_compound_short_circuits_pass(self):
        verdicts = [_mk_verdict("h1", "DISPROVEN")]
        report = DiagnosisReport(
            summary="x", root_cause="x", root_cause_confidence="high",
            verdict_kind="compound", primary_suspect_nf="upf",
            localization=Localization(
                hop_node="upf", hop_kind="container", hop_iface="eth0",
                attribution_kind="drops_attributed_here",
                counter_kind="qdisc_netem",
                evidence="x",
            ),
            additional_root_causes=[RootCause(
                primary_suspect_nf="pyhss", fault_layer="application",
                evidence_source="investigator", evidence_summary="x",
                confidence="medium",
            )],
            affected_components=[AffectedComponent(name="upf", role="Root Cause")],
            recommendation="x", explanation="x",
        )
        r = lint_synthesis_no_overclaim(report, verdicts)
        assert r.verdict == GuardrailVerdict.PASS

    def test_guardrail_notes_carry_verdict_counts(self):
        verdicts = [
            _mk_verdict("h1", "DISPROVEN"),
            _mk_verdict("h2", "DISPROVEN"),
            _mk_verdict("h3", "INCONCLUSIVE"),
        ]
        report = _mk_undetected_report()
        r = lint_synthesis_no_overclaim(report, verdicts)
        assert r.notes["verdict_counts"]["DISPROVEN"] == 2
        assert r.notes["verdict_counts"]["INCONCLUSIVE"] == 1
        assert r.notes["verdict_counts"]["NOT_DISPROVEN"] == 0


# =========================================================================
# synthesis_pool short-circuit for undetected_fault
# =========================================================================

class TestSynthesisPoolUndetectedFaultShortCircuit:

    def test_undetected_fault_bypasses_pool_membership(self):
        """undetected_fault carries no named suspect — pool membership
        has no meaning. The dedicated synthesis_pool guardrail must
        short-circuit PASS."""
        report = _mk_undetected_report()
        # Even with an empty pool (the case that used to require
        # verdict_kind=inconclusive), undetected_fault is now PASS
        empty_pool = CandidatePool(members=[])
        r = lint_synthesis_pool_membership(report, empty_pool)
        assert r.verdict == GuardrailVerdict.PASS


# =========================================================================
# Phase 8 (Blast Radius) handling
# =========================================================================

class TestPhase8UndetectedFaultHandling:

    def test_compute_blast_radius_empty_for_undetected_fault(self):
        """undetected_fault enforces primary_suspect_nf=None, so the
        deterministic compute returns an empty BlastRadius."""
        diagnosis = {
            "verdict_kind": "undetected_fault",
            "primary_suspect_nf": None,
            "affected_components": [],
            "additional_root_causes": [],
        }
        state = {"symptom_classification": {}, "path_walk_report": None}
        br = compute_blast_radius(diagnosis, state)
        assert br.root_cause_nfs == []
        assert br.affected_flows == []
        assert br.affected_services == []

    def test_template_narrative_undetected_fault_says_manual_review(self):
        """The narrator must emit the humble-admission framing for
        undetected_fault, not the generic 'undetermined' phrase."""
        from agentic_ops_v7.models import BlastRadius
        br = BlastRadius()
        narr = render_template_narrative(br, verdict_kind="undetected_fault")
        assert "No specific fault was localized" in narr
        assert "Manual NOC review recommended" in narr

    def test_template_narrative_legacy_inconclusive_unchanged(self):
        """When no verdict_kind is passed (legacy callers), preserve the
        existing 'undetermined' message."""
        from agentic_ops_v7.models import BlastRadius
        br = BlastRadius()
        narr = render_template_narrative(br)
        assert "undetermined" in narr.lower()


# =========================================================================
# Task A — OUT_OF_SCOPE tool error messages: tested at the v1.5 layer.
# See agentic_ops/tests/test_out_of_scope_tool_boundary.py — kept there
# because the v7 self-containment CI gate
# (test_v7_has_no_prior_version_imports) forbids `from agentic_ops.X`
# inside v7. The tool implementations live in agentic_ops/tools.py and
# the constants live in agentic_ops/models.py, so the tests have to
# live with the package they exercise.
# =========================================================================
