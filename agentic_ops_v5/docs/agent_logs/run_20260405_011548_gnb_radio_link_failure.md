# Episode Report: gNB Radio Link Failure

**Agent:** v5  
**Episode ID:** ep_20260405_011356_gnb_radio_link_failure  
**Date:** 2026-04-05T01:13:57.074670+00:00  
**Duration:** 110.3s  

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
| pcscf | httpclient:connfail | 522.0 | 523.0 | 1.0 |
| pcscf | core:rcv_requests_options | 521.0 | 522.0 | 1.0 |

## Network Analysis (Phase 1)

**Summary:** The network is down due to a complete RAN failure, and the core's data plane is also impaired.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | All infrastructure components (mongo, mysql, dns) are running and connected. |
| **ran** | 🔴 RED | The gNB is completely disconnected from the 5G core, preventing any UE from attaching. |
| **core** | 🟡 YELLOW | Core components are running, but the UPF is dropping outbound packets, indicating a data plane failure. Control plane state is stale. |
| **ims** | 🟢 GREEN | IMS components are running with registered users, but this is stale state due to the RAN failure. No new calls are possible. |

**RAN evidence:**
- N2 (NGAP) link to AMF is INACTIVE per get_network_topology
- amf metric 'gnb' is 0 (expected 1) per compare_to_baseline
- amf metric 'ran_ue' is 0 (expected 2) per compare_to_baseline
- nr_gnb container is not reported as running in get_network_status

**CORE evidence:**
- UPF outbound traffic is 0.0 pps while inbound is 0.2 pps from get_dp_quality_gauges
- UPF total out packets (1243) is less than half of in packets (2690) from get_nf_metrics
- AMF and SMF report active sessions/UEs while RAN has 0 UEs, indicating stale state.

**Suspect components:**

- **nr_gnb** (high): The gNB is not connected to the AMF or UPF (N2/N3 links are INACTIVE). AMF metrics confirm gnb=0. This is the primary failure preventing UE access.
- **upf** (medium): The UPF is dropping outbound packets. `get_dp_quality_gauges` shows 0.2 pps in but 0.0 pps out over the last 30s. This is a critical data plane fault independent of the RAN issue.

**Investigation hint:** Start by investigating the `nr_gnb` container; it is likely down or misconfigured, as it has no connection to the core. Concurrently, examine the UPF's data plane, as it is black-holing outbound traffic, which will prevent any data flow even if the RAN is restored.

**Tools called:** get_vonr_components, get_network_topology, get_network_status, get_nf_metrics, get_dp_quality_gauges, check_stack_rules, compare_to_baseline


## Pattern Match (Phase 2)

**✅ Match:** N2 connectivity loss — RAN/gNB unreachable, radio access lost

- **Confidence:** very_high
- **Failure domain:** ran
- **Matched signatures:** 1
  - `ran_failure` (score: 1.0)
- **Baseline anomalies:** 2 metrics across 1 components


## Investigation Instruction (Phase 3)

> ESTABLISHED FACT: The ontology diagnosed N2 connectivity loss — RAN/gNB unreachable, radio access lost with very_high confidence.
>
> This means:
> *   The AMF is reporting the loss, not failing itself.
> *   The UPF's data plane issues (outbound packet drops) are likely a consequence of the gNB endpoint being gone, not an independent UPF fault.
> *   IMS symptoms are secondary to the RAN being unreachable.
>
> Your ONLY job: verify this diagnosis using the following specific tools. Do NOT investigate other layers as primary root causes.
>
> **VERIFY:**
> 1.  **`get_nf_metrics`**: Check `amf` for `ran_ue = 0` (expected 2) and `gnb = 0` (expected 1).
> 2.  **`measure_rtt`**: From the `amf` container to the gNB IP (`172.22.0.23`) to confirm 100% packet loss, indicating unreachability.
> 3.  **`read_container_logs`**: For the `amf` container, `grep 'NGAP'` to check for state change logs detailing when and why the association was lost.

## Ground Truth

**Failure domain:** data_plane  
**Protocol impact:** GTP-U  
**Affected components:** nr_gnb  
**Severity:** degraded

## Agent Diagnosis

**Model:** v5-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 102.0s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: The `nr_gnb` (gNodeB) container is completely unreachable from the 5G Core, causing a total radio access network (RAN) outage.
> - **timeline**:
>     1.  The `nr_gnb` container or its network path failed, resulting in it becoming unreachable at the IP layer.
>     2.  The SCTP transport link for the N2 interface between the AMF and gNB timed out and failed.
>     3.  The AMF correctly reported its connected gNB count as `0` and RAN UE count as `0`.
>     4.  The UPF, unable to reach the gNB's N3 interface endpoint, began dropping all outbound user plane traffic, leading to 0 pps outbound.
>     5.  All UEs attached to the gNB were disconnected, and the entire network went down.
> - **root_cause**: A transport-level failure has isolated the `nr_gnb` from the rest of the network. The investigation confirmed the initial analysis that the gNB was the primary suspect. The definitive proof is a `measure_rtt` test from the AMF to the gNB's IP (`172.22.0.23`) which showed `100% packet loss`. This is the foundational failure causing all other symptoms.
> - **affected_components**: `nr_gnb`, `amf`, `upf`
> - **recommendation**: The `nr_gnb` container has either crashed or is network-partitioned. Restart the `nr_gnb` container. If it fails to connect, verify host-level networking for the container.
> - **confidence**: high
> - **explanation**: The network is down due to a complete RAN failure. The investigation confirmed that the gNB is offline and unreachable at a basic network level. This was proven by a ping test from the AMF to the gNB's IP address, which had 100% packet loss. While other components like the UPF show errors (e.g., dropping all outbound packets), this is a symptom, not a cause; the UPF has nowhere to send the data because its connection to the gNB is gone. AMF logs confirm the connection was previously working, pointing to a sudden crash or network partition rather than a misconfiguration. The immediate priority is to restore the `nr_gnb` container and its network connectivity.

### Scoring Breakdown

**Overall score: 100%**

**Scorer assessment:** The agent provided an excellent and highly accurate diagnosis, correctly identifying the unreachable gNB as the root cause with strong evidence, appropriate severity, and justified confidence.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | Yes | The agent correctly identified that the 'nr_gnb' was completely unreachable due to a transport-level failure, evidenced by 100% packet loss. This directly matches the simulated 'gNB Radio Link Failure' where the gNB is unreachable. |
| Component overlap | 100% | The agent correctly identified 'nr_gnb' as the primary affected component. It also listed 'amf' and 'upf' as affected, which are correct cascading effects of the gNB being down, demonstrating good causal reasoning. |
| Severity correct | Yes | The agent accurately described the severity as a 'total radio access network (RAN) outage' and 'entire network went down', with the gNB being 'completely unreachable' and showing '100% packet loss'. This perfectly matches the simulated complete outage. |
| Fault type identified | Yes | The agent identified the fault type as a component being 'completely unreachable' and 'isolated' due to a 'transport-level failure', with '100% packet loss'. This aligns with the observable class of a component being down/unreachable. |
| Confidence calibrated | Yes | The agent stated 'high' confidence, which is appropriate given the accuracy, detail, and supporting evidence (ping test with 100% packet loss) provided in its diagnosis. |

**Ranking position:** #1 — The agent provided a single, clear root cause, which was correct.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 78,910 |
| Output tokens | 3,040 |
| Thinking tokens | 6,880 |
| **Total tokens** | **88,830** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| NetworkAnalystAgent | 32,857 | 9 | 4 |
| PatternMatcherAgent | 0 | 0 | 0 |
| InstructionGeneratorAgent | 6,362 | 0 | 1 |
| InvestigatorAgent | 42,173 | 3 | 4 |
| SynthesisAgent | 7,438 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 110.3s
