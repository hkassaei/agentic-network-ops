# Episode Report: HSS Unresponsive

**Agent:** v5  
**Episode ID:** ep_20260402_010136_hss_unresponsive  
**Date:** 2026-04-02T01:01:37.201507+00:00  
**Duration:** 215.0s  

---

## Scenario

**Category:** network  
**Blast radius:** single_nf  
**Description:** Inject 60-second outbound delay on the HSS (PyHSS). The HSS container is running, the process is alive, and the IP is reachable — but all Diameter responses are delayed by 60 seconds, far exceeding the Cx Diameter timeout. Tests how the I-CSCF and S-CSCF handle a Diameter peer that accepts connections but never responds in time.

## Faults Injected

- **network_latency** on `pyhss` — {'delay_ms': 60000, 'jitter_ms': 0}

## Baseline (Pre-Fault)

Stack phase before injection: **ready**
All containers running at baseline.

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

## Pattern Match (Phase 2)

```
{"matched": false, "top_diagnosis": "No matching signature found", "confidence": "low", "failure_domain": "unknown", "matched_signatures": [], "baseline_anomalies": {"icscf": [{"metric": "ims_icscf:uar_timeouts", "expected": 0.0, "actual": 1.0, "alarm_if": "> 0", "note": ""}], "scscf": [{"metric": "ims_usrloc_scscf:active_contacts", "expected": 2.0, "actual": 1.0, "alarm_if": "", "note": ""}]}, "health_check_suggestions": [], "diagnostic_actions": [], "observations": {"amf_session": 4.0, "gnb": 
```

## Anomaly Analysis (Phase 3)

> **Layer Status**
- **RAN:** GREEN — `gnb = 1.0`, `ran_ue = 2.0` (active UEs and gNodeBs)
- **Core:** GREEN — `amf_session = 4.0`, `pfcp_sessions_active = 4.0`, `ues_active = 2.0`, `bearers_active = 4.0` (core functions appear active and handling sessions)
- **IMS:** YELLOW — `core:rcv_requests_invite = 0.0` for ICSCF, PCSCF, and SCSCF (no IMS calls initiated/received), `dialog_ng:active = 0.0` for PCSCF and SCSCF, `httpclient:connfail = 18.0` on PCSCF, `ims_icscf:uar_timeouts = 1.0`, `ims_usrloc

## Investigation Instruction (Phase 4)

> INVESTIGATE: The IMS layer is failing with registration and call setup. RAN and 5G Core functions (AMF, SMF, UPF, PCF) are GREEN — do not investigate them.

**Key Anomalies:**
*   **PCSCF:** `httpclient:connfail` (18.0), `script:register_failed` (1.0), `core:rcv_requests_invite` (0.0), `dialog_ng:active` (0.0). No successful HTTP connections (`httpclient:connok = 0.0`) or SIP 200 replies (`sl:200_replies = 0.0`).
*   **ICSCF:** `ims_icscf:uar_timeouts` (1.0), `cdp:timeout` (1.0), `core:rcv_reque

## Ground Truth

**Failure domain:** ims_signaling  
**Protocol impact:** Diameter  
**Affected components:** pyhss  
**Severity:** degraded

## Agent Diagnosis

**Model:** v5-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 194.0s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: The root cause of the IMS failure is a complete network partition between the ICSCF and the HSS (pyhss), preventing user authorization and halting the IMS registration process.
> - **timeline**:
>     1.  A network fault occurs, causing 100% packet loss between the `icscf` and `pyhss` containers.
>     2.  A UE attempts to register. The SIP REGISTER request is forwarded by the PCSCF to the ICSCF.
>     3.  The ICSCF sends a Diameter User-Authorization-Request (UAR) to the HSS to authenticate the user.
>     4.  Due to the network partition, the UAR packets never reach the HSS.
>     5.  The Diameter request on the ICSCF times out, incrementing the `ims_icscf:uar_timeouts` and `cdp:timeout` metrics.
>     6.  The registration process fails. As a result, users cannot get online, and no IMS calls can be established, explaining the zero values for `core:rcv_requests_invite`.
> - **root_cause**: **Transport Layer Failure**. A network fault is dropping all packets between the `icscf` container and the `pyhss` container. This was definitively proven by a network reachability test.
> - **affected_components**: `icscf`, `pyhss`. Downstream effects are seen on `pcscf` and `scscf`.
> - **recommendation**: Resolve the network connectivity issue between the `icscf` and `pyhss` containers. Investigate the underlying container networking configuration, firewall rules, or routing policies affecting traffic between these two specific components.
> - **confidence**: high
> - **explanation**: The investigation confirmed the initial anomaly analysis pointing to a connectivity issue. While initial metrics showed errors across multiple IMS components, the definitive root cause was isolated to the transport layer. The ICSCF is unable to authorize users because it cannot reach the HSS, as evidenced by `measure_rtt` showing 100% packet loss. This network failure is the first and most critical fault in the chain, directly causing the `ims_icscf:uar_timeouts`. All other symptoms, including one failed registration (`script:register_failed`) and a low number of active contacts (`ims_usrloc_scscf:active_contacts`), are direct consequences of this primary network outage. The `httpclient` failures on the PCSCF are a separate, secondary issue that is not blocking the system in the same way.

### Scoring Breakdown

**Overall score: 40%**

**Scorer assessment:** The agent correctly identified the affected components and the severity of the impact (outage due to timeouts), but misidentified the specific network fault as packet loss/partition instead of high latency. Its high confidence was therefore not calibrated.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | No | The simulated failure was a 60-second network delay on the HSS (pyhss), causing Diameter timeouts. The agent diagnosed a 'complete network partition' and '100% packet loss' between the ICSCF and HSS, explicitly stating packets 'never reach the HSS' and are 'dropping all packets'. These are distinct network phenomena; packets were delayed, not dropped. |
| Component overlap | 100% | The agent correctly identified 'pyhss' (HSS) as the primary component experiencing the network issue, and 'icscf' as directly affected, with 'pcscf' and 'scscf' as downstream impacts. |
| Severity correct | Yes | The 60-second delay 'far exceeding the Cx Diameter timeout' effectively causes a complete service outage for IMS registration, which the agent correctly described as 'halting the IMS registration process' and 'users cannot get online'. |
| Fault type identified | No | The simulated fault type was 'Elevated network latency' (a form of network degradation). The agent identified 'complete network partition' and '100% packet loss' (a form of component unreachable/service partition). These are different observable fault types. |
| Confidence calibrated | No | The agent expressed 'high' confidence in its diagnosis of '100% packet loss' based on a 'network reachability test' showing this. However, the actual simulated failure was a 60-second delay, not packet loss. While the agent's tools might have reported 100% loss due to timeouts, the underlying network fault type was misidentified, making the high confidence poorly calibrated to the actual failure mode. |

**Ranking:** The agent provided only one primary diagnosis, which was incorrect.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 123,704 |
| Output tokens | 11,538 |
| Thinking tokens | 13,790 |
| **Total tokens** | **149,032** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| TriageAgent | 11,563 | 3 | 4 |
| PatternMatcherAgent | 0 | 0 | 0 |
| AnomalyDetectorAgent | 39,275 | 3 | 4 |
| InstructionGeneratorAgent | 7,083 | 0 | 1 |
| InvestigatorAgent | 83,259 | 9 | 7 |
| SynthesisAgent | 7,852 | 0 | 1 |


## Resolution

**Heal method:** scheduled
**Recovery time:** 215.0s

---

## Post-Run Analysis

### Agent Performance Assessment

The agent performed well on this scenario. The 40% score from the automated scorer does not reflect the actual quality of the diagnosis.

**What the agent got right:**
- Correctly identified HSS (pyhss) as the root cause component
- Correctly traced the full causal chain: I-CSCF → Diameter UAR to HSS → timeout → registration fails
- Correctly identified `ims_icscf:uar_timeouts` and `cdp:timeout` as the key diagnostic signals
- Correctly separated the `httpclient:connfail` at P-CSCF as a "separate, secondary issue" (pre-existing noise)
- Correctly concluded RAN and Core are GREEN and focused exclusively on IMS
- Cited tool evidence throughout: `measure_rtt`, `get_nf_metrics`, container logs
- The 6-phase pipeline worked as designed: Pattern Matcher found no match → Anomaly Detector identified IMS YELLOW with Diameter timeouts → Instruction Generator focused the investigator on IMS → Investigator confirmed HSS connectivity issue

**Estimated fair score: ~85%**

### Scorer Problem: Latency vs Packet Loss Indistinguishability

The scorer penalized the agent for diagnosing "100% packet loss / network partition" instead of "elevated latency (60s delay)." This is unfair for two reasons:

1. **`measure_rtt` (ping) cannot distinguish extreme latency from packet loss.** The default ping timeout is 1-5 seconds. A 60-second network delay causes every ping to timeout, and the tool reports "100% packet loss." The agent correctly interpreted the tool output it received — it didn't misread the evidence; the evidence itself is ambiguous at this latency level.

2. **From the network's observable perspective, extreme latency and packet loss are functionally identical** when the latency exceeds the application's timeout. The Diameter Tw timer is ~30s. A 60-second delay means the Diameter response arrives AFTER the timeout has fired — the I-CSCF treats this identically to a dropped packet. The agent's diagnosis ("S-CSCF cannot reach HSS, Diameter requests timeout") is operationally correct regardless of whether the underlying cause is loss or delay.

The agent's recommendation — "resolve the network connectivity issue between I-CSCF and HSS" — is the correct action for both scenarios.

**Scorer improvement needed:** The scorer should accept "transport failure to HSS" / "HSS unreachable" / "network partition" as equivalent to "elevated latency on HSS" when the simulated latency exceeds the application's timeout threshold, since both produce identical observable symptoms and require the same remediation.
