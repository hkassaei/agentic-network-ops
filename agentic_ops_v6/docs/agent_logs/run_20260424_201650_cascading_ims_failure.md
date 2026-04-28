# Episode Report: Cascading IMS Failure

**Agent:** v6  
**Episode ID:** ep_20260424_201144_cascading_ims_failure  
**Date:** 2026-04-24T20:11:46.699767+00:00  
**Duration:** 302.8s  

---

## Scenario

**Category:** compound  
**Blast radius:** multi_nf  
**Description:** Kill PyHSS AND add 2-second latency to the S-CSCF. This simulates a cascading failure: the HSS is gone (no Diameter auth) AND the S-CSCF is degraded (slow SIP processing). Total IMS outage.

## Faults Injected

- **container_kill** on `pyhss`
- **network_latency** on `scscf` — {'delay_ms': 2000}

## Baseline (Pre-Fault)

Stack phase before injection: **ready**
All containers running at baseline.

## Fault Propagation Verification

**Verdict:** ✅ `confirmed`

- **Wait:** 0s
- **Actual elapsed:** 0.0s
- **Nodes with significant deltas:** 4
- **Nodes with any drift:** 5

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 0.99 (threshold: 0.70, trained on 209 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following metrics deviate from their learned-healthy baseline. Treat each as a semantic observation (meaning + numbers), not a number alone — the KB's interpretation is the authoritative reading.

- **`derived.upf_activity_during_calls`** — current **1.00** vs learned baseline **0.09** (HIGH, spike). *(No KB context available — interpret from the metric name.)*

- **`normalized.upf.gtp_outdatapktn3upf_per_ue`** (GTP-U downlink rate per UE (N3)) — current **0.03 packets_per_second** vs learned baseline **6.08 packets_per_second** (HIGH, drop)
    - **What it measures:** Health of the downlink user-plane path UPF → gNB. Typically mirrors
uplink rate during calls/data; asymmetry indicates directional
faults (e.g., UPF receiving from internet but not forwarding).
    - **Drop means:** No traffic leaving UPF toward RAN.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE — constant regardless of UE pool size. Roughly symmetric with uplink during healthy calls.

- **`normalized.upf.gtp_indatapktn3upf_per_ue`** (GTP-U uplink rate per UE (N3)) — current **0.12 packets_per_second** vs learned baseline **6.15 packets_per_second** (HIGH, drop)
    - **What it measures:** Health of the uplink user-plane path gNB → UPF. Drops to near-zero
during RAN or N3 outage; stays nonzero during active calls or data
sessions. Decoupled from SIP signaling (signals data plane, not
control plane).
    - **Drop means:** Data plane dead on uplink — UPF receiving no packets from gNB.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE — constant regardless of UE pool size. Rises during active VoNR calls (~100 pps for G.711 voice) and data transfer.

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

**Summary:** The IMS core has failed due to the Home Subscriber Server (HSS) having exited, which prevents all user registrations and subsequent call setups, causing a collapse in user plane traffic.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | The underlying infrastructure appears to be stable. |
| **ran** | 🟡 YELLOW | The RAN appears to be connected, but no user traffic is flowing, which is a symptom of the core network failure, not a RAN issue itself. |
| **core** | 🟡 YELLOW | The 5G core components are running but idle due to the upstream IMS failure preventing any VoNR calls from being established. |
| **ims** | 🔴 RED | The HSS, a critical component for user authentication, has crashed. This has led to a complete outage of the IMS system. |

**RAN evidence:**
- RAN-to-AMF (N2) and RAN-to-UPF (N3) links are active.

**CORE evidence:**
- UPF and SMF are running, but key metrics show no activity.
- normalized.upf.gtp_outdatapktn3upf_per_ue is near zero.
- normalized.upf.gtp_indatapktn3upf_per_ue is near zero.
- normalized.smf.bearers_per_ue has dropped to default levels.

**IMS evidence:**
- The 'pyhss' container has exited.
- Cx links from I-CSCF and S-CSCF to HSS are inactive.
- normalized.pcscf.dialogs_per_ue is zero.

**Ranked hypotheses:**

- **`h1`** (fit=0.95, nf=pyhss, specificity=specific):
    - **Statement:** The Home Subscriber Server (HSS/pyhss) has exited, causing a complete failure of the IMS network. As the central database for subscriber authentication, its absence prevents UEs from performing IMS registration, making it impossible to establish VoNR calls, which explains the collapse in SIP dialogs, dedicated bearers, and user-plane traffic.
    - **Falsification probes:**
        - Check if the 'pyhss' container process is running.
        - Attempt to query the HSS from the I-CSCF or S-CSCF using a Diameter command; any response other than a timeout or transport failure would disprove this.
        - Check the status of the Cx Diameter links in the network topology; if they are active, this hypothesis is false.


## Falsification Plans (Phase 4)

**1 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `pyhss`)

**Hypothesis:** The Home Subscriber Server (HSS/pyhss) has exited, causing a complete failure of the IMS network. As the central database for subscriber authentication, its absence prevents UEs from performing IMS registration, making it impossible to establish VoNR calls, which explains the collapse in SIP dialogs, dedicated bearers, and user-plane traffic.

**Probes (3):**
1. **`check_process_listeners`** — container='pyhss'
    - *Expected if hypothesis holds:* Empty result, or no process listening on the Diameter port (3868). This confirms the process is down or unresponsive.
    - *Falsifying observation:* A process is actively listening on TCP/SCTP port 3868. This would indicate the HSS process is running and bound to its service port, contradicting the 'exited' hypothesis.
2. **`get_nf_metrics`** — container='icscf', counters=['ims_icscf_uar_timeouts']
    - *Expected if hypothesis holds:* The 'ims_icscf_uar_timeouts' counter will be elevated and likely increasing, as the I-CSCF's User-Authorization-Requests (UARs) to the HSS will be failing.
    - *Falsifying observation:* The 'ims_icscf_uar_timeouts' counter is zero or not increasing. This implies the I-CSCF is either not attempting to contact the HSS or is receiving successful or error responses, both of which mean the HSS is reachable.
3. **`get_nf_metrics`** — container='scscf', counters=['ims_registrar_scscf_sar_timeouts']
    - *Expected if hypothesis holds:* The 'ims_registrar_scscf_sar_timeouts' counter will be elevated and likely increasing, as the S-CSCF's Server-Assignment-Requests (SARs) to the HSS will be failing.
    - *Falsifying observation:* The 'ims_registrar_scscf_sar_timeouts' counter is zero or not increasing. This provides triangulation; if the S-CSCF can communicate with the HSS, the HSS has not exited.

*Notes:* The plan focuses on verifying the 'exited' state of the HSS from multiple perspectives. Probe 1 checks for process-level network presence. Probes 2 and 3 check for the expected timeout failures from the two primary clients of the HSS (I-CSCF and S-CSCF) as defined in the 'ims_registration' flow (steps 4 and 7). If the clients are not seeing timeouts, the HSS cannot be down.


## Parallel Investigators (Phase 5)

**1 sub-Investigator verdict(s):** **1 DISPROVEN**

### `h1` — ❌ **DISPROVEN**

**Hypothesis:** The Home Subscriber Server (HSS/pyhss) has exited, causing a complete failure of the IMS network. As the central database for subscriber authentication, its absence prevents UEs from performing IMS registration, making it impossible to establish VoNR calls, which explains the collapse in SIP dialogs, dedicated bearers, and user-plane traffic.

**Reasoning:** The hypothesis states the IMS failure is caused by the HSS (`pyhss`) having exited, leading to authentication timeouts at the I-CSCF and S-CSCF. Probe 1 confirmed that the `pyhss` container has indeed exited. However, subsequent probes revealed that both the I-CSCF's UAR timeout counter (`ims_icscf_uar_timeouts`) and the S-CSCF's SAR timeout counter (`ims_registrar_scscf_sar_timeouts`) are zero. This directly contradicts the hypothesis's core mechanism. If the HSS were unreachable, these CSCFs would be logging timeouts for authentication requests (UAR/SAR). The absence of these timeouts falsifies the proposed causal link between the HSS being down and the IMS failure.

**Probes executed (3):**
- **Check if a process is listening on the Diameter port (3868) in the 'pyhss' container.** ✓ CONSISTENT
    - *Tool:* `check_process_listeners(container='pyhss')`
    - *Observation:* [EVIDENCE: check_process_listeners("pyhss") -> "Error response from daemon: container 8d9002eddc5bbae44f9f8bdebb686ebe8f36c77075f8a1d3075d619d2aba46ab is not running"]
    - *Comment:* The tool confirmed that the 'pyhss' container is not running. This is consistent with the first part of the hypothesis that the HSS has exited.
- **Check for an increase in the 'ims_icscf_uar_timeouts' counter on the I-CSCF.** ✗ CONTRADICTS
    - *Tool:* `get_nf_metrics()`
    - *Observation:* [EVIDENCE: get_nf_metrics() -> "ims_icscf:uar_timeouts = 0.0  [counter]"]
    - *Comment:* The hypothesis expects I-CSCF's User-Authorization-Requests (UARs) to the HSS to time out. The 'ims_icscf_uar_timeouts' counter is zero, which falsifies this expectation.
- **Check for an increase in the 'ims_registrar_scscf_sar_timeouts' counter on the S-CSCF.** ✗ CONTRADICTS
    - *Tool:* `get_nf_metrics()`
    - *Observation:* [EVIDENCE: get_nf_metrics() -> "ims_registrar_scscf:sar_timeouts = 0.0  [counter]"]
    - *Comment:* The hypothesis expects S-CSCF's Server-Assignment-Requests (SARs) to the HSS to time out. The 'ims_registrar_scscf_sar_timeouts' counter is zero, which provides a second piece of evidence falsifying the hypothesis's causal mechanism.

**Alternative suspects:** pcscf


## Evidence Validation (Phase 6)

**Overall verdict:** clean
**Overall confidence:** high

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 2 | 3/3 | clean | high |


## Ground Truth

**Failure domain:** ims_signaling  
**Protocol impact:** SIP  
**Affected components:** pyhss, scscf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v6-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 159.7s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: The initial hypothesis of a Home Subscriber Server (HSS) failure has been disproven, and the investigation now points towards a potential issue with the P-CSCF as the root cause of the IMS network outage.
> - **timeline**:
>     1. A complete outage occurs in the IMS network, preventing all user registrations and VoNR calls, leading to a collapse in user plane traffic.
>     2. Automated analysis initially identified that the Home Subscriber Server (HSS, `pyhss`) container had exited, making it the primary suspect.
>     3. Investigation confirmed the HSS was down but also revealed that neither the I-CSCF nor the S-CSCF were logging authentication timeouts, proving that the HSS failure was not the cause of the registration outage.
> - **root_cause**: The root cause is not confirmed. The initial hypothesis (HSS failure) was falsified. The P-CSCF (`pcscf`) is now the primary suspect, as the failure likely occurs before the registration request reaches the I/S-CSCFs.
> - **affected_components**:
>     - `pcscf`: Root Cause (Suspected)
>     - `pyhss`: Secondary (Confirmed down, but not the root cause)
>     - `icscf`: Symptomatic
>     - `scscf`: Symptomatic
>     - `ran`: Symptomatic
> - **recommendation**: The operator should investigate the P-CSCF (`pcscf`). Specifically, verify its logs for errors processing incoming SIP REGISTER requests from UEs and check its ability to forward those requests to the I-CSCF.
> - **confidence**: low
> - **explanation**: The initial hypothesis from the Network Analyst, which blamed the exited HSS (`pyhss`), was disproven. While the HSS container is indeed offline, the key evidence that falsified this theory was that the I-CSCF's UAR timeout counter (`ims_icscf_uar_timeouts`) and the S-CSCF's SAR timeout counter (`ims_registrar_scscf_sar_timeouts`) are both zero. If the HSS were the cause, these components would be logging timeouts trying to contact it for authentication. Since they are not, the registration requests are not reaching them in the first place, pointing to a failure earlier in the call flow. This implicates the P-CSCF, the entry point for UE registrations, as the next most likely failure point.

### Scoring Breakdown

**Overall score: 40%**

**Scorer assessment:** The agent correctly identified the severity and that the HSS was down, and attributed it to the correct layer. However, it incorrectly 'falsified' the HSS as the root cause and misidentified the primary affected component, leading to a low overall score.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | No | The simulated failure's root causes were PyHSS being down and S-CSCF having high latency. The agent explicitly states that the HSS failure was 'falsified' as the root cause and instead points to the P-CSCF as the primary suspect. This is incorrect; the HSS being down is a primary root cause of the IMS outage. |
| Component overlap | 0% | The agent lists 'pcscf' as 'Root Cause (Suspected)', which is incorrect. It lists 'pyhss' (a correct root cause) as 'Secondary (Confirmed down, but not the root cause)' and 'scscf' (another correct root cause) as 'Symptomatic'. Neither of the actual root cause components are identified as the primary 'Root Cause' in the affected_components list. |
| Severity correct | Yes | The agent correctly identifies the impact as a 'complete outage in the IMS network' preventing 'all user registrations and VoNR calls', which matches the simulated 'Total IMS outage'. |
| Fault type identified | Yes | The agent correctly identifies that the 'pyhss' container 'had exited' and was 'down', which is a correct observable fault type for the HSS. While it doesn't explicitly mention latency for S-CSCF, it correctly identifies the 'down' state of a key component. |
| Layer accuracy | Yes | The agent's network analysis correctly rates the 'ims' layer as 'red' and provides evidence that 'The 'pyhss' container has exited.', which aligns with the ground truth that 'pyhss' belongs to the 'ims' layer. |
| Confidence calibrated | Yes | The agent's confidence is 'low', which is appropriate given its significant error in identifying the root cause (falsifying the HSS as root cause and incorrectly suspecting P-CSCF) despite correctly identifying the HSS was down. |

**Ranking:** The correct root cause (pyhss) is explicitly stated as 'not the root cause' and ranked as 'Secondary', while an incorrect component (pcscf) is ranked as the 'Root Cause (Suspected)'.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 97,288 |
| Output tokens | 2,772 |
| Thinking tokens | 9,529 |
| **Total tokens** | **109,589** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| EventAggregator | 0 | 0 | 0 |
| CorrelationAnalyzer | 0 | 0 | 0 |
| NetworkAnalystAgent | 52,030 | 4 | 5 |
| InstructionGeneratorAgent | 24,121 | 3 | 4 |
| InvestigatorAgent_h1 | 29,622 | 2 | 3 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 3,816 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 302.8s
