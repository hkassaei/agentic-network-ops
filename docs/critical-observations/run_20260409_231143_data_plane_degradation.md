# Episode Report: Data Plane Degradation

**Agent:** v5  
**Episode ID:** ep_20260409_230517_data_plane_degradation  
**Date:** 2026-04-09T23:05:17.703543+00:00  
**Duration:** 385.3s  

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

**Verdict:** ✅ `confirmed`

- **Wait:** 0s
- **Actual elapsed:** 0.0s
- **Nodes with significant deltas:** 4
- **Nodes with any drift:** 6

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

### Metrics Changes

| Node | Metric | Baseline | Current | Delta |
|------|--------|----------|---------|-------|
| pcscf | httpclient:connok | 0.0 | 8.0 | 8.0 |
| pcscf | core:rcv_requests_bye | 0.0 | 9.0 | 9.0 |
| pcscf | sl:1xx_replies | 5.0 | 26.0 | 21.0 |
| pcscf | script:register_time | 750.0 | 14861.0 | 14111.0 |
| pcscf | dialog_ng:active | 0.0 | 2.0 | 2.0 |
| pcscf | script:register_success | 2.0 | 9.0 | 7.0 |
| pcscf | core:rcv_requests_invite | 0.0 | 6.0 | 6.0 |
| pcscf | core:rcv_requests_options | 80.0 | 105.0 | 25.0 |
| pcscf | httpclient:connfail | 81.0 | 118.0 | 37.0 |
| pcscf | core:rcv_requests_register | 5.0 | 23.0 | 18.0 |
| pcscf | dialog_ng:processed | 0.0 | 6.0 | 6.0 |
| rtpengine | sum_of_all_packet_loss_values_sampled | 0.0 | 116.0 | 116.0 |
| rtpengine | packet_loss_standard_deviation | 0.0 | 5.0 | 5.0 |
| rtpengine | sum_of_all_packet_loss_square_values_sampled | 0.0 | 6856.0 | 6856.0 |
| rtpengine | total_timed_out_sessions_via_timeout | 5.0 | 6.0 | 1.0 |
| rtpengine | total_number_of_1_way_streams | 0.0 | 1.0 | 1.0 |
| scscf | ims_registrar_scscf:sar_replies_response_time | 212.0 | 982.0 | 770.0 |
| scscf | cdp:replies_received | 4.0 | 19.0 | 15.0 |
| scscf | dialog_ng:active | 0.0 | 2.0 | 2.0 |
| scscf | ims_registrar_scscf:sar_replies_received | 2.0 | 9.0 | 7.0 |
| scscf | ims_auth:mar_replies_response_time | 269.0 | 1275.0 | 1006.0 |
| scscf | core:rcv_requests_invite | 0.0 | 6.0 | 6.0 |
| scscf | cdp:replies_response_time | 481.0 | 2257.0 | 1776.0 |
| scscf | core:rcv_requests_register | 4.0 | 19.0 | 15.0 |
| scscf | ims_auth:mar_replies_received | 2.0 | 10.0 | 8.0 |
| scscf | ims_registrar_scscf:accepted_regs | 2.0 | 9.0 | 7.0 |
| scscf | dialog_ng:processed | 0.0 | 6.0 | 6.0 |
| smf | bearers_active | 4.0 | 6.0 | 2.0 |

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 1.00 (threshold: 0.70, trained on 50 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following specific metrics were flagged as the top contributors to the anomaly. These MUST be reflected in your layer ratings:

| Component | Metric | Current | Learned Normal | Severity |
|-----------|--------|---------|---------------|----------|
| pcscf | httpclient:connfail_rate | 1661.44 | 0.27 | HIGH |
| pcscf | sl:1xx_replies_rate | 2076.80 | 0.12 | HIGH |
| scscf | ims_registrar_scscf:accepted_regs_rate | 830.72 | 0.04 | HIGH |
| pcscf | core:rcv_requests_invite_rate | 830.72 | 0.04 | HIGH |
| scscf | core:rcv_requests_invite_rate | 830.72 | 0.04 | HIGH |
| icscf | cdp:replies_received_rate | 830.72 | 0.06 | HIGH |
| scscf | cdp:replies_received_rate | 1246.08 | 0.08 | HIGH |
| pcscf | core:rcv_requests_register_rate | 1246.08 | 0.08 | HIGH |
| icscf | core:rcv_requests_register_rate | 1246.08 | 0.08 | HIGH |
| scscf | core:rcv_requests_register_rate | 1246.08 | 0.08 | HIGH |

## Network Analysis (Phase 1)

**Summary:** The network is experiencing a critical failure in the IMS layer, causing a widespread signaling storm, while the RAN and 5G Core layers remain healthy.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | All infrastructure components are running and connected. |
| **ran** | 🟢 GREEN | gNB is connected and UEs are attached. |
| **core** | 🟢 GREEN | The 5G Core is stable and processing user sessions. |
| **ims** | 🔴 RED | Critical IMS failure: I-CSCF is timing out on Diameter requests to the HSS, causing a cascading signaling storm across all CSCFs. |

**IMS evidence:**
- Anomaly Screener: pcscf httpclient:connfail_rate is 1661.44 (vs 0.27 normal)
- Anomaly Screener: Multiple HIGH severity alerts on pcscf, icscf, and scscf rates.
- icscf: cdp:timeout = 7.0 (expected: 0)
- icscf: ims_icscf:lir_timeouts = 3.0 (expected: 0)
- icscf: ims_icscf:uar_timeouts = 4.0 (expected: 0)
- pcscf: httpclient:connfail = 123.0

**Suspect components:**

- **pyhss** (high): The I-CSCF is reporting multiple Diameter timeouts (cdp:timeout=7, lir_timeouts=3, uar_timeouts=4) when communicating with the HSS. This indicates the HSS is likely unresponsive or slow, making it the probable root cause of the entire signaling storm.
- **icscf** (medium): It is the component directly experiencing and reporting the Diameter timeouts. While it's likely a victim of the HSS issue, its logs are critical to confirming the problem, and it is a key part of the failure chain.
- **pcscf** (medium): Flagged by the anomaly screener as the epicenter of the statistical deviation with a very high `httpclient:connfail_rate`. This is a significant symptom, likely a downstream effect of the HSS-induced signaling storm, possibly related to Rx interface communication with the PCF under load.

**Investigation hint:** The investigation must prioritize the IMS layer. The primary suspect is the HSS (`pyhss`), which appears to be failing to respond to Diameter queries from the I-CSCF, triggering a cascade of timeouts and retries throughout the signaling path. Start by examining the `pyhss` container's logs and internal health for any errors or performance bottlenecks. Concurrently, inspect `icscf` logs to confirm the details of the Diameter UAR/LIR timeout errors. Finally, analyze `pcscf` logs to understand the high rate of `httpclient:connfail` errors, which are likely a secondary symptom of the core HSS problem.

**Tools called:** get_vonr_components, get_network_topology, get_network_status, get_nf_metrics, get_dp_quality_gauges, read_env_config, measure_rtt, compare_to_baseline, check_stack_rules


## Pattern Match (Phase 2)

**❌ Match:** No matching signature found

- **Confidence:** low
- **Failure domain:** unknown
- **Baseline anomalies:** 5 metrics across 4 components


## Investigation Instruction (Phase 3)

> INVESTIGATE: Critical failure in the IMS layer, specifically a widespread signaling storm. The RAN and 5G Core layers are GREEN — do NOT investigate them.
>
> The primary suspect is the `pyhss` (HSS), which appears to be failing to respond to Diameter queries from the I-CSCF, triggering a cascade of timeouts and retries throughout the signaling path. Secondary suspects are `icscf` and `pcscf` due to cascading effects.
>
> **FIRST, check transport-layer connectivity and latency for the primary suspect:**
> Run `measure_rtt` from `pyhss` to `icscf`.
>
> **THEN, investigate the IMS layer components (Transport > Core > Application):**
> 1.  **`pyhss` (HSS):** Examine container logs and internal health (e.g., resource usage, application state) for any errors, performance bottlenecks, or indications of unresponsiveness.
> 2.  **`icscf`:** Inspect logs to confirm the reported `ims_icscf:lir_timeouts` (3.0) and `ims_icscf:uar_timeouts` (4.0) errors, and look for associated Diameter request failures towards the HSS.
> 3.  **`pcscf`:** Analyze logs to understand the high `httpclient:connfail` (142.0) events. This is likely a secondary symptom of the HSS-induced signaling storm, possibly related to Rx interface communication with the PCF under load.

## Investigation (Phase 4)

> ### Hypothesis Verification
> - **Instruction received:** Investigate a critical failure in the IMS layer, suspecting the `pyhss` is unresponsive to Diameter queries from the `icscf`. The primary instruction was to first check transport-layer connectivity and then investigate the application logs of `pyhss`, `icscf`, and `pcscf`.
> - **Verdict:** PARTIALLY CONFIRMED. The failure is indeed in the IMS layer, centered around the Diameter communication between `icscf` and `pyhss`. However, the root cause does not appear to be an unresponsive `pyhss` or a transport-layer failure, but rather the state of the Diameter peer connection on the `icscf` itself.
>
> ### Evidence Chain
> - **Finding**: Transport-layer connectivity between the `icscf` and the primary suspect `pyhss` is healthy, with a round-trip time of approximately 0.1ms. This rules out network latency or packet loss as the cause of the timeouts.
> - **Evidence**: `[EVIDENCE: measure_rtt("icscf", "172.22.0.18") -> "rtt min/avg/max/mdev = 0.095/0.101/0.111/0.007 ms"]`
> - **Significance**: This finding contradicts the initial hypothesis that the HSS is unreachable or slow to respond due to a network issue. The problem lies at a higher layer.
>
> - **Finding**: The `pyhss` container logs show no signs of error, unresponsiveness, or performance bottlenecks. The logs indicate normal database and HTTP web UI activity.
> - **Evidence**: `[EVIDENCE: read_container_logs("pyhss", since_seconds=300) -> "172.22.0.1 - - [09/Apr/2026 19:09:21] \"GET /ims_subscriber/list HTTP/1.1\" 200 -"]`
> - **Significance**: This provides further evidence that the `pyhss` application itself is not the source of the failure, shifting the focus of the investigation towards the `icscf`.
>
> - **Finding**: Despite metrics indicating a high rate of timeouts and connection failures, the logs for `icscf` and `pcscf` are completely silent on these events over the last five minutes.
> - **Evidence**: `[EVIDENCE: read_container_logs("icscf", grep="timeout", since_seconds=300) -> "(no log output)"]`, `[EVIDENCE: read_container_logs("pcscf", grep="connfail", since_seconds=300) -> "(no log output)"]`
> - **Significance**: This suggests the Kamailio processes within these containers may be overwhelmed or stuck in a state where they are incrementing failure statistics but are unable to perform normal operations like writing logs, which is a severe symptom of a signaling storm.
>
> - **Finding**: The `icscf`'s Diameter peer connection to the HSS (`hss.ims.mnc001.mcc001.3gppnetwork.org`) is in the `I_Open` state.
> - **Evidence**: `[EVIDENCE: run_kamcmd("icscf", "cdp.list_peers") -> "FQDN: hss.ims.mnc001.mcc001.3gppnetwork.org... State: I_Open"]`
> - **Significance**: This is the most critical piece of evidence. While the tool output notes that `I_Open` can be a benign display issue during normal operation, it is not the expected fully-established state (`R_Open`). In the context of the observed Diameter timeouts (`lir_timeouts`, `uar_timeouts`), this `I_Open` state indicates the connection is not perceived as fully functional by the `icscf`, preventing it from reliably sending Diameter queries. This directly explains the timeouts and the subsequent cascading failures at the `pcscf`.
>
> ### Layer Status
> - **Transport**: GREEN. RTT between IMS components is excellent `[EVIDENCE: measure_rtt("icscf", "172.22.0.18") -> "rtt min/avg/max/mdev = 0.095/0.101/0.111/0.007 ms"]`.
> - **Core**: GREEN. Per the initial instruction, the 5G Core is stable.
> - **Application**: RED. The `icscf` Diameter connection to the HSS is in a non-operational state (`I_Open`), leading to timeouts and a cascading signaling storm affecting the `pcscf`. `[EVIDENCE: run_kamcmd("icscf", "cdp.list_peers") -> "State: I_Open"]`.
>
> ### Root Cause Assessment
> - **Primary cause**: The root cause of the IMS signaling storm is the Diameter connection from the `icscf` to the `pyhss` being stuck in the `I_Open` state. The `icscf` is unable to process user authentication (UAR) and location (LIR) requests because it does not have a fully established Diameter connection to the HSS. This failure leads to timeouts within `icscf`, which in turn causes a cascade of connection failures and timeouts upstream at the `pcscf` as it attempts to forward SIP requests.
> - **Confidence**: High
> - **Supporting evidence**:
>     - `[EVIDENCE: run_kamcmd("icscf", "cdp.list_peers") -> "State: I_Open"]`
>     - `[EVIDENCE: measure_rtt("icscf", "172.22.0.18") -> "rtt min/avg/max/mdev = 0.095/0.101/0.111/0.007 ms"]`
>     - `[EVIDENCE: read_container_logs("pyhss", since_seconds=300) -> "172.22.0.1 - - [09/Apr/2026 19:09:21] \"GET /ims_subscriber/list HTTP/1.1\" 200 -"]`

## Evidence Validation (Phase 5)

**Verdict:** clean
**Investigator confidence:** high
**Citations:** 10/10 verified

```
Evidence validation: 10/10 citations verified (0 unmatched). Investigator: 10 citations from 4 tool calls.
Verdict: clean. Investigator confidence: high.

Tool calls vs. citations:
  NetworkAnalystAgent:
    ✗ check_stack_rules — called but NOT cited in output
    ✗ compare_to_baseline — called but NOT cited in output
    ✗ get_dp_quality_gauges — called but NOT cited in output
    ✗ get_network_status — called but NOT cited in output
    ✗ get_network_topology — called but NOT cited in output
    ✗ get_nf_metrics — called but NOT cited in output
    ✗ get_vonr_components — called but NOT cited in output
    ✗ measure_rtt — called but NOT cited in output
    ✗ read_env_config — called but NOT cited in output
  InvestigatorAgent:
    ✓ measure_rtt — called AND cited (3x)
    ✓ read_container_logs — called AND cited (4x)
    ✗ read_env_config — called but NOT cited in output
    ✓ run_kamcmd — called AND cited (3x)
```

## Ground Truth

**Failure domain:** data_plane  
**Protocol impact:** GTP-U  
**Affected components:** upf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v5-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 255.5s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: A stuck Diameter connection on the I-CSCF is preventing it from communicating with the HSS, causing internal timeouts and a cascading signaling storm that has impacted the entire IMS layer.
> - **timeline**:
>     1.  The Diameter peer connection from the `icscf` to the HSS (`pyhss`) enters a non-operational `I_Open` state, preventing the sending of new requests.
>     2.  The `icscf`, unable to query the HSS, experiences timeouts for user authentication (UAR) and location (LIR) procedures, incrementing `uar_timeouts` and `lir_timeouts` metrics.
>     3.  Upstream, the `pcscf` attempts to forward user registration requests to the now-unresponsive `icscf`, resulting in a massive spike in connection failures (`httpclient:connfail_rate`) and a system-wide signaling failure.
> - **root_cause**: The Diameter client within the `icscf` is the root cause. Its peer connection to the HSS is stuck in an `I_Open` (initiating) state, rather than the required `R_Open` (fully established) state. This prevents the `icscf` from processing any Diameter-based procedures like user authentication or location queries. The subsequent timeouts cascade upstream, creating a signaling storm that overwhelms the `pcscf`.
> - **affected_components**:
>     - `icscf`: Root Cause
>     - `pcscf`: Symptomatic
>     - `pyhss`: Symptomatic
> - **recommendation**: The operator should verify the state of the Diameter peer connections on the `icscf` using its management interface. Further investigation should focus on why the `icscf`'s Diameter client failed to fully establish the connection with the HSS, despite healthy transport connectivity between the components.
> - **confidence**: high
> - **explanation**: The IMS network failure is caused by the I-CSCF's Diameter connection to the HSS being stuck in an initiating state. This prevents the I-CSCF from sending authentication and location queries, causing internal timeouts. These failures cascade upstream to the P-CSCF, triggering a widespread signaling storm. While initial analysis pointed to an unresponsive HSS, investigation confirmed the HSS is healthy and transport connectivity is fine, isolating the fault to the Diameter client state within the I-CSCF itself.

### Scoring Breakdown

**Overall score: 0%**

**Scorer assessment:** The agent completely misdiagnosed the issue, identifying a signaling plane problem in the IMS layer instead of a data plane degradation in the 5G Core, with high but uncalibrated confidence.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | No | The simulated failure was 30% packet loss on the UPF, causing data plane degradation. The agent diagnosed a stuck Diameter connection on the I-CSCF leading to an IMS signaling storm, which is a completely different root cause and failure domain. |
| Component overlap | 0% | The primary affected component in the simulation was the 'upf'. The agent identified 'icscf', 'pcscf', and 'pyhss' as affected components, with no mention of the 'upf'. |
| Severity correct | No | The simulated failure was a 30% packet loss, indicating degradation. The agent's diagnosis of a 'critical failure' and 'widespread signaling failure' implies a complete outage or severe disruption, which does not match the actual degradation. |
| Fault type identified | No | The simulated fault type was 'packet loss' (network degradation). The agent identified 'stuck Diameter connection', 'internal timeouts', and a 'signaling storm', which are different fault types related to service unresponsiveness and signaling issues. |
| Layer accuracy | No | The 'upf' belongs to the 'core' layer. The agent incorrectly rated the 'core' layer as GREEN and attributed the problem to the 'ims' layer (RED), misattributing the failure to the wrong layer. |
| Confidence calibrated | No | The agent expressed 'high' confidence in a diagnosis that was completely incorrect across all dimensions (root cause, component, severity, fault type, and layer). This indicates poor calibration. |

**Ranking:** The correct cause (UPF packet loss) was not identified or ranked by the agent.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 205,102 |
| Output tokens | 8,581 |
| Thinking tokens | 13,853 |
| **Total tokens** | **227,536** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| NetworkAnalystAgent | 94,583 | 16 | 6 |
| PatternMatcherAgent | 0 | 0 | 0 |
| InstructionGeneratorAgent | 6,195 | 0 | 1 |
| InvestigatorAgent | 116,624 | 8 | 9 |
| EvidenceValidatorAgent | 0 | 0 | 0 |
| SynthesisAgent | 10,134 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 385.3s

---

## Post-Run Critical Analysis

### Overview

This episode represents a **total diagnostic failure** — 0% score across all dimensions. The agent diagnosed an IMS signaling storm caused by a stuck Diameter connection on the I-CSCF, when the actual fault was 30% packet loss on the UPF. The failure exposes deep architectural issues in how the anomaly detection pipeline interacts with this class of fault, and raises fundamental questions about how an agent can reason through correlated multi-layer symptoms to find a root cause that doesn't self-report.

### Issue 1: The Anomaly Screener Is Blind to UPF Degradation

**What happened:** The anomaly screener flagged 10 metrics, all IMS signaling (SIP rates, Diameter rates). No UPF metric was flagged. The screener's top contributors — `pcscf.httpclient:connfail_rate` at 1661x normal, `sl:1xx_replies_rate` at 2076x normal — completely dominated the agent's attention.

**Root cause investigation:** The trained anomaly model has these learned baselines for UPF:

| Feature | Mean | Std Dev | Min | Max |
|---------|------|---------|-----|-----|
| `upf.indatapktn3upf_rate` | 5.04 | 4.90 | 0.00 | 17.03 |
| `upf.outdatapktn3upf_rate` | 4.92 | 4.77 | 0.00 | 16.85 |

The standard deviation is nearly as large as the mean, and the minimum is 0.0. During training, the traffic generator produces bursty patterns — VoNR calls create GTP-U packet spikes, idle periods between calls produce zeros. The model learned that any UPF rate between 0 and 17 pkt/s is normal. When the fault caused UPF rates to drop to near-zero (because calls failed to set up), the anomaly screener said "this is normal — I've seen zero before."

Meanwhile, the IMS signaling metrics have tiny trained baselines (0.04–0.27 pkt/s). The traffic generated during the observation window caused 1000x+ deviations from these baselines, overwhelming the UPF signal entirely.

**Verification:** We confirmed that:
- Prometheus CAN scrape UPF under 30% loss (scrape duration increases from 0.0015s to ~1s, but succeeds)
- `snapshot_metrics()` DOES include UPF data under the fault
- The GTP-U counters moved by only 25 packets (just SIP signaling), not enough to stand out
- `outdatapktn3upf` didn't increment at all — no downlink GTP-U packets were sent during the observation

### Issue 2: RTPEngine Diagnostic Metrics Were Excluded

**What happened:** The observation delta DID contain RTPEngine evidence of data plane degradation:

| Metric | Baseline | Current | Delta |
|--------|----------|---------|-------|
| `sum_of_all_packet_loss_values_sampled` | 0 | 116 | 116 |
| `packet_loss_standard_deviation` | 0 | 5 | 5 |
| `total_number_of_1_way_streams` | 0 | 1 | 1 |
| `total_timed_out_sessions_via_timeout` | 5 | 6 | 1 |

These are direct evidence of data plane degradation. But the anomaly screener never saw them because the preprocessor's `_DIAGNOSTIC_METRICS` set excluded raw RTPEngine counters — it only included the averaged gauges (`average_packet_loss`, `average_mos`), which smooth out the signal.

**Why these metrics were excluded:** When the anomaly detection system was built, the preprocessor was given a hand-curated set of ~35 "diagnostically important" metrics out of 143 available, with the rationale that HalfSpaceTrees works better with a smaller feature space. The raw RTPEngine packet loss counters were left out in favor of the averaged gauges — a judgment call that turned out to be wrong for this class of failure.

**Fix applied (this session):** Added 5 RTPEngine metrics to `_DIAGNOSTIC_METRICS`: `packets_lost`, `total_number_of_1_way_streams`, `total_relayed_packet_errors`, `errors_per_second_(total)`, `packet_loss_standard_deviation`. Also added corresponding GUI tooltips and data plane health panel. The anomaly model needs retraining to incorporate these.

### Issue 3: tc netem on UPF Affects Everything, Not Just the Data Plane

**What happened:** The scenario injects 30% packet loss on the UPF container's `eth0` — its only network interface. This affects ALL traffic through the UPF:

- **GTP-U N3** (gNB ↔ UPF): user plane data, including SIP signaling from UEs
- **PFCP N4** (SMF ↔ UPF): control plane session management
- **N6** (UPF ↔ data network / P-CSCF): traffic toward IMS and internet

In VoNR, SIP signaling rides inside the GTP-U tunnel: UE → gNB → UPF → P-CSCF. The 30% packet loss drops SIP REGISTER and INVITE messages along with RTP media. SIP over UDP retransmits on T1 timers (500ms). Dropped SIP messages trigger retransmissions that create the "signaling storm" the anomaly screener detected. The agent correctly identified the symptoms (IMS signaling disruption) but attributed them to an IMS-layer problem rather than a data-plane-layer cause.

**Implication:** This scenario doesn't test "data plane degradation" in isolation — it tests "everything-on-UPF degradation." SIP signaling is encapsulated inside GTP-U, so there is no way to filter tc netem rules on the UPF to affect only media traffic without also affecting signaling. If the goal is to test pure media degradation without signaling disruption, the loss should be applied to RTPEngine instead (RTP media flows through RTPEngine but SIP signaling does not).

### Issue 4: The Root Cause Component Doesn't Self-Report

**What happened:** Even if the agent had investigated the UPF, it would find:
- Container status: running
- Prometheus scrape: healthy
- GTP-U counters: barely changed (not because of failure, but because traffic was disrupted)
- No "packet loss" metric exposed by Open5GS UPF

The tc netem loss operates below the UPF application layer. The UPF hands packets to the kernel for transmission; tc netem drops them after that point. The UPF's own metrics don't count the drops because the UPF doesn't know about them. From the UPF application's perspective, it successfully processed and forwarded every packet.

**Verification:** `docker exec upf tc -s qdisc show dev eth0` showed 71 packets dropped out of 169 sent (42% effective drop rate). But this information is only available via tc stats inside the container — none of the agent's diagnostic tools (`get_nf_metrics`, `measure_rtt`, `read_container_logs`) expose tc qdisc statistics.

### Issue 5: The UPF GTP-U Counters Don't Change Because Calls Fail

**What happened:** Under 30% packet loss on the UPF, VoNR call setup fails. We reproduced this:

```
Triggering SIP re-register... (succeeded — short transaction, survives retransmits)
Attempting VoNR call... 
  Call result: False
  Call failed: Call setup timed out after 30s — call did not reach CONFIRMED state
  
DELTA:
  indatapkt: 25  (just the SIP signaling packets)
  outdatapkt: 0  (no downlink GTP-U at all)
```

Call setup involves multiple SIP round-trips (INVITE → 100 Trying → 180 Ringing → 200 OK → ACK), each traversing the lossy UPF path. With 30% loss on each hop, the probability of a complete call setup succeeding drops significantly. When calls don't set up, no RTP media flows, and the GTP-U counters barely move.

The observation delta therefore contains no UPF entries — not because collection failed, but because there was genuinely almost no UPF traffic to measure. The scenario is **self-concealing**: the fault prevents the traffic that would reveal the fault. 30% loss → calls fail to set up → no RTP media flows → no UPF throughput to measure → UPF looks idle (which is "normal" per the trained model).

### Why This Failure Is Fundamentally Difficult to Diagnose

1. **The root cause is invisible to its own metrics.** The UPF doesn't know it's dropping packets. tc netem operates below the application layer. No Open5GS counter tracks kernel-level drops.

2. **The loudest symptoms point away from the root cause.** IMS signaling metrics spike 1000x+ because of SIP retransmissions. RTPEngine metrics (once included) show packet loss but at much lower deviation. The anomaly screener will always flag IMS first.

3. **The root cause component sits at the intersection of two paths** (signaling and media) **but the symptoms appear separately in each path.** The agent would need to recognize that correlated degradation in both paths implies a shared upstream dependency.

4. **The scenario is self-concealing.** The fault prevents the traffic that would reveal the fault.

### How an Agent Could Be Designed to Reason Through This

The LLM powering the Ops agent has telecom knowledge in its weights — it understands GTP-U encapsulation, media paths, and shared dependencies. The problem is not missing knowledge but missing activation. The anomaly screener shouts "IMS!" and the agent follows that signal because the pipeline structure and prompts funnel it toward "which component is broken?" rather than "what do these correlated symptoms tell me about the network topology?"

**Approach 1: Correlated multi-path reasoning in the Network Analyst prompt.**

Add a reasoning step before layer rating: *"When symptoms appear in multiple independent subsystems (e.g., IMS signaling degradation AND RTPEngine media quality degradation simultaneously), look for a shared upstream dependency using `get_network_topology` or `get_causal_chain_for_component`. In VoNR, both SIP signaling and RTP media traverse the GTP-U tunnel through the UPF. Correlated degradation in both paths may indicate a problem at their convergence point rather than in either path individually."*

This activates the model's existing telecom knowledge by prompting it to think about topology before attributing symptoms to individual layers.

**Approach 2: Teach the agent that "component looks healthy but path through it is degraded" is a valid failure mode.**

The agent currently investigates components by checking if they're running, examining logs, and measuring RTT. For a tc netem fault, all of these return "healthy." The agent needs a tool or reasoning step that checks the quality of traffic *through* a component, not just the component's own health. `measure_rtt` partially does this (it traverses the lossy interface), but under 30% loss with TCP retransmission, ping might still succeed — it just takes longer. The agent would need to interpret elevated RTT or intermittent packet loss in `measure_rtt` results as evidence of a network-level fault on the component's interface.

**Approach 3: Include UPF rate *drop* as a diagnostic signal.**

The anomaly screener currently flags values that deviate above the learned normal. But a DROP in UPF throughput from ~5 pkt/s to ~0 during active traffic generation is also anomalous — it means the data plane is not carrying traffic that should be flowing. The challenge is that the trained baseline includes zero (from idle periods), so the model can't distinguish "idle" from "degraded." A potential fix: train the model only on snapshots where traffic is actively being generated, not on idle intervals. Or use a conditional feature: "UPF rate during active call" vs "UPF rate during idle."

**Approach 4: Surface tc/interface stats as a diagnostic tool.**

Add a tool that runs `docker exec <container> tc -s qdisc show dev eth0` and parses the dropped packet count, or reads interface-level error counters via `ip -s link show`. This would directly expose network-level drops to the agent. This approach is not specific to tc netem — production networks also have interface error counters, and a NOC operator would check them. The tool would generalize beyond chaos testing.

### Changes Made in This Session

1. **Added 5 RTPEngine metrics to `_DIAGNOSTIC_METRICS`** in `agentic_ops_v5/anomaly/preprocessor.py`: `packets_lost`, `total_number_of_1_way_streams`, `total_relayed_packet_errors`, `errors_per_second_(total)`, `packet_loss_standard_deviation`.

2. **Added GUI support** for these metrics: gauge keys in `gui/metrics.py`, tooltip descriptions in `network_ontology/data/baselines.yaml`, and a new "Data Plane Health" section in the RTPEngine detail panel in `gui/templates/topology.html`.

### Outstanding Work

- **Retrain the anomaly model** with the new RTPEngine diagnostic metrics included (`python -m anomaly_trainer --duration 300`).
- **Add correlated multi-path reasoning** to the Network Analyst prompt to activate the LLM's existing telecom knowledge for shared-dependency diagnosis.
- **Consider redesigning the scenario** to inject loss on RTPEngine instead of UPF, if the goal is to test pure data plane degradation without signaling disruption.
- **Consider adding a `check_interface_stats` tool** that exposes tc qdisc drop counts and interface-level error counters to the agent's diagnostic toolkit.
