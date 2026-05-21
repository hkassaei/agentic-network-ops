# Episode Report: AMF Restart (Upgrade Simulation)

**Agent:** v7  
**Episode ID:** ep_20260521_130333_amf_restart_(upgrade_simulatio  
**Date:** 2026-05-21T13:03:34.799513+00:00  
**Duration:** 402.2s  

---

## Scenario

**Category:** container  
**Blast radius:** multi_nf  
**Description:** Stop the AMF for 10 seconds, then restart it. Simulates a rolling upgrade of the access and mobility management function. UEs will temporarily lose their 5G NAS connection and must re-attach.

## Faults Injected

- **container_stop** on `amf` — {'timeout': 10}

## Baseline (Pre-Fault)

Stack phase before injection: **ready**
All containers running at baseline.

## Fault Propagation Verification

**Verdict:** ✅ `confirmed`

- **Propagation window:** 137s (ObservationTrafficAgent drove traffic for this window; verifier added wait=0s on top)
- **Nodes with significant deltas:** 4
- **Nodes with any drift:** 5

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 48.96 (per-bucket threshold: 26.31, context bucket (0, 1), trained on 323 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following metrics deviate from their learned-healthy baseline. Treat each as a semantic observation (meaning + numbers), not a number alone — the KB's interpretation is the authoritative reading.

- **`normalized.icscf.core:rcv_requests_invite_per_ue`** (SIP INVITE rate per UE at I-CSCF) — current **0.01 requests_per_second** vs learned baseline **0.00 requests_per_second** (MEDIUM, spike)
    - **What it measures:** Health of call-setup forwarding P-CSCF → I-CSCF. Partition signature
same as REGISTER rate.
    - **Spike means:** Forwarding failure.
    - **Healthy typical range:** 0–0.2 requests_per_second
    - **Healthy invariant:** Per-UE rate. Tracks pcscf.invite rate.

- **`normalized.pcscf.core:rcv_requests_invite_per_ue`** (SIP INVITE rate per UE at P-CSCF) — current **0.03 requests_per_second** vs learned baseline **0.00 requests_per_second** (MEDIUM, spike)
    - **What it measures:** Call attempt rate from registered UEs. Unlike REGISTER (periodic),
INVITEs only fire when UEs place calls. Zero is normal during
quiet periods; nonzero INVITE with zero dialogs is the signature
of call setup failure.
    - **Spike means:** Fewer call attempts.
    - **Healthy typical range:** 0–0.2 requests_per_second
    - **Healthy invariant:** Per-UE rate.

- **`normalized.scscf.core:rcv_requests_invite_per_ue`** (SIP INVITE rate per UE at S-CSCF) — current **0.03 requests_per_second** vs learned baseline **0.00 requests_per_second** (MEDIUM, spike)
    - **What it measures:** S-CSCF participation in call setup. Zero when calls aren't being
placed OR S-CSCF not receiving forwarded INVITEs.
    - **Spike means:** Upstream forwarding issue.
    - **Healthy typical range:** 0–0.2 requests_per_second
    - **Healthy invariant:** Per-UE rate.

- **`normalized.smf.bearers_per_ue`** (Active QoS bearers per UE) — current **0.00 count** vs learned baseline **2.48 count** (MEDIUM, drop)
    - **What it measures:** Per-UE count of active QoS bearers. Baseline reflects default
bearers; increments during VoNR calls indicate dedicated voice
bearers being set up. Drop during an active call = dedicated
bearer torn down unexpectedly (voice will fail).
    - **Drop means:** Lost bearers. If sustained during a call, voice path is broken.
    - **Healthy typical range:** 2–3.5 count
    - **Healthy invariant:** At rest: equals configured default bearers (typically 2 per UE).
During active VoNR call: +1 per caller. The per-UE ratio is the
invariant; absolute count scales with UE pool.

- **`normalized.smf.sessions_per_ue`** (PDU sessions per attached UE) — current **0.00 count** vs learned baseline **2.00 count** (MEDIUM, drop)
    - **What it measures:** Ratio of established PDU sessions to RAN-attached UEs. Constant under
healthy operation (depends on configured APNs per UE). Drift means
some UEs lost or failed to establish their sessions — usually points
to SMF or UPF control-plane issues, since attachment (ran_ue) is
independent of session establishment.
    - **Drop means:** Some UEs have fewer PDU sessions than they should. Likely SMF or PFCP (N4) issues.
    - **Healthy typical range:** 1.9–2.1 count
    - **Healthy invariant:** Constant equal to configured_apns_per_ue (typically 2). Scale-independent.

- **`normalized.upf.gtp_indatapktn3upf_per_ue`** (GTP-U uplink rate per UE (N3)) — current **0.00 packets_per_second** vs learned baseline **1.45 packets_per_second** (HIGH, drop)
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

- **`normalized.upf.gtp_outdatapktn3upf_per_ue`** (GTP-U downlink rate per UE (N3)) — current **0.00 packets_per_second** vs learned baseline **1.45 packets_per_second** (HIGH, drop)
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


## Symptom Classifier (Phase 0.5)

**Label:** `mixed`  
**Flag counts:** transport=2, application=2, ambiguous=6

### Transport-bucket flags (2)

| Metric | Direction | Score | KB-driven reason |
|---|---|---:|---|
| `normalized.upf.gtp_indatapktn3upf_per_ue` | drop | 4.59 | KB-labeled transport: core.upf.gtp_indatapktn3upf_per_ue (drop, score=4.59) |
| `normalized.upf.gtp_outdatapktn3upf_per_ue` | drop | 4.59 | KB-labeled transport: core.upf.gtp_outdatapktn3upf_per_ue (drop, score=4.59) |

### Application-bucket flags (2)

| Metric | Direction | Score | KB-driven reason |
|---|---|---:|---|
| `normalized.smf.bearers_per_ue` | drop | 4.59 | KB-labeled application: core.smf.bearers_per_ue (drop, score=4.59) |
| `normalized.smf.sessions_per_ue` | drop | 4.59 | KB-labeled application: core.smf.sessions_per_ue (drop, score=4.59) |

### Ambiguous-bucket flags (6)

| Metric | Direction | Score | KB-driven reason |
|---|---|---:|---|
| `normalized.icscf.core:rcv_requests_invite_per_ue` | spike | 4.59 | KB-labeled mixed: ims.icscf.rcv_requests_invite_per_ue (spike, score=4.59) |
| `normalized.pcscf.core:rcv_requests_invite_per_ue` | spike | 4.59 | KB-labeled mixed: ims.pcscf.rcv_requests_invite_per_ue (spike, score=4.59) |
| `normalized.scscf.core:rcv_requests_invite_per_ue` | spike | 4.59 | KB-labeled mixed: ims.scscf.rcv_requests_invite_per_ue (spike, score=4.59) |
| `normalized.icscf.core:rcv_requests_register_per_ue` | drop | 3.50 | KB-labeled mixed: ims.icscf.rcv_requests_register_per_ue (drop, score=3.50) |
| `normalized.pcscf.core:rcv_requests_register_per_ue` | drop | 3.50 | KB-labeled mixed: ims.pcscf.rcv_requests_register_per_ue (drop, score=3.50) |
| `normalized.scscf.cdp_replies_per_ue` | drop | 3.50 | KB-labeled mixed: ims.scscf.cdp_replies_per_ue (drop, score=3.50) |

**Rationale:**

```
label=mixed. Both transport-layer (2) and application-layer (2) signals are load-bearing. Path walk runs first; falls through to the application-layer pipeline if the walk produces null localization.

Transport signals: normalized.upf.gtp_indatapktn3upf_per_ue (drop, score=4.59) — KB-labeled transport: core.upf.gtp_indatapktn3upf_per_ue (drop, score=4.59); normalized.upf.gtp_outdatapktn3upf_per_ue (drop, score=4.59) — KB-labeled transport: core.upf.gtp_outdatapktn3upf_per_ue (drop, score=4.59)

Application signals: normalized.smf.bearers_per_ue (drop, score=4.59) — KB-labeled application: core.smf.bearers_per_ue (drop, score=4.59); normalized.smf.sessions_per_ue (drop, score=4.59) — KB-labeled application: core.smf.sessions_per_ue (drop, score=4.59)

Ambiguous signals: normalized.icscf.core:rcv_requests_invite_per_ue (spike, score=4.59) — KB-labeled mixed: ims.icscf.rcv_requests_invite_per_ue (spike, score=4.59); normalized.pcscf.core:rcv_requests_invite_per_ue (spike, score=4.59) — KB-labeled mixed: ims.pcscf.rcv_requests_invite_per_ue (spike, score=4.59); normalized.scscf.core:rcv_requests_invite_per_ue (spike, score=4.59) — KB-labeled mixed: ims.scscf.rcv_requests_invite_per_ue (spike, score=4.59); normalized.icscf.core:rcv_requests_register_per_ue (drop, score=3.50) — KB-labeled mixed: ims.icscf.rcv_requests_register_per_ue (drop, score=3.50); normalized.pcscf.core:rcv_requests_register_per_ue (drop, score=3.50) — KB-labeled mixed: ims.pcscf.rcv_requests_register_per_ue (drop, score=3.50) [+1 more]
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
Resolved transport path to flow `data_pdu_session_user_traffic` (score=12, 11 hops on the walk). Load-bearing components: ['icscf', 'pcscf', 'scscf', 'smf', 'upf']. Other candidate flows considered: vonr_media=12, ims_registration=8, vonr_call_teardown=8, vonr_call_setup=8.
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

**1 events fired during the observation window:**

- `core.smf.sessions_per_ue_drop` (source: `core.smf.sessions_per_ue`, nf: `smf`, t=1779368744.4)  [current_value=0.0, prior_stable_value=2.0, delta_percent=-100.0]

## Correlation Analysis (Phase 2)

1 events fired but no composite hypothesis emerged. The events may be from independent faults or lack registered correlation hints in the KB.

## RAG & Operational Lessons (Phase 2.5)

### RAG retrieval — prior similar episodes

**Status:** `hits` — hits=5, top_sim=0.93, top_case=v7/ep_20260510_200052_amf_restart_(upgrade_simulatio
**Index:** `/home/ehoskas/agentic-network-ops/rag_index`  **Corpus size:** 102 cases
**Classifier label used in retrieval:** `mixed`
**Retrieval params:** k=5, min_similarity=0.4
**Hits (5):**

| Rank | Sim | Case ID | Scenario | Ground truth | Primary suspect | Score |
|---:|---:|---|---|---|---|---:|
| 0 | 93% | `v7/ep_20260510_200052_amf_restart_(upgrade_simulatio` | AMF Restart (Upgrade Simulation) | `amf` | `amf` | 100% |
| 1 | 91% | `v6/ep_20260429_165324_amf_restart_(upgrade_simulatio` | AMF Restart (Upgrade Simulation) | `amf` | `amf` | 100% |
| 2 | 88% | `v7/ep_20260510_183211_data_plane_degradation` | Data Plane Degradation | `upf` | `upf` | 100% |
| 3 | 84% | `v7/ep_20260510_115059_data_plane_degradation` | Data Plane Degradation | `upf` | `upf` | 100% |
| 4 | 83% | `v7/ep_20260510_184035_p_cscf_packet_loss` | P-CSCF Packet Loss | `pcscf` | `pcscf` | 100% |

*Rendered block injected into the NA prompt's `{prior_similar_episodes}` placeholder: 4963 chars. Source paths are inlined in the block so the EvidenceValidator can audit any case the NA cites.*

### Operational lessons — hand-authored rules corpus

**Status:** `injected` — lessons=16, chars=15678
**Path:** `/home/ehoskas/agentic-network-ops/agentic_ops_common/rag/lessons.yaml`  **Count:** 16  **Block size:** 15678 chars
**Injected lesson IDs:** `L01`, `L02`, `L03`, `L04`, `L05`, `L06`, `L07`, `L08`, `L09`, `L10`, `L11`, `L12`, `L13`, `L14`, `L15`, `L16`

### NA citations of the injected content

**Cited lesson IDs:**
- `L10`

*Citations are verbatim string matches — case_ids and lesson_ids appear in the NA's emitted text (summary, hypothesis statements, or layer notes). The EvidenceValidator can audit any cited case by following its `source_episode_path` from the retrieval table above.*

## Network Analysis (Phase 3)

**Summary:** The AMF container has exited (L10), tearing down the 5G control plane and dropping all UE attachments; the anomaly flags at SMF, UPF, P-CSCF, I-CSCF, and S-CSCF are demoted as downstream consequences and secondary symptoms of this upstream starvation.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🔴 RED | The amf container process has stopped running. |
| **ran** |   |  |
| **core** | 🔴 RED | Complete 5G control plane collapse at the AMF severs all UE connections, directly causing the SMF and UPF data plane symptoms. |
| **ims** | 🟡 YELLOW | IMS components are passively reporting starvation; they are unreachable by UEs due to the upstream RAN/AMF failure. |

**INFRASTRUCTURE evidence:**
- get_network_status() shows amf as exited

**CORE evidence:**
- AMF container is in 'exited' state
- SMF bearers_per_ue and sessions_per_ue dropped to 0
- UPF gtp_indatapktn3upf_per_ue and gtp_outdatapktn3upf_per_ue dropped to 0

**IMS evidence:**
- P-CSCF, I-CSCF, and S-CSCF REGISTER rates dropped to near zero
- S-CSCF CDP replies per UE dropped
- CSCF INVITE rates flagged as anomalous

**Ranked hypotheses:**

- **`h1`** (fit=0.99, nf=amf, specificity=specific):
    - **Statement:** The AMF is the source of the total network failure, as its container has exited, resulting in a complete teardown of the 5G control plane and detachment of all UEs (L10).
    - **Supporting events:** `core.smf.sessions_per_ue_drop`
    - **Falsification probes:**
        - Verify `get_network_status()` continues to report the AMF container as exited or down.
        - Check AMF container logs for crash or out-of-memory (OOM) kill signatures.


## Falsification Plans (Phase 4)

**1 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `amf`)

**Hypothesis:** The AMF is the source of the total network failure, as its container has exited, resulting in a complete teardown of the 5G control plane and detachment of all UEs (L10).

**Probes (3):**
1. **`get_network_status`** — Check the status of the amf container in the topology.
    - *Expected if hypothesis holds:* The amf container is reported as exited or down.
    - *Falsifying observation:* The amf container is reported as running.
2. **`check_process_listeners`** — amf
    - *Expected if hypothesis holds:* The tool returns an error or empty list because the amf container is inaccessible or stopped.
    - *Falsifying observation:* The tool successfully returns active listening ports for the amf container.
3. **`get_network_status`** — Check the status of the nr_gnb container.
    - *Expected if hypothesis holds:* The nr_gnb container is reported as running, meaning the outage is not due to a total infrastructure failure encompassing RAN.
    - *Falsifying observation:* The nr_gnb container is reported as exited or down.

*Notes:* Verified container exit via get_network_status and process listeners. Avoiding compositional measure_rtt probes since container down state can be directly observed.


## Parallel Investigators (Phase 5)

**1 sub-Investigator verdict(s):** **1 NOT_DISPROVEN**

### `h1` — ✅ **NOT_DISPROVEN**

**Hypothesis:** The AMF is the source of the total network failure, as its container has exited, resulting in a complete teardown of the 5G control plane and detachment of all UEs (L10).

**Reasoning:** [Multi-shot consensus — both shots returned NOT_DISPROVEN.]

Shot 1: The get_network_status probe explicitly reports the amf container in an 'exited' state, confirming the mechanism of failure proposed in the hypothesis. The check_process_listeners probe was unable to execute due to missing binaries, but the container's exited state combined with the running state of the rest of the infrastructure supports the hypothesis without contradiction.

Shot 2: The hypothesis holds up to falsification testing. Evidence from get_network_status directly confirms that the amf container is in an 'exited' state while other infrastructure components remain running. The check_process_listeners probe could not execute on the amf container due to a missing binary (tool_unavailable), so it produced no contradicting signal. Because the container is verifiably down, the hypothesis that an AMF container crash is the root cause is not disproven.

**Probes executed (3):**
- **Check the status of the amf container in the topology.** ✓ CONSISTENT
    - *Tool:* `get_network_status()`
    - *Observation:* [EVIDENCE: get_network_status() -> "\"amf\": \"exited\""]
    - *Comment:* The container status directly confirms that the AMF has exited, corroborating the hypothesis.
- **amf** ~ AMBIGUOUS
    - *Tool:* `check_process_listeners("amf")`
    - *Observation:* [EVIDENCE: check_process_listeners("amf") -> "PROBE_TOOL_UNAVAILABLE: check_process_listeners cannot run on container `amf`"]
    - *Comment:* The probe could not run because the required binary is missing from the container image. Treated as no evidence.
- **Check the status of the nr_gnb container.** ✓ CONSISTENT
    - *Tool:* `get_network_status()`
    - *Observation:* [EVIDENCE: get_network_status() -> "\"down_or_absent\": [\n    \"amf\"\n  ]"]
    - *Comment:* nr_gnb is not listed among down containers, and the rest of the core infrastructure is confirmed running, indicating this is an isolated failure of the AMF container rather than a total node outage.


## Evidence Validation (Phase 6)

**Overall verdict:** clean
**Overall confidence:** high

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 6 | 3/3 | clean | high |


## Ground Truth

**Failure domain:** core_control_plane  
**Protocol impact:** NGAP  
**Affected components:** amf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v7-adk/pro=gemini-3.1-pro-preview+flash=gemini-3.5-flash  
**Time to diagnosis:** 256.2s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: The 5G core network is experiencing a complete control plane collapse due to the AMF container unexpectedly exiting, which drops all UE attachments and starves downstream components.
> - **timeline**:
>     1. AMF container process stops running and enters an exited state.
>     2. The 5G control plane drops all UE attachments (core.smf.sessions_per_ue_drop).
>     3. Downstream data plane components (SMF, UPF) and IMS components (P-CSCF, I-CSCF, S-CSCF) passively report starvation.
> - **root_cause**: The AMF container process has exited, leading to a total teardown of the 5G control plane and detachment of all UEs. (primary_suspect_nf: `amf`)
> - **affected_components**:
>     - `amf`: Root Cause
>     - `smf`: Symptomatic
>     - `upf`: Symptomatic
>     - `pcscf`: Symptomatic
>     - `icscf`: Symptomatic
>     - `scscf`: Symptomatic
> - **recommendation**: Verify the AMF container logs to identify the crash reason or OOM kill signature (`docker logs amf`), and check host resource constraints.
> - **confidence**: medium
> - **verdict_kind**: confirmed
> - **explanation**: The AMF container has been verified to be in an 'exited' state via network status probes. Because the AMF is the entry point for all 5G control plane signaling, its failure severs all UE connections and tears down the network's control plane. This upstream starvation cascades, causing the SMF, UPF, and IMS core components to report secondary symptoms and anomaly flags. The primary hypothesis (h1) was confirmed by directly observing the exited state of the AMF container while confirming the rest of the infrastructure (like nr_gnb) remains running. Confidence is bounded to medium because an internal process listener check produced an ambiguous outcome (tool unavailable), though the external state confirmation is decisive.

### Scoring Breakdown

**Overall score: 100%**

**Scorer assessment:** The agent perfectly diagnosed the AMF failure, correctly identifying the root cause, affected component, severity, and layer ontology with well-calibrated confidence.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | Yes | The agent correctly identified that the AMF container had exited/stopped, which is semantically equivalent to the simulated AMF restart/temporary unavailability. |
| Component overlap | 100% | The agent correctly identified 'amf' as the primary affected component and labeled it as the 'Root Cause' in the affected components list. |
| Severity correct | Yes | The agent correctly identified the severity as a complete control plane collapse and teardown of UE attachments, which matches the complete outage of the AMF during its down period. |
| Fault type identified | Yes | The agent correctly identified the fault type as a component being down/unreachable ('AMF container process has exited'). |
| Layer accuracy | Yes | The agent correctly rated the 'core' layer as RED and attributed the AMF failure to it, matching the ontology where AMF belongs to the core layer. |
| Confidence calibrated | Yes | The agent's confidence is appropriately calibrated to 'medium' because it confirmed the container's exited state but noted that some internal process checks were unavailable. |

**Ranking position:** #1 — The correct root cause (AMF failure) was identified as the primary suspect and ranked first.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 309,325 |
| Output tokens | 3,567 |
| Thinking tokens | 13,013 |
| **Total tokens** | **325,905** |

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
| NetworkAnalystAgent | 228,960 | 8 | 7 |
| Phase 3 NetworkAnalyst__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 9,755 | 0 | 1 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 10,599 | 0 | 1 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| InvestigatorAgent_h1 | 26,331 | 2 | 2 |
| InvestigatorAgent_h1 | 38,871 | 4 | 3 |
| InvestigatorAgent_h1__reconciliation | 0 | 0 | 0 |
| Phase5FanOutAudit | 0 | 0 | 0 |
| Phase6.5CandidatePool | 0 | 0 | 0 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 11,389 | 0 | 1 |
| Phase 7 Synthesis__guardrail | 0 | 0 | 0 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 402.2s
