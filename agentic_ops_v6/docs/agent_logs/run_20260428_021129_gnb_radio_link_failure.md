# Episode Report: gNB Radio Link Failure

**Agent:** v6  
**Episode ID:** ep_20260428_020605_gnb_radio_link_failure  
**Date:** 2026-04-28T02:06:07.272671+00:00  
**Duration:** 321.6s  

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

**ANOMALY DETECTED.** Overall anomaly score: 0.99 (threshold: 0.70, trained on 104 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

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

- **`normalized.smf.bearers_per_ue`** (Active QoS bearers per UE) — current **0.00 count** vs learned baseline **2.59 count** (HIGH, drop)
    - **What it measures:** Per-UE count of active QoS bearers. Baseline reflects default
bearers; increments during VoNR calls indicate dedicated voice
bearers being set up. Drop during an active call = dedicated
bearer torn down unexpectedly (voice will fail).
    - **Drop means:** Lost bearers. If sustained during a call, voice path is broken.
    - **Healthy typical range:** 2–3.5 count
    - **Healthy invariant:** At rest: equals configured default bearers (typically 2 per UE).
During active VoNR call: +1 per caller. The per-UE ratio is the
invariant; absolute count scales with UE pool.

- **`normalized.upf.gtp_outdatapktn3upf_per_ue`** (GTP-U downlink rate per UE (N3)) — current **0.00 packets_per_second** vs learned baseline **3.37 packets_per_second** (MEDIUM, drop)
    - **What it measures:** Health of the downlink user-plane path UPF → gNB. Typically mirrors
uplink rate during calls/data; asymmetry indicates directional
faults (e.g., UPF receiving from internet but not forwarding).
    - **Drop means:** No traffic leaving UPF toward RAN.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE — constant regardless of UE pool size. Roughly symmetric with uplink during healthy calls.

- **`normalized.upf.gtp_indatapktn3upf_per_ue`** (GTP-U uplink rate per UE (N3)) — current **0.00 packets_per_second** vs learned baseline **3.44 packets_per_second** (MEDIUM, drop)
    - **What it measures:** Health of the uplink user-plane path gNB → UPF. Drops to near-zero
during RAN or N3 outage; stays nonzero during active calls or data
sessions. Decoupled from SIP signaling (signals data plane, not
control plane).
    - **Drop means:** Data plane dead on uplink — UPF receiving no packets from gNB.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE — constant regardless of UE pool size. Rises during active VoNR calls (~100 pps for G.711 voice) and data transfer.

- **`normalized.pcscf.dialogs_per_ue`** (Active SIP dialogs per registered UE at P-CSCF) — current **0.00 count** vs learned baseline **0.59 count** (LOW, drop)
    - **What it measures:** How many calls per user are currently in progress at the P-CSCF.
Going to zero from a non-zero baseline means calls have ended
(normal) OR call setup is failing system-wide (degradation).
Together with rcv_requests_* it discriminates the two.
    - **Drop means:** No active calls. Normal at rest; suspicious if prior state had calls AND INVITE rate is also zero.
    - **Healthy typical range:** 0–1 count
    - **Healthy invariant:** Per-UE — scale-independent. 0 at rest, ~1 per active VoNR call.

- **`derived.upf_activity_during_calls`** — current **1.00** vs learned baseline **0.45** (LOW, spike). *(No KB context available — interpret from the metric name.)*


## Event Aggregation (Phase 1)

**4 events fired during the observation window:**

- `core.amf.gnb_association_drop` (source: `core.amf.gnb`, nf: `amf`, t=1777342085.2)  [current_value=0.0, prior_stable_value=1.0]
- `core.amf.ran_ue_sudden_drop` (source: `core.amf.ran_ue`, nf: `amf`, t=1777342085.2)  [current_value=0.0, prior_stable_value=2.0, delta_percent=-100.0]
- `core.amf.ran_ue_full_loss` (source: `core.amf.ran_ue`, nf: `amf`, t=1777342085.2)  [current_value=0.0, prior_stable_value=2.0]
- `core.smf.sessions_per_ue_drop` (source: `core.smf.sessions_per_ue`, nf: `smf`, t=1777342085.2)  [current_value=0.0, prior_stable_value=2.0, delta_percent=-100.0]

## Correlation Analysis (Phase 2)

**Correlation engine produced 5 ranked composite hypotheses from 4 fired events (showing top 3 of 5):**

### H1: Total RAN outage
  - primary_nf: amf
  - explanatory_fit: 0.50 (2/4 events)
  - testability: 2 (2 disambiguating metrics)
  - supporting events: `core.amf.gnb_association_drop`, `core.amf.ran_ue_full_loss`
  - probes to discriminate:
      - Check core.amf.gnb → gNB-side failure (gnb=0) vs. AMF-side attach-processing issue (gnb>0 but ran_ue=0)
      - Check core.amf.ran_ue → Whether N2 is dead (both zero) vs. AMF-side attach issue (gnb>0, ran_ue=0)

### H2: Total RAN failure — gNB + UEs both gone
  - primary_nf: amf
  - explanatory_fit: 0.50 (2/4 events)
  - testability: 2 (2 disambiguating metrics)
  - supporting events: `core.amf.gnb_association_drop`, `core.amf.ran_ue_full_loss`
  - probes to discriminate:
      - Check core.amf.gnb → gNB-side failure (gnb=0) vs. AMF-side attach-processing issue (gnb>0 but ran_ue=0)
      - Check core.amf.ran_ue → Whether N2 is dead (both zero) vs. AMF-side attach issue (gnb>0, ran_ue=0)

### H3: UEs detaching, sessions torn down — RAN-triggered
  - primary_nf: smf
  - explanatory_fit: 0.50 (2/4 events)
  - testability: 2 (2 disambiguating metrics)
  - supporting events: `core.amf.ran_ue_sudden_drop`, `core.smf.sessions_per_ue_drop`
  - probes to discriminate:
      - Check core.amf.ran_ue → SMF/UPF fault (ran_ue stable but sessions_per_ue dropping) vs. general attachment issue (both dropping)
      - Check core.amf.gnb → gNB-side failure (gnb=0) vs. AMF-side attach-processing issue (gnb>0 but ran_ue=0)


## Network Analysis (Phase 3)

**Summary:** The entire RAN appears to be down, causing a total loss of UE attachment and data plane connectivity.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | All infrastructure components are up and running. |
| **ran** | 🔴 RED | The RAN is completely disconnected from the core. |
| **core** | 🟡 YELLOW | The core network is internally healthy but is showing symptoms of the RAN outage, such as a full loss of PDU sessions. |
| **ims** | 🟡 YELLOW | The IMS system is operationally ready, but no UEs can connect to use it. |

**RAN evidence:**
- get_network_topology() shows INACTIVE links for N2, N3 and Air Interface.
- get_nf_metrics() shows gnb=0 and ran_ue=0 at the AMF.

**CORE evidence:**
- Fired event core.smf.sessions_per_ue_drop
- Metric normalized.smf.sessions_per_ue is 0
- Metric normalized.smf.bearers_per_ue is 0

**IMS evidence:**
- Metric normalized.pcscf.dialogs_per_ue is 0

**Ranked hypotheses:**

- **`h1`** (fit=0.95, nf=amf, specificity=specific):
    - **Statement:** The gNB has failed or is partitioned from the core network, causing a complete loss of N2 and N3 connectivity, leading to all UEs detaching and all PDU sessions being dropped. This is consistent with the n2_connectivity_loss causal chain.
    - **Supporting events:** `core.amf.gnb_association_drop`, `core.amf.ran_ue_full_loss`, `core.amf.ran_ue_sudden_drop`, `core.smf.sessions_per_ue_drop`
    - **Falsification probes:**
        - Check if the gNB process is running and has network connectivity to the AMF.
        - Check AMF logs for any SCTP association attempts from the gNB.
- **`h2`** (fit=0.70, nf=amf, specificity=specific):
    - **Statement:** The AMF is running but has an internal fault that prevents it from processing N2 messages from the gNB, leading to the rejection or timeout of all UE attachments. This corresponds to the amf_service_disruption causal chain.
    - **Supporting events:** `core.amf.gnb_association_drop`, `core.amf.ran_ue_full_loss`, `core.amf.ran_ue_sudden_drop`
    - **Falsification probes:**
        - If a network trace on the AMF shows no incoming N2 messages from the gNB, the fault is upstream at the gNB or on the path, not in the AMF.
        - Examine AMF's internal logs for errors related to SCTP or NGAP processing.


## Falsification Plans (Phase 4)

**3 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `nr_gnb`)

**Hypothesis:** The gNB has failed or is partitioned from the core network, causing a complete loss of N2 and N3 connectivity, leading to all UEs detaching and all PDU sessions being dropped. This is consistent with the n2_connectivity_loss causal chain.

**Probes (3):**
1. **`get_network_status`** — container=nr_gnb
    - *Expected if hypothesis holds:* The nr_gnb container is in an 'exited' or 'unhealthy' state.
    - *Falsifying observation:* The nr_gnb container is 'running' and healthy. This would point towards a network partition rather than gNB failure.
2. **`measure_rtt`** — from=amf, to=nr_gnb
    - *Expected if hypothesis holds:* 100% packet loss or high latency, indicating a network partition.
    - *Falsifying observation:* Clean RTT (<5ms) and no packet loss, indicating the network path from AMF to gNB is healthy.
3. **`measure_rtt`** — from=nr_gnb, to=amf
    - *Expected if hypothesis holds:* 100% packet loss or high latency, confirming a bidirectional partition.
    - *Falsifying observation:* Clean RTT (<5ms). If the reverse path is healthy but the forward path is not, it points to an asymmetric routing or firewall issue, rather than a full gNB failure or partition.

*Notes:* This plan directly tests the two components of the hypothesis: a gNB failure (probe 1) and a network partition between the gNB and the core (probes 2 and 3). The bidirectional RTT check provides triangulation to isolate the fault.

### Plan for `h2` (target: `amf`)

**Hypothesis:** The AMF is running but has an internal fault that prevents it from processing N2 messages from the gNB, leading to the rejection or timeout of all UE attachments. This corresponds to the amf_service_disruption causal chain.

**Probes (3):**
1. **`check_process_listeners`** — container=amf
    - *Expected if hypothesis holds:* The AMF process is running and listening on the N2/SCTP port (38412), but is failing to process messages.
    - *Falsifying observation:* The AMF is not listening on the N2/SCTP port. This indicates a failure to initialize or a crash, not a silent internal fault.
2. **`get_nf_metrics`** — Focus on AMF internal error counters and NGAP/SCTP processing statistics.
    - *Expected if hypothesis holds:* Metrics should show signs of processing failure, such as incrementing error counters (e.g., sctp_send_failed, ngap_decode_error) while NGAP receive counters are static.
    - *Falsifying observation:* All AMF internal metrics are nominal, and counters for received NGAP messages are zero. This suggests that messages are not reaching the AMF, pointing to an upstream fault at the gNB or in the network.
3. **`measure_rtt`** — from=amf, to=smf
    - *Expected if hypothesis holds:* Clean RTT (<5ms). This would confirm the AMF's general networking stack is healthy and the issue is confined to N2 processing.
    - *Falsifying observation:* High packet loss or latency. This would indicate a broader networking problem with the AMF container itself, not just an application-level fault.

*Notes:* This plan focuses on isolating the failure to the AMF's application logic. It verifies that the AMF process is up and listening, checks for internal processing errors via metrics, and confirms its connectivity to other core components is healthy.

### Plan for `h3` (target: `smf`)

**Hypothesis:** UEs detaching, sessions torn down — RAN-triggered

**Probes (3):**
1. **`get_network_status`** — container=smf
    - *Expected if hypothesis holds:* The SMF container is 'running', as it is presumed to be healthy and simply reacting to upstream events from the AMF.
    - *Falsifying observation:* The SMF container is 'exited', which would indicate a primary SMF failure, not a reaction to a RAN problem.
2. **`get_nf_metrics`** — Focus on SMF's N4 session management metrics related to the UPF.
    - *Expected if hypothesis holds:* Metrics show N4 session release requests being sent from SMF to UPF, confirming the SMF is correctly processing session teardown commands from the AMF.
    - *Falsifying observation:* Metrics show no N4 session release activity, or show N4-related error counters incrementing. This would suggest the SMF itself is failing to handle the teardown, making it a contributing factor.
3. **`measure_rtt`** — from=smf, to=upf
    - *Expected if hypothesis holds:* Clean RTT (<5ms), indicating the N4 control plane path is healthy for the SMF to perform its duties.
    - *Falsifying observation:* Packet loss or high latency. This would implicate the SMF-UPF link as a potential fault location, contradicting the purely 'RAN-triggered' nature of the hypothesis.

*Notes:* This hypothesis suggests the SMF is a victim, not a cause. The probes are designed to verify this by checking that the SMF is alive and correctly performing its expected function (session teardown via N4) in response to the RAN outage.


## Parallel Investigators (Phase 5)

**2 sub-Investigator verdict(s):** **1 NOT_DISPROVEN**, **1 DISPROVEN**

### `h1` — ✅ **NOT_DISPROVEN**

**Hypothesis:** The gNB has failed or is partitioned from the core network, causing a complete loss of N2 and N3 connectivity, leading to all UEs detaching and all PDU sessions being dropped. This is consistent with the n2_connectivity_loss causal chain.

**Reasoning:** Probes indicate the nr_gnb container is not running and is unreachable from the AMF. The first probe, checking network status, showed `nr_gnb` is not in the list of running containers, supporting the 'gNB has failed' part of the hypothesis. The second probe confirmed this by showing 100% packet loss from the AMF to the gNB's IP. No falsifying evidence was found.

**Probes executed (3):**
- **Check if the gNB container is running.** ✓ CONSISTENT
    - *Tool:* `get_network_status()`
    - *Observation:* [EVIDENCE: get_network_status() -> '"down_or_absent": []' and 'nr_gnb' is not in the list of running containers.]
    - *Comment:* The get_network_status tool showed that the nr_gnb container is not in the list of running containers, which is consistent with the hypothesis that the gNB has failed.
- **Measure network connectivity from AMF to gNB.** ✓ CONSISTENT
    - *Tool:* `measure_rtt("amf", "172.22.0.23")`
    - *Observation:* [EVIDENCE: measure_rtt("amf", "172.22.0.23") -> "100% packet loss"]
    - *Comment:* The RTT measurement from the AMF to the gNB's last known IP address shows 100% packet loss, which is consistent with the gNB being down or partitioned.
- **Measure network connectivity from gNB to AMF.** ✓ CONSISTENT
    - *Tool:* `None`
    - *Observation:* The tool 'measure_rtt' could not be executed from the nr_gnb container because it is not running, as established by the first probe.
    - *Comment:* The inability to run this probe because the source container 'nr_gnb' is down serves as additional evidence supporting the hypothesis of gNB failure.

### `h2` — ❌ **DISPROVEN**

**Hypothesis:** The AMF is running but has an internal fault that prevents it from processing N2 messages from the gNB, leading to the rejection or timeout of all UE attachments. This corresponds to the amf_service_disruption causal chain.

**Reasoning:** The hypothesis is disproven by direct evidence from two probes. The core of the hypothesis is that the AMF is failing to *process* N2 messages. However, the evidence shows the AMF is not even *listening* on the N2/SCTP port (38412), which indicates a failure to initialize the service interface, not a fault in processing messages it receives. The metrics confirm a total lack of N2 activity, rather than processing errors.

**Probes executed (3):**
- **Check if the AMF process is listening on the N2/SCTP port (38412).** ✗ CONTRADICTS
    - *Tool:* `check_process_listeners(container='amf')`
    - *Observation:* [EVIDENCE: check_process_listeners("amf") -> "tcp   LISTEN 0      4096     172.22.0.10:9091       0.0.0.0:*    users:((\"open5gs-amfd\",pid=8,fd=10))\ntcp   LISTEN 0      5        172.22.0.10:7777       0.0.0.0:*    users:((\"open5gs-amfd\",pid=8,fd=11)) "]
    - *Comment:* The AMF process is running, but it is not listening on the N2/SCTP port 38412. This directly contradicts the hypothesis's premise that the AMF is running correctly but failing to process N2 traffic. It cannot process traffic it is not listening for.
- **Focus on AMF internal error counters and NGAP/SCTP processing statistics.** ✗ CONTRADICTS
    - *Tool:* `get_nf_metrics()`
    - *Observation:* [EVIDENCE: get_nf_metrics() -> "gnb = 0.0  [gauge, count]  — Direct liveness indicator of the N2 control plane.\n  ran_ue = 0.0  [gauge, count]  — Fundamental RAN health indicator."]
    - *Comment:* The metrics show zero connected gNBs and zero UEs from the RAN, and an absence of any NGAP/SCTP counters. This reflects a total lack of N2 activity, which aligns with the finding that the N2 port is not open. The hypothesis expected to see processing errors, but instead there is no activity to process.
- **Measure RTT from AMF to SMF to confirm the AMF's general networking stack is healthy.** ✓ CONSISTENT
    - *Tool:* `measure_rtt(container='amf', target_ip='172.22.0.7')`
    - *Observation:* [EVIDENCE: measure_rtt("amf", "172.22.0.7") -> "3 packets transmitted, 3 received, 0% packet loss, time 2042ms\nrtt min/avg/max/mdev = 0.096/0.143/0.225/0.057 ms"]
    - *Comment:* The RTT from AMF to SMF is excellent (<1ms). This shows the AMF container's networking is healthy. However, this doesn't save the hypothesis, as the issue is with the application layer not opening the necessary port, a fact established by other probes.

**Alternative suspects:** amf


## Evidence Validation (Phase 6)

**Overall verdict:** clean
**Overall confidence:** high

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 3 | 2/2 | clean | high |
| `InvestigatorAgent_h2` | 4 | 3/3 | clean | high |


## Ground Truth

**Failure domain:** data_plane  
**Protocol impact:** GTP-U  
**Affected components:** nr_gnb  
**Severity:** degraded

## Agent Diagnosis

**Model:** v6-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 179.2s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: The gNB has failed, causing a complete Radio Access Network (RAN) outage and total loss of connectivity for all user equipment.
> - **timeline**:
>     1. The gNB's control plane association with the AMF was lost (`core.amf.gnb_association_drop`).
>     2. This immediately caused a sudden and total loss of all registered UEs (`core.amf.ran_ue_sudden_drop`, `core.amf.ran_ue_full_loss`).
>     3. Consequently, all associated PDU sessions for the detached UEs were dropped (`core.smf.sessions_per_ue_drop`).
> - **root_cause**: The gNB has failed. Investigation confirmed that the `nr_gnb` container is not running and is unreachable from the core network. The primary suspect network function is `nr_gnb`.
> - **affected_components**:
>     - `nr_gnb`: Root Cause
>     - `amf`: Symptomatic
>     - `smf`: Symptomatic
>     - `ims`: Symptomatic
> - **recommendation**: Investigate the `nr_gnb` container/service to determine why it is not running. Check its logs for errors that may have occurred during startup or that led to its termination.
> - **confidence**: high
> - **explanation**: The investigation confirmed the hypothesis that the gNB failed or became partitioned from the network (`h1`). Probes showed definitively that the `nr_gnb` container is not running and is unreachable from the AMF, which aligns with the observed loss of N2 connectivity and all RAN UEs. An alternative hypothesis blaming an internal AMF fault (`h2`) was disproven; while the AMF was not listening on the N2 port, the primary cause was the complete absence of the gNB. The evidence points conclusively to a gNB failure as the trigger for the entire outage.

### Scoring Breakdown

**Overall score: 100%**

**Scorer assessment:** The agent provided a perfectly accurate and well-calibrated diagnosis, correctly identifying the root cause, affected components, severity, fault type, and layer, with high confidence.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | Yes | The agent correctly identified the gNB failure and its unreachability as the root cause, which directly matches the simulated failure mode of 'nr_gnb' being completely unreachable. |
| Component overlap | 100% | The agent explicitly listed 'nr_gnb' as the 'Root Cause' in its 'affected_components', which is the primary affected component according to the simulated failure. |
| Severity correct | Yes | The agent accurately described the impact as a 'complete Radio Access Network (RAN) outage and total loss of connectivity', which aligns with the simulated complete unreachability and loss of all services. |
| Fault type identified | Yes | The agent identified the gNB as 'not running and unreachable', which correctly describes a 'Component unreachable' fault type, consistent with the simulated failure. |
| Layer accuracy | Yes | The 'NETWORK ANALYSIS' correctly rated the 'ran' layer as 'red', which is the correct ontology layer for the 'nr_gnb' component. |
| Confidence calibrated | Yes | The agent's diagnosis is entirely accurate and well-supported by the explanation and evidence, making a 'high' confidence level appropriate. |

**Ranking position:** #1 — The agent provided a single, definitive root cause, which is correct, thus it is implicitly ranked first.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 172,744 |
| Output tokens | 4,392 |
| Thinking tokens | 14,398 |
| **Total tokens** | **191,534** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| EventAggregator | 0 | 0 | 0 |
| CorrelationAnalyzer | 0 | 0 | 0 |
| NetworkAnalystAgent | 73,668 | 5 | 6 |
| InstructionGeneratorAgent | 28,174 | 2 | 2 |
| InvestigatorAgent_h1 | 37,365 | 3 | 4 |
| InvestigatorAgent_h2 | 46,567 | 4 | 4 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 5,760 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 321.6s
