# Episode Report: P-CSCF Latency

**Agent:** v5  
**Episode ID:** ep_20260406_232724_p_cscf_latency  
**Date:** 2026-04-06T23:27:25.554522+00:00  
**Duration:** 553.9s  

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
- **Nodes with significant deltas:** 1
- **Nodes with any drift:** 4

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

### Metrics Changes

| Node | Metric | Baseline | Current | Delta |
|------|--------|----------|---------|-------|
| pcscf | core:rcv_requests_register | 70.0 | 86.0 | 16.0 |
| pcscf | script:register_time | 115570.0 | 144168.0 | 28598.0 |

## Network Analysis (Phase 1)

**Summary:** The IMS layer is down due to Diameter timeouts between the I-CSCF and HSS, preventing user registration and call setup; all other network layers appear healthy.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | All infrastructure components (mongo, mysql, dns) are running with no reported anomalies. |
| **ran** | 🟢 GREEN | gNB is connected to the AMF and 2 UEs are attached. |
| **core** | 🟢 GREEN | 5G Core is stable, with active PDU sessions. The data plane is idle, which is normal as no calls are in progress. |
| **ims** | 🔴 RED | The I-CSCF is failing to communicate with the HSS, resulting in control plane failure. |

**IMS evidence:**
- I-CSCF shows a Diameter timeout with cdp:timeout=1.0 from get_nf_metrics (expected: 0).
- I-CSCF shows a User Authorization Request (UAR) timeout with ims_icscf:uar_timeouts=1.0 from get_nf_metrics (expected: 0).

**Suspect components:**

- **icscf** (high): The I-CSCF is the component reporting the Diameter timeouts (cdp:timeout=1.0), indicating it cannot get a response from the HSS for user authorization.
- **pyhss** (high): The HSS (pyhss) is the target of the timed-out Diameter requests from the I-CSCF. The failure is likely due to the HSS being unresponsive or misconfigured.

**Investigation hint:** Focus on the Diameter (Cx interface) communication between the I-CSCF and the HSS (pyhss). The I-CSCF is reporting timeouts when sending User Authorization Requests (UAR). Check for network connectivity between the two containers, and inspect the logs and status of the pyhss container to determine why it is not responding to the I-CSCF's Diameter queries.

**Tools called:** get_vonr_components, get_network_topology, get_network_status, get_nf_metrics, get_dp_quality_gauges, compare_to_baseline, check_stack_rules


## Pattern Match (Phase 2)

**❌ Match:** No matching signature found

- **Confidence:** low
- **Failure domain:** unknown
- **Baseline anomalies:** 2 metrics across 2 components


## Investigation Instruction (Phase 3)

> Anomalies detected in IMS. Suspect components: `icscf` and `pyhss`. The I-CSCF is experiencing Diameter User Authorization Request (UAR) timeouts (`ims_icscf:uar_timeouts=1.0`) when attempting to communicate with the HSS (pyhss) over the Cx interface, preventing user registration.
>
> Per the Hierarchy of Truth, first, check transport layer connectivity using `measure_rtt` between the `icscf` and `pyhss` containers. Then, examine `check_container_logs` for both `icscf` and `pyhss` for errors related to Diameter or HSS responses. Do NOT investigate the RAN, Core, or Infrastructure layers as they are healthy.

## Ground Truth

**Failure domain:** ims_signaling  
**Protocol impact:** SIP  
**Affected components:** pcscf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v5-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 174.4s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: The IMS HSS (`pyhss`) container is unresponsive to Diameter requests, causing user registration to fail due to timeouts at the I-CSCF.
> - **timeline**:
>   - 1. A user equipment attempts to register with the IMS network.
>   - 2. The I-CSCF sends a Diameter User-Authorization-Request (UAR) to the HSS (`pyhss`) to authenticate the user.
>   - 3. Network transport between `icscf` and `pyhss` is healthy, with a round-trip time of less than 1ms.
>   - 4. The Diameter application service within the `pyhss` container fails to process the incoming UAR request and does not send a response. This is confirmed by a complete lack of Diameter-related log entries in the `pyhss` container.
>   - 5. The I-CSCF's request times out, incrementing the `ims_icscf:uar_timeouts` metric.
>   - 6. The user registration process fails, preventing access to IMS services like VoNR calls.
> - **root_cause**: The application service responsible for handling the Diameter protocol inside the `pyhss` container has silently failed. While the container itself is running and reachable over the network, it is not processing authentication requests from the I-CSCF, leading to a control plane failure in the IMS layer.
> - **affected_components**:
>   - `pyhss` (Root Cause)
>   - `icscf` (Symptom)
> - **recommendation**: The network transport layer has been ruled out as a cause. The operator should investigate the application state within the `pyhss` container. Verify the status of the internal Diameter service process and inspect application-specific health checks to determine why it is not responding to requests.
> - **confidence**: high
> - **explanation**: The investigation confirmed that IMS registration is failing due to Diameter timeouts between the I-CSCF and the HSS (`pyhss`). Evidence shows that network connectivity between these components is excellent, ruling out a transport-layer issue. However, logs from the `pyhss` container show no evidence of it processing any Diameter requests, indicating the application service within the container is unresponsive. This silent application failure is the root cause of the outage.

### Scoring Breakdown

**Overall score: 0%**

**Scorer assessment:** The agent completely misdiagnosed the issue, attributing it to an HSS application failure instead of P-CSCF latency, and showed poor confidence calibration.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | No | The simulated failure was P-CSCF latency, leading to SIP REGISTER timeouts. The agent diagnosed an unresponsive Diameter application service within the HSS (pyhss) container, which is a completely different root cause and component. |
| Component overlap | 0% | The primary affected component in the simulation was 'pcscf'. The agent identified 'pyhss' as the root cause component, which has no overlap. |
| Severity correct | No | The simulated failure was a 'latency' issue (degradation) causing timeouts. The agent diagnosed an 'unresponsive' application leading to a 'control plane failure' and 'outage', which implies a complete functional failure rather than a degradation. |
| Fault type identified | No | The simulated fault type was 'network degradation' (latency). The agent identified a 'service hang' or 'component unresponsive' (application service silently failed), which is a different class of failure. |
| Confidence calibrated | No | The agent stated 'high' confidence for a diagnosis that was entirely incorrect, indicating poor calibration. |

**Ranking:** The agent provided only one primary diagnosis, which was incorrect.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 141,371 |
| Output tokens | 2,888 |
| Thinking tokens | 9,647 |
| **Total tokens** | **153,906** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| NetworkAnalystAgent | 48,339 | 8 | 4 |
| PatternMatcherAgent | 0 | 0 | 0 |
| InstructionGeneratorAgent | 5,278 | 0 | 1 |
| InvestigatorAgent | 92,020 | 9 | 10 |
| EvidenceValidatorAgent | 0 | 0 | 0 |
| SynthesisAgent | 8,269 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 553.9s
