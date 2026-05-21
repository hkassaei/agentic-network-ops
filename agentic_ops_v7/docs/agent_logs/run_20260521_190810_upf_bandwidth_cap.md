# Episode Report: UPF Bandwidth Cap

**Agent:** v7  
**Episode ID:** ep_20260521_190100_upf_bandwidth_cap  
**Date:** 2026-05-21T19:01:01.933509+00:00  
**Duration:** 428.2s  

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

- **Propagation window:** 129s (ObservationTrafficAgent drove traffic for this window; verifier added wait=0s on top)
- **Nodes with significant deltas:** 0
- **Nodes with any drift:** 1

## Symptoms Observed

Symptoms detected: **No**  
Observation iterations: 1

## Anomaly Screening (Phase 0)

No anomalies detected by the statistical screener.

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

No events fired during this episode. Either no metric KB triggers matched, or the episode encountered no meaningful state transitions.

## Correlation Analysis (Phase 2)

No events fired — correlation engine had nothing to work with.

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

**Summary:** The 5G SA + IMS stack is fully healthy with no active faults; all VoNR components are running, UEs are attached, and no metric deviations were detected. Grafana is exited but is an out-of-scope observability component.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | Core infrastructure is fully operational. |
| **ran** | 🟢 GREEN | RAN is connected and serving UEs. |
| **core** | 🟢 GREEN | 5G Core is fully operational. |
| **ims** | 🟢 GREEN | IMS signaling and media components are healthy. |

**Ranked hypotheses:**

- **`h1`** (fit=0.10, nf=amf, specificity=vague):
    - **Statement:** The stack is entirely healthy and functioning normally; AMF is nominated as a placeholder suspect to verify that UEs remain actively attached to the control plane.
    - **Falsification probes:**
        - Verify AMF logs to confirm UE registration states are stable.
        - Check AMF ran_ue metric continues to hold at 2.


## Falsification Plans (Phase 4)

**1 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `amf`)

**Hypothesis:** The stack is entirely healthy and functioning normally; AMF is nominated as a placeholder suspect to verify that UEs remain actively attached to the control plane.

**Probes (3):**
1. **`get_network_status`** — Check if amf and nr_gnb containers are running
    - *Expected if hypothesis holds:* Both amf and nr_gnb are reported as running and healthy.
    - *Falsifying observation:* Either amf or nr_gnb is exited or down, contradicting the claim that the stack is fully healthy.
2. **`get_diagnostic_metrics`** — Check AMF metric 'ran_ue' to verify active UEs and 'amf.gnb' to verify N2 connection.
    - *Expected if hypothesis holds:* ran_ue is stable at 2 and amf.gnb is equal to configured gNB count (1).
    - *Falsifying observation:* ran_ue drops to 0 or amf.gnb drops to 0, indicating UEs have detached or gNB has lost its N2 association.
3. **`check_process_listeners`** — Check listening ports on amf to ensure the SCTP N2 port (38412) is active.
    - *Expected if hypothesis holds:* AMF is actively listening on its expected ports, including SCTP 38412.
    - *Falsifying observation:* AMF is not listening on SCTP 38412, meaning it cannot accept connections from gNB.

*Notes:* Hypothesis h1 is a placeholder for 'all clear'. Validating AMF liveness, N2 connection count, and active UE count confirms the control plane baseline.


## Parallel Investigators (Phase 5)

**1 sub-Investigator verdict(s):** **1 NOT_DISPROVEN**

### `h1` — ✅ **NOT_DISPROVEN**

**Hypothesis:** The stack is entirely healthy and functioning normally; AMF is nominated as a placeholder suspect to verify that UEs remain actively attached to the control plane.

**Reasoning:** [Multi-shot consensus — both shots returned NOT_DISPROVEN.]

Shot 1: Diagnostic metrics confirm that the AMF maintains an active N2 connection to the gNB (gnb=1) and both UEs remain actively attached (ran_ue=2). Network status shows all core components are running with no containers down or absent. The evidence is entirely consistent with a healthy stack.

Shot 2: The AMF container is actively running and the stack appears healthy. Diagnostic metrics at the time of the anomaly show gnb=1 and ran_ue=2, confirming that the N2 control plane connection is alive and UEs remain successfully attached. While check_process_listeners did not list the SCTP 38412 port, the gnb=1 metric is a strong positive proving the N2 connection is active, rendering the listener output a weak negative likely due to tool limits (ss not surfacing SCTP). The hypothesis of a fully healthy stack survives.

**Probes executed (3):**
- **Check if amf and nr_gnb containers are running** ✓ CONSISTENT
    - *Tool:* `get_network_status()`
    - *Observation:* [EVIDENCE: get_network_status() -> "'down_or_absent': []"] and amf is listed in 'running'.
    - *Comment:* AMF is running and no containers are reported as down or absent, confirming the baseline stack health.
- **Check AMF metric 'ran_ue' to verify active UEs and 'amf.gnb' to verify N2 connection.** ✓ CONSISTENT
    - *Tool:* `get_diagnostic_metrics(at_time_ts=1779390096.0529375, nfs=['amf'])`
    - *Observation:* [EVIDENCE: get_diagnostic_metrics(1779390096.05294, ["amf"]) -> "gnb = 1 [gauge, count]" and "ran_ue = 2 [gauge, count]"]
    - *Comment:* ran_ue is stable at 2 and gnb is 1, proving the control plane connection to RAN and UEs is fully active.
- **Check listening ports on amf to ensure the SCTP N2 port (38412) is active.** ~ AMBIGUOUS
    - *Tool:* `check_process_listeners("amf")`
    - *Observation:* [EVIDENCE: check_process_listeners("amf") -> "tcp   LISTEN 0      4096     172.22.0.10:9091" and "tcp   LISTEN 0      5        172.22.0.10:7777"]
    - *Comment:* SCTP 38412 is not displayed, likely due to a tool limitation where the ss command omits SCTP listeners by default. However, the active gNB metric confirms the N2 connection is established.


## Evidence Validation (Phase 6)

**Overall verdict:** clean
**Overall confidence:** high

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 10 | 3/3 | clean | high |


## Ground Truth

**Failure domain:** data_plane  
**Protocol impact:** GTP-U  
**Affected components:** upf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v7-adk/pro=gemini-3.1-pro-preview+flash=gemini-3.5-flash  
**Time to diagnosis:** 291.6s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: Diagnostic checks confirm the 5G SA and IMS stack is entirely healthy and functioning normally with stable UE attachments and no active faults.
> - **timeline**:
>     1. System health check initiated to confirm normal baseline operations.
>     2. Investigator verified core infrastructure status, finding all components running without failure.
>     3. Diagnostic metrics retrieved for AMF, confirming gnb=1 and ran_ue=2.
>     4. Process listener check yielded an ambiguous result due to SCTP tool limitations, but metrics definitively proved N2 stability.
>     5. Stack deemed completely healthy and fully operational.
> - **root_cause**: The system is operating optimally; the AMF maintains an active N2 control plane connection and stable UE registrations. (primary_suspect_nf: `amf`)
> - **affected_components**:
>     - `?`: ?
> - **recommendation**: Verify continuous baseline stability by monitoring the AMF 'ran_ue' gauge and confirming steady-state registration logs.
> - **confidence**: medium
> - **verdict_kind**: confirmed
> - **explanation**: The 5G SA and IMS stack is entirely healthy and functioning normally. To verify baseline operations, the AMF was investigated to confirm control plane and UE status. Automated probes verified that all network components are actively running with zero containers down. Diagnostic metrics definitively confirmed that the N2 connection is alive (gnb=1) and both expected UEs remain successfully attached (ran_ue=2). While a process listener check returned an ambiguous result due to standard tooling omitting SCTP ports by default, the active gNB metrics firmly prove the control plane connection is established. Consequently, the hypothesis that the stack is fully operational is confirmed with no network faults present.

### Scoring Breakdown

**Overall score: 0%**

**Scorer assessment:** The agent completely missed the UPF bandwidth cap, falsely concluding that the entire network stack was healthy and operating normally.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | No | The agent failed to identify the UPF bandwidth cap, instead concluding that the entire 5G SA and IMS stack is healthy and operating normally. |
| Component overlap | 0% | The agent did not identify the UPF as an affected component, listing '?' instead and using AMF as a placeholder. |
| Severity correct | No | The agent assessed the system as fully operational and healthy, completely missing the severe bandwidth degradation affecting VoNR media. |
| Fault type identified | No | The agent did not identify any network degradation or packet loss, claiming the system is operating optimally. |
| Layer accuracy | No | The agent rated the 'core' layer (which contains the UPF) as green/healthy, failing to identify the degradation in this layer. |
| Confidence calibrated | No | The agent expressed medium confidence in a completely incorrect diagnosis of a healthy network. |

**Ranking:** The correct root cause (UPF bandwidth cap) was not listed in the agent's diagnosis.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 337,223 |
| Output tokens | 3,394 |
| Thinking tokens | 20,132 |
| **Total tokens** | **360,749** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| SymptomClassifier | 0 | 0 | 0 |
| EventAggregator | 0 | 0 | 0 |
| CorrelationAnalyzer | 0 | 0 | 0 |
| RAGRetriever | 0 | 0 | 0 |
| OperationalLessons | 0 | 0 | 0 |
| NetworkAnalystAgent | 208,971 | 12 | 6 |
| Phase 3 NetworkAnalyst__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 8,833 | 0 | 1 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| InvestigatorAgent_h1 | 41,194 | 4 | 3 |
| InvestigatorAgent_h1 | 89,675 | 6 | 5 |
| InvestigatorAgent_h1__reconciliation | 0 | 0 | 0 |
| Phase5FanOutAudit | 0 | 0 | 0 |
| Phase6.5CandidatePool | 0 | 0 | 0 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 12,076 | 0 | 1 |
| Phase 7 Synthesis__guardrail | 0 | 0 | 0 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 428.2s
