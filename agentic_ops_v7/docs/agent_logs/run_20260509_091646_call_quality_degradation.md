# Episode Report: Call Quality Degradation

**Agent:** v7  
**Episode ID:** ep_20260509_090501_call_quality_degradation  
**Date:** 2026-05-09T09:05:05.595579+00:00  
**Duration:** 700.6s  

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

**ANOMALY DETECTED.** Overall anomaly score: 48.85 (per-bucket threshold: 28.18, context bucket (1, 1), trained on 323 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following metrics deviate from their learned-healthy baseline. Treat each as a semantic observation (meaning + numbers), not a number alone — the KB's interpretation is the authoritative reading.

- **`derived.rtpengine_loss_ratio`** (RTPEngine RTCP-reported per-RR average packet loss) — current **25.26 packets_per_rr** vs learned baseline **0.00 packets_per_rr** (MEDIUM, spike)
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

- **`normalized.icscf.cdp_replies_per_ue`** (I-CSCF Diameter reply rate per UE) — current **0.07 replies_per_second_per_ue** vs learned baseline **0.03 replies_per_second_per_ue** (MEDIUM, spike)
    - **What it measures:** Liveness of the I-CSCF↔HSS Cx path. Drops to 0 when HSS is unreachable OR when no signaling is occurring at the I-CSCF (idle or upstream P-CSCF partitioned).
    - **Spike means:** Either HSS is unreachable or upstream signaling has stopped reaching I-CSCF.
    - **Healthy typical range:** 0–1 replies_per_second_per_ue

- **`normalized.icscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at I-CSCF) — current **0.11 requests_per_second** vs learned baseline **0.06 requests_per_second** (MEDIUM, spike)
    - **What it measures:** Health of the P-CSCF → I-CSCF forwarding path (Mw interface). When
this drops to zero while P-CSCF REGISTER rate is still non-zero,
it's the SIGNATURE of an IMS partition between P-CSCF and I-CSCF.
    - **Spike means:** Forwarding issue on the Mw interface, or P-CSCF stopped forwarding.
    - **Healthy typical range:** 0–0.5 requests_per_second
    - **Healthy invariant:** Per-UE rate. Should closely track ims.pcscf.rcv_requests_register_per_ue.

- **`normalized.pcscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at P-CSCF) — current **0.11 requests_per_second** vs learned baseline **0.06 requests_per_second** (MEDIUM, spike)
    - **What it measures:** How actively UEs are refreshing their IMS registrations with the
P-CSCF. REGISTERs arrive periodically (re-registration timer) plus
at attach. Sustained zero means UEs cannot reach P-CSCF OR the
UE-to-network SIP path is broken.
    - **Spike means:** Fewer REGISTERs than expected — UE connectivity or P-CSCF reachability issue.
    - **Healthy typical range:** 0–0.5 requests_per_second
    - **Healthy invariant:** Per-UE rate — same value at any deployment scale.

- **`normalized.pcscf.dialogs_per_ue`** (Active SIP dialogs per registered UE at P-CSCF) — current **2.00 count** vs learned baseline **0.48 count** (MEDIUM, spike)
    - **What it measures:** How many calls per user are currently in progress at the P-CSCF.
Going to zero from a non-zero baseline means calls have ended
(normal) OR call setup is failing system-wide (degradation).
Together with rcv_requests_* it discriminates the two.
    - **Spike means:** Calls ending or setup failing.
    - **Healthy typical range:** 0–1 count
    - **Healthy invariant:** Per-UE — scale-independent. 0 at rest, ~1 per active VoNR call.

- **`normalized.scscf.cdp_replies_per_ue`** (S-CSCF CDP Diameter replies per UE) — current **0.11 replies_per_second_per_ue** vs learned baseline **0.06 replies_per_second_per_ue** (MEDIUM, spike)
    - **What it measures:** Active S-CSCF Diameter traffic with HSS. Near-zero when registrations idle OR HSS partition.
    - **Spike means:** Diameter peering loss with HSS.
    - **Healthy typical range:** 0–1 replies_per_second_per_ue
    - **Healthy invariant:** Per-UE rate; varies with registration/auth load.

- **`normalized.scscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at S-CSCF) — current **0.11 requests_per_second** vs learned baseline **0.06 requests_per_second** (MEDIUM, spike)
    - **What it measures:** Health of the I-CSCF → S-CSCF forwarding path. Drop to zero while
I-CSCF is receiving REGISTERs = S-CSCF-side issue (crashed, or
I-CSCF → S-CSCF path broken).
    - **Spike means:** I-CSCF not forwarding or S-CSCF not receiving.
    - **Healthy typical range:** 0–0.5 requests_per_second
    - **Healthy invariant:** Per-UE rate. Tracks icscf.register rate.

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

- **`normalized.upf.gtp_indatapktn3upf_per_ue`** (GTP-U uplink rate per UE (N3)) — current **7.53 packets_per_second** vs learned baseline **1.45 packets_per_second** (MEDIUM, spike)
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

- **`normalized.upf.gtp_outdatapktn3upf_per_ue`** (GTP-U downlink rate per UE (N3)) — current **5.32 packets_per_second** vs learned baseline **1.45 packets_per_second** (MEDIUM, spike)
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


## Network Analysis (Phase 1)

**Summary:** The network is experiencing severe media plane packet loss, with secondary indications of IMS signaling issues.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** |   |  |
| **ran** | 🟢 GREEN | No metrics or events point to a RAN-layer fault. |
| **core** | 🔴 RED | The data plane, which involves the UPF, is clearly impacted. A fired event directly implicates the UPF's activity during calls. |
| **ims** | 🔴 RED | The primary anomaly is a massive spike in the RTPEngine packet loss ratio, indicating a severe media quality degradation. |

**CORE evidence:**
- core.upf.activity_during_calls_collapsed

**IMS evidence:**
- derived.rtpengine_loss_ratio

**Ranked hypotheses:**

- **`h1`** (fit=0.90, nf=rtpengine, specificity=specific):
    - **Statement:** rtpengine is the source of the severe media packet loss observed in the 'derived.rtpengine_loss_ratio' metric.
    - **Falsification probes:**
        - Check for packet drops on the rtpengine container's egress network interface using `tc -s qdisc show`.
        - A measure_rtt probe from rtpengine to upf showing no loss would indicate the loss originates elsewhere.
- **`h2`** (fit=0.70, nf=upf, specificity=specific):
    - **Statement:** upf is the source of the data plane fault, causing the collapse in activity reported by the `core.upf.activity_during_calls_collapsed` event and contributing to the packet loss seen by rtpengine.
    - **Supporting events:** `core.upf.activity_during_calls_collapsed`
    - **Falsification probes:**
        - Check for packet drops on the UPF's N3 and N6 interfaces using `tc -s qdisc show`.
        - A measure_rtt probe from rtpengine to upf showing significant loss would implicate the path or the UPF itself.
- **`h3`** (fit=0.40, nf=pyhss, specificity=moderate):
    - **Statement:** The HSS is the source of the IMS signaling disruption, evidenced by anomalous Diameter reply rates from both I-CSCF and S-CSCF.
    - **Falsification probes:**
        - A measure_rtt probe from 'icscf' to the 'pyhss' IP showing high latency or packet loss would confirm a Cx path issue.
        - Querying HSS-internal metrics for signs of overload or errors.


## Pattern Match (Phase 2)

*No output produced.*

## Investigation Instruction (Phase 3)

**3 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `rtpengine`)

**Hypothesis:** rtpengine is the source of the severe media packet loss observed in the 'derived.rtpengine_loss_ratio' metric.

**Probes (3):**
1. **`get_dp_quality_gauges`** — Returns rate-based MOS/loss/jitter alongside RTPEngine errors.
    - *Expected if hypothesis holds:* Probe reads a non-zero value for `rtpengine.errors_per_second`, indicating active relay-loop errors.
    - *Falsifying observation:* Probe reads that `rtpengine.errors_per_second` is zero, suggesting the relay loop is healthy and packet loss originates elsewhere in the media path.
2. **`get_dp_quality_gauges`** — window_seconds=120 to confirm MOS drop and packet-loss percentage across the same window
    - *Expected if hypothesis holds:* A high value for `rtpengine.loss_ratio` is observed, confirming sustained packet loss.
    - *Falsifying observation:* The `rtpengine.loss_ratio` is within its healthy baseline (0.0-0.1), which would contradict the initial anomaly detection.
3. **`get_dp_quality_gauges`** — Check UPF's downlink packet rate (traffic from rtpengine).
    - *Expected if hypothesis holds:* UPF's per-UE downlink packet rate (`gtp_outdatapktn3upf_per_ue`) is significantly reduced or zero, suggesting that packets are being dropped by rtpengine before reaching the UPF.
    - *Falsifying observation:* UPF's per-UE downlink packet rate (`gtp_outdatapktn3upf_per_ue`) is at a healthy, non-zero level, indicating that rtpengine is forwarding packets correctly to the UPF.

*Notes:* This plan uses the KB-authored probe candidates for h1. It first checks for errors within rtpengine, then confirms the high-level loss metric, and finally checks a downstream component (UPF) to see if packets are being forwarded from rtpengine. This avoids compositional ambiguity. Reference 'vonr_media' flow, steps 3 and 4.

### Plan for `h2` (target: `upf`)

**Hypothesis:** upf is the source of the data plane fault, causing the collapse in activity reported by the `core.upf.activity_during_calls_collapsed` event and contributing to the packet loss seen by rtpengine.

**Probes (3):**
1. **`get_dp_quality_gauges`** — Returns UPF in/out pps, RTPEngine sessions; correlate.
    - *Expected if hypothesis holds:* The `upf.activity_during_calls` metric is near zero, confirming that media traffic is not flowing through the UPF as expected during active calls.
    - *Falsifying observation:* The `upf.activity_during_calls` metric is close to its healthy value of 1.0, indicating media is flowing correctly through the UPF.
2. **`measure_rtt`** — Probe path from rtpengine to upf's N6 interface IP.
    - *Expected if hypothesis holds:* High RTT or packet loss is observed.
    - *Falsifying observation:* Low RTT and zero packet loss are observed.
3. **`measure_rtt`** — Probe path from smf to upf's N4 interface IP.
    - *Expected if hypothesis holds:* High RTT or packet loss is observed. If the rtpengine->upf probe also shows loss, it strengthens the hypothesis that the UPF is the source.
    - *Falsifying observation:* Low RTT and zero packet loss are observed. If the rtpengine->upf probe showed loss but this one does not, it suggests the fault lies on the path to the N6 interface, not the UPF itself.

*Notes:* This plan confirms the collapsed activity at the UPF. It then uses a pair of `measure_rtt` probes from different sources (rtpengine, smf) to the suspect NF (upf) to disambiguate between a fault in the UPF itself versus a fault on one of the network paths leading to it. This directly addresses the feedback on compositional probes. Reference 'data_pdu_session_user_traffic' and 'vonr_media' flows.

### Plan for `h3` (target: `pyhss`)

**Hypothesis:** The HSS is the source of the IMS signaling disruption, evidenced by anomalous Diameter reply rates from both I-CSCF and S-CSCF.

**Probes (3):**
1. **`measure_rtt`** — from='icscf', to_ip='<pyhss_ip>'
    - *Expected if hypothesis holds:* High RTT or packet loss is observed.
    - *Falsifying observation:* Low RTT and zero packet loss are observed.
2. **`measure_rtt`** — from='scscf', to_ip='<pyhss_ip>'
    - *Expected if hypothesis holds:* High RTT or packet loss is observed. If the probe from icscf also shows issues, it points towards pyhss as the common point of failure.
    - *Falsifying observation:* Low RTT and zero packet loss are observed. This would suggest any issue seen from icscf is path-specific, not due to pyhss.
3. **`get_network_status`** — Check the running status of the pyhss container.
    - *Expected if hypothesis holds:* The pyhss container is in a 'down' or 'restarting' state.
    - *Falsifying observation:* The pyhss container is in a 'running' state.

*Notes:* This plan investigates the HSS hypothesis. It uses a pair of `measure_rtt` probes from two different clients (i-cscf, s-cscf) that both depend on the HSS. This allows for disambiguation between a network path issue and an issue with the HSS container itself. A third probe checks the basic status of the container. The plan avoids mechanism-scoping language as required by the feedback.


## Investigation (Phase 4)

**4 sub-Investigator verdict(s):** **3 DISPROVEN**, **1 NOT_DISPROVEN**

### `h1` — ❌ **DISPROVEN**

**Hypothesis:** rtpengine is the source of the severe media packet loss observed in the 'derived.rtpengine_loss_ratio' metric.

**Reasoning:** [Multi-shot consensus — both shots returned DISPROVEN.]

Shot 1: The investigation revealed two key pieces of evidence that contradict the hypothesis. First, `rtpengine.errors_per_second` was zero, indicating that rtpengine's internal relay loop is healthy and not the source of errors. Second, the UPF's per-UE downlink packet rate (`gtp_outdatapktn3upf_per_ue`) was at a healthy, non-zero level, demonstrating that rtpengine is successfully forwarding packets to the UPF. While the high `rtpengine.loss_ratio` confirms severe packet loss, the other probes localize the source of this loss to be downstream of the UPF, likely in the RAN.

Shot 2: The investigation found that while the 'derived.rtpengine_loss_ratio' is indeed extremely high, the 'rtpengine.errors_per_second' metric is zero. According to the falsification plan, a zero value for internal errors suggests the rtpengine relay loop is healthy and the packet loss originates elsewhere in the media path. This directly contradicts the hypothesis that rtpengine's processing is the source of the fault. The problem likely lies downstream from rtpengine's application logic, either on the network path to the UPF or within the UPF itself, making UPF a primary alternative suspect.

**Probes executed (3):**
- **Check for non-zero `rtpengine.errors_per_second` to indicate active relay-loop errors.** ✗ CONTRADICTS
    - *Tool:* `print(default_api.get_diagnostic_metrics(at_time_ts = 1778317624.4327137, nfs = ["rtpengine", "upf"]))`
    - *Observation:* [EVIDENCE: get_diagnostic_metrics(at_time_ts=1778317624.4327137, nfs=['rtpengine', 'upf']) -> "rtpengine.errors_per_second_(total) = 0 [gauge, errors_per_second]"]
    - *Comment:* The probe found that rtpengine's internal error rate was zero. This contradicts the expectation that rtpengine's relay loop would be showing errors if it were the source of the packet loss.
- **Confirm the `rtpengine.loss_ratio` is high.** ✓ CONSISTENT
    - *Tool:* `print(default_api.get_dp_quality_gauges(at_time_ts = 1778317624.4327137))`
    - *Observation:* [EVIDENCE: get_dp_quality_gauges(at_time_ts=1778317624.4327137) -> "loss (recent)  : 26.94"]
    - *Comment:* The probe confirmed a very high packet loss ratio reported by rtpengine's RTCP metrics, which aligns with the initial anomaly report.
- **Check if UPF's per-UE downlink packet rate is reduced or zero.** ✗ CONTRADICTS
    - *Tool:* `print(default_api.get_diagnostic_metrics(at_time_ts = 1778317624.4327137, nfs = ["rtpengine", "upf"]))`
    - *Observation:* [EVIDENCE: get_diagnostic_metrics(at_time_ts=1778317624.4327137, nfs=['rtpengine', 'upf']) -> "normalized.upf.gtp_outdatapktn3upf_per_ue = 5.321 [derived, packets_per_second]"]
    - *Comment:* The UPF's downlink packet rate was found to be at a healthy, non-zero level. This contradicts the expectation that packets would be dropped by rtpengine before reaching the UPF, indicating that rtpengine is correctly forwarding media packets.

**Alternative suspects:** ran, upf

### `h2` — ❌ **DISPROVEN**

**Hypothesis:** upf is the source of the data plane fault, causing the collapse in activity reported by the `core.upf.activity_during_calls_collapsed` event and contributing to the packet loss seen by rtpengine.

**Reasoning:** [Multi-shot consensus — both shots returned DISPROVEN.]

Shot 1: The probes reveal a discrepancy in connectivity to the UPF. While the path from rtpengine to UPF shows significant packet loss (27%), the path from SMF to UPF is clean (0% loss). This contradicts the hypothesis that the UPF itself is the source of the fault, and instead points to a network path issue specific to the connection between rtpengine and UPF.

Shot 2: The probe from rtpengine to upf showed ~26% packet loss, consistent with a data plane fault. However, the probe from smf to upf showed 0% packet loss. This combination contradicts the hypothesis that the UPF is the source of the fault. If the UPF were the root cause, both paths to it should be degraded. The evidence points to the fault being on the network path between rtpengine and upf, or an issue with the rtpengine container itself.

**Probes executed (3):**
- **Returns UPF in/out pps, RTPEngine sessions; correlate.** ✓ CONSISTENT
    - *Tool:* `print(default_api.get_dp_quality_gauges(at_time_ts = 1778317624.4327137))`
    - *Observation:* [EVIDENCE: get_dp_quality_gauges(at_time_ts=1778317624.4327137) -> "UPF:\n    in  packets/sec: 11.3\n    out packets/sec: 8.0"]
    - *Comment:* The UPF packet-per-second rates are extremely low for the number of active sessions, which is consistent with the 'activity_during_calls_collapsed' event mentioned in the hypothesis.
- **Probe path from rtpengine to upf's N6 interface IP.** ✓ CONSISTENT
    - *Tool:* `print(default_api.measure_rtt(container = "rtpengine", target_ip = "172.22.0.8"))`
    - *Observation:* [EVIDENCE: measure_rtt('rtpengine', '172.22.0.8') -> "66 packets transmitted, 48 received, 27.2727% packet loss"]
    - *Comment:* This probe showed high packet loss between rtpengine and UPF, which is consistent with the hypothesis of a data plane fault. However, this result is ambiguous by itself.
- **Probe path from smf to upf's N4 interface IP.** ✗ CONTRADICTS
    - *Tool:* `print(default_api.measure_rtt(container = "smf", target_ip = "172.22.0.8"))`
    - *Observation:* [EVIDENCE: measure_rtt('smf', '172.22.0.8') -> "66 packets transmitted, 66 received, 0% packet loss"]
    - *Comment:* This probe showed a healthy connection from the SMF to the UPF. Since the rtpengine->upf path is lossy while the smf->upf path is clean, the fault is not in the UPF container itself but on the network path between rtpengine and UPF. This contradicts the hypothesis.

**Alternative suspects:** the network path between rtpengine and upf, rtpengine

### `h3` — ❌ **DISPROVEN**

**Hypothesis:** The HSS is the source of the IMS signaling disruption, evidenced by anomalous Diameter reply rates from both I-CSCF and S-CSCF.

**Reasoning:** [Multi-shot consensus — both shots returned DISPROVEN.]

Shot 1: The hypothesis is disproven as all probes indicate a healthy and reachable HSS. Both `measure_rtt` probes from I-CSCF and S-CSCF to the HSS (`pyhss`) show zero packet loss and very low latency, contradicting the idea of a network issue. Furthermore, the `get_network_status` probe confirms the `pyhss` container is running. This evidence strongly suggests the HSS is not the root cause of the signaling disruption.

Shot 2: The hypothesis is disproven as all probes contradict the expected behavior. Probes from both I-CSCF and S-CSCF to the HSS (pyhss) show excellent network health with 0% packet loss and low RTT, indicating no transport-layer issues. Furthermore, the HSS container is confirmed to be in a 'running' state. These results refute the claim that the HSS is the source of the signaling disruption.

**Probes executed (3):**
- **from='icscf', to_ip='<pyhss_ip>'** ✗ CONTRADICTS
    - *Tool:* `measure_rtt(container='icscf', target_ip='172.22.0.18')`
    - *Observation:* [EVIDENCE: measure_rtt('icscf', '172.22.0.18') -> "66 packets transmitted, 66 received, 0% packet loss, time 6773ms\nrtt min/avg/max/mdev = 0.043/0.097/0.183/0.028 ms"]
    - *Comment:* The RTT from I-CSCF to pyHSS is extremely low and there is no packet loss. This contradicts the hypothesis that the HSS is experiencing a connectivity issue.
- **from='scscf', to_ip='<pyhss_ip>'** ✗ CONTRADICTS
    - *Tool:* `measure_rtt(container='scscf', target_ip='172.22.0.18')`
    - *Observation:* [EVIDENCE: measure_rtt('scscf', '172.22.0.18') -> "66 packets transmitted, 66 received, 0% packet loss, time 6788ms\nrtt min/avg/max/mdev = 0.039/0.108/0.724/0.080 ms"]
    - *Comment:* Similar to the I-CSCF, the RTT from S-CSCF to pyHSS is very low with no packet loss, further evidence against a network problem related to the HSS.
- **Check the running status of the pyhss container.** ✗ CONTRADICTS
    - *Tool:* `get_network_status()`
    - *Observation:* [EVIDENCE: get_network_status() -> '"pyhss": "running"']
    - *Comment:* The pyHSS container is confirmed to be in a 'running' state, which contradicts the possibility of a container crash or an issue with its startup.

### `h_promoted_ran` — ✅ **NOT_DISPROVEN**

**Hypothesis:** ran is the source of the anomaly named in the alternative_suspects of the original verdict tree.

**Reasoning:** All probes executed returned observations consistent with the hypothesis. A high packet loss ratio was observed at RTPEngine, while RTPEngine's internal error rate was zero, indicating the loss occurred elsewhere on the media path. Furthermore, low packet rates at the UPF are consistent with loss on the N3 path, which includes the RAN. No contradictory evidence was found.

**Probes executed (3):**
- **window_seconds=120 to confirm MOS drop and packet-loss percentage across the same window** ✓ CONSISTENT
    - *Tool:* `default_api.get_dp_quality_gauges(at_time_ts=1778317624.4327137, window_seconds=120)`
    - *Observation:* [EVIDENCE: get_dp_quality_gauges(at_time_ts=1778317624.4327137, window_seconds=120) -> "MOS (recent): 3.62, loss (recent): 26.94"]
    - *Comment:* The packet loss ratio ('loss (recent)') is 26.94, a significant spike from the healthy range of [0, 0.1]. This confirms that receivers are reporting packet loss, which is expected if the RAN is dropping packets.
- **Returns rate-based MOS/loss/jitter alongside RTPEngine errors.** ✓ CONSISTENT
    - *Tool:* `default_api.get_diagnostic_metrics(at_time_ts=1778317624.4327137, nfs=['rtpengine'])`
    - *Observation:* [EVIDENCE: get_diagnostic_metrics(at_time_ts=1778317624.4327137, nfs=['rtpengine']) -> "rtpengine.errors_per_second_(total) = 0 [gauge, errors_per_second]"]
    - *Comment:* The probe for RTPEngine errors per second found a value of 0. This indicates a healthy relay loop inside rtpengine, which strengthens the hypothesis that the problem lies elsewhere in the media path, such as the RAN.
- **Returns rate-windowed UPF in/out pps over the probe's window to check for N3 path degradation.** ✓ CONSISTENT
    - *Tool:* `default_api.get_dp_quality_gauges(at_time_ts=1778317624.4327137, window_seconds=120)`
    - *Observation:* [EVIDENCE: get_dp_quality_gauges(at_time_ts=1778317624.4327137, window_seconds=120) -> "in packets/sec: 11.3, out packets/sec: 8.0"]
    - *Comment:* The UPF packet rates are very low compared to the expected rate for an active voice call (~50 pps). This drop is consistent with packet loss occurring on the N3 path between the UPF and the gNB (RAN).


## Evidence Validation (Phase 5)

**Overall verdict:** clean
**Overall confidence:** high

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 4 | 3/3 | clean | high |
| `InvestigatorAgent_h2` | 8 | 3/3 | clean | high |
| `InvestigatorAgent_h3` | 8 | 3/3 | clean | high |
| `InvestigatorAgent_h_promoted_ran` | 2 | 3/3 | clean | high |


## Ground Truth

**Failure domain:** ims_media  
**Protocol impact:** RTP  
**Affected components:** rtpengine  
**Severity:** degraded

## Agent Diagnosis

**Model:** v7-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 555.7s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: The root cause of severe media plane packet loss has been isolated to the Radio Access Network (RAN).
> - **timeline**:
>     1. Anomaly detected: 'derived.rtpengine_loss_ratio' shows a massive spike, indicating severe media plane packet loss.
>     2. Event fired: 'core.upf.activity_during_calls_collapsed', indicating a sharp drop in expected data plane traffic.
> - **root_cause**: The gNB component of the RAN is dropping a significant percentage of downlink media packets on the N3 path from the UPF. This is the direct cause of the high packet loss ratio (~27%) reported by rtpengine and the resulting degradation of voice call quality. (primary_suspect_nf: `nr_gnb`)
> - **affected_components**:
>     - `nr_gnb`: Root Cause
>     - `rtpengine`: Symptomatic
>     - `upf`: Symptomatic
> - **recommendation**: Investigate the gNB (RAN) for the source of packet drops on the N3 interface. Check gNB logs and internal counters for errors, resource exhaustion, or poor radio frequency (RF) conditions for affected UEs.
> - **confidence**: medium
> - **verdict_kind**: confirmed
> - **explanation**: The investigation systematically ruled out other components in the media path. The `rtpengine` was disproven as a cause because its internal error counters were zero, indicating a healthy relay loop. The `upf` was disproven because connectivity probes to it from the control plane (SMF) were healthy, isolating the packet loss to the rtpengine-to-upf path. A follow-up investigation into the RAN, a component on that path, found all evidence to be consistent with the hypothesis that the RAN is the source of the packet loss. Confidence is 'medium' as this conclusion was reached via a single round of re-investigation on a promoted suspect rather than surviving the initial three-hypothesis fan-out.

### Scoring Breakdown

**Overall score: 36%**

**Scorer assessment:** The agent correctly identified the symptoms (packet loss, degradation) but completely misidentified the root cause and the primary affected component, blaming the RAN instead of RTPEngine. Its intermediate layer analysis was more accurate than its final conclusion.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | No | The simulated failure was 30% packet loss on RTPEngine. The agent incorrectly identified the gNB component of the RAN as the root cause, explicitly stating that rtpengine was disproven. |
| Component overlap | 30% | The actual primary affected component is 'rtpengine'. The agent listed 'rtpengine' in 'affected_components' but labeled it 'Symptomatic', while incorrectly labeling 'nr_gnb' as 'Root Cause'. This indicates partial identification but an incorrect causal role, warranting a partial score. |
| Severity correct | Yes | The simulated failure involved '30% packet loss' and 'degrading voice quality'. The agent correctly diagnosed 'severe media plane packet loss' and 'degradation of voice call quality', accurately reflecting the severity as a degradation rather than a complete outage. |
| Fault type identified | Yes | The simulated failure was 'packet loss'. The agent correctly identified 'packet loss' as the observable fault type, mentioning 'dropping a significant percentage of downlink media packets' and 'high packet loss ratio'. |
| Layer accuracy | Yes | The simulated failure component 'rtpengine' belongs to the 'ims' layer. The 'AGENT NETWORK ANALYSIS' correctly marked the 'ims' layer as 'red' due to 'derived.rtpengine_loss_ratio'. It also correctly marked the 'ran' layer as 'green', which is accurate given the actual failure was not in RAN, despite the agent's final diagnosis incorrectly pointing to RAN. The layer status assessment itself is accurate for the observed symptoms and non-symptoms. |
| Confidence calibrated | No | The agent's diagnosis of the root cause ('nr_gnb') is incorrect, and it misidentifies the role of the actual affected component ('rtpengine'). A 'medium' confidence for a fundamentally incorrect diagnosis is not well-calibrated. |

**Ranking:** The agent provided a single root cause in its final diagnosis, so no ranking is applicable.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 718,929 |
| Output tokens | 14,107 |
| Thinking tokens | 47,809 |
| **Total tokens** | **780,845** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| SymptomClassifier | 0 | 0 | 0 |
| PathResolver | 0 | 0 | 0 |
| PathWalkInvestigator | 0 | 0 | 0 |
| EventAggregator | 0 | 0 | 0 |
| CorrelationAnalyzer | 0 | 0 | 0 |
| NetworkAnalystAgent | 100,605 | 7 | 4 |
| Phase 3 NetworkAnalyst__guardrail | 0 | 0 | 0 |
| NetworkAnalystAgent | 56,422 | 3 | 4 |
| Phase 3 NetworkAnalyst__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 36,091 | 1 | 2 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 52,849 | 2 | 3 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| InvestigatorAgent_h1 | 49,077 | 2 | 3 |
| InvestigatorAgent_h1 | 46,051 | 2 | 3 |
| InvestigatorAgent_h1__reconciliation | 0 | 0 | 0 |
| InvestigatorAgent_h2 | 76,872 | 4 | 5 |
| InvestigatorAgent_h2 | 76,794 | 4 | 5 |
| InvestigatorAgent_h2__reconciliation | 0 | 0 | 0 |
| InvestigatorAgent_h3 | 77,132 | 4 | 5 |
| InvestigatorAgent_h3 | 77,133 | 4 | 5 |
| InvestigatorAgent_h3__reconciliation | 0 | 0 | 0 |
| Phase5FanOutAudit | 0 | 0 | 0 |
| Phase6.5CandidatePool | 0 | 0 | 0 |
| InstructionGeneratorAgent | 30,032 | 1 | 2 |
| Phase 6.5 Reinvestigation IG__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 34,406 | 1 | 2 |
| Phase 6.5 Reinvestigation IG__guardrail | 0 | 0 | 0 |
| InvestigatorAgent_h_promoted_ran | 45,429 | 2 | 3 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 11,050 | 0 | 1 |
| Phase 7 Synthesis__guardrail | 0 | 0 | 0 |
| SynthesisAgent | 10,902 | 0 | 1 |
| Phase 7 Synthesis__guardrail | 0 | 0 | 0 |
| Phase 7 Synthesis__guardrail | 0 | 0 | 0 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 700.6s
