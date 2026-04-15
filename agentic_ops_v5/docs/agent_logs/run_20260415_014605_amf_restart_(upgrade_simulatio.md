# Episode Report: AMF Restart (Upgrade Simulation)

**Agent:** v5  
**Episode ID:** ep_20260415_014147_amf_restart_(upgrade_simulatio  
**Date:** 2026-04-15T01:41:48.850851+00:00  
**Duration:** 256.3s  

---

## Scenario

**Category:** container  
**Blast radius:** multi_nf  
**Description:** Stop the AMF for 10 seconds, then restart it. Simulates a rolling upgrade of the access and mobility management function. UEs will temporarily lose their 5G NAS connection and must re-attach.

## Faults Injected

- **container_stop** on `amf` — {'timeout': 10}

## Baseline (Pre-Fault)

Stack phase before injection: **ready**
All containers running at baseline.

## Fault Propagation Verification

**Verdict:** ✅ `confirmed`

- **Wait:** 0s
- **Actual elapsed:** 0.0s
- **Nodes with significant deltas:** 5
- **Nodes with any drift:** 5

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

### Metrics Changes

| Node | Metric | Baseline | Current | Delta |
|------|--------|----------|---------|-------|
| icscf | cdp:replies_response_time | 861.0 | 1318.0 | 457.0 |
| icscf | ims_icscf:uar_replies_response_time | 710.0 | 956.0 | 246.0 |
| icscf | cdp:replies_received | 15.0 | 24.0 | 9.0 |
| icscf | ims_icscf:lir_replies_response_time | 151.0 | 362.0 | 211.0 |
| icscf | core:rcv_requests_invite | 4.0 | 8.0 | 4.0 |
| icscf | core:rcv_requests_register | 22.0 | 32.0 | 10.0 |
| icscf | ims_icscf:lir_avg_response_time | 37.0 | 45.0 | 8.0 |
| icscf | ims_icscf:lir_replies_received | 4.0 | 8.0 | 4.0 |
| icscf | ims_icscf:uar_replies_received | 11.0 | 16.0 | 5.0 |
| pcscf | core:rcv_requests_bye | 16.0 | 24.0 | 8.0 |
| pcscf | httpclient:connok | 8.0 | 16.0 | 8.0 |
| pcscf | sl:1xx_replies | 30.0 | 48.0 | 18.0 |
| pcscf | dialog_ng:processed | 8.0 | 16.0 | 8.0 |
| pcscf | script:register_time | 3191.0 | 4258.0 | 1067.0 |
| pcscf | core:rcv_requests_invite | 8.0 | 16.0 | 8.0 |
| pcscf | core:rcv_requests_register | 22.0 | 32.0 | 10.0 |
| pcscf | script:register_success | 11.0 | 16.0 | 5.0 |
| rtpengine | total_relayed_packets | 341.0 | 919.0 | 578.0 |
| rtpengine | total_relayed_packets_(userspace) | 341.0 | 919.0 | 578.0 |
| rtpengine | total_number_of_discrete_round_trip_time_samples | 21.0 | 57.0 | 36.0 |
| rtpengine | total_relayed_bytes_(userspace) | 16660.0 | 47268.0 | 30608.0 |
| rtpengine | total_number_of_packet_loss_samples | 21.0 | 57.0 | 36.0 |
| rtpengine | sum_of_all_mos_values_sampled | 72.8 | 206.1 | 133.3 |
| rtpengine | sum_of_all_end_to_end_round_trip_time_values_sampled | 118055.0 | 318948.0 | 200893.0 |
| rtpengine | sum_of_all_end_to_end_round_trip_time_square_values_sampled | 793484081.0 | 2149222022.0 | 1355737941.0 |
| rtpengine | total_number_of_jitter_(reported)_samples | 21.0 | 57.0 | 36.0 |
| rtpengine | total_regular_terminated_sessions | 2.0 | 5.0 | 3.0 |
| rtpengine | total_number_of_mos_samples | 18.0 | 49.0 | 31.0 |
| rtpengine | jitter_(reported)_standard_deviation | 7.0 | 5.0 | -2.0 |
| rtpengine | total_number_of_end_to_end_round_trip_time_samples | 21.0 | 57.0 | 36.0 |
| rtpengine | total_sessions | 0.0 | 1.0 | 1.0 |
| rtpengine | average_jitter_(reported) | 6.0 | 2.0 | -4.0 |
| rtpengine | total_relayed_bytes | 16660.0 | 47268.0 | 30608.0 |
| rtpengine | sum_of_all_discrete_round_trip_time_square_values_sampled | 208565998.0 | 567035336.0 | 358469338.0 |
| rtpengine | sum_of_all_discrete_round_trip_time_values_sampled | 64172.0 | 174160.0 | 109988.0 |
| rtpengine | owned_sessions | 0.0 | 1.0 | 1.0 |
| rtpengine | total_managed_sessions | 2.0 | 5.0 | 3.0 |
| rtpengine | mos_standard_deviation | 0.06 | 0.04 | -0.019999999999999997 |
| rtpengine | average_packet_loss | 22.0 | 8.0 | -14.0 |
| rtpengine | sum_of_all_mos_square_values_sampled | 301.72 | 874.91 | 573.1899999999999 |
| scscf | cdp:replies_response_time | 2312.0 | 3052.0 | 740.0 |
| scscf | ims_registrar_scscf:accepted_regs | 11.0 | 16.0 | 5.0 |
| scscf | ims_auth:mar_replies_response_time | 1224.0 | 1588.0 | 364.0 |
| scscf | cdp:replies_received | 22.0 | 32.0 | 10.0 |
| scscf | dialog_ng:processed | 8.0 | 16.0 | 8.0 |
| scscf | ims_auth:mar_replies_received | 11.0 | 16.0 | 5.0 |
| scscf | ims_registrar_scscf:sar_replies_received | 11.0 | 16.0 | 5.0 |
| scscf | core:rcv_requests_invite | 8.0 | 16.0 | 8.0 |
| scscf | core:rcv_requests_register | 22.0 | 32.0 | 10.0 |
| scscf | ims_registrar_scscf:sar_replies_response_time | 1088.0 | 1464.0 | 376.0 |
| upf | fivegs_ep_n3_gtp_outdatapktn3upf | 641.0 | 1267.0 | 626.0 |
| upf | fivegs_ep_n3_gtp_outdatavolumeqosleveln3upf | 115936.0 | 213122.0 | 97186.0 |
| upf | fivegs_ep_n3_gtp_indatavolumeqosleveln3upf | 115744.0 | 202651.0 | 86907.0 |
| upf | fivegs_ep_n3_gtp_indatapktn3upf | 902.0 | 1550.0 | 648.0 |

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 0.95 (threshold: 0.70, trained on 99 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following specific metrics were flagged as the top contributors to the anomaly. These MUST be reflected in your layer ratings:

| Component | Metric | Current | Learned Normal | Severity |
|-----------|--------|---------|---------------|----------|
| rtpengine | packet_loss_standard_deviation | 17.00 | 0.00 | HIGH |
| rtpengine | average_packet_loss | 11.00 | 0.00 | HIGH |
| normalized | smf.sessions_per_ue | 0.00 | 2.00 | HIGH |
| normalized | smf.bearers_per_ue | 0.00 | 2.66 | HIGH |
| scscf | ims_registrar_scscf:sar_avg_response_time | 97.00 | 119.92 | MEDIUM |
| scscf | ims_auth:mar_avg_response_time | 106.00 | 88.89 | MEDIUM |
| normalized | upf.gtp_outdatapktn3upf_per_ue | 0.00 | 2.50 | MEDIUM |
| normalized | upf.gtp_indatapktn3upf_per_ue | 0.00 | 2.58 | MEDIUM |
| normalized | pcscf.dialogs_per_ue | 0.00 | 0.65 | LOW |
| derived | upf_activity_during_calls | 1.00 | 0.39 | LOW |

## Network Analysis (Phase 1)

**Summary:** A critical outage has occurred in the 5G core, with the AMF container having exited, leading to a loss of RAN connectivity and subsequent downstream anomalies in the IMS layer.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | All infrastructure components (MongoDB, MySQL, DNS) are running and responsive. |
| **ran** | 🔴 RED | RAN is disconnected from the 5G core due to AMF failure. |
| **core** | 🔴 RED | Critical failure in the control plane (AMF exited) and high-severity anomalies in SMF. |
| **ims** | 🟡 YELLOW | IMS media plane (RTPEngine) shows high packet loss and signaling metrics are degraded; these are likely downstream effects of the core/RAN failure. |

**RAN evidence:**
- AMF container, which terminates the RAN's N2 interface, has exited (per get_network_status).
- The N2 link '[RAN] -> AMF' is INACTIVE (per get_network_topology).
- The stack rule 'ran_down_invalidates_ims' fired, indicating a foundational RAN/Core connectivity failure.

**CORE evidence:**
- AMF container has exited, breaking UE registration, mobility, and session management.
- AnomalyScreener flagged 'smf.sessions_per_ue' (0.00 vs 2.00 normal) and 'smf.bearers_per_ue' (0.00 vs 2.66 normal) with HIGH severity.
- AnomalyScreener flagged UPF data plane metrics ('upf.gtp_outdatapktn3upf_per_ue' and 'upf.gtp_indatapktn3upf_per_ue') with MEDIUM severity.

**IMS evidence:**
- AnomalyScreener flagged 'rtpengine.packet_loss_standard_deviation' (17.00 vs 0.00 normal) and 'rtpengine.average_packet_loss' (11.00 vs 0.00 normal) with HIGH severity.
- AnomalyScreener flagged S-CSCF metrics 'sar_avg_response_time' and 'mar_avg_response_time' with MEDIUM severity.

**Suspect components:**

- **amf** (high): The AMF container has exited. This is a hard failure of a critical component, explaining the loss of RAN connectivity and inability to process UE registrations or sessions, making it the primary cause of the outage.
- **rtpengine** (medium): Flagged by the AnomalyScreener with HIGH severity for a large deviation in packet loss. While likely a downstream symptom of the AMF failure causing session collapse, the magnitude of the deviation warrants a secondary investigation into its state during the event.

**Investigation hint:** The immediate priority is to investigate the `amf` container failure. Check its logs, docker events, and host system logs (dmesg, journalctl) to determine why it exited. Once the AMF root cause is understood, examine the `rtpengine` packet loss as a likely secondary, cascading effect to understand how the core outage impacted active media sessions.

**Tools called:** get_vonr_components, get_network_topology, get_network_status, get_nf_metrics, get_dp_quality_gauges, read_env_config, measure_rtt, compare_to_baseline, check_stack_rules


## Pattern Match (Phase 2)

**❌ Match:** No matching signature found

- **Confidence:** low
- **Failure domain:** unknown


## Investigation Instruction (Phase 3)

> Instruction generation skipped: Network Analyst diagnosis is definitive.

## Investigation (Phase 4)

> Investigation skipped: Network Analyst produced a high-confidence diagnosis with definitive evidence (RED layer + high-confidence suspect). See Phase 1 analysis.

## Evidence Validation (Phase 5)

**Verdict:** clean
**Investigator confidence:** high
**Citations:** 2/2 verified

```
Investigator was intentionally skipped (Network Analyst diagnosis was definitive). Validating Network Analyst evidence only.
Network Analyst made 9 tool calls. Evidence validation: 2/2 NA citations verified.
Verdict: clean. Confidence: high.

Tool calls vs. citations:
  NetworkAnalystAgent:
    ✗ check_stack_rules — called but NOT cited in output
    ✗ compare_to_baseline — called but NOT cited in output
    ✗ get_dp_quality_gauges — called but NOT cited in output
    ✓ get_network_status — called AND cited (1x)
    ✓ get_network_topology — called AND cited (1x)
    ✗ get_nf_metrics — called but NOT cited in output
    ✗ get_vonr_components — called but NOT cited in output
    ✗ measure_rtt — called but NOT cited in output
    ✗ read_env_config — called but NOT cited in output
```

## Ground Truth

**Failure domain:** core_control_plane  
**Protocol impact:** NGAP  
**Affected components:** amf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v5-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 115.9s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: A critical 5G core outage occurred due to the failure of the Access and Mobility Management Function (AMF) container, causing a loss of RAN connectivity and a cascading failure of user sessions.
> - **timeline**:
>     1.  The AMF container, a key 5G core control plane function, unexpectedly exited.
>     2.  This immediately brought down the N2 interface, severing the connection between the Radio Access Network (RAN) and the core network.
>     3.  With the AMF unavailable, UE registration, mobility, and session management functions ceased, preventing any user traffic.
>     4.  The abrupt loss of underlying data bearers caused active IMS media sessions to fail, resulting in high packet loss within the RTPEngine and degraded signaling response times in the S-CSCF.
> - **root_cause**: The definitive root cause is the termination of the `amf` container. This single failure in the core control plane is responsible for the complete loss of service, as it sits at the critical junction between the radio network and all other core functions. The downstream anomalies in the SMF, UPF, and IMS layers are symptoms, not causes.
> - **affected_components**:
>     - `amf`: Root Cause
>     - `ran`: Symptomatic
>     - `smf`: Symptomatic
>     - `upf`: Symptomatic
>     - `rtpengine`: Symptomatic
> - **recommendation**: The immediate priority is to determine why the `amf` container exited. Operators should inspect the container's logs, Docker events, and the underlying host's system logs (e.g., dmesg, journalctl) for errors related to crashes, resource exhaustion (OOM killer), or configuration problems.
> - **confidence**: high
> - **explanation**: The network outage is the direct result of a hard failure in the 5G core. The AMF container has exited, breaking the fundamental link between the radio network and the core. Without a functional AMF, no user devices can register or establish data sessions, leading to a total service disruption. The observed high packet loss and signaling degradation in the IMS layer are downstream consequences of this core failure, as active voice and data sessions were abruptly torn down.

### Scoring Breakdown

**Overall score: 100%**

**Scorer assessment:** The agent provided an outstanding diagnosis, accurately identifying the AMF as the root cause of the core outage, correctly assessing its severity, identifying the fault type, and attributing it to the correct network layer, all with high confidence.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | Yes | The agent correctly identified the 'amf' component's termination/exit as the definitive root cause, which directly corresponds to the simulated failure mode of the AMF being temporarily unavailable/stopped. |
| Component overlap | 100% | The agent correctly identified 'amf' as the root cause component. It also accurately listed other components ('ran', 'smf', 'upf', 'rtpengine') as symptomatically affected, which demonstrates correct causal reasoning. |
| Severity correct | Yes | The agent described the event as a 'critical 5G core outage' and 'complete loss of service' due to the AMF container exiting. This accurately reflects the severity of a critical control plane component being stopped, even if temporarily. |
| Fault type identified | Yes | The agent clearly identified the fault type as a component 'termination' or 'exit' ('AMF container has exited'), leading to 'loss of RAN connectivity' and 'severing the connection', which aligns with a component being unreachable/down. |
| Layer accuracy | Yes | The agent correctly attributed the AMF failure to the 'core' layer in its layer status assessment, which matches the ground truth ontology for the 'amf' component. |
| Confidence calibrated | Yes | The agent expressed 'high' confidence, which is appropriate given the accuracy and completeness of its diagnosis, supported by detailed rationale and evidence. |

**Ranking position:** #1 — The agent explicitly identified the 'amf' container termination as the 'definitive root cause' and listed it as the primary suspect with high confidence, making it the top-ranked correct cause.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 82,618 |
| Output tokens | 1,927 |
| Thinking tokens | 7,673 |
| **Total tokens** | **92,218** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| NetworkAnalystAgent | 84,946 | 14 | 5 |
| PatternMatcherAgent | 0 | 0 | 0 |
| EvidenceValidatorAgent | 0 | 0 | 0 |
| SynthesisAgent | 7,272 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 256.3s
