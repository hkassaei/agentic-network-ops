# Episode Report: Call Quality Degradation

**Agent:** v6  
**Episode ID:** ep_20260504_151246_call_quality_degradation  
**Date:** 2026-05-04T15:12:47.849551+00:00  
**Duration:** 346.9s  

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
- **Nodes with any drift:** 6

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 37.14 (per-bucket threshold: 11.07, context bucket (0, 0), trained on 323 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following metrics deviate from their learned-healthy baseline. Treat each as a semantic observation (meaning + numbers), not a number alone — the KB's interpretation is the authoritative reading.

- **`context.cx_active`** — current **1.00** vs learned baseline **0.59** (MEDIUM, spike). *(No KB context available — interpret from the metric name.)*

- **`derived.rtpengine_loss_ratio`** (RTPEngine RTCP-reported per-RR average packet loss) — current **16.00 packets_per_rr** vs learned baseline **0.00 packets_per_rr** (MEDIUM, spike)
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

- **`normalized.scscf.core:rcv_requests_invite_per_ue`** (SIP INVITE rate per UE at S-CSCF) — current **0.06 requests_per_second** vs learned baseline **0.00 requests_per_second** (MEDIUM, spike)
    - **What it measures:** S-CSCF participation in call setup. Zero when calls aren't being
placed OR S-CSCF not receiving forwarded INVITEs.
    - **Spike means:** Upstream forwarding issue.
    - **Healthy typical range:** 0–0.2 requests_per_second
    - **Healthy invariant:** Per-UE rate.

- **`normalized.upf.gtp_indatapktn3upf_per_ue`** (GTP-U uplink rate per UE (N3)) — current **4.31 packets_per_second** vs learned baseline **1.45 packets_per_second** (MEDIUM, spike)
    - **What it measures:** Health of the uplink user-plane path gNB → UPF. Drops to near-zero
during RAN or N3 outage; stays nonzero during active calls or data
sessions. Decoupled from SIP signaling (signals data plane, not
control plane).
    - **Spike means:** Either UEs not generating uplink traffic (no calls/data) or N3 path is degraded.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE — constant regardless of UE pool size. Rises during active VoNR calls (~100 pps for G.711 voice) and data transfer.

- **`normalized.upf.gtp_outdatapktn3upf_per_ue`** (GTP-U downlink rate per UE (N3)) — current **4.13 packets_per_second** vs learned baseline **1.45 packets_per_second** (MEDIUM, spike)
    - **What it measures:** Health of the downlink user-plane path UPF → gNB. Typically mirrors
uplink rate during calls/data; asymmetry indicates directional
faults (e.g., UPF receiving from internet but not forwarding).
    - **Spike means:** Downlink data plane degraded — UPF not forwarding to gNB.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE — constant regardless of UE pool size. Roughly symmetric with uplink during healthy calls.

- **`normalized.smf.bearers_per_ue`** (Active QoS bearers per UE) — current **3.00 count** vs learned baseline **2.48 count** (LOW, shift)
    - **What it measures:** Per-UE count of active QoS bearers. Baseline reflects default
bearers; increments during VoNR calls indicate dedicated voice
bearers being set up. Drop during an active call = dedicated
bearer torn down unexpectedly (voice will fail).
    - **Shift means:** Expected during VoNR calls (1 extra bearer per active call).
    - **Healthy typical range:** 2–3.5 count
    - **Healthy invariant:** At rest: equals configured default bearers (typically 2 per UE).
During active VoNR call: +1 per caller. The per-UE ratio is the
invariant; absolute count scales with UE pool.


## Event Aggregation (Phase 1)

**1 events fired during the observation window:**

- `core.upf.activity_during_calls_collapsed` (source: `core.upf.activity_during_calls`, nf: `upf`, t=1777907685.0)  [current_value=0.0480745]

## Correlation Analysis (Phase 2)

1 events fired but no composite hypothesis emerged. The events may be from independent faults or lack registered correlation hints in the KB.

## Network Analysis (Phase 3)

**Summary:** The UPF is the source of a data plane failure, causing significant packet loss for VoNR calls.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | All physical and virtual links are active and all relevant containers are running. |
| **ran** | 🟢 GREEN | No anomalies reported from the RAN. Signaling appears to be reaching the core. |
| **core** | 🔴 RED | The UPF is the primary suspect. A critical event points to its failure to process data during calls, and its own metrics are highly anomalous, indicating it is not forwarding traffic correctly. |
| **ims** | 🟡 YELLOW | The IMS media plane is experiencing high packet loss, as reported by rtpengine. This is assessed to be a symptom of the upstream UPF failure, not a fault originating in the IMS layer itself. |

**CORE evidence:**
- core.upf.activity_during_calls_collapsed
- normalized.upf.gtp_outdatapktn3upf_per_ue

**IMS evidence:**
- derived.rtpengine_loss_ratio

**Ranked hypotheses:**

- **`h1`** (fit=0.90, nf=upf, specificity=specific):
    - **Statement:** The UPF is the source of data plane packet loss, causing a high packet loss ratio reported by RTPEngine and triggering the `core.upf.activity_during_calls_collapsed` event.
    - **Supporting events:** `core.upf.activity_during_calls_collapsed`
    - **Falsification probes:**
        - A live packet capture on the link between UPF and RTPEngine shows RTP packets are successfully leaving the UPF.
        - The UPF's internal GTP-U packet forwarding counters show no discrepancy between received and transmitted packets.
        - Restarting only the RTPEngine container resolves the packet loss without any changes to the UPF.


## Falsification Plans (Phase 4)

**1 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `upf`)

**Hypothesis:** The UPF is the source of data plane packet loss, causing a high packet loss ratio reported by RTPEngine and triggering the `core.upf.activity_during_calls_collapsed` event.

**Probes (3):**
1. **`get_dp_quality_gauges`** — Check UPF in/out data plane packet rates for symmetry over a 60-second window. This checks for discrepancies between packets received by the UPF and packets it forwards.
    - *Expected if hypothesis holds:* The probe returns asymmetric packet rates for the UPF (e.g. `upf.gtp_indatapktn3upf_per_ue` and `upf.gtp_outdatapktn3upf_per_ue` are imbalanced), indicating a discrepancy in packet handling.
    - *Falsifying observation:* The probe returns symmetric packet rates for the UPF (e.g., `upf.gtp_indatapktn3upf_per_ue` and `upf.gtp_outdatapktn3upf_per_ue` are roughly equal during active calls), suggesting it is forwarding packets as expected.
2. **`get_dp_quality_gauges`** — Check RTPEngine's reported packet loss ratio over the same 60-second window to confirm the downstream impact.
    - *Expected if hypothesis holds:* The `ims.rtpengine.loss_ratio` metric is significantly greater than 0, confirming the presence of high packet loss in the media plane as observed by RTPEngine.
    - *Falsifying observation:* The `ims.rtpengine.loss_ratio` metric is at or near 0. This would indicate a healthy media plane from RTPEngine's perspective, which contradicts the hypothesis's stated consequence.
3. **`get_dp_quality_gauges`** — Check for any internally-generated errors within RTPEngine over the same 60-second window to rule out RTPEngine as the primary cause.
    - *Expected if hypothesis holds:* The `ims.rtpengine.errors_per_second` metric is 0. This suggests the high loss ratio is from an upstream source and not from RTPEngine's own processing.
    - *Falsifying observation:* The `ims.rtpengine.errors_per_second` metric is greater than 0, suggesting that RTPEngine itself is encountering errors and could be the source of the media plane issues, which would falsify the hypothesis about UPF being the source.

*Notes:* The hypothesis concerns a failure in the VoNR data plane. The relevant flow is `vonr_call_setup`, particularly step 12 ('RTP media - voice call active'), which traverses the UPF.


## Parallel Investigators (Phase 5)

**1 sub-Investigator verdict(s):** **1 NOT_DISPROVEN**

### `h1` — ✅ **NOT_DISPROVEN**

**Hypothesis:** The UPF is the source of data plane packet loss, causing a high packet loss ratio reported by RTPEngine and triggering the `core.upf.activity_during_calls_collapsed` event.

**Reasoning:** [Multi-shot consensus — both shots returned NOT_DISPROVEN.]

Shot 1: All executed probes returned results consistent with the hypothesis. The UPF's packet rates showed a small but notable asymmetry (16% drop from input to output), and RTPEngine reported a very high packet loss (24.58%) while simultaneously reporting zero internal errors. This combination strongly suggests the packet loss originates upstream of RTPEngine, implicating the UPF as the likely source, thus failing to falsify the hypothesis.

Shot 2: All three probes executed were consistent with the hypothesis. Probes confirmed a high packet loss ratio reported by RTPEngine, an imbalance in the UPF's ingress and egress packet rates, and a lack of internally generated errors within RTPEngine. This combination of evidence strongly supports the hypothesis that the UPF is the source of the packet loss.

**Probes executed (3):**
- **Check UPF in/out data plane packet rates for symmetry over a 60-second window. This checks for discrepancies between packets received by the UPF and packets it forwards.** ✓ CONSISTENT
    - *Tool:* `default_api.get_dp_quality_gauges(at_time_ts = 1777907623.9566491, window_seconds = 60)`
    - *Observation:* [EVIDENCE: get_dp_quality_gauges(at_time_ts=1777907623.9566491, window_seconds=60) -> "UPF:\n    in  packets/sec: 8.0\n    out packets/sec: 6.7"]
    - *Comment:* The UPF's output packet rate (6.7 pps) is lower than its input rate (8.0 pps), indicating a packet drop of approximately 16%. This asymmetry is consistent with the hypothesis that the UPF is the source of packet loss.
- **Check RTPEngine's reported packet loss ratio over the same 60-second window to confirm the downstream impact.** ✓ CONSISTENT
    - *Tool:* `default_api.get_dp_quality_gauges(at_time_ts = 1777907623.9566491, window_seconds = 60)`
    - *Observation:* [EVIDENCE: get_dp_quality_gauges(at_time_ts=1777907623.9566491, window_seconds=60) -> "RTPEngine:\n    loss (recent)  : 24.58"]
    - *Comment:* RTPEngine reports a very high recent packet loss of 24.58%. This confirms that significant packet loss is occurring in the media plane, as stated in the hypothesis.
- **Check for any internally-generated errors within RTPEngine over the same 60-second window to rule out RTPEngine as the primary cause.** ✓ CONSISTENT
    - *Tool:* `default_api.get_diagnostic_metrics(at_time_ts = 1777907623.9566491, nfs = ["rtpengine", "upf"])`
    - *Observation:* [EVIDENCE: get_diagnostic_metrics(at_time_ts=1777907623.9566491, nfs=['rtpengine', 'upf']) -> "rtpengine.errors_per_second_(total) = 0"]
    - *Comment:* The `rtpengine.errors_per_second` metric is 0, indicating that RTPEngine itself is not the source of the errors. This supports the hypothesis that the packet loss is caused by an upstream component, which is the UPF.


## Evidence Validation (Phase 6)

**Overall verdict:** clean
**Overall confidence:** high

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 4 | 3/3 | clean | high |


## Ground Truth

**Failure domain:** ims_media  
**Protocol impact:** RTP  
**Affected components:** rtpengine  
**Severity:** degraded

## Agent Diagnosis

**Model:** v6-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 210.1s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: The UPF is experiencing a data plane failure, causing significant packet loss for VoNR calls.
> - **timeline**:
>     1. An event `core.upf.activity_during_calls_collapsed` was triggered, indicating a failure in the UPF's data processing during active calls.
>     2. The IMS media plane component (rtpengine) began reporting a high packet loss ratio.
>     3. Investigation revealed an asymmetry in the UPF's ingress and egress packet counters, confirming it was dropping packets.
> - **root_cause**: The User Plane Function (UPF) is the source of a data plane failure, dropping packets and leading to a high packet loss ratio for Real-Time Protocol (RTP) media streams. (primary_suspect_nf: `upf`)
> - **affected_components**:
>     - `upf`: Root Cause
>     - `rtpengine`: Symptomatic
> - **recommendation**: Investigate the User Plane Function's (UPF) internal forwarding logic and resource utilization. A live packet capture on the N6 interface between the UPF and RTPEngine would also help verify if RTP packets are being dropped by the UPF.
> - **confidence**: high
> - **verdict_kind**: confirmed
> - **explanation**: The diagnosis is based on a single, strongly supported hypothesis (h1) that was not disproven by investigation. Probes confirmed that the UPF's output packet rate (6.7 pps) was significantly lower than its input rate (8.0 pps), indicating it is dropping packets. Downstream, RTPEngine reported a correspondingly high packet loss ratio (24.58%) while simultaneously reporting zero internal errors. This combination of evidence isolates the fault to the UPF, ruling out RTPEngine as the cause.

### Scoring Breakdown

**Overall score: 36%**

**Scorer assessment:** The agent correctly identified the fault type and severity, and placed the affected component in the correct layer, but failed to identify the true root cause and primary affected component, leading to poor confidence calibration.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | No | The simulated failure was 30% packet loss on RTPEngine, meaning RTPEngine itself was the source of the packet drops. The agent incorrectly identified the User Plane Function (UPF) as the root cause, stating it was dropping packets. |
| Component overlap | 30% | The actual root cause component is 'rtpengine'. The agent listed 'rtpengine' in 'affected_components' but labeled it 'Symptomatic' rather than 'Root Cause'. It incorrectly identified 'upf' as the 'Root Cause'. |
| Severity correct | Yes | The simulated failure involved '30% packet loss' and 'degrading voice quality', which is a degradation. The agent correctly described the issue as 'significant packet loss' and a 'high packet loss ratio', indicating degradation rather than a complete outage. |
| Fault type identified | Yes | The simulated failure was 'packet loss'. The agent correctly identified 'data plane failure' and 'dropping packets' leading to 'high packet loss ratio' as the observable fault type. |
| Layer accuracy | Yes | The ground truth 'rtpengine' belongs to the 'ims' layer. The agent's network analysis correctly rated the 'ims' layer as 'yellow' and explicitly mentioned 'rtpengine' experiencing high packet loss within that layer. While the agent incorrectly attributed the root cause to the 'core' layer, it did not misattribute the 'rtpengine' component to the wrong layer. |
| Confidence calibrated | No | The agent stated 'high' confidence for a diagnosis that incorrectly identified the root cause and the primary affected component. |

**Ranking:** The agent provided a single root cause ('UPF') which was incorrect. The actual root cause ('rtpengine') was not identified as the root cause.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 164,773 |
| Output tokens | 4,394 |
| Thinking tokens | 16,353 |
| **Total tokens** | **185,520** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| EventAggregator | 0 | 0 | 0 |
| CorrelationAnalyzer | 0 | 0 | 0 |
| NetworkAnalystAgent | 69,658 | 5 | 6 |
| Phase 3 NetworkAnalyst__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 24,495 | 1 | 2 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 23,126 | 1 | 2 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| InvestigatorAgent_h1 | 31,507 | 2 | 3 |
| InvestigatorAgent_h1 | 31,259 | 2 | 3 |
| InvestigatorAgent_h1__reconciliation | 0 | 0 | 0 |
| Phase5FanOutAudit | 0 | 0 | 0 |
| Phase6.5CandidatePool | 0 | 0 | 0 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 5,475 | 0 | 1 |
| Phase 7 Synthesis__guardrail | 0 | 0 | 0 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 346.9s
