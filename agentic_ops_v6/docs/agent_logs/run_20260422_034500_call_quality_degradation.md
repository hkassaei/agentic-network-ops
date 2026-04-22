# Episode Report: Call Quality Degradation

**Agent:** v6  
**Episode ID:** ep_20260422_034042_call_quality_degradation  
**Date:** 2026-04-22T03:40:43.417083+00:00  
**Duration:** 256.4s  

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

**Verdict:** ✅ `confirmed`

- **Wait:** 0s
- **Actual elapsed:** 0.0s
- **Nodes with significant deltas:** 4
- **Nodes with any drift:** 5

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

## Anomaly Screening (Phase 0)

No anomalies detected by the statistical screener.

## Event Aggregation (Phase 1)

No events fired during this episode. Either no metric KB triggers matched, or the episode encountered no meaningful state transitions.

## Correlation Analysis (Phase 2)

No events fired — correlation engine had nothing to work with.

## Network Analysis (Phase 3)

**Summary:** The IMS core is impaired due to Diameter connectivity issues between the I-CSCF and HSS, preventing user registration and call setup.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | The underlying container and network infrastructure appears to be functioning correctly. |
| **ran** | 🟢 GREEN | The RAN layer appears healthy and connected to the core. |
| **core** | 🟢 GREEN | The 5G core seems stable and is maintaining user sessions. |
| **ims** | 🔴 RED | The problem is localized to the IMS core. The evidence strongly points to a communication failure between the I-CSCF and the HSS, which is critical for registration and call routing. |

**IMS evidence:**
- I-CSCF is reporting Diameter timeouts (cdp:timeout=5.0, uar_timeouts=4.0, lir_timeouts=1.0).
- S-CSCF is reporting zero Diameter timeouts, suggesting the issue is specific to the I-CSCF's connection.
- P-CSCF metrics imply registration failures (register_failed=4.0, sl:200_replies=0.0).

**Ranked hypotheses:**

- **`h1`** (fit=0.90, nf=icscf, specificity=specific):
    - **Statement:** I-CSCF is failing to communicate with the HSS (pyhss) over the Diameter Cx interface, likely due to a localized network partition or a routing misconfiguration. This is preventing IMS registration and terminating call setup procedures.
    - **Falsification probes:**
        - A successful round-trip-time measurement (measure_rtt) from the 'icscf' container to the 'pyhss' container's IP would disprove a network partition.
        - The appearance of new Diameter timeout errors on the 'scscf' would indicate the fault is more likely with the HSS itself, not the I-CSCF's link.
- **`h2`** (fit=0.60, nf=pyhss, specificity=moderate):
    - **Statement:** The HSS is experiencing a partial failure or resource exhaustion that causes it to selectively drop or reject Diameter requests from the I-CSCF. The S-CSCF remains unaffected because its requests are being processed normally.
    - **Falsification probes:**
        - HSS container ('pyhss') showing healthy CPU and memory utilization would make a resource exhaustion hypothesis unlikely.
        - Logs on the HSS showing no record of incoming Diameter requests from the I-CSCF would shift the blame back to the network path or the I-CSCF itself.


## Falsification Plans (Phase 4)

*No output produced.*

## Parallel Investigators (Phase 5)

**2 sub-Investigator verdict(s):** **2 INCONCLUSIVE**

### `h1` — ❓ **INCONCLUSIVE**

**Hypothesis:** I-CSCF is failing to communicate with the HSS (pyhss) over the Diameter Cx interface, likely due to a localized network partition or a routing misconfiguration. This is preventing IMS registration and terminating call setup procedures.

**Reasoning:** No falsification plan was generated for this hypothesis.

### `h2` — ❓ **INCONCLUSIVE**

**Hypothesis:** The HSS is experiencing a partial failure or resource exhaustion that causes it to selectively drop or reject Diameter requests from the I-CSCF. The S-CSCF remains unaffected because its requests are being processed normally.

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


## Ground Truth

**Failure domain:** ims_media  
**Protocol impact:** RTP  
**Affected components:** rtpengine  
**Severity:** degraded

## Agent Diagnosis

**Model:** v6-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 121.0s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: The IMS core is impaired due to a likely communication failure between the I-CSCF and the HSS over the Diameter Cx interface, preventing user registration and call setup.
> - **timeline**:
>     1. No specific events were provided to construct a timeline. The issue was identified through an impairment in the IMS layer.
> - **root_cause**: The most probable root cause is a network partition or misconfiguration that is preventing the I-CSCF from communicating with the HSS. The primary suspect network function is `icscf`.
> - **affected_components**:
>     - `icscf`: Root Cause (suspected)
>     - `pyhss`: Secondary (potentially affected or a secondary suspect)
> - **recommendation**: The operator should manually investigate the network path between the `icscf` and `pyhss` containers to verify reachability and check for packet loss. Additionally, review the logs on both the I-CSCF and HSS for specific Diameter timeout or rejection errors that could pinpoint the failure.
> - **confidence**: low
> - **explanation**: The initial analysis produced two hypotheses: one pointing to a network failure between the I-CSCF and HSS (h1), and another suggesting a partial failure of the HSS itself (h2). However, the automated investigation agents failed to execute any commands to test these hypotheses, resulting in an `INCONCLUSIVE` verdict for both. The Evidence Validator flagged this as a `severe` failure, as no evidence could be verified. Therefore, confidence in the diagnosis is low. The highest-ranked hypothesis (h1), while unverified, remains the most likely starting point for manual troubleshooting.

### Scoring Breakdown

**Overall score: 15%**

**Scorer assessment:** The agent's diagnosis was largely incorrect, failing to identify the actual root cause, affected components, severity, or fault type. However, it correctly identified the general layer of the network where it believed the problem resided and appropriately expressed low confidence in its unverified diagnosis.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | No | The simulated failure was 30% packet loss on RTPEngine, leading to call quality degradation. The agent diagnosed a network partition/misconfiguration between I-CSCF and HSS, preventing user registration and call setup. This is a completely different root cause, affecting a different part of the network (signaling plane vs. media plane) and a different type of failure. |
| Component overlap | 0% | The simulated affected component was 'rtpengine'. The agent identified 'icscf' and 'pyhss' as affected components. There is no overlap. |
| Severity correct | No | The simulated failure was 'Call Quality Degradation' due to packet loss. The agent's diagnosis implies a complete service outage ('preventing user registration and call setup'), which is a higher severity than the actual degradation. |
| Fault type identified | No | The simulated fault type was 'packet loss' (degradation). The agent identified a 'network partition or misconfiguration' leading to communication failure, which is a different fault type (connectivity/reachability issue) and not specifically packet loss on the media plane. |
| Layer accuracy | Yes | The simulated affected component 'rtpengine' belongs to the 'ims' layer. The agent's network analysis correctly rated the 'ims' layer as 'red', even though its specific diagnosis within that layer was incorrect (I-CSCF/HSS instead of RTPEngine). Since I-CSCF and HSS are also IMS components, the layer attribution is consistent with the agent's (incorrect) reasoning. |
| Confidence calibrated | Yes | The agent's diagnosis was entirely incorrect, and it appropriately assigned a 'low' confidence, stating that automated investigation failed and hypotheses were unverified. This shows good calibration. |

**Ranking:** The correct root cause (RTPEngine packet loss) was not identified or ranked by the agent.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 46,814 |
| Output tokens | 1,229 |
| Thinking tokens | 8,995 |
| **Total tokens** | **57,038** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| EventAggregator | 0 | 0 | 0 |
| CorrelationAnalyzer | 0 | 0 | 0 |
| NetworkAnalystAgent | 47,722 | 4 | 5 |
| InstructionGeneratorAgent | 6,028 | 0 | 1 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 3,288 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 256.4s
