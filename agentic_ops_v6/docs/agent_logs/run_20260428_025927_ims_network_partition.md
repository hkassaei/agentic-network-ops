# Episode Report: IMS Network Partition

**Agent:** v6  
**Episode ID:** ep_20260428_025352_ims_network_partition  
**Date:** 2026-04-28T02:53:53.975270+00:00  
**Duration:** 333.0s  

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
- **Nodes with significant deltas:** 2
- **Nodes with any drift:** 3

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 0.94 (threshold: 0.70, trained on 104 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following metrics deviate from their learned-healthy baseline. Treat each as a semantic observation (meaning + numbers), not a number alone — the KB's interpretation is the authoritative reading.

- **`derived.pcscf_avg_register_time_ms`** (P-CSCF average SIP REGISTER processing time) — current **0.00 ms** vs learned baseline **155.39 ms** (HIGH, drop)
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

- **`normalized.upf.gtp_outdatapktn3upf_per_ue`** (GTP-U downlink rate per UE (N3)) — current **0.15 packets_per_second** vs learned baseline **3.37 packets_per_second** (MEDIUM, drop)
    - **What it measures:** Health of the downlink user-plane path UPF → gNB. Typically mirrors
uplink rate during calls/data; asymmetry indicates directional
faults (e.g., UPF receiving from internet but not forwarding).
    - **Drop means:** No traffic leaving UPF toward RAN.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE — constant regardless of UE pool size. Roughly symmetric with uplink during healthy calls.

- **`normalized.upf.gtp_indatapktn3upf_per_ue`** (GTP-U uplink rate per UE (N3)) — current **0.10 packets_per_second** vs learned baseline **3.44 packets_per_second** (MEDIUM, drop)
    - **What it measures:** Health of the uplink user-plane path gNB → UPF. Drops to near-zero
during RAN or N3 outage; stays nonzero during active calls or data
sessions. Decoupled from SIP signaling (signals data plane, not
control plane).
    - **Drop means:** Data plane dead on uplink — UPF receiving no packets from gNB.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE — constant regardless of UE pool size. Rises during active VoNR calls (~100 pps for G.711 voice) and data transfer.

- **`normalized.smf.bearers_per_ue`** (Active QoS bearers per UE) — current **4.00 count** vs learned baseline **2.59 count** (MEDIUM, spike)
    - **What it measures:** Per-UE count of active QoS bearers. Baseline reflects default
bearers; increments during VoNR calls indicate dedicated voice
bearers being set up. Drop during an active call = dedicated
bearer torn down unexpectedly (voice will fail).
    - **Spike means:** Expected during VoNR calls (1 extra bearer per active call).
    - **Healthy typical range:** 2–3.5 count
    - **Healthy invariant:** At rest: equals configured default bearers (typically 2 per UE).
During active VoNR call: +1 per caller. The per-UE ratio is the
invariant; absolute count scales with UE pool.

- **`normalized.pcscf.dialogs_per_ue`** (Active SIP dialogs per registered UE at P-CSCF) — current **0.00 count** vs learned baseline **0.59 count** (LOW, drop)
    - **What it measures:** How many calls per user are currently in progress at the P-CSCF.
Going to zero from a non-zero baseline means calls have ended
(normal) OR call setup is failing system-wide (degradation).
Together with rcv_requests_* it discriminates the two.
    - **Drop means:** No active calls. Normal at rest; suspicious if prior state had calls AND INVITE rate is also zero.
    - **Healthy typical range:** 0–1 count
    - **Healthy invariant:** Per-UE — scale-independent. 0 at rest, ~1 per active VoNR call.

- **`derived.upf_activity_during_calls`** — current **1.00** vs learned baseline **0.45** (LOW, spike). *(No KB context available — interpret from the metric name.)*


## Event Aggregation (Phase 1)

No events fired during this episode. Either no metric KB triggers matched, or the episode encountered no meaningful state transitions.

## Correlation Analysis (Phase 2)

No events fired — correlation engine had nothing to work with.

## Network Analysis (Phase 3)

**Summary:** P-CSCF is stalling SIP registrations due to an application-layer failure on its Rx interface to the PCF, causing a complete IMS outage.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | All containers and underlying network links are healthy. |
| **ran** | 🟢 GREEN | UEs are connected to the RAN and attached to the AMF. |
| **core** | 🟡 YELLOW | The user plane at the UPF is idle, but this is a symptom of upstream IMS control plane failures, not a root cause in the core. |
| **ims** | 🔴 RED | The IMS signaling chain is broken at the first hop. P-CSCF is stalling all SIP procedures, likely due to an application-level fault on its Rx interface to the PCF, preventing calls from being established. |

**CORE evidence:**
- normalized.upf.gtp_outdatapktn3upf_per_ue: drop to 0.15
- normalized.upf.gtp_indatapktn3upf_per_ue: drop to 0.10

**IMS evidence:**
- derived.pcscf_avg_register_time_ms: drop to 0.00 ms
- pcscf.httpclient:connfail: 427
- icscf.cdp:timeout: 3

**Ranked hypotheses:**

- **`h1`** (fit=0.95, nf=pcscf, specificity=specific):
    - **Statement:** The P-CSCF is failing to communicate with the PCF over the Rx interface, as shown by the high count of 'httpclient:connfail' metrics. This application-layer fault prevents P-CSCF from acquiring policy for SIP sessions, causing registrations to stall and leading to a system-wide inability to make calls.
    - **Falsification probes:**
        - Check PCF logs for errors corresponding to incoming Rx requests from P-CSCF.
        - Inspect the Rx interface configuration on both P-CSCF and PCF for a mismatch.
        - Restart the PCF container and observe if the 'httpclient:connfail' count on P-CSCF stops increasing.
- **`h2`** (fit=0.40, nf=icscf, specificity=moderate):
    - **Statement:** The I-CSCF has a specific connectivity issue to the HSS, causing Diameter timeouts on the Cx interface for UAR and LIR requests. This prevents it from routing registration requests to the S-CSCF. The issue does not affect the S-CSCF, which can still communicate with the HSS.
    - **Falsification probes:**
        - measure_rtt from 'icscf' to 'pyhss' shows no network latency, making a network partition unlikely.
        - The 'pcscf_bottleneck' causal chain suggests these timeouts are a cascading effect of an upstream P-CSCF stall, not an independent fault.
        - Check HSS logs for malformed Diameter requests specifically from the I-CSCF's IP address.


## Falsification Plans (Phase 4)

**2 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `pcscf`)

**Hypothesis:** The P-CSCF is failing to communicate with the PCF over the Rx interface, as shown by the high count of 'httpclient:connfail' metrics. This application-layer fault prevents P-CSCF from acquiring policy for SIP sessions, causing registrations to stall and leading to a system-wide inability to make calls.

**Probes (3):**
1. **`measure_rtt`** — from 'pcscf' to the 'pcf' container's IP
    - *Expected if hypothesis holds:* Clean RTT (<5ms) with no packet loss. The hypothesis states an application-layer fault, so the underlying network should be healthy.
    - *Falsifying observation:* High RTT or significant packet loss. This would indicate a network-layer issue is the cause, not an application-layer fault as hypothesized.
2. **`check_process_listeners`** — on the 'pcf' container
    - *Expected if hypothesis holds:* The PCF process is listening on the expected port for the Rx interface. This would confirm the PCF process is running and ready to accept connections.
    - *Falsifying observation:* The PCF process is not listening on the expected port. This would implicate the PCF container/process as the root cause, falsifying the hypothesis that the fault is primarily on the P-CSCF side.
3. **`get_nf_metrics`** — for the 'pcf' container
    - *Expected if hypothesis holds:* Metrics for incoming Rx requests on PCF (e.g., 'pcf_rx_requests_total' or equivalent) are zero or not increasing, confirming that P-CSCF's connection attempts are failing.
    - *Falsifying observation:* PCF's metrics show a steady rate of incoming Rx requests. This would prove P-CSCF is successfully communicating, directly falsifying the hypothesis.

*Notes:* This plan is designed to isolate the fault between the P-CSCF client, the network, and the PCF server. It starts by verifying the network layer is healthy before moving to application-level checks on the PCF side to see if it's ready and if it's receiving traffic.

### Plan for `h2` (target: `icscf`)

**Hypothesis:** The I-CSCF has a specific connectivity issue to the HSS, causing Diameter timeouts on the Cx interface for UAR and LIR requests. This prevents it from routing registration requests to the S-CSCF. The issue does not affect the S-CSCF, which can still communicate with the HSS.

**Probes (3):**
1. **`get_nf_metrics`** — for the 'scscf' container, focusing on Diameter metrics related to HSS communication
    - *Expected if hypothesis holds:* S-CSCF metrics show successful ongoing communication with the HSS (e.g., non-zero successful requests, zero timeouts).
    - *Falsifying observation:* S-CSCF metrics also show timeouts or errors communicating with the HSS. This would falsify the 'specific connectivity issue' aspect and point to a general problem with the HSS.
2. **`get_nf_metrics`** — for the 'icscf' container, focusing on incoming SIP REGISTER metrics
    - *Expected if hypothesis holds:* I-CSCF is receiving SIP REGISTER requests from P-CSCF, which it then fails to authorize with HSS.
    - *Falsifying observation:* I-CSCF metrics show zero or no increase in incoming SIP REGISTER requests. This would strongly suggest the I-CSCF timeouts are a symptom of an upstream stall at P-CSCF (per h1), not a primary fault, thus falsifying h2 as the root cause.
3. **`check_process_listeners`** — on the 'pyhss' container
    - *Expected if hypothesis holds:* The HSS process is running and listening on its Diameter Cx port, consistent with the problem being specific to the I-CSCF's connection.
    - *Falsifying observation:* The HSS process is not listening on the Diameter port. This would make the HSS itself the root cause of the timeouts, falsifying the hypothesis.

*Notes:* This plan focuses on testing the two main claims of the hypothesis: that the problem is *specific* to I-CSCF and not a general HSS failure, and that the I-CSCF fault is the primary bottleneck. The probes check the S-CSCF-HSS path for contrast and verify if I-CSCF is receiving any work to do in the first place.


## Parallel Investigators (Phase 5)

**2 sub-Investigator verdict(s):** **2 DISPROVEN**

### `h1` — ❌ **DISPROVEN**

**Hypothesis:** The P-CSCF is failing to communicate with the PCF over the Rx interface, as shown by the high count of 'httpclient:connfail' metrics. This application-layer fault prevents P-CSCF from acquiring policy for SIP sessions, causing registrations to stall and leading to a system-wide inability to make calls.

**Reasoning:** The hypothesis is disproven because evidence shows that communication between P-CSCF and PCF has not completely failed. While P-CSCF metrics show a high number of connection failures, PCF metrics confirm that it is successfully receiving and processing policy requests. This contradicts the hypothesis's central claim that the fault 'prevents P-CSCF from acquiring policy'.

**Probes executed (3):**
- **from 'pcscf' to the 'pcf' container's IP** ✓ CONSISTENT
    - *Tool:* `measure_rtt("pcscf", "172.22.0.27")`
    - *Observation:* [EVIDENCE: measure_rtt("pcscf", "172.22.0.27") -> "3 packets transmitted, 3 received, 0% packet loss... rtt min/avg/max/mdev = 0.074/0.148/0.275/0.089 ms"]
    - *Comment:* The RTT is extremely low and there is no packet loss, confirming the network layer is healthy. This aligns with the hypothesis's claim of an application-layer fault, but does not help distinguish the cause.
- **on the 'pcf' container** ✓ CONSISTENT
    - *Tool:* `check_process_listeners("pcf")`
    - *Observation:* [EVIDENCE: check_process_listeners("pcf") -> "tcp   LISTEN 0      4096     172.22.0.27:9091       0.0.0.0:*    users:(('open5gs-pcfd',pid=8,fd=10))\ntcp   LISTEN 0      5        172.22.0.27:7777       0.0.0.0:*    users:(('open5gs-pcfd',pid=8,fd=12))"]
    - *Comment:* The PCF process 'open5gs-pcfd' is actively listening on TCP ports, indicating the server process is up and ready to accept connections.
- **for the 'pcf' container** ✗ CONTRADICTS
    - *Tool:* `get_nf_metrics()`
    - *Observation:* [EVIDENCE: get_nf_metrics() -> "PCF ... fivegs_pcffunction_pa_policyamassoreq = 10.0 [counter] ... fivegs_pcffunction_pa_policyamassosucc = 10.0 [counter]"]
    - *Comment:* This directly falsifies the hypothesis. The PCF's metrics show it has received (policyamassoreq=10) and successfully processed (policyamassosucc=10) policy association requests. This proves that P-CSCF is, at least intermittently, able to communicate and acquire policy, contradicting the core assertion of the hypothesis.

**Alternative suspects:** pcf

### `h2` — ❌ **DISPROVEN**

**Hypothesis:** The I-CSCF has a specific connectivity issue to the HSS, causing Diameter timeouts on the Cx interface for UAR and LIR requests. This prevents it from routing registration requests to the S-CSCF. The issue does not affect the S-CSCF, which can still communicate with the HSS.

**Reasoning:** Probe 2 revealed that the upstream P-CSCF is experiencing a massive number of connection failures and is therefore not sending SIP REGISTER requests to the I-CSCF. This means the I-CSCF is starved and its Diameter timeouts are a symptom of an upstream stall, not the root cause of the outage. The evidence points to the P-CSCF being the primary suspect.

**Probes executed (3):**
- **for the 'scscf' container, focusing on Diameter metrics related to HSS communication** ✓ CONSISTENT
    - *Tool:* `get_nf_metrics()`
    - *Observation:* [EVIDENCE: get_nf_metrics() -> "scscf: ... cdp:timeout = 0.0, ... cdp:replies_received = 16.0, ... ims_auth:mar_timeouts = 0.0, ... ims_registrar_scscf:sar_timeouts = 0.0"]
    - *Comment:* The S-CSCF metrics show successful communication with the HSS (zero timeouts, non-zero replies), which is consistent with the hypothesis's claim that the connectivity issue is specific to the I-CSCF.
- **for the 'icscf' container, focusing on incoming SIP REGISTER metrics** ✗ CONTRADICTS
    - *Tool:* `get_nf_metrics()`
    - *Observation:* [EVIDENCE: get_nf_metrics() -> "pcscf: ... httpclient:connfail = 452.0 ... icscf: ... core:rcv_requests_register = 21.0"]
    - *Comment:* This falsifies the hypothesis. The high 'httpclient:connfail' count on the P-CSCF indicates it's failing before it can send requests to the I-CSCF. Therefore, the I-CSCF is not receiving new requests to process, meaning its timeouts are not the primary fault. The problem lies upstream.
- **on the 'pyhss' container** ~ AMBIGUOUS
    - *Tool:* `check_process_listeners("pyhss")`
    - *Observation:* [EVIDENCE: check_process_listeners("pyhss") -> "Neither ss nor netstat available in pyhss. Output: OCI runtime exec failed: exec failed: unable to start container process: exec: \"netstat\": executable file not found in $PATH: unknown"]
    - *Comment:* The tool could not run inside the container, so it's impossible to determine if the HSS process is listening on its Diameter port. This probe is inconclusive.

**Alternative suspects:** pcscf


## Evidence Validation (Phase 6)

**Overall verdict:** clean
**Overall confidence:** high

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 4 | 3/3 | clean | high |
| `InvestigatorAgent_h2` | 2 | 3/3 | clean | high |


## Ground Truth

**Failure domain:** ims_signaling  
**Protocol impact:** SIP  
**Affected components:** pcscf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v6-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 195.2s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: The initial hypotheses were disproven; investigation reveals a severe application-layer fault between the P-CSCF and PCF, where the PCF appears to be incorrectly handling connections, causing the P-CSCF to stall and fail all SIP registrations.
> - **timeline**:
>     1. The P-CSCF begins experiencing a very high rate of connection failures (`httpclient:connfail=452`) when attempting to contact the PCF for policy information.
>     2. While a small number of policy requests succeed (`policyamassosucc=10`), the vast majority of connection attempts fail, causing the P-CSCF to stall incoming SIP REGISTER requests.
>     3. Downstream components like the I-CSCF become idle due to the halt in traffic from the P-CSCF, leading to secondary timeouts.
>     4. The IMS control plane is broken at the first hop, preventing any UEs from completing registration and causing a complete outage.
> - **root_cause**: The original hypotheses were disproven. The evidence points to an application-level fault in the `pcf`. While the PCF process is running and reports some successful policy transactions, the massive number of connection failures reported by its client (the P-CSCF) suggests the PCF is incorrectly rejecting or dropping the vast majority of incoming Rx requests. This starves the P-CSCF of the policy information it needs to process SIP registrations, halting the entire IMS signaling chain.
> - **affected_components**:
>     - `pcf`: Root Cause
>     - `pcscf`: Secondary (Directly impacted by PCF fault, stalling all SIP procedures)
>     - `icscf`: Symptomatic (Starved of traffic due to the upstream P-CSCF stall)
> - **recommendation**: Investigate the PCF container logs for any errors or warnings related to connection handling, resource exhaustion, or malformed requests. Concurrently, inspect the P-CSCF logs to understand the nature of the 'httpclient:connfail' errors. Comparing logs from both sides for corresponding timestamps should clarify which component is initiating the connection termination.
> - **confidence**: low
> - **explanation**: The investigation disproved both initial hypotheses. Hypothesis `h2` (I-CSCF fault) was invalidated when evidence showed the I-CSCF was simply starved of traffic from an upstream failure at the P-CSCF. Hypothesis `h1` (P-CSCF to PCF communication failure) was disproven by PCF metrics confirming it had successfully received and processed some policy requests. This contradicts the idea of a total communication breakdown. The resulting picture points to a degraded state, not a complete failure. The most likely cause is an application fault in the PCF that causes it to reject most, but not all, connections. Confidence is low because both primary hypotheses were falsified, and this new conclusion is an inference based on reconciling the conflicting evidence.

### Scoring Breakdown

**Overall score: 36%**

**Scorer assessment:** The agent correctly identified the severity and the affected layer, and its low confidence was appropriate given the incorrect diagnosis. However, it completely missed the actual root cause and fault type, misattributing the issue to an application fault in the PCF instead of a network partition affecting the P-CSCF.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | No | The simulated failure was a network partition isolating the P-CSCF from the I-CSCF and S-CSCF. The agent diagnosed an application-level fault in the PCF causing the P-CSCF to stall due to rejected Rx requests. This is a different component (PCF vs I/S-CSCF) and a different type of fault (application fault vs network partition). |
| Component overlap | 30% | The primary affected component in the simulated failure was the P-CSCF. The agent listed 'pcscf' in its 'affected_components' but as 'Secondary', while incorrectly identifying 'pcf' as the 'Root Cause'. This indicates partial identification but a mis-ranking of the causal role. |
| Severity correct | Yes | The simulated failure resulted in SIP signaling being 'completely severed' and new registrations failing, indicating a complete outage. The agent's diagnosis correctly states 'fail all SIP registrations' and 'causing a complete outage'. |
| Fault type identified | No | The simulated failure was a 'Network partition'. The agent identified an 'application-level fault' in the PCF causing 'incorrectly rejecting or dropping' requests, which is not a network partition. |
| Layer accuracy | Yes | The primary affected component, P-CSCF, belongs to the 'ims' layer. The agent's network analysis correctly rated the 'ims' layer as 'red'. |
| Confidence calibrated | Yes | The agent's diagnosis for the root cause and fault type was incorrect. However, the agent explicitly stated 'confidence: low' and explained that 'both primary hypotheses were falsified, and this new conclusion is an inference based on reconciling the conflicting evidence', indicating appropriate calibration given the incorrect diagnosis. |

**Ranking:** The agent provided a single root cause in its final diagnosis, which was incorrect.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 139,118 |
| Output tokens | 4,480 |
| Thinking tokens | 16,333 |
| **Total tokens** | **159,931** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| EventAggregator | 0 | 0 | 0 |
| CorrelationAnalyzer | 0 | 0 | 0 |
| NetworkAnalystAgent | 62,985 | 8 | 4 |
| InstructionGeneratorAgent | 21,728 | 1 | 2 |
| InvestigatorAgent_h1 | 34,015 | 4 | 3 |
| InvestigatorAgent_h2 | 35,199 | 2 | 3 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 6,004 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 333.0s
