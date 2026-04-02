# Episode Report: gNB Radio Link Failure

**Agent:** v5  
**Episode ID:** ep_20260402_003735_gnb_radio_link_failure  
**Date:** 2026-04-02T00:37:35.798886+00:00  
**Duration:** 98.0s  

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

## Ground Truth

**Failure domain:** data_plane  
**Protocol impact:** GTP-U  
**Affected components:** nr_gnb  
**Severity:** degraded

## Agent Diagnosis

**Model:** v5-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 89.1s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: The Radio Access Network (RAN), specifically the gNodeB (gNB), is unreachable from the 5G core, resulting in a complete loss of radio access for all UEs.
> - **timeline**:
>     1.  The transport layer link between the AMF and the gNB at IP `172.22.0.23` failed.
>     2.  The AMF lost its N2 (NGAP/SCTP) connection to the gNB, causing its `gnb` metric to drop to 0.
>     3.  Without a path to the core, all UEs disconnected, causing the AMF's `ran_ue` metric to drop to 0.
>     4.  Consequently, PDU sessions were lost, and UEs were unable to register with the IMS, leading to IMS registration failures and the expiration of existing contacts.
> - **root_cause**: A definitive transport layer failure has isolated the gNB from the AMF. The investigator confirmed the `very_high` confidence diagnosis from the pattern matcher by proving the gNB is unreachable at the IP layer.
>     - **[EVIDENCE: measure_rtt(container = "amf", target_ip = "172.22.0.23") -> "100% packet loss"]**
>     - The impact of this transport failure is visible in the AMF's key metrics, which show zero connected RAN nodes or UEs.
>     - **[EVIDENCE: get_nf_metrics() -> "gnb = 0.0", "ran_ue = 0.0"]**
> - **affected_components**:
>     - **Primary**: gNB (unreachable), AMF (cannot connect to gNB)
>     - **Secondary**: All UEs (no access), SMF/UPF (stale sessions, no traffic), entire IMS Stack (no registered users)
> - **recommendation**: **Do not investigate the 5G core or IMS components.** The issue is external to the core network containers. The NOC must investigate the network path to the RAN. Check for:
>     1.  The operational status of the gNB hardware/software at IP `172.22.0.23`.
>     2.  Physical connectivity (e.g., fiber, cabling) between the core and RAN sites.
>     3.  Intermediate network device health (switches, routers) and firewall rules that may be blocking SCTP or ICMP traffic between the AMF and the gNB.
> - **confidence**: high
> - **explanation**: The investigation confirmed the initial hypothesis of a RAN failure. Evidence shows the AMF cannot reach the gNB at a basic IP level, indicated by 100% packet loss. This transport failure is the root cause of the outage. As a result, the AMF correctly reports zero connected gNBs and UEs. All observed issues in the IMS system, such as zero registered contacts and high connection failures at the P-CSCF, are symptoms of the fact that no UEs can connect to the network in the first place. The core network and IMS are functioning but have no users to serve.

### Scoring Breakdown

**Overall score: 100%**

**Scorer assessment:** The agent provided an excellent and highly accurate diagnosis, correctly identifying the gNB unreachability due to a transport layer failure as the root cause, supported by strong evidence, and with appropriate confidence.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | Yes | The agent correctly identified the gNB being unreachable due to a transport layer failure as the root cause, which directly corresponds to the simulated 'gNB Radio Link Failure' and 'Component completely unreachable'. The diagnosis is semantically equivalent and well-supported by evidence. |
| Component overlap | 100% | The agent explicitly named 'gNB (unreachable)' as the primary affected component, which is the exact component targeted by the simulation. It also correctly identified the AMF as directly affected and other components as secondary/cascading. |
| Severity correct | Yes | The agent's diagnosis of 'complete loss of radio access for all UEs' and '100% packet loss' to the gNB accurately reflects the 'Component completely unreachable' and 'All UEs lose 5G registration' severity of the simulated failure. |
| Fault type identified | Yes | The agent identified the fault type as 'unreachable' and 'transport layer link failed' with '100% packet loss', which correctly describes the observable 'Component completely unreachable' fault type. |
| Confidence calibrated | Yes | The agent stated 'high' confidence, which is well-calibrated given the accuracy of its diagnosis and the strong, direct evidence provided (100% packet loss to gNB IP, AMF metrics showing zero gNBs/UEs). |

**Ranking position:** #1 — The agent provided a single, clear root cause, which was correct.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 59,407 |
| Output tokens | 3,691 |
| Thinking tokens | 6,232 |
| **Total tokens** | **69,330** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| TriageAgent | 13,670 | 3 | 4 |
| PatternMatcherAgent | 0 | 0 | 0 |
| InstructionGeneratorAgent | 6,127 | 0 | 1 |
| InvestigatorAgent | 41,487 | 3 | 4 |
| SynthesisAgent | 8,046 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 98.0s
