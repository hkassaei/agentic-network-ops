"""Recorder — Blast Radius & Downstream Impact section rendering.

Pins that `_format_blast_radius` renders the structured fields + narrative,
omits the section cleanly when blast_radius is absent (pre-Phase-8 episodes),
and renders the "undetermined" note for an empty (inconclusive) blast radius.

ADR: docs/ADR/blast_radius_downstream_impact_phase8.md
"""

from __future__ import annotations

from agentic_chaos.recorder import _format_blast_radius


def test_absent_blast_radius_omits_section():
    assert _format_blast_radius(None) == []
    assert _format_blast_radius({}) == []
    assert _format_blast_radius("not a dict") == []


def test_inconclusive_blast_radius_renders_undetermined():
    br = {"root_cause_nfs": [], "affected_flows": [], "affected_services": [],
          "affected_nfs": [], "narrative": ""}
    md = "\n".join(_format_blast_radius(br))
    assert "## Blast Radius & Downstream Impact" in md
    assert "undetermined" in md.lower()


def test_full_blast_radius_renders_all_parts():
    br = {
        "root_cause_nfs": ["pcscf"],
        "narrative": "P-CSCF fault is breaking IMS registration; VoNR calls failing.",
        "affected_services": [
            {"service": "VoNR voice calls", "status": "failing",
             "affected_flow_ids": ["ims_registration"]},
        ],
        "affected_flows": [
            {"flow_id": "ims_registration", "flow_name": "IMS Registration",
             "use_case": "vonr", "status": "failing",
             "evidence": "observed degradation on icscf, scscf"},
            {"flow_id": "vonr_call_setup", "flow_name": "VoNR Call Setup",
             "use_case": "vonr", "status": "at_risk",
             "evidence": "potential — no direct signal this episode"},
        ],
        "affected_nfs": [
            {"name": "icscf", "role": "Symptomatic"},
            {"name": "scscf", "role": "Symptomatic"},
        ],
    }
    md = "\n".join(_format_blast_radius(br))
    # narrative
    assert "breaking IMS registration" in md
    # services section with status badges
    assert "### Affected Services" in md
    assert "VoNR voice calls" in md
    # procedures table
    assert "### Affected Procedures" in md
    assert "`ims_registration`" in md
    assert "`vonr_call_setup`" in md
    assert "failing" in md and "at-risk" in md
    # downstream NFs
    assert "`icscf`" in md and "`scscf`" in md
