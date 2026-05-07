"""get_diagnostic_metrics — curated, agent-facing metric view.

Replaces `get_nf_metrics` in agent toolsets. Returns per-NF output with
two clearly-labeled blocks:

  1. Model features — every metric the anomaly screener trains on,
     auto-discovered via `MetricPreprocessor.EXPECTED_FEATURE_KEYS`.
     Includes current value + the screener's learned baseline.
  2. Diagnostic supporting — KB-tagged metrics (`agent_exposed: true`)
     that have proven load-bearing in agent hypothesis-confirmation
     chains across saved chaos episodes.

`get_nf_metrics` itself is unchanged and still serves the GUI / internal
consumers; this is the agent-facing view.

ADRs:
  - `docs/ADR/get_diagnostic_metrics_tool.md` — why two blocks; the
    KB schema change; what's in the curated set.
  - `docs/ADR/dealing_with_temporality_3.md` — the time-awareness
    architecture this tool is built for. The `at_time_ts` parameter
    is reserved on the public signature; live mode (Step 3) is the
    only mode implemented; time-aware mode (Step 5) lands later.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from agentic_ops_common.metric_kb import (
    MetricsKB,
    load_kb,
)
from agentic_ops_common.metric_kb.feature_mapping import (
    NF_LAYER,
    map_preprocessor_key_to_kb,
)

_log = logging.getLogger("tools.diagnostic_metrics")

# Two snapshots, 5s apart, give the preprocessor's rate pipeline a
# 5-second instantaneous rate window. Less smoothed than the
# screener's 30-second sliding window but vastly fresher than no
# rates at all. Step 5 of the ADR replaces this with time-anchored
# replay against the chaos framework's observation_snapshots.
_LIVE_RATE_SAMPLE_INTERVAL_S = 5.0


async def get_diagnostic_metrics(
    at_time_ts: Optional[float] = None,
    nfs: Optional[list[str]] = None,
) -> str:
    """Return the curated, agent-relevant metric view.

    Two classes of metrics are returned per NF:

      1. Model features — every metric the anomaly screener trains on,
         with current value and the screener's learned baseline. These
         answer "is anything statistically anomalous right now?"
      2. Diagnostic supporting metrics — KB-tagged metrics that have
         proven load-bearing in agent hypothesis-confirmation chains.
         These answer "given the hypothesis, what would we expect to
         see?"

    Args:
        at_time_ts: Optional Unix timestamp to anchor the query at.
            When None (default), live mode: take two snapshots 5s
            apart, compute rates from the delta. When set, historical
            mode: replay the chaos framework's recorded
            `observation_snapshots` against the matched timestamp.
            Investigators should pass `anomaly_screener_snapshot_ts`
            from session state — this anchors evidence-gathering at
            the moment the screener flagged the anomaly, instead of
            "now" (when the test traffic may have already stopped).
            See ADR `dealing_with_temporality_3.md`.
        nfs: Optional filter — list of NF names (e.g. ["pcscf",
            "icscf"]) to restrict the output to. None returns all NFs
            covered by either block.

    Returns:
        Per-NF text rendering with "Model features" and "Diagnostic
        supporting" sections. Each metric line includes value, type/
        unit annotation, and (for model features) the learned baseline.
        Header surfaces the time anchor (live vs anchored at ts=...).
    """
    # Lazy imports so this module doesn't pull in the heavy preprocessor
    # / screener / persistence stack at import time. The `tools` package
    # is imported broadly across the agent system; that overhead is real.
    from agentic_ops_common.anomaly.preprocessor import (
        EXPECTED_FEATURE_KEYS,
        MetricPreprocessor,
        parse_nf_metrics_text,
    )
    from agentic_ops_common import tools

    # 1. Load KB. Without it, we can't render annotations or look up
    # the agent_exposed supporting set. Failure here is fatal for the
    # tool — better to surface the error than emit a degraded view.
    try:
        kb = load_kb()
    except Exception as e:
        return f"get_diagnostic_metrics: cannot load KB ({e})"

    # 2. Choose between live mode (default) and time-anchored mode
    # (ADR `dealing_with_temporality_3.md` Step 5).
    if at_time_ts is None:
        try:
            features, raw_snapshot = await _collect_live_features_and_snapshot(
                tools, parse_nf_metrics_text, MetricPreprocessor,
            )
        except Exception as e:
            return f"get_diagnostic_metrics: snapshot collection failed ({e})"
        anchor_text = None  # header reads as live
    else:
        result = _collect_historical_features_and_snapshot(
            at_time_ts, MetricPreprocessor,
        )
        if isinstance(result, str):
            # _collect_historical returns a string when no historical
            # data is reachable — surface it directly to the agent.
            return result
        features, raw_snapshot = result
        anchor_text = f"anchored at ts={at_time_ts:.0f}"

    # 3. Load the trained screener for learned-baseline values. This
    # is best-effort — without it, model-feature rendering loses the
    # `learned_normal` line but the rest still works.
    learned_means: dict[str, float] = {}
    try:
        from anomaly_trainer.persistence import load_model
        screener, _, _ = load_model()
        if screener is not None:
            for fkey, vals in getattr(screener, "_feature_means", {}).items():
                if vals:
                    learned_means[fkey] = sum(vals) / len(vals)
    except Exception as e:
        _log.warning("Could not load screener for learned baselines: %s", e)

    # 4. Render.
    return _render_two_block_per_nf(
        features=features,
        raw_snapshot=raw_snapshot,
        learned_means=learned_means,
        kb=kb,
        nf_filter=set(nfs) if nfs else None,
        anchor_text=anchor_text,
    )


# ============================================================================
# Live and time-anchored data collection paths
# ============================================================================

async def _collect_live_features_and_snapshot(
    tools_mod,
    parse_nf_metrics_text,
    MetricPreprocessor,
):
    """Live mode: two snapshots 5s apart through the preprocessor."""
    text_a = await tools_mod.get_nf_metrics()
    snap_a = parse_nf_metrics_text(text_a)
    await asyncio.sleep(_LIVE_RATE_SAMPLE_INTERVAL_S)
    text_b = await tools_mod.get_nf_metrics()
    snap_b = parse_nf_metrics_text(text_b)

    pp = MetricPreprocessor()
    pp.process(snap_a)
    features = pp.process(snap_b)
    return features, snap_b


def _collect_historical_features_and_snapshot(
    at_time_ts: float,
    MetricPreprocessor,
):
    """Time-anchored mode: replay observation_snapshots at `at_time_ts`.

    Returns (features_dict, raw_snapshot) on success, OR a string
    error message when no historical data is reachable for the
    requested timestamp. The string return is intentional — it
    bubbles up to the agent so it knows the query couldn't be
    answered, instead of silently falling back to live data.

    Implementation: the preprocessor needs a sliding rate window of
    history to emit rate-derived features. We replay the snapshots
    leading up to `at_time_ts` (in chronological order) through a
    fresh preprocessor, then take the features from the matched
    snapshot's `process()` call.
    """
    from agentic_ops_common.tools.snapshot_replay import (
        find_closest_snapshot,
        get_observation_snapshots,
    )

    snapshots = get_observation_snapshots()
    if not snapshots:
        return (
            f"get_diagnostic_metrics: no observation_snapshots are "
            f"available in this context, cannot answer at_time_ts="
            f"{at_time_ts:.0f}. Time-anchored queries require the "
            f"chaos framework's snapshot history; orchestrator must "
            f"have called set_observation_snapshots(). For live "
            f"queries, omit at_time_ts."
        )

    matched = find_closest_snapshot(snapshots, at_time_ts)
    if matched is None:
        # Surface the gap explicitly. Do NOT fall back to live data —
        # that would defeat the time-anchoring contract.
        ts_min = min((s.get("_timestamp", 0) for s in snapshots
                      if isinstance(s.get("_timestamp"), (int, float))),
                     default=None)
        ts_max = max((s.get("_timestamp", 0) for s in snapshots
                      if isinstance(s.get("_timestamp"), (int, float))),
                     default=None)
        window_text = (
            f" (snapshot history covers ts={ts_min:.0f}..{ts_max:.0f})"
            if ts_min is not None and ts_max is not None
            else ""
        )
        return (
            f"get_diagnostic_metrics: no snapshot within drift "
            f"tolerance of at_time_ts={at_time_ts:.0f}{window_text}. "
            f"Either the requested time is outside the observation "
            f"window, or the recorded data has been cleared."
        )

    # Sort snapshots chronologically. Pick everything up to and
    # including the matched one. Need at least 6 prior snapshots (the
    # rate window) for the preprocessor to emit rate-derived features
    # — if fewer are available, rate features are zero, but the gauge
    # / pass-through features still come through correctly.
    matched_ts = matched["_timestamp"]
    sorted_snaps = sorted(
        (s for s in snapshots
         if isinstance(s.get("_timestamp"), (int, float))),
        key=lambda s: s["_timestamp"],
    )
    history_until_match = [
        s for s in sorted_snaps if s["_timestamp"] <= matched_ts
    ]

    pp = MetricPreprocessor()
    features: dict = {}
    for snap in history_until_match:
        # Build the per-NF dict the preprocessor expects. The
        # observation snapshot uses `{"metrics": {...}}` wrapper —
        # MetricPreprocessor's process() handles both shapes.
        raw_metrics = {
            comp: data
            for comp, data in snap.items()
            if not comp.startswith("_") and isinstance(data, dict)
        }
        features = pp.process(raw_metrics, timestamp=snap["_timestamp"])

    return features, matched


# ============================================================================
# Render layer
# ============================================================================

def _render_two_block_per_nf(
    *,
    features: dict[str, float],
    raw_snapshot: dict[str, dict[str, float]],
    learned_means: dict[str, float],
    kb: MetricsKB,
    nf_filter: Optional[set[str]],
    anchor_text: Optional[str] = None,
) -> str:
    """Build the per-NF "Model features" + "Diagnostic supporting" text.

    `anchor_text` (when provided) surfaces the time anchor in the
    output header — e.g., "anchored at ts=1700000000". None means
    live mode; the header reads as "live snapshot".
    """
    # Group model features by NF using the feature-mapping layer. Some
    # features map to "<no nf>" (e.g. context.calls_active) — those
    # land in a synthetic OPERATIONAL_CONTEXT bucket at the top so the
    # agent always sees the operational state up front.
    feats_by_nf, context_features = _bucket_model_features_by_nf(features)

    # Group agent_exposed=True KB entries by NF.
    supporting_by_nf = _bucket_supporting_metrics_by_nf(kb, nf_filter)

    # NFs that have something to show (either block).
    all_nfs = set(feats_by_nf) | set(supporting_by_nf)
    if nf_filter is not None:
        all_nfs &= nf_filter

    if anchor_text:
        header = f"DIAGNOSTIC METRICS ({anchor_text})"
    else:
        header = "DIAGNOSTIC METRICS (live snapshot)"

    out: list[str] = [
        header,
        "",
        "Per-NF curated view. Two blocks per NF:",
        "  - Model features: current values vs the anomaly screener's "
        "learned baseline.",
        "  - Diagnostic supporting: raw values that have proven load-"
        "bearing in agent hypothesis testing across saved episodes.",
        "",
    ]

    # Operational context goes first when no nf_filter is set —
    # context features carry no NF label but inform every other read.
    if context_features and nf_filter is None:
        out.append("OPERATIONAL CONTEXT:")
        for fkey, val in sorted(context_features.items()):
            out.append(f"  {fkey} = {_fmt_value(val)}")
        out.append("")

    for nf in sorted(all_nfs):
        layer = NF_LAYER.get(nf, "?")
        out.append(f"{nf.upper()} ({layer} layer):")

        # Block 1 — Model features. Each feature is rendered through the
        # unified KB-block helper so the LLM sees the full authored
        # semantics (what_it_signals, value-specific interpretation,
        # every disambiguator with partner value inlined).
        feats = feats_by_nf.get(nf, {})
        out.append("  -- Model features --")
        if feats:
            for fkey, val in sorted(feats.items()):
                kb_id = map_preprocessor_key_to_kb(fkey)
                entry = kb.get_metric(kb_id) if kb_id else None
                out.extend(_render_metric_with_full_kb_block(
                    label=fkey,
                    value=val,
                    entry=entry,
                    kb=kb,
                    raw_snapshot=raw_snapshot,
                    features=features,
                    learned_value=learned_means.get(fkey),
                ))
        else:
            out.append("    (no model features for this NF)")

        # Block 2 — Diagnostic supporting. Same renderer, raw-snapshot
        # value lookup instead of preprocessor-feature lookup.
        supporting = supporting_by_nf.get(nf, [])
        out.append("  -- Diagnostic supporting --")
        if supporting:
            for kb_id, entry in supporting:
                metric_name = kb_id.split(".", 2)[-1]
                raw_value = _lookup_raw_value(kb_id, raw_snapshot)
                out.extend(_render_metric_with_full_kb_block(
                    label=metric_name,
                    value=raw_value,
                    entry=entry,
                    kb=kb,
                    raw_snapshot=raw_snapshot,
                    features=features,
                    learned_value=None,
                ))
        else:
            out.append("    (no diagnostic supporting metrics for this NF)")
        out.append("")

    return "\n".join(out)


def _bucket_model_features_by_nf(
    features: dict[str, float],
) -> tuple[dict[str, dict[str, float]], dict[str, float]]:
    """Group preprocessor feature values by their owning NF.

    Returns (per_nf_features, context_features). `context_features`
    holds keys like `context.calls_active` that don't map to any
    specific NF — they describe operational state.
    """
    by_nf: dict[str, dict[str, float]] = {}
    context: dict[str, float] = {}
    for fkey, val in features.items():
        if fkey.startswith("context."):
            context[fkey] = val
            continue
        kb_id = map_preprocessor_key_to_kb(fkey)
        if kb_id is None:
            # Feature with no KB mapping (e.g., synthetic). Skip from
            # block 1 — there's no place to put it. Operators looking
            # for it can find the underlying raw counter in block 2 if
            # it's tagged, or in get_nf_metrics directly.
            continue
        # kb_id format: "<layer>.<nf>.<metric>" — extract nf.
        parts = kb_id.split(".", 2)
        if len(parts) < 2:
            continue
        nf = parts[1]
        by_nf.setdefault(nf, {})[fkey] = val
    return by_nf, context


def _bucket_supporting_metrics_by_nf(
    kb: MetricsKB,
    nf_filter: Optional[set[str]],
) -> dict[str, list[tuple[str, Any]]]:
    """Walk the KB; collect every entry tagged `agent_exposed: true`.

    Returns dict mapping nf -> list of (kb_id, MetricEntry) tuples.
    """
    by_nf: dict[str, list[tuple[str, Any]]] = {}
    for nf, nf_block in kb.metrics.items():
        if nf_filter is not None and nf not in nf_filter:
            continue
        for mname, entry in nf_block.metrics.items():
            if not entry.agent_exposed:
                continue
            kb_id = f"{nf_block.layer.value}.{nf}.{mname}"
            by_nf.setdefault(nf, []).append((kb_id, entry))
    # Stable ordering — alphabetical by KB id.
    for nf in by_nf:
        by_nf[nf].sort(key=lambda pair: pair[0])
    return by_nf


def _lookup_raw_value(
    kb_id: str,
    raw_snapshot: dict[str, dict[str, float]],
) -> Optional[float]:
    """Read a metric's current value from the snapshot using its
    fully-qualified KB id `<layer>.<nf>.<metric>`.

    The snapshot's per-NF dict can be either flat (`{key: value}`) or
    wrapped (`{"metrics": {key: value}}`) — both shapes are accepted.
    Live mode (parse_nf_metrics_text) emits flat. Historical mode
    (observation_snapshots from MetricsCollector) emits wrapped.
    Returns None when the metric is not in the snapshot.
    """
    parts = kb_id.split(".", 2)
    if len(parts) < 3:
        return None
    _layer, nf, metric_name = parts
    nf_data = raw_snapshot.get(nf) or {}
    if isinstance(nf_data, dict) and "metrics" in nf_data:
        nf_data = nf_data["metrics"]
    if not isinstance(nf_data, dict):
        return None
    return nf_data.get(metric_name)


def _select_meaning_variant(
    entry: Any,
    value: Optional[float],
) -> Optional[tuple[str, str]]:
    """Pick the meaning.* variant that matches the current value.

    Returns (variant_name, variant_text) or None if no authored
    variant matches.

    Selection rule (ordered):
      - value is None  → no variant (we can't reason about absence).
      - value == 0 and meaning.zero authored → ("zero", text).
      - value > healthy.typical_range[1] and meaning.spike authored → ("spike", text).
      - value < healthy.typical_range[0] (non-zero) and meaning.drop authored → ("drop", text).
      - meaning.steady_non_zero authored and value within healthy range and value != 0
        → ("steady_non_zero", text).
      - otherwise: no variant.

    Deliberately conservative — when the KB doesn't author a matching
    variant, the renderer omits the line cleanly rather than guessing.
    """
    if value is None or entry is None or entry.meaning is None:
        return None
    m = entry.meaning
    healthy = entry.healthy
    typical = healthy.typical_range if healthy else None

    if value == 0 and m.zero:
        return ("zero", m.zero)
    if typical is not None:
        low, high = typical
        if value > high and m.spike:
            return ("spike", m.spike)
        if value < low and value != 0 and m.drop:
            return ("drop", m.drop)
        if low <= value <= high and value != 0 and m.steady_non_zero:
            return ("steady_non_zero", m.steady_non_zero)
    # Fall through: no typical_range or no matching variant authored.
    if m.spike and (value or 0) > 0 and typical is None:
        # When typical_range is absent, treat any non-zero as a spike
        # only if zero is the authored healthy state. Conservative.
        return None
    return None


def _render_metric_with_full_kb_block(
    *,
    label: str,
    value: Optional[float],
    entry: Optional[Any],
    kb: MetricsKB,
    raw_snapshot: dict[str, dict[str, float]],
    features: dict[str, float],
    learned_value: Optional[float],
) -> list[str]:
    """Unified renderer. One metric → its full KB-authored semantic block.

    Used for BOTH the Model-features and Diagnostic-supporting blocks,
    so every metric the LLM sees carries the same depth: full
    `what_it_signals` (verbatim, no truncation), the value-specific
    `meaning.*` variant matching the current value, every
    `disambiguators` entry with the partner metric's current value
    inlined, full `description`, full `healthy.pre_existing_noise`,
    and `healthy.typical_range`.

    The truncation that hid 30 metrics' worth of authored content from
    the LLM (see ADR `expose_kb_disambiguators_to_investigator.md`) is
    deliberately impossible here — there is no first-sentence shortcut,
    no length cap, no paraphrase. A static-analysis test in
    `tests/test_renderer_no_truncation_patterns.py` enforces that the
    forbidden patterns never reappear in the source.
    """
    lines: list[str] = []

    # ---- Header line: `label = value [type, unit]` ----
    type_annotation = ""
    if entry is not None:
        type_str = f"[{entry.type.value}"
        if entry.unit:
            type_str += f", {entry.unit}"
        type_str += "]"
        type_annotation = f" {type_str}"
    if value is None:
        value_str = "(not in snapshot)"
    else:
        value_str = _fmt_value(value)
    lines.append(f"    {label} = {value_str}{type_annotation}")

    # ---- Learned baseline (model-features path only) ----
    if learned_value is not None:
        lines.append(f"        learned_normal = {_fmt_value(learned_value)}")

    if entry is None:
        return lines

    # ---- Healthy typical range ----
    if entry.healthy and entry.healthy.typical_range is not None:
        low, high = entry.healthy.typical_range
        lines.append(
            f"        healthy_range = [{_fmt_value(low)}, {_fmt_value(high)}]"
        )

    # ---- Value-specific interpretation ----
    variant = _select_meaning_variant(entry, value)
    if variant is not None:
        variant_name, variant_text = variant
        lines.append(f"        interpretation ({variant_name}):")
        for vline in variant_text.rstrip().splitlines():
            lines.append(f"            {vline}")

    # ---- Full what_it_signals (no truncation) ----
    if entry.meaning and entry.meaning.what_it_signals:
        lines.append("        what_it_signals:")
        for sline in entry.meaning.what_it_signals.rstrip().splitlines():
            lines.append(f"            {sline}")

    # ---- Full description (no truncation) ----
    if entry.description:
        lines.append("        description:")
        for dline in entry.description.rstrip().splitlines():
            lines.append(f"            {dline}")

    # ---- pre_existing_noise — flag prominently and in full ----
    if entry.healthy and entry.healthy.pre_existing_noise:
        lines.append("        NOTE (pre-existing noise):")
        for nline in entry.healthy.pre_existing_noise.rstrip().splitlines():
            lines.append(f"            {nline}")

    # ---- Scale-dependent guidance ----
    if "scale_dependent" in (entry.tags or []):
        lines.append(
            "        Scale-dependent: read as a presence check "
            "(non-zero = present, zero = absent). Absolute count "
            "varies by deployment."
        )

    # ---- Disambiguators (every entry, full text, partner value inlined) ----
    if entry.disambiguators:
        lines.append("        disambiguators:")
        for d in entry.disambiguators:
            partner_value = _resolve_partner_value(
                d.metric, raw_snapshot, features, kb,
            )
            partner_value_str = (
                _fmt_value(partner_value) if partner_value is not None
                else "not in snapshot"
            )
            lines.append(
                f"            vs {d.metric} (current = {partner_value_str}):"
            )
            for sline in d.separates.rstrip().splitlines():
                lines.append(f"                {sline}")

    return lines


def _resolve_partner_value(
    partner_kb_id: str,
    raw_snapshot: dict[str, dict[str, float]],
    features: dict[str, float],
    kb: MetricsKB,
) -> Optional[float]:
    """Resolve a disambiguator partner's current value.

    Lookup order:
      1. Raw snapshot at the partner's `<nf>.<metric>` location.
      2. Preprocessor features under any feature-key that maps back
         to the partner's KB id (covers per-UE rates and other
         derived features that don't appear in raw snapshots).

    Returns None when neither path produces a numeric value. Non-
    numeric values found in the snapshot or features are treated as
    "not in snapshot" — the renderer must never crash on a malformed
    upstream value.
    """
    raw = _lookup_raw_value(partner_kb_id, raw_snapshot)
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return float(raw)
    # Feature lookup — scan the features dict, mapping each feature
    # key back to its KB id and matching against the partner.
    for fkey, fval in features.items():
        if map_preprocessor_key_to_kb(fkey) == partner_kb_id:
            if isinstance(fval, (int, float)) and not isinstance(fval, bool):
                return float(fval)
    return None


def _fmt_value(v: float) -> str:
    """Render a float without trailing-zero noise, integers as integers."""
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, int) or (isinstance(v, float) and v.is_integer()):
        return f"{int(v)}"
    return f"{v:.4g}"
