# Episode Report: P-CSCF Latency

**Agent:** v6  
**Episode ID:** ep_20260424_191923_p_cscf_latency  
**Date:** 2026-04-24T19:19:25.036392+00:00  
**Duration:** 297.3s  

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

**ANOMALY DETECTED.** Overall anomaly score: 0.99 (threshold: 0.70, trained on 209 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following metrics deviate from their learned-healthy baseline. Treat each as a semantic observation (meaning + numbers), not a number alone — the KB's interpretation is the authoritative reading.

- **`derived.upf_activity_during_calls`** — current **1.00** vs learned baseline **0.09** (HIGH, spike). *(No KB context available — interpret from the metric name.)*

- **`normalized.upf.gtp_outdatapktn3upf_per_ue`** (GTP-U downlink rate per UE (N3)) — current **0.06 packets_per_second** vs learned baseline **6.08 packets_per_second** (HIGH, drop)
    - **What it measures:** Health of the downlink user-plane path UPF → gNB. Typically mirrors
uplink rate during calls/data; asymmetry indicates directional
faults (e.g., UPF receiving from internet but not forwarding).
    - **Drop means:** No traffic leaving UPF toward RAN.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE — constant regardless of UE pool size. Roughly symmetric with uplink during healthy calls.

- **`normalized.upf.gtp_indatapktn3upf_per_ue`** (GTP-U uplink rate per UE (N3)) — current **0.18 packets_per_second** vs learned baseline **6.15 packets_per_second** (HIGH, drop)
    - **What it measures:** Health of the uplink user-plane path gNB → UPF. Drops to near-zero
during RAN or N3 outage; stays nonzero during active calls or data
sessions. Decoupled from SIP signaling (signals data plane, not
control plane).
    - **Drop means:** Data plane dead on uplink — UPF receiving no packets from gNB.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE — constant regardless of UE pool size. Rises during active VoNR calls (~100 pps for G.711 voice) and data transfer.

- **`derived.pcscf_sip_error_ratio`** (P-CSCF SIP error response ratio) — current **0.50 ratio** vs learned baseline **0.00 ratio** (MEDIUM, spike)
    - **What it measures:** Proportion of SIP responses that are errors. Zero is the healthy
baseline; any sustained non-zero value means P-CSCF or something
downstream is rejecting requests.
    - **Spike means:** Errors flowing back — downstream CSCFs or HSS rejecting.
    - **Healthy typical range:** 0–0 ratio
    - **Healthy invariant:** Zero in healthy operation.

- **`normalized.smf.bearers_per_ue`** (Active QoS bearers per UE) — current **2.00 count** vs learned baseline **4.15 count** (MEDIUM, drop)
    - **What it measures:** Per-UE count of active QoS bearers. Baseline reflects default
bearers; increments during VoNR calls indicate dedicated voice
bearers being set up. Drop during an active call = dedicated
bearer torn down unexpectedly (voice will fail).
    - **Drop means:** Lost bearers. If sustained during a call, voice path is broken.
    - **Healthy typical range:** 2–3.5 count
    - **Healthy invariant:** At rest: equals configured default bearers (typically 2 per UE).
During active VoNR call: +1 per caller. The per-UE ratio is the
invariant; absolute count scales with UE pool.

- **`normalized.pcscf.dialogs_per_ue`** (Active SIP dialogs per registered UE at P-CSCF) — current **0.00 count** vs learned baseline **1.58 count** (MEDIUM, drop)
    - **What it measures:** How many calls per user are currently in progress at the P-CSCF.
Going to zero from a non-zero baseline means calls have ended
(normal) OR call setup is failing system-wide (degradation).
Together with rcv_requests_* it discriminates the two.
    - **Drop means:** No active calls. Normal at rest; suspicious if prior state had calls AND INVITE rate is also zero.
    - **Healthy typical range:** 0–1 count
    - **Healthy invariant:** Per-UE — scale-independent. 0 at rest, ~1 per active VoNR call.


## Event Aggregation (Phase 1)

No events fired during this episode. Either no metric KB triggers matched, or the episode encountered no meaningful state transitions.

## Correlation Analysis (Phase 2)

No events fired — correlation engine had nothing to work with.

## Network Analysis (Phase 3)

**Summary:** The data plane is completely down, with no GTP-U traffic flowing through the UPF, while the control plane is experiencing SIP errors at the P-CSCF during call setup.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | All network function containers are running and interconnected. |
| **ran** | 🟢 GREEN | The RAN appears to be connected and UEs are attached to the network. |
| **core** | 🔴 RED | The user plane is not operational. Both uplink and downlink traffic rates at the UPF are near zero, and dedicated QoS bearers are not being established. |
| **ims** | 🟡 YELLOW | IMS call setup is failing, indicated by a high SIP error rate at the P-CSCF and no active SIP dialogs. This is likely a consequence of the core network data plane failure. |

**CORE evidence:**
- normalized.upf.gtp_outdatapktn3upf_per_ue dropped to 0.06
- normalized.upf.gtp_indatapktn3upf_per_ue dropped to 0.18
- normalized.smf.bearers_per_ue dropped to 2.00

**IMS evidence:**
- derived.pcscf_sip_error_ratio spiked to 0.50
- normalized.pcscf.dialogs_per_ue dropped to 0.00

**Ranked hypotheses:**

- **`h1`** (fit=0.90, nf=upf, specificity=specific):
    - **Statement:** The UPF has an internal fault causing it to black-hole all N3 user plane traffic. This results in a complete data plane outage, and the observed SIP errors are a secondary effect of call setups failing to establish media bearers.
    - **Falsification probes:**
        - Check UPF logs for errors related to packet forwarding or N4 rule processing.
        - Use packet capture on the UPF's N3 and N6 interfaces to confirm if traffic arrives but is not forwarded.
        - Restart the UPF container to see if the condition clears.
- **`h2`** (fit=0.70, nf=smf, specificity=specific):
    - **Statement:** The SMF is failing to program the UPF with the correct forwarding rules over the N4 interface. Although the N4 link is active, invalid or missing PFCP messages from the SMF would cause the UPF to not forward any data plane traffic.
    - **Falsification probes:**
        - Check SMF logs for errors related to PFCP session creation or modification.
        - Use packet capture on the N4 interface to inspect the content of PFCP messages being sent from the SMF to the UPF.
        - Check for configuration drift on the SMF.
- **`h3`** (fit=0.60, nf=pcscf, specificity=moderate):
    - **Statement:** The P-CSCF is failing to receive QoS authorization from the PCF over the N5 interface, causing it to reject all VoNR call attempts with a SIP error. The lack of data plane traffic is a consequence of no calls ever being successfully established.
    - **Falsification probes:**
        - Check P-CSCF logs for explicit N5/Rx failure messages or timeouts when communicating with PCF.
        - Check PCF logs to see if it is receiving and processing N5 requests from the P-CSCF.
        - Measure RTT and connectivity from the P-CSCF container to the PCF container.


## Falsification Plans (Phase 4)

*No output produced.*

## Parallel Investigators (Phase 5)

**3 sub-Investigator verdict(s):** **3 INCONCLUSIVE**

### `h1` — ❓ **INCONCLUSIVE**

**Hypothesis:** The UPF has an internal fault causing it to black-hole all N3 user plane traffic. This results in a complete data plane outage, and the observed SIP errors are a secondary effect of call setups failing to establish media bearers.

**Reasoning:** No falsification plan was generated for this hypothesis.

### `h2` — ❓ **INCONCLUSIVE**

**Hypothesis:** The SMF is failing to program the UPF with the correct forwarding rules over the N4 interface. Although the N4 link is active, invalid or missing PFCP messages from the SMF would cause the UPF to not forward any data plane traffic.

**Reasoning:** No falsification plan was generated for this hypothesis.

### `h3` — ❓ **INCONCLUSIVE**

**Hypothesis:** The P-CSCF is failing to receive QoS authorization from the PCF over the N5 interface, causing it to reject all VoNR call attempts with a SIP error. The lack of data plane traffic is a consequence of no calls ever being successfully established.

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
**Time to diagnosis:** 153.0s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: A complete data plane outage is preventing all user traffic, but the investigation was unable to confirm a root cause due to a failure in the diagnostic process.
> - **timeline**:
>     1. A fault occurred within the 5G core network, leading to a complete failure of the user plane.
>     2. Uplink and downlink GTP-U traffic rates at the UPF dropped to zero.
>     3. Concurrently, IMS call setups began to fail, evidenced by a high rate of SIP errors at the P-CSCF, as the required data plane bearers for media could not be established.
> - **root_cause**: Undetermined. The leading hypothesis is an internal fault in the UPF (`primary_suspect_nf: upf`) causing it to silently discard all N3 user plane traffic, but this was not verified.
> - **affected_components**:
>     - `upf`: Potential Root Cause
>     - `smf`: Potential Root Cause
>     - `pcscf`: Symptomatic
> - **recommendation**: The automated investigation failed to run. A human operator must manually execute the diagnostic probes from the initial analysis, starting with the most likely hypothesis (h1). For the UPF, check logs for errors related to packet forwarding or N4 rule processing. Then, use packet capture on the UPF's N3 and N6 interfaces to confirm if traffic is arriving but not being forwarded.
> - **confidence**: low
> - **explanation**: Confidence is `low` because the investigation was `INCONCLUSIVE`. The Evidence Validator reported a `severe` failure, noting that the automated investigator agents made zero tool calls and thus could not verify or falsify any of the proposed hypotheses. While the top-ranked hypothesis—that the UPF is black-holing traffic—is a strong fit for the observed symptoms of a complete data plane outage, it remains an unproven theory. The other possibilities, such as the SMF failing to program the UPF or a P-CSCF/PCF interface failure, also could not be ruled out. Manual verification is required to identify the true root cause.

### Scoring Breakdown

**Overall score: 21%**

**Scorer assessment:** The agent failed to identify the correct root cause (P-CSCF latency) and instead hypothesized a data plane outage at the UPF. It correctly identified the P-CSCF as an affected component, albeit symptomatic, and accurately rated the IMS layer as impacted. Its low confidence was well-calibrated given the inconclusive diagnosis.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | No | The simulated failure was P-CSCF latency. The agent's final diagnosis stated the root cause was "Undetermined" with a "leading hypothesis" of an "internal fault in the UPF causing it to silently discard all N3 user plane traffic." This is incorrect; the issue was latency on the P-CSCF, not a UPF data plane outage. |
| Component overlap | 30% | The simulated affected component was 'pcscf'. The agent listed 'pcscf' in its `affected_components` but labeled it as 'Symptomatic', not 'Root Cause'. The primary affected component was identified, but its causal role was mis-ranked. |
| Severity correct | No | The simulated failure was 2000ms latency, which is a degradation. The agent's diagnosis described a "complete data plane outage" and "complete failure of the user plane," which is a more severe and incorrect assessment of the underlying issue. |
| Fault type identified | No | The simulated fault type was latency. The agent did not identify latency as the fault type. Instead, it focused on a 'complete data plane outage' and 'UPF silently discarding traffic', which are incorrect fault types for the simulated scenario. |
| Layer accuracy | Yes | The 'pcscf' component belongs to the 'ims' layer. The agent's network analysis correctly rated the 'ims' layer as 'yellow' and provided evidence related to 'pcscf_sip_error_ratio' and 'pcscf.dialogs_per_ue', indicating it correctly attributed the P-CSCF's issues to the IMS layer. |
| Confidence calibrated | Yes | The agent's diagnosis was incorrect and inconclusive, and it appropriately stated its confidence as 'low' with an explanation that the investigation was 'INCONCLUSIVE' and could not verify or falsify hypotheses. This demonstrates good calibration. |

**Ranking:** The agent's final diagnosis listed the root cause as 'Undetermined' with the 'leading hypothesis' being the 'upf'. The correct component (pcscf) was only listed as 'Symptomatic' and not as a root cause candidate in the final diagnosis.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 63,274 |
| Output tokens | 1,561 |
| Thinking tokens | 11,801 |
| **Total tokens** | **76,636** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| EventAggregator | 0 | 0 | 0 |
| CorrelationAnalyzer | 0 | 0 | 0 |
| NetworkAnalystAgent | 63,076 | 6 | 5 |
| InstructionGeneratorAgent | 9,229 | 0 | 1 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 4,331 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 297.3s
