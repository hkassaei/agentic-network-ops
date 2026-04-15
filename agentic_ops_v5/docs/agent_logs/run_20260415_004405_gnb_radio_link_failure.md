# Episode Report: gNB Radio Link Failure

**Agent:** v5  
**Episode ID:** ep_20260415_003954_gnb_radio_link_failure  
**Date:** 2026-04-15T00:39:56.041982+00:00  
**Duration:** 248.5s  

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
- **Nodes with significant deltas:** 3
- **Nodes with any drift:** 3

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

### Metrics Changes

| Node | Metric | Baseline | Current | Delta |
|------|--------|----------|---------|-------|
| amf | ran_ue | 2.0 | 0.0 | -2.0 |
| amf | gnb | 1.0 | 0.0 | -1.0 |
| pcscf | core:rcv_requests_options | 14.0 | 42.0 | 28.0 |
| pcscf | httpclient:connfail | 15.0 | 43.0 | 28.0 |
| scscf | ims_usrloc_scscf:impu_collisions | 0.0 | 1.0 | 1.0 |
| scscf | ims_usrloc_scscf:subscription_collisions | 0.0 | 1.0 | 1.0 |
| scscf | ims_usrloc_scscf:contact_collisions | 0.0 | 1.0 | 1.0 |

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 0.96 (threshold: 0.70, trained on 99 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following specific metrics were flagged as the top contributors to the anomaly. These MUST be reflected in your layer ratings:

| Component | Metric | Current | Learned Normal | Severity |
|-----------|--------|---------|---------------|----------|
| normalized | smf.sessions_per_ue | 0.00 | 2.00 | HIGH |
| icscf | ims_icscf:lir_avg_response_time | 0.00 | 51.03 | HIGH |
| normalized | smf.bearers_per_ue | 0.00 | 2.66 | HIGH |
| normalized | upf.gtp_outdatapktn3upf_per_ue | 0.00 | 2.50 | MEDIUM |
| normalized | upf.gtp_indatapktn3upf_per_ue | 0.00 | 2.58 | MEDIUM |
| icscf | ims_icscf:uar_avg_response_time | 50.00 | 61.39 | LOW |
| icscf | cdp:average_response_time | 50.00 | 58.83 | LOW |
| normalized | pcscf.dialogs_per_ue | 0.00 | 0.65 | LOW |
| derived | upf_activity_during_calls | 1.00 | 0.39 | LOW |

## Network Analysis (Phase 1)

**Summary:** The network is down due to a Radio Access Network (RAN) failure, with no UEs able to connect.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | All infrastructure components are running and responsive. |
| **ran** | 🔴 RED | RAN is down; no gNB is connected to the core network. |
| **core** | 🔴 RED | Core is impacted by the RAN failure, with SMF showing significant anomalies. |
| **ims** | 🟡 YELLOW | IMS layer is likely affected by the upstream RAN failure, showing signs of no activity. |

**RAN evidence:**
- ran_ue=0 from get_nf_metrics (expected: >0)
- gnb=0 from get_nf_metrics (expected: >0)
- N2 (NGAP) link to AMF is INACTIVE per get_network_topology
- N3 (GTP-U) link to UPF is INACTIVE per get_network_topology

**CORE evidence:**
- smf.sessions_per_ue=0.00 flagged by AnomalyScreener (HIGH severity)
- smf.bearers_per_ue=0.00 flagged by AnomalyScreener (HIGH severity)
- AMF reports gnb=0, consistent with RAN failure.

**IMS evidence:**
- ims_icscf:lir_avg_response_time=0.00 flagged by AnomalyScreener (HIGH severity)

**Suspect components:**

- **nr_gnb** (high): AMF reports zero connected gNBs (gnb=0) and the N2/N3 links are inactive. The 'ran_down_invalidates_ims' stack rule indicates this is the primary failure.
- **amf** (medium): Directly connected to the failed gNB. It reports gnb=0 and ran_ue=0, indicating a loss of connection with the RAN.
- **smf** (high): Top-ranked anomaly from the screener ('smf.sessions_per_ue' and 'smf.bearers_per_ue' are zero), indicating a severe deviation from the learned baseline. This is likely a direct consequence of the RAN failure.
- **icscf** (low): Flagged with a HIGH severity anomaly by the screener, but the metric value (lir_avg_response_time=0) suggests a lack of traffic, which is expected when the RAN is down. This is likely a downstream symptom.

**Investigation hint:** The investigation should prioritize the RAN layer. The AMF is not detecting any gNB connection, and key metrics like 'ran_ue' and 'gnb' are zero, indicating a fundamental RAN failure. Start by examining the 'nr_gnb' container's logs and status to determine why it failed to connect to the AMF. The anomalies detected in the SMF and I-CSCF are almost certainly downstream symptoms of the RAN outage. Once the gNB connectivity is restored, these downstream issues are expected to resolve automatically.

**Tools called:** get_vonr_components, get_network_topology, get_network_status, get_nf_metrics, get_dp_quality_gauges, read_env_config, measure_rtt, compare_to_baseline, check_stack_rules


## Pattern Match (Phase 2)

**✅ Match:** N2 connectivity loss — RAN/gNB unreachable, radio access lost

- **Confidence:** very_high
- **Failure domain:** ran
- **Matched signatures:** 1
  - `ran_failure` (score: 1.0)
- **Baseline anomalies:** 2 metrics across 1 components


## Investigation Instruction (Phase 3)

> Instruction generation skipped: Network Analyst diagnosis is definitive.

## Investigation (Phase 4)

> Investigation skipped: Network Analyst produced a high-confidence diagnosis with definitive evidence (RED layer + high-confidence suspect). See Phase 1 analysis.

## Evidence Validation (Phase 5)

**Verdict:** clean
**Investigator confidence:** high
**Citations:** 4/4 verified

```
Investigator was intentionally skipped (Network Analyst diagnosis was definitive). Validating Network Analyst evidence only.
Network Analyst made 9 tool calls. Evidence validation: 4/4 NA citations verified.
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
```

## Ground Truth

**Failure domain:** data_plane  
**Protocol impact:** GTP-U  
**Affected components:** nr_gnb  
**Severity:** degraded

## Agent Diagnosis

**Model:** v5-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 101.0s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: The network is down due to a complete failure of the Radio Access Network (RAN), resulting in a total loss of connectivity between the gNB and the 5G Core.
> - **timeline**:
>     1.  The N2 control plane link between the `nr_gnb` and the AMF becomes inactive.
>     2.  The AMF reports that zero gNBs (`gnb=0`) and zero UEs (`ran_ue=0`) are connected to the network.
>     3.  As a result of no active UEs, the SMF's session and bearer counts drop to zero, triggering high-severity anomalies.
>     4.  The IMS layer ceases to receive traffic from the core, leading to inactivity anomalies in components like the I-CSCF.
> - **root_cause**: A complete failure of the Radio Access Network. The AMF reports no connected gNBs (`gnb=0`), indicating a loss of the N2 (NGAP) control plane interface. This prevents any User Equipment (UE) from attaching to the network, causing a full service outage.
> - **affected_components**:
>     - `nr_gnb`: Root Cause
>     - `amf`: Symptomatic
>     - `smf`: Symptomatic
>     - `icscf`: Symptomatic
> - **recommendation**: The investigation should focus exclusively on the RAN. Verify the status and logs of the `nr_gnb` component to understand why it is not connected to the AMF. Check for transport-level connectivity issues (e.g., routing, firewalls) between the gNB and the AMF.
> - **confidence**: high
> - **explanation**: The diagnosis is definitive. Evidence from the AMF shows `gnb=0` and `ran_ue=0`, and network topology confirms the N2 link is `INACTIVE`. This points conclusively to a RAN failure as the root cause. The significant anomalies flagged in the SMF and IMS are direct, downstream consequences of the RAN being down and are not independent problems. Restoring gNB connectivity to the core is expected to resolve all observed symptoms.

### Scoring Breakdown

**Overall score: 100%**

**Scorer assessment:** The agent provided an excellent and accurate diagnosis, correctly identifying the root cause, affected components, severity, fault type, and layer, all with appropriate confidence and strong supporting evidence.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | Yes | The agent correctly identified a 'complete failure of the Radio Access Network' with 'no connected gNBs' and 'loss of the N2 (NGAP) control plane interface', which is semantically equivalent to a gNB radio link failure and the gNB being unreachable. |
| Component overlap | 100% | The agent correctly identified 'nr_gnb' as the root cause component. It also correctly listed downstream affected components. |
| Severity correct | Yes | The agent described the failure as a 'complete failure' and 'full service outage', which accurately reflects the impact of killing the gNB. |
| Fault type identified | Yes | The agent identified the fault as a 'complete failure' of the RAN, with 'no connected gNBs' and an 'INACTIVE' N2 link, which aligns with the observable 'component completely unreachable' fault type. |
| Layer accuracy | Yes | The agent correctly attributed the failure to the 'ran' layer, which is the correct ontology layer for 'nr_gnb'. |
| Confidence calibrated | Yes | The agent stated 'high' confidence, which is appropriate given the accuracy and strong evidence provided in the diagnosis. |

**Ranking position:** #1 — The agent explicitly listed 'nr_gnb' as the 'Root Cause' and the primary suspect component.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 82,564 |
| Output tokens | 2,221 |
| Thinking tokens | 6,253 |
| **Total tokens** | **91,038** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| NetworkAnalystAgent | 82,553 | 16 | 5 |
| PatternMatcherAgent | 0 | 0 | 0 |
| EvidenceValidatorAgent | 0 | 0 | 0 |
| SynthesisAgent | 8,485 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 248.5s
