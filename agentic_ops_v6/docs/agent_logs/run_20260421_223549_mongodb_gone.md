# Episode Report: MongoDB Gone

**Agent:** v6  
**Episode ID:** ep_20260421_223201_mongodb_gone  
**Date:** 2026-04-21T22:32:03.183919+00:00  
**Duration:** 225.7s  

---

## Scenario

**Category:** container  
**Blast radius:** global  
**Description:** Kill MongoDB — the 5G core subscriber data store. UDR loses its backend, new PDU sessions cannot be created, and subscriber queries fail. Existing sessions may survive briefly.

## Faults Injected

- **container_kill** on `mongo`

## Baseline (Pre-Fault)

Stack phase before injection: **ready**
All containers running at baseline.

## Fault Propagation Verification

**Verdict:** ✅ `confirmed`

- **Wait:** 0s
- **Actual elapsed:** 0.0s
- **Nodes with significant deltas:** 1
- **Nodes with any drift:** 2

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 0.96 (threshold: 0.70, trained on 211 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following metrics deviate from their learned-healthy baseline. Treat each as a semantic observation (meaning + numbers), not a number alone — the KB's interpretation is the authoritative reading.

- **`derived.pcscf_sip_error_ratio`** (P-CSCF SIP error response ratio) — current **1.00 ratio** vs learned baseline **0.00 ratio** (HIGH, spike)
    - **What it measures:** Proportion of SIP responses that are errors. Zero is the healthy
baseline; any sustained non-zero value means P-CSCF or something
downstream is rejecting requests.
    - **Spike means:** Errors flowing back — downstream CSCFs or HSS rejecting.
    - **Healthy typical range:** 0–0 ratio
    - **Healthy invariant:** Zero in healthy operation.

- **`normalized.upf.gtp_outdatapktn3upf_per_ue`** (GTP-U downlink rate per UE (N3)) — current **0.02 packets_per_second** vs learned baseline **3.34 packets_per_second** (MEDIUM, drop)
    - **What it measures:** Health of the downlink user-plane path UPF → gNB. Typically mirrors
uplink rate during calls/data; asymmetry indicates directional
faults (e.g., UPF receiving from internet but not forwarding).
    - **Drop means:** No traffic leaving UPF toward RAN.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE — constant regardless of UE pool size. Roughly symmetric with uplink during healthy calls.

- **`normalized.upf.gtp_indatapktn3upf_per_ue`** (GTP-U uplink rate per UE (N3)) — current **0.08 packets_per_second** vs learned baseline **3.42 packets_per_second** (MEDIUM, drop)
    - **What it measures:** Health of the uplink user-plane path gNB → UPF. Drops to near-zero
during RAN or N3 outage; stays nonzero during active calls or data
sessions. Decoupled from SIP signaling (signals data plane, not
control plane).
    - **Drop means:** Data plane dead on uplink — UPF receiving no packets from gNB.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE — constant regardless of UE pool size. Rises during active VoNR calls (~100 pps for G.711 voice) and data transfer.

- **`normalized.smf.bearers_per_ue`** (Active QoS bearers per UE) — current **2.00 count** vs learned baseline **2.61 count** (LOW, shift)
    - **What it measures:** Per-UE count of active QoS bearers. Baseline reflects default
bearers; increments during VoNR calls indicate dedicated voice
bearers being set up. Drop during an active call = dedicated
bearer torn down unexpectedly (voice will fail).
    - **Shift means:** Expected during VoNR calls (1 extra bearer per active call).
    - **Healthy typical range:** 2–3.5 count
    - **Healthy invariant:** At rest: equals configured default bearers (typically 2 per UE).
During active VoNR call: +1 per caller. The per-UE ratio is the
invariant; absolute count scales with UE pool.

- **`normalized.pcscf.dialogs_per_ue`** (Active SIP dialogs per registered UE at P-CSCF) — current **0.00 count** vs learned baseline **0.57 count** (LOW, drop)
    - **What it measures:** How many calls per user are currently in progress at the P-CSCF.
Going to zero from a non-zero baseline means calls have ended
(normal) OR call setup is failing system-wide (degradation).
Together with rcv_requests_* it discriminates the two.
    - **Drop means:** No active calls. Normal at rest; suspicious if prior state had calls AND INVITE rate is also zero.
    - **Healthy typical range:** 0–1 count
    - **Healthy invariant:** Per-UE — scale-independent. 0 at rest, ~1 per active VoNR call.

- **`derived.upf_activity_during_calls`** — current **1.00** vs learned baseline **0.47** (LOW, spike). *(No KB context available — interpret from the metric name.)*


## Event Aggregation (Phase 1)

No events fired during this episode. Either no metric KB triggers matched, or the episode encountered no meaningful state transitions.

## Correlation Analysis (Phase 2)

No events fired — correlation engine had nothing to work with.

## Network Analysis (Phase 3)

**Summary:** The root cause of the anomaly is the failure of the MongoDB container, which is a critical dependency for the Policy Control Function (PCF), leading to cascading failures in the IMS subsystem during VoNR call setup.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🔴 RED | The MongoDB container is down, which is a critical failure for dependent NFs. |
| **ran** | 🟢 GREEN | No evidence of RAN failure. UEs are registered with the AMF. |
| **core** | 🟡 YELLOW | The core network is partially impacted. The PCF is unable to function without its database, affecting policy decisions. |
| **ims** | 🔴 RED | IMS is non-functional. P-CSCF is reporting 100% SIP error ratio, and no calls are being established, likely due to the PCF failure. |

**INFRASTRUCTURE evidence:**
- get_network_status: mongo container has exited.
- get_network_topology: Multiple NFs show INACTIVE links to MongoDB.

**CORE evidence:**
- get_network_topology: PCF has an inactive link to MongoDB.
- get_flows_through_component: PCF is essential for PDU session and VoNR call setup.

**IMS evidence:**
- derived.pcscf_sip_error_ratio: 1.00
- normalized.pcscf.dialogs_per_ue: 0.00
- get_nf_metrics: pcscf shows high httpclient:connfail count.

**Ranked hypotheses:**

- **`h1`** (fit=0.90, nf=pcf, specificity=specific):
    - **Statement:** The MongoDB container has crashed, which caused the PCF to fail. The P-CSCF's attempts to contact the PCF for policy authorization (Rx interface) are failing, causing it to reject SIP INVITEs and preventing VoNR call setup.
    - **Supporting events:** `derived.pcscf_sip_error_ratio`, `normalized.pcscf.dialogs_per_ue`, `normalized.upf.gtp_outdatapktn3upf_per_ue`, `normalized.upf.gtp_indatapktn3upf_per_ue`
    - **Falsification probes:**
        - Check PCF logs for errors related to MongoDB connectivity.
        - Restart the MongoDB container and observe if the SIP error ratio at the P-CSCF returns to normal.
        - Check P-CSCF logs for explicit error messages pointing to a failure in communication with the PCF.
- **`h2`** (fit=0.60, nf=pcscf, specificity=moderate):
    - **Statement:** The P-CSCF has an internal fault or misconfiguration that prevents it from communicating with the PCF, leading to SIP errors. The high 'httpclient:connfail' count at the P-CSCF suggests a client-side issue.
    - **Supporting events:** `derived.pcscf_sip_error_ratio`
    - **Falsification probes:**
        - Check the P-CSCF configuration for the PCF endpoint.
        - Inspect PCF's metrics/logs to see if it is receiving any requests from the P-CSCF.
        - Attempt to query the PCF from a different client to verify its responsiveness.
- **`h3`** (fit=0.20, nf=upf, specificity=moderate):
    - **Statement:** The UPF is experiencing a fault or a connectivity issue on the N3 interface, causing a complete halt of user plane traffic. This data plane failure is preventing media from flowing for VoNR calls.
    - **Supporting events:** `normalized.upf.gtp_outdatapktn3upf_per_ue`, `normalized.upf.gtp_indatapktn3upf_per_ue`
    - **Falsification probes:**
        - Create a PDU session for data (not VoNR) and test for internet connectivity.
        - Use 'measure_rtt' to check connectivity between the gNB and UPF.
        - Examine UPF logs for any errors related to packet forwarding or PFCP session handling.


## Falsification Plans (Phase 4)

*No output produced.*

## Parallel Investigators (Phase 5)

**3 sub-Investigator verdict(s):** **3 INCONCLUSIVE**

### `h1` — ❓ **INCONCLUSIVE**

**Hypothesis:** The MongoDB container has crashed, which caused the PCF to fail. The P-CSCF's attempts to contact the PCF for policy authorization (Rx interface) are failing, causing it to reject SIP INVITEs and preventing VoNR call setup.

**Reasoning:** No falsification plan was generated for this hypothesis.

### `h2` — ❓ **INCONCLUSIVE**

**Hypothesis:** The P-CSCF has an internal fault or misconfiguration that prevents it from communicating with the PCF, leading to SIP errors. The high 'httpclient:connfail' count at the P-CSCF suggests a client-side issue.

**Reasoning:** No falsification plan was generated for this hypothesis.

### `h3` — ❓ **INCONCLUSIVE**

**Hypothesis:** The UPF is experiencing a fault or a connectivity issue on the N3 interface, causing a complete halt of user plane traffic. This data plane failure is preventing media from flowing for VoNR calls.

**Reasoning:** No falsification plan was generated for this hypothesis.


## Evidence Validation (Phase 6)

**Overall verdict:** severe
**Overall confidence:** none

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 0 | 0/0 | severe | none |
|  |  |  |  | *ZERO tool calls — all citations fabricated* |
| `InvestigatorAgent_h2` | 0 | 0/0 | severe | none |
|  |  |  |  | *ZERO tool calls — all citations fabricated* |
| `InvestigatorAgent_h3` | 0 | 0/0 | severe | none |
|  |  |  |  | *ZERO tool calls — all citations fabricated* |


## Ground Truth

**Failure domain:** data_layer  
**Protocol impact:** multiple  
**Affected components:** mongo  
**Severity:** degraded

## Agent Diagnosis

**Model:** v6-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 91.3s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: The likely root cause is a failure of the MongoDB container, a critical dependency for the Policy Control Function (PCF), which resulted in a complete outage of the VoNR service in the IMS subsystem.
> - **timeline**:
>     1. The SIP error ratio at the P-CSCF (`derived.pcscf_sip_error_ratio`) rises to 100%.
>     2. Simultaneously, user plane traffic on the UPF's N3 interface (`normalized.upf.gtp_outdatapktn3upf_per_ue`, `normalized.upf.gtp_indatapktn3upf_per_ue`) drops to zero.
>     3. The number of active SIP dialogs at the P-CSCF (`normalized.pcscf.dialogs_per_ue`) also drops to zero, indicating no successful calls are being established.
> - **root_cause**: The most likely but unconfirmed root cause is the `pcf`'s backend database (MongoDB). The `pcf` itself is non-functional due to this dependency failure.
> - **affected_components**:
>     - `mongodb`: Root Cause (Suspected)
>     - `pcf`: Secondary (Impacted by dependency failure)
>     - `pcscf`: Symptomatic (Unable to get policy, rejecting calls)
>     - `upf`: Symptomatic (No user plane established for calls)
> - **recommendation**: Manually investigate the highest-ranked hypothesis (`h1`) by checking the health of the PCF and its dependencies. Specifically, an operator should:
>     1.  Verify the running state and health of the MongoDB container.
>     2.  Inspect PCF logs for any errors related to database connectivity.
>     3.  Inspect P-CSCF logs for specific errors indicating a failure to communicate with the PCF.
> - **confidence**: low
> - **explanation**: The Network Analyst's top-ranked hypothesis (`h1`) posits that the MongoDB container crashed, causing the PCF to become unresponsive. This prevents the P-CSCF from acquiring policy decisions for VoNR calls, forcing it to reject all incoming call attempts and leading to a 100% SIP error rate. This theory aligns perfectly with the observed symptoms. However, confidence in this diagnosis is **low** because the automated Investigator agents failed to execute any verification steps. The Evidence Validator issued a `severe` warning, noting that "ZERO tool calls" were made. Therefore, while the MongoDB failure is the most plausible explanation, it requires immediate manual verification.

### Scoring Breakdown

**Overall score: 100%**

**Scorer assessment:** The agent provided an excellent diagnosis, correctly identifying the root cause, affected component, severity, and fault type, with well-calibrated confidence and accurate layer attribution.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | Yes | The simulated failure was the killing of the MongoDB container. The agent's final diagnosis correctly identifies 'failure of the MongoDB container' and 'mongodb' as the root cause, which is semantically equivalent to the simulated failure mode. |
| Component overlap | 100% | The agent correctly identifies 'mongodb' as the 'Root Cause (Suspected)' in its `affected_components` list, matching the primary affected component in the simulated failure. |
| Severity correct | Yes | The simulated failure resulted in 'Component completely unreachable (down/not responding)', implying a complete outage. The agent's summary states 'resulted in a complete outage of the VoNR service', which accurately reflects the severity. |
| Fault type identified | Yes | The simulated failure mode was 'Component completely unreachable (down/not responding)'. The agent's diagnosis refers to 'failure of the MongoDB container' and 'MongoDB container crashed', which correctly identifies the observable fault type as a component failure/unreachability. |
| Layer accuracy | Yes | The ground truth states 'mongo' belongs to the 'infrastructure' layer. The agent's network analysis correctly rates the 'infrastructure' layer as 'red' with evidence 'mongo container has exited'. |
| Confidence calibrated | Yes | The agent correctly identifies the root cause but explicitly states 'low' confidence due to the lack of automated verification steps ('ZERO tool calls'). This demonstrates appropriate calibration, as it acknowledges the correctness of the hypothesis while highlighting the need for manual confirmation. |

**Ranking position:** #1 — The agent's final diagnosis presents a single, coherent root cause in its `causes` block, which is correct. Therefore, the correct cause is at position 1.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 37,546 |
| Output tokens | 1,702 |
| Thinking tokens | 7,186 |
| **Total tokens** | **46,434** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| EventAggregator | 0 | 0 | 0 |
| CorrelationAnalyzer | 0 | 0 | 0 |
| NetworkAnalystAgent | 36,102 | 4 | 3 |
| InstructionGeneratorAgent | 5,763 | 0 | 1 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 4,569 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 225.7s

---

## Post-Run Analysis — Gemini 2.5 Flash + `output_schema` Reliability Limit

### What happened

NA produced a strong Phase-3 report with the correct causal chain: h1 at fit=0.9 named `pcf` as primary suspect with `mongo` as the underlying cause, h2/h3 ranked appropriately. Everything upstream of Phase 4 worked.

**Then the InstructionGenerator produced no output.** Phase-4 section reads *"No output produced."* The orchestrator short-circuited Phase 5, spawning three sub-Investigators that each returned INCONCLUSIVE with reasoning *"No falsification plan was generated for this hypothesis."* Each Investigator ran zero tool calls. The Evidence Validator flagged all three as `severe` with *"ZERO tool calls — all citations fabricated."*

Synthesis still produced a reasonable diagnosis by falling back to NA's ranked hypotheses directly. The agent got the right answer despite the IG failure, by relying on NA alone.

### Diagnostic signature of the IG failure

The IG's phase breakdown shows the telltale pattern:

| Metric | This run | Prior-break (22:29) | Healthy runs |
|---|---|---|---|
| IG tokens total | 5,763 | 9,873 | 13,000 – 45,000 |
| IG tool calls | 0 | 0 | 1 – 3 |
| IG LLM calls | 1 | 1 | 2 – 4 |
| FalsificationPlanSet emitted | ✗ | ✗ | ✓ |

Single LLM call, zero tool calls, no parseable structured output, terminates early. This is the **ADK thinking-mode + `output_schema` structural failure** documented in earlier v6 work: the model spends its generation budget on thinking tokens and never commits to a valid Pydantic output.

### Root cause

The IG was the only agent in the v6 pipeline still running on `gemini-2.5-flash`:

| Agent | Model | Output schema | Recurring empty-output failures? |
|---|---|---|---|
| NetworkAnalyst | gemini-2.5-pro | `NetworkAnalystReport` | No (one transient flake) |
| **InstructionGenerator** | **gemini-2.5-flash** | **`FalsificationPlanSet`** | **Yes (twice in this session)** |
| Investigator (x N) | gemini-2.5-pro | `InvestigatorVerdict` | No |
| Synthesis | gemini-2.5-pro | (plain markdown) | No |

Flash + `output_schema` is structurally less reliable than Pro + `output_schema` on prompts past a modest length. That's why NA, Investigator, and Synthesis were already on Pro. IG was the last holdout, and its prompt had accumulated 9 numbered rules + a flow-tools section + a tool catalog + a format example — each rule justified individually by failure modes seen in earlier runs, but the aggregate pushed Flash past its reliability threshold.

### Fix applied

One-line change in `agentic_ops_v6/subagents/instruction_generator.py`:

```python
model="gemini-2.5-pro",  # was: gemini-2.5-flash
```

Rationale: every other LlmAgent in this pipeline already uses Pro for this exact reason. IG being the odd one out was a historical accident, not a deliberate choice. Cost impact is modest — IG is one of the smaller phases — and the reliability gain is decisive.

The IG's accumulated rules stay. Each describes a real reasoning mistake we've observed and want to prevent. Pro tolerates the complexity; Flash does not.

### Lesson for future prompt edits

**`output_schema` on `gemini-2.5-flash` has a prompt-complexity ceiling that's easy to cross unintentionally.** Each individual rule we add to a Flash-backed agent is fine in isolation; the aggregate silently degrades reliability until the model simply fails to produce a parseable output. The failure is not in the prompt's wording — it's in the combination of prompt length, output-schema strictness, and the model's reasoning budget.

Rules of thumb going forward:
- **Any LlmAgent in this pipeline with `output_schema`** should default to `gemini-2.5-pro`, not Flash. Reserve Flash for plain-text agents or simple structured outputs.
- **When adding a rule to an agent prompt**, check that agent's model. If Flash, either justify keeping Flash (short prompt, simple schema) or upgrade to Pro as part of the same change.
- **The IG-tokens / tool-calls / LLM-calls pattern (1, 0, 1) with zero output is diagnostic** for this failure mode. When seen in a future run, check the model before rewriting prompts.

### What's NOT changed

- All IG rules (#1–#9, including the activity-vs-drops discriminator from this session) remain.
- Investigator prompt edits (evidence weighting, tightened negative-result rule) remain — Investigator was already on Pro.
- Scorer edits (final-diagnosis-pinned, NA scoped to `layer_accuracy`) remain.
- NA prompt unchanged.

### Relation to prior failure modes

Combined with the earlier IG break (22:29) and the earlier NA flakiness in run `run_20260421_222234_mongodb_gone.md` (where NA produced no output with the same 1-LLM-call signature on Pro), the broader lesson is that `output_schema` is the most structurally fragile part of the ADK-based pipeline. Pro greatly reduces but does not eliminate this risk. If Pro-based agents flake on future runs, the next-level mitigation is an orchestrator-side retry on empty structured output (one retry, ~15 lines in `_run_phase`). Not implemented yet; deferred until Pro is observed to flake at production rates.
