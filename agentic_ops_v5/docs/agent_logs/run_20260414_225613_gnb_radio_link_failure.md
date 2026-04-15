# Episode Report: gNB Radio Link Failure

**Agent:** v5  
**Episode ID:** ep_20260414_225209_gnb_radio_link_failure  
**Date:** 2026-04-14T22:52:11.684087+00:00  
**Duration:** 240.5s  

---

## Scenario

**Category:** container  
**Blast radius:** single_nf  
**Description:** Kill the gNB to simulate a radio link failure. All UEs lose 5G registration, PDU sessions drop, and IMS SIP unregisters.

## Faults Injected

- **container_kill** on `nr_gnb`

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
| amf | ran_ue | 2.0 | 0.0 | -2.0 |
| amf | gnb | 1.0 | 0.0 | -1.0 |
| pcscf | httpclient:connfail | 55.0 | 80.0 | 25.0 |
| pcscf | core:rcv_requests_options | 54.0 | 79.0 | 25.0 |

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 0.96 (threshold: 0.70, trained on 99 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following specific metrics were flagged as the top contributors to the anomaly. These MUST be reflected in your layer ratings:

| Component | Metric | Current | Learned Normal | Severity |
|-----------|--------|---------|---------------|----------|
| normalized | smf.sessions_per_ue | 0.00 | 2.00 | HIGH |
| scscf | ims_auth:mar_avg_response_time | 128.00 | 88.89 | HIGH |
| icscf | ims_icscf:lir_avg_response_time | 0.00 | 51.03 | HIGH |
| normalized | smf.bearers_per_ue | 0.00 | 2.66 | HIGH |
| scscf | ims_registrar_scscf:sar_avg_response_time | 142.00 | 119.92 | MEDIUM |
| normalized | upf.gtp_outdatapktn3upf_per_ue | 0.00 | 2.50 | MEDIUM |
| normalized | upf.gtp_indatapktn3upf_per_ue | 0.00 | 2.58 | MEDIUM |
| icscf | cdp:average_response_time | 70.00 | 58.83 | LOW |
| icscf | ims_icscf:uar_avg_response_time | 70.00 | 61.39 | LOW |
| normalized | pcscf.dialogs_per_ue | 0.00 | 0.65 | LOW |

## Network Analysis (Phase 1)

**Summary:** The network is experiencing a critical RAN failure, causing a full disconnection of the gNB, which is leading to downstream issues in the Core and IMS layers.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | All infrastructure components (mongo, mysql, dns) are running and responsive. |
| **ran** | 🔴 RED | Critical failure: The gNB is completely disconnected from the 5G core. |
| **core** | 🟡 YELLOW | Core components are running, but have lost RAN connectivity. The SMF experienced significant anomalies during the event. |
| **ims** | 🟡 YELLOW | IMS components show signs of degradation with elevated response times, likely as a downstream symptom of the RAN failure. |

**RAN evidence:**
- get_network_topology: N2 (NGAP) link from [RAN] to AMF is INACTIVE.
- get_network_topology: N3 (GTP-U) link from [RAN] to UPF is INACTIVE.
- get_nf_metrics: amf.gnb = 0.0 (expected > 0)
- get_nf_metrics: amf.ran_ue = 0.0 (expected > 0)

**CORE evidence:**
- AnomalyScreener: normalized metric smf.sessions_per_ue was 0.00, a HIGH severity deviation.
- AnomalyScreener: normalized metric smf.bearers_per_ue was 0.00, a HIGH severity deviation.
- The AMF reports no connected gNBs or UEs, indicating a loss of its primary function.

**IMS evidence:**
- AnomalyScreener: scscf metric ims_auth:mar_avg_response_time was 128.00ms, a HIGH severity deviation.
- AnomalyScreener: icscf metric ims_icscf:lir_avg_response_time was 0.00ms, a HIGH severity deviation.
- AnomalyScreener: scscf metric ims_registrar_scscf:sar_avg_response_time was 142.00ms, a MEDIUM severity deviation.

**Suspect components:**

- **nr_gnb** (high): The gNB is the epicenter of the failure. Network topology shows its links to both AMF (N2) and UPF (N3) are INACTIVE, and AMF metrics confirm no gNB is connected. This is the root cause of all other symptoms.
- **amf** (low): The AMF is correctly reporting the loss of the gNB. While it's central to the failure, it appears to be a victim reporting the state of the RAN, not the cause of the failure itself.
- **smf** (low): The AnomalyScreener flagged SMF with the highest severity anomaly (zero sessions/bearers per UE). This is a direct and expected cascading effect of all UEs disconnecting simultaneously due to the RAN outage.

**Investigation hint:** The investigation must start at the Radio Access Network (RAN). All evidence points to a critical failure of the gNB or its connectivity to the core. The IMS and Core-level anomalies are downstream symptoms. Prioritize checking the status and logs of the `nr_gnb` container. Verify its configuration and the virtual network path to the AMF and UPF. The `ran_down_invalidates_ims` stack rule has triggered, confirming that resolving the RAN issue is the only path to recovery.

**Tools called:** get_vonr_components, get_network_topology, get_network_status, get_nf_metrics, get_dp_quality_gauges, read_env_config, measure_rtt, compare_to_baseline, check_stack_rules


## Pattern Match (Phase 2)

**✅ Match:** N2 connectivity loss — RAN/gNB unreachable, radio access lost

- **Confidence:** very_high
- **Failure domain:** ran
- **Matched signatures:** 1
  - `ran_failure` (score: 1.0)
- **Baseline anomalies:** 2 metrics across 1 components


## Investigation Instruction (Phase 3)

> Instruction generation skipped: Network Analyst diagnosis is definitive.

## Investigation (Phase 4)

> Investigation skipped: Network Analyst produced a high-confidence diagnosis with definitive evidence (RED layer + high-confidence suspect). See Phase 1 analysis.

## Evidence Validation (Phase 5)

**Verdict:** has_warnings
**Investigator confidence:** low
**Citations:** 0/0 verified

**WARNING:** Investigator made ZERO tool calls — all evidence citations are fabricated.

```
⚠️ CRITICAL: InvestigatorAgent made ZERO tool calls — no actual verification was performed.
Evidence validation: 0/0 citations verified (0 unmatched). Investigator: 0 citations from 0 tool calls.
Verdict: has_warnings. Investigator confidence: low.

Tool calls vs. citations:
  NetworkAnalystAgent:
    ✗ check_stack_rules — called but NOT cited in output
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

**Failure domain:** data_plane  
**Protocol impact:** GTP-U  
**Affected components:** nr_gnb  
**Severity:** degraded

## Agent Diagnosis

**Model:** v5-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 102.8s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: The investigation did not produce verifiable evidence. Manual investigation is required.
> - **timeline**:
> - **root_cause**: Unknown — the automated investigation could not verify its own findings.
> - **affected_components**:
>     - `nr_gnb`: Root Cause
>     - `amf`: Symptomatic
>     - `smf`: Symptomatic
> - **recommendation**: Manual investigation required. Start from the Network Analyst's suspect list and verify each component's state with direct tool calls: measure_rtt, check_process_listeners, read_container_logs, read_running_config. Do not act on the Investigator's unverified claims without independent verification.
> - **confidence**: low
> - **explanation**: The initial Network Analysis phase identified a critical failure in the Radio Access Network (RAN). All evidence pointed to the gNB being completely disconnected from the 5G core, as its N2 and N3 links were inactive and the AMF reported zero connected gNBs. However, the subsequent automated investigation phase was skipped and made no tool calls to verify these initial findings. This diagnosis has been downgraded to low confidence because the investigation phase did not produce independent, verifiable evidence. A human operator should investigate manually before taking action.

### Scoring Breakdown

**Overall score: 90%**

**Scorer assessment:** The agent correctly identified the gNB as the root cause of the critical RAN failure, accurately describing its complete disconnection and the cascading effects, despite formally stating "Unknown" root cause due to a lack of automated verification. The confidence was under-calibrated given the strong evidence presented.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | Yes | The agent's detailed explanation, affected components list, and suspect components list all clearly identify `nr_gnb` as the root cause, describing it as "completely disconnected from the 5G core" and the "epicenter of the failure." While the formal `root_cause` field states "Unknown" due to lack of automated verification, the identification itself is correct and primary. |
| Component overlap | 100% | The agent correctly identified `nr_gnb` as the primary affected component and explicitly labeled it as the "Root Cause" and "epicenter of the failure." It also correctly identified downstream affected components like AMF and SMF as symptomatic. |
| Severity correct | Yes | The agent correctly assessed the severity as a "Critical failure" and described the gNB as "completely disconnected" with inactive N2/N3 links and zero connected gNBs reported by the AMF, which aligns with a complete outage/unreachable state. |
| Fault type identified | Yes | The agent clearly identified the fault type as the gNB being "completely disconnected" and its N2/N3 links being "inactive," which directly corresponds to a component unreachable/network partition fault type. |
| Layer accuracy | Yes | The agent correctly identified the `ran` layer as "RED" and provided evidence directly related to the gNB's failure and disconnection, aligning with the ground truth that `nr_gnb` belongs to the `ran` layer. |
| Confidence calibrated | No | The agent's diagnosis is largely correct and supported by significant evidence from the `NETWORK ANALYSIS` section (e.g., inactive N2/N3 links, AMF metrics). Despite this strong evidence, the agent states "low" confidence because the *automated investigation phase* did not perform *further* verification. This indicates under-confidence, making the confidence poorly calibrated relative to the quality of the diagnosis and available evidence. |

**Ranking position:** #1 — The agent explicitly identifies `nr_gnb` as the "Root Cause" in the `affected_components` and as the primary suspect with "high" confidence in `suspect_components`, placing it as the top-ranked candidate.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 91,336 |
| Output tokens | 2,254 |
| Thinking tokens | 5,870 |
| **Total tokens** | **99,460** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| NetworkAnalystAgent | 90,866 | 20 | 6 |
| PatternMatcherAgent | 0 | 0 | 0 |
| EvidenceValidatorAgent | 0 | 0 | 0 |
| SynthesisAgent | 8,594 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 240.5s
