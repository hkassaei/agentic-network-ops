# Episode Report: AMF Restart (Upgrade Simulation)

**Agent:** v6  
**Episode ID:** ep_20260428_025930_amf_restart_(upgrade_simulatio  
**Date:** 2026-04-28T02:59:32.023215+00:00  
**Duration:** 274.8s  

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
- **Nodes with significant deltas:** 4
- **Nodes with any drift:** 5

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 0.99 (threshold: 0.70, trained on 104 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

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

- **`icscf.cdp:average_response_time`** (I-CSCF Diameter average response time) — current **48.00 ms** vs learned baseline **63.54 ms** (HIGH, shift)
    - **What it measures:** Responsiveness of the Cx path and HSS processing speed. A spike
without timeouts = pure latency; a spike WITH timeout_ratio rising
= approaching timeout ceiling (HSS overload or partial partition).
    - **Shift means:** HSS slow, network latency to HSS, or HSS overload.
    - **Healthy typical range:** 30–100 ms

- **`normalized.smf.bearers_per_ue`** (Active QoS bearers per UE) — current **0.00 count** vs learned baseline **2.59 count** (HIGH, drop)
    - **What it measures:** Per-UE count of active QoS bearers. Baseline reflects default
bearers; increments during VoNR calls indicate dedicated voice
bearers being set up. Drop during an active call = dedicated
bearer torn down unexpectedly (voice will fail).
    - **Drop means:** Lost bearers. If sustained during a call, voice path is broken.
    - **Healthy typical range:** 2–3.5 count
    - **Healthy invariant:** At rest: equals configured default bearers (typically 2 per UE).
During active VoNR call: +1 per caller. The per-UE ratio is the
invariant; absolute count scales with UE pool.

- **`normalized.upf.gtp_outdatapktn3upf_per_ue`** (GTP-U downlink rate per UE (N3)) — current **0.00 packets_per_second** vs learned baseline **3.37 packets_per_second** (HIGH, drop)
    - **What it measures:** Health of the downlink user-plane path UPF → gNB. Typically mirrors
uplink rate during calls/data; asymmetry indicates directional
faults (e.g., UPF receiving from internet but not forwarding).
    - **Drop means:** No traffic leaving UPF toward RAN.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE — constant regardless of UE pool size. Roughly symmetric with uplink during healthy calls.

- **`normalized.upf.gtp_indatapktn3upf_per_ue`** (GTP-U uplink rate per UE (N3)) — current **0.00 packets_per_second** vs learned baseline **3.44 packets_per_second** (HIGH, drop)
    - **What it measures:** Health of the uplink user-plane path gNB → UPF. Drops to near-zero
during RAN or N3 outage; stays nonzero during active calls or data
sessions. Decoupled from SIP signaling (signals data plane, not
control plane).
    - **Drop means:** Data plane dead on uplink — UPF receiving no packets from gNB.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE — constant regardless of UE pool size. Rises during active VoNR calls (~100 pps for G.711 voice) and data transfer.

- **`icscf.ims_icscf:lir_avg_response_time`** (I-CSCF LIR response time) — current **40.00 ms** vs learned baseline **62.98 ms** (MEDIUM, shift)
    - **What it measures:** Call-routing-specific Cx leg. If LIR is healthy but UAR is slow,
registration path has a specific issue separate from call routing.
    - **Shift means:** HSS slow to respond to LIR; affects call setup.
    - **Healthy typical range:** 30–100 ms

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

**1 events fired during the observation window:**

- `core.smf.sessions_per_ue_drop` (source: `core.smf.sessions_per_ue`, nf: `smf`, t=1777345300.3)  [current_value=0.0, prior_stable_value=2.0, delta_percent=-100.0]

## Correlation Analysis (Phase 2)

1 events fired but no composite hypothesis emerged. The events may be from independent faults or lack registered correlation hints in the KB.

## Network Analysis (Phase 3)

**Summary:** The AMF container has exited, causing a complete control plane outage which prevents UEs from registering and accessing any network services.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | All infrastructure components (databases, DNS) appear to be running correctly. |
| **ran** | 🟡 YELLOW | The RAN itself is likely functional, but its connection to the core network is down due to the AMF failure. It has no path to forward UE requests. |
| **core** | 🔴 RED | The AMF, a critical core component, has failed. This has led to a complete failure in UE attachment and session management, taking down the entire data plane. |
| **ims** | 🟡 YELLOW | The IMS components are running, but no UEs can register to use IMS services because the core network is down. The IMS stack is a victim of the core failure, not the cause. |

**RAN evidence:**
- N2 (NGAP): [RAN] → AMF [INACTIVE — AMF is exited]

**CORE evidence:**
- AMF container has exited.
- normalized.smf.sessions_per_ue is 0.
- normalized.smf.bearers_per_ue is 0.
- normalized.upf.gtp_outdatapktn3upf_per_ue is 0.
- normalized.upf.gtp_indatapktn3upf_per_ue is 0.

**IMS evidence:**
- normalized.pcscf.dialogs_per_ue is 0.

**Ranked hypotheses:**

- **`h1`** (fit=1.00, nf=amf, specificity=specific):
    - **Statement:** The Access and Mobility Management Function (AMF) has exited, causing a complete outage of the 5G core's control plane for UE registration. This prevents UEs from attaching to the network, which in turn means no PDU sessions can be established, leading to a drop in all user-plane and session-related metrics to zero.
    - **Supporting events:** `core.smf.sessions_per_ue_drop`
    - **Falsification probes:**
        - Check the 'amf' container logs for the reason it exited.
        - Attempt to restart the 'amf' container and observe if services are restored.
        - Verify connectivity from the AMF's host to its dependencies (NRF, SCP).


## Falsification Plans (Phase 4)

**1 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `amf`)

**Hypothesis:** The Access and Mobility Management Function (AMF) has exited, causing a complete outage of the 5G core's control plane for UE registration. This prevents UEs from attaching to the network, which in turn means no PDU sessions can be established, leading to a drop in all user-plane and session-related metrics to zero.

**Probes (3):**
1. **`get_network_status`** — None
    - *Expected if hypothesis holds:* The 'amf' container has a status of 'exited' or 'down'.
    - *Falsifying observation:* The 'amf' container is 'running'. This directly falsifies the hypothesis.
2. **`measure_rtt`** — from: nr_gnb, to: amf_ip
    - *Expected if hypothesis holds:* 100% packet loss. The AMF container is down and cannot respond to pings.
    - *Falsifying observation:* A clean RTT (< 5ms) indicates the AMF is up and responsive on the network, falsifying the hypothesis.
3. **`measure_rtt`** — from: smf, to: amf_ip
    - *Expected if hypothesis holds:* 100% packet loss, confirming the AMF is unreachable from within the core network.
    - *Falsifying observation:* A clean RTT (< 5ms). This is a triangulation probe; a success here while the gNB probe fails would point to a RAN-Core network partition, not a failed AMF container, thus falsifying the hypothesis as stated.

*Notes:* The plan focuses on directly verifying the central claim of the hypothesis: that the AMF container has exited. Probe 1 is a direct check. Probes 2 and 3 confirm the expected network-level impact (unreachability) from both the RAN and another core component to ensure the AMF itself is the problem, not a network partition.


## Parallel Investigators (Phase 5)

**1 sub-Investigator verdict(s):** **1 NOT_DISPROVEN**

### `h1` — ✅ **NOT_DISPROVEN**

**Hypothesis:** The Access and Mobility Management Function (AMF) has exited, causing a complete outage of the 5G core's control plane for UE registration. This prevents UEs from attaching to the network, which in turn means no PDU sessions can be established, leading to a drop in all user-plane and session-related metrics to zero.

**Reasoning:** The executed probes confirmed the central claims of the hypothesis. `get_network_status` showed the AMF container has 'exited'. `measure_rtt` from the SMF to the AMF's IP address showed 100% packet loss, confirming its unreachability within the core network. No contradictory evidence was found.

**Probes executed (3):**
- **Check if the 'amf' container has a status of 'exited' or 'down'.** ✓ CONSISTENT
    - *Tool:* `default_api.get_network_status()`
    - *Observation:* [EVIDENCE: get_network_status() -> "'amf': 'exited'"]
    - *Comment:* The primary claim of the hypothesis, that the AMF has exited, is directly confirmed by the network status.
- **Measure RTT from RAN to AMF to confirm unreachability.** ~ AMBIGUOUS
    - *Tool:* `default_api.measure_rtt(container = "nr_gnb", target_ip = "172.22.0.10")`
    - *Observation:* [EVIDENCE: measure_rtt("nr_gnb", "172.22.0.10") -> "Unknown container 'nr_gnb'."]
    - *Comment:* The probe could not be executed as planned because the container 'nr_gnb' was not found. The IP for AMF was determined to be 172.22.0.10 from read_env_config.
- **Measure RTT from SMF to AMF to confirm unreachability from within the core.** ✓ CONSISTENT
    - *Tool:* `default_api.measure_rtt(container = "smf", target_ip = "172.22.0.10")`
    - *Observation:* [EVIDENCE: measure_rtt("smf", "172.22.0.10") -> "100% packet loss"]
    - *Comment:* This confirms the network-level impact of the AMF container being down. It is unreachable from another critical core component (SMF).


## Evidence Validation (Phase 6)

**Overall verdict:** clean
**Overall confidence:** high

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 4 | 3/3 | clean | high |


## Ground Truth

**Failure domain:** core_control_plane  
**Protocol impact:** NGAP  
**Affected components:** amf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v6-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 133.1s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: The Access and Mobility Management Function (AMF) container has exited, causing a complete control plane outage that prevents user devices from registering with the network.
> - **timeline**:
>     1. The first symptom observed was the `core.smf.sessions_per_ue_drop` event, indicating a catastrophic failure in the network's ability to maintain user sessions.
>     2. Investigation confirmed the AMF container, a critical control plane component, had a status of 'exited'.
>     3. Network probes confirmed the AMF was unreachable from other core components (e.g., the SMF), verifying the network impact of the exited container.
> - **root_cause**: The AMF container has exited. The reason for its exit is the underlying fault. (primary_suspect_nf: `amf`)
> - **affected_components**:
>     - `amf`: Root Cause
>     - `core`: Secondary (The failure of the AMF renders the entire core control plane non-functional)
>     - `ran`: Symptomatic (The RAN is operational but cannot connect UEs to a non-responsive core)
>     - `ims`: Symptomatic (The IMS stack is running but is unusable as no UEs can register)
> - **recommendation**: Investigate the 'amf' container logs to determine the reason it exited (e.g., application crash, out-of-memory error, configuration issue). Verify that the host has sufficient resources (CPU, memory) allocated for the container.
> - **confidence**: high
> - **explanation**: The initial hypothesis, stating the AMF had exited and caused a control plane outage, was directly confirmed by the investigation. Probes showed the 'amf' container had 'exited' and was unreachable within the network, validating the hypothesis. This single point of failure in the AMF is the definitive root cause of the outage, as it is responsible for UE registration. Without a functional AMF, no UEs can attach to the network, which explains the complete drop in all session and user-plane metrics. No contradictory evidence was found.

### Scoring Breakdown

**Overall score: 100%**

**Scorer assessment:** The agent provided an excellent and accurate diagnosis, correctly identifying the root cause, affected component, severity, fault type, and layer, with appropriate confidence.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | Yes | The simulated failure was the AMF being temporarily unavailable/stopped. The agent correctly identified the root cause as 'The AMF container has exited', which is semantically equivalent to the simulated failure mode. |
| Component overlap | 100% | The primary affected component, 'amf', was correctly identified and listed as 'Root Cause' in the `affected_components` list. |
| Severity correct | Yes | The simulated failure involved the AMF being stopped, leading to UEs losing NAS connection and a temporary PDU session disruption, which implies a complete outage for affected UEs. The agent correctly diagnosed a 'complete control plane outage' and 'complete drop in all session and user-plane metrics', matching the severity. |
| Fault type identified | Yes | The simulated failure was the AMF being stopped/unavailable. The agent identified this as the 'AMF container has exited' and being 'unreachable', which correctly describes a component being down/unresponsive. |
| Layer accuracy | Yes | The ground truth states 'amf' belongs to the 'core' layer. The agent's network analysis correctly rated the 'core' layer as 'red' with the evidence 'AMF container has exited.', accurately attributing the failure to its correct ontology layer. |
| Confidence calibrated | Yes | The agent stated 'high' confidence, and its diagnosis was accurate across all dimensions, making the confidence level well-calibrated. |

**Ranking position:** #1 — The agent provided a single, clear root cause, which was correct.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 106,035 |
| Output tokens | 2,361 |
| Thinking tokens | 7,515 |
| **Total tokens** | **115,911** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| EventAggregator | 0 | 0 | 0 |
| CorrelationAnalyzer | 0 | 0 | 0 |
| NetworkAnalystAgent | 50,825 | 4 | 5 |
| InstructionGeneratorAgent | 13,554 | 1 | 2 |
| InvestigatorAgent_h1 | 47,910 | 4 | 5 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 3,622 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 274.8s
