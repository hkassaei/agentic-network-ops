# Episode Report: Cascading IMS Failure

**Agent:** v6  
**Episode ID:** ep_20260428_030718_cascading_ims_failure  
**Date:** 2026-04-28T03:07:20.496721+00:00  
**Duration:** 344.5s  

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

**ANOMALY DETECTED.** Overall anomaly score: 0.94 (threshold: 0.70, trained on 104 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following metrics deviate from their learned-healthy baseline. Treat each as a semantic observation (meaning + numbers), not a number alone — the KB's interpretation is the authoritative reading.

- **`normalized.upf.gtp_outdatapktn3upf_per_ue`** (GTP-U downlink rate per UE (N3)) — current **0.03 packets_per_second** vs learned baseline **3.37 packets_per_second** (MEDIUM, drop)
    - **What it measures:** Health of the downlink user-plane path UPF → gNB. Typically mirrors
uplink rate during calls/data; asymmetry indicates directional
faults (e.g., UPF receiving from internet but not forwarding).
    - **Drop means:** No traffic leaving UPF toward RAN.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE — constant regardless of UE pool size. Roughly symmetric with uplink during healthy calls.

- **`normalized.upf.gtp_indatapktn3upf_per_ue`** (GTP-U uplink rate per UE (N3)) — current **0.12 packets_per_second** vs learned baseline **3.44 packets_per_second** (MEDIUM, drop)
    - **What it measures:** Health of the uplink user-plane path gNB → UPF. Drops to near-zero
during RAN or N3 outage; stays nonzero during active calls or data
sessions. Decoupled from SIP signaling (signals data plane, not
control plane).
    - **Drop means:** Data plane dead on uplink — UPF receiving no packets from gNB.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE — constant regardless of UE pool size. Rises during active VoNR calls (~100 pps for G.711 voice) and data transfer.

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

**Summary:** The IMS HSS has crashed, preventing all user authentications and subsequent call setups, which has resulted in a complete stall of the user data plane.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | No evidence of an infrastructure-layer fault. |
| **ran** | 🟢 GREEN | The RAN appears to be operational and connected to the core. |
| **core** | 🟡 YELLOW | The 5G core data plane is inactive, but this is a symptom of an IMS-layer fault, not a root cause within the core itself. Core NFs appear to be running correctly but are not being tasked by the IMS layer. |
| **ims** | 🔴 RED | The HSS is the authoritative source for subscriber data and authentication. Its failure is a critical fault that stops all IMS services. |

**CORE evidence:**
- UPF GTP data rates are near-zero, indicating no user plane traffic.
- SMF bearer count is at the baseline default, with no dedicated bearers for calls.

**IMS evidence:**
- The HSS container has exited and is not running.
- All Diameter-based links to the HSS (from I-CSCF and S-CSCF) are inactive.
- P-CSCF reports zero active SIP dialogs, indicating no active calls.

**Ranked hypotheses:**

- **`h1`** (fit=0.95, nf=pyhss, specificity=specific):
    - **Statement:** The HSS container has crashed, which prevents IMS subscriber registration and authentication. Without successful authentication via the HSS, no VoNR calls can be established, explaining the lack of SIP dialogs and the resultant zeroing of data plane traffic at the UPF.
    - **Falsification probes:**
        - Check the container logs for 'pyhss' to find a crash traceback.
        - Attempt to restart the 'pyhss' container and observe if IMS registrations and call setup succeed.
        - Inspect the logs of 'icscf' and 'scscf' for Diameter connection errors or timeouts when attempting to contact the HSS.
- **`h3`** (fit=0.80, nf=pyhss, specificity=specific):
    - **Statement:** A network partition is preventing the I-CSCF and S-CSCF from reaching the HSS. While the HSS container may be running, the failure of the Cx interface makes authentication impossible, leading to the same symptoms as a full HSS crash.
    - **Falsification probes:**
        - Executing 'measure_rtt' from the 'icscf' container to the 'pyhss' container IP would fail if a partition exists.
        - Check DNS resolution for the HSS service name from the 'scscf' container.
        - The 'get_network_status' tool showing HSS as 'exited' strongly contradicts this hypothesis in favor of h1.
- **`h2`** (fit=0.30, nf=upf, specificity=moderate):
    - **Statement:** The data plane is stalled because the UPF has an internal fault or is misconfigured, causing it to drop all GTP-U packets. This would directly explain the metrics showing near-zero traffic on the N3 interface.
    - **Falsification probes:**
        - Confirming the HSS is down (Hypothesis h1) would falsify this, as it provides an upstream reason for the lack of traffic.
        - Check PFCP association between SMF and UPF; if sessions are established, the UPF is likely configured correctly.
        - Inspect UPF-internal logs and metrics for packet drop counters or processing errors.


## Falsification Plans (Phase 4)

**3 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `pyhss`)

**Hypothesis:** The HSS container has crashed, which prevents IMS subscriber registration and authentication. Without successful authentication via the HSS, no VoNR calls can be established, explaining the lack of SIP dialogs and the resultant zeroing of data plane traffic at the UPF.

**Probes (3):**
1. **`get_network_status`** — Check running status of all containers
    - *Expected if hypothesis holds:* The 'pyhss' container has status 'exited'.
    - *Falsifying observation:* The 'pyhss' container has status 'running'.
2. **`get_nf_metrics`** — Check I-CSCF metrics for Diameter timeouts to the HSS. Specifically 'ims_icscf:uar_timeouts'.
    - *Expected if hypothesis holds:* The 'ims_icscf:uar_timeouts' counter on the I-CSCF is elevated and increasing.
    - *Falsifying observation:* The 'ims_icscf:uar_timeouts' counter is zero or not increasing, indicating successful UAR transactions.
3. **`run_kamcmd`** — container='scscf', command='ul.dump'
    - *Expected if hypothesis holds:* The user location table is empty, as no registrations can complete.
    - *Falsifying observation:* The user location table contains active registrations, which would be impossible if the HSS was crashed.

*Notes:* This plan directly tests the core assertion of the hypothesis: that the HSS container process is no longer running. Probes check for the process status, and then for the direct upstream consequences of it being down (Diameter timeouts from its clients).

### Plan for `h3` (target: `pyhss`)

**Hypothesis:** A network partition is preventing the I-CSCF and S-CSCF from reaching the HSS. While the HSS container may be running, the failure of the Cx interface makes authentication impossible, leading to the same symptoms as a full HSS crash.

**Probes (3):**
1. **`measure_rtt`** — From 'icscf' to 'pyhss' container IP.
    - *Expected if hypothesis holds:* 100% packet loss or extremely high RTT.
    - *Falsifying observation:* A clean, low RTT (<5ms) measurement, which proves connectivity is healthy.
2. **`measure_rtt`** — Triangulation probe: from 'pyhss' to 'icscf' container IP.
    - *Expected if hypothesis holds:* 100% packet loss, assuming a symmetric partition.
    - *Falsifying observation:* A clean, low RTT (<5ms) measurement. If both this and the forward probe succeed, the network path is bi-directionally healthy, falsifying the partition hypothesis.
3. **`get_network_status`** — Check running status of the 'pyhss' container.
    - *Expected if hypothesis holds:* The 'pyhss' container has status 'running'.
    - *Falsifying observation:* The 'pyhss' container has status 'exited'. A partition is irrelevant if the container is not running; this observation would confirm hypothesis h1 instead.

*Notes:* This plan focuses on testing the network reachability aspect of the hypothesis. It uses directional RTT measurements and a triangulation probe to confirm or deny the existence of a network partition, while also verifying the prerequisite that the HSS container is actually running.

### Plan for `h2` (target: `upf`)

**Hypothesis:** The data plane is stalled because the UPF has an internal fault or is misconfigured, causing it to drop all GTP-U packets. This would directly explain the metrics showing near-zero traffic on the N3 interface.

**Probes (3):**
1. **`get_nf_metrics`** — Activity-vs-drops discriminator: Compare gNB's transmitted GTP-U bytes ('ran_gtpu_bytes_tx') with UPF's received GTP-U bytes ('upf_gtpu_bytes_rx').
    - *Expected if hypothesis holds:* The gNB's 'ran_gtpu_bytes_tx' is non-zero, while the UPF's 'upf_gtpu_bytes_rx' is zero or near-zero.
    - *Falsifying observation:* The gNB's 'ran_gtpu_bytes_tx' is zero. This proves no traffic is being sent to the UPF, so the UPF cannot be the component dropping it.
2. **`get_nf_metrics`** — Check UPF internal drop counters, such as 'upf_gtpu_packet_drops_internal_error'.
    - *Expected if hypothesis holds:* A non-zero and increasing value, indicating the UPF is dropping packets for internal reasons.
    - *Falsifying observation:* The counter is zero, suggesting the UPF is not self-reporting any internal packet drops.
3. **`get_nf_metrics`** — Check for control plane issues between SMF and UPF by inspecting PFCP session failure metrics on the SMF (e.g., 'smf_pfcp_session_establishment_failures').
    - *Expected if hypothesis holds:* The counter is zero, as this hypothesis posits a data plane fault, not a control plane one.
    - *Falsifying observation:* A high number of PFCP failures. This indicates the problem is in the control plane setup, not silent dropping on the data plane, thus changing the fault's location.

*Notes:* This plan is designed to test the 'silent drop' theory at the UPF. It uses an activity-vs-drops check to see if the UPF is receiving traffic from upstream, and then checks internal UPF metrics for evidence of drops or control plane failures that would provide an alternative explanation.


## Parallel Investigators (Phase 5)

**3 sub-Investigator verdict(s):** **3 DISPROVEN**

### `h1` — ❌ **DISPROVEN**

**Hypothesis:** The HSS container has crashed, which prevents IMS subscriber registration and authentication. Without successful authentication via the HSS, no VoNR calls can be established, explaining the lack of SIP dialogs and the resultant zeroing of data plane traffic at the UPF.

**Reasoning:** The hypothesis is disproven because two of the three probes returned evidence that contradicts the expected consequences of a crashed HSS. While the HSS container was indeed found to be 'exited', there were no corresponding Diameter timeouts on the I-CSCF, and more importantly, the S-CSCF still held active user registrations. This contradicts the hypothesis's central claim that the HSS crash is preventing all authentications and registrations.

**Probes executed (3):**
- **Check running status of all containers** ✓ CONSISTENT
    - *Tool:* `print(default_api.get_network_status())`
    - *Observation:* [EVIDENCE: get_network_status() -> "'pyhss': 'exited'"]
    - *Comment:* The pyhss container was found to be 'exited', which is consistent with the hypothesis that the HSS has crashed.
- **Check I-CSCF metrics for Diameter timeouts to the HSS. Specifically 'ims_icscf:uar_timeouts'.** ✗ CONTRADICTS
    - *Tool:* `print(default_api.get_nf_metrics())`
    - *Observation:* [EVIDENCE: get_nf_metrics() -> "ims_icscf:uar_timeouts = 0.0  [counter]"]
    - *Comment:* The 'ims_icscf:uar_timeouts' counter is zero. If the HSS were unreachable due to a crash, this counter was expected to be elevated as the I-CSCF failed to get replies to authentication requests. This contradicts the hypothesis.
- **run_kamcmd, container='scscf', command='ul.dump'** ✗ CONTRADICTS
    - *Tool:* `print(default_api.run_kamcmd(command = "ul.dump", container = "scscf"))`
    - *Observation:* [EVIDENCE: get_nf_metrics() -> "ims_usrloc_scscf:active_contacts = 2.0  [counter]"]
    - *Comment:* The initial probe command failed. However, examining metrics from the S-CSCF shows 2 active contacts. This contradicts the hypothesis's expectation that the user location table would be empty because no registrations could complete without the HSS.

**Alternative suspects:** scscf, icscf

### `h3` — ❌ **DISPROVEN**

**Hypothesis:** A network partition is preventing the I-CSCF and S-CSCF from reaching the HSS. While the HSS container may be running, the failure of the Cx interface makes authentication impossible, leading to the same symptoms as a full HSS crash.

**Reasoning:** The hypothesis is predicated on the HSS container being online but unreachable. The first probe, `get_network_status`, directly falsified this by showing the `pyhss` container has a status of 'exited'. A network partition is irrelevant if the destination container is not running. A second probe confirmed that the Diameter peer connection from I-CSCF to HSS is 'Closed', which is the expected symptom of the HSS being down, not necessarily partitioned.

**Probes executed (2):**
- **Check running status of the 'pyhss' container.** ✗ CONTRADICTS
    - *Tool:* `print(default_api.get_network_status())`
    - *Observation:* [EVIDENCE: get_network_status() -> "'pyhss': 'exited'"]
    - *Comment:* The hypothesis assumes the HSS container is running, but it has exited. This directly contradicts the hypothesis's core premise and points to a container crash (h1) rather than a network issue.
- **Check the status of the Diameter connection from I-CSCF to HSS.** ✓ CONSISTENT
    - *Tool:* `print(default_api.run_kamcmd(container='icscf', command='cdp.list_peers'))`
    - *Observation:* [EVIDENCE: run_kamcmd('icscf', 'cdp.list_peers') -> "State: Closed"]
    - *Comment:* This observation is consistent with the symptom of a failed Cx interface. However, when combined with the knowledge that the pyhss container has exited, it supports the conclusion that the HSS has crashed, rather than being isolated by a network partition.

**Alternative suspects:** pyhss

### `h2` — ❌ **DISPROVEN**

**Hypothesis:** The data plane is stalled because the UPF has an internal fault or is misconfigured, causing it to drop all GTP-U packets. This would directly explain the metrics showing near-zero traffic on the N3 interface.

**Reasoning:** The hypothesis claims the UPF is dropping GTP-U packets. This requires that packets are being sent to it. However, probes reveal that the UPF is receiving zero packets per second. If no traffic is arriving at the UPF, it cannot be responsible for dropping it. This observation directly contradicts the hypothesis and indicates the fault lies upstream from the UPF, preventing traffic from being sent in the first place.

**Probes executed (3):**
- **Activity-vs-drops discriminator: Compare gNB's transmitted GTP-U bytes ('ran_gtpu_bytes_tx') with UPF's received GTP-U bytes ('upf_gtpu_bytes_rx').** ✗ CONTRADICTS
    - *Tool:* `print(default_api.get_dp_quality_gauges())`
    - *Observation:* [EVIDENCE: get_dp_quality_gauges() -> "UPF: in packets/sec: 0.0"]
    - *Comment:* The hypothesis expects the UPF to be receiving packets and then dropping them. This probe shows zero packets are arriving at the UPF. This contradicts the premise of the hypothesis, as the UPF cannot drop packets it never receives. The issue is upstream.
- **Check UPF internal drop counters, such as 'upf_gtpu_packet_drops_internal_error'.** ~ AMBIGUOUS
    - *Tool:* `print(default_api.get_nf_metrics())`
    - *Observation:* [EVIDENCE: get_nf_metrics() -> "UPF [8 sess] (via prometheus): <metrics list>"]
    - *Comment:* The metrics output for the UPF does not contain any counters for internal packet drops. While this could mean no drops are occurring (which would contradict the hypothesis), it could also mean the metric simply isn't exported. The result is ambiguous.
- **Check for control plane issues between SMF and UPF by inspecting PFCP session failure metrics on the SMF (e.g., 'smf_pfcp_session_establishment_failures').** ✓ CONSISTENT
    - *Tool:* `print(default_api.get_nf_metrics())`
    - *Observation:* [EVIDENCE: get_nf_metrics() -> "SMF [4 PDU] (via prometheus): pfcp_sessions_active = 4.0"]
    - *Comment:* The hypothesis posits a data plane fault, implying the control plane is healthy. Observing active PFCP sessions between the SMF and UPF is consistent with this expectation. However, this doesn't support the overall hypothesis, it just confirms one of its preconditions.

**Alternative suspects:** gNB, amf, smf, pyhss


## Evidence Validation (Phase 6)

**Overall verdict:** clean
**Overall confidence:** high

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 3 | 3/3 | clean | high |
| `InvestigatorAgent_h3` | 2 | 2/2 | clean | high |
| `InvestigatorAgent_h2` | 2 | 3/3 | clean | high |


## Ground Truth

**Failure domain:** ims_signaling  
**Protocol impact:** SIP  
**Affected components:** pyhss, scscf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v6-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 187.0s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: The initial hypotheses of an HSS crash, network partition, or UPF fault have been disproven, revealing a more complex issue where the IMS control plane (S-CSCF, I-CSCF) is not reacting correctly to the downed HSS, preventing call setup.
> - **timeline**:
>     1. The IMS HSS (`pyhss`) container crashed and is now in an 'exited' state.
>     2. Despite the HSS failure, the S-CSCF is anomalously maintaining at least two active user registrations.
>     3. The I-CSCF, which should be failing to contact the HSS, is not reporting any Diameter connection timeouts.
>     4. As a result of the control plane fault, no new VoNR calls can be authenticated or established, leading to a complete stall of user plane traffic at the UPF.
> - **root_cause**: The root cause is not yet confirmed, as all initial hypotheses were disproven. The investigation revealed contradictory evidence pointing to a complex failure in the IMS core. The primary suspects are now the **S-CSCF** and **I-CSCF** due to their unexpected behavior after the HSS went offline.
> - **affected_components**:
>     - `scscf`: Primary Suspect (anomalous behavior)
>     - `icscf`: Primary Suspect (anomalous behavior)
>     - `pyhss`: Secondary (crashed, but may not be the initiating cause)
>     - `upf`: Symptomatic (no traffic due to upstream control plane failure)
> - **recommendation**: The operator should investigate why the S-CSCF still holds active user registrations and why the I-CSCF is not reporting Diameter timeouts, given that the HSS container has exited. Focus on S-CSCF and I-CSCF logs around the time of the HSS failure to understand their state and error handling logic.
> - **confidence**: low
> - **explanation**: All initial hypotheses were disproven. The top hypothesis of a simple HSS crash was contradicted by evidence showing the S-CSCF still held active user registrations and the I-CSCF showed no connection timeouts, which should not be possible if the HSS were the sole point of failure. Hypotheses blaming the UPF or a network partition were also falsified. The fault lies within the IMS control plane, which is in an inconsistent state. Manual investigation is required, starting with the S-CSCF and I-CSCF.

### Scoring Breakdown

**Overall score: 50%**

**Scorer assessment:** The agent correctly identified the severity of the issue and the affected layer, and its low confidence was well-calibrated given its inconclusive diagnosis. However, it failed to correctly identify the root causes, downplaying the HSS crash and missing the S-CSCF latency, leading to a low component overlap score.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | No | The agent explicitly states that the root cause is 'not yet confirmed' and that 'all initial hypotheses were disproven'. While it identifies the pyhss container as crashed in the timeline, it then labels it as 'Secondary (crashed, but may not be the initiating cause)' in affected_components, effectively downplaying it as a root cause. It also completely misses the S-CSCF latency as a root cause, only noting 'anomalous behavior'. The agent's reasoning for disproving the HSS crash (S-CSCF registrations, I-CSCF not reporting timeouts) is a misinterpretation of the symptoms or a failure to connect the dots, as the HSS crash is indeed a primary root cause of the IMS outage. |
| Component overlap | 50% | The ground truth root cause components are 'pyhss' and 'scscf'. The agent lists 'scscf' as a 'Primary Suspect', which is a good identification for one of the root causes. However, it lists 'pyhss' as 'Secondary (crashed, but may not be the initiating cause)', which is a demotion for a primary root cause. It also incorrectly elevates 'icscf' to 'Primary Suspect'. Given one root cause is correctly identified as a primary suspect, but the other is demoted and an incorrect component is elevated, a score of 0.5 is appropriate. |
| Severity correct | Yes | The agent correctly identifies a complete service outage for IMS, stating 'no new VoNR calls can be authenticated or established, leading to a complete stall of user plane traffic at the UPF', which matches the 'Total IMS outage' and 'No voice calls possible' from the simulated failure. |
| Fault type identified | Yes | The agent identifies that the 'pyhss' container 'crashed and is now in an 'exited' state', which correctly identifies a 'component unreachable' fault type. While it misses the 'network degradation' (latency) aspect of the S-CSCF, it successfully identifies one of the primary observable fault types. |
| Layer accuracy | Yes | The agent's network analysis correctly rates the 'ims' layer as 'red' and provides evidence directly related to IMS components like HSS (pyhss) and Diameter links, aligning with the ground truth that 'pyhss' and 'scscf' belong to the IMS layer. |
| Confidence calibrated | Yes | The agent's confidence is 'low', which is appropriate given its failure to correctly identify the root causes and its misinterpretation of evidence, leading to an inconclusive diagnosis. The low confidence accurately reflects the quality of its final conclusion. |

**Ranking:** The agent does not provide a ranked list of root causes. It states the root cause is 'not yet confirmed' and lists 'primary suspects' in the affected components, but not as a ranked list of root causes.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 146,689 |
| Output tokens | 5,175 |
| Thinking tokens | 16,395 |
| **Total tokens** | **168,259** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| EventAggregator | 0 | 0 | 0 |
| CorrelationAnalyzer | 0 | 0 | 0 |
| NetworkAnalystAgent | 23,317 | 3 | 2 |
| InstructionGeneratorAgent | 32,662 | 2 | 3 |
| InvestigatorAgent_h1 | 43,689 | 3 | 4 |
| InvestigatorAgent_h3 | 26,183 | 2 | 3 |
| InvestigatorAgent_h2 | 36,564 | 2 | 3 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 5,844 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 344.5s
