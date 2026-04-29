# Episode Report: Cascading IMS Failure

**Agent:** v6  
**Episode ID:** ep_20260429_170046_cascading_ims_failure  
**Date:** 2026-04-29T17:00:48.185094+00:00  
**Duration:** 310.5s  

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

**ANOMALY DETECTED.** Overall anomaly score: 53.35 (per-bucket threshold: 26.31, context bucket (0, 1), trained on 323 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following metrics deviate from their learned-healthy baseline. Treat each as a semantic observation (meaning + numbers), not a number alone — the KB's interpretation is the authoritative reading.

- **`context.cx_active`** — current **0.00** vs learned baseline **0.59** (MEDIUM, drop). *(No KB context available — interpret from the metric name.)*

- **`normalized.icscf.cdp_replies_per_ue`** (I-CSCF Diameter reply rate per UE) — current **0.00 replies_per_second_per_ue** vs learned baseline **0.03 replies_per_second_per_ue** (MEDIUM, drop)
    - **What it measures:** Liveness of the I-CSCF↔HSS Cx path. Drops to 0 when HSS is unreachable OR when no signaling is occurring at the I-CSCF (idle or upstream P-CSCF partitioned).
    - **Drop means:** No Cx replies in the window. Could be healthy idle OR a Cx-path fault.
    - **Healthy typical range:** 0–1 replies_per_second_per_ue

- **`normalized.icscf.core:rcv_requests_invite_per_ue`** (SIP INVITE rate per UE at I-CSCF) — current **0.03 requests_per_second** vs learned baseline **0.00 requests_per_second** (MEDIUM, spike)
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

- **`normalized.pcscf.core:rcv_requests_invite_per_ue`** (SIP INVITE rate per UE at P-CSCF) — current **0.02 requests_per_second** vs learned baseline **0.00 requests_per_second** (MEDIUM, spike)
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

- **`normalized.scscf.core:rcv_requests_invite_per_ue`** (SIP INVITE rate per UE at S-CSCF) — current **0.06 requests_per_second** vs learned baseline **0.00 requests_per_second** (MEDIUM, spike)
    - **What it measures:** S-CSCF participation in call setup. Zero when calls aren't being
placed OR S-CSCF not receiving forwarded INVITEs.
    - **Spike means:** Upstream forwarding issue.
    - **Healthy typical range:** 0–0.2 requests_per_second
    - **Healthy invariant:** Per-UE rate.

- **`normalized.scscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at S-CSCF) — current **0.00 requests_per_second** vs learned baseline **0.06 requests_per_second** (MEDIUM, drop)
    - **What it measures:** Health of the I-CSCF → S-CSCF forwarding path. Drop to zero while
I-CSCF is receiving REGISTERs = S-CSCF-side issue (crashed, or
I-CSCF → S-CSCF path broken).
    - **Drop means:** S-CSCF isolated or not running.
    - **Healthy typical range:** 0–0.5 requests_per_second
    - **Healthy invariant:** Per-UE rate. Tracks icscf.register rate.

- **`normalized.upf.gtp_indatapktn3upf_per_ue`** (GTP-U uplink rate per UE (N3)) — current **0.05 packets_per_second** vs learned baseline **1.45 packets_per_second** (MEDIUM, drop)
    - **What it measures:** Health of the uplink user-plane path gNB → UPF. Drops to near-zero
during RAN or N3 outage; stays nonzero during active calls or data
sessions. Decoupled from SIP signaling (signals data plane, not
control plane).
    - **Drop means:** Data plane dead on uplink — UPF receiving no packets from gNB.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE — constant regardless of UE pool size. Rises during active VoNR calls (~100 pps for G.711 voice) and data transfer.


## Event Aggregation (Phase 1)

No events fired during this episode. Either no metric KB triggers matched, or the episode encountered no meaningful state transitions.

## Correlation Analysis (Phase 2)

No events fired — correlation engine had nothing to work with.

## Network Analysis (Phase 3)

**Summary:** The IMS network is down due to the HSS component having exited, preventing user registration and call setup.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🔴 RED | The failure of the HSS container indicates an infrastructure or application-level problem that needs to be addressed. |
| **ran** | 🟢 GREEN | No evidence of a RAN issue. UEs are still attached to the network. |
| **core** | 🟡 YELLOW | The core network data plane is affected due to the lack of VoNR calls. |
| **ims** | 🔴 RED | The HSS is the main user database for IMS. Its failure is critical. |

**INFRASTRUCTURE evidence:**
- A critical network function container (pyhss) has exited.

**CORE evidence:**
- upf throughput is significantly lower than baseline

**IMS evidence:**
- hss container has exited
- cx links to hss are inactive

**Ranked hypotheses:**

- **`h1`** (fit=1.00, nf=pyhss, specificity=specific):
    - **Statement:** The HSS (pyhss) container has exited, causing a complete failure of the IMS user database. This prevents all IMS procedures that require user authentication or subscriber location information, such as registration and call setup.
    - **Falsification probes:**
        - Restart the pyhss container and observe if registration and call setup succeed.
        - Check the logs of the pyhss container to determine the cause of the exit.
- **`h2`** (fit=0.50, nf=icscf, specificity=moderate):
    - **Statement:** There is a partition between the I-CSCF and S-CSCF, preventing the forwarding of REGISTER requests. This is indicated by the S-CSCF receiving no REGISTER requests while the I-CSCF is still receiving some.
    - **Falsification probes:**
        - Send a test SIP request from the I-CSCF to the S-CSCF to verify connectivity.
        - Check the routing configuration on the I-CSCF to ensure it is correctly configured to forward requests to the S-CSCF.


## Falsification Plans (Phase 4)

**2 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `pyhss`)

**Hypothesis:** The HSS (pyhss) container has exited, causing a complete failure of the IMS user database. This prevents all IMS procedures that require user authentication or subscriber location information, such as registration and call setup.

**Probes (3):**
1. **`get_network_status`** — Check all containers, focus on pyhss
    - *Expected if hypothesis holds:* The 'pyhss' container has a status of 'exited'.
    - *Falsifying observation:* The 'pyhss' container is 'running'.
2. **`query_subscriber`** — any valid IMSI, e.g. '208930100000001'
    - *Expected if hypothesis holds:* The tool call fails or times out, indicating the HSS is not responsive.
    - *Falsifying observation:* The tool successfully returns subscriber data, proving the HSS is responsive.
3. **`get_nf_metrics`** — icscf and scscf
    - *Expected if hypothesis holds:* Metrics on I-CSCF/S-CSCF show an increasing count of Diameter/Cx connection failures or timeouts to the HSS.
    - *Falsifying observation:* Zero Diameter/Cx errors on I-CSCF and S-CSCF, suggesting they are not having issues communicating with the HSS.

*Notes:* This plan directly tests the primary claim (container exited) and its immediate functional consequence (HSS is unresponsive to queries from CSCFs). The `ims_registration` flow confirms that I-CSCF and S-CSCF both depend on HSS for this procedure.

### Plan for `h2` (target: `icscf`)

**Hypothesis:** There is a partition between the I-CSCF and S-CSCF, preventing the forwarding of REGISTER requests. This is indicated by the S-CSCF receiving no REGISTER requests while the I-CSCF is still receiving some.

**Probes (3):**
1. **`measure_rtt`** — from: icscf, to_ip: <scscf_ip>
    - *Expected if hypothesis holds:* High or 100% packet loss, indicating a network partition.
    - *Falsifying observation:* Low RTT (<5ms) and 0% packet loss, indicating clean connectivity.
2. **`get_nf_metrics`** — icscf
    - *Expected if hypothesis holds:* An increase in metrics related to SIP request timeouts or forwarding failures. This corresponds to step 5 of the 'ims_registration' flow.
    - *Falsifying observation:* No increase in SIP forwarding errors or timeouts. This would imply the I-CSCF isn't attempting to forward or is succeeding.
3. **`measure_rtt`** — from: icscf, to_ip: <pcscf_ip>
    - *Expected if hypothesis holds:* Low RTT (<5ms) and 0% packet loss. This shows the icscf's networking is otherwise healthy, isolating the problem to the scscf path.
    - *Falsifying observation:* High or 100% packet loss. This suggests a broader problem with the icscf's egress networking, not just a partition to the scscf.

*Notes:* This plan tests the 'partition' claim at both the network layer (RTT) and application layer (SIP metrics). It includes a triangulation probe to isolate the fault domain, per instructions. The `ims_registration` flow shows step 5 'Forward REGISTER to S-CSCF' is the critical step affected.


## Parallel Investigators (Phase 5)

**2 sub-Investigator verdict(s):** **2 DISPROVEN**

### `h1` — ❌ **DISPROVEN**

**Hypothesis:** The HSS (pyhss) container has exited, causing a complete failure of the IMS user database. This prevents all IMS procedures that require user authentication or subscriber location information, such as registration and call setup.

**Reasoning:** While the `pyhss` container has indeed exited, as confirmed by `get_network_status`, the expected consequence—a spike in Diameter/Cx timeouts on the I-CSCF and S-CSCF—is not observed. The `get_nf_metrics` tool shows that all HSS-related timeout counters (`ims_icscf:uar_timeouts`, `ims_auth:mar_timeouts`, `ims_registrar_scscf:sar_timeouts`) on both the I-CSCF and S-CSCF are zero. This directly contradicts the hypothesis's causal claim that IMS procedures are failing due to an inability to communicate with the HSS. The CSCFs are not registering timeouts, which means the failure mechanism is not what the hypothesis describes.

**Probes executed (3):**
- **Check all containers, focus on pyhss** ✓ CONSISTENT
    - *Tool:* `print(default_api.get_network_status())`
    - *Observation:* [EVIDENCE: get_network_status() -> "'pyhss': 'exited'"]
    - *Comment:* The primary assertion of the hypothesis, that the pyhss container has exited, is confirmed. This supports the first part of the hypothesis statement.
- **any valid IMSI, e.g. '208930100000001'** ✓ CONSISTENT
    - *Tool:* `print(default_api.query_subscriber(domain = "ims", imsi = "208930100000001"))`
    - *Observation:* [EVIDENCE: query_subscriber(domain='ims', imsi='208930100000001') -> "'ims_error': 'Cannot connect to PyHSS API at http://172.22.0.18:8080. Is the pyhss container running?'"]
    - *Comment:* The HSS is not responsive to direct API queries, which is consistent with the container being in an 'exited' state. This further supports the idea that the HSS is non-functional.
- **icscf and scscf** ✗ CONTRADICTS
    - *Tool:* `print(default_api.get_nf_metrics())`
    - *Observation:* [EVIDENCE: get_nf_metrics() -> "ICSCF [...] ims_icscf:uar_timeouts = 0.0 [...] SCSCF [...] ims_auth:mar_timeouts = 0.0 [...] ims_registrar_scscf:sar_timeouts = 0.0"]
    - *Comment:* This is the key falsifying observation. If the HSS were down and CSCFs were trying to process registrations, their Diameter/Cx connections to the HSS should be timing out. The metrics show zero timeouts on both I-CSCF and S-CSCF for all HSS-related procedures (UAR, MAR, SAR). This proves that the IMS failure is not caused by CSCFs failing to get a response from the HSS.

**Alternative suspects:** icscf, scscf

### `h2` — ❌ **DISPROVEN**

**Hypothesis:** There is a partition between the I-CSCF and S-CSCF, preventing the forwarding of REGISTER requests. This is indicated by the S-CSCF receiving no REGISTER requests while the I-CSCF is still receiving some.

**Reasoning:** Probe 1 confirmed a major network issue on the path from I-CSCF to S-CSCF, with a 2-second RTT. However, probe 2 showed that the I-CSCF is not experiencing any application-level timeouts or forwarding failures (`cdp:timeout = 0.0`, `ims_icscf:uar_timeouts = 0.0`). This contradicts the core of the hypothesis that the I-CSCF is "prevented" from forwarding requests. Forwarding is attempted, but the connection to the S-CSCF is severely degraded. The fault is not in the I-CSCF's forwarding logic, but rather in the S-CSCF's responsiveness or the network path leading to it.

**Probes executed (3):**
- **measure rtt from icscf to scscf** ✓ CONSISTENT
    - *Tool:* `default_api.measure_rtt(container='icscf', target_ip='172.22.0.20')`
    - *Observation:* [EVIDENCE: measure_rtt("icscf", "172.22.0.20") -> "3 packets transmitted, 3 received, 0% packet loss, time 2027ms\nrtt min/avg/max/mdev = 2000.301/2000.435/2000.646/0.150 ms"]
    - *Comment:* While there was 0% packet loss, the RTT of 2000ms is exceptionally high and indicates a severe network performance issue, which is consistent with the 'partition' concept in the hypothesis.
- **get nf metrics for icscf** ✗ CONTRADICTS
    - *Tool:* `default_api.get_nf_metrics()`
    - *Observation:* [EVIDENCE: get_nf_metrics() -> "ICSCF [13 req] (via kamcmd):\n  cdp:timeout = 0.0  [counter]\n  core:rcv_requests_register = 13.0  [counter]\n  ims_icscf:uar_timeouts = 0.0  [counter]"]
    - *Comment:* The metrics show zero timeouts for both Diameter (CDP) and UAR (user authorization requests to HSS). If a partition were preventing the I-CSCF from forwarding, these timeout counters should be increasing. This contradicts the hypothesis.
- **measure rtt from icscf to pcscf** ✓ CONSISTENT
    - *Tool:* `default_api.measure_rtt(container='icscf', target_ip='172.22.0.21')`
    - *Observation:* [EVIDENCE: measure_rtt("icscf", "172.22.0.21") -> "3 packets transmitted, 3 received, 0% packet loss, time 2059ms\nrtt min/avg/max/mdev = 0.066/0.101/0.159/0.041 ms"]
    - *Comment:* The RTT from I-CSCF to P-CSCF is very low, confirming that the I-CSCF's network interface and local network path are healthy. This isolates the network problem to the path specifically leading to the S-CSCF.

**Alternative suspects:** scscf


## Evidence Validation (Phase 6)

**Overall verdict:** clean
**Overall confidence:** high

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 3 | 3/3 | clean | high |
| `InvestigatorAgent_h2` | 4 | 3/3 | clean | high |


## Ground Truth

**Failure domain:** ims_signaling  
**Protocol impact:** SIP  
**Affected components:** pyhss, scscf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v6-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 147.8s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: The two initial hypotheses were disproven; investigation now points to the S-CSCF (`scscf`) as the likely root cause, as it is exhibiting extreme network latency which prevents it from processing user registrations.
> - **timeline**:
>     1. The `pyhss` (HSS) container was observed in an 'exited' state.
>     2. Probes from the I-CSCF to the S-CSCF revealed an extremely high round-trip time of 2000ms.
>     3. Investigation into the HSS failure hypothesis (`h1`) found that CSCFs were not experiencing any Diameter timeouts, disproving that the exited HSS was the cause of the registration failure.
>     4. Investigation into the network partition hypothesis (`h2`) found that the I-CSCF was not timing out on forwarding requests, isolating the problem to the S-CSCF's responsiveness rather than a fault in the I-CSCF.
> - **root_cause**: The root cause is undetermined, but the primary suspect is the S-CSCF (`scscf`). It is exhibiting extreme network latency (2000ms RTT when probed from the I-CSCF), which is preventing it from processing SIP REGISTER messages from the I-CSCF. A secondary, but currently non-causal, issue is that the HSS container (`pyhss`) has also exited.
> - **affected_components**:
>     - `scscf`: Root Cause (Suspected)
>     - `pyhss`: Secondary
>     - `icscf`: Symptomatic
> - **recommendation**: The operator should investigate the S-CSCF (`scscf`) container to determine the cause of the extreme network latency (2000ms RTT). Check the container's internal processes, resource utilization (CPU, memory), and logs for errors. Separately, the operator should inspect the logs for the `pyhss` container to understand why it exited.
> - **confidence**: low
> - **explanation**: The initial hypotheses from the Network Analyst were incorrect. The first hypothesis (`h1`), blaming the exited HSS container, was disproven because metrics showed zero HSS-related timeouts on the CSCFs; they were not failing because of an unreachable HSS. The second hypothesis (`h2`), blaming a network partition at the I-CSCF, was disproven because the I-CSCF showed no forwarding timeouts, indicating the fault was with the S-CSCF's lack of response. Based on the alternative suspects identified during the investigation, the S-CSCF (`scscf`) is now the focus due to the 2000ms RTT, which points to a severe performance issue within that component.

### Scoring Breakdown

**Overall score: 51%**

**Scorer assessment:** The agent partially identified the failure, correctly pinpointing S-CSCF latency but misjudging the HSS failure as non-causal and stating the root cause was undetermined. Its severity and fault type identification were accurate, and its confidence was calibrated, but layer attribution was flawed.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | No | The agent explicitly states that the 'root cause is undetermined'. While it correctly identifies S-CSCF latency as a primary suspect, it incorrectly dismisses the HSS failure (which is a root cause) as 'secondary' and 'non-causal'. According to the scoring rules, 'undetermined' root causes are scored False. |
| Component overlap | 80% | The agent correctly identifies 'scscf' (one of the two root causes) as 'Root Cause (Suspected)'. It also identifies 'pyhss' (the other root cause) but mis-ranks it as 'Secondary' and 'non-causal'. This results in partial credit for 'pyhss' (0.3) and full credit for 'scscf' (0.5), totaling 0.8. |
| Severity correct | Yes | The agent identifies 'extreme network latency' on the S-CSCF preventing registrations and the HSS container being 'exited'. This accurately reflects the 'total IMS outage' and 'no voice calls possible' severity described in the simulated failure. |
| Fault type identified | Yes | The agent correctly identifies 'extreme network latency' for the S-CSCF and the HSS container being 'exited' (component unreachable/down). These match the observable fault types of network degradation and component unreachability. |
| Layer accuracy | No | The agent correctly attributes the HSS failure to the 'ims' layer. However, it also attributes the 'pyhss' container exiting to the 'infrastructure' layer. As per the ontology, 'pyhss' is an IMS component, and its failure, even if due to an infrastructure issue like a container exit, should primarily be attributed to the IMS layer from a network function perspective. |
| Confidence calibrated | Yes | The agent states 'low' confidence. Given that it correctly identified one root cause but mis-attributed the causality of another, and explicitly stated the root cause was 'undetermined', a low confidence is appropriate and well-calibrated. |

**Ranking position:** #1 — Although the overall root cause is stated as 'undetermined', the agent identifies 'scscf' as the 'primary suspect' for the root cause. 'scscf' is indeed one of the correct root causes, placing it at position 1 among the agent's identified suspects.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 102,740 |
| Output tokens | 4,099 |
| Thinking tokens | 13,352 |
| **Total tokens** | **120,191** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| EventAggregator | 0 | 0 | 0 |
| CorrelationAnalyzer | 0 | 0 | 0 |
| NetworkAnalystAgent | 23,396 | 3 | 2 |
| InstructionGeneratorAgent | 19,993 | 2 | 2 |
| InvestigatorAgent_h1 | 38,107 | 3 | 4 |
| InvestigatorAgent_h2 | 33,587 | 4 | 3 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 5,108 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 310.5s
