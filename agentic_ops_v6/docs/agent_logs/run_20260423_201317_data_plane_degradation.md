# Episode Report: Data Plane Degradation

**Agent:** v6  
**Episode ID:** ep_20260423_200727_data_plane_degradation  
**Date:** 2026-04-23T20:07:29.463556+00:00  
**Duration:** 347.6s  

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
- **Nodes with significant deltas:** 5
- **Nodes with any drift:** 6

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 0.90 (threshold: 0.70, trained on 211 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following metrics deviate from their learned-healthy baseline. Treat each as a semantic observation (meaning + numbers), not a number alone — the KB's interpretation is the authoritative reading.

- **`normalized.upf.gtp_outdatapktn3upf_per_ue`** (GTP-U downlink rate per UE (N3)) — current **0.03 packets_per_second** vs learned baseline **3.34 packets_per_second** (MEDIUM, drop)
    - **What it measures:** Health of the downlink user-plane path UPF → gNB. Typically mirrors
uplink rate during calls/data; asymmetry indicates directional
faults (e.g., UPF receiving from internet but not forwarding).
    - **Drop means:** No traffic leaving UPF toward RAN.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE — constant regardless of UE pool size. Roughly symmetric with uplink during healthy calls.

- **`normalized.upf.gtp_indatapktn3upf_per_ue`** (GTP-U uplink rate per UE (N3)) — current **0.10 packets_per_second** vs learned baseline **3.42 packets_per_second** (MEDIUM, drop)
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

**Summary:** The root cause of the outage is a data plane failure, which is a consequence of a control plane fault. The P-CSCF is unable to connect to the PCF, which prevents VoNR call setup and results in no user plane traffic.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | All containers are running and network links are reported as active. |
| **ran** | 🟢 GREEN | The RAN appears to be up and connected to the core, with 2 UEs attached. |
| **core** | 🔴 RED | The user plane is down. The issue appears to originate from a control plane failure preventing call setup, specifically between the P-CSCF and PCF. |
| **ims** | 🔴 RED | Call setup is failing at the P-CSCF. It is unable to connect to the PCF over the Rx interface to authorize QoS for VoNR calls. |

**CORE evidence:**
- normalized.upf.gtp_outdatapktn3upf_per_ue = 0.03
- normalized.upf.gtp_indatapktn3upf_per_ue = 0.10

**IMS evidence:**
- normalized.pcscf.dialogs_per_ue = 0.00
- pcscf.httpclient:connfail = 138.0
- pcscf.httpclient:connok = 0.0

**Ranked hypotheses:**

- **`h1`** (fit=0.90, nf=pcscf, specificity=specific):
    - **Statement:** The P-CSCF is unable to establish a connection with the PCF over the Rx interface, as evidenced by a high number of HTTP client connection failures (138) and zero successful connections. This failure prevents the P-CSCF from obtaining QoS rules for VoNR calls, causing call setup to fail, which in turn leads to no active SIP dialogs and no user plane traffic.
    - **Supporting events:** `normalized.pcscf.dialogs_per_ue`, `normalized.upf.gtp_outdatapktn3upf_per_ue`, `normalized.upf.gtp_indatapktn3upf_per_ue`
    - **Falsification probes:**
        - Check P-CSCF logs for specific error messages regarding connection attempts to the PCF's IP address.
        - Check PCF logs to confirm it is not receiving any incoming HTTP requests from the P-CSCF.
        - Measure network connectivity (ping, traceroute) from the 'pcscf' container to the 'pcf' container; high RTT or packet loss would confirm a network-level partition.
- **`h2`** (fit=0.40, nf=icscf, specificity=moderate):
    - **Statement:** The I-CSCF is experiencing intermittent timeouts when communicating with the HSS over the Cx interface. This could delay or fail user registration and authentication, preventing calls from being made.
    - **Falsification probes:**
        - Check the 'pyhss' logs for Diameter errors or timeouts corresponding to requests from the I-CSCF.
        - Measure RTT from the 'icscf' container to the 'pyhss' container; elevated RTT would indicate a network problem.
- **`h3`** (fit=0.30, nf=upf, specificity=moderate):
    - **Statement:** The UPF has an internal fault or misconfiguration that is causing it to drop all user plane packets. Although control plane functions appear active, the data packets for established PDU sessions are not being forwarded.
    - **Supporting events:** `normalized.upf.gtp_outdatapktn3upf_per_ue`, `normalized.upf.gtp_indatapktn3upf_per_ue`
    - **Falsification probes:**
        - Inspect the UPF's running configuration for errors or anomalies.
        - Check SMF logs for any N4 interface errors reported when trying to manage sessions on the UPF.
        - Review UPF logs for any internal error messages related to packet forwarding.


## Falsification Plans (Phase 4)

**3 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `pcscf`)

**Hypothesis:** The P-CSCF is unable to establish a connection with the PCF over the Rx interface, as evidenced by a high number of HTTP client connection failures (138) and zero successful connections. This failure prevents the P-CSCF from obtaining QoS rules for VoNR calls, causing call setup to fail, which in turn leads to no active SIP dialogs and no user plane traffic.

**Probes (3):**
1. **`measure_rtt`** — from 'pcscf' to 'pcf' container's IP
    - *Expected if hypothesis holds:* High RTT or 100% packet loss, confirming a network partition.
    - *Falsifying observation:* Clean RTT (< 5ms) and no packet loss, indicating the transport layer is healthy.
2. **`measure_rtt`** — from 'pcscf' to 'icscf' container's IP (triangulation)
    - *Expected if hypothesis holds:* Clean RTT (< 5ms), as the hypothesis is specific to the P-CSCF->PCF path.
    - *Falsifying observation:* High RTT or packet loss, which would indicate a broader networking problem with the P-CSCF container itself, not a specific path.
3. **`check_process_listeners`** — on container 'pcf'
    - *Expected if hypothesis holds:* The PCF process is listening on its configured Rx/N5 interface port.
    - *Falsifying observation:* The PCF process is not listening on its Rx/N5 port, which would make the PCF itself the likely root cause, rather than the network path from the P-CSCF.

*Notes:* This plan focuses on falsifying the 'network partition' interpretation of hypothesis h1. Probes are anchored to the 'vonr_call_setup' flow, step 2 ('N5 App Session Create'), which is the point of failure described.

### Plan for `h2` (target: `icscf`)

**Hypothesis:** The I-CSCF is experiencing intermittent timeouts when communicating with the HSS over the Cx interface. This could delay or fail user registration and authentication, preventing calls from being made.

**Probes (3):**
1. **`measure_rtt`** — from 'icscf' to 'pyhss' container's IP
    - *Expected if hypothesis holds:* Elevated RTT (>10ms) or intermittent packet loss.
    - *Falsifying observation:* Consistently low RTT (< 5ms) and no packet loss.
2. **`measure_rtt`** — from 'udm' to 'pyhss' container's IP (triangulation)
    - *Expected if hypothesis holds:* Elevated RTT, similar to the icscf->pyhss probe, if the HSS or its immediate network is slow.
    - *Falsifying observation:* Clean RTT (< 5ms), which would isolate the latency problem to the I-CSCF's client or its specific network path.
3. **`query_subscriber`** — IMSI for any known-good subscriber, e.g. 'imsi-001010000000001'
    - *Expected if hypothesis holds:* The query is slow to return (>100ms) or times out.
    - *Falsifying observation:* The query returns quickly (<50ms) with a full subscriber profile, demonstrating the HSS is alive and responsive.

*Notes:* This plan attempts to isolate the 'intermittent timeouts' described in h2. Probes test the network path from multiple angles and check the liveness of the HSS directly, which would disambiguate a slow HSS from a network issue between I-CSCF and HSS.

### Plan for `h3` (target: `upf`)

**Hypothesis:** The UPF has an internal fault or misconfiguration that is causing it to drop all user plane packets. Although control plane functions appear active, the data packets for established PDU sessions are not being forwarded.

**Probes (3):**
1. **`read_running_config`** — container 'upf'
    - *Expected if hypothesis holds:* An anomaly or misconfiguration is found in the UPF's bessd.conf file.
    - *Falsifying observation:* The configuration is verified as correct against the expected network deployment.
2. **`get_nf_metrics`** — Check the gNB's outbound GTP-U packet counter (e.g., metric name containing 'gtp_outdatapktn3gnb')
    - *Expected if hypothesis holds:* The gNB's outbound N3 packet counter is > 0, indicating it is sending traffic to the UPF.
    - *Falsifying observation:* The gNB's outbound N3 packet counter is 0. This would prove the fault lies upstream of the UPF, as the UPF cannot drop packets it never receives.
3. **`get_nf_metrics`** — Check the SMF's active N4 session counter (e.g., metric name containing 'n4_sessions')
    - *Expected if hypothesis holds:* The number of active N4 sessions on the SMF is > 0.
    - *Falsifying observation:* The number of active N4 sessions is 0, which contradicts the hypothesis's premise that the control plane is active. A failure to establish N4 sessions would be the root cause.

*Notes:* This plan uses the 'activity-vs-drops' pattern. Probe 2 checks if the upstream component (gNB) is sending data. If not, the hypothesis that UPF is 'dropping' it is falsified. Probes 1 and 3 check the control plane preconditions for UPF activity.


## Parallel Investigators (Phase 5)

**3 sub-Investigator verdict(s):** **2 DISPROVEN**, **1 NOT_DISPROVEN**

### `h1` — ❌ **DISPROVEN**

**Hypothesis:** The P-CSCF is unable to establish a connection with the PCF over the Rx interface, as evidenced by a high number of HTTP client connection failures (138) and zero successful connections. This failure prevents the P-CSCF from obtaining QoS rules for VoNR calls, causing call setup to fail, which in turn leads to no active SIP dialogs and no user plane traffic.

**Reasoning:** The hypothesis implies a network-level connectivity issue between the P-CSCF and the PCF. However, my probes directly contradict this. The `measure_rtt` probe from P-CSCF to PCF shows a perfectly healthy transport path with no packet loss and sub-millisecond latency. While the symptom of 'connection failures' is correct, the underlying cause is not a network partition. The failure must be occurring at a higher layer, such as an application-level (HTTP/TLS) configuration mismatch between the P-CSCF and PCF.

**Probes executed (3):**
- **from 'pcscf' to 'pcf' container's IP** ✗ CONTRADICTS
    - *Tool:* `measure_rtt("pcscf", "172.22.0.27")`
    - *Observation:* [EVIDENCE: measure_rtt("pcscf", "172.22.0.27") -> "3 packets transmitted, 3 received, 0% packet loss, time 2027ms\nrtt min/avg/max/mdev = 0.086/0.158/0.300/0.100 ms"]
    - *Comment:* The clean RTT and 0% packet loss directly contradict the expectation of a network partition (high RTT/loss). This falsifies the idea that the P-CSCF is unable to establish a connection at the network transport layer.
- **from 'pcscf' to 'icscf' container's IP (triangulation)** ✓ CONSISTENT
    - *Tool:* `measure_rtt("pcscf", "172.22.0.19")`
    - *Observation:* [EVIDENCE: measure_rtt("pcscf", "172.22.0.19") -> "3 packets transmitted, 3 received, 0% packet loss, time 2039ms\nrtt min/avg/max/mdev = 0.051/0.088/0.151/0.044 ms"]
    - *Comment:* The clean RTT to a different NF confirms that the P-CSCF's own network stack is healthy, reinforcing that the issue is specific to the P-CSCF-PCF interaction, not a general failure of the P-CSCF container.
- **on container 'pcf'** ✓ CONSISTENT
    - *Tool:* `check_process_listeners("pcf")`
    - *Observation:* [EVIDENCE: check_process_listeners("pcf") -> "tcp   LISTEN 0      5        172.22.0.27:7777       0.0.0.0:*    users:((\"open5gs-pcfd\",pid=8,fd=12))\ntcp   LISTEN 0      4096     172.22.0.27:9091       0.0.0.0:*    users:((\"open5gs-pcfd\",pid=8,fd=10))"]
    - *Comment:* The PCF process is listening on its IP address, meaning it is ready to accept incoming connections. This is consistent with the hypothesis but, combined with the other probes, suggests the failure occurs after the initial TCP SYN packet.

**Alternative suspects:** pcf

### `h2` — ❌ **DISPROVEN**

**Hypothesis:** The I-CSCF is experiencing intermittent timeouts when communicating with the HSS over the Cx interface. This could delay or fail user registration and authentication, preventing calls from being made.

**Reasoning:** All probes executed directly contradict the hypothesis. Network RTT between the I-CSCF and HSS is excellent, with no packet loss. A triangulation probe from the UDM to the HSS also shows a healthy, low-latency connection. Finally, a direct query to the HSS for a subscriber profile returned a full record quickly, proving the HSS is alive and responsive. There is no evidence of timeouts or network issues on the Cx interface.

**Probes executed (3):**
- **from 'icscf' to 'pyhss' container's IP** ✗ CONTRADICTS
    - *Tool:* `default_api.measure_rtt(container='icscf', target_ip='172.22.0.18')`
    - *Observation:* [EVIDENCE: measure_rtt("icscf", "172.22.0.18") -> "rtt min/avg/max/mdev = 0.067/0.091/0.129/0.026 ms"]
    - *Comment:* The RTT is extremely low (<1ms), which contradicts the expectation of elevated RTT (>10ms). This indicates a healthy network path between the I-CSCF and the HSS.
- **from 'udm' to 'pyhss' container's IP (triangulation)** ✗ CONTRADICTS
    - *Tool:* `default_api.measure_rtt(container='udm', target_ip='172.22.0.18')`
    - *Observation:* [EVIDENCE: measure_rtt("udm", "172.22.0.18") -> "rtt min/avg/max/mdev = 0.037/0.182/0.441/0.183 ms"]
    - *Comment:* This triangulation probe also shows a very low RTT, confirming the HSS and its network path are healthy from a different source NF. This rules out the HSS itself being the source of any potential slowness.
- **IMSI for any known-good subscriber, e.g. 'imsi-001010000000001'** ✗ CONTRADICTS
    - *Tool:* `default_api.query_subscriber(imsi='001011234567891')`
    - *Observation:* [EVIDENCE: query_subscriber("001011234567891") -> "{\"core_5g\": {\"_id\": \"69e6d7b7e60d585d99783d8c\", \"imsi\": \"001011234567891\", ...}, \"ims_subscriber\": {...}, \"ims_details\": {...}}"]
    - *Comment:* The query returned a full subscriber profile successfully and quickly. This directly contradicts the hypothesis that the HSS is slow to respond or timing out.

### `h3` — ✅ **NOT_DISPROVEN**

**Hypothesis:** The UPF has an internal fault or misconfiguration that is causing it to drop all user plane packets. Although control plane functions appear active, the data packets for established PDU sessions are not being forwarded.

**Reasoning:** Probes revealed that the UPF is receiving data plane packets but not sending any, while control plane N4 sessions are established. This directly aligns with the hypothesis's claim of a data plane fault despite an active control plane. An attempt to read the UPF's running configuration failed, making that specific probe inconclusive, but the available evidence from traffic rates and session metrics supports the hypothesis.

**Probes executed (3):**
- **Check the SMF's active N4 session counter (e.g., metric name containing 'n4_sessions')** ✓ CONSISTENT
    - *Tool:* `print(default_api.get_nf_metrics())`
    - *Observation:* [EVIDENCE: get_nf_metrics() -> "SMF [4 PDU] (via prometheus):...pfcp_sessions_active = 4.0"]
    - *Comment:* The presence of 4 active PFCP (N4) sessions on the SMF confirms the hypothesis's premise that the control plane is active and has instructed the UPF to establish PDU sessions.
- **Check the gNB's outbound GTP-U packet counter (e.g., metric name containing 'gtp_outdatapktn3gnb')** ✓ CONSISTENT
    - *Tool:* `print(default_api.get_dp_quality_gauges())`
    - *Observation:* [EVIDENCE: get_dp_quality_gauges() -> "UPF: in packets/sec: 0.2, out packets/sec: 0.0"]
    - *Comment:* The UPF is receiving packets on its ingress interface (implying the gNB is sending them) but is forwarding zero packets on its egress. This strongly supports the hypothesis that the UPF is dropping user plane packets.
- **An anomaly or misconfiguration is found in the UPF's bessd.conf file.** ~ AMBIGUOUS
    - *Tool:* `print(default_api.read_running_config(container='upf', grep='access|core'))`
    - *Observation:* [EVIDENCE: read_running_config("upf", "access|core") -> "Failed to read config from upf:/open5gs/install/etc/open5gs/upf.yaml — "]
    - *Comment:* The tool failed to read the UPF's configuration file, so it was not possible to check for a misconfiguration. This probe is inconclusive and neither supports nor contradicts the hypothesis.


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

**Failure domain:** data_plane  
**Protocol impact:** GTP-U  
**Affected components:** upf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v6-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 210.4s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: The root cause of the outage is a data plane failure within the UPF, which is dropping all user plane traffic despite a healthy control plane.
> - **timeline**:
>     1. The control plane successfully establishes PDU sessions, confirmed by the SMF reporting 4 active N4 sessions with the UPF.
>     2. The RAN sends user plane packets to the UPF's N3 interface.
>     3. The UPF receives these packets (ingress rate > 0) but fails to forward any packets to the data network via its N6 interface (egress rate = 0).
>     4. This complete packet loss in the user plane prevents all data services, including VoNR call setup, which fails due to the inability to establish a media path.
> - **root_cause**: The UPF has an internal fault or misconfiguration causing it to drop all user plane packets. The control plane appears to be functioning correctly, as the SMF has established active PDU sessions, but the UPF's data plane is not forwarding any traffic. The primary suspect is `upf`.
> - **affected_components**:
>     - `upf`: Root Cause
>     - `core`: Secondary (The user plane is down due to the UPF fault)
>     - `ims`: Symptomatic (VoNR call setup fails because the required user plane cannot be established)
> - **recommendation**: Manually inspect the UPF's running configuration for errors, as automated checks were unable to read the file. Review the internal logs of the `upf` container for any error messages related to packet processing or forwarding failures.
> - **confidence**: high
> - **explanation**: The investigation confirmed a data plane failure isolated to the UPF. Initial hypotheses suggesting control plane issues, such as a P-CSCF to PCF connection failure (`h1`) or an I-CSCF to HSS timeout (`h2`), were disproven by probes showing healthy network connectivity on those interfaces. The surviving hypothesis (`h3`), which posited an internal UPF fault, was validated by metrics showing the UPF receives user plane packets but transmits none, despite the SMF confirming that control plane sessions are active. This isolates the fault to the UPF's packet forwarding logic.

### Scoring Breakdown

**Overall score: 85%**

**Scorer assessment:** The agent accurately identified the UPF as the component experiencing a data plane packet loss issue, but it overestimated the severity of the problem, diagnosing a complete outage instead of a degradation.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | Yes | The agent correctly identified the UPF as the root cause and a data plane failure involving packet dropping/loss. While the simulated failure was 30% packet loss and the agent diagnosed 100% packet loss ('dropping all user plane traffic', 'egress rate = 0'), the fundamental root cause (packet loss on UPF) is correctly identified. |
| Component overlap | 100% | The agent explicitly listed 'upf' as the 'Root Cause' in its 'affected_components' list, which is the correct primary affected component. |
| Severity correct | No | The simulated failure was a degradation (30% packet loss), but the agent diagnosed a complete outage ('dropping all user plane traffic', 'egress rate = 0', 'complete packet loss'). |
| Fault type identified | Yes | The agent clearly identified a 'data plane failure' involving 'dropping all user plane packets' and 'complete packet loss', which accurately describes a packet loss/forwarding failure. |
| Layer accuracy | Yes | The 'upf' belongs to the 'core' layer. The agent's 'NETWORK ANALYSIS' correctly rated the 'core' layer as 'red' and provided UPF-related metrics as evidence. The final diagnosis also correctly identifies 'core' as an affected layer. |
| Confidence calibrated | Yes | The agent's diagnosis correctly identified the component, the type of fault, and the affected layer. The only inaccuracy was the severity (100% loss vs 30% loss). Given the strong identification of the core problem, 'high' confidence is reasonable. |

**Ranking position:** #1 — The agent provided a single, clear root cause in its final diagnosis, with 'upf' explicitly labeled as 'Root Cause' in 'affected_components'.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 172,060 |
| Output tokens | 5,855 |
| Thinking tokens | 18,970 |
| **Total tokens** | **196,885** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| EventAggregator | 0 | 0 | 0 |
| CorrelationAnalyzer | 0 | 0 | 0 |
| NetworkAnalystAgent | 40,816 | 4 | 3 |
| InstructionGeneratorAgent | 23,898 | 1 | 2 |
| InvestigatorAgent_h1 | 46,777 | 4 | 5 |
| InvestigatorAgent_h2 | 28,453 | 4 | 3 |
| InvestigatorAgent_h3 | 50,033 | 3 | 4 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 6,908 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 347.6s
