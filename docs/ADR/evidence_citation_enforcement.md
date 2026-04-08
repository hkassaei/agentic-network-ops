# ADR: Mandatory Evidence Citations and Validator Enforcement

**Date:** 2026-04-08
**Status:** Implemented
**Related episodes:**
- `agentic_ops_v5/docs/agent_logs/run_20260408_015734_p_cscf_latency.md` — EvidenceValidator produced no output (evidence_validation=None)
- `agentic_ops_v5/docs/agent_logs/run_20260408_030826_p_cscf_latency.md` — Investigator made 4 tool calls but ZERO [EVIDENCE:] citations; validator said "clean"
- `agentic_ops_v5/docs/agent_logs/run_20260408_034713_p_cscf_latency.md` — Investigator cited 10 evidence items, all verified (fix confirmed working)

## Context

Three related problems surfaced across consecutive runs:

### Problem 1: Evidence Validator output was not reaching the episode report

The EvidenceValidatorAgent ran and produced correct output, but the ChallengerAgent did not capture `evidence_validation` from the v5 result dict. It only passed `_network_analysis`, `_pattern_match`, and `_investigation_instruction` — the evidence validation was silently dropped.

### Problem 2: Investigator wrote narratives without formal citations

The Investigator made 4+ tool calls but wrote a flowing narrative instead of using the required `[EVIDENCE: tool_name(args) -> "output"]` format. The Evidence Validator found 0 Investigator citations and returned `verdict: clean, confidence: medium` — because "no citations to be unmatched" was treated as "no fabrications found."

### Problem 3: Investigator misinterpreted 2000ms RTT as "healthy"

When the Investigator did run `measure_rtt`, it saw 2000ms RTT and concluded "transport is healthy, connectivity confirmed." It didn't understand that 2000ms on a Docker bridge (normal: <1ms) is catastrophic for SIP.

## Decision

### Fix 1: Plumb evidence_validation through the challenger

Added `_evidence_validation` to the dict returned by `_run_adk_agent()` and `evidence_validation` to the `challenge_result`. Added "Evidence Validation (Phase 5)" section to the episode markdown report.

### Fix 2: Enforce minimum citations in Investigator prompt

Updated `investigator.md`:
- Changed header to "Evidence Rules (MANDATORY — violations cause automatic downgrade)"
- Added: "An automated Evidence Validator runs after you. It cross-references every [EVIDENCE:] citation against the actual tool-call log."
- Added minimum citation requirement: "You MUST produce at least 3 [EVIDENCE:] citations"
- Added: "If you called tools but didn't cite them, your investigation is useless — downstream agents cannot see your tool results, only your citations"

### Fix 3: Update Evidence Validator to detect zero-citation investigations

Updated `_determine_confidence_and_verdict()`:
- New case: `investigator_tool_calls > 0` but `investigator_citations == 0` → `has_warnings`, `low` confidence (was: `clean`, `medium`)
- Summary now warns: "InvestigatorAgent made N tool calls but produced ZERO [EVIDENCE:] citations. The investigation narrative is unverifiable."

### Fix 4: Detailed tool-to-citation mapping in validator output

The validator summary now includes a "Tool calls vs. citations" section:
```
  InvestigatorAgent:
    ✓ measure_rtt — called AND cited (1x)
    ✗ check_process_listeners — called but NOT cited in output
```

Plus a "Fabricated citations" section for any citations about tools never called.

### Fix 5: RTT interpretation guidance

Added to `investigator.md`: "Normal Docker bridge RTT is <1ms. RTT >10ms is ABNORMAL. RTT of 2000ms is CATASTROPHIC — sufficient to explain all SIP/Diameter/HTTP timeouts. Do not dismiss elevated RTT as 'connectivity is healthy.'"

## Files changed

- `agentic_chaos/agents/challenger.py` — pass `_evidence_validation` and `evidence_validation` through
- `agentic_chaos/recorder.py` — render "Evidence Validation (Phase 5)" section in episode markdown
- `agentic_ops_v5/prompts/investigator.md` — enforcement language, minimum citations, RTT interpretation
- `agentic_ops_v5/subagents/evidence_validator.py` — zero-citation detection, tool-to-citation mapping

## Verification

Unit tested three scenarios:
- 4 tool calls, 0 citations → `has_warnings`, `low` confidence (was `clean`, `medium`)
- 1 tool call, 1 matched citation → `clean`, `high`
- 0 tool calls → `severe`, `none`

Confirmed working in `run_20260408_034713`: 10/10 citations verified, tool mapping shown.
