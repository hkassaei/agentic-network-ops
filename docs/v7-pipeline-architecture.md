# v7 Agentic Pipeline — Architecture

## Purpose

A diagnostic agent that takes anomaly observations from a 5G SA + IMS deployment and produces a structured root-cause diagnosis (`DiagnosisReport`) naming the responsible network function or transport hop. The pipeline routes faults through one of two specialized branches based on whether the cause lives above or below the application's `recv()`/`send()` boundary, then converges on a single LLM Synthesis stage that emits the diagnosis.

## Pipeline overview

```
                  ┌────────────────────────────────┐
                  │  Phase 0    Anomaly Screener   │  PyOD ECOD on
                  │             (Python)            │  preprocessor features
                  └──────────────┬─────────────────┘
                                 │
                                 ▼
                  ┌────────────────────────────────┐
                  │  Phase 0.5  Symptom Classifier │  KB-driven (no LLM):
                  │             (Python)            │  reads each flag's
                  │                                 │  fault_layer label
                  └──────────────┬─────────────────┘
                                 │
                  label ∈ {transport_layer, mixed}     label == application_layer
                                 │                          │
                                 ▼                          │
                  ┌────────────────────────────────┐        │
                  │  Phase 0.6  Path Resolver      │        │
                  │             (Python)            │        │
                  │             flow → ordered hops │        │
                  │                                 │        │
                  │  Phase 0.6  Path Walker        │        │
                  │             (Python)            │        │
                  │             KernelHopProber     │        │
                  │             + DockerBridgeProber│        │
                  │             per hop             │        │
                  └─────┬──────────────────┬───────┘        │
                        │ localized        │ null-localized │
                        │                  └────────────────┤  (fall-through)
                        │                                   │
                        │                                   ▼
                        │                ┌─────────────────────────────────┐
                        │                │  Phase 1   Event Aggregator     │
                        │                │            (Python)              │
                        │                │  Phase 2   Correlation Analyzer │
                        │                │            (Python)              │
                        │                │  Phase 3   Network Analyst (LLM)│
                        │                │  Phase 4   Instruction Gen (LLM)│
                        │                │  Phase 5   Investigator(s) (LLM)│
                        │                │            ≤3 parallel fan-out, │
                        │                │            multi-shot consensus │
                        │                │  Phase 6   Evidence Validator   │
                        │                │            (LLM)                 │
                        │                │  Phase 6.5 Candidate Pool       │
                        │                │            (Python) +           │
                        │                │            bounded re-invest    │
                        │                └─────────────────┬───────────────┘
                        │                                  │
                        └──────────────┐    ┌──────────────┘
                                       ▼    ▼
                        ┌──────────────────────────────────────┐
                        │  Phase 7   Synthesis (LLM)           │
                        │            unified agent,            │
                        │            four verdict_kinds        │
                        └──────────────┬───────────────────────┘
                                       │
                                       ▼
                                DiagnosisReport
```

## Phase reference

| Phase | Component | Kind | Output |
|---|---|---|---|
| 0 | AnomalyScreener | Python (PyOD ECOD) | `AnomalyReport` — list of `AnomalyFlag` per metric, each enriched with `kb_context` |
| 0.5 | SymptomClassifier | Python (KB lookup) | `SymptomClassification(label, transport_flags, application_flags, ambiguous_flags, rationale)` |
| 0.6 | PathResolver | Python (flows + topology) | `ResolvedPath(flow_id, hops)` |
| 0.6 | PathWalkInvestigator | Python (HopProber registry) | `PathWalkReport(flow_id, hops[HopRecord], is_localized, first_attributed_hop)` |
| 1 | EventAggregator | Python (causal-chain rendering) | rendered event list + structured events |
| 2 | CorrelationAnalyzer | Python (composite scoring) | `CorrelationAnalysis(top_statement, top_primary_nf, hypotheses_text)` |
| 3 | NetworkAnalyst | LLM (Gemini, structured output) | `NetworkAnalystReport(hypotheses[1..3], layer_status, summary)` |
| 4 | InstructionGenerator | LLM (Gemini, structured output) | `FalsificationPlanSet(plans[≥1, each with 2-4 probes])` |
| 5 | Investigator (fan-out) | LLM (Gemini, tools enabled) | per-hypothesis `InvestigatorVerdict(verdict ∈ {DISPROVEN, NOT_DISPROVEN, INCONCLUSIVE}, probes_executed, alternative_suspects)` |
| 6 | EvidenceValidator | LLM (Gemini) | per-Investigator citation-fabrication verdict |
| 6.5 | CandidatePool | Python (verdict-tree walk) | `CandidatePool(members[survivors + promoted])`; runs bounded re-investigation when all-DISPROVEN with promoted suspects |
| 7 | Synthesis | LLM (Gemini, structured output) | `DiagnosisReport` |

## Routing logic (Phase 0.5 → 0.6 → 1)

The classifier inspects each anomaly flag's `MetricEntry.fault_layer` from the KB:

- **`application_layer`** — go straight to Phase 1. The path walker is skipped.
- **`transport_layer`** — engage Phase 0.6. If the walker localizes a hop, jump to Phase 7. If not, fall through to Phase 1.
- **`mixed`** — same as `transport_layer`. Mixed signals (e.g. control-plane signaling counters that move under both transport and application faults) are checked at the kernel/element layer first; only if no transport-layer counter advances do we run the application-layer pipeline.

The label is computed deterministically — every flag has a definite `fault_layer` value in the KB, the classifier counts buckets and applies a fixed precedence rule. No LLM involved.

## Two pipeline branches

### Application-layer branch

Phases 1 → 2 → 3 → 4 → 5 → 6 → 6.5 → 7. Each LLM phase is gated by an empty-output retry plus phase-specific guardrails (output sanitizers, ranking coverage, hypothesis-statement linter, IG plan validator, multi-shot consensus, candidate-pool membership, confidence cap). Phase 5 fans out one Investigator per hypothesis (≤3 parallel); each Investigator has access to a fixed tool surface (`measure_rtt`, `check_process_listeners`, `get_diagnostic_metrics`, `run_kamcmd`, `read_running_config`, `query_subscriber`, ontology consultation, etc.).

The branch produces one of three verdict kinds at Phase 7:
- `confirmed` — sole NOT_DISPROVEN survivor (or re-investigation NOT_DISPROVEN).
- `promoted` — diagnosis derived from `alternative_suspects` cross-corroboration in an all-DISPROVEN tree.
- `inconclusive` — empty pool or evidence too weak.

### Transport-layer (path-walk) branch

Phase 0.6 runs deterministic Python:

1. **PathResolver** — turns the implicated flow (resolved from KB authoring) into an ordered hop list. Each hop is `(node, kind, iface)`; `kind ∈ {container, docker_bridge, l2_switch, ...}`.
2. **PathWalkInvestigator** — for each hop in topology order, dispatches to a `HopProber` matching the hop's kind. The prober reads the kernel/element-level counter natively (e.g. `tc -s qdisc show dev <iface>` inside the container, `iptables -L -v -n` on the bridge) and emits one of: `CleanHop`, `DropsAttributedHere`, `DropsAttributedToInboundLink`, `LatencyAtHop`, `InconclusiveHop`. The walk's `first_attributed_hop` is the first non-`CleanHop`/`InconclusiveHop` in topology order.
3. If `is_localized`, jump to Phase 7. If null-localized, fall through to the application-layer pipeline.

The branch produces a `localized` verdict at Phase 7 — `primary_suspect_nf` is the attributed hop's node, `localization` carries the verbatim counter excerpt.

## Synthesis unification

Both branches converge on a single `create_synthesis_agent()` LLM call (Gemini, structured output, schema = `DiagnosisReport`). The agent's behaviour is selected by the prompt's branch-select directive, which reads the input bundle.

**Bundle keys (template substitutions):**

| Placeholder | Source | App-layer branch | Localized branch |
|---|---|---|---|
| `{path_walk_for_synthesis}` | Phase 0.6 walk-table render | `""` | walk-table + verbatim counter excerpt + classifier rationale |
| `{network_analysis}` | Phase 3 | NA-rendered hypotheses | `""` |
| `{correlation_analysis}` | Phase 2 | rendered text | `""` |
| `{investigator_verdicts}` | Phase 5 | aggregated verdicts JSON | `""` |
| `{evidence_validation}` | Phase 6 | validator output JSON | `""` |
| `{candidate_pool}` | Phase 6.5 | rendered pool | `""` |

**Branch-select rule (in the prompt):** if `{path_walk_for_synthesis}` is non-empty, emit `verdict_kind=localized` and follow the localized-verdict rules; otherwise apply the application-layer rules and emit `confirmed`/`promoted`/`inconclusive`.

**Guardrail closures differ by branch:**

- App-layer closure: pool-membership → confidence cap → output sanitizer.
- Localized closure: output sanitizer only. The pool-membership and confidence-cap guardrails recognize `verdict_kind == "localized"` and short-circuit at function entry; they have no candidate pool or InvestigatorVerdict probe-result counts to compute against on the path-walk branch.

The output is the same `DiagnosisReport` Pydantic model regardless of branch. The `localization` field is populated only on `localized`; the `primary_suspect_nf` field is `null` only on `inconclusive`.

## Data contracts at branch boundaries

```
AnomalyReport (Phase 0)
    └─ list[AnomalyFlag(metric, component, current, learned_normal,
                        anomaly_score, severity, direction, kb_context)]

SymptomClassification (Phase 0.5)
    ├─ label: "transport_layer" | "application_layer" | "mixed"
    ├─ rationale: str
    └─ {transport, application, ambiguous}_flags: list[FlagBucket]

ResolvedPath (Phase 0.6)
    ├─ flow_id: str
    └─ hops: list[Hop(node, kind, iface)]

PathWalkReport (Phase 0.6)
    ├─ flow_id: str
    ├─ is_localized: bool
    ├─ first_attributed_hop: HopRecord | None
    └─ hops: list[HopRecord(hop, attribution, prober)]

NetworkAnalystReport (Phase 3)
    └─ hypotheses: list[Hypothesis(id, statement, primary_suspect_nf,
                                   falsification_probes, ...)]

FalsificationPlanSet (Phase 4)
    └─ plans: list[FalsificationPlan(hypothesis_id, primary_suspect_nf,
                                     probes: list[FalsificationProbe])]

InvestigatorVerdict (Phase 5, one per hypothesis)
    ├─ verdict: DISPROVEN | NOT_DISPROVEN | INCONCLUSIVE
    ├─ probes_executed: list[ProbeResult]
    └─ alternative_suspects: list[str]

CandidatePool (Phase 6.5)
    └─ members: list[CandidatePoolMember(nf, kind: survivor|promoted, ...)]

DiagnosisReport (Phase 7 — both branches)
    ├─ verdict_kind: confirmed | promoted | inconclusive | localized
    ├─ primary_suspect_nf: <known NF name> | None
    ├─ root_cause_confidence: high | medium | low
    ├─ summary, root_cause, affected_components, timeline,
    │   recommendation, explanation
    └─ localization: Localization | None
```

## External dependencies

- **Metric Knowledge Base** (`agentic_ops_common/metric_kb/`) — YAML-authored catalog of all 108 metrics with `Plane`, `FaultLayer`, role labels, disambiguators, related metrics. Drives the classifier's routing decision and the Investigator's metric-context rendering.
- **Flows + Topology authoring** (`network_ontology/data/flows.yaml`, topology configs) — drives the path resolver's hop list.
- **Diagnostic toolbelt** (`agentic_ops/tools.py`, `agentic_ops_common/tools/`) — the LLM-facing surface for `measure_rtt`, `get_diagnostic_metrics`, `read_running_config`, `query_subscriber`, etc. Each container ships a uniform toolbelt (`tc`, `ip`, `ss`, `nsenter`-capable host) so probers and probes are portable across NF kinds.
- **HopProber registry** (`agentic_ops_common/path_walk/`) — pluggable probers keyed on hop kind; lab implementations are `KernelHopProber` and `DockerBridgeProber`. Carrier-grade extensions (SNMP, BGP, IPsec, optical) attach to the same registry without modifying the walker.
- **Vertex AI / Gemini** — model surface for all LLM phases. Each LLM agent uses constrained decoding against its Pydantic output schema; the retry wrapper handles 429/408/5xx transparently.
- **ADK (`google.adk`)** — agent runner, session management, prompt template substitution, tool dispatch.
- **Snapshot replay** — historical metric snapshots are made available to time-aware tools via a contextvar so probes can read NF state as of the anomaly-window timestamp.

## Module layout

```
agentic_ops_v7/
  orchestrator.py                  # entry: investigate(question, ...)
  symptom_classifier.py            # Phase 0.5
  path_resolver.py                 # Phase 0.6 resolver
  models.py                        # DiagnosisReport, Hypothesis, Localization, ...
  prompts/                         # one prompt per LLM phase
    network_analyst.md
    instruction_generator.md
    investigator.md
    synthesis.md                   # branch-select directive + both verdict-kind rule sets
    ontology_consultation.md
  subagents/                       # one factory per LLM agent
    network_analyst.py
    instruction_generator.py
    investigator.py
    synthesis.py                   # the unified Synthesis agent
    correlation_analyzer.py
    event_aggregator.py
    path_walk_investigator.py      # Phase 0.6 walker
    ontology_consultation.py
  guardrails/                      # output validators / repairers
    runner.py                      # generic guardrail loop with resample
    empty_output.py
    na_linter.py
    na_ranking.py
    mechanism_grounding.py
    ig_validator.py
    probe_selection.py
    investigator_consensus.py
    investigator_minimum.py
    evidence_citations.py
    synthesis_pool.py              # short-circuits verdict_kind=localized
    confidence_cap.py              # short-circuits verdict_kind=localized
    llm_output_sanitizer.py
    base.py                        # GuardrailResult, GuardrailVerdict

agentic_ops_common/
  metric_kb/                       # Pydantic models, YAML loader, enrichment
  path_walk/                       # HopProber registry, attribution variants
  models/                          # InvestigationTrace, PhaseTrace, TokenBreakdown
  tools/                           # diagnostic tool implementations
  anomaly/                         # screener, preprocessor, feature mapping

agentic_chaos/
  agents/challenger.py             # plumbs investigate() into the chaos run
  recorder.py                      # renders InvestigationTrace into episode markdown
  scenarios/library.py             # fault-injection scenario definitions
```

## Invocation contract

```python
from agentic_ops_v7.orchestrator import investigate

result = await investigate(
    question="Why is call quality degraded?",
    on_event=on_event_callback,                     # optional event sink
    anomaly_window_hint_seconds=300,
    metric_snapshots=[...],                          # historical readings
    observation_window_duration=...,
    seconds_since_observation=...,
    episode_id="run_20260510_..."
)
# result keys:
#   diagnosis            — markdown rendering of DiagnosisReport
#   diagnosis_report     — structured DiagnosisReport (model_dump)
#   investigation_trace  — full per-phase trace
#   total_tokens
#   anomaly_report, fired_events, correlation_analysis,
#   network_analysis, investigation_instruction,
#   investigation, evidence_validation               — Phase 0..6 outputs
#   symptom_classification, resolved_path, path_walk_report
#                                                    — Phase 0.5 + 0.6 outputs
```

## Determinism and LLM exposure

| Phase | Deterministic? | LLM tokens spent |
|---|---|---|
| 0 | Yes | 0 |
| 0.5 | Yes (KB lookup) | 0 |
| 0.6 | Yes (kernel counters / probers) | 0 |
| 1 | Yes (causal-chain rendering) | 0 |
| 2 | Yes (composite scoring) | 0 |
| 3 | LLM | ~1 NA call |
| 4 | LLM | ~1 IG call |
| 5 | LLM | ≤6 calls (3 hypotheses × 2 shots) |
| 6 | LLM | ~1 EV call |
| 6.5 | Yes (verdict-tree walk) + optional 1 LLM | 0 or 1 re-investigation |
| 7 | LLM | ~1 Synthesis call |

A pure transport-layer fault (Phase 0 → 0.5 → 0.6 localized → 7) costs one LLM round-trip — Phase 7 Synthesis. A pure application-layer fault costs ~10 LLM round-trips.
