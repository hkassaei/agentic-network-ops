# Plan: agentic_ops_v5 — Deterministic Backbone & Lean Investigation

## Context

After 10+ chaos runs across v1.5-v4, the RCA agents score 2/10. The v4 attempt to wire the network ontology as optional LLM tools failed — the agent never called them (see `agentic_ops_v4/docs/ontology-integration-reflection.md`). The ADR at `docs/ADR/agentic_ops_v5_plan.md` proposes a fundamental shift: move from LLM-driven reasoning to orchestrator-driven verification, where the ontology is a deterministic step in Python, not a tool the LLM can skip.

v5 consolidates 8 agents into 3 + a deterministic Python step, and introduces short-circuit logic to avoid wasting tokens on irrelevant investigation paths.

## Architecture: 4-Phase Pipeline

```
Phase 0:   TriageAgent (LLM)           → Collects metrics, topology, logs
Phase 0.5: OntologyAnalysis (Python)   → Deterministic diagnosis + short-circuit plan
Phase 1:   InvestigatorAgent (LLM)     → Proves/disproves ontology hypothesis
Phase 2:   SynthesisAgent (LLM)        → NOC-ready diagnosis
```

## File Structure

```
agentic_ops_v5/
├── __init__.py                    # __version__ = "5.0.0"
├── orchestrator.py                # investigate() + Phase 0.5 + short-circuit logic
├── ontology_bridge.py             # Phase 0.5: collect_observations() + OntologyClient calls + plan computation
├── tools.py                       # Re-exports from agentic_ops_v4.tools (no copy)
├── agents/
│   ├── triage.py                  # Phase 0: data collection only (no ontology tools)
│   ├── investigator.py            # Phase 1: unified agent, all tools, mandate-driven
│   └── synthesis.py               # Phase 2: fact-check against ontology
├── prompts/
│   ├── triage.md                  # Simplified: collect data, no reasoning
│   ├── investigator.md            # New: ontology hypothesis as ESTABLISHED FACT, evidence rules
│   └── synthesis.md               # Hierarchy of Truth, compare investigation vs ontology
└── docs/
    └── agent_logs/                # Runtime output
```

## Key Design Decisions

### 1. Phase 0.5 collects metrics directly (not from triage text)
The orchestrator calls `get_nf_metrics()` and `get_network_status()` in Python, in parallel with the triage LLM. The ontology gets clean structured data, not parsed LLM output. The triage agent's text is for human context downstream.

### 2. Short-circuit logic
Based on ontology confidence + failure domain:
- **RAN failure (very_high)**: skip all IMS investigation, mandate = "verify RAN only"
- **Data plane failure**: skip SIP tracing, mandate = "verify data plane only"
- **Transport fault**: skip application layer until transport confirmed clean
- **IMS signaling**: still check transport first (Hierarchy of Truth), then IMS
- **No match / low confidence**: full bottom-up investigation with all tools

### 3. InvestigatorAgent replaces Tracer + 4 Specialists
Single unified agent with ALL tools. The ontology mandate steers it ("ESTABLISHED FACT: RAN failure. Your ONLY job: verify using these tools."). Evidence rules: every claim must cite a tool_call. This eliminates the v4 problem of specialists working in silos and ignoring triage findings.

### 4. Neo4j fallback
If Neo4j is down, Phase 0.5 emits a warning and proceeds with full investigation (no short-circuit). Degrades gracefully to v4-like behavior.

## Tools Per Agent

| Agent | Tools | Rationale |
|---|---|---|
| TriageAgent | `get_network_topology`, `get_network_status`, `get_nf_metrics`, `read_env_config`, `check_tc_rules` | Data collection only. No ontology tools (moved to orchestrator). |
| OntologyAnalysis | N/A (Python code) | Calls `OntologyClient.diagnose()` directly |
| InvestigatorAgent | ALL 15 tools | Full access. Mandate + suggested_tools steer usage. |
| SynthesisAgent | `interpret_log_message`, `check_component_health`, `get_causal_chain` | Read-only ontology for fact-checking |

## Implementation Steps

### Step 1: Package skeleton + standalone tools and models
- Create `agentic_ops_v5/` with `__init__.py`, empty dirs
- `tools.py`: copy from v4 (self-contained, no v4 dependency). Remove the ontology tools that were added to v4 — they're now in the orchestrator.
- `models.py`: copy from v4 (Pydantic data classes, no v4-specific logic)
- **v5 has zero imports from v4** — fully standalone

### Step 2: ontology_bridge.py (the core innovation)
- `collect_observations()` — calls tools directly (not via LLM) for clean structured metrics
- `run_deterministic_diagnosis()` — wraps OntologyClient.diagnose() + check_stack_rules()
- `_compute_investigation_plan()` — short-circuit logic per failure domain
- `_format_ontology_for_prompt()` — human-readable formatting for LLM context

### Step 3: Agents + prompts
- `agents/triage.py` + `prompts/triage.md` — simplified data collection
- `agents/investigator.py` + `prompts/investigator.md` — mandate-driven with evidence rules
- `agents/synthesis.py` + `prompts/synthesis.md` — Hierarchy of Truth enforcement

### Step 4: Orchestrator
- Port `_run_phase()` from v4 (identical session isolation pattern)
- `investigate()`: Phase 0 → Phase 0.5 (Python) → Phase 1 → Phase 2
- Parallel metrics collection alongside triage LLM
- Short-circuit logic from investigation plan
- `on_event` callbacks including new `phase_skip` event type

### Step 5: Integration points
- `gui/server.py`: add `handle_investigate_v5` + route registration
- `agentic_chaos/agents/challenger.py`: add v5 to `_rca_agent_available()` and `_run_adk_agent()`
- `agentic_chaos/cli.py`: add v5 to `_AGENT_LOG_DIRS` and `--agent` choices

### Step 6: Validation
- Run gNB Radio Link Failure scenario (the benchmark — currently 0-60%)
- Run Data Plane Degradation scenario (currently 0%)
- Compare token usage and accuracy vs v4

## Critical Files to Modify (outside v5)
- `gui/server.py` — add WebSocket endpoint (~30 lines, copy v4 handler pattern)
- `agentic_chaos/agents/challenger.py` — add v5 to 3 places (availability check, dispatch, model string)
- `agentic_chaos/cli.py` — add v5 to `_AGENT_LOG_DIRS` dict and `--agent` choices

## Critical Files to Reference (read-only, then copy into v5)
- `agentic_ops_v4/orchestrator.py` — `_run_phase()` pattern to port (not import)
- `network_ontology/query.py` — OntologyClient API (v5's only external dependency beyond ADK)
- `agentic_ops_v4/tools.py` — copy into v5/tools.py (remove v4 ontology tools, keep network tools)
- `agentic_ops_v4/models.py` — copy into v5/models.py (standalone Pydantic classes)

**v5 has zero imports from v4.** The only external dependencies are `network_ontology`, `google.adk`, and `agentic_ops` (v1.5 base tools).

## Verification
1. `python3 -c "from agentic_ops_v5.orchestrator import investigate"` — import succeeds
2. `python -m agentic_chaos run "gNB Radio Link Failure" --agent v5` — completes with score improvement over v4
3. `python -m agentic_chaos run "Data Plane Degradation" --agent v5` — completes, ontology correctly identifies N3 issue
4. Check that Phase 0.5 appears in episode JSON as `OntologyAnalysis` in the investigation_trace
5. Check that short-circuit skips are logged when RAN/transport failures detected
6. Verify GUI at `http://localhost:8073` can run v5 investigations
