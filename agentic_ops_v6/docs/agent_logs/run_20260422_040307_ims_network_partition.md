# Episode Report: IMS Network Partition

**Agent:** v6  
**Episode ID:** ep_20260422_035718_ims_network_partition  
**Date:** 2026-04-22T03:57:19.795198+00:00  
**Duration:** 347.2s  

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

**Summary:** IMS component I-CSCF is observing Diameter timeouts when communicating with the HSS, suggesting a fault in the IMS registration or call setup flows.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | No evidence of infrastructure-level problems. |
| **ran** | 🟢 GREEN | RAN appears to be operational. |
| **core** | 🟢 GREEN | The 5G Core appears to be functioning correctly. |
| **ims** | 🔴 RED | The issue seems to be localized to the IMS subsystem, specifically around the I-CSCF/HSS interaction. |

**IMS evidence:**
- I-CSCF is reporting timeouts on the Cx interface to the HSS (ims_icscf:uar_timeouts=4, ims_icscf:lir_timeouts=1).
- These timeouts can affect IMS registration and VoNR call setup.

**Ranked hypotheses:**

- **`h1`** (fit=0.80, nf=icscf, specificity=specific):
    - **Statement:** The I-CSCF is experiencing an intermittent internal fault that causes it to fail to process some responses from the HSS, leading to Diameter timeouts on the Cx interface for both registration (UAR) and call setup (LIR) procedures.
    - **Supporting events:** `ims_icscf:uar_timeouts > 0`, `ims_icscf:lir_timeouts > 0`
    - **Falsification probes:**
        - A detailed log analysis on the I-CSCF does not show any errors related to Diameter message processing.
        - A packet capture on the Cx interface between I-CSCF and HSS shows that the HSS is not sending responses to the timed-out requests.
        - Restarting the I-CSCF container does not resolve the issue.
- **`h2`** (fit=0.70, nf=pyhss, specificity=specific):
    - **Statement:** The HSS is selectively failing to process requests from the I-CSCF, while successfully handling requests from the S-CSCF. This would explain why timeouts are only observed on the I-CSCF.
    - **Supporting events:** `ims_icscf:uar_timeouts > 0`, `ims_icscf:lir_timeouts > 0`, `scscf.ims_auth:mar_timeouts == 0`, `scscf.ims_registrar_scscf:sar_timeouts == 0`
    - **Falsification probes:**
        - A detailed log analysis on the HSS shows no incoming requests from the I-CSCF corresponding to the timeout periods.
        - A packet capture on the HSS shows it is receiving and responding to all requests from the I-CSCF correctly.
- **`h3`** (fit=0.40, nf=pcscf, specificity=moderate):
    - **Statement:** The P-CSCF has a high number of HTTP client connection failures, which may indicate a misconfiguration or partial failure. This could be causing it to send malformed SIP requests to the I-CSCF, which in turn causes the I-CSCF to fail in its procedures with the HSS.
    - **Supporting events:** `pcscf.httpclient:connfail > 400`, `ims_icscf:uar_timeouts > 0`
    - **Falsification probes:**
        - An analysis of P-CSCF logs reveals the HTTP connection failures are unrelated to the IMS flows.
        - A packet capture on the Mw interface between P-CSCF and I-CSCF shows well-formed SIP requests.
        - The issue can be reproduced by sending requests directly to the I-CSCF, bypassing the P-CSCF.


## Falsification Plans (Phase 4)

**3 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `icscf`)

**Hypothesis:** The I-CSCF is experiencing an intermittent internal fault that causes it to fail to process some responses from the HSS, leading to Diameter timeouts on the Cx interface for both registration (UAR) and call setup (LIR) procedures.

**Probes (3):**
1. **`get_network_status`** — Check status of all NFs
    - *Expected if hypothesis holds:* The 'icscf' container is in a 'running' state. The hypothesis is about an intermittent internal fault, not a container crash.
    - *Falsifying observation:* The 'icscf' container is 'exited' or in a restart loop. This points to a catastrophic failure, not an intermittent one.
2. **`measure_rtt`** — from='icscf', to_ip='pyhss_ip'
    - *Expected if hypothesis holds:* Low RTT (<5ms) and 0% packet loss. The hypothesis states the fault is internal to the I-CSCF application, not the network connection to the HSS.
    - *Falsifying observation:* High RTT or packet loss. This would indicate a network problem is causing the timeouts, falsifying the application-level fault hypothesis.
3. **`measure_rtt`** — from='pyhss', to_ip='icscf_ip'
    - *Expected if hypothesis holds:* Low RTT (<5ms) and 0% packet loss, for the same reason as the previous probe.
    - *Falsifying observation:* High RTT or packet loss. This, combined with the previous probe, would isolate a network issue as the cause of timeouts, falsifying the application-level hypothesis.

*Notes:* This plan tests the 'internal fault' hypothesis by first checking the basic container health and then verifying the integrity of the network path to the HSS. Any network-level issue between I-CSCF and HSS would falsify the claim that the problem is an application-level fault inside I-CSCF.

### Plan for `h2` (target: `pyhss`)

**Hypothesis:** The HSS is selectively failing to process requests from the I-CSCF, while successfully handling requests from the S-CSCF. This would explain why timeouts are only observed on the I-CSCF.

**Probes (3):**
1. **`get_nf_metrics`** — Check I-CSCF's outbound Diameter metrics.
    - *Expected if hypothesis holds:* Counters on I-CSCF for outbound Diameter requests (UAR/LIR) to HSS should be increasing. This shows I-CSCF is sending requests.
    - *Falsifying observation:* I-CSCF's outbound request counters for UAR/LIR are zero or not increasing. This would mean I-CSCF is not sending the requests, so HSS cannot be dropping them.
2. **`measure_rtt`** — from='scscf', to_ip='pyhss_ip'
    - *Expected if hypothesis holds:* Low RTT (<5ms) and 0% packet loss. The hypothesis relies on the S-CSCF to HSS path being healthy.
    - *Falsifying observation:* High RTT or packet loss. This would show that even the supposedly 'good' path to the HSS has network issues, making a general network problem more likely than a selective HSS processing failure.
3. **`get_nf_metrics`** — Check pyHSS's inbound Diameter metrics.
    - *Expected if hypothesis holds:* HSS metrics should show successful requests from S-CSCF and failed or timed-out requests from I-CSCF.
    - *Falsifying observation:* HSS metrics show zero inbound requests from I-CSCF. If the HSS never receives the requests, it cannot be responsible for failing to process them.

*Notes:* This plan focuses on the 'selective failure' aspect. It verifies that I-CSCF is actually sending requests that HSS is allegedly ignoring (activity-vs-drops), and uses the known-good S-CSCF path as a baseline for triangulation to detect network anomalies.

### Plan for `h3` (target: `pcscf`)

**Hypothesis:** The P-CSCF has a high number of HTTP client connection failures, which may indicate a misconfiguration or partial failure. This could be causing it to send malformed SIP requests to the I-CSCF, which in turn causes the I-CSCF to fail in its procedures with the HSS.

**Probes (3):**
1. **`run_kamcmd`** — container='icscf', command='sl.stats'
    - *Expected if hypothesis holds:* A high count of '4xx' class of failures in the SIP layer statistics. This would indicate that I-CSCF is rejecting requests from P-CSCF as malformed.
    - *Falsifying observation:* Zero or a low count of '4xx' failures. If I-CSCF is not rejecting requests from P-CSCF, it's unlikely that P-CSCF is sending malformed SIP.
2. **`measure_rtt`** — from='pcscf', to_ip='pcf_ip'
    - *Expected if hypothesis holds:* High RTT or packet loss. This would provide a network-level explanation for the 'pcscf.httpclient:connfail' metric.
    - *Falsifying observation:* Low RTT (<5ms) and 0% packet loss. If the network path to the PCF is healthy, the HTTP connection failures are likely due to a configuration or application issue, not a partial network failure, weakening the 'malformed SIP' causal link.
3. **`read_running_config`** — container='pcscf'
    - *Expected if hypothesis holds:* The configuration file shows an incorrect address, port, or other parameter for the PCF, explaining the HTTP connection failures.
    - *Falsifying observation:* The configuration for the PCF (Rx interface) is correct. This would make 'misconfiguration' an unlikely cause for the HTTP failures.

*Notes:* This plan investigates the proposed causal chain from P-CSCF to I-CSCF. It checks for the expected effect (SIP errors on I-CSCF) and then examines the initial trigger (HTTP failures from P-CSCF) by checking for network issues or misconfigurations that could cause it.


## Parallel Investigators (Phase 5)

**3 sub-Investigator verdict(s):** **2 NOT_DISPROVEN**, **1 DISPROVEN**

### `h1` — ✅ **NOT_DISPROVEN**

**Hypothesis:** The I-CSCF is experiencing an intermittent internal fault that causes it to fail to process some responses from the HSS, leading to Diameter timeouts on the Cx interface for both registration (UAR) and call setup (LIR) procedures.

**Reasoning:** The executed probes did not produce evidence that contradicts the hypothesis. The I-CSCF container is running, and network latency from the I-CSCF to the HSS is negligible, which is consistent with the fault being internal to the I-CSCF application. While the reverse path RTT check from the HSS to the I-CSCF failed due to a missing tool in the container, the available evidence does not falsify the hypothesis.

**Probes executed (3):**
- **Check status of all NFs** ✓ CONSISTENT
    - *Tool:* `get_network_status()`
    - *Observation:* [EVIDENCE: get_network_status() -> "'icscf': 'running'"]
    - *Comment:* The 'icscf' container is in a 'running' state as expected. This aligns with the hypothesis of an intermittent internal fault rather than a container-level failure.
- **from='icscf', to_ip='pyhss_ip'** ✓ CONSISTENT
    - *Tool:* `measure_rtt("icscf", "172.22.0.18")`
    - *Observation:* [EVIDENCE: measure_rtt("icscf", "172.22.0.18") -> "3 packets transmitted, 3 received, 0% packet loss, time 2043ms\nrtt min/avg/max/mdev = 0.087/0.105/0.117/0.013 ms"]
    - *Comment:* The RTT from I-CSCF to HSS is extremely low (<1ms) with no packet loss. This confirms the network path is healthy, supporting the hypothesis that the fault is internal to the I-CSCF and not caused by the network.
- **from='pyhss', to_ip='icscf_ip'** ~ AMBIGUOUS
    - *Tool:* `measure_rtt("pyhss", "172.22.0.19")`
    - *Observation:* [EVIDENCE: measure_rtt("pyhss", "172.22.0.19") -> "Ping failed from pyhss to 172.22.0.19: OCI runtime exec failed: exec failed: unable to start container process: exec: \"ping\": executable file not found in $PATH: unknown"]
    - *Comment:* The probe could not be executed because the 'ping' utility is not present in the pyhss container. Therefore, the health of the reverse network path from HSS to I-CSCF could not be verified. This result is ambiguous and does not either confirm or contradict the hypothesis.

### `h2` — ✅ **NOT_DISPROVEN**

**Hypothesis:** The HSS is selectively failing to process requests from the I-CSCF, while successfully handling requests from the S-CSCF. This would explain why timeouts are only observed on the I-CSCF.

**Reasoning:** The executed probes confirm the key elements of the hypothesis. Metrics from the I-CSCF show it is sending Diameter requests (UAR/LIR) but also recording timeouts. Metrics from the S-CSCF show it is also sending requests (MAR/SAR) but receiving replies successfully with zero timeouts. A network connectivity check from the S-CSCF to the HSS shows a healthy path, supporting the 'selective failure' aspect of the hypothesis. While HSS's own metrics lack the granularity to show inbound requests by source, the combined evidence from the CSCFs strongly supports the claim that the HSS is handling requests from the S-CSCF but not consistently from the I-CSCF.

**Probes executed (3):**
- **Check I-CSCF's outbound Diameter metrics.** ✓ CONSISTENT
    - *Tool:* `get_nf_metrics()`
    - *Observation:* [EVIDENCE: get_nf_metrics() -> "ims_icscf:uar_replies_received = 23.0, ims_icscf:uar_timeouts = 4.0, ims_icscf:lir_replies_received = 6.0, ims_icscf:lir_timeouts = 1.0"]
    - *Comment:* The I-CSCF metrics show it is sending both UAR and LIR requests and is experiencing timeouts. This is consistent with the hypothesis that the I-CSCF is attempting to communicate with the HSS.
- **Measure RTT from S-CSCF to pyHSS.** ✓ CONSISTENT
    - *Tool:* `measure_rtt(container = "scscf", target_ip = "172.22.0.18")`
    - *Observation:* [EVIDENCE: measure_rtt("scscf", "172.22.0.18") -> "rtt min/avg/max/mdev = 0.065/0.108/0.133/0.030 ms, 0% packet loss"]
    - *Comment:* The RTT from the S-CSCF to the HSS is extremely low and there is no packet loss. This confirms that the network path for the supposedly 'good' leg of the communication is healthy, which supports the 'selective failure' part of the hypothesis.
- **Check pyHSS's inbound Diameter metrics.** ~ AMBIGUOUS
    - *Tool:* `get_nf_metrics()`
    - *Observation:* [EVIDENCE: get_nf_metrics() -> "pyhss: ims_subscribers = 2"] and [EVIDENCE: get_nf_metrics() -> "scscf: ims_auth:mar_timeouts = 0.0, ims_registrar_scscf:sar_timeouts = 0.0"]
    - *Comment:* The metrics from pyHSS are not detailed enough to show inbound requests from different sources. However, the metrics from the S-CSCF clearly show successful exchanges with the HSS (zero timeouts), while I-CSCF metrics show failures. This contrast strongly, albeit circumstantially, supports the hypothesis.

### `h3` — ❌ **DISPROVEN**

**Hypothesis:** The P-CSCF has a high number of HTTP client connection failures, which may indicate a misconfiguration or partial failure. This could be causing it to send malformed SIP requests to the I-CSCF, which in turn causes the I-CSCF to fail in its procedures with the HSS.

**Reasoning:** The investigation found no evidence to support the proposed causal chain. The I-CSCF is not rejecting requests from the P-CSCF as malformed, which is a direct contradiction of the hypothesis. Furthermore, the probes into the cause of the P-CSCF's HTTP connection failures ruled out both network-level issues and static misconfiguration, weakening the premise of the hypothesis.

**Probes executed (3):**
- **Check I-CSCF for SIP errors from P-CSCF** ✗ CONTRADICTS
    - *Tool:* `run_kamcmd("icscf", "sl.stats")`
    - *Observation:* [EVIDENCE: run_kamcmd("icscf", "sl.stats") -> "\t4xx: 0\n"]
    - *Comment:* The hypothesis predicts a high number of 4xx class failures on the I-CSCF due to malformed SIP from the P-CSCF. The kamcmd statistics show zero such failures, which directly refutes this central claim.
- **Check network path between P-CSCF and PCF** ✗ CONTRADICTS
    - *Tool:* `measure_rtt("pcscf", "172.22.0.27")`
    - *Observation:* [EVIDENCE: measure_rtt("pcscf", "172.22.0.27") -> "0% packet loss, time 2027ms\nrtt min/avg/max/mdev = 0.065/0.080/0.093/0.011 ms"]
    - *Comment:* The RTT and packet loss are negligible, indicating a healthy network path between P-CSCF and PCF. This rules out a partial network failure as the cause for the HTTP connection failures mentioned in the hypothesis's premise.
- **Check P-CSCF's running configuration for the PCF address** ✗ CONTRADICTS
    - *Tool:* `read_running_config("pcscf", "pcf")`
    - *Observation:* [EVIDENCE: read_running_config("pcscf", "pcf") -> "route(NRF_NFM_SUBSCRIBE_PCF);"]
    - *Comment:* The configuration shows that the P-CSCF does not use a static address for the PCF but rather dynamic service discovery via the NRF. This contradicts the 'misconfiguration' premise of the hypothesis, as there is no static address to be misconfigured.

**Alternative suspects:** icscf, pyhss


## Evidence Validation (Phase 6)

**Overall verdict:** clean
**Overall confidence:** high

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 4 | 3/3 | clean | high |
| `InvestigatorAgent_h2` | 3 | 4/4 | clean | high |
| `InvestigatorAgent_h3` | 4 | 3/3 | clean | high |


## Ground Truth

**Failure domain:** ims_signaling  
**Protocol impact:** SIP  
**Affected components:** pcscf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v6-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 207.4s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: The IMS subsystem is experiencing a fault where the I-CSCF is observing Diameter timeouts when communicating with the HSS, impacting user registration and call setup.
> - **timeline**:
>     1. The I-CSCF began observing timeouts for Diameter User Authorization Requests (UAR) sent to the HSS during registration procedures.
>     2. The I-CSCF also began observing timeouts for Diameter Location Info Requests (LIR) sent to the HSS during call setup procedures.
>     3. Investigation confirmed that the S-CSCF is communicating successfully with the same HSS without any timeouts.
> - **root_cause**: The evidence is insufficient to isolate a single root cause. The fault lies in the Diameter communication between the I-CSCF and the HSS, with two equally plausible hypotheses remaining:
>     1. (`h1`) The I-CSCF is experiencing an internal fault, causing it to fail to process valid responses from the HSS. (`primary_suspect_nf`: `icscf`)
>     2. (`h2`) The HSS is selectively failing to process requests from the I-CSCF while continuing to serve the S-CSCF. (`primary_suspect_nf`: `pyhss`)
> - **affected_components**:
>     - `icscf`: Root Cause Candidate
>     - `pyhss`: Root Cause Candidate
>     - `pcscf`: Symptomatic (Exhibited unrelated HTTP client failures)
> - **recommendation**: Verify the Diameter exchange on the Cx interface between the I-CSCF and HSS via packet capture and detailed log analysis on both components. The goal is to determine if the HSS is failing to send responses to the I-CSCF's UAR/LIR messages, or if the I-CSCF is receiving valid responses but failing to process them, leading to a timeout.
> - **confidence**: medium
> - **explanation**: The investigation has confirmed that the issue is isolated to the IMS core, specifically between the I-CSCF and HSS. A hypothesis blaming an upstream P-CSCF fault (`h3`) was disproven, as the I-CSCF is not rejecting any SIP requests from the P-CSCF. The available evidence could not distinguish between an internal I-CSCF fault (`h1`) and a selective failure at the HSS (`h2`). Both remain possible because while the I-CSCF reports timeouts, the S-CSCF reports successful communication with the same HSS. Confidence is medium because further inspection is required to pinpoint the fault to one of these two components.

### Scoring Breakdown

**Overall score: 20%**

**Scorer assessment:** The agent failed to identify the core issue of a P-CSCF network partition, instead focusing on I-CSCF/HSS Diameter timeouts. While it correctly identified the IMS layer as problematic and the severity of impact on new services, its root cause and component identification were incorrect, leading to poor confidence calibration.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | No | The simulated failure was a network partition affecting the P-CSCF, severing its connection to the I-CSCF/S-CSCF. The agent's diagnosis incorrectly identifies the root cause as Diameter timeouts between the I-CSCF and HSS, and explicitly dismisses a P-CSCF fault (h3) as disproven. |
| Component overlap | 0% | The primary affected component, 'pcscf', was identified by the agent but incorrectly labeled as 'Symptomatic' for 'unrelated HTTP client failures,' rather than being identified as the root cause of the network partition. The agent's root cause candidates were 'icscf' and 'pyhss'. |
| Severity correct | Yes | The simulated failure involved completely severed SIP signaling and failure of new registrations/invites, indicating a complete outage for new services. The agent's diagnosis of 'impacting user registration and call setup' due to timeouts correctly reflects this severity. |
| Fault type identified | No | The simulated failure was a network partition leading to severed SIP signaling. The agent identified 'Diameter timeouts' as the fault type, which is a different class of failure (degradation/hang) and for the wrong interface/components. |
| Layer accuracy | Yes | The simulated failure involved the 'pcscf', which is an IMS component. The agent correctly identified the 'ims' layer as being affected ('red' status), even though it misidentified the specific root cause within that layer. |
| Confidence calibrated | No | The agent's diagnosis completely missed the actual root cause (P-CSCF network partition) and misidentified the primary affected component's role. A 'medium' confidence for such a significantly incorrect diagnosis is not well-calibrated. |

**Ranking:** The correct root cause (P-CSCF network partition) was not identified or ranked among the agent's root cause candidates.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 183,937 |
| Output tokens | 5,880 |
| Thinking tokens | 17,491 |
| **Total tokens** | **207,308** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| EventAggregator | 0 | 0 | 0 |
| CorrelationAnalyzer | 0 | 0 | 0 |
| NetworkAnalystAgent | 55,288 | 5 | 6 |
| InstructionGeneratorAgent | 32,168 | 2 | 3 |
| InvestigatorAgent_h1 | 41,673 | 4 | 5 |
| InvestigatorAgent_h2 | 30,023 | 3 | 3 |
| InvestigatorAgent_h3 | 41,338 | 4 | 5 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 6,818 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 347.2s
