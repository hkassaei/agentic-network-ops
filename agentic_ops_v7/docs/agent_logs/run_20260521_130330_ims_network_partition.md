# Episode Report: IMS Network Partition

**Agent:** v7  
**Episode ID:** ep_20260521_125444_ims_network_partition  
**Date:** 2026-05-21T12:54:46.002666+00:00  
**Duration:** 523.5s  

---

## Scenario

**Category:** network  
**Blast radius:** multi_nf  
**Description:** Partition the P-CSCF from both the I-CSCF and S-CSCF using iptables DROP rules. SIP signaling between the edge proxy and the core IMS is completely severed. Tests IMS behavior under a network split.

## Faults Injected

- **network_partition** on `pcscf` — {'target_ip': '172.22.0.19'}
- **network_partition** on `pcscf` — {'target_ip': '172.22.0.20'}

## Baseline (Pre-Fault)

Stack phase before injection: **ready**
All containers running at baseline.

## Fault Propagation Verification

**Verdict:** ✅ `confirmed`

- **Propagation window:** 137s (ObservationTrafficAgent drove traffic for this window; verifier added wait=0s on top)
- **Nodes with significant deltas:** 2
- **Nodes with any drift:** 3

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 44.85 (per-bucket threshold: 26.31, context bucket (0, 1), trained on 323 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

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

- **`normalized.pcscf.core:rcv_requests_invite_per_ue`** (SIP INVITE rate per UE at P-CSCF) — current **0.01 requests_per_second** vs learned baseline **0.00 requests_per_second** (MEDIUM, spike)
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

- **`normalized.smf.bearers_per_ue`** (Active QoS bearers per UE) — current **3.50 count** vs learned baseline **2.48 count** (MEDIUM, shift)
    - **What it measures:** Per-UE count of active QoS bearers. Baseline reflects default
bearers; increments during VoNR calls indicate dedicated voice
bearers being set up. Drop during an active call = dedicated
bearer torn down unexpectedly (voice will fail).
    - **Shift means:** Expected during VoNR calls (1 extra bearer per active call).
    - **Healthy typical range:** 2–3.5 count
    - **Healthy invariant:** At rest: equals configured default bearers (typically 2 per UE).
During active VoNR call: +1 per caller. The per-UE ratio is the
invariant; absolute count scales with UE pool.

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

- **`normalized.upf.gtp_outdatapktn3upf_per_ue`** (GTP-U downlink rate per UE (N3)) — current **0.06 packets_per_second** vs learned baseline **1.45 packets_per_second** (LOW, drop)
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


## Symptom Classifier (Phase 0.5)

**Label:** `mixed`  
**Flag counts:** transport=2, application=1, ambiguous=7

### Transport-bucket flags (2)

| Metric | Direction | Score | KB-driven reason |
|---|---|---:|---|
| `normalized.upf.gtp_indatapktn3upf_per_ue` | drop | 4.59 | KB-labeled transport: core.upf.gtp_indatapktn3upf_per_ue (drop, score=4.59) |
| `normalized.upf.gtp_outdatapktn3upf_per_ue` | drop | 3.50 | KB-labeled transport: core.upf.gtp_outdatapktn3upf_per_ue (drop, score=3.50) |

### Application-bucket flags (1)

| Metric | Direction | Score | KB-driven reason |
|---|---|---:|---|
| `normalized.smf.bearers_per_ue` | shift | 4.59 | KB-labeled application: core.smf.bearers_per_ue (shift, score=4.59) |

### Ambiguous-bucket flags (7)

| Metric | Direction | Score | KB-driven reason |
|---|---|---:|---|
| `context.cx_active` | drop | 4.59 | no KB entry for context.cx_active — classification ambiguous |
| `normalized.icscf.cdp_replies_per_ue` | drop | 4.59 | KB-labeled mixed: ims.icscf.cdp_replies_per_ue (drop, score=4.59) |
| `normalized.icscf.core:rcv_requests_register_per_ue` | drop | 4.59 | KB-labeled mixed: ims.icscf.rcv_requests_register_per_ue (drop, score=4.59) |
| `normalized.pcscf.core:rcv_requests_invite_per_ue` | spike | 4.59 | KB-labeled mixed: ims.pcscf.rcv_requests_invite_per_ue (spike, score=4.59) |
| `normalized.pcscf.core:rcv_requests_register_per_ue` | drop | 4.59 | KB-labeled mixed: ims.pcscf.rcv_requests_register_per_ue (drop, score=4.59) |
| `normalized.scscf.cdp_replies_per_ue` | drop | 4.59 | KB-labeled mixed: ims.scscf.cdp_replies_per_ue (drop, score=4.59) |
| `normalized.scscf.core:rcv_requests_register_per_ue` | drop | 4.59 | KB-labeled mixed: ims.scscf.rcv_requests_register_per_ue (drop, score=4.59) |

**Rationale:**

```
label=mixed. Both transport-layer (2) and application-layer (1) signals are load-bearing. Path walk runs first; falls through to the application-layer pipeline if the walk produces null localization.

Transport signals: normalized.upf.gtp_indatapktn3upf_per_ue (drop, score=4.59) — KB-labeled transport: core.upf.gtp_indatapktn3upf_per_ue (drop, score=4.59); normalized.upf.gtp_outdatapktn3upf_per_ue (drop, score=3.50) — KB-labeled transport: core.upf.gtp_outdatapktn3upf_per_ue (drop, score=3.50)

Application signals: normalized.smf.bearers_per_ue (shift, score=4.59) — KB-labeled application: core.smf.bearers_per_ue (shift, score=4.59)

Ambiguous signals: context.cx_active (drop, score=4.59) — no KB entry for context.cx_active — classification ambiguous; normalized.icscf.cdp_replies_per_ue (drop, score=4.59) — KB-labeled mixed: ims.icscf.cdp_replies_per_ue (drop, score=4.59); normalized.icscf.core:rcv_requests_register_per_ue (drop, score=4.59) — KB-labeled mixed: ims.icscf.rcv_requests_register_per_ue (drop, score=4.59); normalized.pcscf.core:rcv_requests_invite_per_ue (spike, score=4.59) — KB-labeled mixed: ims.pcscf.rcv_requests_invite_per_ue (spike, score=4.59); normalized.pcscf.core:rcv_requests_register_per_ue (drop, score=4.59) — KB-labeled mixed: ims.pcscf.rcv_requests_register_per_ue (drop, score=4.59) [+2 more]
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

**Status:** `hits` — hits=5, top_sim=0.94, top_case=v7/ep_20260510_194005_dns_failure
**Index:** `/home/ehoskas/agentic-network-ops/rag_index`  **Corpus size:** 102 cases
**Classifier label used in retrieval:** `mixed`
**Retrieval params:** k=5, min_similarity=0.4
**Hits (5):**

| Rank | Sim | Case ID | Scenario | Ground truth | Primary suspect | Score |
|---:|---:|---|---|---|---|---:|
| 0 | 94% | `v7/ep_20260510_194005_dns_failure` | DNS Failure | `dns` | `dns` | 85% |
| 1 | 90% | `v6/ep_20260429_164815_ims_network_partition` | IMS Network Partition | `pcscf` | `pcscf` | 100% |
| 2 | 90% | `v6/ep_20260430_014832_hss_unresponsive` | HSS Unresponsive | `pyhss` | `pyhss` | 95% |
| 3 | 89% | `v7/ep_20260514_213640_cascading_ims_failure` | Cascading IMS Failure | `pyhss, scscf` | `pyhss` | 100% |
| 4 | 85% | `v6/ep_20260430_020852_dns_failure` | DNS Failure | `dns` | `dns` | 100% |

*Rendered block injected into the NA prompt's `{prior_similar_episodes}` placeholder: 4635 chars. Source paths are inlined in the block so the EvidenceValidator can audit any case the NA cites.*

### Operational lessons — hand-authored rules corpus

**Status:** `injected` — lessons=16, chars=15678
**Path:** `/home/ehoskas/agentic-network-ops/agentic_ops_common/rag/lessons.yaml`  **Count:** 16  **Block size:** 15678 chars
**Injected lesson IDs:** `L01`, `L02`, `L03`, `L04`, `L05`, `L06`, `L07`, `L08`, `L09`, `L10`, `L11`, `L12`, `L13`, `L14`, `L15`, `L16`

### NA citations of the injected content

**Cited lesson IDs:**
- `L03`
- `L09`

*Citations are verbatim string matches — case_ids and lesson_ids appear in the NA's emitted text (summary, hypothesis statements, or layer notes). The EvidenceValidator can audit any cited case by following its `source_episode_path` from the retrieval table above.*

## Network Analysis (Phase 3)

**Summary:** Following L09 and matching prior case ep_20260429_164815_ims_network_partition, pcscf is the source of a network partition isolating it from the IMS core, completely starving downstream I-CSCF/S-CSCF signaling, while UPF drops are demoted as bucket (0,1) noise per L03.

**Ranked hypotheses:**

- **`h1`** (fit=0.95, nf=pcscf, specificity=specific):
    - **Statement:** pcscf is the source of the 100% packet loss toward I-CSCF and S-CSCF, which causes the observed downstream registration drops and upstream INVITE spikes.
    - **Falsification probes:**
        - measure_rtt from pcscf to icscf to confirm 100% loss on the Mw path
        - measure_rtt from pcscf to scscf to confirm 100% loss on the Mw path
        - measure_rtt from icscf to scscf to confirm the rest of the IMS subnet is healthy
- **`h2`** (fit=0.30, nf=icscf, specificity=moderate):
    - **Statement:** icscf is the source of the 100% packet loss affecting traffic arriving from P-CSCF, starving the downstream IMS core.
    - **Falsification probes:**
        - measure_rtt from pcscf to scscf to test if the partition is specific to icscf or affects all pcscf outbound core traffic


## Falsification Plans (Phase 4)

**2 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `pcscf`)

**Hypothesis:** pcscf is the source of the 100% packet loss toward I-CSCF and S-CSCF, which causes the observed downstream registration drops and upstream INVITE spikes.

**Probes (3):**
1. **`measure_rtt`** — from pcscf to icscf
    - *Expected if hypothesis holds:* 100% packet loss
    - *Falsifying observation:* 0% packet loss
2. **`measure_rtt`** — from pcscf to scscf
    - *Expected if hypothesis holds:* 100% packet loss
    - *Falsifying observation:* 0% packet loss
3. **`measure_rtt`** — from icscf to scscf
    - *Expected if hypothesis holds:* 0% packet loss
    - *Falsifying observation:* 100% packet loss

*Notes:* Triangulating P-CSCF isolation using ping tests between IMS core components.

### Plan for `h2` (target: `icscf`)

**Hypothesis:** icscf is the source of the 100% packet loss affecting traffic arriving from P-CSCF, starving the downstream IMS core.

**Probes (3):**
1. **`measure_rtt`** — from pcscf to icscf
    - *Expected if hypothesis holds:* 100% packet loss
    - *Falsifying observation:* 0% packet loss
2. **`measure_rtt`** — from pcscf to scscf
    - *Expected if hypothesis holds:* 0% packet loss
    - *Falsifying observation:* 100% packet loss
3. **`measure_rtt`** — from scscf to icscf
    - *Expected if hypothesis holds:* 100% packet loss
    - *Falsifying observation:* 0% packet loss

*Notes:* Testing I-CSCF specific isolation from the rest of the IMS core.


## Parallel Investigators (Phase 5)

**2 sub-Investigator verdict(s):** **1 NOT_DISPROVEN**, **1 DISPROVEN**

### `h1` — ✅ **NOT_DISPROVEN**

**Hypothesis:** pcscf is the source of the 100% packet loss toward I-CSCF and S-CSCF, which causes the observed downstream registration drops and upstream INVITE spikes.

**Reasoning:** [Multi-shot consensus — both shots returned NOT_DISPROVEN.]

Shot 1: Triangulating ping tests confirmed a network partition isolating the P-CSCF from the IMS core. Probes from pcscf to both icscf and scscf resulted in 100% packet loss, whereas a probe from icscf to scscf showed 0% loss, localizing the partition specifically to P-CSCF's network paths. Additionally, checking container health confirmed that I-CSCF and S-CSCF are running, ruling out node failures as the source of the packet loss.

Shot 2: The probes confirm that pcscf is experiencing 100% packet loss when attempting to reach both icscf and scscf. Meanwhile, the path between icscf and scscf remains healthy with 0% packet loss, confirming the isolation is specific to pcscf and neither icscf nor scscf is down.

**Probes executed (4):**
- **measure_rtt from pcscf to icscf** ✓ CONSISTENT
    - *Tool:* `measure_rtt("pcscf", "icscf")`
    - *Observation:* [EVIDENCE: measure_rtt("pcscf", "icscf") -> "66 packets transmitted, 0 received, 100% packet loss"]
    - *Comment:* 100% packet loss observed from P-CSCF to I-CSCF, consistent with P-CSCF being partitioned from the core.
- **measure_rtt from pcscf to scscf** ✓ CONSISTENT
    - *Tool:* `measure_rtt("pcscf", "scscf")`
    - *Observation:* [EVIDENCE: measure_rtt("pcscf", "scscf") -> "66 packets transmitted, 0 received, 100% packet loss"]
    - *Comment:* 100% packet loss observed from P-CSCF to S-CSCF, confirming P-CSCF isolation extends across the IMS core nodes.
- **measure_rtt from icscf to scscf** ✓ CONSISTENT
    - *Tool:* `measure_rtt("icscf", "scscf")`
    - *Observation:* [EVIDENCE: measure_rtt("icscf", "scscf") -> "66 packets transmitted, 66 received, 0% packet loss"]
    - *Comment:* 0% packet loss between I-CSCF and S-CSCF, proving that the rest of the IMS core is mutually reachable and the issue is uniquely tied to P-CSCF.
- **get_network_status to check container health** ✓ CONSISTENT
    - *Tool:* `get_network_status()`
    - *Observation:* [EVIDENCE: get_network_status() -> ""icscf": "running", "scscf": "running", "pcscf": "running""]
    - *Comment:* All relevant containers are running, successfully ruling out the conflating possibilities that the I-CSCF or S-CSCF nodes are down.

### `h2` — ❌ **DISPROVEN**

**Hypothesis:** icscf is the source of the 100% packet loss affecting traffic arriving from P-CSCF, starving the downstream IMS core.

**Reasoning:** [Multi-shot consensus — both shots returned DISPROVEN.]

Shot 1: The hypothesis claims that I-CSCF is the source of the packet loss isolating it from P-CSCF. However, probes reveal that I-CSCF is perfectly reachable from S-CSCF (0% loss), meaning I-CSCF is healthy and connected to the network. Meanwhile, P-CSCF experiences 100% packet loss when attempting to reach both I-CSCF and S-CSCF. This confirms the network partition is anchored at P-CSCF itself rather than I-CSCF, refuting the hypothesis.

Shot 2: The hypothesis suggests I-CSCF is the source of the fault isolating it from P-CSCF. However, triangulation probes reveal that P-CSCF is unreachable from both I-CSCF and S-CSCF, while I-CSCF and S-CSCF can communicate with each other with 0% packet loss. This proves the network partition is anchored at P-CSCF, entirely clearing I-CSCF as the source.

**Probes executed (3):**
- **from pcscf to icscf** ✓ CONSISTENT
    - *Tool:* `measure_rtt("pcscf", "icscf")`
    - *Observation:* [EVIDENCE: measure_rtt("pcscf", "icscf") -> "66 packets transmitted, 0 received, 100% packet loss"]
    - *Comment:* Confirms the 100% packet loss exists on the path between P-CSCF and I-CSCF, but does not isolate which node is at fault.
- **from pcscf to scscf** ✗ CONTRADICTS
    - *Tool:* `measure_rtt("pcscf", "scscf")`
    - *Observation:* [EVIDENCE: measure_rtt("pcscf", "scscf") -> "66 packets transmitted, 0 received, 100% packet loss"]
    - *Comment:* P-CSCF is unable to reach S-CSCF either. If I-CSCF were the sole source of the partition, P-CSCF would still be able to communicate with other IMS core elements like S-CSCF.
- **from scscf to icscf** ✗ CONTRADICTS
    - *Tool:* `measure_rtt("scscf", "icscf")`
    - *Observation:* [EVIDENCE: measure_rtt("scscf", "icscf") -> "66 packets transmitted, 66 received, 0% packet loss"]
    - *Comment:* I-CSCF is reachable from the rest of the IMS core. This proves that I-CSCF is not partitioned from the network.

**Alternative suspects:** pcscf


## Evidence Validation (Phase 6)

**Overall verdict:** clean
**Overall confidence:** high

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 8 | 4/4 | clean | high |
| `InvestigatorAgent_h2` | 7 | 3/3 | clean | high |


## Ground Truth

**Failure domain:** ims_signaling  
**Protocol impact:** SIP  
**Affected components:** pcscf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v7-adk/pro=gemini-3.1-pro-preview+flash=gemini-3.5-flash  
**Time to diagnosis:** 375.0s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: P-CSCF is isolated from the IMS core due to a network partition, causing 100% packet loss to I-CSCF and S-CSCF.
> - **timeline**:
>     1. Downstream registration drops and upstream INVITE spikes observed.
>     2. Probes executed from pcscf to icscf and scscf observed 100% packet loss.
>     3. Control probe from icscf to scscf observed 0% packet loss.
>     4. Container health checks verified that all relevant IMS nodes (pcscf, icscf, scscf) are running.
>     5. Fault isolated to P-CSCF's network path, confirming hypothesis h1 and disproving h2.
> - **root_cause**: A network partition anchored at P-CSCF is completely dropping outbound traffic toward the IMS core. (primary_suspect_nf: `pcscf`)
> - **affected_components**:
>     - `pcscf`: Root Cause
>     - `icscf`: Symptomatic
>     - `scscf`: Symptomatic
> - **recommendation**: Investigate P-CSCF's network interfaces, routing tables, and firewall rules to determine the cause of the outbound packet loss.
> - **confidence**: high
> - **verdict_kind**: confirmed
> - **explanation**: Triangulating ping tests confirmed a network partition isolating the P-CSCF from the IMS core. Probes from pcscf to both icscf and scscf resulted in 100% packet loss. A control probe from icscf to scscf showed 0% loss, localizing the partition specifically to P-CSCF's network paths and proving that the rest of the IMS subnet is healthy. Container health checks confirmed that all IMS core nodes are running, successfully ruling out container crashes. The alternative hypothesis blaming I-CSCF (h2) was definitively disproven because I-CSCF remains reachable from S-CSCF, leaving P-CSCF as the confirmed root cause.

### Scoring Breakdown

**Overall score: 96%**

**Scorer assessment:** The agent accurately diagnosed the P-CSCF network partition with high confidence and correct component attribution.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | Yes | The agent correctly identified the network partition isolating the P-CSCF from the IMS core. |
| Component overlap | 80% | P-CSCF was correctly identified as the primary root cause component. |
| Severity correct | Yes | The agent correctly assessed the severity as a complete network partition with 100% packet loss. |
| Fault type identified | Yes | The agent correctly identified the fault type as a network partition. |
| Layer accuracy | Yes | No layer status was provided, so no misattribution occurred. |
| Confidence calibrated | Yes | High confidence is justified by the diagnostic evidence. |

**Ranking position:** #1 — The correct cause was ranked first.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 508,339 |
| Output tokens | 6,575 |
| Thinking tokens | 24,323 |
| **Total tokens** | **539,237** |

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
| NetworkAnalystAgent | 319,902 | 17 | 8 |
| Phase 3 NetworkAnalyst__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 13,347 | 0 | 1 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 14,962 | 0 | 1 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| InvestigatorAgent_h1 | 46,711 | 5 | 3 |
| InvestigatorAgent_h1 | 28,744 | 3 | 2 |
| InvestigatorAgent_h1__reconciliation | 0 | 0 | 0 |
| InvestigatorAgent_h2 | 73,362 | 4 | 5 |
| InvestigatorAgent_h2 | 29,771 | 3 | 2 |
| InvestigatorAgent_h2__reconciliation | 0 | 0 | 0 |
| Phase5FanOutAudit | 0 | 0 | 0 |
| Phase6.5CandidatePool | 0 | 0 | 0 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 12,438 | 0 | 1 |
| Phase 7 Synthesis__guardrail | 0 | 0 | 0 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 523.5s
