"""Tests for the Phase 7 Synthesis localized-verdict consistency guardrail.

The guardrail is the structural backstop against the failure mode
observed in `run_20260510_121231_p_cscf_latency.md` and
`run_20260510_185152_p_cscf_packet_loss.md`: Synthesis emitting
`verdict_kind=localized` with fabricated kernel-counter evidence even
when Phase 0.6's walker null-localized (or never ran). The check is
mechanical:

  verdict_kind == "localized"  ⟹  path_walk_report.is_localized == True

Anything else is a hallucination → REJECT with a resample directive.

These tests pin the four reachable input combinations.
"""

from __future__ import annotations

import pytest

from agentic_ops_v7.guardrails.base import GuardrailVerdict
from agentic_ops_v7.guardrails.synthesis_localized_consistency import (
    lint_localized_verdict_consistency,
)
from agentic_ops_v7.models import DiagnosisReport, Localization


# ─────────────────────────────────────────────────────────────────────
# Helpers — build minimal DiagnosisReports for each verdict_kind.
# ─────────────────────────────────────────────────────────────────────


def _make_report(
    *, verdict_kind: str,
    primary_suspect_nf: str | None,
    localization: Localization | None = None,
) -> DiagnosisReport:
    return DiagnosisReport(
        summary="test summary",
        root_cause="test root cause",
        root_cause_confidence="high",
        primary_suspect_nf=primary_suspect_nf,
        verdict_kind=verdict_kind,
        affected_components=[{"name": "test", "role": "Root Cause"}],
        timeline=["t0"],
        recommendation="inspect test",
        explanation="test explanation",
        localization=localization,
    )


def _make_localization() -> Localization:
    return Localization(
        hop_node="rtpengine",
        hop_kind="container",
        hop_iface="eth0",
        attribution_kind="drops_attributed_here",
        counter_kind="qdisc_netem",
        dropped_pkts=300,
        dropped_pct=0.30,
        observed_delay_ms=None,
        evidence=(
            "rtpengine[eth0] qdisc=netem: dropped 300 (30.00%)\n"
            "qdisc netem 8001: root refcnt 2 loss 30%"
        ),
    )


def _localized_walker_report() -> dict:
    """A path_walk_report dict shape matching what `_path_walk_report_to_dict`
    produces when the walker successfully attributed a hop."""
    return {
        "flow_id": "vonr_media",
        "direction": "both",
        "is_localized": True,
        "first_attributed_hop": {
            "node": "rtpengine", "kind": "container", "iface": "eth0",
        },
        "hops": [
            {"hop": {"node": "rtpengine", "kind": "container", "iface": "eth0"},
             "attribution": {"kind": "drops_attributed_here"},
             "prober": "KernelHopProber"},
        ],
    }


def _null_localized_walker_report() -> dict:
    """Walker ran but no hop attributed the fault — the symptom turned
    out to be application-layer after all (the orchestrator falls
    through to the app-layer pipeline after this)."""
    return {
        "flow_id": "ims_registration",
        "direction": "both",
        "is_localized": False,
        "first_attributed_hop": None,
        "hops": [
            {"hop": {"node": "pcscf", "kind": "container", "iface": "eth0"},
             "attribution": {"kind": "clean"},
             "prober": "KernelHopProber"},
        ],
    }


# ─────────────────────────────────────────────────────────────────────
# REJECT cases — the hallucination failure modes
# ─────────────────────────────────────────────────────────────────────


def test_rejects_localized_when_path_walk_report_is_none():
    """The original 2026-05-10 121231_p_cscf_latency failure mode.
    Synthesis emits verdict_kind=localized but Phase 0.6 was never
    engaged (application_layer classifier label) — there's no
    path_walk_report in state at all.
    """
    report = _make_report(
        verdict_kind="localized",
        primary_suspect_nf="nr_gnb",
        localization=_make_localization(),
    )
    result = lint_localized_verdict_consistency(report, path_walk_report=None)
    assert result.verdict is GuardrailVerdict.REJECT
    assert "did not run the transport-layer path walk" in result.reason
    assert result.notes["path_walk_engaged"] is False
    assert result.notes["submitted_verdict_kind"] == "localized"


def test_rejects_localized_when_walker_null_localized():
    """The 2026-05-10 185152_p_cscf_packet_loss failure mode.
    Phase 0.6 ran but the walker returned is_localized=False (the
    resolver walked a wrong flow that didn't contain the fault, or
    the fault is genuinely application-layer). The orchestrator falls
    through to the app-layer pipeline; the LLM-emitted localized
    verdict is not backed by any walker attribution.
    """
    report = _make_report(
        verdict_kind="localized",
        primary_suspect_nf="pcscf",
        localization=_make_localization(),
    )
    result = lint_localized_verdict_consistency(
        report, path_walk_report=_null_localized_walker_report(),
    )
    assert result.verdict is GuardrailVerdict.REJECT
    assert "null-localization" in result.reason
    assert result.notes["path_walk_engaged"] is True
    assert result.notes["path_walk_is_localized"] is False


# ─────────────────────────────────────────────────────────────────────
# PASS cases — consistent verdicts
# ─────────────────────────────────────────────────────────────────────


def test_passes_localized_when_walker_actually_localized():
    """The legitimate localized branch: walker localized at a hop,
    LLM emits a matching verdict_kind=localized diagnosis. This is
    what every transport-layer scenario should look like."""
    report = _make_report(
        verdict_kind="localized",
        primary_suspect_nf="rtpengine",
        localization=_make_localization(),
    )
    result = lint_localized_verdict_consistency(
        report, path_walk_report=_localized_walker_report(),
    )
    assert result.verdict is GuardrailVerdict.PASS


@pytest.mark.parametrize("verdict_kind,primary_suspect_nf", [
    ("confirmed", "pcscf"),
    ("promoted", "upf"),
    ("inconclusive", None),
])
def test_passes_irrelevant_verdict_kinds_regardless_of_walker_state(
    verdict_kind, primary_suspect_nf,
):
    """For confirmed/promoted/inconclusive the guardrail is a no-op.
    Those verdict_kinds are governed by `synthesis_pool` and
    `confidence_cap`; this guardrail's only job is to police the
    `localized` verdict_kind. Parametrized across all three to assert
    the no-op cleanly across walker states."""
    report = _make_report(
        verdict_kind=verdict_kind, primary_suspect_nf=primary_suspect_nf,
    )

    # No matter what the walker did, the guardrail must PASS.
    for path_walk_report in (
        None,
        _null_localized_walker_report(),
        _localized_walker_report(),
    ):
        result = lint_localized_verdict_consistency(
            report, path_walk_report=path_walk_report,
        )
        assert result.verdict is GuardrailVerdict.PASS, (
            f"verdict_kind={verdict_kind} with path_walk_report="
            f"{path_walk_report} should PASS — only `localized` is policed"
        )


# ─────────────────────────────────────────────────────────────────────
# Edge cases
# ─────────────────────────────────────────────────────────────────────


def test_rejects_localized_when_path_walk_report_missing_is_localized_key():
    """Defensive: a malformed path_walk_report dict that's missing the
    `is_localized` key should be treated as null-localization
    (dict.get default behavior). REJECT.
    """
    report = _make_report(
        verdict_kind="localized",
        primary_suspect_nf="pcscf",
        localization=_make_localization(),
    )
    malformed = {"flow_id": "vonr_media"}  # no is_localized
    result = lint_localized_verdict_consistency(report, path_walk_report=malformed)
    assert result.verdict is GuardrailVerdict.REJECT
    assert result.notes["path_walk_engaged"] is True
    assert result.notes["path_walk_is_localized"] is False


def test_reject_reason_mentions_first_attributed_hop_node_when_available():
    """The rejection reason should surface the walker's
    `first_attributed_hop.node` (if any) so the resample LLM has
    concrete context to anchor on."""
    report = _make_report(
        verdict_kind="localized",
        primary_suspect_nf="pcscf",
        localization=_make_localization(),
    )
    walker = _null_localized_walker_report()
    walker["first_attributed_hop"] = {
        "node": "rtpengine", "kind": "container", "iface": "eth0",
    }
    result = lint_localized_verdict_consistency(report, path_walk_report=walker)
    assert result.verdict is GuardrailVerdict.REJECT
    assert "rtpengine" in result.reason
