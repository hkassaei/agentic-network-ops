# Episode Report: Data Plane Degradation

**Agent:** v7  
**Episode ID:** ep_20260520_132808_data_plane_degradation  
**Date:** 2026-05-20T13:28:09.862251+00:00  
**Duration:** 654.8s  

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

- **Propagation window:** 126s (ObservationTrafficAgent drove traffic for this window; verifier added wait=0s on top)
- **Nodes with significant deltas:** 6
- **Nodes with any drift:** 6

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 46.56 (per-bucket threshold: 28.18, context bucket (1, 1), trained on 323 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following metrics deviate from their learned-healthy baseline. Treat each as a semantic observation (meaning + numbers), not a number alone — the KB's interpretation is the authoritative reading.

- **`derived.rtpengine_loss_ratio`** (RTPEngine RTCP-reported per-RR average packet loss) — current **53.38 packets_per_rr** vs learned baseline **0.00 packets_per_rr** (MEDIUM, spike)
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

- **`derived.upf_activity_during_calls`** (UPF activity consistency with active dialogs) — current **0.09 ratio** vs learned baseline **0.54 ratio** (MEDIUM, drop)
    - **What it measures:** Cross-layer consistency check between IMS dialog state and UPF
throughput. A drop while dialogs_per_ue is non-zero is a
smoking-gun signal for media-plane failure independent of signaling.
    - **Drop means:** Active calls reported but no media flowing — media path broken (UPF, RTPEngine, or N3 packet loss).
    - **Healthy typical range:** 0.3–1 ratio
    - **Healthy invariant:** 1.0 when traffic fully follows active calls; 0.0 when signaling says active but data plane is silent.

- **`normalized.icscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at I-CSCF) — current **0.14 requests_per_second** vs learned baseline **0.06 requests_per_second** (MEDIUM, spike)
    - **What it measures:** Health of the P-CSCF → I-CSCF forwarding path (Mw interface). When
this drops to zero while P-CSCF REGISTER rate is still non-zero,
it's the SIGNATURE of an IMS partition between P-CSCF and I-CSCF.
    - **Spike means:** Forwarding issue on the Mw interface, or P-CSCF stopped forwarding.
    - **Healthy typical range:** 0–0.5 requests_per_second
    - **Healthy invariant:** Per-UE rate. Should closely track ims.pcscf.rcv_requests_register_per_ue.

- **`normalized.pcscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at P-CSCF) — current **0.21 requests_per_second** vs learned baseline **0.06 requests_per_second** (MEDIUM, spike)
    - **What it measures:** How actively UEs are refreshing their IMS registrations with the
P-CSCF. REGISTERs arrive periodically (re-registration timer) plus
at attach. Sustained zero means UEs cannot reach P-CSCF OR the
UE-to-network SIP path is broken.
    - **Spike means:** Fewer REGISTERs than expected — UE connectivity or P-CSCF reachability issue.
    - **Healthy typical range:** 0–0.5 requests_per_second
    - **Healthy invariant:** Per-UE rate — same value at any deployment scale.

- **`normalized.scscf.cdp_replies_per_ue`** (S-CSCF CDP Diameter replies per UE) — current **0.14 replies_per_second_per_ue** vs learned baseline **0.06 replies_per_second_per_ue** (MEDIUM, spike)
    - **What it measures:** Active S-CSCF Diameter traffic with HSS. Near-zero when registrations idle OR HSS partition.
    - **Spike means:** Diameter peering loss with HSS.
    - **Healthy typical range:** 0–1 replies_per_second_per_ue
    - **Healthy invariant:** Per-UE rate; varies with registration/auth load.

- **`normalized.scscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at S-CSCF) — current **0.14 requests_per_second** vs learned baseline **0.06 requests_per_second** (MEDIUM, spike)
    - **What it measures:** Health of the I-CSCF → S-CSCF forwarding path. Drop to zero while
I-CSCF is receiving REGISTERs = S-CSCF-side issue (crashed, or
I-CSCF → S-CSCF path broken).
    - **Spike means:** I-CSCF not forwarding or S-CSCF not receiving.
    - **Healthy typical range:** 0–0.5 requests_per_second
    - **Healthy invariant:** Per-UE rate. Tracks icscf.register rate.

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

- **`normalized.upf.gtp_indatapktn3upf_per_ue`** (GTP-U uplink rate per UE (N3)) — current **5.35 packets_per_second** vs learned baseline **1.45 packets_per_second** (MEDIUM, spike)
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

- **`normalized.icscf.cdp_replies_per_ue`** (I-CSCF Diameter reply rate per UE) — current **0.06 replies_per_second_per_ue** vs learned baseline **0.03 replies_per_second_per_ue** (LOW, spike)
    - **What it measures:** Liveness of the I-CSCF↔HSS Cx path. Drops to 0 when HSS is unreachable OR when no signaling is occurring at the I-CSCF (idle or upstream P-CSCF partitioned).
    - **Spike means:** Either HSS is unreachable or upstream signaling has stopped reaching I-CSCF.
    - **Healthy typical range:** 0–1 replies_per_second_per_ue

- **`normalized.pcscf.core:rcv_requests_invite_per_ue`** (SIP INVITE rate per UE at P-CSCF) — current **0.03 requests_per_second** vs learned baseline **0.00 requests_per_second** (LOW, spike)
    - **What it measures:** Call attempt rate from registered UEs. Unlike REGISTER (periodic),
INVITEs only fire when UEs place calls. Zero is normal during
quiet periods; nonzero INVITE with zero dialogs is the signature
of call setup failure.
    - **Spike means:** Fewer call attempts.
    - **Healthy typical range:** 0–0.2 requests_per_second
    - **Healthy invariant:** Per-UE rate.


## Symptom Classifier (Phase 0.5)

**Label:** `mixed`  
**Flag counts:** transport=3, application=1, ambiguous=6

### Transport-bucket flags (3)

| Metric | Direction | Score | KB-driven reason |
|---|---|---:|---|
| `derived.rtpengine_loss_ratio` | spike | 4.28 | KB-labeled transport: ims.rtpengine.loss_ratio (spike, score=4.28) |
| `derived.upf_activity_during_calls` | drop | 4.28 | KB-labeled transport: core.upf.activity_during_calls (drop, score=4.28) |
| `normalized.upf.gtp_indatapktn3upf_per_ue` | spike | 4.28 | KB-labeled transport: core.upf.gtp_indatapktn3upf_per_ue (spike, score=4.28) |

### Application-bucket flags (1)

| Metric | Direction | Score | KB-driven reason |
|---|---|---:|---|
| `normalized.smf.bearers_per_ue` | shift | 4.28 | KB-labeled application: core.smf.bearers_per_ue (shift, score=4.28) |

### Ambiguous-bucket flags (6)

| Metric | Direction | Score | KB-driven reason |
|---|---|---:|---|
| `normalized.icscf.core:rcv_requests_register_per_ue` | spike | 4.28 | KB-labeled mixed: ims.icscf.rcv_requests_register_per_ue (spike, score=4.28) |
| `normalized.pcscf.core:rcv_requests_register_per_ue` | spike | 4.28 | KB-labeled mixed: ims.pcscf.rcv_requests_register_per_ue (spike, score=4.28) |
| `normalized.scscf.cdp_replies_per_ue` | spike | 4.28 | KB-labeled mixed: ims.scscf.cdp_replies_per_ue (spike, score=4.28) |
| `normalized.scscf.core:rcv_requests_register_per_ue` | spike | 4.28 | KB-labeled mixed: ims.scscf.rcv_requests_register_per_ue (spike, score=4.28) |
| `normalized.icscf.cdp_replies_per_ue` | spike | 3.58 | KB-labeled mixed: ims.icscf.cdp_replies_per_ue (spike, score=3.58) |
| `normalized.pcscf.core:rcv_requests_invite_per_ue` | spike | 2.48 | KB-labeled mixed: ims.pcscf.rcv_requests_invite_per_ue (spike, score=2.48) |

**Rationale:**

```
label=mixed. Both transport-layer (3) and application-layer (1) signals are load-bearing. Path walk runs first; falls through to the application-layer pipeline if the walk produces null localization.

Transport signals: derived.rtpengine_loss_ratio (spike, score=4.28) — KB-labeled transport: ims.rtpengine.loss_ratio (spike, score=4.28); derived.upf_activity_during_calls (drop, score=4.28) — KB-labeled transport: core.upf.activity_during_calls (drop, score=4.28); normalized.upf.gtp_indatapktn3upf_per_ue (spike, score=4.28) — KB-labeled transport: core.upf.gtp_indatapktn3upf_per_ue (spike, score=4.28)

Application signals: normalized.smf.bearers_per_ue (shift, score=4.28) — KB-labeled application: core.smf.bearers_per_ue (shift, score=4.28)

Ambiguous signals: normalized.icscf.core:rcv_requests_register_per_ue (spike, score=4.28) — KB-labeled mixed: ims.icscf.rcv_requests_register_per_ue (spike, score=4.28); normalized.pcscf.core:rcv_requests_register_per_ue (spike, score=4.28) — KB-labeled mixed: ims.pcscf.rcv_requests_register_per_ue (spike, score=4.28); normalized.scscf.cdp_replies_per_ue (spike, score=4.28) — KB-labeled mixed: ims.scscf.cdp_replies_per_ue (spike, score=4.28); normalized.scscf.core:rcv_requests_register_per_ue (spike, score=4.28) — KB-labeled mixed: ims.scscf.rcv_requests_register_per_ue (spike, score=4.28); normalized.icscf.cdp_replies_per_ue (spike, score=3.58) — KB-labeled mixed: ims.icscf.cdp_replies_per_ue (spike, score=3.58) [+1 more]
```

## Transport-Layer Route (Phase 0.6)

### Resolver

**Flow:** `vonr_media` (VoNR Media Path)  
**Direction:** both  
**Hop count:** 13

**Candidates considered:**

| Flow | Score |
|---|---:|
| `vonr_media` ← chosen | 14 |
| `vonr_call_teardown` | 10 |
| `vonr_call_setup` | 10 |
| `ims_registration` | 8 |
| `data_pdu_session_user_traffic` | 7 |

**Rationale:**

```
Resolved transport path to flow `vonr_media` (score=14, 13 hops on the walk). Load-bearing components: ['icscf', 'pcscf', 'rtpengine', 'scscf', 'smf', 'upf']. Other candidate flows considered: vonr_call_teardown=10, vonr_call_setup=10, ims_registration=8, data_pdu_session_user_traffic=7.
```

### Walker

**Status:** ✅ **localized**
**First attributed hop:** `upf[eth0]`
**Window:** 5s  
**Walked flow:** `vonr_media`

**Per-hop results:**

| # | Node | Kind | Iface | Attribution | Detail |
|---:|---|---|---|---|---|
| 0 | `e2e_ue1` | container | `eth0` | `clean` | _clean_ |
| 1 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 2 | `nr_gnb` | container | `eth0` | `clean` | _clean_ |
| 3 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 4 | 🎯 `upf` | container | `eth0` | `drops_attributed_here` | `qdisc_netem`: 656 dropped, 42.0% |
| 5 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 6 | `rtpengine` | container | `eth0` | `clean` | _clean_ |
| 7 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 8 | `upf` | container | `eth0` | `drops_attributed_here` | `qdisc_netem`: 659 dropped, 42.2% |
| 9 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 10 | `nr_gnb` | container | `eth0` | `clean` | _clean_ |
| 11 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 12 | `e2e_ue2` | container | `eth0` | `clean` | _clean_ |

### Localized Synthesis

**Verdict:** `localized`  
**Primary suspect NF:** `upf`  
**Confidence:** high

**Summary:** Transport-layer fault localized to upf[eth0]: qdisc_netem reports 656 packets dropped (42.0%).

**Recommendation:** Inspect the traffic control qdisc configuration on the `upf` container's `eth0` interface: `docker exec upf tc -s qdisc show dev eth0`.


## Event Aggregation (Phase 1)

**1 events fired during the observation window:**

- `core.upf.activity_during_calls_collapsed` (source: `core.upf.activity_during_calls`, nf: `upf`, t=1779283807.1)  [current_value=0.08850799999999999]

## Correlation Analysis (Phase 2)

1 events fired but no composite hypothesis emerged. The events may be from independent faults or lack registered correlation hints in the KB.

## RAG & Operational Lessons (Phase 2.5)

### RAG retrieval — prior similar episodes

**Status:** `hits` — hits=5, top_sim=0.91, top_case=v6/ep_20260430_015439_data_plane_degradation
**Index:** `/home/ehoskas/agentic-network-ops/rag_index`  **Corpus size:** 102 cases
**Classifier label used in retrieval:** `mixed`
**Retrieval params:** k=5, min_similarity=0.4
**Hits (5):**

| Rank | Sim | Case ID | Scenario | Ground truth | Primary suspect | Score |
|---:|---:|---|---|---|---|---:|
| 0 | 91% | `v6/ep_20260430_015439_data_plane_degradation` | Data Plane Degradation | `upf` | `upf` | 85% |
| 1 | 89% | `v7/ep_20260510_185748_call_quality_degradation` | Call Quality Degradation | `rtpengine` | `rtpengine` | 100% |
| 2 | 88% | `v6/ep_20260501_012004_data_plane_degradation` | Data Plane Degradation | `upf` | `upf` | 90% |
| 3 | 88% | `v7/ep_20260509_125816_call_quality_degradation` | Call Quality Degradation | `rtpengine` | `rtpengine` | 90% |
| 4 | 87% | `v7/ep_20260514_221925_data_plane_degradation` | Data Plane Degradation | `upf` | `upf` | 100% |

*Rendered block injected into the NA prompt's `{prior_similar_episodes}` placeholder: 4748 chars. Source paths are inlined in the block so the EvidenceValidator can audit any case the NA cites.*

### Operational lessons — hand-authored rules corpus

**Status:** `injected` — lessons=15, chars=14426
**Path:** `/home/ehoskas/agentic-network-ops/agentic_ops_common/rag/lessons.yaml`  **Count:** 15  **Block size:** 14426 chars
**Injected lesson IDs:** `L01`, `L02`, `L03`, `L04`, `L05`, `L06`, `L07`, `L08`, `L09`, `L10`, `L11`, `L12`, `L13`, `L14`, `L15`

### NA citations of the injected content

**No verbatim citations.** The NA's output text did not reference any retrieved case_id or any injected lesson_id verbatim. This does NOT prove the NA ignored the injected content — the model may have absorbed the patterns implicitly — but it does mean no audit trail links the NA's reasoning back to a specific case or lesson.

## Network Analysis (Phase 3)

**Summary:** The network anomaly is characterized by a severe media-plane failure, indicated by a collapse in UPF activity during calls and a high packet loss ratio reported at RTPEngine, with the primary suspects being rtpengine or upf.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | No evidence of infrastructure-layer faults (DNS, database, container orchestration). |
| **ran** | 🟢 GREEN | No direct evidence of a RAN-layer fault. |
| **core** | 🔴 RED | The core data plane (UPF) shows a significant drop in activity during calls, indicating a media path failure. |
| **ims** | 🔴 RED | The IMS media plane is highly degraded, with significant packet loss reported by RTPEngine and a drop in UPF activity during calls. The signaling plane shows signs of stress, likely as a secondary effect of media failures. |

**CORE evidence:**
- derived.upf_activity_during_calls

**IMS evidence:**
- derived.rtpengine_loss_ratio
- derived.upf_activity_during_calls

**Ranked hypotheses:**

- **`h1`** (fit=0.90, nf=rtpengine, specificity=specific):
    - **Statement:** rtpengine is the source of the anomalous behavior observed in derived.rtpengine_loss_ratio.
    - **Supporting events:** `core.upf.activity_during_calls_collapsed`
    - **Falsification probes:**
        - measure_rtt(container='rtpengine', target='upf', loss_threshold=0.1)
        - get_diagnostic_metrics(nfs=['rtpengine'])
- **`h2`** (fit=0.80, nf=upf, specificity=specific):
    - **Statement:** upf is the source of the anomalous behavior observed in core.upf.activity_during_calls_collapsed.
    - **Supporting events:** `core.upf.activity_during_calls_collapsed`
    - **Falsification probes:**
        - measure_rtt(container='upf', target='rtpengine', loss_threshold=0.1)
        - get_diagnostic_metrics(nfs=['upf'])


## Falsification Plans (Phase 4)

**2 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `rtpengine`)

**Hypothesis:** rtpengine is the source of the anomalous behavior observed in derived.rtpengine_loss_ratio.

**Probes (3):**
1. **`get_dp_quality_gauges`** — Returns rate-based MOS/loss/jitter alongside RTPEngine errors.
    - *Expected if hypothesis holds:* The value of `rtpengine.errors_per_second` is greater than zero, consistent with errors originating at rtpengine.
    - *Falsifying observation:* The value of `rtpengine.errors_per_second` is zero.
2. **`measure_rtt`** — from='upf', to_ip='rtpengine'
    - *Expected if hypothesis holds:* High packet loss is observed, which is consistent with the issue being located at the destination, rtpengine.
    - *Falsifying observation:* Low or zero packet loss is observed, suggesting the path to rtpengine is healthy.
3. **`measure_rtt`** — from='pcscf', to_ip='rtpengine'
    - *Expected if hypothesis holds:* High packet loss is observed, consistent with the issue being located at the destination, rtpengine.
    - *Falsifying observation:* Low or zero packet loss is observed. If the path from UPF to rtpengine shows loss while this path does not, it suggests the issue is not at rtpengine's ingress but rather on the path from the UPF.

*Notes:* Probes are derived from KB-Curated Probe Candidates for h1, specifically candidates #1 and the falsification probe `measure_rtt`. A partner probe has been added to disambiguate the path measurement.

### Plan for `h2` (target: `upf`)

**Hypothesis:** upf is the source of the anomalous behavior observed in core.upf.activity_during_calls_collapsed.

**Probes (3):**
1. **`get_dp_quality_gauges`** — Returns rate-based MOS/loss/jitter alongside RTPEngine errors.
    - *Expected if hypothesis holds:* The value of `rtpengine.errors_per_second` is zero. This is consistent with the hypothesis that the failure is at UPF, not rtpengine.
    - *Falsifying observation:* The value of `rtpengine.errors_per_second` is greater than zero. This observation points to an issue at rtpengine, which is inconsistent with the hypothesis that upf is the source.
2. **`measure_rtt`** — from='upf', to_ip='nr_gnb'
    - *Expected if hypothesis holds:* High packet loss is observed, consistent with a failure at the UPF affecting the N3 data path.
    - *Falsifying observation:* Low or zero packet loss is observed. This would suggest the UPF's connectivity to the RAN is healthy.
3. **`measure_rtt`** — from='amf', to_ip='nr_gnb'
    - *Expected if hypothesis holds:* Low or zero packet loss is observed, as the control plane path is not expected to be affected by a UPF data plane issue.
    - *Falsifying observation:* High packet loss is observed. If both the control plane (AMF-gNB) and data plane (UPF-gNB) paths show loss, this points towards a shared network segment or the gNB, which is inconsistent with the hypothesis that UPF is the source.

*Notes:* Probes are derived from KB-Curated Probe Candidates for h2, particularly the disambiguator hint to check rtpengine metrics (candidate #5). The compositional `measure_rtt` probe pair is designed to isolate the data plane path (UPF-gNB) from the control plane path (AMF-gNB) as suggested by resampling feedback.


## Parallel Investigators (Phase 5)

**3 sub-Investigator verdict(s):** **1 DISPROVEN**, **1 INCONCLUSIVE**, **1 NOT_DISPROVEN**

### `h1` — ❌ **DISPROVEN**

**Hypothesis:** rtpengine is the source of the anomalous behavior observed in derived.rtpengine_loss_ratio.

**Reasoning:** [Multi-shot consensus — both shots returned DISPROVEN.]

Shot 1: The hypothesis is disproven because multiple probes indicate the fault lies upstream of rtpengine. While rtpengine reports a high loss ratio, it reports zero internal errors. Crucially, a connectivity test from P-CSCF to rtpengine shows 0% packet loss, while a test from UPF to rtpengine shows 31.8% loss. This isolates the issue to the UPF or the path between UPF and rtpengine, not rtpengine itself.

Shot 2: The hypothesis is disproven by triangulation. While the path from the UPF to rtpengine shows high packet loss (34.8%), the path from the P-CSCF to rtpengine shows 0% packet loss. If rtpengine were the source of the packet loss, both paths should be affected. The fact that one path is healthy indicates rtpengine is not the problem, and the issue lies either with the UPF or the network path between the UPF and rtpengine.

**Probes executed (4):**
- **Returns rate-based MOS/loss/jitter alongside RTPEngine errors.** ~ AMBIGUOUS
    - *Tool:* `print(default_api.get_dp_quality_gauges(at_time_ts = 1779283807.1008863))`
    - *Observation:* [EVIDENCE: get_dp_quality_gauges(at_time_ts=1779283807.1008863) -> "loss (recent)  : 50.52"]
    - *Comment:* This confirms high packet loss is being observed, but doesn't locate the source. The expected 'rtpengine.errors_per_second' was not in this output, requiring a separate tool call.
- **Check for rtpengine internal errors.** ✗ CONTRADICTS
    - *Tool:* `print(default_api.get_diagnostic_metrics(at_time_ts = 1779283807.1008863, nfs = ['rtpengine']))`
    - *Observation:* [EVIDENCE: get_diagnostic_metrics(at_time_ts=1779283807.1008863, nfs=['rtpengine']) -> "rtpengine.errors_per_second_(total) = 0 [gauge, errors_per_second]"]
    - *Comment:* The value of `rtpengine.errors_per_second` is zero. This directly contradicts the expectation that errors would be originating at rtpengine, and fulfills the falsifying condition for the first probe in the plan.
- **from='upf', to_ip='rtpengine'** ~ AMBIGUOUS
    - *Tool:* `print(default_api.measure_rtt(container = "upf", target = "rtpengine"))`
    - *Observation:* [EVIDENCE: measure_rtt('upf', 'rtpengine') -> "31.8182% packet loss"]
    - *Comment:* High packet loss is observed, which is consistent with a problem at the destination (rtpengine). However, this result is ambiguous as it also conflates with the health of the source (upf) and the network path between them.
- **from='pcscf', to_ip='rtpengine'** ✗ CONTRADICTS
    - *Tool:* `print(default_api.measure_rtt(container = "pcscf", target = "rtpengine"))`
    - *Observation:* [EVIDENCE: measure_rtt('pcscf', 'rtpengine') -> "0% packet loss"]
    - *Comment:* This probe shows a healthy path from a different source (pcscf) to rtpengine. This contradicts the hypothesis that rtpengine is the source of the packet loss, as it is reachable from other network functions. This triangulates the problem to be between upf and rtpengine.

**Alternative suspects:** upf, the network path from upf to rtpengine

### `h2` — ❓ **INCONCLUSIVE**

**Hypothesis:** upf is the source of the anomalous behavior observed in core.upf.activity_during_calls_collapsed.

**Reasoning:** [Multi-shot consensus — DISAGREEMENT. Shot 1 returned NOT_DISPROVEN; shot 2 returned DISPROVEN. Two independent samples of the same Investigator on the same plan reached opposite conclusions. The reconciler forces verdict to INCONCLUSIVE because we cannot trust either shot in isolation when the underlying LLM judgment is unstable.]

Shot 1 (NOT_DISPROVEN): All three probes yielded results consistent with the hypothesis. The first probe showed that while rtpengine reports high packet loss, it does not report any internal errors, suggesting the problem lies elsewhere. The second and third probes isolated the issue to the data plane, showing significant packet loss from the UPF to another data plane component (rtpengine), while a control plane path (AMF to SMF) remains healthy. This combination of evidence strongly supports the hypothesis that the UPF is the source of the failure.

Shot 2 (DISPROVEN): The hypothesis that UPF is the source is disproven. While RTPEngine shows no internal errors, a `measure_rtt` probe from `rtpengine` to `upf` reveals 31.8% packet loss. This indicates that packets are being dropped on the path to the UPF. This upstream packet loss is the likely cause for both the high loss ratio reported at RTPEngine and the collapse in UPF activity, contradicting the hypothesis that the UPF itself is the source of the failure. The evidence points to an issue with `rtpengine`'s egress or the network path preceding the UPF.

**Probes executed (3):**
- **Returns rate-based MOS/loss/jitter alongside RTPEngine errors.** ✓ CONSISTENT
    - *Tool:* `get_diagnostic_metrics(at_time_ts=1779283807.1008863, nfs=["rtpengine"])`
    - *Observation:* [EVIDENCE: get_diagnostic_metrics("at_time_ts=1779283807.1008863", nfs=["rtpengine"]) -> "rtpengine.errors_per_second_(total) = 0 [gauge, errors_per_second]"]
    - *Comment:* The value of `rtpengine.errors_per_second` is zero, which is consistent with the hypothesis that the failure is at UPF, not rtpengine. Although `get_dp_quality_gauges` shows a high loss ratio, the absence of errors at rtpengine itself points away from it as the source.
- **from='upf', to_ip='nr_gnb'** ✓ CONSISTENT
    - *Tool:* `measure_rtt(container='upf', target='rtpengine')`
    - *Observation:* [EVIDENCE: measure_rtt("container='upf'", "target='rtpengine'") -> "22.7273% packet loss"]
    - *Comment:* The probe to 'nr_gnb' failed as it is not a container. A substitute probe from 'upf' to 'rtpengine' was used to check a data plane path. The observed high packet loss (22.7%) is consistent with a failure at the UPF affecting its data plane interfaces.
- **from='amf', to_ip='nr_gnb'** ✓ CONSISTENT
    - *Tool:* `measure_rtt(container='amf', target='smf')`
    - *Observation:* [EVIDENCE: measure_rtt("container='amf'", "target='smf'") -> "0% packet loss"]
    - *Comment:* The probe to 'nr_gnb' failed. A substitute probe checking a control plane path between 'amf' and 'smf' was used instead. The observed 0% packet loss is consistent with the expectation that the control plane path is not affected by a UPF data plane issue.

**Alternative suspects:** rtpengine

### `h_promoted_upf` — ✅ **NOT_DISPROVEN**

**Hypothesis:** upf is the source of the anomaly named in the alternative_suspects of the original verdict tree.

**Reasoning:** All three probes executed were consistent with the hypothesis. Probes measuring round-trip time from two separate components (rtpengine, smf) to the UPF both revealed significant packet loss (32-35%). This triangulation makes it highly likely that the UPF is the source of the packet loss, rather than an issue with a specific path or source container. This is further corroborated by the high packet loss reported by RTPEngine's data plane quality gauges.

**Probes executed (3):**
- **window_seconds=120 to check UPF packet rates** ✓ CONSISTENT
    - *Tool:* `default_api.get_dp_quality_gauges(at_time_ts = 1779283807.1008863, window_seconds = 120)`
    - *Observation:* [EVIDENCE: get_dp_quality_gauges(at_time_ts=1779283807.1008863, window_seconds=120) -> "loss (recent)  : 50.52"]
    - *Comment:* The high packet loss reported by RTPEngine is consistent with a data plane anomaly. While not pinpointing UPF directly, it confirms a problem exists that the UPF is a candidate for, especially given the disambiguation note in the tool output that pointed to checking the rtpengine-to-upf path.
- **from: rtpengine, to: upf** ✓ CONSISTENT
    - *Tool:* `default_api.measure_rtt(container = 'rtpengine', target = 'upf')`
    - *Observation:* [EVIDENCE: measure_rtt('rtpengine', 'upf') -> "66 packets transmitted, 45 received, 31.8182% packet loss"]
    - *Comment:* This directly confirms the expectation of increased RTT or packet loss. The high packet loss from rtpengine to upf is strong evidence supporting the hypothesis.
- **from: smf, to: upf** ✓ CONSISTENT
    - *Tool:* `default_api.measure_rtt(container = 'smf', target = 'upf')`
    - *Observation:* [EVIDENCE: measure_rtt('smf', 'upf') -> "66 packets transmitted, 43 received, 34.8485% packet loss"]
    - *Comment:* This partner probe confirms that the packet loss is not specific to the rtpengine-upf path. Seeing high packet loss from a second source (smf) strongly indicates the problem lies with the common destination, the UPF.


## Evidence Validation (Phase 6)

**Overall verdict:** clean
**Overall confidence:** high

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 7 | 4/4 | clean | high |
| `InvestigatorAgent_h2` | 9 | 3/3 | clean | high |
| `InvestigatorAgent_h_promoted_upf` | 3 | 3/3 | clean | high |


## Ground Truth

**Failure domain:** data_plane  
**Protocol impact:** GTP-U  
**Affected components:** upf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v7-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 519.4s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: Transport-layer fault localized to upf[eth0]: qdisc_netem reports 656 packets dropped (42.0%).
> - **timeline**:
>     1. Path walk initiated for flow `vonr_media` based on transport-layer signals.
>     2. At hop 5, fault localized to `upf[eth0]` with attribution kind `drops_attributed_here` (qdisc_netem).
>     3. Path walk completed with high confidence localization.
> - **root_cause**: Kernel-level packet drop on upf's eth0 interface: a `tc netem` qdisc is configured to drop 30% of packets, causing 42.0% observed loss. (primary_suspect_nf: `upf`)
> - **affected_components**:
>     - `upf`: Root Cause
> - **recommendation**: Inspect the traffic control qdisc configuration on the `upf` container's `eth0` interface: `docker exec upf tc -s qdisc show dev eth0`.
> - **confidence**: high
> - **verdict_kind**: localized
> - **explanation**: The path walk for the `vonr_media` flow localized a transport-layer fault to the `upf` container. The walk attributed packet drops directly to the `eth0` interface on this hop.
> 
> Path walk — flow `vonr_media`
> 
> | # | hop | kind | iface | prober | attribution |
> |---|-----|------|-------|--------|-------------|
> | 1 | e2e_ue1 | container | eth0 | KernelHopProber | clean |
> | 2 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 3 | nr_gnb | container | eth0 | KernelHopProber | clean |
> | 4 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 5 | upf | container | eth0 | KernelHopProber | drops_attributed_here (qdisc_netem, 656 dropped, 42.0%) 🎯 |
> | 6 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 7 | rtpengine | container | eth0 | KernelHopProber | clean |
> | 8 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 9 | upf | container | eth0 | KernelHopProber | drops_attributed_here (qdisc_netem, 659 dropped, 42.2%) |
> | 10 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 11 | nr_gnb | container | eth0 | KernelHopProber | clean |
> | 12 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 13 | e2e_ue2 | container | eth0 | KernelHopProber | clean |
> 
> Evidence from first-attributed hop `upf[eth0]`:
> ```
> upf[eth0] qdisc=netem, authored loss=30%: sent=1562 dropped=656 (42.00%)
> ---tc -s qdisc show dev eth0---
> qdisc netem 806e: root refcnt 9 limit 1000 loss 30%
>  Sent 331616 bytes 1562 pkt (dropped 656, overlimits 0 requeues 0) 
>  backlog 0b 0p requeues 0
> ```
> 
> Classifier rationale for running path-walk: label=mixed. Both transport-layer (3) and application-layer (1) signals are load-bearing. Path walk runs first; falls through to the application-layer pipeline if the walk produces null localization.

### Scoring Breakdown

**Overall score: 100%**

**Scorer assessment:** The agent provided an exceptionally accurate and detailed diagnosis, correctly identifying the root cause, affected component, severity, and fault type with high confidence, and attributing it to the correct network layer.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | Yes | The simulated failure was 30% packet loss on the UPF. The agent correctly identified 'Kernel-level packet drop on upf's eth0 interface' caused by a 'tc netem' qdisc configured to drop 30% of packets, leading to 42.0% observed loss. This is a precise and accurate identification of the simulated failure mode. |
| Component overlap | 100% | The primary affected component in the simulation was 'upf'. The agent correctly identified 'upf' as the 'Root Cause' in its 'affected_components' list. |
| Severity correct | Yes | The simulated failure involved 30% packet loss, leading to degradation. The agent's diagnosis of 'packet drop' and '42.0% observed loss' accurately reflects a degradation rather than a complete outage. |
| Fault type identified | Yes | The simulated fault type was packet loss. The agent explicitly identified 'Kernel-level packet drop' and '42.0% observed loss', which directly corresponds to the fault type. |
| Layer accuracy | Yes | The 'upf' component belongs to the 'core' layer. The agent's network analysis correctly rated the 'core' layer as 'red' with evidence related to 'upf_activity_during_calls', indicating correct layer attribution. |
| Confidence calibrated | Yes | The agent stated 'high' confidence, which is appropriate given the accuracy and detailed evidence provided in the diagnosis (path walk, specific qdisc configuration, observed loss percentage). |

**Ranking position:** #1 — The agent provided a single, clear root cause in its final diagnosis, which was correct.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 553,252 |
| Output tokens | 11,555 |
| Thinking tokens | 42,046 |
| **Total tokens** | **606,853** |

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
| NetworkAnalystAgent | 50,988 | 3 | 2 |
| Phase 3 NetworkAnalyst__guardrail | 0 | 0 | 0 |
| NetworkAnalystAgent | 43,624 | 4 | 2 |
| Phase 3 NetworkAnalyst__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 35,178 | 1 | 2 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 42,277 | 1 | 2 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| InvestigatorAgent_h1 | 83,142 | 4 | 5 |
| InvestigatorAgent_h1 | 44,321 | 3 | 3 |
| InvestigatorAgent_h1__reconciliation | 0 | 0 | 0 |
| InvestigatorAgent_h2 | 101,676 | 5 | 6 |
| InvestigatorAgent_h2 | 80,574 | 4 | 5 |
| InvestigatorAgent_h2__reconciliation | 0 | 0 | 0 |
| Phase5FanOutAudit | 0 | 0 | 0 |
| Phase6.5CandidatePool | 0 | 0 | 0 |
| InstructionGeneratorAgent | 33,982 | 1 | 2 |
| Phase 6.5 Reinvestigation IG__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 30,149 | 1 | 2 |
| Phase 6.5 Reinvestigation IG__guardrail | 0 | 0 | 0 |
| Phase 6.5 Reinvestigation IG__guardrail | 0 | 0 | 0 |
| InvestigatorAgent_h_promoted_upf | 44,334 | 3 | 3 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 16,608 | 0 | 1 |
| Phase 7 Synthesis__guardrail | 0 | 0 | 0 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 654.8s
