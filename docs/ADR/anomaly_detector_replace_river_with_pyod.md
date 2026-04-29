# ADR: Replace River HalfSpaceTrees with PyOD ECOD as the Anomaly Screener

**Date:** 2026-04-28
**Status:** Proposed — pending implementation.
**Supersedes (in part):** [`anomaly_detection_layer.md`](anomaly_detection_layer.md) — that ADR's choice of River HalfSpaceTrees is replaced. The anomaly *layer* (algorithmic screener feeding NetworkAnalyst) stays; the *implementation* changes.
**Related ADRs:**
- [`anomaly_model_overflagging.md`](anomaly_model_overflagging.md) — over-flagging is the dominant remaining diagnosis-quality ceiling. This ADR is the model-side fix; the multi-phase trainer + context features (Option 1 of that ADR) are the trainer-side fix. The two are paired.
- [`anomaly_model_v2_improvements.md`](anomaly_model_v2_improvements.md) — earlier iterative improvements to feature engineering. Those carry over unchanged.
- [`anomaly_model_feature_set.md`](anomaly_model_feature_set.md) — the 33-feature set (30 original + 3 context features) the new model will train on.
- [`anomaly_training_zero_pollution.md`](anomaly_training_zero_pollution.md) — the temporal pre-filter that decides which response-time features reach training. Carries over unchanged.

---

## TL;DR

River's `HalfSpaceTrees` was a poor fit for our use case in three compounding ways and we have been paying for that mismatch for weeks. PyOD's `ECOD` (Empirical CDF-based Outlier Detection) directly addresses every one of those mismatches: it's static (no windowing/forgetting), range-agnostic (no `[0, 1]` assumption), and per-feature interpretable (free attribution). We will replace `HalfSpaceTrees` with `ECOD` as the primary screener. Validation is operator-driven on the live stack: train the new model with the multi-phase trainer, run individual high-impact failure scenarios first as smoke tests, then a full batch run; compare per-scenario results against the Apr-28 baseline. If that validation shows ECOD missing multivariate anomalies (features that look fine individually but are unusual in their joint configuration), the documented next step is `COPOD` — same architectural slot as ECOD with the same per-feature interpretability, plus copula-based dependence modeling. `HBOS` and an `ECOD + IForest` ensemble are documented further fallbacks in that order. Deep-learning detectors (`DeepSVDD`, `LSTM`/`TimesNet`) are explicitly rejected for our problem scale and shape; the ADR records why so future contributors don't have to retrace the reasoning.

---

## Context — three things that compounded into the over-flagging problem

The over-flagging documented in [`anomaly_model_overflagging.md`](anomaly_model_overflagging.md) has multiple causes. The trainer-side bias toward "calls active" baseline snapshots is one — Option 1 in that ADR addresses it via context features and a multi-phase trainer. But while implementing Option 1 we surfaced two more issues that are model-side and have nothing to do with training-data shape. All three together explain why retraining produced inconsistent results across batches and why the over-flagging persisted regardless of training duration.

### Issue 1 — wrong tool category for our problem

`river.anomaly.HalfSpaceTrees` is a *streaming, concept-drift* detector. The intended deployment is a production system whose "normal" shifts over time (traffic patterns change, software updates, seasonality), and the model needs to forget old normal so it can track the new normal. The tumbling-window mass-rotation mechanism is the feature that delivers this: every `window_size` samples, the live mass replaces the reference mass and live resets.

Our use case is the opposite. We have a **static lab stack** with a controlled traffic generator and no drift. We want the model to remember every training sample, permanently, so the saved baseline reflects all of it. The river algorithm by design throws this away: scoring uses only `r_mass`, which contains at most one completed window's worth of samples.

Consequence: training duration didn't matter beyond ensuring at least one swap completed. Whether `--duration 600` or `--duration 1800`, the saved model's reference distribution was always "the last `window_size` training samples." That's why retraining produced inconsistent results across batches that we couldn't fully explain — the random-walk traffic generator, combined with last-window-only memory, made the saved model's "normal" essentially a roll of the dice over the final ~4 minutes of training.

### Issue 2 — wrong feature-range assumption

River's `HalfSpaceTrees` builds tree splits inside a per-feature `limits` range, defaulting to `[0, 1]` for every feature unless overridden. We never overrode it. From the river source:

```python
on = rng.choices(population=list(limits.keys()),
                 weights=[limits[i][1] - limits[i][0] for i in limits])[0]
at = rng.uniform(a + padding * (b - a), b - padding * (b - a))
```

So splits are random thresholds in `[0.15, 0.85]` (with default padding) for every feature. Look at the actual feature ranges:

| Feature class | Actual range observed | What `[0, 1]` random splits do |
|---|---|---|
| Cx response times (UAR/LIR/MAR/SAR/CDP) | 0 – 500 ms | Every sample lands above every split. Tree is degenerate for these features. |
| `pcscf_avg_register_time_ms` | 0 – 350 | Same — degenerate. |
| `bearers_per_ue` | 2 – 3.5 | Same. |
| `sessions_per_ue` | ≈ 2.0 | Same. |
| `gtp_*_per_ue` | 0 – 10 | Same — degenerate. |
| Per-UE rates (REGISTER/INVITE) | 0 – 0.5 | Splits only see the bottom half of the range. Tree partly works. |
| Error/timeout ratios | 0 – 1 | Works correctly. |
| Context flags (new) | 0 / 1 | Works correctly. |

About a third of the trained features have been pass-through dead weight in the tree structure for the entire history of the model. Splits on those features can never separate samples — every sample lands on the same side of every split. The model has been effectively learning on a smaller feature subset than we thought.

The river docstring even calls this out: "if this isn't the case, then you can manually specify the limits via the `limits` argument… or use a `preprocessing.MinMaxScaler` as an initial preprocessing step." We did neither.

### Issue 3 — the screener was already half-doing per-feature stats

Look at `screener.py:_attribute_anomalies`:

```python
learned_mean = sum(mean_values) / len(mean_values)
std = statistics.stdev(std_values)
deviation = abs(current_value - learned_mean) / effective_std
if deviation > 1.0:
    candidates.append(...)
```

That's a per-feature z-score detector. The flag list is computed entirely from running mean/stdev maintained outside river (in `_feature_means`). River's overall_score is a gate — "should we even look at flags?" — via the `_RIVER_THRESHOLD = 0.7` cutoff. The flags themselves are statistics, not tree-derived.

So the architecture has been: a per-feature gaussian z-score detector underneath, with river bolted on top as a "should we bother?" gate. Given Issues 1 and 2, that gate has been doing its job poorly — when the last window's reference mass happened to be unrepresentative, the gate fired on perfectly healthy snapshots, producing the over-flagging.

### Combined effect on the diagnostic ceiling

Brittleness across retrains, over-flagging on quiet runtime periods, the pattern that "more training samples make it worse" — these aren't mysteries when you understand the three issues compound. The Apr-23 batch hit 74.7% mean, Apr-24 dropped to 63.0%, Apr-28 recovered only to 65.6% despite shipping the IG and rtpengine fixes. That gap is essentially the over-flagging this ADR is designed to remove.

---

## Why we did not catch this earlier

Honest postmortem: River was selected (per [`anomaly_detection_layer.md`](anomaly_detection_layer.md)) because it was the first credible Python anomaly library encountered, the streaming-incremental API matched the early "just call learn_one in a loop" mental model, and the over-flagging that exposed the design mismatch only became dominant after the ceiling-removal work in IG schemas and the rtpengine sensor swap. It also took two specific findings to make the issues visible: comparing learned σ to KB ranges (which exposed the [0,1] tax), and reading the river source line-by-line to verify the swap mechanic (which exposed the forgetting).

The `screener.py` docstring at the top of the file already names "PyOD ECOD" as a planned secondary detector — so an earlier reasoning thread had identified the right alternative; the implementation just never followed through. The right move would have been to revisit that thread when the over-flagging picture sharpened, rather than going deeper into river-internal patches.

---

## Why PyOD is the right library to pick from

[PyOD](https://github.com/yzhao062/pyod) is the Python anomaly-detection library with the broadest selection of algorithms (40+) under a consistent `.fit() / .decision_function()` API. For a problem like ours — pick the right detector once, train it on a static dataset, save it, score samples against it — PyOD is the obvious starting point. The library does the bulk of "which algorithm is right for which shape of data" survey work for us by collecting the canonical algorithms together with reference implementations.

Properties that match our needs:
- All detectors are batch-fit, not streaming. No windowing, no forgetting.
- Range-agnostic. Detectors don't assume features are in `[0, 1]` (or do their own scaling internally).
- Pickle-friendly. Trained models save and load cleanly.
- Well-tested implementations of canonical algorithms (ECOD, HBOS, IForest, COPOD, LOF, KNN, ABOD, autoencoder variants…).
- Same architectural pattern we already have: train once on healthy data, save the model, load at runtime to score new samples. No conceptual change for downstream code.

It's also lightweight enough to add — depends on numpy, scipy, scikit-learn, and a couple of small extras. We already pull in scikit-learn transitively elsewhere, so the marginal cost is small.

---

## Algorithms considered

| Detector | How it works | Fit for our problem | Verdict |
|---|---|---|---|
| **ECOD** (Empirical Cumulative-distribution Outlier Detection) | Per-feature empirical CDF from training. Anomaly score = sum across features of `-log(min(F(x), 1-F(x)))` — the tail probability. Parameter-free. | Static. Range-agnostic (each feature has its own CDF). Per-feature interpretable — the `model.O` array gives per-feature outlier scores so attribution is free. Handles non-Gaussian shapes (skewed rates, bimodal context flags) correctly because it uses the empirical distribution rather than parametric assumptions. | **Primary choice.** See "Why ECOD" below. |
| **HBOS** (Histogram-Based Outlier Score) | Per-feature histograms from training. Score = sum of `-log(bin_density)` across features. | Same general shape as ECOD but discretized into histogram bins. Slightly faster. Slightly less accurate on tail probabilities because of bin edges. | **Backup if ECOD has issues.** Same interpretability, same range-agnostic behavior. Different enough that a problem with ECOD's CDF construction is unlikely to be shared. |
| **IForest** (Isolation Forest, PyOD wrapper around `sklearn.ensemble.IsolationForest`) | Random binary trees, but split thresholds are picked from the actual data range (not `[0, 1]`). Anomaly score derived from average path length to isolation. | Multivariate detection — catches feature combinations weird in their joint distribution but normal individually. Static fit. Fixes Issue 2 (range mismatch) automatically because sklearn picks split thresholds from observed feature ranges. Per-feature attribution is approximate (sklearn exposes `feature_importances_` but the per-sample story is harder). | **Documented fallback / complement.** Use case: catch multivariate anomalies that ECOD's per-feature view misses. Could ship as a secondary detector running in parallel with ECOD. |
| **COPOD** (Copula-based Outlier Detection) | Like ECOD but uses copulas to model feature dependencies. Per-feature marginals retained (same interpretability shape as ECOD), plus joint tail behavior captured by the copula. | Same per-feature attribution story as ECOD, plus catches the class of anomalies where individual features look fine but their joint configuration is unusual (e.g. "calls active is 1 but GTP-U per-UE is 0" — the "ghost-bearer" pattern). At our 33-feature scale the training cost is still milliseconds. The dependence-modeling adds expressiveness exactly where ECOD-alone might miss multivariate signal. | **Documented second-place backup** (see "Backup options"). Same interpretability properties as ECOD; promotes naturally if ECOD proves insufficient on multivariate anomalies. |
| **LOF** (Local Outlier Factor) | Density-based — score is local-density relative to neighbors. | Distance-based, sensitive to feature scaling, sensitive to which distance metric. Doesn't natively give per-feature attribution. | Reject. Wrong shape for our problem — we want "is this number weird for this metric?", not "is this point in a sparse region of joint space." |
| **KNN** (k-Nearest-Neighbor outlier score) | Score = distance to k-th nearest neighbor in training data. | Distance-based, same problems as LOF. Cubic-ish memory at scoring time (have to keep all training points). | Reject. |
| **OCSVM** (One-Class SVM, sklearn alternative) | Learns a decision boundary around training data. Score = signed distance from boundary. | Multivariate. Hyperparameter-sensitive (kernel, gamma). Hard to interpret. | Reject. IForest covers the multivariate-detection slot more cleanly. |
| **AutoEncoder / VAE** | Neural reconstruction error. | Powerful for high-dimensional data, but our 33-feature problem is small. Training is more involved (network architecture, hyperparameters). | Reject. Disproportionate complexity for the problem size. |
| **DeepSVDD** (Deep Support Vector Data Description) | Maps inputs through a neural network to a learned hypersphere. Anomaly score = distance from sphere center. | Designed for high-dimensional data (hundreds–thousands of features, often images) with thousands–tens of thousands of training samples. Single scalar output, no per-feature attribution. Needs GPU for tractable training. | Reject. **See "Explicitly rejected: deep-learning detectors" below.** |
| **LSTM / TimesNet** (sequence-modeling deep learning) | Recurrent / transformer networks operating on time-series sequences. | Operates on sequence inputs at score time; we score on single multivariate snapshots. Needs long sequences (50–500 steps) and large datasets (thousands of sequences) to train. | Reject. **See "Explicitly rejected: deep-learning detectors" below.** |
| **Custom Gaussian z-score** | What was already half-implemented in `_attribute_anomalies`. Per-feature mean/stdev, score by z-score. | Same shape as ECOD but parametric — assumes features are Gaussian, which several of ours aren't (ratios pile at 0, response times have long right tails, context flags are bimodal). | Reject. ECOD is strictly better — same interpretability, no Gaussian assumption, lives in a battle-tested library rather than our own code. |

---

## Why ECOD specifically

Five reasons:

1. **It is the non-parametric version of what `_attribute_anomalies` was already doing.** Per-feature scoring, attribution falls out of the per-feature components of the model output. The pipeline downstream (NetworkAnalyst reads flag list with severity + KB context) doesn't need to change at all — only the source of the per-feature scores changes, from "running mean + stdev z-score" to "empirical CDF tail probability."

2. **No assumptions about feature distribution shape.** Our features are not Gaussian:
   - Timeout/error ratios pile at 0 (long left tail, rare positive values).
   - Response times have long right tails (most observations clustered, occasional spikes).
   - Per-UE rates are roughly half-Gaussian truncated at 0.
   - Binary context flags are pure 0-or-1 — every parametric model handles these badly.
   ECOD's empirical CDF reads the actual distribution from training data and scores each feature against its own observed shape. Strictly better than parametric assumptions on this dataset.

3. **No tuning.** `ECOD()` takes no hyperparameters worth tuning (only optional ones like `n_jobs`). No `window_size` debate, no threshold selection beyond the score-to-flag cutoff that lives in our code. Eliminates an entire category of "did we configure the detector correctly?" questions.

4. **Solves Issue 2 automatically.** Each feature's CDF is built from that feature's observed values. Cx response time at 73 ms is scored against the empirical distribution of training-time Cx response times, not against a `[0, 1]` assumption. There is no "feature range mismatch" failure mode.

5. **Solves Issue 1 by construction.** ECOD is fit once on the entire training set. There is no streaming/window mechanism to misuse. `screener.finalize_training()` becomes a single `model.fit(X)` call. Saved model represents every training sample, full stop.

---

## Explicitly rejected: deep-learning detectors

Deep-learning anomaly detectors (DeepSVDD, AutoEncoder/VAE, LSTM, TimesNet) come up frequently in any "what's the latest in anomaly detection?" survey, and were considered. They are rejected for our specific problem for reasons that are easy to lose sight of without anchoring to constraints, so we record them explicitly here so future contributors don't have to retrace the reasoning.

### DeepSVDD

Maps inputs through a neural network to a learned hypersphere; anomaly score = distance from sphere center. Rejected on **four** grounds:

1. **"33 features" is not high-dimensional.** DeepSVDD is designed for problems where the input is hundreds to thousands of features (image pixels, sensor arrays, learned embeddings) and dimensionality reduction matters. At 33 features, classical statistical methods consistently outperform deep methods on benchmark anomaly-detection datasets — the literature on this is unambiguous. Recommending DeepSVDD because we have "many correlated features" misreads the scale entirely.
2. **Training data size.** Neural networks need thousands to tens of thousands of samples to learn a meaningful hypersphere boundary without overfitting. Our training runs produce hundreds of samples. The boundary we'd learn would be noisy and strongly dependent on initialization seed.
3. **No per-feature attribution.** DeepSVDD's output is a single distance-from-center scalar. NetworkAnalyst's whole reasoning chain depends on a per-feature flag list with semantic context. To recover attribution we'd have to bolt on SHAP values or feature occlusion analysis at score time — additional code, additional latency, additional failure modes, all to recover what ECOD/COPOD/HBOS give for free.
4. **Hardware.** Practical training requires GPU. Our chaos lab does not have one allocated for training. Without GPU, training time stretches from minutes to hours, breaking the iterate-fast loop we need for validation.

### LSTM / TimesNet (sequence-modeling deep learning)

Recurrent / transformer networks operating on time-series sequences. Rejected on **four** grounds:

1. **Wrong problem shape at score time.** Our screener gets a single multivariate snapshot at score time, not a sequence. The temporal structure that matters is already baked into the feature vector via the sliding-window rate computation in the preprocessor (~30s rolling window for counter rates). Adding LSTM/TimesNet would require rearchitecting the entire score-time path to pass sequences instead of snapshots.
2. **Wrong problem shape at training time.** Sequence models need long input sequences (typically 50–500 time steps per sample) and many sequences (thousands+) to train. Our chaos baseline-collection runs produce ~30–60 snapshots per phase at 5-second polling. Total available sequence material is ~hundreds of snapshots — orders of magnitude short of what these models require.
3. **Wrong fault-onset profile.** The "slow-burn drift over minutes" pattern these models excel at detecting is not how our chaos faults work. Our scenarios use `tc netem`, container kill, iptables rules, and DNS server kill — fast-onset, step-function failures. Slow-burn detection is solving for a use case we don't have.
4. **Slope features beat sequence models for our needs.** If the value of temporal context becomes evident in validation, the cheapest correct intervention is to add per-feature slope features (e.g. "linear-fit slope of metric X over the last 5 samples") to the preprocessor. This captures the temporal-trend signal at the cost of three lines of code per feature, without rearchitecting the screener or shipping a deep-learning training pipeline.

### General principle

Deep-learning methods are appropriate when the problem has high dimensionality, non-tabular structure (images/text/sequences), abundant training data, and either no need for interpretability or established attribution tooling. Our problem has *none* of those properties. The "more sophisticated = better" reflex that pushes deep learning as the default is wrong for the problem in front of us. ECOD/COPOD/HBOS/IForest are the right scale of tool for the right scale of problem.

---

## Backup options if ECOD does not perform

We will not commit to ECOD blindly. The validation step (live training + smoke-test on individual high-impact scenarios + full batch run, see implementation plan step 5) decides whether ECOD's flag set on real scenarios matches operational reality. If it doesn't, the fallback options in priority order:

### Backup 1 — COPOD

Same architectural slot as ECOD: per-feature interpretable, range-agnostic, parameter-free, batch-fit. Adds copula-based dependence modeling on top of the per-feature CDFs, so the score reflects both per-feature tail probability AND joint distribution behavior.

When to switch: if ECOD's flag set is reasonable on per-feature anomalies but misses the class of issues where features look individually fine but their joint configuration is unusual. Examples in our context:
- `calls_active=1` AND `gtp_indatapktn3upf_per_ue=0` simultaneously — each value is in-range on its own but the combination is impossible in healthy operation.
- `dialogs_per_ue` non-zero AND all RTP-engine activity at zero — a "ghost dialog" pattern where signaling state remains but media doesn't flow.

These are real diagnostic signals we'd want, and ECOD's per-feature design cannot represent them. COPOD gives us that capability without sacrificing the per-feature attribution NetworkAnalyst already depends on.

Implementation cost is essentially zero — `from pyod.models.copod import COPOD` and reuse the same wrapper code as ECOD. Validation step is the same.

### Backup 2 — HBOS

Per-feature histogram-based outlier scoring. Same architecture as ECOD but with a different math kernel — bin densities instead of empirical CDF tail probabilities.

When to switch: if both ECOD and COPOD have a shared failure mode rooted in per-feature CDF construction (e.g. features with very narrow training distributions where `1 - F(x)` saturates near zero, making small deviations look extreme). HBOS uses histogram bins which behave differently at the tails. Same drop-in swap pattern.

### Backup 3 — ECOD + IForest as a 2-of-2 ensemble

Run ECOD as the primary scorer, IForest in parallel for a multivariate cross-check. A flag fires only when both agree the value is anomalous, raising precision at the cost of recall.

When to switch: only if (a) we still see false positives after trying ECOD then COPOD, AND (b) we have evidence we're missing real multivariate anomalies that COPOD's copula-based detection didn't catch. The "two detectors must agree" story is more complex for downstream consumers (NetworkAnalyst), so this is a measured last-line option rather than an early try.

### Backup 4 — pure IForest

Drop ECOD/COPOD entirely, use IForest as the sole detector. We lose natural per-feature attribution; flag attribution would require a separate post-hoc analysis (SHAP values or per-feature contribution to isolation path length).

When to switch: only if every interpretable detector above produces patently wrong flag sets in the live-validation runs. This is the "the per-feature story is broken in our data" escape hatch and we don't expect to need it.

---

## How state-conditioning fits in (relationship to Option 1 of `anomaly_model_overflagging.md`)

The 3 binary context features (`context.calls_active`, `context.registration_in_progress`, `context.cx_active`) and the multi-phase trainer that produces balanced training data across operational states — both of those are **independent of which detector we use**. They sit in the preprocessor and the trainer respectively, both of which are unchanged by this ADR.

Two ways to use them with ECOD:

1. **Single ECOD, context features as input columns.** Train one ECOD on the full 33-feature training set. ECOD's per-feature CDFs include the binary context columns. At score time, runtime samples carry their context bits, get scored. Per-feature score on `context.calls_active=0` against an empirical CDF that's roughly 50/50 means a "0" reading is unsurprising; per-feature score on a value that's bimodal won't help at all though, because a 50/50 CDF puts every reading in the middle of the distribution.

2. **Multiple ECODs, one per context state bucket.** Partition training data by `(calls_active, registration_in_progress)` → 4 state buckets. Fit one ECOD per bucket. At score time, route by current context. Each ECOD scores against an empirical distribution conditioned on that operational state — exactly the conditional reasoning we want.

Option (2) is what the conditional-reasoning argument in [`anomaly_model_overflagging.md`](anomaly_model_overflagging.md) requires. Option (1) is simpler but doesn't actually deliver state-conditioning — the binary context columns don't help ECOD reason conditionally because ECOD scores each column independently. **Implementation will use option (2).**

This implies the multi-phase trainer must produce comparable sample counts in each of the 4 state buckets (≥ 30 samples per bucket is the working threshold) so each per-bucket ECOD has enough training data. The phased trainer already targets this with B → C → D → E rotation; the implementation just needs to count samples per bucket and warn / abort if any bucket is under-trained.

---

## Risks and known limitations

1. **Per-bucket ECODs may have very few training samples per bucket** if the phased trainer's phase durations are short relative to a feature's natural variability. With `phase_duration=150s` and 5-second polling we get ~30 samples per bucket per cycle. ECOD's empirical CDF is computed pointwise over the training data — 30 samples is the bare minimum for the tail-probability calculations to be meaningful. Plan: 2 cycles minimum (60 samples per bucket); 3-4 cycles for headroom.

2. **The 4 state buckets are not equally interesting.** `(calls_active=0, registration_in_progress=0)` (Phase C — idle-registered) is the dominant runtime state in chaos scenarios where everything has gone quiet. It will be the bucket that fires most often during scoring. We should make sure that bucket gets the most training samples, or at least that it's not the smallest.

3. **Adding PyOD as a dependency.** Modest — pulls in numpy, scipy, scikit-learn, and a few small extras. We already import scikit-learn transitively. Net new disk footprint ~10–20 MB. Acceptable but should be declared in `requirements.txt` so future contributors see the dependency explicitly.

4. **Existing `model.pkl` becomes incompatible.** Same as any other model rewrite. Must be regenerated on next training run. Backup-on-save (already shipped as part of the Option-1 work) preserves the previous model for comparison.

5. **The `_RIVER_THRESHOLD = 0.7` overall-anomaly cutoff goes away.** ECOD's scores have a different scale and distribution. We'll need a new cutoff, derived from the validation step rather than picked a priori. Specifically: score the training data with the trained ECOD, look at the distribution of scores, pick a percentile (e.g. 99th) as the runtime flag cutoff. This is mechanical but can't be done in advance — it depends on the trained model.

6. **Multi-state routing at score time can fail if the runtime context features carry a value that didn't appear in any training bucket** (e.g. a context combination none of the 4 phases produced). Mitigation: fall back to a default bucket (probably `C — idle-registered`) and log a warning. Should be impossible if the multi-phase trainer is doing its job, but worth a guard.

---

## Implementation plan

Sequenced so each step produces a testable artifact and the previous step is revert-safe.

1. **Add PyOD to dependencies.** New entry in `anomaly_trainer/requirements.txt` (or top-level if there's one). Verify the venv builds.

2. **Replace the `AnomalyScreener` internals.**
   - Constructor: replace `river_anomaly.HalfSpaceTrees(...)` with a dict-of-state-bucket-keyed `pyod.models.ecod.ECOD()` instances (4 buckets). Keep the `learn / score / finalize_training / feature_keys / training_samples` API surface.
   - `learn()`: route the sample to the bucket determined by its context flags, accumulate in that bucket's training matrix.
   - `finalize_training()`: call `.fit(X)` on each bucket's accumulated training matrix. Set `self._fitted = True`. Replaces the manual mass-rotation we were considering.
   - `score()`: route the runtime sample to its bucket, call `model.decision_function([x])[0]` for the overall score, read `model.O[0]` for per-feature scores, build the same `AnomalyReport` shape as today.
   - `_RIVER_THRESHOLD` becomes `_OVERALL_ANOMALY_THRESHOLD`, derived from the trained model's training-set score distribution (computed at finalize time and stored on the screener).

3. **Update tests.** The existing tests that exercised `screener.score()` and the report-rendering remain; they don't depend on river internals. The save-coverage guard test continues to work — it reads `screener.feature_keys`, which still derives from `_feature_means`. Add new tests:
   - Per-bucket fit happens correctly given a mock training stream.
   - Per-bucket scoring routes runtime samples by context flags.
   - `finalize_training()` is idempotent.
   - A bucket with zero training samples raises a clear error rather than silently scoring everything as 0.

4. **Update the trainer's context-coverage gate.** It currently checks the running mean of each context feature is in `[0.15, 0.85]`. After this change it should additionally check that each of the 4 (calls × registration) buckets received at least N training samples (working threshold: 60 = 2 phase cycles).

5. **Train and validate on the live stack.** Operator-driven validation against the actual chaos pipeline rather than offline replay against saved snapshots. The latter would have been faster to iterate on but exercises only the screener in isolation; the live path tests the whole system as it operates and gives a directly comparable score against prior batches. Sequence:
   1. Train the new model on a clean stack via `python -m anomaly_trainer --duration 1200 --mode phased`. Confirm the existing context-coverage gate passes (each of the 4 state buckets received ≥ 60 samples). The previous on-disk model is preserved automatically by the backup-on-save logic (see `anomaly_trainer/persistence.py`) so a comparison baseline is always available.
   2. Smoke-test on individual high-impact scenarios first to catch obvious issues before paying for a full batch run. Recommended scenarios in priority order:
      - `dns_failure` — regressed 100% → 25% on Apr-28; the most striking case of over-flagging-driven misattribution. If ECOD doesn't recover this, ECOD alone is not sufficient.
      - `data_plane_degradation` — Apr-28 score 21%. The Cx-response-time over-flagging shape that made NA blame HSS instead of UPF.
      - `ims_network_partition` — Apr-28 score 36%. Tests the Phase 0 narrative when calls torn down across multiple components simultaneously.
      - `call_quality_degradation` — Apr-28 score 90%. Real-fault regression check; any drop here means the new model is masking real anomalies.
   3. Run the full batch against the same 11 scenarios as Apr-28. Compare per-scenario score deltas (not just the mean). Acceptance signal:
      - Contextual scenarios above (`dns_failure`, `data_plane_degradation`, `ims_network_partition`, `cascading_ims_failure`) move by ≥ 30 score points each in the right direction.
      - 100% scenarios stay at 100% (or above ~85% within batch-to-batch noise).
      - Mean across the 11 scenarios reaches at least mid-80s; 90s if the implementation is solid.
   4. Operator runs the scenarios and the batch; analysis happens together post-run. The trainer output (context-coverage gate, per-bucket sample counts), per-scenario agent logs, and final batch summary are the inputs to that analysis.

6. **Decide on ECOD vs backup.** Based on (5), confirm ECOD is the right primary or fall back to COPOD, HBOS, or the ECOD + IForest ensemble as documented in "Backup options if ECOD does not perform" above. The ranking specifically anticipates the failure mode where ECOD recovers per-feature anomalies but misses joint-distribution ones — that's the COPOD case.

7. **Update related ADRs.**
   - `anomaly_detection_layer.md` — supersede the "Algorithm: River HalfSpaceTrees" section with a pointer to this ADR.
   - `anomaly_model_overflagging.md` — note that Option 1's "Three model-architecture options" table is now superseded by the ECOD direction; the multi-phase trainer + context features parts of Option 1 carry over unchanged.

8. **Tear out river.** Remove `from river import anomaly` and the river dependency from requirements after the new screener is shipped and validated.

The work is roughly: ~150 lines of screener replacement, ~100 lines of new tests, ~30 lines of trainer guard updates, validation step, ADR updates. About a day of focused work plus the validation run.

---

## Open questions

1. **Single-ECOD-with-context-columns vs per-bucket ECODs.** This ADR commits to per-bucket. If the per-bucket sample counts turn out too low to fit good CDFs (Risk 1 above), we may have to fall back to single-ECOD plus an explicit per-feature suppression rule for state-conditional features. Decide based on validation results.

2. **Single-detector cascade vs ensemble.** Is the single-detector path (ECOD → COPOD on miss → HBOS on miss → ensemble as last resort) the right shape, or should we run two interpretable detectors in parallel from day one? Argument for cascade: simpler downstream story (one flag list, one source of truth), each detector validated independently, easy to revert. Argument against: a single missed multivariate fault during validation would force a full re-validation cycle on the ensemble. Plan: ship ECOD-only first, validate, switch to COPOD if ECOD's miss pattern is multivariate-shaped, fall through to HBOS or ensemble only if both interpretable per-feature options fail.

3. **Cutoff calibration cadence.** How often do we re-derive `_OVERALL_ANOMALY_THRESHOLD`? Once per retrain seems right; the alternative ("re-derive on every batch run from the runtime score distribution") would adapt to drift but introduces feedback we don't want in a static lab stack.

4. **Deprecation of the river-related ADR sections.** Specifically, the "Algorithm choice: River HalfSpaceTrees" reasoning in `anomaly_detection_layer.md` should be either rewritten or marked as "historical context, superseded by `anomaly_detector_replace_river_with_pyod.md`." Choosing language so future readers don't have to retrace this entire reasoning trail to understand why we made the decision.
