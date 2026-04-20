# Episode Report: gNB Radio Link Failure

**Agent:** v6  
**Episode ID:** ep_20260420_041956_gnb_radio_link_failure  
**Date:** 2026-04-20T04:19:58.304550+00:00  
**Duration:** 258.8s  

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

### Metrics Changes

| Node | Metric | Baseline | Current | Delta |
|------|--------|----------|---------|-------|
| amf | gnb | 1.0 | 0.0 | -1.0 |
| amf | ran_ue | 2.0 | 0.0 | -2.0 |

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 0.98 (threshold: 0.70, trained on 211 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following specific metrics were flagged as the top contributors to the anomaly. These MUST be reflected in your layer ratings:

| Component | Metric | Current | Learned Normal | Severity |
|-----------|--------|---------|---------------|----------|
| normalized | smf.sessions_per_ue | 0.00 | 2.00 | HIGH |
| normalized | smf.bearers_per_ue | 0.00 | 2.61 | HIGH |
| normalized | upf.gtp_outdatapktn3upf_per_ue | 0.00 | 3.34 | MEDIUM |
| normalized | upf.gtp_indatapktn3upf_per_ue | 0.00 | 3.42 | MEDIUM |
| normalized | pcscf.dialogs_per_ue | 0.00 | 0.57 | LOW |
| derived | upf_activity_during_calls | 1.00 | 0.47 | LOW |

## Event Aggregation (Phase 1)

**4 events fired during the observation window:**

- `core.amf.ran_ue_sudden_drop` (source: `core.amf.ran_ue`, nf: `amf`, t=1776658916.0)  [current_value=0.0, prior_stable_value=2.0, delta_percent=-100.0]
- `core.amf.ran_ue_full_loss` (source: `core.amf.ran_ue`, nf: `amf`, t=1776658916.0)  [current_value=0.0, prior_stable_value=2.0]
- `core.amf.gnb_association_drop` (source: `core.amf.gnb`, nf: `amf`, t=1776658916.0)  [current_value=0.0, prior_stable_value=1.0]
- `core.smf.sessions_per_ue_drop` (source: `core.smf.sessions_per_ue`, nf: `smf`, t=1776658916.0)  [current_value=0.0, prior_stable_value=2.0, delta_percent=-100.0]

## Correlation Analysis (Phase 2)

**Correlation engine produced 5 ranked composite hypotheses from 4 fired events (showing top 3 of 5):**

### H1: gNB/N2 failure — RAN access lost for both gNB and UEs
  - primary_nf: amf
  - explanatory_fit: 0.50 (2/4 events)
  - testability: 2 (2 disambiguating metrics)
  - supporting events: `core.amf.gnb_association_drop`, `core.amf.ran_ue_sudden_drop`
  - probes to discriminate:
      - Check core.amf.gnb → gNB-side failure (gnb=0) vs. AMF-side attach-processing issue (gnb>0 but ran_ue=0)
      - Check core.amf.ran_ue → Whether N2 is dead (both zero) vs. AMF-side attach issue (gnb>0, ran_ue=0)

### H2: RAN failure confirmed — gNB down, UEs followed
  - primary_nf: amf
  - explanatory_fit: 0.50 (2/4 events)
  - testability: 2 (2 disambiguating metrics)
  - supporting events: `core.amf.gnb_association_drop`, `core.amf.ran_ue_sudden_drop`
  - probes to discriminate:
      - Check core.amf.gnb → gNB-side failure (gnb=0) vs. AMF-side attach-processing issue (gnb>0 but ran_ue=0)
      - Check core.amf.ran_ue → Whether N2 is dead (both zero) vs. AMF-side attach issue (gnb>0, ran_ue=0)

### H3: UEs detaching, sessions torn down — RAN-triggered
  - primary_nf: amf
  - explanatory_fit: 0.50 (2/4 events)
  - testability: 2 (2 disambiguating metrics)
  - supporting events: `core.amf.ran_ue_sudden_drop`, `core.smf.sessions_per_ue_drop`
  - probes to discriminate:
      - Check core.amf.gnb → gNB-side failure (gnb=0) vs. AMF-side attach-processing issue (gnb>0 but ran_ue=0)
      - Check core.amf.ran_ue → SMF/UPF fault (ran_ue stable but sessions_per_ue dropping) vs. general attachment issue (both dropping)


## Network Analysis (Phase 3)

```
**Summary:** The RAN layer is down, causing a complete loss of UE connectivity and session establishment.

**Layer status:**
  - infrastructure: green — The underlying container infrastructure appears healthy.
  - ran: red — The gNB is offline, leading to a total loss of access.
  - core: yellow — Core components are up but are operationally impaired due to the RAN outage, with no UEs or sessions.
  - ims: green — The IMS stack is healthy and awaiting registrations, which are impossible without RAN access.

**Top 3 hypotheses (ranked, testable only):**
- `h1` (fit=0.95, nf=ran, specificity=specific):
    statement: The gNB has failed or is partitioned from the network, causing a complete loss of N2/N3 connectivity to the 5G core and preventing all UE attachments.
    supporting events: cor
```

## Falsification Plans (Phase 4)

**3 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `ran`)

**Hypothesis:** The gNB has failed or is partitioned from the network, causing a complete loss of N2/N3 connectivity to the 5G core and preventing all UE attachments.

**Probes (3):**
1. **`get_network_status`** — container='nr_gnb'
    - *Expected if hypothesis holds:* nr_gnb container status is 'down' or 'unreachable'
    - *Falsifying observation:* nr_gnb container status is 'running'
2. **`measure_rtt`** — from='amf', to_ip='<nr_gnb_control_plane_ip>'
    - *Expected if hypothesis holds:* High RTT or 100% packet loss between AMF and gNB (indicating partition)
    - *Falsifying observation:* Low RTT (<5ms) and no packet loss (indicating network connectivity)
3. **`search_logs`** — container='nr_gnb', pattern='error|fail|N2|N3|connection refused'
    - *Expected if hypothesis holds:* Logs showing gNB startup failures, N2/N3 connection errors, or process crashes
    - *Falsifying observation:* Clean logs with no relevant N2/N3 errors or indications of process failure

*Notes:* Focuses on direct gNB liveness and network reachability from the core.

### Plan for `h2` (target: `amf`)

**Hypothesis:** The AMF has experienced a critical failure, causing it to incorrectly terminate its N2 interface and drop all connections with the gNB and associated UEs.

**Probes (3):**
1. **`get_network_status`** — container='amf'
    - *Expected if hypothesis holds:* AMF container status is 'down' or 'unreachable'
    - *Falsifying observation:* AMF container status is 'running'
2. **`search_logs`** — container='amf', pattern='N2.*(fail|error)|critical error|stack trace'
    - *Expected if hypothesis holds:* AMF logs showing critical errors, stack traces, or N2 interface failures
    - *Falsifying observation:* Clean AMF logs, no critical errors or N2 interface specific issues
3. **`check_process_listeners`** — container='amf'
    - *Expected if hypothesis holds:* AMF's N2 listening port (e.g., 38412 for NGAP) is not active
    - *Falsifying observation:* AMF's N2 listening port is active and accepting connections

*Notes:* Focuses on AMF process health, internal error logs, and N2 interface listener status.

### Plan for `h3` (target: `amf`)

**Hypothesis:** A mass UE detachment event, triggered by an external factor, caused a cascading teardown of PDU sessions and bearers across the SMF and UPF.

**Probes (3):**
1. **`search_logs`** — container='nr_gnb', pattern='(radio link failure|RLF)|authentication failed|connection timeout'
    - *Expected if hypothesis holds:* Widespread 'radio link failure', 'authentication failed', or 'connection timeout' messages in gNB logs, preceding the drops
    - *Falsifying observation:* No such messages in gNB logs, or only isolated incidents not correlating with the mass drop
2. **`search_logs`** — container='amf', pattern='UE.*(detach|release)|registration reject|authentication reject'
    - *Expected if hypothesis holds:* AMF logs showing mass UE detach/release messages or widespread registration/authentication rejections, potentially with external cause codes
    - *Falsifying observation:* No such messages, or detach reasons indicating AMF internal issues rather than external triggers
3. **`get_nf_metrics`** — component='smf'
    - *Expected if hypothesis holds:* SMF metrics showing zero PDU session setup attempts and zero active sessions, confirming complete session loss
    - *Falsifying observation:* SMF metrics showing any PDU session setup attempts (even if failing) or some residual active sessions, indicating the problem isn't a complete cascading teardown

*Notes:* Focuses on RAN-side triggers in gNB logs and AMF/SMF logs/metrics for evidence of mass UE detachment or lack of new attempts.


## Parallel Investigators (Phase 5)

**3 sub-Investigator verdict(s):** **1 NOT_DISPROVEN**, **2 DISPROVEN**

### `h1` — ✅ **NOT_DISPROVEN**

**Hypothesis:** The gNB has failed or is partitioned from the network, causing a complete loss of N2/N3 connectivity to the 5G core and preventing all UE attachments.

**Reasoning:** All probes consistently showed that the gNB is offline and unreachable from the core network. The gNB container is not running, the AMF cannot ping the gNB's IP address, and the logging system does not recognize the gNB container. This evidence strongly supports the hypothesis.

**Probes executed (3):**
- **Check the status of the gNB container/process to see if it is running.** ✓ CONSISTENT
    - *Tool:* `get_network_status()`
    - *Observation:* [EVIDENCE: get_network_status() -> "'running': ['mongo', 'nrf', 'scp', 'ausf', 'udr', 'udm', 'amf', 'smf', 'upf', 'pcf', 'dns', 'mysql', 'pyhss', 'icscf', 'scscf', 'pcscf', 'rtpengine']"]
    - *Comment:* The nr_gnb container is absent from the list of running containers, which aligns with the expectation that the gNB has failed.
- **Verify network connectivity (ping, traceroute) from the gNB's host to the AMF and UPF IPs.** ✓ CONSISTENT
    - *Tool:* `measure_rtt("amf", "172.22.0.23")`
    - *Observation:* [EVIDENCE: measure_rtt("amf", "172.22.0.23") -> "100% packet loss"]
    - *Comment:* The AMF cannot reach the gNB's IP address, confirming a complete network partition or that the gNB is down, as the hypothesis suggests.
- **Logs showing gNB startup failures, N2/N3 connection errors, or process crashes** ✓ CONSISTENT
    - *Tool:* `search_logs(containers=["nr_gnb"], pattern="error|fail|N2|N3|connection refused", since="1h")`
    - *Observation:* [EVIDENCE: search_logs(containers=["nr_gnb"], pattern="error|fail|N2|N3|connection refused", since="1h") -> "Unknown containers: nr_gnb"]
    - *Comment:* The logging system does not recognize the 'nr_gnb' container. This is consistent with the gNB container being completely down and not just in an error state, supporting the failure hypothesis.

### `h2` — ❌ **DISPROVEN**

**Hypothesis:** The AMF has experienced a critical failure, causing it to incorrectly terminate its N2 interface and drop all connections with the gNB and associated UEs.

**Reasoning:** The AMF container is confirmed to be running and its logs are clean, with no indications of critical failures, stack traces, or N2 interface errors. This contradicts the hypothesis of a critical failure within the AMF. The issue likely lies with the other end of the N2 connection, the gNB.

**Probes executed (3):**
- **Check the status of the AMF container.** ✗ CONTRADICTS
    - *Tool:* `get_network_status()`
    - *Observation:* [EVIDENCE: get_network_status() -> "'amf': 'running'"]
    - *Comment:* The AMF process is healthy and running. This contradicts the expectation of a 'down' or 'unreachable' status that would result from a critical failure.
- **Search AMF logs for critical errors or N2 interface failures.** ✗ CONTRADICTS
    - *Tool:* `search_logs(containers=["amf"], pattern="N2.*(fail|error)|critical error|stack trace")`
    - *Observation:* [EVIDENCE: search_logs('containers=["amf"], pattern="N2.*(fail|error)|critical error|stack trace"') -> "No matches for 'N2.*(fail|error)|critical error|stack trace' in containers: amf"]
    - *Comment:* The logs show no evidence of a critical failure, stack trace, or specific N2 interface problem. This directly falsifies the core of the hypothesis.
- **Check if the AMF's N2 listening port is active.** ~ AMBIGUOUS
    - *Tool:* `check_process_listeners(container="amf")`
    - *Observation:* [EVIDENCE: check_process_listeners('container="amf"') -> "Netid State  Recv-Q Send-Q Local Address:Port  Peer Address:PortProcess                              \ntcp   LISTEN 0      5        172.22.0.10:7777       0.0.0.0:*    users:((\"open5gs-amfd\",pid=8,fd=11))\ntcp   LISTEN 0      4096     172.22.0.10:9091       0.0.0.0:*    users:((\"open5gs-amfd\",pid=8,fd=10))"]
    - *Comment:* The expected N2 listening port (38412 over SCTP) was not observed. However, the tool output does not show any SCTP listeners at all, suggesting a tool limitation. Given the strong contradictory evidence from the other probes, this result is considered ambiguous and insufficient to support the hypothesis.

**Alternative suspects:** ran

### `h3` — ❌ **DISPROVEN**

**Hypothesis:** A mass UE detachment event, triggered by an external factor, caused a cascading teardown of PDU sessions and bearers across the SMF and UPF.

**Reasoning:** All three probes strongly contradict the hypothesis. The non-existence of the gNB container proves the issue is not an external trigger causing detachments but a RAN failure. Furthermore, AMF logs show no record of a mass detachment event, and SMF metrics confirm that PDU sessions were not torn down but are still considered active.

**Probes executed (3):**
- **Widespread 'radio link failure', 'authentication failed', or 'connection timeout' messages in gNB logs, preceding the drops** ✗ CONTRADICTS
    - *Tool:* `search_logs(containers=['nr_gnb'], pattern='(radio link failure|RLF)|authentication failed|connection timeout')`
    - *Observation:* [EVIDENCE: search_logs("containers=['nr_gnb'], pattern=(radio link failure|RLF)|authentication failed|connection timeout") -> "{'result': 'Unknown containers: nr_gnb. Known: mongo, nrf, scp, ausf, udr, udm, amf, smf, upf, pcf, dns, mysql, pyhss, icscf, scscf, pcscf, rtpengine'}"]
    - *Comment:* The hypothesis assumes a functioning RAN through which UEs could detach. The gNB container ('nr_gnb') does not exist, indicating a direct RAN failure, not an externally triggered event through the RAN.
- **AMF logs showing mass UE detach/release messages or widespread registration/authentication rejections, potentially with external cause codes** ✗ CONTRADICTS
    - *Tool:* `search_logs(containers=['amf'], pattern='UE.*(detach|release)|registration reject|authentication reject')`
    - *Observation:* [EVIDENCE: search_logs("containers=['amf'], pattern=UE.*(detach|release)|registration reject|authentication reject") -> "{'result': 'No matches for \'UE.*(detach|release)|registration reject|authentication reject\' in containers: amf'}"]
    - *Comment:* The AMF, which would process any UE detachment, shows no logs of such an event. This directly falsifies the claim that a 'mass UE detachment event' occurred.
- **SMF metrics showing zero PDU session setup attempts and zero active sessions, confirming complete session loss** ✗ CONTRADICTS
    - *Tool:* `get_nf_metrics()`
    - *Observation:* [EVIDENCE: get_nf_metrics() -> "SMF [4 PDU] (via prometheus): bearers_active = 4.0, fivegs_smffunction_sm_sessionnbr = 4.0, pfcp_sessions_active = 4.0, ues_active = 2.0"]
    - *Comment:* The hypothesis claims a 'cascading teardown of PDU sessions and bearers'. However, SMF metrics show that sessions and bearers are still considered active. The core network has not torn down the sessions; it has lost contact with the RAN where the UEs were connected.

**Alternative suspects:** ran


## Evidence Validation (Phase 6)

**Overall verdict:** clean
**Overall confidence:** high

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 4 | 3/3 | clean | high |
| `InvestigatorAgent_h2` | 4 | 3/3 | clean | high |
| `InvestigatorAgent_h3` | 3 | 3/3 | clean | high |


## Ground Truth

**Failure domain:** data_plane  
**Protocol impact:** GTP-U  
**Affected components:** nr_gnb  
**Severity:** degraded

## Agent Diagnosis

**Model:** v6-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 119.2s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: A complete failure of the gNodeB (gNB) has caused a total loss of RAN connectivity, preventing all UEs from accessing the 5G network.
> - **timeline**:
>     1.  The N2 association between the gNB and the AMF was dropped (`core.amf.gnb_association_drop`).
>     2.  As a direct result, all UEs connected via the RAN were lost to the core network (`core.amf.ran_ue_full_loss`, `core.amf.ran_ue_sudden_drop`).
>     3.  PDU sessions in the core were left stranded without a corresponding UE bearer (`core.smf.sessions_per_ue_drop`).
> - **root_cause**: The gNB component has failed. It is offline and unreachable from the 5G core network. The primary suspect network function is `ran`.
> - **affected_components**:
>     - `ran (gNB)`: Root Cause
>     - `core (AMF)`: Symptomatic
>     - `core (SMF)`: Symptomatic
> - **recommendation**: The operator should investigate the `nr_gnb` component on its host system to determine why it is not running. Check the host's system logs and the container runtime logs for any errors related to the `nr_gnb` process that occurred at the time of the outage.
> - **confidence**: high
> - **explanation**: The investigation confirmed with high confidence that the root cause is a failure of the gNodeB. This hypothesis (`h1`) was supported by multiple probes showing the `nr_gnb` container is not running and is unreachable from the AMF. Alternative hypotheses were disproven: an AMF failure (`h2`) was ruled out as the AMF container is healthy with no relevant errors in its logs, and a mass UE detachment event (`h3`) was falsified because the core network never received detachment signals and still considers the PDU sessions active. The RAN simply disappeared.

### Scoring Breakdown

**Overall score: 100%**

**Scorer assessment:** The agent provided an outstanding diagnosis, accurately identifying the root cause, affected components, severity, and fault type, with correct layer attribution and appropriate confidence.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | Yes | The agent correctly identified the gNB component failure and its unreachability as the root cause, which directly matches the simulated failure mode of 'gNB Radio Link Failure' and 'nr_gnb' being unreachable. |
| Component overlap | 100% | The agent explicitly named 'ran (gNB)' as the root cause component. It also correctly identified AMF and SMF as symptomatically affected, showing good causal reasoning. |
| Severity correct | Yes | The agent described the failure as a 'complete failure', 'total loss of RAN connectivity', and 'offline and unreachable', which accurately reflects the complete outage caused by killing the gNB. |
| Fault type identified | Yes | The agent identified the gNB as 'offline and unreachable', which correctly describes the observable fault type of a component being unreachable. |
| Layer accuracy | Yes | The agent correctly attributed the gNB failure to the 'ran' layer, marking it 'red', which aligns with the ground truth that 'nr_gnb' belongs to the 'ran' layer. |
| Confidence calibrated | Yes | The agent stated 'high' confidence, which is appropriate given the accuracy and completeness of its diagnosis, supported by clear evidence and falsification of alternative hypotheses. |

**Ranking position:** #1 — The correct root cause (gNB failure) was presented as the top hypothesis (h1) with the highest fit score.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 108,466 |
| Output tokens | 5,136 |
| Thinking tokens | 11,977 |
| **Total tokens** | **125,579** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| EventAggregator | 0 | 0 | 0 |
| CorrelationAnalyzer | 0 | 0 | 0 |
| NetworkAnalystAgent | 24,831 | 3 | 4 |
| InstructionGeneratorAgent | 13,064 | 1 | 2 |
| InvestigatorAgent_h1 | 31,871 | 4 | 5 |
| InvestigatorAgent_h2 | 26,384 | 4 | 5 |
| InvestigatorAgent_h3 | 23,024 | 3 | 4 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 6,405 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 258.8s
