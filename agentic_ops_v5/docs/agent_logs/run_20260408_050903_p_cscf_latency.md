# Episode Report: P-CSCF Latency

**Agent:** v5  
**Episode ID:** ep_20260408_050341_p_cscf_latency  
**Date:** 2026-04-08T05:03:42.025440+00:00  
**Duration:** 321.1s  

---

## Scenario

**Category:** network  
**Blast radius:** single_nf  
**Description:** Inject 500ms latency on the P-CSCF (SIP edge proxy). SIP T1 timer is 500ms, so REGISTER transactions will start timing out. Tests IMS resilience to WAN-like latency on the signaling path.

## Faults Injected

- **network_latency** on `pcscf` — {'delay_ms': 2000, 'jitter_ms': 50}

## Baseline (Pre-Fault)

Stack phase before injection: **ready**
All containers running at baseline.

## Fault Propagation Verification

**Verdict:** ⚠️ `inconclusive`

- **Wait:** 30s
- **Actual elapsed:** 30.0s
- **Nodes with significant deltas:** 0
- **Nodes with any drift:** 4

## Symptoms Observed

Symptoms detected: **No**  
Observation iterations: 1

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 0.99 (threshold: 0.70, trained on 50 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following specific metrics were flagged as the top contributors to the anomaly. These MUST be reflected in your layer ratings:

| Component | Metric | Current | Learned Normal | Severity |
|-----------|--------|---------|---------------|----------|
| pcscf | core:rcv_requests_register_rate | 2720.63 | 0.08 | HIGH |
| pcscf | sl:1xx_replies_rate | 906.88 | 0.12 | HIGH |
| pcscf | httpclient:connfail_rate | 453.44 | 0.27 | HIGH |
| icscf | core:rcv_requests_register_rate | 453.44 | 0.08 | HIGH |
| upf | fivegs_ep_n3_gtp_indatapktn3upf_rate | 3174.07 | 5.04 | HIGH |
| upf | fivegs_ep_n3_gtp_outdatapktn3upf_rate | 1813.75 | 4.92 | HIGH |
| icscf | cdp:timeout | 1.00 | 0.00 | HIGH |
| icscf | ims_icscf:uar_timeouts | 1.00 | 0.00 | HIGH |
| pcscf | tmx:active_transactions | 2.00 | 0.04 | HIGH |
| scscf | cdp:average_response_time | 112.00 | 86.98 | MEDIUM |

## Network Analysis (Phase 1)

**Summary:** The IMS layer is failing due to catastrophic network latency isolated to the P-CSCF container, causing SIP signaling timeouts and cascading failures.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | All infrastructure components (mongo, mysql, dns) are running and connected. |
| **ran** | 🟢 GREEN | RAN appears healthy, with 1 gNB and 2 UEs connected to the AMF. |
| **core** | 🟢 GREEN | Core components are stable. Near-zero data plane throughput is the expected idle state, as no active call is in progress. |
| **ims** | 🔴 RED | Catastrophic network latency (~2000ms RTT) at the P-CSCF container is causing IMS registration and session setup to fail. |

**IMS evidence:**
- RTT from pcscf to icscf is ~1989ms (from measure_rtt)
- RTT from pcscf to rtpengine is ~2010ms (from measure_rtt)
- icscf:cdp:timeout = 1.0 (from get_nf_metrics)
- icscf:ims_icscf:uar_timeouts = 1.0 (from get_nf_metrics)
- Screener: pcscf:core:rcv_requests_register_rate is 2720.63 (vs 0.08 baseline)

**Suspect components:**

- **pcscf** (high): Direct measurement shows ~2000ms RTT from the pcscf container to its immediate neighbors (icscf, rtpengine), which is orders of magnitude above the normal <1ms. This severe latency is the clear epicenter of the failure, causing the timeouts observed downstream at the I-CSCF.
- **icscf** (low): I-CSCF is reporting Diameter timeouts (cdp:timeout=1, uar_timeouts=1), but its own network links to S-CSCF and HSS are healthy (<1ms RTT). The timeouts are symptomatic of the extreme latency from P-CSCF, which is the component it is waiting on. I-CSCF is a victim, not a cause.

**Investigation hint:** The investigation must focus exclusively on the 'pcscf' container and its host environment. The ~2000ms RTT is not an application-level issue; it points to a severe problem at the container's network layer or the host itself. Recommended steps are to check for CPU starvation, memory exhaustion, or a 'noisy neighbor' container on the same host that could be impacting the Docker network bridge. Probes like 'docker stats' and 'top' on the host are critical. Ignore the errors on other IMS components, as they are downstream effects.

**Tools called:** get_vonr_components, get_network_topology, get_network_status, get_nf_metrics, get_dp_quality_gauges, read_env_config, measure_rtt, compare_to_baseline, check_stack_rules


## Pattern Match (Phase 2)

**❌ Match:** No matching signature found

- **Confidence:** low
- **Failure domain:** unknown
- **Baseline anomalies:** 2 metrics across 2 components


## Investigation Instruction (Phase 3)

> Anomalies detected in IMS layer. Suspect components: `pcscf` (high confidence), `icscf` (low confidence). Catastrophic network latency isolated to the P-CSCF container is causing SIP signaling timeouts.
>
> Your primary focus is the `pcscf` container.
> **FIRST (Hierarchy of Truth: Transport Layer):** Run `measure_rtt` from `pcscf` to its immediate neighbors (`icscf`, `rtpengine`). Confirm the reported ~2000ms RTT. This extreme latency (orders of magnitude above normal <1ms) points to a severe problem at the `pcscf` container's network layer or its host environment.
>
> Do NOT investigate other layers (RAN, Core, Infrastructure are GREEN). The observed `icscf:cdp:timeout` and `icscf:ims_icscf:uar_timeouts` are direct consequences of the P-CSCF's upstream latency and should be ignored for root cause analysis. Do NOT investigate application-level logic within `pcscf` as the transport layer is clearly failing. Focus exclusively on validating the network latency from the `pcscf`.

## Investigation (Phase 4)

> ### Hypothesis Verification
> - Instruction received: The primary directive is to investigate the `pcscf` container and confirm the suspected catastrophic network latency by measuring the round-trip time (RTT) to its immediate neighbors, `icscf` and `rtpengine`.
> - Verdict: CONFIRMED
>
> ### Evidence Chain
> - **Finding**: The `pcscf` container is experiencing catastrophic network latency, with an average round-trip time of approximately 2 seconds to its direct neighbors.
> - **Evidence**:
>     1.  `[EVIDENCE: read_env_config() -> "icscf_ip: 172.22.0.19, rtpengine_ip: 172.22.0.16"]`
>     2.  `[EVIDENCE: measure_rtt("pcscf", "172.22.0.19") -> "rtt min/avg/max/mdev = 1951.883/1968.600/1980.713/12.211 ms"]`
>     3.  `[EVIDENCE: measure_rtt("pcscf", "172.22.0.16") -> "rtt min/avg/max/mdev = 1950.658/2007.593/2040.418/40.416 ms"]`
> - **Significance**: An RTT of ~2000ms is orders of magnitude above the expected sub-millisecond latency in a container network. This extreme delay is sufficient to cause timeouts for any network protocol, including the SIP and Diameter signaling used in the IMS layer. It directly explains the cascading failures reported in the initial analysis.
>
> ### Layer Status
> - **Transport**: RED. Direct measurements confirm catastrophic latency originating from the `pcscf` container. `[EVIDENCE: measure_rtt("pcscf", "172.22.0.19") -> "rtt min/avg/max/mdev = 1951.883/1968.600/1980.713/12.211 ms"]` and `[EVIDENCE: measure_rtt("pcscf", "172.22.0.16") -> "rtt min/avg/max/mdev = 1950.658/2007.593/2040.418/40.416 ms"]`.
> - **Core**: GREEN. The initial analysis showed the core was stable, and the identified issue is isolated to the IMS transport layer. No evidence suggests a core network problem.
> - **Application**: RED. The application layer is failing as a direct consequence of the underlying transport layer failure. Protocols like SIP cannot function with a 2-second packet delay, leading to the timeouts observed at the `icscf`.
>
> ### Root Cause Assessment
> - **Primary cause**: The root cause of the outage is a severe transport layer failure isolated to the `pcscf` container. This container's network interface or its host environment is causing extreme packet latency (~2000ms), which in turn causes timeouts in dependent IMS services.
> - **Confidence**: High
> - **Supporting evidence**:
>     - `[EVIDENCE: measure_rtt("pcscf", "172.22.0.19") -> "rtt min/avg/max/mdev = 1951.883/1968.600/1980.713/12.211 ms"]`
>     - `[EVIDENCE: measure_rtt("pcscf", "172.22.0.16") -> "rtt min/avg/max/mdev = 1950.658/2007.593/2040.418/40.416 ms"]`

## Evidence Validation (Phase 5)

**Verdict:** clean
**Investigator confidence:** high
**Citations:** 14/14 verified

```
Evidence validation: 14/14 citations verified (0 unmatched). Investigator: 7 citations from 2 tool calls.
Verdict: clean. Investigator confidence: high.

Tool calls vs. citations:
  NetworkAnalystAgent:
    ✗ check_stack_rules — called but NOT cited in output
    ✗ compare_to_baseline — called but NOT cited in output
    ✓ get_dp_quality_gauges — called AND cited (1x)
    ✗ get_network_status — called but NOT cited in output
    ✗ get_network_topology — called but NOT cited in output
    ✓ get_nf_metrics — called AND cited (4x)
    ✗ get_vonr_components — called but NOT cited in output
    ✓ measure_rtt — called AND cited (2x)
    ✗ read_env_config — called but NOT cited in output
  InvestigatorAgent:
    ✓ measure_rtt — called AND cited (6x)
    ✓ read_env_config — called AND cited (1x)
```

## Ground Truth

**Failure domain:** ims_signaling  
**Protocol impact:** SIP  
**Affected components:** pcscf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v5-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 161.8s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: The IMS outage is caused by a severe network performance degradation isolated to the P-CSCF container, which is introducing approximately 2000ms of latency and causing SIP signaling to time out.
> - **timeline**:
>     1.  IMS components begin reporting timeouts; specifically, the I-CSCF reports User Authorization Request (UAR) timeouts.
>     2.  Initial analysis rules out failures in the RAN, Core, and Infrastructure layers, which all appear healthy.
>     3.  Direct RTT measurements from the `pcscf` container to its immediate neighbors (`icscf`, `rtpengine`) confirm catastrophic latency, with an average round-trip time of ~2000ms.
>     4.  This transport-layer failure is identified as the root cause, explaining why the I-CSCF is timing out while waiting for responses from the P-CSCF.
> - **root_cause**: The root cause is a transport-layer failure localized to the `pcscf` container. Its network stack is introducing an extreme delay (~2 seconds) on all egress traffic. This latency is far beyond the tolerance of IMS protocols, causing SIP and Diameter messages sent from the `pcscf` to time out before a transaction can complete. This prevents UEs from registering and establishing sessions.
> - **affected_components**:
>     - `pcscf`: Root Cause
>     - `icscf`: Symptomatic
> - **recommendation**: The investigation should focus entirely on the `pcscf` container and its host environment. Verify host-level resource utilization (CPU, memory) to check for starvation. Inspect the container's network interface and any associated Docker network bridges for misconfigurations or policies that could be introducing artificial latency.
> - **confidence**: high
> - **explanation**: The IMS layer is failing because the P-CSCF container has catastrophic network latency. Direct measurements confirm a round-trip time of ~2000ms from `pcscf` to its peers, which is thousands of times higher than normal. This is not an application bug; it is a transport-layer failure preventing SIP messages from being processed in time. The timeouts seen on other components like the I-CSCF are symptoms of this upstream latency, as they are waiting for responses from the malfunctioning P-CSCF.

### Scoring Breakdown

**Overall score: 100%**

**Scorer assessment:** The agent provided an outstanding diagnosis, perfectly identifying the root cause, affected component, severity, and fault type with high confidence, matching all aspects of the simulated failure.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | Yes | The agent correctly identified 'severe network performance degradation isolated to the P-CSCF container, which is introducing approximately 2000ms of latency' and 'transport-layer failure localized to the `pcscf` container. Its network stack is introducing an extreme delay (~2 seconds)' as the root cause, which perfectly matches the simulated failure mode of 'Elevated network latency on the component's interfaces (2000ms delay)' on the P-CSCF. |
| Component overlap | 100% | The agent explicitly named `pcscf` as the 'Root Cause', which is the primary affected component in the simulation. It also correctly identified `icscf` as 'Symptomatic', showing good causal reasoning. |
| Severity correct | Yes | The agent described the impact as an 'IMS outage', 'severe network performance degradation', 'catastrophic latency', and 'extreme delay (~2 seconds)' that 'prevents UEs from registering and establishing sessions'. This accurately reflects the complete service failure caused by the 2000ms latency, which is far beyond the SIP T1 timer of 500ms. |
| Fault type identified | Yes | The agent clearly identified the fault type as 'network performance degradation', 'latency', 'extreme delay', and a 'transport-layer failure', which directly corresponds to the 'Elevated network latency' simulated. |
| Confidence calibrated | Yes | The agent stated 'high' confidence, which is appropriate given the exceptional accuracy and detail of its diagnosis, including specific latency values and supporting evidence from RTT measurements. |

**Ranking position:** #1 — The agent provided a single, clear root cause, which was the correct one.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 111,099 |
| Output tokens | 4,475 |
| Thinking tokens | 11,155 |
| **Total tokens** | **126,729** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| NetworkAnalystAgent | 84,195 | 16 | 5 |
| PatternMatcherAgent | 0 | 0 | 0 |
| InstructionGeneratorAgent | 6,775 | 0 | 1 |
| InvestigatorAgent | 26,230 | 3 | 3 |
| EvidenceValidatorAgent | 0 | 0 | 0 |
| SynthesisAgent | 9,529 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 321.1s
