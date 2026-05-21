# Episode Report: P-CSCF Latency

**Agent:** v7  
**Episode ID:** ep_20260521_020953_p_cscf_latency  
**Date:** 2026-05-21T02:09:54.653800+00:00  
**Duration:** 481.6s  

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

- **Propagation window:** 136s (ObservationTrafficAgent drove traffic for this window; verifier added wait=0s on top)
- **Nodes with significant deltas:** 3
- **Nodes with any drift:** 4

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 34.83 (per-bucket threshold: 26.31, context bucket (0, 1), trained on 323 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following metrics deviate from their learned-healthy baseline. Treat each as a semantic observation (meaning + numbers), not a number alone — the KB's interpretation is the authoritative reading.

- **`context.cx_active`** — current **0.00** vs learned baseline **0.59** (MEDIUM, drop). *(No KB context available — interpret from the metric name.)*

- **`normalized.icscf.cdp_replies_per_ue`** (I-CSCF Diameter reply rate per UE) — current **0.00 replies_per_second_per_ue** vs learned baseline **0.03 replies_per_second_per_ue** (MEDIUM, drop)
    - **What it measures:** Liveness of the I-CSCF↔HSS Cx path. Drops to 0 when HSS is unreachable OR when no signaling is occurring at the I-CSCF (idle or upstream P-CSCF partitioned).
    - **Drop means:** No Cx replies in the window. Could be healthy idle OR a Cx-path fault.
    - **Healthy typical range:** 0–1 replies_per_second_per_ue

- **`normalized.icscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at I-CSCF) — current **0.00 requests_per_second** vs learned baseline **0.06 requests_per_second** (MEDIUM, drop)
    - **What it measures:** Health of the P-CSCF → I-CSCF forwarding path (Mw interface). When
this drops to zero while P-CSCF REGISTER rate is still non-zero,
it's the SIGNATURE of an IMS partition between P-CSCF and I-CSCF.
    - **Drop means:** Either UEs not registering at all, or P-CSCF isolated from I-CSCF.
    - **Healthy typical range:** 0–0.5 requests_per_second
    - **Healthy invariant:** Per-UE rate. Should closely track ims.pcscf.rcv_requests_register_per_ue.

- **`normalized.scscf.cdp_replies_per_ue`** (S-CSCF CDP Diameter replies per UE) — current **0.00 replies_per_second_per_ue** vs learned baseline **0.06 replies_per_second_per_ue** (MEDIUM, drop)
    - **What it measures:** Active S-CSCF Diameter traffic with HSS. Near-zero when registrations idle OR HSS partition.
    - **Drop means:** No active S-CSCF Diameter exchanges (idle or partitioned).
    - **Healthy typical range:** 0–1 replies_per_second_per_ue
    - **Healthy invariant:** Per-UE rate; varies with registration/auth load.

- **`normalized.scscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at S-CSCF) — current **0.00 requests_per_second** vs learned baseline **0.06 requests_per_second** (MEDIUM, drop)
    - **What it measures:** Health of the I-CSCF → S-CSCF forwarding path. Drop to zero while
I-CSCF is receiving REGISTERs = S-CSCF-side issue (crashed, or
I-CSCF → S-CSCF path broken).
    - **Drop means:** S-CSCF isolated or not running.
    - **Healthy typical range:** 0–0.5 requests_per_second
    - **Healthy invariant:** Per-UE rate. Tracks icscf.register rate.

- **`normalized.upf.gtp_indatapktn3upf_per_ue`** (GTP-U uplink rate per UE (N3)) — current **0.06 packets_per_second** vs learned baseline **1.45 packets_per_second** (MEDIUM, drop)
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

- **`normalized.upf.gtp_outdatapktn3upf_per_ue`** (GTP-U downlink rate per UE (N3)) — current **0.00 packets_per_second** vs learned baseline **1.45 packets_per_second** (MEDIUM, drop)
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

- **`normalized.pcscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at P-CSCF) — current **0.06 requests_per_second** vs learned baseline **0.06 requests_per_second** (LOW, shift)
    - **What it measures:** How actively UEs are refreshing their IMS registrations with the
P-CSCF. REGISTERs arrive periodically (re-registration timer) plus
at attach. Sustained zero means UEs cannot reach P-CSCF OR the
UE-to-network SIP path is broken.
    - **Shift means:** Fewer REGISTERs than expected — UE connectivity or P-CSCF reachability issue.
    - **Healthy typical range:** 0–0.5 requests_per_second
    - **Healthy invariant:** Per-UE rate — same value at any deployment scale.

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
**Flag counts:** transport=2, application=1, ambiguous=6

### Transport-bucket flags (2)

| Metric | Direction | Score | KB-driven reason |
|---|---|---:|---|
| `normalized.upf.gtp_indatapktn3upf_per_ue` | drop | 4.59 | KB-labeled transport: core.upf.gtp_indatapktn3upf_per_ue (drop, score=4.59) |
| `normalized.upf.gtp_outdatapktn3upf_per_ue` | drop | 4.59 | KB-labeled transport: core.upf.gtp_outdatapktn3upf_per_ue (drop, score=4.59) |

### Application-bucket flags (1)

| Metric | Direction | Score | KB-driven reason |
|---|---|---:|---|
| `normalized.smf.bearers_per_ue` | shift | 0.01 | KB-labeled application: core.smf.bearers_per_ue (shift, score=0.01) |

### Ambiguous-bucket flags (6)

| Metric | Direction | Score | KB-driven reason |
|---|---|---:|---|
| `context.cx_active` | drop | 4.59 | no KB entry for context.cx_active — classification ambiguous |
| `normalized.icscf.cdp_replies_per_ue` | drop | 4.59 | KB-labeled mixed: ims.icscf.cdp_replies_per_ue (drop, score=4.59) |
| `normalized.icscf.core:rcv_requests_register_per_ue` | drop | 4.59 | KB-labeled mixed: ims.icscf.rcv_requests_register_per_ue (drop, score=4.59) |
| `normalized.scscf.cdp_replies_per_ue` | drop | 4.59 | KB-labeled mixed: ims.scscf.cdp_replies_per_ue (drop, score=4.59) |
| `normalized.scscf.core:rcv_requests_register_per_ue` | drop | 4.59 | KB-labeled mixed: ims.scscf.rcv_requests_register_per_ue (drop, score=4.59) |
| `normalized.pcscf.core:rcv_requests_register_per_ue` | shift | 2.65 | KB-labeled mixed: ims.pcscf.rcv_requests_register_per_ue (shift, score=2.65) |

**Rationale:**

```
label=mixed. Both transport-layer (2) and application-layer (1) signals are load-bearing. Path walk runs first; falls through to the application-layer pipeline if the walk produces null localization.

Transport signals: normalized.upf.gtp_indatapktn3upf_per_ue (drop, score=4.59) — KB-labeled transport: core.upf.gtp_indatapktn3upf_per_ue (drop, score=4.59); normalized.upf.gtp_outdatapktn3upf_per_ue (drop, score=4.59) — KB-labeled transport: core.upf.gtp_outdatapktn3upf_per_ue (drop, score=4.59)

Application signals: normalized.smf.bearers_per_ue (shift, score=0.01) — KB-labeled application: core.smf.bearers_per_ue (shift, score=0.01)

Ambiguous signals: context.cx_active (drop, score=4.59) — no KB entry for context.cx_active — classification ambiguous; normalized.icscf.cdp_replies_per_ue (drop, score=4.59) — KB-labeled mixed: ims.icscf.cdp_replies_per_ue (drop, score=4.59); normalized.icscf.core:rcv_requests_register_per_ue (drop, score=4.59) — KB-labeled mixed: ims.icscf.rcv_requests_register_per_ue (drop, score=4.59); normalized.scscf.cdp_replies_per_ue (drop, score=4.59) — KB-labeled mixed: ims.scscf.cdp_replies_per_ue (drop, score=4.59); normalized.scscf.core:rcv_requests_register_per_ue (drop, score=4.59) — KB-labeled mixed: ims.scscf.rcv_requests_register_per_ue (drop, score=4.59) [+1 more]
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
Resolved transport path to flow `data_pdu_session_user_traffic` (score=12, 11 hops on the walk). Load-bearing components: ['context', 'icscf', 'pcscf', 'scscf', 'smf', 'upf']. Other candidate flows considered: vonr_media=12, ims_registration=8, vonr_call_teardown=8, vonr_call_setup=8.
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

### Localized Synthesis

*Walker found no hop with attribution. Phase 0.6 returned None and the orchestrator fell through to the application-layer pipeline (Phases 1-7) below — the diagnosis you see in `Agent Diagnosis` came from that fallback path, not from Phase 0.6.*

## Event Aggregation (Phase 1)

No events fired during this episode. Either no metric KB triggers matched, or the episode encountered no meaningful state transitions.

## Correlation Analysis (Phase 2)

No events fired — correlation engine had nothing to work with.

## RAG & Operational Lessons (Phase 2.5)

### RAG retrieval — prior similar episodes

**Status:** `hits` — hits=5, top_sim=0.89, top_case=v7/ep_20260510_194005_dns_failure
**Index:** `/home/ehoskas/agentic-network-ops/rag_index`  **Corpus size:** 102 cases
**Classifier label used in retrieval:** `mixed`
**Retrieval params:** k=5, min_similarity=0.4
**Hits (5):**

| Rank | Sim | Case ID | Scenario | Ground truth | Primary suspect | Score |
|---:|---:|---|---|---|---|---:|
| 0 | 89% | `v7/ep_20260510_194005_dns_failure` | DNS Failure | `dns` | `dns` | 85% |
| 1 | 86% | `v6/ep_20260429_164815_ims_network_partition` | IMS Network Partition | `pcscf` | `pcscf` | 100% |
| 2 | 82% | `v6/ep_20260430_013408_p_cscf_latency` | P-CSCF Latency | `pcscf` | `pcscf` | 100% |
| 3 | 81% | `v6/ep_20260429_160912_s_cscf_crash` | S-CSCF Crash | `scscf` | `scscf` | 100% |
| 4 | 81% | `v6/ep_20260430_020852_dns_failure` | DNS Failure | `dns` | `dns` | 100% |

*Rendered block injected into the NA prompt's `{prior_similar_episodes}` placeholder: 4545 chars. Source paths are inlined in the block so the EvidenceValidator can audit any case the NA cites.*

### Operational lessons — hand-authored rules corpus

**Status:** `injected` — lessons=16, chars=15678
**Path:** `/home/ehoskas/agentic-network-ops/agentic_ops_common/rag/lessons.yaml`  **Count:** 16  **Block size:** 15678 chars
**Injected lesson IDs:** `L01`, `L02`, `L03`, `L04`, `L05`, `L06`, `L07`, `L08`, `L09`, `L10`, `L11`, `L12`, `L13`, `L14`, `L15`, `L16`

### NA citations of the injected content

**No verbatim citations.** The NA's output text did not reference any retrieved case_id or any injected lesson_id verbatim. This does NOT prove the NA ignored the injected content — the model may have absorbed the patterns implicitly — but it does mean no audit trail links the NA's reasoning back to a specific case or lesson.

## Network Analysis (Phase 3)

**Summary:** The anomaly is driven by a network fault at the P-CSCF which continues to receive REGISTER requests but fails to pass them along, so I-CSCF, S-CSCF, UPF, and SMF are demoted as secondary observers showing downstream consequence metrics of the signaling halt.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | Infrastructure layer is healthy. |
| **ran** | 🟢 GREEN | RAN is healthy and UEs are actively sending requests to the core and IMS. |
| **core** | 🟡 YELLOW | Core layer components (UPF, SMF) are exhibiting downstream symptoms of the IMS signaling partition, as lack of registration prevents data plane traffic. |
| **ims** | 🔴 RED | IMS signaling is severed at the P-CSCF, isolating downstream CSCFs from UE traffic. |

**CORE evidence:**
- normalized.upf.gtp_indatapktn3upf_per_ue drops to near zero
- normalized.upf.gtp_outdatapktn3upf_per_ue drops to near zero
- normalized.smf.bearers_per_ue shifted

**IMS evidence:**
- normalized.icscf.core:rcv_requests_register_per_ue dropped to 0
- normalized.scscf.core:rcv_requests_register_per_ue dropped to 0
- measure_rtt from P-CSCF to I-CSCF shows ~2000 ms latency

**Ranked hypotheses:**

- **`h1`** (fit=0.95, nf=pcscf, specificity=specific):
    - **Statement:** pcscf is the source of the drop in SIP REGISTER rates at I-CSCF and S-CSCF, and the collapse of data plane metrics at the UPF.
    - **Falsification probes:**
        - measure_rtt from pcscf to multiple core NFs to verify if latency is isolated to pcscf's network interface
        - check pcscf logs for forwarding failures or transaction timeouts due to delayed SIP message routing
- **`h2`** (fit=0.20, nf=icscf, specificity=moderate):
    - **Statement:** icscf is the source of the drop in SIP REGISTER rates and CDP replies.
    - **Falsification probes:**
        - measure_rtt from icscf to dns or scscf to check if icscf network is degraded
        - check icscf logs for dropped Mw interface SIP messages
- **`h3`** (fit=0.10, nf=dns, specificity=moderate):
    - **Statement:** dns is the source of the drop in SIP REGISTER rates at I-CSCF and S-CSCF.
    - **Falsification probes:**
        - check dns container status and logs for query resolution errors
        - measure_rtt from pcscf to dns to see if dns is unreachable or delayed


## Falsification Plans (Phase 4)

**3 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `pcscf`)

**Hypothesis:** pcscf is the source of the drop in SIP REGISTER rates at I-CSCF and S-CSCF, and the collapse of data plane metrics at the UPF.

**Probes (3):**
1. **`run_kamcmd`** — run_kamcmd("pcscf", "stats.fetch script:register_time") to check for registration stall signatures.
    - *Expected if hypothesis holds:* A zero reading indicating stalled transactions where the denominator advanced but no registrations completed in the window, or a massive latency spike.
    - *Falsifying observation:* A value within the typical range of 150.0 to 350.0 ms, indicating registrations are actively completing.
2. **`measure_rtt`** — measure_rtt("pcscf", icscf_ip) to test the outbound path to the next hop in registration.
    - *Expected if hypothesis holds:* High packet loss or extreme latency, indicating packets are failing to cross from pcscf to icscf.
    - *Falsifying observation:* 0% packet loss and low latency, indicating the path is healthy.
3. **`measure_rtt`** — measure_rtt("scscf", icscf_ip) as a partner probe to test icscf reachability from a different source.
    - *Expected if hypothesis holds:* 0% packet loss and low latency, demonstrating that icscf is reachable from other nodes and localizing the failure to pcscf's outbound path.
    - *Falsifying observation:* High packet loss, indicating that icscf is broadly unreachable and not uniquely a pcscf issue.

*Notes:* Using KB-authored verification path run_kamcmd for script:register_time on pcscf. Compositional measure_rtt pcscf->icscf is disambiguated by scscf->icscf.

### Plan for `h2` (target: `icscf`)

**Hypothesis:** icscf is the source of the drop in SIP REGISTER rates and CDP replies.

**Probes (3):**
1. **`run_kamcmd`** — run_kamcmd("icscf", "stats.fetch ims_icscf:lir_avg_response_time") to measure responses received by icscf.
    - *Expected if hypothesis holds:* A zero reading indicating no LIR completions (due to dropped traffic) or a massive spike in response time.
    - *Falsifying observation:* A value within the typical range of 30.0 to 100.0 ms.
2. **`measure_rtt`** — measure_rtt("icscf", pyhss_ip) to test connectivity from icscf to the HSS.
    - *Expected if hypothesis holds:* High packet loss or extreme latency.
    - *Falsifying observation:* 0% packet loss and low latency, meaning icscf has no transport issues reaching the HSS.
3. **`measure_rtt`** — measure_rtt("scscf", pyhss_ip) as a partner probe to test pyhss reachability from a different source.
    - *Expected if hypothesis holds:* 0% packet loss and low latency, isolating the previously observed unreachability specifically to the icscf.
    - *Falsifying observation:* High packet loss, which would imply pyhss is broadly down and falsify icscf as the primary source.

*Notes:* Checks I-CSCF specific LIR response times (KB candidate) and disambiguates the path to HSS using S-CSCF as the alternative source.

### Plan for `h3` (target: `dns`)

**Hypothesis:** dns is the source of the drop in SIP REGISTER rates at I-CSCF and S-CSCF.

**Probes (3):**
1. **`get_network_status`** — Check the status of the dns container.
    - *Expected if hypothesis holds:* The dns container is in an exited, down, or restarting state.
    - *Falsifying observation:* The dns container is running stably with no recent restarts.
2. **`measure_rtt`** — measure_rtt("pcscf", dns_ip) to verify if dns is reachable by nodes attempting to resolve addresses.
    - *Expected if hypothesis holds:* High packet loss or extreme latency.
    - *Falsifying observation:* 0% packet loss and low latency.
3. **`measure_rtt`** — measure_rtt("icscf", dns_ip) as a partner probe to test dns reachability from a different node.
    - *Expected if hypothesis holds:* High packet loss or extreme latency, confirming that dns is broadly unreachable across the network rather than just isolated from pcscf.
    - *Falsifying observation:* 0% packet loss and low latency, meaning dns is healthy and the issue observed in the first probe belongs to pcscf.

*Notes:* Checks DNS container health natively, then tests network path to DNS from multiple locations to rule out single-node isolation.


## Parallel Investigators (Phase 5)

**3 sub-Investigator verdict(s):** **1 NOT_DISPROVEN**, **2 DISPROVEN**

### `h1` — ✅ **NOT_DISPROVEN**

**Hypothesis:** pcscf is the source of the drop in SIP REGISTER rates at I-CSCF and S-CSCF, and the collapse of data plane metrics at the UPF.

**Reasoning:** [Multi-shot consensus — both shots returned NOT_DISPROVEN.]

Shot 1: All probes executed produced evidence consistent with the hypothesis. The massive spike in `script:register_time` (29990) at the P-CSCF confirms registrations are stalled. The `measure_rtt` results disambiguate the issue, showing extreme network latency (~2000ms RTT) isolated to the P-CSCF's path to the I-CSCF, while the I-CSCF remains perfectly reachable from the S-CSCF (<1ms RTT).

Shot 2: The probes confirmed a severe network fault isolated to the P-CSCF. A triangulation test using measure_rtt demonstrated extreme latency (~2003ms) on the path from P-CSCF to I-CSCF, while a partner probe from S-CSCF to I-CSCF showed normal healthy latency (~0.1ms), pinpointing the egress issue at the P-CSCF. This perfectly matches the massive latency spike observed in the P-CSCF's registration processing times (29990), confirming it as the source of the blocked signaling.

**Probes executed (3):**
- **run_kamcmd("pcscf", "stats.fetch script:register_time") to check for registration stall signatures.** ✓ CONSISTENT
    - *Tool:* `run_kamcmd("pcscf", "stats.fetch script:register_time")`
    - *Observation:* [EVIDENCE: run_kamcmd("pcscf", "stats.fetch script:register_time") -> "script.register_time: 29990"]
    - *Comment:* The registration time is extremely high (~30 seconds), confirming a massive stall in SIP REGISTER transactions at the P-CSCF.
- **measure_rtt("pcscf", "icscf") to test the outbound path to the next hop in registration.** ✓ CONSISTENT
    - *Tool:* `measure_rtt("pcscf", "icscf")`
    - *Observation:* [EVIDENCE: measure_rtt("pcscf", "icscf") -> "0% packet loss, time 6665ms\nrtt min/avg/max/mdev = 1950.651/1997.630/2048.369/27.278 ms"]
    - *Comment:* Latency between P-CSCF and I-CSCF is hovering around 2000ms, which is extraordinarily high and explains the transaction stalls.
- **measure_rtt("scscf", "icscf") as a partner probe to test icscf reachability from a different source.** ✓ CONSISTENT
    - *Tool:* `measure_rtt("scscf", "icscf")`
    - *Observation:* [EVIDENCE: measure_rtt("scscf", "icscf") -> "0% packet loss, time 6658ms\nrtt min/avg/max/mdev = 0.036/0.096/0.248/0.030 ms"]
    - *Comment:* The path from S-CSCF to I-CSCF is completely healthy (<1ms latency), proving that I-CSCF is operational and the network degradation is isolated to P-CSCF.

### `h2` — ❌ **DISPROVEN**

**Hypothesis:** icscf is the source of the drop in SIP REGISTER rates and CDP replies.

**Reasoning:** [Multi-shot consensus — both shots returned DISPROVEN.]

Shot 1: The hypothesis posits that icscf is the source of the drop in SIP REGISTER rates and CDP replies, potentially due to connectivity loss with the HSS. However, transport probes directly contradict this: [EVIDENCE: measure_rtt("icscf", "pyhss") -> "66 packets transmitted, 66 received, 0% packet loss"] verifies icscf has perfect network connectivity to the HSS. While [EVIDENCE: run_kamcmd("icscf", "stats.fetch ims_icscf:lir_avg_response_time") -> "ims_icscf.lir_avg_response_time: 0"] confirmed a lack of responses, an additional check of [EVIDENCE: get_diagnostic_metrics(at_time_ts=1779329484.03375) -> "normalized.pcscf.core:rcv_requests_register_per_ue = 0.0599"] and [EVIDENCE: get_diagnostic_metrics(at_time_ts=1779329484.03375) -> "normalized.icscf.core:rcv_requests_register_per_ue = 0"] reveals this is because icscf is completely starved of incoming traffic. The drop therefore originates upstream at the pcscf, not at the icscf.

Shot 2: Direct transport measurements show 0% packet loss and healthy latency from icscf to pyhss, contradicting the hypothesis that icscf is experiencing network or reachability issues towards the HSS. While icscf shows 0ms LIR response times (indicating no completions), the healthy network path implies this is due to starvation from upstream rather than a fault originating at the icscf. The evidence points to an upstream failure at pcscf preventing traffic from reaching icscf.

**Probes executed (4):**
- **run_kamcmd("icscf", "stats.fetch ims_icscf:lir_avg_response_time") to measure responses received by icscf.** ✓ CONSISTENT
    - *Tool:* `run_kamcmd("icscf", "stats.fetch ims_icscf:lir_avg_response_time")`
    - *Observation:* [EVIDENCE: run_kamcmd("icscf", "stats.fetch ims_icscf:lir_avg_response_time") -> "ims_icscf.lir_avg_response_time: 0"]
    - *Comment:* A reading of 0 indicates no LIR completions. While this is expected under the hypothesis, diagnostic metrics reveal it is due to upstream traffic starvation from pcscf, not an icscf fault.
- **measure_rtt("icscf", "pyhss") to test connectivity from icscf to the HSS.** ✗ CONTRADICTS
    - *Tool:* `measure_rtt("icscf", "pyhss")`
    - *Observation:* [EVIDENCE: measure_rtt("icscf", "pyhss") -> "66 packets transmitted, 66 received, 0% packet loss, time 6701ms"]
    - *Comment:* 0% packet loss and low latency directly refutes the mechanism of icscf having transport or connectivity issues reaching the HSS.
- **measure_rtt("scscf", "pyhss") as a partner probe to test pyhss reachability from a different source.** ✓ CONSISTENT
    - *Tool:* `measure_rtt("scscf", "pyhss")`
    - *Observation:* [EVIDENCE: measure_rtt("scscf", "pyhss") -> "66 packets transmitted, 66 received, 0% packet loss, time 6723ms"]
    - *Comment:* 0% packet loss confirms the pyhss container is up and broadly reachable, successfully ruling out pyhss being completely down and matching the partner probe expectation.
- **get_diagnostic_metrics(at_time_ts=...) to check where REGISTER traffic is dropping.** ✗ CONTRADICTS
    - *Tool:* `get_diagnostic_metrics(at_time_ts=1779329484.03375)`
    - *Observation:* [EVIDENCE: get_diagnostic_metrics(at_time_ts=1779329484.03375) -> "normalized.icscf.core:rcv_requests_register_per_ue = 0"]
    - *Comment:* This conclusively demonstrates that the traffic drop originates upstream of icscf, as pcscf is receiving REGISTERs but forwarding none to icscf. This exonerates icscf as the source of the drop.

**Alternative suspects:** pcscf

### `h3` — ❌ **DISPROVEN**

**Hypothesis:** dns is the source of the drop in SIP REGISTER rates at I-CSCF and S-CSCF.

**Reasoning:** [Multi-shot consensus — both shots returned DISPROVEN.]

Shot 1: The dns container is running and healthy. While probes revealed extreme latency (approx 2000ms) from pcscf to dns, a triangulation probe from icscf to dns showed normal sub-millisecond latency and 0% packet loss. This confirms that dns itself is fully reachable and responsive; the fault is localized to pcscf's network interface, not the dns component.

Shot 2: The DNS container is running and healthy. While the P-CSCF experiences extreme latency (~2000ms) when pinging DNS, the I-CSCF can reach DNS with normal sub-millisecond latency (0.1ms). This directional triangulation proves that DNS is fully functional and reachable, and that the network fault is isolated to the P-CSCF.

**Probes executed (3):**
- **Check the status of the dns container.** ✗ CONTRADICTS
    - *Tool:* `get_network_status()`
    - *Observation:* [EVIDENCE: get_network_status() -> "'dns': 'running'"]
    - *Comment:* The dns container is in a running state, contradicting the expectation that it would be exited, down, or restarting.
- **measure_rtt("pcscf", dns_ip) to verify if dns is reachable by nodes attempting to resolve addresses.** ✓ CONSISTENT
    - *Tool:* `measure_rtt("pcscf", "dns")`
    - *Observation:* [EVIDENCE: measure_rtt("pcscf", "dns") -> "0% packet loss, time 6627ms\nrtt min/avg/max/mdev = 1953.083/1992.924/2049.260/25.801 ms"]
    - *Comment:* Extreme latency (~2s) was observed from pcscf to dns. While consistent with the symptoms, this directional probe conflates dns health with pcscf network isolation.
- **measure_rtt("icscf", dns_ip) as a partner probe to test dns reachability from a different node.** ✗ CONTRADICTS
    - *Tool:* `measure_rtt("icscf", "dns")`
    - *Observation:* [EVIDENCE: measure_rtt("icscf", "dns") -> "0% packet loss, time 6681ms\nrtt min/avg/max/mdev = 0.042/0.089/0.191/0.025 ms"]
    - *Comment:* Triangulation probe shows 0% packet loss and <1ms latency from icscf to dns. This confirms dns is healthy and the issue is localized to pcscf.

**Alternative suspects:** pcscf


## Evidence Validation (Phase 6)

**Overall verdict:** clean
**Overall confidence:** high

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 6 | 3/3 | clean | high |
| `InvestigatorAgent_h2` | 7 | 8/8 | clean | high |
| `InvestigatorAgent_h3` | 6 | 3/3 | clean | high |


## Ground Truth

**Failure domain:** ims_signaling  
**Protocol impact:** SIP  
**Affected components:** pcscf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v7-adk/pro=gemini-3.1-pro-preview+flash=gemini-3.5-flash  
**Time to diagnosis:** 337.2s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: Extreme network latency originating at the P-CSCF is stalling SIP REGISTER transactions and preventing downstream IMS and core network functionality.
> - **timeline**:
>     1. UEs initiate registrations, successfully sending SIP REGISTER requests to the P-CSCF.
>     2. The P-CSCF attempts to forward the requests but encounters ~2000ms network latency on its path to the I-CSCF.
>     3. SIP REGISTER processing times on the P-CSCF spike to approximately 30 seconds due to stalled transactions.
>     4. I-CSCF and S-CSCF are starved of incoming registration traffic.
>     5. Data plane metrics at the UPF collapse due to the lack of successful registrations.
> - **root_cause**: The P-CSCF is experiencing massive outbound network latency (~2000ms RTT) toward the I-CSCF, causing SIP REGISTER transactions to stall. (primary_suspect_nf: `pcscf`)
> - **affected_components**:
>     - `pcscf`: Root Cause
>     - `icscf`: Secondary
>     - `scscf`: Secondary
>     - `upf`: Symptomatic
>     - `smf`: Symptomatic
> - **recommendation**: Investigate the outbound network path and interface configurations on the P-CSCF; verify connectivity and look for sources of extreme latency or traffic shaping on the link towards the I-CSCF.
> - **confidence**: high
> - **verdict_kind**: confirmed
> - **explanation**: Investigations confirmed that the P-CSCF is the root cause of the IMS signaling partition. Probes revealed that the P-CSCF is experiencing extreme latency (~2000ms RTT) when attempting to reach the I-CSCF, which causes SIP REGISTER processing times to spike to nearly 30 seconds. Triangulation probes confirmed this issue is isolated to the P-CSCF's egress path, as the I-CSCF remains fully reachable with sub-millisecond latency from the S-CSCF. Because the P-CSCF cannot forward requests, downstream components including the I-CSCF, S-CSCF, and UPF are starved of traffic, which explains their metric drops. Hypotheses blaming the I-CSCF and DNS were conclusively disproven as both are operating normally and perfectly reachable from other nodes.

### Scoring Breakdown

**Overall score: 100%**

**Scorer assessment:** The agent delivered a flawless diagnosis, accurately identifying the P-CSCF latency, its exact magnitude (~2000ms), and its downstream impacts on IMS registration.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | Yes | The agent correctly identified that the P-CSCF was experiencing massive outbound network latency (~2000ms RTT), which perfectly matches the simulated failure of 2000ms latency injected on the P-CSCF. |
| Component overlap | 100% | The agent correctly identified 'pcscf' as the 'Root Cause' in the affected components list. |
| Severity correct | Yes | The agent correctly characterized the issue as extreme latency and stalled transactions (degradation/delay) rather than a hard container crash, matching the simulated latency injection. |
| Fault type identified | Yes | The agent explicitly identified the fault type as network latency (~2000ms RTT). |
| Layer accuracy | Yes | The agent correctly rated the 'ims' layer as RED and attributed the P-CSCF latency to this layer, which matches the ground truth ontology. |
| Confidence calibrated | Yes | The agent expressed high confidence, which is fully justified given the highly accurate diagnosis and precise RTT measurement evidence. |

**Ranking position:** #1 — The correct root cause (P-CSCF latency) was identified as the primary suspect and ranked first.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 585,571 |
| Output tokens | 10,522 |
| Thinking tokens | 29,348 |
| **Total tokens** | **625,441** |

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
| NetworkAnalystAgent | 342,472 | 13 | 9 |
| Phase 3 NetworkAnalyst__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 14,646 | 0 | 1 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 14,770 | 0 | 1 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| InvestigatorAgent_h1 | 33,252 | 3 | 2 |
| InvestigatorAgent_h1 | 33,877 | 3 | 2 |
| InvestigatorAgent_h1__reconciliation | 0 | 0 | 0 |
| InvestigatorAgent_h2 | 71,560 | 4 | 3 |
| InvestigatorAgent_h2 | 33,847 | 3 | 2 |
| InvestigatorAgent_h2__reconciliation | 0 | 0 | 0 |
| InvestigatorAgent_h3 | 33,736 | 3 | 2 |
| InvestigatorAgent_h3 | 32,555 | 3 | 2 |
| InvestigatorAgent_h3__reconciliation | 0 | 0 | 0 |
| Phase5FanOutAudit | 0 | 0 | 0 |
| Phase6.5CandidatePool | 0 | 0 | 0 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 14,726 | 0 | 1 |
| Phase 7 Synthesis__guardrail | 0 | 0 | 0 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 481.6s
