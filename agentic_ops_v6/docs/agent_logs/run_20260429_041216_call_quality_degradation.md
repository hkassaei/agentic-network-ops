# Episode Report: Call Quality Degradation

**Agent:** v6  
**Episode ID:** ep_20260429_040624_call_quality_degradation  
**Date:** 2026-04-29T04:06:25.690728+00:00  
**Duration:** 349.8s  

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

**ANOMALY DETECTED.** Overall anomaly score: 48.92 (per-bucket threshold: 28.18, context bucket (1, 1), trained on 323 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following metrics deviate from their learned-healthy baseline. Treat each as a semantic observation (meaning + numbers), not a number alone — the KB's interpretation is the authoritative reading.

- **`derived.rtpengine_loss_ratio`** (RTPEngine RTCP-reported per-RR average packet loss) — current **24.45 packets_per_rr** vs learned baseline **0.00 packets_per_rr** (MEDIUM, spike)
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

- **`normalized.icscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at I-CSCF) — current **0.03 requests_per_second** vs learned baseline **0.06 requests_per_second** (MEDIUM, drop)
    - **What it measures:** Health of the P-CSCF → I-CSCF forwarding path (Mw interface). When
this drops to zero while P-CSCF REGISTER rate is still non-zero,
it's the SIGNATURE of an IMS partition between P-CSCF and I-CSCF.
    - **Drop means:** Either UEs not registering at all, or P-CSCF isolated from I-CSCF.
    - **Healthy typical range:** 0–0.5 requests_per_second
    - **Healthy invariant:** Per-UE rate. Should closely track ims.pcscf.rcv_requests_register_per_ue.

- **`normalized.pcscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at P-CSCF) — current **0.03 requests_per_second** vs learned baseline **0.06 requests_per_second** (MEDIUM, drop)
    - **What it measures:** How actively UEs are refreshing their IMS registrations with the
P-CSCF. REGISTERs arrive periodically (re-registration timer) plus
at attach. Sustained zero means UEs cannot reach P-CSCF OR the
UE-to-network SIP path is broken.
    - **Drop means:** No REGISTERs flowing. Unusual unless UEs are all deregistered.
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

- **`normalized.scscf.cdp_replies_per_ue`** (S-CSCF CDP Diameter replies per UE) — current **0.03 replies_per_second_per_ue** vs learned baseline **0.06 replies_per_second_per_ue** (MEDIUM, drop)
    - **What it measures:** Active S-CSCF Diameter traffic with HSS. Near-zero when registrations idle OR HSS partition.
    - **Drop means:** No active S-CSCF Diameter exchanges (idle or partitioned).
    - **Healthy typical range:** 0–1 replies_per_second_per_ue
    - **Healthy invariant:** Per-UE rate; varies with registration/auth load.

- **`normalized.scscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at S-CSCF) — current **0.03 requests_per_second** vs learned baseline **0.06 requests_per_second** (MEDIUM, drop)
    - **What it measures:** Health of the I-CSCF → S-CSCF forwarding path. Drop to zero while
I-CSCF is receiving REGISTERs = S-CSCF-side issue (crashed, or
I-CSCF → S-CSCF path broken).
    - **Drop means:** S-CSCF isolated or not running.
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

- **`normalized.upf.gtp_indatapktn3upf_per_ue`** (GTP-U uplink rate per UE (N3)) — current **8.06 packets_per_second** vs learned baseline **1.45 packets_per_second** (MEDIUM, spike)
    - **What it measures:** Health of the uplink user-plane path gNB → UPF. Drops to near-zero
during RAN or N3 outage; stays nonzero during active calls or data
sessions. Decoupled from SIP signaling (signals data plane, not
control plane).
    - **Spike means:** Either UEs not generating uplink traffic (no calls/data) or N3 path is degraded.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE — constant regardless of UE pool size. Rises during active VoNR calls (~100 pps for G.711 voice) and data transfer.

- **`normalized.upf.gtp_outdatapktn3upf_per_ue`** (GTP-U downlink rate per UE (N3)) — current **5.70 packets_per_second** vs learned baseline **1.45 packets_per_second** (MEDIUM, spike)
    - **What it measures:** Health of the downlink user-plane path UPF → gNB. Typically mirrors
uplink rate during calls/data; asymmetry indicates directional
faults (e.g., UPF receiving from internet but not forwarding).
    - **Spike means:** Downlink data plane degraded — UPF not forwarding to gNB.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE — constant regardless of UE pool size. Roughly symmetric with uplink during healthy calls.


## Event Aggregation (Phase 1)

**1 events fired during the observation window:**

- `core.upf.activity_during_calls_collapsed` (source: `core.upf.activity_during_calls`, nf: `upf`, t=1777435704.8)  [current_value=0.0427705]

## Correlation Analysis (Phase 2)

1 events fired but no composite hypothesis emerged. The events may be from independent faults or lack registered correlation hints in the KB.

## Network Analysis (Phase 3)

**Summary:** The root cause of the anomaly is severe packet loss in the data plane, originating from the UPF, which is causing VoNR call quality degradation and secondary IMS signaling failures.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | All underlying infrastructure components (containers, links) are reported as active and healthy. |
| **ran** | 🟢 GREEN | No evidence of a RAN-layer fault. All components appear to be functioning correctly. |
| **core** | 🔴 RED | The UPF is the primary suspect. It is dropping packets on the N3 user plane, leading to data plane failure that cascades to the IMS layer. |
| **ims** | 🟡 YELLOW | The IMS layer is showing symptoms of degradation, including high media packet loss and reduced registration rates. These are likely consequences of the upstream data plane failure in the Core layer, rather than an independent IMS fault. |

**CORE evidence:**
- core.upf.activity_during_calls_collapsed
- normalized.upf.gtp_outdatapktn3upf_per_ue
- UPF egress packet rate is significantly lower than its ingress rate.

**IMS evidence:**
- derived.rtpengine_loss_ratio
- normalized.pcscf.core:rcv_requests_register_per_ue
- normalized.icscf.core:rcv_requests_register_per_ue
- normalized.scscf.core:rcv_requests_register_per_ue

**Ranked hypotheses:**

- **`h1`** (fit=0.90, nf=upf, specificity=specific):
    - **Statement:** The UPF is experiencing internal packet loss on the downlink path (N3 interface), causing significant media degradation for VoNR calls. This is evidenced by a mismatch in its own packet counters (ingress vs. egress) and corroborated by high packet loss reports from the downstream RTPEngine.
    - **Supporting events:** `core.upf.activity_during_calls_collapsed`
    - **Falsification probes:**
        - Check for kernel-level drop counters or errors on the UPF container's network interfaces (e.g., `netstat -s`, `ethtool -S`). If these are zero, the loss is likely inside the UPF application itself.
        - Use `tcpdump` on the UPF's N3 and N6 interfaces to directly observe if packets arriving on one interface are failing to be forwarded out the other.
        - Restart the UPF container. If the packet loss stops, it points to a transient internal state issue within the UPF.
- **`h2`** (fit=0.50, nf=rtpengine, specificity=moderate):
    - **Statement:** The RTPEngine is independently dropping media packets in its userspace process, separate from any UPF issue, leading to poor VoNR call quality.
    - **Falsification probes:**
        - Check the rtpengine logs for errors related to packet handling, buffer overruns, or invalid packets.
        - Take a packet capture on the rtpengine container's interfaces. If packets from the UPF are arriving intact but not being forwarded correctly, the fault is in RTPEngine. If the packets are not arriving, the fault is upstream.
- **`h3`** (fit=0.30, nf=pcscf, specificity=moderate):
    - **Statement:** A control plane fault in the IMS core is causing SIP registration failures, independent of the data plane issues. This is evidenced by consistently low REGISTER rates across all CSCF components.
    - **Falsification probes:**
        - Resolve the data plane packet loss issue (Hypothesis 1). If the registration rates return to normal, this hypothesis is falsified as the issues were consequential, not causal.
        - Check the logs on P-CSCF, I-CSCF, and S-CSCF for specific SIP error responses (e.g., 4xx, 5xx) to REGISTER requests that could indicate a processing failure.


## Falsification Plans (Phase 4)

**3 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `upf`)

**Hypothesis:** The UPF is experiencing internal packet loss on the downlink path (N3 interface), causing significant media degradation for VoNR calls. This is evidenced by a mismatch in its own packet counters (ingress vs. egress) and corroborated by high packet loss reports from the downstream RTPEngine.

**Probes (3):**
1. **`get_dp_quality_gauges`** — window_seconds=60
    - *Expected if hypothesis holds:* The UPF's reported 'downlink_loss' gauge is high, confirming it is the source of loss.
    - *Falsifying observation:* The UPF's reported 'downlink_loss' is near zero. This would indicate the loss is occurring downstream from the UPF, or is not being detected by the UPF itself.
2. **`get_nf_metrics`** — Look for UPF's N3/N6 interface counters.
    - *Expected if hypothesis holds:* A significant mismatch exists between packets received on the ingress interface (e.g., N6) and packets transmitted on the egress interface (e.g., N3 for downlink).
    - *Falsifying observation:* Packet counters for ingress and egress are closely matched, indicating no significant internal packet loss within the UPF application.
3. **`measure_rtt`** — from='smf', to_ip='<gnb_ip>'
    - *Expected if hypothesis holds:* RTT is clean and packet loss is low, as the hypothesis posits an internal UPF application issue, not a network-level problem on the path.
    - *Falsifying observation:* High packet loss is observed on the path between the core and the RAN. This would suggest a network-level issue rather than a fault confined to the UPF.

*Notes:* This plan focuses on verifying the packet loss is located specifically within the UPF. It uses data plane quality metrics as the primary evidence and uses a network RTT check as a triangulation probe to distinguish between an application fault and a network path fault.

### Plan for `h2` (target: `rtpengine`)

**Hypothesis:** The RTPEngine is independently dropping media packets in its userspace process, separate from any UPF issue, leading to poor VoNR call quality.

**Probes (3):**
1. **`get_dp_quality_gauges`** — window_seconds=60
    - *Expected if hypothesis holds:* RTPEngine's 'forward_loss' is high, while the upstream UPF's 'downlink_loss' is low. This pattern would isolate the loss to the RTPEngine.
    - *Falsifying observation:* The UPF's 'downlink_loss' is high, indicating that the packets are already lost before they even arrive at the RTPEngine. This would falsify the hypothesis that RTPEngine is the *independent* source of the problem.
2. **`get_nf_metrics`** — Look for RTPEngine's internal drop or error counters.
    - *Expected if hypothesis holds:* Internal RTPEngine metrics for dropped packets or processing errors are elevated.
    - *Falsifying observation:* All internal error and drop counters for RTPEngine are zero, suggesting it is not encountering any issues processing the media stream.
3. **`measure_rtt`** — from='upf', to_ip='<rtpengine_ip>'
    - *Expected if hypothesis holds:* RTT is clean and there is no packet loss, confirming the network path between the UPF and RTPEngine is healthy.
    - *Falsifying observation:* High packet loss is observed on the direct path between the UPF and RTPEngine, pointing to a network link issue rather than an application-level fault in RTPEngine.

*Notes:* This plan's primary goal is to distinguish between a fault in the UPF (h1) and a fault in the RTPEngine (h2). The get_dp_quality_gauges probe is the key discriminator, as it compares loss metrics from both components.

### Plan for `h3` (target: `pcscf`)

**Hypothesis:** A control plane fault in the IMS core is causing SIP registration failures, independent of the data plane issues. This is evidenced by consistently low REGISTER rates across all CSCF components.

**Probes (3):**
1. **`get_nf_metrics`** — Look for SIP request counts and error ratios on pcscf, icscf, and scscf.
    - *Expected if hypothesis holds:* Metrics show a high rate of SIP errors (e.g., 4xx, 5xx responses) for REGISTER requests, indicating the IMS core is actively failing to process them.
    - *Falsifying observation:* Metrics show low incoming REGISTER request volume but also a low error rate. This would imply the requests are not reaching the IMS core in the first place, making the registration issue a symptom of an upstream problem (like the data plane loss), not an independent IMS fault.
2. **`measure_rtt`** — from='pcscf', to_ip='<icscf_ip>'
    - *Expected if hypothesis holds:* The RTT is clean and there is no packet loss, as the hypothesized fault is internal to the IMS components, not the network between them.
    - *Falsifying observation:* High packet loss or latency is observed between CSCF components, which would indicate a network-level partition within the IMS core.
3. **`check_process_listeners`** — container='pcscf'
    - *Expected if hypothesis holds:* The P-CSCF process is actively listening on its standard SIP port (e.g., 5060), ready to receive traffic.
    - *Falsifying observation:* The P-CSCF process is not listening on its SIP port, indicating a crash or misconfiguration that is preventing it from serving any traffic. This is a different, more fundamental failure than a control plane processing error.

*Notes:* This plan tests the 'independent fault' aspect of the hypothesis. The primary probe aims to determine if the IMS core is failing on its own, or if it is simply not receiving traffic due to the data plane issues identified in h1.


## Parallel Investigators (Phase 5)

**3 sub-Investigator verdict(s):** **1 NOT_DISPROVEN**, **2 DISPROVEN**

### `h1` — ✅ **NOT_DISPROVEN**

**Hypothesis:** The UPF is experiencing internal packet loss on the downlink path (N3 interface), causing significant media degradation for VoNR calls. This is evidenced by a mismatch in its own packet counters (ingress vs. egress) and corroborated by high packet loss reports from the downstream RTPEngine.

**Reasoning:** All probes executed were consistent with the hypothesis. Probes confirmed that the UPF is dropping packets, as evidenced by both real-time gauges and cumulative counters. A network path check between the core and RAN was clean, which isolates the fault to the UPF application itself, as the hypothesis suggests.

**Probes executed (3):**
- **Check the UPF's reported 'downlink_loss' gauge.** ✓ CONSISTENT
    - *Tool:* `default_api.get_dp_quality_gauges(window_seconds=60)`
    - *Observation:* [EVIDENCE: get_dp_quality_gauges("window_seconds=60") -> "UPF:\n    in  packets/sec: 10.5\n    out packets/sec: 7.0"]
    - *Comment:* The live data plane gauges show a significant packet loss rate (~33%) at the UPF, strongly supporting the hypothesis that the UPF is the source of the loss.
- **Look for UPF's N3/N6 interface counters.** ✓ CONSISTENT
    - *Tool:* `default_api.get_nf_metrics()`
    - *Observation:* [EVIDENCE: get_nf_metrics() -> "UPF ... fivegs_ep_n3_gtp_indatapktn3upf = 34144.0 ... fivegs_ep_n3_gtp_outdatapktn3upf = 29732.0"]
    - *Comment:* The cumulative metrics for the N3 interface show a large and significant mismatch between ingress and egress packets, corroborating the live packet loss observed in the first probe. While these are lifetime counters, the delta is large enough to be meaningful alongside the gauge data.
- **Check RTT and packet loss on the path from the core to the RAN.** ✓ CONSISTENT
    - *Tool:* `default_api.measure_rtt(container="smf", target_ip="172.22.0.23")`
    - *Observation:* [EVIDENCE: measure_rtt("smf", "172.22.0.23") -> "3 packets transmitted, 3 received, 0% packet loss, time 2064ms"]
    - *Comment:* The RTT measurement from the SMF to the gNB shows 0% packet loss and very low latency. This confirms the network path itself is healthy, ruling out a network-level issue and strengthening the hypothesis that the packet loss is internal to the UPF application.

### `h2` — ❌ **DISPROVEN**

**Hypothesis:** The RTPEngine is independently dropping media packets in its userspace process, separate from any UPF issue, leading to poor VoNR call quality.

**Reasoning:** All three probes executed contradict the hypothesis. The quality gauges show that packet loss originates upstream at the UPF, not the RTPEngine. RTPEngine's internal metrics show zero errors or dropped packets, confirming it is not the source of the loss. Finally, a direct network measurement between the UPF and RTPEngine revealed high packet loss on the link, proving the packets are lost before they even reach the RTPEngine's userspace process.

**Probes executed (3):**
- **RTPEngine's 'forward_loss' is high, while the upstream UPF's 'downlink_loss' is low. This pattern would isolate the loss to the RTPEngine.** ✗ CONTRADICTS
    - *Tool:* `print(default_api.get_dp_quality_gauges(window_seconds=60))`
    - *Observation:* [EVIDENCE: get_dp_quality_gauges(window_seconds=60) -> "RTPEngine:\n    loss (recent)  : 30.28\n  UPF:\n    in  packets/sec: 10.5\n    out packets/sec: 6.9"]
    - *Comment:* The packet loss originates at the UPF. The UPF's outbound packet rate (6.9 pps) is significantly lower than its inbound rate (10.5 pps), a drop of over 34%. This loss is seen by the downstream RTPEngine (30.28% loss), indicating the packets are already gone before they arrive. This falsifies the idea that RTPEngine is the independent source of the loss.
- **Look for RTPEngine's internal drop or error counters.** ✗ CONTRADICTS
    - *Tool:* `print(default_api.get_nf_metrics())`
    - *Observation:* [EVIDENCE: get_nf_metrics() -> "RTPENGINE... errors_per_second_(total) = 0.0... packets_lost = 0.0... total_relayed_packet_errors = 0.0"]
    - *Comment:* Internal metrics for RTPEngine show no evidence of packet drops or processing errors. Counters like 'packets_lost' and 'total_relayed_packet_errors' are all zero. This contradicts the hypothesis that packets are being dropped within the RTPEngine userspace process.
- **from='upf', to_ip='<rtpengine_ip>'** ✗ CONTRADICTS
    - *Tool:* `print(default_api.measure_rtt(container = "upf", target_ip = "172.22.0.16"))`
    - *Observation:* [EVIDENCE: measure_rtt(container='upf', target_ip='172.22.0.16') -> "3 packets transmitted, 1 received, 66.6667% packet loss"]
    - *Comment:* The probe found high packet loss (66.7%) on the direct network path between the UPF and RTPEngine containers. This falsifies the hypothesis that the RTPEngine's *userspace process* is at fault, as the packets are being lost on the network link before they can even be processed by the application.

**Alternative suspects:** upf

### `h3` — ❌ **DISPROVEN**

**Hypothesis:** A control plane fault in the IMS core is causing SIP registration failures, independent of the data plane issues. This is evidenced by consistently low REGISTER rates across all CSCF components.

**Reasoning:** The hypothesis is disproven because key evidence directly contradicts the claim of a control plane fault within the IMS core. Probes show that the CSCF components are not generating SIP errors for REGISTER requests; on the contrary, registrations that are received are processed successfully. The issue is not the IMS core failing to process requests, but rather that requests are not reaching it, pointing to an upstream issue likely related to the data plane problems identified in other hypotheses.

**Probes executed (3):**
- **Look for SIP request counts and error ratios on pcscf, icscf, and scscf.** ✗ CONTRADICTS
    - *Tool:* `default_api.get_nf_metrics()`
    - *Observation:* [EVIDENCE: get_nf_metrics() -> "PCSCF: ... sl:4xx_replies = 0.0, sl:5xx_replies = 0.0 ... SCSCF: ... ims_registrar_scscf:rejected_regs = 0.0"]
    - *Comment:* The metrics show zero SIP 4xx/5xx errors and zero rejected registrations across the CSCF chain. This directly contradicts the expectation that an IMS control plane fault would be generating such errors. The IMS core is correctly processing the registrations it receives.
- **Check if the P-CSCF process is listening on its standard SIP port.** ✓ CONSISTENT
    - *Tool:* `default_api.check_process_listeners(container='pcscf')`
    - *Observation:* [EVIDENCE: check_process_listeners("pcscf") -> "udp   UNCONN 0      0        172.22.0.21:5060       0.0.0.0:*    users:((\"kamailio\"...)) ... tcp   LISTEN 0      1024     172.22.0.21:5060       0.0.0.0:*    users:((\"kamailio\"...))"]
    - *Comment:* The P-CSCF's Kamailio process is actively listening on its SIP port (5060) for both UDP and TCP. This rules out a simple process crash or misconfiguration preventing it from receiving traffic.
- **Measure RTT from P-CSCF to I-CSCF to check for network partitions within the IMS core.** ✓ CONSISTENT
    - *Tool:* `default_api.measure_rtt(container='pcscf', target_ip='172.22.0.19')`
    - *Observation:* [EVIDENCE: measure_rtt("pcscf", "172.22.0.19") -> "3 packets transmitted, 3 received, 0% packet loss, time 2055ms"]
    - *Comment:* The RTT between P-CSCF and I-CSCF is healthy with 0% packet loss. This confirms there is no network-level partition between the IMS components, as expected by the hypothesis which posits a fault within the components themselves.

**Alternative suspects:** upf


## Evidence Validation (Phase 6)

**Overall verdict:** clean
**Overall confidence:** high

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 4 | 3/3 | clean | high |
| `InvestigatorAgent_h2` | 4 | 3/3 | clean | high |
| `InvestigatorAgent_h3` | 4 | 3/3 | clean | high |


## Ground Truth

**Failure domain:** ims_media  
**Protocol impact:** RTP  
**Affected components:** rtpengine  
**Severity:** degraded

## Agent Diagnosis

**Model:** v6-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 215.9s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: The root cause is severe data plane packet loss originating within the User Plane Function (UPF), which is degrading VoNR call quality and causing secondary IMS registration failures.
> - **timeline**:
>     1. The UPF begins dropping a significant percentage (~33%) of downlink packets on the N3 user plane interface.
>     2. This packet loss immediately degrades media quality for VoNR calls, observed as high loss rates by the downstream RTPEngine.
>     3. The data plane failure prevents some control plane messages (like SIP REGISTER) from reaching the IMS core, resulting in a drop in successful UE registrations.
> - **root_cause**: The UPF is experiencing an internal fault causing it to drop user plane packets. The `primary_suspect_nf` is **upf**.
> - **affected_components**:
>     - `upf`: Root Cause
>     - `rtpengine`: Symptomatic
>     - `pcscf`, `icscf`, `scscf`: Symptomatic
> - **recommendation**: The operator should verify the source of the packet loss within the UPF. Check for kernel-level packet drop counters (e.g., via `netstat -s` or `ethtool -S`) on the UPF's network interfaces. If kernel counters are zero, it further isolates the fault to the UPF application itself. Live packet captures on the UPF's N3 and N6 interfaces can also be used to directly observe the loss.
> - **confidence**: high
> - **explanation**: The investigation confirmed with high confidence that the UPF is the source of the anomaly (Hypothesis `h1`). Probes revealed a significant mismatch between the UPF's ingress and egress packet counters, with live gauges showing a ~33% packet drop rate. Alternative hypotheses were disproven: the RTPEngine is merely a victim of this upstream loss, not the source (Hypothesis `h2`), and the IMS core is processing all received SIP requests correctly, proving the registration issues are a consequence of the data plane failure (Hypothesis `h3`). The data plane collapse in the UPF is the root cause for both the poor media quality and the secondary control plane symptoms. All evidence cited by the investigation was successfully validated.

### Scoring Breakdown

**Overall score: 31%**

**Scorer assessment:** The agent correctly identified the type and severity of the fault (packet loss, degradation) but completely missed the root cause component and its associated layer, leading to a poorly calibrated high confidence score.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | No | The simulated failure was 30% packet loss on RTPEngine. The agent incorrectly identified the UPF as the root cause, stating it was dropping user plane packets. The actual failure was within RTPEngine itself, after it received packets. |
| Component overlap | 30% | The primary affected component was 'rtpengine'. The agent listed 'rtpengine' in 'affected_components' but labeled it 'Symptomatic', while incorrectly labeling 'upf' as 'Root Cause'. This indicates it identified the component but mis-ranked its causal role. |
| Severity correct | Yes | The simulated failure involved '30% packet loss' and 'degrading voice quality'. The agent correctly identified 'severe data plane packet loss' and 'degrading VoNR call quality', which aligns with a degradation rather than a complete outage. |
| Fault type identified | Yes | The simulated failure was 'packet loss'. The agent correctly identified 'packet loss' as the fault type. |
| Layer accuracy | No | The ground truth states 'rtpengine' belongs to the 'ims' layer. The agent's network analysis incorrectly attributed the root cause to the 'core' layer (UPF) and marked it red, while marking the 'ims' layer yellow as a consequence, not the source of the problem. |
| Confidence calibrated | No | The agent stated 'high' confidence, but its diagnosis for the root cause, primary affected component, and layer attribution was incorrect. High confidence for an incorrect diagnosis indicates poor calibration. |

**Ranking:** The agent provided a single root cause (UPF), which was incorrect. The correct root cause (RTPEngine) was not identified as the primary root cause.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 250,693 |
| Output tokens | 5,860 |
| Thinking tokens | 16,362 |
| **Total tokens** | **272,915** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| EventAggregator | 0 | 0 | 0 |
| CorrelationAnalyzer | 0 | 0 | 0 |
| NetworkAnalystAgent | 56,296 | 6 | 4 |
| InstructionGeneratorAgent | 21,856 | 1 | 2 |
| InvestigatorAgent_h1 | 61,108 | 4 | 5 |
| InvestigatorAgent_h2 | 59,632 | 4 | 5 |
| InvestigatorAgent_h3 | 67,662 | 4 | 5 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 6,361 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 349.8s
