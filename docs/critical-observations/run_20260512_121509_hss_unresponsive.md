# Episode Report: HSS Unresponsive

**Agent:** v7  
**Episode ID:** ep_20260512_120607_hss_unresponsive  
**Date:** 2026-05-12T12:06:09.334701+00:00  
**Duration:** 538.2s  

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

- **Wait:** 0s
- **Actual elapsed:** 0.0s
- **Nodes with significant deltas:** 4
- **Nodes with any drift:** 5

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 58.65 (per-bucket threshold: 26.31, context bucket (0, 1), trained on 323 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following metrics deviate from their learned-healthy baseline. Treat each as a semantic observation (meaning + numbers), not a number alone — the KB's interpretation is the authoritative reading.

- **`context.cx_active`** — current **0.00** vs learned baseline **0.59** (MEDIUM, drop). *(No KB context available — interpret from the metric name.)*

- **`derived.icscf_lir_timeout_ratio`** (I-CSCF LIR timeout ratio) — current **1.00 ratio** vs learned baseline **0.00 ratio** (MEDIUM, spike)
    - **What it measures:** Partial partition or severe overload on the Cx path during call routing. Zero in healthy operation; non-zero means some LIR queries did not receive a response within the timeout window.
    - **Spike means:** HSS partitioned during call setup, overloaded, or Cx path losing packets.
    - **Healthy typical range:** 0–0 ratio
    - **Healthy invariant:** Zero in healthy operation.

- **`derived.icscf_uar_timeout_ratio`** (I-CSCF UAR timeout ratio) — current **1.00 ratio** vs learned baseline **0.00 ratio** (MEDIUM, spike)
    - **What it measures:** Partial partition or severe overload on the Cx path. Zero in
healthy operation; non-zero means some UAR queries did not receive
any response within the timeout window.
    - **Spike means:** HSS partitioned, overloaded past its timeout, or Cx path losing packets.
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


## Symptom Classifier (Phase 0.5)

**Label:** `mixed`  
**Flag counts:** transport=0, application=0, ambiguous=10

### Ambiguous-bucket flags (10)

| Metric | Direction | Score | KB-driven reason |
|---|---|---:|---|
| `context.cx_active` | drop | 4.59 | no KB entry for context.cx_active — classification ambiguous |
| `derived.icscf_lir_timeout_ratio` | spike | 4.59 | KB-labeled mixed: ims.icscf.lir_timeout_ratio (spike, score=4.59) |
| `derived.icscf_uar_timeout_ratio` | spike | 4.59 | KB-labeled mixed: ims.icscf.uar_timeout_ratio (spike, score=4.59) |
| `normalized.icscf.cdp_replies_per_ue` | drop | 4.59 | KB-labeled mixed: ims.icscf.cdp_replies_per_ue (drop, score=4.59) |
| `normalized.icscf.core:rcv_requests_invite_per_ue` | spike | 4.59 | KB-labeled mixed: ims.icscf.rcv_requests_invite_per_ue (spike, score=4.59) |
| `normalized.icscf.core:rcv_requests_register_per_ue` | drop | 4.59 | KB-labeled mixed: ims.icscf.rcv_requests_register_per_ue (drop, score=4.59) |
| `normalized.pcscf.core:rcv_requests_invite_per_ue` | spike | 4.59 | KB-labeled mixed: ims.pcscf.rcv_requests_invite_per_ue (spike, score=4.59) |
| `normalized.pcscf.core:rcv_requests_register_per_ue` | drop | 4.59 | KB-labeled mixed: ims.pcscf.rcv_requests_register_per_ue (drop, score=4.59) |
| `normalized.scscf.cdp_replies_per_ue` | drop | 4.59 | KB-labeled mixed: ims.scscf.cdp_replies_per_ue (drop, score=4.59) |
| `normalized.scscf.core:rcv_requests_invite_per_ue` | spike | 4.59 | KB-labeled mixed: ims.scscf.rcv_requests_invite_per_ue (spike, score=4.59) |

**Rationale:**

```
label=mixed. 10 ambiguous signal(s) — KB labels them `mixed` or could not be resolved. Path walk runs first to attempt deterministic localization; falls through to the application-layer pipeline if no hop attribution is found.

Ambiguous signals: context.cx_active (drop, score=4.59) — no KB entry for context.cx_active — classification ambiguous; derived.icscf_lir_timeout_ratio (spike, score=4.59) — KB-labeled mixed: ims.icscf.lir_timeout_ratio (spike, score=4.59); derived.icscf_uar_timeout_ratio (spike, score=4.59) — KB-labeled mixed: ims.icscf.uar_timeout_ratio (spike, score=4.59); normalized.icscf.cdp_replies_per_ue (drop, score=4.59) — KB-labeled mixed: ims.icscf.cdp_replies_per_ue (drop, score=4.59); normalized.icscf.core:rcv_requests_invite_per_ue (spike, score=4.59) — KB-labeled mixed: ims.icscf.rcv_requests_invite_per_ue (spike, score=4.59) [+5 more]
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

**Status:** ⚠️ **null localization**
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

*Walker found no hop with attribution. Phase 0.6 returned None and the orchestrator fell through to the application-layer pipeline (Phases 1-7) below — the diagnosis you see in `Agent Diagnosis` came from that fallback path, not from Phase 0.6.*

## Event Aggregation (Phase 1)

No events fired during this episode. Either no metric KB triggers matched, or the episode encountered no meaningful state transitions.

## Correlation Analysis (Phase 2)

No events fired — correlation engine had nothing to work with.

## Network Analysis (Phase 3)

**Summary:** The IMS core is impaired due to the HSS being unresponsive on the Cx interface, causing Diameter timeouts at the I-CSCF and preventing user registration and call setup procedures.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | All relevant containers are running and network links are reported as active. |
| **ran** | 🟢 GREEN | No evidence of a RAN-layer fault. Signaling from UEs is reaching the P-CSCF. |
| **core** | 🟢 GREEN | Core network functions appear to be operating normally. |
| **ims** | 🔴 RED | The HSS is not responding to Diameter queries, leading to 100% timeout ratios from the I-CSCF and a drop in received replies at both I-CSCF and S-CSCF. This is preventing IMS registration and call setup. |

**IMS evidence:**
- derived.icscf_lir_timeout_ratio
- derived.icscf_uar_timeout_ratio
- normalized.icscf.cdp_replies_per_ue
- normalized.scscf.cdp_replies_per_ue

**Ranked hypotheses:**

- **`h1`** (fit=0.90, nf=pyhss, specificity=specific):
    - **Statement:** The HSS is the source of the anomalous Diameter behavior, failing to respond to Cx-interface requests from the I-CSCF and S-CSCF.
    - **Supporting events:** `derived.icscf_lir_timeout_ratio`, `derived.icscf_uar_timeout_ratio`, `normalized.icscf.cdp_replies_per_ue`, `normalized.scscf.cdp_replies_per_ue`
    - **Falsification probes:**
        - A live probe showing successful Diameter transactions between the I-CSCF and the HSS.
        - A network measurement (`measure_rtt`) from `icscf` to `pyhss` showing high packet loss, which would indicate a network partition is the cause rather than an HSS application fault.


## Falsification Plans (Phase 4)

**1 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `pyhss`)

**Hypothesis:** The HSS is the source of the anomalous Diameter behavior, failing to respond to Cx-interface requests from the I-CSCF and S-CSCF.

**Probes (3):**
1. **`check_process_listeners`** — container=pyhss
    - *Expected if hypothesis holds:* A process is listening on the Diameter port (e.g., TCP/3868).
    - *Falsifying observation:* No process is listening on the Diameter port.
2. **`measure_rtt`** — from=icscf, to_ip=pyhss
    - *Expected if hypothesis holds:* The measurement shows high latency or packet loss.
    - *Falsifying observation:* The measurement shows low latency and no packet loss.
3. **`measure_rtt`** — from=icscf, to_ip=scscf
    - *Expected if hypothesis holds:* The measurement shows low latency and no packet loss.
    - *Falsifying observation:* The measurement shows high latency or packet loss.

*Notes:* The NA report shows symptoms (icscf_lir_timeout_ratio, icscf_uar_timeout_ratio) consistent with step 1 of the 'diameter_cx_authentication' flow, where the HSS is unreachable for UAR/LIR requests. This plan attempts to distinguish between a network-layer partition to the HSS and an application-layer fault within the HSS.


## Parallel Investigators (Phase 5)

**1 sub-Investigator verdict(s):** **1 NOT_DISPROVEN**

### `h1` — ✅ **NOT_DISPROVEN**

**Hypothesis:** The HSS is the source of the anomalous Diameter behavior, failing to respond to Cx-interface requests from the I-CSCF and S-CSCF.

**Reasoning:** [Multi-shot consensus — both shots returned NOT_DISPROVEN.]

Shot 1: All executed probes produced evidence consistent with the hypothesis. Probes showed that the HSS container (`pyhss`) is unreachable from the I-CSCF (`icscf`) with 100% packet loss, while the I-CSCF can successfully reach the S-CSCF, pointing to a fault localized at the HSS. Furthermore, a process inside the HSS container was found listening on a non-standard port (3875 instead of the expected Diameter port 3868), which would prevent it from receiving Diameter requests.

Shot 2: All probes were consistent with the hypothesis. The HSS process is running and listening, but is unreachable at the network layer from the I-CSCF, exhibiting 100% packet loss. A triangulation probe from the I-CSCF to the S-CSCF was successful, which isolates the network issue to the HSS or its immediate network path, confirming it as the source of the unreachability.

**Probes executed (3):**
- **Check what ports and protocols the pyhss container's processes are listening on.** ✓ CONSISTENT
    - *Tool:* `check_process_listeners(container='pyhss')`
    - *Observation:* [EVIDENCE: check_process_listeners("pyhss") -> "tcp   LISTEN 0      100      172.22.0.18:3875       0.0.0.0:*    users:((\"python3\",pid=30,fd=6))     "]
    - *Comment:* The HSS is listening on port 3875, not the standard Diameter port 3868. This is consistent with the HSS being unable to respond to requests sent to the correct port.
- **Measure round-trip time and packet loss from icscf to pyhss.** ✓ CONSISTENT
    - *Tool:* `measure_rtt(container='icscf', target_ip='172.22.0.18')`
    - *Observation:* [EVIDENCE: measure_rtt("icscf", "172.22.0.18") -> "100% packet loss"]
    - *Comment:* The measurement shows 100% packet loss from icscf to pyhss. This is consistent with the hypothesis that the HSS is unreachable.
- **Measure round-trip time and packet loss from icscf to scscf.** ✓ CONSISTENT
    - *Tool:* `measure_rtt(container='icscf', target_ip='scscf')`
    - *Observation:* [EVIDENCE: measure_rtt("icscf", "scscf") -> "66 packets transmitted, 66 received, 0% packet loss"]
    - *Comment:* The measurement shows low latency and no packet loss between icscf and scscf. This result, when compared with the failure to reach pyhss, indicates that the icscf's networking is functional and the problem is specific to pyhss.


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

**Model:** v7-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 403.1s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: The IMS core is impaired because the HSS is unreachable and listening on the wrong port, causing Diameter timeouts and preventing user registration.
> - **timeline**:
>     1. The I-CSCF begins reporting 100% timeout ratios for Diameter User-Authorization-Request (UAR) and Location-Information-Request (LIR) messages sent to the HSS.
>     2. A corresponding drop in received Diameter replies is observed at both the I-CSCF and S-CSCF, indicating a failure at the HSS.
>     3. Investigation confirms 100% packet loss between the I-CSCF and the HSS container (`pyhss`), indicating a network reachability issue.
>     4. Further investigation reveals the process inside the `pyhss` container is listening on port 3875, not the standard Diameter port 3868.
> - **root_cause**: The HSS container (`pyhss`) is both unreachable at the network layer from the I-CSCF (100% packet loss) and has its main process listening on a non-standard port (3875 instead of 3868), making it unable to respond to Diameter requests. (primary_suspect_nf: `pyhss`)
> - **affected_components**:
>     - `pyhss`: Root Cause
>     - `icscf`: Symptomatic
>     - `scscf`: Symptomatic
> - **recommendation**: The operator should verify the network connectivity to the `pyhss` container and inspect its configuration to determine why it is unreachable from the I-CSCF and why its process is listening on port 3875 instead of the standard Diameter port 3868.
> - **confidence**: high
> - **verdict_kind**: confirmed
> - **explanation**: The Network Analyst identified an IMS fault caused by the HSS being unresponsive. The single hypothesis (h1) that the HSS was the source of the anomalous Diameter behavior was investigated and found to be NOT_DISPROVEN. Probes provided strong, consistent evidence: `measure_rtt` from the I-CSCF to the HSS showed 100% packet loss, while a control probe to the S-CSCF succeeded, isolating the network fault to the HSS. Additionally, `check_process_listeners` inside the HSS container found the Diameter process listening on the wrong port (3875 instead of 3868). This combination of network unreachability and incorrect port configuration fully explains why the HSS is not responding to requests from the I-CSCF, leading to registration failures. The evidence validation was clean.

### Scoring Breakdown

**Overall score: 100%**

**Scorer assessment:** The agent provided an excellent diagnosis, correctly identifying the root cause, affected component, severity, and fault type, with appropriate confidence and layer attribution.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | Yes | The simulated failure was extreme latency on the HSS, making it functionally unreachable and causing 100% packet loss for probes. The agent correctly identified the HSS as the root cause, stating it was 'unreachable at the network layer from the I-CSCF (100% packet loss)'. The additional finding about the wrong port, while not part of the simulation, is a plausible observation from the agent's perspective and does not detract from the correct identification of the simulated failure mode. |
| Component overlap | 100% | The agent correctly identified 'pyhss' (HSS) as the 'Root Cause' in its `affected_components` list, which is the primary affected component in the simulated failure. |
| Severity correct | Yes | The simulated failure resulted in functional unreachability and 100% packet loss, which is a complete outage. The agent's diagnosis of 'unreachable', '100% packet loss', and 'preventing user registration' accurately reflects this severe impact. |
| Fault type identified | Yes | The agent correctly identified the observable fault type as 'unreachable at the network layer' and '100% packet loss', which aligns with the simulated functional unreachability/unresponsiveness. |
| Layer accuracy | Yes | The ground truth states that 'pyhss' belongs to the 'ims' layer. The agent's network analysis correctly rated the 'ims' layer as 'red', indicating a problem within that layer. |
| Confidence calibrated | Yes | The agent's diagnosis is highly accurate and well-supported by the provided evidence (100% packet loss from measure_rtt, wrong port from check_process_listeners). A 'high' confidence level is appropriate. |

**Ranking position:** #1 — The agent provided a single, correct root cause in its final diagnosis.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 277,316 |
| Output tokens | 4,753 |
| Thinking tokens | 27,305 |
| **Total tokens** | **309,374** |

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
| NetworkAnalystAgent | 69,768 | 4 | 3 |
| Phase 3 NetworkAnalyst__guardrail | 0 | 0 | 0 |
| NetworkAnalystAgent | 57,735 | 3 | 4 |
| Phase 3 NetworkAnalyst__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 26,256 | 1 | 2 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 23,136 | 1 | 2 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| InvestigatorAgent_h1 | 60,039 | 3 | 4 |
| InvestigatorAgent_h1 | 64,286 | 3 | 4 |
| InvestigatorAgent_h1__reconciliation | 0 | 0 | 0 |
| Phase5FanOutAudit | 0 | 0 | 0 |
| Phase6.5CandidatePool | 0 | 0 | 0 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 8,154 | 0 | 1 |
| Phase 7 Synthesis__guardrail | 0 | 0 | 0 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 538.2s

---

## Post-run critical observation: RAG A/B comparison (2026-05-12)

This is the **RAG-OFF half** of a paired A/B against the same scenario. Both runs scored 100%, but for very different reasons. The full per-run cost and quality differences below are dominated by **state-bucket variance**, not by RAG injection state. The comparison highlights three structural issues worth surfacing independent of the RAG question itself.

### Side-by-side with the RAG-ON run (run_20260512_082224_hss_unresponsive)

| Metric | RAG-ON (08:22) | **RAG-OFF (this run)** | Delta |
|---|---:|---:|---|
| Score | 100% | **100%** | same |
| **Total tokens** | **530K** | **309K** | **−42%** (RAG-OFF cheaper) |
| Duration | 614s | 538s | −12% |
| State bucket | `(1, 1)` calls+reg | `(0, 1)` reg-only | **different** |
| Classifier label | `transport_layer` | `mixed` | RAG-OFF more conservative |
| Resolver pick | `data_pdu_session_user_traffic` ❌ | **`ims_registration` ✓** | RAG-OFF correct |
| Walker hops | 11 (wrong path) | 41 (right path — pyhss walked 3×) | RAG-OFF correct |
| Walker outcome | null-localized | **null-localized (despite walking pyhss)** | **same — see point 3** |
| NA hypotheses | 3 (pyhss h1, dns h2, upf h3) | **1 (pyhss h1 only)** | RAG-OFF focused |
| Investigator h1 verdict | INCONCLUSIVE (shots disagreed) | **NOT_DISPROVEN (both shots agreed)** | RAG-OFF cleaner |
| Re-investigation needed? | Yes (~63K tokens on it) | No | RAG-OFF efficient |
| measure_rtt(icscf, pyhss) | `0% loss` against `172.22.0.8` (wrong IP) | `100% loss` against `172.22.0.18` (correct pyhss IP) | RAG-OFF probed right target |
| Final confidence | medium | high | — |

### What actually drove the difference — three findings, only one of them about RAG

#### 1. State-bucket variance dominates

The two runs landed in **different state buckets** in the screener:
- 08:22 RAG-ON: bucket `(1, 1)` — calls active + registration in progress
- 12:15 RAG-OFF: bucket `(0, 1)` — no calls, just registration

The bucket is determined by what the stack was doing at the moment of screening, not by RAG. In bucket `(1, 1)`, the learned baselines for UPF GTP per-UE rates are higher than in `(0, 1)`. So when the chaos fault stalled signaling and call setup:

- In `(1, 1)`: UPF GTP rates dropped *relative to the high-baseline bucket value* enough to register as `spike` (current 2.41 vs learned 1.45). Plus `upf_activity_during_calls` dropped from 0.54 → 0.05. Three KB-`transport`-labeled flags → classifier said `transport_layer` → resolver was pulled toward UPF-traversing flows (`data_pdu`) and away from `ims_registration`.
- In `(0, 1)`: UPF rates barely moved (the `(0, 1)` baseline is closer to "no traffic"), so they weren't flagged. The screener emitted only IMS signaling flags, all KB-`mixed` → 10 ambiguous, 0 transport, 0 application → classifier said `mixed` → resolver weighed all candidates equally → `ims_registration` tied with two others at score 6 and won the tiebreaker.

**This is B4 (from `docs/work-plan-may-11.md`) biting in two different ways across the two runs.** B4 said "UPF over-flagging in bucket `(0, 1)` produces wrong-flow routing on HSS-side faults." Today's RAG-ON run showed a *symmetric variant*: UPF spike-flagging in `(1, 1)` pulling the resolver to `data_pdu`. The RAG-OFF run got lucky and landed in `(0, 1)` where the (mis-trained) `(0, 1)` baseline happened to *not* over-flag UPF on this particular run.

**The "resolver picked the right flow" win for RAG-OFF is a screener-state-baseline effect, not a RAG effect.** RAG injection sits downstream of the screener and resolver; it cannot influence either's output.

#### 2. The Investigator pinged the right IP in RAG-OFF and got the smoking gun

- **RAG-ON h1:** `measure_rtt("icscf", "172.22.0.8")` → 0% packet loss, 0.095ms RTT. Conclusion: "pyhss reachable at network layer."
- **RAG-OFF h1:** `measure_rtt("icscf", "172.22.0.18")` → 100% packet loss. Conclusion: "pyhss unreachable."

`172.22.0.18` is pyhss's actual IP (the `check_process_listeners` output in both runs confirms it). **`172.22.0.8` is some other container** (likely AMF). In the RAG-ON run the Investigator pinged the wrong target, got clean results, and was led astray into reasoning about port-binding faults. In the RAG-OFF run it pinged the correct target and got the smoking gun.

This is an LLM autonomous-choice variable, not a RAG variable — lessons are NA-only, not Investigator. The "100% packet loss" reading is functionally correct for the timeout window question but masks the actual mechanism (60s deferral, not packet loss). The ping command's per-packet timeout (~10s default) fires long before the 60s-deferred replies arrive, so each one shows up as "lost."

The agent's diagnosis of "100% packet loss / pyhss unreachable" is also functionally correct for the timeout-window question, but it's not the underlying mechanism. The scorer accepts it as semantically equivalent.

#### 3. The walker walked pyhss in RAG-OFF and STILL reported clean — separate bug

The most operationally interesting finding. In RAG-OFF, the resolver picked `ims_registration` (the right flow). The walker walked 41 hops, **including `pyhss[eth0]` at hops 16, 22, and 26**. All three reported `clean`.

But the injected qdisc is sitting right there: `tc qdisc add dev eth0 root netem delay 60000ms`. The `KernelHopProber`'s `tc -s qdisc show dev eth0` command should return `qdisc netem ... delay 60.0s`, which the parser supports — `_parse_netem_delay_ms` exists in `agentic_ops/tools.py:1022`, and the `LatencyAtHop` HopAttribution variant exists in `agentic_ops_common.path_walk.protocol`. The `rtpengine_latency_injection` unit test exercises this code path.

So one of:

- The prober checks only for `drops_attributed_here` (loss-counter movements) and doesn't surface `delay`-only qdiscs in live mode, OR
- The prober parses delay correctly in unit-test fixtures but mis-parses the live `tc` output (format drift), OR
- The prober reaches pyhss via a different mechanism than the unit test expects (`docker exec` vs `nsenter`) and reads a different namespace, OR
- Some other implementation gap.

**This is a separate, high-leverage bug.** If the walker had emitted `LatencyAtHop(observed_delay_ms=60000, counter_kind=qdisc_netem_delay)` at hop 16, Synthesis would have produced a clean localized verdict in ~10K tokens and the entire app-layer pipeline (200K+ tokens) wouldn't have run. Worth a focused code review of `agentic_ops_common/path_walk/probers/kernel.py`.

### The Investigator's tool-access gap (from earlier session)

Even if the walker continues to miss delay-only netem qdiscs, the Investigator could in principle detect this fault directly via `check_tc_rules(container='pyhss')` — a tool that exists in `agentic_ops/tools.py:756` with the docstring:

> **CRITICAL: Call this FIRST on any container showing timeouts or slow responses.** A tc netem rule is the #1 cause of latency-induced timeouts in this environment.

But `check_tc_rules`, `get_qdisc_drops`, and `get_interface_drops` are **all absent from the v7 Investigator's tool list** (`agentic_ops_v7/subagents/investigator.py:47-101`). The deliberate architectural decision per [`docs/ADR/path_anchored_probe_planning_for_transport_layer_faults.md`](../../../docs/ADR/path_anchored_probe_planning_for_transport_layer_faults.md) is that kernel-level transport detection is the path-walker's job, not the LLM Investigator's. The v3 `TransportSpecialist` agent had these tools and they worked, but were sometimes used on the wrong container.

The gap this creates: when the walker mis-routes (B1 / F1 follow-up) OR misses an attribution type it should have caught (point 3 above), the Investigator has no fallback tool to recover the kernel evidence. Today's RAG-OFF run hit *both* limitations and still scored 100% only because:
- The Investigator picked the correct pyhss IP for `measure_rtt` (luck)
- The 100% packet loss reading was a functionally-correct signal for "pyhss unreachable" (proximate cause)
- The scorer is lenient on mechanism mismatch when the affected NF is right

### Honest verdict on the A/B

With n=1 RAG-ON + n=1 RAG-OFF run:

- **RAG didn't help here.** RAG-OFF spent 42% fewer tokens and produced a more focused investigation.
- **The variation between the two runs is dominated by state-bucket effects, not by RAG.** Different bucket → different screener flags → different classifier label → different resolver pick. RAG injection sits downstream of all that.
- **The RAG-OFF run benefited from two pieces of luck unrelated to RAG:** (a) landing in bucket `(0, 1)` where UPF didn't over-flag, and (b) the Investigator picking the correct pyhss IP. Either could go the other way on a re-run.

I would *not* draw "RAG hurts" from this. Three honest possibilities all consistent with the data:

1. RAG genuinely doesn't help on this scenario — the NA already has enough signal to reach pyhss from `icscf_uar_timeout_ratio = 1.0` alone. Lessons inflate the prompt and trigger more guardrail-rejection resamples.
2. RAG helps mildly; the bucket effect dominated; RAG-ON nudged the NA toward broader exploration (3 hypotheses) which cost tokens but didn't change the answer.
3. RAG hurts modestly — the 14K-char lessons block plus retrieved cases inflate the NA prompt enough to push it into multi-hypothesis mode when single-hypothesis would have sufficed.

To distinguish these, 3-5 paired runs with the bucket pinned (prime the stack into `(0, 1)` before each by holding back call setup) and compare medians.

### Follow-ups in priority order

1. **Investigate the KernelHopProber missing the netem delay on pyhss.** Highest-leverage finding. A 1-hour code review of `agentic_ops_common/path_walk/probers/kernel.py` could turn HSS-style scenarios into 10K-token localized wins instead of 300-530K-token app-layer slogs.
2. **Pin state-bucket variance before more A/B-ing RAG.** Single-pair A/B with uncontrolled bucket variance is statistical noise.
3. **Run the rest of the batch with RAG ON.** Other scenarios (rtpengine_latency, p_cscf_latency, ims_network_partition) may benefit differently. Don't decide RAG from one scenario.
4. **Consider re-exposing `check_tc_rules` to the Investigator as a backstop** for cases where the walker mis-routes or misses an attribution type. ~3 LOC change. Re-opens a small attack surface (LLM picks wrong container) but recovers the kernel-evidence visibility on the most common chaos-fault class. Pair with a lesson teaching the Investigator when to call it.

---

## Addendum (2026-05-12): Follow-up #1 — root cause found and fixed

The walker-missed-delay bug was traced to a single regex in `agentic_ops/tools.py::_parse_netem_delay_ms`. The pre-fix code hard-coded the `ms` suffix:

```python
m = _re.search(r"delay\s+([\d.]+)\s*ms", raw)
```

But `tc -s qdisc show` auto-scales the time unit (see iproute2's `__print_size_str` in `lib/utils.c`):

  - sub-millisecond → `us` (microseconds)
  - sub-second      → `ms`
  - second and above → `s`

So `tc qdisc add … netem delay 60000ms` is shown by `tc` as `delay 60.0s`, NOT `delay 60000.0ms`. The `ms`-only regex returned `None` for every delay ≥ 1 second. The KernelHopProber's `LatencyAtHop` branch never fired, the prober fell through to `CleanHop`, and the walker null-localized despite walking pyhss[eth0] three times.

The existing unit test covered only the `100.0ms` case (the `rtpengine_latency_injection` scenario, which injects 100 ms — the one unit the regex happened to match), so this regression sat undetected since the parser was written.

**Fix shipped same day.** New parser:

```python
m = _re.search(r"delay\s+([\d.]+)\s*(us|ms|ns|ps|s)\b", raw)
```

Captures the unit, normalizes to milliseconds:

- `us` → ÷ 1,000
- `ms` → ×1
- `s`  → × 1,000
- `ns` → ÷ 1,000,000
- `ps` → ÷ 1,000,000,000

Two-character units are listed before single-char `s` so the regex engine prefers `ms` over `s` when both match — Python alternates left-to-right.

**New test coverage (18 cases) pinned in `agentic_ops_common/tests/test_path_walk_probes.py`:**

- Parametrized table over `us`, `ms`, `s`, `ns` formats including decimal values.
- Jitter format: `delay 100.0ms 25.0ms 50%` — parser correctly extracts the central delay, ignores the jitter.
- Direct regression pin for the live HSS Unresponsive failure: `delay 60.0s` → `60000.0`.
- Non-delay outputs return `None` (fq_codel, noqueue, empty, etc.).

**Test state after fix:** 803 passed, 48 skipped, 3 xfailed across the full v7 + common suites. No other tests regressed.

### Expected impact on the next HSS Unresponsive run

With the parser fixed, a re-run of `HSS Unresponsive` (60-second netem delay on pyhss) should:

1. Walker walks `ims_registration` flow (assuming the resolver routes correctly, as it did in the RAG-OFF run).
2. KernelHopProber reaches pyhss[eth0] at hop 16, runs `tc -s qdisc show dev eth0`, sees `delay 60.0s`, parser returns `60000.0`.
3. Branch at `kernel.py:124` fires: `LatencyAtHop(observed_delay_ms=60000.0, counter_kind="qdisc_netem_delay", evidence=<verbatim tc output>)`.
4. Walker emits `is_localized=True` with `first_attributed_hop=pyhss[eth0]`.
5. Synthesis takes the localized branch, emits `verdict_kind=localized, primary_suspect_nf=pyhss, observed_delay_ms=60000ms, root_cause=Kernel-level 60-second egress delay on pyhss[eth0]`.
6. **Cost: ~10K tokens** (single Synthesis call, no app-layer pipeline).

That's a 30-50× token reduction vs. either previous HSS Unresponsive run, with a more mechanism-faithful diagnosis (the actual fault is netem latency, not "port-binding failure" or "100% packet loss").

Caveat: this assumes the resolver routes to `ims_registration` (RAG-OFF bucket-(0,1) path). The RAG-ON run in bucket-(1,1) routed to `data_pdu_session_user_traffic`, which doesn't include pyhss as a hop, so the walker wouldn't reach pyhss regardless of the parser. The B4 (screener over-flagging) follow-up still controls whether the walker gets the chance to fire on this scenario.

### What this episode's investigation reveals about test discipline

The pre-fix parser passed every existing unit test. The bug surfaced only when a chaos scenario injected a delay magnitude that the test fixtures didn't cover. The lesson is **test fixtures must cover the *range* of inputs the production system actually produces, not just one representative value.** A single-magnitude test that happens to match the kernel's unit-scaling boundary on the unlucky side fails silently and indefinitely.

The fix added a parametrized table covering every unit the kernel can emit, including a direct pin for the exact live-failure case. The principle: when a parser handles auto-scaling inputs, every scale should appear in the test corpus.
