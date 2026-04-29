# Episode Report: gNB Radio Link Failure

**Agent:** v6  
**Episode ID:** ep_20260429_155442_gnb_radio_link_failure  
**Date:** 2026-04-29T15:54:45.134143+00:00  
**Duration:** 349.7s  

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
- **Nodes with significant deltas:** 1
- **Nodes with any drift:** 2

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 12.08 (per-bucket threshold: 11.07, context bucket (0, 0), trained on 323 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following metrics deviate from their learned-healthy baseline. Treat each as a semantic observation (meaning + numbers), not a number alone — the KB's interpretation is the authoritative reading.

- **`normalized.smf.bearers_per_ue`** (Active QoS bearers per UE) — current **0.00 count** vs learned baseline **2.48 count** (MEDIUM, drop)
    - **What it measures:** Per-UE count of active QoS bearers. Baseline reflects default
bearers; increments during VoNR calls indicate dedicated voice
bearers being set up. Drop during an active call = dedicated
bearer torn down unexpectedly (voice will fail).
    - **Drop means:** Lost bearers. If sustained during a call, voice path is broken.
    - **Healthy typical range:** 2–3.5 count
    - **Healthy invariant:** At rest: equals configured default bearers (typically 2 per UE).
During active VoNR call: +1 per caller. The per-UE ratio is the
invariant; absolute count scales with UE pool.

- **`normalized.smf.sessions_per_ue`** (PDU sessions per attached UE) — current **0.00 count** vs learned baseline **2.00 count** (MEDIUM, drop)
    - **What it measures:** Ratio of established PDU sessions to RAN-attached UEs. Constant under
healthy operation (depends on configured APNs per UE). Drift means
some UEs lost or failed to establish their sessions — usually points
to SMF or UPF control-plane issues, since attachment (ran_ue) is
independent of session establishment.
    - **Drop means:** Some UEs have fewer PDU sessions than they should. Likely SMF or PFCP (N4) issues.
    - **Healthy typical range:** 1.9–2.1 count
    - **Healthy invariant:** Constant equal to configured_apns_per_ue (typically 2). Scale-independent.

- **`normalized.upf.gtp_indatapktn3upf_per_ue`** (GTP-U uplink rate per UE (N3)) — current **0.00 packets_per_second** vs learned baseline **1.45 packets_per_second** (LOW, drop)
    - **What it measures:** Health of the uplink user-plane path gNB → UPF. Drops to near-zero
during RAN or N3 outage; stays nonzero during active calls or data
sessions. Decoupled from SIP signaling (signals data plane, not
control plane).
    - **Drop means:** Data plane dead on uplink — UPF receiving no packets from gNB.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE — constant regardless of UE pool size. Rises during active VoNR calls (~100 pps for G.711 voice) and data transfer.

- **`normalized.upf.gtp_outdatapktn3upf_per_ue`** (GTP-U downlink rate per UE (N3)) — current **0.00 packets_per_second** vs learned baseline **1.45 packets_per_second** (LOW, drop)
    - **What it measures:** Health of the downlink user-plane path UPF → gNB. Typically mirrors
uplink rate during calls/data; asymmetry indicates directional
faults (e.g., UPF receiving from internet but not forwarding).
    - **Drop means:** No traffic leaving UPF toward RAN.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE — constant regardless of UE pool size. Roughly symmetric with uplink during healthy calls.


## Event Aggregation (Phase 1)

**4 events fired during the observation window:**

- `core.amf.gnb_association_drop` (source: `core.amf.gnb`, nf: `amf`, t=1777478202.1)  [current_value=0.0, prior_stable_value=1.0]
- `core.amf.ran_ue_sudden_drop` (source: `core.amf.ran_ue`, nf: `amf`, t=1777478202.1)  [current_value=0.0, prior_stable_value=2.0, delta_percent=-100.0]
- `core.amf.ran_ue_full_loss` (source: `core.amf.ran_ue`, nf: `amf`, t=1777478202.1)  [current_value=0.0, prior_stable_value=2.0]
- `core.smf.sessions_per_ue_drop` (source: `core.smf.sessions_per_ue`, nf: `smf`, t=1777478202.1)  [current_value=0.0, prior_stable_value=2.0, delta_percent=-100.0]

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

### H3: RAN failure confirmed — gNB down, UEs followed
  - primary_nf: amf
  - explanatory_fit: 0.50 (2/4 events)
  - testability: 2 (2 disambiguating metrics)
  - supporting events: `core.amf.gnb_association_drop`, `core.amf.ran_ue_sudden_drop`
  - probes to discriminate:
      - Check core.amf.ran_ue → Whether N2 is dead (both zero) vs. AMF-side attach issue (gnb>0, ran_ue=0)
      - Check core.amf.gnb → gNB-side failure (gnb=0) vs. AMF-side attach-processing issue (gnb>0 but ran_ue=0)


## Network Analysis (Phase 3)

**Summary:** The entire RAN has detached from the 5G core, resulting in a complete outage for all UEs.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | All supporting infrastructure (databases, DNS) are running and responsive. |
| **ran** | 🔴 RED | The nr_gnb container is not running, and all links (N2, N3) to the core are inactive. This is a total failure of the radio access network. |
| **core** | 🟡 YELLOW | Core components are running but are completely idle due to the RAN outage. Metrics for sessions and bearers have dropped to zero as a direct consequence of all UEs disappearing. |
| **ims** | 🟢 GREEN | IMS components are running and appear healthy, although they are receiving no traffic from the core. |

**RAN evidence:**
- core.amf.gnb_association_drop
- core.amf.ran_ue_full_loss

**CORE evidence:**
- core.smf.sessions_per_ue_drop

**Ranked hypotheses:**

- **`h1`** (fit=1.00, nf=nr_gnb, specificity=specific):
    - **Statement:** The nr_gnb (gNodeB) container is down. The process is not running, causing a total loss of the N2 control plane and N3 user plane interfaces to the 5G core.
    - **Supporting events:** `core.amf.gnb_association_drop`, `core.amf.ran_ue_full_loss`, `core.amf.ran_ue_sudden_drop`, `core.smf.sessions_per_ue_drop`
    - **Falsification probes:**
        - Check the container runtime status (e.g., 'docker ps') on the host machine to confirm the nr_gnb container is truly stopped or absent.
        - Review the container logs for nr_gnb to find the reason it terminated.
- **`h2`** (fit=0.80, nf=nr_gnb, specificity=moderate):
    - **Statement:** The gNB is alive but fully partitioned from the 5G core at the network level, severing both N2 (control-plane) and N3 (user-plane) connectivity.
    - **Supporting events:** `core.amf.gnb_association_drop`, `core.amf.ran_ue_full_loss`
    - **Falsification probes:**
        - Measure RTT from the AMF container to the gNB container's IP address. A successful ping would indicate the gNB container is up, disproving H1 and pointing towards a higher-layer partition.
        - Check for firewall rules or network policies that could be blocking SCTP (for N2) and GTP-U (for N3) traffic between the RAN and core.
- **`h3`** (fit=0.60, nf=amf, specificity=specific):
    - **Statement:** The AMF suffered an internal SCTP stack failure that selectively dropped its N2 association to the gNB, causing it to deregister all UEs, even though the AMF process itself remains online.
    - **Supporting events:** `core.amf.gnb_association_drop`, `core.amf.ran_ue_full_loss`
    - **Falsification probes:**
        - Inspect AMF logs for any SCTP error messages, association resets, or stack traces occurring at the time of the failure.
        - If the gNB is confirmed to be running, attempt to manually re-establish the N2 connection from the gNB side. If it succeeds, the fault was likely a transient issue within the AMF.


## Falsification Plans (Phase 4)

**3 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `nr_gnb`)

**Hypothesis:** The nr_gnb (gNodeB) container is down. The process is not running, causing a total loss of the N2 control plane and N3 user plane interfaces to the 5G core.

**Probes (3):**
1. **`get_network_status`** — for all components, but specifically nr_gnb
    - *Expected if hypothesis holds:* The nr_gnb container status is 'exited' or not present in the list.
    - *Falsifying observation:* The nr_gnb container status is 'running'. This directly contradicts the hypothesis.
2. **`check_process_listeners`** — container='nr_gnb'
    - *Expected if hypothesis holds:* The command fails or returns an empty list of listeners, as the process is not running.
    - *Falsifying observation:* The nr_gnb process is listening on the N2/SCTP port (38412). This proves the process is up and ready for control-plane connections.
3. **`measure_rtt`** — from='amf', to_ip='nr_gnb_ip'
    - *Expected if hypothesis holds:* 100% packet loss or host unreachable, as the gNB container is down.
    - *Falsifying observation:* A clean RTT (<5ms) and 0% packet loss, indicating the container is up and responsive on the network.

*Notes:* This plan aims to falsify the most direct and highest-ranked hypothesis. Probes check three different layers of 'down': container runtime state, process listener state, and network reachability.

### Plan for `h2` (target: `nr_gnb`)

**Hypothesis:** The gNB is alive but fully partitioned from the 5G core at the network level, severing both N2 (control-plane) and N3 (user-plane) connectivity.

**Probes (3):**
1. **`measure_rtt`** — from='amf', to_ip='nr_gnb_ip'
    - *Expected if hypothesis holds:* 100% packet loss, indicating a complete network partition.
    - *Falsifying observation:* Any successful packet return (e.g., RTT < 5ms, loss < 100%) proves connectivity exists, falsifying the 'fully partitioned' claim.
2. **`measure_rtt`** — from='amf', to_ip='upf_ip'
    - *Expected if hypothesis holds:* Clean RTT (<5ms), indicating the AMF's network stack is fine and the issue is specific to the gNB path.
    - *Falsifying observation:* 100% packet loss. This would suggest the AMF itself is partitioned from the network, not just the gNB, shifting the likely fault location.
3. **`get_network_status`** — for component 'nr_gnb'
    - *Expected if hypothesis holds:* The nr_gnb container status is 'running', as per the hypothesis 'gNB is alive'.
    - *Falsifying observation:* The nr_gnb container status is 'exited'. This falsifies H2 and confirms H1.

*Notes:* This plan tests the network partition theory. It includes a mandatory triangulation probe (AMF to UPF) to isolate the partition and avoid incorrectly blaming the RAN-Core path if the AMF itself is the source of the problem.

### Plan for `h3` (target: `amf`)

**Hypothesis:** The AMF suffered an internal SCTP stack failure that selectively dropped its N2 association to the gNB, causing it to deregister all UEs, even though the AMF process itself remains online.

**Probes (3):**
1. **`get_nf_metrics`** — component='amf'
    - *Expected if hypothesis holds:* One or more SCTP error metrics (e.g., sctp_assocs_aborted, sctp_errors) should have a non-zero value.
    - *Falsifying observation:* All SCTP-related error and drop counters on the AMF are zero, suggesting its SCTP stack is healthy.
2. **`get_network_status`** — for component 'nr_gnb'
    - *Expected if hypothesis holds:* The nr_gnb container status is 'running'.
    - *Falsifying observation:* The nr_gnb container status is 'exited'. This would prove the AMF dropped the association because the gNB was gone, making this a symptom, not a cause.
3. **`get_nf_metrics`** — component='nr_gnb'
    - *Expected if hypothesis holds:* A metric like 'n2_sctp_packets_out' is > 0, showing the gNB is attempting to communicate with the AMF.
    - *Falsifying observation:* The 'n2_sctp_packets_out' metric on the gNB is 0. This implies the gNB is not even trying to send N2 traffic, which contradicts the idea that the AMF is the sole party at fault for the lost association.

*Notes:* This plan focuses on the AMF as the potential root cause. It uses a combination of checking AMF internal metrics, verifying the gNB is actually up (to rule out a cascading failure), and checking gNB egress traffic (as an activity-vs-drops discriminator).


## Parallel Investigators (Phase 5)

**3 sub-Investigator verdict(s):** **1 NOT_DISPROVEN**, **2 DISPROVEN**

### `h1` — ✅ **NOT_DISPROVEN**

**Hypothesis:** The nr_gnb (gNodeB) container is down. The process is not running, causing a total loss of the N2 control plane and N3 user plane interfaces to the 5G core.

**Reasoning:** All three executed probes returned results consistent with the hypothesis. The container status check confirmed 'nr_gnb' is not running, the process listener check failed as expected for a down container, and a network reachability test from the AMF to the gNB's IP showed 100% packet loss. No contradictory evidence was found.

**Probes executed (3):**
- **Check the container runtime status for nr_gnb.** ✓ CONSISTENT
    - *Tool:* `default_api.get_network_status()`
    - *Observation:* [EVIDENCE: get_network_status() -> "The list of running containers does not include 'nr_gnb'."]
    - *Comment:* The container status confirms that 'nr_gnb' is not running, which is the core assertion of the hypothesis.
- **Check if the nr_gnb process is listening on any ports.** ✓ CONSISTENT
    - *Tool:* `default_api.check_process_listeners(container='nr_gnb')`
    - *Observation:* [EVIDENCE: check_process_listeners("nr_gnb") -> "Unknown container 'nr_gnb'."]
    - *Comment:* The tool reports that the container is unknown. This is expected if the container is down and not running, thus supporting the hypothesis.
- **Measure RTT from AMF to the nr_gnb IP to check for network reachability.** ✓ CONSISTENT
    - *Tool:* `default_api.measure_rtt(container='amf', target_ip='172.22.0.23')`
    - *Observation:* [EVIDENCE: measure_rtt("amf", "172.22.0.23") -> "3 packets transmitted, 0 received, 100% packet loss"]
    - *Comment:* The nr_gnb IP is unreachable from the AMF. This aligns with the expectation that a downed container would be offline and unresponsive to pings.

### `h2` — ❌ **DISPROVEN**

**Hypothesis:** The gNB is alive but fully partitioned from the 5G core at the network level, severing both N2 (control-plane) and N3 (user-plane) connectivity.

**Reasoning:** The hypothesis claims a specific network partition between the gNB and the core. However, the triangulation probe from the AMF to the UPF also resulted in 100% packet loss, just like the probe to the gNB. This indicates the AMF itself is partitioned from the network, contradicting the hypothesis that the partition is specific to the gNB. The fault is likely with the AMF or its immediate network environment.

**Probes executed (3):**
- **from='amf', to_ip='nr_gnb_ip'** ✓ CONSISTENT
    - *Tool:* `measure_rtt(container = "amf", target_ip = "172.22.0.4")`
    - *Observation:* [EVIDENCE: measure_rtt("amf", "172.22.0.4") -> "100% packet loss"]
    - *Comment:* The packet loss from AMF to the gNB's IP is consistent with the 'fully partitioned' aspect of the hypothesis.
- **from='amf', to_ip='upf_ip'** ✗ CONTRADICTS
    - *Tool:* `measure_rtt(container = "amf", target_ip = "172.22.0.6")`
    - *Observation:* [EVIDENCE: measure_rtt("amf", "172.22.0.6") -> "100% packet loss"]
    - *Comment:* This falsifies the hypothesis. A failure here indicates the AMF is the likely source of the network problem, as it cannot reach other core components either, not just the gNB. This contradicts the expectation that the AMF's network stack is fine.
- **for component 'nr_gnb'** ~ AMBIGUOUS
    - *Tool:* `get_network_status()`
    - *Observation:* [EVIDENCE: get_network_status() -> "The 'nr_gnb' container is not listed in the status output."]
    - *Comment:* The hypothesis states the gNB is 'alive'. The network status tool did not list the nr_gnb container at all, making it impossible to confirm or deny its status from this probe. While this doesn't directly falsify the hypothesis, the RTT probes provide a clear contradiction.

**Alternative suspects:** amf

### `h3` — ❌ **DISPROVEN**

**Hypothesis:** The AMF suffered an internal SCTP stack failure that selectively dropped its N2 association to the gNB, causing it to deregister all UEs, even though the AMF process itself remains online.

**Reasoning:** The hypothesis is disproven because evidence shows the nr_gnb container is not running. The AMF dropping the N2 association is the correct response to its peer disappearing, not the result of an internal SCTP stack failure. The fault lies with the gNB, not the AMF.

**Probes executed (3):**
- **Check AMF SCTP error metrics to see if the SCTP stack is healthy.** ~ AMBIGUOUS
    - *Tool:* `print(default_api.get_nf_metrics())`
    - *Observation:* [EVIDENCE: get_nf_metrics() -> "AMF (via prometheus):\n  amf_session = 4.0  [counter]\n  gnb = 0.0  [gauge, count]  — Direct liveness indicator of the N2 control plane.\n  ran_ue = 0.0  [gauge, count]  — Fundamental RAN health indicator."]
    - *Comment:* The metrics did not include any specific SCTP error counters. While this doesn't confirm the hypothesis, it also doesn't contradict it, as the metrics might not be exported. The `gnb = 0.0` gauge confirms the association is down, which is known.
- **Check the network status of the 'nr_gnb' to see if it is running.** ✗ CONTRADICTS
    - *Tool:* `print(default_api.get_network_status())`
    - *Observation:* [EVIDENCE: get_network_status() -> "{\n  \"phase\": \"ready\",\n  \"running\": [..., \"amf\", ...],\n  \"down_or_absent\": [],\n  \"containers\": { ... }\n}"]
    - *Comment:* The 'nr_gnb' container is not listed as running. The hypothesis assumes the gNB is online for the AMF to selectively drop the connection. Since the gNB is down, the AMF's behavior is a symptom, not the cause. This falsifies the hypothesis.
- **Check gNB egress traffic to see if it is attempting to communicate with the AMF.** ✗ CONTRADICTS
    - *Tool:* `print(default_api.get_nf_metrics())`
    - *Observation:* [EVIDENCE: get_nf_metrics() -> The command returned no metrics for the 'nr_gnb' component.]
    - *Comment:* The absence of any metrics for 'nr_gnb' is consistent with the 'nr_gnb' container being down, as confirmed by the get_network_status probe. A down gNB cannot send any packets, which contradicts the expectation that the gNB is actively trying to communicate. This further falsifies the hypothesis.

**Alternative suspects:** nr_gnb


## Evidence Validation (Phase 6)

**Overall verdict:** clean
**Overall confidence:** high

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 4 | 3/3 | clean | high |
| `InvestigatorAgent_h2` | 3 | 3/3 | clean | high |
| `InvestigatorAgent_h3` | 2 | 3/3 | clean | high |


## Ground Truth

**Failure domain:** data_plane  
**Protocol impact:** GTP-U  
**Affected components:** nr_gnb  
**Severity:** degraded

## Agent Diagnosis

**Model:** v6-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 195.0s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: The entire Radio Access Network (RAN) has detached from the 5G core because the `nr_gnb` (gNodeB) container is down, resulting in a complete outage for all user devices.
> - **timeline**:
>     1. The `nr_gnb` container terminated unexpectedly.
>     2. The AMF detected the loss of its N2 peer, triggering a `gnb_association_drop` event.
>     3. The AMF deregistered all UEs associated with the lost gNB, causing `ran_ue_full_loss` and `ran_ue_sudden_drop` events.
>     4. The SMF was notified of the UE de-registrations and tore down all associated PDU sessions, causing the `sessions_per_ue_drop` metric to fall to zero.
> - **root_cause**: The `nr_gnb` container has stopped running. The process is no longer active, severing all connectivity between the RAN and the core network. The primary suspect is `nf=nr_gnb`.
> - **affected_components**:
>     - `nr_gnb`: Root Cause
>     - `amf`: Symptomatic
>     - `smf`: Symptomatic
> - **recommendation**: Verify the status of the `nr_gnb` container on its host machine. If confirmed down, investigate the container's logs to determine the cause of the unexpected termination.
> - **confidence**: high
> - **explanation**: The investigation confirmed that the gNodeB container (`nr_gnb`) is not running. This aligns perfectly with hypothesis `h1`, which was the only hypothesis not disproven by the evidence. Probes verified that the container process is absent and that its IP address is unreachable. Alternative hypotheses suggesting a network partition (`h2`) or an internal AMF failure (`h3`) were disproven, as they were predicated on the gNB being online. The AMF's behavior of dropping the N2 association was a correct and expected response to its peer disappearing, making it a symptom, not the cause. The gNB failure is the definitive root cause of the outage.

### Scoring Breakdown

**Overall score: 100%**

**Scorer assessment:** The agent provided a perfectly accurate and well-supported diagnosis, correctly identifying the root cause, affected components, severity, fault type, and layer, with appropriate confidence.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | Yes | The agent correctly identified that the 'nr_gnb' container stopped running, which directly leads to the simulated 'nr_gnb' component being completely unreachable/down. This is semantically equivalent to the simulated failure mode. |
| Component overlap | 100% | The agent correctly identified 'nr_gnb' as the 'Root Cause' in its 'affected_components' list, which is the primary affected component in the simulated failure. |
| Severity correct | Yes | The agent correctly described the situation as a 'complete outage for all user devices' and 'severing all connectivity', matching the simulated failure of 'component completely unreachable' and 'all UEs lose 5G registration'. |
| Fault type identified | Yes | The agent identified that the 'nr_gnb' container 'stopped running' and is 'no longer active', leading to 'severing all connectivity'. This accurately describes a component unreachable/down fault type. |
| Layer accuracy | Yes | The agent's network analysis correctly rated the 'ran' layer as 'red' and explicitly mentioned the 'nr_gnb container is not running' as the reason, aligning with 'nr_gnb' belonging to the 'ran' layer. |
| Confidence calibrated | Yes | The agent stated 'high' confidence, which is appropriate given the accuracy and thoroughness of its diagnosis, including disproving alternative hypotheses. |

**Ranking position:** #1 — The agent provided a single, definitive root cause in its final diagnosis, which was correct.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 162,583 |
| Output tokens | 5,143 |
| Thinking tokens | 18,126 |
| **Total tokens** | **185,852** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| EventAggregator | 0 | 0 | 0 |
| CorrelationAnalyzer | 0 | 0 | 0 |
| NetworkAnalystAgent | 44,098 | 6 | 3 |
| InstructionGeneratorAgent | 28,758 | 2 | 3 |
| InvestigatorAgent_h1 | 44,836 | 4 | 5 |
| InvestigatorAgent_h2 | 27,486 | 3 | 2 |
| InvestigatorAgent_h3 | 34,396 | 2 | 3 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 6,278 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 349.7s
