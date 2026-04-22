# Episode Report: gNB Radio Link Failure

**Agent:** v6  
**Episode ID:** ep_20260422_030627_gnb_radio_link_failure  
**Date:** 2026-04-22T03:06:29.263821+00:00  
**Duration:** 323.2s  

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
- **Nodes with any drift:** 3

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 0.98 (threshold: 0.70, trained on 211 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

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

- **`normalized.smf.bearers_per_ue`** (Active QoS bearers per UE) — current **0.00 count** vs learned baseline **2.61 count** (HIGH, drop)
    - **What it measures:** Per-UE count of active QoS bearers. Baseline reflects default
bearers; increments during VoNR calls indicate dedicated voice
bearers being set up. Drop during an active call = dedicated
bearer torn down unexpectedly (voice will fail).
    - **Drop means:** Lost bearers. If sustained during a call, voice path is broken.
    - **Healthy typical range:** 2–3.5 count
    - **Healthy invariant:** At rest: equals configured default bearers (typically 2 per UE).
During active VoNR call: +1 per caller. The per-UE ratio is the
invariant; absolute count scales with UE pool.

- **`normalized.upf.gtp_outdatapktn3upf_per_ue`** (GTP-U downlink rate per UE (N3)) — current **0.00 packets_per_second** vs learned baseline **3.34 packets_per_second** (MEDIUM, drop)
    - **What it measures:** Health of the downlink user-plane path UPF → gNB. Typically mirrors
uplink rate during calls/data; asymmetry indicates directional
faults (e.g., UPF receiving from internet but not forwarding).
    - **Drop means:** No traffic leaving UPF toward RAN.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE — constant regardless of UE pool size. Roughly symmetric with uplink during healthy calls.

- **`normalized.upf.gtp_indatapktn3upf_per_ue`** (GTP-U uplink rate per UE (N3)) — current **0.00 packets_per_second** vs learned baseline **3.42 packets_per_second** (MEDIUM, drop)
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

**4 events fired during the observation window:**

- `core.amf.ran_ue_sudden_drop` (source: `core.amf.ran_ue`, nf: `amf`, t=1776827307.2)  [current_value=0.0, prior_stable_value=2.0, delta_percent=-100.0]
- `core.amf.ran_ue_full_loss` (source: `core.amf.ran_ue`, nf: `amf`, t=1776827307.2)  [current_value=0.0, prior_stable_value=2.0]
- `core.amf.gnb_association_drop` (source: `core.amf.gnb`, nf: `amf`, t=1776827307.2)  [current_value=0.0, prior_stable_value=1.0]
- `core.smf.sessions_per_ue_drop` (source: `core.smf.sessions_per_ue`, nf: `smf`, t=1776827307.2)  [current_value=0.0, prior_stable_value=2.0, delta_percent=-100.0]

## Correlation Analysis (Phase 2)

**Correlation engine produced 5 ranked composite hypotheses from 4 fired events (showing top 3 of 5):**

### H1: gNB/N2 failure — RAN access lost for both gNB and UEs
  - primary_nf: amf
  - explanatory_fit: 0.50 (2/4 events)
  - testability: 2 (2 disambiguating metrics)
  - supporting events: `core.amf.gnb_association_drop`, `core.amf.ran_ue_sudden_drop`
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

**Summary:** The root cause is a complete RAN failure; the gNB has lost its connection to the AMF, causing a full outage for all UEs.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | All core and IMS NF containers are up. The issue is not at the container orchestration level. |
| **ran** | 🔴 RED | The RAN is completely disconnected from the core network. No gNBs are attached to the AMF, and consequently, no UEs are attached. |
| **core** | 🟡 YELLOW | The core network is operationally healthy but is experiencing a complete loss of user sessions and traffic due to the upstream RAN failure. These are symptoms, not the root cause. |
| **ims** | 🟡 YELLOW | The IMS system is healthy but has no active calls because no UEs are connected to the network to initiate them. |

**RAN evidence:**
- get_network_topology() shows INACTIVE links for N2, N3, and Air Interface.
- get_nf_metrics() shows amf.gnb = 0 and amf.ran_ue = 0.
- Fired events core.amf.gnb_association_drop and core.amf.ran_ue_full_loss.

**CORE evidence:**
- normalized.smf.sessions_per_ue dropped to 0.
- normalized.smf.bearers_per_ue dropped to 0.
- normalized.upf.gtp_outdatapktn3upf_per_ue and normalized.upf.gtp_indatapktn3upf_per_ue dropped to 0.

**IMS evidence:**
- normalized.pcscf.dialogs_per_ue dropped to 0.

**Ranked hypotheses:**

- **`h1`** (fit=0.95, nf=nr_gnb, specificity=specific):
    - **Statement:** The gNB has failed or is partitioned from the AMF, causing a total loss of the N2 interface. This is the primary upstream failure leading to all other symptoms.
    - **Supporting events:** `core.amf.gnb_association_drop`, `core.amf.ran_ue_sudden_drop`, `core.amf.ran_ue_full_loss`
    - **Falsification probes:**
        - Check logs on the gNB for errors.
        - Check network connectivity from the gNB container/host to the AMF's N2 IP address.
- **`h2`** (fit=0.70, nf=amf, specificity=moderate):
    - **Statement:** The AMF has an internal fault specifically affecting its N2 interface handling, causing it to drop the gNB association. While the AMF container is running, this specific service within it has failed.
    - **Supporting events:** `core.amf.gnb_association_drop`, `core.amf.ran_ue_full_loss`
    - **Falsification probes:**
        - Check AMF logs for any N2-related errors or stack traces.
        - Attempt to connect a new, known-good gNB to the AMF. If it also fails, the AMF is the likely culprit.
- **`h3`** (fit=0.50, nf=smf, specificity=vague):
    - **Statement:** All PDU sessions and bearers were lost because the UEs detached from the network, which was caused by the loss of RAN connectivity.
    - **Supporting events:** `core.smf.sessions_per_ue_drop`
    - **Falsification probes:**
        - Restore RAN connectivity; if sessions are re-established, this hypothesis is confirmed as a consequence, not a cause.


## Falsification Plans (Phase 4)

**3 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `nr_gnb`)

**Hypothesis:** The gNB has failed or is partitioned from the AMF, causing a total loss of the N2 interface. This is the primary upstream failure leading to all other symptoms.

**Probes (3):**
1. **`get_network_status`** — target: nr_gnb
    - *Expected if hypothesis holds:* The nr_gnb container status is 'exited' or 'unhealthy'. This would be a direct confirmation of gNB failure.
    - *Falsifying observation:* The nr_gnb container is in a 'running' and 'healthy' state. This would falsify the 'gNB has failed' part of the hypothesis, leaving the 'partition' as the remaining possibility.
2. **`measure_rtt`** — from: nr_gnb, to: amf_ip
    - *Expected if hypothesis holds:* 100% packet loss. This would confirm a network partition or a failure of the AMF's network stack.
    - *Falsifying observation:* A clean RTT (< 5ms) is measured. This would prove that the gNB and AMF have IP-level connectivity, falsifying the network partition hypothesis.
3. **`measure_rtt`** — from: amf, to: gnb_ip (triangulation probe)
    - *Expected if hypothesis holds:* 100% packet loss. Confirms a bidirectional partition.
    - *Falsifying observation:* A clean RTT (< 5ms). If the reverse path works but the forward path (probe 2) fails, it suggests an asymmetric issue like a misconfigured firewall on the gNB host.

*Notes:* This plan first checks for a simple container crash (the most likely failure), then for a network partition, which is the other possibility covered by the hypothesis. The triangulation probe helps isolate the location of a potential partition.

### Plan for `h2` (target: `amf`)

**Hypothesis:** The AMF has an internal fault specifically affecting its N2 interface handling, causing it to drop the gNB association. While the AMF container is running, this specific service within it has failed.

**Probes (3):**
1. **`check_process_listeners`** — container: amf
    - *Expected if hypothesis holds:* The AMF process is NOT listening on the N2/SCTP port (38412). This would indicate the N2 handling component inside the AMF has crashed or failed to start.
    - *Falsifying observation:* The AMF process is actively listening on port 38412. This proves the transport layer for the N2 interface is up and ready, suggesting any issue is higher in the application logic.
2. **`get_nf_metrics`** — Look for AMF metrics related to N11 (SMF interface) activity.
    - *Expected if hypothesis holds:* Metrics for other interfaces (like N11 requests to SMF) are zero or unchanged, indicating a failure specific to the N2 interface.
    - *Falsifying observation:* Metrics for other interfaces show healthy activity. This would strongly isolate the fault to the N2 interface stack, as the rest of the AMF is working. Conversely if ALL AMF metrics are frozen, it indicates a wider AMF failure.
3. **`measure_rtt`** — from: nr_gnb, to: amf_ip
    - *Expected if hypothesis holds:* Clean RTT (< 5ms). This hypothesis assumes an internal AMF application fault, not a network-level partition.
    - *Falsifying observation:* 100% packet loss. This observation would falsify H2 because it indicates a network partition, which directly supports H1 instead.

*Notes:* This plan focuses on proving that the AMF container is reachable but internally broken specifically at the N2 interface. It contrasts with H1 by expecting network connectivity to be healthy.

### Plan for `h3` (target: `smf`)

**Hypothesis:** All PDU sessions and bearers were lost because the UEs detached from the network, which was caused by the loss of RAN connectivity.

**Probes (3):**
1. **`get_nf_metrics`** — Look for any SMF-specific error counters (e.g., N4, N11, PFCP errors).
    - *Expected if hypothesis holds:* All SMF-internal error counters are zero. The only anomalous metric should be the drop in session count, which is a symptom of the upstream failure.
    - *Falsifying observation:* One or more SMF error counters (e.g., `pfcp_session_establishment_errors`, `n11_request_failures`) are non-zero. This would suggest the SMF has its own problems and could be a contributing cause, not just a downstream victim.
2. **`measure_rtt`** — from: smf, to: upf_ip
    - *Expected if hypothesis holds:* Clean RTT (< 5ms). This shows the SMF's critical data plane dependency (N4 interface to UPF) is healthy.
    - *Falsifying observation:* High packet loss or latency. This would indicate a network problem affecting the SMF, making it a more likely candidate for the root cause.
3. **`get_network_status`** — target: smf
    - *Expected if hypothesis holds:* The SMF container is in a 'running' and 'healthy' state.
    - *Falsifying observation:* The SMF container status is 'exited' or 'unhealthy'. This would falsify the hypothesis that the SMF is just a victim and would make it a primary suspect.

*Notes:* This plan treats H3 as a 'null hypothesis' for the SMF. The goal is to confirm the SMF is healthy and is only reflecting an upstream problem. Any observation that proves the SMF is unhealthy in its own right will falsify this hypothesis.


## Parallel Investigators (Phase 5)

**3 sub-Investigator verdict(s):** **3 NOT_DISPROVEN**

### `h1` — ✅ **NOT_DISPROVEN**

**Hypothesis:** The gNB has failed or is partitioned from the AMF, causing a total loss of the N2 interface. This is the primary upstream failure leading to all other symptoms.

**Reasoning:** The evidence gathered is consistent with the hypothesis. A network reachability test from the AMF to the gNB's IP address showed 100% packet loss, which supports the 'network partition' part of the hypothesis. While the status of the gNB container itself could not be verified due to tool limitations (it was not a known container), no evidence was found to contradict the hypothesis.

**Probes executed (3):**
- **Check the status of all network function containers to see if the nr_gnb has exited.** ~ AMBIGUOUS
    - *Tool:* `get_network_status()`
    - *Observation:* [EVIDENCE: get_network_status() -> "'containers': {'mongo': 'running', 'nrf': 'running', ...}"]
    - *Comment:* The tool output did not include the status for 'nr_gnb', making this probe inconclusive. The tool appears to only monitor core network functions.
- **Check network connectivity from gNB to AMF to test for a partition.** ~ AMBIGUOUS
    - *Tool:* `measure_rtt("nr_gnb", "172.22.0.10")`
    - *Observation:* [EVIDENCE: measure_rtt("nr_gnb", "172.22.0.10") -> "Unknown container 'nr_gnb'"]
    - *Comment:* The probe could not be executed because the 'nr_gnb' container is not accessible by this tool. This prevented a direct test of the gNB-to-AMF network path.
- **Check network connectivity from AMF to gNB to test for a partition (triangulation probe).** ✓ CONSISTENT
    - *Tool:* `measure_rtt("amf", "172.22.0.23")`
    - *Observation:* [EVIDENCE: measure_rtt("amf", "172.22.0.23") -> "100% packet loss"]
    - *Comment:* This result shows that the AMF cannot reach the gNB at the IP layer. This is strong evidence for a network partition, which is consistent with the hypothesis.

### `h2` — ✅ **NOT_DISPROVEN**

**Hypothesis:** The AMF has an internal fault specifically affecting its N2 interface handling, causing it to drop the gNB association. While the AMF container is running, this specific service within it has failed.

**Reasoning:** The executed probes both provided evidence consistent with the hypothesis. The AMF process is not listening on the N2/SCTP port 38412, which directly supports the claim that the N2 interface handling service within the AMF has failed. Furthermore, metrics confirm that there are zero associated gNBs. An attempt to test for a network partition (which would have falsified the hypothesis) failed due to tool limitations, leaving no contradictory evidence.

**Probes executed (3):**
- **Check if the AMF process is listening on the N2/SCTP port (38412).** ✓ CONSISTENT
    - *Tool:* `check_process_listeners(container='amf')`
    - *Observation:* [EVIDENCE: check_process_listeners("amf") -> "tcp   LISTEN 0      4096     172.22.0.10:9091       0.0.0.0:*    users:((\"open5gs-amfd\",pid=8,fd=10))\ntcp   LISTEN 0      5        172.22.0.10:7777       0.0.0.0:*    users:((\"open5gs-amfd\",pid=8,fd=11)) "]
    - *Comment:* The output confirms the amf process is running, but it is NOT listening on the expected N2 interface port 38412 (SCTP). This directly supports the hypothesis that the N2 service within the AMF has failed to initialize or has crashed.
- **Look for AMF metrics related to N2 and other interfaces (like N11).** ✓ CONSISTENT
    - *Tool:* `get_nf_metrics()`
    - *Observation:* [EVIDENCE: get_nf_metrics() -> "AMF (via prometheus):\n  gnb = 0.0  [gauge, count]  — Direct liveness indicator of the N2 control plane.\n  ran_ue = 0.0  [gauge, count]  — Fundamental RAN health indicator."]
    - *Comment:* The metrics explicitly show `gnb = 0.0`, confirming no gNBs are connected via the N2 interface. The absence of other metrics like N11 activity prevents a full comparison, but the available data is fully consistent with a failed N2 interface.
- **Measure RTT from gNB to AMF to check for a network partition.** ~ AMBIGUOUS
    - *Tool:* `measure_rtt(container='nr-gnb', target_ip='172.22.0.10')`
    - *Observation:* [EVIDENCE: measure_rtt("nr-gnb", "172.22.0.10") -> "Unknown container 'nr-gnb'."]
    - *Comment:* This probe could not be completed as planned because the 'nr-gnb' container is not available to the tool, so no conclusion about network connectivity could be drawn from this attempt. It neither supports nor contradicts the hypothesis.

### `h3` — ✅ **NOT_DISPROVEN**

**Hypothesis:** All PDU sessions and bearers were lost because the UEs detached from the network, which was caused by the loss of RAN connectivity.

**Reasoning:** All probes confirmed that the SMF is healthy. There are no SMF-internal error metrics, the container is running, and its N4 interface to the UPF is healthy. This aligns with the hypothesis that the SMF is only a downstream victim of an external failure.

**Probes executed (3):**
- **Look for any SMF-specific error counters (e.g., N4, N11, PFCP errors).** ✓ CONSISTENT
    - *Tool:* `get_nf_metrics()`
    - *Observation:* [EVIDENCE: get_nf_metrics() -> "SMF [4 PDU] (via prometheus): bearers_active = 4.0, fivegs_smffunction_sm_sessionnbr = 4.0, pfcp_sessions_active = 4.0, ues_active = 2.0"]
    - *Comment:* The metrics show no error counters for the SMF. The session counts appear to be from before the final outage, but the absence of error flags is the key observation, and it supports the hypothesis that the SMF is not faulty.
- **The SMF container is in a 'running' and 'healthy' state.** ✓ CONSISTENT
    - *Tool:* `get_network_status()`
    - *Observation:* [EVIDENCE: get_network_status() -> "'smf': 'running'"]
    - *Comment:* The SMF container is running, which is consistent with the hypothesis that the SMF itself has not failed.
- **from: smf, to: upf_ip** ✓ CONSISTENT
    - *Tool:* `measure_rtt("smf", "172.22.0.8")`
    - *Observation:* [EVIDENCE: measure_rtt("smf", "172.22.0.8") -> "rtt min/avg/max/mdev = 0.123/0.152/0.185/0.025 ms"]
    - *Comment:* The RTT from the SMF to the UPF is excellent, with 0% packet loss. This confirms the N4 interface, a critical dependency for the SMF, is healthy. This result strongly supports that the SMF is not the locus of the failure.


## Evidence Validation (Phase 6)

**Overall verdict:** clean
**Overall confidence:** high

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 4 | 3/3 | clean | high |
| `InvestigatorAgent_h2` | 3 | 3/3 | clean | high |
| `InvestigatorAgent_h3` | 4 | 3/3 | clean | high |


## Ground Truth

**Failure domain:** data_plane  
**Protocol impact:** GTP-U  
**Affected components:** nr_gnb  
**Severity:** degraded

## Agent Diagnosis

**Model:** v6-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 182.6s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: A combination of an AMF internal fault and a network partition has caused a complete RAN outage, disconnecting the gNB and all UEs from the core network.
> - **timeline**:
>     1. The `core.amf.gnb_association_drop` event indicates the N2 link between the gNB and AMF was lost.
>     2. This was immediately followed by `core.amf.ran_ue_sudden_drop` and `core.amf.ran_ue_full_loss`, as all UEs connected via that gNB were also lost.
>     3. As a downstream consequence, the SMF registered a loss of PDU sessions, reflected in the `core.smf.sessions_per_ue_drop` event.
> - **root_cause**: Multiple contributing factors prevent a single root cause determination. The primary suspects are:
>     1. An internal fault in the **AMF** (`primary_suspect_nf: amf`), which is not listening on its N2 interface port (SCTP/38412).
>     2. A network partition between the AMF and the gNB (`primary_suspect_nf: nr_gnb`), confirmed by 100% packet loss from the AMF to the gNB's IP.
> - **affected_components**:
>     - `nr_gnb`: Root Cause (Partitioned from network)
>     - `amf`: Root Cause (Internal N2 interface fault)
>     - `smf`: Symptomatic (Lost sessions due to UE detachment)
>     - `ims`: Symptomatic (No active calls due to no registered UEs)
> - **recommendation**: The evidence points to two distinct faults that must be investigated.
>     1. On the AMF, verify why the `open5gs-amfd` process is not listening on the N2/SCTP port 38412. Check AMF logs for errors during initialization or related to the N2 interface.
>     2. Investigate the network path between the AMF container (`172.22.0.10`) and the gNB's last known IP address (`172.22.0.23`) to identify the source of the 100% packet loss.
> - **confidence**: medium
> - **explanation**: The investigation could not falsify multiple competing hypotheses, indicating a complex failure scenario. Evidence strongly supports hypothesis `h2`, as the AMF process is verifiably not listening on its N2 port, pointing to an internal service fault. Simultaneously, evidence supports hypothesis `h1`, as a network reachability test showed 100% packet loss from the AMF to the gNB, confirming a network partition. Because both an application-level fault (AMF) and a network-level fault (partition) are present and could be causal, confidence is `medium`. The SMF session loss (`h3`) was confirmed to be a downstream symptom.

### Scoring Breakdown

**Overall score: 60%**

**Scorer assessment:** The agent correctly identified the symptoms, severity, and fault type of the RAN outage, and attributed it to the correct layer. It also correctly identified the gNB as a root cause component. However, its final diagnosis was ambiguous, presenting an incorrect AMF internal fault as an equally likely root cause, which lowered its overall root cause accuracy. Its confidence was appropriately calibrated given this ambiguity.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | No | The agent correctly identified the network partition/unreachability of the gNB as a primary suspect for the root cause. However, it also listed an 'internal fault in the AMF' as an equally weighted primary suspect, and explicitly stated that 'Multiple contributing factors prevent a single root cause determination.' The inclusion of an incorrect primary root cause and the ambiguity in determining a single root cause means it did not definitively identify the simulated failure mode as THE root cause. |
| Component overlap | 100% | The primary affected component, 'nr_gnb', is correctly identified and explicitly labeled as 'Root Cause' in the 'affected_components' list. The agent also correctly identifies 'smf' and 'ims' as symptomatic. While it incorrectly labels 'amf' as a 'Root Cause', the presence of the correct primary component with the 'Root Cause' label satisfies the criteria for a 1.0 score. |
| Severity correct | Yes | The simulated failure resulted in a complete outage ('Component completely unreachable', 'All UEs lose 5G registration'). The agent's diagnosis describes a 'complete RAN outage' and '100% packet loss', which accurately reflects a complete service disruption. |
| Fault type identified | Yes | The agent identified the fault as a 'network partition between the AMF and the gNB' and confirmed by '100% packet loss', which accurately describes the observable fault type of component unreachability/isolation. |
| Layer accuracy | Yes | The ground truth states 'nr_gnb' belongs to the 'ran' layer. The agent's 'NETWORK ANALYSIS' correctly rated the 'ran' layer as 'red' and provided relevant evidence for a RAN failure (inactive N2/N3 links, gNB association drop). |
| Confidence calibrated | Yes | The agent stated 'medium' confidence and provided a clear explanation that this was due to 'multiple competing hypotheses' and the inability to falsify them, leading to two distinct faults being present and potentially causal. Given that one of its primary root causes was incorrect, a medium confidence is appropriate and well-calibrated. |

**Ranking position:** #2 — The agent listed two 'primary suspects' for the root cause, numbered '1.' and '2.'. The correct cause (network partition between AMF and gNB) was listed as the second item.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 181,426 |
| Output tokens | 5,561 |
| Thinking tokens | 15,597 |
| **Total tokens** | **202,584** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| EventAggregator | 0 | 0 | 0 |
| CorrelationAnalyzer | 0 | 0 | 0 |
| NetworkAnalystAgent | 36,227 | 3 | 4 |
| InstructionGeneratorAgent | 20,239 | 3 | 2 |
| InvestigatorAgent_h1 | 43,214 | 4 | 5 |
| InvestigatorAgent_h2 | 34,578 | 3 | 4 |
| InvestigatorAgent_h3 | 60,934 | 4 | 5 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 7,392 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 323.2s
