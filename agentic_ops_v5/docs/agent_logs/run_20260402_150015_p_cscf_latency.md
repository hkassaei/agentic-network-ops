# Episode Report: P-CSCF Latency

**Agent:** v5  
**Episode ID:** ep_20260402_145550_p_cscf_latency  
**Date:** 2026-04-02T14:55:51.203674+00:00  
**Duration:** 263.4s  

---

## Scenario

**Category:** network  
**Blast radius:** single_nf  
**Description:** Inject 500ms latency on the P-CSCF (SIP edge proxy). SIP T1 timer is 500ms, so REGISTER transactions will start timing out. Tests IMS resilience to WAN-like latency on the signaling path.

## Faults Injected

- **network_latency** on `pcscf` — {'delay_ms': 500, 'jitter_ms': 50}

## Baseline (Pre-Fault)

Stack phase before injection: **ready**
All containers running at baseline.

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

## Pattern Match (Phase 2)

```
{"matched": false, "top_diagnosis": "No matching signature found", "confidence": "low", "failure_domain": "unknown", "matched_signatures": [], "baseline_anomalies": {"icscf": [{"metric": "ims_icscf:uar_timeouts", "expected": 0.0, "actual": 2.0, "alarm_if": "> 0", "note": ""}]}, "health_check_suggestions": [], "diagnostic_actions": [], "observations": {"amf_session": 4.0, "gnb": 1.0, "ran_ue": 2.0, "cdp:average_response_time": 104.0, "cdp:queuelength": 0.0, "cdp:replies_received": 4.0, "cdp:repli
```

## Anomaly Analysis (Phase 3)

> ### Layer Status
-   **RAN:** GREEN — `ran_ue = 2.0`, `gnb = 1.0` (UEs and gNB connected).
-   **Core:** GREEN — Active sessions and subscribers across AMF, SMF, UPF. All 5G core containers are running. Data plane metrics show activity.
-   **IMS:** YELLOW — Registrations are successful, but `ims_icscf:uar_timeouts = 2.0` (anomalous). Metrics for call setup and active calls (`core:rcv_requests_invite`, `dialog_ng:active`) are 0 across ICSCF, PCSCF, and SCSCF, suggesting a problem with call initi

## Investigation Instruction (Phase 4)

> INVESTIGATE: IMS layer is degraded. RAN and Core 5G are GREEN — do not investigate them first.

**Suspect components:** ICSCF, PCSCF, SCSCF.

**Key anomalies:**
*   **ICSCF:** `ims_icscf:uar_timeouts = 2.0` (Diameter User Authorization Request issues).
*   **PCSCF:** `httpclient:connfail = 186.0` (high HTTP client connection failures).
*   **ICSCF/PCSCF/SCSCF:** No call setup activity observed (`core:rcv_requests_invite = 0.0`, `dialog_ng:active = 0.0`) despite successful registrations. This ind

## Ground Truth

**Failure domain:** ims_signaling  
**Protocol impact:** SIP  
**Affected components:** pcscf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v5-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 253.7s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: Severe network latency (~470ms) between the PCSCF and SCP containers is causing HTTP client requests to time out, preventing the PCSCF from performing service discovery and blocking all IMS call setups.
> - **timeline**: 
>   1.  Network performance degrades between the `pcscf` and `scp` containers, introducing an average round-trip time of ~470ms.
>   2.  The PCSCF attempts to communicate with the SCP (acting as a proxy to the NRF) over HTTP for service discovery and registration, as shown by its configuration. `[EVIDENCE: read_running_config(container="pcscf", grep="http") -> "http_client_request_v2pk(\"PUT\", \"http://SCP_BIND_IP:SCP_BIND_PORT/nnrf-nfm/v1/nf-instances/$var(pcscf_uuid)\", ..."]`
>   3.  These HTTP requests fail due to the extreme latency, causing the PCSCF's `httpclient:connfail` metric to increase significantly. `[EVIDENCE: Triage Findings -> "PCSCF: httpclient:connfail = 184.0"]`
>   4.  Unable to communicate with core network functions via the SCP, the PCSCF cannot process call signaling.
>   5.  As a result, no call setup (INVITE) requests are processed, and all new IMS calls fail. `[EVIDENCE: Triage Findings -> "PCSCF: core:rcv_requests_invite = 0.0"]`
> - **root_cause**: The definitive first cause is a transport layer failure between the `pcscf` and `scp` containers. This was confirmed by direct measurement. `[EVIDENCE: measure_rtt(container="pcscf", target_ip="172.22.0.35") -> "rtt min/avg/max/mdev = 461.953/471.401/479.127/7.116 ms"]`
> - **affected_components**: `pcscf`, `scp`
> - **recommendation**: Resolve the network latency issue on the underlying host or container network between the `pcscf` and `scp` containers.
> - **confidence**: high
> - **explanation**: The investigation disproved the initial hypothesis that an anomaly on the ICSCF (`ims_icscf:uar_timeouts`) was the root cause. While the timeouts exist, the investigator demonstrated that the network path to the HSS is healthy and, more importantly, that user registrations are succeeding. Instead, the root cause was traced to a severe transport layer problem. An RTT measurement of over 470ms between the PCSCF and SCP confirms a network fault. This extreme latency directly causes the PCSCF's HTTP client to fail when communicating with the core network for service discovery, explaining the high `httpclient:connfail` count and the complete inability to establish any calls.

### Scoring Breakdown

**Overall score: 100%**

**Scorer assessment:** The agent provided an excellent and highly accurate diagnosis, correctly identifying the root cause, affected components, severity, and fault type with strong evidence and calibrated confidence.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | Yes | The agent correctly identified 'severe network latency' and 'transport layer failure' between the P-CSCF and a critical dependency (SCP) as the root cause, which directly matches the simulated 'elevated network latency on the P-CSCF's interfaces'. The measured latency (~470ms) is very close to the simulated 500ms. |
| Component overlap | 100% | The primary affected component, 'pcscf', was correctly identified. The inclusion of 'scp' is appropriate as it's a directly impacted dependency due to the latency. |
| Severity correct | Yes | The agent correctly assessed the severity as 'severe network latency' leading to 'HTTP client requests to time out' and 'blocking all IMS call setups' / 'complete inability to establish any calls', which aligns with the simulated failure causing SIP REGISTER timeouts and IMS registration failures. |
| Fault type identified | Yes | The agent clearly identified 'network latency' and 'transport layer failure' as the fault type, which is a correct observable class of network degradation. |
| Confidence calibrated | Yes | The agent stated 'high' confidence, which is well-calibrated given the accurate diagnosis, the specific evidence provided (RTT measurement), and the clear explanation of the causal chain. |

**Ranking position:** #1 — The agent provided a single, clear root cause as its primary diagnosis.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 350,218 |
| Output tokens | 10,676 |
| Thinking tokens | 23,202 |
| **Total tokens** | **384,096** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| TriageAgent | 12,525 | 3 | 4 |
| PatternMatcherAgent | 0 | 0 | 0 |
| AnomalyDetectorAgent | 211,061 | 12 | 13 |
| InstructionGeneratorAgent | 5,486 | 0 | 1 |
| InvestigatorAgent | 147,563 | 12 | 13 |
| SynthesisAgent | 7,461 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 263.4s
