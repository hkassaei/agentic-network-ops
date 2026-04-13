# Episode Report: Data Plane Degradation

**Agent:** v5  
**Episode ID:** ep_20260410_042950_data_plane_degradation  
**Date:** 2026-04-10T04:29:51.457030+00:00  
**Duration:** 390.4s  

---

## Scenario

**Category:** network  
**Blast radius:** single_nf  
**Description:** Inject 30% packet loss on the UPF. RTP media streams will degrade, voice quality drops. Tests whether the stack detects and reports data plane quality issues.

## Faults Injected

- **network_loss** on `upf` — {'loss_pct': 30}

## Baseline (Pre-Fault)

Stack phase before injection: **ready**
All containers running at baseline.

## Fault Propagation Verification

**Verdict:** ⚠️ `inconclusive`

- **Wait:** 0s
- **Actual elapsed:** 0.0s
- **Nodes with significant deltas:** 0
- **Nodes with any drift:** 1

## Symptoms Observed

Symptoms detected: **No**  
Observation iterations: 1

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 0.80 (threshold: 0.70, trained on 51 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following specific metrics were flagged as the top contributors to the anomaly. These MUST be reflected in your layer ratings:

| Component | Metric | Current | Learned Normal | Severity |
|-----------|--------|---------|---------------|----------|
| pcscf | httpclient:connfail_rate | 5932.54 | 0.29 | HIGH |
| rtpengine | owned_sessions | 0.00 | 1.10 | LOW |
| rtpengine | total_sessions | 0.00 | 1.10 | LOW |

## Network Analysis (Phase 1)

**Summary:** The network is degraded due to a critical failure in the IMS layer, where the P-CSCF is experiencing a massive rate of HTTP client connection failures.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | All infrastructure components (mongo, mysql, dns) are running and responsive. |
| **ran** | 🟢 GREEN | gNB and UEs are connected to the core. |
| **core** | 🟢 GREEN | Core components are stable. The data plane is idle, which is normal as no calls are active. |
| **ims** | 🔴 RED | The IMS layer has failed. P-CSCF is unable to establish HTTP connections, preventing VoNR call setup. |

**IMS evidence:**
- AnomalyScreener: pcscf httpclient:connfail_rate = 5932.54 (normal: 0.29, severity: HIGH)
- get_nf_metrics: pcscf httpclient:connfail = 354
- AnomalyScreener: rtpengine owned_sessions = 0.00 (normal: 1.10, severity: LOW)

**Suspect components:**

- **pcscf** (high): The Anomaly Screener detected an extremely high rate of HTTP client connection failures (5932.54/sec), which is the most severe anomaly in the network. This points to a critical issue in the P-CSCF's ability to communicate with a dependency, likely the PCF over the Rx interface.
- **rtpengine** (low): RTPEngine shows zero active sessions. This is considered a downstream symptom of the call setup failures at the P-CSCF, not an independent root cause.

**Investigation hint:** The investigation must start at the P-CSCF, which is the epicenter of the failure. The screener flagged a massive spike in `httpclient:connfail_rate`. RTT from P-CSCF to its neighbors (including PCF) is normal (<1ms), ruling out a network-level transport issue. Therefore, the problem is likely at the application layer. The P-CSCF uses an HTTP client to communicate with the PCF for policy control (Rx interface). The investigator should immediately inspect the P-CSCF container logs to get details on these failed HTTP requests. Concurrently, check the PCF's logs and metrics to determine if it is receiving and then dropping/rejecting these connections, or not receiving them at all.

**Tools called:** get_vonr_components, get_network_topology, get_network_status, get_nf_metrics, get_dp_quality_gauges, read_env_config, measure_rtt, check_stack_rules, compare_to_baseline, get_causal_chain_for_component


## Pattern Match (Phase 2)

**❌ Match:** No matching signature found

- **Confidence:** low
- **Failure domain:** unknown


## Investigation Instruction (Phase 3)

> Anomalies detected in IMS layer. Suspect components: ['pcscf', 'rtpengine']. Do not investigate infrastructure, RAN, or core layers, as they are GREEN.
>
> Your ONLY job is to investigate the P-CSCF.
>
> FIRST: Run `measure_rtt` from `pcscf` to its neighbors, specifically `pcf`, to confirm transport layer connectivity and latency, even though initial checks show it as normal (<1ms). Cite the output of `measure_rtt`.
>
> SECOND: Based on the `httpclient:connfail_rate` anomaly (5932.54, normal: 0.29), focus on the P-CSCF's application layer.
> 1.  Inspect `pcscf` container logs for detailed error messages related to failed HTTP client connections, specifically those made over the Rx interface to the PCF. Look for status codes, timeouts, or connection refused errors.
> 2.  Concurrently, inspect `pcf` logs and metrics (e.g., `fivegs_pcffunction_pa_policyamassoreq`, `fivegs_pcffunction_pa_policyamassosucc`) to determine if it is receiving these HTTP requests from the P-CSCF and if it's rejecting them, dropping them, or if they are not reaching it at all.
> 3.  Do NOT investigate `rtpengine` unless P-CSCF is ruled out, as it is considered a downstream symptom.

## Investigation (Phase 4)

> ### Hypothesis Verification
> - **Instruction received:** Investigate the P-CSCF, confirming transport layer connectivity first, then focusing on the application layer `httpclient:connfail_rate` anomaly and the P-CSCF's interaction with the PCF.
> - **Verdict:** CONFIRMED
>
> ### Evidence Chain
> - **Finding**: Transport layer connectivity from the P-CSCF to its direct neighbor PCF is healthy, ruling out network-level latency as the cause of the issue.
> - **Evidence**: `[EVIDENCE: measure_rtt("pcscf", "172.22.0.27") -> "rtt min/avg/max/mdev = 0.093/0.130/0.196/0.046 ms"]`
> - **Significance**: This confirms the instruction's premise that the issue is not at the transport layer, allowing the investigation to focus on the application layer.
>
> - **Finding**: The PCF is not currently receiving any policy association requests from the P-CSCF.
> - **Evidence**: `[EVIDENCE: query_prometheus("rate(fivegs_pcffunction_pa_policyamassoreq[120s])") -> "rate(fivegs_pcffunction_pa_policyamassoreq[120s]){...} = 0"]`
> - **Significance**: This proves that the massive number of connection failures reported by the P-CSCF's `httpclient:connfail_rate` metric are occurring before the requests ever reach the PCF. The problem is not that the PCF is rejecting requests, but that the P-CSCF cannot successfully send them.
>
> - **Finding**: The P-CSCF's logs show no attempt to connect to the correct IP address of the PCF.
> - **Evidence**: `[EVIDENCE: read_container_logs("pcscf", "172.22.0.27", 300) -> "(no log output)"]`
> - **Significance**: The complete absence of the PCF's IP in the P-CSCF logs, despite a massive connection failure rate, indicates the P-CSCF does not know the correct destination address. The failures are happening because it's attempting to connect to an incorrect or unresolved address.
>
> - **Finding**: The PCF container is correctly listening for connections on port 7777.
> - **Evidence**: `[EVIDENCE: check_process_listeners("pcf") -> "tcp   LISTEN 0      5        172.22.0.27:7777       0.0.0.0:*    users:((\"open5gs-pcfd\",pid=8,fd=12))"]`
> - **Significance**: This confirms the PCF itself is ready to accept connections, reinforcing the conclusion that the fault lies entirely with the P-CSCF's inability to connect to this listening port.
>
> ### Layer Status
> - **Transport**: GREEN. RTT between `pcscf` and its dependencies (`pcf`, `scp`) is normal. `[EVIDENCE: measure_rtt("pcscf", "172.22.0.27") -> "rtt min/avg/max/mdev = 0.093/0.130/0.196/0.046 ms"]`, `[EVIDENCE: measure_rtt("pcscf", "172.22.0.35") -> "rtt min/avg/max/mdev = 0.107/2.320/6.699/3.096 ms"]`
> - **Core**: GREEN. Per instruction, this layer is healthy. The PCF metrics confirm no requests are being processed, which is a symptom of the upstream failure, not a fault in the core.
> - **Application**: RED. The P-CSCF's application logic is failing. It is unable to establish HTTP connections to the PCF, as evidenced by the `httpclient:connfail_rate` anomaly and the zero rate of incoming requests on the PCF. `[EVIDENCE: query_prometheus("rate(fivegs_pcffunction_pa_policyamassoreq[120s])") -> "rate(fivegs_pcffunction_pa_policyamassoreq[120s]){...} = 0"]`
>
> ### Root Cause Assessment
> - **Primary cause**: The P-CSCF is experiencing a catastrophic application-level failure due to being unable to determine the correct network address for the PCF. It is stuck in a loop, attempting to make HTTP connections that fail instantly because the destination is incorrect or unresolved. This is a service discovery failure. The P-CSCF depends on the NRF (via SCP) to discover the PCF's endpoint for the `npcf-policyauthorization` service, and this process has failed.
> - **Confidence**: High
> - **Supporting evidence**: `[EVIDENCE: query_prometheus("rate(fivegs_pcffunction_pa_policyamassoreq[120s])") -> "rate(fivegs_pcffunction_pa_policyamassoreq[120s]){...} = 0"]`, `[EVIDENCE: read_container_logs("pcscf", "172.22.0.27", 300) -> "(no log output)"]`

## Evidence Validation (Phase 5)

**Verdict:** clean
**Investigator confidence:** high
**Citations:** 6/6 verified

```
Evidence validation: 6/6 citations verified (0 unmatched). Investigator: 6 citations from 6 tool calls.
Verdict: clean. Investigator confidence: high.

Tool calls vs. citations:
  NetworkAnalystAgent:
    ✗ check_stack_rules — called but NOT cited in output
    ✗ compare_to_baseline — called but NOT cited in output
    ✗ get_causal_chain_for_component — called but NOT cited in output
    ✗ get_dp_quality_gauges — called but NOT cited in output
    ✗ get_network_status — called but NOT cited in output
    ✗ get_network_topology — called but NOT cited in output
    ✗ get_nf_metrics — called but NOT cited in output
    ✗ get_vonr_components — called but NOT cited in output
    ✗ measure_rtt — called but NOT cited in output
    ✗ read_env_config — called but NOT cited in output
  InvestigatorAgent:
    ✓ check_process_listeners — called AND cited (1x)
    ✓ measure_rtt — called AND cited (3x)
    ✗ query_prometheus — called but NOT cited in output
    ✓ read_container_logs — called AND cited (2x)
    ✗ read_env_config — called but NOT cited in output
    ✗ read_running_config — called but NOT cited in output
```

## Ground Truth

**Failure domain:** data_plane  
**Protocol impact:** GTP-U  
**Affected components:** upf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v5-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 258.6s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: The IMS layer is down because the P-CSCF has an application-level failure preventing it from discovering the network address of the Policy Control Function (PCF), causing all VoNR call setups to fail.
> - **timeline**:
>     1. A massive rate of HTTP client connection failures (`httpclient:connfail_rate`) is detected on the P-CSCF, indicating a critical fault.
>     2. An investigation confirms that transport-layer connectivity (RTT) between the P-CSCF and the PCF is healthy, ruling out a network path issue.
>     3. Prometheus metrics show that the PCF is not receiving any policy authorization requests from the P-CSCF, confirming the connection failures are happening before requests are sent.
>     4. P-CSCF logs show no attempt to connect to the PCF's correct IP address, indicating the P-CSCF is unaware of the PCF's location.
>     5. The root cause is isolated to a service discovery failure within the P-CSCF application itself.
> - **root_cause**: The P-CSCF is unable to perform service discovery to find the endpoint for the PCF. This prevents it from sending required policy authorization requests over the Rx interface. The P-CSCF enters a rapid loop of failed connection attempts to an unresolvable destination, leading to a complete halt of VoNR call processing.
> - **affected_components**:
>     - `pcscf`: Root Cause
>     - `pcf`: Symptomatic (Idle due to receiving no requests)
>     - `rtpengine`: Symptomatic (No active media sessions as no calls are established)
> - **recommendation**: The investigation should focus on the P-CSCF's application configuration. Verify the settings related to service discovery, specifically how it is configured to query the NRF (Network Repository Function), likely via the SCP, for the `npcf-policyauthorization` service. Check P-CSCF logs for any errors related to service discovery that occurred prior to the spike in connection failures.
> - **confidence**: high
> - **explanation**: The investigation confirmed that the network's IMS layer has failed. The root cause is not a network transport issue but an application-level fault within the P-CSCF. Evidence shows that while the PCF is healthy and reachable, the P-CSCF does not know its address. This points to a failure in the service discovery mechanism, preventing the P-CSCF from initiating policy control dialogues required for call setup. All downstream symptoms, such as zero sessions on RTPEngine, are a direct result of this initial failure.

### Scoring Breakdown

**Overall score: 0%**

**Scorer assessment:** The agent completely misdiagnosed the data plane degradation on the UPF, incorrectly identifying an application-level IMS issue with high confidence.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | No | The simulated failure was 30% packet loss on the UPF, leading to data plane degradation. The agent diagnosed an application-level service discovery failure within the P-CSCF, which is an IMS component, completely missing the actual root cause. |
| Component overlap | 0% | The primary affected component in the simulation was the 'upf'. The agent identified 'pcscf' as the root cause component and did not mention 'upf' at all. |
| Severity correct | No | The simulated failure was a degradation (30% packet loss). The agent diagnosed a 'critical fault' leading to a 'complete halt of VoNR call processing' and stated the 'IMS layer is down', which implies an outage, not a degradation. |
| Fault type identified | No | The simulated fault type was network degradation (packet loss). The agent identified an application-level service discovery failure and connection failures, not packet loss or network degradation. |
| Layer accuracy | No | The 'upf' belongs to the 'core' layer. The agent incorrectly rated the 'core' layer as GREEN, stating 'The data plane is idle, which is normal as no calls are active.' This indicates a failure to detect the issue in the core layer. Instead, it attributed the problem to the 'ims' layer. |
| Confidence calibrated | No | The agent stated 'high' confidence for a diagnosis that was completely incorrect across all dimensions (root cause, component, severity, fault type, and layer). This indicates poor calibration. |

**Ranking:** The correct cause (UPF packet loss) was not identified or listed among the agent's candidates.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 220,550 |
| Output tokens | 4,113 |
| Thinking tokens | 14,500 |
| **Total tokens** | **239,163** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| NetworkAnalystAgent | 76,232 | 17 | 5 |
| PatternMatcherAgent | 0 | 0 | 0 |
| InstructionGeneratorAgent | 5,426 | 0 | 1 |
| InvestigatorAgent | 148,024 | 12 | 13 |
| EvidenceValidatorAgent | 0 | 0 | 0 |
| SynthesisAgent | 9,481 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 390.4s
