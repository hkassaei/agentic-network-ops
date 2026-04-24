# Episode Report: P-CSCF Latency

**Agent:** v6  
**Episode ID:** ep_20260423_194530_p_cscf_latency  
**Date:** 2026-04-23T19:45:32.063700+00:00  
**Duration:** 290.3s  

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

**ANOMALY DETECTED.** Overall anomaly score: 0.92 (threshold: 0.70, trained on 211 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following metrics deviate from their learned-healthy baseline. Treat each as a semantic observation (meaning + numbers), not a number alone — the KB's interpretation is the authoritative reading.

- **`normalized.upf.gtp_outdatapktn3upf_per_ue`** (GTP-U downlink rate per UE (N3)) — current **0.07 packets_per_second** vs learned baseline **3.34 packets_per_second** (MEDIUM, drop)
    - **What it measures:** Health of the downlink user-plane path UPF → gNB. Typically mirrors
uplink rate during calls/data; asymmetry indicates directional
faults (e.g., UPF receiving from internet but not forwarding).
    - **Drop means:** No traffic leaving UPF toward RAN.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE — constant regardless of UE pool size. Roughly symmetric with uplink during healthy calls.

- **`normalized.upf.gtp_indatapktn3upf_per_ue`** (GTP-U uplink rate per UE (N3)) — current **0.16 packets_per_second** vs learned baseline **3.42 packets_per_second** (MEDIUM, drop)
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

- **`normalized.smf.bearers_per_ue`** (Active QoS bearers per UE) — current **2.00 count** vs learned baseline **2.61 count** (LOW, shift)
    - **What it measures:** Per-UE count of active QoS bearers. Baseline reflects default
bearers; increments during VoNR calls indicate dedicated voice
bearers being set up. Drop during an active call = dedicated
bearer torn down unexpectedly (voice will fail).
    - **Shift means:** Expected during VoNR calls (1 extra bearer per active call).
    - **Healthy typical range:** 2–3.5 count
    - **Healthy invariant:** At rest: equals configured default bearers (typically 2 per UE).
During active VoNR call: +1 per caller. The per-UE ratio is the
invariant; absolute count scales with UE pool.

- **`normalized.pcscf.dialogs_per_ue`** (Active SIP dialogs per registered UE at P-CSCF) — current **0.00 count** vs learned baseline **0.57 count** (LOW, drop)
    - **What it measures:** How many calls per user are currently in progress at the P-CSCF.
Going to zero from a non-zero baseline means calls have ended
(normal) OR call setup is failing system-wide (degradation).
Together with rcv_requests_* it discriminates the two.
    - **Drop means:** No active calls. Normal at rest; suspicious if prior state had calls AND INVITE rate is also zero.
    - **Healthy typical range:** 0–1 count
    - **Healthy invariant:** Per-UE — scale-independent. 0 at rest, ~1 per active VoNR call.

- **`derived.upf_activity_during_calls`** — current **1.00** vs learned baseline **0.47** (LOW, spike). *(No KB context available — interpret from the metric name.)*


## Event Aggregation (Phase 1)

No events fired during this episode. Either no metric KB triggers matched, or the episode encountered no meaningful state transitions.

## Correlation Analysis (Phase 2)

No events fired — correlation engine had nothing to work with.

## Network Analysis (Phase 3)

**Summary:** VoNR call setup is failing due to a control plane issue, likely a communication breakdown between the P-CSCF and the PCF, which has resulted in a silent data plane.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | The underlying container and network infrastructure appears to be stable. |
| **ran** | 🟢 GREEN | The RAN appears to be connected and has active UEs. No direct evidence of a RAN-side fault. |
| **core** | 🔴 RED | The user plane is completely inactive, indicating a severe fault in the core data path (UPF) or a complete lack of call setup to activate it. |
| **ims** | 🔴 RED | The P-CSCF is rejecting SIP requests and failing to make HTTP connections, indicating a critical failure in the IMS call setup flow, likely when communicating with the PCF. |

**CORE evidence:**
- normalized.upf.gtp_indatapktn3upf_per_ue is near zero
- normalized.upf.gtp_outdatapktn3upf_per_ue is near zero

**IMS evidence:**
- derived.pcscf_sip_error_ratio spiked from 0.0 to 0.25
- normalized.pcscf.dialogs_per_ue dropped to 0.0
- pcscf.httpclient:connfail is high (44)

**Ranked hypotheses:**

- **`h1`** (fit=0.90, nf=pcf, specificity=specific):
    - **Statement:** The P-CSCF is unable to establish connections to the PCF for QoS authorization. This is evidenced by a high count of HTTP connection failures at the P-CSCF, causing it to reject VoNR call attempts and resulting in a silent data plane as no calls are successfully established.
    - **Supporting events:** `derived.pcscf_sip_error_ratio`, `normalized.pcscf.dialogs_per_ue`
    - **Falsification probes:**
        - Measure RTT and packet loss from the 'pcscf' container to the 'pcf' container's IP; high loss would confirm a partition.
        - Check PCF logs for incoming requests from P-CSCF; an absence would confirm the connection failure.
        - Check UDR logs to see if PCF is successfully fetching subscriber data; failure here could be the upstream cause.
- **`h2`** (fit=0.70, nf=upf, specificity=moderate):
    - **Statement:** A complete outage has occurred on the N3 data plane interface between the gNB and the UPF. Control plane sessions remain active but are 'zombied,' meaning no user plane traffic can pass, explaining the near-zero GTP traffic.
    - **Supporting events:** `normalized.upf.gtp_indatapktn3upf_per_ue`, `normalized.upf.gtp_outdatapktn3upf_per_ue`
    - **Falsification probes:**
        - Measure RTT and packet loss from a gNB-like location to the UPF's N3 interface IP.
        - Check UPF logs for any errors related to its N3 interface or GTP-U processing.
- **`h3`** (fit=0.60, nf=upf, specificity=moderate):
    - **Statement:** The UPF has suffered a critical internal fault, stalling its forwarding engine. This has led to a complete collapse of the user data plane, with no GTP packets being processed in either direction.
    - **Supporting events:** `normalized.upf.gtp_indatapktn3upf_per_ue`, `normalized.upf.gtp_outdatapktn3upf_per_ue`
    - **Falsification probes:**
        - Inspect the UPF container's resource utilization (CPU, memory) for anomalies.
        - Review UPF logs for fatal errors, panics, or forwarding engine stall messages.


## Falsification Plans (Phase 4)

*No output produced.*

## Parallel Investigators (Phase 5)

**3 sub-Investigator verdict(s):** **3 INCONCLUSIVE**

### `h1` — ❓ **INCONCLUSIVE**

**Hypothesis:** The P-CSCF is unable to establish connections to the PCF for QoS authorization. This is evidenced by a high count of HTTP connection failures at the P-CSCF, causing it to reject VoNR call attempts and resulting in a silent data plane as no calls are successfully established.

**Reasoning:** No falsification plan was generated for this hypothesis.

### `h2` — ❓ **INCONCLUSIVE**

**Hypothesis:** A complete outage has occurred on the N3 data plane interface between the gNB and the UPF. Control plane sessions remain active but are 'zombied,' meaning no user plane traffic can pass, explaining the near-zero GTP traffic.

**Reasoning:** No falsification plan was generated for this hypothesis.

### `h3` — ❓ **INCONCLUSIVE**

**Hypothesis:** The UPF has suffered a critical internal fault, stalling its forwarding engine. This has led to a complete collapse of the user data plane, with no GTP packets being processed in either direction.

**Reasoning:** No falsification plan was generated for this hypothesis.


## Evidence Validation (Phase 6)

**Overall verdict:** severe
**Overall confidence:** none

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 0 | 0/0 | severe | none |
|  |  |  |  | *ZERO tool calls — all citations fabricated* |
| `InvestigatorAgent_h2` | 0 | 0/0 | severe | none |
|  |  |  |  | *ZERO tool calls — all citations fabricated* |
| `InvestigatorAgent_h3` | 0 | 0/0 | severe | none |
|  |  |  |  | *ZERO tool calls — all citations fabricated* |


## Ground Truth

**Failure domain:** ims_signaling  
**Protocol impact:** SIP  
**Affected components:** pcscf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v6-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 136.9s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: VoNR call setup is failing due to a control plane communication failure between the P-CSCF and the PCF, resulting in a completely silent user data plane.
> - **timeline**:
>     1. The P-CSCF began reporting a high ratio of SIP errors and HTTP connection failures.
>     2. The UPF subsequently reported a complete absence of GTP data packets on its N3 interface, indicating no user traffic is flowing.
> - **root_cause**: The P-CSCF is unable to establish connections to the PCF for QoS authorization. The `primary_suspect_nf` is the **pcf**.
> - **affected_components**:
>     - `pcf`: Root Cause (Suspected)
>     - `pcscf`: Secondary (Unable to get QoS authorization, rejecting calls)
>     - `upf`: Symptomatic (No user plane sessions are established, resulting in zero traffic)
> - **recommendation**: The operator should manually execute the verification probes that the automated investigation failed to run. First, verify connectivity between the P-CSCF and PCF by measuring RTT and packet loss between the containers. Second, inspect PCF logs to determine if it is receiving any incoming HTTP requests from the P-CSCF. Finally, check UDR logs to confirm if the PCF is able to successfully fetch subscriber data.
> - **confidence**: low
> - **explanation**: The most plausible hypothesis (`h1`) suggests that the P-CSCF is rejecting VoNR calls because it cannot communicate with the PCF to authorize the necessary Quality of Service. This control plane failure prevents any calls from being successfully established, which explains why the user data plane at the UPF is completely silent. However, confidence in this diagnosis is **low**. The automated investigation agents failed to execute any verification steps, rendering their verdicts inconclusive. The Evidence Validator flagged this failure as severe, noting that all findings were based on fabricated data. This conclusion is therefore based only on the initial analysis, and requires manual verification.

### Scoring Breakdown

**Overall score: 46%**

**Scorer assessment:** The agent correctly identified the severity and the affected layer, and appropriately calibrated its low confidence, but misidentified the root cause and its primary affected component.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | No | The simulated failure was 2000ms latency on the P-CSCF. The agent diagnosed a 'control plane communication failure between the P-CSCF and the PCF' and identified the PCF as the 'primary_suspect_nf'/'Root Cause'. While latency on P-CSCF would cause communication issues, the agent misidentified the specific nature of the failure (latency vs. general communication failure) and the root component (PCF vs. P-CSCF itself). |
| Component overlap | 30% | The actual affected component, 'pcscf', is listed in 'affected_components' but is incorrectly labeled as 'Secondary'. The 'pcf' is incorrectly identified as the 'Root Cause'. This indicates the agent identified the component as involved but misattributed its causal role. |
| Severity correct | Yes | The simulated 2000ms latency would lead to timeouts and registration failures, effectively causing a service outage. The agent's diagnosis of 'VoNR call setup is failing' and 'completely silent user data plane' accurately reflects this severe impact. |
| Fault type identified | Yes | The agent identified 'control plane communication failure' and 'unable to establish connections', which are the observable effects of severe latency leading to service hang/rejection. While not explicitly 'latency', it describes the resulting functional failure. |
| Layer accuracy | Yes | The P-CSCF belongs to the 'ims' layer. The agent's network analysis correctly flagged the 'ims' layer as 'red' with evidence directly related to P-CSCF issues (SIP error ratio, dialogs, HTTP connection failures). |
| Confidence calibrated | Yes | The agent's diagnosis was incorrect in identifying the root cause and primary affected component, but it correctly stated 'low' confidence and provided valid reasons for its uncertainty (failed verification probes, fabricated data flag). |

**Ranking:** The agent provided a single root cause in its final diagnosis, which was incorrect. The correct cause (P-CSCF latency) was not identified.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 77,008 |
| Output tokens | 1,634 |
| Thinking tokens | 9,699 |
| **Total tokens** | **88,341** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| EventAggregator | 0 | 0 | 0 |
| CorrelationAnalyzer | 0 | 0 | 0 |
| NetworkAnalystAgent | 75,279 | 5 | 6 |
| InstructionGeneratorAgent | 8,813 | 0 | 1 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 4,249 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 290.3s
