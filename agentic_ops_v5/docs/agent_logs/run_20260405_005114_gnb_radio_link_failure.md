# Episode Report: gNB Radio Link Failure

**Agent:** v5  
**Episode ID:** ep_20260405_004922_gnb_radio_link_failure  
**Date:** 2026-04-05T00:49:23.553907+00:00  
**Duration:** 109.7s  

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

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

### Metrics Changes

| Node | Metric | Baseline | Current | Delta |
|------|--------|----------|---------|-------|
| upf | fivegs_ep_n3_gtp_indatavolumeqosleveln3upf | 157144.0 | 157174.0 | 30.0 |
| upf | fivegs_ep_n3_gtp_indatapktn3upf | 2480.0 | 2481.0 | 1.0 |

## Network Analysis (Phase 1)

**Summary:** The network is down due to a failure in the Radio Access Network (RAN) layer; core and IMS layers are up but idle.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟡 YELLOW | Degraded: The Grafana monitoring container has exited. |
| **ran** | 🔴 RED | Failed: The gNB is not running, and no UEs are attached. |
| **core** | 🟡 YELLOW | Degraded: PDU sessions are established but no user plane traffic is flowing due to RAN failure. |
| **ims** | 🟡 YELLOW | Degraded: UEs are registered, but no calls are possible due to RAN failure. |

**INFRASTRUCTURE evidence:**
- Datasource: Grafana → Prometheus [INACTIVE — Grafana is exited] from get_network_topology

**RAN evidence:**
- gnb=0.0 from get_nf_metrics (expected: 1.0)
- ran_ue=0.0 from get_nf_metrics (expected: 2.0)
- N2 (NGAP): [RAN] → AMF [INACTIVE — [RAN] not connected] from get_network_topology
- The 'nr_gnb' container is not in the list of running containers from get_network_status.

**CORE evidence:**
- upf in/out throughput = 0.0 KB/s with 4 active sessions from get_dp_quality_gauges

**IMS evidence:**
- rtpengine active sessions = 0 from get_dp_quality_gauges, despite 2 registered UEs
- Stack rule triggered: 'If gNB is down (ran_ue=0, gnb=0), ALL IMS symptoms are secondary effects.'

**Suspect components:**

- **nr_gnb** (high): Not listed as a running container in get_network_status. AMF metrics show gnb=0 and ran_ue=0. get_network_topology shows N2 and Air Interface links are INACTIVE.
- **grafana** (low): get_network_topology reports 'Grafana is exited' and its datasource link to Prometheus is INACTIVE.

**Investigation hint:** The RAN is down. The nr_gnb container is not running, preventing any UE from attaching to the network. Investigate the nr_gnb container logs and state to determine why it failed to start or exited.

**Tools called:** get_network_topology, get_network_status, get_nf_metrics, get_dp_quality_gauges, check_stack_rules, compare_to_baseline


## Pattern Match (Phase 2)

**✅ Match:** N2 connectivity loss — RAN/gNB unreachable, radio access lost

- **Confidence:** very_high
- **Failure domain:** ran
- **Matched signatures:** 1
  - `ran_failure` (score: 1.0)
- **Baseline anomalies:** 2 metrics across 1 components


## Investigation Instruction (Phase 3)

> ESTABLISHED FACT: The ontology diagnosed "N2 connectivity loss — RAN/gNB unreachable, radio access lost" with very_high confidence. Stack rules: AMF, UPF, and IMS symptoms are secondary effects of the RAN failure; do NOT investigate these layers as primary causes.
>
> Your ONLY job: verify this diagnosis by focusing on the RAN layer.
>
> 1.  **Investigate the `nr_gnb` container:** The Network Analysis indicates the `nr_gnb` container is not running. Use `get_network_status` to re-confirm its state. Then, use `read_container_logs` for `nr_gnb` to understand why it failed to start or exited. This is the most likely root cause.
> 2.  **Confirm N2 unreachability:** Use `measure_rtt` from the `amf` container to the gNB's IP address (`172.22.0.23`) to confirm 100% packet loss.
> 3.  **Validate AMF metrics:** Use `get_nf_metrics` to verify that `ran_ue` and `gnb` counters at the `amf` are both 0.
> 4.  **Check AMF logs:** Use `read_container_logs` for the `amf` container, specifically grepping for 'NGAP', to find details on when and why the association was lost.
>
> Do NOT investigate other layers (Core, IMS, or Grafana) as their issues are a direct consequence of the RAN failure.

## Ground Truth

**Failure domain:** data_plane  
**Protocol impact:** GTP-U  
**Affected components:** nr_gnb  
**Severity:** degraded

## Agent Diagnosis

**Model:** v5-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 101.3s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: The gNB (Radio Access Network) container (`nr_gnb`) has crashed and is not running, causing a complete loss of radio access and a full network outage.
>   - **timeline**:
>     1.  The `nr_gnb` container, which provides the 5G radio network, terminated unexpectedly.
>     2.  The N2 transport connection (SCTP) between the gNB and the AMF was severed.
>     3.  From the AMF's perspective, the gNB became unreachable, confirmed by 100% packet loss.
>     4.  The AMF's metrics updated to `gnb=0` and `ran_ue=0`, reflecting the loss of the entire RAN.
>     5.  All connected UEs were dropped, and no new connections, sessions, or calls are possible, rendering the Core and IMS networks idle.
>   - **root_cause**: The `nr_gnb` container process has terminated. The investigation confirmed the initial high-confidence suspicion from the Network Analysis phase. The failure of this single component has broken the link between users and the network.
>   - **affected_components**: `nr_gnb` (failed), `amf`, `smf`, `upf`, `pcscf` (all idle due to RAN failure).
>   - **recommendation**: Restart the `nr_gnb` container. After it has been restarted, immediately check its logs (`read_container_logs` for `nr_gnb`) to diagnose why it failed and prevent a recurrence.
>   - **confidence**: high
>   - **explanation**: The investigation confirmed the initial diagnosis of "N2 connectivity loss" by finding the most direct cause: the gNB itself is not running. Evidence from `get_network_status` showed the `nr_gnb` container was missing from the list of running processes. This was corroborated by a transport-layer test (`measure_rtt`) from the AMF to the gNB's IP, which showed 100% packet loss. Core network metrics (`get_nf_metrics`) also confirmed the AMF sees zero connected gNBs (`gnb=0`). The abrupt failure of the `nr_gnb` container is the definitive root cause, and all issues observed in the Core and IMS layers are secondary consequences.

### Scoring Breakdown

**Overall score: 100%**

**Scorer assessment:** The agent provided an outstanding diagnosis, accurately identifying the root cause, affected components, severity, and fault type with high confidence, fully aligning with the simulated failure.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | Yes | The agent correctly identified that the 'nr_gnb' container process terminated, leading to the gNB being unreachable. This is semantically equivalent to a radio link failure or the gNB being down/unresponsive from a network perspective, and aligns with the simulated failure mode. |
| Component overlap | 100% | The agent correctly identified 'nr_gnb' as the primary failed component. It also appropriately listed downstream components (AMF, SMF, UPF, P-CSCF) as affected due to the gNB failure, which demonstrates good causal reasoning. |
| Severity correct | Yes | The agent's assessment of 'complete loss of radio access and a full network outage' perfectly matches the simulated impact where all UEs lose registration, PDU sessions drop, and IMS SIP unregisters. |
| Fault type identified | Yes | The agent clearly identified the fault type as a component being 'crashed and not running', 'unreachable', and experiencing '100% packet loss', which falls under the 'Component unreachable' observable class of failure. |
| Confidence calibrated | Yes | The agent stated 'high' confidence, which is well-calibrated given the accuracy and detail of its diagnosis, supported by multiple pieces of evidence (container status, packet loss, AMF metrics). |

**Ranking position:** #1 — The agent provided a single, clear root cause as its primary diagnosis.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 81,445 |
| Output tokens | 2,690 |
| Thinking tokens | 7,064 |
| **Total tokens** | **91,199** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| NetworkAnalystAgent | 21,962 | 7 | 3 |
| PatternMatcherAgent | 0 | 0 | 0 |
| InstructionGeneratorAgent | 6,125 | 0 | 1 |
| InvestigatorAgent | 55,454 | 5 | 6 |
| SynthesisAgent | 7,658 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 109.7s
