# Episode Report: HSS Unresponsive

**Agent:** v6  
**Episode ID:** ep_20260429_161845_hss_unresponsive  
**Date:** 2026-04-29T16:18:48.256894+00:00  
**Duration:** 330.8s  

---

## Scenario

**Category:** network  
**Blast radius:** single_nf  
**Description:** Inject 60-second outbound delay on the HSS (PyHSS), making it functionally unreachable for all real-time protocols. The HSS container is running and the process is alive, but all network responses are delayed by 60 seconds — far exceeding Diameter Cx timeouts (5-30s) and standard probe timeouts (10s). From the perspective of diagnostic tools and IMS peers, the HSS appears completely unresponsive or unreachable.

## Faults Injected

- **network_latency** on `pyhss` — {'delay_ms': 60000, 'jitter_ms': 0}

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

**ANOMALY DETECTED.** Overall anomaly score: 56.57 (per-bucket threshold: 26.31, context bucket (0, 1), trained on 323 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following metrics deviate from their learned-healthy baseline. Treat each as a semantic observation (meaning + numbers), not a number alone — the KB's interpretation is the authoritative reading.

- **`context.cx_active`** — current **0.00** vs learned baseline **0.59** (MEDIUM, drop). *(No KB context available — interpret from the metric name.)*

- **`derived.icscf_lir_timeout_ratio`** (I-CSCF LIR timeout ratio) — current **1.00 ratio** vs learned baseline **0.00 ratio** (MEDIUM, spike)
    - **What it measures:** Partial partition or severe overload on the Cx path during call routing. Zero in healthy operation; non-zero means some LIR queries did not receive a response within the timeout window.
    - **Spike means:** HSS partitioned during call setup, overloaded, or Cx path losing packets.
    - **Healthy typical range:** 0–0 ratio
    - **Healthy invariant:** Zero in healthy operation.

- **`derived.icscf_uar_timeout_ratio`** (I-CSCF UAR timeout ratio) — current **1.00 ratio** vs learned baseline **0.00 ratio** (MEDIUM, spike)
    - **What it measures:** Partial partition or severe overload on the Cx path. Zero in
healthy operation; non-zero means some UAR queries did not receive
any response within the timeout window.
    - **Spike means:** HSS partitioned, overloaded past its timeout, or Cx path losing packets.
    - **Healthy typical range:** 0–0 ratio
    - **Healthy invariant:** Zero in healthy operation.

- **`normalized.icscf.cdp_replies_per_ue`** (I-CSCF Diameter reply rate per UE) — current **0.00 replies_per_second_per_ue** vs learned baseline **0.03 replies_per_second_per_ue** (MEDIUM, drop)
    - **What it measures:** Liveness of the I-CSCF↔HSS Cx path. Drops to 0 when HSS is unreachable OR when no signaling is occurring at the I-CSCF (idle or upstream P-CSCF partitioned).
    - **Drop means:** No Cx replies in the window. Could be healthy idle OR a Cx-path fault.
    - **Healthy typical range:** 0–1 replies_per_second_per_ue

- **`normalized.icscf.core:rcv_requests_invite_per_ue`** (SIP INVITE rate per UE at I-CSCF) — current **0.01 requests_per_second** vs learned baseline **0.00 requests_per_second** (MEDIUM, spike)
    - **What it measures:** Health of call-setup forwarding P-CSCF → I-CSCF. Partition signature
same as REGISTER rate.
    - **Spike means:** Forwarding failure.
    - **Healthy typical range:** 0–0.2 requests_per_second
    - **Healthy invariant:** Per-UE rate. Tracks pcscf.invite rate.

- **`normalized.icscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at I-CSCF) — current **0.02 requests_per_second** vs learned baseline **0.06 requests_per_second** (MEDIUM, drop)
    - **What it measures:** Health of the P-CSCF → I-CSCF forwarding path (Mw interface). When
this drops to zero while P-CSCF REGISTER rate is still non-zero,
it's the SIGNATURE of an IMS partition between P-CSCF and I-CSCF.
    - **Drop means:** Either UEs not registering at all, or P-CSCF isolated from I-CSCF.
    - **Healthy typical range:** 0–0.5 requests_per_second
    - **Healthy invariant:** Per-UE rate. Should closely track ims.pcscf.rcv_requests_register_per_ue.

- **`normalized.pcscf.core:rcv_requests_invite_per_ue`** (SIP INVITE rate per UE at P-CSCF) — current **0.01 requests_per_second** vs learned baseline **0.00 requests_per_second** (MEDIUM, spike)
    - **What it measures:** Call attempt rate from registered UEs. Unlike REGISTER (periodic),
INVITEs only fire when UEs place calls. Zero is normal during
quiet periods; nonzero INVITE with zero dialogs is the signature
of call setup failure.
    - **Spike means:** Fewer call attempts.
    - **Healthy typical range:** 0–0.2 requests_per_second
    - **Healthy invariant:** Per-UE rate.

- **`normalized.pcscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at P-CSCF) — current **0.02 requests_per_second** vs learned baseline **0.06 requests_per_second** (MEDIUM, drop)
    - **What it measures:** How actively UEs are refreshing their IMS registrations with the
P-CSCF. REGISTERs arrive periodically (re-registration timer) plus
at attach. Sustained zero means UEs cannot reach P-CSCF OR the
UE-to-network SIP path is broken.
    - **Drop means:** No REGISTERs flowing. Unusual unless UEs are all deregistered.
    - **Healthy typical range:** 0–0.5 requests_per_second
    - **Healthy invariant:** Per-UE rate — same value at any deployment scale.

- **`normalized.scscf.cdp_replies_per_ue`** (S-CSCF CDP Diameter replies per UE) — current **0.00 replies_per_second_per_ue** vs learned baseline **0.06 replies_per_second_per_ue** (MEDIUM, drop)
    - **What it measures:** Active S-CSCF Diameter traffic with HSS. Near-zero when registrations idle OR HSS partition.
    - **Drop means:** No active S-CSCF Diameter exchanges (idle or partitioned).
    - **Healthy typical range:** 0–1 replies_per_second_per_ue
    - **Healthy invariant:** Per-UE rate; varies with registration/auth load.

- **`normalized.scscf.core:rcv_requests_invite_per_ue`** (SIP INVITE rate per UE at S-CSCF) — current **0.01 requests_per_second** vs learned baseline **0.00 requests_per_second** (MEDIUM, spike)
    - **What it measures:** S-CSCF participation in call setup. Zero when calls aren't being
placed OR S-CSCF not receiving forwarded INVITEs.
    - **Spike means:** Upstream forwarding issue.
    - **Healthy typical range:** 0–0.2 requests_per_second
    - **Healthy invariant:** Per-UE rate.


## Event Aggregation (Phase 1)

No events fired during this episode. Either no metric KB triggers matched, or the episode encountered no meaningful state transitions.

## Correlation Analysis (Phase 2)

No events fired — correlation engine had nothing to work with.

## Network Analysis (Phase 3)

**Summary:** The HSS is online but unresponsive to application-level Diameter queries, causing a complete failure of IMS registration and call setup procedures.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | All relevant containers are running, and network connectivity between them is healthy. The fault is not at the infrastructure level. |
| **ran** | 🟢 GREEN | RAN components are reporting normal status. |
| **core** | 🟢 GREEN | Core network functions appear to be operating as expected. The issue is localized to the IMS domain. |
| **ims** | 🔴 RED | The entire IMS signaling plane is non-functional. Both I-CSCF and S-CSCF are unable to communicate with the HSS over the Cx interface, leading to 100% timeouts on requests for user location (LIR) and authorization (UAR). |

**IMS evidence:**
- derived.icscf_lir_timeout_ratio: 1.0
- derived.icscf_uar_timeout_ratio: 1.0
- normalized.icscf.cdp_replies_per_ue: 0.0
- normalized.scscf.cdp_replies_per_ue: 0.0

**Ranked hypotheses:**

- **`h1`** (fit=0.95, nf=pyhss, specificity=specific):
    - **Statement:** The HSS (pyhss) is unresponsive to Diameter queries on the Cx interface from both the I-CSCF and S-CSCF. While the container is running and network-reachable, its Diameter service is either stalled, overloaded, or has failed internally, causing all dependent IMS procedures to time out.
    - **Supporting events:** `derived.icscf_lir_timeout_ratio`, `derived.icscf_uar_timeout_ratio`, `normalized.icscf.cdp_replies_per_ue`, `normalized.scscf.cdp_replies_per_ue`
    - **Falsification probes:**
        - Check the logs of the 'pyhss' container for any Diameter errors or stack traces.
        - Attempt a direct Diameter query to the HSS from a test tool to see if it responds to any Cx requests.
        - Check the CPU and memory utilization of the 'pyhss' container to rule out resource exhaustion.


## Falsification Plans (Phase 4)

**1 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `pyhss`)

**Hypothesis:** The HSS (pyhss) is unresponsive to Diameter queries on the Cx interface from both the I-CSCF and S-CSCF. While the container is running and network-reachable, its Diameter service is either stalled, overloaded, or has failed internally, causing all dependent IMS procedures to time out.

**Probes (3):**
1. **`check_process_listeners`** — container: pyhss
    - *Expected if hypothesis holds:* The pyhss container has a process listening on the Diameter port (TCP 3868). This confirms the service is running but unresponsive at the application layer.
    - *Falsifying observation:* There is no process listening on TCP port 3868. This would imply the Diameter service inside the container has crashed or failed to start.
2. **`measure_rtt`** — from: icscf, to_ip: pyhss
    - *Expected if hypothesis holds:* RTT is low (<10ms) and there is 0% packet loss, confirming that the network path is not the source of the timeouts.
    - *Falsifying observation:* High RTT or significant packet loss is observed. This would indicate a network connectivity issue is the likely cause, falsifying the hypothesis that the HSS application is the sole culprit.
3. **`get_nf_metrics`** — Inspect Diameter metrics for icscf and pyhss.
    - *Expected if hypothesis holds:* I-CSCF's outgoing Diameter request metrics (e.g., kamailio.cdp.requests_sent) are increasing, while pyhss's received request metrics (e.g., pyhss.diameter.requests.total) are at zero or are not increasing.
    - *Falsifying observation:* pyhss's received request metrics are increasing at a rate comparable to I-CSCF's sent requests. This would prove the HSS is not unresponsive and the issue lies elsewhere.

*Notes:* This plan aims to falsify the hypothesis by triangulating the problem. It checks for basic network reachability to rule out a partition, verifies the HSS process is listening at the transport layer, and compares application-layer metrics on both sides of the Diameter connection (I-CSCF and HSS) to pinpoint where requests are being dropped.


## Parallel Investigators (Phase 5)

**1 sub-Investigator verdict(s):** **1 DISPROVEN**

### `h1` — ❌ **DISPROVEN**

**Hypothesis:** The HSS (pyhss) is unresponsive to Diameter queries on the Cx interface from both the I-CSCF and S-CSCF. While the container is running and network-reachable, its Diameter service is either stalled, overloaded, or has failed internally, causing all dependent IMS procedures to time out.

**Reasoning:** The hypothesis is disproven because one of its core premises, that the pyhss container is 'network-reachable', is false. The `measure_rtt` probe shows 100% packet loss from the I-CSCF to the pyhss container, indicating a network partition. This network failure is the cause of the Diameter timeouts, not an application-level issue within a reachable HSS.

**Probes executed (3):**
- **Check if pyhss container has a process listening on the Diameter port (TCP 3868).** ~ AMBIGUOUS
    - *Tool:* `print(default_api.check_process_listeners(container = "pyhss"))`
    - *Observation:* [EVIDENCE: check_process_listeners("pyhss") -> "Neither ss nor netstat available in pyhss. Output: OCI runtime exec failed: exec failed: unable to start container process: exec: \"netstat\": executable file not found in $PATH: unknown"]
    - *Comment:* The tool failed to execute within the container, so no conclusion could be drawn about listening processes. This neither supports nor contradicts the hypothesis.
- **Measure RTT from icscf to pyhss to confirm network path is not the source of timeouts.** ✗ CONTRADICTS
    - *Tool:* `print(default_api.measure_rtt(container = "icscf", target_ip = "172.22.0.18"))`
    - *Observation:* [EVIDENCE: measure_rtt("icscf", "172.22.0.18") -> "Target 172.22.0.18 is UNREACHABLE from icscf (no response within 10s):\nPING 172.22.0.18 (172.22.0.18) 56(84) bytes of data.\n\n--- 172.22.0.18 ping statistics ---\n3 packets transmitted, 0 received, 100% packet loss, time 2036ms"]
    - *Comment:* This result directly contradicts the hypothesis's claim that the pyhss container is 'network-reachable'. The 100% packet loss indicates a network partition is the root cause of the communication failure.
- **Inspect Diameter metrics for icscf and pyhss.** ✗ CONTRADICTS
    - *Tool:* `print(default_api.get_nf_metrics())`
    - *Observation:* [EVIDENCE: get_nf_metrics() -> "ICSCF... cdp:timeout = 3.0... ims_icscf:lir_timeouts = 1.0... ims_icscf:uar_timeouts = 2.0... pyhss metrics are NOT present in the output"]
    - *Comment:* I-CSCF shows Diameter timeouts as expected, but the complete absence of any metrics from pyhss, combined with the packet loss observed in the RTT probe, contradicts the idea of a running but 'stalled' or 'overloaded' service. The evidence points to a network isolation issue.

**Alternative suspects:** pyhss


## Evidence Validation (Phase 6)

**Overall verdict:** clean
**Overall confidence:** high

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 4 | 3/3 | clean | high |


## Ground Truth

**Failure domain:** ims_signaling  
**Protocol impact:** Diameter  
**Affected components:** pyhss  
**Severity:** degraded

## Agent Diagnosis

**Model:** v6-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 168.3s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: The IMS service is down due to a network partition that is isolating the HSS container (`pyhss`), preventing the I-CSCF and S-CSCF from communicating with it.
> - **timeline**:
>     1. IMS registration and call setup procedures begin to fail due to timeouts on Diameter requests.
>     2. The I-CSCF (`icscf`) and S-CSCF (`scscf`) report 100% timeouts for User Authorization (UAR) and Location Info (LIR) requests sent to the HSS.
>     3. Investigation reveals 100% packet loss between the I-CSCF and the HSS, confirming the HSS container is unreachable over the network.
> - **root_cause**: A network partition is isolating the HSS (`pyhss`) container from other IMS network functions. While the `pyhss` container itself is running, it is unreachable, causing all dependent services to fail. The `primary_suspect_nf` is `pyhss` due to its network isolation.
> - **affected_components**:
>     - `pyhss`: Root Cause (Isolated by network partition)
>     - `icscf`: Secondary (Unable to reach HSS)
>     - `scscf`: Secondary (Unable to reach HSS)
> - **recommendation**: Verify the network path and connectivity between the `icscf` container and the `pyhss` container (IP `172.22.0.18`). Investigate container networking configurations, virtual switches, and any host-level networking or firewall rules that could be causing the observed 100% packet loss.
> - **confidence**: low
> - **explanation**: The initial hypothesis, which suggested an application-level failure within a reachable HSS, was disproven. Probes conducted by the investigator revealed that the core premise of the HSS being 'network-reachable' was false. A network round-trip time test from the I-CSCF to the HSS showed 100% packet loss, indicating a complete network partition. This network failure is the direct cause of the Diameter timeouts observed by the I-CSCF and S-CSCF, leading to the total IMS outage. Because the initial hypothesis set was incorrect, confidence is low pending further investigation into the source of the network partition.

### Scoring Breakdown

**Overall score: 85%**

**Scorer assessment:** The agent provided a highly accurate diagnosis of the HSS unreachability due to network issues, correctly identifying the root cause, affected components, severity, and fault type. However, its intermediate network analysis contained contradictory information regarding infrastructure health, and its final confidence was unduly low given the accuracy of its conclusion.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | Yes | The simulated failure was an extreme network delay on the HSS, making it functionally unreachable and causing 100% packet loss for standard probes. The agent correctly identified the HSS as unreachable due to a 'network partition' and '100% packet loss', which is an accurate description of the observable failure mode. |
| Component overlap | 100% | The agent correctly identified 'pyhss' (HSS) as the 'Root Cause' in its affected components list. |
| Severity correct | Yes | The simulated failure caused a complete functional unreachability of the HSS, leading to a total service outage. The agent correctly described this as 'IMS service is down' and a 'total IMS outage' due to a 'complete network partition'. |
| Fault type identified | Yes | The agent identified the fault as a 'network partition' leading to the HSS being 'unreachable' with '100% packet loss'. This accurately describes the observable fault type resulting from the extreme network delay. |
| Layer accuracy | No | While the agent correctly rated the 'ims' layer as red (as HSS is an IMS component), its 'NETWORK ANALYSIS' section incorrectly stated the 'infrastructure' layer was green with 'measure_rtt(icscf -> pyhss): <1ms'. The simulated failure (60s delay) should have resulted in 100% packet loss for RTT probes and indicated an issue at the infrastructure/network level, not healthy connectivity. This is a misrepresentation of the network layer's status in the intermediate reasoning. |
| Confidence calibrated | No | The agent's final diagnosis is highly accurate and definitive, correctly identifying the root cause, affected components, severity, and fault type. Despite this, the agent stated 'low' confidence, citing an initial incorrect hypothesis. Given the strength and correctness of the final conclusion, a 'low' confidence is under-calibrated. |

**Ranking:** The agent provided a single root cause in its diagnosis, so no ranking is applicable.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 97,588 |
| Output tokens | 2,819 |
| Thinking tokens | 10,664 |
| **Total tokens** | **111,071** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| EventAggregator | 0 | 0 | 0 |
| CorrelationAnalyzer | 0 | 0 | 0 |
| NetworkAnalystAgent | 57,947 | 7 | 4 |
| InstructionGeneratorAgent | 16,984 | 1 | 2 |
| InvestigatorAgent_h1 | 31,755 | 4 | 3 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 4,385 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 330.8s
