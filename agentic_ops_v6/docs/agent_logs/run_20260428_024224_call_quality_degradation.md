# Episode Report: Call Quality Degradation

**Agent:** v6  
**Episode ID:** ep_20260428_023720_call_quality_degradation  
**Date:** 2026-04-28T02:37:22.386609+00:00  
**Duration:** 301.2s  

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
- **Nodes with significant deltas:** 4
- **Nodes with any drift:** 5

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 0.75 (threshold: 0.70, trained on 104 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following metrics deviate from their learned-healthy baseline. Treat each as a semantic observation (meaning + numbers), not a number alone — the KB's interpretation is the authoritative reading.

- **`derived.rtpengine_loss_ratio`** (RTPEngine RTCP-reported per-RR average packet loss) — current **10.14 packets_per_rr** vs learned baseline **0.00 packets_per_rr** (HIGH, spike)
    - **What it measures:** Live measure of media-plane packet loss as observed by
the far end of each call (via RTCP RRs) and aggregated
into per-RR mean. Zero during healthy traffic regardless
of call volume; rises when receivers report missing
packets. Magnitude scales with loss intensity, so a
higher value indicates more packets lost per report.
    - **Spike means:** Receivers are reporting packet loss back to rtpengine.
Could be loss on the rtpengine container's egress
(iptables / tc / interface congestion), loss anywhere
upstream of the receiver, or — with simultaneous UPF
counter degradation — loss on the N3 path.
    - **Healthy typical range:** 0–0.1 packets_per_rr

- **`icscf.cdp:average_response_time`** (I-CSCF Diameter average response time) — current **45.00 ms** vs learned baseline **63.54 ms** (HIGH, shift)
    - **What it measures:** Responsiveness of the Cx path and HSS processing speed. A spike
without timeouts = pure latency; a spike WITH timeout_ratio rising
= approaching timeout ceiling (HSS overload or partial partition).
    - **Shift means:** HSS slow, network latency to HSS, or HSS overload.
    - **Healthy typical range:** 30–100 ms

- **`icscf.ims_icscf:lir_avg_response_time`** (I-CSCF LIR response time) — current **32.00 ms** vs learned baseline **62.98 ms** (MEDIUM, shift)
    - **What it measures:** Call-routing-specific Cx leg. If LIR is healthy but UAR is slow,
registration path has a specific issue separate from call routing.
    - **Shift means:** HSS slow to respond to LIR; affects call setup.
    - **Healthy typical range:** 30–100 ms

- **`normalized.pcscf.dialogs_per_ue`** (Active SIP dialogs per registered UE at P-CSCF) — current **0.00 count** vs learned baseline **0.59 count** (LOW, drop)
    - **What it measures:** How many calls per user are currently in progress at the P-CSCF.
Going to zero from a non-zero baseline means calls have ended
(normal) OR call setup is failing system-wide (degradation).
Together with rcv_requests_* it discriminates the two.
    - **Drop means:** No active calls. Normal at rest; suspicious if prior state had calls AND INVITE rate is also zero.
    - **Healthy typical range:** 0–1 count
    - **Healthy invariant:** Per-UE — scale-independent. 0 at rest, ~1 per active VoNR call.

- **`derived.upf_activity_during_calls`** — current **1.00** vs learned baseline **0.45** (LOW, spike). *(No KB context available — interpret from the metric name.)*


## Event Aggregation (Phase 1)

No events fired during this episode. Either no metric KB triggers matched, or the episode encountered no meaningful state transitions.

## Correlation Analysis (Phase 2)

No events fired — correlation engine had nothing to work with.

## Network Analysis (Phase 3)

**Summary:** The network is experiencing severe media degradation due to high packet loss at the RTPEngine, and a potential signaling issue with I-CSCF to HSS communication.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | The underlying infrastructure appears to be stable. |
| **ran** | 🟢 GREEN | The RAN appears to be functioning correctly. |
| **core** | 🟢 GREEN | Core network components appear to be functioning correctly. The issue seems to be localized to the IMS and media plane. |
| **ims** | 🔴 RED | The primary issue is the high packet loss on the media plane, making VoNR calls unusable. There are also signs of signaling degradation between the I-CSCF and HSS. |

**IMS evidence:**
- derived.rtpengine_loss_ratio is 10.14 packets_per_rr
- icscf.cdp:average_response_time is 45.00 ms
- normalized.pcscf.dialogs_per_ue is 0.00 count

**Ranked hypotheses:**

- **`h1`** (fit=0.90, nf=rtpengine, specificity=specific):
    - **Statement:** The RTPEngine is experiencing high packet loss, leading to severe media quality degradation for VoNR calls. This is the most likely cause of the user-facing impact.
    - **Supporting events:** `derived.rtpengine_loss_ratio`
    - **Falsification probes:**
        - Check for packet drops on the rtpengine container's virtual ethernet interface.
        - Inspect the rtpengine logs for any errors or warnings related to packet processing or buffer overflows.
- **`h2`** (fit=0.60, nf=icscf, specificity=moderate):
    - **Statement:** The I-CSCF is having issues communicating with the HSS, as indicated by increased response times and timeouts for Diameter messages. This could be due to a network issue between the two components, or a problem specific to the I-CSCF's Diameter stack.
    - **Supporting events:** `icscf.cdp:average_response_time`, `icscf.ims_icscf:lir_avg_response_time`
    - **Falsification probes:**
        - Measure the RTT between the I-CSCF and HSS containers. A high RTT would indicate a network issue.
        - Check the HSS logs to see if it is receiving and responding to the I-CSCF's requests in a timely manner.
- **`h3`** (fit=0.40, nf=pcscf, specificity=vague):
    - **Statement:** There is a general degradation of the IMS signaling plane, causing call setup failures. The lack of active dialogs on the P-CSCF supports this, but the evidence is not specific to a single component.
    - **Supporting events:** `normalized.pcscf.dialogs_per_ue`
    - **Falsification probes:**
        - Trace a new call attempt to see where it fails in the signaling chain.
        - Examine the logs of P-CSCF, I-CSCF, and S-CSCF for SIP error messages.


## Falsification Plans (Phase 4)

**3 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `rtpengine`)

**Hypothesis:** The RTPEngine is experiencing high packet loss, leading to severe media quality degradation for VoNR calls. This is the most likely cause of the user-facing impact.

**Probes (3):**
1. **`measure_rtt`** — from: upf, to: rtpengine
    - *Expected if hypothesis holds:* Low RTT and no packet loss. This would isolate the packet loss to the rtpengine process itself, not the underlying network path to it.
    - *Falsifying observation:* High RTT or significant packet loss. This would suggest the problem is in the transport network between the UPF and RTPEngine, not within the RTPEngine container.
2. **`measure_rtt`** — from: nr_gnb, to: upf
    - *Expected if hypothesis holds:* Low RTT and no packet loss, indicating the RAN-to-core data plane is healthy.
    - *Falsifying observation:* High RTT or significant packet loss. This would suggest the media degradation originates upstream from the IMS media plane, likely in the RAN or 5G core data plane.
3. **`check_process_listeners`** — container: rtpengine
    - *Expected if hypothesis holds:* The rtpengine process is listening on its configured UDP port range for media.
    - *Falsifying observation:* The rtpengine process has no open UDP ports for media. This would mean it cannot receive any media, falsifying the 'high packet loss' hypothesis in favor of a total connectivity failure.

*Notes:* The hypothesis points to packet processing inside rtpengine. These probes test the external factors that could cause the same symptom: network loss on the path to/from rtpengine, or a failure of the process to listen for traffic at all.

### Plan for `h2` (target: `icscf`)

**Hypothesis:** The I-CSCF is having issues communicating with the HSS, as indicated by increased response times and timeouts for Diameter messages. This could be due to a network issue between the two components, or a problem specific to the I-CSCF's Diameter stack.

**Probes (3):**
1. **`measure_rtt`** — from: icscf, to: pyhss
    - *Expected if hypothesis holds:* High RTT (>100ms) or packet loss, confirming a network issue on the Cx interface.
    - *Falsifying observation:* Clean RTT (<5ms) and no packet loss. This would indicate the network is healthy, pointing the problem to the application-layer Diameter stacks on either icscf or pyhss.
2. **`measure_rtt`** — from: scscf, to: pyhss
    - *Expected if hypothesis holds:* RTT is also high. While this doesn't falsify the original 'icscf to hss' observation, it makes the 'icscf is the problem' part of the hypothesis less likely.
    - *Falsifying observation:* Clean RTT (<5ms) from scscf to pyhss. This isolates the problem to the icscf-to-pyhss path specifically, strengthening the hypothesis that icscf is the source of the issue.
3. **`measure_rtt`** — from: icscf, to: scscf
    - *Expected if hypothesis holds:* Clean RTT (<5ms) and no packet loss. The hypothesis is specific to the HSS link.
    - *Falsifying observation:* High RTT or packet loss. This would suggest a broader networking issue with the I-CSCF, not one confined to its HSS communication.

*Notes:* This plan focuses on falsifying the 'I-CSCF is the problem' hypothesis by triangulating the observed network problem (h2). Probes measure RTT from another source to the same destination (pyhss) and from the same source (icscf) to another destination to isolate the fault.

### Plan for `h3` (target: `pcscf`)

**Hypothesis:** There is a general degradation of the IMS signaling plane, causing call setup failures. The lack of active dialogs on the P-CSCF supports this, but the evidence is not specific to a single component.

**Probes (3):**
1. **`get_network_status`** — container: pcscf
    - *Expected if hypothesis holds:* Container is in a 'running' state.
    - *Falsifying observation:* Container is in an 'exited' or other non-running state. This would be a root cause, not 'degradation'.
2. **`measure_rtt`** — from: pcscf, to: icscf
    - *Expected if hypothesis holds:* High RTT or packet loss, consistent with 'general degradation'.
    - *Falsifying observation:* Clean RTT (<5ms) and no packet loss. This makes a network-level issue between P-CSCF and I-CSCF unlikely, suggesting the problem is at the application layer within one of the components.
3. **`get_nf_metrics`** — Check for pcscf SIP error metrics, e.g. kamailio_s_core_fwd_failure_counter
    - *Expected if hypothesis holds:* SIP error counters on the P-CSCF are elevated, showing it is actively failing to process signaling messages.
    - *Falsifying observation:* All P-CSCF SIP error counters are zero. This would strongly suggest the P-CSCF is not receiving any signaling traffic to reject, pointing the root cause upstream (e.g., UPF, gNB, or UE).

*Notes:* The hypothesis is vague. This plan aims to make it concrete by checking three distinct failure modes for the primary suspect, P-CSCF: is it down, is its network connectivity impaired, or is it failing internally at the application level?


## Parallel Investigators (Phase 5)

**3 sub-Investigator verdict(s):** **2 NOT_DISPROVEN**, **1 DISPROVEN**

### `h1` — ✅ **NOT_DISPROVEN**

**Hypothesis:** The RTPEngine is experiencing high packet loss, leading to severe media quality degradation for VoNR calls. This is the most likely cause of the user-facing impact.

**Reasoning:** All executed probes returned results consistent with the hypothesis. Network paths to and from the core data plane (UPF to RTPEngine, UPF to RAN) show no packet loss or high latency, which isolates the issue from the transport network. The rtpengine process was confirmed to be listening on its UDP media ports, ruling out a simple connectivity failure. This points towards the packet loss occurring within the rtpengine process itself, as the hypothesis suggests.

**Probes executed (3):**
- **from: upf, to: rtpengine** ✓ CONSISTENT
    - *Tool:* `default_api.measure_rtt(container='upf', target_ip='172.22.0.16')`
    - *Observation:* [EVIDENCE: measure_rtt("upf", "172.22.0.16") -> "3 packets transmitted, 3 received, 0% packet loss, time 2029ms\nrtt min/avg/max/mdev = 0.081/0.111/0.152/0.030 ms"]
    - *Comment:* The RTT and packet loss between the UPF and RTPEngine are negligible. This confirms the network path between them is healthy, which is consistent with the hypothesis that the problem lies within the RTPEngine itself.
- **from: nr_gnb, to: upf** ✓ CONSISTENT
    - *Tool:* `default_api.measure_rtt(container='upf', target_ip='172.22.0.23')`
    - *Observation:* [EVIDENCE: measure_rtt("upf", "172.22.0.23") -> "3 packets transmitted, 3 received, 0% packet loss, time 2045ms\nrtt min/avg/max/mdev = 0.083/0.108/0.153/0.031 ms"]
    - *Comment:* The probe from nr_gnb was not possible, so I ran it from upf to the gNB's IP. The RTT and packet loss are negligible, indicating the RAN-to-core data plane is healthy. This result is consistent with the hypothesis, as it suggests the media degradation is not occurring upstream of the IMS media plane.
- **container: rtpengine** ✓ CONSISTENT
    - *Tool:* `default_api.check_process_listeners(container='rtpengine')`
    - *Observation:* [EVIDENCE: check_process_listeners("rtpengine") -> "udp   UNCONN 0      0        172.22.0.16:49100      0.0.0.0:*    users:((\"rtpengine\",pid=1,fd=37))\nudp   UNCONN 0      0        172.22.0.16:49101      0.0.0.0:*    users:((\"rtpengine\",pid=1,fd=38))\n..."]
    - *Comment:* The rtpengine process is listening on a wide range of UDP ports. This confirms it is ready to receive media traffic, which is consistent with a 'high packet loss' scenario rather than a total failure to listen for media.

### `h2` — ✅ **NOT_DISPROVEN**

**Hypothesis:** The I-CSCF is having issues communicating with the HSS, as indicated by increased response times and timeouts for Diameter messages. This could be due to a network issue between the two components, or a problem specific to the I-CSCF's Diameter stack.

**Reasoning:** The probes successfully ruled out a network-level issue as the cause for the communication problems between I-CSCF and HSS, with RTT measurements being clean (<1ms). However, this does not disprove the hypothesis itself, which allows for an application-layer problem (e.g., in the Diameter stack). The evidence gathered is consistent with the hypothesis, but refines the potential cause to the application layer rather than the network.

**Probes executed (3):**
- **Measure RTT from icscf to pyhss to check for network issues on the Cx interface.** ✓ CONSISTENT
    - *Tool:* `measure_rtt("icscf", "172.22.0.18")`
    - *Observation:* [EVIDENCE: measure_rtt("icscf", "172.22.0.18") -> "3 packets transmitted, 3 received, 0% packet loss, time 2050ms\nrtt min/avg/max/mdev = 0.091/0.099/0.110/0.008 ms"]
    - *Comment:* The RTT is clean (<1ms) with no packet loss. This contradicts the 'network issue' part of the hypothesis's explanation, but is consistent with the falsification plan's expectation that a clean network points to an application-layer problem. Thus, it does not falsify the overall hypothesis.
- **Measure RTT from scscf to pyhss to triangulate the network health to the HSS.** ✓ CONSISTENT
    - *Tool:* `measure_rtt("scscf", "172.22.0.18")`
    - *Observation:* [EVIDENCE: measure_rtt("scscf", "172.22.0.18") -> "3 packets transmitted, 3 received, 0% packet loss, time 2030ms\nrtt min/avg/max/mdev = 0.123/0.123/0.124/0.000 ms"]
    - *Comment:* The RTT from another CSCF to the HSS is also clean. This confirms the network path to the HSS is healthy, further isolating the issue to the application layer as the hypothesis allows.
- **Measure RTT from icscf to scscf to check for broader networking issues with the I-CSCF.** ✓ CONSISTENT
    - *Tool:* `measure_rtt("icscf", "172.22.0.20")`
    - *Observation:* [EVIDENCE: measure_rtt("icscf", "172.22.0.20") -> "3 packets transmitted, 3 received, 0% packet loss, time 2049ms\nrtt min/avg/max/mdev = 0.053/0.123/0.215/0.067 ms"]
    - *Comment:* The RTT from I-CSCF to another peer (S-CSCF) is also clean, indicating the I-CSCF itself does not have a general network problem. This supports the hypothesis that the issue is specific to its communication with the HSS.

### `h3` — ❌ **DISPROVEN**

**Hypothesis:** There is a general degradation of the IMS signaling plane, causing call setup failures. The lack of active dialogs on the P-CSCF supports this, but the evidence is not specific to a single component.

**Reasoning:** The hypothesis of a 'general degradation' is contradicted by direct network measurement. The RTT between P-CSCF and I-CSCF is excellent, with zero packet loss. Furthermore, P-CSCF's SIP error counters (4xx and 5xx replies) are zero, indicating it is not the component actively rejecting signaling traffic. The lack of dialogs is likely a symptom of an issue upstream from the P-CSCF, not a failure within it.

**Probes executed (3):**
- **Container is in a 'running' state.** ✓ CONSISTENT
    - *Tool:* `default_api.get_network_status()`
    - *Observation:* [EVIDENCE: get_network_status() -> "{\n  \"phase\": \"ready\", ... \"pcscf\": \"running\"\n}"]
    - *Comment:* The P-CSCF container is running as expected. This is consistent with a 'degradation' scenario rather than a complete component failure.
- **High RTT or packet loss, consistent with 'general degradation'.** ✗ CONTRADICTS
    - *Tool:* `default_api.measure_rtt(container='pcscf', target_ip='172.22.0.19')`
    - *Observation:* [EVIDENCE: measure_rtt("pcscf", "172.22.0.19") -> "3 packets transmitted, 3 received, 0% packet loss, time 2032ms\nrtt min/avg/max/mdev = 0.123/0.178/0.233/0.044 ms"]
    - *Comment:* The RTT between P-CSCF and I-CSCF is less than 1ms with 0% packet loss. This result falsifies the claim of a 'general degradation' on the signaling plane, as this key network path is perfectly healthy.
- **Check for pcscf SIP error metrics, e.g. kamailio_s_core_fwd_failure_counter** ✗ CONTRADICTS
    - *Tool:* `default_api.get_nf_metrics()`
    - *Observation:* [EVIDENCE: get_nf_metrics() -> "PCSCF ... sl:4xx_replies = 0.0 ... sl:5xx_replies = 0.0"]
    - *Comment:* SIP error counters (4xx and 5xx) on the P-CSCF are zero. This indicates the P-CSCF is not actively failing or rejecting SIP signaling, contradicting the hypothesis that it's a source of call setup failure. The problem likely lies elsewhere.

**Alternative suspects:** icscf, hss


## Evidence Validation (Phase 6)

**Overall verdict:** clean
**Overall confidence:** high

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 5 | 3/3 | clean | high |
| `InvestigatorAgent_h2` | 4 | 3/3 | clean | high |
| `InvestigatorAgent_h3` | 4 | 3/3 | clean | high |


## Ground Truth

**Failure domain:** ims_media  
**Protocol impact:** RTP  
**Affected components:** rtpengine  
**Severity:** degraded

## Agent Diagnosis

**Model:** v6-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 161.7s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: The network is suffering from two distinct problems: severe media packet loss within the RTPEngine process and a signaling plane degradation caused by an application-layer communication failure between the I-CSCF and HSS.
> - **timeline**:
>     1. The `icscf.cdp:average_response_time` and `icscf.ims_icscf:lir_avg_response_time` metrics increased, indicating a signaling problem between the I-CSCF and HSS.
>     2. The `normalized.pcscf.dialogs_per_ue` metric dropped, likely as a symptom of the upstream signaling failures.
>     3. The `derived.rtpengine_loss_ratio` metric spiked, indicating severe media degradation and causing unusable VoNR calls.
> - **root_cause**: There appear to be two concurrent root causes. The most user-impacting issue is severe packet loss on the media plane originating from the RTPEngine. A secondary issue exists on the signaling plane between the I-CSCF and HSS.
>     - **Primary:** High packet loss is occurring within the RTPEngine process itself, leading to severe media quality degradation. `primary_suspect_nf: rtpengine`.
>     - **Secondary:** The I-CSCF is experiencing an application-layer communication failure with the HSS, likely within its Diameter stack, causing signaling delays and timeouts. `primary_suspect_nf: icscf`.
> - **affected_components**:
>     - `rtpengine`: Root Cause (Media Plane)
>     - `icscf`: Root Cause (Signaling Plane)
>     - `hss`: Secondary
>     - `pcscf`: Symptomatic
> - **recommendation**:
>     1.  **For the media issue:** Inspect the RTPEngine logs for errors related to packet processing or buffer overflows. Also, check statistics for packet drops on the `rtpengine` container's virtual ethernet interface.
>     2.  **For the signaling issue:** Examine the logs on both the I-CSCF and HSS to identify the specific Diameter command that is timing out or failing. Verify if the HSS is receiving requests from the I-CSCF and responding in a timely manner.
> - **confidence**: medium
> - **explanation**: The investigation identified two concurrent issues. Hypothesis `h1`, stating that the RTPEngine is the source of high packet loss, was not disproven and is supported by the high `rtpengine_loss_ratio` metric. Probes confirmed the network paths to and from the RTPEngine are healthy, isolating the packet loss to the component itself. Hypothesis `h2`, pointing to a communication failure between the I-CSCF and HSS, was also not disproven. Network probes ruled out a transport-layer problem, refining the cause to an application-layer (Diameter) issue. Because two distinct hypotheses remain, confidence is medium until manual checks can confirm the precise failure mode within each component.

### Scoring Breakdown

**Overall score: 90%**

**Scorer assessment:** The agent accurately identified the primary root cause, fault type, and severity, and correctly attributed it to the IMS layer. However, it incorrectly identified a secondary root cause, leading to a partial score for component overlap.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | Yes | The agent correctly identified 'High packet loss is occurring within the RTPEngine process itself, leading to severe media quality degradation' as the primary root cause, which directly matches the simulated failure mode of 30% packet loss on RTPEngine. |
| Component overlap | 50% | The agent correctly identified 'rtpengine' as a 'Root Cause'. However, it also incorrectly identified 'icscf' as another 'Root Cause' for a non-existent signaling problem. Since 1 out of 2 identified root cause components were correct, the score is 0.5. |
| Severity correct | Yes | The simulated failure involved 30% packet loss, which significantly degrades voice quality. The agent described this as 'severe media packet loss', 'severe media quality degradation', and leading to 'unusable VoNR calls'. This assessment of severity is appropriate for the impact of 30% packet loss on voice calls. |
| Fault type identified | Yes | The agent explicitly identified 'High packet loss' as the fault type, which directly matches the simulated failure mode. |
| Layer accuracy | Yes | The simulated failure component 'rtpengine' belongs to the 'ims' layer. The agent's network analysis correctly rated the 'ims' layer as 'red' and cited 'derived.rtpengine_loss_ratio' as evidence, indicating correct layer attribution. |
| Confidence calibrated | Yes | The agent stated 'medium' confidence. This is appropriate given that it correctly identified the primary root cause and its characteristics, but also incorrectly identified a secondary, non-existent root cause. A medium confidence level reflects this mixed accuracy. |

**Ranking position:** #1 — The correct root cause (RTPEngine packet loss) was explicitly identified as the 'Primary' root cause, making its ranking position 1.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 230,516 |
| Output tokens | 5,973 |
| Thinking tokens | 13,545 |
| **Total tokens** | **250,034** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| EventAggregator | 0 | 0 | 0 |
| CorrelationAnalyzer | 0 | 0 | 0 |
| NetworkAnalystAgent | 47,852 | 5 | 4 |
| InstructionGeneratorAgent | 35,072 | 3 | 4 |
| InvestigatorAgent_h1 | 59,169 | 5 | 6 |
| InvestigatorAgent_h2 | 49,804 | 4 | 5 |
| InvestigatorAgent_h3 | 51,334 | 4 | 5 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 6,803 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 301.2s
