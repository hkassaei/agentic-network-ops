# Episode Report: RTPEngine Latency Injection

**Agent:** v7  
**Episode ID:** ep_20260521_032923_rtpengine_latency_injection  
**Date:** 2026-05-21T03:29:24.941647+00:00  
**Duration:** 537.7s  

---

## Scenario

**Category:** network  
**Blast radius:** single_nf  
**Description:** Inject 100ms latency on RTPEngine egress. Same fault locus as Call Quality Degradation (rtpengine container, kernel-level qdisc) but the manifestation is delay rather than drop. Tests v7's path-walk generalization from `drops_attributed_here` to `latency_at_hop` — both are first-class HopAttribution variants. Operators see audio jitter / one-way audio rather than gappy audio. v7's `KernelHopProber` reads the qdisc's authored `delay 100ms` parameter and v7's unified Synthesis LLM emits verdict_kind=localized with attribution_kind=latency_at_hop. v6's per-NF pipeline mis-diagnoses for the same reason it mis-diagnoses Call Quality Degradation: rtpengine.errors_per_second stays at 0 (the relay loop sees no errors), and 3-ping measure_rtt is too undersampled to reliably distinguish 100ms latency from Docker-bridge baseline.

## Faults Injected

- **network_latency** on `rtpengine` — {'delay_ms': 100, 'jitter_ms': 0}

## Baseline (Pre-Fault)

Stack phase before injection: **ready**
All containers running at baseline.

## Fault Propagation Verification

**Verdict:** ✅ `confirmed`

- **Propagation window:** 124s (ObservationTrafficAgent drove traffic for this window; verifier added wait=0s on top)
- **Nodes with significant deltas:** 4
- **Nodes with any drift:** 5

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 55.60 (per-bucket threshold: 28.18, context bucket (1, 1), trained on 323 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following metrics deviate from their learned-healthy baseline. Treat each as a semantic observation (meaning + numbers), not a number alone — the KB's interpretation is the authoritative reading.

- **`derived.upf_activity_during_calls`** (UPF activity consistency with active dialogs) — current **0.02 ratio** vs learned baseline **0.54 ratio** (MEDIUM, drop)
    - **What it measures:** Cross-layer consistency check between IMS dialog state and UPF
throughput. A drop while dialogs_per_ue is non-zero is a
smoking-gun signal for media-plane failure independent of signaling.
    - **Drop means:** Active calls reported but no media flowing — media path broken (UPF, RTPEngine, or N3 packet loss).
    - **Healthy typical range:** 0.3–1 ratio
    - **Healthy invariant:** 1.0 when traffic fully follows active calls; 0.0 when signaling says active but data plane is silent.

- **`normalized.icscf.cdp_replies_per_ue`** (I-CSCF Diameter reply rate per UE) — current **0.08 replies_per_second_per_ue** vs learned baseline **0.03 replies_per_second_per_ue** (MEDIUM, spike)
    - **What it measures:** Liveness of the I-CSCF↔HSS Cx path. Drops to 0 when HSS is unreachable OR when no signaling is occurring at the I-CSCF (idle or upstream P-CSCF partitioned).
    - **Spike means:** Either HSS is unreachable or upstream signaling has stopped reaching I-CSCF.
    - **Healthy typical range:** 0–1 replies_per_second_per_ue

- **`normalized.icscf.core:rcv_requests_invite_per_ue`** (SIP INVITE rate per UE at I-CSCF) — current **0.02 requests_per_second** vs learned baseline **0.00 requests_per_second** (MEDIUM, spike)
    - **What it measures:** Health of call-setup forwarding P-CSCF → I-CSCF. Partition signature
same as REGISTER rate.
    - **Spike means:** Forwarding failure.
    - **Healthy typical range:** 0–0.2 requests_per_second
    - **Healthy invariant:** Per-UE rate. Tracks pcscf.invite rate.

- **`normalized.icscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at I-CSCF) — current **0.12 requests_per_second** vs learned baseline **0.06 requests_per_second** (MEDIUM, spike)
    - **What it measures:** Health of the P-CSCF → I-CSCF forwarding path (Mw interface). When
this drops to zero while P-CSCF REGISTER rate is still non-zero,
it's the SIGNATURE of an IMS partition between P-CSCF and I-CSCF.
    - **Spike means:** Forwarding issue on the Mw interface, or P-CSCF stopped forwarding.
    - **Healthy typical range:** 0–0.5 requests_per_second
    - **Healthy invariant:** Per-UE rate. Should closely track ims.pcscf.rcv_requests_register_per_ue.

- **`normalized.pcscf.core:rcv_requests_invite_per_ue`** (SIP INVITE rate per UE at P-CSCF) — current **0.03 requests_per_second** vs learned baseline **0.00 requests_per_second** (MEDIUM, spike)
    - **What it measures:** Call attempt rate from registered UEs. Unlike REGISTER (periodic),
INVITEs only fire when UEs place calls. Zero is normal during
quiet periods; nonzero INVITE with zero dialogs is the signature
of call setup failure.
    - **Spike means:** Fewer call attempts.
    - **Healthy typical range:** 0–0.2 requests_per_second
    - **Healthy invariant:** Per-UE rate.

- **`normalized.pcscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at P-CSCF) — current **0.12 requests_per_second** vs learned baseline **0.06 requests_per_second** (MEDIUM, spike)
    - **What it measures:** How actively UEs are refreshing their IMS registrations with the
P-CSCF. REGISTERs arrive periodically (re-registration timer) plus
at attach. Sustained zero means UEs cannot reach P-CSCF OR the
UE-to-network SIP path is broken.
    - **Spike means:** Fewer REGISTERs than expected — UE connectivity or P-CSCF reachability issue.
    - **Healthy typical range:** 0–0.5 requests_per_second
    - **Healthy invariant:** Per-UE rate — same value at any deployment scale.

- **`normalized.pcscf.dialogs_per_ue`** (Active SIP dialogs per registered UE at P-CSCF) — current **2.00 count** vs learned baseline **0.48 count** (MEDIUM, spike)
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

- **`normalized.scscf.core:rcv_requests_invite_per_ue`** (SIP INVITE rate per UE at S-CSCF) — current **0.03 requests_per_second** vs learned baseline **0.00 requests_per_second** (MEDIUM, spike)
    - **What it measures:** S-CSCF participation in call setup. Zero when calls aren't being
placed OR S-CSCF not receiving forwarded INVITEs.
    - **Spike means:** Upstream forwarding issue.
    - **Healthy typical range:** 0–0.2 requests_per_second
    - **Healthy invariant:** Per-UE rate.

- **`normalized.scscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at S-CSCF) — current **0.12 requests_per_second** vs learned baseline **0.06 requests_per_second** (MEDIUM, spike)
    - **What it measures:** Health of the I-CSCF → S-CSCF forwarding path. Drop to zero while
I-CSCF is receiving REGISTERs = S-CSCF-side issue (crashed, or
I-CSCF → S-CSCF path broken).
    - **Spike means:** I-CSCF not forwarding or S-CSCF not receiving.
    - **Healthy typical range:** 0–0.5 requests_per_second
    - **Healthy invariant:** Per-UE rate. Tracks icscf.register rate.


## Symptom Classifier (Phase 0.5)

**Label:** `mixed`  
**Flag counts:** transport=1, application=0, ambiguous=9

### Transport-bucket flags (1)

| Metric | Direction | Score | KB-driven reason |
|---|---|---:|---|
| `derived.upf_activity_during_calls` | drop | 4.28 | KB-labeled transport: core.upf.activity_during_calls (drop, score=4.28) |

### Ambiguous-bucket flags (9)

| Metric | Direction | Score | KB-driven reason |
|---|---|---:|---|
| `normalized.icscf.cdp_replies_per_ue` | spike | 4.28 | KB-labeled mixed: ims.icscf.cdp_replies_per_ue (spike, score=4.28) |
| `normalized.icscf.core:rcv_requests_invite_per_ue` | spike | 4.28 | KB-labeled mixed: ims.icscf.rcv_requests_invite_per_ue (spike, score=4.28) |
| `normalized.icscf.core:rcv_requests_register_per_ue` | spike | 4.28 | KB-labeled mixed: ims.icscf.rcv_requests_register_per_ue (spike, score=4.28) |
| `normalized.pcscf.core:rcv_requests_invite_per_ue` | spike | 4.28 | KB-labeled mixed: ims.pcscf.rcv_requests_invite_per_ue (spike, score=4.28) |
| `normalized.pcscf.core:rcv_requests_register_per_ue` | spike | 4.28 | KB-labeled mixed: ims.pcscf.rcv_requests_register_per_ue (spike, score=4.28) |
| `normalized.pcscf.dialogs_per_ue` | spike | 4.28 | KB-labeled mixed: ims.pcscf.dialogs_per_ue (spike, score=4.28) |
| `normalized.scscf.cdp_replies_per_ue` | spike | 4.28 | KB-labeled mixed: ims.scscf.cdp_replies_per_ue (spike, score=4.28) |
| `normalized.scscf.core:rcv_requests_invite_per_ue` | spike | 4.28 | KB-labeled mixed: ims.scscf.rcv_requests_invite_per_ue (spike, score=4.28) |
| `normalized.scscf.core:rcv_requests_register_per_ue` | spike | 4.28 | KB-labeled mixed: ims.scscf.rcv_requests_register_per_ue (spike, score=4.28) |

**Rationale:**

```
label=mixed. 1 transport-layer signal(s) plus 9 ambiguous signal(s) clustering on a different NF-owner layer (transport on core; ambiguous cluster on ims (100%)). Treated as compound: walker plus application-layer pipeline both run; Synthesis merges into a single (potentially multi-root-cause) verdict. See ADR multi_fault_orchestration.md.

Transport signals: derived.upf_activity_during_calls (drop, score=4.28) — KB-labeled transport: core.upf.activity_during_calls (drop, score=4.28)

Ambiguous signals: normalized.icscf.cdp_replies_per_ue (spike, score=4.28) — KB-labeled mixed: ims.icscf.cdp_replies_per_ue (spike, score=4.28); normalized.icscf.core:rcv_requests_invite_per_ue (spike, score=4.28) — KB-labeled mixed: ims.icscf.rcv_requests_invite_per_ue (spike, score=4.28); normalized.icscf.core:rcv_requests_register_per_ue (spike, score=4.28) — KB-labeled mixed: ims.icscf.rcv_requests_register_per_ue (spike, score=4.28); normalized.pcscf.core:rcv_requests_invite_per_ue (spike, score=4.28) — KB-labeled mixed: ims.pcscf.rcv_requests_invite_per_ue (spike, score=4.28); normalized.pcscf.core:rcv_requests_register_per_ue (spike, score=4.28) — KB-labeled mixed: ims.pcscf.rcv_requests_register_per_ue (spike, score=4.28) [+4 more]
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
| `diameter_cx_authentication` | 4 |
| `data_pdu_session_user_traffic` | 2 |

**Rationale:**

```
Resolved transport path to flow `ims_registration` (score=8, 41 hops on the walk). Load-bearing components: ['icscf', 'pcscf', 'scscf', 'upf']. Other candidate flows considered: vonr_call_teardown=8, vonr_call_setup=8, diameter_cx_authentication=4, data_pdu_session_user_traffic=2.
```

### Walker

**Status:** ⚠️ **null localization**
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
| 12 | `pcscf` | container | `eth0` | `clean` | _clean_ |
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
| 32 | `pcscf` | container | `eth0` | `clean` | _clean_ |
| 33 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 34 | `e2e_ue1` | container | `eth0` | `clean` | _clean_ |
| 35 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 36 | `pcscf` | container | `eth0` | `clean` | _clean_ |
| 37 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 38 | `scp` | container | `eth0` | `clean` | _clean_ |
| 39 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 40 | `pcf` | container | `eth0` | `clean` | _clean_ |

### Localized Synthesis

*Walker found no hop with attribution. Phase 0.6 returned None and the orchestrator fell through to the application-layer pipeline (Phases 1-7) below — the diagnosis you see in `Agent Diagnosis` came from that fallback path, not from Phase 0.6.*

## Event Aggregation (Phase 1)

**1 events fired during the observation window:**

- `core.upf.activity_during_calls_collapsed` (source: `core.upf.activity_during_calls`, nf: `upf`, t=1779334281.3)  [current_value=0.045656499999999996]

## Correlation Analysis (Phase 2)

1 events fired but no composite hypothesis emerged. The events may be from independent faults or lack registered correlation hints in the KB.

## RAG & Operational Lessons (Phase 2.5)

### RAG retrieval — prior similar episodes

**Status:** `hits` — hits=5, top_sim=0.87, top_case=v7/ep_20260514_221925_data_plane_degradation
**Index:** `/home/ehoskas/agentic-network-ops/rag_index`  **Corpus size:** 102 cases
**Classifier label used in retrieval:** `mixed`
**Retrieval params:** k=5, min_similarity=0.4
**Hits (5):**

| Rank | Sim | Case ID | Scenario | Ground truth | Primary suspect | Score |
|---:|---:|---|---|---|---|---:|
| 0 | 87% | `v7/ep_20260514_221925_data_plane_degradation` | Data Plane Degradation | `upf` | `upf` | 100% |
| 1 | 85% | `v6/ep_20260430_014832_hss_unresponsive` | HSS Unresponsive | `pyhss` | `pyhss` | 95% |
| 2 | 85% | `v7/ep_20260509_135947_call_quality_degradation` | Call Quality Degradation | `rtpengine` | `rtpengine` | 100% |
| 3 | 84% | `v7/ep_20260514_213640_cascading_ims_failure` | Cascading IMS Failure | `pyhss, scscf` | `pyhss` | 100% |
| 4 | 83% | `v7/ep_20260510_115059_data_plane_degradation` | Data Plane Degradation | `upf` | `upf` | 100% |

*Rendered block injected into the NA prompt's `{prior_similar_episodes}` placeholder: 4948 chars. Source paths are inlined in the block so the EvidenceValidator can audit any case the NA cites.*

### Operational lessons — hand-authored rules corpus

**Status:** `injected` — lessons=16, chars=15678
**Path:** `/home/ehoskas/agentic-network-ops/agentic_ops_common/rag/lessons.yaml`  **Count:** 16  **Block size:** 15678 chars
**Injected lesson IDs:** `L01`, `L02`, `L03`, `L04`, `L05`, `L06`, `L07`, `L08`, `L09`, `L10`, `L11`, `L12`, `L13`, `L14`, `L15`, `L16`

### NA citations of the injected content

**Cited lesson IDs:**
- `L04`

*Citations are verbatim string matches — case_ids and lesson_ids appear in the NA's emitted text (summary, hypothesis statements, or layer notes). The EvidenceValidator can audit any cited case by following its `source_episode_path` from the retrieval table above.*

## Network Analysis (Phase 3)

**Summary:** The primary fault originates at rtpengine, which is exhibiting a 100ms network latency that stalls call setups; this explicitly demotes UPF, P-CSCF, I-CSCF, and S-CSCF as secondary reporters, since the latency causes the media collapse at UPF and inflates the system-wide signaling retries across the CSCFs.

**Ranked hypotheses:**

- **`h1`** (fit=0.95, nf=rtpengine, specificity=specific):
    - **Statement:** rtpengine is the source of the collapsed UPF activity during calls and the system-wide IMS signaling spikes.
    - **Supporting events:** `core.upf.activity_during_calls_collapsed`
    - **Falsification probes:**
        - Check tc -s qdisc show dev eth0 on rtpengine to detect kernel-level network latency or drops, as L04 notes internal errors_per_second is blind to this.
        - Review measure_rtt results from P-CSCF to RTPEngine to confirm the 100ms path latency.
- **`h2`** (fit=0.30, nf=upf, specificity=moderate):
    - **Statement:** upf is the source of the collapsed activity during calls, aligning with the vonr_media_stops branch of the n3_data_plane_outage chain.
    - **Supporting events:** `core.upf.activity_during_calls_collapsed`
    - **Falsification probes:**
        - Check UPF application logs for data plane processing errors or internal packet drops.
        - Verify with measure_rtt if the UPF to RTPEngine path is the exclusive source of the fault rather than RTPEngine itself.
- **`h3`** (fit=0.15, nf=pcscf, specificity=moderate):
    - **Statement:** pcscf is the source of the elevated active dialogs and signaling rates.
    - **Falsification probes:**
        - Check P-CSCF application metrics and logs for internal stalls or processing errors during call setup.
        - Run measure_rtt from UE to P-CSCF to confirm signaling path latency.


## Falsification Plans (Phase 4)

**3 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `rtpengine`)

**Hypothesis:** rtpengine is the source of the collapsed UPF activity during calls and the system-wide IMS signaling spikes.

**Probes (3):**
1. **`measure_rtt`** — measure_rtt('pcscf', rtpengine_ip)
    - *Expected if hypothesis holds:* High round-trip time (e.g., ~100ms) or packet loss is observed on the path to rtpengine.
    - *Falsifying observation:* The probe's reading is inconsistent with rtpengine being the source (e.g., latency is low and no packet loss is observed).
2. **`measure_rtt`** — measure_rtt('pcscf', upf_ip)
    - *Expected if hypothesis holds:* Latency is low (< 5ms) on this path, isolating the latency observed in the first probe to rtpengine rather than the pcscf network interface.
    - *Falsifying observation:* High latency is observed on this path as well, meaning the original reading was attributable to the pcscf network interface, not rtpengine.
3. **`get_dp_quality_gauges`** — window_seconds=120 to read rtpengine.errors_per_second and rtpengine.loss_ratio
    - *Expected if hypothesis holds:* Probe reads `rtpengine.errors_per_second` with a spike > 0, or `rtpengine.loss_ratio` > 0.
    - *Falsifying observation:* The probe's reading is inconsistent with rtpengine being the source (e.g., the metrics stay at their healthy baseline of zero).

*Notes:* Testing the specific 100ms network latency identified by the NA. measure_rtt targets rtpengine from pcscf, with a partner probe to upf to isolate the delay. get_dp_quality_gauges checks the KB-authored verification path for rtpengine drops.

### Plan for `h2` (target: `upf`)

**Hypothesis:** upf is the source of the collapsed activity during calls, aligning with the vonr_media_stops branch of the n3_data_plane_outage chain.

**Probes (3):**
1. **`measure_rtt`** — measure_rtt('rtpengine', upf_ip)
    - *Expected if hypothesis holds:* High round-trip time or packet loss is observed on the path to upf.
    - *Falsifying observation:* The probe's reading is inconsistent with upf being the source (e.g., latency is low and no packet loss is observed).
2. **`measure_rtt`** — measure_rtt('rtpengine', pcscf_ip)
    - *Expected if hypothesis holds:* Latency is low (< 5ms) on this path, isolating the latency observed in the first probe to upf rather than the rtpengine network interface.
    - *Falsifying observation:* High latency is observed on this path as well, meaning the original reading was attributable to the rtpengine network interface, not upf.
3. **`get_dp_quality_gauges`** — window_seconds=120 to check upf.gtp_indatapktn3upf_per_ue and upf.gtp_outdatapktn3upf_per_ue
    - *Expected if hypothesis holds:* Probe reads a drop in `upf.gtp_indatapktn3upf_per_ue` or `upf.gtp_outdatapktn3upf_per_ue` indicating a collapsed data plane.
    - *Falsifying observation:* The probe reads values within the typical healthy range, staying at their baseline.

*Notes:* Aligns with the n3_data_plane_outage chain. Uses partner measure_rtt probes to disambiguate upf-path latency from rtpengine constraints.

### Plan for `h3` (target: `pcscf`)

**Hypothesis:** pcscf is the source of the elevated active dialogs and signaling rates.

**Probes (3):**
1. **`measure_rtt`** — measure_rtt('pcscf', icscf_ip)
    - *Expected if hypothesis holds:* High latency or packet loss is observed on the path to icscf.
    - *Falsifying observation:* The probe's reading is inconsistent with pcscf being the source (e.g., latency is low and no packet loss is observed).
2. **`measure_rtt`** — measure_rtt('pcscf', upf_ip)
    - *Expected if hypothesis holds:* Latency is low (< 5ms) on this path, isolating the latency observed in the first probe to the path toward icscf rather than the pcscf network interface.
    - *Falsifying observation:* High latency is observed on this path as well, meaning the original reading was attributable to the pcscf network interface.
3. **`run_kamcmd`** — run_kamcmd('pcscf', 'stats.fetch script:register_time')
    - *Expected if hypothesis holds:* Probe reads `pcscf.avg_register_time_ms` and finds a value significantly elevated above the healthy range or zero (stall signature).
    - *Falsifying observation:* The probe reads a value within the typical healthy range (e.g., 150-350ms), inconsistent with pcscf stalling signaling.

*Notes:* Checks P-CSCF latency and stall states as indicated by the NA. Uses partner measure_rtt probes to cleanly attribute path delays.


## Parallel Investigators (Phase 5)

**3 sub-Investigator verdict(s):** **1 NOT_DISPROVEN**, **2 DISPROVEN**

### `h1` — ✅ **NOT_DISPROVEN**

**Hypothesis:** rtpengine is the source of the collapsed UPF activity during calls and the system-wide IMS signaling spikes.

**Reasoning:** [Multi-shot consensus — both shots returned NOT_DISPROVEN.]

Shot 1: Triangulation confirms the fault is at rtpengine: measure_rtt from P-CSCF to RTPEngine shows a solid 100ms delay, while P-CSCF to UPF shows <1ms. This successfully isolates the latency to RTPEngine, ruling out P-CSCF's network interface. The lack of packet loss and internal errors in the data plane gauges is consistent with a pure network delay injection, which stalls signaling timers without incrementing drop counters.

Shot 2: The hypothesis asserts that rtpengine is the source of the failure. The measure_rtt probe from pcscf to rtpengine reveals a highly elevated ~100ms latency. The partner probe from pcscf to upf shows normal low latency (<1ms), which triangulates the 100ms delay explicitly to rtpengine rather than the pcscf network interface. While application-layer metrics (errors_per_second and loss_ratio) remain at 0, this weak negative is expected because internal application metrics are blind to kernel-level network latency. The strong positive evidence from the transport layer confirms the fault originates at rtpengine.

**Probes executed (3):**
- **measure_rtt('pcscf', rtpengine_ip)** ✓ CONSISTENT
    - *Tool:* `measure_rtt("pcscf", "rtpengine")`
    - *Observation:* [EVIDENCE: measure_rtt("pcscf", "rtpengine") -> "66 packets transmitted, 66 received, 0% packet loss, time 6578ms\nrtt min/avg/max/mdev = 100.079/100.287/100.663/0.118 ms"]
    - *Comment:* Strong positive confirmation of the ~100ms round-trip time on the path to RTPEngine.
- **measure_rtt('pcscf', upf_ip)** ✓ CONSISTENT
    - *Tool:* `measure_rtt("pcscf", "upf")`
    - *Observation:* [EVIDENCE: measure_rtt("pcscf", "upf") -> "66 packets transmitted, 66 received, 0% packet loss, time 6710ms\nrtt min/avg/max/mdev = 0.036/0.094/0.216/0.032 ms"]
    - *Comment:* The low latency on the path to UPF acts as a perfect triangulation point, ruling out the P-CSCF network interface and isolating the 100ms delay to RTPEngine.
- **window_seconds=120 to read rtpengine.errors_per_second and rtpengine.loss_ratio** ~ AMBIGUOUS
    - *Tool:* `get_dp_quality_gauges(window_seconds=120, at_time_ts=1779334215.21017)`
    - *Observation:* [EVIDENCE: get_dp_quality_gauges(at_time_ts=1779334215.21017, window_seconds=120) -> "loss (recent)  : 0.00"]
    - *Comment:* While the plan expected loss_ratio or errors_per_second to spike, a pure network delay fault (confirmed by measure_rtt) does not trigger RTCP loss or relay loop errors. This metric is thus a weak negative that does not override the strong positive latency findings.

### `h2` — ❌ **DISPROVEN**

**Hypothesis:** upf is the source of the collapsed activity during calls, aligning with the vonr_media_stops branch of the n3_data_plane_outage chain.

**Reasoning:** [Multi-shot consensus — both shots returned DISPROVEN.]

Shot 1: Triangulation probes directly refute the hypothesis that upf is the source of the fault. While the path from rtpengine to upf showed 100ms latency, a partner probe from rtpengine to pcscf revealed the exact same 100ms delay. This localizes the latency definitively to rtpengine's network interface rather than upf, disproving upf as the primary suspect.

Shot 2: Network latency of ~100ms was observed on the path from rtpengine to upf. However, a partner probe from rtpengine to an independent destination (pcscf) also showed ~100ms latency. This cross-path triangulation localizes the network latency to the rtpengine network interface, exonerating the UPF as the source. Additionally, data plane gauges confirm UPF inbound and outbound packets are symmetric, contradicting a UPF-specific packet drop.

**Probes executed (3):**
- **measure_rtt('rtpengine', upf_ip)** ✓ CONSISTENT
    - *Tool:* `measure_rtt("rtpengine", "upf")`
    - *Observation:* [EVIDENCE: measure_rtt("rtpengine", "upf") -> "rtt min/avg/max/mdev = 100.047/100.219/100.428/0.097 ms"]
    - *Comment:* Revealed 100ms latency on the path to UPF, which on its own is consistent with the hypothesis but conflates UPF with RTPEngine.
- **measure_rtt('rtpengine', pcscf_ip)** ✗ CONTRADICTS
    - *Tool:* `measure_rtt("rtpengine", "pcscf")`
    - *Observation:* [EVIDENCE: measure_rtt("rtpengine", "pcscf") -> "rtt min/avg/max/mdev = 100.036/100.231/100.603/0.121 ms"]
    - *Comment:* Showed identical 100ms latency to an entirely different component (P-CSCF), proving the latency originates at RTPEngine, not UPF.
- **window_seconds=120 to check upf.gtp_indatapktn3upf_per_ue and upf.gtp_outdatapktn3upf_per_ue** ~ AMBIGUOUS
    - *Tool:* `get_dp_quality_gauges(at_time_ts=1779334215.21017, window_seconds=120)`
    - *Observation:* [EVIDENCE: get_dp_quality_gauges(at_time_ts=1779334215.21017, window_seconds=120) -> "UPF:\n    in  packets/sec: 2.5\n    out packets/sec: 2.4"]
    - *Comment:* Data plane rates are low (around 2.5 pps) indicating upstream starvation due to the RTPEngine latency, but they do not confirm a UPF internal failure as the primary cause since the rates are symmetric.

**Alternative suspects:** rtpengine

### `h3` — ❌ **DISPROVEN**

**Hypothesis:** pcscf is the source of the elevated active dialogs and signaling rates.

**Reasoning:** [Multi-shot consensus — both shots returned DISPROVEN.]

Shot 1: P-CSCF is operating normally and is not the source of the latency or stalls. Network probes from P-CSCF to I-CSCF and UPF show <1ms latency and 0% packet loss, clearing the P-CSCF network interface. Internal processing metrics (derived.pcscf_avg_register_time_ms = 169.7ms) show P-CSCF is well within healthy limits and is not stalling signaling. An additional probe verified that rtpengine has a persistent 100ms latency, proving it is the actual cause of the signaling stalls.

Shot 2: P-CSCF is healthy and is not the source of the delays. Round-trip times from P-CSCF to both I-CSCF and UPF are well under 1ms, confirming the P-CSCF network interface is functioning normally. Furthermore, P-CSCF's internal script execution metrics show an average register time of 169.7ms, which is completely within the healthy range, indicating no internal stalls. A supplementary probe revealed a 100ms path latency between P-CSCF and RTPEngine, confirming that the elevated signaling states at P-CSCF are a cascading effect caused by the RTPEngine path, not a primary fault at P-CSCF.

**Probes executed (4):**
- **measure_rtt('pcscf', icscf_ip) to check latency on the path to icscf.** ✗ CONTRADICTS
    - *Tool:* `measure_rtt("pcscf", "icscf")`
    - *Observation:* [EVIDENCE: measure_rtt("pcscf", "icscf") -> "66 packets transmitted, 66 received, 0% packet loss, time 6694ms\nrtt min/avg/max/mdev = 0.040/0.084/0.145/0.022 ms"]
    - *Comment:* Network latency is <1ms and no packet loss is observed, ruling out P-CSCF to I-CSCF network path issues.
- **measure_rtt('pcscf', upf_ip) to isolate if latency is attributable to pcscf network interface.** ✗ CONTRADICTS
    - *Tool:* `measure_rtt("pcscf", "upf")`
    - *Observation:* [EVIDENCE: measure_rtt("pcscf", "upf") -> "66 packets transmitted, 66 received, 0% packet loss, time 6755ms\nrtt min/avg/max/mdev = 0.034/0.080/0.152/0.023 ms"]
    - *Comment:* Latency is also <1ms towards UPF, demonstrating the P-CSCF network interface itself is perfectly healthy.
- **run_kamcmd('pcscf', 'stats.fetch script:register_time') to check for internal stalling in P-CSCF.** ✗ CONTRADICTS
    - *Tool:* `run_kamcmd("pcscf", "stats.fetch script:register_time")`
    - *Observation:* [EVIDENCE: run_kamcmd("pcscf", "stats.fetch script:register_time") -> "script.register_time: 26971"] combined with [EVIDENCE: get_diagnostic_metrics(at_time_ts=1779334215.21017, nfs=["pcscf", "rtpengine"]) -> "derived.pcscf_avg_register_time_ms = 169.7 [derived, ms]... healthy_range = [150, 350]"]
    - *Comment:* Average registration processing time translates to 169.7ms, safely within the healthy 150-350ms range. P-CSCF is not stalling signaling internally.
- **measure_rtt('rtpengine', 'upf') to verify if latency is actually originating elsewhere.** ✗ CONTRADICTS
    - *Tool:* `measure_rtt("rtpengine", "upf")`
    - *Observation:* [EVIDENCE: measure_rtt("rtpengine", "upf") -> "66 packets transmitted, 66 received, 0% packet loss, time 6578ms\nrtt min/avg/max/mdev = 100.079/100.282/100.723/0.138 ms"]
    - *Comment:* Reveals exactly 100ms latency originating at rtpengine, confirming rtpengine as the true source of the fault rather than P-CSCF.

**Alternative suspects:** rtpengine


## Evidence Validation (Phase 6)

**Overall verdict:** clean
**Overall confidence:** high

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 8 | 3/3 | clean | high |
| `InvestigatorAgent_h2` | 6 | 3/3 | clean | high |
| `InvestigatorAgent_h3` | 10 | 5/5 | clean | high |


## Ground Truth

**Failure domain:** ims_media  
**Protocol impact:** RTP  
**Affected components:** rtpengine  
**Severity:** degraded

## Agent Diagnosis

**Model:** v7-adk/pro=gemini-3.1-pro-preview+flash=gemini-3.5-flash  
**Time to diagnosis:** 398.1s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: Network latency of ~100ms originating at RTPEngine is stalling IMS call setups and causing cascaded signaling spikes.
> - **timeline**:
>     1. Network Analyst detected collapsed UPF activity during calls and system-wide IMS signaling spikes.
>     2. Latency probes from P-CSCF to UPF and I-CSCF returned <1ms latency, exonerating the P-CSCF network interface.
>     3. Latency probes from P-CSCF to RTPEngine revealed a persistent 100ms delay.
>     4. Latency probes from RTPEngine to both UPF and P-CSCF confirmed the 100ms delay originates entirely at RTPEngine.
>     5. UPF and P-CSCF internal processing metrics confirmed healthy, disproving alternative component faults.
>     6. RTPEngine confirmed as the sole root cause of the incident.
> - **root_cause**: The RTPEngine network interface is experiencing a 100ms path latency, which collapses downstream media at UPF and inflates system-wide signaling retries. (primary_suspect_nf: `rtpengine`)
> - **affected_components**:
>     - `?`: ?
> - **recommendation**: Investigate kernel-level network latency or traffic control limits on the RTPEngine interface.
> - **confidence**: medium
> - **verdict_kind**: confirmed
> - **explanation**: The outage is driven by a ~100ms network latency originating at RTPEngine, which stalls IMS call setups and induces cascading failures across the stack. Triangulation via measure_rtt probes provided definitive evidence: latency from P-CSCF to RTPEngine measured ~100ms, while P-CSCF to UPF and I-CSCF showed <1ms, clearly exonerating P-CSCF. Probes originating from RTPEngine to independent destinations identically showed 100ms delays, isolating the fault strictly to RTPEngine's network interface. Alternative hypotheses pointing to UPF processing failures or P-CSCF stalls were successfully disproven by healthy internal script execution times and symmetric packet rates on those components.
> 
> [Confidence cap applied: emitted 'high' downgraded to 'medium' because evidence-strength is MODERATE (verdict h1: 2/3 CONSISTENT, 0 CONTRADICTS, 1 AMBIGUOUS). The confidence claim was deterministically corrected to match the underlying probe evidence; the diagnosed NF stands.]

### Scoring Breakdown

**Overall score: 75%**

**Scorer assessment:** The agent successfully diagnosed the RTPEngine latency but mischaracterized the severity and had formatting issues in the affected components list.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | Yes | The agent correctly identified the 100ms network latency originating at RTPEngine as the root cause. |
| Component overlap | 50% | RTPEngine was identified as the primary suspect, but the affected_components list was malformed. |
| Severity correct | No | The agent classified the latency degradation as a complete media and signaling outage. |
| Fault type identified | Yes | The agent correctly identified the fault type as network latency. |
| Layer accuracy | Yes | No layer status information was provided, so no misattribution was detected. |
| Confidence calibrated | Yes | Medium confidence is appropriate given the diagnostic evidence and probe results. |

**Ranking position:** #1 — RTPEngine was identified as the single primary root cause.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 628,423 |
| Output tokens | 10,829 |
| Thinking tokens | 38,016 |
| **Total tokens** | **677,268** |

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
| NetworkAnalystAgent | 258,774 | 10 | 7 |
| Phase 3 NetworkAnalyst__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 18,090 | 0 | 1 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 18,779 | 0 | 1 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| InvestigatorAgent_h1 | 58,425 | 4 | 3 |
| InvestigatorAgent_h1 | 60,808 | 4 | 3 |
| InvestigatorAgent_h1__reconciliation | 0 | 0 | 0 |
| InvestigatorAgent_h2 | 35,099 | 3 | 2 |
| InvestigatorAgent_h2 | 35,142 | 3 | 2 |
| InvestigatorAgent_h2__reconciliation | 0 | 0 | 0 |
| InvestigatorAgent_h3 | 86,397 | 5 | 4 |
| InvestigatorAgent_h3 | 89,279 | 5 | 4 |
| InvestigatorAgent_h3__reconciliation | 0 | 0 | 0 |
| Phase5FanOutAudit | 0 | 0 | 0 |
| Phase6.5CandidatePool | 0 | 0 | 0 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 16,475 | 0 | 1 |
| Phase 7 Synthesis__guardrail | 0 | 0 | 0 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 537.7s
