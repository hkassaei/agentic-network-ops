# Episode Report: Cascading IMS Failure

**Agent:** v7  
**Episode ID:** ep_20260521_131331_cascading_ims_failure  
**Date:** 2026-05-21T13:13:32.788856+00:00  
**Duration:** 520.1s  

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

- **Propagation window:** 135s (ObservationTrafficAgent drove traffic for this window; verifier added wait=0s on top)
- **Nodes with significant deltas:** 4
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

- **`normalized.icscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at I-CSCF) — current **0.01 requests_per_second** vs learned baseline **0.06 requests_per_second** (MEDIUM, drop)
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

- **`normalized.scscf.core:rcv_requests_invite_per_ue`** (SIP INVITE rate per UE at S-CSCF) — current **0.03 requests_per_second** vs learned baseline **0.00 requests_per_second** (MEDIUM, spike)
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
| 16 | 🎯 `pyhss` | container | `eth0` | `container_dead` | **container `exited`** |
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

**Verdict:** `localized`  
**Primary suspect NF:** `pyhss`  
**Confidence:** high

**Summary:** Transport-layer fault localized to pyhss[eth0]: container_dead reports container has exited.

**Recommendation:** Verify pyhss container status: `docker ps -a | grep pyhss` and inspect its logs to determine the crash reason.


## Event Aggregation (Phase 1)

No events fired during this episode. Either no metric KB triggers matched, or the episode encountered no meaningful state transitions.

## Correlation Analysis (Phase 2)

No events fired — correlation engine had nothing to work with.

## RAG & Operational Lessons (Phase 2.5)

### RAG retrieval — prior similar episodes

**Status:** `hits` — hits=5, top_sim=0.95, top_case=v6/ep_20260430_014832_hss_unresponsive
**Index:** `/home/ehoskas/agentic-network-ops/rag_index`  **Corpus size:** 102 cases
**Classifier label used in retrieval:** `mixed`
**Retrieval params:** k=5, min_similarity=0.4
**Hits (5):**

| Rank | Sim | Case ID | Scenario | Ground truth | Primary suspect | Score |
|---:|---:|---|---|---|---|---:|
| 0 | 95% | `v6/ep_20260430_014832_hss_unresponsive` | HSS Unresponsive | `pyhss` | `pyhss` | 95% |
| 1 | 94% | `v7/ep_20260514_213640_cascading_ims_failure` | Cascading IMS Failure | `pyhss, scscf` | `pyhss` | 100% |
| 2 | 90% | `v7/ep_20260510_194005_dns_failure` | DNS Failure | `dns` | `dns` | 85% |
| 3 | 89% | `v7/ep_20260510_201356_cascading_ims_failure` | Cascading IMS Failure | `pyhss, scscf` | `pyhss` | 100% |
| 4 | 85% | `v6/ep_20260429_164815_ims_network_partition` | IMS Network Partition | `pcscf` | `pcscf` | 100% |

*Rendered block injected into the NA prompt's `{prior_similar_episodes}` placeholder: 4775 chars. Source paths are inlined in the block so the EvidenceValidator can audit any case the NA cites.*

### Operational lessons — hand-authored rules corpus

**Status:** `injected` — lessons=16, chars=15678
**Path:** `/home/ehoskas/agentic-network-ops/agentic_ops_common/rag/lessons.yaml`  **Count:** 16  **Block size:** 15678 chars
**Injected lesson IDs:** `L01`, `L02`, `L03`, `L04`, `L05`, `L06`, `L07`, `L08`, `L09`, `L10`, `L11`, `L12`, `L13`, `L14`, `L15`, `L16`

### NA citations of the injected content

**Cited lesson IDs:**
- `L03`
- `L09`
- `L10`

*Citations are verbatim string matches — case_ids and lesson_ids appear in the NA's emitted text (summary, hypothesis statements, or layer notes). The EvidenceValidator can audit any cited case by following its `source_episode_path` from the retrieval table above.*

## Network Analysis (Phase 3)

**Summary:** The pyhss container is exited, making it the direct fault locus (L10) for the IMS outage; P-CSCF, I-CSCF, S-CSCF, and UPF are explicitly demoted as secondary observers reporting downstream symptoms of the HSS partition (L09) and over-flagged idle state noise (L03).

**Ranked hypotheses:**

- **`h1`** (fit=0.99, nf=pyhss, specificity=specific):
    - **Statement:** pyhss is the source of the Cx Diameter failures and subsequent IMS call setup drops.
    - **Falsification probes:**
        - Execute get_container_logs on pyhss to identify the application crash reason.
        - Inspect the pyhss container exit code to determine if it was OOM-killed or deliberately stopped.


## Falsification Plans (Phase 4)

**1 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `pyhss`)

**Hypothesis:** pyhss is the source of the Cx Diameter failures and subsequent IMS call setup drops.

**Probes (3):**
1. **`get_network_status`** — No arguments needed
    - *Expected if hypothesis holds:* The returned status string shows the pyhss container in an exited state.
    - *Falsifying observation:* The returned status string shows the pyhss container in an up or running state.
2. **`check_process_listeners`** — container: pyhss
    - *Expected if hypothesis holds:* The command output yields an empty list of listening ports or an execution failure message.
    - *Falsifying observation:* The command output lists active listening TCP or SCTP ports.
3. **`query_subscriber`** — imsi: 999310000000001 or any default test IMSI
    - *Expected if hypothesis holds:* The command output is a connection error, timeout message, or execution failure.
    - *Falsifying observation:* The command output contains a valid subscriber profile payload.

*Notes:* Hypothesis isolates pyhss as the direct fault locus (L10). Probes strictly check for the observable signs of component unavailability without imposing mechanism or layer causality in the expected text.


## Parallel Investigators (Phase 5)

**1 sub-Investigator verdict(s):** **1 NOT_DISPROVEN**

### `h1` — ✅ **NOT_DISPROVEN**

**Hypothesis:** pyhss is the source of the Cx Diameter failures and subsequent IMS call setup drops.

**Reasoning:** [Multi-shot consensus — both shots returned NOT_DISPROVEN.]

Shot 1: The execution of get_network_status explicitly confirms that the pyhss container is in an exited state. Correspondingly, query_subscriber failed to connect to the PyHSS API, which strongly corroborates that PyHSS is unavailable and acting as the direct fault locus. The check_process_listeners probe could not execute because the required binary (ss/netstat) is missing in the container. The hypothesis is fully consistent with the observed component downtime.

Shot 2: The get_network_status probe confirmed that the pyhss container is in an exited state. Additionally, query_subscriber failed with a connection error to the PyHSS API, corroborating the hypothesis that pyhss is unavailable and the source of the failures. The check_process_listeners probe could not execute because the container was unavailable, but the other strong positive evidence confirms the hypothesis.

**Probes executed (3):**
- **Check the status of the network containers to see if pyhss is running.** ✓ CONSISTENT
    - *Tool:* `get_network_status()`
    - *Observation:* [EVIDENCE: get_network_status() -> ""pyhss": "exited""]
    - *Comment:* The status output clearly shows the pyhss container in an exited state, confirming it is unavailable.
- **Check if pyhss is listening on TCP or SCTP ports.** ~ AMBIGUOUS
    - *Tool:* `check_process_listeners("pyhss")`
    - *Observation:* [EVIDENCE: check_process_listeners("pyhss") -> "PROBE_TOOL_UNAVAILABLE: check_process_listeners cannot run on container `pyhss`"]
    - *Comment:* The tool could not run because the required binary (ss/netstat) is not available in the pyhss container.
- **Query subscriber profile to test PyHSS API reachability.** ✓ CONSISTENT
    - *Tool:* `query_subscriber("999310000000001", "ims")`
    - *Observation:* [EVIDENCE: query_subscriber("999310000000001", "ims") -> "Cannot connect to PyHSS API at http://172.22.0.18:8080. Is the pyhss container running?"]
    - *Comment:* The query fails to connect to the PyHSS API, directly confirming that PyHSS is uncontactable.


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
**Affected components:** scscf, pyhss  
**Severity:** degraded

## Agent Diagnosis

**Model:** v7-adk/pro=gemini-3.1-pro-preview+flash=gemini-3.5-flash  
**Time to diagnosis:** 364.9s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: Transport-layer fault localized to pyhss[eth0]: container_dead reports container has exited.
> - **timeline**:
>     1. Path walk initiated for ims_registration flow.
>     2. Walk progressed cleanly until hop 17.
>     3. First fault localized at hop 17: pyhss container found in 'exited' state (container_dead).
>     4. Application-layer investigations confirmed PyHSS API is uncontactable.
>     5. Walk ended with high confidence attribution.
> - **root_cause**: The pyhss container has unexpectedly exited, causing it to be unavailable for Cx Diameter operations and IMS call setup. (primary_suspect_nf: `pyhss`)
> - **affected_components**:
>     - `?`: ?
> - **recommendation**: Verify pyhss container status: `docker ps -a | grep pyhss` and inspect its logs to determine the crash reason.
> - **confidence**: high
> - **verdict_kind**: localized
> - **explanation**: The bisection walk for flow `ims_registration` identified a fault at the `pyhss` container.
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
> | 17 | pyhss | container | eth0 | KernelHopProber | container_dead (status=exited) 🎯 |
> | 18 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 19 | icscf | container | eth0 | KernelHopProber | clean |
> | 20 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 21 | scscf | container | eth0 | KernelHopProber | latency_at_hop (2000ms, qdisc_netem_delay) |
> | 22 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 23 | pyhss | container | eth0 | KernelHopProber | container_dead (status=exited) |
> | 24 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 25 | scscf | container | eth0 | KernelHopProber | latency_at_hop (2000ms, qdisc_netem_delay) |
> | 26 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 27 | pyhss | container | eth0 | KernelHopProber | container_dead (status=exited) |
> | 28 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 29 | scscf | container | eth0 | KernelHopProber | latency_at_hop (2000ms, qdisc_netem_delay) |
> | 30 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 31 | icscf | container | eth0 | KernelHopProber | clean |
> | 32 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 33 | pcscf | container | eth0 | KernelHopProber | clean |
> | 34 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 35 | e2e_ue1 | container | eth0 | KernelHopProber | clean |
> | 36 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 37 | pcscf | container | eth0 | KernelHopProber | clean |
> | 38 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 39 | scp | container | eth0 | KernelHopProber | clean |
> | 40 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 41 | pcf | container | eth0 | KernelHopProber | clean |
> 
> ```
> container 'pyhss' state is `exited` (expected `running`); probes cannot execute against a non-running container
> 
> (no evidence available)
> ```
> 
> Classifier rationale: label=mixed. 1 transport-layer signal(s) plus 9 ambiguous signal(s) clustering on a different NF-owner layer (transport on core; ambiguous cluster on ims (100%)). Treated as compound: walker plus application-layer pipeline both run; Synthesis merges into a single (potentially multi-root-cause) verdict.

### Scoring Breakdown

**Overall score: 90%**

**Scorer assessment:** The agent successfully diagnosed the primary root cause (PyHSS container exit) with high confidence, though it missed the secondary S-CSCF latency degradation in its final summary.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | Yes | The agent correctly identified that the pyhss container had unexpectedly exited (container_dead), which is the primary root cause of the total IMS outage. |
| Component overlap | 50% | The agent identified 'pyhss' as the primary suspect NF in the root cause, but the 'affected_components' list was left as a placeholder ('?'), and the secondary affected component 'scscf' (which had latency injected) was not included in the final causes block. |
| Severity correct | Yes | The agent correctly identified the severity as a complete outage, noting that the pyhss container was dead/exited and unavailable. |
| Fault type identified | Yes | The agent correctly identified the fault type as a component being down/unreachable ('container_dead' and 'uncontactable'). |
| Layer accuracy | Yes | No layer status information was provided in the network analysis, so no misattribution was detected. |
| Confidence calibrated | Yes | The agent's high confidence is justified because it found direct container-level evidence of the pyhss failure. |

**Ranking position:** #1 — The correct primary root cause (pyhss) was identified as the top suspect.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 295,415 |
| Output tokens | 4,418 |
| Thinking tokens | 21,433 |
| **Total tokens** | **321,266** |

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
| NetworkAnalystAgent | 226,373 | 8 | 7 |
| Phase 3 NetworkAnalyst__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 10,885 | 0 | 1 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 9,937 | 0 | 1 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| InvestigatorAgent_h1 | 25,979 | 3 | 2 |
| InvestigatorAgent_h1 | 25,977 | 3 | 2 |
| InvestigatorAgent_h1__reconciliation | 0 | 0 | 0 |
| Phase5FanOutAudit | 0 | 0 | 0 |
| Phase6.5CandidatePool | 0 | 0 | 0 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 22,115 | 0 | 1 |
| Phase 7 Synthesis__guardrail | 0 | 0 | 0 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 520.1s
