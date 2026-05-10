# Episode Report: IMS Network Partition

**Agent:** v7  
**Episode ID:** ep_20260510_195023_ims_network_partition  
**Date:** 2026-05-10T19:50:25.206738+00:00  
**Duration:** 522.1s  

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

- **Wait:** 0s
- **Actual elapsed:** 0.0s
- **Nodes with significant deltas:** 1
- **Nodes with any drift:** 3

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 14.80 (per-bucket threshold: 11.07, context bucket (0, 0), trained on 323 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following metrics deviate from their learned-healthy baseline. Treat each as a semantic observation (meaning + numbers), not a number alone — the KB's interpretation is the authoritative reading.

- **`normalized.pcscf.core:rcv_requests_invite_per_ue`** (SIP INVITE rate per UE at P-CSCF) — current **0.02 requests_per_second** vs learned baseline **0.00 requests_per_second** (MEDIUM, spike)
    - **What it measures:** Call attempt rate from registered UEs. Unlike REGISTER (periodic),
INVITEs only fire when UEs place calls. Zero is normal during
quiet periods; nonzero INVITE with zero dialogs is the signature
of call setup failure.
    - **Spike means:** Fewer call attempts.
    - **Healthy typical range:** 0–0.2 requests_per_second
    - **Healthy invariant:** Per-UE rate.

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

- **`normalized.upf.gtp_indatapktn3upf_per_ue`** (GTP-U uplink rate per UE (N3)) — current **0.12 packets_per_second** vs learned baseline **1.45 packets_per_second** (LOW, drop)
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

- **`normalized.upf.gtp_outdatapktn3upf_per_ue`** (GTP-U downlink rate per UE (N3)) — current **0.03 packets_per_second** vs learned baseline **1.45 packets_per_second** (LOW, drop)
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
**Flag counts:** transport=2, application=1, ambiguous=1

### Transport-bucket flags (2)

| Metric | Direction | Score | KB-driven reason |
|---|---|---:|---|
| `normalized.upf.gtp_indatapktn3upf_per_ue` | drop | 3.15 | KB-labeled transport: core.upf.gtp_indatapktn3upf_per_ue (drop, score=3.15) |
| `normalized.upf.gtp_outdatapktn3upf_per_ue` | drop | 3.15 | KB-labeled transport: core.upf.gtp_outdatapktn3upf_per_ue (drop, score=3.15) |

### Application-bucket flags (1)

| Metric | Direction | Score | KB-driven reason |
|---|---|---:|---|
| `normalized.smf.bearers_per_ue` | shift | 4.25 | KB-labeled application: core.smf.bearers_per_ue (shift, score=4.25) |

### Ambiguous-bucket flags (1)

| Metric | Direction | Score | KB-driven reason |
|---|---|---:|---|
| `normalized.pcscf.core:rcv_requests_invite_per_ue` | spike | 4.25 | KB-labeled mixed: ims.pcscf.rcv_requests_invite_per_ue (spike, score=4.25) |

**Rationale:**

```
label=mixed. Both transport-layer (2) and application-layer (1) signals are load-bearing. Path walk runs first; falls through to the application-layer pipeline if the walk produces null localization.

Transport signals: normalized.upf.gtp_indatapktn3upf_per_ue (drop, score=3.15) — KB-labeled transport: core.upf.gtp_indatapktn3upf_per_ue (drop, score=3.15); normalized.upf.gtp_outdatapktn3upf_per_ue (drop, score=3.15) — KB-labeled transport: core.upf.gtp_outdatapktn3upf_per_ue (drop, score=3.15)

Application signals: normalized.smf.bearers_per_ue (shift, score=4.25) — KB-labeled application: core.smf.bearers_per_ue (shift, score=4.25)

Ambiguous signals: normalized.pcscf.core:rcv_requests_invite_per_ue (spike, score=4.25) — KB-labeled mixed: ims.pcscf.rcv_requests_invite_per_ue (spike, score=4.25)
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
| `pdu_session_establishment` | 2 |
| `ue_deregistration` | 2 |
| `ims_registration` | 2 |

**Rationale:**

```
Resolved transport path to flow `data_pdu_session_user_traffic` (score=13, 11 hops on the walk). Load-bearing components: ['pcscf', 'smf', 'upf']. Other candidate flows considered: vonr_media=13, pdu_session_establishment=2, ue_deregistration=2, ims_registration=2.
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

**Summary:** The core network's data plane is down, preventing any user traffic and causing VoNR call setup failures, with the User Plane Function (UPF) being the most likely source of the outage.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | No signs of issues at the container or link level. |
| **ran** | 🟢 GREEN | The RAN appears to be connected to the core. |
| **core** | 🔴 RED | The data plane is completely inactive, with both uplink and downlink traffic at a standstill through the UPF. This is a critical failure. |
| **ims** | 🟡 YELLOW | IMS signaling for call attempts is failing as a downstream consequence of the core data plane outage. The IMS components themselves appear to be healthy. |

**CORE evidence:**
- normalized.upf.gtp_indatapktn3upf_per_ue
- normalized.upf.gtp_outdatapktn3upf_per_ue

**IMS evidence:**
- normalized.pcscf.core:rcv_requests_invite_per_ue

**Ranked hypotheses:**

- **`h1`** (fit=0.90, nf=upf, specificity=specific):
    - **Statement:** upf is the source of the anomalous behavior observed in normalized.upf.gtp_indatapktn3upf_per_ue and normalized.upf.gtp_outdatapktn3upf_per_ue.
    - **Falsification probes:**
        - A successful 'measure_rtt' probe from a gNB container to the UPF's N3 IP address would indicate the N3 path is healthy, pointing to an internal UPF issue.
        - The presence of correct PFCP session rules for active UEs on the UPF would rule out an N4 control plane issue as the cause.
        - UPF logs showing no errors related to packet processing would suggest the issue lies on the network path to/from the UPF.


## Falsification Plans (Phase 4)

**1 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `upf`)

**Hypothesis:** upf is the source of the anomalous behavior observed in normalized.upf.gtp_indatapktn3upf_per_ue and normalized.upf.gtp_outdatapktn3upf_per_ue.

**Probes (3):**
1. **`get_dp_quality_gauges`** — window_seconds=120
    - *Expected if hypothesis holds:* The probe shows near-zero values for `upf_in_pps` and `upf_out_pps`, consistent with a data plane outage at the UPF.
    - *Falsifying observation:* The probe shows non-zero packet rates for `upf_in_pps` or `upf_out_pps`, indicating that the data plane is not completely inactive and the issue may be intermittent or located elsewhere.
2. **`measure_rtt`** — From the nr_gnb container to the UPF's N3 interface IP.
    - *Expected if hypothesis holds:* The probe reports low latency and no packet loss, indicating the network path from the gNB to the UPF is healthy.
    - *Falsifying observation:* The probe reports high latency or significant packet loss. This reading, when combined with the partner probe, suggests a potential network path issue rather than a problem confined to the UPF application logic.
3. **`measure_rtt`** — From the nr_gnb container to the AMF's N2 interface IP.
    - *Expected if hypothesis holds:* The probe reports low latency and no packet loss. A successful result for this probe, when the partner probe to the UPF also succeeds, suggests the network fabric is generally healthy.
    - *Falsifying observation:* If this probe succeeds while the partner probe to the UPF fails, it would isolate the issue to the N3 path or the UPF's network interface. If both probes fail, it would point to a problem with the gNB or its local network segment, thus falsifying the UPF-specific hypothesis.

*Notes:* This plan addresses the feedback from the previous attempt. It includes a non-compositional probe to check data plane activity directly and a pair of compositional 'measure_rtt' probes to disambiguate between a UPF-internal issue and a network path issue. The probe descriptions are revised to focus on observable phenomena rather than inferred mechanisms.


## Parallel Investigators (Phase 5)

**1 sub-Investigator verdict(s):** **1 INCONCLUSIVE**

### `h1` — ❓ **INCONCLUSIVE**

**Hypothesis:** upf is the source of the anomalous behavior observed in normalized.upf.gtp_indatapktn3upf_per_ue and normalized.upf.gtp_outdatapktn3upf_per_ue.

**Reasoning:** [Multi-shot consensus — at least one shot returned INCONCLUSIVE (shot 1: NOT_DISPROVEN, shot 2: INCONCLUSIVE). Treating the combined verdict as INCONCLUSIVE because INCONCLUSIVE on either shot means we lack confident evidence to commit.]

Shot 1: All executed probes were consistent with the hypothesis. The data plane quality gauges confirmed that UPF packet processing was stalled at the time of the anomaly. Subsequent RTT probes to the UPF from the SMF showed a healthy and responsive network path, suggesting the issue is internal to the UPF application and not a network connectivity problem. While the originally planned probes from the gNB could not be run, the available evidence points to the UPF as the source of the failure.

Shot 2: The investigation is inconclusive. One probe confirmed that the UPF's data plane was inactive, which is consistent with the hypothesis. However, the crucial probes to test the network path between the gNB and the UPF could not be executed because the `measure_rtt` tool does not support the `nr_gnb` container as a source. Without these probes, it is impossible to disambiguate between a UPF-internal fault and a network path issue, as noted in the falsification plan's `conflates_with` section.

**Probes executed (3):**
- **The probe shows near-zero values for `upf_in_pps` and `upf_out_pps`, consistent with a data plane outage at the UPF.** ✓ CONSISTENT
    - *Tool:* `print(default_api.get_dp_quality_gauges(at_time_ts = 1778442663.2742429, window_seconds = 120))`
    - *Observation:* [EVIDENCE: get_dp_quality_gauges(at_time_ts=1778442663.2742429, window_seconds=120) -> "UPF:\n    in  packets/sec: 0.2\n    out packets/sec: 0.0"]
    - *Comment:* The UPF's data plane throughput was effectively zero at the time of the anomaly, which is consistent with the hypothesis that the UPF is the source of the failure.
- **From the nr_gnb container to the UPF's N3 interface IP.** ✓ CONSISTENT
    - *Tool:* `print(default_api.measure_rtt(container = "smf", target_ip = "172.22.0.8"))`
    - *Observation:* [EVIDENCE: measure_rtt('smf', '172.22.0.8') -> "66 packets transmitted, 66 received, 0% packet loss, time 6770ms"]
    - *Comment:* The original probe from 'nr_gnb' failed as the tool does not support that container. A substitute probe from 'smf' to UPF shows perfect connectivity. This indicates the UPF's network stack is responsive, making an internal application issue more likely, which is consistent with the hypothesis.
- **From the nr_gnb container to the AMF's N2 interface IP.** ✓ CONSISTENT
    - *Tool:* `print(default_api.measure_rtt(container = "smf", target_ip = "172.22.0.10"))`
    - *Observation:* [EVIDENCE: measure_rtt('smf', '172.22.0.10') -> "66 packets transmitted, 66 received, 0% packet loss, time 6771ms"]
    - *Comment:* This probe was a substitute for the original plan, providing triangulation. It confirms the general health of the network from the 'smf' container. The successful RTT to both the AMF and the UPF (in the previous probe) from the same source reinforces the conclusion that the network path is not the problem.


## Evidence Validation (Phase 6)

**Overall verdict:** clean
**Overall confidence:** high

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 9 | 3/3 | clean | high |


## Ground Truth

**Failure domain:** ims_signaling  
**Protocol impact:** SIP  
**Affected components:** pcscf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v7-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 379.1s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: The 5G core data plane is down, but investigation was inconclusive as it could not distinguish between a UPF-internal fault and a gNB-to-UPF network path issue.
> - **timeline**:
>     1. VoNR call setup failures are observed.
>     2. Core network data plane traffic through the UPF is identified to be at a standstill.
>     3. Investigation of the UPF as the potential root cause is inconclusive.
>     4. The inability to execute network path probes from the gNB prevents distinguishing between a UPF failure and a network path failure.
> - **root_cause**: Investigation was inconclusive because automated probes could not run to test the network path between the gNB and the UPF. This makes it impossible to determine if the data plane outage originates within the UPF or on the network path to it.
> - **affected_components**:
>     - `upf`: Symptomatic
>     - `ims`: Symptomatic
> - **recommendation**: Manually verify network connectivity between the `nr_gnb` container and the UPF container's N3 interface (IP from probe logs: 172.22.0.8). A successful ping or trace from the `nr_gnb` would implicate the UPF itself, while a failure would point to a transport issue.
> - **confidence**: low
> - **verdict_kind**: inconclusive
> - **explanation**: The core network's data plane is down, causing a complete halt of user traffic and subsequent VoNR call failures. The Network Analyst identified the User Plane Function (UPF) as the most likely source of the outage, as telemetry showed both its inbound and outbound packet processing was stalled. However, the subsequent investigation was inconclusive. While probes confirmed the UPF's data plane was inactive, the crucial probes to test the N3 data path from the gNB could not be executed due to tooling limitations. Therefore, it is not possible to determine if the fault lies within the UPF application or on the network path between the RAN and the core.

### Scoring Breakdown

**Overall score: 27%**

**Scorer assessment:** The agent completely missed the IMS network partition, focusing instead on an inconclusive data plane issue involving the UPF. While it correctly assessed the severity and its own low confidence, it failed to identify the correct root cause, affected component's role, fault type, and layer.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | No | The simulated failure was an IMS network partition affecting the P-CSCF, severing SIP signaling. The agent's diagnosis focused on an inconclusive issue with the 5G core data plane (UPF or gNB-UPF path) and completely missed the IMS signaling plane partition as the root cause. |
| Component overlap | 10% | The primary affected component is 'pcscf' (an IMS component). The agent listed 'ims' as 'Symptomatic' but attributed the primary issue to the 'upf' or the network path to it. While 'ims' was mentioned as affected, it was not identified as the root cause, and the focus was on a different component/layer. |
| Severity correct | Yes | The simulated failure resulted in completely severed SIP signaling and new call failures. The agent correctly identified a 'complete halt of user traffic' and 'VoNR call failures', which accurately reflects the severity of a complete outage for new services. |
| Fault type identified | No | The simulated failure was a 'network partition' affecting 'SIP signaling' for IMS components. The agent identified a 'data plane outage' or 'component unreachable' for the UPF/gNB-UPF path, which is a different type and location of fault than the actual IMS signaling partition. |
| Layer accuracy | No | The primary affected component ('pcscf') belongs to the 'ims' layer. The agent's network analysis rated the 'ims' layer as 'yellow' and stated 'IMS components themselves appear to be healthy,' while rating the 'core' layer as 'red' and identifying the UPF (a core component) as the most likely source. This incorrectly attributes the root cause to the 'core' layer instead of the 'ims' layer. |
| Confidence calibrated | Yes | The agent's diagnosis was 'inconclusive' and its stated 'confidence' was 'low'. Given that the diagnosis was incorrect and missed the actual root cause, this low confidence is appropriate and well-calibrated. |

**Ranking:** The agent provided a single, inconclusive diagnosis focused on the UPF/data plane. The correct root cause (IMS network partition) was not identified or ranked among any candidates.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 374,519 |
| Output tokens | 5,300 |
| Thinking tokens | 28,492 |
| **Total tokens** | **408,311** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| SymptomClassifier | 0 | 0 | 0 |
| PathResolver | 0 | 0 | 0 |
| PathWalkInvestigator | 0 | 0 | 0 |
| EventAggregator | 0 | 0 | 0 |
| CorrelationAnalyzer | 0 | 0 | 0 |
| NetworkAnalystAgent | 91,724 | 5 | 6 |
| Phase 3 NetworkAnalyst__guardrail | 0 | 0 | 0 |
| NetworkAnalystAgent | 71,623 | 6 | 3 |
| Phase 3 NetworkAnalyst__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 25,933 | 1 | 2 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 15,503 | 0 | 1 |
| InstructionGeneratorAgent | 26,908 | 1 | 2 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| InvestigatorAgent_h1 | 94,034 | 5 | 6 |
| InvestigatorAgent_h1 | 72,755 | 4 | 5 |
| InvestigatorAgent_h1__reconciliation | 0 | 0 | 0 |
| Phase5FanOutAudit | 0 | 0 | 0 |
| Phase6.5CandidatePool | 0 | 0 | 0 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 9,831 | 0 | 1 |
| Phase 7 Synthesis__guardrail | 0 | 0 | 0 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 522.1s
