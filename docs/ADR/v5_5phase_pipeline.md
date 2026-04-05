# ADR: Agentic Ops v5 — 5-Phase Pipeline with Merged Network Analyst

**Date:** 2026-04-04
**Status:** Accepted
**Supersedes:** `v5_6phase_pipeline.md`

---

## Decision

Merge the former `TriageAgent` (Phase 1 — data collection) and `AnomalyDetectorAgent` (Phase 3 — ontology-guided analysis) into a single **`NetworkAnalystAgent`** that runs as the new Phase 1. The pipeline contracts from 6 phases to 5.

The new agent:
1. Collects network state via mandatory tool calls (topology, status, metrics, DP quality gauges)
2. Compares observations against ontology baselines and stack rules
3. Rates each layer (infrastructure, RAN, core, IMS) with evidence
4. Identifies suspect components and writes a directional investigation hint

Its output is a **structured Pydantic model** (`NetworkAnalysis`) enforced via ADK's `output_schema`. Downstream phases consume this structured assessment instead of loose markdown text.

## Context

The 6-phase v5 pipeline (`v5_6phase_pipeline.md`) separated data collection (TriageAgent) from anomaly analysis (AnomalyDetectorAgent) on architectural purity grounds: "one agent collects, one agent reasons." In practice, three problems emerged:

### Problem 1: Persistent ADK output_key crashes

The `AnomalyDetectorAgent` frequently produced no output at all, leaving `state["anomaly_analysis"]` as `None`. Downstream phases referencing `{anomaly_analysis}` in their instruction template crashed with `KeyError: Context variable not found: 'anomaly_analysis'`, halting the entire investigation.

Root cause (documented in `docs/bugs/adk_output_key_thinking_mode.md`): ADK's `LlmAgent.__maybe_save_output_to_state` filters out `part.thought` when writing `output_key` (added by [google/adk-python#976](https://github.com/google/adk-python/issues/976)). When Gemini 2.5 Flash responds with only thought-tagged parts — which happens when the model reaches a conclusion without calling any tools — the filter produces an empty result and the state key is left unset.

Empirical pattern across failed runs:
- **Succeeded**: AnomalyDetector made 12 tool calls → real text response → `output_key` written
- **Failed**: AnomalyDetector made 0 tool calls → thought-only response → `output_key` null → pipeline crash

### Problem 2: Expensive duplication between phases

When the AnomalyDetector did produce output, it re-collected the same data the TriageAgent had already gathered. One successful run burned **211,061 tokens** in the AnomalyDetector alone, with 12 tool calls to fetch metrics TriageAgent had fetched 30 seconds earlier. ADK sessions don't share tool results between phases — only `output_key` text passes through — so every phase that wants to reason about metrics must re-fetch them.

### Problem 3: Pattern matching on uninterpreted data

The PatternMatcher (Phase 2 in the old pipeline) ran between Triage and AnomalyDetector. It tried to match failure signatures against raw metric observations before any interpretation had happened. This is strictly harder than matching against pre-digested findings like "IMS layer is YELLOW because Diameter cdp:timeout is 5 at I-CSCF."

### Why this wasn't a problem in v2/v3/v4

v4 faced the same ADK thinking-mode behavior but degraded gracefully because its downstream prompts used the `?` suffix for cross-phase variables (e.g., `{finding_ims?}`). ADK's template resolver replaces optional-missing variables with empty string instead of raising. v5 adopted mandatory variables (no `?` suffix), which exposed the latent ADK bug as a hard crash.

## The 5-Phase Pipeline

```
Phase 1: NetworkAnalystAgent     (LlmAgent, Pydantic output_schema)  → state["network_analysis"]
Phase 2: PatternMatcherAgent     (BaseAgent, deterministic)          → state["pattern_match"]
Phase 3: InstructionGeneratorAgent (LlmAgent)                        → state["investigation_instruction"]
Phase 4: InvestigatorAgent       (LlmAgent, multi-layer tools)       → state["investigation"]
Phase 5: SynthesisAgent          (LlmAgent, no tools)                → state["diagnosis"]
```

### Phase 1: NetworkAnalystAgent

**Model:** `gemini-2.5-pro` (higher reasoning capacity for combined collection + analysis)

**Tools (10 total):**
- Data collection: `get_network_topology`, `get_network_status`, `get_nf_metrics`, `get_dp_quality_gauges`
- Ontology comparison: `compare_to_baseline`, `check_stack_rules`, `check_component_health`, `get_causal_chain_for_component`, `interpret_log_message`
- Environment: `read_env_config`

**Prompt enforces four mandatory steps:**
1. **Collect** — must call all four data-collection tools
2. **Compare to baselines** — must call `compare_to_baseline` and `check_stack_rules`
3. **Rate each layer** — GREEN/YELLOW/RED for infrastructure, RAN, core, IMS, with evidence for anything non-GREEN
4. **Identify suspects** — list suspect components with confidence and reason, plus a 1-3 sentence investigation hint

**Output schema** (`agentic_ops_v5/models.py`):

```python
class LayerRating(str, Enum):
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"

class LayerStatus(BaseModel):
    rating: LayerRating
    evidence: list[str]         # required for YELLOW/RED
    note: str

class SuspectComponent(BaseModel):
    name: str                   # container name
    confidence: str              # low | medium | high
    reason: str                  # concrete evidence

class NetworkAnalysis(BaseModel):
    summary: str
    layer_status: dict[str, LayerStatus]  # keys: infrastructure, ran, core, ims
    suspect_components: list[SuspectComponent]
    investigation_hint: str
    tools_called: list[str]
```

### Structured output + tools: how it works

Gemini's `response_schema` mode is normally mutually exclusive with `tools`. ADK 1.28.1 handles this via `_output_schema_processor.py`: when both are set, it injects a synthetic `set_model_response` tool whose parameters match the schema, plus an instruction telling the model to "use other tools as needed, then call `set_model_response` with your final answer." The model can call diagnostic tools freely and then emit the structured result as a tool call. ADK intercepts the `set_model_response` call and converts it to a normal model response event whose text is the schema-validated JSON.

### Phase 2: PatternMatcherAgent (unchanged)

Pure `BaseAgent` that collects observations directly from tools and queries the ontology's signature matcher. No LLM. Unchanged from the 6-phase version — it doesn't reference any upstream agent output in a prompt, so the phase reorder has no impact on it.

With the reorder, the PatternMatcher now sees the Network Analyst's interpreted assessment via `state["network_analysis"]` instead of having to match signatures against raw metrics. This gives it more reliable input for future enhancements.

### Phases 3, 4, 5: Instruction Generator, Investigator, Synthesis (unchanged structure)

All three were updated to reference `{network_analysis}` instead of `{triage}` + `{anomaly_analysis}`. Their internal logic is unchanged. Prompts are simpler because they now read one structured assessment instead of two loose markdown blobs.

## Why This Works

### 1. The ADK thinking-mode bug stops triggering in practice

The NetworkAnalystAgent's prompt makes five tool calls mandatory. The model physically cannot skip to a conclusion without calling tools. Once tools are called, the flow is: *tool call → tool response → follow-up LLM call → final text response*. That final response goes through the regular (non-thought) path and is properly written to `output_key`. The bug is still there in ADK, but our agent no longer exercises it.

### 2. Token cost drops substantially

The old pipeline re-fetched network state in both TriageAgent and AnomalyDetectorAgent because ADK sessions don't share tool results across phases. One run hit 211,061 tokens in AnomalyDetector alone. The merged agent fetches once and reasons about the same context, cutting Phase 1+3 token costs by an estimated 30-50%.

### 3. Pattern matching gets better input

The PatternMatcher now runs after a layer-rated assessment is in state. Future enhancements can match signatures against interpreted findings (e.g., "Core is RED with evidence including ran_ue=0") instead of raw metric dumps.

### 4. Failures degrade gracefully

When PostgresAI's downstream phases fail to find data they expected, they no longer crash on a missing key. The merged agent's schema guarantees all four layer keys are present, and the structured output means downstream templates have stable field references.

### 5. Better evaluation story

A layer status report with evidence is testable. Ground truth (from chaos scenarios) directly maps to expected layer ratings. You can now score "did the analyst correctly identify which layer is degraded?" as a standalone metric, without waiting for the full pipeline to finish.

## Trade-offs and Risks

### Single point of failure

If the NetworkAnalystAgent fails, the pipeline loses both data collection and analysis. Mitigation: the orchestrator wraps Phase 1 in try/except and falls back to a descriptive placeholder in `state["network_analysis"]` rather than crashing.

### Larger prompt, more cognitive load

Asking one agent to both collect and analyze may cause rushed analysis on either side. Mitigation: the prompt is structured as four explicit steps with mandatory tool calls per step. The model cannot skip steps without violating explicit prompt instructions.

### Structured output adds a failure mode

If the model emits malformed JSON via `set_model_response`, ADK's schema validator raises. Mitigation: Pydantic's error messages are specific enough that retry logic (future work) can guide the model to fix its output.

### Loss of phase-level specialization

The v5 6-phase architecture followed a "one job per agent" principle. Merging blurs this. Counter-argument: the split was artificial — data collection and analysis are inherently intertwined, and separating them into two agents forced expensive data re-fetching with no reasoning benefit.

## Files Changed

**New files:**
- `agentic_ops_v5/subagents/network_analyst.py` — merged agent factory
- `agentic_ops_v5/prompts/network_analyst.md` — four-step mandatory workflow prompt

**Modified files:**
- `agentic_ops_v5/models.py` — added `NetworkAnalysis`, `LayerStatus`, `LayerRating`, `SuspectComponent`
- `agentic_ops_v5/orchestrator.py` — 5-phase pipeline, Phase 1 calls `create_network_analyst()`
- `agentic_ops_v5/prompts/instruction_generator.md` — references `{network_analysis}` + `{pattern_match}`
- `agentic_ops_v5/prompts/investigator.md` — references `{network_analysis}` + `{pattern_match}` + `{investigation_instruction}`
- `agentic_ops_v5/prompts/synthesis.md` — references `{network_analysis}` + `{pattern_match}` + `{investigation_instruction}` + `{investigation}`
- `agentic_chaos/agents/challenger.py` — passes `network_analysis` through to episode results
- `agentic_chaos/recorder.py` — episode report shows Network Analysis (Phase 1) section

**Deleted files:**
- `agentic_ops_v5/subagents/triage.py`
- `agentic_ops_v5/subagents/anomaly_detector.py`
- `agentic_ops_v5/prompts/triage.md`
- `agentic_ops_v5/prompts/anomaly_detector.md`

## Alternatives Considered

1. **Add `?` to v5 cross-phase variables** (like v4 did). Would stop the crashes but not fix the underlying problem — the AnomalyDetector would still sometimes produce no output, just silently instead of loudly. Analysis quality would degrade without anyone noticing. Rejected.

2. **Disable thinking on all v5 agents** (`thinking_budget=0`). Would prevent the ADK bug from triggering but gives up the reasoning benefits of Gemini 2.5 thinking mode on every agent. Degrades quality to work around a framework bug. Rejected.

3. **Extract output from event stream on failure** (what the orchestrator currently does as a safety net). Partially mitigates the symptom but doesn't address the duplication problem or the pattern-matching-on-raw-data problem. Kept as a defense-in-depth mechanism.

4. **Keep the 6-phase structure, strengthen AnomalyDetector prompt** to mandate tool calls. Would fix the thinking-only failure mode but keeps the expensive data re-fetching between phases. Rejected.

5. **Merge (chosen).** Addresses all three problems simultaneously: eliminates the thinking-mode trigger, removes duplication, and feeds interpreted data to the pattern matcher.

## Follow-ups

- File the ADK thinking-mode bug upstream (draft ready at `/tmp/adk_issue/issue.md`). The merged pipeline sidesteps the bug in practice, but the framework-level fix is still worth pursuing.
- Measure actual token savings and quality on the next set of chaos scenarios. If the merged agent regresses on accuracy, revisit step 4 in "Alternatives Considered."
- Consider adding a `?` suffix defensively on `{network_analysis}` references in downstream prompts as a belt-and-suspenders safety net, even though the structured schema should guarantee the field exists.
