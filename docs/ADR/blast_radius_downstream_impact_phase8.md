# ADR: Phase 8 — Blast Radius & Downstream Impact (deterministic compute + grounded narration)

**Date:** 2026-05-27
**Status:** Proposed
**Related:**
- The ontology's downstream-effect data this builds on:
    - `network_ontology/data/causal_chains.yaml` — failure modes with named `cascading` branches (each has `effect`, `mechanism`, `source_steps`, `observable_metrics`, `discriminating_from`, `lag`).
    - `network_ontology/data/flows.yaml` — procedures with `name` + `use_case` (`5g_core` / `vonr` / `ims`) and per-step `failure_modes` / `metrics_to_watch`.
    - `network_ontology/data/components.yaml` — `use_cases` per component.
- Existing agent-facing tools reused for the deterministic compute:
    - `get_canonical_flows_through_component` / `get_active_flows_through_component` (`agentic_ops_common/tools/flows.py`).
    - `get_causal_chain_for_component` / `find_chains_by_observable_metric` (`agentic_ops_common/tools/causal_reasoning.py` → `network_ontology/query.py`).
- Dead code this revives: `OntologyClient.get_downstream_impact` (`network_ontology/query.py`, defined but never called) and `topology.impact_of` (wrapped as `compute_blast_radius`, test-only).
- [`multi_fault_orchestration.md`](multi_fault_orchestration.md) — compound verdicts; Phase 8 must handle multiple root-cause NFs (primary + `additional_root_causes`).
- Sibling determinism-first ADRs from the same arc: [`path_prioritizer_walks_all_candidates.md`](path_prioritizer_walks_all_candidates.md), and the AffectedComponent typed-schema fix. Phase 8 follows the same principle: **the LLM never decides what's affected — it only describes what deterministic code already determined.**

---

## Decision

Add **Phase 8 — Impact Assessment**, a dedicated phase that runs after Phase 7 Synthesis and produces a **Blast Radius & Downstream Impact** section in the final report. It has two strictly separated halves:

1. **Deterministic compute (no LLM).** From the final diagnosis's root-cause NF(s), compute a fully-structured `BlastRadius` object — affected NFs, affected flows, affected services — by ontology graph traversal (the *potential* set) intersected with this episode's actual evidence (the *observed* set). Every entry is tagged `failing` / `degraded` / `at_risk`, where `at_risk` is the potential-but-not-observed tail.

2. **Grounded narration (small LLM call).** A pure narrator sub-agent receives the deterministic `BlastRadius` object and writes human-readable prose for the report. Its sole job is readability. It MAY NOT introduce any NF, flow, or service that is not already present in the computed object; a guardrail rejects output that references anything outside the computed set.

The structured impact data is 100% deterministic and trustworthy. The LLM adds only prose, grounded in that data plus the explicitly-named NFs and ontology facts from the prior phases. It invents nothing.

Decisions locked in review: a full phase named **Phase 8** (not 7.5); separate narrator sub-agent (Fork A.1); `at_risk` entries are shown and clearly tagged (Fork B.1); impact layers = NF + flow + service (business/subscriber/SLA layer deferred); source of truth = hybrid; report shows both potential and observed.

## Context

### What already exists

The ontology is rich in downstream-effect data, but it's *investigation fuel*, not *report output*. Causal chains describe cascading branches with the flow steps they block and the metrics that signal them; flows map procedures to NFs and use-cases; the agents already consult all of this during investigation via existing tools. None of it is captured into the final structured diagnosis or surfaced as a consequence-of-failure section.

The closest existing artifact is `DiagnosisReport.affected_components` (NF `name` + `role`: Root Cause / Secondary / Symptomatic) — terse, NF-only, no flow or service framing. The report's "Blast radius" header field is the scenario author's *input* label (`single_nf` / `multi_nf` / `global`), not the agent's computed consequence.

Two impact functions exist but are dead: `OntologyClient.get_downstream_impact` (one-hop ontology neighbors, never called) and `topology.impact_of` (one-hop topology neighbors, test-only). Both are too shallow on their own (single hop, no service/flow framing, no observed-vs-potential distinction), but `get_downstream_impact` is a useful primitive for the deterministic compute.

### The gap

The raw material is present; what's missing is **structure + surfacing + audience translation**. A NOC engineer reading the report can't see "which procedures and services this failure took down," and there's no machine-readable impact block on the diagnosis artifact. Phase 8 closes that gap without asking the LLM to reason about impact — the reasoning is deterministic graph traversal; the LLM only narrates.

## Design

### Phase placement

```
Phase 7    Synthesis → DiagnosisReport (primary_suspect_nf [+ additional_root_causes], verdict_kind)
Phase 8    Impact Assessment:
   8a  DETERMINISTIC compute_blast_radius(diagnosis, state) → BlastRadius   (no LLM)
   8b  LLM narrator: fills BlastRadius.narrative, grounded ONLY in 8a       (small LLM call)
   8c  grounding guardrail: every NF/flow/service named in narrative ∈ 8a   (reject otherwise)
```

Phase 8 runs on every terminal verdict. For `inconclusive` (no root-cause NF), it emits an explicit "impact undetermined — no root cause localized" `BlastRadius` and skips the LLM call (nothing to narrate, nothing to invent).

### 8a — the deterministic compute

Input: the diagnosed root-cause NF set = `{primary_suspect_nf}` ∪ `{rc.primary_suspect_nf for rc in additional_root_causes}`. For `localized` verdicts the root-cause NF is the walker's attributed hop node.

**Potential set (ontology, worst-case from the root-cause NF):**
1. **Affected flows** — `get_canonical_flows_through_component(nf)` for each root-cause NF → the union of flows whose hop list traverses it.
2. **Causal cascading branches** — `get_causal_chain_for_component(nf)` → branches, each carrying `source_steps` (`flow.step` references) and `observable_metrics`. This refines "which steps of which flows break" and supplies the metric signatures used for the observed intersection.
3. **Affected services** — each affected flow's `use_case` (`5g_core` / `vonr` / `ims`) mapped to a plain-language service label (e.g. `vonr` → "VoNR voice calls", `5g_core` → "5G data / registration", `ims` → "IMS signaling").

**Observed set (this episode's evidence — already in orchestrator `state`):**
For each potential flow/branch, check for corroborating signal from the pipeline's own observations:
- the branch's `observable_metrics` ∩ the episode's flagged metrics (`state["anomaly_flags"]` / `symptom_classification` buckets),
- `state["fired_events"]` matching the branch,
- the flow's NFs appearing in the walker attributions (`path_walk_all_reports`) or Investigator findings.

**Status assignment (how potential and observed combine into one tag):**
- `failing` — observed with strong corroboration (flagged metric on the branch AND a fired event / walker-or-investigator finding).
- `degraded` — observed with partial corroboration (e.g. a single flagged metric, lower severity).
- `at_risk` — in the potential set but no observed signal this episode (the "potential" tail; Fork B.1 — shown, clearly tagged).

This is pure dictionary/set arithmetic over ontology lookups and `state` — fully deterministic and replayable.

### The structured output

```python
class AffectedFlow(BaseModel):
    flow_id: str
    flow_name: str
    use_case: str                                   # 5g_core | vonr | ims
    status: Literal["failing", "degraded", "at_risk"]
    evidence: str          # the observed signal(s), or "potential — no direct signal this episode"

class AffectedService(BaseModel):
    service: str                                    # plain-language, e.g. "VoNR voice calls"
    status: Literal["failing", "degraded", "at_risk"]
    affected_flow_ids: list[str]

class BlastRadius(BaseModel):
    root_cause_nfs: list[str]                       # the NF(s) the impact was computed from
    affected_nfs: list[AffectedComponent]           # reuse the existing typed model
    affected_flows: list[AffectedFlow]
    affected_services: list[AffectedService]
    narrative: str = ""                             # filled by 8b ONLY; "" on inconclusive
```

8a fills everything except `narrative`. The structured fields are the source of truth; the recorder renders them as deterministic tables regardless of the LLM.

### 8b — the grounded narrator

A small sub-agent (`create_impact_narrator_agent`) whose prompt receives the fully-computed `BlastRadius` object (serialized) plus the diagnosis summary, and emits only the `narrative` prose: one NOC-facing paragraph (NFs, flows, the failing/degraded/at-risk split) and one service-facing sentence a non-engineer can read ("VoNR voice calls are failing; new 5G registrations are degraded").

Hard constraints, stated in the prompt and enforced structurally:
- It may reference **only** NFs/flows/services present in the injected `BlastRadius`.
- It may not assign or change a `status` — those are fixed by 8a; the narrator describes them.
- It may not introduce subscriber counts, SLAs, or numbers (business layer is out of scope).

### 8c — the grounding guardrail

A deterministic check (no LLM): tokenize the narrative for flow_ids, service labels, and NF names; assert every referenced entity appears in the 8a `BlastRadius`. On violation, REJECT and resample once with the offending tokens injected; if it fails twice, fall back to a deterministic template narrative built directly from 8a (no LLM) so the report still ships with grounded prose. This makes "invents nothing" a structural guarantee, not a prompt aspiration.

### Report rendering

A new "## Blast Radius & Downstream Impact" section in the episode markdown:
- **Narrative** (8b prose) at the top — the readable summary for both audiences.
- **Affected services** — plain-language list with status.
- **Affected flows** — table: flow / use_case / status / evidence.
- **Affected NFs** — the typed `affected_nfs` with roles.

The existing scenario-header "Blast radius: single_nf" stays (it's the author's input label); the new section is the agent's *computed* consequence and is clearly distinct.

## Trade-offs and limitations

- **Bounded by what the ontology encodes.** If a flow or causal branch isn't authored, it won't appear in the potential set. This is the correct failure mode (under-report rather than hallucinate) and matches the determinism guarantee. Authoring gaps surface as missing entries, which is a useful signal to improve the ontology.
- **`at_risk` can read as noise to some teams.** Showing potential-but-unobserved impact is what "both potential and observed" requires; the explicit tag + the `evidence` text ("potential — no direct signal this episode") keep it honest. If it proves noisy in practice, suppressing `at_risk` is a one-line filter later.
- **One extra LLM call per episode.** Small and bounded (narration only, no tools, no investigation). The deterministic fallback (8c) means a narrator failure never blocks the report.
- **Service mapping is coarse (3 use-cases).** `5g_core` / `vonr` / `ims` is the granularity `flows.yaml` currently carries. Finer service decomposition (e.g. "SMS over IMS" vs "voice over IMS") would need flow-metadata enrichment — deferred with the business layer.
- **Compound verdicts widen the potential set.** Multiple root-cause NFs union their flows/services. This is correct but can produce a large `at_risk` tail; the status tags keep the observed core distinguishable.
- **Not scored.** Blast-radius accuracy is report-only this iteration (no new scoring dimension — consistent with having just removed `layer_accuracy`). A future ADR could add a scored dimension once the section has proven out.

## Implementation outline

1. **`agentic_ops_v7/models.py`** — add `AffectedFlow`, `AffectedService`, `BlastRadius` (reusing `AffectedComponent`). Strongly typed, required fields, `extra="forbid"` (same discipline as the AffectedComponent fix so the narrator's structured echo can't carry empty elements).
2. **`agentic_ops_v7/blast_radius.py`** (new) — `compute_blast_radius(diagnosis_report, state) -> BlastRadius`: the deterministic 8a logic. Pure function over ontology tool results + `state` evidence; no LLM, no I/O beyond the ontology queries.
3. **Revive the dead primitives** — use `get_downstream_impact` and the flows-through-component queries inside `compute_blast_radius`; add a unit-tested wrapper if their shape needs adapting.
4. **`agentic_ops_v7/subagents/impact_narrator.py`** (new) — `create_impact_narrator_agent()`; prompt at `agentic_ops_v7/prompts/impact_narrator.md`. Output is the `narrative` string only (or a `BlastRadius` echo whose structured fields must equal the injected ones — TBD in impl; simplest is narrative-only).
5. **`agentic_ops_v7/guardrails/impact_grounding.py`** (new) — 8c grounding check + deterministic template fallback.
6. **`agentic_ops_v7/orchestrator.py`** — add `_phase8_impact_assessment(state, ...)`; call it after Synthesis on every terminal path (localized, compound, confirmed, promoted, inconclusive). Write `state["blast_radius"]`. Add a `PhaseTrace(agent_name="ImpactAssessment")`. Surface `blast_radius` in `_build_result`.
7. **`agentic_chaos/agents/challenger.py`** — forward `blast_radius` through the inbound/outbound field-copy shims (the layer the AffectedComponent run-through earlier proved is easy to miss).
8. **`agentic_chaos/recorder.py`** — render the new section.
9. **Tests** — deterministic compute pins (potential set from a known NF; observed intersection from synthetic flags; status assignment; inconclusive → empty); grounding-guardrail pins (narrative referencing an out-of-set flow is rejected; fallback template fires on double failure); schema pins (typed models reject empty elements).

## Validation target

- A re-run of a localized scenario (e.g. p_cscf_latency) produces a Blast Radius section naming the IMS-registration / VoNR-call-setup flows as `failing` (observed: the CSCF metrics flagged) and any pcscf-traversing flow with no signal as `at_risk`, with the service line "VoNR voice calls / IMS signaling — failing."
- A data-plane scenario (upf_bandwidth_cap) names the data-PDU and VoNR-media flows, service "5G data / VoNR media."
- Grounding guardrail: inject a narrator output that mentions a flow not in the computed set → REJECT, then template fallback. Verify no episode ships a narrative referencing anything outside `compute_blast_radius`'s output.
- Inconclusive verdict → "impact undetermined" section, no LLM call.
- Full `agentic_ops_v7` + `agentic_chaos` suites green; episode JSON gains `blast_radius` and pre-Phase-8 episodes still render (recorder treats a missing `blast_radius` as "section omitted").

## Out of scope

- Business / subscriber / SLA layer; subscriber-scale numbers; criticality tiers (deferred per review).
- Scoring blast-radius accuracy.
- Finer-than-use_case service decomposition.
- Quantified propagation timing / MTTR / RTO (the `lag` field exists in causal chains but is not surfaced this iteration).

## Resolved decisions (from review)

1. **Phase 8, a full named phase after Phase 7** — not a fractional "7.5" phase.
2. **Separate narrator sub-agent** (Fork A.1) — keeps deterministic compute and diagnosis cleanly separated; the grounding guardrail validates the narrator in isolation.
3. **`at_risk` entries shown, clearly tagged** (Fork B.1) — this is how the "potential" half surfaces.
4. **Impact layers = NF + flow + service**; business/subscriber/SLA deferred.
5. **Hybrid source of truth**, with the determinism boundary placed so the LLM is a *pure narrator*: it produces human-readable prose only, grounded in the deterministically-computed `BlastRadius`, the explicitly-named NFs, and ontology facts. It invents nothing — enforced by the 8c grounding guardrail, not just the prompt.
6. **Both potential and observed**, encoded inline via the `failing` / `degraded` / `at_risk` status tag rather than two separate lists.
