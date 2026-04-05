# Episode Report: P-CSCF Latency

**Agent:** v5  
**Episode ID:** ep_20260405_014922_p_cscf_latency  
**Date:** 2026-04-05T01:49:22.947082+00:00  
**Duration:** 173.1s  

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

## Network Analysis (Phase 1)

**Summary:** The network's control plane is operational with UEs registered, but the user plane is down, preventing any data or voice traffic from flowing.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | All infrastructure components are running and connected. |
| **ran** | 🟢 GREEN | gNB is connected and 2 UEs are attached. |
| **core** | 🔴 RED | The UPF is not forwarding any user plane traffic, indicating a complete data plane failure. |
| **ims** | 🔴 RED | The IMS media plane is non-functional as a downstream consequence of the UPF failure. P-CSCF is also logging a high rate of HTTP connection failures. |

**CORE evidence:**
- upf_kbps_in=0.0, upf_kbps_out=0.0 with 4 active sessions (from get_dp_quality_gauges)
- UPF lifetime packet loss > 55% (in: 2819, out: 1251) (from get_nf_metrics)

**IMS evidence:**
- rtpengine_pps=0.0 (from get_dp_quality_gauges), indicating no media traffic is flowing.
- pcscf_http_connfail=725 and pcscf_http_connok=0 (from get_nf_metrics)

**Suspect components:**

- **upf** (high): UPF shows 0 packets/sec throughput despite having 4 active PDU sessions. Lifetime metrics show over 55% of incoming packets were dropped (in:2819, out:1251). This indicates a total failure of the user plane forwarding function.
- **pcscf** (low): P-CSCF is reporting a high number of HTTP client connection failures (725) and zero successful connections. While the control plane appears to be working for registrations, this indicates a potential issue with a secondary interface, possibly for policy (Rx) or charging.

**Investigation hint:** Focus investigation on the UPF immediately. The data plane is completely stalled. Analyze UPF logs and internal state to understand why it is not forwarding packets for its active sessions. The massive packet loss observed in historical metrics is the strongest lead.

**Tools called:** get_vonr_components, get_network_topology, get_network_status, get_nf_metrics, get_dp_quality_gauges, compare_to_baseline, check_stack_rules, check_component_health


## Pattern Match (Phase 2)

**❌ Match:** No matching signature found

- **Confidence:** low
- **Failure domain:** unknown


## Investigation Instruction (Phase 3)

> INVESTIGATE: Core and IMS layers are RED.
>
> **CRITICAL**: UPF (core layer) is the primary suspect; the data plane is completely stalled. It shows `upf_kbps_in=0.0, upf_kbps_out=0.0` despite 4 active PDU sessions and has massive lifetime packet loss (>55%, in: 2819, out: 1251). This indicates a total failure of the user plane forwarding function (GTP-U).
>
> **IMMEDIATE ACTION**: Focus exclusively on the UPF.
> 1.  **Transport Layer First**: Verify UPF transport connectivity using `measure_rtt` to the UPF.
> 2.  **Component Health**: Use `check_component_health` specifically for the UPF container.
> 3.  **UPF Specifics**: Analyze UPF logs and internal state to determine why GTP-U forwarding is failing for active sessions. Examine `get_nf_metrics` for the UPF (specifically `fivegs_ep_n3_gtp_indatapktn3upf`, `fivegs_ep_n3_gtp_outdatapktn3upf`).
>
> **Secondary Issue**: P-CSCF (IMS layer) is reporting `pcscf_http_connfail=725` and `pcscf_http_connok=0`. This indicates a problem with a secondary interface, possibly for policy (Rx) or charging. RTPengine shows `rtpengine_pps=0.0`, which is a downstream consequence of the UPF failure. After addressing the UPF, investigate P-CSCF HTTP connectivity using `check_component_health` for P-CSCF and P-CSCF logs for specific HTTP client errors.
>
> **Hierarchy of Truth Reminder**: Always check the transport layer first for any component you are investigating. Do NOT investigate RAN or Infrastructure as they are GREEN.

## Ground Truth

**Failure domain:** ims_signaling  
**Protocol impact:** SIP  
**Affected components:** pcscf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v5-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 158.8s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: The UPF is in a "zombie" state, running and connected but silently dropping 100% of user plane packets, causing a complete data plane outage.
>   - **timeline**:
>     1.  The 5G control plane successfully establishes 4 PDU sessions for 2 UEs, instructing the UPF to create data plane tunnels.
>     2.  The UPF accepts the control plane instructions but fails to forward any GTP-U user plane packets.
>     3.  Initial packets entering the UPF from the RAN are dropped, as evidenced by lifetime metrics showing 2819 packets in but only 1251 out (>55% loss). During the incident, this drop rate became 100%.
>     4.  The lack of a data path causes all user data and IMS media (VoNR) traffic to fail, reflected by `rtpengine_pps=0.0`.
>     5.  The P-CSCF logs HTTP connection failures, likely a secondary effect of being unable to reach a policy or charging function over the dead data plane.
>   - **root_cause**: The UPF has experienced a critical failure of its packet forwarding function. The investigation confirmed the UPF container is running and reachable via the network, but it is not processing any packets. The failure is silent (no error logs) and absolute (zero throughput), which points to a severe internal state corruption or a critical misconfiguration that was not caught on startup. The investigator's inability to read the component's configuration file further supports the conclusion that the component is in a non-functional, unrecoverable state.
>   - **affected_components**: `upf`, `rtpengine`, `pcscf`
>   - **recommendation**: Restart the `upf` container to force it to clear its corrupted state and reload its configuration.
>   - **confidence**: high
>   - **explanation**: The Network Analyst's initial suspicion of the UPF was correct. All evidence points to a complete and silent failure of the UPF's data plane forwarding logic. The control plane is working correctly, creating sessions, but the UPF is a black hole for the resulting user traffic. Our investigation ruled out network connectivity issues or a simple process crash. The component is running but internally broken, a state from which a restart is the only reliable recovery method. All other alerts, such as those from the IMS layer, are direct consequences of this core data plane collapse.

### Scoring Breakdown

**Overall score: 25%**

**Scorer assessment:** The agent completely missed the actual P-CSCF latency issue, instead diagnosing a severe UPF data plane outage with high confidence, despite correctly listing P-CSCF as an affected component.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | No | The simulated failure was 500ms latency on the P-CSCF. The agent diagnosed a critical failure of the UPF's packet forwarding function, leading to 100% packet loss. These are entirely different components and failure modes. |
| Component overlap | 100% | The primary affected component in the simulated failure is 'pcscf'. The agent lists 'pcscf' in its 'affected_components' list. While the agent misattributes the reason for P-CSCF's affection (secondary effect of UPF failure), the component itself is named. |
| Severity correct | No | The simulated failure is a 500ms latency, which is a degradation. The agent diagnosed a 'complete data plane outage' with '100% packet loss' and 'zero throughput', which is a much higher severity (outage). |
| Fault type identified | No | The simulated fault type is latency/delay. The agent identified a 'component unreachable' / '100% packet loss' / 'silent dropping' type of fault, which is incorrect. |
| Confidence calibrated | No | The agent stated 'high' confidence for a diagnosis that is incorrect across all key dimensions (root cause, severity, fault type). This indicates poor calibration. |

**Ranking:** The agent provided only one diagnosis, which was incorrect.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 135,238 |
| Output tokens | 3,069 |
| Thinking tokens | 9,036 |
| **Total tokens** | **147,343** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| NetworkAnalystAgent | 57,414 | 11 | 6 |
| PatternMatcherAgent | 0 | 0 | 0 |
| InstructionGeneratorAgent | 5,241 | 0 | 1 |
| InvestigatorAgent | 78,153 | 10 | 9 |
| SynthesisAgent | 6,535 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 173.1s
