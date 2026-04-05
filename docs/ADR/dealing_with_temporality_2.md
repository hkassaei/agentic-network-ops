# ADR: Dealing with Temporality — Part 2: Time-Windowed Observation and Agent Temporal Reasoning

**Date:** 2026-04-05
**Status:** Accepted
**Series:** Part 2 of N — builds on `dealing_with_temporality_1.md` (FaultPropagationVerifier)

---

## Decision

Extend the observation tool layer and the `NetworkAnalystAgent` prompt so the agent reasons about time the way a NOC engineer does: **start with recent data, walk backwards if nothing is found, cap the lookback, and never rely on external ground-truth fault timestamps.**

Specifically:

1. Every observation tool that can be time-bounded gains a `window_seconds` (or `since_seconds`) parameter:
   - `query_prometheus(query, window_seconds)` — uses the window in PromQL range selectors
   - `get_dp_quality_gauges(window_seconds)` — replaces the hardcoded `[30s]` with the parameter
   - `read_container_logs(container, since_seconds)` — uses `docker logs --since Ns`
2. All trigger paths (chaos framework, GUI `/investigate`, future alert webhooks) pass a single rough `anomaly_window_hint_seconds` value into session state. The chaos framework **deliberately does not** leak the precise `fault_injected_at` timestamp, even though it has it.
3. Default value: **300 seconds (5 minutes)**. Same value across all trigger paths for now.
4. The `NetworkAnalystAgent` prompt is updated to teach the doubling lookback strategy: start at 60s, widen to 120/300/900 only if no signal is found, cap at 15 minutes.

## Context

### The problem with ground-truth timing

Part 1 of this series fixed the fault propagation verification phase. While planning Part 2 I initially proposed writing `fault_injected_at` (ISO timestamp) into session state so the agent would know exactly how far back to look. That proposal was rejected on architectural grounds.

The reason: **the chaos testing framework is one of multiple trigger paths for these agents.** The same agents will eventually be invoked from:
- The GUI's `/investigate` page, when an operator clicks the button after noticing a symptom
- An alertmanager webhook, when a Prometheus alert fires
- A CLI or API call from another automation

In none of these real-world paths does the agent get a precise "fault occurred at timestamp T" input. The operator just says "something is wrong now." If we train the agent on precise chaos-framework timestamps, its reasoning will not transfer to production.

### How a NOC engineer actually works

A human NOC engineer does not say *"I know the fault happened at 14:23:07, let me pull metrics from 14:23:07."* They say *"the alert is firing **now**, what's anomalous **now**, and how long has it been like this?"* Their anchor is the present moment, and their search direction is backwards through time.

Their mental model has three query types:
1. **"What's wrong right now?"** — instant snapshot with no window
2. **"How long has X been wrong?"** — find the inflection point of an already-identified anomaly (scroll back on the graph)
3. **"What else changed around the time X went bad?"** — zoom into a bounded window around a suspected event

The agent tool layer has to support these questions without leaking the cause through the input parameters.

### Current tool limitations

Today's tools do not support any of this cleanly:
- `get_dp_quality_gauges` has a hardcoded `[30s]` window in its PromQL rate queries
- `query_prometheus` accepts arbitrary PromQL, so range selectors work, but the agent has to construct them — the prompt gives no guidance about when to use which
- `read_container_logs` uses `tail N` — historical lines regardless of timestamp, which caused the stale-log bug that Part 1 fixed in the verifier but did not fix in the tools
- The agent has no principled strategy for choosing windows; it picks arbitrary values

### The bootstrap hint problem

The NOC engineer typically has some idea — even imprecise — of when the problem started. The alert fired a minute ago. The user complained two minutes ago. An operator noticed something "in the last few minutes." This is coarse-grained but informative.

The agent needs something analogous. Without a hint it either queries too narrow (missing slow faults) or too wide (drowning in stale data). With a precise hint it becomes dependent on information it won't have in production.

The right answer is a **deliberately imprecise** bootstrap: "the problem started in roughly the last N seconds." This matches real-world NOC inputs and forces the agent to develop temporal reasoning that generalizes.

## The Design

### `anomaly_window_hint_seconds` in session state

Every trigger path writes a single integer value into the ADK session state under the key `anomaly_window_hint_seconds`. The `NetworkAnalystAgent` prompt references it as `{anomaly_window_hint_seconds}`.

| Trigger | Value source |
|---|---|
| Chaos framework (`run_scenario`) | Fixed at 300, regardless of when fault was injected |
| GUI `/investigate` page | Fixed at 300 (a future enhancement may add a dropdown) |
| Future alert webhook | `(now - alert_time) + buffer`, rounded to a typical bucket |

**The chaos framework deliberately does not compute a tight hint based on the real `fault_injected_at`.** Even though the framework knows exactly when the fault was injected, it passes the same 300-second value as every other trigger path. This prevents the agent from overfitting to chaos-test timing, and ensures its temporal reasoning transfers to production scenarios where precise timing is unknown.

### Default value: 300 seconds (5 minutes)

Selected as a middle ground:
- **Long enough** to cover slow-propagating faults (Diameter timeouts, gradual resource exhaustion) and human delay between symptom and investigation click (operator notices, thinks about it, clicks the button)
- **Short enough** that the agent starts fresh and anchors to recent state, not hours-old noise
- **Matches intuition** — "the problem started in the last few minutes" is how a real operator would describe the situation if pressed for a number

This value is a constant in the chaos orchestrator and in the GUI investigation endpoint. Future parts of this series may make it configurable per-trigger; for now it is hardcoded.

### Time-windowed tool parameters

All time-boundable tools gain an explicit window parameter.

**`query_prometheus(query, window_seconds=120)`**
Exposes the window as a tool argument so the prompt can guide the agent to choose it. The agent is free to embed the window directly in PromQL (e.g., `rate(metric[2m])`) or pass the parameter and have the tool use it as a hint when constructing range queries. Default 120s.

**`get_dp_quality_gauges(window_seconds=120)`**
Replaces the hardcoded `[30s]` in the PromQL rate queries with a parameterized window. Default 120s. The 14 Prometheus queries inside the tool all use the same window.

**`read_container_logs(container, since_seconds=120, tail=None, ...)`**
Adds `since_seconds` parameter. When provided, translates to `docker logs --since Ns <container>`. The existing `tail` parameter remains for the case where the agent wants bounded output regardless of time. If both are provided, `--since` runs first and `tail` limits the result. Default 120s.

### Parameter naming convention

Two names are used, chosen for clarity per tool:
- **`window_seconds`** — for rate/range queries where the window is a **lookback duration from "now"** (Prometheus metrics, DP gauges)
- **`since_seconds`** — for log reading where the window is a **start time relative to "now"** (`docker logs --since`)

Both mean the same thing semantically ("include data from the last N seconds"), but the naming matches the underlying primitive the tool wraps.

### The prompt teaches the NOC walk-backwards strategy

The `NetworkAnalystAgent` prompt gains a new section near the top:

```
## Temporal Reasoning

You are investigating an issue NOW. Start with recent data and walk
backwards only if you need to.

An operator has indicated the problem started roughly within the last
{anomaly_window_hint_seconds} seconds. Use this as the MAXIMUM window
for your first query — narrower is better.

Your strategy:
  1. Start with window_seconds = 60 for your first pass
  2. If nothing anomalous shows up, widen to 120 seconds
  3. If still nothing, widen to 300 seconds (the hint cap)
  4. Only widen beyond the hint (up to 900 seconds max) if the hint
     window shows a suspicious tail — evidence that the onset is earlier
  5. Never look back further than 15 minutes (900 seconds)

Recent data is signal. Old data is noise. A metric that was bad an hour
ago but is fine now is not the fault you are looking for.
```

This is prompt-based rather than tool-based on purpose. The agent needs to develop explicit reasoning about *why* it picked a given window, not hide that choice behind a wrapper.

### What Part 2 does NOT do

- **No anomaly onset detection tool yet.** A dedicated `find_anomaly_onset(metric)` tool that finds the inflection point of a metric is stage 3 of the roadmap. Part 2 teaches the agent to widen a window when it finds nothing, which is a weaker but simpler substitute.
- **No multi-metric correlation by onset time.** Stage 4 of the roadmap. Part 2 still has the agent reasoning about one window at a time.
- **No learned per-fault-type propagation profiles.** Stage 5. Part 2 uses a single bootstrap value across all fault types.
- **No backward fill of `kamcmd` / `rtpengine-ctl` CLI metrics.** These sources return current values only. The time-windowed improvements apply only to Prometheus-scraped data and docker logs. Kamailio stats remain instant snapshots; the agent must reason about them as cumulative counters against the ontology's `is_pre_existing` / `typical_range` markers. This is acceptable for now since RTPEngine's own HTTP metrics endpoint is already scraped by Prometheus (see `data_plane_quality_gauges.md`).

## Evolution Roadmap

This ADR maps the stages of temporal reasoning the agent will progress through. Part 2 covers stages 1-2.

**Stage 1 — Windowed queries + bootstrap hint.** *(Part 2 — this ADR)*
Tools accept `window_seconds` / `since_seconds`. Agent receives a single rough hint. Prompt teaches the doubling strategy with a cap.

**Stage 2 — Narrow-first, widen-on-miss.** *(Part 2 — this ADR)*
Agent starts with a 60-second window, widens to 120/300/900 only if nothing is found. This is the "walk backwards" behavior in its simplest form.

**Stage 3 — Anomaly onset detection.** *(future part)*
A dedicated `find_anomaly_onset(metric_name)` tool that scans backwards via Prometheus `query_range` to find the moment a metric transitioned from its baseline range to its current off-baseline state. This removes the agent's reliance on external hints — it derives the event time from the symptom itself.

**Stage 4 — Multi-metric correlation.** *(future part)*
After finding onsets for multiple anomalous metrics, order them chronologically. The metric with the earliest onset is closest to the root cause. The last is furthest downstream. This reconstructs the causal chain of a cascading failure the way a seasoned NOC engineer does.

**Stage 5 — Learned per-fault-type propagation profiles.** *(future part)*
Over many investigations, the system builds typical propagation profiles by fault class. "Data plane faults visible within 10s. Diameter timeouts: 60-90s. Container crashes: instant." The agent uses these to choose smarter initial windows than the fixed 60s default, and the domain knowledge accumulates over time.

## Files to Change in Part 2

**Tool layer:**
- `agentic_ops/tools.py` — add `window_seconds` to `query_prometheus`, add `since_seconds` to `read_container_logs` (the v1.5 base tools that v5 wraps)
- `agentic_ops_v5/tools/data_plane.py` — add `window_seconds` to `get_dp_quality_gauges`, replace hardcoded `_WINDOW = "30s"` with parameterized value
- `agentic_ops_v5/tools/metrics.py` — thread `window_seconds` through v5's `query_prometheus` wrapper
- `agentic_ops_v5/tools/log_search.py` — thread `since_seconds` through v5's `read_container_logs` wrapper

**Agent layer:**
- `agentic_ops_v5/prompts/network_analyst.md` — add the "Temporal Reasoning" section with the doubling strategy
- `agentic_ops_v5/orchestrator.py` — read `anomaly_window_hint_seconds` from session state and expose it to the `NetworkAnalystAgent` prompt template

**Trigger layer:**
- `agentic_chaos/orchestrator.py` — write `anomaly_window_hint_seconds: 300` into ADK session state before invoking the challenge agent (deliberately NOT derived from `fault_injected_at`)
- `gui/server.py` — write `anomaly_window_hint_seconds: 300` into v5 investigation WebSocket's session state

## Why This Design Transfers to Production

Once implemented, the agent will behave identically whether it is invoked by:
- A chaos test that injected a fault 45 seconds ago
- A GUI button click from an operator who noticed something 2 minutes ago
- An alert webhook that fired 30 seconds ago
- A cron job running periodic investigations

In all four cases the agent sees the same interface: a rough hint saying "the problem started in roughly the last 5 minutes," a set of time-windowed tools, and a prompt telling it to start narrow and widen only if needed. The agent's reasoning does not distinguish between "test" and "real" — because it cannot.

This is the fundamental design goal of Part 2: **make the agent's temporal behavior indistinguishable from a NOC engineer's, so it transfers to any trigger path without retraining.**

## Alternatives Considered

1. **Leak `fault_injected_at` from chaos to agent.** Rejected. Trains the agent on ground-truth timing that won't exist in production. Was my original proposal in the brainstorm; the operator correctly pushed back.

2. **Hide window selection inside tools via auto-retry.** (A "smart" `get_metrics(metric)` that internally widens until it finds something, without the agent knowing.) Rejected. Hides reasoning from the trace, prevents the agent from learning, and couples retry logic to tool implementation. The NOC engineer's skill is choosing the right window — that skill should live in the agent, not the tool.

3. **Variable hint values per trigger path** (e.g., chaos=60s, GUI=300s, alert=90s). Rejected as over-engineering for Part 2. Pin at 300 everywhere. Revisit in a later part once we have evidence that a single value is insufficient.

4. **Pass an ISO timestamp instead of a seconds-relative hint.** Rejected. Seconds-relative is simpler, matches how operators think ("the last few minutes"), and avoids timezone/clock skew issues between trigger systems.

5. **Hardcode 60-second default in tools, ignore the hint.** Rejected. The hint is informative — it tells the agent the maximum meaningful lookback. Without it, the agent would widen unnecessarily in cases where the problem is truly recent, or fail to widen enough for slow-propagating faults.
