# Episode Report: P-CSCF Latency

**Agent:** v5  
**Episode ID:** ep_20260414_195918_p_cscf_latency  
**Date:** 2026-04-14T19:59:20.385780+00:00  
**Duration:** 280.3s  

---

## Scenario

**Category:** network  
**Blast radius:** single_nf  
**Description:** Inject 2000ms latency (with 50ms jitter) on the P-CSCF (SIP edge proxy). SIP transactions will experience severe delays as every message entering and leaving the P-CSCF is delayed, compounding across multiple round-trips in the IMS registration chain. Tests IMS resilience to high latency on the signaling edge.

## Faults Injected

- **network_latency** on `pcscf` — {'delay_ms': 2000, 'jitter_ms': 50}

## Baseline (Pre-Fault)

Stack phase before injection: **ready**
All containers running at baseline.

## Fault Propagation Verification

**Verdict:** ✅ `confirmed`

- **Wait:** 0s
- **Actual elapsed:** 0.0s
- **Nodes with significant deltas:** 3
- **Nodes with any drift:** 4

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

### Metrics Changes

| Node | Metric | Baseline | Current | Delta |
|------|--------|----------|---------|-------|
| icscf | ims_icscf:uar_avg_response_time | 67.0 | 53.0 | -14.0 |
| icscf | cdp:replies_received | 2.0 | 5.0 | 3.0 |
| icscf | core:rcv_requests_register | 4.0 | 22.0 | 18.0 |
| icscf | ims_icscf:uar_replies_response_time | 135.0 | 268.0 | 133.0 |
| icscf | cdp:replies_response_time | 135.0 | 268.0 | 133.0 |
| icscf | ims_icscf:uar_replies_received | 2.0 | 5.0 | 3.0 |
| icscf | cdp:average_response_time | 67.0 | 53.0 | -14.0 |
| pcscf | script:register_success | 2.0 | 5.0 | 3.0 |
| pcscf | core:rcv_requests_invite | 0.0 | 9.0 | 9.0 |
| pcscf | httpclient:connfail | 38.0 | 60.0 | 22.0 |
| pcscf | core:rcv_requests_register | 4.0 | 28.0 | 24.0 |
| pcscf | script:register_time | 508.0 | 43346.0 | 42838.0 |
| pcscf | sl:4xx_replies | 0.0 | 3.0 | 3.0 |
| pcscf | sl:1xx_replies | 4.0 | 19.0 | 15.0 |
| pcscf | core:rcv_requests_options | 37.0 | 57.0 | 20.0 |
| scscf | cdp:replies_received | 4.0 | 10.0 | 6.0 |
| scscf | ims_registrar_scscf:sar_replies_response_time | 213.0 | 572.0 | 359.0 |
| scscf | core:rcv_requests_register | 4.0 | 10.0 | 6.0 |
| scscf | ims_auth:mar_replies_response_time | 118.0 | 274.0 | 156.0 |
| scscf | ims_auth:mar_replies_received | 2.0 | 5.0 | 3.0 |
| scscf | ims_registrar_scscf:accepted_regs | 2.0 | 5.0 | 3.0 |
| scscf | ims_registrar_scscf:sar_replies_received | 2.0 | 5.0 | 3.0 |
| scscf | cdp:replies_response_time | 331.0 | 846.0 | 515.0 |

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 0.83 (threshold: 0.70, trained on 103 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following specific metrics were flagged as the top contributors to the anomaly. These MUST be reflected in your layer ratings:

| Component | Metric | Current | Learned Normal | Severity |
|-----------|--------|---------|---------------|----------|
| scscf | ims_auth:mar_avg_response_time | 54.00 | 129.30 | HIGH |
| pcscf | script:register_time | 43346.00 | 8371.17 | HIGH |
| icscf | ims_icscf:lir_avg_response_time | 0.00 | 76.82 | HIGH |
| derived | pcscf_sip_error_ratio | 0.25 | 0.00 | MEDIUM |
| icscf | cdp:average_response_time | 53.00 | 77.85 | MEDIUM |
| normalized | upf.gtp_outdatapktn3upf_per_ue | 0.06 | 2.11 | MEDIUM |
| icscf | ims_icscf:uar_avg_response_time | 53.00 | 77.56 | MEDIUM |
| normalized | upf.gtp_indatapktn3upf_per_ue | 0.17 | 2.15 | MEDIUM |
| scscf | ims_registrar_scscf:sar_avg_response_time | 114.00 | 110.33 | LOW |

## Network Analysis (Phase 1)

**Summary:** The network issue is a severe transport-layer latency problem localized to the P-CSCF container, causing IMS registration and signaling to fail.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | All components are running and responsive |
| **ran** | 🟢 GREEN | UEs are connected to the gNB and registered with the AMF |
| **core** | 🟢 GREEN | 5G Core is healthy and operational, data plane is normally idle |
| **ims** | 🔴 RED | P-CSCF is experiencing catastrophic network latency, making IMS signaling non-functional |

**IMS evidence:**
- pcscf to icscf RTT: ~2012ms (expected <1ms)
- pcscf to scscf RTT: ~1966ms (expected <1ms)
- pcscf to rtpengine RTT: ~1998ms (expected <1ms)
- icscf to pcscf RTT: ~1981ms (expected <1ms)
- pcscf script:register_time: 43346ms (anomaly screener: HIGH)

**Suspect components:**

- **pcscf** (high): Catastrophic RTT (~2000ms) measured from pcscf to all its network neighbors (icscf, scscf, pcf, rtpengine). RTT from icscf to pcscf is also ~2000ms, while RTT between all other components is normal (<1ms). This indicates a severe fault localized to the pcscf container's network interface.
- **icscf** (low): Flagged by anomaly screener (lir_avg_response_time), but this is a downstream symptom of the pcscf latency. I-CSCF itself is responsive to pings from other neighbors (<1ms RTT).
- **scscf** (low): Flagged by anomaly screener (mar_avg_response_time), but this is a downstream symptom of the pcscf latency. S-CSCF itself is responsive to pings from other neighbors (<1ms RTT).

**Investigation hint:** The root cause is extreme network latency (~2 seconds RTT) on the P-CSCF container's interface. All other components are healthy. The investigation should focus exclusively on the `pcscf` container's networking. Check for `tc` traffic control rules (e.g., `netem delay`), veth interface issues, or resource exhaustion (CPU, memory) on the Docker host that could be impacting only this container. The problem is not in the application logic of P-CSCF, but in its network transport.

**Tools called:** get_vonr_components, get_network_topology, get_network_status, get_nf_metrics, get_dp_quality_gauges, read_env_config, measure_rtt, check_stack_rules


## Pattern Match (Phase 2)

**❌ Match:** No matching signature found

- **Confidence:** low
- **Failure domain:** unknown


## Investigation Instruction (Phase 3)

> Anomalies detected in the IMS layer, which is RED. Suspect components: `pcscf` (high confidence), `icscf` (low confidence), `scscf` (low confidence). Infrastructure, RAN, and Core layers are GREEN — do not investigate them.
>
> The primary suspect is the `pcscf` container experiencing catastrophic transport-layer network latency (~2 seconds RTT) localized to its interface, making IMS signaling non-functional. `icscf` and `scscf` issues are downstream symptoms. The problem is not in the application logic of P-CSCF, but in its network transport.
>
> **Your ONLY job is to investigate the `pcscf` container's networking exclusively.**
>
> **FIRST:**
> 1.  Run `measure_rtt` FROM `pcscf` to its neighbors (`icscf`, `scscf`, `rtpengine`, `pcf`) to confirm the ~2 second RTT.
> 2.  Run `measure_rtt` FROM `icscf` and `scscf` to `pcscf` to confirm the RTT from their perspective.
>
> **THEN, if network latency from/to `pcscf` is confirmed:**
> 1.  Check for `tc` (traffic control) rules (e.g., `netem delay`) configured on the `pcscf` container's network interfaces or its host.
> 2.  Investigate for potential veth interface issues related to the `pcscf` container.
> 3.  Monitor resource exhaustion (CPU, memory, network I/O) on the Docker host that could be specifically impacting the `pcscf` container's network performance.
> 4.  Examine `pcscf` container logs for any networking-related errors or warnings.
> 5.  Do NOT investigate application logic or other components until the `pcscf` transport-layer issue is fully understood and ruled out as the root cause.

## Investigation (Phase 4)

> Investigation failed: Tool 'run_code' not found.
> Available tools: measure_rtt, check_process_listeners, query_prometheus, get_nf_metrics, get_dp_quality_gauges, get_network_status, run_kamcmd, read_running_config, read_container_logs, search_logs, read_env_config, query_subscriber, OntologyConsultationAgent
>
> Possible causes:
>   1. LLM hallucinated the function name - review agent instruction clarity
>   2. Tool not registered - verify agent.tools list
>   3. Name mismatch - check for typos
>
> Suggested fixes:
>   - Review agent instruction to ensure tool usage is clear
>   - Verify tool is included in agent.tools list
>   - Check for typos in function name

## Evidence Validation (Phase 5)

**Verdict:** has_warnings
**Investigator confidence:** low
**Citations:** 1/1 verified

**WARNING:** Investigator made ZERO tool calls — all evidence citations are fabricated.

```
⚠️ CRITICAL: InvestigatorAgent made ZERO tool calls — no actual verification was performed.
Evidence validation: 1/1 citations verified (0 unmatched). Investigator: 0 citations from 0 tool calls.
Verdict: has_warnings. Investigator confidence: low.

Tool calls vs. citations:
  NetworkAnalystAgent:
    ✗ check_stack_rules — called but NOT cited in output
    ✗ get_dp_quality_gauges — called but NOT cited in output
    ✗ get_network_status — called but NOT cited in output
    ✗ get_network_topology — called but NOT cited in output
    ✓ get_nf_metrics — called AND cited (1x)
    ✗ get_vonr_components — called but NOT cited in output
    ✗ measure_rtt — called but NOT cited in output
    ✗ read_env_config — called but NOT cited in output
```

## Ground Truth

**Failure domain:** ims_signaling  
**Protocol impact:** SIP  
**Affected components:** pcscf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v5-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 134.5s

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
>     - `pcscf`: (Suspected Root Cause)
>     - `icscf`: (Suspected Symptomatic)
>     - `scscf`: (Suspected Symptomatic)
> - **recommendation**: Manual investigation required. Start from the Network Analyst's suspect list and verify each component's state with direct tool calls: measure_rtt, check_process_listeners, read_container_logs, read_running_config. Do not act on the Investigator's unverified claims without independent verification.
> - **confidence**: low
> - **explanation**: The Network Analyst identified a potential root cause: severe, transport-layer network latency (~2000ms RTT) localized to the `pcscf` container. However, the subsequent investigation phase failed to validate this hypothesis. The Investigator agent produced no tool calls — any evidence citations in its output are fabricated. This diagnosis has been downgraded to low confidence because the investigation phase did not produce reliable evidence. A human operator should investigate manually before taking action.

### Scoring Breakdown

**Overall score: 100%**

**Scorer assessment:** The agent provided an excellent diagnosis, accurately identifying the root cause as severe latency on the P-CSCF, correctly pinpointing the affected component and its layer, and assessing the severity and fault type with high confidence and supporting evidence.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | Yes | The agent's 'NETWORK ANALYSIS' section clearly identifies the root cause as 'extreme network latency (~2 seconds RTT) on the P-CSCF container's interface' and 'severe transport-layer latency problem localized to the P-CSCF container'. This perfectly matches the simulated failure mode of 2000ms latency on the P-CSCF. |
| Component overlap | 100% | The agent correctly identifies 'pcscf' as the primary affected component and the 'Suspected Root Cause' in the 'causes' section, and as the high-confidence suspect in the 'NETWORK ANALYSIS' section. It also correctly identifies 'icscf' and 'scscf' as symptomatic, which is appropriate. |
| Severity correct | Yes | The agent describes the latency as 'severe', 'catastrophic', and states it is 'making IMS signaling non-functional'. This accurately reflects the impact of a 2000ms delay, which would lead to timeouts and registration failures, effectively rendering the signaling non-functional. |
| Fault type identified | Yes | The agent explicitly identifies the fault type as 'severe, transport-layer network latency' and 'extreme network latency', which is a correct classification of the observable failure (network degradation due to latency). |
| Layer accuracy | Yes | The 'pcscf' component belongs to the 'ims' layer. The agent correctly rates the 'ims' layer as 'RED' and provides evidence of P-CSCF latency within that layer's status, demonstrating correct layer attribution. |
| Confidence calibrated | Yes | While the 'causes' section states 'confidence: low' due to an internal investigation workflow issue, the 'NETWORK ANALYSIS' section, which contains the actual technical diagnosis, expresses 'high confidence' for the 'pcscf' as the root cause. This high confidence is well-calibrated as the diagnosis is correct and supported by specific tool evidence (RTT measurements of ~2000ms). The agent's technical findings are robust and well-evidenced. |

**Ranking position:** #1 — The 'pcscf' is listed first as the 'Suspected Root Cause' in the 'causes' section and first in the 'suspect_components' list within 'NETWORK ANALYSIS' with 'high confidence'.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 90,028 |
| Output tokens | 2,178 |
| Thinking tokens | 6,660 |
| **Total tokens** | **98,866** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| NetworkAnalystAgent | 85,951 | 18 | 5 |
| PatternMatcherAgent | 0 | 0 | 0 |
| InstructionGeneratorAgent | 6,148 | 0 | 1 |
| EvidenceValidatorAgent | 0 | 0 | 0 |
| SynthesisAgent | 6,767 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 280.3s
