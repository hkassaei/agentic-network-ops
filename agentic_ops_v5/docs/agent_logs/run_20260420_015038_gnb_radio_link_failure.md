# Episode Report: gNB Radio Link Failure

**Agent:** v5  
**Episode ID:** ep_20260420_014605_gnb_radio_link_failure  
**Date:** 2026-04-20T01:46:07.315911+00:00  
**Duration:** 270.6s  

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
- **Nodes with any drift:** 2

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

### Metrics Changes

| Node | Metric | Baseline | Current | Delta |
|------|--------|----------|---------|-------|
| amf | gnb | 1.0 | 0.0 | -1.0 |
| amf | ran_ue | 2.0 | 0.0 | -2.0 |
| pcscf | core:rcv_requests_options | 44.0 | 69.0 | 25.0 |
| pcscf | httpclient:connfail | 45.0 | 70.0 | 25.0 |

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

## Network Analysis (Phase 1)

**Summary:** The network is down due to a failure in the Radio Access Network (RAN), preventing any UEs from connecting.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | All infrastructure components (mongo, mysql, dns) are running and responsive. |
| **ran** | 🔴 RED | RAN is completely disconnected from the core network, preventing all UE attachments. |
| **core** | 🟡 YELLOW | Core components are running, but SMF holds stale PDU sessions for UEs that are no longer connected at the RAN level. Data plane is idle, which is expected. |
| **ims** | 🟡 YELLOW | IMS components are running, but hold stale registrations. This is a downstream symptom of the RAN failure. |

**RAN evidence:**
- N2 (NGAP) link from RAN to AMF is INACTIVE (get_network_topology)
- N3 (GTP-U) link from RAN to UPF is INACTIVE (get_network_topology)
- amf.gnb = 0 (get_nf_metrics, expected: 1)
- amf.ran_ue = 0 (get_nf_metrics, expected: 2)

**CORE evidence:**
- SMF has stale state: smf.ues_active = 2 while amf.ran_ue = 0.
- Anomaly screener flagged smf.sessions_per_ue and smf.bearers_per_ue as HIGH severity due to inconsistency between SMF session count and AMF UE count.

**IMS evidence:**
- P-CSCF has stale IMS registrations: pcscf.ims_usrloc_pcscf:registered_contacts = 2, but no UEs are connected to the network.

**Suspect components:**

- **nr_gnb** (high): The gNB is not connected to the AMF (N2 interface is INACTIVE) or UPF (N3 is INACTIVE), which is the root cause of all other observed issues, including the lack of connected UEs and zero data plane traffic. AMF metrics confirm gnb=0.
- **smf** (low): SMF is showing anomalous metrics because it has stale sessions for disconnected UEs. This is likely a downstream symptom of the RAN failure, not a root cause, but its state should be verified.

**Investigation hint:** The root cause of the outage is at the RAN layer. All other anomalies, including those on the SMF, are downstream symptoms. Prioritize investigating the `nr_gnb` component. Check its logs and status to understand why it failed to establish or maintain its N2 (NGAP) connection with the AMF. The data plane being idle is an expected consequence of the RAN failure, not an independent problem.

**Tools called:** get_vonr_components, get_network_topology, get_network_status, get_nf_metrics, get_dp_quality_gauges, read_env_config, measure_rtt, compare_to_baseline, check_stack_rules


## Pattern Match (Phase 2)

**✅ Match:** N2 connectivity loss — RAN/gNB unreachable, radio access lost

- **Confidence:** very_high
- **Failure domain:** ran
- **Matched signatures:** 1
  - `ran_failure` (score: 1.0)
- **Baseline anomalies:** 2 metrics across 1 components


## Investigation Instruction (Phase 3)

> PRIMARY HYPOTHESIS TO FALSIFY: nr_gnb is down/unreachable, causing N2 and N3 interfaces to be inactive.
>
> FALSIFICATION PROBES (minimum 2, target 3):
>
> Probe 1 — AMF:
>   Tool: `read_container_logs(container='amf', grep='NGAP')`
>   Expected if hypothesis holds: AMF logs show no incoming NGAP messages from the gNB, or only messages indicating it's waiting for a connection from the gNB.
>   Falsifying observation: AMF logs show active NGAP connection attempts from the gNB (e.g., NGAP SETUP REQUEST) that are being rejected by the AMF. This would imply the gNB is alive and attempting to connect, but the AMF is preventing the connection.
>
> Probe 2 — UPF:
>   Tool: `read_container_logs(container='upf', grep='GTP-U')`
>   Expected if hypothesis holds: UPF logs show no incoming GTP-U traffic from the gNB, or only messages related to the inactive N3 link not being established by the gNB.
>   Falsifying observation: UPF logs show active GTP-U tunnel establishment attempts or data traffic from the gNB (e.g., malformed packets, unexpected messages), indicating the gNB is online but potentially misconfigured or sending corrupted data.
>
> Probe 3 — SMF:
>   Tool: `measure_rtt(from='smf', to_ip='172.22.0.23')`
>   Expected if hypothesis holds: 100% packet loss when pinging the gNB's IP, consistent with the gNB being unreachable from the core network.
>   Falsifying observation: Successful RTT (low latency, 0% packet loss) to the gNB's IP. This would indicate the gNB is reachable from the core network, suggesting the issue lies in the specific N2/N3 control plane setup (e.g., SCTP/GTP-U configuration) rather than gNB unreachability.
>
> ADDITIONAL NOTES:
>   - The Network Analyst already probed the AMF and used its metrics (`amf.gnb = 0`, `amf.ran_ue = 0`) as key evidence. The falsification probes for AMF and UPF specifically target logs for deeper, potentially contradicting, insights into connection attempts and rejections, rather than just state.
>   - The IP address '172.22.0.23' is inferred as the gNB's IP based on the pattern matching diagnostic actions.

## Investigation (Phase 4)

> ### Hypothesis
> - **NA's primary suspect:** nr_gnb
> - **NA's claimed fault:** The gNB is down or unreachable, causing the N2 and N3 interfaces to be inactive.
>
> ### Falsification Probes Executed
> - **Probe 1 — AMF:**
>   - **Tool call:** `read_container_logs(container='amf', grep='NGAP', since_seconds=120)`
>   - **Observation:** [EVIDENCE: read_container_logs(container='amf', grep='NGAP', since_seconds=120) -> "(no log output)"]
>   - **Compared to expected:** CONSISTENT — The absence of any NGAP messages in the last two minutes aligns with the hypothesis that the gNB is offline and not attempting to establish an N2 connection with the AMF.
>
> - **Probe 2 — UPF:**
>   - **Tool call:** `read_container_logs(container='upf', grep='GTP-U', since_seconds=120)`
>   - **Observation:** [EVIDENCE: read_container_logs(container='upf', grep='GTP-U', since_seconds=120) -> "(no log output)"]
>   - **Compared to expected:** CONSISTENT — The absence of any GTP-U related messages aligns with the hypothesis that the gNB is offline and not establishing or using the N3 data plane tunnel.
>
> - **Probe 3 — SMF:**
>   - **Tool call:** `measure_rtt(container='smf', target_ip='172.22.0.23')`
>   - **Observation:** [EVIDENCE: measure_rtt(container='smf', target_ip='172.22.0.23') -> "3 packets transmitted, 0 received, +3 errors, 100% packet loss"]
>   - **Compared to expected:** CONSISTENT — The 100% packet loss confirms that the gNB's IP address is unreachable from the core network, which is the strongest possible confirmation of the NA's hypothesis.
>
> ### Verdict
> - **Verdict:** NOT_FALSIFIED
> - **Reasoning:** All three probes produced results that directly support the Network Analyst's hypothesis. The RTT measurement from the core (`smf`) to the gNB's IP address showed 100% packet loss, confirming it is unreachable at the transport layer. The lack of recent NGAP and GTP-U logs on the AMF and UPF, respectively, is the expected consequence of this transport failure.
>
> ### Layer Status (brief)
> - Transport: RED — The RAN (`nr_gnb`) is unreachable from the core network.
> - Core: YELLOW — Core components are running but hold stale session information as a result of the RAN failure.
> - Application: YELLOW — IMS services have stale registrations, which is a downstream symptom of the RAN outage.

## Evidence Validation (Phase 5)

**Verdict:** clean
**Investigator confidence:** high
**Citations:** 7/7 verified

```
Evidence validation: 7/7 citations verified (0 unmatched). Investigator: 3 citations from 2 tool calls.
Verdict: clean. Confidence: high.

Tool calls vs. citations:
  NetworkAnalystAgent:
    ✗ check_stack_rules — called but NOT cited in output
    ✗ compare_to_baseline — called but NOT cited in output
    ✗ get_dp_quality_gauges — called but NOT cited in output
    ✗ get_network_status — called but NOT cited in output
    ✓ get_network_topology — called AND cited (2x)
    ✓ get_nf_metrics — called AND cited (2x)
    ✗ get_vonr_components — called but NOT cited in output
    ✗ measure_rtt — called but NOT cited in output
    ✗ read_env_config — called but NOT cited in output
  InvestigatorAgent:
    ✓ measure_rtt — called AND cited (1x)
    ✓ read_container_logs — called AND cited (2x)
```

## Ground Truth

**Failure domain:** data_plane  
**Protocol impact:** GTP-U  
**Affected components:** nr_gnb  
**Severity:** degraded

## Agent Diagnosis

**Model:** v5-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 139.7s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: The network is down due to the Radio Access Network (gNB) being completely unreachable from the core network.
> - **timeline**:
>     1. The `nr_gnb` component became unreachable from the core network, confirmed by 100% packet loss when pinging its IP address (`172.22.0.23`).
>     2. As a result, the N2 control plane link to the AMF and the N3 data plane link to the UPF both went down.
>     3. The AMF reported the loss of connection, with its metrics dropping to `gnb = 0` and `ran_ue = 0`.
>     4. All UE connectivity was lost, and user plane traffic ceased. Downstream components like the SMF and P-CSCF now hold stale session/registration data from before the failure.
> - **root_cause**: A transport-layer failure has made the `nr_gnb` unreachable from the 5G core. This severed the N2 (control plane) and N3 (user plane) interfaces, causing a complete loss of radio access for all UEs.
> - **affected_components**:
>     - `nr_gnb`: Root Cause
>     - `amf`: Symptomatic
>     - `upf`: Symptomatic
>     - `smf`: Symptomatic
>     - `pcscf`: Symptomatic
> - **recommendation**: Prioritize investigating the `nr_gnb` component and its transport path to the core network. Verify the gNB's power, software status, and physical/IP connectivity to the AMF and UPF.
> - **confidence**: high
> - **explanation**: The network outage is caused by a complete failure in the Radio Access Network (RAN). The gNodeB (`nr_gnb`) is offline or unreachable at the IP layer, which was confirmed by a 100% packet loss from the core network during the investigation. This transport failure is the root cause, leading to the observed inactive N2/N3 interfaces and the inability for any UEs to connect. All other anomalies, such as stale sessions in the SMF and stale registrations in the IMS, are downstream symptoms of the RAN being down.

### Scoring Breakdown

**Overall score: 100%**

**Scorer assessment:** The agent provided a perfect diagnosis, accurately identifying the root cause, affected components, severity, fault type, and layer, with appropriate confidence and clear ranking.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | Yes | The agent correctly identified the gNB being unreachable due to a transport-layer failure as the root cause, which directly matches the simulated 'gNB Radio Link Failure' where the gNB was killed and became unreachable. |
| Component overlap | 100% | The agent correctly identified 'nr_gnb' as the root cause and listed it as the primary affected component. It also correctly identified downstream symptomatic components. |
| Severity correct | Yes | The agent described the failure as a 'complete loss of radio access for all UEs' and a 'network outage', which accurately reflects the complete unavailability caused by killing the gNB. |
| Fault type identified | Yes | The agent identified the fault type as 'completely unreachable' and '100% packet loss' for the gNB, which is the observable class of failure for a component being down. |
| Layer accuracy | Yes | The agent correctly attributed the failure to the 'ran' layer, rating it RED, which aligns with 'nr_gnb' belonging to the ran layer in the ontology. |
| Confidence calibrated | Yes | The agent's diagnosis is highly accurate and well-supported by evidence (100% packet loss, N2/N3 inactive, AMF metrics), making its 'high' confidence level appropriate. |

**Ranking position:** #1 — The agent explicitly stated 'nr_gnb' as the root cause and listed it first among affected components and suspect components with high confidence.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 130,408 |
| Output tokens | 3,026 |
| Thinking tokens | 10,597 |
| **Total tokens** | **144,031** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| NetworkAnalystAgent | 79,162 | 12 | 5 |
| PatternMatcherAgent | 0 | 0 | 0 |
| InstructionGeneratorAgent | 18,985 | 2 | 2 |
| InvestigatorAgent | 35,924 | 3 | 4 |
| EvidenceValidatorAgent | 0 | 0 | 0 |
| SynthesisAgent | 9,960 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 270.6s
