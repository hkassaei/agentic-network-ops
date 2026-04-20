"""Chaos framework ↔ metric KB trigger evaluator integration.

Invoked by the chaos framework at phase boundaries (baseline, injection,
observation, wrap). Converts collected metric snapshots into the format the
evaluator expects and persists fired events to the SQLite event store.

Per the v6 plan:
  - The agentic ops pipeline is a pure CONSUMER of events.
  - The agentic chaos framework is responsible for invoking the evaluator
    at the right moments so that events land in the store with correct
    episode_id scoping before the RCA agent runs.

Integration point (first cut, Phase 1): a single helper called at the end
of observation-traffic collection. Combines baseline + observation snapshots
into a metric-history dict and runs the evaluator once, writing all fired
events to the store.

Future cuts may add per-tick evaluation for faster clear detection — the
current single-pass approach is sufficient for end-of-episode analysis.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from agentic_ops_common.anomaly.preprocessor import MetricPreprocessor
from agentic_ops_common.metric_kb import (
    EvaluationContext,
    EventStore,
    FiredEvent,
    KBLoadError,
    evaluate,
    load_kb,
)

log = logging.getLogger("chaos.trigger_eval")


# ----------------------------------------------------------------------------
# Snapshot → feature-history conversion
# ----------------------------------------------------------------------------

def _snapshots_to_feature_history(
    snapshots: list[dict],
    baseline_snapshot: Optional[dict] = None,
) -> tuple[dict[str, list[tuple[float, float]]], dict[str, float]]:
    """Convert a sequence of raw metric snapshots into the format the
    evaluator's MetricContext expects.

    Each chaos snapshot looks like:
        {"pcscf": {"metrics": {key: value, ...}, "badge": ..., "source": ...},
         "amf":   {...}, ...,
         "_timestamp": 1234567890.0}

    The preprocessor's `process()` turns each into a flat feature dict keyed
    on `<component>.<metric>` or `derived.*` / `normalized.*`. We run the
    preprocessor across the sequence to get sliding-window rates computed
    correctly, producing per-feature time series.

    For the KB's namespacing (`<layer>.<nf>.<metric>`), we apply a rename:
    the preprocessor emits keys like `amf.ran_ue`, `icscf.cdp:average_response_time`,
    `normalized.pcscf.dialogs_per_ue`, `derived.pcscf_avg_register_time_ms`.
    The KB uses `core.amf.ran_ue`, `ims.pcscf.dialogs_per_ue`, etc. We map
    between them.

    Returns:
        (history_dict, current_values_dict) — history is keyed by KB metric_id
        (`<layer>.<nf>.<metric>`), values are current (most recent) floats.
    """
    # Order snapshots chronologically, baseline first if provided.
    #
    # Critical: we EXPAND the single baseline snapshot into a long synthetic
    # pre-fault history (a row per N seconds across a 10-minute window). This
    # anchors prior_stable() in pre-fault data.
    #
    # Rationale: the DSL's prior_stable(window='5m') looks back from eval_time
    # (= end of observation). By end of observation, the fault has been in
    # effect for the majority of the last 5 minutes — the "stable" median of
    # that window is post-fault data, not pre-fault. With a single baseline
    # point, _filter_stable treats it as an outlier and ignores it. By
    # synthesizing ~60 baseline-valued samples across the pre-fault window,
    # we give prior_stable a dominant pre-fault signal to anchor against.
    ordered: list[dict] = []
    if baseline_snapshot is not None:
        baseline_ts = float(baseline_snapshot.get("_timestamp", 0.0))
        # Determine the earliest observation timestamp so we fill the gap
        obs_start_ts = min(
            (float(s.get("_timestamp", 0.0)) for s in snapshots),
            default=baseline_ts,
        )
        # Fill from baseline_ts - 600 up to obs_start_ts - 5, spaced every 10s
        synth_end = obs_start_ts - 5.0
        synth_start = min(baseline_ts - 600.0, synth_end - 60.0)
        t = synth_start
        while t <= synth_end:
            synth = dict(baseline_snapshot)
            synth["_timestamp"] = t
            ordered.append(synth)
            t += 10.0
    ordered.extend(sorted(snapshots, key=lambda s: s.get("_timestamp", 0.0)))

    if not ordered:
        return {}, {}

    pp = MetricPreprocessor()
    per_timestamp_features: list[tuple[float, dict[str, float]]] = []
    per_timestamp_raw: list[tuple[float, dict[str, float]]] = []

    for snap in ordered:
        ts = snap.get("_timestamp", 0.0)
        # Preprocessor expects {component: {metrics: {...}, ...}} or flat dict
        raw_metrics = {
            k: v for k, v in snap.items()
            if not k.startswith("_") and isinstance(v, dict)
        }
        features = pp.process(raw_metrics, timestamp=ts)
        per_timestamp_features.append((ts, features))

        # Also extract raw NF metrics that the KB tracks but the preprocessor
        # excludes from its feature set (typically scale-dependent counts like
        # ran_ue, gnb, amf_session). These still need to flow to the KB
        # evaluator because the KB's scale-dependent entries depend on them.
        flat_raw: dict[str, float] = {}
        for comp, comp_data in raw_metrics.items():
            if not isinstance(comp_data, dict):
                continue
            metrics = (
                comp_data.get("metrics", comp_data)
                if "metrics" in comp_data else comp_data
            )
            if not isinstance(metrics, dict):
                continue
            for mkey, mval in metrics.items():
                if isinstance(mval, (int, float)) and not mkey.startswith("_"):
                    flat_raw[f"{comp}.{mkey}"] = float(mval)
        per_timestamp_raw.append((ts, flat_raw))

    # Collect into per-feature time series
    history_raw: dict[str, list[tuple[float, float]]] = {}
    for ts, features in per_timestamp_features:
        for fkey, value in features.items():
            history_raw.setdefault(fkey, []).append((ts, float(value)))

    # Map preprocessor feature keys -> KB metric ids
    history: dict[str, list[tuple[float, float]]] = {}
    current_values: dict[str, float] = {}
    for fkey, series in history_raw.items():
        kb_key = _map_preprocessor_key_to_kb(fkey)
        if kb_key is None:
            continue
        history[kb_key] = series
        current_values[kb_key] = series[-1][1]

    # Layer the raw-metric series on top. These cover metrics the KB tracks
    # but the preprocessor deliberately doesn't (ran_ue, gnb, etc.).
    raw_history: dict[str, list[tuple[float, float]]] = {}
    for ts, flat_raw in per_timestamp_raw:
        for fkey, value in flat_raw.items():
            raw_history.setdefault(fkey, []).append((ts, value))
    for fkey, series in raw_history.items():
        kb_key = _map_preprocessor_key_to_kb(fkey)
        if kb_key is None:
            continue
        if kb_key not in history:  # don't override preprocessor-computed series
            history[kb_key] = series
            current_values[kb_key] = series[-1][1]

    return history, current_values


# ----------------------------------------------------------------------------
# Feature-key mapping
# ----------------------------------------------------------------------------

# Layer assignment per NF (matches components.yaml). Used for namespacing.
_NF_LAYER: dict[str, str] = {
    "amf": "core",
    "smf": "core",
    "upf": "core",
    "pcf": "core",
    "ausf": "core",
    "udm": "core",
    "udr": "core",
    "nrf": "core",
    "pcscf": "ims",
    "icscf": "ims",
    "scscf": "ims",
    "pyhss": "ims",
    "rtpengine": "ims",
    "mongo": "infrastructure",
    "mysql": "infrastructure",
    "dns": "infrastructure",
    "nr_gnb": "ran",
}


def _map_preprocessor_key_to_kb(fkey: str) -> Optional[str]:
    """Translate a preprocessor feature key to its KB metric id.

    Preprocessor emits keys like:
        amf.ran_ue
        icscf.cdp:average_response_time
        icscf.ims_icscf:uar_avg_response_time
        normalized.pcscf.dialogs_per_ue
        normalized.upf.gtp_indatapktn3upf_per_ue
        derived.pcscf_avg_register_time_ms
        derived.icscf_uar_timeout_ratio
        derived.upf_activity_during_calls
        rtpengine.errors_per_second_(total)

    KB uses <layer>.<nf>.<metric>, e.g. core.amf.ran_ue, ims.pcscf.dialogs_per_ue.
    """
    # normalized.<nf>.<metric_part>  ->  <layer>.<nf>.<metric_part stripped of _per_ue>
    if fkey.startswith("normalized."):
        rest = fkey[len("normalized."):]
        parts = rest.split(".", 1)
        if len(parts) != 2:
            return None
        nf, metric = parts
        layer = _NF_LAYER.get(nf)
        if layer is None:
            return None
        # normalized.pcscf.dialogs_per_ue -> ims.pcscf.dialogs_per_ue
        # normalized.pcscf.core:rcv_requests_register_per_ue -> ims.pcscf.rcv_requests_register_per_ue
        clean_metric = metric.replace("core:", "")
        return f"{layer}.{nf}.{clean_metric}"

    # derived.<rest>  -> find the NF it belongs to
    if fkey.startswith("derived."):
        rest = fkey[len("derived."):]
        # Patterns: pcscf_avg_register_time_ms, icscf_uar_timeout_ratio,
        #          upf_activity_during_calls, scscf_mar_timeout_ratio, etc.
        for nf in _NF_LAYER:
            if rest.startswith(nf + "_"):
                layer = _NF_LAYER[nf]
                metric = rest[len(nf) + 1:]
                return f"{layer}.{nf}.{metric}"
        return None  # e.g. derived.upf_activity_during_calls handled above

    # <nf>.<metric>  -> <layer>.<nf>.<metric_cleaned>
    parts = fkey.split(".", 1)
    if len(parts) != 2:
        return None
    nf, metric = parts
    layer = _NF_LAYER.get(nf)
    if layer is None:
        return None
    # Strip kamailio "group:" prefix (e.g. ims_icscf:uar_avg_response_time)
    if ":" in metric:
        # Keep the full key without the group prefix:
        # ims_icscf:uar_avg_response_time -> uar_avg_response_time
        # cdp:average_response_time -> cdp_avg_response_time (rename to match KB)
        group, bare = metric.split(":", 1)
        if group == "cdp" and bare == "average_response_time":
            return f"{layer}.{nf}.cdp_avg_response_time"
        if group.startswith("ims_") and bare.endswith("_response_time"):
            return f"{layer}.{nf}.{bare}"
        # Other group:metric combos — skip for now (not in KB)
        return None
    # Handle rtpengine.errors_per_second_(total) -> ims.rtpengine.errors_per_second
    if nf == "rtpengine" and metric == "errors_per_second_(total)":
        return "ims.rtpengine.errors_per_second"
    return f"{layer}.{nf}.{metric}"


# ----------------------------------------------------------------------------
# Main integration entrypoint
# ----------------------------------------------------------------------------

def evaluate_episode_events(
    episode_id: str,
    observation_snapshots: list[dict],
    baseline_snapshot: Optional[dict] = None,
    event_store_path: Optional[Path] = None,
) -> list[FiredEvent]:
    """Run the trigger evaluator over an episode's snapshots and write events.

    Called by the chaos framework at the end of observation traffic collection.
    Writes fired events into the SQLite event store, scoped by episode_id.

    Args:
        episode_id: chaos episode identifier.
        observation_snapshots: list of snapshot dicts collected during
            observation traffic. Each must have a `_timestamp` key.
        baseline_snapshot: Optional pre-fault baseline snapshot to anchor
            prior_stable() queries. If None, only the observation window is
            available to the evaluator.
        event_store_path: override for the SQLite file location.

    Returns:
        List of fired events.
    """
    try:
        kb = load_kb()
    except KBLoadError as e:
        log.warning("Could not load metric KB — skipping trigger evaluation: %s", e)
        return []

    history, current_values = _snapshots_to_feature_history(
        observation_snapshots, baseline_snapshot=baseline_snapshot,
    )
    if not current_values:
        log.info("No metric history — skipping trigger evaluation")
        return []

    eval_time = max(
        (s.get("_timestamp", 0.0) for s in observation_snapshots),
        default=0.0,
    )

    eval_ctx = EvaluationContext(
        episode_id=episode_id,
        eval_time=eval_time,
        phase="steady_state",
        history=history,
        current_values=current_values,
    )

    fired: list[FiredEvent]
    store = EventStore(event_store_path)
    try:
        fired = evaluate(kb, eval_ctx, store)
    finally:
        store.close()

    log.info(
        "[chaos trigger eval] episode=%s: %d events fired across %d metrics",
        episode_id, len(fired), len(current_values),
    )
    return fired
