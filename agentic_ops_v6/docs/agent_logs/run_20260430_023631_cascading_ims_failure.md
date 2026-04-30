# Episode Report: Cascading IMS Failure

**Agent:** v6  
**Episode ID:** ep_20260430_022827_cascading_ims_failure  
**Date:** 2026-04-30T02:28:29.339849+00:00  
**Duration:** 480.9s  

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

**ANOMALY DETECTED.** Overall anomaly score: 22.20 (per-bucket threshold: 11.07, context bucket (0, 0), trained on 323 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following metrics deviate from their learned-healthy baseline. Treat each as a semantic observation (meaning + numbers), not a number alone — the KB's interpretation is the authoritative reading.

- **`normalized.icscf.core:rcv_requests_invite_per_ue`** (SIP INVITE rate per UE at I-CSCF) — current **0.03 requests_per_second** vs learned baseline **0.00 requests_per_second** (MEDIUM, spike)
    - **What it measures:** Health of call-setup forwarding P-CSCF → I-CSCF. Partition signature
same as REGISTER rate.
    - **Spike means:** Forwarding failure.
    - **Healthy typical range:** 0–0.2 requests_per_second
    - **Healthy invariant:** Per-UE rate. Tracks pcscf.invite rate.

- **`normalized.pcscf.core:rcv_requests_invite_per_ue`** (SIP INVITE rate per UE at P-CSCF) — current **0.02 requests_per_second** vs learned baseline **0.00 requests_per_second** (MEDIUM, spike)
    - **What it measures:** Call attempt rate from registered UEs. Unlike REGISTER (periodic),
INVITEs only fire when UEs place calls. Zero is normal during
quiet periods; nonzero INVITE with zero dialogs is the signature
of call setup failure.
    - **Spike means:** Fewer call attempts.
    - **Healthy typical range:** 0–0.2 requests_per_second
    - **Healthy invariant:** Per-UE rate.

- **`normalized.scscf.core:rcv_requests_invite_per_ue`** (SIP INVITE rate per UE at S-CSCF) — current **0.06 requests_per_second** vs learned baseline **0.00 requests_per_second** (MEDIUM, spike)
    - **What it measures:** S-CSCF participation in call setup. Zero when calls aren't being
placed OR S-CSCF not receiving forwarded INVITEs.
    - **Spike means:** Upstream forwarding issue.
    - **Healthy typical range:** 0–0.2 requests_per_second
    - **Healthy invariant:** Per-UE rate.

- **`normalized.smf.bearers_per_ue`** (Active QoS bearers per UE) — current **2.50 count** vs learned baseline **2.48 count** (LOW, shift)
    - **What it measures:** Per-UE count of active QoS bearers. Baseline reflects default
bearers; increments during VoNR calls indicate dedicated voice
bearers being set up. Drop during an active call = dedicated
bearer torn down unexpectedly (voice will fail).
    - **Shift means:** Expected during VoNR calls (1 extra bearer per active call).
    - **Healthy typical range:** 2–3.5 count
    - **Healthy invariant:** At rest: equals configured default bearers (typically 2 per UE).
During active VoNR call: +1 per caller. The per-UE ratio is the
invariant; absolute count scales with UE pool.

- **`normalized.upf.gtp_indatapktn3upf_per_ue`** (GTP-U uplink rate per UE (N3)) — current **0.09 packets_per_second** vs learned baseline **1.45 packets_per_second** (LOW, drop)
    - **What it measures:** Health of the uplink user-plane path gNB → UPF. Drops to near-zero
during RAN or N3 outage; stays nonzero during active calls or data
sessions. Decoupled from SIP signaling (signals data plane, not
control plane).
    - **Drop means:** Data plane dead on uplink — UPF receiving no packets from gNB.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE — constant regardless of UE pool size. Rises during active VoNR calls (~100 pps for G.711 voice) and data transfer.

- **`normalized.upf.gtp_outdatapktn3upf_per_ue`** (GTP-U downlink rate per UE (N3)) — current **0.02 packets_per_second** vs learned baseline **1.45 packets_per_second** (LOW, drop)
    - **What it measures:** Health of the downlink user-plane path UPF → gNB. Typically mirrors
uplink rate during calls/data; asymmetry indicates directional
faults (e.g., UPF receiving from internet but not forwarding).
    - **Drop means:** No traffic leaving UPF toward RAN.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE — constant regardless of UE pool size. Roughly symmetric with uplink during healthy calls.


## Event Aggregation (Phase 1)

No events fired during this episode. Either no metric KB triggers matched, or the episode encountered no meaningful state transitions.

## Correlation Analysis (Phase 2)

No events fired — correlation engine had nothing to work with.

## Network Analysis (Phase 3)

**Summary:** VoNR calls are failing due to a definite crash of the HSS, which is critical for IMS signaling, and a concurrent, severe failure in the UPF which has halted all downlink data traffic.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | With the exception of the HSS application, all other network function containers are running. |
| **ran** | 🟡 YELLOW | The RAN is likely operating correctly but cannot provide service to UEs due to the core and IMS layer failures. |
| **core** | 🔴 RED | The UPF data plane is non-functional, preventing any user data, including voice media, from being transmitted to UEs. |
| **ims** | 🔴 RED | The HSS is the central database for subscriber information. Its failure makes IMS registration and call routing impossible. |

**CORE evidence:**
- UPF downlink GTP-U traffic is at zero, while uplink traffic is anomalously high.
- Initial anomaly report showed a drop to near-zero for both uplink and downlink per-UE GTP-U traffic at the UPF.

**IMS evidence:**
- pyhss container has exited.
- Cx links from I-CSCF and S-CSCF to HSS are inactive.
- Increased SIP INVITE requests per UE at P-CSCF, I-CSCF, and S-CSCF, indicating call setup failures.

**Ranked hypotheses:**

- **`h1`** (fit=0.90, nf=pyhss, specificity=specific):
    - **Statement:** The Home Subscriber Server (HSS) has exited, causing a complete failure of IMS services. The I-CSCF and S-CSCF cannot query the HSS for user location and authentication during call setup, leading to the observed SIP INVITE failures.
    - **Supporting events:** `normalized.icscf.core:rcv_requests_invite_per_ue`, `normalized.pcscf.core:rcv_requests_invite_per_ue`, `normalized.scscf.core:rcv_requests_invite_per_ue`
    - **Falsification probes:**
        - Check the logs for the 'pyhss' container to determine the cause of its exit.
        - Restart the 'pyhss' container and observe if IMS registration and VoNR call setup succeed.
- **`h2`** (fit=0.80, nf=upf, specificity=specific):
    - **Statement:** The User Plane Function (UPF) is experiencing a critical fault, causing it to drop all downlink traffic. While uplink traffic is being received, no traffic is being forwarded to the RAN, resulting in a complete data plane outage.
    - **Supporting events:** `normalized.upf.gtp_indatapktn3upf_per_ue`, `normalized.upf.gtp_outdatapktn3upf_per_ue`
    - **Falsification probes:**
        - Examine the internal logs and packet counters of the 'upf' container for discard/error statistics.
        - Trace the data path from the UPF towards the gNB to identify where packets are being dropped.


## Falsification Plans (Phase 4)

**2 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `pyhss`)

**Hypothesis:** The Home Subscriber Server (HSS) has exited, causing a complete failure of IMS services. The I-CSCF and S-CSCF cannot query the HSS for user location and authentication during call setup, leading to the observed SIP INVITE failures.

**Probes (3):**
1. **`get_network_status`** — Check all containers, looking for 'pyhss'
    - *Expected if hypothesis holds:* The 'pyhss' container status is 'exited' or 'down'.
    - *Falsifying observation:* The 'pyhss' container status is 'running' or 'up'.
2. **`check_process_listeners`** — container: 'pyhss', protocol: 'tcp'
    - *Expected if hypothesis holds:* No process is listening on the Diameter port (TCP/3868), or the check fails because the container is down.
    - *Falsifying observation:* A process is listening on the Diameter port (TCP/3868), indicating the HSS application is running.
3. **`query_subscriber`** — imsi: <any valid IMSI from the test environment>
    - *Expected if hypothesis holds:* The query fails or times out.
    - *Falsifying observation:* The query returns a valid subscriber profile, proving the HSS is fully operational.

*Notes:* Hypothesis h1 alleges a failure of the HSS, which is critical for the 'ims_registration' flow (steps 4, 6, 7) and 'vonr_call_setup' (step 6). These probes verify the HSS container, process, and application-level health.

### Plan for `h2` (target: `upf`)

**Hypothesis:** The User Plane Function (UPF) is experiencing a critical fault, causing it to drop all downlink traffic. While uplink traffic is being received, no traffic is being forwarded to the RAN, resulting in a complete data plane outage.

**Probes (3):**
1. **`get_dp_quality_gauges`** — window_seconds: 60
    - *Expected if hypothesis holds:* Non-zero packet rates arriving from the data network (e.g., n6_dl_packets_per_second > 0) but zero or near-zero rates for downlink traffic being forwarded to the RAN (n3_dl_packets_per_second == 0).
    - *Falsifying observation:* Non-zero packet rates for downlink traffic on the N3 interface (n3_dl_packets_per_second > 0), contradicting the claim that the UPF is dropping all downlink traffic.
2. **`get_diagnostic_metrics`** — Look for UPF-specific counters for N3 downlink packet discards or errors.
    - *Expected if hypothesis holds:* High or incrementing packet discard/error counters for the N3 downlink path, while N6 downlink ingress counters are incrementing.
    - *Falsifying observation:* Zero or non-incrementing discard/error counters for the N3 downlink path. This suggests the UPF is either successfully forwarding packets or not receiving them in the first place.
3. **`check_process_listeners`** — container: 'upf', port: 8805, protocol: 'udp'
    - *Expected if hypothesis holds:* A process is listening on the PFCP port (UDP/8805), indicating the N4 control plane interface is up. This isolates the failure to the data plane.
    - *Falsifying observation:* No process is listening on the PFCP port (UDP/8805). This would point to an N4 control plane failure as the root cause, rather than a pure data plane fault.

*Notes:* Hypothesis h2 alleges a data plane failure in the UPF. The 'pdu_session_establishment' flow creates the user plane, and media packets in 'vonr_call_setup' (step 12) depend on it. These probes check the UPF's data forwarding behavior (N6-in vs N3-out), internal error counters, and control plane status to isolate the fault.


## Parallel Investigators (Phase 5)

**2 sub-Investigator verdict(s):** **1 NOT_DISPROVEN**, **1 DISPROVEN**

### `h1` — ✅ **NOT_DISPROVEN**

**Hypothesis:** The Home Subscriber Server (HSS) has exited, causing a complete failure of IMS services. The I-CSCF and S-CSCF cannot query the HSS for user location and authentication during call setup, leading to the observed SIP INVITE failures.

**Reasoning:** All probes executed returned results that are consistent with the hypothesis. The 'pyhss' container is confirmed to be in an 'exited' state, and as a result, it is not listening on any ports and is unresponsive to application-level queries for subscriber information. This directly supports the claim that the HSS has failed.

**Probes executed (3):**
- **Check all containers, looking for 'pyhss'** ✓ CONSISTENT
    - *Tool:* `default_api.get_network_status()`
    - *Observation:* [EVIDENCE: get_network_status() -> "'pyhss': 'exited'"]
    - *Comment:* The network status confirms the 'pyhss' container has exited, which is the central claim of the hypothesis.
- **container: 'pyhss', protocol: 'tcp'** ✓ CONSISTENT
    - *Tool:* `default_api.check_process_listeners(container='pyhss')`
    - *Observation:* [EVIDENCE: check_process_listeners('pyhss') -> "Error response from daemon: container ... is not running"]
    - *Comment:* This probe failed because the container is down, which is the expected outcome if the hypothesis holds. An exited container cannot have any listening processes.
- **imsi: <any valid IMSI from the test environment>** ✓ CONSISTENT
    - *Tool:* `default_api.query_subscriber(domain='ims', imsi='001011234567891')`
    - *Observation:* [EVIDENCE: query_subscriber('001011234567891', domain='ims') -> "'ims_error': 'Cannot connect to PyHSS API at http://172.22.0.18:8080. Is the pyhss container running?'"]
    - *Comment:* The application-level query to the HSS failed with a connection error, which directly supports the hypothesis that the HSS is down and unresponsive. The IMSI was obtained from a prior call to read_env_config.

### `h2` — ❌ **DISPROVEN**

**Hypothesis:** The User Plane Function (UPF) is experiencing a critical fault, causing it to drop all downlink traffic. While uplink traffic is being received, no traffic is being forwarded to the RAN, resulting in a complete data plane outage.

**Reasoning:** The hypothesis is disproven because evidence from multiple probes contradicts the central claim that the UPF is dropping *all* downlink traffic. Both data plane quality gauges and diagnostic metrics show a non-zero rate of packets being forwarded on the N3 interface to the RAN. While the rate is extremely low, it is not zero, which falsifies the assertion of a 'complete data plane outage'.

**Probes executed (3):**
- **Check data plane quality gauges for the UPF to see if downlink traffic is being forwarded to the RAN.** ✗ CONTRADICTS
    - *Tool:* `default_api.get_dp_quality_gauges(at_time_ts = 1777516161.0209599, window_seconds = 60)`
    - *Observation:* [EVIDENCE: get_dp_quality_gauges(at_time_ts=1777516161.0209599, window_seconds=60) -> "UPF:\n    out packets/sec: 0.1"]
    - *Comment:* The hypothesis predicted zero downlink traffic being forwarded (out packets/sec == 0). The observation of 0.1 packets/sec, while low, contradicts the claim of a complete outage.
- **Examine UPF-specific counters for N3 downlink packet discards or errors.** ✗ CONTRADICTS
    - *Tool:* `default_api.get_diagnostic_metrics(at_time_ts = 1777516161.0209599, nfs = ["upf"])`
    - *Observation:* [EVIDENCE: get_diagnostic_metrics(at_time_ts=1777516161.0209599, nfs=['upf']) -> "normalized.upf.gtp_outdatapktn3upf_per_ue = 0.0208"]
    - *Comment:* The metric 'gtp_outdatapktn3upf_per_ue' represents downlink packets from UPF to gNB. A non-zero value directly contradicts the hypothesis that no traffic is being forwarded to the RAN.
- **Check if a process is listening on the PFCP port (UDP/8805) to isolate the failure to the data plane.** ✓ CONSISTENT
    - *Tool:* `default_api.check_process_listeners(container = "upf")`
    - *Observation:* [EVIDENCE: check_process_listeners(container='upf') -> "udp   UNCONN 0      0         172.22.0.8:8805       0.0.0.0:*    users:((\"open5gs-upfd\",pid=8,fd=7))"]
    - *Comment:* The UPF process is listening on the N4 PFCP port (8805). This is consistent with the hypothesis that the control plane interface is up and the issue is confined to the data plane.


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
**Affected components:** scscf, pyhss  
**Severity:** degraded

## Agent Diagnosis

**Model:** v6-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 194.2s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: VoNR call failures are caused by a crash of the Home Subscriber Server (HSS), which is essential for IMS signaling, rendering call setup impossible.
> - **timeline**:
>     1. IMS signaling for new calls fails, observed as a drop in SIP INVITE requests at the P-CSCF, I-CSCF, and S-CSCF.
>     2. Investigation confirms the `pyhss` container, which runs the HSS, is in an 'exited' state.
>     3. Application-level probes to the HSS fail with connection errors, verifying that the service is offline and unresponsive.
> - **root_cause**: The Home Subscriber Server (HSS) has crashed. The HSS is a critical component for user authentication and call routing in the IMS network. Its failure halts all IMS-related signaling.
>     - `primary_suspect_nf`: `pyhss`
> - **affected_components**:
>     - `pyhss` (HSS): Root Cause
>     - `icscf`: Secondary
>     - `scscf`: Secondary
>     - `upf`: Secondary
> - **recommendation**: The operator should first verify the logs for the `pyhss` container to determine the reason for its crash. Concurrently, the operator should investigate the performance degradation of the `upf`, as metrics indicate a severe but not total loss of downlink traffic, suggesting a separate, concurrent fault.
> - **confidence**: high
> - **explanation**: The investigation confirmed that VoNR calls are failing because the Home Subscriber Server (HSS) has crashed. The hypothesis (`h1`) pointing to the HSS failure was validated by evidence showing the `pyhss` container was in an 'exited' state and unresponsive to network and application-level queries. The HSS is required for the IMS Core to authenticate subscribers and route calls; without it, all IMS sessions will fail. A concurrent hypothesis (`h2`) blaming a complete downlink outage at the User Plane Function (UPF) was disproven, as probes detected a non-zero, albeit extremely low, rate of outbound packets. While the UPF issue is not the primary cause of the IMS signaling failure, it represents a severe, concurrent fault that is crippling the user data plane.

### Scoring Breakdown

**Overall score: 55%**

**Scorer assessment:** The agent correctly identified the HSS crash as a primary cause of the IMS outage but failed to detect the concurrent S-CSCF latency, leading to an incomplete diagnosis of the cascading failure scenario despite high confidence.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | No | The simulated failure involved two distinct issues: a complete outage of 'pyhss' AND a 2-second latency on 'scscf'. The agent correctly identified the 'pyhss' crash as the root cause for IMS signaling failure, but completely missed the 'scscf' latency, which is a separate, concurrent failure mode that contributes to the 'cascading IMS failure' scenario. While the HSS crash alone would cause a total IMS outage, the scenario explicitly includes S-CSCF degradation, which was not identified. |
| Component overlap | 50% | The agent correctly identified 'pyhss' (HSS) as the 'Root Cause' component, which is one of the two primary affected components. It also listed 'scscf' as a 'Secondary' affected component, indicating it was observed but its specific failure mode (latency) was not identified as a root cause or even a distinct degradation. The UPF was also listed as secondary, which was a separate, concurrent issue identified by the agent, but not part of the simulated IMS failure. |
| Severity correct | Yes | The agent diagnosed a 'crash' of the HSS and 'total IMS outage' / 'VoNR call failures', which aligns with the 'pyhss' being 'completely unreachable (down/not responding)' and leading to 'total IMS registration failure' and 'no voice calls possible'. |
| Fault type identified | Yes | The agent identified the HSS as 'crashed' and 'unresponsive', which is equivalent to 'component unreachable' or 'not responding'. This correctly describes the observable failure mode for the HSS. |
| Layer accuracy | Yes | The agent's network analysis correctly rated the 'ims' layer as 'red' and provided evidence directly related to the 'pyhss' container (HSS) and IMS signaling, which aligns with 'pyhss' belonging to the 'ims' layer. No misattribution of layers was observed for the identified issues. |
| Confidence calibrated | No | The agent stated 'high' confidence, but missed a significant part of the simulated failure (S-CSCF latency). While it correctly identified the HSS crash, the 'high' confidence is not fully calibrated given the incomplete diagnosis of a 'cascading failure' scenario. |

**Ranking:** The agent presented a single root cause (HSS crash) and did not rank multiple candidates for the *simulated* failure modes. It did identify a separate UPF issue, but that was not part of the IMS cascading failure.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 166,669 |
| Output tokens | 4,107 |
| Thinking tokens | 15,312 |
| **Total tokens** | **186,088** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| EventAggregator | 0 | 0 | 0 |
| CorrelationAnalyzer | 0 | 0 | 0 |
| NetworkAnalystAgent | 61,992 | 4 | 5 |
| InstructionGeneratorAgent | 23,206 | 2 | 2 |
| InvestigatorAgent_h1 | 52,043 | 4 | 5 |
| InvestigatorAgent_h2 | 43,801 | 3 | 4 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 5,046 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 480.9s
