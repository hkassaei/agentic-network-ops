# Episode Report: Call Quality Degradation

**Agent:** v6  
**Episode ID:** ep_20260502_171328_call_quality_degradation  
**Date:** 2026-05-02T17:13:29.540309+00:00  
**Duration:** 463.4s  

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
- **Nodes with significant deltas:** 5
- **Nodes with any drift:** 6

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 44.30 (per-bucket threshold: 25.22, context bucket (1, 0), trained on 323 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following metrics deviate from their learned-healthy baseline. Treat each as a semantic observation (meaning + numbers), not a number alone — the KB's interpretation is the authoritative reading.

- **`derived.rtpengine_loss_ratio`** (RTPEngine RTCP-reported per-RR average packet loss) — current **22.79 packets_per_rr** vs learned baseline **0.00 packets_per_rr** (MEDIUM, spike)
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

- **`normalized.icscf.cdp_replies_per_ue`** (I-CSCF Diameter reply rate per UE) — current **0.03 replies_per_second_per_ue** vs learned baseline **0.03 replies_per_second_per_ue** (MEDIUM, shift)
    - **What it measures:** Liveness of the I-CSCF↔HSS Cx path. Drops to 0 when HSS is unreachable OR when no signaling is occurring at the I-CSCF (idle or upstream P-CSCF partitioned).
    - **Shift means:** I-CSCF is actively conversing with HSS — healthy.
    - **Healthy typical range:** 0–1 replies_per_second_per_ue

- **`normalized.icscf.core:rcv_requests_invite_per_ue`** (SIP INVITE rate per UE at I-CSCF) — current **0.03 requests_per_second** vs learned baseline **0.00 requests_per_second** (MEDIUM, spike)
    - **What it measures:** Health of call-setup forwarding P-CSCF → I-CSCF. Partition signature
same as REGISTER rate.
    - **Spike means:** Forwarding failure.
    - **Healthy typical range:** 0–0.2 requests_per_second
    - **Healthy invariant:** Per-UE rate. Tracks pcscf.invite rate.

- **`normalized.pcscf.core:rcv_requests_invite_per_ue`** (SIP INVITE rate per UE at P-CSCF) — current **0.06 requests_per_second** vs learned baseline **0.00 requests_per_second** (MEDIUM, spike)
    - **What it measures:** Call attempt rate from registered UEs. Unlike REGISTER (periodic),
INVITEs only fire when UEs place calls. Zero is normal during
quiet periods; nonzero INVITE with zero dialogs is the signature
of call setup failure.
    - **Spike means:** Fewer call attempts.
    - **Healthy typical range:** 0–0.2 requests_per_second
    - **Healthy invariant:** Per-UE rate.

- **`normalized.pcscf.dialogs_per_ue`** (Active SIP dialogs per registered UE at P-CSCF) — current **2.00 count** vs learned baseline **0.48 count** (MEDIUM, spike)
    - **What it measures:** How many calls per user are currently in progress at the P-CSCF.
Going to zero from a non-zero baseline means calls have ended
(normal) OR call setup is failing system-wide (degradation).
Together with rcv_requests_* it discriminates the two.
    - **Spike means:** Calls ending or setup failing.
    - **Healthy typical range:** 0–1 count
    - **Healthy invariant:** Per-UE — scale-independent. 0 at rest, ~1 per active VoNR call.

- **`normalized.scscf.core:rcv_requests_invite_per_ue`** (SIP INVITE rate per UE at S-CSCF) — current **0.06 requests_per_second** vs learned baseline **0.00 requests_per_second** (MEDIUM, spike)
    - **What it measures:** S-CSCF participation in call setup. Zero when calls aren't being
placed OR S-CSCF not receiving forwarded INVITEs.
    - **Spike means:** Upstream forwarding issue.
    - **Healthy typical range:** 0–0.2 requests_per_second
    - **Healthy invariant:** Per-UE rate.

- **`normalized.smf.bearers_per_ue`** (Active QoS bearers per UE) — current **4.00 count** vs learned baseline **2.48 count** (MEDIUM, spike)
    - **What it measures:** Per-UE count of active QoS bearers. Baseline reflects default
bearers; increments during VoNR calls indicate dedicated voice
bearers being set up. Drop during an active call = dedicated
bearer torn down unexpectedly (voice will fail).
    - **Spike means:** Expected during VoNR calls (1 extra bearer per active call).
    - **Healthy typical range:** 2–3.5 count
    - **Healthy invariant:** At rest: equals configured default bearers (typically 2 per UE).
During active VoNR call: +1 per caller. The per-UE ratio is the
invariant; absolute count scales with UE pool.

- **`normalized.upf.gtp_indatapktn3upf_per_ue`** (GTP-U uplink rate per UE (N3)) — current **7.04 packets_per_second** vs learned baseline **1.45 packets_per_second** (MEDIUM, spike)
    - **What it measures:** Health of the uplink user-plane path gNB → UPF. Drops to near-zero
during RAN or N3 outage; stays nonzero during active calls or data
sessions. Decoupled from SIP signaling (signals data plane, not
control plane).
    - **Spike means:** Either UEs not generating uplink traffic (no calls/data) or N3 path is degraded.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE — constant regardless of UE pool size. Rises during active VoNR calls (~100 pps for G.711 voice) and data transfer.

- **`normalized.upf.gtp_outdatapktn3upf_per_ue`** (GTP-U downlink rate per UE (N3)) — current **6.10 packets_per_second** vs learned baseline **1.45 packets_per_second** (MEDIUM, spike)
    - **What it measures:** Health of the downlink user-plane path UPF → gNB. Typically mirrors
uplink rate during calls/data; asymmetry indicates directional
faults (e.g., UPF receiving from internet but not forwarding).
    - **Spike means:** Downlink data plane degraded — UPF not forwarding to gNB.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE — constant regardless of UE pool size. Roughly symmetric with uplink during healthy calls.

- **`derived.upf_activity_during_calls`** (UPF activity consistency with active dialogs) — current **0.07 ratio** vs learned baseline **0.54 ratio** (LOW, drop)
    - **What it measures:** Cross-layer consistency check between IMS dialog state and UPF
throughput. A drop while dialogs_per_ue is non-zero is a
smoking-gun signal for media-plane failure independent of signaling.
    - **Drop means:** Active calls reported but no media flowing — media path broken (UPF, RTPEngine, or N3 packet loss).
    - **Healthy typical range:** 0.3–1 ratio
    - **Healthy invariant:** 1.0 when traffic fully follows active calls; 0.0 when signaling says active but data plane is silent.


## Event Aggregation (Phase 1)

**1 events fired during the observation window:**

- `core.upf.activity_during_calls_collapsed` (source: `core.upf.activity_during_calls`, nf: `upf`, t=1777742128.4)  [current_value=0.095168]

## Correlation Analysis (Phase 2)

1 events fired but no composite hypothesis emerged. The events may be from independent faults or lack registered correlation hints in the KB.

## Network Analysis (Phase 3)

**Summary:** The system is experiencing severe media plane degradation, with evidence strongly pointing to the RTPEngine as the source of packet loss.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | All network function containers are running and all network links are active. |
| **ran** | 🟢 GREEN | No evidence of a RAN-layer fault. UEs are attached and able to generate traffic. |
| **core** | 🟢 GREEN | Core network functions, including the UPF, appear to be operating correctly. The UPF is handling a high volume of user plane traffic, and QoS bearers are established as expected for calls. The issue appears to be downstream of the core data plane. |
| **ims** | 🔴 RED | The IMS media plane is highly degraded. RTPEngine is reporting a massive packet loss ratio (40), indicating voice calls will be unintelligible or silent. While signaling components appear stable, the media relay itself is failing. |

**IMS evidence:**
- derived.rtpengine_loss_ratio
- core.upf.activity_during_calls_collapsed

**Ranked hypotheses:**

- **`h1`** (fit=0.90, nf=rtpengine, specificity=specific):
    - **Statement:** RTPEngine is the source of extensive packet loss on the media plane. While the UPF is processing a high volume of user plane traffic, RTPEngine's own metrics report a severe packet loss ratio, indicating it is failing to relay RTP packets correctly.
    - **Supporting events:** `core.upf.activity_during_calls_collapsed`
    - **Falsification probes:**
        - Inspect RTPEngine's internal kernel or userspace packet drop counters.
        - Capture packets on RTPEngine's network interface to verify if RTP packets are arriving from the UPF but not being relayed outbound.
        - Review RTPEngine's container logs for errors related to packet processing, buffer overflows, or resource exhaustion.


## Falsification Plans (Phase 4)

**1 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `rtpengine`)

**Hypothesis:** RTPEngine is the source of extensive packet loss on the media plane. While the UPF is processing a high volume of user plane traffic, RTPEngine's own metrics report a severe packet loss ratio, indicating it is failing to relay RTP packets correctly.

**Probes (3):**
1. **`get_dp_quality_gauges`** — Returns rate-based MOS/loss/jitter alongside RTPEngine errors.
    - *Expected if hypothesis holds:* A non-zero value for `rtpengine.errors_per_second`, confirming that RTPEngine is encountering and reporting errors.
    - *Falsifying observation:* The value for `rtpengine.errors_per_second` is zero, suggesting the component is not aware of any processing errors.
2. **`get_dp_quality_gauges`** — window_seconds=120 to confirm MOS drop and packet-loss percentage across the same window
    - *Expected if hypothesis holds:* The value for `rtpengine.loss_ratio` is high (e.g., > 0.1), confirming the primary symptom from the NA report.
    - *Falsifying observation:* The value for `rtpengine.loss_ratio` is within the typical healthy range (0.0, 0.1), which contradicts the evidence the hypothesis is based on.
3. **`get_dp_quality_gauges`** — Check UPF in/out symmetry in the output.
    - *Expected if hypothesis holds:* UPF packet counters for uplink (N3-in vs N6-out) and downlink (N6-in vs N3-out) are roughly symmetric, indicating the UPF is forwarding traffic correctly and the packet loss occurs at RTPEngine.
    - *Falsifying observation:* UPF packet counters are asymmetric (e.g., N3-in is much higher than N6-out), which points to the UPF as the source of packet loss, falsifying the hypothesis that RTPEngine is the sole source.

*Notes:* The plan focuses on verifying the three key conditions of the hypothesis: RTPEngine is reporting errors, its loss ratio is high, and the adjacent UPF is not the source of the loss. This is anchored to the 'RTP media -- voice call active' step (12) of the 'vonr_call_setup' flow.


## Parallel Investigators (Phase 5)

**2 sub-Investigator verdict(s):** **1 DISPROVEN**, **1 NOT_DISPROVEN**

### `h1` — ❌ **DISPROVEN**

**Hypothesis:** RTPEngine is the source of extensive packet loss on the media plane. While the UPF is processing a high volume of user plane traffic, RTPEngine's own metrics report a severe packet loss ratio, indicating it is failing to relay RTP packets correctly.

**Reasoning:** [Multi-shot consensus — both shots returned DISPROVEN.]

Shot 1: The hypothesis is disproven because two key observations contradict it. First, RTPEngine's own error counters are zero, indicating it is not aware of any internal errors. Second, and more importantly, the UPF's packet counters show a significant asymmetry between inbound and outbound traffic (8.9 pps in vs. 6.8 pps out), pointing to the UPF as the location of the packet loss, not RTPEngine. While RTPEngine does report high packet loss, this is a correct observation of loss on the path, but the evidence points to the loss originating upstream at the UPF.

Shot 2: The evidence strongly contradicts the hypothesis that RTPEngine is the source of packet loss. While RTPEngine does report a high loss ratio, its internal error counters are at zero, indicating it is not the source of the errors. Furthermore, metrics from the UPF show a clear asymmetry between incoming and outgoing packet rates, pointing to the UPF as the location of the packet loss, before the traffic ever reaches RTPEngine.

**Probes executed (3):**
- **Returns rate-based MOS/loss/jitter alongside RTPEngine errors.** ✗ CONTRADICTS
    - *Tool:* `print(default_api.get_diagnostic_metrics(at_time_ts = 1777742116.7580352, nfs = ["rtpengine"]))`
    - *Observation:* [EVIDENCE: get_diagnostic_metrics(at_time_ts=1777742116.7580352, nfs=["rtpengine"]) -> "rtpengine.errors_per_second_(total) = 0"]
    - *Comment:* The hypothesis expected a non-zero error count from RTPEngine, but the metric is zero. This falsifies the expectation that RTPEngine is aware of and reporting errors.
- **window_seconds=120 to confirm MOS drop and packet-loss percentage across the same window** ✓ CONSISTENT
    - *Tool:* `print(default_api.get_dp_quality_gauges(at_time_ts = 1777742116.7580352, window_seconds = 120))`
    - *Observation:* [EVIDENCE: get_dp_quality_gauges(at_time_ts=1777742116.7580352, window_seconds=120) -> "RTPEngine:\n    loss (recent)  : 25.05"]
    - *Comment:* The observed high packet loss ratio is consistent with the hypothesis and the initial NA report. However, this metric reflects the end-to-end quality and does not by itself isolate the source of the loss.
- **Check UPF in/out symmetry in the output.** ✗ CONTRADICTS
    - *Tool:* `print(default_api.get_dp_quality_gauges(at_time_ts = 1777742116.7580352, window_seconds = 120))`
    - *Observation:* [EVIDENCE: get_dp_quality_gauges(at_time_ts=1777742116.7580352, window_seconds=120) -> "UPF:\n    in  packets/sec: 8.9\n    out packets/sec: 6.8"]
    - *Comment:* The UPF's inbound packet rate is significantly higher than its outbound rate. This asymmetry indicates that packets are being dropped within the UPF, which contradicts the hypothesis that RTPEngine is the source of the loss.

**Alternative suspects:** upf

### `h_promoted_upf` — ✅ **NOT_DISPROVEN**

**Hypothesis:** upf is the source of the anomaly named in the alternative_suspects of the original verdict tree.

**Reasoning:** The investigation did not find evidence to disprove the hypothesis. On the contrary, the probes revealed strong evidence supporting it. There is a clear asymmetry in the UPF's inbound and outbound packet rates, indicating a packet drop within the UPF itself. Furthermore, the downstream RTPEngine reports a correspondingly high packet loss ratio of 25%, which is the expected symptom of such a drop. While one probe was ambiguous due to a missing metric in the tool output, the two consistent and strong results provide significant corroboration for the hypothesis.

**Probes executed (3):**
- **Returns rate-based UPF in/out pps with in/out symmetry check.** ✓ CONSISTENT
    - *Tool:* `print(default_api.get_dp_quality_gauges(at_time_ts = 1777742116.7580352))`
    - *Observation:* [EVIDENCE: get_dp_quality_gauges(at_time_ts=1777742116.7580352) -> "UPF:\n    in  packets/sec: 8.9\n    out packets/sec: 6.8"]
    - *Comment:* A clear asymmetry is visible between the inbound (8.9 pps) and outbound (6.8 pps) packet rates at the UPF. This directly supports the hypothesis that the UPF is dropping packets.
- **window_seconds=120 to confirm MOS drop and packet-loss percentage across the same window** ✓ CONSISTENT
    - *Tool:* `print(default_api.get_dp_quality_gauges(at_time_ts = 1777742116.7580352, window_seconds = 120))`
    - *Observation:* [EVIDENCE: get_dp_quality_gauges(at_time_ts=1777742116.7580352, window_seconds=120) -> "RTPEngine:\n    loss (recent)  : 25.05"]
    - *Comment:* RTPEngine reports a packet loss ratio of 25.05%. This high value is the expected downstream effect of the packet drop observed at the UPF, strongly corroborating the hypothesis.
- **Returns rate-based MOS/loss/jitter alongside RTPEngine errors.** ~ AMBIGUOUS
    - *Tool:* `print(default_api.get_dp_quality_gauges(at_time_ts = 1777742116.7580352))`
    - *Observation:* [EVIDENCE: get_dp_quality_gauges(at_time_ts=1777742116.7580352) -> "<output does not contain rtpengine.errors_per_second>"]
    - *Comment:* The expected metric 'rtpengine.errors_per_second' was not found in the tool output. Therefore, this probe could not be used to confirm or deny the hypothesis that the UPF is dropping packets silently.


## Evidence Validation (Phase 6)

**Overall verdict:** clean
**Overall confidence:** high

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 4 | 3/3 | clean | high |
| `InvestigatorAgent_h_promoted_upf` | 3 | 3/3 | clean | high |


## Ground Truth

**Failure domain:** ims_media  
**Protocol impact:** RTP  
**Affected components:** rtpengine  
**Severity:** degraded

## Agent Diagnosis

**Model:** v6-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 327.1s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: The User Plane Function (UPF) is the root cause of media plane degradation, as it is dropping a significant percentage of user plane packets.
> - **timeline**:
>     1. IMS media plane quality degrades, with RTPEngine reporting high packet loss.
>     2. Initial investigation of RTPEngine finds no internal errors, suggesting an upstream problem.
>     3. Further investigation reveals a significant packet rate asymmetry at the UPF (8.9 pps in vs. 6.8 pps out), identifying it as the source of packet loss.
> - **root_cause**: The User Plane Function (UPF) is dropping approximately 24% of its inbound user plane packets, causing severe media degradation for voice calls. (primary_suspect_nf: `upf`)
> - **affected_components**:
>     - `upf`: Root Cause
>     - `rtpengine`: Symptomatic
> - **recommendation**: Investigate the User Plane Function (UPF) to determine the cause of the packet drops. Operators should inspect the UPF's internal resource utilization (CPU, memory), buffer statistics, and any data plane-specific drop counters or logs.
> - **confidence**: medium
> - **verdict_kind**: confirmed
> - **explanation**: The initial hypothesis blaming RTPEngine for media plane packet loss was disproven. Although RTPEngine correctly reported a high loss ratio, investigation showed it had no internal errors. Instead, evidence pointed to an upstream issue at the User Plane Function (UPF), which was confirmed during a targeted re-investigation. Probes revealed a clear asymmetry between the UPF's inbound (8.9 pps) and outbound (6.8 pps) packet rates, indicating it is dropping roughly 24% of packets. The loss reported by RTPEngine is a direct symptom of this upstream failure.

### Scoring Breakdown

**Overall score: 36%**

**Scorer assessment:** The agent correctly identified the severity and type of fault (packet loss/degradation) and accurately flagged the IMS layer as affected in its intermediate reasoning. However, it incorrectly attributed the root cause to the UPF instead of RTPEngine, mis-ranking the actual affected component, and its confidence was not calibrated given the incorrect root cause.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | No | The simulated failure was 30% packet loss on RTPEngine. The agent's final diagnosis incorrectly identifies the User Plane Function (UPF) as the root cause, stating it is dropping packets. This contradicts the ground truth where RTPEngine itself was dropping packets. |
| Component overlap | 30% | The primary affected component is 'rtpengine'. The agent lists 'rtpengine' as 'Symptomatic' but incorrectly identifies 'upf' as the 'Root Cause'. Since 'rtpengine' is mentioned but mis-ranked, a partial score of 0.3 is awarded. |
| Severity correct | Yes | The simulated failure describes 'Call Quality Degradation' due to packet loss, leading to 'degrading voice quality'. The agent's diagnosis correctly identifies 'severe media degradation for voice calls', which matches the degradation severity. |
| Fault type identified | Yes | The simulated failure is '30% packet loss'. The agent's diagnosis correctly identifies 'dropping approximately 24% of its inbound user plane packets' and 'packet loss' as the core issue, which is the correct observable fault type. |
| Layer accuracy | Yes | The ground truth states 'rtpengine' belongs to the 'ims' layer. The agent's NETWORK ANALYSIS correctly rates the 'ims' layer as 'red' with evidence pointing to 'rtpengine_loss_ratio'. Although the final diagnosis points to UPF, the layer status in the intermediate analysis correctly flags the IMS layer for an IMS component issue. |
| Confidence calibrated | No | The agent's confidence is 'medium', but its primary diagnosis (root cause and main affected component) is incorrect. A medium confidence is not appropriate for a fundamentally incorrect root cause identification. |

**Ranking:** The correct root cause ('rtpengine') is not identified as the primary root cause in the final diagnosis; it is listed as 'Symptomatic'. The agent only provides one root cause candidate, which is incorrect.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 247,949 |
| Output tokens | 5,935 |
| Thinking tokens | 27,919 |
| **Total tokens** | **281,803** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| EventAggregator | 0 | 0 | 0 |
| CorrelationAnalyzer | 0 | 0 | 0 |
| NetworkAnalystAgent | 75,916 | 5 | 6 |
| Phase 3 NetworkAnalyst__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 37,639 | 2 | 3 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 23,190 | 1 | 2 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| InvestigatorAgent_h1 | 31,165 | 2 | 3 |
| InvestigatorAgent_h1 | 31,950 | 2 | 3 |
| InvestigatorAgent_h1__reconciliation | 0 | 0 | 0 |
| Phase5FanOutAudit | 0 | 0 | 0 |
| Phase6.5CandidatePool | 0 | 0 | 0 |
| InstructionGeneratorAgent | 20,831 | 1 | 2 |
| Phase 6.5 Reinvestigation IG__guardrail | 0 | 0 | 0 |
| InvestigatorAgent_h_promoted_upf | 53,381 | 3 | 4 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 7,731 | 0 | 1 |
| Phase 7 Synthesis__guardrail | 0 | 0 | 0 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 463.4s
