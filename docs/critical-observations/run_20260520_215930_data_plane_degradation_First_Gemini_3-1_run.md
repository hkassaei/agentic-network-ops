# Episode Report: Data Plane Degradation

**Agent:** v7  
**Episode ID:** ep_20260520_214933_data_plane_degradation  
**Date:** 2026-05-20T21:49:35.345681+00:00  
**Duration:** 594.8s  

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
- **Nodes with significant deltas:** 5
- **Nodes with any drift:** 6

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 39.31 (per-bucket threshold: 25.22, context bucket (1, 0), trained on 323 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following metrics deviate from their learned-healthy baseline. Treat each as a semantic observation (meaning + numbers), not a number alone — the KB's interpretation is the authoritative reading.

- **`derived.rtpengine_loss_ratio`** (RTPEngine RTCP-reported per-RR average packet loss) — current **32.50 packets_per_rr** vs learned baseline **0.00 packets_per_rr** (MEDIUM, spike)
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

- **`normalized.icscf.core:rcv_requests_invite_per_ue`** (SIP INVITE rate per UE at I-CSCF) — current **0.03 requests_per_second** vs learned baseline **0.00 requests_per_second** (MEDIUM, spike)
    - **What it measures:** Health of call-setup forwarding P-CSCF → I-CSCF. Partition signature
same as REGISTER rate.
    - **Spike means:** Forwarding failure.
    - **Healthy typical range:** 0–0.2 requests_per_second
    - **Healthy invariant:** Per-UE rate. Tracks pcscf.invite rate.

- **`normalized.pcscf.core:rcv_requests_invite_per_ue`** (SIP INVITE rate per UE at P-CSCF) — current **0.07 requests_per_second** vs learned baseline **0.00 requests_per_second** (MEDIUM, spike)
    - **What it measures:** Call attempt rate from registered UEs. Unlike REGISTER (periodic),
INVITEs only fire when UEs place calls. Zero is normal during
quiet periods; nonzero INVITE with zero dialogs is the signature
of call setup failure.
    - **Spike means:** Fewer call attempts.
    - **Healthy typical range:** 0–0.2 requests_per_second
    - **Healthy invariant:** Per-UE rate.

- **`normalized.pcscf.dialogs_per_ue`** (Active SIP dialogs per registered UE at P-CSCF) — current **2.00 count** vs learned baseline **0.48 count** (MEDIUM, spike)
    - **What it measures:** How many calls per user are currently in progress at the P-CSCF.
Going to zero from a non-zero baseline means calls have ended
(normal) OR call setup is failing system-wide (degradation).
Together with rcv_requests_* it discriminates the two.
    - **Spike means:** Calls ending or setup failing.
    - **Healthy typical range:** 0–1 count
    - **Healthy invariant:** Per-UE — scale-independent. 0 at rest, ~1 per active VoNR call.

- **`normalized.scscf.core:rcv_requests_invite_per_ue`** (SIP INVITE rate per UE at S-CSCF) — current **0.06 requests_per_second** vs learned baseline **0.00 requests_per_second** (MEDIUM, spike)
    - **What it measures:** S-CSCF participation in call setup. Zero when calls aren't being
placed OR S-CSCF not receiving forwarded INVITEs.
    - **Spike means:** Upstream forwarding issue.
    - **Healthy typical range:** 0–0.2 requests_per_second
    - **Healthy invariant:** Per-UE rate.

- **`normalized.smf.bearers_per_ue`** (Active QoS bearers per UE) — current **4.50 count** vs learned baseline **2.48 count** (MEDIUM, spike)
    - **What it measures:** Per-UE count of active QoS bearers. Baseline reflects default
bearers; increments during VoNR calls indicate dedicated voice
bearers being set up. Drop during an active call = dedicated
bearer torn down unexpectedly (voice will fail).
    - **Spike means:** Expected during VoNR calls (1 extra bearer per active call).
    - **Healthy typical range:** 2–3.5 count
    - **Healthy invariant:** At rest: equals configured default bearers (typically 2 per UE).
During active VoNR call: +1 per caller. The per-UE ratio is the
invariant; absolute count scales with UE pool.

- **`derived.upf_activity_during_calls`** (UPF activity consistency with active dialogs) — current **0.02 ratio** vs learned baseline **0.54 ratio** (LOW, drop)
    - **What it measures:** Cross-layer consistency check between IMS dialog state and UPF
throughput. A drop while dialogs_per_ue is non-zero is a
smoking-gun signal for media-plane failure independent of signaling.
    - **Drop means:** Active calls reported but no media flowing — media path broken (UPF, RTPEngine, or N3 packet loss).
    - **Healthy typical range:** 0.3–1 ratio
    - **Healthy invariant:** 1.0 when traffic fully follows active calls; 0.0 when signaling says active but data plane is silent.

- **`normalized.upf.gtp_outdatapktn3upf_per_ue`** (GTP-U downlink rate per UE (N3)) — current **1.74 packets_per_second** vs learned baseline **1.45 packets_per_second** (LOW, shift)
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
    - **Shift means:** Downlink data plane degraded ON THIS DIRECTION SPECIFICALLY
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

- **`context.cx_active`** — current **1.00** vs learned baseline **0.59** (LOW, spike). *(No KB context available — interpret from the metric name.)*


## Symptom Classifier (Phase 0.5)

**Label:** `mixed`  
**Flag counts:** transport=3, application=1, ambiguous=6

### Transport-bucket flags (3)

| Metric | Direction | Score | KB-driven reason |
|---|---|---:|---|
| `derived.rtpengine_loss_ratio` | spike | 4.45 | KB-labeled transport: ims.rtpengine.loss_ratio (spike, score=4.45) |
| `derived.upf_activity_during_calls` | drop | 3.36 | KB-labeled transport: core.upf.activity_during_calls (drop, score=3.36) |
| `normalized.upf.gtp_outdatapktn3upf_per_ue` | shift | 2.51 | KB-labeled transport: core.upf.gtp_outdatapktn3upf_per_ue (shift, score=2.51) |

### Application-bucket flags (1)

| Metric | Direction | Score | KB-driven reason |
|---|---|---:|---|
| `normalized.smf.bearers_per_ue` | spike | 4.45 | KB-labeled application: core.smf.bearers_per_ue (spike, score=4.45) |

### Ambiguous-bucket flags (6)

| Metric | Direction | Score | KB-driven reason |
|---|---|---:|---|
| `normalized.icscf.cdp_replies_per_ue` | shift | 4.45 | KB-labeled mixed: ims.icscf.cdp_replies_per_ue (shift, score=4.45) |
| `normalized.icscf.core:rcv_requests_invite_per_ue` | spike | 4.45 | KB-labeled mixed: ims.icscf.rcv_requests_invite_per_ue (spike, score=4.45) |
| `normalized.pcscf.core:rcv_requests_invite_per_ue` | spike | 4.45 | KB-labeled mixed: ims.pcscf.rcv_requests_invite_per_ue (spike, score=4.45) |
| `normalized.pcscf.dialogs_per_ue` | spike | 4.45 | KB-labeled mixed: ims.pcscf.dialogs_per_ue (spike, score=4.45) |
| `normalized.scscf.core:rcv_requests_invite_per_ue` | spike | 4.45 | KB-labeled mixed: ims.scscf.rcv_requests_invite_per_ue (spike, score=4.45) |
| `context.cx_active` | spike | 1.36 | no KB entry for context.cx_active — classification ambiguous |

**Rationale:**

```
label=mixed. Both transport-layer (3) and application-layer (1) signals are load-bearing. Path walk runs first; falls through to the application-layer pipeline if the walk produces null localization.

Transport signals: derived.rtpengine_loss_ratio (spike, score=4.45) — KB-labeled transport: ims.rtpengine.loss_ratio (spike, score=4.45); derived.upf_activity_during_calls (drop, score=3.36) — KB-labeled transport: core.upf.activity_during_calls (drop, score=3.36); normalized.upf.gtp_outdatapktn3upf_per_ue (shift, score=2.51) — KB-labeled transport: core.upf.gtp_outdatapktn3upf_per_ue (shift, score=2.51)

Application signals: normalized.smf.bearers_per_ue (spike, score=4.45) — KB-labeled application: core.smf.bearers_per_ue (spike, score=4.45)

Ambiguous signals: normalized.icscf.cdp_replies_per_ue (shift, score=4.45) — KB-labeled mixed: ims.icscf.cdp_replies_per_ue (shift, score=4.45); normalized.icscf.core:rcv_requests_invite_per_ue (spike, score=4.45) — KB-labeled mixed: ims.icscf.rcv_requests_invite_per_ue (spike, score=4.45); normalized.pcscf.core:rcv_requests_invite_per_ue (spike, score=4.45) — KB-labeled mixed: ims.pcscf.rcv_requests_invite_per_ue (spike, score=4.45); normalized.pcscf.dialogs_per_ue (spike, score=4.45) — KB-labeled mixed: ims.pcscf.dialogs_per_ue (spike, score=4.45); normalized.scscf.core:rcv_requests_invite_per_ue (spike, score=4.45) — KB-labeled mixed: ims.scscf.rcv_requests_invite_per_ue (spike, score=4.45) [+1 more]
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
Resolved transport path to flow `vonr_media` (score=14, 13 hops on the walk). Load-bearing components: ['context', 'icscf', 'pcscf', 'rtpengine', 'scscf', 'smf', 'upf']. Other candidate flows considered: vonr_call_teardown=10, vonr_call_setup=10, ims_registration=8, data_pdu_session_user_traffic=7.
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
| 4 | 🎯 `upf` | container | `eth0` | `drops_attributed_here` | `qdisc_netem`: 507 dropped, 41.2% |
| 5 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 6 | `rtpengine` | container | `eth0` | `clean` | _clean_ |
| 7 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 8 | `upf` | container | `eth0` | `drops_attributed_here` | `qdisc_netem`: 508 dropped, 41.2% |
| 9 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 10 | `nr_gnb` | container | `eth0` | `clean` | _clean_ |
| 11 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 12 | `e2e_ue2` | container | `eth0` | `clean` | _clean_ |

### Localized Synthesis

**Verdict:** `localized`  
**Primary suspect NF:** `upf`  
**Confidence:** high

**Summary:** Transport-layer fault localized to upf[eth0]: qdisc_netem reports 507 packets dropped (41.22%).

**Recommendation:** Inspect tc qdisc on upf: `docker exec upf tc -s qdisc show dev eth0`


## Event Aggregation (Phase 1)

**1 events fired during the observation window:**

- `core.upf.activity_during_calls_collapsed` (source: `core.upf.activity_during_calls`, nf: `upf`, t=1779313892.9)  [current_value=0.0696485]

## Correlation Analysis (Phase 2)

1 events fired but no composite hypothesis emerged. The events may be from independent faults or lack registered correlation hints in the KB.

## RAG & Operational Lessons (Phase 2.5)

### RAG retrieval — prior similar episodes

**Status:** `hits` — hits=5, top_sim=0.79, top_case=v7/ep_20260509_125816_call_quality_degradation
**Index:** `/home/ehoskas/agentic-network-ops/rag_index`  **Corpus size:** 102 cases
**Classifier label used in retrieval:** `mixed`
**Retrieval params:** k=5, min_similarity=0.4
**Hits (5):**

| Rank | Sim | Case ID | Scenario | Ground truth | Primary suspect | Score |
|---:|---:|---|---|---|---|---:|
| 0 | 79% | `v7/ep_20260509_125816_call_quality_degradation` | Call Quality Degradation | `rtpengine` | `rtpengine` | 90% |
| 1 | 78% | `v6/ep_20260429_162423_data_plane_degradation` | Data Plane Degradation | `upf` | `upf` | 85% |
| 2 | 77% | `v6/ep_20260430_015439_data_plane_degradation` | Data Plane Degradation | `upf` | `upf` | 85% |
| 3 | 76% | `v7/ep_20260510_183211_data_plane_degradation` | Data Plane Degradation | `upf` | `upf` | 100% |
| 4 | 74% | `v7/ep_20260510_185748_call_quality_degradation` | Call Quality Degradation | `rtpengine` | `rtpengine` | 100% |

*Rendered block injected into the NA prompt's `{prior_similar_episodes}` placeholder: 4761 chars. Source paths are inlined in the block so the EvidenceValidator can audit any case the NA cites.*

### Operational lessons — hand-authored rules corpus

**Status:** `injected` — lessons=16, chars=15678
**Path:** `/home/ehoskas/agentic-network-ops/agentic_ops_common/rag/lessons.yaml`  **Count:** 16  **Block size:** 15678 chars
**Injected lesson IDs:** `L01`, `L02`, `L03`, `L04`, `L05`, `L06`, `L07`, `L08`, `L09`, `L10`, `L11`, `L12`, `L13`, `L14`, `L15`, `L16`

### NA citations of the injected content

**Cited lesson IDs:**
- `L08`

*Citations are verbatim string matches — case_ids and lesson_ids appear in the NA's emitted text (summary, hypothesis statements, or layer notes). The EvidenceValidator can audit any cited case by following its `source_episode_path` from the retrieval table above.*

## Network Analysis (Phase 3)

**Summary:** Severe media-plane packet loss during active VoNR calls (rtpengine_loss_ratio spike to 51.5) and a concurrent collapse in UPF activity relative to active dialogs point to a data-plane drop fault localized to rtpengine or upf.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | No infrastructure or container-state faults detected. |
| **ran** | 🟢 GREEN | UEs and gNB are successfully attached; N2 control plane is healthy. |
| **core** | 🟡 YELLOW | UPF traffic is anomalously low for the number of active dialogs. N3 packets-per-second did not drop to 0, which suggests data plane is still active but media throughput is not scaling up with active calls. |
| **ims** | 🔴 RED | Active VoNR calls are established, but RTPEngine is receiving severe RTCP loss reports from receivers, indicating massive media plane degradation. |

**CORE evidence:**
- core.upf.activity_during_calls_collapsed event fired
- derived.upf_activity_during_calls dropped to 0.02

**IMS evidence:**
- derived.rtpengine_loss_ratio spiked to 51.5
- normalized.pcscf.dialogs_per_ue spiked to 2.0
- normalized.smf.bearers_per_ue spiked to 4.50

**Ranked hypotheses:**

- **`h1`** (fit=0.95, nf=rtpengine, specificity=specific):
    - **Statement:** rtpengine is the source of the media-plane packet loss, causing both the RTCP loss_ratio spike and the downstream UPF traffic deficit.
    - **Supporting events:** `core.upf.activity_during_calls_collapsed`
    - **Falsification probes:**
        - measure_rtt(rtpengine, upf) with >= 30 packets to reliably detect egress transport drops on rtpengine (applying L08)
        - measure_rtt(upf, rtpengine) to rule out the reverse path
        - Agentic path walk along the VoNR media flow from rtpengine to upf to isolate hop drops
- **`h2`** (fit=0.75, nf=upf, specificity=specific):
    - **Statement:** upf is the source of the packet loss and media path breakdown.
    - **Supporting events:** `core.upf.activity_during_calls_collapsed`
    - **Falsification probes:**
        - measure_rtt(upf, rtpengine) with >= 30 packets to verify UPF N6 egress health
        - Agentic path walk along the VoNR media flow from upf to ran to isolate N3/kernel-level drop counters


## Falsification Plans (Phase 4)

**2 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `rtpengine`)

**Hypothesis:** rtpengine is the source of the media-plane packet loss, causing both the RTCP loss_ratio spike and the downstream UPF traffic deficit.

**Probes (3):**
1. **`get_dp_quality_gauges`** — window_seconds=120 to check rtpengine.errors_per_second and rtpengine.loss_ratio
    - *Expected if hypothesis holds:* A spike is observed in rtpengine.errors_per_second, or rtpengine.loss_ratio is greater than 0 while errors_per_second is 0.
    - *Falsifying observation:* Both rtpengine.errors_per_second and rtpengine.loss_ratio are within typical healthy ranges (0.0).
2. **`measure_rtt`** — from rtpengine to upf with at least 30 packets to detect egress transport drops
    - *Expected if hypothesis holds:* Packet loss (> 0%) is observed on the path from rtpengine to upf.
    - *Falsifying observation:* 0% packet loss is observed on the forward path.
3. **`measure_rtt`** — from upf to rtpengine with at least 30 packets (partner probe to disambiguate directionality)
    - *Expected if hypothesis holds:* 0% packet loss is observed on this reverse path, confirming the drops are directional and isolated to the rtpengine egress.
    - *Falsifying observation:* The probe's reading is inconsistent with rtpengine being the source (e.g. packet loss is observed on the reverse path as well, indicating a bidirectional network path issue rather than a failure at rtpengine).

*Notes:* Using get_dp_quality_gauges to verify RTPEngine's relay loop errors and receiver loss reports. Using a pair of measure_rtt probes to verify if loss is specifically on RTPEngine's egress or a bidirectional link issue.

### Plan for `h2` (target: `upf`)

**Hypothesis:** upf is the source of the packet loss and media path breakdown.

**Probes (3):**
1. **`get_dp_quality_gauges`** — window_seconds=120 to evaluate UPF packet rates (upf.gtp_indatapktn3upf_per_ue and upf.gtp_outdatapktn3upf_per_ue)
    - *Expected if hypothesis holds:* The rate for one or both directions shows a significant drop compared to expected baselines for active calls, indicating the data plane at the upf is degraded.
    - *Falsifying observation:* The UPF packet rates are maintained at healthy levels consistent with the traffic profile of active calls.
2. **`measure_rtt`** — from upf to rtpengine with at least 30 packets to verify UPF egress health
    - *Expected if hypothesis holds:* Packet loss (> 0%) is observed on the path from upf to rtpengine.
    - *Falsifying observation:* 0% packet loss is observed on this path.
3. **`measure_rtt`** — from rtpengine to upf with at least 30 packets (partner probe)
    - *Expected if hypothesis holds:* 0% packet loss is observed on the forward path, isolating the drops to the upf egress direction.
    - *Falsifying observation:* The probe's reading is inconsistent with upf being the source (e.g. the loss is observed on a path that does not traverse upf, or symmetric loss is observed pointing to a shared network issue).

*Notes:* Checking UPF data plane rates with get_dp_quality_gauges to rule out generic network path drop vs UPF specific degradation, paired with directional pings to isolate UPF egress.


## Parallel Investigators (Phase 5)

**2 sub-Investigator verdict(s):** **1 DISPROVEN**, **1 NOT_DISPROVEN**

### `h1` — ❌ **DISPROVEN**

**Hypothesis:** rtpengine is the source of the media-plane packet loss, causing both the RTCP loss_ratio spike and the downstream UPF traffic deficit.

**Reasoning:** [Multi-shot consensus — both shots returned DISPROVEN.]

Shot 1: Triangulation probes conclusively falsify the hypothesis that rtpengine is the source of the packet loss. While there is ~25-30% packet loss between rtpengine and UPF in both directions, measuring from rtpengine to an unrelated component (pcscf) shows 0% loss, proving rtpengine's network egress is healthy. Conversely, measuring from UPF to other components (amf, smf) shows the same ~25-30% packet loss, isolating UPF as the actual source of the network drops.

Shot 2: The data plane metrics confirm a spike in RTCP loss ratio at rtpengine, and the forward path from rtpengine to UPF exhibits ~36% packet loss. However, the reverse path probe from UPF to rtpengine also reveals ~29% packet loss. This bidirectional transport loss directly contradicts the hypothesis that the drops are directionally isolated to rtpengine's egress, pointing instead to a bidirectional network path impairment or an issue with the UPF itself.

**Probes executed (5):**
- **window_seconds=120 to check rtpengine.errors_per_second and rtpengine.loss_ratio** ✓ CONSISTENT
    - *Tool:* `get_dp_quality_gauges(at_time_ts=1779313859.6846604, window_seconds=120)`
    - *Observation:* [EVIDENCE: get_dp_quality_gauges(at_time_ts=1779313859.6846604, window_seconds=120) -> "loss (recent)  : 37.60... Receivers are reporting packet loss back to rtpengine."]
    - *Comment:* The spike in RTCP-reported loss ratio (37.60) confirms media-plane packet loss is occurring, which is consistent with the hypothesis but requires further localization to pinpoint the source.
- **from rtpengine to upf with at least 30 packets to detect egress transport drops** ✓ CONSISTENT
    - *Tool:* `measure_rtt("rtpengine", "upf")`
    - *Observation:* [EVIDENCE: measure_rtt("rtpengine", "upf") -> "66 packets transmitted, 49 received, 25.7576% packet loss"]
    - *Comment:* Observing 25.7% packet loss on the forward path is consistent with the hypothesis but conflates rtpengine egress with the path and UPF ingress.
- **from upf to rtpengine with at least 30 packets (partner probe to disambiguate directionality)** ✗ CONTRADICTS
    - *Tool:* `measure_rtt("upf", "rtpengine")`
    - *Observation:* [EVIDENCE: measure_rtt("upf", "rtpengine") -> "66 packets transmitted, 46 received, 30.303% packet loss"]
    - *Comment:* Packet loss on the reverse path indicates the drops are bidirectional between the two containers, which contradicts the hypothesis that drops are isolated to rtpengine's egress.
- **Triangulation probe from rtpengine to a known-good third component (pcscf)** ✗ CONTRADICTS
    - *Tool:* `measure_rtt("rtpengine", "pcscf")`
    - *Observation:* [EVIDENCE: measure_rtt("rtpengine", "pcscf") -> "66 packets transmitted, 66 received, 0% packet loss"]
    - *Comment:* 0% packet loss to a different container confirms rtpengine's networking stack and egress are completely healthy, directly disproving it as the source of drops.
- **Triangulation probe from upf to a known-good third component (amf)** ✗ CONTRADICTS
    - *Tool:* `measure_rtt("upf", "amf")`
    - *Observation:* [EVIDENCE: measure_rtt("upf", "amf") -> "66 packets transmitted, 49 received, 25.7576% packet loss"]
    - *Comment:* UPF experiencing identical packet loss rates when communicating with the AMF confirms that UPF is the true source of the drops.

**Alternative suspects:** upf, network path between rtpengine and upf

### `h2` — ✅ **NOT_DISPROVEN**

**Hypothesis:** upf is the source of the packet loss and media path breakdown.

**Reasoning:** [Multi-shot consensus — both shots returned NOT_DISPROVEN.]

Shot 1: The UPF packet rates are significantly degraded (4.6 pps in, 2.9 pps out) and ping tests show ~40-45% packet loss on both upf -> rtpengine and rtpengine -> upf paths. While the falsification plan expected egress-only drops, triangulation probes (rtpengine -> pcscf having 0% loss, amf -> upf having 41.9% loss) confirm that the UPF container is actively dropping packets on both its ingress and egress interfaces. The hypothesis holds: UPF is the true localized source of the packet loss.

Shot 2: The evidence correctly localizes the fault to the UPF. Data plane gauges show UPF packet throughput (4.6 pps) has collapsed relative to the active call volume. While the original falsification plan anticipated a unidirectional egress drop, RTT probes discovered severe bidirectional loss between RTPEngine and UPF (27% upf->rtpengine, 36% rtpengine->upf). However, triangulation probes decisively isolate this drop to the UPF container: RTPEngine experiences 0% loss to other peers (pcscf), while UPF experiences 33% loss to its other peers (smf). The hypothesis holds: UPF is indeed the source of the packet loss, manifesting as a bidirectional interface drop rather than a purely egress fault.

**Probes executed (5):**
- **window_seconds=120 to evaluate UPF packet rates** ✓ CONSISTENT
    - *Tool:* `get_dp_quality_gauges(at_time_ts=1779313859.68466, window_seconds=120)`
    - *Observation:* [EVIDENCE: get_dp_quality_gauges(at_time_ts=1779313859.68466, window_seconds=120) -> "UPF:\n    in  packets/sec: 4.6\n    out packets/sec: 2.9"]
    - *Comment:* UPF packet rates are significantly below the expected baseline of ~50 pps for active calls, confirming data plane degradation at the UPF.
- **from upf to rtpengine with at least 30 packets to verify UPF egress health** ✓ CONSISTENT
    - *Tool:* `measure_rtt("upf", "rtpengine", loss_threshold=0.2)`
    - *Observation:* [EVIDENCE: measure_rtt("upf", "rtpengine") -> "31 packets transmitted, 18 received, 41.9355% packet loss"]
    - *Comment:* Significant packet loss is observed on the UPF egress path to RTPEngine, confirming degradation.
- **from rtpengine to upf with at least 30 packets (partner probe)** ✗ CONTRADICTS
    - *Tool:* `measure_rtt("rtpengine", "upf", loss_threshold=0.2)`
    - *Observation:* [EVIDENCE: measure_rtt("rtpengine", "upf") -> "31 packets transmitted, 17 received, 45.1613% packet loss"]
    - *Comment:* The plan expected 0% loss (isolating to egress-only drops), but the partner probe shows 45.1% loss, indicating symmetric drops. However, this is refined via triangulation.
- **triangulation from rtpengine to pcscf to rule out shared network or rtpengine ingress issues** ✓ CONSISTENT
    - *Tool:* `measure_rtt("rtpengine", "pcscf", loss_threshold=0.2)`
    - *Observation:* [EVIDENCE: measure_rtt("rtpengine", "pcscf") -> "31 packets transmitted, 31 received, 0% packet loss"]
    - *Comment:* 0% loss on a path from RTPEngine confirms its interface is healthy, ruling it out as the source of the drops.
- **triangulation from amf to upf to isolate UPF ingress drops** ✓ CONSISTENT
    - *Tool:* `measure_rtt("amf", "upf", loss_threshold=0.2)`
    - *Observation:* [EVIDENCE: measure_rtt("amf", "upf") -> "31 packets transmitted, 18 received, 41.9355% packet loss"]
    - *Comment:* Loss on this path confirms the drops are localized specifically to the UPF container's interfaces (affecting both ingress and egress).


## Evidence Validation (Phase 6)

**Overall verdict:** clean
**Overall confidence:** high

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 10 | 5/5 | clean | high |
| `InvestigatorAgent_h2` | 12 | 5/5 | clean | high |


## Ground Truth

**Failure domain:** data_plane  
**Protocol impact:** GTP-U  
**Affected components:** upf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v7-adk/pro=gemini-3.1-pro-preview+flash=gemini-3.5-flash  
**Time to diagnosis:** 462.3s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: Transport-layer fault localized to upf[eth0]: qdisc_netem reports 507 packets dropped (41.22%).
> - **timeline**:
>     1. Agentic path walk initiated for vonr_media flow.
>     2. Path walk attributes severe packet loss (41.22%) to upf container on interface eth0 via qdisc_netem counters.
>     3. Application-layer investigation independently validates and converges on upf as the sole source of bidirectional drops via RTT triangulation.
> - **root_cause**: Kernel-level packet drop on upf's eth0 interface: tc netem qdisc dropping 30% of packets. (primary_suspect_nf: `upf`)
> - **affected_components**:
>     - `upf`: Root Cause
> - **recommendation**: Inspect tc qdisc on upf: `docker exec upf tc -s qdisc show dev eth0`
> - **confidence**: high
> - **verdict_kind**: localized
> - **explanation**: Per-hop walk through the last attribution:
> 
> | # | hop | kind | iface | prober | attribution |
> |---|-----|------|-------|--------|-------------|
> | 1 | e2e_ue1 | container | eth0 | KernelHopProber | clean |
> | 2 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 3 | nr_gnb | container | eth0 | KernelHopProber | clean |
> | 4 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 5 | upf | container | eth0 | KernelHopProber | drops_attributed_here (qdisc_netem, 507 dropped, 41.2%) 🎯 |
> | 6 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 7 | rtpengine | container | eth0 | KernelHopProber | clean |
> | 8 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 9 | upf | container | eth0 | KernelHopProber | drops_attributed_here (qdisc_netem, 508 dropped, 41.2%) |
> | 10 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 11 | nr_gnb | container | eth0 | KernelHopProber | clean |
> | 12 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 13 | e2e_ue2 | container | eth0 | KernelHopProber | clean |
> 
> ```
> upf[eth0] qdisc=netem, authored loss=30%: sent=1230 dropped=507 (41.22%)
> ---tc -s qdisc show dev eth0---
> qdisc netem 809a: root refcnt 9 limit 1000 loss 30%
>  Sent 270776 bytes 1230 pkt (dropped 507, overlimits 0 requeues 0) 
>  backlog 0b 0p requeues 0
> ```
> 
> Classifier rationale: label=mixed. Both transport-layer (3) and application-layer (1) signals are load-bearing. Path walk runs first; falls through to the application-layer pipeline if the walk produces null localization.
> 
> Transport signals: derived.rtpengine_loss_ratio (spike, score=4.45) — KB-labeled transport: ims.rtpengine.loss_ratio (spike, score=4.45); derived.upf_activity_during_calls (drop, score=3.36) — KB-labeled transport: core.upf.activity_during_calls (drop, score=3.36); normalized.upf.gtp_outdatapktn3upf_per_ue (shift, score=2.51) — KB-labeled transport: core.upf.gtp_outdatapktn3upf_per_ue (shift, score=2.51)
> 
> Application signals: normalized.smf.bearers_per_ue (spike, score=4.45) — KB-labeled application: core.smf.bearers_per_ue (spike, score=4.45)

### Scoring Breakdown

**Overall score: 100%**

**Scorer assessment:** The agent provided an exceptionally accurate diagnosis, correctly identifying the UPF packet loss down to the exact percentage and interface.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | Yes | The agent correctly identified the root cause as packet loss on the UPF's eth0 interface, specifically identifying the 30% packet drop rate. |
| Component overlap | 100% | The agent correctly identified the 'upf' as the root cause component. |
| Severity correct | Yes | The agent correctly identified the issue as a degradation (packet loss) rather than a complete outage. |
| Fault type identified | Yes | The agent correctly identified the fault type as packet loss/drop on the transport layer. |
| Layer accuracy | Yes | The agent correctly associated the UPF with the core layer, which was rated yellow due to anomalous traffic levels. |
| Confidence calibrated | Yes | The agent's high confidence is well-calibrated given the precise and accurate diagnosis supported by direct command outputs. |

**Ranking position:** #1 — The correct root cause (UPF packet loss) was identified as the primary and only root cause.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 390,981 |
| Output tokens | 9,444 |
| Thinking tokens | 37,164 |
| **Total tokens** | **437,589** |

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
| NetworkAnalystAgent | 129,662 | 7 | 4 |
| Phase 3 NetworkAnalyst__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 15,826 | 0 | 1 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 15,547 | 0 | 1 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| InvestigatorAgent_h1 | 88,874 | 7 | 4 |
| InvestigatorAgent_h1 | 35,746 | 3 | 2 |
| InvestigatorAgent_h1__reconciliation | 0 | 0 | 0 |
| InvestigatorAgent_h2 | 74,024 | 7 | 4 |
| InvestigatorAgent_h2 | 60,289 | 5 | 3 |
| InvestigatorAgent_h2__reconciliation | 0 | 0 | 0 |
| Phase5FanOutAudit | 0 | 0 | 0 |
| Phase6.5CandidatePool | 0 | 0 | 0 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 17,621 | 0 | 1 |
| Phase 7 Synthesis__guardrail | 0 | 0 | 0 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 594.8s

---

## Post-run Analysis (2026-05-21) — First Gemini-3.1-pro run + compound-prompt validation

This is the first chaos run using the new model mix:

```
v7-adk/pro=gemini-3.1-pro-preview+flash=gemini-3.5-flash
```

The "reasoning" agents (NA, IG, Investigator, Synthesis) run on **gemini-3.1-pro-preview**; the ontology-consultation sub-agent runs on **gemini-3.5-flash**. Worth analyzing because it surfaces (a) early signals on how 3.1-pro behaves on this workload, (b) the first clean validation of the compound-verdict prompt tightening landed in the previous task, and (c) a clarification of the Sim-vs-Score columns in the RAG hits table that's been a recurring confusion.

### Sim vs. Score — different things measuring different aspects of the same prior case

The RAG hits table in §RAG & Operational Lessons carries two numeric columns that are easy to conflate:

| Column | What it measures | Source | Computed when |
|---|---|---|---|
| **Sim** | Cosine similarity (TF-IDF, L2-normalized) between THIS run's screener-signature query vector and the prior case's vector. Range 0–1, rendered as %. | `agentic_ops_common/rag/index.py` (`embeddings @ query_norm.T`) | Live, at retrieval time |
| **Score** | The LLM judge's grade on the *prior case's diagnosis* against that case's ground truth. Range 0–100. | `agentic_chaos/scorer.py` (when the prior case was run); persisted into the indexed corpus via `parser.py:_extract_score_pct` | Baked into the corpus at index time |

They answer **different questions**:

- **Sim:** "How relevant is this prior case to today's symptom pattern?" (signature similarity)
- **Score:** "How well did the agent do on that prior case — i.e., how trustworthy is its `Primary suspect`?" (diagnosis quality)

The two columns together let the NA weight prior cases by **both relevance AND verdict quality**. Read jointly:

- **High Sim + High Score** → "very similar shape, agent nailed it" → strongest prior. Pattern-match the suspect.
- **High Sim + Low Score** → "similar shape, agent got it wrong last time" → use for caution, not as a suspect-borrowing signal.
- **Low Sim + High Score** → "less similar but high confidence in that suspect IF the pattern applies" → weak prior, fine to consider but not anchor on.
- **Low Sim + Low Score** → noise floor; the NA should treat as uninformative.

In this run's table all five hits have **Score ≥ 85** with **Sim 74–79%**. The agent did well on every retrieved case — but the signature match is weaker than the 88–94% we'd seen on previous DPD runs, because today's screener-flag mix is slightly different from the indexed cases.

### Run outcomes

| Dimension | Result |
|---|---|
| Score | **100%** (correct: UPF qdisc_netem drops, kernel-level localization) |
| Verdict_kind | **`localized`** — NOT `compound`. This is the right shape for a single-fault scenario where both pipelines converge on the same NF. |
| Walker | Localized at hops 5 and 9 with `drops_attributed_here qdisc_netem 507 dropped (41.2%)`. Header reads `upf[eth0]`. 🎯 markers correct. |
| RAG citations | Zero verbatim case-id citations. One lesson cited: **L08** (in h1's falsification probes, applying the "≥30-ping" rule for reliable loss detection). |
| Investigator | 2 hypotheses, multi-shot both shots agree on each: **h1 (rtpengine) DISPROVEN** via triangulation, **h2 (upf) NOT_DISPROVEN** via the same triangulation pattern. Clean. |
| Token cost | **437K** total. Thinking tokens 37K (~8.5% of total, vs ~6% on 2.5-pro). 3.1-pro's reasoning allocation per call is higher. |

### Three load-bearing findings

#### 1. The compound-verdict prompt tightening worked

The previous run with the same shape (`run_20260520_212351_hss_unresponsive`: `mixed` label routes through both pipelines, walker localizes one NF, app-layer pipeline implicates the *same* NF) emitted `verdict_kind=compound` with an empty `additional_root_causes` list — the structurally invalid shape the old prompt didn't cleanly rule out. The compound-consistency guardrail REJECTed twice, exhaustion-accept let the bad shape through.

This run hit the same shape — mixed label, walker localized UPF, h2 also UPF (h1 rtpengine was DISPROVEN) — and **correctly emitted `verdict_kind=localized`**. Single Synthesis call, single guardrail trace (no REJECT, no resample). The prompt-tightening that named the entry condition explicitly ("walker and app-layer named DIFFERENT NFs" required for compound; otherwise `localized`) is doing its job.

**Caveat:** two variables changed between the runs (prompt edit + model upgrade), so causality is ambiguous. To attribute cleanly we'd need to A/B-test the prompt change on 2.5-pro. But the failure mode the prompt edit targeted is gone in this run, which is the empirical signal we wanted.

#### 2. The ghost-rtpengine NA-ranking pattern persists across the model upgrade

NA emitted **h1=rtpengine (fit 0.95)**, **h2=upf (fit 0.75)** — the same ordering observed on every DPD run going back to May 14. Driven by the metric name `derived.rtpengine_loss_ratio` containing "rtpengine" in its identifier. 3.1-pro did not fix this on its own.

RAG's signal — 3 of 5 hits had ground truth = upf with verified primary suspect = upf — was again ignored at the NA-ranking stage. The Investigator's triangulation correctly disproved rtpengine via:
- `measure_rtt(rtpengine, pcscf)` → 0% loss (rtpengine's networking is healthy)
- `measure_rtt(upf, amf)` → 25.7% loss (UPF is the source)

The diagnosis came out right, but **at the cost of two parallel multi-shot Investigators (~260K tokens)** to clean up the NA's ranking error. The `na_evidence_grounding` ADR (drafted but un-implemented) is still the right structural fix for this — model upgrades don't address it.

#### 3. `get_deployment_config` was still not called

Same as the previous HSS Unresponsive run. The tool is wired into both IG and Investigator toolsets but neither invoked it. The IG didn't generate a `check_process_listeners` probe in either hypothesis's plan, so the natural trigger for the deployment-config lookup didn't arise. We still don't have a clean validation run showing the tool earns its keep.

### Other 3.1-pro behavioral observations vs. 2.5-pro (n=1, caveat)

Worth tracking across more runs to see if these are consistent traits or single-run variance:

- **NA made 7 tool calls** (vs typical 3-4 on 2.5-pro). 3.1-pro is more exploratory.
- **IG made 0 tool calls** on both attempts (vs typical 1 on 2.5-pro). IG seems to synthesize from the bundle without consulting external tools. If this continues across more runs, we may be paying for prompt-only IG (less grounding) at higher thinking-token cost.
- **Investigators each made 7 and 12 tool calls** (vs typical 3–6 on 2.5-pro). More probes per hypothesis. More thoroughness, more cost.
- **Investigator narratives are noticeably more detailed.** The DISPROVEN reasoning explicitly walks through triangulation logic; the NOT_DISPROVEN reasoning includes the bidirectional-loss observation and how triangulation resolves it. Quality of intermediate reasoning is higher.
- **Per-call thinking tokens are up.** 37K thinking on 437K total = ~8.5% (vs ~6% on 2.5-pro runs we've seen). 3.1-pro is using more internal reasoning per call.

### Net read on 3.1-pro from n=1

Single data point so caveat heavily, but: **3.1-pro produces a more detailed, more exploratory trace at similar overall token cost** for the same correct verdict. The "more thorough investigator" + "more exploratory NA" tendencies are positive if the diagnosis quality holds across more runs. The NA's metric-name pattern-match (ghost-rtpengine) is a structural weakness that no model upgrade has touched — the fix is the evidence-grounding ADR, not a model swap. Run more scenarios before drawing conclusions about whether 3.1-pro is net better, worse, or roughly equivalent to 2.5-pro for this workload.
