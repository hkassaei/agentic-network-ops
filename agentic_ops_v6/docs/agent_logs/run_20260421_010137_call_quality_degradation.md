# Episode Report: Call Quality Degradation

**Agent:** v6  
**Episode ID:** ep_20260421_005701_call_quality_degradation  
**Date:** 2026-04-21T00:57:03.199213+00:00  
**Duration:** 273.9s  

---

## Scenario

**Category:** network  
**Blast radius:** single_nf  
**Description:** Inject 30% packet loss on RTPEngine — the media relay for VoNR voice calls. RTP packets are dropped after RTPEngine receives them, degrading voice quality (MOS drop, jitter increase, audible artifacts). SIP signaling and 5G core are completely unaffected because they don't traverse RTPEngine. Tests whether the agent can diagnose a pure media-path fault without IMS signaling noise.

## Faults Injected

- **network_loss** on `rtpengine` — {'loss_pct': 30}

## Baseline (Pre-Fault)

Stack phase before injection: **ready**
All containers running at baseline.

## Fault Propagation Verification

**Verdict:** ✅ `confirmed`

- **Wait:** 0s
- **Actual elapsed:** 0.0s
- **Nodes with significant deltas:** 6
- **Nodes with any drift:** 6

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

### Metrics Changes

| Node | Metric | Baseline | Current | Delta |
|------|--------|----------|---------|-------|
| icscf | ims_icscf:lir_replies_received | 0.0 | 2.0 | 2.0 |
| icscf | core:rcv_requests_invite | 0.0 | 2.0 | 2.0 |
| icscf | ims_icscf:lir_replies_response_time | 0.0 | 69.0 | 69.0 |
| icscf | ims_icscf:lir_avg_response_time | 0.0 | 34.0 | 34.0 |
| pcscf | httpclient:connok | 0.0 | 10.0 | 10.0 |
| pcscf | core:rcv_requests_bye | 0.0 | 2.0 | 2.0 |
| pcscf | dialog_ng:processed | 0.0 | 4.0 | 4.0 |
| pcscf | dialog_ng:active | 0.0 | 2.0 | 2.0 |
| rtpengine | total_number_of_packet_loss_samples | 0.0 | 27.0 | 27.0 |
| rtpengine | sum_of_all_end_to_end_round_trip_time_square_values_sampled | 0.0 | 1268345001.0 | 1268345001.0 |
| rtpengine | sum_of_all_mos_square_values_sampled | 0.0 | 391.92 | 391.92 |
| rtpengine | total_relayed_packets | 0.0 | 471.0 | 471.0 |
| rtpengine | total_relayed_bytes | 0.0 | 15936.0 | 15936.0 |
| rtpengine | total_number_of_mos_samples | 0.0 | 26.0 | 26.0 |
| rtpengine | end_to_end_round_trip_time_standard_deviation | 0.0 | 1838.0 | 1838.0 |
| rtpengine | discrete_round_trip_time_standard_deviation | 0.0 | 848.0 | 848.0 |
| rtpengine | average_discrete_round_trip_time | 0.0 | 3398.0 | 3398.0 |
| rtpengine | total_number_of_end_to_end_round_trip_time_samples | 0.0 | 27.0 | 27.0 |
| rtpengine | average_jitter_(reported) | 0.0 | 13.0 | 13.0 |
| rtpengine | average_mos | 0.0 | 3.7 | 3.7 |
| rtpengine | average_packet_loss | 0.0 | 30.0 | 30.0 |
| rtpengine | owned_sessions | 0.0 | 1.0 | 1.0 |
| rtpengine | total_number_of_jitter_(reported)_samples | 0.0 | 27.0 | 27.0 |
| rtpengine | sum_of_all_packet_loss_square_values_sampled | 0.0 | 30596.0 | 30596.0 |
| rtpengine | sum_of_all_end_to_end_round_trip_time_values_sampled | 0.0 | 178273.0 | 178273.0 |
| rtpengine | packets_per_second_(userspace) | 0.0 | 5.0 | 5.0 |
| rtpengine | bytes_per_second_(userspace) | 0.0 | 131.0 | 131.0 |
| rtpengine | sum_of_all_mos_values_sampled | 0.0 | 98.0 | 98.0 |
| rtpengine | total_relayed_packets_(userspace) | 0.0 | 471.0 | 471.0 |
| rtpengine | sum_of_all_jitter_(reported)_square_values_sampled | 0.0 | 24296.0 | 24296.0 |
| rtpengine | total_number_of_discrete_round_trip_time_samples | 0.0 | 27.0 | 27.0 |
| rtpengine | sum_of_all_jitter_(reported)_values_sampled | 0.0 | 368.0 | 368.0 |
| rtpengine | total_sessions | 0.0 | 1.0 | 1.0 |
| rtpengine | total_relayed_bytes_(userspace) | 0.0 | 15936.0 | 15936.0 |
| rtpengine | sum_of_all_discrete_round_trip_time_values_sampled | 0.0 | 91769.0 | 91769.0 |
| rtpengine | packets_per_second_(total) | 0.0 | 5.0 | 5.0 |
| rtpengine | sum_of_all_discrete_round_trip_time_square_values_sampled | 0.0 | 331331933.0 | 331331933.0 |
| rtpengine | sum_of_all_packet_loss_values_sampled | 0.0 | 828.0 | 828.0 |
| rtpengine | average_end_to_end_round_trip_time | 0.0 | 6602.0 | 6602.0 |
| rtpengine | packet_loss_standard_deviation | 0.0 | 13.0 | 13.0 |
| rtpengine | jitter_(reported)_standard_deviation | 0.0 | 26.0 | 26.0 |
| rtpengine | bytes_per_second_(total) | 0.0 | 131.0 | 131.0 |
| rtpengine | userspace_only_media_streams | 0.0 | 2.0 | 2.0 |
| scscf | dialog_ng:processed | 0.0 | 4.0 | 4.0 |
| scscf | dialog_ng:active | 0.0 | 2.0 | 2.0 |
| scscf | core:rcv_requests_invite | 0.0 | 4.0 | 4.0 |
| smf | bearers_active | 6.0 | 8.0 | 2.0 |
| upf | fivegs_ep_n3_gtp_outdatavolumeqosleveln3upf | 229092.0 | 320419.0 | 91327.0 |
| upf | fivegs_ep_n3_gtp_outdatapktn3upf | 356.0 | 938.0 | 582.0 |

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 0.92 (threshold: 0.70, trained on 211 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following metrics deviate from their learned-healthy baseline. Treat each as a semantic observation (meaning + numbers), not a number alone — the KB's interpretation is the authoritative reading.

- **`icscf.cdp:average_response_time`** (I-CSCF Diameter average response time) — current **70.00 ms** vs learned baseline **51.50 ms** (MEDIUM, shift)
    - **What it measures:** Responsiveness of the Cx path and HSS processing speed. A spike
without timeouts = pure latency; a spike WITH timeout_ratio rising
= approaching timeout ceiling (HSS overload or partial partition).
    - **Shift means:** HSS slow, network latency to HSS, or HSS overload.
    - **Healthy typical range:** 30–100 ms

- **`normalized.upf.gtp_indatapktn3upf_per_ue`** (GTP-U uplink rate per UE (N3)) — current **0.21 packets_per_second** vs learned baseline **3.42 packets_per_second** (MEDIUM, drop)
    - **What it measures:** Health of the uplink user-plane path gNB → UPF. Drops to near-zero
during RAN or N3 outage; stays nonzero during active calls or data
sessions. Decoupled from SIP signaling (signals data plane, not
control plane).
    - **Drop means:** Data plane dead on uplink — UPF receiving no packets from gNB.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE — constant regardless of UE pool size. Rises during active VoNR calls (~100 pps for G.711 voice) and data transfer.

- **`normalized.upf.gtp_outdatapktn3upf_per_ue`** (GTP-U downlink rate per UE (N3)) — current **0.35 packets_per_second** vs learned baseline **3.34 packets_per_second** (MEDIUM, drop)
    - **What it measures:** Health of the downlink user-plane path UPF → gNB. Typically mirrors
uplink rate during calls/data; asymmetry indicates directional
faults (e.g., UPF receiving from internet but not forwarding).
    - **Drop means:** No traffic leaving UPF toward RAN.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE — constant regardless of UE pool size. Roughly symmetric with uplink during healthy calls.

- **`icscf.ims_icscf:uar_avg_response_time`** (I-CSCF UAR response time) — current **70.00 ms** vs learned baseline **51.94 ms** (MEDIUM, shift)
    - **What it measures:** Specifically the UAR leg of the Cx interface. Spikes here without
LIR spikes are unusual — either UAR-handler issue at HSS or
specific network path to that code path.
    - **Shift means:** UAR-specific HSS slowness.
    - **Healthy typical range:** 30–100 ms

- **`scscf.ims_auth:mar_avg_response_time`** (S-CSCF MAR response time) — current **111.00 ms** vs learned baseline **91.62 ms** (MEDIUM, shift)
    - **What it measures:** S-CSCF side of the Cx interface. If MAR latency spikes alongside
I-CSCF UAR/LIR spikes, it's HSS-wide; if only MAR spikes, it's
S-CSCF ↔ HSS specific.
    - **Shift means:** HSS slow responding to MAR.
    - **Healthy typical range:** 50–150 ms

- **`derived.pcscf_avg_register_time_ms`** (P-CSCF average SIP REGISTER processing time) — current **107.90 ms** vs learned baseline **248.24 ms** (MEDIUM, drop)
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

- **`normalized.scscf.cdp_replies_per_ue`** — current **0.21** vs learned baseline **0.06** (LOW, spike). *(No KB context available — interpret from the metric name.)*

- **`normalized.scscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at S-CSCF) — current **0.21 requests_per_second** vs learned baseline **0.06 requests_per_second** (LOW, spike)
    - **What it measures:** Health of the I-CSCF → S-CSCF forwarding path. Drop to zero while
I-CSCF is receiving REGISTERs = S-CSCF-side issue (crashed, or
I-CSCF → S-CSCF path broken).
    - **Spike means:** I-CSCF not forwarding or S-CSCF not receiving.
    - **Healthy typical range:** 0–0.5 requests_per_second
    - **Healthy invariant:** Per-UE rate. Tracks icscf.register rate.

- **`normalized.pcscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at P-CSCF) — current **0.21 requests_per_second** vs learned baseline **0.06 requests_per_second** (LOW, spike)
    - **What it measures:** How actively UEs are refreshing their IMS registrations with the
P-CSCF. REGISTERs arrive periodically (re-registration timer) plus
at attach. Sustained zero means UEs cannot reach P-CSCF OR the
UE-to-network SIP path is broken.
    - **Spike means:** Fewer REGISTERs than expected — UE connectivity or P-CSCF reachability issue.
    - **Healthy typical range:** 0–0.5 requests_per_second
    - **Healthy invariant:** Per-UE rate — same value at any deployment scale.

- **`normalized.icscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at I-CSCF) — current **0.21 requests_per_second** vs learned baseline **0.06 requests_per_second** (LOW, spike)
    - **What it measures:** Health of the P-CSCF → I-CSCF forwarding path (Mw interface). When
this drops to zero while P-CSCF REGISTER rate is still non-zero,
it's the SIGNATURE of an IMS partition between P-CSCF and I-CSCF.
    - **Spike means:** Forwarding issue on the Mw interface, or P-CSCF stopped forwarding.
    - **Healthy typical range:** 0–0.5 requests_per_second
    - **Healthy invariant:** Per-UE rate. Should closely track ims.pcscf.rcv_requests_register_per_ue.


## Event Aggregation (Phase 1)

No events fired during this episode. Either no metric KB triggers matched, or the episode encountered no meaningful state transitions.

## Correlation Analysis (Phase 2)

No events fired — correlation engine had nothing to work with.

## Network Analysis (Phase 3)

**Summary:** IMS registration is failing due to high latency from the HSS, causing widespread signaling issues and a near-complete stall of the user data plane.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🟢 GREEN | No evidence of infrastructure-level faults (e.g., container crashes, network partitions). |
| **ran** | 🟢 GREEN | RAN appears healthy; UEs have L2/L3 connectivity. |
| **core** | 🟡 YELLOW | The user plane is nearly inactive. This is likely a symptom of the upstream IMS failure, as UEs cannot establish data sessions without successful registration. The core itself is likely not the root cause. |
| **ims** | 🔴 RED | The entire IMS signaling path is showing signs of severe distress, centered around slow responses from the HSS. |

**CORE evidence:**
- normalized.upf.gtp_indatapktn3upf_per_ue has dropped from 3.42 to 0.21 pps.
- normalized.upf.gtp_outdatapktn3upf_per_ue has dropped from 3.34 to 0.35 pps.

**IMS evidence:**
- derived.pcscf_avg_register_time_ms dropped from 248ms to 107ms, a classic stall signature.
- icscf.cdp:average_response_time, icscf.ims_icscf:uar_avg_response_time, and scscf.ims_auth:mar_avg_response_time all show elevated latency.
- REGISTER request rates are spiking at P-CSCF, I-CSCF, and S-CSCF, indicating a retry storm.

**Ranked hypotheses:**

- **`h1`** (fit=0.90, nf=pyhss, specificity=specific):
    - **Statement:** The HSS (pyhss) is experiencing a processing slowdown, causing high latency on the Cx interface. This is stalling SIP registration attempts, leading to UE retry storms and preventing the establishment of VoNR calls, which explains the silent data plane.
    - **Falsification probes:**
        - Measure RTT from icscf to the pyhss IP. A low RTT (<5ms) would confirm the network path is healthy, isolating the fault to the HSS application itself.
        - Check CPU/Memory utilization of the pyhss container; high usage would confirm a performance bottleneck.
- **`h2`** (fit=0.40, nf=pcscf, specificity=moderate):
    - **Statement:** The P-CSCF is experiencing an internal processing stall. This is causing end-to-end registration to fail and timeout from the client's perspective, which makes the calculated average registration time drop to near-zero.
    - **Falsification probes:**
        - Examine P-CSCF internal logs for errors not related to Diameter or SIP timeouts.
        - Confirm that REGISTER requests are still being forwarded to the I-CSCF. If they are, the P-CSCF is not fully stalled.
- **`h3`** (fit=0.20, nf=upf, specificity=specific):
    - **Statement:** The data plane is broken at the UPF, preventing user traffic. This is a separate fault from the observed IMS signaling latency.
    - **Falsification probes:**
        - Force a UE to register and establish a data session. If it succeeds despite the signaling latency, but no traffic flows, this would confirm a separate data plane fault.
        - Check for packet drops or errors on the N3 and N6 interfaces of the UPF.


## Falsification Plans (Phase 4)

**3 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `pyhss`)

**Hypothesis:** The HSS (pyhss) is experiencing a processing slowdown, causing high latency on the Cx interface. This is stalling SIP registration attempts, leading to UE retry storms and preventing the establishment of VoNR calls, which explains the silent data plane.

**Probes (3):**
1. **`measure_rtt`** — from icscf to pyhss IP
    - *Expected if hypothesis holds:* High RTT (>500ms) or significant packet loss, indicating network congestion or HSS unresponsiveness on the forward path.
    - *Falsifying observation:* Low RTT (<5ms) and no packet loss, suggesting the network path from icscf to pyhss is healthy.
2. **`measure_rtt`** — from pyhss to icscf IP (triangulation for RTT)
    - *Expected if hypothesis holds:* High RTT (>500ms) or significant packet loss, confirming a broader network issue affecting both directions or icscf unresponsiveness.
    - *Falsifying observation:* Low RTT (<5ms) and no packet loss, localizing any RTT problem observed in the first probe to pyhss or the forward path.
3. **`get_nf_metrics`** — pyhss CPU/Memory utilization and Diameter Cx request/response metrics (e.g., `pyhss_cpu_usage_percent`, `pyhss_memory_usage_bytes`, `pyhss_diameter_cx_request_queue_length`, `pyhss_diameter_cx_response_time_ms`)
    - *Expected if hypothesis holds:* High CPU/Memory utilization on pyhss, a growing Diameter Cx request queue, or increased `pyhss_diameter_cx_response_time_ms`, indicating internal processing overload.
    - *Falsifying observation:* Normal CPU/Memory utilization and healthy Diameter Cx metrics on pyhss, indicating the HSS itself is not overloaded or slow.

*Notes:* This plan focuses on verifying both network latency to the HSS and the HSS's internal processing state. Triangulation helps differentiate network path issues from HSS internal issues for RTT.

### Plan for `h2` (target: `pcscf`)

**Hypothesis:** The P-CSCF is experiencing an internal processing stall. This is causing end-to-end registration to fail and timeout from the client's perspective, which makes the calculated average registration time drop to near-zero.

**Probes (3):**
1. **`read_container_logs`** — pcscf logs, grep for 'error|fail' excluding 'timeout|diameter_error' from the last 5 minutes
    - *Expected if hypothesis holds:* Existence of critical errors in pcscf logs not related to upstream/downstream timeouts or Diameter, indicating an internal processing fault within the application.
    - *Falsifying observation:* Absence of such internal critical errors, suggesting the pcscf application itself is stable and not internally stalled.
2. **`get_nf_metrics`** — pcscf metrics for incoming SIP REGISTER requests (e.g., `pcscf_sip_requests_received_total{method='REGISTER'}`) and outgoing SIP REGISTER requests (e.g., `pcscf_sip_requests_sent_total{method='REGISTER'}`)
    - *Expected if hypothesis holds:* A non-zero rate of incoming REGISTER messages at pcscf, but a near-zero rate of outgoing REGISTER messages to the I-CSCF, confirming pcscf is receiving requests but not forwarding them due to a stall.
    - *Falsifying observation:* Either a zero rate of incoming REGISTER messages (upstream starvation) or a healthy, non-zero rate of both incoming and outgoing REGISTER messages (pcscf is processing requests).
3. **`check_process_listeners`** — pcscf container to ensure SIP ports are open and listening
    - *Expected if hypothesis holds:* SIP ports on pcscf are open and listening, indicating the process is running but stalled internally.
    - *Falsifying observation:* SIP ports on pcscf are not open or listening, suggesting a process crash or misconfiguration rather than a processing stall.

*Notes:* This plan aims to distinguish an internal P-CSCF stall from upstream starvation or a complete crash, by checking for internal errors, forwarding behavior, and process liveness.

### Plan for `h3` (target: `upf`)

**Hypothesis:** The data plane is broken at the UPF, preventing user traffic. This is a separate fault from the observed IMS signaling latency.

**Probes (3):**
1. **`get_dp_quality_gauges`** — Retrieve UPF data plane quality gauges over a 60-second window, specifically looking at N3 and N6 packet rates and loss.
    - *Expected if hypothesis holds:* Non-zero incoming packet rate on UPF N3 but a high packet loss rate or zero outgoing packet rate on N6, indicating traffic reaches UPF but is dropped or not forwarded.
    - *Falsifying observation:* Low or zero packet loss and a healthy, non-zero packet rate across both N3 and N6, suggesting the data plane is functional, or zero incoming packet rate on N3 indicating upstream issue.
2. **`read_container_logs`** — upf logs, grep for 'error|drop|fail' from the last 5 minutes
    - *Expected if hypothesis holds:* Logs show 'drop' or 'error' messages indicating packets being discarded by the UPF, despite receiving them, confirming an internal data plane fault.
    - *Falsifying observation:* Absence of packet 'drop' or 'error' messages in UPF logs, suggesting the UPF is not actively dropping traffic or not receiving any traffic to drop.
3. **`get_nf_metrics`** — smf metrics related to N4 session establishment (e.g., `smf_n4_session_establishment_success_total`, `smf_n4_session_establishment_fail_total`)
    - *Expected if hypothesis holds:* SMF metrics show successful N4 session establishments to the UPF, confirming that SMF believes it is setting up data sessions correctly, but no traffic flows.
    - *Falsifying observation:* SMF metrics show a high rate of N4 session establishment failures, indicating a problem in setting up the data path to the UPF, not necessarily a UPF forwarding issue after setup.

*Notes:* This plan aims to verify if user plane traffic is reaching the UPF, if the UPF is actively dropping it, and if session establishment with the UPF from SMF's perspective is succeeding or failing.


## Parallel Investigators (Phase 5)

**3 sub-Investigator verdict(s):** **2 DISPROVEN**, **1 NOT_DISPROVEN**

### `h1` — ❌ **DISPROVEN**

**Hypothesis:** The HSS (pyhss) is experiencing a processing slowdown, causing high latency on the Cx interface. This is stalling SIP registration attempts, leading to UE retry storms and preventing the establishment of VoNR calls, which explains the silent data plane.

**Reasoning:** Probes contradict the central claim of the hypothesis. The network path to the HSS is healthy, and more importantly, metrics from IMS core components (I-CSCF, S-CSCF) that communicate with the HSS show moderate response times and zero timeouts on the Cx interface. This falsifies the assertion that the HSS is slow or stalled.

**Probes executed (3):**
- **from icscf to pyhss IP** ✗ CONTRADICTS
    - *Tool:* `measure_rtt("icscf", "172.22.0.18")`
    - *Observation:* [EVIDENCE: measure_rtt("icscf", "172.22.0.18") -> "rtt min/avg/max/mdev = 0.117/0.171/0.241/0.051 ms"]
    - *Comment:* The RTT between the I-CSCF and the HSS is extremely low (<1ms) with no packet loss. This contradicts the expectation of high RTT and confirms the network path is healthy.
- **from pyhss to icscf IP (triangulation for RTT)** ~ AMBIGUOUS
    - *Tool:* `measure_rtt("pyhss", "172.22.0.19")`
    - *Observation:* [EVIDENCE: measure_rtt("pyhss", "172.22.0.19") -> "Ping failed from pyhss to 172.22.0.19: OCI runtime exec failed: exec failed: unable to start container process: exec: \"ping\": executable file not found in $PATH: unknown"]
    - *Comment:* The reverse RTT measurement could not be performed because the 'ping' utility is not installed in the pyhss container. While not providing a direct measurement, the clean forward-path RTT makes a network issue unlikely.
- **pyhss CPU/Memory utilization and Diameter Cx request/response metrics (e.g., `pyhss_cpu_usage_percent`, `pyhss_memory_usage_bytes`, `pyhss_diameter_cx_request_queue_length`, `pyhss_diameter_cx_response_time_ms`)** ✗ CONTRADICTS
    - *Tool:* `get_nf_metrics()`
    - *Observation:* [EVIDENCE: get_nf_metrics() -> "ims_icscf:uar_avg_response_time = 69.0 [gauge, ms]", "ims_icscf:uar_timeouts = 0.0 [counter]", "ims_auth:mar_avg_response_time = 110.0 [gauge, ms]", "ims_auth:mar_timeouts = 0.0 [counter]"]
    - *Comment:* Metrics from the HSS's clients (I-CSCF and S-CSCF) show that average response times for Cx interface procedures (UAR, MAR) are moderate (~70-110ms) and, critically, there are zero timeouts. This directly contradicts the hypothesis that the HSS is experiencing a processing slowdown causing high latency and stalling.

### `h2` — ❌ **DISPROVEN**

**Hypothesis:** The P-CSCF is experiencing an internal processing stall. This is causing end-to-end registration to fail and timeout from the client's perspective, which makes the calculated average registration time drop to near-zero.

**Reasoning:** The hypothesis is disproven by two key observations. First, metrics show that the P-CSCF is successfully forwarding SIP REGISTER requests to the I-CSCF, which directly contradicts the claim that it is stalled. Second, a review of the P-CSCF's logs shows no internal errors, which contradicts the claim of an 'internal processing stall'. The P-CSCF appears to be operating correctly.

**Probes executed (3):**
- **pcscf logs, grep for 'error|fail' excluding 'timeout|diameter_error' from the last 5 minutes** ✗ CONTRADICTS
    - *Tool:* `read_container_logs("pcscf", grep="error|fail", since_seconds=300)`
    - *Observation:* [EVIDENCE: read_container_logs("pcscf", grep="error|fail", since_seconds=300) -> "(no log output)"]
    - *Comment:* The absence of internal errors contradicts the hypothesis that the P-CSCF is suffering an internal processing stall. The application appears stable.
- **pcscf metrics for incoming SIP REGISTER requests (e.g., `pcscf_sip_requests_received_total{method='REGISTER'}`) and outgoing SIP REGISTER requests (e.g., `pcscf_sip_requests_sent_total{method='REGISTER'}`)** ✗ CONTRADICTS
    - *Tool:* `get_nf_metrics()`
    - *Observation:* [EVIDENCE: get_nf_metrics() -> "PCSCF ... core:rcv_requests_register = 188.0 ... ICSCF ... core:rcv_requests_register = 204.0"]
    - *Comment:* The lifetime counters show that REGISTER requests are being received by P-CSCF (188) and forwarded to I-CSCF (204). This directly falsifies the claim that P-CSCF is stalled and not forwarding requests.
- **pcscf container to ensure SIP ports are open and listening** ✓ CONSISTENT
    - *Tool:* `check_process_listeners("pcscf")`
    - *Observation:* [EVIDENCE: check_process_listeners("pcscf") -> "udp   UNCONN 0      0        172.22.0.21:5060       0.0.0.0:*    users:((\"kamailio\"...)"]
    - *Comment:* The kamailio process is listening on the correct SIP port (5060). This rules out a process crash, and in the context of the other probes, points towards a healthy, functioning P-CSCF rather than a stalled one.

**Alternative suspects:** icscf, scscf, pyhss

### `h3` — ✅ **NOT_DISPROVEN**

**Hypothesis:** The data plane is broken at the UPF, preventing user traffic. This is a separate fault from the observed IMS signaling latency.

**Reasoning:** The investigation revealed a significant packet loss (~30%) within the UPF, supporting the claim of a data plane issue. While the UPF is not completely 'broken' as it still passes some traffic, it is clearly degraded. Furthermore, metrics from the SMF and UPF confirm that N4 control plane sessions are being established successfully, isolating the fault to the data plane forwarding logic itself. The absence of error logs in the UPF is unusual but does not outweigh the direct evidence of packet loss.

**Probes executed (3):**
- **Retrieve UPF data plane quality gauges over a 60-second window, specifically looking at N3 and N6 packet rates and loss.** ✓ CONSISTENT
    - *Tool:* `default_api.get_dp_quality_gauges(window_seconds=60)`
    - *Observation:* [EVIDENCE: get_dp_quality_gauges(window_seconds=60) -> "UPF: in  packets/sec: 5.3 out packets/sec: 3.7"]
    - *Comment:* The gauges show a significant drop of ~30% in packet rate between the UPF's input and output. This is consistent with a data plane fault, although 'degraded' is more accurate than 'broken'.
- **upf logs, grep for 'error|drop|fail' from the last 5 minutes** ✗ CONTRADICTS
    - *Tool:* `default_api.read_container_logs(container='upf', grep='error|drop|fail', since_seconds=300)`
    - *Observation:* [EVIDENCE: read_container_logs(container='upf', grep='error|drop|fail', since_seconds=300) -> "(no log output)"]
    - *Comment:* The absence of any 'drop' or 'error' logs is surprising given the observed packet loss. This suggests the UPF is dropping packets silently, which contradicts the expectation of explicit error logging but does not disprove the packet loss itself.
- **smf metrics related to N4 session establishment (e.g., `smf_n4_session_establishment_success_total`, `smf_n4_session_establishment_fail_total`)** ✓ CONSISTENT
    - *Tool:* `default_api.get_nf_metrics()`
    - *Observation:* [EVIDENCE: get_nf_metrics() -> "SMF [4 PDU] (via prometheus): pfcp_sessions_active = 4.0 [...] UPF [4 sess] (via prometheus): fivegs_upffunction_upf_sessionnbr = 4.0"]
    - *Comment:* Both SMF and UPF report 4 active sessions, indicating that the SMF is successfully establishing N4 control plane sessions with the UPF. This confirms the control plane is working as expected, pointing the finger towards a data plane issue after the session is established.


## Evidence Validation (Phase 6)

**Overall verdict:** clean
**Overall confidence:** high

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 4 | 3/3 | clean | high |
| `InvestigatorAgent_h2` | 3 | 3/3 | clean | high |
| `InvestigatorAgent_h3` | 3 | 3/3 | clean | high |


## Ground Truth

**Failure domain:** ims_media  
**Protocol impact:** RTP  
**Affected components:** rtpengine  
**Severity:** degraded

## Agent Diagnosis

**Model:** v6-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 134.8s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: The UPF is silently dropping approximately 30% of user plane traffic, causing severe data plane degradation; initial alerts pointing to an IMS fault were misleading.
> - **timeline**:
>     1. Initial alerts indicated widespread IMS registration failures, suggesting a signaling storm or a stalled component like the HSS.
>     2. The user data plane was observed to be nearly inactive, which was initially attributed to the inability of UEs to complete registration and establish data sessions.
>     3. Investigation disproved the hypothesis of an HSS slowdown, finding that Cx interface response times were normal with zero timeouts.
>     4. Investigation also disproved a P-CSCF stall, confirming it was forwarding REGISTER requests correctly.
>     5. Direct measurement of the UPF's data plane revealed a ~30% packet loss between its input and output interfaces, confirming a data plane fault as the true root cause.
> - **root_cause**: A data plane forwarding fault within the UPF is causing it to silently drop a significant percentage of packets. The primary_suspect_nf is `upf`.
> - **affected_components**:
>     - `upf`: Root Cause
>     - `core`: Symptomatic (User plane is degraded due to the UPF fault)
>     - `ims`: Symptomatic (End-to-end signaling is unreliable due to packet loss on the underlying data plane, causing timeouts and registration failures)
> - **recommendation**: Investigate the UPF's internal state and logs to identify the reason for the silent packet loss. Verify internal forwarding tables, buffer states, and any QoS enforcement mechanisms that might be incorrectly dropping traffic.
> - **confidence**: high
> - **explanation**: The investigation definitively identified the root cause as a data plane fault in the UPF. The initial primary hypothesis (`h1`), which suggested a slowdown in the HSS, was disproven by probe results showing healthy network RTT and zero timeouts on the Cx interface. The second hypothesis (`h2`) of a P-CSCF stall was also falsified, as metrics proved it was forwarding SIP requests correctly. The surviving hypothesis (`h3`) was confirmed by direct observation: a comparison of the UPF's incoming and outgoing packet rates showed a consistent 30% drop. This packet loss is the source of the user data plane stall and also explains the user-facing IMS timeouts, which were symptoms of an unreliable underlying transport path, not a failure in the IMS components themselves.

### Scoring Breakdown

**Overall score: 25%**

**Scorer assessment:** The agent correctly identified the fault type and severity as packet loss and degradation, but completely missed the root cause component (RTPEngine) and its associated layer, incorrectly pointing to the UPF and misinterpreting IMS symptoms. Its high confidence was unwarranted.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | No | The simulated failure was 30% packet loss on RTPEngine, a media plane component. The agent diagnosed 30% packet loss on the UPF, a user plane component, and incorrectly stated that IMS signaling was affected. The agent completely missed the actual root cause and component. |
| Component overlap | 0% | The primary affected component in the simulation was 'rtpengine'. The agent identified 'upf' as the primary affected component. There is no overlap between these components. |
| Severity correct | Yes | The simulated failure involved 30% packet loss leading to call quality degradation. The agent identified 'approximately 30% of user plane traffic' being dropped and 'severe data plane degradation', which accurately reflects the severity of the issue. |
| Fault type identified | Yes | The simulated failure type was 'packet loss'. The agent correctly identified 'packet loss' as the fault type ('silently dropping approximately 30% of user plane traffic', 'data plane forwarding fault'). |
| Layer accuracy | No | The actual root cause component, 'rtpengine', belongs to the 'ims' layer. The agent identified the 'upf' (which belongs to the 'core' layer) as the root cause. Therefore, the agent attributed the root cause to the wrong layer. While the agent did rate the 'ims' layer as 'red', its reasoning was based on incorrect symptoms (IMS signaling issues, not media path issues), and its primary root cause was placed in the 'core' layer. |
| Confidence calibrated | No | The agent stated 'high' confidence for a diagnosis that was fundamentally incorrect regarding the root cause component ('upf' instead of 'rtpengine') and its location, and misidentified the affected symptoms (IMS signaling unaffected in simulation, but agent claimed it was affected). |

**Ranking:** The correct root cause (RTPEngine packet loss) was not listed among the agent's hypotheses or final diagnosis.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 124,083 |
| Output tokens | 5,899 |
| Thinking tokens | 14,183 |
| **Total tokens** | **144,165** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| EventAggregator | 0 | 0 | 0 |
| CorrelationAnalyzer | 0 | 0 | 0 |
| NetworkAnalystAgent | 21,297 | 3 | 2 |
| InstructionGeneratorAgent | 15,156 | 1 | 2 |
| InvestigatorAgent_h1 | 39,329 | 4 | 5 |
| InvestigatorAgent_h2 | 33,670 | 3 | 4 |
| InvestigatorAgent_h3 | 27,804 | 3 | 4 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 6,909 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 273.9s
