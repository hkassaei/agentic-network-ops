# ADR: Agentic Reasoning Capability — Gap Analysis

**Date:** 2026-04-17
**Status:** Proposed (for review)
**Related:**
- [`anomaly_model_feature_set.md`](anomaly_model_feature_set.md) — inventory of model features
- [`v5_6phase_pipeline.md`](v5_6phase_pipeline.md) — current agent pipeline
- [`falsifier_investigator_and_rag.md`](falsifier_investigator_and_rag.md) — Track 1/2 plan
- [`anomaly_training_zero_pollution.md`](anomaly_training_zero_pollution.md) — recent training-data fixes

---

## Purpose of this document

This is not a decision record for a specific change. It is a **capability gap analysis** for review. It inventories what the agent pipeline has today across metrics, ontology, tools, and liveness signals, then enumerates what is missing to support the stated goal: an agent that automatically detects serious network issues, performs root-cause analysis, computes blast radius and consequences, and proposes remediation — without a human in the loop except as final approver of action.

No implementation is proposed here. The gaps are ranked but the sequence of addressing them is left open for discussion.

---

## Context — the desired capability

The long-term goal is an agentic operations system that performs **80-90% of a NOC engineer's reasoning work**:

- **Detects** non-trivial issues from passively-reported telemetry (alarms, metrics, logs, traces), without continuous active probing of every link.
- **Roots out the cause** by combining observed state with knowledge of the network (how NFs relate, how procedures flow, which faults produce which signatures).
- **Assesses blast radius** — which services, flows, subscribers are affected; severity; duration.
- **Proposes remediation** — which actions resolve the issue, with tradeoffs.
- **Defers final action to a human** — the loop is not closed; all mutation is human-approved.

The reasoning needs to be *general*, not a lookup table of known failure scenarios. The agent must handle unseen combinations of faults, unfamiliar signatures, and ambiguous evidence.

---

## What we have today

### Model (29 features, retrained 2026-04-17)

River HalfSpaceTrees with per-feature mean/std attribution. Four semantic categories:
- **Rate metrics** — per-UE-normalized signaling throughput (REGISTER, INVITE, Diameter replies, GTP packets).
- **Response times** — Diameter round-trip latencies, P-CSCF register time.
- **Error ratios** — timeout ratios, SIP error ratios, registration rejection ratio.
- **Cross-layer activity** — UPF-activity-during-calls, dialogs-per-UE, bearers-per-UE, RTPEngine errors per second.

Produces: overall anomaly score + per-feature severity ranking with silent-failure escalation.

### Ontology (10 YAML files, 4264 lines)

- `components.yaml` — NF roles, layers, protocols, subsystems, use-case participation.
- `flows.yaml` (1216 lines) — end-to-end procedure flows, step by step.
- `causal_chains.yaml` (724 lines) — failure modes with `possible_causes` and `observable_symptoms`.
- `interfaces.yaml` — 3GPP interface definitions.
- `healthchecks.yaml` — per-component probes (ordered cheapest → most expensive), with `disambiguates` field.
- `baselines.yaml` — expected healthy values (see separate note below re: scale-dependence).
- `symptom_signatures.yaml` — pre-computed signature matches (`match_all` / `match_any` / `rule_out`).
- `log_patterns.yaml` — log message interpretation.
- `stack_rules.yaml` — cross-component invariants.

### Tools available to agents

`measure_rtt`, `check_process_listeners`, `query_prometheus`, `get_nf_metrics`, `get_dp_quality_gauges`, `get_network_status`, `read_container_logs`, `search_logs`, `run_kamcmd`, `read_running_config`, `read_env_config`, `query_subscriber`, `check_component_health`, `match_symptoms`, `compare_to_baseline`, `get_causal_chain`, `get_causal_chain_for_component`, `get_network_topology`, `get_vonr_components`.

### Liveness signals

Per-feature liveness in the preprocessor (did the underlying counter advance recently?), consumed by the screener's silent-failure escalation. Not yet consolidated or exposed to the downstream reasoner as a standalone "who is up/down" snapshot.

### Episodes

~100 JSON+MD episode files in `agentic_ops_v5/docs/agent_logs/` with ground truth, diagnoses, and token traces. ~30 have post-run analyses in `docs/critical-observations/`. Currently static — not retrievable at runtime.

---

## The nine gaps

Ranked by estimated leverage. Each gap includes what is missing, what partially covers it today, and why it matters.

### Gap 1 — Temporal reasoning

**What is missing:** The model is snapshot-based. Reasoning about faults needs onset time ("when did this start"), trend direction ("rising, stable, or dropping"), and persistence ("for how long"). None of these are currently surfaced to the reasoning layer.

**Partial coverage today:** Prometheus stores 5-second-resolution time-series with adequate retention. `query_prometheus` lets agents run `rate()`, `delta()`, `offset`, `predict_linear()`. But the agent prompts rarely direct the agent to use these; most `query_prometheus` calls are for current values only. The anomaly screener processes multiple snapshots but picks the single best-scoring one — temporal context is lost at the output boundary.

**Impact if left unaddressed:** The agent cannot distinguish transient spikes from sustained degradation, cannot establish event timelines for the NOC narrative, and cannot detect slow-onset faults (e.g., MongoDB cache exhaustion).

---

### Gap 2 — Bidirectional causal inference

**What is missing:** The ontology's causal chains map `cause → observable_symptoms`. Reasoning needs the inverse: given a noisy, possibly partial observation set, rank candidate causes by how well each *explains the observed pattern AND is consistent with the absent observations*.

**Partial coverage today:** `symptom_signatures.yaml` attempts this with pre-computed `match_all` / `match_any` / `rule_out` signatures. This works for known patterns but is rigid — it does not reason about *why* a symptom pattern is consistent with a cause, or handle partial matches gracefully.

**Impact if left unaddressed:** The agent falls back to pattern-match-or-fail behavior. Novel combinations of faults produce "no match found" outcomes. The screener's severity ranking (which inverts causality in cascade failures — see the IMS partition cases where P-CSCF is the cause but UPF shows higher severity) is taken at face value.

---

### Gap 3 — Per-metric semantic interpretation

**What is missing:** The ontology describes *NFs* and *flows* thoroughly, and baselines give expected *values*, but there is no structured "what does a change in this metric SPECIFICALLY MEAN about this NF's responsibility in this moment?" layer. The agent currently relies on the LLM's own domain knowledge to interpret metric semantics — reliable for common metrics, thin for edge cases and deployment-specific quirks (e.g., the pcscf `httpclient:connfail` pre-existing 84% failure noise).

**Partial coverage today:** `baselines.yaml` descriptions are good for NOC operational documentation but inconsistent: some metrics have rich alarm-conditions and notes; others are one-liners. The descriptions are narrative prose, not structured-reasoning input.

**Impact if left unaddressed:** Agent diagnosis quality varies by the LLM's prior familiarity with each metric. Misinterpretations of specific metrics (e.g., treating the derived `pcscf_avg_register_time_ms` as a Diameter latency rather than a composite of UAR+MAR+SAR+SIP-forwarding time) are hard to prevent without explicit semantic scaffolding.

---

### Gap 4 — Consolidated liveness snapshot at event time

**What is missing:** A unified "who is up / down / partitioned / slow" view generated at (or reconstructed for) the observation window. Currently this exists only as scattered evidence: preprocessor liveness flags, `get_network_status` output, `check_process_listeners` returns, interface probe results.

**Partial coverage today:** Each tool returns its own slice. The agent must assemble the composite itself, often inconsistently across runs.

**Impact if left unaddressed:** The reasoner re-derives liveness from scratch per episode. The temporal alignment problem (what was the state AT the event time, not now) compounds Gap 1. Hypotheses that depend on liveness context (e.g., "silent upstream means partition OR crash, disambiguate via container state") require multiple separate tool calls.

---

### Gap 5 — Blast radius / service impact model

**What is missing:** A dependency graph that answers: "if `<component>` is degraded, which *flows* are affected → which *services* → which *subscribers/use cases* → what *SLA impact*."

**Partial coverage today:** The raw materials are in the ontology. `components.yaml` lists use-case participation per NF. `flows.yaml` maps NFs to procedure steps. But the projection — "component X → impacted flows → impacted services → affected subscribers" — is not computed or queryable.

**Impact if left unaddressed:** The agent cannot tell the NOC engineer "this outage affects 100% of VoNR registrations, 0% of data-only PDU sessions" or "this is a 30-subscriber blast radius." The output remains at the technical level (which NF broke) without translating to the business / user impact level (what's actually affected). This is one of the stated deliverables that we cannot produce today.

---

### Gap 6 — Remediation knowledge base

**What is missing:** Per-failure-mode, a catalog of candidate actions with prerequisites, expected outcome, reversibility, blast radius of the action itself, and success criteria.

**Partial coverage today:** Nothing. System prompts currently forbid proposing actions (observation-only constraint). This is a deliberate boundary — trust level insufficient — but the stated end-goal is proposing remediation for human approval.

**Impact if left unaddressed:** The agent stops at diagnosis. The NOC engineer still has to look up remediation. The "80-90% of NOC work" target cannot be met without action proposal capability.

---

### Gap 7 — Hypothesis-space working memory

**What is missing:** The reasoner should maintain a set of *competing hypotheses* with evidence weights, plus *discriminating probes* — then converge via probes. Today the chain-of-thought is implicit in the LLM's reasoning; hypotheses are not externalized or tracked across phases.

**Partial coverage today:** The NA produces a flat `suspect_components` list. The Investigator (when it runs) is told to falsify the top suspect, not maintain a hypothesis set. Track 1's falsifier design is a step in this direction but not a full working-memory model.

**Impact if left unaddressed:** The agent cannot explain "I considered hypotheses A, B, C; A is eliminated by observation X; B and C both consistent; the probe that discriminates them is Y." This is exactly the reasoning transparency the NOC engineer needs to trust the conclusion.

---

### Gap 8 — Reasoning orchestration over the ontology

**What is missing:** A structured workflow that the NA follows: *observe → consult causal chains for candidate causes → intersect with liveness → rank hypotheses by evidence fit → pick discriminating healthcheck → probe → narrow → repeat until converged*. All the pieces exist; the conductor does not.

**Partial coverage today:** The NA has ontology tools available and sometimes calls them, but the prompt does not structure their use. The Investigator (pre-Track-1) was expected to do this but failed to run tools consistently.

**Impact if left unaddressed:** Inconsistent use of the domain knowledge we already have. The ontology's investment is under-realized because the agent doesn't systematically consult it.

---

### Gap 9 — Episode RAG (planned Track 2)

**What is missing:** Historical similarity retrieval. Given the current anomaly signature, retrieve past episodes with similar signatures and their ground-truth diagnoses (and post-run-analysis traps).

**Partial coverage today:** Nothing. Episodes are static files; the agent has no memory across runs.

**Impact if left unaddressed:** Every run starts cold. Patterns the NOC engineer would recognize ("I've seen this — it's always the tc netem rule that didn't get cleaned up") are re-discovered or missed each time.

**Note:** [`falsifier_investigator_and_rag.md`](falsifier_investigator_and_rag.md) captures the Track 2 plan with two retrievers (analogs + known traps).

---

## Categorization

The nine gaps fall into three classes:

### Class A — Reasoning engine (gaps 1, 2, 4, 7, 8)

These describe a reasoning component that **consumes the material we already have** (ontology + metrics + tools) and produces structured hypotheses with temporal context, liveness integration, and hypothesis-space tracking.

The data and tools exist. The conductor does not. This is where the biggest leverage sits, because no new content authoring is required — just better orchestration and externalized reasoning state.

### Class B — Missing domain content (gaps 3, 5, 6)

These are content-authoring tasks that extend the ontology:
- Per-metric semantic interpretation (gap 3)
- Service-impact / blast-radius model (gap 5)
- Remediation catalog (gap 6)

Mostly YAML + structured prose. The cost is review effort and domain correctness, not engineering.

### Class C — Memory infrastructure (gap 9)

Historical retrieval. Plumbing work, already scoped in the Track 2 ADR.

---

## Suggested sequence — for discussion, not decision

The worst order is to author more domain content before the reasoning engine that will consume it is designed, because the reasoner's needs will shape the content structure. The second worst is to build the reasoning engine without deciding what output format (blast radius / consequences / remediation) the user consumes, because the output shape dictates what the reasoner must compute.

A less-bad order:

1. **First design the output format** the NOC engineer will see. This drives everything else. It determines whether we need blast-radius computation (yes if the user output includes it), remediation proposal (yes if the user output includes it), and how structured the hypothesis space needs to be.
2. **Then design the reasoning engine** (Class A) with that output in mind — enumerate what inputs it needs, what intermediate representations it maintains, what ontology queries it performs.
3. **Then author the content** (Class B) in the shape the engine needs.
4. **In parallel**, progress Class C (episode RAG) since it is structurally independent.

The existing Track 1 falsifier work plus the mechanical guardrail should be treated as scaffolding that can coexist with whatever reasoning-engine work we start. Track 1 is a partial answer to gap 7 and 8; we do not need to tear it out.

---

## Out of scope for this ADR

- Implementation of any gap.
- Specific design of the reasoning engine (Class A).
- Schema for a service-impact model (Class B).
- Integration of remediation actions into the closed-loop (Class B + permission model; this is explicitly human-gated regardless).

---

## Open questions for review

1. **Output format first:** what do we want the agent's final output to look like? This is the most decision-shaping question. Options range from "flat diagnosis" (today's output) through "structured incident report with hypotheses, blast radius, and recommended actions" to "machine-readable action plan for a closed-loop system."
2. **Reasoning engine shape:** prompt-orchestrated LLM (current approach, extended) vs. structured planner (external component that drives the LLM as a skill)? The former is cheaper; the latter is more predictable and testable.
3. **Where does blast radius compute:** statically in the ontology (precomputed per-component impact projection) or dynamically at diagnosis time (agent-driven query using `components.yaml` + `flows.yaml`)? Affects gap 5 content authoring scope.
4. **Remediation trust level:** should the catalog be consulted only at diagnosis time (agent reads it, proposes actions, human executes) or could a subset be marked "pre-approved, agent may execute" down the line? This shapes gap 6's content model.
5. **Ontology consolidation:** `baselines.yaml` and `anomaly_model_feature_set.md` overlap but don't align. See related note in the conversation about making baselines.yaml scale-independent and clarifying the authoritative source. Worth its own follow-up ADR.
