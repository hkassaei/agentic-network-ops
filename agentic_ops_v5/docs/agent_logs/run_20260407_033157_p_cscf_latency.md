# Episode Report: P-CSCF Latency

**Agent:** v5  
**Episode ID:** ep_20260407_032122_p_cscf_latency  
**Date:** 2026-04-07T03:21:23.038318+00:00  
**Duration:** 634.1s  

---

## Scenario

**Category:** network  
**Blast radius:** single_nf  
**Description:** Inject 500ms latency on the P-CSCF (SIP edge proxy). SIP T1 timer is 500ms, so REGISTER transactions will start timing out. Tests IMS resilience to WAN-like latency on the signaling path.

## Faults Injected

- **network_latency** on `pcscf` — {'delay_ms': 2000, 'jitter_ms': 50}

## Baseline (Pre-Fault)

Stack phase before injection: **ready**
All containers running at baseline.

## Fault Propagation Verification

**Verdict:** ✅ `confirmed`

- **Wait:** 30s
- **Actual elapsed:** 30.0s
- **Nodes with significant deltas:** 3
- **Nodes with any drift:** 4

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

### Metrics Changes

| Node | Metric | Baseline | Current | Delta |
|------|--------|----------|---------|-------|
| icscf | core:rcv_requests_register | 227.0 | 281.0 | 54.0 |
| pcscf | core:rcv_requests_options | 16.0 | 92.0 | 76.0 |
| pcscf | script:register_time | 732.0 | 128707.0 | 127975.0 |
| pcscf | core:rcv_requests_invite | 0.0 | 33.0 | 33.0 |
| pcscf | httpclient:connfail | 17.0 | 105.0 | 88.0 |
| pcscf | script:register_success | 2.0 | 11.0 | 9.0 |
| pcscf | core:rcv_requests_register | 4.0 | 76.0 | 72.0 |
| pcscf | sl:4xx_replies | 0.0 | 12.0 | 12.0 |
| pcscf | sl:1xx_replies | 4.0 | 55.0 | 51.0 |
| scscf | ims_registrar_scscf:sar_avg_response_time | 111.0 | 80.0 | -31.0 |
| scscf | ims_usrloc_scscf:impu_collisions | 0.0 | 1.0 | 1.0 |
| scscf | ims_usrloc_scscf:subscription_collisions | 0.0 | 1.0 | 1.0 |
| scscf | ims_auth:mar_replies_received | 2.0 | 11.0 | 9.0 |
| scscf | cdp:replies_response_time | 372.0 | 1837.0 | 1465.0 |
| scscf | ims_usrloc_scscf:contact_collisions | 0.0 | 1.0 | 1.0 |
| scscf | ims_auth:mar_replies_response_time | 150.0 | 952.0 | 802.0 |
| scscf | ims_registrar_scscf:accepted_regs | 2.0 | 11.0 | 9.0 |
| scscf | ims_registrar_scscf:sar_replies_response_time | 222.0 | 885.0 | 663.0 |
| scscf | cdp:replies_received | 4.0 | 22.0 | 18.0 |
| scscf | core:rcv_requests_register | 4.0 | 22.0 | 18.0 |
| scscf | ims_registrar_scscf:sar_replies_received | 2.0 | 11.0 | 9.0 |

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 1.00 (threshold: 0.70, trained on 50 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following specific metrics were flagged as the top contributors to the anomaly. These MUST be reflected in your layer ratings:

| Component | Metric | Current | Learned Normal | Severity |
|-----------|--------|---------|---------------|----------|
| pcscf | core:rcv_requests_register_rate | 3027.29 | 0.08 | HIGH |
| icscf | cdp:replies_received_rate | 504.55 | 0.06 | HIGH |
| pcscf | httpclient:connfail_rate | 504.55 | 0.27 | HIGH |
| icscf | core:rcv_requests_register_rate | 504.55 | 0.08 | HIGH |
| scscf | core:rcv_requests_register_rate | 504.55 | 0.08 | HIGH |
| pcscf | sl:1xx_replies_rate | 504.55 | 0.12 | HIGH |
| upf | fivegs_ep_n3_gtp_indatapktn3upf_rate | 1009.10 | 5.04 | HIGH |
| upf | fivegs_ep_n3_gtp_outdatapktn3upf_rate | 504.55 | 4.92 | HIGH |
| icscf | cdp:timeout | 1.00 | 0.00 | HIGH |
| icscf | ims_icscf:uar_timeouts | 1.00 | 0.00 | HIGH |

## Network Analysis (Phase 1)

**Summary:** The network is experiencing a critical failure in the 5G core control plane, causing a service outage and cascading failures in the IMS layer.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | Infrastructure components (mongo, mysql, dns) are running and connected. |
| **ran** | 🟢 GREEN | gNB is connected and UEs are attached at the 5G NAS layer. |
| **core** | 🔴 RED | Critical failure: The SCP (Service Communication Proxy) has exited, breaking inter-NF communication. |
| **ims** | 🟡 YELLOW | IMS layer is degraded with Diameter timeouts and a likely registration storm, caused by upstream 5G core failure. |

**CORE evidence:**
- scp container status is 'exited' per get_network_status
- Multiple SBI links are INACTIVE due to SCP being down, per get_network_topology

**IMS evidence:**
- icscf:cdp:timeout=1.0 from get_nf_metrics (expected: 0)
- icscf:ims_icscf:uar_timeouts=1.0 from get_nf_metrics (expected: 0)
- High registration request rate (core:rcv_requests_register_rate) on pcscf, icscf, scscf flagged by AnomalyScreener

**Suspect components:**

- **scp** (high): The 'scp' container has exited. As the Service Communication Proxy, its failure is catastrophic for the 5G control plane, causing the numerous INACTIVE SBI links seen in the topology.
- **icscf** (medium): It is exhibiting secondary failures in the form of Diameter (cdp) timeouts. This is a symptom of the upstream SCP failure, but it is the component where the IMS service breakdown is most visible.

**Investigation hint:** The root cause is the failure of the 'scp' container. All investigation should prioritize understanding why 'scp' terminated. Check its container logs immediately. The IMS-level issues, such as the Diameter timeouts at the I-CSCF and the registration storm, are downstream symptoms of the core network collapse and not the primary fault.

**Tools called:** get_vonr_components, get_network_topology, get_network_status, get_nf_metrics, get_dp_quality_gauges, compare_to_baseline, check_stack_rules


## Pattern Match (Phase 2)

**❌ Match:** No matching signature found

- **Confidence:** low
- **Failure domain:** unknown
- **Baseline anomalies:** 1 metrics across 1 components


## Investigation Instruction (Phase 3)

> ESTABLISHED ROOT CAUSE: The 'scp' container has exited, causing a critical failure in the 5G core control plane, rendering multiple SBI links INACTIVE. This is the primary fault. The IMS layer degradation (I-CSCF Diameter timeouts, high registration request rate) is a *symptom* of this core network collapse, not the root cause. Your ONLY job: determine *why* the 'scp' container terminated. Immediately use `get_container_logs('scp')` to identify the reason for its exit. Re-confirm its status with `get_network_status('scp')` and its impact on communication paths with `get_network_topology()`. Do NOT investigate IMS-level issues as they are downstream symptoms.

## Ground Truth

**Failure domain:** ims_signaling  
**Protocol impact:** SIP  
**Affected components:** pcscf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v5-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 96.9s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ```json
> {
>   "causes": [
>     {
>       "summary": "The investigation did not produce verifiable evidence. Manual investigation is required.",
>       "timeline": [],
>       "root_cause": "Unknown — the automated investigation could not verify its own findings.",
>       "affected_components": [
>         {
>           "name": "scp",
>           "confidence": "high",
>           "reason": "The 'scp' container has exited. As the Service Communication Proxy, its failure is catastrophic for the 5G control plane, causing the numerous INACTIVE SBI links seen in the topology."
>         },
>         {
>           "name": "icscf",
>           "confidence": "medium",
>           "reason": "It is exhibiting secondary failures in the form of Diameter (cdp) timeouts. This is a symptom of the upstream SCP failure, but it is the component where the IMS service breakdown is most visible."
>         }
>       ],
>       "recommendation": "Manual investigation required. Start from the Network Analyst's suspect list and verify each component's state with direct tool calls: measure_rtt, check_process_listeners, read_container_logs, read_running_config. Do not act on the Investigator's unverified claims without independent verification.",
>       "confidence": "low",
>       "explanation": "The initial network analysis identified a critical failure: the Service Communication Proxy ('scp') container has exited, causing a collapse of the 5G core control plane and secondary failures in the IMS layer. However, the subsequent automated investigation phase failed to validate this hypothesis. The Investigator agent produced no tool calls — any evidence citations in its output are fabricated. This diagnosis has been downgraded to low confidence because the investigation phase did not produce reliable evidence. A human operator should investigate manually before taking action."
>     }
>   ]
> }
> ```

### Scoring Breakdown

**Overall score: 10%**

**Scorer assessment:** The agent completely failed to diagnose the P-CSCF latency issue, incorrectly identifying components and fault types, but demonstrated excellent confidence calibration by explicitly stating its findings were unverified and unreliable.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | No | The simulated failure was P-CSCF latency. The agent's stated root cause is 'Unknown' and its primary hypothesis (which it then discredits) was an 'scp container exit', neither of which matches the actual failure. |
| Component overlap | 0% | The primary affected component was 'pcscf'. The agent identified 'scp' and 'icscf' as affected components, neither of which is 'pcscf'. |
| Severity correct | No | The simulated failure was a degradation (latency). The agent's diagnosis implies a catastrophic outage ('scp container has exited', 'catastrophic for the 5G control plane', 'collapse of the 5G core control plane'), which is incorrect. |
| Fault type identified | No | The simulated fault type was network degradation (latency). The agent's diagnosis points to a component failure/unreachability ('scp container has exited'), not latency. |
| Confidence calibrated | Yes | Despite being completely wrong in its diagnosis, the agent correctly assessed its own low confidence, stating that the investigation did not produce verifiable evidence and that evidence citations were fabricated. This shows good calibration. |

**Ranking:** The correct cause (P-CSCF latency) was not listed among the agent's hypotheses.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 50,288 |
| Output tokens | 2,731 |
| Thinking tokens | 5,843 |
| **Total tokens** | **58,862** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| NetworkAnalystAgent | 37,977 | 9 | 3 |
| PatternMatcherAgent | 0 | 0 | 0 |
| InstructionGeneratorAgent | 5,096 | 0 | 1 |
| InvestigatorAgent | 6,982 | 0 | 1 |
| EvidenceValidatorAgent | 0 | 0 | 0 |
| SynthesisAgent | 8,807 | 0 | 1 |


## Resolution

**Heal method:** scheduled
**Recovery time:** 634.1s

## Post-Run Analysis

### Score: 10% — anomaly screener works, but SCP crash derailed the diagnosis

This is the first run where the anomaly detection pipeline worked end-to-end. The screener produced useful output. The failure was caused by a confounding variable (SCP crash) and a recurring Investigator bug (zero tool calls).

### Milestone: Anomaly Screener (Phase 0) worked correctly

For the first time, Phase 0 produced actionable output:

- **Overall score: 1.00** (threshold 0.70) — maximum anomaly detected
- **10 flags, all HIGH severity** — correctly identified pcscf as the epicenter
- `pcscf.core:rcv_requests_register_rate`: 3027/s vs normal 0.08/s — massive REGISTER retransmission storm
- `pcscf.httpclient:connfail_rate`: 504/s vs normal 0.27/s — HTTP connection failures spiking
- `icscf.cdp:timeout`: 1.0 vs normal 0.0 — Diameter timeouts appearing downstream
- The NetworkAnalyst acknowledged the screener: "High registration request rate on pcscf, icscf, scscf flagged by AnomalyScreener"

This validates the entire anomaly detection architecture: standalone training on healthy traffic → persisted model → loaded at runtime → ObservationTrafficAgent generates 2 min of faulted traffic + collects 22 snapshots → fresh preprocessor builds counter rates → screener scores against trained model → flags injected into NetworkAnalyst prompt.

### Issue 1 — SCP container crashed during the test (confounding variable)

The NetworkAnalyst found that the SCP (Service Communication Proxy) container had exited:
> "scp container status is 'exited' per get_network_status"

This was NOT part of the injected fault. The scenario only adds `tc netem delay 2000ms` to pcscf — it doesn't touch the SCP. The SCP likely crashed from cascading stress: the 2000ms P-CSCF delay caused SIP retransmission storms, which generated excessive SBI traffic through the SCP, overwhelming it.

The NetworkAnalyst correctly identified the SCP crash as the most severe visible issue (an exited container trumps elevated latency in severity assessment). From its perspective, blaming the SCP was rational — but it's a secondary failure caused by the injected P-CSCF latency, not the root cause.

**Impact:** The agent diagnosed "SCP crash causing core control plane collapse" instead of "P-CSCF latency causing SIP timeouts." The anomaly screener correctly flagged pcscf as the epicenter (register_rate 3027/s), but the NetworkAnalyst was distracted by the more dramatic SCP crash.

**Possible fixes:**
- Investigate why SCP crashes under load — it may need resource limits or restart policy
- The Hierarchy of Truth should help: transport-layer RTT from pcscf would have shown 2000ms, which precedes and explains the SCP crash. But the Investigator never ran `measure_rtt`.

### Issue 2 — Investigator made 0 tool calls (recurring)

`InvestigatorAgent | 6,982 | 0 | 1` — the Investigator produced one LLM response with zero tool invocations. It was given the instruction "check SCP logs" but didn't actually call `read_container_logs` or any other tool.

This is the same bug seen in `run_20260407_001824` (0 tool calls) and `run_20260406_235512` (0 tool calls). The Investigator LLM sometimes generates a narrative response without invoking any diagnostic tools, then the EvidenceValidator flags all citations as fabricated, and Synthesis downgrades to "low confidence, manual investigation required."

This is a separate agent behavior issue unrelated to the anomaly detection pipeline. Possible causes:
- The instruction telling it to "ONLY check SCP" is too narrow — the LLM may not find SCP-specific tool calls and gives up
- The LLM may be hitting a context length or tool-calling limitation
- The instruction from Phase 3 may be framed in a way that the LLM interprets as not requiring tools

### What the correct diagnosis chain would look like

If the SCP hadn't crashed and the Investigator had actually called tools:

1. **Screener (Phase 0):** pcscf register_rate 3027/s (normal 0.08) — ANOMALY at pcscf ✓ (this worked)
2. **NetworkAnalyst (Phase 1):** IMS RED, pcscf is the epicenter of the registration storm
3. **Investigator (Phase 4):** `measure_rtt("pcscf", "172.22.0.19")` → 2000ms RTT. `measure_rtt("icscf", "172.22.0.16")` → 0.5ms. Conclusion: unidirectional egress latency on pcscf.
4. **Synthesis (Phase 6):** "P-CSCF egress latency (~2000ms) causing SIP REGISTER timeouts"

Steps 1 is now working. Steps 2-4 were blocked by the SCP crash (confounding) and Investigator zero-tool-calls (recurring bug).
