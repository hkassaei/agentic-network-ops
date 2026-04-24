# Episode Report: AMF Restart (Upgrade Simulation)

**Agent:** v6  
**Episode ID:** ep_20260423_203455_amf_restart_(upgrade_simulatio  
**Date:** 2026-04-23T20:34:57.240689+00:00  
**Duration:** 293.3s  

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

**ANOMALY DETECTED.** Overall anomaly score: 0.96 (threshold: 0.70, trained on 211 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

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

- **`normalized.smf.bearers_per_ue`** (Active QoS bearers per UE) — current **0.00 count** vs learned baseline **2.61 count** (HIGH, drop)
    - **What it measures:** Per-UE count of active QoS bearers. Baseline reflects default
bearers; increments during VoNR calls indicate dedicated voice
bearers being set up. Drop during an active call = dedicated
bearer torn down unexpectedly (voice will fail).
    - **Drop means:** Lost bearers. If sustained during a call, voice path is broken.
    - **Healthy typical range:** 2–3.5 count
    - **Healthy invariant:** At rest: equals configured default bearers (typically 2 per UE).
During active VoNR call: +1 per caller. The per-UE ratio is the
invariant; absolute count scales with UE pool.

- **`normalized.upf.gtp_outdatapktn3upf_per_ue`** (GTP-U downlink rate per UE (N3)) — current **0.00 packets_per_second** vs learned baseline **3.34 packets_per_second** (HIGH, drop)
    - **What it measures:** Health of the downlink user-plane path UPF → gNB. Typically mirrors
uplink rate during calls/data; asymmetry indicates directional
faults (e.g., UPF receiving from internet but not forwarding).
    - **Drop means:** No traffic leaving UPF toward RAN.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE — constant regardless of UE pool size. Roughly symmetric with uplink during healthy calls.

- **`normalized.upf.gtp_indatapktn3upf_per_ue`** (GTP-U uplink rate per UE (N3)) — current **0.00 packets_per_second** vs learned baseline **3.42 packets_per_second** (HIGH, drop)
    - **What it measures:** Health of the uplink user-plane path gNB → UPF. Drops to near-zero
during RAN or N3 outage; stays nonzero during active calls or data
sessions. Decoupled from SIP signaling (signals data plane, not
control plane).
    - **Drop means:** Data plane dead on uplink — UPF receiving no packets from gNB.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE — constant regardless of UE pool size. Rises during active VoNR calls (~100 pps for G.711 voice) and data transfer.

- **`normalized.pcscf.dialogs_per_ue`** (Active SIP dialogs per registered UE at P-CSCF) — current **2.00 count** vs learned baseline **0.57 count** (MEDIUM, spike)
    - **What it measures:** How many calls per user are currently in progress at the P-CSCF.
Going to zero from a non-zero baseline means calls have ended
(normal) OR call setup is failing system-wide (degradation).
Together with rcv_requests_* it discriminates the two.
    - **Spike means:** Calls ending or setup failing.
    - **Healthy typical range:** 0–1 count
    - **Healthy invariant:** Per-UE — scale-independent. 0 at rest, ~1 per active VoNR call.

- **`scscf.ims_auth:mar_avg_response_time`** (S-CSCF MAR response time) — current **111.00 ms** vs learned baseline **91.62 ms** (MEDIUM, shift)
    - **What it measures:** S-CSCF side of the Cx interface. If MAR latency spikes alongside
I-CSCF UAR/LIR spikes, it's HSS-wide; if only MAR spikes, it's
S-CSCF ↔ HSS specific.
    - **Shift means:** HSS slow responding to MAR.
    - **Healthy typical range:** 50–150 ms

- **`icscf.ims_icscf:lir_avg_response_time`** (I-CSCF LIR response time) — current **60.00 ms** vs learned baseline **48.47 ms** (MEDIUM, shift)
    - **What it measures:** Call-routing-specific Cx leg. If LIR is healthy but UAR is slow,
registration path has a specific issue separate from call routing.
    - **Shift means:** HSS slow to respond to LIR; affects call setup.
    - **Healthy typical range:** 30–100 ms

- **`scscf.ims_registrar_scscf:sar_avg_response_time`** (S-CSCF SAR response time) — current **113.00 ms** vs learned baseline **100.81 ms** (MEDIUM, shift)
    - **What it measures:** Second S-CSCF ↔ HSS leg. Together with MAR, these are the S-CSCF-side
Diameter contribution to register_time.
    - **Shift means:** HSS slow for SAR. Less common than MAR.
    - **Healthy typical range:** 50–150 ms

- **`derived.pcscf_avg_register_time_ms`** (P-CSCF average SIP REGISTER processing time) — current **142.70 ms** vs learned baseline **248.24 ms** (LOW, shift)
    - **What it measures:** End-to-end cost of processing a SIP REGISTER through the IMS
signaling chain. Under healthy conditions, dominated by four
Diameter round-trips (UAR + LIR + MAR + SAR) plus SIP forwarding
overhead. Spikes without matching Diameter latency spikes indicate
SIP-path latency (P-CSCF itself or P-CSCF ↔ I-CSCF hop). Remains
meaningful when REGISTERs are failing — numerator and denominator
both track attempts, not completions.
    - **Shift means:** Latency injected on the REGISTER path. Compare against Diameter response times to localize.
    - **Healthy typical range:** 150–350 ms
    - **Healthy invariant:** Approximately equal to the sum of the four HSS Diameter round-trips
(UAR + LIR + MAR + SAR).
Large positive delta between observed register_time and this sum =
SIP-path latency (P-CSCF interface or P-CSCF ↔ I-CSCF).

- **`icscf.cdp:average_response_time`** (I-CSCF Diameter average response time) — current **57.00 ms** vs learned baseline **51.50 ms** (LOW, shift)
    - **What it measures:** Responsiveness of the Cx path and HSS processing speed. A spike
without timeouts = pure latency; a spike WITH timeout_ratio rising
= approaching timeout ceiling (HSS overload or partial partition).
    - **Shift means:** HSS slow, network latency to HSS, or HSS overload.
    - **Healthy typical range:** 30–100 ms


## Event Aggregation (Phase 1)

**1 events fired during the observation window:**

- `core.smf.sessions_per_ue_drop` (source: `core.smf.sessions_per_ue`, nf: `smf`, t=1776976624.9)  [current_value=0.0, prior_stable_value=2.0, delta_percent=-100.0]

## Correlation Analysis (Phase 2)

1 events fired but no composite hypothesis emerged. The events may be from independent faults or lack registered correlation hints in the KB.

## Network Analysis (Phase 3)

**Summary:** The 5G core network is down due to the unexpected termination of the Access and Mobility Management Function (AMF), causing a complete failure of PDU session establishment and a loss of the data plane.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | No evidence of infrastructure-level faults. |
| **ran** | 🟡 YELLOW | The RAN itself is likely functional, but it has lost its connection to the core network, rendering it unable to service UEs. |
| **core** | 🔴 RED | The core network is non-functional due to the AMF being down. This is the root cause of the outage. |
| **ims** | 🟡 YELLOW | The IMS stack is showing minor secondary symptoms but the primary issue preventing its use is the core network failure. |

**RAN evidence:**
- get_network_topology shows the N2 link from RAN to AMF is INACTIVE.

**CORE evidence:**
- get_network_status shows the 'amf' container has 'exited'.
- get_network_topology shows critical SBI and N2 links attached to the AMF are INACTIVE.
- Anomaly screener reported a 100% drop in PDU sessions, bearers, and GTP data plane traffic, which is a direct consequence of AMF failure.

**IMS evidence:**
- Anomaly screener noted minor latency increases for HSS-related Diameter transactions.
- The core network outage prevents UEs from establishing the PDU sessions required to access IMS services.

**Ranked hypotheses:**

- **`h1`** (fit=0.95, nf=amf, specificity=specific):
    - **Statement:** The Access and Mobility Management Function (AMF) has terminated unexpectedly. As the core control-plane function for registration and session management, its failure has halted all PDU session establishment, leading to a complete loss of data plane connectivity.
    - **Supporting events:** `core.smf.sessions_per_ue_drop`
    - **Falsification probes:**
        - Check the AMF's container logs to determine the reason for its termination.
        - Restart the AMF container and observe if UEs can subsequently establish PDU sessions.


## Falsification Plans (Phase 4)

**1 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `amf`)

**Hypothesis:** The Access and Mobility Management Function (AMF) has terminated unexpectedly. As the core control-plane function for registration and session management, its failure has halted all PDU session establishment, leading to a complete loss of data plane connectivity.

**Probes (3):**
1. **`get_network_status`** — Check the container status for 'amf'
    - *Expected if hypothesis holds:* The 'amf' container has a status of 'exited' or is not listed among running containers.
    - *Falsifying observation:* The 'amf' container is in a 'running' state. This would directly contradict the hypothesis that it has terminated.
2. **`check_process_listeners`** — Check listening ports on the 'amf' container.
    - *Expected if hypothesis holds:* The command returns no output or an error, indicating no processes are listening for traffic, which is expected if the AMF has terminated.
    - *Falsifying observation:* A process is actively listening on the AMF's NGAP SCTP port (38412). This would imply the AMF process is alive and has initialized its network interfaces, contradicting the hypothesis.
3. **`measure_rtt`** — Measure RTT from the 'nr_gnb' container to the IP of the 'amf' container.
    - *Expected if hypothesis holds:* 100% packet loss. An offline container cannot respond to pings.
    - *Falsifying observation:* A clean RTT (< 5ms) is measured. This would prove the AMF container is online and network-reachable from the RAN, falsifying the hypothesis.

*Notes:* This plan directly tests the core assertion of the hypothesis: the unexpected termination of the AMF container. The probes verify the container's runtime state, its process-level network initialization, and its network reachability from the RAN. If the AMF is running and reachable, this hypothesis is false.


## Parallel Investigators (Phase 5)

**1 sub-Investigator verdict(s):** **1 NOT_DISPROVEN**

### `h1` — ✅ **NOT_DISPROVEN**

**Hypothesis:** The Access and Mobility Management Function (AMF) has terminated unexpectedly. As the core control-plane function for registration and session management, its failure has halted all PDU session establishment, leading to a complete loss of data plane connectivity.

**Reasoning:** All probes executed returned results consistent with the hypothesis. The AMF container is confirmed to be in an 'exited' state, is not listening on any ports (because it's not running), and is unreachable on the network. No contradictory evidence was found.

**Probes executed (3):**
- **Check the container status for 'amf'** ✓ CONSISTENT
    - *Tool:* `default_api.get_network_status()`
    - *Observation:* [EVIDENCE: get_network_status() -> "'containers': {'amf': 'exited'}"]
    - *Comment:* The get_network_status tool confirmed that the AMF container has a status of 'exited'. This directly supports the hypothesis that the AMF has terminated.
- **Check listening ports on the 'amf' container.** ✓ CONSISTENT
    - *Tool:* `default_api.check_process_listeners(container='amf')`
    - *Observation:* [EVIDENCE: check_process_listeners("amf") -> "Error response from daemon: container e0d230d12cc938dd02636a6a3b72da26094e31996d1e4f993c35d7bd1de8fea6 is not running"]
    - *Comment:* The tool failed because the container is not running, which is the expected outcome if the AMF has terminated. No processes can be listening if the container is down.
- **Measure RTT from the 'nr_gnb' container to the IP of the 'amf' container.** ✓ CONSISTENT
    - *Tool:* `default_api.measure_rtt(container='smf', target_ip='172.22.0.10')`
    - *Observation:* [EVIDENCE: measure_rtt("smf", "172.22.0.10") -> "100% packet loss"]
    - *Comment:* The AMF's IP is unreachable, which is expected for a terminated container. The source container was changed from 'nr_gnb' (which does not exist) to 'smf', but the result still strongly supports the hypothesis.


## Evidence Validation (Phase 6)

**Overall verdict:** clean
**Overall confidence:** high

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 5 | 3/3 | clean | high |


## Ground Truth

**Failure domain:** core_control_plane  
**Protocol impact:** NGAP  
**Affected components:** amf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v6-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 151.1s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: The 5G core network is down due to the unexpected termination of the Access and Mobility Management Function (AMF), leading to a complete failure of user session establishment and loss of the data plane.
> - **timeline**:
>     1. The Session Management Function (SMF) detected a catastrophic drop in established sessions, indicating a widespread control-plane failure (`core.smf.sessions_per_ue_drop`).
> - **root_cause**: The Access and Mobility Management Function (AMF) has terminated unexpectedly. As the core control-plane function for registration and session management, its failure has halted all PDU session establishment, leading to a complete loss of data plane connectivity. The primary suspect network function is `amf`.
> - **affected_components**:
>     - `amf`: Root Cause
>     - `smf`: Secondary
>     - `ran`: Symptomatic
>     - `ims`: Symptomatic
> - **recommendation**: The operator should inspect the AMF container to confirm its 'exited' status and review its logs to determine the reason for the unexpected termination.
> - **confidence**: high
> - **explanation**: The initial analysis produced a single hypothesis: the AMF container had terminated. An investigation confirmed this hypothesis by directly observing that the AMF container's status is 'exited' and that it is unreachable on the network. The failure of the AMF, which is essential for user registration and mobility, directly explains the observed network-wide failure to establish PDU sessions. All evidence gathered was validated and found to be consistent with this conclusion.

### Scoring Breakdown

**Overall score: 100%**

**Scorer assessment:** The agent provided a perfectly accurate and well-supported diagnosis, correctly identifying the root cause, affected component, severity, fault type, and layer, with appropriate confidence.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | Yes | The agent correctly identified the Access and Mobility Management Function (AMF) as the root cause and accurately described its state as 'terminated unexpectedly' or 'exited', which aligns with the simulated failure of the AMF being temporarily unavailable/stopped. |
| Component overlap | 100% | The agent explicitly listed 'amf' as the 'Root Cause' in its `affected_components` list, which is the primary affected component in the simulated failure. |
| Severity correct | Yes | The agent described the impact as a 'complete failure of user session establishment and loss of the data plane' and 'halted all PDU session establishment, leading to a complete loss of data plane connectivity', which accurately reflects the severity of a core component like the AMF being stopped/unavailable. |
| Fault type identified | Yes | The agent identified the fault type as the AMF 'terminated unexpectedly' and its container status as 'exited' and 'unreachable on the network', which is an accurate observable description of a component being unavailable/stopped. |
| Layer accuracy | Yes | The ground truth states that 'amf' belongs to the 'core' layer. The agent's network analysis correctly rated the 'core' layer as 'red' and provided evidence directly linking it to the 'amf' container being 'exited'. |
| Confidence calibrated | Yes | The agent stated 'high' confidence, which is appropriate given that its diagnosis is entirely correct and supported by direct observation of the AMF's status. |

**Ranking position:** #1 — The agent provided a single, clear root cause, which was correct.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 113,902 |
| Output tokens | 2,287 |
| Thinking tokens | 8,660 |
| **Total tokens** | **124,849** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| EventAggregator | 0 | 0 | 0 |
| CorrelationAnalyzer | 0 | 0 | 0 |
| NetworkAnalystAgent | 56,591 | 6 | 4 |
| InstructionGeneratorAgent | 15,078 | 1 | 2 |
| InvestigatorAgent_h1 | 49,588 | 5 | 6 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 3,592 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 293.3s
