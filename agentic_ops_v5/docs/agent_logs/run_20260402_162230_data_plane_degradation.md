# Episode Report: Data Plane Degradation

**Agent:** v5  
**Episode ID:** ep_20260402_161733_data_plane_degradation  
**Date:** 2026-04-02T16:17:35.554308+00:00  
**Duration:** 294.4s  

---

## Scenario

**Category:** network  
**Blast radius:** single_nf  
**Description:** Inject 30% packet loss on the UPF. RTP media streams will degrade, voice quality drops. Tests whether the stack detects and reports data plane quality issues.

## Faults Injected

- **network_loss** on `upf` — {'loss_pct': 30}

## Baseline (Pre-Fault)

Stack phase before injection: **ready**
All containers running at baseline.

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

### Metrics Changes

| Node | Metric | Baseline | Current | Delta |
|------|--------|----------|---------|-------|
| icscf | cdp:average_response_time | 90.0 | 97.0 | 7.0 |
| icscf | ims_icscf:lir_replies_response_time | 85.0 | 247.0 | 162.0 |
| icscf | cdp:replies_received | 9.0 | 10.0 | 1.0 |
| icscf | ims_icscf:lir_avg_response_time | 85.0 | 123.0 | 38.0 |
| icscf | cdp:replies_response_time | 815.0 | 977.0 | 162.0 |
| icscf | core:rcv_requests_invite | 1.0 | 2.0 | 1.0 |
| icscf | ims_icscf:lir_replies_received | 1.0 | 2.0 | 1.0 |
| pcscf | core:rcv_requests_invite | 2.0 | 4.0 | 2.0 |
| pcscf | httpclient:connok | 2.0 | 4.0 | 2.0 |
| pcscf | sl:1xx_replies | 14.0 | 16.0 | 2.0 |
| pcscf | dialog_ng:active | 0.0 | 2.0 | 2.0 |
| pcscf | httpclient:connfail | 1154.0 | 1157.0 | 3.0 |
| pcscf | core:rcv_requests_options | 1149.0 | 1150.0 | 1.0 |
| pcscf | dialog_ng:processed | 2.0 | 4.0 | 2.0 |
| scscf | dialog_ng:active | 0.0 | 2.0 | 2.0 |
| scscf | core:rcv_requests_invite | 2.0 | 4.0 | 2.0 |
| scscf | dialog_ng:processed | 2.0 | 4.0 | 2.0 |
| upf | fivegs_ep_n3_gtp_indatapktn3upf | 2968.0 | 2969.0 | 1.0 |

## Pattern Match (Phase 2)

```
{"matched": false, "top_diagnosis": "No matching signature found", "confidence": "low", "failure_domain": "unknown", "matched_signatures": [], "baseline_anomalies": {"smf": [{"metric": "bearers_active", "expected": 4.0, "actual": 6.0, "alarm_if": "", "note": "Rises to 6 during active VoNR call (2 dedicated QoS flows for voice)"}], "icscf": [{"metric": "ims_icscf:uar_timeouts", "expected": 0.0, "actual": 2.0, "alarm_if": "> 0", "note": ""}], "scscf": [{"metric": "dialog_ng:active", "expected": 0.
```

## Anomaly Analysis (Phase 3)

> ### Causal Chain Hints
- No specific causal chains were found in the ontology for PCSCF, ICSCF, or SCSCF. Therefore, no direct causal chain patterns match the observed anomalies.

## Investigation Instruction (Phase 4)

> INVESTIGATE: PCSCF is experiencing severe HTTP connection failures (`httpclient:connfail = 1158.0` vs `connok = 4.0`), likely impacting its ability to communicate with other network functions, possibly related to its high `core:rcv_requests_options = 1151.0`. Concurrently, ICSCF shows `ims_icscf:uar_timeouts = 2.0`, indicating issues with User Authorization Requests, typically pointing to the HSS.

Suspect: PyHSS (HSS) or underlying network connectivity to it from both PCSCF and ICSCF.

Your ONL

## Ground Truth

**Failure domain:** data_plane  
**Protocol impact:** GTP-U  
**Affected components:** upf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v5-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 280.1s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: The Diameter service within the PyHSS (Home Subscriber Server) container has silently failed, causing IMS user authentication requests from the ICSCF to time out.
> - **timeline**:
>   1. The Diameter application inside the `pyhss` container fails, but the container itself remains in a running state.
>   2. The ICSCF forwards a Diameter User-Authorization-Request (UAR) to the PyHSS to authenticate a user.
>   3. The PyHSS Diameter service, being non-functional, fails to respond to the UAR message.
>   4. The request in the ICSCF times out, incrementing the `ims_icscf:uar_timeouts` metric and failing the user registration procedure.
>   5. The PCSCF experiences a very high rate of `httpclient:connfail` errors, which is a secondary symptom of the downstream IMS authentication failure.
> - **root_cause**: The initial anomaly analysis suspected an issue with PyHSS due to `uar_timeouts` on the ICSCF. The investigation confirmed this hypothesis. The root cause is an application-level failure within the `pyhss` container. While the container is running and its database is responsive to API queries ([EVIDENCE: `query_subscriber(...)` -> Successful]), its core Diameter service is non-operational, as evidenced by the complete lack of Diameter message processing in its logs ([EVIDENCE: `read_container_logs(container="pyhss", ...)`]). Healthy network connectivity was confirmed ([EVIDENCE: `measure_rtt(...)` -> RTT < 1ms]), definitively isolating the fault to the PyHSS application.
> - **affected_components**: pyhss, icscf, pcscf
> - **recommendation**: Restart the `pyhss` container to re-initialize the failed Diameter service.
> - **confidence**: high
> - **explanation**: The root cause of the outage is a silent failure of the Diameter service inside the PyHSS container. Although the container appears "running" to the orchestrator, the specific application responsible for handling authentication requests is not responding. This is causing the ICSCF's authentication requests to time out, which in turn prevents users from registering on the IMS network. We have ruled out any network connectivity issues between the components, confirming this is a pure application-level fault within PyHSS.

### Scoring Breakdown

**Overall score: 0%**

**Scorer assessment:** The agent completely misdiagnosed the simulated data plane degradation, incorrectly identifying an IMS control plane authentication failure with high confidence, indicating a significant failure in diagnosis and calibration.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | No | The simulated failure was 30% packet loss on the UPF, leading to data plane degradation and RTP media issues. The agent diagnosed a silent failure of the Diameter service within the PyHSS, causing IMS user authentication timeouts. These are entirely different root causes affecting different parts of the network stack (data plane vs. control plane, UPF vs. HSS/IMS). |
| Component overlap | 0% | The primary affected component in the simulation was the UPF. The agent identified PyHSS, ICSCF, and PCSCF as affected components. There is no overlap with the actual primary affected component. |
| Severity correct | No | The simulated failure was a 'degradation' (30% packet loss, voice quality drops). The agent diagnosed a complete failure of IMS user authentication, leading to 'failing the user registration procedure' and implying an 'outage' for authentication, which is a more severe and different type of impact than the simulated degradation. |
| Fault type identified | No | The simulated fault type was 'network degradation' (packet loss). The agent identified an 'application-level failure' or 'service hang' (Diameter service non-operational, requests time out). These are distinct fault types. |
| Confidence calibrated | No | The agent stated 'high' confidence, but its diagnosis was completely incorrect across all dimensions (root cause, component, severity, fault type). This indicates poor calibration. |

**Ranking:** The agent provided only one primary diagnosis, which was incorrect.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 140,742 |
| Output tokens | 8,164 |
| Thinking tokens | 22,675 |
| **Total tokens** | **171,581** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| TriageAgent | 12,029 | 3 | 4 |
| PatternMatcherAgent | 0 | 0 | 0 |
| AnomalyDetectorAgent | 49,964 | 8 | 5 |
| InstructionGeneratorAgent | 6,041 | 0 | 1 |
| InvestigatorAgent | 96,644 | 9 | 9 |
| SynthesisAgent | 6,903 | 0 | 1 |


## Post-Run Analysis

**Analyst:** manual review against verified ground truth
**Date:** 2026-04-02

### Why the Agent Scored 0%

The agent's reasoning was internally consistent — given what it could see, the PyHSS diagnosis was a plausible inference. The failure is upstream of the reasoning: the agent was **chasing the wrong signal from the start**.

### Problem 1: No Metrics for Data Plane Quality

The injected fault was 30% packet loss on the UPF. The only UPF metric captured:

| Node | Metric | Baseline | Current | Delta |
|------|--------|----------|---------|-------|
| upf | fivegs_ep_n3_gtp_indatapktn3upf | 2968.0 | 2969.0 | **+1** |

A cumulative packet counter does not reveal packet loss — it still increments, just fewer packets arrive. Detecting 30% loss requires input-vs-output ratios, drop counters, or RTP quality metrics (jitter, MOS, loss rate). None of these exist in the agent's telemetry. The UE2 pjsua logs clearly show `pkt loss=368 (51.1%)`, but UE logs are inaccessible by design. **Data plane degradation is fundamentally undetectable through the available metrics.**

### Problem 2: Call Setup Noise Dominated the Observation Window

The CallSetupAgent established a VoNR call immediately before the observation window. This produced a burst of IMS control plane activity that was the loudest signal in the 30-second window:

- `pcscf: core:rcv_requests_invite` +2 (call setup INVITEs)
- `scscf: dialog_ng:active` 0→2 (new dialogs from the call)
- `icscf: lir_replies_response_time` 85→247ms (lookup during call routing)
- `pcscf: httpclient:connfail` +3 (routine NRF polling failures)

These are normal call setup artifacts, not fault symptoms. But they dwarfed the invisible UPF signal.

### Problem 3: Pre-existing Anomaly Misled the Diagnosis

The baseline anomalies flagged `ims_icscf:uar_timeouts = 2.0` as alarming (`alarm_if: > 0`). This was a pre-existing condition unrelated to the injected fault. The agent couldn't distinguish it from a fault-induced symptom and built its entire investigation around it.

### The Misdirection Cascade

Each pipeline phase amplified the error from the previous one:

1. **Triage**: UPF delta invisible (+1), IMS metrics loud. Focused on IMS.
2. **Pattern Match**: No signature found (correct — no data plane degradation pattern exists in the ontology).
3. **Anomaly Detector** (49,964 tokens): Latched onto `uar_timeouts` and PCSCF `httpclient:connfail`. No causal chains found in ontology for these.
4. **Investigation Instruction**: Directed investigator to PCSCF HTTP failures and ICSCF UAR timeouts. Explicitly said "*Do not investigate AMF, SMF, PCF, or UPF*" — steering away from the actual faulty component.
5. **Investigator** (96,644 tokens, 9 tool calls): Faithfully investigated PyHSS. Found container running, DB responsive, Diameter logs quiet. Fabricated "silent Diameter failure" as root cause.
6. **Synthesis**: Packaged the wrong answer with high confidence.

### Structural Issues to Address

**A) Add data plane quality metrics.** The metrics collector needs RTP-level observability: packet loss ratios, jitter, MOS estimates, and UPF input-vs-output packet ratios or drop counters. Without these, any data plane degradation scenario is undiagnosable.

**B) Separate call setup from observation baseline.** The observation window should start after the call stabilizes, not immediately after setup. Call setup metrics (INVITE counts, dialog creation, LIR lookups) pollute the fault signal. Either add a stabilization delay or teach the anomaly detector to filter known call-setup patterns.

**C) Distinguish pre-existing anomalies from fault-induced symptoms.** The `uar_timeouts = 2` existed at baseline but was still treated as a fault symptom. The anomaly detector should only flag metrics that *changed* after injection, not pre-existing conditions that happen to exceed a threshold.

**D) Add a correction mechanism to the pipeline.** The multi-phase architecture amplifies early errors — once the instruction generator pointed away from the UPF, the investigator had no way to self-correct. Consider a feedback loop where the investigator can challenge the instruction if its findings don't converge on a coherent root cause.

## Resolution

**Heal method:** scheduled
**Recovery time:** 288.9s
