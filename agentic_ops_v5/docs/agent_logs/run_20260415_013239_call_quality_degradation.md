# Episode Report: Call Quality Degradation

**Agent:** v5  
**Episode ID:** ep_20260415_012845_call_quality_degradation  
**Date:** 2026-04-15T01:28:46.783825+00:00  
**Duration:** 232.1s  

---

## Scenario

**Category:** network  
**Blast radius:** single_nf  
**Description:** Inject 30% packet loss on RTPEngine — the media relay for VoNR voice calls. RTP packets are dropped after RTPEngine receives them, degrading voice quality (MOS drop, jitter increase, audible artifacts). SIP signaling and 5G core are completely unaffected because they don't traverse RTPEngine. Tests whether the agent can diagnose a pure media-path fault without IMS signaling noise.

## Faults Injected

- **network_loss** on `rtpengine` — {'loss_pct': 30}

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
| icscf | ims_icscf:lir_avg_response_time | 0.0 | 37.0 | 37.0 |
| icscf | cdp:replies_response_time | 440.0 | 861.0 | 421.0 |
| icscf | ims_icscf:uar_replies_response_time | 440.0 | 710.0 | 270.0 |
| icscf | ims_icscf:uar_replies_received | 6.0 | 11.0 | 5.0 |
| icscf | core:rcv_requests_register | 12.0 | 22.0 | 10.0 |
| icscf | cdp:average_response_time | 73.0 | 57.0 | -16.0 |
| icscf | core:rcv_requests_invite | 0.0 | 4.0 | 4.0 |
| icscf | ims_icscf:lir_replies_response_time | 0.0 | 151.0 | 151.0 |
| icscf | cdp:replies_received | 6.0 | 15.0 | 9.0 |
| icscf | ims_icscf:lir_replies_received | 0.0 | 4.0 | 4.0 |
| pcscf | script:register_success | 6.0 | 11.0 | 5.0 |
| pcscf | script:register_time | 1916.0 | 3191.0 | 1275.0 |
| pcscf | core:rcv_requests_register | 12.0 | 22.0 | 10.0 |
| pcscf | core:rcv_requests_invite | 0.0 | 8.0 | 8.0 |
| pcscf | core:rcv_requests_bye | 0.0 | 16.0 | 16.0 |
| pcscf | core:rcv_requests_options | 51.0 | 76.0 | 25.0 |
| pcscf | dialog_ng:processed | 0.0 | 8.0 | 8.0 |
| pcscf | httpclient:connok | 0.0 | 8.0 | 8.0 |
| pcscf | sl:1xx_replies | 12.0 | 30.0 | 18.0 |
| pcscf | httpclient:connfail | 52.0 | 93.0 | 41.0 |
| rtpengine | sum_of_all_packet_loss_values_sampled | 0.0 | 475.0 | 475.0 |
| rtpengine | average_jitter_(reported) | 0.0 | 6.0 | 6.0 |
| rtpengine | total_relayed_packets_(userspace) | 0.0 | 341.0 | 341.0 |
| rtpengine | jitter_(reported)_standard_deviation | 0.0 | 7.0 | 7.0 |
| rtpengine | average_discrete_round_trip_time | 0.0 | 3055.0 | 3055.0 |
| rtpengine | discrete_round_trip_time_standard_deviation | 0.0 | 770.0 | 770.0 |
| rtpengine | sum_of_all_mos_values_sampled | 0.0 | 72.8 | 72.8 |
| rtpengine | end_to_end_round_trip_time_standard_deviation | 0.0 | 2486.0 | 2486.0 |
| rtpengine | sum_of_all_discrete_round_trip_time_square_values_sampled | 0.0 | 208565998.0 | 208565998.0 |
| rtpengine | total_number_of_discrete_round_trip_time_samples | 0.0 | 21.0 | 21.0 |
| rtpengine | sum_of_all_end_to_end_round_trip_time_values_sampled | 0.0 | 118055.0 | 118055.0 |
| rtpengine | sum_of_all_discrete_round_trip_time_values_sampled | 0.0 | 64172.0 | 64172.0 |
| rtpengine | total_number_of_jitter_(reported)_samples | 0.0 | 21.0 | 21.0 |
| rtpengine | total_number_of_packet_loss_samples | 0.0 | 21.0 | 21.0 |
| rtpengine | average_packet_loss | 0.0 | 22.0 | 22.0 |
| rtpengine | sum_of_all_jitter_(reported)_square_values_sampled | 0.0 | 2010.0 | 2010.0 |
| rtpengine | total_regular_terminated_sessions | 0.0 | 2.0 | 2.0 |
| rtpengine | average_end_to_end_round_trip_time | 0.0 | 5621.0 | 5621.0 |
| rtpengine | total_managed_sessions | 0.0 | 2.0 | 2.0 |
| rtpengine | average_mos | 0.0 | 4.0 | 4.0 |
| rtpengine | total_number_of_end_to_end_round_trip_time_samples | 0.0 | 21.0 | 21.0 |
| rtpengine | sum_of_all_mos_square_values_sampled | 0.0 | 301.72 | 301.72 |
| rtpengine | total_relayed_bytes_(userspace) | 0.0 | 16660.0 | 16660.0 |
| rtpengine | total_relayed_packets | 0.0 | 341.0 | 341.0 |
| rtpengine | sum_of_all_jitter_(reported)_values_sampled | 0.0 | 126.0 | 126.0 |
| rtpengine | packet_loss_standard_deviation | 0.0 | 18.0 | 18.0 |
| rtpengine | sum_of_all_packet_loss_square_values_sampled | 0.0 | 18065.0 | 18065.0 |
| rtpengine | sum_of_all_end_to_end_round_trip_time_square_values_sampled | 0.0 | 793484081.0 | 793484081.0 |
| rtpengine | total_number_of_mos_samples | 0.0 | 18.0 | 18.0 |
| rtpengine | total_relayed_bytes | 0.0 | 16660.0 | 16660.0 |
| scscf | cdp:replies_response_time | 1377.0 | 2312.0 | 935.0 |
| scscf | core:rcv_requests_register | 12.0 | 22.0 | 10.0 |
| scscf | ims_registrar_scscf:sar_replies_response_time | 605.0 | 1088.0 | 483.0 |
| scscf | core:rcv_requests_invite | 0.0 | 8.0 | 8.0 |
| scscf | ims_auth:mar_replies_response_time | 772.0 | 1224.0 | 452.0 |
| scscf | ims_auth:mar_replies_received | 6.0 | 11.0 | 5.0 |
| scscf | dialog_ng:processed | 0.0 | 8.0 | 8.0 |
| scscf | ims_registrar_scscf:accepted_regs | 6.0 | 11.0 | 5.0 |
| scscf | ims_registrar_scscf:sar_replies_received | 6.0 | 11.0 | 5.0 |
| scscf | cdp:replies_received | 12.0 | 22.0 | 10.0 |
| upf | fivegs_ep_n3_gtp_indatapktn3upf | 66.0 | 802.0 | 736.0 |
| upf | fivegs_ep_n3_gtp_outdatapktn3upf | 32.0 | 641.0 | 609.0 |
| upf | fivegs_ep_n3_gtp_outdatavolumeqosleveln3upf | 21072.0 | 115936.0 | 94864.0 |
| upf | fivegs_ep_n3_gtp_indatavolumeqosleveln3upf | 15410.0 | 112744.0 | 97334.0 |

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 0.76 (threshold: 0.70, trained on 99 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following specific metrics were flagged as the top contributors to the anomaly. These MUST be reflected in your layer ratings:

| Component | Metric | Current | Learned Normal | Severity |
|-----------|--------|---------|---------------|----------|
| rtpengine | average_packet_loss | 22.00 | 0.00 | HIGH |
| rtpengine | packet_loss_standard_deviation | 18.00 | 0.00 | HIGH |
| scscf | ims_auth:mar_avg_response_time | 127.00 | 88.89 | HIGH |
| scscf | ims_registrar_scscf:sar_avg_response_time | 102.00 | 119.92 | MEDIUM |
| icscf | ims_icscf:uar_avg_response_time | 76.00 | 61.39 | MEDIUM |
| normalized | upf.gtp_indatapktn3upf_per_ue | 3.79 | 2.58 | LOW |
| icscf | cdp:average_response_time | 67.00 | 58.83 | LOW |
| normalized | upf.gtp_outdatapktn3upf_per_ue | 3.56 | 2.50 | LOW |
| normalized | pcscf.dialogs_per_ue | 0.00 | 0.65 | LOW |
| derived | upf_activity_during_calls | 1.00 | 0.39 | LOW |

## Network Analysis (Phase 1)

**Summary:** The network is experiencing a critical media plane failure due to severe packet loss at the RTPEngine, with secondary impacts on IMS signaling.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | All infrastructure components (mongo, mysql, dns) are running and responsive. |
| **ran** | 🟢 GREEN | RAN components are stable, with 2 UEs connected to the gNB and AMF. |
| **core** | 🟡 YELLOW | Minor anomalies detected in UPF throughput metrics, but the primary fault lies downstream in the IMS layer. The UPF is on the path to the failing component. |
| **ims** | 🔴 RED | Critical failure at RTPEngine, which is experiencing severe packet loss on its network interface. This is causing media plane disruption and cascading IMS signaling delays. |

**CORE evidence:**
- upf.gtp_indatapktn3upf_per_ue = 3.79 (Learned Normal: 2.58) per AnomalyScreener
- upf.gtp_outdatapktn3upf_per_ue = 3.56 (Learned Normal: 2.50) per AnomalyScreener

**IMS evidence:**
- rtpengine: average_packet_loss = 22.00 (Screener flag: HIGH)
- measure_rtt from pcscf to rtpengine shows 33.3% packet loss.
- measure_rtt from upf to rtpengine shows 33.3% packet loss.
- get_dp_quality_gauges shows recent packet loss of 20.62 at RTPEngine.
- scscf: ims_auth:mar_avg_response_time = 127.00 (Screener flag: HIGH)

**Suspect components:**

- **rtpengine** (high): The AnomalyScreener flagged rtpengine with HIGH severity for packet loss. This was confirmed by 'measure_rtt' from two independent neighbors (pcscf, upf), both showing 33% packet loss to rtpengine's IP. This indicates the fault is localized to rtpengine's own network interface.
- **scscf** (low): Flagged by the screener for high Diameter response times. However, RTT measurements to S-CSCF are clean, suggesting it is a victim of downstream issues (like media plane failure causing SIP session timeouts/retries) rather than the root cause.

**Investigation hint:** The investigation should immediately focus on the 'rtpengine' container. The concurrent packet loss observed from both the UPF and P-CSCF strongly indicates a fault on the rtpengine container's own network interface, not an upstream issue. Examine kernel-level network statistics (e.g., using 'netstat -i' or 'tc -s qdisc') inside the rtpengine container to check for interface errors, drops, or buffer overflows. The elevated IMS response times are likely secondary symptoms of call failures caused by this media plane collapse.

**Tools called:** get_vonr_components, get_network_topology, get_network_status, get_nf_metrics, get_dp_quality_gauges, read_env_config, measure_rtt, compare_to_baseline, check_stack_rules, get_causal_chain_for_component


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
**Citations:** 0/0 verified

```
Investigator was intentionally skipped (Network Analyst diagnosis was definitive). Validating Network Analyst evidence only.
Network Analyst made 10 tool calls. Evidence validation: 0/0 NA citations verified.
Verdict: clean. Confidence: high.

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
```

## Ground Truth

**Failure domain:** ims_media  
**Protocol impact:** RTP  
**Affected components:** rtpengine  
**Severity:** degraded

## Agent Diagnosis

**Model:** v5-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 101.5s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: The network is experiencing a critical media plane failure due to severe packet loss localized to the RTPEngine's network interface, causing call quality degradation and secondary IMS signaling delays.
> - **timeline**:
>     1.  The RTPEngine begins experiencing severe packet loss (~22-33%) on its network interface.
>     2.  RTT measurements from both the UPF and P-CSCF confirm this packet loss is isolated to the RTPEngine.
>     3.  The loss of media packets disrupts active VoNR calls, leading to media plane failure.
>     4.  As a secondary effect, SIP session failures and timeouts cause high response time alarms in signaling components like the S-CSCF.
> - **root_cause**: The fault is localized to the `rtpengine` component, which is suffering from a high rate of packet loss on its own network interface. This is not an upstream network issue, as confirmed by clean RTT measurements to other components and simultaneous packet loss reports from two independent neighbors (UPF and P-CSCF) pointing specifically to `rtpengine`.
> - **affected_components**:
>     - `rtpengine`: Root Cause
>     - `scscf`: Symptomatic
> - **recommendation**: The investigation should focus exclusively on the `rtpengine` container. Verify kernel-level network statistics inside the container to identify interface errors, drops, or buffer overflows that would explain the observed packet loss.
> - **confidence**: high
> - **explanation**: The root cause is a media plane failure originating at the RTPEngine. Network analysis confirmed severe packet loss (22%) at this component. This was corroborated by active RTT probes from both the UPF and P-CSCF, which both reported ~33% packet loss when communicating with the RTPEngine. This isolates the fault to the RTPEngine itself. The elevated signaling delays seen at the S-CSCF are a secondary symptom caused by call failures resulting from this media plane collapse. The 5G core, RAN, and infrastructure layers are operating correctly.

### Scoring Breakdown

**Overall score: 100%**

**Scorer assessment:** The agent provided an excellent and highly accurate diagnosis, correctly identifying the root cause, affected component, severity, fault type, and layer, with appropriate confidence.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | Yes | The agent correctly identified 'packet loss on the RTPEngine's network interface' as the root cause, which perfectly matches the simulated failure mode. |
| Component overlap | 100% | The agent correctly identified 'rtpengine' as the primary affected component (root cause). It also correctly identified 'scscf' as a symptomatic component, showing good causal reasoning. |
| Severity correct | Yes | The agent described the issue as 'call quality degradation' and 'severe packet loss (~22-33%)', which accurately reflects a degradation rather than a complete outage, matching the 30% packet loss simulation. |
| Fault type identified | Yes | The agent explicitly identified 'packet loss' as the fault type, which is precisely what was simulated. |
| Layer accuracy | Yes | The agent correctly attributed the RTPEngine failure to the 'ims' layer, rating it RED, which aligns with the ground truth that 'rtpengine' belongs to the IMS layer. |
| Confidence calibrated | Yes | The agent stated 'high' confidence, which is appropriate given the accuracy and detail of its diagnosis, supported by multiple pieces of evidence. |

**Ranking position:** #1 — The agent clearly identified 'rtpengine' as the 'Root Cause' and listed it as the primary suspect component.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 78,854 |
| Output tokens | 1,956 |
| Thinking tokens | 6,186 |
| **Total tokens** | **86,996** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| NetworkAnalystAgent | 80,190 | 15 | 5 |
| PatternMatcherAgent | 0 | 0 | 0 |
| EvidenceValidatorAgent | 0 | 0 | 0 |
| SynthesisAgent | 6,806 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 232.1s
