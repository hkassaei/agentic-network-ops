# Episode Report: P-CSCF Latency

**Agent:** v5  
**Episode ID:** ep_20260406_171449_p_cscf_latency  
**Date:** 2026-04-06T17:14:49.792000+00:00  
**Duration:** 149.6s  

---

## Scenario

**Category:** network  
**Blast radius:** single_nf  
**Description:** Inject 500ms latency on the P-CSCF (SIP edge proxy). SIP T1 timer is 500ms, so REGISTER transactions will start timing out. Tests IMS resilience to WAN-like latency on the signaling path.

## Faults Injected

- **network_latency** on `pcscf` — {'delay_ms': 1500, 'jitter_ms': 50}

## Baseline (Pre-Fault)

Stack phase before injection: **ready**
All containers running at baseline.

## Fault Propagation Verification

**Verdict:** ✅ `confirmed`

- **Wait:** 30s
- **Actual elapsed:** 30.0s
- **Nodes with significant deltas:** 2
- **Nodes with any drift:** 4

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

### Metrics Changes

| Node | Metric | Baseline | Current | Delta |
|------|--------|----------|---------|-------|
| pcscf | sl:1xx_replies | 8.0 | 12.0 | 4.0 |
| pcscf | script:register_time | 8527.0 | 30155.0 | 21628.0 |
| pcscf | script:register_success | 4.0 | 6.0 | 2.0 |
| pcscf | core:rcv_requests_register | 10.0 | 26.0 | 16.0 |
| scscf | cdp:replies_received | 8.0 | 12.0 | 4.0 |
| scscf | ims_auth:mar_replies_response_time | 448.0 | 652.0 | 204.0 |
| scscf | ims_registrar_scscf:accepted_regs | 4.0 | 6.0 | 2.0 |
| scscf | ims_auth:mar_replies_received | 4.0 | 6.0 | 2.0 |
| scscf | ims_registrar_scscf:sar_replies_received | 4.0 | 6.0 | 2.0 |
| scscf | cdp:replies_response_time | 881.0 | 1397.0 | 516.0 |
| scscf | ims_registrar_scscf:sar_replies_response_time | 433.0 | 745.0 | 312.0 |
| scscf | core:rcv_requests_register | 8.0 | 12.0 | 4.0 |

## Network Analysis (Phase 1)

**Summary:** The 5G SA and IMS network stack appears to be fully healthy and in a normal idle state.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | All infrastructure components (mongo, mysql, dns) are running and connected. |
| **ran** | 🟢 GREEN | The gNB is connected to the AMF and both UEs are attached. |
| **core** | 🟢 GREEN | All 5G Core components are running, connected, and have established PDU sessions. The data plane is idle, which is expected. |
| **ims** | 🟢 GREEN | All IMS components are running and UEs are registered. Media plane is idle, which is expected. |

**Investigation hint:** No anomalies were detected across the network stack. All components report a healthy status, UEs are registered, and the data plane is idle, which is the expected state when no call is active. The `httpclient:connfail` metric at the P-CSCF was confirmed to be within its normal baseline range. The perceived issue may be intermittent, may have occurred outside the 60-second observation window, or may have already resolved. Continued monitoring is recommended to observe if any new anomalies appear during a service attempt.

**Tools called:** get_vonr_components, get_network_topology, get_network_status, get_nf_metrics, get_dp_quality_gauges, compare_to_baseline, check_stack_rules


## Pattern Match (Phase 2)

**❌ Match:** No matching signature found

- **Confidence:** low
- **Failure domain:** unknown


## Investigation Instruction (Phase 3)

> No clear pattern or anomaly was identified in the provided analysis. The network stack appears fully healthy and in a normal idle state, with all components running, UEs registered, and data/media planes inactive, which is the expected behavior. The `httpclient:connfail` metric at the P-CSCF was confirmed to be within its normal baseline range. The perceived issue may be intermittent, may have occurred outside the 60-second observation window, or may have already resolved.
>
> Your ONLY job is to perform a full bottom-up investigation to verify the healthy state or uncover any new anomalies.
> 1.  **Transport Layer First:** Begin by checking network reachability and latency between all identified components. Use `measure_rtt` between components in the `get_network_topology` output to confirm no basic connectivity issues.
> 2.  **Core Network Layer:** Systematically review metrics for all 5G Core and RAN components (`get_nf_metrics`, `get_dp_quality_gauges`, `get_network_status`) to ensure all are connected, registering, and processing as expected for an idle network.
> 3.  **Application Layer:** Check relevant logs for P-CSCF, S-CSCF, and I-CSCF for any errors or warnings (`get_ims_logs`) that might indicate application-level issues not captured by aggregated metrics.
> 4.  **Baseline Comparison:** Continue to `compare_to_baseline` for all relevant metrics to catch subtle deviations.
> 5.  **Monitor:** Given the idle state, continued monitoring of `get_nf_metrics`, `get_dp_quality_gauges`, and `get_ims_logs` is recommended to observe if any new anomalies appear during a service attempt.
>
> Cite tool outputs for every claim made. Do NOT attempt to initiate calls or modify network state.

## Ground Truth

**Failure domain:** ims_signaling  
**Protocol impact:** SIP  
**Affected components:** pcscf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v5-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 110.0s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ```json
> {
>   "causes": [
>     {
>       "summary": "No anomalies were detected; the network is in a healthy, idle state with UEs registered and PDU sessions established.",
>       "timeline": [
>         {
>           "timestamp": "T-60s",
>           "description": "Network analysis begins. All infrastructure, 5G Core, and IMS components are confirmed to be running and interconnected."
>         },
>         {
>           "timestamp": "T-50s",
>           "description": "The gNB is confirmed connected to the AMF, and two UEs are attached to the RAN (evidence: 'ran_ue=2.0 at AMF from get_nf_metrics')."
>         },
>         {
>           "timestamp": "T-40s",
>           "description": "Four PDU sessions are confirmed to be established in the 5G Core (evidence: 'fivegs_upffunction_upf_sessionnbr=4.0 from get_nf_metrics'). Data plane throughput is near-zero, consistent with an idle state."
>         },
>         {
>           "timestamp": "T-30s",
>           "description": "Both UEs are confirmed to be registered with the IMS (evidence: 'ims_usrloc_pcscf:registered_contacts=2.0 from get_nf_metrics'). The media plane (RTPEngine) is idle."
>         },
>         {
>           "timestamp": "T-0s",
>           "description": "Investigation concludes. All metrics indicate a stable and healthy idle state. No active call is in progress."
>         }
>       ],
>       "root_cause": "No root cause of failure was identified. All components across the RAN, 5G Core, and IMS layers are reporting a healthy status. The state of the network is consistent with a normally functioning system in an idle state (no active calls).",
>       "affected_components": [],
>       "recommendation": "The perceived issue may be intermittent, may have occurred outside the 60-second observation window, or may have already resolved. Continued monitoring is recommended to observe if any new anomalies appear during a service attempt, such as placing a VoNR call.",
>       "confidence": "high",
>       "explanation": "The automated analysis confirmed that the entire network stack is healthy. Infrastructure services are running, the gNB is connected, and both UEs are attached to the 5G Core with active PDU sessions. Furthermore, both UEs are successfully registered with the IMS, ready to make or receive calls. The data and media planes are quiet, which is the expected behavior for an idle network. An initial alert on `httpclient:connfail` at the P-CSCF was investigated and confirmed to be within its normal baseline range, indicating no active fault."
>     }
>   ]
> }
> ```

### Scoring Breakdown

**Overall score: 0%**

**Scorer assessment:** The agent completely failed to detect the simulated P-CSCF latency, incorrectly diagnosing the network as healthy and exhibiting poor confidence calibration.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | No | The simulated failure was elevated network latency on the P-CSCF, leading to SIP REGISTER timeouts and IMS registration failures. The agent explicitly stated, 'No root cause of failure was identified' and concluded the network was in a 'healthy, idle state'. |
| Component overlap | 0% | The primary affected component was the P-CSCF. While the agent mentioned an 'initial alert on `httpclient:connfail` at the P-CSCF', it dismissed this as being 'within its normal baseline range' and did not identify P-CSCF as an affected component due to the simulated latency. |
| Severity correct | No | The simulated failure involved significant latency causing timeouts and registration failures, which is a severe degradation or outage for IMS registration. The agent incorrectly assessed the network as 'healthy' and 'idle', indicating no active fault. |
| Fault type identified | No | The simulated fault type was network degradation (latency). The agent failed to identify any fault, concluding the network was healthy. |
| Confidence calibrated | No | The agent stated 'high' confidence in its diagnosis that 'No anomalies were detected' and the network was healthy. This is poorly calibrated as there was a significant, observable failure (P-CSCF latency leading to timeouts). |

**Ranking:** The agent provided only one diagnosis, which was incorrect.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 53,377 |
| Output tokens | 3,314 |
| Thinking tokens | 6,131 |
| **Total tokens** | **62,822** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| NetworkAnalystAgent | 35,212 | 7 | 3 |
| PatternMatcherAgent | 0 | 0 | 0 |
| InstructionGeneratorAgent | 4,618 | 0 | 1 |
| InvestigatorAgent | 15,439 | 2 | 2 |
| EvidenceValidatorAgent | 0 | 0 | 0 |
| SynthesisAgent | 7,553 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 149.6s
