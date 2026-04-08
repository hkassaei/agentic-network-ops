# Episode Report: P-CSCF Latency

**Agent:** v5  
**Episode ID:** ep_20260406_215015_p_cscf_latency  
**Date:** 2026-04-06T21:50:16.502531+00:00  
**Duration:** 160.1s  

---

## Scenario

**Category:** network  
**Blast radius:** single_nf  
**Description:** Inject 500ms latency on the P-CSCF (SIP edge proxy). SIP T1 timer is 500ms, so REGISTER transactions will start timing out. Tests IMS resilience to WAN-like latency on the signaling path.

## Faults Injected

- **network_latency** on `pcscf` — {'delay_ms': 5000, 'jitter_ms': 50}

## Baseline (Pre-Fault)

Stack phase before injection: **ready**
All containers running at baseline.

## Fault Propagation Verification

**Verdict:** ✅ `confirmed`

- **Wait:** 30s
- **Actual elapsed:** 30.0s
- **Nodes with significant deltas:** 1
- **Nodes with any drift:** 2

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

### Metrics Changes

| Node | Metric | Baseline | Current | Delta |
|------|--------|----------|---------|-------|
| pcscf | core:rcv_requests_register | 34.0 | 54.0 | 20.0 |

## Network Analysis (Phase 1)

**Summary:** The 5G SA + IMS network stack is healthy and operating normally in an idle state with two UEs registered.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | All data stores and support services are running and connected. |
| **ran** | 🟢 GREEN | gNB is connected to the core and both UEs are attached. |
| **core** | 🟢 GREEN | Core is healthy. UEs have active PDU sessions and the data plane is in a normal idle state. |
| **ims** | 🟢 GREEN | IMS is healthy. Both UEs are registered and ready; media plane is in a normal idle state. |

**Investigation hint:** No anomalies were detected across the network stack. All components report healthy status and metrics consistent with an idle network with two registered UEs. The system appears to be operating normally. If a problem is still suspected, further information would be needed about the specific user-visible symptoms, as the network itself shows no signs of a fault.

**Tools called:** get_vonr_components, get_network_topology, get_network_status, get_nf_metrics, get_dp_quality_gauges, check_stack_rules, compare_to_baseline


## Pattern Match (Phase 2)

**❌ Match:** No matching signature found

- **Confidence:** low
- **Failure domain:** unknown


## Investigation Instruction (Phase 3)

> No clear pattern or anomaly identified. The network analysis indicates that the 5G SA + IMS stack is currently healthy and operating normally in an idle state with two UEs registered, with all layers (Infrastructure, RAN, Core, IMS) showing green status. The UPF data plane is correctly observed to be near-zero, consistent with the `idle_data_plane_is_normal` stack rule. Despite this, since an issue is reported, perform a full bottom-up investigation: transport layer first using `measure_rtt` between components, then core network metrics (e.g., using `get_nf_metrics`, `get_dp_quality_gauges`), then application layer logs and state (e.g., `get_container_logs`, `kamcmd` for IMS components). Cite specific tool outputs for every claim to confirm the healthy state or uncover subtle anomalies not previously detected.

## Ground Truth

**Failure domain:** ims_signaling  
**Protocol impact:** SIP  
**Affected components:** pcscf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v5-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 118.4s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ```json
> {
>   "causes": [
>     {
>       "summary": "Extreme network latency (~5000ms RTT) isolated to the P-CSCF container is causing IMS service failures.",
>       "timeline": [
>         {
>           "timestamp": "T-0",
>           "description": "A transport-layer fault is introduced, affecting only the 'pcscf' container and causing all its outbound traffic to be delayed by approximately 5 seconds."
>         },
>         {
>           "timestamp": "T+1",
>           "description": "Network analysis tools report that all containers are 'running' and UEs are registered. This is based on existing state and does not detect the new transport-layer latency."
>         },
>         {
>           "timestamp": "T+2",
>           "description": "Any new SIP request arriving at the P-CSCF (e.g., an INVITE for a new call) is delayed by ~5000ms on its next hop to the I-CSCF."
>         },
>         {
>           "timestamp": "T+3",
>           "description": "The 5-second delay exceeds standard SIP transaction timers, causing the operation to time out. From the user's perspective, the call fails."
>         }
>       ],
>       "root_cause": "A transport-layer fault is causing extreme packet delay (~5000ms RTT) for all traffic originating from the `pcscf` container. This is not a software configuration issue within the P-CSCF application but a network-level problem specific to that container's environment. This latency is sufficient to cause virtually all SIP signaling transactions to time out, leading to failures for any new call setup or registration attempts.",
>       "affected_components": [
>         "pcscf"
>       ],
>       "recommendation": "The operator should verify the network path and performance for the `pcscf` container. Investigate the container's host for potential resource exhaustion or network virtualization misconfigurations (e.g., traffic shaping) that could be causing this isolated, high-latency condition. Comparing its network configuration to a healthy peer like the `icscf` is recommended.",
>       "confidence": "high",
>       "explanation": "The investigation confirmed a severe network performance degradation isolated to the P-CSCF container. Round-trip-time (RTT) measurements show an average latency of approximately 5000ms (5 seconds) from the P-CSCF to other core network components, while latency between other components remains normal (<1ms). This extreme delay is the root cause of service failures, as it will cause SIP signaling to time out before transactions can complete. The initial network analysis missed this because it only confirmed that components were running, not the quality of the underlying transport connections."
>     }
>   ]
> }
> ```

### Scoring Breakdown

**Overall score: 100%**

**Scorer assessment:** The agent provided an exceptionally accurate and detailed diagnosis, perfectly identifying the root cause, affected component, severity, and fault type with high confidence, directly matching the simulated P-CSCF latency failure.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | Yes | The agent correctly identified 'extreme network latency' on the P-CSCF as the root cause, matching the simulated failure mode of 'Elevated network latency on the P-CSCF's interfaces (5000ms delay)'. The agent even specified the observed RTT as ~5000ms, which aligns with the simulated observation. |
| Component overlap | 100% | The agent explicitly listed 'pcscf' as the affected component, which is precisely where the latency was injected. |
| Severity correct | Yes | The agent stated that the latency is 'sufficient to cause virtually all SIP signaling transactions to time out, leading to failures for any new call setup or registration attempts,' which accurately reflects the 'IMS registration failures at UEs' and 'SIP REGISTER 408 Request Timeout' symptoms of a complete service outage for affected transactions. |
| Fault type identified | Yes | The agent clearly identified the fault type as 'extreme network latency' and a 'transport-layer fault causing extreme packet delay,' which directly corresponds to the 'Elevated network latency' simulated failure mode. |
| Confidence calibrated | Yes | The agent's 'high' confidence is well-calibrated given the precise and accurate diagnosis, which perfectly matches the simulated failure and observable symptoms. The explanation provides clear evidence (RTT measurements). |

**Ranking position:** #1 — The agent provided only one diagnosis, which was correct.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 63,675 |
| Output tokens | 3,341 |
| Thinking tokens | 6,944 |
| **Total tokens** | **73,960** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| NetworkAnalystAgent | 34,379 | 7 | 3 |
| PatternMatcherAgent | 0 | 0 | 0 |
| InstructionGeneratorAgent | 5,457 | 0 | 1 |
| InvestigatorAgent | 25,067 | 5 | 3 |
| EvidenceValidatorAgent | 0 | 0 | 0 |
| SynthesisAgent | 9,057 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 160.1s
