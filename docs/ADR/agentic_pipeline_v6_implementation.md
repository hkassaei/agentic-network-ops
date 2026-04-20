# ADR: Agentic Pipeline v6 — Implementation Reference

**Date:** 2026-04-19
**Status:** Implemented (Phases 0-3 landed; Phases 4-6 deferred)
**Related:**
- [`agentic_ops_v6_plan.md`](agentic_ops_v6_plan.md) — decision record for v6 (the "why")
- [`metric_knowledge_base_schema.md`](metric_knowledge_base_schema.md) — schema for the KB the pipeline consumes
- [`alarm_correlation_engine.md`](alarm_correlation_engine.md) — stub ADR; this pipeline embeds an MVP correlation engine
- [`falsifier_investigator_and_rag.md`](falsifier_investigator_and_rag.md) — Track 1 (falsifier) carried forward, now parallelized per hypothesis

---

## Purpose

The v6 plan ADR captures **what** we decided to build and **why**. This ADR captures **what was actually implemented and how it flows at runtime**. Intended readers: anyone who needs to understand, debug, or extend the v6 pipeline without re-deriving it from code.

Scope: the 8-phase agent pipeline in `agentic_ops_v6/` plus its contracts with the chaos framework and the metric KB. Content-authoring (`metrics.yaml`) and shared infrastructure (`agentic_ops_common/`) are described in their own ADRs.

---

## The pipeline at a glance

```
 BEFORE the pipeline runs — the chaos framework has already:
   - captured a baseline snapshot
   - injected faults
   - generated observation traffic + collected metric snapshots
   - invoked the trigger evaluator, which fired events into SQLite
     scoped by episode_id
                             │
                             ▼
 ┌────────────────────────────────────────────────────────────────────┐
 │ agentic_ops_v6.orchestrator.investigate(question, episode_id, …)   │
 │                                                                    │
 │ Phase 0  AnomalyScreener         (ML, no LLM)                       │
 │ Phase 1  EventAggregator         (Python, no LLM)                   │
 │ Phase 2  CorrelationAnalyzer     (Python, runs correlation engine)  │
 │ Phase 3  NetworkAnalyst          (LLM — forms ranked hypotheses)    │
 │ Phase 4  InstructionGenerator    (LLM — plan per hypothesis)        │
 │ Phase 5  Investigator × N        (LLM — parallel sub-agents)        │
 │ Phase 6  EvidenceValidator       (Python, per-sub-agent)            │
 │ Phase 7  Synthesis               (LLM — aggregates verdicts)        │
 │                                                                    │
 │ Returns:                                                           │
 │   diagnosis: markdown text                                         │
 │   investigation_trace: phases + tokens + tool calls                │
 │ (contract matches v5 for ChallengeAgent integration)               │
 └────────────────────────────────────────────────────────────────────┘
```

Phases run in numbered order: 0 → 1 → 2 → 3 → 4 → 5 → 6 → 7. Earlier drafts had NA at Phase 2 and correlation at Phase 3; they've been swapped so the numbering matches execution order. The NA (Phase 3) consumes the correlation engine's output (Phase 2) as an input.

---

## Phase 0 — AnomalyScreener

**Type:** Python + River HalfSpaceTrees. No LLM.
**Location:** `agentic_ops_v6/orchestrator.py::_phase0_anomaly_screener`.
**Inputs:**
- Optional `metric_snapshots` (the chaos framework passes observation snapshots here).
- Falls back to a live `get_nf_metrics()` snapshot if none provided.
**Outputs:**
- `state["anomaly_report"]` — prompt-injectable text for downstream agents.
- `state["anomaly_flags"]` — structured per-feature anomaly records.

**Behavior:**
- Loads the trained 28-feature baseline model via `agentic_ops_common.anomaly`.
- Runs the preprocessor's sliding-window rates + liveness signals across all snapshots.
- Scores snapshots 6 onward (earlier ones lack rate history). Keeps the highest-scoring report.
- Silent-failure escalation + temporal-metric pre-filter are already applied at the screener + preprocessor layers (per [`anomaly_training_zero_pollution.md`](anomaly_training_zero_pollution.md)).

**Unchanged from v5** after the zero-pollution + escalation improvements. This is the fastest and cheapest signal — everything downstream weights it.

---

## Phase 1 — EventAggregator

**Type:** Python. No LLM.
**Location:** `agentic_ops_v6/subagents/event_aggregator.py`, invoked from the orchestrator.
**Inputs:**
- `episode_id` (from the chaos framework's session state, passed via `V6_EPISODE_ID` env var).
- SQLite event store at `agentic_ops_common/metric_kb/events.db`.
**Outputs:**
- `state["fired_events"]` — rendered text listing event type, source metric, source NF, timestamp, magnitude payload.
- `state["fired_event_count"]` — raw integer count.
- Returns the `list[FiredEvent]` for Phase 3 to consume.

**Behavior:**
- Queries `EventStore.get_events(episode_id=…)`.
- Renders each event as one line with key magnitude fields (`current_value`, `prior_stable_value`, `delta_percent`) when present.

**New in v6.** v5 had no notion of structured events — it reasoned directly over raw metrics.

**Contract note:** v6 is a pure consumer of the event store. If the chaos framework did not invoke the trigger evaluator (e.g., because the KB is unavailable), this phase yields an empty event set and the pipeline still runs but with weaker input signal.

---

## Phase 2 — CorrelationAnalyzer

**Type:** Python wrapping the correlation engine. No LLM.
**Location:** `agentic_ops_v6/subagents/correlation_analyzer.py`, engine at `agentic_ops_common/correlation/engine.py`.
**Inputs:**
- Metric KB (loaded from `network_ontology/data/metrics.yaml`).
- List of fired events from Phase 1.
**Outputs:**
- `state["correlation_analysis"]` — rendered text showing ranked composite hypotheses, each with primary NF, explanatory_fit, supporting events, and discriminating probes.
- Internally, a `CorrelationAnalysis` object with `top_statement`, `top_primary_nf`, `top_explanatory_fit`.

**Algorithm** (`correlate()` in the engine):
1. Build a participation index from the KB: for every trigger event, which composite interpretations does it support, paired with which peer event?
2. For each fired event, consult its `correlates_with` entries. If the referenced peer event also fired, the composite interpretation is realized.
3. Group fired events by composite interpretation (pair-wise minimum: ≥2 constituents).
4. Collect disambiguators from each supporting event's source metric for testability scoring.
5. Rank by `(explanatory_fit, testability, event_count)` descending.

**Why Python, not LLM:** the correlation logic is deterministic — apply rules authored in the KB's `correlates_with` hints. No reasoning invention. This is Gap-2 bidirectional inference done structurally.

**Runs before the NetworkAnalyst:** the NA (Phase 3) consumes the correlation engine's ranked hypotheses as one of its structured inputs. A flat event list without correlation would make NA's job materially harder.

---

## Phase 3 — NetworkAnalyst (LLM, gemini-2.5-pro)

### The NA's four inputs

The NetworkAnalyst receives FOUR independent input sources and must reconcile them. This is the core design principle of the v6 pipeline: the NA is a reconciler over heterogeneous evidence, not a single-source reasoner.

```
                  ┌─────────────────────────────────────────────┐
                  │         NetworkAnalyst (Phase 3)            │
                  │                                             │
    Phase 0  ────▶│ 1. Anomaly screener output                  │
    (ML)          │    "these metrics deviate N-σ from baseline"│
                  │                                             │
    Phase 1  ────▶│ 2. Fired events                             │
    (Python)      │    "these state transitions crossed         │
                  │     thresholds during the window"           │
                  │                                             │
    Phase 2  ────▶│ 3. Correlation analysis                     │
    (Python)      │    "events X + Y together suggest H"        │
                  │                                             │
    Tools    ────▶│ 4. Live tools (measure_rtt, get_nf_metrics, │
                  │    ontology, etc.) for confirmation         │
                  │                                             │
                  │ Output: ranked testable hypotheses          │
                  └─────────────────────────────────────────────┘
```

Each input answers a **different question** about the incident:

| Input | Question it answers | Type of signal |
|---|---|---|
| Anomaly screener | "Which raw metrics are off?" | Statistical (σ distance) |
| Fired events | "Which named state transitions happened?" | Qualitative / semantic |
| Correlation | "Which transitions co-fire meaningfully?" | Compositional / causal |
| Live tools | "What's the current ground truth?" | Direct verification |

### Why all four, not a subset

1. **Anomaly screener is a safety net for gaps in the KB.** The screener flags any trained feature that deviates, regardless of whether we've authored a KB event trigger for it. If we missed authoring a trigger for some rarely-anomalous metric, the screener still surfaces it. We lose nothing by keeping it.

2. **Events are the KB's opinion; anomaly screener is the model's opinion.** They're independent evidence. If they agree, confidence is higher. If they disagree, that disagreement is itself diagnostic information — the NA should notice and investigate why.

3. **Correlation needs events to work on.** If no events fire (a scenario outside the KB's coverage), correlation has nothing. In that case the NA falls back to anomaly-screener-only reasoning — equivalent to v5's behavior. It's a graceful degradation, not a hard dependency.

4. **Events are structured; the screener is quantitative.** An event says `core.amf.ran_ue_full_loss fired` — a named, bounded claim carrying its own `local_meaning` narrative from the KB. The screener says `amf.ran_ue: 2 → 0, severity HIGH` — a magnitude with statistical weight. Both useful, for different kinds of reasoning. Neither subsumes the other.

### Detailed input wiring

**Location:** `agentic_ops_v6/subagents/network_analyst.py`, prompt at `agentic_ops_v6/prompts/network_analyst.md`.
**Template variables in the prompt:**
- `{anomaly_report}` — Phase 0 output.
- `{fired_events}` — Phase 1 rendered text.
- `{correlation_analysis}` — Phase 2 rendered text.
**Tools available:**
- Metric queries: `get_nf_metrics`, `get_dp_quality_gauges`, `get_network_status`, `measure_rtt`.
- Ontology: `get_network_topology`, `get_vonr_components`, `check_stack_rules`, `compare_to_baseline`, `get_causal_chain_for_component`, and the `OntologyConsultationAgent` subagent.
**Output schema:** `NetworkAnalystReport` (structured):
```yaml
summary: str
layer_status:
  infrastructure: {rating, evidence, note}
  ran: ...
  core: ...
  ims: ...
hypotheses:
  - id: h1
    statement: "specific-mechanism claim, 1-2 sentences"
    primary_suspect_nf: "amf"
    supporting_events: ["core.amf.ran_ue_full_loss", ...]
    explanatory_fit: 0.87
    falsification_probes: ["measure_rtt from pcscf to icscf_ip", ...]
    specificity: specific | moderate | vague
```

**Ranking rule** baked into the prompt (enforced by the orchestrator after parsing):
1. Primary — `explanatory_fit` DESC.
2. Secondary — testability (count of `falsification_probes`) DESC. **Hypotheses with zero probes are DROPPED, not ranked low.**
3. Tertiary — specificity tier (specific > moderate > vague).

**Cap:** `MAX_PARALLEL_INVESTIGATORS = 3`. If NA produces more hypotheses, the orchestrator applies the ranking rule and takes top 3.

**Major change vs v5:** v5's NA produced a flat `suspect_components` list with informal confidence labels. v6's NA produces **ranked competing hypotheses with explicit evidence and discriminating probes** — the input format the downstream falsifier architecture requires.

---

## Phase 4 — InstructionGenerator (LLM, gemini-2.5-flash)

**Location:** `agentic_ops_v6/subagents/instruction_generator.py`, prompt at `agentic_ops_v6/prompts/instruction_generator.md`.
**Inputs:**
- `{network_analysis}` — NA's ranked hypotheses, rendered as markdown.
- `{correlation_analysis}` — same as NA's.
- `{fired_events}` — for context.
**Tools:**
- `get_causal_chain_for_component`, `get_network_topology`, `get_vonr_components` (ontology-driven).
**Output schema:** `FalsificationPlanSet`:
```yaml
plans:
  - hypothesis_id: h1
    hypothesis_statement: "..."
    primary_suspect_nf: "amf"
    probes:
      - tool: measure_rtt
        args_hint: "pcscf → icscf_ip"
        expected_if_hypothesis_holds: "100% packet loss (partition)"
        falsifying_observation: "clean RTT — hypothesis disproven"
      # minimum 2 probes per plan, target 3
    notes: "cross-layer focus: ..."
```

**Behavior:**
- Iterates over the NA's hypotheses, produces ONE focused plan per hypothesis.
- Each plan has ≥2 probes (target 3) chosen to specifically discriminate that hypothesis — preferring KB disambiguators the NA surfaced, plus cross-layer checks the NA did not cover.
- Probes must name real tools from the Investigator's toolkit; invented tool names will fail downstream.

**Major change vs v5:** v5 IG produced one plan for the NA's primary suspect only. v6 IG produces N plans — the structural enabler for parallel Investigators.

---

## Phase 5 — Investigator × N (LLM, gemini-2.5-pro, parallel)

**Location:** `agentic_ops_v6/subagents/investigator.py` (factory), parallel execution in `orchestrator.py::_run_parallel_investigators`. Prompt at `agentic_ops_v6/prompts/investigator.md`.
**Fan-out:**
- Orchestrator ranks + caps NA hypotheses at 3.
- Drops hypotheses with zero `falsification_probes` (per the ranking rule).
- For each surviving hypothesis, spawns a fresh `InvestigatorAgent_{h.id}` with its own ADK session.
- `asyncio.gather` executes them concurrently.

**Per-sub-agent prompt template vars:**
- `{hypothesis_id}`, `{hypothesis_statement}`, `{primary_suspect_nf}` — JUST this hypothesis.
- `{falsification_plan}` — JUST this hypothesis's plan.
- `{network_analysis}` — full NA report for context.

**Tools available:** every diagnostic tool (13 total): `measure_rtt`, `check_process_listeners`, `query_prometheus`, `get_nf_metrics`, `get_dp_quality_gauges`, `get_network_status`, `run_kamcmd`, `read_running_config`, `read_container_logs`, `search_logs`, `read_env_config`, `query_subscriber`, plus `OntologyConsultationAgent`.

**Output schema:** `InvestigatorVerdict`:
```yaml
hypothesis_id: h1
hypothesis_statement: "..."
verdict: DISPROVEN | NOT_DISPROVEN | INCONCLUSIVE
reasoning: "2-3 sentences"
probes_executed:
  - probe_description: "..."
    tool_call: 'measure_rtt("pcscf", "172.22.0.19")'
    observation: '[EVIDENCE: measure_rtt("pcscf", "172.22.0.19") -> "100% loss"]'
    compared_to_expected: CONTRADICTS | CONSISTENT | AMBIGUOUS
    commentary: "..."
alternative_suspects: [<populated only if DISPROVEN>]
```

### Mechanical guardrail

The orchestrator inspects each sub-Investigator's trace AFTER the sub-agent finishes. If `tool_calls < MIN_TOOL_CALLS_PER_INVESTIGATOR (=2)`, the verdict is **forced to `INCONCLUSIVE`** regardless of what the LLM self-reported, and the self-reported output is discarded.

**Rationale:** v5 suffered from repeated 0-tool-call hallucinations — the LLM emitted polished falsification output without invoking any tool. Two fixes applied together in v6:
1. **Focus reduction** — a small prompt with one hypothesis + 2-3 probes is easier for the LLM to execute faithfully than a broad falsification task.
2. **Mechanical enforcement** — the guardrail catches any residual hallucination.

**Major change vs v5:** v5 had one Investigator seeing all hypotheses at once with one mixed plan. v6 has N sub-agents each with a focused contract. Parallel execution means the wall-clock impact is proportional to the slowest sub-agent, not N × duration.

---

## Phase 6 — EvidenceValidator

**Type:** Python, no LLM.
**Location:** `agentic_ops_v6/subagents/evidence_validator.py`.
**Inputs:**
- All phase traces collected so far (each with its `tool_calls` list).
- The list of `InvestigatorVerdict` objects from Phase 5, labeled by agent name.
**Output:** `state["evidence_validation"]` with per-agent and overall verdicts:
```yaml
overall_verdict: clean | has_warnings | severe
overall_confidence: high | medium | low | none
per_agent:
  - agent_name: InvestigatorAgent_h1
    tool_calls_made: 3
    citations_found: 3
    citations_matched: 3
    citations_unmatched: 0
    verdict: clean
    confidence: high
    notes: []
  - ...
summary: "..."
```

**Algorithm:**
1. For each sub-Investigator, extract `[EVIDENCE: tool_name(...)]` citations from its rendered output using regex.
2. Compare against the set of tool names the sub-Investigator actually called.
3. Per-agent verdict:
   - `severe` if tool_calls == 0, or if unmatched citations ≥ matched citations.
   - `has_warnings` if any unmatched citations exist or tool_calls < 2.
   - `clean` otherwise.
4. **Aggregate:** worst per-agent verdict becomes overall; confidence = tightest (lowest) per-agent confidence.

**Change vs v5:** v5's validator saw one Investigator. v6's processes N sub-agents independently and aggregates with tightest-cap semantics.

---

## Phase 7 — Synthesis (LLM, gemini-2.5-pro)

**Location:** `agentic_ops_v6/subagents/synthesis.py`, prompt at `agentic_ops_v6/prompts/synthesis.md`.
**Inputs (template vars):**
- `{network_analysis}` — NA's ranked hypotheses.
- `{correlation_analysis}` — Phase 2 output.
- `{investigator_verdicts}` — all N sub-Investigator verdicts.
- `{evidence_validation}` — Phase 6 output.
**Tools:** none. Pure synthesis.
**Output:** `state["diagnosis"]` — plain markdown NOC report.

### Verdict aggregation rule (in the prompt)

- **Case A** — exactly one `NOT_DISPROVEN`, others `DISPROVEN` → that's the root cause, confidence `high`.
- **Case B** — multiple `NOT_DISPROVEN` → cascade or insufficient evidence, confidence `medium`; list survivors.
- **Case C** — all `DISPROVEN` → NA's hypothesis set was wrong; aggregate alternative suspects from each DISPROVEN, confidence `low`.
- **Case D** — any `INCONCLUSIVE` → cap confidence at `medium`.

### Evidence cap

- `clean` → no additional cap beyond verdict rule.
- `has_warnings` → cap at `medium`.
- `severe` → cap at `low`.
- **Whichever cap is tighter wins.**

**Output shape** (matches v5's for ChallengeAgent integration):
```markdown
### causes
- **summary**: one sentence.
- **timeline**: [events in order]
- **root_cause**: the confirmed or best-candidate cause.
- **affected_components**: [{name, role}]
- **recommendation**: what to VERIFY next (not remediation).
- **confidence**: high | medium | low
- **explanation**: 3-5 sentences for a NOC engineer.
```

**Change vs v5:** v5's synthesis processed a single Investigator's output with a single verdict. v6's explicitly aggregates across N verdicts with the rules above.

---

## The trigger evaluator contract (external to this pipeline)

v6 is a **consumer** of the event store. The **producer** is the chaos framework, via `agentic_chaos/trigger_evaluator_integration.py`. The evaluator is invoked by the chaos `ObservationTrafficAgent` at the end of observation traffic collection:

1. Combines baseline snapshot + observation snapshots.
2. Runs them through `MetricPreprocessor` to get rate-based features.
3. Also extracts raw NF metrics that the KB tracks but the preprocessor excludes (e.g., `amf.ran_ue`).
4. Invokes `evaluate(kb, eval_ctx, store)` — the trigger evaluator (simpleeval DSL) fires events into SQLite with `episode_id` scoping.

v6 reads from that store at Phase 1. If the chaos framework fails to invoke the evaluator (e.g., `metrics.yaml` fails to load), Phase 1 yields an empty event list, Phase 3 produces no correlation hypotheses, and the NA has only the anomaly screener as input — degraded but still functional.

---

## Orchestrator state — what flows through the pipeline

The v6 orchestrator uses ADK's session state dict as the canonical bus between phases. Key entries:

| Key | Producer | Consumer |
|---|---|---|
| `episode_id` | entrypoint | every phase |
| `anomaly_report` | Phase 0 | Phase 3 (NA) |
| `anomaly_flags` | Phase 0 | (telemetry) |
| `fired_events` | Phase 1 | Phases 3, 4 (NA, IG) |
| `fired_event_count` | Phase 1 | (telemetry) |
| `correlation_analysis` | Phase 2 | Phases 3, 4, 7 |
| `network_analysis` | Phase 3 (NA) | Phases 4, 5, 7 |
| `falsification_plan_set` | Phase 4 (IG) | Phase 5 |
| `investigator_verdict` (per sub-agent session) | Phase 5 | aggregated in orchestrator |
| `investigator_verdicts` (combined) | orchestrator | Phase 7 |
| `evidence_validation` | Phase 6 | Phase 7 |
| `diagnosis` | Phase 7 (Synthesis) | return value |
| `phase_traces_so_far` | every phase | EvidenceValidator + trace output |

All inter-phase handoffs that go to LLM prompts get re-rendered as markdown text via helpers in `orchestrator.py` (`_pretty_print_na_report`, `_render_correlation_result`, etc.) — the LLM sees structured-yet-readable text, not raw JSON.

---

## Integration with the chaos framework

Three touch points:

1. **`--agent v6` registered** in `agentic_chaos/cli.py` + `_AGENT_LOG_DIRS`.
2. **ChallengeAgent** (`agentic_chaos/agents/challenger.py`) recognizes `v6`, sets `V6_EPISODE_ID` env var from session state, and calls `agentic_ops_v6.orchestrator.investigate(...)` with the same kwargs as v5.
3. **ObservationTrafficAgent** (`agentic_chaos/agents/observation_traffic.py`) invokes the trigger evaluator via `agentic_chaos/trigger_evaluator_integration.py` at end of observation, writing fired events to SQLite scoped by `episode_id`.

v5 continues to work unchanged (frozen per the v6 plan). `--agent v5` and `--agent v6` can both be run without cross-contamination; episode outputs land in separate `docs/agent_logs/` directories.

---

## File layout reference

```
agentic_ops_v6/
  __init__.py
  __main__.py                    # CLI entry: python -m agentic_ops_v6 "<question>"
  orchestrator.py                # the pipeline glue; _run_phase, _run_parallel_investigators
  models.py                      # Pydantic types: Hypothesis, FalsificationPlan, InvestigatorVerdict, ...
  prompts/
    network_analyst.md
    instruction_generator.md
    investigator.md
    synthesis.md
    ontology_consultation.md
  subagents/
    __init__.py
    network_analyst.py           # create_network_analyst()
    instruction_generator.py     # create_instruction_generator()
    investigator.py              # create_investigator_agent(name=...)
    synthesis.py                 # create_synthesis_agent()
    event_aggregator.py          # aggregate_episode_events()
    correlation_analyzer.py      # analyze_correlations()
    evidence_validator.py        # validate_evidence()
    ontology_consultation.py     # create_ontology_consultation_agent()
  docs/
    agent_logs/                  # episode outputs for --agent v6
  tests/
    test_orchestrator_helpers.py # ranking, parsing, rendering
    test_evidence_validator.py   # per-agent + aggregate verdicts
    test_wiring.py               # every agent constructible
```

```
agentic_ops_common/
  anomaly/                       # shared with v5 (frozen)
  tools/                         # shared with v5 (frozen)
  models/trace.py                # shared trace types
  metric_kb/                     # Phase 1 infrastructure
    loader.py
    models.py
    event_dsl.py
    metric_context.py
    event_store.py
    evaluator.py
  correlation/                   # Phase 2 infrastructure
    engine.py
    models.py
```

---

## Differences from v5, summarized

| Aspect | v5 | v6 |
|---|---|---|
| NA input | Raw metrics + ontology tools | Metrics + **fired events** + **correlation hypotheses** + ontology |
| NA output | Flat suspect list | Ranked hypotheses with explicit probes |
| Investigator | One agent, one plan, all hypotheses | N parallel sub-agents, focused prompts |
| 0-tool-call defense | Single guardrail on the one Investigator | Guardrail **per sub-agent** |
| Correlation reasoning | Rigid `symptom_signatures.yaml` pattern matching | Event-driven correlation engine over KB hints |
| Verdict aggregation | Implicit in LLM reasoning | Explicit rules in Synthesis prompt |
| Event vocabulary | None | 22 event types across 27 metrics in KB |
| Chaos ↔ ops boundary | Ops reads metrics directly | Chaos produces events → ops consumes them via SQLite |
| Output contract | `diagnosis` + `investigation_trace` | Same — v6 matches for ChallengeAgent integration |

Underlying theme: **v6 moves reasoning from implicit LLM chains to structured pipelines with explicit contracts at each boundary.** The LLM still does the hypothesis generation, probe execution, and synthesis, but the shape of what flows between phases is deterministic and inspectable.

---

## Known limitations (Phase-3-scope)

1. **No operational-context suppression** (Phase 5 of the v6 plan). The correlation engine produces composite hypotheses but doesn't know about planned change windows or subscriber lifecycle events. A chaos scenario tagged "AMF upgrade window" would escalate instead of being suppressed. Deferred to Phase 5.

2. **No blast-radius projection.** Synthesis names affected components but doesn't project forward to flows / services / subscribers. Deferred to Phase 5.

3. **No episode RAG.** Past episode diagnoses aren't retrievable as analogs. Deferred to Phase 6 (Track 2).

4. **KB content covers 27 metrics of ~77 in `baselines.yaml`.** Sufficient for the 11 chaos scenarios, but `baselines.yaml` is still active for metrics the KB doesn't cover. Deferred to Phase 4 (retire baselines.yaml).

5. **No live Prometheus-backed `MetricContext`.** The trigger evaluator runs over snapshot history (via the preprocessor's ring buffer + baseline snapshot). Longer-window temporal queries would require Prometheus integration. Sufficient for episode-scoped evaluation; production-scale would need it.

6. **Sub-Investigator isolation is session-level, not container-level.** Each sub-agent gets its own ADK session, but they share the same Python process + tool instances. Fine for current scale.

---

## Testing status

118 tests passing across the v6 stack (as of Phase 3 completion):

- **19** loader + schema tests (`agentic_ops_common/tests/test_metric_kb_loader.py`)
- **24** DSL + predicate tests (`test_event_dsl.py`)
- **10** event store tests (`test_event_store.py`)
- **11** trigger evaluator integration tests (`test_evaluator.py`)
- **13** correlation engine tests (`test_correlation_engine.py`)
- **12** chaos integration tests (`test_trigger_evaluator_integration.py`)
- **29** v6-specific tests (ranking, parsing, validator, wiring)

Not tested automatically (requires live stack + GCP credentials):
- End-to-end chaos scenarios against `--agent v6` (Phase 3 acceptance criteria).
- LLM output quality under specific scenarios.
