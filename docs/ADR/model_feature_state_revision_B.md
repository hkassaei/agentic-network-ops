# Anomaly Model — Current State (Revision B)

**Date:** 2026-05-10
**Status:** Current. Supersedes [Revision A (2026-04-28)](model_feature_state_revision_A.md).
**Related:**
- [Revision A](model_feature_state_revision_A.md) — the prior survey, scoped to support a `typical_range`-based flag-suppression override (Option A in the parent ADR). Preserved for historical context.
- [`anomaly_model_overflagging.md`](anomaly_model_overflagging.md) — parent ADR. Resolved direction: **Option 1** (state-bucketing via context features) plus a scoped Cx-only KB-bound override as the deferred fallback.
- [`anomaly_detector_replace_river_with_pyod.md`](anomaly_detector_replace_river_with_pyod.md) — the river HalfSpaceTrees → PyOD ECOD migration that landed alongside state-bucketing.
- [`anomaly_training_zero_pollution.md`](anomaly_training_zero_pollution.md) — the temporal pre-filter at training and score time for response-time / register-time features.
- [`path_anchored_probe_planning_for_transport_layer_faults.md`](path_anchored_probe_planning_for_transport_layer_faults.md) — adds the `fault_layer` KB label that drives v7's transport-vs-application-layer routing downstream of the screener.

---

## Purpose

A current-state description of the anomaly model that fronts the v7 diagnostic pipeline. Aimed at: someone arriving fresh and needing to understand what the screener flags, why, and what gets handed to the LLM agents downstream. Strictly current shape — no history beyond what's needed to ground a reference.

## Architecture in one diagram

```
        Raw per-NF metrics                         Healthy-baseline
        (counters + gauges)                        training corpus
              │                                    (multi-phase replay
              ▼                                     across 4 op states)
   ┌─────────────────────────┐                            │
   │   MetricPreprocessor    │ ─────────────►  AnomalyScreener.learn()
   │  rates, ratios, per-UE  │                            │
   │  normalization,         │                            ▼
   │  derived composites,    │                  finalize_training()
   │  binary context flags,  │                            │
   │  liveness signals       │              ┌─────────────┴─────────────┐
   └─────────────────────────┘              ▼                           ▼
              │                  bucket(0,0)  bucket(0,1)  bucket(1,0)  bucket(1,1)
              │                  ECOD model   ECOD model   ECOD model   ECOD model
              │                  threshold    threshold    threshold    threshold
              ▼                       │           │            │            │
   AnomalyScreener.score(features, liveness)      │            │            │
              │                                   │            │            │
   bucket key = (context.calls_active, context.registration_in_progress)
              │                                                │
              ▼                                                ▼
        Route to matching bucket's ECOD ─────►  decision_function() →
              │                                  overall + per-feature scores
              ▼                                                │
        score < threshold? ── yes ──► AnomalyReport(flags=[])  │
              │                                                │
              no                                               │
              ▼                                                │
        AnomalyReport(                                         │
          flags=top-K per-feature outliers,                   ◄┘
          overall_score, threshold, bucket,
          training_samples, model_ready,
        )
              │                                            ┌─►  Phase 0.5
              ▼                                            │    Symptom Classifier
   metric_kb.flag_enrichment.enrich_report(report, kb)     │    (reads kb_context
              │                                            │     .fault_layer)
              ▼                                            │
   AnomalyReport with each AnomalyFlag.kb_context populated├─►  Phase 0
              │                                            │    NA prompt
              └──── handed to v7 orchestrator state ───────┘    rendering
```

## Algorithm

**PyOD ECOD** — Empirical Cumulative Distribution-based Outlier Detection. Replaced river HalfSpaceTrees on 2026-04-28. ECOD computes per-feature tail probabilities from the empirical CDF of the training distribution; the per-sample anomaly score is the sum of `-log(tail_prob)` across features. Two consequences worth flagging:

- **Per-feature attribution falls out of the math.** ECOD's `model.O[-1]` after `decision_function()` is a per-feature outlier-score row for the inference sample. The screener sorts that and picks top-K to attribute as flags — no auxiliary attribution heuristic.
- **Static training, not streaming.** Every training sample is permanently retained until `finalize_training()`. The river tumbling-window forgetting that previously caused brittleness across retrains is gone.

## State-bucketing (the load-bearing design choice)

The screener fits **four** ECOD models, one per operational state, keyed on a binary `(calls_active, registration_in_progress)` tuple:

| Bucket | calls_active | registration_in_progress | Operational state |
|---|---|---|---|
| `(0, 0)` | no | no | idle-registered (steady state) |
| `(0, 1)` | no | yes | registration burst, no call |
| `(1, 0)` | yes | no | active call, no signaling |
| `(1, 1)` | yes | yes | call + concurrent register |

The bucket key is computed by `_bucket_key_for(features)` from two of the three `context.*` features the preprocessor emits (the third, `cx_active`, is highly correlated with `registration_in_progress` and would fragment training data without adding distinct conditional regions if used as a third bucket axis). Each bucket has:

- Its own ECOD model fit on its own slice of the training corpus.
- Its own runtime anomaly cutoff, derived as the 99th percentile of that bucket's training-score distribution.
- A minimum-samples gate (`_MIN_BUCKET_SAMPLES = 30`); buckets below the gate stay unfit and runtime samples routed to them fall back to `(0, 0)`.

This is what closed the over-flagging problem Revision A was scoping. A "quiet GTP rate" is healthy in `(0, 0)` and anomalous in `(1, 0)`; the bucketed model treats them as different distributions instead of averaging them into one cluster that's wrong for both.

## Feature set — 33 features

The preprocessor emits 33 features per snapshot in a locked order. `EXPECTED_FEATURE_KEYS` (in `agentic_ops_common/anomaly/preprocessor.py`) is the source of truth.

### Category 1 — Passthrough gauges (6 features)

Read directly from the metric snapshot, no per-UE normalization. All have `typical_range` and reach the KB cleanly.

| Feature | KB id | typical_range | fault_layer |
|---|---|---|---|
| `rtpengine.errors_per_second_(total)` | `ims.rtpengine.errors_per_second` | `[0, 0]` | application |
| `icscf.cdp:average_response_time` | `ims.icscf.cdp_avg_response_time` | `[30, 100]` | mixed |
| `icscf.ims_icscf:uar_avg_response_time` | `ims.icscf.uar_avg_response_time` | `[30, 100]` | mixed |
| `icscf.ims_icscf:lir_avg_response_time` | `ims.icscf.lir_avg_response_time` | `[30, 100]` | mixed |
| `scscf.ims_auth:mar_avg_response_time` | `ims.scscf.mar_avg_response_time` | `[50, 150]` | mixed |
| `scscf.ims_registrar_scscf:sar_avg_response_time` | `ims.scscf.sar_avg_response_time` | `[50, 150]` | mixed |

The five Cx response-time gauges plus the rtpengine error gauge. All five Cx gauges go through the temporal pre-filter (next section).

### Category 2 — Error ratios (8 features)

Scale-independent ratios in `[0, 1]`. Computed by the preprocessor from rate-counter pairs.

| Feature | KB id | typical_range | fault_layer |
|---|---|---|---|
| `derived.icscf_uar_timeout_ratio` | `ims.icscf.uar_timeout_ratio` | `[0, 0]` | mixed |
| `derived.icscf_lir_timeout_ratio` | `ims.icscf.lir_timeout_ratio` | `[0, 0]` | mixed |
| `derived.icscf_sip_error_ratio` | `ims.icscf.sip_error_ratio` | `[0, 0]` | application |
| `derived.scscf_mar_timeout_ratio` | `ims.scscf.mar_timeout_ratio` | `[0, 0]` | mixed |
| `derived.scscf_sar_timeout_ratio` | `ims.scscf.sar_timeout_ratio` | `[0, 0]` | mixed |
| `derived.scscf_sip_error_ratio` | `ims.scscf.sip_error_ratio` | `[0, 0]` | application |
| `derived.scscf_registration_reject_ratio` | `ims.scscf.registration_reject_ratio` | `[0, 0]` | application |
| `derived.pcscf_sip_error_ratio` | `ims.pcscf.sip_error_ratio` | `[0, 0]` | application |

P-CSCF's HTTP client failure ratio is intentionally excluded — the SCP timeouts on Rx AAR have a baseline ~84% failure rate in this deployment that masks real faults.

### Category 3 — Per-UE normalized rates (13 features)

Sliding-window rates divided by the active UE count, which makes the feature scale-independent across small/large user populations.

| Feature | KB id | typical_range | fault_layer |
|---|---|---|---|
| `normalized.icscf.core:rcv_requests_register_per_ue` | `ims.icscf.rcv_requests_register_per_ue` | `[0, 0.5]` | mixed |
| `normalized.icscf.core:rcv_requests_invite_per_ue` | `ims.icscf.rcv_requests_invite_per_ue` | `[0, 0.2]` | mixed |
| `normalized.pcscf.core:rcv_requests_register_per_ue` | `ims.pcscf.rcv_requests_register_per_ue` | `[0, 0.5]` | mixed |
| `normalized.pcscf.core:rcv_requests_invite_per_ue` | `ims.pcscf.rcv_requests_invite_per_ue` | `[0, 0.2]` | mixed |
| `normalized.scscf.core:rcv_requests_register_per_ue` | `ims.scscf.rcv_requests_register_per_ue` | `[0, 0.5]` | mixed |
| `normalized.scscf.core:rcv_requests_invite_per_ue` | `ims.scscf.rcv_requests_invite_per_ue` | `[0, 0.2]` | mixed |
| `normalized.icscf.cdp_replies_per_ue` | `ims.icscf.cdp_replies_per_ue` | `[0, 1.0]` | mixed |
| `normalized.scscf.cdp_replies_per_ue` | `ims.scscf.cdp_replies_per_ue` | `[0, 1.0]` | mixed |
| `normalized.upf.gtp_indatapktn3upf_per_ue` | `core.upf.gtp_indatapktn3upf_per_ue` | `[0, 10]` | transport |
| `normalized.upf.gtp_outdatapktn3upf_per_ue` | `core.upf.gtp_outdatapktn3upf_per_ue` | `[0, 10]` | transport |
| `normalized.smf.sessions_per_ue` | `core.smf.sessions_per_ue` | `[1.9, 2.1]` | application |
| `normalized.smf.bearers_per_ue` | `core.smf.bearers_per_ue` | `[2, 3.5]` | application |
| `normalized.pcscf.dialogs_per_ue` | `ims.pcscf.dialogs_per_ue` | `[0, 1.0]` | mixed |

### Category 4 — Derived composite / temporal (3 features)

Composites built across NFs or against time gates.

| Feature | KB id | typical_range | fault_layer |
|---|---|---|---|
| `derived.upf_activity_during_calls` | `core.upf.activity_during_calls` | `[0.3, 1.0]` | transport |
| `derived.pcscf_avg_register_time_ms` | `ims.pcscf.avg_register_time_ms` | `[150, 350]` | mixed |
| `derived.rtpengine_loss_ratio` | `ims.rtpengine.loss_ratio` | `[0, 0.1]` | transport |

### Category 5 — Operational context (3 features, binary 0/1)

These are the bucket-axis features. NOT mapped to the metric KB; they are gating signals consumed by `_bucket_key_for()` and never themselves flagged.

| Feature | Computed from | What it means |
|---|---|---|
| `context.calls_active` | `pcscf.dialog_ng:active > 0` | At least one SIP dialog is active right now. |
| `context.registration_in_progress` | rate of `pcscf.core:rcv_requests_register > 0` | A REGISTER was processed in the last sliding-rate window (~30s). |
| `context.cx_active` | rate of any of 6 Cx reply counters > 0 | Some Cx Diameter response was received in the last window — strict superset of the per-counter gates used by the temporal pre-filter. |

## KB integration

Every metric feature reaches the KB cleanly: `map_preprocessor_key_to_kb()` resolves all 30 metric features to entries that exist and carry a `typical_range`. The four authoring gaps Revision A flagged (`lir_timeout_ratio`, `sar_timeout_ratio`, both `cdp_replies_per_ue`) are filled. The `upf_activity_during_calls` mapper bug is resolved (KB key was renamed from `upf_activity_during_calls` to `activity_during_calls`).

`typical_range` is consumed at **two** points downstream of the screener:

1. **Flag enrichment (`metric_kb.flag_enrichment.enrich_report`).** After scoring, each `AnomalyFlag` gets a `kb_context: FlagKBContext` attached carrying `display_name`, `unit`, `what_it_signals`, `direction_meaning`, `typical_range`, `invariant`, `pre_existing_noise`. The downstream LLM prompts read this so the agent sees a deviation as a *semantic observation*, not a number.
2. **Prompt rendering (`screener._render_flag`).** When `to_prompt_text()` formats a flag for the NetworkAnalyst's prompt, the typical range is rendered as "Healthy typical range: lo–hi unit" so the operator-facing view always shows the band.

`typical_range` is **not** used at flag time to suppress firing (the Option A path Revision A scoped). State-bucketing carries the over-flagging fix; the KB-bound override remains scoped as a deferred fallback for the Cx response-time class only (per the parent ADR's "Decide on Cx response time class" step).

`fault_layer` (added by the v7 transport-layer ADR) is a separate KB label — `transport | application | mixed` — that drives v7's Phase 0.5 SymptomClassifier routing. Every metric in the KB carries a value. It's not consumed by the screener itself; the screener attaches `kb_context` to flags, the classifier reads `entry.fault_layer` per flag and buckets the report.

## Liveness signals

The preprocessor maintains a `_liveness: dict[str, bool]` populated during `process()`. A feature is "live" if its underlying counter advanced in at least one of the last `_LIVENESS_LOOKBACK_WINDOWS = 2` snapshot pairs. Liveness is consumed by `AnomalyScreener.score(features, liveness=...)` for the silent-failure severity escalation rule.

Two distinct sources of liveness in the current code:

- **Temporal features** (Cx response times + `derived.pcscf_avg_register_time_ms`). The preprocessor *omits* the feature from the snapshot when the gating counter didn't advance — i.e., applies the same filter at score time that `anomaly_training_zero_pollution.md` applies at training time. When the feature IS emitted, its liveness is set `True`.
- **Per-UE rate features** (Category 3). Liveness is computed independently of whether the feature is emitted, by checking the last N snapshot pairs. Used so that a rate that drops to 0 *despite* recent activity gets escalated to HIGH severity rather than flagged at whatever the per-feature ECOD score happens to say.

## Silent-failure severity escalation

After ECOD's per-feature score is binned into HIGH / MEDIUM / LOW, one rule can override:

> If a flagged feature's `current == 0` AND its `liveness == True` AND its `learned_mean > floor` (where the floor is `_MIN_ACTIVE_MEAN_TIME_MS = 10ms` for response-time features and `_MIN_ACTIVE_MEAN_RATE = 0.01` for rate features), force severity to HIGH.

The intent is to surface "this subsystem was just doing things and now its signal is exactly zero" cases that ECOD scoring alone would under-rank — the per-feature outlier score for a zero-reading depends on how much of the training distribution sat at zero, which is noisy for sparsely-observed features. The liveness gate prevents the escalation from firing on "feature is still asleep" cases.

## Flag attribution

When `score()` finds the bucket-level overall score above its threshold, it walks ECOD's per-feature outlier-score row and picks the top `_TOP_K_FLAGS = 10` by score. For each picked feature it emits an `AnomalyFlag`:

```python
@dataclass
class AnomalyFlag:
    metric: str             # e.g. "ims_icscf:uar_avg_response_time"
    component: str          # e.g. "icscf"  (split on first "." of the feature key)
    current: float          # rounded to 4 dp
    learned_normal: float   # cross-bucket mean for that feature
    anomaly_score: float    # ECOD per-feature outlier score, rounded to 3 dp
    severity: str           # HIGH | MEDIUM | LOW (post silent-failure escalation)
    direction: str          # spike | drop | shift  (vs cross-bucket mean)
    kb_context: Optional[FlagKBContext] = None  # populated by enrich_report()
```

Direction is decided by comparing `current` to the cross-bucket learned mean: `>1.5x` → spike, `<0.5x` → drop, mean-zero with current-positive → spike, otherwise → shift. Note the comparison is against the *cross-bucket* mean, not the per-bucket mean — this is deliberate, the cross-bucket value gives a comparable baseline regardless of which bucket the runtime sample landed in.

## Output: `AnomalyReport`

```python
@dataclass
class AnomalyReport:
    flags: list[AnomalyFlag]                 # top-K, severity-sorted
    overall_score: float                     # ECOD bucket score for this sample
    threshold: float                         # the bucket's runtime cutoff
    training_samples: int                    # total across all buckets
    model_ready: bool                        # gates downstream consumption
    bucket: Optional[tuple[int, int]]        # which (calls, reg) bucket scored
```

`to_prompt_text()` renders this as a semantic block per flag (with KB context inlined when enriched), suitable for direct injection into the NA prompt. `to_dict_list()` serializes the flags for state passing to v7's orchestrator.

## Downstream consumers

| Consumer | What it reads | What it does |
|---|---|---|
| v7 orchestrator Phase 0 | `report.to_prompt_text()` | renders into the NA / IG / Investigator prompts as the "## Anomaly Screener" section |
| v7 orchestrator Phase 0.5 (Symptom Classifier) | `flag.kb_context.kb_metric_id` → KB → `fault_layer` | classifies each flag into transport / application / mixed; aggregates into a route label |
| v7 orchestrator Phase 0.6 (Path Resolver) | `flag.kb_context.kb_metric_id` (parsed back to `(nf, metric)`) | picks load-bearing flow + hop list; drives the path walker |
| Episode recorder | `to_dict_list()` | persists flags into the episode markdown / JSON |

## Reproduction snippet

The script that audits typical_range coverage and KB-mapping cleanliness against the live state:

```python
from pathlib import Path
from agentic_ops_common.metric_kb.loader import load_kb
from agentic_ops_common.metric_kb.feature_mapping import map_preprocessor_key_to_kb
from agentic_ops_common.anomaly.preprocessor import EXPECTED_FEATURE_KEYS

kb = load_kb(Path("network_ontology/data/metrics.yaml"))

for fkey in sorted(EXPECTED_FEATURE_KEYS):
    kb_id = map_preprocessor_key_to_kb(fkey)
    if not kb_id:
        # Expected for the 3 context.* features.
        print(f"{fkey:<55} (context feature, no KB mapping)")
        continue
    parts = kb_id.split(".")
    nf, metric = parts[1], ".".join(parts[2:])
    nf_block = kb.metrics.get(nf)
    entry = nf_block.metrics.get(metric) if nf_block else None
    tr = entry.healthy.typical_range if entry and entry.healthy else None
    fl = entry.fault_layer.value if entry and entry.fault_layer else None
    print(f"{fkey:<55} {kb_id:<45} typical_range={tr} fault_layer={fl}")
```

Diff against this document's tables to spot drift after future edits.

## Open work

- **Cx response-time KB-bound override (deferred from the parent ADR).** The 6 Cx response-time gauges in Category 1 had a residual within-band drift problem under state-bucketing alone (e.g. UAR=73 vs learned 62; both inside the `[30, 100]` healthy band but flagged as HIGH-shift by ECOD because the learned cluster was narrower than the band). The parent ADR specifies a scoped Option-A-style override for these 6 features only as the deferred fallback. Status: not implemented; revisit after sufficient post-bucketing replay evidence accumulates.
- **DNS-direct features.** Not currently in the feature set. Without them the agent cannot directly diagnose DNS-failure scenarios from screener output. Step 6 of the parent ADR's Option-1 work package; status: tracked, not yet landed.

## Side observations worth flagging

- **Ten of the 30 metric features have `typical_range = [0, 0]`** — the four timeout ratios, three SIP error ratios, registration-reject ratio, rtpengine errors-per-second, plus the two newly-authored timeout-ratio peers. For this set the KB-bound check is trivially decisive ("any non-zero value is by definition outside the band"); ECOD's empirical-CDF scoring is essentially redundant. Useful evidence for any future "do we need the multivariate model at all on this subset?" discussion.
- **The 3 context features make the ECOD model conditional, not multi-class.** They live in the same feature vector as the metric features. Bucketing happens at training time (separate models per bucket key) and at score time (route to matching bucket), but ECOD never sees `context.*` as a feature within a bucket — they're sliced on, not modelled. The feature vector ECOD trains on inside any one bucket has 30 dimensions, not 33.
