# Episode Report: P-CSCF Latency

**Agent:** v6  
**Episode ID:** ep_20260428_021415_p_cscf_latency  
**Date:** 2026-04-28T02:14:16.480422+00:00  
**Duration:** 217.4s  

---

## Scenario

**Category:** network  
**Blast radius:** single_nf  
**Description:** Inject 2000ms latency (with 50ms jitter) on the P-CSCF (SIP edge proxy). SIP transactions will experience severe delays as every message entering and leaving the P-CSCF is delayed, compounding across multiple round-trips in the IMS registration chain. Tests IMS resilience to high latency on the signaling edge.

## Faults Injected

- **network_latency** on `pcscf` — {'delay_ms': 2000, 'jitter_ms': 50}

## Baseline (Pre-Fault)

Stack phase before injection: **ready**
All containers running at baseline.

## Fault Propagation Verification

**Verdict:** ✅ `confirmed`

- **Wait:** 0s
- **Actual elapsed:** 0.0s
- **Nodes with significant deltas:** 3
- **Nodes with any drift:** 4

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 0.95 (threshold: 0.70, trained on 104 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following metrics deviate from their learned-healthy baseline. Treat each as a semantic observation (meaning + numbers), not a number alone — the KB's interpretation is the authoritative reading.

- **`normalized.upf.gtp_outdatapktn3upf_per_ue`** (GTP-U downlink rate per UE (N3)) — current **0.06 packets_per_second** vs learned baseline **3.37 packets_per_second** (MEDIUM, drop)
    - **What it measures:** Health of the downlink user-plane path UPF → gNB. Typically mirrors
uplink rate during calls/data; asymmetry indicates directional
faults (e.g., UPF receiving from internet but not forwarding).
    - **Drop means:** No traffic leaving UPF toward RAN.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE — constant regardless of UE pool size. Roughly symmetric with uplink during healthy calls.

- **`normalized.upf.gtp_indatapktn3upf_per_ue`** (GTP-U uplink rate per UE (N3)) — current **0.16 packets_per_second** vs learned baseline **3.44 packets_per_second** (MEDIUM, drop)
    - **What it measures:** Health of the uplink user-plane path gNB → UPF. Drops to near-zero
during RAN or N3 outage; stays nonzero during active calls or data
sessions. Decoupled from SIP signaling (signals data plane, not
control plane).
    - **Drop means:** Data plane dead on uplink — UPF receiving no packets from gNB.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE — constant regardless of UE pool size. Rises during active VoNR calls (~100 pps for G.711 voice) and data transfer.

- **`derived.pcscf_sip_error_ratio`** (P-CSCF SIP error response ratio) — current **0.25 ratio** vs learned baseline **0.00 ratio** (MEDIUM, spike)
    - **What it measures:** Proportion of SIP responses that are errors. Zero is the healthy
baseline; any sustained non-zero value means P-CSCF or something
downstream is rejecting requests.
    - **Spike means:** Errors flowing back — downstream CSCFs or HSS rejecting.
    - **Healthy typical range:** 0–0 ratio
    - **Healthy invariant:** Zero in healthy operation.

- **`normalized.smf.bearers_per_ue`** (Active QoS bearers per UE) — current **2.00 count** vs learned baseline **2.59 count** (LOW, shift)
    - **What it measures:** Per-UE count of active QoS bearers. Baseline reflects default
bearers; increments during VoNR calls indicate dedicated voice
bearers being set up. Drop during an active call = dedicated
bearer torn down unexpectedly (voice will fail).
    - **Shift means:** Expected during VoNR calls (1 extra bearer per active call).
    - **Healthy typical range:** 2–3.5 count
    - **Healthy invariant:** At rest: equals configured default bearers (typically 2 per UE).
During active VoNR call: +1 per caller. The per-UE ratio is the
invariant; absolute count scales with UE pool.

- **`normalized.pcscf.dialogs_per_ue`** (Active SIP dialogs per registered UE at P-CSCF) — current **0.00 count** vs learned baseline **0.59 count** (LOW, drop)
    - **What it measures:** How many calls per user are currently in progress at the P-CSCF.
Going to zero from a non-zero baseline means calls have ended
(normal) OR call setup is failing system-wide (degradation).
Together with rcv_requests_* it discriminates the two.
    - **Drop means:** No active calls. Normal at rest; suspicious if prior state had calls AND INVITE rate is also zero.
    - **Healthy typical range:** 0–1 count
    - **Healthy invariant:** Per-UE — scale-independent. 0 at rest, ~1 per active VoNR call.

- **`derived.upf_activity_during_calls`** — current **1.00** vs learned baseline **0.45** (LOW, spike). *(No KB context available — interpret from the metric name.)*


## Event Aggregation (Phase 1)

No events fired during this episode. Either no metric KB triggers matched, or the episode encountered no meaningful state transitions.

## Correlation Analysis (Phase 2)

No events fired — correlation engine had nothing to work with.

## Network Analysis (Phase 3)

**Summary:** NA produced no output


## Falsification Plans (Phase 4)

*No output produced.*

## Parallel Investigators (Phase 5)

*No investigation output produced.*

## Evidence Validation (Phase 6)

*No evidence validation output.*

## Ground Truth

**Failure domain:** ims_signaling  
**Protocol impact:** SIP  
**Affected components:** pcscf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v6-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 78.1s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: NA produced no output
> - **timeline**: []
> - **root_cause**: Unknown — NetworkAnalyst produced no testable hypotheses.
> - **affected_components**: []
> - **recommendation**: Manual investigation required. Re-run when more events are available.
> - **confidence**: low
> - **explanation**: The v6 pipeline received insufficient evidence to form testable hypotheses. Either no events fired during the observation window or none of the NA's candidate hypotheses had identifiable falsification probes. Review the anomaly screener output and event store directly.
> 

### Scoring Breakdown

**Overall score: 15%**

**Scorer assessment:** The agent completely failed to diagnose the P-CSCF latency issue, reporting 'Unknown' as the root cause and identifying no affected components. However, its low confidence was calibrated, and it did not misattribute any layers.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | No | The agent's final diagnosis explicitly states 'Unknown — NetworkAnalyst produced no testable hypotheses.' and 'NA produced no output', failing to identify the P-CSCF latency as the root cause. |
| Component overlap | 0% | The agent's 'affected_components' list is empty, indicating it did not identify the P-CSCF as the affected component. |
| Severity correct | No | The agent did not identify any fault, therefore it could not correctly assess the severity of the 2000ms latency leading to timeouts and registration failures. |
| Fault type identified | No | The agent's diagnosis is 'Unknown', meaning it did not identify 'elevated network latency' or any other fault type. |
| Layer accuracy | Yes | The 'AGENT NETWORK ANALYSIS' section for layer status is empty, meaning no layer misattribution occurred. According to the scoring rules, if no layer status information is available, it scores True. |
| Confidence calibrated | Yes | The agent's confidence is 'low', which is appropriate given its complete failure to diagnose the issue and its explicit statement of 'insufficient evidence'. |

**Ranking:** The agent did not provide any ranked candidates; it stated the root cause was 'Unknown'.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 55,551 |
| Output tokens | 156 |
| Thinking tokens | 5,365 |
| **Total tokens** | **61,072** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| EventAggregator | 0 | 0 | 0 |
| CorrelationAnalyzer | 0 | 0 | 0 |
| NetworkAnalystAgent | 61,072 | 6 | 4 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 217.4s
