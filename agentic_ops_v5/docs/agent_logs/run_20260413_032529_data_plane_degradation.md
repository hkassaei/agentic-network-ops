# Episode Report: Data Plane Degradation

**Agent:** v5  
**Episode ID:** ep_20260413_031959_data_plane_degradation  
**Date:** 2026-04-13T03:19:59.968430+00:00  
**Duration:** 329.2s  

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
- **Nodes with significant deltas:** 6
- **Nodes with any drift:** 6

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

### Metrics Changes

| Node | Metric | Baseline | Current | Delta |
|------|--------|----------|---------|-------|
| icscf | cdp:replies_response_time | 96.0 | 845.0 | 749.0 |
| icscf | ims_icscf:uar_replies_response_time | 96.0 | 729.0 | 633.0 |
| icscf | ims_icscf:lir_replies_received | 0.0 | 2.0 | 2.0 |
| icscf | cdp:replies_received | 2.0 | 16.0 | 14.0 |
| icscf | ims_icscf:uar_replies_received | 2.0 | 14.0 | 12.0 |
| icscf | ims_icscf:lir_replies_response_time | 0.0 | 116.0 | 116.0 |
| icscf | core:rcv_requests_register | 4.0 | 29.0 | 25.0 |
| icscf | core:rcv_requests_invite | 0.0 | 2.0 | 2.0 |
| icscf | ims_icscf:lir_avg_response_time | 0.0 | 58.0 | 58.0 |
| pcscf | dialog_ng:processed | 0.0 | 4.0 | 4.0 |
| pcscf | sl:1xx_replies | 4.0 | 33.0 | 29.0 |
| pcscf | httpclient:connfail | 34.0 | 65.0 | 31.0 |
| pcscf | core:rcv_requests_options | 33.0 | 58.0 | 25.0 |
| pcscf | core:rcv_requests_register | 4.0 | 35.0 | 31.0 |
| pcscf | script:register_success | 2.0 | 14.0 | 12.0 |
| pcscf | httpclient:connok | 0.0 | 6.0 | 6.0 |
| pcscf | dialog_ng:active | 0.0 | 2.0 | 2.0 |
| pcscf | core:rcv_requests_bye | 0.0 | 2.0 | 2.0 |
| pcscf | core:rcv_requests_invite | 0.0 | 4.0 | 4.0 |
| pcscf | script:register_time | 491.0 | 15911.0 | 15420.0 |
| rtpengine | bytes_per_second_(userspace) | 0.0 | 123.0 | 123.0 |
| rtpengine | total_number_of_packet_loss_samples | 124.0 | 158.0 | 34.0 |
| rtpengine | sum_of_all_end_to_end_round_trip_time_values_sampled | 631142.0 | 782978.0 | 151836.0 |
| rtpengine | total_relayed_bytes_(userspace) | 92440.0 | 112798.0 | 20358.0 |
| rtpengine | total_relayed_packets | 1895.0 | 2467.0 | 572.0 |
| rtpengine | total_sessions | 0.0 | 2.0 | 2.0 |
| rtpengine | sum_of_all_packet_loss_values_sampled | 607.0 | 2140.0 | 1533.0 |
| rtpengine | sum_of_all_mos_values_sampled | 464.6 | 596.6 | 132.0 |
| rtpengine | average_packet_loss | 4.0 | 13.0 | 9.0 |
| rtpengine | total_number_of_discrete_round_trip_time_samples | 124.0 | 158.0 | 34.0 |
| rtpengine | sum_of_all_discrete_round_trip_time_square_values_sampled | 1084021516.0 | 1301263539.0 | 217242023.0 |
| rtpengine | total_relayed_packets_(userspace) | 1895.0 | 2467.0 | 572.0 |
| rtpengine | packets_per_second_(userspace) | 0.0 | 2.0 | 2.0 |
| rtpengine | userspace_only_media_streams | 0.0 | 2.0 | 2.0 |
| rtpengine | mos_standard_deviation | 0.01 | 0.03 | 0.019999999999999997 |
| rtpengine | owned_sessions | 0.0 | 2.0 | 2.0 |
| rtpengine | bytes_per_second_(total) | 0.0 | 123.0 | 123.0 |
| rtpengine | sum_of_all_packet_loss_square_values_sampled | 32229.0 | 112088.0 | 79859.0 |
| rtpengine | total_number_of_jitter_(reported)_samples | 124.0 | 158.0 | 34.0 |
| rtpengine | sum_of_all_mos_square_values_sampled | 2000.92 | 2574.34 | 573.4200000000001 |
| rtpengine | packet_loss_standard_deviation | 15.0 | 22.0 | 7.0 |
| rtpengine | total_relayed_bytes | 92440.0 | 112798.0 | 20358.0 |
| rtpengine | total_number_of_mos_samples | 108.0 | 139.0 | 31.0 |
| rtpengine | total_number_of_end_to_end_round_trip_time_samples | 124.0 | 158.0 | 34.0 |
| rtpengine | packets_per_second_(total) | 0.0 | 2.0 | 2.0 |
| rtpengine | sum_of_all_discrete_round_trip_time_values_sampled | 346216.0 | 430155.0 | 83939.0 |
| scscf | dialog_ng:processed | 0.0 | 4.0 | 4.0 |
| scscf | cdp:replies_response_time | 335.0 | 2552.0 | 2217.0 |
| scscf | ims_registrar_scscf:accepted_regs | 2.0 | 14.0 | 12.0 |
| scscf | ims_registrar_scscf:sar_avg_response_time | 76.0 | 112.0 | 36.0 |
| scscf | ims_auth:mar_replies_received | 2.0 | 15.0 | 13.0 |
| scscf | cdp:replies_received | 4.0 | 29.0 | 25.0 |
| scscf | core:rcv_requests_register | 4.0 | 29.0 | 25.0 |
| scscf | dialog_ng:active | 0.0 | 2.0 | 2.0 |
| scscf | ims_auth:mar_replies_response_time | 182.0 | 981.0 | 799.0 |
| scscf | core:rcv_requests_invite | 0.0 | 4.0 | 4.0 |
| scscf | ims_registrar_scscf:sar_replies_received | 2.0 | 14.0 | 12.0 |
| scscf | ims_auth:mar_avg_response_time | 91.0 | 65.0 | -26.0 |
| scscf | ims_registrar_scscf:sar_replies_response_time | 153.0 | 1571.0 | 1418.0 |
| smf | bearers_active | 4.0 | 6.0 | 2.0 |
| upf | fivegs_ep_n3_gtp_outdatavolumeqosleveln3upf | 354914.0 | 453727.0 | 98813.0 |
| upf | fivegs_ep_n3_gtp_outdatapktn3upf | 2117.0 | 2753.0 | 636.0 |
| upf | fivegs_ep_n3_gtp_indatavolumeqosleveln3upf | 398947.0 | 513492.0 | 114545.0 |
| upf | fivegs_ep_n3_gtp_indatapktn3upf | 2988.0 | 3883.0 | 895.0 |

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 1.00 (threshold: 0.70, trained on 51 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following specific metrics were flagged as the top contributors to the anomaly. These MUST be reflected in your layer ratings:

| Component | Metric | Current | Learned Normal | Severity |
|-----------|--------|---------|---------------|----------|
| pcscf | httpclient:connfail_rate | 1480.26 | 0.29 | HIGH |
| icscf | cdp:replies_received_rate | 740.13 | 0.06 | HIGH |
| pcscf | sl:1xx_replies_rate | 1480.26 | 0.11 | HIGH |
| pcscf | core:rcv_requests_invite_rate | 740.13 | 0.05 | HIGH |
| scscf | core:rcv_requests_invite_rate | 740.13 | 0.05 | HIGH |
| pcscf | core:rcv_requests_register_rate | 740.13 | 0.07 | HIGH |
| icscf | core:rcv_requests_register_rate | 740.13 | 0.07 | HIGH |
| scscf | core:rcv_requests_register_rate | 740.13 | 0.07 | HIGH |
| scscf | cdp:replies_received_rate | 740.13 | 0.07 | HIGH |
| icscf | core:rcv_requests_invite_rate | 370.06 | 0.02 | HIGH |

## Network Analysis (Phase 1)

**Summary:** The network is experiencing a critical failure in the IMS layer, leading to massive voice media packet loss, despite all components being online.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | All infrastructure components (mongo, mysql, dns) are running and responsive. |
| **ran** | 🟢 GREEN | RAN appears healthy, with 2 UEs connected to the gNB. |
| **core** | 🟡 YELLOW | Core control plane is stable, but high HTTP connection failures at P-CSCF, likely to PCF, suggest a policy-related issue affecting the UPF data plane. |
| **ims** | 🔴 RED | IMS service is failing. RTPEngine reports catastrophic packet loss (45%) for active calls, and CSCFs are flooded with requests, likely from client retries. |

**CORE evidence:**
- pcscf: httpclient:connfail_rate=1480.26 (from AnomalyScreener)
- upf: in_pps=7.3, out_pps=5.2 (from get_dp_quality_gauges)

**IMS evidence:**
- rtpengine: loss (recent)=45.0 (from get_dp_quality_gauges)
- rtpengine: packets/sec=4.7 (from get_dp_quality_gauges)
- pcscf: sl:1xx_replies_rate=1480.26 (from AnomalyScreener)
- icscf: cdp:replies_received_rate=740.13 (from AnomalyScreener)
- scscf: core:rcv_requests_invite_rate=740.13 (from AnomalyScreener)

**Suspect components:**

- **pcscf** (high): The AnomalyScreener flagged 'pcscf: httpclient:connfail_rate' as the highest-severity anomaly (1480.26 vs 0.29 normal). This suggests a failure in communicating with the PCF, which is critical for setting up VoNR QoS bearers.
- **pcf** (medium): The PCF is the likely target of the failing HTTP requests from the P-CSCF over the Rx interface. It should be investigated for errors, overload, or misconfiguration.
- **rtpengine** (low): RTPEngine is reporting severe symptoms (45% packet loss) but is likely not the cause. The packet loss is happening in the user plane (UPF) due to a lack of proper QoS, which is a control plane/policy failure.

**Investigation hint:** The investigation should prioritize the P-CSCF to PCF interface (Rx). The high rate of `httpclient:connfail` at the P-CSCF is the most likely trigger for this entire incident. Examine container logs on both `pcscf` and `pcf` for HTTP errors or Diameter Rx failures. This failure likely prevented the correct QoS rules from being installed on the UPF, causing the catastrophic media packet loss reported by `rtpengine`. The elevated SIP traffic at all CSCFs is probably a cascading symptom of clients retrying failed calls.

**Tools called:** get_vonr_components, get_network_topology, get_network_status, get_nf_metrics, get_dp_quality_gauges, read_env_config, measure_rtt, compare_to_baseline, check_stack_rules


## Pattern Match (Phase 2)

**❌ Match:** No matching signature found

- **Confidence:** low
- **Failure domain:** unknown
- **Baseline anomalies:** 4 metrics across 4 components


## Investigation Instruction (Phase 3)

> Anomalies detected in IMS (RED) and Core (YELLOW) layers. Suspect components: `pcscf` (primary, high confidence), `pcf` (secondary, medium confidence). Infrastructure and RAN are GREEN; do not investigate them.
>
> FIRST: Run `measure_rtt` FROM `pcscf` TO `pcf` to check for transport-layer latency or connectivity issues over the Rx interface.
>
> NEXT: Focus investigation on the `pcscf` to `pcf` communication. The `pcscf:httpclient:connfail_rate` anomaly (1480.26) is the highest priority. Examine container logs on both `pcscf` and `pcf` for specific HTTP errors or Diameter Rx interface failures. This communication failure is critically preventing the correct VoNR QoS rules from being installed on the UPF, leading to the catastrophic 45% media packet loss reported by `rtpengine`. The elevated SIP traffic observed at `icscf` and `scscf` is a cascading symptom of clients retrying failed calls and should not be prioritized for root cause analysis.

## Investigation (Phase 4)

> [InvestigatorAgent produced no output — possible ADK thinking-mode issue]

## Evidence Validation (Phase 5)

**Verdict:** has_warnings
**Investigator confidence:** medium
**Citations:** 5/5 verified

```
⚠️ WARNING: InvestigatorAgent made 6 tool calls but produced ZERO [EVIDENCE: ...] citations. The investigation narrative is unverifiable — tool results exist but are not traceably referenced.
Evidence validation: 5/5 citations verified (0 unmatched). Investigator: 0 citations from 6 tool calls.
Verdict: has_warnings. Investigator confidence: medium.

Tool calls vs. citations:
  NetworkAnalystAgent:
    ✗ check_stack_rules — called but NOT cited in output
    ✗ compare_to_baseline — called but NOT cited in output
    ✓ get_dp_quality_gauges — called AND cited (3x)
    ✗ get_network_status — called but NOT cited in output
    ✗ get_network_topology — called but NOT cited in output
    ✓ get_nf_metrics — called AND cited (2x)
    ✗ get_vonr_components — called but NOT cited in output
    ✗ measure_rtt — called but NOT cited in output
    ✗ read_env_config — called but NOT cited in output
  InvestigatorAgent:
    ✗ OntologyConsultationAgent — called but NOT cited in output
    ✗ measure_rtt — called but NOT cited in output
    ✗ read_container_logs — called but NOT cited in output
    ✗ read_env_config — called but NOT cited in output
    ✗ read_running_config — called but NOT cited in output
    ✗ run_kamcmd — called but NOT cited in output
```

## Ground Truth

**Failure domain:** data_plane  
**Protocol impact:** GTP-U  
**Affected components:** upf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v5-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 191.8s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: The investigation did not produce verifiable evidence to confirm the root cause; manual investigation is required.
> - **timeline**:
> - **root_cause**: Unknown — the automated investigation phase failed to produce any findings.
> - **affected_components**:
>     - `pcscf`: Suspect (Primary)
>     - `pcf`: Suspect (Secondary)
>     - `rtpengine`: Suspect (Symptomatic)
> - **recommendation**: Manual investigation required. Start from the Network Analyst's suspect list and the provided investigation hint. Prioritize checking the P-CSCF to PCF (Rx) interface for transport-level issues (`measure_rtt`) and application errors (`read_container_logs` on both components). Do not act on any automated findings beyond the initial network analysis without independent verification.
> - **confidence**: low
> - **explanation**: The Network Analyst identified a critical failure in the IMS layer, characterized by massive voice media packet loss (45% at RTPEngine) and a very high rate of HTTP connection failures at the P-CSCF (`httpclient:connfail_rate=1480.26`). This strongly suggests a failure in the P-CSCF to PCF communication, preventing proper QoS setup for voice calls. However, the subsequent automated investigation agent produced no output. While 6 tool calls were made, no findings or evidence were generated. This diagnosis has been downgraded to low confidence because the investigation phase failed completely. A human operator must investigate manually before taking action.

### Scoring Breakdown

**Overall score: 50%**

**Scorer assessment:** The agent correctly identified the severity and fault type (packet loss) and the UPF as the location of the data plane issue. However, it failed to identify the direct packet loss on the UPF as the root cause, instead hypothesizing a control plane issue and stating the root cause as 'Unknown' with low confidence.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | No | The simulated failure mode is 30% packet loss directly on the UPF. The agent's stated root_cause is 'Unknown'. While the agent identifies 'catastrophic media packet loss' and states 'The packet loss is happening in the user plane (UPF)', its primary hypothesis for the root cause is a control plane issue (P-CSCF to PCF communication failure preventing QoS setup) that *leads to* the UPF data plane issue, rather than identifying the direct packet loss on the UPF as the root cause itself. The prompt requires the simulated failure mode to be identified as the root cause. |
| Component overlap | 50% | The primary affected component is 'upf'. The agent explicitly states 'The packet loss is happening in the user plane (UPF)' and mentions 'affecting the UPF data plane' in the core layer status. This correctly identifies the component where the failure is occurring. However, 'upf' is not listed in the agent's 'affected_components' list, which instead focuses on hypothesized root cause components (pcscf, pcf). Partial credit is given because the UPF is clearly identified as the location of the fault. |
| Severity correct | Yes | The agent describes the impact as 'critical failure', 'massive voice media packet loss (45% at RTPEngine)', and 'catastrophic packet loss'. A 30% packet loss on the UPF would indeed lead to such severe degradation, so the severity assessment is correct. |
| Fault type identified | Yes | The agent clearly identifies 'massive voice media packet loss' and 'catastrophic packet loss' as the observable fault type, which directly matches the simulated 'packet loss'. |
| Layer accuracy | Yes | The ground truth states 'upf' belongs to the 'core' layer. The agent's 'core' layer status note mentions 'affecting the UPF data plane' and rates the 'core' layer as YELLOW, which is appropriate for a degradation involving the UPF. The IMS layer is rated RED due to RTPEngine packet loss, which is an IMS component and a symptom of the UPF issue. This is consistent. |
| Confidence calibrated | Yes | The agent states 'low' confidence and provides a clear explanation that the automated investigation failed to produce verifiable evidence, leading to an 'Unknown' root cause. This self-assessment of low confidence is appropriate given the lack of conclusive findings from its automated tools. |

**Ranking:** The agent explicitly states the root cause is 'Unknown' and does not provide a ranked list of root cause candidates. The 'affected_components' list does not include the UPF as a primary candidate.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 167,803 |
| Output tokens | 2,640 |
| Thinking tokens | 11,706 |
| **Total tokens** | **182,149** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| NetworkAnalystAgent | 78,157 | 17 | 5 |
| PatternMatcherAgent | 0 | 0 | 0 |
| InstructionGeneratorAgent | 5,847 | 0 | 1 |
| InvestigatorAgent | 90,385 | 9 | 9 |
| EvidenceValidatorAgent | 0 | 0 | 0 |
| SynthesisAgent | 7,760 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 329.2s
