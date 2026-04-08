# Episode Report: P-CSCF Latency

**Agent:** v5  
**Episode ID:** ep_20260408_033403_p_cscf_latency  
**Date:** 2026-04-08T03:34:04.211133+00:00  
**Duration:** 787.8s  

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
| pcscf | core:rcv_requests_invite | 99.0 | 138.0 | 39.0 |
| pcscf | script:register_success | 35.0 | 47.0 | 12.0 |
| pcscf | core:rcv_requests_register | 268.0 | 364.0 | 96.0 |
| pcscf | sl:4xx_replies | 36.0 | 49.0 | 13.0 |
| pcscf | script:register_time | 473303.0 | 645566.0 | 172263.0 |
| pcscf | sl:1xx_replies | 169.0 | 232.0 | 63.0 |
| scscf | ims_auth:mar_replies_received | 35.0 | 47.0 | 12.0 |
| scscf | cdp:replies_received | 70.0 | 94.0 | 24.0 |
| scscf | ims_registrar_scscf:sar_replies_response_time | 3936.0 | 5161.0 | 1225.0 |
| scscf | ims_registrar_scscf:accepted_regs | 35.0 | 47.0 | 12.0 |
| scscf | cdp:replies_response_time | 8070.0 | 10845.0 | 2775.0 |
| scscf | core:rcv_requests_register | 70.0 | 94.0 | 24.0 |
| scscf | ims_auth:mar_replies_response_time | 4134.0 | 5684.0 | 1550.0 |
| scscf | ims_registrar_scscf:sar_replies_received | 35.0 | 47.0 | 12.0 |

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 1.00 (threshold: 0.70, trained on 50 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following specific metrics were flagged as the top contributors to the anomaly. These MUST be reflected in your layer ratings:

| Component | Metric | Current | Learned Normal | Severity |
|-----------|--------|---------|---------------|----------|
| pcscf | core:rcv_requests_invite_rate | 1564.07 | 0.04 | HIGH |
| pcscf | sl:1xx_replies_rate | 2085.42 | 0.12 | HIGH |
| pcscf | core:rcv_requests_register_rate | 1564.07 | 0.08 | HIGH |
| icscf | core:rcv_requests_register_rate | 1564.07 | 0.08 | HIGH |
| pcscf | httpclient:connfail_rate | 1042.71 | 0.27 | HIGH |
| pcscf | sl:4xx_replies_rate | 521.36 | 0.00 | HIGH |
| icscf | cdp:replies_received_rate | 521.36 | 0.06 | HIGH |
| scscf | cdp:replies_received_rate | 521.36 | 0.08 | HIGH |
| scscf | core:rcv_requests_register_rate | 521.36 | 0.08 | HIGH |
| upf | fivegs_ep_n3_gtp_indatapktn3upf_rate | 5213.55 | 5.04 | HIGH |

## Network Analysis (Phase 1)

**Summary:** The network experienced a massive IMS signaling storm, leading to service degradation.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | All infrastructure components (mongo, mysql, dns) are running and connected. |
| **ran** | 🟢 GREEN | gNB is connected and 2 UEs are attached, which is the baseline healthy state. |
| **core** | 🟡 YELLOW | Core control plane functions appear stable, but the UPF experienced an anomalous high packet rate, likely related to the signaling storm. |
| **ims** | 🔴 RED | A massive SIP request storm at the P-CSCF caused overload, connection failures, and downstream timeouts in the IMS signaling chain. |

**CORE evidence:**
- upf fivegs_ep_n3_gtp_indatapktn3upf_rate was flagged as HIGH severity by the anomaly screener (current: 5213.55, normal: 5.04)

**IMS evidence:**
- pcscf core:rcv_requests_invite_rate was 1564.07 (normal: 0.04)
- pcscf sl:1xx_replies_rate was 2085.42 (normal: 0.12)
- pcscf core:rcv_requests_register_rate was 1564.07 (normal: 0.08)
- pcscf httpclient:connfail_rate was 1042.71 (normal: 0.27)
- pcscf sl:4xx_replies_rate was 521.36 (normal: 0.00)
- icscf is experiencing Diameter timeouts when querying HSS (cdp:timeout=1.0, expected 0).

**Suspect components:**

- **pcscf** (high): The anomaly screener identified P-CSCF as the epicenter of the disturbance, with multiple metrics showing extreme deviation from baseline, including invite, register, and error rates. This indicates it was the entry point for a signaling storm.
- **icscf** (medium): Live metrics show Diameter timeouts (cdp:timeout=1.0), indicating it is failing to get timely responses from the HSS. This is likely a downstream symptom of the overload initiated at the P-CSCF.
- **pyhss** (medium): The timeouts reported by the I-CSCF strongly suggest that the HSS (PyHSS) was unable to handle the high rate of Diameter queries for user location and authentication, making it a key bottleneck in the signaling chain.

**Investigation hint:** The evidence points to a massive SIP signaling storm originating at the P-CSCF, which then cascaded to downstream components. The primary suspect is the P-CSCF. I recommend examining the P-CSCF logs during the event window to identify the source of the anomalous traffic. The timeouts at the I-CSCF and inferred overload at the HSS are likely secondary symptoms of this initial flood. The Investigator should probe the P-CSCF-to-I-CSCF and I-CSCF-to-HSS signaling path to confirm the point of failure and measure response times under load.

**Tools called:** get_vonr_components, get_network_topology, get_network_status, get_nf_metrics, get_dp_quality_gauges, compare_to_baseline, check_stack_rules


## Pattern Match (Phase 2)

**❌ Match:** No matching signature found

- **Confidence:** low
- **Failure domain:** unknown
- **Baseline anomalies:** 2 metrics across 2 components


## Investigation Instruction (Phase 3)

> Anomalies detected in IMS (RED) and Core (YELLOW) layers due to a massive IMS SIP signaling storm. The `pcscf` is identified as the primary suspect and entry point for this storm, exhibiting extremely high `invite`, `register`, `httpclient:connfail`, and `4xx_replies` rates. This overload is causing downstream Diameter timeouts at the `icscf` when querying the `pyhss` (`ims_icscf:uar_timeouts=1.0`). The `upf` also shows high data packet rates, likely as a secondary effect.
>
> Your task is to investigate the cascading effects of this signaling storm, focusing on IMS signaling paths. Do NOT investigate the RAN or Infrastructure layers as they are GREEN.
>
> **FIRST:** Probe transport layer connectivity and latency for the IMS signaling path:
> 1.  Run `measure_rtt` from `pcscf` to `icscf`.
> 2.  Run `measure_rtt` from `icscf` to `pyhss`.
>
> **THEN:** Investigate application and signaling specifics:
> 1.  Examine `pcscf` logs (`get_nf_logs('pcscf')`) during the event window to understand the nature and source of the anomalous SIP traffic (e.g., specific SIP methods, source IPs).
> 2.  Verify current `pcscf` metrics for high error rates and request rates using `get_nf_metrics('pcscf', ['httpclient:connfail', 'sl:4xx_replies', 'core:rcv_requests_invite', 'core:rcv_requests_register'])`.
> 3.  Confirm current `icscf` Diameter timeouts to `pyhss` using `get_nf_metrics('icscf', ['ims_icscf:uar_timeouts', 'cdp:timeout'])`.
> 4.  If transport to `pyhss` is healthy but timeouts persist, check `pyhss` internal health and processing metrics using `get_nf_metrics('pyhss')` to identify potential overload or unresponsiveness during Diameter queries.
> Focus on SIP and Diameter signaling paths for the observed errors.

## Evidence Validation (Phase 5)

**Verdict:** clean
**Investigator confidence:** high
**Citations:** 10/10 verified

```
Evidence validation: 10/10 citations verified (0 unmatched). Investigator: 10 citations from 4 tool calls.
Verdict: clean. Investigator confidence: high.
```

## Ground Truth

**Failure domain:** ims_signaling  
**Protocol impact:** SIP  
**Affected components:** pcscf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v5-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 181.6s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ```json
> {
>   "causes": [
>     {
>       "summary": "The IMS HSS (PyHSS) is overloaded at the application layer, failing to respond to Diameter queries and causing widespread IMS registration and session failures.",
>       "timeline": [
>         {
>           "timestamp": "T-N",
>           "description": "A massive SIP signaling storm, characterized by extremely high REGISTER and INVITE rates, begins at the P-CSCF."
>         },
>         {
>           "timestamp": "T-N+1",
>           "description": "The P-CSCF forwards requests to the I-CSCF, which in turn queries the PyHSS (HSS) for user authorization via Diameter (UAR messages)."
>         },
>         {
>           "timestamp": "T-N+2",
>           "description": "The PyHSS application becomes overwhelmed by the high rate of Diameter queries and fails to respond within the timeout period."
>         },
>         {
>           "timestamp": "T-N+3",
>           "description": "The I-CSCF records Diameter timeouts waiting for the PyHSS (ims_icscf:uar_timeouts = 1.0), causing the signaling chain to fail."
>         },
>         {
>           "timestamp": "T-N+4",
>           "description": "Concurrently, the P-CSCF experiences HTTP client timeouts when trying to communicate with the 5G Core's SCP, indicating broader control plane distress."
>         },
>         {
>           "timestamp": "T-N+5",
>           "description": "The failures result in SIP error responses (4xx replies) and service degradation for end-users."
>         }
>       ],
>       "root_cause": "The primary root cause is an application-level overload of the PyHSS (HSS). A massive SIP signaling storm originating at the P-CSCF created a flood of Diameter UAR (User-Authorization-Request) queries that the PyHSS could not process in time. Investigation confirmed that the transport layer between components is healthy (sub-millisecond RTT), isolating the failure to the PyHSS application itself. A secondary contributing factor is the unresponsiveness of the SCP to the P-CSCF, indicating the control plane overload extends beyond just the HSS.",
>       "affected_components": [
>         "pyhss",
>         "icscf",
>         "pcscf",
>         "scp"
>       ],
>       "recommendation": "Focus investigation on the application health of the PyHSS. Check its internal logs, CPU, memory, and any internal queue metrics to confirm the processing bottleneck. Similarly, investigate the SCP's logs and resource utilization to determine the cause of its unresponsiveness to HTTP requests from the P-CSCF.",
>       "confidence": "high",
>       "explanation": "The network service degradation is caused by an application-level failure within the IMS and 5G control planes, not a network transport issue. A signaling storm originating at the P-CSCF overwhelmed the PyHSS (HSS), which is now unable to process authentication requests in a timely manner. This is confirmed by Diameter timeouts at the I-CSCF despite healthy, sub-millisecond network latency to the PyHSS. A related symptom is the P-CSCF's inability to communicate with the SCP, pointing to a wider application performance problem under load."
>     }
>   ]
> }
> ```

### Scoring Breakdown

**Overall score: 40%**

**Scorer assessment:** The agent correctly identified the severity and that the P-CSCF was involved, but completely missed the root cause, incorrectly attributing it to application overload rather than network latency, and was overconfident in its incorrect diagnosis.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | No | The simulated failure was elevated network latency on the P-CSCF. The agent diagnosed an application-level overload of the PyHSS (HSS) and SCP unresponsiveness, explicitly stating that the 'transport layer between components is healthy', which directly contradicts the actual simulated failure. |
| Component overlap | 100% | The agent correctly identified 'pcscf' as an affected component, even though it misidentified its role in the root cause. |
| Severity correct | Yes | The agent correctly identified 'widespread IMS registration and session failures' and 'service degradation for end-users', which matches the impact of the simulated latency causing timeouts. |
| Fault type identified | No | The simulated fault type was 'network degradation' (latency). The agent explicitly ruled out a 'network transport issue' and instead identified 'application-level overload' and 'timeouts' as the fault type, attributing them to application issues rather than network degradation. |
| Confidence calibrated | No | The agent stated 'high' confidence despite completely misidentifying the root cause and the underlying fault type. It confidently asserted the transport layer was healthy when it was the source of the problem. |

**Ranking:** The agent provided only one diagnosis, which was incorrect.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 152,829 |
| Output tokens | 5,645 |
| Thinking tokens | 11,157 |
| **Total tokens** | **169,631** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| NetworkAnalystAgent | 65,336 | 10 | 5 |
| PatternMatcherAgent | 0 | 0 | 0 |
| InstructionGeneratorAgent | 7,297 | 0 | 1 |
| InvestigatorAgent | 86,927 | 7 | 7 |
| EvidenceValidatorAgent | 0 | 0 | 0 |
| SynthesisAgent | 10,071 | 0 | 1 |


## Resolution

**Heal method:** scheduled
**Recovery time:** 787.8s

## Post-Run Analysis

### Score: 40% — Investigator probed a healed network, missed the latency

The anomaly screener, NetworkAnalyst, InstructionGenerator, and Evidence Validator all worked well this run. The Investigator cited 10 evidence items (all verified). But it concluded "transport is healthy, sub-millisecond RTT" because by the time it ran `measure_rtt`, the fault had already expired or the network had recovered.

### What worked

**Evidence Validator (Phase 5):** 10/10 citations verified, clean verdict, high confidence. The Investigator actually cited its evidence this time — the prompt fix worked.

**InstructionGenerator (Phase 3):** Correctly told the Investigator to run `measure_rtt` from pcscf FIRST. Good.

**NetworkAnalyst (Phase 1):** Correctly named pcscf as PRIMARY suspect with detailed IMS evidence from the screener.

### Critical failure: Investigator's `measure_rtt` was too late

The Investigator ran `measure_rtt("pcscf", icscf_ip)` and got sub-millisecond RTT. It then concluded "transport layer is healthy" and blamed the HSS/SCP application layer instead.

**Why RTT was normal:** The observation traffic took much longer than 120 seconds due to a bug — the traffic generator tracked elapsed time by summing `asyncio.sleep()` durations, but `establish_vonr_call()` has a 30-second internal timeout for failed calls that wasn't counted. With 45% call weight and each failed call taking 30s wall time (counted as 3-6s), the generator ran ~300+ wall seconds while believing it was at 120s. By the time the Investigator ran (T+500+), the fault's 600s TTL had expired.

### Key insight: `measure_rtt` must happen DURING the event, not after

Even without the timing bug, `measure_rtt` at investigation time is fundamentally unreliable for transient conditions. In a real network, congestion clears, routes flap back, processes recover. The anomaly screener catches symptoms DURING the observation window, but the Investigator runs minutes later.

**The fix:** The NetworkAnalyst should run `measure_rtt` from suspect components IMMEDIATELY when it detects anomalies, while the symptoms are still fresh. It's closer in time to the observation window than the Investigator. The RTT measurements become part of the NetworkAnalyst's output — established evidence that the Investigator and Synthesis agents can reference regardless of whether the condition has since cleared.

The pipeline becomes:
1. **Phase 0 (Screener):** flags pcscf as anomaly epicenter
2. **Phase 1 (NetworkAnalyst):** sees flags → immediately runs `measure_rtt` FROM pcscf → records "pcscf→icscf: 2034ms" in evidence → passes to downstream
3. **Phase 3 (InstructionGenerator):** sees RTT in NetworkAnalyst output → "P-CSCF latency confirmed"
4. **Phase 4 (Investigator):** has RTT evidence from Phase 1 — focuses on WHY, not WHETHER

### Fixes implemented

1. **Synthesis prompt:** Added "Do NOT produce JSON. Use plain markdown only." to prevent inconsistent output format.

2. **Evidence Validator:** Now lists all tools called per phase with citation mapping (✓ called AND cited / ✗ called but NOT cited). Fabricated citations listed separately.

3. **Traffic generator wall-clock timing:** Replaced accumulated-sleep elapsed tracking with `time.time() - start` wall-clock. The generator now stops at exactly the specified duration regardless of call timeout durations.

4. **NetworkAnalyst prompt:** Updated to run `measure_rtt` from screener-flagged components during its own data collection phase, capturing transport evidence while symptoms are fresh.
