# ADR: InstructionGenerator Must Respect Suspect Ranking and Mandate Transport Probing

**Date:** 2026-04-08
**Status:** Implemented
**Related episodes:**
- `agentic_ops_v5/docs/agent_logs/run_20260408_015734_p_cscf_latency.md` — InstructionGenerator pivoted to HSS despite NetworkAnalyst naming pcscf as primary (40%)
- `agentic_ops_v5/docs/agent_logs/run_20260408_030826_p_cscf_latency.md` — Investigator skipped measure_rtt, missed the latency (25%)

## Context

The NetworkAnalyst correctly identified pcscf as the PRIMARY suspect (high confidence) with icscf/pyhss as secondary. But the InstructionGenerator (Phase 3) wrote:

> "Your ONLY job is to investigate the root cause of the HSS unresponsiveness."

It re-derived its own priority from individual metrics (`icscf.cdp:timeout=1`), overriding the NetworkAnalyst's suspect ranking. The Investigator then spent all its time investigating HSS instead of pcscf.

Separately, the Investigator was not running `measure_rtt` as its first diagnostic step, violating the Hierarchy of Truth (Transport > Core > Application). It went straight to log analysis and metrics, missing the transport-layer latency.

## Decision

### 1. Preserve suspect ranking

The InstructionGenerator prompt now includes a mandatory "Suspect Ranking" section:

> "Preserve the NetworkAnalyst's suspect ordering. The NetworkAnalyst's PRIMARY suspect (highest confidence) MUST be the Investigator's primary investigation target. Do NOT re-derive your own priority from individual metrics or alarm conditions."

### 2. Mandate transport probing first

Every investigation instruction MUST include `measure_rtt` FROM the primary suspect as the FIRST diagnostic step:

> "Every investigation instruction MUST include measure_rtt FROM the primary suspect component as the FIRST diagnostic step. Transport-layer probing comes before log analysis, before metrics re-checks, before anything else."

### 3. Frame as hypotheses

Investigation instructions should frame the task as "hypotheses to test" rather than "conclusions to verify."

## Files changed

- `agentic_ops_v5/prompts/instruction_generator.md` — added Suspect Ranking (MANDATORY) section, Transport-Layer Probing First (MANDATORY) section, hypothesis framing

## Consequences

**Positive:** The Investigator now starts from the right component and probes transport first.

**Risk:** The InstructionGenerator still reads the raw NetworkAnalyst output which contains secondary symptoms (like `cdp:timeout`). Strong LLMs may still be tempted to investigate the most "dramatic" finding rather than the one the NetworkAnalyst ranked highest. The mandatory framing mitigates this but doesn't guarantee it.
