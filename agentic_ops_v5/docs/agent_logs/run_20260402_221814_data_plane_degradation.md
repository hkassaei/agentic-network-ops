# Episode Report: Data Plane Degradation

**Agent:** v5  
**Episode ID:** ep_20260402_221556_data_plane_degradation  
**Date:** 2026-04-02T22:15:57.332101+00:00  
**Duration:** 136.3s  

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
| icscf | cdp:average_response_time | 91.0 | 85.0 | -6.0 |
| icscf | ims_icscf:lir_avg_response_time | 0.0 | 73.0 | 73.0 |
| icscf | cdp:replies_received | 2.0 | 3.0 | 1.0 |
| icscf | ims_icscf:lir_replies_response_time | 0.0 | 73.0 | 73.0 |
| icscf | ims_icscf:lir_replies_received | 0.0 | 1.0 | 1.0 |
| icscf | core:rcv_requests_invite | 0.0 | 1.0 | 1.0 |
| icscf | cdp:replies_response_time | 182.0 | 255.0 | 73.0 |
| pcscf | httpclient:connfail | 159.0 | 162.0 | 3.0 |
| pcscf | sl:1xx_replies | 4.0 | 6.0 | 2.0 |
| pcscf | core:rcv_requests_options | 158.0 | 159.0 | 1.0 |
| pcscf | dialog_ng:active | 0.0 | 2.0 | 2.0 |
| pcscf | dialog_ng:processed | 0.0 | 2.0 | 2.0 |
| pcscf | httpclient:connok | 0.0 | 2.0 | 2.0 |
| pcscf | core:rcv_requests_invite | 0.0 | 2.0 | 2.0 |
| rtpengine | userspace_only_media_streams | 0.0 | 2.0 | 2.0 |
| rtpengine | total_sessions | 0.0 | 1.0 | 1.0 |
| rtpengine | bytes_per_second_(total) | 0.0 | 4511.0 | 4511.0 |
| rtpengine | owned_sessions | 0.0 | 1.0 | 1.0 |
| rtpengine | packets_per_second_(userspace) | 0.0 | 57.0 | 57.0 |
| rtpengine | total_relayed_packets_(userspace) | 0.0 | 72.0 | 72.0 |
| rtpengine | total_relayed_bytes_(userspace) | 0.0 | 5572.0 | 5572.0 |
| rtpengine | bytes_per_second_(userspace) | 0.0 | 4511.0 | 4511.0 |
| rtpengine | packets_per_second_(total) | 0.0 | 57.0 | 57.0 |
| rtpengine | total_relayed_packets | 0.0 | 72.0 | 72.0 |
| rtpengine | total_relayed_bytes | 0.0 | 5572.0 | 5572.0 |
| scscf | dialog_ng:active | 0.0 | 2.0 | 2.0 |
| scscf | dialog_ng:processed | 0.0 | 2.0 | 2.0 |
| scscf | core:rcv_requests_invite | 0.0 | 2.0 | 2.0 |

## Pattern Match (Phase 2)

```
{"matched": false, "top_diagnosis": "No matching signature found", "confidence": "low", "failure_domain": "unknown", "matched_signatures": [], "baseline_anomalies": {"smf": [{"metric": "bearers_active", "expected": 4.0, "actual": 6.0, "alarm_if": "", "note": "Rises to 6 during active VoNR call (2 dedicated QoS flows for voice)"}], "scscf": [{"metric": "dialog_ng:active", "expected": 0.0, "actual": 2.0, "alarm_if": "", "note": ""}], "pcscf": [{"metric": "dialog_ng:active", "expected": 0.0, "actua
```

## Investigation Instruction (Phase 4)

> INVESTIGATE: Primary anomaly is within the IMS Core, specifically **PCSCF**, which is experiencing a high number of `httpclient:connfail` (163.0) compared to `httpclient:connok` (2.0). This strongly indicates a **transport/network layer issue** affecting PCSCF's ability to establish HTTP connections to its dependencies.

Secondly, investigate **RTPEngine media quality metrics**: There is a critical discrepancy where `get_dp_quality_gauges` reports `MOS (recent) = 0`, `loss (recent) = 0`, and `ji

## Ground Truth

**Failure domain:** data_plane  
**Protocol impact:** GTP-U  
**Affected components:** upf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v5-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 121.6s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: The `rtpengine` container failed to start correctly because it lacks the necessary kernel permissions (`NET_ADMIN`) to create `nftables` rules, which completely breaks media (RTP) packet forwarding and results in no-way audio and erroneous quality metrics.
> - **timeline**:
>     1. The `rtpengine` container starts but fails to create kernel `nftables` rules, logging a critical error.
>     2. A VoNR call is initiated. SIP signaling proceeds normally, and `rtpengine` is engaged to handle the media session.
>     3. `rtpengine` reports an active session (`owned_sessions = 1.0`), as the control-plane part of its job was successful.
>     4. However, due to the missing `nftables` rules, the kernel cannot forward the actual RTP media packets through `rtpengine`.
>     5. This results in 100% packet loss for the call, leading to no audio.
>     6. Quality monitoring tools that rely on *recent* media (`get_dp_quality_gauges`) report MOS, loss, and jitter as 0 because they are not processing any packets. Older aggregate metrics (`get_nf_metrics`) report very poor quality (MOS 2.3, loss 13%) from initial session setup or historical data.
> - **root_cause**: The `rtpengine` container was launched without the required `--cap-add NET_ADMIN` privilege. This prevents it from modifying the host's networking rules (`nftables`), which is a core requirement for its function as a kernel-based media proxy.
> - **affected_components**:
>     - `rtpengine`
> - **recommendation**: Restart the `rtpengine` container, ensuring it is launched with the `NET_ADMIN` capability. For a docker-compose deployment, this involves adding `cap_add: - NET_ADMIN` to the `rtpengine` service definition.
> - **confidence**: high
> - **explanation**: The investigation found definitive proof of this failure in the `rtpengine` logs: `[EVIDENCE: read_container_logs("rtpengine", grep="error") -> "ERR: [core] FAILED TO CREATE NFTABLES CHAINS OR RULES, KERNEL FORWARDING POSSIBLY WON'T WORK"]`. This transport-layer failure directly explains the application-layer symptoms. Although a session is established in the signaling plane, the media plane is non-functional because the kernel is not configured to forward the RTP packets. This causes the call to fail and explains the discrepancy between session counts and the zero-value recent quality metrics.
> 
> ---
> - **summary**: A secondary, unconfirmed issue exists where the `pcscf` is experiencing a high volume of HTTP client connection failures.
> - **timeline**:
>     1. Throughout its operation, `pcscf` is attempting outbound HTTP connections which are failing at a high rate.
>     2. This is reflected in the metric `httpclient:connfail = 163.0` versus `httpclient:connok = 2.0`.
> - **root_cause**: Unknown. The investigation did not find corresponding errors in the `pcscf` logs, and a basic connectivity test to the `pcf` was successful. This did not contribute to the media failure but indicates a potential secondary problem.
> - **affected_components**:
>     - `pcscf`
> - **recommendation**: This issue is not the primary cause of the service outage. After resolving the critical `rtpengine` failure, if IMS issues persist, increase the `pcscf` log verbosity to identify the destination and reason for the failing HTTP requests.
> - **confidence**: low
> - **explanation**: The anomaly of high HTTP connection failures at the `pcscf` was noted, but the investigation did not uncover a cause. Given the critical and proven failure in the media plane (`rtpengine`), this `pcscf` issue is considered secondary and unrelated to the primary symptom of poor call quality. It should be investigated only if problems remain after fixing `rtpengine`.

### Scoring Breakdown

**Overall score: 10%**

**Scorer assessment:** The agent completely missed the simulated failure, diagnosing a different component and a different type of failure (complete outage due to configuration vs. degradation due to network path loss), despite correctly identifying 'packet loss' as a symptom.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | No | The simulated failure was 30% packet loss on the UPF. The agent diagnosed a complete failure (100% packet loss) of the rtpengine due to missing kernel permissions, which is a different component and a different root cause. |
| Component overlap | 0% | The simulated failure affected the UPF. The agent identified 'rtpengine' as the affected component, which is incorrect. |
| Severity correct | No | The simulated failure was a degradation (30% packet loss). The agent diagnosed a complete outage (100% packet loss, no audio). The severity assessment does not match. |
| Fault type identified | Yes | The simulated failure involved 'packet loss'. The agent identified '100% packet loss' as the observable symptom, which is a type of packet loss, thus identifying the general fault class. |
| Confidence calibrated | No | The agent expressed 'high' confidence in a diagnosis that was incorrect regarding the root cause, affected component, and severity of the simulated failure. |

**Ranking:** The correct root cause (packet loss on UPF) was not identified or listed by the agent.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 97,982 |
| Output tokens | 8,469 |
| Thinking tokens | 8,254 |
| **Total tokens** | **114,705** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| TriageAgent | 20,152 | 4 | 5 |
| PatternMatcherAgent | 0 | 0 | 0 |
| AnomalyDetectorAgent | 29,922 | 2 | 3 |
| InstructionGeneratorAgent | 5,955 | 0 | 1 |
| InvestigatorAgent | 50,831 | 6 | 7 |
| SynthesisAgent | 7,845 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 131.0s
