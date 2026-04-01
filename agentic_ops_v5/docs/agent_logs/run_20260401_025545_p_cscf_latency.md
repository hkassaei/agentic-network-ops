# Episode Report: P-CSCF Latency

**Agent:** v5  
**Episode ID:** ep_20260401_025407_p_cscf_latency  
**Date:** 2026-04-01T02:54:08.095328+00:00  
**Duration:** 96.8s  

---

## Scenario

**Category:** network  
**Blast radius:** single_nf  
**Description:** Inject 500ms latency on the P-CSCF (SIP edge proxy). SIP T1 timer is 500ms, so REGISTER transactions will start timing out. Tests IMS resilience to WAN-like latency on the signaling path.

## Faults Injected

- **network_latency** on `pcscf` — {'delay_ms': 500, 'jitter_ms': 50}

## Baseline (Pre-Fault)

Stack phase before injection: **ready**
All containers running at baseline.

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

## Ground Truth

**Failure domain:** ims_signaling  
**Protocol impact:** SIP  
**Affected components:** pcscf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v5-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 86.7s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: Extreme network latency originating from the `pcscf` container is causing application-level timeouts, preventing UE registrations and session establishment across the entire stack.
> - **timeline**:
>     1.  A severe transport layer issue introduces catastrophic latency (500-1000ms RTT) on egress traffic from the `pcscf` container.
>     2.  `pcscf`'s internal health checks (HTTP OPTIONS requests) to other IMS components like `icscf` begin to time out. This is reflected in the `pcscf` metric `httpclient:connfail`, which increments for each failed attempt.
>     3.  UE registration requests arriving at the `pcscf` cannot be forwarded to the `icscf`/`scscf` due to the same timeouts, preventing any IMS registrations from completing.
>     4.  Without successful UE registration, PDU session establishment requests are never initiated towards the 5G Core.
>     5.  As a result, all session-related metrics in the AMF, SMF, UPF, and PCF remain at zero, triggering the baseline alarms.
> - **root_cause**: The definitive first cause is a transport layer failure specific to the `pcscf` container. The investigation confirmed this with direct RTT measurements showing latency over 500x the norm. This network failure is the root cause of the cascading application failures and the resulting lack of user sessions.
> - **affected_components**:
>     - **Root Cause**: `pcscf` (container network interface)
>     - **Downstream Impact**: `icscf`, `scscf`, `amf`, `smf`, `upf`, `pcf`
> - **recommendation**: Investigate and resolve the source of the extreme network latency on the `pcscf` container. Check for misconfigured traffic control policies (e.g., `tc`, `netem`), iptables rules, or container resource constraints (CPU/memory) that could be causing packet processing delays.
> - **confidence**: high
> - **explanation**: The investigator confirmed the ontology's finding that there was no known failure signature. The subsequent bottom-up investigation found that while alarms are firing across the core, the problem is not with the core logic itself. The `pcscf` container, which is the entry point for user traffic, is experiencing catastrophic network lag. Evidence shows a round-trip time of over 500ms from `pcscf` to its peers, which should be sub-millisecond. This extreme latency causes application-level protocols like HTTP and SIP to time out, effectively isolating the `pcscf` and preventing any user from registering or creating a data session. The thousands of `httpclient:connfail` events on the `pcscf` are a direct symptom of this network failure.
> 
> 

### Scoring Breakdown

**Overall score: 100%**

**Scorer assessment:** The agent provided an outstanding diagnosis, perfectly identifying the root cause, affected component, severity, and fault type with high confidence, demonstrating a complete understanding of the simulated failure and its observable symptoms.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | Yes | The agent correctly identified 'extreme network latency originating from the pcscf container' and 'transport layer failure specific to the pcscf container' with 'latency over 500x the norm' as the root cause, which perfectly matches the simulated P-CSCF latency of 500ms. |
| Component overlap | 100% | The agent precisely identified 'pcscf (container network interface)' as the root cause component. It also correctly listed downstream affected components, which is acceptable. |
| Severity correct | Yes | The agent described the latency as 'extreme' and 'catastrophic', leading to 'application-level timeouts' and 'preventing UE registrations', effectively 'isolating the pcscf'. This accurately reflects the severe impact of 500ms latency causing timeouts and service disruption. |
| Fault type identified | Yes | The agent clearly identified 'extreme network latency' and 'transport layer issue' as the fault type, which is an observable network degradation. The mention of 'tc, netem' in the recommendation is a suggestion for investigation/resolution, not part of the diagnosis of the observable fault type itself. |
| Confidence calibrated | Yes | The agent stated 'high' confidence, which is well-calibrated given the highly accurate, detailed, and evidence-backed diagnosis (500-1000ms RTT, httpclient:connfail). |

**Ranking position:** #1 — The agent provided a single, primary diagnosis that was correct.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 30,512 |
| Output tokens | 2,921 |
| Thinking tokens | 5,644 |
| **Total tokens** | **39,077** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| TriageAgent | 10,767 | 3 | 4 |
| OntologyAnalysis | 0 | 0 | 0 |
| InvestigatorAgent | 23,009 | 3 | 4 |
| SynthesisAgent | 5,301 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 96.8s
