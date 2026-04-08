# Episode Report: P-CSCF Latency

**Agent:** v5  
**Episode ID:** ep_20260408_014636_p_cscf_latency  
**Date:** 2026-04-08T01:46:37.626120+00:00  
**Duration:** 656.1s  

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
| pcscf | core:rcv_requests_options | 7.0 | 79.0 | 72.0 |
| pcscf | script:register_time | 755.0 | 158681.0 | 157926.0 |
| pcscf | httpclient:connfail | 8.0 | 90.0 | 82.0 |
| pcscf | core:rcv_requests_register | 4.0 | 92.0 | 88.0 |
| pcscf | script:register_success | 2.0 | 13.0 | 11.0 |
| pcscf | sl:1xx_replies | 4.0 | 56.0 | 52.0 |
| pcscf | sl:4xx_replies | 0.0 | 10.0 | 10.0 |
| pcscf | core:rcv_requests_invite | 0.0 | 30.0 | 30.0 |
| scscf | ims_registrar_scscf:sar_replies_received | 2.0 | 13.0 | 11.0 |
| scscf | cdp:replies_received | 4.0 | 26.0 | 22.0 |
| scscf | ims_registrar_scscf:sar_replies_response_time | 213.0 | 1486.0 | 1273.0 |
| scscf | cdp:replies_response_time | 468.0 | 3078.0 | 2610.0 |
| scscf | core:rcv_requests_register | 4.0 | 26.0 | 22.0 |
| scscf | ims_auth:mar_replies_received | 2.0 | 13.0 | 11.0 |
| scscf | ims_auth:mar_replies_response_time | 255.0 | 1592.0 | 1337.0 |
| scscf | ims_usrloc_scscf:impu_collisions | 0.0 | 1.0 | 1.0 |
| scscf | ims_usrloc_scscf:contact_collisions | 0.0 | 1.0 | 1.0 |
| scscf | ims_usrloc_scscf:subscription_collisions | 0.0 | 1.0 | 1.0 |
| scscf | ims_registrar_scscf:accepted_regs | 2.0 | 13.0 | 11.0 |
| smf | bearers_active | 4.0 | 5.0 | 1.0 |

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 1.00 (threshold: 0.70, trained on 50 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following specific metrics were flagged as the top contributors to the anomaly. These MUST be reflected in your layer ratings:

| Component | Metric | Current | Learned Normal | Severity |
|-----------|--------|---------|---------------|----------|
| pcscf | core:rcv_requests_invite_rate | 888.06 | 0.04 | HIGH |
| icscf | core:rcv_requests_register_rate | 1332.09 | 0.08 | HIGH |
| pcscf | httpclient:connfail_rate | 888.06 | 0.27 | HIGH |
| pcscf | sl:4xx_replies_rate | 444.03 | 0.00 | HIGH |
| scscf | ims_registrar_scscf:accepted_regs_rate | 444.03 | 0.04 | HIGH |
| pcscf | sl:1xx_replies_rate | 888.06 | 0.12 | HIGH |
| scscf | cdp:replies_received_rate | 444.03 | 0.08 | HIGH |
| pcscf | core:rcv_requests_register_rate | 444.03 | 0.08 | HIGH |
| scscf | core:rcv_requests_register_rate | 444.03 | 0.08 | HIGH |
| upf | fivegs_ep_n3_gtp_indatapktn3upf_rate | 6216.41 | 5.04 | HIGH |

## Network Analysis (Phase 1)

**Summary:** The network is recovering from a massive IMS signaling storm that led to service degradation and errors, primarily centered around the P-CSCF and HSS.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟡 YELLOW | HSS (pyhss) appears to have been unresponsive, causing downstream timeouts. |
| **ran** | 🟢 GREEN | RAN appears stable, with 1 gNB and 2 UEs connected. |
| **core** | 🟢 GREEN | 5G Core components are stable; data plane is idle as no call is active. |
| **ims** | 🔴 RED | IMS layer experienced a major signaling storm, leading to cascading failures. |

**INFRASTRUCTURE evidence:**
- I-CSCF experienced Diameter timeouts when querying the HSS (pyhss): cdp:timeout=1, ims_icscf:uar_timeouts=1. This indicates the HSS was unresponsive.

**IMS evidence:**
- P-CSCF was flooded with an extremely high rate of SIP requests (anomaly screener: core:rcv_requests_invite_rate=888.06).
- P-CSCF experienced a high rate of connection failures (anomaly screener: httpclient:connfail_rate=888.06).
- P-CSCF sent a high rate of client errors back to UEs (anomaly screener: sl:4xx_replies_rate=444.03).
- I-CSCF also saw an extremely high registration rate (anomaly screener: core:rcv_requests_register_rate=1332.09).

**Suspect components:**

- **pcscf** (high): The anomaly screener identified P-CSCF as the epicenter of the disturbance, with the highest-severity metric deviations. It was the entry point for a flood of SIP requests and exhibited a high rate of connection failures and 4xx client errors.
- **icscf** (medium): Experienced timeouts when trying to query the HSS, indicating it was a victim of both the initial traffic flood and the unresponsiveness of its HSS dependency. The metric 'ims_icscf:uar_timeouts' was 1, where 0 is expected.
- **pyhss** (medium): While it reports no internal errors, its primary client (I-CSCF) reported Diameter timeouts. This makes the HSS a strong suspect for being overloaded or unresponsive during the signaling storm.

**Investigation hint:** The immediate anomaly has passed, but the root cause appears to be a massive, correlated flood of SIP requests overwhelming the IMS core. Start by investigating the P-CSCF to identify the source of the traffic; check its logs around the time of the event for source IPs or misbehaving UEs. Concurrently, examine the HSS (pyhss) logs and system performance (CPU/memory) to understand why it became unresponsive to the I-CSCF's Diameter queries, as this was a key factor in the cascading failure.

**Tools called:** get_vonr_components, get_network_topology, get_network_status, get_nf_metrics, get_dp_quality_gauges, compare_to_baseline, check_stack_rules


## Pattern Match (Phase 2)

**❌ Match:** No matching signature found

- **Confidence:** low
- **Failure domain:** unknown
- **Baseline anomalies:** 2 metrics across 2 components


## Investigation Instruction (Phase 3)

> Anomalies detected in IMS (RED) and Infrastructure (YELLOW) layers. Suspect components: pcscf, icscf, pyhss. The network is recovering from a massive IMS signaling storm, but issues persist, notably `ims_icscf:uar_timeouts=1` indicating HSS unresponsiveness.
>
> Your ONLY job is to investigate the root cause of the HSS unresponsiveness and the prior SIP signaling storm.
>
> 1.  **HSS (pyhss):** The I-CSCF reported `ims_icscf:uar_timeouts=1` when querying the HSS.
>     *   First, check network reachability and latency between I-CSCF and HSS using `measure_rtt` to `pyhss`.
>     *   Examine `pyhss` logs (using `get_nf_logs`) from the time of the event for errors, resource exhaustion, or other issues.
>     *   Check `pyhss` system performance (CPU/memory via `get_nf_metrics` if available).
>
> 2.  **P-CSCF:** The epicenter of the signaling storm. While the storm has subsided, previous `httpclient:connfail=100` and `sl:4xx_replies=10` indicate past issues.
>     *   Examine `pcscf` logs (using `get_nf_logs`) from the time of the event to identify the source of the excessive SIP traffic (e.g., misbehaving UEs, specific IPs).
>
> Do NOT investigate RAN or Core layers as they are GREEN. Focus on Diameter and SIP signaling plane issues.

## Ground Truth

**Failure domain:** ims_signaling  
**Protocol impact:** SIP  
**Affected components:** pcscf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v5-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 145.6s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: The P-CSCF is stuck in an internal error state, causing a continuous loop of registration failures with the Service Communication Proxy (SCP), which in turn creates a massive signaling storm that overloads other IMS components.
> - **timeline**:
>     1.  The `pcscf` enters an error state, causing it to fail registration with the SCP, noted as `P-CSCF NF failed to register at SCP with code=28`.
>     2.  The `pcscf` begins a high-frequency retry loop, flooding the IMS core with registration requests. This is the "signaling storm" identified by the Network Analyst.
>     3.  The `icscf` is inundated with this traffic from the `pcscf`, becoming overloaded.
>     4.  While processing a legitimate UE request, the overloaded `icscf` sends a Diameter query to the HSS (`pyhss`). Due to its high load, the `icscf` fails to process the HSS's response in time, resulting in a client-side timeout (`ims_icscf:uar_timeouts=1`).
>     5.  This makes the HSS appear unresponsive, but the HSS itself is healthy; the timeout is a symptom of the overload at the `icscf`.
> - **root_cause**: The root cause is an internal registration logic failure within the P-CSCF. This failure triggers a retry storm that overwhelms downstream components. The HSS unresponsiveness (`ims_icscf:uar_timeouts=1`) is a secondary symptom of the I-CSCF being too overloaded by the storm to process a timely response from the HSS.
> - **affected_components**:
>     - `pcscf`: The source of the failure.
>     - `icscf`: A primary victim of the signaling storm, leading to cascading timeouts.
>     - `pyhss`: Incorrectly implicated due to client-side timeouts at the `icscf`.
> - **recommendation**: The investigation should focus exclusively on the P-CSCF. Examine the P-CSCF's configuration and detailed logs related to its NRF/SCP registration client to determine the cause of the `code=28` failure. It may also be useful to check the SCP's logs for corresponding error messages regarding the P-CSCF's registration attempts.
> - **confidence**: medium
> - **explanation**: The network incident was caused by an internal error within the P-CSCF, not the HSS. The P-CSCF is failing to register with the SCP and is caught in a high-frequency retry loop, creating a signaling storm. This storm overloaded the I-CSCF, which then timed out while waiting for a response from the HSS on an unrelated transaction. The key evidence is the P-CSCF log showing repeated registration failures, which explains the massive signaling volume seen across the IMS layer and clarifies why the otherwise healthy HSS appeared unresponsive.

### Scoring Breakdown

**Overall score: 40%**

**Scorer assessment:** The agent correctly identified the primary affected component and the severity of the impact, but completely missed the actual root cause (network latency) and the underlying fault type, instead fabricating an internal software error. Its confidence was poorly calibrated given the incorrect diagnosis.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | No | The simulated failure was 'P-CSCF Latency' (elevated network latency on P-CSCF interfaces). The agent diagnosed an 'internal registration logic failure within the P-CSCF' leading to a 'retry storm'. This is a fundamentally different root cause (software bug vs. network condition). |
| Component overlap | 100% | The agent correctly identified 'pcscf' as the source of the failure. It also listed cascading components ('icscf', 'pyhss') which is acceptable. |
| Severity correct | Yes | The simulated failure caused 'SIP REGISTER 408 Request Timeout' and 'IMS registration failures'. The agent described 'continuous loop of registration failures', 'massive signaling storm', and 'overloads other IMS components', which accurately reflects a severe functional degradation and service impact consistent with the timeouts and failures. |
| Fault type identified | No | The simulated fault type was 'Elevated network latency' (network degradation). The agent identified 'internal error state', 'registration logic failure', and 'signaling storm' as the fault types, not network degradation or latency. |
| Confidence calibrated | No | The agent stated 'medium' confidence, but its root cause diagnosis was incorrect. Medium confidence is not appropriate for a fundamentally wrong root cause. |

**Ranking:** The agent provided a single root cause explanation, which was incorrect.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 122,529 |
| Output tokens | 5,159 |
| Thinking tokens | 7,959 |
| **Total tokens** | **135,647** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| NetworkAnalystAgent | 41,656 | 9 | 3 |
| PatternMatcherAgent | 0 | 0 | 0 |
| InstructionGeneratorAgent | 6,287 | 0 | 1 |
| InvestigatorAgent | 79,198 | 5 | 6 |
| EvidenceValidatorAgent | 0 | 0 | 0 |
| SynthesisAgent | 8,506 | 0 | 1 |


## Resolution

**Heal method:** scheduled
**Recovery time:** 656.1s

## Post-Run Analysis

### Score: 40% — best run yet, but three pipeline issues remain

This is the strongest run so far. The anomaly screener works, the NetworkAnalyst correctly identified pcscf as the primary suspect for the first time, and the Investigator actually called tools and found real evidence. The score improved from 0-15% to 40% (100% component overlap). The remaining 60% was lost because the diagnosis said "internal software bug" instead of "network latency."

### What worked

**Anomaly screener (Phase 0):** Score 1.00, 10 HIGH flags, pcscf metrics dominating the top of the table. Working as designed.

**NetworkAnalyst (Phase 1):** Correctly named pcscf as PRIMARY suspect (high confidence) with icscf and pyhss as secondary. Line 107: "The anomaly screener identified P-CSCF as the epicenter of the disturbance." This is a direct result of the generalized ontology changes and the prompt guidance about screener flags indicating proximity to root cause.

**Investigator (Phase 4):** Called 5 tools and investigated. Found a real log entry in pcscf: `P-CSCF NF failed to register at SCP with code=28`. This is genuine evidence — the P-CSCF's NRF/SCP registration is failing because the 2000ms egress latency causes curl timeout (code=28). The Investigator correctly linked the log to pcscf as the source of the problem.

**Final diagnosis:** Named pcscf as the source of the failure (100% component overlap). Correctly identified icscf Diameter timeouts as cascading symptoms, not the root cause. Correctly exonerated pyhss ("incorrectly implicated due to client-side timeouts"). This causal reasoning is a major improvement.

### Issue 1: InstructionGenerator overrides NetworkAnalyst's suspect ranking

The NetworkAnalyst correctly ranked pcscf as PRIMARY suspect. But the InstructionGenerator (Phase 3) wrote:

> "Your ONLY job is to investigate the root cause of the **HSS unresponsiveness** and the prior SIP signaling storm."

It elevated `ims_icscf:uar_timeouts=1` into the primary investigation target, overriding the NetworkAnalyst's pcscf priority. The Investigator was then told to focus on HSS first (step 1) and pcscf second (step 2).

**Root cause:** The InstructionGenerator reads the raw NetworkAnalyst output and re-derives its own priority. It sees `cdp:timeout=1` as an ontology alarm condition and gives it weight regardless of what the NetworkAnalyst's suspect ranking says. The InstructionGenerator prompt needs to explicitly say: "Preserve the NetworkAnalyst's suspect ordering. The PRIMARY suspect is your primary investigation target."

### Issue 2: EvidenceValidator produced no output

`EvidenceValidatorAgent | 0 | 0 | 0` and `evidence_validation: None` in the episode JSON. The EvidenceValidator is a BaseAgent that should cross-check the Investigator's evidence citations against the actual tool call traces stored in `phase_traces_so_far`. It either:
- Didn't find the phase traces in state (the `_accumulate_phase_traces` function may not be running correctly)
- Threw an exception that was silently caught
- Ran but its output wasn't captured in the result dict

This needs debugging. The EvidenceValidator is critical — it's the safety net that downgrades confidence when the Investigator fabricates evidence. In this run, the Investigator's evidence was real (code=28 log entry exists), so the validator would have confirmed it. But in previous runs where the Investigator made 0 tool calls, the validator should have flagged the entire investigation as unreliable.

### Issue 3: Timing — agent sees "recovery" instead of active fault

The NetworkAnalyst said (line 85): "The network is **recovering** from a massive IMS signaling storm." This is because:

1. ObservationTrafficAgent generates traffic for 2 minutes, collecting 22 snapshots (with the fault active)
2. FaultPropagationVerifier runs for 30 seconds
3. ChallengerAgent invokes the v5 pipeline
4. Phase 0 (screener) scores the OBSERVATION snapshots — correctly sees the storm (score 1.00)
5. Phase 1 (NetworkAnalyst) calls `get_nf_metrics` LIVE — by this time, the ObservationTrafficAgent stopped generating traffic ~3 minutes ago

The NetworkAnalyst's live `get_nf_metrics` sees a calmer picture because the traffic generator stopped. The retransmission storm subsided because no new REGISTERs are being triggered. The screener saw the storm (from the observation snapshots) but the NetworkAnalyst's own live data shows "recovery."

**Fix needed:** The screener's anomaly report should include a note about the timeframe: "These anomalies were detected in metric snapshots collected during a 2-minute observation window that ended N seconds ago. Current live metrics may show recovery." OR the NetworkAnalyst should be instructed to trust the screener's findings over its own live snapshot when the screener reports high-severity anomalies.

### Issue 4: Investigator found the right evidence but drew the wrong conclusion

The Investigator found `P-CSCF NF failed to register at SCP with code=28` in the pcscf logs. This is a real finding — code=28 is a curl timeout error, caused by the 2000ms egress latency making the NRF/SCP HTTP registration request time out. But the Investigator concluded "internal registration logic failure" instead of recognizing it as a symptom of transport-layer latency.

If the Investigator had followed the Hierarchy of Truth and run `measure_rtt` FROM pcscf before examining application logs, it would have seen 2000ms RTT and correctly identified network latency as the root cause. The `code=28` log entry would then be understood as a CONSEQUENCE of the latency, not the cause itself.

**Fix needed:** The InstructionGenerator should always include "run measure_rtt FROM the primary suspect as the FIRST step" regardless of what the specific symptoms suggest. Transport-layer probing must come before log analysis per the Hierarchy of Truth.

### Fixes needed

| Problem | Fix location | What to do |
|---|---|---|
| InstructionGenerator overrides suspect ranking | `instruction_generator.md` prompt | Add: "Preserve the NetworkAnalyst's suspect ordering. PRIMARY suspect = primary investigation target. Do not re-derive priority from individual metrics." |
| EvidenceValidator not producing output | `evidence_validator.py` + orchestrator | Debug why evidence_validation is None — check phase_traces_so_far accumulation and exception handling |
| Agent sees "recovery" from stale live metrics | `network_analyst.md` prompt or Phase 0 | Tell NetworkAnalyst to trust screener findings over its own live snapshot when screener reports HIGH anomalies |
| Investigator skips measure_rtt | `instruction_generator.md` prompt | Always include "measure_rtt FROM primary suspect as FIRST step" in every investigation instruction |

### Fixes implemented

  1. InstructionGenerator prompt (instruction_generator.md)

  - Added "Suspect Ranking (MANDATORY)" section: must preserve NetworkAnalyst's suspect ordering, PRIMARY suspect = primary investigation target, do not re-derive priority from individual metrics
  - Added "Transport-Layer Probing First (MANDATORY)" section: every instruction must include measure_rtt FROM the primary suspect as the FIRST step
  - Added "Frame as hypotheses to test, not conclusions to verify"

  2. NetworkAnalyst prompt (network_analyst.md) — temporal reasoning rewrite

  - Replaced the old "start with 60s window, widen to 120s, 300s" strategy
  - New approach: agents receive {event_lookback_seconds} which is computed as observation_window_duration + seconds_since_observation — the exact window that covers the event period
  - Added "trust the screener over live metrics" principle: if screener reports HIGH anomalies but live data looks calm, the event has passed — don't dismiss the screener's findings
  - All Prometheus queries now use {event_lookback_seconds} as the starting window instead of 60s

  3. Observation timing plumbed end-to-end

  - ObservationTrafficAgent now records observation_window_start, observation_window_end, observation_window_duration in session state
  - ChallengerAgent computes seconds_since_observation and passes both to investigate()
  - investigate() computes event_lookback_seconds = duration + seconds_since and puts it in state
  - The NetworkAnalyst prompt renders {event_lookback_seconds}, {observation_window_duration}, {seconds_since_observation} so the agent knows exactly when the event occurred and uses the right Prometheus query window.

  4. Fixed evidence validator
  Three fixes:

  I. Root cause: Challenger wasn't passing evidence_validation through

  Added "_evidence_validation" to the dict returned by _run_adk_agent() and "evidence_validation" to the challenge_result dict. The validator was running and producing correct output all along — it was just
  being dropped at the challenger layer.

  II. Added debug logging to the EvidenceValidator

  Now logs the number of phase traces it receives, each phase's name and tool call count, and warns if no traces are available. This will help diagnose any future issues.

  III. Added "Evidence Validation (Phase 5)" section to episode markdown report

  Shows: verdict, investigator confidence, citations matched/total, zero-calls warning, and the full summary text. This will be visible in every future episode report.