# Episode Report: HSS Unresponsive

**Agent:** v5  
**Episode ID:** ep_20260401_043456_hss_unresponsive  
**Date:** 2026-04-01T04:34:57.667714+00:00  
**Duration:** 195.6s  

---

## Scenario

**Category:** network  
**Blast radius:** single_nf  
**Description:** Inject 60-second outbound delay on the HSS (PyHSS). The HSS container is running, the process is alive, and the IP is reachable — but all Diameter responses are delayed by 60 seconds, far exceeding the Cx Diameter timeout. Tests how the I-CSCF and S-CSCF handle a Diameter peer that accepts connections but never responds in time.

## Faults Injected

- **network_latency** on `pyhss` — {'delay_ms': 60000, 'jitter_ms': 0}

## Baseline (Pre-Fault)

Stack phase before injection: **ready**
All containers running at baseline.

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

## Ontology Analysis (Phase 0.5)

```
Top Diagnosis: No matching signature found (confidence: low)
Triggered Rules: baseline_delta_rule
```

**Focus domain:** unknown  
**Confidence:** low  
**Mandate to investigator:** The ontology found no matching failure signature. Perform a bottom-up investigation: check transport first, then core, then application layer. Cite tool outputs for every claim.

## Ground Truth

**Failure domain:** ims_signaling  
**Protocol impact:** Diameter  
**Affected components:** pyhss  
**Severity:** degraded

## Agent Diagnosis

**Model:** v5-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 184.9s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: The P-CSCF is misconfigured, with its TLS key and certificate parameters commented out, preventing it from establishing secure HTTP/2 connections to other 5G network functions.
> - **timeline**:
>     1.  The P-CSCF container starts, loading a configuration where `modparam` directives for the `nghttp2` module's TLS private key and certificate are commented out.
>     2.  The `nghttp2` module fails to initialize its TLS context, logging an error: "Could not read private key file".
>     3.  The P-CSCF attempts to communicate with the Service Communication Proxy (SCP) over the HTTP/2-based Service-Based Interface (SBI) to discover other network functions (like PCF).
>     4.  The outgoing connection attempt fails during the TLS handshake because the P-CSCF's TLS context is not properly initialized.
>     5.  This failure is recorded as the metric `httpclient:connfail`, which increments repeatedly, while `httpclient:connok` remains at 0.
>     6.  Without the ability to communicate over the SBI, the P-CSCF cannot function correctly within the 5G Service-Based Architecture, leading to a failure of end-to-end IMS flows.
> - **root_cause**: The P-CSCF's running configuration file has the `modparam` lines for loading the TLS private key and public certificate commented out. This prevents the `nghttp2` module from initializing TLS, which is mandatory for all Service-Based Interface (SBI) communication in the 5G core.
> - **affected_components**:
>     - P-CSCF
>     - SCP (indirectly, as it never receives valid requests from P-CSCF)
> - **recommendation**: Edit the P-CSCF's Kamailio configuration file and uncomment the following lines to enable the loading of TLS credentials for the HTTP/2 module:
>     ```
>     # modparam("nghttp2", "tls_private_key", "/mnt/pcscf/http2_key.pem")
>     # modparam("nghttp2", "tls_public_key", "/mnt/pcscf/http2_tr.pem")
>     ```
>     Then, restart the P-CSCF container for the change to take effect.
> - **confidence**: high
> - **explanation**: The investigation disproved the initial low-confidence ontology hypothesis, finding a novel configuration error. The 5G core uses a Service-Based Architecture (SBA) where network functions communicate using secure HTTP/2 APIs. The P-CSCF's role requires it to talk to other services like the PCF via this mechanism. The root cause is a simple configuration mistake where the lines telling the P-CSCF's HTTP/2 engine where to find its security credentials were disabled. Without these credentials, all its attempts to establish secure connections failed, as confirmed by the `httpclient:connfail = 99.0` metric and the "Could not read private key file" error in its logs.

### Scoring Breakdown

**Overall score: 15%**

**Scorer assessment:** The agent completely misdiagnosed the HSS latency issue, instead identifying an unrelated P-CSCF configuration problem with high confidence, though it correctly assessed the severity as a complete service outage.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | No | The simulated failure was an HSS unresponsiveness due to 60-second latency, leading to Diameter timeouts. The agent diagnosed a P-CSCF misconfiguration related to TLS keys for HTTP/2 communication, which is completely unrelated to the actual failure. |
| Component overlap | 0% | The primary affected component in the simulated failure was the HSS (PyHSS), with I-CSCF and S-CSCF experiencing timeouts. The agent identified P-CSCF and SCP as affected components, which have no overlap with the actual affected components. |
| Severity correct | Yes | The simulated failure (60-second delay on HSS) would lead to a complete outage for services relying on HSS (SIP REGISTER stalls). The agent's diagnosis also describes a complete failure of end-to-end IMS flows due to the P-CSCF not functioning correctly. Both describe a complete service disruption, so the severity assessment is correct. |
| Fault type identified | No | The simulated failure was 'elevated network latency' leading to 'timeout'. The agent identified a 'configuration error' (TLS keys commented out) and a 'functional failure' (TLS handshake failure), not a network degradation or timeout issue. |
| Confidence calibrated | No | The agent stated 'high' confidence for a diagnosis that is entirely incorrect regarding the root cause, affected components, and fault type. This indicates poor calibration. |

**Ranking:** The agent provided only one diagnosis, which was incorrect.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 87,627 |
| Output tokens | 3,049 |
| Thinking tokens | 9,292 |
| **Total tokens** | **99,968** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| TriageAgent | 10,987 | 3 | 4 |
| OntologyAnalysis | 0 | 0 | 0 |
| InvestigatorAgent | 84,289 | 10 | 11 |
| SynthesisAgent | 4,692 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 195.6s
