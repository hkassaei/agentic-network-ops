"""Unit tests for guardrails/mechanism_grounding.lint_mechanism_grounding —
Decision G, PR 8.

Pure-Python tests. No KB lookup; PR 8 ships the simpler blocklist-only
form.
"""

from __future__ import annotations

import pytest

from agentic_ops_v6.guardrails.base import GuardrailVerdict
from agentic_ops_v6.guardrails.mechanism_grounding import (
    lint_mechanism_grounding,
)
from agentic_ops_v6.models import (
    Hypothesis,
    LayerStatus,
    NetworkAnalystReport,
)


def _hyp(*, statement: str, hid: str = "h1", nf: str = "upf",
         supporting: list[str] | None = None) -> Hypothesis:
    return Hypothesis(
        id=hid,
        statement=statement,
        primary_suspect_nf=nf,
        supporting_events=supporting or ["evt1"],
        explanatory_fit=0.85,
        falsification_probes=["p"],
        specificity="specific",
    )


def _report(*hypotheses: Hypothesis) -> NetworkAnalystReport:
    return NetworkAnalystReport(
        summary="test",
        layer_status={"core": LayerStatus(rating="red", note="x")},
        hypotheses=list(hypotheses) or [_hyp(statement="default clean")],
    )


# ---------------------------------------------------------------------------
# PASS path
# ---------------------------------------------------------------------------


def test_clean_statement_passes():
    """A statement that names observable + component without inventing
    a mechanism narrative passes cleanly."""
    report = _report(_hyp(
        statement="UPF is the source of the user-plane packet loss observed in dp_quality_gauges.",
    ))
    result = lint_mechanism_grounding(report)
    assert result.verdict is GuardrailVerdict.PASS


def test_multiple_clean_statements_pass():
    report = _report(
        _hyp(hid="h1", nf="upf",
             statement="UPF is the source of packet loss observed in dp_quality_gauges."),
        _hyp(hid="h2", nf="rtpengine",
             statement="RTPEngine is the source of media-plane errors."),
    )
    result = lint_mechanism_grounding(report)
    assert result.verdict is GuardrailVerdict.PASS


# ---------------------------------------------------------------------------
# REJECT path — narrative phrases
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("offending_phrase", [
    "The UPF is overloaded by a massive GTP-U traffic storm.",
    "P-CSCF is hit by a packet storm on the SIP path.",
    "S-CSCF is overloaded by Diameter requests.",  # 'is overloaded by'
    "Bearer setup is failing under an overload condition at SMF.",
    "AMF is flooded by N1 messages from the gNB.",
    "P-CSCF is suffering from flooding from the UE pool.",
    "There is a surge of REGISTERs that the I-CSCF cannot handle.",
    "RTPEngine is experiencing spike-induced packet drops.",
    "There is a congestive failure at the N3 transport.",
    "A congestion event at UPF caused the data plane outage.",
    "There is a network partition between P-CSCF and I-CSCF.",
    "S-CSCF is partitioned from the HSS.",
    "Pyhss is partitioned away from the IMS core.",
    "This is a cascade failure originating at the HSS.",
    "We are seeing a cascading failure across IMS components.",
    "RTPEngine is running out of buffer memory.",
    "UPF is suffering from session-state starvation.",
    "There is a meltdown in the S-CSCF dialog handling.",
    "We are seeing a breakdown of the SIP forwarding chain.",
    "This is a system breakdown in the IMS layer.",
])
def test_narrative_phrases_reject(offending_phrase: str):
    report = _report(_hyp(statement=offending_phrase))
    result = lint_mechanism_grounding(report)
    assert result.verdict is GuardrailVerdict.REJECT, (
        f"Expected REJECT for: {offending_phrase!r}"
    )
    assert "h1" in result.reason
    assert result.notes["flagged_count"] == 1


# ---------------------------------------------------------------------------
# False-positive guards — bare words that have legitimate uses
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("clean_phrase", [
    # Bare 'partition' is a 3GPP partition event, not a fabricated mechanism
    "The IMS partition event triggered the chaos scenario.",
    # 'cascade' as a description of REGISTER chains is legitimate
    "The cascade of REGISTERs after failover is expected behavior.",
    # 'storm' alone in unrelated context
    "The storm of activity began with the first call.",
    # 'collapse' as observed-metric language
    "UPF traffic shows a collapse in dp_quality_gauges activity.",
    # 'exhausted' alone is too vague to flag without a phrase
    "We have exhausted the available probes for this hypothesis.",
    # 'flood' alone (not 'flooded by' or 'flooding from')
    "The flood plain analysis isn't relevant here.",
])
def test_legitimate_uses_dont_false_positive(clean_phrase: str):
    """Bare narrative-adjacent words have legitimate uses; the linter
    only fires on phrase-level patterns to limit false positives."""
    report = _report(_hyp(statement=clean_phrase))
    result = lint_mechanism_grounding(report)
    assert result.verdict is GuardrailVerdict.PASS, (
        f"Expected PASS for: {clean_phrase!r}"
    )


# ---------------------------------------------------------------------------
# Multi-hypothesis behavior
# ---------------------------------------------------------------------------


def test_multi_hypothesis_lists_all_offenders():
    report = _report(
        _hyp(hid="h1", nf="upf",
             statement="UPF is overloaded by a massive traffic storm."),
        _hyp(hid="h2", nf="rtpengine",
             statement="RTPEngine is the source of packet loss."),  # clean
        _hyp(hid="h3", nf="pcscf",
             statement="P-CSCF is suffering from a congestive failure."),
    )
    result = lint_mechanism_grounding(report)
    assert result.verdict is GuardrailVerdict.REJECT
    assert "`h1`" in result.reason
    assert "`h3`" in result.reason
    assert "`h2`" not in result.reason
    assert result.notes["flagged_count"] == 2


def test_reason_includes_dynamic_bad_good_example():
    report = _report(_hyp(
        hid="h1", nf="upf",
        statement="UPF is overloaded by a massive traffic storm.",
        supporting=["core.upf.activity_during_calls_collapsed"],
    ))
    result = lint_mechanism_grounding(report)
    assert result.verdict is GuardrailVerdict.REJECT
    assert "Bad:" in result.reason
    assert "UPF is overloaded by a massive traffic storm." in result.reason
    assert "Good:" in result.reason
    assert "upf is the source of" in result.reason.lower()
    assert "core.upf.activity_during_calls_collapsed" in result.reason


def test_notes_structure_is_recorder_friendly():
    report = _report(_hyp(
        hid="h1", nf="upf",
        statement="UPF is overloaded by a traffic storm.",
    ))
    result = lint_mechanism_grounding(report)
    assert isinstance(result.notes, dict)
    assert result.notes["flagged_count"] == 1
    rows = result.notes["per_hypothesis"]
    assert len(rows) == 1
    assert rows[0]["id"] == "h1"
    assert rows[0]["primary_suspect_nf"] == "upf"
    # Both 'is overloaded by' and 'traffic storm' fire
    assert "traffic storm" in rows[0]["hits"]
    assert "is overloaded by" in rows[0]["hits"]


# ---------------------------------------------------------------------------
# Replay run_20260501_022351_data_plane_degradation — the canonical
# motivating failure mode for Decision G
# ---------------------------------------------------------------------------


def test_replay_run_20260501_022351_traffic_storm_rejects():
    """Post-PR-4 data-plane-degradation run scored 100% on a generous
    scorer despite NA writing a fabricated 'traffic storm' narrative
    that the actual fault (tc-netem at kernel layer) has nothing to
    do with. Decision G catches this directly."""
    report = _report(_hyp(
        hid="h1", nf="upf",
        statement=(
            "The UPF is overloaded by a massive GTP-U traffic storm on the "
            "N3 interface, causing extreme packet loss for all user plane "
            "traffic, including RTP media for VoNR calls."
        ),
        supporting=["core.upf.activity_during_calls_collapsed"],
    ))
    result = lint_mechanism_grounding(report)
    assert result.verdict is GuardrailVerdict.REJECT
    hits = result.notes["per_hypothesis"][0]["hits"]
    assert "traffic storm" in hits
    assert "is overloaded by" in hits


# ---------------------------------------------------------------------------
# Composes correctly when run with a clean statement matching just one
# narrative word (e.g. statement contains the word as part of a legit
# phrase)
# ---------------------------------------------------------------------------


def test_required_shape_and_probe_guidance_in_reason():
    """The rejection reason teaches NA where mechanism intuition can
    legitimately go — falsification_probes / supporting_events grounded
    in KB — so the resample knows what to do."""
    report = _report(_hyp(
        statement="The HSS is overloaded by Diameter requests, causing timeouts.",
    ))
    result = lint_mechanism_grounding(report)
    assert "falsification_probes" in result.reason or "falsification_probe" in result.reason
    assert "supporting_events" in result.reason
    assert "Required shape:" in result.reason
