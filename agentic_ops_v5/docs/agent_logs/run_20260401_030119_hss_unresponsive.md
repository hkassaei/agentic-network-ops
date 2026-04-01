# Episode Report: HSS Unresponsive

**Agent:** v5  
**Episode ID:** ep_20260401_025914_hss_unresponsive  
**Date:** 2026-04-01T02:59:15.415070+00:00  
**Duration:** 123.5s  

---

## Scenario

**Category:** container  
**Blast radius:** single_nf  
**Description:** Pause PyHSS (freeze all processes). The HSS is still 'running' from Docker's perspective but cannot process Diameter requests. Tests how the I-CSCF and S-CSCF handle a hung Diameter peer.

## Faults Injected

- **container_pause** on `pyhss`

## Baseline (Pre-Fault)

Stack phase before injection: **ready**
All containers running at baseline.

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

## Ground Truth

**Failure domain:** ims_signaling  
**Protocol impact:** Diameter  
**Affected components:** pyhss  
**Severity:** degraded

## Agent Diagnosis

**Model:** v5-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 112.8s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: The IMS Home Subscriber Server (HSS) is offline because its container (`pyhss`) is in a `paused` state, which prevents all user authentications and subsequent 5G session establishments.
> - **timeline**:
>     1.  The `pyhss` container, which provides HSS functionality, entered a `paused` state, effectively taking the HSS offline.
>     2.  IMS components (I-CSCF, S-CSCF) attempting to query the HSS for subscriber authentication data timed out, as confirmed by a direct API query.
>     3.  Without a functional HSS, no IMS registrations could be completed, and no 5G sessions could be established.
>     4.  This led to all session-related metrics across the 5G core and IMS (`amf_session`, `smf.bearers_active`, `upf_sessionnbr`, etc.) dropping to zero, triggering the baseline alarms.
> - **root_cause**: The `pyhss` container has been administratively paused. The investigation confirmed this is not a crash or a network failure, as the container's IP is reachable with zero packet loss. The failure of other components to perform their functions is a direct result of their dependency on the HSS.
> - **affected_components**: `pyhss` (root cause), `scscf`, `icscf`, `pcscf`, `amf`, `smf`, `pcf`, `upf` (symptomatic).
> - **recommendation**: Unpause the `pyhss` container using the command: `docker unpause pyhss`.
> - **confidence**: high
> - **explanation**: The investigation confirmed the ontology's initial inability to find a signature and followed its recommendation for a bottom-up investigation. The root cause is not a software bug or network failure, but an administrative state change. The HSS acts as the master database for subscriber authentication and services in the IMS core. With it paused, no user can be verified, which halts the entire IMS registration and 5G session setup process. Evidence confirms network connectivity to the HSS is healthy, isolating the problem to the `paused` state of the container itself.
> 
> ---
> *The Investigator's findings confirmed the ontology's initial assessment that no specific failure signature matched, warranting a manual bottom-up investigation. The evidence trail directly supports the conclusion that the paused HSS container is the root cause.*
> *Supporting Evidence: [EVIDENCE: get_network_status() -> "{\"pyhss\": \"paused\"}"], [EVIDENCE: query_subscriber("ims", "001011234567891") -> "PyHSS API timeout"], [EVIDENCE: measure_rtt("icscf", "172.22.0.18") -> "0% packet loss"]*

### Scoring Breakdown

**Overall score: 100%**

**Scorer assessment:** The agent provided an outstanding diagnosis, precisely identifying the paused HSS container as the root cause, its severe impact, and supporting it with clear evidence, demonstrating excellent understanding of the simulated failure.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | Yes | The agent correctly identified that the PyHSS container being in a 'paused' state was the root cause, which directly matches the simulated failure mode of an unresponsive HSS due to freezing processes. |
| Component overlap | 100% | The agent correctly identified 'pyhss' as the root cause component. It also correctly listed downstream components affected by the HSS outage. |
| Severity correct | Yes | The agent described the impact as the HSS being 'offline', preventing 'all user authentications', and leading to 'all session-related metrics... dropping to zero', which accurately reflects the complete functional outage caused by the HSS being unresponsive. |
| Fault type identified | Yes | The agent identified the fault as the HSS being in a 'paused' state, leading to unresponsiveness despite network connectivity being healthy. This accurately describes the observable fault type where a component is functionally hung/unresponsive. |
| Confidence calibrated | Yes | The agent stated 'high' confidence, which is appropriate given the precise and accurate diagnosis, backed by direct evidence of the 'paused' container state and API timeouts. |

**Ranking position:** #1 — The agent provided a single, clear root cause as its primary diagnosis.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 69,546 |
| Output tokens | 3,772 |
| Thinking tokens | 3,876 |
| **Total tokens** | **77,194** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| TriageAgent | 11,243 | 3 | 4 |
| OntologyAnalysis | 0 | 0 | 0 |
| InvestigatorAgent | 61,016 | 8 | 9 |
| SynthesisAgent | 4,935 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 123.5s
