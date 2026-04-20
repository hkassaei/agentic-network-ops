# Episode Report: IMS Network Partition

**Agent:** v5  
**Episode ID:** ep_20260417_042643_ims_network_partition  
**Date:** 2026-04-17T04:26:45.356294+00:00  
**Duration:** 264.6s  

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
- **Nodes with significant deltas:** 2
- **Nodes with any drift:** 4

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

### Metrics Changes

| Node | Metric | Baseline | Current | Delta |
|------|--------|----------|---------|-------|
| rtpengine | owned_sessions | 0.0 | 3.0 | 3.0 |
| rtpengine | total_sessions | 0.0 | 3.0 | 3.0 |
| smf | bearers_active | 4.0 | 7.0 | 3.0 |

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 0.94 (threshold: 0.70, trained on 213 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following specific metrics were flagged as the top contributors to the anomaly. These MUST be reflected in your layer ratings:

| Component | Metric | Current | Learned Normal | Severity |
|-----------|--------|---------|---------------|----------|
| normalized | upf.gtp_outdatapktn3upf_per_ue | 0.03 | 3.65 | MEDIUM |
| normalized | upf.gtp_indatapktn3upf_per_ue | 0.12 | 3.75 | MEDIUM |
| derived | upf_activity_during_calls | 1.00 | 0.44 | LOW |
| normalized | pcscf.dialogs_per_ue | 0.00 | 0.60 | LOW |

## Network Analysis (Phase 1)

**Summary:** The network is currently stable but experienced a significant data plane failure in the core network during the analysis window.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | All infrastructure components are running and connected. |
| **ran** | 🟢 GREEN | gNB is running and both UEs are attached to the AMF. |
| **core** | 🟡 YELLOW | A significant drop in UPF data plane traffic was detected during the event window, indicating a potential user plane forwarding issue. |
| **ims** | 🟡 YELLOW | IMS metrics indicate a lack of session activity, likely a downstream symptom of the core network data plane issue. |

**CORE evidence:**
- upf.gtp_outdatapktn3upf_per_ue was 0.03, expected ~3.65 (AnomalyScreener)
- upf.gtp_indatapktn3upf_per_ue was 0.12, expected ~3.75 (AnomalyScreener)

**IMS evidence:**
- pcscf.dialogs_per_ue was 0.00, expected ~0.60 (AnomalyScreener)

**Suspect components:**

- **upf** (high): The AnomalyScreener flagged a severe drop in both incoming and outgoing GTP packets per UE at the UPF, making it the primary suspect for a data plane failure. This indicates that user traffic was not being forwarded correctly.
- **pcscf** (low): The lack of dialogs at the P-CSCF is likely a downstream symptom of the UPF issue. If SIP signaling from the UE is dropped by the UPF, no dialogs can be established.

**Investigation hint:** The investigation should focus on the UPF as the primary suspect. The anomaly screener detected a near-total drop in GTP traffic during a period of expected activity, suggesting a data plane forwarding failure. Although live metrics now show an idle network, the fault was transient and severe. The Investigator should analyze UPF logs and detailed GTP counters from the event period (last 122 seconds) to find evidence of packet drops, errors on the N3/N9 interfaces, or PFCP session misconfiguration from the SMF.

**Tools called:** get_vonr_components, get_network_topology, get_network_status, get_nf_metrics, get_dp_quality_gauges, read_env_config, measure_rtt, check_stack_rules, compare_to_baseline


## Pattern Match (Phase 2)

**❌ Match:** No matching signature found

- **Confidence:** low
- **Failure domain:** unknown
- **Baseline anomalies:** 1 metrics across 1 components


## Investigation Instruction (Phase 3)

> PRIMARY HYPOTHESIS TO FALSIFY: The UPF experienced a data plane forwarding issue, indicated by a severe drop in incoming and outgoing GTP packets per UE.
>
> FALSIFICATION PROBES (minimum 2, target 3):
>
> Probe 1 — gNB (Upstream Data Plane):
>   Tool: get_nf_metrics(component='gnb')
>   Expected if hypothesis holds: gNB metrics should show data packets being successfully sent towards the UPF on the N3 interface during the event window (last 122 seconds). This would imply the gNB was doing its job, and the UPF failed to forward the traffic it received.
>   Falsifying observation: gNB metrics show no (or significantly reduced) data packets being sent on N3 towards the UPF during the event window. This would indicate the problem originates upstream of the UPF's data plane, potentially at the gNB or even the UE, rather than the UPF itself failing to forward received traffic.
>
> Probe 2 — SMF (Control Plane for UPF):
>   Tool: get_nf_metrics(component='smf')
>   Expected if hypothesis holds: SMF metrics should show successful PFCP session establishments and modifications, with no abnormal increase in PFCP errors or failures related to the UPF during the event window. This would suggest that the UPF was correctly configured by the SMF, but then failed at the data plane level.
>   Falsifying observation: SMF metrics show a significant increase in PFCP session setup/modification failures, a decrease in active PFCP sessions, or errors related to UPF interaction during the event window. This would imply that the UPF's data plane issue is a symptom of a control plane problem, where the SMF failed to properly instruct or manage the UPF.
>
> ADDITIONAL NOTES (optional):
>   - The Network Analyst previously noted "gNB is running and both UEs are attached to the AMF," suggesting basic RAN connectivity was present. However, this does not guarantee data plane forwarding.
>   - The NA also flagged `pcscf.dialogs_per_ue` as a downstream symptom; therefore, probing P-CSCF further would likely confirm the existing hypothesis rather than falsify it.

## Investigation (Phase 4)

> ### Hypothesis
> Not assessed — the mechanical guardrail triggered before the Investigator could produce a trustworthy verdict.
>
> ### Falsification Probes Executed
> Tool calls made: 0 (minimum required: 2).
> The Investigator's self-reported output has been discarded because it did not execute the minimum number of probes needed to falsify the Network Analyst's hypothesis. Any [EVIDENCE: ...] citations the Investigator produced are not backed by real tool invocations and have been removed.
>
> ### Verdict
> - **Verdict:** INCONCLUSIVE
> - **Reasoning:** Mechanical override. The Investigator made only 0 tool call(s) — below the 2-probe minimum required to attempt falsification. Confidence in any downstream diagnosis must be capped at medium per the INCONCLUSIVE branch in the Synthesis prompt.

## Evidence Validation (Phase 5)

**Verdict:** has_warnings
**Investigator confidence:** low
**Citations:** 0/0 verified

**WARNING:** Investigator made ZERO tool calls — all evidence citations are fabricated.

```
⚠️ CRITICAL: InvestigatorAgent made ZERO tool calls — no actual verification was performed.
Evidence validation: 0/0 citations verified (0 unmatched). Investigator: 0 citations from 0 tool calls.
Verdict: has_warnings. Confidence: low.

Tool calls vs. citations:
  NetworkAnalystAgent:
    ✗ check_stack_rules — called but NOT cited in output
    ✗ compare_to_baseline — called but NOT cited in output
    ✗ get_dp_quality_gauges — called but NOT cited in output
    ✗ get_network_status — called but NOT cited in output
    ✗ get_network_topology — called but NOT cited in output
    ✗ get_nf_metrics — called but NOT cited in output
    ✗ get_vonr_components — called but NOT cited in output
    ✗ measure_rtt — called but NOT cited in output
    ✗ read_env_config — called but NOT cited in output
```

## Ground Truth

**Failure domain:** ims_signaling  
**Protocol impact:** SIP  
**Affected components:** pcscf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v5-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 127.2s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: The investigation did not produce verifiable evidence. Manual investigation is required.
> - **timeline**:
> - **root_cause**: Unknown — the automated investigation could not verify its own findings.
> - **affected_components**:
>     - `upf`: Suspect
>     - `pcscf`: Suspect
> - **recommendation**: Manual investigation required. Start from the Network Analyst's suspect list and verify each component's state with direct tool calls: measure_rtt, check_process_listeners, read_container_logs, read_running_config. Do not act on the Investigator's unverified claims without independent verification.
> - **confidence**: low
> - **explanation**: The Network Analyst detected a significant, transient data plane failure in the core network. Anomaly detection flagged a severe drop in incoming and outgoing GTP packets at the UPF, making it the primary suspect. However, the subsequent automated investigation phase failed to execute and produced no verifiable evidence. The Investigator agent produced no tool calls, meaning any claims it made are fabricated. This diagnosis has been downgraded to low confidence because the investigation phase did not produce reliable evidence. A human operator should investigate manually before taking action.

### Scoring Breakdown

**Overall score: 40%**

**Scorer assessment:** The agent correctly assessed the severity and attributed the P-CSCF symptom to the IMS layer, but failed to identify the P-CSCF network partition as the root cause, instead focusing on an incorrect UPF data plane issue. Its low confidence was appropriate.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | No | The simulated failure was an IMS Network Partition affecting the P-CSCF. The agent's root cause was 'Unknown' and its primary suspect was the UPF due to a data plane failure, incorrectly attributing the P-CSCF issue as a downstream symptom. |
| Component overlap | 50% | The agent listed 'pcscf' as a suspect component, which is the correct primary affected component. However, it was listed as a secondary suspect with low confidence, and its observed issues were incorrectly attributed as a downstream symptom of a UPF problem, rather than the root cause. |
| Severity correct | Yes | The simulated failure involved 'SIP signaling completely severed' and 'New REGISTER and INVITE fail', indicating a severe outage. The agent described a 'significant, transient data plane failure' and 'severe drop in incoming and outgoing GTP packets' and 'lack of session activity', which aligns with a severe impact. |
| Fault type identified | No | The simulated fault type was 'Network partition' / 'component isolated'. The agent focused on 'data plane failure' and 'drop in GTP packets' for the UPF, and 'lack of dialogs' for the P-CSCF, which is a symptom, not the fault type of isolation/partition. |
| Layer accuracy | Yes | The 'pcscf' belongs to the 'ims' layer. The agent correctly flagged the 'ims' layer as YELLOW with evidence from 'pcscf.dialogs_per_ue'. While its causal reasoning was incorrect, the layer attribution for the observed symptom was accurate. |
| Confidence calibrated | Yes | The agent stated 'low' confidence and explicitly noted that 'the automated investigation could not verify its own findings' and 'no verifiable evidence'. Given that the root cause was missed and the primary suspect was incorrect, a low confidence is appropriate and well-calibrated. |

**Ranking:** The agent's root cause was 'Unknown'. While 'pcscf' was listed as a suspect, it was not identified as the primary root cause, and its issues were misattributed as a downstream symptom of another component (UPF).


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 103,510 |
| Output tokens | 2,942 |
| Thinking tokens | 9,803 |
| **Total tokens** | **116,255** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| NetworkAnalystAgent | 81,427 | 13 | 6 |
| PatternMatcherAgent | 0 | 0 | 0 |
| InstructionGeneratorAgent | 17,577 | 2 | 2 |
| InvestigatorAgent | 9,805 | 0 | 1 |
| EvidenceValidatorAgent | 0 | 0 | 0 |
| SynthesisAgent | 7,446 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 264.6s
