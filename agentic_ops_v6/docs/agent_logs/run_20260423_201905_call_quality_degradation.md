# Episode Report: Call Quality Degradation

**Agent:** v6  
**Episode ID:** ep_20260423_201321_call_quality_degradation  
**Date:** 2026-04-23T20:13:22.986188+00:00  
**Duration:** 341.8s  

---

## Scenario

**Category:** network  
**Blast radius:** single_nf  
**Description:** Inject 30% packet loss on RTPEngine — the media relay for VoNR voice calls. RTP packets are dropped after RTPEngine receives them, degrading voice quality (MOS drop, jitter increase, audible artifacts). SIP signaling and 5G core are completely unaffected because they don't traverse RTPEngine. Tests whether the agent can diagnose a pure media-path fault without IMS signaling noise.

## Faults Injected

- **network_loss** on `rtpengine` — {'loss_pct': 30}

## Baseline (Pre-Fault)

Stack phase before injection: **ready**
All containers running at baseline.

## Fault Propagation Verification

**Verdict:** ✅ `confirmed`

- **Wait:** 0s
- **Actual elapsed:** 0.0s
- **Nodes with significant deltas:** 5
- **Nodes with any drift:** 6

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

## Anomaly Screening (Phase 0)

No anomalies detected by the statistical screener.

## Event Aggregation (Phase 1)

No events fired during this episode. Either no metric KB triggers matched, or the episode encountered no meaningful state transitions.

## Correlation Analysis (Phase 2)

No events fired — correlation engine had nothing to work with.

## Network Analysis (Phase 3)

**Summary:** The investigation points to a dual fault in the IMS core, with strong evidence of HSS unresponsiveness to the I-CSCF and a simultaneous connectivity issue between the P-CSCF and PCF.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | All containers are running and network links appear to be active. |
| **ran** | 🟢 GREEN | The RAN appears healthy, with 2 UEs connected to the AMF. |
| **core** | 🟡 YELLOW | Core signaling shows signs of distress, particularly with P-CSCF being unable to connect to PCF. |
| **ims** | 🔴 RED | The IMS layer is critical, with multiple timeouts at the I-CSCF pointing to a failure in HSS communication, preventing registrations. |

**CORE evidence:**
- pcscf:httpclient:connfail = 219.0

**IMS evidence:**
- icscf.cdp:timeout = 3.0
- icscf.ims_icscf:lir_timeouts = 2.0
- icscf.ims_icscf:uar_timeouts = 1.0

**Ranked hypotheses:**

- **`h1`** (fit=0.80, nf=pyhss, specificity=specific):
    - **Statement:** The HSS is not responding to Diameter requests from the I-CSCF, causing timeouts for user authentication (UAR) and location lookup (LIR). This is the likely cause of IMS registration failures.
    - **Supporting events:** `icscf.cdp:timeout`, `icscf.ims_icscf:uar_timeouts`, `icscf.ims_icscf:lir_timeouts`
    - **Falsification probes:**
        - Measure RTT from 'icscf' to 'pyhss' to check for network latency or packet loss.
        - Check 'pyhss' logs for incoming Diameter requests from 'icscf' and for any processing errors.
- **`h2`** (fit=0.70, nf=pcf, specificity=specific):
    - **Statement:** The P-CSCF is failing to connect to the PCF over its Rx interface (HTTP-based). This is evidenced by a high number of connection failures, which would prevent QoS policy negotiation for IMS sessions.
    - **Supporting events:** `pcscf:httpclient:connfail`
    - **Falsification probes:**
        - Measure RTT from 'pcscf' to 'pcf' to rule out a network partition.
        - Check 'pcf' logs for incoming HTTP requests from 'pcscf'.
- **`h3`** (fit=0.30, nf=upf, specificity=moderate):
    - **Statement:** The UPF may be dropping a significant amount of user plane traffic, as suggested by the large discrepancy between inbound and outbound GTP packet counters.
    - **Falsification probes:**
        - Invoke `get_dp_quality_gauges()` to get a real-time measurement of packet loss and throughput on the data plane.


## Falsification Plans (Phase 4)

**3 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `pyhss`)

**Hypothesis:** The HSS is not responding to Diameter requests from the I-CSCF, causing timeouts for user authentication (UAR) and location lookup (LIR). This is the likely cause of IMS registration failures.

**Probes (3):**
1. **`measure_rtt`** — from 'icscf' to 'pyhss'
    - *Expected if hypothesis holds:* High RTT or >0% packet loss, indicating a network partition or HSS unreachability.
    - *Falsifying observation:* Clean RTT (<5ms) and 0% packet loss. This would indicate the network path is healthy and the issue is likely at the application layer.
2. **`measure_rtt`** — Triangulation probe: from 'pcscf' to 'pyhss'
    - *Expected if hypothesis holds:* High RTT or >0% packet loss. If HSS is the root cause, it should be unreachable from other NFs as well.
    - *Falsifying observation:* Clean RTT (<5ms) from a different source. This would isolate the connectivity problem to the I-CSCF or its specific link, not the HSS itself.
3. **`check_process_listeners`** — container='pyhss'
    - *Expected if hypothesis holds:* The pyHSS process is not listening on the Diameter port (TCP/3868), indicating an application failure.
    - *Falsifying observation:* The process is actively listening on the Diameter port. This proves the HSS application is running and capable of accepting connections.

*Notes:* This plan tests for both network-level and application-level failures to isolate why HSS might be unresponsive. It uses a triangulation probe to distinguish between a faulty HSS and a faulty network path specific to the I-CSCF.

### Plan for `h2` (target: `pcf`)

**Hypothesis:** The P-CSCF is failing to connect to the PCF over its Rx interface (HTTP-based). This is evidenced by a high number of connection failures, which would prevent QoS policy negotiation for IMS sessions.

**Probes (3):**
1. **`measure_rtt`** — from 'pcscf' to 'pcf'
    - *Expected if hypothesis holds:* High RTT or >0% packet loss, indicating a network partition is causing the HTTP connection failures.
    - *Falsifying observation:* Clean RTT (<5ms) and 0% packet loss. This suggests a healthy network path, pointing the blame to an application-level issue (e.g., PCF's webserver is down).
2. **`measure_rtt`** — Triangulation probe: from 'smf' to 'pcf'
    - *Expected if hypothesis holds:* High RTT or >0% packet loss. If the PCF itself is unreachable, other NFs that connect to it (like the SMF) should also see failures.
    - *Falsifying observation:* Clean RTT (<5ms) from the SMF to the PCF. This would isolate the problem to the P-CSCF or its link, falsifying the hypothesis that PCF is the primary suspect.
3. **`check_process_listeners`** — container='pcf'
    - *Expected if hypothesis holds:* The PCF process is not listening on its HTTP port for the Rx interface.
    - *Falsifying observation:* The PCF process is actively listening on its Rx port, proving the application is ready to accept connections.

*Notes:* This plan follows the same structure as for h1, using network probes with triangulation and an application liveness check to determine if the PCF is truly the source of the connection failures seen by the P-CSCF.

### Plan for `h3` (target: `upf`)

**Hypothesis:** The UPF may be dropping a significant amount of user plane traffic, as suggested by the large discrepancy between inbound and outbound GTP packet counters.

**Probes (3):**
1. **`get_dp_quality_gauges`** — window_seconds=60
    - *Expected if hypothesis holds:* A non-zero `packet_loss_rate` value for UPF-transiting flows.
    - *Falsifying observation:* A `packet_loss_rate` of 0. This would directly contradict the hypothesis that the UPF is dropping packets.
2. **`get_nf_metrics`** — Filter for UPF container resource metrics (CPU, memory)
    - *Expected if hypothesis holds:* High CPU or memory usage for the 'upf' container, suggesting resource exhaustion as a cause for packet drops.
    - *Falsifying observation:* Normal CPU and memory utilization. This would indicate the UPF is not under resource pressure, making random drops less likely.
3. **`get_nf_metrics`** — Filter for UPF-specific internal drop counters (e.g., related to BESS pipeline)
    - *Expected if hypothesis holds:* Non-zero values for internal UPF packet drop counters, confirming that the UPF is internally accounting for dropped packets.
    - *Falsifying observation:* All internal drop counters are zero. This, combined with zero packet loss from the quality gauges, would strongly falsify the hypothesis.

*Notes:* This plan focuses on the data plane. It uses a direct measurement of packet loss, checks for common causes like resource exhaustion, and looks for corroborating internal metrics within the UPF to confirm or deny the packet drop hypothesis.


## Parallel Investigators (Phase 5)

**3 sub-Investigator verdict(s):** **2 DISPROVEN**, **1 INCONCLUSIVE**

### `h1` — ❌ **DISPROVEN**

**Hypothesis:** The HSS is not responding to Diameter requests from the I-CSCF, causing timeouts for user authentication (UAR) and location lookup (LIR). This is the likely cause of IMS registration failures.

**Reasoning:** The hypothesis that the HSS is unresponsive is contradicted by multiple probes. Network-level probes show a healthy, low-latency connection between the I-CSCF and the HSS, ruling out a network partition. Furthermore, metrics from the HSS itself confirm the application is running and responsive. The timeouts observed at the I-CSCF are not due to an unreachable or inactive HSS.

**Probes executed (4):**
- **Measure RTT from 'icscf' to 'pyhss' to check for network latency or packet loss.** ✗ CONTRADICTS
    - *Tool:* `default_api.measure_rtt(container='icscf', target_ip='172.22.0.18')`
    - *Observation:* [EVIDENCE: measure_rtt("icscf", "172.22.0.18") -> "3 packets transmitted, 3 received, 0% packet loss, time 2051ms\nrtt min/avg/max/mdev = 0.071/0.093/0.125/0.023 ms"]
    - *Comment:* The RTT is excellent (<1ms) and there is 0% packet loss. This contradicts the expectation of high latency or packet loss for an unresponsive component, falsifying a network partition as the cause.
- **Triangulation probe: Measure RTT from 'pcscf' to 'pyhss'.** ✗ CONTRADICTS
    - *Tool:* `default_api.measure_rtt(container='pcscf', target_ip='172.22.0.18')`
    - *Observation:* [EVIDENCE: measure_rtt("pcscf", "172.22.0.18") -> "3 packets transmitted, 3 received, 0% packet loss, time 2020ms\nrtt min/avg/max/mdev = 0.061/0.420/1.133/0.503 ms"]
    - *Comment:* The triangulation probe also shows a clean network path from a different source (P-CSCF) to the HSS. This confirms the HSS is reachable on the network and the issue is not specific to the I-CSCF's link.
- **Check if pyHSS process is listening on the Diameter port (TCP/3868).** ~ AMBIGUOUS
    - *Tool:* `default_api.check_process_listeners(container='pyhss')`
    - *Observation:* [EVIDENCE: check_process_listeners("pyhss") -> "Neither ss nor netstat available in pyhss. Output: OCI runtime exec failed: exec failed: unable to start container process: exec: \"netstat\": executable file not found in $PATH: unknown"]
    - *Comment:* The tool to check listening ports was not available in the container, so this probe was inconclusive. However, a subsequent probe using get_nf_metrics confirmed the application process is alive.
- **Check if the pyHSS application is alive by fetching its metrics.** ✗ CONTRADICTS
    - *Tool:* `default_api.get_nf_metrics()`
    - *Observation:* [EVIDENCE: get_nf_metrics() -> "PYHSS [2 subs] (via api):\n  ims_subscribers = 2  [counter]"]
    - *Comment:* The HSS is successfully reporting metrics, specifically 'ims_subscribers'. This proves the application is running and able to respond to API requests, contradicting the hypothesis that it is unresponsive.

**Alternative suspects:** icscf, pyhss

### `h2` — ❌ **DISPROVEN**

**Hypothesis:** The P-CSCF is failing to connect to the PCF over its Rx interface (HTTP-based). This is evidenced by a high number of connection failures, which would prevent QoS policy negotiation for IMS sessions.

**Reasoning:** The hypothesis is disproven by strong evidence from network and application-level probes. RTT checks from both the P-CSCF and SMF to the PCF show a healthy network path with no packet loss. Furthermore, the PCF process is actively listening for connections. This indicates the connection failures reported by the P-CSCF are not due to an issue with the PCF or the underlying network, but rather with the P-CSCF itself.

**Probes executed (3):**
- **from 'pcscf' to 'pcf'** ✗ CONTRADICTS
    - *Tool:* `measure_rtt("pcscf", "172.22.0.27")`
    - *Observation:* [EVIDENCE: measure_rtt("pcscf", "172.22.0.27") -> "3 packets transmitted, 3 received, 0% packet loss, time 2045ms\nrtt min/avg/max/mdev = 0.055/0.076/0.096/0.016 ms"]
    - *Comment:* The RTT is clean (<1ms) and there is 0% packet loss. This contradicts the expectation of a network partition causing connection failures and points to a healthy network path.
- **Triangulation probe: from 'smf' to 'pcf'** ✗ CONTRADICTS
    - *Tool:* `measure_rtt("smf", "172.22.0.27")`
    - *Observation:* [EVIDENCE: measure_rtt("smf", "172.22.0.27") -> "3 packets transmitted, 3 received, 0% packet loss, time 2052ms\nrtt min/avg/max/mdev = 0.053/0.078/0.098/0.018 ms"]
    - *Comment:* The RTT from another network function (SMF) to the PCF is also clean. This triangulates the issue, confirming the PCF is reachable and isolating the problem's source away from the PCF.
- **container='pcf'** ✗ CONTRADICTS
    - *Tool:* `check_process_listeners("pcf")`
    - *Observation:* [EVIDENCE: check_process_listeners("pcf") -> "tcp   LISTEN 0      5        172.22.0.27:7777       0.0.0.0:*    users:((\"open5gs-pcfd\",pid=8,fd=12))\ntcp   LISTEN 0      4096     172.22.0.27:9091       0.0.0.0:*    users:((\"open5gs-pcfd\",pid=8,fd=10))"]
    - *Comment:* The PCF process (open5gs-pcfd) is actively listening on its service ports (7777 and 9091). This proves the application is ready to accept connections, contradicting the hypothesis that the PCF is unavailable.

**Alternative suspects:** pcscf

### `h3` — ❓ **INCONCLUSIVE**

**Hypothesis:** The UPF may be dropping a significant amount of user plane traffic, as suggested by the large discrepancy between inbound and outbound GTP packet counters.

**Reasoning:** Sub-agent crashed: 
On how to mitigate this issue, please refer to:

https://google.github.io/adk-docs/agents/models/google-gemini/#error-code-429-resource_exhausted


429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'Resource exhausted. Please try again later. Please refer to https://cloud.google.com/vertex-ai/generative-ai/docs/error-code-429 for more details.', 'status': 'RESOURCE_EXHAUSTED'}}


## Evidence Validation (Phase 6)

**Overall verdict:** severe
**Overall confidence:** none

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 6 | 4/4 | clean | high |
| `InvestigatorAgent_h2` | 4 | 3/3 | clean | high |
| `InvestigatorAgent_h3` | 0 | 0/0 | severe | none |
|  |  |  |  | *ZERO tool calls — all citations fabricated* |


## Ground Truth

**Failure domain:** ims_media  
**Protocol impact:** RTP  
**Affected components:** rtpengine  
**Severity:** degraded

## Agent Diagnosis

**Model:** v6-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 208.7s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: A dual fault is indicated, with the I-CSCF failing to process responses from a healthy HSS and the P-CSCF failing to connect to a healthy PCF, leading to IMS registration failures.
> - **timeline**:
>     1. The I-CSCF begins reporting timeouts for Diameter User-Authentication-Requests (UAR) and Location-Info-Requests (LIR) sent to the HSS.
>     2. The I-CSCF's Diameter peer connection to the HSS times out.
>     3. The P-CSCF reports a high number of connection failures when attempting to contact the PCF over the Rx interface.
> - **root_cause**: The initial hypotheses were disproven. The investigation points towards a software or configuration fault within the `icscf` and `pcscf` network functions, as they are failing to communicate with target systems that have been verified as healthy and reachable.
> - **affected_components**:
>     - `icscf`: Root Cause
>     - `pcscf`: Root Cause
>     - `pyhss`: Symptomatic
>     - `pcf`: Symptomatic
> - **recommendation**: Further investigation should focus on the `icscf` and `pcscf` containers. Verify the internal logs of the I-CSCF for errors in its Diameter client stack. Concurrently, inspect the P-CSCF logs for specific errors related to its HTTP client configuration or state that would explain the connection failures to the PCF.
> - **confidence**: low
> - **explanation**: The initial hypotheses pointing to an unresponsive HSS and an unreachable PCF were both decisively disproven. Network probes confirmed that both the HSS (`pyhss`) and PCF are reachable with low latency and are listening for connections, ruling them out as the source of the failure. This shifts suspicion to the client components that reported the original errors: the I-CSCF and the P-CSCF. The timeouts and connection failures likely originate from software or configuration faults within these two network functions. Confidence in this assessment is capped at **low** due to a severe finding from the Evidence Validator, which reported that one of the sub-investigative agents fabricated its findings.

### Scoring Breakdown

**Overall score: 15%**

**Scorer assessment:** The agent completely missed the actual failure mode (RTPEngine packet loss) and instead focused on unrelated IMS signaling issues. However, its low confidence and correct identification of the IMS layer as problematic were positive aspects.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | No | The simulated failure was 30% packet loss on RTPEngine, leading to call quality degradation. The agent diagnosed a software or configuration fault within the I-CSCF and P-CSCF, leading to IMS registration failures. This is a completely different failure mode and set of affected components. |
| Component overlap | 0% | The primary affected component in the simulated failure was 'rtpengine'. The agent's diagnosis lists 'icscf' and 'pcscf' as root causes, and 'pyhss' and 'pcf' as symptomatic. 'rtpengine' is not mentioned at all. |
| Severity correct | No | The simulated failure was a degradation (30% packet loss) affecting call quality. The agent's diagnosis describes 'IMS registration failures' and 'failing to process responses'/'failing to connect', which implies a functional outage or severe disruption of signaling, not a media path degradation. |
| Fault type identified | No | The simulated failure was 'packet loss', which is a network degradation. The agent's diagnosis points to 'software or configuration fault' and 'connection failures'/'timeouts' related to signaling, not packet loss on the media plane. |
| Layer accuracy | Yes | The ground truth affected component 'rtpengine' belongs to the 'ims' layer. The agent's network analysis correctly rated the 'ims' layer as 'red', even though its reasoning for this rating was based on incorrect components (I-CSCF timeouts) within that layer. |
| Confidence calibrated | Yes | The agent's diagnosis was entirely incorrect regarding the root cause, affected components, severity, and fault type. Given this, its stated 'low' confidence is appropriate and well-calibrated. |

**Ranking:** The correct root cause (packet loss on RTPEngine) was not identified or ranked by the agent.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 197,540 |
| Output tokens | 4,917 |
| Thinking tokens | 14,389 |
| **Total tokens** | **216,846** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| EventAggregator | 0 | 0 | 0 |
| CorrelationAnalyzer | 0 | 0 | 0 |
| NetworkAnalystAgent | 60,009 | 5 | 6 |
| InstructionGeneratorAgent | 30,812 | 2 | 3 |
| InvestigatorAgent_h1 | 75,705 | 6 | 7 |
| InvestigatorAgent_h2 | 44,533 | 4 | 5 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 5,787 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 341.8s
