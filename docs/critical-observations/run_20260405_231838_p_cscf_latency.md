# Episode Report: P-CSCF Latency

**Agent:** v5  
**Episode ID:** ep_20260405_231621_p_cscf_latency  
**Date:** 2026-04-05T23:16:21.662611+00:00  
**Duration:** 136.3s  

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
| pcscf | sl:1xx_replies | 8.0 | 10.0 | 2.0 |
| pcscf | core:rcv_requests_register | 10.0 | 30.0 | 20.0 |

## Network Analysis (Phase 1)

**Summary:** The network is healthy and operational, with UEs registered and all services ready, but is currently idle with no active calls.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | All infrastructure components (mongo, mysql, dns) are running and connected. |
| **ran** | 🟢 GREEN | gNB is connected to the AMF and 2 UEs are attached. |
| **core** | 🟢 GREEN | All 5G Core NFs are running, and 2 UEs have active PDU sessions. The data plane is idle, which is normal as no call is in progress. |
| **ims** | 🟢 GREEN | All IMS components are running, and 2 UEs are registered. The media plane is idle, which is normal as no call is in progress. |

**Investigation hint:** The network appears to be fully healthy. All components are running, UEs are registered across both the 5G core and IMS, and all network links are active. The data and media planes show zero traffic, but this is the expected behavior as there are no active voice calls in progress. The issue reported by the operator is not currently manifesting in the network's health metrics. It's possible the issue was transient or requires an active test call to reproduce.

**Tools called:** get_vonr_components, get_network_topology, get_network_status, get_nf_metrics, get_dp_quality_gauges, check_stack_rules, compare_to_baseline


## Pattern Match (Phase 2)

**❌ Match:** No matching signature found

- **Confidence:** low
- **Failure domain:** unknown


## Investigation Instruction (Phase 3)

> No clear pattern or anomaly has been identified; the network is currently reporting as fully healthy, with all components running and UEs registered in both 5G Core and IMS. The data and media planes are idle, which is expected as no calls are in progress. It's possible the reported issue was transient or requires an active test call to manifest.
>
> Your task is to perform a full bottom-up investigation to diagnose any latent or transient issues.
>
> 1.  **Transport Layer (Priority 1):** Verify connectivity and latency between all critical NFs (e.g., gNB to AMF, AMF to SMF, SMF to UPF, IMS components). Use `measure_rtt <source> <destination>` for critical links.
> 2.  **Core Layer (Priority 2):** Re-examine core network function metrics for any unusual historical spikes or recent anomalies not captured in the current snapshot. Pay attention to `fivegs_smffunction_sm_sessionnbr`, `pfcp_sessions_active`, `ues_active`, and all `cdp` (Diameter) and `ims_auth` (Diameter) metrics, specifically looking for any `timeout` increases that might have occurred in the recent past even if currently zero. Use `get_nf_metrics <nf_name>` and consider historical data if available.
> 3.  **Application Layer (Priority 3 - IMS/VoNR specific):** Review IMS component logs (`icscf`, `scscf`, `pcscf`, `rtpengine`, `pyhss`) for any errors or warnings that occurred around the time the user reported the issue, especially looking for failed registrations (`ims_registrar_scscf:rejected_regs`) or issues with `script:register_failed`. Check `kamcmd` output for active IMS transactions if any are initiated.
>
> **Crucial Note:** If an active test call is feasible, initiate one and monitor all relevant KPIs and logs in real-time to reproduce the issue and identify the failure point. Cite tool outputs for every claim.

## Ground Truth

**Failure domain:** ims_signaling  
**Protocol impact:** SIP  
**Affected components:** pcscf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v5-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 95.1s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: Critical transport layer failures are preventing communication on essential network paths, specifically between the AMF and gNB, and between the P-CSCF and I-CSCF, rendering both 5G Core and IMS services non-functional.
> - **timeline**:
>     1.  A transport layer fault occurs, isolating key network functions.
>     2.  The AMF attempts to communicate with the gNB over the N2 interface but fails due to 100% packet loss. This prevents any UEs from attaching or maintaining a connection to the 5G Core.
>     3.  Simultaneously, the P-CSCF, which serves as the IMS entry point, attempts to forward SIP messages to the I-CSCF but also fails due to 100% packet loss.
>     4.  As a result, no 5G sessions can be established, and no IMS registrations or calls can be processed, despite all individual containers reporting a "running" status.
> - **root_cause**: The root cause is a transport layer failure, resulting in 100% packet loss on two critical communication paths.
>     - **Causal Chain 1 (5G Core)**: `AMF -> gNB` connectivity is broken. Evidence shows `measure_rtt("amf", "172.22.0.37") -> "100% packet loss"`. This severs the N2 interface, making UE attachment impossible.
>     - **Causal Chain 2 (IMS Core)**: `P-CSCF -> I-CSCF` connectivity is broken. Evidence shows `measure_rtt("pcscf", "172.22.0.19") -> "100% packet loss"`. This severs the Mw interface, making IMS registration and call setup impossible.
> - **affected_components**:
>     - amf
>     - gNB (at IP 172.22.0.37)
>     - pcscf
>     - icscf
> - **recommendation**: Investigate the underlying virtual network fabric connecting the containers. Check for misconfigured network policies, firewall rules (`iptables`), or virtual switch/bridge settings that could be dropping packets between the AMF and gNB, and between the P-CSCF and I-CSCF. Correct the routing or firewall rules to restore connectivity.
> - **confidence**: high
> - **explanation**: The initial analysis indicating a healthy network was incorrect. A detailed transport layer investigation revealed critical connectivity failures. The AMF cannot reach the gNB, which prevents UEs from attaching to the 5G network. In parallel, the P-CSCF cannot reach the I-CSCF, which breaks all IMS services, including VoNR. These failures are due to 100% packet loss on these specific routes, pointing to a network configuration issue rather than a problem with the network function applications themselves.

### Scoring Breakdown

**Overall score: 25%**

**Scorer assessment:** The agent correctly identified the P-CSCF as an affected component but fundamentally misdiagnosed the type of fault (packet loss instead of latency) and incorrectly identified an additional, non-existent fault path, leading to an inaccurate severity assessment and poor confidence calibration.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | No | The simulated failure was P-CSCF latency (500ms/5000ms delay). The agent diagnosed '100% packet loss' on the P-CSCF to I-CSCF path, which is incorrect. Furthermore, it incorrectly identified a second root cause of '100% packet loss' between AMF and gNB, which was not part of the simulated failure. |
| Component overlap | 100% | The agent correctly identified 'pcscf' as an affected component. It also listed 'icscf' which would be a cascading effect. While it incorrectly listed 'amf' and 'gNB', the primary affected component was named. |
| Severity correct | No | The simulated failure was latency, leading to degradation and timeouts. The agent diagnosed '100% packet loss' and 'non-functional' services, which implies a complete outage, a much higher severity than the actual latency-induced degradation. |
| Fault type identified | No | The simulated fault type was 'latency'. The agent identified '100% packet loss', which is a different observable class of failure. |
| Confidence calibrated | No | The agent stated 'high' confidence despite a largely incorrect diagnosis regarding the type of fault, its extent, and its severity. This indicates poor calibration. |

**Ranking:** The agent provided a single primary diagnosis, which was incorrect.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 60,810 |
| Output tokens | 3,306 |
| Thinking tokens | 6,028 |
| **Total tokens** | **70,144** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| NetworkAnalystAgent | 33,184 | 7 | 3 |
| PatternMatcherAgent | 0 | 0 | 0 |
| InstructionGeneratorAgent | 4,983 | 0 | 1 |
| InvestigatorAgent | 24,080 | 7 | 3 |
| EvidenceValidatorAgent | 0 | 0 | 0 |
| SynthesisAgent | 7,897 | 0 | 1 |


## Resolution

**Heal method:** scheduled
**Recovery time:** 136.3s

## Post-Run Analysis

### Score: 25% — latency misdiagnosed as total connectivity failure

With 5000ms delay (up from 500ms in the previous run), the symptoms were far more dramatic, but the agent performed *worse*. Here's why.

### The chaos framework generated clear, visible symptoms

The **Symptoms Observed** section shows damning evidence the agent had available:

| Node | Metric | Baseline | Current | Delta |
|------|--------|----------|---------|-------|
| pcscf | `core:rcv_requests_register` | 10 | 30 | **+20** |
| pcscf | `sl:1xx_replies` | 8 | 10 | **+2** |

20 new REGISTER requests at the P-CSCF in 30 seconds. The UEs sent 2 re-registrations (triggered by `ControlPlaneTrafficAgent`), but with 5000ms delay on every outgoing packet, the SIP retransmission timer (T1=500ms) fires repeatedly because the 200 OK never comes back in time. Those 20 REGISTERs are the UEs hammering retransmissions. Only 2 provisional 1xx replies got out. `sl:200_replies` didn't even appear in the delta — zero successful registrations. **This is a screaming obvious symptom.**

### Issue 1 — NetworkAnalyst AGAIN rated everything GREEN

Despite `core:rcv_requests_register` exploding from 10→30 and `sl:200_replies` not budging, the NetworkAnalyst says: *"The network is healthy and operational... 2 UEs are registered."*

Same root cause as the 500ms run: the prompt has zero guidance on interpreting kamcmd SIP transaction counters. It looked at the cached `ims_usrloc_pcscf:registered_contacts=2` (stale from before the fault) and concluded IMS was green. The 20 retransmissions visible in `core:rcv_requests_register` were ignored.

### Issue 2 — `measure_rtt` misinterpreted as "100% packet loss"

The Investigator ran `measure_rtt("pcscf", "172.22.0.19")` (P-CSCF → I-CSCF). With 5000ms outgoing delay, `ping`'s default timeout (~2 seconds, from the tool's `ping -c 3 -W 2` invocation) expires before the packet even leaves the container. `ping` reports "100% packet loss" — but packets aren't lost, they're delayed beyond the timeout.

The Investigator then concluded:
> **Causal Chain 1 (5G Core):** `AMF -> gNB` connectivity is broken. Evidence: `measure_rtt("amf", "172.22.0.37") -> "100% packet loss"`
> **Causal Chain 2 (IMS Core):** `P-CSCF -> I-CSCF` connectivity is broken. Evidence: `measure_rtt("pcscf", "172.22.0.19") -> "100% packet loss"`

The P-CSCF → I-CSCF "loss" is actually extreme latency (correct path, wrong diagnosis). But the **AMF → gNB "100% packet loss" is completely fabricated** — AMF has no tc rules, its RTT to gNB should be <1ms. Either the agent ran this from the wrong container (pcscf instead of amf), or it hallucinated the evidence entirely.

This led to the final diagnosis: *"100% packet loss on two critical communication paths, rendering both 5G Core and IMS services non-functional."* In reality, only the P-CSCF had elevated latency; the AMF-gNB path was fine.

### Issue 3 — InstructionGenerator still suggests impossible actions

The instruction again says:
> If an active test call is feasible, initiate one and monitor all relevant KPIs and logs in real-time...

Same prompt gap as the 500ms run — no prohibition on suggesting state-changing actions.

### The `measure_rtt` tool design flaw

The underlying `measure_rtt` implementation uses `ping -c 3 -W 2` (3 packets, 2-second timeout). Any latency above 2000ms will report as "100% packet loss" even if the packets would eventually arrive. The tool cannot distinguish between:
- Actual packet loss (packets dropped)
- Extreme latency (packets arrive after timeout)

For a diagnostic tool used by an RCA agent, this ambiguity is dangerous. Options:
1. Increase the timeout (e.g., `-W 10`) so latency up to 10s is measured, not misreported as loss
2. Have the tool explicitly state "packets may be delayed beyond timeout" when 100% loss is reported
3. Add a second measurement with a longer timeout when the first shows 100% loss

### Fixes needed

| Problem | Fix location | What to do |
|---|---|---|
| NetworkAnalyst blind to kamcmd SIP transaction counters | `network_analyst.md` | Add IMS SIP transaction analysis: "compare `core:rcv_requests_register` delta to `sl:200_replies` delta — large gap = registrations failing" |
| `measure_rtt` reports extreme latency as "100% packet loss" | `agentic_ops_v5/tools/reachability.py` or underlying `_t.measure_rtt` | Increase ping timeout to 10s, or add a follow-up probe when 100% loss is detected |
| Investigator may have fabricated AMF→gNB evidence | `investigator.md` | The prompt already says "do not hallucinate evidence" but the LLM still does. May need stronger enforcement in EvidenceValidatorAgent |
| InstructionGenerator suggests placing calls | `instruction_generator.md` | Add: "You are a passive observer. Never suggest state-changing actions." |
| Scorer gave 100% to diagnosis that named `tc netem` (previous run) | `agentic_chaos/scorer.py` | Consider penalizing mechanism leakage |
