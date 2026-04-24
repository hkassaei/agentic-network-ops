# Anomaly Detection Model — Feature Set Reference

**Last updated:** 2026-04-24 (post-retrain, post-`_feature_keys` property fix)
**Total features (preprocessor capability):** 30
**Features present in the trained model (2026-04-24T19:03:17Z, 209 samples):** 30 (full coverage — `training_meta.json::n_features = 30`, all expected features present)
**Model:** River HalfSpaceTrees (50 trees, height 15, window 50, threshold 0.70)
**Training:** 1200 seconds (default) of randomized IMS traffic on a healthy stack, 5-second collection intervals, 30-second sliding window for rate computation. Temporal metrics are pre-filtered: response-time features are emitted only in snapshots where the underlying event counter advanced (see ADR `anomaly_training_zero_pollution.md`). The trained feature set is now reported authoritatively by `AnomalyScreener.feature_keys` (a property over `_feature_means.keys()`), not the earlier first-sample-snapshot attribute that produced spurious "gap" numbers.
**Persistence guard:** `anomaly_trainer.persistence.save_model()` refuses to persist a model whose trained feature set is missing any key declared in `MetricPreprocessor.EXPECTED_FEATURE_KEYS`. Existing on-disk model is preserved on failure.

---

## Design Principles

1. **Scale-independent** — all features produce the same values regardless of UE count (2 or 2000)
2. **No cumulative lifetime metrics** — only point-in-time gauges, sliding-window rates, and derived ratios. Cumulative counters that carry stale data from previous runs are excluded (see ADRs: `remove_cumulative_rtpengine_features.md`, `remove_cumulative_timeout_counters.md`)
3. **Sliding window smoothed** — counter-derived rates use a 30-second window (6 samples) to eliminate sparsity from bursty SIP traffic
4. **Per-UE normalized** — traffic rates divided by registered UE count so the model generalizes across different UE populations

---

## Error Ratios (8 features)

Scale-independent ratios in [0, 1]. Zero during healthy operation, spike during faults. Computed from counter pairs so the ratio is always well-defined regardless of absolute traffic volume.

| # | Feature | Formula | What it detects |
|---|---|---|---|
| 1 | `derived.icscf_uar_timeout_ratio` | uar_timeouts_rate / (uar_timeouts_rate + uar_replies_rate) | % of I-CSCF → HSS User-Authorization-Requests timing out |
| 2 | `derived.icscf_lir_timeout_ratio` | lir_timeouts_rate / (lir_timeouts_rate + lir_replies_rate) | % of I-CSCF → HSS Location-Info-Requests timing out |
| 3 | `derived.scscf_mar_timeout_ratio` | mar_timeouts_rate / (mar_timeouts_rate + mar_replies_rate) | % of S-CSCF → HSS Multimedia-Authentication-Requests timing out |
| 4 | `derived.scscf_sar_timeout_ratio` | sar_timeouts_rate / (sar_timeouts_rate + sar_replies_rate) | % of S-CSCF → HSS Server-Assignment-Requests timing out |
| 5 | `derived.scscf_registration_reject_ratio` | rejected_regs_rate / (rejected_regs_rate + accepted_regs_rate) | % of IMS registrations rejected by S-CSCF |
| 6 | `derived.pcscf_sip_error_ratio` | (4xx + 5xx) / total_replies | % of P-CSCF SIP responses that are errors |
| 7 | `derived.icscf_sip_error_ratio` | (4xx + 5xx) / total_replies | % of I-CSCF SIP responses that are errors |
| 8 | `derived.scscf_sip_error_ratio` | (4xx + 5xx) / total_replies | % of S-CSCF SIP responses that are errors |

---

## Response Times (5 features)

Point-in-time Diameter latency gauges. Tight distributions during healthy operation, spike under HSS latency or overload faults. Each feature is omitted from a snapshot when its underlying reply counter did not advance (no new requests completed in the rate window); see ADR `anomaly_training_zero_pollution.md`.

| # | Feature | Healthy Baseline | What it measures |
|---|---|---|---|
| 9 | `icscf.cdp:average_response_time` | ~51ms | Average Diameter response time at I-CSCF (across all Cx operations — weighted mix of UAR + LIR) |
| 10 | `icscf.ims_icscf:uar_avg_response_time` | ~52ms | Average UAR response time (user authorization during REGISTER) |
| 11 | `icscf.ims_icscf:lir_avg_response_time` | ~48ms | Average LIR response time (user location during call routing) |
| 12 | `scscf.ims_auth:mar_avg_response_time` | ~92ms | Average MAR response time (authentication vector retrieval) |
| 13 | `scscf.ims_registrar_scscf:sar_avg_response_time` | ~101ms | Average SAR response time (S-CSCF assignment at HSS) |

---

## Per-UE Normalized Rates (13 features)

Counter rates divided by registered UE count (`ims_usrloc_pcscf:registered_contacts` for IMS metrics, `ran_ue` for 5G core metrics). Sliding 30-second window. Same value whether 2 or 200 UEs.

| # | Feature | Normalizer | What it measures |
|---|---|---|---|
| 14 | `normalized.pcscf.core:rcv_requests_register_per_ue` | IMS registered | SIP REGISTER rate per IMS user at P-CSCF |
| 15 | `normalized.pcscf.core:rcv_requests_invite_per_ue` | IMS registered | SIP INVITE (call attempt) rate per IMS user at P-CSCF |
| 16 | `normalized.icscf.core:rcv_requests_register_per_ue` | IMS registered | SIP REGISTER rate per user at I-CSCF |
| 17 | `normalized.icscf.core:rcv_requests_invite_per_ue` | IMS registered | SIP INVITE rate per user at I-CSCF |
| 18 | `normalized.scscf.core:rcv_requests_register_per_ue` | IMS registered | SIP REGISTER rate per user at S-CSCF |
| 19 | `normalized.scscf.core:rcv_requests_invite_per_ue` | IMS registered | SIP INVITE rate per user at S-CSCF |
| 20 | `normalized.icscf.cdp_replies_per_ue` | IMS registered | Diameter reply rate per user at I-CSCF |
| 21 | `normalized.scscf.cdp_replies_per_ue` | IMS registered | Diameter reply rate per user at S-CSCF |
| 22 | `normalized.pcscf.dialogs_per_ue` | IMS registered | Active SIP dialogs (calls) per user. 0 when idle, ~1.0 during calls. |
| 23 | `normalized.smf.bearers_per_ue` | 5G attached | QoS bearers per attached UE. ~2.0 idle, ~3.0 during calls (dedicated voice bearer). |
| 24 | `normalized.smf.sessions_per_ue` | 5G attached | PDU sessions per attached UE. Always 2.0 (internet + IMS APNs). |
| 25 | `normalized.upf.gtp_indatapktn3upf_per_ue` | 5G attached | GTP-U uplink (UE → gNB → UPF) packet rate per UE |
| 26 | `normalized.upf.gtp_outdatapktn3upf_per_ue` | 5G attached | GTP-U downlink (UPF → gNB → UE) packet rate per UE |

---

## Derived Composite / Temporal (3 features)

Features derived from multiple inputs or gated on event occurrence. Not pure error ratios (their denominators are not error counts), not pure counter rates (they combine counter-rates with activity gates). Each is scale-independent by construction.

| # | Feature | Formula | What it detects |
|---|---|---|---|
| 27 | `derived.upf_activity_during_calls` | actual_upf_rate / expected_upf_rate (only evaluated when `dialog_ng:active > 0`) | Ratio of UPF throughput vs expected during active calls. 1.0 = healthy or idle (when idle returns 1.0 directly). Drops to 0.0 when calls are active but UPF is not forwarding. |
| 28 | `derived.pcscf_avg_register_time_ms` | delta(register_time) / delta(register_success) | Average milliseconds per SIP registration at P-CSCF. ~250ms healthy (dominated by four serial HSS Diameter RTTs: UAR+MAR+SAR+LIR). Spikes to 4000ms+ under P-CSCF latency faults. Omitted from a snapshot when no new REGISTERs completed in the window. |
| 29 | `derived.rtpengine_loss_ratio` | packets_lost_rate / (packets_lost_rate + total_relayed_packets_rate) | Sliding-window packet-loss ratio on the rtpengine media relay. Detects network-layer packet loss at or upstream of rtpengine — a signal `errors_per_second` is blind to. See ADR `rtpengine_loss_ratio_feature.md` for why re-admitting the two underlying counters as rate inputs is compatible with `remove_cumulative_rtpengine_features.md`. |

---

## RTPEngine Gauge (1 feature)

One point-in-time gauge for rtpengine's internal error rate. See the Derived Composite section for `rtpengine_loss_ratio`, which is the scale-independent signal for network-layer packet loss.

| # | Feature | Healthy Baseline | What it measures |
|---|---|---|---|
| 30 | `rtpengine.errors_per_second_(total)` | 0 | Real-time RTP relay error rate. Detects rtpengine-**internal** relay failures (e.g. "can't forward," "malformed SDP"). Does NOT move on network-layer packet loss upstream of rtpengine — that's the job of `derived.rtpengine_loss_ratio` (feature #29). |

---

## Features intentionally excluded

| Feature | Reason | ADR |
|---|---|---|
| `rtpengine.average_packet_loss` | Cumulative lifetime average — carries stale data from previous chaos runs | `remove_cumulative_rtpengine_features.md` |
| `rtpengine.packet_loss_standard_deviation` | Cumulative lifetime stddev — same problem | `remove_cumulative_rtpengine_features.md` |
| `rtpengine.average_mos` | Cumulative lifetime average — shifts permanently after bad sessions | `remove_cumulative_rtpengine_features.md` |
| `rtpengine.packets_lost` (absolute value) | Cumulative counter — only increments, never resets. Re-admitted for sliding-window rate use only; never surfaced to the model as an absolute value. | `remove_cumulative_rtpengine_features.md`, `rtpengine_loss_ratio_feature.md` |
| `rtpengine.total_relayed_packets` (absolute value) | Cumulative counter. Re-admitted for sliding-window rate use only; never surfaced as an absolute value. | `rtpengine_loss_ratio_feature.md` |
| `rtpengine.total_number_of_1_way_streams` | Cumulative counter — only increments | `remove_cumulative_rtpengine_features.md` |
| `rtpengine.total_relayed_packet_errors` | Cumulative counter — only increments | `remove_cumulative_rtpengine_features.md` |
| `icscf.cdp:timeout` | Cumulative counter — carries stale timeout count from previous runs | `remove_cumulative_timeout_counters.md` |
| `icscf.ims_icscf:uar_timeouts` | Cumulative counter — covered by `icscf_uar_timeout_ratio` instead | `remove_cumulative_timeout_counters.md` |
| `icscf.ims_icscf:lir_timeouts` | Cumulative counter — covered by `icscf_lir_timeout_ratio` instead | `remove_cumulative_timeout_counters.md` |
| `scscf.ims_auth:mar_timeouts` | Cumulative counter — covered by `scscf_mar_timeout_ratio` instead | `remove_cumulative_timeout_counters.md` |
| `health.ran_ue`, `health.gnb`, `health.upf_sessions`, `health.ims_registered` | Absolute UE/gNB counts — don't generalize across different UE populations | `anomaly_model_v2_improvements.md` |
| `derived.pcscf_httpclient_failure_ratio` | 84% failure rate is "normal" (deployment-specific SCP/Rx noise) — masks real faults | `anomaly_model_v2_improvements.md` |
| `normalized.rtpengine.pps_per_session` | Always 0 — gauge resets between snapshots faster than collection interval | `anomaly_model_v2_improvements.md` |

---

## Historical note — the "24-feature model" bookkeeping bug (fixed 2026-04-24)

Before 2026-04-24, `training_meta.json` reported 24 features while the preprocessor capability was 30. An earlier version of this reference documented this as a traffic-coverage gap, hypothesizing that the trainer's traffic didn't exercise the Diameter Cx paths often enough for the 6 temporal response-time features to enter the trained set. A `--debug-counters` diagnostic run disproved that hypothesis: all 6 gating counters advanced 20–44% of windows, all 6 temporal features emitted in 67–98% of snapshots, and `_feature_means` had full samples for each.

**Actual root cause:** `AnomalyScreener.learn()` set `self._feature_keys` from the *first* sample's `features.keys()` and never updated it. The first sample is structurally smaller than subsequent ones because the preprocessor's sliding-window rate pipeline needs ≥2 history entries to compute rates (`preprocessor.py:312`), and the 6 temporal features are gated on their counter's rate being > 0 (`preprocessor.py:360-364`). Rate = 0 on snapshot 1 → temporal features omitted from snapshot 1 → `_feature_keys` locked to the incomplete set forever.

The model itself was always correct — River's `HalfSpaceTrees` received the full features dict on every `learn_one()` call, and `_feature_means` (the running-stats dict used by runtime attribution) was populated without a first-sample gate. Only the metadata export was wrong, and only because it read from the frozen `_feature_keys` attribute.

**Fix that shipped:** removed the `_feature_keys` instance attribute entirely. `AnomalyScreener.feature_keys` is now a property returning `sorted(self._feature_means.keys())` — the authoritative union of every feature seen across all training samples. Consumers (`training_meta.json` export, CLI prints) now read the property. Single source of truth.

**Prevention:** `MetricPreprocessor.EXPECTED_FEATURE_KEYS` declares the 30 features the preprocessor is designed to emit. `anomaly_trainer.persistence.save_model()` refuses to persist if the trained feature set is missing any declared key, printing the missing features and preserving the previous good model on disk. `--allow-missing-features` exists for intentional partial-coverage experiments and is documented as "not for production." Tests: `agentic_ops_common/tests/test_anomaly_save_coverage_guard.py`.

Verification: the 2026-04-24T19:03:17Z retrain produced a model with all 30 features (209 samples, guard passed without override). No temporal-feature gap remains.
