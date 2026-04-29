# ADR: Anomaly Model Over-Flagging on Healthy-Range Metrics

**Date:** 2026-04-27 (updated 2026-04-28 with Apr-28 batch evidence; re-framed 2026-04-28 after Option A scoping work)
**Status:** Direction agreed — Option 1 (context features in the same model) plus a scoped KB-bound override for Cx response times only. See "Update 2026-04-28: re-framing the fix space" below. Options A/B/C above are retained as historical context but superseded.
**Related:**
- [`anomaly_detection_layer.md`](anomaly_detection_layer.md) — the original choice of River HalfSpaceTrees as the screener.
- [`anomaly_model_feature_set.md`](anomaly_model_feature_set.md) — the 30-feature set the model is trained on.
- [`anomaly_training_zero_pollution.md`](anomaly_training_zero_pollution.md) — the temporal pre-filter that decides which response-time features even reach training.
- [`anomaly_model_v2_improvements.md`](anomaly_model_v2_improvements.md) — earlier iterative improvements to the model.

---

## The problem in one sentence

The trained anomaly model flags **healthy-range readings of multiple feature classes** (Cx response times, per-UE GTP-U rates, derived activity gauges) as deviations. The LLM agents read those flags as semantic observations and write hypotheses centered on the wrongly-flagged NF, which lands diagnoses on the wrong component on at least 4 of 11 scenarios per batch and puts a hard ceiling on the system's possible accuracy.

## Direct evidence — 2026-04-24 batch run

From the Phase 0 output of the `call_quality_degradation` scenario, where the actual fault was 30% tc-injected packet loss on the rtpengine container (HSS and Cx were not involved):

| Feature | Runtime reading | Learned model baseline | Model flag | KB-documented healthy range |
|---|---|---|---|---|
| `icscf.ims_icscf:uar_avg_response_time` | 73 ms | 62.50 ms | HIGH, shift | 30–100 ms |
| `icscf.cdp:average_response_time` | 75 ms | 61.05 ms | HIGH, shift | 30–100 ms |
| `icscf.ims_icscf:lir_avg_response_time` | 80 ms | 58.57 ms | HIGH, shift | 30–100 ms |
| `scscf.ims_registrar_scscf:sar_avg_response_time` | 113 ms | 108.62 ms | HIGH, shift | 50–150 ms |

Every reading is inside the KB's documented healthy range. None indicates a real fault. The model flagged all four as anomalous because they sit outside the *learned* distribution from training.

A second example from the same run: `derived.upf_activity_during_calls` reading 1.00 was flagged HIGH "spike" vs baseline 0.09. But 1.00 is the healthy default value this feature returns when no call is active — `min(1.0, ...)` clamps healthy/idle states to 1.0 by design. The model learned 0.09 because most training snapshots happened during active calls; runtime saw an idle moment and flagged it as a fault.

## Direct evidence — 2026-04-28 batch run (broader pattern emerges)

The Apr-28 batch (run on a 104-snapshot retrain — looser than Apr-24's 209-snapshot model) confirmed and **expanded** the bug class. Over-flagging now demonstrably affects four distinct feature families, not just Cx response times. Three regressed scenarios from this batch all show the same shape: model flags fire on metrics whose absolute values are healthy, NA reads them as fault signatures, diagnosis lands on the wrong NF.

### `data_plane_degradation` 17 → **21%** (real fault: 30% packet loss on UPF)

Top flags from Phase 0:

| Feature | Runtime | Baseline | Flag | Domain reading |
|---|---|---|---|---|
| `scscf.ims_auth:mar_avg_response_time` | 104 ms | 126 ms | **HIGH, shift** | inside healthy range |
| `icscf.ims_icscf:lir_avg_response_time` | 24 ms | 63 ms | **HIGH, drop** | low end of healthy |
| `icscf.cdp:average_response_time` | 51 ms | 64 ms | MEDIUM, shift | inside healthy range |
| `derived.pcscf_avg_register_time_ms` | 87 ms | 155 ms | MEDIUM, shift | low end of healthy |
| `normalized.upf.gtp_indatapktn3upf_per_ue` | 0.14 pps | 3.44 pps | MEDIUM, drop | calls didn't establish |
| `normalized.upf.gtp_outdatapktn3upf_per_ue` | 0.23 pps | 3.37 pps | MEDIUM, drop | calls didn't establish |
| `derived.upf_activity_during_calls` | 1.00 | 0.45 | LOW, spike | **idle default** |
| `normalized.pcscf.dialogs_per_ue` | 0.00 | 0.59 | LOW, drop | no calls |

NA wrote h1 = "HSS Diameter interface overloaded preventing LIR/MAR processing." That's wrong — the actual fault is UPF packet loss. NA was led there by the cluster of Cx flags + the (correct) GTP-U drop flags being mis-attributed to "data-plane downstream of HSS failure." Score: 21%.

### `ims_network_partition` 20 → **36%** (real fault: P-CSCF ↔ I/S-CSCF iptables partition)

| Feature | Runtime | Baseline | Flag | Domain reading |
|---|---|---|---|---|
| `derived.pcscf_avg_register_time_ms` | 0.00 ms | 155 ms | HIGH, drop | no REGISTERs being processed (correct → fault is P-CSCF) |
| `normalized.upf.gtp_outdatapktn3upf_per_ue` | 0.15 pps | 3.37 pps | MEDIUM, drop | no calls flowing |
| `normalized.upf.gtp_indatapktn3upf_per_ue` | 0.10 pps | 3.44 pps | MEDIUM, drop | no calls flowing |
| `normalized.smf.bearers_per_ue` | 4.00 | 2.59 | MEDIUM, spike | bearer state from before partition |
| `derived.upf_activity_during_calls` | 1.00 | 0.45 | LOW, spike | **idle default** |
| `normalized.pcscf.dialogs_per_ue` | 0.00 | 0.59 | LOW, drop | calls torn down |

NA wrote h1 = "PCF is incorrectly rejecting Rx requests, starving P-CSCF." Wrong — the actual fault is the network partition between P-CSCF and the rest of IMS. Even with the correct P-CSCF register-time → 0 signal in front of NA, the noise from UPF/idle-default flags pulled the diagnosis toward PCF. Score: 36%.

### `dns_failure` 100 → **25%** — the dramatic regression

| Feature | Runtime | Baseline | Flag | Domain reading |
|---|---|---|---|---|
| `normalized.upf.gtp_outdatapktn3upf_per_ue` | 0.03 pps | 3.37 pps | MEDIUM, drop | no calls |
| `normalized.upf.gtp_indatapktn3upf_per_ue` | 0.12 pps | 3.44 pps | MEDIUM, drop | no calls |
| `normalized.pcscf.dialogs_per_ue` | 0.00 | 0.59 | LOW, drop | no calls |
| `derived.upf_activity_during_calls` | 1.00 | 0.45 | LOW, spike | **idle default** |

The DNS server itself has **zero metrics in the trained feature set**. When DNS goes down, IMS hostname resolution fails → no REGISTERs reach P-CSCF → no calls established → no GTP-U → silence everywhere downstream. NA sees the silence and concludes "user data plane fault — UPF / SMF / N3 path." DNS isn't even considered as a hypothesis. Score: 25% — was 100% on Apr-23, on the same scenario, against a model with a different healthy-distribution training.

This is a **category-defining example**: the over-flagging combined with the absence of any DNS-direct feature in the model meant the only signal NA could see was the side-effect downstream of DNS failure, and the model's interpretation of that side-effect was wrong.

### Summary of the Apr-28 evidence

The bug class is broader than Cx response times. Confirmed over-flagging on:

1. **Cx response times** (UAR, LIR, MAR, SAR, CDP) — original case, still firing on multiple scenarios.
2. **`derived.pcscf_avg_register_time_ms`** — drops to 0 when no REGISTERs are flowing; flagged HIGH "drop" even when 0 is the correct healthy reading for an idle period.
3. **`normalized.upf.gtp_indatapktn3upf_per_ue` / `_out`** — drops to ~0 when calls don't establish; flagged MEDIUM "drop" even when the underlying fault is upstream (signaling, DNS) rather than at the UPF.
4. **`normalized.pcscf.dialogs_per_ue`** — drops to 0 when calls torn down; flagged LOW "drop" indistinguishably from a real dialog-management failure.
5. **`derived.upf_activity_during_calls`** — fixed at 1.00 during idle (this is the feature's healthy default), training had baseline 0.45 (mostly active-call snapshots), so idle flags as "spike." This appeared in **every regressed scenario above**.

**The unifying root cause is broader than "the model's distribution is too narrow."** It's that the **training-time distribution is biased toward "calls active"** (because the trainer's traffic generator places calls during baseline collection), so any runtime period where calls aren't active — for any reason — looks anomalous on a half-dozen features simultaneously. Combined with the algorithm's lack of an absolute-threshold safety net, this creates spurious Phase 0 narratives that NA cannot distinguish from real faults.

This batch made the impact concrete: **mean dropped to 65.6%**, and 4 of the 5 misses trace directly to over-flagging-driven misattribution. Without addressing this, the system has a structural ceiling around 65–75%.

## How the current model decides the "normal range"

The screener uses **River's HalfSpaceTrees** ([`anomaly_detection_layer.md`](anomaly_detection_layer.md)) — a streaming-friendly variant of Isolation Forest. Its mechanism, in plain terms:

1. **Build a forest of random binary trees.** Each tree splits feature space by picking a random feature and a random threshold within the observed range. After enough samples, each tree has many splits encoding the regions where training data fell.

2. **Anomaly score by tree-traversal depth.** A new sample is dropped down each tree. Samples that land in deeply-traversed paths (because the splits saw many similar samples there during training) get low anomaly scores. Samples that land in shallow paths (no training data was there to refine the splits) get high scores.

3. **The "normal range" is implicit in the splits.** There is no explicit `min`/`max` bound stored anywhere. The algorithm infers normality from where training samples clustered. A 10ms wide cluster (e.g. UAR observed at 60±5 ms during training) makes anything 70+ms look anomalous — even though domain truth says 30–100 ms is fine.

4. **More training samples narrow the inferred normal range.** Each new training sample refines splits in regions of feature space it touches, sharpening the model's idea of where "training data lives." With 102 samples (Apr-22 model), the learned bands were looser. With 209 samples (Apr-24 retrain), they tightened — which is what worsened the over-flagging on the Apr-24 batch. **More training is exactly the wrong remedy** for this failure mode.

5. **The KB's documented healthy range is not used by the model.** `metrics.yaml` declares `healthy.typical_range: [30, 100]` for `icscf.cdp:average_response_time`. The screener doesn't consult this. The screener only knows what it learned from the 209 healthy training snapshots, all of which happened to be in the 55–65 ms band.

This is a fundamental shape-mismatch between **what the algorithm is good at** (detecting deviations from learned distributions) and **what the operational problem requires** (deciding whether a reading is in the *domain-meaningful* healthy band).

## Downstream consequence — why this matters for diagnosis quality

The anomaly screener's flags feed Phase 0 of the v6 pipeline. NetworkAnalyst (Phase 3) reads the flags as authoritative semantic observations and writes hypotheses around them. When the screener fires on multiple healthy-range or quiet-period readings, NA has no machinery to distinguish "real fault here" from "side-effect-of-fault-elsewhere" or "training distribution didn't span this state." It treats every flagged feature as evidence of a problem at the flagged NF.

### Apr-24 batch (initial evidence)
- `call_quality_degradation` (real fault: rtpengine packet loss) → NA blamed HSS — score 5%
- `cascading_ims_failure` (real fault: pyhss + scscf compound) → NA blamed P-CSCF, contaminated by Cx flags — score 40% (was 100% on Apr-23 with the looser model)
- `ims_network_partition` (real fault: P-CSCF↔I/S-CSCF iptables partition) → NA blamed SMF/N4 — score 20%

### Apr-28 batch (confirmed and broadened)
- `data_plane_degradation` (real fault: UPF packet loss) → NA blamed HSS Diameter overload — score 21%
- `ims_network_partition` (real fault: P-CSCF partition) → NA blamed PCF Rx connection failures — score 36%
- `dns_failure` (real fault: DNS server down) → NA blamed UPF/SMF/N3 — score **25%** (down from 100%)
- `cascading_ims_failure` → NA blamed P-CSCF — score 50%

### Magnitude of the impact

Across two batches, the over-flagging-driven misattribution accounts for **roughly 30–50 score points per affected scenario** and affects **4 of 11 scenarios consistently**. That puts a structural ceiling around 65–75% on the system's batch mean, regardless of how good the rest of the pipeline becomes. Two pieces of evidence make this stark:

1. **`dns_failure` going from 100% → 25%** in less than a week, with no prompt or causal-chain regression in between — the model's interpretation of side-effect signals dragged the entire diagnosis off course.
2. **The retrained model with fewer samples (104 vs 209) didn't help** — the over-flagging persisted because the bias toward "calls-active" training snapshots is inherent to how the trainer generates baseline data, not just to sample count.

## Fix options

Three approaches, in increasing order of work and architectural impact:

### Option A — Wider tolerance via KB healthy ranges (preferred starting point)

Augment the screener so a feature is flagged only when it falls **outside the KB-documented `healthy.typical_range`**, not just outside the learned distribution. Implementation sketch:

- After the screener computes its per-feature anomaly score, do a second pass that checks each candidate flag against `metric_kb`'s `healthy.typical_range`.
- If the runtime value is inside that range, suppress the flag regardless of the model's score.
- If the metric has no documented range (e.g., a derived ratio), fall back to the model's verdict.

Pros: minimally invasive. Uses the domain knowledge we already have. Doesn't replace the learning algorithm. Each affected metric has its KB range vetted by an operator who knows the stack.

Cons: depends on `metric_kb` having accurate ranges for every feature. For some derived metrics (`upf_activity_during_calls`, `pcscf_avg_register_time_ms`), the "healthy range" is harder to pin down a priori. A miscalibrated KB range silently masks real faults.

Effort: small, ~50–100 lines.

### Option B — Different algorithm with explicit per-feature thresholds

Replace HalfSpaceTrees with a residual-based detector that tracks per-feature mean and standard deviation, flagging only when the value exceeds N×σ AND the absolute value exceeds an absolute threshold derived from the KB.

Pros: more interpretable. Naturally honors domain ranges. Per-feature attribution is mechanically correct.

Cons: gives up the multivariate aspect — HalfSpaceTrees catches anomalies that come from feature *combinations* the residual approach won't. May miss subtle correlated failures.

Effort: medium, several hundred lines + retraining + validation.

### Option C — Hybrid: HalfSpaceTrees for structure, KB for thresholds

Keep HalfSpaceTrees as one of two screeners. Add a parallel KB-bound check (Option A's logic, standalone). A flag fires only when both agree the value is anomalous. Conversely, surfacing semantically requires only the KB-bound to be loud — the multivariate signal is for "interesting clusters of deviation," the KB-bound is for "this number is outside the operationally-acceptable band."

Pros: doesn't lose the multivariate strength. Adds the explicit-threshold safety net.

Cons: more code, more cases. Fan-in logic for "when does a flag fire?" is fiddly.

Effort: large.

## Update 2026-04-28: re-framing the fix space

Options A/B/C above frame the problem as "the model is right, layer suppression on top." That framing missed something: **the model is unconditional.** It treats every snapshot as IID and has no representation of operational state. So when the system goes idle (no calls, no registrations) — for whatever reason — the model sees a region of feature space it rarely encountered during training (the trainer biases toward calls-active, ADR question #3 above) and flags multiple features as deviations simultaneously.

A scoped attempt at Option A was implemented and reverted. What we learned in the process:

1. **Many KB `typical_range` declarations are LLM-priors, not measurements of this stack.** The original `baselines.yaml` was hand-authored as "expected metric values when the stack is healthy with 2 UEs registered and 0–1 active VoNR calls"; many ranges (e.g., `[0, 0.5]` REGISTERs/UE/s, `[0, 0.2]` INVITEs/UE/s) are round-number engineering ceilings reflecting general IMS literature, not anything measured against this lab.

2. **Comparing the KB ranges to the trained model's learned distribution shows they often disagree by 5-20×.** For example, `rcv_requests_register_per_ue` has KB range `[0, 0.5]` but learned mean = 0.06 ± 0.06 (range 0–0.21). A genuine spike to 0.3 — which the model would correctly flag — would be silently suppressed by an Option-A-style override because 0.3 ∈ `[0, 0.5]`. The KB ceiling masks real anomalies.

3. **For the 8 `[0, 0]` timeout/error ratio features, the suppression rule is pure redundancy.** Learned σ = 0; the model already won't flag values near zero, so the KB override fires only on values the model wouldn't have flagged anyway.

4. **The contextual features (rows 9, 23, 29, 30 in the Apr-28 summary table) need conditional reasoning, not blanket range checks.** `dialogs_per_ue=0` is healthy when calls are idle and anomalous mid-call. A scalar range cannot express that.

The cleaner direction is to teach the model itself about operational state.

### Three model-architecture options

| | Approach | What changes | Effort |
|---|---|---|---|
| **1** | Context features in the same HalfSpaceTrees model | Add 3-4 binary context features (`calls_active`, `registration_in_progress`, `cx_active`) to the existing 30-feature vector. Trees split on these naturally, encoding regions like "calls_active=0 ∧ gtp=0 → dense (healthy)" vs "calls_active=1 ∧ gtp=0 → rare (anomalous)." No score-time rules; conditional is in tree structure. | Small — preprocessor (~30 lines) + multi-phase trainer (~50 lines) + retrain |
| **2** | Per-state submodels | One HalfSpaceTrees instance per operational state. At score time, classify state, route to matching submodel. Mathematically equivalent to Option 1 for tree-based detectors but with explicit rather than implicit splits. | Medium — adds state classifier, per-state model files, routing logic |
| **3** | Bayesian / probabilistic graphical model | Learn `P(metric_i \| other_metrics, state)` directly. Captures conditional distributions explicitly; gives calibrated probabilities. | Large — significant rewrite |

### Why Option 1 alone is not enough — the Cx response time exception

Option 1 fixes the **contextual** over-flagging classes — rows 2–5 of the Apr-28 evidence summary (drops to ~0 when calls/registrations not active). It does **not** fix the Cx response time within-band drift documented in row 1 of the Apr-24 evidence and the Apr-28 `data_plane_degradation` row (UAR=73 vs learned 62; MAR=104 vs learned 126; LIR=24 vs learned 63). For those, `cx_active=1` in both training and at score time — the issue is the learned cluster being narrower than the KB band, not context-dependence.

Two ways to address this class specifically:

- **(a) Driver-side fix:** training must exercise Cx response times under varying load (response-time jitter, longer training runs spanning the natural variance, multiple traffic-intensity phases). This is the architecturally "right" answer but requires chaos-framework infrastructure work.
- **(b) Operator-side fix:** re-introduce the KB-bound override **scoped to the 6 Cx response time features only**, where (i) the KB band is grounded in IMS/Diameter operational reality (30-100 ms for direct Cx hops, 50-150 ms for Cx+HSS), and (ii) the trained model has demonstrably narrower clusters than the KB band. Unlike the per-UE rate features, the Cx KB ranges reflect actual Diameter timing characteristics that don't materially differ between this lab and a production stack — so suppressing flags inside `[30, 100]` will not mask real faults; real Cx faults manifest as values outside this band (timeouts, hundreds of ms).

Recommended: ship Option 1 first, measure on the offline replay set, then decide whether (a) or (b) is also needed for the Cx response time class. If the over-flagging on Cx response times persists after Option 1, fall back to (b) as a narrow, well-justified override on 6 features only.

### Implementation plan for Option 1

1. **Preprocessor** (`agentic_ops_common/anomaly/preprocessor.py`): add 3 derived context features to the feature dict.
   - `context.calls_active` = `1.0 if pcscf.dialog_ng:active > 0 else 0.0`
   - `context.registration_in_progress` = `1.0 if rates['pcscf.script:register_attempts'] > 0 else 0.0`
   - `context.cx_active` = `1.0 if any(rates[icscf.<uar/lir/cdp>:replies_received] > 0) else 0.0`
   - Adds 3 entries to `EXPECTED_FEATURE_KEYS` (30 → 33). ~30 lines + unit tests.

2. **Multi-phase training script** (chaos framework): rotate the stack through 5 operational phases during baseline collection, ≥30 samples per phase.
   - Phase A: idle stack (no UEs, no traffic) — `calls_active=0, reg=0, cx=0`
   - Phase B: registration burst (UEs registering, no calls) — `calls_active=0, reg=1, cx=1`
   - Phase C: idle-registered (UEs registered, quiet) — `calls_active=0, reg=0, cx=0` (different metric profile from A — counters non-zero, dialogs_per_ue still 0)
   - Phase D: active call (1-2 UEs in call) — `calls_active=1, reg=0, cx=0`
   - Phase E: call + register (call active, new UE registering) — `calls_active=1, reg=1, cx=1`
   - ~50 lines + an ADR update describing the phased training protocol.

3. **Retrain.** Inspect `_feature_means['context.calls_active']` and similar — the running mean across training samples should be ~0.4-0.6, not stuck at 0 or 1. If stuck, training did not span both states, and the trees won't split on it.

4. **Validate against the Apr-24 and Apr-28 saved snapshots.** Replay each scenario through the new model, count flags by category. Acceptance criteria:
   - Contextual flag classes (rows 2-5 of the Apr-28 evidence) drop to near-zero false positives.
   - Real-fault detection on `call_quality_degradation` (rtpengine packet loss) and similar 100% scenarios is preserved.
   - Cx response time drift (row 1) may remain — that's expected, decision deferred to step 5.

5. **Decide on Cx response time class.** If over-flagging on Cx response times persists after Option 1, ship a narrow KB-bound override scoped to the 6 Cx response time features only:
   - `derived.pcscf_avg_register_time_ms` (range [150, 350])
   - `icscf.cdp:average_response_time` (range [30, 100])
   - `icscf.ims_icscf:uar_avg_response_time` (range [30, 100])
   - `icscf.ims_icscf:lir_avg_response_time` (range [30, 100])
   - `scscf.ims_auth:mar_avg_response_time` (range [50, 150])
   - `scscf.ims_registrar_scscf:sar_avg_response_time` (range [50, 150])

   Implementation reuses the reverted `suppress_in_range_flags` shape, but gated on a hard-coded allowlist of these 6 KB IDs. ~30 lines + tests.

6. **DNS-direct features** (orthogonal to model architecture, bundled into the same work package): add `dns_query_response_time_ms` and `dns_query_failures_per_second` to the preprocessor + KB. Without these, no model architecture can diagnose `dns_failure` correctly — currently DNS is invisible in the feature set, which is why `dns_failure` regressed 100% → 25%.

### Note on the reverted Option A code

A working implementation of `suppress_in_range_flags` was added to `agentic_ops_common/metric_kb/flag_enrichment.py` and wired into `agentic_ops_v6/orchestrator.py`, then reverted after the analysis above. The function shape is good; if step 5 above lands as a scoped re-introduction, the reverted code is in git history (look for the commit between `7dc3837` and the Option-1 work) and can be restored with the addition of an allowlist filter.

## Open questions for the work package

1. **Coverage of `healthy.typical_range` in `metric_kb` today.** How many of the 30 trained features have a non-empty `typical_range`? If most do, Option A is straightforward. If many don't, Option A starts with an authoring pass. (Survey to be run as part of the work package.)

2. **What about features whose "healthy" depends on context?** `derived.upf_activity_during_calls = 1.00` is healthy when no call is active AND when a call is active and UPF is forwarding properly. The same value means different things depending on whether `pcscf.dialogs_per_ue > 0`. A pure scalar `typical_range` can't capture this. Options: (a) declare a context-conditioned range in metric_kb, (b) suppress the flag whenever `pcscf.dialogs_per_ue == 0` (idle suppression), (c) accept the false positive as noise and rely on NA to discount it — but the Apr-28 evidence shows NA cannot discount it reliably.

3. **The training-distribution-bias root cause.** Independent of Option A, the trainer's traffic generator produces baseline snapshots that are biased toward "calls active" — because it's literally placing calls during baseline collection. This means every per-call activity feature has a learned baseline closer to "active" than "average across realistic traffic mix." Two ways to fix at the trainer side: (a) include extended idle periods in the baseline run, (b) post-process training samples to compute separate active-call and idle-period distributions, with the screener picking the right one based on `dialogs_per_ue`. Even after a screener-side fix, this trainer-side bias deserves attention.

4. **DNS-class faults need direct features.** `dns_failure` going from 100→25% revealed that the DNS server has zero metrics in the trained feature set — the screener can only see DNS failure indirectly via downstream silence on UPF/dialogs, which is exactly the over-flagged territory. Even after fixing over-flagging, DNS will be hard to diagnose without at least one DNS-direct feature (e.g., `dns_query_response_time`, `dns_query_failures_per_second`). This is a separate authoring item but it bundles with the same work package.

5. **Validation methodology.** To pick a winner among A/B/C, we need a test set of "known-healthy" snapshots and "known-faulty" snapshots, then measure precision and recall of each option. We now have ≥ 22 saved chaos episodes (Apr-22 / Apr-23 / Apr-24 / Apr-28 batches) with ground-truth labels — almost certainly enough.

6. **Magnitude vs. shape signals.** HalfSpaceTrees is good at detecting that "this feature combination is unlike anything in training." That's a real diagnostic signal — sometimes a value individually within range is anomalous because it conflicts with another feature. Do we need to preserve that, or is per-feature checking enough for our scenarios? Strong evidence so far that the multivariate signal isn't worth the false-positive cost we're paying for it.

7. **Healthy-distribution drift.** Production stacks evolve — new subscribers, traffic shape changes, software upgrades. A purely KB-bounded approach is robust to drift; a learning-only approach suffers. Where do we want to land on this axis given that this stack runs in a lab and not a real production network?

8. **Calibration cadence.** If we keep any learning component, what triggers a retrain? Quarterly? On config change? Only manually? The Apr-24 retrain made the over-flagging *worse*, so default-to-retrain is a footgun.

## Provisional next steps (subject to scoping)

The original list (1-6 below) was written before the Apr-28 analysis re-framed the problem. Items 1, 2, and 4 are still relevant; items 3, 5, 6 are superseded by the Option 1 plan in "Update 2026-04-28: re-framing the fix space" above.

1. **Survey** the 30 trained features and tabulate which have `healthy.typical_range` declared in `metric_kb`. Note features where the range is context-dependent (per question 2 above). — **Done** as `docs/ADR/model_feature_range_survey.md`.
2. **Build offline replay harness** using saved Apr-24 and Apr-28 anomaly snapshots. Feed each through (a) current model, (b) candidate model variants from the Option 1 plan. Compare flag sets and Phase 0 narratives. — **Still needed**, will use this to validate Option 1.
3. ~~Address `derived.upf_activity_during_calls` first~~ — **superseded**. Idle suppression on this single feature is a special case of what Option 1's `calls_active` context feature handles uniformly.
4. **Add DNS-direct features to the KB** alongside the screener fixes. Without them, no amount of screener tuning will let the agent diagnose DNS failure correctly. — **Still needed**, bundled into the Option 1 work package as step 6.
5. ~~Pick the smallest Option A/B/C variant~~ — **superseded**. The new direction is Option 1 (model-architecture change) with a scoped Cx-only KB-bound override as a fallback if Option 1 doesn't fully address Cx response time drift.
6. ~~Re-evaluate trainer traffic shape~~ — **superseded**. The multi-phase training script in step 2 of the Option 1 plan is the trainer-shape fix; it is no longer optional.

## Why this is now the priority

(Originally written 2026-04-27 as: "Why this isn't a blocker for tomorrow's batch run.")

The Apr-28 batch invalidated my prior framing. The IG empty-output fix and rtpengine sensor swap **both shipped successfully** — verified by `tool_calls ≥ 1` on every IG run this batch and `call_quality_degradation` jumping from 5% → 90%. With those two ceilings removed, the remaining ceiling is over-flagging, and it's worth more than I credited it for: ~30 points across 4 scenarios in a batch of 11.

The system mean was 74.7% on Apr-23, dropped to 63.0% on Apr-24, recovered only to 65.6% on Apr-28 despite the IG and rtpengine fixes. That gap is essentially all over-flagging. **This is now the dominant unfixed problem.** Pre-empting any further prompt/sensor work to attack this directly is justified.
