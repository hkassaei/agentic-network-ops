# Episode Report: P-CSCF Packet Loss

**Agent:** v7  
**Episode ID:** ep_20260521_024709_p_cscf_packet_loss  
**Date:** 2026-05-21T02:47:16.061781+00:00  
**Duration:** 1637.2s  

---

## Scenario

**Category:** network  
**Blast radius:** single_nf  
**Description:** Inject 30% packet loss on the P-CSCF (SIP edge proxy) — the same fault class as Call Quality Degradation but on a signaling-plane container. Packets leaving P-CSCF (REGISTER forwards to I-CSCF, 401/200 responses to UEs) are silently dropped by the kernel after Kamailio's sendto() returns success. SIP retransmission timers (T1 = 500 ms) absorb some of the loss; a meaningful fraction of registrations still time out. This is the second worked example in ADR `path_anchored_probe_planning_for_transport_layer_faults.md` — it proves that the same fault class manifests in the signaling plane and that v7's path walk localizes both data-plane (Call Quality Degradation) and signaling-plane (this scenario) instances of it correctly. v6's per-NF hypothesis pipeline mis-diagnoses both.

## Faults Injected

- **network_loss** on `pcscf` — {'loss_pct': 30}

## Baseline (Pre-Fault)

Stack phase before injection: **ready**
All containers running at baseline.

## Fault Propagation Verification

**Verdict:** ✅ `confirmed`

- **Propagation window:** 938s (ObservationTrafficAgent drove traffic for this window; verifier added wait=0s on top)
- **Nodes with significant deltas:** 5
- **Nodes with any drift:** 6

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

## Anomaly Screening (Phase 0)

Anomaly screening produced no results (5 snapshots).

## Symptom Classifier (Phase 0.5)

**Label:** `application_layer`  
**Flag counts:** transport=0, application=0, ambiguous=0

**Rationale:**

```
No anomaly flags in the screener output. Nothing for the transport-layer path walk to localize; the orchestrator routes through the application-layer pipeline by default.
```

## Transport-Layer Route (Phase 0.6)

*Skipped — classifier label is `application_layer`. Routes through the app-layer pipeline (Phases 1-7) below.*

## Event Aggregation (Phase 1)

**1 events fired during the observation window:**

- `core.upf.activity_during_calls_collapsed` (source: `core.upf.activity_during_calls`, nf: `upf`, t=1779332560.2)  [current_value=0.0013273333333333334]

## Correlation Analysis (Phase 2)

1 events fired but no composite hypothesis emerged. The events may be from independent faults or lack registered correlation hints in the KB.

## RAG & Operational Lessons (Phase 2.5)

### RAG retrieval — prior similar episodes

**Status:** `no_flags` — no_flags (corpus_size=102)
**Index:** `/home/ehoskas/agentic-network-ops/rag_index`  **Corpus size:** 102 cases

*Phase 0 produced no anomaly flags, so the query couldn't be built — no retrieval ran. Likely a clean stack with a transient symptom that subsided.*

### Operational lessons — hand-authored rules corpus

**Status:** `injected` — lessons=16, chars=15678
**Path:** `/home/ehoskas/agentic-network-ops/agentic_ops_common/rag/lessons.yaml`  **Count:** 16  **Block size:** 15678 chars
**Injected lesson IDs:** `L01`, `L02`, `L03`, `L04`, `L05`, `L06`, `L07`, `L08`, `L09`, `L10`, `L11`, `L12`, `L13`, `L14`, `L15`, `L16`

### NA citations of the injected content

**No verbatim citations.** The NA's output text did not reference any retrieved case_id or any injected lesson_id verbatim. This does NOT prove the NA ignored the injected content — the model may have absorbed the patterns implicitly — but it does mean no audit trail links the NA's reasoning back to a specific case or lesson.

## Network Analysis (Phase 3)

**Summary:** A complete bidirectional data plane outage is occurring at or upstream of the UPF, evidenced by zero N3 throughput and collapsed UPF activity despite healthy IMS signaling and active calls.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | Docker bridge is healthy; no exited containers. |
| **ran** | 🟡 YELLOW | N2 control plane is up, but gNB may be failing to emit N3 user-plane traffic. |
| **core** | 🔴 RED | UPF is either dropping packets silently or not receiving any user plane traffic despite SMF maintaining active sessions. |
| **ims** | 🟢 GREEN | IMS signaling is completing successfully; the fault is strictly isolated to the data plane. |

**RAN evidence:**
- AMF reports 2 attached UEs and 1 active gNB (N2 is healthy).
- UPF is receiving 0 incoming GTP-U packets from gNB.

**CORE evidence:**
- UPF `gtp_indatapktn3upf_per_ue` and `gtp_outdatapktn3upf_per_ue` are both exactly 0.
- Fired event `core.upf.activity_during_calls_collapsed`.

**Ranked hypotheses:**

- **`h1`** (fit=0.95, nf=upf, specificity=specific):
    - **Statement:** UPF is the source of the bidirectional data plane outage, causing zero N3 throughput and collapsed activity during active calls.
    - **Supporting events:** `core.upf.activity_during_calls_collapsed`
    - **Falsification probes:**
        - Path walk the N3 interface from gNB to UPF to verify if packets are reaching UPF ingress
        - Inspect UPF internal application logs and counters for silent drops (e.g., 'no matching PDR' or TUN interface issues)
- **`h2`** (fit=0.75, nf=nr_gnb, specificity=moderate):
    - **Statement:** nr_gnb is the source of the data plane outage, failing to transmit uplink N3 traffic despite successful N2 attachment and active PDU sessions.
    - **Supporting events:** `core.upf.activity_during_calls_collapsed`
    - **Falsification probes:**
        - Path walk the N3 uplink from gNB to UPF to confirm if gNB is failing to emit GTP-U packets
        - Check gNB logs for F-TEID mismatch, radio link failures, or transmission drops


## Falsification Plans (Phase 4)

**2 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `upf`)

**Hypothesis:** UPF is the source of the bidirectional data plane outage, causing zero N3 throughput and collapsed activity during active calls.

**Probes (4):**
1. **`get_dp_quality_gauges`** — window_seconds=120 to measure upf.gtp_indatapktn3upf_per_ue and upf.gtp_outdatapktn3upf_per_ue
    - *Expected if hypothesis holds:* Both uplink and downlink N3 per-UE packet rates read zero or near zero despite active calls, confirming the outage.
    - *Falsifying observation:* Uplink and downlink packet rates are healthy (> 50 pps), indicating traffic is actively flowing through the UPF.
2. **`get_diagnostic_metrics`** — Check nr_gnb metrics for N3/GTP-U outbound packets
    - *Expected if hypothesis holds:* The metrics show active outbound GTP-U packet counters at nr_gnb, confirming that the upstream NF is transmitting data, and localizing the failure to the UPF.
    - *Falsifying observation:* The metrics show zero outbound GTP-U packets at nr_gnb, indicating the upstream NF is not generating traffic.
3. **`measure_rtt`** — from: nr_gnb, to_ip: upf (N3 interface)
    - *Expected if hypothesis holds:* Ping succeeds with 0% packet loss and low latency. The structural network path is intact, meaning the zero N3 throughput is not caused by an infrastructure partition.
    - *Falsifying observation:* Ping shows 100% packet loss.
4. **`measure_rtt`** — from: smf, to_ip: upf (N4 interface)
    - *Expected if hypothesis holds:* Ping succeeds with 0% packet loss, confirming the UPF is reachable on other interfaces.
    - *Falsifying observation:* Ping shows 100% packet loss, indicating the UPF is completely partitioned or down.

*Notes:* Plan tests if UPF is dropping N3 traffic while remaining reachable on infrastructure.

### Plan for `h2` (target: `nr_gnb`)

**Hypothesis:** nr_gnb is the source of the data plane outage, failing to transmit uplink N3 traffic despite successful N2 attachment and active PDU sessions.

**Probes (3):**
1. **`get_dp_quality_gauges`** — window_seconds=120 to check upf.gtp_indatapktn3upf_per_ue
    - *Expected if hypothesis holds:* The uplink metric upf.gtp_indatapktn3upf_per_ue reads exactly 0 or is entirely collapsed, confirming the lack of arriving N3 packets from nr_gnb.
    - *Falsifying observation:* The uplink metric reads typical values (> 50 pps for active calls), indicating nr_gnb is successfully transmitting GTP-U packets.
2. **`measure_rtt`** — from: upf, to_ip: nr_gnb (N3 interface)
    - *Expected if hypothesis holds:* Ping succeeds with 0% packet loss. The structural network path is intact, meaning the zero N3 throughput is not caused by an infrastructure partition.
    - *Falsifying observation:* Ping shows 100% packet loss.
3. **`measure_rtt`** — from: amf, to_ip: nr_gnb (N2 interface)
    - *Expected if hypothesis holds:* Ping succeeds with 0% packet loss. This localizes the nr_gnb as active and reachable on its N2 interface.
    - *Falsifying observation:* Ping shows 100% packet loss, indicating the nr_gnb is completely partitioned or down on all interfaces.

*Notes:* Plan tests if nr_gnb is failing to emit GTP-U packets despite being healthy on control plane (N2).


## Parallel Investigators (Phase 5)

**2 sub-Investigator verdict(s):** **2 INCONCLUSIVE**

### `h1` — ❓ **INCONCLUSIVE**

**Hypothesis:** UPF is the source of the bidirectional data plane outage, causing zero N3 throughput and collapsed activity during active calls.

**Reasoning:** The UPF N3 throughput is exactly 0.0 pps for both ingress and egress, confirming a complete data plane collapse while SMF session control plane counters remain healthy. However, the hypothesis claims UPF is the SOURCE of this outage. Validating this attribution requires proving that the upstream NF (gNB) is generating traffic that the UPF is dropping, or ruling out an infrastructure partition between gNB and UPF. Because `nr_gnb` metrics and ping tools are unavailable in this environment, the gNB's outbound N3 activity cannot be verified. Following the silence-shaped hypothesis rules, an unavailable upstream counter forces an INCONCLUSIVE verdict since the data-plane silence at UPF is equally consistent with UPF failure and gNB starvation.

**Probes executed (4):**
- **window_seconds=120 to measure upf.gtp_indatapktn3upf_per_ue and upf.gtp_outdatapktn3upf_per_ue** ✓ CONSISTENT
    - *Tool:* `get_dp_quality_gauges(window_seconds=120)`
    - *Observation:* [EVIDENCE: get_dp_quality_gauges(window_seconds=120) -> "UPF: in packets/sec: 0.0, out packets/sec: 0.0"]
    - *Comment:* UPF data plane throughput is dead bidirectionally, confirming the outage is active.
- **Check nr_gnb metrics for N3/GTP-U outbound packets** ~ AMBIGUOUS
    - *Tool:* `get_diagnostic_metrics(nfs=["nr_gnb"])`
    - *Observation:* [EVIDENCE: get_diagnostic_metrics(nfs=["nr_gnb"]) -> "DIAGNOSTIC METRICS (live snapshot)... (no metrics listed for nr_gnb)"]
    - *Comment:* The nr_gnb container is not present in diagnostic metrics, so its outbound GTP-U counters cannot be checked to determine if UPF is starved.
- **from: nr_gnb, to_ip: upf (N3 interface)** ~ AMBIGUOUS
    - *Tool:* `measure_rtt("nr_gnb", "upf")`
    - *Observation:* [EVIDENCE: measure_rtt("nr_gnb", "upf") -> "Unknown source container 'nr_gnb'"]
    - *Comment:* nr_gnb is not a known container for measure_rtt, preventing the N3 infrastructure path check.
- **from: smf, to_ip: upf (N4 interface)** ✓ CONSISTENT
    - *Tool:* `measure_rtt("smf", "upf")`
    - *Observation:* [EVIDENCE: measure_rtt("smf", "upf") -> "66 packets transmitted, 66 received, 0% packet loss"]
    - *Comment:* UPF is reachable from SMF on N4, confirming the UPF infrastructure partition is not total.

### `h2` — ❓ **INCONCLUSIVE**

**Hypothesis:** nr_gnb is the source of the data plane outage, failing to transmit uplink N3 traffic despite successful N2 attachment and active PDU sessions.

**Reasoning:** The get_dp_quality_gauges probe confirms that zero uplink packets are arriving at the UPF, matching the hypothesis's prediction of a collapsed N3 uplink. However, this directional reading is structurally ambiguous: it cannot distinguish between the gNB failing to transmit N3 packets, the network path dropping them, or the UPF dropping them at ingress. Triangulating the N3 and N2 network paths (using measure_rtt from UPF and AMF to nr_gnb) failed because the container name 'nr_gnb' is not recognized by the tool. Without these triangulation probes to verify path integrity, it is impossible to conclusively attribute the lack of arriving packets to the gNB itself.

**Probes executed (3):**
- **window_seconds=120 to check upf.gtp_indatapktn3upf_per_ue** ✓ CONSISTENT
    - *Tool:* `get_dp_quality_gauges(window_seconds=120, at_time_ts=0)`
    - *Observation:* [EVIDENCE: get_dp_quality_gauges(window_seconds=120, at_time_ts=0) -> "UPF:\n    in  packets/sec: 0.0\n    out packets/sec: 0.0"]
    - *Comment:* Uplink N3 traffic is entirely collapsed at the UPF ingress. This is consistent with the gNB failing to transmit packets, but equally consistent with a network partition or UPF ingress failure.
- **from: upf, to_ip: nr_gnb (N3 interface)** ~ AMBIGUOUS
    - *Tool:* `measure_rtt("upf", "nr_gnb")`
    - *Observation:* [EVIDENCE: measure_rtt("upf", "nr_gnb") -> "Unknown target container 'nr_gnb'"]
    - *Comment:* The target container 'nr_gnb' is not accessible to the tool, preventing verification of the N3 network path between UPF and gNB.
- **from: amf, to_ip: nr_gnb (N2 interface)** ~ AMBIGUOUS
    - *Tool:* `measure_rtt("amf", "nr_gnb")`
    - *Observation:* [EVIDENCE: measure_rtt("amf", "nr_gnb") -> "Unknown target container 'nr_gnb'"]
    - *Comment:* The target container 'nr_gnb' is not accessible to the tool, preventing verification of the N2 network path between AMF and gNB.


## Evidence Validation (Phase 6)

**Overall verdict:** clean
**Overall confidence:** high

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 15 | 4/4 | clean | high |
| `InvestigatorAgent_h2` | 9 | 3/3 | clean | high |


## Ground Truth

**Failure domain:** ims_signaling  
**Protocol impact:** SIP  
**Affected components:** pcscf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v7-adk/pro=gemini-3.1-pro-preview+flash=gemini-3.5-flash  
**Time to diagnosis:** 686.9s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: Investigation into the bidirectional N3 data plane outage was inconclusive due to missing diagnostic tools and inaccessible components for verifying uplink N3 traffic from the gNB.
> - **timeline**:
>     1. Observed complete bidirectional data plane outage with zero N3 throughput at UPF during active calls.
>     2. Investigated UPF as the potential source of the N3 outage, confirming dead N3 throughput, but could not determine if it was starved by the upstream gNB due to missing metrics.
>     3. Investigated nr_gnb as the potential source of the N3 uplink failure, but the container could not be reached by network path verification tools.
> - **root_cause**: INCONCLUSIVE
> - **affected_components**:
>     - `upf`: Symptomatic
>     - `nr_gnb`: Symptomatic
> - **recommendation**: Manually investigate nr_gnb outbound N3/GTP-U metrics and verify the N3 network path between nr_gnb and UPF for potential partition or silent drops.
> - **confidence**: low
> - **verdict_kind**: inconclusive
> - **explanation**: The investigation confirmed a complete bidirectional data plane collapse at the UPF, with ingress and egress N3 throughput at exactly 0.0 pps while SMF session control plane counters remained healthy. However, attributing the root cause was impossible due to structural ambiguity and unavailable tools. Hypothesis 1 (UPF failure) and Hypothesis 2 (nr_gnb failure) both returned INCONCLUSIVE verdicts because the `nr_gnb` container could not be accessed by ping tools (`measure_rtt`) and its N3 outbound metrics were unavailable in the diagnostic snapshot. Without verifying whether the gNB is generating N3 packets or if the path between the gNB and UPF is intact, the evidence is equally consistent with a gNB failure, a network partition, or a silent drop at the UPF ingress.

### Scoring Breakdown

**Overall score: 0%**

**Scorer assessment:** The agent completely missed the P-CSCF packet loss, incorrectly declaring the IMS layer healthy and chasing a non-existent data plane outage between the UPF and gNB.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | No | The agent failed to identify the 30% packet loss on the P-CSCF, instead concluding that there was an inconclusive bidirectional N3 data plane outage between the UPF and gNB. |
| Component overlap | 0% | The agent did not identify 'pcscf' as an affected component, listing only 'upf' and 'nr_gnb' as symptomatic. |
| Severity correct | No | The agent diagnosed a complete data plane outage (100% loss/collapse) instead of a signaling plane degradation (30% packet loss on P-CSCF). |
| Fault type identified | No | The agent identified a complete outage/partition in the data plane rather than a network degradation (packet loss) in the signaling plane. |
| Layer accuracy | No | The agent rated the 'ims' layer as green (healthy) and attributed the failure to the 'core' and 'ran' layers, whereas the actual failing component (pcscf) belongs to the IMS layer. |
| Confidence calibrated | No | Although the agent stated 'low' confidence for its final inconclusive verdict, it confidently and incorrectly ruled out the IMS layer as healthy ('IMS signaling is completing successfully; the fault is strictly isolated to the data plane'). |

**Ranking:** The correct root cause (P-CSCF packet loss) was not listed in the agent's diagnosis.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 851,005 |
| Output tokens | 6,149 |
| Thinking tokens | 26,566 |
| **Total tokens** | **883,720** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| SymptomClassifier | 0 | 0 | 0 |
| EventAggregator | 0 | 0 | 0 |
| CorrelationAnalyzer | 0 | 0 | 0 |
| RAGRetriever | 0 | 0 | 0 |
| OperationalLessons | 0 | 0 | 0 |
| NetworkAnalystAgent | 354,049 | 12 | 11 |
| Phase 3 NetworkAnalyst__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 15,105 | 0 | 1 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 16,400 | 0 | 1 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| InvestigatorAgent_h1 | 380,511 | 15 | 13 |
| InvestigatorAgent_h1__reconciliation | 0 | 0 | 0 |
| InvestigatorAgent_h2 | 105,545 | 9 | 5 |
| InvestigatorAgent_h2__reconciliation | 0 | 0 | 0 |
| Phase5FanOutAudit | 0 | 0 | 0 |
| Phase6.5CandidatePool | 0 | 0 | 0 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 12,110 | 0 | 1 |
| Phase 7 Synthesis__guardrail | 0 | 0 | 0 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 1637.2s
