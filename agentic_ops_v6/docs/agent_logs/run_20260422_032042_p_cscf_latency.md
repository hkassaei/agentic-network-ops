# Episode Report: P-CSCF Latency

**Agent:** v6  
**Episode ID:** ep_20260422_031504_p_cscf_latency  
**Date:** 2026-04-22T03:15:05.953062+00:00  
**Duration:** 336.4s  

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
- **Nodes with any drift:** 5

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 0.93 (threshold: 0.70, trained on 211 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following metrics deviate from their learned-healthy baseline. Treat each as a semantic observation (meaning + numbers), not a number alone — the KB's interpretation is the authoritative reading.

- **`derived.pcscf_sip_error_ratio`** (P-CSCF SIP error response ratio) — current **0.50 ratio** vs learned baseline **0.00 ratio** (MEDIUM, spike)
    - **What it measures:** Proportion of SIP responses that are errors. Zero is the healthy
baseline; any sustained non-zero value means P-CSCF or something
downstream is rejecting requests.
    - **Spike means:** Errors flowing back — downstream CSCFs or HSS rejecting.
    - **Healthy typical range:** 0–0 ratio
    - **Healthy invariant:** Zero in healthy operation.

- **`normalized.upf.gtp_outdatapktn3upf_per_ue`** (GTP-U downlink rate per UE (N3)) — current **0.06 packets_per_second** vs learned baseline **3.34 packets_per_second** (MEDIUM, drop)
    - **What it measures:** Health of the downlink user-plane path UPF → gNB. Typically mirrors
uplink rate during calls/data; asymmetry indicates directional
faults (e.g., UPF receiving from internet but not forwarding).
    - **Drop means:** No traffic leaving UPF toward RAN.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE — constant regardless of UE pool size. Roughly symmetric with uplink during healthy calls.

- **`normalized.upf.gtp_indatapktn3upf_per_ue`** (GTP-U uplink rate per UE (N3)) — current **0.18 packets_per_second** vs learned baseline **3.42 packets_per_second** (MEDIUM, drop)
    - **What it measures:** Health of the uplink user-plane path gNB → UPF. Drops to near-zero
during RAN or N3 outage; stays nonzero during active calls or data
sessions. Decoupled from SIP signaling (signals data plane, not
control plane).
    - **Drop means:** Data plane dead on uplink — UPF receiving no packets from gNB.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE — constant regardless of UE pool size. Rises during active VoNR calls (~100 pps for G.711 voice) and data transfer.

- **`normalized.pcscf.dialogs_per_ue`** (Active SIP dialogs per registered UE at P-CSCF) — current **0.00 count** vs learned baseline **0.57 count** (LOW, drop)
    - **What it measures:** How many calls per user are currently in progress at the P-CSCF.
Going to zero from a non-zero baseline means calls have ended
(normal) OR call setup is failing system-wide (degradation).
Together with rcv_requests_* it discriminates the two.
    - **Drop means:** No active calls. Normal at rest; suspicious if prior state had calls AND INVITE rate is also zero.
    - **Healthy typical range:** 0–1 count
    - **Healthy invariant:** Per-UE — scale-independent. 0 at rest, ~1 per active VoNR call.

- **`derived.upf_activity_during_calls`** — current **1.00** vs learned baseline **0.47** (LOW, spike). *(No KB context available — interpret from the metric name.)*


## Event Aggregation (Phase 1)

No events fired during this episode. Either no metric KB triggers matched, or the episode encountered no meaningful state transitions.

## Correlation Analysis (Phase 2)

No events fired — correlation engine had nothing to work with.

## Network Analysis (Phase 3)

**Summary:** The data plane is down due to a failure in establishing the user plane path, likely caused by an issue on the N4 interface between the SMF and UPF.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** |   |  |
| **ran** | 🟢 GREEN | RAN appears healthy; UEs are connected to the AMF. |
| **core** | 🔴 RED | The user plane is not carrying traffic. GTP traffic at the UPF is near zero in both directions, indicating a critical failure in the data path, likely related to SMF or UPF. |
| **ims** | 🟡 YELLOW | IMS call setup is failing. The P-CSCF is rejecting SIP requests, which appears to be related to failures communicating with the PCF. |

**CORE evidence:**
- normalized.upf.gtp_outdatapktn3upf_per_ue drop to 0.06
- normalized.upf.gtp_indatapktn3upf_per_ue drop to 0.18

**IMS evidence:**
- derived.pcscf_sip_error_ratio spike to 0.50
- normalized.pcscf.dialogs_per_ue drop to 0.00
- pcscf.httpclient:connfail = 42.0

**Ranked hypotheses:**

- **`h1`** (fit=0.90, nf=smf, specificity=specific):
    - **Statement:** The SMF is failing to correctly install N4 session rules on the UPF, resulting in a complete outage of the user data plane. Although the SMF reports active PDU sessions, the UPF has no forwarding rules and drops all GTP packets.
    - **Falsification probes:**
        - Check PFCP (N4) statistics on both SMF and UPF for session establishment errors or mismatches in active session counts.
        - Examine SMF logs for any errors related to PFCP session establishment or modification requests sent to the UPF.
        - Check UPF logs for incoming PFCP requests and any error responses.
- **`h2`** (fit=0.80, nf=pcscf, specificity=specific):
    - **Statement:** The P-CSCF is rejecting VoNR call setups because it cannot communicate with the PCF to obtain QoS policy authorization over the Rx interface. This is causing SIP errors and preventing any calls from being established.
    - **Falsification probes:**
        - Check P-CSCF logs for errors related to HTTP client connections to the PCF.
        - Check PCF logs to see if it is receiving Rx requests from the P-CSCF.
        - Measure RTT and connectivity from the P-CSCF container to the PCF container's IP address.
- **`h3`** (fit=0.60, nf=upf, specificity=moderate):
    - **Statement:** The UPF has experienced an internal failure and is black-holing all N3 and N9 traffic. This explains the complete lack of GTP traffic, but the root cause is within the UPF itself, not the N4 control interface.
    - **Falsification probes:**
        - Inspect UPF internal logs and process status for crashes, errors, or resource exhaustion symptoms.
        - Verify that the UPF has active N4 session state corresponding to the sessions reported by the SMF.
        - Check for packet drops using low-level counters on the UPF's network interfaces.


## Falsification Plans (Phase 4)

**3 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `smf`)

**Hypothesis:** The SMF is failing to correctly install N4 session rules on the UPF, resulting in a complete outage of the user data plane. Although the SMF reports active PDU sessions, the UPF has no forwarding rules and drops all GTP packets.

**Probes (3):**
1. **`get_nf_metrics`** — smf
    - *Expected if hypothesis holds:* A high or increasing value for a metric like `pfcp.session_establishment.failed` on the SMF.
    - *Falsifying observation:* The `pfcp.session_establishment.failed` counter on the SMF is 0. This directly contradicts the hypothesis that the SMF is failing to install rules.
2. **`get_dp_quality_gauges`** — window_seconds=60
    - *Expected if hypothesis holds:* The gNB is sending GTP-U packets (`ran.gtpu.tx.packets_per_second` > 0), but the UPF is not receiving them (`upf.n3.rx.packets_per_second` == 0), consistent with a drop or black-hole at the UPF.
    - *Falsifying observation:* The gNB is not sending any GTP-U packets (`ran.gtpu.tx.packets_per_second` == 0). This would indicate the problem is upstream of the SMF/UPF N4 interface.
3. **`get_network_status`** — smf, upf
    - *Expected if hypothesis holds:* Both the `smf` and `upf` containers are in a 'running' state, as the hypothesis concerns a protocol-level failure, not a container crash.
    - *Falsifying observation:* Either the `smf` or `upf` container is in an 'exited' state. This would point to a simpler container crash as the root cause, not a rule installation failure.

*Notes:* This plan tests the N4 failure hypothesis by checking for direct evidence of PFCP failures on the SMF, verifying the 'no traffic' symptom by checking upstream traffic from the gNB, and ruling out a simple container crash.

### Plan for `h2` (target: `pcscf`)

**Hypothesis:** The P-CSCF is rejecting VoNR call setups because it cannot communicate with the PCF to obtain QoS policy authorization over the Rx interface. This is causing SIP errors and preventing any calls from being established.

**Probes (3):**
1. **`measure_rtt`** — from='pcscf', to_ip='pcf_ip'
    - *Expected if hypothesis holds:* High RTT or 100% packet loss, indicating a network partition or problem on the PCF.
    - *Falsifying observation:* Clean, low RTT (<5ms). This proves basic network connectivity is fine, suggesting the problem is at the application layer (e.g., config, credentials, PCF logic).
2. **`measure_rtt`** — from='smf', to_ip='pcf_ip'
    - *Expected if hypothesis holds:* Clean, low RTT (<5ms). If this succeeds while the P-CSCF->PCF ping fails, it isolates the problem to the P-CSCF or its immediate network path.
    - *Falsifying observation:* High RTT or 100% packet loss. If the PCF is unreachable from multiple sources, it becomes the primary suspect, falsifying the hypothesis that the P-CSCF is the source of the communication failure.
3. **`get_nf_metrics`** — pcscf
    - *Expected if hypothesis holds:* A high or increasing value for P-CSCF's `http_client.conn_failed` metric, confirming that it is failing to connect to the PCF over the Rx interface.
    - *Falsifying observation:* The `http_client.conn_failed` metric is 0. This implies the P-CSCF is either not attempting to connect or is succeeding, meaning the SIP rejections have a different cause.

*Notes:* This is a triangulation plan. It first checks the P-CSCF->PCF path as suggested by the hypothesis. It then uses the SMF as a second vantage point to determine if the PCF is broadly unreachable, which would falsify the P-CSCF-specific nature of the hypothesis. Finally, it checks for application-level connection errors.

### Plan for `h3` (target: `upf`)

**Hypothesis:** The UPF has experienced an internal failure and is black-holing all N3 and N9 traffic. This explains the complete lack of GTP traffic, but the root cause is within the UPF itself, not the N4 control interface.

**Probes (3):**
1. **`get_network_status`** — upf
    - *Expected if hypothesis holds:* The `upf` container is in a 'running' state, as 'black-holing' implies a misbehaving but active process.
    - *Falsifying observation:* The `upf` container is in an 'exited' state, which would mean it crashed rather than experienced an 'internal failure' of the black-holing type.
2. **`get_nf_metrics`** — upf
    - *Expected if hypothesis holds:* High resource usage metrics for the `upf`, such as `container.cpu.usage` or `container.memory.usage`, which are common causes of internal failures.
    - *Falsifying observation:* Normal resource utilization for the `upf`. This would suggest the failure is not related to resource exhaustion but perhaps a software deadlock or other bug.
3. **`get_dp_quality_gauges`** — window_seconds=60
    - *Expected if hypothesis holds:* `ran.gtpu.tx.packets_per_second` is > 0 while `upf.n3.rx.packets_per_second` is 0, which confirms traffic is being sent but not received/processed by the UPF.
    - *Falsifying observation:* `ran.gtpu.tx.packets_per_second` is 0. If the gNB isn't sending traffic, the UPF cannot be black-holing it. This would point the problem upstream.

*Notes:* This plan aims to falsify the 'internal failure' hypothesis by checking for the most common failure modes: a container crash or resource exhaustion. It also verifies the precondition for the 'black-holing' claim by ensuring traffic is actually being sent to the UPF from upstream.


## Parallel Investigators (Phase 5)

**3 sub-Investigator verdict(s):** **2 DISPROVEN**, **1 NOT_DISPROVEN**

### `h1` — ❌ **DISPROVEN**

**Hypothesis:** The SMF is failing to correctly install N4 session rules on the UPF, resulting in a complete outage of the user data plane. Although the SMF reports active PDU sessions, the UPF has no forwarding rules and drops all GTP packets.

**Reasoning:** Probe 2 provided strong evidence that contradicts the hypothesis. The hypothesis states that the UPF is dropping GTP packets, but the `get_dp_quality_gauges` tool shows that the UPF is receiving virtually no packets on its N3 interface. This indicates the problem is not the UPF dropping traffic, but rather that no traffic is being sent from the RAN in the first place, pointing to an upstream issue.

**Probes executed (3):**
- **Check for a high or increasing value for a metric like `pfcp.session_establishment.failed` on the SMF.** ~ AMBIGUOUS
    - *Tool:* `print(default_api.get_nf_metrics())`
    - *Observation:* [EVIDENCE: get_nf_metrics() -> "SMF [4 PDU] (via prometheus):...pfcp_sessions_active = 4.0"]
    - *Comment:* The expected metric `pfcp.session_establishment.failed` was not returned, which often implies a value of zero. This weakly contradicts the hypothesis, as it suggests no failures are occurring. However, it's not strong proof on its own.
- **The gNB is sending GTP-U packets (`ran.gtpu.tx.packets_per_second` > 0), but the UPF is not receiving them (`upf.n3.rx.packets_per_second` == 0), consistent with a drop or black-hole at the UPF.** ✗ CONTRADICTS
    - *Tool:* `print(default_api.get_dp_quality_gauges(window_seconds=60))`
    - *Observation:* [EVIDENCE: get_dp_quality_gauges("window_seconds=60") -> "UPF: in packets/sec: 0.1"]
    - *Comment:* This observation directly falsifies the core of the hypothesis. The UPF cannot be dropping packets if it isn't receiving any. The near-zero ingress traffic points to an issue upstream from the UPF.
- **Both the `smf` and `upf` containers are in a 'running' state, as the hypothesis concerns a protocol-level failure, not a container crash.** ✓ CONSISTENT
    - *Tool:* `print(default_api.get_network_status())`
    - *Observation:* [EVIDENCE: get_network_status() -> "containers": {"smf": "running", "upf": "running"}]
    - *Comment:* This result confirms that the SMF and UPF are running, which is consistent with the hypothesis of a protocol-level failure rather than a component crash. However, it doesn't overcome the contradictory evidence from the other probes.

**Alternative suspects:** ran

### `h2` — ✅ **NOT_DISPROVEN**

**Hypothesis:** The P-CSCF is rejecting VoNR call setups because it cannot communicate with the PCF to obtain QoS policy authorization over the Rx interface. This is causing SIP errors and preventing any calls from being established.

**Reasoning:** All probes returned evidence consistent with the hypothesis. The P-CSCF has extremely high latency to the PCF, while another core component (SMF) has a clean, low-latency path, isolating the issue to the P-CSCF. Furthermore, P-CSCF's own metrics show a high number of HTTP connection failures, confirming it is failing to communicate with its peer (the PCF).

**Probes executed (3):**
- **Measure RTT from P-CSCF to PCF to check for network partition.** ✓ CONSISTENT
    - *Tool:* `measure_rtt("pcscf", "172.22.0.27")`
    - *Observation:* [EVIDENCE: measure_rtt("pcscf", "172.22.0.27") -> "rtt min/avg/max/mdev = 2043.974/3005.221/3955.627/780.466 ms"]
    - *Comment:* The average RTT of over 3 seconds is exceptionally high and confirms a severe network problem for the P-CSCF when trying to reach the PCF. This directly supports the hypothesis.
- **Measure RTT from SMF to PCF to triangulate the source of the high latency.** ✓ CONSISTENT
    - *Tool:* `measure_rtt("smf", "172.22.0.27")`
    - *Observation:* [EVIDENCE: measure_rtt("smf", "172.22.0.27") -> "rtt min/avg/max/mdev = 0.098/0.159/0.254/0.067 ms"]
    - *Comment:* The very low RTT from the SMF proves the PCF is healthy and reachable. This isolates the source of the communication failure to the P-CSCF or its specific network path, which is consistent with the hypothesis that P-CSCF cannot communicate with PCF.
- **Check P-CSCF metrics for application-level connection errors.** ✓ CONSISTENT
    - *Tool:* `get_nf_metrics()`
    - *Observation:* [EVIDENCE: get_nf_metrics() -> "PCSCF ... httpclient:connfail = 59.0 ... httpclient:connok = 0.0"]
    - *Comment:* The metrics show that the P-CSCF's HTTP client has failed to connect 59 times with zero successful connections. This is strong evidence of an application-layer failure to communicate with the PCF over the Rx (HTTP-based) interface, as predicted by the hypothesis.

### `h3` — ❌ **DISPROVEN**

**Hypothesis:** The UPF has experienced an internal failure and is black-holing all N3 and N9 traffic. This explains the complete lack of GTP traffic, but the root cause is within the UPF itself, not the N4 control interface.

**Reasoning:** The hypothesis is disproven because its central claim, that the UPF is 'black-holing' traffic, is false. The precondition for black-holing is that traffic is being sent to the component in the first place. Evidence from data plane quality gauges shows that the UPF is receiving virtually no traffic on its N3 interface. Therefore, the lack of GTP traffic is due to upstream starvation, not an internal failure at the UPF.

**Probes executed (3):**
- **Check if the `upf` container is in a 'running' state, as 'black-holing' implies a misbehaving but active process.** ✓ CONSISTENT
    - *Tool:* `print(default_api.get_network_status())`
    - *Observation:* [EVIDENCE: get_network_status() -> "{\"phase\": \"ready\", ... \"upf\": \"running\"...}"]
    - *Comment:* The UPF container is running, which is consistent with the hypothesis of an active but misbehaving network function.
- **Check for high resource usage metrics for the `upf`, such as `container.cpu.usage` or `container.memory.usage`.** ~ AMBIGUOUS
    - *Tool:* `print(default_api.get_nf_metrics())`
    - *Observation:* [EVIDENCE: get_nf_metrics() -> "UPF [8 sess] (via prometheus):\n  fivegs_ep_n3_gtp_indatapktn3upf = 22886.0  [counter]...fivegs_upffunction_upf_sessionnbr = 8.0  [gauge]"]
    - *Comment:* The available metrics for the UPF do not include CPU or memory usage, so resource exhaustion cannot be confirmed or denied. The existing metrics do not suggest an internal failure.
- **Check if `ran.gtpu.tx.packets_per_second` is > 0 while `upf.n3.rx.packets_per_second` is 0, to confirm traffic is being sent but not processed by the UPF.** ✗ CONTRADICTS
    - *Tool:* `print(default_api.get_dp_quality_gauges(window_seconds=60))`
    - *Observation:* [EVIDENCE: get_dp_quality_gauges("window_seconds=60") -> "UPF:\n    in  packets/sec: 0.1\n    out packets/sec: 0.0"]
    - *Comment:* The UPF's ingress packet rate is near zero (0.1 pps). This falsifies the hypothesis because the UPF cannot be 'black-holing' traffic it is not receiving. The problem is upstream of the UPF's N3 interface.

**Alternative suspects:** smf, ran


## Evidence Validation (Phase 6)

**Overall verdict:** clean
**Overall confidence:** high

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 3 | 3/3 | clean | high |
| `InvestigatorAgent_h2` | 4 | 3/3 | clean | high |
| `InvestigatorAgent_h3` | 3 | 3/3 | clean | high |


## Ground Truth

**Failure domain:** ims_signaling  
**Protocol impact:** SIP  
**Affected components:** pcscf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v6-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 193.7s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: IMS voice services are down due to a severe network connectivity failure between the P-CSCF and the PCF, preventing call authorization.
> - **timeline**:
>     1. The core data plane was observed to be down, with near-zero GTP traffic arriving at the UPF.
>     2. Simultaneously, IMS VoNR call setups began to fail, with the P-CSCF rejecting requests.
>     3. Investigation confirmed PDU sessions were active on the SMF, but no corresponding traffic was being sent from the RAN to the UPF.
>     4. Further investigation revealed the P-CSCF was unable to communicate with the PCF, showing >3000ms RTT and 100% connection failure rates, while other components' connectivity to the PCF remained healthy.
> - **root_cause**: A network path degradation or misconfiguration is preventing the P-CSCF from communicating with the PCF over the Rx interface to get policy authorization for calls. The `primary_suspect_nf` is the `pcscf`'s networking environment.
> - **affected_components**:
>     - `pcscf`: Root Cause (experiencing isolated network failure)
>     - `pcf`: Secondary (unreachable by P-CSCF but otherwise healthy)
>     - `ims`: Symptomatic (call setup fails due to lack of policy authorization)
>     - `upf`: Symptomatic (displays no traffic, but is not the cause)
> - **recommendation**: Verify the network configuration and health of the underlying virtual network fabric connecting the `pcscf` container to the `pcf` container. Examine for any specific network policies, routing issues, or link failures that could be the source of the isolated high latency observed on this path.
> - **confidence**: high
> - **explanation**: The root cause of the IMS service failure is a network connectivity breakdown between the P-CSCF and the PCF. This was confirmed with high confidence after probes measured an extremely high RTT (>3s) unique to the P-CSCF's path to the PCF, and P-CSCF metrics showed a total failure to establish required HTTP connections for policy control. While a wider data plane outage was also observed, hypotheses blaming the SMF or UPF were disproven, as evidence showed the UPF is not receiving traffic to begin with. The data plane issue is therefore located upstream of the core network and is considered a separate fault from the confirmed P-CSCF connectivity issue.

### Scoring Breakdown

**Overall score: 100%**

**Scorer assessment:** The agent provided an excellent and highly accurate diagnosis, correctly identifying the root cause, affected component, severity, and fault type, with appropriate confidence and layer attribution.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | Yes | The simulated failure was P-CSCF latency (2000ms delay). The agent identified 'network path degradation' and 'high RTT (>3s)' unique to the P-CSCF's path to the PCF, which is semantically equivalent to elevated latency on the P-CSCF's interfaces. |
| Component overlap | 100% | The simulated affected component was 'pcscf'. The agent correctly identified 'pcscf' as the 'Root Cause' in its 'affected_components' list. |
| Severity correct | Yes | The simulated 2000ms latency would cause 'severe delays' and 'IMS registration failures', effectively leading to a service outage for many transactions. The agent diagnosed 'IMS voice services are down' and '100% connection failure rates', which accurately reflects the impact of such high latency. |
| Fault type identified | Yes | The simulated fault type was 'Elevated network latency'. The agent identified 'network path degradation' and 'high RTT (>3s)', which correctly describes the observable fault type. |
| Layer accuracy | Yes | The 'pcscf' component belongs to the 'ims' layer. The agent's network analysis correctly rated the 'ims' layer as 'yellow' and provided P-CSCF related evidence for this rating. |
| Confidence calibrated | Yes | The agent's diagnosis is accurate across all evaluated dimensions, making its 'high' confidence level appropriate and well-calibrated. |

**Ranking position:** #1 — The agent provided a single, clear root cause in its final diagnosis, with 'pcscf' explicitly labeled as the 'Root Cause' in the 'affected_components' list.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 159,393 |
| Output tokens | 5,725 |
| Thinking tokens | 17,116 |
| **Total tokens** | **182,234** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| EventAggregator | 0 | 0 | 0 |
| CorrelationAnalyzer | 0 | 0 | 0 |
| NetworkAnalystAgent | 36,343 | 6 | 3 |
| InstructionGeneratorAgent | 19,854 | 3 | 2 |
| InvestigatorAgent_h1 | 45,327 | 3 | 4 |
| InvestigatorAgent_h2 | 45,827 | 4 | 5 |
| InvestigatorAgent_h3 | 26,246 | 3 | 3 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 8,637 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 336.4s
