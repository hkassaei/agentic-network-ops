# Episode Report: IMS Network Partition

**Agent:** v6  
**Episode ID:** ep_20260421_030810_ims_network_partition  
**Date:** 2026-04-21T03:08:12.389184+00:00  
**Duration:** 314.6s  

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
- **Nodes with significant deltas:** 1
- **Nodes with any drift:** 3

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

## Anomaly Screening (Phase 0)

No anomalies detected by the statistical screener.

## Event Aggregation (Phase 1)

No events fired during this episode. Either no metric KB triggers matched, or the episode encountered no meaningful state transitions.

## Correlation Analysis (Phase 2)

No events fired — correlation engine had nothing to work with.

## Network Analysis (Phase 3)

**Summary:** IMS registration failures are occurring due to Diameter timeouts between the I-CSCF and the HSS, with a secondary anomaly of high HTTP connection failures on the P-CSCF.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟡 YELLOW | The timeouts between I-CSCF and HSS could indicate an underlying network issue (latency, packet loss), but there is no direct evidence yet. All containers are running and links appear active. |
| **ran** | 🟢 GREEN | No metrics or events indicate a RAN-layer issue. AMF reports 2 connected UEs and 1 GNB. |
| **core** | 🟢 GREEN | Core network functions (AMF, SMF, UPF) appear stable with active sessions and no error counters. |
| **ims** | 🔴 RED | The IMS layer is unhealthy. I-CSCF is timing out on user authorization requests to the HSS, which is a critical failure for registration. P-CSCF is also reporting a very high number of HTTP client connection failures. |

**INFRASTRUCTURE evidence:**
- icscf.ims_icscf:uar_timeouts = 9

**IMS evidence:**
- icscf.ims_icscf:uar_timeouts = 9
- pcscf.httpclient:connfail = 376
- pcscf.script:register_failed = 9

**Ranked hypotheses:**

- **`h1`** (fit=0.80, nf=pyhss, specificity=specific):
    - **Statement:** The HSS is partially unresponsive or overloaded, failing to respond to Diameter User-Authorization-Requests (UAR) from the I-CSCF within the timeout period. This is the likely cause of the observed registration failures.
    - **Supporting events:** `icscf.ims_icscf:uar_timeouts = 9`
    - **Falsification probes:**
        - Measure RTT and packet loss from I-CSCF to HSS to rule out a network path issue.
        - Examine HSS internal logs and resource metrics (CPU, memory) for signs of overload or errors when processing UARs.
- **`h2`** (fit=0.60, nf=pcscf, specificity=specific):
    - **Statement:** The P-CSCF is experiencing a local malfunction or resource exhaustion, indicated by the massive number of HTTP client connection failures. This primary fault on the ingress NF of the IMS domain could be causing the registration failures, with downstream symptoms like the I-CSCF timeouts being secondary effects.
    - **Supporting events:** `pcscf.httpclient:connfail = 376`, `pcscf.script:register_failed = 9`
    - **Falsification probes:**
        - Investigate the purpose of the HTTP client in the P-CSCF configuration to understand the impact of its failure.
        - Check P-CSCF container logs and resource usage (file descriptors, memory) for signs of exhaustion.
        - Attempt a registration with a UE, tracing the flow to see if the failure occurs before or after the P-CSCF forwards the request.
- **`h3`** (fit=0.50, nf=icscf, specificity=moderate):
    - **Statement:** There is a network connectivity issue, such as packet loss or high latency, specifically on the path between the I-CSCF and the HSS. This is causing the Diameter timeouts, which are transport-sensitive.
    - **Supporting events:** `icscf.ims_icscf:uar_timeouts = 9`
    - **Falsification probes:**
        - Use 'measure_rtt' from 'icscf' to the HSS IP address to check for elevated latency or packet loss.
        - Run a packet capture on the I-CSCF's Diameter interface to look for retransmissions or lack of replies from the HSS.


## Falsification Plans (Phase 4)

**3 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `pyhss`)

**Hypothesis:** The HSS is partially unresponsive or overloaded, failing to respond to Diameter User-Authorization-Requests (UAR) from the I-CSCF within the timeout period. This is the likely cause of the observed registration failures.

**Probes (3):**
1. **`get_nf_metrics`** — for 'pyhss'
    - *Expected if hypothesis holds:* High CPU usage, high memory usage, or increasing Diameter message queue length on 'pyhss'.
    - *Falsifying observation:* Normal CPU/memory usage and stable Diameter queue length on 'pyhss' – indicating HSS is not overloaded.
2. **`measure_rtt`** — from='icscf', to_ip='pyhss'
    - *Expected if hypothesis holds:* High RTT (> 100ms) or significant packet loss (> 5%) from icscf to pyhss, or at least slow responses.
    - *Falsifying observation:* Low RTT (< 5ms) and 0% packet loss from 'icscf' to 'pyhss' – indicating a healthy network path, suggesting the HSS might be actively dropping requests at the application layer.
3. **`read_container_logs`** — container='pyhss', grep='User-Authorization-Request|UAR|error', since='5m'
    - *Expected if hypothesis holds:* Logs showing errors related to processing UARs or no logs for incoming UARs if it's truly unresponsive at the application layer (i.e. not even receiving them).
    - *Falsifying observation:* Logs showing successful UAR processing and responses, or a complete absence of logs for UARs (which, combined with healthy RTT, would indicate another issue).

*Notes:* This plan focuses on HSS internal state and direct connectivity, distinguishing between HSS application-layer issues and basic network reachability.

### Plan for `h2` (target: `pcscf`)

**Hypothesis:** The P-CSCF is experiencing a local malfunction or resource exhaustion, indicated by the massive number of HTTP client connection failures. This primary fault on the ingress NF of the IMS domain could be causing the registration failures, with downstream symptoms like the I-CSCF timeouts being secondary effects.

**Probes (3):**
1. **`get_nf_metrics`** — for 'pcscf'
    - *Expected if hypothesis holds:* High CPU usage, high memory usage, high open file descriptors, or high HTTP connection counts exceeding limits on 'pcscf'.
    - *Falsifying observation:* Normal resource usage (CPU, memory, file descriptors) on 'pcscf' – indicating the connection failures might not be due to local exhaustion.
2. **`read_container_logs`** — container='pcscf', grep='httpclient.*connfail|error|register_failed', since='5m'
    - *Expected if hypothesis holds:* Logs detailing specific errors related to HTTP client connection failures or registration failures, possibly showing target IP addresses or reasons for failure.
    - *Falsifying observation:* Absence of new HTTP client connection failure logs, or logs indicating successful connections after a period of failures – suggesting the issue might be intermittent or resolved.
3. **`measure_rtt`** — from='pcscf', to_ip='icscf'
    - *Expected if hypothesis holds:* Normal RTT (< 5ms) and 0% packet loss from 'pcscf' to 'icscf' – suggesting the P-CSCF's issues are internal and not network-related to its next hop.
    - *Falsifying observation:* High RTT or packet loss from 'pcscf' to 'icscf' – suggesting the P-CSCF's connection failures are due to network problems reaching its next hop, which would shift the fault away from the P-CSCF itself.

*Notes:* This plan aims to confirm P-CSCF resource issues and understand the nature of HTTP connection failures, and also checks its connectivity to the next IMS hop (I-CSCF).

### Plan for `h3` (target: `icscf`)

**Hypothesis:** There is a network connectivity issue, such as packet loss or high latency, specifically on the path between the I-CSCF and the HSS. This is causing the Diameter timeouts, which are transport-sensitive.

**Probes (3):**
1. **`measure_rtt`** — from='icscf', to_ip='pyhss'
    - *Expected if hypothesis holds:* High RTT (> 100ms) or significant packet loss (> 5%) from 'icscf' to 'pyhss'.
    - *Falsifying observation:* Low RTT (< 5ms) and 0% packet loss from 'icscf' to 'pyhss' – this would directly falsify the hypothesis of a network connectivity issue on this specific path.
2. **`measure_rtt`** — from='pyhss', to_ip='icscf'
    - *Expected if hypothesis holds:* High RTT or significant packet loss from 'pyhss' to 'icscf' (mirroring the forward path issue).
    - *Falsifying observation:* Low RTT (< 5ms) and 0% packet loss from 'pyhss' to 'icscf' while the forward path (I-CSCF to HSS) shows issues – this would suggest a unidirectional problem or an issue closer to the I-CSCF's sending path rather than a general network path issue. If both are healthy, the hypothesis is false.
3. **`measure_rtt`** — from='icscf', to_ip='amf'
    - *Expected if hypothesis holds:* Low RTT (< 5ms) and 0% packet loss from 'icscf' to 'amf' (confirming I-CSCF's general network health, isolating the problem to the HSS path).
    - *Falsifying observation:* High RTT or packet loss from 'icscf' to 'amf' – this would indicate a general network issue originating from the I-CSCF or its immediate network segment, rather than a specific path issue to HSS.

*Notes:* This plan uses multiple RTT probes to rigorously test the network path between I-CSCF and HSS, including triangulation to pinpoint if the issue is bidirectional, unidirectional, or I-CSCF-specific.


## Parallel Investigators (Phase 5)

**3 sub-Investigator verdict(s):** **3 DISPROVEN**

### `h1` — ❌ **DISPROVEN**

**Hypothesis:** The HSS is partially unresponsive or overloaded, failing to respond to Diameter User-Authorization-Requests (UAR) from the I-CSCF within the timeout period. This is the likely cause of the observed registration failures.

**Reasoning:** The `measure_rtt` probe showed a perfect network path between I-CSCF and HSS, ruling out network-level unresponsiveness. The `read_container_logs` probe showed a complete absence of logs for incoming User-Authorization-Requests (UARs) in the HSS, while the I-CSCF is reporting timeouts for these exact requests. This indicates the HSS is not overloaded, but likely has an application-level fault preventing it from receiving or processing any UARs at all.

**Probes executed (3):**
- **High CPU usage, high memory usage, or increasing Diameter message queue length on 'pyhss'.** ~ AMBIGUOUS
    - *Tool:* `print(default_api.get_nf_metrics())`
    - *Observation:* [EVIDENCE: get_nf_metrics() -> "PYHSS [2 subs] (via api):\n  ims_subscribers = 2  [uncategorized]"]
    - *Comment:* The metrics returned for pyhss were minimal and did not contain any information about resource usage (CPU, memory) or Diameter queue length. This result is inconclusive.
- **High RTT (> 100ms) or significant packet loss (> 5%) from icscf to pyhss, or at least slow responses.** ✗ CONTRADICTS
    - *Tool:* `print(default_api.measure_rtt(container = "icscf", target_ip = "172.22.0.18"))`
    - *Observation:* [EVIDENCE: measure_rtt("icscf", "172.22.0.18") -> "3 packets transmitted, 3 received, 0% packet loss...rtt min/avg/max/mdev = 0.080/0.086/0.092/0.005 ms"]
    - *Comment:* The RTT between I-CSCF and HSS is extremely low (< 1ms) with zero packet loss. This falsifies the idea that the HSS is unresponsive due to network issues or OS-level resource exhaustion.
- **Logs showing errors related to processing UARs or no logs for incoming UARs if it's truly unresponsive at the application layer (i.e. not even receiving them).** ✓ CONSISTENT
    - *Tool:* `print(default_api.read_container_logs(container = "pyhss", grep = "User-Authorization-Request|UAR|error", since_seconds = 300))`
    - *Observation:* [EVIDENCE: read_container_logs("pyhss", "User-Authorization-Request|UAR|error", 300) -> "(no log output)"]
    - *Comment:* There are no logs in the pyhss container related to UARs or errors. Combined with the healthy RTT and the I-CSCF's timeout reports, this strongly suggests the HSS application is not processing the requests at all, contradicting the 'overload' hypothesis and pointing towards a more fundamental application failure.

**Alternative suspects:** pyhss

### `h2` — ❌ **DISPROVEN**

**Hypothesis:** The P-CSCF is experiencing a local malfunction or resource exhaustion, indicated by the massive number of HTTP client connection failures. This primary fault on the ingress NF of the IMS domain could be causing the registration failures, with downstream symptoms like the I-CSCF timeouts being secondary effects.

**Reasoning:** The hypothesis of a local P-CSCF malfunction is disproven by the finding of a complete network partition between the P-CSCF and I-CSCF. A probe to measure the round-trip time showed 100% packet loss, indicating the P-CSCF cannot reach the I-CSCF at all. The HTTP client connection failures are therefore a symptom of this network failure, not a cause rooted in P-CSCF resource exhaustion.

**Probes executed (3):**
- **for 'pcscf'** ~ AMBIGUOUS
    - *Tool:* `get_nf_metrics()`
    - *Observation:* [EVIDENCE: get_nf_metrics() -> "PCSCF [...]: httpclient:connfail = 390.0  [counter]"]
    - *Comment:* The high cumulative counter for 'connfail' is consistent with the initial symptom, but no metrics indicating CPU/memory/resource exhaustion were found. This neither strongly supports nor contradicts the hypothesis.
- **container='pcscf', grep='httpclient.*connfail|error|register_failed', since='5m'** ✗ CONTRADICTS
    - *Tool:* `read_container_logs("pcscf", "httpclient.*connfail|error|register_failed", 300)`
    - *Observation:* [EVIDENCE: read_container_logs("pcscf", "httpclient.*connfail|error|register_failed", 300) -> "(no log output)"]
    - *Comment:* The absence of any recent logs related to HTTP connection failures or registration failures contradicts the idea of an ongoing local malfunction. The problem that caused the high 'connfail' counter is not currently happening.
- **from='pcscf', to_ip='icscf'** ✗ CONTRADICTS
    - *Tool:* `measure_rtt("pcscf", "172.22.0.19")`
    - *Observation:* [EVIDENCE: measure_rtt("pcscf", "172.22.0.19") -> "100% packet loss"]
    - *Comment:* This result directly falsifies the hypothesis. The problem is not a 'local malfunction' within P-CSCF, but a network failure preventing it from reaching its next hop, the I-CSCF. This externalizes the fault from the P-CSCF itself.

**Alternative suspects:** pcscf, icscf

### `h3` — ❌ **DISPROVEN**

**Hypothesis:** There is a network connectivity issue, such as packet loss or high latency, specifically on the path between the I-CSCF and the HSS. This is causing the Diameter timeouts, which are transport-sensitive.

**Reasoning:** The core of the hypothesis is a network issue between I-CSCF and HSS. The RTT measurement from I-CSCF to HSS (pyhss) shows extremely low latency (<1ms) and zero packet loss, which directly contradicts this claim. This indicates the network path is healthy and the timeouts are likely an application-layer issue within the HSS, not a transport problem.

**Probes executed (3):**
- **Measure RTT from 'icscf' to 'pyhss'.** ✗ CONTRADICTS
    - *Tool:* `default_api.measure_rtt(container='icscf', target_ip='pyhss')`
    - *Observation:* [EVIDENCE: measure_rtt("icscf", "pyhss") -> "rtt min/avg/max/mdev = 0.080/0.163/0.278/0.083 ms", "0% packet loss"]
    - *Comment:* The measured RTT is excellent and there is no packet loss. This directly falsifies the hypothesis that a network connectivity issue exists on this path.
- **Measure RTT from 'pyhss' to 'icscf'.** ~ AMBIGUOUS
    - *Tool:* `default_api.measure_rtt(container='pyhss', target_ip='icscf')`
    - *Observation:* [EVIDENCE: measure_rtt("pyhss", "icscf") -> "Ping failed from pyhss to icscf: OCI runtime exec failed: exec failed: unable to start container process: exec: \"ping\": executable file not found in $PATH: unknown"]
    - *Comment:* The probe could not be executed because the 'ping' utility is not available in the pyhss container. No conclusion can be drawn about the reverse network path.
- **Measure RTT from 'icscf' to 'amf'.** ✗ CONTRADICTS
    - *Tool:* `default_api.measure_rtt(container='icscf', target_ip='amf')`
    - *Observation:* [EVIDENCE: measure_rtt("icscf", "amf") -> "rtt min/avg/max/mdev = 0.136/0.317/0.531/0.162 ms", "0% packet loss"]
    - *Comment:* This probe confirms that the I-CSCF has healthy network connectivity to other network functions. Combined with the first probe's result, this reinforces the conclusion that there is no network issue originating from or specific to the I-CSCF's path to the HSS.

**Alternative suspects:** pyhss


## Evidence Validation (Phase 6)

**Overall verdict:** clean
**Overall confidence:** high

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 4 | 3/3 | clean | high |
| `InvestigatorAgent_h2` | 4 | 3/3 | clean | high |
| `InvestigatorAgent_h3` | 3 | 3/3 | clean | high |


## Ground Truth

**Failure domain:** ims_signaling  
**Protocol impact:** SIP  
**Affected components:** pcscf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v6-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 153.7s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: The initial hypotheses were disproven, but the investigation revealed two distinct critical failures: a network partition between the P-CSCF and I-CSCF, and an application-level fault in the HSS preventing it from processing Diameter requests.
> - **timeline**:
>     1. The P-CSCF begins failing to connect to its upstream peer (`pcscf.httpclient:connfail`), leading to registration failures (`pcscf.script:register_failed`).
>     2. Concurrently, the I-CSCF starts timing out when sending user authorization requests to the HSS (`icscf.ims_icscf:uar_timeouts`).
>     3. These two independent failures combine to create a complete breakdown of the IMS registration process.
> - **root_cause**: The initial set of hypotheses was incorrect. The investigation points to a complex scenario with two independent root causes that were not anticipated: a complete network partition between the P-CSCF and I-CSCF, and an application-level fault within the HSS (pyhss) that prevents it from processing Diameter requests, even though it is reachable on the network.
> - **affected_components**:
>     - `Network between pcscf and icscf`: Root Cause (network partition)
>     - `pyhss (HSS)`: Root Cause (application fault)
>     - `pcscf`: Symptomatic (isolated by network partition)
>     - `icscf`: Symptomatic (isolated from both P-CSCF and HSS)
> - **recommendation**: Further investigation is required.
>     1. Verify network connectivity between the `pcscf` and `icscf` containers to diagnose the cause of the 100% packet loss. Examine container networking, routing, and any intermediate firewall or network policies.
>     2. Verify the application status within the `pyhss` container. Although the network path from the I-CSCF is healthy, logs confirm the HSS is not processing incoming Diameter User-Authorization-Requests, suggesting a service configuration error or a hung process.
> - **confidence**: low
> - **explanation**: All three initial hypotheses were disproven through investigation. The hypothesis of an HSS network issue (`h3`) was falsified by a probe showing perfect connectivity between the I-CSCF and HSS. The HSS overload hypothesis (`h1`) was disproven when logs showed the HSS was not receiving any UARs at all, pointing to an application fault rather than overload. Finally, the P-CSCF local malfunction hypothesis (`h2`) was disproven by the discovery of 100% packet loss between the P-CSCF and I-CSCF, indicating the P-CSCF failures are a symptom of a network partition, not a local cause. Confidence is low because the original hypotheses were wrong, and the precise nature of the two newly discovered faults requires manual verification.

### Scoring Breakdown

**Overall score: 100%**

**Scorer assessment:** The agent provided an excellent diagnosis, correctly identifying the network partition as the root cause, its severity, fault type, and affected components, and placing it in the correct layer. Its low confidence was also well-calibrated despite identifying an additional, incorrect root cause.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | Yes | The agent correctly identified 'a complete network partition between the P-CSCF and I-CSCF' as a root cause. Although it also identified an additional, incorrect root cause (HSS application fault), the correct cause was listed first among the 'two independent root causes'. |
| Component overlap | 100% | The agent correctly identified 'Network between pcscf and icscf' as a root cause and 'pcscf' as a symptomatic affected component, which directly aligns with the simulated failure. It also correctly identified 'icscf' as symptomatic due to isolation from P-CSCF. The mention of HSS is an additional, incorrect component, but the primary affected components for the simulated failure are correctly identified. |
| Severity correct | Yes | The agent described the failure as a 'complete network partition' and '100% packet loss', which accurately reflects the 'completely severed' SIP signaling and 'new REGISTER and INVITE fail' of the simulated outage. |
| Fault type identified | Yes | The agent explicitly identified the fault type as a 'network partition' and '100% packet loss', which directly matches the simulated 'Network partition — component isolated' failure mode. |
| Layer accuracy | Yes | The agent correctly rated the 'ims' layer as 'red' with evidence from 'pcscf' (an IMS component), indicating the primary failure is correctly attributed. While it also flagged 'infrastructure' as 'yellow' for a potential network issue, a network partition is an infrastructure-level problem, and it did not misattribute an IMS component's failure to the infrastructure layer. |
| Confidence calibrated | Yes | The agent stated 'low' confidence, explaining that its initial hypotheses were disproven and the precise nature of the two newly discovered faults (one correct, one incorrect) requires manual verification. This level of confidence is appropriate given the mixed accuracy of its final diagnosis. |

**Ranking position:** #1 — The correct root cause ('complete network partition between the P-CSCF and I-CSCF') was listed first among the two identified root causes.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 152,088 |
| Output tokens | 5,843 |
| Thinking tokens | 16,943 |
| **Total tokens** | **174,874** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| EventAggregator | 0 | 0 | 0 |
| CorrelationAnalyzer | 0 | 0 | 0 |
| NetworkAnalystAgent | 29,448 | 3 | 4 |
| InstructionGeneratorAgent | 19,013 | 1 | 2 |
| InvestigatorAgent_h1 | 52,437 | 4 | 5 |
| InvestigatorAgent_h2 | 53,008 | 4 | 5 |
| InvestigatorAgent_h3 | 14,466 | 3 | 2 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 6,502 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 314.6s
