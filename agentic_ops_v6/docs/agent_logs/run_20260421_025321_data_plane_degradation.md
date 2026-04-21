# Episode Report: Data Plane Degradation

**Agent:** v6  
**Episode ID:** ep_20260421_024854_data_plane_degradation  
**Date:** 2026-04-21T02:48:55.783877+00:00  
**Duration:** 265.1s  

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
- **Nodes with significant deltas:** 6
- **Nodes with any drift:** 6

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 0.90 (threshold: 0.70, trained on 211 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following metrics deviate from their learned-healthy baseline. Treat each as a semantic observation (meaning + numbers), not a number alone — the KB's interpretation is the authoritative reading.

- **`normalized.upf.gtp_outdatapktn3upf_per_ue`** (GTP-U downlink rate per UE (N3)) — current **0.03 packets_per_second** vs learned baseline **3.34 packets_per_second** (MEDIUM, drop)
    - **What it measures:** Health of the downlink user-plane path UPF → gNB. Typically mirrors
uplink rate during calls/data; asymmetry indicates directional
faults (e.g., UPF receiving from internet but not forwarding).
    - **Drop means:** No traffic leaving UPF toward RAN.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE — constant regardless of UE pool size. Roughly symmetric with uplink during healthy calls.

- **`normalized.upf.gtp_indatapktn3upf_per_ue`** (GTP-U uplink rate per UE (N3)) — current **0.05 packets_per_second** vs learned baseline **3.42 packets_per_second** (MEDIUM, drop)
    - **What it measures:** Health of the uplink user-plane path gNB → UPF. Drops to near-zero
during RAN or N3 outage; stays nonzero during active calls or data
sessions. Decoupled from SIP signaling (signals data plane, not
control plane).
    - **Drop means:** Data plane dead on uplink — UPF receiving no packets from gNB.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE — constant regardless of UE pool size. Rises during active VoNR calls (~100 pps for G.711 voice) and data transfer.

- **`normalized.smf.bearers_per_ue`** (Active QoS bearers per UE) — current **2.00 count** vs learned baseline **2.61 count** (LOW, shift)
    - **What it measures:** Per-UE count of active QoS bearers. Baseline reflects default
bearers; increments during VoNR calls indicate dedicated voice
bearers being set up. Drop during an active call = dedicated
bearer torn down unexpectedly (voice will fail).
    - **Shift means:** Expected during VoNR calls (1 extra bearer per active call).
    - **Healthy typical range:** 2–3.5 count
    - **Healthy invariant:** At rest: equals configured default bearers (typically 2 per UE).
During active VoNR call: +1 per caller. The per-UE ratio is the
invariant; absolute count scales with UE pool.

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

**1 events fired during the observation window:**

- `ims.pcscf.register_time_elevated` (source: `ims.pcscf.avg_register_time_ms`, nf: `pcscf`, t=1776739852.7)  [current_value=1454.8, delta_percent=73.72820635299738]

## Correlation Analysis (Phase 2)

1 events fired but no composite hypothesis emerged. The events may be from independent faults or lack registered correlation hints in the KB.

## Network Analysis (Phase 3)

**Summary:** IMS registration is failing due to the HSS being unresponsive to Diameter requests, which prevents users from making VoNR calls and leads to an inactive data plane.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | The underlying container infrastructure appears healthy. |
| **ran** | 🟢 GREEN | No evidence of a RAN-side fault; UEs appear to be attached to the core. |
| **core** | 🟡 YELLOW | The 5G core's data plane is inactive, but this is a symptom of the IMS control plane failure, not a root cause within the core itself. |
| **ims** | 🔴 RED | The failure is localized to the IMS control plane. Registration is failing due to timeouts, preventing any SIP dialogs from being established. |

**CORE evidence:**
- screener: normalized.upf.gtp_outdatapktn3upf_per_ue is near-zero
- screener: normalized.upf.gtp_indatapktn3upf_per_ue is near-zero
- screener: normalized.smf.bearers_per_ue has shifted down

**IMS evidence:**
- fired_events: ims.pcscf.register_time_elevated
- screener: normalized.pcscf.dialogs_per_ue is zero
- get_nf_metrics: icscf.ims_icscf:uar_timeouts is 9
- get_nf_metrics: pcscf.script:register_failed is 9 (vs 10 success)

**Ranked hypotheses:**

- **`h1`** (fit=0.90, nf=pyhss, specificity=specific):
    - **Statement:** The HSS is unresponsive or partitioned from the network, causing Diameter timeouts on the Cx interface. The I-CSCF cannot resolve user identities (UAR requests), which in turn causes registrations to fail and prevents any call setup.
    - **Supporting events:** `ims.pcscf.register_time_elevated`
    - **Falsification probes:**
        - measure_rtt(container='icscf', target_ip='<HSS_IP>') to check network path latency.
        - get_causal_chain_for_component(component='pyhss') to see if ontology predicts this symptom pattern.
        - Check HSS's own logs or metrics for internal errors or resource exhaustion.
- **`h2`** (fit=0.60, nf=pcscf, specificity=moderate):
    - **Statement:** The P-CSCF has an internal fault or is misconfigured, causing it to fail during the registration process. This is supported by the high number of HTTP client connection failures, which may indicate a problem with its ability to communicate with other NFs like the PCF.
    - **Supporting events:** `ims.pcscf.register_time_elevated`
    - **Falsification probes:**
        - measure_rtt(container='pcscf', target_ip='<ICSCF_IP>') to rule out a network issue between P-CSCF and I-CSCF.
        - measure_rtt(container='pcscf', target_ip='<PCF_IP>') to test connectivity on the Rx path.
        - Examine P-CSCF logs for errors related to registration or the HTTP client.


## Falsification Plans (Phase 4)

**2 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `pyhss`)

**Hypothesis:** The HSS is unresponsive or partitioned from the network, causing Diameter timeouts on the Cx interface. The I-CSCF cannot resolve user identities (UAR requests), which in turn causes registrations to fail and prevents any call setup.

**Probes (3):**
1. **`measure_rtt`** — from='icscf', to_ip='<HSS_IP>'
    - *Expected if hypothesis holds:* High RTT (>500ms, indicating timeout) or 100% packet loss, consistent with an unresponsive or partitioned HSS.
    - *Falsifying observation:* Clean RTT (< 5ms) and 0% packet loss, indicating a healthy network path from I-CSCF to HSS, which would contradict the HSS being unreachable.
2. **`read_container_logs`** — container='pyhss', grep='DIAMETER_REQUEST|UAR|ERROR|TIMEOUT'
    - *Expected if hypothesis holds:* Logs showing no incoming UAR Diameter messages or logs indicating errors/timeouts when processing such requests, supporting the HSS being unresponsive or not receiving traffic.
    - *Falsifying observation:* Logs showing a high volume of successfully processed UAR Diameter requests and no relevant errors, indicating the HSS is responsive and receiving requests as expected.
3. **`measure_rtt`** — from='pyhss', to_ip='<ICSCF_IP>'
    - *Expected if hypothesis holds:* If the HSS is partitioned from the network, this probe should also show high RTT or packet loss. If only the I-CSCF to HSS path is bad, it would narrow the network issue.
    - *Falsifying observation:* Clean RTT (< 5ms) and 0% packet loss, suggesting the network path *from* HSS to I-CSCF is healthy, making a general HSS network partition less likely.

*Notes:* This plan triangulates network connectivity to HSS and checks its internal processing and activity to confirm unresponsiveness or partitioning.

### Plan for `h2` (target: `pcscf`)

**Hypothesis:** The P-CSCF has an internal fault or is misconfigured, causing it to fail during the registration process. This is supported by the high number of HTTP client connection failures, which may indicate a problem with its ability to communicate with other NFs like the PCF.

**Probes (3):**
1. **`read_container_logs`** — container='pcscf', grep='ERROR|registration failed|HTTP client connection failure'
    - *Expected if hypothesis holds:* Logs explicitly showing errors related to registration failures or HTTP client connection problems, directly supporting the internal fault or misconfiguration claim.
    - *Falsifying observation:* Clean logs with no entries matching the error patterns, indicating the P-CSCF is not experiencing these internal failures during registration or HTTP communication.
2. **`get_nf_metrics`** — Look for P-CSCF HTTP client error counters or registration failure metrics.
    - *Expected if hypothesis holds:* High values for P-CSCF HTTP client connection failure counters or registration failure metrics, directly supporting the hypothesis's supporting event.
    - *Falsifying observation:* Zero or very low values for P-CSCF HTTP client connection failure counters and registration failure metrics, directly contradicting the observation of high failures.
3. **`measure_rtt`** — from='pcf', to_ip='<P-CSCF_IP>'
    - *Expected if hypothesis holds:* Clean RTT (< 5ms) and 0% packet loss. If the P-CSCF has an *internal* fault or misconfiguration, the network path to it should be healthy.
    - *Falsifying observation:* High RTT (>500ms) or 100% packet loss, indicating a network issue between PCF and P-CSCF, which would suggest a network problem rather than an internal P-CSCF fault.

*Notes:* This plan focuses on P-CSCF internal logs and metrics for direct evidence of errors, and includes a network check from a related NF (PCF) to rule out external network issues.


## Parallel Investigators (Phase 5)

**2 sub-Investigator verdict(s):** **2 DISPROVEN**

### `h1` — ❌ **DISPROVEN**

**Hypothesis:** The HSS is unresponsive or partitioned from the network, causing Diameter timeouts on the Cx interface. The I-CSCF cannot resolve user identities (UAR requests), which in turn causes registrations to fail and prevents any call setup.

**Reasoning:** The hypothesis is disproven because the primary evidence shows there is no network partition. The RTT from the I-CSCF to the HSS is perfectly healthy, which directly contradicts the core of the hypothesis. The lack of Diameter request logs on the HSS, when combined with the healthy network path, points to the I-CSCF as the likely source of the issue, as it is failing to send requests to a reachable HSS.

**Probes executed (3):**
- **from='icscf', to_ip='<HSS_IP>'** ✗ CONTRADICTS
    - *Tool:* `default_api.measure_rtt(container='icscf', target_ip='172.22.0.18')`
    - *Observation:* [EVIDENCE: measure_rtt("icscf", "172.22.0.18") -> "rtt min/avg/max/mdev = 0.072/0.089/0.101/0.012 ms"]
    - *Comment:* The RTT is extremely low (<1ms) with 0% packet loss. This result falsifies the claim that the HSS is partitioned from the network or unresponsive at the network layer, as the I-CSCF has a clear path to it.
- **container='pyhss', grep='DIAMETER_REQUEST|UAR|ERROR|TIMEOUT'** ~ AMBIGUOUS
    - *Tool:* `default_api.read_container_logs(container='pyhss', grep='DIAMETER_REQUEST|UAR|ERROR|TIMEOUT')`
    - *Observation:* [EVIDENCE: read_container_logs("pyhss", "DIAMETER_REQUEST|UAR|ERROR|TIMEOUT") -> "(no log output)"]
    - *Comment:* The absence of logs is ambiguous on its own. However, when combined with the clean RTT from I-CSCF to HSS, it suggests that the HSS is not receiving any UAR requests to process or log, pointing the finger upstream to the I-CSCF.
- **from='pyhss', to_ip='<ICSCF_IP>'** ~ AMBIGUOUS
    - *Tool:* `default_api.measure_rtt(container='pyhss', target_ip='172.22.0.19')`
    - *Observation:* [EVIDENCE: measure_rtt("pyhss", "172.22.0.19") -> "Ping failed from pyhss to 172.22.0.19: OCI runtime exec failed: exec failed: unable to start container process: exec: \"ping\": executable file not found in $PATH: unknown"]
    - *Comment:* The probe failed because the 'ping' utility is not installed in the pyhss container. Therefore, this probe could not be used to triangulate network connectivity in the reverse direction.

**Alternative suspects:** icscf

### `h2` — ❌ **DISPROVEN**

**Hypothesis:** The P-CSCF has an internal fault or is misconfigured, causing it to fail during the registration process. This is supported by the high number of HTTP client connection failures, which may indicate a problem with its ability to communicate with other NFs like the PCF.

**Reasoning:** The hypothesis of an internal P-CSCF fault is contradicted by the complete absence of relevant error logs on the P-CSCF container. While metrics show a high number of HTTP client connection failures, these are not accompanied by any corresponding logged events, which would be expected if the P-CSCF itself were the source of the fault. The problem is more likely external to the P-CSCF, with the connection failures being a symptom of another NF's failure to respond.

**Probes executed (3):**
- **Check P-CSCF logs for errors related to registration or HTTP client failures.** ✗ CONTRADICTS
    - *Tool:* `default_api.read_container_logs(container='pcscf', grep='ERROR|registration failed|HTTP client connection failure')`
    - *Observation:* [EVIDENCE: read_container_logs("container='pcscf', grep='ERROR|registration failed|HTTP client connection failure'") -> "(no log output)"]
    - *Comment:* The complete absence of logs matching patterns for errors, registration failures, or HTTP client connection failures strongly contradicts the hypothesis that the P-CSCF has an internal fault.
- **Look for P-CSCF HTTP client error counters or registration failure metrics.** ~ AMBIGUOUS
    - *Tool:* `default_api.get_nf_metrics()`
    - *Observation:* [EVIDENCE: get_nf_metrics() -> "PCSCF [2 reg] (via kamcmd):\n  httpclient:connfail = 132.0  [counter]"]
    - *Comment:* The metric `httpclient:connfail = 132.0` is consistent with the supporting event of the hypothesis. However, without corresponding error logs, this metric alone is ambiguous. It confirms connection failures are occurring but does not prove they are caused by an internal P-CSCF fault; they could be caused by the remote end (e.g., PCF) being unavailable.
- **Measure RTT from PCF to P-CSCF to check the network path.** ✓ CONSISTENT
    - *Tool:* `default_api.measure_rtt(container='pcf', target_ip='172.22.0.21')`
    - *Observation:* [EVIDENCE: measure_rtt("container='pcf', target_ip='172.22.0.21'") -> "3 packets transmitted, 3 received, 0% packet loss, time 2028ms\nrtt min/avg/max/mdev = 0.100/0.144/0.181/0.033 ms"]
    - *Comment:* The network path from the PCF to the P-CSCF is healthy. This result is consistent with the hypothesis of an *internal* P-CSCF fault, as it rules out a network connectivity issue *to* the P-CSCF. However, it does not rule out a problem with the PCF itself.

**Alternative suspects:** pcf


## Evidence Validation (Phase 6)

**Overall verdict:** clean
**Overall confidence:** high

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 4 | 3/3 | clean | high |
| `InvestigatorAgent_h2` | 4 | 3/3 | clean | high |


## Ground Truth

**Failure domain:** data_plane  
**Protocol impact:** GTP-U  
**Affected components:** upf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v6-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 132.6s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: Initial hypotheses pointing to the HSS and P-CSCF have been disproven; evidence suggests the root cause of IMS registration failures is likely a fault within the I-CSCF or the PCF.
> - **timeline**:
>     1. The `ims.pcscf.register_time_elevated` event was observed, indicating that SIP REGISTER requests were timing out.
> - **root_cause**: The root cause is undetermined, as initial hypotheses were invalidated. Investigation points to two new primary suspects that require further analysis.
> - **affected_components**:
>     - `icscf`: Potential Root Cause
>     - `pcf`: Potential Root Cause
>     - `pyhss`: Symptomatic
>     - `pcscf`: Symptomatic
> - **recommendation**: Verify the internal state of the I-CSCF to determine why it is not sending Diameter UAR requests to the HSS, despite a healthy network path. Concurrently, investigate the logs and health of the PCF to understand the cause of the P-CSCF's HTTP client connection failures.
> - **confidence**: low
> - **explanation**: The investigation disproved the two initial hypotheses. The primary hypothesis (`h1`), blaming an unresponsive HSS, was falsified by evidence of a healthy, low-latency network path between the I-CSCF and the HSS. The HSS logs also showed no incoming requests, suggesting the fault lies upstream with the I-CSCF failing to send them. The second hypothesis (`h2`), blaming an internal P-CSCF fault, was disproven by a lack of corresponding error logs on the P-CSCF, indicating its observed HTTP connection failures are a symptom of a remote service failing. Because both initial theories were incorrect, confidence in a specific root cause is low, and investigation must now focus on the alternative suspects surfaced: the I-CSCF and the PCF.

### Scoring Breakdown

**Overall score: 10%**

**Scorer assessment:** The agent completely misdiagnosed the data plane degradation on the UPF, incorrectly focusing on IMS control plane registration failures. However, its low confidence was appropriately calibrated given the incorrect diagnosis.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | No | The simulated failure was 30% packet loss on the UPF, leading to data plane degradation. The agent incorrectly focused on IMS registration failures, I-CSCF, and PCF as potential root causes, and explicitly stated the root cause was undetermined. It completely missed the UPF packet loss. |
| Component overlap | 0% | The primary affected component was the UPF. The agent identified I-CSCF and PCF as potential root causes, and HSS/P-CSCF as symptomatic. It did not identify UPF as a root cause or even a primary symptomatic component, explicitly stating that the core data plane inactivity (which would include UPF) was a symptom of an IMS control plane failure, not a root cause. |
| Severity correct | No | The simulated failure was a degradation (30% packet loss). The agent diagnosed 'IMS registration failures' and 'inactive data plane', implying a complete outage or severe functional failure, which is more severe than the actual degradation. |
| Fault type identified | No | The simulated fault type was 'packet loss' (network degradation). The agent identified 'timeouts', 'unresponsive HSS', and 'inactive data plane', which are related to component unreachability/hang or complete service failure, not packet loss. |
| Layer accuracy | No | The primary affected component, UPF, belongs to the 'core' layer. The agent incorrectly attributed the root cause to the 'ims' layer and explicitly dismissed the 'core' layer as the root cause, stating its inactivity was a symptom. |
| Confidence calibrated | Yes | The agent's diagnosis was entirely incorrect, missing the actual root cause, component, and fault type. Its stated 'low' confidence is appropriate given the poor quality of its diagnosis and its acknowledgment that the root cause is undetermined. |

**Ranking:** The correct root cause (UPF packet loss) was not identified or ranked by the agent.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 106,974 |
| Output tokens | 4,265 |
| Thinking tokens | 12,348 |
| **Total tokens** | **123,587** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| EventAggregator | 0 | 0 | 0 |
| CorrelationAnalyzer | 0 | 0 | 0 |
| NetworkAnalystAgent | 31,328 | 3 | 4 |
| InstructionGeneratorAgent | 7,357 | 0 | 1 |
| InvestigatorAgent_h1 | 33,647 | 4 | 5 |
| InvestigatorAgent_h2 | 46,109 | 4 | 5 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 5,146 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 265.1s
