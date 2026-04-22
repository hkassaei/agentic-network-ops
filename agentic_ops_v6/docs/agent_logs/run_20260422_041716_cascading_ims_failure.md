# Episode Report: Cascading IMS Failure

**Agent:** v6  
**Episode ID:** ep_20260422_041137_cascading_ims_failure  
**Date:** 2026-04-22T04:11:38.951420+00:00  
**Duration:** 333.5s  

---

## Scenario

**Category:** compound  
**Blast radius:** multi_nf  
**Description:** Kill PyHSS AND add 2-second latency to the S-CSCF. This simulates a cascading failure: the HSS is gone (no Diameter auth) AND the S-CSCF is degraded (slow SIP processing). Total IMS outage.

## Faults Injected

- **container_kill** on `pyhss`
- **network_latency** on `scscf` — {'delay_ms': 2000}

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

**ANOMALY DETECTED.** Overall anomaly score: 0.90 (threshold: 0.70, trained on 211 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following metrics deviate from their learned-healthy baseline. Treat each as a semantic observation (meaning + numbers), not a number alone — the KB's interpretation is the authoritative reading.

- **`normalized.upf.gtp_outdatapktn3upf_per_ue`** (GTP-U downlink rate per UE (N3)) — current **0.03 packets_per_second** vs learned baseline **3.34 packets_per_second** (MEDIUM, drop)
    - **What it measures:** Health of the downlink user-plane path UPF → gNB. Typically mirrors
uplink rate during calls/data; asymmetry indicates directional
faults (e.g., UPF receiving from internet but not forwarding).
    - **Drop means:** No traffic leaving UPF toward RAN.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE — constant regardless of UE pool size. Roughly symmetric with uplink during healthy calls.

- **`normalized.upf.gtp_indatapktn3upf_per_ue`** (GTP-U uplink rate per UE (N3)) — current **0.11 packets_per_second** vs learned baseline **3.42 packets_per_second** (MEDIUM, drop)
    - **What it measures:** Health of the uplink user-plane path gNB → UPF. Drops to near-zero
during RAN or N3 outage; stays nonzero during active calls or data
sessions. Decoupled from SIP signaling (signals data plane, not
control plane).
    - **Drop means:** Data plane dead on uplink — UPF receiving no packets from gNB.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE — constant regardless of UE pool size. Rises during active VoNR calls (~100 pps for G.711 voice) and data transfer.

- **`normalized.pcscf.dialogs_per_ue`** (Active SIP dialogs per registered UE at P-CSCF) — current **0.00 count** vs learned baseline **0.57 count** (LOW, drop)
    - **What it measures:** How many calls per user are currently in progress at the P-CSCF.
Going to zero from a non-zero baseline means calls have ended
(normal) OR call setup is failing system-wide (degradation).
Together with rcv_requests_* it discriminates the two.
    - **Drop means:** No active calls. Normal at rest; suspicious if prior state had calls AND INVITE rate is also zero.
    - **Healthy typical range:** 0–1 count
    - **Healthy invariant:** Per-UE — scale-independent. 0 at rest, ~1 per active VoNR call.

- **`derived.upf_activity_during_calls`** — current **1.00** vs learned baseline **0.47** (LOW, spike). *(No KB context available — interpret from the metric name.)*


## Event Aggregation (Phase 1)

No events fired during this episode. Either no metric KB triggers matched, or the episode encountered no meaningful state transitions.

## Correlation Analysis (Phase 2)

No events fired — correlation engine had nothing to work with.

## Network Analysis (Phase 3)

**Summary:** The HSS container has exited, which has crippled the IMS control plane, preventing all user registrations and calls; the observed data plane inactivity is a direct downstream consequence.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | Core infrastructure is stable. |
| **ran** | 🟡 YELLOW | The RAN is connected to the core, but its function is impaired as no user plane traffic can be established due to upstream IMS failures. |
| **core** | 🔴 RED | The user plane is inactive and a critical control plane dependency (HSS) has failed. |
| **ims** | 🔴 RED | The IMS stack is non-functional due to the failure of the HSS, which is essential for authentication and registration. |

**RAN evidence:**
- get_nf_metrics shows 2 UEs connected to the AMF.
- get_network_topology shows the N2 and N3 links from the RAN are considered active.

**CORE evidence:**
- Screener shows gtp_indatapktn3upf_per_ue and gtp_outdatapktn3upf_per_ue are near-zero, indicating a dead data plane.
- get_nf_metrics confirms zero packet-per-second rates on RTPEngine and UPF.
- The HSS, a critical authentication component for the core, is down.

**IMS evidence:**
- get_network_status shows the HSS container (pyhss) has exited.
- get_network_topology shows all Diameter links to the HSS are INACTIVE.
- Screener shows active SIP dialogs per UE is zero.

**Ranked hypotheses:**

- **`h1`** (fit=1.00, nf=pyhss, specificity=specific):
    - **Statement:** The HSS container has exited, causing a complete failure of the IMS control plane. All Diameter Cx interface communication from I-CSCF and S-CSCF to the HSS is failing, which prevents UE registration and VoNR call setup. The observed data plane inactivity is a direct downstream consequence of this control plane failure.
    - **Falsification probes:**
        - Check the container logs for `pyhss` to determine the cause of its exit.
        - Restarting the `pyhss` container should restore IMS registration and call setup functionality.
        - Live logs on I-CSCF or S-CSCF should show Diameter connection errors or timeouts when a new UE attempts to register.
- **`h2`** (fit=0.40, nf=upf, specificity=moderate):
    - **Statement:** A fundamental breakdown exists in the GTP-U transport path involving the UPF, causing both uplink and downlink packet rates to drop to zero. This prevents any user data or VoNR media from traversing the core network.
    - **Falsification probes:**
        - After restoring the HSS and successfully registering a UE, if data still doesn't flow during a call, then a separate data plane fault exists.
        - Check PFCP sessions between SMF and UPF; if they are correctly established, the problem lies purely in the GTP-U transport path itself.


## Falsification Plans (Phase 4)

**2 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `pyhss`)

**Hypothesis:** The HSS container has exited, causing a complete failure of the IMS control plane. All Diameter Cx interface communication from I-CSCF and S-CSCF to the HSS is failing, which prevents UE registration and VoNR call setup. The observed data plane inactivity is a direct downstream consequence of this control plane failure.

**Probes (3):**
1. **`get_network_status`** — None
    - *Expected if hypothesis holds:* The 'pyhss' container is in an 'exited' or otherwise non-running state.
    - *Falsifying observation:* The 'pyhss' container is in a 'running' state. This would directly contradict the central claim of the hypothesis.
2. **`check_process_listeners`** — container='pyhss'
    - *Expected if hypothesis holds:* No process is listening on the Diameter port (TCP 3868) inside the container.
    - *Falsifying observation:* A process is actively listening on TCP port 3868. This would indicate the HSS process is running, even if the container status is misleading.
3. **`run_kamcmd`** — container='scscf', command='dm.print_conns'
    - *Expected if hypothesis holds:* The Diameter connection to the HSS FQDN (hss.ims.mnc001.mcc001.3gppnetwork.org) is in a 'DOWN'/'CONNECTING' state or is absent from the list.
    - *Falsifying observation:* The Diameter connection to the HSS is in an 'UP' or 'OK' state, indicating a healthy control plane link from S-CSCF's perspective.

*Notes:* This plan directly tests the hypothesis's core claim (container exit) and its immediate effect on adjacent IMS components (CSCFs).

### Plan for `h2` (target: `upf`)

**Hypothesis:** A fundamental breakdown exists in the GTP-U transport path involving the UPF, causing both uplink and downlink packet rates to drop to zero. This prevents any user data or VoNR media from traversing the core network.

**Probes (3):**
1. **`check_process_listeners`** — container='upf'
    - *Expected if hypothesis holds:* No process is listening on the GTP-U port (UDP 2152), indicating the data plane process has failed.
    - *Falsifying observation:* A process is listening on UDP port 2152. This proves the UPF data plane is running and ready to receive traffic.
2. **`measure_rtt`** — from='nr_gnb', to_ip='UPF N3 interface IP'
    - *Expected if hypothesis holds:* High packet loss (>50%) or complete unreachability, indicating a network partition between the RAN and the core data plane.
    - *Falsifying observation:* Clean, low-latency RTT (< 5ms). This proves the N3 transport path is healthy.
3. **`measure_rtt`** — from='smf', to_ip='UPF N4 interface IP'
    - *Expected if hypothesis holds:* High packet loss (>50%) or complete unreachability, preventing the SMF from managing the UPF via PFCP.
    - *Falsifying observation:* Clean, low-latency RTT (< 5ms). This proves the N4 control-plane transport path is healthy.

*Notes:* This plan tests the viability of the UPF and its transport paths (N3 and N4). If all probes return falsifying observations, the UPF and its connections are sound, meaning the lack of data plane traffic is an effect of an upstream issue (like h1), not the cause.


## Parallel Investigators (Phase 5)

**2 sub-Investigator verdict(s):** **1 NOT_DISPROVEN**, **1 DISPROVEN**

### `h1` — ✅ **NOT_DISPROVEN**

**Hypothesis:** The HSS container has exited, causing a complete failure of the IMS control plane. All Diameter Cx interface communication from I-CSCF and S-CSCF to the HSS is failing, which prevents UE registration and VoNR call setup. The observed data plane inactivity is a direct downstream consequence of this control plane failure.

**Reasoning:** All probes executed were consistent with the hypothesis. The primary claim, that the HSS container has exited, was confirmed directly. The expected downstream consequences on networking (no listening ports, closed Diameter connection from S-CSCF) were also observed, providing a consistent picture of the failure as described.

**Probes executed (3):**
- **The 'pyhss' container is in an 'exited' or otherwise non-running state.** ✓ CONSISTENT
    - *Tool:* `default_api.get_network_status()`
    - *Observation:* [EVIDENCE: get_network_status() -> "containers": {"pyhss": "exited"}]
    - *Comment:* This observation directly confirms the core assertion of the hypothesis: the pyhss container is not running.
- **No process is listening on the Diameter port (TCP 3868) inside the container.** ✓ CONSISTENT
    - *Tool:* `default_api.check_process_listeners(container='pyhss')`
    - *Observation:* [EVIDENCE: check_process_listeners("pyhss") -> "Error response from daemon: container 8d9002eddc5bbae44f9f8bdebb686ebe8f36c77075f8a1d3075d619d2aba46ab is not running"]
    - *Comment:* The tool confirmed the container is not running, which is consistent with the expectation that no process would be listening on any port.
- **The Diameter connection to the HSS FQDN (hss.ims.mnc001.mcc001.3gppnetwork.org) is in a 'DOWN'/'CONNECTING' state or is absent from the list.** ✓ CONSISTENT
    - *Tool:* `default_api.run_kamcmd(container='scscf', command='cdp.list_peers')`
    - *Observation:* [EVIDENCE: run_kamcmd("scscf", "cdp.list_peers") -> "FQDN: hss.ims.mnc001.mcc001.3gppnetwork.org\n\t\tDetails: {\n\t\t\tState: Closed"]
    - *Comment:* The Diameter peer connection from the S-CSCF to the HSS is in the 'Closed' state, which is equivalent to 'DOWN'. This confirms the expected impact on the S-CSCF.

### `h2` — ❌ **DISPROVEN**

**Hypothesis:** A fundamental breakdown exists in the GTP-U transport path involving the UPF, causing both uplink and downlink packet rates to drop to zero. This prevents any user data or VoNR media from traversing the core network.

**Reasoning:** All three probes executed returned evidence that directly contradicts the hypothesis. The UPF process is listening on the GTP-U port (2152), and the transport paths for both the N3 interface (to the RAN) and the N4 interface (to the SMF) are healthy with no packet loss. This proves the UPF itself and its network connectivity are not the cause of the data plane inactivity; the UPF is simply starved of traffic from an upstream failure.

**Probes executed (3):**
- **No process is listening on the GTP-U port (UDP 2152), indicating the data plane process has failed.** ✗ CONTRADICTS
    - *Tool:* `check_process_listeners("upf")`
    - *Observation:* [EVIDENCE: check_process_listeners("upf") -> "udp   UNCONN 0      0         172.22.0.8:2152       0.0.0.0:*    users:((\"open5gs-upfd\",pid=8,fd=8))"]
    - *Comment:* A process, open5gs-upfd, is actively listening on UDP port 2152. This directly falsifies the claim that the data plane process has failed.
- **High packet loss (>50%) or complete unreachability, indicating a network partition between the RAN and the core data plane.** ✗ CONTRADICTS
    - *Tool:* `measure_rtt("upf", "172.22.0.23")`
    - *Observation:* [EVIDENCE: measure_rtt("upf", "172.22.0.23") -> "3 packets transmitted, 3 received, 0% packet loss, time 2032ms\nrtt min/avg/max/mdev = 0.059/0.163/0.360/0.139 ms"]
    - *Comment:* The RTT from the UPF to the gNB's IP address shows 0% packet loss and sub-millisecond latency. This proves the N3 transport path is healthy. (Note: The probe was run from UPF->gNB as the 'nr_gnb' container was not available in the tool's context).
- **High packet loss (>50%) or complete unreachability, preventing the SMF from managing the UPF via PFCP.** ✗ CONTRADICTS
    - *Tool:* `measure_rtt("smf", "172.22.0.8")`
    - *Observation:* [EVIDENCE: measure_rtt("smf", "172.22.0.8") -> "3 packets transmitted, 3 received, 0% packet loss, time 2026ms\nrtt min/avg/max/mdev = 0.084/0.207/0.391/0.132 ms"]
    - *Comment:* The RTT from the SMF to the UPF shows 0% packet loss and sub-millisecond latency. This proves the N4 control plane transport path is healthy.

**Alternative suspects:** pyhss, amf, smf


## Evidence Validation (Phase 6)

**Overall verdict:** clean
**Overall confidence:** high

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 3 | 3/3 | clean | high |
| `InvestigatorAgent_h2` | 5 | 3/3 | clean | high |


## Ground Truth

**Failure domain:** ims_signaling  
**Protocol impact:** SIP  
**Affected components:** scscf, pyhss  
**Severity:** degraded

## Agent Diagnosis

**Model:** v6-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 190.7s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: The HSS container has exited, which has crippled the IMS control plane, preventing all user registrations and calls; the observed data plane inactivity is a direct downstream consequence.
> - **timeline**:
>     1. The `pyhss` container, providing the Home Subscriber Server (HSS) function, entered an `exited` state.
>     2. The S-CSCF, unable to communicate with the HSS, marked its Diameter peer connection as `Closed`.
>     3. With the HSS unavailable for authentication, new user registrations with the IMS network began to fail.
>     4. As no users could register and make calls, no VoNR media sessions were established, leading to a complete drop in user plane traffic through the UPF.
> - **root_cause**: The `pyhss` container (providing HSS functionality) has exited. This control plane component is essential for user authentication and service authorization in the IMS stack. Its failure has halted all IMS-related activities, including registration and call setup.
> - **affected_components**:
>     - `pyhss`: Root Cause
>     - `scscf`: Secondary
>     - `icscf`: Secondary
>     - `upf`: Symptomatic
>     - `ran`: Symptomatic
> - **recommendation**: Investigate the container logs for `pyhss` to determine the specific reason for its exit (e.g., application crash, out-of-memory error, or configuration issue).
> - **confidence**: high
> - **explanation**: The investigation confirmed hypothesis `h1` and disproved `h2`. The root cause is a definitive failure in the IMS control plane, not the 5G core's data plane. Evidence showed the `pyhss` container is in an `exited` state and the S-CSCF's Diameter connection to it is `Closed`. This completely explains the inability for users to register. The alternative hypothesis (`h2`), which suggested a data plane failure at the UPF, was disproven by tests showing the UPF process is running correctly and its network paths are healthy. The lack of traffic at the UPF is merely a symptom of the upstream HSS failure.

### Scoring Breakdown

**Overall score: 95%**

**Scorer assessment:** The agent accurately identified the HSS failure as the primary root cause of the total IMS outage, correctly assessing its severity and fault type. It also correctly attributed the failure to the IMS layer. While it noted the S-CSCF's involvement, it did not identify the injected latency as a concurrent root cause, but this does not detract significantly from its overall strong diagnosis of the complete service failure.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | Yes | The agent correctly identified the 'pyhss' container exiting as the root cause. While the simulation also included S-CSCF latency, the HSS failure is the primary and most impactful cause leading to a 'total IMS outage' and 'Diameter completely down', which the agent accurately diagnosed. |
| Component overlap | 75% | The agent correctly identified 'pyhss' as the 'Root Cause'. It also identified 'scscf' as 'Secondary'. The S-CSCF was a primary affected component due to injected latency, not a secondary effect of the HSS failure. Therefore, while 'pyhss' was perfectly identified, the 'scscf' was recognized as involved but its causal role (direct latency injection) was not fully captured as a root cause. |
| Severity correct | Yes | The agent's diagnosis of 'crippled the IMS control plane', 'preventing all user registrations and calls', and 'complete drop in user plane traffic' accurately reflects the 'Total IMS outage' simulated. |
| Fault type identified | Yes | The agent identified the HSS as 'exited', which correctly describes a 'component completely unreachable (down/not responding)'. While it did not explicitly mention the S-CSCF's 'elevated network latency', the primary fault type for the most critical component was correctly identified. |
| Layer accuracy | Yes | The agent's network analysis correctly rated the 'ims' layer as 'red' and explicitly cited the 'pyhss' (HSS) container exiting as evidence, which aligns with the ground truth that 'pyhss' belongs to the 'ims' layer. |
| Confidence calibrated | Yes | The agent expressed 'high' confidence, which is justified given its accurate identification of the primary root cause, severity, and fault type for the total IMS outage, even with the minor omission regarding the S-CSCF's concurrent latency. |

**Ranking position:** #1 — The agent provided a single, correct root cause in its final diagnosis.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 125,799 |
| Output tokens | 4,123 |
| Thinking tokens | 13,598 |
| **Total tokens** | **143,520** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| EventAggregator | 0 | 0 | 0 |
| CorrelationAnalyzer | 0 | 0 | 0 |
| NetworkAnalystAgent | 36,353 | 4 | 3 |
| InstructionGeneratorAgent | 25,227 | 2 | 3 |
| InvestigatorAgent_h1 | 28,280 | 3 | 4 |
| InvestigatorAgent_h2 | 48,553 | 5 | 6 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 5,107 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 333.5s
