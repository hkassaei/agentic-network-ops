# Episode Report: P-CSCF Latency

**Agent:** v5  
**Episode ID:** ep_20260408_043527_p_cscf_latency  
**Date:** 2026-04-08T04:35:28.086395+00:00  
**Duration:** 356.6s  

---

## Scenario

**Category:** network  
**Blast radius:** single_nf  
**Description:** Inject 500ms latency on the P-CSCF (SIP edge proxy). SIP T1 timer is 500ms, so REGISTER transactions will start timing out. Tests IMS resilience to WAN-like latency on the signaling path.

## Faults Injected

- **network_latency** on `pcscf` — {'delay_ms': 2000, 'jitter_ms': 50}

## Baseline (Pre-Fault)

Stack phase before injection: **ready**
All containers running at baseline.

## Fault Propagation Verification

**Verdict:** ⚠️ `inconclusive`

- **Wait:** 30s
- **Actual elapsed:** 30.01s
- **Nodes with significant deltas:** 0
- **Nodes with any drift:** 5

## Symptoms Observed

Symptoms detected: **No**  
Observation iterations: 1

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 1.00 (threshold: 0.70, trained on 50 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following specific metrics were flagged as the top contributors to the anomaly. These MUST be reflected in your layer ratings:

| Component | Metric | Current | Learned Normal | Severity |
|-----------|--------|---------|---------------|----------|
| icscf | core:rcv_requests_register_rate | 1500.00 | 0.08 | HIGH |
| scscf | ims_registrar_scscf:accepted_regs_rate | 600.00 | 0.04 | HIGH |
| pcscf | core:rcv_requests_invite_rate | 600.00 | 0.04 | HIGH |
| pcscf | core:rcv_requests_register_rate | 900.00 | 0.08 | HIGH |
| pcscf | httpclient:connfail_rate | 600.00 | 0.27 | HIGH |
| pcscf | sl:4xx_replies_rate | 300.00 | 0.00 | HIGH |
| scscf | cdp:replies_received_rate | 600.00 | 0.08 | HIGH |
| scscf | core:rcv_requests_register_rate | 600.00 | 0.08 | HIGH |
| pcscf | sl:1xx_replies_rate | 600.00 | 0.12 | HIGH |
| upf | fivegs_ep_n3_gtp_indatapktn3upf_rate | 4800.00 | 5.04 | HIGH |

## Network Analysis (Phase 1)

**Summary:** The network is experiencing a critical failure in the IMS layer, caused by extreme transport-layer latency originating from the P-CSCF container, leading to widespread SIP signaling timeouts and registration failures.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | All infrastructure components (mongo, mysql, dns) are running and responsive. |
| **ran** | 🟢 GREEN | gNB is connected and 2 UEs are attached, as expected. |
| **core** | 🟡 YELLOW | The core control plane appears stable, but a high UPF packet rate was flagged and connectivity from the IMS layer (P-CSCF) to the PCF is severely degraded. |
| **ims** | 🔴 RED | The IMS signaling plane is non-functional due to a severe latency issue at the P-CSCF, causing cascading failures and timeouts across all SIP registration and call setup procedures. |

**CORE evidence:**
- upf:fivegs_ep_n3_gtp_indatapktn3upf_rate was flagged as a HIGH severity anomaly (4800.00 vs 5.04)
- RTT from P-CSCF to PCF is extremely high (~2981ms), which may impact policy control.

**IMS evidence:**
- Catastrophic RTT from P-CSCF to its peers: ~2023ms to I-CSCF, ~1967ms to RTPEngine.
- AnomalyScreener flagged multiple IMS components with HIGH severity: pcscf, icscf, scscf.
- icscf:core:rcv_requests_register_rate is abnormally high (1500.00 vs 0.08), indicating likely client retransmissions.
- pcscf:sl:4xx_replies_rate is high (300.00 vs 0.00), indicating client-side errors, likely due to timeouts.
- icscf shows Diameter timeouts (cdp:timeout = 1.0), likely from failed communication with HSS or other peers due to transport delays.

**Suspect components:**

- **pcscf** (high): The 'measure_rtt' tool reported catastrophic latency (~2-3 seconds) from the P-CSCF container to ALL of its network peers (I-CSCF, RTPEngine, PCF). RTT from other containers is normal. This indicates the issue is localized to the P-CSCF container or its host.
- **icscf** (medium): This component was the top-ranked anomaly by the screener, with its register request rate showing the largest statistical deviation. It is directly impacted by P-CSCF's latency, causing it to become a major symptom hotspot.

**Investigation hint:** The evidence strongly points to a transport-layer crisis originating at the P-CSCF. The next step should be to investigate the internal state of the 'pcscf' container to understand the source of the extreme latency. Check for process-level issues, resource exhaustion (CPU, memory), or network interface problems within that container. Use 'check_process_listeners' and 'read_container_logs' on 'pcscf' to start.

**Tools called:** get_vonr_components, get_network_topology, get_network_status, get_nf_metrics, get_dp_quality_gauges, read_env_config, measure_rtt, check_stack_rules


## Pattern Match (Phase 2)

**❌ Match:** No matching signature found

- **Confidence:** low
- **Failure domain:** unknown
- **Baseline anomalies:** 2 metrics across 2 components


## Investigation Instruction (Phase 3)

> CRITICAL IMS FAILURE: The IMS layer is non-functional due to severe transport-layer latency originating from the P-CSCF, causing widespread SIP signaling timeouts and registration failures. The RAN and Infrastructure layers are GREEN – do not investigate them. The Core layer is YELLOW due to a high UPF packet rate and extremely high RTT from the P-CSCF to the PCF, which is likely a secondary effect of the P-CSCF's primary transport issue.
>
> PRIMARY SUSPECT: The `pcscf` container (high confidence).
> FIRST, and critically: Run `measure_rtt` *from* the `pcscf` container to all its neighbors (I-CSCF, RTPEngine, PCF) to confirm the catastrophic transport-layer latency reported by the Network Analyst. This follows the Hierarchy of Truth: Transport > Core > Application.
> NEXT: Investigate the internal state of the `pcscf` container to understand the source of this extreme latency. Look for process-level issues, resource exhaustion (CPU, memory), or network interface problems within that container. Use `check_process_listeners` on `pcscf` to check process health and listening ports, and then `read_container_logs` for `pcscf` to find any errors or warnings related to its network stack or operations.
>
> The `icscf` is a secondary suspect (medium confidence) exhibiting symptoms like abnormally high register request rates and Diameter timeouts. These are likely cascading effects of the `pcscf`'s transport-layer latency. Do not investigate `icscf` until the root cause of the `pcscf` transport issue is identified.

## Evidence Validation (Phase 5)

**Verdict:** has_warnings
**Investigator confidence:** low
**Citations:** 0/0 verified

```
⚠️ WARNING: InvestigatorAgent made 4 tool calls but produced ZERO [EVIDENCE: ...] citations. The investigation narrative is unverifiable — tool results exist but are not traceably referenced.
Evidence validation: 0/0 citations verified (0 unmatched). Investigator: 0 citations from 4 tool calls.
Verdict: has_warnings. Investigator confidence: low.

Tool calls vs. citations:
  NetworkAnalystAgent:
    ✗ check_stack_rules — called but NOT cited in output
    ✗ get_dp_quality_gauges — called but NOT cited in output
    ✗ get_network_status — called but NOT cited in output
    ✗ get_network_topology — called but NOT cited in output
    ✗ get_nf_metrics — called but NOT cited in output
    ✗ get_vonr_components — called but NOT cited in output
    ✗ measure_rtt — called but NOT cited in output
    ✗ read_env_config — called but NOT cited in output
  InvestigatorAgent:
    ✗ OntologyConsultationAgent — called but NOT cited in output
    ✗ check_process_listeners — called but NOT cited in output
    ✗ measure_rtt — called but NOT cited in output
    ✗ read_container_logs — called but NOT cited in output
```

## Ground Truth

**Failure domain:** ims_signaling  
**Protocol impact:** SIP  
**Affected components:** pcscf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v5-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 186.3s

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
>     - `pcscf`: Suspect
>     - `icscf`: Suspect
> - **recommendation**: Manual investigation is required. Start from the Network Analyst's suspect list. The primary hypothesis is extreme transport latency originating within the `pcscf` container. Use `measure_rtt` from `pcscf` to its peers (I-CSCF, RTPEngine, PCF) to confirm the high latency. If confirmed, use `check_process_listeners` and `read_container_logs` on the `pcscf` container to find the source of the internal transport issue.
> - **confidence**: low
> - **explanation**: The Network Analyst identified a critical failure in the IMS layer, likely caused by extreme transport latency originating from the `pcscf` container, leading to widespread SIP signaling timeouts. However, the subsequent Investigator agent failed to produce any output or verifiable evidence to confirm or deny this hypothesis. This diagnosis has been downgraded to low confidence because the investigation phase did not produce any findings. A human operator should investigate manually, following the analyst's initial hypothesis, before taking any action.

### Scoring Breakdown

**Overall score: 60%**

**Scorer assessment:** The agent correctly identified the affected component, severity, and fault type as a strong hypothesis, but failed to commit to it as the definitive root cause due to a lack of automated verification, leading to a lower score for root cause identification.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | No | The agent explicitly states "root_cause: Unknown", indicating it did not definitively identify the simulated failure mode as the root cause, despite having a correct hypothesis for manual investigation. |
| Component overlap | 100% | The primary affected component, `pcscf`, was correctly identified as a suspect. `icscf` is a downstream component and does not penalize the score. |
| Severity correct | Yes | The agent describes a "critical failure in the IMS layer" and "widespread SIP signaling timeouts" due to "extreme transport latency", which accurately reflects the severe impact of the latency causing registration failures. |
| Fault type identified | Yes | The agent correctly identified "extreme transport latency" as the fault type, which is semantically equivalent to the simulated "elevated network latency". |
| Confidence calibrated | Yes | The agent's low confidence is appropriate given its stated "root_cause: Unknown" and the failure of its automated investigation to verify its hypothesis. It correctly assessed its own process limitations. |

**Ranking:** The agent's formal `root_cause` field is "Unknown". While the correct cause is presented as a "primary hypothesis" for manual investigation, it is not ranked as the primary identified root cause.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 106,486 |
| Output tokens | 2,419 |
| Thinking tokens | 11,357 |
| **Total tokens** | **120,262** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| NetworkAnalystAgent | 76,522 | 13 | 5 |
| PatternMatcherAgent | 0 | 0 | 0 |
| InstructionGeneratorAgent | 5,764 | 0 | 1 |
| InvestigatorAgent | 30,960 | 6 | 3 |
| EvidenceValidatorAgent | 0 | 0 | 0 |
| SynthesisAgent | 7,016 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 356.6s
