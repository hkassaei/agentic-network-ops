# ADR: Temporal Evidence Collection — Capture Transport Evidence When Symptoms Are Visible

**Date:** 2026-04-08
**Status:** Implemented
**Related episodes:**
- `agentic_ops_v5/docs/agent_logs/run_20260408_015734_p_cscf_latency.md` — agent saw "recovery" instead of active fault (40%)
- `agentic_ops_v5/docs/agent_logs/run_20260408_034713_p_cscf_latency.md` — Investigator's measure_rtt showed "healthy" because fault had cleared (40%)

## Context

The P-CSCF Latency scenario injects 2000ms egress delay, generates 2 minutes of traffic (ObservationTrafficAgent), then invokes the v5 RCA pipeline. Two timing problems surfaced:

### Problem 1: NetworkAnalyst sees "recovery"

The NetworkAnalyst calls `get_nf_metrics` LIVE, but the observation traffic stopped minutes earlier. Live metrics show a calmer picture. The agent says "the network is recovering from a signaling storm" instead of "the network has an active latency fault."

### Problem 2: Investigator's measure_rtt sees a healed network

The Investigator runs `measure_rtt("pcscf", icscf_ip)` and gets sub-millisecond RTT — the fault either expired (TTL) or the traffic generator ran longer than expected (wall-clock bug). The Investigator concludes "transport is healthy" and blames the HSS application layer.

### Root insight

Transport-layer evidence (`measure_rtt`) is the most time-sensitive evidence in the pipeline. It MUST be collected when the fault is most likely still active — during or immediately after the observation window. The Investigator runs too late.

## Decision

### 1. Observation window timestamps plumbed end-to-end

The `ObservationTrafficAgent` now records `observation_window_start`, `observation_window_end`, and `observation_window_duration` in ADK session state. The ChallengerAgent computes `seconds_since_observation` (how long ago the window ended) and passes both to `investigate()`. The v5 orchestrator computes `event_lookback_seconds = duration + seconds_since` and injects it into the NetworkAnalyst's prompt template.

### 2. NetworkAnalyst temporal reasoning rewrite

Replaced the old "start with 60s, widen to 120s, 300s" Prometheus query strategy. The NetworkAnalyst now:
- Receives `{event_lookback_seconds}` — the exact Prometheus window that covers the event period
- Uses this for all time-windowed queries: `get_dp_quality_gauges(window_seconds={event_lookback_seconds})`
- Is told: "trust the screener over live metrics" — if the screener reports HIGH anomalies but live data looks calm, the event has passed; don't dismiss the screener

### 3. NetworkAnalyst probes transport from flagged components (Step 1b)

New mandatory step between data collection (Step 1) and ontology comparison (Step 2):

> "If the anomaly screener flagged ANY component as HIGH severity, you MUST immediately run `measure_rtt` FROM that component to its neighbors."

This captures transport evidence while the fault is most likely still active — the NetworkAnalyst runs closest in time to the observation window. The RTT measurements become part of the NetworkAnalyst's structured output, carried forward to all downstream phases as established fact.

Added `measure_rtt` to the NetworkAnalyst's toolset (`network_analyst.py`).

### 4. Traffic generator wall-clock timing fix

The traffic generator's elapsed tracking was based on accumulated `asyncio.sleep()` durations, not wall time. `establish_vonr_call()` has a 30-second internal timeout for failed calls, but this wasn't counted in elapsed. With 45% call weight, the generator ran 300+ wall seconds while tracking only 120s of sleep time.

Fixed: replaced accumulated-sleep tracking with `time.time() - start` wall-clock checking. The generator now stops at exactly the specified duration.

### 5. Synthesis output format standardized

The Synthesis agent sometimes produced JSON wrapped in code blocks, sometimes plain markdown. Added explicit instruction: "Do NOT produce JSON. Use plain markdown only."

## Files changed

- `agentic_chaos/agents/observation_traffic.py` — wall-clock timing fix, observation window timestamps in state
- `agentic_chaos/agents/challenger.py` — pass observation timing to investigate()
- `agentic_ops_v5/orchestrator.py` — compute event_lookback_seconds, inject into state
- `agentic_ops_v5/prompts/network_analyst.md` — temporal reasoning rewrite, Step 1b (measure_rtt from flagged components)
- `agentic_ops_v5/subagents/network_analyst.py` — added measure_rtt to toolset
- `agentic_ops_v5/prompts/synthesis.md` — markdown-only output format

## Design principle

**Collect evidence when symptoms are visible, not when you get around to analyzing them.** In the pipeline:
- Phase 0 (Screener) processes observation snapshots — captures WHAT is anomalous
- Phase 1 (NetworkAnalyst) runs immediately after — captures WHY (transport RTT) while the fault is still likely active
- Phase 4 (Investigator) runs minutes later — can reference Phase 1's RTT evidence even if the condition has cleared

This principle applies beyond this specific scenario: any transient condition (congestion, process hang, memory pressure) should have its most time-sensitive evidence captured at the earliest possible pipeline stage.
