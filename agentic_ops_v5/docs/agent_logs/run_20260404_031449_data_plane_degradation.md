# Episode Report: Data Plane Degradation

**Agent:** v5  
**Episode ID:** ep_20260404_031334_data_plane_degradation  
**Date:** 2026-04-04T03:13:34.745752+00:00  
**Duration:** 74.4s  

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

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

### Metrics Changes

| Node | Metric | Baseline | Current | Delta |
|------|--------|----------|---------|-------|
| icscf | cdp:average_response_time | 82.0 | 80.0 | -2.0 |
| icscf | ims_icscf:lir_replies_response_time | 154.0 | 222.0 | 68.0 |
| icscf | cdp:replies_received | 8.0 | 9.0 | 1.0 |
| icscf | ims_icscf:lir_replies_received | 2.0 | 3.0 | 1.0 |
| icscf | cdp:replies_response_time | 658.0 | 726.0 | 68.0 |
| icscf | ims_icscf:lir_avg_response_time | 77.0 | 74.0 | -3.0 |
| icscf | core:rcv_requests_invite | 2.0 | 3.0 | 1.0 |
| pcscf | httpclient:connfail | 12.0 | 19.0 | 7.0 |
| pcscf | core:rcv_requests_options | 11.0 | 16.0 | 5.0 |
| pcscf | httpclient:connok | 0.0 | 2.0 | 2.0 |
| pcscf | dialog_ng:processed | 0.0 | 2.0 | 2.0 |
| pcscf | dialog_ng:active | 0.0 | 2.0 | 2.0 |
| pcscf | sl:1xx_replies | 4.0 | 6.0 | 2.0 |
| pcscf | core:rcv_requests_invite | 0.0 | 2.0 | 2.0 |
| rtpengine | total_number_of_packet_loss_samples | 66.0 | 75.0 | 9.0 |
| rtpengine | owned_sessions | 0.0 | 1.0 | 1.0 |
| rtpengine | average_packet_loss | 31.0 | 27.0 | -4.0 |
| rtpengine | total_number_of_discrete_round_trip_time_samples | 66.0 | 75.0 | 9.0 |
| rtpengine | end_to_end_round_trip_time_standard_deviation | 2620.0 | 2613.0 | -7.0 |
| rtpengine | sum_of_all_end_to_end_round_trip_time_values_sampled | 430699.0 | 484971.0 | 54272.0 |
| rtpengine | bytes_per_second_(userspace) | 0.0 | 167.0 | 167.0 |
| rtpengine | sum_of_all_end_to_end_round_trip_time_square_values_sampled | 3263763705.0 | 3648342637.0 | 384578932.0 |
| rtpengine | average_end_to_end_round_trip_time | 6525.0 | 6466.0 | -59.0 |
| rtpengine | total_number_of_jitter_(reported)_samples | 66.0 | 75.0 | 9.0 |
| rtpengine | packet_loss_standard_deviation | 25.0 | 26.0 | 1.0 |
| rtpengine | packets_per_second_(total) | 0.0 | 4.0 | 4.0 |
| rtpengine | sum_of_all_jitter_(reported)_square_values_sampled | 50.0 | 61.0 | 11.0 |
| rtpengine | sum_of_all_discrete_round_trip_time_square_values_sampled | 822114055.0 | 925473358.0 | 103359303.0 |
| rtpengine | total_sessions | 0.0 | 1.0 | 1.0 |
| rtpengine | sum_of_all_jitter_(reported)_values_sampled | 50.0 | 57.0 | 7.0 |
| rtpengine | sum_of_all_mos_square_values_sampled | 1133.18 | 1281.1 | 147.91999999999985 |
| rtpengine | sum_of_all_mos_values_sampled | 264.6 | 299.0 | 34.39999999999998 |
| rtpengine | sum_of_all_discrete_round_trip_time_values_sampled | 218197.0 | 247654.0 | 29457.0 |
| rtpengine | packets_per_second_(userspace) | 0.0 | 4.0 | 4.0 |
| rtpengine | discrete_round_trip_time_standard_deviation | 1235.0 | 1198.0 | -37.0 |
| rtpengine | bytes_per_second_(total) | 0.0 | 167.0 | 167.0 |
| rtpengine | userspace_only_media_streams | 0.0 | 2.0 | 2.0 |
| rtpengine | average_discrete_round_trip_time | 3306.0 | 3302.0 | -4.0 |
| rtpengine | total_number_of_end_to_end_round_trip_time_samples | 66.0 | 75.0 | 9.0 |
| rtpengine | total_relayed_bytes_(userspace) | 30078.0 | 38402.0 | 8324.0 |
| rtpengine | total_relayed_packets_(userspace) | 834.0 | 1010.0 | 176.0 |
| rtpengine | total_relayed_bytes | 30078.0 | 38402.0 | 8324.0 |
| rtpengine | total_relayed_packets | 834.0 | 1010.0 | 176.0 |
| rtpengine | total_number_of_mos_samples | 63.0 | 71.0 | 8.0 |
| scscf | dialog_ng:processed | 0.0 | 2.0 | 2.0 |
| scscf | dialog_ng:active | 0.0 | 2.0 | 2.0 |
| scscf | core:rcv_requests_invite | 0.0 | 2.0 | 2.0 |
| smf | bearers_active | 4.0 | 6.0 | 2.0 |
| upf | fivegs_ep_n3_gtp_indatapktn3upf | 1620.0 | 1788.0 | 168.0 |
| upf | fivegs_ep_n3_gtp_outdatapktn3upf | 872.0 | 1035.0 | 163.0 |
| upf | fivegs_ep_n3_gtp_outdatavolumeqosleveln3upf | 96076.0 | 116317.0 | 20241.0 |
| upf | fivegs_ep_n3_gtp_indatavolumeqosleveln3upf | 105952.0 | 124027.0 | 18075.0 |

## Pattern Match (Phase 2)

```
{"matched": false, "top_diagnosis": "No matching signature found", "confidence": "low", "failure_domain": "unknown", "matched_signatures": [], "baseline_anomalies": {"smf": [{"metric": "bearers_active", "expected": 4.0, "actual": 6.0, "alarm_if": "", "note": "Rises to 6 during active VoNR call (2 dedicated QoS flows for voice)"}], "scscf": [{"metric": "dialog_ng:active", "expected": 0.0, "actual": 2.0, "alarm_if": "", "note": ""}], "pcscf": [{"metric": "dialog_ng:active", "expected": 0.0, "actua
```

## Anomaly Analysis (Phase 3)

*No output produced.*

## Investigation Instruction (Phase 4)

> Instruction generation failed. Perform a full bottom-up investigation: transport first, then core, then application. Cite tool outputs.

## Ground Truth

**Failure domain:** data_plane  
**Protocol impact:** GTP-U  
**Affected components:** upf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v5-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 44.1s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> Investigation failed: 'Context variable not found: `anomaly_analysis`.'

### Scoring Breakdown

**Overall score: 0%**

**Scorer assessment:** The agent failed to provide any diagnosis due to an internal error, resulting in a score of 0 across all dimensions.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | No | The agent failed to provide any diagnosis, instead returning an error message. It did not identify 'packet loss on UPF' as the root cause. |
| Component overlap | 0% | The agent did not identify any component, as it returned an error message. |
| Severity correct | No | The agent did not provide any diagnosis or severity assessment. |
| Fault type identified | No | The agent did not identify any fault type, as it returned an error message. |
| Confidence calibrated | No | The agent returned an error message indicating a failure to perform an investigation, rather than a diagnosis with a confidence level. Therefore, it cannot be calibrated. |

**Ranking:** No diagnosis was provided, so no ranking is applicable.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 22,168 |
| Output tokens | 782 |
| Thinking tokens | 1,179 |
| **Total tokens** | **24,129** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| TriageAgent | 19,633 | 4 | 5 |
| PatternMatcherAgent | 0 | 0 | 0 |
| AnomalyDetectorAgent | 4,496 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 49.1s
