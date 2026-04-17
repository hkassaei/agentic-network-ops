# ADR: Fix Zero-Pollution in Anomaly Training + Silent-Failure Severity

**Date:** 2026-04-16
**Status:** Proposed
**Supersedes / Amends:**
- Partially amends [`anomaly_model_feature_set.md`](anomaly_model_feature_set.md) — the feature set itself is unchanged, but how several of those features are captured during training changes.
- Amends [`standalone_anomaly_trainer.md`](standalone_anomaly_trainer.md) — the baseline trainer's traffic pattern and default duration change.
- Partially amends [`anomaly_attribution_algorithm.md`](anomaly_attribution_algorithm.md) — the severity rule gains a silent-failure escalation path.

**Related:**
- [`../../agentic_ops_v5/docs/agent_logs/run_20260416_223936_ims_network_partition.md`](../../agentic_ops_v5/docs/agent_logs/run_20260416_223936_ims_network_partition.md) — the episode that surfaced these problems.

---

## Decision

Fix three coupled problems in the anomaly screener's training pipeline and scoring logic, in a single coordinated change:

1. **Temporal-metric pre-filter.** Response-time / average-duration metrics are excluded from a snapshot when the underlying event counter did not advance. A response time of 0 is semantically *not applicable* (no event occurred), not a value of zero — feeding it into the baseline as if it were a valid observation has been inflating std and suppressing deviations.
2. **Denser baseline traffic + longer training duration.** Rework the traffic generator's activity weights and waits so the stack sees signaling and data-plane activity in a larger fraction of training snapshots. Extend default training duration from ~12 min to 20 min to compensate for the pre-filter dropping some data points.
3. **Silent-failure severity escalation.** Add a severity-rule branch that escalates `current=0, learned_mean>>0` to HIGH — but only when the metric's own underlying counter was observed to advance in recent history. This prevents false positives during naturally quiet moments.

A fourth item — **doubling UEs from 2 to 4** — is recorded here as future work. It is orthogonal to the zero-pollution fix above and needs its own provisioning work before it can be adopted.

---

## Context

### The triggering evidence

In episode `run_20260416_223936_ims_network_partition.md`, the anomaly screener produced the following flag table for a P-CSCF network partition:

| Component | Metric | Current | Learned Normal | Severity |
|---|---|---|---|---|
| icscf | `ims_icscf:lir_avg_response_time` | 0.00 | 62.73 | MEDIUM |
| icscf | `ims_icscf:uar_avg_response_time` | 79.00 | 59.23 | MEDIUM |
| icscf | `cdp:average_response_time` | 79.00 | 61.35 | MEDIUM |

The first row — a response time dropping from ~63ms to exactly 0 — is, in domain terms, a complete halt of LIR processing. But it was flagged MEDIUM, not HIGH.

Investigating why: the trained std of `ims_icscf:lir_avg_response_time` is 16.04ms, not the ~5ms you would expect for a healthy load-driven response-time metric. The std was inflated because 4% of the 104 training snapshots recorded exactly 0ms — snapshots taken during moments when no LIR requests were flowing, so the "average response time" had nothing to average and reported 0. At std=16ms, `|0 − 62.73| / 16 = 3.91σ` falls in the MEDIUM band (2-5σ), not HIGH (>5σ).

### Scope of the problem across the 28-feature model

A full audit (see triggering run's post-run analysis) showed **13 of 28 features** are polluted to some degree by idle-period snapshots:

- **Severely polluted (≥46% of training snapshots = 0):** 6 metrics, most of them `_per_ue` rate metrics and the derived `pcscf_avg_register_time_ms` (59% zeros, std > mean).
- **Moderately polluted (3-8% zeros):** 5 metrics, including `lir_avg_response_time`.
- **Minimally polluted (1-2% zeros):** 2 UPF rate metrics.

Temporal/duration metrics (6 of the 28) are the ones where "0" is semantically wrong — no event means the metric is *undefined* for that window, not zero. The rate/counter metrics (`_per_ue` family) are a separate, structural problem: 0 is a legitimate observation for those, but the mean/std detector cannot distinguish "naturally idle" from "silent failure."

### Why traffic-generator idle time amplifies the problem

The current trainer (`anomaly_trainer/traffic.py`) picks activities weighted as:
- `register_both` 20%, `register_ue1` 15%, `call` 45%, `idle` 20%.

Most training time (~79%) is spent inside the `call` activity, but calls are mostly SIP-idle during the 5-30s hold phase — RTP flows, but no new REGISTER / INVITE / Diameter signaling. Combined with the explicit 20% idle, **roughly 74% of training snapshots are SIP-signaling-idle**. That's where the rate metrics inherit their 46-59% zero fractions, and where temporal metrics inherit their 0-ms entries.

---

## Design

### 1. Temporal-metric pre-filter

**Scope.** Applies to these 6 time/duration features:

- `icscf.ims_icscf:lir_avg_response_time`
- `icscf.ims_icscf:uar_avg_response_time`
- `icscf.cdp:average_response_time`
- `scscf.ims_auth:mar_avg_response_time`
- `scscf.ims_registrar_scscf:sar_avg_response_time`
- `derived.pcscf_avg_register_time_ms`

**Rule.** For each such feature at each snapshot, the preprocessor checks whether the corresponding event counter advanced since the previous snapshot:
- If the counter advanced by ≥1, emit the metric normally.
- If the counter is unchanged, **omit the feature from this snapshot's feature vector entirely.**

The River `HalfSpaceTrees` model and the per-feature mean/std accumulator both handle sparse feature vectors — a feature absent from one sample's dict is simply skipped for that sample.

**Semantics.** This differs from "treat 0 as missing":
- Missing implies uncertainty about what happened.
- The pre-filter encodes "we know no event occurred, so the timing question is not applicable."
- Both result in "don't update stats for this feature on this snapshot," but the semantic distinction is worth preserving in comments and logs so future debugging isn't confused.

**Counter mapping.** Each time metric is paired with its underlying counter in the preprocessor:
- `lir_avg_response_time` → LIR request count
- `uar_avg_response_time` → UAR request count
- `cdp:average_response_time` → Diameter replies count
- `mar_avg_response_time` → MAR request count
- `sar_avg_response_time` → SAR request count
- `pcscf_avg_register_time_ms` → P-CSCF REGISTER count

### 2. Denser baseline traffic + longer duration

**Traffic generator changes (`anomaly_trainer/traffic.py`).** Four knobs:

| Knob | Before | After | Rationale |
|---|---|---|---|
| `idle` activity weight | 20% | 5% | Remove most explicit idle — there's already plenty of SIP-idle embedded in call holds. |
| Post-register waits | (3-8)s / (3-6)s | (1-3)s | ~3× more register events per unit time. |
| Call hold duration | 5-30s | 5-15s | Same signaling count per call, shorter dead-SIP time. |
| Call post-hangup settle | 3-8s | 2-4s | Faster cycling between calls. |

**Not adopted:** a "concurrent register during active call" pattern. That pattern does occur in real multi-subscriber IMS networks but is not naturally present in our 2-UE stack, so training on it would be synthetic augmentation that doesn't match the system we're actually monitoring.

**Training duration.** Default changes from 715s (~12 min) to 1200s (20 min). At the existing 5-second collector poll, this yields ~170 snapshots (vs 104 today). After the pre-filter drops polluted temporal entries:

- `lir_avg_response_time`: ~163 valid samples (was ~100 pre-filter, ~100 with no change).
- `pcscf_avg_register_time_ms`: ~70-120 valid samples depending on how much the traffic density changes cut its zero rate.

### 3. Silent-failure severity escalation

**Rule addition to `agentic_ops_v5/anomaly/screener.py:_attribute_anomalies`.** After computing `deviation = |current − mean| / std`:

```python
if deviation > 5.0:
    severity = "HIGH"
elif deviation > 2.0:
    severity = "MEDIUM"
else:
    severity = "LOW"

# Silent-failure escalation:
# A counter or rate metric going to exactly 0 when its learned mean is
# substantially non-zero is categorically different from "shifted below
# mean." Escalate to HIGH — but only if we have evidence that the
# subsystem WAS active recently (otherwise we'd false-positive on
# naturally-idle moments).
if (
    current_value == 0.0
    and learned_mean > MIN_ACTIVE_MEAN
    and _counter_advanced_in_last_n_snapshots(underlying_counter, n=2)
):
    severity = "HIGH"
```

**Liveness gate (`_counter_advanced_in_last_n_snapshots`).** The preprocessor already maintains counter history for rate computation. The escalation consults it: the metric's underlying counter must have advanced in at least one of the last 2 snapshots. "Was active, then went silent" is escalated; "has been quiet all along" is not.

**`MIN_ACTIVE_MEAN`.** A floor that says "this metric was meaningfully active during training." For response-time metrics we'll use 10ms; for rate metrics, 0.01 per UE per window. Below the floor, the metric is not considered a load-bearing liveness signal and escalation does not apply.

**Consequences considered:**
- Case A (metric never used in the monitored system): training mean ≈ 0, so escalation never triggers. No effect.
- Case B (metric has non-trivial mean but system is naturally quiet right now): escalation would false-positive *without* the liveness gate. The gate prevents this by requiring recent activity.
- Case C (metric should be active and isn't — the case we want to catch): escalation correctly marks HIGH.

---

## Future work — not part of this ADR

### Doubling UEs from 2 to 4

Would give:
- **Concurrent signaling patterns naturally** — one UE pair can be on a call while the other pair re-registers, without having to fabricate the pattern.
- **Differential fault signals** — a partition that isolates UE1+UE2 but leaves UE3+UE4 reachable gives a richer ground-truth pattern than today's all-or-nothing.
- **Better aggregate statistics** — metrics averaging over more UEs produce smoother baselines.

Cost (roughly half a day plus a stack cold-start to verify):
- Subscriber provisioning in PyHSS / MongoDB for 2 new IMSIs with K/OPc/AMF.
- UERANSIM configs for UE3/UE4.
- New pjsua UE containers in `e2e-vonr.yaml`.
- Parameterize the UE pool in `anomaly_trainer/traffic.py`, `network/operate/agentic_chaos/agents/call_setup.py`, `tools/observation_tools.py`, `tools/application_tools.py`, and the GUI/topology viewer — all currently hardcode `e2e_ue1` and `e2e_ue2`.

The normalized `_per_ue` metric design already makes the model UE-count invariant when traffic scales linearly, so doubling UEs doesn't break existing training data. But deploying it needs its own coordination with the chaos framework and scorer, and is decoupled from the zero-pollution fix. Handled as a follow-up ADR when prioritized.

---

## Sequencing and validation

1. **Pre-filter + screener escalation** land first. Both are small, local code changes (`agentic_ops_v5/anomaly/preprocessor.py`, `agentic_ops_v5/anomaly/screener.py`). The existing trained model stays loadable — the escalation only activates during scoring of new snapshots.

2. **Traffic changes + retraining.** Update `anomaly_trainer/traffic.py` and run `python -m anomaly_trainer --duration 1200` on a fresh, healthy stack. Verify post-training that:
   - `lir_avg_response_time` std drops from ~16ms toward ~5ms.
   - `pcscf_avg_register_time_ms` zero rate drops from ~59% toward ~20-25%.
   - `_per_ue` rate metrics' zero rate drops from ~59% toward ~30-40%.

3. **Regression re-run.** Re-run the corpus (`IMS Network Partition`, `HSS Unresponsive`, `MongoDB Gone`, etc.) and compare scores against the Track-1 baseline. Expected:
   - The P-CSCF partition episode sees LIR response time flagged HIGH (via escalation) rather than MEDIUM.
   - No regressions on episodes that were already scoring 100%.

4. **If a regression appears,** the pre-filter change is easily revertible by flipping a single flag in the preprocessor. The traffic changes require retraining to revert; if that becomes necessary we keep both model variants on disk.

---

## Files that will change

**Preprocessor and screener:**
- `agentic_ops_v5/anomaly/preprocessor.py` — temporal-metric pre-filter, counter-advance history for the liveness gate.
- `agentic_ops_v5/anomaly/screener.py` — silent-failure escalation branch in `_attribute_anomalies`.

**Traffic generator:**
- `anomaly_trainer/traffic.py` — four knob changes (idle weight, register waits, call hold, settle).
- `anomaly_trainer/__main__.py` — default duration 715 → 1200.

**Documentation:**
- This ADR.
- Cross-link from `anomaly_model_feature_set.md` and `standalone_anomaly_trainer.md`.

No prompt changes. No orchestrator changes. The trained model on disk will need to be regenerated after the traffic changes land — existing deployments must re-run `python -m anomaly_trainer --duration 1200` before taking advantage of the cleaner baseline.
