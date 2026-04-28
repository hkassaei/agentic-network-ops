# Episode Report: IMS Network Partition

**Agent:** v6  
**Episode ID:** ep_20260424_195747_ims_network_partition  
**Date:** 2026-04-24T19:57:49.405576+00:00  
**Duration:** 350.1s  

---

## Scenario

**Category:** network  
**Blast radius:** multi_nf  
**Description:** Partition the P-CSCF from both the I-CSCF and S-CSCF using iptables DROP rules. SIP signaling between the edge proxy and the core IMS is completely severed. Tests IMS behavior under a network split.

## Faults Injected

- **network_partition** on `pcscf` — {'target_ip': '172.22.0.19'}
- **network_partition** on `pcscf` — {'target_ip': '172.22.0.20'}

## Baseline (Pre-Fault)

Stack phase before injection: **ready**
All containers running at baseline.

## Fault Propagation Verification

**Verdict:** ✅ `confirmed`

- **Wait:** 0s
- **Actual elapsed:** 0.0s
- **Nodes with significant deltas:** 1
- **Nodes with any drift:** 4

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 0.99 (threshold: 0.70, trained on 209 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following metrics deviate from their learned-healthy baseline. Treat each as a semantic observation (meaning + numbers), not a number alone — the KB's interpretation is the authoritative reading.

- **`derived.upf_activity_during_calls`** — current **1.00** vs learned baseline **0.09** (HIGH, spike). *(No KB context available — interpret from the metric name.)*

- **`normalized.upf.gtp_outdatapktn3upf_per_ue`** (GTP-U downlink rate per UE (N3)) — current **0.03 packets_per_second** vs learned baseline **6.08 packets_per_second** (HIGH, drop)
    - **What it measures:** Health of the downlink user-plane path UPF → gNB. Typically mirrors
uplink rate during calls/data; asymmetry indicates directional
faults (e.g., UPF receiving from internet but not forwarding).
    - **Drop means:** No traffic leaving UPF toward RAN.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE — constant regardless of UE pool size. Roughly symmetric with uplink during healthy calls.

- **`normalized.upf.gtp_indatapktn3upf_per_ue`** (GTP-U uplink rate per UE (N3)) — current **0.04 packets_per_second** vs learned baseline **6.15 packets_per_second** (HIGH, drop)
    - **What it measures:** Health of the uplink user-plane path gNB → UPF. Drops to near-zero
during RAN or N3 outage; stays nonzero during active calls or data
sessions. Decoupled from SIP signaling (signals data plane, not
control plane).
    - **Drop means:** Data plane dead on uplink — UPF receiving no packets from gNB.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE — constant regardless of UE pool size. Rises during active VoNR calls (~100 pps for G.711 voice) and data transfer.

- **`normalized.pcscf.dialogs_per_ue`** (Active SIP dialogs per registered UE at P-CSCF) — current **0.00 count** vs learned baseline **1.58 count** (MEDIUM, drop)
    - **What it measures:** How many calls per user are currently in progress at the P-CSCF.
Going to zero from a non-zero baseline means calls have ended
(normal) OR call setup is failing system-wide (degradation).
Together with rcv_requests_* it discriminates the two.
    - **Drop means:** No active calls. Normal at rest; suspicious if prior state had calls AND INVITE rate is also zero.
    - **Healthy typical range:** 0–1 count
    - **Healthy invariant:** Per-UE — scale-independent. 0 at rest, ~1 per active VoNR call.


## Event Aggregation (Phase 1)

No events fired during this episode. Either no metric KB triggers matched, or the episode encountered no meaningful state transitions.

## Correlation Analysis (Phase 2)

No events fired — correlation engine had nothing to work with.

## Network Analysis (Phase 3)

**Summary:** A complete data plane outage on the N3 interface has occurred, leading to a halt in all user traffic and call activity, likely due to a fault within the UPF.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | All network function containers are running and all critical network links are reported as active. |
| **ran** | 🟢 GREEN | The gNodeB appears to be connected and registered with the AMF, suggesting the RAN control plane is healthy. |
| **core** | 🔴 RED | The UPF, a core network function, shows zero data plane activity (uplink and downlink) despite active PDU sessions, indicating a critical failure. |
| **ims** | 🟡 YELLOW | IMS is non-operational (no active calls), but this is a symptom of the underlying core data plane failure, not a fault within the IMS components themselves. |

**CORE evidence:**
- normalized.upf.gtp_indatapktn3upf_per_ue
- normalized.upf.gtp_outdatapktn3upf_per_ue

**IMS evidence:**
- normalized.pcscf.dialogs_per_ue

**Ranked hypotheses:**

- **`h1`** (fit=0.90, nf=upf, specificity=specific):
    - **Statement:** The UPF is experiencing a 'zombied session' failure, as described by the 'n3_data_plane_outage' causal chain. The N4 control interface appears healthy with active sessions, but the N3 data plane is internally non-functional, causing all GTP-U traffic to be dropped.
    - **Falsification probes:**
        - Check UPF logs for errors related to GTP-U packet processing or N3 interface failures.
        - Inspect the PFCP session rules on the UPF to confirm they are correctly installed by the SMF.
        - Attempt to ping the gNB's N3 IP address from the UPF container; success would strongly point to an internal UPF fault.
- **`h2`** (fit=0.60, nf=smf, specificity=moderate):
    - **Statement:** The SMF is failing to correctly program the UPF over the N4 interface. While PFCP sessions exist, the specific forwarding rules may be missing or incorrect, causing the UPF to discard all user plane traffic.
    - **Falsification probes:**
        - Inspect SMF logs for errors related to PFCP communication with the UPF.
        - Compare the forwarding rule set on the UPF with the intended session state on the SMF; a mismatch would implicate the SMF.
- **`h3`** (fit=0.40, nf=upf, specificity=moderate):
    - **Statement:** A network-level partition has severed the N3 interface path between the gNodeB and the UPF. Both components may be healthy, but a routing or firewall issue is preventing GTP-U packets from being exchanged.
    - **Falsification probes:**
        - Ping the gNB's N3 IP address from the UPF container; failure would prove the path is broken.
        - Ping the UPF's N3 IP address from the gNB; failure would prove the path is broken in the other direction.


## Falsification Plans (Phase 4)

**3 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `upf`)

**Hypothesis:** The UPF is experiencing a 'zombied session' failure, as described by the 'n3_data_plane_outage' causal chain. The N4 control interface appears healthy with active sessions, but the N3 data plane is internally non-functional, causing all GTP-U traffic to be dropped.

**Probes (3):**
1. **`measure_rtt`** — From UPF container to the gNB's N3 IP address.
    - *Expected if hypothesis holds:* Clean RTT (< 5ms). This indicates the network path is healthy, pointing to an internal UPF issue (the 'zombie' state).
    - *Falsifying observation:* 100% packet loss. This falsifies the 'internal fault' hypothesis and proves a network partition, supporting h3.
2. **`check_process_listeners`** — Check for a listener on UDP port 2152 in the UPF container.
    - *Expected if hypothesis holds:* A process is listening on port 2152. This confirms the data plane process is running, but internally failing to process packets.
    - *Falsifying observation:* No process is listening on port 2152. This suggests the UPF's data plane process has crashed or failed to bind to its port, a more severe infrastructure fault.
3. **`get_nf_metrics`** — Get the gNB's outbound N3 GTP traffic counter (e.g., `gtp_pdu_tx_n3`).
    - *Expected if hypothesis holds:* The gNB's transmit counter for N3 GTP packets is high and increasing, proving that traffic is being sent but dropped by the UPF.
    - *Falsifying observation:* The gNB's transmit counter is zero. This would mean no traffic is being sent to the UPF, so the problem lies upstream of the UPF.

*Notes:* This plan focuses on proving the UPF is the failure point by confirming N3 path health (discriminating from h3) and upstream activity.

### Plan for `h2` (target: `smf`)

**Hypothesis:** The SMF is failing to correctly program the UPF over the N4 interface. While PFCP sessions exist, the specific forwarding rules may be missing or incorrect, causing the UPF to discard all user plane traffic.

**Probes (3):**
1. **`get_nf_metrics`** — Get SMF metrics for PFCP session modification failures (e.g., `smf_pfcp_modification_errors`).
    - *Expected if hypothesis holds:* PFCP error counters on the SMF are elevated, indicating it is aware of failures when programming the UPF.
    - *Falsifying observation:* All SMF-side PFCP counters are clean. This falsifies the hypothesis, as it shows the SMF believes it is programming the UPF successfully.
2. **`get_nf_metrics`** — Get UPF metrics for rejected N4 PFCP requests (e.g., `upf_pfcp_request_rejects`).
    - *Expected if hypothesis holds:* The UPF's PFCP rejection counter is zero, which would mean it is accepting the rules from the SMF, even if they are semantically incorrect.
    - *Falsifying observation:* The UPF's PFCP rejection counter is high. This would indicate an incompatibility or misconfiguration, shifting the fault from 'bad rules from SMF' to 'UPF actively rejecting rules'.
3. **`measure_rtt`** — Measure RTT from the SMF container to the UPF's N4 IP address.
    - *Expected if hypothesis holds:* Clean RTT (< 5ms), confirming the N4 control plane path is healthy.
    - *Falsifying observation:* 100% packet loss. This would indicate an N4 network partition, a more fundamental issue than incorrect PFCP programming.

*Notes:* This plan investigates the health of the N4 interface and the PFCP message exchange between the SMF and UPF.

### Plan for `h3` (target: `upf`)

**Hypothesis:** A network-level partition has severed the N3 interface path between the gNodeB and the UPF. Both components may be healthy, but a routing or firewall issue is preventing GTP-U packets from being exchanged.

**Probes (3):**
1. **`measure_rtt`** — From UPF container to the gNB's N3 IP address.
    - *Expected if hypothesis holds:* 100% packet loss, confirming the path is broken.
    - *Falsifying observation:* Clean RTT (< 5ms). This directly falsifies the hypothesis by proving the path is healthy.
2. **`measure_rtt`** — From gNB container to the UPF's N3 IP address.
    - *Expected if hypothesis holds:* 100% packet loss, confirming the path is broken in the reverse direction.
    - *Falsifying observation:* Clean RTT (< 5ms). This would suggest a unidirectional network issue, but still falsifies a simple, complete partition.
3. **`measure_rtt`** — From UPF container to the SMF's N4 IP address.
    - *Expected if hypothesis holds:* Clean RTT (< 5ms). This shows the UPF's networking is working, isolating the problem to the N3 path.
    - *Falsifying observation:* 100% packet loss. This would indicate a broader network issue where the UPF is completely isolated, not just a partitioned N3 interface.

*Notes:* This plan uses bi-directional and triangulated RTT measurements to definitively prove or disprove a network partition on the N3 interface.


## Parallel Investigators (Phase 5)

**3 sub-Investigator verdict(s):** **1 DISPROVEN**, **1 NOT_DISPROVEN**, **1 INCONCLUSIVE**

### `h1` — ❌ **DISPROVEN**

**Hypothesis:** The UPF is experiencing a 'zombied session' failure, as described by the 'n3_data_plane_outage' causal chain. The N4 control interface appears healthy with active sessions, but the N3 data plane is internally non-functional, causing all GTP-U traffic to be dropped.

**Reasoning:** The hypothesis that the UPF is internally dropping traffic is contradicted by the observation that there is no incoming traffic to drop. Probes confirm the UPF process is running and the N3 network path is healthy via ICMP. However, live data plane gauges show zero packets per second arriving at the UPF's N3 interface. This indicates the gNB is not sending data, shifting the focus upstream.

**Probes executed (3):**
- **From UPF container to the gNB's N3 IP address.** ✓ CONSISTENT
    - *Tool:* `default_api.measure_rtt(container = "upf", target_ip = "172.22.0.23")`
    - *Observation:* [EVIDENCE: measure_rtt("upf", "172.22.0.23") -> "3 packets transmitted, 3 received, 0% packet loss, time 2031ms\nrtt min/avg/max/mdev = 0.143/0.171/0.218/0.033 ms"]
    - *Comment:* The RTT is clean with 0% packet loss, which is consistent with the hypothesis that the network path itself is healthy. This initially pointed away from a network partition.
- **Check for a listener on UDP port 2152 in the UPF container.** ✓ CONSISTENT
    - *Tool:* `default_api.check_process_listeners(container = "upf")`
    - *Observation:* [EVIDENCE: check_process_listeners("upf") -> "udp   UNCONN 0      0         172.22.0.8:2152       0.0.0.0:*    users:((\"open5gs-upfd\",pid=8,fd=8))"]
    - *Comment:* A process is listening on the GTP-U port (2152), which is consistent with the 'zombie session' hypothesis where the data plane process is running but failing internally.
- **Get the gNB's outbound N3 GTP traffic counter (e.g., `gtp_pdu_tx_n3`).** ✗ CONTRADICTS
    - *Tool:* `default_api.get_dp_quality_gauges()`
    - *Observation:* [EVIDENCE: get_dp_quality_gauges() -> "UPF: in packets/sec: 0.0"]
    - *Comment:* The plan expected to see the gNB transmitting traffic. Instead, the UPF's live inbound traffic rate is zero. This contradicts the core of the hypothesis, which assumes traffic is being sent and then dropped by the UPF. The fault is likely upstream, as no data is being sent.

**Alternative suspects:** nr-gnb

### `h2` — ✅ **NOT_DISPROVEN**

**Hypothesis:** The SMF is failing to correctly program the UPF over the N4 interface. While PFCP sessions exist, the specific forwarding rules may be missing or incorrect, causing the UPF to discard all user plane traffic.

**Reasoning:** The probes executed did not produce evidence to contradict the hypothesis. The N4 network path between the SMF and UPF is confirmed to be healthy. Furthermore, metrics from both the SMF and UPF show no reported errors in the PFCP exchange, which is consistent with the hypothesis that the SMF is sending rules that it believes are correct, and the UPF is accepting them, even if they are semantically incorrect and cause traffic to be dropped.

**Probes executed (3):**
- **Get SMF metrics for PFCP session modification failures (e.g., `smf_pfcp_modification_errors`).** ~ AMBIGUOUS
    - *Tool:* `default_api.get_nf_metrics()`
    - *Observation:* [EVIDENCE: get_nf_metrics() -> "SMF [4 PDU] (via prometheus): bearers_active = 8.0  [counter] fivegs_smffunction_sm_sessionnbr = 4.0  [counter] pfcp_sessions_active = 4.0  [counter] ues_active = 2.0  [counter]"]
    - *Comment:* The specific metric for PFCP modification errors was not found. While this is consistent with a value of zero (which would mean the SMF is not aware of any failures), the absence of a metric is weak evidence. The SMF is not reporting any PFCP errors.
- **Get UPF metrics for rejected N4 PFCP requests (e.g., `upf_pfcp_request_rejects`).** ✓ CONSISTENT
    - *Tool:* `default_api.get_nf_metrics()`
    - *Observation:* [EVIDENCE: get_nf_metrics() -> "UPF [16 sess] (via prometheus): fivegs_ep_n3_gtp_indatapktn3upf = 136568.0  [counter] fivegs_ep_n3_gtp_outdatapktn3upf = 85919.0  [counter] fivegs_upffunction_upf_sessionnbr = 16.0  [counter]"]
    - *Comment:* The specific metric for rejected PFCP requests was not found. This is consistent with the expected value of zero, as the hypothesis states the UPF is accepting the rules from the SMF, not rejecting them.
- **Measure RTT from the SMF container to the UPF's N4 IP address.** ✓ CONSISTENT
    - *Tool:* `default_api.measure_rtt(container = 'smf', target_ip = '172.22.0.8')`
    - *Observation:* [EVIDENCE: measure_rtt("smf", "172.22.0.8") -> "3 packets transmitted, 3 received, 0% packet loss, time 2049ms\nrtt min/avg/max/mdev = 0.069/0.130/0.248/0.083 ms"]
    - *Comment:* The RTT is excellent (<1ms) and there is no packet loss, confirming the N4 control plane network path between the SMF and UPF is healthy. This rules out a network partition issue on this interface.

### `h3` — ❓ **INCONCLUSIVE**

**Hypothesis:** A network-level partition has severed the N3 interface path between the gNodeB and the UPF. Both components may be healthy, but a routing or firewall issue is preventing GTP-U packets from being exchanged.

**Reasoning:** The falsification attempt yielded ambiguous results. The environment contains two potential IP addresses for the gNodeB: 172.22.0.23 and 172.22.0.37. Probing from the UPF shows that one of these IPs is reachable while the other is not. Since it is unknown which IP corresponds to the N3 interface, it is impossible to determine if the N3 path is truly severed. The hypothesis is therefore neither proven nor disproven.

**Probes executed (3):**
- **From UPF container to a potential gNB IP address (srs_gnb_ip).** ~ AMBIGUOUS
    - *Tool:* `measure_rtt("upf", "172.22.0.37")`
    - *Observation:* [EVIDENCE: measure_rtt("upf", "172.22.0.37") -> "100% packet loss"]
    - *Comment:* This result would be CONSISTENT with the hypothesis if this is the N3 interface IP. However, without that confirmation, its significance is unclear.
- **From UPF container to the SMF's N4 IP address.** ✓ CONSISTENT
    - *Tool:* `measure_rtt("upf", "172.22.0.7")`
    - *Observation:* [EVIDENCE: measure_rtt("upf", "172.22.0.7") -> "0% packet loss"]
    - *Comment:* This result shows the UPF's networking is generally functional, which aligns with the hypothesis of an isolated N3 partition rather than a totally isolated UPF.
- **From UPF container to a second potential gNB IP address (nr_gnb_ip).** ~ AMBIGUOUS
    - *Tool:* `measure_rtt("upf", "172.22.0.23")`
    - *Observation:* [EVIDENCE: measure_rtt("upf", "172.22.0.23") -> "0% packet loss"]
    - *Comment:* This clean RTT would CONTRADICT the hypothesis if this is the N3 interface IP. This conflicting result is the primary reason for the INCONCLUSIVE verdict.


## Evidence Validation (Phase 6)

**Overall verdict:** clean
**Overall confidence:** high

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 5 | 3/3 | clean | high |
| `InvestigatorAgent_h2` | 3 | 3/3 | clean | high |
| `InvestigatorAgent_h3` | 6 | 3/3 | clean | high |


## Ground Truth

**Failure domain:** ims_signaling  
**Protocol impact:** SIP  
**Affected components:** pcscf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v6-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 207.5s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: A complete data plane outage has occurred due to a halt in GTP-U traffic between the gNodeB and the UPF, with the SMF being the primary suspect for misconfiguring the data path.
> - **timeline**:
>     1. The issue was identified by a complete loss of user plane traffic, with live data plane gauges showing zero packets per second arriving at the UPF's N3 interface.
> - **root_cause**: The leading hypothesis is that the SMF has failed to correctly program the UPF over the N4 interface. While PFCP sessions exist and are accepted by the UPF, the specific forwarding rules are likely missing or semantically incorrect, causing the UPF to not process any user plane traffic. An alternative, but unconfirmed, hypothesis of an N3 network partition remains. `primary_suspect_nf: smf`.
> - **affected_components**:
>     - `smf`: Root Cause (Primary Candidate)
>     - `upf`: Secondary (Symptom of misconfiguration)
>     - `nr-gnb`: Symptomatic (Unable to send/receive traffic)
>     - `ims`: Symptomatic (Non-operational due to lack of data plane)
> - **recommendation**:
>     1.  First, investigate the inconclusive hypothesis by identifying the correct N3 interface IP address for the gNodeB and verifying connectivity (e.g., via ping) from the UPF container to that specific IP to rule out a network partition.
>     2.  Verify the gNodeB's N3 interface traffic counters to confirm if it is attempting to transmit GTP-U packets towards the UPF.
>     3.  Inspect the PFCP session forwarding rules on the UPF and compare them with the intended session state on the SMF to identify any discrepancies that would confirm the SMF misconfiguration.
> - **confidence**: medium
> - **explanation**: The investigation confirmed a total data plane outage originating upstream of the UPF. The initial hypothesis of an internal UPF "zombie session" failure (`h1`) was **disproven**; crucial evidence showed the UPF is receiving zero inbound packets on its N3 interface, meaning it cannot be the one dropping the traffic. The most likely cause is the surviving hypothesis (`h2`), which posits the SMF sent incorrect forwarding rules that were accepted but not properly actioned by the UPF. However, a third hypothesis (`h3`) of a network-level partition on the N3 interface remains **inconclusive** because probes yielded conflicting results due to an ambiguous gNodeB IP address. Because one hypothesis survived but another could not be fully tested, confidence is rated as **medium**.

### Scoring Breakdown

**Overall score: 20%**

**Scorer assessment:** The agent failed to correctly identify the root cause, affected components, and fault type, diagnosing a user plane issue instead of an IMS control plane partition. However, it correctly assessed the severity as a complete outage and identified the IMS layer as affected.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | No | The simulated failure was an IMS network partition, specifically isolating the P-CSCF from I-CSCF and S-CSCF, leading to severed SIP signaling. The agent diagnosed an SMF misconfiguration causing a data plane outage or an N3 network partition. These are fundamentally different failure modes and affected network domains (IMS control plane vs. user plane/core network). |
| Component overlap | 0% | The primary affected component in the simulated failure is the P-CSCF. The agent's diagnosis lists 'smf' as the 'Root Cause (Primary Candidate)' and 'ims' as 'Symptomatic'. The P-CSCF is not identified as the root cause or even explicitly mentioned as a primary affected component. |
| Severity correct | Yes | The simulated failure resulted in 'SIP signaling severed' and 'New REGISTER and INVITE fail', indicating a complete outage for new IMS services. The agent diagnosed a 'complete data plane outage' with 'zero packets per second'. Both describe a complete service disruption, so the severity assessment (complete outage) is correct, even if the affected network domain is wrong. |
| Fault type identified | No | The simulated failure is a 'Network partition' affecting the IMS control plane. The agent's primary diagnosis is 'SMF misconfiguration' leading to a 'complete data plane outage'. While 'N3 network partition' is mentioned as an alternative hypothesis, it is not the primary identified fault type, nor is it attributed to the correct network segment (IMS control plane). |
| Layer accuracy | Yes | The P-CSCF belongs to the 'ims' layer. The agent's network analysis correctly rated the 'ims' layer as 'yellow' (affected), even though it attributed the IMS issues as a symptom of a core data plane failure rather than a root cause within the IMS layer itself. The layer itself was correctly identified as impacted. |
| Confidence calibrated | No | The agent's diagnosis of the root cause and primary affected components is completely incorrect. A 'medium' confidence level for a diagnosis that is entirely wrong indicates poor calibration. |

**Ranking:** The correct root cause (IMS network partition / P-CSCF isolation) was not identified or ranked by the agent.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 236,128 |
| Output tokens | 5,666 |
| Thinking tokens | 19,009 |
| **Total tokens** | **260,803** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| EventAggregator | 0 | 0 | 0 |
| CorrelationAnalyzer | 0 | 0 | 0 |
| NetworkAnalystAgent | 42,355 | 6 | 3 |
| InstructionGeneratorAgent | 18,907 | 1 | 2 |
| InvestigatorAgent_h1 | 69,593 | 5 | 6 |
| InvestigatorAgent_h2 | 51,391 | 3 | 4 |
| InvestigatorAgent_h3 | 71,736 | 6 | 7 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 6,821 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 350.1s
