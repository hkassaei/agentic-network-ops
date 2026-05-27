"""Phase 8c — grounding guardrail for the impact narrator.

Makes "the narrator invents nothing" a STRUCTURAL guarantee, not a prompt
aspiration. The narrative may reference only entities present in the
deterministically-computed `BlastRadius`:

  * NFs: the root cause(s), the affected (Symptomatic) NFs, and any NF on
    an affected procedure's path,
  * flows: the affected flow ids,

Any KNOWN ontology NF or flow id mentioned in the narrative that is NOT in
that allowed set is an ungrounded reference → the narrative is rejected.

The check is deterministic (no LLM). On rejection the orchestrator
resamples the narrator once, then falls back to the deterministic template
narrative, so the report always ships grounded prose.

ADR: docs/ADR/blast_radius_downstream_impact_phase8.md
"""

from __future__ import annotations

import re

from ..blast_radius import _flow_nfs, _load_components, _load_flows
from ..models import BlastRadius


def _allowed_nfs(br: BlastRadius) -> set[str]:
    """Every NF the narrator may name: root cause(s) + affected NFs + all
    NFs on the paths of affected flows."""
    allowed = {n.lower() for n in br.root_cause_nfs}
    allowed |= {c.name.lower() for c in br.affected_nfs}
    flows = _load_flows()
    for af in br.affected_flows:
        fd = flows.get(af.flow_id)
        if fd:
            allowed |= {nf.lower() for nf in _flow_nfs(fd)}
    return allowed


def check_narrative_grounding(
    narrative: str, br: BlastRadius,
) -> tuple[bool, list[str]]:
    """Return (is_grounded, offending_references).

    Scans the narrative for any KNOWN ontology NF name or flow id that is
    not in the blast radius's allowed set. Word-boundary matching so e.g.
    `scp` does not match inside `sctp`.
    """
    if not narrative:
        return True, []  # empty narrative is handled by the caller

    text = narrative.lower()
    offending: list[str] = []

    allowed_nfs = _allowed_nfs(br)
    for nf in {n.lower() for n in _load_components().keys()}:
        if nf in allowed_nfs:
            continue
        if re.search(rf"\b{re.escape(nf)}\b", text):
            offending.append(f"NF '{nf}'")

    allowed_flows = {af.flow_id.lower() for af in br.affected_flows}
    for fid in {f.lower() for f in _load_flows().keys()}:
        if fid in allowed_flows:
            continue
        if re.search(rf"\b{re.escape(fid)}\b", text):
            offending.append(f"flow '{fid}'")

    return (len(offending) == 0, offending)
