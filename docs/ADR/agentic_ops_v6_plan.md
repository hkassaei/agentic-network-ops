# ADR: agentic_ops_v6 — Plan

**Date:** 2026-04-19
**Status:** Accepted (open questions resolved 2026-04-19)
**Related:**
- [`agentic_reasoning_capability_gaps.md`](agentic_reasoning_capability_gaps.md) — the gap analysis that motivates v6
- [`metric_knowledge_base_schema.md`](metric_knowledge_base_schema.md) — metric KB schema
- [`alarm_correlation_engine.md`](alarm_correlation_engine.md) — correlation engine (stub)
- [`agentic_ops_v5_plan.md`](agentic_ops_v5_plan.md) — v5 plan (v6 supersedes)
- [`v5_6phase_pipeline.md`](v5_6phase_pipeline.md) — v5 pipeline (v6 replaces)
- [`falsifier_investigator_and_rag.md`](falsifier_investigator_and_rag.md) — Track 1 (falsifier) carried forward, parallelized per hypothesis in v6

---

## Why a new major version

v6 is not an incremental change to v5. It is a restructuring of the reasoning architecture driven by the capability gap analysis, specifically:

- **New reasoning substrate:** the Network Analyst reasons over structured *events* (from the metric KB) and *correlated hypotheses* (from the correlation engine), not over raw anomaly-screener output.
- **Parallel per-hypothesis falsification:** the Investigator is no longer a single agent that sees all hypotheses at once. Instead, the orchestrator spawns one Investigator sub-agent per hypothesis. Each sub-agent has a focused contract: probe to disprove one specific hypothesis, report a verdict. This addresses both the limited-context failure mode of the current single Investigator and the 0-tool-call problem (smaller, more concrete prompts are harder to respond to with fabricated output).
- **New infrastructure:** metric knowledge base with simpleeval-backed trigger evaluation, Kamailio Prometheus exporter for temporal queries on IMS metrics, SQLite event store, correlation engine consuming fired events.
- **Clean dependency boundary:** v6 does not import from v5. Shared code (anomaly subsystem, low-level tools, trace models) moves to a new `agentic_ops_common/` package. v5 remains runnable for regression comparison during and after v6 development.

---

## High-level architecture

### Agent pipeline (replaces v5's 6-phase pipeline)

```
Phase 0  AnomalyScreener          (as v5; unchanged)
Phase 1  EventAggregator          NEW — reads already-fired events from the event store
                                  for the observation window. The agentic ops pipeline
                                  is a CONSUMER of events, not a producer — the chaos
                                  framework is responsible for invoking the trigger
                                  evaluator at fault injection, during traffic generation,
                                  and throughout the observation window. See "Trigger
                                  evaluator invocation model" below.
Phase 2  NetworkAnalyst           UPDATED — reasons over events + KB semantics + correlation
Phase 3  CorrelationAnalyzer      NEW — produces composite hypotheses from events
Phase 4  InstructionGenerator     UPDATED — produces N per-hypothesis falsification plans
Phase 5  Investigator × N         UPDATED — parallel sub-agents, one per hypothesis
Phase 6  EvidenceValidator        UPDATED — validates each sub-investigator's citations
Phase 7  Synthesis                UPDATED — aggregates N per-hypothesis verdicts
```

Phases 1-5 are the novel architecture. Phase 0 and 6 are carried forward with minor adaptations.

### Trigger evaluator invocation model

The trigger evaluator (simpleeval + `MetricContext` + predicates) is **agent-driven, not a daemon, and invoked by the agentic chaos framework — not by the agentic ops pipeline.**

The agentic chaos framework invokes the evaluator at the following moments during an episode:

1. **Baseline phase** — before fault injection, over a pre-fault window. Captures "normal" events (typically none; events should be quiet during baseline).
2. **At fault injection** — evaluates over the window straddling the injection moment. Captures the immediate-onset events (sudden drops, first-latency-spikes).
3. **During observation-traffic generation** — each metric-collection tick, the evaluator runs over a rolling window. Captures sustained events and clear-condition transitions.
4. **At end of observation** — a final pass over the full observation window to catch anything missed.

Fired events write to the SQLite event store with:
- `event_type` (namespaced id)
- `timestamp` (first observed)
- `source_metric`, `source_nf`
- `magnitude_payload_json` (values captured per the KB's `magnitude_captured` list)
- `episode_id` (ties events to a chaos episode for query scope)
- `cleared_at` (set when the clear_condition evaluates true in a subsequent pass)

When the chaos framework invokes the agentic ops orchestrator (Phase 0 → 7), the pipeline **reads** events from the store for the current episode's observation window. It does not invoke the evaluator itself. This keeps the pipeline's job pure — consume events, reason over them — and avoids the pipeline needing to know about trigger evaluation implementation details.

**Why chaos-framework-driven over daemon:** in this testing environment, scenarios are discrete episodes with known phase boundaries (baseline, inject, observe, heal). The chaos framework already knows when each phase starts and ends. Having it drive evaluation keeps the event timeline tightly correlated with the fault lifecycle. A continuous daemon would evaluate constantly regardless of scenario phase, which adds noise and doesn't improve signal fidelity. If v6 ever deploys against a continuously-monitored production stack, the evaluator can be wrapped in a daemon loop without changing its internals.

### Parallel per-hypothesis Investigator architecture

**Before (v5):**

```
NA: produces list of hypotheses H1, H2, H3
      │
      ▼
IG: produces ONE falsification plan covering all three
      │
      ▼
Investigator: receives plan + all hypotheses, tries to falsify NA's primary suspect
      │
      ▼
Synthesis: consumes one verdict
```

**v6:**

```
NA: produces ranked hypotheses H1, H2, H3 with evidence and reasoning
      │
      ▼
IG: iterates — produces FP1, FP2, FP3 (one focused falsification plan per hypothesis)
      │
      ▼
Orchestrator: spawns 3 sub-agents in parallel
      │
      ├─▶ Investigator(H1, FP1) → verdict_1
      ├─▶ Investigator(H2, FP2) → verdict_2
      └─▶ Investigator(H3, FP3) → verdict_3
             │
             ▼
Synthesis: aggregates N verdicts into final diagnosis
```

Each sub-Investigator's prompt contains only its assigned hypothesis and the focused plan for that hypothesis. Smaller context, clearer contract, falsify-or-fail semantics. A sub-Investigator emits one of three verdicts:

- `DISPROVEN` — at least one probe produced evidence inconsistent with the hypothesis.
- `NOT_DISPROVEN` — all probes ran, none produced disconfirming evidence. Hypothesis survives.
- `INCONCLUSIVE` — probes ran but evidence is ambiguous (or minimum-probe-count guardrail fired).

Synthesis combines verdicts:

- **Exactly one `NOT_DISPROVEN` + all others `DISPROVEN`** → high-confidence root cause.
- **Multiple `NOT_DISPROVEN`** → hypotheses are not mutually exclusive (cascade) or evidence insufficient. Synthesis surfaces all survivors with their evidence for NOC review.
- **All `DISPROVEN`** → NA's hypothesis set was wrong; manual investigation required.
- **Any `INCONCLUSIVE`** → caps confidence at medium.

### Hypothesis cap and ranking rule

Orchestrator enforces `MAX_PARALLEL_INVESTIGATORS = 3` (configurable). If the NA produces more than 3 hypotheses, only the top 3 (by NA's ranking) are investigated.

**Ranking rule (enforced in the NA prompt and in the structured hypothesis schema):**

1. **Primary — explanatory fit.** How well does the hypothesis explain the observed events, metric anomalies, and liveness signals? Hypotheses that account for MORE of the observations rank higher. The NA inherits the correlation engine's fit ranking by default when consuming its output; it may adjust based on additional observations it surfaced itself.

2. **Secondary — testability.** Does the hypothesis have KB `disambiguators` or specific probes that could falsify it? A hypothesis with 2-3 clear discriminating probes is a much better Investigator target than one where falsification would require a broad hunt. **Hypotheses without any identifiable falsification probe are DROPPED, not ranked low.** An untested slot is wasted; an untestable hypothesis produces no useful verdict.

3. **Tertiary — specificity.** Prefer specific-mechanism hypotheses ("HSS backend is slow due to Mongo cache exhaustion") over vague ones ("something is wrong in the HSS path"). Specific hypotheses produce actionable diagnoses and map cleanly to probes.

The structured hypothesis schema the NA produces includes:

```python
class Hypothesis:
    id: str
    statement: str                  # specific-mechanism claim
    explanatory_fit: float          # 0-1, from correlation engine or NA's own estimate
    supporting_events: list[str]    # event_ids this hypothesis explains
    falsification_probes: list[str] # >=1 required; drop if empty
    specificity: Literal["specific", "moderate", "vague"]
```

Ranker = sort by `(explanatory_fit DESC, len(falsification_probes) DESC, specificity preference)`. Drop hypotheses with `len(falsification_probes) == 0`. Take top 3.

### Per-hypothesis minimum probes (guardrail)

The mechanical minimum-tool-call guardrail from v5 is retained per sub-Investigator. If any sub-agent produces < 2 tool calls, its verdict is forced to `INCONCLUSIVE` at the orchestrator layer.

---

## Directory structure

```
agentic_ops_v6/                        # v6 package, mirrors v5 structure
  __init__.py
  __main__.py                          # CLI entry
  orchestrator.py                      # NEW — parallel per-hypothesis orchestration
  models.py                            # v6-specific models; imports shared from common
  prompts/
    network_analyst.md                 # UPDATED — KB-aware, event-aware
    correlation_analyzer.md            # NEW — multi-event reasoning
    instruction_generator.md           # UPDATED — generates N per-hypothesis plans
    investigator.md                    # UPDATED — single-hypothesis focus
    synthesis.md                       # UPDATED — multi-verdict aggregation
    ontology_consultation.md           # carried forward
  subagents/
    __init__.py
    network_analyst.py
    correlation_analyzer.py            # NEW
    instruction_generator.py           # UPDATED — returns list[HypothesisPlan]
    investigator.py                    # UPDATED — parameterized by hypothesis_id
    evidence_validator.py
    synthesis.py
    ontology_consultation.py
  docs/
    agent_logs/                        # v6 episode outputs land here
  tests/
    __init__.py
    test_orchestrator.py
    test_instruction_generator.py
    test_investigator.py
    test_synthesis.py
    test_correlation_analyzer.py
```

```
agentic_ops_common/                    # NEW — shared across v5, v6, and future versions
  __init__.py
  anomaly/                             # moved from agentic_ops_v5/anomaly/
    __init__.py
    preprocessor.py
    screener.py
    baseline/
      model.pkl
  tools/                               # moved from agentic_ops_v5/tools/
    __init__.py
    _common.py
    causal_reasoning.py
    config_inspection.py
    container_status.py
    data_plane.py
    health_checks.py
    kamailio_state.py
    log_interpretation.py
    log_search.py
    metrics.py
    reachability.py
    subscriber_lookup.py
    symptom_matching.py
    topology.py
    vonr_scope.py
  models/                              # shared trace models (InvestigationTrace, PhaseTrace, ToolCallTrace)
    __init__.py
    trace.py
  metric_kb/                           # NEW — metric knowledge base infrastructure
    __init__.py
    loader.py                          # pydantic + YAML
    models.py                          # pydantic schema classes
    event_dsl.py                       # simpleeval + predicates
    metric_context.py                  # MetricContext + Prometheus/ring-buffer backends
    event_store.py                     # SQLite event store
    schema/
      metrics.schema.json              # auto-generated JSON Schema for IDE
  correlation/                         # NEW — correlation engine
    __init__.py
    engine.py
    rules.py                           # correlation rules from KB + ontology
    operational_context.py             # stub for change windows etc.
```

```
network_ontology/                      # unchanged location
  data/
    metrics.yaml                       # NEW — the metric KB content
    components.yaml
    flows.yaml
    causal_chains.yaml
    interfaces.yaml
    healthchecks.yaml
    baselines.yaml                     # retained during migration; deprecated after cutover
    symptom_signatures.yaml
    log_patterns.yaml
    stack_rules.yaml
```

```
anomaly_trainer/                       # unchanged location; imports from agentic_ops_common
  __init__.py
  __main__.py
  collector.py
  persistence.py
  traffic.py
```

### Dependency rules

- `agentic_ops_v6/*` imports from `agentic_ops_common/*` and `network_ontology/*`.
- `agentic_ops_v6/*` does NOT import from `agentic_ops_v5/*`.
- `agentic_ops_common/*` does not import from any `agentic_ops_v{n}/*`.
- `anomaly_trainer/*` imports from `agentic_ops_common/*` (not from v5 or v6).
- `agentic_ops_v5/*` is frozen — it continues to work by importing the shared code from `agentic_ops_common/*` after refactor. No feature work on v5.

---

## Dependency refactor plan

Three things need to move from `agentic_ops_v5/` to `agentic_ops_common/`:

### 1. Anomaly subsystem
- `agentic_ops_v5/anomaly/preprocessor.py` → `agentic_ops_common/anomaly/preprocessor.py`
- `agentic_ops_v5/anomaly/screener.py` → `agentic_ops_common/anomaly/screener.py`
- `agentic_ops_v5/anomaly/baseline/` → `agentic_ops_common/anomaly/baseline/`

Update imports in:
- `agentic_ops_v5/orchestrator.py`
- `anomaly_trainer/collector.py`
- `anomaly_trainer/persistence.py`
- `anomaly_trainer/__main__.py`
- `check_anomaly_baseline_model.py`

### 2. Low-level tools
- All of `agentic_ops_v5/tools/*.py` → `agentic_ops_common/tools/*.py`

These are mostly thin wrappers around external systems (Prometheus, kamcmd, Docker, etc.) and don't have agent-version-specific logic. Moving them to common is clean.

Update imports in:
- `agentic_ops_v5/subagents/*.py`
- `agentic_ops_v5/orchestrator.py`

### 3. Trace models
- `InvestigationTrace`, `PhaseTrace`, `ToolCallTrace` from `agentic_ops_v5/models.py` → `agentic_ops_common/models/trace.py`

v5 keeps a thin `models.py` that re-exports from common plus any v5-only state it defines. v6 imports directly from common.

### Subagent code NOT shared

Subagents are intentionally version-specific. v5's network_analyst.py, investigator.py, etc. stay in v5; v6 writes its own. This preserves the "no dependency on prior versions" rule — v6's agent code evolves independently from v5's.

### Refactor sequence

1. Create `agentic_ops_common/` with empty `__init__.py`.
2. Move files with `git mv` to preserve history.
3. Update imports in the five callers listed above.
4. Run v5 orchestrator end-to-end to confirm no regressions.
5. Only then begin v6 implementation.

---

## Phased implementation plan

### Phase 0 — Common refactor (prerequisite)

Refactor shared code to `agentic_ops_common/`. No v6 work starts until v5 still passes.

**Acceptance:** v5 orchestrator runs a chaos scenario end-to-end with the same output shape as before the refactor.

### Phase 1 — Metric KB infrastructure + content

1. **Kamailio Prometheus exporter.** Deploy `kamailio-mod-prometheus` (or equivalent) so every KB metric has Prometheus history. Blocks temporal predicates otherwise.
2. **Metric KB infrastructure:**
   - `agentic_ops_common/metric_kb/loader.py` (pydantic + YAML)
   - `agentic_ops_common/metric_kb/event_dsl.py` (simpleeval + predicates)
   - `agentic_ops_common/metric_kb/metric_context.py` (Prometheus + ring buffer backends)
   - `agentic_ops_common/metric_kb/event_store.py` (SQLite)
   - `agentic_ops_common/metric_kb/evaluator.py` — the callable trigger evaluator (NOT a daemon). Exposes a function like `evaluate(episode_id, window_start, window_end, metrics=None) -> list[FiredEvent]`.
3. **Chaos framework integration.** Extend `agentic_chaos/` to invoke the evaluator at the four phase points described in "Trigger evaluator invocation model":
   - Baseline collection
   - Fault injection moment
   - Each observation-traffic tick
   - End of observation
   Each invocation passes the current episode ID so fired events are correctly scoped. No changes to the agentic ops pipeline — it reads the store.
4. **KB content.** Author `network_ontology/data/metrics.yaml` for the ~20-25 metrics that cover the 11 chaos scenarios. Populated fields: `meaning`, `disambiguators`, `related_metrics`, `event_triggers`, `how_to_verify_live`, `healthy.invariant`.

**Acceptance:** a chaos scenario runs; the chaos framework invokes the evaluator at phase boundaries; expected events land in SQLite with correct episode_id scoping; a query tool can retrieve events for a given episode/NF/window.

### Phase 2 — Correlation engine (minimum viable)

1. `agentic_ops_common/correlation/engine.py` — reads recent events, applies KB `correlates_with` hints and ontology causal chains, outputs ranked hypotheses with supporting events.
2. `agentic_ops_common/correlation/rules.py` — rule loader (bootstrapping from KB hints; extensible).
3. Does NOT yet handle operational-context suppression (deferred to Phase 5).

**Acceptance:** given a synthetic event stream (e.g., `core.amf.ran_ue_sudden_drop` + `infrastructure.mongo.subscribers_decrease`), the engine produces the expected composite hypothesis ("planned offboarding — benign").

### Phase 3 — v6 agent pipeline

1. `agentic_ops_v6/orchestrator.py` — new 8-phase orchestrator. Spawns N parallel Investigators.
2. `agentic_ops_v6/subagents/network_analyst.py` + prompt — reasons over events + KB semantics + correlation output.
3. `agentic_ops_v6/subagents/correlation_analyzer.py` + prompt — thin wrapper over the Phase-2 engine for LLM consumption.
4. `agentic_ops_v6/subagents/instruction_generator.py` + prompt — produces list of per-hypothesis falsification plans, one per hypothesis.
5. `agentic_ops_v6/subagents/investigator.py` + prompt — parameterized by hypothesis_id + single focused plan. Returns `DISPROVEN`/`NOT_DISPROVEN`/`INCONCLUSIVE` verdict.
6. `agentic_ops_v6/subagents/synthesis.py` + prompt — aggregates N verdicts.
7. Minimum-probe guardrail preserved and applied per sub-Investigator.

**Acceptance:** run all 11 chaos scenarios, measure scores against v5 baseline. Target: 80%+ average, no scenario below 50%, partition scenarios above 70%.

### Phase 4 — Retire `baselines.yaml`, consolidate on `metrics.yaml`

Triggered after Phase 3 acceptance. Phase 1 authored `metrics.yaml` covering the 27 metrics the 11 chaos scenarios exercise. `baselines.yaml` still holds entries for ~77 metrics (many overlapping in concept but not in the structured KB schema) and is actively consumed by:

- `network_ontology/loader.py` — loads baselines into Neo4j as properties on Component/Metric nodes.
- `network_ontology/query.py::get_baseline()` + `compare_to_baseline()` — ontology tools the v5 NetworkAnalyst uses every run.
- `gui/server.py::/api/metric-descriptions` — serves tooltips from baselines.yaml to the GUI.
- v5's NetworkAnalyst prompt instructs explicit use of `compare_to_baseline`.

Coexistence is safe during Phases 1–3 (different lookup paths, no conflict). After Phase 3, consolidate.

1. **Expand KB content.** Author the remaining ~50 metrics from baselines.yaml into `metrics.yaml` with the same semantic depth as Phase 1 entries (meaning, invariants, disambiguators, related_metrics). Mostly AMF/SMF/PCF counters, P/I/S-CSCF raw kamailio counters, RTPEngine rich gauges, pyhss/mongo subscriber counts.
2. **Migrate ontology tools.** `network_ontology/query.py::compare_to_baseline()` and `get_baseline()` read from `metrics.yaml` via the KB loader instead of the Neo4j-backed baselines properties.
3. **Migrate GUI tooltips.** `gui/server.py::/api/metric-descriptions` reads `meaning.what_it_signals` + `description` from the KB loader.
4. **Remove baselines loader path.** Drop the `_load_yaml("baselines.yaml")` call in `network_ontology/loader.py`. Neo4j no longer carries baseline properties.
5. **Delete `baselines.yaml`.** Single commit after consumers verify green against the KB-backed paths.
6. **Update v5 prompts (documentation-only).** v5 is frozen so behavior doesn't change, but cross-references in v5's NetworkAnalyst prompt referencing baselines.yaml by name are updated to metrics.yaml for consistency. v5 is a regression-only baseline at this point.

**Acceptance:**
- `metrics.yaml` covers every metric previously in `baselines.yaml`.
- v5 still runs end-to-end with `compare_to_baseline` backed by the KB.
- GUI tooltips render identically.
- `baselines.yaml` is deleted.
- All tests green.

**Why after Phase 3, not before:** Phase 3 is the path to the chaos-score deliverable. Retirement work doesn't improve scores and touches consumers v5 still depends on for regression comparison. Keeping it as a cleanup phase avoids conflating the two.

### Phase 5 — Operational context + suppression (stub implementation)

In production telecom ops, operational context comes from external systems (ServiceNow change management, BSS/OSS subscriber-lifecycle platforms, deployment automation, ITSM ticketing). Our test environment has none of these. Phase 5 defines the *interface* for operational context and provides a *stub implementation* driven by chaos-scenario metadata.

1. **Scenario metadata as operational context.** Extend `agentic_chaos/scenarios/library.py` to allow each scenario to declare context tags:

   ```python
   ScenarioSpec(
       name="AMF Restart (Upgrade Simulation)",
       operational_context={
           "upgrade_window": True,
           "affected_component": "amf",
           "expected_symptoms": ["core.amf.ran_ue_sudden_drop", "core.amf.process_restart"],
           "suppression_rationale": "Planned AMF upgrade — transient drops expected",
       },
       ...
   )
   ```

2. **Context provider interface in `agentic_ops_common/correlation/operational_context.py`.** A provider returns context for a given episode_id. Stub implementation reads the scenario's metadata. Interface is ready for future real providers (ServiceNow adapter, etc.).

3. **Correlation engine suppression rules.** Engine consumes operational context. When an episode has `upgrade_window: True` on a specific component, correlated events on that component's `expected_symptoms` list are tagged "suppressed_by_change_window" rather than escalated as alarms.

4. **Blast radius projection** using ontology `flows.yaml` + `components.yaml` — "given this component is degraded, which flows traverse it, which services depend on those flows."

**Acceptance:** a chaos scenario explicitly tagged as "AMF upgrade window" produces events that the correlation engine recognizes as expected-during-upgrade and suppresses. A scenario NOT tagged produces events that escalate normally.

**Priority note:** Phase 5 is lower priority than Phase 3 for the chaos-score goal. Our current 11 scenarios do not include planned-maintenance variants; we don't need suppression to score 100% on them. Phase 5 becomes relevant when the chaos library expands to include planned-activity variants (a separate chaos-framework ADR).

### Phase 6 — Episode RAG (Track 2)

1. Index past episodes (ground truth + post-run analyses).
2. Retrieval inputs to correlation engine: "past episodes with similar event signatures had these actual root causes."

**Acceptance:** a partition scenario's correlation output cites a past partition episode as a supporting analog.

---

## What carries forward from v5

- **Anomaly model and its training pipeline.** Moves to common; behavior unchanged.
- **Pattern matcher.** v6 does not include it by default — the correlation engine covers its role more richly. Can be revisited.
- **Evidence validator.** Simplified for v6 — validates per sub-Investigator independently.
- **Mechanical minimum-probe guardrail.** Preserved and applied per sub-Investigator.
- **Observation-only constraint.** Retained for all v6 agents until a separate ADR authorizes remediation proposals.

## What does NOT carry forward from v5

- **Single-Investigator falsifier path.** Replaced by parallel per-hypothesis Investigators.
- **Flat suspect-list output from NA.** Replaced by ranked hypothesis list with evidence and explicit discriminating probes.
- **Pattern matcher as a pipeline phase.** Deferred or dropped.

---

## Versioning and coexistence

- **v5 is FROZEN as of v6 development start.** No new feature work or bug fixes on v5 — all development moves to v6. The only exception is the Phase 0 refactor, which modifies v5's imports to reference `agentic_ops_common/` instead of `agentic_ops_v5/anomaly/` and `agentic_ops_v5/tools/`. After Phase 0, v5 is archived in-place.
- v5 remains runnable from the repo for regression comparison only. The chaos framework's `--agent v5` argument continues to work; outputs land under `agentic_ops_v5/docs/agent_logs/`.
- v6 is invoked with `--agent v6` (requires a small chaos-framework update to register it).
- Episode outputs are stored under each version's `docs/agent_logs/` directory; no cross-contamination.
- No runtime coupling: running v5 and v6 against the same stack simultaneously is safe (they share Prometheus read access, don't mutate stack state).
- If a v5-specific bug is discovered during v6 development, it is documented but not fixed. v5 is a regression baseline, not a maintained agent.

---

## The 0-tool-call problem

The parallel-hypothesis architecture is an **indirect fix** for this problem:

- Each sub-Investigator receives a short, focused prompt (one hypothesis + 2-3 probes) instead of the full falsification scope.
- Smaller context, clearer contract, higher probability the LLM actually invokes tools rather than fabricating output.
- The minimum-probe guardrail catches any sub-Investigator that still fails to probe.
- Even if one sub-Investigator silently fails, the others still contribute verdicts, so the Synthesis gets partial signal rather than nothing.

If 0-tool-call recurs in v6 under the smaller prompts — for example, if multiple sub-Investigators consistently fail to probe for certain hypothesis shapes — we treat it as a structural ADK issue to debug in isolation (tool definitions, model config, thinking-mode interactions). That debugging is scoped out of this ADR but will likely be needed during Phase 3.

---

## Resolved design decisions

All seven open questions from the initial draft were resolved on 2026-04-19.

1. **Parallel Investigator cap.** `MAX_PARALLEL_INVESTIGATORS = 3`. NA produces up to 3 hypotheses; if more, ranked per the hypothesis-ranking rule, top 3 investigated.

2. **Execution model.** Parallel. Orchestrator uses concurrent Runners so N sub-Investigators execute simultaneously. Reduces wall-clock time; token cost grows linearly with N (capped at 3).

3. **Hypothesis ranking rule.** Primary: explanatory fit (how well does the hypothesis account for observed events?). Secondary: testability (drop any hypothesis with no identifiable falsification probes). Tertiary: specificity (prefer specific-mechanism claims over vague ones). Full rule and structured hypothesis schema in the "Hypothesis cap and ranking rule" section.

4. **Common package name.** `agentic_ops_common`. Verbose but unambiguous and consistent with the `agentic_ops_v{n}` naming pattern.

5. **Trigger evaluator invocation model.** Agent-driven, invoked by the agentic chaos framework (NOT by the agentic ops pipeline), at four phase points: baseline, fault injection, each observation-traffic tick, end of observation. Full details in the "Trigger evaluator invocation model" section. The agentic ops pipeline is a pure consumer of events read from the event store, scoped by episode_id.

6. **Phase 4 (operational context).** Stub implementation driven by chaos-scenario metadata. No external-system integration in scope. Scenarios declare `operational_context` tags (e.g., `upgrade_window: True`, `expected_symptoms: [...]`); correlation engine consumes these for suppression rules. Real integration with ServiceNow / BSS / etc. is deferred. Phase 4 itself is lower priority than Phase 3 for the chaos-score goal and becomes relevant only when the chaos library adds planned-activity variants.

7. **v5 frozen.** No feature work, no bug fixes on v5 going forward. Only exception: the Phase 0 refactor that updates v5's imports to reference `agentic_ops_common/`. v5 remains runnable solely as a regression baseline. Bugs discovered in v5 during v6 development are documented but not fixed.

---

## What this ADR does not cover

- The specific event DSL grammar (covered in `metric_knowledge_base_schema.md`).
- Correlation engine algorithm details (deferred to its own ADR when promoted from stub).
- Per-agent prompt text.
- UI/GUI changes for v6 episode visualization.
- Production deployment plan.
