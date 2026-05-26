"""PathPrioritizer — flow scoring → prioritized hop-list candidates.

Per ADR `path_anchored_probe_planning_for_transport_layer_faults.md`,
when the SymptomClassifier labels an episode `transport_layer` (or
`mixed`), the v7 orchestrator routes to the path-walk pipeline. The
walker needs ordered `(node, hop_kind, iface)` hop lists to traverse.

This module does NOT select a single flow. Per ADR
`path_prioritizer_walks_all_candidates.md`, it PRIORITIZES the
evidence-bearing flows (those whose hop list contains at least one
flagged NF) and returns up to `_HARD_CAP_FLOWS` of them in priority
order. The walker then walks ALL of them in parallel — localization
correctness lives with the deterministic walker, not with this
scoring step, which only decides walk order and which candidates make
the cap. (The module was previously named `path_resolver` / the
function `resolve_path`, from when it selected one flow; renamed to
reflect the prioritize-not-select contract.)

Inputs:

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
     ascending (canonical preference). Flows scoring 0 (no flagged NF
     in the hop list) are dropped — this is the evidence-bearing gate
     that prevents brute-force walking.
  3. For each surviving flow, expand its steps to an ordered hop list:
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
  5. Apply the hard cap (top `_HARD_CAP_FLOWS` by score); surface the
     rest as `truncated`.

The prioritizer is deterministic Python — no LLM. It returns a
`PrioritizedPaths` carrying the ranked candidate list (each with its
ordered Hop list) plus the rationale, for episode-log auditability.
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
# Prioritizer output
# ---------------------------------------------------------------------------


# Caps on the number of evidence-bearing candidates the walker will probe.
# ADR: docs/ADR/path_prioritizer_walks_all_candidates.md
#   * Soft cap = 3: walk all candidates, emit a warning if more than 3
#     were walked. Signals a noisy load-bearing set worth inspecting.
#   * Hard cap = 5: never walk more than the top 5 by priority. Anything
#     ranked 6+ is dropped and surfaced as "not walked (hard cap)" in the
#     episode log.
_SOFT_CAP_FLOWS = 3
_HARD_CAP_FLOWS = 5


@dataclass(frozen=True)
class PathCandidate:
    """One evidence-bearing flow the walker should probe.

    The prioritizer (`prioritize_paths`) returns a list of these in
    priority order. The walker walks all of them in parallel (Phase 0.6).
    ADR: docs/ADR/path_prioritizer_walks_all_candidates.md
    """
    flow_id: str
    flow_name: str
    direction: str  # "uplink" | "downlink" | "both"
    hops: list[Hop]
    score: int


@dataclass(frozen=True)
class PrioritizedPaths:
    """Prioritized list of evidence-bearing candidate flows.

    Returned by `prioritize_paths`. Carries the ranked candidate list
    (each with its own ordered hop list); the walker walks all of them
    in parallel (Phase 0.6). The backward-compat properties (`flow_id`,
    `flow_name`, `direction`, `hops`) return the *primary candidate's*
    values, where "primary" = first in priority order — these let older
    call sites that expect a single resolved path keep working.

    Caps (`_SOFT_CAP_FLOWS=3`, `_HARD_CAP_FLOWS=5`) limit how many
    candidates the walker probes. `truncated` surfaces flows that scored
    > 0 but were dropped past the hard cap, so the episode log can show
    them as "not walked".

    ADR: docs/ADR/path_prioritizer_walks_all_candidates.md
    """
    candidates: list[PathCandidate]
    rationale: str
    candidate_flows: list[tuple[str, int]] = field(default_factory=list)
    """list of (flow_id, score) considered, for auditability."""
    truncated: list[tuple[str, int]] = field(default_factory=list)
    """list of (flow_id, score) dropped past the hard cap. Empty when
    the candidate count ≤ _HARD_CAP_FLOWS."""

    @property
    def soft_cap_exceeded(self) -> bool:
        return len(self.candidates) > _SOFT_CAP_FLOWS

    @property
    def hard_cap_truncated(self) -> bool:
        return bool(self.truncated)

    # ── Backward-compat properties (primary candidate access) ────────
    # Existing callers read `resolved.flow_id`, `resolved.hops`, etc.
    # These return the highest-priority candidate's values so call sites
    # that haven't been updated for the multi-walk model still work.
    @property
    def flow_id(self) -> str:
        return self.candidates[0].flow_id if self.candidates else ""

    @property
    def flow_name(self) -> str:
        return self.candidates[0].flow_name if self.candidates else ""

    @property
    def direction(self) -> str:
        return self.candidates[0].direction if self.candidates else "both"

    @property
    def hops(self) -> list[Hop]:
        return self.candidates[0].hops if self.candidates else []

    @property
    def is_resolved(self) -> bool:
        """True when at least one candidate produced ≥ 2 hops (otherwise
        there's nothing for the walker to do). Kept named `is_resolved`
        for call-site compatibility."""
        return any(len(c.hops) >= 2 for c in self.candidates)

    def to_dict(self) -> dict:
        # `flow_id` / `flow_name` / `direction` / `hops` keys preserved for
        # backward compat — they reflect the primary candidate. The new
        # `candidates` list carries the full prioritized set.
        primary = self.candidates[0] if self.candidates else None
        return {
            "flow_id": primary.flow_id if primary else "",
            "flow_name": primary.flow_name if primary else "",
            "direction": primary.direction if primary else "both",
            "hops": [
                {"node": h.node, "kind": h.kind, "iface": h.iface}
                for h in (primary.hops if primary else [])
            ],
            "rationale": self.rationale,
            "candidate_flows": [
                {"flow_id": f, "score": s} for f, s in self.candidate_flows
            ],
            # New under the prioritizer ADR:
            "candidates": [
                {
                    "flow_id": c.flow_id,
                    "flow_name": c.flow_name,
                    "direction": c.direction,
                    "score": c.score,
                    "hops": [
                        {"node": h.node, "kind": h.kind, "iface": h.iface}
                        for h in c.hops
                    ],
                }
                for c in self.candidates
            ],
            "truncated": [
                {"flow_id": f, "score": s} for f, s in self.truncated
            ],
            "soft_cap_exceeded": self.soft_cap_exceeded,
            "hard_cap_truncated": self.hard_cap_truncated,
        }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def prioritize_paths(
    classification: SymptomClassification,
    flows_yaml_path: Optional[_PathLib] = None,
    topology_yaml_path: Optional[_PathLib] = None,
) -> Optional[PrioritizedPaths]:
    """Prioritize the evidence-bearing flows for a transport-layer / mixed
    symptom — the walker walks all of them (up to the hard cap) in parallel.

    Returns:
        A `PrioritizedPaths` when at least one flow scored > 0 and produced
        ≥ 2 hops. `None` when no flow scored (no flagged NF appears in any
        flow's hop list — the "no smoking gun" case) or all candidates
        produced empty hop lists — the caller (orchestrator) treats `None`
        as "fall back to the application-layer pipeline; don't walk."
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
    metrics_by_bucket = _load_bearing_metrics_by_bucket(classification)
    if not load_bearing:
        return None

    scored = _score_flows(flows, load_bearing, metrics_by_bucket)
    if not scored:
        return None

    # Expand each scored flow to its hop list. Drop flows whose expansion
    # produced fewer than 2 hops — there's nothing for the walker to do.
    expanded: list[PathCandidate] = []
    for flow_id, score in scored:
        flow_def = flows.get(flow_id, {})
        hops = _expand_flow_to_hops(
            flow_def, nodes_topology, bridges, default_bridge_id,
        )
        if len(hops) < 2:
            continue
        expanded.append(PathCandidate(
            flow_id=flow_id,
            flow_name=flow_def.get("name", flow_id),
            direction="both",
            hops=hops,
            score=score,
        ))

    if not expanded:
        return None

    # Apply hard cap. Anything past _HARD_CAP_FLOWS is surfaced as
    # "truncated" so the episode log can render "not walked (hard cap)".
    # ADR: docs/ADR/path_prioritizer_walks_all_candidates.md
    candidates = expanded[:_HARD_CAP_FLOWS]
    truncated = [(c.flow_id, c.score) for c in expanded[_HARD_CAP_FLOWS:]]

    rationale = _render_rationale(
        candidates[0].flow_id, candidates[0].score, scored,
        load_bearing, len(candidates[0].hops),
        candidate_count=len(candidates),
        truncated_count=len(truncated),
    )
    return PrioritizedPaths(
        candidates=candidates,
        rationale=rationale,
        candidate_flows=scored[:5],
        truncated=truncated,
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


def _metrics_from_bucket(flag_buckets) -> list[set[str]]:
    """Per-flag list of searchable metric tokens.

    Returns one set per flag in the bucket. Each set carries the
    flag's short metric name (`loss_ratio`) AND its dotted
    `nf.metric` form (`rtpengine.loss_ratio`). The dotted form is
    what `network_ontology/data/flows.yaml` uses in its
    `observable_metrics` blobs; the short form catches flow specs
    that prefix the NF differently.

    Returning per-flag sets (not a flat union) is load-bearing for
    `_count_unique_flag_hits`: we want to count *unique flags*
    whose tokens matched the flow blob, not total token hits. Both
    token forms for the same flag matching the same blob shouldn't
    inflate the score by 2× — that artifact is what made the
    resolver pick `data_pdu_session_user_traffic` over
    `ims_registration` on the 2026-05-10 batch.
    """
    per_flag: list[set[str]] = []
    for fb in flag_buckets:
        nf, metric_short = _flag_nf_metric(fb)
        if not metric_short:
            continue
        tokens = {metric_short.lower()}
        if nf:
            tokens.add(f"{nf}.{metric_short}".lower())
        per_flag.append(tokens)
    return per_flag


def _load_bearing_metrics_by_bucket(
    c: SymptomClassification,
) -> dict[str, list[set[str]]]:
    """Per-bucket, per-flag metric-token sets for flow scoring.

    Returns a dict with keys `"transport"`, `"application"`,
    `"ambiguous"` mapped to a *list of per-flag token sets*. The list
    shape preserves the "one entry per flag" count that
    `_count_unique_flag_hits` reads — see `_metrics_from_bucket` for
    why per-flag dedup is load-bearing.
    """
    return {
        "transport": _metrics_from_bucket(c.transport_flags),
        "application": _metrics_from_bucket(c.application_flags),
        "ambiguous": _metrics_from_bucket(c.ambiguous_flags),
    }


def _load_bearing_metrics(c: SymptomClassification) -> set[str]:
    """Flat union of metric tokens across all three buckets.

    Kept as a thin compatibility wrapper. New code that scores flows
    should call `_load_bearing_metrics_by_bucket` and pass the
    per-flag structure to `_count_unique_flag_hits`.
    """
    flat: set[str] = set()
    per_bucket = _load_bearing_metrics_by_bucket(c)
    for flags in per_bucket.values():
        for tokens in flags:
            flat |= tokens
    return flat


# ---------------------------------------------------------------------------
# Flow scoring
# ---------------------------------------------------------------------------


def _score_flows(
    flows: dict,
    load_bearing: set[str],
    metrics_by_bucket: dict[str, list[set[str]]],
) -> list[tuple[str, int]]:
    """Score every flow against the symptom (F1.2 + F1.4).

    Score formula (additive):
      `score = 2 * component_score
             + 5 * transport_flag_hits
             + 3 * application_flag_hits
             + 1 * ambiguous_flag_hits`

    Where:
      - `component_score` = count of load-bearing NFs whose name
        appears in the flow's hop list.
      - `<bucket>_flag_hits` = count of UNIQUE flagged metrics from
        that bucket whose token (short or dotted form) appears in
        the flow's `observable_metrics` blob. Per-flag dedup — see
        `_count_unique_flag_hits`.

    Why each weight is what it is:

      Component weight bumped from 1 to 2. The pre-F1 weighting
      treated each metric-token hit as 3× a component match, which
      collapsed under per-flag token duplication: two flagged UPF
      GTP metrics produced 4 token hits (each appears in both short
      and dotted form) × 3 = 12 metric points, vs. 4 component
      matches × 1 = 4 component points. The right flow lost. After
      per-flag dedup *and* doubling the component weight, the
      signal-to-noise ratio of "this flow covers the implicated
      NFs" is restored.

      Per-bucket metric weights — transport (5) > application (3)
      > ambiguous (1). A metric KB-labeled transport is a stronger
      transport-fault locator than an ambiguous-bucket metric whose
      bucket assignment is "the screener flagged it but the KB
      can't unambiguously say transport or application." The
      classifier already produced this stratification; the scorer
      should respect it.

    Tie-break order (F1.2 — bucket affinity, kept as a backstop for
    flows that tie even after the weighted scoring):
      1. score DESC
      2. transport-bucket flag matched (any) DESC
      3. application-bucket flag matched (any) DESC
      4. total component count ASC (more specific flows win when
         scoring is otherwise tied)
      5. display_order ASC

    Flows scoring 0 are filtered out.
    """
    # Weights chosen against the 2026-05-10 batch:
    #   _COMPONENT_WEIGHT = 2 — bumped from the pre-F1 value of 1.
    #     Restores component-match signal relative to metric-match signal
    #     after per-flag dedup removed the artificial 2× inflation that
    #     used to make data_pdu_session_user_traffic win on its UPF GTP
    #     observable_metrics callout. Stronger values (4+) regress the
    #     rtpengine-loss roundtrip test by letting many-component flows
    #     like vonr_call_teardown win over vonr_media on ambiguous-bucket
    #     CSCF component overlap.
    #   _BUCKET_WEIGHTS — transport (5) > application (3) > ambiguous (1).
    #     A metric KB-labeled `transport` is the strongest indicator of
    #     transport-fault locus; ambiguous flags get dampened because
    #     they're often downstream-consequence signals (e.g. a CSCF's
    #     register-rate drop under a media fault) that pollute the
    #     load-bearing set.
    #
    # Cases the current weighting CANNOT fix (documented in the F1.3
    # tests' xfail marks): when the screener emits ≥2 UPF GTP transport
    # flags, those alone produce +10 (5×2) for any flow with UPF GTP in
    # its observable_metrics. The right flow for signaling-layer faults
    # (`ims_registration`) has no UPF GTP in its observable_metrics, so
    # it can never match that boost. Fix is at the screener level (B4
    # in the work plan), not here.
    _COMPONENT_WEIGHT = 2
    _BUCKET_WEIGHTS = {"transport": 5, "application": 3, "ambiguous": 1}

    # Tuple shape: (id, score, transport_matched, application_matched,
    #               total_components, display_order)
    scored: list[tuple[str, int, int, int, int, int]] = []
    for flow_id, flow_def in flows.items():
        components = _flow_components(flow_def)
        component_score = len(components & load_bearing)

        observable = _flow_observable_metrics_blob(flow_def).lower()
        transport_hits = _count_unique_flag_hits(
            observable, metrics_by_bucket["transport"],
        )
        application_hits = _count_unique_flag_hits(
            observable, metrics_by_bucket["application"],
        )
        ambiguous_hits = _count_unique_flag_hits(
            observable, metrics_by_bucket["ambiguous"],
        )

        score = (
            _COMPONENT_WEIGHT * component_score
            + _BUCKET_WEIGHTS["transport"] * transport_hits
            + _BUCKET_WEIGHTS["application"] * application_hits
            + _BUCKET_WEIGHTS["ambiguous"] * ambiguous_hits
        )
        if score == 0:
            continue
        display_order = flow_def.get("display_order", 999)
        scored.append((
            flow_id, score,
            1 if transport_hits > 0 else 0,
            1 if application_hits > 0 else 0,
            len(components), display_order,
        ))

    # Sort by tuple priorities above. Negation on the DESC fields.
    scored.sort(key=lambda t: (-t[1], -t[2], -t[3], t[4], t[5]))
    return [(t[0], t[1]) for t in scored]


def _count_unique_flag_hits(
    observable_blob: str,
    per_flag_token_sets: list[set[str]],
) -> int:
    """Count flags (not tokens) whose any-of-its-tokens appears in
    the observable_metrics blob.

    Each flagged metric contributes at most one hit to a given flow,
    regardless of whether both its short form AND its dotted form
    appear in the blob. This is the deduplication that prevents
    per-flag double-counting from inflating metric_score relative
    to component_score.
    """
    if not observable_blob:
        return 0
    hits = 0
    for tokens in per_flag_token_sets:
        if any(tok and tok in observable_blob for tok in tokens):
            hits += 1
    return hits


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
    candidate_count: int = 1,
    truncated_count: int = 0,
) -> str:
    """Render a one-paragraph explanation of which flow is primary and how
    many candidates the walker will probe.

    Under ADR `path_prioritizer_walks_all_candidates.md` the walker walks
    ALL surviving candidates (up to the hard cap); the "chosen" flow here
    is just the primary (highest-priority) one — the rationale notes how
    many total flows the walker will probe.
    """
    parts: list[str] = [
        f"Primary flow `{chosen_flow_id}` (score={chosen_score}, "
        f"{hop_count} hops); walker probes {candidate_count} candidate "
        f"flow{'s' if candidate_count != 1 else ''} in parallel.",
        f"Load-bearing components: {sorted(load_bearing)}.",
    ]
    if len(candidates) > 1:
        runners_up = ", ".join(
            f"{f}={s}" for f, s in candidates[1:5]
        )
        parts.append(f"Other candidate flows considered: {runners_up}.")
    if truncated_count > 0:
        parts.append(
            f"Hard cap (5 flows) truncated {truncated_count} additional "
            f"candidate{'s' if truncated_count != 1 else ''} below the cut."
        )
    if candidate_count > _SOFT_CAP_FLOWS:
        parts.append(
            f"Soft cap exceeded ({candidate_count} > {_SOFT_CAP_FLOWS}): "
            f"noisy load-bearing set — inspect screener flag bucketing if "
            f"this recurs."
        )
    return " ".join(parts)
