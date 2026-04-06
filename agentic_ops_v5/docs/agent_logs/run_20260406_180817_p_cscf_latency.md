# Episode Report: P-CSCF Latency

**Agent:** v5  
**Episode ID:** ep_20260406_180544_p_cscf_latency  
**Date:** 2026-04-06T18:05:45.076143+00:00  
**Duration:** 151.8s  

---

## Scenario

**Category:** network  
**Blast radius:** single_nf  
**Description:** Inject 500ms latency on the P-CSCF (SIP edge proxy). SIP T1 timer is 500ms, so REGISTER transactions will start timing out. Tests IMS resilience to WAN-like latency on the signaling path.

## Faults Injected

- **network_latency** on `pcscf` — {'delay_ms': 5000, 'jitter_ms': 50}

## Baseline (Pre-Fault)

Stack phase before injection: **ready**
All containers running at baseline.

## Fault Propagation Verification

**Verdict:** ⚠️ `inconclusive`

- **Wait:** 30s
- **Actual elapsed:** 30.0s
- **Nodes with significant deltas:** 0
- **Nodes with any drift:** 1

## Symptoms Observed

Symptoms detected: **No**  
Observation iterations: 1

## Network Analysis (Phase 1)

**Summary:** The network is healthy and stable, with all components running and interconnected, but is currently idle with no active VoNR calls.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | All infrastructure components (mongo, mysql, dns) are running and connected. |
| **ran** | 🟢 GREEN | gNB is connected to the AMF and 2 UEs are attached (ran_ue=2). |
| **core** | 🟢 GREEN | All 5G Core components are healthy. UEs have active PDU sessions. Zero data plane throughput is expected as there are no active calls. |
| **ims** | 🟢 GREEN | IMS components are healthy and UEs are registered. Zero RTP traffic is the expected idle state, as confirmed by the 'idle_data_plane_is_normal' stack rule. |

**Investigation hint:** No anomalies were detected across the stack; all metrics are within their baseline ranges and all components are healthy. The data plane is idle, which is normal as there is no active call in progress. The user's report of 'issues' does not match the observed state. The next step should be to obtain more specific details from the user about the exact nature of the problem (e.g., call setup failure, no audio, registration error) and the precise time it occurred.

**Tools called:** get_vonr_components, get_network_topology, get_network_status, get_nf_metrics, get_dp_quality_gauges, compare_to_baseline, check_stack_rules


## Pattern Match (Phase 2)

**❌ Match:** No matching signature found

- **Confidence:** low
- **Failure domain:** unknown


## Investigation Instruction (Phase 3)

> No clear pattern or anomaly identified. The network analysis indicates that all components are healthy, running, and interconnected, with UEs attached and registered to IMS. The data plane is currently idle, which is normal as no active VoNR calls are in progress. The Pattern Matcher found no matching signatures, and all baseline anomalies are within expected ranges for an idle system.
>
> Perform a full bottom-up investigation to gather more specific data:
>
> 1.  **Transport Layer First:**
>     *   Use `measure_rtt` to confirm basic IP connectivity and latency between key components (e.g., gNB to AMF, AMF to SMF, SMF to UPF, P-CSCF to I-CSCF, I-CSCF to S-CSCF, S-CSCF to UDM/UDR).
>     *   Specifically check connectivity to all listed healthy containers: `mongo`, `nrf`, `scp`, `ausf`, `udr`, `udm`, `amf`, `smf`, `upf`, `pcf`, `dns`, `mysql`, `pyhss`, `icscf`, `scscf`, `pcscf`, `rtpengine`.
>
> 2.  **Core Layer:**
>     *   Re-check all `get_nf_metrics` for all 5G Core NFs (AMF, SMF, UPF, PCF, UDM, UDR, AUSF, NRF, SCP) to ensure no subtle changes have occurred since the last check. Pay attention to `fivegs_pcffunction_pa_policyamassoreq`, `fivegs_pcffunction_pa_policysmassoreq`, `fivegs_smffunction_sm_sessionnbr`, `fivegs_upffunction_upf_sessionnbr`, `pfcp_sessions_active`, `ues_active`, and `bearers_active` to confirm the continued idle, attached state.
>
> 3.  **IMS/Application Layer:**
>     *   Re-check `get_nf_metrics` for IMS components (P-CSCF, I-CSCF, S-CSCF, RTPENGINE). Confirm `ims_usrloc_pcscf:registered_contacts` and `ims_usrloc_scscf:active_contacts` remain at 2.
>     *   Confirm `core:rcv_requests_invite` remains at 0, indicating no call attempts.
>     *   Monitor `get_dp_quality_gauges` for any unexpected traffic or quality degradation if a call were to initiate (though none are expected now).
>
> 4.  **Baseline Comparison:**
>     *   For any metrics collected, use `compare_to_baseline` to confirm they remain consistent with the idle, healthy state.
>
> Cite tool outputs for every claim. The current state is healthy and idle; thus, the user's report is not yet corroborated by network observations. The next step will require more specific information from the user regarding the nature and timing of the reported issues.

## Ground Truth

**Failure domain:** ims_signaling  
**Protocol impact:** SIP  
**Affected components:** pcscf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v5-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 108.8s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - summary: The 5G Core (AMF) has lost all IP connectivity to the Radio Access Network (gNB), a critical failure preventing UEs from accessing the network.
>   timeline:
>   - 1. A transport layer failure occurs, breaking the network path between the AMF and the gNB.
>   - 2. Attempts by the AMF to send packets to the gNB result in 100% packet loss, as confirmed by `measure_rtt`.
>   - 3. The loss of this N2 interface path severs communication between the radio network and the core, making UE attachment and signaling impossible.
>   root_cause: A complete transport layer connectivity failure exists between the `amf` container and the `srs_gnb` container. Packets sent from the AMF to the gNB are being dropped, leading to 100% packet loss.
>   affected_components:
>   - amf
>   - srs_gnb
>   recommendation: Verify IP reachability and routing between the AMF and gNB containers. Check for any network policies, firewall rules, or container networking issues that could be blocking traffic on this specific path.
>   confidence: medium
>   explanation: The initial network analysis was misleading, as it reported a healthy state based on existing UE registrations. However, direct investigation confirmed a complete communication breakdown between the 5G Core's Access and Mobility Management Function (AMF) and the Radio Access Network (gNB). This loss of connectivity on the N2 interface makes it impossible for any UE to communicate with the core network, causing a total service outage.
> 
> - summary: Catastrophic network latency (~5000ms) between the 5G Core and the IMS core is causing service-related procedures to time out.
>   timeline:
>   - 1. A network condition introduces an extreme delay on packets traveling between the AMF and P-CSCF.
>   - 2. Direct measurement confirms the round-trip time (RTT) has increased to nearly 5 seconds.
>   - 3. Any IMS-related signaling, such as for a VoNR call, would time out long before a response is received from the P-CSCF, rendering voice services non-functional.
>   root_cause: A transport layer fault is causing extreme packet delay between the `amf` container and the `pcscf` container. An RTT of ~5000ms is far beyond the tolerance of real-time protocols like SIP.
>   affected_components:
>   - amf
>   - pcscf
>   recommendation: Investigate the network path between the AMF and P-CSCF to identify the source of the extreme latency. Check for potential causes such as network misconfiguration, traffic shaping rules, or resource contention on the host system affecting these specific containers.
>   confidence: medium
>   explanation: In addition to the gNB connectivity loss, the investigation found a debilitating ~5-second network latency between the 5G core (AMF) and the IMS core's entry point (P-CSCF). This delay would cause any real-time communication requests, such as initiating a voice call, to fail due to protocol timeouts. Even if the radio link were active, IMS services would be unusable.

### Scoring Breakdown

**Overall score: 60%**

**Scorer assessment:** The agent correctly identified the type of fault (latency) and the affected component (P-CSCF) with appropriate severity and confidence, but failed to rank this correct diagnosis as the primary cause, instead prioritizing an incorrect diagnosis.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | No | The agent identified the correct root cause (P-CSCF latency) as its second candidate. According to the scoring rules, for 'root_cause_correct' to be true, the correct cause must be ranked as the primary/top candidate. |
| Component overlap | 100% | The agent's second diagnosis correctly identifies 'pcscf' as an affected component, which is the primary component experiencing the simulated latency. It also correctly includes 'amf' as part of the affected path. |
| Severity correct | Yes | The agent's second diagnosis describes the 5000ms latency as 'catastrophic' and leading to services being 'non-functional', which accurately reflects the impact of such a delay on real-time protocols like SIP and IMS registration. |
| Fault type identified | Yes | The agent's second diagnosis clearly identifies the fault type as 'network latency' and 'extreme packet delay' with an RTT of ~5000ms, which directly matches the simulated failure mode. |
| Confidence calibrated | Yes | The agent assigned 'medium' confidence to its second diagnosis, which is correct. Given that it also presented an incorrect primary diagnosis, a medium confidence for the correct one is reasonably calibrated, suggesting some uncertainty or multiple potential issues were being considered. |

**Ranking position:** #2 — The correct root cause (P-CSCF latency) was listed as the second candidate.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 66,422 |
| Output tokens | 3,660 |
| Thinking tokens | 6,932 |
| **Total tokens** | **77,014** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| NetworkAnalystAgent | 36,439 | 7 | 3 |
| PatternMatcherAgent | 0 | 0 | 0 |
| InstructionGeneratorAgent | 4,403 | 0 | 1 |
| InvestigatorAgent | 27,664 | 18 | 3 |
| EvidenceValidatorAgent | 0 | 0 | 0 |
| SynthesisAgent | 8,508 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 151.8s
