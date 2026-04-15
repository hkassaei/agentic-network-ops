# ADR: Anomaly Detection Model v2 — Iterative Improvements

**Date:** 2026-04-14
**Status:** Accepted
**Supersedes:** [`scale_independent_anomaly_features.md`](scale_independent_anomaly_features.md) — this ADR incorporates all changes from the initial rewrite plus subsequent iterative improvements. `scale_independent_anomaly_features.md` is now historical context only.
**Related ADRs:**
- [`convergence_point_reasoning.md`](convergence_point_reasoning.md) — Network Analyst prompt improvements
- [`auto_heal_broken_stack.md`](auto_heal_broken_stack.md) — stack health recovery between runs

---

## Context

The initial anomaly feature engineering rewrite ([`scale_independent_anomaly_features.md`](scale_independent_anomaly_features.md)) solved the 1000x rate inflation bug and introduced scale-independent features. However, subsequent testing revealed additional issues that required iterative improvements across four areas: feature quality, rate smoothing, noise removal, and metric correctness.

This ADR documents all improvements made after the initial rewrite, capturing the full journey from a model that scored 0-10% on every scenario to one that reliably detects faults.

---

## Improvement 1: Sliding Window Rate Smoothing

### Problem

Counter-derived rates were computed as instantaneous point-to-point deltas: `rate = (counter_now - counter_prev) / dt`. With 5-second collection intervals and bursty traffic (sub-second SIP transactions separated by multi-second call holds or idle gaps), most snapshots caught idle moments. In training data, only 12/50 snapshots (24%) had non-zero register rates — despite the traffic generator being active 80% of the time.

The root cause: a SIP REGISTER transaction completes in <1 second, but a VoNR call holds for 5-30 seconds. The 5-second snapshot interval has low probability of catching the brief register burst and high probability of landing during a long call hold.

### Fix

Replaced instantaneous deltas with a **sliding window** of the last 6 counter snapshots (~30 seconds at 5-second intervals). Rates are computed as:

```
rate = (counter_now - counter_6_samples_ago) / window_duration
```

A register event that happened anywhere in the last 30 seconds produces a non-zero rate in every snapshot for the duration of the window.

**Before:** `[0, 0, 0, 0.35, 0, 0, 0, 0, 0.35, 0]` — 24% non-zero
**After:** `[0.06, 0.06, 0.06, 0.06, 0.12, 0.12, 0.12, 0.12, 0.06, 0.06]` — mostly non-zero

Implementation: `MetricPreprocessor` maintains a `_history` ring buffer of `(timestamp, {fkey: counter_value})` tuples, capped at 7 entries. The orchestrator's scoring warmup threshold was updated from 2 to 6 to allow the window to fill before scoring begins.

### Result

Per-UE register rate non-zero samples improved from 37% to 73% in training data.

### File changed

- `agentic_ops_v5/anomaly/preprocessor.py` — ring buffer, sliding window rate computation

---

## Improvement 2: Removed Noisy and Useless Features

### Features removed

**`derived.pcscf_httpclient_failure_ratio`** — Baseline failure rate was 84% (103/104 samples non-zero). The P-CSCF's HTTP client to the PCF over the Rx interface has a chronic failure rate due to SCP timeouts on Rx AAR requests. This is a deployment-specific quirk, not a fault signal. IMS registration and calls work without dedicated QoS bearers. With 84% as "normal," the model can't distinguish healthy from degraded.

**`normalized.rtpengine.pps_per_session`** — Always 0 in every training sample (0/104). The `packets_per_second_(total)` gauge is a point-in-time value that resets to 0 between RTPEngine control snapshots faster than the collection interval. Provides no signal.

**`health.ran_ue`, `health.gnb`, `health.upf_sessions`, `health.ims_registered`** — Absolute UE/gNB/session counts baked into the model. A production network has varying UE counts — training with 2 UEs and testing with 4 would flag the increased count as anomalous. These values are used internally for per-UE normalization but are not fed to the anomaly model.

**`normalized.smf.sessions_per_ue`** — Always exactly 2.0 with zero variance (each UE always has exactly 2 PDU sessions). Zero variance means the HalfSpaceTrees model can't build any useful splits on it. Harmless but dead weight.

### Result

Feature count reduced from 44 to 38. All remaining features carry real signal with meaningful variance during healthy operation.

### File changed

- `agentic_ops_v5/anomaly/preprocessor.py` — removed features, added explanatory comments for each exclusion

---

## Improvement 3: Fixed `script:register_time` (Cumulative Counter Treated as Gauge)

### Problem

`script:register_time` was treated as a point-in-time gauge showing "how long the last registration took." In reality, it's a **cumulative counter** — total milliseconds spent on all registrations since the Kamailio container started. The raw value (e.g., 43695 → 86798) grows monotonically with every registration and is meaningless as a health indicator.

The anomaly model learned "43695 is normal" during training, but after more registrations the value would be 87000, flagged as anomalous — not because anything is wrong, but because more registrations happened.

### Discovery

We measured a single registration precisely:
- Before: `script:register_time = 87136`, `script:register_success = 10`
- After one register: `script:register_time = 87500`, `script:register_success = 11`
- Delta: 364ms for one registration — a reasonable value

The accumulated average (87136ms / 10 = 8714ms) was misleading because early registrations during stack bring-up took much longer.

### Fix

1. Added `script:register_time` and `script:register_success` to the counter set (both are cumulative)
2. Removed `pcscf.script:register_time` from the passthrough gauge list
3. Added a derived feature: `derived.pcscf_avg_register_time_ms = delta(register_time) / delta(register_success)`

This gives the actual milliseconds per registration (~300ms healthy, ~4000ms+ under P-CSCF latency fault).

### Result

Training baseline: mean 131ms, range 0-467ms. During a P-CSCF latency fault with 2000ms added delay, this spikes to 4000ms+ — a clear 30x deviation that the model reliably detects.

### File changed

- `agentic_ops_v5/anomaly/preprocessor.py` — counter classification, derived feature computation

---

## Improvement 4: Added RTPEngine Data Plane Quality Metrics

### Problem

The anomaly screener had no visibility into RTPEngine packet loss. The original diagnostic metric set included only averaged gauges (`average_packet_loss`, `average_mos`) which smooth out the signal. Raw packet loss counters (`sum_of_all_packet_loss_values_sampled`, `packet_loss_standard_deviation`) that showed clear 0→116 jumps during faults were excluded.

### Fix

Added 5 RTPEngine metrics to the diagnostic set:
- `packets_lost` — cumulative count of lost RTP packets
- `total_number_of_1_way_streams` — streams where one direction died
- `total_relayed_packet_errors` — packet relay failures
- `errors_per_second_(total)` — real-time error rate gauge
- `packet_loss_standard_deviation` — bursty loss indicator

### Result

All 5 metrics are 0/N in healthy training (clean zero baseline). During Call Quality Degradation (30% loss on RTPEngine), `packet_loss_standard_deviation` and `average_packet_loss` are now consistently flagged as HIGH severity anomalies — the top-ranked signals above all IMS signaling noise.

### Files changed

- `agentic_ops_v5/anomaly/preprocessor.py` — added to `_COLLECT_METRICS` and passthrough gauges
- `gui/metrics.py` — added gauge keys for GUI display
- `network_ontology/data/baselines.yaml` — added tooltip descriptions
- `gui/templates/topology.html` — added "Data Plane Health" panel to RTPEngine detail

---

## Improvement 5: UPF GTP-U Counter Fix (Infrastructure)

### Problem

UPF GTP-U packet counters (`fivegs_ep_n3_gtp_indatapktn3upf`, `fivegs_ep_n3_gtp_outdatapktn3upf`) were permanently zero despite traffic flowing through the UPF (confirmed via tcpdump).

### Root cause

Open5GS upstream disabled the counter increment code with `#if 0` in `src/upf/gtp-path.c` (Issue #2210, PR #2219) due to malloc contention at multi-Gbps rates. The project's Dockerfile has a `sed` patch that re-enables them (`#if 0` → `#if 1`), but when the `docker_open5gs` image was pulled from ghcr.io instead of built from source, the patch was missing.

### Fix

Rebuilt `docker_open5gs` from source using the project's Dockerfile (which includes the `sed` patch). Documented in README that this image must always be built from source, never pulled from ghcr.io.

### Result

UPF GTP-U counters now increment during active traffic. Training baseline: `normalized.upf.gtp_indatapktn3upf_per_ue` mean 2.58, non-zero 102/103 samples. Provides a clean signal for UPF-level traffic anomalies.

---

## Final Model Summary

**38 features across 4 categories:**

| Category | Count | Purpose | Non-zero in training |
|---|---|---|---|
| Quality gauges | 13 | MOS, packet loss, jitter, response times | Varies (0% for fault indicators, 99%+ for response times) |
| Error ratios | 9 | Diameter timeout %, SIP error %, registration reject % | 0% (clean zero baseline — any non-zero is anomalous) |
| Per-UE normalized rates | 12 | Register/invite/GTP rates divided by UE count | 50-99% (sliding window smoothing) |
| Derived composites | 4 | Avg register time, UPF activity during calls, SIP error ratios | Varies |

**Key design principles:**
1. **Scale-independent** — all features produce the same values regardless of UE count
2. **Sliding window smoothed** — counter rates use 30-second windows to eliminate sparsity
3. **No noise** — pre-existing deployment quirks (httpclient:connfail) excluded
4. **Semantically correct** — cumulative counters treated as counters (not gauges), derived features compute meaningful ratios

**Training parameters:**
- Duration: 600 seconds (10 minutes)
- Collection interval: 5 seconds
- Sliding window: 6 samples (~30 seconds)
- Scoring warmup: 6 snapshots (skip first 6 during scoring)
- Model: River HalfSpaceTrees (50 trees, height 15, window 50)
- Threshold: 0.70

---

## Files Changed (cumulative across all improvements)

- `agentic_ops_v5/anomaly/preprocessor.py` — complete rewrite: sliding window, per-UE normalization, error ratios, derived features, noise removal, counter/gauge classification fixes
- `agentic_ops_v5/orchestrator.py` — timestamp passing for replay, scoring warmup threshold
- `agentic_chaos/agents/observation_traffic.py` — snapshot timestamps
- `agentic_chaos/agents/baseline.py` — tc rule cleanup
- `gui/metrics.py` — RTPEngine gauge keys
- `gui/templates/topology.html` — Data Plane Health panel
- `network_ontology/data/baselines.yaml` — metric descriptions
- `network/base/Dockerfile` — UPF GTP counter patch (pre-existing, documented)
