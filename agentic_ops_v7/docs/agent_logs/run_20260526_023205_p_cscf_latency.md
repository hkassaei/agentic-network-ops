# Episode Report: P-CSCF Latency

**Agent:** v7  
**Episode ID:** ep_20260526_022026_p_cscf_latency  
**Date:** 2026-05-26T02:20:28.251574+00:00  
**Duration:** 697.1s  

---

## Scenario

**Category:** network  
**Blast radius:** single_nf  
**Description:** Inject 2000ms latency (with 50ms jitter) on the P-CSCF (SIP edge proxy). SIP transactions will experience severe delays as every message entering and leaving the P-CSCF is delayed, compounding across multiple round-trips in the IMS registration chain. Tests IMS resilience to high latency on the signaling edge.

## Faults Injected

- **network_latency** on `pcscf` — {'delay_ms': 2000, 'jitter_ms': 50}

## Baseline (Pre-Fault)

Stack phase before injection: **ready**
All containers running at baseline.

## Fault Propagation Verification

**Verdict:** ✅ `confirmed`

- **Propagation window:** 138s (ObservationTrafficAgent drove traffic for this window; verifier added wait=0s on top)
- **Nodes with significant deltas:** 3
- **Nodes with any drift:** 5

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 34.85 (per-bucket threshold: 26.31, context bucket (0, 1), trained on 323 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following metrics deviate from their learned-healthy baseline. Treat each as a semantic observation (meaning + numbers), not a number alone — the KB's interpretation is the authoritative reading.

- **`derived.pcscf_sip_error_ratio`** (P-CSCF SIP error response ratio) — current **0.25 ratio** vs learned baseline **0.00 ratio** (MEDIUM, spike)
    - **What it measures:** Proportion of SIP responses that are errors. Zero is the healthy
baseline; any sustained non-zero value means P-CSCF or something
downstream is rejecting requests.
    - **Spike means:** Errors flowing back — downstream CSCFs or HSS rejecting.
    - **Healthy typical range:** 0–0 ratio
    - **Healthy invariant:** Zero in healthy operation.

- **`normalized.icscf.cdp_replies_per_ue`** (I-CSCF Diameter reply rate per UE) — current **0.00 replies_per_second_per_ue** vs learned baseline **0.03 replies_per_second_per_ue** (MEDIUM, drop)
    - **What it measures:** Liveness of the I-CSCF↔HSS Cx path. Drops to 0 when HSS is unreachable OR when no signaling is occurring at the I-CSCF (idle or upstream P-CSCF partitioned).
    - **Drop means:** No Cx replies in the window. Could be healthy idle OR a Cx-path fault.
    - **Healthy typical range:** 0–1 replies_per_second_per_ue

- **`normalized.pcscf.core:rcv_requests_invite_per_ue`** (SIP INVITE rate per UE at P-CSCF) — current **0.04 requests_per_second** vs learned baseline **0.00 requests_per_second** (MEDIUM, spike)
    - **What it measures:** Call attempt rate from registered UEs. Unlike REGISTER (periodic),
INVITEs only fire when UEs place calls. Zero is normal during
quiet periods; nonzero INVITE with zero dialogs is the signature
of call setup failure.
    - **Spike means:** Fewer call attempts.
    - **Healthy typical range:** 0–0.2 requests_per_second
    - **Healthy invariant:** Per-UE rate.

- **`normalized.pcscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at P-CSCF) — current **0.01 requests_per_second** vs learned baseline **0.06 requests_per_second** (MEDIUM, drop)
    - **What it measures:** How actively UEs are refreshing their IMS registrations with the
P-CSCF. REGISTERs arrive periodically (re-registration timer) plus
at attach. Sustained zero means UEs cannot reach P-CSCF OR the
UE-to-network SIP path is broken.
    - **Drop means:** No REGISTERs flowing. Unusual unless UEs are all deregistered.
    - **Healthy typical range:** 0–0.5 requests_per_second
    - **Healthy invariant:** Per-UE rate — same value at any deployment scale.

- **`normalized.scscf.cdp_replies_per_ue`** (S-CSCF CDP Diameter replies per UE) — current **0.01 replies_per_second_per_ue** vs learned baseline **0.06 replies_per_second_per_ue** (MEDIUM, drop)
    - **What it measures:** Active S-CSCF Diameter traffic with HSS. Near-zero when registrations idle OR HSS partition.
    - **Drop means:** No active S-CSCF Diameter exchanges (idle or partitioned).
    - **Healthy typical range:** 0–1 replies_per_second_per_ue
    - **Healthy invariant:** Per-UE rate; varies with registration/auth load.

- **`normalized.scscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at S-CSCF) — current **0.01 requests_per_second** vs learned baseline **0.06 requests_per_second** (MEDIUM, drop)
    - **What it measures:** Health of the I-CSCF → S-CSCF forwarding path. Drop to zero while
I-CSCF is receiving REGISTERs = S-CSCF-side issue (crashed, or
I-CSCF → S-CSCF path broken).
    - **Drop means:** S-CSCF isolated or not running.
    - **Healthy typical range:** 0–0.5 requests_per_second
    - **Healthy invariant:** Per-UE rate. Tracks icscf.register rate.

- **`normalized.upf.gtp_outdatapktn3upf_per_ue`** (GTP-U downlink rate per UE (N3)) — current **0.09 packets_per_second** vs learned baseline **1.45 packets_per_second** (LOW, drop)
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
    - **Drop means:** No traffic leaving UPF toward RAN.
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

- **`normalized.icscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at I-CSCF) — current **0.04 requests_per_second** vs learned baseline **0.06 requests_per_second** (LOW, shift)
    - **What it measures:** Health of the P-CSCF → I-CSCF forwarding path (Mw interface). When
this drops to zero while P-CSCF REGISTER rate is still non-zero,
it's the SIGNATURE of an IMS partition between P-CSCF and I-CSCF.
    - **Shift means:** Forwarding issue on the Mw interface, or P-CSCF stopped forwarding.
    - **Healthy typical range:** 0–0.5 requests_per_second
    - **Healthy invariant:** Per-UE rate. Should closely track ims.pcscf.rcv_requests_register_per_ue.

- **`normalized.upf.gtp_indatapktn3upf_per_ue`** (GTP-U uplink rate per UE (N3)) — current **0.19 packets_per_second** vs learned baseline **1.45 packets_per_second** (LOW, drop)
    - **What it measures:** Health of the uplink user-plane path gNB → UPF. Drops to near-zero
during RAN or N3 outage; stays nonzero during active calls or data
sessions. Decoupled from SIP signaling (signals data plane, not
control plane).
    - **Drop means:** Data plane dead on uplink — UPF receiving no packets from gNB.
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

- **`normalized.smf.bearers_per_ue`** (Active QoS bearers per UE) — current **2.00 count** vs learned baseline **2.48 count** (LOW, shift)
    - **What it measures:** Per-UE count of active QoS bearers. Baseline reflects default
bearers; increments during VoNR calls indicate dedicated voice
bearers being set up. Drop during an active call = dedicated
bearer torn down unexpectedly (voice will fail).
    - **Shift means:** Expected during VoNR calls (1 extra bearer per active call).
    - **Healthy typical range:** 2–3.5 count
    - **Healthy invariant:** At rest: equals configured default bearers (typically 2 per UE).
During active VoNR call: +1 per caller. The per-UE ratio is the
invariant; absolute count scales with UE pool.


## Symptom Classifier (Phase 0.5)

**Label:** `mixed`  
**Flag counts:** transport=2, application=2, ambiguous=6

### Transport-bucket flags (2)

| Metric | Direction | Score | KB-driven reason |
|---|---|---:|---|
| `normalized.upf.gtp_outdatapktn3upf_per_ue` | drop | 3.50 | KB-labeled transport: core.upf.gtp_outdatapktn3upf_per_ue (drop, score=3.50) |
| `normalized.upf.gtp_indatapktn3upf_per_ue` | drop | 0.79 | KB-labeled transport: core.upf.gtp_indatapktn3upf_per_ue (drop, score=0.79) |

### Application-bucket flags (2)

| Metric | Direction | Score | KB-driven reason |
|---|---|---:|---|
| `derived.pcscf_sip_error_ratio` | spike | 4.59 | KB-labeled application: ims.pcscf.sip_error_ratio (spike, score=4.59) |
| `normalized.smf.bearers_per_ue` | shift | 0.01 | KB-labeled application: core.smf.bearers_per_ue (shift, score=0.01) |

### Ambiguous-bucket flags (6)

| Metric | Direction | Score | KB-driven reason |
|---|---|---:|---|
| `normalized.icscf.cdp_replies_per_ue` | drop | 4.59 | KB-labeled mixed: ims.icscf.cdp_replies_per_ue (drop, score=4.59) |
| `normalized.pcscf.core:rcv_requests_invite_per_ue` | spike | 4.59 | KB-labeled mixed: ims.pcscf.rcv_requests_invite_per_ue (spike, score=4.59) |
| `normalized.pcscf.core:rcv_requests_register_per_ue` | drop | 4.59 | KB-labeled mixed: ims.pcscf.rcv_requests_register_per_ue (drop, score=4.59) |
| `normalized.scscf.cdp_replies_per_ue` | drop | 4.59 | KB-labeled mixed: ims.scscf.cdp_replies_per_ue (drop, score=4.59) |
| `normalized.scscf.core:rcv_requests_register_per_ue` | drop | 4.59 | KB-labeled mixed: ims.scscf.rcv_requests_register_per_ue (drop, score=4.59) |
| `normalized.icscf.core:rcv_requests_register_per_ue` | shift | 2.99 | KB-labeled mixed: ims.icscf.rcv_requests_register_per_ue (shift, score=2.99) |

**Rationale:**

```
label=mixed. Both transport-layer (2) and application-layer (2) signals are load-bearing. Path walk runs first; falls through to the application-layer pipeline if the walk produces null localization.

Transport signals: normalized.upf.gtp_outdatapktn3upf_per_ue (drop, score=3.50) — KB-labeled transport: core.upf.gtp_outdatapktn3upf_per_ue (drop, score=3.50); normalized.upf.gtp_indatapktn3upf_per_ue (drop, score=0.79) — KB-labeled transport: core.upf.gtp_indatapktn3upf_per_ue (drop, score=0.79)

Application signals: derived.pcscf_sip_error_ratio (spike, score=4.59) — KB-labeled application: ims.pcscf.sip_error_ratio (spike, score=4.59); normalized.smf.bearers_per_ue (shift, score=0.01) — KB-labeled application: core.smf.bearers_per_ue (shift, score=0.01)

Ambiguous signals: normalized.icscf.cdp_replies_per_ue (drop, score=4.59) — KB-labeled mixed: ims.icscf.cdp_replies_per_ue (drop, score=4.59); normalized.pcscf.core:rcv_requests_invite_per_ue (spike, score=4.59) — KB-labeled mixed: ims.pcscf.rcv_requests_invite_per_ue (spike, score=4.59); normalized.pcscf.core:rcv_requests_register_per_ue (drop, score=4.59) — KB-labeled mixed: ims.pcscf.rcv_requests_register_per_ue (drop, score=4.59); normalized.scscf.cdp_replies_per_ue (drop, score=4.59) — KB-labeled mixed: ims.scscf.cdp_replies_per_ue (drop, score=4.59); normalized.scscf.core:rcv_requests_register_per_ue (drop, score=4.59) — KB-labeled mixed: ims.scscf.rcv_requests_register_per_ue (drop, score=4.59) [+1 more]
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
Primary flow `data_pdu_session_user_traffic` (score=12, 11 hops); walker probes 5 candidate flows in parallel. Load-bearing components: ['icscf', 'pcscf', 'scscf', 'smf', 'upf']. Other candidate flows considered: vonr_media=12, ims_registration=8, vonr_call_teardown=8, vonr_call_setup=8. Hard cap (5 flows) truncated 3 additional candidates below the cut. Soft cap exceeded (5 > 3): noisy load-bearing set — inspect screener flag bucketing if this recurs.
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
| 12 | 🎯 `pcscf` | container | `eth0` | `latency_at_hop` | `qdisc_netem_delay`: delay 2000.0 ms |
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
| 32 | `pcscf` | container | `eth0` | `latency_at_hop` | `qdisc_netem_delay`: delay 2000.0 ms |
| 33 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 34 | `e2e_ue1` | container | `eth0` | `clean` | _clean_ |
| 35 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 36 | `pcscf` | container | `eth0` | `latency_at_hop` | `qdisc_netem_delay`: delay 2000.0 ms |
| 37 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 38 | `scp` | container | `eth0` | `clean` | _clean_ |
| 39 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 40 | `pcf` | container | `eth0` | `clean` | _clean_ |

### Prioritized Candidates Walked In Parallel

The walker probed 5 candidate flows in parallel. The primary outcome (above) is `ims_registration`; the others are listed here so the deterministic disambiguation is fully auditable.

| Flow | Walker outcome | First attributed hop |
|---|---|---|
| `data_pdu_session_user_traffic` | ⚠️ null | — |
| `vonr_media` | ⚠️ null | — |
| `vonr_call_teardown` | ✅ localized | `pcscf[eth0]` |
| `vonr_call_setup` | ✅ localized | `pcscf[eth0]` |

> ⚠️ **Soft cap exceeded** — walker probed 5 flows (soft cap = 3). Signals a noisy load-bearing set; inspect screener flag bucketing if this recurs.

> 🔪 **Hard cap (5 flows) truncated 3 additional candidate(s)** below the cut: `diameter_cx_authentication` (4), `pdu_session_establishment` (4), `ue_deregistration` (4). These scored above zero but ranked beyond the top 5 by the prioritizer; not walked.

### Localized Synthesis

**Verdict:** `localized`  
**Primary suspect NF:** `pcscf`  
**Confidence:** high

**Summary:** Transport-layer fault localized to pcscf[eth0]: qdisc_netem_delay reports 2000.0 ms of delay.

**Recommendation:** Inspect tc qdisc on pcscf: `docker exec pcscf tc -s qdisc show dev eth0`


## Event Aggregation (Phase 1)

No events fired during this episode. Either no metric KB triggers matched, or the episode encountered no meaningful state transitions.

## Correlation Analysis (Phase 2)

No events fired — correlation engine had nothing to work with.

## RAG & Operational Lessons (Phase 2.5)

### RAG retrieval — prior similar episodes

**Status:** `hits` — hits=5, top_sim=0.95, top_case=v6/ep_20260430_013408_p_cscf_latency
**Index:** `/home/ehoskas/agentic-network-ops/rag_index`  **Corpus size:** 102 cases
**Classifier label used in retrieval:** `mixed`
**Retrieval params:** k=5, min_similarity=0.4
**Hits (5):**

| Rank | Sim | Case ID | Scenario | Ground truth | Primary suspect | Score |
|---:|---:|---|---|---|---|---:|
| 0 | 95% | `v6/ep_20260430_013408_p_cscf_latency` | P-CSCF Latency | `pcscf` | `pcscf` | 100% |
| 1 | 93% | `v6/ep_20260429_160912_s_cscf_crash` | S-CSCF Crash | `scscf` | `scscf` | 100% |
| 2 | 93% | `v6/ep_20260501_212815_mongodb_gone` | MongoDB Gone | `mongo` | `mongo` | 100% |
| 3 | 89% | `v7/ep_20260510_184035_p_cscf_packet_loss` | P-CSCF Packet Loss | `pcscf` | `pcscf` | 100% |
| 4 | 84% | `v7/ep_20260510_194005_dns_failure` | DNS Failure | `dns` | `dns` | 85% |

*Rendered block injected into the NA prompt's `{prior_similar_episodes}` placeholder: 4646 chars. Source paths are inlined in the block so the EvidenceValidator can audit any case the NA cites.*

### Operational lessons — hand-authored rules corpus

**Status:** `injected` — lessons=16, chars=15678
**Path:** `/home/ehoskas/agentic-network-ops/agentic_ops_common/rag/lessons.yaml`  **Count:** 16  **Block size:** 15678 chars
**Injected lesson IDs:** `L01`, `L02`, `L03`, `L04`, `L05`, `L06`, `L07`, `L08`, `L09`, `L10`, `L11`, `L12`, `L13`, `L14`, `L15`, `L16`

### NA citations of the injected content

**No verbatim citations.** The NA's output text did not reference any retrieved case_id or any injected lesson_id verbatim. This does NOT prove the NA ignored the injected content — the model may have absorbed the patterns implicitly — but it does mean no audit trail links the NA's reasoning back to a specific case or lesson.

## Network Analysis (Phase 3)

**Summary:** P-CSCF is the primary suspect due to observed 2000ms network latency on all its outbound interfaces, which causes SIP transaction timeouts and fully explains the downstream signaling drops at I-CSCF and S-CSCF, as well as the consequent data plane starvation observed as secondary symptoms at UPF and SMF.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | No signs of infrastructure failure. |
| **ran** | 🟢 GREEN | RAN is operating nominally. |
| **core** | 🟢 GREEN | Data plane metrics are degraded but these are downstream symptoms of the IMS signaling failures. |
| **ims** | 🔴 RED | P-CSCF network latency is breaking the entire IMS registration and call setup signaling chain. |

**IMS evidence:**
- P-CSCF SIP error ratio spiked to 0.25.
- 2000ms network latency measured from P-CSCF to all internal interfaces.
- I-CSCF and S-CSCF see severe drops in incoming requests and Diameter replies.

**Ranked hypotheses:**

- **`h1`** (fit=0.95, nf=pcscf, specificity=specific):
    - **Statement:** P-CSCF is the source of the elevated SIP error ratio and downstream signaling drops, evidenced by a measured 2000ms network latency on all its outbound interfaces.
    - **Falsification probes:**
        - measure_rtt from UPF to PCF to confirm the latency is isolated strictly to the P-CSCF network stack
        - Check P-CSCF Kamailio logs for SIP 408 Request Timeout errors resulting from the T1 timer expiry on the Mw interface
- **`h2`** (fit=0.30, nf=icscf, specificity=moderate):
    - **Statement:** I-CSCF is the source of the signaling drops on the Mw interface, acting as a downstream partition.
    - **Falsification probes:**
        - measure_rtt from I-CSCF to S-CSCF to check for Mw interface latency originating from I-CSCF
        - Check I-CSCF SIP error counters for elevated values indicating failure to forward requests
- **`h3`** (fit=0.10, nf=upf, specificity=moderate):
    - **Statement:** UPF is the source of the data plane throughput drops.
    - **Falsification probes:**
        - Check UPF logs for internal errors
        - Check fivegs_ep_n3_gtp_indatapktn3upf counters to see if packets are actively arriving


## Falsification Plans (Phase 4)

**3 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `pcscf`)

**Hypothesis:** P-CSCF is the source of the elevated SIP error ratio and downstream signaling drops, evidenced by a measured 2000ms network latency on all its outbound interfaces.

**Probes (3):**
1. **`measure_rtt`** — pcscf -> icscf_ip
    - *Expected if hypothesis holds:* Probe observes a latency of approximately 2000ms.
    - *Falsifying observation:* Probe observes a baseline latency under 10ms.
2. **`measure_rtt`** — scscf -> icscf_ip
    - *Expected if hypothesis holds:* Probe observes a baseline latency under 10ms.
    - *Falsifying observation:* Probe observes a latency of approximately 2000ms.
3. **`run_kamcmd`** — run_kamcmd('pcscf', 'stats.fetch script:register_time')
    - *Expected if hypothesis holds:* Probe reads a value equal to 0 or a very large positive delta above the typical range.
    - *Falsifying observation:* Probe reads a value within the typical range of 150.0 to 350.0.

*Notes:* Uses KB-curated metric pcscf.avg_register_time_ms. The partner probe scscf -> icscf isolates the latency solely to pcscf by establishing the I-CSCF container and path to S-CSCF are operating normally.

### Plan for `h2` (target: `icscf`)

**Hypothesis:** I-CSCF is the source of the signaling drops on the Mw interface, acting as a downstream partition.

**Probes (3):**
1. **`measure_rtt`** — pcscf -> icscf_ip
    - *Expected if hypothesis holds:* Probe observes high latency or packet loss.
    - *Falsifying observation:* Probe observes a baseline latency under 10ms and zero packet loss.
2. **`measure_rtt`** — scscf -> icscf_ip
    - *Expected if hypothesis holds:* Probe observes high latency or packet loss.
    - *Falsifying observation:* Probe observes a baseline latency under 10ms and zero packet loss.
3. **`run_kamcmd`** — run_kamcmd('icscf', 'stats.fetch ims_icscf:uar_avg_response_time')
    - *Expected if hypothesis holds:* Probe reads a value of 0 or a large spike.
    - *Falsifying observation:* Probe reads a value within the typical range of 30.0 to 100.0.

*Notes:* Uses partner RTT probe from scscf to confirm icscf is the shared source of the partition.

### Plan for `h3` (target: `upf`)

**Hypothesis:** UPF is the source of the data plane throughput drops.

**Probes (3):**
1. **`get_dp_quality_gauges`** — window_seconds=120 to check upf.gtp_indatapktn3upf_per_ue
    - *Expected if hypothesis holds:* Probe reads upf.gtp_indatapktn3upf_per_ue as 0 or severely dropped compared to typical active traffic.
    - *Falsifying observation:* Probe reads upf.gtp_indatapktn3upf_per_ue within the typical range of 0.0 to 10.0 for active calls.
2. **`get_dp_quality_gauges`** — window_seconds=120 to check ims.rtpengine.loss_ratio
    - *Expected if hypothesis holds:* Probe reads ims.rtpengine.loss_ratio as a large spike.
    - *Falsifying observation:* Probe reads ims.rtpengine.loss_ratio within the typical range of 0.0 to 0.1.
3. **`get_dp_quality_gauges`** — window_seconds=120 to check ims.rtpengine.errors_per_second
    - *Expected if hypothesis holds:* Probe reads ims.rtpengine.errors_per_second as 0.
    - *Falsifying observation:* Probe reads ims.rtpengine.errors_per_second as a spiked value.

*Notes:* Checks specific indicators for UPF data plane throughput drops based on upf.gtp_indatapktn3upf_per_ue and cross-validates with RTPEngine stats.


## Parallel Investigators (Phase 5)

**3 sub-Investigator verdict(s):** **1 NOT_DISPROVEN**, **2 DISPROVEN**

### `h1` — ✅ **NOT_DISPROVEN**

**Hypothesis:** P-CSCF is the source of the elevated SIP error ratio and downstream signaling drops, evidenced by a measured 2000ms network latency on all its outbound interfaces.

**Reasoning:** [Multi-shot consensus — both shots returned NOT_DISPROVEN.]

Shot 1: All probes executed produced evidence consistent with the hypothesis. A measured latency of ~2000ms was observed from P-CSCF to I-CSCF, while a partner probe from S-CSCF to I-CSCF showed sub-millisecond baseline latency, isolating the fault to the P-CSCF's networking stack. Furthermore, P-CSCF's `script:register_time` stat was heavily inflated (32201), confirming severe processing and forwarding delays aligned with the latency fault.

Shot 2: The falsification plan probes confirmed the hypothesis at every step. Measuring RTT from P-CSCF to I-CSCF yielded ~2000ms latency, proving the presence of significant outbound delay. Running the partner RTT probe from S-CSCF to I-CSCF showed sub-millisecond baseline latency (0.083ms), isolating the latency to the P-CSCF stack specifically rather than a network-wide path or the I-CSCF container itself. Querying Kamailio stats on P-CSCF for the registration time script metric yielded an extremely large value (32201), confirming severe processing and signaling delays on the P-CSCF.

**Probes executed (3):**
- **pcscf -> icscf_ip** ✓ CONSISTENT
    - *Tool:* `measure_rtt(container="pcscf", target="icscf")`
    - *Observation:* [EVIDENCE: measure_rtt("pcscf", "icscf") -> "rtt min/avg/max/mdev = 1952.128/1996.624/2049.824/30.714 ms"]
    - *Comment:* The probe confirmed ~2000ms latency on the outbound path from P-CSCF to I-CSCF, matching the hypothesized fault condition.
- **scscf -> icscf_ip** ✓ CONSISTENT
    - *Tool:* `measure_rtt(container="scscf", target="icscf")`
    - *Observation:* [EVIDENCE: measure_rtt("scscf", "icscf") -> "rtt min/avg/max/mdev = 0.038/0.093/0.623/0.069 ms"]
    - *Comment:* The probe confirmed normal network latency between S-CSCF and I-CSCF. This rules out I-CSCF as the source of the latency and isolates the fault entirely to P-CSCF.
- **run_kamcmd('pcscf', 'stats.fetch script:register_time')** ✓ CONSISTENT
    - *Tool:* `run_kamcmd(container="pcscf", command="stats.fetch script:register_time")`
    - *Observation:* [EVIDENCE: run_kamcmd("pcscf", "stats.fetch script:register_time") -> "script.register_time: 32201"]
    - *Comment:* The registration time script statistic at P-CSCF shows an abnormally huge positive delta (32201 vs a typical 150-350 range), demonstrating the direct impact of the latency on SIP transactions.

### `h2` — ❌ **DISPROVEN**

**Hypothesis:** I-CSCF is the source of the signaling drops on the Mw interface, acting as a downstream partition.

**Reasoning:** [Multi-shot consensus — both shots returned DISPROVEN.]

Shot 1: The hypothesis is contradicted by direct evidence. RTT from S-CSCF to I-CSCF is healthy (<1ms) and the I-CSCF UAR response time is within the normal range (94ms). The high latency is isolated to the P-CSCF to I-CSCF path, proving the issue originates from the P-CSCF network stack rather than the I-CSCF acting as a downstream partition.

Shot 2: The hypothesis is falsified by direct triangulation. While latency from P-CSCF to I-CSCF is 2000ms, latency from S-CSCF to I-CSCF is less than 0.1ms with zero packet loss, proving the I-CSCF network stack itself is not partitioned or delayed. Furthermore, the I-CSCF's UAR average response time is 94ms, which falls within the healthy baseline range, proving it is processing requests nominally without internal stalling.

**Probes executed (3):**
- **pcscf -> icscf_ip** ✓ CONSISTENT
    - *Tool:* `measure_rtt("pcscf", "icscf")`
    - *Observation:* [EVIDENCE: measure_rtt("pcscf", "icscf") -> "rtt min/avg/max/mdev = 1950.580/2005.544/2048.322/28.064 ms"]
    - *Comment:* Shows high latency (2000ms), but this measurement conflates I-CSCF health with P-CSCF health and their network path.
- **scscf -> icscf_ip** ✗ CONTRADICTS
    - *Tool:* `measure_rtt("scscf", "icscf")`
    - *Observation:* [EVIDENCE: measure_rtt("scscf", "icscf") -> "0% packet loss, time 6748ms\nrtt min/avg/max/mdev = 0.037/0.080/0.196/0.025 ms"]
    - *Comment:* S-CSCF to I-CSCF latency is under 1ms with 0% loss, proving I-CSCF is reachable and not broadly partitioned.
- **run_kamcmd('icscf', 'stats.fetch ims_icscf:uar_avg_response_time')** ✗ CONTRADICTS
    - *Tool:* `run_kamcmd("icscf", "stats.fetch ims_icscf:uar_avg_response_time")`
    - *Observation:* [EVIDENCE: run_kamcmd("icscf", "stats.fetch ims_icscf:uar_avg_response_time") -> "ims_icscf.uar_avg_response_time: 94"]
    - *Comment:* I-CSCF UAR response time is 94, which is well within the typical healthy range of 30 to 100, proving I-CSCF is responding normally.

**Alternative suspects:** pcscf

### `h3` — ❌ **DISPROVEN**

**Hypothesis:** UPF is the source of the data plane throughput drops.

**Reasoning:** [Multi-shot consensus — both shots returned DISPROVEN.]

Shot 1: UPF is silent because upstream IMS produced no work (active dialogs = 0), making it a case of starvation rather than a fault at the UPF. P-CSCF is failing to set up calls due to ~2000ms latency, resulting in zero active dialogs and zero active media sessions at RTPEngine. Because no calls are established, there is no user-plane traffic for UPF to process, contradicting the hypothesis that UPF is dropping active data plane traffic.

Shot 2: The hypothesis is disproven because UPF is silent due to upstream starvation, not an internal fault. The RTPEngine reports a loss_ratio of 0, meaning no packets are being dropped by UPF during the minimal active sessions. Instead, the control plane is failing to set up any calls (pcscf.dialogs_per_ue = 0) because P-CSCF is experiencing a severe network latency of 2000ms to downstream components (measured from P-CSCF to I-CSCF). This latency times out SIP transactions before any RTP traffic can be established, starving the UPF of data plane traffic.

**Probes executed (3):**
- **window_seconds=120 to check upf.gtp_indatapktn3upf_per_ue** ✗ CONTRADICTS
    - *Tool:* `get_diagnostic_metrics(at_time_ts=1779762079.84375, nfs=["upf", "pcscf"])`
    - *Observation:* [EVIDENCE: get_diagnostic_metrics(at_time_ts=1779762079.84375, nfs=["upf", "pcscf"]) -> "normalized.upf.gtp_indatapktn3upf_per_ue = 0.19"] and [EVIDENCE: get_diagnostic_metrics(at_time_ts=1779762079.84375, nfs=["upf", "pcscf"]) -> "normalized.pcscf.dialogs_per_ue = 0"]
    - *Comment:* UPF uplink traffic per UE is extremely low, but P-CSCF dialogs per UE is 0. UPF is starved of media traffic because no calls are active.
- **window_seconds=120 to check ims.rtpengine.loss_ratio** ✗ CONTRADICTS
    - *Tool:* `get_dp_quality_gauges(at_time_ts=1779762079.84375, window_seconds=120)`
    - *Observation:* [EVIDENCE: get_dp_quality_gauges(at_time_ts=1779762079.84375, window_seconds=120) -> "loss (recent)  : N/A (no samples in window)"] and [EVIDENCE: get_dp_quality_gauges(at_time_ts=1779762079.84375, window_seconds=120) -> "active sessions: 0"]
    - *Comment:* RTPEngine reports no packet loss and zero active sessions, confirming no media streams exist to experience drops.
- **window_seconds=120 to check ims.rtpengine.errors_per_second** ✗ CONTRADICTS
    - *Tool:* `get_diagnostic_metrics(at_time_ts=1779762079.84375, nfs=["rtpengine"])`
    - *Observation:* [EVIDENCE: get_diagnostic_metrics(at_time_ts=1779762079.84375, nfs=["rtpengine"]) -> "rtpengine.errors_per_second_(total) = 0"]
    - *Comment:* RTPEngine shows zero relay-loop errors.

**Alternative suspects:** pcscf


## Evidence Validation (Phase 6)

**Overall verdict:** clean
**Overall confidence:** high

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 6 | 3/3 | clean | high |
| `InvestigatorAgent_h2` | 6 | 3/3 | clean | high |
| `InvestigatorAgent_h3` | 7 | 5/5 | clean | high |


## Ground Truth

**Failure domain:** ims_signaling  
**Protocol impact:** SIP  
**Affected components:** pcscf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v7-adk/pro=gemini-3.1-pro-preview+flash=gemini-3.5-flash  
**Time to diagnosis:** 546.0s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: Transport-layer fault localized to pcscf[eth0]: qdisc_netem_delay reports 2000.0 ms of delay.
> - **timeline**:
>     1. Path walk started for flow ims_registration.
>     2. Walk attributed latency_at_hop (2000ms) to pcscf at eth0 via qdisc_netem_delay.
>     3. Application-layer pipeline confirmed severe processing and signaling delays on P-CSCF due to latency.
>     4. Path walk concluded with high confidence.
> - **root_cause**: Kernel-level packet delay on P-CSCF's egress: `tc netem` qdisc is injecting 2000ms of delay. (primary_suspect_nf: `pcscf`)
> - **affected_components**:
>     - `pcscf`: Root Cause
> - **recommendation**: Inspect tc qdisc on pcscf: `docker exec pcscf tc -s qdisc show dev eth0`
> - **confidence**: high
> - **verdict_kind**: localized
> - **explanation**: | # | hop | kind | iface | prober | attribution |
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
> | 13 | pcscf | container | eth0 | KernelHopProber | latency_at_hop (2000ms, qdisc_netem_delay) 🎯 |
> | 14 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 15 | icscf | container | eth0 | KernelHopProber | clean |
> | 16 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 17 | pyhss | container | eth0 | KernelHopProber | clean |
> | 18 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 19 | icscf | container | eth0 | KernelHopProber | clean |
> | 20 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 21 | scscf | container | eth0 | KernelHopProber | clean |
> | 22 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 23 | pyhss | container | eth0 | KernelHopProber | clean |
> | 24 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 25 | scscf | container | eth0 | KernelHopProber | clean |
> | 26 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 27 | pyhss | container | eth0 | KernelHopProber | clean |
> | 28 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 29 | scscf | container | eth0 | KernelHopProber | clean |
> | 30 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 31 | icscf | container | eth0 | KernelHopProber | clean |
> | 32 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 33 | pcscf | container | eth0 | KernelHopProber | latency_at_hop (2000ms, qdisc_netem_delay) |
> | 34 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 35 | e2e_ue1 | container | eth0 | KernelHopProber | clean |
> | 36 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 37 | pcscf | container | eth0 | KernelHopProber | latency_at_hop (2000ms, qdisc_netem_delay) |
> | 38 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 39 | scp | container | eth0 | KernelHopProber | clean |
> | 40 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 41 | pcf | container | eth0 | KernelHopProber | clean |
> 
> ```
> pcscf[eth0] qdisc=netem: sent=424 dropped=0 (0.00%)
> ---tc -s qdisc show dev eth0---
> qdisc netem 80d9: root refcnt 9 limit 1000 delay 2s  50ms
>  Sent 62006 bytes 424 pkt (dropped 0, overlimits 0 requeues 0) 
>  backlog 74b 1p requeues 0
> ```
> 
> Classifier rationale: label=mixed. Both transport-layer (2) and application-layer (2) signals are load-bearing. Path walk runs first; falls through to the application-layer pipeline if the walk produces null localization.
> Transport signals: normalized.upf.gtp_outdatapktn3upf_per_ue (drop, score=3.50) — KB-labeled transport: core.upf.gtp_outdatapktn3upf_per_ue (drop, score=3.50); normalized.upf.gtp_indatapktn3upf_per_ue (drop, score=0.79) — KB-labeled transport: core.upf.gtp_indatapktn3upf_per_ue (drop, score=0.79)
> Application signals: derived.pcscf_sip_error_ratio (spike, score=4.59) — KB-labeled application: ims.pcscf.sip_error_ratio (spike, score=4.59); normalized.smf.bearers_per_ue (shift, score=0.01) — KB-labeled application: core.smf.bearers_per_ue (shift, score=0.01)
> Ambiguous signals: normalized.icscf.cdp_replies_per_ue (drop, score=4.59) — KB-labeled mixed: ims.icscf.cdp_replies_per_ue (drop, score=4.59)

### Scoring Breakdown

**Overall score: 100%**

**Scorer assessment:** The agent delivered a flawless diagnosis, precisely identifying the 2000ms latency on the P-CSCF as the root cause with perfect layer and component attribution.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | Yes | The agent correctly identified that the root cause was a 2000ms network latency/delay on the P-CSCF component, matching the simulated failure mode perfectly. |
| Component overlap | 100% | The agent correctly identified 'pcscf' as the primary affected component and labeled it as the 'Root Cause' in the affected components list. |
| Severity correct | Yes | The agent correctly characterized the issue as a severe latency/delay degradation (2000ms delay) rather than a complete container crash or network partition. |
| Fault type identified | Yes | The agent correctly identified the fault type as network latency/delay, specifically noting the 2000ms delay on the egress interface. |
| Layer accuracy | Yes | The agent correctly attributed the failure to the 'ims' layer in its network analysis, which is the correct ontology layer for the P-CSCF. |
| Confidence calibrated | Yes | The agent's high confidence is fully justified given the precise identification of the 2000ms delay and the supporting 'tc qdisc' tool evidence. |

**Ranking position:** #1 — The correct root cause (P-CSCF latency) was identified as the primary and only suspect.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 633,012 |
| Output tokens | 12,216 |
| Thinking tokens | 42,694 |
| **Total tokens** | **687,922** |

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
| NetworkAnalystAgent | 314,225 | 16 | 7 |
| Phase 3 NetworkAnalyst__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 18,735 | 0 | 1 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 19,463 | 0 | 1 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| InvestigatorAgent_h1 | 32,792 | 3 | 2 |
| InvestigatorAgent_h1 | 32,307 | 3 | 2 |
| InvestigatorAgent_h1__reconciliation | 0 | 0 | 0 |
| InvestigatorAgent_h2 | 32,821 | 3 | 2 |
| InvestigatorAgent_h2 | 32,751 | 3 | 2 |
| InvestigatorAgent_h2__reconciliation | 0 | 0 | 0 |
| InvestigatorAgent_h3 | 96,452 | 4 | 5 |
| InvestigatorAgent_h3 | 84,272 | 3 | 4 |
| InvestigatorAgent_h3__reconciliation | 0 | 0 | 0 |
| Phase5FanOutAudit | 0 | 0 | 0 |
| Phase6.5CandidatePool | 0 | 0 | 0 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 24,104 | 0 | 1 |
| Phase 7 Synthesis__guardrail | 0 | 0 | 0 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 697.1s
