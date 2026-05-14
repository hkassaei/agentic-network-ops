# Episode Report: Cascading IMS Failure

**Agent:** v7  
**Episode ID:** ep_20260514_193632_cascading_ims_failure  
**Date:** 2026-05-14T19:36:33.872913+00:00  
**Duration:** 187.2s  

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

- **Propagation window:** 132s (ObservationTrafficAgent drove traffic for this window; verifier added wait=0s on top)
- **Nodes with significant deltas:** 5
- **Nodes with any drift:** 5

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 54.45 (per-bucket threshold: 26.31, context bucket (0, 1), trained on 323 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

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

- **`normalized.pcscf.core:rcv_requests_invite_per_ue`** (SIP INVITE rate per UE at P-CSCF) — current **0.02 requests_per_second** vs learned baseline **0.00 requests_per_second** (MEDIUM, spike)
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

- **`normalized.upf.gtp_indatapktn3upf_per_ue`** (GTP-U uplink rate per UE (N3)) — current **0.03 packets_per_second** vs learned baseline **1.45 packets_per_second** (MEDIUM, drop)
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

**Label:** `transport_layer`  
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
label=transport_layer. 1 transport-layer signal(s); no application-layer smoking guns. Routes to the deterministic path walk (see ADR path_anchored_probe_planning_for_transport_layer_faults.md).

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
| 16 | `pyhss` | container | `eth0` | `inconclusive` | _tool_unavailable_: required binary 'tc' missing in container 'pyhss'; see docs/ADR/nf_container_dia |
| 17 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 18 | `icscf` | container | `eth0` | `clean` | _clean_ |
| 19 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 20 | `scscf` | container | `eth0` | `latency_at_hop` | `qdisc_netem_delay`: delay 2000.0 ms |
| 21 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 22 | `pyhss` | container | `eth0` | `inconclusive` | _tool_unavailable_: required binary 'tc' missing in container 'pyhss'; see docs/ADR/nf_container_dia |
| 23 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 24 | `scscf` | container | `eth0` | `latency_at_hop` | `qdisc_netem_delay`: delay 2000.0 ms |
| 25 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 26 | `pyhss` | container | `eth0` | `inconclusive` | _tool_unavailable_: required binary 'tc' missing in container 'pyhss'; see docs/ADR/nf_container_dia |
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
**Primary suspect NF:** `scscf`  
**Confidence:** high

**Summary:** Transport-layer fault localized to scscf[eth0]: `qdisc_netem_delay` reports an injected latency of 2000.0ms.

**Recommendation:** Inspect tc qdisc on scscf: `docker exec scscf tc -s qdisc show dev eth0` to verify the configured network emulation delay.


## Event Aggregation (Phase 1)

*No events aggregated — Phase 0.6 localized, app-layer pipeline did not run.*

## Correlation Analysis (Phase 2)

*No correlation analysis — Phase 0.6 localized, app-layer pipeline did not run.*

## RAG & Operational Lessons (Phase 2.5)

### RAG retrieval — prior similar episodes

*Phase 2.5 did not run for this episode — typically because Phase 0.6's walker localized the fault and the orchestrator short-circuited to Phase 7 Synthesis, bypassing the application-layer pipeline.*

### Operational lessons — hand-authored rules corpus

*Phase 2.5b did not run for this episode — same reason as RAG retrieval above (localized branch).*

### NA citations of the injected content

*Phase 3 NetworkAnalyst did not run for this episode (localized branch). No citation scan was performed.*

## Network Analysis (Phase 3)

*No NA output — Phase 0.6 localized, app-layer pipeline did not run.*

## Falsification Plans (Phase 4)

*No falsification plans — Phase 0.6 localized, app-layer pipeline did not run.*

## Parallel Investigators (Phase 5)

*No sub-Investigator output — Phase 0.6 localized, app-layer pipeline did not run.*

## Evidence Validation (Phase 6)

*No evidence validation — Phase 0.6 localized, app-layer pipeline did not run.*

## Ground Truth

**Failure domain:** ims_signaling  
**Protocol impact:** SIP  
**Affected components:** pyhss, scscf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v7-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 32.0s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: Transport-layer fault localized to scscf[eth0]: `qdisc_netem_delay` reports an injected latency of 2000.0ms.
> - **timeline**:
>     1. Path walk initiated for flow `ims_registration` due to transport-layer anomaly signals.
>     2. Walk attributes high latency to hop #21, container `scscf`, based on kernel-level probers.
>     3. Fault localized with high confidence to `scscf[eth0]` via `qdisc_netem_delay` counter, confirming a 2000ms injected delay.
> - **root_cause**: Kernel-level packet delay on scscf's egress interface eth0: a `tc netem` qdisc is configured to add a 2000ms delay to all outgoing packets. (primary_suspect_nf: `scscf`)
> - **affected_components**:
>     - `scscf`: Root Cause
> - **recommendation**: Inspect tc qdisc on scscf: `docker exec scscf tc -s qdisc show dev eth0` to verify the configured network emulation delay.
> - **confidence**: high
> - **verdict_kind**: localized
> - **explanation**: A transport-layer path walk for flow `ims_registration` localized the fault to `scscf`. The walk identified significant latency at hop #21 (`scscf`). The kernel's `tc` statistics for interface `eth0` on that container confirm an injected delay, which is the root cause of the observed service degradation. Verbatim counter excerpt from the attributed hop:
> ```
> scscf[eth0] qdisc=netem: sent=240 dropped=0 (0.00%)
> ---tc -s qdisc show dev eth0---
> qdisc netem 800a: root refcnt 9 limit 1000 delay 2s
>  Sent 48528 bytes 240 pkt (dropped 0, overlimits 0 requeues 0) 
>  backlog 0b 0p requeues 0
> ```
> Classifier Rationale: label=transport_layer. 1 transport-layer signal(s); no application-layer smoking guns. Routes to the deterministic path walk.

### Scoring Breakdown

**Overall score: 15%**

**Scorer assessment:** The agent partially identified one aspect of the simulated cascading failure (S-CSCF latency) but completely missed the other critical part (PyHSS unreachability), leading to an incomplete diagnosis and an incorrect severity assessment, despite high confidence.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | No | The simulated failure involved two root causes: PyHSS being completely unreachable AND S-CSCF having 2-second latency. The agent only identified the S-CSCF latency as the root cause, completely missing the PyHSS unreachability. |
| Component overlap | 50% | The simulated failure involved two primary affected components: 'pyhss' and 'scscf'. The agent correctly identified 'scscf' as a 'Root Cause' component, but completely missed 'pyhss'. Therefore, 1 out of 2 primary affected components were correctly identified as a root cause. |
| Severity correct | No | The simulated failure resulted in a 'Total IMS outage'. The agent's diagnosis described the issue as 'service degradation' due to latency, which is a less severe assessment and misses the complete outage caused by the HSS failure. |
| Fault type identified | No | The simulated failure involved two observable fault types: 'component unreachable' (for PyHSS) and 'network degradation' (for S-CSCF latency). The agent only identified 'kernel-level packet delay' (network degradation) and missed the 'component unreachable' aspect. |
| Layer accuracy | Yes | The agent focused on 'scscf', which is an IMS component. Since no layer status information from the NETWORK ANALYSIS section was provided, and the agent correctly attributed the issue to an IMS component, no misattribution can be detected. The 'ims' layer is the correct ontology layer for 'scscf'. |
| Confidence calibrated | No | The agent stated 'high' confidence, but its diagnosis was significantly incomplete, missing a major root cause (PyHSS unreachability), the overall severity (total outage vs. degradation), and a key fault type. High confidence is not justified for such a partial diagnosis. |

**Ranking:** The agent provided only one diagnosis. This diagnosis is incomplete as it misses a significant part of the simulated failure (PyHSS unreachability and total IMS outage). Therefore, the full correct cause is not listed.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 6,063 |
| Output tokens | 722 |
| Thinking tokens | 1,620 |
| **Total tokens** | **8,405** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| SymptomClassifier | 0 | 0 | 0 |
| PathResolver | 0 | 0 | 0 |
| PathWalkInvestigator | 0 | 0 | 0 |
| SynthesisAgent | 8,405 | 0 | 1 |
| Phase 7 Synthesis (localized)__guardrail | 0 | 0 | 0 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 187.2s
