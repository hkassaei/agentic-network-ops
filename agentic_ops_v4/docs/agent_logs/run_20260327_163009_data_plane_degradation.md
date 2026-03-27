# Episode Report: Data Plane Degradation

**Agent:** v4  
**Episode ID:** ep_20260327_162757_data_plane_degradation  
**Date:** 2026-03-27T16:27:58.030006+00:00  
**Duration:** 130.4s  

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

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

### Metrics Changes

| Node | Metric | Baseline | Current | Delta |
|------|--------|----------|---------|-------|
| icscf | cdp:replies_received | 18.0 | 19.0 | 1.0 |
| icscf | ims_icscf:lir_replies_received | 9.0 | 10.0 | 1.0 |
| icscf | core:rcv_requests_invite | 9.0 | 10.0 | 1.0 |
| icscf | ims_icscf:lir_replies_response_time | 431.0 | 470.0 | 39.0 |
| icscf | cdp:average_response_time | 68.0 | 66.0 | -2.0 |
| icscf | cdp:replies_response_time | 1233.0 | 1272.0 | 39.0 |
| pcscf | core:rcv_requests_invite | 16.0 | 18.0 | 2.0 |
| pcscf | core:rcv_requests_options | 1353.0 | 1354.0 | 1.0 |
| pcscf | dialog_ng:active | 0.0 | 2.0 | 2.0 |
| pcscf | dialog_ng:processed | 16.0 | 18.0 | 2.0 |
| pcscf | httpclient:connfail | 1386.0 | 1389.0 | 3.0 |
| pcscf | httpclient:connok | 16.0 | 18.0 | 2.0 |
| pcscf | sl:1xx_replies | 28.0 | 30.0 | 2.0 |
| scscf | core:rcv_requests_invite | 16.0 | 18.0 | 2.0 |
| scscf | dialog_ng:active | 0.0 | 2.0 | 2.0 |
| scscf | dialog_ng:processed | 16.0 | 18.0 | 2.0 |

### Notable Log Lines

**e2e_ue1:**
- `12:28:01.841     strm0x781920007e68 !Resetting jitter buffer in stream playback start`
**e2e_ue2:**
- `12:28:01.826     strm0x7836a0032fd8 !Resetting jitter buffer in stream playback start`
**icscf:**
- `[0;39;49m[0;36;49m22(72) INFO: ims_icscf [cxdx_avp.c:140]: cxdx_get_avp(): cxdx_get_experimental_result_code: Failed finding avp`
- `[0;39;49m[0;31;49m 3(53) ERROR: {1 5253 INVITE 0RUZy2ZZkDPxj8mvq3oOlCSfQGbeeGpI initial_request} <script>: $ru => sip:001011234567892@ims.mnc001.mcc`
- `[0;39;49m[0;36;49m23(73) INFO: ims_icscf [cxdx_avp.c:140]: cxdx_get_avp(): cxdx_get_experimental_result_code: Failed finding avp`
- `[0;39;49m[0;31;49m 2(52) ERROR: {1 11963 INVITE MjcLnuXmWAWVZvyU5jS-C9YWy..Un6Hv initial_request} <script>: $ru => sip:001011234567892@ims.mnc001.mc`
- `[0;39;49m[0;36;49m24(74) INFO: ims_icscf [cxdx_avp.c:140]: cxdx_get_avp(): cxdx_get_experimental_result_code: Failed finding avp`
**nr_gnb:**
- `[2026-03-27 11:57:16.298] [ngap] [[31m[1merror[m] Unhandled NGAP initiating-message received (9)`
- `[2026-03-27 11:57:16.304] [ngap] [[31m[1merror[m] Unhandled NGAP initiating-message received (9)`
- `[2026-03-27 11:57:21.214] [ngap] [[31m[1merror[m] Unhandled NGAP initiating-message received (9)`
- `[2026-03-27 11:57:21.220] [ngap] [[31m[1merror[m] Unhandled NGAP initiating-message received (9)`
- `[2026-03-27 12:01:27.287] [ngap] [[31m[1merror[m] Unhandled NGAP initiating-message received (9)`
**scscf:**
- `[0;39;49m[0;39;49m 3(42) DEBUG: {1 24805 ACK aLXNMMZks6M8rpye0rIuFN4NaHiHscls DEFAULT_ROUTE} ims_usrloc_scscf [contact_dlg_handlers.c:251]: contact_`

## Ground Truth

**Failure domain:** data_plane  
**Protocol impact:** GTP-U  
**Affected components:** upf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v4-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 118.7s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> Based on the evidence provided by the specialist agents, I have synthesized the findings to determine the root cause of the system failure.
> 
> ### Final Diagnosis
> 
> There are two contributing factors to the observed P-CSCF HTTP connection failures. One is the definitive root cause of the massive failure count, while the other is a latent configuration issue that would cause problems independently.
> 
> ---
> 
> ### **Cause 1 (Primary Root Cause)**
> 
> *   **summary**: The P-CSCF is attempting to connect to a non-existent server because its configuration file contains a literal placeholder string, `SCP_BIND_IP`, instead of a valid IP address for the Service Communication Proxy (SCP).
> *   **timeline**:
>     *   `t0`: P-CSCF container starts and loads its configuration.
>     *   `t1`: The P-CSCF needs to discover the Policy Control Function (PCF) to apply call policies. It attempts to send an HTTP request to the SCP, as per its routing logic.
>     *   `t2`: The request is targeted at `http://SCP_BIND_IP:SCP_BIND_PORT/...`.
>     *   `t3`: The operating system's network stack immediately fails the connection attempt because `SCP_BIND_IP` is not a resolvable hostname or a valid IP address.
>     *   `t4`: The P-CSCF's HTTP client registers the transport-level failure, incrementing the `httpclient:connfail` statistic. This loop repeats for every PCF discovery attempt.
> *   **root_cause**: A deployment misconfiguration. The P-CSCF's configuration template was not correctly processed, leaving the placeholder `SCP_BIND_IP` in the active configuration for the SCP route. Every connection attempt using this route is therefore guaranteed to fail.
> *   **affected_components**: `pcscf`
> *   **recommendation**: Edit the P-CSCF's configuration file and replace the placeholder strings `SCP_BIND_IP` and `SCP_BIND_PORT` with the correct, routable IP address and port of the Service Communication Proxy (SCP). After updating the configuration, reload the service or restart the P-CSCF container.
> *   **confidence**: `high`
> *   **explanation**: The `httpclient:connfail` alarm is a direct result of a critical misconfiguration. Evidence from the P-CSCF's running configuration shows it is trying to contact a server at the address `SCP_BIND_IP`. This is not a real address but a placeholder value. All connection attempts fail instantly because the destination is invalid. This explains the near-total failure rate (1391 fails vs 18 successes), as the successful connections are for other services with correct configurations. The P-CSCF cannot discover the PCF, which is essential for applying QoS and other policies to user sessions.
> 
> ---
> 
> ### **Cause 2 (Secondary Finding)**
> 
> *   **summary**: The P-CSCF is configured with an overly aggressive 2-second HTTP connection timeout, making it intolerant to normal network latency or peer node processing delays.
> *   **timeline**:
>     *   `t0`: P-CSCF attempts to establish an HTTP connection to a valid, but slow, peer.
>     *   `t1`: The TCP SYN packet is sent.
>     *   `t2`: The peer node is under load and takes >2 seconds to respond with a SYN-ACK.
>     *   `t3`: At the 2-second mark, the P-CSCF's client library aborts the connection attempt due to the configured `connection_timeout`.
>     *   `t4`: The connection is logged as a failure (`httpclient:connfail`), even though the peer was online.
> *   **root_cause**: The `connection_timeout` parameter for the P-CSCF's HTTP client is set too low (2 seconds). This value does not provide sufficient buffer for network round-trip time and server-side processing, leading to false-positive connection failures.
> *   **affected_components**: `pcscf`
> *   **recommendation**: Modify the P-CSCF's configuration to increase the HTTP connection timeout. A value of 10 seconds is a safer starting point. The parameter to change is `modparam("http_client", "connection_timeout", 10)`.
> *   **confidence**: `medium`
> *   **explanation**: While not the cause of the primary outage, the Transport Specialist identified that the P-CSCF will give up on any new connection that doesn't establish within 2 seconds. This setting is too aggressive for a production environment and makes the system brittle. Even after fixing the primary `SCP_BIND_IP` issue, this low timeout would likely cause intermittent connection failures during periods of high network latency or load on peer components. It should be corrected to ensure system stability.

### Scoring Breakdown

**Overall score: 0%**

**Scorer assessment:** The agent completely failed to identify the injected fault, its location, type, or severity, and was overconfident in its incorrect diagnosis.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | No | The agent identified a P-CSCF configuration error and an HTTP timeout as root causes, neither of which matches the injected network loss on the UPF. |
| Component overlap | 0% | The injected fault targeted the 'upf' container, but the agent incorrectly identified 'pcscf' as the affected component. |
| Severity correct | No | The agent described a 'massive failure count' and 'primary outage', whereas the injected fault (30% packet loss) would lead to degradation, not a complete outage. |
| Fault type identified | No | The agent identified configuration errors and timeouts, which are not semantically equivalent to the injected 'network_loss' fault type. |
| Confidence calibrated | No | The agent expressed 'high' confidence in a diagnosis that was completely incorrect, indicating poor calibration. |

**Ranking:** Neither of the agent's ranked causes was correct.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 63,973 |
| Output tokens | 2,788 |
| Thinking tokens | 14,055 |
| **Total tokens** | **80,816** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| TriageAgent | 7,388 | 2 | 3 |
| EndToEndTracer | 34,492 | 6 | 7 |
| DispatchAgent | 2,801 | 0 | 1 |
| TransportSpecialist | 13,925 | 3 | 4 |
| IMSSpecialist | 16,054 | 3 | 4 |
| SynthesisAgent | 6,156 | 0 | 1 |


## Resolution

**Heal method:** scheduled
**Recovery time:** 125.1s

---

## Post-Run Analysis

### Why the agent scored 0%

The agent completely missed the injected UPF packet loss and instead fixated on pre-existing P-CSCF configuration artifacts. Both "causes" it reported are not symptoms of the injected fault:

- **Cause 1 (SCP_BIND_IP placeholder):** The `httpclient:connfail` counter was already at 1,386 in the baseline — the +3 delta during the fault window is background noise, not a symptom. The agent treated a pre-existing condition as the root cause.
- **Cause 2 (HTTP timeout):** The 2-second `connection_timeout` is a static config value. It existed before the fault and has no causal relationship to the injected 30% packet loss on the UPF.

### Pipeline failure analysis

| Phase | What happened | What should have happened |
|---|---|---|
| Triage | Identified metric changes but did not flag UPF GTP counter deltas as significant | Should have recognized GTP packet counter movement + UE jitter buffer resets as data plane symptoms |
| EndToEndTracer | Consumed 43% of all tokens (34K) going deep on IMS call flow | Should have checked the data plane path (UPF) alongside the signaling path |
| Dispatch | Selected Transport + IMS specialists, did not select Core | Should have selected Core — the UPF is a core NF and its metrics are only examined by the Core specialist |
| TransportSpecialist | Focused on P-CSCF HTTP failures (pre-existing) | With `run_kamcmd` removed, correctly stayed closer to transport layer but still didn't look at UPF tc rules |
| IMSSpecialist | Investigated IMS signaling, found no fault there | Correctly scoped but the fault wasn't in IMS |
| SynthesisAgent | Synthesized wrong findings into wrong conclusion | Garbage in, garbage out — the synthesis was coherent but based on incorrect specialist findings |

### Structural root cause

**The Core specialist was never dispatched.** The UPF is a core network function. Its Prometheus metrics (`fivegs_ep_n3_gtp_indatapktn3upf/outdatapktn3upf`) and its network interface (`tc` rules showing `netem loss 30%`) would only be examined by a specialist that investigates core NFs. Neither TransportSpecialist nor IMSSpecialist had reason to inspect the UPF specifically.

The dispatcher's LLM chose IMS + Transport because the observable symptoms (IMS metric deltas, INVITE processing, jitter buffer resets) pointed at the application layer. It did not reason that these could be secondary effects of a data plane fault upstream.

### Comparison with previous run

| Dimension | Run 1 (161736) | Run 2 (163009) |
|---|---|---|
| Score | 0% | 0% |
| Misdiagnosis | S-CSCF port 6060 mismatch (hallucinated) | P-CSCF SCP_BIND_IP placeholder (pre-existing) |
| Specialists dispatched | Transport only | Transport + IMS |
| TransportSpecialist tokens | 33,478 (8 tool calls) | 13,925 (3 tool calls) |
| Total tokens | 70,797 | 80,816 |
| Time to diagnosis | 77s | 119s |

Narrowing the TransportSpecialist's toolset (removing `run_kamcmd`) successfully prevented it from hallucinating SIP-layer diagnoses — it dropped from 33K to 14K tokens and from 8 to 3 tool calls. However, the fundamental problem persists: nobody looks at the UPF.

### Recommended fixes

1. **Make `core` a mandatory specialist** (same pattern as the existing `transport` always-include rule). The core specialist costs ~5K tokens and would check UPF metrics and tc rules. This is the highest-impact fix.

2. **Give TriageAgent a `check_tc_rules` tool.** If triage checks tc rules on containers showing metric changes during its initial health scan, it would catch `netem loss 30%` on UPF immediately. This finding would then flow into the triage state and correctly inform the dispatcher.

3. **Teach the dispatcher about data plane symptoms.** UE jitter buffer resets and GTP counter anomalies are textbook data plane indicators. The dispatcher prompt should explicitly map these symptom patterns to the `core` specialist.
