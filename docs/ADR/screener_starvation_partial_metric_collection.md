# ADR: Screener Starvation — Return Partial Metric Snapshots Instead of Discarding the Whole Collect

**Date:** 2026-05-21
**Status:** Proposed
**Related:**
- Triggering episodes:
    - [`agentic_ops_v7/docs/agent_logs/run_20260521_031433_p_cscf_packet_loss.md`](../../agentic_ops_v7/docs/agent_logs/run_20260521_031433_p_cscf_packet_loss.md) — Phase 0 emitted `Anomaly screening produced no results (5 snapshots).` The classifier defaulted to `application_layer`, the path walk was skipped, RAG produced `no_flags`, the NA chased a phantom N3 outage. Final score 0%.
    - [`agentic_ops_v7/docs/agent_logs/run_20260521_123910_upf_bandwidth_cap.md`](../../agentic_ops_v7/docs/agent_logs/run_20260521_123910_upf_bandwidth_cap.md) — Same pipeline state from a different chaos scenario: `Anomaly screening produced no results (2 snapshots).` Same downstream cascade.
- Counter-example (screener fired, same scenario, same code): [`agentic_ops_v7/docs/agent_logs/run_20260521_162224_p_cscf_packet_loss.md`](../../agentic_ops_v7/docs/agent_logs/run_20260521_162224_p_cscf_packet_loss.md) — anomaly score 44.02 (threshold 28.18), 10 flags, walker localized `pcscf[eth0]`, score 100%. The pipeline works when Phase 0 has enough input snapshots.
- [`anomaly_detection_layer.md`](anomaly_detection_layer.md) — the original ADR introducing the screener and its rate-window warmup.
- [`structural_guardrails_for_llm_pipeline.md`](structural_guardrails_for_llm_pipeline.md) — same architectural principle: pipeline-load-bearing behavior must be structural, not left to per-run luck.

---

## Decision

Change `MetricsCollector.collect()` to return **whatever sub-collectors completed within the 15-second deadline** rather than discarding everything when the outer wall-clock budget is exceeded. Concretely, replace the single outer `asyncio.wait_for(collect(), timeout=15)` in `snapshot_metrics()` with a deadline-aware `asyncio.wait(..., timeout=15)` inside `collect()` itself, returning a merged dict of the sub-collectors that finished. Sub-collectors still in flight at the deadline are cancelled cleanly; their NFs are simply absent from the snapshot.

Pair this with a second, smaller change in the orchestrator: distinguish the **starved** state ("screener received fewer than `_MIN_SCORED_SNAPSHOTS` inputs") from the **clean** state ("screener scored snapshots and found no anomalies") so downstream phases can react differently. Today both states present identically (zero flags) and the classifier silently defaults to `application_layer` in both.

The structural fix (partial-result collection) addresses the root cause: snapshot loss when one NF's scrape is slow. The orchestrator state fix is the safety net: if starvation still happens on a sufficiently degraded host, the pipeline emits "I had insufficient input to screen" rather than impersonating a clean screening and routing wrong.

## Context

### The failure mode

Phase 0 (anomaly screener) requires a minimum number of metric snapshots to score the current state against its learned-healthy ECOD baseline. The threshold is 6: the preprocessor's sliding-window-rate pipeline needs 6 samples to seed temporal features (`agentic_ops_v7/orchestrator.py:400-403`), and earlier samples emit empty feature dicts that the scorer skips. With fewer than 7 snapshots in the input list, zero snapshots get scored, `best_report` stays `None`, and the orchestrator emits this literal at `orchestrator.py:448-449`:

```python
state["anomaly_report"] = (
    f"Anomaly screening produced no results ({len(snapshots)} snapshots)."
)
```

This zero-flag state propagates through every downstream phase that reads `state["anomaly_flags"]`:

| Phase | Behavior with 0 flags |
|---|---|
| 0.5 SymptomClassifier | defaults `label = application_layer` (no flags to classify into transport/application/ambiguous buckets) |
| 0.6 Path Walk | **skipped entirely** — the walker is the localizer for transport-bucket signals; with no transport flags there is nothing to localize |
| 2.5 RAG retrieval | returns `no_flags` — the retrieval query is built from the screener's flag set |
| 3 NA | falls back to event-based reasoning from whatever rule-engine events fired (typically just `core.upf.activity_during_calls_collapsed` for any IMS-side fault that breaks call setup); this single event in isolation reads like a data-plane outage and the NA chases UPF/gNB |

A single quantitative failure in Phase 0 (snapshot count) silently switches the entire pipeline from "transport-fault-localizer mode" into "application-layer-fallback mode." No downstream phase has any signal that this happened.

### Where the snapshots come from

`ObservationTrafficAgent._collect_metrics()` polls `snapshot_metrics()` on a ~5s cadence for the full observation window (~120s). Expected yield: ~24 snapshots in the list handed to Phase 0. The collector wrapper at `agentic_chaos/tools/observation_tools.py:71-89` is the failure point:

```python
_METRICS_TIMEOUT = 15  # seconds

async def snapshot_metrics() -> dict[str, dict]:
    collector = _get_metrics_collector()
    collector._cache_ts = 0.0
    try:
        return await asyncio.wait_for(collector.collect(), timeout=_METRICS_TIMEOUT)
    except asyncio.TimeoutError:
        log.warning("Metrics collection timed out after %ds", _METRICS_TIMEOUT)
        return {}
```

When `wait_for` cancels `collect()`, the call returns `{}`. The observation loop then does:

```python
metrics = await snapshot_metrics()
if metrics:                          # ← empty dict skipped
    metrics["_timestamp"] = time.time()
    snapshots.append(metrics)
```

Empty dict → not appended. A run where most iterations time out doesn't produce *incomplete* snapshots — it produces *fewer entries in the list*. Five entries in 938 seconds (the prior p-cscf run) is one entry per 188s — 37× slower than the normal 5s cadence.

### Why `collect()` exceeds 15s

The inner `MetricsCollector.collect()` at `gui/metrics.py:44-93` runs 7 sub-collectors in parallel via `asyncio.gather(..., return_exceptions=True)`. Per-collector timeouts are well below 15s (kamcmd 5s, rtpengine-ctl 5s, prometheus 3s, pyhss 3s, mongo 5s). The theoretical parallel wall-clock is `max(...) = 5s`. So in steady state the outer 15s budget is never threatened.

In practice the 5s-per-collector ceiling is wall-clock from the docker-exec/HTTP perspective — it does not bound the *Python-coroutine* wall-clock when:

1. **Docker daemon contention.** `kamcmd`, `mongosh`, and `rtpengine-ctl` all run via `docker exec`. The ObservationTrafficAgent is concurrently invoking `docker exec e2e_ue1 …` for pjsua FIFO writes and `docker exec e2e_ue1 docker logs …` for call-confirmation polls. The daemon serializes some operations; per-call latency climbs from milliseconds to seconds.

2. **Kamailio worker-thread starvation during degraded scenarios.** `kamcmd stats.get_statistics all` runs on the same MI socket that worker threads service. When workers are blocked on degraded SIP/HTTP paths (e.g., pcscf's `httpclient:connfail` retries to pyhss), the kamcmd response queues behind them. The 5s per-collector timeout fires per-NF, but if all three CSCF collectors compound, the gather's wall-clock drifts past 15s.

3. **Event-loop pressure.** Asyncio cancellation is cooperative; cancelling a coroutine blocked in a synchronous subprocess wait incurs cleanup latency.

The result: the outer `wait_for` cancels everything, including the four or five sub-collectors that *already completed*. Those completed results are discarded along with the in-flight ones.

### Starvation vs. blindness — the distinction the orchestrator currently cannot make

Two ways Phase 0 produces zero flags:

- **Starvation:** the screener was *starved* of input data — fewer than 7 snapshots reached it, so ECOD never ran. This is an input-supply failure.
- **Blindness:** the screener ran on enough snapshots and ECOD scored everything below threshold — the run looked healthy. This is a normal clean-stack outcome.

These look identical from `state["anomaly_flags"] == []` downstream. The classifier and the routing logic make the same decision in both cases (default to `application_layer`). That is wrong for the starvation case: the pipeline should know it lacks the evidence to route confidently, not pretend it ran cleanly.

The current text in `state["anomaly_report"]` does distinguish the two (`"Anomaly screening produced no results (5 snapshots)"` vs `"No anomalies detected"`), but only as freeform prose for the NA prompt. No structural state key tells the classifier or the router which case it's in.

### Why this is the right problem to fix

The counter-example run (`run_20260521_162224_p_cscf_packet_loss.md`, same scenario, same code, 100% score) proves the rest of the pipeline is correct: when Phase 0 fires flags, the classifier picks `mixed`, the walker localizes `pcscf[eth0]` at 45.3% drops within a 5-second probe window, RAG retrieves 90%-similar episodes, and the parallel Investigators triangulate via `measure_rtt('pcscf','icscf')=28.8%` and `measure_rtt('rtpengine','pcscf')=31.8%`. The diagnosis cascades correctly the moment Phase 0 has input.

So the failure is not in the screener's model, not in the walker, not in the classifier, not in the NA prompt. It is in the single line that says "if 15 seconds is up, throw away everything." Every other phase is downstream of that decision.

## Design

### Change 1 — partial-result return in `MetricsCollector.collect()`

Replace the current pattern (outer `wait_for` cancels everything) with an inner deadline that returns whatever sub-collectors completed.

**Today** (`gui/metrics.py:44-93`):

```python
async def collect(self) -> dict[str, dict]:
    if now - self._cache_ts < CACHE_TTL and self._cache:
        return self._cache
    results = await asyncio.gather(
        self._collect_prometheus(),
        self._collect_kamailio("pcscf"),
        self._collect_kamailio("icscf"),
        self._collect_kamailio("scscf"),
        self._collect_rtpengine(),
        self._collect_pyhss(),
        self._collect_mongo(),
        return_exceptions=True,
    )
    # … merge `results` into `merged` …
    return merged
```

**Proposed**:

```python
_COLLECT_DEADLINE = 12  # seconds — under the wrapper's 15s so the wrapper
                       # is a true backstop, not the load-bearing timeout

async def collect(self) -> dict[str, dict]:
    if now - self._cache_ts < CACHE_TTL and self._cache:
        return self._cache

    # Name the collectors so we can attribute partial results back to NFs
    coros = {
        "prometheus": self._collect_prometheus(),
        "pcscf":      self._collect_kamailio("pcscf"),
        "icscf":      self._collect_kamailio("icscf"),
        "scscf":      self._collect_kamailio("scscf"),
        "rtpengine":  self._collect_rtpengine(),
        "pyhss":      self._collect_pyhss(),
        "mongo":      self._collect_mongo(),
    }
    tasks = {name: asyncio.create_task(coro) for name, coro in coros.items()}
    done, pending = await asyncio.wait(
        tasks.values(),
        timeout=_COLLECT_DEADLINE,
        return_when=asyncio.ALL_COMPLETED,
    )
    # Cancel slow sub-collectors and let them clean up
    for t in pending:
        t.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
        log.info(
            "MetricsCollector deadline: %d of %d sub-collectors completed within %ds",
            len(done), len(tasks), _COLLECT_DEADLINE,
        )

    # Build merged from completed tasks only, attributed by NF name
    merged: dict[str, dict] = {}
    for name, t in tasks.items():
        if not t.done() or t.cancelled():
            continue
        if t.exception() is not None:
            continue
        result = t.result()
        if name == "prometheus" and isinstance(result, dict):
            merged.update(result)              # multi-NF result
        elif isinstance(result, dict) and result.get("metrics"):
            merged[name] = result
    # … history append and cache update, unchanged …
    return merged
```

The outer `snapshot_metrics()` wrapper keeps its `wait_for(15)` as a backstop (in case the cancellation path itself wedges), but `collect()` is now responsible for its own deadline at 12s. A snapshot that has 5-of-7 NFs populated is appended to the list and progresses the screener instead of being discarded.

### Change 2 — surface starvation as a distinct state in the orchestrator

In `agentic_ops_v7/orchestrator.py`, replace the implicit zero-flag fallback with an explicit state machine value the classifier and router can read.

Today:

```python
if best_report is not None:
    state["anomaly_report"] = best_report.to_prompt_text()
    state["anomaly_flags"] = best_report.to_dict_list()
    # … window timestamps, etc.
else:
    state["anomaly_report"] = (
        f"Anomaly screening produced no results ({len(snapshots)} snapshots)."
    )
```

Proposed:

```python
_MIN_SCORED_SNAPSHOTS = 1   # at least one snapshot must pass the warmup
                            # and be scored for screener output to be valid

if best_report is not None and len(scored_snap_timestamps) >= _MIN_SCORED_SNAPSHOTS:
    state["screener_status"] = "scored"
    state["anomaly_report"] = best_report.to_prompt_text()
    state["anomaly_flags"] = best_report.to_dict_list()
    # … window timestamps, etc.
elif len(snapshots) < 7:   # below preprocessor warmup
    state["screener_status"] = "starved"
    state["screener_starvation_reason"] = (
        f"Only {len(snapshots)} snapshots reached Phase 0; the rate-window "
        f"preprocessor needs ≥7 to seed temporal features."
    )
    state["anomaly_report"] = (
        f"Anomaly screening starved — {len(snapshots)} input snapshots, "
        f"below the 7-snapshot warmup threshold. The metrics collector "
        f"likely hit its per-snapshot deadline repeatedly during the "
        f"observation window. Downstream phases should treat the absence "
        f"of anomaly flags as 'unknown', not 'healthy'."
    )
    state["anomaly_flags"] = []
else:
    state["screener_status"] = "clean"
    state["anomaly_report"] = "Anomaly screening ran; no anomalies detected."
    state["anomaly_flags"] = []
```

The classifier and the routing logic then read `state["screener_status"]`. For `starved`, two routing options (open question — see "Open questions" below):

1. **Conservative:** route to the full application-layer pipeline AND run the path walk on every transport-capable flow (since we can't trust the classifier's bucket-based routing). The NA prompt explicitly includes the starvation reason so the model knows it has degraded input.
2. **Fail-fast:** mark the run as `verdict_kind=insufficient_evidence` and short-circuit, with the recommendation "metrics-collector saturation prevented anomaly screening; re-run with reduced concurrent load or increase per-snapshot deadline."

The conservative option is the better default — the walker is cheap and produces high-confidence localization when it does. Fail-fast is a tempting safety valve but in practice the user wants *a diagnosis*, not an apology.

### Why both changes are needed

Change 1 alone fixes the proximate cause (snapshot loss from one slow NF) and will eliminate the starvation case in the vast majority of runs. But it does not bound the worst case: under enough host load, even partial-result collection can fail to fill 7 snapshots. Change 2 ensures the pipeline degrades visibly when that happens, rather than silently mis-routing to the wrong path.

Change 2 alone (without Change 1) would convert silent mis-routing into a loud apology, but would not actually fix any episodes — the screener would still be starved on the same scenarios. Change 1 is load-bearing; Change 2 is the safety net.

## Trade-offs and limitations

- **Partial snapshots have missing NFs.** A snapshot built from 5-of-7 sub-collectors is structurally well-formed (the merged dict simply omits the slow NF), and the screener's per-bucket model handles missing keys via the preprocessor's default-to-zero rule (`screener.py:382-388`). The risk is that a metric the screener relies on for bucketing — `calls_active` or `registration_in_progress` — comes from a sub-collector that's chronically slow under degraded scenarios. Need to confirm those bucketing inputs come from `_collect_prometheus()` (fast, 3s timeout) rather than from a CSCF kamcmd path.

- **Per-NF cancellation may leak `docker exec` processes.** `asyncio.create_subprocess_exec` returns a `Process`; cancelling the wrapping task does not always reap the underlying subprocess immediately. The host could accumulate zombie `docker exec` invocations under sustained degradation. Mitigation: in the cancellation handler, explicitly `proc.terminate()` and `await proc.wait()` for any sub-collector that owns a subprocess handle. Worth verifying with `pgrep -fc 'docker exec'` after a long degraded run.

- **`_COLLECT_DEADLINE=12s` is one knob more.** Currently the per-NF timeouts (3-5s) plus the outer 15s wrapper are the only two budgets. Adding an inner 12s deadline creates a third. The justification: the inner deadline is the one the screener cares about (because it determines whether the call returns *something*); the outer 15s is a defensive backstop in case the cancellation path itself hangs. Tuning: 12s leaves 3s of headroom above the 5s-per-collector ceiling for serialization overhead, but is still under the wrapper's 15s.

- **The starvation message in the NA prompt does not actually prevent the NA from hallucinating.** Even with `screener_status=starved` and an explicit "treat absence of flags as unknown" in the prompt, an LLM may still confabulate a diagnosis from the lone `upf.activity_during_calls_collapsed` event. The mitigation is the routing change — running the path walk unconditionally when starved — not the prompt change. The prompt change is the audit trail.

- **The fix does not address the underlying scrape-path degradation.** Docker daemon contention, kamailio worker starvation, and event-loop pressure are real environmental issues. The right long-term direction is probably a host-side metrics shim (kamailio's MI socket forwarded out of the container, a sidecar that exposes the data over a stable HTTP endpoint) that bypasses `docker exec` entirely. That's a much larger change; this ADR is the bounded fix.

## Implementation outline

1. **Refactor `MetricsCollector.collect()`** to use `asyncio.wait(..., timeout=_COLLECT_DEADLINE)` over a name-keyed task dict. Update the merging logic to iterate per task instead of per index position. Keep the cache-hit short-circuit at the top. (`gui/metrics.py`)
2. **Add a `_COLLECT_DEADLINE` constant** at the top of `gui/metrics.py` with the rationale comment.
3. **Cancellation-cleanup helper** for sub-collectors that own subprocesses: on cancellation, ensure the underlying `docker exec` subprocess is terminated and reaped (verify with a stress test that runs the partial-result path 100× and counts zombie processes).
4. **Add `screener_status` keys to orchestrator Phase 0** as described in Change 2. Update the existing references to `state["anomaly_report"]` in downstream phases to also read `state["screener_status"]` where they make routing decisions.
5. **Update the symptom classifier** (`agentic_ops_v7/symptom_classifier.py:classify()`) to branch on `screener_status` first: if `starved`, return a new label `insufficient_anomaly_evidence`; existing code path otherwise.
6. **Update the routing logic** to treat `insufficient_anomaly_evidence` as "run the path walk on every plausible flow, then fall through to app-layer regardless of walker outcome." This is the conservative option from the design section.
7. **Tests:**
    - Unit: `MetricsCollector` with one mock sub-collector that sleeps `> _COLLECT_DEADLINE`; assert the returned dict contains the fast sub-collectors and omits the slow one.
    - Unit: orchestrator Phase 0 with a snapshot list of length 3; assert `state["screener_status"] == "starved"` and `state["anomaly_report"]` mentions the starvation cause.
    - Integration: pin test using a recorded snapshot list that previously produced `Anomaly screening produced no results (5 snapshots)`; assert the new code path produces at least 7 snapshots after applying the partial-result rule to a synthetic slow-NF scenario.

## Validation target

A re-run of the p-cscf packet-loss scenario on a freshly-deployed stack under typical load should not exhibit starvation. The cleaner test is a deliberately-loaded stack: bring up the chaos pipeline with 2-3 background `docker exec` loops generating daemon contention, inject p-cscf 30% loss, and confirm:

- `MetricsCollector.collect()` returns merged dicts with 5-7 NF entries (not 0-or-7) across the observation window.
- Phase 0 receives ≥ 7 snapshots in the input list.
- Phase 0 emits `screener_status = "scored"` with non-empty flags.
- The walker localizes `pcscf[eth0]`.
- Final score = 100%.

A negative test (starvation case): run the same setup but with `_COLLECT_DEADLINE` artificially lowered to 1s. Confirm:

- Phase 0 emits `screener_status = "starved"`.
- The classifier returns `insufficient_anomaly_evidence`.
- The walker runs anyway and localizes correctly.
- The NA's diagnosis text references the starvation reason.

## Resolved decisions (from review)

1. **`_COLLECT_DEADLINE = 12s`, hardcoded for now.** 12s leaves 3s headroom above the worst per-NF timeout (5s) for serialization overhead, and is still under the wrapper's 15s backstop. We are deliberately not making this configurable per scenario class in this iteration — one knob, one place, one value. Revisit after the first batch of validation runs if any scenario consistently sits above the threshold.

2. **Starved-state routing: conservative — run the walker unconditionally.** When `screener_status = starved`, the orchestrator routes through the path walk on every transport-capable flow and then falls through to the application-layer pipeline regardless of walker outcome. The walker is cheap, produces high-confidence localization when it does, and never harms the diagnosis when it doesn't. Fail-fast (`verdict_kind=insufficient_evidence`) is rejected — the user wants a diagnosis, not an apology.

3. **`screener_status` is a typed enum.** Concretely: `Literal["scored", "starved", "clean"]` declared in `agentic_ops_v7/state_types.py` (or wherever the orchestrator's TypedDict shape lives) and referenced by exact string value at every downstream consumer. Pattern-matched, not stringly-compared.

4. **Subprocess-cancellation cleanup is in scope.** On task cancellation, sub-collectors that own a `docker exec` subprocess must explicitly `proc.terminate()` and `await proc.wait()` to reap the process. The stress test (running the partial-result path 100× and counting `pgrep -fc 'docker exec'` afterward) is a required check before this lands.

5. **The partial-result fix applies always, everywhere.** `MetricsCollector.collect()` is used for steady-state GUI updates as well as chaos snapshots, and the semantics are identical in both contexts: a 5-of-7 snapshot is more useful than a 0-of-7 snapshot for every consumer. No conditional gating on caller context.

## Out of scope

- Host-side metrics shim that bypasses `docker exec` entirely. Larger architectural change; defer.
- Increasing the screener's tolerance for fewer snapshots (lowering the 7-snapshot warmup threshold). The threshold is structural — the preprocessor needs that many samples for its rate-window features to stabilize. Lowering it would solve starvation by destabilizing the screener model.
- Re-architecting `ObservationTrafficAgent` to pace its `docker exec` calls. Reducing daemon contention is worth doing, but it's a different change with its own trade-offs (slower call setup, less realistic load).
- The Phase 7 Synthesis prompt directive for `verdict_kind=insufficient_evidence`. If we adopt the fail-fast option for starved-state routing in the future, that prompt directive becomes load-bearing — but the conservative option recommended here doesn't need it.
