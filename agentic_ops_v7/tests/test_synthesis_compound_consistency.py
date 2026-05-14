"""Compound-verdict consistency guardrails.

Tests `lint_compound_verdict_consistency` and
`lint_compound_additional_causes` against synthetic `DiagnosisReport`
fixtures. No LLM involved — these are pure post-emit invariant checks
per ADR `multi_fault_orchestration.md`.
"""

from __future__ import annotations

import pytest

from agentic_ops_v7.guardrails.base import GuardrailVerdict
from agentic_ops_v7.guardrails.synthesis_compound_consistency import (
    lint_compound_additional_causes,
    lint_compound_verdict_consistency,
)
from agentic_ops_v7.models import DiagnosisReport, Localization, RootCause


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _localization() -> Localization:
    return Localization(
        hop_node="scscf", hop_kind="container", hop_iface="eth0",
        attribution_kind="latency_at_hop",
        counter_kind="qdisc_netem_delay",
        dropped_pkts=0, dropped_pct=None, observed_delay_ms=2000.0,
        evidence="qdisc netem 800a: root refcnt 9 limit 1000 delay 2s",
    )


def _root_cause(
    nf: str = "pyhss",
    fault_layer: str = "application",
    evidence_source: str = "investigator",
) -> RootCause:
    return RootCause(
        primary_suspect_nf=nf,
        fault_layer=fault_layer,
        evidence_source=evidence_source,
        evidence_summary="pyhss container exited per get_network_status",
        confidence="high",
    )


def _compound_report(
    *,
    additional: list[RootCause] | None = None,
    primary_nf: str = "scscf",
) -> DiagnosisReport:
    return DiagnosisReport(
        summary="Compound IMS outage.",
        root_cause="scscf latency AND pyhss exited.",
        root_cause_confidence="high",
        primary_suspect_nf=primary_nf,
        verdict_kind="compound",
        affected_components=[
            {"name": "scscf", "role": "Root Cause"},
            {"name": "pyhss", "role": "Root Cause"},
        ],
        timeline=["walk", "attribution", "synthesis"],
        recommendation="Inspect tc qdisc on scscf; check pyhss status.",
        explanation="Walker localized scscf; NA hypothesized pyhss.",
        localization=_localization(),
        additional_root_causes=additional if additional is not None else [_root_cause()],
    )


def _localized_report() -> DiagnosisReport:
    return DiagnosisReport(
        summary="Transport-layer fault localized to scscf.",
        root_cause="Kernel-level packet delay on scscf.",
        root_cause_confidence="high",
        primary_suspect_nf="scscf",
        verdict_kind="localized",
        affected_components=[{"name": "scscf", "role": "Root Cause"}],
        timeline=["walk", "attribution"],
        recommendation="Inspect tc qdisc.",
        explanation="Walker localized scscf at 2000ms.",
        localization=_localization(),
    )


_PATH_WALK_LOCALIZED = {
    "is_localized": True,
    "first_attributed_hop": {"node": "scscf", "iface": "eth0", "kind": "container"},
    "hops": [],
}
_PATH_WALK_NULL = {"is_localized": False, "first_attributed_hop": None, "hops": []}
_NA_BUNDLE = "## NA: hypothesis 1 — pyhss exited"


# ---------------------------------------------------------------------------
# lint_compound_verdict_consistency
# ---------------------------------------------------------------------------


def test_compound_consistency_passes_when_both_bundles_present():
    result = lint_compound_verdict_consistency(
        _compound_report(),
        path_walk_report=_PATH_WALK_LOCALIZED,
        network_analysis=_NA_BUNDLE,
    )
    assert result.verdict is GuardrailVerdict.PASS


def test_compound_consistency_rejects_when_walker_absent():
    """No walker bundle → resampler is told to use application-layer
    rules (since NA evidence exists)."""
    result = lint_compound_verdict_consistency(
        _compound_report(),
        path_walk_report=None,
        network_analysis=_NA_BUNDLE,
    )
    assert result.verdict is GuardrailVerdict.REJECT
    assert "walker" in result.reason.lower() or "path-walk" in result.reason.lower()
    assert "application-layer" in result.reason.lower()
    assert result.notes["rejection_branch"] == "application-layer"


def test_compound_consistency_rejects_when_walker_null_localized():
    result = lint_compound_verdict_consistency(
        _compound_report(),
        path_walk_report=_PATH_WALK_NULL,
        network_analysis=_NA_BUNDLE,
    )
    assert result.verdict is GuardrailVerdict.REJECT
    assert result.notes["walker_localized"] is False


def test_compound_consistency_rejects_when_na_absent():
    result = lint_compound_verdict_consistency(
        _compound_report(),
        path_walk_report=_PATH_WALK_LOCALIZED,
        network_analysis=None,
    )
    assert result.verdict is GuardrailVerdict.REJECT
    assert "localized" in result.reason.lower()  # degrade-to-localized hint


def test_compound_consistency_rejects_when_both_absent():
    """Worst case: LLM emitted `compound` with neither bundle. Resampler
    is told to emit `inconclusive`."""
    result = lint_compound_verdict_consistency(
        _compound_report(),
        path_walk_report=None,
        network_analysis=None,
    )
    assert result.verdict is GuardrailVerdict.REJECT
    assert "inconclusive" in result.reason.lower()


@pytest.mark.parametrize("vk", ["confirmed", "promoted", "inconclusive", "localized"])
def test_compound_consistency_passes_through_other_verdicts(vk):
    """The guardrail is a no-op for every non-compound verdict."""
    report = _localized_report().model_copy(update={"verdict_kind": vk})
    if vk == "inconclusive":
        report = report.model_copy(update={"primary_suspect_nf": None})
    result = lint_compound_verdict_consistency(
        report,
        path_walk_report=None,
        network_analysis=None,
    )
    assert result.verdict is GuardrailVerdict.PASS


# ---------------------------------------------------------------------------
# lint_compound_additional_causes
# ---------------------------------------------------------------------------


def test_compound_additional_causes_passes_on_valid_list():
    result = lint_compound_additional_causes(_compound_report())
    assert result.verdict is GuardrailVerdict.PASS


def test_compound_additional_causes_rejects_empty_list():
    """Compound with no additional causes carries no compound information —
    resampler is told to use `localized` instead."""
    report = _compound_report(additional=[])
    result = lint_compound_additional_causes(report)
    assert result.verdict is GuardrailVerdict.REJECT
    assert "empty" in result.reason.lower()
    assert "localized" in result.reason.lower()


def test_compound_additional_causes_rejects_duplicate_of_primary():
    """An entry duplicating the primary slot's NF carries no new
    information — must be a different NF."""
    report = _compound_report(
        primary_nf="scscf",
        additional=[_root_cause(nf="scscf")],  # duplicate of primary
    )
    result = lint_compound_additional_causes(report)
    assert result.verdict is GuardrailVerdict.REJECT
    assert "duplicate" in result.reason.lower() or "different" in result.reason.lower()


def test_compound_additional_causes_passes_multiple_distinct_nfs():
    """Two distinct additional NFs are legitimate (e.g. a three-fault
    scenario)."""
    report = _compound_report(
        primary_nf="scscf",
        additional=[
            _root_cause(nf="pyhss"),
            _root_cause(nf="pcscf"),
        ],
    )
    result = lint_compound_additional_causes(report)
    assert result.verdict is GuardrailVerdict.PASS


@pytest.mark.parametrize("vk", ["confirmed", "promoted", "inconclusive", "localized"])
def test_compound_additional_causes_passes_through_other_verdicts(vk):
    """No-op for every non-compound verdict — even if `additional_root_causes`
    is somehow populated (it shouldn't be, but defensive)."""
    report = _localized_report().model_copy(update={"verdict_kind": vk})
    if vk == "inconclusive":
        report = report.model_copy(update={"primary_suspect_nf": None})
    result = lint_compound_additional_causes(report)
    assert result.verdict is GuardrailVerdict.PASS


# ---------------------------------------------------------------------------
# Pydantic schema — additional_root_causes default behavior
# ---------------------------------------------------------------------------


def test_diagnosis_report_default_additional_root_causes_is_empty_list():
    """Existing single-suspect reports (every non-compound verdict) emit
    no `additional_root_causes`. The Pydantic default must keep them
    parseable and ensure the field is always a list."""
    report = _localized_report()
    assert report.additional_root_causes == []
    # Round-trip through model_dump + model_validate stays valid.
    payload = report.model_dump(mode="json")
    rehydrated = DiagnosisReport.model_validate(payload)
    assert rehydrated.additional_root_causes == []


def test_root_cause_evidence_source_literal_rejects_invalid():
    """Pydantic Literal on `evidence_source` catches typos at parse time
    (defense-in-depth alongside the runtime guardrail)."""
    with pytest.raises(Exception):  # ValidationError
        RootCause(
            primary_suspect_nf="pyhss",
            fault_layer="application",
            evidence_source="hallucinated",  # invalid
            evidence_summary="x",
            confidence="high",
        )


def test_root_cause_fault_layer_literal_rejects_invalid():
    with pytest.raises(Exception):
        RootCause(
            primary_suspect_nf="pyhss",
            fault_layer="weather",  # invalid
            evidence_source="investigator",
            evidence_summary="x",
            confidence="high",
        )
