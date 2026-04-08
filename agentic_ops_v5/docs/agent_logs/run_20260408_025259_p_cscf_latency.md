# Episode Report: P-CSCF Latency

**Agent:** v5  
**Episode ID:** ep_20260408_024118_p_cscf_latency  
**Date:** 2026-04-08T02:41:19.212260+00:00  
**Duration:** 700.1s  

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
- **Nodes with significant deltas:** 2
- **Nodes with any drift:** 4

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

### Metrics Changes

| Node | Metric | Baseline | Current | Delta |
|------|--------|----------|---------|-------|
| pcscf | script:register_success | 13.0 | 22.0 | 9.0 |
| pcscf | core:rcv_requests_invite | 30.0 | 66.0 | 36.0 |
| pcscf | sl:1xx_replies | 56.0 | 110.0 | 54.0 |
| pcscf | core:rcv_requests_register | 92.0 | 164.0 | 72.0 |
| pcscf | sl:4xx_replies | 10.0 | 25.0 | 15.0 |
| pcscf | script:register_time | 158681.0 | 287440.0 | 128759.0 |
| scscf | ims_registrar_scscf:sar_replies_received | 13.0 | 22.0 | 9.0 |
| scscf | ims_registrar_scscf:accepted_regs | 13.0 | 22.0 | 9.0 |
| scscf | cdp:replies_received | 26.0 | 44.0 | 18.0 |
| scscf | core:rcv_requests_register | 26.0 | 44.0 | 18.0 |
| scscf | ims_registrar_scscf:sar_replies_response_time | 1486.0 | 2413.0 | 927.0 |
| scscf | ims_auth:mar_replies_received | 13.0 | 22.0 | 9.0 |
| scscf | ims_auth:mar_replies_response_time | 1592.0 | 2521.0 | 929.0 |
| scscf | cdp:replies_response_time | 3078.0 | 4934.0 | 1856.0 |

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 1.00 (threshold: 0.70, trained on 50 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following specific metrics were flagged as the top contributors to the anomaly. These MUST be reflected in your layer ratings:

| Component | Metric | Current | Learned Normal | Severity |
|-----------|--------|---------|---------------|----------|
| pcscf | core:rcv_requests_register_rate | 3531.30 | 0.08 | HIGH |
| pcscf | core:rcv_requests_invite_rate | 1324.24 | 0.04 | HIGH |
| icscf | core:rcv_requests_register_rate | 2648.48 | 0.08 | HIGH |
| pcscf | sl:1xx_replies_rate | 2207.06 | 0.12 | HIGH |
| icscf | cdp:replies_received_rate | 882.83 | 0.06 | HIGH |
| pcscf | httpclient:connfail_rate | 882.83 | 0.27 | HIGH |
| pcscf | sl:4xx_replies_rate | 441.41 | 0.00 | HIGH |
| scscf | cdp:replies_received_rate | 882.83 | 0.08 | HIGH |
| scscf | core:rcv_requests_register_rate | 882.83 | 0.08 | HIGH |
| upf | fivegs_ep_n3_gtp_indatapktn3upf_rate | 7945.43 | 5.04 | HIGH |

## Network Analysis (Phase 1)

**Summary:** The 5G core is down due to a critical failure of the Service Communication Proxy (SCP), which has exited, causing cascading control plane failures across the stack.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | All infrastructure components (mongo, mysql, dns) are running and connected. |
| **ran** | 🟡 YELLOW | RAN is connected but cannot provide service due to core failure. |
| **core** | 🔴 RED | Fatal failure: The Service Communication Proxy (scp) is down, breaking the 5G control plane. |
| **ims** | 🟡 YELLOW | IMS components are running but experiencing severe signaling storms and errors, likely as a cascading symptom of the core network failure. |

**RAN evidence:**
- AMF reports gNB and UEs are connected (gnb=1, ran_ue=2), but service is unavailable due to the core network failure.

**CORE evidence:**
- The 'scp' container has exited (per get_network_status).
- get_network_topology shows 9 INACTIVE SBI links to the exited 'scp' container, breaking all inter-NF communication.

**IMS evidence:**
- P-CSCF flagged by AnomalyScreener for extremely high SIP REGISTER and INVITE request rates.
- P-CSCF shows high rate of 4xx replies (sl:4xx_replies_rate = 441.41 vs 0.00 normal), indicating client-side errors.
- I-CSCF shows Diameter timeouts (cdp:timeout=1.0), indicating problems communicating with HSS or S-CSCF.

**Suspect components:**

- **scp** (high): The 'scp' container has exited, as confirmed by get_network_status and get_network_topology. This is a critical failure causing 9 inactive SBI links and breaking inter-NF communication in the 5G core.
- **pcscf** (medium): Top-flagged component by AnomalyScreener with HIGH severity 'core:rcv_requests_register_rate' (3531.30 vs 0.08 normal). It is the epicenter of the signaling storm, though this is a cascading symptom of the upstream SCP failure.

**Investigation hint:** The root cause is the failure of the 'scp' container. All other anomalies, particularly the signaling storm seen at the P-CSCF and other IMS components, are downstream symptoms of the broken 5G core control plane. Start by investigating the logs of the 'scp' container to determine the reason for its exit. Do not waste time debugging IMS components until the core 'scp' is restored and all SBI links are active.

**Tools called:** get_vonr_components, get_network_topology, get_network_status, get_nf_metrics, get_dp_quality_gauges, compare_to_baseline, check_stack_rules


## Pattern Match (Phase 2)

**❌ Match:** No matching signature found

- **Confidence:** low
- **Failure domain:** unknown
- **Baseline anomalies:** 2 metrics across 2 components


## Investigation Instruction (Phase 3)

> Anomalies detected in `core` (RED), and `ims`, `ran` (YELLOW, as cascading effects). Suspect components: `scp` (high confidence), `pcscf` (medium confidence, symptom).
>
> PRIMARY INVESTIGATION FOCUS: The `scp` container.
>
> FIRST: Per the Hierarchy of Truth (Transport > Core > Application), run `measure_rtt` from a neighboring 5G core component (e.g., `amf` or `smf`) to the expected IP of the `scp` service. While `scp` is reported as 'exited', confirm network unreachability from an active component.
>
> NEXT: The most critical immediate step is to determine *why* the `scp` container exited. Get the `scp` container logs: `get_container_logs scp`.
>
> Do NOT investigate the IMS signaling storm at `pcscf` or `icscf` (high SIP REGISTER/INVITE rates, 4xx replies, Diameter timeouts) at this stage. These are direct, cascading symptoms of the core control plane failure. Re-evaluate IMS only after the `scp` container is confirmed running and all its SBI links are active (verify with `get_network_topology` and `get_network_status`).

## Evidence Validation (Phase 5)

**Verdict:** clean
**Investigator confidence:** high
**Citations:** 13/13 verified

```
Evidence validation: 13/13 citations verified (0 unmatched).
Verdict: clean. Investigator confidence: high.
```

## Ground Truth

**Failure domain:** ims_signaling  
**Protocol impact:** SIP  
**Affected components:** pcscf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v5-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 125.5s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ```json
> {
>   "causes": [
>     {
>       "summary": "The Service Communication Proxy (SCP) crashed due to a fatal software defect, causing a complete outage of the 5G core control plane.",
>       "timeline": [
>         {
>           "level": "INFO",
>           "finding": "The SCP receives a Network Function (NF) profile update from the NRF.",
>           "evidence": "[EVIDENCE: read_container_logs(\"scp\") -> \"(NF-discover) NF Profile updated [type:PCF validity:30s]\"]"
>         },
>         {
>           "level": "ERROR",
>           "finding": "The SCP code fails to handle a null value within the update, triggering a fatal assertion failure.",
>           "evidence": "[EVIDENCE: read_container_logs(\"scp\") -> \"FATAL: add_params_to_uri: Assertion 'val' failed. (../lib/sbi/client.c:361)\"]"
>         },
>         {
>           "level": "FATAL",
>           "finding": "The SCP process aborts, generating a core dump and causing the container to exit.",
>           "evidence": "[EVIDENCE: read_container_logs(\"scp\") -> \"/open5gs_init.sh: line 86: 8 Aborted (core dumped) /mnt/scp/${COMPONENT_NAME}_init.sh\"]"
>         },
>         {
>           "level": "CRITICAL",
>           "finding": "The SCP becomes unreachable, severing all Service Based Interface (SBI) communication links within the 5G core.",
>           "evidence": "[EVIDENCE: measure_rtt(\"amf\", \"172.22.0.35\") -> \"Target 172.22.0.35 is UNREACHABLE from amf...100% packet loss\"]"
>         },
>         {
>           "level": "WARN",
>           "finding": "As a downstream effect, IMS components (P-CSCF) are flooded with client requests that cannot be served, causing a signaling storm.",
>           "evidence": "[EVIDENCE: Network Analysis (Phase 1) -> \"P-CSCF flagged by AnomalyScreener for extremely high SIP REGISTER and INVITE request rates.\"]"
>         }
>       ],
>       "root_cause": "A software defect in the 'scp' container caused the process to crash with an assertion failure ('Assertion 'val' failed') when attempting to process an NF profile update from the NRF. The failure of this central communication proxy resulted in a total collapse of inter-NF communication across the 5G core control plane, leading to a full service outage.",
>       "affected_components": [
>         {
>           "name": "scp",
>           "reason": "Root cause component; process crashed and exited."
>         },
>         {
>           "name": "amf",
>           "reason": "Impacted component; lost communication with all other core NFs via the SCP."
>         },
>         {
>           "name": "smf",
>           "reason": "Impacted component; lost communication with all other core NFs via the SCP."
>         },
>         {
>           "name": "pcscf",
>           "reason": "Symptomatic component; experiencing signaling storms due to the upstream core failure."
>         },
>         {
>           "name": "icscf",
>           "reason": "Symptomatic component; experiencing timeouts due to the upstream core failure."
>         }
>       ],
>       "recommendation": "The immediate focus should be on restoring the SCP service. Before restarting the container, investigate if the core dump file mentioned in the logs can be preserved for software vendor analysis. After restoring the service, verify that the 'scp' container is running and that all associated SBI links are active via network topology checks.",
>       "confidence": "high",
>       "explanation": "The root cause of the outage is a fatal software crash in the Service Communication Proxy (SCP), a critical component for routing all 5G core control plane messages. Evidence from the container logs confirms the process aborted due to an unhandled value during an NF discovery update. The subsequent unreachability of the SCP broke all communication between network functions, causing the service outage. The signaling storm observed in the IMS layer is a direct symptom of this core failure and will resolve once the SCP is restored."
>     }
>   ]
> }
> ```

### Scoring Breakdown

**Overall score: 0%**

**Scorer assessment:** The agent completely misdiagnosed the failure, identifying an SCP crash and outage instead of P-CSCF latency, and incorrectly assessed the severity and fault type with high confidence.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | No | The simulated failure was P-CSCF latency, leading to transaction timeouts. The agent diagnosed an SCP crash due to a software defect, resulting in a complete outage and 100% packet loss for the SCP. These are entirely different root causes and failure modes. |
| Component overlap | 0% | The primary affected component in the simulation was 'pcscf' experiencing latency. The agent identified 'scp' as the root cause component and 'pcscf' only as a symptomatic component experiencing a 'signaling storm' due to the SCP failure, which is incorrect for the simulated scenario. |
| Severity correct | No | The simulated failure was a degradation (latency). The agent diagnosed a 'complete outage' and '100% packet loss', which is a much more severe assessment than the actual degradation. |
| Fault type identified | No | The simulated fault type was network degradation (latency). The agent identified a component crash/unreachability ('SCP crashed', '100% packet loss'), which is a different class of failure. |
| Confidence calibrated | No | The agent expressed 'high' confidence for a diagnosis that is completely incorrect across all dimensions (root cause, component, severity, fault type). This indicates poor calibration. |

**Ranking:** The agent provided only one primary cause, which was incorrect. The correct cause (P-CSCF latency) was not identified.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 73,058 |
| Output tokens | 3,886 |
| Thinking tokens | 7,942 |
| **Total tokens** | **84,886** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| NetworkAnalystAgent | 38,728 | 7 | 3 |
| PatternMatcherAgent | 0 | 0 | 0 |
| InstructionGeneratorAgent | 6,747 | 0 | 1 |
| InvestigatorAgent | 29,559 | 3 | 3 |
| EvidenceValidatorAgent | 0 | 0 | 0 |
| SynthesisAgent | 9,852 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 700.0s
