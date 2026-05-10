# ADR Companion: Anomaly Model Feature Range Survey (Revision A)

**Date:** 2026-04-28
**Status:** **Superseded by [Revision B](model_feature_state_revision_B.md) (2026-05-10).** This document is preserved for historical context; its operational recommendations are obsolete. The over-flagging problem this survey was scoped to address was eventually solved via state-bucketing (Option 1 in the parent ADR), not via the KB-bound `typical_range` override (Option A) this survey was supporting. Counts, the missing-KB-entry list, and the mapper-bug entry are all out of date — see Revision B for current state.
**Related:**
- **[Revision B](model_feature_state_revision_B.md)** — current-state description of the anomaly model and feature set as of 2026-05-10.
- [`anomaly_model_overflagging.md`](anomaly_model_overflagging.md) — the parent ADR this survey supports. Lists "Survey the 30 trained features and tabulate which have `healthy.typical_range`" as provisional next-step #1.
- [`anomaly_model_feature_set.md`](anomaly_model_feature_set.md) — the feature reference being surveyed.
- [`anomaly_detection_layer.md`](anomaly_detection_layer.md) — the screener whose flag logic Option A would augment.

---

## Purpose

The over-flagging ADR proposes Option A — augment the anomaly screener so a feature is flagged only when its value is **outside** the KB-documented `healthy.typical_range`, not just outside the model's learned distribution. That option is only viable if `metric_kb` actually has a usable `typical_range` declared for most trained features. This survey audits coverage and identifies the gaps that need closing before Option A can ship.

## Methodology

For each of the 30 features in `MetricPreprocessor.EXPECTED_FEATURE_KEYS`:

1. Map the preprocessor key to its `metric_kb` id using `agentic_ops_common.metric_kb.feature_mapping.map_preprocessor_key_to_kb`.
2. Look up the entry in the loaded KB (`load_kb()` from `network_ontology/data/metrics.yaml`).
3. Read `entry.healthy.typical_range`.
4. Cross-check whether the feature is context-dependent (the same numerical value can be healthy or unhealthy depending on a runtime condition).

The script that produced this survey is reproducible — see "Reproducing this survey" at the end.

## Top-line counts

| Status | Count | Notes |
|---|---:|---|
| Has `typical_range`, KB lookup clean | **24** / 30 | Drop-in candidates for Option A, of which 8 are context-dependent |
| Has `typical_range` but field-mapper produces wrong path | **1** / 30 | `upf_activity_during_calls` (mapper bug) — context-dependent too |
| Mapped to KB but `typical_range` not declared | **0** / 30 | Good — no half-authored entries |
| Not mapped to a KB entry at all (authoring gap) | **4** / 30 | Real missing entries |
| Context-dependent (range alone insufficient) | **9** / 30 | Includes overlap with the above |

## Full table

| # | Feature | KB id | typical_range | Issue |
|---|---|---|---|---|
| 1 | `derived.icscf_uar_timeout_ratio` | `ims.icscf.uar_timeout_ratio` | [0, 0] | — |
| 2 | `derived.icscf_lir_timeout_ratio` | `ims.icscf.lir_timeout_ratio` | — | **MISSING from KB** |
| 3 | `derived.icscf_sip_error_ratio` | `ims.icscf.sip_error_ratio` | [0, 0] | — |
| 4 | `derived.scscf_mar_timeout_ratio` | `ims.scscf.mar_timeout_ratio` | [0, 0] | — |
| 5 | `derived.scscf_sar_timeout_ratio` | `ims.scscf.sar_timeout_ratio` | — | **MISSING from KB** |
| 6 | `derived.scscf_registration_reject_ratio` | `ims.scscf.registration_reject_ratio` | [0, 0] | — |
| 7 | `derived.scscf_sip_error_ratio` | `ims.scscf.sip_error_ratio` | [0, 0] | — |
| 8 | `derived.pcscf_sip_error_ratio` | `ims.pcscf.sip_error_ratio` | [0, 0] | — |
| 9 | `derived.upf_activity_during_calls` | `core.upf.upf_activity_during_calls` | [0.3, 1.0] | **mapper bug** (double-prefix mismatch) + **context-dep** |
| 10 | `derived.pcscf_avg_register_time_ms` | `ims.pcscf.avg_register_time_ms` | [150, 350] | **context-dep** (only valid when REGISTER counter advances) |
| 11 | `derived.rtpengine_loss_ratio` | `ims.rtpengine.loss_ratio` | [0, 0.1] | — (just shipped 2026-04-27) |
| 12 | `icscf.cdp:average_response_time` | `ims.icscf.cdp_avg_response_time` | [30, 100] | **context-dep** (only valid when Cx active) |
| 13 | `icscf.ims_icscf:uar_avg_response_time` | `ims.icscf.uar_avg_response_time` | [30, 100] | **context-dep** |
| 14 | `icscf.ims_icscf:lir_avg_response_time` | `ims.icscf.lir_avg_response_time` | [30, 100] | **context-dep** |
| 15 | `scscf.ims_auth:mar_avg_response_time` | `ims.scscf.mar_avg_response_time` | [50, 150] | **context-dep** |
| 16 | `scscf.ims_registrar_scscf:sar_avg_response_time` | `ims.scscf.sar_avg_response_time` | [50, 150] | **context-dep** |
| 17 | `rtpengine.errors_per_second_(total)` | `ims.rtpengine.errors_per_second` | [0, 0] | — |
| 18 | `normalized.icscf.core:rcv_requests_register_per_ue` | `ims.icscf.rcv_requests_register_per_ue` | [0, 0.5] | — |
| 19 | `normalized.icscf.core:rcv_requests_invite_per_ue` | `ims.icscf.rcv_requests_invite_per_ue` | [0, 0.2] | — |
| 20 | `normalized.icscf.cdp_replies_per_ue` | `ims.icscf.cdp_replies_per_ue` | — | **MISSING from KB** |
| 21 | `normalized.pcscf.core:rcv_requests_register_per_ue` | `ims.pcscf.rcv_requests_register_per_ue` | [0, 0.5] | — |
| 22 | `normalized.pcscf.core:rcv_requests_invite_per_ue` | `ims.pcscf.rcv_requests_invite_per_ue` | [0, 0.2] | — |
| 23 | `normalized.pcscf.dialogs_per_ue` | `ims.pcscf.dialogs_per_ue` | [0, 1] | **context-dep** (drop to 0 is healthy idle, unhealthy mid-call) |
| 24 | `normalized.scscf.core:rcv_requests_register_per_ue` | `ims.scscf.rcv_requests_register_per_ue` | [0, 0.5] | — |
| 25 | `normalized.scscf.core:rcv_requests_invite_per_ue` | `ims.scscf.rcv_requests_invite_per_ue` | [0, 0.2] | — |
| 26 | `normalized.scscf.cdp_replies_per_ue` | `ims.scscf.cdp_replies_per_ue` | — | **MISSING from KB** |
| 27 | `normalized.smf.sessions_per_ue` | `core.smf.sessions_per_ue` | [1.9, 2.1] | — |
| 28 | `normalized.smf.bearers_per_ue` | `core.smf.bearers_per_ue` | [2, 3.5] | — |
| 29 | `normalized.upf.gtp_indatapktn3upf_per_ue` | `core.upf.gtp_indatapktn3upf_per_ue` | [0, 10] | **context-dep** (drop to 0 is healthy idle, unhealthy mid-call) |
| 30 | `normalized.upf.gtp_outdatapktn3upf_per_ue` | `core.upf.gtp_outdatapktn3upf_per_ue` | [0, 10] | **context-dep** |

---

## Three buckets of work to act on

### Bucket 1 — drop-in wins (16 features)

Rows 1, 3, 4, 6, 7, 8, 11, 17, 18, 19, 21, 22, 24, 25, 27, 28.

These have well-defined `typical_range`, are NOT context-dependent, and are exactly where Option A (KB-bound override at the screener) gets immediate effect with no further authoring or design.

- **Eight have `[0, 0]` ranges** — timeout ratios, SIP error ratios, RTPEngine errors-per-second. "Healthy means exactly zero." Any non-zero reading is, by definition, outside the range; the screener should flag and the KB-bound check is decisive.
- **Five have small per-UE rate ranges** — REGISTER/INVITE per UE at I/P/S-CSCF. Tight but with non-zero room.
- **Two SMF steady-state features** — sessions/bearers per UE. Narrow ranges around the configured topology values (2 sessions, 2–3 bearers).
- **One ratio-with-room feature** — `rtpengine_loss_ratio` at [0, 0.1].

All trivially benefit from a "if value ∈ typical_range, suppress flag" rule. No further design needed.

### Bucket 2 — context-dependent (9 features) — the heart of the over-flagging problem

Rows 9, 10, 12–16, 23, 29, 30.

Range alone doesn't tell you whether the reading is healthy. Three sub-patterns to address:

#### 2A — Per-event meaningful, per-snapshot meaningless

Rows 10, 12, 13, 14, 15, 16. The Cx response-time gauges (`uar/lir/cdp/mar/sar avg_response_time`) plus `pcscf_avg_register_time_ms`. A reading of 0 ms is "no events in the last window" — could be perfectly healthy idle OR a real fault. There's already a pre-filter at TRAINING time that skips these when the underlying counter didn't advance (per [`anomaly_training_zero_pollution.md`](anomaly_training_zero_pollution.md)) but the screener at SCORE time has no equivalent suppression. The fix is symmetric: at score time, if the gating counter (`cdp:replies_received`, `script:register_success`, etc.) didn't advance in the window, the response-time feature is N/A and should be excluded from anomaly attribution.

#### 2B — Healthy means activity

Rows 9, 23, 29, 30. `dialogs_per_ue`, `gtp_indatapktn3upf_per_ue`, `gtp_outdatapktn3upf_per_ue`, `upf_activity_during_calls`. These should be > 0 during a call but legitimately 0 (or 1.0 in `upf_activity`'s case) during idle. The Apr-28 batch showed all four firing simultaneously on `dns_failure`, `ims_network_partition`, and `data_plane_degradation` — because in those scenarios calls didn't establish, traffic went quiet, and the model flagged the silence as anomalous. The fix: a context gate based on a "calls active" indicator (e.g., `pcscf.dialog_ng:active > 0` from raw metrics) suppresses drop-flags on these when no calls are expected.

#### 2C — The `upf_activity_during_calls` mapper bug

Row 9. The KB entry exists at `core.upf.upf_activity_during_calls` (key duplicates the NF prefix). The field-mapper in `feature_mapping.py` strips `upf_` because it identifies the NF prefix and removes it, producing `core.upf.activity_during_calls` — which doesn't match. Trivial one-line fix: either rename the metric_kb key to `activity_during_calls` (consistent with peer metrics) or special-case the mapper. Renaming is cleaner because every other UPF metric in the KB doesn't double-prefix.

### Bucket 3 — missing KB entries (4 features)

Rows 2, 5, 20, 26.

| Missing KB entry | Effort | Rationale |
|---|---|---|
| `ims.icscf.lir_timeout_ratio` | trivial | Peer of `uar_timeout_ratio` (already authored with `[0, 0]` range). Healthy = 0 timeouts. |
| `ims.scscf.sar_timeout_ratio` | trivial | Peer of `mar_timeout_ratio`. Healthy = 0. |
| `ims.icscf.cdp_replies_per_ue` | small | Per-UE Diameter reply rate at I-CSCF. Range needs determination from a healthy run; likely `[0, ~0.5]` similar to the other Cx per-UE rates. |
| `ims.scscf.cdp_replies_per_ue` | small | Per-UE Diameter reply rate at S-CSCF. Same as above. |

The first two are pure authoring oversights with obvious fills. The latter two need a quick measurement on a healthy stack to pick the upper bound. ~30 minutes of authoring total.

---

## Recommended sequence for the work package

1. **Fix the mapper bug for `upf_activity_during_calls`** (trivial, one-line). Unblocks Bucket 1's coverage to 17 features.
2. **Add KB entries for the 4 missing features** (Bucket 3). After this, every trained feature has a KB-mapped `typical_range` declared.
3. **Implement Option A — KB-bound override** at the screener. Simple "value within range = suppress flag" rule. Immediately benefits the 17 non-context-dependent features. Measurable improvement on its own.
4. **Add context-suppression on top of Option A** for the 9 context-dependent features (Bucket 2). Two distinct suppression rules:
   - For the 2A class: replicate the training-time temporal pre-filter at score time (suppress if gating counter didn't advance).
   - For the 2B class: gate drop-flags on a "calls active" condition.
5. **Validate against the saved Apr-24 and Apr-28 anomaly snapshots** in offline replay. Confirm spurious flags are suppressed (compare `dns_failure` Phase 0 before/after; expect the 4 flags currently misleading NA to disappear) without losing real-fault detection on the 100% scenarios.

## Side observation worth flagging

**Eight of the 25 features with declared ranges have `typical_range = [0, 0]`** — meaning "exactly zero is the only healthy value." Under Option A, any non-zero reading on these is, by definition, outside the range and would be flagged regardless of the model's distribution opinion. The model's HalfSpaceTrees scoring is essentially **redundant** for these eight features: the KB-bound check is decisive without it.

This is strong evidence that for the timeout/error-ratio family, a simple explicit-threshold detector ("if value > threshold, flag") would work as well as or better than the multivariate learning algorithm. Worth keeping in mind when evaluating Option B (full algorithm replacement) — the gain over Option A on this subset of features may be near zero.

## Reproducing this survey

The Python snippet below regenerates the table when run from the repo root. Useful to re-check after KB edits or feature changes:

```python
from pathlib import Path
from agentic_ops_common.metric_kb.loader import load_kb
from agentic_ops_common.metric_kb.feature_mapping import map_preprocessor_key_to_kb
from agentic_ops_common.anomaly.preprocessor import EXPECTED_FEATURE_KEYS

kb = load_kb(Path("network_ontology/data/metrics.yaml"))

for fkey in sorted(EXPECTED_FEATURE_KEYS):
    kb_id = map_preprocessor_key_to_kb(fkey)
    if not kb_id:
        print(f"{fkey} → NO MAPPING")
        continue
    parts = kb_id.split(".")
    nf, metric = parts[1], ".".join(parts[2:])
    nf_block = kb.metrics.get(nf)
    entry = nf_block.metrics.get(metric) if nf_block else None
    tr = entry.healthy.typical_range if entry else None
    print(f"{fkey:<55} {kb_id:<40} typical_range={tr}")
```

Diff against this document's table to spot drift after future edits.
