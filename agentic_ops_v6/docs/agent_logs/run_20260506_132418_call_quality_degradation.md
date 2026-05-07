# Episode Report: Call Quality Degradation

**Agent:** v6  
**Episode ID:** ep_20260506_131429_call_quality_degradation  
**Date:** 2026-05-06T13:14:31.322700+00:00  
**Duration:** 586.9s  

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
- **Nodes with significant deltas:** 6
- **Nodes with any drift:** 6

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 44.37 (per-bucket threshold: 26.31, context bucket (0, 1), trained on 323 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following metrics deviate from their learned-healthy baseline. Treat each as a semantic observation (meaning + numbers), not a number alone — the KB's interpretation is the authoritative reading.

- **`derived.rtpengine_loss_ratio`** (RTPEngine RTCP-reported per-RR average packet loss) — current **25.67 packets_per_rr** vs learned baseline **0.00 packets_per_rr** (MEDIUM, spike)
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

- **`normalized.icscf.core:rcv_requests_invite_per_ue`** (SIP INVITE rate per UE at I-CSCF) — current **0.01 requests_per_second** vs learned baseline **0.00 requests_per_second** (MEDIUM, spike)
    - **What it measures:** Health of call-setup forwarding P-CSCF → I-CSCF. Partition signature
same as REGISTER rate.
    - **Spike means:** Forwarding failure.
    - **Healthy typical range:** 0–0.2 requests_per_second
    - **Healthy invariant:** Per-UE rate. Tracks pcscf.invite rate.

- **`normalized.pcscf.core:rcv_requests_invite_per_ue`** (SIP INVITE rate per UE at P-CSCF) — current **0.03 requests_per_second** vs learned baseline **0.00 requests_per_second** (MEDIUM, spike)
    - **What it measures:** Call attempt rate from registered UEs. Unlike REGISTER (periodic),
INVITEs only fire when UEs place calls. Zero is normal during
quiet periods; nonzero INVITE with zero dialogs is the signature
of call setup failure.
    - **Spike means:** Fewer call attempts.
    - **Healthy typical range:** 0–0.2 requests_per_second
    - **Healthy invariant:** Per-UE rate.

- **`normalized.scscf.core:rcv_requests_invite_per_ue`** (SIP INVITE rate per UE at S-CSCF) — current **0.03 requests_per_second** vs learned baseline **0.00 requests_per_second** (MEDIUM, spike)
    - **What it measures:** S-CSCF participation in call setup. Zero when calls aren't being
placed OR S-CSCF not receiving forwarded INVITEs.
    - **Spike means:** Upstream forwarding issue.
    - **Healthy typical range:** 0–0.2 requests_per_second
    - **Healthy invariant:** Per-UE rate.

- **`normalized.upf.gtp_indatapktn3upf_per_ue`** (GTP-U uplink rate per UE (N3)) — current **3.39 packets_per_second** vs learned baseline **1.45 packets_per_second** (MEDIUM, spike)
    - **What it measures:** Health of the uplink user-plane path gNB → UPF. Drops to near-zero
during RAN or N3 outage; stays nonzero during active calls or data
sessions. Decoupled from SIP signaling (signals data plane, not
control plane).
    - **Spike means:** Either UEs not generating uplink traffic (no calls/data) or N3 path is degraded.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE rate. Constant regardless of UE pool size. Rises during
active VoNR calls (~100 pps for G.711 voice) and data transfer.
Uplink and downlink (gtp_outdatapktn3upf_per_ue) are independent
directions whose ratio is determined entirely by the current
traffic profile — voice with NULL_AUDIO (this testbed),
signaling-only chatter, idle UEs, and asymmetric data sessions
all produce persistent in/out imbalance under healthy operation.
Asymmetry between uplink and downlink rates is NEVER, by itself,
evidence of packet loss — not at any magnitude, not under any
traffic mix. To detect actual loss, use the methods listed in
stack rule `upf_counters_are_directional` (same-direction rate
comparison, RTCP loss_ratio at RTPEngine, or tc qdisc drop
counters). Rate-based metrics like this one are usually MORE
informative than the underlying lifetime cumulative counter for
current-state failure detection.

- **`normalized.upf.gtp_outdatapktn3upf_per_ue`** (GTP-U downlink rate per UE (N3)) — current **3.26 packets_per_second** vs learned baseline **1.45 packets_per_second** (MEDIUM, spike)
    - **What it measures:** Health of the downlink user-plane path UPF → gNB. Drops to
near-zero during a downlink-affecting RAN, N3, or UPF
outage; stays nonzero during active calls or data sessions.
Decoupled from SIP signaling. The cross-direction
relationship to uplink (gtp_indatapktn3upf_per_ue) reflects
current traffic profile, NOT data-plane health — voice
with NULL_AUDIO, signaling-only chatter, idle UEs, and
asymmetric data sessions all produce persistent in/out
imbalance under healthy operation. Use this metric for
same-direction collapse detection (a known-active downlink
collapsing toward zero); do NOT infer loss from
uplink-vs-downlink asymmetry — see stack rule
upf_counters_are_directional.
    - **Spike means:** Downlink data plane degraded ON THIS DIRECTION SPECIFICALLY
— UPF is not forwarding toward gNB at the rate consistent
with the current traffic profile. To confirm loss (vs a
traffic-profile shift that just lowered downlink demand),
cross-check RTCP loss_ratio at RTPEngine and the same-
direction expected rate per stack rule
upf_counters_are_directional.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE rate. Constant regardless of UE pool size. Uplink
(gtp_indatapktn3upf_per_ue) and downlink are independent
directions whose ratio is determined entirely by the current
traffic profile — voice with NULL_AUDIO (this testbed),
signaling-only chatter, idle UEs, and asymmetric data
sessions all produce persistent in/out imbalance under
healthy operation. Asymmetry between uplink and downlink
rates is NEVER, by itself, evidence of packet loss — not
at any magnitude, not under any traffic mix. To detect
actual loss, use the methods listed in stack rule
`upf_counters_are_directional` (same-direction rate
comparison, RTCP loss_ratio at RTPEngine, or tc qdisc drop
counters). Rate-based metrics like this one are usually
MORE informative than the underlying lifetime cumulative
counter for current-state failure detection.

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

- **`normalized.scscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at S-CSCF) — current **0.03 requests_per_second** vs learned baseline **0.06 requests_per_second** (LOW, drop)
    - **What it measures:** Health of the I-CSCF → S-CSCF forwarding path. Drop to zero while
I-CSCF is receiving REGISTERs = S-CSCF-side issue (crashed, or
I-CSCF → S-CSCF path broken).
    - **Drop means:** S-CSCF isolated or not running.
    - **Healthy typical range:** 0–0.5 requests_per_second
    - **Healthy invariant:** Per-UE rate. Tracks icscf.register rate.


## Event Aggregation (Phase 1)

**1 events fired during the observation window:**

- `core.upf.activity_during_calls_collapsed` (source: `core.upf.activity_during_calls`, nf: `upf`, t=1778073388.7)  [current_value=0.059091000000000005]

## Correlation Analysis (Phase 2)

1 events fired but no composite hypothesis emerged. The events may be from independent faults or lack registered correlation hints in the KB.

## Network Analysis (Phase 3)

**Summary:** The data plane has collapsed, causing a live call to fail and preventing any new IMS signaling; evidence points to a fault at the UPF.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** |   |  |
| **ran** | 🟢 GREEN | RAN appears healthy. AMF reports that UEs are still attached. |
| **core** | 🔴 RED | The UPF is the primary suspect for a major data plane outage. The 'activity_during_calls_collapsed' event is a strong indicator of failure, and metrics show a significant deviation from baseline. |
| **ims** | 🔴 RED | IMS is heavily impacted. RTPEngine reports a massive packet loss ratio, and all SIP signaling has ceased. This appears to be a downstream consequence of the core data plane failure. |

**CORE evidence:**
- core.upf.activity_during_calls_collapsed
- normalized.upf.gtp_indatapktn3upf_per_ue
- normalized.upf.gtp_outdatapktn3upf_per_ue

**IMS evidence:**
- derived.rtpengine_loss_ratio
- normalized.pcscf.core:rcv_requests_register_per_ue
- normalized.icscf.core:rcv_requests_register_per_ue
- normalized.scscf.core:rcv_requests_register_per_ue

**Ranked hypotheses:**

- **`h1`** (fit=0.90, nf=upf, specificity=specific):
    - **Statement:** The UPF is the source of a data plane failure, causing severe packet loss for RTP media streams and blocking all UE-to-network SIP signaling.
    - **Supporting events:** `core.upf.activity_during_calls_collapsed`, `derived.rtpengine_loss_ratio`
    - **Falsification probes:**
        - Check tc/iptables/nftables stats on the UPF container for dropped packets.
        - Run a packet capture on the UPF's N3 and N6 interfaces to verify if it is forwarding traffic.
        - Measure RTT between RTPEngine and UPF to check for path degradation.
- **`h2`** (fit=0.70, nf=rtpengine, specificity=specific):
    - **Statement:** The RTPEngine is the source of the media-plane packet loss, originating from its own networking stack or egress path, causing the observed quality collapse.
    - **Supporting events:** `derived.rtpengine_loss_ratio`
    - **Falsification probes:**
        - Check for packet drops on the RTPEngine container's interfaces (e.g., using `tc -s qdisc show`).
        - Inspect the RTPEngine logs for any errors not captured by the 'errors_per_second' metric.
        - Run a packet capture on the RTPEngine's interfaces to trace the flow of RTP packets.


## Falsification Plans (Phase 4)

**2 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `upf`)

**Hypothesis:** The UPF is the source of a data plane failure, causing severe packet loss for RTP media streams and blocking all UE-to-network SIP signaling.

**Probes (3):**
1. **`get_dp_quality_gauges`** — Check UPF's GTP-U packet rates on the N3 interface over a 120s window.
    - *Expected if hypothesis holds:* The values for `upf.gtp_indatapktn3upf_per_ue` and `upf.gtp_outdatapktn3upf_per_ue` are near zero or significantly below baseline.
    - *Falsifying observation:* The values for `upf.gtp_indatapktn3upf_per_ue` and `upf.gtp_outdatapktn3upf_per_ue` are within their typical range, indicating traffic is flowing correctly over the N3 interface.
2. **`measure_rtt`** — from='rtpengine', to_ip='<upf_n6_ip>'. Measures connectivity on the user plane path from RTPEngine to UPF.
    - *Expected if hypothesis holds:* High RTT or packet loss is observed.
    - *Falsifying observation:* Normal RTT and zero packet loss are observed.
3. **`measure_rtt`** — from='smf', to_ip='<upf_n4_ip>'. This is a partner probe to measure connectivity on the control plane path from SMF to UPF.
    - *Expected if hypothesis holds:* High RTT or packet loss is also observed on this path, suggesting the issue is with the UPF node itself.
    - *Falsifying observation:* Normal RTT and zero packet loss are observed. This result, combined with a failure in the rtpengine->upf probe, would suggest the fault lies on the N6 path or with RTPEngine, not the UPF itself.

*Notes:* This plan uses a compositional probe (`measure_rtt` from rtpengine) and a partner probe (from smf) to distinguish between a general UPF failure and a path-specific issue, addressing linter feedback A1. Probes also check data plane counters directly at the UPF.

### Plan for `h2` (target: `rtpengine`)

**Hypothesis:** The RTPEngine is the source of the media-plane packet loss, originating from its own networking stack or egress path, causing the observed quality collapse.

**Probes (3):**
1. **`get_dp_quality_gauges`** — Check for internal processing errors in RTPEngine over a 120s window.
    - *Expected if hypothesis holds:* The `ims.rtpengine.errors_per_second` metric is greater than zero, indicating active errors inside the RTPEngine relay.
    - *Falsifying observation:* The `ims.rtpengine.errors_per_second` metric is zero, indicating the observed loss is not caused by RTPEngine's internal relay logic.
2. **`get_network_status`** — Check the container status of 'rtpengine'.
    - *Expected if hypothesis holds:* The 'rtpengine' container is in a 'running' state.
    - *Falsifying observation:* The 'rtpengine' container is in an 'exited' or other non-running state, which would indicate a container crash rather than a media quality issue in a running instance.
3. **`get_dp_quality_gauges`** — Check UPF's N3 interface packet rates to help isolate the location of the packet loss.
    - *Expected if hypothesis holds:* The `upf.gtp_indatapktn3upf_per_ue` and `upf.gtp_outdatapktn3upf_per_ue` metrics show traffic flowing in both directions. This would imply the path through the UPF to the RAN is healthy, pointing towards a problem at RTPEngine.
    - *Falsifying observation:* The UPF N3 packet counters show a significant drop, halt, or directional asymmetry in traffic. This would suggest the problem is located at the UPF or on the RAN, not at RTPEngine.

*Notes:* This plan attempts to isolate the fault to RTPEngine by checking for internal application-level errors and verifying that adjacent components in the data path (UPF) are still forwarding traffic as expected.


## Parallel Investigators (Phase 5)

**3 sub-Investigator verdict(s):** **3 DISPROVEN**

### `h1` — ❌ **DISPROVEN**

**Hypothesis:** The UPF is the source of a data plane failure, causing severe packet loss for RTP media streams and blocking all UE-to-network SIP signaling.

**Reasoning:** [Multi-shot consensus — both shots returned DISPROVEN.]

Shot 1: Probes measuring RTT from both `rtpengine` and `smf` to the UPF show 0% packet loss and normal, low latency. This contradicts the hypothesis that the UPF is the source of a data plane failure, as it is reachable and responsive on network paths associated with its user plane (N6) and control plane (N4) interfaces. While data plane quality metrics show high packet loss reported by RTPEngine, the clean connectivity results for the UPF suggest it is not the root cause. The issue likely lies elsewhere, possibly with RTPEngine itself.

Shot 2: The hypothesis is disproven by a partner probe that isolates the fault to the user plane path, not the UPF itself. While a probe from RTPEngine to the UPF shows significant packet loss (33%), a parallel probe from the SMF to the UPF's control plane interface shows 0% packet loss. This indicates the UPF is responsive and healthy on its control plane interface, contradicting the idea that the UPF node is the root source of the failure. The problem is localized to the N6 data path between RTPEngine and UPF.

**Probes executed (3):**
- **Check UPF's GTP-U packet rates on the N3 interface over a 120s window.** ~ AMBIGUOUS
    - *Tool:* `default_api.get_dp_quality_gauges(at_time_ts=1778073349.6518736, window_seconds=120)`
    - *Observation:* [EVIDENCE: get_dp_quality_gauges(at_time_ts=1778073349.6518736, window_seconds=120) -> "UPF:\n    in  packets/sec: 4.9\n    out packets/sec: 3.7\n    in  throughput : 0.61 KB/s\n    out throughput : 0.53 KB/s"]
    - *Comment:* The packet rates are very low but not zero, which is ambiguous. The hypothesis expected near-zero rates, so this doesn't strongly confirm or contradict. However, the high loss ratio of 20.86 reported by RTPEngine in the same tool output is consistent with the symptom of 'severe packet loss'.
- **from='rtpengine', to_ip='<upf_n6_ip>'. Measures connectivity on the user plane path from RTPEngine to UPF.** ✗ CONTRADICTS
    - *Tool:* `default_api.measure_rtt(container='rtpengine', target_ip='172.22.0.8')`
    - *Observation:* [EVIDENCE: measure_rtt('rtpengine', '172.22.0.8') -> "3 packets transmitted, 3 received, 0% packet loss, time 2044ms\nrtt min/avg/max/mdev = 0.082/0.331/0.809/0.337 ms"]
    - *Comment:* This result shows perfect connectivity and normal RTT between the RTPEngine and the UPF. This contradicts the hypothesis that the UPF is the source of the data plane failure, as the path to it is healthy.
- **from='smf', to_ip='<upf_n4_ip>'. This is a partner probe to measure connectivity on the control plane path from SMF to UPF.** ✗ CONTRADICTS
    - *Tool:* `default_api.measure_rtt(container='smf', target_ip='172.22.0.8')`
    - *Observation:* [EVIDENCE: measure_rtt('smf', '172.22.0.8') -> "3 packets transmitted, 3 received, 0% packet loss, time 2029ms\nrtt min/avg/max/mdev = 0.079/0.122/0.186/0.045 ms"]
    - *Comment:* This partner probe also shows perfect connectivity and normal RTT, this time from the SMF to the UPF. Combined with the previous probe, this strongly indicates that the UPF node is not experiencing a general failure or network partition.

**Alternative suspects:** rtpengine

### `h2` — ❌ **DISPROVEN**

**Hypothesis:** The RTPEngine is the source of the media-plane packet loss, originating from its own networking stack or egress path, causing the observed quality collapse.

**Reasoning:** [Multi-shot consensus — both shots returned DISPROVEN.]

Shot 1: The evidence contradicts the hypothesis that RTPEngine is the source of the packet loss. Probe 1 revealed that RTPEngine's internal error rate is zero, indicating its relay logic is functioning correctly. Probe 3 showed significantly degraded packet rates at the UPF, which is downstream from RTPEngine in the media path. This suggests the data plane issue is located at or before the UPF, not originating from RTPEngine's egress path.

Shot 2: The hypothesis is disproven by probe results indicating the issue lies with the UPF, not the RTPEngine. While RTPEngine is reporting high packet loss, the `get_dp_quality_gauges` tool shows that the UPF's N3 interface has extremely low packet rates (in: 4.9 pps, out: 3.7 pps). If RTPEngine were the source of the loss, the UPF would still show healthy traffic volumes passing through it. The collapse in traffic at the UPF points to it, or a path leading to it, as the source of the failure.

**Probes executed (3):**
- **Check for internal processing errors in RTPEngine over a 120s window.** ✗ CONTRADICTS
    - *Tool:* `print(default_api.get_diagnostic_metrics(at_time_ts = 1778073349.6518736, nfs = ["rtpengine"]))`
    - *Observation:* [EVIDENCE: get_diagnostic_metrics(at_time_ts=1778073349.6518736, nfs=["rtpengine"]) -> "rtpengine.errors_per_second_(total) = 0 [gauge, errors_per_second]"]
    - *Comment:* The metric `rtpengine.errors_per_second_(total)` was 0, which contradicts the expectation that it would be greater than zero if RTPEngine's internal relay were the source of errors. This is the falsifying observation.
- **Check the container status of 'rtpengine'.** ✓ CONSISTENT
    - *Tool:* `print(default_api.get_network_status())`
    - *Observation:* [EVIDENCE: get_network_status() -> "'rtpengine': 'running'"]
    - *Comment:* The 'rtpengine' container is in a 'running' state, which is consistent with the hypothesis that the issue is a media quality problem within a running instance, not a container crash.
- **Check UPF's N3 interface packet rates to help isolate the location of the packet loss.** ✗ CONTRADICTS
    - *Tool:* `print(default_api.get_dp_quality_gauges(at_time_ts = 1778073349.6518736, window_seconds = 120))`
    - *Observation:* [EVIDENCE: get_dp_quality_gauges(at_time_ts=1778073349.6518736, window_seconds=120) -> "UPF: in packets/sec: 4.9 out packets/sec: 3.7"]
    - *Comment:* The packet rates at the UPF are extremely low, indicating a significant drop or halt in traffic. This contradicts the expectation that traffic would be flowing normally through the UPF, and instead suggests the problem is located at the UPF or on the path leading to it.

**Alternative suspects:** upf

### `h_promoted_rtpengine` — ❌ **DISPROVEN**

**Hypothesis:** rtpengine is the source of the anomaly named in the alternative_suspects of the original verdict tree.

**Reasoning:** The hypothesis is disproven because key indicators of an rtpengine-internal fault are absent. Specifically, the 'rtpengine.errors_per_second' metric was 0, contradicting the expectation that a faulty rtpengine relay would be reporting errors. Furthermore, the 'upf.gtp_outdatapktn3upf_per_ue' metric, which tracks downlink traffic from the UPF, was healthy and not showing the expected drop. While a high packet loss ratio was observed, the combination of zero errors at rtpengine and healthy downstream traffic at the UPF points to the data loss occurring elsewhere on the media path, not within rtpengine itself.

**Probes executed (3):**
- **Returns rate-based MOS/loss/jitter alongside RTPEngine errors. Check 'ims.rtpengine.errors_per_second'.** ✗ CONTRADICTS
    - *Tool:* `default_api.get_diagnostic_metrics(at_time_ts=1778073349.6518736, nfs=['rtpengine', 'upf'])`
    - *Observation:* [EVIDENCE: get_diagnostic_metrics(at_time_ts=1778073349.6518736, nfs=['rtpengine', 'upf']) -> "rtpengine.errors_per_second_(total) = 0 [gauge, errors_per_second]"]
    - *Comment:* The 'ims.rtpengine.errors_per_second' metric was 0. This directly contradicts the expected outcome for a faulty rtpengine relay, which would be a value greater than 0. This suggests the relay loop within rtpengine is healthy.
- **window_seconds=120 to confirm MOS drop and packet-loss percentage across the same window. Check 'ims.rtpengine.loss_ratio'.** ✓ CONSISTENT
    - *Tool:* `default_api.get_dp_quality_gauges(at_time_ts=1778073349.6518736, window_seconds=120)`
    - *Observation:* [EVIDENCE: get_dp_quality_gauges(at_time_ts=1778073349.6518736, window_seconds=120) -> "loss (recent)  : 20.86"]
    - *Comment:* The packet loss ratio is extremely high (20.86, where healthy is < 0.1), which is consistent with a data plane anomaly. However, this observation on its own does not localize the fault to rtpengine.
- **Returns rate-windowed UPF in/out pps. Check 'upf.gtp_outdatapktn3upf_per_ue' to observe downlink traffic.** ✗ CONTRADICTS
    - *Tool:* `default_api.get_diagnostic_metrics(at_time_ts=1778073349.6518736, nfs=['rtpengine', 'upf'])`
    - *Observation:* [EVIDENCE: get_diagnostic_metrics(at_time_ts=1778073349.6518736, nfs=['rtpengine', 'upf']) -> "normalized.upf.gtp_outdatapktn3upf_per_ue = 3.256 [derived, packets_per_second]"]
    - *Comment:* The downlink packet rate from the UPF is healthy and shows no drop. This contradicts the expectation that a fault in rtpengine would disrupt the downlink path, suggesting the loss is not occurring on the path between rtpengine and the gNB (via UPF).

**Alternative suspects:** UPF


## Evidence Validation (Phase 6)

**Overall verdict:** clean
**Overall confidence:** high

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 8 | 3/3 | clean | high |
| `InvestigatorAgent_h2` | 6 | 3/3 | clean | high |
| `InvestigatorAgent_h_promoted_rtpengine` | 2 | 3/3 | clean | high |


## Ground Truth

**Failure domain:** ims_media  
**Protocol impact:** RTP  
**Affected components:** rtpengine  
**Severity:** degraded

## Agent Diagnosis

**Model:** v6-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 436.0s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: A data plane collapse caused a live call to fail, with evidence pointing to a fault within the User Plane Function (UPF) despite initial hypotheses being disproven.
> - **timeline**:
>     1. core.upf.activity_during_calls_collapsed
>     2. derived.rtpengine_loss_ratio
> - **root_cause**: All initial hypotheses were disproven, but cross-corroboration from investigator verdicts consistently implicates the UPF as the source of the data plane failure. Probes ruled out a simple network partition, suggesting a more subtle failure in the UPF's packet forwarding logic. (primary_suspect_nf: `upf`)
> - **affected_components**:
>     - `upf`: Root Cause
>     - `rtpengine`: Symptomatic
>     - `ims`: Secondary
> - **recommendation**: The initial connectivity probes to the UPF were insufficient to detect a data plane forwarding issue. A human operator should inspect the UPF's internal state, specifically checking traffic control or firewall statistics (e.g., using `tc -s qdisc show` or `nft list ruleset`) for dropped packets. A packet capture on the UPF's N3 and N6 interfaces would also help verify if it is forwarding GTP-U traffic correctly.
> - **confidence**: low
> - **verdict_kind**: promoted
> - **explanation**: All initial hypotheses, including one targeting the UPF (h1) and two targeting RTPEngine (h2, h_promoted_rtpengine), were disproven. However, the investigations into RTPEngine both concluded that the UPF was the more likely alternative suspect. The probes used to disprove the UPF hypothesis only confirmed its basic network reachability via RTT checks, which passed. This does not rule out a failure in the UPF's internal data plane forwarding logic. Given the symptoms of massive packet loss and collapsed traffic, and the elimination of RTPEngine, the UPF remains the most probable, though unconfirmed, root cause.

### Scoring Breakdown

**Overall score: 46%**

**Scorer assessment:** The agent correctly identified the fault type (packet loss) and its severity, and showed good confidence calibration. It also correctly identified the IMS layer as affected. However, it incorrectly attributed the root cause to the UPF, despite RTPEngine being the actual source of the packet loss, and only listed RTPEngine as symptomatic.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | No | The simulated failure was 30% packet loss on RTPEngine. The agent's final diagnosis explicitly states that RTPEngine hypotheses were 'disproven' and 'eliminated', concluding that the UPF is the root cause. This is incorrect. |
| Component overlap | 30% | The primary affected component is 'rtpengine'. The agent lists 'rtpengine' in 'affected_components' but labels it 'Symptomatic', while incorrectly labeling 'upf' as 'Root Cause'. This indicates it recognized RTPEngine's involvement but mis-ranked its causal role. |
| Severity correct | Yes | The simulated failure involved 30% packet loss, leading to 'degrading voice quality'. The agent described the situation as 'massive packet loss' and 'collapsed traffic', which accurately reflects a severe degradation or impairment. |
| Fault type identified | Yes | The simulated failure was 'packet loss'. The agent's diagnosis clearly identifies 'massive packet loss' and issues with 'packet forwarding logic' as the core problem, even if attributed to the wrong component. |
| Layer accuracy | Yes | The simulated failure component 'rtpengine' belongs to the 'ims' layer. The agent's network analysis correctly rated the 'ims' layer as 'red' and cited 'derived.rtpengine_loss_ratio' as evidence, indicating correct layer attribution for the observed symptoms. |
| Confidence calibrated | Yes | The agent's confidence is 'low', and its explanation states 'All initial hypotheses were disproven' and 'UPF remains the most probable, though unconfirmed, root cause.' Given that the root cause identified was incorrect, this low confidence is well-calibrated to the uncertainty and incorrectness of the diagnosis. |

**Ranking:** The correct root cause (RTPEngine packet loss) was not identified as the primary root cause. RTPEngine was listed as 'Symptomatic' while UPF was incorrectly identified as the 'Root Cause'.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 480,247 |
| Output tokens | 10,555 |
| Thinking tokens | 35,466 |
| **Total tokens** | **526,268** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| EventAggregator | 0 | 0 | 0 |
| CorrelationAnalyzer | 0 | 0 | 0 |
| NetworkAnalystAgent | 118,913 | 5 | 6 |
| Phase 3 NetworkAnalyst__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 33,430 | 1 | 2 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 35,621 | 1 | 2 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| InvestigatorAgent_h1 | 73,442 | 4 | 5 |
| InvestigatorAgent_h1 | 41,647 | 4 | 3 |
| InvestigatorAgent_h1__reconciliation | 0 | 0 | 0 |
| InvestigatorAgent_h2 | 55,760 | 3 | 4 |
| InvestigatorAgent_h2 | 52,032 | 3 | 4 |
| InvestigatorAgent_h2__reconciliation | 0 | 0 | 0 |
| Phase5FanOutAudit | 0 | 0 | 0 |
| Phase6.5CandidatePool | 0 | 0 | 0 |
| InstructionGeneratorAgent | 32,133 | 1 | 2 |
| Phase 6.5 Reinvestigation IG__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 28,996 | 1 | 2 |
| Phase 6.5 Reinvestigation IG__guardrail | 0 | 0 | 0 |
| InvestigatorAgent_h_promoted_rtpengine | 45,954 | 2 | 3 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 8,340 | 0 | 1 |
| Phase 7 Synthesis__guardrail | 0 | 0 | 0 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 586.9s
