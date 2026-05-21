# Episode Report: HSS Unresponsive

**Agent:** v7  
**Episode ID:** ep_20260520_211610_hss_unresponsive  
**Date:** 2026-05-20T21:16:12.070115+00:00  
**Duration:** 459.2s  

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

- **Propagation window:** 132s (ObservationTrafficAgent drove traffic for this window; verifier added wait=0s on top)
- **Nodes with significant deltas:** 4
- **Nodes with any drift:** 5

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 54.05 (per-bucket threshold: 26.31, context bucket (0, 1), trained on 323 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

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

**Verdict:** `compound`  
**Primary suspect NF:** `pyhss`  
**Confidence:** high

**Summary:** Compound fault: a 60-second transport-layer delay injected on pyhss[eth0] is causing application-level unresponsiveness and IMS registration failures.

**Recommendation:** Inspect the traffic control configuration on the `pyhss` container's `eth0` interface by running `docker exec pyhss tc -s qdisc show dev eth0` to verify the 60-second netem delay.


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

**Cited case IDs:**
- `v7/ep_20260512_120607_hss_unresponsive`
- `v6/ep_20260429_161845_hss_unresponsive`

**Cited lesson IDs:**
- `L03`

*Citations are verbatim string matches — case_ids and lesson_ids appear in the NA's emitted text (summary, hypothesis statements, or layer notes). The EvidenceValidator can audit any cited case by following its `source_episode_path` from the retrieval table above.*

## Network Analysis (Phase 3)

**Summary:** The anomaly is characterized by a failure in the IMS core, specifically related to the HSS. Multiple indicators, including Diameter timeouts at the I-CSCF and a drop in Diameter replies across both I-CSCF and S-CSCF, point to the HSS being unresponsive. Prior similar episodes strongly corroborate this diagnosis.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | All network function containers are running, and the network topology shows no link failures. The underlying infrastructure is considered healthy. |
| **ran** | 🟢 GREEN | No metrics from the RAN layer were flagged. The issue appears to be localized within the IMS core. |
| **core** | 🟢 GREEN | The core network components appear to be operating normally. While some UPF metrics showed unusual values, they are likely noise in an idle state and not indicative of a data plane fault, as per lesson L03. |
| **ims** | 🔴 RED | The IMS signaling layer is heavily impacted. The primary issue appears to be a breakdown in communication with the HSS, preventing user registration and call setup procedures. |

**IMS evidence:**
- derived.icscf_lir_timeout_ratio:spike:MEDIUM
- normalized.icscf.cdp_replies_per_ue:drop:MEDIUM
- normalized.scscf.cdp_replies_per_ue:drop:MEDIUM
- context.cx_active:drop:MEDIUM

**Ranked hypotheses:**

- **`h1`** (fit=0.90, nf=pyhss, specificity=specific):
    - **Statement:** HSS (pyhss) is the source of the anomaly, causing Diameter timeouts on the Cx interface. This is supported by direct timeout metrics from I-CSCF and corroborated by multiple prior incidents (v7/ep_20260512_120607_hss_unresponsive, v6/ep_20260429_161845_hss_unresponsive) with identical signatures.
    - **Falsification probes:**
        - measure_rtt('icscf', 'pyhss') to check for network-level connectivity issues.
        - Query HSS internal logs and error counters for signs of application-level failure or overload.
        - Initiate a new registration from a test UE to see if it fails at the HSS authentication step.


## Falsification Plans (Phase 4)

**1 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `pyhss`)

**Hypothesis:** HSS (pyhss) is the source of the anomaly, causing Diameter timeouts on the Cx interface. This is supported by direct timeout metrics from I-CSCF and corroborated by multiple prior incidents (v7/ep_20260512_120607_hss_unresponsive, v6/ep_20260429_161845_hss_unresponsive) with identical signatures.

**Probes (3):**
1. **`measure_rtt`** — from: 'icscf', to: '172.22.0.18'
    - *Expected if hypothesis holds:* High RTT or packet loss is observed.
    - *Falsifying observation:* The probe's reading is inconsistent with pyhss being the source of a network-level fault (e.g. low RTT and no packet loss).
2. **`measure_rtt`** — from: 'scscf', to: '172.22.0.18'
    - *Expected if hypothesis holds:* High RTT or packet loss is observed, with a similar value to the probe from 'icscf'. This would indicate the issue is at or near the common destination (pyhss).
    - *Falsifying observation:* The probe's reading from this path is significantly different from the icscf-pyhss path (e.g., low RTT and no packet loss), suggesting the issue is path-specific to icscf, not a problem with pyhss itself.
3. **`get_diagnostic_metrics`** — nf='pyhss'
    - *Expected if hypothesis holds:* Metrics show a discrepancy between incoming Diameter requests and outgoing Diameter answers, or an increase in processing error counters.
    - *Falsifying observation:* Metrics show a healthy ratio of outgoing answers to incoming requests and no significant error counters.

*Notes:* The plan uses a pair of measure_rtt probes to disambiguate between a pyhss-specific network problem and a path-specific one. It also checks the NF's own metrics for signs of processing failure. This covers both network-level and service-level unresponsiveness and addresses the feedback from the prior rejection.


## Parallel Investigators (Phase 5)

**1 sub-Investigator verdict(s):** **1 NOT_DISPROVEN**

### `h1` — ✅ **NOT_DISPROVEN**

**Hypothesis:** HSS (pyhss) is the source of the anomaly, causing Diameter timeouts on the Cx interface. This is supported by direct timeout metrics from I-CSCF and corroborated by multiple prior incidents (v7/ep_20260512_120607_hss_unresponsive, v6/ep_20260429_161845_hss_unresponsive) with identical signatures.

**Reasoning:** [Multi-shot consensus — both shots returned NOT_DISPROVEN.]

Shot 1: Probes confirm that pyhss is unreachable from both icscf and scscf, with 100% packet loss observed from both sources. This strongly supports the hypothesis of an unresponsive HSS. The lack of diagnostic metrics from pyhss is consistent with a network-level fault that makes the component unreachable. No evidence was found to contradict the hypothesis.

Shot 2: All executed probes returned results consistent with the hypothesis. Probes measuring network connectivity to 'pyhss' from two different sources ('icscf' and 'scscf') both showed 100% packet loss, indicating 'pyhss' is unreachable. A subsequent attempt to retrieve diagnostic metrics from 'pyhss' yielded no data, which further corroborates its unresponsiveness. No contradictory evidence was found.

**Probes executed (3):**
- **measure RTT from 'icscf' to 'pyhss'** ✓ CONSISTENT
    - *Tool:* `default_api.measure_rtt(container = "icscf", target = "pyhss")`
    - *Observation:* [EVIDENCE: measure_rtt("icscf", "pyhss") -> "100% packet loss"]
    - *Comment:* The observation of 100% packet loss is consistent with the hypothesis that pyhss is unresponsive.
- **measure RTT from 'scscf' to 'pyhss'** ✓ CONSISTENT
    - *Tool:* `default_api.measure_rtt(container = "scscf", target = "pyhss")`
    - *Observation:* [EVIDENCE: measure_rtt("scscf", "pyhss") -> "100% packet loss"]
    - *Comment:* The observation of 100% packet loss from a second source (scscf) triangulates the problem to pyhss, which is consistent with the hypothesis.
- **get diagnostic metrics for 'pyhss'** ~ AMBIGUOUS
    - *Tool:* `default_api.get_diagnostic_metrics(at_time_ts = 1779311863.2821918, nfs = ["pyhss"])`
    - *Observation:* [EVIDENCE: get_diagnostic_metrics(at_time_ts=1779311863.2821918, nfs=["pyhss"]) -> "DIAGNOSTIC METRICS (anchored at ts=1779311863)\n\nPer-NF curated view. Two blocks per NF:\n  - Model features: current values vs the anomaly screener's learned baseline.\n  - Diagnostic supporting: raw values that have proven load-bearing in agent hypothesis testing across saved episodes.\n"]
    - *Comment:* The tool returned no metrics for pyhss. This is ambiguous. While it doesn't show any processing errors, it is consistent with a completely unresponsive or offline NF, which aligns with the 100% packet loss seen in the other probes. It does not falsify the hypothesis.


## Evidence Validation (Phase 6)

**Overall verdict:** clean
**Overall confidence:** high

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 6 | 3/3 | clean | high |


## Ground Truth

**Failure domain:** ims_signaling  
**Protocol impact:** Diameter  
**Affected components:** pyhss  
**Severity:** degraded

## Agent Diagnosis

**Model:** v7-adk/pro=gemini-2.5-pro+flash=gemini-2.5-flash  
**Time to diagnosis:** 314.9s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: Compound fault: a 60-second transport-layer delay injected on pyhss[eth0] is causing application-level unresponsiveness and IMS registration failures.
> - **timeline**:
>     1. IMS registration flow initiated.
>     2. Path walk localized a 60,000ms latency attribution to pyhss[eth0] due to a `qdisc_netem_delay` configuration.
>     3. Simultaneously, the application-layer pipeline reported Diameter timeouts at I-CSCF, hypothesizing an unresponsive HSS (pyhss).
>     4. Investigator probes confirmed pyhss is unreachable from both icscf and scscf (100% packet loss), validating the application-layer hypothesis.
>     5. Both transport and application layer analyses converge on pyhss as the root cause of the outage.
> - **root_cause**: A 60-second network delay was artificially injected via `tc qdisc netem` on the `eth0` interface of the `pyhss` container. This transport-layer fault makes `pyhss` unreachable, causing Diameter timeouts at the I-CSCF and S-CSCF and preventing IMS registration. (primary_suspect_nf: `pyhss`)
> - **affected_components**:
>     - `pyhss`: Root Cause
>     - `icscf`: Symptomatic
>     - `scscf`: Symptomatic
> - **recommendation**: Inspect the traffic control configuration on the `pyhss` container's `eth0` interface by running `docker exec pyhss tc -s qdisc show dev eth0` to verify the 60-second netem delay.
> - **confidence**: high
> - **verdict_kind**: compound
> - **explanation**: The orchestrator detected a `mixed` symptom and ran both transport-layer and application-layer analysis pipelines, both of which converged on `pyhss` as the root cause.
> 
> The transport-layer path walk attributed a fault to `pyhss` based on kernel-level counters. Per-hop walk through the last attribution:
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
> | 17 | pyhss | container | eth0 | KernelHopProber | latency_at_hop (60000ms, qdisc_netem_delay) 🎯 |
> | 18 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 19 | icscf | container | eth0 | KernelHopProber | clean |
> | 20 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 21 | scscf | container | eth0 | KernelHopProber | clean |
> | 22 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 23 | pyhss | container | eth0 | KernelHopProber | latency_at_hop (60000ms, qdisc_netem_delay) 🎯 |
> | 24 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 25 | scscf | container | eth0 | KernelHopProber | clean |
> | 26 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 27 | pyhss | container | eth0 | KernelHopProber | latency_at_hop (60000ms, qdisc_netem_delay) 🎯 |
> 
> Evidence for `pyhss` latency_at_hop:
> ```
> pyhss[eth0] qdisc=netem: sent=180 dropped=0 (0.00%)
> ---tc -s qdisc show dev eth0---
> qdisc netem 8091: root refcnt 9 limit 1000 delay 60s
>  Sent 9627 bytes 180 pkt (dropped 0, overlimits 0 requeues 0) 
>  backlog 7104b 120p requeues 0
> ```
> Concurrently, the application-layer pipeline produced a high-confidence hypothesis (`h1`) also blaming `pyhss`, which was confirmed by the Investigator. The verdict reasoning was: "Probes confirm that pyhss is unreachable from both icscf and scscf, with 100% packet loss observed from both sources. This strongly supports the hypothesis of an unresponsive HSS."
> 
> Classifier rationale for running both pipelines: label=mixed. 10 ambiguous signal(s) — KB labels them `mixed` or could not be resolved. Path walk runs first to attempt deterministic localization; falls through to the application-layer pipeline if no hop attribution is found.

### Scoring Breakdown

**Overall score: 100%**

**Scorer assessment:** The agent provided a perfectly accurate and well-supported diagnosis, correctly identifying the root cause, affected component, severity, fault type, and layer, with appropriate high confidence.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | Yes | The agent correctly identified the 60-second network delay on pyhss as the root cause, which functionally leads to unreachability, matching the simulated failure mode. The agent even identified the specific injection mechanism (`tc qdisc netem`), which is more detailed than required but still accurate from an observable network perspective (the `qdisc_netem_delay` is an observable artifact). |
| Component overlap | 100% | The agent correctly identified 'pyhss' as the 'Root Cause' in its affected components list, which is the primary affected component in the simulated failure. |
| Severity correct | Yes | The simulated failure describes the HSS as 'functionally unreachable' and leading to '100% packet loss' for probes, which the agent correctly interpreted as 'unreachable' and 'preventing IMS registration', indicating a complete service outage. |
| Fault type identified | Yes | The agent identified the fault as a '60-second transport-layer delay' making 'pyhss unreachable', which accurately describes the observable network behavior (extreme latency leading to unreachability/unresponsiveness). |
| Layer accuracy | Yes | The simulated failure states that 'pyhss' belongs to the 'ims' layer. The agent's network analysis correctly rated the 'ims' layer as 'red', indicating a problem within that layer. |
| Confidence calibrated | Yes | The agent stated 'high' confidence, which is appropriate given the accuracy and detailed evidence provided in its diagnosis (path walk, application-layer analysis, `tc` output). |

**Ranking position:** #1 — The agent provided a single, clear root cause, which was correct.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 194,113 |
| Output tokens | 7,322 |
| Thinking tokens | 21,700 |
| **Total tokens** | **223,135** |

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
| NetworkAnalystAgent | 49,528 | 3 | 2 |
| Phase 3 NetworkAnalyst__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 35,929 | 2 | 3 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 23,601 | 1 | 2 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| InvestigatorAgent_h1 | 28,283 | 3 | 2 |
| InvestigatorAgent_h1 | 54,227 | 3 | 4 |
| InvestigatorAgent_h1__reconciliation | 0 | 0 | 0 |
| Phase5FanOutAudit | 0 | 0 | 0 |
| Phase6.5CandidatePool | 0 | 0 | 0 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 15,864 | 0 | 1 |
| Phase 7 Synthesis__guardrail | 0 | 0 | 0 |
| SynthesisAgent | 15,703 | 0 | 1 |
| Phase 7 Synthesis__guardrail | 0 | 0 | 0 |
| Phase 7 Synthesis__guardrail | 0 | 0 | 0 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 459.2s
