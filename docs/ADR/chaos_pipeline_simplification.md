# ADR: Chaos Pipeline Simplification — Remove Redundant Agents, Unify Traffic Generation

**Date:** 2026-04-08
**Status:** Implemented
**Related episodes:**
- `agentic_ops_v5/docs/agent_logs/run_20260407_035711_p_cscf_latency.md` — first run with new pipeline (15%)
- `agentic_ops_v5/docs/agent_logs/run_20260408_034713_p_cscf_latency.md` — wall-clock timing bug caused 787s episode

## Context

The chaos pipeline had several agents that became redundant after introducing the ObservationTrafficAgent:

- **CallSetupAgent:** Established VoNR calls before fault injection for user-plane scenarios. Redundant because ObservationTrafficAgent generates both control-plane and user-plane traffic (including VoNR calls).
- **ControlPlaneTrafficAgent:** Triggered brief SIP re-registers after fault injection. Redundant because ObservationTrafficAgent generates sustained traffic for 2 minutes.
- **FaultPropagationVerifier before ObservationTrafficAgent:** The verifier ran before the extended traffic, but it needs traffic to verify propagation. Moving it after the observation window gives it much richer metric data.

## Decision

### Pipeline simplification

Old pipeline (10 agents):
```
baseline → [call_setup] → inject → [cp_traffic] → verify → [observation_traffic] → challenge → heal → [call_teardown] → record
```

New pipeline (8 agents):
```
baseline → inject → observation_traffic → verify → challenge → heal → [call_teardown] → record
```

Removed:
- `CallSetupAgent` — ObservationTrafficAgent places calls as part of its randomized traffic
- `ControlPlaneTrafficAgent` — ObservationTrafficAgent triggers re-registrations

Reordered:
- `ObservationTrafficAgent` now runs BEFORE `FaultPropagationVerifier` — generates 2 minutes of sustained traffic, then the verifier confirms propagation from the accumulated metric deltas

### Observation traffic on all scenarios

Added `observation_traffic_seconds=120` to all 10 scenarios, not just P-CSCF Latency. Even self-evident faults (gNB kill, AMF restart) benefit from traffic generation — it helps the anomaly screener capture the full impact pattern.

### Fault TTL increased

All scenarios: `ttl_seconds=600` (10 minutes) to survive the full pipeline. Previous 300s TTL was too short — the observation traffic + LLM processing + scoring exceeded 5 minutes.

### Wall-clock timing fix

The traffic generator tracked elapsed time by accumulating `asyncio.sleep()` durations, but blocking operations (e.g., `establish_vonr_call()` with 30s timeout for failed calls) weren't counted. The generator ran 300+ wall seconds while tracking only 120s. Fixed: replaced with `time.time() - start` wall-clock checking.

## Files changed

- `agentic_chaos/orchestrator.py` — removed CallSetupAgent, ControlPlaneTrafficAgent; reordered pipeline
- `agentic_chaos/scenarios/library.py` — `observation_traffic_seconds=120` and `ttl_seconds=600` on all 10 scenarios
- `agentic_chaos/agents/observation_traffic.py` — wall-clock timing, observation window timestamps

## Consequences

**Positive:**
- Simpler pipeline (8 agents instead of 10)
- All scenarios get consistent observation traffic + metric collection
- Fault TTL survives the full pipeline
- Traffic generation timing is accurate

**Negative:**
- Every scenario now takes ~2 extra minutes (observation traffic). Total episode time: ~8-13 minutes depending on LLM response times.
- The CallTeardownAgent is kept for safety (hangs up any lingering call) but may not always be needed.
