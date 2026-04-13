# Episode Report: Data Plane Degradation

**Agent:** v5  
**Episode ID:** ep_20260413_024035_data_plane_degradation  
**Date:** 2026-04-13T02:40:36.795980+00:00  
**Duration:** 317.2s  

---

## Scenario

**Category:** network  
**Blast radius:** single_nf  
**Description:** Inject 30% packet loss on the UPF. RTP media streams will degrade, voice quality drops. Tests whether the stack detects and reports data plane quality issues.

## Faults Injected

- **network_loss** on `upf` — {'loss_pct': 30}

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
| icscf | ims_icscf:uar_replies_received | 18.0 | 26.0 | 8.0 |
| icscf | ims_icscf:uar_replies_response_time | 1201.0 | 1636.0 | 435.0 |
| icscf | cdp:replies_received | 27.0 | 38.0 | 11.0 |
| icscf | ims_icscf:lir_replies_received | 9.0 | 12.0 | 3.0 |
| icscf | core:rcv_requests_invite | 9.0 | 12.0 | 3.0 |
| icscf | cdp:replies_response_time | 1749.0 | 2464.0 | 715.0 |
| icscf | core:rcv_requests_register | 36.0 | 53.0 | 17.0 |
| icscf | ims_icscf:lir_replies_response_time | 548.0 | 828.0 | 280.0 |
| pcscf | script:register_success | 2.0 | 10.0 | 8.0 |
| pcscf | sl:1xx_replies | 4.0 | 27.0 | 23.0 |
| pcscf | httpclient:connok | 0.0 | 10.0 | 10.0 |
| pcscf | core:rcv_requests_invite | 0.0 | 9.0 | 9.0 |
| pcscf | script:register_time | 581.0 | 15992.0 | 15411.0 |
| pcscf | httpclient:connfail | 89.0 | 125.0 | 36.0 |
| pcscf | core:rcv_requests_bye | 0.0 | 10.0 | 10.0 |
| pcscf | core:rcv_requests_register | 4.0 | 23.0 | 19.0 |
| pcscf | core:rcv_requests_options | 88.0 | 112.0 | 24.0 |
| pcscf | dialog_ng:processed | 0.0 | 6.0 | 6.0 |
| rtpengine | sum_of_all_packet_loss_values_sampled | 0.0 | 607.0 | 607.0 |
| rtpengine | average_packet_loss | 0.0 | 4.0 | 4.0 |
| rtpengine | packet_loss_standard_deviation | 0.0 | 15.0 | 15.0 |
| rtpengine | total_managed_sessions | 9.0 | 11.0 | 2.0 |
| rtpengine | total_sessions | 0.0 | 1.0 | 1.0 |
| rtpengine | total_regular_terminated_sessions | 9.0 | 11.0 | 2.0 |
| rtpengine | total_relayed_bytes | 76544.0 | 92440.0 | 15896.0 |
| rtpengine | owned_sessions | 0.0 | 1.0 | 1.0 |
| rtpengine | total_relayed_bytes_(userspace) | 76544.0 | 92440.0 | 15896.0 |
| rtpengine | sum_of_all_jitter_(reported)_values_sampled | 64.0 | 860.0 | 796.0 |
| rtpengine | average_jitter_(reported) | 0.0 | 6.0 | 6.0 |
| rtpengine | jitter_(reported)_standard_deviation | 0.0 | 49.0 | 49.0 |
| rtpengine | sum_of_all_packet_loss_square_values_sampled | 0.0 | 32229.0 | 32229.0 |
| rtpengine | sum_of_all_jitter_(reported)_square_values_sampled | 64.0 | 313702.0 | 313638.0 |
| scscf | cdp:replies_received | 4.0 | 21.0 | 17.0 |
| scscf | core:rcv_requests_invite | 0.0 | 6.0 | 6.0 |
| scscf | ims_auth:mar_replies_received | 2.0 | 11.0 | 9.0 |
| scscf | dialog_ng:processed | 0.0 | 6.0 | 6.0 |
| scscf | ims_registrar_scscf:sar_replies_response_time | 218.0 | 1115.0 | 897.0 |
| scscf | ims_registrar_scscf:accepted_regs | 2.0 | 10.0 | 8.0 |
| scscf | ims_auth:mar_replies_response_time | 193.0 | 1271.0 | 1078.0 |
| scscf | cdp:replies_response_time | 411.0 | 2386.0 | 1975.0 |
| scscf | core:rcv_requests_register | 4.0 | 21.0 | 17.0 |
| scscf | ims_registrar_scscf:sar_replies_received | 2.0 | 10.0 | 8.0 |
| upf | fivegs_ep_n3_gtp_outdatavolumeqosleveln3upf | 256010.0 | 344674.0 | 88664.0 |
| upf | fivegs_ep_n3_gtp_outdatapktn3upf | 1719.0 | 2099.0 | 380.0 |
| upf | fivegs_ep_n3_gtp_indatapktn3upf | 2049.0 | 2623.0 | 574.0 |
| upf | fivegs_ep_n3_gtp_indatavolumeqosleveln3upf | 231733.0 | 366166.0 | 134433.0 |

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 1.00 (threshold: 0.70, trained on 51 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following specific metrics were flagged as the top contributors to the anomaly. These MUST be reflected in your layer ratings:

| Component | Metric | Current | Learned Normal | Severity |
|-----------|--------|---------|---------------|----------|
| icscf | cdp:replies_received_rate | 453.95 | 0.06 | HIGH |
| pcscf | httpclient:connfail_rate | 680.93 | 0.29 | HIGH |
| pcscf | core:rcv_requests_invite_rate | 453.95 | 0.05 | HIGH |
| scscf | core:rcv_requests_invite_rate | 453.95 | 0.05 | HIGH |
| pcscf | sl:1xx_replies_rate | 680.93 | 0.11 | HIGH |
| icscf | core:rcv_requests_invite_rate | 226.98 | 0.02 | HIGH |
| pcscf | core:rcv_requests_register_rate | 226.98 | 0.07 | HIGH |
| icscf | core:rcv_requests_register_rate | 226.98 | 0.07 | HIGH |
| scscf | core:rcv_requests_register_rate | 226.98 | 0.07 | HIGH |
| scscf | cdp:replies_received_rate | 226.98 | 0.07 | HIGH |

## Network Analysis (Phase 1)

**Summary:** The 5G core is down due to an exited SMF container, causing a complete outage of PDU session establishment and subsequent failures in the IMS layer.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | All infrastructure components (mongo, mysql, dns) are running. |
| **ran** | 🟢 GREEN | gNB is connected and UEs are attached to the AMF. |
| **core** | 🔴 RED | The core is non-functional because the SMF has exited, preventing PDU session management. |
| **ims** | 🔴 RED | IMS layer is experiencing high error rates and request floods, assessed as cascading symptoms of the core network failure. |

**CORE evidence:**
- smf container has exited, as reported by get_network_status.
- N4 link from SMF to UPF is INACTIVE, as reported by get_network_topology.

**IMS evidence:**
- Anomaly Screener: icscf cdp:replies_received_rate was 453.95 (normal: 0.06).
- Anomaly Screener: pcscf httpclient:connfail_rate was 680.93 (normal: 0.29).
- Anomaly Screener: pcscf core:rcv_requests_invite_rate was 453.95 (normal: 0.05).
- Anomaly Screener: scscf core:rcv_requests_invite_rate was 453.95 (normal: 0.05).

**Suspect components:**

- **smf** (high): The smf container has exited. This is a critical failure that halts all PDU session establishment, making it the most likely root cause of the network-wide outage.
- **icscf** (medium): Flagged by the AnomalyScreener as the top anomaly with a high rate of received Diameter replies. This is considered a downstream symptom of the SMF failure, as UEs are unable to get PDU sessions and their subsequent SIP requests fail.
- **pcscf** (medium): Flagged by the AnomalyScreener for a high rate of connection failures and incoming SIP INVITEs. This is assessed as a downstream symptom of the SMF failure.

**Investigation hint:** The primary and most critical fault is that the 'smf' container has exited. This prevents all PDU session establishment, which is a prerequisite for any user activity, including VoNR. The numerous high-severity anomalies in the IMS layer are cascading symptoms of this core failure. The Investigator must prioritize examining the logs of the 'smf' container to determine the cause of its termination. All other symptoms can be disregarded until the SMF is restored.

**Tools called:** get_vonr_components, get_network_topology, get_network_status, get_nf_metrics, get_dp_quality_gauges, read_env_config, measure_rtt, compare_to_baseline, check_stack_rules, get_causal_chain_for_component


## Pattern Match (Phase 2)

**❌ Match:** No matching signature found

- **Confidence:** low
- **Failure domain:** unknown


## Investigation Instruction (Phase 3)

> Anomalies detected in core and ims layers. Suspect components: smf (high confidence), icscf (medium confidence), pcscf (medium confidence). Your ONLY job is to investigate the primary suspect, 'smf'. Do NOT investigate icscf or pcscf until the smf issue is resolved, as their anomalies are considered cascading symptoms of the core network failure.
>
> The primary and most critical fault is that the 'smf' container has exited, preventing all PDU session establishment.
>
> FIRST: Per the Hierarchy of Truth (Transport > Core > Application), you MUST FIRST attempt to check transport layer connectivity relevant to the 'smf'. Since the 'smf' container is exited, run `measure_rtt` from its direct neighbors (`upf`, `pcf`) to the 'smf's expected network endpoint. Also, if possible, run `measure_rtt` from the host environment where the 'smf' container is supposed to run, to its dependencies (`upf`, `pcf`). This will help confirm if any underlying network problems contributed to the SMF's termination or are preventing its restart.
>
> NEXT: Examine the logs of the 'smf' container using `get_nf_logs(component='smf')` to determine the specific cause of its termination. This is the crucial step for diagnosing why the container exited.

## Investigation (Phase 4)

> ### Hypothesis Verification
> - **Instruction received:** Investigate the exited 'smf' container, starting with transport layer connectivity checks and then analyzing its logs.
> - **Verdict:** CONFIRMED
>
> ### Evidence Chain
> - **Finding**: The SMF container has exited and is unreachable on the network.
> - **Evidence**: [EVIDENCE: measure_rtt("upf", "172.22.0.7") -> "Target 172.22.0.7 is UNREACHABLE from upf...100% packet loss"]
> - **Significance**: This confirms the container is down and not just isolated by a network issue. The unreachability is a symptom of the container's exited state, not the cause.
>
> - **Finding**: The SMF container is also unreachable from the PCF container.
> - **Evidence**: [EVIDENCE: measure_rtt("pcf", "172.22.0.7") -> "Target 172.22.0.7 is UNREACHABLE from pcf...100% packet loss"]
> - **Significance**: This corroborates that the SMF network endpoint is offline, consistent with the process being terminated.
>
> - **Finding**: The SMF process terminated due to a fatal software error.
> - **Evidence**: [EVIDENCE: read_container_logs("smf", 50) -> "FATAL: ogs_nas_build_qos_flow_descriptions: Assertion `num_of_flow_description' failed...Aborted (core dumped)"]
> - **Significance**: This is the direct root cause of the SMF failure. A critical assertion in the NAS message handling logic failed, leading to a core dump and the immediate termination of the SMF application.
>
> - **Finding**: The network environment configuration was successfully retrieved.
> - **Evidence**: [EVIDENCE: read_env_config() -> "smf_ip": "172.22.0.7"]
> - **Significance**: This provided the necessary IP address to perform the transport layer connectivity checks, enabling the investigation to proceed as instructed.
>
> ### Layer Status
> - **Transport**: RED. The SMF container's IP is unreachable. [EVIDENCE: measure_rtt("upf", "172.22.0.7") -> "Target 172.22.0.7 is UNREACHABLE from upf...100% packet loss"]
> - **Core**: RED. The SMF, a critical 5G core component, has crashed and exited. [EVIDENCE: read_container_logs("smf", 50) -> "...FATAL: ogs_nas_build_qos_flow_descriptions: Assertion `num_of_flow_description' failed...Aborted (core dumped)"]
> - **Application**: RED. All PDU session establishment is impossible without a functional SMF, causing cascading failures in the IMS layer. The initial analysis correctly identified the IMS issues as symptoms.
>
> ### Root Cause Assessment
> - **Primary cause**: The SMF container has exited due to a fatal assertion failure within the Open5GS SMF software. Specifically, the `ogs_nas_build_qos_flow_descriptions` function crashed while handling a NAS message, which indicates a software bug or a malformed message that was not handled gracefully.
> - **Confidence**: High
> - **Supporting evidence**:
>     - [EVIDENCE: read_container_logs("smf", 50) -> "FATAL: ogs_nas_build_qos_flow_descriptions: Assertion `num_of_flow_description' failed. (../lib/nas/5gs/types.c:413)"]
>     - [EVIDENCE: read_container_logs("smf", 50) -> "/open5gs_init.sh: line 86:     8 Aborted                 (core dumped) /mnt/smf/${COMPONENT_NAME}_init.sh"]
>     - [EVIDENCE: measure_rtt("upf", "172.22.0.7") -> "Target 172.22.0.7 is UNREACHABLE from upf"]

## Evidence Validation (Phase 5)

**Verdict:** clean
**Investigator confidence:** high
**Citations:** 9/9 verified

```
Evidence validation: 9/9 citations verified (0 unmatched). Investigator: 9 citations from 3 tool calls.
Verdict: clean. Investigator confidence: high.

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
    ✗ measure_rtt — called but NOT cited in output
    ✗ read_env_config — called but NOT cited in output
  InvestigatorAgent:
    ✓ measure_rtt — called AND cited (4x)
    ✓ read_container_logs — called AND cited (4x)
    ✓ read_env_config — called AND cited (1x)
```

## Ground Truth

**Failure domain:** data_plane  
**Protocol impact:** GTP-U  
**Affected components:** upf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v5-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 184.2s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: The SMF container crashed due to a fatal software assertion failure, causing a complete outage of the 5G core network and subsequent cascading failures in the IMS layer.
> - **timeline**:
>     1.  The SMF application process encountered a fatal software error (`Assertion 'num_of_flow_description' failed`) within its NAS message handling logic.
>     2.  This error caused the SMF process to abort and generate a core dump, leading to the immediate exit of the `smf` container.
>     3.  With the SMF offline, all PDU session establishment requests from UEs began to fail, bringing down the 5G core data plane.
>     4.  As a consequence, IMS components (`pcscf`, `icscf`) were flooded with failing requests from UEs that could not get data plane connectivity, resulting in the high error rates detected by monitoring.
> - **root_cause**: A software bug in the SMF's `ogs_nas_build_qos_flow_descriptions` function caused a fatal assertion failure, which terminated the SMF process. This single component failure in the 5G Core is the definitive root cause of the network-wide service outage.
> - **affected_components**:
>     - `smf`: Root Cause
>     - `pcscf`: Symptomatic
>     - `icscf`: Symptomatic
>     - `scscf`: Symptomatic
> - **recommendation**: The evidence points to a software bug in the SMF. The operator should examine the full SMF logs and the associated core dump file to prepare a bug report for the software vendor. Restarting the component might restore service temporarily, but the underlying issue may recur until a software patch is deployed.
> - **confidence**: high
> - **explanation**: The investigation confirmed that the `smf` container, a critical 5G core component, has exited. Log analysis revealed the direct cause: a fatal software crash due to an assertion failure in the NAS message processing code. This crash made the SMF unreachable on the network and halted all PDU session management. The numerous anomalies observed in the IMS layer are secondary symptoms of this primary core network failure, as user devices cannot obtain the necessary data connectivity to use IMS services.

### Scoring Breakdown

**Overall score: 0%**

**Scorer assessment:** The agent's diagnosis was completely incorrect, misidentifying the root cause, affected component, severity, and fault type, and showing poor confidence calibration.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | No | The simulated failure was 30% packet loss on the UPF, leading to data plane degradation. The agent diagnosed an SMF container crash due to a software bug, causing a complete network outage. These are entirely different failure modes and root causes. |
| Component overlap | 0% | The simulated primary affected component is 'upf'. The agent identified 'smf' as the root cause. There is no overlap between the identified and actual primary components. |
| Severity correct | No | The simulated failure was a data plane degradation (30% packet loss), which implies impaired service. The agent diagnosed a 'complete outage' and 'network-wide service outage', which is a much higher severity than the actual degradation. |
| Fault type identified | No | The simulated fault type was network degradation (packet loss). The agent identified a component being down/unreachable (SMF container exited), which is a different class of failure. |
| Layer accuracy | No | The actual affected component is 'upf', which belongs to the 'core' layer. The agent did not identify 'upf' as the affected component. While the agent did rate the 'core' layer RED, its reasoning was based on an incorrect root cause ('smf' crash) and not the actual 'upf' packet loss. |
| Confidence calibrated | No | The agent stated 'high' confidence for a diagnosis that was completely incorrect regarding the root cause, affected component, severity, and fault type. This indicates poor calibration. |

**Ranking:** The correct root cause (packet loss on UPF) was not identified or listed by the agent.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 151,757 |
| Output tokens | 5,711 |
| Thinking tokens | 11,923 |
| **Total tokens** | **169,391** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| NetworkAnalystAgent | 116,984 | 19 | 7 |
| PatternMatcherAgent | 0 | 0 | 0 |
| InstructionGeneratorAgent | 7,235 | 0 | 1 |
| InvestigatorAgent | 36,166 | 4 | 4 |
| EvidenceValidatorAgent | 0 | 0 | 0 |
| SynthesisAgent | 9,006 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 317.2s

---

*Post-run critical analysis available at: `docs/critical-observations/run_20260413_024554_data_plane_degradation.md`*
