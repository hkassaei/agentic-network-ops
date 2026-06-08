# Episode Report: PyHSS Clock Skew (Observability)

**Agent:** v7  
**Episode ID:** ep_20260606_025230_pyhss_clock_skew_(observabilit  
**Date:** 2026-06-06T02:52:31.783975+00:00  
**Duration:** 945.9s  

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

- **Propagation window:** 127s (ObservationTrafficAgent drove traffic for this window; verifier added wait=0s on top)
- **Nodes with significant deltas:** 5
- **Nodes with any drift:** 5

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 37.44 (per-bucket threshold: 26.31, context bucket (0, 1), trained on 323 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following metrics deviate from their learned-healthy baseline. Treat each as a semantic observation (meaning + numbers), not a number alone — the KB's interpretation is the authoritative reading.

- **`normalized.icscf.core:rcv_requests_invite_per_ue`** (SIP INVITE rate per UE at I-CSCF) — current **0.02 requests_per_second** vs learned baseline **0.00 requests_per_second** (MEDIUM, spike)
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

- **`normalized.upf.gtp_indatapktn3upf_per_ue`** (GTP-U uplink rate per UE (N3)) — current **3.31 packets_per_second** vs learned baseline **1.45 packets_per_second** (MEDIUM, spike)
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

- **`normalized.upf.gtp_outdatapktn3upf_per_ue`** (GTP-U downlink rate per UE (N3)) — current **3.19 packets_per_second** vs learned baseline **1.45 packets_per_second** (MEDIUM, spike)
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

- **`normalized.icscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at I-CSCF) — current **0.03 requests_per_second** vs learned baseline **0.06 requests_per_second** (LOW, shift)
    - **What it measures:** Health of the P-CSCF → I-CSCF forwarding path (Mw interface). When
this drops to zero while P-CSCF REGISTER rate is still non-zero,
it's the SIGNATURE of an IMS partition between P-CSCF and I-CSCF.
    - **Shift means:** Forwarding issue on the Mw interface, or P-CSCF stopped forwarding.
    - **Healthy typical range:** 0–0.5 requests_per_second
    - **Healthy invariant:** Per-UE rate. Should closely track ims.pcscf.rcv_requests_register_per_ue.

- **`normalized.pcscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at P-CSCF) — current **0.03 requests_per_second** vs learned baseline **0.06 requests_per_second** (LOW, shift)
    - **What it measures:** How actively UEs are refreshing their IMS registrations with the
P-CSCF. REGISTERs arrive periodically (re-registration timer) plus
at attach. Sustained zero means UEs cannot reach P-CSCF OR the
UE-to-network SIP path is broken.
    - **Shift means:** Fewer REGISTERs than expected — UE connectivity or P-CSCF reachability issue.
    - **Healthy typical range:** 0–0.5 requests_per_second
    - **Healthy invariant:** Per-UE rate — same value at any deployment scale.

- **`normalized.scscf.cdp_replies_per_ue`** (S-CSCF CDP Diameter replies per UE) — current **0.03 replies_per_second_per_ue** vs learned baseline **0.06 replies_per_second_per_ue** (LOW, shift)
    - **What it measures:** Active S-CSCF Diameter traffic with HSS. Near-zero when registrations idle OR HSS partition.
    - **Shift means:** Diameter peering loss with HSS.
    - **Healthy typical range:** 0–1 replies_per_second_per_ue
    - **Healthy invariant:** Per-UE rate; varies with registration/auth load.

- **`normalized.scscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at S-CSCF) — current **0.03 requests_per_second** vs learned baseline **0.06 requests_per_second** (LOW, shift)
    - **What it measures:** Health of the I-CSCF → S-CSCF forwarding path. Drop to zero while
I-CSCF is receiving REGISTERs = S-CSCF-side issue (crashed, or
I-CSCF → S-CSCF path broken).
    - **Shift means:** I-CSCF not forwarding or S-CSCF not receiving.
    - **Healthy typical range:** 0–0.5 requests_per_second
    - **Healthy invariant:** Per-UE rate. Tracks icscf.register rate.

- **`normalized.icscf.cdp_replies_per_ue`** (I-CSCF Diameter reply rate per UE) — current **0.03 replies_per_second_per_ue** vs learned baseline **0.03 replies_per_second_per_ue** (LOW, shift)
    - **What it measures:** Liveness of the I-CSCF↔HSS Cx path. Drops to 0 when HSS is unreachable OR when no signaling is occurring at the I-CSCF (idle or upstream P-CSCF partitioned).
    - **Shift means:** I-CSCF is actively conversing with HSS — healthy.
    - **Healthy typical range:** 0–1 replies_per_second_per_ue


## Symptom Classifier (Phase 0.5)

**Label:** `mixed`  
**Flag counts:** transport=2, application=0, ambiguous=8

### Transport-bucket flags (2)

| Metric | Direction | Score | KB-driven reason |
|---|---|---:|---|
| `normalized.upf.gtp_indatapktn3upf_per_ue` | spike | 4.59 | KB-labeled transport: core.upf.gtp_indatapktn3upf_per_ue (spike, score=4.59) |
| `normalized.upf.gtp_outdatapktn3upf_per_ue` | spike | 4.59 | KB-labeled transport: core.upf.gtp_outdatapktn3upf_per_ue (spike, score=4.59) |

### Ambiguous-bucket flags (8)

| Metric | Direction | Score | KB-driven reason |
|---|---|---:|---|
| `normalized.icscf.core:rcv_requests_invite_per_ue` | spike | 4.59 | KB-labeled mixed: ims.icscf.rcv_requests_invite_per_ue (spike, score=4.59) |
| `normalized.pcscf.core:rcv_requests_invite_per_ue` | spike | 4.59 | KB-labeled mixed: ims.pcscf.rcv_requests_invite_per_ue (spike, score=4.59) |
| `normalized.scscf.core:rcv_requests_invite_per_ue` | spike | 4.59 | KB-labeled mixed: ims.scscf.rcv_requests_invite_per_ue (spike, score=4.59) |
| `normalized.icscf.core:rcv_requests_register_per_ue` | shift | 2.99 | KB-labeled mixed: ims.icscf.rcv_requests_register_per_ue (shift, score=2.99) |
| `normalized.pcscf.core:rcv_requests_register_per_ue` | shift | 2.99 | KB-labeled mixed: ims.pcscf.rcv_requests_register_per_ue (shift, score=2.99) |
| `normalized.scscf.cdp_replies_per_ue` | shift | 2.99 | KB-labeled mixed: ims.scscf.cdp_replies_per_ue (shift, score=2.99) |
| `normalized.scscf.core:rcv_requests_register_per_ue` | shift | 2.99 | KB-labeled mixed: ims.scscf.rcv_requests_register_per_ue (shift, score=2.99) |
| `normalized.icscf.cdp_replies_per_ue` | shift | 2.52 | KB-labeled mixed: ims.icscf.cdp_replies_per_ue (shift, score=2.52) |

**Rationale:**

```
label=mixed. 2 transport-layer signal(s) plus 8 ambiguous signal(s) clustering on a different NF-owner layer (transport on core; ambiguous cluster on ims (100%)). Treated as compound: walker plus application-layer pipeline both run; Synthesis merges into a single (potentially multi-root-cause) verdict. See ADR multi_fault_orchestration.md.

Transport signals: normalized.upf.gtp_indatapktn3upf_per_ue (spike, score=4.59) — KB-labeled transport: core.upf.gtp_indatapktn3upf_per_ue (spike, score=4.59); normalized.upf.gtp_outdatapktn3upf_per_ue (spike, score=4.59) — KB-labeled transport: core.upf.gtp_outdatapktn3upf_per_ue (spike, score=4.59)

Ambiguous signals: normalized.icscf.core:rcv_requests_invite_per_ue (spike, score=4.59) — KB-labeled mixed: ims.icscf.rcv_requests_invite_per_ue (spike, score=4.59); normalized.pcscf.core:rcv_requests_invite_per_ue (spike, score=4.59) — KB-labeled mixed: ims.pcscf.rcv_requests_invite_per_ue (spike, score=4.59); normalized.scscf.core:rcv_requests_invite_per_ue (spike, score=4.59) — KB-labeled mixed: ims.scscf.rcv_requests_invite_per_ue (spike, score=4.59); normalized.icscf.core:rcv_requests_register_per_ue (shift, score=2.99) — KB-labeled mixed: ims.icscf.rcv_requests_register_per_ue (shift, score=2.99); normalized.pcscf.core:rcv_requests_register_per_ue (shift, score=2.99) — KB-labeled mixed: ims.pcscf.rcv_requests_register_per_ue (shift, score=2.99) [+3 more]
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
Primary flow `data_pdu_session_user_traffic` (score=12, 11 hops); walker probes 5 candidate flows in parallel. Load-bearing components: ['icscf', 'pcscf', 'scscf', 'upf']. Other candidate flows considered: vonr_media=12, ims_registration=8, vonr_call_teardown=8, vonr_call_setup=8. Hard cap (5 flows) truncated 3 additional candidates below the cut. Soft cap exceeded (5 > 3): noisy load-bearing set — inspect screener flag bucketing if this recurs.
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

> 🔪 **Hard cap (5 flows) truncated 3 additional candidate(s)** below the cut: `diameter_cx_authentication` (4), `pdu_session_establishment` (2), `ue_deregistration` (2). These scored above zero but ranked beyond the top 5 by the prioritizer; not walked.

### Localized Synthesis

*Walker found no hop with attribution. Phase 0.6 returned None and the orchestrator fell through to the application-layer pipeline (Phases 1-7) below — the diagnosis you see in `Agent Diagnosis` came from that fallback path, not from Phase 0.6.*

## Event Aggregation (Phase 1)

No events fired during this episode. Either no metric KB triggers matched, or the episode encountered no meaningful state transitions.

## Correlation Analysis (Phase 2)

No events fired — correlation engine had nothing to work with.

## RAG & Operational Lessons (Phase 2.5)

### RAG retrieval — prior similar episodes

**Status:** `hits` — hits=5, top_sim=0.87, top_case=v6/ep_20260429_162423_data_plane_degradation
**Index:** `/home/ehoskas/agentic-network-ops/rag_index`  **Corpus size:** 102 cases
**Classifier label used in retrieval:** `mixed`
**Retrieval params:** k=5, min_similarity=0.4
**Hits (5):**

| Rank | Sim | Case ID | Scenario | Ground truth | Primary suspect | Score |
|---:|---:|---|---|---|---|---:|
| 0 | 87% | `v6/ep_20260429_162423_data_plane_degradation` | Data Plane Degradation | `upf` | `upf` | 85% |
| 1 | 83% | `v7/ep_20260527_205700_mongodb_gone` | MongoDB Gone | `mongo` | `mongo` | 90% |
| 2 | 83% | `v7/ep_20260528_014756_mongodb_gone` | MongoDB Gone | `mongo` | `mongo` | 100% |
| 3 | 83% | `v7/ep_20260526_184459_mongodb_gone` | MongoDB Gone | `mongo` | `mongo` | 100% |
| 4 | 82% | `v7/ep_20260526_022026_p_cscf_latency` | P-CSCF Latency | `pcscf` | `pcscf` | 100% |

*Rendered block injected into the NA prompt's `{prior_similar_episodes}` placeholder: 4761 chars. Source paths are inlined in the block so the EvidenceValidator can audit any case the NA cites.*

### Operational lessons — hand-authored rules corpus

**Status:** `injected` — lessons=16, chars=15678
**Path:** `/home/ehoskas/agentic-network-ops/agentic_ops_common/rag/lessons.yaml`  **Count:** 16  **Block size:** 15678 chars
**Injected lesson IDs:** `L01`, `L02`, `L03`, `L04`, `L05`, `L06`, `L07`, `L08`, `L09`, `L10`, `L11`, `L12`, `L13`, `L14`, `L15`, `L16`

### NA citations of the injected content

**No verbatim citations.** The NA's output text did not reference any retrieved case_id or any injected lesson_id verbatim. This does NOT prove the NA ignored the injected content — the model may have absorbed the patterns implicitly — but it does mean no audit trail links the NA's reasoning back to a specific case or lesson.

## Network Analysis (Phase 3)

**Summary:** Screener flags show a 50% shift down in IMS registration metrics across all CSCFs without SIP errors, combined with spikes in INVITE and UPF GTP rates. The IMS layer components are demoted as downstream reporters; the fault originates upstream on the data-plane signaling path (UPF or gNB), preventing one UE's registration while the other actively but unsuccessfully attempts to place calls.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | No DB or DNS error signatures observed. |
| **ran** | 🟡 YELLOW | Control plane is healthy, but user-plane signaling might be dropping. |
| **core** | 🔴 RED | Primary suspect layer for the data-plane isolation of the unregistered UE. |
| **ims** | 🟡 YELLOW | Demoted as a downstream reporter. The CSCFs and HSS are correctly processing the halved traffic volume. |

**RAN evidence:**
- ran_ue = 2, indicating UEs are successfully attached at the control plane.
- A fault at gNB N3/Uu could explain the silent isolation of one UE's SIP signaling.

**CORE evidence:**
- UPF GTP-U in and out rates spiked.
- UPF serves as the signaling data-plane anchor; dropping packets here perfectly explains the downstream IMS registration shifts.

**IMS evidence:**
- All CSCFs show a 50% drop in REGISTER rates and CDP replies.
- INVITE rates spiked across P-CSCF, I-CSCF, and S-CSCF.
- No SIP error ratio spikes or Diameter timeouts observed.

**Ranked hypotheses:**

- **`h1`** (fit=0.90, nf=upf, specificity=specific):
    - **Statement:** upf is the source of the CSCF register-rate shifts and the INVITE and GTP spikes. A fault at the UPF is dropping N3 data-plane packets for one of the UEs, isolating its SIP signaling path and causing subsequent VoNR call setups to fail because the callee is unregistered.
    - **Falsification probes:**
        - Execute a kernel-counter probe on UPF's N3 interface (e.g., `tc -s qdisc show`) to check for dropped packets.
        - Run `measure_rtt` between `upf` and `rtpengine` to rule out container network loss on the UPF segment.
- **`h2`** (fit=0.80, nf=nr_gnb, specificity=specific):
    - **Statement:** nr_gnb is the source of the CSCF register-rate shifts. A fault at the gNB is dropping SIP signaling for one UE on the Uu or N3 interface, causing its IMS registration to drop while its AMF control-plane state remains active.
    - **Falsification probes:**
        - Check gNB logs or kernel drop counters on its N3 egress interface.
        - Run a targeted test of the Uu radio interface to confirm bidirectional signaling capability for both UEs.
- **`h3`** (fit=0.50, nf=pcscf, specificity=moderate):
    - **Statement:** pcscf is the source of the CSCF register-rate shifts. A fault at the P-CSCF is silently dropping incoming REGISTER requests from one UE without generating SIP errors, leading to partial IMS registration failure.
    - **Falsification probes:**
        - Check P-CSCF Kamailio logs for parse errors or silent drops of incoming REGISTER requests.
        - Compare the rate of REGISTER packets arriving at P-CSCF's network interface against the application-level `rcv_requests_register` metric.


## Falsification Plans (Phase 4)

**3 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `upf`)

**Hypothesis:** upf is the source of the CSCF register-rate shifts and the INVITE and GTP spikes. A fault at the UPF is dropping N3 data-plane packets for one of the UEs, isolating its SIP signaling path and causing subsequent VoNR call setups to fail because the callee is unregistered.

**Probes (3):**
1. **`get_dp_quality_gauges`** — window_seconds=120
    - *Expected if hypothesis holds:* A directional drop or zero in UPF in/out pps, or elevated rtpengine.loss_ratio without errors_per_second.
    - *Falsifying observation:* The probe's reading is inconsistent with upf being the source (e.g. upf in/out pps match active traffic expectations and rtpengine.loss_ratio is ~0).
2. **`measure_rtt`** — amf -> upf_ip
    - *Expected if hypothesis holds:* Packet loss or elevated latency observed on the path.
    - *Falsifying observation:* 0% packet loss and stable latency.
3. **`measure_rtt`** — pcscf -> upf_ip
    - *Expected if hypothesis holds:* Packet loss or elevated latency observed on this path as well, confirming the deviation belongs to upf.
    - *Falsifying observation:* 0% packet loss and stable latency, indicating the deviation belongs to one of the shared conflates_with elements from the partner probe.

*Notes:* Uses KB-authored get_dp_quality_gauges for data plane metrics and cross-verifies UPF unreachability via partner compositional probes.

### Plan for `h2` (target: `nr_gnb`)

**Hypothesis:** nr_gnb is the source of the CSCF register-rate shifts. A fault at the gNB is dropping SIP signaling for one UE on the Uu or N3 interface, causing its IMS registration to drop while its AMF control-plane state remains active.

**Probes (3):**
1. **`measure_rtt`** — amf -> nr_gnb_ip
    - *Expected if hypothesis holds:* 100% packet loss or unreachability.
    - *Falsifying observation:* 0% packet loss and stable latency.
2. **`measure_rtt`** — amf -> upf_ip
    - *Expected if hypothesis holds:* 0% packet loss and stable latency, confirming the loss seen in the partner probe is localized to nr_gnb.
    - *Falsifying observation:* Packet loss observed on this path as well, indicating the deviation belongs to one of the shared conflates_with elements.
3. **`get_network_status`** — Check if nr_gnb container is running
    - *Expected if hypothesis holds:* nr_gnb container status is Exited or Down.
    - *Falsifying observation:* nr_gnb container status is Up.

*Notes:* nr_gnb emits no metrics; probing focuses on network unreachability from AMF and container state, paired with a disambiguation ping to upf.

### Plan for `h3` (target: `pcscf`)

**Hypothesis:** pcscf is the source of the CSCF register-rate shifts. A fault at the P-CSCF is silently dropping incoming REGISTER requests from one UE without generating SIP errors, leading to partial IMS registration failure.

**Probes (3):**
1. **`get_diagnostic_metrics`** — pcscf metrics: avg_register_time_ms and rcv_requests_register_per_ue
    - *Expected if hypothesis holds:* avg_register_time_ms is 0 while rcv_requests_register_per_ue is advancing.
    - *Falsifying observation:* The probe's reading is inconsistent with pcscf being the source (e.g. the metrics stay at their healthy baseline).
2. **`get_diagnostic_metrics`** — icscf metrics: rcv_requests_register_per_ue
    - *Expected if hypothesis holds:* Rate is zero or significantly dropped.
    - *Falsifying observation:* Rate is normal and matches the expected per-UE baseline.
3. **`run_kamcmd`** — pcscf -> stats.get_statistics ims_usrloc_pcscf:
    - *Expected if hypothesis holds:* registered_contacts is less than 2.
    - *Falsifying observation:* registered_contacts is 2 or higher.

*Notes:* Uses KB candidates for checking SIP stalling signatures directly on pcscf along with downstream impact validation at icscf.


## Parallel Investigators (Phase 5)

**4 sub-Investigator verdict(s):** **3 DISPROVEN**, **1 INCONCLUSIVE**

### `h1` — ❌ **DISPROVEN**

**Hypothesis:** upf is the source of the CSCF register-rate shifts and the INVITE and GTP spikes. A fault at the UPF is dropping N3 data-plane packets for one of the UEs, isolating its SIP signaling path and causing subsequent VoNR call setups to fail because the callee is unregistered.

**Reasoning:** [Multi-shot consensus — both shots returned DISPROVEN.]

Shot 1: The hypothesis claims that the UPF is dropping N3 data-plane packets, isolating a UE's SIP signaling. This is contradicted by data plane metrics, which show RTPEngine reporting 0.00 packet loss and UPF processing expected, stable throughput (~4 pps in/out) with 4 active sessions. Furthermore, transport-layer network probes from both AMF and P-CSCF to the UPF show 0% packet loss and normal latency (<0.1ms), ruling out any container unreachability or network packet loss at the UPF.

Shot 2: Data-plane gauges show UPF processing packets normally (in: 4.3 pps, out: 4.1 pps) with RTPEngine reporting 0.00 recent packet loss, directly contradicting the claim of N3 packet drops at the UPF. Furthermore, transport probes from both AMF and P-CSCF to the UPF returned 0% packet loss and healthy <1ms latency, proving the UPF network interfaces are fully reachable and not dropping packets.

**Probes executed (3):**
- **Check data plane quality metrics for UPF throughput drops or RTPEngine packet loss.** ✗ CONTRADICTS
    - *Tool:* `get_dp_quality_gauges(window_seconds=120, at_time_ts=1780714466.1694305)`
    - *Observation:* [EVIDENCE: get_dp_quality_gauges(window_seconds=120, at_time_ts=1780714466.1694305) -> "RTPEngine: ... loss (recent)  : 0.00 ... UPF: in  packets/sec: 4.3, out packets/sec: 4.1"]
    - *Comment:* Data plane metrics show zero packet loss at RTPEngine and matching, healthy packet rates for UPF ingress and egress, directly contradicting the claim that UPF is dropping N3 packets.
- **Measure transport-layer RTT and packet loss from AMF to UPF.** ✗ CONTRADICTS
    - *Tool:* `measure_rtt(container="amf", target="upf")`
    - *Observation:* [EVIDENCE: measure_rtt("amf", "upf") -> "66 packets transmitted, 66 received, 0% packet loss, time 6586ms, rtt min/avg/max/mdev = 0.040/0.092/0.260/0.036 ms"]
    - *Comment:* The transport layer path from AMF to UPF exhibits 0% packet loss and normal sub-millisecond latency, proving UPF is healthy and reachable.
- **Measure transport-layer RTT and packet loss from P-CSCF to UPF to confirm the deviation belongs to UPF.** ✗ CONTRADICTS
    - *Tool:* `measure_rtt(container="pcscf", target="upf")`
    - *Observation:* [EVIDENCE: measure_rtt("pcscf", "upf") -> "66 packets transmitted, 66 received, 0% packet loss, time 6601ms, rtt min/avg/max/mdev = 0.049/0.090/0.159/0.022 ms"]
    - *Comment:* The P-CSCF to UPF path also shows 0% loss and nominal latency, confirming the lack of faults on the UPF network segment.

**Alternative suspects:** nr_gnb, pcscf

### `h2` — ❓ **INCONCLUSIVE**

**Hypothesis:** nr_gnb is the source of the CSCF register-rate shifts. A fault at the gNB is dropping SIP signaling for one UE on the Uu or N3 interface, causing its IMS registration to drop while its AMF control-plane state remains active.

**Reasoning:** The required falsification probes targeting nr_gnb could not be executed because the component is not tracked by the available diagnostic tools. The measure_rtt probe rejected nr_gnb as an unknown target, and get_network_status does not include it in its tracked container list. While a disambiguation ping from AMF to UPF succeeded, and AMF metrics (gnb=1, ran_ue=2) confirm the control-plane state remains active, this evidence is entirely consistent with the hypothesis of a localized user-plane (Uu/N3) drop at the gNB. Because no direct reachability or state check against nr_gnb could be performed, the hypothesis cannot be definitively confirmed or falsified.

**Probes executed (3):**
- **amf -> nr_gnb_ip** ~ AMBIGUOUS
    - *Tool:* `measure_rtt("amf", "nr_gnb")`
    - *Observation:* [EVIDENCE: measure_rtt("amf", "nr_gnb") -> "Unknown target container 'nr_gnb'"]
    - *Comment:* The measure_rtt tool restricts targets to a predefined list of dockerized containers that excludes nr_gnb, making the primary reachability test impossible.
- **amf -> upf_ip** ~ AMBIGUOUS
    - *Tool:* `measure_rtt("amf", "upf")`
    - *Observation:* [EVIDENCE: measure_rtt("amf", "upf") -> "0% packet loss"]
    - *Comment:* The disambiguation ping verifies the AMF-to-UPF segment is healthy. However, without a successful baseline ping to nr_gnb to compare against, this cannot localize or rule out a fault at the gNB.
- **Check if nr_gnb container is running** ~ AMBIGUOUS
    - *Tool:* `get_network_status()`
    - *Observation:* [EVIDENCE: get_network_status() -> "down_or_absent: []" with nr_gnb missing entirely from the container list]
    - *Comment:* The get_network_status tool only monitors core and IMS layer Docker containers; it is structurally blind to nr_gnb, preventing any container-level state verification.

### `h3` — ❌ **DISPROVEN**

**Hypothesis:** pcscf is the source of the CSCF register-rate shifts. A fault at the P-CSCF is silently dropping incoming REGISTER requests from one UE without generating SIP errors, leading to partial IMS registration failure.

**Reasoning:** [Multi-shot consensus — both shots returned DISPROVEN.]

Shot 1: The evidence shows P-CSCF is successfully forwarding 100% of the REGISTER requests it receives. The incoming REGISTER rate at P-CSCF (0.0308) has halved from its baseline (0.06), and exactly matches the forwarding rate at I-CSCF (0.0308), proving P-CSCF is not dropping requests internally. Additionally, the average register time is healthy (181.9 ms), indicating the requests that do arrive are processed normally. This points to an upstream data-plane starvation issue, not a P-CSCF fault.

Shot 2: P-CSCF is starved of requests from upstream, not silently dropping them internally. During the anomaly window, the incoming REGISTER rate at P-CSCF (`rcv_requests_register_per_ue`) had already halved to 0.0308 (from a normal of 0.06042), indicating the requests from one UE never reached the P-CSCF. Furthermore, the rate of REGISTERs arriving at I-CSCF exactly matches the P-CSCF rate (0.0308), proving P-CSCF successfully forwarded all requests it received without silent drops. Live Kamailio state also confirms both UE contacts remain registered.

**Probes executed (3):**
- **pcscf metrics: avg_register_time_ms and rcv_requests_register_per_ue** ✗ CONTRADICTS
    - *Tool:* `get_diagnostic_metrics(at_time_ts=1780714466.1694305, nfs=["pcscf"])`
    - *Observation:* [EVIDENCE: get_diagnostic_metrics(at_time_ts=1780714466.16943, nfs=["pcscf"]) -> "derived.pcscf_avg_register_time_ms = 181.9 [derived, ms]" and "normalized.pcscf.core:rcv_requests_register_per_ue = 0.0308 [derived, requests_per_second]"]
    - *Comment:* Average register time is normal (181.9 ms), not 0. The incoming REGISTER rate at P-CSCF has dropped to half its baseline, showing starvation rather than internal dropping.
- **icscf metrics: rcv_requests_register_per_ue** ✗ CONTRADICTS
    - *Tool:* `get_diagnostic_metrics(at_time_ts=1780714466.1694305, nfs=["icscf"])`
    - *Observation:* [EVIDENCE: get_diagnostic_metrics(at_time_ts=1780714466.16943, nfs=["icscf"]) -> "normalized.icscf.core:rcv_requests_register_per_ue = 0.0308 [derived, requests_per_second]"]
    - *Comment:* The I-CSCF REGISTER rate exactly matches the P-CSCF incoming rate (both 0.0308). There is no gap between them, confirming P-CSCF is successfully forwarding all arriving requests.
- **pcscf -> stats.get_statistics ims_usrloc_pcscf:** ✗ CONTRADICTS
    - *Tool:* `run_kamcmd(container="pcscf", command="stats.get_statistics ims_usrloc_pcscf:")`
    - *Observation:* [EVIDENCE: run_kamcmd(container="pcscf", command="stats.get_statistics ims_usrloc_pcscf:") -> "ims_usrloc_pcscf:registered_contacts = 2"]
    - *Comment:* Both contacts are still registered in the P-CSCF usrloc database, contrary to the expectation of less than 2.

**Alternative suspects:** upf, nr_gnb

### `h_promoted_nr_gnb` — ❌ **DISPROVEN**

**Hypothesis:** nr_gnb is the source of the anomaly named in the alternative_suspects of the original verdict tree.

**Reasoning:** The falsification plan relied on reachability and liveness checks for nr_gnb. However, nr_gnb is not an explicit container that can be pinged or queried via get_network_status in this environment, making direct pings impossible (tool unavailable). By examining the AMF's diagnostic metrics, it is clear that nr_gnb is fully operational: the AMF shows an active N2 association (gnb=1) and attached UEs (ran_ue=2). Additionally, data plane gauges show active, healthy sessions with 0% packet loss. This strongly contradicts the hypothesis that nr_gnb is down, unreachable, or the source of a network anomaly.

**Probes executed (4):**
- **Check the container status for nr_gnb.** ~ AMBIGUOUS
    - *Tool:* `get_network_status()`
    - *Observation:* [EVIDENCE: get_network_status() -> ""down_or_absent": []"]
    - *Comment:* nr_gnb is not listed as a known container in the network status tool output, making this probe inconclusive for direct liveness.
- **Ping from 'amf' to 'nr_gnb' (using nr_gnb IP).** ~ AMBIGUOUS
    - *Tool:* `measure_rtt("amf", "nr_gnb")`
    - *Observation:* [EVIDENCE: measure_rtt("amf", "nr_gnb") -> "Unknown target container 'nr_gnb'"]
    - *Comment:* Tool rejected the container name 'nr_gnb' as it is not managed in the standard container pool, preventing direct reachability testing from AMF.
- **Ping from 'amf' to 'upf' (using upf IP) as a disambiguation partner.** ~ AMBIGUOUS
    - *Tool:* `measure_rtt("amf", "upf")`
    - *Observation:* [EVIDENCE: measure_rtt("amf", "upf") -> "66 packets transmitted, 66 received, 0% packet loss"]
    - *Comment:* Since the primary probe failed, this one doesn't isolate any fault to nr_gnb, though it shows AMF networking is functioning normally.
- **Check AMF metrics for live N2/RAN connections to evaluate nr_gnb liveness.** ✗ CONTRADICTS
    - *Tool:* `get_diagnostic_metrics(at_time_ts=1780714466.16943, nfs=["amf"])`
    - *Observation:* [EVIDENCE: get_diagnostic_metrics(at_time_ts=1780714466.16943, nfs=["amf"]) -> "gnb = 1 [gauge, count]... ran_ue = 2 [gauge, count]"]
    - *Comment:* The AMF reports an active N2 connection (gnb=1) and attached UEs (ran_ue=2), definitively contradicting the hypothesis that nr_gnb is down or unreachable.


## Evidence Validation (Phase 6)

**Overall verdict:** clean
**Overall confidence:** high

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 6 | 3/3 | clean | high |
| `InvestigatorAgent_h2` | 19 | 3/3 | clean | high |
| `InvestigatorAgent_h3` | 8 | 3/3 | clean | high |
| `InvestigatorAgent_h_promoted_nr_gnb` | 9 | 4/4 | clean | high |


## Ground Truth

**Failure domain:** ims_signaling  
**Protocol impact:** Diameter  
**Affected components:** pyhss  
**Severity:** degraded

## Agent Diagnosis

**Model:** v7-adk/pro=gemini-3.1-pro-preview+flash=gemini-3.5-flash  
**Time to diagnosis:** 812.8s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: The IMS signaling starvation is likely caused by an upstream issue, with nr_gnb being the strongest remaining candidate despite inconclusive direct container checks.
> - **timeline**:
>     1. Screener flagged a 50% shift down in IMS registration metrics across CSCFs without SIP errors.
>     2. UPF GTP rates and INVITE rates showed concurrent spikes.
>     3. Automated diagnostics ruled out data-plane drops at the UPF and internal silent drops at the P-CSCF.
>     4. Re-investigation of nr_gnb confirmed its AMF control-plane state is active but could not directly probe user-plane metrics.
> - **root_cause**: Suspected localized user-plane (Uu/N3) signal drop at nr_gnb causing one UE to lose IMS registration. (primary_suspect_nf: `nr_gnb`)
> - **affected_components**:
>     - `nr_gnb`: Root Cause
>     - `pcscf`: Symptomatic
>     - `upf`: Symptomatic
> - **recommendation**: Manually investigate nr_gnb logs for Uu radio interface or N3 data-plane packet drops causing SIP starvation.
> - **confidence**: low
> - **verdict_kind**: promoted
> - **explanation**: All primary hypotheses were ultimately disproven or inconclusive, but cross-corroboration points to nr_gnb as the most likely source of the fault. Diagnostics confirmed that P-CSCF is starved of incoming REGISTER requests (rate halved to 0.0308) and UPF is successfully routing all traffic it receives (0% loss, ~4pps). While AMF metrics show the gNB is alive and maintaining N2 associations (gnb=1, ran_ue=2), a localized user-plane fault at the gNB would isolate the UE's SIP signaling while keeping the control plane active. Because nr_gnb is not accessible to standard transport probes, this hypothesis could not be definitively tested and requires manual verification.

### Scoring Breakdown

**Overall score: 0%**

**Scorer assessment:** The agent failed the negative-control test, hallucinating an IMS registration/gNB user-plane fault instead of correctly identifying that there was no functional impact.

| Dimension | Weight | Result | Rationale |
|-----------|-------:|--------|-----------|
| Root cause correct | 0.40 | No | The agent diagnosed a localized user-plane signal drop at nr_gnb causing IMS registration loss. The actual simulated failure was a PyHSS clock skew with no functional impact (negative control). The agent failed to identify that there was no functional fault and instead hallucinated a gNB/IMS issue. |
| Component overlap | 0.25 | 0% | Mechanical comparison: ground truth ['pyhss'] vs diagnosis root cause(s) ['nr_gnb']. pyhss=absent (0.0). |
| Severity correct | 0.15 | No | The agent treated the issue as a functional outage/starvation (degraded/down), whereas the actual scenario had no functional impact (purely cosmetic/observability anomaly). |
| Fault type identified | 0.10 | No | The agent identified the fault type as a user-plane signal drop / packet loss, whereas the actual fault was a clock skew / observability anomaly. |
| Confidence calibrated | 0.10 | No | Although the agent stated 'low' confidence, it failed the negative-control test by hallucinating a functional fault (IMS signaling starvation) and promoting a false positive instead of concluding that there was no functional fault. |

**Ranking:** The correct cause (PyHSS clock skew / no functional fault) was not listed in the agent's diagnosis.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 1,110,832 |
| Output tokens | 12,920 |
| Thinking tokens | 67,900 |
| **Total tokens** | **1,191,652** |

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
| NetworkAnalystAgent | 441,972 | 19 | 11 |
| Phase 3 NetworkAnalyst__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 44,117 | 3 | 2 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 21,062 | 0 | 1 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| InvestigatorAgent_h1 | 33,928 | 3 | 2 |
| InvestigatorAgent_h1 | 36,249 | 3 | 2 |
| InvestigatorAgent_h1__reconciliation | 0 | 0 | 0 |
| InvestigatorAgent_h2 | 99,290 | 8 | 5 |
| InvestigatorAgent_h2 | 201,121 | 11 | 10 |
| InvestigatorAgent_h2__reconciliation | 0 | 0 | 0 |
| InvestigatorAgent_h3 | 87,423 | 6 | 4 |
| InvestigatorAgent_h3 | 35,902 | 2 | 2 |
| InvestigatorAgent_h3__reconciliation | 0 | 0 | 0 |
| Phase5FanOutAudit | 0 | 0 | 0 |
| Phase6.5CandidatePool | 0 | 0 | 0 |
| InstructionGeneratorAgent | 15,673 | 0 | 1 |
| Phase 6.5 Reinvestigation IG__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 15,126 | 0 | 1 |
| Phase 6.5 Reinvestigation IG__guardrail | 0 | 0 | 0 |
| Phase 6.5 Reinvestigation IG__guardrail | 0 | 0 | 0 |
| InvestigatorAgent_h_promoted_nr_gnb | 143,739 | 9 | 8 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 16,050 | 0 | 1 |
| Phase 7 Synthesis__guardrail | 0 | 0 | 0 |
| ImpactAssessment | 0 | 0 | 0 |


## Blast Radius & Downstream Impact

The root cause NF nr_gnb has impacted symptomatic network functions icscf, pcscf, scscf, and upf. This has resulted in failing statuses for the following flows: Data PDU Session — User Traffic, IMS Registration, PDU Session Establishment, UE Deregistration, VoNR Call Setup, VoNR Call Teardown, and VoNR Media Path, while the UE Registration flow is at risk.

Currently, the 5G data & registration and VoNR voice calls services are failing.

### Affected Services

- **5G data & registration** — 🔴 failing
- **VoNR voice calls** — 🔴 failing

### Affected Procedures

| Procedure | Service | Status | Evidence |
|---|---|---|---|
| `data_pdu_session_user_traffic` (Data PDU Session — User Traffic) | 5g_core | 🔴 failing | observed degradation on upf along this procedure's path this episode |
| `ims_registration` (IMS Registration) | vonr | 🔴 failing | observed degradation on icscf, pcscf, scscf, upf along this procedure's path this episode |
| `pdu_session_establishment` (PDU Session Establishment) | 5g_core | 🔴 failing | observed degradation on upf along this procedure's path this episode |
| `ue_deregistration` (UE Deregistration) | 5g_core | 🔴 failing | observed degradation on upf along this procedure's path this episode |
| `ue_registration` (UE Registration) | 5g_core | ⚪ at-risk | potential — traverses the diagnosed NF but no degradation signal observed on this procedure this episode |
| `vonr_call_setup` (VoNR Call Setup) | vonr | 🔴 failing | observed degradation on icscf, pcscf, scscf, upf along this procedure's path this episode |
| `vonr_call_teardown` (VoNR Call Teardown) | vonr | 🔴 failing | observed degradation on icscf, pcscf, scscf, upf along this procedure's path this episode |
| `vonr_media` (VoNR Media Path) | vonr | 🔴 failing | observed degradation on upf along this procedure's path this episode |

**Downstream-affected NFs (symptomatic):** `icscf`, `pcscf`, `scscf`, `upf`

## Resolution

**Heal method:** scheduled  
**Recovery time:** 945.9s
