# ADR: Generalized Ontology Causal Chains — Hypothesis-Driven Diagnostics

**Date:** 2026-04-08
**Status:** Implemented
**Related episodes:**
- `agentic_ops_v5/docs/agent_logs/run_20260407_035711_p_cscf_latency.md` — ontology led agent to wrong causal chain (15%)
- `agentic_ops_v5/docs/agent_logs/run_20260408_015734_p_cscf_latency.md` — agent still blamed HSS despite pcscf being primary suspect (40%)

## Context

The v5 RCA agent repeatedly misdiagnosed the P-CSCF Latency scenario (score 0-15%) because the ontology's causal chains were overfitted to specific root causes:

- The `sip_edge_latency` chain was P-CSCF-specific: "if register storm + cdp:timeout → P-CSCF latency"
- The `hss_unreachable` chain matched `cdp:timeout > 0` at I-CSCF, which also appears as a cascading symptom of P-CSCF latency
- The agent matched `hss_unreachable` instead of `sip_edge_latency` because the Diameter timeout symptom was a better pattern match

The initial fix was to add P-CSCF-specific disambiguation rules. But this was challenged: the same symptom pattern (register storm + Diameter timeouts) can be caused by latency on ANY IMS component (P-CSCF, I-CSCF, S-CSCF), or by process hangs, overload, database slowness — not just P-CSCF latency. The ontology was memorizing one specific failure instead of teaching the agent how to diagnose.

## Decision

**The ontology must teach agents HOW to diagnose, not WHAT the answer is.** Causal chains describe symptom patterns and prescribe diagnostic procedures (hypotheses to test), not specific root causes.

### Changes

**1. Renamed `sip_edge_latency` → `ims_signaling_chain_degraded`**

No longer P-CSCF-specific. Describes the general symptom pattern: "SIP transactions timing out, REGISTER retransmissions spiking, Diameter queries failing — one or more components on the IMS signaling chain is slow, overloaded, or broken."

Lists ALL possible causes: latency on any hop, process hang, overload, database slowness, network partition. The `does_NOT_mean` section explains that the component REPORTING the timeout is not necessarily the component CAUSING the problem.

The diagnostic approach is now a systematic 4-step procedure:
1. Identify the failure domain (confirm IMS signaling chain is degraded)
2. Probe each IMS component independently with `measure_rtt` — find the bottleneck
3. Check process health on the suspected component
4. Check HSS specifically if Diameter timeouts are present and all RTTs are normal

**2. Updated `hss_unreachable` with `hypothesis_testing`**

Replaced the P-CSCF-specific disambiguation with a general hypothesis testing framework:
- **Hypothesis A:** HSS is genuinely unreachable or broken → test with `measure_rtt`, logs, process listeners
- **Hypothesis B:** The Diameter timeouts are a cascading symptom of upstream IMS chain degradation → test by probing each IMS component with `measure_rtt`

The chain instructs: "Only conclude `hss_unreachable` if Hypothesis A is confirmed AND Hypothesis B is ruled out."

**3. Replaced overfitted symptom signatures**

Removed `pcscf_latency_with_diameter_cascade` (hardcoded "pcscf register storm + cdp:timeout → P-CSCF latency"). Replaced with `ims_signaling_chain_degraded` signature that lists hypotheses to test, not predetermined answers.

**4. Updated NetworkAnalyst prompt**

Added generalized principle: "Network signaling chains are sequential — a bottleneck at any point causes cascading symptoms at other components. The component REPORTING a timeout is NOT necessarily the component CAUSING it." Instructs the agent to frame investigation hints as hypotheses to test, not conclusions to verify.

## Files changed

- `network_ontology/data/causal_chains.yaml` — renamed chain, generalized cascading effects, added hypothesis testing
- `network_ontology/data/symptom_signatures.yaml` — replaced overfitted signature with hypothesis-driven one
- `agentic_ops_v5/prompts/network_analyst.md` — generalized suspect reasoning guidance

## Consequences

**Positive:** The ontology no longer memorizes specific failures. It teaches the diagnostic methodology that works for any IMS signaling chain degradation, regardless of which component is the bottleneck or what type of failure caused it.

**Risk:** The agent now has more work to do (must test hypotheses instead of following a predetermined chain). This requires the Investigator to actually call `measure_rtt` and interpret the results correctly — which is a separate ongoing challenge.
