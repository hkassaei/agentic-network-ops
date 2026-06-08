# Episode Report: PyHSS Clock Skew (Observability)

**Agent:** v7  
**Episode ID:** ep_20260608_195604_pyhss_clock_skew_(observabilit  
**Date:** 2026-06-08T19:56:05.935314+00:00  
**Duration:** 1403.5s  

---

## Scenario

**Category:** application  
**Blast radius:** single_nf  
**Description:** Step PyHSS's wall clock forward by 47 minutes via libfaketime. Verified in CDR-0001 §1: this lab's PyHSS uses pure counter-based SQN (no time dependency), Diameter Cx is cleartext SCTP (no certs), and Kamailio's `date_check` module is not loaded. Result: NO functional impact. All UE registrations and calls continue working. The fault is purely OBSERVABILITY-degrading — PyHSS log timestamps and Diameter Session-Id high-32 fields drift 47 minutes into the future. The screener and the log-correlation surface will look anomalous, but no protocol actually breaks. NEGATIVE-CONTROL test: the correct v7 verdict is INCONCLUSIVE / 'observability anomaly, no functional fault.' If v7 hallucinates a PyHSS auth or Diameter outage to explain the timestamp drift, that's a false-positive failure mode we need to harden against. **Requires one-time PyHSS Dockerfile prep (libfaketime + LD_PRELOAD + /etc/faketimerc); see CDR-0001 §1 Injection mechanism.** Without prep, fault injection fails fast with a clear message; heal is a harmless no-op.

## Faults Injected

- **clock_skew** on `pyhss` — {'skew_seconds': 2820}

## Baseline (Pre-Fault)

Stack phase before injection: **ready**
All containers running at baseline.

## Fault Propagation Verification

**Verdict:** ✅ `confirmed`

- **Propagation window:** 125s (ObservationTrafficAgent drove traffic for this window; verifier added wait=0s on top)
- **Nodes with significant deltas:** 5
- **Nodes with any drift:** 5

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 43.75 (per-bucket threshold: 28.18, context bucket (1, 1), trained on 323 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following metrics deviate from their learned-healthy baseline. Treat each as a semantic observation (meaning + numbers), not a number alone — the KB's interpretation is the authoritative reading.

- **`derived.upf_activity_during_calls`** (UPF activity consistency with active dialogs) — current **0.03 ratio** vs learned baseline **0.54 ratio** (MEDIUM, drop)
    - **What it measures:** Cross-layer consistency check between IMS dialog state and UPF
throughput. A drop while dialogs_per_ue is non-zero is a
smoking-gun signal for media-plane failure independent of signaling.
    - **Drop means:** Active calls reported but no media flowing — media path broken (UPF, RTPEngine, or N3 packet loss).
    - **Healthy typical range:** 0.3–1 ratio
    - **Healthy invariant:** 1.0 when traffic fully follows active calls; 0.0 when signaling says active but data plane is silent.

- **`normalized.icscf.cdp_replies_per_ue`** (I-CSCF Diameter reply rate per UE) — current **0.12 replies_per_second_per_ue** vs learned baseline **0.03 replies_per_second_per_ue** (MEDIUM, spike)
    - **What it measures:** Liveness of the I-CSCF↔HSS Cx path. Drops to 0 when HSS is unreachable OR when no signaling is occurring at the I-CSCF (idle or upstream P-CSCF partitioned).
    - **Spike means:** Either HSS is unreachable or upstream signaling has stopped reaching I-CSCF.
    - **Healthy typical range:** 0–1 replies_per_second_per_ue

- **`normalized.icscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at I-CSCF) — current **0.21 requests_per_second** vs learned baseline **0.06 requests_per_second** (MEDIUM, spike)
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

- **`normalized.scscf.cdp_replies_per_ue`** (S-CSCF CDP Diameter replies per UE) — current **0.21 replies_per_second_per_ue** vs learned baseline **0.06 replies_per_second_per_ue** (MEDIUM, spike)
    - **What it measures:** Active S-CSCF Diameter traffic with HSS. Near-zero when registrations idle OR HSS partition.
    - **Spike means:** Diameter peering loss with HSS.
    - **Healthy typical range:** 0–1 replies_per_second_per_ue
    - **Healthy invariant:** Per-UE rate; varies with registration/auth load.

- **`normalized.scscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at S-CSCF) — current **0.21 requests_per_second** vs learned baseline **0.06 requests_per_second** (MEDIUM, spike)
    - **What it measures:** Health of the I-CSCF → S-CSCF forwarding path. Drop to zero while
I-CSCF is receiving REGISTERs = S-CSCF-side issue (crashed, or
I-CSCF → S-CSCF path broken).
    - **Spike means:** I-CSCF not forwarding or S-CSCF not receiving.
    - **Healthy typical range:** 0–0.5 requests_per_second
    - **Healthy invariant:** Per-UE rate. Tracks icscf.register rate.

- **`normalized.smf.bearers_per_ue`** (Active QoS bearers per UE) — current **2.00 count** vs learned baseline **2.48 count** (MEDIUM, shift)
    - **What it measures:** Per-UE count of active QoS bearers. Baseline reflects default
bearers; increments during VoNR calls indicate dedicated voice
bearers being set up. Drop during an active call = dedicated
bearer torn down unexpectedly (voice will fail).
    - **Shift means:** Expected during VoNR calls (1 extra bearer per active call).
    - **Healthy typical range:** 2–3.5 count
    - **Healthy invariant:** At rest: equals configured default bearers (typically 2 per UE).
During active VoNR call: +1 per caller. The per-UE ratio is the
invariant; absolute count scales with UE pool.

- **`normalized.upf.gtp_indatapktn3upf_per_ue`** (GTP-U uplink rate per UE (N3)) — current **1.41 packets_per_second** vs learned baseline **1.45 packets_per_second** (MEDIUM, shift)
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

- **`normalized.upf.gtp_outdatapktn3upf_per_ue`** (GTP-U downlink rate per UE (N3)) — current **1.63 packets_per_second** vs learned baseline **1.45 packets_per_second** (MEDIUM, shift)
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
| `derived.upf_activity_during_calls` | drop | 4.28 | KB-labeled transport: core.upf.activity_during_calls (drop, score=4.28) |
| `normalized.upf.gtp_indatapktn3upf_per_ue` | shift | 4.28 | KB-labeled transport: core.upf.gtp_indatapktn3upf_per_ue (shift, score=4.28) |
| `normalized.upf.gtp_outdatapktn3upf_per_ue` | shift | 4.28 | KB-labeled transport: core.upf.gtp_outdatapktn3upf_per_ue (shift, score=4.28) |

### Application-bucket flags (1)

| Metric | Direction | Score | KB-driven reason |
|---|---|---:|---|
| `normalized.smf.bearers_per_ue` | shift | 4.28 | KB-labeled application: core.smf.bearers_per_ue (shift, score=4.28) |

### Ambiguous-bucket flags (6)

| Metric | Direction | Score | KB-driven reason |
|---|---|---:|---|
| `normalized.icscf.cdp_replies_per_ue` | spike | 4.28 | KB-labeled mixed: ims.icscf.cdp_replies_per_ue (spike, score=4.28) |
| `normalized.icscf.core:rcv_requests_register_per_ue` | spike | 4.28 | KB-labeled mixed: ims.icscf.rcv_requests_register_per_ue (spike, score=4.28) |
| `normalized.pcscf.core:rcv_requests_register_per_ue` | spike | 4.28 | KB-labeled mixed: ims.pcscf.rcv_requests_register_per_ue (spike, score=4.28) |
| `normalized.scscf.cdp_replies_per_ue` | spike | 4.28 | KB-labeled mixed: ims.scscf.cdp_replies_per_ue (spike, score=4.28) |
| `normalized.scscf.core:rcv_requests_register_per_ue` | spike | 4.28 | KB-labeled mixed: ims.scscf.rcv_requests_register_per_ue (spike, score=4.28) |
| `normalized.pcscf.core:rcv_requests_invite_per_ue` | spike | 1.88 | KB-labeled mixed: ims.pcscf.rcv_requests_invite_per_ue (spike, score=1.88) |

**Rationale:**

```
label=mixed. Both transport-layer (3) and application-layer (1) signals are load-bearing. Path walk runs first; falls through to the application-layer pipeline if the walk produces null localization.

Transport signals: derived.upf_activity_during_calls (drop, score=4.28) — KB-labeled transport: core.upf.activity_during_calls (drop, score=4.28); normalized.upf.gtp_indatapktn3upf_per_ue (shift, score=4.28) — KB-labeled transport: core.upf.gtp_indatapktn3upf_per_ue (shift, score=4.28); normalized.upf.gtp_outdatapktn3upf_per_ue (shift, score=4.28) — KB-labeled transport: core.upf.gtp_outdatapktn3upf_per_ue (shift, score=4.28)

Application signals: normalized.smf.bearers_per_ue (shift, score=4.28) — KB-labeled application: core.smf.bearers_per_ue (shift, score=4.28)

Ambiguous signals: normalized.icscf.cdp_replies_per_ue (spike, score=4.28) — KB-labeled mixed: ims.icscf.cdp_replies_per_ue (spike, score=4.28); normalized.icscf.core:rcv_requests_register_per_ue (spike, score=4.28) — KB-labeled mixed: ims.icscf.rcv_requests_register_per_ue (spike, score=4.28); normalized.pcscf.core:rcv_requests_register_per_ue (spike, score=4.28) — KB-labeled mixed: ims.pcscf.rcv_requests_register_per_ue (spike, score=4.28); normalized.scscf.cdp_replies_per_ue (spike, score=4.28) — KB-labeled mixed: ims.scscf.cdp_replies_per_ue (spike, score=4.28); normalized.scscf.core:rcv_requests_register_per_ue (spike, score=4.28) — KB-labeled mixed: ims.scscf.rcv_requests_register_per_ue (spike, score=4.28) [+1 more]
```

## Transport-Layer Route (Phase 0.6)

### Prioritizer

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
Primary flow `data_pdu_session_user_traffic` (score=12, 11 hops); walker probes 5 candidate flows in parallel. Load-bearing components: ['icscf', 'pcscf', 'scscf', 'smf', 'upf']. Other candidate flows considered: vonr_media=12, ims_registration=8, vonr_call_teardown=8, vonr_call_setup=8. Hard cap (5 flows) truncated 3 additional candidates below the cut. Soft cap exceeded (5 > 3): noisy load-bearing set — inspect screener flag bucketing if this recurs.
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

### Prioritized Candidates Walked In Parallel

The walker probed 5 candidate flows in parallel. All walked flows are listed below (primary marked); the primary's full per-hop walk is in the Walker section above. Listing every walked flow makes the deterministic disambiguation fully auditable.

| Flow | Walker outcome | First attributed hop |
|---|---|---|
| `data_pdu_session_user_traffic` ← primary | ⚠️ null | — |
| `vonr_media` | ⚠️ null | — |
| `ims_registration` | ⚠️ null | — |
| `vonr_call_teardown` | ⚠️ null | — |
| `vonr_call_setup` | ⚠️ null | — |

> ⚠️ **Soft cap exceeded** — walker probed 5 flows (soft cap = 3). Signals a noisy load-bearing set; inspect screener flag bucketing if this recurs.

> 🔪 **Hard cap (5 flows) truncated 3 additional candidate(s)** below the cut: `diameter_cx_authentication` (4), `pdu_session_establishment` (4), `ue_deregistration` (4). These scored above zero but ranked beyond the top 5 by the prioritizer; not walked.

### Localized Synthesis

*Walker found no hop with attribution. Phase 0.6 returned None and the orchestrator fell through to the application-layer pipeline (Phases 1-7) below — the diagnosis you see in `Agent Diagnosis` came from that fallback path, not from Phase 0.6.*

## Event Aggregation (Phase 1)

No events fired during this episode. Either no metric KB triggers matched, or the episode encountered no meaningful state transitions.

## Correlation Analysis (Phase 2)

No events fired — correlation engine had nothing to work with.

## RAG & Operational Lessons (Phase 2.5)

### RAG retrieval — prior similar episodes

**Status:** `hits` — hits=5, top_sim=0.92, top_case=v7/ep_20260514_221925_data_plane_degradation
**Index:** `/home/ehoskas/agentic-network-ops/rag_index`  **Corpus size:** 102 cases
**Classifier label used in retrieval:** `mixed`
**Retrieval params:** k=5, min_similarity=0.4
**Hits (5):**

| Rank | Sim | Case ID | Scenario | Ground truth | Primary suspect | Score |
|---:|---:|---|---|---|---|---:|
| 0 | 92% | `v7/ep_20260514_221925_data_plane_degradation` | Data Plane Degradation | `upf` | `upf` | 100% |
| 1 | 87% | `v7/ep_20260521_161133_p_cscf_packet_loss` | P-CSCF Packet Loss | `pcscf` | `pcscf` | 100% |
| 2 | 86% | `v7/ep_20260520_132808_data_plane_degradation` | Data Plane Degradation | `upf` | `upf` | 100% |
| 3 | 85% | `v7/ep_20260510_185748_call_quality_degradation` | Call Quality Degradation | `rtpengine` | `rtpengine` | 100% |
| 4 | 85% | `v6/ep_20260430_015439_data_plane_degradation` | Data Plane Degradation | `upf` | `upf` | 85% |

*Rendered block injected into the NA prompt's `{prior_similar_episodes}` placeholder: 4902 chars. Source paths are inlined in the block so the EvidenceValidator can audit any case the NA cites.*

### Operational lessons — hand-authored rules corpus

**Status:** `injected` — lessons=16, chars=15678
**Path:** `/home/ehoskas/agentic-network-ops/agentic_ops_common/rag/lessons.yaml`  **Count:** 16  **Block size:** 15678 chars
**Injected lesson IDs:** `L01`, `L02`, `L03`, `L04`, `L05`, `L06`, `L07`, `L08`, `L09`, `L10`, `L11`, `L12`, `L13`, `L14`, `L15`, `L16`

### NA citations of the injected content

**No verbatim citations.** The NA's output text did not reference any retrieved case_id or any injected lesson_id verbatim. This does NOT prove the NA ignored the injected content — the model may have absorbed the patterns implicitly — but it does mean no audit trail links the NA's reasoning back to a specific case or lesson.

## Network Analysis (Phase 3)

**Summary:** The anomaly pattern indicates a degraded user-plane or early signaling path, where UPF N3 packet loss is the primary hypothesis (dropping both media and UE-tunneled SIP requests), causing UEs to retransmit signaling which appears as downstream spikes in registration and INVITE rates at P-CSCF and the CSCFs.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | All required network elements are active. |
| **ran** | 🟢 GREEN | RAN appears healthy and connected. |
| **core** | 🔴 RED | UPF data plane is exhibiting severe deviation, dropping both activity and throughput relative to baseline. |
| **ims** | 🟡 YELLOW | IMS components are showing correlated spikes in registration and INVITE signaling, likely downstream consequences (retransmissions) due to early-path packet loss. |

**CORE evidence:**
- normalized.upf.gtp_indatapktn3upf_per_ue flagged as shift
- normalized.upf.gtp_outdatapktn3upf_per_ue flagged as shift
- derived.upf_activity_during_calls dropped heavily from baseline
- normalized.smf.bearers_per_ue shift

**IMS evidence:**
- normalized.pcscf.core:rcv_requests_register_per_ue spike
- normalized.icscf.core:rcv_requests_register_per_ue spike
- normalized.scscf.core:rcv_requests_register_per_ue spike
- normalized.pcscf.core:rcv_requests_invite_per_ue spike

**Ranked hypotheses:**

- **`h1`** (fit=0.95, nf=upf, specificity=specific):
    - **Statement:** UPF is the source of packet loss on the N3 data plane (matching the n3_data_plane_degradation chain), which drops RTP media—causing the drop in UPF activity during calls—and drops UE SIP signaling, forcing UE retransmissions that manifest as spikes in registration and INVITE rates across the CSCF chain.
    - **Falsification probes:**
        - Use measure_rtt from rtpengine to upf to check for packet loss on the media transport path.
        - Check UPF kernel qdisc drop counters (e.g. via tc -s qdisc show) to localize if the packet loss is internal to UPF.
        - Check rtpengine.errors_per_second and loss_ratio to verify if the loss is visible outside the relay loop.
- **`h2`** (fit=0.85, nf=pcscf, specificity=specific):
    - **Statement:** P-CSCF is the source of packet loss on the IMS signaling path, causing UEs to repeatedly retransmit SIP REGISTER and INVITE requests (creating the observed spikes) and preventing calls from successfully establishing media, dropping UPF activity during calls.
    - **Falsification probes:**
        - Use measure_rtt from pcscf to icscf to detect packet loss on the Mw transport interface.
        - Check derived.pcscf_sip_error_ratio and P-CSCF processing latency to detect application-layer faults.
        - Check UPF N3 in/out metrics to confirm whether the data plane is healthy and exonerate UPF.
- **`h3`** (fit=0.60, nf=rtpengine, specificity=moderate):
    - **Statement:** RTPEngine is the source of media-plane packet loss, failing to relay RTP packets which causes the drop in UPF activity during calls, while the SIP signaling spikes are an independent artifact or consequence of call failures.
    - **Falsification probes:**
        - Check rtpengine.errors_per_second to detect relay-loop application failures inside RTPEngine.
        - Check derived.rtpengine_loss_ratio to verify end-to-end media loss on active calls.
        - Use measure_rtt from upf to rtpengine to detect transport loss on the N6 interface.


## Falsification Plans (Phase 4)

**3 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `upf`)

**Hypothesis:** UPF is the source of packet loss on the N3 data plane (matching the n3_data_plane_degradation chain), which drops RTP media—causing the drop in UPF activity during calls—and drops UE SIP signaling, forcing UE retransmissions that manifest as spikes in registration and INVITE rates across the CSCF chain.

**Probes (3):**
1. **`get_dp_quality_gauges`** — window_seconds=120 to check core.upf.gtp_indatapktn3upf_per_ue and core.upf.gtp_outdatapktn3upf_per_ue alongside the upf_counters_are_directional verdict.
    - *Expected if hypothesis holds:* UPF N3 metrics show a drop or are zero, indicating data plane degradation or failure on the N3 path.
    - *Falsifying observation:* UPF N3 metrics are within typical ranges (e.g., 0 to 10 pps), showing the N3 data plane is actively receiving and sending traffic without severe drops.
2. **`get_dp_quality_gauges`** — window_seconds=120 to check core.upf.activity_during_calls.
    - *Expected if hypothesis holds:* The metric drops significantly (towards 0.0), indicating signaling says active but the data plane is broken or silent.
    - *Falsifying observation:* The metric reads ~1.0, showing that data plane traffic fully follows active calls without packet loss.
3. **`get_diagnostic_metrics`** — Check pcscf.rcv_requests_register_per_ue and pcscf.rcv_requests_invite_per_ue.
    - *Expected if hypothesis holds:* Spikes in registration and INVITE rates, as UEs retransmit signaling due to the UPF dropping tunneled SIP packets.
    - *Falsifying observation:* Rates are at their normal baseline, contradicting the claim that UEs are repeatedly retransmitting signaling.

*Notes:* Anchored to the n3_data_plane_degradation chain and its observables. The probes assess data plane drop and correlate signaling retransmission spikes across UPF and P-CSCF.

### Plan for `h2` (target: `pcscf`)

**Hypothesis:** P-CSCF is the source of packet loss on the IMS signaling path, causing UEs to repeatedly retransmit SIP REGISTER and INVITE requests (creating the observed spikes) and preventing calls from successfully establishing media, dropping UPF activity during calls.

**Probes (3):**
1. **`get_diagnostic_metrics`** — Check pcscf.rcv_requests_register_per_ue and pcscf.rcv_requests_invite_per_ue.
    - *Expected if hypothesis holds:* Elevated rates indicating UEs are repeatedly retransmitting SIP requests due to packet loss at the P-CSCF.
    - *Falsifying observation:* Rates are normal, contradicting the presence of repeated SIP retransmissions.
2. **`get_diagnostic_metrics`** — Check pcscf.dialogs_per_ue.
    - *Expected if hypothesis holds:* The metric drops or remains zero, as packet loss prevents SIP calls from successfully establishing.
    - *Falsifying observation:* The metric reads ~1.0 per active UE, demonstrating that calls are successfully established and maintained.
3. **`get_diagnostic_metrics`** — Check pcscf.sip_error_ratio.
    - *Expected if hypothesis holds:* Non-zero ratio, indicating the P-CSCF is actively rejecting SIP requests.
    - *Falsifying observation:* Zero ratio, demonstrating the P-CSCF is processing and responding to SIP signaling successfully without errors.

*Notes:* Anchored to IMS signaling observables. Checks UE retransmission rates, dialog establishment success, and P-CSCF error ratios to isolate the signaling failure.

### Plan for `h3` (target: `rtpengine`)

**Hypothesis:** RTPEngine is the source of media-plane packet loss, failing to relay RTP packets which causes the drop in UPF activity during calls, while the SIP signaling spikes are an independent artifact or consequence of call failures.

**Probes (3):**
1. **`get_dp_quality_gauges`** — window_seconds=120 to check ims.rtpengine.errors_per_second.
    - *Expected if hypothesis holds:* Spike above zero, indicating active relay-loop errors.
    - *Falsifying observation:* The value is 0.0, indicating the RTPEngine relay loop is functioning without errors.
2. **`get_dp_quality_gauges`** — window_seconds=120 to check ims.rtpengine.loss_ratio.
    - *Expected if hypothesis holds:* Spike above typical range, confirming end-to-end packet loss is reported by receivers.
    - *Falsifying observation:* The value is within the typical range (0.0 to 0.1), demonstrating no significant end-to-end media loss.
3. **`get_dp_quality_gauges`** — window_seconds=120 to check core.upf.gtp_indatapktn3upf_per_ue and core.upf.gtp_outdatapktn3upf_per_ue.
    - *Expected if hypothesis holds:* UPF N3 counters remain healthy and unchanged, isolating the loss to RTPEngine or downstream components.
    - *Falsifying observation:* UPF N3 counters are severely degraded or zero, indicating the loss occurs upstream on the N3 path (UPF) rather than originating at RTPEngine.

*Notes:* Anchored to RTPEngine relay observables. Distinguishes RTPEngine-sourced media loss from UPF N3 loss using KB-curated disambiguators.


## Parallel Investigators (Phase 5)

**4 sub-Investigator verdict(s):** **1 INCONCLUSIVE**, **3 DISPROVEN**

### `h1` — ❓ **INCONCLUSIVE**

**Hypothesis:** UPF is the source of packet loss on the N3 data plane (matching the n3_data_plane_degradation chain), which drops RTP media—causing the drop in UPF activity during calls—and drops UE SIP signaling, forcing UE retransmissions that manifest as spikes in registration and INVITE rates across the CSCF chain.

**Reasoning:** [Multi-shot consensus — DISAGREEMENT. Shot 1 returned NOT_DISPROVEN; shot 2 returned DISPROVEN. Two independent samples of the same Investigator on the same plan reached opposite conclusions. The reconciler forces verdict to INCONCLUSIVE because we cannot trust either shot in isolation when the underlying LLM judgment is unstable.]

Shot 1 (NOT_DISPROVEN): The evidence perfectly confirms the hypothesis's mechanism. UPF data plane activity (upf_activity_during_calls) has dropped to near zero (0.03), and UPF in/out packets are sitting at baseline (1.0 pps) despite active dialogs being present, confirming media is not traversing the N3 path. Simultaneously, P-CSCF metrics show significant spikes in incoming INVITE and REGISTER requests, which aligns exactly with UE SIP signaling hitting N3 loss and forcing retransmissions. Since uplink media isn't even reaching UPF's N3 ingress, the fault is isolated to the N3 data plane, exonerating downstream NF…

Shot 2 (DISPROVEN): The hypothesis claims the UPF is dropping N3 data plane traffic, including both RTP media and UE SIP signaling. This is disproven by two independent observations. First, UPF N3 throughput metrics (both ingress and egress) are perfectly at their historical baselines (~1.4 pps), showing no N3-level data plane packet loss. Second, the P-CSCF is successfully receiving spikes of SIP REGISTER and INVITE retransmissions. If the UPF were dropping UE SIP signaling on the N3 path, these packets would never reach the P-CSCF. The fact that the N3 data plane successfully forwards the signaling to the P-CS…

**Probes executed (3):**
- **get_dp_quality_gauges(window_seconds=120) to check UPF N3 input/output rates and the upf_counters_are_directional verdict.** ✓ CONSISTENT
    - *Tool:* `get_dp_quality_gauges(at_time_ts=1780948644.86074, window_seconds=120)`
    - *Observation:* [EVIDENCE: get_dp_quality_gauges(at_time_ts=1780948644.86074, window_seconds=120) -> "UPF:\n    in  packets/sec: 1.0\n    out packets/sec: 1.0\n    in  throughput : 0.25 KB/s\n    out throughput : 0.32 KB/s\n    active sessions: 4"]
    - *Comment:* UPF in/out rates are at 1.0 pps, which is a massive drop from the ~50 pps expected per direction during an active call. This confirms the N3 data plane is not receiving/sending media.
- **get_diagnostic_metrics() to check core.upf.activity_during_calls.** ✓ CONSISTENT
    - *Tool:* `get_diagnostic_metrics(at_time_ts=1780948644.86074, nfs=["upf"])`
    - *Observation:* [EVIDENCE: get_diagnostic_metrics(at_time_ts=1780948644.86074, nfs=["upf"]) -> "derived.upf_activity_during_calls = 0.03039 [derived, ratio]\n        learned_normal = 0.5431"]
    - *Comment:* The metric drops significantly towards 0.0 (reading 0.03), directly indicating that while signaling says calls are active, the data plane is broken and media is not flowing.
- **get_diagnostic_metrics() to check pcscf.rcv_requests_register_per_ue and pcscf.rcv_requests_invite_per_ue.** ✓ CONSISTENT
    - *Tool:* `get_diagnostic_metrics(at_time_ts=1780948644.86074, nfs=["pcscf"])`
    - *Observation:* [EVIDENCE: get_diagnostic_metrics(at_time_ts=1780948644.86074, nfs=["pcscf"]) -> "normalized.pcscf.core:rcv_requests_invite_per_ue = 0.03 [derived, requests_per_second]\n        learned_normal = 0.003327\n...\n    normalized.pcscf.core:rcv_requests_register_per_ue = 0.2096 [derived, requests_per_second]\n        learned_normal = 0.06042"]
    - *Comment:* Both INVITE and registration rates have spiked 3x to 10x above their learned baselines, matching the predicted signature of UE SIP retransmissions caused by packet loss on N3.

**Alternative suspects:** pcscf, rtpengine

### `h2` — ❌ **DISPROVEN**

**Hypothesis:** P-CSCF is the source of packet loss on the IMS signaling path, causing UEs to repeatedly retransmit SIP REGISTER and INVITE requests (creating the observed spikes) and preventing calls from successfully establishing media, dropping UPF activity during calls.

**Reasoning:** [Multi-shot consensus — both shots returned DISPROVEN.]

Shot 1: The P-CSCF is successfully processing SIP signaling and establishing calls without errors. The sip_error_ratio is 0 and active dialogs_per_ue is 1.0, directly contradicting the claim that P-CSCF drops packets and prevents call establishment. Additionally, measure_rtt confirms 0% transport packet loss on the Mw interface to I-CSCF. The fault must lie on the data plane (e.g., UPF or RTPEngine), as calls successfully establish their signaling but media fails to flow.

Shot 2: Diagnostic metrics directly contradict the hypothesis that the P-CSCF is failing to establish calls or dropping signaling. The P-CSCF sip_error_ratio is 0, and dialogs_per_ue reads 1.0, proving that SIP calls are successfully established and maintained at the signaling layer without application-layer errors. Furthermore, a measure_rtt probe from P-CSCF to I-CSCF confirmed 0% packet loss on the outbound IMS transport path. The elevated signaling rates are likely due to upstream packet drops (e.g., at the UPF N3 data plane) dropping UE-tunneled SIP requests and causing UEs to retransmit, rather than a fault originating at the P-CSCF.

**Probes executed (4):**
- **Check pcscf.rcv_requests_register_per_ue and pcscf.rcv_requests_invite_per_ue.** ✓ CONSISTENT
    - *Tool:* `get_diagnostic_metrics(at_time_ts=1780948644.86074, nfs=["pcscf"])`
    - *Observation:* [EVIDENCE: get_diagnostic_metrics(at_time_ts=1780948644.86074, nfs=["pcscf"]) -> "normalized.pcscf.core:rcv_requests_register_per_ue = 0.2096" and "normalized.pcscf.core:rcv_requests_invite_per_ue = 0.03"]
    - *Comment:* Request rates are slightly elevated, which is consistent with the observed spikes, but does not isolate P-CSCF as the failure point.
- **Check pcscf.dialogs_per_ue.** ✗ CONTRADICTS
    - *Tool:* `get_diagnostic_metrics(at_time_ts=1780948644.86074, nfs=["pcscf"])`
    - *Observation:* [EVIDENCE: get_diagnostic_metrics(at_time_ts=1780948644.86074, nfs=["pcscf"]) -> "normalized.pcscf.dialogs_per_ue = 1 [derived, count]"]
    - *Comment:* The metric reads 1.0 per active UE, directly contradicting the hypothesis that P-CSCF packet loss prevents calls from successfully establishing.
- **Check pcscf.sip_error_ratio.** ✗ CONTRADICTS
    - *Tool:* `get_diagnostic_metrics(at_time_ts=1780948644.86074, nfs=["pcscf"])`
    - *Observation:* [EVIDENCE: get_diagnostic_metrics(at_time_ts=1780948644.86074, nfs=["pcscf"]) -> "derived.pcscf_sip_error_ratio = 0 [ratio, ratio]"]
    - *Comment:* Zero error ratio demonstrates the P-CSCF is processing and responding to SIP signaling successfully without errors, disproving it as the source of drops.
- **Use measure_rtt from pcscf to icscf to detect packet loss on the Mw transport interface.** ✗ CONTRADICTS
    - *Tool:* `measure_rtt(container="pcscf", target="icscf")`
    - *Observation:* [EVIDENCE: measure_rtt("pcscf", "icscf") -> "66 packets transmitted, 66 received, 0% packet loss"]
    - *Comment:* No packet loss detected between P-CSCF and I-CSCF, eliminating transport layer loss on this segment.

**Alternative suspects:** upf, rtpengine

### `h3` — ❌ **DISPROVEN**

**Hypothesis:** RTPEngine is the source of media-plane packet loss, failing to relay RTP packets which causes the drop in UPF activity during calls, while the SIP signaling spikes are an independent artifact or consequence of call failures.

**Reasoning:** [Multi-shot consensus — both shots returned DISPROVEN.]

Shot 1: The hypothesis asserts that RTPEngine is actively failing to relay media packets. However, evidence directly contradicts this mechanism: RTPEngine's relay loop shows 0 errors, and its end-to-end loss ratio is zero (or N/A due to no receiver reports), meaning no loss is originating from or reported by RTPEngine. Furthermore, a clean transport probe from RTPEngine to UPF shows 0% loss. Although UPF N3 counters remain near their healthy baseline (which the plan hypothesized would isolate the fault to RTPEngine), the complete absence of any error or loss signal at RTPEngine definitively clears it as the source. The loss must be occurring downstream or via an internal layer at UPF that bypasses the N3 interface counters.

Shot 2: RTPEngine is not dropping packets; it is starved of them. RTPEngine's relay loop errors and end-to-end loss ratio are both 0, and its throughput is a flat 0.0 packets/sec, proving it is receiving no media to relay. Furthermore, UPF N3 metrics show severe bidirectional degradation (1.0 pps inbound and outbound, far below the ~50 pps expected for active calls), causing a massive drop in `upf_activity_during_calls`. Since UPF N3 inbound traffic (from gNB) is upstream of RTPEngine, an RTPEngine fault cannot cause it to drop. The loss must originate upstream at the UPF or on the N3 path.

**Probes executed (3):**
- **window_seconds=120 to check ims.rtpengine.errors_per_second.** ✗ CONTRADICTS
    - *Tool:* `get_diagnostic_metrics(at_time_ts=1780948644.86074, nfs=["rtpengine", "upf"])`
    - *Observation:* [EVIDENCE: get_diagnostic_metrics(at_time_ts=1780948644.86074, nfs=["rtpengine", "upf"]) -> "rtpengine.errors_per_second_(total) = 0 [gauge, errors_per_second]"]
    - *Comment:* The value is 0.0, indicating the RTPEngine relay loop is functioning without errors, directly refuting the claim of relay failure.
- **window_seconds=120 to check ims.rtpengine.loss_ratio.** ✗ CONTRADICTS
    - *Tool:* `get_diagnostic_metrics(at_time_ts=1780948644.86074, nfs=["rtpengine", "upf"])`
    - *Observation:* [EVIDENCE: get_diagnostic_metrics(at_time_ts=1780948644.86074, nfs=["rtpengine", "upf"]) -> "derived.rtpengine_loss_ratio = 0 [ratio, packets_per_rr]"] and [EVIDENCE: get_dp_quality_gauges(at_time_ts=1780948644.86074, window_seconds=120) -> "loss (recent)  : N/A (no samples in window)"]
    - *Comment:* The value is 0 (or N/A), which is within the typical healthy range and demonstrates no significant end-to-end media loss is visible to RTPEngine.
- **window_seconds=120 to check core.upf.gtp_indatapktn3upf_per_ue and core.upf.gtp_outdatapktn3upf_per_ue.** ✓ CONSISTENT
    - *Tool:* `get_diagnostic_metrics(at_time_ts=1780948644.86074, nfs=["rtpengine", "upf"])`
    - *Observation:* [EVIDENCE: get_diagnostic_metrics(at_time_ts=1780948644.86074, nfs=["rtpengine", "upf"]) -> "normalized.upf.gtp_indatapktn3upf_per_ue = 1.407 ... normalized.upf.gtp_outdatapktn3upf_per_ue = 1.632"]
    - *Comment:* UPF N3 counters are not severely degraded; they remain near their baseline (learned_normal = 1.454), which the plan predicted if RTPEngine was at fault. However, given RTPEngine's innocence, the loss is likely occurring downstream or internal to UPF without affecting these N3 counters.

**Alternative suspects:** upf

### `h_promoted_upf` — ❌ **DISPROVEN**

**Hypothesis:** upf is the source of the anomaly named in the alternative_suspects of the original verdict tree.

**Reasoning:** Direct evidence contradicts the hypothesis that the UPF is the source of the anomaly. The UPF container is running normally without restarts. Data plane metrics show healthy uplink traffic processing at the UPF (gtp_indatapktn3upf_per_ue = 1.407), and RTPEngine confirms 0 packet loss end-to-end, meaning the UPF is correctly handling traffic.

**Probes executed (4):**
- **Check if the upf container is running.** ✗ CONTRADICTS
    - *Tool:* `get_network_status()`
    - *Observation:* [EVIDENCE: get_network_status() -> "'upf': 'running'"]
    - *Comment:* The upf container is running normally, contradicting the hypothesis that it might be down or restarting.
- **Read UPF metric 'gtp_indatapktn3upf_per_ue' to check uplink data plane activity.** ✗ CONTRADICTS
    - *Tool:* `get_diagnostic_metrics(at_time_ts=1780948644.86074, nfs=["upf", "rtpengine"])`
    - *Observation:* [EVIDENCE: get_diagnostic_metrics(at_time_ts=1780948644.86074, nfs=["upf", "rtpengine"]) -> "normalized.upf.gtp_indatapktn3upf_per_ue = 1.407"]
    - *Comment:* The uplink data plane activity is healthy (> 0), contradicting a UPF traffic processing failure.
- **Read RTPEngine metric 'loss_ratio' to act as a partner probe to gtp_indatapktn3upf_per_ue.** ✗ CONTRADICTS
    - *Tool:* `get_diagnostic_metrics(at_time_ts=1780948644.86074, nfs=["upf", "rtpengine"])`
    - *Observation:* [EVIDENCE: get_diagnostic_metrics(at_time_ts=1780948644.86074, nfs=["upf", "rtpengine"]) -> "derived.rtpengine_loss_ratio = 0"]
    - *Comment:* The RTPEngine loss_ratio is 0.0, indicating healthy end-to-end delivery and no packet loss occurring at or after the UPF.
- **Read RTPEngine metric 'errors_per_second' to act as a partner probe to loss_ratio.** ✓ CONSISTENT
    - *Tool:* `get_diagnostic_metrics(at_time_ts=1780948644.86074, nfs=["upf", "rtpengine"])`
    - *Observation:* [EVIDENCE: get_diagnostic_metrics(at_time_ts=1780948644.86074, nfs=["upf", "rtpengine"]) -> "rtpengine.errors_per_second_(total) = 0"]
    - *Comment:* RTPEngine errors_per_second is 0, which was expected if the UPF was at fault, but since loss_ratio is also 0, this only confirms the RTPEngine is not dropping packets either.


## Evidence Validation (Phase 6)

**Overall verdict:** clean
**Overall confidence:** high

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 14 | 3/3 | clean | high |
| `InvestigatorAgent_h2` | 6 | 4/4 | clean | high |
| `InvestigatorAgent_h3` | 11 | 4/4 | clean | high |
| `InvestigatorAgent_h_promoted_upf` | 2 | 4/4 | clean | high |


## Ground Truth

**Failure domain:** ims_signaling  
**Protocol impact:** Diameter  
**Affected components:** pyhss  
**Severity:** degraded

## Agent Diagnosis

**Model:** v7-adk/pro=gemini-3.1-pro-preview+flash=gemini-3.5-flash  
**Time to diagnosis:** 1268.6s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: Investigation completed without identifying a specific root cause. Manual NOC review recommended.
> - **timeline**:
>     1. Observed anomalous drops in UPF activity during calls and correlated spikes in SIP registration and INVITE signaling at the P-CSCF.
>     2. Formulated hypotheses attributing the packet loss to UPF (h1), P-CSCF (h2), and RTPEngine (h3).
>     3. Gathered diagnostic metrics and transport measurements which ruled out P-CSCF (h2) and RTPEngine (h3) due to 0% error ratios and healthy operation.
>     4. Investigated UPF (h1) but reached an INCONCLUSIVE verdict because active session data dropped while interface-level packet counters remained at baseline.
>     5. Executed a promoted re-investigation on UPF but still found no conclusive evidence of a fault, concluding the automated investigation without a confirmed root cause.
> - **root_cause**: undetected — investigation completed without confirmation
> - **affected_components**: []
> - **recommendation**: Manually inspect upf, pcscf, and rtpengine for subtle data plane failures, extended observation, or symptoms outside the current detection capability.
> - **confidence**: low
> - **verdict_kind**: undetected_fault
> - **explanation**: The Network Analyst generated three initial hypotheses to explain the dropped UPF activity during calls and downstream signaling spikes: UPF N3 packet loss (h1), P-CSCF signaling loss (h2), and RTPEngine media-plane loss (h3). The P-CSCF and RTPEngine hypotheses were definitively DISPROVEN, as both components exhibited zero application errors, zero end-to-end packet loss, and healthy transport interfaces. The UPF N3 loss hypothesis (h1) returned an INCONCLUSIVE verdict due to conflicting evidence: while the data plane showed severely reduced activity, the N3 ingress and egress counters remained at baseline levels. A promoted re-investigation into the UPF similarly found healthy container status and uplink traffic processing, resulting in a DISPROVEN verdict. The original anomalies in UPF media processing and the resulting SIP signaling retransmissions remain unexplained, and the agent could not pinpoint a specific fault — please investigate further.

### Scoring Breakdown

**Overall score: 10%**

**Scorer assessment:** The agent missed the PyHSS clock skew but correctly hedged with an undetected fault verdict rather than fabricating a failure.

| Dimension | Weight | Result | Rationale |
|-----------|-------:|--------|-----------|
| Root cause correct | 0.40 | No | The agent declared an undetected fault and did not identify the PyHSS clock skew. While it avoided fabricating a false outage, it failed to detect the observability anomaly. |
| Component overlap | 0.25 | 0% | Mechanical comparison: ground truth ['pyhss'] vs diagnosis root cause(s) []. pyhss=absent (0.0). |
| Severity correct | 0.15 | No | The agent did not evaluate the severity of the clock drift, focusing instead on unrelated data-plane metrics. |
| Fault type identified | 0.10 | No | The agent did not identify the clock drift or any observability-class anomaly. |
| Confidence calibrated | 0.10 | Yes | The agent appropriately assigned low confidence to its inconclusive findings. |

**Ranking:** The correct cause was not identified or ranked.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 1,029,745 |
| Output tokens | 14,560 |
| Thinking tokens | 85,159 |
| **Total tokens** | **1,129,464** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| SymptomClassifier | 0 | 0 | 0 |
| PathPrioritizer | 0 | 0 | 0 |
| PathWalkInvestigator | 0 | 0 | 0 |
| EventAggregator | 0 | 0 | 0 |
| CorrelationAnalyzer | 0 | 0 | 0 |
| InfraStatusSnapshot | 0 | 0 | 0 |
| RAGRetriever | 0 | 0 | 0 |
| OperationalLessons | 0 | 0 | 0 |
| NetworkAnalystAgent | 166,456 | 8 | 5 |
| Phase 3 NetworkAnalyst__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 22,097 | 0 | 1 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 26,624 | 0 | 1 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| InvestigatorAgent_h1 | 245,960 | 9 | 9 |
| InvestigatorAgent_h1 | 125,921 | 5 | 5 |
| InvestigatorAgent_h1__reconciliation | 0 | 0 | 0 |
| InvestigatorAgent_h2 | 76,303 | 3 | 4 |
| InvestigatorAgent_h2 | 75,081 | 3 | 4 |
| InvestigatorAgent_h2__reconciliation | 0 | 0 | 0 |
| InvestigatorAgent_h3 | 102,099 | 4 | 5 |
| InvestigatorAgent_h3 | 190,523 | 7 | 8 |
| InvestigatorAgent_h3__reconciliation | 0 | 0 | 0 |
| Phase5FanOutAudit | 0 | 0 | 0 |
| Phase6.5CandidatePool | 0 | 0 | 0 |
| InstructionGeneratorAgent | 17,194 | 0 | 1 |
| Phase 6.5 Reinvestigation IG__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 24,922 | 0 | 1 |
| Phase 6.5 Reinvestigation IG__guardrail | 0 | 0 | 0 |
| Phase 6.5 Reinvestigation IG__guardrail | 0 | 0 | 0 |
| InvestigatorAgent_h_promoted_upf | 35,460 | 2 | 2 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 20,824 | 0 | 1 |
| Phase 7 Synthesis__guardrail | 0 | 0 | 0 |
| ImpactAssessment | 0 | 0 | 0 |


## Blast Radius & Downstream Impact

*Impact undetermined — no root cause was localized, so no downstream impact could be computed.*

## Resolution

**Heal method:** scheduled  
**Recovery time:** 1403.5s
