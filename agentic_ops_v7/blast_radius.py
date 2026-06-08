"""Phase 8a — deterministic blast-radius compute + template narrative.

Computes the structured downstream impact of a diagnosed failure from
three inputs, with NO LLM and NO graph-DB dependency:

  1. the final diagnosis's root-cause NF(s),
  2. the ontology YAML (`flows.yaml` + `components.yaml`), read directly —
     same precedent as `path_prioritizer.py`, so the compute is
     deterministic, replayable, and unit-testable without a live Neo4j,
  3. this episode's observed evidence already in orchestrator `state`
     (symptom-classifier flags + path-walk attributions).

Potential set = procedures that traverse the down NF (worst case).
Observed set  = of those, which showed corroborating degradation this
                episode. The two combine into one inline `status` tag:
  failing / degraded — observed corroboration on the procedure's path,
  at_risk            — potential only (traverses the down NF, no signal).

ADR: docs/ADR/blast_radius_downstream_impact_phase8.md
"""

from __future__ import annotations

from pathlib import Path as _PathLib
from typing import Any, Optional

import yaml

from .models import (
    AffectedComponent,
    AffectedFlow,
    AffectedService,
    BlastRadius,
)

_REPO_ROOT = _PathLib(__file__).resolve().parents[1]
_FLOWS_PATH = _REPO_ROOT / "network_ontology" / "data" / "flows.yaml"
_COMPONENTS_PATH = _REPO_ROOT / "network_ontology" / "data" / "components.yaml"

# use_case → plain-language service label (the stakeholder-readable layer).
_SERVICE_LABELS = {
    "vonr": "VoNR voice calls",
    "5g_core": "5G data & registration",
    "ims": "IMS signaling",
}

_STATUS_RANK = {"at_risk": 1, "degraded": 2, "failing": 3}

_flows_cache: Optional[dict] = None
_components_cache: Optional[dict] = None


def _load_flows(path: Optional[_PathLib] = None) -> dict:
    global _flows_cache
    if path is None and _flows_cache is not None:
        return _flows_cache
    doc = yaml.safe_load((path or _FLOWS_PATH).read_text()) or {}
    flows = doc.get("flows", {}) or {}
    if path is None:
        _flows_cache = flows
    return flows


def _load_components(path: Optional[_PathLib] = None) -> dict:
    global _components_cache
    if path is None and _components_cache is not None:
        return _components_cache
    doc = yaml.safe_load((path or _COMPONENTS_PATH).read_text()) or {}
    comps = doc.get("components", doc) or {}
    if path is None:
        _components_cache = comps
    return comps


def _flow_nfs(flow_def: dict) -> set[str]:
    """All node names a flow's steps reference (from/to/via)."""
    out: set[str] = set()
    for step in flow_def.get("steps", []) or []:
        if step.get("from"):
            out.add(step["from"])
        if step.get("to"):
            out.add(step["to"])
        for v in step.get("via", []) or []:
            out.add(v)
    return out


def _nf_from_kb_id(kb_metric_id: Optional[str]) -> Optional[str]:
    """Recover the NF from a canonical `<layer>.<nf>.<metric_short>` id.

    The metric short-name can contain colons but no further dots, so a
    2-split on '.' is safe. Mirrors `path_prioritizer._flag_nf_metric`.
    """
    if not kb_metric_id:
        return None
    parts = kb_metric_id.split(".", 2)
    if len(parts) == 3:
        return parts[1]
    return None


def _walker_reports(state: dict) -> list[dict]:
    reps: list[dict] = []
    pwr = state.get("path_walk_report")
    if isinstance(pwr, dict):
        reps.append(pwr)
    allr = state.get("path_walk_all_reports") or {}
    if isinstance(allr, dict):
        reps.extend(r for r in allr.values() if isinstance(r, dict))
    return reps


def _observed_nfs(state: dict) -> tuple[set[str], set[str]]:
    """Return (high-severity, low-severity) observed-degraded NF sets from
    this episode's evidence.

    Sources:
      * symptom_classification flag buckets — NF via kb_metric_id, bucketed
        by the flag's severity (HIGH/MEDIUM → high; else low),
      * path-walk attributions — the attributed hop node is high-severity
        observed evidence.
    """
    high: set[str] = set()
    low: set[str] = set()

    sc = state.get("symptom_classification") or {}
    if isinstance(sc, dict):
        for bucket in ("transport_flags", "application_flags", "ambiguous_flags"):
            for flag in sc.get(bucket, []) or []:
                if not isinstance(flag, dict):
                    continue
                nf = _nf_from_kb_id(flag.get("kb_metric_id"))
                if not nf:
                    continue
                sev = (flag.get("severity") or "").upper()
                if sev in ("HIGH", "MEDIUM"):
                    high.add(nf)
                else:
                    low.add(nf)

    for rep in _walker_reports(state):
        fah = rep.get("first_attributed_hop")
        if isinstance(fah, dict) and fah.get("node"):
            high.add(fah["node"])

    low -= high
    return high, low


def _root_cause_nfs(diagnosis: dict) -> list[str]:
    """Root-cause NF(s) from the diagnosis dict: primary + any compound
    additional_root_causes, de-duplicated, order-preserving."""
    nfs: list[str] = []
    primary = diagnosis.get("primary_suspect_nf")
    if primary:
        nfs.append(primary)
    for rc in diagnosis.get("additional_root_causes") or []:
        n = rc.get("primary_suspect_nf") if isinstance(rc, dict) else None
        if n and n not in nfs:
            nfs.append(n)
    return nfs


def compute_blast_radius(diagnosis: dict, state: dict) -> BlastRadius:
    """Deterministically compute the blast radius from a diagnosis dict.

    Returns an empty `BlastRadius` (no root_cause_nfs) when the diagnosis
    names no root-cause NF — i.e. an inconclusive verdict, where impact is
    undetermined and there is nothing to project from.
    """
    rc_nfs = _root_cause_nfs(diagnosis)
    if not rc_nfs:
        return BlastRadius()

    rc_set = set(rc_nfs)
    flows = _load_flows()
    components = _load_components()
    obs_high, obs_low = _observed_nfs(state)

    # Corroboration must come from NFs OTHER than the root cause — otherwise
    # every flow through the root cause would auto-tag "failing" and the
    # potential-vs-observed distinction collapses.
    sig_high = obs_high - rc_set
    sig_low = obs_low - rc_set

    # Potential flows: procedures whose path traverses a root-cause NF.
    direct = {fid: fd for fid, fd in flows.items() if rc_set & _flow_nfs(fd)}
    if direct:
        potential = direct
    else:
        # Backing-store fallback (e.g. mongo/udr aren't on flow steps):
        # the procedures of the use_case(s) this NF supports per the
        # component ontology.
        rc_use_cases: set[str] = set()
        for nf in rc_nfs:
            uc = (components.get(nf) or {}).get("use_cases") or {}
            for name, spec in uc.items():
                if isinstance(spec, dict) and spec.get("enabled"):
                    rc_use_cases.add(name)
        potential = {
            fid: fd for fid, fd in flows.items()
            if fd.get("use_case") in rc_use_cases
        }

    affected_flows: list[AffectedFlow] = []
    for fid, fd in sorted(potential.items()):
        fnfs = _flow_nfs(fd)
        corro_high = sorted(fnfs & sig_high)
        corro_low = sorted(fnfs & sig_low)
        if corro_high:
            status = "failing"
            evidence = (
                f"observed degradation on {', '.join(corro_high)} along "
                f"this procedure's path this episode"
            )
        elif corro_low:
            status = "degraded"
            evidence = (
                f"low-severity signal on {', '.join(corro_low)} along this "
                f"procedure's path this episode"
            )
        else:
            status = "at_risk"
            evidence = (
                "potential — traverses the diagnosed NF but no degradation "
                "signal observed on this procedure this episode"
            )
        affected_flows.append(AffectedFlow(
            flow_id=fid,
            flow_name=fd.get("name", fid),
            use_case=fd.get("use_case", "unknown"),
            status=status,
            evidence=evidence,
        ))

    # Services: group affected flows by use_case; service status = worst.
    by_use_case: dict[str, list[AffectedFlow]] = {}
    for af in affected_flows:
        by_use_case.setdefault(af.use_case, []).append(af)
    affected_services: list[AffectedService] = []
    for uc, afs in sorted(by_use_case.items()):
        worst = max((a.status for a in afs), key=lambda s: _STATUS_RANK[s])
        affected_services.append(AffectedService(
            service=_SERVICE_LABELS.get(uc, uc),
            status=worst,
            affected_flow_ids=[a.flow_id for a in afs],
        ))

    # Downstream-affected NFs: observed-degraded NFs other than the root
    # cause (role Symptomatic — they reported, they didn't cause).
    affected_nfs = [
        AffectedComponent(name=nf, role="Symptomatic")
        for nf in sorted(sig_high | sig_low)
    ]

    return BlastRadius(
        root_cause_nfs=rc_nfs,
        affected_nfs=affected_nfs,
        affected_flows=affected_flows,
        affected_services=affected_services,
        narrative="",
    )


def render_template_narrative(
    br: BlastRadius,
    verdict_kind: Optional[str] = None,
) -> str:
    """Deterministic prose fallback used when the narrator LLM is
    unavailable or its output fails the grounding guardrail. Built purely
    from the structured fields — grounded by construction.

    `verdict_kind` lets the caller tailor the no-root-cause branch:
    `undetected_fault` (ADR `synthesis_undetected_fault_verdict.md`)
    gets an action-oriented "manual NOC review recommended" line so
    the downstream consumer (operator, scoring rubric, GUI overlay)
    knows the diagnosis is the agent's humble admission, not just
    an inconclusive procedural failure.
    """
    if not br.root_cause_nfs:
        if verdict_kind == "undetected_fault":
            return (
                "No specific fault was localized during this episode. "
                "Anomalous signals were observed but could not be attributed "
                "to a confirmed root cause. Manual NOC review recommended."
            )
        return "Downstream impact undetermined — no root cause was localized."

    rc = ", ".join(f"`{n}`" for n in br.root_cause_nfs)
    n_flows = len(br.affected_flows)
    parts = [
        f"Root cause {rc} impacts {n_flows} "
        f"procedure{'s' if n_flows != 1 else ''}."
    ]
    for label, status in (
        ("Failing", "failing"), ("Degraded", "degraded"), ("At-risk", "at_risk"),
    ):
        svcs = [s.service for s in br.affected_services if s.status == status]
        if svcs:
            parts.append(f"{label} services: {', '.join(svcs)}.")
    return " ".join(parts)
