# ADR: Multi-Fault Orchestration — `mixed` label runs both pipelines

**Date:** 2026-05-14
**Status:** Proposed
**Related:**
- [`path_anchored_probe_planning_for_transport_layer_faults.md`](path_anchored_probe_planning_for_transport_layer_faults.md) — defines the Phase 0.5 classifier, Phase 0.6 path walker, and the existing routing rules this ADR amends.
- [`structural_guardrails_for_llm_pipeline.md`](structural_guardrails_for_llm_pipeline.md) — load-bearing pipeline behavior is enforced structurally; the routing decision is one such piece of behavior.
- [`agentic_pipeline_v6_implementation.md`](agentic_pipeline_v6_implementation.md) — the application-layer pipeline (Phases 1–7) this ADR re-enables for compound scenarios.
- Task #61 (walker emits `container_dead` attribution) — independent and landed before this ADR. The two together let a single walker pass detect both a dead container AND a tc-netem fault, which feeds the multi-suspect handling this ADR introduces.
- Task #63 (classifier weighs ambiguous-cluster signals as `mixed`) — upstream dependency of this ADR; without it the new routing rule rarely fires.
- Failing run [`agentic_ops_v7/docs/agent_logs/run_20260514_193941_cascading_ims_failure.md`](../../agentic_ops_v7/docs/agent_logs/run_20260514_193941_cascading_ims_failure.md) — Cascading IMS Failure (pyhss kill + scscf 2s latency). Walker localized scscf, orchestrator short-circuited to Phase 7, pyhss missed entirely, score 15%.

---

## Decision

The Phase 0.6 transport-layer route's short-circuit to Phase 7 Synthesis becomes **conditional on the classifier label**, not unconditional on walker localization. The new routing matrix:

| Classifier label | Walker (Phase 0.6) | App-layer pipeline (Phases 1–7) | Synthesis input |
|---|---|---|---|
| `transport_layer` | run; short-circuit when localized | only when walker null-localized | `PathWalkReport` only (current behavior) |
| **`mixed`** | **run; never short-circuit** | **always run after walker** | **`PathWalkReport` + NA report + Investigator verdicts merged** |
| `application_layer` | skip | run | NA report + Investigator verdicts (current behavior) |

The walker's output shape also changes for the `mixed` path: instead of returning *one* `first_attributed_hop`, it surfaces **all** attributed hops so Synthesis can name every load-bearing fault rather than picking the earliest one.

Phase 7 Synthesis gains a fourth verdict_kind — `compound` — for the merged path. The existing `localized` verdict_kind keeps its current contract (single-hop attribution, kernel evidence only) and stays the right answer for genuine single-fault transport scenarios.

We add one guardrail to keep `compound` honest (see [Trade-offs](#trade-offs)). An earlier draft of this ADR also included a per-episode token cap; it was reverted after an empirical failure (see §Circuit-breakers).

---

## Context

### The problem this ADR solves

Today's orchestrator short-circuits to Phase 7 the moment the walker returns `is_localized=True`, regardless of classifier label:

```python
# agentic_ops_v7/orchestrator.py:2118-2128
if classifier_label in ("transport_layer", "mixed"):
    localized_result = await _phase06_transport_layer_route(...)
    if localized_result is not None:
        return localized_result          # ← short-circuits regardless of label
    # Fall through to application-layer pipeline.
```

For a single-fault transport scenario this is correct: the walker found the kernel-level cause, the app-layer pipeline would only re-derive the same fault at higher token cost, and Synthesis already has everything it needs. **For compound scenarios — one transport-layer fault + one application-layer fault — this is wrong.** The walker finds one of the two, the orchestrator short-circuits, and the application-layer pipeline never runs to characterize the second fault.

Concrete evidence from `run_20260514_193941_cascading_ims_failure` (Cascading IMS Failure scenario, ground truth: `pyhss` killed AND `scscf` netem delay 2000 ms):

- Phase 0.5 classifier flagged `transport=1, application=0, ambiguous=9`. Label: `transport_layer`. (Task #63 will fix this to `mixed`.)
- Phase 0.6 walker localized `scscf[eth0]` (`latency_at_hop: qdisc_netem_delay 2000.0 ms`). The pyhss hop reported `inconclusive: tool_unavailable: tc missing`. (Task #61 already fixed this — pyhss now reports `container_dead`.)
- Orchestrator short-circuited to Phase 7.
- Synthesis emitted `verdict_kind=localized, primary_suspect_nf=scscf` and the scoring rubric returned **15%** because the report listed only one of the two ground-truth root causes.

This is structural, not a one-off. Every future compound scenario that mixes a transport-layer fault with an application-layer fault hits the same failure mode.

### Why short-circuit was the right default originally

When [the path-walk ADR](path_anchored_probe_planning_for_transport_layer_faults.md) landed, every scenario in the chaos library was single-fault. Short-circuit served three concrete purposes:

1. **Token economics.** App-layer pipeline costs ~120K–160K tokens per run; localized-only Synthesis runs in ~8K. Skipping the app-layer pipeline when the walker has the answer saves ~95% of the token budget for transport-layer scenarios.
2. **Variance reduction.** App-layer reasoning is LLM-mediated and noisier than walker output. Skipping it where it adds nothing reduces the chance of an LLM hypothesis polluting a kernel-grade attribution.
3. **Latency.** App-layer pipeline adds ~150 s of LLM round-trips per run; the localized path completes in ~30 s.

None of these go away. We're only carving out the case where short-circuit hides a second root cause — and gating the carve-out behind a label (`mixed`) that the classifier issues exactly when it has evidence of compound failure.

### Why this can't be solved by tightening the walker alone

After task #61 lands the walker emits a `container_dead` attribution for the pyhss hop, so the cascading scenario will now have **two** attributed hops: pyhss (container_dead) at hop 16 and scscf (latency_at_hop) at hop 20. But the walker's current contract reports `first_attributed_hop` only — and the `Localization` Pydantic model on `DiagnosisReport` is a single-hop payload. Even with #61, Synthesis would emit `primary_suspect_nf=pyhss` (earliest attribution) and silently drop scscf, which is the same failure mode in reverse.

To surface both root causes the walker output shape must change AND Synthesis must accept multi-suspect input. That's why this ADR is structural, not a tweak.

### Why `mixed` and not "always merge"

The conservative alternative is to always run both pipelines after the walker. That works diagnostically but costs every transport-layer single-fault run an extra 120K+ tokens for no benefit. Routing the cost to `mixed` only lets us keep the per-fault-class economics while paying for compound diagnoses when (and only when) the evidence warrants it.

The risk is asymmetric:
- A `mixed` label fired on a single-fault scenario costs ~20× extra tokens for that one run.
- A `transport_layer` label fired on a compound scenario silently drops the second fault (today's failure mode).

`mixed` is the label that says "I have evidence of more than one layer being broken." Per task #63 it will be issued when ambiguous flags cluster on a different layer from the transport flag's owner. That's a structurally accurate trigger — paying app-layer tokens then is the right trade.

---

## Design

### 1. Routing matrix

The orchestrator's Phase 0.6 routing decision becomes (pseudocode, replacing the current `if classifier_label in ("transport_layer", "mixed"):` block):

```python
classifier_label = state["symptom_classification"]["label"]

walk_report = None
if classifier_label in ("transport_layer", "mixed"):
    walk_report = await _phase06_run_walker(state, ...)

if classifier_label == "transport_layer":
    if walk_report and walk_report.is_localized:
        return await _phase07_synthesis_localized(walk_report, ...)
    # else: fall through to app-layer

# `mixed` always runs both. `application_layer` runs app-layer only.
# `transport_layer` lands here only when the walker null-localized.

await _phase1_event_aggregator(...)
await _phase2_correlation_analyzer(...)
await _phase25_rag(...)
# ... NA, IG, Investigators, Evidence Validator ...

if classifier_label == "mixed":
    return await _phase07_synthesis_compound(walk_report, na_report, verdicts, ...)
else:
    return await _phase07_synthesis_application_layer(na_report, verdicts, ...)
```

Three new code paths land:
- `_phase06_run_walker` — extracted from `_phase06_transport_layer_route` so the orchestrator can run the walker and decide what to do with the result, rather than letting the helper decide for it.
- `_phase07_synthesis_compound` — new Synthesis branch that takes both the `PathWalkReport` and the application-layer bundle.
- A `compound` verdict_kind value on `DiagnosisReport`.

The `mixed` case where the walker null-localized is treated as a *demoted* application-layer scenario — the path walker found nothing, no kernel-level evidence exists, so Synthesis emits one of `{confirmed, promoted, inconclusive}` from the app-layer pipeline output. No `compound` verdict without walker attribution to back it up.

### 2. Walker output: multi-suspect

The walker today returns `PathWalkReport.first_attributed_hop`. We extend the report (additively — existing single-suspect consumers don't break):

```python
class PathWalkReport:
    ...

    @property
    def attributed_hops(self) -> list[HopRecord]:
        """All hops with a load-bearing attribution, in topology order.

        Used by the compound-verdict Synthesis branch to surface every
        root cause the walker found. Includes drops_attributed_here,
        drops_attributed_to_inbound_link, latency_at_hop, container_dead.
        Excludes clean and inconclusive.
        """
        return [
            r for r in self.hops
            if r.attribution.kind in (
                "drops_attributed_here",
                "drops_attributed_to_inbound_link",
                "latency_at_hop",
                "container_dead",
            )
        ]

    # first_attributed_hop and is_localized keep their current contract.
```

Topology order matters: when the walker traverses a flow and finds drops at hop A then drops at hop B downstream of A, the upstream attribution is the cause and the downstream is the consequence. The list-order convention lets Synthesis prefer earlier hops when the operator wants a single root cause, and lets it surface all attributions when ranking is ambiguous.

**De-duplication.** A single container hop can appear multiple times in a flow walk (e.g. uplink scscf at hop 18, downlink scscf at hop 32). The walker collapses entries with matching `(node, iface, kind)` triples into one — they're the same fault observed twice. Entries that share `(node, iface)` but differ in `kind` are kept separate: drops on uplink + latency on downlink at the same hop are *two* faults, not one, even though they're at the same physical NF. This matters operationally because the operator's remediation differs per fault kind.

### 3. Synthesis input shape

For the `compound` verdict the Synthesis prompt sees both inputs and emits a multi-suspect `DiagnosisReport`. The Pydantic model gains a list field that's `Optional` so the existing single-suspect schema continues to validate:

```python
class DiagnosisReport(BaseModel):
    ...
    verdict_kind: Literal["confirmed", "promoted", "inconclusive",
                           "localized", "compound"]
    primary_suspect_nf: _KnownNF | None       # required for non-inconclusive
    additional_root_causes: list[RootCause]   # NEW — populated on `compound`
    localization: Localization | None         # walker attribution for primary
    ...

class RootCause(BaseModel):
    """One contributing root cause in a compound diagnosis.

    Mirror of the primary slot — suspect NF + layer + evidence pointer.
    Populated by the compound-verdict branch when the walker found
    transport-layer faults AND the application-layer pipeline produced
    a strong-evidence hypothesis whose primary_suspect_nf differs from
    the walker's primary attributed hop.
    """
    primary_suspect_nf: _KnownNF
    fault_layer: Literal["transport", "application"]
    evidence_source: Literal["path_walk", "investigator", "anomaly_screener"]
    evidence_summary: str
    confidence: Literal["high", "medium", "low"]
```

The compound verdict's primary slot is reserved for the **most localized** root cause — usually the walker's earliest attributed hop because kernel evidence is exact. The application-layer hypothesis gets a `RootCause` entry. If the walker null-localized despite the `mixed` label, we don't emit `compound` — we fall back to application-layer rules.

### 4. Synthesis prompt + guardrails

The Synthesis prompt today has one branch-select directive at the top: localized-vs-application-layer based on whether `{path_walk_for_synthesis}` is non-empty. It gains a third branch:

> If both `{path_walk_for_synthesis}` is non-empty (the walker localized) AND `{network_analysis}` is non-empty (the application-layer pipeline ran), emit `verdict_kind=compound`. Primary slot = the walker's earliest attributed hop. Populate `additional_root_causes` with every NA-hypothesis-derived fault whose `primary_suspect_nf` differs from the primary. Each `RootCause` entry must cite its evidence source (path_walk | investigator | anomaly_screener) and quote the verbatim evidence excerpt.

Two new guardrails layer on top of the existing localized-consistency check:

- **`lint_compound_verdict_consistency`** — if `verdict_kind=compound`, both `path_walk_report.is_localized=True` AND `network_analysis` must be populated. Either missing → REJECT with a directive to resample as the appropriate single-branch verdict.
- **`lint_compound_additional_causes`** — if `verdict_kind=compound`, `additional_root_causes` must be non-empty (otherwise the verdict carries no compound information and should be `localized`). The list cannot contain the primary's `primary_suspect_nf` (no duplicates). Each entry's `evidence_source` must point at a real artifact in the input bundle.

Both follow the structural-guardrails pattern from prior ADRs: mechanical post-emit checks, resample directive on REJECT.

### 5. Circuit-breakers against false `mixed` labels

One guardrail is the only remaining safeguard:

1. **Synthesis-emitted `compound` requires walker localization.** Classifier may say `mixed`, orchestration may pay for both pipelines, but Synthesis still can't emit `compound` without kernel evidence to back the primary slot. A `mixed`-labeled run whose walker null-localizes degrades cleanly to application-layer-only verdicts (`confirmed` / `promoted` / `inconclusive`). Enforced by `lint_compound_verdict_consistency`.

**Reverted circuit-breaker — per-episode token cap.** The original draft of this ADR also proposed a 200K per-episode cumulative token cap, intended to bound damage from false-positive `mixed` labels. The cap was implemented as a check at the entry to Phase 7 Synthesis: if `sum(p.tokens.total for p in all_phases) > 200_000`, skip Synthesis and emit an `inconclusive` sentinel.

**It was removed on 2026-05-15** after `run_20260514_220149_data_plane_degradation`. That episode was a single-fault Data Plane Degradation scenario that the classifier false-positive-labeled `mixed`. The app-layer pipeline ran cleanly and produced an h1=UPF NOT_DISPROVEN consensus with paired-probe triangulation, multi-shot agreement, and the right answer staring at Synthesis. The cap fired at **458K cumulative** and Synthesis was replaced with an `inconclusive` sentinel — destroying a diagnosis that would have scored well.

What went wrong:

- **Granularity was wrong.** The cap measured *cumulative across all prior phases*. With three parallel Investigators each running multi-shot consensus, cumulative tokens routinely hit 300K–500K on perfectly valid runs (NA ~50K + IG ~70K + 3 × Investigator × 2 shots × ~50K avg). The cap fired on normal pipeline behavior, not runaway behavior.
- **Threshold was wrong.** The "worst-case 160K" anchor came from a no-walker, single-Investigator-fan-out run. It was not a worst case for the compound path with Investigator fan-out. Even with the granularity issue fixed, 200K would be too low.
- **The cap defeated its own purpose.** False-positive `mixed` labels are the very thing the cap was supposed to protect against — but on those scenarios the app-layer pipeline produces a *valid* diagnosis, not runaway behavior. The cap was killing correct answers instead of bounding wrong ones.

Lesson and forward guidance:

- The classifier's accuracy (task #63) plus the compound-consistency guardrail are the actual backstops. They're load-bearing; the token cap added nothing on top.
- If a future runaway *does* materialize, re-add a cap that measures the *Synthesis call alone*, not whole-run cumulative — Investigator fan-out is normal and shouldn't be subject to the same guard as a Synthesis-prompt blowup.
- General principle: don't size empirical thresholds against a single observed worst-case run; sample across the failure mode shapes you're actually trying to bound.

The single remaining guardrail above is sufficient.

---

## Trade-offs

| Option | Token cost (compound) | Single-fault regression risk | Operational complexity | Outcome on the failing run |
|---|---|---|---|---|
| **A. Status quo** (short-circuit on any walker localization) | n/a — fault is silently missed | none | none | 15% — what we have today |
| **B. Always run both pipelines after walker** | ~150K extra on every transport-layer scenario | none | low | ≥90% — but ~20× cost inflation on all transport runs |
| **C. `mixed` label runs both** (this ADR) | ~150K extra **only on `mixed`-labeled scenarios** | depends on classifier precision (task #63) | medium — new verdict_kind, two new guardrails, three circuit-breakers | ≥90% on compound scenarios; transport-layer scenarios unchanged |
| **D. Walker returns multi-suspect, Synthesis still single-branch** | ~0 extra | none on single-fault | low | partial — Synthesis still picks one suspect; doesn't actually surface both faults |

Option C is the only choice that gets compound diagnosis right without paying the regression tax on single-fault runs. Option D is necessary infrastructure (the multi-suspect walker output) but not sufficient on its own — without the new Synthesis branch, multi-suspect walker output collapses back to a single primary at Synthesis time.

---

## Implementation outline

Land in this order:

1. **PathWalkReport.attributed_hops** (`agentic_ops_common/path_walk/protocol.py`). Additive — no consumer breaks. Unit-tested alongside existing `first_attributed_hop` tests.
2. **DiagnosisReport.additional_root_causes + RootCause** (`agentic_ops_v7/models.py`). Optional field; existing reports validate unchanged. Pydantic-level tests.
3. **`compound` verdict_kind** added to `DiagnosisReport.verdict_kind` Literal and to the Synthesis pool-membership guardrail's allowed set.
4. **`lint_compound_verdict_consistency` + `lint_compound_additional_causes`** guardrails (`agentic_ops_v7/guardrails/`). Pure unit tests against synthetic `DiagnosisReport` fixtures, no LLM involvement.
5. **Synthesis prompt** (`agentic_ops_v7/prompts/synthesis.md`). New branch-select directive; new section explaining compound-verdict rules; bad-output / good-output examples per the prompt-engineering pattern used elsewhere in v7.
6. **Orchestrator routing** (`agentic_ops_v7/orchestrator.py`). Extract `_phase06_run_walker` from `_phase06_transport_layer_route`. New compound-branch arm in the main `investigate()` flow. (An earlier revision of this step also added a per-episode token-budget circuit-breaker; reverted — see §Circuit-breakers.)
7. **Recorder** (`agentic_chaos/recorder.py`). Render `verdict_kind=compound` with the primary slot table + `additional_root_causes` list. Backwards-compatible — old episode JSONs continue to render via the existing single-suspect path.
8. **Episode-log JSON shape**: `challenge_result["compound_root_causes"]` mirrors `additional_root_causes` for the recorder. Recorder-side parsing handles missing-key (older runs) gracefully.

Touches 8 files across `agentic_ops_v7/`, `agentic_ops_common/`, and `agentic_chaos/`. No changes to v5/v6 — they keep their frozen behavior.

---

## Backwards compatibility & risk

**Schema:** `additional_root_causes` is optional with `default=[]`. Old `DiagnosisReport` JSONs validate unchanged. `verdict_kind=compound` is new; old reports never emit it. No migration needed.

**Behavior on the existing 26+ historical scenarios:** if task #63 is *not* landed, the classifier never emits `mixed` (today's label distribution shows zero `mixed` labels on the existing chaos library). So this ADR is a no-op on every scenario until #63 lands. That's the deliberate dependency ordering — the classifier change unlocks the routing change.

**Risk: classifier mis-labels** a single-fault scenario as `mixed`. Mitigations:
- The guardrail (`compound` requires walker localization) means a `mixed`-labeled single-fault scenario degrades to whichever single-branch verdict the bundle supports, not an invented compound verdict. The app-layer pipeline still runs and produces its normal output; Synthesis chooses the right verdict_kind based on what the bundles contain.
- **Empirical observation.** False positives do happen (see task #63's corpus analysis: HSS Unresponsive, Data Plane Degradation, Call Quality Degradation occasionally label `mixed`). On every observed case the app-layer pipeline still produces a correct diagnosis and Synthesis emits a valid single-suspect verdict. The marginal cost is the extra walker pass (~8K) plus whatever Investigator fan-out the scenario triggers — not catastrophic.

**Risk: Synthesis hallucinates the second root cause.** The existing post-emit guardrail pattern handles this. `lint_compound_additional_causes` requires each `RootCause.evidence_source` to point at a real artifact (`path_walk_report.attributed_hops` for `path_walk`, `network_analysis.hypotheses` for `investigator`, `anomaly_flags` for `anomaly_screener`). Anything else REJECTs.

**Risk: token-cost blowout in production batches.** Token cost stays proportional to the number of `mixed` labels the classifier emits × the Investigator fan-out per scenario. Batch-level economics are controlled by task #63's classifier accuracy, not by a per-episode cap (which was tried and removed — see §Circuit-breakers). The recorder prints per-phase token counts so any run going pathologically high is visible immediately in the episode log; that's the operator-facing signal.

---

## Testing strategy

**Unit tests (pre-merge):**
- `PathWalkReport.attributed_hops` returns load-bearing attributions in topology order, deduplicates `(node, iface, kind)` repeats.
- `lint_compound_verdict_consistency` REJECTs `compound` without walker localization; REJECTs `compound` without NA output; PASSes both populated.
- `lint_compound_additional_causes` REJECTs empty list, REJECTs primary-NF duplicate, REJECTs invalid `evidence_source`.
- Recorder renders the `compound` verdict including the multi-cause list.

**Integration tests (live stack, manual gate):**
- Re-run `Cascading IMS Failure` after both this ADR and tasks #61 + #63 land. Expectation: classifier `mixed`, walker finds pyhss `container_dead` + scscf `latency_at_hop`, NA hypothesizes pyhss-exited, Synthesis emits `compound` with both root causes, score ≥90%.
- Re-run every existing single-fault scenario. Expectation: classifier `transport_layer` or `application_layer` (never `mixed`), behavior unchanged, scores within ±5% of historical mean.

**Empirical validation (post-merge):**
- Batch run of all chaos scenarios with the full v7 stack. Compare scores and token usage against the May-10 baseline. Compound scenarios should improve dramatically; single-fault scenarios should be unchanged.

---

## Validation & rollout

Sequencing constraint: this ADR depends on task #63. Without `mixed`-firing classifier signal, the new routing path is unreachable. Recommended rollout:

1. Task #61 (walker `container_dead`) — **landed**.
2. Task #63 (classifier `mixed` rule, with corpus analysis). Tune thresholds on the 26-episode historical corpus until the false-positive rate of `mixed` is ≤10% (single-fault scenarios mislabeled `mixed`) and the false-negative rate is ≤5% (true compound scenarios mislabeled single-layer).
3. This ADR's implementation. Land with circuit-breakers **enabled** by default for the first week of operation.
4. Re-run the chaos batch. Confirm the `Cascading IMS Failure` improvement and the no-regression property on single-fault scenarios.
5. If no false-positive `mixed` runs hit the token cap over the first ~50 episodes, optionally relax circuit-breakers (or keep them — they're cheap insurance).

The decision point at each step is empirical, not architectural: each step has a measurable failure mode that gates the next.

---

## Out of scope

- **Carrier-grade hop kinds.** The path walker's `HopKind` literal includes `l2_switch`, `wan_edge`, etc., but no probers exist for them yet. The compound-verdict change is hop-kind-agnostic — if those probers ship later and produce `DropsAttributedHere` attributions, they'll feed the same multi-suspect path without further ADR.
- **More than two root causes.** The schema supports `additional_root_causes: list[RootCause]` with no upper bound, but we have no chaos scenario today that injects three+ faults. We'll size the prompt's worked examples for two, and let the schema absorb whatever future scenarios bring.
- **Cross-fault causal reasoning.** Synthesis emits the *list* of root causes; it does not reason about whether one caused the other. That's a follow-up ADR (`causal_chain_across_root_causes.md`?) if and when we have scenarios where the causal direction matters operationally.
- **App-layer pipeline pruning under `mixed`.** Today every app-layer phase runs in full. A future optimization could skip Phases 2.5 (RAG) or 4 (IG) when the walker already produced strong attribution, to claw back some of the token cost. Not in this ADR.

---

## Open questions for review

1. **What's the right text in the resample directive for `lint_compound_additional_causes` REJECT?** Today's localized-consistency guardrail directive is ~10 lines and works well. The compound-consistency variant needs at least three modes (no walker, no NA, no additional causes). I'll draft templates with the implementation; flagged here so the prompt-tuning step doesn't catch us by surprise.

2. **Should there be a separate Synthesis agent for the `compound` branch?** Today there's one Synthesis agent with a multi-branch prompt. Adding a fourth branch makes the prompt longer and potentially less reliable. Two cleaner alternatives: (a) prompt stays unified, branch-select directive expanded; (b) new `compound_synthesis_agent` parallel to the existing one, dispatched by the orchestrator. Default in the draft is (a) for consistency. Open to (b) if it produces more reliable output in pre-merge testing.

## Resolved decisions (from review)

- **`compound` is a fourth `verdict_kind`** — keeps the guardrail allow-lists clean and matches the pattern set by `localized`. Not a flag on `localized`.
- **Walker `attributed_hops` deduplicates on `(node, iface, kind)`** — uplink and downlink visits of the same hop with the same attribution kind collapse to one entry; entries that share `(node, iface)` but differ in `kind` stay separate because they represent operationally distinct faults at the same physical NF.
