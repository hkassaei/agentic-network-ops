# Episode Report: HSS Unresponsive

**Agent:** v5  
**Episode ID:** ep_20260415_005516_hss_unresponsive  
**Date:** 2026-04-15T00:55:18.118880+00:00  
**Duration:** 244.6s  

---

## Scenario

**Category:** network  
**Blast radius:** single_nf  
**Description:** Inject 60-second outbound delay on the HSS (PyHSS), making it functionally unreachable for all real-time protocols. The HSS container is running and the process is alive, but all network responses are delayed by 60 seconds — far exceeding Diameter Cx timeouts (5-30s) and standard probe timeouts (10s). From the perspective of diagnostic tools and IMS peers, the HSS appears completely unresponsive or unreachable.

## Faults Injected

- **network_latency** on `pyhss` — {'delay_ms': 60000, 'jitter_ms': 0}

## Baseline (Pre-Fault)

Stack phase before injection: **ready**
All containers running at baseline.

## Fault Propagation Verification

**Verdict:** ✅ `confirmed`

- **Wait:** 0s
- **Actual elapsed:** 0.0s
- **Nodes with significant deltas:** 2
- **Nodes with any drift:** 3

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

### Metrics Changes

| Node | Metric | Baseline | Current | Delta |
|------|--------|----------|---------|-------|
| icscf | ims_icscf:uar_timeouts | 0.0 | 1.0 | 1.0 |
| icscf | core:rcv_requests_register | 10.0 | 12.0 | 2.0 |
| icscf | cdp:timeout | 0.0 | 1.0 | 1.0 |
| pcscf | sl:1xx_replies | 10.0 | 12.0 | 2.0 |
| pcscf | core:rcv_requests_register | 10.0 | 12.0 | 2.0 |
| pcscf | script:register_failed | 0.0 | 1.0 | 1.0 |

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 0.98 (threshold: 0.70, trained on 99 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following specific metrics were flagged as the top contributors to the anomaly. These MUST be reflected in your layer ratings:

| Component | Metric | Current | Learned Normal | Severity |
|-----------|--------|---------|---------------|----------|
| icscf | cdp:timeout | 1.00 | 0.00 | HIGH |
| icscf | ims_icscf:uar_timeouts | 1.00 | 0.00 | HIGH |
| derived | icscf_uar_timeout_ratio | 1.00 | 0.00 | HIGH |
| icscf | ims_icscf:lir_avg_response_time | 0.00 | 51.03 | HIGH |
| normalized | upf.gtp_outdatapktn3upf_per_ue | 0.02 | 2.50 | MEDIUM |
| normalized | upf.gtp_indatapktn3upf_per_ue | 0.05 | 2.58 | MEDIUM |
| scscf | ims_registrar_scscf:sar_avg_response_time | 130.00 | 119.92 | MEDIUM |
| normalized | smf.bearers_per_ue | 2.00 | 2.66 | LOW |
| normalized | pcscf.dialogs_per_ue | 0.00 | 0.65 | LOW |
| derived | upf_activity_during_calls | 1.00 | 0.39 | LOW |

## Network Analysis (Phase 1)

**Summary:** The network is experiencing a complete IMS signaling failure due to the HSS being unreachable at the network layer.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | All infrastructure components (databases, DNS) are running and responsive. |
| **ran** | 🟢 GREEN | gNB is running and both UEs are attached to the core network. |
| **core** | 🟢 GREEN | 5G core is stable with active PDU sessions. The data plane is idle, which is normal as no call is in progress. |
| **ims** | 🔴 RED | Critical failure: The HSS (pyhss) is unreachable from the I-CSCF, causing all IMS authentication and registration procedures to fail. |

**IMS evidence:**
- measure_rtt from 'icscf' to 'pyhss' (172.22.0.18) resulted in 100% packet loss.
- icscf metric 'cdp:timeout' is 1.0 (expected 0.0), indicating Diameter transaction timeouts.
- icscf metric 'ims_icscf:uar_timeouts' is 1.0 (expected 0.0), indicating User-Authorization-Request to HSS failed.
- pcscf metric 'script:register_failed' is 1.0, confirming IMS registration is failing.

**Suspect components:**

- **pyhss** (high): The HSS container (pyhss) is unreachable from the I-CSCF, with measure_rtt showing 100% packet loss. This network-level failure is the direct cause of the Diameter timeouts observed at the I-CSCF and subsequent IMS registration failures.
- **icscf** (low): Reports high-severity Diameter timeouts, but these are symptoms of its inability to reach the HSS. The I-CSCF is likely functioning correctly and is the victim, not the cause.

**Investigation hint:** The root cause is a network connectivity failure to the HSS (pyhss). The I-CSCF cannot reach it, causing all IMS procedures to time out. The highest priority is to diagnose why the pyhss container at IP 172.22.0.18 is unreachable. Check its container status, logs, and internal network configuration (ifconfig, route). Also, run 'measure_rtt' from another container, like 'pcscf', to 'pyhss' to confirm the connectivity issue is not specific to the I-CSCF.

**Tools called:** get_vonr_components, get_network_topology, get_network_status, get_nf_metrics, get_dp_quality_gauges, read_env_config, measure_rtt, get_causal_chain_for_component, check_stack_rules, compare_to_baseline


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
Network Analyst made 10 tool calls. Evidence validation: 1/1 NA citations verified.
Verdict: clean. Confidence: high.

Tool calls vs. citations:
  NetworkAnalystAgent:
    ✗ check_stack_rules — called but NOT cited in output
    ✗ compare_to_baseline — called but NOT cited in output
    ✗ get_causal_chain_for_component — called but NOT cited in output
    ✗ get_dp_quality_gauges — called but NOT cited in output
    ✗ get_network_status — called but NOT cited in output
    ✗ get_network_topology — called but NOT cited in output
    ✓ get_nf_metrics — called AND cited (1x)
    ✗ get_vonr_components — called but NOT cited in output
    ✗ measure_rtt — called but NOT cited in output
    ✗ read_env_config — called but NOT cited in output
```

## Ground Truth

**Failure domain:** ims_signaling  
**Protocol impact:** Diameter  
**Affected components:** pyhss  
**Severity:** degraded

## Agent Diagnosis

**Model:** v5-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 108.2s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: A complete IMS signaling failure is occurring because the Home Subscriber Server (HSS) is unreachable at the network layer, preventing user authentication.
> - **timeline**:
>     1.  The HSS (`pyhss`) container becomes unreachable on the network at its IP address (172.22.0.18).
>     2.  The I-CSCF attempts a User-Authorization-Request (UAR) via the Diameter protocol to the HSS to authenticate a registering user.
>     3.  Due to 100% packet loss between the I-CSCF and the HSS, the Diameter transaction times out, indicated by the `ims_icscf:uar_timeouts` metric.
>     4.  The authentication failure causes the entire IMS registration process to fail, confirmed by the `script:register_failed` metric at the P-CSCF.
> - **root_cause**: The `pyhss` (HSS) container is unreachable on the network. RTT measurements from the I-CSCF show 100% packet loss, indicating a fundamental network connectivity problem. This transport-layer failure is the direct cause of the application-layer Diameter timeouts and subsequent IMS registration failures.
> - **affected_components**:
>     - `pyhss`: Root Cause
>     - `icscf`: Symptomatic
> - **recommendation**: The primary suspect is the `pyhss` container. Verify its network status and connectivity from other containers within the core network. Check the `pyhss` container's logs and internal network configuration to determine why it is not responding to network traffic.
> - **confidence**: high
> - **explanation**: The root cause of the outage is a network-layer connectivity failure to the Home Subscriber Server (HSS). The I-CSCF cannot reach the HSS to perform user authentication, causing Diameter protocol requests to time out. This prevents any users from registering with the IMS network, effectively causing a total failure of all IMS services. The underlying 5G core and radio networks are healthy, isolating the fault to the network path leading to the HSS.

### Scoring Breakdown

**Overall score: 100%**

**Scorer assessment:** The agent provided a perfectly accurate and well-supported diagnosis, correctly identifying the root cause, affected component, severity, fault type, and layer, with appropriate confidence.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | Yes | The agent correctly identified the HSS (pyhss) as unreachable on the network due to 100% packet loss, which is the observable symptom of the extreme latency simulated. This is semantically equivalent to the simulated failure mode. |
| Component overlap | 100% | The agent correctly identified 'pyhss' as the root cause component. |
| Severity correct | Yes | The agent correctly assessed the severity as a 'complete IMS signaling failure' and 'total failure of all IMS services' due to the HSS being 'unreachable' and experiencing '100% packet loss', matching the functional unreachability for real-time protocols. |
| Fault type identified | Yes | The agent identified the fault type as 'unreachable on the network', '100% packet loss', and a 'network connectivity problem' / 'transport-layer failure', which accurately describes the observable behavior of the HSS due to the extreme delay. |
| Layer accuracy | Yes | The agent correctly attributed the failure to the 'ims' layer, where the 'pyhss' component resides, and rated it RED while other layers were GREEN. |
| Confidence calibrated | Yes | The agent stated 'high' confidence, which is appropriate given the accuracy and detailed evidence provided in the diagnosis. |

**Ranking position:** #1 — The agent explicitly listed 'pyhss' as the root cause and primary affected component.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 77,821 |
| Output tokens | 1,982 |
| Thinking tokens | 4,998 |
| **Total tokens** | **84,801** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| NetworkAnalystAgent | 77,814 | 12 | 5 |
| PatternMatcherAgent | 0 | 0 | 0 |
| EvidenceValidatorAgent | 0 | 0 | 0 |
| SynthesisAgent | 6,987 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 244.6s
