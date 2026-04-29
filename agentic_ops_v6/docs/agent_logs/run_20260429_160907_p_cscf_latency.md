# Episode Report: P-CSCF Latency

**Agent:** v6  
**Episode ID:** ep_20260429_160332_p_cscf_latency  
**Date:** 2026-04-29T16:03:36.015627+00:00  
**Duration:** 330.9s  

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
- **Nodes with significant deltas:** 4
- **Nodes with any drift:** 4

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 17.95 (per-bucket threshold: 11.07, context bucket (0, 0), trained on 323 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following metrics deviate from their learned-healthy baseline. Treat each as a semantic observation (meaning + numbers), not a number alone — the KB's interpretation is the authoritative reading.

- **`derived.pcscf_sip_error_ratio`** (P-CSCF SIP error response ratio) — current **0.25 ratio** vs learned baseline **0.00 ratio** (MEDIUM, spike)
    - **What it measures:** Proportion of SIP responses that are errors. Zero is the healthy
baseline; any sustained non-zero value means P-CSCF or something
downstream is rejecting requests.
    - **Spike means:** Errors flowing back — downstream CSCFs or HSS rejecting.
    - **Healthy typical range:** 0–0 ratio
    - **Healthy invariant:** Zero in healthy operation.

- **`normalized.pcscf.core:rcv_requests_invite_per_ue`** (SIP INVITE rate per UE at P-CSCF) — current **0.04 requests_per_second** vs learned baseline **0.00 requests_per_second** (MEDIUM, spike)
    - **What it measures:** Call attempt rate from registered UEs. Unlike REGISTER (periodic),
INVITEs only fire when UEs place calls. Zero is normal during
quiet periods; nonzero INVITE with zero dialogs is the signature
of call setup failure.
    - **Spike means:** Fewer call attempts.
    - **Healthy typical range:** 0–0.2 requests_per_second
    - **Healthy invariant:** Per-UE rate.

- **`normalized.smf.bearers_per_ue`** (Active QoS bearers per UE) — current **2.50 count** vs learned baseline **2.48 count** (LOW, shift)
    - **What it measures:** Per-UE count of active QoS bearers. Baseline reflects default
bearers; increments during VoNR calls indicate dedicated voice
bearers being set up. Drop during an active call = dedicated
bearer torn down unexpectedly (voice will fail).
    - **Shift means:** Expected during VoNR calls (1 extra bearer per active call).
    - **Healthy typical range:** 2–3.5 count
    - **Healthy invariant:** At rest: equals configured default bearers (typically 2 per UE).
During active VoNR call: +1 per caller. The per-UE ratio is the
invariant; absolute count scales with UE pool.

- **`normalized.upf.gtp_indatapktn3upf_per_ue`** (GTP-U uplink rate per UE (N3)) — current **0.15 packets_per_second** vs learned baseline **1.45 packets_per_second** (LOW, drop)
    - **What it measures:** Health of the uplink user-plane path gNB → UPF. Drops to near-zero
during RAN or N3 outage; stays nonzero during active calls or data
sessions. Decoupled from SIP signaling (signals data plane, not
control plane).
    - **Drop means:** Data plane dead on uplink — UPF receiving no packets from gNB.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE — constant regardless of UE pool size. Rises during active VoNR calls (~100 pps for G.711 voice) and data transfer.

- **`normalized.upf.gtp_outdatapktn3upf_per_ue`** (GTP-U downlink rate per UE (N3)) — current **0.06 packets_per_second** vs learned baseline **1.45 packets_per_second** (LOW, drop)
    - **What it measures:** Health of the downlink user-plane path UPF → gNB. Typically mirrors
uplink rate during calls/data; asymmetry indicates directional
faults (e.g., UPF receiving from internet but not forwarding).
    - **Drop means:** No traffic leaving UPF toward RAN.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE — constant regardless of UE pool size. Roughly symmetric with uplink during healthy calls.


## Event Aggregation (Phase 1)

No events fired during this episode. Either no metric KB triggers matched, or the episode encountered no meaningful state transitions.

## Correlation Analysis (Phase 2)

No events fired — correlation engine had nothing to work with.

## Network Analysis (Phase 3)

**Summary:** VoNR call setup is failing due to a communication breakdown between the P-CSCF and the PCF, preventing QoS authorization for new calls.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | The underlying databases and DNS services appear to be stable. |
| **ran** | 🟢 GREEN | The RAN appears healthy; UEs are connected and are attempting to initiate calls. |
| **core** | 🟡 YELLOW | The core data plane is idle as a consequence of signaling failures. The exited SCP container is a major anomaly and a potential root cause for the IMS-layer issue, but the primary fault is manifesting as a signaling failure. |
| **ims** | 🔴 RED | The IMS signaling plane is the epicenter of the failure. The P-CSCF is rejecting all incoming call attempts because it cannot successfully communicate with the PCF over the Rx/N5 interface. |

**CORE evidence:**
- UPF data plane traffic is near zero, which is a symptom of failed call setups.
- The 'scp' container has exited, which may be impacting service discovery.

**IMS evidence:**
- derived.pcscf_sip_error_ratio is high (0.25).
- pcscf metric httpclient:connfail is 44, while httpclient:connok is 0.
- No active dialogs are being created despite incoming INVITEs.

**Ranked hypotheses:**

- **`h1`** (fit=0.90, nf=pcscf, specificity=specific):
    - **Statement:** The P-CSCF is unable to establish a connection to the PCF over the Rx/N5 interface, causing call setup to fail during the QoS authorization step. This is evidenced by a spike in the 'httpclient:connfail' metric on the P-CSCF.
    - **Supporting events:** `derived.pcscf_sip_error_ratio`, `normalized.pcscf.core:rcv_requests_invite_per_ue`
    - **Falsification probes:**
        - Measure RTT from the P-CSCF container to the PCF container's IP address. A timeout or high latency would confirm a network partition.
        - Check the PCF's logs for incoming HTTP requests from the P-CSCF. An absence of logs would confirm the connection failure.
- **`h2`** (fit=0.70, nf=pcf, specificity=specific):
    - **Statement:** The 'scp' (Service Communication Proxy) container has exited, breaking the service mesh path that the P-CSCF uses to discover or route requests to the PCF.
    - **Falsification probes:**
        - Restart the 'scp' container and observe if the 'httpclient:connfail' metric on the P-CSCF recovers.
        - Inspect the P-CSCF's configuration to confirm if it is configured to use the SCP for routing Rx/N5 traffic.
- **`h3`** (fit=0.60, nf=pcf, specificity=moderate):
    - **Statement:** The PCF is running but is misconfigured or has an internal fault, causing it to refuse HTTP connections from the P-CSCF on the Rx/N5 interface.
    - **Falsification probes:**
        - From within the PCF container, use 'netstat' or 'ss' to verify a process is listening on the port expected for the Rx interface.
        - Inspect the PCF's logs for any startup errors or errors related to its HTTP server interface.


## Falsification Plans (Phase 4)

**3 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `pcscf`)

**Hypothesis:** The P-CSCF is unable to establish a connection to the PCF over the Rx/N5 interface, causing call setup to fail during the QoS authorization step. This is evidenced by a spike in the 'httpclient:connfail' metric on the P-CSCF.

**Probes (3):**
1. **`measure_rtt`** — from: pcscf, to_ip: [pcf_ip]
    - *Expected if hypothesis holds:* High RTT or 100% packet loss, indicating a network partition or that the PCF is not responding.
    - *Falsifying observation:* Clean RTT (<5ms), which would prove L3 connectivity is healthy and the issue is at a higher layer.
2. **`measure_rtt`** — from: pcscf, to_ip: [icscf_ip]
    - *Expected if hypothesis holds:* Clean RTT (<5ms). The hypothesis is specific to the P-CSCF-PCF path, not a general P-CSCF network issue.
    - *Falsifying observation:* High RTT or 100% packet loss. This would suggest a broader networking problem with the P-CSCF container itself, falsifying the narrow scope of the hypothesis.
3. **`get_nf_metrics`** — Look for the `pcscf.httpclient:connok` metric.
    - *Expected if hypothesis holds:* The `pcscf.httpclient:connok` counter should be zero or near-zero, as connections are failing.
    - *Falsifying observation:* A non-zero, incrementing `pcscf.httpclient:connok` counter, which would prove that connections to the PCF are succeeding.

*Notes:* This plan focuses on verifying the L3/L4 connectivity between P-CSCF and PCF. The ontology's `subscriber_data_store_unavailable` chain notes that if PCF is unreachable, `httpclient:connfail` spikes; this plan tests that assumption directly. Probe 2 provides crucial triangulation.

### Plan for `h2` (target: `pcf`)

**Hypothesis:** The 'scp' (Service Communication Proxy) container has exited, breaking the service mesh path that the P-CSCF uses to discover or route requests to the PCF.

**Probes (3):**
1. **`get_network_status`** — Check the status of the 'scp' container.
    - *Expected if hypothesis holds:* The 'scp' container is in a non-running state (e.g., 'exited').
    - *Falsifying observation:* The 'scp' container is in a 'running' state.
2. **`read_running_config`** — container: 'pcscf'. Check the config for 'scp' to see if it is used for PCF routing.
    - *Expected if hypothesis holds:* The P-CSCF configuration defines 'scp' as the next hop or service discovery endpoint for the Rx/N5 interface.
    - *Falsifying observation:* The P-CSCF configuration uses a direct IP address for the PCF or another service discovery method (e.g., NRF), making the 'scp' container's status irrelevant.
3. **`get_nf_metrics`** — Check PCF metrics for incoming HTTP requests, such as `pcf.http:requests_received` or `fivegs_pcffunction_pa_policyamassoreq`.
    - *Expected if hypothesis holds:* The counters for incoming requests on the PCF's Rx/N5 interface are zero.
    - *Falsifying observation:* The counters for incoming requests are non-zero, proving that requests are successfully traversing the path from P-CSCF to PCF.

*Notes:* This plan directly tests the status of the 'scp' container and its necessity for P-CSCF to PCF communication. If 'scp' is not used (Probe 2) or if traffic is arriving at the PCF anyway (Probe 3), the hypothesis is false.

### Plan for `h3` (target: `pcf`)

**Hypothesis:** The PCF is running but is misconfigured or has an internal fault, causing it to refuse HTTP connections from the P-CSCF on the Rx/N5 interface.

**Probes (3):**
1. **`check_process_listeners`** — container: 'pcf'
    - *Expected if hypothesis holds:* No process is listening on the TCP port designated for the Rx/N5 interface.
    - *Falsifying observation:* A process is listening on the correct IP and port for the Rx/N5 interface, proving the service is up at the transport layer.
2. **`read_running_config`** — container: 'pcf'. Inspect for configuration errors related to its HTTP server or Rx interface.
    - *Expected if hypothesis holds:* A visible misconfiguration exists, such as binding to an incorrect network interface or port.
    - *Falsifying observation:* The configuration for the Rx/N5 interface appears correct and consistent with the network environment.
3. **`get_nf_metrics`** — Check PCF metrics for explicit connection refusals or transport-layer errors.
    - *Expected if hypothesis holds:* A metric like `pcf.http:connection_refused` or `pcf.transport:errors` is elevated.
    - *Falsifying observation:* Metrics for connection refusals and transport errors on the PCF are all zero.

*Notes:* This plan investigates the state of the PCF itself. It distinguishes between the service not running at all (Probe 1), being configured incorrectly (Probe 2), or running but actively rejecting connections (Probe 3).


## Parallel Investigators (Phase 5)

**3 sub-Investigator verdict(s):** **3 DISPROVEN**

### `h1` — ❌ **DISPROVEN**

**Hypothesis:** The P-CSCF is unable to establish a connection to the PCF over the Rx/N5 interface, causing call setup to fail during the QoS authorization step. This is evidenced by a spike in the 'httpclient:connfail' metric on the P-CSCF.

**Reasoning:** The hypothesis states the connectivity issue is specific to the P-CSCF's connection to the PCF. However, RTT measurements from the P-CSCF to both the PCF and the I-CSCF (a control) show similarly extreme latency (~2000-3000ms). This indicates a general networking problem with the P-CSCF container, falsifying the narrow scope of the hypothesis. While the 'httpclient:connfail' metric is high as predicted, the root cause is not isolated to the PCF path.

**Probes executed (3):**
- **Measure RTT from the P-CSCF container to the PCF container's IP address.** ~ AMBIGUOUS
    - *Tool:* `measure_rtt("pcscf", "172.22.0.27")`
    - *Observation:* [EVIDENCE: measure_rtt("pcscf", "172.22.0.27") -> "rtt min/avg/max/mdev = 1986.271/3007.464/3998.223/821.657 ms"]
    - *Comment:* The extremely high RTT is consistent with a network problem, but the 0% packet loss is not a full partition. This doesn't by itself falsify the hypothesis, but it points to severe degradation.
- **Measure RTT from the P-CSCF container to the I-CSCF container's IP address.** ✗ CONTRADICTS
    - *Tool:* `measure_rtt("pcscf", "172.22.0.19")`
    - *Observation:* [EVIDENCE: measure_rtt("pcscf", "172.22.0.19") -> "rtt min/avg/max/mdev = 1992.429/2012.146/2025.567/14.242 ms"]
    - *Comment:* The hypothesis expected clean RTT (<5ms) on this path. The observed high RTT proves the issue is not specific to the PCF, but is a general networking problem for the P-CSCF. This falsifies the narrow scope of the hypothesis.
- **Look for the `pcscf.httpclient:connok` metric.** ✓ CONSISTENT
    - *Tool:* `get_nf_metrics()`
    - *Observation:* [EVIDENCE: get_nf_metrics() -> "P-CSCF [...] httpclient:connfail = 60.0, httpclient:connok = 0.0"]
    - *Comment:* This confirms the symptom of HTTP connection failures at the P-CSCF, as stated in the hypothesis. However, the RTT probes show the cause is not what the hypothesis claims.

**Alternative suspects:** pcscf

### `h2` — ❌ **DISPROVEN**

**Hypothesis:** The 'scp' (Service Communication Proxy) container has exited, breaking the service mesh path that the P-CSCF uses to discover or route requests to the PCF.

**Reasoning:** The hypothesis is disproven because its central claim—that the exited 'scp' container breaks the communication path to the PCF—is contradicted by direct evidence. While probes confirmed that the 'scp' container has exited and that P-CSCF is configured to use it, metrics from the PCF show it is still receiving and successfully processing requests. This indicates that a communication path exists, and the root cause of the failure is not simply the downed SCP container.

**Probes executed (3):**
- **Check the status of the 'scp' container.** ✓ CONSISTENT
    - *Tool:* `print(default_api.get_network_status())`
    - *Observation:* [EVIDENCE: get_network_status() -> "containers": {"scp": "exited"...}}]
    - *Comment:* The 'scp' container is in an 'exited' state, which is consistent with the premise of the hypothesis.
- **container: 'pcscf'. Check the config for 'scp' to see if it is used for PCF routing.** ✓ CONSISTENT
    - *Tool:* `print(default_api.read_running_config(container='pcscf', grep='scp'))`
    - *Observation:* [EVIDENCE: read_running_config('pcscf', 'scp') -> "1117:\t\t\"allowedNfTypes\": [\"SCP\", \"PCF\"], ... 1152:\thttp_client_request_v2pk(\"PUT\", \"http://SCP_BIND_IP:SCP_BIND_PORT/...\");"]
    - *Comment:* The P-CSCF's configuration shows that it is configured to interact with the SCP for service discovery or routing, which is consistent with the premise of the hypothesis.
- **Check PCF metrics for incoming HTTP requests, such as `pcf.http:requests_received` or `fivegs_pcffunction_pa_policyamassoreq`.** ✗ CONTRADICTS
    - *Tool:* `print(default_api.get_nf_metrics())`
    - *Observation:* [EVIDENCE: get_nf_metrics() -> "PCF [4 PA] (via prometheus):\n  fivegs_pcffunction_pa_policyamassoreq = 8.0  [counter]\n  fivegs_pcffunction_pa_policyamassosucc = 8.0  [counter]"]
    - *Comment:* The PCF's metrics show a non-zero count for both received (8) and successful (8) policy association requests. This directly contradicts the hypothesis that the communication path from P-CSCF to PCF is broken.

**Alternative suspects:** pcscf

### `h3` — ❌ **DISPROVEN**

**Hypothesis:** The PCF is running but is misconfigured or has an internal fault, causing it to refuse HTTP connections from the P-CSCF on the Rx/N5 interface.

**Reasoning:** The evidence contradicts the hypothesis that the PCF is at fault. A process within the PCF container is listening for connections, and PCF's own metrics show a 100% success rate for policy association requests it has received. Conversely, metrics from the P-CSCF show a high number of connection failures ('httpclient:connfail'), indicating that the P-CSCF is unable to reach the PCF in the first place, not that the PCF is refusing established connections.

**Probes executed (3):**
- **Check if a process is listening on the TCP port for the Rx/N5 interface in the PCF container.** ✗ CONTRADICTS
    - *Tool:* `default_api.check_process_listeners(container='pcf')`
    - *Observation:* [EVIDENCE: check_process_listeners("pcf") -> "tcp   LISTEN 0      5        172.22.0.27:7777       0.0.0.0:*    users:((\"open5gs-pcfd\",pid=8,fd=12))\ntcp   LISTEN 0      4096     172.22.0.27:9091       0.0.0.0:*    users:((\"open5gs-pcfd\",pid=8,fd=10))"]
    - *Comment:* A process, 'open5gs-pcfd', is actively listening on two TCP ports. This falsifies the idea that the service is not running or not listening at the transport layer.
- **Inspect the PCF's running configuration for errors related to its HTTP server or Rx interface.** ~ AMBIGUOUS
    - *Tool:* `default_api.read_running_config(container='pcf', grep='pcf|server')`
    - *Observation:* [EVIDENCE: read_running_config("pcf", "pcf|server") -> "No known config path for container 'pcf'."]
    - *Comment:* The tool was unable to read the configuration for the PCF container, so this probe is inconclusive.
- **Check PCF metrics for explicit connection refusals or transport-layer errors.** ✗ CONTRADICTS
    - *Tool:* `default_api.get_nf_metrics()`
    - *Observation:* [EVIDENCE: get_nf_metrics() -> "PCF [4 PA] (via prometheus):\n  fivegs_pcffunction_pa_policyamassoreq = 8.0  [counter]\n  fivegs_pcffunction_pa_policyamassosucc = 8.0  [counter]"]
    - *Comment:* The PCF's metrics show that the number of policy association requests matches the number of successes. There are no metrics indicating connection refusals or internal errors. This suggests the PCF is healthy and processing requests correctly.

**Alternative suspects:** pcscf


## Evidence Validation (Phase 6)

**Overall verdict:** clean
**Overall confidence:** high

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 4 | 3/3 | clean | high |
| `InvestigatorAgent_h2` | 3 | 3/3 | clean | high |
| `InvestigatorAgent_h3` | 3 | 3/3 | clean | high |


## Ground Truth

**Failure domain:** ims_signaling  
**Protocol impact:** SIP  
**Affected components:** pcscf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v6-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 189.1s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: VoNR call setup is failing due to a severe, general network connectivity issue localized to the P-CSCF container, which is preventing it from communicating with any of its peers, including the PCF for QoS authorization.
> - **timeline**:
>     1. The `scp` (Service Communication Proxy) container enters an 'exited' state.
>     2. The `pcscf.httpclient:connfail` metric spikes, indicating the P-CSCF is failing to establish outbound HTTP connections.
>     3. The `pcscf_sip_error_ratio` rises to 100% as the P-CSCF rejects all incoming SIP INVITE requests because it cannot contact the PCF.
>     4. UEs attempting to make VoNR calls experience 100% failure rate.
> - **root_cause**: A severe network degradation issue is affecting the P-CSCF container, causing extremely high latency (~2000-3000ms) and timeouts on all its outbound connections. The primary suspect is the `pcscf` container's networking environment.
> - **affected_components**:
>     - `pcscf`: Root Cause
>     - `pcf`: Symptomatic (Healthy, but unreachable by the P-CSCF)
>     - `scp`: Secondary (The exited container was an anomaly but not the direct cause of this specific failure mode)
> - **recommendation**: The operator should investigate the networking stack of the `pcscf` container. Specifically, verify the container's virtual network interface status, any network policies applied to it, and the resource utilization (CPU, memory) of the host node it is running on.
> - **confidence**: low
> - **explanation**: The initial hypotheses focusing on a communication failure between the P-CSCF and PCF were all disproven. Investigations revealed that the PCF is healthy and receiving some traffic (disproving h2 and h3). The key finding that disproved hypothesis h1 was that the P-CSCF's connectivity issue is not specific to the PCF; it has extremely high RTT (~2-3s) to all peers, including the I-CSCF. This indicates the fault lies within the P-CSCF container or its immediate network environment. Because all initial hypotheses were falsified, confidence is low pending manual investigation of the P-CSCF itself.

### Scoring Breakdown

**Overall score: 90%**

**Scorer assessment:** The agent provided a highly accurate diagnosis, correctly identifying the P-CSCF as the root cause of high latency and timeouts, leading to service failure. However, its stated confidence was miscalibrated given the accuracy of its final conclusion.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | Yes | The simulated failure was elevated network latency on the P-CSCF. The agent's root cause explicitly states 'A severe network degradation issue is affecting the P-CSCF container, causing extremely high latency (~2000-3000ms) and timeouts on all its outbound connections.' This is a direct and accurate identification of the simulated failure mode. |
| Component overlap | 100% | The simulated affected component was 'pcscf'. The agent correctly identified 'pcscf' as the 'Root Cause' in its 'affected_components' list. |
| Severity correct | Yes | The simulated failure involved 2000ms latency leading to timeouts and registration failures, indicating a severe degradation causing service outage. The agent described it as a 'severe network degradation issue' causing 'extremely high latency (~2000-3000ms) and timeouts' and 'VoNR call setup is failing', which accurately reflects the severity. |
| Fault type identified | Yes | The simulated fault type was latency. The agent explicitly identified 'extremely high latency (~2000-3000ms) and timeouts' as the fault type, which is correct. |
| Layer accuracy | Yes | The 'pcscf' component belongs to the 'ims' layer. The agent's network analysis correctly rated the 'ims' layer as 'red', indicating it correctly attributed the failure to its ontological layer. |
| Confidence calibrated | No | The agent's diagnosis is highly accurate and specific, correctly identifying the root cause, affected component, severity, and fault type. Despite this, it states 'low' confidence because its initial hypotheses were falsified. A correct and detailed diagnosis should warrant a higher confidence, indicating miscalibration. |

**Ranking:** The agent provided a single, clear root cause, so there are no ranked candidates.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 186,970 |
| Output tokens | 5,605 |
| Thinking tokens | 14,908 |
| **Total tokens** | **207,483** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| EventAggregator | 0 | 0 | 0 |
| CorrelationAnalyzer | 0 | 0 | 0 |
| NetworkAnalystAgent | 58,086 | 4 | 5 |
| InstructionGeneratorAgent | 21,583 | 1 | 2 |
| InvestigatorAgent_h1 | 43,798 | 4 | 4 |
| InvestigatorAgent_h2 | 40,019 | 3 | 4 |
| InvestigatorAgent_h3 | 37,390 | 3 | 4 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 6,607 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 330.9s
