# Episode Report: P-CSCF Packet Loss

**Agent:** v7  
**Episode ID:** ep_20260521_161133_p_cscf_packet_loss  
**Date:** 2026-05-21T16:11:34.456219+00:00  
**Duration:** 649.8s  

---

## Scenario

**Category:** network  
**Blast radius:** single_nf  
**Description:** Inject 30% packet loss on the P-CSCF (SIP edge proxy) — the same fault class as Call Quality Degradation but on a signaling-plane container. Packets leaving P-CSCF (REGISTER forwards to I-CSCF, 401/200 responses to UEs) are silently dropped by the kernel after Kamailio's sendto() returns success. SIP retransmission timers (T1 = 500 ms) absorb some of the loss; a meaningful fraction of registrations still time out. This is the second worked example in ADR `path_anchored_probe_planning_for_transport_layer_faults.md` — it proves that the same fault class manifests in the signaling plane and that v7's path walk localizes both data-plane (Call Quality Degradation) and signaling-plane (this scenario) instances of it correctly. v6's per-NF hypothesis pipeline mis-diagnoses both.

## Faults Injected

- **network_loss** on `pcscf` — {'loss_pct': 30}

## Baseline (Pre-Fault)

Stack phase before injection: **ready**
All containers running at baseline.

## Fault Propagation Verification

**Verdict:** ✅ `confirmed`

- **Propagation window:** 145s (ObservationTrafficAgent drove traffic for this window; verifier added wait=0s on top)
- **Nodes with significant deltas:** 4
- **Nodes with any drift:** 5

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 44.02 (per-bucket threshold: 28.18, context bucket (1, 1), trained on 323 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following metrics deviate from their learned-healthy baseline. Treat each as a semantic observation (meaning + numbers), not a number alone — the KB's interpretation is the authoritative reading.

- **`derived.upf_activity_during_calls`** (UPF activity consistency with active dialogs) — current **0.10 ratio** vs learned baseline **0.54 ratio** (MEDIUM, drop)
    - **What it measures:** Cross-layer consistency check between IMS dialog state and UPF
throughput. A drop while dialogs_per_ue is non-zero is a
smoking-gun signal for media-plane failure independent of signaling.
    - **Drop means:** Active calls reported but no media flowing — media path broken (UPF, RTPEngine, or N3 packet loss).
    - **Healthy typical range:** 0.3–1 ratio
    - **Healthy invariant:** 1.0 when traffic fully follows active calls; 0.0 when signaling says active but data plane is silent.

- **`normalized.icscf.cdp_replies_per_ue`** (I-CSCF Diameter reply rate per UE) — current **0.03 replies_per_second_per_ue** vs learned baseline **0.03 replies_per_second_per_ue** (MEDIUM, shift)
    - **What it measures:** Liveness of the I-CSCF↔HSS Cx path. Drops to 0 when HSS is unreachable OR when no signaling is occurring at the I-CSCF (idle or upstream P-CSCF partitioned).
    - **Shift means:** I-CSCF is actively conversing with HSS — healthy.
    - **Healthy typical range:** 0–1 replies_per_second_per_ue

- **`normalized.icscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at I-CSCF) — current **0.03 requests_per_second** vs learned baseline **0.06 requests_per_second** (MEDIUM, drop)
    - **What it measures:** Health of the P-CSCF → I-CSCF forwarding path (Mw interface). When
this drops to zero while P-CSCF REGISTER rate is still non-zero,
it's the SIGNATURE of an IMS partition between P-CSCF and I-CSCF.
    - **Drop means:** Either UEs not registering at all, or P-CSCF isolated from I-CSCF.
    - **Healthy typical range:** 0–0.5 requests_per_second
    - **Healthy invariant:** Per-UE rate. Should closely track ims.pcscf.rcv_requests_register_per_ue.

- **`normalized.pcscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at P-CSCF) — current **0.10 requests_per_second** vs learned baseline **0.06 requests_per_second** (MEDIUM, spike)
    - **What it measures:** How actively UEs are refreshing their IMS registrations with the
P-CSCF. REGISTERs arrive periodically (re-registration timer) plus
at attach. Sustained zero means UEs cannot reach P-CSCF OR the
UE-to-network SIP path is broken.
    - **Spike means:** Fewer REGISTERs than expected — UE connectivity or P-CSCF reachability issue.
    - **Healthy typical range:** 0–0.5 requests_per_second
    - **Healthy invariant:** Per-UE rate — same value at any deployment scale.

- **`normalized.pcscf.dialogs_per_ue`** (Active SIP dialogs per registered UE at P-CSCF) — current **0.50 count** vs learned baseline **0.48 count** (MEDIUM, shift)
    - **What it measures:** How many calls per user are currently in progress at the P-CSCF.
Going to zero from a non-zero baseline means calls have ended
(normal) OR call setup is failing system-wide (degradation).
Together with rcv_requests_* it discriminates the two.
    - **Shift means:** Calls ending or setup failing.
    - **Healthy typical range:** 0–1 count
    - **Healthy invariant:** Per-UE — scale-independent. 0 at rest, ~1 per active VoNR call.

- **`normalized.scscf.cdp_replies_per_ue`** (S-CSCF CDP Diameter replies per UE) — current **0.03 replies_per_second_per_ue** vs learned baseline **0.06 replies_per_second_per_ue** (MEDIUM, drop)
    - **What it measures:** Active S-CSCF Diameter traffic with HSS. Near-zero when registrations idle OR HSS partition.
    - **Drop means:** No active S-CSCF Diameter exchanges (idle or partitioned).
    - **Healthy typical range:** 0–1 replies_per_second_per_ue
    - **Healthy invariant:** Per-UE rate; varies with registration/auth load.

- **`normalized.scscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at S-CSCF) — current **0.03 requests_per_second** vs learned baseline **0.06 requests_per_second** (MEDIUM, drop)
    - **What it measures:** Health of the I-CSCF → S-CSCF forwarding path. Drop to zero while
I-CSCF is receiving REGISTERs = S-CSCF-side issue (crashed, or
I-CSCF → S-CSCF path broken).
    - **Drop means:** S-CSCF isolated or not running.
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

- **`normalized.upf.gtp_outdatapktn3upf_per_ue`** (GTP-U downlink rate per UE (N3)) — current **2.38 packets_per_second** vs learned baseline **1.45 packets_per_second** (MEDIUM, spike)
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

- **`normalized.icscf.core:rcv_requests_invite_per_ue`** (SIP INVITE rate per UE at I-CSCF) — current **0.01 requests_per_second** vs learned baseline **0.00 requests_per_second** (LOW, spike)
    - **What it measures:** Health of call-setup forwarding P-CSCF → I-CSCF. Partition signature
same as REGISTER rate.
    - **Spike means:** Forwarding failure.
    - **Healthy typical range:** 0–0.2 requests_per_second
    - **Healthy invariant:** Per-UE rate. Tracks pcscf.invite rate.


## Symptom Classifier (Phase 0.5)

**Label:** `mixed`  
**Flag counts:** transport=2, application=1, ambiguous=7

### Transport-bucket flags (2)

| Metric | Direction | Score | KB-driven reason |
|---|---|---:|---|
| `derived.upf_activity_during_calls` | drop | 4.28 | KB-labeled transport: core.upf.activity_during_calls (drop, score=4.28) |
| `normalized.upf.gtp_outdatapktn3upf_per_ue` | spike | 4.28 | KB-labeled transport: core.upf.gtp_outdatapktn3upf_per_ue (spike, score=4.28) |

### Application-bucket flags (1)

| Metric | Direction | Score | KB-driven reason |
|---|---|---:|---|
| `normalized.smf.bearers_per_ue` | shift | 4.28 | KB-labeled application: core.smf.bearers_per_ue (shift, score=4.28) |

### Ambiguous-bucket flags (7)

| Metric | Direction | Score | KB-driven reason |
|---|---|---:|---|
| `normalized.icscf.cdp_replies_per_ue` | shift | 4.28 | KB-labeled mixed: ims.icscf.cdp_replies_per_ue (shift, score=4.28) |
| `normalized.icscf.core:rcv_requests_register_per_ue` | drop | 4.28 | KB-labeled mixed: ims.icscf.rcv_requests_register_per_ue (drop, score=4.28) |
| `normalized.pcscf.core:rcv_requests_register_per_ue` | spike | 4.28 | KB-labeled mixed: ims.pcscf.rcv_requests_register_per_ue (spike, score=4.28) |
| `normalized.pcscf.dialogs_per_ue` | shift | 4.28 | KB-labeled mixed: ims.pcscf.dialogs_per_ue (shift, score=4.28) |
| `normalized.scscf.cdp_replies_per_ue` | drop | 4.28 | KB-labeled mixed: ims.scscf.cdp_replies_per_ue (drop, score=4.28) |
| `normalized.scscf.core:rcv_requests_register_per_ue` | drop | 4.28 | KB-labeled mixed: ims.scscf.rcv_requests_register_per_ue (drop, score=4.28) |
| `normalized.icscf.core:rcv_requests_invite_per_ue` | spike | 1.50 | KB-labeled mixed: ims.icscf.rcv_requests_invite_per_ue (spike, score=1.50) |

**Rationale:**

```
label=mixed. Both transport-layer (2) and application-layer (1) signals are load-bearing. Path walk runs first; falls through to the application-layer pipeline if the walk produces null localization.

Transport signals: derived.upf_activity_during_calls (drop, score=4.28) — KB-labeled transport: core.upf.activity_during_calls (drop, score=4.28); normalized.upf.gtp_outdatapktn3upf_per_ue (spike, score=4.28) — KB-labeled transport: core.upf.gtp_outdatapktn3upf_per_ue (spike, score=4.28)

Application signals: normalized.smf.bearers_per_ue (shift, score=4.28) — KB-labeled application: core.smf.bearers_per_ue (shift, score=4.28)

Ambiguous signals: normalized.icscf.cdp_replies_per_ue (shift, score=4.28) — KB-labeled mixed: ims.icscf.cdp_replies_per_ue (shift, score=4.28); normalized.icscf.core:rcv_requests_register_per_ue (drop, score=4.28) — KB-labeled mixed: ims.icscf.rcv_requests_register_per_ue (drop, score=4.28); normalized.pcscf.core:rcv_requests_register_per_ue (spike, score=4.28) — KB-labeled mixed: ims.pcscf.rcv_requests_register_per_ue (spike, score=4.28); normalized.pcscf.dialogs_per_ue (shift, score=4.28) — KB-labeled mixed: ims.pcscf.dialogs_per_ue (shift, score=4.28); normalized.scscf.cdp_replies_per_ue (drop, score=4.28) — KB-labeled mixed: ims.scscf.cdp_replies_per_ue (drop, score=4.28) [+2 more]
```

## Transport-Layer Route (Phase 0.6)

### Resolver

**Flow:** `ims_registration` (IMS Registration)  
**Direction:** both  
**Hop count:** 41

**Candidates considered:**

| Flow | Score |
|---|---:|
| `ims_registration` ← chosen | 8 |
| `vonr_call_teardown` | 8 |
| `vonr_call_setup` | 8 |
| `data_pdu_session_user_traffic` | 7 |
| `vonr_media` | 7 |

**Rationale:**

```
Resolved transport path to flow `ims_registration` (score=8, 41 hops on the walk). Load-bearing components: ['icscf', 'pcscf', 'scscf', 'smf', 'upf']. Other candidate flows considered: vonr_call_teardown=8, vonr_call_setup=8, data_pdu_session_user_traffic=7, vonr_media=7.
```

### Walker

**Status:** ✅ **localized**
**First attributed hop:** `pcscf[eth0]`
**Window:** 5s  
**Walked flow:** `ims_registration`

**Per-hop results:**

| # | Node | Kind | Iface | Attribution | Detail |
|---:|---|---|---|---|---|
| 0 | `e2e_ue1` | container | `eth0` | `clean` | _clean_ |
| 1 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 2 | `nr_gnb` | container | `eth0` | `clean` | _clean_ |
| 3 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 4 | `amf` | container | `eth0` | `clean` | _clean_ |
| 5 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 6 | `e2e_ue1` | container | `eth0` | `clean` | _clean_ |
| 7 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 8 | `nr_gnb` | container | `eth0` | `clean` | _clean_ |
| 9 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 10 | `upf` | container | `eth0` | `clean` | _clean_ |
| 11 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 12 | 🎯 `pcscf` | container | `eth0` | `drops_attributed_here` | `qdisc_netem`: 340 dropped, 45.3% |
| 13 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 14 | `icscf` | container | `eth0` | `clean` | _clean_ |
| 15 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 16 | `pyhss` | container | `eth0` | `clean` | _clean_ |
| 17 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 18 | `icscf` | container | `eth0` | `clean` | _clean_ |
| 19 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 20 | `scscf` | container | `eth0` | `clean` | _clean_ |
| 21 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 22 | `pyhss` | container | `eth0` | `clean` | _clean_ |
| 23 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 24 | `scscf` | container | `eth0` | `clean` | _clean_ |
| 25 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 26 | `pyhss` | container | `eth0` | `clean` | _clean_ |
| 27 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 28 | `scscf` | container | `eth0` | `clean` | _clean_ |
| 29 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 30 | `icscf` | container | `eth0` | `clean` | _clean_ |
| 31 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 32 | `pcscf` | container | `eth0` | `drops_attributed_here` | `qdisc_netem`: 340 dropped, 44.9% |
| 33 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 34 | `e2e_ue1` | container | `eth0` | `clean` | _clean_ |
| 35 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 36 | `pcscf` | container | `eth0` | `drops_attributed_here` | `qdisc_netem`: 340 dropped, 44.9% |
| 37 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 38 | `scp` | container | `eth0` | `clean` | _clean_ |
| 39 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 40 | `pcf` | container | `eth0` | `clean` | _clean_ |

### Localized Synthesis

**Verdict:** `localized`  
**Primary suspect NF:** `pcscf`  
**Confidence:** high

**Summary:** Transport-layer fault localized to pcscf[eth0]: qdisc_netem reports 340 packets dropped (45.33%).

**Recommendation:** Inspect tc qdisc on pcscf: `docker exec pcscf tc -s qdisc show dev eth0`.


## Event Aggregation (Phase 1)

**1 events fired during the observation window:**

- `core.upf.activity_during_calls_collapsed` (source: `core.upf.activity_during_calls`, nf: `upf`, t=1779380012.7)  [current_value=0.04025]

## Correlation Analysis (Phase 2)

1 events fired but no composite hypothesis emerged. The events may be from independent faults or lack registered correlation hints in the KB.

## RAG & Operational Lessons (Phase 2.5)

### RAG retrieval — prior similar episodes

**Status:** `hits` — hits=5, top_sim=0.90, top_case=v7/ep_20260514_221925_data_plane_degradation
**Index:** `/home/ehoskas/agentic-network-ops/rag_index`  **Corpus size:** 102 cases
**Classifier label used in retrieval:** `mixed`
**Retrieval params:** k=5, min_similarity=0.4
**Hits (5):**

| Rank | Sim | Case ID | Scenario | Ground truth | Primary suspect | Score |
|---:|---:|---|---|---|---|---:|
| 0 | 90% | `v7/ep_20260514_221925_data_plane_degradation` | Data Plane Degradation | `upf` | `upf` | 100% |
| 1 | 85% | `v7/ep_20260510_185748_call_quality_degradation` | Call Quality Degradation | `rtpengine` | `rtpengine` | 100% |
| 2 | 84% | `v7/ep_20260510_194005_dns_failure` | DNS Failure | `dns` | `dns` | 85% |
| 3 | 83% | `v6/ep_20260430_015439_data_plane_degradation` | Data Plane Degradation | `upf` | `upf` | 85% |
| 4 | 83% | `v6/ep_20260429_160912_s_cscf_crash` | S-CSCF Crash | `scscf` | `scscf` | 100% |

*Rendered block injected into the NA prompt's `{prior_similar_episodes}` placeholder: 4782 chars. Source paths are inlined in the block so the EvidenceValidator can audit any case the NA cites.*

### Operational lessons — hand-authored rules corpus

**Status:** `injected` — lessons=16, chars=15678
**Path:** `/home/ehoskas/agentic-network-ops/agentic_ops_common/rag/lessons.yaml`  **Count:** 16  **Block size:** 15678 chars
**Injected lesson IDs:** `L01`, `L02`, `L03`, `L04`, `L05`, `L06`, `L07`, `L08`, `L09`, `L10`, `L11`, `L12`, `L13`, `L14`, `L15`, `L16`

### NA citations of the injected content

**Cited lesson IDs:**
- `L09`

*Citations are verbatim string matches — case_ids and lesson_ids appear in the NA's emitted text (summary, hypothesis statements, or layer notes). The EvidenceValidator can audit any cited case by following its `source_episode_path` from the retrieval table above.*

## Network Analysis (Phase 3)

**Summary:** pcscf is the root cause, experiencing ~25-30% packet loss on all its interfaces; per L09, the I-CSCF, S-CSCF, and UPF direct anomaly flags are explicitly demoted as downstream consequences (symptoms) of this P-CSCF partition and signaling degradation causing incomplete call setups.

**Ranked hypotheses:**

- **`h1`** (fit=0.95, nf=pcscf, specificity=specific):
    - **Statement:** pcscf is the source of the anomalous SIP REGISTER rates and the resulting downstream UPF media activity collapse.
    - **Supporting events:** `core.upf.activity_during_calls_collapsed`
    - **Falsification probes:**
        - measure_rtt(pcscf, icscf)
        - measure_rtt(rtpengine, pcscf)
        - measure_rtt(pcscf, dns)
- **`h2`** (fit=0.10, nf=upf, specificity=specific):
    - **Statement:** upf is the source of the gtp_outdatapktn3upf_per_ue spike and the activity during calls collapse.
    - **Supporting events:** `core.upf.activity_during_calls_collapsed`
    - **Falsification probes:**
        - measure_rtt(upf, rtpengine)
        - measure_rtt(amf, upf)
- **`h3`** (fit=0.05, nf=icscf, specificity=specific):
    - **Statement:** icscf is the source of the downstream REGISTER and CDP reply rate drops.
    - **Falsification probes:**
        - measure_rtt(icscf, scscf)
        - measure_rtt(pcscf, icscf)


## Falsification Plans (Phase 4)

**3 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `pcscf`)

**Hypothesis:** pcscf is the source of the anomalous SIP REGISTER rates and the resulting downstream UPF media activity collapse.

**Probes (3):**
1. **`measure_rtt`** — measure_rtt('pcscf', icscf_ip) to check transport reachability from pcscf.
    - *Expected if hypothesis holds:* High packet loss or elevated latency is observed on the path from pcscf to icscf.
    - *Falsifying observation:* 0% packet loss and normal latency is observed.
2. **`measure_rtt`** — measure_rtt('rtpengine', pcscf_ip) to test pcscf from a different source.
    - *Expected if hypothesis holds:* High packet loss or elevated latency is observed, corroborating that the deviation belongs to pcscf.
    - *Falsifying observation:* 0% packet loss and normal latency is observed, indicating the original reading was attributable to one of the conflated entries, not pcscf.
3. **`run_kamcmd`** — run_kamcmd('pcscf', 'dlg.list') to show active dialogs directly.
    - *Expected if hypothesis holds:* Value drops to 0 or significantly decreases.
    - *Falsifying observation:* Value remains stable at ~1 per active VoNR call.

*Notes:* Using KB-curated metric candidates and partner probes to isolate pcscf.

### Plan for `h2` (target: `upf`)

**Hypothesis:** upf is the source of the gtp_outdatapktn3upf_per_ue spike and the activity during calls collapse.

**Probes (3):**
1. **`measure_rtt`** — measure_rtt('upf', rtpengine_ip) to verify the media forwarding path.
    - *Expected if hypothesis holds:* High packet loss or elevated latency is observed on the path from upf to rtpengine.
    - *Falsifying observation:* The metric stays at its healthy baseline.
2. **`measure_rtt`** — measure_rtt('amf', upf_ip) to test upf from a different source.
    - *Expected if hypothesis holds:* High packet loss or elevated latency is observed, corroborating that the deviation belongs to upf.
    - *Falsifying observation:* The probe's reading is inconsistent with upf being the source (e.g. the metric stays at its healthy baseline).
3. **`get_dp_quality_gauges`** — window_seconds=120 to check upf.activity_during_calls.
    - *Expected if hypothesis holds:* Active calls are reported but no media is flowing, resulting in a drop in activity_during_calls.
    - *Falsifying observation:* The value remains at ~1.0, indicating traffic fully follows active calls.

*Notes:* Partner probe added for compositional measure_rtt tool, layer scoping removed from expected texts.

### Plan for `h3` (target: `icscf`)

**Hypothesis:** icscf is the source of the downstream REGISTER and CDP reply rate drops.

**Probes (3):**
1. **`measure_rtt`** — measure_rtt('icscf', scscf_ip) to check transport reachability from icscf.
    - *Expected if hypothesis holds:* High packet loss or elevated latency is observed on the path from icscf to scscf.
    - *Falsifying observation:* 0% packet loss and normal latency is observed.
2. **`measure_rtt`** — measure_rtt('pcscf', icscf_ip) to test icscf from a different source.
    - *Expected if hypothesis holds:* High packet loss or elevated latency is observed, corroborating that the deviation belongs to icscf.
    - *Falsifying observation:* 0% packet loss and normal latency is observed, indicating the original reading was attributable to one of the conflated entries, not icscf.
3. **`run_kamcmd`** — run_kamcmd('icscf', 'stats.fetch ims_icscf:uar_timeouts')
    - *Expected if hypothesis holds:* A spike in UAR timeouts is observed.
    - *Falsifying observation:* Value remains at 0.

*Notes:* Includes composition disambiguation partner probe for measure_rtt.


## Parallel Investigators (Phase 5)

**3 sub-Investigator verdict(s):** **1 NOT_DISPROVEN**, **2 DISPROVEN**

### `h1` — ✅ **NOT_DISPROVEN**

**Hypothesis:** pcscf is the source of the anomalous SIP REGISTER rates and the resulting downstream UPF media activity collapse.

**Reasoning:** [Multi-shot consensus — both shots returned NOT_DISPROVEN.]

Shot 1: Network probes observed roughly 30% packet loss in both directions involving the P-CSCF (from pcscf to icscf, and from rtpengine to pcscf), directly confirming transport-layer degradation at the P-CSCF. This confirms that P-CSCF is dropping packets and struggling to forward SIP signaling. Additionally, diagnostic metrics reveal a stall in REGISTER processing, which is the classic SIP-path latency/partition signature on P-CSCF. Note that the run_kamcmd probe on the pcscf container was attempted but failed because the 'dlg.list' command is unavailable.

Shot 2: The hypothesis is NOT_DISPROVEN. Triangulating probes `measure_rtt('pcscf', 'icscf')` and `measure_rtt('rtpengine', 'pcscf')` both reported ~25.7% packet loss, firmly localizing the transport degradation to the P-CSCF container itself rather than a specific path. The third probe (`run_kamcmd` for dialogs) was unavailable, but the transport-layer evidence directly corroborates P-CSCF as the root cause of the signaling anomalies and subsequent media collapse.

**Probes executed (4):**
- **measure_rtt('pcscf', icscf_ip) to check transport reachability from pcscf.** ✓ CONSISTENT
    - *Tool:* `measure_rtt("pcscf", "icscf")`
    - *Observation:* [EVIDENCE: measure_rtt("pcscf", "icscf") -> "28.7879% packet loss"]
    - *Comment:* Observed high packet loss from pcscf to icscf, confirming degraded transport reachability.
- **measure_rtt('rtpengine', pcscf_ip) to test pcscf from a different source.** ✓ CONSISTENT
    - *Tool:* `measure_rtt("rtpengine", "pcscf")`
    - *Observation:* [EVIDENCE: measure_rtt("rtpengine", "pcscf") -> "31.8182% packet loss"]
    - *Comment:* Triangulation probe from rtpengine to pcscf also shows similar packet loss, isolating the problem to pcscf's network interface.
- **run_kamcmd('pcscf', 'dlg.list') to show active dialogs directly.** ~ AMBIGUOUS
    - *Tool:* `run_kamcmd("pcscf", "dlg.list")`
    - *Observation:* [EVIDENCE: run_kamcmd("pcscf", "dlg.list") -> "error: 500 - command dlg.list not found"]
    - *Comment:* The probe could not be executed because the requested kamcmd module/command is not available in the container.
- **Check diagnostic metrics at P-CSCF to confirm SIP REGISTER stall signature.** ✓ CONSISTENT
    - *Tool:* `get_diagnostic_metrics(at_time_ts=1779379995.87537, nfs=["pcscf"])`
    - *Observation:* [EVIDENCE: get_diagnostic_metrics(at_time_ts=1779379995.87537, nfs=["pcscf"]) -> "derived.pcscf_avg_register_time_ms = 0 [derived, ms]"]
    - *Comment:* The derived register time drops to 0 due to stalled REGISTER completions (none completed while requests arrived), confirming the latency/partition signature on the P-CSCF.

### `h2` — ❌ **DISPROVEN**

**Hypothesis:** upf is the source of the gtp_outdatapktn3upf_per_ue spike and the activity during calls collapse.

**Reasoning:** [Multi-shot consensus — both shots returned DISPROVEN.]

Shot 1: The hypothesis claims the UPF is the source of the media activity collapse. However, network probes (`measure_rtt`) from the UPF to RTPEngine and from the AMF to the UPF show 0% packet loss, directly contradicting the mechanism of UPF-localized network degradation. While `upf_activity_during_calls` did drop, the healthy transport paths indicate this is a downstream consequence of a failure elsewhere, not a fault at the UPF itself.

Shot 2: The data plane metrics confirm a collapse in activity during calls, but the probes targeting UPF explicitly rule it out as the source. RTT measurements from UPF to RTPEngine and from AMF to UPF show 0% packet loss and low latency, contradicting the hypothesis that UPF is degraded. Instead, triangulation probes confirm that P-CSCF is experiencing ~30-36% packet loss on its network interfaces, making it the true source of the failure.

**Probes executed (3):**
- **measure_rtt('upf', rtpengine_ip) to verify the media forwarding path.** ✗ CONTRADICTS
    - *Tool:* `measure_rtt("upf", "rtpengine")`
    - *Observation:* [EVIDENCE: measure_rtt("upf", "rtpengine") -> "66 packets transmitted, 66 received, 0% packet loss"]
    - *Comment:* The forwarding path from UPF to RTPEngine is completely healthy, indicating no packet loss is originating at the UPF's egress.
- **measure_rtt('amf', upf_ip) to test upf from a different source.** ✗ CONTRADICTS
    - *Tool:* `measure_rtt("amf", "upf")`
    - *Observation:* [EVIDENCE: measure_rtt("amf", "upf") -> "66 packets transmitted, 66 received, 0% packet loss"]
    - *Comment:* The path from AMF to UPF is also healthy, ruling out UPF's network interface ingress as the source of packet loss.
- **window_seconds=120 to check upf.activity_during_calls.** ✓ CONSISTENT
    - *Tool:* `get_diagnostic_metrics(at_time_ts=1779379995.87537, nfs=["upf"])`
    - *Observation:* [EVIDENCE: get_diagnostic_metrics(at_time_ts=1779379995.87537, nfs=["upf"]) -> "derived.upf_activity_during_calls = 0.1047 [derived, ratio]"]
    - *Comment:* The drop in activity during calls is confirmed, but combined with the clean ping sweeps, it indicates a downstream symptom of signaling failure rather than a UPF-rooted failure.

**Alternative suspects:** pcscf

### `h3` — ❌ **DISPROVEN**

**Hypothesis:** icscf is the source of the downstream REGISTER and CDP reply rate drops.

**Reasoning:** [Multi-shot consensus — both shots returned DISPROVEN.]

Shot 1: The hypothesis is disproven because icscf shows no signs of network or internal degradation. The probe `measure_rtt('icscf', 'scscf')` showed 0% packet loss, confirming icscf can communicate downstream flawlessly. Furthermore, querying `ims_icscf:uar_timeouts` on icscf returned 0. While the path from pcscf to icscf showed ~39% packet loss, triangulation with the healthy icscf-to-scscf path localizes the network partition to pcscf, completely exonerating icscf.

Shot 2: Probes confirm that icscf is not the source of the packet loss. The outbound path from icscf to scscf is perfectly clean (0% loss), while the path from pcscf to icscf experiences 30% packet loss, triangulating the fault to pcscf. Additionally, icscf reports no UAR timeouts, confirming it is not internally dropping or timing out on requests.

**Probes executed (3):**
- **measure_rtt('icscf', scscf_ip) to check transport reachability from icscf.** ✗ CONTRADICTS
    - *Tool:* `measure_rtt("icscf", "scscf")`
    - *Observation:* [EVIDENCE: measure_rtt("icscf", "scscf") -> "66 packets transmitted, 66 received, 0% packet loss, time 6649ms"]
    - *Comment:* The path from icscf to scscf is completely healthy (0% packet loss), contradicting the hypothesis that icscf is the source of downstream communication drops.
- **measure_rtt('pcscf', icscf_ip) to test icscf from a different source.** ~ AMBIGUOUS
    - *Tool:* `measure_rtt("pcscf", "icscf")`
    - *Observation:* [EVIDENCE: measure_rtt("pcscf", "icscf") -> "66 packets transmitted, 40 received, 39.3939% packet loss, time 6695ms"]
    - *Comment:* Although packet loss was observed here, the healthy icscf-to-scscf probe results triangulate this loss to pcscf's interfaces rather than icscf.
- **run_kamcmd('icscf', 'stats.fetch ims_icscf:uar_timeouts')** ✗ CONTRADICTS
    - *Tool:* `run_kamcmd("icscf", "stats.fetch ims_icscf:uar_timeouts")`
    - *Observation:* [EVIDENCE: run_kamcmd("icscf", "stats.fetch ims_icscf:uar_timeouts") -> "ims_icscf.uar_timeouts: 0"]
    - *Comment:* UAR timeouts are at 0, confirming icscf is not experiencing internal failures.

**Alternative suspects:** pcscf


## Evidence Validation (Phase 6)

**Overall verdict:** clean
**Overall confidence:** high

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 9 | 4/4 | clean | high |
| `InvestigatorAgent_h2` | 11 | 3/3 | clean | high |
| `InvestigatorAgent_h3` | 6 | 3/3 | clean | high |


## Ground Truth

**Failure domain:** ims_signaling  
**Protocol impact:** SIP  
**Affected components:** pcscf  
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
> - **summary**: Transport-layer fault localized to pcscf[eth0]: qdisc_netem reports 340 packets dropped (45.33%).
> - **timeline**:
>     1. Walk started for flow 'ims_registration' evaluating topology up to the IMS stack.
>     2. Attribution localized at hop 13 (pcscf[eth0]) due to 'drops_attributed_here' identifying an authored 30% loss qdisc.
>     3. Walk completed with high confidence in pcscf packet drop root cause; application-layer probes further confirmed stall in REGISTER processing.
> - **root_cause**: Kernel-level packet drop on pcscf's network interface: a `tc netem` qdisc is actively dropping approximately 30-45% of packets, leading to signaling latency and failures which cascade into downstream media activity collapses at the UPF. (primary_suspect_nf: `pcscf`)
> - **affected_components**:
>     - `pcscf`: Root Cause
> - **recommendation**: Inspect tc qdisc on pcscf: `docker exec pcscf tc -s qdisc show dev eth0`.
> - **confidence**: high
> - **verdict_kind**: localized
> - **explanation**: Per-hop walk through the first attributed hop on the `ims_registration` flow:
> 
> | # | hop | kind | iface | prober | attribution |
> |---|-----|------|-------|--------|-------------|
> | 1 | e2e_ue1 | container | eth0 | KernelHopProber | clean |
> | 2 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 3 | nr_gnb | container | eth0 | KernelHopProber | clean |
> | 4 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 5 | amf | container | eth0 | KernelHopProber | clean |
> | 6 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 7 | e2e_ue1 | container | eth0 | KernelHopProber | clean |
> | 8 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 9 | nr_gnb | container | eth0 | KernelHopProber | clean |
> | 10 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 11 | upf | container | eth0 | KernelHopProber | clean |
> | 12 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 13 | pcscf | container | eth0 | KernelHopProber | 🎯 drops_attributed_here (qdisc_netem, 340 dropped, 45.3%) |
> 
> Verbatim counter excerpt for the attributed hop:
> ```
> pcscf[eth0] qdisc=netem, authored loss=30%: sent=750 dropped=340 (45.33%)
> ---tc -s qdisc show dev eth0---
> qdisc netem 80a6: root refcnt 9 limit 1000 loss 30%
>  Sent 172165 bytes 750 pkt (dropped 340, overlimits 0 requeues 0) 
>  backlog 0b 0p requeues 0
> ```
> 
> Classifier rationale: label=mixed. Both transport-layer (2) and application-layer (1) signals are load-bearing. Path walk runs first; falls through to the application-layer pipeline if the walk produces null localization.

### Scoring Breakdown

**Overall score: 100%**

**Scorer assessment:** The agent delivered an exceptionally accurate diagnosis, correctly identifying the P-CSCF packet loss down to the exact interface and drop rate using direct tool evidence.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | Yes | The agent correctly identified the root cause as packet drops on the P-CSCF network interface, matching the simulated 30% packet loss on the P-CSCF signaling-plane container. |
| Component overlap | 100% | The agent correctly identified 'pcscf' as the primary affected component and labeled it as the 'Root Cause'. |
| Severity correct | Yes | The agent correctly characterized the failure as a packet drop/loss degradation (30-45% packet loss) causing signaling latency and failures, rather than a complete container outage. |
| Fault type identified | Yes | The agent explicitly identified the fault type as packet drops/loss on the network interface. |
| Layer accuracy | Yes | No layer status information was provided in the intermediate network analysis, so no misattribution was detected. |
| Confidence calibrated | Yes | The agent's confidence was high, which is fully justified given the precise identification of the packet loss and the direct evidence from the 'tc qdisc' tool. |

**Ranking position:** #1 — The correct root cause (pcscf packet loss) was identified as the primary and only suspect.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 680,746 |
| Output tokens | 10,146 |
| Thinking tokens | 39,526 |
| **Total tokens** | **730,418** |

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
| NetworkAnalystAgent | 323,330 | 19 | 6 |
| Phase 3 NetworkAnalyst__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 17,064 | 0 | 1 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 18,690 | 0 | 1 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| InvestigatorAgent_h1 | 52,079 | 4 | 3 |
| InvestigatorAgent_h1 | 60,065 | 5 | 3 |
| InvestigatorAgent_h1__reconciliation | 0 | 0 | 0 |
| InvestigatorAgent_h2 | 84,830 | 5 | 4 |
| InvestigatorAgent_h2 | 93,454 | 6 | 4 |
| InvestigatorAgent_h2__reconciliation | 0 | 0 | 0 |
| InvestigatorAgent_h3 | 33,365 | 3 | 2 |
| InvestigatorAgent_h3 | 30,817 | 3 | 2 |
| InvestigatorAgent_h3__reconciliation | 0 | 0 | 0 |
| Phase5FanOutAudit | 0 | 0 | 0 |
| Phase6.5CandidatePool | 0 | 0 | 0 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 16,724 | 0 | 1 |
| Phase 7 Synthesis__guardrail | 0 | 0 | 0 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 649.8s
