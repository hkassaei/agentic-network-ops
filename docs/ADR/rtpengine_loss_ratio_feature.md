# ADR: Rate-Based RTPEngine Loss Ratio Feature

**Date:** 2026-04-24 (revised 2026-04-27 — sensor source corrected)
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

| Feature | Formula | Type | Healthy | Under loss |
|---|---|---|---|---|
| `derived.rtpengine_loss_ratio` | `rate(rtpengine_packetloss_total) / rate(rtpengine_packetloss_samples_total)` | `derived` (per-RR avg) | 0 | rises from 0 to tens|

This is the same quantity rtpengine-ctl labels `Average packet loss`: the per-RR mean of the lost-packet counts that arrive in RTCP Receiver Reports. NOT a fraction of all packets. Empirically verified on 2026-04-27 under a real VoNR call with 30% tc-injected egress loss: value rose from 0 to ~4 at 5s into injection and continued growing past 30 by 30s. The growth happens because each RTCP Receiver Report carries a cumulative-since-call-start lost-packet count; summing across RRs and dividing by sample count gives a number that scales with both loss intensity AND call age.

For anomaly detection this is exactly what we need — the healthy/lossy distinction is dramatic (0 vs tens) and the threshold (`sustained_gt(0.5)`) sits comfortably below any non-trivial loss case. For interpretation, "value 5 at one minute and 30% loss" vs "value 50 at five minutes and 10% loss" CAN both fire equivalently — the metric isn't a clean linear function of loss-percentage alone. Distinguishing loss severity precisely would require an additional sensor; this one's job is reliable detection of "loss is happening on this call's media path."

Where `_rate` is the `preprocessor.py` sliding-window rate (≈30 s, 6 samples).

### Sensor-source correction (2026-04-27)

The original wiring of this feature read `rtpengine.packets_lost` and `rtpengine.total_relayed_packets` from `rtpengine-ctl list totals` output. Empirical testing on 2026-04-27 showed those counters do **not** advance under the chaos framework's tc-egress-loss injection — even with active RTP flowing through the relay. Direct measurement during a real VoNR call with 30% tc loss:

| Counter | Source | Delta over 33 s | Notes |
|---|---|---|---|
| `Total relayed packets` | rtpengine-ctl | +173 | normal call traffic |
| `Packets lost` | rtpengine-ctl | **+0** | did not respond to fault |
| `rtpengine_packetloss_total` | Prometheus | **+304** | responds correctly |
| qdisc internal `dropped` | `tc -s qdisc show` | +85 | ground truth |

The two counter names look interchangeable but they're not. `Packets lost` from `list totals` is populated under specific RTCP-handling code paths that don't fire on this fault mode in our deployment. `rtpengine_packetloss_total` accumulates `packets_lost` values from every RTCP Receiver Report that arrives — and in our setup the receivers' RRs do come through and rtpengine does process them.

The fix was a sensor-source swap: pull the two Prometheus counters via the metrics collector and use them as the rate inputs. The feature name, the event trigger, the causal chain, and `EXPECTED_FEATURE_KEYS` all stay; only the data path underneath changed.

### What the model does NOT see

- `rtpengine.prom_packetloss_total` (absolute value) — never emitted as a feature; only its rate feeds into the ratio above.
- `rtpengine.prom_packetloss_samples_total` (absolute value) — same: never emitted as a feature.
- `rtpengine.packets_lost` and `rtpengine.total_relayed_packets` from rtpengine-ctl — **dropped entirely** from `_COLLECT_METRICS` after the 2026-04-27 sensor-source correction. They were the wrong counters for this fault mode and their continued presence would only add noise.
- `rtpengine.average_packet_loss`, `rtpengine.average_mos`, `rtpengine.packet_loss_standard_deviation`, `rtpengine.total_number_of_1_way_streams`, `rtpengine.total_relayed_packet_errors` — remain excluded per `remove_cumulative_rtpengine_features.md`. These are lifetime averages or non-loss counters whose rate form would either be meaningless (an average-of-an-average is noise) or redundant with the new ratio.

### Why rates are immune to the pollution the original ADR called out

The pollution argument was: absolute values persist across chaos runs. A cumulative counter sitting at `prom_packetloss_total = 1,000,000` from prior faults looks alarming to the model, forever, regardless of what's happening right now.

Rates evade this. The preprocessor's 30-second ring buffer only retains the last ~6 samples. The rate is `(current - oldest_in_buffer) / window_dt`. If the counter has been stationary for 30 seconds, the rate is 0 — regardless of how large the absolute value is. Stale accumulation from a fault last week is invisible to a rate sampled this minute.

Concretely, with `prom_packetloss_total = 1,000,000` as the starting value:

- **Healthy window (idle stack or healthy calls):** RRs that arrive carry `packets_lost = 0`, so the cumulative counter doesn't advance. Rate = `0`. Samples-rate is whatever (e.g. 0.3 RR/s during a healthy call). Ratio = `0 / 0.3 = 0`. Clean.
- **Loss injection window:** delta of 300 over the 30 s window. Rate = 10/s. Samples-rate ≈ 0.3 RR/s. Ratio ≈ `10 / 0.3 ≈ 33` per RR — at the high end of what 30% loss produces (the precise scaling depends on how many streams are in each RR; in our test we observed ~5).

The large pre-existing absolute value plays no role in either computation. The window is bounded; what happened before it is gone.

### Accompanying changes (for cross-reference; not ADR decisions themselves)

- New KB entry `ims.rtpengine.loss_ratio` in `metrics.yaml` with one event trigger (`sustained_gt(0.5, min_duration='15s')`, clear on `sustained_lt(0.1, min_duration='30s')`), emitting `ims.rtpengine.packet_loss_sustained`. The threshold sits well below the empirical 10%-loss value (~1.7) and well above noise (a single transient 1-packet RR averages to <0.5 over the window), so 10% and 30% scenarios both fire reliably and remain distinguishable in the model's anomaly attribution.
- New causal chain `rtpengine_media_degradation` in `causal_chains.yaml` with one positive branch (`vonr_rtp_loss`) and three negative branches (`sip_signaling_unaffected`, `n3_user_plane_unaffected`, `hss_cx_unaffected`) authored to suppress the "blame HSS / PCF / UPF" hallucinations seen in the motivating episodes.
- `gui/metrics.py::_collect_rtpengine` augmented with a Prometheus pull (`_collect_rtpengine_prom`) that fetches `rtpengine_packetloss_total` and `rtpengine_packetloss_samples_total` and merges them into the rtpengine metric dict. The existing rtpengine-ctl path stays for the rest of the per-call summary metrics; only the loss-counter source changed.
- Anomaly model trained with the new feature (30 features total, including the 6 temporal Cx response-time features now correctly reported per the `_feature_keys` property fix). No retrain required to switch the sensor source: `derived.rtpengine_loss_ratio` continues to be 0 during healthy traffic regardless of which underlying counter populates it, so the trained baseline stays correct.

## Consequences

### Positive

- **Observable fault mode now has a signal path.** Network-layer packet loss at the rtpengine container produces a non-zero feature that the trained model flags and an event trigger fires on.
- **Zero schema pollution.** No cumulative absolute value is surfaced to the model; the ADR `remove_cumulative_rtpengine_features.md` remains honored.
- **Precedent for similar cases.** The next time a cumulative counter is the only semantically-correct source for a diagnostic signal, this ADR documents the pattern: take the rate, not the value.

### Risk

- **Counter reset behavior.** If rtpengine restarts, both `prom_packetloss_total` and `prom_packetloss_samples_total` reset to 0. The preprocessor's `max(0.0, current - oldest)` clamp prevents negative deltas — restarts will simply produce `rate = 0` for the window spanning the restart, not a huge spike. Verified in the preprocessor code (`preprocessor.py:320`).
- **No active calls means feature is 0.** When no calls are active, no RTCP RRs are processed — both rates are 0 and `_safe_ratio(0, 0) = 0`. This is correct behavior (no media to report on means no loss to report) but means the feature is silent during quiet periods. Detection still requires that some media flow exist, which is the same precondition any RTCP-based metric has.
- **Schema forward-compatibility.** The preprocessor's `_COUNTER_PATTERNS` now contains two entries (`prom_packetloss_total`, `prom_packetloss_samples_total`) that are *only* used internally for derived features. A future maintainer who assumes everything in `_COUNTER_PATTERNS` is emitted as a feature would misread. Mitigated by an inline comment pointing at this ADR.

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
