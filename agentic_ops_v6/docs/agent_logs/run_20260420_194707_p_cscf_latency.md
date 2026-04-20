# Episode Report: P-CSCF Latency

**Agent:** v6  
**Episode ID:** ep_20260420_194214_p_cscf_latency  
**Date:** 2026-04-20T19:42:16.213124+00:00  
**Duration:** 289.8s  

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
- **Nodes with significant deltas:** 2
- **Nodes with any drift:** 4

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

### Metrics Changes

| Node | Metric | Baseline | Current | Delta |
|------|--------|----------|---------|-------|
| icscf | core:rcv_requests_register | 126.0 | 162.0 | 36.0 |
| pcscf | script:register_time | 54947.0 | 140747.0 | 85800.0 |
| pcscf | sl:4xx_replies | 6.0 | 8.0 | 2.0 |
| pcscf | core:rcv_requests_invite | 18.0 | 24.0 | 6.0 |
| pcscf | core:rcv_requests_register | 98.0 | 146.0 | 48.0 |

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 0.93 (threshold: 0.70, trained on 211 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following specific metrics were flagged as the top contributors to the anomaly. These MUST be reflected in your layer ratings:

| Component | Metric | Current | Learned Normal | Severity |
|-----------|--------|---------|---------------|----------|
| derived | pcscf_sip_error_ratio | 0.50 | 0.00 | MEDIUM |
| derived | pcscf_avg_register_time_ms | 0.00 | 248.24 | HIGH |
| normalized | upf.gtp_outdatapktn3upf_per_ue | 0.06 | 3.34 | MEDIUM |
| normalized | upf.gtp_indatapktn3upf_per_ue | 0.20 | 3.42 | MEDIUM |
| normalized | pcscf.dialogs_per_ue | 0.00 | 0.57 | LOW |
| derived | upf_activity_during_calls | 1.00 | 0.47 | LOW |

## Event Aggregation (Phase 1)

No events fired during this episode. Either no metric KB triggers matched, or the episode encountered no meaningful state transitions.

## Correlation Analysis (Phase 2)

No events fired — correlation engine had nothing to work with.

## Network Analysis (Phase 3)

**Summary:** The network is experiencing a dual fault: a complete data plane blockage at the UPF and a simultaneous severe error condition within the P-CSCF, preventing successful IMS registrations and call setup.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | The underlying containers and network connections appear healthy. |
| **ran** | 🟢 GREEN | The RAN appears to be operating correctly, with UEs attached and sending data. |
| **core** | 🔴 RED | The UPF is effectively a black hole for user data, representing a critical data plane failure. |
| **ims** | 🔴 RED | The IMS registration process is failing at the P-CSCF, preventing users from accessing VoNR services. |

**CORE evidence:**
- UPF metrics show a massive discrepancy between inbound (9348) and outbound (294) GTP packets.
- Anomaly screener flagged 'upf.gtp_outdatapktn3upf_per_ue' and 'upf.gtp_indatapktn3upf_per_ue' with MEDIUM severity.

**IMS evidence:**
- P-CSCF metrics show a very high number of httpclient connection failures (11276).
- P-CSCF shows zero active dialogs and zero accepted registrations, despite receiving 146 REGISTER requests.
- Anomaly screener flagged 'pcscf_sip_error_ratio' as MEDIUM and 'pcscf_avg_register_time_ms' as HIGH.

**Ranked hypotheses:**

- **`h1`** (fit=0.90, nf=upf, specificity=specific):
    - **Statement:** The UPF is dropping almost all outbound user plane traffic. Data is arriving from the RAN over the N3 interface but is not being forwarded to the data network (N6).
    - **Falsification probes:**
        - Check the UPF's routing table for a valid default route.
        - Examine the UPF's firewall or packet processing rules for a misconfiguration that would drop N6 traffic.
        - Run a packet capture on the UPF's N6 interface to confirm the absence of outbound traffic.
- **`h2`** (fit=0.80, nf=pcscf, specificity=specific):
    - **Statement:** The P-CSCF is unable to establish outbound HTTP connections, causing failures in dependent services. This is evidenced by over 11,000 'httpclient:connfail' errors and prevents successful SIP dialog establishment.
    - **Falsification probes:**
        - Identify the destination service for the failing HTTP connections from the P-CSCF's configuration or logs.
        - From the P-CSCF container, attempt to manually connect to the target IP and port of the service to test connectivity.
        - Check PCF logs to see if it is receiving Rx requests from the P-CSCF.
- **`h3`** (fit=0.70, nf=pcscf, specificity=moderate):
    - **Statement:** There is a signaling disconnect between the P-CSCF and the downstream IMS components (I/S-CSCF). While the S-CSCF is successfully processing some registrations, the P-CSCF is not receiving or processing the final success (200 OK) responses, causing it to report zero successful registrations and drop dialogs.
    - **Falsification probes:**
        - Run a packet capture on the Mw interface between P-CSCF and I-CSCF to see if 200 OK responses for REGISTER are arriving at the P-CSCF.
        - Examine the P-CSCF logs for errors related to processing inbound SIP responses from the S-CSCF.


## Falsification Plans (Phase 4)

**3 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `upf`)

**Hypothesis:** The UPF is dropping almost all outbound user plane traffic. Data is arriving from the RAN over the N3 interface but is not being forwarded to the data network (N6).

**Probes (3):**
1. **`query_prometheus`** — Check UPF's N3 ingress traffic metrics.
    - *Expected if hypothesis holds:* Prometheus metric 'upf_rx_packets_n3_total' shows significant non-zero traffic on the N3 interface, confirming data is arriving at the UPF.
    - *Falsifying observation:* Prometheus metric 'upf_rx_packets_n3_total' is zero or near zero, suggesting upstream starvation rather than UPF dropping traffic.
2. **`query_prometheus`** — Check UPF's N6 egress traffic metrics.
    - *Expected if hypothesis holds:* Prometheus metric 'upf_tx_packets_n6_total' shows zero or near zero traffic on the N6 interface, consistent with no data being forwarded.
    - *Falsifying observation:* Prometheus metric 'upf_tx_packets_n6_total' shows significant non-zero traffic on the N6 interface, directly contradicting the hypothesis that data is not being forwarded.
3. **`measure_rtt`** — Measure RTT from 'upf' to a known external IP, e.g., 8.8.8.8. The investigator should try to connect to the UPF container and run the ping.
    - *Expected if hypothesis holds:* High packet loss (near 100%) or complete unreachability to the external IP, consistent with a blockage on the N6 interface.
    - *Falsifying observation:* Low RTT and 0% packet loss to the external IP, indicating basic N6 network connectivity is functional from the UPF.

*Notes:* Probes focus on confirming traffic ingress and egress at the UPF's N3/N6 interfaces, and direct network connectivity from UPF to an external target to triangulate N6 blockage.

### Plan for `h2` (target: `pcscf`)

**Hypothesis:** The P-CSCF is unable to establish outbound HTTP connections, causing failures in dependent services. This is evidenced by over 11,000 'httpclient:connfail' errors and prevents successful SIP dialog establishment.

**Probes (3):**
1. **`read_container_logs`** — Read P-CSCF logs for patterns indicating attempts to initiate outbound HTTP requests, e.g., 'Outbound HTTP request to'.
    - *Expected if hypothesis holds:* P-CSCF logs show recent attempts to initiate outbound HTTP connections, which are then failing.
    - *Falsifying observation:* No log entries for outbound HTTP requests, suggesting the P-CSCF isn't attempting these connections, so the failures are not from active attempts.
2. **`measure_rtt`** — Identify the target IP of failing HTTP connections from P-CSCF configuration or logs. Then, measure RTT from the P-CSCF container to that identified HTTP target IP.
    - *Expected if hypothesis holds:* High packet loss or complete unreachability to the target HTTP IP, confirming a network-level blockage for HTTP connections from P-CSCF.
    - *Falsifying observation:* Low RTT and 0% packet loss to the target HTTP IP, indicating underlying network connectivity is fine, pointing to an application-level issue at P-CSCF or the target.
3. **`read_container_logs`** — Check PCF logs for incoming Rx requests from the P-CSCF, e.g., 'Received Rx request from P-CSCF'.
    - *Expected if hypothesis holds:* PCF logs show no (or very few) incoming Rx requests from P-CSCF, consistent with P-CSCF's inability to establish outbound connections to dependent services like PCF.
    - *Falsifying observation:* PCF logs show a healthy stream of incoming Rx requests from the P-CSCF, implying the P-CSCF *can* communicate with at least this dependent service.

*Notes:* Probes confirm P-CSCF's HTTP activity, network connectivity to its HTTP targets, and cross-layer communication with a dependent service (PCF) to triangulate the source of connection failures.

### Plan for `h3` (target: `pcscf`)

**Hypothesis:** There is a signaling disconnect between the P-CSCF and the downstream IMS components (I/S-CSCF). While the S-CSCF is successfully processing some registrations, the P-CSCF is not receiving or processing the final success (200 OK) responses, causing it to report zero successful registrations and drop dialogs.

**Probes (3):**
1. **`read_container_logs`** — Read P-CSCF logs for outgoing SIP REGISTER messages, e.g., 'SIP REGISTER request sent to'.
    - *Expected if hypothesis holds:* P-CSCF logs show recent outgoing SIP REGISTER requests, confirming P-CSCF is initiating registration attempts upstream.
    - *Falsifying observation:* No outgoing SIP REGISTER requests in P-CSCF logs, suggesting P-CSCF isn't initiating registrations, thus it cannot be waiting for 200 OK responses for those requests.
2. **`read_container_logs`** — Read S-CSCF logs for outgoing SIP 200 OK responses for REGISTER messages, e.g., 'SIP/2.0 200 OK for REGISTER sent to'.
    - *Expected if hypothesis holds:* S-CSCF logs show successful sending of 200 OKs for REGISTER requests, confirming upstream processing and generation of responses.
    - *Falsifying observation:* S-CSCF logs show no (or very few) 200 OKs for REGISTER, contradicting the NA's statement that S-CSCF is successfully processing registrations.
3. **`read_container_logs`** — Read I-CSCF logs for forwarding SIP 200 OK responses towards the P-CSCF, e.g., 'SIP/2.0 200 OK sending to <P_CSCF_IP>'. The investigator needs to identify the P-CSCF's IP first.
    - *Expected if hypothesis holds:* I-CSCF logs show 200 OK messages being sent from I-CSCF towards the P-CSCF, indicating the response is being forwarded mid-path.
    - *Falsifying observation:* No 200 OK messages are sent from I-CSCF to P-CSCF, indicating a problem at or upstream of I-CSCF in forwarding the response, rather than P-CSCF not processing an received response.

*Notes:* Probes confirm P-CSCF's registration attempts, S-CSCF's successful response generation, and I-CSCF's forwarding of these responses, triangulating the point of failure for the 200 OK messages.


## Parallel Investigators (Phase 5)

**3 sub-Investigator verdict(s):** **3 DISPROVEN**

### `h1` — ❌ **DISPROVEN**

**Hypothesis:** The UPF is dropping almost all outbound user plane traffic. Data is arriving from the RAN over the N3 interface but is not being forwarded to the data network (N6).

**Reasoning:** The hypothesis is disproven because a direct test of the UPF's N6 data path shows it is functional. A ping from the UPF container to an external IP address (8.8.8.8) was successful with 0% packet loss, which directly contradicts the claim that data is not being forwarded to the data network (N6). While traffic metrics show a significant drop between ingress and egress, the successful connectivity test proves the forwarding path itself is not blocked.

**Probes executed (3):**
- **Check UPF's N3 ingress traffic metrics.** ~ AMBIGUOUS
    - *Tool:* `default_api.query_prometheus(query='rate(upf_rx_packets_n3_total[120s])')`
    - *Observation:* [EVIDENCE: query_prometheus("rate(upf_rx_packets_n3_total[120s])") -> "No results for query 'rate(upf_rx_packets_n3_total[120s])'. The metric may not exist or have no data."]
    - *Comment:* The Prometheus query returned no data. This is ambiguous as it could mean there is no traffic or the metric is not available. A substitute probe was used to get a clearer signal.
- **Check UPF's N6 egress traffic metrics. (Substituted for a more reliable tool)** ~ AMBIGUOUS
    - *Tool:* `default_api.get_dp_quality_gauges(window_seconds=120)`
    - *Observation:* [EVIDENCE: get_dp_quality_gauges(120) -> "UPF:\n    in  packets/sec: 0.3\n    out packets/sec: 0.1\n    in  throughput : 0.12 KB/s\n    out throughput : 0.05 KB/s"]
    - *Comment:* This probe shows that egress traffic (0.1 pps) is not zero, but is very low and represents a ~67% drop from ingress traffic. This neither fully confirms nor denies the hypothesis that 'almost all' traffic is dropped, making the result ambiguous on its own.
- **Measure RTT from 'upf' to a known external IP, e.g., 8.8.8.8. The investigator should try to connect to the UPF container and run the ping.** ✗ CONTRADICTS
    - *Tool:* `default_api.measure_rtt(container='upf', target_ip='8.8.8.8')`
    - *Observation:* [EVIDENCE: measure_rtt("upf", "8.8.8.8") -> "3 packets transmitted, 3 received, 0% packet loss, time 2003ms"]
    - *Comment:* This result directly falsifies the hypothesis. The successful ping with 0% packet loss proves that the UPF has a functional data path to the external data network (N6) and is capable of forwarding traffic, contrary to the hypothesis statement.

### `h2` — ❌ **DISPROVEN**

**Hypothesis:** The P-CSCF is unable to establish outbound HTTP connections, causing failures in dependent services. This is evidenced by over 11,000 'httpclient:connfail' errors and prevents successful SIP dialog establishment.

**Reasoning:** The hypothesis is disproven because the evidence points to an external factor, not a fault within the P-CSCF's HTTP client. Probes show that while connections are failing, the root cause is extreme network latency between the P-CSCF and its target (PCF), with RTTs over 3 seconds. The P-CSCF isn't logging outbound attempts, and the PCF isn't receiving any, which is consistent with connections timing out due to this severe latency rather than an intrinsic inability of the P-CSCF to initiate them.

**Probes executed (3):**
- **Read P-CSCF logs for patterns indicating attempts to initiate outbound HTTP requests, e.g., 'Outbound HTTP request to'.** ✗ CONTRADICTS
    - *Tool:* `read_container_logs("pcscf", grep="Outbound HTTP request to", since_seconds=300)`
    - *Observation:* [EVIDENCE: read_container_logs("pcscf", grep="Outbound HTTP request to", since_seconds=300) -> "(no log output)"]
    - *Comment:* The absence of logs for outbound HTTP attempts contradicts the hypothesis that the P-CSCF is actively trying and failing to establish connections. This suggests the application is not even reaching the stage of initiating the request, or is timing out before it can be logged.
- **Identify the target IP of failing HTTP connections from P-CSCF configuration or logs. Then, measure RTT from the P-CSCF container to that identified HTTP target IP.** ✗ CONTRADICTS
    - *Tool:* `measure_rtt("pcscf", "172.22.0.27")`
    - *Observation:* [EVIDENCE: measure_rtt("pcscf", "172.22.0.27") -> "3 packets transmitted, 3 received, 0% packet loss, time 2036ms\nrtt min/avg/max/mdev = 1971.414/3030.117/4089.953/864.890 ms, pipe 3"]
    - *Comment:* While the hypothesis expects a network-level blockage (packet loss), the observation shows 0% packet loss but an extremely high RTT (~3 seconds). This indicates the network path is open but severely degraded, or the target (PCF) is unresponsive. This points the blame away from the P-CSCF's client and towards the network path or the PCF itself.
- **Check PCF logs for incoming Rx requests from the P-CSCF, e.g., 'Received Rx request from P-CSCF'.** ✓ CONSISTENT
    - *Tool:* `read_container_logs("pcf", grep="Received Rx request from P-CSCF", since_seconds=300)`
    - *Observation:* [EVIDENCE: read_container_logs("pcf", grep="Received Rx request from P-CSCF", since_seconds=300) -> "(no log output)"]
    - *Comment:* This is consistent with the hypothesis that connections are failing. However, when combined with the other probes, it supports the alternative explanation that connections are timing out due to extreme latency before being processed by the PCF, rather than the P-CSCF being unable to send them.

**Alternative suspects:** pcf

### `h3` — ❌ **DISPROVEN**

**Hypothesis:** There is a signaling disconnect between the P-CSCF and the downstream IMS components (I/S-CSCF). While the S-CSCF is successfully processing some registrations, the P-CSCF is not receiving or processing the final success (200 OK) responses, causing it to report zero successful registrations and drop dialogs.

**Reasoning:** The hypothesis is disproven as there is no evidence of the P-CSCF sending initial REGISTER requests or the S-CSCF sending the corresponding 200 OK responses. Log searches on P-CSCF, S-CSCF, and I-CSCF for the relevant SIP messages within the last 120 seconds all came back empty, contradicting the hypothesis that 200 OKs are being sent but not received.

**Probes executed (3):**
- **Read P-CSCF logs for outgoing SIP REGISTER messages, e.g., 'SIP REGISTER request sent to'.** ✗ CONTRADICTS
    - *Tool:* `default_api.read_container_logs(container = "pcscf", grep = "SIP REGISTER request sent to", since_seconds = 120)`
    - *Observation:* [EVIDENCE: read_container_logs("pcscf", "SIP REGISTER request sent to", 120) -> "(no log output)"]
    - *Comment:* This contradicts the core assumption of the hypothesis. If the P-CSCF is not sending REGISTER requests, it cannot be waiting for 200 OK responses. The fault lies in the P-CSCF's inability to initiate the registration.
- **Read S-CSCF logs for outgoing SIP 200 OK responses for REGISTER messages, e.g., 'SIP/2.0 200 OK for REGISTER sent to'.** ✗ CONTRADICTS
    - *Tool:* `default_api.read_container_logs(container = "scscf", grep = "SIP/2.0 200 OK for REGISTER sent to", since_seconds = 120)`
    - *Observation:* [EVIDENCE: read_container_logs("scscf", "SIP/2.0 200 OK for REGISTER sent to", 120) -> "(no log output)"]
    - *Comment:* This contradicts the claim that the 'S-CSCF is successfully processing some registrations'. The S-CSCF logs show no evidence of sending successful responses, which is expected since the P-CSCF never sent the initial requests.
- **Read I-CSCF logs for forwarding SIP 200 OK responses towards the P-CSCF, e.g., 'SIP/2.0 200 OK sending to <P_CSCF_IP>'. The investigator needs to identify the P-CSCF's IP first.** ✗ CONTRADICTS
    - *Tool:* `default_api.read_container_logs(container = "icscf", grep = "SIP/2.0 200 OK sending to 172.22.0.21", since_seconds = 120)`
    - *Observation:* [EVIDENCE: read_container_logs("icscf", "SIP/2.0 200 OK sending to 172.22.0.21", 120) -> "(no log output)"]
    - *Comment:* As expected from the previous probes, the I-CSCF is not forwarding any 200 OKs because it never receives them from the S-CSCF. This confirms the entire signaling chain for registration is dormant, not just the final return path to the P-CSCF.

**Alternative suspects:** pcscf


## Evidence Validation (Phase 6)

**Overall verdict:** clean
**Overall confidence:** high

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 4 | 3/3 | clean | high |
| `InvestigatorAgent_h2` | 4 | 3/3 | clean | high |
| `InvestigatorAgent_h3` | 4 | 3/3 | clean | high |


## Ground Truth

**Failure domain:** ims_signaling  
**Protocol impact:** SIP  
**Affected components:** pcscf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v6-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 150.0s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: The primary issue is a failure in the IMS core, where the P-CSCF cannot communicate with the PCF due to extreme network latency, preventing all user registrations; an initial theory of a UPF data plane blockage was disproven.
> - **timeline**:
>     1. The P-CSCF begins logging over 11,000 'httpclient:connfail' errors, indicating a complete failure to establish outbound HTTP connections.
>     2. As a result, SIP dialogs fail to establish, and P-CSCF metrics show zero successful IMS registrations.
>     3. Simultaneously, UPF metrics show a significant drop between ingress and egress packet rates, suggesting a data plane issue.
>     4. Investigation disproves the UPF fault by confirming its external connectivity, and isolates the P-CSCF connection failures to extreme latency (>3000ms RTT) on the path to the PCF.
> - **root_cause**: While all initial hypotheses were disproven, the investigation uncovered that the P-CSCF is unable to connect to the PCF due to severe network latency between them. The primary suspect is the PCF being unresponsive or a network path degradation. `primary_suspect_nf`: **pcf**.
> - **affected_components**:
>     - `pcf`: Root Cause (Candidate)
>     - `pcscf`: Secondary
>     - `upf`: Symptomatic
> - **recommendation**: The operator should manually investigate the cause of the extreme latency between the P-CSCF and PCF. Verify the health and resource utilization (CPU, memory) of the PCF container to ensure it is not overloaded. Additionally, inspect the virtual network path between the P-CSCF and PCF for any anomalies or misconfigurations that could explain a round-trip time of over 3 seconds.
> - **confidence**: low
> - **explanation**: All initial hypotheses from the Network Analyst were incorrect and have been disproven. The suspected UPF data plane blockage (h1) was falsified by a successful ping test from the UPF to an external network, proving its forwarding path is functional. The hypotheses regarding an internal P-CSCF failure (h2, h3) were also disproven; the P-CSCF's inability to establish SIP dialogs is a symptom, not the cause. The investigation revealed that the P-CSCF cannot establish required HTTP connections to the PCF because of extreme network latency, with tests measuring an RTT of over 3 seconds. This points to the PCF being unresponsive or a severe network path issue as the most likely root cause, but confidence is low as this was not part of the initial hypothesis set and requires further investigation.

### Scoring Breakdown

**Overall score: 90%**

**Scorer assessment:** The agent accurately identified extreme network latency affecting the P-CSCF as the root cause, correctly assessed the severity and fault type, and attributed it to the correct IMS layer, but its stated low confidence was under-calibrated given the quality of the diagnosis.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | Yes | The agent correctly identified 'extreme network latency' as the root cause, specifically noting that the P-CSCF is unable to connect due to this latency. This directly matches the simulated failure mode of elevated network latency on the P-CSCF. |
| Component overlap | 100% | The agent explicitly identifies 'pcscf' as an affected component and describes its inability to establish connections due to latency. While it also lists 'pcf' as a primary suspect for the *source* of the latency, the P-CSCF is clearly identified as the component experiencing the problem, which aligns with the simulated failure. |
| Severity correct | Yes | The agent accurately describes the impact as 'extreme network latency,' 'complete failure to establish outbound HTTP connections,' and 'preventing all user registrations,' which correctly reflects the severe degradation leading to an outage for IMS registrations. |
| Fault type identified | Yes | The agent clearly identifies the fault type as 'extreme network latency' and 'network path degradation,' which is precisely what was simulated. |
| Layer accuracy | Yes | The agent correctly rates the 'ims' layer as 'red' and provides evidence directly related to the P-CSCF, which belongs to the IMS layer according to the ontology. |
| Confidence calibrated | No | The agent's diagnosis is highly accurate, correctly identifying the root cause, affected component, severity, and fault type. Stating 'low' confidence for such a precise and correct diagnosis is under-calibrated. |

**Ranking position:** #1 — The agent presents a single, correct root cause in its final diagnosis, after disproving initial hypotheses.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 116,917 |
| Output tokens | 6,362 |
| Thinking tokens | 16,110 |
| **Total tokens** | **139,389** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| EventAggregator | 0 | 0 | 0 |
| CorrelationAnalyzer | 0 | 0 | 0 |
| NetworkAnalystAgent | 24,865 | 3 | 4 |
| InstructionGeneratorAgent | 8,891 | 0 | 1 |
| InvestigatorAgent_h1 | 30,951 | 4 | 5 |
| InvestigatorAgent_h2 | 33,114 | 4 | 5 |
| InvestigatorAgent_h3 | 34,880 | 4 | 5 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 6,688 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 289.8s
