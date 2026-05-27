"""Phase 8c — grounding guardrail tests.

The narrator may reference only entities in the computed BlastRadius
(root cause, affected NFs, NFs on affected flows, affected flow ids).
Any other known ontology NF or flow id in the narrative is ungrounded.

ADR: docs/ADR/blast_radius_downstream_impact_phase8.md
"""

from __future__ import annotations

from agentic_ops_v7.blast_radius import compute_blast_radius, render_template_narrative
from agentic_ops_v7.guardrails.impact_grounding import check_narrative_grounding


def _br_for_pcscf():
    diagnosis = {"primary_suspect_nf": "pcscf", "additional_root_causes": []}
    state = {
        "symptom_classification": {
            "transport_flags": [],
            "application_flags": [],
            "ambiguous_flags": [
                {"kb_metric_id": "ims.icscf.cdp_replies_per_ue", "severity": "MEDIUM"},
                {"kb_metric_id": "ims.scscf.cdp_replies_per_ue", "severity": "MEDIUM"},
            ],
        }
    }
    return compute_blast_radius(diagnosis, state)


def test_grounded_narrative_passes():
    br = _br_for_pcscf()
    narrative = (
        "The P-CSCF fault is breaking IMS registration; icscf and scscf are "
        "reporting downstream degradation. VoNR voice calls are failing."
    )
    ok, offending = check_narrative_grounding(narrative, br)
    assert ok, f"expected grounded, offending={offending}"


def test_template_narrative_is_self_grounded():
    """The deterministic fallback must always pass its own guardrail."""
    br = _br_for_pcscf()
    ok, offending = check_narrative_grounding(render_template_narrative(br), br)
    assert ok, f"template narrative must be grounded; offending={offending}"


def test_ungrounded_nf_is_rejected():
    """Mentioning an NF not in the blast radius (and not on any affected
    flow) is rejected."""
    br = _br_for_pcscf()
    # `mongo` is unrelated to a pcscf blast radius and not on its flows.
    narrative = "The P-CSCF fault also took down mongo and its database."
    ok, offending = check_narrative_grounding(narrative, br)
    assert not ok
    assert any("mongo" in o for o in offending)


def test_ungrounded_flow_is_rejected():
    br = _br_for_pcscf()
    # Invent a flow id that isn't in the affected set.
    narrative = "This also broke the diameter_cx_authentication procedure."
    ok, offending = check_narrative_grounding(narrative, br)
    # diameter_cx_authentication is a known flow; if it's not in br's
    # affected flows, it must be flagged.
    affected_ids = {f.flow_id for f in br.affected_flows}
    if "diameter_cx_authentication" not in affected_ids:
        assert not ok
        assert any("diameter_cx_authentication" in o for o in offending)


def test_word_boundary_avoids_false_positive():
    """`scp` must not match inside `sctp` etc. — a narrative that doesn't
    actually name an out-of-set NF should pass."""
    br = _br_for_pcscf()
    narrative = "SIP signaling over SCTP transport is affected at the edge proxy."
    ok, offending = check_narrative_grounding(narrative, br)
    assert ok, f"false-positive grounding rejection: {offending}"
