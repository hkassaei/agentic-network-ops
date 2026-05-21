# Episode Report: Call Quality Degradation

**Agent:** v7  
**Episode ID:** ep_20260521_031437_call_quality_degradation  
**Date:** 2026-05-21T03:14:39.045836+00:00  
**Duration:** 881.0s  

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

- **Propagation window:** 125s (ObservationTrafficAgent drove traffic for this window; verifier added wait=0s on top)
- **Nodes with significant deltas:** 4
- **Nodes with any drift:** 5

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 51.68 (per-bucket threshold: 28.18, context bucket (1, 1), trained on 323 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following metrics deviate from their learned-healthy baseline. Treat each as a semantic observation (meaning + numbers), not a number alone — the KB's interpretation is the authoritative reading.

- **`derived.rtpengine_loss_ratio`** (RTPEngine RTCP-reported per-RR average packet loss) — current **22.50 packets_per_rr** vs learned baseline **0.00 packets_per_rr** (MEDIUM, spike)
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

- **`derived.upf_activity_during_calls`** (UPF activity consistency with active dialogs) — current **0.03 ratio** vs learned baseline **0.54 ratio** (MEDIUM, drop)
    - **What it measures:** Cross-layer consistency check between IMS dialog state and UPF
throughput. A drop while dialogs_per_ue is non-zero is a
smoking-gun signal for media-plane failure independent of signaling.
    - **Drop means:** Active calls reported but no media flowing — media path broken (UPF, RTPEngine, or N3 packet loss).
    - **Healthy typical range:** 0.3–1 ratio
    - **Healthy invariant:** 1.0 when traffic fully follows active calls; 0.0 when signaling says active but data plane is silent.

- **`normalized.icscf.cdp_replies_per_ue`** (I-CSCF Diameter reply rate per UE) — current **0.07 replies_per_second_per_ue** vs learned baseline **0.03 replies_per_second_per_ue** (MEDIUM, spike)
    - **What it measures:** Liveness of the I-CSCF↔HSS Cx path. Drops to 0 when HSS is unreachable OR when no signaling is occurring at the I-CSCF (idle or upstream P-CSCF partitioned).
    - **Spike means:** Either HSS is unreachable or upstream signaling has stopped reaching I-CSCF.
    - **Healthy typical range:** 0–1 replies_per_second_per_ue

- **`normalized.icscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at I-CSCF) — current **0.12 requests_per_second** vs learned baseline **0.06 requests_per_second** (MEDIUM, spike)
    - **What it measures:** Health of the P-CSCF → I-CSCF forwarding path (Mw interface). When
this drops to zero while P-CSCF REGISTER rate is still non-zero,
it's the SIGNATURE of an IMS partition between P-CSCF and I-CSCF.
    - **Spike means:** Forwarding issue on the Mw interface, or P-CSCF stopped forwarding.
    - **Healthy typical range:** 0–0.5 requests_per_second
    - **Healthy invariant:** Per-UE rate. Should closely track ims.pcscf.rcv_requests_register_per_ue.

- **`normalized.pcscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at P-CSCF) — current **0.12 requests_per_second** vs learned baseline **0.06 requests_per_second** (MEDIUM, spike)
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

- **`normalized.scscf.cdp_replies_per_ue`** (S-CSCF CDP Diameter replies per UE) — current **0.12 replies_per_second_per_ue** vs learned baseline **0.06 replies_per_second_per_ue** (MEDIUM, spike)
    - **What it measures:** Active S-CSCF Diameter traffic with HSS. Near-zero when registrations idle OR HSS partition.
    - **Spike means:** Diameter peering loss with HSS.
    - **Healthy typical range:** 0–1 replies_per_second_per_ue
    - **Healthy invariant:** Per-UE rate; varies with registration/auth load.

- **`normalized.scscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at S-CSCF) — current **0.12 requests_per_second** vs learned baseline **0.06 requests_per_second** (MEDIUM, spike)
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

- **`normalized.upf.gtp_indatapktn3upf_per_ue`** (GTP-U uplink rate per UE (N3)) — current **5.40 packets_per_second** vs learned baseline **1.45 packets_per_second** (MEDIUM, spike)
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
**First attributed hop:** `rtpengine[eth0]`
**Window:** 5s  
**Walked flow:** `vonr_media`

**Per-hop results:**

| # | Node | Kind | Iface | Attribution | Detail |
|---:|---|---|---|---|---|
| 0 | `e2e_ue1` | container | `eth0` | `clean` | _clean_ |
| 1 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 2 | `nr_gnb` | container | `eth0` | `clean` | _clean_ |
| 3 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 4 | `upf` | container | `eth0` | `clean` | _clean_ |
| 5 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 6 | 🎯 `rtpengine` | container | `eth0` | `drops_attributed_here` | `qdisc_netem`: 341 dropped, 44.3% |
| 7 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 8 | `upf` | container | `eth0` | `clean` | _clean_ |
| 9 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 10 | `nr_gnb` | container | `eth0` | `clean` | _clean_ |
| 11 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 12 | `e2e_ue2` | container | `eth0` | `clean` | _clean_ |

### Localized Synthesis

**Verdict:** `localized`  
**Primary suspect NF:** `rtpengine`  
**Confidence:** high

**Summary:** Transport-layer fault localized to rtpengine[eth0]: qdisc_netem reports 341 packets dropped (44.29%).

**Recommendation:** Inspect tc qdisc on rtpengine: `docker exec rtpengine tc -s qdisc show dev eth0`


## Event Aggregation (Phase 1)

**1 events fired during the observation window:**

- `core.upf.activity_during_calls_collapsed` (source: `core.upf.activity_during_calls`, nf: `upf`, t=1779333397.2)  [current_value=0.02445716666666667]

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

**Summary:** A data plane failure is causing severe packet loss and breaking media flow during active calls, with RTPEngine and UPF as the primary suspects, while the flagged signaling metrics at P-CSCF, I-CSCF, S-CSCF, and SMF are demoted as they merely reflect expected healthy activity during VoNR call setup.

**Ranked hypotheses:**

- **`h1`** (fit=0.90, nf=rtpengine, specificity=moderate):
    - **Statement:** RTPEngine is the source of the elevated rtpengine_loss_ratio (matching branch vonr_rtp_loss), causing the RTCP-reported loss on the media plane.
    - **Supporting events:** `core.upf.activity_during_calls_collapsed`
    - **Falsification probes:**
        - measure_rtt from upf to rtpengine to identify drops on the media path
        - examine tc -s qdisc show on rtpengine to detect kernel-level packet drops
- **`h2`** (fit=0.80, nf=upf, specificity=moderate):
    - **Statement:** UPF is the source of the collapsed upf_activity_during_calls (matching branch vonr_media_stops), causing the deficit in data plane throughput.
    - **Supporting events:** `core.upf.activity_during_calls_collapsed`
    - **Falsification probes:**
        - measure_rtt from rtpengine to upf to check for N6 downlink path drops
        - examine UPF internal logs and drop counters for packet forwarding errors


## Falsification Plans (Phase 4)

**2 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `rtpengine`)

**Hypothesis:** RTPEngine is the source of the elevated rtpengine_loss_ratio (matching branch vonr_rtp_loss), causing the RTCP-reported loss on the media plane.

**Probes (3):**
1. **`get_dp_quality_gauges`** — window_seconds=120 to check rtpengine.errors_per_second
    - *Expected if hypothesis holds:* Spike in rtpengine.errors_per_second, indicating active relay loop errors.
    - *Falsifying observation:* Value within typical range (0.0, 0.0), showing the metric stays at its healthy baseline.
2. **`measure_rtt`** — upf to rtpengine
    - *Expected if hypothesis holds:* Packet loss observed on the path from upf to rtpengine.
    - *Falsifying observation:* The probe's reading is inconsistent with rtpengine being the source (e.g. the metric stays at its healthy baseline, or the loss is observed on a path that does not traverse rtpengine).
3. **`measure_rtt`** — pcscf to rtpengine
    - *Expected if hypothesis holds:* Packet loss also observed on this path, isolating the deviation to rtpengine.
    - *Falsifying observation:* 0% packet loss, meaning the deviation observed in the upf to rtpengine probe is attributable to upf or the network, not rtpengine.

*Notes:* KB candidate check for rtpengine_loss_ratio branch and isolating RTPEngine from the UPF-RTPEngine path.

### Plan for `h2` (target: `upf`)

**Hypothesis:** UPF is the source of the collapsed upf_activity_during_calls (matching branch vonr_media_stops), causing the deficit in data plane throughput.

**Probes (3):**
1. **`get_dp_quality_gauges`** — window_seconds=120 to check upf.activity_during_calls
    - *Expected if hypothesis holds:* Drop in activity_during_calls indicating active calls reported but no media flowing.
    - *Falsifying observation:* Value within typical range (0.3, 1.0), meaning the metric stays at its healthy baseline.
2. **`measure_rtt`** — rtpengine to upf
    - *Expected if hypothesis holds:* Packet loss observed on the path from rtpengine to upf.
    - *Falsifying observation:* The probe's reading is inconsistent with upf being the source (e.g. the metric stays at its healthy baseline, or the loss is observed on a path that does not traverse upf).
3. **`measure_rtt`** — smf to upf
    - *Expected if hypothesis holds:* Packet loss also observed on this path, isolating the deviation to upf.
    - *Falsifying observation:* 0% packet loss, meaning the deviation observed in the rtpengine to upf probe is attributable to rtpengine or the network, not upf.

*Notes:* KB candidate check for collapsed upf_activity_during_calls and isolating UPF from the RTPEngine-UPF path.


## Parallel Investigators (Phase 5)

**3 sub-Investigator verdict(s):** **1 INCONCLUSIVE**, **2 DISPROVEN**

### `h1` — ❓ **INCONCLUSIVE**

**Hypothesis:** RTPEngine is the source of the elevated rtpengine_loss_ratio (matching branch vonr_rtp_loss), causing the RTCP-reported loss on the media plane.

**Reasoning:** [Multi-shot consensus — DISAGREEMENT. Shot 1 returned NOT_DISPROVEN; shot 2 returned DISPROVEN. Two independent samples of the same Investigator on the same plan reached opposite conclusions. The reconciler forces verdict to INCONCLUSIVE because we cannot trust either shot in isolation when the underlying LLM judgment is unstable.]

Shot 1 (NOT_DISPROVEN): Triangulation probes confirm the packet loss is completely localized to the RTPEngine container boundary. Traffic terminating at RTPEngine from both UPF and P-CSCF showed significant packet loss (~24% and ~39%), whereas a triangulation probe between UPF and P-CSCF (bypassing RTPEngine) showed 0% loss. While the relay loop errors metric (rtpengine.errors_per_second) was 0, this only refines the location of the fault from the application layer to the container's network boundary or kernel layer; it does not exonerate RTPEngine as the source.

Shot 2 (DISPROVEN): The hypothesis is falsified by direct evidence showing RTPEngine's relay loop and network interfaces are entirely healthy. The internal relay-loop metric `rtpengine.errors_per_second_(total)` is 0, contradicting any internal packet rejection. Additionally, transport-layer probes (`measure_rtt`) from UPF to RTPEngine, P-CSCF to RTPEngine, and RTPEngine to UPF all show 0% packet loss, ruling out container egress/ingress congestion. This isolates the packet drops away from RTPEngine, meaning the RTCP-reported `loss_ratio` must be originating downstream (likely at the UPF).

**Probes executed (4):**
- **window_seconds=120 to check rtpengine.errors_per_second** ✗ CONTRADICTS
    - *Tool:* `get_diagnostic_metrics(at_time_ts=1779333363.57062, nfs=["rtpengine"])`
    - *Observation:* [EVIDENCE: get_diagnostic_metrics(at_time_ts=1779333363.57062, nfs=["rtpengine"]) -> "rtpengine.errors_per_second_(total) = 0"]
    - *Comment:* The lack of application-layer errors contradicts the plan's expectation of relay loop drops, but refines the fault to the container's network interface.
- **upf to rtpengine** ✓ CONSISTENT
    - *Tool:* `measure_rtt("upf", "rtpengine")`
    - *Observation:* [EVIDENCE: measure_rtt("upf", "rtpengine") -> "24.2424% packet loss"]
    - *Comment:* Packet loss observed on the path from UPF to RTPEngine, confirming the deviation on the media path.
- **pcscf to rtpengine** ✓ CONSISTENT
    - *Tool:* `measure_rtt("pcscf", "rtpengine")`
    - *Observation:* [EVIDENCE: measure_rtt("pcscf", "rtpengine") -> "39.3939% packet loss"]
    - *Comment:* Packet loss observed on the path from P-CSCF to RTPEngine, confirming drops affect multiple paths terminating at RTPEngine.
- **upf to pcscf for triangulation** ✓ CONSISTENT
    - *Tool:* `measure_rtt("upf", "pcscf")`
    - *Observation:* [EVIDENCE: measure_rtt("upf", "pcscf") -> "0% packet loss"]
    - *Comment:* Traffic bypassing RTPEngine experiences no packet loss, confirming the network itself is healthy and isolating the fault squarely to RTPEngine's boundary.

**Alternative suspects:** upf

### `h2` — ❌ **DISPROVEN**

**Hypothesis:** UPF is the source of the collapsed upf_activity_during_calls (matching branch vonr_media_stops), causing the deficit in data plane throughput.

**Reasoning:** [Multi-shot consensus — both shots returned DISPROVEN.]

Shot 1: Data plane metrics confirm that upf_activity_during_calls has collapsed to 0.025, validating the data plane throughput deficit. Probing the network path from rtpengine to upf revealed ~28.7% packet loss, which initially appeared consistent with a UPF issue. However, a triangulation probe from smf to upf showed 0% packet loss. According to triangulation principles, since the path from smf to upf is healthy while the path from rtpengine to upf is lossy, the packet loss originates at rtpengine's egress or the intervening network, not at UPF ingress. This contradicts the hypothesis that UPF is the source.

Shot 2: Triangulation probes confirm that UPF is not the source of the dropped packets. While the path from RTPEngine to UPF experiences ~26% packet loss, the path from SMF to UPF experiences 0% packet loss. This isolates the loss to RTPEngine's egress or the network path between RTPEngine and UPF, falsifying the hypothesis that UPF itself is the source of the fault.

**Probes executed (3):**
- **window_seconds=120 to check upf.activity_during_calls** ✓ CONSISTENT
    - *Tool:* `get_diagnostic_metrics(at_time_ts=1779333363.57062, nfs=["upf"])`
    - *Observation:* [EVIDENCE: get_diagnostic_metrics(at_time_ts=1779333363.57062, nfs=["upf"]) -> "derived.upf_activity_during_calls = 0.02519 [derived, ratio]"]
    - *Comment:* The upf_activity_during_calls metric has dropped to near zero (well below the healthy range of [0.3, 1]), indicating active calls exist but no media is flowing. This confirms the symptoms but does not isolate the source.
- **rtpengine to upf** ✓ CONSISTENT
    - *Tool:* `measure_rtt("rtpengine", "upf")`
    - *Observation:* [EVIDENCE: measure_rtt("rtpengine", "upf") -> "66 packets transmitted, 47 received, 28.7879% packet loss"]
    - *Comment:* The ~28.7% packet loss observed on this path is consistent with the hypothesis, but as noted in the plan, it conflates UPF issues with drops at rtpengine egress or the intervening network.
- **smf to upf** ✗ CONTRADICTS
    - *Tool:* `measure_rtt("smf", "upf")`
    - *Observation:* [EVIDENCE: measure_rtt("smf", "upf") -> "66 packets transmitted, 66 received, 0% packet loss"]
    - *Comment:* Triangulating by pinging UPF from SMF shows 0% loss. This localizes the drop to RTPEngine (or the path specifically from RTPEngine), exonerating UPF as the source.

**Alternative suspects:** rtpengine

### `h_promoted_rtpengine` — ❌ **DISPROVEN**

**Hypothesis:** rtpengine is the source of the anomaly named in the alternative_suspects of the original verdict tree.

**Reasoning:** Evidence directly contradicts the hypothesis that rtpengine is the source of the anomaly. The rtpengine container is currently UP and running normally, and its internal relay loop is healthy with 0 errors per second. Furthermore, network reachability probes from both the UPF and P-CSCF to RTPEngine returned 0% packet loss, confirming there are no unreachability or inbound network congestion issues on those paths.

**Probes executed (4):**
- **Check the container state for rtpengine.** ✗ CONTRADICTS
    - *Tool:* `get_network_status()`
    - *Observation:* [EVIDENCE: get_network_status() -> ""rtpengine": "running""]
    - *Comment:* The rtpengine container is running normally, which contradicts the hypothesis expectation that it would be EXITED, DOWN, or continuously restarting.
- **Read rtpengine.errors_per_second over a 120s window.** ✗ CONTRADICTS
    - *Tool:* `get_diagnostic_metrics(at_time_ts=1779333363.57062, nfs=["rtpengine"])`
    - *Observation:* [EVIDENCE: get_diagnostic_metrics(1779333363.57062, ["rtpengine"]) -> "rtpengine.errors_per_second_(total) = 0 [gauge, errors_per_second]"]
    - *Comment:* The errors_per_second metric is 0, showing that the rtpengine internal relay loop is healthy and not experiencing any drops, contradicting the expectation of a spike.
- **upf -> rtpengine_ip** ✗ CONTRADICTS
    - *Tool:* `measure_rtt("upf", "rtpengine")`
    - *Observation:* [EVIDENCE: measure_rtt("upf", "rtpengine") -> "66 packets transmitted, 66 received, 0% packet loss"]
    - *Comment:* Zero packet loss from the UPF to RTPEngine contradicts the expectation of packet loss or unreachability on this path.
- **pcscf -> rtpengine_ip (Disambiguation partner to isolate RTPEngine from the UPF path)** ✗ CONTRADICTS
    - *Tool:* `measure_rtt("pcscf", "rtpengine")`
    - *Observation:* [EVIDENCE: measure_rtt("pcscf", "rtpengine") -> "66 packets transmitted, 66 received, 0% packet loss"]
    - *Comment:* Zero packet loss from P-CSCF to RTPEngine confirms RTPEngine is fully reachable, exonerating RTPEngine's ingress as the source of loss.

**Alternative suspects:** upf, nr_gnb


## Evidence Validation (Phase 6)

**Overall verdict:** clean
**Overall confidence:** high

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 12 | 4/4 | clean | high |
| `InvestigatorAgent_h2` | 9 | 3/3 | clean | high |
| `InvestigatorAgent_h_promoted_rtpengine` | 5 | 4/4 | clean | high |


## Ground Truth

**Failure domain:** ims_media  
**Protocol impact:** RTP  
**Affected components:** rtpengine  
**Severity:** degraded

## Agent Diagnosis

**Model:** v7-adk/pro=gemini-3.1-pro-preview+flash=gemini-3.5-flash  
**Time to diagnosis:** 748.1s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: Transport-layer fault localized to rtpengine[eth0]: qdisc_netem reports 341 packets dropped (44.29%).
> - **timeline**:
>     1. Path walk initiated on flow `vonr_media`.
>     2. Attribution at rtpengine[eth0]: drops_attributed_here due to qdisc_netem dropping 341 packets (44.29%).
>     3. Path walk concluded with high confidence transport-layer localization.
> - **root_cause**: Kernel-level packet drop on rtpengine's egress: `tc netem` qdisc dropping 30% of packets. (primary_suspect_nf: `rtpengine`)
> - **affected_components**:
>     - `rtpengine`: Root Cause
> - **recommendation**: Inspect tc qdisc on rtpengine: `docker exec rtpengine tc -s qdisc show dev eth0`
> - **confidence**: high
> - **verdict_kind**: localized
> - **explanation**: | # | hop | kind | iface | prober | attribution |
> |---|-----|------|-------|--------|-------------|
> | 1 | e2e_ue1 | container | eth0 | KernelHopProber | clean |
> | 2 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 3 | nr_gnb | container | eth0 | KernelHopProber | clean |
> | 4 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 5 | upf | container | eth0 | KernelHopProber | clean |
> | 6 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 7 | rtpengine | container | eth0 | KernelHopProber | drops_attributed_here (qdisc_netem, 341 dropped, 44.3%) 🎯 |
> | 8 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 9 | upf | container | eth0 | KernelHopProber | clean |
> | 10 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 11 | nr_gnb | container | eth0 | KernelHopProber | clean |
> | 12 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 13 | e2e_ue2 | container | eth0 | KernelHopProber | clean |
> 
> ```
> rtpengine[eth0] qdisc=netem, authored loss=30%: sent=770 dropped=341 (44.29%)
> ---tc -s qdisc show dev eth0---
> qdisc netem 80a2: root refcnt 9 limit 1000 loss 30%
>  Sent 640297 bytes 770 pkt (dropped 341, overlimits 0 requeues 0) 
>  backlog 0b 0p requeues 0
> ```
> 
> Classifier rationale: label=mixed. Both transport-layer (3) and application-layer (1) signals are load-bearing. Path walk runs first; falls through to the application-layer pipeline if the walk produces null localization.
> Transport signals: derived.rtpengine_loss_ratio (spike, score=4.28) — KB-labeled transport: ims.rtpengine.loss_ratio (spike, score=4.28); derived.upf_activity_during_calls (drop, score=4.28) — KB-labeled transport: core.upf.activity_during_calls (drop, score=4.28); normalized.upf.gtp_indatapktn3upf_per_ue (spike, score=4.28) — KB-labeled transport: core.upf.gtp_indatapktn3upf_per_ue (spike, score=4.28)
> Application signals: normalized.smf.bearers_per_ue (spike, score=4.28) — KB-labeled application: core.smf.bearers_per_ue (spike, score=4.28)
> Ambiguous signals: normalized.icscf.cdp_replies_per_ue (spike, score=4.28) — KB-labeled mixed: ims.icscf.cdp_replies_per_ue (spike, score=4.28); normalized.icscf.core:rcv_requests_register_per_ue (spike, score=4.28) — KB-labeled mixed: ims.icscf.rcv_requests_register_per_ue (spike, score=4.28); normalized.pcscf.core:rcv_requests_register_per_ue (spike, score=4.28) — KB-labeled mixed: ims.pcscf.rcv_requests_register_per_ue (spike, score=4.28); normalized.pcscf.dialogs_per_ue (spike, score=4.28) — KB-labeled mixed: ims.pcscf.dialogs_per_ue (spike, score=4.28); normalized.scscf.cdp_replies_per_ue (spike, score=4.28) — KB-labeled mixed: ims.scscf.cdp_replies_per_ue (spike, score=4.28) [+1 more]

### Scoring Breakdown

**Overall score: 100%**

**Scorer assessment:** The agent provided an exceptionally accurate diagnosis, correctly identifying the 30% packet loss on the RTPEngine egress path with precise tool evidence.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | Yes | The agent correctly identified the root cause as packet drops on the rtpengine egress path, specifically identifying the 30% packet loss on rtpengine. |
| Component overlap | 100% | The agent correctly identified 'rtpengine' as the primary affected component and labeled it as the 'Root Cause'. |
| Severity correct | Yes | The agent correctly identified the issue as a packet loss degradation (30% to 44% packet drops) rather than a complete outage. |
| Fault type identified | Yes | The agent correctly identified the fault type as packet drops/loss on the transport layer. |
| Layer accuracy | Yes | No layer status information was provided in the intermediate network analysis, so no misattribution was detected. |
| Confidence calibrated | Yes | The agent expressed high confidence, which is fully justified given the precise identification of the packet loss and the exact tc netem configuration. |

**Ranking position:** #1 — The correct root cause (rtpengine packet loss) was identified as the primary and only suspect.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 762,654 |
| Output tokens | 10,693 |
| Thinking tokens | 50,507 |
| **Total tokens** | **823,854** |

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
| NetworkAnalystAgent | 131,318 | 8 | 4 |
| NetworkAnalystAgent | 197,744 | 11 | 5 |
| Phase 3 NetworkAnalyst__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 14,416 | 0 | 1 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 17,751 | 0 | 1 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| InvestigatorAgent_h1 | 134,152 | 7 | 6 |
| InvestigatorAgent_h1 | 87,900 | 5 | 4 |
| InvestigatorAgent_h1__reconciliation | 0 | 0 | 0 |
| InvestigatorAgent_h2 | 57,652 | 4 | 3 |
| InvestigatorAgent_h2 | 82,497 | 5 | 4 |
| InvestigatorAgent_h2__reconciliation | 0 | 0 | 0 |
| Phase5FanOutAudit | 0 | 0 | 0 |
| Phase6.5CandidatePool | 0 | 0 | 0 |
| InstructionGeneratorAgent | 14,862 | 0 | 1 |
| Phase 6.5 Reinvestigation IG__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 14,914 | 0 | 1 |
| Phase 6.5 Reinvestigation IG__guardrail | 0 | 0 | 0 |
| Phase 6.5 Reinvestigation IG__guardrail | 0 | 0 | 0 |
| InvestigatorAgent_h_promoted_rtpengine | 52,130 | 5 | 3 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 18,518 | 0 | 1 |
| Phase 7 Synthesis__guardrail | 0 | 0 | 0 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 881.0s
