# Episode Report: Cascading IMS Failure

**Agent:** v7  
**Episode ID:** ep_20260510_201356_cascading_ims_failure  
**Date:** 2026-05-10T20:13:57.497434+00:00  
**Duration:** 281.8s  

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

- **Wait:** 0s
- **Actual elapsed:** 0.0s
- **Nodes with significant deltas:** 4
- **Nodes with any drift:** 5

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 51.88 (per-bucket threshold: 26.31, context bucket (0, 1), trained on 323 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following metrics deviate from their learned-healthy baseline. Treat each as a semantic observation (meaning + numbers), not a number alone — the KB's interpretation is the authoritative reading.

- **`context.cx_active`** — current **0.00** vs learned baseline **0.59** (MEDIUM, drop). *(No KB context available — interpret from the metric name.)*

- **`normalized.icscf.cdp_replies_per_ue`** (I-CSCF Diameter reply rate per UE) — current **0.00 replies_per_second_per_ue** vs learned baseline **0.03 replies_per_second_per_ue** (MEDIUM, drop)
    - **What it measures:** Liveness of the I-CSCF↔HSS Cx path. Drops to 0 when HSS is unreachable OR when no signaling is occurring at the I-CSCF (idle or upstream P-CSCF partitioned).
    - **Drop means:** No Cx replies in the window. Could be healthy idle OR a Cx-path fault.
    - **Healthy typical range:** 0–1 replies_per_second_per_ue

- **`normalized.icscf.core:rcv_requests_invite_per_ue`** (SIP INVITE rate per UE at I-CSCF) — current **0.06 requests_per_second** vs learned baseline **0.00 requests_per_second** (MEDIUM, spike)
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

- **`normalized.scscf.core:rcv_requests_invite_per_ue`** (SIP INVITE rate per UE at S-CSCF) — current **0.06 requests_per_second** vs learned baseline **0.00 requests_per_second** (MEDIUM, spike)
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

- **`normalized.upf.gtp_outdatapktn3upf_per_ue`** (GTP-U downlink rate per UE (N3)) — current **0.05 packets_per_second** vs learned baseline **1.45 packets_per_second** (MEDIUM, drop)
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

**Label:** `transport_layer`  
**Flag counts:** transport=1, application=0, ambiguous=9

### Transport-bucket flags (1)

| Metric | Direction | Score | KB-driven reason |
|---|---|---:|---|
| `normalized.upf.gtp_outdatapktn3upf_per_ue` | drop | 4.59 | KB-labeled transport: core.upf.gtp_outdatapktn3upf_per_ue (drop, score=4.59) |

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

Transport signals: normalized.upf.gtp_outdatapktn3upf_per_ue (drop, score=4.59) — KB-labeled transport: core.upf.gtp_outdatapktn3upf_per_ue (drop, score=4.59)

Ambiguous signals: context.cx_active (drop, score=4.59) — no KB entry for context.cx_active — classification ambiguous; normalized.icscf.cdp_replies_per_ue (drop, score=4.59) — KB-labeled mixed: ims.icscf.cdp_replies_per_ue (drop, score=4.59); normalized.icscf.core:rcv_requests_invite_per_ue (spike, score=4.59) — KB-labeled mixed: ims.icscf.rcv_requests_invite_per_ue (spike, score=4.59); normalized.icscf.core:rcv_requests_register_per_ue (drop, score=4.59) — KB-labeled mixed: ims.icscf.rcv_requests_register_per_ue (drop, score=4.59); normalized.pcscf.core:rcv_requests_invite_per_ue (spike, score=4.59) — KB-labeled mixed: ims.pcscf.rcv_requests_invite_per_ue (spike, score=4.59) [+4 more]
```

## Transport-Layer Route (Phase 0.6)

### Resolver

**Flow:** `data_pdu_session_user_traffic` (Data PDU Session — User Traffic)  
**Direction:** both  
**Hop count:** 11

**Candidates considered:**

| Flow | Score |
|---|---:|
| `data_pdu_session_user_traffic` ← chosen | 7 |
| `vonr_media` | 7 |
| `ims_registration` | 4 |
| `vonr_call_teardown` | 4 |
| `vonr_call_setup` | 4 |

**Rationale:**

```
Resolved transport path to flow `data_pdu_session_user_traffic` (score=7, 11 hops on the walk). Load-bearing components: ['context', 'icscf', 'pcscf', 'scscf', 'upf']. Other candidate flows considered: vonr_media=7, ims_registration=4, vonr_call_teardown=4, vonr_call_setup=4.
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

## Network Analysis (Phase 3)

**Summary:** The HSS container has exited, which has caused a complete failure of the IMS registration and authentication process, bringing down the entire VoNR service.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | Core infrastructure components are stable. |
| **ran** | 🟢 GREEN | RAN appears to be connected to the core. |
| **core** | 🟢 GREEN | The 5G core components are operational. |
| **ims** | 🔴 RED | The IMS layer is non-functional due to the HSS failure, preventing any user registrations or call setups. |

**IMS evidence:**
- pyhss container has exited
- Cx links from I-CSCF and S-CSCF to HSS are INACTIVE
- normalized.icscf.cdp_replies_per_ue is 0
- normalized.scscf.cdp_replies_per_ue is 0
- normalized.pcscf.core:rcv_requests_register_per_ue has dropped
- normalized.icscf.core:rcv_requests_register_per_ue has dropped
- normalized.scscf.core:rcv_requests_register_per_ue is 0

**Ranked hypotheses:**

- **`h1`** (fit=1.00, nf=pyhss, specificity=specific):
    - **Statement:** The primary cause of the outage is that the HSS (pyhss) container has exited, breaking the IMS authentication and registration flow.
    - **Supporting events:** `pyhss container status is 'exited'`, `Cx (Diameter) links from both I-CSCF and S-CSCF to HSS are INACTIVE`, `Metric 'normalized.icscf.cdp_replies_per_ue' dropped to 0`, `Metric 'normalized.scscf.cdp_replies_per_ue' dropped to 0`, `Metric 'normalized.scscf.core:rcv_requests_register_per_ue' dropped to 0`
    - **Falsification probes:**
        - Check the container logs for pyhss to understand why it terminated.
        - Attempt to restart the pyhss container and observe if registration rates recover.


## Falsification Plans (Phase 4)

**1 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `pyhss`)

**Hypothesis:** The primary cause of the outage is that the HSS (pyhss) container has exited, breaking the IMS authentication and registration flow.

**Probes (3):**
1. **`get_network_status`** — Check status of all network functions.
    - *Expected if hypothesis holds:* The 'pyhss' container is reported with a status of 'exited' or another non-running state.
    - *Falsifying observation:* The 'pyhss' container is reported as 'running'.
2. **`check_process_listeners`** — container='pyhss'
    - *Expected if hypothesis holds:* The command fails or returns an empty list, as a container that has exited will have no active processes listening on network ports.
    - *Falsifying observation:* The command returns a list of active listeners for the pyhss container, indicating that the HSS process is running and bound to its service ports (e.g., Diameter port 3868).
3. **`query_subscriber`** — imsi='<any_valid_imsi>'
    - *Expected if hypothesis holds:* The tool fails to connect to the HSS and returns an error, as the service is down.
    - *Falsifying observation:* The tool successfully retrieves subscriber information, proving the HSS is running, reachable, and functionally responding to requests.

*Notes:* The hypothesis points to a complete failure of the HSS. The selected probes aim to falsify this by checking three distinct aspects of the service: the container's reported status, the presence of a listening process, and the application-level functionality. The IMS registration flow ('ims_registration', steps 4, 6, 7) and Diameter authentication ('diameter_cx_authentication') depend entirely on the HSS being responsive. A successful result from any of these probes would strongly contradict the hypothesis.


## Parallel Investigators (Phase 5)

**1 sub-Investigator verdict(s):** **1 NOT_DISPROVEN**

### `h1` — ✅ **NOT_DISPROVEN**

**Hypothesis:** The primary cause of the outage is that the HSS (pyhss) container has exited, breaking the IMS authentication and registration flow.

**Reasoning:** [Multi-shot consensus — both shots returned NOT_DISPROVEN.]

Shot 1: All executed probes produced results consistent with the hypothesis. The 'pyhss' container is confirmed to be in an 'exited' state, and as a direct result, application-level queries to the HSS are failing with connection errors. No contradictory evidence was found.

Shot 2: The executed probes confirm the core claims of the hypothesis. The 'pyhss' container is reported as 'exited', and application-level queries to the HSS are failing with a connection error. No contradictory evidence was found.

**Probes executed (3):**
- **Check status of all network functions.** ✓ CONSISTENT
    - *Tool:* `default_api.get_network_status()`
    - *Observation:* [EVIDENCE: get_network_status() -> "'pyhss': 'exited'"]
    - *Comment:* The network status confirms that the pyhss container has an 'exited' status, which directly supports the hypothesis.
- **container='pyhss'** ✓ CONSISTENT
    - *Tool:* `default_api.check_process_listeners(container='pyhss')`
    - *Observation:* [EVIDENCE: check_process_listeners('pyhss') -> 'PROBE_TOOL_UNAVAILABLE: check_process_listeners cannot run on container `pyhss` — required binary `ss/netstat` is not present.']
    - *Comment:* The tool could not execute because the container is not running. This is the expected behavior for an exited container and is therefore consistent with the hypothesis.
- **imsi='<any_valid_imsi>'** ✓ CONSISTENT
    - *Tool:* `default_api.query_subscriber(domain='ims', imsi='001011234567891')`
    - *Observation:* [EVIDENCE: query_subscriber('001011234567891', 'ims') -> '{"ims_error": "Cannot connect to PyHSS API at http://172.22.0.18:8080. Is the pyhss container running?"}']
    - *Comment:* The query to the IMS subscriber database failed with a connection error. This confirms that the HSS service is unreachable, as stated in the hypothesis.


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
**Time to diagnosis:** 142.8s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: The HSS (pyhss) container has exited, causing a complete failure of the IMS registration and authentication process, which has brought down the entire VoNR service.
> - **timeline**:
>     1. The pyhss container enters an 'exited' state.
>     2. Cx (Diameter) links from both I-CSCF and S-CSCF to the HSS become INACTIVE.
>     3. The I-CSCF stops receiving Diameter capabilities replies from the HSS, causing the 'normalized.icscf.cdp_replies_per_ue' metric to drop to 0.
>     4. The S-CSCF stops receiving Diameter capabilities replies from the HSS, causing the 'normalized.scscf.cdp_replies_per_ue' metric to drop to 0.
>     5. The S-CSCF stops receiving successful registration requests, causing the 'normalized.scscf.core:rcv_requests_register_per_ue' metric to drop to 0.
>     6. The IMS registration and authentication process fails for all users.
> - **root_cause**: The primary cause of the outage is that the HSS (pyhss) container has exited, breaking the IMS authentication and registration flow. (primary_suspect_nf: `pyhss`)
> - **affected_components**:
>     - `pyhss`: Root Cause
>     - `icscf`: Symptomatic
>     - `scscf`: Symptomatic
> - **recommendation**: Check the container logs for the 'pyhss' container to investigate the reason for its unexpected termination.
> - **confidence**: high
> - **verdict_kind**: confirmed
> - **explanation**: The diagnosis is confirmed with high confidence based on a single surviving hypothesis (h1). Investigation confirmed that the HSS component, pyhss, is in an 'exited' state. Probes executed by the Investigator verified this status and also confirmed that application-level queries to the HSS are failing with connection errors. This directly explains the inactive Diameter links and the drop to zero for multiple IMS registration and authentication metrics on the I-CSCF and S-CSCF. No contradictory evidence was found, and the evidence validation was clean.

### Scoring Breakdown

**Overall score: 100%**

**Scorer assessment:** The agent provided an excellent diagnosis, correctly identifying the primary root cause, its severity, affected components, and fault type with high confidence, and accurately mapping it to the correct network layer.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | Yes | The agent correctly identified the HSS (pyhss) being down/exited as the primary root cause of the total IMS outage. While the S-CSCF also experienced latency, the HSS failure alone is sufficient to cause a complete IMS registration failure and total VoNR service outage, making it the most critical root cause. |
| Component overlap | 100% | The agent correctly identified 'pyhss' as the 'Root Cause' in its affected_components list. Although 'scscf' was also directly affected by a simulated latency, its role was labeled 'Symptomatic'. However, the HSS failure is the primary driver of the total outage, and the agent correctly prioritized it as the root cause. The prompt allows for 1.0 if the primary affected component is listed as 'Root Cause' and does not penalize for listing cascading components. |
| Severity correct | Yes | The agent's diagnosis of a 'complete failure of the IMS registration and authentication process' and 'brought down the entire VoNR service' accurately reflects the 'Total IMS outage' and 'No voice calls possible' described in the simulated failure. |
| Fault type identified | Yes | The agent identified the HSS (pyhss) as being in an 'exited' state and 'application-level queries to the HSS are failing with connection errors', which correctly describes a 'component unreachable' or 'not responding' fault type. It did not explicitly mention the S-CSCF latency, but the primary fault type is correctly identified. |
| Layer accuracy | Yes | The agent correctly attributed the failure to the 'ims' layer in its network analysis, with 'pyhss container has exited' and related IMS metrics as evidence. Both 'pyhss' and 'scscf' belong to the IMS layer. |
| Confidence calibrated | Yes | The agent stated 'high' confidence, which is appropriate given its accurate identification of the primary root cause, severity, and supporting evidence for the total IMS outage. |

**Ranking position:** #1 — The agent provided a single, correct root cause as its primary diagnosis.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 153,158 |
| Output tokens | 3,222 |
| Thinking tokens | 9,800 |
| **Total tokens** | **166,180** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| SymptomClassifier | 0 | 0 | 0 |
| PathResolver | 0 | 0 | 0 |
| PathWalkInvestigator | 0 | 0 | 0 |
| EventAggregator | 0 | 0 | 0 |
| CorrelationAnalyzer | 0 | 0 | 0 |
| NetworkAnalystAgent | 24,922 | 3 | 2 |
| Phase 3 NetworkAnalyst__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 35,395 | 2 | 3 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| InvestigatorAgent_h1 | 47,281 | 3 | 4 |
| InvestigatorAgent_h1 | 51,246 | 3 | 4 |
| InvestigatorAgent_h1__reconciliation | 0 | 0 | 0 |
| Phase5FanOutAudit | 0 | 0 | 0 |
| Phase6.5CandidatePool | 0 | 0 | 0 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 7,336 | 0 | 1 |
| Phase 7 Synthesis__guardrail | 0 | 0 | 0 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 281.8s
