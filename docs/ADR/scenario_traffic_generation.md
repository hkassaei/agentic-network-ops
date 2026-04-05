# ADR: Scenario-Driven Traffic Generation

**Date:** 2026-03-30
**Status:** Accepted
**Related:**
- Critical observation: [`docs/critical-observations/run_20260405_043504_p_cscf_latency.md`](../critical-observations/run_20260405_043504_p_cscf_latency.md) — Issue 4
- Depends on: [`dealing_with_temporality_1.md`](dealing_with_temporality_1.md) (FaultPropagationVerifier is what measures the symptoms this traffic generates)
- Sibling issue ADRs: [`data_plane_idle_stack_rule.md`](data_plane_idle_stack_rule.md) (Issue 1), [`upf_counters_directional_stack_rule.md`](upf_counters_directional_stack_rule.md) (Issue 2), [`evidence_validator_agent.md`](evidence_validator_agent.md) (Issue 3)

---

## Decision

Every chaos scenario declares, up front, what kind of network traffic is required for its fault to produce observable symptoms. A new `required_traffic` field on the `Scenario` model takes one of three values:

| Value | Meaning |
|---|---|
| `"none"` | Fault is self-evident. Killing a container drops its gauges; no stimulation needed. |
| `"control_plane"` | Fault sits in the SIP/Diameter signaling path. Symptoms only appear when a fresh transaction traverses the affected path. |
| `"user_plane"` | Fault sits in the data path. Symptoms only appear while RTP media is actively flowing. |

The `ChaosDirector` pipeline now has two traffic-generation phases that honor this field:

- **`CallSetupAgent`** (existing, between Baseline and FaultInjector) — establishes a VoNR call and waits 20s for media stabilization when `required_traffic == "user_plane"`.
- **`ControlPlaneTrafficAgent`** (**new**, between FaultInjector and FaultPropagationVerifier) — writes pjsua's `rr` re-register command to both `e2e_ue1` and `e2e_ue2`, then waits a few seconds for the REGISTER transactions to traverse the IMS signaling chain (P-CSCF → I-CSCF → Diameter to HSS → S-CSCF) — which is now sitting behind the just-injected fault.

All 10 scenarios in the library have been classified with an explicit `required_traffic` value and a comment justifying the choice. The deprecated `requires_active_call` boolean is retained for backward compatibility (treated as equivalent to `required_traffic == "user_plane"`) but new scenarios should use the new field.

## Context

On 2026-04-05, the `NetworkAnalystAgent` ran against a P-CSCF latency scenario (500ms latency + 50ms jitter injected on the `pcscf` container) and scored only 35%. The four-issue critical observation pinpointed *scenario design* — not the agent — as the fourth and orthogonal failure:

> *"The metrics that WOULD have caught it — `tmx:active_transactions > 0`, `cdp:average_response_time` elevated, `script:register_time` elevated, `sl:1xx_replies` accumulating without matching `sl:200_replies` — never appeared in the filtered delta."*
>
> *"Without exercising the signaling path, the P-CSCF latency fault produces no observable symptoms beyond minor baseline noise. The agent cannot diagnose what it cannot see."*

The P-CSCF was delayed by 500ms, but nothing was talking to it. Both UEs had been registered 20 minutes earlier and their registrations were comfortably cached. During the entire 30-second propagation window, no new SIP transaction entered the affected path. So the fault was "injected" in the infrastructure sense but totally invisible in the behavioral sense. The `FaultPropagationVerifier` correctly concluded that nothing had changed — because, for any externally observable purpose, nothing had.

### The symmetry the library had missed

The scenario library already had *one* scenario that understood it needed traffic stimulation:

- `data_plane_degradation` set `requires_active_call=True`, causing `CallSetupAgent` to establish a VoNR call before fault injection. This is the only way packet loss on the UPF manifests — there needs to be media flowing for packets to be dropped.

But the library had nothing equivalent for the *control-plane* side. Seven other scenarios (P-CSCF latency, S-CSCF crash, HSS unresponsive, MongoDB gone, DNS failure, IMS network partition, cascading IMS failure) target the SIP/Diameter signaling path and all share the same fundamental requirement: *there has to be a new REGISTER or INVITE traversing the affected path during the observation window, otherwise the fault is silent*. None of them had any mechanism to make that happen. The framework was asking the agent to diagnose a fault whose symptoms had been allowed to sleep.

### The three scenario shapes

Looking across all 10 scenarios, three distinct patterns emerged:

1. **Self-evident destruction** (2 scenarios: gNB Radio Link Failure, AMF Restart).
   Killing the container collapses gauges immediately. The AMF session count goes to zero, NGAP associations drop, UEs disconnect — all visible without any extra stimulation. No traffic needed.

2. **Control-plane latent faults** (7 scenarios: P-CSCF Latency, S-CSCF Crash, HSS Unresponsive, MongoDB Gone, DNS Failure, IMS Network Partition, Cascading IMS Failure).
   The fault sits somewhere in the SIP/Diameter path and only matters when a new transaction flows through. Existing UE registrations are cached at every hop and nothing forces them to refresh during the propagation window. These were the silently-broken scenarios.

3. **User-plane data faults** (1 scenario: Data Plane Degradation).
   The fault is on the RTP media path. Packet loss on the UPF is meaningless unless media is actively flowing. Requires an active VoNR call.

The fix is to make that classification *explicit* in the scenario definition and to have the orchestrator honor it.

### Why pjsua's `rr` command is the right mechanism for control-plane stimulation

The UE containers run pjsua with a FIFO command interface at `/tmp/pjsua_cmd`. pjsua exposes several commands via this FIFO, including `rr` (re-register). Writing `rr` causes pjsua to emit a fresh SIP REGISTER transaction that traverses the full IMS signaling chain:

```
UE → P-CSCF → I-CSCF → [Diameter UAR to HSS → UAA] → S-CSCF → [Diameter MAR to HSS → MAA] → back
```

Every one of the seven control-plane scenarios targets something on this chain. A re-register is the smallest, cheapest probe that exercises all of it. Verified during implementation: sending `echo rr >> /tmp/pjsua_cmd` to `e2e_ue1` produces a visible `TX 689 bytes Request msg REGISTER/cseq=... to UDP 172.22.0.21:5060` in pjsua's log within milliseconds.

Using the UE's own pjsua also avoids a class of problems that the alternative (a synthetic SIP client inside the framework) would introduce: the re-register comes from a real registered UE on a real APN, across the real NAT/iptables topology, through the real gNB and UPF. Nothing about the test is synthetic from the CSCF's perspective.

## Design

### The scenario field (`agentic_chaos/models.py`)

```python
class Scenario(BaseModel):
    ...
    required_traffic: str = "none"
    """What kind of traffic the fault needs in order to produce observable
    symptoms. One of:

      - "none"          — fault is self-evident (container kill, etc.)
      - "control_plane" — needs fresh SIP signaling during propagation.
                          ControlPlaneTrafficAgent will force a UE
                          re-registration after fault injection so new
                          REGISTER transactions flow through the affected
                          path. Use for P-CSCF latency, S-CSCF crash,
                          HSS unresponsive, DNS failure, IMS partition,
                          cascading IMS failure, MongoDB gone.
      - "user_plane"    — needs active RTP media during propagation.
                          CallSetupAgent will establish a VoNR call
                          before fault injection and keep it active
                          during the propagation window. Use for data
                          plane degradation scenarios.
    """

    requires_active_call: bool = False
    """DEPRECATED — use required_traffic='user_plane' instead. Retained
    for backward compatibility. When True, is treated as equivalent to
    required_traffic='user_plane'."""
```

### The new agent (`agentic_chaos/agents/control_plane_traffic.py`)

`ControlPlaneTrafficAgent` is a small `BaseAgent` that:

1. Reads `scenario["required_traffic"]` from session state. Skips with an explicit event if it is not `"control_plane"`.
2. Calls `trigger_sip_reregister(ue)` on both `e2e_ue1` and `e2e_ue2`. Both are re-registered so one UE's lucky code path cannot mask the fault for the other.
3. Sleeps 3 seconds to let the REGISTER transactions actually traverse the IMS chain. On a healthy stack this is generous; under a fault it may never complete, but the transaction must be *in flight* before the FaultPropagationVerifier starts measuring.
4. Writes `control_plane_traffic_triggered: bool` into session state and yields a summary event.

### The new tool (`agentic_chaos/tools/application_tools.py`)

```python
async def trigger_sip_reregister(ue_container: str = "e2e_ue1") -> dict:
    """Force a fresh SIP REGISTER from a UE via pjsua's 'rr' command.

    Writes the 'rr' command to the UE's pjsua FIFO. The UE will send a
    new REGISTER transaction through the full IMS signaling chain:
    P-CSCF → I-CSCF → S-CSCF → HSS (Diameter UAR/MAR) → back.
    """
```

A thin wrapper around `docker exec {ue_container} bash -c "echo rr >> /tmp/pjsua_cmd"`. Returns the usual `{success, detail}` dict so the agent can log per-UE results.

### The pipeline wiring (`agentic_chaos/orchestrator.py`)

The `ChaosDirector` `SequentialAgent` now runs:

```
BaselineCollector
  → CallSetupAgent              [runs iff required_traffic == "user_plane"]
  → FaultInjector
  → ControlPlaneTrafficAgent    [runs iff required_traffic == "control_plane"]
  → FaultPropagationVerifier
  → ChallengeAgent
  → Healer
  → CallTeardownAgent           [runs iff a call was established]
  → EpisodeRecorder
```

Both traffic agents are always in the pipeline and self-gate on the scenario's `required_traffic` value. There are no conditional wiring paths or scenario-specific graph variants — the same pipeline runs every time, the gating is data-driven.

**Why the control-plane agent runs AFTER FaultInjector, but the call-setup agent runs BEFORE.** This is not an accidental asymmetry; it reflects the different physics of the two cases:

- A voice call takes ~30s of churn to establish (SIP INVITE, SDP negotiation, RTPEngine session setup, RTP flow establishment). If we tried to set up the call *after* injecting the fault, the call setup itself would fail because the fault breaks the signaling path — and we would never get to observe the user-plane symptoms. So the call goes up first, on a healthy stack, and we inject the fault into an already-flowing call.
- A re-register is a single atomic transaction that either completes or times out. Running it *after* injection is the whole point: we want to see what happens when the REGISTER hits the freshly-broken path. Running it before injection would be useless — it would succeed on the healthy stack and leave nothing for the fault to act on.

### Scenario classification

All 10 scenarios were classified. Each carries a comment explaining its classification:

| Scenario | Blast Radius | required_traffic | Why |
|---|---|---|---|
| gNB Radio Link Failure | SINGLE_NF | `none` | Killing gNB collapses NGAP/session gauges immediately. |
| AMF Restart | MULTI_NF | `none` | Stopping AMF drops gauges; UERANSIM auto-retries NGAP. |
| P-CSCF Latency | SINGLE_NF | `control_plane` | Latency only bites on new SIP transactions. |
| S-CSCF Crash | SINGLE_NF | `control_plane` | Cached registrations unaffected until a new REGISTER tries to route. |
| HSS Unresponsive | SINGLE_NF | `control_plane` | Diameter timeouts only appear when a new UAR/MAR fires. |
| MongoDB Gone | GLOBAL | `control_plane` | REGISTER triggers PyHSS → Mongo subscriber lookup; exposes the outage. |
| DNS Failure | GLOBAL | `control_plane` | DNS lookups only happen on new SIP transactions. |
| IMS Network Partition | MULTI_NF | `control_plane` | iptables DROP on CSCF paths bites only when SIP tries to traverse. |
| Cascading IMS Failure | MULTI_NF | `control_plane` | Both the HSS kill and S-CSCF latency need fresh SIP/Diameter traffic. |
| Data Plane Degradation | SINGLE_NF | `user_plane` | Packet loss needs active RTP media; CallSetupAgent establishes VoNR call. |

## Files Changed

- `agentic_chaos/models.py` — added `required_traffic` field to `Scenario`; marked `requires_active_call` as deprecated with back-compat semantics.
- `agentic_chaos/tools/application_tools.py` — new `trigger_sip_reregister(ue_container)` tool.
- `agentic_chaos/agents/control_plane_traffic.py` — **new file**, `ControlPlaneTrafficAgent` class.
- `agentic_chaos/agents/call_setup.py` — `CallSetupAgent` now honors both `required_traffic == "user_plane"` and the legacy `requires_active_call` flag.
- `agentic_chaos/orchestrator.py` — `ControlPlaneTrafficAgent` wired into the `ChaosDirector` pipeline between `FaultInjector` and `FaultPropagationVerifier`; docstring and description updated.
- `agentic_chaos/scenarios/library.py` — all 10 scenarios annotated with `required_traffic` and an explanatory comment.

## Verification

Verified during implementation that `docker exec e2e_ue1 bash -c "echo rr >> /tmp/pjsua_cmd"` produces a fresh SIP REGISTER transaction visible in pjsua's log:

```
.TX 689 bytes Request msg REGISTER/cseq=59788 ... to UDP 172.22.0.21:5060
```

End-to-end verification — running the full scenario library against the v5 RCA agent and confirming each control-plane fault now produces the expected symptoms in the FaultPropagationVerifier's filtered delta — is the next step and will be reported in a follow-up critical observation if any scenario still underperforms.

## Alternatives Considered

1. **Run scenarios for longer (300s instead of 30s) so natural REGISTER refreshes happen.** Rejected. The default registration lifetime in Kamailio is 3600s. We would need to wait up to an hour to guarantee a natural refresh, which is infeasible for an interactive chaos platform. Shortening the UE registration lifetime specifically for testing would couple the scenario library to a UE provisioning change and introduce a test-only code path, which is exactly what we are trying to avoid.

2. **Embed a synthetic SIP client (e.g., sipp) in the framework to generate REGISTER probes.** Rejected. A synthetic client would need its own credentials, its own IPSec SA setup, its own P-CSCF discovery, and would produce traffic that looks different to the CSCFs than real UE traffic. The real UEs are already registered and already have pjsua running — using their existing FIFO is a single-line docker exec and the REGISTER is indistinguishable from a real refresh.

3. **Add an application-level SIP OPTIONS ping instead of a full re-register.** Rejected. OPTIONS does not traverse the full S-CSCF/HSS Diameter path in Kamailio's default route script. A P-CSCF would answer OPTIONS locally without routing onward, which would miss the whole point for scenarios like HSS Unresponsive or S-CSCF Crash. REGISTER is the minimum probe that exercises the full signaling chain, including Diameter UAR/MAR.

4. **Make `ControlPlaneTrafficAgent` trigger re-register repeatedly throughout the propagation window (e.g., every 5s).** Considered and deferred. The FaultPropagationVerifier's window is ~30s and a single REGISTER gives the CSCFs enough to reveal latency, timeouts, and routing failures. Repeated re-registers would exercise the path more thoroughly but might also pile up retry state inside pjsua and Kamailio in ways that confound the verifier's metrics. Start with one re-register; revisit if any scenario still produces borderline signals.

5. **Put the traffic generation logic inside each scenario definition (e.g., a `pre_verify_hook` callback).** Rejected. That would scatter orchestration behavior across 10 scenario definitions, make the pipeline graph dependent on the scenario's hook, and create a bespoke plugin interface for what turned out to be three discrete shapes. A single enum-like field and two always-present agents (self-gating on the field) is simpler and more auditable.

6. **Make the orchestrator dynamically compose the pipeline per scenario (omit `ControlPlaneTrafficAgent` when not needed).** Rejected. The `SequentialAgent` is a static graph built once at import time. A dynamic graph would complicate debugging and phase tracing. Leaving both traffic agents in the graph and having them emit an explicit skip event keeps the episode record uniform and makes it trivial to verify, from the recorded events, which scenarios needed which kind of traffic.

## Follow-ups

This ADR closes Issue 4 of the four-issue critical observation from 2026-04-05. All four issues are now addressed:

- Issue 1 (idle data plane misread) → `data_plane_idle_stack_rule.md`
- Issue 2 (cumulative counter subtraction) → `upf_counters_directional_stack_rule.md`
- Issue 3 (fabricated evidence) → `evidence_validator_agent.md`
- Issue 4 (scenario design) → **this ADR**

Next validation step: re-run each control-plane scenario against v5 with the new traffic generation phase and confirm the FaultPropagationVerifier's filtered delta now contains the expected signaling-path metrics (`tmx:active_transactions`, `cdp:average_response_time`, `script:register_time`, `sl:1xx_replies` without matching `sl:200_replies`, etc.). If any scenario still underperforms, the likely next iteration is to extend `ControlPlaneTrafficAgent` with scenario-specific traffic shapes (e.g., INVITE probes for call-setup-path faults, OPTIONS pings for keepalive-path faults).
