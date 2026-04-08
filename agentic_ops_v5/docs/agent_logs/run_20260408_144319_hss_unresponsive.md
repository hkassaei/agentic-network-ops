# Episode Report: HSS Unresponsive

**Agent:** v5  
**Episode ID:** ep_20260408_143808_hss_unresponsive  
**Date:** 2026-04-08T14:38:08.839038+00:00  
**Duration:** 309.9s  

---

## Scenario

**Category:** network  
**Blast radius:** single_nf  
**Description:** Inject 60-second outbound delay on the HSS (PyHSS), making it functionally unreachable for all real-time protocols. The HSS container is running and the process is alive, but all network responses are delayed by 60 seconds — far exceeding Diameter Cx timeouts (5-30s) and standard probe timeouts (10s). From the perspective of diagnostic tools and IMS peers, the HSS appears completely unresponsive or unreachable.

## Faults Injected

- **network_latency** on `pyhss` — {'delay_ms': 60000, 'jitter_ms': 0}

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

### Metrics Changes

| Node | Metric | Baseline | Current | Delta |
|------|--------|----------|---------|-------|
| icscf | ims_icscf:lir_timeouts | 1.0 | 3.0 | 2.0 |
| icscf | cdp:timeout | 3.0 | 6.0 | 3.0 |
| icscf | ims_icscf:uar_timeouts | 2.0 | 3.0 | 1.0 |
| pcscf | script:register_failed | 0.0 | 1.0 | 1.0 |
| pcscf | sl:1xx_replies | 4.0 | 9.0 | 5.0 |
| pcscf | core:rcv_requests_options | 30.0 | 55.0 | 25.0 |
| pcscf | dialog_ng:processed | 0.0 | 3.0 | 3.0 |
| pcscf | core:rcv_requests_invite | 0.0 | 3.0 | 3.0 |
| pcscf | core:rcv_requests_register | 4.0 | 6.0 | 2.0 |
| pcscf | httpclient:connfail | 31.0 | 62.0 | 31.0 |
| rtpengine | owned_sessions | 0.0 | 3.0 | 3.0 |
| rtpengine | total_sessions | 0.0 | 3.0 | 3.0 |
| scscf | dialog_ng:processed | 0.0 | 3.0 | 3.0 |
| scscf | core:rcv_requests_invite | 0.0 | 3.0 | 3.0 |

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 1.00 (threshold: 0.70, trained on 50 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following specific metrics were flagged as the top contributors to the anomaly. These MUST be reflected in your layer ratings:

| Component | Metric | Current | Learned Normal | Severity |
|-----------|--------|---------|---------------|----------|
| pcscf | httpclient:connfail_rate | 1356.79 | 0.27 | HIGH |
| icscf | core:rcv_requests_invite_rate | 452.26 | 0.02 | HIGH |
| pcscf | core:rcv_requests_invite_rate | 452.26 | 0.04 | HIGH |
| scscf | core:rcv_requests_invite_rate | 452.26 | 0.04 | HIGH |
| pcscf | sl:1xx_replies_rate | 904.53 | 0.12 | HIGH |
| pcscf | core:rcv_requests_register_rate | 452.26 | 0.08 | HIGH |
| icscf | core:rcv_requests_register_rate | 452.26 | 0.08 | HIGH |
| upf | fivegs_ep_n3_gtp_indatapktn3upf_rate | 904.53 | 5.04 | HIGH |
| upf | fivegs_ep_n3_gtp_outdatapktn3upf_rate | 452.26 | 4.92 | HIGH |
| icscf | cdp:timeout | 6.00 | 0.00 | HIGH |

## Network Analysis (Phase 1)

**Summary:** The network has experienced a critical failure in the IMS layer, traced to the HSS being unreachable, which is preventing user registration and causing a stall in the data plane.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🔴 RED | HSS is running but non-responsive on the network, constituting an infrastructure failure. |
| **ran** | 🟢 GREEN | The Radio Access Network appears healthy. |
| **core** | 🟡 YELLOW | The 5G Core is functioning but the user plane is stalled due to upstream IMS failures. |
| **ims** | 🔴 RED | The IMS core is non-functional due to its inability to communicate with the HSS for subscriber authentication. |

**INFRASTRUCTURE evidence:**
- HSS container (pyhss) is unreachable from both I-CSCF and S-CSCF (100% packet loss in RTT measurements).
- Target 172.22.0.18 is UNREACHABLE from icscf.
- Target 172.22.0.18 is UNREACHABLE from scscf.

**CORE evidence:**
- UPF throughput is near-zero (in: 0.04 KB/s, out: 0.02 KB/s) despite active sessions and call attempts, indicating a data plane stall.
- Anomaly screener flagged high rates on UPF GTP data packets, which have now dropped to zero, indicating a recent failure.
- fivegs_ep_n3_gtp_indatapktn3upf_rate: 904.53 -> 0.1
- fivegs_ep_n3_gtp_outdatapktn3upf_rate: 452.26 -> 0.0

**IMS evidence:**
- I-CSCF is experiencing a high number of Diameter timeouts when trying to contact the HSS (cdp:timeout = 6, lir_timeouts = 3, uar_timeouts = 3).
- P-CSCF, I-CSCF, and S-CSCF are seeing massive spikes in SIP INVITE and REGISTER request rates, which are failing.
- core:rcv_requests_invite_rate at icscf: 452.26 (vs 0.02 normal)
- core:rcv_requests_register_rate at icscf: 452.26 (vs 0.08 normal)
- P-CSCF httpclient is failing to connect (httpclient:connfail_rate = 1356.79), the top-flagged anomaly.

**Suspect components:**

- **pyhss** (high): The HSS (pyhss) is the epicenter of the failure. It is completely unreachable from the I-CSCF and S-CSCF, causing Diameter timeouts and preventing all IMS user activity. RTT checks show 100% packet loss to its IP (172.22.0.18).
- **icscf** (medium): The I-CSCF is the primary victim of the HSS failure, exhibiting multiple Diameter timeouts (cdp:timeout=6). Its logs would contain direct evidence of the failed attempts to contact the HSS.
- **pcscf** (low): The P-CSCF was flagged by the anomaly screener for a very high rate of httpclient connection failures. This is assessed to be a downstream symptom of the primary HSS failure, as SIP transactions cannot proceed.

**Investigation hint:** The investigation should immediately focus on the HSS container, `pyhss`. Although `get_network_status` shows it as 'running', it is not responsive on the network to critical IMS components. Check the container's internal processes, logs (`docker logs pyhss`), and networking stack. The failure of `icscf` and `scscf` to ping `pyhss` is the most critical lead.

**Tools called:** get_vonr_components, get_network_topology, get_network_status, get_nf_metrics, get_dp_quality_gauges, read_env_config, measure_rtt, check_stack_rules, compare_to_baseline, get_causal_chain_for_component


## Pattern Match (Phase 2)

**❌ Match:** No matching signature found

- **Confidence:** low
- **Failure domain:** unknown
- **Baseline anomalies:** 2 metrics across 1 components


## Investigation Instruction (Phase 3)

> Anomalies detected in Infrastructure (RED) and IMS (RED) layers. The HSS (`pyhss`) is unreachable from critical IMS components, causing a complete IMS and data plane stall.
>
> Suspect components, in order of priority: `pyhss` (high confidence), `icscf` (medium confidence), `pcscf` (low confidence).
>
> Your PRIMARY investigation target is the HSS container, `pyhss`.
> FIRST: The `measure_rtt` tool has already confirmed 100% packet loss from `icscf` and `scscf` to `pyhss` (172.22.0.18). Though `get_network_status` reports `pyhss` as 'running', it is non-responsive on the network.
> Therefore, investigate the *internal* state and network stack of the `pyhss` container.
> 1.  Examine `pyhss` logs for errors, crashes, or any indications of internal failure preventing network responsiveness using `read_container_logs('pyhss')`.
> 2.  Hypothesize: Is the HSS application within the container hung, misconfigured, or has its network interface failed, despite the container process itself running?
>
> If `pyhss` internal issues are not found or fully explain the unreachability, SECONDARILY investigate `icscf`.
> 1.  Confirm the high rates of Diameter timeouts (e.g., `ims_icscf:lir_timeouts`, `ims_icscf:uar_timeouts`) using `get_nf_metrics('icscf')`.
> 2.  Examine `icscf` logs for specific error messages regarding HSS connection failures using `read_container_logs('icscf')`.
>
> The stalled UPF data plane and P-CSCF httpclient connection failures are likely downstream symptoms. Focus entirely on `pyhss` and `icscf` until the HSS unreachability and IMS failures are understood.
> Hierarchy of Truth: Transport > Core > Application. This investigation starts with the confirmed transport layer unreachability to the HSS, then moves to the HSS's internal application state, and then to affected IMS components like I-CSCF.

## Investigation (Phase 4)

> ### Hypothesis Verification
> - **Instruction received:** The primary investigation target is the HSS container, `pyhss`. I was instructed to investigate its internal state and network stack, starting with its logs, to understand why it is unresponsive on the network despite being in a 'running' state.
> - **Verdict:** CONFIRMED
>
> ### Evidence Chain
> - **Finding**: The `pyhss` container logs show no errors and indicate that its web server is running, but there is a complete absence of any Diameter protocol activity. This suggests the core Diameter service is hung or has failed to start.
> - **Evidence**: `[EVIDENCE: read_container_logs("pyhss") -> "172.22.0.1 - - [08/Apr/2026 10:38:08] \"GET /ims_subscriber/list HTTP/1.1\" 200 -"]`
> - **Significance**: This shows the container is running but the critical IMS service it's supposed to provide is non-functional, leading to a "silent failure".
>
> - **Finding**: The I-CSCF's Diameter peer list explicitly shows that the connection to the HSS is in a `Closed` state.
> - **Evidence**: `[EVIDENCE: run_kamcmd("icscf", "cdp.list_peers") -> "State: Closed"]`
> - **Significance**: This confirms from the client's (`icscf`) perspective that the communication link to the HSS is completely down, corroborating the unreachability reported in the initial analysis.
>
> - **Finding**: Logs from the I-CSCF reveal that it closed the Diameter connection to the HSS due to inactivity. Specifically, the HSS failed to respond to Diameter Watchdog Requests (DWRs), which are keep-alive messages.
> - **Evidence**: `[EVIDENCE: read_container_logs("icscf", "hss.ims.mnc001.mcc001.3gppnetwork.org") -> "WARNING: ... Inactivity on peer [hss.ims.mnc001.mcc001.3gppnetwork.org] and no DWA, Closing peer..."]`
> - **Significance**: This is the root cause of the `Closed` peer state. The HSS's Diameter application is not responding to network health checks from its peers, forcing them to terminate the connection. This directly explains the Diameter timeouts and the overall IMS stall.
>
> ### Layer Status
> - **Transport**: RED. While the `pyhss` container has an IP, the application process is not responding to Diameter traffic, effectively creating 100% packet loss at the application layer. The `icscf` logs confirm the HSS is not responding to watchdog keep-alives. `[EVIDENCE: read_container_logs("icscf", "hss.ims.mnc001.mcc001.3gppnetwork.org") -> "WARNING: ... Inactivity on peer [hss.ims.mnc001.mcc001.3gppnetwork.org] and no DWA, Closing peer..."]`
> - **Core**: YELLOW. The 5G Core itself is functional, but the data plane is stalled as a direct consequence of the IMS failure. User equipment cannot complete registration without a functional HSS, which in turn prevents the establishment of data sessions.
> - **Application**: RED. The IMS application layer is non-functional. The HSS, a critical component for authentication and user location, is unresponsive. This has caused the `icscf` to close its connection to the HSS, leading to cascading failures for all registration and session setup procedures. `[EVIDENCE: run_kamcmd("icscf", "cdp.list_peers") -> "State: Closed"]`
>
> ### Root Cause Assessment
> - **Primary cause**: The primary root cause is a silent failure of the Diameter service within the `pyhss` container. Although the container is running, the Diameter application is not responding to any network requests, including essential keep-alive messages (Diameter Watchdog). This has made the HSS a "black hole" on the network from the perspective of the IMS core.
> - **Confidence**: High
> - **Supporting evidence**: `[EVIDENCE: run_kamcmd("icscf", "cdp.list_peers") -> "State: Closed"]`, `[EVIDENCE: read_container_logs("icscf", "hss.ims.mnc001.mcc001.3gppnetwork.org") -> "WARNING: ... Inactivity on peer [hss.ims.mnc001.mcc001.3gppnetwork.org] and no DWA, Closing peer..."]`, `[EVIDENCE: read_container_logs("pyhss") -> "GET /ims_subscriber/list HTTP/1.1\" 200 -"]`

## Evidence Validation (Phase 5)

**Verdict:** clean
**Investigator confidence:** high
**Citations:** 9/9 verified

```
Evidence validation: 9/9 citations verified (0 unmatched). Investigator: 8 citations from 4 tool calls.
Verdict: clean. Investigator confidence: high.

Tool calls vs. citations:
  NetworkAnalystAgent:
    ✗ check_stack_rules — called but NOT cited in output
    ✗ compare_to_baseline — called but NOT cited in output
    ✗ get_causal_chain_for_component — called but NOT cited in output
    ✗ get_dp_quality_gauges — called but NOT cited in output
    ✗ get_network_status — called but NOT cited in output
    ✓ get_network_topology — called AND cited (1x)
    ✗ get_nf_metrics — called but NOT cited in output
    ✗ get_vonr_components — called but NOT cited in output
    ✗ measure_rtt — called but NOT cited in output
    ✗ read_env_config — called but NOT cited in output
  InvestigatorAgent:
    ✗ check_process_listeners — called but NOT cited in output
    ✓ read_container_logs — called AND cited (5x)
    ✗ read_running_config — called but NOT cited in output
    ✓ run_kamcmd — called AND cited (3x)
```

## Ground Truth

**Failure domain:** ims_signaling  
**Protocol impact:** Diameter  
**Affected components:** pyhss  
**Severity:** degraded

## Agent Diagnosis

**Model:** v5-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 175.3s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: A silent failure of the Diameter service within the Home Subscriber Server (HSS) container (`pyhss`) has caused a complete IMS outage and a stall in the 5G data plane.
> - **timeline**:
>     1.  The Diameter application process inside the `pyhss` container hangs or becomes unresponsive, while the container itself remains in a 'running' state.
>     2.  The HSS stops responding to Diameter Watchdog Request (DWR) keep-alive messages from the I-CSCF.
>     3.  The I-CSCF detects the prolonged inactivity and, after failing to receive a watchdog response (DWA), closes its Diameter peer connection to the HSS.
>     4.  UEs attempting to register with the network trigger SIP REGISTER requests that are forwarded to the I-CSCF.
>     5.  The I-CSCF is unable to query the now-disconnected HSS for authentication data, resulting in Diameter timeouts and failed user registrations.
>     6.  Without successful IMS registration, PDU sessions cannot be fully established, causing data throughput on the User Plane Function (UPF) to drop to zero.
> - **root_cause**: The Diameter service within the `pyhss` container has experienced a silent failure. While the container is running, the core application is non-responsive to network traffic. This was confirmed by the I-CSCF, which logged that it closed its connection to the HSS peer (`hss.ims.mnc001.mcc001.3gppnetwork.org`) due to "Inactivity... and no DWA". This single point of failure in the HSS has broken the IMS authentication chain, leading to a system-wide service outage.
> - **affected_components**:
>     - `pyhss`: Root Cause
>     - `icscf`: Symptomatic
>     - `upf`: Symptomatic
> - **recommendation**: The investigation should focus on confirming the hung state of the Diameter application within the `pyhss` container. An operator should inspect the container's internal processes and application-specific health metrics to verify the silent failure before taking any corrective action. The running state of the container is misleading.
> - **confidence**: high
> - **explanation**: The root cause of the outage is a "zombie" HSS. The `pyhss` container is running, but the critical Diameter service inside it has hung, making it a black hole for authentication requests. The I-CSCF correctly identified this failure when the HSS stopped responding to network keep-alives and severed the connection. This prevents all user registrations, which in turn stalls the 5G data plane, as no user sessions can be established.

### Scoring Breakdown

**Overall score: 100%**

**Scorer assessment:** The agent provided an excellent and highly accurate diagnosis, correctly identifying the root cause, affected component, severity, and fault type, with appropriate confidence.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | Yes | The agent correctly identified that the HSS's Diameter service was unresponsive/hung, leading to functional unreachability, which perfectly matches the simulated failure mode of extreme latency making it functionally unreachable for real-time protocols. |
| Component overlap | 100% | The agent explicitly named 'pyhss' (HSS) as the root cause component. |
| Severity correct | Yes | The agent described the impact as a 'complete IMS outage and a stall in the 5G data plane' and 'system-wide service outage', which accurately reflects the severity of the HSS being functionally unreachable. |
| Fault type identified | Yes | The agent identified the fault type as the Diameter service being 'hung or becomes unresponsive' and the 'core application is non-responsive to network traffic', which aligns with the observable 'unresponsive' or 'unreachable' state caused by the extreme delay. |
| Confidence calibrated | Yes | The agent's 'high' confidence is well-calibrated given the accuracy and detail of its diagnosis, which correctly inferred the application-level unresponsiveness despite the container running. |

**Ranking position:** #1 — The agent provided a single, clear root cause, placing it as the primary diagnosis.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 165,303 |
| Output tokens | 4,328 |
| Thinking tokens | 10,167 |
| **Total tokens** | **179,798** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| NetworkAnalystAgent | 83,617 | 16 | 6 |
| PatternMatcherAgent | 0 | 0 | 0 |
| InstructionGeneratorAgent | 7,066 | 0 | 1 |
| InvestigatorAgent | 79,309 | 5 | 6 |
| EvidenceValidatorAgent | 0 | 0 | 0 |
| SynthesisAgent | 9,806 | 0 | 1 |


## Post-Run Analysis

### Layer Misattribution: HSS categorized as "infrastructure" instead of "ims"

In the Phase 1 Network Analysis, the agent rated the **infrastructure** layer RED with the rationale: *"HSS is running but non-responsive on the network, constituting an infrastructure failure."* However, the ontology explicitly assigns `pyhss` to the **ims** layer (`layer: ims`, `role: subscriber-db`, `subsystem: IMS Subscriber DB`), and the network analyst prompt itself lists HSS under the IMS layer: *"ims — IMS functions in scope (typically P-CSCF, I-CSCF, S-CSCF, HSS, RTPEngine)"*.

**Root cause of the misattribution:** The LLM (Gemini Flash) conflated the *nature of the failure* (network/transport-level unreachability) with the *layer of the component*. It observed that HSS was unreachable at the network level (100% packet loss from I-CSCF and S-CSCF), and made the cognitive leap that "network unreachability = infrastructure problem." In reality, a component in the IMS layer can suffer a network-level failure — that doesn't move it to the infrastructure layer. The agent should have rated only the **ims** layer RED for the HSS failure, and left **infrastructure** GREEN (since MongoDB, MySQL, and DNS — the actual infrastructure components — were unaffected).

**Impact on diagnosis:** None. The agent correctly identified `pyhss` as the root cause, diagnosed the Diameter silent failure, and traced the full cascading impact chain. The layer misattribution is a cosmetic error in the status table, not a diagnostic failure.

**Suggested mitigations:**
1. **Stronger prompt guardrails** — Add explicit language: *"Rate each component under its ontology layer, NOT under the layer that matches the failure symptom. A network-level failure of an IMS component is still an IMS-layer problem."*
2. **Structured enforcement** — Have the code validate that layer ratings only reference components that `get_vonr_components` assigned to that layer, and flag misattributions before the report is finalized.
3. **Post-hoc validation** — Add a scoring penalty when the agent attributes a component to a layer that contradicts the ontology.

## Resolution

**Heal method:** scheduled  
**Recovery time:** 309.9s
