# Episode Report: IMS Network Partition

**Agent:** v5  
**Episode ID:** ep_20260415_031804_ims_network_partition  
**Date:** 2026-04-15T03:18:06.166809+00:00  
**Duration:** 235.8s  

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
- **Nodes with significant deltas:** 3
- **Nodes with any drift:** 4

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

### Metrics Changes

| Node | Metric | Baseline | Current | Delta |
|------|--------|----------|---------|-------|
| pcscf | dialog_ng:processed | 0.0 | 3.0 | 3.0 |
| pcscf | core:rcv_requests_invite | 11.0 | 14.0 | 3.0 |
| rtpengine | owned_sessions | 0.0 | 3.0 | 3.0 |
| rtpengine | total_sessions | 0.0 | 3.0 | 3.0 |
| smf | bearers_active | 4.0 | 7.0 | 3.0 |

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 0.94 (threshold: 0.70, trained on 99 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following specific metrics were flagged as the top contributors to the anomaly. These MUST be reflected in your layer ratings:

| Component | Metric | Current | Learned Normal | Severity |
|-----------|--------|---------|---------------|----------|
| rtpengine | packet_loss_standard_deviation | 15.00 | 0.00 | HIGH |
| rtpengine | average_packet_loss | 8.00 | 0.00 | HIGH |
| icscf | ims_icscf:lir_avg_response_time | 0.00 | 51.03 | HIGH |
| scscf | ims_auth:mar_avg_response_time | 106.00 | 88.89 | MEDIUM |
| scscf | ims_registrar_scscf:sar_avg_response_time | 105.00 | 119.92 | MEDIUM |
| normalized | upf.gtp_outdatapktn3upf_per_ue | 0.03 | 2.50 | MEDIUM |
| normalized | upf.gtp_indatapktn3upf_per_ue | 0.13 | 2.58 | MEDIUM |
| normalized | pcscf.dialogs_per_ue | 0.00 | 0.65 | LOW |
| derived | upf_activity_during_calls | 1.00 | 0.39 | LOW |

## Network Analysis (Phase 1)

**Summary:** The network is experiencing a critical failure in the IMS layer, centered around RTPEngine, which is reporting severe packet loss.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | All infrastructure components (mongo, mysql, dns) are running and responsive. |
| **ran** | 🟢 GREEN | gNB is connected and 2 UEs are attached to the AMF. |
| **core** | 🟡 YELLOW | UPF throughput is near zero, flagged as anomalous by the screener. However, with no active calls, this is also the expected idle state. |
| **ims** | 🔴 RED | Critical failure: RTPEngine is reporting extreme packet loss. IMS signaling components (ICSCF, SCSCF) also show significant anomalies, indicating call setup and routing failures. |

**CORE evidence:**
- normalized upf.gtp_outdatapktn3upf_per_ue: 0.03 (learned normal: 2.50)
- normalized upf.gtp_indatapktn3upf_per_ue: 0.13 (learned normal: 2.58)

**IMS evidence:**
- rtpengine average_packet_loss: 8.00 (learned normal: 0.00)
- rtpengine packet_loss_standard_deviation: 15.00 (learned normal: 0.00)
- icscf ims_icscf:lir_avg_response_time: 0.00 (learned normal: 51.03)
- scscf ims_auth:mar_avg_response_time: 106.00 (learned normal: 88.89)

**Suspect components:**

- **rtpengine** (high): The anomaly screener flagged RTPEngine with the highest severity score due to extreme packet loss (average_packet_loss: 8.00 vs normal 0.00). This directly impacts voice media quality and is the most likely epicenter of the failure.
- **icscf** (medium): The screener flagged a HIGH severity anomaly for 'ims_icscf:lir_avg_response_time' being 0. This indicates a failure in handling user location queries (LIR), which is essential for routing IMS traffic.
- **upf** (low): The screener flagged significantly lower-than-normal GTP traffic. While this is expected in the current idle state, the deviation from the learned baseline suggests a drop in activity, likely as a downstream symptom of the IMS failures (i.e., failed calls lead to no data traffic).

**Investigation hint:** The primary suspect is RTPEngine. The AnomalyScreener detected severe packet loss originating from it, which is a critical media plane failure. Although live RTT checks to RTPEngine are currently clean, the metrics snapshot captured the event. The Investigator should prioritize examining RTPEngine's container logs and internal statistics from the event window (last 123 seconds) to determine the cause of this loss. The anomalies in the IMS signaling plane (ICSCF, SCSCF) are likely cascading symptoms of calls failing due to the underlying media quality degradation.

**Tools called:** get_vonr_components, get_network_topology, get_network_status, get_nf_metrics, get_dp_quality_gauges, read_env_config, measure_rtt, check_stack_rules, compare_to_baseline


## Pattern Match (Phase 2)

**❌ Match:** No matching signature found

- **Confidence:** low
- **Failure domain:** unknown
- **Baseline anomalies:** 3 metrics across 3 components


## Investigation Instruction (Phase 3)

> Instruction generation skipped: Network Analyst diagnosis is definitive.

## Investigation (Phase 4)

> Investigation skipped: Network Analyst produced a high-confidence diagnosis with definitive evidence (RED layer + high-confidence suspect). See Phase 1 analysis.

## Evidence Validation (Phase 5)

**Verdict:** clean
**Investigator confidence:** high
**Citations:** 0/0 verified

```
Investigator was intentionally skipped (Network Analyst diagnosis was definitive). Validating Network Analyst evidence only.
Network Analyst made 9 tool calls. Evidence validation: 0/0 NA citations verified.
Verdict: clean. Confidence: high.

Tool calls vs. citations:
  NetworkAnalystAgent:
    ✗ check_stack_rules — called but NOT cited in output
    ✗ compare_to_baseline — called but NOT cited in output
    ✗ get_dp_quality_gauges — called but NOT cited in output
    ✗ get_network_status — called but NOT cited in output
    ✗ get_network_topology — called but NOT cited in output
    ✗ get_nf_metrics — called but NOT cited in output
    ✗ get_vonr_components — called but NOT cited in output
    ✗ measure_rtt — called but NOT cited in output
    ✗ read_env_config — called but NOT cited in output
```

## Ground Truth

**Failure domain:** ims_signaling  
**Protocol impact:** SIP  
**Affected components:** pcscf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v5-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 99.2s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: The IMS media plane has failed due to severe packet loss originating from RTPEngine, causing VoNR call setups to fail.
> - **timeline**:
>     1. The `rtpengine` component began reporting severe media quality degradation, with metrics showing an average packet loss of 8.00 (normal is 0.00).
>     2. Concurrently, IMS signaling components registered failures. The I-CSCF showed a complete failure to process user location queries (`lir_avg_response_time` of 0), indicating call routing has stopped.
>     3. As a direct result of media plane and signaling failures, no VoNR calls could be established, causing user plane traffic on the UPF to drop to near-zero levels.
> - **root_cause**: The root cause is a critical failure within the `rtpengine` component, which handles the Real-time Transport Protocol (RTP) media streams for voice calls. The component is reporting an unsustainable level of packet loss, making voice communication impossible. This media plane failure is the primary trigger for the observed cascading failures in the IMS signaling plane (I-CSCF, S-CSCF).
> - **affected_components**:
>     - `rtpengine`: Root Cause
>     - `icscf`: Symptomatic
>     - `scscf`: Symptomatic
>     - `upf`: Symptomatic
> - **recommendation**: The primary focus should be on `rtpengine`. Investigate the component's container logs and internal statistics from the event window to determine the source of the packet loss. Check for resource exhaustion (CPU, memory), network connectivity issues specific to the `rtpengine` pod, or internal software faults.
> - **confidence**: high
> - **explanation**: The network outage is isolated to the IMS layer. The root cause is a definitive failure in the `rtpengine` media proxy, which is experiencing 8% average packet loss, rendering the media plane unusable for voice calls. All other anomalies, such as the signaling errors in the I-CSCF and the near-zero data traffic at the UPF, are downstream symptoms of calls failing due to this core media quality issue. The underlying 5G core and RAN infrastructure remain healthy.

### Scoring Breakdown

**Overall score: 20%**

**Scorer assessment:** The agent incorrectly identified the root cause as RTPEngine packet loss instead of a P-CSCF network partition, but correctly assessed the severity as a critical outage and identified the IMS layer as affected, despite poor confidence calibration.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | No | The simulated failure was a network partition of the P-CSCF, severing SIP signaling between P-CSCF and I/S-CSCF. The agent diagnosed a critical failure within the `rtpengine` component due to severe packet loss, which is a different failure mode (media plane vs. signaling plane) and a different component. |
| Component overlap | 0% | The primary affected component in the simulated failure was 'pcscf'. The agent identified 'rtpengine' as the root cause and primary affected component. While 'icscf' and 'scscf' were mentioned as symptomatic, the primary component 'pcscf' was not identified, and the root cause component was incorrect. |
| Severity correct | Yes | The simulated failure described SIP signaling being 'completely severed' and new calls failing, indicating a complete outage. The agent's diagnosis of 'severe packet loss', 'making voice communication impossible', and 'no VoNR calls could be established' also correctly reflects a critical service outage. |
| Fault type identified | No | The simulated failure was a 'Network partition' / 'component isolated' / 'SIP signaling severed'. The agent identified 'severe packet loss' and 'media plane failure', which is a degradation type of fault, not a partition or unreachability. |
| Layer accuracy | Yes | The 'pcscf' component belongs to the 'ims' layer. The agent correctly identified the 'ims' layer as being in a RED state due to the diagnosed issues, even though the specific component and fault type were incorrect. 'rtpengine' is also an IMS component, so attributing its failure to the IMS layer is consistent with the ontology. |
| Confidence calibrated | No | The agent stated 'high' confidence, but the root cause, primary affected component, and fault type were all incorrect. High confidence for an incorrect diagnosis indicates poor calibration. |

**Ranking:** The correct root cause (P-CSCF network partition) was not identified or listed among the agent's candidates.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 84,724 |
| Output tokens | 2,064 |
| Thinking tokens | 5,307 |
| **Total tokens** | **92,095** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| NetworkAnalystAgent | 84,709 | 13 | 6 |
| PatternMatcherAgent | 0 | 0 | 0 |
| EvidenceValidatorAgent | 0 | 0 | 0 |
| SynthesisAgent | 7,386 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 235.8s

---

## Post-Run Analysis

### Overview

Score: 20%. The agent misdiagnosed an IMS network partition (P-CSCF severed from I-CSCF and S-CSCF via iptables DROP rules) as an RTPEngine packet loss failure. The actual root cause component (P-CSCF) was never mentioned. The Investigator was skipped, preventing any chance of discovering the partition via targeted RTT probes.

### Issue 1: RTPEngine cumulative metrics are stale

The anomaly screener flagged `rtpengine.average_packet_loss: 8.0` and `rtpengine.packet_loss_standard_deviation: 15.0` as HIGH severity. But these are **cumulative lifetime averages** from the RTPEngine container — they include packet loss from previous chaos runs (Data Plane Degradation, Call Quality Degradation) that happened hours or days ago. They don't reflect the current scenario.

RTPEngine's `average_packet_loss` is computed as `sum_of_all_packet_loss_values_sampled / total_number_of_packet_loss_samples` across ALL sessions since the container started. Once a previous scenario introduced packet loss, this average stays elevated forever (it can only go down slowly as more healthy sessions dilute it).

The anomaly model trained on a fresh stack where these values were 0.0. After running fault scenarios that cause real packet loss, the cumulative averages shift permanently. The model then flags them as anomalous in every subsequent run — even when there's no current packet loss.

These metrics need to either be excluded from the anomaly model (since they're not indicators of current state) or replaced with a rate-based or delta-based version that only reflects recent changes.

### Issue 2: Network Analyst didn't check P-CSCF ↔ I-CSCF/S-CSCF connectivity

The fault was iptables DROP rules blocking traffic between P-CSCF (172.22.0.21) and I-CSCF (172.22.0.19) / S-CSCF (172.22.0.20). Running `measure_rtt("pcscf", "172.22.0.19")` would have shown 100% packet loss — immediate confirmation of a network partition.

Instead, the NA checked RTT to RTPEngine (which was clean) and concluded "live RTT checks to RTPEngine are currently clean." It never checked the signaling path between CSCFs.

The `icscf.ims_icscf:lir_avg_response_time = 0` was a strong clue — a response time of 0ms means no LIR responses were received at all, indicating a connectivity break on the Diameter/SIP path. The NA noted this as a HIGH anomaly but attributed it to "call routing has stopped" without investigating WHY routing stopped (i.e., checking if the path between P-CSCF and I-CSCF was actually reachable).

### Issue 3: Investigator skip was incorrect

The skip logic triggered because the NA had a HIGH-confidence suspect (`rtpengine`) and a RED layer (`ims`). But the NA's diagnosis was wrong — `rtpengine` wasn't the cause. If the Investigator had run, the Instruction Generator would have directed it to check P-CSCF connectivity, and `measure_rtt` from P-CSCF to I-CSCF/S-CSCF would have revealed the partition.

This is the same class of skip problem as the MongoDB episode — the skip is based on the NA's confidence, but the NA can be confidently wrong.

### Issue 4: No IMS signaling path probing

The fault localization prompt instructs the NA to check `measure_rtt` when packet loss is suspected, focused on RTPEngine and UPF. But for an IMS network partition, the critical RTT checks are between the IMS signaling components: P-CSCF ↔ I-CSCF and P-CSCF ↔ S-CSCF. The prompt doesn't explicitly instruct the NA to check these paths when IMS signaling metrics (SIP errors, Diameter response times) show failures.

### Fixes Needed

1. **RTPEngine cumulative metrics**: Either exclude `average_packet_loss` and `packet_loss_standard_deviation` from the anomaly model (since they're lifetime averages that carry stale data from previous runs), or replace them with delta-based features that only detect recent changes.

2. **IMS signaling path probing**: Add to the NA prompt: when IMS signaling metrics show failures (SIP error ratio > 0, Diameter response times anomalous, LIR/UAR timeouts), ALWAYS run `measure_rtt` between IMS signaling components (P-CSCF ↔ I-CSCF, P-CSCF ↔ S-CSCF, I-CSCF/S-CSCF ↔ HSS) to check for network partitions before attributing the issue to any individual component.

3. **Investigator skip refinement**: Consider not skipping when the NA's suspect list doesn't include any component that appears in the anomaly screener's flagged metrics for the affected layer — i.e., the NA is attributing the RED layer to a component that isn't even the top anomaly.

### Actions to take as follow-up

1. Re-run the failure scenaio against a clean baseline (freshly instantiated stack) to compare the impact from cumulative metrics and how they affect the anomaly detector. If positive, remove such metrics from the feature set and re-train the model.

2. Improve the prompt, and likely causal chains in the ontology and add a specific section on IMS signaling.

3. Re-think the agent orchestration and methodology. As it stands, NetworkAnalyst always sounds very confident and therefore, investigator agent is always skipped! Instead, maybe it's better to have the NA come up with the most likely hypothese and have the investigator prove or disprove those hypothese. Also, related to sub-agents, the match finder is not that useful either. It might be better to create a RAG-based agent that looks at all the episode files that we have collected so far and perform semantic search and add to context. It then must still be investigated by the investigator agent.