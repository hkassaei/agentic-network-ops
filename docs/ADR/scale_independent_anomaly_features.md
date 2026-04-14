# ADR: Scale-Independent Anomaly Feature Engineering

**Date:** 2026-04-13
**Status:** Accepted
**Related episodes:**
- [`docs/critical-observations/run_20260409_231143_data_plane_degradation.md`](../critical-observations/run_20260409_231143_data_plane_degradation.md) — first data plane degradation (0%, anomaly screener blind to UPF, all flags were IMS signaling noise)
- [`agentic_ops_v5/docs/agent_logs/run_20260413_032529_data_plane_degradation.md`](../../agentic_ops_v5/docs/agent_logs/run_20260413_032529_data_plane_degradation.md) — third run (50%, screener flagged RTPEngine but IMS noise still dominated)
- [`agentic_ops_v5/docs/agent_logs/run_20260413_201118_data_plane_degradation.md`](../../agentic_ops_v5/docs/agent_logs/run_20260413_201118_data_plane_degradation.md) — fourth run (10%, SMF metrics crashed to 0 but agent said "normal idle state")
- [`agentic_ops_v5/docs/agent_logs/run_20260413_205532_call_quality_degradation.md`](../../agentic_ops_v5/docs/agent_logs/run_20260413_205532_call_quality_degradation.md) — first call quality degradation (35%, agent misdiagnosed as UPF failure despite fault being on RTPEngine)
- Related ADRs: [`convergence_point_reasoning.md`](convergence_point_reasoning.md), [`anomaly_detection_layer.md`](anomaly_detection_layer.md)

---

## Decision

Complete rewrite of the anomaly detection feature engineering to produce **scale-independent features** that are invariant to UE count, traffic volume, and observation timing. Three major changes:

1. **Rewrote `MetricPreprocessor`** with five feature categories: quality gauges, error ratios, per-UE normalized rates, health indicators, and derived composite features.
2. **Fixed a critical rate inflation bug** where replaying stored snapshots produced rates 1000x too high.
3. **Added tc rule cleanup to `BaselineCollector`** to prevent residual fault state from polluting subsequent runs.

---

## Context

### Problem 1: Rate inflation bug (every v5 episode was corrupted)

The anomaly screener processes stored metric snapshots from the `ObservationTrafficAgent` to compute anomaly scores. The `MetricPreprocessor` computes counter rates as `delta / dt`, where `dt` was derived from `time.time()`.

**The bug:** During training, the preprocessor runs in real-time (one snapshot every ~6 seconds, `dt` ≈ 6s). During scoring in the orchestrator, it replays 20-50 stored snapshots in a tight Python loop. Each loop iteration takes ~5ms, so `dt` ≈ 0.005s instead of the original 5s collection interval. This inflated all counter-derived rates by ~1000x.

**Example from a real episode:**
- `pcscf.core:rcv_requests_register` counter delta: 8 over 120 seconds
- Expected rate: 8/120 = 0.067/s
- Actual rate computed by screener: 8/0.005 = 1600/s
- Screener flagged: `pcscf.core:rcv_requests_register_rate = 1502.53` (vs learned normal 0.11) → HIGH

Every IMS signaling metric in every v5 episode was inflated by this factor, causing the anomaly screener to flag normal traffic as catastrophic anomalies. The RTPEngine quality metrics (which are gauges, not rate-computed) were the only correct signals, but they were drowned by 8-10 inflated IMS flags ranked above them.

**Fix:** Snapshots now carry `_timestamp` from when they were collected. The preprocessor accepts an optional `timestamp` parameter and uses it instead of `time.time()` when replaying stored snapshots.

### Problem 2: Traffic-dependent features can't generalize across UE counts

The original feature set included raw counter-derived rates like `pcscf.core:rcv_requests_register_rate`. These scale linearly with UE count — 4 UEs produce 2x the register rate of 2 UEs. A model trained with 2 UEs would flag 4 UEs as anomalous, and vice versa. This makes the model useless in production where UE count constantly changes.

Even with the same UE count, the training traffic generator produces bursty patterns (mostly idle, occasional bursts), while the observation traffic generator produces more sustained patterns. The model learned `register_rate ≈ 0.1` during training but saw `register_rate ≈ 0.7` during observation — a 7x deviation flagged as MEDIUM even though both represent healthy traffic.

### Problem 3: Residual tc rules from previous runs

Every container in the stack had residual tc netem rules from previous chaos runs that weren't properly cleaned up by the healer. This meant the "baseline" captured at the start of each scenario was already polluted, and `measure_rtt` showed packet loss on paths that should have been clean.

---

## Design

### Feature categories (45 total features)

The preprocessor produces features in five categories, all designed to be independent of UE count and traffic volume:

#### Category 1: Quality gauges (17 features)

Metrics that are inherently scale-independent — their values don't change with UE count.

| Feature | Healthy Value | What Triggers It |
|---|---|---|
| `rtpengine.average_mos` | ~4.0 | Packet loss → MOS drops |
| `rtpengine.average_packet_loss` | 0 | Network loss on media path |
| `rtpengine.packet_loss_standard_deviation` | 0 | Bursty packet loss |
| `rtpengine.average_jitter_(reported)` | 0 | Network jitter |
| `rtpengine.packets_lost` | 0 | Cumulative RTP loss |
| `rtpengine.total_number_of_1_way_streams` | 0 | Severe one-direction loss |
| `rtpengine.errors_per_second_(total)` | 0 | Active relay errors |
| `rtpengine.total_relayed_packet_errors` | 0 | Cumulative relay errors |
| `icscf.cdp:average_response_time` | ~50ms | HSS latency |
| `icscf.ims_icscf:uar_avg_response_time` | ~50ms | HSS UAR latency |
| `icscf.ims_icscf:lir_avg_response_time` | ~50ms | HSS LIR latency |
| `scscf.ims_auth:mar_avg_response_time` | ~100ms | HSS MAR latency |
| `scscf.ims_registrar_scscf:sar_avg_response_time` | ~100ms | HSS SAR latency |
| `icscf.cdp:timeout` | 0 | Diameter timeouts (absolute) |
| `icscf.ims_icscf:uar_timeouts` | 0 | UAR timeouts (absolute) |
| `icscf.ims_icscf:lir_timeouts` | 0 | LIR timeouts (absolute) |
| `scscf.ims_auth:mar_timeouts` | 0 | MAR timeouts (absolute) |

These are the strongest anomaly signals because they have near-zero variance during healthy operation and spike clearly during faults.

#### Category 2: Error ratios (10 features)

Derived from counter pairs as `failures / (failures + successes)`. Always in [0, 1]. Independent of both UE count and traffic volume.

| Feature | Formula | Healthy | What Triggers It |
|---|---|---|---|
| `derived.icscf_uar_timeout_ratio` | uar_timeouts / (timeouts + replies) | 0 | HSS unresponsive |
| `derived.icscf_lir_timeout_ratio` | lir_timeouts / (timeouts + replies) | 0 | HSS unresponsive |
| `derived.scscf_mar_timeout_ratio` | mar_timeouts / (timeouts + replies) | 0 | HSS auth failure |
| `derived.scscf_sar_timeout_ratio` | sar_timeouts / (timeouts + replies) | 0 | HSS assignment failure |
| `derived.scscf_registration_reject_ratio` | rejected / (rejected + accepted) | 0 | Auth/credential issues |
| `derived.pcscf_httpclient_failure_ratio` | connfail / (connfail + connok) | ~0 | PCF/SCP unreachable |
| `derived.pcscf_sip_error_ratio` | (4xx+5xx) / total_replies | 0 | SIP processing errors |
| `derived.icscf_sip_error_ratio` | (4xx+5xx) / total_replies | 0 | SIP processing errors |
| `derived.scscf_sip_error_ratio` | (4xx+5xx) / total_replies | 0 | SIP processing errors |
| `derived.upf_activity_during_calls` | upf_rate / expected_rate | 1.0 | UPF not forwarding during active call |

These are the second-strongest signals. `uar_timeout_ratio` going from 0 to 0.5 means "half of all Diameter requests are timing out" — an unambiguous fault signal regardless of scale.

#### Category 3: Per-UE normalized rates (14 features)

Counter-derived rates divided by the current UE count. Measures "how much traffic is each UE generating."

| Feature | Normalizer | Meaning |
|---|---|---|
| `normalized.{cscf}.core:rcv_requests_register_per_ue` | `registered_contacts` | SIP REGISTER rate per IMS user |
| `normalized.{cscf}.core:rcv_requests_invite_per_ue` | `registered_contacts` | Call rate per IMS user |
| `normalized.{cscf}.cdp_replies_per_ue` | `registered_contacts` | Diameter activity per IMS user |
| `normalized.upf.gtp_{in,out}datapktn3upf_per_ue` | `ran_ue` | GTP-U throughput per attached UE |
| `normalized.rtpengine.pps_per_session` | `owned_sessions` | RTP packets per active media session |
| `normalized.pcscf.dialogs_per_ue` | `registered_contacts` | Active calls per IMS user |
| `normalized.smf.sessions_per_ue` | `ran_ue` | PDU sessions per attached UE |
| `normalized.smf.bearers_per_ue` | `ran_ue` | QoS bearers per attached UE |

These features are stable across different UE populations. A healthy network produces ~0.3 registers/s/UE regardless of whether there are 2 or 200 UEs.

When UE count is 0 (no UEs registered), per-UE features are set to 0.0 rather than omitted, ensuring a consistent feature set size across all snapshots. The model always sees 45 features regardless of UE count.

#### Category 4: Health indicators (4 features)

Absolute counts that provide context for interpreting other features. Not normalized — they tell the model "how many UEs are in the system."

| Feature | Meaning |
|---|---|
| `health.ran_ue` | Number of 5G-attached UEs |
| `health.gnb` | Number of connected gNBs |
| `health.upf_sessions` | Active PFCP sessions on UPF |
| `health.ims_registered` | IMS-registered contacts |

These help the model understand context. A drop from 2 to 0 in `health.ran_ue` is a gNB crash. A drop from 4 to 0 in `health.upf_sessions` is an SMF crash.

#### Category 5: Derived composites (included in error ratios)

`derived.upf_activity_during_calls` — ratio of actual UPF throughput to expected throughput given the number of active calls. 1.0 when healthy (idle or flowing), drops to 0.0 when calls are active but UPF isn't forwarding.

### Metrics collected but NOT used as features

The preprocessor collects more metrics than it feeds to the model. Some metrics are only inputs to derived features:

- `httpclient:connfail` + `httpclient:connok` → used to compute `pcscf_httpclient_failure_ratio` but not exposed as raw rates
- `ims_icscf:uar_replies_received` → used to compute `icscf_uar_timeout_ratio` denominator
- `ims_auth:mar_replies_received` → used to compute `scscf_mar_timeout_ratio` denominator
- `sl:1xx_replies`, `sl:200_replies`, `sl:4xx_replies`, `sl:5xx_replies` → used to compute SIP error ratios

This separation ensures the model sees clean, interpretable features while the preprocessor has access to the raw counters needed for derivation.

---

## Sliding Window Rate Smoothing

### The sparsity problem

The original preprocessor computed instantaneous point-to-point rates: `rate = (counter_now - counter_prev) / dt`. With 5-second collection intervals and bursty traffic (sub-second SIP transactions separated by multi-second idle gaps or 30-second calls), most snapshots caught idle moments. In training data, only 12 out of 50 snapshots had non-zero register rates — despite the traffic generator being active 80% of the time.

The traffic generator weights are `[20, 15, 45, 20]` for `[register_both, register_one, call, idle]`. But a single VoNR call consumes 13-68 seconds of elapsed time (setup + hold + teardown), during which no register activity occurs. A SIP REGISTER transaction completes in <1 second. The 5-second snapshot interval has low probability of capturing the brief register burst, and high probability of landing during a long call hold.

This produces features like `[0, 0, 0, 0.35, 0, 0, 0, 0, 0.35, 0, ...]` — sparse, mostly zero, with high variance. The model learns "register rate is usually 0" and flags any non-zero rate as anomalous, even during normal traffic.

### The fix: sliding window rates

Instead of instantaneous point-to-point deltas, the preprocessor now maintains a ring buffer of the last 6 counter snapshots and computes rates over the full window:

```
rate = (counter_now - counter_6_samples_ago) / (window_duration)
```

With 5-second collection intervals and a window of 6 samples, the effective window is ~30 seconds. A register event that happened anywhere in the last 30 seconds produces a non-zero rate in every snapshot for the duration of the window. The rate is smaller (spread over 30s) but consistently non-zero.

**Before (instantaneous):** `[0, 0, 0, 0.35, 0, 0, 0, 0, 0.35, 0, ...]` — 12/50 non-zero (24%)

**After (30s window):** `[0.06, 0.06, 0.06, 0.06, 0.06, 0.06, 0.12, 0.12, 0.12, 0.12, ...]` — smooth, mostly non-zero

The model learns "the network sustains ~0.1 registers/s/UE when traffic is flowing" rather than "registers come in 0.35 spikes separated by zeros."

### Implementation

The `MetricPreprocessor` maintains a `_history` ring buffer of `(timestamp, {fkey: counter_value})` tuples. Each call to `process()` appends the current snapshot. The rate for each counter is computed as:

```python
oldest_time, oldest_counters = self._history[0]
window_dt = now - oldest_time
rate = (current_value - oldest_value) / window_dt
```

The buffer is capped at `_RATE_WINDOW_SAMPLES + 1 = 7` entries (6 intervals). The orchestrator's scoring warmup threshold was updated from 2 to 6 to allow the window to fill before scoring begins.

### Consistency with training

The anomaly trainer also uses `MetricPreprocessor` in real-time — the same sliding window applies during training. Both training and scoring see the same smoothed rates, eliminating the training/testing mismatch.

---

## Rate Inflation Bug Fix

### Root cause

`MetricPreprocessor.process()` used `time.time()` as the timestamp for rate computation. During training (real-time), `dt` between calls is ~6 seconds. During scoring (replaying stored snapshots in a loop), `dt` is ~5 milliseconds. Rates are `delta / dt`, so the same counter delta produces rates 1000x higher during scoring.

### Fix (3 files)

- **`agentic_chaos/agents/observation_traffic.py`** — each snapshot now carries `_timestamp` from `time.time()` at collection
- **`agentic_ops_v5/anomaly/preprocessor.py`** — `process()` accepts optional `timestamp` parameter; uses it instead of `time.time()` when provided
- **`agentic_ops_v5/orchestrator.py`** — extracts `_timestamp` from stored snapshots and passes it to the preprocessor during replay

### Impact

Every v5 episode's Phase 0 (anomaly screening) output was corrupted by inflated rates. The IMS signaling "anomalies" that dominated every episode report were artifacts of this bug, not real anomalies. The RTPEngine quality metrics (gauges, not rate-computed) were the only correct signals but were consistently outranked by 8-10 inflated IMS flags.

---

## Baseline TC Cleanup Fix

### Root cause

The `Healer` agent is supposed to clear tc netem rules after each scenario. But it only clears rules for faults registered in the `FaultRegistry`. If a scenario is interrupted, or the healer misses a container, residual tc rules persist across runs.

We discovered that **every container in the stack** had residual tc rules from previous data plane degradation runs. This meant the baseline was polluted, `measure_rtt` showed false packet loss, and the agent found genuine (but old) problems instead of the injected fault.

### Fix

`BaselineCollector` now runs `clear_tc_rules()` on all 12 containers before capturing the baseline snapshot. This ensures a pristine network state regardless of what happened in previous runs.

---

## Network Analyst Prompt Updates

### Fault Localization via measure_rtt

Replaced the rigid "UPF is always the convergence point cause" section with a `measure_rtt`-based fault localization protocol:

- Run `measure_rtt` TO the suspected component from multiple neighbors
- If multiple sources show loss TO the same target → fault is at the target's own interface
- If only one source shows loss → fault is on that source's interface or the specific path

This prevents the agent from assuming UPF when the fault is actually at RTPEngine.

### Multi-Subsystem Anomaly Analysis

When anomalies span multiple subsystems, the agent must now consider two possibilities:
1. Shared upstream dependency (UPF convergence point) — verify with `measure_rtt` to UPF
2. Direct fault on one component with cascading effects — verify with `measure_rtt` from multiple sources to the symptomatic component

The agent must use RTT evidence to distinguish, not assume either case.

---

## Files Changed

**Complete rewrite:**
- `agentic_ops_v5/anomaly/preprocessor.py` — 45 scale-independent features in 5 categories, per-UE normalization, error ratio derivation, sliding window rate smoothing, format-agnostic snapshot handling, consistent feature set size

**Bug fixes:**
- `agentic_chaos/agents/observation_traffic.py` — snapshots carry `_timestamp`
- `agentic_ops_v5/orchestrator.py` — passes `_timestamp` to preprocessor during replay; scoring warmup threshold updated from 2 to 6 for sliding window fill
- `agentic_chaos/agents/baseline.py` — clears tc rules on all containers before baseline capture

**Prompt updates:**
- `agentic_ops_v5/prompts/network_analyst.md` — fault localization via measure_rtt, multi-subsystem analysis

**Ontology updates:**
- `network_ontology/data/causal_chains.yaml` — UPF convergence point now includes `how_to_localize` guidance

**New scenario:**
- `agentic_chaos/scenarios/library.py` — added "Call Quality Degradation" (30% loss on RTPEngine)
- `agentic_chaos/recorder.py` — `ims_media` failure domain, `RTP` protocol impact for RTPEngine faults

---

## Verification

After retraining the anomaly model (`python -m anomaly_trainer --duration 600`):

1. **Feature sanity check:** All per-UE normalized rates should be stable between training (2 UEs) and testing (2 UEs). If tested with more UEs, the per-UE rates should remain similar.
2. **No IMS signaling noise:** The anomaly screener should NOT flag `core:rcv_requests_register_rate` or `cdp:replies_received_rate` as anomalies during normal observation traffic. These raw rates are no longer in the feature set — only per-UE normalized versions exist.
3. **RTPEngine detection:** For the Call Quality Degradation scenario, `rtpengine.average_packet_loss` and `rtpengine.packet_loss_standard_deviation` should be the TOP anomaly flags (not buried under IMS noise).
4. **Error ratios work:** For HSS Unresponsive scenario, `derived.icscf_uar_timeout_ratio` should spike from 0 to >0.5 and be flagged as HIGH.
5. **Rate inflation fixed:** Verify that the maximum rate in any anomaly flag is in the same order of magnitude as the learned normal (not 1000x higher).
6. **Sliding window smoothing:** During training, verify that >80% of per-UE rate samples are non-zero (vs the previous 24% with instantaneous rates). Check the training metadata for feature statistics.
7. **Consistent feature count:** Every snapshot should produce exactly 45 features, regardless of whether UEs are registered or calls are active.
