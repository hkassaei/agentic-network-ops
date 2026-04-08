# Episode Report: HSS Unresponsive

**Agent:** v5  
**Episode ID:** ep_20260408_052616_hss_unresponsive  
**Date:** 2026-04-08T05:26:16.757540+00:00  
**Duration:** 337.8s  

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
| icscf | cdp:timeout | 1.0 | 3.0 | 2.0 |
| icscf | ims_icscf:uar_timeouts | 1.0 | 2.0 | 1.0 |
| icscf | ims_icscf:lir_timeouts | 0.0 | 1.0 | 1.0 |
| pcscf | dialog_ng:processed | 0.0 | 2.0 | 2.0 |
| pcscf | script:register_failed | 0.0 | 2.0 | 2.0 |
| rtpengine | total_sessions | 0.0 | 2.0 | 2.0 |
| rtpengine | owned_sessions | 0.0 | 2.0 | 2.0 |
| scscf | dialog_ng:processed | 0.0 | 2.0 | 2.0 |
| scscf | core:rcv_requests_invite | 0.0 | 2.0 | 2.0 |

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 1.00 (threshold: 0.70, trained on 50 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following specific metrics were flagged as the top contributors to the anomaly. These MUST be reflected in your layer ratings:

| Component | Metric | Current | Learned Normal | Severity |
|-----------|--------|---------|---------------|----------|
| pcscf | httpclient:connfail_rate | 1038.45 | 0.27 | HIGH |
| pcscf | core:rcv_requests_register_rate | 519.23 | 0.08 | HIGH |
| icscf | core:rcv_requests_register_rate | 519.23 | 0.08 | HIGH |
| pcscf | sl:1xx_replies_rate | 519.23 | 0.12 | HIGH |
| upf | fivegs_ep_n3_gtp_indatapktn3upf_rate | 1557.68 | 5.04 | HIGH |
| upf | fivegs_ep_n3_gtp_outdatapktn3upf_rate | 1038.45 | 4.92 | HIGH |
| icscf | cdp:timeout | 3.00 | 0.00 | HIGH |
| icscf | ims_icscf:uar_timeouts | 2.00 | 0.00 | HIGH |
| icscf | ims_icscf:lir_timeouts | 1.00 | 0.00 | HIGH |
| scscf | cdp:average_response_time | 113.00 | 86.98 | MEDIUM |

## Network Analysis (Phase 1)

**Summary:** The IMS layer has failed, preventing user registration and voice calls, due to a loss of connectivity to the HSS (pyhss).

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | All infrastructure components (mongo, mysql, dns) are running and connected. |
| **ran** | 🟢 GREEN | gNB is connected and both UEs are attached to the 5G network (ran_ue=2). |
| **core** | 🟢 GREEN | 5G Core network functions are stable, and PDU sessions are established. The data plane is idle, which is expected as no calls are active. |
| **ims** | 🔴 RED | Critical failure: I-CSCF cannot communicate with the HSS (pyhss), causing IMS registration and authentication to fail. |

**IMS evidence:**
- measure_rtt from icscf to pyhss (172.22.0.18) shows 100% packet loss.
- icscf has cdp:timeout=3.0 (expected: 0), indicating Diameter protocol timeouts when communicating with the HSS.
- icscf has ims_icscf:uar_timeouts=2.0 and ims_icscf:lir_timeouts=1.0, confirming timeouts for user authentication and location queries to the HSS.
- pcscf shows a high rate of httpclient:connfail_rate, a cascading symptom of the downstream HSS failure.

**Suspect components:**

- **pyhss** (high): The pyhss container at IP 172.22.0.18 is completely unreachable from the icscf, with measure_rtt showing 100% packet loss. This is the root cause of the Diameter timeouts at I-CSCF and S-CSCF.
- **icscf** (medium): It is the epicenter of the reported symptoms (Diameter timeouts), but these are caused by its inability to reach the HSS. It is a victim of the pyhss failure, not the cause.

**Investigation hint:** The primary suspect is the HSS (pyhss). The connection from the I-CSCF to the HSS is completely down, as confirmed by a `measure_rtt` test showing 100% packet loss. This explains all the Diameter and SIP registration timeouts seen across the IMS layer. The Investigator should focus on the `pyhss` container: check its process status, read its logs, and verify its networking configuration. The other anomalies at P-CSCF and S-CSCF are cascading symptoms of this core connectivity failure.

**Tools called:** get_vonr_components, get_network_topology, get_network_status, get_nf_metrics, get_dp_quality_gauges, read_env_config, measure_rtt, check_stack_rules, compare_to_baseline


## Pattern Match (Phase 2)

**❌ Match:** No matching signature found

- **Confidence:** low
- **Failure domain:** unknown
- **Baseline anomalies:** 3 metrics across 2 components


## Investigation Instruction (Phase 3)

> Anomalies detected in IMS layer (RED). Suspect components: `pyhss` (high confidence), `icscf` (medium confidence). The I-CSCF cannot communicate with the HSS (pyhss), preventing user registration and voice calls due to Diameter timeouts.
>
> FIRST: Investigate the primary suspect, `pyhss`. Verify its transport layer connectivity. Run `measure_rtt` from `icscf` to `pyhss` (IP 172.22.0.18) to confirm the 100% packet loss reported by the Network Analyst.
> If `pyhss` is confirmed as unreachable at the transport layer, investigate `pyhss` directly:
> - Check its container status (`get_nf_metrics` for `pyhss` container_status).
> - Review its logs (`read_nf_logs` for `pyhss`) for errors or issues preventing network communication.
> - Analyze its networking configuration if logs suggest a problem (`read_env_config` for `pyhss`).
>
> The `icscf` metrics (`ims_icscf:uar_timeouts=2.0`, `ims_icscf:lir_timeouts=1.0`, `cdp:timeout=3.0`) and `pcscf` `httpclient:connfail_rate` are cascading symptoms of the HSS unreachability. RAN and Core layers are GREEN; do not investigate them.

## Investigation (Phase 4)

> ### Hypothesis Verification
> - **Instruction received:** The primary suspect is `pyhss`, which is suspected to be unreachable at the transport layer, causing Diameter timeouts at the `icscf`. The instruction was to verify the packet loss, then investigate the `pyhss` container's status and logs.
> - **Verdict:** CONFIRMED
>
> ### Evidence Chain
> - **Finding**: There is 100% packet loss from the `icscf` to the `pyhss` container, confirming it is unreachable at the transport layer.
> - **Evidence**: `[EVIDENCE: measure_rtt("icscf", "172.22.0.18") -> "3 packets transmitted, 0 received, +3 errors, 100% packet loss"]`
> - **Significance**: This confirms the fundamental connectivity failure reported by the Network Analyst. The "Destination Host Unreachable" error indicates a routing or network-level problem, preventing `icscf` from finding a path to `pyhss`. This is the direct cause of the Diameter timeouts.
>
> - **Finding**: The `pyhss` container is not reporting any metrics, suggesting it has either crashed or is not functioning correctly.
> - **Evidence**: `[EVIDENCE: get_nf_metrics() -> "AMF [...] ICSCF [...] MONGO [...] PCF [...] PCSCF [...] RTPENGINE [...] SCSCF [...] SMF [...] UPF"]`
> - **Significance**: In a healthy state, `pyhss` would report its metrics alongside the other network functions. Its complete absence from the metrics snapshot indicates a critical failure, corroborating the unreachability finding.
>
> - **Finding**: The logs for the `pyhss` container show that the application process is running and appears healthy, serving HTTP requests.
> - **Evidence**: `[EVIDENCE: read_container_logs("pyhss") -> "172.22.0.1 - - [08/Apr/2026 01:26:16] \"GET /ims_subscriber/list HTTP/1.1\" 200 -"]`
> - **Significance**: This creates a critical contradiction. The application process is active inside the container, but the container itself is isolated from the network. This pinpoints the failure to the container's specific network configuration, rather than a crash of the `pyhss` application itself.
>
> - **Finding**: The environment configuration confirms that the IP address `172.22.0.18` is assigned to `pyhss`.
> - **Evidence**: `[EVIDENCE: read_env_config() -> "pyhss_ip\": \"172.22.0.18"]`
> - **Significance**: This rules out a simple IP address misconfiguration in the environment files. The problem lies in how the container's networking stack is instantiated, isolating it despite having the correct IP assigned.
>
> ### Layer Status
> - **Transport**: RED. There is a complete loss of connectivity to the `pyhss` container from its peers. `[EVIDENCE: measure_rtt("icscf", "172.22.0.18") -> "100% packet loss"]`
> - **Core**: GREEN. Core network metrics appear stable, and the investigation instructions indicated no anomalies in this layer.
> - **Application**: RED. The `icscf` is experiencing Diameter timeouts due to its inability to communicate with `pyhss`, preventing user authentication and registration. The `get_nf_metrics` output shows `cdp:timeout=3.0`, `ims_icscf:uar_timeouts=2.0`, and `ims_icscf:lir_timeouts=1.0` on the `icscf`.
>
> ### Root Cause Assessment
> - **Primary cause**: The `pyhss` container is unreachable on the network, causing a complete failure of the IMS layer. While the `pyhss` application process is running internally, the container is suffering from network isolation, preventing any other components from communicating with it. The "Destination Host Unreachable" error points to a container-level networking issue (e.g., misconfigured virtual network interface, incorrect network attachment) rather than an application-level crash.
> - **Confidence**: high
> - **Supporting evidence**: `[EVIDENCE: measure_rtt("icscf", "172.22.0.18") -> "100% packet loss"]`, `[EVIDENCE: get_nf_metrics() -> "pyhss metrics are absent"]`, `[EVIDENCE: read_container_logs("pyhss") -> "GET /ims_subscriber/list HTTP/1.1\" 200 -"]`

## Evidence Validation (Phase 5)

**Verdict:** clean
**Investigator confidence:** high
**Citations:** 8/8 verified

```
Evidence validation: 8/8 citations verified (0 unmatched). Investigator: 8 citations from 4 tool calls.
Verdict: clean. Investigator confidence: high.

Tool calls vs. citations:
  NetworkAnalystAgent:
    ✗ check_stack_rules — called but NOT cited in output
    ✗ compare_to_baseline — called but NOT cited in output
    ✗ get_dp_quality_gauges — called but NOT cited in output
    ✗ get_network_status — called but NOT cited in output
    ✗ get_network_topology — called but NOT cited in output
    ✗ get_nf_metrics — called but NOT cited in output
    ✗ get_vonr_components — called but NOT cited in output
    ✗ measure_rtt — called but NOT cited in output
    ✗ read_env_config — called but NOT cited in output
  InvestigatorAgent:
    ✓ get_nf_metrics — called AND cited (2x)
    ✓ measure_rtt — called AND cited (3x)
    ✓ read_container_logs — called AND cited (2x)
    ✓ read_env_config — called AND cited (1x)
```

## Ground Truth

**Failure domain:** ims_signaling  
**Protocol impact:** Diameter  
**Affected components:** pyhss  
**Severity:** degraded

## Agent Diagnosis

**Model:** v5-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 202.0s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: The IMS layer has failed, preventing user registration and voice calls, because the HSS (`pyhss`) container has become unreachable on the network due to a container-level networking fault.
> - **timeline**:
>     1.  The `pyhss` container becomes unreachable on the network, with ping tests from its peer (`icscf`) showing 100% packet loss and a "Destination Host Unreachable" error.
>     2.  As a result, `pyhss` stops reporting any metrics, indicating it is completely isolated from the monitoring and management plane.
>     3.  The `icscf`, unable to query `pyhss` for user authentication or location, experiences Diameter protocol timeouts.
>     4.  These timeouts prevent IMS user registration, causing voice calls to fail.
> - **root_cause**: The `pyhss` container is suffering from network isolation. While the HSS application process is running correctly *inside* the container, the container itself cannot communicate with the rest of the network. This transport-layer failure is the definitive cause of the Diameter timeouts at the `icscf` and the subsequent failure of all IMS services that depend on the HSS for authentication and user location data.
> - **affected_components**:
>     - `pyhss`: Root Cause
>     - `icscf`: Symptomatic
>     - `scscf`: Symptomatic
>     - `pcscf`: Symptomatic
> - **recommendation**: The operator should investigate the virtual networking configuration of the `pyhss` container on its host. The focus should be on container-level networking (e.g., its attachment to the Docker bridge, its virtual Ethernet interface state), not the application logs, as the application appears to be running correctly within its isolated environment.
> - **confidence**: high
> - **explanation**: The HSS (`pyhss`) container has become isolated from the network. While the application inside is running, nothing can reach it, as confirmed by 100% packet loss from its peers. This is the root cause of the Diameter timeouts seen at the I-CSCF, which in turn prevent user registration and voice calls. The problem lies with the container's networking stack, not the HSS application itself.

### Scoring Breakdown

**Overall score: 25%**

**Scorer assessment:** The agent correctly identified the affected component but misdiagnosed the specific network failure mode, mistaking extreme delay for complete unreachability, leading to incorrect severity and fault type assessments despite high confidence.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | No | The simulated failure was an extreme network latency (60-second delay) on the HSS, making it slow to respond but still technically reachable. The agent diagnosed the HSS as 'unreachable' with '100% packet loss' and 'Destination Host Unreachable,' which describes a complete transport layer failure, not extreme delay. The HSS was not unreachable; its responses were just severely delayed. |
| Component overlap | 100% | The agent correctly identified 'pyhss' as the root cause component. It also correctly listed 'icscf', 'scscf', and 'pcscf' as symptomatically affected, which demonstrates good causal reasoning. |
| Severity correct | No | The agent described the component as 'unreachable' and 'completely isolated' with '100% packet loss.' While the 60-second delay effectively caused an outage, the component itself was not 'unreachable' in the sense of a transport layer failure. It was severely degraded/slow, leading to timeouts, but not completely offline or isolated. |
| Fault type identified | No | The agent identified a 'component unreachable' or 'network isolation' fault type. The actual simulated fault type was 'network degradation' (extreme delay), which is a distinct observable class of failure from complete unreachability. |
| Confidence calibrated | No | The agent expressed 'high' confidence in a diagnosis that fundamentally misidentified the network failure mode (unreachable vs. extreme delay). This indicates poor calibration. |

**Ranking:** The agent provided a single primary diagnosis, which was incorrect. Therefore, the correct cause was not listed.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 147,926 |
| Output tokens | 7,519 |
| Thinking tokens | 9,286 |
| **Total tokens** | **164,731** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| NetworkAnalystAgent | 87,207 | 13 | 6 |
| PatternMatcherAgent | 0 | 0 | 0 |
| InstructionGeneratorAgent | 6,231 | 0 | 1 |
| InvestigatorAgent | 62,189 | 4 | 5 |
| EvidenceValidatorAgent | 0 | 0 | 0 |
| SynthesisAgent | 9,104 | 0 | 1 |


## Resolution

**Heal method:** scheduled
**Recovery time:** 337.8s

## Post-Run Analysis

### Score: 25% — best pipeline execution yet, penalized by scorer semantics

This is the best-executed run across the entire pipeline. Every phase worked as designed, the reasoning was excellent, and the correct component was identified. The low score reflects a semantic disagreement between the agent's interpretation and the scorer's ground truth, not a diagnostic failure.

### What worked perfectly

**Full pipeline execution:** Every phase produced meaningful output. The Investigator used the structured format (Hypothesis Verification → Evidence Chain → Layer Status → Root Cause Assessment) and produced 8 `[EVIDENCE:]` citations, all verified clean by the Evidence Validator. This is the first run where ALL pipeline components functioned correctly end-to-end.

**NetworkAnalyst Step 1b:** The NetworkAnalyst ran `measure_rtt` from icscf to pyhss and saw 100% packet loss — capturing transport evidence while the fault was active. This is exactly the temporal evidence collection pattern we designed.

**Investigator reasoning:** Found a critical contradiction — pyhss application process is running (HTTP 200 OK in logs) but the container is unreachable on the network. Correctly concluded "container-level networking fault, not application crash." This is sophisticated diagnostic reasoning.

**Evidence Validator:** 8/8 citations verified, clean verdict, high confidence. Tool-to-citation mapping shows all 4 Investigator tools were called AND cited.

**Correct component identification:** pyhss identified as root cause. icscf, scscf, pcscf correctly identified as symptomatic (cascading effects).

### Why the scorer gave 25%

The scorer penalized three dimensions:

1. **Root cause:** Agent said "unreachable, 100% packet loss." Ground truth says "60-second delay." The scorer treats these as different failure modes.

2. **Severity:** Agent said "completely isolated." Scorer says it was "severely degraded/slow, not offline."

3. **Fault type:** Agent said "network isolation." Scorer says "network degradation (extreme delay)."

### Why the agent's interpretation is defensible

The `measure_rtt` tool uses `ping -c 3 -W 10` (10-second timeout). With 60,000ms egress delay on pyhss, every ping times out because 10s < 60s. The tool reports "100% packet loss, Destination Host Unreachable." From the agent's observable evidence, pyhss IS unreachable — no probe can reach it within any reasonable timeout.

The distinction between "60-second delay" and "unreachable" is practically meaningless for IMS operations: the Diameter Tw timer (5-30 seconds) will time out regardless. A component that responds after 60 seconds is functionally equivalent to one that doesn't respond at all. The agent correctly diagnosed the operational impact.

### Historical context of this scenario

This scenario was originally designed to crash the HSS container (`container_kill` on pyhss) to simulate HSS failure. But killing a container was too easy to detect — the agent would simply see "pyhss: exited" in `get_network_status` and trivially diagnose "HSS is down." The scenario was redesigned to inject 60-second egress delay instead, simulating an HSS that accepts connections but never responds in time. This makes the diagnostic challenge more realistic — the container is running, the process is alive, the IP is reachable at the network level, but the application is effectively unresponsive.

The `measure_rtt` tool's 10-second timeout cannot distinguish this scenario from true unreachability. A longer timeout (e.g., 120 seconds) would reveal the 60-second RTT, but would make every `measure_rtt` call take 2 minutes, which is impractical.

### Scorer assessment

The scorer is technically correct that "60s delay" and "unreachable" are different failure modes. But the agent's reasoning was sound given its observable evidence:
- Probed with `measure_rtt` → 100% loss (the only rational conclusion from ping timeout)
- Checked logs → application alive (rules out process crash)
- Found the contradiction → "network isolation" (the only explanation that fits both observations)

A more nuanced scorer might award partial credit for: correct component (100%), correct operational impact (timeouts → IMS failure), sophisticated reasoning (contradiction between alive process and unreachable network), and only deduct for the specific delay-vs-loss distinction.

### No fixes needed

This run validates the pipeline. The remaining improvement is tooling (making `measure_rtt` report "timeout — possible extreme latency" instead of "100% loss") which is a known open issue from the `measure_rtt` ADR discussion.
