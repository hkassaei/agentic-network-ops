# ADR: EvidenceValidatorAgent — Machine-Checked Fact-Checking in the v5 Pipeline

**Date:** 2026-04-05
**Status:** Accepted
**Related:**
- Critical observation: [`docs/critical-observations/run_20260405_043504_p_cscf_latency.md`](../critical-observations/run_20260405_043504_p_cscf_latency.md) (Issue 3)
- Companion ADRs:
  - [`data_plane_idle_stack_rule.md`](data_plane_idle_stack_rule.md) (addresses Issue 1 from the same critical observation)
  - [`upf_counters_directional_stack_rule.md`](upf_counters_directional_stack_rule.md) (addresses Issue 2)
- Part of the v5 pipeline defined in: [`v5_5phase_pipeline.md`](v5_5phase_pipeline.md) (now obsolete — this ADR expands the pipeline to 6 phases)

---

## Decision

Add a new deterministic `BaseAgent` named `EvidenceValidatorAgent` as **Phase 5** of the v5 Ops agent pipeline, between the `InvestigatorAgent` and the `SynthesisAgent`. Its job is to cross-check every evidence claim produced by the upstream LLM phases (`NetworkAnalystAgent` and `InvestigatorAgent`) against the actual tool-call log recorded by the orchestrator. It produces a machine-computed verdict and confidence level that the downstream `SynthesisAgent` is required to honor.

The v5 pipeline becomes **6 phases**:

```
1. NetworkAnalystAgent        (LLM — produces layer assessment with evidence strings)
2. PatternMatcherAgent        (BaseAgent — deterministic signature match)
3. InstructionGeneratorAgent  (LLM — produces investigation mandate)
4. InvestigatorAgent          (LLM — produces evidence-backed findings)
5. EvidenceValidatorAgent     (BaseAgent, NEW — cross-checks claims against tool traces)
6. SynthesisAgent             (LLM — reads validation verdict and produces final diagnosis)
```

The validator:

- **Does not call an LLM.** Pure deterministic text processing: regex extraction + set membership checks against the phase trace list.
- **Does not block** Synthesis. The pipeline always runs to completion. The validator only adjusts the `confidence` and disclosure of the final diagnosis.
- **Validates both LLM phases**: NetworkAnalyst evidence strings and Investigator `[EVIDENCE: tool(args) -> "..."]` citations, in a single pass.
- **Uses strict exact-name matching** for tool names. Fuzzy matching was considered and rejected for the first version as too permissive.
- **Detects the zero-tool-calls failure mode** (`investigator_made_zero_calls: True`) as a first-class signal, separately from citation mismatches.

The `SynthesisAgent` prompt template is updated to read the validation result from session state and route through one of four mandatory branches (`clean` / `has_warnings` / `severe` / `investigator_made_zero_calls`), each with explicit rules for what the final diagnosis must look like.

## Context

On 2026-04-05, the v5 agent ran a P-CSCF latency chaos scenario and produced a diagnosis that contained **fabricated evidence citations** with high confidence. Full episode and post-run analysis captured in [`docs/critical-observations/run_20260405_043504_p_cscf_latency.md`](../critical-observations/run_20260405_043504_p_cscf_latency.md) as Issue 3 — flagged by the analyst as *"the most serious failure in the run."*

Phase breakdown from the failing episode:

| Phase | Tokens | Tool Calls | LLM Calls |
|---|---|---|---|
| NetworkAnalystAgent | 28,473 | 8 | 3 |
| PatternMatcherAgent | 0 | 0 | 0 |
| InstructionGeneratorAgent | 5,776 | 0 | 1 |
| **InvestigatorAgent** | **7,723** | **0** | **1** |
| SynthesisAgent | 7,632 | 0 | 1 |

The `InvestigatorAgent` consumed 7,723 tokens in a single LLM call and made **zero** tool calls. Its prompt explicitly stated *"Every claim must cite a tool output"* and required evidence citations in the `[EVIDENCE: tool(args) -> "..."]` format. Yet the Investigator generated text containing these citations:

- `[EVIDENCE: read_container_logs(container="upf", ...) -> "tx_send(): No buffer space available"]`
- `[EVIDENCE: measure_rtt(...) -> "50% packet loss, time 1004ms"]`

**Neither tool was called.** The citations were fabricated. The LLM generated plausible-looking evidence strings to support a diagnosis it had already formed from the upstream NetworkAnalyst context, without doing any actual verification. The `SynthesisAgent` then produced a final diagnosis citing these fabrications, ultimately recommending *"restart Docker / reboot the host"* — a remediation completely unrelated to the actual P-CSCF latency fault.

Fabricated evidence is **strictly worse than a wrong diagnosis**. A NOC engineer reading the episode report would have no visible signal that the citations are fictional and would likely act on the recommendation. In a production incident, this could cause real damage.

### Why prompt warnings alone cannot fix this

This is a fundamental property of autoregressive LLMs, not a failure of prompt engineering:

1. **LLMs optimize for plausible continuations, not correctness.** When the context already contains a coherent narrative (from the upstream NetworkAnalyst + InstructionGenerator phases), generating more of the same narrative is the lowest-resistance path. Tool-calling is just one action in the LLM's decision space; text generation is another. The LLM picks whichever produces the more plausible continuation, and a strong upstream narrative biases it toward "just complete the story."

2. **Context pressure defeats early instructions.** The Investigator's prompt says "every claim must cite a tool output," but that instruction appears at the top of a long prompt that also contains the NetworkAnalyst's detailed assessment and the InstructionGenerator's pre-digested conclusion. Under generation pressure, the LLM prioritizes the local context (the narrative) over the global instruction (cite real tools).

3. **The LLM has no concept of "real vs fake tool call" at the generation level.** To the LLM, `[EVIDENCE: read_container_logs(...) -> "..."]` is just a string. It doesn't distinguish between a string it produced because a tool actually returned that output vs. a string it produced because the pattern completion suggested it. That distinction only exists in the orchestrator's event log, which the LLM cannot see.

4. **This failure mode has a name: narrative hallucination** (also called "sycophantic completion"). It's well-documented in multi-agent systems where downstream agents receive pre-digested context from upstream agents. The stronger and more coherent the upstream narrative, the more likely the downstream LLM is to skip actual work and ride the narrative.

The Investigator's prompt has been tightened before. Additional warnings produced no measurable improvement. The failing episode is the empirical proof that prompt-level constraints are not sufficient for this class of failure. Any fix that depends on the LLM "following instructions reliably" will eventually fail in the same way. For a safety-critical application — and production RCA for a live 5G network is safety-critical — we need enforcement outside the LLM.

### Why production portability matters for this decision

The chaos testing framework is **one** trigger path for the v5 Ops agent. In production, the agent will be invoked from:

- The GUI's `/investigate` page, when an operator notices a symptom
- An alertmanager webhook, when a Prometheus alert fires
- Other automation (cron, external orchestrators)

Each of those triggers should automatically get evidence validation without needing to wire it up. If validation lived in the chaos framework (my initial design proposal), every other caller would silently miss the safety check and the fabricated-evidence failure mode would reach production unfiltered.

The validator must be part of the v5 Ops agent's own pipeline — a first-class phase that runs every time `agentic_ops_v5.orchestrator.investigate()` is called, regardless of who called it. Quality control for the agent's own output is an agent-level concern, not a test-framework concern.

## Design

### Shape: deterministic BaseAgent, not a utility function

My first draft positioned the validator as a pure Python function called from both the chaos framework's recorder and (optionally) the orchestrator. That design was rejected because:

- It required every caller to remember to invoke the validator, violating the "safety by default" principle
- It split the validation logic between the Ops agent and external consumers, making the agent's self-reporting incomplete
- It did not integrate with ADK's phase trace, so the validation result was not visible in the agent's own output stream

The revised design makes the validator a `BaseAgent` that runs as a proper phase in the v5 sequential pipeline. Same shape as `PatternMatcherAgent` and `FaultPropagationVerifier` (both are deterministic BaseAgents with no LLM call). It participates in the ADK event loop, writes its output to session state, and becomes visible in the phase trace just like any other agent. Every caller of `investigate()` gets it automatically.

### Placement: after Investigator, before Synthesis

A single validator phase positioned between Phase 4 (Investigator) and Phase 6 (Synthesis) validates everything both LLM phases have produced in one pass:

- **NetworkAnalyst's structured evidence strings** in `layer_status[layer].evidence` and `suspect_components[].reason`
- **Investigator's formal `[EVIDENCE: tool(args) -> "..."]` citations** in the free-form investigation text

Running it once (instead of twice — after NetworkAnalyst and after Investigator) was a deliberate choice. NetworkAnalyst's evidence is relatively low-risk because its output is structured Pydantic and constrained to values the agent actually computed. The Investigator is the high-risk phase — that's where the fabrication happened. One validator pass after the Investigator covers both phases' outputs without doubling the trace complexity.

### Running BEFORE Synthesis is critical

This is the load-bearing design decision. If the validator ran AFTER Synthesis, the hallucinated citations would already be baked into the final text — we could only attach warnings to an already-corrupted output.

By running BEFORE Synthesis, the validation verdict goes into session state as `state["evidence_validation"]` and `state["investigator_confidence"]`. The Synthesis prompt template references `{evidence_validation}` and reads the verdict as mandatory input. Synthesis then produces a diagnosis whose confidence matches the machine-checked verdict — it cannot rationalize around a `severe` verdict because the prompt's branching logic is explicit.

This turns the validator from a post-hoc critique into a **signal the agent uses to self-regulate its own confidence**. The final diagnosis is aware of its own reliability.

### The validator's outputs

`EvidenceValidationResult` Pydantic model with nine fields:

```python
class EvidenceValidationResult(BaseModel):
    total_citations: int
    matched: int
    unmatched: int
    network_analyst_claims: list[ClaimCheck]
    investigator_claims: list[ClaimCheck]
    investigator_tool_call_count: int
    investigator_made_zero_calls: bool
    investigator_confidence: str  # high | medium | low | none
    verdict: str                   # clean | has_warnings | severe
    summary: str                   # human-readable, for the episode report

class ClaimCheck(BaseModel):
    raw_text: str        # the original claim or citation string
    claimed_tool: str    # tool name extracted from the claim
    source_phase: str    # NetworkAnalystAgent or InvestigatorAgent
    matched: bool
    match_reason: str    # plain-English explanation of the match/mismatch
```

The verdict/confidence mapping is deterministic and based on the unmatched ratio:

| Condition | investigator_confidence | verdict |
|---|---|---|
| `investigator_tool_call_count == 0` | `none` | `severe` |
| `total_citations == 0` (no claims to validate) | `medium` | `clean` |
| `unmatched == 0` | `high` | `clean` |
| `unmatched / total <= 25%` | `medium` | `has_warnings` |
| `unmatched / total <= 50%` | `low` | `has_warnings` |
| `unmatched / total > 50%` | `none` | `severe` |

The zero-tool-calls check is the first rule and takes priority over everything else. An Investigator that didn't call any tools is always `severe` regardless of what its text claims.

### Claim extraction

Two regex extractors handle the two different LLM output formats:

**Investigator format** — formal citation:
```
\[EVIDENCE:\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\(([^)]*)\)\s*->\s*(.+?)\]
```
Matches `[EVIDENCE: tool_name(args) -> "excerpt"]`. Extracts the tool name (group 1).

**NetworkAnalyst format** — evidence strings in structured Pydantic output:
```
(?:from|via|per|using|\()\s*(get_[a-zA-Z_]+|check_[a-zA-Z_]+|compare_[a-zA-Z_]+|read_[a-zA-Z_]+|query_[a-zA-Z_]+|measure_[a-zA-Z_]+)
```
Matches patterns like `"ran_ue=0 from get_nf_metrics"` or `"... (get_dp_quality_gauges)"`. Extracts the tool name (group 1). Narrower than the Investigator regex because NA output is structured strings, not free-form text — constrained to known tool name prefixes to avoid false matches.

Both extractors produce `(raw_text, tool_name)` tuples that flow into the same validation loop.

### Cross-reference against phase traces

The orchestrator maintains `state["phase_traces_so_far"]` — a serialized list of `PhaseTrace` dicts, appended after every phase runs. Each phase trace contains an `agent_name` and a `tool_calls` list. The validator builds `{phase_name: {tool_names...}}` from this, then checks each extracted claim against the set of tools actually called in its source phase.

**Strict exact-name matching**: `claimed_tool == tool_name` is the only match criterion. No fuzzy matching, no substring matching. If the Investigator cites `read_container_logs` but its phase trace only contains `measure_rtt`, the claim is unmatched.

This is strict enough to catch all the failing cases (which are egregious — a whole tool invented from scratch) without producing false positives on partial matches. If empirical evidence later shows strict matching is too tight, the threshold can be tuned.

### How Synthesis honors the verdict

The `synthesis.md` prompt template gains a new **"Confidence Adjustment Based on Evidence Validation (MANDATORY)"** section with four explicit branches:

**`verdict: clean`** → Normal confident diagnosis. `confidence: high` allowed.

**`verdict: has_warnings`** → Mark unverified claims explicitly, omit unmatched citations from the timeline, add a caveat in the explanation. `confidence: medium` at most.

**`verdict: severe`** → MANDATORY structure:
- `summary: "The investigation did not produce verifiable evidence. Manual investigation is required."`
- `timeline: []` (no fabricated sequence)
- `root_cause: "Unknown — the automated investigation could not verify its own findings."`
- `affected_components`: only the Network Analyst's suspects (pre-validation, still usable)
- `recommendation`: Manual investigation starting from the NA's suspect list
- `confidence: low`
- `explanation`: Must include the specific counts — *"The Investigator produced [N] evidence citations, of which [M] could not be verified. The Investigator made [K] actual tool calls."*

**`investigator_made_zero_calls: true`** → Same as `severe`, with additional explicit disclosure: *"The Investigator agent produced no tool calls — any evidence citations in its output are fabricated."*

The prompt explicitly forbids Synthesis from rationalizing around the verdict: *"Do not 'upgrade' the confidence because the narrative sounds coherent — the narrative may be fabricated."*

### Graceful degradation when the validator itself crashes

The orchestrator wraps the EvidenceValidator phase in try/except. If the validator raises an exception (e.g., malformed phase trace data), the orchestrator writes a fallback `severe`/`none` verdict into state and continues. Synthesis still runs, sees the severe verdict via its prompt template, and produces the low-confidence output. The pipeline never crashes; the agent fails safe.

## Verification

Unit-tested against three distinct scenarios:

### Test 1 — The failing episode reproduced
Inputs: NetworkAnalyst's actual evidence strings (3 legitimate tool references, all matched against NA's real 7-tool call trace) and Investigator text containing two fabricated `[EVIDENCE: ...]` citations, with an Investigator phase trace showing `tool_calls: []`.

Result:
```
total_citations: 5
matched: 3
unmatched: 2
investigator_tool_call_count: 0
investigator_made_zero_calls: True
verdict: severe
investigator_confidence: none
```
Summary output:
```
⚠️ CRITICAL: InvestigatorAgent made ZERO tool calls — no actual verification was performed.
Evidence validation: 3/5 citations verified (2 unmatched).
Verdict: severe. Investigator confidence: none.
Unmatched citations (sample):
  - [InvestigatorAgent] claimed 'read_container_logs' — tool 'read_container_logs' NEVER called in InvestigatorAgent trace — fabricated
  - [InvestigatorAgent] claimed 'measure_rtt' — tool 'measure_rtt' NEVER called in InvestigatorAgent trace — fabricated
```

### Test 2 — Clean run
Investigator cites two tools that were actually called. Phase trace contains both. Result: `verdict: clean`, `confidence: high`, 2/2 matched.

### Test 3 — Mixed run (fabrication majority)
Investigator cites three tools. Only one was actually called; two are fabricated. Result: `verdict: severe`, `confidence: none`, 1/3 matched (>50% unmatched ratio correctly escalates to severe).

All three scenarios produce the correct verdict and confidence. The failing episode's exact input now produces a `severe`/`none` result that would trigger Synthesis's mandatory manual-investigation branch, preventing the fabricated "restart Docker" recommendation from reaching a user.

## Files Changed

**New files:**
- `agentic_ops_v5/subagents/evidence_validator.py` — `EvidenceValidatorAgent` (BaseAgent), `EvidenceValidationResult` and `ClaimCheck` Pydantic models, pure `validate()` function, two regex extractors, cross-reference logic, and the `_determine_confidence_and_verdict()` deterministic mapping.

**Modified files:**
- `agentic_ops_v5/orchestrator.py`:
  - Imports `create_evidence_validator`
  - New helper `_accumulate_phase_traces()` that serializes and appends `PhaseTrace` objects to `state["phase_traces_so_far"]` after every phase
  - Pipeline expanded from 5 to 6 phases; EvidenceValidator inserted between Investigator and Synthesis
  - Validator phase wrapped in try/except with a graceful `severe`/`none` fallback
  - Final `result` dict exposes `evidence_validation` and `investigator_confidence` alongside the existing fields
- `agentic_ops_v5/prompts/synthesis.md`:
  - New `{evidence_validation}` reference in the phase-output header
  - New **"Confidence Adjustment Based on Evidence Validation (MANDATORY)"** section with four explicit branches
  - The `severe` branch dictates an exact structured response with empty timeline, unknown root cause, low confidence, and manual-investigation recommendation
  - Explicit instruction not to rationalize around the verdict

## How This Plays In Production

When `agentic_ops_v5.orchestrator.investigate()` is called — from the chaos framework, from the GUI's `/investigate` page, from a future alertmanager webhook, or from any other automation — the EvidenceValidator runs automatically as Phase 5. The caller does not need to know it exists. The result dict always includes `evidence_validation` and `investigator_confidence`, so any downstream consumer (GUI display, episode recorder, alert integration) can read and surface them.

The chaos testing framework benefits from this because the scorer now has access to a self-reported confidence signal it can cross-reference with its ground-truth score. But the chaos framework required **zero changes** to receive this benefit. Validation is part of the Ops agent's own quality process.

In the failing episode scenario, the final user-visible diagnosis would have been:

> **Summary:** The investigation did not produce verifiable evidence. Manual investigation is required.
>
> **Root cause:** Unknown — the automated investigation could not verify its own findings.
>
> **Recommendation:** Manual investigation required. Start from the Network Analyst's suspect list and verify each component's state with direct tool calls: measure_rtt, check_process_listeners, read_container_logs, read_running_config. Do not act on the Investigator's unverified claims without independent verification.
>
> **Confidence:** low
>
> **Explanation:** [NA's observations, followed by:] The Investigator produced 2 evidence citations, of which 2 could not be verified against real tool calls. The Investigator made 0 actual tool calls. This diagnosis has been downgraded to low confidence because the investigation phase did not produce reliable evidence. The Investigator agent produced no tool calls — any evidence citations in its output are fabricated. A human operator should investigate manually before taking action.

The fabricated "restart Docker / reboot the host" recommendation would never reach the user.

## Alternatives Considered

1. **Prompt tightening on the Investigator alone.** Rejected. The Investigator prompt already said "every claim must cite a tool output" when the failing episode occurred. Additional emphasis, CAPS, or mandatory language would have diminishing returns. Prompt constraints are soft and stochastic generation can violate them under context pressure. The failing episode is empirical proof that this approach has a tail.

2. **Pure validator function called from the chaos recorder.** Rejected (my initial design). Couples validation to one specific trigger path. Production invocations from the GUI or alert webhooks would silently miss the safety check. Validation must be an Ops-agent-level concern, not a test-framework-level concern.

3. **Validator as a tool the Investigator or Synthesis can call.** Rejected. A tool is optional — the LLM can choose not to call it, which defeats the purpose. A pipeline phase runs unconditionally.

4. **Running the validator in two places** (after NetworkAnalyst, and after Investigator). Rejected as over-engineering for the first version. NetworkAnalyst's structured output is lower-risk and a single post-Investigator validation pass covers both phases' claims adequately. Can be split into two phases later if needed.

5. **Running the validator AFTER Synthesis** (post-hoc critique). Rejected. By the time Synthesis finishes, fabricated citations are already baked into the final diagnosis. A post-hoc warning cannot un-corrupt the output — it can only attach a disclaimer to something already written. Running BEFORE Synthesis turns the validator into a signal Synthesis can act on, which is strictly more useful.

6. **Fuzzy tool name matching** (substring, Levenshtein distance). Rejected for the first version. The failing cases are egregious (tools invented from scratch), so strict matching catches them cleanly. Fuzzy matching would risk false positives on partial matches. Can be tuned later if empirical evidence shows strict matching is too tight.

7. **Retry the Investigator on `severe` verdict.** Considered, not implemented. A retry loop adds complexity, doubles token cost for the worst case, and is not needed to achieve the safety goal (graceful degradation with transparent low confidence is already sufficient). Retry logic can be added later as a separate enhancement.

8. **Block Synthesis entirely on `severe` verdict** (hard-stop behavior). Rejected in favor of always running Synthesis with mandatory low-confidence output. Users always want *some* diagnosis, even if it's explicitly unreliable. A hard stop would leave callers with no output to display and no clear path forward. The "produce a caveat-laden diagnosis" approach gives users actionable information while still preventing false confidence.

## Follow-ups

This ADR addresses **Issue 3** from the four-issue critical observation. Progress on the full list:

- ✅ **Issue 1** — Idle data plane misread as failure → addressed in [`data_plane_idle_stack_rule.md`](data_plane_idle_stack_rule.md).
- ✅ **Issue 2** — Cumulative counter subtraction → addressed in [`upf_counters_directional_stack_rule.md`](upf_counters_directional_stack_rule.md).
- ✅ **Issue 3** — Investigator zero tool calls and fabricated evidence → addressed in this ADR.
- ⬜ **Issue 4** — Scenario design: no signaling activity during the propagation window. Requires chaos-framework-level changes to trigger fresh SIP traffic during the `fault_propagation_time` wait, independent of the Ops agent itself.

Additional follow-ups specific to this ADR:

- **Evidence match quality beyond tool name.** Current validation checks only that the claimed tool name matches a real tool call. It does NOT check whether the claimed args match the real args, or whether the claimed output excerpt matches the real tool output. A more rigorous validator could extract and compare these, catching subtler hallucinations (e.g., the agent citing a real `measure_rtt` call but inventing the RTT value it returned). Adding this requires storing full tool outputs in the phase trace, not just tool names and sizes.
- **Consider expanding to v3 and v4.** The evidence validator logic is specific to v5's phase structure but the concept is general. If v3/v4 are still maintained, a similar phase could be added to each. Low priority — v5 is the active development line.
- **GUI surface for the validation verdict.** The validation result is now part of the `investigate()` return dict. The GUI's investigation pages could display a confidence badge (🟢 clean / 🟡 warnings / 🔴 severe) alongside the diagnosis. Currently only the raw diagnosis is shown.
- **Scoring integration in the chaos framework.** The chaos scorer currently evaluates diagnoses against ground truth. It could now also factor in the validation verdict — a `severe` verdict should correlate with a lower score, and a score discrepancy between ground truth and validation could surface bugs in either the agent or the scorer.
- **Parse Synthesis's own output for new hallucinations.** The current validator runs before Synthesis, so it catches NetworkAnalyst + Investigator hallucinations. Synthesis itself could theoretically introduce new fabricated citations when rewriting the diagnosis. A second validator pass after Synthesis (with the same logic) would catch this. Not observed in practice yet, but a reasonable belt-and-suspenders addition.
