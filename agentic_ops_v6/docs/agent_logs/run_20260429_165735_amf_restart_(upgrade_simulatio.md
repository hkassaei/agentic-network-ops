# Episode Report: AMF Restart (Upgrade Simulation)

**Agent:** v6  
**Episode ID:** ep_20260429_165324_amf_restart_(upgrade_simulatio  
**Date:** 2026-04-29T16:53:25.650511+00:00  
**Duration:** 248.5s  

---

## Scenario

**Category:** container  
**Blast radius:** multi_nf  
**Description:** Stop the AMF for 10 seconds, then restart it. Simulates a rolling upgrade of the access and mobility management function. UEs will temporarily lose their 5G NAS connection and must re-attach.

## Faults Injected

- **container_stop** on `amf` — {'timeout': 10}

## Baseline (Pre-Fault)

Stack phase before injection: **ready**
All containers running at baseline.

## Fault Propagation Verification

**Verdict:** ✅ `confirmed`

- **Wait:** 0s
- **Actual elapsed:** 0.0s
- **Nodes with significant deltas:** 5
- **Nodes with any drift:** 5

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 47.65 (per-bucket threshold: 26.31, context bucket (0, 1), trained on 323 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following metrics deviate from their learned-healthy baseline. Treat each as a semantic observation (meaning + numbers), not a number alone — the KB's interpretation is the authoritative reading.

- **`normalized.icscf.core:rcv_requests_invite_per_ue`** (SIP INVITE rate per UE at I-CSCF) — current **0.01 requests_per_second** vs learned baseline **0.00 requests_per_second** (MEDIUM, spike)
    - **What it measures:** Health of call-setup forwarding P-CSCF → I-CSCF. Partition signature
same as REGISTER rate.
    - **Spike means:** Forwarding failure.
    - **Healthy typical range:** 0–0.2 requests_per_second
    - **Healthy invariant:** Per-UE rate. Tracks pcscf.invite rate.

- **`normalized.pcscf.core:rcv_requests_invite_per_ue`** (SIP INVITE rate per UE at P-CSCF) — current **0.03 requests_per_second** vs learned baseline **0.00 requests_per_second** (MEDIUM, spike)
    - **What it measures:** Call attempt rate from registered UEs. Unlike REGISTER (periodic),
INVITEs only fire when UEs place calls. Zero is normal during
quiet periods; nonzero INVITE with zero dialogs is the signature
of call setup failure.
    - **Spike means:** Fewer call attempts.
    - **Healthy typical range:** 0–0.2 requests_per_second
    - **Healthy invariant:** Per-UE rate.

- **`normalized.scscf.core:rcv_requests_invite_per_ue`** (SIP INVITE rate per UE at S-CSCF) — current **0.03 requests_per_second** vs learned baseline **0.00 requests_per_second** (MEDIUM, spike)
    - **What it measures:** S-CSCF participation in call setup. Zero when calls aren't being
placed OR S-CSCF not receiving forwarded INVITEs.
    - **Spike means:** Upstream forwarding issue.
    - **Healthy typical range:** 0–0.2 requests_per_second
    - **Healthy invariant:** Per-UE rate.

- **`normalized.smf.bearers_per_ue`** (Active QoS bearers per UE) — current **0.00 count** vs learned baseline **2.48 count** (MEDIUM, drop)
    - **What it measures:** Per-UE count of active QoS bearers. Baseline reflects default
bearers; increments during VoNR calls indicate dedicated voice
bearers being set up. Drop during an active call = dedicated
bearer torn down unexpectedly (voice will fail).
    - **Drop means:** Lost bearers. If sustained during a call, voice path is broken.
    - **Healthy typical range:** 2–3.5 count
    - **Healthy invariant:** At rest: equals configured default bearers (typically 2 per UE).
During active VoNR call: +1 per caller. The per-UE ratio is the
invariant; absolute count scales with UE pool.

- **`normalized.smf.sessions_per_ue`** (PDU sessions per attached UE) — current **0.00 count** vs learned baseline **2.00 count** (MEDIUM, drop)
    - **What it measures:** Ratio of established PDU sessions to RAN-attached UEs. Constant under
healthy operation (depends on configured APNs per UE). Drift means
some UEs lost or failed to establish their sessions — usually points
to SMF or UPF control-plane issues, since attachment (ran_ue) is
independent of session establishment.
    - **Drop means:** Some UEs have fewer PDU sessions than they should. Likely SMF or PFCP (N4) issues.
    - **Healthy typical range:** 1.9–2.1 count
    - **Healthy invariant:** Constant equal to configured_apns_per_ue (typically 2). Scale-independent.

- **`normalized.upf.gtp_indatapktn3upf_per_ue`** (GTP-U uplink rate per UE (N3)) — current **0.00 packets_per_second** vs learned baseline **1.45 packets_per_second** (HIGH, drop)
    - **What it measures:** Health of the uplink user-plane path gNB → UPF. Drops to near-zero
during RAN or N3 outage; stays nonzero during active calls or data
sessions. Decoupled from SIP signaling (signals data plane, not
control plane).
    - **Drop means:** Data plane dead on uplink — UPF receiving no packets from gNB.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE — constant regardless of UE pool size. Rises during active VoNR calls (~100 pps for G.711 voice) and data transfer.

- **`normalized.upf.gtp_outdatapktn3upf_per_ue`** (GTP-U downlink rate per UE (N3)) — current **0.00 packets_per_second** vs learned baseline **1.45 packets_per_second** (HIGH, drop)
    - **What it measures:** Health of the downlink user-plane path UPF → gNB. Typically mirrors
uplink rate during calls/data; asymmetry indicates directional
faults (e.g., UPF receiving from internet but not forwarding).
    - **Drop means:** No traffic leaving UPF toward RAN.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE — constant regardless of UE pool size. Roughly symmetric with uplink during healthy calls.

- **`normalized.icscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at I-CSCF) — current **0.03 requests_per_second** vs learned baseline **0.06 requests_per_second** (LOW, drop)
    - **What it measures:** Health of the P-CSCF → I-CSCF forwarding path (Mw interface). When
this drops to zero while P-CSCF REGISTER rate is still non-zero,
it's the SIGNATURE of an IMS partition between P-CSCF and I-CSCF.
    - **Drop means:** Either UEs not registering at all, or P-CSCF isolated from I-CSCF.
    - **Healthy typical range:** 0–0.5 requests_per_second
    - **Healthy invariant:** Per-UE rate. Should closely track ims.pcscf.rcv_requests_register_per_ue.

- **`normalized.pcscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at P-CSCF) — current **0.03 requests_per_second** vs learned baseline **0.06 requests_per_second** (LOW, drop)
    - **What it measures:** How actively UEs are refreshing their IMS registrations with the
P-CSCF. REGISTERs arrive periodically (re-registration timer) plus
at attach. Sustained zero means UEs cannot reach P-CSCF OR the
UE-to-network SIP path is broken.
    - **Drop means:** No REGISTERs flowing. Unusual unless UEs are all deregistered.
    - **Healthy typical range:** 0–0.5 requests_per_second
    - **Healthy invariant:** Per-UE rate — same value at any deployment scale.

- **`normalized.scscf.cdp_replies_per_ue`** (S-CSCF CDP Diameter replies per UE) — current **0.03 replies_per_second_per_ue** vs learned baseline **0.06 replies_per_second_per_ue** (LOW, drop)
    - **What it measures:** Active S-CSCF Diameter traffic with HSS. Near-zero when registrations idle OR HSS partition.
    - **Drop means:** No active S-CSCF Diameter exchanges (idle or partitioned).
    - **Healthy typical range:** 0–1 replies_per_second_per_ue
    - **Healthy invariant:** Per-UE rate; varies with registration/auth load.


## Event Aggregation (Phase 1)

**1 events fired during the observation window:**

- `core.smf.sessions_per_ue_drop` (source: `core.smf.sessions_per_ue`, nf: `smf`, t=1777481733.6)  [current_value=0.0, prior_stable_value=2.0, delta_percent=-100.0]

## Correlation Analysis (Phase 2)

1 events fired but no composite hypothesis emerged. The events may be from independent faults or lack registered correlation hints in the KB.

## Network Analysis (Phase 3)

**Summary:** The AMF container has exited, causing a complete failure of all UE-related procedures including registration and session establishment, which has in turn broken the data plane and impacted IMS services.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | With the exception of the AMF container, all other infrastructure and network function containers appear to be running. |
| **ran** | 🟡 YELLOW | The RAN itself is likely functional, but it has no path to the core network due to the AMF failure. Data plane traffic to and from the RAN is at zero. |
| **core** | 🔴 RED | The AMF, a critical core component, has terminated. This prevents all UE access and session management, causing cascading failures in the SMF and UPF. |
| **ims** | 🟡 YELLOW | IMS registration rates have dropped significantly. This is a direct consequence of UEs being unable to establish the necessary PDU sessions through the 5G core. |

**RAN evidence:**
- normalized.upf.gtp_indatapktn3upf_per_ue
- normalized.upf.gtp_outdatapktn3upf_per_ue

**CORE evidence:**
- core.smf.sessions_per_ue_drop
- get_network_status: amf container exited

**IMS evidence:**
- normalized.pcscf.core:rcv_requests_register_per_ue
- normalized.icscf.core:rcv_requests_register_per_ue

**Ranked hypotheses:**

- **`h1`** (fit=0.99, nf=amf, specificity=specific):
    - **Statement:** The Access and Mobility Management Function (AMF) container has exited. This is a fatal control-plane failure that prevents UEs from registering with the network, leading to a complete loss of PDU session establishment and a collapse of all user-plane and subsequent IMS activity.
    - **Supporting events:** `core.smf.sessions_per_ue_drop`
    - **Falsification probes:**
        - Check the Docker/container runtime logs for the AMF container to determine why it exited.
        - Attempt to restart the AMF container and observe if UE registration and PDU session establishment resume.


## Falsification Plans (Phase 4)

**1 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `amf`)

**Hypothesis:** The Access and Mobility Management Function (AMF) container has exited. This is a fatal control-plane failure that prevents UEs from registering with the network, leading to a complete loss of PDU session establishment and a collapse of all user-plane and subsequent IMS activity.

**Probes (3):**
1. **`get_network_status`** — Check the status of the 'amf' container.
    - *Expected if hypothesis holds:* The 'amf' container is reported as 'exited' or otherwise not running.
    - *Falsifying observation:* The 'amf' container is reported as 'running'.
2. **`check_process_listeners`** — container="amf"
    - *Expected if hypothesis holds:* The tool returns an error or an empty list, as no process should be listening for connections in an exited container.
    - *Falsifying observation:* The tool returns a list of active listening ports, which would indicate the AMF process is running.
3. **`measure_rtt`** — from="nr_gnb", to_ip="amf"
    - *Expected if hypothesis holds:* 100% packet loss. The AMF container is down and its IP should be unreachable.
    - *Falsifying observation:* Normal RTT (<10ms) and 0% packet loss, indicating the container is up and its network stack is responsive.

*Notes:* This plan directly tests the central claim of the hypothesis: that the AMF container has exited. The probes verify this at the infrastructure, process, and network layers.


## Parallel Investigators (Phase 5)

**1 sub-Investigator verdict(s):** **1 NOT_DISPROVEN**

### `h1` — ✅ **NOT_DISPROVEN**

**Hypothesis:** The Access and Mobility Management Function (AMF) container has exited. This is a fatal control-plane failure that prevents UEs from registering with the network, leading to a complete loss of PDU session establishment and a collapse of all user-plane and subsequent IMS activity.

**Reasoning:** All three probes executed returned results that are consistent with the hypothesis. The 'amf' container is confirmed to be in an 'exited' state, its processes are not listening, and its IP address is unreachable on the network. No contradictory evidence was found.

**Probes executed (3):**
- **Check the status of the 'amf' container.** ✓ CONSISTENT
    - *Tool:* `print(default_api.get_network_status())`
    - *Observation:* [EVIDENCE: get_network_status() -> "'amf': 'exited'"]
    - *Comment:* The get_network_status tool confirmed that the AMF container has an 'exited' status, which directly supports the hypothesis.
- **container="amf"** ✓ CONSISTENT
    - *Tool:* `print(default_api.check_process_listeners(container='amf'))`
    - *Observation:* [EVIDENCE: check_process_listeners("amf") -> "Error response from daemon: container ... is not running"]
    - *Comment:* The tool reported that the container is not running, which is the expected outcome for an exited container. Therefore, no processes can be listening for connections.
- **from="nr_gnb", to_ip="amf"** ✓ CONSISTENT
    - *Tool:* `print(default_api.measure_rtt(container = "upf", target_ip = "172.22.0.10"))`
    - *Observation:* [EVIDENCE: measure_rtt("upf", "172.22.0.10") -> "100% packet loss"]
    - *Comment:* Pinging the AMF's IP address (172.22.0.10) from the UPF resulted in 100% packet loss. This confirms the AMF is unreachable at the network layer, as expected if the container is down.


## Evidence Validation (Phase 6)

**Overall verdict:** clean
**Overall confidence:** high

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 4 | 3/3 | clean | high |


## Ground Truth

**Failure domain:** core_control_plane  
**Protocol impact:** NGAP  
**Affected components:** amf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v6-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 106.4s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: The Access and Mobility Management Function (AMF) container has exited, causing a complete control plane failure that has severed the RAN from the core network, preventing all user equipment from registering or establishing data sessions.
> - **timeline**:
>     1. The `amf` container terminated unexpectedly.
>     2. UE registration requests began to fail as they could no longer reach a functional AMF.
>     3. The SMF observed a drop in established PDU sessions as new ones could not be created and existing ones may have timed out.
>     4. Data plane traffic to and from the RAN dropped to zero due to the lack of active PDU sessions.
>     5. IMS registration rates collapsed because UEs could not establish the necessary underlying connectivity to the IMS platform.
> - **root_cause**: The `amf` container, a critical 5G control plane component, is no longer running. The primary suspect is `amf`.
> - **affected_components**:
>     - `amf`: Root Cause
>     - `smf`: Secondary
>     - `upf`: Secondary
>     - `ran`: Symptomatic
>     - `ims`: Symptomatic
> - **recommendation**: The operator should inspect the logs of the exited `amf` container to determine the reason for its termination (e.g., an application error, out-of-memory exception, or misconfiguration).
> - **confidence**: high
> - **explanation**: The investigation has confirmed with high confidence that the root cause is the failure of the AMF container. The primary hypothesis (`h1`)—that an AMF container exit would cause a catastrophic failure of UE registration and session establishment—was directly validated by probe results. Evidence confirmed the `amf` container is in an 'exited' state and is unreachable on the network. This single control-plane failure fully explains the cascading symptoms observed across the core, RAN, and IMS layers, including the drop in PDU sessions and the halt of all user plane traffic. No conflicting evidence was found.

### Scoring Breakdown

**Overall score: 100%**

**Scorer assessment:** The agent provided an excellent and highly accurate diagnosis, correctly identifying the root cause, affected components, severity, and fault type, with appropriate confidence and layer attribution.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | Yes | The agent correctly identified the AMF as the root cause, stating that the 'amf container... is no longer running' and is in an 'exited' state, which directly matches the simulated failure mode of the AMF being temporarily unavailable/stopped. |
| Component overlap | 100% | The primary affected component, 'amf', is correctly listed as 'Root Cause' in the `affected_components` list. |
| Severity correct | Yes | The agent described the failure as a 'complete control plane failure' and 'catastrophic failure of UE registration and session establishment', which accurately reflects the impact of the AMF being stopped and UEs losing NAS connection and requiring re-attachment. |
| Fault type identified | Yes | The agent identified the fault type as the 'amf container... no longer running' and in an 'exited' state, making it 'unreachable on the network'. This correctly describes the observable state of the component (unreachable/down). |
| Layer accuracy | Yes | The ground truth states that 'amf' belongs to the 'core' layer. The agent's network analysis correctly rated the 'core' layer as 'red' and explicitly noted that 'The AMF, a critical core component, has terminated.' |
| Confidence calibrated | Yes | The agent stated 'high' confidence, which is appropriate given that its diagnosis is accurate across all dimensions and supported by clear evidence (AMF container exited, unreachable). |

**Ranking position:** #1 — The agent provided a single, clear root cause, which was correct.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 91,207 |
| Output tokens | 2,149 |
| Thinking tokens | 6,994 |
| **Total tokens** | **100,350** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| EventAggregator | 0 | 0 | 0 |
| CorrelationAnalyzer | 0 | 0 | 0 |
| NetworkAnalystAgent | 39,459 | 5 | 3 |
| InstructionGeneratorAgent | 15,189 | 1 | 2 |
| InvestigatorAgent_h1 | 42,144 | 4 | 5 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 3,558 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 248.5s
