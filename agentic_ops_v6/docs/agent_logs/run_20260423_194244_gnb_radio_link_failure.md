# Episode Report: gNB Radio Link Failure

**Agent:** v6  
**Episode ID:** ep_20260423_193657_gnb_radio_link_failure  
**Date:** 2026-04-23T19:37:00.560226+00:00  
**Duration:** 343.4s  

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

- `core.amf.gnb_association_drop` (source: `core.amf.gnb`, nf: `amf`, t=1776973139.8)  [current_value=0.0, prior_stable_value=1.0]
- `core.amf.ran_ue_sudden_drop` (source: `core.amf.ran_ue`, nf: `amf`, t=1776973139.8)  [current_value=0.0, prior_stable_value=2.0, delta_percent=-100.0]
- `core.amf.ran_ue_full_loss` (source: `core.amf.ran_ue`, nf: `amf`, t=1776973139.8)  [current_value=0.0, prior_stable_value=2.0]
- `core.smf.sessions_per_ue_drop` (source: `core.smf.sessions_per_ue`, nf: `smf`, t=1776973139.8)  [current_value=0.0, prior_stable_value=2.0, delta_percent=-100.0]

## Correlation Analysis (Phase 2)

**Correlation engine produced 5 ranked composite hypotheses from 4 fired events (showing top 3 of 5):**

### H1: UEs detaching, sessions torn down — RAN-triggered
  - primary_nf: smf
  - explanatory_fit: 0.50 (2/4 events)
  - testability: 2 (2 disambiguating metrics)
  - supporting events: `core.amf.ran_ue_sudden_drop`, `core.smf.sessions_per_ue_drop`
  - probes to discriminate:
      - Check core.amf.ran_ue → SMF/UPF fault (ran_ue stable but sessions_per_ue dropping) vs. general attachment issue (both dropping)
      - Check core.amf.gnb → gNB-side failure (gnb=0) vs. AMF-side attach-processing issue (gnb>0 but ran_ue=0)

### H2: RAN failure confirmed — gNB down, UEs followed
  - primary_nf: amf
  - explanatory_fit: 0.50 (2/4 events)
  - testability: 2 (2 disambiguating metrics)
  - supporting events: `core.amf.gnb_association_drop`, `core.amf.ran_ue_sudden_drop`
  - probes to discriminate:
      - Check core.amf.ran_ue → Whether N2 is dead (both zero) vs. AMF-side attach issue (gnb>0, ran_ue=0)
      - Check core.amf.gnb → gNB-side failure (gnb=0) vs. AMF-side attach-processing issue (gnb>0 but ran_ue=0)

### H3: Total RAN outage
  - primary_nf: amf
  - explanatory_fit: 0.50 (2/4 events)
  - testability: 2 (2 disambiguating metrics)
  - supporting events: `core.amf.gnb_association_drop`, `core.amf.ran_ue_full_loss`
  - probes to discriminate:
      - Check core.amf.ran_ue → Whether N2 is dead (both zero) vs. AMF-side attach issue (gnb>0, ran_ue=0)
      - Check core.amf.gnb → gNB-side failure (gnb=0) vs. AMF-side attach-processing issue (gnb>0 but ran_ue=0)


## Network Analysis (Phase 3)

**Summary:** The entire network is non-operational due to a complete Radio Access Network (RAN) outage; the gNB is disconnected from the core, preventing all UE attachments and subsequent services.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | The underlying container platform appears healthy; the issue is specific to the RAN component. |
| **ran** | 🔴 RED | The RAN is completely disconnected from the core network. No UEs can attach. |
| **core** | 🟡 YELLOW | Core services are running but are starved of traffic from the RAN. The core is observing a failure, not causing it. |
| **ims** | 🟡 YELLOW | IMS services are running but have no registered users to serve, as a direct consequence of the RAN/Core attachment failure. |

**RAN evidence:**
- event: core.amf.gnb_association_drop
- metric: amf.gnb = 0
- metric: amf.ran_ue = 0
- topology: N2 link is INACTIVE
- topology: N3 link is INACTIVE

**CORE evidence:**
- metric: normalized.smf.sessions_per_ue = 0
- metric: normalized.upf.gtp_indatapktn3upf_per_ue = 0

**IMS evidence:**
- metric: normalized.pcscf.dialogs_per_ue = 0

**Ranked hypotheses:**

- **`h1`** (fit=1.00, nf=nr_gnb, specificity=specific):
    - **Statement:** The gNB has lost SCTP connectivity to the AMF over the N2 interface, causing a total RAN outage. This aligns with the 'n2_connectivity_loss' causal chain, explaining why the AMF sees zero connected gNBs and UEs.
    - **Supporting events:** `core.amf.gnb_association_drop`, `core.amf.ran_ue_full_loss`, `core.amf.ran_ue_sudden_drop`, `core.smf.sessions_per_ue_drop`
    - **Falsification probes:**
        - Check the gNB container's status and logs to see if it is running and has SCTP reachability to the AMF.
        - Verify bi-directional IP connectivity between the gNB's N2 interface and the AMF's N2 interface.
- **`h2`** (fit=0.60, nf=amf, specificity=moderate):
    - **Statement:** The AMF experienced an internal fault that caused it to drop all N2 associations, despite its process remaining online. This is a less likely alternative to H1, suggested by the 'amf_service_disruption' chain.
    - **Supporting events:** `core.amf.gnb_association_drop`, `core.amf.ran_ue_full_loss`
    - **Falsification probes:**
        - The causal chain 'amf_service_disruption' includes a discriminator: this hypothesis is likely false if the AMF is running and the issue is on the gNB side.
        - Examine AMF logs for any internal errors unrelated to SCTP transport that would cause it to tear down gNB associations.


## Falsification Plans (Phase 4)

**2 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `nr_gnb`)

**Hypothesis:** The gNB has lost SCTP connectivity to the AMF over the N2 interface, causing a total RAN outage. This aligns with the 'n2_connectivity_loss' causal chain, explaining why the AMF sees zero connected gNBs and UEs.

**Probes (3):**
1. **`measure_rtt`** — From AMF container to the gNB's N2 interface IP address
    - *Expected if hypothesis holds:* High packet loss or total unreachability. This confirms a network partition, but doesn't isolate the direction.
    - *Falsifying observation:* Clean RTT (< 5ms). This would falsify the hypothesis by showing the gNB is reachable from the AMF, suggesting the issue is at a higher layer than IP connectivity (e.g., SCTP process on gNB is dead).
2. **`measure_rtt`** — From the gNB container to the UPF's N3 interface IP address
    - *Expected if hypothesis holds:* Clean RTT (< 5ms). This would help isolate the connectivity problem to the gNB-AMF path specifically.
    - *Falsifying observation:* High packet loss. This would suggest the gNB container has a general networking issue, not one specific to the N2 interface, thus broadening the fault domain.
3. **`check_process_listeners`** — On the 'nr_gnb' container
    - *Expected if hypothesis holds:* The gNB process is listening on the SCTP port for N2. The hypothesis is about connectivity, implying the process is up.
    - *Falsifying observation:* The gNB process is not listening on its N2 SCTP port. This would falsify the 'connectivity loss' hypothesis and point to a gNB application failure.

*Notes:* This plan attempts to falsify the gNB network connectivity hypothesis (h1) by using triangulation. Probes check the reverse path (AMF->gNB) and a path from the gNB to a different target (gNB->UPF) to isolate the fault to the N2 link itself.

### Plan for `h2` (target: `amf`)

**Hypothesis:** The AMF experienced an internal fault that caused it to drop all N2 associations, despite its process remaining online. This is a less likely alternative to H1, suggested by the 'amf_service_disruption' chain.

**Probes (3):**
1. **`get_network_status`** — Check the status of the 'amf' container
    - *Expected if hypothesis holds:* The 'amf' container is in a 'running' state, as per the hypothesis statement.
    - *Falsifying observation:* The 'amf' container is 'exited' or in a restart loop. This falsifies the premise of the hypothesis that the process remained online.
2. **`get_nf_metrics`** — Filter for metrics from the 'amf' container, particularly any with 'error' or 'failure' in their names
    - *Expected if hypothesis holds:* A non-zero value or recent spike in a counter for internal errors, dropped messages, or SBI client failures.
    - *Falsifying observation:* All internal error and failure metrics for the AMF are zero or at their baseline. The absence of any error metric makes an 'internal fault' less likely.
3. **`measure_rtt`** — From the AMF container to the SMF's N11 interface IP address
    - *Expected if hypothesis holds:* Clean RTT (< 5ms). This demonstrates the AMF's networking stack is functional, supporting the theory of a specific, internal service fault.
    - *Falsifying observation:* High packet loss or failure. This would indicate a broader networking problem affecting the AMF container, contradicting the hypothesis of a contained 'internal fault'.

*Notes:* This plan tests the 'AMF internal fault' hypothesis (h2). It first verifies the process is actually online as claimed, then checks for positive evidence of an internal error via metrics, and finally uses a connectivity check to a different peer (SMF) to rule out a general networking failure at the AMF.


## Parallel Investigators (Phase 5)

**2 sub-Investigator verdict(s):** **2 DISPROVEN**

### `h1` — ❌ **DISPROVEN**

**Hypothesis:** The gNB has lost SCTP connectivity to the AMF over the N2 interface, causing a total RAN outage. This aligns with the 'n2_connectivity_loss' causal chain, explaining why the AMF sees zero connected gNBs and UEs.

**Reasoning:** The hypothesis assumes the gNB is running but has lost network connectivity. Probes revealed that the 'nr_gnb' container itself is not running or is absent from the network, which is a more fundamental issue than a network partition. The unreachability of the gNB's IP from the AMF is a symptom of the gNB being down, not a network problem between two running components. The failure of a probe from the 'nr_gnb' container and its absence in the network status directly contradict the hypothesis's premise.

**Probes executed (3):**
- **From AMF container to the gNB's N2 interface IP address** ✓ CONSISTENT
    - *Tool:* `default_api.measure_rtt(container='amf', target_ip='172.22.0.23')`
    - *Observation:* [EVIDENCE: measure_rtt("amf", "172.22.0.23") -> "100% packet loss"]
    - *Comment:* This confirmed the loss of connectivity from the AMF's perspective, which is an expected symptom. However, it does not isolate the cause to a network partition.
- **From the gNB container to the UPF's N3 interface IP address** ✗ CONTRADICTS
    - *Tool:* `default_api.measure_rtt(container='nr_gnb', target_ip='172.22.0.8')`
    - *Observation:* [EVIDENCE: measure_rtt("nr_gnb", "172.22.0.8") -> "Unknown container 'nr_gnb'"]
    - *Comment:* This probe was expected to succeed with low latency to confirm the gNB's general network health. Instead, it revealed the 'nr_gnb' container does not exist, falsifying the premise that the gNB is running but partitioned from the AMF.
- **Check container status for 'nr_gnb'** ✗ CONTRADICTS
    - *Tool:* `default_api.get_network_status()`
    - *Observation:* [EVIDENCE: get_network_status() -> "down_or_absent": [] and 'nr_gnb' not in 'running' list]
    - *Comment:* This probe confirms the finding from the previous one. The 'nr_gnb' container is not running. This contradicts the hypothesis's implied assumption that the gNB is an active but unreachable process. Consequently, the third planned probe (`check_process_listeners`) could not be run as the target container is absent.

**Alternative suspects:** nr_gnb

### `h2` — ❌ **DISPROVEN**

**Hypothesis:** The AMF experienced an internal fault that caused it to drop all N2 associations, despite its process remaining online. This is a less likely alternative to H1, suggested by the 'amf_service_disruption' chain.

**Reasoning:** Probes confirmed the AMF process is online and has healthy network connectivity to other core components (SMF), which is consistent with parts of the hypothesis. However, a probe for metrics indicating an internal AMF fault found no such evidence. The absence of any positive evidence for the hypothesized "internal fault"—the core of this hypothesis—makes it extremely unlikely to be the root cause. A healthy AMF that has lost contact with its peer points to an external fault.

**Probes executed (3):**
- **Check the status of the 'amf' container** ✓ CONSISTENT
    - *Tool:* `print(default_api.get_network_status())`
    - *Observation:* [EVIDENCE: get_network_status() -> "'amf': 'running'"]
    - *Comment:* The AMF container is in a 'running' state, which is consistent with the hypothesis's premise that the process remained online.
- **Filter for metrics from the 'amf' container, particularly any with 'error' or 'failure' in their names** ✗ CONTRADICTS
    - *Tool:* `print(default_api.get_nf_metrics())`
    - *Observation:* [EVIDENCE: get_nf_metrics() -> "AMF (via prometheus):\n  amf_session = 4.0  [counter]\n  gnb = 0.0  [gauge, count]  \u2014 Direct liveness indicator of the N2 control plane.\n  ran_ue = 0.0  [gauge, count]  \u2014 Fundamental RAN health indicator."]
    - *Comment:* No metrics indicating an internal error, dropped message, or SBI client failure were found for the AMF. This contradicts the expectation that an internal fault would produce such a metric, and weakens the hypothesis.
- **From the AMF container to the SMF's N11 interface IP address** ✓ CONSISTENT
    - *Tool:* `print(default_api.measure_rtt(container = 'amf', target_ip = '172.22.0.7'))`
    - *Observation:* [EVIDENCE: measure_rtt("amf", "172.22.0.7") -> "3 packets transmitted, 3 received, 0% packet loss, time 2046ms\nrtt min/avg/max/mdev = 0.082/0.165/0.325/0.112 ms"]
    - *Comment:* The AMF has excellent connectivity to the SMF, with 0% packet loss and sub-millisecond RTT. This supports the hypothesis's premise that the AMF's networking stack is functional and the problem is not a general network failure at the AMF.

**Alternative suspects:** nr_gnb


## Evidence Validation (Phase 6)

**Overall verdict:** clean
**Overall confidence:** high

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 4 | 3/3 | clean | high |
| `InvestigatorAgent_h2` | 4 | 3/3 | clean | high |


## Ground Truth

**Failure domain:** data_plane  
**Protocol impact:** GTP-U  
**Affected components:** nr_gnb  
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
> - **summary**: The entire network is non-operational due to a total Radio Access Network (RAN) outage caused by the `nr_gnb` container being down or absent.
> - **timeline**:
>     1. The gNB association with the AMF was lost (`core.amf.gnb_association_drop`).
>     2. As a direct result, all UEs attached to the RAN were lost from the core network's perspective (`core.amf.ran_ue_full_loss`, `core.amf.ran_ue_sudden_drop`).
>     3. Subsequently, all associated PDU sessions were torn down by the SMF (`core.smf.sessions_per_ue_drop`).
> - **root_cause**: The `nr_gnb` component has failed; it is not running or is absent from the container platform.
> - **affected_components**:
>     - `nr_gnb`: Root Cause
>     - `amf`: Secondary (Lost N2 connectivity due to gNB failure)
>     - `smf`: Symptomatic (Lost PDU sessions as a consequence of UE detachment)
>     - `ims`: Symptomatic (No registered users to serve due to the attachment failure)
> - **recommendation**: Verify the status of the `nr_gnb` container on its host system. Investigate the container's logs to determine why it failed to start or why it terminated.
> - **confidence**: low
> - **explanation**: The initial hypotheses focused on a network partition between the gNB and AMF (`h1`) or an internal AMF fault (`h2`). Both were disproven. Investigation for `h1` revealed that the gNB container itself is not running, which contradicts the hypothesis of a network partition between two running components. Investigation for `h2` found the AMF to be healthy and fully connected to its core peers, ruling out an internal AMF fault. Since both initial hypotheses were wrong, the evidence points to the alternative suspect identified during the investigation: the `nr_gnb` component has failed entirely. Confidence is low because this was discovered by process of elimination, not by confirming a primary hypothesis.

### Scoring Breakdown

**Overall score: 90%**

**Scorer assessment:** The agent provided a highly accurate diagnosis, correctly identifying the root cause, affected components, severity, and fault type. However, its stated low confidence for a correct diagnosis indicates poor calibration.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | Yes | The agent correctly identified the `nr_gnb` component failure as the root cause, stating it was 'not running or absent from the container platform,' which accurately describes the simulated 'unreachable/down' state of the gNB. |
| Component overlap | 100% | The agent correctly identified `nr_gnb` as the 'Root Cause' in its `affected_components` list, achieving full overlap with the primary affected component. |
| Severity correct | Yes | The agent correctly assessed the severity as a 'total Radio Access Network (RAN) outage' and that the 'entire network is non-operational,' matching the simulated complete outage where all UEs lose registration and PDU sessions drop. |
| Fault type identified | Yes | The agent identified the fault type as the `nr_gnb` component being 'not running or absent,' which is semantically equivalent to a component being unreachable or down, matching the observable failure mode. |
| Layer accuracy | Yes | The agent's network analysis correctly rated the 'ran' layer as 'red,' which is the correct ontology layer for the `nr_gnb` component. |
| Confidence calibrated | No | The agent's diagnosis is entirely correct and well-supported by the provided evidence and timeline, yet it states 'low' confidence. This indicates poor calibration, as a correct and well-supported diagnosis should ideally have high confidence. |

**Ranking position:** #1 — The agent provided a single, correct root cause in its final diagnosis, placing it at position 1.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 168,397 |
| Output tokens | 4,175 |
| Thinking tokens | 14,891 |
| **Total tokens** | **187,463** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| EventAggregator | 0 | 0 | 0 |
| CorrelationAnalyzer | 0 | 0 | 0 |
| NetworkAnalystAgent | 57,505 | 5 | 4 |
| InstructionGeneratorAgent | 20,218 | 1 | 2 |
| InvestigatorAgent_h1 | 47,000 | 4 | 5 |
| InvestigatorAgent_h2 | 57,343 | 4 | 5 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 5,397 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 343.4s
