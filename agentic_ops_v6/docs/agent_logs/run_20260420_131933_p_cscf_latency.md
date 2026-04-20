# Episode Report: P-CSCF Latency

**Agent:** v6  
**Episode ID:** ep_20260420_131408_p_cscf_latency  
**Date:** 2026-04-20T13:14:09.873882+00:00  
**Duration:** 323.5s  

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
- **Nodes with any drift:** 5

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

### Metrics Changes

| Node | Metric | Baseline | Current | Delta |
|------|--------|----------|---------|-------|
| pcscf | script:register_time | 7295.0 | 21555.0 | 14260.0 |
| pcscf | core:rcv_requests_invite | 0.0 | 9.0 | 9.0 |
| pcscf | sl:4xx_replies | 0.0 | 3.0 | 3.0 |
| pcscf | sl:1xx_replies | 48.0 | 59.0 | 11.0 |
| smf | bearers_active | 4.0 | 5.0 | 1.0 |

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 0.93 (threshold: 0.70, trained on 211 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following specific metrics were flagged as the top contributors to the anomaly. These MUST be reflected in your layer ratings:

| Component | Metric | Current | Learned Normal | Severity |
|-----------|--------|---------|---------------|----------|
| derived | pcscf_sip_error_ratio | 0.50 | 0.00 | MEDIUM |
| normalized | upf.gtp_outdatapktn3upf_per_ue | 0.07 | 3.34 | MEDIUM |
| normalized | upf.gtp_indatapktn3upf_per_ue | 0.19 | 3.42 | MEDIUM |
| normalized | pcscf.dialogs_per_ue | 0.00 | 0.57 | LOW |
| derived | upf_activity_during_calls | 1.00 | 0.47 | LOW |

## Event Aggregation (Phase 1)

No events fired during this episode. Either no metric KB triggers matched, or the episode encountered no meaningful state transitions.

## Correlation Analysis (Phase 2)

No events fired — correlation engine had nothing to work with.

## Network Analysis (Phase 3)

**Summary:** IMS registration is failing due to P-CSCF errors and the data plane is broken due to massive packet loss at the UPF, likely caused by a communication failure between P-CSCF and PCF.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | The underlying infrastructure, including all containers and network links between them, appears to be healthy. |
| **ran** | 🟡 YELLOW | The RAN appears to be connected, with 2 UEs attached to the AMF. However, as there is no data flowing, its status is suspect but there is no direct evidence of a fault in the RAN itself. |
| **core** | 🔴 RED | The core data plane is non-functional. The UPF is dropping the vast majority of packets it receives. This is likely the result of missing or incorrect forwarding rules, which could be a downstream effect of the signaling plane failures. |
| **ims** | 🔴 RED | The IMS layer is critical. P-CSCF is reporting a high rate of SIP errors and is unable to establish any dialogs. It is also experiencing a massive number of HTTP client connection failures, which points to a problem with a component it is trying to reach, likely the PCF. |

**CORE evidence:**
- upf.gtp_outdatapktn3upf_per_ue: 0.07 (very low)
- upf.gtp_indatapktn3upf_per_ue: 0.19 (very low)
- UPF outgoing packets (190) is a fraction of incoming packets (5653)

**IMS evidence:**
- pcscf_sip_error_ratio: 0.50
- pcscf.dialogs_per_ue: 0.00
- P-CSCF httpclient:connfail is very high (6670)

**Ranked hypotheses:**

- **`h1`** (fit=0.90, nf=pcf, specificity=specific):
    - **Statement:** P-CSCF is failing to connect to the PCF over the Rx interface, resulting in SIP registration and call setup failures. This prevents the installation of correct QoS rules in the UPF, causing it to drop data plane packets.
    - **Falsification probes:**
        - measure_rtt from pcscf to pcf
        - check pcf logs for rx interface errors
- **`h2`** (fit=0.70, nf=upf, specificity=moderate):
    - **Statement:** The User Plane Function (UPF) is dropping almost all incoming data packets, indicating an internal fault or a misconfiguration of its packet forwarding rules.
    - **Falsification probes:**
        - check UPF logs for errors
        - inspect PFCP session rules on the UPF
- **`h3`** (fit=0.60, nf=icscf, specificity=specific):
    - **Statement:** The I-CSCF is failing to process user registration requests correctly. It has received 88 REGISTER requests but has only received 42 UAR replies, and no LIR replies at all, suggesting a failure in communicating with the HSS.
    - **Falsification probes:**
        - check I-CSCF logs for errors during registration
        - measure_rtt from icscf to pyhss


## Falsification Plans (Phase 4)

**3 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `pcf`)

**Hypothesis:** P-CSCF is failing to connect to the PCF over the Rx interface, resulting in SIP registration and call setup failures. This prevents the installation of correct QoS rules in the UPF, causing it to drop data plane packets.

**Probes (3):**
1. **`measure_rtt`** — from=pcscf, to_ip=pcf
    - *Expected if hypothesis holds:* High latency or 100% packet loss, indicating a network communication issue between P-CSCF and PCF.
    - *Falsifying observation:* Low latency (<5ms) and 0% packet loss, indicating healthy network connectivity.
2. **`search_logs`** — container=pcf, pattern="Rx interface error|connection refused|connection reset|failed to bind|failed to listen"
    - *Expected if hypothesis holds:* PCF logs will show errors related to the Rx interface or connection attempts from P-CSCF.
    - *Falsifying observation:* PCF logs show no errors related to the Rx interface or successful connection establishments.
3. **`search_logs`** — container=pcscf, pattern="Failed to connect to PCF|Rx connection error|PCF unreachable"
    - *Expected if hypothesis holds:* P-CSCF logs will contain entries indicating failed connection attempts or communication issues with the PCF.
    - *Falsifying observation:* P-CSCF logs contain no errors related to PCF communication.

*Notes:* Probes focus on validating network connectivity and application-level errors between P-CSCF and PCF, as well as errors reported by each component about their communication.

### Plan for `h2` (target: `upf`)

**Hypothesis:** The User Plane Function (UPF) is dropping almost all incoming data packets, indicating an internal fault or a misconfiguration of its packet forwarding rules.

**Probes (3):**
1. **`search_logs`** — container=upf, pattern="error|fail|drop|misconfiguration|rule not found"
    - *Expected if hypothesis holds:* UPF logs will contain critical errors related to packet processing, forwarding rules, or explicit packet drops.
    - *Falsifying observation:* UPF logs are clean, showing no significant errors or indications of packet forwarding issues.
2. **`get_dp_quality_gauges`** — window="5m"
    - *Expected if hypothesis holds:* High packet loss rate (close to 100%) and poor data plane quality reported by the UPF.
    - *Falsifying observation:* Low packet loss rate and healthy data plane quality metrics, indicating packets are being forwarded correctly.
3. **`query_prometheus`** — query="upf_pfcp_session_rules_count{nf_name='upf'}"
    - *Expected if hypothesis holds:* Prometheus metric shows zero or very few active PFCP session rules, or metrics indicating misconfigured rules.
    - *Falsifying observation:* Prometheus metric shows an expected number of active and correctly applied PFCP session rules for the established sessions.

*Notes:* Probes aim to verify UPF internal state, log for errors, and directly measure data plane performance to confirm packet dropping.

### Plan for `h3` (target: `icscf`)

**Hypothesis:** The I-CSCF is failing to process user registration requests correctly. It has received 88 REGISTER requests but has only received 42 UAR replies, and no LIR replies at all, suggesting a failure in communicating with the HSS.

**Probes (3):**
1. **`search_logs`** — container=icscf, pattern="HSS communication error|UAR request failed|LIR request failed|Diameter error"
    - *Expected if hypothesis holds:* I-CSCF logs will show errors related to communication with HSS for UAR/LIR requests.
    - *Falsifying observation:* I-CSCF logs show successful Diameter exchanges (UAR/LIR requests and replies) with HSS without errors.
2. **`measure_rtt`** — from=icscf, to_ip=pyhss
    - *Expected if hypothesis holds:* High latency or 100% packet loss between I-CSCF and PyHSS, indicating network connectivity issues.
    - *Falsifying observation:* Low latency (<5ms) and 0% packet loss, indicating healthy network connectivity.
3. **`search_logs`** — container=pyhss, pattern="UAR received|LIR received|UAR failed|LIR failed|Diameter error"
    - *Expected if hypothesis holds:* PyHSS logs will either not show the expected number of UAR/LIR requests, or show errors when processing them or responding.
    - *Falsifying observation:* PyHSS logs show successful reception and processing of UAR/LIR requests and corresponding responses, with no errors.

*Notes:* Probes aim to confirm the communication failure between I-CSCF and HSS, checking network path, I-CSCF's view of HSS, and HSS's reception/processing of requests.


## Parallel Investigators (Phase 5)

**3 sub-Investigator verdict(s):** **2 NOT_DISPROVEN**, **1 DISPROVEN**

### `h1` — ✅ **NOT_DISPROVEN**

**Hypothesis:** P-CSCF is failing to connect to the PCF over the Rx interface, resulting in SIP registration and call setup failures. This prevents the installation of correct QoS rules in the UPF, causing it to drop data plane packets.

**Reasoning:** The hypothesis is NOT_DISPROVEN. The primary evidence is the extremely high RTT (approaching 4 seconds) between the P-CSCF and the PCF, which indicates a severe network or processing bottleneck, effectively making communication impossible. While searches for specific connection error logs in both P-CSCF and PCF were negative, this lack of application-level logs is superseded by the fundamental network-level communication failure shown by the RTT probe.

**Probes executed (3):**
- **measure round-trip-time from pcscf to pcf** ✓ CONSISTENT
    - *Tool:* `measure_rtt("pcscf", "172.22.0.27")`
    - *Observation:* [EVIDENCE: measure_rtt("pcscf", "172.22.0.27") -> "3 packets transmitted, 3 received, 0% packet loss, time 2041ms
rtt min/avg/max/mdev = 2023.127/2987.379/3964.139/792.464 ms, pipe 3"]
    - *Comment:* The observed RTT is astronomically high for a container network, averaging ~3 seconds. This is consistent with the hypothesis that there is a severe communication problem, even though there was no packet loss. The PCF is likely too overloaded to respond in a timely manner.
- **check pcf logs for rx interface errors** ✗ CONTRADICTS
    - *Tool:* `search_logs(containers=["pcf"], pattern="Rx interface error|connection refused|connection reset|failed to bind|failed to listen")`
    - *Observation:* [EVIDENCE: search_logs(containers=["pcf"], pattern="Rx interface error|connection refused|connection reset|failed to bind|failed to listen") -> "No matches for 'Rx interface error|connection refused|connection reset|failed to bind|failed to listen' in containers: pcf"]
    - *Comment:* No errors related to the Rx interface were found in the PCF logs. This contradicts the expectation, but the extreme latency seen in the RTT probe suggests the PCF might be too unresponsive to even generate log messages.
- **check pcscf logs for pcf connection errors** ✗ CONTRADICTS
    - *Tool:* `search_logs(containers=["pcscf"], pattern="Failed to connect to PCF|Rx connection error|PCF unreachable")`
    - *Observation:* [EVIDENCE: search_logs(containers=["pcscf"], pattern="Failed to connect to PCF|Rx connection error|PCF unreachable") -> "No matches for 'Failed to connect to PCF|Rx connection error|PCF unreachable' in containers: pcscf"]
    - *Comment:* No errors indicating a failure to connect to the PCF were found in the P-CSCF logs. This also contradicts the expectation. However, the transport-layer evidence from the RTT probe is a stronger signal of failure than the absence of specific application-layer logs.

### `h2` — ✅ **NOT_DISPROVEN**

**Hypothesis:** The User Plane Function (UPF) is dropping almost all incoming data packets, indicating an internal fault or a misconfiguration of its packet forwarding rules.

**Reasoning:** The investigation confirms the central claim of the hypothesis. Data plane quality gauges show the UPF is dropping approximately two-thirds of its incoming packets. While the UPF logs show no internal errors, the Prometheus query for PFCP session rules returned no data, which, combined with the observed packet loss, strongly implies the forwarding rules are missing. This aligns with the 'misconfiguration of packet forwarding rules' aspect of the hypothesis.

**Probes executed (3):**
- **UPF logs will contain critical errors related to packet processing, forwarding rules, or explicit packet drops.** ✗ CONTRADICTS
    - *Tool:* `search_logs(containers=['upf'], pattern='error|fail|drop|misconfiguration|rule not found', since='5m')`
    - *Observation:* [EVIDENCE: search_logs("containers=['upf'], pattern='error|fail|drop|misconfiguration|rule not found', since='5m'") -> "No matches for 'error|fail|drop|misconfiguration|rule not found' in containers: upf"]
    - *Comment:* The UPF logs are clean, which argues against an 'internal fault'. However, a lack of rules might not be logged as an error, so this doesn't fully disprove the hypothesis.
- **High packet loss rate (close to 100%) and poor data plane quality reported by the UPF.** ✓ CONSISTENT
    - *Tool:* `get_dp_quality_gauges(window_seconds=300)`
    - *Observation:* [EVIDENCE: get_dp_quality_gauges("window_seconds=300") -> "UPF:\n    in  packets/sec: 0.3\n    out packets/sec: 0.1\n    in  throughput : 0.09 KB/s\n    out throughput : 0.03 KB/s"]
    - *Comment:* The UPF is dropping about 67% of its traffic (0.1 out / 0.3 in), which is a massive packet loss rate and consistent with the hypothesis.
- **Prometheus metric shows zero or very few active PFCP session rules, or metrics indicating misconfigured rules.** ✓ CONSISTENT
    - *Tool:* `query_prometheus(query='upf_pfcp_session_rules_count{nf_name=\'upf\'}')`
    - *Observation:* [EVIDENCE: query_prometheus("query='upf_pfcp_session_rules_count{nf_name=\'upf\'}'") -> "No results for query 'upf_pfcp_session_rules_count{nf_name='upf'}'. The metric may not exist or have no data."]
    - *Comment:* The query returning no data, in conjunction with the observed packet loss, strongly suggests that there are no PFCP session rules installed on the UPF. Without rules, the UPF's default behavior is to drop packets.

### `h3` — ❌ **DISPROVEN**

**Hypothesis:** The I-CSCF is failing to process user registration requests correctly. It has received 88 REGISTER requests but has only received 42 UAR replies, and no LIR replies at all, suggesting a failure in communicating with the HSS.

**Reasoning:** Probes directly contradict the claim of a communication failure between I-CSCF and HSS. The I-CSCF's logs show no errors related to HSS communication, and a network RTT test confirms the connection is perfectly healthy. The metric discrepancy cited in the hypothesis does not appear to be caused by a communication failure.

**Probes executed (3):**
- **I-CSCF logs will show errors related to communication with HSS for UAR/LIR requests.** ✗ CONTRADICTS
    - *Tool:* `search_logs(containers=['icscf'], pattern='HSS communication error|UAR request failed|LIR request failed|Diameter error')`
    - *Observation:* [EVIDENCE: search_logs("icscf", "HSS communication error|UAR request failed|LIR request failed|Diameter error") -> "No matches for 'HSS communication error|UAR request failed|LIR request failed|Diameter error' in containers: icscf"]
    - *Comment:* The absence of any Diameter or HSS communication errors in the I-CSCF logs falsifies the expectation that it is failing to communicate with the HSS.
- **High latency or 100% packet loss between I-CSCF and PyHSS, indicating network connectivity issues.** ✗ CONTRADICTS
    - *Tool:* `measure_rtt(container='icscf', target_ip='172.22.0.18')`
    - *Observation:* [EVIDENCE: measure_rtt("icscf", "172.22.0.18") -> "3 packets transmitted, 3 received, 0% packet loss, time 2041ms\nrtt min/avg/max/mdev = 0.090/0.167/0.294/0.090 ms"]
    - *Comment:* The network path from I-CSCF to the HSS (PyHSS) is healthy, with sub-millisecond latency and zero packet loss. This directly contradicts the hypothesis of a communication failure.
- **PyHSS logs will either not show the expected number of UAR/LIR requests, or show errors when processing them or responding.** ~ AMBIGUOUS
    - *Tool:* `search_logs(containers=['pyhss'], pattern='UAR received|LIR received|UAR failed|LIR failed|Diameter error')`
    - *Observation:* [EVIDENCE: search_logs("pyhss", "UAR received|LIR received|UAR failed|LIR failed|Diameter error") -> "No matches for 'UAR received|LIR received|UAR failed|LIR failed|Diameter error' in containers: pyhss"]
    - *Comment:* The PyHSS logs show no recent UAR/LIR requests being received or processed. While not a direct contradiction on its own, when combined with the clean I-CSCF logs and healthy network, it suggests the I-CSCF is not sending the requests at all, rather than failing to communicate them.

**Alternative suspects:** pcscf


## Evidence Validation (Phase 6)

**Overall verdict:** clean
**Overall confidence:** high

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 4 | 3/3 | clean | high |
| `InvestigatorAgent_h2` | 3 | 3/3 | clean | high |
| `InvestigatorAgent_h3` | 4 | 3/3 | clean | high |


## Ground Truth

**Failure domain:** ims_signaling  
**Protocol impact:** SIP  
**Affected components:** pcscf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v6-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 174.8s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: IMS registration is failing and the data plane is broken due to a severe communication failure between the P-CSCF and the PCF, which prevents the installation of packet forwarding rules on the UPF.
> - **timeline**:
>     1. The communication path between the P-CSCF and the PCF becomes critically degraded, with measured round-trip times averaging ~3 seconds.
>     2. Due to this extreme latency, the P-CSCF is unable to successfully establish Rx sessions with the PCF, causing SIP registration requests to fail.
>     3. Without policy authorization from the PCF, the core network cannot install the necessary PFCP session rules on the User Plane Function (UPF).
>     4. The UPF, lacking forwarding rules, defaults to dropping approximately 67% of incoming user plane packets, rendering the data plane non-functional.
> - **root_cause**: A severe communication failure between the P-CSCF and the PCF over the Rx interface, making the PCF effectively unreachable. The investigation points to the PCF being unresponsive as the primary issue. The `primary_suspect_nf` is the **pcf**.
> - **affected_components**:
>     - `pcf`: Root Cause
>     - `pcscf`: Secondary
>     - `upf`: Symptomatic
> - **recommendation**: The operator should investigate the health of the PCF to determine the cause of its unresponsiveness. Specifically, verify the resource utilization (CPU, memory) of the `pcf` container and inspect its logs for signs of processing overload or internal deadlocks that would explain the extreme response latency.
> - **confidence**: medium
> - **explanation**: The investigation disproved the hypothesis that the I-CSCF was failing to contact the HSS (`h3`), as network connectivity was confirmed to be healthy. Two hypotheses remain (`h1`, `h2`), which together describe a cascading failure. The investigation of `h1` confirmed a critical communication failure between the P-CSCF and PCF, evidenced by a ~3-second RTT. This failure prevents the PCF from authorizing QoS rules. The investigation of `h2` confirmed the *result* of this failure: the UPF has no PFCP session rules installed and is dropping the majority of its packets. The root cause is the PCF's unresponsiveness. Confidence is medium because while this causal chain is strongly supported, the underlying reason for the PCF's unresponsiveness has not yet been determined.

### Scoring Breakdown

**Overall score: 60%**

**Scorer assessment:** The agent correctly identified the symptoms, severity, fault type, and affected layers, but misattributed the root cause of the latency from the P-CSCF to the PCF.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | No | The simulated failure was 2000ms latency on the P-CSCF itself. The agent diagnosed a 'severe communication failure between the P-CSCF and the PCF' and identified the PCF as the primary suspect due to its unresponsiveness. While the observed high RTT between P-CSCF and PCF is a symptom of P-CSCF's latency, the agent incorrectly attributes the unresponsiveness to the PCF rather than the P-CSCF being the source of the delay. |
| Component overlap | 100% | The primary affected component is 'pcscf'. The agent listed 'pcscf' as a 'Secondary' affected component, thus it was named. |
| Severity correct | Yes | The simulated failure involved 2000ms latency, leading to severe delays and registration failures. The agent described a 'severe communication failure', 'critically degraded' path with '~3 seconds RTT', 'extreme latency', 'SIP registration requests to fail', and a 'data plane non-functional' with '67% packet drop', which accurately reflects a severe degradation leading to functional impact. |
| Fault type identified | Yes | The simulated failure is latency. The agent correctly identified 'extreme latency', 'critically degraded communication path', and 'unresponsiveness' (a consequence of extreme latency/timeouts) as the fault type. |
| Layer accuracy | Yes | The 'pcscf' belongs to the 'ims' layer. The agent correctly flagged the 'ims' layer as 'red' and provided P-CSCF specific evidence for its status. |
| Confidence calibrated | Yes | The agent's diagnosis correctly identified many symptoms, the affected layers, and the type of fault (latency/unresponsiveness) in the P-CSCF-PCF interaction. While it misattributed the ultimate root cause component, it stated 'Confidence is medium because while this causal chain is strongly supported, the underlying reason for the PCF's unresponsiveness has not yet been determined.' This acknowledgment of uncertainty makes the medium confidence appropriate for a diagnosis that is partially correct but misses the exact root cause. |

**Ranking:** The agent explicitly identified 'pcf' as the 'primary_suspect_nf' and the 'primary issue' in its root cause summary. The actual root cause component ('pcscf') was listed as 'Secondary' or not as the primary suspect.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 92,828 |
| Output tokens | 5,599 |
| Thinking tokens | 18,896 |
| **Total tokens** | **117,323** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| EventAggregator | 0 | 0 | 0 |
| CorrelationAnalyzer | 0 | 0 | 0 |
| NetworkAnalystAgent | 22,442 | 3 | 4 |
| InstructionGeneratorAgent | 13,059 | 1 | 2 |
| InvestigatorAgent_h1 | 18,379 | 4 | 3 |
| InvestigatorAgent_h2 | 10,707 | 3 | 2 |
| InvestigatorAgent_h3 | 46,381 | 4 | 5 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 6,355 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 323.5s

---

## Post-Run Analysis

The overall structure of per-hypothesis parallel falsification is a real improvement — all three Investigators invoked their tools (no 0-call hallucinations) and cited evidence honestly. But the diagnosis misidentified the root cause (named `pcf` instead of `pcscf`) and failed to disprove the UPF hypothesis. Three concrete reasoning gaps explain both errors.

### Gap 1 — UPF hypothesis not disproven

Investigator `h2` cited two pieces of "evidence":

1. **"67% packet loss"** from `get_dp_quality_gauges` (0.3 in / 0.1 out packets/sec).
   - *Flaw:* Those numbers are tiny in absolute terms — 0.3 packets/sec is *low activity*, not packet loss. The investigator treated a ratio as a drop rate without a baseline. In this real failure, registrations fail upstream so almost no bearer traffic reaches the UPF — hence low throughput on both sides.
2. **`upf_pfcp_session_rules_count` returned no data** → "no rules installed."
   - *Flaw:* The Prometheus response even said *"The metric may not exist or have no data."* The investigator chose the "no rules" reading when the safer read is "metric doesn't exist in this stack." No cross-check against PFCP session logs or UPF state.
3. UPF logs were clean (contradicting evidence) — dismissed as "a lack of rules might not be logged."

There is no falsification probe in the plan for **"is this low activity upstream-starved, or real drops?"** (e.g. check whether PFCP sessions were ever established, or whether P-CSCF completed any REGISTER).

### Gap 2 — PCF named as root cause

RTT probe from pcscf → pcf returned **~3s, 0% packet loss**. Investigator `h1` read that as "PCF is overloaded."

The flaw is geometric: **netem on P-CSCF adds latency to every packet crossing P-CSCF's interface in either direction**. Any RTT measured *from* P-CSCF will show the inflation, regardless of the destination. To localize the delay you need the *reverse* or *bypass* probe:

- `measure_rtt` from **another container** (e.g. icscf, pcf) **to pcscf's IP**
- or `measure_rtt` from pcscf → a known-good target (e.g. dns, mongo) — if *all* destinations look slow, P-CSCF is the source

Neither cross-check appeared in h1's plan. The "hierarchy of truth" rule in the Investigator prompt says transport beats application, but it doesn't teach the triangulation needed to identify *which endpoint* the transport problem sits on.

Both PCF and P-CSCF logs were clean of Rx errors — that's an important negative signal (a truly overloaded PCF usually surfaces timeouts or Diameter errors somewhere) — but the investigator explicitly hand-waved it away as "PCF too unresponsive to log."

### Gap 3 — Upstream framing biased the whole run

Phase 1 fired **zero events**. The metric KB has no trigger for the very clear signature of this fault — `pcscf.script:register_time` jumped 7295 → 21555 (roughly 3×). Without that event, the NA had to reason from raw anomaly flags, which pointed at UPF packet ratios (a downstream symptom) and P-CSCF error ratio. NA's summary already committed to "data plane broken due to massive packet loss at UPF … caused by P-CSCF↔PCF failure" — a causal chain the investigators then went looking to *confirm* rather than falsify.

### Fix plan

1. **Investigator prompt (Hierarchy of truth)** — add a latency-localization rule: a single directional probe (RTT from A→B) is ambiguous about which endpoint owns the problem. Attribution to B requires triangulation (A→C, X→A).
2. **IG prompt (Plan construction)** — when a plan measures a directional property between two components, it must include at least one triangulation probe that isolates which side is degraded.
3. **Metric KB** — add generalizable latency triggers for `script:*_time` across IMS NFs (register/invite processing time), so the event store fires when *any* NF's transaction time inflates, not just when cumulative error ratios rise.
4. **NA prompt (Evidence interpretation)** — teach the distinction between *low absolute activity* (upstream starvation) and *low ratio/drop rate* (local fault). Ratio deltas at near-zero absolute volume mean the caller never sent work, not that the callee dropped it.

These are generalizable fixes, not case-specific patches — they apply to any latency/partition/overload fault on any NF, not only P-CSCF.
