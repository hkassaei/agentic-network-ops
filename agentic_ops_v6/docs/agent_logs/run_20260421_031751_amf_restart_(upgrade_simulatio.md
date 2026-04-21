# Episode Report: AMF Restart (Upgrade Simulation)

**Agent:** v6  
**Episode ID:** ep_20260421_031330_amf_restart_(upgrade_simulatio  
**Date:** 2026-04-21T03:13:31.884199+00:00  
**Duration:** 259.0s  

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
- **Nodes with significant deltas:** 5
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

- **`icscf.ims_icscf:lir_avg_response_time`** (I-CSCF LIR response time) — current **66.00 ms** vs learned baseline **48.47 ms** (MEDIUM, shift)
    - **What it measures:** Call-routing-specific Cx leg. If LIR is healthy but UAR is slow,
registration path has a specific issue separate from call routing.
    - **Shift means:** HSS slow to respond to LIR; affects call setup.
    - **Healthy typical range:** 30–100 ms

- **`scscf.ims_auth:mar_avg_response_time`** (S-CSCF MAR response time) — current **117.00 ms** vs learned baseline **91.62 ms** (MEDIUM, shift)
    - **What it measures:** S-CSCF side of the Cx interface. If MAR latency spikes alongside
I-CSCF UAR/LIR spikes, it's HSS-wide; if only MAR spikes, it's
S-CSCF ↔ HSS specific.
    - **Shift means:** HSS slow responding to MAR.
    - **Healthy typical range:** 50–150 ms

- **`icscf.cdp:average_response_time`** (I-CSCF Diameter average response time) — current **67.00 ms** vs learned baseline **51.50 ms** (MEDIUM, shift)
    - **What it measures:** Responsiveness of the Cx path and HSS processing speed. A spike
without timeouts = pure latency; a spike WITH timeout_ratio rising
= approaching timeout ceiling (HSS overload or partial partition).
    - **Shift means:** HSS slow, network latency to HSS, or HSS overload.
    - **Healthy typical range:** 30–100 ms

- **`normalized.pcscf.dialogs_per_ue`** (Active SIP dialogs per registered UE at P-CSCF) — current **2.00 count** vs learned baseline **0.57 count** (MEDIUM, spike)
    - **What it measures:** How many calls per user are currently in progress at the P-CSCF.
Going to zero from a non-zero baseline means calls have ended
(normal) OR call setup is failing system-wide (degradation).
Together with rcv_requests_* it discriminates the two.
    - **Spike means:** Calls ending or setup failing.
    - **Healthy typical range:** 0–1 count
    - **Healthy invariant:** Per-UE — scale-independent. 0 at rest, ~1 per active VoNR call.

- **`icscf.ims_icscf:uar_avg_response_time`** (I-CSCF UAR response time) — current **67.00 ms** vs learned baseline **51.94 ms** (MEDIUM, shift)
    - **What it measures:** Specifically the UAR leg of the Cx interface. Spikes here without
LIR spikes are unusual — either UAR-handler issue at HSS or
specific network path to that code path.
    - **Shift means:** UAR-specific HSS slowness.
    - **Healthy typical range:** 30–100 ms

- **`scscf.ims_registrar_scscf:sar_avg_response_time`** (S-CSCF SAR response time) — current **116.00 ms** vs learned baseline **100.81 ms** (MEDIUM, shift)
    - **What it measures:** Second S-CSCF ↔ HSS leg. Together with MAR, these are the S-CSCF-side
Diameter contribution to register_time.
    - **Shift means:** HSS slow for SAR. Less common than MAR.
    - **Healthy typical range:** 50–150 ms


## Event Aggregation (Phase 1)

**1 events fired during the observation window:**

- `core.smf.sessions_per_ue_drop` (source: `core.smf.sessions_per_ue`, nf: `smf`, t=1776741339.5)  [current_value=0.0, prior_stable_value=2.0, delta_percent=-100.0]

## Correlation Analysis (Phase 2)

1 events fired but no composite hypothesis emerged. The events may be from independent faults or lack registered correlation hints in the KB.

## Network Analysis (Phase 3)

**Summary:** The root cause of the outage is that the AMF has exited, preventing any UEs from connecting to the 5G core and establishing data sessions.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟡 YELLOW | One of the critical network function containers (AMF) has terminated. The rest of the infrastructure appears to be running. |
| **ran** | 🟡 YELLOW | The RAN components may be functional, but they have no path into the core network due to the AMF failure. UEs cannot attach. |
| **core** | 🔴 RED | The Access and Mobility Management Function (AMF) is down. This is a critical failure that prevents any UE from registering with the network. No PDU sessions can be established, which means the data and voice planes are completely unavailable for new users. |
| **ims** | 🟡 YELLOW | Multiple IMS components are reporting increased response times from the HSS on the Cx interface. This indicates a performance degradation in the IMS control plane, affecting registrations and call setup for any already-registered users. This is secondary to the complete core outage. |

**INFRASTRUCTURE evidence:**
- amf container has exited

**RAN evidence:**
- N2 link to AMF is INACTIVE

**CORE evidence:**
- amf container has exited
- normalized.smf.sessions_per_ue is 0
- normalized.smf.bearers_per_ue is 0
- GTP-U traffic is 0 in both directions

**IMS evidence:**
- icscf.ims_icscf:lir_avg_response_time shift
- scscf.ims_auth:mar_avg_response_time shift
- icscf.cdp:average_response_time shift

**Ranked hypotheses:**

- **`h1`** (fit=0.95, nf=amf, specificity=specific):
    - **Statement:** The AMF container has exited, causing a complete failure of the 5G core's access and mobility functions. This prevents UEs from registering, which in turn means no PDU sessions can be created, halting all user plane traffic.
    - **Supporting events:** `core.smf.sessions_per_ue_drop`
    - **Falsification probes:**
        - Confirm AMF container status; if it is actually running, this hypothesis is false.
        - Check AMF logs for the reason it exited.
- **`h2`** (fit=0.40, nf=pyhss, specificity=moderate):
    - **Statement:** The HSS is responding slowly to Diameter requests from the I-CSCF and S-CSCF over the Cx interface. This is causing increased latency for IMS registration and call routing procedures.
    - **Falsification probes:**
        - Measure RTT from icscf to pyhss; if latency is normal (<10ms), this hypothesis is false.
        - Check HSS container logs for signs of overload, errors, or long processing times.


## Falsification Plans (Phase 4)

**2 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `amf`)

**Hypothesis:** The AMF container has exited, causing a complete failure of the 5G core's access and mobility functions. This prevents UEs from registering, which in turn means no PDU sessions can be created, halting all user plane traffic.

**Probes (3):**
1. **`get_network_status`** — container='amf'
    - *Expected if hypothesis holds:* The status of the 'amf' container will be 'exited' or 'down'.
    - *Falsifying observation:* The status of the 'amf' container is 'running', indicating it is operational.
2. **`read_container_logs`** — container='amf', grep='exit|error|terminate', since='1h'
    - *Expected if hypothesis holds:* Logs from the 'amf' container will contain messages indicating an unexpected exit, termination, or critical errors leading to its shutdown.
    - *Falsifying observation:* The 'amf' container logs show no recent 'exit', 'error', or 'terminate' messages, or indicate a clean shutdown, contradicting an abrupt failure.
3. **`get_nf_metrics`** — nf='nr_gnb'
    - *Expected if hypothesis holds:* The metric 'nr_gnb.n2_setup_attempts_total' (or similar N2 setup attempt counter) will be non-zero and potentially high, while 'nr_gnb.n2_setup_success_total' will be zero or very low, indicating gNBs are attempting to connect to a non-responsive AMF.
    - *Falsifying observation:* The metric 'nr_gnb.n2_setup_attempts_total' is zero (indicating no attempts from RAN to connect to core), or 'nr_gnb.n2_setup_success_total' is high (indicating successful N2 setups, meaning AMF is functional).

*Notes:* These probes aim to directly confirm the AMF's operational status and inspect its logs for a reason for exit. The gNB N2 setup metric serves as an 'activity vs. drops' discriminator, confirming that RAN is indeed trying to connect to the core, which should fail if the AMF is down.

### Plan for `h2` (target: `pyhss`)

**Hypothesis:** The HSS is responding slowly to Diameter requests from the I-CSCF and S-CSCF over the Cx interface. This is causing increased latency for IMS registration and call routing procedures.

**Probes (4):**
1. **`measure_rtt`** — from='icscf', to_ip='pyhss_ip'
    - *Expected if hypothesis holds:* The Round Trip Time (RTT) from 'icscf' to 'pyhss_ip' will be consistently high (>10ms) or show significant packet loss, confirming slow communication over the Cx interface.
    - *Falsifying observation:* The RTT from 'icscf' to 'pyhss_ip' is low (<5ms) with no packet loss, indicating healthy network connectivity and responsiveness from PyHSS's perspective.
2. **`measure_rtt`** — from='pyhss', to_ip='icscf_ip'
    - *Expected if hypothesis holds:* The RTT from 'pyhss' to 'icscf_ip' will also be high (>10ms) or show significant packet loss, suggesting a general network issue or a problem internal to PyHSS affecting both directions.
    - *Falsifying observation:* The RTT from 'pyhss' to 'icscf_ip' is low (<5ms) with no packet loss. If the RTT from 'icscf' to 'pyhss' was high, this result would point towards a specific issue with the forward path from I-CSCF or I-CSCF's ability to send traffic, rather than PyHSS's general responsiveness or the network path itself.
3. **`read_container_logs`** — container='pyhss', grep='slow|latency|error|timeout', since='1h'
    - *Expected if hypothesis holds:* Logs from the 'pyhss' container will contain entries indicating slow Diameter request processing, timeouts, or errors related to resource exhaustion or performance degradation.
    - *Falsifying observation:* The 'pyhss' container logs show no recent messages related to slow processing, timeouts, or errors, suggesting normal operation and responsiveness.
4. **`get_nf_metrics`** — nf='pyhss'
    - *Expected if hypothesis holds:* The metric 'pyhss.diameter_requests_received_total' (or similar counter for incoming Diameter requests) will be non-zero and possibly increasing, indicating that PyHSS is actively receiving requests but potentially processing them slowly.
    - *Falsifying observation:* The metric 'pyhss.diameter_requests_received_total' is zero or very low, indicating that PyHSS is not receiving traffic from I-CSCF/S-CSCF. This would suggest an upstream problem preventing requests from reaching the HSS, rather than the HSS itself being slow.

*Notes:* This plan employs RTT measurements for direct latency checks in both directions (triangulation) to pinpoint network versus host-specific issues. Log analysis will provide evidence of internal HSS performance problems. An 'activity vs. drops' probe checks if the HSS is even receiving requests, ruling out upstream starvation.


## Parallel Investigators (Phase 5)

**2 sub-Investigator verdict(s):** **1 NOT_DISPROVEN**, **1 DISPROVEN**

### `h1` — ✅ **NOT_DISPROVEN**

**Hypothesis:** The AMF container has exited, causing a complete failure of the 5G core's access and mobility functions. This prevents UEs from registering, which in turn means no PDU sessions can be created, halting all user plane traffic.

**Reasoning:** The investigation confirmed the central claim of the hypothesis: the AMF container has indeed exited. While a search for corresponding error logs was inconclusive (no output), and RAN-side metrics were unavailable, no evidence directly contradicted the hypothesis. The primary evidence of the exited container is strong enough for the hypothesis to survive falsification.

**Probes executed (3):**
- **Confirm AMF container status; if it is actually running, this hypothesis is false.** ✓ CONSISTENT
    - *Tool:* `print(default_api.get_network_status())`
    - *Observation:* [EVIDENCE: get_network_status() -> "'amf': 'exited'"]
    - *Comment:* The tool output confirms that the AMF container is in an 'exited' state, which is consistent with the hypothesis.
- **Check AMF logs for the reason it exited.** ~ AMBIGUOUS
    - *Tool:* `print(default_api.read_container_logs(container = 'amf', grep = 'exit|error|terminate', since_seconds = 3600))`
    - *Observation:* [EVIDENCE: read_container_logs('amf', 'exit|error|terminate', 3600) -> "(no log output)"]
    - *Comment:* The hypothesis expected to find error or termination messages in the AMF logs. The tool returned no output, which is ambiguous. It does not confirm the hypothesis, but it also does not contradict it, as the container could have exited without logging.
- **The metric 'nr_gnb.n2_setup_attempts_total' (or similar N2 setup attempt counter) will be non-zero and potentially high, while 'nr_gnb.n2_setup_success_total' will be zero or very low, indicating gNBs are attempting to connect to a non-responsive AMF.** ~ AMBIGUOUS
    - *Tool:* `print(default_api.get_nf_metrics())`
    - *Observation:* [EVIDENCE: get_nf_metrics() -> "(output does not contain metrics for nr_gnb)"]
    - *Comment:* The expected metrics for the gNB (nr_gnb.n2_setup_attempts_total, nr_gnb.n2_setup_success_total) were not found in the tool's output. Without these metrics, it's impossible to determine if the RAN is attempting to connect to the AMF and failing, as the hypothesis suggests. The probe is therefore inconclusive.

### `h2` — ❌ **DISPROVEN**

**Hypothesis:** The HSS is responding slowly to Diameter requests from the I-CSCF and S-CSCF over the Cx interface. This is causing increased latency for IMS registration and call routing procedures.

**Reasoning:** The probe measuring network latency from the I-CSCF to the HSS showed a very fast and healthy connection, directly contradicting the hypothesis of a slow interface. Furthermore, an examination of the HSS container logs for the past hour revealed no errors, timeouts, or latency-related messages. These results falsify the claim that the HSS is the source of the slowness.

**Probes executed (4):**
- **The Round Trip Time (RTT) from 'icscf' to 'pyhss_ip' will be consistently high (>10ms) or show significant packet loss, confirming slow communication over the Cx interface.** ✓ CONSISTENT
    - *Tool:* `read_env_config()`
    - *Observation:* [EVIDENCE: read_env_config() -> "'icscf_ip': '172.22.0.19', 'pyhss_ip': '172.22.0.18'"]
    - *Comment:* Used to get the IP addresses for the RTT measurement.
- **The Round Trip Time (RTT) from 'icscf' to 'pyhss_ip' will be consistently high (>10ms) or show significant packet loss, confirming slow communication over the Cx interface.** ✗ CONTRADICTS
    - *Tool:* `measure_rtt("icscf", "172.22.0.18")`
    - *Observation:* [EVIDENCE: measure_rtt("icscf", "172.22.0.18") -> "rtt min/avg/max/mdev = 0.083/0.089/0.097/0.005 ms"]
    - *Comment:* The RTT from I-CSCF to PyHSS is extremely low (< 0.1ms) with 0% packet loss. This directly contradicts the hypothesis that the interface is slow.
- **The RTT from 'pyhss' to 'icscf_ip' will also be high (>10ms) or show significant packet loss, suggesting a general network issue or a problem internal to PyHSS affecting both directions.** ~ AMBIGUOUS
    - *Tool:* `measure_rtt("pyhss", "172.22.0.19")`
    - *Observation:* [EVIDENCE: measure_rtt("pyhss", "172.22.0.19") -> "Ping failed from pyhss to 172.22.0.19: OCI runtime exec failed: exec failed: unable to start container process: exec: \"ping\": executable file not found in $PATH: unknown"]
    - *Comment:* The probe failed because the 'ping' tool is not installed in the pyhss container. This provides no information about the reverse network path.
- **Logs from the 'pyhss' container will contain entries indicating slow Diameter request processing, timeouts, or errors related to resource exhaustion or performance degradation.** ✗ CONTRADICTS
    - *Tool:* `read_container_logs("pyhss", "slow|latency|error|timeout", 3600)`
    - *Observation:* [EVIDENCE: read_container_logs("pyhss", "slow|latency|error|timeout", 3600) -> "(no log output)"]
    - *Comment:* The absence of any logs related to slowness, errors, or timeouts in the last hour strongly suggests that PyHSS is operating normally and not experiencing performance issues.

**Alternative suspects:** icscf, scscf


## Evidence Validation (Phase 6)

**Overall verdict:** clean
**Overall confidence:** high

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 3 | 3/3 | clean | high |
| `InvestigatorAgent_h2` | 4 | 4/4 | clean | high |


## Ground Truth

**Failure domain:** core_control_plane  
**Protocol impact:** NGAP  
**Affected components:** amf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v6-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 116.3s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: The root cause of the outage is that the Access and Mobility Management Function (AMF) container has exited, causing a complete 5G core failure that prevents any user equipment from connecting to the network.
> - **timeline**:
>     1. The AMF container terminated for an unknown reason.
>     2. As a direct result, gNodeBs in the RAN could no longer establish N2 connections to the core network.
>     3. The SMF detected a drop in PDU sessions per UE (`core.smf.sessions_per_ue_drop`) because no new UEs could register to create sessions.
>     4. Separately, IMS components reported degraded performance, but this was investigated and found not to be the primary fault.
> - **root_cause**: The AMF container has exited. The `primary_suspect_nf` is **amf**.
> - **affected_components**:
>     - `amf`: Root Cause
>     - `smf`: Symptomatic
>     - `ran`: Symptomatic
>     - `pyhss`: Symptomatic
>     - `icscf`: Symptomatic
>     - `scscf`: Symptomatic
> - **recommendation**: The operator should verify the status of the `amf` container and inspect the underlying container orchestration platform's logs (e.g., `docker ps -a`, `kubectl get pods`) to determine why the container terminated. Further investigation should focus on the AMF's application logs leading up to the exit event.
> - **confidence**: high
> - **explanation**: The investigation confirmed with high confidence that the AMF has exited. This was validated by checking the network function status, which showed the component in an 'exited' state. This single failure explains the complete loss of service, as the AMF is essential for UE registration and access to the 5G core. A secondary hypothesis, suggesting slow HSS performance was causing IMS issues, was tested and definitively disproven; network latency to the HSS was found to be excellent (<1ms) and HSS logs showed no signs of distress. Therefore, the AMF failure is the conclusive root cause of the outage.

### Scoring Breakdown

**Overall score: 100%**

**Scorer assessment:** The agent provided an excellent and highly accurate diagnosis, correctly identifying the AMF as the root cause, its impact, and its location within the network architecture with high confidence.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | Yes | The agent correctly identified the AMF as the root cause, stating 'The AMF container has exited' and 'primary_suspect_nf is amf', which accurately reflects the simulated failure of the AMF being temporarily unavailable/stopped. |
| Component overlap | 100% | The agent correctly identified 'amf' as the root cause and primary suspect. It also listed relevant symptomatic components, which is appropriate. |
| Severity correct | Yes | The agent described the impact as a 'complete 5G core failure' and 'complete loss of service', which aligns with the simulated temporary unavailability of a critical component like the AMF. |
| Fault type identified | Yes | The agent identified the fault type as a component being 'exited' and 'down', which is equivalent to 'component unreachable/not responding' from a network observability perspective. |
| Layer accuracy | Yes | The agent correctly rated the 'core' layer as 'red' and provided 'amf container has exited' as evidence, aligning with the ground truth that AMF belongs to the core layer. While it also mentioned 'infrastructure' as yellow due to the container exit, the primary network function failure was correctly attributed to the core layer. |
| Confidence calibrated | Yes | The agent stated 'high' confidence, which is appropriate given the accuracy and detail of its diagnosis, including the successful falsification of a secondary hypothesis. |

**Ranking position:** #1 — The correct cause (AMF container exited) was clearly identified as the primary root cause and top candidate.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 91,407 |
| Output tokens | 4,496 |
| Thinking tokens | 10,015 |
| **Total tokens** | **105,918** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| EventAggregator | 0 | 0 | 0 |
| CorrelationAnalyzer | 0 | 0 | 0 |
| NetworkAnalystAgent | 38,597 | 3 | 4 |
| InstructionGeneratorAgent | 6,634 | 0 | 1 |
| InvestigatorAgent_h1 | 28,000 | 3 | 4 |
| InvestigatorAgent_h2 | 27,590 | 4 | 4 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 5,097 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 259.0s
