# Episode Report: HSS Unresponsive

**Agent:** v7  
**Episode ID:** ep_20260521_022733_hss_unresponsive  
**Date:** 2026-05-21T02:27:34.980693+00:00  
**Duration:** 525.1s  

---

## Scenario

**Category:** network  
**Blast radius:** single_nf  
**Description:** Inject 60-second outbound delay on the HSS (PyHSS), making it functionally unreachable for all real-time protocols. The HSS container is running and the process is alive, but all network responses are delayed by 60 seconds — far exceeding Diameter Cx timeouts (5-30s) and standard probe timeouts (10s). From the perspective of diagnostic tools and IMS peers, the HSS appears completely unresponsive or unreachable.

## Faults Injected

- **network_latency** on `pyhss` — {'delay_ms': 60000, 'jitter_ms': 0}

## Baseline (Pre-Fault)

Stack phase before injection: **ready**
All containers running at baseline.

## Fault Propagation Verification

**Verdict:** ✅ `confirmed`

- **Propagation window:** 122s (ObservationTrafficAgent drove traffic for this window; verifier added wait=0s on top)
- **Nodes with significant deltas:** 4
- **Nodes with any drift:** 5

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 51.97 (per-bucket threshold: 26.31, context bucket (0, 1), trained on 323 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following metrics deviate from their learned-healthy baseline. Treat each as a semantic observation (meaning + numbers), not a number alone — the KB's interpretation is the authoritative reading.

- **`context.cx_active`** — current **0.00** vs learned baseline **0.59** (MEDIUM, drop). *(No KB context available — interpret from the metric name.)*

- **`derived.icscf_lir_timeout_ratio`** (I-CSCF LIR timeout ratio) — current **1.00 ratio** vs learned baseline **0.00 ratio** (MEDIUM, spike)
    - **What it measures:** Partial partition or severe overload on the Cx path during call routing. Zero in healthy operation; non-zero means some LIR queries did not receive a response within the timeout window.
    - **Spike means:** HSS partitioned during call setup, overloaded, or Cx path losing packets.
    - **Healthy typical range:** 0–0 ratio
    - **Healthy invariant:** Zero in healthy operation.

- **`normalized.icscf.cdp_replies_per_ue`** (I-CSCF Diameter reply rate per UE) — current **0.00 replies_per_second_per_ue** vs learned baseline **0.03 replies_per_second_per_ue** (MEDIUM, drop)
    - **What it measures:** Liveness of the I-CSCF↔HSS Cx path. Drops to 0 when HSS is unreachable OR when no signaling is occurring at the I-CSCF (idle or upstream P-CSCF partitioned).
    - **Drop means:** No Cx replies in the window. Could be healthy idle OR a Cx-path fault.
    - **Healthy typical range:** 0–1 replies_per_second_per_ue

- **`normalized.icscf.core:rcv_requests_invite_per_ue`** (SIP INVITE rate per UE at I-CSCF) — current **0.01 requests_per_second** vs learned baseline **0.00 requests_per_second** (MEDIUM, spike)
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

- **`normalized.scscf.core:rcv_requests_invite_per_ue`** (SIP INVITE rate per UE at S-CSCF) — current **0.01 requests_per_second** vs learned baseline **0.00 requests_per_second** (MEDIUM, spike)
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


## Symptom Classifier (Phase 0.5)

**Label:** `mixed`  
**Flag counts:** transport=0, application=0, ambiguous=10

### Ambiguous-bucket flags (10)

| Metric | Direction | Score | KB-driven reason |
|---|---|---:|---|
| `context.cx_active` | drop | 4.59 | no KB entry for context.cx_active — classification ambiguous |
| `derived.icscf_lir_timeout_ratio` | spike | 4.59 | KB-labeled mixed: ims.icscf.lir_timeout_ratio (spike, score=4.59) |
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
label=mixed. 10 ambiguous signal(s) — KB labels them `mixed` or could not be resolved. Path walk runs first to attempt deterministic localization; falls through to the application-layer pipeline if no hop attribution is found.

Ambiguous signals: context.cx_active (drop, score=4.59) — no KB entry for context.cx_active — classification ambiguous; derived.icscf_lir_timeout_ratio (spike, score=4.59) — KB-labeled mixed: ims.icscf.lir_timeout_ratio (spike, score=4.59); normalized.icscf.cdp_replies_per_ue (drop, score=4.59) — KB-labeled mixed: ims.icscf.cdp_replies_per_ue (drop, score=4.59); normalized.icscf.core:rcv_requests_invite_per_ue (spike, score=4.59) — KB-labeled mixed: ims.icscf.rcv_requests_invite_per_ue (spike, score=4.59); normalized.icscf.core:rcv_requests_register_per_ue (drop, score=4.59) — KB-labeled mixed: ims.icscf.rcv_requests_register_per_ue (drop, score=4.59) [+5 more]
```

## Transport-Layer Route (Phase 0.6)

### Resolver

**Flow:** `ims_registration` (IMS Registration)  
**Direction:** both  
**Hop count:** 41

**Candidates considered:**

| Flow | Score |
|---|---:|
| `ims_registration` ← chosen | 6 |
| `vonr_call_teardown` | 6 |
| `vonr_call_setup` | 6 |
| `diameter_cx_authentication` | 4 |

**Rationale:**

```
Resolved transport path to flow `ims_registration` (score=6, 41 hops on the walk). Load-bearing components: ['context', 'icscf', 'pcscf', 'scscf']. Other candidate flows considered: vonr_call_teardown=6, vonr_call_setup=6, diameter_cx_authentication=4.
```

### Walker

**Status:** ✅ **localized**
**First attributed hop:** `pyhss[eth0]`
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
| 16 | 🎯 `pyhss` | container | `eth0` | `latency_at_hop` | `qdisc_netem_delay`: delay 60000.0 ms |
| 17 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 18 | `icscf` | container | `eth0` | `clean` | _clean_ |
| 19 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 20 | `scscf` | container | `eth0` | `clean` | _clean_ |
| 21 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 22 | `pyhss` | container | `eth0` | `latency_at_hop` | `qdisc_netem_delay`: delay 60000.0 ms |
| 23 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 24 | `scscf` | container | `eth0` | `clean` | _clean_ |
| 25 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 26 | `pyhss` | container | `eth0` | `latency_at_hop` | `qdisc_netem_delay`: delay 60000.0 ms |
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

**Verdict:** `localized`  
**Primary suspect NF:** `pyhss`  
**Confidence:** high

**Summary:** Transport-layer fault localized to pyhss[eth0]: qdisc_netem_delay reports 60000.0ms delay.

**Recommendation:** Inspect tc qdisc on pyhss: `docker exec pyhss tc -s qdisc show dev eth0`.


## Event Aggregation (Phase 1)

No events fired during this episode. Either no metric KB triggers matched, or the episode encountered no meaningful state transitions.

## Correlation Analysis (Phase 2)

No events fired — correlation engine had nothing to work with.

## RAG & Operational Lessons (Phase 2.5)

### RAG retrieval — prior similar episodes

**Status:** `hits` — hits=5, top_sim=0.94, top_case=v7/ep_20260512_120607_hss_unresponsive
**Index:** `/home/ehoskas/agentic-network-ops/rag_index`  **Corpus size:** 102 cases
**Classifier label used in retrieval:** `mixed`
**Retrieval params:** k=5, min_similarity=0.4
**Hits (5):**

| Rank | Sim | Case ID | Scenario | Ground truth | Primary suspect | Score |
|---:|---:|---|---|---|---|---:|
| 0 | 94% | `v7/ep_20260512_120607_hss_unresponsive` | HSS Unresponsive | `pyhss` | `pyhss` | 100% |
| 1 | 92% | `v6/ep_20260429_161845_hss_unresponsive` | HSS Unresponsive | `pyhss` | `pyhss` | 85% |
| 2 | 90% | `v6/ep_20260430_014832_hss_unresponsive` | HSS Unresponsive | `pyhss` | `pyhss` | 95% |
| 3 | 89% | `v7/ep_20260514_213640_cascading_ims_failure` | Cascading IMS Failure | `pyhss, scscf` | `pyhss` | 100% |
| 4 | 84% | `v7/ep_20260510_201356_cascading_ims_failure` | Cascading IMS Failure | `pyhss, scscf` | `pyhss` | 100% |

*Rendered block injected into the NA prompt's `{prior_similar_episodes}` placeholder: 4792 chars. Source paths are inlined in the block so the EvidenceValidator can audit any case the NA cites.*

### Operational lessons — hand-authored rules corpus

**Status:** `injected` — lessons=16, chars=15678
**Path:** `/home/ehoskas/agentic-network-ops/agentic_ops_common/rag/lessons.yaml`  **Count:** 16  **Block size:** 15678 chars
**Injected lesson IDs:** `L01`, `L02`, `L03`, `L04`, `L05`, `L06`, `L07`, `L08`, `L09`, `L10`, `L11`, `L12`, `L13`, `L14`, `L15`, `L16`

### NA citations of the injected content

**Cited lesson IDs:**
- `L09`

*Citations are verbatim string matches — case_ids and lesson_ids appear in the NA's emitted text (summary, hypothesis statements, or layer notes). The EvidenceValidator can audit any cited case by following its `source_episode_path` from the retrieval table above.*

## Network Analysis (Phase 3)

**Summary:** Per L09, pyhss is the primary suspect as the source of the I-CSCF LIR timeouts and the stack-wide drop in Cx activity, corroborated by 100% packet loss from multiple CSCF components to the HSS.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | Infrastructure components like MySQL and MongoDB are running and accessible by other network elements, though pyhss is isolated. |
| **ran** | 🟢 GREEN | No anomalies detected in the RAN layer. |
| **core** | 🟢 GREEN | AMF, SMF, and UPF metrics are healthy with no anomalies flagged by the screener. |
| **ims** | 🔴 RED | Multiple IMS components report timeouts and missing Diameter responses on the Cx interface towards the HSS. |

**IMS evidence:**
- derived.icscf_lir_timeout_ratio spike
- normalized.icscf.cdp_replies_per_ue drop
- normalized.scscf.cdp_replies_per_ue drop
- context.cx_active drop

**Ranked hypotheses:**

- **`h1`** (fit=0.98, nf=pyhss, specificity=specific):
    - **Statement:** pyhss is the source of the I-CSCF LIR timeout ratio spike, the drop in Cx activity, and the drop in CDP replies across the CSCF components.
    - **Falsification probes:**
        - Execute measure_rtt from icscf to pyhss to confirm the network partition on the Cx interface.
        - Execute measure_rtt from scscf to pyhss to confirm the partition affects all Cx peers.
        - Check pyhss container logs to rule out process-level failure or misconfiguration.


## Falsification Plans (Phase 4)

**1 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `pyhss`)

**Hypothesis:** pyhss is the source of the I-CSCF LIR timeout ratio spike, the drop in Cx activity, and the drop in CDP replies across the CSCF components.

**Probes (4):**
1. **`measure_rtt`** — from icscf to pyhss
    - *Expected if hypothesis holds:* 100% packet loss or severe latency is observed on the path to pyhss.
    - *Falsifying observation:* 0% packet loss and normal latency, indicating the network path from icscf to pyhss is fully functional.
2. **`measure_rtt`** — from scscf to pyhss
    - *Expected if hypothesis holds:* 100% packet loss or severe latency is observed, corroborating the failure from the first probe and localizing the reachability loss to pyhss.
    - *Falsifying observation:* 0% packet loss and normal latency, indicating pyhss is reachable from other Cx peers and the failure observed in the first probe is localized to icscf.
3. **`check_process_listeners`** — container: pyhss
    - *Expected if hypothesis holds:* The probe returns no active listening sockets on Diameter ports TCP 3868 or 3875.
    - *Falsifying observation:* The probe returns active listening sockets bound to Diameter ports TCP 3868 and 3875.
4. **`get_network_status`** — check container state for pyhss
    - *Expected if hypothesis holds:* The pyhss container state is reported as down, exited, or restarting.
    - *Falsifying observation:* The pyhss container state is reported as UP.

*Notes:* Using compositional paired measure_rtt probes from two distinct CSCF peers to localize the network reachability failure to pyhss. Avoided mechanism-scoping language per previous feedback.


## Parallel Investigators (Phase 5)

**1 sub-Investigator verdict(s):** **1 NOT_DISPROVEN**

### `h1` — ✅ **NOT_DISPROVEN**

**Hypothesis:** pyhss is the source of the I-CSCF LIR timeout ratio spike, the drop in Cx activity, and the drop in CDP replies across the CSCF components.

**Reasoning:** [Multi-shot consensus — both shots returned NOT_DISPROVEN.]

Shot 1: The hypothesis holds: pyhss is indeed the source of the Cx activity drop and I-CSCF timeouts. Probes confirm 100% packet loss between multiple components (icscf, scscf, amf) and pyhss, as well as outbound from pyhss to mongo. While pyhss is running and its processes are correctly bound to Diameter port 3875, it is entirely network-partitioned. This layer mismatch (network isolation rather than a container/process crash) refines the failure mechanism but does not disprove the hypothesis statement that pyhss is the source of the failure.

Shot 2: Triangulated measure_rtt probes confirm 100% packet loss to PyHSS from both I-CSCF and S-CSCF, localizing the failure to PyHSS. While the container is running and the process is actively listening on its Diameter port, this simply refines the mechanism to a network-layer partition at PyHSS (rather than an application crash). PyHSS remains correctly identified as the source of the fault.

**Probes executed (6):**
- **from icscf to pyhss** ✓ CONSISTENT
    - *Tool:* `measure_rtt("icscf", "pyhss")`
    - *Observation:* [EVIDENCE: measure_rtt("icscf", "pyhss") -> "100% packet loss"]
    - *Comment:* Confirms a total loss of network reachability from I-CSCF to pyhss.
- **from scscf to pyhss** ✓ CONSISTENT
    - *Tool:* `measure_rtt("scscf", "pyhss")`
    - *Observation:* [EVIDENCE: measure_rtt("scscf", "pyhss") -> "100% packet loss"]
    - *Comment:* Corroborates the reachability failure from another Cx peer, indicating the issue is not localized to I-CSCF's egress.
- **container: pyhss** ✗ CONTRADICTS
    - *Tool:* `check_process_listeners("pyhss")`
    - *Observation:* [EVIDENCE: check_process_listeners("pyhss") -> "tcp   LISTEN 0      100      172.22.0.18:3875"]
    - *Comment:* The process is actually running and listening on its configured Cx port (3875). This contradicts a process-level crash mechanism but does not disprove pyhss as the source of the unreachability.
- **check container state for pyhss** ✗ CONTRADICTS
    - *Tool:* `get_network_status()`
    - *Observation:* [EVIDENCE: get_network_status() -> ""pyhss": "running""]
    - *Comment:* The container is UP, contradicting a container-level crash mechanism but not disproving the hypothesis statement (which asserts pyhss is the source of the failure).
- **triangulate inbound reachability from a non-IMS peer** ✓ CONSISTENT
    - *Tool:* `measure_rtt("amf", "pyhss")`
    - *Observation:* [EVIDENCE: measure_rtt("amf", "pyhss") -> "100% packet loss"]
    - *Comment:* Triangulation from a non-IMS peer shows pyhss is completely network-isolated inbound.
- **triangulate outbound reachability from pyhss** ✓ CONSISTENT
    - *Tool:* `measure_rtt("pyhss", "mongo")`
    - *Observation:* [EVIDENCE: measure_rtt("pyhss", "mongo") -> "100% packet loss"]
    - *Comment:* Triangulation shows pyhss is also completely network-isolated outbound, proving the fault originates at pyhss (network layer) and not the path from CSCF components.


## Evidence Validation (Phase 6)

**Overall verdict:** clean
**Overall confidence:** high

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 11 | 6/6 | clean | high |


## Ground Truth

**Failure domain:** ims_signaling  
**Protocol impact:** Diameter  
**Affected components:** pyhss  
**Severity:** degraded

## Agent Diagnosis

**Model:** v7-adk/pro=gemini-3.1-pro-preview+flash=gemini-3.5-flash  
**Time to diagnosis:** 386.4s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: Transport-layer fault localized to pyhss[eth0]: qdisc_netem_delay reports 60000.0ms delay.
> - **timeline**:
>     1. Walk start: Trace initiated along ims_registration flow.
>     2. Attribution: Transport-layer fault isolated at pyhss[eth0] due to 60000ms latency injected by qdisc_netem.
>     3. Walk end: High-confidence localization to pyhss.
> - **root_cause**: Kernel-level packet delay on pyhss's egress: `tc netem` qdisc injecting 60s of delay. (primary_suspect_nf: `pyhss`)
> - **affected_components**:
>     - `?`: ?
> - **recommendation**: Inspect tc qdisc on pyhss: `docker exec pyhss tc -s qdisc show dev eth0`.
> - **confidence**: high
> - **verdict_kind**: localized
> - **explanation**: Path walk localized a transport-layer fault along the `ims_registration` flow. Per-hop walk through the last attribution:
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
> | 13 | pcscf | container | eth0 | KernelHopProber | clean |
> | 14 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 15 | icscf | container | eth0 | KernelHopProber | clean |
> | 16 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 17 | pyhss | container | eth0 | KernelHopProber | 🎯 latency_at_hop (60000ms, qdisc_netem_delay) |
> | 18 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 19 | icscf | container | eth0 | KernelHopProber | clean |
> | 20 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 21 | scscf | container | eth0 | KernelHopProber | clean |
> | 22 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 23 | pyhss | container | eth0 | KernelHopProber | 🎯 latency_at_hop (60000ms, qdisc_netem_delay) |
> | 24 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 25 | scscf | container | eth0 | KernelHopProber | clean |
> | 26 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 27 | pyhss | container | eth0 | KernelHopProber | 🎯 latency_at_hop (60000ms, qdisc_netem_delay) |
> 
> Evidence for attribution at pyhss[eth0]:
> ```
> pyhss[eth0] qdisc=netem: sent=146 dropped=0 (0.00%)
> ---tc -s qdisc show dev eth0---
> qdisc netem 809f: root refcnt 9 limit 1000 delay 60s
>  Sent 8223 bytes 146 pkt (dropped 0, overlimits 0 requeues 0) 
>  backlog 7754b 129p requeues 0
> ```
> 
> Classifier rationale: label=mixed. 10 ambiguous signal(s) — KB labels them `mixed` or could not be resolved. Path walk runs first to attempt deterministic localization; falls through to the application-layer pipeline if no hop attribution is found.

### Scoring Breakdown

**Overall score: 80%**

**Scorer assessment:** The agent accurately diagnosed the 60-second delay on pyhss with exact tool evidence, but failed to populate the affected_components list in its final output.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | Yes | The agent correctly identified the root cause as a 60-second egress delay on the pyhss component, matching the simulated 60-second outbound delay. |
| Component overlap | 0% | The agent failed to populate the 'affected_components' list in its final diagnosis, leaving it as '?: ?', although it correctly identified pyhss as the primary suspect in other fields. |
| Severity correct | Yes | The agent correctly identified the severity as a 60000ms delay, which represents the exact latency degradation simulated. |
| Fault type identified | Yes | The agent correctly identified the class of failure as packet delay/latency. |
| Layer accuracy | Yes | The agent correctly rated the 'ims' layer as RED in its intermediate network analysis, which is the correct ontology layer for pyhss. |
| Confidence calibrated | Yes | The agent's high confidence is well-calibrated because it found direct, definitive evidence of the tc netem delay rule on the pyhss container. |

**Ranking position:** #1 — The correct root cause (pyhss delay) was identified as the primary and only suspect in the diagnosis.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 299,937 |
| Output tokens | 5,594 |
| Thinking tokens | 21,173 |
| **Total tokens** | **326,704** |

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
| NetworkAnalystAgent | 196,995 | 12 | 6 |
| Phase 3 NetworkAnalyst__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 10,285 | 0 | 1 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 10,218 | 0 | 1 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| InvestigatorAgent_h1 | 62,114 | 7 | 4 |
| InvestigatorAgent_h1 | 28,706 | 4 | 2 |
| InvestigatorAgent_h1__reconciliation | 0 | 0 | 0 |
| Phase5FanOutAudit | 0 | 0 | 0 |
| Phase6.5CandidatePool | 0 | 0 | 0 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 18,386 | 0 | 1 |
| Phase 7 Synthesis__guardrail | 0 | 0 | 0 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 525.1s
