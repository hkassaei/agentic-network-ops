# Episode Report: gNB Radio Link Failure

**Agent:** v6  
**Episode ID:** ep_20260420_040102_gnb_radio_link_failure  
**Date:** 2026-04-20T04:01:03.574604+00:00  
**Duration:** 259.5s  

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
| pcscf | core:rcv_requests_options | 11.0 | 36.0 | 25.0 |
| pcscf | httpclient:connfail | 12.0 | 37.0 | 25.0 |
| scscf | ims_usrloc_scscf:contact_collisions | 0.0 | 1.0 | 1.0 |
| scscf | ims_usrloc_scscf:subscription_collisions | 0.0 | 1.0 | 1.0 |
| scscf | ims_usrloc_scscf:impu_collisions | 0.0 | 1.0 | 1.0 |

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

```
**Summary:** The entire RAN appears to be down or disconnected from the core, causing a total loss of user plane and control plane connectivity for all UEs.

**Layer status:**
  - ran: red — The RAN layer is the primary suspect. All connections from the RAN to the core network are down, and AMF metrics confirm zero connected gNBs and UEs.
  - core: yellow — The core network components are all running, but are showing the downstream effects of the RAN failure. UE sessions and bearers have been lost, and there is no user plane traffic flowing through the UPF. The AMF correctly reports the loss of RAN connectivity.
  - ims: yellow — The IMS system is operational but is unable to serve UEs because they cannot attach to the network. There are no active IMS dialogs.
  - infrastructure: green — T
```

## Pattern Match (Phase 2)

```
**Correlation engine produced 5 ranked composite hypotheses from 4 fired events:**

### H1: gNB/N2 failure — RAN access lost for both gNB and UEs
  - primary_nf: amf
  - explanatory_fit: 0.50 (2/4 events)
  - testability: 2 (2 disambiguating metrics)
  - supporting events: `core.amf.gnb_association_drop`, `core.amf.ran_ue_sudden_drop`
  - probes to discriminate:
      - Check core.amf.ran_ue → Whether N2 is dead (both zero) vs. AMF-side attach issue (gnb>0, ran_ue=0)
      - Check core.amf.gnb →
```

## Investigation Instruction (Phase 3)

> {
>   "plans": [
>     {
>       "hypothesis_id": "h1",
>       "hypothesis_statement": "The gNB has failed or is completely partitioned from the core network. This has resulted in the loss of both the N2 control plane interface to the AMF and the N3 user plane interface to the UPF, leading to a full network outage for all UEs.",
>       "primary_suspect_nf": "nr_gnb",
>       "probes": [
>         {
>           "tool": "get_network_status",
>           "args_hint": "container: nr_gnb",
>           "expected_if_hypothesis_holds": "The `nr_gnb` container is 'exited' or 'stopped'.",
>           "falsifying_observation": "The `nr_gnb` container is 'running' and healthy."
>         },
>         {
>           "tool": "measure_rtt",
>           "args_hint": "from: amf, to_ip: <gNB N2 IP address>",
>           "expected_if_hypothesis_holds": "High RTT or 100% packet loss when pinging gNB N2 IP from AMF, indicating a network partition.",
>           "falsifying_observation": "Clean RTT (< 5ms) to gNB N2 IP from AMF, indicating the network path is open."
>         },
>         {
>           "tool": "read_container_logs",
>           "args_hint": "container: nr_gnb, grep: \"N2|N3|error|fail|shutdown\"",
>           "expected_if_hypothesis_holds": "gNB logs show N2/N3 interface errors, connectivity issues, or critical failures/shutdown messages.",
>           "falsifying_observation": "gNB logs are clean, showing no N2/N3 interface errors or critical failures."
>         }
>       ],
>       "notes": "Focus on direct gNB liveness and its network connectivity to the core (AMF/UPF)."
>     },
>     {
>       "hypothesis_id": "h2",
>       "hypothesis_statement": "The AMF's N2 interface has failed, preventing it from communicating with the gNB. Although the AMF container is running, this specific interface failure makes it impossible to maintain gNB associations or process UE registrations.",
>       "primary_suspect_nf": "amf",
>       "probes": [
>         {
>           "tool": "read_container_logs",
>           "args_hint": "container: amf, grep: \"SCTP|N2|error|failed to establish gNB association\"",
>           "expected_if_hypothesis_holds": "AMF logs show errors related to SCTP association setup or N2 interface communication failures.",
>           "falsifying_observation": "AMF logs are clean regarding SCTP/N2 interface errors."
>         },
>         {
>           "tool": "check_process_listeners",
>           "args_hint": "container: amf",
>           "expected_if_hypothesis_holds": "The AMF process is not listening on its N2 port (e.g., 38412/SCTP) or the listener is in a faulty state.",
>           "falsifying_observation": "The AMF process is actively listening on its N2 port."
>         },
>         {
>           "tool": "query_prometheus",
>           "args_hint": "query: \"amf_n2_connection_status{job='amf'}\" (or similar AMF N2 metric)",
>           "expected_if_hypothesis_holds": "Prometheus metric indicates AMF's N2 connection state is 'down' or 'unhealthy'.",
>           "falsifying_observation": "Prometheus metric indicates AMF's N2 connection state is 'up' or 'healthy'."
>         }
>       ],
>       "notes": "Focus on the AMF's internal state and its external visibility concerning the N2 interface."
>     },
>     {
>       "hypothesis_id": "h3",
>       "hypothesis_statement": "A sudden, widespread UE detachment event triggered a cascading failure. While this explains the drop in UE-related metrics and sessions, it does not fully account for the gNB itself becoming disconnected from the AMF.",
>       "primary_suspect_nf": "amf",
>       "probes": [
>         {
>           "tool": "query_prometheus",
>           "args_hint": "query: \"amf_gnb_associations{job='amf'}\"",
>           "expected_if_hypothesis_holds": "The AMF reports active gNB associations (`amf_gnb_associations > 0`), meaning the gNB is still connected to the AMF.",
>           "falsifying_observation": "The AMF reports zero active gNB associations (`amf_gnb_associations == 0`), indicating the gNB is disconnected, which contradicts the hypothesis premise."
>         },
>         {
>           "tool": "read_container_logs",
>           "args_hint": "container: amf, grep: \"Deregistration Request|UE Context Release Command\"",
>           "expected_if_hypothesis_holds": "AMF logs show a high volume of UE-initiated Deregistration Requests or UE Context Release Commands, indicating a widespread UE detachment.",
>           "falsifying_observation": "AMF logs show few to no UE Deregistration or Context Release requests, suggesting the detach was not UE-initiated."
>         },
>         {
>           "tool": "read_container_logs",
>           "args_hint": "container: upf, grep: \"PDU session release|UPF session termination\"",
>           "expected_if_hypothesis_holds": "UPF logs show PDU session releases or terminations, possibly initiated by the SMF due to UE detach.",
>           "falsifying_observation": "UPF logs do not show PDU session releases/terminations, or show them initiated by N3 interface loss, not SMF."
>         }
>       ],
>       "notes": "Tests if the gNB is actually still connected to the AMF and if UE detach events are evident in logs."
>     }
>   ]
> }

## Investigation (Phase 4)

> [
>   {
>     "hypothesis_id": "h1",
>     "hypothesis_statement": "The gNB has failed or is completely partitioned from the core network. This has resulted in the loss of both the N2 control plane interface to the AMF and the N3 user plane interface to the UPF, leading to a full network outage for all UEs.",
>     "verdict": "NOT_DISPROVEN",
>     "reasoning": "All probes executed were consistent with the hypothesis. The 'nr_gnb' container is not running and is unreachable from the core network (AMF), confirming it has either failed or is partitioned. The inability to find the container or its logs provides strong evidence for this hypothesis.",
>     "probes_executed": [
>       {
>         "probe_description": "Check the operational status of the gNB container.",
>         "tool_call": "get_network_status()",
>         "observation": "[EVIDENCE: get_network_status() -> \"'running': ['mongo', 'nrf', ... 'rtpengine'], 'down_or_absent': []\"]",
>         "compared_to_expected": "CONSISTENT",
>         "commentary": "The output confirms the 'nr_gnb' container is not running, as it is absent from the list of all running containers. This aligns with the expectation that the gNB has failed."
>       },
>       {
>         "probe_description": "Check gNB logs for N2/N3 interface errors or failures.",
>         "tool_call": "read_container_logs(\"nr_gnb\", \"N2|N3|error|fail|shutdown\")",
>         "observation": "[EVIDENCE: read_container_logs(\"nr_gnb\", \"N2|N3|error|fail|shutdown\") -> \"Unknown container 'nr_gnb'.\"]",
>         "compared_to_expected": "CONSISTENT",
>         "commentary": "The inability to read logs because the container does not exist is the strongest possible indicator of a failed gNB, which is consistent with the hypothesis."
>       },
>       {
>         "probe_description": "Measure RTT from AMF to the gNB's N2 IP address to check for a network partition.",
>         "tool_call": "measure_rtt(\"amf\", \"172.22.0.23\")",
>         "observation": "[EVIDENCE: measure_rtt(\"amf\", \"172.22.0.23\") -> \"100% packet loss\"]",
>         "compared_to_expected": "CONSISTENT",
>         "commentary": "The 100% packet loss from the AMF to the gNB's expected IP address confirms a complete network partition or that the gNB is down, as stated in the hypothesis. The gNB IP was found via read_env_config."
>       }
>     ],
>     "alternative_suspects": []
>   },
>   {
>     "hypothesis_id": "h2",
>     "hypothesis_statement": "The AMF's N2 interface has failed, preventing it from communicating with the gNB. Although the AMF container is running, this specific interface failure makes it impossible to maintain gNB associations or process UE registrations.",
>     "verdict": "DISPROVEN",
>     "reasoning": "The AMF's logs show no errors related to its N2 interface or SCTP, which directly contradicts the hypothesis that the interface has failed internally. While no gNBs are connected, the AMF is not reporting any faults that would prevent it from accepting a connection. This suggests the fault lies with the gNB or the network path to it.",
>     "probes_executed": [
>       {
>         "probe_description": "AMF logs show errors related to SCTP association setup or N2 interface communication failures.",
>         "tool_call": "read_container_logs(\"amf\", \"SCTP|N2|error|failed to establish gNB association\")",
>         "observation": "[EVIDENCE: read_container_logs(\"amf\", \"SCTP|N2|error|failed to establish gNB association\") -> \"(no log output)\"]",
>         "compared_to_expected": "CONTRADICTS",
>         "commentary": "The complete absence of any SCTP or N2-related errors in the AMF's logs is the strongest piece of evidence. If the AMF's N2 interface had failed internally, it would have generated logs to that effect. Their absence indicates the AMF believes its interface is healthy."
>       },
>       {
>         "probe_description": "The AMF process is not listening on its N2 port (e.g., 38412/SCTP) or the listener is in a faulty state.",
>         "tool_call": "check_process_listeners(\"amf\")",
>         "observation": "[EVIDENCE: check_process_listeners(\"amf\") -> \"Netid State  Recv-Q Send-Q Local Address:Port  Peer Address:PortProcess                              \\nudp   UNCONN 0      0         127.0.0.11:32956      0.0.0.0:*                                        \\ntcp   LISTEN 0      5        172.22.0.10:7777       0.0.0.0:*    users:((\\\"open5gs-amfd\\\",pid=8,fd=11))\\ntcp   LISTEN 0      4096      127.0.0.11:33059      0.0.0.0:*                                        \\ntcp   LISTEN 0      4096     172.22.0.10:9091       0.0.0.0:*    users:((\\\"open5gs-amfd\\\",pid=8,fd=10))\"]",
>         "compared_to_expected": "AMBIGUOUS",
>         "commentary": "The tool output does not show a listener on the standard N2 SCTP port (38412). While this could be seen as consistent with the hypothesis, it's more likely a limitation of the tool (not showing SCTP listeners) or that the interface is simply idle. Given the lack of errors in the logs, this observation is not conclusive."
>       },
>       {
>         "probe_description": "Prometheus metric indicates AMF's N2 connection state is 'down' or 'unhealthy'.",
>         "tool_call": "query_prometheus(\"amf_ngap_associated_gnb_total\")",
>         "observation": "[EVIDENCE: query_prometheus(\"amf_ngap_associated_gnb_total\") -> \"No results for query 'amf_ngap_associated_gnb_total'. The metric may not exist or have no data.\"]",
>         "compared_to_expected": "CONSISTENT",
>         "commentary": "The fact that there is no data for associated gNBs is consistent with the symptom that no gNBs are connected. However, this confirms the network state, not the root cause. It doesn't prove the failure is within the AMF's N2 interface."
>       }
>     ],
>     "alternative_suspects": [
>       "gNB"
>     ]
>   },
>   {
>     "hypothesis_id": "h3",
>     "hypothesis_statement": "A sudden, widespread UE detachment event triggered a cascading failure. While this explains the drop in UE-related metrics and sessions, it does not fully account for the gNB itself becoming disconnected from the AMF.",
>     "verdict": "DISPROVEN",
>     "reasoning": "The core assertion of the hypothesis is a 'widespread UE detachment event'. Probes of the AMF and UPF logs show no evidence of such an event. Specifically, there are no 'Deregistration Request' or 'UE Context Release Command' logs in the AMF, and no 'PDU session release' logs in the UPF. This directly contradicts the hypothesized cause of the failure.",
>     "probes_executed": [
>       {
>         "probe_description": "Check if the gNB is still connected to the AMF by querying for gNB associations.",
>         "tool_call": "query_prometheus(query='amf_gnb_associations{job=\"amf\"}')",
>         "observation": "[EVIDENCE: query_prometheus(\"query='amf_gnb_associations{job=\\\"amf\\\"'\",) -> \"No results for query 'amf_gnb_associations{job=\\\"amf\\\"}'. The metric may not exist or have no data.\"]",
>         "compared_to_expected": "AMBIGUOUS",
>         "commentary": "The lack of data for this metric implies zero gNB associations, confirming the gNB is disconnected. The hypothesis acknowledges this disconnection, so this observation doesn't directly falsify it, but it also doesn't support the 'UE detachment' cause."
>       },
>       {
>         "probe_description": "Check AMF logs for a high volume of UE-initiated Deregistration Requests or UE Context Release Commands.",
>         "tool_call": "read_container_logs(container='amf', grep='Deregistration Request|UE Context Release Command')",
>         "observation": "[EVIDENCE: read_container_logs(\"container='amf', grep='Deregistration Request|UE Context Release Command'\",) -> \"(no log output)\"]",
>         "compared_to_expected": "CONTRADICTS",
>         "commentary": "This is the primary falsifying observation. A widespread UE detachment would have generated a large number of these log entries. Their complete absence indicates the failure was not initiated by the UEs."
>       },
>       {
>         "probe_description": "Check UPF logs for PDU session releases or terminations initiated by the SMF.",
>         "tool_call": "read_container_logs(container='upf', grep='PDU session release|UPF session termination')",
>         "observation": "[EVIDENCE: read_container_logs(\"container='upf', grep='PDU session release|UPF session termination'\",) -> \"(no log output)\"]",
>         "compared_to_expected": "CONTRADICTS",
>         "commentary": "This corroborates the finding from the AMF logs. If UEs were detaching, the SMF would command the UPF to release PDU sessions. The absence of these logs suggests the sessions disappeared for another reason, such as a loss of the N3 interface from the gNB."
>       }
>     ],
>     "alternative_suspects": [
>       "gNB"
>     ]
>   }
> ]

## Evidence Validation (Phase 5)

{
  "overall_verdict": "clean",
  "overall_confidence": "high",
  "per_agent": [
    {
      "agent_name": "InvestigatorAgent_h1",
      "tool_calls_made": 4,
      "citations_found": 3,
      "citations_matched": 3,
      "citations_unmatched": 0,
      "verdict": "clean",
      "confidence": "high",
      "notes": []
    },
    {
      "agent_name": "InvestigatorAgent_h2",
      "tool_calls_made": 3,
      "citations_found": 3,
      "citations_matched": 3,
      "citations_unmatched": 0,
      "verdict": "clean",
      "confidence": "high",
      "notes": []
    },
    {
      "agent_name": "InvestigatorAgent_h3",
      "tool_calls_made": 3,
      "citations_found": 3,
      "citations_matched": 3,
      "citations_unmatched": 0,
      "verdict": "clean",
      "confidence": "high",
      "notes": []
    }
  ],
  "summary": "Evidence validation across 3 sub-Investigator(s): overall verdict=clean, confidence=high.\n  - InvestigatorAgent_h1: 4 tool calls, 3/3 citations verified (clean, high)\n  - InvestigatorAgent_h2: 3 tool calls, 3/3 citations verified (clean, high)\n  - InvestigatorAgent_h3: 3 tool calls, 3/3 citations verified (clean, high)"
}

## Ground Truth

**Failure domain:** data_plane  
**Protocol impact:** GTP-U  
**Affected components:** nr_gnb  
**Severity:** degraded

## Agent Diagnosis

**Model:** v6-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 128.4s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: The gNB (RAN) has failed or become completely disconnected from the core network, causing a total outage for all UEs.
> - **timeline**:
>     1. The gNB's control plane association (N2 interface) with the AMF dropped (`core.amf.gnb_association_drop`).
>     2. As a direct result, all UEs connected via the gNB were lost from the core network's perspective (`core.amf.ran_ue_full_loss`, `core.amf.ran_ue_sudden_drop`).
>     3. Subsequently, the SMF tore down the PDU sessions associated with the now-disconnected UEs (`core.smf.sessions_per_ue_drop`).
> - **root_cause**: The gNB has failed or is completely partitioned from the core network. This has resulted in the loss of both the N2 control plane interface to the AMF and the N3 user plane interface to the UPF, leading to a full network outage for all UEs. (primary_suspect_nf: gNB)
> - **affected_components**:
>     - `gNB`: Root Cause
>     - `amf`: Secondary
>     - `smf`: Secondary
>     - `upf`: Secondary
>     - `ims`: Symptomatic
> - **recommendation**: The operator should verify the operational state of the gNB hardware and software. Investigation should focus on why the gNB container (`nr_gnb`) is down and why it is unreachable from the core network.
> - **confidence**: high
> - **explanation**: The investigation confirmed with high confidence that the root cause is a failure of the gNB. The surviving hypothesis (`h1`) stated the gNB failed or was partitioned, which was validated by probes showing the `nr_gnb` container is not running and is completely unreachable from the AMF. Alternative hypotheses were disproven: an AMF-side N2 interface failure (`h2`) was ruled out by clean AMF logs with no SCTP errors, and a mass UE detachment event (`h3`) was ruled out by the lack of any de-registration logs in the core. All evidence points conclusively to the gNB as the source of the outage.

### Scoring Breakdown

**Overall score: 100%**

**Scorer assessment:** The agent provided an excellent and highly accurate diagnosis, correctly identifying the gNB failure as the root cause, its impact, and its location within the network layers, with appropriate confidence.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | Yes | The agent correctly identified 'gNB failure' or 'gNB completely partitioned/disconnected' as the root cause, which directly matches the simulated 'gNB Radio Link Failure' and 'nr_gnb component completely unreachable'. The agent also explicitly states 'primary_suspect_nf: gNB' and ranks this as the top hypothesis. |
| Component overlap | 100% | The agent correctly identified 'gNB' as the root cause component. It also correctly listed downstream affected components (AMF, SMF, UPF, IMS) which is appropriate. |
| Severity correct | Yes | The simulated failure resulted in a complete outage ('All UEs lose 5G registration, PDU sessions drop'). The agent correctly described this as a 'total outage for all UEs' and a 'full network outage'. |
| Fault type identified | Yes | The agent identified the gNB as 'failed or completely partitioned/disconnected' and 'unreachable from the core network', which aligns with the simulated 'component completely unreachable (down/not responding)' fault type. |
| Layer accuracy | Yes | The ground truth states 'nr_gnb' belongs to the 'ran' layer. The agent correctly marked the 'ran' layer as 'red' and the 'primary suspect' due to the gNB failure. |
| Confidence calibrated | Yes | The agent stated 'high' confidence, which is appropriate given the accuracy and completeness of its diagnosis, supported by evidence (probes, ruling out alternatives). |

**Ranking position:** #1 — The correct root cause (gNB failure/partition) was listed as the first and highest-ranked hypothesis (h1).


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 89,520 |
| Output tokens | 5,590 |
| Thinking tokens | 13,945 |
| **Total tokens** | **109,055** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| EventAggregator | 0 | 0 | 0 |
| CorrelationAnalyzer | 0 | 0 | 0 |
| NetworkAnalystAgent | 28,786 | 3 | 4 |
| InstructionGeneratorAgent | 8,632 | 0 | 1 |
| InvestigatorAgent_h1 | 31,388 | 4 | 5 |
| InvestigatorAgent_h2 | 11,375 | 3 | 2 |
| InvestigatorAgent_h3 | 21,783 | 3 | 4 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 7,091 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 259.5s
