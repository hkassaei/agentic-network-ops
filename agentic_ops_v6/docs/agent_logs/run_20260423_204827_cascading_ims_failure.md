# Episode Report: Cascading IMS Failure

**Agent:** v6  
**Episode ID:** ep_20260423_204302_cascading_ims_failure  
**Date:** 2026-04-23T20:43:04.339065+00:00  
**Duration:** 322.4s  

---

## Scenario

**Category:** compound  
**Blast radius:** multi_nf  
**Description:** Kill PyHSS AND add 2-second latency to the S-CSCF. This simulates a cascading failure: the HSS is gone (no Diameter auth) AND the S-CSCF is degraded (slow SIP processing). Total IMS outage.

## Faults Injected

- **container_kill** on `pyhss`
- **network_latency** on `scscf` — {'delay_ms': 2000}

## Baseline (Pre-Fault)

Stack phase before injection: **ready**
All containers running at baseline.

## Fault Propagation Verification

**Verdict:** ✅ `confirmed`

- **Wait:** 0s
- **Actual elapsed:** 0.0s
- **Nodes with significant deltas:** 4
- **Nodes with any drift:** 5

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 0.90 (threshold: 0.70, trained on 211 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following metrics deviate from their learned-healthy baseline. Treat each as a semantic observation (meaning + numbers), not a number alone — the KB's interpretation is the authoritative reading.

- **`derived.pcscf_avg_register_time_ms`** (P-CSCF average SIP REGISTER processing time) — current **0.00 ms** vs learned baseline **248.24 ms** (HIGH, drop)
    - **What it measures:** End-to-end cost of processing a SIP REGISTER through the IMS
signaling chain. Under healthy conditions, dominated by four
Diameter round-trips (UAR + LIR + MAR + SAR) plus SIP forwarding
overhead. Spikes without matching Diameter latency spikes indicate
SIP-path latency (P-CSCF itself or P-CSCF ↔ I-CSCF hop). Remains
meaningful when REGISTERs are failing — numerator and denominator
both track attempts, not completions.
    - **Drop means:** Stall signature. Two distinct cases:
  (a) No REGISTERs arrived in the window — feature is omitted entirely by pre-filter; you won't see a 0 here, you'll see the metric absent.
  (b) REGISTERs arrived but none completed within the window, so the numerator (cumulative register_time) didn't advance while the denominator (rcv_requests_register) did — the ratio snapshots to 0. This is the classic SIP-path-latency signature: a latency injection on P-CSCF, or a partition, is stretching REGISTER processing past the sliding-window horizon. Confirm by checking whether `pcscf.core:rcv_requests_register` is still advancing (it is = case b); if it's flat too, it's case (a).
    - **Healthy typical range:** 150–350 ms
    - **Healthy invariant:** Approximately equal to the sum of the four HSS Diameter round-trips
(UAR + LIR + MAR + SAR).
Large positive delta between observed register_time and this sum =
SIP-path latency (P-CSCF interface or P-CSCF ↔ I-CSCF).

- **`normalized.upf.gtp_outdatapktn3upf_per_ue`** (GTP-U downlink rate per UE (N3)) — current **0.06 packets_per_second** vs learned baseline **3.34 packets_per_second** (MEDIUM, drop)
    - **What it measures:** Health of the downlink user-plane path UPF → gNB. Typically mirrors
uplink rate during calls/data; asymmetry indicates directional
faults (e.g., UPF receiving from internet but not forwarding).
    - **Drop means:** No traffic leaving UPF toward RAN.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE — constant regardless of UE pool size. Roughly symmetric with uplink during healthy calls.

- **`normalized.upf.gtp_indatapktn3upf_per_ue`** (GTP-U uplink rate per UE (N3)) — current **0.05 packets_per_second** vs learned baseline **3.42 packets_per_second** (MEDIUM, drop)
    - **What it measures:** Health of the uplink user-plane path gNB → UPF. Drops to near-zero
during RAN or N3 outage; stays nonzero during active calls or data
sessions. Decoupled from SIP signaling (signals data plane, not
control plane).
    - **Drop means:** Data plane dead on uplink — UPF receiving no packets from gNB.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE — constant regardless of UE pool size. Rises during active VoNR calls (~100 pps for G.711 voice) and data transfer.

- **`normalized.smf.bearers_per_ue`** (Active QoS bearers per UE) — current **2.00 count** vs learned baseline **2.61 count** (LOW, shift)
    - **What it measures:** Per-UE count of active QoS bearers. Baseline reflects default
bearers; increments during VoNR calls indicate dedicated voice
bearers being set up. Drop during an active call = dedicated
bearer torn down unexpectedly (voice will fail).
    - **Shift means:** Expected during VoNR calls (1 extra bearer per active call).
    - **Healthy typical range:** 2–3.5 count
    - **Healthy invariant:** At rest: equals configured default bearers (typically 2 per UE).
During active VoNR call: +1 per caller. The per-UE ratio is the
invariant; absolute count scales with UE pool.

- **`normalized.pcscf.dialogs_per_ue`** (Active SIP dialogs per registered UE at P-CSCF) — current **0.00 count** vs learned baseline **0.57 count** (LOW, drop)
    - **What it measures:** How many calls per user are currently in progress at the P-CSCF.
Going to zero from a non-zero baseline means calls have ended
(normal) OR call setup is failing system-wide (degradation).
Together with rcv_requests_* it discriminates the two.
    - **Drop means:** No active calls. Normal at rest; suspicious if prior state had calls AND INVITE rate is also zero.
    - **Healthy typical range:** 0–1 count
    - **Healthy invariant:** Per-UE — scale-independent. 0 at rest, ~1 per active VoNR call.

- **`derived.upf_activity_during_calls`** — current **1.00** vs learned baseline **0.47** (LOW, spike). *(No KB context available — interpret from the metric name.)*


## Event Aggregation (Phase 1)

No events fired during this episode. Either no metric KB triggers matched, or the episode encountered no meaningful state transitions.

## Correlation Analysis (Phase 2)

No events fired — correlation engine had nothing to work with.

## Network Analysis (Phase 3)

**Summary:** The IMS stack is down due to the HSS (Home Subscriber Server) container having exited, which prevents UE registration and all subsequent call activity.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | No signs of underlying infrastructure failure. |
| **ran** | 🟢 GREEN | RAN appears healthy and connected to the core. |
| **core** | 🟡 YELLOW | The 5G core is partially degraded. While NFs are running, it is not processing user plane traffic for voice, which is a secondary effect of the IMS failure, not a root cause in the core itself. |
| **ims** | 🔴 RED | The IMS layer is non-functional due to the critical failure of the HSS. |

**CORE evidence:**
- UPF per-UE data rates are near zero.
- SMF is not setting up dedicated bearers.

**IMS evidence:**
- The HSS container has exited.
- Multiple Diameter links to the HSS are inactive.
- P-CSCF average register time has dropped to zero, indicating a stall.
- No active SIP dialogs are present.

**Ranked hypotheses:**

- **`h1`** (fit=1.00, nf=pyhss, specificity=specific):
    - **Statement:** The HSS (Home Subscriber Server) container ('pyhss') has exited. This is a fatal failure for the IMS stack, as the HSS is required for UE authentication and routing. All observed anomalies are direct consequences of its unavailability.
    - **Falsification probes:**
        - Check the container logs for 'pyhss' to determine the cause of the exit.
        - Restart the 'pyhss' container and observe if IMS registration functionality is restored.
        - Attempt to measure RTT from 'icscf' or 'scscf' to the 'pyhss' IP address; the probe should fail.
- **`h3`** (fit=0.60, nf=icscf, specificity=moderate):
    - **Statement:** The I-CSCF is failing to route authentication and registration requests to the HSS. While it receives REGISTER requests from the P-CSCF, it cannot get a successful response from the HSS for the Diameter Cx interface UAR/LIR procedures, causing the entire registration process to time out.
    - **Falsification probes:**
        - Check I-CSCF logs for Diameter timeout errors related to the HSS.
        - Confirm that the HSS is in fact unreachable from the I-CSCF container via a ping or other network probe.
- **`h2`** (fit=0.40, nf=pcscf, specificity=moderate):
    - **Statement:** The P-CSCF is experiencing a processing stall or internal latency injection. This is causing SIP REGISTER transactions to fail to complete within the measurement window, leading to the appearance of a downstream failure.
    - **Falsification probes:**
        - Check P-CSCF logs for internal errors or high CPU usage that is not correlated with traffic.
        - Use 'measure_rtt' to confirm low latency from P-CSCF to its direct peer, I-CSCF. If latency is low, the issue is likely not on the network path and could be internal to P-CSCF.


## Falsification Plans (Phase 4)

**3 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `pyhss`)

**Hypothesis:** The HSS (Home Subscriber Server) container ('pyhss') has exited. This is a fatal failure for the IMS stack, as the HSS is required for UE authentication and routing. All observed anomalies are direct consequences of its unavailability.

**Probes (3):**
1. **`get_network_status`** — None
    - *Expected if hypothesis holds:* The status for container 'pyhss' will be 'exited' or 'down'.
    - *Falsifying observation:* The status is 'running'. This would directly contradict the hypothesis.
2. **`measure_rtt`** — from 'icscf' to the IP of 'pyhss'
    - *Expected if hypothesis holds:* 100% packet loss. The container is down and cannot respond.
    - *Falsifying observation:* Clean RTT (< 5ms). This would indicate the HSS container is up and reachable on the network, falsifying the 'exited' claim.
3. **`check_process_listeners`** — container 'pyhss'
    - *Expected if hypothesis holds:* The tool returns an error because the container is not running, or it returns an empty list of listening ports.
    - *Falsifying observation:* A list of listening ports including the Diameter port (3868/tcp). This would prove the HSS process is running and has bound its network sockets.

*Notes:* This hypothesis is the most specific and has the highest fit. The probes are designed to quickly and definitively confirm or deny the container's status, which is the core claim.

### Plan for `h3` (target: `icscf`)

**Hypothesis:** The I-CSCF is failing to route authentication and registration requests to the HSS. While it receives REGISTER requests from the P-CSCF, it cannot get a successful response from the HSS for the Diameter Cx interface UAR/LIR procedures, causing the entire registration process to time out.

**Probes (3):**
1. **`measure_rtt`** — from 'icscf' to the IP of 'pyhss'
    - *Expected if hypothesis holds:* High packet loss or latency, indicating a network partition between I-CSCF and HSS.
    - *Falsifying observation:* Clean RTT (< 5ms). If the network path is healthy, the inability to get a response is not due to a routing/network failure.
2. **`measure_rtt`** — Triangulation probe: from 'scscf' to the IP of 'pyhss'
    - *Expected if hypothesis holds:* High packet loss or latency (similar to the first probe). This would suggest the HSS is broadly unreachable, not an issue specific to I-CSCF's path.
    - *Falsifying observation:* Clean RTT (< 5ms). If S-CSCF can reach HSS but I-CSCF cannot, it strongly isolates the fault to the I-CSCF or its specific network path.
3. **`get_nf_metrics`** — Filter for 'icscf' metrics
    - *Expected if hypothesis holds:* Elevated counters for Diameter client timeouts or errors (e.g., a metric like 'diameter_cx_timeout_count'). This shows I-CSCF is *trying* to communicate but failing.
    - *Falsifying observation:* No Diameter-related error metrics are incrementing on I-CSCF. This would suggest I-CSCF may not even be attempting the HSS query, pointing towards a configuration issue rather than a runtime routing failure.

*Notes:* This plan tests the integrity of the connection from I-CSCF to HSS. The triangulation probe is key to distinguishing between an I-CSCF-specific issue and a broader HSS availability problem.

### Plan for `h2` (target: `pcscf`)

**Hypothesis:** The P-CSCF is experiencing a processing stall or internal latency injection. This is causing SIP REGISTER transactions to fail to complete within the measurement window, leading to the appearance of a downstream failure.

**Probes (3):**
1. **`measure_rtt`** — from 'pcscf' to the IP of 'icscf'
    - *Expected if hypothesis holds:* Clean RTT (< 5ms). If the problem is an internal stall, the network path to its peer should be healthy.
    - *Falsifying observation:* High latency or packet loss. This would falsify the 'internal stall' claim by providing evidence of a network issue between P-CSCF and its next hop.
2. **`get_nf_metrics`** — Filter for 'pcscf' metrics
    - *Expected if hypothesis holds:* High value for shared memory usage ('kamailio_shmem_used_pct') or a high number of transaction processing errors ('kamailio_tm_rpl_sent_failure_ratio').
    - *Falsifying observation:* Internal health and processing metrics for P-CSCF are all nominal. If memory usage and transaction error rates are low, an 'internal stall' is unlikely.
3. **`run_kamcmd`** — container 'pcscf', command 'ps.ps'
    - *Expected if hypothesis holds:* Output shows one or more SIP worker processes with very high CPU time or in a stuck state.
    - *Falsifying observation:* All SIP worker processes show low CPU time and are in a 'waiting' or 'idle' state. This would indicate no processing backlog or stall.

*Notes:* This plan focuses on P-CSCF's internal state, assuming the network is healthy as per the hypothesis. Probes check for signs of resource exhaustion or processing backlogs that would be invisible to external network probes.


## Parallel Investigators (Phase 5)

**3 sub-Investigator verdict(s):** **1 NOT_DISPROVEN**, **2 DISPROVEN**

### `h1` — ✅ **NOT_DISPROVEN**

**Hypothesis:** The HSS (Home Subscriber Server) container ('pyhss') has exited. This is a fatal failure for the IMS stack, as the HSS is required for UE authentication and routing. All observed anomalies are direct consequences of its unavailability.

**Reasoning:** All executed probes returned results that are consistent with the hypothesis. The 'pyhss' container is confirmed to be in an 'exited' state, is unreachable on the network from the I-CSCF, and consequently has no active listening ports. No falsifying evidence was found.

**Probes executed (3):**
- **Check the status for container 'pyhss'.** ✓ CONSISTENT
    - *Tool:* `default_api.get_network_status()`
    - *Observation:* [EVIDENCE: get_network_status() -> "'pyhss': 'exited'"]
    - *Comment:* The tool confirmed that the status of the 'pyhss' container is 'exited', which directly supports the core claim of the hypothesis.
- **Measure RTT from 'icscf' to the IP of 'pyhss'.** ✓ CONSISTENT
    - *Tool:* `default_api.measure_rtt(container='icscf', target_ip='172.22.0.18')`
    - *Observation:* [EVIDENCE: measure_rtt("icscf", "172.22.0.18") -> "100% packet loss"]
    - *Comment:* The ping from I-CSCF to the HSS IP address resulted in 100% packet loss. This is the expected outcome if the target container is down.
- **Check listening ports on container 'pyhss'.** ✓ CONSISTENT
    - *Tool:* `default_api.check_process_listeners(container='pyhss')`
    - *Observation:* [EVIDENCE: check_process_listeners("pyhss") -> "Error response from daemon: container ... is not running"]
    - *Comment:* The tool failed because the container is not running, which is what the hypothesis predicts. This confirms the container is not in a state where it could be listening for connections.

### `h3` — ❌ **DISPROVEN**

**Hypothesis:** The I-CSCF is failing to route authentication and registration requests to the HSS. While it receives REGISTER requests from the P-CSCF, it cannot get a successful response from the HSS for the Diameter Cx interface UAR/LIR procedures, causing the entire registration process to time out.

**Reasoning:** The hypothesis is disproven because the I-CSCF's metrics show no Diameter timeouts. Probes show the HSS is unreachable, but the I-CSCF is not erroring in the way the hypothesis predicts. Specifically, `ims_icscf:uar_timeouts` and `ims_icscf:lir_timeouts` are both 0, which directly contradicts the claim that the registration process is timing out due to failed Diameter procedures at the I-CSCF.

**Probes executed (3):**
- **from 'icscf' to the IP of 'pyhss'** ✓ CONSISTENT
    - *Tool:* `default_api.measure_rtt(container='icscf', target_ip='172.22.0.18')`
    - *Observation:* [EVIDENCE: measure_rtt("icscf", "172.22.0.18") -> "Target 172.22.0.18 is UNREACHABLE from icscf (no response within 10s):...100% packet loss"]
    - *Comment:* This confirms a network partition or failure at the HSS, which is consistent with the hypothesis's premise of I-CSCF being unable to get a response.
- **Triangulation probe: from 'scscf' to the IP of 'pyhss'** ✓ CONSISTENT
    - *Tool:* `default_api.measure_rtt(container='scscf', target_ip='172.22.0.18')`
    - *Observation:* [EVIDENCE: measure_rtt("scscf", "172.22.0.18") -> "Target 172.22.0.18 is UNREACHABLE from scscf (no response within 10s):...100% packet loss"]
    - *Comment:* This triangulation probe shows that the HSS is unreachable from another IMS component as well, suggesting the fault lies with the HSS itself rather than a path specific to the I-CSCF.
- **Filter for 'icscf' metrics** ✗ CONTRADICTS
    - *Tool:* `default_api.get_nf_metrics()`
    - *Observation:* [EVIDENCE: get_nf_metrics() -> "ims_icscf:uar_timeouts = 0.0, ims_icscf:lir_timeouts = 0.0"]
    - *Comment:* This is the key falsifying observation. The hypothesis states the process is timing out, which should increment Diameter timeout counters on the I-CSCF. The metrics show zero timeouts, proving the failure mechanism described in the hypothesis is not occurring.

**Alternative suspects:** pyhss

### `h2` — ❌ **DISPROVEN**

**Hypothesis:** The P-CSCF is experiencing a processing stall or internal latency injection. This is causing SIP REGISTER transactions to fail to complete within the measurement window, leading to the appearance of a downstream failure.

**Reasoning:** The hypothesis of an internal P-CSCF stall is contradicted by key metrics. The `tmx:active_transactions` counter for P-CSCF is zero, indicating no backlog of stuck SIP transactions. Conversely, the metrics `httpclient:connfail = 88.0` and `httpclient:connok = 0.0` strongly indicate that P-CSCF is healthy but is failing to connect to a required downstream service over HTTP, which points to an external dependency failure, not an internal stall.

**Probes executed (3):**
- **from 'pcscf' to the IP of 'icscf'** ✓ CONSISTENT
    - *Tool:* `default_api.measure_rtt(container='pcscf', target_ip='172.22.0.19')`
    - *Observation:* [EVIDENCE: measure_rtt("pcscf", "172.22.0.19") -> "3 packets transmitted, 3 received, 0% packet loss, time 2007ms\nrtt min/avg/max/mdev = 0.069/1.919/5.586/2.592 ms"]
    - *Comment:* The network path from P-CSCF to its next hop (I-CSCF) is healthy, with low latency and no packet loss. This is consistent with the hypothesis that the problem is not a network issue.
- **Filter for 'pcscf' metrics** ✗ CONTRADICTS
    - *Tool:* `default_api.get_nf_metrics()`
    - *Observation:* [EVIDENCE: get_nf_metrics() -> "P-CSCF [2 reg] (via kamcmd): ... tmx:active_transactions = 0.0 ... httpclient:connfail = 88.0 ... httpclient:connok = 0.0"]
    - *Comment:* The number of active transactions is zero, which falsifies the 'processing stall' claim. Furthermore, the high number of HTTP connection failures points to a downstream dependency issue (likely the PCF), not an internal P-CSCF problem.
- **container 'pcscf', command 'ps.ps'** ~ AMBIGUOUS
    - *Tool:* `default_api.run_kamcmd(container='pcscf', command='ps.ps')`
    - *Observation:* [EVIDENCE: run_kamcmd("pcscf", "ps.ps") -> "error: 500 - command ps.ps not found"]
    - *Comment:* The tool command failed, so no information about the state of worker processes could be obtained. However, other evidence (zero active transactions) makes stuck processes very unlikely.

**Alternative suspects:** pcf


## Evidence Validation (Phase 6)

**Overall verdict:** clean
**Overall confidence:** high

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 4 | 3/3 | clean | high |
| `InvestigatorAgent_h3` | 4 | 3/3 | clean | high |
| `InvestigatorAgent_h2` | 4 | 3/3 | clean | high |


## Ground Truth

**Failure domain:** ims_signaling  
**Protocol impact:** SIP  
**Affected components:** scscf, pyhss  
**Severity:** degraded

## Agent Diagnosis

**Model:** v6-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 169.9s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: The IMS stack is non-functional because the Home Subscriber Server (HSS) container has exited, which prevents all user equipment from registering and making calls.
> - **timeline**:
>     1. The `pyhss` container, which runs the Home Subscriber Server (HSS), enters an 'exited' state.
>     2. Consequently, the HSS becomes completely unreachable on the network.
>     3. The I-CSCF, which needs to query the HSS to authenticate users during registration, can no longer establish a connection.
>     4. All incoming UE registration attempts arriving at the P-CSCF and forwarded to the I-CSCF fail because the authentication step cannot be completed.
>     5. This leads to a complete outage of the IMS service.
> - **root_cause**: The `pyhss` (HSS) container has terminated unexpectedly. The HSS is a critical component for user authentication and service profile management, and its failure is fatal for the entire IMS stack. The primary suspect is `pyhss`.
> - **affected_components**:
>     - `pyhss` (HSS): Root Cause
>     - `icscf` (I-CSCF): Secondary
>     - `scscf` (S-CSCF): Secondary
>     - `pcscf` (P-CSCF): Symptomatic
> - **recommendation**: An operator should investigate the logs for the `pyhss` container to determine the reason for its unexpected exit. They should also verify that the container is currently in an 'exited' state and is unreachable from other IMS components like the 'icscf'.
> - **confidence**: high
> - **explanation**: The investigation confirmed with high confidence that the root cause is the failure of the Home Subscriber Server (HSS). Hypothesis `h1`, which stated the `pyhss` container had exited, was directly supported by evidence showing the container's status as 'exited' and network probes confirming it was unreachable. Alternative hypotheses were definitively disproven. The theory of an I-CSCF routing failure (`h3`) was falsified because its specific Diameter timeout metrics were at zero. The theory of a P-CSCF processing stall (`h2`) was falsified because its active transaction count was zero, ruling out an internal backlog. The failure of the HSS is the single event that explains all observed symptoms.

### Scoring Breakdown

**Overall score: 100%**

**Scorer assessment:** The agent provided an excellent diagnosis, accurately identifying the HSS failure as the root cause of the IMS outage, correctly assessing its severity and fault type, and attributing it to the correct layer with high confidence.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | Yes | The agent correctly identified the HSS (pyhss) being unreachable/terminated as the root cause of the IMS outage. While the S-CSCF also had latency injected, the HSS failure is sufficient to cause a total IMS registration failure and would mask the S-CSCF's degradation for many IMS functions. |
| Component overlap | 100% | The agent correctly identified 'pyhss' (HSS) as the 'Root Cause' in its affected components list. This is one of the primary components directly affected by the simulation. It also correctly listed other cascading/downstream components and the S-CSCF (which was also directly affected) as 'Secondary', indicating its involvement. |
| Severity correct | Yes | The agent correctly assessed the impact as a 'non-functional' IMS stack and a 'complete outage of the IMS service', which matches the 'Total IMS outage' described in the simulated failure. |
| Fault type identified | Yes | The agent identified the HSS as 'completely unreachable' and its container as 'exited', which accurately describes the 'Component completely unreachable (down/not responding)' fault type for the HSS. |
| Layer accuracy | Yes | The agent's network analysis correctly rated the 'ims' layer as 'red' and provided evidence directly related to the HSS failure and its impact on IMS components, aligning with the ground truth that 'pyhss' and 'scscf' belong to the 'ims' layer. |
| Confidence calibrated | Yes | The agent's diagnosis is highly accurate and well-supported by the provided explanation and evidence, making its 'high' confidence level appropriate. |

**Ranking position:** #1 — The agent clearly identified the 'pyhss' (HSS) as the primary root cause, effectively ranking it first.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 160,797 |
| Output tokens | 5,316 |
| Thinking tokens | 12,013 |
| **Total tokens** | **178,126** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| EventAggregator | 0 | 0 | 0 |
| CorrelationAnalyzer | 0 | 0 | 0 |
| NetworkAnalystAgent | 39,417 | 4 | 3 |
| InstructionGeneratorAgent | 14,880 | 1 | 2 |
| InvestigatorAgent_h1 | 32,360 | 4 | 4 |
| InvestigatorAgent_h3 | 31,159 | 4 | 3 |
| InvestigatorAgent_h2 | 54,352 | 4 | 5 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 5,958 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 322.4s
