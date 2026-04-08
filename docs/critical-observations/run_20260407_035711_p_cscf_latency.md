# Episode Report: P-CSCF Latency

**Agent:** v5  
**Episode ID:** ep_20260407_034511_p_cscf_latency  
**Date:** 2026-04-07T03:45:12.490188+00:00  
**Duration:** 718.1s  

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
- **Nodes with significant deltas:** 4
- **Nodes with any drift:** 5

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

### Metrics Changes

| Node | Metric | Baseline | Current | Delta |
|------|--------|----------|---------|-------|
| icscf | core:rcv_requests_register | 281.0 | 347.0 | 66.0 |
| pcscf | sl:1xx_replies | 55.0 | 98.0 | 43.0 |
| pcscf | httpclient:connfail | 238.0 | 302.0 | 64.0 |
| pcscf | script:register_time | 128707.0 | 285537.0 | 156830.0 |
| pcscf | core:rcv_requests_register | 76.0 | 164.0 | 88.0 |
| pcscf | core:rcv_requests_options | 224.0 | 281.0 | 57.0 |
| pcscf | script:register_success | 11.0 | 22.0 | 11.0 |
| pcscf | sl:4xx_replies | 12.0 | 19.0 | 7.0 |
| pcscf | core:rcv_requests_invite | 33.0 | 54.0 | 21.0 |
| scscf | ims_registrar_scscf:sar_replies_received | 11.0 | 22.0 | 11.0 |
| scscf | cdp:replies_received | 22.0 | 44.0 | 22.0 |
| scscf | ims_auth:mar_replies_received | 11.0 | 22.0 | 11.0 |
| scscf | ims_registrar_scscf:sar_replies_response_time | 885.0 | 1931.0 | 1046.0 |
| scscf | core:rcv_requests_register | 22.0 | 44.0 | 22.0 |
| scscf | ims_auth:mar_replies_response_time | 952.0 | 2100.0 | 1148.0 |
| scscf | ims_registrar_scscf:accepted_regs | 11.0 | 22.0 | 11.0 |
| scscf | cdp:replies_response_time | 1837.0 | 4031.0 | 2194.0 |
| smf | bearers_active | 4.0 | 7.0 | 3.0 |

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 0.99 (threshold: 0.70, trained on 50 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following specific metrics were flagged as the top contributors to the anomaly. These MUST be reflected in your layer ratings:

| Component | Metric | Current | Learned Normal | Severity |
|-----------|--------|---------|---------------|----------|
| pcscf | core:rcv_requests_register_rate | 3761.23 | 0.08 | HIGH |
| icscf | core:rcv_requests_register_rate | 2149.27 | 0.08 | HIGH |
| pcscf | sl:1xx_replies_rate | 1074.64 | 0.12 | HIGH |
| icscf | cdp:replies_received_rate | 537.32 | 0.06 | HIGH |
| pcscf | httpclient:connfail_rate | 537.32 | 0.27 | HIGH |
| scscf | cdp:replies_received_rate | 537.32 | 0.08 | HIGH |
| scscf | core:rcv_requests_register_rate | 537.32 | 0.08 | HIGH |
| upf | fivegs_ep_n3_gtp_indatapktn3upf_rate | 3223.91 | 5.04 | HIGH |
| upf | fivegs_ep_n3_gtp_outdatapktn3upf_rate | 537.32 | 4.92 | HIGH |
| icscf | cdp:timeout | 1.00 | 0.00 | HIGH |

## Network Analysis (Phase 1)

**Summary:** The network is experiencing a critical IMS failure preventing user registration, caused by the HSS (pyhss) being unresponsive to I-CSCF's Diameter authentication queries.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | All infrastructure components (mongo, mysql, dns) are running and connected. |
| **ran** | 🟢 GREEN | gNB is connected and both UEs are attached at the 5G level. |
| **core** | 🟢 GREEN | 5G core is stable with active PDU sessions. Data plane is idle as expected. |
| **ims** | 🔴 RED | IMS registration is failing due to Diameter timeouts between I-CSCF and HSS. |

**IMS evidence:**
- icscf 'cdp:timeout'=1.0 from get_nf_metrics (expected: 0.0)
- icscf 'ims_icscf:uar_timeouts'=1.0 from get_nf_metrics (expected: 0.0)
- AnomalyScreener flagged 'icscf:core:rcv_requests_register_rate' and 'pcscf:core:rcv_requests_register_rate' as HIGH, indicating a registration storm.

**Suspect components:**

- **pyhss** (high): The I-CSCF is reporting a Diameter timeout ('cdp:timeout' = 1.0) and a User-Authorization-Request timeout ('ims_icscf:uar_timeouts' = 1.0), which are queries sent to the HSS (pyhss). This indicates pyhss is not responding, causing IMS registration failures.
- **icscf** (medium): It is the component directly reporting the timeouts. While it is likely the victim of an unresponsive HSS, its logs and internal state would provide the most direct evidence of the failure.

**Investigation hint:** The primary suspect is the HSS (pyhss). Although the container is running, it appears to be unresponsive to Diameter queries from the I-CSCF, leading to IMS registration timeouts and a subsequent retry storm from UEs. The Investigator should first check the logs and internal process status of the 'pyhss' container to understand why it is not processing Diameter requests. Then, examine the 'icscf' logs for detailed error messages regarding the Cx interface connection to 'pyhss'.

**Tools called:** get_vonr_components, get_network_topology, get_network_status, get_nf_metrics, get_dp_quality_gauges, compare_to_baseline, check_stack_rules


## Pattern Match (Phase 2)

**❌ Match:** No matching signature found

- **Confidence:** low
- **Failure domain:** unknown
- **Baseline anomalies:** 2 metrics across 2 components


## Investigation Instruction (Phase 3)

> INVESTIGATE: Critical IMS failure due to unresponsive HSS. The IMS layer is RED because I-CSCF is reporting Diameter timeouts (`icscf 'cdp:timeout'=1.0` and `ims_icscf:uar_timeouts'=1.0`), indicating `pyhss` is not responding to authentication queries. This is causing an IMS registration retry storm.
>
> RAN, Core, and Infrastructure layers are GREEN — do not investigate them.
>
> **Primary Suspect:** `pyhss` (high confidence).
> **Secondary Suspect:** `icscf` (as the reporting component).
>
> Your ONLY job is to determine why `pyhss` is unresponsive to Diameter requests from `icscf`.
> 1.  **Check `pyhss`:** Although `pyhss` container is running, use `get_container_logs pyhss` to examine its application logs for errors, crashes, or any indications of unresponsiveness or processing failures related to Diameter requests. Use `get_process_status pyhss` to verify its internal Diameter application process is active and healthy.
> 2.  **Check `icscf`:** Use `get_container_logs icscf` to find detailed error messages regarding the Cx interface connection and Diameter failures when attempting to query `pyhss`.

## Ground Truth

**Failure domain:** ims_signaling  
**Protocol impact:** SIP  
**Affected components:** pcscf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v5-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 313.2s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ```json
> {
>   "causes": [
>     {
>       "summary": "The HSS (pyhss) application is not processing Diameter requests, causing all IMS user registrations to fail due to authentication timeouts.",
>       "timeline": [
>         {
>           "timestamp": "T-300s",
>           "description": "The Diameter server process within the 'pyhss' container is non-functional or not running."
>         },
>         {
>           "timestamp": "T-60s",
>           "description": "UEs begin attempting IMS registration. The I-CSCF forwards a Diameter User-Authorization-Request (UAR) to 'pyhss' to authenticate the user."
>         },
>         {
>           "timestamp": "T-5s",
>           "description": "'pyhss' fails to respond to the UAR. The I-CSCF's request times out, evidenced by the 'ims_icscf:uar_timeouts' metric incrementing to 1.0."
>         },
>         {
>           "timestamp": "T-0s",
>           "description": "IMS registration fails. UEs and P-CSCF begin to aggressively retry, creating a registration storm."
>         }
>       ],
>       "root_cause": "The core Diameter server application inside the 'pyhss' container is not running. While the container itself is active and running a web server, its essential HSS Diameter service is non-functional. This prevents it from responding to authentication queries (UAR) from the I-CSCF, which is the direct cause of the system-wide IMS registration failure.",
>       "affected_components": [
>         {
>           "name": "pyhss",
>           "role": "Root Cause"
>         },
>         {
>           "name": "icscf",
>           "role": "Symptomatic (reporting timeouts)"
>         },
>         {
>           "name": "pcscf",
>           "role": "Symptomatic (experiencing registration failures)"
>         }
>       ],
>       "recommendation": "Investigate the 'pyhss' container to determine why the core Diameter application is not running. Check the container's full startup logs and internal process list to confirm the absence of the Diameter service and identify any errors that may have prevented it from starting.",
>       "confidence": "high",
>       "explanation": "A critical IMS failure is preventing all user registrations. The root cause is that the Diameter server application within the HSS (pyhss) container is not running. Although the container is active, verified by a running web server, it is not processing any Diameter authentication requests. This has been confirmed by the absence of Diameter-related logs in 'pyhss' and corresponding timeouts on the I-CSCF. Network connectivity between the components is healthy, isolating the fault to the 'pyhss' application itself."
>     }
>   ]
> }
> ```

### Scoring Breakdown

**Overall score: 15%**

**Scorer assessment:** The agent correctly identified the severity of the impact but completely missed the root cause, affected component, and fault type, demonstrating poor calibration of confidence.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | No | The simulated failure was P-CSCF latency, causing SIP REGISTER timeouts. The agent incorrectly identified the root cause as the HSS (pyhss) application not processing Diameter requests. |
| Component overlap | 0% | The primary affected component in the simulated failure was P-CSCF. The agent identified 'pyhss' (HSS) as the root cause component. While P-CSCF is listed as 'symptomatic', it is not identified as the primary affected component or the source of the issue. |
| Severity correct | Yes | The simulated failure led to IMS registration failures. The agent correctly identified the severity as a 'critical IMS failure preventing all user registrations', which matches the expected impact. |
| Fault type identified | No | The simulated failure was network latency. The agent identified an 'application not running/non-functional' fault type for the HSS, which is incorrect. |
| Confidence calibrated | No | The agent stated 'high' confidence for a diagnosis that is incorrect in its root cause, primary affected component, and fault type. |

**Ranking:** The correct cause (P-CSCF latency) was not listed in the agent's diagnosis.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 169,595 |
| Output tokens | 3,584 |
| Thinking tokens | 13,376 |
| **Total tokens** | **186,555** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| NetworkAnalystAgent | 43,670 | 10 | 4 |
| PatternMatcherAgent | 0 | 0 | 0 |
| InstructionGeneratorAgent | 5,885 | 0 | 1 |
| InvestigatorAgent | 127,672 | 9 | 10 |
| EvidenceValidatorAgent | 0 | 0 | 0 |
| SynthesisAgent | 9,328 | 0 | 1 |


## Resolution

**Heal method:** scheduled
**Recovery time:** 718.1s

## Post-Run Analysis

### Score: 15% — anomaly screener works, but ontology leads agent to the wrong causal chain

This is the second consecutive run where the anomaly screener worked correctly (score 0.99, 10 HIGH flags with pcscf as the clear epicenter). The agent failure is no longer a detection problem — it's a **reasoning problem** rooted in the ontology's causal chains.

### Anomaly Screener: Working as designed

Phase 0 produced exactly the right output:
- `pcscf.core:rcv_requests_register_rate: 3761/s` (normal: 0.08) — **pcscf is the #1 anomaly**
- `icscf.core:rcv_requests_register_rate: 2149/s` — downstream cascade
- `icscf.cdp:timeout: 1.0` (normal: 0.0) — Diameter timeout appearing at I-CSCF

The NetworkAnalyst even acknowledged the screener's flags in its evidence section: "AnomalyScreener flagged `icscf:core:rcv_requests_register_rate` and `pcscf:core:rcv_requests_register_rate` as HIGH."

### Root cause of failure: Ontology's causal chains misguide the agent

The NetworkAnalyst sees two findings:
1. Screener flag: `pcscf.register_rate` at 3761/s (pcscf is the anomaly epicenter)
2. Ontology metric: `icscf.cdp:timeout = 1` (known alarm condition in baselines.yaml)

It then consults the ontology via `compare_to_baseline` and `check_stack_rules`. The ontology returns a match against the **`hss_unreachable` causal chain**, which lists `cdp:timeout > 0` at I-CSCF as an immediate symptom. The agent follows this chain and concludes "HSS is unresponsive."

Meanwhile, the **`sip_edge_latency` causal chain** — which is the correct one — has three problems that prevent it from being matched:

**Flaw 1: Missing cascading symptom.** The `sip_edge_latency` chain's cascading effects only mention SIP transaction timeouts and UE de-registration. It does NOT mention that `icscf.cdp:timeout` will increment as a cascading effect of P-CSCF latency. In reality, P-CSCF egress delay slows the entire SIP REGISTER chain. The I-CSCF receives the forwarded REGISTER late, sends a Diameter UAR to HSS, gets a reply, but the overall SIP transaction has already timed out. The I-CSCF reports `cdp:timeout` — but this is a SYMPTOM of P-CSCF latency, not an HSS failure.

**Flaw 2: Misleading `does_NOT_mean`.** The `sip_edge_latency` chain says:
> "Diameter Cx failures — the Diameter path is separate from the Gm SIP path"

This is technically true (the Diameter transport between I-CSCF and HSS is fine) but operationally misleading. The Diameter query itself succeeds, but the SIP transaction that wraps it times out because of the P-CSCF delay. The I-CSCF reports `cdp:timeout` because the Kamailio transaction timer expired before the Diameter response could propagate back through the delayed P-CSCF. The `does_NOT_mean` should clarify: "Diameter Cx failures at I-CSCF CAN appear as a secondary symptom of P-CSCF latency — check P-CSCF RTT before concluding HSS is the problem."

**Flaw 3: No disambiguation between `sip_edge_latency` and `hss_unreachable`.** Both chains share the same observable symptom (`cdp:timeout > 0` at I-CSCF). The ontology provides no disambiguation rule to help the agent decide which chain applies. The critical differentiator is:
- If `pcscf.register_rate` is anomalously HIGH (retransmission storm) AND `cdp:timeout` is elevated → likely `sip_edge_latency` (P-CSCF is the bottleneck)
- If `pcscf.register_rate` is NORMAL and `cdp:timeout` is elevated → likely `hss_unreachable` (HSS is genuinely failing)

The ontology needs this disambiguation rule, and the symptom signatures need a pattern that matches "pcscf register storm + I-CSCF Diameter timeout → sip_edge_latency."

### Why the Investigator investigated the wrong thing

The InstructionGenerator (Phase 3) received the NetworkAnalyst's conclusion ("pyhss is the root cause") and generated:
> "Your ONLY job is to determine why `pyhss` is unresponsive to Diameter requests from `icscf`."

The Investigator followed this instruction and spent 127K tokens (9 tool calls) investigating pyhss and icscf. It checked pyhss logs (no Diameter errors — because pyhss is fine), checked icscf logs (saw the timeout — confirming the symptom but not the cause), and concluded "pyhss Diameter service is non-functional."

If the InstructionGenerator had been told "pcscf is the primary anomaly" (which the screener correctly flagged), it would have instructed: "Check P-CSCF transport layer RTT" → `measure_rtt("pcscf", "172.22.0.19")` → 2000ms RTT → correct diagnosis.

### Fixes needed

| Problem | Fix location | What to do |
|---|---|---|
| `sip_edge_latency` missing I-CSCF Diameter timeout as cascading symptom | `network_ontology/data/causal_chains.yaml` | Add `icscf.cdp:timeout > 0` as a cascading symptom of P-CSCF latency |
| `sip_edge_latency` misleading `does_NOT_mean` | `network_ontology/data/causal_chains.yaml` | Clarify that Diameter timeouts CAN appear as secondary effect of P-CSCF latency |
| No disambiguation between `sip_edge_latency` and `hss_unreachable` | `network_ontology/data/causal_chains.yaml` + `symptom_signatures.yaml` | Add disambiguation rule: "pcscf register storm + cdp:timeout → sip_edge_latency" |
| NetworkAnalyst prioritizes ontology alarms over screener flags | `network_analyst.md` prompt | Strengthen guidance: "The #1 screener flag identifies the component closest to the root cause. Ontology alarms on other components may be downstream symptoms." |

### Changes implemented
  1. causal_chains.yaml — sip_edge_latency enhanced:
  - Added I-CSCF cdp:timeout as a cascading symptom with detailed explanation of WHY it happens (SIP transaction wrapping the Diameter query times out due to P-CSCF delay)
  - Added disambiguation section: "If pcscf register rate is HIGH and cdp:timeout is elevated → sip_edge_latency, NOT hss_unreachable"
  - Fixed does_NOT_mean: no longer says Diameter Cx failures are unrelated — now clarifies they CAN appear as secondary symptoms
  - Updated diagnostic approach: priority 1 is now measure_rtt FROM pcscf (not from UE)
  - Added key signal: "pcscf register rate spike is THE distinguishing signal"

  2. causal_chains.yaml — hss_unreachable enhanced:
  - Added disambiguation section: "BEFORE concluding HSS is the root cause, check pcscf register rate and RTT"
  - Updated does_NOT_mean: added "HSS is necessarily the root cause — check P-CSCF first"
  - Updated diagnostic approach: priority 1 is now measure_rtt FROM pcscf to rule out sip_edge_latency

  3. symptom_signatures.yaml — new disambiguation signature:
  - Added pcscf_latency_with_diameter_cascade (very_high confidence): matches "pcscf register rate spike + icscf cdp:timeout" → diagnosis points to P-CSCF latency, explicitly warns against misdiagnosing as
  hss_unreachable

  4. network_analyst.md — screener priority guidance:
  - Added "Screener flags indicate proximity to root cause" section
  - Highest-ranked screener flag = epicenter of the problem
  - Other ontology alarms on different components may be cascading symptoms.
