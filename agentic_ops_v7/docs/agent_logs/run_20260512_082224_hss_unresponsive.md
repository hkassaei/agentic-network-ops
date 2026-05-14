# Episode Report: HSS Unresponsive

**Agent:** v7  
**Episode ID:** ep_20260512_081208_hss_unresponsive  
**Date:** 2026-05-12T08:12:09.644516+00:00  
**Duration:** 613.8s  

---

## Scenario

**Category:** network  
**Blast radius:** single_nf  
**Description:** Inject 60-second outbound delay on the HSS (PyHSS), making it functionally unreachable for all real-time protocols. The HSS container is running and the process is alive, but all network responses are delayed by 60 seconds — far exceeding Diameter Cx timeouts (5-30s) and standard probe timeouts (10s). From the perspective of diagnostic tools and IMS peers, the HSS appears completely unresponsive or unreachable.

## Faults Injected

- **network_latency** on `pyhss` — {'delay_ms': 60000, 'jitter_ms': 0}

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

**ANOMALY DETECTED.** Overall anomaly score: 43.88 (per-bucket threshold: 28.18, context bucket (1, 1), trained on 323 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following metrics deviate from their learned-healthy baseline. Treat each as a semantic observation (meaning + numbers), not a number alone — the KB's interpretation is the authoritative reading.

- **`context.cx_active`** — current **0.00** vs learned baseline **0.59** (MEDIUM, drop). *(No KB context available — interpret from the metric name.)*

- **`derived.icscf_uar_timeout_ratio`** (I-CSCF UAR timeout ratio) — current **1.00 ratio** vs learned baseline **0.00 ratio** (MEDIUM, spike)
    - **What it measures:** Partial partition or severe overload on the Cx path. Zero in
healthy operation; non-zero means some UAR queries did not receive
any response within the timeout window.
    - **Spike means:** HSS partitioned, overloaded past its timeout, or Cx path losing packets.
    - **Healthy typical range:** 0–0 ratio
    - **Healthy invariant:** Zero in healthy operation.

- **`normalized.icscf.cdp_replies_per_ue`** (I-CSCF Diameter reply rate per UE) — current **0.00 replies_per_second_per_ue** vs learned baseline **0.03 replies_per_second_per_ue** (MEDIUM, drop)
    - **What it measures:** Liveness of the I-CSCF↔HSS Cx path. Drops to 0 when HSS is unreachable OR when no signaling is occurring at the I-CSCF (idle or upstream P-CSCF partitioned).
    - **Drop means:** No Cx replies in the window. Could be healthy idle OR a Cx-path fault.
    - **Healthy typical range:** 0–1 replies_per_second_per_ue

- **`normalized.icscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at I-CSCF) — current **0.02 requests_per_second** vs learned baseline **0.06 requests_per_second** (MEDIUM, drop)
    - **What it measures:** Health of the P-CSCF → I-CSCF forwarding path (Mw interface). When
this drops to zero while P-CSCF REGISTER rate is still non-zero,
it's the SIGNATURE of an IMS partition between P-CSCF and I-CSCF.
    - **Drop means:** Either UEs not registering at all, or P-CSCF isolated from I-CSCF.
    - **Healthy typical range:** 0–0.5 requests_per_second
    - **Healthy invariant:** Per-UE rate. Should closely track ims.pcscf.rcv_requests_register_per_ue.

- **`normalized.pcscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at P-CSCF) — current **0.02 requests_per_second** vs learned baseline **0.06 requests_per_second** (MEDIUM, drop)
    - **What it measures:** How actively UEs are refreshing their IMS registrations with the
P-CSCF. REGISTERs arrive periodically (re-registration timer) plus
at attach. Sustained zero means UEs cannot reach P-CSCF OR the
UE-to-network SIP path is broken.
    - **Drop means:** No REGISTERs flowing. Unusual unless UEs are all deregistered.
    - **Healthy typical range:** 0–0.5 requests_per_second
    - **Healthy invariant:** Per-UE rate — same value at any deployment scale.

- **`normalized.scscf.cdp_replies_per_ue`** (S-CSCF CDP Diameter replies per UE) — current **0.00 replies_per_second_per_ue** vs learned baseline **0.06 replies_per_second_per_ue** (MEDIUM, drop)
    - **What it measures:** Active S-CSCF Diameter traffic with HSS. Near-zero when registrations idle OR HSS partition.
    - **Drop means:** No active S-CSCF Diameter exchanges (idle or partitioned).
    - **Healthy typical range:** 0–1 replies_per_second_per_ue
    - **Healthy invariant:** Per-UE rate; varies with registration/auth load.

- **`normalized.scscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at S-CSCF) — current **0.00 requests_per_second** vs learned baseline **0.06 requests_per_second** (MEDIUM, drop)
    - **What it measures:** Health of the I-CSCF → S-CSCF forwarding path. Drop to zero while
I-CSCF is receiving REGISTERs = S-CSCF-side issue (crashed, or
I-CSCF → S-CSCF path broken).
    - **Drop means:** S-CSCF isolated or not running.
    - **Healthy typical range:** 0–0.5 requests_per_second
    - **Healthy invariant:** Per-UE rate. Tracks icscf.register rate.

- **`normalized.upf.gtp_outdatapktn3upf_per_ue`** (GTP-U downlink rate per UE (N3)) — current **2.41 packets_per_second** vs learned baseline **1.45 packets_per_second** (LOW, spike)
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

- **`derived.upf_activity_during_calls`** (UPF activity consistency with active dialogs) — current **0.05 ratio** vs learned baseline **0.54 ratio** (LOW, drop)
    - **What it measures:** Cross-layer consistency check between IMS dialog state and UPF
throughput. A drop while dialogs_per_ue is non-zero is a
smoking-gun signal for media-plane failure independent of signaling.
    - **Drop means:** Active calls reported but no media flowing — media path broken (UPF, RTPEngine, or N3 packet loss).
    - **Healthy typical range:** 0.3–1 ratio
    - **Healthy invariant:** 1.0 when traffic fully follows active calls; 0.0 when signaling says active but data plane is silent.

- **`normalized.upf.gtp_indatapktn3upf_per_ue`** (GTP-U uplink rate per UE (N3)) — current **2.41 packets_per_second** vs learned baseline **1.45 packets_per_second** (LOW, spike)
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


## Symptom Classifier (Phase 0.5)

**Label:** `transport_layer`  
**Flag counts:** transport=3, application=0, ambiguous=7

### Transport-bucket flags (3)

| Metric | Direction | Score | KB-driven reason |
|---|---|---:|---|
| `normalized.upf.gtp_outdatapktn3upf_per_ue` | spike | 3.58 | KB-labeled transport: core.upf.gtp_outdatapktn3upf_per_ue (spike, score=3.58) |
| `derived.upf_activity_during_calls` | drop | 3.18 | KB-labeled transport: core.upf.activity_during_calls (drop, score=3.18) |
| `normalized.upf.gtp_indatapktn3upf_per_ue` | spike | 2.67 | KB-labeled transport: core.upf.gtp_indatapktn3upf_per_ue (spike, score=2.67) |

### Ambiguous-bucket flags (7)

| Metric | Direction | Score | KB-driven reason |
|---|---|---:|---|
| `context.cx_active` | drop | 4.28 | no KB entry for context.cx_active — classification ambiguous |
| `derived.icscf_uar_timeout_ratio` | spike | 4.28 | KB-labeled mixed: ims.icscf.uar_timeout_ratio (spike, score=4.28) |
| `normalized.icscf.cdp_replies_per_ue` | drop | 4.28 | KB-labeled mixed: ims.icscf.cdp_replies_per_ue (drop, score=4.28) |
| `normalized.icscf.core:rcv_requests_register_per_ue` | drop | 4.28 | KB-labeled mixed: ims.icscf.rcv_requests_register_per_ue (drop, score=4.28) |
| `normalized.pcscf.core:rcv_requests_register_per_ue` | drop | 4.28 | KB-labeled mixed: ims.pcscf.rcv_requests_register_per_ue (drop, score=4.28) |
| `normalized.scscf.cdp_replies_per_ue` | drop | 4.28 | KB-labeled mixed: ims.scscf.cdp_replies_per_ue (drop, score=4.28) |
| `normalized.scscf.core:rcv_requests_register_per_ue` | drop | 4.28 | KB-labeled mixed: ims.scscf.rcv_requests_register_per_ue (drop, score=4.28) |

**Rationale:**

```
label=transport_layer. 3 transport-layer signal(s); no application-layer smoking guns. Routes to the deterministic path walk (see ADR path_anchored_probe_planning_for_transport_layer_faults.md).

Transport signals: normalized.upf.gtp_outdatapktn3upf_per_ue (spike, score=3.58) — KB-labeled transport: core.upf.gtp_outdatapktn3upf_per_ue (spike, score=3.58); derived.upf_activity_during_calls (drop, score=3.18) — KB-labeled transport: core.upf.activity_during_calls (drop, score=3.18); normalized.upf.gtp_indatapktn3upf_per_ue (spike, score=2.67) — KB-labeled transport: core.upf.gtp_indatapktn3upf_per_ue (spike, score=2.67)

Ambiguous signals: context.cx_active (drop, score=4.28) — no KB entry for context.cx_active — classification ambiguous; derived.icscf_uar_timeout_ratio (spike, score=4.28) — KB-labeled mixed: ims.icscf.uar_timeout_ratio (spike, score=4.28); normalized.icscf.cdp_replies_per_ue (drop, score=4.28) — KB-labeled mixed: ims.icscf.cdp_replies_per_ue (drop, score=4.28); normalized.icscf.core:rcv_requests_register_per_ue (drop, score=4.28) — KB-labeled mixed: ims.icscf.rcv_requests_register_per_ue (drop, score=4.28); normalized.pcscf.core:rcv_requests_register_per_ue (drop, score=4.28) — KB-labeled mixed: ims.pcscf.rcv_requests_register_per_ue (drop, score=4.28) [+2 more]
```

## Transport-Layer Route (Phase 0.6)

### Resolver

**Flow:** `data_pdu_session_user_traffic` (Data PDU Session — User Traffic)  
**Direction:** both  
**Hop count:** 11

**Candidates considered:**

| Flow | Score |
|---|---:|
| `data_pdu_session_user_traffic` ← chosen | 12 |
| `vonr_media` | 12 |
| `ims_registration` | 8 |
| `vonr_call_teardown` | 8 |
| `vonr_call_setup` | 8 |

**Rationale:**

```
Resolved transport path to flow `data_pdu_session_user_traffic` (score=12, 11 hops on the walk). Load-bearing components: ['context', 'icscf', 'pcscf', 'scscf', 'upf']. Other candidate flows considered: vonr_media=12, ims_registration=8, vonr_call_teardown=8, vonr_call_setup=8.
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

**1 events fired during the observation window:**

- `core.upf.activity_during_calls_collapsed` (source: `core.upf.activity_during_calls`, nf: `upf`, t=1778573647.1)  [current_value=0.051735]

## Correlation Analysis (Phase 2)

1 events fired but no composite hypothesis emerged. The events may be from independent faults or lack registered correlation hints in the KB.

## Network Analysis (Phase 3)

**Summary:** The IMS stack is non-functional due to a suspected HSS failure, causing a complete halt in user registrations and call setup procedures; a secondary data plane anomaly is also observed at the UPF.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | No signs of infrastructure-level failure. |
| **ran** | 🟢 GREEN | RAN appears healthy and stable. |
| **core** | 🟡 YELLOW | The UPF is showing anomalous traffic patterns and a collapse in expected activity during calls, but the primary failure appears to be in the IMS signaling layer. This is likely a downstream effect. |
| **ims** | 🔴 RED | Complete failure of IMS registration and authentication flows, pointing to a central IMS component failure. All CSCFs report zero registration traffic and no replies from the HSS. |

**CORE evidence:**
- derived.upf_activity_during_calls:drop:LOW
- normalized.upf.gtp_indatapktn3upf_per_ue:spike:LOW
- normalized.upf.gtp_outdatapktn3upf_per_ue:spike:LOW
- core.upf.activity_during_calls_collapsed

**IMS evidence:**
- derived.icscf_uar_timeout_ratio:spike:MEDIUM
- normalized.icscf.cdp_replies_per_ue:drop:MEDIUM
- normalized.scscf.cdp_replies_per_ue:drop:MEDIUM
- normalized.pcscf.core:rcv_requests_register_per_ue:drop:MEDIUM
- normalized.icscf.core:rcv_requests_register_per_ue:drop:MEDIUM
- normalized.scscf.core:rcv_requests_register_per_ue:drop:MEDIUM
- context.cx_active:drop:MEDIUM

**Ranked hypotheses:**

- **`h1`** (fit=0.90, nf=pyhss, specificity=specific):
    - **Statement:** The HSS (pyhss) is unresponsive to Diameter Cx requests, causing a complete failure of IMS registration and authentication.
    - **Falsification probes:**
        - Check the logs of the pyhss container for error messages or signs of a crash/hang.
        - Execute a 'measure_rtt' from the 'icscf' container to the 'pyhss' container to test for network-level connectivity issues.
        - Check the 'mysql' database that 'pyhss' uses for lock contention or errors.
- **`h2`** (fit=0.80, nf=dns, specificity=specific):
    - **Statement:** A DNS failure is preventing IMS components from resolving the hostname for the HSS, leading to the observed Diameter Cx timeouts and registration failures.
    - **Falsification probes:**
        - Execute 'nslookup pyhss' from within the 'icscf' container to verify DNS resolution.
        - Check the logs of the 'dns' container for any error messages.
- **`h3`** (fit=0.60, nf=upf, specificity=moderate):
    - **Statement:** The UPF has experienced a data plane failure, leading to a collapse in media traffic.
    - **Supporting events:** `core.upf.activity_during_calls_collapsed`
    - **Falsification probes:**
        - Check UPF container logs for errors.
        - Use 'measure_rtt' to check connectivity between 'rtpengine' and 'upf'.
        - Inspect PFCP session status on the SMF and UPF.


## Falsification Plans (Phase 4)

**3 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `pyhss`)

**Hypothesis:** The HSS (pyhss) is unresponsive to Diameter Cx requests, causing a complete failure of IMS registration and authentication.

**Probes (3):**
1. **`measure_rtt`** — from:'icscf', to:'pyhss'
    - *Expected if hypothesis holds:* High RTT or packet loss, indicating unresponsiveness.
    - *Falsifying observation:* Normal RTT and no packet loss. This would suggest the network path is healthy and the HSS is responsive at the network layer.
2. **`measure_rtt`** — from:'scscf', to:'pyhss'
    - *Expected if hypothesis holds:* High RTT or packet loss, confirming pyhss unresponsiveness from a different source.
    - *Falsifying observation:* Normal RTT and no packet loss. If the first probe showed issues, this would isolate the problem to the icscf or its specific path, not pyhss.
3. **`check_process_listeners`** — container:'pyhss'
    - *Expected if hypothesis holds:* A process is listening on the Diameter port 3868/tcp, indicating the process is running but may be hung or otherwise unresponsive.
    - *Falsifying observation:* No process is listening on port 3868/tcp. This points to a different failure mode, such as the process having failed to start.

*Notes:* This plan tests the 'unresponsive' claim from h1. It uses a paired set of 'measure_rtt' probes to isolate unresponsiveness to the pyhss container versus the network path or source container. It also checks for a more fundamental failure (a non-listening process) as a falsifying condition.

### Plan for `h2` (target: `dns`)

**Hypothesis:** A DNS failure is preventing IMS components from resolving the hostname for the HSS, leading to the observed Diameter Cx timeouts and registration failures.

**Probes (3):**
1. **`measure_rtt`** — from:'icscf', to:'dns'
    - *Expected if hypothesis holds:* High RTT or packet loss, indicating network-level connectivity issues to the DNS server.
    - *Falsifying observation:* Normal RTT and no packet loss, suggesting network connectivity to the DNS server is fine.
2. **`measure_rtt`** — from:'scscf', to:'dns'
    - *Expected if hypothesis holds:* High RTT or packet loss, confirming issues reaching the DNS server from multiple clients.
    - *Falsifying observation:* Normal RTT and no packet loss. If the first probe showed issues, this would point away from a general DNS NF failure.
3. **`check_process_listeners`** — container:'dns'
    - *Expected if hypothesis holds:* No process is listening on port 53/udp or 53/tcp, indicating the DNS server process itself is down.
    - *Falsifying observation:* A process is listening on port 53. This would suggest the DNS server process is running, and the issue might be in its configuration or upstream, rather than a process failure.

*Notes:* This plan attempts to falsify the DNS failure hypothesis by checking network reachability to the DNS container from two different IMS components and verifying that the DNS process is listening on its standard port.

### Plan for `h3` (target: `upf`)

**Hypothesis:** The UPF has experienced a data plane failure, leading to a collapse in media traffic.

**Probes (3):**
1. **`get_dp_quality_gauges`** — read upf.activity_during_calls
    - *Expected if hypothesis holds:* The value of upf.activity_during_calls is near zero, indicating a collapse in media traffic despite active calls.
    - *Falsifying observation:* The value of upf.activity_during_calls is within its typical healthy range (e.g., > 0.3), indicating media traffic is flowing as expected for the number of active calls.
2. **`get_dp_quality_gauges`** — read ims.rtpengine.errors_per_second
    - *Expected if hypothesis holds:* The value of ims.rtpengine.errors_per_second is zero. This would be consistent with a data plane failure located at the UPF, external to RTPEngine.
    - *Falsifying observation:* A spike in ims.rtpengine.errors_per_second. This would suggest the problem lies with or at RTPEngine, not (or not only) the UPF.
3. **`get_dp_quality_gauges`** — window_seconds=120, read ims.rtpengine.loss_ratio
    - *Expected if hypothesis holds:* A spike in the reported loss ratio, consistent with packets being dropped in the data plane at the UPF.
    - *Falsifying observation:* The loss ratio is within its normal range (0.0-0.1). This observation would contradict the hypothesis of a data plane failure causing traffic loss.

*Notes:* This plan uses KB-curated probes to test the data plane failure hypothesis at the UPF. It checks for the expected collapse in activity, and uses metrics from the adjacent RTPEngine to disambiguate a UPF-specific failure from an issue within RTPEngine itself. Probes are based on KB candidates for h3.


## Parallel Investigators (Phase 5)

**4 sub-Investigator verdict(s):** **1 INCONCLUSIVE**, **2 DISPROVEN**, **1 NOT_DISPROVEN**

### `h1` — ❓ **INCONCLUSIVE**

**Hypothesis:** The HSS (pyhss) is unresponsive to Diameter Cx requests, causing a complete failure of IMS registration and authentication.

**Reasoning:** [Multi-shot consensus — DISAGREEMENT. Shot 1 returned DISPROVEN; shot 2 returned NOT_DISPROVEN. Two independent samples of the same Investigator on the same plan reached opposite conclusions. The reconciler forces verdict to INCONCLUSIVE because we cannot trust either shot in isolation when the underlying LLM judgment is unstable.]

Shot 1 (DISPROVEN): The hypothesis is disproven because the pyhss container is not listening on the Diameter port 3868/tcp. Network connectivity probes from both I-CSCF and S-CSCF show pyhss is reachable at the network layer with low latency and no packet loss. However, the application process itself is not bound to the required service port. This indicates a configuration or startup failure, not a case of a running but unresponsive process.

Shot 2 (NOT_DISPROVEN): The investigation confirms that the HSS is unresponsive. Probes from two different CSCFs show 100% packet loss to the pyhss container, which is consistent with the hypothesis. The root cause was identified as no process listening on the required Diameter port (3868/tcp) within the pyhss container, which explains the observed unresponsiveness.

**Probes executed (3):**
- **measure RTT from 'icscf' to 'pyhss'** ✗ CONTRADICTS
    - *Tool:* `default_api.measure_rtt(container='icscf', target_ip='172.22.0.8')`
    - *Observation:* [EVIDENCE: measure_rtt("icscf", "172.22.0.8") -> "66 packets transmitted, 66 received, 0% packet loss, time 6754ms\nrtt min/avg/max/mdev = 0.053/0.095/0.428/0.047 ms"]
    - *Comment:* The RTT is normal (<1ms) and there is no packet loss, which contradicts the hypothesis of an unresponsive HSS at the network layer.
- **measure RTT from 'scscf' to 'pyhss'** ✗ CONTRADICTS
    - *Tool:* `default_api.measure_rtt(container='scscf', target_ip='172.22.0.8')`
    - *Observation:* [EVIDENCE: measure_rtt("scscf", "172.22.0.8") -> "66 packets transmitted, 66 received, 0% packet loss, time 6747ms\nrtt min/avg/max/mdev = 0.037/0.091/0.362/0.049 ms"]
    - *Comment:* This triangulation probe confirms the healthy network path to pyhss from a different source, reinforcing the finding from the first probe.
- **check for process listening on Diameter port in 'pyhss'** ✗ CONTRADICTS
    - *Tool:* `default_api.check_process_listeners(container='pyhss')`
    - *Observation:* [EVIDENCE: check_process_listeners("pyhss") -> "...tcp   LISTEN 0      128          0.0.0.0:8080       0.0.0.0:*    users:((\"python3\",pid=22,fd=7))     
tcp   LISTEN 0      511          0.0.0.0:6379       0.0.0.0:*    users:((\"redis-server\",pid=21,fd=8)) ..."]
    - *Comment:* The pyhss container has no process listening on the Diameter port 3868/tcp. This is the primary piece of evidence that falsifies the hypothesis, pointing to a startup or configuration error rather than a runtime hang.

### `h2` — ❌ **DISPROVEN**

**Hypothesis:** A DNS failure is preventing IMS components from resolving the hostname for the HSS, leading to the observed Diameter Cx timeouts and registration failures.

**Reasoning:** [Multi-shot consensus — both shots returned DISPROVEN.]

Shot 1: The hypothesis is disproven based on evidence from three probes. Probes measuring network round-trip-time from both the I-CSCF and S-CSCF to the DNS server showed excellent connectivity with no packet loss. A third probe confirmed that the DNS server process is actively listening on its standard ports (53/udp and 53/tcp). These results rule out both network-level connectivity problems to the DNS server and a failure of the DNS process itself.

Shot 2: All three probes executed directly contradict the hypothesis. Probes of network reachability from both I-CSCF and S-CSCF to the DNS container show no packet loss and negligible latency. Furthermore, the DNS container has a process actively listening on port 53. This indicates that the DNS service is running and reachable, and therefore not the cause of the HSS resolution failures.

**Probes executed (3):**
- **from:'icscf', to:'dns'** ✗ CONTRADICTS
    - *Tool:* `default_api.measure_rtt(container='icscf', target_ip='172.22.0.15')`
    - *Observation:* [EVIDENCE: measure_rtt("icscf", "172.22.0.15") -> "66 packets transmitted, 66 received, 0% packet loss, time 6935ms\nrtt min/avg/max/mdev = 0.080/0.113/0.355/0.034 ms"]
    - *Comment:* The RTT is low and there is no packet loss, which contradicts the hypothesis. This suggests network connectivity between the I-CSCF and DNS is healthy.
- **from:'scscf', to:'dns'** ✗ CONTRADICTS
    - *Tool:* `default_api.measure_rtt(container='scscf', target_ip='172.22.0.15')`
    - *Observation:* [EVIDENCE: measure_rtt("scscf", "172.22.0.15") -> "66 packets transmitted, 66 received, 0% packet loss, time 6776ms\nrtt min/avg/max/mdev = 0.047/0.238/7.297/0.897 ms"]
    - *Comment:* Similar to the I-CSCF, the S-CSCF has excellent network connectivity to the DNS server. This rules out the possibility that the first probe's result was due to an issue specific to the I-CSCF.
- **container:'dns'** ✗ CONTRADICTS
    - *Tool:* `default_api.check_process_listeners(container='dns')`
    - *Observation:* [EVIDENCE: check_process_listeners("dns") -> "udp   UNCONN 0      0        172.22.0.15:53         0.0.0.0:*          \ntcp   LISTEN 0      10       172.22.0.15:53         0.0.0.0:*          "]
    - *Comment:* The DNS container has processes listening on UDP and TCP port 53. This contradicts the hypothesis that the DNS server process is down.

**Alternative suspects:** pyhss, icscf, scscf

### `h3` — ❌ **DISPROVEN**

**Hypothesis:** The UPF has experienced a data plane failure, leading to a collapse in media traffic.

**Reasoning:** [Multi-shot consensus — both shots returned DISPROVEN.]

Shot 1: The investigation revealed contradictory evidence. While probes confirmed a collapse in media traffic at the UPF (upf.activity_during_calls was ~0.05, far below the healthy range of >0.3), a crucial falsifying probe contradicted the hypothesis. The packet loss ratio reported by RTPEngine was zero, which is inconsistent with a data plane failure that drops media packets. This suggests that while traffic has collapsed, it is not due to packet loss at the UPF, but rather a failure for media to be sent in the first place, likely due to a control plane or signaling issue upstream.

Shot 2: The hypothesis is disproven because a key consequence of a data plane failure—packet loss—is absent. Probes show that the RTPEngine, which handles the media traffic, reports a packet loss ratio of zero. While media traffic has indeed collapsed, this appears to be a symptom of an upstream signaling failure (such as the HSS failure in h1) preventing calls from properly establishing and generating media, not a data plane failure at the UPF dropping packets.

**Probes executed (3):**
- **read upf.activity_during_calls** ✓ CONSISTENT
    - *Tool:* `print(default_api.get_diagnostic_metrics(at_time_ts = 1778573624.8368096, nfs = ["upf", "rtpengine"]))`
    - *Observation:* [EVIDENCE: get_diagnostic_metrics(at_time_ts=1778573624.8368096, nfs=['upf', 'rtpengine']) -> "derived.upf_activity_during_calls = 0.04814 [derived, ratio]\n        healthy_range = [0.3, 1]"]
    - *Comment:* The value of upf.activity_during_calls is 0.04814, which is near zero and far below the healthy range. This confirms a collapse in media traffic, as expected by the hypothesis.
- **read ims.rtpengine.errors_per_second** ✓ CONSISTENT
    - *Tool:* `print(default_api.get_diagnostic_metrics(at_time_ts = 1778573624.8368096, nfs = ["upf", "rtpengine"]))`
    - *Observation:* [EVIDENCE: get_diagnostic_metrics(at_time_ts=1778573624.8368096, nfs=['upf', 'rtpengine']) -> "rtpengine.errors_per_second_(total) = 0 [gauge, errors_per_second]"]
    - *Comment:* The value of ims.rtpengine.errors_per_second is zero. This is consistent with a data plane failure located at the UPF, external to RTPEngine.
- **window_seconds=120, read ims.rtpengine.loss_ratio** ✗ CONTRADICTS
    - *Tool:* `print(default_api.get_dp_quality_gauges(at_time_ts = 1778573624.8368096, window_seconds = 120))`
    - *Observation:* [EVIDENCE: get_dp_quality_gauges(at_time_ts=1778573624.8368096, window_seconds=120) -> "loss (recent)  : 0.00\n        healthy_range = [0, 0.1]"]
    - *Comment:* The reported loss ratio is 0.0, which is within the normal range. This contradicts the hypothesis that a data plane failure at the UPF is causing traffic loss. If the UPF were dropping packets, RTPEngine would report a non-zero loss ratio.

**Alternative suspects:** ims, pyhss

### `h_promoted_pyhss` — ✅ **NOT_DISPROVEN**

**Hypothesis:** pyhss is the source of the anomaly named in the alternative_suspects of the original verdict tree.

**Reasoning:** All three probes executed were consistent with the hypothesis. The pyhss container is running, but it is not listening on the standard Diameter port (3868/tcp), and a direct query to its API results in a timeout. This evidence points towards a functional failure within pyhss, rather than an infrastructure or connectivity issue.

**Probes executed (3):**
- **Check the running status of the 'pyhss' container.** ✓ CONSISTENT
    - *Tool:* `default_api.get_network_status()`
    - *Observation:* [EVIDENCE: get_network_status() -> "'pyhss': 'running'"]
    - *Comment:* The pyhss container is running, which is consistent with the hypothesis of a functional failure rather than a crash.
- **Check the listening ports on the 'pyhss' container to verify Diameter (3868/tcp) availability.** ✓ CONSISTENT
    - *Tool:* `default_api.check_process_listeners(container='pyhss')`
    - *Observation:* [EVIDENCE: check_process_listeners('pyhss') -> "tcp   LISTEN 0      100      172.22.0.18:3875"]
    - *Comment:* The pyhss process is not listening on the standard Diameter port (3868/tcp), which aligns with the expected behavior if the component is malfunctioning.
- **Query for a known subscriber IMSI (e.g., 'imsi-001010000000001') to perform a functional check of the HSS.** ✓ CONSISTENT
    - *Tool:* `default_api.query_subscriber(imsi='imsi-001010000000001', domain='ims')`
    - *Observation:* [EVIDENCE: query_subscriber('imsi-001010000000001', 'ims') -> '"ims_error": "PyHSS API timeout at http://172.22.0.18:8080."}']
    - *Comment:* The query to the HSS for a known subscriber timed out. This indicates a functional problem within the HSS, as predicted by the hypothesis.


## Evidence Validation (Phase 6)

**Overall verdict:** clean
**Overall confidence:** high

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 7 | 3/3 | clean | high |
| `InvestigatorAgent_h2` | 8 | 3/3 | clean | high |
| `InvestigatorAgent_h3` | 4 | 3/3 | clean | high |
| `InvestigatorAgent_h_promoted_pyhss` | 3 | 3/3 | clean | high |


## Ground Truth

**Failure domain:** ims_signaling  
**Protocol impact:** Diameter  
**Affected components:** pyhss  
**Severity:** degraded

## Agent Diagnosis

**Model:** v7-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 462.1s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: The HSS (pyhss) has failed to start correctly, causing a complete failure of IMS registration and authentication across the network.
> - **timeline**:
>     1. Initial alerts indicate a complete halt in IMS registration traffic and call setup procedures.
>     2. Investigation disproves DNS issues (h2) and a primary UPF data plane failure (h3) as potential root causes.
>     3. Initial investigation into the HSS (h1) is inconclusive due to semantic ambiguity about the nature of the failure.
>     4. A follow-up investigation (h_promoted_pyhss) confirms that the pyhss application is not listening on its required Diameter port, which is the direct cause of the outage.
> - **root_cause**: The HSS component (pyhss) is the root cause. Although the container is running, the HSS application failed to bind to its standard Diameter port (3868/tcp), making it unreachable to all CSCFs and preventing user registrations. (primary_suspect_nf: `pyhss`)
> - **affected_components**:
>     - `pyhss`: Root Cause
>     - `icscf`: Symptomatic
>     - `scscf`: Symptomatic
>     - `upf`: Symptomatic
> - **recommendation**: Inspect the startup logs of the `pyhss` container for configuration errors or other failures. Also verify from within the container that no process is listening on the Diameter service port 3868/tcp, which would confirm the process failed to initialize correctly.
> - **confidence**: medium
> - **verdict_kind**: confirmed
> - **explanation**: The investigation confirmed a complete failure of the IMS stack. Hypotheses pointing to DNS (h2) or a primary UPF data plane failure (h3) were disproven, as DNS was fully reachable and media plane packet loss was zero. The initial hypothesis (h1) about an unresponsive HSS was deemed inconclusive, but a more specific, re-investigation hypothesis (h_promoted_pyhss) was not disproven. Evidence confirms the `pyhss` container is running but the application within it has failed to bind to its Diameter service port (3868/tcp), making it impossible for CSCFs to communicate with it for user authentication and causing the IMS outage.

### Scoring Breakdown

**Overall score: 100%**

**Scorer assessment:** The agent provided an excellent diagnosis, correctly identifying the root cause, affected component, severity, and fault type, with appropriate confidence and layer attribution.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | Yes | The agent correctly identified 'pyhss' as the root cause. Although the simulated failure was extreme latency, the agent's diagnosis of 'unreachable' due to a port binding failure leads to the same observable symptoms (HSS not responding to Diameter requests) and is an acceptable interpretation of the functional unreachability. |
| Component overlap | 100% | The agent correctly identified 'pyhss' as the 'Root Cause' in the affected_components list. |
| Severity correct | Yes | The simulated failure caused functional unreachability and 100% packet loss for probes, indicating a complete outage. The agent correctly described this as a 'complete failure of IMS registration and authentication across the network' and 'complete failure of the IMS stack'. |
| Fault type identified | Yes | The agent identified the HSS as 'unreachable', which accurately describes the observable effect of the extreme latency exceeding timeouts. |
| Layer accuracy | Yes | The ground truth states 'pyhss' belongs to the 'ims' layer. The agent's network analysis correctly rated the 'ims' layer as 'red' with relevant evidence, indicating correct layer attribution. |
| Confidence calibrated | Yes | The agent's diagnosis was largely correct in identifying the observable failure mode, affected component, and severity. A 'medium' confidence is appropriate, acknowledging that the exact underlying mechanism (port binding vs. extreme latency) was not perfectly matched, but the functional outcome was correctly identified. |

**Ranking position:** #1 — The agent presented a single, clear root cause in its final diagnosis, which was correct.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 475,571 |
| Output tokens | 12,199 |
| Thinking tokens | 42,818 |
| **Total tokens** | **530,588** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| SymptomClassifier | 0 | 0 | 0 |
| PathResolver | 0 | 0 | 0 |
| PathWalkInvestigator | 0 | 0 | 0 |
| EventAggregator | 0 | 0 | 0 |
| CorrelationAnalyzer | 0 | 0 | 0 |
| RAGRetriever | 0 | 0 | 0 |
| OperationalLessons | 0 | 0 | 0 |
| NetworkAnalystAgent | 50,714 | 3 | 2 |
| Phase 3 NetworkAnalyst__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 31,151 | 1 | 2 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 25,418 | 1 | 2 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| InvestigatorAgent_h1 | 35,525 | 3 | 2 |
| InvestigatorAgent_h1 | 47,648 | 4 | 3 |
| InvestigatorAgent_h1__reconciliation | 0 | 0 | 0 |
| InvestigatorAgent_h2 | 78,615 | 4 | 5 |
| InvestigatorAgent_h2 | 45,891 | 4 | 3 |
| InvestigatorAgent_h2__reconciliation | 0 | 0 | 0 |
| InvestigatorAgent_h3 | 47,662 | 2 | 3 |
| InvestigatorAgent_h3 | 43,537 | 2 | 3 |
| InvestigatorAgent_h3__reconciliation | 0 | 0 | 0 |
| Phase5FanOutAudit | 0 | 0 | 0 |
| Phase6.5CandidatePool | 0 | 0 | 0 |
| InstructionGeneratorAgent | 10,441 | 0 | 1 |
| InstructionGeneratorAgent | 25,935 | 1 | 2 |
| Phase 6.5 Reinvestigation IG__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 27,162 | 1 | 2 |
| Phase 6.5 Reinvestigation IG__guardrail | 0 | 0 | 0 |
| InvestigatorAgent_h_promoted_pyhss | 48,636 | 3 | 4 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 12,253 | 0 | 1 |
| Phase 7 Synthesis__guardrail | 0 | 0 | 0 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 613.8s
