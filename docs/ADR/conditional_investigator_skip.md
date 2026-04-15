# ADR: Conditional Skip of Phases 3+4 (Instruction Generator + Investigator)

**Date:** 2026-04-14
**Status:** Accepted
**Supersedes:** Partially supersedes [`evidence_validator_agent.md`](evidence_validator_agent.md) which defined the pipeline with mandatory Phases 3 and 4. The Evidence Validator itself remains mandatory — only the Investigator and its Instruction Generator are now conditionally skipped.
**Related:**
- [`evidence_validator_agent.md`](evidence_validator_agent.md) — defined the 6-phase pipeline with mandatory InstructionGenerator (Phase 3) and Investigator (Phase 4)
- [`agentic_ops_v5/docs/agent_logs/run_20260414_223317_gnb_radio_link_failure.md`](../../agentic_ops_v5/docs/agent_logs/run_20260414_223317_gnb_radio_link_failure.md) — episode where the Investigator fabricated 8 evidence citations with zero tool calls, despite the Network Analyst having already definitively diagnosed the fault

---

## Decision

Make Phases 3 (Instruction Generator) and 4 (Investigator) conditional. When the Network Analyst (Phase 1) produces a definitive diagnosis — high-confidence suspect with at least one RED layer — skip both phases and pass the Network Analyst's findings directly to Evidence Validation (Phase 5) and Synthesis (Phase 6).

The Evidence Validator always runs regardless, validating whatever evidence exists.

---

## Context

### The problem: redundant investigation on clear-cut failures

Across multiple chaos episodes, when the fault was unambiguous (container killed, 100% packet loss, process exited), the Network Analyst correctly identified the root cause in Phase 1 with high confidence and definitive evidence. The Investigator then ran and consistently did one of three things:

1. **Re-ran the same tools** and got the same results (redundant, wasted ~100K tokens)
2. **Produced zero output** due to ADK thinking-mode issues (wasted time, degraded confidence)
3. **Fabricated evidence citations** from the upstream narrative without calling any tools (hallucination caught by Evidence Validator, diagnosis downgraded to low confidence)

In the triggering episode (gNB Radio Link Failure), the Network Analyst found:
- gNB container exited (`get_network_status`)
- 100% packet loss to gNB (`measure_rtt`)
- `ran_ue=0`, `gnb=0` (`get_nf_metrics`)
- RAN layer rated RED, primary suspect `nr_gnb` with HIGH confidence

The Investigator made zero tool calls but produced 8 fabricated `[EVIDENCE: ...]` citations including invented log messages. The Evidence Validator caught all 8 as unmatched, downgraded confidence to low. The final diagnosis was correct in substance but reported as low confidence — the Investigator actively made the output worse.

### Cost of running the Investigator unnecessarily

| Metric | Investigator Run | Investigator Skipped |
|---|---|---|
| Tokens consumed | ~100-120K | 0 |
| Time added | ~100-200s | 0 |
| Risk of hallucination | High (when upstream narrative is strong) | None |
| Risk of zero output | Moderate (ADK thinking-mode bug) | None |
| Diagnostic value added | None (for clear-cut faults) | N/A |

---

## Design

### Skip conditions

Phases 3+4 are skipped when ALL of the following are true:

1. **Network Analyst produced a structured output** (not a failure string)
2. **At least one suspect component has `confidence: "high"`**
3. **At least one layer is rated `RED`**

These conditions capture "definitive diagnosis" — the Network Analyst found something clearly broken (RED) and is confident about which component is responsible (HIGH).

### When the Investigator still runs

- **No RED layer** (everything YELLOW or GREEN) — the fault is subtle, deeper investigation needed
- **No HIGH-confidence suspect** — the Network Analyst sees symptoms but isn't sure what's causing them
- **Network Analyst failed** — the output is an error string, not structured data

Examples where the Investigator is needed:
- P-CSCF latency: IMS is YELLOW, suspects are MEDIUM confidence
- Data plane degradation: symptoms spread across layers, no single clear cause
- Call quality degradation: RTPEngine metrics anomalous but component is running

Examples where the Investigator is skipped:
- gNB killed: RAN is RED, `nr_gnb` is HIGH confidence
- SMF crashed: Core is RED, `smf` is HIGH confidence  
- HSS unresponsive: IMS is RED, `pyhss` is HIGH confidence

### Pipeline flow

**Skip path:**
```
Phase 0: AnomalyScreener
Phase 1: NetworkAnalystAgent → HIGH suspect + RED layer detected
Phase 2: PatternMatcherAgent
Phase 3: SKIPPED (Instruction Generator)
Phase 4: SKIPPED (Investigator)
Phase 5: EvidenceValidatorAgent → validates Network Analyst's evidence
Phase 6: SynthesisAgent → uses Network Analyst's findings directly
```

**Full path:**
```
Phase 0: AnomalyScreener
Phase 1: NetworkAnalystAgent → no definitive diagnosis
Phase 2: PatternMatcherAgent
Phase 3: InstructionGeneratorAgent → generates investigation instructions
Phase 4: InvestigatorAgent → deep-dives into suspects
Phase 5: EvidenceValidatorAgent → validates both agents' evidence
Phase 6: SynthesisAgent → combines all findings
```

### Evidence Validator behavior

The Evidence Validator always runs regardless of whether the Investigator ran or was skipped. Its behavior adapts based on the `investigator_skipped` flag in session state:

**When the Investigator is skipped (`investigator_skipped=True`):**
- The orchestrator sets `state["investigator_skipped"] = True`
- The validator passes an empty string for `investigation_text` (no Investigator output to validate)
- Confidence is determined solely from the Network Analyst's evidence quality:
  - NA made ≥5 tool calls → `confidence: high`, `verdict: clean`
  - NA made <5 tool calls → `confidence: medium`, `verdict: has_warnings`
- `investigator_made_zero_calls` is NOT flagged (zero calls is expected, not a failure)
- Summary reads: "Investigator was intentionally skipped (Network Analyst diagnosis was definitive). Validating Network Analyst evidence only."
- No "⚠️ CRITICAL: zero tool calls" warning

**When the Investigator runs (`investigator_skipped=False`):**
- Behavior is unchanged from the existing ADR — validates both phases
- Zero tool calls from the Investigator IS flagged as a failure

**Example output when skipped:**
```
Investigator was intentionally skipped (Network Analyst diagnosis was definitive).
Network Analyst made 9 tool calls. Evidence validation: 2/2 NA citations verified.
Verdict: clean. Confidence: high.

Tool calls vs. citations:
  NetworkAnalystAgent:
    ✓ get_nf_metrics — called AND cited (1x)
    ✓ measure_rtt — called AND cited (1x)
    ✗ get_network_status — called but NOT cited in output
    ...
```

**Contrast with previous behavior (before this fix):**
```
⚠️ CRITICAL: InvestigatorAgent made ZERO tool calls — no actual verification was performed.
Evidence validation: 0/0 citations verified (0 unmatched). Investigator: 0 citations from 0 tool calls.
Verdict: has_warnings. Investigator confidence: low.
```

The old behavior incorrectly penalized the intentional skip as a failure, downgrading confidence to `low` even though the Network Analyst had definitive evidence from 9 tool calls.

---

## Files Changed

- `agentic_ops_v5/orchestrator.py` — added conditional skip logic before Phases 3+4; sets `state["investigator_skipped"] = True` when skipping; parses Network Analyst's structured output to check for HIGH-confidence suspects and RED layers; emits `phase_skip` events for GUI streaming
- `agentic_ops_v5/subagents/evidence_validator.py` — reads `investigator_skipped` from session state; adapts confidence determination and summary output for the skip case; does not flag `investigator_made_zero_calls` when skip was intentional

---

## Relationship to Evidence Validator ADR

The [`evidence_validator_agent.md`](evidence_validator_agent.md) ADR defined the pipeline as:

```
1. NetworkAnalystAgent
2. PatternMatcherAgent
3. InstructionGeneratorAgent
4. InvestigatorAgent
5. EvidenceValidatorAgent
6. SynthesisAgent
```

This ADR modifies phases 3 and 4 from mandatory to conditional. All other aspects of the Evidence Validator ADR remain in effect:
- The validator still runs after every investigation (or non-investigation)
- The `clean` / `has_warnings` / `severe` verdict system is unchanged
- The Synthesis prompt's mandatory branching on the verdict is unchanged
- The validator's regex-based citation extraction is unchanged
