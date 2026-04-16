# ADR: Remove Raw Diameter Timeout Counters from Anomaly Model

**Date:** 2026-04-15
**Status:** Accepted
**Related:**
- [`remove_cumulative_rtpengine_features.md`](remove_cumulative_rtpengine_features.md) — same class of problem (cumulative metrics carrying stale data)
- [`anomaly_model_v2_improvements.md`](anomaly_model_v2_improvements.md) — parent ADR for anomaly feature engineering

---

## Decision

Remove 4 raw Diameter timeout counters from the anomaly model's passthrough gauge list. These are monotonically incrementing counters that carry stale data from previous chaos runs. The derived error ratio features that use these counters as inputs are retained — they compute sliding-window rates that only reflect current state.

### Counters removed from the model

| Counter | Component | What it counts |
|---|---|---|
| `cdp:timeout` | I-CSCF | Total Diameter transactions that timed out (UAR + LIR combined) since Kamailio container start |
| `ims_icscf:uar_timeouts` | I-CSCF | Total User-Authorization-Request (UAR) timeouts. UAR is sent from I-CSCF to HSS during SIP REGISTER to ask "does this user exist and which S-CSCF serves them?" |
| `ims_icscf:lir_timeouts` | I-CSCF | Total Location-Info-Request (LIR) timeouts. LIR is sent from I-CSCF to HSS to ask "where is this user registered?" for routing incoming calls |
| `scscf.ims_auth:mar_timeouts` | S-CSCF | Total Multimedia-Authentication-Request (MAR) timeouts. MAR is sent from S-CSCF to HSS to request authentication vectors for the UE during SIP REGISTER |

### Derived features retained (use the same counters but as rates)

| Derived Feature | Formula | What it measures |
|---|---|---|
| `derived.icscf_uar_timeout_ratio` | `uar_timeouts_rate / (uar_timeouts_rate + uar_replies_rate)` | What percentage of UAR requests are timing out RIGHT NOW (sliding 30s window) |
| `derived.icscf_lir_timeout_ratio` | `lir_timeouts_rate / (lir_timeouts_rate + lir_replies_rate)` | What percentage of LIR requests are timing out RIGHT NOW |
| `derived.scscf_mar_timeout_ratio` | `mar_timeouts_rate / (mar_timeouts_rate + mar_replies_rate)` | What percentage of MAR requests are timing out RIGHT NOW |

These ratios are scale-independent (same value regardless of traffic volume or UE count) and time-bounded (only reflect the last 30 seconds via the sliding window). They are 0.0 during healthy operation and spike to 0.5-1.0 during an HSS failure — a clean, unambiguous signal.

---

## Context

### The problem

These 4 counters are monotonically incrementing — each timeout adds 1, and the value never decreases. They only reset when the Kamailio container restarts.

After running an HSS Unresponsive chaos scenario that causes 7 Diameter timeouts, `cdp:timeout` stays at 7 permanently. In the next scenario (e.g., P-CSCF Latency), the anomaly model sees `cdp:timeout = 7` vs the trained baseline of 0 and flags it as anomalous — even though no Diameter timeouts are currently happening. This is the same class of stale-data problem that affected the RTPEngine cumulative metrics.

### Why the raw counters were in the model originally

The raw counters were included as passthrough gauges because an absolute count of timeouts seems intuitively useful — "7 timeouts happened" sounds diagnostic. But the model can't distinguish "7 timeouts happened 2 hours ago during a different test" from "7 timeouts are happening right now." Without temporal context, the absolute number is misleading.

### Why the derived ratios are sufficient

The derived ratio features already capture everything the raw counters provide, but without the staleness:

- **During an HSS fault:** `uar_timeouts_rate` spikes (new timeouts happening), `uar_replies_rate` drops (fewer successful replies). The ratio rises from 0 to ~0.5-1.0. The model detects this as anomalous.

- **After the fault heals:** `uar_timeouts_rate` drops to 0 (no new timeouts in the 30s window), even though the raw counter stays elevated. The ratio returns to 0. The model sees this as healthy.

- **In the next scenario:** The ratio is 0 (no current timeouts). The raw counter is still 7 but the model never sees it. No false positive.

### Note on `cdp:timeout`

`cdp:timeout` is the I-CSCF's aggregate Diameter timeout counter (essentially `uar_timeouts + lir_timeouts`). It has no corresponding derived ratio because the two individual ratios (`icscf_uar_timeout_ratio` and `icscf_lir_timeout_ratio`) already cover both Diameter operations separately. There is no additional signal in the aggregate that the individual ratios don't capture.

---

## Implementation

The raw counters remain in `_COLLECT_METRICS` because they are needed as inputs to the sliding window rate computation that feeds the derived ratio features. They are only removed from the passthrough gauge list in the feature builder, so the anomaly model never sees the absolute values.

---

## Files Changed

- `agentic_ops_v5/anomaly/preprocessor.py` — removed 4 counters from the passthrough gauge list
