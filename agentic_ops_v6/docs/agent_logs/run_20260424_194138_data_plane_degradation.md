# Episode Report: Data Plane Degradation

**Agent:** v6  
**Episode ID:** ep_20260424_193706_data_plane_degradation  
**Date:** 2026-04-24T19:37:08.391180+00:00  
**Duration:** 269.2s  

---

## Scenario

**Category:** network  
**Blast radius:** single_nf  
**Description:** Inject 30% packet loss on the UPF. RTP media streams will degrade, voice quality drops. Tests whether the stack detects and reports data plane quality issues.

## Faults Injected

- **network_loss** on `upf` — {'loss_pct': 30}

## Baseline (Pre-Fault)

Stack phase before injection: **ready**
All containers running at baseline.

## Fault Propagation Verification

**Verdict:** ✅ `confirmed`

- **Wait:** 0s
- **Actual elapsed:** 0.0s
- **Nodes with significant deltas:** 4
- **Nodes with any drift:** 6

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 0.99 (threshold: 0.70, trained on 209 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following metrics deviate from their learned-healthy baseline. Treat each as a semantic observation (meaning + numbers), not a number alone — the KB's interpretation is the authoritative reading.

- **`icscf.cdp:average_response_time`** (I-CSCF Diameter average response time) — current **69.00 ms** vs learned baseline **61.05 ms** (HIGH, shift)
    - **What it measures:** Responsiveness of the Cx path and HSS processing speed. A spike
without timeouts = pure latency; a spike WITH timeout_ratio rising
= approaching timeout ceiling (HSS overload or partial partition).
    - **Shift means:** HSS slow, network latency to HSS, or HSS overload.
    - **Healthy typical range:** 30–100 ms

- **`derived.upf_activity_during_calls`** — current **1.00** vs learned baseline **0.09** (HIGH, spike). *(No KB context available — interpret from the metric name.)*

- **`icscf.ims_icscf:uar_avg_response_time`** (I-CSCF UAR response time) — current **67.00 ms** vs learned baseline **62.50 ms** (HIGH, shift)
    - **What it measures:** Specifically the UAR leg of the Cx interface. Spikes here without
LIR spikes are unusual — either UAR-handler issue at HSS or
specific network path to that code path.
    - **Shift means:** UAR-specific HSS slowness.
    - **Healthy typical range:** 30–100 ms

- **`normalized.upf.gtp_outdatapktn3upf_per_ue`** (GTP-U downlink rate per UE (N3)) — current **0.15 packets_per_second** vs learned baseline **6.08 packets_per_second** (HIGH, drop)
    - **What it measures:** Health of the downlink user-plane path UPF → gNB. Typically mirrors
uplink rate during calls/data; asymmetry indicates directional
faults (e.g., UPF receiving from internet but not forwarding).
    - **Drop means:** No traffic leaving UPF toward RAN.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE — constant regardless of UE pool size. Roughly symmetric with uplink during healthy calls.

- **`normalized.upf.gtp_indatapktn3upf_per_ue`** (GTP-U uplink rate per UE (N3)) — current **0.12 packets_per_second** vs learned baseline **6.15 packets_per_second** (HIGH, drop)
    - **What it measures:** Health of the uplink user-plane path gNB → UPF. Drops to near-zero
during RAN or N3 outage; stays nonzero during active calls or data
sessions. Decoupled from SIP signaling (signals data plane, not
control plane).
    - **Drop means:** Data plane dead on uplink — UPF receiving no packets from gNB.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE — constant regardless of UE pool size. Rises during active VoNR calls (~100 pps for G.711 voice) and data transfer.

- **`icscf.ims_icscf:lir_avg_response_time`** (I-CSCF LIR response time) — current **74.00 ms** vs learned baseline **58.57 ms** (HIGH, shift)
    - **What it measures:** Call-routing-specific Cx leg. If LIR is healthy but UAR is slow,
registration path has a specific issue separate from call routing.
    - **Shift means:** HSS slow to respond to LIR; affects call setup.
    - **Healthy typical range:** 30–100 ms

- **`derived.pcscf_avg_register_time_ms`** (P-CSCF average SIP REGISTER processing time) — current **0.00 ms** vs learned baseline **160.42 ms** (HIGH, drop)
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

- **`normalized.smf.bearers_per_ue`** (Active QoS bearers per UE) — current **2.50 count** vs learned baseline **4.15 count** (MEDIUM, shift)
    - **What it measures:** Per-UE count of active QoS bearers. Baseline reflects default
bearers; increments during VoNR calls indicate dedicated voice
bearers being set up. Drop during an active call = dedicated
bearer torn down unexpectedly (voice will fail).
    - **Shift means:** Expected during VoNR calls (1 extra bearer per active call).
    - **Healthy typical range:** 2–3.5 count
    - **Healthy invariant:** At rest: equals configured default bearers (typically 2 per UE).
During active VoNR call: +1 per caller. The per-UE ratio is the
invariant; absolute count scales with UE pool.

- **`normalized.pcscf.dialogs_per_ue`** (Active SIP dialogs per registered UE at P-CSCF) — current **0.00 count** vs learned baseline **1.58 count** (MEDIUM, drop)
    - **What it measures:** How many calls per user are currently in progress at the P-CSCF.
Going to zero from a non-zero baseline means calls have ended
(normal) OR call setup is failing system-wide (degradation).
Together with rcv_requests_* it discriminates the two.
    - **Drop means:** No active calls. Normal at rest; suspicious if prior state had calls AND INVITE rate is also zero.
    - **Healthy typical range:** 0–1 count
    - **Healthy invariant:** Per-UE — scale-independent. 0 at rest, ~1 per active VoNR call.


## Event Aggregation (Phase 1)

No events fired during this episode. Either no metric KB triggers matched, or the episode encountered no meaningful state transitions.

## Correlation Analysis (Phase 2)

No events fired — correlation engine had nothing to work with.

## Network Analysis (Phase 3)

**Summary:** IMS registration is failing due to severe latency and timeouts on the Diameter Cx interface, leading to an inability to establish calls and a silent data plane.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | All containers are running and all network links between components are active. The issue does not appear to be at the infrastructure level. |
| **ran** | 🟢 GREEN | The AMF reports that UEs are connected to the RAN. The issue is upstream from the RAN. |
| **core** | 🟡 YELLOW | The user plane is inactive, with GTP traffic rates at both UPF and RAN sides near zero. This is likely a consequence of control plane failures preventing call setup, rather than a root cause in the core. Bearer count is low. |
| **ims** | 🔴 RED | The IMS stack is the clear epicenter. P-CSCF shows a registration stall, I-CSCF is experiencing Diameter timeouts, and both I-CSCF and S-CSCF show high Diameter latency towards the HSS. No SIP dialogs are active. |

**CORE evidence:**
- normalized.upf.gtp_indatapktn3upf_per_ue
- normalized.upf.gtp_outdatapktn3upf_per_ue
- normalized.smf.bearers_per_ue

**IMS evidence:**
- derived.pcscf_avg_register_time_ms
- icscf.cdp:average_response_time
- icscf.ims_icscf:uar_avg_response_time
- icscf.ims_icscf:lir_avg_response_time
- icscf.cdp:timeout
- normalized.pcscf.dialogs_per_ue

**Ranked hypotheses:**

- **`h1`** (fit=0.90, nf=pyhss, specificity=specific):
    - **Statement:** The HSS is overloaded or experiencing a processing slowdown, causing high latency on all Diameter Cx interface queries and leading to timeouts for clients with stricter timer configurations like the I-CSCF. This is causing SIP registration to fail and preventing any calls from being established.
    - **Supporting events:** `icscf.cdp:average_response_time`, `icscf.ims_icscf:uar_avg_response_time`, `icscf.ims_icscf:lir_avg_response_time`, `icscf.cdp:timeout`, `derived.pcscf_avg_register_time_ms`
    - **Falsification probes:**
        - Run `measure_rtt('icscf', 'pyhss')` and `measure_rtt('scscf', 'pyhss')`. If RTTs are low (< 10ms), the network is not the source of latency, pointing to the HSS application.
        - Query HSS internal metrics for CPU utilization, memory, or queue depth. If the HSS reports itself as healthy and unloaded, this hypothesis is likely false.
- **`h2`** (fit=0.70, nf=pcscf, specificity=specific):
    - **Statement:** The P-CSCF is experiencing an internal processing stall, preventing it from completing SIP registration transactions. This is indicated by the `derived.pcscf_avg_register_time_ms` dropping to zero, a classic stall signature. This stall may be causing a backup or retransmission storm that manifests as latency and timeouts downstream at the I-CSCF and HSS.
    - **Supporting events:** `derived.pcscf_avg_register_time_ms`, `normalized.pcscf.dialogs_per_ue`
    - **Falsification probes:**
        - Check the internal logs of the P-CSCF container for error messages or signs of resource exhaustion.
        - Confirm via direct probes (see h1) that the HSS is healthy and responsive. If the HSS is slow, the P-CSCF is more likely a victim.
- **`h3`** (fit=0.40, nf=icscf, specificity=moderate):
    - **Statement:** There is a specific network issue causing high latency or packet loss on the path between the I-CSCF and the HSS. This explains why the I-CSCF is experiencing Diameter timeouts while the S-CSCF is not, although it does not fully explain why the S-CSCF also sees elevated latency.
    - **Supporting events:** `icscf.cdp:timeout`, `icscf.ims_icscf:uar_timeouts`, `icscf.ims_icscf:lir_timeouts`
    - **Falsification probes:**
        - Run `measure_rtt('icscf', 'pyhss')`. If RTT is low and shows no packet loss, this hypothesis is false.
        - Run `measure_rtt('scscf', 'pyhss')`. If this path also shows high latency, it points away from a localized I-CSCF path issue and towards a general HSS problem (h1).


## Falsification Plans (Phase 4)

*No output produced.*

## Parallel Investigators (Phase 5)

**3 sub-Investigator verdict(s):** **3 INCONCLUSIVE**

### `h1` — ❓ **INCONCLUSIVE**

**Hypothesis:** The HSS is overloaded or experiencing a processing slowdown, causing high latency on all Diameter Cx interface queries and leading to timeouts for clients with stricter timer configurations like the I-CSCF. This is causing SIP registration to fail and preventing any calls from being established.

**Reasoning:** No falsification plan was generated for this hypothesis.

### `h2` — ❓ **INCONCLUSIVE**

**Hypothesis:** The P-CSCF is experiencing an internal processing stall, preventing it from completing SIP registration transactions. This is indicated by the `derived.pcscf_avg_register_time_ms` dropping to zero, a classic stall signature. This stall may be causing a backup or retransmission storm that manifests as latency and timeouts downstream at the I-CSCF and HSS.

**Reasoning:** No falsification plan was generated for this hypothesis.

### `h3` — ❓ **INCONCLUSIVE**

**Hypothesis:** There is a specific network issue causing high latency or packet loss on the path between the I-CSCF and the HSS. This explains why the I-CSCF is experiencing Diameter timeouts while the S-CSCF is not, although it does not fully explain why the S-CSCF also sees elevated latency.

**Reasoning:** No falsification plan was generated for this hypothesis.


## Evidence Validation (Phase 6)

**Overall verdict:** severe
**Overall confidence:** none

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 0 | 0/0 | severe | none |
|  |  |  |  | *ZERO tool calls — all citations fabricated* |
| `InvestigatorAgent_h2` | 0 | 0/0 | severe | none |
|  |  |  |  | *ZERO tool calls — all citations fabricated* |
| `InvestigatorAgent_h3` | 0 | 0/0 | severe | none |
|  |  |  |  | *ZERO tool calls — all citations fabricated* |


## Ground Truth

**Failure domain:** data_plane  
**Protocol impact:** GTP-U  
**Affected components:** upf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v6-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 132.6s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: IMS registration is failing due to severe Diameter Cx interface latency, but a conclusive root cause could not be determined because the automated investigation failed to validate its hypotheses.
> - **timeline**:
>     1. High Diameter latency was observed for queries from the S-CSCF and I-CSCF towards the HSS (`icscf.cdp:average_response_time`, `icscf.ims_icscf:uar_avg_response_time`).
>     2. The I-CSCF began experiencing Diameter timeouts (`icscf.cdp:timeout`), indicating its timers were expiring before receiving responses from the HSS.
>     3. SIP registration attempts from UEs began to fail at the P-CSCF, which showed a registration processing stall (`derived.pcscf_avg_register_time_ms`).
>     4. As a result of registration failure, no SIP dialogs were established, and user plane traffic on the core network dropped to zero.
> - **root_cause**: The investigation was inconclusive. The leading hypothesis suggests a processing slowdown or overload in the **pyhss (HSS)**, causing high latency on Diameter Cx queries. This could not be verified.
> - **affected_components**:
>     - `pyhss`: Primary Suspect (Unverified)
>     - `icscf`: Secondary (Experiencing timeouts)
>     - `scscf`: Secondary (Experiencing high latency)
>     - `pcscf`: Symptomatic (Registration failing)
>     - `upf`: Symptomatic (No user plane traffic)
> - **recommendation**: The automated investigation failed to execute any verification steps. An operator should manually execute the probes from the original hypotheses to isolate the source of latency.
>     1.  Verify network round-trip time between the Diameter clients and the HSS by running `measure_rtt('icscf', 'pyhss')` and `measure_rtt('scscf', 'pyhss')`. If RTT is low, the network path is not the cause of latency.
>     2.  Investigate the HSS (`pyhss`) container's internal health. Check its logs, CPU and memory utilization, and any internal queue depth metrics for signs of overload or processing errors.
>     3.  Check the P-CSCF (`pcscf`) logs for error messages that could explain its registration stall.
> - **confidence**: low
> - **explanation**: The investigation was unable to determine a root cause due to a critical failure in the automated evidence gathering process. The most plausible hypothesis (`h1`), though unverified, suggests the HSS is overloaded, causing severe Diameter Cx latency and subsequent timeouts at the I-CSCF. This prevents IMS registration, leading to a silent data plane. The other hypotheses involving a P-CSCF stall (`h2`) or a localized network issue (`h3`) were also not tested. **Crucially, the Evidence Validator reported that the investigation agents failed to run any diagnostic commands, making their verdicts unreliable.** Manual verification is required to confirm whether the HSS application is the source of the slowdown.

### Scoring Breakdown

**Overall score: 17%**

**Scorer assessment:** The agent completely misidentified the root cause, fault type, and severity, focusing on IMS control plane issues instead of the data plane packet loss. However, it did correctly flag the core layer as having an issue and appropriately expressed low confidence in its inconclusive diagnosis.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | No | The simulated failure was 30% packet loss on the UPF (data plane degradation). The agent's diagnosis focused on IMS registration failures due to HSS latency and an inconclusive root cause, completely missing the data plane packet loss on the UPF. |
| Component overlap | 10% | The primary affected component was the UPF. The agent listed 'upf' in its 'affected_components' but only as 'Symptomatic' and attributed the primary suspect role to 'pyhss (HSS)'. This indicates a very low overlap in identifying the causal role of the correct component. |
| Severity correct | No | The simulated failure was a degradation (30% packet loss). The agent described a complete service outage ('IMS registration is failing', 'no SIP dialogs were established', 'user plane traffic on the core network dropped to zero'), which is a higher severity than the actual degradation. |
| Fault type identified | No | The simulated fault type was 'packet loss'. The agent identified 'latency' and 'timeouts' as the primary fault types, leading to a service outage, but did not mention packet loss. |
| Layer accuracy | Yes | The UPF belongs to the 'core' layer. The agent's network analysis correctly rated the 'core' layer as 'yellow', indicating an issue within that layer, even though its interpretation of the root cause within that layer was incorrect. |
| Confidence calibrated | Yes | The agent's diagnosis was completely incorrect, and it appropriately stated 'confidence: low' and that the 'investigation was inconclusive' due to failed verification steps. This shows good calibration. |

**Ranking:** The correct root cause (UPF packet loss) was not identified as a root cause or leading hypothesis; it was only listed as a symptomatic component.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 43,894 |
| Output tokens | 2,071 |
| Thinking tokens | 10,248 |
| **Total tokens** | **56,213** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| EventAggregator | 0 | 0 | 0 |
| CorrelationAnalyzer | 0 | 0 | 0 |
| NetworkAnalystAgent | 42,462 | 4 | 3 |
| InstructionGeneratorAgent | 9,009 | 0 | 1 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 4,742 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 269.2s
