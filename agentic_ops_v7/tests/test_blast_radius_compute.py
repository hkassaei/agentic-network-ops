"""Phase 8a — deterministic compute_blast_radius tests.

Pins the deterministic core (no LLM): potential set from the ontology,
observed intersection from episode `state`, status tagging, the
backing-store use_case fallback, and the inconclusive empty case.

ADR: docs/ADR/blast_radius_downstream_impact_phase8.md
"""

from __future__ import annotations

from agentic_ops_v7.blast_radius import (
    compute_blast_radius,
    render_template_narrative,
)


def _flag(kb_metric_id: str, severity: str = "MEDIUM") -> dict:
    return {"kb_metric_id": kb_metric_id, "severity": severity, "metric": kb_metric_id}


def _state_with_flags(*flags: dict, walker_node: str | None = None) -> dict:
    state: dict = {
        "symptom_classification": {
            "transport_flags": [],
            "application_flags": [],
            "ambiguous_flags": list(flags),
        }
    }
    if walker_node:
        state["path_walk_report"] = {
            "is_localized": True,
            "first_attributed_hop": {"node": walker_node, "iface": "eth0"},
        }
    return state


# ---------------------------------------------------------------------------
# Inconclusive / empty
# ---------------------------------------------------------------------------


def test_no_root_cause_returns_empty():
    """Inconclusive verdict (no primary_suspect_nf) → empty blast radius,
    no projection."""
    br = compute_blast_radius({"primary_suspect_nf": None}, {})
    assert br.root_cause_nfs == []
    assert br.affected_flows == []
    assert br.affected_services == []
    assert br.narrative == ""
    # Template narrative is honest about the undetermined case.
    assert "undetermined" in render_template_narrative(br).lower()


# ---------------------------------------------------------------------------
# IMS-side root cause (pcscf) — direct flows
# ---------------------------------------------------------------------------


def test_pcscf_root_cause_implicates_ims_flows():
    """pcscf is on the IMS-registration / VoNR-call-setup flow paths. With
    CSCF downstream signal observed, those procedures are `failing` and the
    VoNR service is impacted."""
    diagnosis = {"primary_suspect_nf": "pcscf", "additional_root_causes": []}
    state = _state_with_flags(
        _flag("ims.icscf.cdp_replies_per_ue", "MEDIUM"),
        _flag("ims.scscf.core:rcv_requests_register_per_ue", "MEDIUM"),
    )
    br = compute_blast_radius(diagnosis, state)

    assert br.root_cause_nfs == ["pcscf"]
    flow_ids = {f.flow_id for f in br.affected_flows}
    # pcscf traverses these flows in flows.yaml
    assert "ims_registration" in flow_ids
    # at least one flow is failing (corroborated by icscf/scscf signal)
    assert any(f.status == "failing" for f in br.affected_flows)
    # downstream NFs (icscf/scscf) surfaced as Symptomatic, root cause excluded
    affected_nf_names = {c.name for c in br.affected_nfs}
    assert "icscf" in affected_nf_names or "scscf" in affected_nf_names
    assert "pcscf" not in affected_nf_names
    # a service is reported
    assert br.affected_services
    assert any("VoNR" in s.service or "IMS" in s.service for s in br.affected_services)


def test_pcscf_unexercised_flows_are_at_risk():
    """A flow that traverses pcscf but has no OTHER observed signal on its
    path is `at_risk` (potential), not `failing` — the potential-vs-observed
    distinction."""
    diagnosis = {"primary_suspect_nf": "pcscf", "additional_root_causes": []}
    # Only pcscf itself flagged — no downstream corroboration anywhere.
    state = _state_with_flags(_flag("ims.pcscf.core:rcv_requests_register_per_ue", "MEDIUM"))
    br = compute_blast_radius(diagnosis, state)
    # Every flow is potential (pcscf on path) but none has corroborating
    # non-root-cause signal → all at_risk.
    assert br.affected_flows
    assert all(f.status == "at_risk" for f in br.affected_flows)


# ---------------------------------------------------------------------------
# Data-plane root cause (upf) — direct flows
# ---------------------------------------------------------------------------


def test_upf_root_cause_implicates_data_flows():
    diagnosis = {"primary_suspect_nf": "upf", "additional_root_causes": []}
    state = _state_with_flags(
        _flag("core.upf.gtp_indatapktn3upf_per_ue", "MEDIUM"),
        walker_node="upf",
    )
    br = compute_blast_radius(diagnosis, state)
    assert br.root_cause_nfs == ["upf"]
    flow_ids = {f.flow_id for f in br.affected_flows}
    # upf is on the data-PDU / VoNR-media flows
    assert any("data_pdu" in fid or "vonr_media" in fid for fid in flow_ids)


# ---------------------------------------------------------------------------
# Backing-store fallback (mongo not on any flow step)
# ---------------------------------------------------------------------------


def test_mongo_backing_store_falls_back_to_use_case_flows():
    """mongo is not on any flow step; the compute falls back to the flows
    of the use_case(s) mongo supports (vonr), so impact is still surfaced."""
    diagnosis = {"primary_suspect_nf": "mongo", "additional_root_causes": []}
    state = _state_with_flags(
        _flag("ims.pcscf.sip_error_ratio", "MEDIUM"),
    )
    br = compute_blast_radius(diagnosis, state)
    assert br.root_cause_nfs == ["mongo"]
    # Fallback produced flows (from mongo's vonr use_case), not empty.
    assert br.affected_flows, "backing-store fallback should still surface flows"
    assert all(f.use_case == "vonr" for f in br.affected_flows)


# ---------------------------------------------------------------------------
# Compound (multiple root causes)
# ---------------------------------------------------------------------------


def test_compound_unions_root_cause_flows():
    diagnosis = {
        "primary_suspect_nf": "pyhss",
        "additional_root_causes": [{"primary_suspect_nf": "scscf"}],
    }
    state = _state_with_flags(_flag("ims.scscf.cdp_replies_per_ue", "MEDIUM"))
    br = compute_blast_radius(diagnosis, state)
    assert set(br.root_cause_nfs) == {"pyhss", "scscf"}


# ---------------------------------------------------------------------------
# Status ordering in services
# ---------------------------------------------------------------------------


def test_service_status_is_worst_of_its_flows():
    """If any flow carrying a service is failing, the service is failing."""
    diagnosis = {"primary_suspect_nf": "pcscf", "additional_root_causes": []}
    state = _state_with_flags(
        _flag("ims.icscf.cdp_replies_per_ue", "MEDIUM"),
    )
    br = compute_blast_radius(diagnosis, state)
    for svc in br.affected_services:
        statuses = {
            f.status for f in br.affected_flows if f.flow_id in svc.affected_flow_ids
        }
        # service status == worst (failing > degraded > at_risk)
        rank = {"at_risk": 1, "degraded": 2, "failing": 3}
        assert rank[svc.status] == max(rank[s] for s in statuses)
