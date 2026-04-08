# Episode Report: P-CSCF Latency

**Agent:** v5  
**Episode ID:** ep_20260407_000953_p_cscf_latency  
**Date:** 2026-04-07T00:09:54.463045+00:00  
**Duration:** 509.6s  

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
- **Actual elapsed:** 30.0s
- **Nodes with significant deltas:** 0
- **Nodes with any drift:** 4

## Symptoms Observed

Symptoms detected: **No**  
Observation iterations: 1

## Anomaly Screening (Phase 0)

No anomalies detected by the statistical screener.

## Network Analysis (Phase 1)

**Summary:** The network is partially degraded due to a critical Diameter timeout in the IMS layer, preventing user authorization.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | All infrastructure components (mongo, mysql, dns) are running and responsive. |
| **ran** | 🟢 GREEN | gNB is connected and 2 UEs are attached. |
| **core** | 🟢 GREEN | All 5G Core components are healthy, and 4 PDU sessions are established. |
| **ims** | 🔴 RED | I-CSCF is experiencing Diameter timeouts when trying to contact the HSS for user authorization (UAR). |

**IMS evidence:**
- icscf cdp:timeout = 1.0 (expected: 0.0) from get_nf_metrics/compare_to_baseline
- icscf ims_icscf:uar_timeouts = 1.0 (expected: 0.0) from get_nf_metrics/compare_to_baseline

**Suspect components:**

- **icscf** (high): I-CSCF is the component explicitly reporting the Diameter timeout (cdp:timeout=1.0), which is a direct symptom of the failure.
- **pyhss** (medium): PyHSS is the destination for the I-CSCF's timed-out request (UAR). The timeout could be caused by HSS being slow, unresponsive, or failing to process the request.

**Investigation hint:** The root of the issue lies in the IMS layer, specifically on the Cx (Diameter) interface between the I-CSCF and PyHSS. The I-CSCF is failing to get a response to a User-Authorization-Request (UAR). The next step is to analyze this specific transaction: check the logs on both I-CSCF and PyHSS for this request, and if possible, examine network traffic between them to see if the Diameter messages are being sent and received correctly.

**Tools called:** get_vonr_components, get_network_topology, get_network_status, get_nf_metrics, get_dp_quality_gauges, check_stack_rules, compare_to_baseline


## Pattern Match (Phase 2)

**❌ Match:** No matching signature found

- **Confidence:** low
- **Failure domain:** unknown
- **Baseline anomalies:** 2 metrics across 2 components


## Investigation Instruction (Phase 3)

> Anomalies detected in IMS layer. Suspect components: I-CSCF (high confidence), PyHSS (medium confidence). I-CSCF is experiencing critical Diameter timeouts (ims_icscf:uar_timeouts=1.0, cdp:timeout=1.0) when sending User-Authorization-Requests (UAR) to PyHSS.
>
> INVESTIGATE: The Cx (Diameter) interface between I-CSCF and PyHSS.
> 1.  **Transport Layer (first per Hierarchy of Truth):** Use `measure_rtt` between I-CSCF and PyHSS to check basic network reachability and latency. If possible and allowed, observe network traffic using `tcpdump` to confirm if Diameter messages are being sent by I-CSCF and received by PyHSS, and if any Diameter answers are being sent back.
> 2.  **Application Layer:** Examine logs on both I-CSCF and PyHSS for errors, retransmissions, or slow processing related to the User-Authorization-Request (UAR) transaction.
>
> RAN, Core, and Infrastructure layers are GREEN; do not investigate them.

## Ground Truth

**Failure domain:** ims_signaling  
**Protocol impact:** SIP  
**Affected components:** pcscf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v5-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 86.1s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ```json
> {
>   "causes": [
>     {
>       "summary": "The investigation did not produce verifiable evidence. Manual investigation is required.",
>       "timeline": [],
>       "root_cause": "Unknown — the automated investigation could not verify its own findings.",
>       "affected_components": [
>         {
>           "name": "icscf",
>           "reason": "The Network Analyst identified I-CSCF as the component explicitly reporting a Diameter timeout (cdp:timeout=1.0), which is a direct symptom of a failure."
>         },
>         {
>           "name": "pyhss",
>           "reason": "The Network Analyst identified PyHSS as the destination for the I-CSCF's timed-out User-Authorization-Request (UAR). The timeout could be caused by HSS being unresponsive."
>         }
>       ],
>       "recommendation": "Manual investigation required. Start from the Network Analyst's suspect list and verify each component's state with direct tool calls: measure_rtt, check_process_listeners, read_container_logs, read_running_config. Do not act on the Investigator's unverified claims without independent verification.",
>       "confidence": "low",
>       "explanation": "The initial network analysis identified a critical Diameter timeout in the IMS layer, where the I-CSCF is failing to receive authorization responses from the PyHSS. However, the subsequent automated investigation failed to produce any verifiable evidence. The Investigator agent produced no tool calls — any evidence citations in its output are fabricated. This diagnosis has been downgraded to low confidence because the investigation phase did not produce reliable evidence. A human operator should investigate manually before taking action."
>     }
>   ]
> }
> ```

### Scoring Breakdown

**Overall score: 35%**

**Scorer assessment:** The agent correctly identified a severe timeout-related fault and expressed appropriate low confidence, but completely missed the actual root cause (P-CSCF latency) and the primary affected component.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | No | The simulated failure was P-CSCF latency. The agent diagnosed an 'Unknown' root cause, pointing to a Diameter timeout between I-CSCF and PyHSS, which is not the actual root cause. |
| Component overlap | 0% | The primary affected component was P-CSCF. The agent identified I-CSCF and PyHSS, completely missing the P-CSCF. |
| Severity correct | Yes | The simulated failure involved latency leading to timeouts and registration failures (a severe impact). The agent's diagnosis, while incorrect in root cause, correctly identified a severe impact in the form of 'Diameter timeout' and implied 'IMS registration failures'. |
| Fault type identified | Yes | The simulated failure manifested as timeouts (SIP REGISTER 408 Request Timeout, Kamailio tm transaction timeouts). The agent correctly identified a 'timeout' as the observable fault type, specifically a 'Diameter timeout'. |
| Confidence calibrated | Yes | The agent stated 'low' confidence and explicitly mentioned that the automated investigation could not verify its findings and that the Investigator agent produced no tool calls. Given that the diagnosis completely missed the actual root cause and component, this low confidence is well-calibrated and appropriate. |

**Ranking:** The correct cause (P-CSCF latency) was not listed among the agent's findings.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 47,640 |
| Output tokens | 2,666 |
| Thinking tokens | 4,655 |
| **Total tokens** | **54,961** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| NetworkAnalystAgent | 34,568 | 8 | 3 |
| PatternMatcherAgent | 0 | 0 | 0 |
| InstructionGeneratorAgent | 4,693 | 0 | 1 |
| InvestigatorAgent | 7,135 | 0 | 1 |
| EvidenceValidatorAgent | 0 | 0 | 0 |
| SynthesisAgent | 8,565 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 509.5s
