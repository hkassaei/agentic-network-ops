# ADR: Rate-Based RTPEngine Loss Ratio Feature

**Date:** 2026-04-24
**Status:** Accepted
**Related ADRs:**
- [`remove_cumulative_rtpengine_features.md`](remove_cumulative_rtpengine_features.md) — the prior decision to remove rtpengine cumulative absolute values from the feature vector. This ADR does **not** reverse that decision; it refines it.
- [`anomaly_model_feature_set.md`](anomaly_model_feature_set.md) — the feature-set reference updated alongside this ADR.
- [`anomaly_training_zero_pollution.md`](anomaly_training_zero_pollution.md) — the policy that gates temporal features on underlying counter advancement.

**Motivating episodes:**
- [`agentic_ops_v6/docs/agent_logs/run_20260423_201905_call_quality_degradation.md`](../../agentic_ops_v6/docs/agent_logs/run_20260423_201905_call_quality_degradation.md) — 30% iptables packet-loss injection on rtpengine, agent scored 15%. Anomaly screener detected nothing, event aggregator fired nothing. Agent reached for an HSS/PCF prior unrelated to the real fault.
- [`agentic_ops_v6/docs/agent_logs/run_20260422_034500_call_quality_degradation.md`](../../agentic_ops_v6/docs/agent_logs/run_20260422_034500_call_quality_degradation.md) — Same scenario one day earlier, also 15%. Same failure mode.

---

## Context

After [`remove_cumulative_rtpengine_features.md`](remove_cumulative_rtpengine_features.md) (2026-04-15) correctly removed six polluting rtpengine absolute values from the anomaly feature set, the model was left with **exactly one** rtpengine feature: `rtpengine.errors_per_second_(total)`. That feature measures rtpengine's **internal** relay errors (e.g. "can't forward," "malformed SDP"). It does **not** move when packets are dropped at the network layer **before** rtpengine sees them — which is precisely what the `call_quality_degradation` scenario injects (an iptables/tc rule on the rtpengine container's veth interface).

Consequence across two separate batch runs: a realistic media-path fault fires zero events. The Network Analyst agent reaches Phase 3 with no symptoms to reason over and falls back to generic "Diameter connectivity" priors that have nothing to do with the actual fault. Score stays at 15% regardless of what we add to the causal-chain ontology, because no event ever surfaces to trigger the reasoning.

The cause is a coverage gap in the feature vector, not an agent-reasoning bug.

## Why the obvious fix is wrong

The obvious fix — "add `rtpengine.packets_lost` and `rtpengine.average_packet_loss` back to the feature vector" — re-introduces the exact pollution `remove_cumulative_rtpengine_features.md` corrected: lifetime cumulative counters carry state across chaos runs, and lifetime averages shift permanently after any prior fault. That ADR is correct; we are not reversing it.

## Decision

Re-admit two rtpengine counters **exclusively as inputs to the sliding-window rate pipeline**, never as absolute values. Derive a single new feature — the loss ratio — from their rates. Keep every other rtpengine cumulative metric in the exclusion list.

### What enters the feature vector

One new feature:

| Feature | Formula | Type | Range | Healthy |
|---|---|---|---|---|
| `derived.rtpengine_loss_ratio` | `packets_lost_rate / (packets_lost_rate + total_relayed_packets_rate)` | `derived` ratio | [0, 1] | 0 |

Where `_rate` is the `preprocessor.py` sliding-window rate (≈30 s, 6 samples).

### What the model does NOT see

- `rtpengine.packets_lost` (absolute value) — never emitted as a feature; only its rate feeds into the ratio above.
- `rtpengine.total_relayed_packets` (absolute value) — same: never emitted as a feature.
- `rtpengine.average_packet_loss`, `rtpengine.average_mos`, `rtpengine.packet_loss_standard_deviation`, `rtpengine.total_number_of_1_way_streams`, `rtpengine.total_relayed_packet_errors` — remain excluded per `remove_cumulative_rtpengine_features.md`. These are lifetime averages or non-loss counters whose rate form would either be meaningless (an average-of-an-average is noise) or redundant with the new ratio.

### Why rates are immune to the pollution the original ADR called out

The pollution argument was: absolute values persist across chaos runs. A cumulative counter sitting at `packets_lost = 1,000,000` from prior faults looks alarming to the model, forever, regardless of what's happening right now.

Rates evade this. The preprocessor's 30-second ring buffer only retains the last ~6 samples. The rate is `(current - oldest_in_buffer) / window_dt`. If the counter has been stationary for 30 seconds, the rate is 0 — regardless of how large the absolute value is. Stale accumulation from a fault last week is invisible to a rate sampled this minute.

Concretely, with `packets_lost = 1,000,000` as the starting value:

- **Healthy window:** all 6 samples show `1,000,000`. Rate = `0/30 = 0`. Ratio = `0/(0 + relayed_rate) = 0`. Clean.
- **Loss injection window:** delta of 30,000 over the 30 s window. Rate = 1000/s. If `total_relayed_packets_rate` ≈ 2000/s over the same window, ratio ≈ `1000/(1000+2000) = 0.33`. Anomalous.

The large pre-existing absolute value plays no role in either computation. The window is bounded; what happened before it is gone.

### Accompanying changes (for cross-reference; not ADR decisions themselves)

- New KB entry `ims.rtpengine.loss_ratio` in `metrics.yaml` with one event trigger (`sustained_gt(0.05, min_duration='15s')`, clear on `sustained_lt(0.01, min_duration='30s')`), emitting `ims.rtpengine.packet_loss_sustained`.
- New causal chain `rtpengine_media_degradation` in `causal_chains.yaml` with one positive branch (`vonr_rtp_loss`) and three negative branches (`sip_signaling_unaffected`, `n3_user_plane_unaffected`, `hss_cx_unaffected`) authored to suppress the "blame HSS / PCF / UPF" hallucinations seen in the motivating episodes.
- Anomaly model retrained with the new feature (24 features total, up from 23).

## Consequences

### Positive

- **Observable fault mode now has a signal path.** Network-layer packet loss at the rtpengine container produces a non-zero feature that the trained model flags and an event trigger fires on.
- **Zero schema pollution.** No cumulative absolute value is surfaced to the model; the ADR `remove_cumulative_rtpengine_features.md` remains honored.
- **Precedent for similar cases.** The next time a cumulative counter is the only semantically-correct source for a diagnostic signal, this ADR documents the pattern: take the rate, not the value.

### Risk

- **Counter reset behavior.** If rtpengine restarts, both `packets_lost` and `total_relayed_packets` reset to 0. The preprocessor's `max(0.0, current - oldest)` clamp prevents negative deltas — restarts will simply produce `rate = 0` for the window spanning the restart, not a huge spike. Verified in the preprocessor code (`preprocessor.py:320`).
- **Numerator-denominator correlation.** During a fault on the rtpengine-upstream path (e.g., UPF-side loss), BOTH `packets_lost_rate` and a reduction in `total_relayed_packets_rate` could move, compressing the signal. The causal chain's correlation hints (`correlates_with` on `core.upf.gtp_*_per_ue_drop`) address this interpretively; the feature still fires, just with attribution requiring the combined reading.
- **Schema forward-compatibility.** The preprocessor's `_COUNTER_PATTERNS` now contains two entries (`packets_lost`, `total_relayed_packets`) that are *only* used internally for derived features. A future maintainer who assumes everything in `_COUNTER_PATTERNS` is emitted as a feature would misread. Mitigated by an inline comment pointing at this ADR.

### Alternatives considered

1. **Re-admit `average_packet_loss` with a stricter window.** Rejected — it's an average of averages (RTCP reports averaged over sessions averaged over time); no windowing trick reconstructs a current-loss signal from it.
2. **Compute a packets-lost-per-second feature without normalizing by total relayed.** Rejected — the raw loss rate is not scale-independent. Different call volumes produce different "healthy" magnitudes. A ratio is, by construction, scale-independent.
3. **Expose MOS via `get_dp_quality_gauges` only and not as a feature.** Adopted for MOS. MOS cumulative average moves too slowly to serve as a trigger signal. The Investigator can still read it via `get_dp_quality_gauges` for attribution during probe execution.
4. **Infer loss ratio from per-call RTCP reports rather than aggregate counters.** Rejected — rtpengine does not expose per-call RTCP loss in a form the collector can pull cheaply; the aggregate counter's rate is the cheapest usable signal.

## Validation

- Preprocessor smoke test: feature emits 0.00 healthy, 0.30 under 30% loss injection, 0.00 silent (no RTP).
- Event trigger: fires under sustained 30% loss ✓, does not fire healthy ✓, does not fire on a single transient spike that lasts < 15 s ✓.
- Trained model feature set includes `derived.rtpengine_loss_ratio` (verified in `training_meta.json` after 2026-04-24 retrain; 102 samples, 24 features).
- Reverse lookup: `find_chains_by_observable_metric("rtpengine_loss_ratio")` surfaces the `rtpengine_media_degradation.vonr_rtp_loss` branch.
- Regression suite: 138/138 passing.

## Follow-on

- After the next batch run, compare the `call_quality_degradation` score against the prior 15%. If this ADR's decision is correct, the event fires, NA anchors on the new branch, and the score lifts significantly. The retro should cite this ADR.
- If a future rtpengine counter is added to the rtpengine stats output, default to excluding it from the feature vector. Re-admit only via this ADR's pattern (rate of cumulative, never absolute) and only if the observable it gives is not already covered by `rtpengine_loss_ratio` or `errors_per_second`.
