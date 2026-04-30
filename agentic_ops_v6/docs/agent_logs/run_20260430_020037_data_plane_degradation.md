# Episode Report: Data Plane Degradation

**Agent:** v6  
**Episode ID:** ep_20260430_015439_data_plane_degradation  
**Date:** 2026-04-30T01:54:40.992575+00:00  
**Duration:** 355.4s  

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
- **Nodes with significant deltas:** 5
- **Nodes with any drift:** 6

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 45.54 (per-bucket threshold: 28.18, context bucket (1, 1), trained on 323 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following metrics deviate from their learned-healthy baseline. Treat each as a semantic observation (meaning + numbers), not a number alone — the KB's interpretation is the authoritative reading.

- **`derived.rtpengine_loss_ratio`** (RTPEngine RTCP-reported per-RR average packet loss) — current **42.03 packets_per_rr** vs learned baseline **0.00 packets_per_rr** (MEDIUM, spike)
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

- **`normalized.icscf.cdp_replies_per_ue`** (I-CSCF Diameter reply rate per UE) — current **0.11 replies_per_second_per_ue** vs learned baseline **0.03 replies_per_second_per_ue** (MEDIUM, spike)
    - **What it measures:** Liveness of the I-CSCF↔HSS Cx path. Drops to 0 when HSS is unreachable OR when no signaling is occurring at the I-CSCF (idle or upstream P-CSCF partitioned).
    - **Spike means:** Either HSS is unreachable or upstream signaling has stopped reaching I-CSCF.
    - **Healthy typical range:** 0–1 replies_per_second_per_ue

- **`normalized.icscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at I-CSCF) — current **0.18 requests_per_second** vs learned baseline **0.06 requests_per_second** (MEDIUM, spike)
    - **What it measures:** Health of the P-CSCF → I-CSCF forwarding path (Mw interface). When
this drops to zero while P-CSCF REGISTER rate is still non-zero,
it's the SIGNATURE of an IMS partition between P-CSCF and I-CSCF.
    - **Spike means:** Forwarding issue on the Mw interface, or P-CSCF stopped forwarding.
    - **Healthy typical range:** 0–0.5 requests_per_second
    - **Healthy invariant:** Per-UE rate. Should closely track ims.pcscf.rcv_requests_register_per_ue.

- **`normalized.pcscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at P-CSCF) — current **0.24 requests_per_second** vs learned baseline **0.06 requests_per_second** (MEDIUM, spike)
    - **What it measures:** How actively UEs are refreshing their IMS registrations with the
P-CSCF. REGISTERs arrive periodically (re-registration timer) plus
at attach. Sustained zero means UEs cannot reach P-CSCF OR the
UE-to-network SIP path is broken.
    - **Spike means:** Fewer REGISTERs than expected — UE connectivity or P-CSCF reachability issue.
    - **Healthy typical range:** 0–0.5 requests_per_second
    - **Healthy invariant:** Per-UE rate — same value at any deployment scale.

- **`normalized.scscf.cdp_replies_per_ue`** (S-CSCF CDP Diameter replies per UE) — current **0.18 replies_per_second_per_ue** vs learned baseline **0.06 replies_per_second_per_ue** (MEDIUM, spike)
    - **What it measures:** Active S-CSCF Diameter traffic with HSS. Near-zero when registrations idle OR HSS partition.
    - **Spike means:** Diameter peering loss with HSS.
    - **Healthy typical range:** 0–1 replies_per_second_per_ue
    - **Healthy invariant:** Per-UE rate; varies with registration/auth load.

- **`normalized.scscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at S-CSCF) — current **0.18 requests_per_second** vs learned baseline **0.06 requests_per_second** (MEDIUM, spike)
    - **What it measures:** Health of the I-CSCF → S-CSCF forwarding path. Drop to zero while
I-CSCF is receiving REGISTERs = S-CSCF-side issue (crashed, or
I-CSCF → S-CSCF path broken).
    - **Spike means:** I-CSCF not forwarding or S-CSCF not receiving.
    - **Healthy typical range:** 0–0.5 requests_per_second
    - **Healthy invariant:** Per-UE rate. Tracks icscf.register rate.

- **`normalized.upf.gtp_indatapktn3upf_per_ue`** (GTP-U uplink rate per UE (N3)) — current **2.20 packets_per_second** vs learned baseline **1.45 packets_per_second** (MEDIUM, spike)
    - **What it measures:** Health of the uplink user-plane path gNB → UPF. Drops to near-zero
during RAN or N3 outage; stays nonzero during active calls or data
sessions. Decoupled from SIP signaling (signals data plane, not
control plane).
    - **Spike means:** Either UEs not generating uplink traffic (no calls/data) or N3 path is degraded.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE — constant regardless of UE pool size. Rises during active VoNR calls (~100 pps for G.711 voice) and data transfer.

- **`normalized.upf.gtp_outdatapktn3upf_per_ue`** (GTP-U downlink rate per UE (N3)) — current **1.61 packets_per_second** vs learned baseline **1.45 packets_per_second** (MEDIUM, shift)
    - **What it measures:** Health of the downlink user-plane path UPF → gNB. Typically mirrors
uplink rate during calls/data; asymmetry indicates directional
faults (e.g., UPF receiving from internet but not forwarding).
    - **Shift means:** Downlink data plane degraded — UPF not forwarding to gNB.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE — constant regardless of UE pool size. Roughly symmetric with uplink during healthy calls.

- **`normalized.pcscf.core:rcv_requests_invite_per_ue`** (SIP INVITE rate per UE at P-CSCF) — current **0.03 requests_per_second** vs learned baseline **0.00 requests_per_second** (LOW, spike)
    - **What it measures:** Call attempt rate from registered UEs. Unlike REGISTER (periodic),
INVITEs only fire when UEs place calls. Zero is normal during
quiet periods; nonzero INVITE with zero dialogs is the signature
of call setup failure.
    - **Spike means:** Fewer call attempts.
    - **Healthy typical range:** 0–0.2 requests_per_second
    - **Healthy invariant:** Per-UE rate.


## Event Aggregation (Phase 1)

**2 events fired during the observation window:**

- `ims.pcscf.register_time_elevated` (source: `ims.pcscf.avg_register_time_ms`, nf: `pcscf`, t=1777514198.6)  [current_value=2084.5, delta_percent=104.13259560299662]
- `core.upf.activity_during_calls_collapsed` (source: `core.upf.activity_during_calls`, nf: `upf`, t=1777514198.6)  [current_value=0.0459125]

## Correlation Analysis (Phase 2)

2 events fired but no composite hypothesis emerged. The events may be from independent faults or lack registered correlation hints in the KB.

## Network Analysis (Phase 3)

**Summary:** The network is experiencing a dual fault: a complete media plane failure causing silent VoNR calls, and a control plane degradation causing slow IMS registrations.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | Infrastructure appears healthy. The issue is likely at a higher layer. |
| **ran** | 🟢 GREEN | RAN appears to be functioning. |
| **core** | 🔴 RED | The core network's data plane (UPF) is critically impacted. |
| **ims** | 🔴 RED | The IMS services are impacted in both signaling and media planes. |

**CORE evidence:**
- derived.upf_activity_during_calls has collapsed to near-zero.
- UPF is suspected of dropping media packets.

**IMS evidence:**
- derived.pcscf_avg_register_time_ms is extremely high.
- derived.rtpengine_loss_ratio is very high.
- I-CSCF is experiencing timeouts to the HSS.

**Ranked hypotheses:**

- **`h1`** (fit=0.90, nf=upf, specificity=specific):
    - **Statement:** The UPF is the source of the media plane failure. It is not forwarding RTP packets from the gNB to RTPEngine, resulting in silent calls and high packet loss.
    - **Supporting events:** `core.upf.activity_during_calls_collapsed`
    - **Falsification probes:**
        - get_dp_quality_gauges() will show UPF ingress traffic but zero egress traffic.
        - measure_rtt('upf', 'rtpengine') and measure_rtt('upf', 'gnb') returning high values would indicate a networking issue local to the UPF's container.
- **`h2`** (fit=0.80, nf=pyhss, specificity=specific):
    - **Statement:** The HSS (pyhss) is latent or partially partitioned from the IMS CSCFs. This is causing slow Diameter Cx responses, leading to delayed IMS registrations and call setups.
    - **Supporting events:** `ims.pcscf.register_time_elevated`
    - **Falsification probes:**
        - measure_rtt('icscf', 'pyhss') and measure_rtt('scscf', 'pyhss') will show elevated RTTs if there is a network latency issue.
        - get_diagnostic_metrics(nfs=['pyhss']) can be checked for internal errors or high resource utilization.
- **`h3`** (fit=0.50, nf=pcscf, specificity=moderate):
    - **Statement:** P-CSCF is experiencing an internal fault or processing delay, which is the primary cause of the elevated SIP REGISTER processing time.
    - **Supporting events:** `ims.pcscf.register_time_elevated`
    - **Falsification probes:**
        - Investigate P-CSCF internal logs and metrics for signs of processing bottlenecks or errors not exposed as high-level metrics.
        - If HSS and UPF are proven healthy, the fault is likely within P-CSCF.


## Falsification Plans (Phase 4)

**3 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `upf`)

**Hypothesis:** The UPF is the source of the media plane failure. It is not forwarding RTP packets from the gNB to RTPEngine, resulting in silent calls and high packet loss.

**Probes (3):**
1. **`get_dp_quality_gauges`** — Get data plane metrics for a recent window (e.g., 15 seconds)
    - *Expected if hypothesis holds:* UPF ingress traffic from gNB (N3 interface) is present, but egress traffic to RTPEngine (N6 interface) is zero or near-zero. Specifically, upf_n3_rx_pkts > 0 and upf_n6_tx_pkts is close to 0.
    - *Falsifying observation:* UPF egress traffic (upf_n6_tx_pkts) is roughly equal to its ingress traffic (upf_n3_rx_pkts), indicating that the UPF is forwarding packets correctly.
2. **`measure_rtt`** — from: 'upf', to_ip: 'rtpengine'
    - *Expected if hypothesis holds:* High RTT or packet loss, indicating a networking issue local to the UPF's container or its immediate network uplink.
    - *Falsifying observation:* Low RTT and zero packet loss, indicating the network path from the UPF container to the RTPEngine container is healthy.
3. **`measure_rtt`** — from: 'upf', to_ip: 'gnb'
    - *Expected if hypothesis holds:* High RTT or packet loss. If the UPF's local networking is faulty, its connectivity to all peers would be impacted.
    - *Falsifying observation:* Low RTT and zero packet loss. If this path is healthy while the path to RTPEngine is not, it implies the issue is not with the UPF's networking in general, but is specific to the path towards the core network (RTPEngine).

*Notes:* This plan tests for a media plane failure at the UPF, anchored to the vonr_call_setup flow, step 12 ('RTP media'). The supporting event was core.upf.activity_during_calls_collapsed.

### Plan for `h2` (target: `pyhss`)

**Hypothesis:** The HSS (pyhss) is latent or partially partitioned from the IMS CSCFs. This is causing slow Diameter Cx responses, leading to delayed IMS registrations and call setups.

**Probes (3):**
1. **`measure_rtt`** — from: 'icscf', to_ip: 'pyhss'
    - *Expected if hypothesis holds:* Elevated RTT or packet loss.
    - *Falsifying observation:* Normal RTT and zero packet loss, suggesting the network path is not the source of latency.
2. **`measure_rtt`** — from: 'scscf', to_ip: 'pyhss'
    - *Expected if hypothesis holds:* Elevated RTT or packet loss. If both this and the icscf->pyhss probes show high latency, it strongly points to a problem with pyHSS itself.
    - *Falsifying observation:* Normal RTT and zero packet loss. If the i-cscf->pyhss RTT was high but this one is normal, it suggests the problem is not with pyHSS, but with I-CSCF or its specific network path.
3. **`get_diagnostic_metrics`** — nfs=['pyhss']
    - *Expected if hypothesis holds:* Internal pyHSS metrics show signs of distress, such as high CPU utilization, high memory usage, or an elevated number of errors or timeouts in Diameter processing.
    - *Falsifying observation:* All internal pyHSS metrics are within normal operational bounds, indicating it is healthy and not the source of the observed latency.

*Notes:* This plan tests for a control plane failure at the HSS, anchored to the ims_registration flow, steps 4-7. The supporting event was ims.pcscf.register_time_elevated.

### Plan for `h3` (target: `pcscf`)

**Hypothesis:** P-CSCF is experiencing an internal fault or processing delay, which is the primary cause of the elevated SIP REGISTER processing time.

**Probes (3):**
1. **`get_diagnostic_metrics`** — nfs=['pcscf']
    - *Expected if hypothesis holds:* P-CSCF's internal metrics, such as CPU or memory utilization (e.g., shmem usage), are abnormally high, indicating resource contention or an internal processing loop.
    - *Falsifying observation:* P-CSCF's internal resource metrics are normal, despite the high registration time. This would suggest the P-CSCF is spending its time waiting for a response from a downstream component, not on internal processing.
2. **`get_diagnostic_metrics`** — nfs=['icscf', 'scscf']
    - *Expected if hypothesis holds:* Metrics related to Diameter transactions on I-CSCF and S-CSCF (e.g., diameter_cx_latency) are normal. This would indicate the downstream IMS components are responding quickly.
    - *Falsifying observation:* Diameter latency metrics on I-CSCF or S-CSCF are elevated. This would be strong evidence that the delay is caused by the HSS (h2), not the P-CSCF.
3. **`run_kamcmd`** — container: 'pcscf', command: 'tm.stats'
    - *Expected if hypothesis holds:* The Kamailio transaction manager statistics show a high number of ongoing 'active' transactions, suggesting P-CSCF's workers are busy or stuck.
    - *Falsifying observation:* The number of 'active' transactions is low, indicating the P-CSCF is mostly idle and likely waiting on network I/O for responses from downstream.

*Notes:* This plan attempts to isolate the cause of slow IMS registration to the P-CSCF itself, discriminating against the alternative hypothesis (h2) that a downstream component (HSS) is the cause. The supporting event was ims.pcscf.register_time_elevated.


## Parallel Investigators (Phase 5)

**3 sub-Investigator verdict(s):** **1 NOT_DISPROVEN**, **1 INCONCLUSIVE**, **1 DISPROVEN**

### `h1` — ✅ **NOT_DISPROVEN**

**Hypothesis:** The UPF is the source of the media plane failure. It is not forwarding RTP packets from the gNB to RTPEngine, resulting in silent calls and high packet loss.

**Reasoning:** The evidence indicates a fault localized at the UPF. Historical data from the time of the anomaly shows the UPF was dropping approximately 32% of packets between its ingress from the gNB and its egress to RTPEngine. While the statement 'not forwarding' is an exaggeration, this high packet loss makes the UPF the source of the failure. Live probes confirm that while the UPF's connectivity to the core network (RTPEngine) is healthy, its connectivity to the gNB has failed, confirming the issue is with the UPF's RAN-facing side.

**Probes executed (3):**
- **Get data plane metrics for a recent window (e.g., 15 seconds)** ✓ CONSISTENT
    - *Tool:* `print(default_api.get_dp_quality_gauges(at_time_ts = 1777514159.4328377, window_seconds = 15))`
    - *Observation:* [EVIDENCE: get_dp_quality_gauges(at_time_ts=1777514159.4328377, window_seconds=15) -> "UPF:\n    in  packets/sec: 6.3\n    out packets/sec: 4.3"]
    - *Comment:* The UPF is dropping ~32% of packets (ingress 6.3 pps, egress 4.3 pps). This is a significant loss and is consistent with the UPF being the source of the media plane failure, although it is not a total drop.
- **from: 'upf', to_ip: 'rtpengine'** ✗ CONTRADICTS
    - *Tool:* `print(default_api.measure_rtt(container = "upf", target_ip = "172.22.0.16"))`
    - *Observation:* [EVIDENCE: measure_rtt("upf", "172.22.0.16") -> "3 packets transmitted, 3 received, 0% packet loss, time 2041ms"]
    - *Comment:* The network path from UPF to RTPEngine is healthy. This contradicts the idea that the UPF has a general, container-wide networking problem. The issue appears to be specific to one of its interfaces.
- **from: 'upf', to_ip: 'gnb'** ✓ CONSISTENT
    - *Tool:* `print(default_api.measure_rtt(container = "upf", target_ip = "172.22.0.23"))`
    - *Observation:* [EVIDENCE: measure_rtt("upf", "172.22.0.23") -> "3 packets transmitted, 0 received, 100% packet loss, time 2054ms"]
    - *Comment:* The UPF cannot reach the gNB. This live probe showing 100% packet loss confirms a network failure on the UPF's RAN-facing interface (N3), which is consistent with the hypothesis that the UPF is the source of the failure.

### `h2` — ❓ **INCONCLUSIVE**

**Hypothesis:** The HSS (pyhss) is latent or partially partitioned from the IMS CSCFs. This is causing slow Diameter Cx responses, leading to delayed IMS registrations and call setups.

**Reasoning:** The 'partially partitioned' aspect of the hypothesis is contradicted by direct measurement. RTT probes from both I-CSCF and S-CSCF to pyHSS show excellent connectivity (<1ms RTT and 0% packet loss). However, the 'latent' aspect, suggesting an internal problem within pyHSS, could not be verified or falsified. The `get_diagnostic_metrics` tool returned no data for pyHSS, preventing any assessment of its internal health (CPU, memory, error rates). Without these metrics, I cannot rule out that pyHSS itself is the source of the latency.

**Probes executed (3):**
- **from: 'icscf', to_ip: 'pyhss'** ✗ CONTRADICTS
    - *Tool:* `measure_rtt(container='icscf', target_ip='172.22.0.18')`
    - *Observation:* [EVIDENCE: measure_rtt("icscf", "172.22.0.18") -> "rtt min/avg/max/mdev = 0.067/0.093/0.110/0.019 ms"]
    - *Comment:* The RTT is extremely low, with zero packet loss. This contradicts the expectation of elevated RTT and falsifies the 'network partition' component of the hypothesis.
- **from: 'scscf', to_ip: 'pyhss'** ✗ CONTRADICTS
    - *Tool:* `measure_rtt(container='scscf', target_ip='172.22.0.18')`
    - *Observation:* [EVIDENCE: measure_rtt("scscf", "172.22.0.18") -> "rtt min/avg/max/mdev = 0.067/0.275/0.615/0.242 ms"]
    - *Comment:* Similar to the I-CSCF, the S-CSCF has excellent connectivity to the HSS. This confirms the network path is not the problem.
- **nfs=['pyhss']** ~ AMBIGUOUS
    - *Tool:* `get_diagnostic_metrics(at_time_ts=1777514159.4328377, nfs=['pyhss'])`
    - *Observation:* [EVIDENCE: get_diagnostic_metrics(at_time_ts=1777514159.4328377, nfs=['pyhss']) -> ""]
    - *Comment:* The probe returned no metrics for pyHSS, even though the container is running. This prevents any conclusion about its internal health. I can neither confirm signs of distress nor observe normal operation. Therefore, the 'latent' part of the hypothesis is unverifiable.

### `h3` — ❌ **DISPROVEN**

**Hypothesis:** P-CSCF is experiencing an internal fault or processing delay, which is the primary cause of the elevated SIP REGISTER processing time.

**Reasoning:** The evidence contradicts the hypothesis that P-CSCF has an internal fault. Probes show that downstream components are latent, specifically the Diameter transactions from I-CSCF and S-CSCF to the HSS are slow and timing out. Furthermore, Kamailio transaction statistics on P-CSCF show no active or waiting transactions, indicating it is not internally blocked but rather waiting for responses from other network functions. This points to the HSS as the source of the delay.

**Probes executed (3):**
- **P-CSCF's internal metrics, such as CPU or memory utilization (e.g., shmem usage), are abnormally high, indicating resource contention or an internal processing loop.** ~ AMBIGUOUS
    - *Tool:* `print(default_api.get_diagnostic_metrics(at_time_ts = 1777514159.4328377, nfs = ["pcscf"]))`
    - *Observation:* [EVIDENCE: get_diagnostic_metrics(at_time_ts=1777514159.4328377, nfs=["pcscf"]) -> "derived.pcscf_avg_register_time_ms = 688.4
        learned_normal = 114.9... sl:4xx_replies = 0 [counter]... sl:5xx_replies = 0 [counter]"]
    - *Comment:* This probe confirmed the elevated registration time but did not show any signs of internal resource contention or SIP errors at the P-CSCF. The available metrics were insufficient to either confirm or deny an internal fault based on this probe alone.
- **Metrics related to Diameter transactions on I-CSCF and S-CSCF (e.g., diameter_cx_latency) are normal. This would indicate the downstream IMS components are responding quickly.** ✗ CONTRADICTS
    - *Tool:* `print(default_api.get_diagnostic_metrics(at_time_ts = 1777514159.4328377, nfs = ["icscf", "scscf"]))`
    - *Observation:* [EVIDENCE: get_diagnostic_metrics(at_time_ts=1777514159.4328377, nfs=["icscf", "scscf"]) -> "icscf.cdp:average_response_time = 74... learned_normal = 49.27... cdp:timeout = 1 [counter]... scscf.ims_auth:mar_avg_response_time = 116... learned_normal = 81.67"]
    - *Comment:* This probe's results directly contradict the hypothesis. Both I-CSCF and S-CSCF show elevated Diameter response times and even a timeout when communicating with the HSS. This indicates the delay is downstream from P-CSCF, likely at the HSS.
- **The Kamailio transaction manager statistics show a high number of ongoing 'active' transactions, suggesting P-CSCF's workers are busy or stuck.** ✗ CONTRADICTS
    - *Tool:* `print(default_api.run_kamcmd(command = "tm.stats", container = "pcscf"))`
    - *Observation:* [EVIDENCE: run_kamcmd(container='pcscf', command='tm.stats') -> "current: 0
	waiting: 0"]
    - *Comment:* The transaction manager statistics show zero current or waiting transactions. This falsifies the hypothesis of an internal processing delay or fault, as it indicates the P-CSCF is idle, not stuck processing requests. It is most likely waiting for responses from downstream components.

**Alternative suspects:** pyhss


## Evidence Validation (Phase 6)

**Overall verdict:** clean
**Overall confidence:** high

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 4 | 3/3 | clean | high |
| `InvestigatorAgent_h2` | 6 | 3/3 | clean | high |
| `InvestigatorAgent_h3` | 3 | 3/3 | clean | high |


## Ground Truth

**Failure domain:** data_plane  
**Protocol impact:** GTP-U  
**Affected components:** upf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v6-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 208.8s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: The network is suffering from a dual fault: a confirmed media plane failure in the UPF causing silent calls, and a control plane degradation causing slow IMS registrations, for which the HSS is the primary but unconfirmed suspect.
> - **timeline**:
>     1. First, `core.upf.activity_during_calls_collapsed` was observed, indicating a sudden drop in media traffic forwarding.
>     2. Subsequently, `ims.pcscf.register_time_elevated` was observed, indicating a slowdown in the IMS registration process.
> - **root_cause**: The investigation identified two independent root causes:
>     - **Primary Root Cause (Media Plane):** The User Plane Function (UPF) has a failure on its RAN-facing (N3) interface. Probes confirm the UPF can reach the core network but has 100% packet loss when attempting to reach the gNB, explaining the silent calls. The `primary_suspect_nf` is `upf`.
>     - **Secondary Root Cause (Control Plane):** The Home Subscriber Server (HSS) is highly suspected of being internally latent. While its network connectivity is healthy, it is believed to be the source of slow Diameter responses causing registration delays. The `primary_suspect_nf` is `pyhss`.
> - **affected_components**:
>     - `upf`: Root Cause (Media Plane)
>     - `pyhss`: Suspected Root Cause (Control Plane)
>     - `pcscf`: Symptomatic (Control Plane)
>     - `icscf`: Symptomatic (Control Plane)
>     - `scscf`: Symptomatic (Control Plane)
> - **recommendation**: Based on the two independent faults, the operator should:
>     1. Investigate the `upf` container's network status, logs, and interface configuration to diagnose the connectivity failure on its RAN-facing interface (N3).
>     2. Manually inspect the `pyhss` container for signs of internal distress, such as high CPU/memory utilization, application-level errors in its logs, or other processing bottlenecks, as diagnostic tools failed to retrieve these metrics.
> - **confidence**: medium
> - **explanation**: The investigation confirmed a dual-fault scenario. The silent call issue was successfully traced to the UPF (hypothesis `h1` was NOT_DISPROVEN), with live probes confirming a total packet loss on its RAN-facing N3 interface. The slow registration issue was isolated by disproving a P-CSCF fault (hypothesis `h3`), as evidence showed the P-CSCF was idle and waiting for slow downstream responses from the HSS. However, the hypothesis implicating the HSS (`h2`) remains INCONCLUSIVE; while network RTT to the HSS is normal, diagnostic probes for its internal health returned no data. Therefore, the HSS is the most likely cause, but it cannot be definitively confirmed. Confidence is set to 'medium' due to this inconclusive finding.

### Scoring Breakdown

**Overall score: 85%**

**Scorer assessment:** The agent accurately identified the UPF and packet loss as the primary root cause, but misjudged the severity. It correctly placed the component in its layer and expressed appropriate confidence given its dual-fault diagnosis, one of which was unconfirmed.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | Yes | The agent correctly identified the User Plane Function (UPF) as the primary root cause for the media plane failure and 'packet loss' as the nature of the failure. Although it stated '100% packet loss' instead of the simulated '30% packet loss', the core component and fault type are correct and it was explicitly labeled 'Primary Root Cause'. The secondary root cause (HSS latency) was not part of the simulation, but the primary cause was correctly identified and prioritized. |
| Component overlap | 100% | The primary affected component, 'upf', was correctly listed in `affected_components` as 'Root Cause (Media Plane)'. |
| Severity correct | No | The simulated failure was '30% packet loss' leading to 'degradation' and 'voice quality drops'. The agent diagnosed '100% packet loss' and 'silent calls', which indicates a complete outage rather than a degradation. This is a mismatch in severity. |
| Fault type identified | Yes | The agent correctly identified 'packet loss' as the observable fault type on the UPF, which matches the simulated failure mode. |
| Layer accuracy | Yes | The simulated failure component 'upf' belongs to the 'core' layer. The agent's network analysis correctly rated the 'core' layer as 'red' and provided evidence related to the UPF. |
| Confidence calibrated | Yes | The agent assigned 'medium' confidence, explaining that it was due to the inconclusive finding regarding the secondary HSS issue. While the primary (simulated) issue was well-diagnosed, the inclusion of an unconfirmed secondary issue justifies a 'medium' confidence for the overall diagnosis. |

**Ranking position:** #1 — The correct root cause (UPF packet loss) was explicitly identified as the 'Primary Root Cause (Media Plane)' in the diagnosis, indicating it was ranked first.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 296,379 |
| Output tokens | 6,304 |
| Thinking tokens | 18,442 |
| **Total tokens** | **321,125** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| EventAggregator | 0 | 0 | 0 |
| CorrelationAnalyzer | 0 | 0 | 0 |
| NetworkAnalystAgent | 102,133 | 7 | 8 |
| InstructionGeneratorAgent | 25,470 | 3 | 2 |
| InvestigatorAgent_h1 | 59,446 | 4 | 5 |
| InvestigatorAgent_h2 | 81,865 | 6 | 7 |
| InvestigatorAgent_h3 | 45,737 | 3 | 4 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 6,474 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 355.4s
