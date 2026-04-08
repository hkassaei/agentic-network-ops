# ADR: Anomaly Attribution Algorithm — From Overall Score to Individual Metrics

**Date:** 2026-04-07
**Status:** Open — decision pending
**Related:**
- `docs/ADR/anomaly_detection_layer.md` — parent ADR for the anomaly detection layer
- `docs/ADR/standalone_anomaly_trainer.md` — training approach
- `agentic_ops_v5/anomaly/screener.py` — current implementation

## Context

The anomaly detection pipeline has two stages:

1. **Detection:** River HalfSpaceTrees scores a 44-feature metric snapshot against the trained healthy baseline. It produces a single overall anomaly score (0.0 = normal, 1.0 = maximally anomalous). This works well — scores of 0.9+ are reliably produced under fault conditions.

2. **Attribution:** Given that the overall score says "something is wrong," we need to tell the NetworkAnalyst LLM WHICH specific metrics are anomalous. The LLM needs a table of flagged metrics with their current vs. normal values, not just a scalar score.

The attribution step bridges the gap between "the ML model detected something" and "the LLM can reason about specific components and metrics."

## The Problem

HalfSpaceTrees operates in 44-dimensional space. When a fault causes multiple correlated metric shifts (e.g., P-CSCF latency causes register_rate to spike, 200_replies to drop, tmx:active_transactions to rise, and Diameter timeouts at I-CSCF — all simultaneously), the anomaly is **multivariate**. No single feature removal explains the overall score because the other 43 shifted features still keep the point in the anomalous region.

## Current Implementation (interim)

**Deviation-based ranking** (`screener.py:_attribute_anomalies`):

For each feature, compute how many training standard deviations the current value is from the training mean. Report the top 10 features by deviation as flags.

```python
deviation = abs(current_value - learned_mean) / max(std, 0.1)
if deviation > 1.0:  # more than 1 std from mean
    candidates.append(...)
```

**Pros:**
- Simple, fast, interpretable
- Works in practice: correctly flags `pcscf.register_rate` at 4.0/s when training mean was 0.2/s
- No dependency on the model's internal structure

**Cons:**
- Doesn't actually explain the MODEL's score — it's a parallel computation
- May flag features that are statistically deviant but not causally relevant
- The 1.0 std threshold is arbitrary
- Doesn't capture feature interactions (e.g., "register_rate is high AND 200_replies is low" is more informative than either alone)

## Alternative Approaches to Evaluate

### Option A: SHAP Values (SHapley Additive exPlanations)

Theoretically optimal attribution. Computes the marginal contribution of each feature to the prediction by averaging over all possible feature coalitions.

**Pros:**
- Gold standard for model interpretability
- Handles multivariate interactions
- Has theoretical guarantees (consistency, local accuracy)

**Cons:**
- Computationally expensive: O(2^N) exact, or O(N × K) for sampling-based approximation. With 44 features and needing results in <1 second, this may be too slow.
- SHAP for tree ensembles (TreeSHAP) is fast, but River's HalfSpaceTrees is not a standard scikit-learn tree — would need custom implementation or model conversion.
- Adds a significant dependency (shap library).

### Option B: Feature Ablation by Component Group

Instead of removing one feature at a time, remove ALL features from a component at once and measure the score drop. With 10 components (pcscf, icscf, scscf, amf, smf, upf, rtpengine, pyhss, mongo, smf), this is only 10 ablation tests instead of 44.

```python
for component in ["pcscf", "icscf", "scscf", ...]:
    modified = {k: learned_mean[k] if k.startswith(component) else v for k, v in features.items()}
    reduced_score = model.score_one(modified)
    component_contribution = overall_score - reduced_score
```

**Pros:**
- Directly answers "which COMPONENT is anomalous" — which is what the NetworkAnalyst needs
- Only 10 model evaluations instead of 44
- Handles multivariate interactions within a component (replacing all pcscf features at once catches the combined effect)

**Cons:**
- Doesn't identify which specific metric within the component is the most anomalous
- Can be combined with the current deviation-based approach: use component ablation to find the anomalous component, then deviation ranking to find the specific metrics within that component

### Option C: Dual-Model Approach

Train a second, simpler model (e.g., per-metric Gaussian threshold) alongside HalfSpaceTrees. Use HalfSpaceTrees for overall detection (it handles multivariate interactions) and per-metric Gaussians for attribution (each metric independently scored).

```python
# Detection (multivariate)
overall_score = hst_model.score_one(features)

# Attribution (per-metric)
for key, value in features.items():
    z_score = (value - mean[key]) / std[key]
    if abs(z_score) > 2.0:
        flag(key, z_score)
```

**Pros:**
- Simple, fast, no model-interpretation complexity
- Each metric's z-score is independently meaningful
- Easy to explain to operators

**Cons:**
- Per-metric Gaussians miss interactions (e.g., register_rate=0.5 is normal during a call but anomalous during idle)
- Essentially what the current deviation-based approach already does — the HalfSpaceTrees model would only serve as a gate ("should we look at individual metrics?")

### Option D: Skip Attribution Entirely

Report the overall anomaly score and the raw feature values vs. their means. Let the NetworkAnalyst LLM do the attribution — it's better at reasoning about which metrics matter in context.

```
ANOMALY DETECTED (score: 0.95). Here are all features with their current vs. healthy values:
| Feature | Current | Healthy Mean |
| pcscf.register_rate | 4.0/s | 0.2/s |
| pcscf.200_replies_rate | 0.0/s | 0.2/s |
| pcscf.tmx_active | 3.0 | 0.0 |
...
```

**Pros:**
- Zero attribution code — simplest possible implementation
- LLM can reason about causality ("register_rate is high BECAUSE of P-CSCF latency")
- No false attribution — the LLM sees all the data and decides what matters

**Cons:**
- Dumps 44 rows into the prompt (adds ~500 tokens)
- LLM may ignore the table (the whole reason we built the screener)
- Attribution quality depends on the LLM's attention

## Recommendation

Not yet decided. The current deviation-based approach (Option C variant) works for the immediate use case. For production at scale, **Option B (component-group ablation) combined with deviation ranking** is the most promising: identify the anomalous component first (10 evaluations), then rank specific metrics within that component by deviation.

## Action Items

- [ ] Test the current deviation-based approach on a full P-CSCF Latency run and evaluate whether the flags are useful to the NetworkAnalyst
- [ ] Prototype Option B (component ablation) and compare flag quality
- [ ] Measure latency impact of each approach at 44 features and at 200+ features (future scale)
- [ ] Decide based on empirical results, not theory
