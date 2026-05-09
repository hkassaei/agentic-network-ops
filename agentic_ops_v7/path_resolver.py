"""PathResolver — flow → ordered hop list.

Per ADR `path_anchored_probe_planning_for_transport_layer_faults.md`,
when the SymptomClassifier labels an episode `transport_layer` (or
`mixed`), the v7 orchestrator routes to the path-walk pipeline. The
walker needs an ordered list of `(node, hop_kind, iface)` hops to
traverse — this resolver produces that list from:

  1. The `SymptomClassification` (which NFs are load-bearing).
  2. `network_ontology/data/flows.yaml` (which protocol flows touch
     those NFs and in what order).
  3. `network_ontology/data/topology.yaml` (per-node hop_kind / iface,
     and the bridge segments inserted between adjacent containers).

Algorithm:

  1. Identify the *load-bearing components* — the set of NF names
     mentioned in transport_flags + ambiguous_flags + application_flags.
     We don't restrict to transport_flags only; if a flag is bucketed
     `application` because the metric name matched a heuristic
     pattern (e.g. timeout_ratio), the underlying NF is still on the
     symptom-implicated path.
  2. Score each flow by the count of load-bearing components present
     in its `from`/`to`/`via` step references. Tie-break by total
     coverage (more specific flows win) and by `display_order`
     ascending (canonical preference).
  3. Walk the chosen flow's steps. For each step, expand to:
        Hop(from)
        Hop(bridge)   ← inserted between every adjacent container pair
        Hop(via_1)
        Hop(bridge)
        ...
        Hop(via_n)
        Hop(bridge)
        Hop(to)
     — subject to the topology's default_inter_container_bridge rule.
  4. Deduplicate consecutive identical-node hops (e.g. when step N's
     `to` equals step N+1's `from`).

The resolver is deterministic Python — no LLM. It returns a
`ResolvedPath` carrying the ordered Hop list plus the rationale
(which flow won and why) for episode-log auditability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path as _PathLib
from typing import Optional

import yaml

from agentic_ops_common.path_walk import Hop, HopKind

from .symptom_classifier import SymptomClassification


_REPO_ROOT = _PathLib(__file__).resolve().parents[1]
_FLOWS_PATH = _REPO_ROOT / "network_ontology" / "data" / "flows.yaml"
_TOPOLOGY_PATH = _REPO_ROOT / "network_ontology" / "data" / "topology.yaml"


# ---------------------------------------------------------------------------
# Resolver output
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResolvedPath:
    """The walker's input: an ordered hop list plus how it was derived."""
    flow_id: str
    flow_name: str
    direction: str  # "uplink" | "downlink" | "both"
    hops: list[Hop]
    rationale: str
    candidate_flows: list[tuple[str, int]] = field(default_factory=list)
    """list of (flow_id, score) considered, for auditability."""

    @property
    def is_resolved(self) -> bool:
        """A path is resolved when at least one flow scored > 0 and
        produced ≥ 2 hops (otherwise there's nothing for the walker
        to do)."""
        return bool(self.flow_id) and len(self.hops) >= 2

    def to_dict(self) -> dict:
        return {
            "flow_id": self.flow_id,
            "flow_name": self.flow_name,
            "direction": self.direction,
            "hops": [
                {"node": h.node, "kind": h.kind, "iface": h.iface}
                for h in self.hops
            ],
            "rationale": self.rationale,
            "candidate_flows": [
                {"flow_id": f, "score": s} for f, s in self.candidate_flows
            ],
        }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def resolve_path(
    classification: SymptomClassification,
    flows_yaml_path: Optional[_PathLib] = None,
    topology_yaml_path: Optional[_PathLib] = None,
) -> Optional[ResolvedPath]:
    """Resolve the implicated path for a transport-layer / mixed symptom.

    Returns:
        A `ResolvedPath` when a flow scored > 0 and produced ≥ 2 hops.
        `None` when no flow scored or all candidates produced empty hop
        lists — the caller (orchestrator) treats `None` as "fall back
        to the application-layer pipeline."
    """
    flows_yaml_path = flows_yaml_path or _FLOWS_PATH
    topology_yaml_path = topology_yaml_path or _TOPOLOGY_PATH

    flows_doc = yaml.safe_load(flows_yaml_path.read_text())
    flows = flows_doc.get("flows", {}) if flows_doc else {}
    topology_doc = yaml.safe_load(topology_yaml_path.read_text()) or {}
    nodes_topology = topology_doc.get("nodes", {})
    bridges = topology_doc.get("bridges", []) or []
    default_bridge_id = topology_doc.get("default_inter_container_bridge")

    load_bearing = _load_bearing_components(classification)
    load_bearing_metrics = _load_bearing_metrics(classification)
    if not load_bearing:
        return None

    candidates = _score_flows(flows, load_bearing, load_bearing_metrics)
    if not candidates:
        return None

    best_flow_id, best_score = candidates[0]
    flow_def = flows.get(best_flow_id, {})
    hops = _expand_flow_to_hops(
        flow_def, nodes_topology, bridges, default_bridge_id,
    )
    if len(hops) < 2:
        return None

    rationale = _render_rationale(
        best_flow_id, best_score, candidates, load_bearing, len(hops),
    )
    return ResolvedPath(
        flow_id=best_flow_id,
        flow_name=flow_def.get("name", best_flow_id),
        direction="both",
        hops=hops,
        rationale=rationale,
        candidate_flows=candidates[:5],
    )


# ---------------------------------------------------------------------------
# Component identification
# ---------------------------------------------------------------------------


def _flag_nf_metric(fb) -> tuple[Optional[str], Optional[str]]:
    """Recover (nf_name, metric_short_name) for one bucketed flag.

    Preferred path: `flag.kb_context.kb_metric_id` (e.g.
    `ims.rtpengine.loss_ratio`), populated by Phase 0's
    `enrich_anomaly_report`. This is the canonical NF.metric pair that
    survives the screener's `derived` / `normalized` namespace prefixes
    — the failure mode that caused v7's first run to resolve the
    wrong flow.

    Fallback: legacy NF-format callers that built `AnomalyFlag` with
    `component=<NF-name>` directly. Those work as-is.

    Returns (None, None) only when neither path resolves.
    """
    flag = fb.flag
    kb_context = getattr(flag, "kb_context", None)
    if kb_context is not None:
        kb_metric_id = getattr(kb_context, "kb_metric_id", None)
        if kb_metric_id:
            # Canonical id is `<layer>.<nf>.<metric_short>`. The metric
            # short-name itself can contain colons (`cdp:replies_received`)
            # but no further dots, so a 2-split on "." is safe.
            parts = kb_metric_id.split(".", 2)
            if len(parts) == 3:
                _layer, nf, metric_short = parts
                return nf, metric_short
    if flag.component and flag.metric:
        return flag.component, flag.metric
    return None, None


def _load_bearing_components(c: SymptomClassification) -> set[str]:
    """Every NF name mentioned by the classifier's flags.

    We pull from all three buckets — transport, application, ambiguous
    — because the implicated path covers the symptom's whole
    topological neighborhood, not only the bucketed-as-transport NFs.
    Concretely: when an HSS-unresponsive case classifies as `mixed`
    with timeout_ratio at I-CSCF (application bucket) and rate drop
    at S-CSCF (transport bucket), the implicated path needs to
    include both CSCFs and pyhss.

    NF names are recovered via `_flag_nf_metric`, which prefers the
    canonical `kb_metric_id` over the screener's raw `flag.component`
    (which is `derived` / `normalized`, not an NF name).
    """
    components: set[str] = set()
    for fb in (
        list(c.transport_flags)
        + list(c.application_flags)
        + list(c.ambiguous_flags)
    ):
        nf, _metric = _flag_nf_metric(fb)
        if nf:
            components.add(nf)
    return components


def _load_bearing_metrics(c: SymptomClassification) -> set[str]:
    """Metric tokens for matching against flow `observable_metrics`.

    Each flagged metric contributes both the short name (`loss_ratio`)
    AND the dotted `nf.metric` form (`rtpengine.loss_ratio`). The dotted
    form is what `network_ontology/data/flows.yaml` uses in its
    `observable_metrics` blobs — e.g. `rtpengine.loss_ratio (RTCP-reported)`.
    Without it, the substring matcher in `_score_flows` misses the
    decisive flow-vs-flow boost (the failure mode that made the v7
    resolver tie between `vonr_media` and `data_pdu_session_user_traffic`
    on the rtpengine episode and pick the wrong one).
    """
    metrics: set[str] = set()
    for fb in (
        list(c.transport_flags)
        + list(c.application_flags)
        + list(c.ambiguous_flags)
    ):
        nf, metric_short = _flag_nf_metric(fb)
        if metric_short:
            metrics.add(metric_short.lower())
            if nf:
                metrics.add(f"{nf}.{metric_short}".lower())
    return metrics


# ---------------------------------------------------------------------------
# Flow scoring
# ---------------------------------------------------------------------------


def _score_flows(
    flows: dict,
    load_bearing: set[str],
    load_bearing_metrics: set[str],
) -> list[tuple[str, int]]:
    """Score every flow against the symptom.

    Score components (additive):
      +1 per load-bearing component matched in flow steps (from/to/via).
      +3 per load-bearing metric named in flow's `outcome.observable_metrics`.

    The 3:1 ratio reflects that an explicit metric callout in the flow
    spec is much stronger evidence than a generic component overlap.
    Component-only matches happen for almost every NF in every flow
    (the IMS pipeline touches a lot of CSCFs); metric-named matches
    are specific to the flow's declared diagnostic surface.

    Tie-break: smaller total component count first (more specific flows
    win), then `display_order` ascending. This prefers `vonr_media`
    (5 components) over `vonr_call_setup` (11 components) when their
    base scores are otherwise comparable.

    Flows scoring 0 are filtered out.
    """
    scored: list[tuple[str, int, int, int]] = []  # (id, score, total, display_order)
    for flow_id, flow_def in flows.items():
        components = _flow_components(flow_def)
        component_score = len(components & load_bearing)

        # Metric-name match against the flow's observable_metrics text.
        # The text is free-form ("rtpengine.loss_ratio (RTCP-reported)"),
        # so we substring-match each load-bearing metric. The boost is
        # 3x to make a metric callout decisive over generic component
        # overlap.
        metric_score = 0
        observable = _flow_observable_metrics_blob(flow_def).lower()
        if observable:
            for metric in load_bearing_metrics:
                if metric and metric in observable:
                    metric_score += 1

        score = component_score + 3 * metric_score
        if score == 0:
            continue
        display_order = flow_def.get("display_order", 999)
        scored.append((flow_id, score, len(components), display_order))

    # Sort: score DESC, total_components ASC (smaller = more specific),
    # display_order ASC.
    scored.sort(key=lambda t: (-t[1], t[2], t[3]))
    return [(t[0], t[1]) for t in scored]


def _flow_observable_metrics_blob(flow_def: dict) -> str:
    """Concatenate every observable_metrics entry from a flow's
    outcome / terminal_step into one searchable blob."""
    blobs: list[str] = []
    for key in ("outcome", "terminal_step"):
        block = flow_def.get(key) or {}
        for m in block.get("observable_metrics", []) or []:
            blobs.append(str(m))
    return " | ".join(blobs)


def _flow_components(flow_def: dict) -> set[str]:
    """All node names referenced by a flow's steps."""
    out: set[str] = set()
    for step in flow_def.get("steps", []) or []:
        if step.get("from"):
            out.add(step["from"])
        if step.get("to"):
            out.add(step["to"])
        for v in step.get("via", []) or []:
            out.add(v)
    return out


# ---------------------------------------------------------------------------
# Flow → hop list expansion
# ---------------------------------------------------------------------------


def _expand_flow_to_hops(
    flow_def: dict,
    nodes_topology: dict,
    bridges: list[dict],
    default_bridge_id: Optional[str],
) -> list[Hop]:
    """Walk a flow's steps and produce an ordered Hop list.

    For each step, we emit hops in order: from, via_1, via_2, ..., to.
    Between every adjacent container-kind pair we insert a bridge hop
    (per topology's default_inter_container_bridge rule).

    Consecutive identical-node hops (e.g. step N's `to` == step N+1's
    `from`) are deduplicated.
    """
    chain: list[str] = []
    for step in flow_def.get("steps", []) or []:
        sequence: list[str] = []
        if step.get("from"):
            sequence.append(step["from"])
        for v in step.get("via", []) or []:
            sequence.append(v)
        if step.get("to"):
            sequence.append(step["to"])
        # Append to the running chain, dedup at the boundary.
        for node in sequence:
            if not chain or chain[-1] != node:
                chain.append(node)

    # Now insert bridge hops between every adjacent container pair.
    hops: list[Hop] = []
    bridge_hop = _bridge_hop(bridges, default_bridge_id)
    for i, node in enumerate(chain):
        node_hop = _node_to_hop(node, nodes_topology)
        if node_hop is None:
            # Skip nodes the topology doesn't know about — better to
            # have a shorter walk than crash on unauthored topology.
            continue
        if hops and bridge_hop is not None:
            prev = hops[-1]
            # Only insert a bridge between two container-kind hops.
            # If either endpoint is non-container (e.g. external
            # internet, optical), skip the bridge.
            if prev.kind == "container" and node_hop.kind == "container":
                hops.append(bridge_hop)
        hops.append(node_hop)
    return hops


def _node_to_hop(node: str, nodes_topology: dict) -> Optional[Hop]:
    spec = nodes_topology.get(node)
    if spec is None:
        return None
    kind: HopKind = spec.get("kind", "container")  # type: ignore[assignment]
    iface = spec.get("iface", "eth0") or "eth0"
    metadata = spec.get("metadata", {}) or {}
    return Hop(node=node, kind=kind, iface=iface, metadata=metadata)


def _bridge_hop(
    bridges: list[dict], default_bridge_id: Optional[str],
) -> Optional[Hop]:
    """Find the default inter-container bridge hop.

    Returns None if the topology hasn't authored one — in that case
    the walker just walks container-to-container without bridge
    inspection.
    """
    if not default_bridge_id or not bridges:
        return None
    for b in bridges:
        if b.get("name") == default_bridge_id:
            return Hop(
                node=b["name"],
                kind=b.get("kind", "docker_bridge"),
                iface=b.get("iface", "docker0") or "docker0",
                metadata=b.get("metadata", {}) or {},
            )
    return None


# ---------------------------------------------------------------------------
# Rationale
# ---------------------------------------------------------------------------


def _render_rationale(
    chosen_flow_id: str,
    chosen_score: int,
    candidates: list[tuple[str, int]],
    load_bearing: set[str],
    hop_count: int,
) -> str:
    """Render a one-paragraph explanation of which flow won and why."""
    parts: list[str] = [
        f"Resolved transport path to flow `{chosen_flow_id}` "
        f"(score={chosen_score}, {hop_count} hops on the walk).",
        f"Load-bearing components: {sorted(load_bearing)}.",
    ]
    if len(candidates) > 1:
        runners_up = ", ".join(
            f"{f}={s}" for f, s in candidates[1:5]
        )
        parts.append(f"Other candidate flows considered: {runners_up}.")
    return " ".join(parts)
