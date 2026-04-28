# Episode Report: AMF Restart (Upgrade Simulation)

**Agent:** v6  
**Episode ID:** ep_20260424_200342_amf_restart_(upgrade_simulatio  
**Date:** 2026-04-24T20:03:44.567808+00:00  
**Duration:** 288.3s  

---

## Scenario

**Category:** container  
**Blast radius:** multi_nf  
**Description:** Stop the AMF for 10 seconds, then restart it. Simulates a rolling upgrade of the access and mobility management function. UEs will temporarily lose their 5G NAS connection and must re-attach.

## Faults Injected

- **container_stop** on `amf` — {'timeout': 10}

## Baseline (Pre-Fault)

Stack phase before injection: **ready**
All containers running at baseline.

## Fault Propagation Verification

**Verdict:** ✅ `confirmed`

- **Wait:** 0s
- **Actual elapsed:** 0.0s
- **Nodes with significant deltas:** 3
- **Nodes with any drift:** 5

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 1.00 (threshold: 0.70, trained on 209 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following metrics deviate from their learned-healthy baseline. Treat each as a semantic observation (meaning + numbers), not a number alone — the KB's interpretation is the authoritative reading.

- **`normalized.smf.sessions_per_ue`** (PDU sessions per attached UE) — current **0.00 count** vs learned baseline **2.00 count** (HIGH, drop)
    - **What it measures:** Ratio of established PDU sessions to RAN-attached UEs. Constant under
healthy operation (depends on configured APNs per UE). Drift means
some UEs lost or failed to establish their sessions — usually points
to SMF or UPF control-plane issues, since attachment (ran_ue) is
independent of session establishment.
    - **Drop means:** Some UEs have fewer PDU sessions than they should. Likely SMF or PFCP (N4) issues.
    - **Healthy typical range:** 1.9–2.1 count
    - **Healthy invariant:** Constant equal to configured_apns_per_ue (typically 2). Scale-independent.

- **`icscf.ims_icscf:uar_avg_response_time`** (I-CSCF UAR response time) — current **69.00 ms** vs learned baseline **62.50 ms** (HIGH, shift)
    - **What it measures:** Specifically the UAR leg of the Cx interface. Spikes here without
LIR spikes are unusual — either UAR-handler issue at HSS or
specific network path to that code path.
    - **Shift means:** UAR-specific HSS slowness.
    - **Healthy typical range:** 30–100 ms

- **`derived.upf_activity_during_calls`** — current **1.00** vs learned baseline **0.09** (HIGH, spike). *(No KB context available — interpret from the metric name.)*

- **`normalized.smf.bearers_per_ue`** (Active QoS bearers per UE) — current **0.00 count** vs learned baseline **4.15 count** (HIGH, drop)
    - **What it measures:** Per-UE count of active QoS bearers. Baseline reflects default
bearers; increments during VoNR calls indicate dedicated voice
bearers being set up. Drop during an active call = dedicated
bearer torn down unexpectedly (voice will fail).
    - **Drop means:** Lost bearers. If sustained during a call, voice path is broken.
    - **Healthy typical range:** 2–3.5 count
    - **Healthy invariant:** At rest: equals configured default bearers (typically 2 per UE).
During active VoNR call: +1 per caller. The per-UE ratio is the
invariant; absolute count scales with UE pool.

- **`normalized.upf.gtp_outdatapktn3upf_per_ue`** (GTP-U downlink rate per UE (N3)) — current **0.00 packets_per_second** vs learned baseline **6.08 packets_per_second** (HIGH, drop)
    - **What it measures:** Health of the downlink user-plane path UPF → gNB. Typically mirrors
uplink rate during calls/data; asymmetry indicates directional
faults (e.g., UPF receiving from internet but not forwarding).
    - **Drop means:** No traffic leaving UPF toward RAN.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE — constant regardless of UE pool size. Roughly symmetric with uplink during healthy calls.

- **`normalized.upf.gtp_indatapktn3upf_per_ue`** (GTP-U uplink rate per UE (N3)) — current **0.00 packets_per_second** vs learned baseline **6.15 packets_per_second** (HIGH, drop)
    - **What it measures:** Health of the uplink user-plane path gNB → UPF. Drops to near-zero
during RAN or N3 outage; stays nonzero during active calls or data
sessions. Decoupled from SIP signaling (signals data plane, not
control plane).
    - **Drop means:** Data plane dead on uplink — UPF receiving no packets from gNB.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE — constant regardless of UE pool size. Rises during active VoNR calls (~100 pps for G.711 voice) and data transfer.

- **`icscf.cdp:average_response_time`** (I-CSCF Diameter average response time) — current **67.00 ms** vs learned baseline **61.05 ms** (HIGH, shift)
    - **What it measures:** Responsiveness of the Cx path and HSS processing speed. A spike
without timeouts = pure latency; a spike WITH timeout_ratio rising
= approaching timeout ceiling (HSS overload or partial partition).
    - **Shift means:** HSS slow, network latency to HSS, or HSS overload.
    - **Healthy typical range:** 30–100 ms

- **`normalized.pcscf.dialogs_per_ue`** (Active SIP dialogs per registered UE at P-CSCF) — current **0.00 count** vs learned baseline **1.58 count** (MEDIUM, drop)
    - **What it measures:** How many calls per user are currently in progress at the P-CSCF.
Going to zero from a non-zero baseline means calls have ended
(normal) OR call setup is failing system-wide (degradation).
Together with rcv_requests_* it discriminates the two.
    - **Drop means:** No active calls. Normal at rest; suspicious if prior state had calls AND INVITE rate is also zero.
    - **Healthy typical range:** 0–1 count
    - **Healthy invariant:** Per-UE — scale-independent. 0 at rest, ~1 per active VoNR call.

- **`scscf.ims_registrar_scscf:sar_avg_response_time`** (S-CSCF SAR response time) — current **110.00 ms** vs learned baseline **108.62 ms** (MEDIUM, shift)
    - **What it measures:** Second S-CSCF ↔ HSS leg. Together with MAR, these are the S-CSCF-side
Diameter contribution to register_time.
    - **Shift means:** HSS slow for SAR. Less common than MAR.
    - **Healthy typical range:** 50–150 ms

- **`scscf.ims_auth:mar_avg_response_time`** (S-CSCF MAR response time) — current **118.00 ms** vs learned baseline **113.13 ms** (MEDIUM, shift)
    - **What it measures:** S-CSCF side of the Cx interface. If MAR latency spikes alongside
I-CSCF UAR/LIR spikes, it's HSS-wide; if only MAR spikes, it's
S-CSCF ↔ HSS specific.
    - **Shift means:** HSS slow responding to MAR.
    - **Healthy typical range:** 50–150 ms


## Event Aggregation (Phase 1)

**1 events fired during the observation window:**

- `core.smf.sessions_per_ue_drop` (source: `core.smf.sessions_per_ue`, nf: `smf`, t=1777061152.0)  [current_value=0.0, prior_stable_value=2.0, delta_percent=-100.0]

## Correlation Analysis (Phase 2)

1 events fired but no composite hypothesis emerged. The events may be from independent faults or lack registered correlation hints in the KB.

## Network Analysis (Phase 3)

**Summary:** The AMF container has exited, causing a complete outage of the 5G core control plane, preventing UE registration and all subsequent network activities.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | All underlying infrastructure components (kubernetes, networking, etc.) appear to be running correctly, as other containers are unaffected. |
| **ran** | 🔴 RED | The RAN is likely functional, but has no path into the core network due to the AMF failure. No data is being exchanged. |
| **core** | 🔴 RED | The AMF, a critical component of the 5G core, has failed. This is the root cause of the outage. |
| **ims** | 🟡 YELLOW | IMS components are running but are unusable as no UEs can register to use IMS services. The elevated response times are likely due to repeated failed attempts from the IMS components to interact with the dead 5G core. |

**RAN evidence:**
- normalized.upf.gtp_indatapktn3upf_per_ue drop
- normalized.upf.gtp_outdatapktn3upf_per_ue drop

**CORE evidence:**
- AMF container has exited
- core.smf.sessions_per_ue_drop
- normalized.smf.bearers_per_ue drop

**IMS evidence:**
- normalized.pcscf.dialogs_per_ue drop
- icscf.ims_icscf:uar_avg_response_time shift
- scscf.ims_registrar_scscf:sar_avg_response_time shift
- scscf.ims_auth:mar_avg_response_time shift

**Ranked hypotheses:**

- **`h1`** (fit=1.00, nf=amf, specificity=specific):
    - **Statement:** The AMF container has exited, causing a complete failure in the 5G core control plane. This prevents UEs from registering and accessing any services, leading to a drop in PDU sessions and all other related metrics.
    - **Supporting events:** `core.smf.sessions_per_ue_drop`
    - **Falsification probes:**
        - Check the logs of the AMF container to determine the cause of the unexpected exit.
        - Attempt to restart the AMF container and observe if network services are restored.
- **`h2`** (fit=0.20, nf=smf, specificity=moderate):
    - **Statement:** An internal software bug or resource leak within the SMF is causing it to fail to manage PDU sessions correctly, leading to a session drop for all UEs.
    - **Supporting events:** `core.smf.sessions_per_ue_drop`
    - **Falsification probes:**
        - Examine the SMF's logs for any error messages or stack traces related to PDU session management that occurred before the AMF failed.
        - Analyze the SMF's memory and CPU usage over time to check for a resource leak.


## Falsification Plans (Phase 4)

**2 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `amf`)

**Hypothesis:** The AMF container has exited, causing a complete failure in the 5G core control plane. This prevents UEs from registering and accessing any services, leading to a drop in PDU sessions and all other related metrics.

**Probes (3):**
1. **`check_process_listeners`** — container='amf'
    - *Expected if hypothesis holds:* Command fails or returns an empty list, as the container's main process has exited and is not listening on any network sockets.
    - *Falsifying observation:* A list of listening ports is returned, indicating the AMF process is alive and running.
2. **`get_nf_metrics`** — nf='nr_gnb', query_spec={'metric': 'sctp_connections', 'labels': {'remote_nf': 'amf'}}
    - *Expected if hypothesis holds:* Value of 0, indicating the gNB has no active N2 connection to the AMF.
    - *Falsifying observation:* A value of 1 or more, indicating a healthy SCTP connection is established from the RAN to the AMF.
3. **`get_nf_metrics`** — nf='smf', query_spec={'metric': 'http_client_requests_total', 'labels': {'server_name': 'amf', 'status_code_class': '5xx'}}
    - *Expected if hypothesis holds:* A high or rapidly increasing count of 5xx errors, indicating the SMF cannot reach the AMF over the N11 interface.
    - *Falsifying observation:* A zero or stable low count of 5xx errors, suggesting the N11 interface is healthy.

*Notes:* This plan focuses on directly verifying the central claim of H1 (the AMF process is dead) and then confirming the expected collateral impact on immediately adjacent components (gNB and SMF) that depend on it.

### Plan for `h2` (target: `smf`)

**Hypothesis:** An internal software bug or resource leak within the SMF is causing it to fail to manage PDU sessions correctly, leading to a session drop for all UEs.

**Probes (3):**
1. **`get_nf_metrics`** — nf='smf', query_spec={'metrics': ['container_cpu_usage', 'container_memory_usage']}
    - *Expected if hypothesis holds:* Abnormally high or steadily increasing CPU or memory usage, consistent with a software bug or resource leak.
    - *Falsifying observation:* Nominal and stable CPU and memory usage.
2. **`get_network_status`** — check status of 'amf' container
    - *Expected if hypothesis holds:* The AMF container is in a RUNNING state. If the SMF were the true root cause, other core components like the AMF should be unaffected.
    - *Falsifying observation:* The AMF container is in an EXITED or otherwise non-running state. This would indicate a problem external to the SMF and would strongly support H1 over H2.
3. **`get_nf_metrics`** — nf='upf', query_spec={'metric': 'n4_session_establishment_failures'}
    - *Expected if hypothesis holds:* A non-zero count of N4 session establishment failures, indicating the SMF is sending invalid requests or failing to manage the UPF correctly.
    - *Falsifying observation:* A zero count for N4 session establishment failures, suggesting the SMF-UPF interface is operating correctly.

*Notes:* This plan attempts to find direct evidence of the claimed SMF bug (resource leak) and its downstream impact (N4 errors). It critically includes a probe to check the status of the AMF, which serves as a powerful discriminator between H1 and H2.


## Parallel Investigators (Phase 5)

**2 sub-Investigator verdict(s):** **1 NOT_DISPROVEN**, **1 DISPROVEN**

### `h1` — ✅ **NOT_DISPROVEN**

**Hypothesis:** The AMF container has exited, causing a complete failure in the 5G core control plane. This prevents UEs from registering and accessing any services, leading to a drop in PDU sessions and all other related metrics.

**Reasoning:** Direct probes confirm the central claim of the hypothesis. Both `check_process_listeners` and `get_network_status` show that the AMF container has exited. While some specific collateral metrics on adjacent NFs (like gNB SCTP connections) could not be checked due to their absence in the tool output, no evidence contradicts the hypothesis. The confirmed dead state of the AMF is sufficient to explain the observed network failure.

**Probes executed (3):**
- **Command fails or returns an empty list, as the container's main process has exited and is not listening on any network sockets.** ✓ CONSISTENT
    - *Tool:* `check_process_listeners(container='amf')`
    - *Observation:* [EVIDENCE: check_process_listeners("amf") -> "Error response from daemon: container e0d230d12cc938dd02636a6a3b72da26094e31996d1e4f993c35d7bd1de8fea6 is not running"]
    - *Comment:* This directly confirms the core assertion of the hypothesis: the AMF process is not running because the container itself has exited.
- **Value of 0, indicating the gNB has no active N2 connection to the AMF.** ~ AMBIGUOUS
    - *Tool:* `get_nf_metrics()`
    - *Observation:* [EVIDENCE: get_nf_metrics() -> The full output did not contain any metrics for the nf='nr_gnb'.]
    - *Comment:* The metric `sctp_connections` for `nr_gnb` was not found. While this is consistent with a dead AMF (no connection is possible), the absence of all gNB metrics prevents a direct confirmation of a value of 0. The AMF's own metrics were also missing, as expected.
- **A high or rapidly increasing count of 5xx errors, indicating the SMF cannot reach the AMF over the N11 interface.** ✓ CONSISTENT
    - *Tool:* `get_network_status()`
    - *Observation:* [EVIDENCE: get_network_status() -> "{\"phase\": \"down\", \"running\": [...], \"down_or_absent\": [\"amf\"], \"containers\": {\"amf\": \"exited\", ...}}"]
    - *Comment:* Although I could not check the specific SMF->AMF error metric, I ran `get_network_status` instead to get a definitive state of the AMF. The output confirms the AMF container has 'exited', which strongly supports the hypothesis and explains why other components would fail to reach it.

### `h2` — ❌ **DISPROVEN**

**Hypothesis:** An internal software bug or resource leak within the SMF is causing it to fail to manage PDU sessions correctly, leading to a session drop for all UEs.

**Reasoning:** The falsification plan for H2 expected the AMF to be in a running state, as a failure within the SMF should not directly cause the AMF to exit. My probe revealed that the AMF container has, in fact, exited. This directly contradicts the hypothesis and points to the AMF itself as the likely root cause of the network outage, rather than the SMF.

**Probes executed (3):**
- **Check SMF CPU and memory usage for signs of a resource leak.** ~ AMBIGUOUS
    - *Tool:* `print(default_api.get_nf_metrics())`
    - *Observation:* [EVIDENCE: get_nf_metrics() -> "SMF [4 PDU] (via prometheus):\n  bearers_active = 8.0  [counter]\n  fivegs_smffunction_sm_sessionnbr = 4.0  [counter]\n  pfcp_sessions_active = 4.0  [counter]\n  ues_active = 2.0  [counter]"]
    - *Comment:* The tool output did not contain the specific metrics for container CPU or memory usage. The available SMF metrics are related to session counts and do not provide evidence for or against a resource leak.
- **Check the status of the AMF container.** ✗ CONTRADICTS
    - *Tool:* `print(default_api.get_network_status())`
    - *Observation:* [EVIDENCE: get_network_status() -> "{\n  \"phase\": \"down\", ... \"down_or_absent\": [\n    \"amf\"\n  ], ... \"containers\": { ... \"amf\": \"exited\", ... }\n}"]
    - *Comment:* The hypothesis assumes that if the SMF were the root cause, other core components like the AMF would be running. The observation that the AMF container is in an 'exited' state falsifies this assumption and strongly points towards an AMF-centric failure, as described in hypothesis H1.
- **Check for N4 session establishment failures between SMF and UPF.** ~ AMBIGUOUS
    - *Tool:* `print(default_api.get_nf_metrics())`
    - *Observation:* [EVIDENCE: get_nf_metrics() -> "UPF [16 sess] (via prometheus):\n  fivegs_ep_n3_gtp_indatapktn3upf = 137227.0  [counter] ..."]
    - *Comment:* The requested metric 'n4_session_establishment_failures' was not found in the metrics output for the UPF. Its absence is a weak signal and does not allow for a conclusion on whether the SMF-UPF interface is operating correctly.

**Alternative suspects:** amf


## Evidence Validation (Phase 6)

**Overall verdict:** clean
**Overall confidence:** high

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 3 | 3/3 | clean | high |
| `InvestigatorAgent_h2` | 2 | 3/3 | clean | high |


## Ground Truth

**Failure domain:** core_control_plane  
**Protocol impact:** NGAP  
**Affected components:** amf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v6-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 146.8s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: The AMF container has exited unexpectedly, causing a complete 5G core control plane failure, which prevents user devices from connecting to the network and accessing any services.
> - **timeline**:
>     1. A drop in PDU sessions per UE was detected (`core.smf.sessions_per_ue_drop`), signaling a widespread session failure.
> - **root_cause**: The unexpected exit of the AMF container. The `primary_suspect_nf` is `amf`.
> - **affected_components**:
>     - `amf`: Root Cause
>     - `smf`: Secondary
>     - `ran`: Symptomatic
>     - `ims`: Symptomatic
> - **recommendation**: Investigate the logs of the exited AMF container to determine the reason for its termination (e.g., crash, out-of-memory error, or configuration issue). Verify the container's status and review its logs before attempting any recovery actions.
> - **confidence**: high
> - **explanation**: The investigation confirmed that the AMF container is in an 'exited' state. This finding directly supports the primary hypothesis (`h1`) that a complete AMF failure is the root cause of the outage, explaining the drop in PDU sessions and the inability of UEs to register. An alternative hypothesis blaming an internal SMF bug (`h2`) was disproven, as an SMF failure would not directly cause the AMF container to exit. The exited AMF is the definitive cause of the control plane collapse.

### Scoring Breakdown

**Overall score: 100%**

**Scorer assessment:** The agent provided a perfectly accurate and well-calibrated diagnosis, correctly identifying the root cause, affected component, severity, fault type, and layer, with high confidence.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | Yes | The simulated failure was an AMF restart, meaning the AMF component was temporarily unavailable. The agent correctly identified the root cause as 'The unexpected exit of the AMF container', which is semantically equivalent to the AMF being stopped or unavailable. |
| Component overlap | 100% | The primary affected component was 'amf'. The agent correctly listed 'amf' as 'Root Cause' in its 'affected_components'. |
| Severity correct | Yes | The simulated failure involved the AMF being stopped, leading to UEs losing NAS connection and requiring re-attachment, which constitutes a temporary complete outage of the control plane. The agent's diagnosis of a 'complete 5G core control plane failure' and 'control plane collapse' accurately reflects this severity. |
| Fault type identified | Yes | The simulated failure mode was the AMF component being temporarily unavailable/stopped. The agent identified this as the 'unexpected exit of the AMF container', which correctly describes the observable fault type of a component being down or exited. |
| Layer accuracy | Yes | The ground truth states that 'amf' belongs to the 'core' layer. The agent's network analysis correctly rated the 'core' layer as 'red' and explicitly noted that 'The AMF, a critical component of the 5G core, has failed. This is the root cause of the outage.' |
| Confidence calibrated | Yes | The agent stated 'high' confidence, and its diagnosis was accurate and well-supported across all dimensions, making the confidence level appropriate. |

**Ranking position:** #1 — The agent provided a single, clear root cause, identifying 'amf' as the primary suspect and root cause, which was correct.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 93,469 |
| Output tokens | 3,813 |
| Thinking tokens | 11,429 |
| **Total tokens** | **108,711** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| EventAggregator | 0 | 0 | 0 |
| CorrelationAnalyzer | 0 | 0 | 0 |
| NetworkAnalystAgent | 22,034 | 4 | 2 |
| InstructionGeneratorAgent | 17,649 | 1 | 2 |
| InvestigatorAgent_h1 | 42,673 | 3 | 4 |
| InvestigatorAgent_h2 | 21,718 | 2 | 2 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 4,637 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 288.3s
