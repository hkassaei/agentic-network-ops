"""Compound verdict — markdown rendering of `additional_root_causes`.

The orchestrator's `_render_diagnosis_report_to_markdown` renders the
DiagnosisReport to the markdown blob that lands in `challenge_result["diagnosis_text"]`
and is displayed as the "Agent Diagnosis" block in the episode log.

Pins that:
  1. `compound` verdict_kind emits a `- **additional_root_causes**:`
     section listing every entry.
  2. Non-compound verdicts emit no such section, even if the field is
     populated defensively.
  3. Empty `additional_root_causes` list emits no section even on
     `compound` — the upstream guardrail should have REJECTed, but the
     renderer is defensive.

See ADR `multi_fault_orchestration.md` and task #62.
"""

from __future__ import annotations

from agentic_ops_v7.models import DiagnosisReport, Localization, RootCause
from agentic_ops_v7.orchestrator import _render_diagnosis_report_to_markdown


def _localization() -> Localization:
    return Localization(
        hop_node="scscf", hop_kind="container", hop_iface="eth0",
        attribution_kind="latency_at_hop",
        counter_kind="qdisc_netem_delay",
        observed_delay_ms=2000.0,
        evidence="qdisc netem 800a: root refcnt 9 limit 1000 delay 2s",
    )


def _compound_report(additional: list[RootCause] | None = None) -> DiagnosisReport:
    if additional is None:
        additional = [
            RootCause(
                primary_suspect_nf="pyhss",
                fault_layer="application",
                evidence_source="investigator",
                evidence_summary="pyhss container exited per get_network_status.",
                confidence="high",
            ),
        ]
    return DiagnosisReport(
        summary="Compound IMS outage.",
        root_cause="scscf latency AND pyhss exited.",
        root_cause_confidence="high",
        primary_suspect_nf="scscf",
        verdict_kind="compound",
        affected_components=[
            {"name": "scscf", "role": "Root Cause"},
            {"name": "pyhss", "role": "Root Cause"},
        ],
        timeline=["step1", "step2"],
        recommendation="Verify scscf qdisc and pyhss status.",
        explanation="Walker localized scscf; NA hypothesized pyhss.",
        localization=_localization(),
        additional_root_causes=additional,
    )


def test_compound_renders_additional_root_causes_section():
    md = _render_diagnosis_report_to_markdown(_compound_report())
    assert "- **additional_root_causes**:" in md
    assert "`pyhss`" in md
    assert "application" in md
    assert "source=`investigator`" in md
    assert "confidence=high" in md
    assert "pyhss container exited per get_network_status." in md


def test_compound_renders_multiple_additional_root_causes():
    md = _render_diagnosis_report_to_markdown(_compound_report(additional=[
        RootCause(
            primary_suspect_nf="pyhss", fault_layer="application",
            evidence_source="investigator",
            evidence_summary="pyhss exited.", confidence="high",
        ),
        RootCause(
            primary_suspect_nf="pcscf", fault_layer="application",
            evidence_source="anomaly_screener",
            evidence_summary="pcscf REGISTER rate dropped.", confidence="medium",
        ),
    ]))
    assert "- `pyhss`" in md
    assert "- `pcscf`" in md
    assert "source=`anomaly_screener`" in md


def test_localized_verdict_does_not_render_additional_causes():
    """Defensive: even if `additional_root_causes` is somehow populated
    on a non-compound report, the renderer doesn't emit the section."""
    report = _compound_report().model_copy(update={"verdict_kind": "localized"})
    md = _render_diagnosis_report_to_markdown(report)
    assert "- **additional_root_causes**:" not in md


def test_compound_with_empty_additional_omits_section():
    report = _compound_report(additional=[])
    md = _render_diagnosis_report_to_markdown(report)
    assert "- **additional_root_causes**:" not in md
