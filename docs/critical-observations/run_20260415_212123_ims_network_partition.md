# Episode Report: IMS Network Partition

**Agent:** v5  
**Episode ID:** ep_20260415_211626_ims_network_partition  
**Date:** 2026-04-15T21:16:28.620975+00:00  
**Duration:** 293.7s  

---

## Scenario

**Category:** network  
**Blast radius:** multi_nf  
**Description:** Partition the P-CSCF from both the I-CSCF and S-CSCF using iptables DROP rules. SIP signaling between the edge proxy and the core IMS is completely severed. Tests IMS behavior under a network split.

## Faults Injected

- **network_partition** on `pcscf` — {'target_ip': '172.22.0.19'}
- **network_partition** on `pcscf` — {'target_ip': '172.22.0.20'}

## Baseline (Pre-Fault)

Stack phase before injection: **ready**
All containers running at baseline.

## Fault Propagation Verification

**Verdict:** ✅ `confirmed`

- **Wait:** 0s
- **Actual elapsed:** 0.0s
- **Nodes with significant deltas:** 4
- **Nodes with any drift:** 4

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

### Metrics Changes

| Node | Metric | Baseline | Current | Delta |
|------|--------|----------|---------|-------|
| pcscf | core:rcv_requests_register | 12.0 | 23.0 | 11.0 |
| pcscf | httpclient:connfail | 28.0 | 57.0 | 29.0 |
| pcscf | core:rcv_requests_invite | 0.0 | 2.0 | 2.0 |
| pcscf | sl:1xx_replies | 12.0 | 25.0 | 13.0 |
| pcscf | core:rcv_requests_options | 27.0 | 54.0 | 27.0 |
| pcscf | dialog_ng:processed | 0.0 | 2.0 | 2.0 |
| rtpengine | owned_sessions | 0.0 | 2.0 | 2.0 |
| rtpengine | total_sessions | 0.0 | 2.0 | 2.0 |
| smf | bearers_active | 4.0 | 6.0 | 2.0 |
| upf | fivegs_ep_n3_gtp_indatapktn3upf | 38.0 | 61.0 | 23.0 |
| upf | fivegs_ep_n3_gtp_outdatavolumeqosleveln3upf | 20599.0 | 33881.0 | 13282.0 |
| upf | fivegs_ep_n3_gtp_outdatapktn3upf | 33.0 | 59.0 | 26.0 |
| upf | fivegs_ep_n3_gtp_indatavolumeqosleveln3upf | 14264.0 | 26977.0 | 12713.0 |

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 0.92 (threshold: 0.70, trained on 99 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following specific metrics were flagged as the top contributors to the anomaly. These MUST be reflected in your layer ratings:

| Component | Metric | Current | Learned Normal | Severity |
|-----------|--------|---------|---------------|----------|
| scscf | ims_auth:mar_avg_response_time | 125.00 | 88.89 | HIGH |
| icscf | ims_icscf:lir_avg_response_time | 0.00 | 51.03 | HIGH |
| rtpengine | average_mos | 0.00 | 4.17 | HIGH |
| scscf | ims_registrar_scscf:sar_avg_response_time | 97.00 | 119.92 | MEDIUM |
| icscf | cdp:average_response_time | 82.00 | 58.83 | MEDIUM |
| icscf | ims_icscf:uar_avg_response_time | 82.00 | 61.39 | MEDIUM |
| normalized | upf.gtp_outdatapktn3upf_per_ue | 0.06 | 2.50 | MEDIUM |
| normalized | upf.gtp_indatapktn3upf_per_ue | 0.10 | 2.58 | MEDIUM |
| normalized | pcscf.dialogs_per_ue | 0.00 | 0.65 | LOW |
| derived | upf_activity_during_calls | 1.00 | 0.39 | LOW |

## Network Analysis (Phase 1)

**Summary:** The network is experiencing a critical IMS failure due to a complete network partition between the P-CSCF and I-CSCF, while the 5G core and RAN layers remain healthy.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | All infrastructure components are running and responsive. |
| **ran** | 🟢 GREEN | gNB and UEs are connected to the 5G core. |
| **core** | 🟢 GREEN | 5G core is stable, with active PDU sessions. Data plane is idle, which is expected. |
| **ims** | 🔴 RED | Catastrophic network failure between P-CSCF and I-CSCF prevents all IMS signaling. |

**IMS evidence:**
- measure_rtt("icscf", "172.22.0.21") -> 100% packet loss
- measure_rtt("pcscf", "172.22.0.19") -> 100% packet loss
- scscf: ims_auth:mar_avg_response_time = 125.0ms (screener severity: HIGH)
- icscf: ims_icscf:lir_avg_response_time = 0.0ms (screener severity: HIGH)
- rtpengine: average_mos = 0.0 (screener severity: HIGH)

**Suspect components:**

- **pcscf** (high): Bidirectional 100% packet loss detected between P-CSCF (172.22.0.21) and I-CSCF (172.22.0.19). This transport failure on the Mw interface is the root cause of the IMS outage.
- **icscf** (high): Bidirectional 100% packet loss detected between I-CSCF (172.22.0.19) and P-CSCF (172.22.0.21). This transport failure on the Mw interface is the root cause of the IMS outage.
- **scscf** (low): Flagged by anomaly screener for high MAR response time (125ms), but this is a downstream symptom of the P-CSCF/I-CSCF transport failure causing SIP registration to stall and timeout.

**Investigation hint:** The root cause is a network partition, not an application-level fault. Focus immediately on the transport layer between the 'pcscf' and 'icscf' containers. The 100% bidirectional packet loss indicates a severe network issue, such as a misconfigured docker network, firewall rule, or a routing problem specific to these two containers. The elevated IMS metrics on S-CSCF and I-CSCF are cascading symptoms of this transport failure. The zero-value data plane metrics (MOS, pps) are expected as the network is idle and should be ignored.

**Tools called:** get_vonr_components, get_network_topology, get_network_status, get_nf_metrics, get_dp_quality_gauges, read_env_config, measure_rtt, compare_to_baseline, check_stack_rules


## Pattern Match (Phase 2)

**❌ Match:** No matching signature found

- **Confidence:** low
- **Failure domain:** unknown
- **Baseline anomalies:** 1 metrics across 1 components


## Investigation Instruction (Phase 3)

> Instruction generation skipped: Network Analyst diagnosis is definitive.

## Investigation (Phase 4)

> Investigation skipped: Network Analyst produced a high-confidence diagnosis with definitive evidence (RED layer + high-confidence suspect). See Phase 1 analysis.

## Evidence Validation (Phase 5)

**Verdict:** clean
**Investigator confidence:** high
**Citations:** 1/1 verified

```
Investigator was intentionally skipped (Network Analyst diagnosis was definitive). Validating Network Analyst evidence only.
Network Analyst made 9 tool calls. Evidence validation: 1/1 NA citations verified.
Verdict: clean. Confidence: high.

Tool calls vs. citations:
  NetworkAnalystAgent:
    ✓ check_stack_rules — called AND cited (1x)
    ✗ compare_to_baseline — called but NOT cited in output
    ✗ get_dp_quality_gauges — called but NOT cited in output
    ✗ get_network_status — called but NOT cited in output
    ✗ get_network_topology — called but NOT cited in output
    ✗ get_nf_metrics — called but NOT cited in output
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
**Time to diagnosis:** 150.1s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: A complete network partition between the P-CSCF and I-CSCF has severed the Mw interface, causing a total IMS service outage. The 5G core and RAN layers are healthy.
> - **timeline**:
>     1. The 5G Core and RAN layers are stable, with UEs connected and PDU sessions established.
>     2. A network transport failure occurs, isolating the P-CSCF and I-CSCF from each other.
>     3. Direct RTT measurements confirm 100% bidirectional packet loss between P-CSCF (172.22.0.21) and I-CSCF (172.22.0.19).
>     4. All SIP signaling from P-CSCF towards the core IMS fails, leading to timeouts and a complete inability to process registrations or calls.
>     5. Metrics on other IMS components, such as high response times on the S-CSCF and zero received replies on the I-CSCF, are logged as symptoms of the transport failure.
> - **root_cause**: The root cause is a transport-layer failure resulting in a complete network partition between the P-CSCF and I-CSCF. This connectivity loss on the Mw interface prevents any SIP messages from being exchanged, effectively halting all IMS procedures.
> - **affected_components**:
>     - `pcscf`: Root Cause (Endpoint of the network partition)
>     - `icscf`: Root Cause (Endpoint of the network partition)
>     - `scscf`: Symptomatic (Experiencing downstream timeouts due to the transport failure)
>     - `rtpengine`: Symptomatic (Zero MOS score is expected as no calls can be established)
> - **recommendation**: Focus investigation on the network transport layer between the `pcscf` and `icscf` containers. Verify routing, firewall rules, and any network policies that might be specifically blocking traffic between IP addresses 172.22.0.21 and 172.22.0.19.
> - **confidence**: high
> - **explanation**: The diagnosis is definitive. Direct network measurements show 100% bidirectional packet loss between the P-CSCF and I-CSCF, indicating a network partition rather than an application-level fault. This transport failure is the root cause of all observed IMS error metrics, which are downstream symptoms. The underlying 5G core and radio network layers remain healthy and are not implicated in this failure.

### Scoring Breakdown

**Overall score: 100%**

**Scorer assessment:** The agent provided an excellent and highly accurate diagnosis, correctly identifying the network partition between P-CSCF and I-CSCF as the root cause, its severity, and the affected components and layer, all with appropriate confidence.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | Yes | The agent correctly identified a 'complete network partition between the P-CSCF and I-CSCF' and a 'transport-layer failure' as the root cause, which directly matches the simulated failure mode of an IMS network partition isolating the P-CSCF from its peers. |
| Component overlap | 100% | The agent correctly identified 'pcscf' and 'icscf' as the primary affected components (endpoints of the network partition). It also correctly listed 'scscf' and 'rtpengine' as symptomatic, which is appropriate causal reasoning. |
| Severity correct | Yes | The agent's assessment of a 'total IMS service outage' and '100% bidirectional packet loss' accurately reflects the 'completely severed' SIP signaling and failure of new registrations/invites in the simulated failure. |
| Fault type identified | Yes | The agent clearly identified the fault type as a 'network partition' and 'transport-layer failure' with '100% bidirectional packet loss', which is precisely the observable failure mode. |
| Layer accuracy | Yes | The agent correctly attributed the failure to the 'ims' layer, rating it RED, with evidence directly related to the P-CSCF and I-CSCF components which belong to the IMS layer. Other layers were correctly rated GREEN. |
| Confidence calibrated | Yes | The agent stated 'high' confidence, which is well-justified given the accuracy and completeness of its diagnosis, supported by direct network measurements (100% packet loss). |

**Ranking position:** #1 — The agent provided a single, clear, and correct root cause as its primary diagnosis.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 102,836 |
| Output tokens | 2,966 |
| Thinking tokens | 8,508 |
| **Total tokens** | **114,310** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| NetworkAnalystAgent | 107,187 | 19 | 6 |
| PatternMatcherAgent | 0 | 0 | 0 |
| EvidenceValidatorAgent | 0 | 0 | 0 |
| SynthesisAgent | 7,123 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 293.7s
