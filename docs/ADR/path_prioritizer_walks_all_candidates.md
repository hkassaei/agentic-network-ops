# ADR: Path Prioritizer — Walk All Evidence-Bearing Candidates In Parallel

**Date:** 2026-05-25
**Status:** Proposed
**Replaces:** [`resolver_nf_burden_scoring.md`](resolver_nf_burden_scoring.md) (marked ⛔ OBSOLETE)

---

## ⚠️ This ADR replaces a previous attempt — read this before reading the rest

The previous ADR ([`resolver_nf_burden_scoring.md`](resolver_nf_burden_scoring.md)) proposed an NF-burden scoring formula to fix the wrong-flow-selection problem. It was implemented in full, tested end-to-end, and reverted in the same session after surfacing **5 real regressions** the proposal's "validation walkthrough" hadn't anticipated:

- `upf_bandwidth_cap`, `data_plane_degradation`, `call_quality_degradation`, the round-trip test, and a 5/10 `ims_network_partition` xfail — all picked the wrong flow under NF-burden.

**Root cause of the previous attempt's failure: the downstream-consequence problem is symmetric.** A pure-UPF fault doesn't fire only UPF flags — it fires UPF flags PLUS downstream CSCF flags (call setup retrying, register-rate dropping). Any additive scoring formula that treats every flagged NF as equally implicating will vote for the IMS flow when both IMS NFs and UPF are flagged, because the IMS flow's hop list spans both. The previous ADR's "pure UPF fault" walkthrough was a reasoning artifact, not a property of real data. The failure mode would have been caught by running the formula against the saved 5/10 episode JSON before writing the walkthrough.

**This ADR takes a different path: stop forcing the scoring formula to be correct.** Localization correctness moves to the walker (deterministic Python kernel probing, the most-trustworthy phase). The scoring formula becomes a prioritization signal, not a selection decision. The walker walks **all** evidence-bearing candidates (up to a hard cap of 5), in parallel. If the scoring is imperfect, the walker still eventually probes the right flow.

The full failure analysis from the previous attempt is preserved at the top of [`resolver_nf_burden_scoring.md`](resolver_nf_burden_scoring.md) for posterity.

---

**Related:**
- ⛔ Supersedes [`resolver_nf_burden_scoring.md`](resolver_nf_burden_scoring.md) — see callout above for the failure analysis and lesson.
- Triggering episodes (still relevant — same wrong-flow cases the previous ADR targeted):
    - [`agentic_ops_v7/docs/agent_logs/run_20260521_021756_p_cscf_latency.md`](../../agentic_ops_v7/docs/agent_logs/run_20260521_021756_p_cscf_latency.md)
    - [`agentic_ops_v7/docs/agent_logs/run_20260521_022431_s_cscf_crash.md`](../../agentic_ops_v7/docs/agent_logs/run_20260521_022431_s_cscf_crash.md)
    - [`agentic_ops_v7/docs/agent_logs/run_20260521_130330_ims_network_partition.md`](../../agentic_ops_v7/docs/agent_logs/run_20260521_130330_ims_network_partition.md)
    - [`agentic_ops_v7/docs/agent_logs/run_20260521_033823_rtpengine_latency_injection.md`](../../agentic_ops_v7/docs/agent_logs/run_20260521_033823_rtpengine_latency_injection.md) — partially resolved: with walk-all-candidates, `vonr_media` gets walked alongside `ims_registration`, and `vonr_media`'s walker reaches rtpengine. The screener-feature gap (no rtpengine-direct latency feature) still bounds the upside but the resolver-side mis-pick stops costing diagnostic information.
- [`path_anchored_probe_planning_for_transport_layer_faults.md`](path_anchored_probe_planning_for_transport_layer_faults.md) — the transport-layer pipeline this changes.
- [`multi_fault_orchestration.md`](multi_fault_orchestration.md) — compound verdicts. Multi-flow walker localization is a new compound source; this ADR scope-reduces walker+walker compound to "log only" — full handling is a follow-up.
- [`screener_starvation_partial_metric_collection.md`](screener_starvation_partial_metric_collection.md) — sibling Phase 0 fix. Both move pre-LLM determinism upstream.

---

## Decision

Replace the path resolver's "pick the one true flow" contract with a **prioritizer** contract: produce a *ranked list* of evidence-bearing candidate flows, and let the walker probe **all of them** (in parallel, up to a hard cap of 5).

The localization-correctness contract moves to the walker — which is deterministic Python doing kernel-level probing, the most-trustworthy phase in the pipeline. The scoring formula becomes a *prioritization signal*, not a *selection decision*. Its job is to rank candidates by relevance so the cap-boundary tie-break is sensible; it doesn't have to be right.

Specifically:

1. **Generate candidates as today** — `_score_flows` produces a sorted list of (flow_id, score). The existing `score == 0` filter (flow contains no flagged NFs and matches no flagged-metric tokens) stays — it's the "evidence-bearing" gate that prevents brute-force.
2. **Soft cap = 3**, **hard cap = 5.** If the surviving candidate list is 1–3 flows, walk all. If 4–5, walk all and emit a soft-cap warning in the episode log. If 6+, truncate to the top 5 by score, log a hard-cap truncation note, and surface the dropped flows in the candidates table marked `not walked`.
3. **Walk all selected candidates in parallel** via `asyncio.gather` — each flow's walk is sequential internally (the inter-hop-diff probes need adjacent-hop ordering), but flows run concurrently. Wall-clock bounded by the longest single-flow walk, not the sum.
4. **No short-circuit on first localization.** Walking all surviving candidates lets the walker surface compound faults (different flows attributing to different NFs) instead of stopping at the first finding.
5. **Don't walk if zero evidence.** When `_score_flows` returns no candidates (e.g., screener starvation, or a truly clean stack), the walker doesn't run. The episode log records "no evidence-bearing candidates; walker skipped" explicitly.
6. **Optional rename.** `PathResolver` → `PathPrioritizer` and `resolve_path` → `prioritize_paths`. The current name implies a selection decision the function no longer makes. Rename is a follow-up if you prefer to keep the existing module path; the behavioral change above does not depend on it.

## Context

### What we learned from the NF-burden attempt

The previous ADR (`resolver_nf_burden_scoring.md`) proposed a scoring formula that voted per-NF-in-flow's-hop-list, weighted by bucket. It correctly fixed three wrong-flow cases by replacing observable_metrics blob matching with NF-membership. But the same formula failed in the opposite direction:

- **`p_cscf_latency`** (IMS fault, downstream UPF flags): IMS-NF burden votes for `ims_registration` — correct.
- **`upf_bandwidth_cap`** (UPF fault, downstream CSCF flags): CSCF-NF burden ALSO votes for `ims_registration` — wrong.

The IMS flow's hop list contains both IMS NFs and UPF, so it wins regardless of which side is upstream-causative. Any additive formula treating each flagged NF as equally implicating will hit this. The asymmetry is real and not patchable at the scoring layer without encoding causal precedence (KB-driven topological priors), which is a much larger redesign.

The right move is to stop forcing the scoring formula to be perfect. The walker IS the ground truth for "is the fault at this hop" — it does kernel-level probing on each hop and reports `drops_attributed_here` / `latency_at_hop` / `container_dead` / `clean` deterministically. If we let the walker probe all evidence-bearing flows, the localization is correct by construction regardless of which flow the scoring put first.

### Why this isn't brute-force

The structural insight: the score gate `score > 0` is doing the brute-force-prevention work, not the selection. A flow scores zero when none of its hop-list NFs are flagged AND none of its observable_metrics tokens match. In a typical chaos scenario the surviving candidate set is 3–7 flows — much smaller than the ontology's full flow count. Walking all surviving candidates is bounded by *evidence*, not by ontology size.

The soft and hard caps add belt-and-suspenders: if a scenario implicates so many NFs that 6+ flows have evidence, something is off (probably an over-flagging screener pattern) and we'd rather truncate visibly than burn unbounded wall-clock.

### Why this is cheap

The walker is deterministic Python doing docker-exec probes. No LLM calls. Per-hop probing is ~100-500ms; a typical flow has ~5-15 unique hops. Per-flow wall-clock is ~5-10 seconds today.

Under walk-all-in-parallel with cap=5:
- **Sequential (rejected):** 5 × 10s = ~50s walker wall-clock — measurable, would push 60-180s chaos runs to 110-230s.
- **Parallel via asyncio.gather (chosen):** bounded by longest single-flow walk ≈ 10-15s. Negligible change to total run time, which is dominated by 60-180s of LLM phases.

There's a further optimization available — deduplicating probes across flows so each unique (node, iface) is probed once and per-flow PathWalkReports are built from a shared cache — but this ADR explicitly defers it. Ship simpler first; revisit if wall-clock becomes a problem.

### What "evidence-bearing" means concretely

Today's `_score_flows` filter (`if score == 0: continue`) already encodes this. Under the existing formula a flow scores zero when:
- Its hop list contains no flagged NFs (component_score = 0), AND
- Its observable_metrics blob token-matches no flagged metrics (`*_flag_hits` = 0)

The first condition is the load-bearing one. The second was contributing to the broken behavior the previous ADR tried to fix. **In this redesign we keep `score > 0` as the gate but the formula behind the score becomes low-stakes** — it just sorts candidates within the surviving set. Any reasonable scoring (current formula, NF-burden, simple component-overlap) works equally well, because correctness is now downstream at the walker.

We retain the existing formula in this ADR. A follow-up can revisit the scoring expression once we have empirical wall-clock data from walk-all-in-parallel.

## Design

### The new contract

`resolve_path` (or `prioritize_paths` after rename) returns a list of candidates, each carrying its hop list:

```python
@dataclass(frozen=True)
class PathCandidate:
    flow_id: str
    flow_name: str
    direction: str
    hops: list[Hop]
    score: int

@dataclass(frozen=True)
class PrioritizedPaths:
    candidates: list[PathCandidate]       # in priority order, up to hard cap
    truncated: list[tuple[str, int]]      # (flow_id, score) for dropped flows
    rationale: str
    soft_cap_exceeded: bool                # >3 candidates walked
    hard_cap_truncated: bool               # >5 candidates existed; only top 5 returned

    @property
    def is_resolved(self) -> bool:
        return any(len(c.hops) >= 2 for c in self.candidates)
```

The legacy `ResolvedPath` dataclass either becomes this `PrioritizedPaths` (rename), or is retained as a thin compatibility shim wrapping the first element of `candidates`. Cleaner is to replace it outright; the rest of the v7 codebase has few references.

### Walker invocation in Phase 0.6

```python
# Walk all candidates in parallel.
walk_tasks = [
    asyncio.create_task(walk_path(
        flow_id=cand.flow_id,
        hops=cand.hops,
        anchor_ts=anchor_ts,
    ))
    for cand in prioritized.candidates
]
walk_reports = await asyncio.gather(*walk_tasks, return_exceptions=True)
```

Per-flow walks are independent — they probe different hop lists in parallel without interfering. (Probes shared across flows — e.g., upf[eth0] appearing in three flows' hop lists — will probe upf[eth0] three times in this iteration. Future deduplication ADR can collapse those into a single probe with cached attribution.)

### Choosing the "primary" report for downstream consumers

The Synthesis prompt and the existing scorer/recorder expect a single `path_walk_report`. To preserve backward compat without rewriting their interfaces in this iteration:

```python
# Primary = highest-priority localized report; falls back to first in list if none.
primary = next(
    (rep for rep in walk_reports
     if isinstance(rep, PathWalkReport) and rep.is_localized),
    walk_reports[0] if walk_reports else None,
)
state["path_walk_report"] = _path_walk_report_to_dict(primary)
state["path_walk_all_reports"] = [
    _path_walk_report_to_dict(r) for r in walk_reports
    if isinstance(r, PathWalkReport)
]
```

The recorder renders all reports; Synthesis sees only the primary. Compound-from-walker+walker (multiple walks localizing at different NFs) is logged for visibility but does not invoke compound Synthesis in this iteration — that's a follow-up.

### Episode-log surface

The Phase 0.6 markdown section gets two new pieces:

```
### Prioritized Candidates (3 walked, 0 truncated)

| Flow | Score | Walker outcome | First attributed hop |
|---|---:|---|---|
| `ims_registration` ← primary | 23 | ✅ localized | `pcscf[eth0]` |
| `vonr_media` | 14 | ⚠️ null | — |
| `data_pdu_session_user_traffic` | 12 | ⚠️ null | — |

*Soft cap = 3, hard cap = 5. This scenario produced 3 evidence-bearing flows;
all were walked in parallel.*
```

When >5 candidates exist:

```
*Hard cap = 5. This scenario produced 7 evidence-bearing flows; top 5 walked;
the following were truncated: `vonr_call_setup` (8), `ue_deregistration` (8).*
```

When >3 walked:

```
*Soft cap = 3 exceeded — 4 flows walked. This signals a noisy load-bearing set;
inspect the screener's flag bucketing if this happens often.*
```

## Trade-offs and limitations

- **Wall-clock impact ≈ 2× walker phase.** Today: ~5-10s for one flow. Proposed (parallel): ~10-15s for up to 5 flows. Total chaos-run time barely changes (still dominated by LLM phases).
- **Probe duplication across flows.** Without dedup, a shared hop like `upf[eth0]` is probed once per flow that contains it. In a 5-flow walk that's up to 5× the work for shared hops. Mitigation deferred — measure first, optimize if it shows up in profiling.
- **Synthesis prompt still sees only the primary.** Compound-from-walker+walker (multiple flows localize at different NFs) is real multi-fault territory and the existing compound machinery was designed for walker+app-layer. We log multi-walker compound in this iteration; a follow-up extends the compound prompt to consume the full walker-reports list.
- **The score formula is now low-stakes — but it still matters at the cap boundary.** When 6+ candidates exist, the top 5 by score get walked and the rest are dropped. A bad score function would drop the right answer. The current formula is good enough for typical scenarios; if a future case shows the right flow dropping below the cap, that's the signal to revisit scoring.
- **`PathResolver` → `PathPrioritizer` rename is cosmetic** but the new name communicates the contract more honestly. Defer if the code churn isn't worth it.
- **Episode-log entries change shape.** The "Resolver" section becomes "Prioritized Candidates" with N walker outcomes instead of one. Operators reading old vs new episodes will notice. Acceptable — the new shape carries more information.

## Implementation outline

1. **`agentic_ops_v7/path_resolver.py`**
    - Add `PathCandidate` and `PrioritizedPaths` dataclasses.
    - Add `_SOFT_CAP_FLOWS = 3` and `_HARD_CAP_FLOWS = 5` constants.
    - Rewrite `resolve_path` to return `PrioritizedPaths` (or `None` when zero evidence).
    - Keep `_score_flows` and the rest of the scoring machinery essentially as-is — they still compute the rank order.
    - Keep `_expand_flow_to_hops` and the hop-expansion machinery unchanged.
    - (Optional) Rename module to `path_prioritizer.py` and the function to `prioritize_paths`. Defer if you'd rather minimize disruption.

2. **`agentic_ops_v7/orchestrator.py` — Phase 0.6**
    - Replace single-flow walk with `asyncio.gather` over all candidates.
    - Pick primary report (highest-priority localized; first in list if none).
    - Stash `state["path_walk_report"]` (primary, as today) AND `state["path_walk_all_reports"]` (full list).
    - Log soft-cap warning and hard-cap truncation.
    - Log multi-walker compound observation (when ≥2 walks localize at distinct NFs).

3. **`agentic_chaos/recorder.py`**
    - Rename the "Resolver" subsection to "Prioritized Candidates" (or keep the old name, change the content).
    - Render the per-flow walker-outcome table with the primary marker.
    - Render soft-cap warning and hard-cap truncation notes when set.

4. **`agentic_ops_v7/tests/test_path_resolver.py`**
    - The `_F1_BROKEN_CASES` xfails become **redundant**, not unblocked: the resolver's flow_id pick no longer determines correctness because the walker walks all evidence-bearing flows. Remove the xfails or convert them to "the right flow appears somewhere in the candidate list" assertions (much weaker, much more honest).
    - The `_F1_PASSING_LOCALIZED_CASES` tests need to be rewritten: today they assert the resolver picks a specific flow. Under this ADR, they should assert "the walker eventually localizes at the expected NF, regardless of which flow ranks first" — that's the operational invariant that actually matters.
    - Add new tests for: soft-cap warning fires at 4 candidates; hard-cap truncation at 6; primary-selection logic (localized wins over null; falls back to first in list).

5. **Synthesis prompt / consumer audit (CLAUDE.md rule).** Walk every consumer of `state["path_walk_report"]` to confirm "primary report" semantics is acceptable. The Synthesis prompt is the load-bearing one. The compound-verdict guardrail may need to recognize multi-walker compound; if not, document the gap.

6. **Mark the previous ADR Superseded.** Add a one-paragraph note at the top of `resolver_nf_burden_scoring.md` pointing here and noting the symmetry insight.

## Validation target

- All 285 existing tests in `agentic_ops_v7` pass.
- The previously-broken cases (4 from 5/10 batch, 4 from 5/21 batch) produce a correct end-to-end diagnosis. The walker now walks the right flow regardless of resolver pick.
- The previously-passing localized cases (data_plane_degradation, call_quality_degradation, upf_bandwidth_cap on 5/10) keep their 100% scores — the walker still localizes at the right NF, just possibly via a different candidate flow than before.
- A re-run of the 5/21 batch against a freshly-deployed stack shows: walker walks 1-3 flows per scenario in the common case, ≥3 in the noisy scenarios with the soft-cap warning visible.
- Episode logs surface the prioritized-candidates table with per-flow walker outcomes.
- Wall-clock per chaos run: no measurable increase (within noise of run-to-run variance).

## Out of scope

- **Probe deduplication across flows.** Future optimization. Measure first.
- **Compound-verdict-from-walker+walker in Synthesis.** When ≥2 walks localize at different NFs, the existing compound prompt directive (`multi_fault_orchestration.md`) was designed for walker+app-layer. Extending it to walker+walker is a follow-up ADR.
- **Scoring formula redesign.** The current formula has known issues (NF-burden symmetry, observable_metrics blob brittleness) but those issues no longer break diagnostic correctness — they only affect *which* candidate the walker probes first. Defer until empirical data shows the rank order causing real wall-clock or operator-readability problems.
- **`screener_status == "starved"` → walk what?** Today the conservative-fallback routing engages the walker even when starved, but with no flagged NFs the resolver returns None and the walker doesn't run. Under this ADR that behavior is preserved (no evidence → no walk). If we want a default broad-probe under starvation, that's a separate ADR; the user-stated principle is "no smoking gun → don't walk."

## Resolved decisions (from review)

1. **Soft cap = 3.** Walk all evidence-bearing candidates; if more than 3 were walked, log a warning in the episode log.
2. **Hard cap = 5.** Never walk more than the top 5 by score. Candidates ranked 6+ are dropped, with the dropped flows listed in the candidates table marked `not walked (hard cap)`. The score formula is load-bearing at this boundary — it determines which 5 get walked when there are 6+.
3. **No short-circuit on first localization.** All selected candidates (up to cap) are walked. Lets the walker surface compound-fault patterns instead of stopping early.
4. **Parallel walks across flows, sequential within each flow.** `asyncio.gather` over per-flow walks; the inter-hop-diff probes within a flow need adjacent-hop ordering so per-flow walks stay sequential internally.
5. **Don't walk if zero evidence.** When the candidate list is empty (screener starvation, truly clean stack, or no flow's hop list contains any flagged NF), the walker doesn't run. The episode log records this explicitly.
6. **The scoring formula stays as-is for this iteration.** It's now a prioritization signal, not a selection decision. Revisiting it is a follow-up if the cap-boundary behavior shows real problems.
