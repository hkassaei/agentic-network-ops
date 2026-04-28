# Episode Report: gNB Radio Link Failure

**Agent:** v6  
**Episode ID:** ep_20260424_191117_gnb_radio_link_failure  
**Date:** 2026-04-24T19:11:18.491136+00:00  
**Duration:** 318.6s  

---

## Scenario

**Category:** container  
**Blast radius:** single_nf  
**Description:** Kill the gNB to simulate a radio link failure. All UEs lose 5G registration, PDU sessions drop, and IMS SIP unregisters.

## Faults Injected

- **container_kill** on `nr_gnb`

## Baseline (Pre-Fault)

Stack phase before injection: **ready**
All containers running at baseline.

## Fault Propagation Verification

**Verdict:** ✅ `confirmed`

- **Wait:** 0s
- **Actual elapsed:** 0.0s
- **Nodes with significant deltas:** 2
- **Nodes with any drift:** 4

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 0.95 (threshold: 0.70, trained on 209 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following metrics deviate from their learned-healthy baseline. Treat each as a semantic observation (meaning + numbers), not a number alone — the KB's interpretation is the authoritative reading.

- **`normalized.smf.sessions_per_ue`** (PDU sessions per attached UE) — current **0.00 count** vs learned baseline **2.00 count** (HIGH, drop)
    - **What it measures:** Ratio of established PDU sessions to RAN-attached UEs. Constant under
healthy operation (depends on configured APNs per UE). Drift means
some UEs lost or failed to establish their sessions — usually points
to SMF or UPF control-plane issues, since attachment (ran_ue) is
independent of session establishment.
    - **Drop means:** Some UEs have fewer PDU sessions than they should. Likely SMF or PFCP (N4) issues.
    - **Healthy typical range:** 1.9–2.1 count
    - **Healthy invariant:** Constant equal to configured_apns_per_ue (typically 2). Scale-independent.

- **`normalized.smf.bearers_per_ue`** (Active QoS bearers per UE) — current **0.00 count** vs learned baseline **4.15 count** (HIGH, drop)
    - **What it measures:** Per-UE count of active QoS bearers. Baseline reflects default
bearers; increments during VoNR calls indicate dedicated voice
bearers being set up. Drop during an active call = dedicated
bearer torn down unexpectedly (voice will fail).
    - **Drop means:** Lost bearers. If sustained during a call, voice path is broken.
    - **Healthy typical range:** 2–3.5 count
    - **Healthy invariant:** At rest: equals configured default bearers (typically 2 per UE).
During active VoNR call: +1 per caller. The per-UE ratio is the
invariant; absolute count scales with UE pool.

- **`normalized.upf.gtp_outdatapktn3upf_per_ue`** (GTP-U downlink rate per UE (N3)) — current **0.00 packets_per_second** vs learned baseline **6.08 packets_per_second** (HIGH, drop)
    - **What it measures:** Health of the downlink user-plane path UPF → gNB. Typically mirrors
uplink rate during calls/data; asymmetry indicates directional
faults (e.g., UPF receiving from internet but not forwarding).
    - **Drop means:** No traffic leaving UPF toward RAN.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE — constant regardless of UE pool size. Roughly symmetric with uplink during healthy calls.

- **`normalized.upf.gtp_indatapktn3upf_per_ue`** (GTP-U uplink rate per UE (N3)) — current **0.00 packets_per_second** vs learned baseline **6.15 packets_per_second** (HIGH, drop)
    - **What it measures:** Health of the uplink user-plane path gNB → UPF. Drops to near-zero
during RAN or N3 outage; stays nonzero during active calls or data
sessions. Decoupled from SIP signaling (signals data plane, not
control plane).
    - **Drop means:** Data plane dead on uplink — UPF receiving no packets from gNB.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE — constant regardless of UE pool size. Rises during active VoNR calls (~100 pps for G.711 voice) and data transfer.

- **`normalized.pcscf.dialogs_per_ue`** (Active SIP dialogs per registered UE at P-CSCF) — current **1.00 count** vs learned baseline **1.58 count** (LOW, shift)
    - **What it measures:** How many calls per user are currently in progress at the P-CSCF.
Going to zero from a non-zero baseline means calls have ended
(normal) OR call setup is failing system-wide (degradation).
Together with rcv_requests_* it discriminates the two.
    - **Shift means:** Calls ending or setup failing.
    - **Healthy typical range:** 0–1 count
    - **Healthy invariant:** Per-UE — scale-independent. 0 at rest, ~1 per active VoNR call.


## Event Aggregation (Phase 1)

**4 events fired during the observation window:**

- `core.amf.gnb_association_drop` (source: `core.amf.gnb`, nf: `amf`, t=1777057996.2)  [current_value=0.0, prior_stable_value=1.0]
- `core.amf.ran_ue_sudden_drop` (source: `core.amf.ran_ue`, nf: `amf`, t=1777057996.2)  [current_value=0.0, prior_stable_value=2.0, delta_percent=-100.0]
- `core.amf.ran_ue_full_loss` (source: `core.amf.ran_ue`, nf: `amf`, t=1777057996.2)  [current_value=0.0, prior_stable_value=2.0]
- `core.smf.sessions_per_ue_drop` (source: `core.smf.sessions_per_ue`, nf: `smf`, t=1777057996.2)  [current_value=0.0, prior_stable_value=2.0, delta_percent=-100.0]

## Correlation Analysis (Phase 2)

**Correlation engine produced 5 ranked composite hypotheses from 4 fired events (showing top 3 of 5):**

### H1: Total RAN outage
  - primary_nf: amf
  - explanatory_fit: 0.50 (2/4 events)
  - testability: 2 (2 disambiguating metrics)
  - supporting events: `core.amf.gnb_association_drop`, `core.amf.ran_ue_full_loss`
  - probes to discriminate:
      - Check core.amf.ran_ue → Whether N2 is dead (both zero) vs. AMF-side attach issue (gnb>0, ran_ue=0)
      - Check core.amf.gnb → gNB-side failure (gnb=0) vs. AMF-side attach-processing issue (gnb>0 but ran_ue=0)

### H2: Total RAN failure — gNB + UEs both gone
  - primary_nf: amf
  - explanatory_fit: 0.50 (2/4 events)
  - testability: 2 (2 disambiguating metrics)
  - supporting events: `core.amf.gnb_association_drop`, `core.amf.ran_ue_full_loss`
  - probes to discriminate:
      - Check core.amf.ran_ue → Whether N2 is dead (both zero) vs. AMF-side attach issue (gnb>0, ran_ue=0)
      - Check core.amf.gnb → gNB-side failure (gnb=0) vs. AMF-side attach-processing issue (gnb>0 but ran_ue=0)

### H3: UEs detaching, sessions torn down — RAN-triggered
  - primary_nf: smf
  - explanatory_fit: 0.50 (2/4 events)
  - testability: 2 (2 disambiguating metrics)
  - supporting events: `core.amf.ran_ue_sudden_drop`, `core.smf.sessions_per_ue_drop`
  - probes to discriminate:
      - Check core.amf.ran_ue → SMF/UPF fault (ran_ue stable but sessions_per_ue dropping) vs. general attachment issue (both dropping)
      - Check core.amf.gnb → gNB-side failure (gnb=0) vs. AMF-side attach-processing issue (gnb>0 but ran_ue=0)


## Network Analysis (Phase 3)

**Summary:** The entire RAN appears to be down or disconnected from the core, causing a total loss of service.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | All underlying containers and infrastructure appear to be healthy. |
| **ran** | 🔴 RED | No gNBs are connected to the AMF, and no UEs are attached to the network. This is a full outage of the radio access network. |
| **core** | 🟡 YELLOW | The core network components are running, but are effectively idle and showing zero activity because no UEs are attached. This is a downstream symptom of the RAN outage. |
| **ims** | 🟢 GREEN | The IMS components are up and appear healthy, but are unused due to the lack of registered UEs. |

**RAN evidence:**
- get_network_topology shows N2 and N3 links as INACTIVE
- AMF metrics show gnb=0 and ran_ue=0

**CORE evidence:**
- Fired event core.smf.sessions_per_ue_drop
- All per-UE metrics at SMF and UPF are at zero

**Ranked hypotheses:**

- **`h1`** (fit=1.00, nf=amf, specificity=specific):
    - **Statement:** The RAN has completely detached from the core network. This is likely due to a failure of the gNB itself or a network partition severing the N2 (control plane) and N3 (user plane) interfaces to the AMF and UPF respectively.
    - **Supporting events:** `core.amf.gnb_association_drop`, `core.amf.ran_ue_full_loss`, `core.amf.ran_ue_sudden_drop`, `core.smf.sessions_per_ue_drop`
    - **Falsification probes:**
        - Check gNB status and logs for errors.
        - Verify network connectivity (ping, traceroute) from the AMF to the gNB's N2 endpoint IP address.
- **`h2`** (fit=0.60, nf=amf, specificity=moderate):
    - **Statement:** The AMF has an internal fault that caused it to drop all N2 associations to the gNBs, even though the process itself is still running. This would lead to a full detachment of all UEs.
    - **Supporting events:** `core.amf.gnb_association_drop`, `core.amf.ran_ue_full_loss`
    - **Falsification probes:**
        - Check AMF logs for any SCTP or NGAP protocol errors that occurred around the time of the event.
        - Restart the AMF container to see if it re-establishes connections to the gNBs.


## Falsification Plans (Phase 4)

**3 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `amf`)

**Hypothesis:** The RAN has completely detached from the core network. This is likely due to a failure of the gNB itself or a network partition severing the N2 (control plane) and N3 (user plane) interfaces to the AMF and UPF respectively.

**Probes (3):**
1. **`measure_rtt`** — from: amf, to_ip: gnb_n2_ip
    - *Expected if hypothesis holds:* High or 100% packet loss, indicating a network partition or gNB unreachability.
    - *Falsifying observation:* Low RTT (<5ms) and no packet loss. This would indicate the network path is healthy and the gNB is responsive at the network layer, making a simple partition unlikely.
2. **`measure_rtt`** — from: upf, to_ip: gnb_n3_ip
    - *Expected if hypothesis holds:* High or 100% packet loss, consistent with a gNB failure or network partition affecting all paths to the gNB.
    - *Falsifying observation:* Low RTT (<5ms). This would falsify a full gNB failure and suggest the issue is specific to the AMF-gNB path (N2 interface).
3. **`check_process_listeners`** — container: nr-gnb
    - *Expected if hypothesis holds:* No process listening on the SCTP port for N2 or the UDP port for N3, indicating a crashed or misconfigured gNB process.
    - *Falsifying observation:* Processes are listening on the correct SCTP (N2) and GTP-U (N3) ports. This proves the gNB process is running and ready for connections.

*Notes:* This plan focuses on testing the 'network partition' and 'gNB failure' aspects of the hypothesis by checking network reachability from multiple core NFs (triangulation) and verifying the gNB process status directly.

### Plan for `h2` (target: `amf`)

**Hypothesis:** The AMF has an internal fault that caused it to drop all N2 associations to the gNBs, even though the process itself is still running. This would lead to a full detachment of all UEs.

**Probes (3):**
1. **`check_process_listeners`** — container: amf
    - *Expected if hypothesis holds:* A process is listening on the N2/SCTP port, but is otherwise non-functional.
    - *Falsifying observation:* No process is listening on the N2/SCTP port. This would mean the AMF process has crashed, contradicting the hypothesis that it is 'still running'.
2. **`get_nf_metrics`** — nf: amf, metrics: ['sctp_errors', 'ngap_errors']
    - *Expected if hypothesis holds:* Elevated counters for SCTP or NGAP protocol errors, indicating the AMF is failing to process messages correctly.
    - *Falsifying observation:* Zero or nominal error counts. This would suggest the AMF is not experiencing any internal processing errors, weakening the 'internal fault' hypothesis.
3. **`get_network_status`** — component: amf
    - *Expected if hypothesis holds:* The link status to the gNB (N2) should appear 'ACTIVE', as the issue is an internal AMF fault, not a lower-level link failure.
    - *Falsifying observation:* The link status to the gNB (N2) is 'INACTIVE'. This points to a network-level problem, falsifying the idea that the fault is contained entirely within the AMF application.

*Notes:* This plan attempts to isolate the failure to the AMF process itself. It verifies the process is running but likely faulty by checking for internal protocol errors while confirming the underlying network links are not the cause.

### Plan for `h3` (target: `smf`)

**Hypothesis:** UEs detaching, sessions torn down — RAN-triggered

**Probes (3):**
1. **`measure_rtt`** — from: smf, to_ip: upf_n4_ip
    - *Expected if hypothesis holds:* Low RTT and no packet loss, as the trigger is from the RAN, not from a core network path failure between SMF and UPF.
    - *Falsifying observation:* High or 100% packet loss. This would indicate a failure in the core N4 path, suggesting a core-triggered issue, not a RAN-triggered one.
2. **`get_nf_metrics`** — nf: nr-gnb, metrics: ['rrc_connection_failures', 'initial_attach_failures']
    - *Expected if hypothesis holds:* Metrics indicating the gNB is what triggered the detachment, such as a high count of RRC connection releases or failures.
    - *Falsifying observation:* Zero or nominal gNB-level failure counts. If the gNB is not showing any signs of actively tearing down connections, the trigger is unlikely to be from the RAN.
3. **`query_subscriber`** — imsi: <known_imsi>
    - *Expected if hypothesis holds:* The subscriber is shown as 'DEREGISTERED' in the UDM/HSS, consistent with a full detachment procedure originating from the RAN.
    - *Falsifying observation:* The subscriber is still shown as 'REGISTERED'. This would indicate a 'ghost' state where the AMF has lost the UE session but the core (UDM) has not been updated, pointing away from a clean RAN-triggered detach.

*Notes:* This plan focuses on verifying the 'RAN-triggered' nature of the event. It checks for core network faults that could be an alternative cause and looks for positive evidence at the gNB and in the UDM that a RAN-initiated procedure actually occurred.


## Parallel Investigators (Phase 5)

**2 sub-Investigator verdict(s):** **1 NOT_DISPROVEN**, **1 DISPROVEN**

### `h1` — ✅ **NOT_DISPROVEN**

**Hypothesis:** The RAN has completely detached from the core network. This is likely due to a failure of the gNB itself or a network partition severing the N2 (control plane) and N3 (user plane) interfaces to the AMF and UPF respectively.

**Reasoning:** Probes confirm that the gNB is unreachable from both the AMF and UPF, which is consistent with the hypothesis. An attempt to inspect the gNB's process listeners failed because the container 'nr-gnb' is unknown to the tool, strongly indicating the container has crashed or is not running. This directly supports the 'gNB failure' aspect of the hypothesis, as a failed gNB container would be unreachable over N2 and N3.

**Probes executed (3):**
- **from: amf, to_ip: gnb_n2_ip** ✓ CONSISTENT
    - *Tool:* `print(default_api.measure_rtt(container = "amf", target_ip = "172.22.0.23"))`
    - *Observation:* [EVIDENCE: measure_rtt("amf", "172.22.0.23") -> "100% packet loss"]
    - *Comment:* The gNB is unreachable from the AMF over the N2 interface path. This result aligns with the hypothesis of a network partition or gNB failure.
- **from: upf, to_ip: gnb_n3_ip** ✓ CONSISTENT
    - *Tool:* `print(default_api.measure_rtt(container = "upf", target_ip = "172.22.0.23"))`
    - *Observation:* [EVIDENCE: measure_rtt("upf", "172.22.0.23") -> "100% packet loss"]
    - *Comment:* The gNB is also unreachable from the UPF over the N3 interface path. This indicates the problem is not specific to the AMF-gNB link and further supports the hypothesis of a full gNB failure or partition.
- **container: nr-gnb** ✓ CONSISTENT
    - *Tool:* `print(default_api.check_process_listeners(container = "nr-gnb"))`
    - *Observation:* [EVIDENCE: check_process_listeners("nr-gnb") -> "Unknown container 'nr-gnb'"]
    - *Comment:* The tool reported that the 'nr-gnb' container is unknown. This is the most direct evidence of a gNB failure, strongly suggesting the container is not running, which would explain its unreachability.

### `h2` — ❌ **DISPROVEN**

**Hypothesis:** The AMF has an internal fault that caused it to drop all N2 associations to the gNBs, even though the process itself is still running. This would lead to a full detachment of all UEs.

**Reasoning:** The evidence contradicts the hypothesis that the AMF 'dropped' N2 associations due to an internal fault. Probes reveal the AMF process is not listening on the N2/SCTP port at all, meaning it was never capable of establishing N2 associations in the first place. This points to a configuration or initialization failure, not a runtime fault that severs existing connections.

**Probes executed (3):**
- **Check if a process in the AMF container is listening on the N2/SCTP port.** ✗ CONTRADICTS
    - *Tool:* `check_process_listeners(container='amf')`
    - *Observation:* [EVIDENCE: check_process_listeners("amf") -> "Netid State  Recv-Q Send-Q Local Address:Port  Peer Address:PortProcess                              \nudp   UNCONN 0      0         127.0.0.11:36247      0.0.0.0:*                                        \ntcp   LISTEN 0      4096      127.0.0.11:42509      0.0.0.0:*                                        \ntcp   LISTEN 0      4096     172.22.0.10:9091…
    - *Comment:* The hypothesis implies the AMF process is running and functional but has dropped connections. The evidence shows the AMF's `open5gs-amfd` process is running but is not listening on any SCTP ports, which are required for the N2 interface. This means it cannot establish N2 associations at all.
- **Check AMF metrics for SCTP or NGAP protocol errors.** ✗ CONTRADICTS
    - *Tool:* `get_nf_metrics()`
    - *Observation:* [EVIDENCE: get_nf_metrics() -> "AMF (via prometheus):\n  amf_session = 4.0  [counter]\n  gnb = 0.0  [gauge, count]  — Direct liveness indicator of the N2 control plane.\n  ran_ue = 0.0  [gauge, count]  — Fundamental RAN health indicator."]
    - *Comment:* The hypothesis expected to see elevated SCTP or NGAP errors. Instead, no such error metrics are present, and the `gnb` gauge is at 0, confirming no gNBs are connected. This is consistent with the AMF not listening on the N2 interface, thus no connections could be formed to generate errors.
- **Check the network status of the AMF.** ~ AMBIGUOUS
    - *Tool:* `get_network_status()`
    - *Observation:* [EVIDENCE: get_network_status() -> "{\n  \"phase\": \"ready\",\n  \"running\": [\n    \"amf\"\n  ],\n  \"containers\": {\n    \"amf\": \"running\"\n  }\n}"]
    - *Comment:* This confirms that the AMF container is running, which is consistent with the hypothesis. However, the tool does not provide the link-level status to the gNB, which was the key part of the planned check. The result doesn't help confirm or deny the core of the hypothesis regarding an internal fault.

**Alternative suspects:** amf


## Evidence Validation (Phase 6)

**Overall verdict:** clean
**Overall confidence:** high

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 4 | 3/3 | clean | high |
| `InvestigatorAgent_h2` | 3 | 3/3 | clean | high |


## Ground Truth

**Failure domain:** data_plane  
**Protocol impact:** GTP-U  
**Affected components:** nr_gnb  
**Severity:** degraded

## Agent Diagnosis

**Model:** v6-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 174.0s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: The entire Radio Access Network (RAN) is down due to a failure of the gNB container, causing a total loss of service as no UEs can connect to the core network.
> - **timeline**:
>     1. The connection between the gNB and the AMF dropped (`core.amf.gnb_association_drop`).
>     2. As a direct result, all UEs connected to the network were lost (`core.amf.ran_ue_full_loss`, `core.amf.ran_ue_sudden_drop`).
>     3. With all UEs disconnected, the SMF tore down all associated PDU sessions (`core.smf.sessions_per_ue_drop`).
> - **root_cause**: The `nr-gnb` container, which constitutes the entire RAN in this deployment, has crashed or is otherwise not running.
> - **affected_components**:
>     - `nr-gnb`: Root Cause
>     - `amf`: Secondary
>     - `smf`: Symptomatic
>     - `upf`: Symptomatic
>     - `ims`: Symptomatic
> - **recommendation**: The operator should verify the state of the `nr-gnb` container on its host. Check the container logs to determine the reason for its termination.
> - **confidence**: high
> - **explanation**: The root cause of the outage is a complete failure of the gNB. The primary hypothesis (`h1`) stated that the RAN had completely detached from the core network due to gNB failure or a network partition. Investigation proved this hypothesis by confirming the gNB was unreachable from both the AMF and the UPF. Crucially, a direct check on the `nr-gnb` container failed, indicating it is not running. The alternative hypothesis (`h2`), which blamed an internal AMF fault, was disproven as the AMF's behavior was a symptom of the gNB's absence, not the cause of it. The gNB failure resulted in a total loss of UE attachments, which explains why all core network components are idle.

### Scoring Breakdown

**Overall score: 100%**

**Scorer assessment:** The agent provided a perfectly accurate diagnosis, correctly identifying the gNB failure as the root cause, its impact, and its location within the network layers with high confidence.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | Yes | The agent correctly identified the 'nr-gnb' container crashing or not running as the root cause, which directly corresponds to the simulated radio link failure and unreachability of the gNB. |
| Component overlap | 100% | The agent correctly identified 'nr-gnb' as the 'Root Cause' in its affected components list. |
| Severity correct | Yes | The agent accurately described the severity as 'entire Radio Access Network (RAN) is down' and 'total loss of service,' which matches the complete unreachability and service disruption caused by the gNB failure. |
| Fault type identified | Yes | The agent identified the fault type as the gNB container being 'crashed or otherwise not running' and 'unreachable,' which accurately describes the observable component unreachability. |
| Layer accuracy | Yes | The agent's network analysis correctly rated the 'ran' layer as 'red,' which is the correct ontology layer for the 'nr_gnb' component. |
| Confidence calibrated | Yes | The agent's diagnosis is highly accurate and well-supported by the provided explanation and evidence, justifying a 'high' confidence level. |

**Ranking position:** #1 — The correct root cause was identified as the primary and only root cause in the final diagnosis.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 146,713 |
| Output tokens | 4,679 |
| Thinking tokens | 11,477 |
| **Total tokens** | **162,869** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| EventAggregator | 0 | 0 | 0 |
| CorrelationAnalyzer | 0 | 0 | 0 |
| NetworkAnalystAgent | 41,227 | 6 | 3 |
| InstructionGeneratorAgent | 24,254 | 3 | 4 |
| InvestigatorAgent_h1 | 46,214 | 4 | 5 |
| InvestigatorAgent_h2 | 45,560 | 3 | 4 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 5,614 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 318.6s
