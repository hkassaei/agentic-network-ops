# Episode Report: Data Plane Degradation

**Agent:** v7  
**Episode ID:** ep_20260514_215421_data_plane_degradation  
**Date:** 2026-05-14T21:54:22.561324+00:00  
**Duration:** 446.6s  

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

- **Propagation window:** 124s (ObservationTrafficAgent drove traffic for this window; verifier added wait=0s on top)
- **Nodes with significant deltas:** 6
- **Nodes with any drift:** 6

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 37.54 (per-bucket threshold: 11.07, context bucket (0, 0), trained on 323 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following metrics deviate from their learned-healthy baseline. Treat each as a semantic observation (meaning + numbers), not a number alone — the KB's interpretation is the authoritative reading.

- **`context.cx_active`** — current **1.00** vs learned baseline **0.59** (MEDIUM, spike). *(No KB context available — interpret from the metric name.)*

- **`derived.rtpengine_loss_ratio`** (RTPEngine RTCP-reported per-RR average packet loss) — current **32.10 packets_per_rr** vs learned baseline **0.00 packets_per_rr** (MEDIUM, spike)
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

- **`normalized.icscf.cdp_replies_per_ue`** (I-CSCF Diameter reply rate per UE) — current **0.01 replies_per_second_per_ue** vs learned baseline **0.03 replies_per_second_per_ue** (MEDIUM, drop)
    - **What it measures:** Liveness of the I-CSCF↔HSS Cx path. Drops to 0 when HSS is unreachable OR when no signaling is occurring at the I-CSCF (idle or upstream P-CSCF partitioned).
    - **Drop means:** No Cx replies in the window. Could be healthy idle OR a Cx-path fault.
    - **Healthy typical range:** 0–1 replies_per_second_per_ue

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

- **`normalized.smf.bearers_per_ue`** (Active QoS bearers per UE) — current **3.50 count** vs learned baseline **2.48 count** (MEDIUM, shift)
    - **What it measures:** Per-UE count of active QoS bearers. Baseline reflects default
bearers; increments during VoNR calls indicate dedicated voice
bearers being set up. Drop during an active call = dedicated
bearer torn down unexpectedly (voice will fail).
    - **Shift means:** Expected during VoNR calls (1 extra bearer per active call).
    - **Healthy typical range:** 2–3.5 count
    - **Healthy invariant:** At rest: equals configured default bearers (typically 2 per UE).
During active VoNR call: +1 per caller. The per-UE ratio is the
invariant; absolute count scales with UE pool.

- **`normalized.upf.gtp_indatapktn3upf_per_ue`** (GTP-U uplink rate per UE (N3)) — current **3.77 packets_per_second** vs learned baseline **1.45 packets_per_second** (MEDIUM, spike)
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

- **`normalized.upf.gtp_outdatapktn3upf_per_ue`** (GTP-U downlink rate per UE (N3)) — current **2.54 packets_per_second** vs learned baseline **1.45 packets_per_second** (LOW, spike)
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


## Symptom Classifier (Phase 0.5)

**Label:** `mixed`  
**Flag counts:** transport=3, application=1, ambiguous=5

### Transport-bucket flags (3)

| Metric | Direction | Score | KB-driven reason |
|---|---|---:|---|
| `derived.rtpengine_loss_ratio` | spike | 4.25 | KB-labeled transport: ims.rtpengine.loss_ratio (spike, score=4.25) |
| `normalized.upf.gtp_indatapktn3upf_per_ue` | spike | 4.25 | KB-labeled transport: core.upf.gtp_indatapktn3upf_per_ue (spike, score=4.25) |
| `normalized.upf.gtp_outdatapktn3upf_per_ue` | spike | 3.56 | KB-labeled transport: core.upf.gtp_outdatapktn3upf_per_ue (spike, score=3.56) |

### Application-bucket flags (1)

| Metric | Direction | Score | KB-driven reason |
|---|---|---:|---|
| `normalized.smf.bearers_per_ue` | shift | 4.25 | KB-labeled application: core.smf.bearers_per_ue (shift, score=4.25) |

### Ambiguous-bucket flags (5)

| Metric | Direction | Score | KB-driven reason |
|---|---|---:|---|
| `context.cx_active` | spike | 4.25 | no KB entry for context.cx_active — classification ambiguous |
| `normalized.icscf.cdp_replies_per_ue` | drop | 4.25 | KB-labeled mixed: ims.icscf.cdp_replies_per_ue (drop, score=4.25) |
| `normalized.icscf.core:rcv_requests_invite_per_ue` | spike | 4.25 | KB-labeled mixed: ims.icscf.rcv_requests_invite_per_ue (spike, score=4.25) |
| `normalized.pcscf.core:rcv_requests_invite_per_ue` | spike | 4.25 | KB-labeled mixed: ims.pcscf.rcv_requests_invite_per_ue (spike, score=4.25) |
| `normalized.scscf.core:rcv_requests_invite_per_ue` | spike | 4.25 | KB-labeled mixed: ims.scscf.rcv_requests_invite_per_ue (spike, score=4.25) |

**Rationale:**

```
label=mixed. Both transport-layer (3) and application-layer (1) signals are load-bearing. Path walk runs first; falls through to the application-layer pipeline if the walk produces null localization.

Transport signals: derived.rtpengine_loss_ratio (spike, score=4.25) — KB-labeled transport: ims.rtpengine.loss_ratio (spike, score=4.25); normalized.upf.gtp_indatapktn3upf_per_ue (spike, score=4.25) — KB-labeled transport: core.upf.gtp_indatapktn3upf_per_ue (spike, score=4.25); normalized.upf.gtp_outdatapktn3upf_per_ue (spike, score=3.56) — KB-labeled transport: core.upf.gtp_outdatapktn3upf_per_ue (spike, score=3.56)

Application signals: normalized.smf.bearers_per_ue (shift, score=4.25) — KB-labeled application: core.smf.bearers_per_ue (shift, score=4.25)

Ambiguous signals: context.cx_active (spike, score=4.25) — no KB entry for context.cx_active — classification ambiguous; normalized.icscf.cdp_replies_per_ue (drop, score=4.25) — KB-labeled mixed: ims.icscf.cdp_replies_per_ue (drop, score=4.25); normalized.icscf.core:rcv_requests_invite_per_ue (spike, score=4.25) — KB-labeled mixed: ims.icscf.rcv_requests_invite_per_ue (spike, score=4.25); normalized.pcscf.core:rcv_requests_invite_per_ue (spike, score=4.25) — KB-labeled mixed: ims.pcscf.rcv_requests_invite_per_ue (spike, score=4.25); normalized.scscf.core:rcv_requests_invite_per_ue (spike, score=4.25) — KB-labeled mixed: ims.scscf.rcv_requests_invite_per_ue (spike, score=4.25)
```

## Transport-Layer Route (Phase 0.6)

### Resolver

**Flow:** `vonr_media` (VoNR Media Path)  
**Direction:** both  
**Hop count:** 13

**Candidates considered:**

| Flow | Score |
|---|---:|
| `vonr_media` ← chosen | 19 |
| `data_pdu_session_user_traffic` | 12 |
| `vonr_call_teardown` | 10 |
| `vonr_call_setup` | 10 |
| `ims_registration` | 8 |

**Rationale:**

```
Resolved transport path to flow `vonr_media` (score=19, 13 hops on the walk). Load-bearing components: ['context', 'icscf', 'pcscf', 'rtpengine', 'scscf', 'smf', 'upf']. Other candidate flows considered: data_pdu_session_user_traffic=12, vonr_call_teardown=10, vonr_call_setup=10, ims_registration=8.
```

### Walker

**Status:** ✅ **localized**
**First attributed hop:** `?[?]`
**Window:** 5s  
**Walked flow:** `vonr_media`

**Per-hop results:**

| # | Node | Kind | Iface | Attribution | Detail |
|---:|---|---|---|---|---|
| 0 | `e2e_ue1` | container | `eth0` | `clean` | _clean_ |
| 1 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 2 | `nr_gnb` | container | `eth0` | `clean` | _clean_ |
| 3 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 4 | `upf` | container | `eth0` | `drops_attributed_here` | `qdisc_netem`: 317 dropped, 38.1% |
| 5 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 6 | `rtpengine` | container | `eth0` | `clean` | _clean_ |
| 7 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 8 | `upf` | container | `eth0` | `drops_attributed_here` | `qdisc_netem`: 321 dropped, 38.5% |
| 9 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 10 | `nr_gnb` | container | `eth0` | `clean` | _clean_ |
| 11 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 12 | `e2e_ue2` | container | `eth0` | `clean` | _clean_ |

### Localized Synthesis

**Verdict:** `inconclusive`  
**Primary suspect NF:** `None`  
**Confidence:** low

**Summary:** Per-episode token budget exceeded for `mixed`-labeled run: 458238 > 200000. Synthesis short-circuited to inconclusive. Partial evidence from walker AND application-layer pipeline is in the episode log; review manually.

**Recommendation:** Manual investigation required.


## Event Aggregation (Phase 1)

No events fired during this episode. Either no metric KB triggers matched, or the episode encountered no meaningful state transitions.

## Correlation Analysis (Phase 2)

No events fired — correlation engine had nothing to work with.

## RAG & Operational Lessons (Phase 2.5)

### RAG retrieval — prior similar episodes

**Status:** `hits` — hits=5, top_sim=0.80, top_case=v7/ep_20260510_183211_data_plane_degradation
**Index:** `/home/ehoskas/agentic-network-ops/rag_index`  **Corpus size:** 97 cases
**Classifier label used in retrieval:** `mixed`
**Retrieval params:** k=5, min_similarity=0.4
**Hits (5):**

| Rank | Sim | Case ID | Scenario | Ground truth | Primary suspect | Score |
|---:|---:|---|---|---|---|---:|
| 0 | 80% | `v7/ep_20260510_183211_data_plane_degradation` | Data Plane Degradation | `upf` | `upf` | 100% |
| 1 | 79% | `v6/ep_20260429_162423_data_plane_degradation` | Data Plane Degradation | `upf` | `?` | 85% |
| 2 | 79% | `v6/ep_20260430_014832_hss_unresponsive` | HSS Unresponsive | `pyhss` | `?` | 95% |
| 3 | 78% | `v7/ep_20260510_194005_dns_failure` | DNS Failure | `dns` | `?` | 85% |
| 4 | 78% | `v7/ep_20260510_115059_data_plane_degradation` | Data Plane Degradation | `upf` | `upf` | 100% |

*Rendered block injected into the NA prompt's `{prior_similar_episodes}` placeholder: 4542 chars. Source paths are inlined in the block so the EvidenceValidator can audit any case the NA cites.*

### Operational lessons — hand-authored rules corpus

**Status:** `injected` — lessons=15, chars=14426
**Path:** `/home/ehoskas/agentic-network-ops/agentic_ops_common/rag/lessons.yaml`  **Count:** 15  **Block size:** 14426 chars
**Injected lesson IDs:** `L01`, `L02`, `L03`, `L04`, `L05`, `L06`, `L07`, `L08`, `L09`, `L10`, `L11`, `L12`, `L13`, `L14`, `L15`

### NA citations of the injected content

**No verbatim citations.** The NA's output text did not reference any retrieved case_id or any injected lesson_id verbatim. This does NOT prove the NA ignored the injected content — the model may have absorbed the patterns implicitly — but it does mean no audit trail links the NA's reasoning back to a specific case or lesson.

## Network Analysis (Phase 3)

**Summary:** The network experienced a transient data plane failure causing media packet loss, evidenced by a spike in rtpengine's loss ratio. The symptoms and prior cases strongly point to the UPF as the root cause.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | Network status and topology probes show all relevant containers and links are up. |
| **ran** | 🟢 GREEN | No direct evidence suggests a RAN failure. |
| **core** | 🔴 RED | The core data plane is the primary suspect. The `rtpengine_loss_ratio` spike is a direct indicator of media packet loss, and several prior similar episodes point to the UPF as the ground truth. UPF's own GTP metrics were also anomalous. |
| **ims** | 🟡 YELLOW | The IMS signaling plane shows signs of call setup failure, likely as a downstream consequence of the data plane instability. The pattern of INVITE request spikes suggests failing retry attempts. |

**CORE evidence:**
- derived.rtpengine_loss_ratio:spike:MEDIUM
- normalized.upf.gtp_indatapktn3upf_per_ue:spike:MEDIUM
- normalized.upf.gtp_outdatapktn3upf_per_ue:spike:LOW

**IMS evidence:**
- normalized.icscf.core:rcv_requests_invite_per_ue:spike:MEDIUM
- normalized.pcscf.core:rcv_requests_invite_per_ue:spike:MEDIUM
- normalized.scscf.core:rcv_requests_invite_per_ue:spike:MEDIUM
- normalized.icscf.cdp_replies_per_ue:drop:MEDIUM

**Ranked hypotheses:**

- **`h1`** (fit=0.90, nf=upf, specificity=specific):
    - **Statement:** The UPF is the source of data plane degradation, resulting in significant media packet loss.
    - **Supporting events:** `derived.rtpengine_loss_ratio:spike:MEDIUM`, `normalized.upf.gtp_indatapktn3upf_per_ue:spike:MEDIUM`, `normalized.upf.gtp_outdatapktn3upf_per_ue:spike:LOW`
    - **Falsification probes:**
        - Run `measure_rtt` from `rtpengine` to `upf` to check for packet loss or high latency on the N6 media path.
        - Inspect UPF-internal kernel/qdisc drop counters and logs for evidence of packet drops.
- **`h2`** (fit=0.70, nf=rtpengine, specificity=specific):
    - **Statement:** The RTPEngine is the source of the data plane degradation, dropping packets on its egress.
    - **Supporting events:** `derived.rtpengine_loss_ratio:spike:MEDIUM`
    - **Falsification probes:**
        - Probe `rtpengine`'s egress network interface for kernel-level packet drops (e.g., using `tc -s qdisc show`).
        - If the `rtpengine` to `upf` path is clean via `measure_rtt`, it would suggest the loss occurs elsewhere, weakening this hypothesis.
- **`h3`** (fit=0.40, nf=pyhss, specificity=moderate):
    - **Statement:** The HSS is unresponsive, causing downstream call setup failures across the IMS.
    - **Supporting events:** `normalized.icscf.cdp_replies_per_ue:drop:MEDIUM`, `normalized.icscf.core:rcv_requests_invite_per_ue:spike:MEDIUM`, `normalized.pcscf.core:rcv_requests_invite_per_ue:spike:MEDIUM`, `context.cx_active:spike:MEDIUM`
    - **Falsification probes:**
        - Run `measure_rtt` from `icscf` to `pyhss` to check for latency or loss on the Cx interface.
        - Check `pyhss` container logs for Diameter errors or timeouts.


## Falsification Plans (Phase 4)

**3 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `upf`)

**Hypothesis:** The UPF is the source of data plane degradation, resulting in significant media packet loss.

**Probes (3):**
1. **`measure_rtt`** — From rtpengine to the suspect upf, to test the N6 media path.
    - *Expected if hypothesis holds:* High latency or packet loss is observed.
    - *Falsifying observation:* No significant latency or packet loss is observed.
2. **`measure_rtt`** — From rtpengine to the smf, to create a baseline for the network path.
    - *Expected if hypothesis holds:* No significant latency or packet loss is observed, suggesting the issue is specific to the UPF and not the general network path from rtpengine.
    - *Falsifying observation:* High latency or packet loss is observed, suggesting a broader network issue rather than a UPF-specific one, weakening the hypothesis.
3. **`get_dp_quality_gauges`** — Check UPF's accounting of GTP packets on N3 uplink and downlink over a 120s window.
    - *Expected if hypothesis holds:* A deviation in `upf.gtp_indatapktn3upf_per_ue` or `upf.gtp_outdatapktn3upf_per_ue` is observed, such as a drop or zero value, corresponding to the packet loss.
    - *Falsifying observation:* Both `upf.gtp_indatapktn3upf_per_ue` and `upf.gtp_outdatapktn3upf_per_ue` are within their typical healthy range.

*Notes:* This plan uses a paired-probe approach (measure_rtt) to distinguish between a faulty UPF and a faulty network path between the media anchor (rtpengine) and the UPF. It adds a direct metric check on the UPF's own counters as a third, non-compositional data point.

### Plan for `h2` (target: `rtpengine`)

**Hypothesis:** The RTPEngine is the source of the data plane degradation, dropping packets on its egress.

**Probes (3):**
1. **`get_dp_quality_gauges`** — Check for errors reported by rtpengine's relay over a 120s window.
    - *Expected if hypothesis holds:* A spike is observed in the `rtpengine.errors_per_second` metric.
    - *Falsifying observation:* The `rtpengine.errors_per_second` metric remains at its healthy baseline of zero.
2. **`measure_rtt`** — From upf to the suspect rtpengine, to test the N6 media path.
    - *Expected if hypothesis holds:* High latency or packet loss is observed.
    - *Falsifying observation:* No significant latency or packet loss is observed.
3. **`measure_rtt`** — From upf to the smf, to create a baseline for the network path.
    - *Expected if hypothesis holds:* No significant latency or packet loss is observed, suggesting the issue is specific to rtpengine and not the general network path from upf.
    - *Falsifying observation:* High latency or packet loss is observed, suggesting a broader network issue rather than an rtpengine-specific one.

*Notes:* This plan first checks for direct evidence of rtpengine-internal errors. It then uses a paired-probe approach (measure_rtt) to test the network path to rtpengine, separating path-level problems from issues at the rtpengine container itself.

### Plan for `h3` (target: `pyhss`)

**Hypothesis:** The HSS is unresponsive, causing downstream call setup failures across the IMS.

**Probes (3):**
1. **`query_subscriber`** — Query for a known test subscriber IMSI (e.g., 'imsi-001010000000001') to check HSS responsiveness to Diameter requests.
    - *Expected if hypothesis holds:* The query times out or returns an error.
    - *Falsifying observation:* The query returns a valid subscriber profile successfully and quickly.
2. **`measure_rtt`** — From icscf to the suspect pyhss, to test the Cx interface path.
    - *Expected if hypothesis holds:* High latency or packet loss is observed.
    - *Falsifying observation:* No significant latency or packet loss is observed.
3. **`measure_rtt`** — From icscf to the scscf, to create a baseline for the IMS network.
    - *Expected if hypothesis holds:* No significant latency or packet loss is observed, suggesting the issue is specific to pyhss and not the general network path from icscf.
    - *Falsifying observation:* High latency or packet loss is observed, suggesting a broader IMS network issue rather than a pyhss-specific one.

*Notes:* This plan tests the HSS at two layers: an application-level query to check the Diameter service, and a paired network-level probe (measure_rtt) to isolate network path issues from container-level unresponsiveness on the Cx interface. This covers the 'no KB candidates' gap for this hypothesis.


## Parallel Investigators (Phase 5)

**3 sub-Investigator verdict(s):** **1 NOT_DISPROVEN**, **2 DISPROVEN**

### `h1` — ✅ **NOT_DISPROVEN**

**Hypothesis:** The UPF is the source of data plane degradation, resulting in significant media packet loss.

**Reasoning:** [Multi-shot consensus — both shots returned NOT_DISPROVEN.]

Shot 1: All executed probes returned evidence consistent with the hypothesis. The paired transport probes (`measure_rtt`) successfully isolated the fault to the UPF. The probe from `rtpengine` to `upf` showed significant packet loss, while the baseline probe from `rtpengine` to `smf` was clean. This strongly suggests the issue is not with the general network path but is specific to the UPF. Furthermore, data plane quality gauges from the time of the incident confirm a high media loss ratio was observed.

Shot 2: All three probes executed returned results consistent with the hypothesis. The paired `measure_rtt` probes from `rtpengine` to both `upf` and `smf` successfully isolated the observed packet loss to the `upf` component, as the path to `smf` was clean while the path to `upf` was not. This was corroborated by `get_dp_quality_gauges`, which showed a high media loss ratio at `rtpengine` and an imbalance in the UPF's own packet counters during the anomaly window.

**Probes executed (3):**
- **From rtpengine to the suspect upf, to test the N6 media path.** ✓ CONSISTENT
    - *Tool:* `print(default_api.measure_rtt(container = "rtpengine", target = "upf"))`
    - *Observation:* [EVIDENCE: measure_rtt("rtpengine", "upf") -> "66 packets transmitted, 41 received, 37.8788% packet loss"]
    - *Comment:* This probe found significant packet loss (37.88%) on the path between the rtpengine and the UPF, which is consistent with the hypothesis of data plane degradation.
- **From rtpengine to the smf, to create a baseline for the network path.** ✓ CONSISTENT
    - *Tool:* `print(default_api.measure_rtt(container = "rtpengine", target = "smf"))`
    - *Observation:* [EVIDENCE: measure_rtt("rtpengine", "smf") -> "66 packets transmitted, 66 received, 0% packet loss"]
    - *Comment:* This probe found 0% packet loss on the path from rtpengine to the SMF. Since this path is clean while the path to the UPF is not, it isolates the fault to the UPF or its immediate network vicinity, ruling out a broader network issue originating from the rtpengine side.
- **Check UPF's accounting of GTP packets on N3 uplink and downlink over a 120s window.** ✓ CONSISTENT
    - *Tool:* `print(default_api.get_dp_quality_gauges(at_time_ts = 1778795780.09069, window_seconds = 120))`
    - *Observation:* [EVIDENCE: get_dp_quality_gauges(at_time_ts=1778795780.09069, window_seconds=120) -> "RTPEngine:\n    loss (recent)  : 32.47"]
    - *Comment:* The data plane quality gauges from the time of the incident show a very high packet loss ratio (32.47) reported by rtpengine, confirming the symptom described in the hypothesis. While the UPF's own counters are not conclusive in isolation, the confirmation of high media loss aligns with the hypothesis.

### `h2` — ❌ **DISPROVEN**

**Hypothesis:** The RTPEngine is the source of the data plane degradation, dropping packets on its egress.

**Reasoning:** [Multi-shot consensus — both shots returned DISPROVEN.]

Shot 1: The hypothesis is disproven by two key findings. First, the `rtpengine.errors_per_second` metric was zero, which contradicts the idea of rtpengine-internal drops. Second, a triangulation using `measure_rtt` showed that the UPF experiences high packet loss to both the rtpengine and the smf, pointing to the UPF as the common point of failure rather than rtpengine.

Shot 2: The investigation revealed significant packet loss on the network path from the UPF to both the RTPEngine (16.7%) and the SMF (42.4%). While the high loss reported by RTPEngine is consistent with the hypothesis, the fact that a baseline path from the same origin (UPF) to a different destination (SMF) is also severely degraded contradicts the claim that RTPEngine is the source. The evidence points to a broader problem originating at the UPF, as it is the common element in both failing paths.

**Probes executed (3):**
- **Check for errors reported by rtpengine's relay over a 120s window.** ✗ CONTRADICTS
    - *Tool:* `default_api.get_diagnostic_metrics(at_time_ts=1778795780.09069, nfs=['rtpengine'])`
    - *Observation:* [EVIDENCE: get_diagnostic_metrics(at_time_ts=1778795780.09069, nfs=['rtpengine']) -> "rtpengine.errors_per_second_(total) = 0 [gauge, errors_per_second]"]
    - *Comment:* The absence of errors reported by the rtpengine relay directly contradicts the hypothesis that it is the source of the packet loss. The loss must be occurring outside the relay's logic.
- **From upf to the suspect rtpengine, to test the N6 media path.** ✓ CONSISTENT
    - *Tool:* `default_api.measure_rtt(container='upf', target='rtpengine')`
    - *Observation:* [EVIDENCE: measure_rtt('upf', 'rtpengine') -> "66 packets transmitted, 47 received, 28.7879% packet loss"]
    - *Comment:* High packet loss was observed on the path from UPF to RTPEngine. While consistent with the hypothesis, this result is ambiguous and could be caused by the network path or the UPF itself.
- **From upf to the smf, to create a baseline for the network path.** ✗ CONTRADICTS
    - *Tool:* `default_api.measure_rtt(container='upf', target='smf')`
    - *Observation:* [EVIDENCE: measure_rtt('upf', 'smf') -> "66 packets transmitted, 42 received, 36.3636% packet loss"]
    - *Comment:* This probe revealed high packet loss from the UPF to an unrelated component (SMF). This indicates the problem is not specific to rtpengine but likely originates from the UPF, as it's the common element in both failing paths. This disproves the hypothesis.

**Alternative suspects:** upf

### `h3` — ❌ **DISPROVEN**

**Hypothesis:** The HSS is unresponsive, causing downstream call setup failures across the IMS.

**Reasoning:** [Multi-shot consensus — both shots returned DISPROVEN.]

Shot 1: The hypothesis is that the HSS is unresponsive. Probes directly contradict this. A network probe from the I-CSCF to the HSS (pyhss) showed a perfectly healthy path with 0% packet loss and sub-millisecond latency. Furthermore, an application-level query to the HSS was successful, returning a response that the subscriber was not found; while not a successful profile lookup, this is a valid response and not a timeout or error, proving the HSS application itself is responsive. The issue is not HSS unresponsiveness.

Shot 2: The hypothesis is disproven because direct network probes show the HSS is responsive. The measure_rtt probe from icscf to pyhss showed 0% packet loss and extremely low latency (average 0.071ms), which directly contradicts the expectation of high latency or packet loss. A baseline RTT check to scscf confirmed the local network is healthy. While a subscriber query did not return a user profile, it did return a response ('subscriber not found'), further showing the HSS application is responsive, even if the specific test user was not provisioned.

**Probes executed (3):**
- **Query for a known test subscriber IMSI (e.g., 'imsi-001010000000001') to check HSS responsiveness to Diameter requests.** ✗ CONTRADICTS
    - *Tool:* `query_subscriber(imsi='imsi-001010000000001')`
    - *Observation:* [EVIDENCE: query_subscriber('imsi-001010000000001') -> '{"core_5g": null, "core_5g_note": "Subscriber imsi-001010000000001 NOT FOUND in Open5GS MongoDB. This means the UE cannot attach to the 5G core.", "ims_subscriber": null}']
    - *Comment:* The HSS responded successfully, indicating it is not unresponsive. The response was that the subscriber was not found, which contradicts the hypothesis of unresponsiveness, which would have resulted in a timeout or error.
- **From icscf to the suspect pyhss, to test the Cx interface path.** ✗ CONTRADICTS
    - *Tool:* `measure_rtt(container='icscf', target='pyhss')`
    - *Observation:* [EVIDENCE: measure_rtt('icscf', 'pyhss') -> '66 packets transmitted, 66 received, 0% packet loss, time 6771ms\nrtt min/avg/max/mdev = 0.047/0.074/0.130/0.018 ms']
    - *Comment:* The network path from the I-CSCF to the HSS is extremely healthy, with no packet loss and very low latency. This falsifies the idea that the HSS is unresponsive at the network layer.
- **From icscf to the scscf, to create a baseline for the IMS network.** ✓ CONSISTENT
    - *Tool:* `measure_rtt(container='icscf', target='scscf')`
    - *Observation:* [EVIDENCE: measure_rtt('icscf', 'scscf') -> '66 packets transmitted, 66 received, 0% packet loss, time 6798ms\nrtt min/avg/max/mdev = 0.038/0.077/0.254/0.026 ms']
    - *Comment:* The network path from the I-CSCF to the S-CSCF is also healthy, confirming there is no general network issue from the I-CSCF's perspective. This reinforces the conclusion that the path to the HSS is not the problem.


## Evidence Validation (Phase 6)

**Overall verdict:** clean
**Overall confidence:** high

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 6 | 3/3 | clean | high |
| `InvestigatorAgent_h2` | 7 | 3/3 | clean | high |
| `InvestigatorAgent_h3` | 6 | 3/3 | clean | high |


## Ground Truth

**Failure domain:** data_plane  
**Protocol impact:** GTP-U  
**Affected components:** upf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v7-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 311.1s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: Per-episode token budget exceeded for `mixed`-labeled run: 458238 > 200000. Synthesis short-circuited to inconclusive. Partial evidence from walker AND application-layer pipeline is in the episode log; review manually.
> - **timeline**: []
> - **root_cause**: Synthesis sentinel — see summary
> - **affected_components**: []
> - **recommendation**: Manual investigation required.
> - **confidence**: low
> - **verdict_kind**: inconclusive
> - **explanation**: Per-episode token budget exceeded for `mixed`-labeled run: 458238 > 200000. Synthesis short-circuited to inconclusive. Partial evidence from walker AND application-layer pipeline is in the episode log; review manually.

### Scoring Breakdown

**Overall score: 15%**

**Scorer assessment:** The agent failed to provide a conclusive diagnosis due to an internal token budget issue, missing the root cause, affected components, severity, and fault type. However, its intermediate reasoning correctly identified the affected layer, and its low confidence for an inconclusive result was well-calibrated.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | No | The agent's final diagnosis explicitly states 'Synthesis short-circuited to inconclusive' and 'root_cause: Synthesis sentinel'. It did not identify the 30% packet loss on the UPF as the root cause. |
| Component overlap | 0% | The agent's final diagnosis lists an empty array for 'affected_components'. It did not identify the UPF. |
| Severity correct | No | The agent's final diagnosis is 'inconclusive' and does not state any severity. The simulated failure was a degradation (30% packet loss), which was not identified. |
| Fault type identified | No | The agent's final diagnosis is 'inconclusive' and does not identify 'packet loss' or 'degradation' as the fault type. |
| Layer accuracy | Yes | The 'NETWORK ANALYSIS' section correctly rates the 'core' layer as 'red' and provides evidence related to UPF GTP metrics and RTP loss, which aligns with the UPF (a core component) being the source of the failure. |
| Confidence calibrated | Yes | The agent's final diagnosis is 'inconclusive' with 'confidence: low', which is appropriate given its inability to provide a definitive root cause. |

**Ranking:** The agent's final diagnosis did not provide a ranked list of causes; it was inconclusive.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 422,098 |
| Output tokens | 9,711 |
| Thinking tokens | 26,429 |
| **Total tokens** | **458,238** |

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
| NetworkAnalystAgent | 52,171 | 3 | 2 |
| Phase 3 NetworkAnalyst__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 35,898 | 3 | 2 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 35,890 | 1 | 2 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| InvestigatorAgent_h1 | 31,993 | 3 | 2 |
| InvestigatorAgent_h1 | 67,615 | 3 | 4 |
| InvestigatorAgent_h1__reconciliation | 0 | 0 | 0 |
| InvestigatorAgent_h2 | 84,940 | 4 | 5 |
| InvestigatorAgent_h2 | 30,307 | 3 | 2 |
| InvestigatorAgent_h2__reconciliation | 0 | 0 | 0 |
| InvestigatorAgent_h3 | 59,655 | 3 | 4 |
| InvestigatorAgent_h3 | 59,769 | 3 | 4 |
| InvestigatorAgent_h3__reconciliation | 0 | 0 | 0 |
| Phase5FanOutAudit | 0 | 0 | 0 |
| Phase6.5CandidatePool | 0 | 0 | 0 |
| EvidenceValidator | 0 | 0 | 0 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 446.6s
