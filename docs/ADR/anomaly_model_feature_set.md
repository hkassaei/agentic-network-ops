# Anomaly Detection Model — Feature Set Reference

**Last updated:** 2026-04-17
**Total features:** 29
**Model:** River HalfSpaceTrees (50 trees, height 15, window 50, threshold 0.70)
**Training:** 1200 seconds (default) of randomized IMS traffic on a healthy stack, 5-second collection intervals, 30-second sliding window for rate computation. Temporal metrics are pre-filtered: response-time features are emitted only in snapshots where the underlying event counter advanced (see ADR `anomaly_training_zero_pollution.md`).

---

## Design Principles

1. **Scale-independent** — all features produce the same values regardless of UE count (2 or 2000)
2. **No cumulative lifetime metrics** — only point-in-time gauges, sliding-window rates, and derived ratios. Cumulative counters that carry stale data from previous runs are excluded (see ADRs: `remove_cumulative_rtpengine_features.md`, `remove_cumulative_timeout_counters.md`)
3. **Sliding window smoothed** — counter-derived rates use a 30-second window (6 samples) to eliminate sparsity from bursty SIP traffic
4. **Per-UE normalized** — traffic rates divided by registered UE count so the model generalizes across different UE populations

---

## Error Ratios (10 features)

Scale-independent ratios in [0, 1]. Zero during healthy operation, spike during faults.

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
| 9 | `derived.upf_activity_during_calls` | actual_upf_rate / expected_upf_rate | Ratio of UPF throughput vs expected during active calls. 1.0 = healthy or idle. Drops to 0.0 when calls are active but UPF is not forwarding. |
| 10 | `derived.pcscf_avg_register_time_ms` | delta(register_time) / delta(register_success) | Average milliseconds per SIP registration at P-CSCF. ~250ms healthy (dominated by four serial HSS Diameter RTTs: UAR+MAR+SAR+LIR). Spikes to 4000ms+ under P-CSCF latency faults. Omitted entirely from the snapshot when no new REGISTERs completed in the window. |

---

## Response Times (5 features)

Point-in-time Diameter latency gauges. Tight distributions during healthy operation, spike under HSS latency or overload faults. Each feature is omitted from a snapshot when its underlying reply counter did not advance (no new requests completed in the rate window); see ADR `anomaly_training_zero_pollution.md`.

| # | Feature | Healthy Baseline | What it measures |
|---|---|---|---|
| 11 | `icscf.cdp:average_response_time` | ~51ms | Average Diameter response time at I-CSCF (across all Cx operations — weighted mix of UAR + LIR) |
| 12 | `icscf.ims_icscf:uar_avg_response_time` | ~52ms | Average UAR response time (user authorization during REGISTER) |
| 13 | `icscf.ims_icscf:lir_avg_response_time` | ~48ms | Average LIR response time (user location during call routing) |
| 14 | `scscf.ims_auth:mar_avg_response_time` | ~92ms | Average MAR response time (authentication vector retrieval) |
| 15 | `scscf.ims_registrar_scscf:sar_avg_response_time` | ~101ms | Average SAR response time (S-CSCF assignment at HSS) |

---

## Per-UE Normalized Rates (12 features)

Counter rates divided by registered UE count (`ims_usrloc_pcscf:registered_contacts` for IMS metrics, `ran_ue` for 5G core metrics). Sliding 30-second window. Same value whether 2 or 200 UEs.

| # | Feature | Normalizer | What it measures |
|---|---|---|---|
| 16 | `normalized.pcscf.core:rcv_requests_register_per_ue` | IMS registered | SIP REGISTER rate per IMS user at P-CSCF |
| 17 | `normalized.pcscf.core:rcv_requests_invite_per_ue` | IMS registered | SIP INVITE (call attempt) rate per IMS user at P-CSCF |
| 18 | `normalized.icscf.core:rcv_requests_register_per_ue` | IMS registered | SIP REGISTER rate per user at I-CSCF |
| 19 | `normalized.icscf.core:rcv_requests_invite_per_ue` | IMS registered | SIP INVITE rate per user at I-CSCF |
| 20 | `normalized.scscf.core:rcv_requests_register_per_ue` | IMS registered | SIP REGISTER rate per user at S-CSCF |
| 21 | `normalized.scscf.core:rcv_requests_invite_per_ue` | IMS registered | SIP INVITE rate per user at S-CSCF |
| 22 | `normalized.icscf.cdp_replies_per_ue` | IMS registered | Diameter reply rate per user at I-CSCF |
| 23 | `normalized.scscf.cdp_replies_per_ue` | IMS registered | Diameter reply rate per user at S-CSCF |
| 24 | `normalized.pcscf.dialogs_per_ue` | IMS registered | Active SIP dialogs (calls) per user. 0 when idle, ~1.0 during calls. |
| 25 | `normalized.smf.bearers_per_ue` | 5G attached | QoS bearers per attached UE. ~2.0 idle, ~3.0 during calls (dedicated voice bearer). |
| 26 | `normalized.smf.sessions_per_ue` | 5G attached | PDU sessions per attached UE. Always 2.0 (internet + IMS APNs). |
| 27 | `normalized.upf.gtp_indatapktn3upf_per_ue` | 5G attached | GTP-U uplink (UE → gNB → UPF) packet rate per UE |
| 28 | `normalized.upf.gtp_outdatapktn3upf_per_ue` | 5G attached | GTP-U downlink (UPF → gNB → UE) packet rate per UE |

---

## RTPEngine (1 feature)

Point-in-time gauge. Not a cumulative lifetime metric.

| # | Feature | Healthy Baseline | What it measures |
|---|---|---|---|
| 29 | `rtpengine.errors_per_second_(total)` | 0 | Real-time RTP relay error rate. Zero when healthy, non-zero during active media path faults. |

---

## Features intentionally excluded

| Feature | Reason | ADR |
|---|---|---|
| `rtpengine.average_packet_loss` | Cumulative lifetime average — carries stale data from previous chaos runs | `remove_cumulative_rtpengine_features.md` |
| `rtpengine.packet_loss_standard_deviation` | Cumulative lifetime stddev — same problem | `remove_cumulative_rtpengine_features.md` |
| `rtpengine.average_mos` | Cumulative lifetime average — shifts permanently after bad sessions | `remove_cumulative_rtpengine_features.md` |
| `rtpengine.packets_lost` | Cumulative counter — only increments, never resets | `remove_cumulative_rtpengine_features.md` |
| `rtpengine.total_number_of_1_way_streams` | Cumulative counter — only increments | `remove_cumulative_rtpengine_features.md` |
| `rtpengine.total_relayed_packet_errors` | Cumulative counter — only increments | `remove_cumulative_rtpengine_features.md` |
| `icscf.cdp:timeout` | Cumulative counter — carries stale timeout count from previous runs | `remove_cumulative_timeout_counters.md` |
| `icscf.ims_icscf:uar_timeouts` | Cumulative counter — covered by `icscf_uar_timeout_ratio` instead | `remove_cumulative_timeout_counters.md` |
| `icscf.ims_icscf:lir_timeouts` | Cumulative counter — covered by `icscf_lir_timeout_ratio` instead | `remove_cumulative_timeout_counters.md` |
| `scscf.ims_auth:mar_timeouts` | Cumulative counter — covered by `scscf_mar_timeout_ratio` instead | `remove_cumulative_timeout_counters.md` |
| `health.ran_ue`, `health.gnb`, `health.upf_sessions`, `health.ims_registered` | Absolute UE/gNB counts — don't generalize across different UE populations | `anomaly_model_v2_improvements.md` |
| `derived.pcscf_httpclient_failure_ratio` | 84% failure rate is "normal" (deployment-specific SCP/Rx noise) — masks real faults | `anomaly_model_v2_improvements.md` |
| `normalized.rtpengine.pps_per_session` | Always 0 — gauge resets between snapshots faster than collection interval | `anomaly_model_v2_improvements.md` |
