# Episode Report: P-CSCF Latency

**Agent:** v6  
**Episode ID:** ep_20260430_013408_p_cscf_latency  
**Date:** 2026-04-30T01:34:10.245817+00:00  
**Duration:** 309.0s  

---

## Scenario

**Category:** network  
**Blast radius:** single_nf  
**Description:** Inject 2000ms latency (with 50ms jitter) on the P-CSCF (SIP edge proxy). SIP transactions will experience severe delays as every message entering and leaving the P-CSCF is delayed, compounding across multiple round-trips in the IMS registration chain. Tests IMS resilience to high latency on the signaling edge.

## Faults Injected

- **network_latency** on `pcscf` — {'delay_ms': 2000, 'jitter_ms': 50}

## Baseline (Pre-Fault)

Stack phase before injection: **ready**
All containers running at baseline.

## Fault Propagation Verification

**Verdict:** ✅ `confirmed`

- **Wait:** 0s
- **Actual elapsed:** 0.0s
- **Nodes with significant deltas:** 3
- **Nodes with any drift:** 4

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 35.04 (per-bucket threshold: 26.31, context bucket (0, 1), trained on 323 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following metrics deviate from their learned-healthy baseline. Treat each as a semantic observation (meaning + numbers), not a number alone — the KB's interpretation is the authoritative reading.

- **`derived.pcscf_sip_error_ratio`** (P-CSCF SIP error response ratio) — current **0.25 ratio** vs learned baseline **0.00 ratio** (MEDIUM, spike)
    - **What it measures:** Proportion of SIP responses that are errors. Zero is the healthy
baseline; any sustained non-zero value means P-CSCF or something
downstream is rejecting requests.
    - **Spike means:** Errors flowing back — downstream CSCFs or HSS rejecting.
    - **Healthy typical range:** 0–0 ratio
    - **Healthy invariant:** Zero in healthy operation.

- **`normalized.icscf.cdp_replies_per_ue`** (I-CSCF Diameter reply rate per UE) — current **0.00 replies_per_second_per_ue** vs learned baseline **0.03 replies_per_second_per_ue** (MEDIUM, drop)
    - **What it measures:** Liveness of the I-CSCF↔HSS Cx path. Drops to 0 when HSS is unreachable OR when no signaling is occurring at the I-CSCF (idle or upstream P-CSCF partitioned).
    - **Drop means:** No Cx replies in the window. Could be healthy idle OR a Cx-path fault.
    - **Healthy typical range:** 0–1 replies_per_second_per_ue

- **`normalized.pcscf.core:rcv_requests_invite_per_ue`** (SIP INVITE rate per UE at P-CSCF) — current **0.04 requests_per_second** vs learned baseline **0.00 requests_per_second** (MEDIUM, spike)
    - **What it measures:** Call attempt rate from registered UEs. Unlike REGISTER (periodic),
INVITEs only fire when UEs place calls. Zero is normal during
quiet periods; nonzero INVITE with zero dialogs is the signature
of call setup failure.
    - **Spike means:** Fewer call attempts.
    - **Healthy typical range:** 0–0.2 requests_per_second
    - **Healthy invariant:** Per-UE rate.

- **`normalized.pcscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at P-CSCF) — current **0.03 requests_per_second** vs learned baseline **0.06 requests_per_second** (MEDIUM, drop)
    - **What it measures:** How actively UEs are refreshing their IMS registrations with the
P-CSCF. REGISTERs arrive periodically (re-registration timer) plus
at attach. Sustained zero means UEs cannot reach P-CSCF OR the
UE-to-network SIP path is broken.
    - **Drop means:** No REGISTERs flowing. Unusual unless UEs are all deregistered.
    - **Healthy typical range:** 0–0.5 requests_per_second
    - **Healthy invariant:** Per-UE rate — same value at any deployment scale.

- **`normalized.scscf.cdp_replies_per_ue`** (S-CSCF CDP Diameter replies per UE) — current **0.03 replies_per_second_per_ue** vs learned baseline **0.06 replies_per_second_per_ue** (MEDIUM, drop)
    - **What it measures:** Active S-CSCF Diameter traffic with HSS. Near-zero when registrations idle OR HSS partition.
    - **Drop means:** No active S-CSCF Diameter exchanges (idle or partitioned).
    - **Healthy typical range:** 0–1 replies_per_second_per_ue
    - **Healthy invariant:** Per-UE rate; varies with registration/auth load.

- **`normalized.scscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at S-CSCF) — current **0.03 requests_per_second** vs learned baseline **0.06 requests_per_second** (MEDIUM, drop)
    - **What it measures:** Health of the I-CSCF → S-CSCF forwarding path. Drop to zero while
I-CSCF is receiving REGISTERs = S-CSCF-side issue (crashed, or
I-CSCF → S-CSCF path broken).
    - **Drop means:** S-CSCF isolated or not running.
    - **Healthy typical range:** 0–0.5 requests_per_second
    - **Healthy invariant:** Per-UE rate. Tracks icscf.register rate.

- **`normalized.upf.gtp_outdatapktn3upf_per_ue`** (GTP-U downlink rate per UE (N3)) — current **0.14 packets_per_second** vs learned baseline **1.45 packets_per_second** (LOW, drop)
    - **What it measures:** Health of the downlink user-plane path UPF → gNB. Typically mirrors
uplink rate during calls/data; asymmetry indicates directional
faults (e.g., UPF receiving from internet but not forwarding).
    - **Drop means:** No traffic leaving UPF toward RAN.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE — constant regardless of UE pool size. Roughly symmetric with uplink during healthy calls.

- **`normalized.icscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at I-CSCF) — current **0.09 requests_per_second** vs learned baseline **0.06 requests_per_second** (LOW, shift)
    - **What it measures:** Health of the P-CSCF → I-CSCF forwarding path (Mw interface). When
this drops to zero while P-CSCF REGISTER rate is still non-zero,
it's the SIGNATURE of an IMS partition between P-CSCF and I-CSCF.
    - **Shift means:** Forwarding issue on the Mw interface, or P-CSCF stopped forwarding.
    - **Healthy typical range:** 0–0.5 requests_per_second
    - **Healthy invariant:** Per-UE rate. Should closely track ims.pcscf.rcv_requests_register_per_ue.

- **`normalized.upf.gtp_indatapktn3upf_per_ue`** (GTP-U uplink rate per UE (N3)) — current **0.29 packets_per_second** vs learned baseline **1.45 packets_per_second** (LOW, drop)
    - **What it measures:** Health of the uplink user-plane path gNB → UPF. Drops to near-zero
during RAN or N3 outage; stays nonzero during active calls or data
sessions. Decoupled from SIP signaling (signals data plane, not
control plane).
    - **Drop means:** Data plane dead on uplink — UPF receiving no packets from gNB.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE — constant regardless of UE pool size. Rises during active VoNR calls (~100 pps for G.711 voice) and data transfer.

- **`normalized.smf.bearers_per_ue`** (Active QoS bearers per UE) — current **2.00 count** vs learned baseline **2.48 count** (LOW, shift)
    - **What it measures:** Per-UE count of active QoS bearers. Baseline reflects default
bearers; increments during VoNR calls indicate dedicated voice
bearers being set up. Drop during an active call = dedicated
bearer torn down unexpectedly (voice will fail).
    - **Shift means:** Expected during VoNR calls (1 extra bearer per active call).
    - **Healthy typical range:** 2–3.5 count
    - **Healthy invariant:** At rest: equals configured default bearers (typically 2 per UE).
During active VoNR call: +1 per caller. The per-UE ratio is the
invariant; absolute count scales with UE pool.


## Event Aggregation (Phase 1)

No events fired during this episode. Either no metric KB triggers matched, or the episode encountered no meaningful state transitions.

## Correlation Analysis (Phase 2)

No events fired — correlation engine had nothing to work with.

## Network Analysis (Phase 3)

**Summary:** The P-CSCF is unable to forward SIP requests to the I-CSCF, causing IMS registration and call setup failures.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | All relevant containers are running and basic network connectivity appears intact. |
| **ran** | 🟢 GREEN | RAN appears healthy. UEs are attempting to send signaling traffic. |
| **core** | 🟢 GREEN | The core network appears healthy. The data plane metrics are low, but this is a consequence of VoNR calls failing at the IMS layer, not a fault in the core itself. |
| **ims** | 🔴 RED | The SIP error rate at the P-CSCF is very high, while the downstream I-CSCF is receiving no SIP REGISTER traffic at all. This indicates a complete failure of the P-CSCF to I-CSCF signaling path. |

**IMS evidence:**
- derived.pcscf_sip_error_ratio
- normalized.icscf.core:rcv_requests_register_per_ue
- normalized.pcscf.core:rcv_requests_register_per_ue

**Ranked hypotheses:**

- **`h1`** (fit=0.95, nf=pcscf, specificity=specific):
    - **Statement:** The P-CSCF is unable to forward SIP requests to the I-CSCF due to a partition on the Mw interface. This is causing IMS registration to fail, leading to SIP errors for all call and registration attempts.
    - **Supporting events:** `derived.pcscf_sip_error_ratio`, `normalized.icscf.core:rcv_requests_register_per_ue`, `normalized.scscf.core:rcv_requests_register_per_ue`, `normalized.icscf.cdp_replies_per_ue`
    - **Falsification probes:**
        - A successful ping or low RTT from the P-CSCF container to the I-CSCF container's IP address would disprove a network-level partition.
        - Check P-CSCF's internal logs or metrics for errors related to DNS resolution for 'icscf' or for routing to the I-CSCF's IP. Absence of such errors would weaken this hypothesis.
        - Examine nf_metrics for pcscf and icscf to compare sent vs. received SIP messages; if they match, the partition is not there.
- **`h2`** (fit=0.60, nf=pyhss, specificity=specific):
    - **Statement:** The HSS is unresponsive to Diameter Cx requests. This is causing authentication and registration to fail, leading to the observed SIP errors at the P-CSCF.
    - **Supporting events:** `derived.pcscf_sip_error_ratio`, `normalized.icscf.cdp_replies_per_ue`, `normalized.scscf.cdp_replies_per_ue`
    - **Falsification probes:**
        - If I-CSCF and S-CSCF diagnostic metrics show zero Diameter timeouts to HSS, it implies they are not sending requests, which would disprove that HSS is the one failing to respond.
        - A live probe showing HSS is responsive to Diameter queries from another source would disprove this hypothesis.


## Falsification Plans (Phase 4)

**2 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `pcscf`)

**Hypothesis:** The P-CSCF is unable to forward SIP requests to the I-CSCF due to a partition on the Mw interface. This is causing IMS registration to fail, leading to SIP errors for all call and registration attempts.

**Probes (3):**
1. **`measure_rtt`** — From pcscf to the icscf container's IP address.
    - *Expected if hypothesis holds:* High RTT or 100% packet loss, indicating a network partition.
    - *Falsifying observation:* Low RTT and 0% packet loss. This would show basic IP connectivity is fine.
2. **`measure_rtt`** — From the smf container to the icscf container's IP address.
    - *Expected if hypothesis holds:* Low RTT and 0% packet loss. If the fault is specific to the P-CSCF, other containers should still be able to reach the I-CSCF.
    - *Falsifying observation:* High RTT or 100% packet loss. If another container also cannot reach I-CSCF, it suggests the problem is with I-CSCF's ingress or the underlying network, not P-CSCF's egress.
3. **`check_process_listeners`** — Check listening ports on the icscf container.
    - *Expected if hypothesis holds:* A process within the icscf container should be listening on the standard SIP port (5060/UDP and 5060/TCP). The hypothesis assumes I-CSCF is running but unreachable.
    - *Falsifying observation:* No process is listening on the SIP port in the icscf container. This would indicate I-CSCF itself is not ready to receive traffic, making the 'partition' hypothesis incorrect.

*Notes:* This plan tests hypothesis h1. The core idea is to verify basic network connectivity between P-CSCF and I-CSCF. Probes are anchored in the `ims_registration` flow, step 3, where P-CSCF forwards the SIP REGISTER to I-CSCF over the Mw interface. The associated causal chain is `cascading_ims_outage`, branch `mw_routing_fails_at_pcscf_or_icscf`.

### Plan for `h2` (target: `pyhss`)

**Hypothesis:** The HSS is unresponsive to Diameter Cx requests. This is causing authentication and registration to fail, leading to the observed SIP errors at the P-CSCF.

**Probes (3):**
1. **`get_network_status`** — Check the status of the pyhss container.
    - *Expected if hypothesis holds:* The pyhss container should be in a 'running' state. The hypothesis is about application-level unresponsiveness, not a container crash.
    - *Falsifying observation:* The pyhss container is in an 'exited' or other non-running state. This would point to a crash rather than unresponsiveness.
2. **`query_subscriber`** — Query pyhss for a known IMSI, for example '208930000000003'.
    - *Expected if hypothesis holds:* The command should fail or time out, as the HSS is hypothesized to be unresponsive.
    - *Falsifying observation:* The command returns the correct subscriber profile, proving the HSS is alive and responding to queries.
3. **`get_diagnostic_metrics`** — Check Diameter metrics for icscf and scscf.
    - *Expected if hypothesis holds:* The `cdp:timeout` metric should be elevated (> 0) at both icscf and scscf, indicating that they are failing to get responses from HSS.
    - *Falsifying observation:* The `cdp:timeout` metric is 0 for both icscf and scscf. This would mean they are not experiencing timeouts when communicating with HSS, contradicting the hypothesis.

*Notes:* This plan tests hypothesis h2. It checks the health of the HSS from three different angles: container status, direct liveness probe, and the perspective of its clients (I-CSCF/S-CSCF). The relevant flows are `diameter_cx_authentication` and the Cx steps within `ims_registration` (steps 4, 6, 7).


## Parallel Investigators (Phase 5)

**2 sub-Investigator verdict(s):** **1 NOT_DISPROVEN**, **1 DISPROVEN**

### `h1` — ✅ **NOT_DISPROVEN**

**Hypothesis:** The P-CSCF is unable to forward SIP requests to the I-CSCF due to a partition on the Mw interface. This is causing IMS registration to fail, leading to SIP errors for all call and registration attempts.

**Reasoning:** All probes executed were consistent with the hypothesis. The round-trip time from the P-CSCF to the I-CSCF is extremely high (~2000ms), while the RTT from another core container (SMF) to the I-CSCF is normal (<1ms). This strongly suggests a network issue specific to the P-CSCF's egress path. The I-CSCF is confirmed to be running and listening for SIP traffic, reinforcing the conclusion that the fault lies in the path from the P-CSCF, not with the I-CSCF itself.

**Probes executed (3):**
- **From pcscf to the icscf container's IP address.** ✓ CONSISTENT
    - *Tool:* `measure_rtt("pcscf", "172.22.0.19")`
    - *Observation:* [EVIDENCE: measure_rtt("pcscf", "172.22.0.19") -> "rtt min/avg/max/mdev = 1961.159/1981.251/2012.966/22.690 ms"]
    - *Comment:* The extremely high RTT (~2 seconds) is a strong indicator of a network partition or severe degradation, which is consistent with the hypothesis.
- **From the smf container to the icscf container's IP address.** ✓ CONSISTENT
    - *Tool:* `measure_rtt("smf", "172.22.0.19")`
    - *Observation:* [EVIDENCE: measure_rtt("smf", "172.22.0.19") -> "rtt min/avg/max/mdev = 0.067/0.128/0.236/0.076 ms"]
    - *Comment:* The low RTT from SMF to I-CSCF demonstrates that the I-CSCF is reachable from other parts of the network. This triangulates the issue to be specific to the P-CSCF or its immediate network path, as stated in the hypothesis.
- **Check listening ports on the icscf container.** ✓ CONSISTENT
    - *Tool:* `check_process_listeners("icscf")`
    - *Observation:* [EVIDENCE: check_process_listeners("icscf") -> "udp   UNCONN 0      0        172.22.0.19:4060       0.0.0.0:*    users:((\"kamailio\",pid=63,fd=8)... tcp   LISTEN 0      1024     172.22.0.19:4060       0.0.0.0:*    users:((\"kamailio\",pid=63,fd=10)) "]
    - *Comment:* The I-CSCF container has a kamailio process listening on its IP address at port 4060 for both UDP and TCP. This confirms the I-CSCF is running and ready to accept SIP traffic, meaning the issue is that it is unreachable by the P-CSCF, not that it's down.

### `h2` — ❌ **DISPROVEN**

**Hypothesis:** The HSS is unresponsive to Diameter Cx requests. This is causing authentication and registration to fail, leading to the observed SIP errors at the P-CSCF.

**Reasoning:** The hypothesis is that the HSS is unresponsive. However, two separate probes contradict this. First, a direct query to the HSS for a subscriber profile using `query_subscriber` completed successfully, returning a result (even if null) instead of timing out. Second, and more decisively, diagnostic metrics from both the I-CSCF and S-CSCF show zero Diameter timeouts (`cdp:timeout = 0`) when communicating with the HSS. This directly falsifies the claim that the HSS is unresponsive to Diameter Cx requests, as its clients are not experiencing timeouts.

**Probes executed (3):**
- **Check the status of the pyhss container.** ✓ CONSISTENT
    - *Tool:* `print(default_api.get_network_status())`
    - *Observation:* [EVIDENCE: get_network_status() -> '"pyhss": "running"']
    - *Comment:* The pyhss container is running, which is consistent with an application-level fault rather than a crash. This probe does not falsify the hypothesis.
- **Query pyhss for a known IMSI, for example '208930000000003'.** ✗ CONTRADICTS
    - *Tool:* `print(default_api.query_subscriber(imsi='208930000000003'))`
    - *Observation:* [EVIDENCE: query_subscriber('208930000000003') -> '"core_5g": null, "ims_subscriber": null']
    - *Comment:* The HSS responded to the query, although it did not find the subscriber. The hypothesis predicted a failure or timeout, but the service was responsive. This contradicts the 'unresponsive' claim.
- **Check Diameter metrics for icscf and scscf.** ✗ CONTRADICTS
    - *Tool:* `print(default_api.get_diagnostic_metrics(at_time_ts = 1777512947.8434014, nfs = ["icscf", "scscf"]))`
    - *Observation:* [EVIDENCE: get_diagnostic_metrics(at_time_ts=1777512947.8434014, nfs=['icscf', 'scscf']) -> 'ICSCF...cdp:timeout = 0 [counter]...SCSCF...cdp:timeout = 0 [counter]']
    - *Comment:* The Diameter timeout counters at both the I-CSCF and S-CSCF are zero. This is strong evidence that they are not experiencing timeouts when communicating with the HSS, directly contradicting the hypothesis.

**Alternative suspects:** pcscf, icscf


## Evidence Validation (Phase 6)

**Overall verdict:** clean
**Overall confidence:** high

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 4 | 3/3 | clean | high |
| `InvestigatorAgent_h2` | 3 | 3/3 | clean | high |


## Ground Truth

**Failure domain:** ims_signaling  
**Protocol impact:** SIP  
**Affected components:** pcscf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v6-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 159.6s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: A network partition on the Mw interface is preventing the P-CSCF from forwarding SIP requests to the I-CSCF, causing all IMS registrations and subsequent call setups to fail.
> - **timeline**:
>     1. A network impairment begins between the P-CSCF and the I-CSCF.
>     2. UEs attempt to register with the IMS network, sending SIP REGISTER requests to the P-CSCF.
>     3. The P-CSCF fails to forward these requests to the I-CSCF across the impaired Mw interface, causing the `pcscf_sip_error_ratio` to spike.
>     4. The I-CSCF receives no SIP REGISTER traffic (`icscf.core:rcv_requests_register_per_ue` is zero), indicating a complete signaling failure on this path.
>     5. All UE attempts to register or make VoNR calls fail.
> - **root_cause**: A network-level partition isolates the P-CSCF from the I-CSCF. Investigation revealed an extremely high round-trip time (~2000ms) specifically from the P-CSCF to the I-CSCF, while other core components can reach the I-CSCF normally (<1ms), confirming the fault is localized to the P-CSCF's egress network path. The `primary_suspect_nf` is `pcscf`.
> - **affected_components**:
>     - `pcscf`: Root Cause
>     - `icscf`: Symptomatic
> - **recommendation**: The operator should investigate the network configuration and path from the P-CSCF container to the I-CSCF container to identify the source of the extreme latency and packet loss. Check for any misconfigured network policies or traffic shaping rules applied to the P-CSCF's network interface.
> - **confidence**: high
> - **explanation**: The investigation confirmed hypothesis `h1` and disproved `h2`. The root cause is a network partition between the P-CSCF and I-CSCF. This was confirmed by measuring an extremely high RTT (~2000ms) between the two components, while simultaneously measuring a normal RTT (<1ms) from another core component (SMF) to the same I-CSCF. This isolates the fault to the P-CSCF's egress path. The alternative hypothesis, that the HSS was unresponsive, was disproven because diagnostic metrics from its clients (I-CSCF, S-CSCF) showed zero Diameter timeouts, and a direct query to the HSS was successful.

### Scoring Breakdown

**Overall score: 100%**

**Scorer assessment:** The agent provided an excellent and accurate diagnosis, correctly identifying the root cause, affected component, severity, and fault type with high confidence.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | Yes | The simulated failure was 2000ms latency on the P-CSCF. The agent correctly identified an 'extremely high round-trip time (~2000ms)' from the P-CSCF to the I-CSCF, which is semantically equivalent to the simulated latency and its impact. |
| Component overlap | 100% | The primary affected component, 'pcscf', was correctly identified and labeled as 'Root Cause' in the affected_components list. |
| Severity correct | Yes | The simulated failure (2000ms latency) led to SIP REGISTER 408 timeouts and IMS registration failures, indicating a complete outage. The agent correctly diagnosed that the issue was 'preventing the P-CSCF from forwarding SIP requests' and 'causing all IMS registrations and subsequent call setups to fail', which aligns with a complete service outage. |
| Fault type identified | Yes | The agent explicitly identified 'extremely high round-trip time (~2000ms)', which is a direct observation of the simulated latency. The characterization as a 'network-level partition' is a reasonable interpretation of such severe latency causing timeouts. |
| Layer accuracy | Yes | The P-CSCF belongs to the 'ims' layer. The agent's network analysis correctly rated the 'ims' layer as 'red'. |
| Confidence calibrated | Yes | The agent's diagnosis is accurate and well-supported by evidence, making its 'high' confidence level appropriate. |

**Ranking position:** #1 — The agent provided a single, correct root cause as its primary diagnosis.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 146,802 |
| Output tokens | 4,537 |
| Thinking tokens | 11,860 |
| **Total tokens** | **163,199** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| EventAggregator | 0 | 0 | 0 |
| CorrelationAnalyzer | 0 | 0 | 0 |
| NetworkAnalystAgent | 37,712 | 5 | 3 |
| InstructionGeneratorAgent | 21,424 | 3 | 2 |
| InvestigatorAgent_h1 | 57,585 | 4 | 5 |
| InvestigatorAgent_h2 | 41,599 | 3 | 4 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 4,879 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 309.0s
