# ADR: Dealing with Temporality — Part 1: Fault Propagation Verification

**Date:** 2026-04-05
**Status:** Accepted
**Series:** Part 1 of N — subsequent parts will address time-windowed observation tools (Prometheus range queries, `docker logs --since`, lookback strategy in the agent)

---

## Decision

Replace the old `SymptomObserver` polling loop with a new `FaultPropagationVerifier`. The chaos framework waits a **single, framework-wide value** (`FAULT_PROPAGATION_TIME_SECONDS = 30`) after injecting every fault — no per-scenario overrides, no CLI overrides. Every failure gets the full 30 seconds to show its primary, secondary, and tertiary effects before the RCA agent is invoked. The verifier then takes a single metrics snapshot and filters the delta against significance thresholds to produce one of three verdicts: `confirmed`, `inconclusive`, or `not_observed`. The RCA agent is invoked in all three cases unless the operator passes `--abort-on-unpropagated`, in which case the agent call is skipped while the rest of the pipeline (Healer, CallTeardown, EpisodeRecorder) still runs.

## Context

### The broken observation loop

The chaos framework had a `SymptomObserver` — a `LoopAgent` that polled metrics and logs every 5 seconds for up to 30 seconds, exiting as soon as it detected any signal. Its job was to *verify* that an injected fault had manifested before invoking the RCA agent, and then pass control downstream.

In a P-CSCF latency scenario run on 2026-04-05, this loop **exited after 137 milliseconds** while reporting `symptoms_detected: True`, producing an empty `metrics_delta` and a corrupted downstream agent run. Investigation surfaced three independent bugs, any one of which on its own would have been enough to ruin the observation:

1. **Exit-on-first-signal with no minimum wait.** The loop's condition was `symptoms_detected = bool(delta) or bool(notable_logs)`. On the very first iteration, if *anything* looked suspicious, it exited. No minimum elapsed time. No "wait at least N seconds before declaring anything." This is the 137ms exit.

2. **Log-based signal detection is inherently noisy.** `notable_logs` was built by running `docker logs --tail 20` on every container, then keyword-matching on `error`, `fail`, `timeout`, `lost`, `drop`, etc. `docker logs --tail N` returns the last N log lines **regardless of when they were written**. Any long-lived container has historical errors — from startup, previous episodes, benign Diameter warnings marked as "ignore" in the ontology, UE signal loss from hours ago. These false positives always triggered the loop to exit.

3. **`bool(delta)` is too permissive.** Even on a healthy network, counters drift every few seconds — SBI keep-alives, `httpclient:connfail` ticking up due to pre-existing configuration issues already flagged in the ontology as `is_pre_existing: true`, etc. Any non-zero delta fired the condition, regardless of whether it represented an actual fault manifestation.

The net effect: the observer routinely declared victory on noise 137 milliseconds after fault injection, before the fault had any chance to actually propagate through the stack. The RCA agent then tried to diagnose a network it had no real observation data for.

### Why this wasn't just a tuning issue

`fault_propagation_time_seconds` alone doesn't fix it. Even if we set the observer to wait 30 seconds, the loop would still exit on stale log keyword matches during the first iteration. The problem is architectural, not numeric.

Three things had to change together:

- Mandatory minimum wait (eliminate early exit)
- No log-based signal detection during verification (eliminate stale log false positives)
- Significance-based delta filtering (eliminate baseline counter drift false positives)

## Design

### FaultPropagationVerifier

A `BaseAgent` that runs between `FaultInjector` and `ChallengeAgent` in the `ChaosDirector` sequential pipeline. Its `_run_async_impl` does exactly three things, in order:

**Step 1 — Mandatory wait.** `await asyncio.sleep(FAULT_PROPAGATION_TIME_SECONDS)`. No polling, no early exit, no log-driven termination. This guarantees every fault gets a full, deterministic propagation window before anything attempts to verify it. The value is a module-level constant set to 30 seconds. There is no per-scenario override and no CLI override — every failure takes its full course. The rationale: we want every scenario to reveal secondary and tertiary downstream effects consistently, and to force the agent to reason about cascading behavior rather than a clean single-point failure. To change the value framework-wide, edit the constant in `fault_propagation_verifier.py`.

**Step 2 — Single metrics snapshot.** After the wait, call `snapshot_metrics()` once. Compute `compute_metrics_delta(baseline_metrics, current_metrics)`. No loop.

**Step 3 — Significance filtering.** Apply two thresholds to each metric delta:

- **Absolute threshold** — `|delta| >= 1` when `baseline == 0`. Catches `0 → N` transitions like `tmx:active_transactions: 0 → 2` (SIP transactions piling up because of signaling delay) or `cdp:timeouts: 0 → 5`.
- **Relative threshold** — `|delta| / |baseline| >= 20%` otherwise. Catches proportional jumps like `cdp:avg_response_time: 85ms → 450ms` (429% change — a clear signal) while dropping `httpclient:connfail: 1500 → 1503` (0.2% change — counter drift).

A delta survives filtering only if at least one threshold is met.

### Three verdicts

- **`confirmed`** — at least one metric passed filtering. The fault has observably propagated. Proceed to agent with high confidence.
- **`inconclusive`** — some metrics drifted but none crossed the significance thresholds. Proceed to agent with a warning flag in the episode record.
- **`not_observed`** — zero deltas (not even drift). The fault may not have propagated, or may not produce detectable metric signals. Proceed to agent by default; skip agent call if `--abort-on-unpropagated` is set.

### Why the pipeline keeps running even on abort

When `--abort-on-unpropagated` is set and the verdict is `not_observed`, the verifier **does not** use ADK's `escalate=True` mechanism. Setting `escalate=True` on a sub-agent inside a `SequentialAgent` terminates the entire chain — which would mean the `Healer`, `CallTeardownAgent`, and `EpisodeRecorder` don't run, leaving the network in a faulted state and losing the episode record.

Instead, the verifier writes `episode_aborted: True` to session state. The `ChallengeAgent` checks this flag and skips itself gracefully. All downstream phases still execute: the healer reverses the fault, the call is torn down, and the episode JSON is written. Only the expensive agent call is skipped.

### Logs are out of scope for verification

This is a deliberate design decision. Logs are **not** used by the verifier at all. The reasons:

- `docker logs --tail N` returns historical lines that pre-date the fault injection. Filtering by timestamp would require `docker logs --since <inject_time>`, which Part 2 of this series will address as part of time-windowed observation tools.
- Keyword matching on logs produces inherent false positives. Containers always have historical error lines. Even with `--since`, some common warnings are benign (e.g., `cxdx_get_result_code: Failed finding avp` at I-CSCF, which the ontology explicitly marks as "ignore if Diameter messages are flowing").
- Log analysis is a **troubleshooting activity**, not a symptom detection activity. It belongs in the Investigator phase of the RCA pipeline, where the agent can cite specific log lines as evidence. Using logs to gate pipeline execution confuses these two roles.

If the user wants to know whether a fault produced log signals, they can examine the container logs directly or have the Investigator read them during the RCA phase. The verifier does not and will not.

## Why This Is Bullet-Proof

1. **Deterministic minimum wait.** The verifier always waits exactly `fault_propagation_time_seconds` seconds. The 137 ms exit cannot happen. There is no code path that exits early.
2. **No stale-log false positives.** Logs are never consulted for verification. `_filter_notable_logs` is deleted along with the rest of `SymptomObserver`.
3. **Significance filtering rejects drift.** Baseline noise (`httpclient:connfail` creeping up, keep-alive counters, SBI OPTIONS polling) drops below the 20% relative threshold or the 1-unit absolute threshold and does not trigger `confirmed`.
4. **Single snapshot, not polling.** There is no "exit on first iteration" bug because there is only ever one iteration.
5. **Graceful degradation on undetected faults.** When the fault genuinely does not manifest in metrics (either because it didn't propagate or doesn't produce metric signals), the verifier records `not_observed` in the episode and proceeds. The episode is still valuable for testing how the agent handles "nothing visible" situations. Optional `--abort-on-unpropagated` skips the agent call for batch regression runs where wasted token spend matters.

## Files Changed

**New:**
- `agentic_chaos/agents/fault_propagation_verifier.py` — the verifier itself

**Modified:**
- `agentic_chaos/models.py` — marked `observation_window_seconds` as deprecated but retained for backward compatibility. No new per-scenario field added — the fault propagation time is a framework-wide constant in `fault_propagation_verifier.py`, not a scenario attribute.
- `agentic_chaos/orchestrator.py` — swapped `create_symptom_observer` out of the `ChaosDirector` pipeline, added `abort_on_unpropagated` parameter to `run_scenario`
- `agentic_chaos/cli.py` — added `--abort-on-unpropagated` flag on the `run` subcommand
- `agentic_chaos/agents/baseline.py` — also writes a flat `baseline_metrics` key so the verifier can read it without nested dict traversal
- `agentic_chaos/agents/challenger.py` — checks `episode_aborted` state flag and skips cleanly without disturbing the rest of the pipeline
- `agentic_chaos/recorder.py` — persists `fault_verification` in the episode JSON; adds a new "Fault Propagation Verification" section to the markdown report with a verdict badge (✅ confirmed / ⚠️ inconclusive / ❌ not_observed)

**Deleted:**
- `agentic_chaos/agents/symptom_observer.py` — the entire broken observer, including `_filter_notable_logs`
- `agentic_chaos/tests/test_symptom_filter.py` — tests for the deleted log filter

## Verdict Examples

Using the filter logic on representative inputs:

| Input | Filtered | Verdict | Reason |
|---|---|---|---|
| `tmx:active_transactions: 0 → 2` | ✅ kept | `confirmed` | Absolute delta ≥ 1 from baseline 0 |
| `cdp:avg_response_time: 85 → 450` | ✅ kept | `confirmed` | 429% relative change |
| `httpclient:connfail: 1500 → 1503` | ❌ dropped | — | 0.2% relative change (below 20% threshold) |
| `ran_ue: 2 → 2` | ❌ dropped | — | No change |
| All metrics show tiny drift only | ❌ all dropped | `inconclusive` | Raw delta exists, filtered delta empty |
| No metrics changed at all | ❌ nothing | `not_observed` | Raw delta empty |

## Configuration Model

| Level | Mechanism | Scope |
|---|---|---|
| Framework-wide propagation wait | `FAULT_PROPAGATION_TIME_SECONDS = 30` constant in `fault_propagation_verifier.py` | All scenarios, no overrides |
| Agent call skip | `--abort-on-unpropagated` CLI flag | Single episode, only when verdict is `not_observed` |

**There is no per-scenario or CLI override for the propagation wait.** This is deliberate. Every failure must take its full course before the RCA agent is invoked — the intent is to capture secondary and tertiary downstream effects consistently across scenarios, and to force the agent to reason about cascading behavior rather than a clean single-point failure. To change the value framework-wide, edit the constant.

## What Part 2 Will Cover

This ADR is deliberately scoped to the verification phase. The broader temporality problem extends into the agent tool layer, and will be addressed in a follow-up ADR (`dealing_with_temporality_2.md`). Specifically:

- **Time-windowed metric queries** — Prometheus `rate(metric[Xs])` and `query_range` for point-in-time metric history; `get_dp_quality_gauges` accepting a `window_seconds` parameter instead of hardcoding 30 seconds.
- **Time-windowed log reading** — `read_container_logs(container, since_seconds=N)` backed by `docker logs --since Ns` so the agent can fetch only logs produced after the fault injection timestamp.
- **Exponential lookback strategy** — guidance in the `NetworkAnalystAgent` prompt for the agent to start with a narrow window (e.g., 60 seconds) and double it up to a cap (e.g., 15 minutes) if no signal is found.
- **Fault injection timestamp exposed to the agent** — via session state so the agent knows how far back to look, instead of guessing.
- **Parameter naming convention** — settle on `window_seconds` vs `since_seconds` consistency across all observation tools.
- **Scope decision on non-Prometheus metric sources** — `kamcmd` and `rtpengine-ctl` only report current values. Decide whether to add delta-based tool variants for these or rely on Prometheus scraping (which is already in place for RTPEngine).

Part 2 will build on the deterministic propagation wait established here. Once we know *when* the fault was injected and *when* verification completed, the agent has a reliable anchor point for choosing observation windows — the piece that was previously missing.

## Alternatives Considered

1. **Tune the existing `SymptomObserver` thresholds.** Rejected — the structural bugs (early-exit, log-keyword matching, unfiltered delta) are not fixable by tuning. Each would need its own architectural change. Simpler to replace.

2. **Keep polling but add a minimum elapsed time.** Rejected — polling only has value if you want to exit early when symptoms arrive quickly. For our use case, we want to wait a full propagation window every time anyway. Polling adds complexity without benefit.

3. **Use `docker logs --since <inject_time>` for log-based verification.** Rejected — even with correct time scoping, keyword matching on logs produces too many benign matches (Diameter AVP warnings, Kamailio timer drift warnings, etc.). The ontology marks many of these as "ignore" but integrating that filter into the verifier duplicates work the agent layer already does via `interpret_log_message`. Keep the two roles separate.

4. **Per-fault-type custom verification logic** (e.g., "for `network_latency`, expect RTT probe metric to increase"). Rejected for this phase as over-scoped. The generic significance filter handles the common case well and has the advantage of being fault-type-agnostic. Per-fault verification can be added later if the generic approach produces too many `inconclusive` verdicts on slow-propagating faults.

5. **Extend the wait time instead of introducing verification.** Rejected — waiting longer alone doesn't solve the detection problem. If the verdict is `not_observed` after 30 seconds, it's unlikely that waiting 60 seconds would change that outcome for most fault types. And for slow-propagating faults, the per-scenario override is the right answer.
