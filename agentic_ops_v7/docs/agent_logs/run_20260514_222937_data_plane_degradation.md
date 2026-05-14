# Episode Report: Data Plane Degradation

**Agent:** v7  
**Episode ID:** ep_20260514_221925_data_plane_degradation  
**Date:** 2026-05-14T22:19:26.820186+00:00  
**Duration:** 610.1s  

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

- **Propagation window:** 125s (ObservationTrafficAgent drove traffic for this window; verifier added wait=0s on top)
- **Nodes with significant deltas:** 6
- **Nodes with any drift:** 6

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 47.33 (per-bucket threshold: 28.18, context bucket (1, 1), trained on 323 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following metrics deviate from their learned-healthy baseline. Treat each as a semantic observation (meaning + numbers), not a number alone — the KB's interpretation is the authoritative reading.

- **`derived.upf_activity_during_calls`** (UPF activity consistency with active dialogs) — current **0.03 ratio** vs learned baseline **0.54 ratio** (MEDIUM, drop)
    - **What it measures:** Cross-layer consistency check between IMS dialog state and UPF
throughput. A drop while dialogs_per_ue is non-zero is a
smoking-gun signal for media-plane failure independent of signaling.
    - **Drop means:** Active calls reported but no media flowing — media path broken (UPF, RTPEngine, or N3 packet loss).
    - **Healthy typical range:** 0.3–1 ratio
    - **Healthy invariant:** 1.0 when traffic fully follows active calls; 0.0 when signaling says active but data plane is silent.

- **`normalized.icscf.cdp_replies_per_ue`** (I-CSCF Diameter reply rate per UE) — current **0.06 replies_per_second_per_ue** vs learned baseline **0.03 replies_per_second_per_ue** (MEDIUM, spike)
    - **What it measures:** Liveness of the I-CSCF↔HSS Cx path. Drops to 0 when HSS is unreachable OR when no signaling is occurring at the I-CSCF (idle or upstream P-CSCF partitioned).
    - **Spike means:** Either HSS is unreachable or upstream signaling has stopped reaching I-CSCF.
    - **Healthy typical range:** 0–1 replies_per_second_per_ue

- **`normalized.icscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at I-CSCF) — current **0.15 requests_per_second** vs learned baseline **0.06 requests_per_second** (MEDIUM, spike)
    - **What it measures:** Health of the P-CSCF → I-CSCF forwarding path (Mw interface). When
this drops to zero while P-CSCF REGISTER rate is still non-zero,
it's the SIGNATURE of an IMS partition between P-CSCF and I-CSCF.
    - **Spike means:** Forwarding issue on the Mw interface, or P-CSCF stopped forwarding.
    - **Healthy typical range:** 0–0.5 requests_per_second
    - **Healthy invariant:** Per-UE rate. Should closely track ims.pcscf.rcv_requests_register_per_ue.

- **`normalized.pcscf.core:rcv_requests_invite_per_ue`** (SIP INVITE rate per UE at P-CSCF) — current **0.06 requests_per_second** vs learned baseline **0.00 requests_per_second** (MEDIUM, spike)
    - **What it measures:** Call attempt rate from registered UEs. Unlike REGISTER (periodic),
INVITEs only fire when UEs place calls. Zero is normal during
quiet periods; nonzero INVITE with zero dialogs is the signature
of call setup failure.
    - **Spike means:** Fewer call attempts.
    - **Healthy typical range:** 0–0.2 requests_per_second
    - **Healthy invariant:** Per-UE rate.

- **`normalized.pcscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at P-CSCF) — current **0.20 requests_per_second** vs learned baseline **0.06 requests_per_second** (MEDIUM, spike)
    - **What it measures:** How actively UEs are refreshing their IMS registrations with the
P-CSCF. REGISTERs arrive periodically (re-registration timer) plus
at attach. Sustained zero means UEs cannot reach P-CSCF OR the
UE-to-network SIP path is broken.
    - **Spike means:** Fewer REGISTERs than expected — UE connectivity or P-CSCF reachability issue.
    - **Healthy typical range:** 0–0.5 requests_per_second
    - **Healthy invariant:** Per-UE rate — same value at any deployment scale.

- **`normalized.scscf.cdp_replies_per_ue`** (S-CSCF CDP Diameter replies per UE) — current **0.15 replies_per_second_per_ue** vs learned baseline **0.06 replies_per_second_per_ue** (MEDIUM, spike)
    - **What it measures:** Active S-CSCF Diameter traffic with HSS. Near-zero when registrations idle OR HSS partition.
    - **Spike means:** Diameter peering loss with HSS.
    - **Healthy typical range:** 0–1 replies_per_second_per_ue
    - **Healthy invariant:** Per-UE rate; varies with registration/auth load.

- **`normalized.scscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at S-CSCF) — current **0.15 requests_per_second** vs learned baseline **0.06 requests_per_second** (MEDIUM, spike)
    - **What it measures:** Health of the I-CSCF → S-CSCF forwarding path. Drop to zero while
I-CSCF is receiving REGISTERs = S-CSCF-side issue (crashed, or
I-CSCF → S-CSCF path broken).
    - **Spike means:** I-CSCF not forwarding or S-CSCF not receiving.
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

- **`normalized.upf.gtp_indatapktn3upf_per_ue`** (GTP-U uplink rate per UE (N3)) — current **1.88 packets_per_second** vs learned baseline **1.45 packets_per_second** (MEDIUM, shift)
    - **What it measures:** Health of the uplink user-plane path gNB → UPF. Drops to near-zero
during RAN or N3 outage; stays nonzero during active calls or data
sessions. Decoupled from SIP signaling (signals data plane, not
control plane).
    - **Shift means:** Either UEs not generating uplink traffic (no calls/data) or N3 path is degraded.
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

- **`normalized.upf.gtp_outdatapktn3upf_per_ue`** (GTP-U downlink rate per UE (N3)) — current **1.14 packets_per_second** vs learned baseline **1.45 packets_per_second** (MEDIUM, shift)
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


## Symptom Classifier (Phase 0.5)

**Label:** `mixed`  
**Flag counts:** transport=3, application=1, ambiguous=6

### Transport-bucket flags (3)

| Metric | Direction | Score | KB-driven reason |
|---|---|---:|---|
| `derived.upf_activity_during_calls` | drop | 4.28 | KB-labeled transport: core.upf.activity_during_calls (drop, score=4.28) |
| `normalized.upf.gtp_indatapktn3upf_per_ue` | shift | 4.28 | KB-labeled transport: core.upf.gtp_indatapktn3upf_per_ue (shift, score=4.28) |
| `normalized.upf.gtp_outdatapktn3upf_per_ue` | shift | 4.28 | KB-labeled transport: core.upf.gtp_outdatapktn3upf_per_ue (shift, score=4.28) |

### Application-bucket flags (1)

| Metric | Direction | Score | KB-driven reason |
|---|---|---:|---|
| `normalized.smf.bearers_per_ue` | spike | 4.28 | KB-labeled application: core.smf.bearers_per_ue (spike, score=4.28) |

### Ambiguous-bucket flags (6)

| Metric | Direction | Score | KB-driven reason |
|---|---|---:|---|
| `normalized.icscf.cdp_replies_per_ue` | spike | 4.28 | KB-labeled mixed: ims.icscf.cdp_replies_per_ue (spike, score=4.28) |
| `normalized.icscf.core:rcv_requests_register_per_ue` | spike | 4.28 | KB-labeled mixed: ims.icscf.rcv_requests_register_per_ue (spike, score=4.28) |
| `normalized.pcscf.core:rcv_requests_invite_per_ue` | spike | 4.28 | KB-labeled mixed: ims.pcscf.rcv_requests_invite_per_ue (spike, score=4.28) |
| `normalized.pcscf.core:rcv_requests_register_per_ue` | spike | 4.28 | KB-labeled mixed: ims.pcscf.rcv_requests_register_per_ue (spike, score=4.28) |
| `normalized.scscf.cdp_replies_per_ue` | spike | 4.28 | KB-labeled mixed: ims.scscf.cdp_replies_per_ue (spike, score=4.28) |
| `normalized.scscf.core:rcv_requests_register_per_ue` | spike | 4.28 | KB-labeled mixed: ims.scscf.rcv_requests_register_per_ue (spike, score=4.28) |

**Rationale:**

```
label=mixed. Both transport-layer (3) and application-layer (1) signals are load-bearing. Path walk runs first; falls through to the application-layer pipeline if the walk produces null localization.

Transport signals: derived.upf_activity_during_calls (drop, score=4.28) — KB-labeled transport: core.upf.activity_during_calls (drop, score=4.28); normalized.upf.gtp_indatapktn3upf_per_ue (shift, score=4.28) — KB-labeled transport: core.upf.gtp_indatapktn3upf_per_ue (shift, score=4.28); normalized.upf.gtp_outdatapktn3upf_per_ue (shift, score=4.28) — KB-labeled transport: core.upf.gtp_outdatapktn3upf_per_ue (shift, score=4.28)

Application signals: normalized.smf.bearers_per_ue (spike, score=4.28) — KB-labeled application: core.smf.bearers_per_ue (spike, score=4.28)

Ambiguous signals: normalized.icscf.cdp_replies_per_ue (spike, score=4.28) — KB-labeled mixed: ims.icscf.cdp_replies_per_ue (spike, score=4.28); normalized.icscf.core:rcv_requests_register_per_ue (spike, score=4.28) — KB-labeled mixed: ims.icscf.rcv_requests_register_per_ue (spike, score=4.28); normalized.pcscf.core:rcv_requests_invite_per_ue (spike, score=4.28) — KB-labeled mixed: ims.pcscf.rcv_requests_invite_per_ue (spike, score=4.28); normalized.pcscf.core:rcv_requests_register_per_ue (spike, score=4.28) — KB-labeled mixed: ims.pcscf.rcv_requests_register_per_ue (spike, score=4.28); normalized.scscf.cdp_replies_per_ue (spike, score=4.28) — KB-labeled mixed: ims.scscf.cdp_replies_per_ue (spike, score=4.28) [+1 more]
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
Resolved transport path to flow `data_pdu_session_user_traffic` (score=12, 11 hops on the walk). Load-bearing components: ['icscf', 'pcscf', 'scscf', 'smf', 'upf']. Other candidate flows considered: vonr_media=12, ims_registration=8, vonr_call_teardown=8, vonr_call_setup=8.
```

### Walker

**Status:** ✅ **localized**
**First attributed hop:** `upf[eth0]`
**Window:** 5s  
**Walked flow:** `data_pdu_session_user_traffic`

**Per-hop results:**

| # | Node | Kind | Iface | Attribution | Detail |
|---:|---|---|---|---|---|
| 0 | `e2e_ue1` | container | `eth0` | `clean` | _clean_ |
| 1 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 2 | `nr_gnb` | container | `eth0` | `clean` | _clean_ |
| 3 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 4 | 🎯 `upf` | container | `eth0` | `drops_attributed_here` | `qdisc_netem`: 310 dropped, 47.2% |
| 5 | `internet` | external_network | `eth0` | `inconclusive` | _no_prober_registered_: "no HopProber registered for kind='external_network'; registered kinds: ['contai |
| 6 | `upf` | container | `eth0` | `drops_attributed_here` | `qdisc_netem`: 310 dropped, 47.2% |
| 7 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 8 | `nr_gnb` | container | `eth0` | `clean` | _clean_ |
| 9 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 10 | `e2e_ue1` | container | `eth0` | `clean` | _clean_ |

### Localized Synthesis

*Walker localized; routing through the application-layer pipeline (Phases 1-7) in parallel so the compound Synthesis branch can merge walker + NA evidence into a multi-root-cause verdict. The final diagnosis appears in `Agent Diagnosis` below with `verdict_kind=compound`. See ADR `multi_fault_orchestration.md`.*

## Event Aggregation (Phase 1)

**1 events fired during the observation window:**

- `core.upf.activity_during_calls_collapsed` (source: `core.upf.activity_during_calls`, nf: `upf`, t=1778797284.4)  [current_value=0.047594500000000005]

## Correlation Analysis (Phase 2)

1 events fired but no composite hypothesis emerged. The events may be from independent faults or lack registered correlation hints in the KB.

## RAG & Operational Lessons (Phase 2.5)

### RAG retrieval — prior similar episodes

**Status:** `hits` — hits=5, top_sim=0.88, top_case=v7/ep_20260510_185748_call_quality_degradation
**Index:** `/home/ehoskas/agentic-network-ops/rag_index`  **Corpus size:** 97 cases
**Classifier label used in retrieval:** `mixed`
**Retrieval params:** k=5, min_similarity=0.4
**Hits (5):**

| Rank | Sim | Case ID | Scenario | Ground truth | Primary suspect | Score |
|---:|---:|---|---|---|---|---:|
| 0 | 88% | `v7/ep_20260510_185748_call_quality_degradation` | Call Quality Degradation | `rtpengine` | `rtpengine` | 100% |
| 1 | 87% | `v6/ep_20260430_015439_data_plane_degradation` | Data Plane Degradation | `upf` | `?` | 85% |
| 2 | 83% | `v7/ep_20260510_194005_dns_failure` | DNS Failure | `dns` | `?` | 85% |
| 3 | 83% | `v6/ep_20260429_160912_s_cscf_crash` | S-CSCF Crash | `scscf` | `?` | 100% |
| 4 | 82% | `v6/ep_20260501_012004_data_plane_degradation` | Data Plane Degradation | `upf` | `?` | 90% |

*Rendered block injected into the NA prompt's `{prior_similar_episodes}` placeholder: 4392 chars. Source paths are inlined in the block so the EvidenceValidator can audit any case the NA cites.*

### Operational lessons — hand-authored rules corpus

**Status:** `injected` — lessons=15, chars=14426
**Path:** `/home/ehoskas/agentic-network-ops/agentic_ops_common/rag/lessons.yaml`  **Count:** 15  **Block size:** 14426 chars
**Injected lesson IDs:** `L01`, `L02`, `L03`, `L04`, `L05`, `L06`, `L07`, `L08`, `L09`, `L10`, `L11`, `L12`, `L13`, `L14`, `L15`

### NA citations of the injected content

**Cited case IDs:**
- `v7/ep_20260510_185748_call_quality_degradation`

*Citations are verbatim string matches — case_ids and lesson_ids appear in the NA's emitted text (summary, hypothesis statements, or layer notes). The EvidenceValidator can audit any cited case by following its `source_episode_path` from the retrieval table above.*

## Network Analysis (Phase 3)

**Summary:** The fired event and screener flags indicate a severe media plane failure. While call signaling appears partially active, user plane traffic is not flowing, pointing to either RTPEngine or UPF as the likely root cause, consistent with several high-similarity prior episodes.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | Network topology and container status appear normal. |
| **ran** | 🟢 GREEN | No direct evidence of a RAN failure. |
| **core** | 🟡 YELLOW | UPF, a core component, is a potential suspect and is showing anomalous traffic patterns. The SMF is also showing a spike in bearer counts. |
| **ims** | 🔴 RED | The primary symptom is the collapse of media activity (rtpengine, upf) during active calls, which is an IMS media plane function. |

**CORE evidence:**
- normalized.upf.gtp_indatapktn3upf_per_ue:shift
- normalized.upf.gtp_outdatapktn3upf_per_ue:shift

**IMS evidence:**
- derived.upf_activity_during_calls:drop

**Ranked hypotheses:**

- **`h1`** (fit=0.90, nf=rtpengine, specificity=specific):
    - **Statement:** The media plane is broken at rtpengine, which is failing to relay RTP packets. This is strongly supported by the `upf_activity_during_calls_collapsed` event and is the ground truth in the highest-similarity prior episode (v7/ep_20260510_185748_call_quality_degradation).
    - **Supporting events:** `core.upf.activity_during_calls_collapsed`
    - **Falsification probes:**
        - A `measure_rtt` probe from `upf` to `rtpengine` that shows no packet loss or abnormal latency would indicate the path is healthy, shifting suspicion away from rtpengine's network layer.
        - Directly inspecting `rtpengine`'s kernel-level network statistics for packet drops on its interfaces. An absence of drops would disprove a network-level fault at rtpengine, as per lesson L04.
- **`h2`** (fit=0.80, nf=upf, specificity=specific):
    - **Statement:** The UPF is the source of the data plane failure, dropping GTP-U packets and preventing media from reaching the rtpengine. This aligns with the `upf_activity_during_calls_collapsed` event and is supported by two high-similarity prior cases.
    - **Supporting events:** `core.upf.activity_during_calls_collapsed`
    - **Falsification probes:**
        - A `measure_rtt` probe from `rtpengine` to `upf` that shows no packet loss or latency would suggest the path to UPF is clean.
        - Probing UPF's PFCP session state via `get_nf_metrics`. Healthy session state alongside zero throughput would point to an internal UPF forwarding issue.


## Falsification Plans (Phase 4)

**2 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `rtpengine`)

**Hypothesis:** The media plane is broken at rtpengine, which is failing to relay RTP packets. This is strongly supported by the `upf_activity_during_calls_collapsed` event and is the ground truth in the highest-similarity prior episode (v7/ep_20260510_185748_call_quality_degradation).

**Probes (3):**
1. **`get_dp_quality_gauges`** — Returns rate-based MOS/loss/jitter alongside RTPEngine errors.
    - *Expected if hypothesis holds:* The `rtpengine.errors_per_second` metric shows a spike, indicating errors in the relay function.
    - *Falsifying observation:* The `rtpengine.errors_per_second` metric is zero or at its baseline, indicating no relay-loop errors are being reported by rtpengine.
2. **`measure_rtt`** — from='upf', to_ip='rtpengine'
    - *Expected if hypothesis holds:* No significant packet loss or latency is observed, which would indicate the network path to rtpengine is healthy and does not contradict the hypothesis.
    - *Falsifying observation:* High packet loss or latency is observed. This would suggest the problem lies in the network path to rtpengine, not within rtpengine itself.
3. **`measure_rtt`** — from='upf', to_ip='smf'
    - *Expected if hypothesis holds:* No significant packet loss or latency is observed. If the path to rtpengine is also healthy, it strengthens the focus on rtpengine as the source of the failure.
    - *Falsifying observation:* High packet loss or latency is observed. If the path to rtpengine also shows high loss, this would strongly suggest the fault lies with UPF's network egress or the common network fabric, falsifying the rtpengine-specific hypothesis.

*Notes:* This plan uses a direct metric from the suspect component (rtpengine.errors_per_second) and a pair of compositional path probes to isolate whether the fault is at the rtpengine application level or in the underlying network path. This directly addresses the feedback from the previous rejection.

### Plan for `h2` (target: `upf`)

**Hypothesis:** The UPF is the source of the data plane failure, dropping GTP-U packets and preventing media from reaching the rtpengine. This aligns with the `upf_activity_during_calls_collapsed` event and is supported by two high-similarity prior cases.

**Probes (3):**
1. **`get_dp_quality_gauges`** — Check UPF packet rates on N3 (towards gNB) and N6 (towards rtpengine) interfaces.
    - *Expected if hypothesis holds:* There is a significant mismatch in packet rates between ingress and egress interfaces (e.g., N6 ingress vs N3 egress for downlink), or rates on all interfaces are collapsed despite active calls.
    - *Falsifying observation:* Packet rates on UPF's ingress and egress interfaces are balanced and consistent with active call volume, indicating UPF is not the source of packet drops.
2. **`measure_rtt`** — from='rtpengine', to_ip='upf'
    - *Expected if hypothesis holds:* No significant packet loss or latency is observed, indicating the network path to UPF is healthy and consistent with the hypothesis that UPF itself is the problem.
    - *Falsifying observation:* High packet loss or latency is observed, suggesting the issue is on the network path to UPF, not a packet dropping issue within UPF.
3. **`measure_rtt`** — from='rtpengine', to_ip='pcscf'
    - *Expected if hypothesis holds:* No significant packet loss or latency is observed. If the path to UPF also shows no loss, it strengthens the hypothesis that packet loss is occurring within UPF's logic.
    - *Falsifying observation:* High packet loss or latency is observed. If the path to UPF also shows high loss, it points to a problem with rtpengine's network egress or the adjacent fabric, rather than a problem specific to UPF.

*Notes:* This plan checks the suspect component's own counters for evidence of packet loss and uses a pair of compositional path probes to distinguish between a fault within UPF versus a fault in the network path leading to it. This structure correctly addresses the prior rejection feedback.


## Parallel Investigators (Phase 5)

**3 sub-Investigator verdict(s):** **3 DISPROVEN**

### `h1` — ❌ **DISPROVEN**

**Hypothesis:** The media plane is broken at rtpengine, which is failing to relay RTP packets. This is strongly supported by the `upf_activity_during_calls_collapsed` event and is the ground truth in the highest-similarity prior episode (v7/ep_20260510_185748_call_quality_degradation).

**Reasoning:** [Multi-shot consensus — both shots returned DISPROVEN.]

Shot 1: All three probes produced evidence that contradicts the hypothesis. The `get_dp_quality_gauges` probe showed zero recent packet loss at rtpengine, which is inconsistent with a relay failure. More importantly, RTT probes from the UPF to both rtpengine and smf revealed significant packet loss (28% and 25% respectively). This indicates the problem is not with rtpengine, but rather with the UPF's network egress or the common network fabric.

Shot 2: The evidence strongly contradicts the hypothesis that rtpengine is the source of the failure. Probes measuring network connectivity from the UPF to two separate components (rtpengine and smf) both revealed high packet loss (26-32%). This indicates the problem originates at the UPF or its network egress, not rtpengine. Furthermore, a direct query to rtpengine's data plane metrics during the anomaly window showed zero packet loss, which is inconsistent with a failing relay.

**Probes executed (3):**
- **Returns rate-based MOS/loss/jitter alongside RTPEngine errors.** ✗ CONTRADICTS
    - *Tool:* `print(default_api.get_dp_quality_gauges(at_time_ts = 1778797273.155766))`
    - *Observation:* [EVIDENCE: get_dp_quality_gauges(at_time_ts=1778797273.155766) -> "loss (recent)  : 0.00"]
    - *Comment:* The plan expected a spike in `rtpengine.errors_per_second`. While this metric was not available, the related `loss (recent)` metric was 0. This contradicts the hypothesis that rtpengine is failing to relay packets, as this would be expected to cause packet loss.
- **from='upf', to_ip='rtpengine'** ✗ CONTRADICTS
    - *Tool:* `print(default_api.measure_rtt(container = "upf", target = "rtpengine"))`
    - *Observation:* [EVIDENCE: measure_rtt('upf', 'rtpengine') -> "66 packets transmitted, 47 received, 28.7879% packet loss"]
    - *Comment:* The observation of high packet loss falsifies the hypothesis by indicating the problem lies in the network path to rtpengine, not within the rtpengine application itself.
- **from='upf', to_ip='smf'** ✗ CONTRADICTS
    - *Tool:* `print(default_api.measure_rtt(container = "upf", target = "smf"))`
    - *Observation:* [EVIDENCE: measure_rtt('upf', 'smf') -> "66 packets transmitted, 49 received, 25.7576% packet loss"]
    - *Comment:* This triangulation probe also showed high packet loss from the UPF to an unrelated component (smf). This strongly suggests the fault lies with the UPF's network egress or the common network fabric, not rtpengine.

**Alternative suspects:** upf

### `h2` — ❌ **DISPROVEN**

**Hypothesis:** The UPF is the source of the data plane failure, dropping GTP-U packets and preventing media from reaching the rtpengine. This aligns with the `upf_activity_during_calls_collapsed` event and is supported by two high-similarity prior cases.

**Reasoning:** [Multi-shot consensus — both shots returned DISPROVEN.]

Shot 1: The probe measuring round-trip time from `rtpengine` to `upf` showed a high packet loss of 27.27%, which directly contradicts the hypothesis's expectation of a healthy network path. A second, triangulating probe from `rtpengine` to `pcscf` showed 0% packet loss. This comparison indicates the fault is not a general problem with `rtpengine`'s egress, but is specific to the path towards the UPF, thus falsifying the hypothesis that the UPF's internal logic is the source of the packet drops.

Shot 2: The hypothesis that the UPF itself is the source of packet drops is disproven. A `measure_rtt` probe from 'rtpengine' to 'upf' showed 33.3% packet loss, which directly contradicts the expectation that the network path to the UPF would be healthy. A subsequent triangulation probe from 'rtpengine' to 'pcscf' showed 0% packet loss, indicating that rtpengine's networking stack is functional and the issue is specific to the network path leading to the UPF, rather than an internal dropping issue within the UPF.

**Probes executed (3):**
- **Check UPF packet rates on N3 (towards gNB) and N6 (towards rtpengine) interfaces.** ✓ CONSISTENT
    - *Tool:* `print(default_api.get_dp_quality_gauges(at_time_ts = 1778797273.155766, window_seconds = 120))`
    - *Observation:* [EVIDENCE: get_dp_quality_gauges(at_time_ts=1778797273.155766, window_seconds=120) -> "UPF:\n    in  packets/sec: 2.9\n    out packets/sec: 1.8\n... RTPEngine:\n    packets/sec    : 0.9"]
    - *Comment:* The packet rates for both UPF and RTPEngine are extremely low, which is consistent with the hypothesis that there is a data plane failure, and aligns with the `upf_activity_during_calls_collapsed` event.
- **from='rtpengine', to_ip='upf'** ✗ CONTRADICTS
    - *Tool:* `print(default_api.measure_rtt(container = 'rtpengine', target = 'upf'))`
    - *Observation:* [EVIDENCE: measure_rtt('rtpengine', 'upf') -> "66 packets transmitted, 48 received, 27.2727% packet loss"]
    - *Comment:* This probe shows significant packet loss on the network path from rtpengine to UPF. This contradicts the hypothesis that the UPF itself is the source of the drops, and instead points to a network-level issue on the path leading to the UPF.
- **from='rtpengine', to_ip='pcscf'** ✓ CONSISTENT
    - *Tool:* `print(default_api.measure_rtt(container = 'rtpengine', target = 'pcscf'))`
    - *Observation:* [EVIDENCE: measure_rtt('rtpengine', 'pcscf') -> "66 packets transmitted, 66 received, 0% packet loss"]
    - *Comment:* This probe showing a healthy path from rtpengine to pcscf serves as a triangulation point. Since this path is clean while the path to the UPF is lossy, it isolates the problem to the network path specific to the UPF, ruling out a general networking issue at the rtpengine source.

**Alternative suspects:** network fabric between rtpengine and upf

### `h_promoted_upf` — ❌ **DISPROVEN**

**Hypothesis:** upf is the source of the anomaly named in the alternative_suspects of the original verdict tree.

**Reasoning:** The hypothesis that UPF is the source of a data plane anomaly is disproven by direct observation. Probes show a receiver-reported packet loss ratio of zero, indicating no media loss on the path. If UPF were dropping packets, the loss ratio at rtpengine would be elevated.

**Probes executed (3):**
- **Probe reads `rtpengine.loss_ratio` and finds a spike. This is consistent with receivers reporting packet loss back to rtpengine.** ✗ CONTRADICTS
    - *Tool:* `default_api.get_dp_quality_gauges(at_time_ts = 1778797273.155766, window_seconds = 120)`
    - *Observation:* [EVIDENCE: get_dp_quality_gauges(at_time_ts=1778797273.155766, window_seconds=120) -> "loss (recent)  : 0.00"]
    - *Comment:* The packet loss reported by rtpengine is 0.00, which contradicts the expectation of a spike. This suggests no packet loss is being observed by the receivers, which falsifies the hypothesis that UPF is dropping media packets.
- **Probe reads `core.upf.gtp_outdatapktn3upf_per_ue` and finds a drop. When seen with a spike in `rtpengine.loss_ratio`, it suggests the drop is happening at or before the UPF's N3 egress.** ✗ CONTRADICTS
    - *Tool:* `default_api.get_dp_quality_gauges(at_time_ts = 1778797273.155766, window_seconds = 120)`
    - *Observation:* [EVIDENCE: get_dp_quality_gauges(at_time_ts=1778797273.155766, window_seconds=120) -> "out packets/sec: 1.8"]
    - *Comment:* While the absolute value of UPF's output pps is observed, the primary signal, `rtpengine.loss_ratio`, is zero. A healthy loss ratio indicates that even if there were a drop in UPF throughput, it is not causing packet loss from the perspective of the call. This contradicts the hypothesis.
- **Probe reads `rtpengine.errors_per_second` and finds a value of zero. A non-zero value would point to an issue within rtpengine itself, but a zero value (in the presence of loss) points the finger away from rtpengine's relay-loop.** ~ AMBIGUOUS
    - *Tool:* `default_api.get_diagnostic_metrics(at_time_ts = 1778797273.155766, nfs = ["rtpengine"])`
    - *Observation:* [EVIDENCE: get_diagnostic_metrics(at_time_ts=1778797273.155766, nfs=['rtpengine']) -> "rtpengine.errors_per_second_(total) = 0 [gauge, errors_per_second]"]
    - *Comment:* The probe found `rtpengine.errors_per_second` is 0, which is technically consistent with the hypothesis (which expects the problem to be at UPF, not rtpengine). However, this result must be interpreted alongside the `loss_ratio`. Since the loss ratio is also 0, the combined evidence indicates a completely healthy media plane, which contradicts the overall premise of the hypothesis.


## Evidence Validation (Phase 6)

**Overall verdict:** clean
**Overall confidence:** high

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 6 | 3/3 | clean | high |
| `InvestigatorAgent_h2` | 6 | 3/3 | clean | high |
| `InvestigatorAgent_h_promoted_upf` | 2 | 3/3 | clean | high |


## Ground Truth

**Failure domain:** data_plane  
**Protocol impact:** GTP-U  
**Affected components:** upf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v7-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 473.1s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: Transport-layer fault localized to upf[eth0]: qdisc_netem reports 310 packets dropped (47.2%).
> - **timeline**:
>     1. Path walk initiated for flow data_pdu_session_user_traffic.
>     2. Fault localized at hop 5 (upf[eth0]) due to qdisc_netem dropping 310 packets (47.2%).
>     3. Path walk completed, yielding a high-confidence transport-layer diagnosis.
> - **root_cause**: Kernel-level packet drop on the UPF's eth0 interface. A `tc netem` traffic control queuing discipline is configured to introduce 30% packet loss and was observed dropping 47.2% of packets for the probed flow. (primary_suspect_nf: `upf`)
> - **affected_components**:
>     - `upf`: Root Cause
> - **recommendation**: Inspect the traffic control configuration on the UPF container's eth0 interface by running: `docker exec upf tc -s qdisc show dev eth0`.
> - **confidence**: high
> - **verdict_kind**: localized
> - **explanation**: The path walk for the `data_pdu_session_user_traffic` flow localized a transport-layer fault to the `upf` container. The bisection report is as follows:
> 
> | # | hop | kind | iface | prober | attribution |
> |---|-----|------|-------|--------|-------------|
> | 1 | e2e_ue1 | container | eth0 | KernelHopProber | clean |
> | 2 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 3 | nr_gnb | container | eth0 | KernelHopProber | clean |
> | 4 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 5 | upf | container | eth0 | KernelHopProber | drops_attributed_here (qdisc_netem, 310 dropped, 47.2%) 🎯 |
> | 6 | internet | external_network | eth0 | <unregistered> | inconclusive (no_prober_registered) |
> | 7 | upf | container | eth0 | KernelHopProber | drops_attributed_here (qdisc_netem, 310 dropped, 47.2%) |
> | 8 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 9 | nr_gnb | container | eth0 | KernelHopProber | clean |
> | 10 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 11 | e2e_ue1 | container | eth0 | KernelHopProber | clean |
> 
> Evidence for the first-attributed hop (`upf[eth0]`):
> ```
> upf[eth0] qdisc=netem, authored loss=30%: sent=657 dropped=310 (47.18%)
> ---tc -s qdisc show dev eth0---
> qdisc netem 8055: root refcnt 9 limit 1000 loss 30%
>  Sent 247485 bytes 657 pkt (dropped 310, overlimits 0 requeues 0) 
>  backlog 0b 0p requeues 0
> ```
> 
> Classifier rationale for path-walk: label=mixed. Both transport-layer (3) and application-layer (1) signals are load-bearing. Path walk runs first; falls through to the application-layer pipeline if the walk produces null localization.

### Scoring Breakdown

**Overall score: 100%**

**Scorer assessment:** The agent provided an exceptionally accurate and precise diagnosis, correctly identifying the root cause, affected component, severity, and fault type with high confidence. Layer attribution was also correct.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | Yes | The agent correctly identified 'Kernel-level packet drop on the UPF's eth0 interface' as the root cause, which directly matches the simulated 30% packet loss on the UPF. The mention of 'tc netem' is the injection mechanism, but the core observable failure mode (packet drop) is accurately described. |
| Component overlap | 100% | The agent correctly identified 'upf' as the 'Root Cause' in the affected_components list, which is the primary affected component in the simulated failure. |
| Severity correct | Yes | The agent identified 'packet drop' and quantified it as '47.2% of packets', which accurately reflects a degradation rather than a complete outage, matching the simulated 'degrade' and 'quality drops'. |
| Fault type identified | Yes | The agent identified 'packet drop' as the fault type, which is semantically equivalent to the simulated 'packet loss'. |
| Layer accuracy | Yes | The ground truth states 'upf' belongs to the 'core' layer. The agent's network analysis correctly rates the 'core' layer as 'yellow' and explicitly notes 'UPF, a core component, is a potential suspect'. While the 'ims' layer is rated 'red' due to the impact on media activity, the UPF's own layer attribution is correct. |
| Confidence calibrated | Yes | The agent's diagnosis is highly accurate and specific, identifying the exact component, failure type, and even the injection mechanism. A 'high' confidence level is appropriate for such a precise and correct diagnosis. |

**Ranking position:** #1 — The agent provided a single, definitive diagnosis, which was correct.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 386,134 |
| Output tokens | 10,847 |
| Thinking tokens | 37,243 |
| **Total tokens** | **434,224** |

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
| NetworkAnalystAgent | 42,504 | 3 | 2 |
| Phase 3 NetworkAnalyst__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 31,855 | 1 | 2 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 17,291 | 0 | 1 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| InvestigatorAgent_h1 | 45,425 | 3 | 3 |
| InvestigatorAgent_h1 | 62,014 | 3 | 4 |
| InvestigatorAgent_h1__reconciliation | 0 | 0 | 0 |
| InvestigatorAgent_h2 | 47,721 | 3 | 3 |
| InvestigatorAgent_h2 | 32,156 | 3 | 2 |
| InvestigatorAgent_h2__reconciliation | 0 | 0 | 0 |
| Phase5FanOutAudit | 0 | 0 | 0 |
| Phase6.5CandidatePool | 0 | 0 | 0 |
| InstructionGeneratorAgent | 57,041 | 3 | 4 |
| Phase 6.5 Reinvestigation IG__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 39,489 | 1 | 2 |
| Phase 6.5 Reinvestigation IG__guardrail | 0 | 0 | 0 |
| InvestigatorAgent_h_promoted_upf | 42,717 | 2 | 3 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 16,011 | 0 | 1 |
| Phase 7 Synthesis__guardrail | 0 | 0 | 0 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 610.1s
