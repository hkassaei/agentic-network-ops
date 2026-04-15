# Episode Report: P-CSCF Latency

**Agent:** v5  
**Episode ID:** ep_20260414_220341_p_cscf_latency  
**Date:** 2026-04-14T22:03:43.181812+00:00  
**Duration:** 335.6s  

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
- **Nodes with any drift:** 3

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

### Metrics Changes

| Node | Metric | Baseline | Current | Delta |
|------|--------|----------|---------|-------|
| pcscf | sl:4xx_replies | 0.0 | 3.0 | 3.0 |
| pcscf | core:rcv_requests_invite | 34.0 | 43.0 | 9.0 |
| smf | bearers_active | 4.0 | 5.0 | 1.0 |

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 0.88 (threshold: 0.70, trained on 99 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following specific metrics were flagged as the top contributors to the anomaly. These MUST be reflected in your layer ratings:

| Component | Metric | Current | Learned Normal | Severity |
|-----------|--------|---------|---------------|----------|
| derived | pcscf_sip_error_ratio | 1.00 | 0.00 | HIGH |
| scscf | ims_registrar_scscf:sar_avg_response_time | 148.00 | 119.92 | HIGH |
| scscf | ims_auth:mar_avg_response_time | 107.00 | 88.89 | MEDIUM |
| normalized | upf.gtp_outdatapktn3upf_per_ue | 0.06 | 2.50 | MEDIUM |
| normalized | upf.gtp_indatapktn3upf_per_ue | 0.20 | 2.58 | MEDIUM |
| icscf | ims_icscf:lir_avg_response_time | 72.00 | 51.03 | MEDIUM |
| normalized | pcscf.dialogs_per_ue | 0.00 | 0.65 | LOW |
| derived | upf_activity_during_calls | 1.00 | 0.39 | LOW |

## Network Analysis (Phase 1)

**Summary:** The IMS layer has failed due to catastrophic network latency originating from the P-CSCF, causing SIP transaction timeouts.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | All infrastructure components (MongoDB, MySQL, DNS) are running and responsive. |
| **ran** | 🟢 GREEN | gNB is connected and 2 UEs are registered with the AMF. |
| **core** | 🟡 YELLOW | Core components are running, but policy communication between IMS and Core (P-CSCF to PCF) is severely impaired by latency. |
| **ims** | 🔴 RED | The IMS layer is non-functional due to extreme network latency at the P-CSCF, preventing SIP signaling from proceeding. |

**CORE evidence:**
- RTT from P-CSCF to PCF is ~2987ms (expected <10ms)
- P-CSCF is reporting a high number of httpclient connection failures (579) likely related to failed Rx communication with PCF.
- scp container has exited, but this is not the primary cause of the issue.

**IMS evidence:**
- Anomaly screener flagged 'pcscf_sip_error_ratio: 1.00' (HIGH severity).
- Round-trip time from P-CSCF to I-CSCF is ~2006ms, making SIP signaling impossible.
- Round-trip time from P-CSCF to RTPEngine is ~1989ms.
- S-CSCF is showing elevated response times for Diameter SAR (148ms) and MAR (107ms), likely a downstream effect of the overall latency.

**Suspect components:**

- **pcscf** (high): The P-CSCF is the epicenter of the failure. RTT measurements from the pcscf container to multiple, independent components (I-CSCF, PCF, RTPEngine) show a catastrophic latency of 2-4 seconds. This directly explains the 100% SIP error ratio detected by the anomaly screener and renders all IMS services unusable.

**Investigation hint:** The investigation must focus on the P-CSCF container and its host environment. The multi-second RTT to multiple targets strongly suggests a problem with the pcscf container's network stack itself, or resource exhaustion (CPU, memory) on the Docker host that is starving the container. The issue is less likely to be the physical network, as other containers would be affected. Check the pcscf container's resource usage, inspect its virtual network interface, and examine the Docker host's system logs for any signs of network or resource contention.

**Tools called:** get_vonr_components, get_network_topology, get_network_status, get_nf_metrics, get_dp_quality_gauges, read_env_config, measure_rtt, check_stack_rules, compare_to_baseline, get_causal_chain_for_component


## Pattern Match (Phase 2)

**❌ Match:** No matching signature found

- **Confidence:** low
- **Failure domain:** unknown
- **Baseline anomalies:** 1 metrics across 1 components


## Investigation Instruction (Phase 3)

> Anomalies detected in IMS (RED) and Core (YELLOW) layers. Suspect components: [`pcscf`].
> The primary issue is catastrophic network latency originating from the P-CSCF, causing SIP transaction timeouts and impairing policy communication.
>
> FIRST, per the Hierarchy of Truth, investigate the transport layer from the P-CSCF. The multi-second RTT to multiple targets strongly suggests a problem with the `pcscf` container's network stack or resource exhaustion on its host.
> 1. Run `measure_rtt` from `pcscf` to its critical neighbors to verify the reported multi-second latencies and check for packet loss:
>     *   `measure_rtt(from='pcscf', to='icscf')`
>     *   `measure_rtt(from='pcscf', to='pcf')`
>     *   `measure_rtt(from='pcscf', to='rtpengine')`
>
> 2. Next, examine the `pcscf` container for indications of resource exhaustion, network interface issues, or other internal errors:
>     *   `read_container_logs(container='pcscf', grep='error|timeout|latency|resource|CPU|memory', since='1h')`
>     *   `get_nf_metrics(component='pcscf')` to check for the reported `httpclient:connfail` (587) and other relevant performance counters.
>
> 3. Briefly confirm the `scp` container's `exited` status using `get_network_status()`, but note that the Network Analyst has determined this is not the primary cause.
>
> Do NOT investigate other layers (RAN, Infrastructure) at this stage as they are reported GREEN. The S-CSCF elevated response times for Diameter are likely a downstream effect of the P-CSCF latency and should not be a primary investigation target until the P-CSCF is cleared.

## Investigation (Phase 4)

> ### Hypothesis Verification
> - Instruction received: The investigation instruction directed me to focus on the transport layer of the `pcscf` container, suspecting catastrophic network latency as the root cause of IMS and Core layer anomalies.
> - Verdict: CONFIRMED
>
> ### Evidence Chain
> - **Finding**: The `pcscf` container is experiencing catastrophic network latency, with a round-trip time of approximately 2 seconds to all its network neighbors. This level of delay makes any real-time communication, such as SIP or HTTP, impossible.
> - **Evidence**:
>   - `[EVIDENCE: measure_rtt(container='pcscf', target_ip='172.22.0.19') -> "rtt min/avg/max/mdev = 2018.769/2029.989/2040.926/9.047 ms"]`
>   - `[EVIDENCE: measure_rtt(container='pcscf', target_ip='172.22.0.27') -> "rtt min/avg/max/mdev = 1962.978/1980.619/1995.502/13.420 ms"]`
>   - `[EVIDENCE: measure_rtt(container='pcscf', target_ip='172.22.0.16') -> "rtt min/avg/max/mdev = 1962.368/1988.887/2014.962/21.473 ms"]`
> - **Significance**: An RTT of ~2000ms (where <1ms is normal) confirms a severe transport layer issue isolated to the `pcscf` container. This latency is the direct cause of the application-level failures.
>
> - **Finding**: The P-CSCF is experiencing a high number of HTTP client connection failures, which is a direct symptom of the underlying network latency when trying to communicate with the PCF.
> - **Evidence**: `[EVIDENCE: get_nf_metrics() -> "PCSCF ... httpclient:connfail = 599.0"]`
> - **Significance**: This metric confirms the impact of the transport-layer latency on the core layer's policy communication. The P-CSCF cannot establish policy sessions with the PCF because the HTTP requests are timing out.
>
> - **Finding**: The P-CSCF container's internal logs show no signs of errors related to resource exhaustion or application-level faults.
> - **Evidence**: `[EVIDENCE: read_container_logs(container='pcscf', grep='error|timeout|latency|resource|CPU|memory', since_seconds=3600) -> "(no log output)"]`
> - **Significance**: The absence of internal errors strongly suggests the application within the container is healthy but is a victim of a problem in its external environment, specifically the networking stack provided by the host.
>
> - **Finding**: The Service Communication Proxy (SCP) container has exited.
> - **Evidence**: `[EVIDENCE: get_network_status() -> "down_or_absent: [\"scp\"], containers: {\"scp\": \"exited\"}"]`
> - **Significance**: While this is an anomaly, it is not the primary cause of the issue, as the catastrophic latency is specifically isolated to the `pcscf` container and affects its communication with multiple, independent components that do not rely on the SCP.
>
> ### Layer Status
> - **Transport**: RED. The `pcscf` container's transport layer is fundamentally broken, exhibiting a uniform ~2000ms RTT to any destination `[EVIDENCE: measure_rtt(container='pcscf', target_ip='172.22.0.19') -> "rtt min/avg/max/mdev = 2018.769/2029.989/2040.926/9.047 ms"]`.
> - **Core**: YELLOW. Core components are running, but policy communication is impaired due to the P-CSCF's inability to connect to the PCF, as shown by the high number of connection failures `[EVIDENCE: get_nf_metrics() -> "PCSCF ... httpclient:connfail = 599.0"]`.
> - **Application**: RED. The IMS application (SIP signaling) is non-functional. The 2-second latency `[EVIDENCE: measure_rtt(container='pcscf', target_ip='172.22.0.19') -> "rtt min/avg/max/mdev = 2018.769/2029.989/2040.926/9.047 ms"]` makes it impossible for SIP transactions to complete before timing out, explaining the 100% SIP error ratio reported by the anomaly screener.
>
> ### Root Cause Assessment
> - **Primary cause**: The definitive root cause is a catastrophic network issue isolated to the `pcscf` container, which imposes a ~2-second delay on all its outbound traffic. The issue is not with the P-CSCF application itself, which shows no internal errors, but rather with the container's network stack or its host environment. This could be due to a misconfigured traffic shaping rule (e.g., `netem delay`) or extreme resource starvation on the host node affecting only this container's network interface.
> - **Confidence**: High
> - **Supporting evidence**:
>   - `[EVIDENCE: measure_rtt(container='pcscf', target_ip='172.22.0.19') -> "rtt min/avg/max/mdev = 2018.769/2029.989/2040.926/9.047 ms"]`
>   - `[EVIDENCE: measure_rtt(container='pcscf', target_ip='172.22.0.27') -> "rtt min/avg/max/mdev = 1962.978/1980.619/1995.502/13.420 ms"]`
>   - `[EVIDENCE: get_nf_metrics() -> "PCSCF ... httpclient:connfail = 599.0"]`
>   - `[EVIDENCE: read_container_logs(container='pcscf', grep='error|timeout|latency|resource|CPU|memory', since_seconds=3600) -> "(no log output)"]`

## Evidence Validation (Phase 5)

**Verdict:** clean
**Investigator confidence:** high
**Citations:** 13/13 verified

```
Evidence validation: 13/13 citations verified (0 unmatched). Investigator: 13 citations from 5 tool calls.
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
    ✓ get_network_status — called AND cited (1x)
    ✓ get_nf_metrics — called AND cited (3x)
    ✓ measure_rtt — called AND cited (7x)
    ✓ read_container_logs — called AND cited (2x)
    ✗ read_env_config — called but NOT cited in output
```

## Ground Truth

**Failure domain:** ims_signaling  
**Protocol impact:** SIP  
**Affected components:** pcscf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v5-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 204.9s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: The P-CSCF container is experiencing a severe, isolated network issue that adds ~2 seconds of latency to all its outbound traffic, causing a total failure of the IMS layer due to SIP and HTTP timeouts.
> - **timeline**:
>     1. A network fault begins, localized to the `pcscf` container, imposing a uniform ~2000ms delay on all its egress network traffic.
>     2. P-CSCF attempts to establish policy sessions with the PCF fail due to HTTP connection timeouts, resulting in over 599 connection failures.
>     3. P-CSCF attempts to forward SIP traffic to other IMS components (I-CSCF, RTPEngine) also fail, as the 2-second round-trip time far exceeds standard SIP transaction timers.
>     4. The IMS layer becomes completely non-functional, as confirmed by a 100% SIP error ratio, because no signaling can successfully transit the P-CSCF.
> - **root_cause**: A catastrophic performance degradation in the network stack of the `pcscf` container. This is not an application-level fault, as the P-CSCF application itself shows no internal errors. The ~2-second latency, confirmed via pings to multiple independent components, is the definitive cause of all subsequent application-layer timeouts.
> - **affected_components**:
>     - `pcscf`: Root Cause (The fault is isolated to this container's network environment)
>     - `icscf`: Symptomatic (Unable to receive timely SIP messages from P-CSCF)
>     - `pcf`: Symptomatic (Unable to receive timely Rx policy requests from P-CSCF)
>     - `ims`: Symptomatic (Layer is down due to P-CSCF failure)
> - **recommendation**: The operator should immediately inspect the host environment of the `pcscf` container. Investigation should focus on host-level networking rules that may be applied to the container's interface and check for severe resource exhaustion (CPU, memory) on the host that could be starving the container's network stack.
> - **confidence**: high
> - **explanation**: The diagnosis is high confidence because direct transport layer measurements (`measure_rtt`) definitively confirmed a catastrophic ~2-second latency originating from the `pcscf` container to multiple destinations. This network issue is the direct cause of the observed application failures, including the 100% SIP error rate and failed policy communication with the PCF. Since the P-CSCF's internal logs show no application errors, the fault lies within the container's networking environment, not the P-CSCF application itself.

### Scoring Breakdown

**Overall score: 100%**

**Scorer assessment:** The agent provided an exceptionally accurate diagnosis, correctly identifying the P-CSCF network latency as the root cause, pinpointing the affected component and layer, and assessing the severity and fault type with appropriate confidence.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | Yes | The agent correctly identified 'catastrophic performance degradation in the network stack of the `pcscf` container' and '~2-second latency' as the definitive root cause, which perfectly matches the simulated failure of 2000ms latency on the P-CSCF. |
| Component overlap | 100% | The agent explicitly named 'pcscf' as the 'Root Cause' component, which is the primary affected component in the simulated failure. |
| Severity correct | Yes | The agent described the issue as 'severe', 'catastrophic performance degradation', and leading to 'total failure of the IMS layer' with a '100% SIP error ratio', which accurately reflects the impact of a 2000ms latency causing timeouts. |
| Fault type identified | Yes | The agent clearly identified 'latency' and 'performance degradation in the network stack' as the fault type, which is precisely what was simulated. |
| Layer accuracy | Yes | The agent correctly attributed the P-CSCF failure to the 'ims' layer, rating it RED, and noted the impact on the 'core' layer (PCF communication) as a downstream effect. This aligns with the ontology where P-CSCF belongs to the IMS layer. |
| Confidence calibrated | Yes | The agent stated 'high' confidence, which is appropriate given the accuracy and detailed evidence (RTT measurements, SIP error ratios) provided in the diagnosis. |

**Ranking position:** #1 — The agent provided a single, clear root cause, which was correct.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 135,642 |
| Output tokens | 5,068 |
| Thinking tokens | 11,901 |
| **Total tokens** | **152,611** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| NetworkAnalystAgent | 85,290 | 13 | 6 |
| PatternMatcherAgent | 0 | 0 | 0 |
| InstructionGeneratorAgent | 7,268 | 0 | 1 |
| InvestigatorAgent | 49,531 | 7 | 4 |
| EvidenceValidatorAgent | 0 | 0 | 0 |
| SynthesisAgent | 10,522 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 335.6s
