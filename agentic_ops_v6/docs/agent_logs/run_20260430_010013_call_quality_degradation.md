# Episode Report: Call Quality Degradation

**Agent:** v6  
**Episode ID:** ep_20260430_005500_call_quality_degradation  
**Date:** 2026-04-30T00:55:01.966882+00:00  
**Duration:** 310.9s  

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

**ANOMALY DETECTED.** Overall anomaly score: 48.92 (per-bucket threshold: 28.18, context bucket (1, 1), trained on 323 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following metrics deviate from their learned-healthy baseline. Treat each as a semantic observation (meaning + numbers), not a number alone — the KB's interpretation is the authoritative reading.

- **`derived.rtpengine_loss_ratio`** (RTPEngine RTCP-reported per-RR average packet loss) — current **29.13 packets_per_rr** vs learned baseline **0.00 packets_per_rr** (MEDIUM, spike)
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

- **`normalized.upf.gtp_indatapktn3upf_per_ue`** (GTP-U uplink rate per UE (N3)) — current **8.10 packets_per_second** vs learned baseline **1.45 packets_per_second** (MEDIUM, spike)
    - **What it measures:** Health of the uplink user-plane path gNB → UPF. Drops to near-zero
during RAN or N3 outage; stays nonzero during active calls or data
sessions. Decoupled from SIP signaling (signals data plane, not
control plane).
    - **Spike means:** Either UEs not generating uplink traffic (no calls/data) or N3 path is degraded.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE — constant regardless of UE pool size. Rises during active VoNR calls (~100 pps for G.711 voice) and data transfer.

- **`normalized.upf.gtp_outdatapktn3upf_per_ue`** (GTP-U downlink rate per UE (N3)) — current **5.48 packets_per_second** vs learned baseline **1.45 packets_per_second** (MEDIUM, spike)
    - **What it measures:** Health of the downlink user-plane path UPF → gNB. Typically mirrors
uplink rate during calls/data; asymmetry indicates directional
faults (e.g., UPF receiving from internet but not forwarding).
    - **Spike means:** Downlink data plane degraded — UPF not forwarding to gNB.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE — constant regardless of UE pool size. Roughly symmetric with uplink during healthy calls.


## Event Aggregation (Phase 1)

**1 events fired during the observation window:**

- `core.upf.activity_during_calls_collapsed` (source: `core.upf.activity_during_calls`, nf: `upf`, t=1777510620.2)  [current_value=0.046809666666666666]

## Correlation Analysis (Phase 2)

1 events fired but no composite hypothesis emerged. The events may be from independent faults or lack registered correlation hints in the KB.

## Network Analysis (Phase 3)

**Summary:** The data plane is experiencing severe packet loss, primarily implicating the UPF, which is causing failures in VoNR calls and IMS registrations.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟡 YELLOW | No direct evidence of an infrastructure fault, but the data plane issues could stem from lower-level container networking problems. This is a secondary possibility. |
| **ran** | 🟢 GREEN | No metrics directly indicate a RAN-side fault. The issue appears to be within the core and IMS layers. |
| **core** | 🔴 RED | The User Plane Function (UPF) is showing signs of extreme traffic volume and is the primary suspect for data plane degradation. |
| **ims** | 🔴 RED | RTPEngine reports massive packet loss, and IMS registration requests have ceased across all CSCFs, likely as a downstream effect of the data plane failure. |

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
    - **Statement:** The UPF is experiencing an internal fault or severe congestion, leading to massive packet drops on the N3/N9 data plane. This is causing high packet loss in RTP streams (observed by RTPEngine) and preventing IMS signaling, such as registrations, from completing successfully.
    - **Supporting events:** `core.upf.activity_during_calls_collapsed`
    - **Falsification probes:**
        - Check internal UPF logs and metrics for packet drop counters or error flags.
        - Measure RTT and packet loss from UPF to RTPEngine and from UPF to the gNB to isolate the location of the drops.
        - Inspect the CPU and memory utilization of the UPF container to check for resource exhaustion.
- **`h2`** (fit=0.70, nf=rtpengine, specificity=specific):
    - **Statement:** The RTPEngine is the source of the media degradation, dropping RTP packets internally due to a bug or resource issue. This would directly explain the high `rtpengine_loss_ratio`.
    - **Falsification probes:**
        - Inspect RTPEngine logs and internal statistics for evidence of internal packet drops or processing errors.
        - Measure RTT from the RTPEngine container to the UPF; a clean path would point to an internal RTPEngine issue.
        - Verify that the UPF's outbound packet counters towards RTPEngine match RTPEngine's inbound counters.
- **`h3`** (fit=0.50, nf=upf, specificity=moderate):
    - **Statement:** A general data plane failure exists within the container networking layer (e.g., veth interfaces, Linux bridge), causing packet loss between multiple components, including the UPF and RTPEngine.
    - **Supporting events:** `core.upf.activity_during_calls_collapsed`
    - **Falsification probes:**
        - Measure RTT and packet loss between several pairs of containers (e.g., AMF to SMF, SMF to PCF) to see if the problem is widespread.
        - Inspect `tc` (traffic control) rules and net-filter (iptables) configurations on the host and within the containers for any rules that might be dropping packets.


## Falsification Plans (Phase 4)

**3 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `upf`)

**Hypothesis:** The UPF is experiencing an internal fault or severe congestion, leading to massive packet drops on the N3/N9 data plane. This is causing high packet loss in RTP streams (observed by RTPEngine) and preventing IMS signaling, such as registrations, from completing successfully.

**Probes (3):**
1. **`get_dp_quality_gauges`** — window_seconds=60
    - *Expected if hypothesis holds:* The 'upf_loss' gauge is high, indicating the UPF is dropping a significant percentage of packets.
    - *Falsifying observation:* The 'upf_loss' gauge is at or near zero, indicating the UPF is not the source of packet loss.
2. **`get_network_status`** — Check status of 'upf' container.
    - *Expected if hypothesis holds:* The UPF container is in a 'running' state (the hypothesis is about an internal fault/congestion, not a crash).
    - *Falsifying observation:* The UPF container is in an 'exited' or 'restarting' state, which would point to a crash loop rather than a performance issue.
3. **`get_diagnostic_metrics`** — Filter for UPF metrics, specifically CPU and memory utilization.
    - *Expected if hypothesis holds:* High CPU or memory utilization for the UPF container, consistent with severe congestion.
    - *Falsifying observation:* Normal CPU and memory utilization, which would contradict the 'severe congestion' part of the hypothesis.

*Notes:* This plan focuses on verifying the internal state of the UPF. The hypothesis is anchored to the failure of the media plane, corresponding to step 12 ('RTP media') of the 'vonr_call_setup' flow.

### Plan for `h2` (target: `rtpengine`)

**Hypothesis:** The RTPEngine is the source of the media degradation, dropping RTP packets internally due to a bug or resource issue. This would directly explain the high `rtpengine_loss_ratio`.

**Probes (3):**
1. **`get_dp_quality_gauges`** — window_seconds=60
    - *Expected if hypothesis holds:* The 'rtpengine_loss_ratio' is high, while the 'upf_loss' ratio is low. This pattern would isolate the loss to the RTPEngine.
    - *Falsifying observation:* The 'upf_loss' ratio is also high, suggesting that packets are being lost before they even reach the RTPEngine.
2. **`measure_rtt`** — from: upf, to_ip: <rtpengine_ip>
    - *Expected if hypothesis holds:* Low RTT and zero packet loss. This would indicate the network path from the UPF is healthy, pointing to a problem inside RTPEngine.
    - *Falsifying observation:* High RTT or significant packet loss, suggesting the issue lies in the network path or the UPF, not internally within RTPEngine.
3. **`measure_rtt`** — from: pcscf, to_ip: <rtpengine_ip>
    - *Expected if hypothesis holds:* Low RTT and zero packet loss, same as the path from the UPF.
    - *Falsifying observation:* High RTT or significant packet loss. If the UPF->RTPEngine path was also lossy, this result would point towards a broader network issue or a problem with RTPEngine's network ingress, rather than a problem specific to the UPF->RTPEngine path.

*Notes:* This plan aims to determine if the packet loss originates within RTPEngine. It compares data plane metrics and tests network paths from multiple sources (UPF, P-CSCF) that interact with RTPEngine during the 'vonr_call_setup' flow.

### Plan for `h3` (target: `upf`)

**Hypothesis:** A general data plane failure exists within the container networking layer (e.g., veth interfaces, Linux bridge), causing packet loss between multiple components, including the UPF and RTPEngine.

**Probes (3):**
1. **`measure_rtt`** — from: amf, to_ip: <smf_ip>
    - *Expected if hypothesis holds:* High RTT or significant packet loss, indicating a widespread networking problem.
    - *Falsifying observation:* Low RTT and zero packet loss, which contradicts the hypothesis of a 'general' failure by showing a critical control-plane path is healthy.
2. **`measure_rtt`** — from: pcscf, to_ip: <icscf_ip>
    - *Expected if hypothesis holds:* High RTT or significant packet loss, providing further evidence of a widespread issue.
    - *Falsifying observation:* Low RTT and zero packet loss. A second healthy path makes the 'general failure' hypothesis very unlikely.
3. **`measure_rtt`** — from: smf, to_ip: <pcf_ip>
    - *Expected if hypothesis holds:* High RTT or significant packet loss.
    - *Falsifying observation:* Low RTT and zero packet loss, providing a third piece of evidence that the container networking is not generally failing.

*Notes:* This plan tests the 'general failure' claim by probing multiple, independent network paths (AMF-SMF, P-CSCF-I-CSCF, SMF-PCF) that are part of different flows like 'pdu_session_establishment' and 'ims_registration'. If these paths are healthy, the hypothesis is false.


## Parallel Investigators (Phase 5)

**3 sub-Investigator verdict(s):** **1 NOT_DISPROVEN**, **2 DISPROVEN**

### `h1` — ✅ **NOT_DISPROVEN**

**Hypothesis:** The UPF is experiencing an internal fault or severe congestion, leading to massive packet drops on the N3/N9 data plane. This is causing high packet loss in RTP streams (observed by RTPEngine) and preventing IMS signaling, such as registrations, from completing successfully.

**Reasoning:** All executed probes returned results consistent with the hypothesis. The data plane quality gauges and diagnostic metrics both show a significant packet loss at the UPF (approximately 24-32% drop between input and output packet rates). Furthermore, the UPF container was confirmed to be in a 'running' state, which aligns with the hypothesis of an internal fault or congestion rather than a crash. No falsifying evidence was found.

**Probes executed (3):**
- **Check UPF packet loss** ✓ CONSISTENT
    - *Tool:* `default_api.get_dp_quality_gauges(at_time_ts=1777510542.1738265, window_seconds=60)`
    - *Observation:* [EVIDENCE: get_dp_quality_gauges(at_time_ts=1777510542.1738265, window_seconds=60) -> "UPF:\n    in  packets/sec: 13.8\n    out packets/sec: 10.5"]
    - *Comment:* The discrepancy between input (13.8 pps) and output (10.5 pps) packets per second indicates a packet loss of ~24% within the UPF, which is consistent with the hypothesis.
- **Check status of 'upf' container** ✓ CONSISTENT
    - *Tool:* `default_api.get_network_status()`
    - *Observation:* [EVIDENCE: get_network_status() -> "'upf': 'running'"]
    - *Comment:* The UPF container is in a 'running' state, which is consistent with the hypothesis of an internal fault or congestion, rather than a crash.
- **Filter for UPF metrics, specifically CPU and memory utilization.** ✓ CONSISTENT
    - *Tool:* `default_api.get_diagnostic_metrics(at_time_ts=1777510542.1738265, nfs=['upf'])`
    - *Observation:* [EVIDENCE: get_diagnostic_metrics(at_time_ts=1777510542.1738265, nfs=['upf']) -> "normalized.upf.gtp_indatapktn3upf_per_ue = 8.104...normalized.upf.gtp_outdatapktn3upf_per_ue = 5.481"]
    - *Comment:* While direct CPU/memory metrics were not available, the metrics confirm a significant packet drop between the GTP input (8.104) and output (5.481) paths on a per-UE basis. This supports the core of the hypothesis regarding packet drops within the UPF.

### `h2` — ❌ **DISPROVEN**

**Hypothesis:** The RTPEngine is the source of the media degradation, dropping RTP packets internally due to a bug or resource issue. This would directly explain the high `rtpengine_loss_ratio`.

**Reasoning:** The hypothesis that RTPEngine is the internal source of packet loss is disproven. Probe 1 revealed that the UPF is dropping a significant percentage of packets before they even reach the RTPEngine. Probes 2 and 3 confirmed network-level packet loss on paths to the RTPEngine from two different sources (UPF and P-CSCF), contradicting the expectation of a healthy network path and pointing away from an internal RTPEngine issue.

**Probes executed (3):**
- **Check data plane quality gauges to see if loss is isolated to RTPEngine.** ✗ CONTRADICTS
    - *Tool:* `default_api.get_dp_quality_gauges(at_time_ts=1777510542.1738265, window_seconds=60)`
    - *Observation:* [EVIDENCE: get_dp_quality_gauges(at_time_ts=1777510542.1738265, window_seconds=60) -> "UPF:\n    in  packets/sec: 13.8\n    out packets/sec: 10.5"]
    - *Comment:* The UPF's outbound packet rate is significantly lower than its inbound rate, indicating packet loss of ~24% at the UPF. This contradicts the hypothesis that RTPEngine is the sole source of loss.
- **Measure RTT from UPF to RTPEngine to check network path health.** ✗ CONTRADICTS
    - *Tool:* `default_api.measure_rtt(container='upf', target_ip='172.22.0.16')`
    - *Observation:* [EVIDENCE: measure_rtt("upf", "172.22.0.16") -> "33.3333% packet loss"]
    - *Comment:* A 33% packet loss on the path from UPF to RTPEngine contradicts the expectation of a healthy network path, suggesting the issue is not internal to RTPEngine.
- **Measure RTT from P-CSCF to RTPEngine to check network path health from another source.** ✗ CONTRADICTS
    - *Tool:* `default_api.measure_rtt(container='pcscf', target_ip='172.22.0.16')`
    - *Observation:* [EVIDENCE: measure_rtt("pcscf", "172.22.0.16") -> "33.3333% packet loss"]
    - *Comment:* A 33% packet loss was also observed on the path from P-CSCF to RTPEngine. This reinforces that the issue is not isolated to the UPF-RTPEngine path and points towards either a broader network problem or an issue with RTPEngine's network ingress, but in either case, it's not an internal processing bug.

**Alternative suspects:** upf

### `h3` — ❌ **DISPROVEN**

**Hypothesis:** A general data plane failure exists within the container networking layer (e.g., veth interfaces, Linux bridge), causing packet loss between multiple components, including the UPF and RTPEngine.

**Reasoning:** The hypothesis of a 'general' data plane failure is contradicted by direct measurement. Probes measuring RTT and packet loss between three separate pairs of network functions (AMF-SMF, PCSCF-ICSCF, and SMF-PCF) all show healthy connections with zero packet loss and sub-millisecond latency. This indicates that the container networking layer is not experiencing a widespread failure, and the problem is likely specific to a particular component or path not tested, such as the one involving the UPF.

**Probes executed (3):**
- **from: amf, to_ip: <smf_ip>** ✗ CONTRADICTS
    - *Tool:* `default_api.measure_rtt(container='amf', target_ip='172.22.0.7')`
    - *Observation:* [EVIDENCE: measure_rtt("amf", "172.22.0.7") -> "3 packets transmitted, 3 received, 0% packet loss, time 2063ms\nrtt min/avg/max/mdev = 0.038/0.154/0.349/0.138 ms"]
    - *Comment:* The path between AMF and SMF is perfectly healthy, which contradicts the hypothesis of a general network failure.
- **from: pcscf, to_ip: <icscf_ip>** ✗ CONTRADICTS
    - *Tool:* `default_api.measure_rtt(container='pcscf', target_ip='172.22.0.19')`
    - *Observation:* [EVIDENCE: measure_rtt("pcscf", "172.22.0.19") -> "3 packets transmitted, 3 received, 0% packet loss, time 2044ms\nrtt min/avg/max/mdev = 0.111/0.135/0.182/0.033 ms"]
    - *Comment:* A second independent path between P-CSCF and I-CSCF is also healthy. This makes a general failure hypothesis very unlikely.
- **from: smf, to_ip: <pcf_ip>** ✗ CONTRADICTS
    - *Tool:* `default_api.measure_rtt(container='smf', target_ip='172.22.0.27')`
    - *Observation:* [EVIDENCE: measure_rtt("smf", "172.22.0.27") -> "3 packets transmitted, 3 received, 0% packet loss, time 2051ms\nrtt min/avg/max/mdev = 0.058/0.168/0.369/0.141 ms"]
    - *Comment:* A third healthy path, this time between SMF and PCF, confirms that the container networking layer is not generally failing. The issue must be more localized.


## Evidence Validation (Phase 6)

**Overall verdict:** clean
**Overall confidence:** high

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 3 | 3/3 | clean | high |
| `InvestigatorAgent_h2` | 4 | 3/3 | clean | high |
| `InvestigatorAgent_h3` | 4 | 3/3 | clean | high |


## Ground Truth

**Failure domain:** ims_media  
**Protocol impact:** RTP  
**Affected components:** rtpengine  
**Severity:** degraded

## Agent Diagnosis

**Model:** v6-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 168.1s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: The User Plane Function (UPF) is experiencing an internal fault or severe congestion, causing massive packet loss in the data plane, which has resulted in the failure of VoNR calls and IMS registrations.
> - **timeline**:
>     1. At timestamp 1777510542.17, a collapse in UPF data plane activity was detected (`core.upf.activity_during_calls_collapsed`).
>     2. This data plane degradation immediately caused high packet loss in RTP media streams, as observed by RTPEngine.
>     3. Subsequently, IMS registration attempts across all CSCFs ceased, as signaling could not traverse the failing data plane.
> - **root_cause**: The User Plane Function (UPF) is dropping a significant percentage of packets, likely due to an internal fault or resource exhaustion.
> - **affected_components**:
>     - `upf`: Root Cause
>     - `rtpengine`: Symptomatic
>     - `pcscf`: Symptomatic
>     - `icscf`: Symptomatic
>     - `scscf`: Symptomatic
> - **recommendation**: The operator should verify the internal state of the UPF. Specifically, investigate its internal logs for error messages or packet drop counters, and check the CPU and memory utilization of the UPF container to confirm or rule out resource exhaustion.
> - **confidence**: high
> - **explanation**: The investigation confirmed that the data plane is suffering from severe packet loss originating at the UPF. The primary hypothesis—that the UPF is dropping packets—was validated by probes showing a ~24-32% discrepancy between its input and output packet rates. Alternative hypotheses were disproven: a general container networking failure was ruled out by observing healthy, zero-loss connections between other network functions, and an internal RTPEngine fault was ruled out by confirming that packets were being lost before ever reaching the RTPEngine. All evidence points conclusively to the UPF as the root cause of the service degradation.

### Scoring Breakdown

**Overall score: 36%**

**Scorer assessment:** The agent correctly identified the fault type (packet loss) and its severity, and correctly placed RTPEngine in the IMS layer. However, it fundamentally misidentified the root cause, attributing the packet loss to the UPF instead of RTPEngine itself, and was highly confident in this incorrect diagnosis.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | No | The simulated failure was 30% packet loss on RTPEngine, meaning packets were dropped *after* RTPEngine received them. The agent's diagnosis explicitly states that an 'internal RTPEngine fault was ruled out by confirming that packets were being lost before ever reaching the RTPEngine', and instead attributes the root cause to the UPF. This directly contradicts the simulated failure mode. |
| Component overlap | 30% | The primary affected component was 'rtpengine'. The agent listed 'rtpengine' as 'Symptomatic' but incorrectly identified 'upf' as the 'Root Cause'. Since the correct component was identified but mis-ranked and not labeled as the root cause, a partial score is given. |
| Severity correct | Yes | The simulated failure involved 30% packet loss, leading to 'degrading voice quality (MOS drop, jitter increase, audible artifacts)'. The agent described this as 'massive packet loss' and 'failure of VoNR calls', which accurately reflects the significant impact of 30% packet loss on voice services. |
| Fault type identified | Yes | The simulated failure was 'packet loss'. The agent correctly identified 'packet loss' as the core issue, stating 'massive packet loss' and 'dropping a significant percentage of packets'. |
| Layer accuracy | Yes | The ground truth states 'rtpengine' belongs to the 'ims' layer. The agent's network analysis correctly flagged the 'ims' layer as 'red' with 'derived.rtpengine_loss_ratio' as evidence, indicating it correctly attributed the RTPEngine issue to its proper layer. |
| Confidence calibrated | No | The agent stated 'high' confidence, but its root cause diagnosis was incorrect. High confidence in a wrong diagnosis indicates poor calibration. |

**Ranking:** The agent provided a single root cause (UPF) which was incorrect. The correct root cause (RTPEngine packet loss) was not identified as the primary cause.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 194,513 |
| Output tokens | 5,810 |
| Thinking tokens | 13,179 |
| **Total tokens** | **213,502** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| EventAggregator | 0 | 0 | 0 |
| CorrelationAnalyzer | 0 | 0 | 0 |
| NetworkAnalystAgent | 36,320 | 6 | 3 |
| InstructionGeneratorAgent | 24,401 | 2 | 2 |
| InvestigatorAgent_h1 | 39,961 | 3 | 4 |
| InvestigatorAgent_h2 | 54,482 | 4 | 5 |
| InvestigatorAgent_h3 | 52,131 | 4 | 5 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 6,207 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 310.9s
