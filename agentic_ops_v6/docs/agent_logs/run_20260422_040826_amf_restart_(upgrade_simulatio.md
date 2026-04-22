# Episode Report: AMF Restart (Upgrade Simulation)

**Agent:** v6  
**Episode ID:** ep_20260422_040310_amf_restart_(upgrade_simulatio  
**Date:** 2026-04-22T04:03:12.046755+00:00  
**Duration:** 313.8s  

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

**ANOMALY DETECTED.** Overall anomaly score: 1.00 (threshold: 0.70, trained on 211 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

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

- **`scscf.ims_auth:mar_avg_response_time`** (S-CSCF MAR response time) — current **121.00 ms** vs learned baseline **91.62 ms** (MEDIUM, shift)
    - **What it measures:** S-CSCF side of the Cx interface. If MAR latency spikes alongside
I-CSCF UAR/LIR spikes, it's HSS-wide; if only MAR spikes, it's
S-CSCF ↔ HSS specific.
    - **Shift means:** HSS slow responding to MAR.
    - **Healthy typical range:** 50–150 ms

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

- **`icscf.cdp:average_response_time`** (I-CSCF Diameter average response time) — current **63.00 ms** vs learned baseline **51.50 ms** (MEDIUM, shift)
    - **What it measures:** Responsiveness of the Cx path and HSS processing speed. A spike
without timeouts = pure latency; a spike WITH timeout_ratio rising
= approaching timeout ceiling (HSS overload or partial partition).
    - **Shift means:** HSS slow, network latency to HSS, or HSS overload.
    - **Healthy typical range:** 30–100 ms

- **`scscf.ims_registrar_scscf:sar_avg_response_time`** (S-CSCF SAR response time) — current **114.00 ms** vs learned baseline **100.81 ms** (MEDIUM, shift)
    - **What it measures:** Second S-CSCF ↔ HSS leg. Together with MAR, these are the S-CSCF-side
Diameter contribution to register_time.
    - **Shift means:** HSS slow for SAR. Less common than MAR.
    - **Healthy typical range:** 50–150 ms

- **`normalized.scscf.cdp_replies_per_ue`** — current **0.27** vs learned baseline **0.06** (MEDIUM, spike). *(No KB context available — interpret from the metric name.)*

- **`normalized.scscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at S-CSCF) — current **0.27 requests_per_second** vs learned baseline **0.06 requests_per_second** (MEDIUM, spike)
    - **What it measures:** Health of the I-CSCF → S-CSCF forwarding path. Drop to zero while
I-CSCF is receiving REGISTERs = S-CSCF-side issue (crashed, or
I-CSCF → S-CSCF path broken).
    - **Spike means:** I-CSCF not forwarding or S-CSCF not receiving.
    - **Healthy typical range:** 0–0.5 requests_per_second
    - **Healthy invariant:** Per-UE rate. Tracks icscf.register rate.

- **`normalized.pcscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at P-CSCF) — current **0.27 requests_per_second** vs learned baseline **0.06 requests_per_second** (MEDIUM, spike)
    - **What it measures:** How actively UEs are refreshing their IMS registrations with the
P-CSCF. REGISTERs arrive periodically (re-registration timer) plus
at attach. Sustained zero means UEs cannot reach P-CSCF OR the
UE-to-network SIP path is broken.
    - **Spike means:** Fewer REGISTERs than expected — UE connectivity or P-CSCF reachability issue.
    - **Healthy typical range:** 0–0.5 requests_per_second
    - **Healthy invariant:** Per-UE rate — same value at any deployment scale.


## Event Aggregation (Phase 1)

**1 events fired during the observation window:**

- `core.smf.sessions_per_ue_drop` (source: `core.smf.sessions_per_ue`, nf: `smf`, t=1776830719.6)  [current_value=0.0, prior_stable_value=2.0, delta_percent=-100.0]

## Correlation Analysis (Phase 2)

1 events fired but no composite hypothesis emerged. The events may be from independent faults or lack registered correlation hints in the KB.

## Network Analysis (Phase 3)

**Summary:** The AMF container has exited, causing a complete loss of 5G core services and a downstream IMS registration storm.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | No direct evidence of infrastructure-level issues like node failures or networking partitions, but the AMF container exit could have an infrastructure cause. |
| **ran** | 🟡 YELLOW | The RAN itself appears to be functional, but it cannot provide service without a working AMF. |
| **core** | 🔴 RED | The 5G core is non-functional due to the AMF failure, which is the root cause of the outage. |
| **ims** | 🟡 YELLOW | The IMS system is under duress, likely due to a registration storm from UEs that have lost their 5G core connectivity. This is a secondary effect of the AMF failure. |

**RAN evidence:**
- UEs are unable to connect to the core network due to the AMF failure.

**CORE evidence:**
- AMF container has exited.
- PDU sessions per UE dropped to 0.
- Active QoS bearers per UE dropped to 0.
- Uplink and downlink GTP data rates are 0.

**IMS evidence:**
- Spike in SIP REGISTER requests at P-CSCF and S-CSCF.
- Slightly increased HSS response times.

**Ranked hypotheses:**

- **`h1`** (fit=1.00, nf=amf, specificity=specific):
    - **Statement:** The AMF container has exited, leading to a complete failure of the 5G core control plane. UEs are unable to register with the network, which prevents the establishment of PDU sessions and results in a total loss of data plane traffic. The observed spike in IMS registration requests is a secondary effect, as UEs that have lost their core network connectivity repeatedly attempt to re-register.
    - **Supporting events:** `core.smf.sessions_per_ue_drop`
    - **Falsification probes:**
        - Check the AMF container logs for the reason it exited.
        - Restart the AMF container and observe if UE registration and PDU session establishment resume.
        - Check the health of the underlying host and the container runtime to rule out infrastructure issues.
- **`h2`** (fit=0.50, nf=smf, specificity=moderate):
    - **Statement:** The SMF is failing to establish PDU sessions for UEs, leading to a loss of data plane connectivity. This is indicated by the drop in `sessions_per_ue` and `bearers_per_ue`.
    - **Supporting events:** `core.smf.sessions_per_ue_drop`
    - **Falsification probes:**
        - Examine the SMF logs for errors related to PDU session establishment.
        - Verify the N4 interface between SMF and UPF is functioning correctly.
- **`h3`** (fit=0.20, nf=pyhss, specificity=moderate):
    - **Statement:** The HSS is experiencing high latency on the Cx interface, as evidenced by the increased Diameter response times at the I-CSCF and S-CSCF. This is causing IMS registration procedures to be delayed or to fail, leading to the observed registration storm.
    - **Falsification probes:**
        - Measure the RTT from the S-CSCF to the HSS to confirm the high latency.
        - Check the HSS logs and resource utilization (CPU, memory) to identify any performance bottlenecks.


## Falsification Plans (Phase 4)

**3 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `amf`)

**Hypothesis:** The AMF container has exited, leading to a complete failure of the 5G core control plane. UEs are unable to register with the network, which prevents the establishment of PDU sessions and results in a total loss of data plane traffic. The observed spike in IMS registration requests is a secondary effect, as UEs that have lost their core network connectivity repeatedly attempt to re-register.

**Probes (3):**
1. **`get_network_status`** — Check all containers
    - *Expected if hypothesis holds:* The 'amf' container will have a status of 'exited'.
    - *Falsifying observation:* The 'amf' container has a status of 'running'. This directly contradicts the primary assertion of the hypothesis.
2. **`get_network_topology`** — Check connectivity graph
    - *Expected if hypothesis holds:* The N2 link between 'nr_gnb' and 'amf' is INACTIVE, as the AMF is down and cannot maintain the SCTP association.
    - *Falsifying observation:* The N2 link between 'nr_gnb' and 'amf' is ACTIVE. This implies the AMF is running and connected to the RAN, falsifying the hypothesis.
3. **`get_nf_metrics`** — Check for SMF metrics related to the N11 interface (e.g., 'smf.n11.requests' or 'smf.n11.messages.rx').
    - *Expected if hypothesis holds:* The rate of incoming requests from the AMF to the SMF over the N11 interface is zero, as the AMF is not running to send them.
    - *Falsifying observation:* The SMF is receiving requests on its N11 interface from the AMF. This proves the AMF is alive and communicating, falsifying the hypothesis.

*Notes:* This plan directly tests the central claim of the hypothesis: that the AMF container has exited. Probes check the container's status directly, its connectivity to the RAN, and the effect of its absence on the downstream SMF.

### Plan for `h2` (target: `smf`)

**Hypothesis:** The SMF is failing to establish PDU sessions for UEs, leading to a loss of data plane connectivity. This is indicated by the drop in `sessions_per_ue` and `bearers_per_ue`.

**Probes (3):**
1. **`get_network_status`** — Check 'smf' container status
    - *Expected if hypothesis holds:* The 'smf' container has a status of 'running' (as the hypothesis is about malfunction, not a crash).
    - *Falsifying observation:* The 'smf' container has a status of 'exited'. This would falsify the hypothesis in favor of a container crash, not a functional failure.
2. **`get_nf_metrics`** — Check SMF for N4 interface errors, e.g. 'smf.n4.association.failures' or 'smf.pfcp.tx.errors'.
    - *Expected if hypothesis holds:* SMF metrics show an increasing number of errors related to PFCP/N4 session establishment when communicating with the UPF.
    - *Falsifying observation:* SMF metrics for the N4 interface show no errors. This suggests the SMF is either not attempting to create sessions or is succeeding at the transport level, making an N4-level SMF failure less likely.
3. **`check_process_listeners`** — container='upf'
    - *Expected if hypothesis holds:* The UPF process is listening on the standard PFCP port (UDP 8805). This would indicate the UPF is ready and the fault lies with the SMF's attempts to connect.
    - *Falsifying observation:* The UPF process is not listening on UDP port 8805. This would falsify the SMF-centric hypothesis, as the UPF is not available to accept N4 associations, making it the likely culprit.

*Notes:* This plan investigates the SMF's ability to perform its function. It first verifies the SMF is running, then checks for specific error metrics on its control interface to the data plane (N4), and finally verifies the data plane (UPF) is even ready to be controlled.

### Plan for `h3` (target: `pyhss`)

**Hypothesis:** The HSS is experiencing high latency on the Cx interface, as evidenced by the increased Diameter response times at the I-CSCF and S-CSCF. This is causing IMS registration procedures to be delayed or to fail, leading to the observed registration storm.

**Probes (3):**
1. **`measure_rtt`** — from='scscf', to_ip='pyhss_ip'
    - *Expected if hypothesis holds:* Round-trip time between the S-CSCF and the HSS is significantly elevated (e.g., >50ms) or shows packet loss.
    - *Falsifying observation:* A clean, low-latency RTT (< 5ms) between S-CSCF and HSS. This would contradict the core claim of high latency on the Cx interface at the network level.
2. **`measure_rtt`** — from='scscf', to_ip='pcscf_ip'
    - *Expected if hypothesis holds:* Round-trip time from the S-CSCF to another known-good target (like P-CSCF) is low (< 5ms). This helps isolate the latency to the HSS or its path.
    - *Falsifying observation:* Round-trip time from S-CSCF to P-CSCF is also elevated. This would suggest the problem originates at the S-CSCF or its host, not the HSS, thus falsifying the hypothesis.
3. **`get_nf_metrics`** — Check for pyhss application-level metrics like 'hss.db.query.latency' or 'hss.diameter.requests.processing_time'.
    - *Expected if hypothesis holds:* Internal HSS metrics indicate high processing latency (e.g., slow database queries or high request processing time), explaining the end-to-end latency.
    - *Falsifying observation:* Internal HSS performance metrics are all nominal. This would indicate the HSS application itself is healthy, suggesting the high RTT observed at the network layer is due to a network fabric issue, not an overloaded HSS application.

*Notes:* This plan uses triangulation to isolate the source of latency. It first measures the direct path latency (S-CSCF to HSS), then measures a baseline from the same source to a different target to rule out source-side issues, and finally checks the HSS's internal metrics to distinguish between network latency and application-level slowness.


## Parallel Investigators (Phase 5)

**3 sub-Investigator verdict(s):** **1 NOT_DISPROVEN**, **2 DISPROVEN**

### `h1` — ✅ **NOT_DISPROVEN**

**Hypothesis:** The AMF container has exited, leading to a complete failure of the 5G core control plane. UEs are unable to register with the network, which prevents the establishment of PDU sessions and results in a total loss of data plane traffic. The observed spike in IMS registration requests is a secondary effect, as UEs that have lost their core network connectivity repeatedly attempt to re-register.

**Reasoning:** The investigation confirmed the primary assertion of the hypothesis. The `get_network_status` tool showed that the AMF container has indeed exited. A subsequent check of SMF metrics showed no evidence of N11 interface activity from the AMF, which is the expected consequence of the AMF being down. No contradictory evidence was found.

**Probes executed (2):**
- **Check all containers** ✓ CONSISTENT
    - *Tool:* `print(default_api.get_network_status())`
    - *Observation:* [EVIDENCE: get_network_status() -> "{\n  \"phase\": \"down\", ... \"containers\": { ... \"amf\": \"exited\" ... }\n}"]
    - *Comment:* The probe directly confirms the central claim of the hypothesis: the AMF container has an 'exited' status.
- **Check for SMF metrics related to the N11 interface (e.g., 'smf.n11.requests' or 'smf.n11.messages.rx').** ✓ CONSISTENT
    - *Tool:* `print(default_api.get_nf_metrics())`
    - *Observation:* [EVIDENCE: get_nf_metrics() -> "SMF [4 PDU] (via prometheus):\n  bearers_active = 8.0  [gauge]\n  fivegs_smffunction_sm_sessionnbr = 4.0  [gauge]\n  pfcp_sessions_active = 4.0  [gauge]\n  ues_active = 2.0  [gauge]"]
    - *Comment:* The metrics for the SMF do not show any incoming requests on the N11 interface from the AMF. The absence of these metrics is consistent with the hypothesis that the AMF is down and not sending any traffic.

### `h2` — ❌ **DISPROVEN**

**Hypothesis:** The SMF is failing to establish PDU sessions for UEs, leading to a loss of data plane connectivity. This is indicated by the drop in `sessions_per_ue` and `bearers_per_ue`.

**Reasoning:** The evidence contradicts the hypothesis that the SMF is the source of the failure. Probes indicate the SMF is running and its data plane counterpart, the UPF, is listening correctly on the N4 interface. Crucially, there are no N4/PFCP error metrics from the SMF, which would be expected if it were actively failing to create sessions. This suggests the SMF is not receiving any PDU session establishment requests in the first place, likely due to an upstream failure.

**Probes executed (3):**
- **Check 'smf' container status** ✓ CONSISTENT
    - *Tool:* `print(default_api.get_network_status())`
    - *Observation:* [EVIDENCE: get_network_status() -> "'smf': 'running'"]
    - *Comment:* The SMF container is running as expected, so this is not a container crash scenario. The hypothesis of a functional failure is still possible.
- **Check SMF for N4 interface errors, e.g. 'smf.n4.association.failures' or 'smf.pfcp.tx.errors'.** ✗ CONTRADICTS
    - *Tool:* `print(default_api.get_nf_metrics())`
    - *Observation:* [EVIDENCE: get_nf_metrics() -> "SMF [4 PDU] (via prometheus):\n  bearers_active = 8.0  [gauge]\n  fivegs_smffunction_sm_sessionnbr = 4.0  [gauge]\n  pfcp_sessions_active = 4.0  [gauge]\n  ues_active = 2.0  [gauge]"]
    - *Comment:* The metrics show no N4/PFCP errors. If the SMF were failing to establish sessions, error counters for its interface to the UPF would be elevated. Their absence indicates the SMF is not the component failing.
- **container='upf'** ✓ CONSISTENT
    - *Tool:* `print(default_api.check_process_listeners(container='upf'))`
    - *Observation:* [EVIDENCE: check_process_listeners(container='upf') -> "udp   UNCONN 0      0         172.22.0.8:8805       0.0.0.0:*    users:((\"open5gs-upfd\",pid=8,fd=7))"]
    - *Comment:* The UPF is listening on the PFCP port (8805/udp), so it is ready for N4 connections from the SMF. This rules out the UPF being unavailable as a reason for SMF failures and further isolates the problem as being upstream of the SMF.

**Alternative suspects:** amf

### `h3` — ❌ **DISPROVEN**

**Hypothesis:** The HSS is experiencing high latency on the Cx interface, as evidenced by the increased Diameter response times at the I-CSCF and S-CSCF. This is causing IMS registration procedures to be delayed or to fail, leading to the observed registration storm.

**Reasoning:** The hypothesis is disproven because its central claim of 'high latency on the Cx interface' is false at the network layer. Probes measuring round-trip time (RTT) from the S-CSCF to the HSS show latency is excellent (<1ms). While metrics do confirm high Diameter *application-layer* response times, the root cause is not network latency as the hypothesis implies. The issue lies within the application processing at either the HSS or the CSCFs.

**Probes executed (3):**
- **Measure RTT from S-CSCF to HSS to check for network latency.** ✗ CONTRADICTS
    - *Tool:* `default_api.measure_rtt(container='scscf', target_ip='172.22.0.18')`
    - *Observation:* [EVIDENCE: measure_rtt("scscf", "172.22.0.18") -> "rtt min/avg/max/mdev = 0.070/0.087/0.102/0.013 ms"]
    - *Comment:* The observed RTT of ~0.1ms is extremely low, directly contradicting the expectation of high latency (>50ms). This falsifies the idea that the Cx interface has high latency at the network level.
- **Measure RTT from S-CSCF to P-CSCF as a triangulation point to isolate the source of latency.** ✓ CONSISTENT
    - *Tool:* `default_api.measure_rtt(container='scscf', target_ip='172.22.0.21')`
    - *Observation:* [EVIDENCE: measure_rtt("scscf", "172.22.0.21") -> "rtt min/avg/max/mdev = 0.076/0.134/0.212/0.057 ms"]
    - *Comment:* The RTT to another NF (P-CSCF) is also very low. This confirms that the network connectivity from the S-CSCF is healthy in general, reinforcing the conclusion that the issue is not network-based.
- **Check for pyhss application-level metrics like 'hss.db.query.latency' or 'hss.diameter.requests.processing_time'.** ~ AMBIGUOUS
    - *Tool:* `default_api.get_nf_metrics()`
    - *Observation:* [EVIDENCE: get_nf_metrics() -> "ims_auth:mar_avg_response_time = 121.0 [gauge, ms]", "ims_icscf:uar_avg_response_time = 63.0 [gauge, ms]", "PYHSS [2 subs] (via api): ims_subscribers = 2"]
    - *Comment:* The metrics confirm the high Diameter response times at S-CSCF (121ms) and I-CSCF (63ms), which is consistent with the 'evidence' part of the hypothesis. However, no internal performance metrics for pyHSS were returned, making it impossible to confirm or deny if the HSS application itself is the source of the application-layer delay. The probe result is ambiguous regarding the culpability of the HSS application.

**Alternative suspects:** icscf, scscf


## Evidence Validation (Phase 6)

**Overall verdict:** clean
**Overall confidence:** high

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 2 | 2/2 | clean | high |
| `InvestigatorAgent_h2` | 3 | 3/3 | clean | high |
| `InvestigatorAgent_h3` | 4 | 3/3 | clean | high |


## Ground Truth

**Failure domain:** core_control_plane  
**Protocol impact:** NGAP  
**Affected components:** amf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v6-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 171.7s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: The AMF container has exited, which has caused a complete outage of the 5G core network control plane and a subsequent registration storm on the IMS system.
> - **timeline**:
>     1. A drop in PDU sessions per UE was observed at the SMF (`core.smf.sessions_per_ue_drop`), indicating UEs were losing their data plane connections.
>     2. Investigation confirmed the AMF container was in an `exited` state, making it unable to handle UE registration or mobility.
>     3. As a secondary effect, the IMS system began experiencing a high volume of registration requests from UEs that had lost 5G core connectivity and were attempting to re-register.
> - **root_cause**: The AMF container has exited, leading to a complete failure of the 5G core control plane. The primary suspect network function is `amf`.
> - **affected_components**:
>     - `amf`: Root Cause
>     - `smf`: Secondary (Unable to establish sessions as its upstream dependency, the AMF, is down)
>     - `ims`: Symptomatic (Experiencing a registration storm from UEs that lost core network connectivity)
> - **recommendation**: The operator should verify the AMF container's logs to determine the reason for its exit. Additionally, check the health of the underlying host and the container runtime to investigate for any infrastructure-level faults that may have caused the container to terminate.
> - **confidence**: high
> - **explanation**: The investigation confirmed that the AMF container has exited (hypothesis `h1`), which fully explains the loss of 5G core services. The lack of N11 interface traffic at the SMF is a direct consequence of the AMF being offline. Alternative hypotheses were disproven: an SMF-centric failure (`h2`) was ruled out because the SMF is running without errors, and an HSS latency issue (`h3`) was disproven by direct RTT measurements showing excellent network performance on the Cx interface. The evidence points conclusively to the AMF container exit as the root cause of the outage.

### Scoring Breakdown

**Overall score: 100%**

**Scorer assessment:** The agent provided an excellent and accurate diagnosis, correctly identifying the root cause, affected components, severity, and fault type with high confidence, and correctly attributing it to the core layer.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | Yes | The simulated failure was an AMF restart, meaning the AMF component was temporarily unavailable/stopped. The agent correctly identified the root cause as 'The AMF container has exited, leading to a complete failure of the 5G core control plane. The primary suspect network function is `amf`.' This is semantically equivalent to the simulated failure mode. |
| Component overlap | 100% | The primary affected component was 'amf'. The agent correctly listed 'amf' as 'Root Cause' in its `affected_components` list. It also correctly identified secondary and symptomatic components without penalization. |
| Severity correct | Yes | The simulated failure involved the AMF being stopped, which implies a complete outage. The agent's diagnosis states 'complete outage of the 5G core network control plane' and 'complete failure of the 5G core control plane', which accurately reflects the severity. |
| Fault type identified | Yes | The simulated failure was a component being temporarily unavailable/stopped. The agent identified this as 'AMF container has exited', leading to a 'complete outage' and 'complete failure', which correctly describes a component being down or unreachable. |
| Layer accuracy | Yes | The ground truth states 'amf' belongs to the 'core' layer. The agent's network analysis correctly rated the 'core' layer as 'red' with the evidence 'AMF container has exited.', accurately attributing the failure to its correct ontology layer. |
| Confidence calibrated | Yes | The agent stated 'high' confidence, and its diagnosis is accurate and well-supported across all dimensions, making the confidence level appropriate. |

**Ranking position:** #1 — The agent provided a single, clear root cause in its final diagnosis, which was correct.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 158,115 |
| Output tokens | 5,603 |
| Thinking tokens | 14,896 |
| **Total tokens** | **178,614** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| EventAggregator | 0 | 0 | 0 |
| CorrelationAnalyzer | 0 | 0 | 0 |
| NetworkAnalystAgent | 40,014 | 3 | 4 |
| InstructionGeneratorAgent | 17,939 | 3 | 2 |
| InvestigatorAgent_h1 | 27,857 | 2 | 3 |
| InvestigatorAgent_h2 | 39,005 | 3 | 4 |
| InvestigatorAgent_h3 | 48,086 | 4 | 5 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 5,713 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 313.8s
