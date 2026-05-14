# Episode Report: Cascading IMS Failure

**Agent:** v7  
**Episode ID:** ep_20260514_213640_cascading_ims_failure  
**Date:** 2026-05-14T21:36:42.095136+00:00  
**Duration:** 396.5s  

---

## Scenario

**Category:** compound  
**Blast radius:** multi_nf  
**Description:** Kill PyHSS AND add 2-second latency to the S-CSCF. This simulates a cascading failure: the HSS is gone (no Diameter auth) AND the S-CSCF is degraded (slow SIP processing). Total IMS outage.

## Faults Injected

- **container_kill** on `pyhss`
- **network_latency** on `scscf` — {'delay_ms': 2000}

## Baseline (Pre-Fault)

Stack phase before injection: **ready**
All containers running at baseline.

## Fault Propagation Verification

**Verdict:** ✅ `confirmed`

- **Propagation window:** 138s (ObservationTrafficAgent drove traffic for this window; verifier added wait=0s on top)
- **Nodes with significant deltas:** 5
- **Nodes with any drift:** 5

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 50.56 (per-bucket threshold: 26.31, context bucket (0, 1), trained on 323 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following metrics deviate from their learned-healthy baseline. Treat each as a semantic observation (meaning + numbers), not a number alone — the KB's interpretation is the authoritative reading.

- **`context.cx_active`** — current **0.00** vs learned baseline **0.59** (MEDIUM, drop). *(No KB context available — interpret from the metric name.)*

- **`normalized.icscf.cdp_replies_per_ue`** (I-CSCF Diameter reply rate per UE) — current **0.00 replies_per_second_per_ue** vs learned baseline **0.03 replies_per_second_per_ue** (MEDIUM, drop)
    - **What it measures:** Liveness of the I-CSCF↔HSS Cx path. Drops to 0 when HSS is unreachable OR when no signaling is occurring at the I-CSCF (idle or upstream P-CSCF partitioned).
    - **Drop means:** No Cx replies in the window. Could be healthy idle OR a Cx-path fault.
    - **Healthy typical range:** 0–1 replies_per_second_per_ue

- **`normalized.icscf.core:rcv_requests_invite_per_ue`** (SIP INVITE rate per UE at I-CSCF) — current **0.03 requests_per_second** vs learned baseline **0.00 requests_per_second** (MEDIUM, spike)
    - **What it measures:** Health of call-setup forwarding P-CSCF → I-CSCF. Partition signature
same as REGISTER rate.
    - **Spike means:** Forwarding failure.
    - **Healthy typical range:** 0–0.2 requests_per_second
    - **Healthy invariant:** Per-UE rate. Tracks pcscf.invite rate.

- **`normalized.icscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at I-CSCF) — current **0.02 requests_per_second** vs learned baseline **0.06 requests_per_second** (MEDIUM, drop)
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

- **`normalized.pcscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at P-CSCF) — current **0.02 requests_per_second** vs learned baseline **0.06 requests_per_second** (MEDIUM, drop)
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

- **`normalized.scscf.core:rcv_requests_invite_per_ue`** (SIP INVITE rate per UE at S-CSCF) — current **0.04 requests_per_second** vs learned baseline **0.00 requests_per_second** (MEDIUM, spike)
    - **What it measures:** S-CSCF participation in call setup. Zero when calls aren't being
placed OR S-CSCF not receiving forwarded INVITEs.
    - **Spike means:** Upstream forwarding issue.
    - **Healthy typical range:** 0–0.2 requests_per_second
    - **Healthy invariant:** Per-UE rate.

- **`normalized.scscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at S-CSCF) — current **0.00 requests_per_second** vs learned baseline **0.06 requests_per_second** (MEDIUM, drop)
    - **What it measures:** Health of the I-CSCF → S-CSCF forwarding path. Drop to zero while
I-CSCF is receiving REGISTERs = S-CSCF-side issue (crashed, or
I-CSCF → S-CSCF path broken).
    - **Drop means:** S-CSCF isolated or not running.
    - **Healthy typical range:** 0–0.5 requests_per_second
    - **Healthy invariant:** Per-UE rate. Tracks icscf.register rate.

- **`normalized.upf.gtp_indatapktn3upf_per_ue`** (GTP-U uplink rate per UE (N3)) — current **0.08 packets_per_second** vs learned baseline **1.45 packets_per_second** (MEDIUM, drop)
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


## Symptom Classifier (Phase 0.5)

**Label:** `mixed`  
**Flag counts:** transport=1, application=0, ambiguous=9

### Transport-bucket flags (1)

| Metric | Direction | Score | KB-driven reason |
|---|---|---:|---|
| `normalized.upf.gtp_indatapktn3upf_per_ue` | drop | 4.59 | KB-labeled transport: core.upf.gtp_indatapktn3upf_per_ue (drop, score=4.59) |

### Ambiguous-bucket flags (9)

| Metric | Direction | Score | KB-driven reason |
|---|---|---:|---|
| `context.cx_active` | drop | 4.59 | no KB entry for context.cx_active — classification ambiguous |
| `normalized.icscf.cdp_replies_per_ue` | drop | 4.59 | KB-labeled mixed: ims.icscf.cdp_replies_per_ue (drop, score=4.59) |
| `normalized.icscf.core:rcv_requests_invite_per_ue` | spike | 4.59 | KB-labeled mixed: ims.icscf.rcv_requests_invite_per_ue (spike, score=4.59) |
| `normalized.icscf.core:rcv_requests_register_per_ue` | drop | 4.59 | KB-labeled mixed: ims.icscf.rcv_requests_register_per_ue (drop, score=4.59) |
| `normalized.pcscf.core:rcv_requests_invite_per_ue` | spike | 4.59 | KB-labeled mixed: ims.pcscf.rcv_requests_invite_per_ue (spike, score=4.59) |
| `normalized.pcscf.core:rcv_requests_register_per_ue` | drop | 4.59 | KB-labeled mixed: ims.pcscf.rcv_requests_register_per_ue (drop, score=4.59) |
| `normalized.scscf.cdp_replies_per_ue` | drop | 4.59 | KB-labeled mixed: ims.scscf.cdp_replies_per_ue (drop, score=4.59) |
| `normalized.scscf.core:rcv_requests_invite_per_ue` | spike | 4.59 | KB-labeled mixed: ims.scscf.rcv_requests_invite_per_ue (spike, score=4.59) |
| `normalized.scscf.core:rcv_requests_register_per_ue` | drop | 4.59 | KB-labeled mixed: ims.scscf.rcv_requests_register_per_ue (drop, score=4.59) |

**Rationale:**

```
label=mixed. 1 transport-layer signal(s) plus 9 ambiguous signal(s) clustering on a different NF-owner layer (transport on core; ambiguous cluster on ims (100%)). Treated as compound: walker plus application-layer pipeline both run; Synthesis merges into a single (potentially multi-root-cause) verdict. See ADR multi_fault_orchestration.md.

Transport signals: normalized.upf.gtp_indatapktn3upf_per_ue (drop, score=4.59) — KB-labeled transport: core.upf.gtp_indatapktn3upf_per_ue (drop, score=4.59)

Ambiguous signals: context.cx_active (drop, score=4.59) — no KB entry for context.cx_active — classification ambiguous; normalized.icscf.cdp_replies_per_ue (drop, score=4.59) — KB-labeled mixed: ims.icscf.cdp_replies_per_ue (drop, score=4.59); normalized.icscf.core:rcv_requests_invite_per_ue (spike, score=4.59) — KB-labeled mixed: ims.icscf.rcv_requests_invite_per_ue (spike, score=4.59); normalized.icscf.core:rcv_requests_register_per_ue (drop, score=4.59) — KB-labeled mixed: ims.icscf.rcv_requests_register_per_ue (drop, score=4.59); normalized.pcscf.core:rcv_requests_invite_per_ue (spike, score=4.59) — KB-labeled mixed: ims.pcscf.rcv_requests_invite_per_ue (spike, score=4.59) [+4 more]
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
Resolved transport path to flow `ims_registration` (score=8, 41 hops on the walk). Load-bearing components: ['context', 'icscf', 'pcscf', 'scscf', 'upf']. Other candidate flows considered: vonr_call_teardown=8, vonr_call_setup=8, data_pdu_session_user_traffic=7, vonr_media=7.
```

### Walker

**Status:** ✅ **localized**
**First attributed hop:** `?[?]`
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
| 16 | `pyhss` | container | `eth0` | `container_dead` | **container `exited`** |
| 17 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 18 | `icscf` | container | `eth0` | `clean` | _clean_ |
| 19 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 20 | `scscf` | container | `eth0` | `latency_at_hop` | `qdisc_netem_delay`: delay 2000.0 ms |
| 21 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 22 | `pyhss` | container | `eth0` | `container_dead` | **container `exited`** |
| 23 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 24 | `scscf` | container | `eth0` | `latency_at_hop` | `qdisc_netem_delay`: delay 2000.0 ms |
| 25 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 26 | `pyhss` | container | `eth0` | `container_dead` | **container `exited`** |
| 27 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 28 | `scscf` | container | `eth0` | `latency_at_hop` | `qdisc_netem_delay`: delay 2000.0 ms |
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

*Walker localized but synthesis returned None — defensive fall-through to app-layer pipeline.*

## Event Aggregation (Phase 1)

No events fired during this episode. Either no metric KB triggers matched, or the episode encountered no meaningful state transitions.

## Correlation Analysis (Phase 2)

No events fired — correlation engine had nothing to work with.

## RAG & Operational Lessons (Phase 2.5)

### RAG retrieval — prior similar episodes

**Status:** `hits` — hits=5, top_sim=0.95, top_case=v6/ep_20260430_014832_hss_unresponsive
**Index:** `/home/ehoskas/agentic-network-ops/rag_index`  **Corpus size:** 97 cases
**Classifier label used in retrieval:** `mixed`
**Retrieval params:** k=5, min_similarity=0.4
**Hits (5):**

| Rank | Sim | Case ID | Scenario | Ground truth | Primary suspect | Score |
|---:|---:|---|---|---|---|---:|
| 0 | 95% | `v6/ep_20260430_014832_hss_unresponsive` | HSS Unresponsive | `pyhss` | `?` | 95% |
| 1 | 90% | `v7/ep_20260510_194005_dns_failure` | DNS Failure | `dns` | `?` | 85% |
| 2 | 88% | `v7/ep_20260510_201356_cascading_ims_failure` | Cascading IMS Failure | `pyhss, scscf` | `?` | 100% |
| 3 | 86% | `v6/ep_20260429_164815_ims_network_partition` | IMS Network Partition | `pcscf` | `?` | 100% |
| 4 | 84% | `v7/ep_20260510_184035_p_cscf_packet_loss` | P-CSCF Packet Loss | `pcscf` | `?` | 100% |

*Rendered block injected into the NA prompt's `{prior_similar_episodes}` placeholder: 4367 chars. Source paths are inlined in the block so the EvidenceValidator can audit any case the NA cites.*

### Operational lessons — hand-authored rules corpus

**Status:** `injected` — lessons=15, chars=14426
**Path:** `/home/ehoskas/agentic-network-ops/agentic_ops_common/rag/lessons.yaml`  **Count:** 15  **Block size:** 14426 chars
**Injected lesson IDs:** `L01`, `L02`, `L03`, `L04`, `L05`, `L06`, `L07`, `L08`, `L09`, `L10`, `L11`, `L12`, `L13`, `L14`, `L15`

### NA citations of the injected content

**Cited lesson IDs:**
- `L03`
- `L10`

*Citations are verbatim string matches — case_ids and lesson_ids appear in the NA's emitted text (summary, hypothesis statements, or layer notes). The EvidenceValidator can audit any cited case by following its `source_episode_path` from the retrieval table above.*

## Network Analysis (Phase 3)

**Summary:** The HSS container (pyhss) has exited, causing a complete failure of the Cx interface which has halted all IMS registration and call setup procedures throughout the network.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | No evidence of a general infrastructure issue like DNS or underlying network connectivity between running components. |
| **ran** | 🟢 GREEN | No metrics directly indicate a RAN-layer fault. |
| **core** | 🟡 YELLOW | The UPF GTP drop is likely a downstream effect of no calls being established, rather than a data plane fault itself, as per Operational Lesson L03. The core network appears to be impacted as a consequence of the IMS failure. |
| **ims** | 🔴 RED | The primary failure is the HSS container exiting. All other IMS metrics are downstream symptoms of this root cause, consistent with Operational Lesson L10. The IMS signaling plane is non-functional. |

**CORE evidence:**
- normalized.upf.gtp_indatapktn3upf_per_ue dropped.

**IMS evidence:**
- get_network_status shows pyhss has exited.
- get_network_topology shows HSS is exited and Cx links are INACTIVE.
- normalized.icscf.cdp_replies_per_ue dropped to 0.
- normalized.scscf.cdp_replies_per_ue dropped to 0.
- normalized.icscf.core:rcv_requests_register_per_ue dropped to 0.
- normalized.scscf.core:rcv_requests_register_per_ue dropped to 0.

**Ranked hypotheses:**

- **`h1`** (fit=1.00, nf=pyhss, specificity=specific):
    - **Statement:** The HSS container (pyhss) is the source of the failure; it has exited, leading to the observed IMS-wide outage.
    - **Falsification probes:**
        - Check the container status of 'pyhss'; if it is 'running', this hypothesis is false.
        - Attempt to query the HSS from the I-CSCF or S-CSCF via a Diameter tool; if a successful response is received, this hypothesis is false.


## Falsification Plans (Phase 4)

**1 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `pyhss`)

**Hypothesis:** The HSS container (pyhss) is the source of the failure; it has exited, leading to the observed IMS-wide outage.

**Probes (3):**
1. **`get_network_status`** — Check the running status of the 'pyhss' container.
    - *Expected if hypothesis holds:* The status for the 'pyhss' container is 'exited' or another non-running state.
    - *Falsifying observation:* The status for the 'pyhss' container is 'running'.
2. **`measure_rtt`** — From the 'icscf' container to the 'pyhss' container.
    - *Expected if hypothesis holds:* The probe reports 100% packet loss or a failure to resolve the host.
    - *Falsifying observation:* The probe measures a successful round-trip time, indicating that 'pyhss' is reachable from 'icscf'.
3. **`measure_rtt`** — From the 'icscf' container to the 'pcscf' container, which is expected to be healthy.
    - *Expected if hypothesis holds:* The probe measures a successful round-trip time, indicating the 'icscf' networking stack is functional.
    - *Falsifying observation:* The probe reports 100% packet loss or a failure to resolve the host, suggesting the fault may lie with 'icscf' or the broader network.

*Notes:* This plan tests the hypothesis directly by checking container status, and then verifies connectivity from a dependent component (icscf) as described in the 'ims_registration' flow, step 4 (UAR). The partner probe to 'pcscf' is to disambiguate between a 'pyhss' failure and a broader network or 'icscf' failure.


## Parallel Investigators (Phase 5)

**1 sub-Investigator verdict(s):** **1 NOT_DISPROVEN**

### `h1` — ✅ **NOT_DISPROVEN**

**Hypothesis:** The HSS container (pyhss) is the source of the failure; it has exited, leading to the observed IMS-wide outage.

**Reasoning:** [Multi-shot consensus — both shots returned NOT_DISPROVEN.]

Shot 1: All executed probes produced results that are consistent with the hypothesis. The 'pyhss' container was confirmed to be in an 'exited' state. Subsequent connectivity tests showed it was unreachable from a dependent container ('icscf'), while that same container had no issue reaching other healthy containers, effectively isolating the failure point to 'pyhss'.

Shot 2: All probes consistently indicated that the 'pyhss' container is the source of the failure. The container status is 'exited', and it is unreachable from 'icscf', while a control probe from 'icscf' to another container ('pcscf') was successful, ruling out a networking issue on the 'icscf' side.

**Probes executed (3):**
- **Check the running status of the 'pyhss' container.** ✓ CONSISTENT
    - *Tool:* `print(default_api.get_network_status())`
    - *Observation:* [EVIDENCE: get_network_status() -> "'pyhss': 'exited'"]
    - *Comment:* The container status for 'pyhss' is 'exited', which directly supports the hypothesis.
- **From the 'icscf' container to the 'pyhss' container.** ✓ CONSISTENT
    - *Tool:* `print(default_api.measure_rtt(container='icscf', target='pyhss'))`
    - *Observation:* [EVIDENCE: measure_rtt('icscf', 'pyhss') -> "Ping failed from 'icscf' to 'pyhss': ping: pyhss: Name or service not known"]
    - *Comment:* The 'pyhss' container is not resolvable on the network, which is expected for an exited container. This confirms it is unreachable.
- **From the 'icscf' container to the 'pcscf' container, which is expected to be healthy.** ✓ CONSISTENT
    - *Tool:* `print(default_api.measure_rtt(container='icscf', target='pcscf'))`
    - *Observation:* [EVIDENCE: measure_rtt('icscf', 'pcscf') -> "66 packets transmitted, 66 received, 0% packet loss"]
    - *Comment:* The successful RTT measurement to a healthy container ('pcscf') indicates that the networking stack of the 'icscf' container is functional. This triangulates the problem to 'pyhss' itself, rather than a broader network issue.


## Evidence Validation (Phase 6)

**Overall verdict:** clean
**Overall confidence:** high

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 6 | 3/3 | clean | high |


## Ground Truth

**Failure domain:** ims_signaling  
**Protocol impact:** SIP  
**Affected components:** pyhss, scscf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v7-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 242.1s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: Compound IMS outage: The HSS container (pyhss) has exited AND the S-CSCF container (scscf) has a 2000ms egress delay on eth0.
> - **timeline**:
>     1. IMS registration flow begins to fail.
>     2. Transport-layer pipeline is initiated, starting a path walk for the `ims_registration` flow.
>     3. At hop #17, the path walk attributes the failure to the 'pyhss' container, which is in an 'exited' state.
>     4. At hop #21, the path walk attributes a 2000ms latency to the 'scscf' container's egress interface.
>     5. The application-layer pipeline is initiated due to mixed-layer signals.
>     6. The Network Analyst hypothesizes the `pyhss` container has exited.
>     7. The Investigator confirms the 'pyhss' container is in an 'exited' state and is unreachable on the network.
> - **root_cause**: Two distinct faults were identified: the HSS service is down as its container 'pyhss' has exited, and significant packet delay of 2000ms is being injected on the egress of the 'scscf' container via a kernel-level `tc netem` qdisc. (primary_suspect_nf: `pyhss`)
> - **affected_components**:
>     - `pyhss`: Root Cause
>     - `scscf`: Root Cause
>     - `icscf`: Symptomatic
>     - `pcscf`: Symptomatic
> - **recommendation**: Verify the status of the 'pyhss' container and inspect its logs: `docker ps -a | grep pyhss`; Inspect the active traffic control settings on the 'scscf' container's eth0 interface: `docker exec scscf tc -s qdisc show dev eth0`.
> - **confidence**: high
> - **verdict_kind**: compound
> - **additional_root_causes**:
>     - `scscf` (transport, source=`path_walk`, confidence=high): Path walk attributed latency at hop scscf[eth0]: 2000ms delay from qdisc_netem_delay.
> - **explanation**: This is a compound failure with two distinct root causes identified across the IMS and transport layers. Both the transport-layer path walk and the application-layer investigation concluded that the HSS container ('pyhss') is non-functional. The path walk pinpointed this as the first point of failure, as the container was in an 'exited' state.
> 
> Path-walk bisection report for primary root cause (pyhss):
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
> | 13 | pcscf | container | eth0 | KernelHopProber | clean |
> | 14 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 15 | icscf | container | eth0 | KernelHopProber | clean |
> | 16 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 17 | pyhss | container | eth0 | KernelHopProber | container_dead (status=exited) 🎯 |
> 
> Evidence for `pyhss` attribution:
> ```
> - `attribution_kind`: `container_dead`  
> - `status`: `exited`  `detail`: container 'pyhss' state is `exited` (expected `running`); probes cannot execute against a non-running container
> ```
> 
> Additionally, the same path walk identified a second, independent fault: a 2000ms packet delay injected on the egress of the 'scscf' container. This was flagged as `latency_at_hop` with a `qdisc_netem_delay` counter, indicating an intentional traffic control rule is in place. While the 'pyhss' failure is sufficient to break IMS registration, the 'scscf' latency would severely impact or time-out any successful connections, representing a second distinct root cause.

### Scoring Breakdown

**Overall score: 100%**

**Scorer assessment:** The agent provided an excellent and highly accurate diagnosis, correctly identifying both root causes, their affected components, severity, and fault types, with appropriate confidence and layer attribution.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | Yes | The agent correctly identified both simulated failure modes as root causes: 'pyhss' being down/exited and 'scscf' experiencing 2000ms packet delay. It even correctly identified the 'tc netem' mechanism for the latency, which is more specific than required but accurate. |
| Component overlap | 100% | Both primary affected components, 'pyhss' and 'scscf', were correctly identified and labeled as 'Root Cause' in the `affected_components` list. |
| Severity correct | Yes | The agent correctly identified 'pyhss' as 'exited' (complete outage) and 'scscf' as having '2000ms delay' (degradation), matching the simulated severities and expected total IMS outage. |
| Fault type identified | Yes | The agent identified 'container exited' for 'pyhss' (implying unreachable/down) and 'packet delay' for 'scscf' (a type of network degradation), which are correct observable fault types. |
| Layer accuracy | Yes | The agent's network analysis correctly attributed the failure to the 'ims' layer, rating it 'red' and providing evidence related to 'pyhss' and 'scscf', both of which belong to the IMS layer. |
| Confidence calibrated | Yes | The agent's diagnosis is highly accurate and detailed, correctly identifying all aspects of the simulated failure. A 'high' confidence level is appropriate. |

**Ranking position:** #1 — The agent identified two distinct root causes. 'pyhss' is mentioned first in the `root_cause` summary and explicitly as the `primary_suspect_nf`. Both identified root causes are correct, so the first one mentioned is in position 1.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 157,661 |
| Output tokens | 4,631 |
| Thinking tokens | 13,223 |
| **Total tokens** | **175,515** |

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
| NetworkAnalystAgent | 41,338 | 3 | 2 |
| Phase 3 NetworkAnalyst__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 19,203 | 1 | 2 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 21,787 | 1 | 2 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| InvestigatorAgent_h1 | 51,814 | 3 | 4 |
| InvestigatorAgent_h1 | 27,597 | 3 | 2 |
| InvestigatorAgent_h1__reconciliation | 0 | 0 | 0 |
| Phase5FanOutAudit | 0 | 0 | 0 |
| Phase6.5CandidatePool | 0 | 0 | 0 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 13,776 | 0 | 1 |
| Phase 7 Synthesis__guardrail | 0 | 0 | 0 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 396.5s
