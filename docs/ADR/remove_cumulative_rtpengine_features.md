# ADR: Remove Cumulative RTPEngine Features from Anomaly Model

**Date:** 2026-04-15
**Status:** Accepted
**Related episodes:**
- [`docs/critical-observations/run_20260415_032202_ims_network_partition.md`](../critical-observations/run_20260415_032202_ims_network_partition.md) — IMS Network Partition, score 20%. Stale RTPEngine metrics dominated the anomaly screener, sending the agent down the wrong path.
- [`docs/critical-observations/run_20260415_212123_ims_network_partition.md`](../critical-observations/run_20260415_212123_ims_network_partition.md) — Same scenario re-run on a fresh stack, score 100%. Without stale RTPEngine metrics, the agent correctly diagnosed the P-CSCF network partition.
- Related ADR: [`anomaly_model_v2_improvements.md`](anomaly_model_v2_improvements.md)

---

## Decision

Remove 6 RTPEngine features from the anomaly detection model's feature set. These are cumulative lifetime metrics that carry stale data from previous chaos runs into subsequent scenarios, causing the anomaly screener to flag phantom anomalies that mislead the agent.

### Features removed

| Feature | Type | Why it's problematic |
|---|---|---|
| `rtpengine.average_packet_loss` | Lifetime average | Computed as `sum_of_all_packet_loss_values / total_samples` across ALL RTP sessions since the container started. Once a chaos scenario causes packet loss, this average stays elevated permanently. It can only decrease slowly as new healthy sessions dilute it — it never resets to 0. |
| `rtpengine.packet_loss_standard_deviation` | Lifetime stddev | Same accumulation problem. After any scenario with bursty packet loss, this stays non-zero until the container is recreated. |
| `rtpengine.average_mos` | Lifetime average | Computed across all sessions since container start. After a bad session drops MOS, the average shifts down permanently. |
| `rtpengine.packets_lost` | Cumulative counter | Total packets lost since container start. Only increments, never resets. After a fault scenario that causes 100+ lost packets, this counter stays at that value in every subsequent run. |
| `rtpengine.total_number_of_1_way_streams` | Cumulative counter | Total one-directional streams detected since container start. Only increments. |
| `rtpengine.total_relayed_packet_errors` | Cumulative counter | Total relay errors since container start. Only increments. |

---

## Context

### The problem: stale metrics from previous runs

The anomaly model is trained on a freshly deployed stack where all RTPEngine cumulative metrics are 0 (or 4.3 for MOS). The model learns "0 is normal" for packet loss and "4.3 is normal" for MOS.

After running a chaos scenario that causes RTP packet loss (e.g., Call Quality Degradation, Data Plane Degradation), these cumulative metrics shift:
- `average_packet_loss`: 0 → 8
- `packet_loss_standard_deviation`: 0 → 15
- `average_mos`: 4.3 → 3.2
- `packets_lost`: 0 → 146

These values persist across subsequent scenarios because RTPEngine only resets them when the container is recreated. On the next scenario (e.g., IMS Network Partition), the anomaly screener sees `average_packet_loss = 8.0` and flags it as a HIGH severity anomaly — even though there is no current packet loss. The stale metric from a previous run dominates the screener's output and sends the Network Analyst down the wrong diagnostic path.

### Proof: two runs of the same scenario

**Run 1 (stale stack, score 20%):** The anomaly screener's top flags were:
```
rtpengine | packet_loss_standard_deviation | 15.00 | 0.00 | HIGH
rtpengine | average_packet_loss            |  8.00 | 0.00 | HIGH
```

These were stale metrics from previous chaos runs. The agent diagnosed RTPEngine as the root cause and missed the actual P-CSCF network partition entirely.

**Run 2 (fresh stack, score 100%):** After redeploying the stack (which recreated the RTPEngine container and reset its cumulative stats), the same scenario produced:
```
scscf    | ims_auth:mar_avg_response_time  | 125.00 | 88.89 | HIGH
icscf    | ims_icscf:lir_avg_response_time |   0.00 | 51.03 | HIGH
rtpengine| average_mos                     |   0.00 |  4.17 | HIGH
```

Without stale RTPEngine noise, the screener surfaced the real signals (Diameter latency, zero LIR responses). The Network Analyst ran `measure_rtt` between P-CSCF and I-CSCF, found 100% bidirectional packet loss, and correctly diagnosed the network partition.

The only difference between the two runs was the container state. No code or model changes were made.

---

## Design

### What remains for RTPEngine

After removing the 6 cumulative features, the model retains one RTPEngine-derived feature:

- `rtpengine.errors_per_second_(total)` — a **point-in-time gauge** that reflects the current error rate, not a lifetime accumulation. This resets to 0 when no errors are occurring, regardless of past history.

RTPEngine media quality is also monitored indirectly through:
- `derived.upf_activity_during_calls` — detects when calls are active but no media is flowing
- `normalized.pcscf.dialogs_per_ue` — tracks active call count per UE

### Why not convert to delta-based features?

An alternative to removal would be converting these cumulative metrics to rate-based features (delta per time window). However:

1. `average_packet_loss` and `average_mos` are already averages — computing a rate of an average is semantically meaningless
2. `packets_lost` and `total_relayed_packet_errors` could be converted to rates, but they increment rarely and in bursts, producing the same sparsity problem we solved with sliding windows for SIP counters
3. The RTPEngine `errors_per_second_(total)` gauge already provides a clean, real-time signal for active errors without any of these complications

The simplest and most robust fix is removal.

---

## Files Changed

- `agentic_ops_v5/anomaly/preprocessor.py` — removed 6 features from `_COLLECT_METRICS` and from the passthrough gauge list

---

## Verification

After retraining the anomaly model:
1. Run a fault scenario that causes RTP packet loss (e.g., Call Quality Degradation)
2. Without redeploying the stack, immediately run a different scenario (e.g., IMS Network Partition or P-CSCF Latency)
3. Verify the anomaly screener does NOT flag stale RTPEngine metrics as HIGH severity
4. Verify the agent diagnoses the second scenario correctly despite residual RTPEngine state from the first
