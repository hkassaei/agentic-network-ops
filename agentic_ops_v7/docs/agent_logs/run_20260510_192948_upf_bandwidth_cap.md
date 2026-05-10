# Episode Report: UPF Bandwidth Cap

**Agent:** v7  
**Episode ID:** ep_20260510_192628_upf_bandwidth_cap  
**Date:** 2026-05-10T19:26:29.798917+00:00  
**Duration:** 197.8s  

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

**Verdict:** ⚠️ `inconclusive`

- **Wait:** 0s
- **Actual elapsed:** 0.0s
- **Nodes with significant deltas:** 0
- **Nodes with any drift:** 3

## Symptoms Observed

Symptoms detected: **No**  
Observation iterations: 1

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 30.57 (per-bucket threshold: 26.31, context bucket (0, 1), trained on 323 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following metrics deviate from their learned-healthy baseline. Treat each as a semantic observation (meaning + numbers), not a number alone — the KB's interpretation is the authoritative reading.

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

- **`normalized.smf.bearers_per_ue`** (Active QoS bearers per UE) — current **2.50 count** vs learned baseline **2.48 count** (LOW, shift)
    - **What it measures:** Per-UE count of active QoS bearers. Baseline reflects default
bearers; increments during VoNR calls indicate dedicated voice
bearers being set up. Drop during an active call = dedicated
bearer torn down unexpectedly (voice will fail).
    - **Shift means:** Expected during VoNR calls (1 extra bearer per active call).
    - **Healthy typical range:** 2–3.5 count
    - **Healthy invariant:** At rest: equals configured default bearers (typically 2 per UE).
During active VoNR call: +1 per caller. The per-UE ratio is the
invariant; absolute count scales with UE pool.

- **`normalized.icscf.cdp_replies_per_ue`** (I-CSCF Diameter reply rate per UE) — current **0.01 replies_per_second_per_ue** vs learned baseline **0.03 replies_per_second_per_ue** (LOW, drop)
    - **What it measures:** Liveness of the I-CSCF↔HSS Cx path. Drops to 0 when HSS is unreachable OR when no signaling is occurring at the I-CSCF (idle or upstream P-CSCF partitioned).
    - **Drop means:** No Cx replies in the window. Could be healthy idle OR a Cx-path fault.
    - **Healthy typical range:** 0–1 replies_per_second_per_ue

- **`normalized.icscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at I-CSCF) — current **0.03 requests_per_second** vs learned baseline **0.06 requests_per_second** (LOW, drop)
    - **What it measures:** Health of the P-CSCF → I-CSCF forwarding path (Mw interface). When
this drops to zero while P-CSCF REGISTER rate is still non-zero,
it's the SIGNATURE of an IMS partition between P-CSCF and I-CSCF.
    - **Drop means:** Either UEs not registering at all, or P-CSCF isolated from I-CSCF.
    - **Healthy typical range:** 0–0.5 requests_per_second
    - **Healthy invariant:** Per-UE rate. Should closely track ims.pcscf.rcv_requests_register_per_ue.

- **`normalized.pcscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at P-CSCF) — current **0.03 requests_per_second** vs learned baseline **0.06 requests_per_second** (LOW, drop)
    - **What it measures:** How actively UEs are refreshing their IMS registrations with the
P-CSCF. REGISTERs arrive periodically (re-registration timer) plus
at attach. Sustained zero means UEs cannot reach P-CSCF OR the
UE-to-network SIP path is broken.
    - **Drop means:** No REGISTERs flowing. Unusual unless UEs are all deregistered.
    - **Healthy typical range:** 0–0.5 requests_per_second
    - **Healthy invariant:** Per-UE rate — same value at any deployment scale.

- **`normalized.scscf.cdp_replies_per_ue`** (S-CSCF CDP Diameter replies per UE) — current **0.03 replies_per_second_per_ue** vs learned baseline **0.06 replies_per_second_per_ue** (LOW, drop)
    - **What it measures:** Active S-CSCF Diameter traffic with HSS. Near-zero when registrations idle OR HSS partition.
    - **Drop means:** No active S-CSCF Diameter exchanges (idle or partitioned).
    - **Healthy typical range:** 0–1 replies_per_second_per_ue
    - **Healthy invariant:** Per-UE rate; varies with registration/auth load.

- **`normalized.scscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at S-CSCF) — current **0.03 requests_per_second** vs learned baseline **0.06 requests_per_second** (LOW, drop)
    - **What it measures:** Health of the I-CSCF → S-CSCF forwarding path. Drop to zero while
I-CSCF is receiving REGISTERs = S-CSCF-side issue (crashed, or
I-CSCF → S-CSCF path broken).
    - **Drop means:** S-CSCF isolated or not running.
    - **Healthy typical range:** 0–0.5 requests_per_second
    - **Healthy invariant:** Per-UE rate. Tracks icscf.register rate.


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
| `normalized.smf.bearers_per_ue` | shift | 3.90 | KB-labeled application: core.smf.bearers_per_ue (shift, score=3.90) |

### Ambiguous-bucket flags (5)

| Metric | Direction | Score | KB-driven reason |
|---|---|---:|---|
| `normalized.icscf.cdp_replies_per_ue` | drop | 3.50 | KB-labeled mixed: ims.icscf.cdp_replies_per_ue (drop, score=3.50) |
| `normalized.icscf.core:rcv_requests_register_per_ue` | drop | 3.50 | KB-labeled mixed: ims.icscf.rcv_requests_register_per_ue (drop, score=3.50) |
| `normalized.pcscf.core:rcv_requests_register_per_ue` | drop | 3.50 | KB-labeled mixed: ims.pcscf.rcv_requests_register_per_ue (drop, score=3.50) |
| `normalized.scscf.cdp_replies_per_ue` | drop | 3.50 | KB-labeled mixed: ims.scscf.cdp_replies_per_ue (drop, score=3.50) |
| `normalized.scscf.core:rcv_requests_register_per_ue` | drop | 3.50 | KB-labeled mixed: ims.scscf.rcv_requests_register_per_ue (drop, score=3.50) |

**Rationale:**

```
label=mixed. Both transport-layer (2) and application-layer (1) signals are load-bearing. Path walk runs first; falls through to the application-layer pipeline if the walk produces null localization.

Transport signals: normalized.upf.gtp_indatapktn3upf_per_ue (drop, score=4.59) — KB-labeled transport: core.upf.gtp_indatapktn3upf_per_ue (drop, score=4.59); normalized.upf.gtp_outdatapktn3upf_per_ue (drop, score=4.59) — KB-labeled transport: core.upf.gtp_outdatapktn3upf_per_ue (drop, score=4.59)

Application signals: normalized.smf.bearers_per_ue (shift, score=3.90) — KB-labeled application: core.smf.bearers_per_ue (shift, score=3.90)

Ambiguous signals: normalized.icscf.cdp_replies_per_ue (drop, score=3.50) — KB-labeled mixed: ims.icscf.cdp_replies_per_ue (drop, score=3.50); normalized.icscf.core:rcv_requests_register_per_ue (drop, score=3.50) — KB-labeled mixed: ims.icscf.rcv_requests_register_per_ue (drop, score=3.50); normalized.pcscf.core:rcv_requests_register_per_ue (drop, score=3.50) — KB-labeled mixed: ims.pcscf.rcv_requests_register_per_ue (drop, score=3.50); normalized.scscf.cdp_replies_per_ue (drop, score=3.50) — KB-labeled mixed: ims.scscf.cdp_replies_per_ue (drop, score=3.50); normalized.scscf.core:rcv_requests_register_per_ue (drop, score=3.50) — KB-labeled mixed: ims.scscf.rcv_requests_register_per_ue (drop, score=3.50)
```

## Transport-Layer Route (Phase 0.6)

### Resolver

**Flow:** `data_pdu_session_user_traffic` (Data PDU Session — User Traffic)  
**Direction:** both  
**Hop count:** 11

**Candidates considered:**

| Flow | Score |
|---|---:|
| `data_pdu_session_user_traffic` ← chosen | 13 |
| `vonr_media` | 13 |
| `ims_registration` | 4 |
| `vonr_call_teardown` | 4 |
| `vonr_call_setup` | 4 |

**Rationale:**

```
Resolved transport path to flow `data_pdu_session_user_traffic` (score=13, 11 hops on the walk). Load-bearing components: ['icscf', 'pcscf', 'scscf', 'smf', 'upf']. Other candidate flows considered: vonr_media=13, ims_registration=4, vonr_call_teardown=4, vonr_call_setup=4.
```

### Walker

**Status:** ✅ **localized**
**First attributed hop:** `?[?]`
**Window:** 5s  
**Walked flow:** `data_pdu_session_user_traffic`

**Per-hop results:**

| # | Node | Kind | Iface | Attribution | Detail |
|---:|---|---|---|---|---|
| 0 | `e2e_ue1` | container | `eth0` | `clean` | _clean_ |
| 1 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 2 | `nr_gnb` | container | `eth0` | `clean` | _clean_ |
| 3 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 4 | `upf` | container | `eth0` | `drops_attributed_here` | `qdisc_tbf`: 292 dropped, 200.0% |
| 5 | `internet` | external_network | `eth0` | `inconclusive` | _no_prober_registered_: "no HopProber registered for kind='external_network'; registered kinds: ['contai |
| 6 | `upf` | container | `eth0` | `drops_attributed_here` | `qdisc_tbf`: 292 dropped, 200.0% |
| 7 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 8 | `nr_gnb` | container | `eth0` | `clean` | _clean_ |
| 9 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 10 | `e2e_ue1` | container | `eth0` | `clean` | _clean_ |

### Localized Synthesis

**Verdict:** `localized`  
**Primary suspect NF:** `upf`  
**Confidence:** high

**Summary:** Transport-layer fault localized to upf[eth0]: qdisc_tbf reports 292 packets dropped (200.0%).

**Recommendation:** Inspect the active traffic shaping configuration on the upf container's eth0 interface by running: `docker exec upf tc -s qdisc show dev eth0`.


## Event Aggregation (Phase 1)

*No events aggregated — Phase 0.6 localized, app-layer pipeline did not run.*

## Correlation Analysis (Phase 2)

*No correlation analysis — Phase 0.6 localized, app-layer pipeline did not run.*

## Network Analysis (Phase 3)

*No NA output — Phase 0.6 localized, app-layer pipeline did not run.*

## Falsification Plans (Phase 4)

*No falsification plans — Phase 0.6 localized, app-layer pipeline did not run.*

## Parallel Investigators (Phase 5)

*No sub-Investigator output — Phase 0.6 localized, app-layer pipeline did not run.*

## Evidence Validation (Phase 6)

*No evidence validation — Phase 0.6 localized, app-layer pipeline did not run.*

## Ground Truth

**Failure domain:** data_plane  
**Protocol impact:** GTP-U  
**Affected components:** upf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v7-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 64.8s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: Transport-layer fault localized to upf[eth0]: qdisc_tbf reports 292 packets dropped (200.0%).
> - **timeline**:
>     1. Path walk initiated for transport-layer flow data_pdu_session_user_traffic.
>     2. Fault localized at hop #5 (upf container, eth0 interface), where the KernelHopProber attributed 292 packet drops to a qdisc_tbf.
>     3. Path walk completed, producing a high-confidence diagnosis.
> - **root_cause**: Kernel-level packet drop on the UPF container's eth0 interface, caused by a Token Bucket Filter (TBF) queueing discipline (`qdisc`) enforcing a rate limit. (primary_suspect_nf: `upf`)
> - **affected_components**:
>     - `upf`: Root Cause
> - **recommendation**: Inspect the active traffic shaping configuration on the upf container's eth0 interface by running: `docker exec upf tc -s qdisc show dev eth0`.
> - **confidence**: high
> - **verdict_kind**: localized
> - **explanation**: The path walk bisection report localized the fault to a single hop. The walk traversed 11 hops from the UE to the internet and back for the flow `data_pdu_session_user_traffic`. The first-attributed hop was #5, `upf[eth0]`, where `KernelHopProber` attributed drops directly to the hop (`drops_attributed_here`). The counter responsible was a `qdisc_tbf` (Token Bucket Filter), indicating rate-limiting. The verbatim counter excerpt below confirms that 292 packets were dropped on this interface. The initial symptom was classified as 'mixed', triggering the transport-layer path walk which successfully localized the issue, pre-empting the application-layer investigation.
> 
> Verbatim counter evidence from `upf`:
> ```
> upf[eth0] qdisc=tbf: sent=146 dropped=292 (200.00%)
> ---tc -s qdisc show dev eth0---
> qdisc tbf 800a: root refcnt 9 rate 100Kbit burst 1280b lat 400ms 
>  Sent 17100 bytes 146 pkt (dropped 292, overlimits 6 requeues 0) 
>  backlog 0b 0p requeues 0
> ```

### Scoring Breakdown

**Overall score: 100%**

**Scorer assessment:** The agent provided an exceptionally accurate and precise diagnosis, correctly identifying the root cause, affected component, severity, and fault type with high confidence, directly matching the simulated failure mode.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | Yes | The agent correctly identified the root cause as a kernel-level packet drop on the UPF container's eth0 interface, caused by a Token Bucket Filter (TBF) queueing discipline enforcing a rate limit. This perfectly matches the simulated failure mode of a bandwidth cap on the UPF using a tc tbf qdisc. |
| Component overlap | 100% | The agent correctly identified 'upf' as the 'Root Cause' in its affected components list, which is the primary component affected by the simulated bandwidth cap. |
| Severity correct | Yes | The agent's diagnosis of 'packet drop' and 'rate limit' due to the TBF qdisc accurately reflects a degradation in service (packet loss, voice quality degradation) rather than a complete outage, aligning with the simulated severity. |
| Fault type identified | Yes | The agent identified 'Kernel-level packet drop' and 'rate limit' caused by a 'qdisc_tbf', which is a clear identification of network degradation due to packet loss, matching the observable fault type. |
| Layer accuracy | Yes | The agent's diagnosis does not include a layer status table. As per instructions, if no layer status information is available, it is scored as True. |
| Confidence calibrated | Yes | The agent stated 'high' confidence, which is appropriate given the extremely precise and accurate diagnosis, including the specific qdisc type, interface, and packet drop count, all directly supported by the verbatim counter evidence. |

**Ranking position:** #1 — The agent provided a single, clear root cause, which was correct.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 5,177 |
| Output tokens | 762 |
| Thinking tokens | 7,349 |
| **Total tokens** | **13,288** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| SymptomClassifier | 0 | 0 | 0 |
| PathResolver | 0 | 0 | 0 |
| PathWalkInvestigator | 0 | 0 | 0 |
| SynthesisAgent | 13,288 | 0 | 1 |
| Phase 7 Synthesis (localized)__guardrail | 0 | 0 | 0 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 197.8s
