# Episode Report: Data Plane Degradation

**Agent:** v7  
**Episode ID:** ep_20260521_023624_data_plane_degradation  
**Date:** 2026-05-21T02:36:26.148536+00:00  
**Duration:** 635.4s  

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
- **Nodes with significant deltas:** 5
- **Nodes with any drift:** 6

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 51.68 (per-bucket threshold: 28.18, context bucket (1, 1), trained on 323 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following metrics deviate from their learned-healthy baseline. Treat each as a semantic observation (meaning + numbers), not a number alone — the KB's interpretation is the authoritative reading.

- **`derived.rtpengine_loss_ratio`** (RTPEngine RTCP-reported per-RR average packet loss) — current **44.32 packets_per_rr** vs learned baseline **0.00 packets_per_rr** (MEDIUM, spike)
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

- **`normalized.icscf.cdp_replies_per_ue`** (I-CSCF Diameter reply rate per UE) — current **0.10 replies_per_second_per_ue** vs learned baseline **0.03 replies_per_second_per_ue** (MEDIUM, spike)
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

- **`normalized.pcscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at P-CSCF) — current **0.27 requests_per_second** vs learned baseline **0.06 requests_per_second** (MEDIUM, spike)
    - **What it measures:** How actively UEs are refreshing their IMS registrations with the
P-CSCF. REGISTERs arrive periodically (re-registration timer) plus
at attach. Sustained zero means UEs cannot reach P-CSCF OR the
UE-to-network SIP path is broken.
    - **Spike means:** Fewer REGISTERs than expected — UE connectivity or P-CSCF reachability issue.
    - **Healthy typical range:** 0–0.5 requests_per_second
    - **Healthy invariant:** Per-UE rate — same value at any deployment scale.

- **`normalized.pcscf.dialogs_per_ue`** (Active SIP dialogs per registered UE at P-CSCF) — current **3.00 count** vs learned baseline **0.48 count** (MEDIUM, spike)
    - **What it measures:** How many calls per user are currently in progress at the P-CSCF.
Going to zero from a non-zero baseline means calls have ended
(normal) OR call setup is failing system-wide (degradation).
Together with rcv_requests_* it discriminates the two.
    - **Spike means:** Calls ending or setup failing.
    - **Healthy typical range:** 0–1 count
    - **Healthy invariant:** Per-UE — scale-independent. 0 at rest, ~1 per active VoNR call.

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

- **`normalized.upf.gtp_indatapktn3upf_per_ue`** (GTP-U uplink rate per UE (N3)) — current **8.06 packets_per_second** vs learned baseline **1.45 packets_per_second** (MEDIUM, spike)
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
| `normalized.smf.bearers_per_ue` | spike | 4.28 | KB-labeled application: core.smf.bearers_per_ue (spike, score=4.28) |

### Ambiguous-bucket flags (6)

| Metric | Direction | Score | KB-driven reason |
|---|---|---:|---|
| `normalized.icscf.cdp_replies_per_ue` | spike | 4.28 | KB-labeled mixed: ims.icscf.cdp_replies_per_ue (spike, score=4.28) |
| `normalized.icscf.core:rcv_requests_register_per_ue` | spike | 4.28 | KB-labeled mixed: ims.icscf.rcv_requests_register_per_ue (spike, score=4.28) |
| `normalized.pcscf.core:rcv_requests_register_per_ue` | spike | 4.28 | KB-labeled mixed: ims.pcscf.rcv_requests_register_per_ue (spike, score=4.28) |
| `normalized.pcscf.dialogs_per_ue` | spike | 4.28 | KB-labeled mixed: ims.pcscf.dialogs_per_ue (spike, score=4.28) |
| `normalized.scscf.cdp_replies_per_ue` | spike | 4.28 | KB-labeled mixed: ims.scscf.cdp_replies_per_ue (spike, score=4.28) |
| `normalized.scscf.core:rcv_requests_register_per_ue` | spike | 4.28 | KB-labeled mixed: ims.scscf.rcv_requests_register_per_ue (spike, score=4.28) |

**Rationale:**

```
label=mixed. Both transport-layer (3) and application-layer (1) signals are load-bearing. Path walk runs first; falls through to the application-layer pipeline if the walk produces null localization.

Transport signals: derived.rtpengine_loss_ratio (spike, score=4.28) — KB-labeled transport: ims.rtpengine.loss_ratio (spike, score=4.28); derived.upf_activity_during_calls (drop, score=4.28) — KB-labeled transport: core.upf.activity_during_calls (drop, score=4.28); normalized.upf.gtp_indatapktn3upf_per_ue (spike, score=4.28) — KB-labeled transport: core.upf.gtp_indatapktn3upf_per_ue (spike, score=4.28)

Application signals: normalized.smf.bearers_per_ue (spike, score=4.28) — KB-labeled application: core.smf.bearers_per_ue (spike, score=4.28)

Ambiguous signals: normalized.icscf.cdp_replies_per_ue (spike, score=4.28) — KB-labeled mixed: ims.icscf.cdp_replies_per_ue (spike, score=4.28); normalized.icscf.core:rcv_requests_register_per_ue (spike, score=4.28) — KB-labeled mixed: ims.icscf.rcv_requests_register_per_ue (spike, score=4.28); normalized.pcscf.core:rcv_requests_register_per_ue (spike, score=4.28) — KB-labeled mixed: ims.pcscf.rcv_requests_register_per_ue (spike, score=4.28); normalized.pcscf.dialogs_per_ue (spike, score=4.28) — KB-labeled mixed: ims.pcscf.dialogs_per_ue (spike, score=4.28); normalized.scscf.cdp_replies_per_ue (spike, score=4.28) — KB-labeled mixed: ims.scscf.cdp_replies_per_ue (spike, score=4.28) [+1 more]
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
| 4 | 🎯 `upf` | container | `eth0` | `drops_attributed_here` | `qdisc_netem`: 783 dropped, 41.6% |
| 5 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 6 | `rtpengine` | container | `eth0` | `clean` | _clean_ |
| 7 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 8 | `upf` | container | `eth0` | `drops_attributed_here` | `qdisc_netem`: 784 dropped, 41.5% |
| 9 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 10 | `nr_gnb` | container | `eth0` | `clean` | _clean_ |
| 11 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 12 | `e2e_ue2` | container | `eth0` | `clean` | _clean_ |

### Localized Synthesis

**Verdict:** `localized`  
**Primary suspect NF:** `upf`  
**Confidence:** high

**Summary:** Transport-layer fault localized to upf[eth0]: qdisc_netem reports 783 packets dropped (41.6%).

**Recommendation:** Inspect tc qdisc on upf: `docker exec upf tc -s qdisc show dev eth0`


## Event Aggregation (Phase 1)

**1 events fired during the observation window:**

- `core.upf.activity_during_calls_collapsed` (source: `core.upf.activity_during_calls`, nf: `upf`, t=1779331105.1)  [current_value=0.071473]

## Correlation Analysis (Phase 2)

1 events fired but no composite hypothesis emerged. The events may be from independent faults or lack registered correlation hints in the KB.

## RAG & Operational Lessons (Phase 2.5)

### RAG retrieval — prior similar episodes

**Status:** `hits` — hits=5, top_sim=0.92, top_case=v6/ep_20260501_012004_data_plane_degradation
**Index:** `/home/ehoskas/agentic-network-ops/rag_index`  **Corpus size:** 102 cases
**Classifier label used in retrieval:** `mixed`
**Retrieval params:** k=5, min_similarity=0.4
**Hits (5):**

| Rank | Sim | Case ID | Scenario | Ground truth | Primary suspect | Score |
|---:|---:|---|---|---|---|---:|
| 0 | 92% | `v6/ep_20260501_012004_data_plane_degradation` | Data Plane Degradation | `upf` | `upf` | 90% |
| 1 | 89% | `v7/ep_20260510_185748_call_quality_degradation` | Call Quality Degradation | `rtpengine` | `rtpengine` | 100% |
| 2 | 88% | `v6/ep_20260430_015439_data_plane_degradation` | Data Plane Degradation | `upf` | `upf` | 85% |
| 3 | 86% | `v6/ep_20260501_021728_data_plane_degradation` | Data Plane Degradation | `upf` | `upf` | 100% |
| 4 | 84% | `v7/ep_20260514_221925_data_plane_degradation` | Data Plane Degradation | `upf` | `upf` | 100% |

*Rendered block injected into the NA prompt's `{prior_similar_episodes}` placeholder: 4742 chars. Source paths are inlined in the block so the EvidenceValidator can audit any case the NA cites.*

### Operational lessons — hand-authored rules corpus

**Status:** `injected` — lessons=16, chars=15678
**Path:** `/home/ehoskas/agentic-network-ops/agentic_ops_common/rag/lessons.yaml`  **Count:** 16  **Block size:** 15678 chars
**Injected lesson IDs:** `L01`, `L02`, `L03`, `L04`, `L05`, `L06`, `L07`, `L08`, `L09`, `L10`, `L11`, `L12`, `L13`, `L14`, `L15`, `L16`

### NA citations of the injected content

**No verbatim citations.** The NA's output text did not reference any retrieved case_id or any injected lesson_id verbatim. This does NOT prove the NA ignored the injected content — the model may have absorbed the patterns implicitly — but it does mean no audit trail links the NA's reasoning back to a specific case or lesson.

## Network Analysis (Phase 3)

**Summary:** The UPF data plane throughput has collapsed severely relative to active SIP dialogs, identifying UPF as the primary fault source, while RTPEngine and CSCFs are demoted as downstream reporters observing the resulting media packet loss and signaling retries.

**Ranked hypotheses:**

- **`h1`** (fit=0.95, nf=upf, specificity=specific):
    - **Statement:** upf is the source of the anomalous behavior observed in core.upf.activity_during_calls_collapsed, causing media-plane packet loss that propagates to downstream receivers and surfaces as high RTCP loss reports at RTPEngine.
    - **Supporting events:** `core.upf.activity_during_calls_collapsed`
    - **Falsification probes:**
        - measure_rtt(upf, rtpengine)
        - measure_rtt(rtpengine, upf)
- **`h2`** (fit=0.40, nf=rtpengine, specificity=specific):
    - **Statement:** rtpengine is the source of the anomalous behavior observed in the derived.rtpengine_loss_ratio anomaly flag, dropping media packets on its end-to-end path despite internal relay errors remaining zero.
    - **Supporting events:** `core.upf.activity_during_calls_collapsed`
    - **Falsification probes:**
        - measure_rtt(rtpengine, upf)
        - measure_rtt(pcscf, rtpengine)


## Falsification Plans (Phase 4)

**2 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `upf`)

**Hypothesis:** upf is the source of the anomalous behavior observed in core.upf.activity_during_calls_collapsed, causing media-plane packet loss that propagates to downstream receivers and surfaces as high RTCP loss reports at RTPEngine.

**Probes (3):**
1. **`get_dp_quality_gauges`** — window_seconds=120 to check upf.activity_during_calls against rtpengine.loss_ratio and upf in/out pps
    - *Expected if hypothesis holds:* Active calls reported but no media flowing (upf.activity_during_calls_collapsed), and high loss ratio at RTPEngine, consistent with upf being the source.
    - *Falsifying observation:* The probe's reading is inconsistent with upf being the source (e.g. the metric stays at its healthy baseline).
2. **`measure_rtt`** — rtpengine -> upf
    - *Expected if hypothesis holds:* Packet loss or elevated latency observed on the path from RTPEngine to UPF.
    - *Falsifying observation:* The probe's reading is inconsistent with upf being the source (e.g. the metric stays at its healthy baseline, or the loss is observed on a path that does not traverse upf).
3. **`measure_rtt`** — smf -> upf (Partner probe differing in source)
    - *Expected if hypothesis holds:* Packet loss observed on this alternative path to UPF, isolating the issue to upf rather than a specific path.
    - *Falsifying observation:* The probe's reading is inconsistent with upf being the source (e.g. the metric stays at its healthy baseline, or the loss is observed on a path that does not traverse upf).

*Notes:* Using get_dp_quality_gauges as the primary metric check to correlate RTPEngine loss with UPF activity. The compositional measure_rtt probe from rtpengine to upf requires a partner probe (smf to upf) to isolate upf from the path.

### Plan for `h2` (target: `rtpengine`)

**Hypothesis:** rtpengine is the source of the anomalous behavior observed in the derived.rtpengine_loss_ratio anomaly flag, dropping media packets on its end-to-end path despite internal relay errors remaining zero.

**Probes (3):**
1. **`get_dp_quality_gauges`** — window_seconds=120 to check rtpengine.errors_per_second and rtpengine.loss_ratio
    - *Expected if hypothesis holds:* High RTPEngine loss ratio observed while RTPEngine errors per second remain at zero.
    - *Falsifying observation:* The probe's reading is inconsistent with rtpengine being the source (e.g. the metric stays at its healthy baseline).
2. **`measure_rtt`** — rtpengine -> upf
    - *Expected if hypothesis holds:* Packet loss observed on the path originating from RTPEngine.
    - *Falsifying observation:* The probe's reading is inconsistent with rtpengine being the source (e.g. the metric stays at its healthy baseline, or the loss is observed on a path that does not traverse rtpengine).
3. **`measure_rtt`** — rtpengine -> pcscf (Partner probe differing in destination)
    - *Expected if hypothesis holds:* Packet loss observed on this alternative path originating from RTPEngine, isolating the issue to rtpengine.
    - *Falsifying observation:* The probe's reading is inconsistent with rtpengine being the source (e.g. the metric stays at its healthy baseline, or the loss is observed on a path that does not traverse rtpengine).

*Notes:* Using measure_rtt(rtpengine, upf) and measure_rtt(rtpengine, pcscf) to disambiguate whether the packet loss originates from rtpengine or the specific path to upf.


## Parallel Investigators (Phase 5)

**2 sub-Investigator verdict(s):** **1 NOT_DISPROVEN**, **1 DISPROVEN**

### `h1` — ✅ **NOT_DISPROVEN**

**Hypothesis:** upf is the source of the anomalous behavior observed in core.upf.activity_during_calls_collapsed, causing media-plane packet loss that propagates to downstream receivers and surfaces as high RTCP loss reports at RTPEngine.

**Reasoning:** [Multi-shot consensus — both shots returned NOT_DISPROVEN.]

Shot 1: Both measure_rtt probes from rtpengine and smf to upf show 33-36% packet loss, isolating the fault to UPF itself rather than a single network path. This network-level packet loss at UPF is consistent with it being the root cause of the media-plane packet loss observed by downstream receivers and reported via RTPEngine's high RTCP loss ratio.

Shot 2: Data plane quality metrics anchored at the anomaly time confirm a severe spike in media packet loss reported by downstream receivers at RTPEngine. To isolate the source, network transport was tested using measure_rtt from both RTPEngine and SMF to UPF. Both probes exhibited over 30% packet loss, triangulating the transport-layer fault directly to UPF's network interface rather than a specific path. The evidence is entirely consistent with UPF being the source of the packet loss.

**Probes executed (3):**
- **window_seconds=120 to check upf.activity_during_calls against rtpengine.loss_ratio and upf in/out pps** ✓ CONSISTENT
    - *Tool:* `get_dp_quality_gauges(at_time_ts=1779331099.52988, window_seconds=120)`
    - *Observation:* [EVIDENCE: get_dp_quality_gauges("at_time_ts=1779331099.52988", "window_seconds=120") -> "RTPEngine:\n    packets/sec    : 6.7\n    throughput     : 0.23 KB/s\n    MOS (recent)   : 4.30\n    loss (recent)  : 46.20\n        healthy_range = [0, 0.1]\n        interpretation (spike):\n            Receivers are reporting packet loss back to rtpengine."]
    - *Comment:* Shows extremely high RTCP-reported loss at RTPEngine, confirming the media-plane degradation.
- **rtpengine -> upf** ✓ CONSISTENT
    - *Tool:* `measure_rtt("rtpengine", "upf")`
    - *Observation:* [EVIDENCE: measure_rtt("rtpengine", "upf") -> "66 packets transmitted, 42 received, 36.3636% packet loss"]
    - *Comment:* Reveals high packet loss on the path from RTPEngine to UPF. Being a compositional probe, a partner probe is needed to attribute the loss specifically to UPF.
- **smf -> upf (Partner probe differing in source)** ✓ CONSISTENT
    - *Tool:* `measure_rtt("smf", "upf")`
    - *Observation:* [EVIDENCE: measure_rtt("smf", "upf") -> "66 packets transmitted, 44 received, 33.3333% packet loss"]
    - *Comment:* Partner probe confirms ~33% loss from a completely different source (SMF) to UPF. Since UPF is the shared element, it isolates UPF as the source of the dropped packets.

### `h2` — ❌ **DISPROVEN**

**Hypothesis:** rtpengine is the source of the anomalous behavior observed in the derived.rtpengine_loss_ratio anomaly flag, dropping media packets on its end-to-end path despite internal relay errors remaining zero.

**Reasoning:** [Multi-shot consensus — both shots returned DISPROVEN.]

Shot 1: Triangulation proves the packet loss does not originate at RTPEngine. While there is 34.8% packet loss on the path from RTPEngine to UPF, a partner probe from RTPEngine to P-CSCF shows 0% packet loss. This isolates the drops to the UPF or the network path specifically to it, exonerating RTPEngine as the source.

Shot 2: Triangulation of network paths proves the packet loss originates at UPF, not RTPEngine. While measure_rtt("rtpengine", "upf") shows ~32% packet loss, the partner probe measure_rtt("rtpengine", "pcscf") shows 0% loss, confirming RTPEngine's general egress is healthy. An additional probe measure_rtt("pcscf", "upf") also shows ~32% loss, isolating the fault to UPF's ingress/egress.

**Probes executed (3):**
- **window_seconds=120 to check rtpengine.errors_per_second and rtpengine.loss_ratio** ✓ CONSISTENT
    - *Tool:* `get_dp_quality_gauges(at_time_ts=1779331099.52988, window_seconds=120)`
    - *Observation:* [EVIDENCE: get_dp_quality_gauges(at_time_ts=1779331099.52988, window_seconds=120) -> "loss (recent)  : 46.20"]
    - *Comment:* RTCP loss ratio is heavily elevated as expected, indicating receivers are experiencing missing packets.
- **rtpengine -> upf** ✓ CONSISTENT
    - *Tool:* `measure_rtt("rtpengine", "upf")`
    - *Observation:* [EVIDENCE: measure_rtt("rtpengine", "upf") -> "34.8485% packet loss"]
    - *Comment:* Packet loss is observed between RTPEngine and UPF, but this reading conflates RTPEngine egress, the network path, and UPF ingress.
- **rtpengine -> pcscf (Partner probe differing in destination)** ✗ CONTRADICTS
    - *Tool:* `measure_rtt("rtpengine", "pcscf")`
    - *Observation:* [EVIDENCE: measure_rtt("rtpengine", "pcscf") -> "0% packet loss"]
    - *Comment:* The clean path from RTPEngine to P-CSCF proves RTPEngine is not dropping packets globally or at its own container boundary, refuting the hypothesis that RTPEngine is the source.

**Alternative suspects:** upf


## Evidence Validation (Phase 6)

**Overall verdict:** clean
**Overall confidence:** high

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 6 | 3/3 | clean | high |
| `InvestigatorAgent_h2` | 9 | 3/3 | clean | high |


## Ground Truth

**Failure domain:** data_plane  
**Protocol impact:** GTP-U  
**Affected components:** upf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v7-adk/pro=gemini-3.1-pro-preview+flash=gemini-3.5-flash  
**Time to diagnosis:** 495.9s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: Transport-layer fault localized to upf[eth0]: qdisc_netem reports 783 packets dropped (41.6%).
> - **timeline**:
>     1. Path walk initiated for vonr_media flow.
>     2. Fault attributed to upf[eth0] via drops_attributed_here (qdisc_netem, 783 dropped, 41.6%).
>     3. Path walk completed with high confidence.
> - **root_cause**: Kernel-level packet drop on upf's egress: tc netem qdisc dropping 30% of packets. (primary_suspect_nf: `upf`)
> - **affected_components**:
>     - `?`: ?
> - **recommendation**: Inspect tc qdisc on upf: `docker exec upf tc -s qdisc show dev eth0`
> - **confidence**: high
> - **verdict_kind**: localized
> - **explanation**: | # | hop | kind | iface | prober | attribution |
> |---|-----|------|-------|--------|-------------|
> | 1 | e2e_ue1 | container | eth0 | KernelHopProber | clean |
> | 2 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 3 | nr_gnb | container | eth0 | KernelHopProber | clean |
> | 4 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 5 | upf | container | eth0 | KernelHopProber | drops_attributed_here (qdisc_netem, 783 dropped, 41.6%) 🎯 |
> | 6 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 7 | rtpengine | container | eth0 | KernelHopProber | clean |
> | 8 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 9 | upf | container | eth0 | KernelHopProber | drops_attributed_here (qdisc_netem, 784 dropped, 41.5%) |
> | 10 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 11 | nr_gnb | container | eth0 | KernelHopProber | clean |
> | 12 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 13 | e2e_ue2 | container | eth0 | KernelHopProber | clean |
> 
> ```
> upf[eth0] qdisc=netem, authored loss=30%: sent=1882 dropped=783 (41.60%)
> ---tc -s qdisc show dev eth0---
> qdisc netem 80a0: root refcnt 9 limit 1000 loss 30%
>  Sent 326045 bytes 1882 pkt (dropped 783, overlimits 0 requeues 0) 
>  backlog 0b 0p requeues 0
> ```
> 
> Classifier rationale: label=mixed. Both transport-layer (3) and application-layer (1) signals are load-bearing. Path walk runs first; falls through to the application-layer pipeline if the walk produces null localization.
> 
> Transport signals: derived.rtpengine_loss_ratio (spike, score=4.28) — KB-labeled transport: ims.rtpengine.loss_ratio (spike, score=4.28); derived.upf_activity_during_calls (drop, score=4.28) — KB-labeled transport: core.upf.activity_during_calls (drop, score=4.28); normalized.upf.gtp_indatapktn3upf_per_ue (spike, score=4.28) — KB-labeled transport: core.upf.gtp_indatapktn3upf_per_ue (spike, score=4.28)
> 
> Application signals: normalized.smf.bearers_per_ue (spike, score=4.28) — KB-labeled application: core.smf.bearers_per_ue (spike, score=4.28)
> 
> Ambiguous signals: normalized.icscf.cdp_replies_per_ue (spike, score=4.28) — KB-labeled mixed: ims.icscf.cdp_replies_per_ue (spike, score=4.28); normalized.icscf.core:rcv_requests_register_per_ue (spike, score=4.28) — KB-labeled mixed: ims.icscf.rcv_requests_register_per_ue (spike, score=4.28); normalized.pcscf.core:rcv_requests_register_per_ue (spike, score=4.28) — KB-labeled mixed: ims.pcscf.rcv_requests_register_per_ue (spike, score=4.28); normalized.pcscf.dialogs_per_ue (spike, score=4.28) — KB-labeled mixed: ims.pcscf.dialogs_per_ue (spike, score=4.28); normalized.scscf.cdp_replies_per_ue (spike, score=4.28) — KB-labeled mixed: ims.scscf.cdp_replies_per_ue (spike, score=4.28) [+1 more]

### Scoring Breakdown

**Overall score: 90%**

**Scorer assessment:** The agent successfully diagnosed the 30% packet loss on the UPF with high accuracy, though it failed to format the affected_components list properly.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | Yes | The agent correctly identified that the root cause was a packet drop issue on the UPF egress, specifically noting the 30% packet loss on the UPF interface. |
| Component overlap | 50% | The agent correctly identified 'upf' as the primary suspect in the root_cause field, but failed to properly populate the structured 'affected_components' list, which contains placeholder values. |
| Severity correct | Yes | The agent correctly identified the issue as a packet drop/degradation fault rather than a complete outage. |
| Fault type identified | Yes | The agent correctly identified the fault type as packet drops/loss on the network path. |
| Layer accuracy | Yes | No explicit layer status table was provided, but the intermediate analysis and KB labels correctly associate the UPF with the 'core' layer. |
| Confidence calibrated | Yes | The agent expressed high confidence, which is fully justified given the highly accurate diagnosis and precise identification of the 30% packet loss. |

**Ranking position:** #1 — The agent identified UPF as the single primary suspect at the top of its diagnosis.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 612,076 |
| Output tokens | 9,961 |
| Thinking tokens | 38,257 |
| **Total tokens** | **660,294** |

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
| NetworkAnalystAgent | 162,953 | 9 | 5 |
| Phase 3 NetworkAnalyst__guardrail | 0 | 0 | 0 |
| NetworkAnalystAgent | 249,353 | 10 | 7 |
| Phase 3 NetworkAnalyst__guardrail | 0 | 0 | 0 |
| Phase 3 NetworkAnalyst__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 19,985 | 0 | 1 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 16,837 | 0 | 1 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| InvestigatorAgent_h1 | 31,530 | 3 | 2 |
| InvestigatorAgent_h1 | 31,480 | 3 | 2 |
| InvestigatorAgent_h1__reconciliation | 0 | 0 | 0 |
| InvestigatorAgent_h2 | 33,409 | 3 | 2 |
| InvestigatorAgent_h2 | 94,811 | 6 | 4 |
| InvestigatorAgent_h2__reconciliation | 0 | 0 | 0 |
| Phase5FanOutAudit | 0 | 0 | 0 |
| Phase6.5CandidatePool | 0 | 0 | 0 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 19,936 | 0 | 1 |
| Phase 7 Synthesis__guardrail | 0 | 0 | 0 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 635.4s
