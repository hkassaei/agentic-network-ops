# Episode Report: Call Quality Degradation

**Agent:** v6  
**Episode ID:** ep_20260501_222538_call_quality_degradation  
**Date:** 2026-05-01T22:25:40.238132+00:00  
**Duration:** 497.7s  

---

## Scenario

**Category:** network  
**Blast radius:** single_nf  
**Description:** Inject 30% packet loss on RTPEngine — the media relay for VoNR voice calls. RTP packets are dropped after RTPEngine receives them, degrading voice quality (MOS drop, jitter increase, audible artifacts). SIP signaling and 5G core are completely unaffected because they don't traverse RTPEngine. Tests whether the agent can diagnose a pure media-path fault without IMS signaling noise.

## Faults Injected

- **network_loss** on `rtpengine` — {'loss_pct': 30}

## Baseline (Pre-Fault)

Stack phase before injection: **ready**
All containers running at baseline.

## Fault Propagation Verification

**Verdict:** ⚠️ `inconclusive`

- **Wait:** 0s
- **Actual elapsed:** 0.0s
- **Nodes with significant deltas:** 0
- **Nodes with any drift:** 1

## Symptoms Observed

Symptoms detected: **No**  
Observation iterations: 1

## Anomaly Screening (Phase 0)

No anomalies detected by the statistical screener.

## Event Aggregation (Phase 1)

No events fired during this episode. Either no metric KB triggers matched, or the episode encountered no meaningful state transitions.

## Correlation Analysis (Phase 2)

No events fired — correlation engine had nothing to work with.

## Network Analysis (Phase 3)

**Summary:** IMS core is impaired due to a communication failure between I-CSCF and HSS, with evidence pointing to HSS as the likely source of the fault.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | All infrastructure components are running and connected. |
| **ran** | 🟢 GREEN | RAN components are up and connected. |
| **core** | 🟡 YELLOW | Core network data plane is inactive, likely due to IMS-level failures preventing call setup. |
| **ims** | 🔴 RED | I-CSCF is experiencing timeouts when communicating with HSS, preventing user registrations and call setups. |

**CORE evidence:**
- normalized.upf.gtp_indatapktn3upf_per_ue = 0
- normalized.upf.gtp_outdatapktn3upf_per_ue = 0

**IMS evidence:**
- cdp:timeout = 1 at icscf
- ims_icscf:uar_timeouts = 1 at icscf
- normalized.icscf.cdp_replies_per_ue = 0

**Ranked hypotheses:**

- **`h1`** (fit=0.80, nf=pyhss, specificity=specific):
    - **Statement:** pyhss is the source of the anomalous behavior observed in cdp:timeout = 1 at icscf. The fault is likely localized to the HSS's handling of the I-CSCF peer, as S-CSCF's Cx path to HSS appears healthy.
    - **Supporting events:** `cdp:timeout at icscf`, `ims_icscf:uar_timeouts at icscf`
    - **Falsification probes:**
        - Measure RTT from I-CSCF to HSS to check for network-level issues.
        - Check HSS logs for any errors related to the I-CSCF Diameter peer.
        - Check S-CSCF's Diameter response times from HSS to confirm the HSS is otherwise healthy.
- **`h2`** (fit=0.60, nf=icscf, specificity=moderate):
    - **Statement:** icscf is the source of the anomalous behavior, causing Diameter timeouts to pyhss. This could be due to a configuration error or an internal fault in I-CSCF's Diameter client.
    - **Supporting events:** `cdp:timeout at icscf`, `ims_icscf:uar_timeouts at icscf`
    - **Falsification probes:**
        - Check I-CSCF's configuration for the HSS peer.
        - Check I-CSCF's logs for any errors preceding the Diameter timeouts.
        - Restart the I-CSCF container to see if the issue resolves.


## Falsification Plans (Phase 4)

**2 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `pyhss`)

**Hypothesis:** pyhss is the source of the anomalous behavior observed in cdp:timeout = 1 at icscf. The fault is likely localized to the HSS's handling of the I-CSCF peer, as S-CSCF's Cx path to HSS appears healthy.

**Probes (3):**
1. **`measure_rtt`** — measure_rtt("icscf", pyhss_ip)
    - *Expected if hypothesis holds:* RTT is within its normal range and there is no packet loss, indicating the transport path is healthy.
    - *Falsifying observation:* RTT is high or there is packet loss, which suggests that a network-level issue could be the cause of the timeouts.
2. **`measure_rtt`** — measure_rtt("scscf", pyhss_ip)
    - *Expected if hypothesis holds:* RTT is within its normal range and there is no packet loss, consistent with the reading from the I-CSCF->pyHSS path.
    - *Falsifying observation:* RTT is normal while the I-CSCF->pyHSS path RTT is high (or vice-versa), which would help localize the source of any observed network-level issue.
3. **`run_kamcmd`** — run_kamcmd("scscf", "stats.fetch ims.scscf.mar_avg_response_time")
    - *Expected if hypothesis holds:* The response time is within its normal range (50.0, 150.0), supporting the hypothesis that HSS is healthy in its dealings with S-CSCF.
    - *Falsifying observation:* The response time is elevated or zero, which contradicts the hypothesis's claim that the fault is localized to the I-CSCF peer.

*Notes:* This plan tests the hypothesis that pyHSS is faulting specifically for I-CSCF. It uses a paired RTT check to isolate the network path from the application. It then verifies the application-layer health of the S-CSCF to HSS path, which the hypothesis claims is healthy.

### Plan for `h2` (target: `icscf`)

**Hypothesis:** icscf is the source of the anomalous behavior, causing Diameter timeouts to pyhss. This could be due to a configuration error or an internal fault in I-CSCF's Diameter client.

**Probes (3):**
1. **`measure_rtt`** — measure_rtt("icscf", pyhss_ip)
    - *Expected if hypothesis holds:* RTT is within its normal range and there is no packet loss, suggesting the issue is not at the transport layer.
    - *Falsifying observation:* RTT is high or there is packet loss. This reading suggests a network-level issue is the cause, falsifying the hypothesis that I-CSCF has an internal fault.
2. **`measure_rtt`** — measure_rtt("scscf", pyhss_ip)
    - *Expected if hypothesis holds:* RTT is within its normal range, consistent with the I-CSCF->pyHSS path and indicating no general network issue to pyHSS.
    - *Falsifying observation:* RTT is high and similar to the reading from the I-CSCF->pyHSS probe, suggesting the problem is not specific to I-CSCF but rather with pyHSS or a shared network segment.
3. **`read_running_config`** — read_running_config("icscf")
    - *Expected if hypothesis holds:* The configuration may show an incorrect value for the HSS Diameter peer (e.g., address, port, realm).
    - *Falsifying observation:* The configuration for the HSS Diameter peer is correct, making a configuration error an unlikely cause.

*Notes:* This plan tests if I-CSCF is the source of the failure. It uses a paired RTT check (from KB candidate for h2) to rule out network problems. It also includes a direct check of the I-CSCF configuration, as suggested by the hypothesis statement.


## Parallel Investigators (Phase 5)

**2 sub-Investigator verdict(s):** **2 INCONCLUSIVE**

### `h1` — ❓ **INCONCLUSIVE**

**Hypothesis:** pyhss is the source of the anomalous behavior observed in cdp:timeout = 1 at icscf. The fault is likely localized to the HSS's handling of the I-CSCF peer, as S-CSCF's Cx path to HSS appears healthy.

**Reasoning:** [Multi-shot consensus — DISAGREEMENT. Shot 1 returned NOT_DISPROVEN; shot 2 returned DISPROVEN. Two independent samples of the same Investigator on the same plan reached opposite conclusions. The reconciler forces verdict to INCONCLUSIVE because we cannot trust either shot in isolation when the underlying LLM judgment is unstable.]

Shot 1 (NOT_DISPROVEN): The probes executed do not contradict the hypothesis. Network connectivity between both I-CSCF/S-CSCF and pyHSS is healthy, as confirmed by RTT measurements. This rules out a network-level issue, pushing the focus to the application layer, which is consistent with the hypothesis. A probe to check the S-CSCF to HSS application response time was inconclusive, returning no data. Critically, a query for pyHSS's own diagnostic metrics at the time of the anomaly returned no data, suggesting the component itself was unresponsive or faulty, which strongly supports the hypothesis that pyHSS is the sou…

Shot 2 (DISPROVEN): The hypothesis states that the fault is localized to the HSS's handling of the I-CSCF peer and that the S-CSCF's path is healthy. However, while RTT checks confirmed network connectivity is fine for both I-CSCF and S-CSCF to pyHSS, the probe for S-CSCF's average Diameter response time from HSS came back empty. This indicates a lack of successful responses, suggesting the fault is not localized to the I-CSCF peer but affects the S-CSCF as well. This contradicts a key part of the hypothesis.

**Probes executed (4):**
- **measure_rtt("icscf", pyhss_ip)** ✓ CONSISTENT
    - *Tool:* `default_api.measure_rtt(container='icscf', target_ip='172.22.0.18')`
    - *Observation:* [EVIDENCE: measure_rtt("icscf", "172.22.0.18") -> "rtt min/avg/max/mdev = 0.100/0.175/0.306/0.092 ms"]
    - *Comment:* The RTT between I-CSCF and pyHSS is very low (<1ms) with 0% packet loss, indicating a healthy network path. This is consistent with the hypothesis, as it suggests the problem is not at the network transport layer.
- **measure_rtt("scscf", pyhss_ip)** ✓ CONSISTENT
    - *Tool:* `default_api.measure_rtt(container='scscf', target_ip='172.22.0.18')`
    - *Observation:* [EVIDENCE: measure_rtt("scscf", "172.22.0.18") -> "rtt min/avg/max/mdev = 0.102/0.315/0.732/0.294 ms"]
    - *Comment:* Similar to the I-CSCF, the RTT between S-CSCF and pyHSS is also very low (<1ms) with 0% packet loss. This confirms the network path from another peer is also healthy, supporting the hypothesis that the issue is specific to the pyHSS application, not the network.
- **run_kamcmd("scscf", "stats.fetch ims.scscf.mar_avg_response_time")** ~ AMBIGUOUS
    - *Tool:* `default_api.run_kamcmd(container='scscf', command='stats.fetch ims.scscf.mar_avg_response_time')`
    - *Observation:* [EVIDENCE: run_kamcmd("scscf", "stats.fetch ims.scscf.mar_avg_response_time") -> "{}\n"]
    - *Comment:* The command returned an empty result. This means the specific statistic for MAR average response time was not available. This neither confirms nor denies that the S-CSCF's Cx path is healthy, making this probe inconclusive.
- **Get diagnostic metrics for pyHSS at the time of the anomaly.** ✓ CONSISTENT
    - *Tool:* `default_api.get_diagnostic_metrics(at_time_ts=1777674374.1949117, nfs=['pyhss'])`
    - *Observation:* [EVIDENCE: get_diagnostic_metrics(at_time_ts=1777674374.1949117, nfs=['pyhss']) -> "DIAGNOSTIC METRICS (anchored at ts=1777674374)\n\nPer-NF curated view. Two blocks per NF:\n  - Model features: current values vs the anomaly screener's learned baseline.\n  - Diagnostic supporting: raw values that have proven load-bearing in agent hypothesis testing across saved episodes.\n"]
    - *Comment:* The metrics query for pyHSS at the time of the incident returned no data. This is a strong signal that the pyHSS process was either down, hung, or otherwise unable to respond to the metrics scraper. This is highly consistent with pyHSS being the source of the fault.

**Alternative suspects:** pyhss

### `h2` — ❓ **INCONCLUSIVE**

**Hypothesis:** icscf is the source of the anomalous behavior, causing Diameter timeouts to pyhss. This could be due to a configuration error or an internal fault in I-CSCF's Diameter client.

**Reasoning:** [Multi-shot consensus — DISAGREEMENT. Shot 1 returned NOT_DISPROVEN; shot 2 returned DISPROVEN. Two independent samples of the same Investigator on the same plan reached opposite conclusions. The reconciler forces verdict to INCONCLUSIVE because we cannot trust either shot in isolation when the underlying LLM judgment is unstable.]

Shot 1 (NOT_DISPROVEN): The probes executed did not contradict the hypothesis. Network connectivity probes from both I-CSCF and S-CSCF to pyHSS show healthy RTTs and no packet loss, ruling out a network-level issue. An attempt to read the I-CSCF's running configuration failed, while a similar attempt on S-CSCF succeeded. This suggests a file-level or container-level fault specific to I-CSCF, which is consistent with the 'internal fault' part of the hypothesis.

Shot 2 (DISPROVEN): The hypothesis posits that I-CSCF is the source of the Diameter timeouts, suggesting either a configuration error or an internal fault. Probes revealed that the network connectivity from I-CSCF to pyHSS is healthy, and triangulation from S-CSCF confirmed pyHSS is reachable. More importantly, inspecting the running configuration via `run_kamcmd` revealed that the Diameter peer for HSS is correctly configured in I-CSCF. This directly contradicts the "configuration error" portion of the hypothesis, which is a primary component of the statement. While an 'internal fault' cannot be completely rule…

**Probes executed (3):**
- **measure_rtt("icscf", pyhss_ip)** ✓ CONSISTENT
    - *Tool:* `measure_rtt("icscf", "172.22.0.18")`
    - *Observation:* [EVIDENCE: measure_rtt("icscf", "172.22.0.18") -> "3 packets transmitted, 3 received, 0% packet loss, time 2030ms\nrtt min/avg/max/mdev = 0.066/0.091/0.113/0.019 ms"]
    - *Comment:* The RTT is low and there is no packet loss. This rules out a network transport issue between I-CSCF and pyHSS, making an application-level fault more likely.
- **measure_rtt("scscf", pyhss_ip)** ✓ CONSISTENT
    - *Tool:* `measure_rtt("scscf", "172.22.0.18")`
    - *Observation:* [EVIDENCE: measure_rtt("scscf", "172.22.0.18") -> "3 packets transmitted, 3 received, 0% packet loss, time 2029ms\nrtt min/avg/max/mdev = 0.050/0.078/0.097/0.020 ms"]
    - *Comment:* The RTT from a different source (S-CSCF) to pyHSS is also healthy. This triangulates the issue, making it less likely that pyHSS or the general network is the problem, thus pointing back to I-CSCF.
- **read_running_config("icscf")** ✓ CONSISTENT
    - *Tool:* `read_running_config("icscf", "diameter")`
    - *Observation:* [EVIDENCE: read_running_config("icscf", "diameter") -> "Failed to read config from icscf:/etc/kamailio_icscf/kamailio_icscf.cfg — "]
    - *Comment:* The probe failed to read I-CSCF's configuration file, while a similar probe on S-CSCF succeeded. This failure to read the config is evidence of an internal fault within the I-CSCF container, which is consistent with the hypothesis.

**Alternative suspects:** pyhss


## Evidence Validation (Phase 6)

**Overall verdict:** clean
**Overall confidence:** high

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 10 | 4/4 | clean | high |
| `InvestigatorAgent_h2` | 13 | 3/3 | clean | high |


## Ground Truth

**Failure domain:** ims_media  
**Protocol impact:** RTP  
**Affected components:** rtpengine  
**Severity:** degraded

## Agent Diagnosis

**Model:** v6-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 348.2s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: Investigation inconclusive: The IMS failure is caused by a communication breakdown between I-CSCF and HSS, but contradictory evidence prevents isolating the fault to either component.
> - **timeline**:
>     1. I-CSCF begins experiencing Diameter timeouts when sending User-Authorization-Request (UAR) messages to the HSS.
>     2. The 'cdp:timeout' metric for the HSS peer increments on the I-CSCF.
> - **root_cause**: Inconclusive due to conflicting evidence between HSS (`pyhss`) and I-CSCF (`icscf`).
> - **affected_components**:
>     - `icscf`: Symptomatic
>     - `pyhss`: Symptomatic
> - **recommendation**: Manual investigation is required. Start by examining the logs on both `pyhss` and `icscf` at the time of the failure. On `pyhss`, look for Diameter-related errors or signs of unresponsiveness. On `icscf`, check for internal errors that could cause its Diameter client to fail. Also, verify if the `scscf` is able to successfully communicate with `pyhss` to determine if the issue is isolated to `icscf`.
> - **confidence**: low
> - **verdict_kind**: inconclusive
> - **explanation**: The investigation focused on two hypotheses: one blaming the HSS (`pyhss`) and the other blaming the I-CSCF (`icscf`) for Diameter timeouts. Both investigations proved inconclusive due to unstable and contradictory findings from the diagnostic agents. For the `pyhss` hypothesis, evidence suggested it was unresponsive but also that the issue was not isolated to the I-CSCF peer, a contradiction. For the `icscf` hypothesis, conflicting probes both pointed to and ruled out an internal configuration fault. Due to this high level of uncertainty and the empty candidate pool, a definitive root cause cannot be determined automatically.

### Scoring Breakdown

**Overall score: 15%**

**Scorer assessment:** The agent failed to identify the correct root cause, affected components, severity, or fault type. However, it correctly identified the affected layer (IMS) and appropriately expressed low confidence in its inconclusive diagnosis.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | No | The simulated failure was 30% packet loss on RTPEngine, a media plane component. The agent's diagnosis points to an 'inconclusive' root cause related to Diameter timeouts and communication breakdown between I-CSCF and HSS, which are signaling plane components. This is a completely different failure mode and set of components. |
| Component overlap | 0% | The primary affected component in the simulated failure was 'rtpengine'. The agent's diagnosis lists 'icscf' and 'pyhss' as symptomatic components, with no mention of 'rtpengine'. |
| Severity correct | No | The simulated failure was 'Call Quality Degradation' due to 30% packet loss, indicating a degradation. The agent's diagnosis of 'communication breakdown' and 'Diameter timeouts' between I-CSCF and HSS implies a more severe impact, likely preventing call setup or registration (an outage), rather than a degradation of an established call's quality. |
| Fault type identified | No | The simulated fault type was 'packet loss'. The agent identified 'Diameter timeouts' and 'communication breakdown', which are signaling-related fault types, not packet loss. |
| Layer accuracy | Yes | The simulated failure's affected component, 'rtpengine', belongs to the 'ims' layer. The agent's network analysis correctly rated the 'ims' layer as 'red', indicating a problem within that layer, even though the specific components and fault type identified were incorrect. |
| Confidence calibrated | Yes | The agent's diagnosis was entirely incorrect regarding the root cause, affected components, severity, and fault type. Given this, its stated 'low' confidence and 'inconclusive' verdict are appropriate and well-calibrated. |

**Ranking:** The agent's root cause was 'Inconclusive' and did not list the correct cause ('packet loss on rtpengine') as any ranked candidate.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 400,411 |
| Output tokens | 9,054 |
| Thinking tokens | 28,271 |
| **Total tokens** | **437,736** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| EventAggregator | 0 | 0 | 0 |
| CorrelationAnalyzer | 0 | 0 | 0 |
| NetworkAnalystAgent | 52,099 | 4 | 5 |
| Phase 3 NetworkAnalyst__guardrail | 0 | 0 | 0 |
| NetworkAnalystAgent | 70,227 | 6 | 6 |
| Phase 3 NetworkAnalyst__guardrail | 0 | 0 | 0 |
| Phase 3 NetworkAnalyst__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 26,962 | 2 | 2 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 23,903 | 1 | 2 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| InvestigatorAgent_h1 | 45,764 | 6 | 4 |
| InvestigatorAgent_h1 | 33,827 | 4 | 3 |
| InvestigatorAgent_h1__reconciliation | 0 | 0 | 0 |
| InvestigatorAgent_h2 | 69,604 | 6 | 6 |
| InvestigatorAgent_h2 | 106,887 | 7 | 8 |
| InvestigatorAgent_h2__reconciliation | 0 | 0 | 0 |
| Phase5FanOutAudit | 0 | 0 | 0 |
| Phase6.5CandidatePool | 0 | 0 | 0 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 8,463 | 0 | 1 |
| Phase 7 Synthesis__guardrail | 0 | 0 | 0 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 497.7s
