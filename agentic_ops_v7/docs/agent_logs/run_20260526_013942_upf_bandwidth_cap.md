# Episode Report: UPF Bandwidth Cap

**Agent:** v7  
**Episode ID:** ep_20260526_012208_upf_bandwidth_cap  
**Date:** 2026-05-26T01:22:10.866164+00:00  
**Duration:** 1051.3s  

---

## Scenario

**Category:** network  
**Blast radius:** single_nf  
**Description:** Cap UPF egress at 100 kbit/s with a tc tbf qdisc. The cap is deliberately tight — VoNR media (G.711 ~64 kbit/s per direction at 100 pps) plus signaling traffic exceeds the budget; tbf drops over-rate packets. Tests v7's path walk localizing a bandwidth-induced drop counter at a tbf qdisc, complementing the netem-loss case. The KernelHopProber distinguishes qdisc_tbf from qdisc_netem in the counter_kind field. v6 would see UPF GTP counters drop and likely diagnose UPF correctly by NF, but with low confidence and without naming the qdisc — v7 names the qdisc and the exact dropped count.

## Faults Injected

- **network_bandwidth** on `upf` — {'rate_kbit': 100}

## Baseline (Pre-Fault)

Stack phase before injection: **ready**
All containers running at baseline.

## Fault Propagation Verification

**Verdict:** ✅ `confirmed`

- **Propagation window:** 140s (ObservationTrafficAgent drove traffic for this window; verifier added wait=0s on top)
- **Nodes with significant deltas:** 2
- **Nodes with any drift:** 3

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 32.18 (per-bucket threshold: 26.31, context bucket (0, 1), trained on 323 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following metrics deviate from their learned-healthy baseline. Treat each as a semantic observation (meaning + numbers), not a number alone — the KB's interpretation is the authoritative reading.

- **`normalized.icscf.cdp_replies_per_ue`** (I-CSCF Diameter reply rate per UE) — current **0.01 replies_per_second_per_ue** vs learned baseline **0.03 replies_per_second_per_ue** (MEDIUM, drop)
    - **What it measures:** Liveness of the I-CSCF↔HSS Cx path. Drops to 0 when HSS is unreachable OR when no signaling is occurring at the I-CSCF (idle or upstream P-CSCF partitioned).
    - **Drop means:** No Cx replies in the window. Could be healthy idle OR a Cx-path fault.
    - **Healthy typical range:** 0–1 replies_per_second_per_ue

- **`normalized.icscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at I-CSCF) — current **0.03 requests_per_second** vs learned baseline **0.06 requests_per_second** (MEDIUM, drop)
    - **What it measures:** Health of the P-CSCF → I-CSCF forwarding path (Mw interface). When
this drops to zero while P-CSCF REGISTER rate is still non-zero,
it's the SIGNATURE of an IMS partition between P-CSCF and I-CSCF.
    - **Drop means:** Either UEs not registering at all, or P-CSCF isolated from I-CSCF.
    - **Healthy typical range:** 0–0.5 requests_per_second
    - **Healthy invariant:** Per-UE rate. Should closely track ims.pcscf.rcv_requests_register_per_ue.

- **`normalized.pcscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at P-CSCF) — current **0.03 requests_per_second** vs learned baseline **0.06 requests_per_second** (MEDIUM, drop)
    - **What it measures:** How actively UEs are refreshing their IMS registrations with the
P-CSCF. REGISTERs arrive periodically (re-registration timer) plus
at attach. Sustained zero means UEs cannot reach P-CSCF OR the
UE-to-network SIP path is broken.
    - **Drop means:** No REGISTERs flowing. Unusual unless UEs are all deregistered.
    - **Healthy typical range:** 0–0.5 requests_per_second
    - **Healthy invariant:** Per-UE rate — same value at any deployment scale.

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

- **`normalized.upf.gtp_indatapktn3upf_per_ue`** (GTP-U uplink rate per UE (N3)) — current **0.00 packets_per_second** vs learned baseline **1.45 packets_per_second** (MEDIUM, drop)
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
**Flag counts:** transport=2, application=1, ambiguous=5

### Transport-bucket flags (2)

| Metric | Direction | Score | KB-driven reason |
|---|---|---:|---|
| `normalized.upf.gtp_indatapktn3upf_per_ue` | drop | 4.59 | KB-labeled transport: core.upf.gtp_indatapktn3upf_per_ue (drop, score=4.59) |
| `normalized.upf.gtp_outdatapktn3upf_per_ue` | drop | 4.59 | KB-labeled transport: core.upf.gtp_outdatapktn3upf_per_ue (drop, score=4.59) |

### Application-bucket flags (1)

| Metric | Direction | Score | KB-driven reason |
|---|---|---:|---|
| `normalized.smf.bearers_per_ue` | shift | 0.01 | KB-labeled application: core.smf.bearers_per_ue (shift, score=0.01) |

### Ambiguous-bucket flags (5)

| Metric | Direction | Score | KB-driven reason |
|---|---|---:|---|
| `normalized.icscf.cdp_replies_per_ue` | drop | 4.59 | KB-labeled mixed: ims.icscf.cdp_replies_per_ue (drop, score=4.59) |
| `normalized.icscf.core:rcv_requests_register_per_ue` | drop | 4.59 | KB-labeled mixed: ims.icscf.rcv_requests_register_per_ue (drop, score=4.59) |
| `normalized.pcscf.core:rcv_requests_register_per_ue` | drop | 4.59 | KB-labeled mixed: ims.pcscf.rcv_requests_register_per_ue (drop, score=4.59) |
| `normalized.scscf.cdp_replies_per_ue` | drop | 4.59 | KB-labeled mixed: ims.scscf.cdp_replies_per_ue (drop, score=4.59) |
| `normalized.scscf.core:rcv_requests_register_per_ue` | drop | 4.59 | KB-labeled mixed: ims.scscf.rcv_requests_register_per_ue (drop, score=4.59) |

**Rationale:**

```
label=mixed. Both transport-layer (2) and application-layer (1) signals are load-bearing. Path walk runs first; falls through to the application-layer pipeline if the walk produces null localization.

Transport signals: normalized.upf.gtp_indatapktn3upf_per_ue (drop, score=4.59) — KB-labeled transport: core.upf.gtp_indatapktn3upf_per_ue (drop, score=4.59); normalized.upf.gtp_outdatapktn3upf_per_ue (drop, score=4.59) — KB-labeled transport: core.upf.gtp_outdatapktn3upf_per_ue (drop, score=4.59)

Application signals: normalized.smf.bearers_per_ue (shift, score=0.01) — KB-labeled application: core.smf.bearers_per_ue (shift, score=0.01)

Ambiguous signals: normalized.icscf.cdp_replies_per_ue (drop, score=4.59) — KB-labeled mixed: ims.icscf.cdp_replies_per_ue (drop, score=4.59); normalized.icscf.core:rcv_requests_register_per_ue (drop, score=4.59) — KB-labeled mixed: ims.icscf.rcv_requests_register_per_ue (drop, score=4.59); normalized.pcscf.core:rcv_requests_register_per_ue (drop, score=4.59) — KB-labeled mixed: ims.pcscf.rcv_requests_register_per_ue (drop, score=4.59); normalized.scscf.cdp_replies_per_ue (drop, score=4.59) — KB-labeled mixed: ims.scscf.cdp_replies_per_ue (drop, score=4.59); normalized.scscf.core:rcv_requests_register_per_ue (drop, score=4.59) — KB-labeled mixed: ims.scscf.rcv_requests_register_per_ue (drop, score=4.59)
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
| 4 | 🎯 `upf` | container | `eth0` | `drops_attributed_here` | `qdisc_tbf`: 329 dropped, 191.3% |
| 5 | `internet` | external_network | `eth0` | `inconclusive` | _no_prober_registered_: "no HopProber registered for kind='external_network'; registered kinds: ['contai |
| 6 | `upf` | container | `eth0` | `drops_attributed_here` | `qdisc_tbf`: 329 dropped, 191.3% |
| 7 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 8 | `nr_gnb` | container | `eth0` | `clean` | _clean_ |
| 9 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 10 | `e2e_ue1` | container | `eth0` | `clean` | _clean_ |

> ⚠️ **Soft cap exceeded** — walker probed 0 flows (soft cap = 3). Signals a noisy load-bearing set; inspect screener flag bucketing if this recurs.

> 🔪 **Hard cap (5 flows) truncated 3 additional candidate(s)** below the cut: `diameter_cx_authentication` (4), `pdu_session_establishment` (4), `ue_deregistration` (4). These scored above zero but ranked beyond the top 5 by the prioritizer; not walked.

### Localized Synthesis

**Verdict:** `localized`  
**Primary suspect NF:** `upf`  
**Confidence:** high

**Summary:** Transport-layer fault localized to upf[eth0]: qdisc_tbf reports 329 packets dropped (191.3%).

**Recommendation:** Inspect tc qdisc on upf: `docker exec upf tc -s qdisc show dev eth0`


## Event Aggregation (Phase 1)

No events fired during this episode. Either no metric KB triggers matched, or the episode encountered no meaningful state transitions.

## Correlation Analysis (Phase 2)

No events fired — correlation engine had nothing to work with.

## RAG & Operational Lessons (Phase 2.5)

### RAG retrieval — prior similar episodes

**Status:** `hits` — hits=5, top_sim=0.86, top_case=v6/ep_20260429_160912_s_cscf_crash
**Index:** `/home/ehoskas/agentic-network-ops/rag_index`  **Corpus size:** 102 cases
**Classifier label used in retrieval:** `mixed`
**Retrieval params:** k=5, min_similarity=0.4
**Hits (5):**

| Rank | Sim | Case ID | Scenario | Ground truth | Primary suspect | Score |
|---:|---:|---|---|---|---|---:|
| 0 | 86% | `v6/ep_20260429_160912_s_cscf_crash` | S-CSCF Crash | `scscf` | `scscf` | 100% |
| 1 | 85% | `v6/ep_20260430_013408_p_cscf_latency` | P-CSCF Latency | `pcscf` | `pcscf` | 100% |
| 2 | 84% | `v7/ep_20260510_194005_dns_failure` | DNS Failure | `dns` | `dns` | 85% |
| 3 | 83% | `v7/ep_20260510_192628_upf_bandwidth_cap` | UPF Bandwidth Cap | `upf` | `upf` | 100% |
| 4 | 81% | `v6/ep_20260429_164815_ims_network_partition` | IMS Network Partition | `pcscf` | `pcscf` | 100% |

*Rendered block injected into the NA prompt's `{prior_similar_episodes}` placeholder: 4647 chars. Source paths are inlined in the block so the EvidenceValidator can audit any case the NA cites.*

### Operational lessons — hand-authored rules corpus

**Status:** `injected` — lessons=16, chars=15678
**Path:** `/home/ehoskas/agentic-network-ops/agentic_ops_common/rag/lessons.yaml`  **Count:** 16  **Block size:** 15678 chars
**Injected lesson IDs:** `L01`, `L02`, `L03`, `L04`, `L05`, `L06`, `L07`, `L08`, `L09`, `L10`, `L11`, `L12`, `L13`, `L14`, `L15`, `L16`

### NA citations of the injected content

**Cited lesson IDs:**
- `L03`
- `L09`
- `L15`

*Citations are verbatim string matches — case_ids and lesson_ids appear in the NA's emitted text (summary, hypothesis statements, or layer notes). The EvidenceValidator can audit any cited case by following its `source_episode_path` from the retrieval table above.*

## Network Analysis (Phase 3)

**Summary:** A bidirectional drop to zero in UPF N3 data-plane throughput indicates a severing of the user plane, which starves the downstream IMS chain of SIP REGISTERs and causes the uniform rate halving observed across all CSCFs.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | Core infrastructure components are responsive. |
| **ran** | 🟡 YELLOW | gNB is active but could be failing to forward user-plane traffic to the UPF on N3. |
| **core** | 🔴 RED | UPF is receiving and sending zero data plane traffic despite UEs being attached. |
| **ims** | 🟡 YELLOW | All CSCFs show a 50% drop in received REGISTER rates without SIP errors; per L09 and L15, this is a downstream consequence of upstream starvation. |

**RAN evidence:**
- core.amf.ran_ue = 2 (UEs are attached)

**CORE evidence:**
- normalized.upf.gtp_indatapktn3upf_per_ue dropped to 0.00
- normalized.upf.gtp_outdatapktn3upf_per_ue dropped to 0.00
- normalized.smf.bearers_per_ue shifted to 2.00 (default no-call state)

**IMS evidence:**
- normalized.pcscf.core:rcv_requests_register_per_ue dropped to 0.03
- normalized.icscf.core:rcv_requests_register_per_ue dropped to 0.03
- normalized.scscf.core:rcv_requests_register_per_ue dropped to 0.03

**Ranked hypotheses:**

- **`h1`** (fit=0.90, nf=upf, specificity=specific):
    - **Statement:** UPF is the source of the bidirectional N3 data plane drop, preventing SIP REGISTER packets from traversing the user plane to reach the IMS signaling chain.
    - **Falsification probes:**
        - Run measure_rtt(nr_gnb, upf) and measure_rtt(upf, smf) to triangulate if packet loss is isolated to the UPF network stack.
        - Check UPF container logs and interface qdisc drop counters for internal data-plane faults.
- **`h2`** (fit=0.80, nf=nr_gnb, specificity=specific):
    - **Statement:** gNB is the source of the N3 data plane drop, failing to forward user-plane traffic over the N3 link to UPF.
    - **Falsification probes:**
        - Run measure_rtt(nr_gnb, upf) and measure_rtt(nr_gnb, amf) to triangulate if packet loss originates specifically at the gNB stack.
        - Check gNB logs for radio link failures or N3 GTP-U encapsulation errors.
- **`h3`** (fit=0.60, nf=pcscf, specificity=moderate):
    - **Statement:** P-CSCF is the source of the SIP REGISTER rate drop due to an inbound partition, while the UPF N3 drop flags are artifacts of bucket (0,1) baseline pollution as per L03.
    - **Falsification probes:**
        - Run measure_rtt(upf, pcscf) to verify if the Gm path is lossy specifically at P-CSCF.
        - Inspect P-CSCF logs for internal processing errors that could silently drop inbound REGISTERs.


## Falsification Plans (Phase 4)

**3 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `upf`)

**Hypothesis:** UPF is the source of the bidirectional N3 data plane drop, preventing SIP REGISTER packets from traversing the user plane to reach the IMS signaling chain.

**Probes (3):**
1. **`measure_rtt`** — nr_gnb -> upf_ip
    - *Expected if hypothesis holds:* Packet loss > 0% or RTT > baseline.
    - *Falsifying observation:* 0% packet loss and normal RTT.
2. **`measure_rtt`** — upf -> smf_ip
    - *Expected if hypothesis holds:* Packet loss > 0% or RTT > baseline, isolating the UPF as the common source of the drop across its interfaces.
    - *Falsifying observation:* 0% packet loss and normal RTT. The deviation in the first probe is attributable to the gNB or the gNB-UPF path, not the UPF.
3. **`get_dp_quality_gauges`** — Returns rate-windowed UPF in/out pps over the probe's window to read upf.gtp_indatapktn3upf_per_ue
    - *Expected if hypothesis holds:* Data plane dead on uplink, UPF receiving no packets from gNB (value is zero or significantly dropped).
    - *Falsifying observation:* Value within typical range (0.0, 10.0), indicating traffic is successfully arriving at UPF.

*Notes:* Uses KB-authored upf.gtp_indatapktn3upf_per_ue to verify N3 drop and measure_rtt compositional partner probes to isolate UPF network stack from gNB or path issues.

### Plan for `h2` (target: `nr_gnb`)

**Hypothesis:** gNB is the source of the N3 data plane drop, failing to forward user-plane traffic over the N3 link to UPF.

**Probes (3):**
1. **`measure_rtt`** — nr_gnb -> upf_ip
    - *Expected if hypothesis holds:* Packet loss > 0% or RTT > baseline.
    - *Falsifying observation:* 0% packet loss and normal RTT.
2. **`measure_rtt`** — nr_gnb -> amf_ip
    - *Expected if hypothesis holds:* Packet loss > 0% or RTT > baseline, isolating the gNB as the common source of the drop.
    - *Falsifying observation:* 0% packet loss and normal RTT. The deviation in the first probe is attributable to the UPF or the gNB-UPF path, not the gNB.
3. **`get_network_status`** — Check nr_gnb container status
    - *Expected if hypothesis holds:* Container is exited or repeatedly restarting.
    - *Falsifying observation:* Container is running stably with no restarts.

*Notes:* Uses cross-interface triangulation for gNB (to UPF vs AMF) to confirm if the packet drop is isolated to gNB.

### Plan for `h3` (target: `pcscf`)

**Hypothesis:** P-CSCF is the source of the SIP REGISTER rate drop due to an inbound partition, while the UPF N3 drop flags are artifacts of bucket (0,1) baseline pollution as per L03.

**Probes (3):**
1. **`measure_rtt`** — upf -> pcscf_ip
    - *Expected if hypothesis holds:* Packet loss > 0% or RTT > baseline on the Gm interface path.
    - *Falsifying observation:* 0% packet loss and normal RTT.
2. **`measure_rtt`** — pcscf -> icscf_ip
    - *Expected if hypothesis holds:* Packet loss > 0% or RTT > baseline, isolating the P-CSCF as the common source of the partition.
    - *Falsifying observation:* 0% packet loss and normal RTT. The deviation in the first probe is attributable to the UPF or the UPF-PCSCF path, not the P-CSCF.
3. **`run_kamcmd`** — run_kamcmd('pcscf', 'stats.fetch script:register_time') to read pcscf.avg_register_time_ms
    - *Expected if hypothesis holds:* Ratio snapshots to 0 (numerator did not advance while denominator did) or metric is completely absent, indicating stall or no arrivals.
    - *Falsifying observation:* Value within typical range (150.0, 350.0), indicating REGISTERs are arriving and completing.

*Notes:* Validates inbound partition at P-CSCF using RTT across two interfaces (Gm vs Mw) to localize the fault to P-CSCF. Uses KB candidate run_kamcmd script:register_time to confirm stall.


## Parallel Investigators (Phase 5)

**4 sub-Investigator verdict(s):** **3 DISPROVEN**, **1 INCONCLUSIVE**

### `h1` — ❌ **DISPROVEN**

**Hypothesis:** UPF is the source of the bidirectional N3 data plane drop, preventing SIP REGISTER packets from traversing the user plane to reach the IMS signaling chain.

**Reasoning:** [Multi-shot consensus — both shots returned DISPROVEN.]

Shot 1: The UPF is fully connected and its network interfaces are healthy, but it is completely starved of N3 traffic on the uplink. measure_rtt probes from UPF to SMF and P-CSCF show 0% packet loss, contradicting a network-stack drop at the UPF. Meanwhile, get_dp_quality_gauges and get_diagnostic_metrics confirm that the rate of packets arriving at the UPF from the gNB is zero (gtp_indatapktn3upf_per_ue = 0). Because the UPF is capable of receiving traffic but none arrives, the drop occurs upstream of the UPF, proving the UPF is starved rather than being the source of the drop.

Shot 2: The hypothesis is DISPROVEN because the UPF is starved of traffic, not dropping it. Metrics show the UPF receives exactly 0 inbound GTP-U packets (`gtp_indatapktn3upf_per_ue = 0`), meaning the data plane drop occurs upstream before reaching the UPF. Furthermore, the UPF's container network interfaces are perfectly healthy (0% loss to both SMF and P-CSCF), ruling out internal network stack drops. The planned `measure_rtt` from `nr_gnb` failed because `nr_gnb` is not a container, but triangulation confirms the UPF is a healthy but starved victim, pointing to the gNB as the actual source.

**Probes executed (5):**
- **Run measure_rtt(nr_gnb, upf) to check network loss between gNB and UPF.** ~ AMBIGUOUS
    - *Tool:* `measure_rtt("nr_gnb", "upf")`
    - *Observation:* [EVIDENCE: measure_rtt("nr_gnb", "upf") -> "Unknown source container 'nr_gnb'"]
    - *Comment:* The nr_gnb container name is not available as a probe source in this environment, making this specific compositional partner probe unavailable.
- **Run measure_rtt(upf, smf) to isolate UPF network stack from gNB or path issues.** ✗ CONTRADICTS
    - *Tool:* `measure_rtt("upf", "smf")`
    - *Observation:* [EVIDENCE: measure_rtt("upf", "smf") -> "66 packets transmitted, 66 received, 0% packet loss"]
    - *Comment:* Shows 0% packet loss, verifying the UPF container's network stack and interfaces are perfectly healthy. This contradicts the hypothesis that the UPF is the common source of a network-level drop across its interfaces.
- **Run measure_rtt(upf, pcscf) to further verify UPF network interfaces towards IMS.** ✗ CONTRADICTS
    - *Tool:* `measure_rtt("upf", "pcscf")`
    - *Observation:* [EVIDENCE: measure_rtt("upf", "pcscf") -> "66 packets transmitted, 66 received, 0% packet loss"]
    - *Comment:* Further confirms the UPF network interfaces are healthy across different container segments. The UPF's connectivity towards the IMS domain is intact, refuting an internal UPF network partition.
- **Check UPF throughput rates using get_dp_quality_gauges.** ✗ CONTRADICTS
    - *Tool:* `get_dp_quality_gauges(at_time_ts=1779758571.823951, window_seconds=120)`
    - *Observation:* [EVIDENCE: get_dp_quality_gauges(at_time_ts=1779758571.823951, window_seconds=120) -> "UPF:
    in  packets/sec: 0.1
    out packets/sec: 0.0"]
    - *Comment:* The UPF is starved on the N3 uplink, receiving nearly 0 packets/sec from the gNB. Since the UPF's network stack is healthy but no packets are arriving, the UPF cannot be the source of the drop.
- **Check UPF diagnostic metrics for uplink data plane health.** ✗ CONTRADICTS
    - *Tool:* `get_diagnostic_metrics(at_time_ts=1779758571.823951, nfs=["upf"])`
    - *Observation:* [EVIDENCE: get_diagnostic_metrics(at_time_ts=1779758571.823951, nfs=["upf"]) -> "normalized.upf.gtp_indatapktn3upf_per_ue = 0 [derived, packets_per_second]... interpretation (zero): Data plane dead on uplink — UPF receiving no packets from gNB."]
    - *Comment:* The metric explicitly interprets the 0 value as 'UPF receiving no packets from gNB'. A component that receives 0 input packets is starved, not the source of a drop.

**Alternative suspects:** nr_gnb, gNB-UPF network path

### `h2` — ❓ **INCONCLUSIVE**

**Hypothesis:** gNB is the source of the N3 data plane drop, failing to forward user-plane traffic over the N3 link to UPF.

**Reasoning:** The falsification plan relies on running network and status probes against the 'nr_gnb' container to isolate the data-plane drop. However, 'nr_gnb' is outside the managed Docker network and is rejected as an unknown container by both measure_rtt and get_network_status. While secondary evidence from the AMF shows the N2 control plane is still connected (gnb=1), there is no available tool to probe the N3 user-plane path from the gNB's perspective, making it impossible to confirm or contradict whether the gNB is dropping the packets.

**Probes executed (4):**
- **measure_rtt nr_gnb -> upf to triangulate packet loss on N3 path** ~ AMBIGUOUS
    - *Tool:* `measure_rtt("nr_gnb", "upf")`
    - *Observation:* [EVIDENCE: measure_rtt("nr_gnb", "upf") -> "Unknown source container 'nr_gnb'"]
    - *Comment:* Tool cannot execute because nr_gnb is not a recognized container within the test framework's managed network.
- **measure_rtt nr_gnb -> amf to isolate gNB stack** ~ AMBIGUOUS
    - *Tool:* `measure_rtt("nr_gnb", "amf")`
    - *Observation:* [EVIDENCE: measure_rtt("nr_gnb", "amf") -> "Unknown source container 'nr_gnb'"]
    - *Comment:* Tool cannot execute because nr_gnb is not recognized.
- **Check nr_gnb container status** ~ AMBIGUOUS
    - *Tool:* `get_network_status()`
    - *Observation:* [EVIDENCE: get_network_status() -> "running: [\n    \"mongo\",\n    \"nrf\",\n    \"scp\",\n    \"ausf\",\n    \"udr\",\n    \"udm\",\n    \"amf\",\n    \"smf\",\n    \"upf\",\n    \"pcf\",\n    \"dns\",\n    \"mysql\",\n    \"pyhss\",\n    \"icscf\",\n    \"scscf\",\n    \"pcscf\",\n    \"rtpengine\"\n  ]"]
    - *Comment:* nr_gnb is not tracked by the Docker network status tool, making its runtime state unobservable directly.
- **Check gNB liveness via AMF N2 metrics** ~ AMBIGUOUS
    - *Tool:* `get_diagnostic_metrics(at_time_ts=1779758571.823951, nfs=["amf"])`
    - *Observation:* [EVIDENCE: get_diagnostic_metrics(1779758571.82395, ["amf"]) -> "gnb = 1 [gauge, count]"]
    - *Comment:* AMF N2 metrics indicate the gNB control plane is up and UEs are attached, but this does not verify the health of the N3 data plane link.

### `h3` — ❌ **DISPROVEN**

**Hypothesis:** P-CSCF is the source of the SIP REGISTER rate drop due to an inbound partition, while the UPF N3 drop flags are artifacts of bucket (0,1) baseline pollution as per L03.

**Reasoning:** [Multi-shot consensus — both shots returned DISPROVEN.]

Shot 1: The hypothesis claims an inbound partition at P-CSCF is causing the SIP REGISTER drop. Network probes directly contradict this: both the UPF-to-PCSCF and PCSCF-to-ICSCF paths show 0% packet loss and <1ms latency, proving P-CSCF is fully reachable. Furthermore, P-CSCF's average register processing time remains healthy at 223.7 ms, confirming that REGISTERs arriving at the IMS are completing successfully. The drop in REGISTERs is caused by upstream starvation, indicating the UPF data-plane disruption is real.

Shot 2: Network path probes demonstrate 0% packet loss and normal RTT on both the UPF-to-PCSCF (Gm) and PCSCF-to-ICSCF (Mw) interfaces, directly refuting an inbound partition at the P-CSCF. Additionally, P-CSCF processing metrics show the average register time is well within healthy bounds, confirming arriving REGISTERs complete normally without stalling. The synchronized drop in both uplink and downlink UPF N3 GTP throughput points to a genuine upstream user-plane failure starving the IMS chain.

**Probes executed (3):**
- **measure_rtt upf -> pcscf_ip** ✗ CONTRADICTS
    - *Tool:* `measure_rtt("upf", "pcscf")`
    - *Observation:* [EVIDENCE: measure_rtt("upf", "pcscf") -> "0% packet loss... rtt min/avg/max/mdev = 0.055/0.097/0.422/0.046 ms"]
    - *Comment:* Zero packet loss and sub-millisecond latency on the Gm path completely refutes an inbound partition at P-CSCF.
- **measure_rtt pcscf -> icscf_ip** ✗ CONTRADICTS
    - *Tool:* `measure_rtt("pcscf", "icscf")`
    - *Observation:* [EVIDENCE: measure_rtt("pcscf", "icscf") -> "0% packet loss... rtt min/avg/max/mdev = 0.050/0.088/0.534/0.060 ms"]
    - *Comment:* Mw path is fully healthy, confirming P-CSCF network interfaces are functioning normally.
- **run_kamcmd('pcscf', 'stats.fetch script:register_time') to read pcscf.avg_register_time_ms** ✗ CONTRADICTS
    - *Tool:* `get_diagnostic_metrics(at_time_ts=1779758571.823951, nfs=["pcscf"])`
    - *Observation:* [EVIDENCE: get_diagnostic_metrics(at_time_ts=1779758571.823951, nfs=["pcscf"]) -> "derived.pcscf_avg_register_time_ms = 223.7 [derived, ms]... healthy_range = [150, 350]"]
    - *Comment:* The average register time is well within the healthy range (150-350ms), confirming P-CSCF is processing arriving REGISTERs normally, rather than stalling as hypothesized.

**Alternative suspects:** upf, nr_gnb

### `h_promoted_nr_gnb` — ❌ **DISPROVEN**

**Hypothesis:** nr_gnb is the source of the anomaly named in the alternative_suspects of the original verdict tree.

**Reasoning:** The hypothesis claiming nr_gnb as the root cause due to container failure or unreachability is disproven. Although the nr_gnb node could not be probed directly via measure_rtt because it runs outside the tracked Docker network, metric substitutions provide strong negative evidence against the hypothesis. AMF metrics report 'gnb = 1' and 'ran_ue = 2', confirming the N2 connection is active, UEs are attached, and the gNB is alive. UPF data plane gauges report incoming GTP-U traffic from N3 at 0.1 pps, proving the N3 path is operational. These strong positive confirmations of node and path liveness contradict the expected unreachability.

**Probes executed (3):**
- **Check the running status of the nr_gnb container.** ~ AMBIGUOUS
    - *Tool:* `get_network_status()`
    - *Observation:* [EVIDENCE: get_network_status() -> "\"down_or_absent\": []"]
    - *Comment:* The nr_gnb container is not listed in the Docker network status output, making this probe ambiguous on its own. However, AMF metrics later confirm it is active.
- **measure_rtt('upf', nr_gnb_ip) to test reachability on the N3 path.** ✗ CONTRADICTS
    - *Tool:* `get_dp_quality_gauges(at_time_ts=1779758571.82395, window_seconds=120)`
    - *Observation:* [EVIDENCE: get_dp_quality_gauges(at_time_ts=1779758571.82395, window_seconds=120) -> "in  packets/sec: 0.1"]
    - *Comment:* measure_rtt rejected nr_gnb as a container name. Substituted with UPF data plane gauges, which show active incoming N3 traffic (0.1 pps), proving the gNB is reachable and sending traffic.
- **measure_rtt('amf', nr_gnb_ip) to test reachability on the N2 path.** ✗ CONTRADICTS
    - *Tool:* `get_diagnostic_metrics(at_time_ts=1779758571.82395)`
    - *Observation:* [EVIDENCE: get_diagnostic_metrics(at_time_ts=1779758571.82395) -> "gnb = 1 [gauge, count]"]
    - *Comment:* measure_rtt rejected nr_gnb. Substituted with AMF metrics showing gnb=1 and ran_ue=2, definitively proving that gNB is alive and N2 connectivity is healthy.


## Evidence Validation (Phase 6)

**Overall verdict:** clean
**Overall confidence:** high

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 22 | 5/5 | clean | high |
| `InvestigatorAgent_h2` | 10 | 4/4 | clean | high |
| `InvestigatorAgent_h3` | 11 | 3/3 | clean | high |
| `InvestigatorAgent_h_promoted_nr_gnb` | 6 | 3/3 | clean | high |


## Ground Truth

**Failure domain:** data_plane  
**Protocol impact:** GTP-U  
**Affected components:** upf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v7-adk/pro=gemini-3.1-pro-preview+flash=gemini-3.5-flash  
**Time to diagnosis:** 898.7s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: Transport-layer fault localized to upf[eth0]: qdisc_tbf reports 329 packets dropped (191.3%).
> - **timeline**:
>     1. Path walk initiated on flow data_pdu_session_user_traffic.
>     2. Path walk attributed fault at hop 5 (upf[eth0]) to qdisc_tbf drops.
>     3. Path walk concluded with high confidence transport-layer localization.
> - **root_cause**: Kernel-level packet drop on upf's egress: tc tbf qdisc dropping 191.3% of packets. (primary_suspect_nf: `upf`)
> - **affected_components**:
>     - `?`: ?
> - **recommendation**: Inspect tc qdisc on upf: `docker exec upf tc -s qdisc show dev eth0`
> - **confidence**: high
> - **verdict_kind**: localized
> - **explanation**: The path walk localized a transport-layer fault along the data_pdu_session_user_traffic flow. Per-hop traversal:
> 
> | # | hop | kind | iface | prober | attribution |
> |---|-----|------|-------|--------|-------------|
> | 1 | e2e_ue1 | container | eth0 | KernelHopProber | clean |
> | 2 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 3 | nr_gnb | container | eth0 | KernelHopProber | clean |
> | 4 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 5 | upf | container | eth0 | KernelHopProber | drops_attributed_here (qdisc_tbf, 329 dropped, 191.3%) 🎯 |
> | 6 | internet | external_network | eth0 | <unregistered> | inconclusive (no_prober_registered) |
> | 7 | upf | container | eth0 | KernelHopProber | drops_attributed_here (qdisc_tbf, 329 dropped, 191.3%) |
> | 8 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 9 | nr_gnb | container | eth0 | KernelHopProber | clean |
> | 10 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 11 | e2e_ue1 | container | eth0 | KernelHopProber | clean |
> 
> Evidence for attribution at upf[eth0]:
> ```
> upf[eth0] qdisc=tbf: sent=172 dropped=329 (191.28%)
> ---tc -s qdisc show dev eth0---
> qdisc tbf 80c8: root refcnt 9 rate 100Kbit burst 1280b lat 400ms 
>  Sent 27346 bytes 172 pkt (dropped 329, overlimits 12 requeues 0) 
>  backlog 0b 0p requeues 0
> ```
> 
> Classifier rationale: label=mixed. Both transport-layer (2) and application-layer (1) signals are load-bearing. Path walk runs first; falls through to the application-layer pipeline if the walk produces null localization.
> Transport signals: normalized.upf.gtp_indatapktn3upf_per_ue (drop, score=4.59) — KB-labeled transport: core.upf.gtp_indatapktn3upf_per_ue (drop, score=4.59); normalized.upf.gtp_outdatapktn3upf_per_ue (drop, score=4.59) — KB-labeled transport: core.upf.gtp_outdatapktn3upf_per_ue (drop, score=4.59)
> Application signals: normalized.smf.bearers_per_ue (shift, score=0.01) — KB-labeled application: core.smf.bearers_per_ue (shift, score=0.01)
> Ambiguous signals: normalized.icscf.cdp_replies_per_ue (drop, score=4.59) — KB-labeled mixed: ims.icscf.cdp_replies_per_ue (drop, score=4.59); normalized.icscf.core:rcv_requests_register_per_ue (drop, score=4.59) — KB-labeled mixed: ims.icscf.rcv_requests_register_per_ue (drop, score=4.59); normalized.pcscf.core:rcv_requests_register_per_ue (drop, score=4.59) — KB-labeled mixed: ims.pcscf.rcv_requests_register_per_ue (drop, score=4.59); normalized.scscf.cdp_replies_per_ue (drop, score=4.59) — KB-labeled mixed: ims.scscf.cdp_replies_per_ue (drop, score=4.59); normalized.scscf.core:rcv_requests_register_per_ue (drop, score=4.59) — KB-labeled mixed: ims.scscf.rcv_requests_register_per_ue (drop, score=4.59)

### Scoring Breakdown

**Overall score: 80%**

**Scorer assessment:** The agent accurately diagnosed the exact root cause and fault type (UPF egress tc tbf drops) with high confidence, but failed to populate the affected_components list in its final output.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | Yes | The agent correctly identified that the root cause was a kernel-level packet drop on the UPF's egress interface (eth0) caused by a tc tbf qdisc, which perfectly matches the simulated bandwidth cap failure mode. |
| Component overlap | 0% | The agent failed to populate the 'affected_components' list in its final diagnosis, leaving it as a placeholder ('?': ?), so the UPF component was not correctly listed there. |
| Severity correct | Yes | The agent correctly identified the issue as a packet drop/degradation fault (reporting 329 dropped packets) rather than a complete container or node outage. |
| Fault type identified | Yes | The agent correctly identified the fault type as packet drops/loss at the transport layer (specifically via the tc tbf qdisc). |
| Layer accuracy | Yes | The agent correctly rated the 'core' layer as RED in its network analysis, which is the correct ontology layer for the UPF component. |
| Confidence calibrated | Yes | The agent expressed high confidence, which is fully justified given that it successfully localized the exact interface, qdisc type, and packet drop count. |

**Ranking position:** #1 — The correct root cause (UPF egress qdisc drops) was identified as the primary and only localized verdict.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 1,258,907 |
| Output tokens | 14,202 |
| Thinking tokens | 76,752 |
| **Total tokens** | **1,349,861** |

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
| NetworkAnalystAgent | 304,916 | 10 | 8 |
| Phase 3 NetworkAnalyst__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 19,043 | 0 | 1 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 16,782 | 0 | 1 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| InvestigatorAgent_h1 | 186,300 | 9 | 8 |
| InvestigatorAgent_h1 | 320,847 | 13 | 12 |
| InvestigatorAgent_h1__reconciliation | 0 | 0 | 0 |
| InvestigatorAgent_h2 | 139,811 | 10 | 8 |
| InvestigatorAgent_h2__reconciliation | 0 | 0 | 0 |
| InvestigatorAgent_h3 | 127,369 | 7 | 6 |
| InvestigatorAgent_h3 | 61,709 | 4 | 3 |
| InvestigatorAgent_h3__reconciliation | 0 | 0 | 0 |
| Phase5FanOutAudit | 0 | 0 | 0 |
| Phase6.5CandidatePool | 0 | 0 | 0 |
| InstructionGeneratorAgent | 13,310 | 0 | 1 |
| Phase 6.5 Reinvestigation IG__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 19,129 | 0 | 1 |
| Phase 6.5 Reinvestigation IG__guardrail | 0 | 0 | 0 |
| InvestigatorAgent_h_promoted_nr_gnb | 117,352 | 6 | 6 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 23,293 | 0 | 1 |
| Phase 7 Synthesis__guardrail | 0 | 0 | 0 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 1051.3s
