# Episode Report: IMS Network Partition

**Agent:** v6  
**Episode ID:** ep_20260423_202953_ims_network_partition  
**Date:** 2026-04-23T20:29:55.486808+00:00  
**Duration:** 296.0s  

---

## Scenario

**Category:** network  
**Blast radius:** multi_nf  
**Description:** Partition the P-CSCF from both the I-CSCF and S-CSCF using iptables DROP rules. SIP signaling between the edge proxy and the core IMS is completely severed. Tests IMS behavior under a network split.

## Faults Injected

- **network_partition** on `pcscf` — {'target_ip': '172.22.0.19'}
- **network_partition** on `pcscf` — {'target_ip': '172.22.0.20'}

## Baseline (Pre-Fault)

Stack phase before injection: **ready**
All containers running at baseline.

## Fault Propagation Verification

**Verdict:** ✅ `confirmed`

- **Wait:** 0s
- **Actual elapsed:** 0.0s
- **Nodes with significant deltas:** 1
- **Nodes with any drift:** 3

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

**Summary:** The network is experiencing intermittent control plane issues, with the most significant symptom being a high rate of connection failures at the P-CSCF, likely related to the RTPEngine, and Diameter timeouts at the I-CSCF when communicating with the HSS.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** |   |  |
| **ran** | 🟢 GREEN | No RAN anomalies were detected. |
| **core** | 🟡 YELLOW | The core network shows some signs of issues, but the data plane appears to be functioning correctly based on recent quality gauges. The main concerns are in the control plane. |
| **ims** | 🔴 RED | The IMS layer is showing multiple anomalies, including a very high number of HTTP connection failures at the P-CSCF, timeouts at the I-CSCF when communicating with the HSS, and high response times at the S-CSCF. The RTPEngine also reports a very high average end-to-end round trip time. |

**CORE evidence:**
- upf.fivegs_ep_n3_gtp_indatapktn3upf
- upf.fivegs_ep_n3_gtp_outdatapktn3upf

**IMS evidence:**
- pcscf.httpclient:connfail
- icscf.cdp:timeout
- icscf.ims_icscf:lir_timeouts
- icscf.ims_icscf:uar_timeouts
- scscf.ims_auth:mar_avg_response_time
- scscf.ims_registrar_scscf:sar_avg_response_time
- rtpengine.average_end_to_end_round_trip_time

**Ranked hypotheses:**

- **`h1`** (fit=0.90, nf=pcscf, specificity=specific):
    - **Statement:** The P-CSCF is experiencing a high rate of connection failures when communicating with the RTPEngine for media session management. This is strongly indicated by the extremely high `httpclient:connfail` metric on the P-CSCF. While recent packet loss on the data plane is zero, the very high average round-trip time on the RTPEngine suggests network-level latency issues that could cause control-plane timeouts between P-CSCF and RTPEngine.
    - **Supporting events:** `pcscf.httpclient:connfail`, `rtpengine.average_end_to_end_round_trip_time`
    - **Falsification probes:**
        - Inspect the P-CSCF logs for errors related to connecting to the RTPEngine.
        - Obtain the IP of the RTPEngine and measure RTT from the P-CSCF container to the RTPEngine IP. A high RTT would confirm a network latency issue.
        - Check the RTPEngine logs for any error messages corresponding to connection attempts from the P-CSCF.
- **`h2`** (fit=0.70, nf=pyhss, specificity=moderate):
    - **Statement:** The HSS is periodically unresponsive or slow, causing Diameter timeouts at the I-CSCF and high response times at the S-CSCF. This affects IMS registration and subscriber authentication. The issue appears to be intermittent or specific to the control plane, as the data plane seems healthy.
    - **Supporting events:** `icscf.cdp:timeout`, `icscf.ims_icscf:lir_timeouts`, `icscf.ims_icscf:uar_timeouts`, `scscf.ims_auth:mar_avg_response_time`, `scscf.ims_registrar_scscf:sar_avg_response_time`
    - **Falsification probes:**
        - Check the CPU and memory utilization of the HSS container (`pyhss`).
        - Obtain the IP of the HSS (`pyhss`) and measure RTT from the I-CSCF container. High RTT would confirm a network or HSS issue.
        - Inspect the HSS logs for any errors or long-running queries during the periods corresponding to I-CSCF timeouts.
- **`h3`** (fit=0.50, nf=scp, specificity=vague):
    - **Statement:** A control plane issue is causing intermittent connectivity problems between various network functions. This is suggested by the timeouts at the I-CSCF and the high connection failures at the P-CSCF. The issue is not affecting the data plane throughput or loss as shown by the `get_dp_quality_gauges`.
    - **Supporting events:** `icscf.cdp:timeout`, `pcscf.httpclient:connfail`
    - **Falsification probes:**
        - Inspect the logs of the SCP for any errors or dropped connections.
        - Check the metrics of the SCP for any signs of overload or high processing times.


## Falsification Plans (Phase 4)

*No output produced.*

## Parallel Investigators (Phase 5)

**3 sub-Investigator verdict(s):** **3 INCONCLUSIVE**

### `h1` — ❓ **INCONCLUSIVE**

**Hypothesis:** The P-CSCF is experiencing a high rate of connection failures when communicating with the RTPEngine for media session management. This is strongly indicated by the extremely high `httpclient:connfail` metric on the P-CSCF. While recent packet loss on the data plane is zero, the very high average round-trip time on the RTPEngine suggests network-level latency issues that could cause control-plane timeouts between P-CSCF and RTPEngine.

**Reasoning:** No falsification plan was generated for this hypothesis.

### `h2` — ❓ **INCONCLUSIVE**

**Hypothesis:** The HSS is periodically unresponsive or slow, causing Diameter timeouts at the I-CSCF and high response times at the S-CSCF. This affects IMS registration and subscriber authentication. The issue appears to be intermittent or specific to the control plane, as the data plane seems healthy.

**Reasoning:** No falsification plan was generated for this hypothesis.

### `h3` — ❓ **INCONCLUSIVE**

**Hypothesis:** A control plane issue is causing intermittent connectivity problems between various network functions. This is suggested by the timeouts at the I-CSCF and the high connection failures at the P-CSCF. The issue is not affecting the data plane throughput or loss as shown by the `get_dp_quality_gauges`.

**Reasoning:** No falsification plan was generated for this hypothesis.


## Evidence Validation (Phase 6)

**Overall verdict:** severe
**Overall confidence:** none

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 0 | 0/0 | severe | none |
|  |  |  |  | *ZERO tool calls — all citations fabricated* |
| `InvestigatorAgent_h2` | 0 | 0/0 | severe | none |
|  |  |  |  | *ZERO tool calls — all citations fabricated* |
| `InvestigatorAgent_h3` | 0 | 0/0 | severe | none |
|  |  |  |  | *ZERO tool calls — all citations fabricated* |


## Ground Truth

**Failure domain:** ims_signaling  
**Protocol impact:** SIP  
**Affected components:** pcscf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v6-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 151.5s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: The IMS layer is experiencing significant control plane failures, manifesting as connection timeouts between the P-CSCF and RTPEngine, and between the I-CSCF and HSS.
> - **timeline**:
>     1.  The P-CSCF begins reporting a very high rate of HTTP connection failures (`pcscf.httpclient:connfail`).
>     2.  The RTPEngine reports a very high average end-to-end round trip time (`rtpengine.average_end_to_end_round_trip_time`).
>     3.  The I-CSCF experiences Diameter timeouts when communicating with the HSS (`icscf.cdp:timeout`, `icscf.ims_icscf:uar_timeouts`).
>     4.  The S-CSCF observes high average response times for authentication and registration requests to the HSS (`scscf.ims_auth:mar_avg_response_time`, `scscf.ims_registrar_scscf:sar_avg_response_time`).
> - **root_cause**: The root cause is unconfirmed, but the two most plausible, unverified hypotheses point to either a network-level latency issue causing connection failures between the P-CSCF and the RTPEngine (primary suspect `pcscf` / `rtpengine`) or the HSS (`pyhss`) being periodically unresponsive and causing timeouts for its clients.
> - **affected_components**:
>     - `pcscf`: Symptomatic / Possible Root Cause
>     - `icscf`: Symptomatic
>     - `scscf`: Symptomatic
>     - `pyhss`: Symptomatic / Possible Root Cause
>     - `rtpengine`: Symptomatic / Possible Root Cause
> - **recommendation**: Manual investigation is required to validate the top hypotheses. First, investigate the P-CSCF/RTPEngine link by inspecting the P-CSCF logs for errors related to connecting to the RTPEngine and measuring the network round-trip time (RTT) from the P-CSCF to the RTPEngine. Concurrently, investigate the HSS by checking the CPU and memory utilization of the `pyhss` container and inspecting its logs for any errors or long-running queries that correspond to the I-CSCF timeouts.
> - **confidence**: low
> - **explanation**: The initial analysis produced three hypotheses, focused on IMS control plane issues. However, the automated investigation phase was unable to confirm or disprove any of them, resulting in INCONCLUSIVE verdicts for all. Critically, the Evidence Validator reported a 'severe' failure, noting that the automated investigators failed to execute any diagnostic commands to gather evidence. This requires downgrading confidence to 'low'. The two most likely but unverified causes are a connectivity failure between the P-CSCF and the RTPEngine, and periodic unresponsiveness from the HSS. Manual verification of the recommended steps is necessary to isolate the true root cause.

### Scoring Breakdown

**Overall score: 50%**

**Scorer assessment:** The agent correctly identified the severity, fault type, and affected layer, and its confidence was well-calibrated. However, it failed to pinpoint the specific root cause (P-CSCF network partition from I/S-CSCF) and was ambiguous about the primary affected component.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | No | The simulated failure was an IMS network partition, specifically severing SIP signaling between the P-CSCF and both the I-CSCF and S-CSCF. The agent's primary hypotheses for the root cause were a network-level latency issue between P-CSCF and RTPEngine, or an unresponsive HSS. Neither of these accurately describes the specific network partition between P-CSCF and the IMS core control plane components (I/S-CSCF). |
| Component overlap | 50% | The primary affected component in the simulated failure is the P-CSCF, which was partitioned. The agent lists 'pcscf' as 'Symptomatic / Possible Root Cause' in its 'affected_components' and as a 'primary suspect' in one of its two main hypotheses. This indicates recognition of the P-CSCF's involvement and potential causal role. However, it also lists 'pyhss' and 'rtpengine' as 'Possible Root Cause' and does not clearly identify the P-CSCF as the sole root cause or the specific nature of its failure (partition from I/S-CSCF). |
| Severity correct | Yes | The simulated failure involved 'completely severed' SIP signaling and new REGISTER/INVITE failures, indicating a complete outage for new services. The agent diagnosed 'significant control plane failures,' 'very high rate of HTTP connection failures,' and 'Diameter timeouts,' which are consistent with a severe impact on service. |
| Fault type identified | Yes | The simulated failure was a 'network partition' leading to 'SIP signaling severed.' The agent identified 'network-level latency issue causing connection failures' and 'timeouts,' which are observable fault types consistent with a network connectivity problem or unreachability. |
| Layer accuracy | Yes | The P-CSCF belongs to the 'ims' layer. The agent's network analysis correctly rated the 'ims' layer as 'red' and provided relevant evidence from P-CSCF and other IMS components. |
| Confidence calibrated | Yes | The agent explicitly stated 'low' confidence and that the root cause was 'unconfirmed' because automated investigations failed to confirm or disprove its hypotheses. Given that the diagnosis missed the actual root cause and was ambiguous, this low confidence is well-calibrated. |

**Ranking:** The agent presented two primary hypotheses for the root cause, neither of which correctly identified the simulated network partition between P-CSCF and I/S-CSCF.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 66,201 |
| Output tokens | 1,943 |
| Thinking tokens | 11,707 |
| **Total tokens** | **79,851** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| EventAggregator | 0 | 0 | 0 |
| CorrelationAnalyzer | 0 | 0 | 0 |
| NetworkAnalystAgent | 65,197 | 5 | 6 |
| InstructionGeneratorAgent | 9,861 | 0 | 1 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 4,793 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 296.0s
