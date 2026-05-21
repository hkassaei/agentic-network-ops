# Episode Report: UPF Bandwidth Cap

**Agent:** v7  
**Episode ID:** ep_20260521_033827_upf_bandwidth_cap  
**Date:** 2026-05-21T03:38:28.966545+00:00  
**Duration:** 32440.7s  

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

**Verdict:** ✅ `confirmed`

- **Propagation window:** 31544s (ObservationTrafficAgent drove traffic for this window; verifier added wait=0s on top)
- **Nodes with significant deltas:** 6
- **Nodes with any drift:** 6

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

## Anomaly Screening (Phase 0)

Anomaly screening produced no results (2 snapshots).

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

- `core.upf.activity_during_calls_collapsed` (source: `core.upf.activity_during_calls`, nf: `upf`, t=1779334715.5)  [current_value=0.0]

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

**Summary:** The UPF data plane has collapsed to zero throughput during an active VoNR call, indicating a user-plane failure either within the UPF stack or upstream at the gNB causing media starvation.

**Ranked hypotheses:**

- **`h1`** (fit=0.95, nf=upf, specificity=specific):
    - **Statement:** UPF is the source of the bidirectional data plane collapse, failing to receive or process user-plane GTP-U packets and resulting in zero throughput despite an active VoNR call.
    - **Supporting events:** `core.upf.activity_during_calls_collapsed`
    - **Falsification probes:**
        - Run 'tc -s qdisc show dev eth0' on UPF to verify if kernel-level ingress drops are preventing packets from reaching the application.
        - Check UPF PFCP session logs for missing or rejected PDR/FAR rules.
- **`h2`** (fit=0.85, nf=nr_gnb, specificity=specific):
    - **Statement:** nr_gnb is the source of the data plane collapse, failing to transmit user-plane GTP-U traffic over the N3 interface and leaving the downstream UPF starved of media packets.
    - **Supporting events:** `core.upf.activity_during_calls_collapsed`
    - **Falsification probes:**
        - Check gNB's N3 egress packet counters to verify if it is successfully emitting GTP-U traffic.
        - Use a network packet capture on the docker bridge to observe if user-plane packets are leaving the nr_gnb container.
- **`h3`** (fit=0.70, nf=smf, specificity=specific):
    - **Statement:** SMF is the source of the data plane collapse, failing to properly install PFCP forwarding rules on the UPF for the dedicated voice bearers, causing the UPF to silently drop media traffic.
    - **Supporting events:** `core.upf.activity_during_calls_collapsed`
    - **Falsification probes:**
        - Query SMF logs for PFCP modification errors or timeouts.
        - Inspect UPF internal logs for 'no matching PDR' errors indicating dropped packets due to missing rules.


## Falsification Plans (Phase 4)

**3 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `upf`)

**Hypothesis:** UPF is the source of the bidirectional data plane collapse, failing to receive or process user-plane GTP-U packets and resulting in zero throughput despite an active VoNR call.

**Probes (3):**
1. **`get_dp_quality_gauges`** — window_seconds=120 to check upf.gtp_indatapktn3upf_per_ue
    - *Expected if hypothesis holds:* The probe reads a metric value that drops to near zero during active calls.
    - *Falsifying observation:* The probe reads a metric value that remains within the typical range for active calls.
2. **`get_diagnostic_metrics`** — Check nr_gnb outbound N3 GTP-U metrics
    - *Expected if hypothesis holds:* The upstream metric shows continuous positive transmission rates, demonstrating the lack of traffic at the downstream destination is not due to the upstream source.
    - *Falsifying observation:* The upstream metric shows zero transmission, revealing the traffic starvation originates upstream.
3. **`get_dp_quality_gauges`** — window_seconds=120 to check ims.rtpengine.loss_ratio and ims.rtpengine.errors_per_second
    - *Expected if hypothesis holds:* ims.rtpengine.loss_ratio spikes while errors_per_second is zero.
    - *Falsifying observation:* ims.rtpengine.loss_ratio remains near zero, or errors_per_second spikes.

*Notes:* Utilized KB disambiguators for upf_counters_are_directional. The partner probe for UPF ingress is checking nr_gnb outbound directly via get_diagnostic_metrics to satisfy the activity-vs-drops discriminator rule.

### Plan for `h2` (target: `nr_gnb`)

**Hypothesis:** nr_gnb is the source of the data plane collapse, failing to transmit user-plane GTP-U traffic over the N3 interface and leaving the downstream UPF starved of media packets.

**Probes (3):**
1. **`get_diagnostic_metrics`** — Check nr_gnb outbound N3 GTP-U packet metrics/counters
    - *Expected if hypothesis holds:* The metric shows zero or severely degraded outbound transmission rates despite active calls.
    - *Falsifying observation:* The metric shows healthy outbound packet rates consistent with active calls.
2. **`get_dp_quality_gauges`** — window_seconds=120 to check upf.gtp_indatapktn3upf_per_ue
    - *Expected if hypothesis holds:* The metric drops to near zero, reflecting the absence of traffic from the upstream element.
    - *Falsifying observation:* The metric value is within the typical active range.
3. **`get_network_status`** — Check nr_gnb container status
    - *Expected if hypothesis holds:* Container status indicates an exited, crashed, or restarting state.
    - *Falsifying observation:* Container is running continuously without restarts.

*Notes:* Targeted nr_gnb outbound metrics first. Probe 2 (compositional UPF ingress check) is paired with Probe 1 (partner) which directly measures nr_gnb's outbound contribution to isolate the fault to the source node.

### Plan for `h3` (target: `smf`)

**Hypothesis:** SMF is the source of the data plane collapse, failing to properly install PFCP forwarding rules on the UPF for the dedicated voice bearers, causing the UPF to silently drop media traffic.

**Probes (3):**
1. **`get_diagnostic_metrics`** — Check smf metrics for PFCP/N4 modification errors or timeouts
    - *Expected if hypothesis holds:* Elevated error counters for N4 interface procedures.
    - *Falsifying observation:* Zero error counters on the N4 interface.
2. **`get_diagnostic_metrics`** — Check upf metrics for packet drops due to missing PDR/FAR rules
    - *Expected if hypothesis holds:* Elevated counters for dropped packets due to missing forwarding rules.
    - *Falsifying observation:* Zero counters for missing-rule dropped packets.
3. **`check_process_listeners`** — Check smf container for port 8805 (PFCP)
    - *Expected if hypothesis holds:* The PFCP port is unbound or not listening.
    - *Falsifying observation:* The port is bound and actively listening.

*Notes:* Free-form probes used due to KB coverage gaps for SMF PFCP failures. Probes directly target SMF N4 control metrics and the resulting observable symptoms on UPF data plane.


## Parallel Investigators (Phase 5)

**4 sub-Investigator verdict(s):** **2 DISPROVEN**, **2 INCONCLUSIVE**

### `h1` — ❌ **DISPROVEN**

**Hypothesis:** UPF is the source of the bidirectional data plane collapse, failing to receive or process user-plane GTP-U packets and resulting in zero throughput despite an active VoNR call.

**Reasoning:** [Multi-shot consensus — both shots returned DISPROVEN.]

Shot 1: Probe 1 confirmed that UPF data plane throughput dropped to zero on the uplink, which is consistent with the symptom but conflates with upstream starvation. Probe 2 attempted to check nr_gnb outbound N3 metrics to rule out upstream starvation, but the nr_gnb container and its metrics were unavailable. Probe 3 definitively contradicted the hypothesis: RTPEngine's loss_ratio remained at 0 instead of spiking. According to the falsification plan, the absence of an RTCP-reported loss_ratio spike during an active call disproves that the UPF is actively dropping packets, indicating instead a complete upstream collapse where traffic never reaches the media path.

Shot 2: The hypothesis claims UPF is silently dropping user-plane packets despite an active VoNR call. However, SMF diagnostic metrics reveal that all PDU sessions have been dropped (fivegs_smffunction_sm_sessionnbr = 0, sessions_per_ue = 0) even though the UEs remain attached (ran_ue = 2). UPF has 0 throughput because the control-plane PDU sessions do not exist, not because of a UPF data-plane fault. This contradicts the premise of a bidirectional data plane collapse during an active call, pointing instead to a control-plane session loss at the SMF.

**Probes executed (3):**
- **get_dp_quality_gauges, window_seconds=120 to check upf.gtp_indatapktn3upf_per_ue** ✓ CONSISTENT
    - *Tool:* `get_diagnostic_metrics(at_time_ts=1779334715, nfs=["upf"])`
    - *Observation:* [EVIDENCE: get_diagnostic_metrics(at_time_ts=1779334715, nfs=["upf"]) -> "normalized.upf.gtp_indatapktn3upf_per_ue = 0 [derived, packets_per_second]"]
    - *Comment:* The metric dropped to 0, which is consistent with the data plane collapse, but conflates with upstream N3 traffic starvation.
- **get_diagnostic_metrics, Check nr_gnb outbound N3 GTP-U metrics** ~ AMBIGUOUS
    - *Tool:* `measure_rtt("upf", "nr_gnb")`
    - *Observation:* [EVIDENCE: measure_rtt("upf", "nr_gnb") -> "Unknown target container 'nr_gnb'. Known: mongo, nrf, scp..."]
    - *Comment:* The nr_gnb container is not directly measurable in this environment, making it impossible to definitively check its outbound N3 metrics.
- **get_dp_quality_gauges, window_seconds=120 to check ims.rtpengine.loss_ratio and ims.rtpengine.errors_per_second** ✗ CONTRADICTS
    - *Tool:* `get_diagnostic_metrics(at_time_ts=1779334715, nfs=["rtpengine"])`
    - *Observation:* [EVIDENCE: get_diagnostic_metrics(at_time_ts=1779334715, nfs=["rtpengine"]) -> "derived.rtpengine_loss_ratio = 0 [ratio, packets_per_rr]"]
    - *Comment:* The RTPEngine loss ratio remained at zero instead of spiking. As dictated by the falsification plan, this absence of RTCP-reported loss contradicts the hypothesis that the UPF is dropping the media.

**Alternative suspects:** nr_gnb, smf

### `h2` — ❓ **INCONCLUSIVE**

**Hypothesis:** nr_gnb is the source of the data plane collapse, failing to transmit user-plane GTP-U traffic over the N3 interface and leaving the downstream UPF starved of media packets.

**Reasoning:** Probe 2 confirms that the downstream UPF is receiving near-zero inbound N3 packets, which is consistent with the hypothesis. However, this reading is compositional and conflates a gNB fault with N3 path packet loss or UPF-internal ingress drops. We could not run the necessary partner probes (Probes 1 and 3) to isolate the fault to nr_gnb because the nr_gnb container is absent from the deployment tools (neither exposed in metrics nor recognized by network status/RTT tools). Without the ability to observe nr_gnb's outbound contribution or container status, we cannot disambiguate the UPF starvation and rule out the conflated alternative causes.

**Probes executed (3):**
- **Check nr_gnb outbound N3 GTP-U packet metrics/counters** ~ AMBIGUOUS
    - *Tool:* `get_diagnostic_metrics(at_time_ts=1779334715, nfs=["nr_gnb", "upf"])`
    - *Observation:* [EVIDENCE: get_diagnostic_metrics(1779334715, ["nr_gnb", "upf"]) -> "DIAGNOSTIC METRICS (anchored at ts=1779334715)"] and no nr_gnb data block was returned.
    - *Comment:* The tool returned data for UPF but completely omitted nr_gnb, indicating that nr_gnb metrics are not exported in this deployment.
- **window_seconds=120 to check upf.gtp_indatapktn3upf_per_ue** ✓ CONSISTENT
    - *Tool:* `get_dp_quality_gauges(at_time_ts=1779334715, window_seconds=120)`
    - *Observation:* [EVIDENCE: get_dp_quality_gauges(1779334715, 120) -> "UPF:\n    in  packets/sec: 0.1"]
    - *Comment:* UPF inbound N3 packet rate is practically zero, which is consistent with media starvation from the upstream gNB. However, this compositional reading cannot independently prove gNB fault without the missing partner probes.
- **Check nr_gnb container status** ~ AMBIGUOUS
    - *Tool:* `get_network_status()`
    - *Observation:* [EVIDENCE: get_network_status() -> ""running": ["mongo", "nrf", "scp", "ausf", "udr", "udm", "amf", "smf", "upf", "pcf", "dns", "mysql", "pyhss", "icscf", "scscf", "pcscf", "rtpengine"]"]; [EVIDENCE: measure_rtt("nr_gnb", "upf") -> "Unknown source container 'nr_gnb'"]
    - *Comment:* The nr_gnb container does not exist in the orchestration list, making it impossible to check its runtime state. A supplemental check via measure_rtt confirmed it is an unknown container.

### `h3` — ❌ **DISPROVEN**

**Hypothesis:** SMF is the source of the data plane collapse, failing to properly install PFCP forwarding rules on the UPF for the dedicated voice bearers, causing the UPF to silently drop media traffic.

**Reasoning:** [Multi-shot consensus — both shots returned DISPROVEN.]

Shot 1: Probe 3 verified that the SMF PFCP port 8805 is bound and actively listening, matching the plan's exact falsifying observation and contradicting an SMF crash or unbinding on N4. Probes 1 and 2 sought explicit N4 error metrics on SMF and missing-rule drop counters on UPF, but these metrics are not exported in this stack (ambiguous weak negatives). Additionally, a triangulation probe confirmed 0% packet loss between SMF and UPF, verifying the N4 transport path is perfectly healthy. With SMF's control plane process active and its transport clear, the failure is not an N4 breakdown, pointing instead to the UPF or upstream gNB.

Shot 2: The hypothesis is contradicted by both control plane and data plane evidence. The SMF PFCP port (8805) is actively bound and listening, which directly refutes the falsification plan's expected unbound state. Furthermore, UPF data plane metrics show zero inbound N3 throughput, indicating the UPF is completely starved of traffic from the upstream gNB rather than actively receiving and silently dropping media traffic as the hypothesis claims.

**Probes executed (4):**
- **Check smf metrics for PFCP/N4 modification errors or timeouts** ~ AMBIGUOUS
    - *Tool:* `get_diagnostic_metrics(nfs=["smf", "upf"])`
    - *Observation:* [EVIDENCE: get_diagnostic_metrics(nfs=["smf", "upf"]) -> "fivegs_smffunction_sm_sessionnbr = 0 [counter]"]
    - *Comment:* The expected N4 error metrics are not exported by SMF in this stack. The absence of these metrics is a weak negative and cannot definitively confirm or deny the hypothesis.
- **Check upf metrics for packet drops due to missing PDR/FAR rules** ~ AMBIGUOUS
    - *Tool:* `get_diagnostic_metrics(nfs=["smf", "upf"])`
    - *Observation:* [EVIDENCE: get_diagnostic_metrics(nfs=["smf", "upf"]) -> "normalized.upf.gtp_indatapktn3upf_per_ue = 0"]
    - *Comment:* UPF does not export specific drop counters for missing PDR/FAR rules in this stack's diagnostic metrics.
- **Check smf container for port 8805 (PFCP)** ✗ CONTRADICTS
    - *Tool:* `check_process_listeners("smf")`
    - *Observation:* [EVIDENCE: check_process_listeners("smf") -> "udp   UNCONN 0      0         172.22.0.7:8805       0.0.0.0:*    users:((\"open5gs-smfd\",pid=8,fd=21))"]
    - *Comment:* The PFCP port on SMF is bound and actively listening. This directly matches the plan's falsifying observation and contradicts a failure of the N4 listening process.
- **Verify transport-layer reachability between SMF and UPF to rule out N4 network partition.** ✗ CONTRADICTS
    - *Tool:* `measure_rtt("smf", "upf")`
    - *Observation:* [EVIDENCE: measure_rtt("smf", "upf") -> "66 packets transmitted, 66 received, 0% packet loss, time 6736ms"]
    - *Comment:* Zero packet loss and low latency on the N4 path confirms there is no transport network partition between SMF and UPF that would cause rules to drop.

**Alternative suspects:** upf, nr_gnb

### `h_promoted_nr_gnb` — ❓ **INCONCLUSIVE**

**Hypothesis:** nr_gnb is the source of the anomaly named in the alternative_suspects of the original verdict tree.

**Reasoning:** The falsification plan relies on running `measure_rtt` and `get_network_status` probes against `nr_gnb`. However, `nr_gnb` is not managed as a valid container name within the docker compose topology exposed to these tools, causing the reachability probes to fail with 'Unknown target container' errors and the status check to omit it entirely. While AMF diagnostic metrics (gnb=1) indicate the N2 control-plane connection from the gNB is alive, I cannot run the specific triangulation path probes needed to determine if the N3 user-plane failure originates at the gNB itself or on the network path to the UPF.

**Probes executed (3):**
- **Check the running state of the nr_gnb container in the topology.** ~ AMBIGUOUS
    - *Tool:* `get_network_status()`
    - *Observation:* [EVIDENCE: get_network_status() -> "'down_or_absent': [], 'containers': { ... 17 containers (nr_gnb not listed) ... }"]
    - *Comment:* The nr_gnb is not part of the docker compose topology managed by get_network_status, so its running state cannot be directly verified here.
- **from: upf, to_ip: nr_gnb** ~ AMBIGUOUS
    - *Tool:* `measure_rtt("upf", "nr_gnb")`
    - *Observation:* [EVIDENCE: measure_rtt("upf", "nr_gnb") -> "Unknown target container 'nr_gnb'"]
    - *Comment:* Tool rejected the probe because nr_gnb is not a valid container target. Unable to measure path latency/loss.
- **from: amf, to_ip: nr_gnb** ~ AMBIGUOUS
    - *Tool:* `measure_rtt("amf", "nr_gnb")`
    - *Observation:* [EVIDENCE: measure_rtt("amf", "nr_gnb") -> "Unknown target container 'nr_gnb'"]
    - *Comment:* Tool rejected the probe because nr_gnb is not a valid container target. Unable to measure path latency/loss.


## Evidence Validation (Phase 6)

**Overall verdict:** clean
**Overall confidence:** high

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 25 | 3/3 | clean | high |
| `InvestigatorAgent_h2` | 12 | 4/4 | clean | high |
| `InvestigatorAgent_h3` | 27 | 4/4 | clean | high |
| `InvestigatorAgent_h_promoted_nr_gnb` | 8 | 3/3 | clean | high |


## Ground Truth

**Failure domain:** data_plane  
**Protocol impact:** GTP-U  
**Affected components:** upf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v7-adk/pro=gemini-3.1-pro-preview+flash=gemini-3.5-flash  
**Time to diagnosis:** 876.2s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: Investigation into the data plane collapse could not definitively isolate the root cause, but evidence points to nr_gnb as the most likely suspect for upstream media starvation.
> - **timeline**:
>     1. core.upf.activity_during_calls_collapsed event fired.
>     2. UPF data plane throughput confirmed to have dropped to zero on the uplink.
>     3. RTPEngine loss ratio remained at zero, ruling out UPF-internal packet drops.
>     4. SMF PFCP N4 port confirmed to be actively listening with 0% packet loss to UPF, ruling out SMF rule installation failure.
>     5. nr_gnb container could not be reached via standard topology probes, rendering the investigation inconclusive.
> - **root_cause**: Potential upstream media starvation at nr_gnb causing downstream UPF to receive zero N3 user-plane traffic. (primary_suspect_nf: `nr_gnb`)
> - **affected_components**:
>     - `nr_gnb`: Root Cause
>     - `upf`: Symptomatic
>     - `smf`: Secondary
> - **recommendation**: Manually investigate the operational status of the nr_gnb container and check its outbound N3 interface metrics to confirm if it is emitting GTP-U traffic.
> - **confidence**: low
> - **verdict_kind**: promoted
> - **explanation**: The UPF data plane showed zero inbound N3 traffic during an active VoNR call, suggesting upstream starvation. Hypotheses implicating the UPF (h1) and SMF (h3) were disproven by active SMF PFCP listening ports, zero RTCP-reported loss, and perfect transport health between SMF and UPF. The nr_gnb hypothesis (h2) and subsequent re-investigation (h_promoted_nr_gnb) returned inconclusive due to the nr_gnb container missing from the orchestrator's topology tools, preventing direct measurement of N3 egress metrics or transport reachability. The lack of gNB telemetry caps the confidence at low, though nr_gnb remains the primary suspect based on the downstream starvation symptoms.

### Scoring Breakdown

**Overall score: 21%**

**Scorer assessment:** The agent failed to diagnose the UPF bandwidth cap, incorrectly attributing the issue to gNB starvation with low confidence.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | No | The agent incorrectly blamed nr_gnb for upstream starvation instead of identifying the UPF bandwidth cap. |
| Component overlap | 30% | UPF was identified but only labeled as symptomatic, while nr_gnb was incorrectly marked as the root cause. |
| Severity correct | No | The agent reported a complete data plane collapse rather than a bandwidth degradation. |
| Fault type identified | No | The agent diagnosed media starvation instead of a network bandwidth constraint. |
| Layer accuracy | Yes | No layer status table was provided, preventing any misattribution detection. |
| Confidence calibrated | Yes | The agent appropriately set confidence to low due to missing gNB telemetry. |

**Ranking:** The correct root cause was not listed as a primary candidate.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 1,489,260 |
| Output tokens | 12,594 |
| Thinking tokens | 82,796 |
| **Total tokens** | **1,584,650** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| SymptomClassifier | 0 | 0 | 0 |
| EventAggregator | 0 | 0 | 0 |
| CorrelationAnalyzer | 0 | 0 | 0 |
| RAGRetriever | 0 | 0 | 0 |
| OperationalLessons | 0 | 0 | 0 |
| NetworkAnalystAgent | 129,388 | 10 | 4 |
| Phase 3 NetworkAnalyst__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 18,492 | 0 | 1 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 15,370 | 0 | 1 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| InvestigatorAgent_h1 | 292,023 | 13 | 12 |
| InvestigatorAgent_h1 | 232,374 | 12 | 11 |
| InvestigatorAgent_h1__reconciliation | 0 | 0 | 0 |
| InvestigatorAgent_h2 | 210,948 | 12 | 9 |
| InvestigatorAgent_h2__reconciliation | 0 | 0 | 0 |
| InvestigatorAgent_h3 | 254,162 | 14 | 11 |
| InvestigatorAgent_h3 | 204,485 | 13 | 11 |
| InvestigatorAgent_h3__reconciliation | 0 | 0 | 0 |
| Phase5FanOutAudit | 0 | 0 | 0 |
| Phase6.5CandidatePool | 0 | 0 | 0 |
| InstructionGeneratorAgent | 64,885 | 4 | 5 |
| Phase 6.5 Reinvestigation IG__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 34,982 | 2 | 2 |
| Phase 6.5 Reinvestigation IG__guardrail | 0 | 0 | 0 |
| Phase 6.5 Reinvestigation IG__guardrail | 0 | 0 | 0 |
| InvestigatorAgent_h_promoted_nr_gnb | 111,291 | 8 | 7 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 16,250 | 0 | 1 |
| Phase 7 Synthesis__guardrail | 0 | 0 | 0 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 32440.7s
