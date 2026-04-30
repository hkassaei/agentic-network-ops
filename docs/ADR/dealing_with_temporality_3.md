# ADR: Dealing with Temporality — Part 3: Anchoring All Phases to the Anomaly Window

**Date:** 2026-04-29
**Status:** Proposed — pending implementation.
**Series:** Part 3 of N — builds on [`dealing_with_temporality_1.md`](dealing_with_temporality_1.md) (FaultPropagationVerifier) and [`dealing_with_temporality_2.md`](dealing_with_temporality_2.md) (per-tool `window_seconds` parameter + NA doubling-lookback prompt).
**Related ADRs:**
- [`falsifier_investigator_and_rag.md`](falsifier_investigator_and_rag.md) — the Investigator+plan architecture this ADR re-anchors.
- [`kb_backed_tool_outputs_and_no_raw_promql.md`](kb_backed_tool_outputs_and_no_raw_promql.md) — the KB-annotated tool layer this ADR extends with time parameters.
- [`anomaly_detection_layer.md`](anomaly_detection_layer.md) — the Phase 0 screener whose timestamp anchors the rest of the pipeline under this ADR.
- [`anomaly_detector_replace_river_with_pyod.md`](anomaly_detector_replace_river_with_pyod.md) — the ECOD screener that produces the timestamps we anchor on.
- [`../critical-observations/challenge_with_stochastic_LLM_behavior.md`](../critical-observations/challenge_with_stochastic_LLM_behavior.md) — orthogonal failure mode (LLM stochasticity); not addressed by this ADR.

---

## Decision

Make every phase of the v6 diagnostic pipeline reason about **the same point in time**: the observation window during which the anomaly was actually present. Today the Phase 0 screener observes state at time T₀ (during fault traffic) and the Phase 5 Investigators query state at time T₁ ≈ T₀ + 60–300s (after traffic has stopped). Both write into the same diagnosis but they describe different worlds. This ADR introduces:

1. **A single canonical anomaly-window timestamp** propagated through every phase's session state.
2. **Time-aware Prometheus tools** that accept an `at_time_ts` parameter and emit time-anchored PromQL.
3. **Snapshot-replay for container-state tools** (`kamcmd`, `rtpengine-ctl`, etc.) so historical kamcmd output can be reproduced from the snapshots the chaos framework already captures.
4. **Honest categorization in the Investigator prompt** about which tools are time-aware and which are inherently live-only, with explicit guidance on how to interpret a contradiction between live state and screener-time state.

The result: Phase 5 Investigator probes describe the world the Phase 0 screener flagged, instead of whatever state the system happens to be in by the time the Investigator runs.

---

## Context

### The structural problem this ADR addresses

The v6 pipeline's phases are temporally inconsistent.

```
T_0: ObservationTrafficAgent generates traffic + collects metric snapshots
                             at 5s intervals.
                             Phase 0 screener fires `derived.rtpengine_loss_ratio = 14.09`
                             based on samples taken DURING the fault.

T_observation_end: traffic stops. Framework moves to challenge mode.

T_1: Phase 5 Investigators run. `get_dp_quality_gauges(window_seconds=60)` queries
     Prometheus at T_1. The 60s window covers (T_1 - 60s) to T_1 — entirely
     POST-traffic. `rate(rtpengine_packetloss_samples_total[60s]) ≈ 0`.
     `_safe_div(0, 0) = 0`. Tool prints `loss (recent): 0`.

T_2: Investigator concludes "RTPEngine has zero loss" and disproves the
     hypothesis that pointed at the actual fault.
```

The Investigator's `loss = 0` reading is technically correct for `T_1` — there genuinely is no recent loss because there is no recent traffic. But it is **not relevant to the question being investigated**, which is "what was happening at T₀ when the screener flagged the loss?"

### The smoking-gun episode

[`run_20260429_163802_call_quality_degradation`](../../agentic_ops_v6/docs/agent_logs/run_20260429_163802_call_quality_degradation.md): the rtpengine packet-loss scenario produced exactly this pattern. h2's investigator, hypothesizing rtpengine-side loss, ran:

- `get_dp_quality_gauges(window_seconds=60)` → `RTPEngine: loss (recent): 0` (because no RR samples in the 60s window — traffic had stopped).
- `get_nf_metrics()` → `rtpengine: packets_lost = 0` (cumulative counter, plus dead under tc-egress loss anyway).
- `measure_rtt(upf, rtpengine_ip)` → did show 33% loss on the live link, but that probe is itself live-only and would be inconsistent if the fault were transient.

Verdict: **DISPROVEN** with confidence: high. Diagnosis landed on UPF. Score: 31%.

The Phase 0 screener had the right signal (`rtpengine_loss_ratio = 14.09` at T₀). The chain just wasn't built to ask Investigators to reason about T₀; it asked them about T₁.

### Why Parts 1 and 2 don't cover this

- **Part 1** (`FaultPropagationVerifier`) ensures the framework waits long enough after fault injection for the fault to manifest before invoking the RCA agent. It addresses *"is the fault visible by the time we observe?"* — not *"do all phases of the agent see the same observation?"*.
- **Part 2** (`window_seconds` parameter, doubling-lookback prompt for NA) gave each tool a tunable lookback, and taught NetworkAnalyst to widen the window if nothing is found at 60s. But the lookback is **always anchored to `now()`** at the moment the tool is called, not to the timestamp of the screener's flag. NA at T_NA looks at `[T_NA - 60s, T_NA]`; Investigator at T_I looks at `[T_I - 60s, T_I]`. These windows don't overlap with each other or with the screener's snapshot.

Part 2 also defaults `anomaly_window_hint_seconds = 300` and deliberately does NOT leak the precise fault-injection time. That is the right choice for production-portable reasoning — but inside the framework where we DO know the screener's snapshot timestamp, refusing to use it forces every phase to re-discover "when did this happen?" independently. They sometimes converge; often they don't.

This ADR closes the gap by making the screener's observation window the single canonical anchor for all downstream phases.

### The chaos framework already collects what this ADR needs

Two pieces of infrastructure already exist:

1. **Observation snapshots.** `ObservationTrafficAgent` (`agentic_chaos/agents/observation_traffic.py`) writes `observation_snapshots` into session state — a list of metric-text snapshots, each tagged with a wall-clock timestamp, taken every 5s during the observation window. Today Phase 0 screener consumes these. Other phases ignore them.
2. **Observation window timestamps.** `observation_window_end` and `observation_window_duration` are already set in challenger session state and passed to the v6 orchestrator (`agentic_chaos/agents/challenger.py:113-123`). What's missing is propagation into Phase 5 tool invocations.

The data is collected. The plumbing isn't done.

---

## How tools split when we ask them to look back in time

Every tool the v6 orchestrator exposes falls into one of three categories:

### Category A — Prometheus-backed: trivially time-anchorable

Prometheus supports `query` with `?time=` for instant queries at a past moment, and `query_range` for explicit `[start, end]` intervals. Both are simple HTTP query parameter changes.

| Tool | Backend | Today's behavior | After this ADR |
|---|---|---|---|
| `get_dp_quality_gauges` | Prometheus | `rate(metric[window_seconds]s)` at now | `rate(metric[window_seconds]s @ at_time_ts)` |
| `compare_to_baseline` | Prometheus + kamcmd | mixed; Prometheus part queries now | Prometheus part anchored; kamcmd part falls into Category B |
| `get_nf_metrics` (Prometheus subset) | Prometheus | snapshot-at-now of AMF/SMF/UPF/PCF gauges + counters | snapshot-at-time |

**Cost**: ~150 lines across these tools + tests for the time-anchored query path.

### Category B — Container-state: time-shiftable IF we use saved snapshots

`docker exec kamcmd stats.get_statistics`, `docker exec rtpengine-ctl list totals`, `pyhss REST /ims_subscriber/list`, MongoDB CLI counts. These query in-process state at query time. There is no native time-rewind for any of them.

But the chaos framework's `observation_snapshots` already contain the kamcmd / rtpengine-ctl / pyhss / mongo outputs from the observation window. The fix is to route tool calls to consult the snapshots when `at_time_ts` is provided, picking the snapshot closest to the requested time:

```
# pseudocode for the snapshot-replay layer
def get_kamcmd_at(container: str, at_time_ts: float) -> dict:
    if at_time_ts is None:
        return await live_kamcmd(container)
    snap = closest_snapshot(observation_snapshots, at_time_ts)
    if abs(snap.timestamp - at_time_ts) > MAX_DRIFT:
        return {"error": "no snapshot near requested time", "drift": ...}
    return snap.metrics.get(container)
```

The snapshots are at 5s resolution, so `MAX_DRIFT = 5s` is the right tolerance. Anything outside the observation window has no historical data — return an explicit "not available historically" so the agent knows to use a different tool.

**Cost**: ~250 lines. The bulk is the snapshot routing + matching logic; tests for "snapshot found", "snapshot too distant", "snapshot doesn't have this NF" cases.

### Category C — Active probes: live-only, no time travel possible

`measure_rtt`, `check_process_listeners`, `run_kamcmd <command>`, `read_running_config`. These actively probe the network or processes *now*. A ping packet sent now travels now. There is no recorded version of "what would `measure_rtt` have returned at T₀?" — we'd have had to run it at T₀ to know.

These tools stay live-only. The architectural change here is **prompt-level honesty**: tell the Investigator explicitly what each tool means, and how to interpret contradictions:

> *Tools that return historical state at the anomaly window: `get_nf_metrics`, `get_dp_quality_gauges`, `compare_to_baseline`. Use these for evidence about the failure.*
>
> *Tools that probe live state right now: `measure_rtt`, `check_process_listeners`, `run_kamcmd <command>`. These tell you whether the fault is STILL present, not whether it WAS present. A clean live result does NOT contradict a flagged historical anomaly — it indicates the fault was transient. That's diagnostic information, not refutation.*

This bit is critical: today an investigator running `measure_rtt` and getting clean RTT will treat the live result as falsifying the hypothesis. Under the new model, "clean RTT live + flagged loss historical" reads as "transient fault — the fault was real but isn't currently active," which is a category of finding the synthesis layer should be able to consume.

**Cost**: prompt edits + tool docstring updates. Maybe ~80 lines including the synthesis-side handling of "transient" verdicts.

---

## What this fixes vs doesn't fix

### Does fix

- The h2-disproven-by-stale-data pattern that lost `call_quality_degradation` at 21–31% across multiple runs.
- "Investigator says X is fine now, screener said X was broken at T₀, which one wins?" — now the Investigator queries T₀, so they agree or genuinely disagree (transient vs persistent fault).
- Synthesis decisions that rest on contradictions between two phases that were actually looking at different worlds.
- The `get_dp_quality_gauges` `loss = 0` collision documented in the call_quality_degradation analysis: not by changing the tool's `_safe_div`, but by aiming the query at T₀ when traffic was flowing.

### Does NOT fix

- **LLM stochasticity** (the call_quality_degradation 90→26 swing on otherwise identical reruns). Documented in [`challenge_with_stochastic_LLM_behavior.md`](../critical-observations/challenge_with_stochastic_LLM_behavior.md). Independent of this ADR.
- **Missing features in the screener feature set** (DNS-direct metrics, etc.). Whatever isn't measured at T₀ stays unmeasured.
- **Pre-existing dead-by-design metrics** like rtpengine-ctl's `Packets lost` counter. Those need to be removed from `get_nf_metrics` regardless of when you query them; documented as separate cleanup work.
- **NA hypothesis-ranking bias** ("the flagged NF IS the cause" blind spot). Independent of this ADR.

---

## Implementation plan — staged

The four layers can ship independently, with usable behavior change after layers 1+2 (about half the work).

### Layer 1 — Plumbing: propagate `anomaly_window_ts` everywhere

Add to v6 orchestrator session state:
- `anomaly_window_start_ts: float`
- `anomaly_window_end_ts: float`
- `anomaly_screener_snapshot_ts: float` — the timestamp of the specific snapshot that produced the highest screener score. This is the canonical "what time should other phases ask about?"

Set them in `agentic_ops_v6/orchestrator.py:_phase0_anomaly_screener` based on the snapshots the screener consumed. Pass through to NA (Phase 3), IG (Phase 4), Investigator (Phase 5), and Synthesis (Phase 7) prompts as template variables.

**Cost**: ~30 lines + state passing. No behavior change yet — phases now know the timestamps but tools still query "now".

### Layer 2 — Time-anchored Prometheus tools

Add an optional `at_time_ts: float | None = None` parameter to:
- `get_dp_quality_gauges`
- `compare_to_baseline` (Prometheus part)
- The Prometheus subset inside `get_nf_metrics`

When `at_time_ts` is provided, emit PromQL with `@ <ts>` for instant queries or with explicit time bounds for range queries. When `None`, fall back to current behavior.

Then update the Investigator prompt to say:

> *When investigating a flagged anomaly, call time-aware tools with `at_time_ts={anomaly_screener_snapshot_ts}`. This anchors your query to the moment the screener flagged the issue, not "now". Without this, your tool reads will reflect the system after the fault has subsided and you'll incorrectly disprove valid hypotheses.*

Where `{anomaly_screener_snapshot_ts}` is templated in from session state.

**Cost**: ~150 lines including tests. Tests should cover both `at_time_ts=None` (regression: same behavior as today) and `at_time_ts=<historical>` (new path).

After Layer 1+2: scenarios where the fault is captured by Prometheus (rtpengine loss, UPF rates, the 5G core counters) work correctly. This is the bulk of the diagnostic surface area.

### Layer 3 — Snapshot replay for container-state tools

Pass `observation_snapshots` from the chaos framework's `ObservationTrafficAgent` into the v6 orchestrator's session state (it's already collected, just needs to be passed through). Then route `get_nf_metrics`'s kamcmd/rtpengine-ctl/pyhss/mongo paths to consult the snapshots when `at_time_ts` is set.

The matching logic: pick the snapshot with `|snap.ts - at_time_ts| < MAX_DRIFT` (5s for our 5s polling interval). If none match, return `{"error": "no snapshot near requested time"}` explicitly so the agent doesn't silently fall through to live data.

**Cost**: ~250 lines. The bulk is the snapshot routing + matching layer. Tests for snapshot-found, no-snapshot-near, snapshot-missing-this-NF cases.

After Layer 3: kamcmd-derived metrics (Cx response times, dialog counts, registrar state) are also time-anchored. We're then time-anchored across Categories A and B.

### Layer 4 — Prompt awareness for Category C

Tell the Investigator explicitly:
- Which tools are time-aware (`get_nf_metrics`, `get_dp_quality_gauges`, `compare_to_baseline`).
- Which tools are live-only (`measure_rtt`, `check_process_listeners`, `run_kamcmd <command>`, `read_running_config`).
- That a clean live result on a hypothesis flagged by the screener at T₀ indicates a TRANSIENT fault, not a refuted hypothesis.

Add a `confidence_modifier: "transient" | None` field on `InvestigatorVerdict` so Synthesis can consume the transient-fault signal explicitly rather than guessing.

**Cost**: ~80 lines including prompt edits, the new verdict field, and one regression test.

---

## Risks and known limitations

1. **Prometheus retention.** Vertex's default retention is ~15 days, but Prometheus's `at_time` query needs the data to still be present at query time. For our chaos runs (minutes-to-an-hour scale), this is fine. For replay analysis weeks later, history may be gone.

2. **Snapshot resolution.** 5s polling means the Investigator's view of T₀ ± 5s. Any fast-moving signal (sub-second packet bursts) gets averaged. Acceptable for our chaos-scale signals, not for fine-grained troubleshooting.

3. **Snapshot fidelity.** The observation snapshots are text dumps of kamcmd / rtpengine-ctl output. They don't capture every metric every NF exposes — only the kamcmd `stats.get_statistics all` filtered set and the rtpengine-ctl `list totals` output. If a tool needs a kamcmd command other than `stats.get_statistics`, that's not in the snapshot — and `run_kamcmd <other_command>` falls into Category C inherently anyway.

4. **Time-anchored queries can return empty for the wrong reason.** If the Prometheus scraper missed a sample at exactly T₀ (rare but possible), `query @ T₀` returns no result. The tool must surface this explicitly as "no data at this time" rather than as `0`.

5. **Tool API breakage.** Adding `at_time_ts` is additive (default None preserves behavior), but downstream callers that pickled or hashed tool signatures would notice. We have only the agent calls and tests, so the blast radius is contained.

6. **Synthesis interpreting "transient" verdicts.** A new verdict modifier requires Synthesis prompt updates. There's a small risk Synthesis learns to over-discount transient findings ("oh it's not active now, so probably nothing"). Counter-balance in the prompt: a transient fault flagged by the screener with high anomaly score is a real diagnostic signal; it just needs different framing in the diagnosis.

---

## Open questions

1. **Naming.** I've used `at_time_ts` as the tool parameter name. Alternatives: `as_of_ts`, `query_time`, `historical_ts`. Pick one and apply uniformly across tools. Bikeshed-worthy because it appears in every tool signature and every prompt.

2. **Should Phase 0 always anchor to its own snapshot, or should Phase 0 itself be allowed to look back?** Today Phase 0 takes a fresh snapshot when the orchestrator runs. We could also let it consult observation snapshots, which would let us replay an old episode through a newer screener for offline validation. Worth a follow-up but not load-bearing here.

3. **Does NA need this too?** NA reads the screener's flag list (already temporally anchored — flags carry their snapshot's reading) plus correlation analysis. NA doesn't directly call tools that hit metrics. So strictly, NA is fine without the anchoring. But for consistency and to support future NA tool calls, I'd pass the timestamps through anyway. Cheap and prevents drift.

4. **What about NETWORK ANALYST consulting the screener's snapshot's underlying data?** Today NA reads the flag-text rendering of the screener's verdict. With timestamps available, NA could in principle re-query the same time directly via the new time-aware tools. That's a future capability worth contemplating; not part of this ADR.

5. **Cost of the snapshot-passing in challenger.py.** The `observation_snapshots` list already gets passed to the RCA agent (`challenger.py:135` `metric_snapshots=observation_snapshots`), but the v6 orchestrator currently uses them only in Phase 0. Layer 3 widens that — confirm the JSON serialization of the snapshots through the ADK session state isn't going to OOM on long observation windows. With 5s polling × 5min observation = 60 snapshots × ~10kB each = ~600kB. Fine.

---

## Why this is worth doing now

We've spent today's work removing failure modes (over-flagging, IG empty output, container-state pre-check, 429 retry). Each fix raised the structural ceiling of the system. With those out of the way, the temporal-inconsistency failure mode documented here is now the largest remaining source of confident-wrong diagnoses — visible in `call_quality_degradation` (multiple runs), `data_plane_degradation` (the data plane fault gets disproven by stale Investigator probes), and contributes to other scenarios where "the fault has subsided by the time the agent looks."

It's also worth doing now because [`anomaly_detector_replace_river_with_pyod.md`](anomaly_detector_replace_river_with_pyod.md) has just shipped — the Phase 0 screener now produces highly-attributable, well-bucketed flag lists with explicit per-bucket anchor timestamps. That's exactly the data this ADR needs for the time-anchoring source. The new screener and time-anchored Investigation are mutually reinforcing — neither delivers full value without the other.

## Implementation completed 2026-04-29

1. Layer 1 — Timestamp plumbing: Phase 0 captures anomaly_screener_snapshot_ts, anomaly_window_start_ts, anomaly_window_end_ts into orchestrator state.
2. Layer 2 — Time-anchored Prometheus: get_dp_quality_gauges accepts at_time_ts; _prom_query adds ?time= param; ratios return "N/A (no samples in window)" when denominator ≤ 0.
3. Layer 3 — Snapshot replay: snapshot_replay.py provides contextvar plumbing + match helpers; orchestrator publishes observation_snapshots so container-state tools can replay them.

This was part of a bigger scope:

Final summary — all 8 architectural changes shipped:

dealing_with_temporality_3.md:
1. Layer 1 — Timestamp plumbing: Phase 0 captures anomaly_screener_snapshot_ts, anomaly_window_start_ts, anomaly_window_end_ts into orchestrator state.
2. Layer 2 — Time-anchored Prometheus: get_dp_quality_gauges accepts at_time_ts; _prom_query adds ?time= param; ratios return "N/A (no samples in window)" when denominator ≤ 0.
3. Layer 3 — Snapshot replay: snapshot_replay.py provides contextvar plumbing + match helpers; orchestrator publishes observation_snapshots so container-state tools can replay them.

get_diagnostic_metrics_tool.md:
4. Step 1 — KB schema: agent_exposed: bool field on MetricEntry (no agent_purpose, leveraging existing KB fields).
5. Step 2 — Tagging: 16 metrics tagged agent_exposed: true; 4 tagged scale_dependent; new ims_registrar_scscf:sar_timeouts entry.
6. Step 3 — Live tool: get_diagnostic_metrics(at_time_ts, nfs) with two-block-per-NF rendering.
7. Step 4 — Wired in: Investigator + Network Analyst toolsets swapped from get_nf_metrics to get_diagnostic_metrics; prompt + Pydantic Literal updated.
8. Step 5 — Time-aware mode: Historical path replays snapshots through preprocessor; renderer handles both flat and {"metrics": ...} shapes; investigator prompt instructs
at_time_ts={anomaly_screener_snapshot_ts} for time-aware tools.
