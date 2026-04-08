# Episode Report: P-CSCF Latency

**Agent:** v5  
**Episode ID:** ep_20260408_025631_p_cscf_latency  
**Date:** 2026-04-08T02:56:31.858146+00:00  
**Duration:** 714.3s  

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

**Verdict:** ✅ `confirmed`

- **Wait:** 30s
- **Actual elapsed:** 30.0s
- **Nodes with significant deltas:** 3
- **Nodes with any drift:** 5

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

### Metrics Changes

| Node | Metric | Baseline | Current | Delta |
|------|--------|----------|---------|-------|
| pcscf | core:rcv_requests_invite | 66.0 | 99.0 | 33.0 |
| pcscf | script:register_time | 287440.0 | 473303.0 | 185863.0 |
| pcscf | core:rcv_requests_register | 164.0 | 268.0 | 104.0 |
| pcscf | sl:1xx_replies | 110.0 | 169.0 | 59.0 |
| pcscf | script:register_success | 22.0 | 35.0 | 13.0 |
| pcscf | sl:4xx_replies | 25.0 | 36.0 | 11.0 |
| scscf | ims_registrar_scscf:sar_replies_received | 22.0 | 35.0 | 13.0 |
| scscf | cdp:replies_response_time | 4934.0 | 8070.0 | 3136.0 |
| scscf | ims_auth:mar_replies_response_time | 2521.0 | 4134.0 | 1613.0 |
| scscf | ims_registrar_scscf:sar_replies_response_time | 2413.0 | 3936.0 | 1523.0 |
| scscf | cdp:replies_received | 44.0 | 70.0 | 26.0 |
| scscf | ims_auth:mar_replies_received | 22.0 | 35.0 | 13.0 |
| scscf | ims_registrar_scscf:accepted_regs | 22.0 | 35.0 | 13.0 |
| scscf | core:rcv_requests_register | 44.0 | 70.0 | 26.0 |
| smf | bearers_active | 5.0 | 6.0 | 1.0 |

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 0.99 (threshold: 0.70, trained on 50 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following specific metrics were flagged as the top contributors to the anomaly. These MUST be reflected in your layer ratings:

| Component | Metric | Current | Learned Normal | Severity |
|-----------|--------|---------|---------------|----------|
| pcscf | core:rcv_requests_register_rate | 36746.09 | 0.08 | HIGH |
| pcscf | core:rcv_requests_invite_rate | 15748.33 | 0.04 | HIGH |
| icscf | core:rcv_requests_register_rate | 31496.65 | 0.08 | HIGH |
| pcscf | sl:1xx_replies_rate | 26247.21 | 0.12 | HIGH |
| icscf | cdp:replies_received_rate | 10498.88 | 0.06 | HIGH |
| scscf | cdp:replies_received_rate | 10498.88 | 0.08 | HIGH |
| scscf | core:rcv_requests_register_rate | 10498.88 | 0.08 | HIGH |
| pcscf | httpclient:connfail_rate | 5249.44 | 0.27 | HIGH |
| upf | fivegs_ep_n3_gtp_outdatapktn3upf_rate | 10498.88 | 4.92 | HIGH |
| upf | fivegs_ep_n3_gtp_indatapktn3upf_rate | 10498.88 | 5.04 | HIGH |

## Network Analysis (Phase 1)

**Summary:** The network is recovering from a massive signaling storm in the IMS layer that caused extreme request rates and downstream impacts to the 5G core data plane.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | All data stores (MongoDB, MySQL) and support services (DNS) are running and connected. |
| **ran** | 🟢 GREEN | gNB is connected and 2 UEs are attached to the AMF. |
| **core** | 🔴 RED | UPF experienced an anomalous burst of data plane traffic, statistically correlated with the IMS signaling storm. |
| **ims** | 🔴 RED | IMS layer was flooded by an extreme rate of SIP REGISTER and INVITE requests, causing system-wide anomalies. |

**CORE evidence:**
- upf:fivegs_ep_n3_gtp_outdatapktn3upf_rate was 10498.88 (expected ~4.92) per anomaly screener.
- upf:fivegs_ep_n3_gtp_indatapktn3upf_rate was 10498.88 (expected ~5.04) per anomaly screener.

**IMS evidence:**
- pcscf:core:rcv_requests_register_rate was 36746.09 (expected ~0.08) per anomaly screener.
- pcscf:core:rcv_requests_invite_rate was 15748.33 (expected ~0.04) per anomaly screener.
- icscf:core:rcv_requests_register_rate was 31496.65 (expected ~0.08) per anomaly screener.
- pcscf:httpclient:connfail_rate was 5249.44 (expected ~0.27) per anomaly screener.
- icscf:cdp:timeout = 1.0 from get_nf_metrics, indicating Diameter issues.

**Suspect components:**

- **pcscf** (high): The anomaly screener identified P-CSCF as the top anomaly, with REGISTER request rates over 450,000x the normal baseline. As the SIP entry point, it was the epicenter of the signaling storm.
- **icscf** (medium): Experienced a massive flood of REGISTER requests cascaded from the P-CSCF. It also recorded Diameter timeouts, suggesting it was overloaded or its downstream HSS was unresponsive.
- **scscf** (medium): Showed a significantly elevated REGISTER request rate, indicating the storm propagated through the entire SIP chain.
- **upf** (low): Exhibited an extremely high packet rate anomaly, which is likely a downstream symptom of the IMS signaling storm causing rapid creation/deletion of data plane resources, not a root cause.

**Investigation hint:** The network fault is characterized by a massive signaling storm originating at the IMS entry point. The P-CSCF, I-CSCF, and S-CSCF were inundated with SIP requests at rates thousands of times higher than normal. This appears to be the primary cause of the incident, with the anomalous UPF traffic being a secondary, cascading effect. The immediate priority is to understand the origin and nature of this traffic. Investigate the P-CSCF's logs from the event timeframe to identify the source IP addresses of the anomalous REGISTER/INVITE requests. Characterize this traffic: is it from legitimate UEs in a loop, or from an unauthorized external source? While the event appears to have subsided, understanding the trigger is critical to prevent recurrence.

**Tools called:** get_vonr_components, get_network_topology, get_network_status, get_nf_metrics, get_dp_quality_gauges, check_stack_rules


## Pattern Match (Phase 2)

**❌ Match:** No matching signature found

- **Confidence:** low
- **Failure domain:** unknown
- **Baseline anomalies:** 2 metrics across 2 components


## Investigation Instruction (Phase 3)

> Anomalies detected in IMS (RED) and Core (RED) layers, driven by a massive signaling storm in the IMS layer. The primary suspect is P-CSCF due to an extreme rate of SIP REGISTER and INVITE requests (e.g., `pcscf:core:rcv_requests_register_rate` was 36746.09, expected ~0.08). This storm also caused downstream impacts on I-CSCF (high REGISTER rate, Diameter timeouts like `icscf:cdp:timeout = 1.0`), S-CSCF, and anomalous data plane traffic on the UPF. RAN and Infrastructure layers are GREEN — do not investigate them.
>
> **FIRST: Check transport-layer connectivity from the primary suspect.**
> Run `measure_rtt` from `pcscf` to its direct neighbors (`icscf`, `smf`, `pyhss`) to rule out connectivity issues.
>
> **NEXT: Investigate the IMS layer, focusing on P-CSCF and the nature of the SIP storm (Application Layer).**
> 1.  **P-CSCF Logs:** Examine `pcscf` logs from the event timeframe to identify the source IP addresses of the anomalous SIP REGISTER/INVITE requests. Characterize this traffic: is it from legitimate UEs in a loop, or an unauthorized external source?
> 2.  **SIP State:** Use `get_nf_metrics` to confirm current SIP request rates on `pcscf`, `icscf`, and `scscf` (e.g., `core:rcv_requests_register`, `core:rcv_requests_invite`) to verify the storm has subsided or is ongoing.
> 3.  **Diameter Issues:** Investigate `icscf` for persistent Diameter issues. Check `icscf:cdp:timeout`, `ims_icscf:uar_timeouts`, and `ims_icscf:lir_timeouts` using `get_nf_metrics` to understand interactions with the HSS (pyhss).
>
> **THEN: Briefly confirm the UPF state (Data Plane Layer).**
> Use `get_nf_metrics` to check current `upf:fivegs_ep_n3_gtp_indatapktn3upf_rate` and `upf:fivegs_ep_n3_gtp_outdatapktn3upf_rate` to confirm if the anomalous data plane traffic has subsided, indicating it was a secondary symptom.

## Evidence Validation (Phase 5)

**Verdict:** clean
**Investigator confidence:** high
**Citations:** 1/1 verified

```
Evidence validation: 1/1 citations verified (0 unmatched).
Verdict: clean. Investigator confidence: high.
```

## Ground Truth

**Failure domain:** ims_signaling  
**Protocol impact:** SIP  
**Affected components:** pcscf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v5-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 167.8s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: The core issue is the unresponsiveness of the Service Communication Proxy (SCP) and the Home Subscriber Server (HSS), leading to critical failures in service discovery and user authorization within the IMS layer.
>   **timeline**:
>   1.  An initial massive SIP signaling storm (REGISTER/INVITE requests) inundated the IMS layer, starting at the P-CSCF.
>   2.  This high load likely overloaded authoritative components, specifically the SCP and the HSS (pyhss).
>   3.  Post-storm, these components have failed to recover. The P-CSCF is now continuously failing to register with the SCP, as evidenced by HTTP connection failures in its logs (`failed to register at SCP with code=28`).
>   4.  Simultaneously, the I-CSCF is experiencing Diameter protocol timeouts (`cdp:timeout`, `ims_icscf:uar_timeouts`) when attempting to contact the HSS for user authorization.
>   5.  These two failures break the fundamental IMS registration flow, rendering the service unusable even though the initial signaling storm has subsided.
>   **root_cause**: The SCP and HSS are unresponsive at the application layer. The P-CSCF cannot perform service registration with the SCP, and the I-CSCF cannot perform user authorization queries to the HSS. This suggests these central components either crashed or are stuck in a non-responsive state, triggered by the initial high-load event. Transport layer tests confirmed that basic network connectivity to these components is healthy.
>   **affected_components**:
>   - `scp`
>   - `pyhss`
>   - `pcscf`
>   - `icscf`
>   **recommendation**: Verify the process status and application-level health of the `scp` and `pyhss` containers. Check their logs for errors, high resource utilization (CPU/memory), or evidence of a crash. Confirm they are listening on their expected service ports and are responsive to application-specific health checks.
>   **confidence**: high
>   **explanation**: The network is suffering from the failure of two critical central components: the SCP and the HSS. Although the incident was triggered by a massive SIP signaling storm, the persistent root cause is that the P-CSCF can no longer communicate with the SCP for service discovery, and the I-CSCF cannot get responses from the HSS for user authorization. This is evidenced by HTTP connection failures from the P-CSCF and Diameter timeouts from the I-CSCF. The underlying transport network is healthy, pointing to an application-level failure within the SCP and HSS components themselves, which were likely overloaded by the initial storm.

### Scoring Breakdown

**Overall score: 25%**

**Scorer assessment:** The agent failed to identify the correct root cause (P-CSCF latency), instead attributing the issue to SCP and HSS unresponsiveness. While it correctly identified the severity and observable fault types, its high confidence was unwarranted given the incorrect root cause and primary affected components.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | No | The simulated failure was P-CSCF latency, leading to SIP transaction timeouts. The agent incorrectly identified the root cause as unresponsiveness of the SCP and HSS at the application layer, triggered by an initial SIP signaling storm. It completely missed the latency on the P-CSCF itself. |
| Component overlap | 0% | The primary affected component in the simulation was the P-CSCF. The agent's diagnosis explicitly states the 'core issue' and 'root_cause' are the SCP and HSS being unresponsive. While P-CSCF is listed as an 'affected_component', it is presented as a downstream component experiencing issues, not the source of the problem. |
| Severity correct | Yes | The simulated failure led to IMS registration failures and timeouts, effectively making the service unusable for registrations. The agent's assessment of 'critical failures' and 'service unusable' aligns with this impact. |
| Fault type identified | Yes | The agent identified 'HTTP connection failures' and 'Diameter protocol timeouts' and 'unresponsiveness', which are observable classes of failure consistent with the simulated latency causing timeouts. |
| Confidence calibrated | No | The agent stated 'high' confidence, but its root cause diagnosis was fundamentally incorrect, missing the actual simulated failure mode (P-CSCF latency). High confidence for an incorrect diagnosis is poorly calibrated. |

**Ranking:** The agent provided only one primary diagnosis, which was incorrect.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 122,133 |
| Output tokens | 4,575 |
| Thinking tokens | 10,169 |
| **Total tokens** | **136,877** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| NetworkAnalystAgent | 50,151 | 6 | 4 |
| PatternMatcherAgent | 0 | 0 | 0 |
| InstructionGeneratorAgent | 6,340 | 0 | 1 |
| InvestigatorAgent | 70,893 | 7 | 6 |
| EvidenceValidatorAgent | 0 | 0 | 0 |
| SynthesisAgent | 9,493 | 0 | 1 |


## Resolution

**Heal method:** scheduled
**Recovery time:** 714.3s

## Post-Run Analysis

### Score: 25% — Evidence Validator now working, but Investigator doesn't cite evidence

Continued progress on infrastructure: the Evidence Validator produced output for the first time (`Verdict: clean, 1/1 verified`). The anomaly screener and NetworkAnalyst are working well. The InstructionGenerator now correctly puts transport-layer probing first. But the Investigator still draws wrong conclusions and doesn't formally cite its evidence.

### What worked

**Evidence Validator (Phase 5):** First run where it appeared in the report with actual output. Verdict: clean, 1/1 citations verified, confidence: high. This validates that the plumbing fix (challenger now passes `evidence_validation` through) is working.

**Anomaly screener:** Score 0.99, 10 HIGH flags, pcscf register rate 36746x normal. Consistently working.

**NetworkAnalyst:** Correctly named pcscf as PRIMARY suspect (high). Correctly identified icscf and scscf as secondary cascading victims. Correctly noted UPF anomaly as downstream symptom.

**InstructionGenerator:** Now includes "FIRST: Check transport-layer connectivity from the primary suspect. Run `measure_rtt` from `pcscf`." This is exactly what we asked for.

### Issue 1: Investigator made 4 tool calls but ZERO `[EVIDENCE: ...]` citations

The per-phase breakdown shows `InvestigatorAgent | 70,893 | 7 | 6` — 7 tool calls. The Evidence Validator found `investigator_claims: []` — zero formal `[EVIDENCE: tool_name(args) -> "output"]` citations in the Investigator's text. The Investigator wrote a detailed narrative about SCP failures and HSS unresponsiveness but didn't formally cite any tool output.

**Why this matters:** The Evidence Validator checked 1 total citation (from NetworkAnalyst), found it matched, and returned `clean, high confidence`. It had no Investigator citations to validate. The validator's "clean" verdict was technically correct (no fabrications found) but operationally misleading — the Investigator's entire diagnosis was unsupported by formal evidence. The Synthesis agent then treated the diagnosis as reliable.

**Root cause:** The Investigator's prompt (investigator.md) says "Format evidence citations as: `[EVIDENCE: tool_name(args) -> excerpt]`" but this is presented as a formatting suggestion, not a hard requirement. The LLM generates a flowing narrative instead of the structured Evidence Chain format required by the prompt's Output Format section.

### Issue 2: Investigator interprets 2000ms RTT as "connectivity is healthy"

The InstructionGenerator told the Investigator to run `measure_rtt` from pcscf first. The Investigator ran it and saw the result. But it concluded "transport layer confirmed healthy" and moved on to application-layer investigation (logs, metrics). It found `code=28` (curl timeout) in pcscf logs and blamed the SCP.

The fundamental problem: 2000ms RTT on a Docker bridge network (normal: <1ms) is catastrophically slow for SIP (T1=500ms). But the Investigator doesn't understand that "2000ms RTT = everything on this container will timeout." It sees "packets are being delivered" and calls it healthy.

### Issue 3: Evidence Validator gave "clean, high" for unverifiable investigation

With 4 Investigator tool calls and 0 Investigator citations, the validator said "clean" because there were no UNMATCHED citations (you can't have unmatched citations if you have zero citations). This is a logic bug — an investigation with many tool calls but zero citations should be flagged as unverifiable, not clean.

### Fixes implemented

**1. Investigator prompt (`investigator.md`) — strengthened evidence rules:**
- Changed header to "Evidence Rules (MANDATORY — violations cause automatic downgrade)"
- Added warning: "An automated Evidence Validator runs after you. It cross-references every `[EVIDENCE: ...]` citation against the actual tool-call log."
- Added minimum citation requirement: "You MUST produce at least 3 `[EVIDENCE: ...]` citations"
- Added: "If you called tools but didn't cite them, your investigation is useless — downstream agents cannot see your tool results, only your citations"
- Added RTT interpretation rule: "Normal Docker bridge RTT is <1ms. RTT >10ms is ABNORMAL. RTT of 2000ms is CATASTROPHIC — sufficient to explain all SIP/Diameter/HTTP timeouts. Do not dismiss elevated RTT as 'connectivity is healthy.'"

**2. Evidence Validator (`evidence_validator.py`) — detect zero-citation investigations:**
- New detection case: if `investigator_tool_calls > 0` but `investigator_citations == 0`, return `has_warnings` verdict with `low` confidence (was: `clean`, `medium`)
- Summary now includes: "WARNING: InvestigatorAgent made N tool calls but produced ZERO [EVIDENCE: ...] citations. The investigation narrative is unverifiable."
- Summary line now shows "Investigator: N citations from M tool calls" for visibility
- Unit tested all three scenarios: zero calls → severe/none; calls but no citations → has_warnings/low; calls with matched citations → clean/high
