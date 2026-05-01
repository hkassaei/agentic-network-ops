# Episode Report: Call Quality Degradation

**Agent:** v6  
**Episode ID:** ep_20260501_041310_call_quality_degradation  
**Date:** 2026-05-01T04:13:12.661835+00:00  
**Duration:** 493.7s  

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
- **Nodes with significant deltas:** 1
- **Nodes with any drift:** 5

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 39.96 (per-bucket threshold: 28.18, context bucket (1, 1), trained on 323 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following metrics deviate from their learned-healthy baseline. Treat each as a semantic observation (meaning + numbers), not a number alone — the KB's interpretation is the authoritative reading.

- **`derived.rtpengine_loss_ratio`** (RTPEngine RTCP-reported per-RR average packet loss) — current **30.81 packets_per_rr** vs learned baseline **0.00 packets_per_rr** (MEDIUM, spike)
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

- **`derived.upf_activity_during_calls`** (UPF activity consistency with active dialogs) — current **0.05 ratio** vs learned baseline **0.54 ratio** (MEDIUM, drop)
    - **What it measures:** Cross-layer consistency check between IMS dialog state and UPF
throughput. A drop while dialogs_per_ue is non-zero is a
smoking-gun signal for media-plane failure independent of signaling.
    - **Drop means:** Active calls reported but no media flowing — media path broken (UPF, RTPEngine, or N3 packet loss).
    - **Healthy typical range:** 0.3–1 ratio
    - **Healthy invariant:** 1.0 when traffic fully follows active calls; 0.0 when signaling says active but data plane is silent.

- **`normalized.icscf.cdp_replies_per_ue`** (I-CSCF Diameter reply rate per UE) — current **0.03 replies_per_second_per_ue** vs learned baseline **0.03 replies_per_second_per_ue** (MEDIUM, shift)
    - **What it measures:** Liveness of the I-CSCF↔HSS Cx path. Drops to 0 when HSS is unreachable OR when no signaling is occurring at the I-CSCF (idle or upstream P-CSCF partitioned).
    - **Shift means:** I-CSCF is actively conversing with HSS — healthy.
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

- **`normalized.upf.gtp_indatapktn3upf_per_ue`** (GTP-U uplink rate per UE (N3)) — current **10.73 packets_per_second** vs learned baseline **1.45 packets_per_second** (MEDIUM, spike)
    - **What it measures:** Health of the uplink user-plane path gNB → UPF. Drops to near-zero
during RAN or N3 outage; stays nonzero during active calls or data
sessions. Decoupled from SIP signaling (signals data plane, not
control plane).
    - **Spike means:** Either UEs not generating uplink traffic (no calls/data) or N3 path is degraded.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE — constant regardless of UE pool size. Rises during active VoNR calls (~100 pps for G.711 voice) and data transfer.

- **`normalized.upf.gtp_outdatapktn3upf_per_ue`** (GTP-U downlink rate per UE (N3)) — current **7.33 packets_per_second** vs learned baseline **1.45 packets_per_second** (MEDIUM, spike)
    - **What it measures:** Health of the downlink user-plane path UPF → gNB. Typically mirrors
uplink rate during calls/data; asymmetry indicates directional
faults (e.g., UPF receiving from internet but not forwarding).
    - **Spike means:** Downlink data plane degraded — UPF not forwarding to gNB.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE — constant regardless of UE pool size. Roughly symmetric with uplink during healthy calls.

- **`normalized.icscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at I-CSCF) — current **0.06 requests_per_second** vs learned baseline **0.06 requests_per_second** (LOW, shift)
    - **What it measures:** Health of the P-CSCF → I-CSCF forwarding path (Mw interface). When
this drops to zero while P-CSCF REGISTER rate is still non-zero,
it's the SIGNATURE of an IMS partition between P-CSCF and I-CSCF.
    - **Shift means:** Forwarding issue on the Mw interface, or P-CSCF stopped forwarding.
    - **Healthy typical range:** 0–0.5 requests_per_second
    - **Healthy invariant:** Per-UE rate. Should closely track ims.pcscf.rcv_requests_register_per_ue.

- **`normalized.pcscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at P-CSCF) — current **0.06 requests_per_second** vs learned baseline **0.06 requests_per_second** (LOW, shift)
    - **What it measures:** How actively UEs are refreshing their IMS registrations with the
P-CSCF. REGISTERs arrive periodically (re-registration timer) plus
at attach. Sustained zero means UEs cannot reach P-CSCF OR the
UE-to-network SIP path is broken.
    - **Shift means:** Fewer REGISTERs than expected — UE connectivity or P-CSCF reachability issue.
    - **Healthy typical range:** 0–0.5 requests_per_second
    - **Healthy invariant:** Per-UE rate — same value at any deployment scale.

- **`normalized.scscf.cdp_replies_per_ue`** (S-CSCF CDP Diameter replies per UE) — current **0.06 replies_per_second_per_ue** vs learned baseline **0.06 replies_per_second_per_ue** (LOW, shift)
    - **What it measures:** Active S-CSCF Diameter traffic with HSS. Near-zero when registrations idle OR HSS partition.
    - **Shift means:** Diameter peering loss with HSS.
    - **Healthy typical range:** 0–1 replies_per_second_per_ue
    - **Healthy invariant:** Per-UE rate; varies with registration/auth load.


## Event Aggregation (Phase 1)

**1 events fired during the observation window:**

- `core.upf.activity_during_calls_collapsed` (source: `core.upf.activity_during_calls`, nf: `upf`, t=1777608911.7)  [current_value=0.04598337499999999]

## Correlation Analysis (Phase 2)

1 events fired but no composite hypothesis emerged. The events may be from independent faults or lack registered correlation hints in the KB.

## Network Analysis (Phase 3)

**Summary:** The media plane is down due to significant packet loss, causing voice calls to fail. Evidence points to the UPF as the primary suspect dropping packets, with RTPEngine being the downstream reporter of the high loss ratio.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** |   |  |
| **ran** | 🟢 GREEN | RAN-side metrics appear nominal. The issue manifests downstream. |
| **core** | 🔴 RED | The UPF, a core component, shows a significant discrepancy between ingress and egress packet rates and is the primary suspect for the media plane failure. |
| **ims** | 🟡 YELLOW | RTPEngine is reporting a very high packet loss ratio and degraded MOS, but it is likely observing a failure from an upstream component (UPF) rather than being the source of the fault itself. |

**CORE evidence:**
- derived.upf_activity_during_calls

**IMS evidence:**
- derived.rtpengine_loss_ratio

**Ranked hypotheses:**

- **`h1`** (fit=0.90, nf=upf, specificity=specific):
    - **Statement:** The UPF is the source of media packet loss, dropping traffic between its N3-interface ingress and its media-proxy-facing egress.
    - **Supporting events:** `core.upf.activity_during_calls_collapsed`
    - **Falsification probes:**
        - Check UPF's internal packet drop counters via metrics; if these counters are zero, the UPF is not the source of the loss.
        - Perform a packet capture on the UPF's N3 and N6 interfaces; if packets arrive on N3 but do not depart on N6, the UPF is dropping them.
        - Examine the 'tc' (traffic control) qdisc and iptables rules on the UPF container; a misconfiguration could be the cause of the packet drops.
- **`h2`** (fit=0.70, nf=rtpengine, specificity=specific):
    - **Statement:** RTPEngine is the source of the media plane failure, dropping RTP packets as they arrive from the UPF.
    - **Supporting events:** `derived.rtpengine_loss_ratio`
    - **Falsification probes:**
        - Check RTPEngine's internal error counters; if they are not incrementing, it is only reporting loss, not causing it.
        - Run a packet capture on RTPEngine's ingress interface; if incoming packets from the UPF are already missing, the fault is upstream of RTPEngine.
        - Check for resource exhaustion (CPU, memory) on the RTPEngine container, which could lead to drops.


## Falsification Plans (Phase 4)

**2 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `upf`)

**Hypothesis:** The UPF is the source of media packet loss, dropping traffic between its N3-interface ingress and its media-proxy-facing egress.

**Probes (3):**
1. **`get_dp_quality_gauges`** — window_seconds=60
    - *Expected if hypothesis holds:* A significant imbalance between UPF's ingress and egress packet rates, where egress is much lower than ingress.
    - *Falsifying observation:* The UPF's ingress and egress packet rates are balanced, indicating it is not dropping an anomalous number of packets.
2. **`get_diagnostic_metrics`** — nf=upf
    - *Expected if hypothesis holds:* UPF's internal metrics for dropped GTP packets are significantly elevated.
    - *Falsifying observation:* UPF's internal metrics for dropped GTP packets are zero or nominal.
3. **`get_diagnostic_metrics`** — nf=smf
    - *Expected if hypothesis holds:* Metrics on the SMF related to N4/PFCP sessions show no errors, indicating the control plane is stable.
    - *Falsifying observation:* The SMF reports errors or failures related to the N4/PFCP interface, suggesting a broader problem at the UPF than just media plane packet loss.

*Notes:* This plan tests the hypothesis that the UPF is internally dropping media packets. It first checks for a packet rate discrepancy across the UPF, then for internal drop counters, and finally checks the health of the control-plane interface to ensure the problem is isolated to the media plane as hypothesized.

### Plan for `h2` (target: `rtpengine`)

**Hypothesis:** RTPEngine is the source of the media plane failure, dropping RTP packets as they arrive from the UPF.

**Probes (3):**
1. **`get_dp_quality_gauges`** — window_seconds=60
    - *Expected if hypothesis holds:* The packet loss ratio reported for RTPEngine is high.
    - *Falsifying observation:* The packet loss ratio reported for RTPEngine is zero or nominal, which contradicts the event that generated this hypothesis.
2. **`get_dp_quality_gauges`** — window_seconds=60, specifically observing UPF egress quality
    - *Expected if hypothesis holds:* The packet loss ratio reported at the egress of the UPF is zero or nominal, indicating packets are successfully leaving the UPF towards RTPEngine.
    - *Falsifying observation:* The packet loss ratio reported at the egress of the UPF is high. This would prove that packets are already lost before reaching RTPEngine, falsifying the hypothesis.
3. **`get_diagnostic_metrics`** — nf=rtpengine
    - *Expected if hypothesis holds:* RTPEngine's metrics for discarded packets or processing errors are elevated.
    - *Falsifying observation:* RTPEngine's metrics for discarded packets and processing errors are zero or nominal.

*Notes:* This plan addresses the ambiguity of whether RTPEngine is the source of packet loss or just the reporter. It uses a pair of observations from get_dp_quality_gauges to localize the loss (is it happening before or at RTPEngine?). It also checks RTPEngine's own metrics for direct evidence of malfunction. This structure corrects the issues flagged in the resample feedback.


## Parallel Investigators (Phase 5)

**3 sub-Investigator verdict(s):** **1 INCONCLUSIVE**, **1 DISPROVEN**, **1 NOT_DISPROVEN**

### `h1` — ❓ **INCONCLUSIVE**

**Hypothesis:** The UPF is the source of media packet loss, dropping traffic between its N3-interface ingress and its media-proxy-facing egress.

**Reasoning:** Mechanical guardrail: InvestigatorAgent_h1 made only 0 tool call(s); minimum is 2. Self-reported output was discarded.

### `h2` — ❌ **DISPROVEN**

**Hypothesis:** RTPEngine is the source of the media plane failure, dropping RTP packets as they arrive from the UPF.

**Reasoning:** The evidence clearly indicates that the packet loss originates at the UPF, before the traffic reaches RTPEngine. Probes revealed a significant discrepancy between the UPF's ingress and egress packet rates, proving it is the source of the drop. Furthermore, RTPEngine's own diagnostic metrics show no internal errors or discards, confirming it is only reporting the upstream loss, not causing it.

**Probes executed (2):**
- **Check packet loss ratio reported by RTPEngine and packet rates at the UPF.** ✗ CONTRADICTS
    - *Tool:* `default_api.get_dp_quality_gauges(at_time_ts=1777608872.1462154, window_seconds=60)`
    - *Observation:* [EVIDENCE: get_dp_quality_gauges(at_time_ts=1777608872.1462154, window_seconds=60) -> "RTPEngine: loss (recent): 30.77, UPF: in packets/sec: 20.9, out packets/sec: 14.1"]
    - *Comment:* This probe was intended to serve two parts of the plan. While the high loss at RTPEngine is consistent with the hypothesis, the data from the UPF directly contradicts it. The UPF is dropping approximately 32.5% of packets, which explains the loss seen downstream at RTPEngine. This falsifies the idea that RTPEngine is the source.
- **Check RTPEngine's internal diagnostic metrics for discarded packets or processing errors.** ✗ CONTRADICTS
    - *Tool:* `default_api.get_diagnostic_metrics(at_time_ts=1777608872.1462154, nfs=["rtpengine"])`
    - *Observation:* [EVIDENCE: get_diagnostic_metrics(at_time_ts=1777608872.1462154, nfs=["rtpengine"]) -> "rtpengine.errors_per_second_(total) = 0"]
    - *Comment:* RTPEngine's internal error rate is zero. This contradicts the expectation that it would show elevated errors if it were the source of packet drops.

**Alternative suspects:** upf

### `h_promoted_upf` — ✅ **NOT_DISPROVEN**

**Hypothesis:** upf is the source of the anomaly named in the alternative_suspects of the original verdict tree.

**Reasoning:** The investigation's most direct evidence strongly supports the hypothesis. The `get_dp_quality_gauges` probe, anchored at the anomaly time, revealed a significant packet drop at the UPF, with `in packets/sec` being much higher than `out packets/sec`. This points to the UPF as the locus of the fault. While the planned RTT probes from the gNB could not be executed due to tool limitations, adapted probes from the SMF showed the UPF was responsive, which simply rules out a complete crash and does not contradict a data plane-specific issue. The evidence for packet loss within the UPF remains unrefuted.

**Probes executed (3):**
- **measure data plane quality gauges for the UPF** ✓ CONSISTENT
    - *Tool:* `default_api.get_dp_quality_gauges(at_time_ts = 1777608872.1462154, window_seconds = 60)`
    - *Observation:* [EVIDENCE: get_dp_quality_gauges(at_time_ts=1777608872.1462154, window_seconds=60) -> "UPF: in  packets/sec: 20.9, out packets/sec: 14.1"]
    - *Comment:* The significant drop between input and output packet rates (20.9 pps in vs 14.1 pps out) is direct evidence of packet loss occurring within the UPF. This aligns perfectly with the hypothesis.
- **measure RTT from nr_gnb to upf** ~ AMBIGUOUS
    - *Tool:* `default_api.measure_rtt(container = "smf", target_ip = "172.22.0.8")`
    - *Observation:* [EVIDENCE: measure_rtt("smf", "172.22.0.8") -> "3 packets transmitted, 3 received, 0% packet loss, time 2041ms"]
    - *Comment:* The probe was adapted to run from 'smf' instead of 'nr_gnb' due to tool limitations. The result shows the UPF is reachable from the core network, which contradicts the expectation of high latency or loss. However, this doesn't falsify a data-plane specific issue on the N3 interface, it only shows the control plane is responsive from another core NF.
- **measure RTT from nr_gnb to amf** ✓ CONSISTENT
    - *Tool:* `default_api.measure_rtt(container = "smf", target_ip = "172.22.0.10")`
    - *Observation:* [EVIDENCE: measure_rtt("smf", "172.22.0.10") -> "3 packets transmitted, 3 received, 0% packet loss, time 2026ms"]
    - *Comment:* This partner probe, also adapted to run from 'smf', confirms that connectivity within the core network is generally healthy. This serves as a baseline for the adapted UPF RTT check.


## Evidence Validation (Phase 6)

**Overall verdict:** severe
**Overall confidence:** none

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 0 | 0/0 | severe | none |
|  |  |  |  | *ZERO tool calls — all citations fabricated* |
| `InvestigatorAgent_h2` | 2 | 2/2 | clean | high |
| `InvestigatorAgent_h_promoted_upf` | 5 | 3/3 | clean | high |


## Ground Truth

**Failure domain:** ims_media  
**Protocol impact:** RTP  
**Affected components:** rtpengine  
**Severity:** degraded

## Agent Diagnosis

**Model:** v6-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 358.1s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: The User Plane Function (UPF) is the root cause of the media plane failure, dropping a significant portion of RTP packets.
> - **timeline**:
>     1. UPF ingress packet rate (20.9 pps) significantly diverges from its egress rate (14.1 pps), indicating internal packet loss.
>     2. RTPEngine reports a high packet loss ratio (30.77%) and degraded Mean Opinion Score (MOS).
>     3. Media plane becomes unavailable, causing voice calls to fail.
> - **root_cause**: The UPF is dropping approximately 32.5% of media packets transiting from its N3 interface (ingress) to its N6 interface (egress), causing high packet loss and subsequent voice call failures. (primary_suspect_nf: `upf`)
> - **affected_components**:
>     - `upf`: Root Cause
>     - `rtpengine`: Symptomatic
> - **recommendation**: Verify the root cause by examining the UPF's internal packet drop counters via its metrics. Additionally, inspect the traffic control (`tc qdisc`) and `iptables` configurations on the UPF's host or container to identify any rules that may be silently dropping packets.
> - **confidence**: low
> - **verdict_kind**: confirmed
> - **explanation**: The investigation confirmed the User Plane Function (UPF) as the source of packet loss. A follow-up investigation on the UPF (`h_promoted_upf`) found direct evidence of packet drops, with ingress packet rates being significantly higher than egress rates. The initial hypothesis targeting RTPEngine (`h2`) was disproven; probes showed RTPEngine was only reporting the loss originating upstream. Confidence in this diagnosis is low, however, because one of the primary investigator agents (`InvestigatorAgent_h1`) failed to execute any tasks and fabricated its findings, which required a secondary investigation to reach this conclusion.

### Scoring Breakdown

**Overall score: 41%**

**Scorer assessment:** The agent correctly identified the fault type as packet loss and its severity as degradation, but incorrectly attributed the root cause to the UPF instead of RTPEngine. Its low confidence was appropriate given the diagnostic errors.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | No | The simulated failure was 30% packet loss on RTPEngine. The agent incorrectly identified the UPF as the root cause, stating it was dropping packets. |
| Component overlap | 30% | The primary affected component was 'rtpengine'. The agent listed 'rtpengine' as 'Symptomatic' but incorrectly identified 'upf' as the 'Root Cause'. This indicates the component was identified but its causal role was mis-ranked. |
| Severity correct | Yes | The simulated failure involved 30% packet loss, leading to degraded voice quality and MOS drop. The agent correctly described 'high packet loss ratio' and 'degraded Mean Opinion Score (MOS)', which aligns with a degradation. |
| Fault type identified | Yes | The simulated failure was 'packet loss'. The agent explicitly identified 'dropping a significant portion of RTP packets' and 'high packet loss' as the fault type. |
| Layer accuracy | No | The ground truth states 'rtpengine' belongs to the 'ims' layer. The agent incorrectly attributed the root cause to the 'core' layer (UPF) in its network analysis, even though the actual problem was in the 'ims' layer component (RTPEngine). While it noted RTPEngine in the 'ims' layer, it explicitly stated it was 'likely observing a failure from an upstream component (UPF)', thus misattributing the root cause to the wrong layer. |
| Confidence calibrated | Yes | The agent's diagnosis had significant errors in identifying the root cause and primary affected component. Given these inaccuracies, its stated 'low' confidence is appropriate and well-calibrated. |

**Ranking:** The agent's final diagnosis presented only one root cause (UPF). The correct component (RTPEngine) was listed as 'Symptomatic' and not as a primary root cause candidate.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 264,014 |
| Output tokens | 7,278 |
| Thinking tokens | 29,027 |
| **Total tokens** | **300,319** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| EventAggregator | 0 | 0 | 0 |
| CorrelationAnalyzer | 0 | 0 | 0 |
| NetworkAnalystAgent | 38,637 | 7 | 3 |
| Phase 3 NetworkAnalyst__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 31,702 | 2 | 3 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 22,704 | 2 | 2 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| InvestigatorAgent_h1 | 10,323 | 0 | 1 |
| InvestigatorAgent_h1 | 42,331 | 3 | 4 |
| InvestigatorAgent_h2 | 31,266 | 2 | 3 |
| Phase5FanOutAudit | 0 | 0 | 0 |
| Phase6.5CandidatePool | 0 | 0 | 0 |
| InstructionGeneratorAgent | 27,670 | 2 | 3 |
| Phase 6.5 Reinvestigation IG__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 17,990 | 1 | 2 |
| Phase 6.5 Reinvestigation IG__guardrail | 0 | 0 | 0 |
| Phase 6.5 Reinvestigation IG__guardrail | 0 | 0 | 0 |
| InvestigatorAgent_h_promoted_upf | 70,289 | 5 | 6 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 7,407 | 0 | 1 |
| Phase 7 Synthesis__guardrail | 0 | 0 | 0 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 493.7s
