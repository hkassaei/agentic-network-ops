# Episode Report: Call Quality Degradation

**Agent:** v6  
**Episode ID:** ep_20260501_152945_call_quality_degradation  
**Date:** 2026-05-01T15:29:47.459781+00:00  
**Duration:** 399.6s  

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
- **Nodes with significant deltas:** 3
- **Nodes with any drift:** 5

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 44.97 (per-bucket threshold: 28.18, context bucket (1, 1), trained on 323 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following metrics deviate from their learned-healthy baseline. Treat each as a semantic observation (meaning + numbers), not a number alone — the KB's interpretation is the authoritative reading.

- **`derived.rtpengine_loss_ratio`** (RTPEngine RTCP-reported per-RR average packet loss) — current **28.26 packets_per_rr** vs learned baseline **0.00 packets_per_rr** (MEDIUM, spike)
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

- **`derived.upf_activity_during_calls`** (UPF activity consistency with active dialogs) — current **0.04 ratio** vs learned baseline **0.54 ratio** (MEDIUM, drop)
    - **What it measures:** Cross-layer consistency check between IMS dialog state and UPF
throughput. A drop while dialogs_per_ue is non-zero is a
smoking-gun signal for media-plane failure independent of signaling.
    - **Drop means:** Active calls reported but no media flowing — media path broken (UPF, RTPEngine, or N3 packet loss).
    - **Healthy typical range:** 0.3–1 ratio
    - **Healthy invariant:** 1.0 when traffic fully follows active calls; 0.0 when signaling says active but data plane is silent.

- **`normalized.icscf.cdp_replies_per_ue`** (I-CSCF Diameter reply rate per UE) — current **0.01 replies_per_second_per_ue** vs learned baseline **0.03 replies_per_second_per_ue** (MEDIUM, drop)
    - **What it measures:** Liveness of the I-CSCF↔HSS Cx path. Drops to 0 when HSS is unreachable OR when no signaling is occurring at the I-CSCF (idle or upstream P-CSCF partitioned).
    - **Drop means:** No Cx replies in the window. Could be healthy idle OR a Cx-path fault.
    - **Healthy typical range:** 0–1 replies_per_second_per_ue

- **`normalized.pcscf.dialogs_per_ue`** (Active SIP dialogs per registered UE at P-CSCF) — current **4.00 count** vs learned baseline **0.48 count** (MEDIUM, spike)
    - **What it measures:** How many calls per user are currently in progress at the P-CSCF.
Going to zero from a non-zero baseline means calls have ended
(normal) OR call setup is failing system-wide (degradation).
Together with rcv_requests_* it discriminates the two.
    - **Spike means:** Calls ending or setup failing.
    - **Healthy typical range:** 0–1 count
    - **Healthy invariant:** Per-UE — scale-independent. 0 at rest, ~1 per active VoNR call.

- **`normalized.smf.bearers_per_ue`** (Active QoS bearers per UE) — current **5.00 count** vs learned baseline **2.48 count** (MEDIUM, spike)
    - **What it measures:** Per-UE count of active QoS bearers. Baseline reflects default
bearers; increments during VoNR calls indicate dedicated voice
bearers being set up. Drop during an active call = dedicated
bearer torn down unexpectedly (voice will fail).
    - **Spike means:** Expected during VoNR calls (1 extra bearer per active call).
    - **Healthy typical range:** 2–3.5 count
    - **Healthy invariant:** At rest: equals configured default bearers (typically 2 per UE).
During active VoNR call: +1 per caller. The per-UE ratio is the
invariant; absolute count scales with UE pool.

- **`normalized.upf.gtp_indatapktn3upf_per_ue`** (GTP-U uplink rate per UE (N3)) — current **9.37 packets_per_second** vs learned baseline **1.45 packets_per_second** (MEDIUM, spike)
    - **What it measures:** Health of the uplink user-plane path gNB → UPF. Drops to near-zero
during RAN or N3 outage; stays nonzero during active calls or data
sessions. Decoupled from SIP signaling (signals data plane, not
control plane).
    - **Spike means:** Either UEs not generating uplink traffic (no calls/data) or N3 path is degraded.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE — constant regardless of UE pool size. Rises during active VoNR calls (~100 pps for G.711 voice) and data transfer.

- **`normalized.upf.gtp_outdatapktn3upf_per_ue`** (GTP-U downlink rate per UE (N3)) — current **6.62 packets_per_second** vs learned baseline **1.45 packets_per_second** (MEDIUM, spike)
    - **What it measures:** Health of the downlink user-plane path UPF → gNB. Typically mirrors
uplink rate during calls/data; asymmetry indicates directional
faults (e.g., UPF receiving from internet but not forwarding).
    - **Spike means:** Downlink data plane degraded — UPF not forwarding to gNB.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE — constant regardless of UE pool size. Roughly symmetric with uplink during healthy calls.

- **`normalized.icscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at I-CSCF) — current **0.03 requests_per_second** vs learned baseline **0.06 requests_per_second** (LOW, drop)
    - **What it measures:** Health of the P-CSCF → I-CSCF forwarding path (Mw interface). When
this drops to zero while P-CSCF REGISTER rate is still non-zero,
it's the SIGNATURE of an IMS partition between P-CSCF and I-CSCF.
    - **Drop means:** Either UEs not registering at all, or P-CSCF isolated from I-CSCF.
    - **Healthy typical range:** 0–0.5 requests_per_second
    - **Healthy invariant:** Per-UE rate. Should closely track ims.pcscf.rcv_requests_register_per_ue.

- **`normalized.pcscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at P-CSCF) — current **0.03 requests_per_second** vs learned baseline **0.06 requests_per_second** (LOW, drop)
    - **What it measures:** How actively UEs are refreshing their IMS registrations with the
P-CSCF. REGISTERs arrive periodically (re-registration timer) plus
at attach. Sustained zero means UEs cannot reach P-CSCF OR the
UE-to-network SIP path is broken.
    - **Drop means:** No REGISTERs flowing. Unusual unless UEs are all deregistered.
    - **Healthy typical range:** 0–0.5 requests_per_second
    - **Healthy invariant:** Per-UE rate — same value at any deployment scale.

- **`normalized.scscf.cdp_replies_per_ue`** (S-CSCF CDP Diameter replies per UE) — current **0.03 replies_per_second_per_ue** vs learned baseline **0.06 replies_per_second_per_ue** (LOW, drop)
    - **What it measures:** Active S-CSCF Diameter traffic with HSS. Near-zero when registrations idle OR HSS partition.
    - **Drop means:** No active S-CSCF Diameter exchanges (idle or partitioned).
    - **Healthy typical range:** 0–1 replies_per_second_per_ue
    - **Healthy invariant:** Per-UE rate; varies with registration/auth load.


## Event Aggregation (Phase 1)

**1 events fired during the observation window:**

- `core.upf.activity_during_calls_collapsed` (source: `core.upf.activity_during_calls`, nf: `upf`, t=1777649505.2)  [current_value=0.0464785]

## Correlation Analysis (Phase 2)

1 events fired but no composite hypothesis emerged. The events may be from independent faults or lack registered correlation hints in the KB.

## Network Analysis (Phase 3)

**Summary:** The network experienced a temporary media plane outage, indicated by a collapse in UPF activity during calls and high packet loss reported by RTPEngine; the primary suspects are the UPF and RTPEngine.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | All required containers are running and network links are active. No evidence of an infrastructure-level fault. |
| **ran** | 🟢 GREEN | No metrics indicate a RAN-layer fault. UEs are attached and bearers are established. |
| **core** | 🔴 RED | The UPF stopped forwarding media traffic, triggering the 'upf_activity_during_calls_collapsed' event. Although throughput has recovered, the initial failure points to a critical fault in the core data plane. |
| **ims** | 🟡 YELLOW | RTPEngine reported significant packet loss, and P-CSCF shows an abnormally high number of dialogs, suggesting calls are not clearing correctly. This appears to be a symptom of the upstream data plane failure at the UPF. |

**CORE evidence:**
- derived.upf_activity_during_calls
- normalized.upf.gtp_indatapktn3upf_per_ue
- normalized.upf.gtp_outdatapktn3upf_per_ue

**IMS evidence:**
- derived.rtpengine_loss_ratio
- normalized.pcscf.dialogs_per_ue

**Ranked hypotheses:**

- **`h1`** (fit=0.90, nf=upf, specificity=specific):
    - **Statement:** The UPF is the source of a temporary media plane failure, causing an outage on the N3 data plane that resulted in dropped RTP packets.
    - **Supporting events:** `core.upf.activity_during_calls_collapsed`
    - **Falsification probes:**
        - Check UPF logs for errors, restarts, or resource exhaustion events coinciding with the anomaly timestamp.
        - Query historical metrics to confirm if UPF's GTP packet counters (in/out) dropped to zero during the exact window of the anomaly.
- **`h2`** (fit=0.70, nf=rtpengine, specificity=specific):
    - **Statement:** RTPEngine is the source of the media plane degradation, experiencing a fault that is causing it to drop packets.
    - **Falsification probes:**
        - Check RTPEngine logs for internal errors, packet discard reports, or stall events.
        - Measure RTT and packet loss on the path between the UPF and RTPEngine to rule out a network partition between them.


## Falsification Plans (Phase 4)

**2 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `upf`)

**Hypothesis:** The UPF is the source of a temporary media plane failure, causing an outage on the N3 data plane that resulted in dropped RTP packets.

**Probes (3):**
1. **`get_network_status`** — Check if the UPF container is running.
    - *Expected if hypothesis holds:* The UPF container is running, as the hypothesis suggests a temporary/transient fault, not a crash.
    - *Falsifying observation:* The UPF container is not in a running state, which would indicate a container-level crash rather than a transient media plane fault.
2. **`get_dp_quality_gauges`** — Get data-plane quality metrics for the UPF for a window around the anomaly time.
    - *Expected if hypothesis holds:* A sharp drop in packet rates and throughput for GTP-U traffic traversing the UPF, corroborating the 'activity_during_calls_collapsed' event.
    - *Falsifying observation:* The UPF's data plane metrics remain stable and show no significant drop in traffic, suggesting it was correctly forwarding all traffic it received.
3. **`get_network_status`** — Check the status of the SMF container.
    - *Expected if hypothesis holds:* The SMF container is running. A failure in the UPF's media plane should not be caused by the SMF.
    - *Falsifying observation:* The SMF container is not in a running state. This would suggest a control plane issue originating from the SMF might be the root cause.

*Notes:* This plan tests the integrity of the UPF, the primary suspect for the core data plane failure. It checks for container crashes versus transient faults and looks for direct evidence of a data plane traffic drop.

### Plan for `h2` (target: `rtpengine`)

**Hypothesis:** RTPEngine is the source of the media plane degradation, experiencing a fault that is causing it to drop packets.

**Probes (3):**
1. **`measure_rtt`** — Measure RTT and packet loss from the UPF to the RTPEngine.
    - *Expected if hypothesis holds:* High RTT or packet loss is observed on the path.
    - *Falsifying observation:* The probe's reading is inconsistent with rtpengine being the source (e.g. the metric stays at its healthy baseline, or the loss is observed on a path that does not traverse rtpengine).
2. **`measure_rtt`** — Measure RTT and packet loss from the UPF to the P-CSCF as a partner probe.
    - *Expected if hypothesis holds:* The RTT and packet loss reading is normal, indicating the path from the UPF is generally healthy and the issue is specific to the path terminating at RTPEngine.
    - *Falsifying observation:* High RTT or packet loss is also observed on this path. This suggests the problem is more likely with the UPF or the shared network infrastructure, not isolated to RTPEngine.
3. **`get_dp_quality_gauges`** — Get data-plane quality metrics for RTPEngine for a window around the anomaly time.
    - *Expected if hypothesis holds:* RTPEngine's metrics show a high rate of discarded packets or a significant drop in media quality (e.g., MOS score).
    - *Falsifying observation:* RTPEngine's metrics show no anomalous behavior, indicating it was processing media streams correctly.

*Notes:* This plan addresses the linter feedback by using a compositional probe with a partner to isolate RTPEngine from the UPF and the network path. It also avoids mechanism-scoping language in the expected/falsifying observations.


## Parallel Investigators (Phase 5)

**2 sub-Investigator verdict(s):** **2 NOT_DISPROVEN**

### `h1` — ✅ **NOT_DISPROVEN**

**Hypothesis:** The UPF is the source of a temporary media plane failure, causing an outage on the N3 data plane that resulted in dropped RTP packets.

**Reasoning:** [Multi-shot consensus — both shots returned NOT_DISPROVEN.]

Shot 1: All probes executed were consistent with the hypothesis. The UPF and SMF containers were running, which aligns with a transient fault rather than a crash. Crucially, data plane quality metrics for the UPF during the anomaly window show a drop in packet rates between its input and output, which directly supports the claim of packet loss within the UPF's media plane.

Shot 2: All executed probes were consistent with the hypothesis. The UPF and SMF containers were confirmed to be in a running state, which supports the premise of a transient fault rather than a component crash. Most importantly, data plane quality metrics taken at the time of the anomaly show a clear discrepancy between the UPF's incoming and outgoing packet rates, which directly supports the hypothesis that the UPF was dropping packets on the N3 data plane.

**Probes executed (3):**
- **Check if the UPF container is running.** ✓ CONSISTENT
    - *Tool:* `print(default_api.get_network_status())`
    - *Observation:* [EVIDENCE: get_network_status() -> "'upf': 'running'"]
    - *Comment:* The hypothesis suggests a transient fault, not a container crash. The UPF container being in a running state is consistent with this expectation.
- **Get data-plane quality metrics for the UPF for a window around the anomaly time.** ✓ CONSISTENT
    - *Tool:* `print(default_api.get_dp_quality_gauges(at_time_ts = 1777649444.0041094, window_seconds = 120))`
    - *Observation:* [EVIDENCE: get_dp_quality_gauges(at_time_ts=1777649444.0041094, window_seconds=120) -> "UPF:\n    in  packets/sec: 18.4\n    out packets/sec: 15.3"]
    - *Comment:* A drop from 18.4 pps (in) to 15.3 pps (out) indicates packet loss within the UPF, which aligns with the hypothesis that the UPF is the source of dropped packets. This is not the stable traffic pattern expected in the falsifying observation.
- **Check the status of the SMF container.** ✓ CONSISTENT
    - *Tool:* `print(default_api.get_network_status())`
    - *Observation:* [EVIDENCE: get_network_status() -> "'smf': 'running'"]
    - *Comment:* The SMF container is running, which makes it less likely that a control plane issue originating from a crashed SMF caused the data plane failure at the UPF. This supports the hypothesis that the fault is located at the UPF itself.

### `h2` — ✅ **NOT_DISPROVEN**

**Hypothesis:** RTPEngine is the source of the media plane degradation, experiencing a fault that is causing it to drop packets.

**Reasoning:** [Multi-shot consensus — both shots returned NOT_DISPROVEN.]

Shot 1: All three probes executed were consistent with the hypothesis. The RTT measurement from the UPF to the RTPEngine showed significant packet loss, while a partner probe to the P-CSCF showed a healthy path, suggesting the issue is specific to the RTPEngine or its link. Crucially, RTPEngine's own data plane quality metrics from the time of the anomaly confirm a high packet loss rate of 14.16%.

Shot 2: All probes executed returned results consistent with the hypothesis. A live RTT measurement from the UPF to RTPEngine showed significant packet loss, while a partner probe to the P-CSCF showed a healthy connection, isolating the issue to the RTPEngine or its direct path. Furthermore, historical data plane metrics for RTPEngine at the time of the anomaly confirm it was experiencing a high rate of packet loss (14.16%). No probe produced evidence that contradicts the hypothesis.

**Probes executed (3):**
- **Measure RTT and packet loss from the UPF to the RTPEngine.** ✓ CONSISTENT
    - *Tool:* `measure_rtt(container='upf', target_ip='172.22.0.16')`
    - *Observation:* [EVIDENCE: measure_rtt('upf', '172.22.0.16') -> "3 packets transmitted, 1 received, 66.6667% packet loss"]
    - *Comment:* Significant packet loss was observed on the path from the UPF to the RTPEngine. This aligns with the hypothesis but could also be caused by the UPF or the network path, as noted in the plan's 'conflates_with'.
- **Measure RTT and packet loss from the UPF to the P-CSCF as a partner probe.** ✓ CONSISTENT
    - *Tool:* `measure_rtt(container='upf', target_ip='172.22.0.21')`
    - *Observation:* [EVIDENCE: measure_rtt('upf', '172.22.0.21') -> "3 packets transmitted, 3 received, 0% packet loss"]
    - *Comment:* The path from the UPF to the P-CSCF is healthy. This partner probe suggests the fault does not originate at the UPF's egress but rather on the specific path to RTPEngine or at RTPEngine itself, thus strengthening the hypothesis.
- **Get data-plane quality metrics for RTPEngine for a window around the anomaly time.** ✓ CONSISTENT
    - *Tool:* `get_dp_quality_gauges(at_time_ts=1777649444.0041094)`
    - *Observation:* [EVIDENCE: get_dp_quality_gauges(at_time_ts=1777649444.0041094) -> "RTPEngine: loss (recent): 14.16"]
    - *Comment:* RTPEngine's metrics show a very high recent packet loss of 14.16% at the time of the anomaly. This is strong, direct evidence that RTPEngine was indeed dropping packets, as the hypothesis states.


## Evidence Validation (Phase 6)

**Overall verdict:** clean
**Overall confidence:** high

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 4 | 3/3 | clean | high |
| `InvestigatorAgent_h2` | 8 | 3/3 | clean | high |


## Ground Truth

**Failure domain:** ims_media  
**Protocol impact:** RTP  
**Affected components:** rtpengine  
**Severity:** degraded

## Agent Diagnosis

**Model:** v6-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 254.0s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: A temporary media plane outage was caused by packet loss, with evidence pointing to faults in both the UPF and RTPEngine, making it impossible to isolate a single root cause.
> - **timeline**:
>     1. The UPF's media plane activity collapsed during active calls, indicating it stopped forwarding traffic.
>     2. RTPEngine began reporting a high rate of packet loss (14.16%).
>     3. The P-CSCF began accumulating a high number of active dialogs, suggesting calls were failing to clear properly due to the media plane disruption.
> - **root_cause**: The root cause is a media plane failure leading to packet loss. However, investigations could not definitively isolate the fault between two primary suspects: the UPF and RTPEngine. Both components exhibit evidence of dropping packets, and their respective hypotheses were not disproven.
> - **affected_components**:
>     - `upf`: Root Cause
>     - `rtpengine`: Root Cause
>     - `pcscf`: Symptomatic
> - **recommendation**: Check for network-level packet loss on the physical or virtual link between the UPF and RTPEngine to determine if a shared infrastructure component is the true root cause. Correlate the exact timestamps of packet drop counters in UPF and RTPEngine logs to identify which component failed first.
> - **confidence**: medium
> - **verdict_kind**: inconclusive
> - **explanation**: A media plane outage occurred, triggered by the `upf_activity_during_calls_collapsed` event. The investigation considered two primary hypotheses. Hypothesis h1, blaming the UPF, was supported by metrics showing a drop in packet rates between the UPF's input and output. Hypothesis h2, blaming RTPEngine, was supported by RTPEngine's own high packet loss metrics and by RTT probes showing packet loss on its specific path from the UPF. Since both hypotheses were supported by consistent evidence and neither could be falsified, confidence is medium. The fault could be a cascade or the current evidence is insufficient to distinguish between the two surviving candidates.

### Scoring Breakdown

**Overall score: 30%**

**Scorer assessment:** The agent correctly identified packet loss as the fault type and listed RTPEngine as a root cause candidate, but failed to isolate it as the sole root cause, incorrectly included UPF as an equally likely root cause, overstated the severity, and misattributed a root cause to the wrong layer. Its medium confidence was not well-calibrated for an inconclusive diagnosis with significant inaccuracies.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | No | The simulated failure was 30% packet loss on RTPEngine. The agent correctly identified 'media plane failure leading to packet loss' but failed to definitively isolate RTPEngine as the sole root cause. Instead, it presented both UPF and RTPEngine as equally likely 'Root Cause' candidates and explicitly stated it 'could not definitively isolate the fault', which, per the scoring rules, makes the root cause identification incorrect due to ambiguity and the inclusion of an incorrect co-equal root cause (UPF). |
| Component overlap | 100% | The primary affected component, 'rtpengine', is explicitly listed under 'affected_components' with the label 'Root Cause'. While the UPF was also incorrectly listed as a 'Root Cause', the rule states to score 1.0 if the primary affected component is listed as 'Root Cause'. |
| Severity correct | No | The simulated failure was a 'degradation' (30% packet loss). The agent repeatedly used the term 'media plane outage' in its summary and explanation, which implies a complete failure (100% loss), overstating the actual severity of the 30% packet loss. |
| Fault type identified | Yes | The simulated failure mode was 'packet loss'. The agent correctly identified 'packet loss' as the core fault type in its summary, root cause, and explanation. |
| Layer accuracy | No | The simulated root cause component 'rtpengine' belongs to the 'ims' layer. While the agent correctly noted 'ims' layer issues related to RTPEngine, it also incorrectly attributed a root cause to the 'core' layer (UPF) by rating the 'core' layer 'red' and considering the UPF a primary suspect. This constitutes attributing a root cause failure to the wrong layer. |
| Confidence calibrated | No | The agent's confidence is 'medium' for an 'inconclusive' diagnosis that incorrectly identifies a co-equal root cause (UPF), overstates severity ('outage' for 30% packet loss), and incorrectly attributes a root cause to the wrong layer. Given these significant inaccuracies and the inconclusive nature, 'medium' confidence is not well-calibrated; a lower confidence would be more appropriate. |

**Ranking:** The agent explicitly stated it 'could not definitively isolate the fault between two primary suspects: the UPF and RTPEngine.' This means it did not rank 'rtpengine' as the primary root cause, but rather as one of two equally likely candidates. Per the scoring rules, if the correct cause is not named as the PRIMARY root cause (due to ties or ambiguity), it is not considered position 1.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 235,394 |
| Output tokens | 6,760 |
| Thinking tokens | 19,783 |
| **Total tokens** | **261,937** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| EventAggregator | 0 | 0 | 0 |
| CorrelationAnalyzer | 0 | 0 | 0 |
| NetworkAnalystAgent | 58,845 | 4 | 5 |
| Phase 3 NetworkAnalyst__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 38,774 | 2 | 3 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 19,402 | 1 | 2 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| InvestigatorAgent_h1 | 20,367 | 2 | 2 |
| InvestigatorAgent_h1 | 30,576 | 2 | 3 |
| InvestigatorAgent_h1__reconciliation | 0 | 0 | 0 |
| InvestigatorAgent_h2 | 32,859 | 4 | 3 |
| InvestigatorAgent_h2 | 54,697 | 4 | 5 |
| InvestigatorAgent_h2__reconciliation | 0 | 0 | 0 |
| Phase5FanOutAudit | 0 | 0 | 0 |
| Phase6.5CandidatePool | 0 | 0 | 0 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 6,417 | 0 | 1 |
| Phase 7 Synthesis__guardrail | 0 | 0 | 0 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 399.6s
