# Episode Report: Data Plane Degradation

**Agent:** v5  
**Episode ID:** ep_20260402_182429_data_plane_degradation  
**Date:** 2026-04-02T18:24:30.077055+00:00  
**Duration:** 377.4s  

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
| icscf | core:rcv_requests_invite | 3.0 | 4.0 | 1.0 |
| icscf | ims_icscf:lir_replies_response_time | 324.0 | 374.0 | 50.0 |
| icscf | cdp:replies_received | 17.0 | 18.0 | 1.0 |
| icscf | ims_icscf:lir_avg_response_time | 108.0 | 93.0 | -15.0 |
| icscf | cdp:average_response_time | 90.0 | 88.0 | -2.0 |
| icscf | cdp:replies_response_time | 1544.0 | 1594.0 | 50.0 |
| icscf | ims_icscf:lir_replies_received | 3.0 | 4.0 | 1.0 |
| pcscf | core:rcv_requests_invite | 6.0 | 8.0 | 2.0 |
| pcscf | httpclient:connok | 6.0 | 8.0 | 2.0 |
| pcscf | sl:1xx_replies | 30.0 | 32.0 | 2.0 |
| pcscf | dialog_ng:active | 0.0 | 2.0 | 2.0 |
| pcscf | httpclient:connfail | 2684.0 | 2687.0 | 3.0 |
| pcscf | core:rcv_requests_options | 2671.0 | 2672.0 | 1.0 |
| pcscf | dialog_ng:processed | 6.0 | 8.0 | 2.0 |
| rtpengine | bytes_per_second_(total) | 0.0 | 4416.0 | 4416.0 |
| rtpengine | owned_sessions | 0.0 | 1.0 | 1.0 |
| rtpengine | userspace_only_media_streams | 0.0 | 2.0 | 2.0 |
| rtpengine | total_relayed_packets_(userspace) | 2697.0 | 2769.0 | 72.0 |
| rtpengine | packets_per_second_(total) | 0.0 | 54.0 | 54.0 |
| rtpengine | total_relayed_bytes_(userspace) | 82932.0 | 88504.0 | 5572.0 |
| rtpengine | total_relayed_packets | 2697.0 | 2769.0 | 72.0 |
| rtpengine | bytes_per_second_(userspace) | 0.0 | 4416.0 | 4416.0 |
| rtpengine | total_sessions | 0.0 | 1.0 | 1.0 |
| rtpengine | packets_per_second_(userspace) | 0.0 | 54.0 | 54.0 |
| rtpengine | total_relayed_bytes | 82932.0 | 88504.0 | 5572.0 |
| scscf | core:rcv_requests_invite | 6.0 | 8.0 | 2.0 |
| scscf | dialog_ng:active | 0.0 | 2.0 | 2.0 |
| scscf | dialog_ng:processed | 6.0 | 8.0 | 2.0 |
| upf | fivegs_ep_n3_gtp_indatavolumeqosleveln3upf | 362133.0 | 362163.0 | 30.0 |
| upf | fivegs_ep_n3_gtp_indatapktn3upf | 6301.0 | 6302.0 | 1.0 |

## Pattern Match (Phase 2)

```
{"matched": false, "top_diagnosis": "No matching signature found", "confidence": "low", "failure_domain": "unknown", "matched_signatures": [], "baseline_anomalies": {"smf": [{"metric": "bearers_active", "expected": 4.0, "actual": 6.0, "alarm_if": "", "note": "Rises to 6 during active VoNR call (2 dedicated QoS flows for voice)"}], "icscf": [{"metric": "ims_icscf:uar_timeouts", "expected": 0.0, "actual": 2.0, "alarm_if": "> 0", "note": ""}], "scscf": [{"metric": "dialog_ng:active", "expected": 0.
```

## Anomaly Analysis (Phase 3)

> ### Layer Status
- **RAN:** GREEN — `ran_ue = 2.0`, `gnb = 1.0` indicate active UEs and gNBs.
- **Core:** GREEN — Core network functions (AMF, SMF, UPF) show active sessions consistent with active UEs. `smf` `bearers_active` anomaly is explained by VoNR calls. All core containers are running.
- **IMS:** YELLOW — `ICSCF` shows `uar_timeouts`, and both `SCSCF` and `PCSCF` have anomalous `dialog_ng:active` metrics. `PCSCF` also shows a high number of `httpclient:connfail`. These indicate issues wit

## Investigation Instruction (Phase 4)

> INVESTIGATE: IMS layer is degraded.
*   **ICSCF**: `ims_icscf:uar_timeouts = 2.0` (expected 0.0) suggests HSS communication issues.
*   **PCSCF**: High `httpclient:connfail = 2688.0` indicates external HTTP connectivity problems.
*   **PCSCF & SCSCF**: `dialog_ng:active = 2.0` (unexpected) points to SIP dialog management issues.
*   **RTPENGINE**: `average_mos = 0.0` and `average_packet_loss = 0.0` despite active media (`packets_per_second_(total) = 4.0`) suggests media quality measurement or ac

## Ground Truth

**Failure domain:** data_plane  
**Protocol impact:** GTP-U  
**Affected components:** upf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v5-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 363.1s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> #### Cause 1: RTPEngine Kernel Module Failure
> - **summary**: The `rtpengine` media proxy failed to load its required kernel module, completely disabling kernel-based media forwarding and quality analysis, thus breaking the media plane for VoNR calls.
> - **timeline**:
>     1.  The `rtpengine` container starts.
>     2.  It attempts to load its kernel module (`xt_RTPENGINE`) into the host kernel via `modprobe`.
>     3.  The command fails because the module is not available on the host system.
>     4.  `rtpengine` logs "KERNEL FORWARDING DISABLED" and falls back to a limited userspace mode.
>     5.  This fallback mode does not support media quality analysis, causing metrics like `average_mos` and `average_packet_loss` to remain at 0, as initially observed in the Triage Findings.
> - **root_cause**: The host system's kernel is missing the `xt_RTPENGINE` module required by the `rtpengine` container. This is a prerequisite mismatch between the container application and its host environment.
> - **affected_components**: `rtpengine`
> - **recommendation**: Install the `xt_RTPENGINE` kernel module and corresponding kernel headers on the container host. Then, restart the `rtpengine` container.
> - **confidence**: high
> - **explanation**: The investigation confirmed the initial observation that `rtpengine` quality metrics were zero despite processing packets. The root cause was found directly in the container logs, which showed a fatal error: `modprobe: FATAL: Module xt_RTPENGINE not found` and a subsequent warning: `KERNEL FORWARDING DISABLED`. This is a hard failure of a critical dependency, making it impossible for `rtpengine` to perform its primary function of efficiently forwarding media in the kernel, thus breaking the entire media plane.
> 
> #### Cause 2: IMS Control Plane Misconfiguration
> - **summary**: Multiple IMS control plane functions (`icscf`, `pcscf`, `scscf`) are misconfigured, preventing proper user authorization and SIP session management.
> - **timeline**:
>     1.  The `pcscf` and `scscf` Kamailio instances start but fail to load the `dialog` module.
>     2.  When a UE attempts to register or make a call, the `icscf` sends a User-Authorization-Request (UAR) to the HSS (`pyhss`).
>     3.  The request times out at the application layer, incrementing the `ims_icscf:uar_timeouts` metric. Investigation showed these UARs never arrived at the `pyhss`.
>     4.  Simultaneously, the `pcscf` and `scscf` are unable to track SIP dialogs correctly, leading to the anomalous `dialog_ng:active` metrics.
> - **root_cause**: The Kamailio configurations for `pcscf` and `scscf` are incorrect, as they are missing the `dialog` module needed for session tracking. Separately, there is an application-level configuration issue on the Diameter interface between `icscf` and `pyhss`, preventing authorization requests from being processed.
> - **affected_components**: `icscf`, `scscf`, `pcscf`, `pyhss`
> - **recommendation**: Correct the Kamailio configuration files for `pcscf` and `scscf` to load the `dialog` module. Separately, review and fix the Diameter endpoint and realm configurations on both `icscf` and `pyhss` to resolve UAR timeouts.
> - **confidence**: high
> - **explanation**: The investigation confirmed the hypotheses from the Anomaly Analysis. The anomalous `dialog_ng:active` metric was explained by the investigator's finding that the `dialog.list` command was missing, proving a module is not loaded ([EVIDENCE: default_api.run_kamcmd(command='dialog.list', container='pcscf') -> "error: 500 - command dialog.list not found"]). The `icscf` timeouts were confirmed to be an application-level fault, as transport latency was healthy, but logs showed UARs were not reaching the HSS. Even if the media plane were working, these control plane failures would prevent successful calls.

### Scoring Breakdown

**Overall score: 0%**

**Scorer assessment:** The agent completely failed to diagnose the simulated data plane degradation on the UPF, instead identifying unrelated control plane and media plane component failures with high, but misplaced, confidence.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | No | The simulated failure was 30% packet loss on the UPF. The agent diagnosed an RTPEngine kernel module failure (Cause 1) and IMS control plane misconfiguration (Cause 2), neither of which matches the simulated root cause of packet loss on the UPF. |
| Component overlap | 0% | The simulated failure affected the 'upf' component. The agent identified 'rtpengine' (Cause 1) and 'icscf', 'scscf', 'pcscf', 'pyhss' (Cause 2) as affected components, none of which is the UPF. |
| Severity correct | No | The simulated failure was a degradation (30% packet loss). The agent's Cause 1 describes a complete media plane outage, and Cause 2 describes a complete failure of call setup due to misconfiguration, neither of which aligns with a 'degradation' due to packet loss. |
| Fault type identified | No | The simulated failure was 'packet loss' (a network degradation). The agent identified a 'component failure' (kernel module not found) and 'configuration/application-level failure' (misconfiguration, timeouts), not network degradation or packet loss. |
| Confidence calibrated | No | The agent expressed 'high' confidence for both diagnoses, despite both being completely incorrect for the simulated failure. This indicates poor calibration. |

**Ranking:** The correct root cause (packet loss on UPF) was not identified or listed by the agent.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 303,526 |
| Output tokens | 11,448 |
| Thinking tokens | 27,060 |
| **Total tokens** | **342,034** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| TriageAgent | 14,784 | 3 | 4 |
| PatternMatcherAgent | 0 | 0 | 0 |
| AnomalyDetectorAgent | 188,822 | 16 | 12 |
| InstructionGeneratorAgent | 6,755 | 0 | 1 |
| InvestigatorAgent | 122,554 | 10 | 11 |
| SynthesisAgent | 9,119 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 372.2s
