# ADR: Layer Accuracy Scoring Dimension

**Date:** 2026-04-08
**Status:** Accepted
**Related:**
- Episode that surfaced the gap: [`agentic_ops_v5/docs/agent_logs/run_20260408_144319_hss_unresponsive.md`](../../agentic_ops_v5/docs/agent_logs/run_20260408_144319_hss_unresponsive.md)
- Ontology component definitions: [`network_ontology/data/components.yaml`](../../network_ontology/data/components.yaml)
- Network Analyst prompt (layer definitions): [`agentic_ops_v5/prompts/network_analyst.md`](../../agentic_ops_v5/prompts/network_analyst.md)

---

## Decision

Add a new `layer_accuracy` scoring dimension to the LLM-based Challenge Mode scorer, and rebalance the scoring weights to accommodate it. The new dimension checks whether the agent correctly attributed affected components to their ontology-defined layers in the network analysis layer status table.

**New weights:**

| Dimension | Old Weight | New Weight | Type |
|-----------|-----------|------------|------|
| `root_cause_correct` | 40% | **40%** | bool |
| `component_overlap` | 25% | **20%** | float 0.0–1.0 |
| `severity_correct` | 15% | **15%** | bool |
| `fault_type_identified` | 10% | **10%** | bool |
| `layer_accuracy` | — | **5%** | bool (new) |
| `confidence_calibrated` | 10% | **10%** | bool |

The 5% for `layer_accuracy` comes from `component_overlap`, which dropped from 25% to 20%. Root cause identification remains the dominant signal at 40%.

## Context

### The triggering episode

During the `hss_unresponsive` chaos scenario (2026-04-08), the agent (Gemini Flash) produced a perfect 100% diagnosis — it correctly identified `pyhss` as the root cause, diagnosed the Diameter silent failure, and traced the full cascading impact chain. However, the Network Analysis phase contained a layer misattribution:

| Layer | Rating | Agent's Rationale |
|---|---|---|
| **infrastructure** | RED | "HSS is running but non-responsive on the network, constituting an infrastructure failure" |
| **ims** | RED | "IMS core is non-functional due to its inability to communicate with the HSS" |

The ontology explicitly defines `pyhss` as `layer: ims` (role: subscriber-db, subsystem: IMS Subscriber DB). The Network Analyst prompt itself lists HSS under the IMS layer: *"ims — IMS functions in scope (typically P-CSCF, I-CSCF, S-CSCF, HSS, RTPEngine)"*. The actual infrastructure components (MongoDB, MySQL, DNS) were unaffected.

The agent conflated the **nature of the failure** (network/transport-level unreachability) with the **layer of the component**. It observed that HSS was unreachable at the network level, and concluded that network unreachability equals an infrastructure problem. In reality, a component in the IMS layer can suffer a network-level failure — that doesn't move it to the infrastructure layer.

### Why the existing scorer missed this

The scorer evaluated five dimensions — root cause, component overlap, severity, fault type, and confidence calibration — none of which assessed whether the agent's layer status table correctly mapped components to their ontology layers. The agent got a 100% score despite misattributing HSS to the infrastructure layer because the diagnosis itself (root cause, component identification, etc.) was accurate.

Layer accuracy matters because the layer status table is what a NOC operator reads first. If it says "infrastructure RED" when the actual problem is in the IMS layer, the operator may start investigating MongoDB, MySQL, and DNS — wasting time on the wrong subsystem before reading deep enough into the report to find the correct diagnosis.

### How the scoring system works (complete reference)

The Challenge Mode scorer is an LLM judge (Gemini 2.5 Flash) that evaluates the RCA agent's diagnosis against ground truth from the chaos scenario. The chaos platform injects faults to simulate real-world failures; the scorer evaluates against the **simulated failure mode** (what the failure looks like from the network), not the injection mechanism (how the platform created it).

#### Input to the scorer

The scorer receives:

1. **Simulated failure** — ground truth assembled from the scenario definition:
   - Scenario name and description
   - Per-fault observable descriptions (mapped from injection mechanism to network-observable effect via `_FAULT_TYPE_DESCRIPTIONS`)
   - Expected observable symptoms from the scenario definition
   - Component ontology layers (new — maps each target component to its ontology layer)
   - A note reminding the LLM judge that the agent cannot see the injection mechanism

2. **Agent diagnosis** — the raw diagnosis text produced by the RCA agent (the `_raw_diagnosis` field from the orchestrator)

3. **Agent network analysis** (new) — the agent's network analysis output containing the layer status table, suspect components, and investigation hints. This is needed for layer_accuracy scoring since the layer ratings live in the network analysis, not in the final diagnosis text.

#### Scoring dimensions

Each dimension evaluates a specific aspect of the agent's diagnostic ability:

**1. Root cause correct (40%)** — The most heavily weighted dimension. Did the agent identify the simulated failure mode as the root cause? Semantic equivalence counts — the agent doesn't need exact wording. If the platform killed a gNB to simulate a radio link failure, "RAN is unreachable" and "N2 connectivity loss" are both correct. The correct cause must be ranked as the primary candidate if multiple candidates are listed.

**2. Component overlap (20%)** — Did the agent name the right affected component(s)? Scored as a float 0.0–1.0. Score 1.0 if the primary affected component is named. The agent is not penalized for also listing cascading/downstream components — that shows correct causal reasoning (e.g., listing `icscf` as symptomatic alongside `pyhss` as root cause is fine).

**3. Severity correct (15%)** — Did the agent's severity assessment match the actual impact? A complete outage (container killed, network partitioned) should be described as "down"/"outage"/"unreachable". A degradation (packet loss, latency) should be "degraded"/"slow"/"impaired".

**4. Fault type identified (10%)** — Did the agent identify the observable class of failure? Scored on what can be observed from the network: component unreachable, network degradation, service partition, or service hang. The agent is not required to name the simulation mechanism.

**5. Layer accuracy (5%, new)** — Did the agent correctly attribute affected components to their ontology layers in the layer status assessment? Each component belongs to a specific layer per the network ontology. The scorer receives the ground truth layer mapping and the agent's network analysis output. Score True if the agent placed the affected component under its correct ontology layer, or if no layer status is available (no misattribution detectable). Score False if the agent attributed a component's failure to the wrong layer — the nature of a failure (e.g., network unreachability) does not determine the component's layer.

**6. Confidence calibrated (10%)** — Is the agent's stated confidence level appropriate? High confidence with a correct diagnosis backed by tool evidence is well calibrated. High confidence with a wrong diagnosis is poorly calibrated. Low confidence with a wrong diagnosis is actually well calibrated (the agent knows it doesn't know).

**7. Ranking position (tracked, not weighted)** — If the agent returned multiple ranked candidates, what position (1-based) is the correct cause? This is tracked for reporting but does not contribute to the total score.

#### Score computation

The total score is a weighted sum of the six scored dimensions:

```
total_score = 0.40 × root_cause_correct
            + 0.20 × component_overlap
            + 0.15 × severity_correct
            + 0.10 × fault_type_identified
            + 0.05 × layer_accuracy
            + 0.10 × confidence_calibrated
```

Boolean dimensions contribute their full weight when True and 0 when False. `component_overlap` is a continuous float 0.0–1.0.

The formula is encoded in the LLM scorer's system prompt (the LLM computes the score itself), but also verified server-side — if the LLM's response omits `total_score`, the scorer recomputes it from the individual dimensions.

#### Fallback behavior

If the LLM scorer fails (API error, malformed response), the scorer returns a zero-score dict with all dimensions set to False/0.0 and a summary indicating the failure. The pipeline never crashes due to a scorer error.

## Design

### Why 5% weight

Layer accuracy is important for operational correctness but secondary to diagnostic correctness. An agent that identifies the right root cause but misattributes the layer is significantly more useful than one that gets the layers right but diagnoses the wrong root cause. The 5% weight reflects this: it's enough to register in the score (a layer misattribution drops the score from 100% to 95%) and flag the issue for review, but it doesn't dominate the signal.

The 5% comes from `component_overlap` (25% → 20%) rather than from `root_cause_correct` (which stays at 40%) because component overlap and layer accuracy are related concerns — both evaluate the agent's understanding of which components are involved and where they sit in the architecture.

### Why the scorer needs the network analysis

The agent's layer status ratings live in the Phase 1 `NetworkAnalysis` output, not in the final Phase 6 `Diagnosis` output. The diagnosis contains root cause, timeline, affected components, and recommendation — but not the layer status table. If the scorer only saw the diagnosis text, it would have no material to evaluate layer accuracy against.

The `network_analysis` field was already captured in the `challenge_result` dict but not passed to the scorer. This change adds it as an optional parameter to `score_diagnosis()` and appends it as a separate section in the LLM judge's input.

### Component-to-layer mapping

The scorer includes a static `_COMPONENT_ONTOLOGY_LAYER` dict mapping container names to their ontology layers. This is derived from `network_ontology/data/components.yaml` and covers all components in the stack.

The alternative — loading components.yaml at runtime — was rejected because:
- It adds a YAML parsing dependency to the scorer
- The component-to-layer mapping changes rarely (it's defined by 3GPP standards)
- A static dict is simpler to test and reason about

If the ontology adds new components, the dict needs a corresponding update. This is acceptable given the low change frequency.

### Scoring semantics

The LLM judge evaluates layer accuracy with these rules:

- **True** if the agent's layer ratings place the primary affected component under its correct ontology layer (e.g., `pyhss` → ims layer rated RED).
- **True** if no layer status information is available in the diagnosis (can't detect misattribution without layer ratings).
- **False** if the agent attributed a component's failure to the wrong layer. The explicit instruction to the judge: *"The nature of the failure (e.g., network unreachability) does NOT determine the component's layer — a network-level failure of an IMS component is still an IMS-layer problem."*

This instruction directly addresses the failure mode observed in the triggering episode, where the LLM confused failure symptom (network-level) with component classification (ontology layer).

## Files Changed

**Modified files:**
- `agentic_chaos/scorer.py`:
  - Added `_COMPONENT_ONTOLOGY_LAYER` static dict mapping container names to ontology layers
  - Added `layer_accuracy` as dimension 5 in the scorer prompt with clear scoring rules
  - Updated weight formula: `component_overlap` 25%→20%, added `layer_accuracy` at 5%
  - Updated `score_diagnosis()` signature: new `network_analysis` optional parameter
  - Ground truth builder now includes component ontology layer info
  - User message now appends network analysis section when available
  - Updated `_call_scorer_llm` validation to include `layer_accuracy` in required bools
  - Updated `_fallback_score()` to include `layer_accuracy` and `layer_accuracy_rationale`

- `agentic_chaos/agents/challenger.py`:
  - Extracts `_network_analysis` from the diagnosis dict and passes it to `score_diagnosis()`
  - Challenge Mode log message now includes `layer_accuracy` in the breakdown

- `agentic_chaos/recorder.py`:
  - Scoring breakdown table in the markdown episode report now includes a `Layer accuracy` row

## Retroactive Impact

If this scorer had been in place for the triggering episode (`run_20260408_144319_hss_unresponsive`), the score would have dropped from 100% to 95%:

| Dimension | Weight | Result | Contribution |
|-----------|--------|--------|-------------|
| Root cause correct | 40% | True | 0.40 |
| Component overlap | 20% | 1.0 | 0.20 |
| Severity correct | 15% | True | 0.15 |
| Fault type identified | 10% | True | 0.10 |
| Layer accuracy | 5% | **False** | **0.00** |
| Confidence calibrated | 10% | True | 0.10 |
| **Total** | | | **0.95** |

The 5% deduction correctly signals that the agent's layer attribution was wrong without overpowering the dominant signal (the diagnosis was otherwise excellent).

## Alternatives Considered

1. **Higher weight (10-15%).** Rejected. Layer accuracy is a presentation/operational concern, not a diagnostic one. An agent that finds the right root cause but misattributes the layer is still highly useful. Over-weighting layer accuracy would cause scenarios where a correct diagnosis with a layer mistake scores lower than a wrong diagnosis with correct layers.

2. **Structured enforcement instead of scoring.** Considered for future work. The Network Analyst could be post-validated against the ontology before the report is finalized — if a layer rating references a component that doesn't belong to that layer, the system could auto-correct or flag it. This is complementary to scoring, not a replacement. Scoring catches the mistake after the fact; enforcement prevents it.

3. **Prompt-only fix in the Network Analyst.** Considered but insufficient alone. Adding explicit language to the analyst prompt (*"Rate each component under its ontology layer, NOT under the layer that matches the failure symptom"*) would help but cannot guarantee compliance — the same class of LLM reasoning error that caused the misattribution can ignore prompt instructions under context pressure. Scoring provides a measurable feedback signal that prompt changes alone cannot.

4. **Separate scorer pass for layer accuracy.** Rejected. A second LLM call to evaluate only layer accuracy would double the scoring cost for a 5% dimension. Including it in the existing scorer prompt is cheaper and keeps the evaluation holistic.

## Follow-ups

- **Prompt guardrails for the Network Analyst.** Add explicit language to `network_analyst.md` reinforcing that components must be rated under their ontology layer, not the layer matching the failure symptom. This is a complementary defense — prompt + scoring together are stronger than either alone.
- **Structured enforcement.** Post-validate the NetworkAnalysis output against `_COMPONENT_ONTOLOGY_LAYER` before the report is finalized. Auto-correct misattributions or flag them in the evidence validation phase.
- **Sync `_COMPONENT_ONTOLOGY_LAYER` with ontology.** If the ontology changes frequently, consider loading the mapping from `components.yaml` at import time instead of maintaining a static dict. Currently not worth the complexity given the low change rate.
