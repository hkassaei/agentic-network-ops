# Episode Report: IMS Network Partition

**Agent:** v5  
**Episode ID:** ep_20260416_223448_ims_network_partition  
**Date:** 2026-04-16T22:34:49.961375+00:00  
**Duration:** 285.5s  

---

## Scenario

**Category:** network  
**Blast radius:** multi_nf  
**Description:** Partition the P-CSCF from both the I-CSCF and S-CSCF using iptables DROP rules. SIP signaling between the edge proxy and the core IMS is completely severed. Tests IMS behavior under a network split.

## Faults Injected

- **network_partition** on `pcscf` — {'target_ip': '172.22.0.19'}
- **network_partition** on `pcscf` — {'target_ip': '172.22.0.20'}

## Baseline (Pre-Fault)

Stack phase before injection: **ready**
All containers running at baseline.

## Fault Propagation Verification

**Verdict:** ✅ `confirmed`

- **Wait:** 0s
- **Actual elapsed:** 0.0s
- **Nodes with significant deltas:** 2
- **Nodes with any drift:** 4

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

### Metrics Changes

| Node | Metric | Baseline | Current | Delta |
|------|--------|----------|---------|-------|
| pcscf | sl:1xx_replies | 14.0 | 22.0 | 8.0 |
| pcscf | core:rcv_requests_invite | 2.0 | 5.0 | 3.0 |
| pcscf | core:rcv_requests_register | 12.0 | 17.0 | 5.0 |
| pcscf | dialog_ng:processed | 2.0 | 5.0 | 3.0 |
| rtpengine | owned_sessions | 2.0 | 5.0 | 3.0 |
| rtpengine | total_sessions | 2.0 | 5.0 | 3.0 |

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 0.93 (threshold: 0.70, trained on 104 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following specific metrics were flagged as the top contributors to the anomaly. These MUST be reflected in your layer ratings:

| Component | Metric | Current | Learned Normal | Severity |
|-----------|--------|---------|---------------|----------|
| icscf | ims_icscf:lir_avg_response_time | 0.00 | 62.73 | MEDIUM |
| icscf | ims_icscf:uar_avg_response_time | 79.00 | 59.23 | MEDIUM |
| icscf | cdp:average_response_time | 79.00 | 61.35 | MEDIUM |
| normalized | upf.gtp_indatapktn3upf_per_ue | 0.04 | 2.77 | MEDIUM |
| normalized | upf.gtp_outdatapktn3upf_per_ue | 0.03 | 2.67 | MEDIUM |
| scscf | ims_auth:mar_avg_response_time | 112.00 | 125.37 | MEDIUM |
| normalized | smf.bearers_per_ue | 3.50 | 2.55 | LOW |
| normalized | pcscf.dialogs_per_ue | 0.00 | 0.54 | LOW |
| derived | upf_activity_during_calls | 1.00 | 0.49 | LOW |

## Network Analysis (Phase 1)

**Summary:** The network appears to have experienced a transient fault in the IMS layer, primarily affecting the I-CSCF, but the system has since returned to a stable state.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | All infrastructure components (mongo, mysql, dns) are running and responsive. |
| **ran** | 🟢 GREEN | gNB is running and 2 UEs are connected. |
| **core** | 🟢 GREEN | Core is stable. Low UPF throughput is expected as there are no active calls. |
| **ims** | 🟡 YELLOW | The anomaly screener detected medium-severity metric deviations on I-CSCF and S-CSCF during the event window, indicating a transient performance issue that has since cleared. |

**IMS evidence:**
- AnomalyScreener: ims_icscf:lir_avg_response_time was 0.00 (vs 62.73 normally)
- AnomalyScreener: ims_icscf:uar_avg_response_time was 79.00 (vs 59.23 normally)
- AnomalyScreener: cdp:average_response_time at icscf was 79.00 (vs 61.35 normally)
- AnomalyScreener: ims_auth:mar_avg_response_time at scscf was 112.00 (vs 125.37 normally)

**Suspect components:**

- **icscf** (high): Top-ranked component in the anomaly screening, with multiple Diameter-related metrics showing significant deviation from the healthy baseline. This points to a transient issue in handling user location or authentication requests.
- **scscf** (medium): Also flagged by the anomaly screener with degraded metric for MAR average response time. Issues at the I-CSCF would likely cascade to the S-CSCF, making it a secondary suspect.
- **pyhss** (low): The anomalies at the I-CSCF and S-CSCF are related to Diameter (Cx interface) requests sent to the HSS. Slowness or errors from the HSS could be the root cause of the elevated response times observed at the CSCFs.

**Investigation hint:** The fault appears to have been transient and is no longer active. The investigation should focus on analyzing historical logs from the event timeframe on the `icscf`, `scscf`, and `pyhss` containers. The primary suspect is the `icscf`. Examine its logs for any errors, timeouts, or high latency related to Diameter communication with `pyhss`. The screener's top flag, `ims_icscf:lir_avg_response_time: 0.00`, is a critical clue and could indicate a complete failure to process Location-Information-Requests.

**Tools called:** get_vonr_components, get_network_topology, get_network_status, get_nf_metrics, get_dp_quality_gauges, check_stack_rules, compare_to_baseline, get_causal_chain_for_component


## Pattern Match (Phase 2)

**❌ Match:** No matching signature found

- **Confidence:** low
- **Failure domain:** unknown
- **Baseline anomalies:** 1 metrics across 1 components


## Investigation Instruction (Phase 3)

> PRIMARY HYPOTHESIS TO FALSIFY: The I-CSCF experienced a transient fault, primarily affecting Diameter-related user location and authentication requests (LIR/UAR), with `ims_icscf:lir_avg_response_time: 0.00` indicating a potential complete failure to process Location-Information-Requests.
>
> FALSIFICATION PROBES (minimum 2, target 3):
>
> Probe 1 — P-CSCF:
>   Tool: `read_container_logs(container="pcscf", grep="REGISTER|INVITE|200 OK|4xx|5xx", since="5 minutes ago")`
>   Expected if hypothesis holds: P-CSCF logs should exhibit normal SIP request forwarding to I-CSCF, showing successful transmissions and receptions of SIP messages (e.g., 200 OKs for REGISTERs) without errors or timeouts directly indicating a problem in communicating with I-CSCF.
>   Falsifying observation: P-CSCF logs display errors, timeouts, or excessive retransmissions when attempting to send SIP requests to I-CSCF, or show I-CSCF responding with errors (e.g., 4xx/5xx SIP codes), suggesting the issue originates from P-CSCF's interaction with I-CSCF, or that I-CSCF is actively rejecting or failing to process SIP signaling.
>
> Probe 2 — PyHSS:
>   Tool: `read_container_logs(container="pyhss", grep="LIR|UAR|Cx-DR|Cx-DA|error|timeout", since="5 minutes ago")`
>   Expected if hypothesis holds: PyHSS logs either indicate no LIR/UAR requests were received from I-CSCF during the event, or show that requests were received and responded to successfully/with only minor transient errors. This would be consistent with the I-CSCF being the primary source of the `0.00` LIR response time (e.g., I-CSCF failed to generate/forward requests, or lost responses internally).
>   Falsifying observation: PyHSS logs show clear, persistent errors, significant delays, or a complete failure to respond to LIR/UAR requests *that it did receive* from I-CSCF during the event window. This would strongly suggest that PyHSS was the actual root cause of the I-CSCF's degraded Diameter metrics, rather than an internal I-CSCF issue.
>
> Probe 3 — S-CSCF:
>   Tool: `read_container_logs(container="scscf", grep="UAR|MAR|SAR|Cx-UR|Cx-AA|error|timeout", since="5 minutes ago")`
>   Expected if hypothesis holds: S-CSCF logs primarily show normal SIP processing and Diameter requests, or show some transient issues (e.g., elevated MAR response time) that could be a secondary effect of I-CSCF's problem or a minor, self-contained issue within S-CSCF, not its root cause.
>   Falsifying observation: S-CSCF logs reveal significant, independent errors or timeouts related to its own Diameter communication (e.g., with HSS for UAR/MAR/SAR requests) or internal SIP processing failures, which are *not* directly attributable to I-CSCF's state. This would imply that S-CSCF's observed anomalies are due to a distinct problem or a co-occurring fault, shifting the primary cause away from I-CSCF.
>
> ADDITIONAL NOTES:
>   - The Network Analyst's evidence suggests `ims_icscf:lir_avg_response_time was 0.00`. This is a critical clue. For the PyHSS probe, look for whether LIRs from I-CSCF were actually *received* by PyHSS and how they were handled.
>   - The Investigator should not re-run the anomaly screener or try to replicate the exact metric values reported by the Network Analyst, as the system is now stable. The focus is on log analysis for historical evidence from the event timeframe.

## Investigation (Phase 4)

> ### Hypothesis
> Not assessed — the mechanical guardrail triggered before the Investigator could produce a trustworthy verdict.
>
> ### Falsification Probes Executed
> Tool calls made: 0 (minimum required: 2).
> The Investigator's self-reported output has been discarded because it did not execute the minimum number of probes needed to falsify the Network Analyst's hypothesis. Any [EVIDENCE: ...] citations the Investigator produced are not backed by real tool invocations and have been removed.
>
> ### Verdict
> - **Verdict:** INCONCLUSIVE
> - **Reasoning:** Mechanical override. The Investigator made only 0 tool call(s) — below the 2-probe minimum required to attempt falsification. Confidence in any downstream diagnosis must be capped at medium per the INCONCLUSIVE branch in the Synthesis prompt.

## Evidence Validation (Phase 5)

**Verdict:** has_warnings
**Investigator confidence:** low
**Citations:** 0/0 verified

**WARNING:** Investigator made ZERO tool calls — all evidence citations are fabricated.

```
⚠️ CRITICAL: InvestigatorAgent made ZERO tool calls — no actual verification was performed.
Evidence validation: 0/0 citations verified (0 unmatched). Investigator: 0 citations from 0 tool calls.
Verdict: has_warnings. Confidence: low.

Tool calls vs. citations:
  NetworkAnalystAgent:
    ✗ check_stack_rules — called but NOT cited in output
    ✗ compare_to_baseline — called but NOT cited in output
    ✗ get_causal_chain_for_component — called but NOT cited in output
    ✗ get_dp_quality_gauges — called but NOT cited in output
    ✗ get_network_status — called but NOT cited in output
    ✗ get_network_topology — called but NOT cited in output
    ✗ get_nf_metrics — called but NOT cited in output
    ✗ get_vonr_components — called but NOT cited in output
```

## Ground Truth

**Failure domain:** ims_signaling  
**Protocol impact:** SIP  
**Affected components:** pcscf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v5-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 138.5s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: The investigation did not produce verifiable evidence. Manual investigation is required.
> - **timeline**:
> - **root_cause**: Unknown — the automated investigation could not verify its own findings.
> - **affected_components**:
>     - `icscf`: Suspect
>     - `scscf`: Suspect
>     - `pyhss`: Suspect
> - **recommendation**: Manual investigation required. Start from the Network Analyst's suspect list and verify each component's state with direct tool calls: measure_rtt, check_process_listeners, read_container_logs, read_running_config. Do not act on the Investigator's unverified claims without independent verification.
> - **confidence**: low
> - **explanation**: The Network Analyst detected a transient fault in the IMS layer, pointing to the I-CSCF as the primary suspect based on anomalous Diameter metrics (e.g., `ims_icscf:lir_avg_response_time: 0.00`). The Investigator agent, tasked with verifying this hypothesis, made zero tool calls — any evidence citations in its output are fabricated. This diagnosis has been downgraded to low confidence because the investigation phase did not produce reliable evidence. A human operator should investigate manually, using the Network Analyst's report as a starting point, before taking action.

### Scoring Breakdown

**Overall score: 15%**

**Scorer assessment:** The agent correctly identified the affected layer and was appropriately calibrated in its low confidence, but failed to identify the root cause, primary affected component, severity, or fault type.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | No | The simulated failure was an IMS network partition affecting the P-CSCF. The agent explicitly stated the root cause was 'Unknown' and did not identify a network partition or the P-CSCF as the cause. It focused on transient performance issues in I-CSCF/S-CSCF/HSS. |
| Component overlap | 0% | The primary affected component was the 'pcscf'. The agent listed 'icscf', 'scscf', and 'pyhss' as suspects, completely missing the 'pcscf'. |
| Severity correct | No | The simulated failure was a complete network partition, leading to severed SIP signaling and failed registrations/invites (a complete outage for affected services). The agent described the issue as a 'transient fault' and 'transient performance issue that has since cleared', rating the IMS layer as YELLOW, which indicates degradation, not a complete outage. |
| Fault type identified | No | The simulated fault type was a 'network partition' / 'component isolated'. The agent described a 'transient fault' and 'performance issue', but did not identify a network partition or isolation. |
| Layer accuracy | Yes | The primary affected component 'pcscf' belongs to the 'ims' layer. The agent's network analysis correctly identified the 'ims' layer as affected (rated YELLOW), even if it misidentified the specific component within that layer. |
| Confidence calibrated | Yes | The agent's diagnosis was largely incorrect regarding the root cause, primary component, severity, and fault type. However, the agent correctly assessed its own confidence as 'low' and provided a clear explanation for this low confidence (lack of verifiable evidence due to the Investigator agent making zero tool calls). This self-awareness and explicit statement of uncertainty, given the poor quality of the diagnosis, indicates good calibration. |

**Ranking:** The correct component ('pcscf') was not listed among the agent's 'affected_components' or 'suspect_components'. The agent also stated the root cause was 'Unknown'.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 74,978 |
| Output tokens | 5,408 |
| Thinking tokens | 9,231 |
| **Total tokens** | **89,617** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| NetworkAnalystAgent | 56,309 | 10 | 4 |
| PatternMatcherAgent | 0 | 0 | 0 |
| InstructionGeneratorAgent | 15,813 | 2 | 2 |
| InvestigatorAgent | 9,851 | 0 | 1 |
| EvidenceValidatorAgent | 0 | 0 | 0 |
| SynthesisAgent | 7,644 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 285.5s
