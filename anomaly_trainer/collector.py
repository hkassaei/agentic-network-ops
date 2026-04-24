"""Metric collector — polls get_nf_metrics() at regular intervals.

Runs concurrently with the traffic generator, collecting metric snapshots
every 5 seconds and feeding them to the anomaly screener's learn() method.
"""

from __future__ import annotations

import asyncio
import logging
import time

from agentic_ops_common.anomaly import MetricPreprocessor, AnomalyScreener
from agentic_ops_common.anomaly.preprocessor import parse_nf_metrics_text
from agentic_ops_common import tools as v5_tools

log = logging.getLogger("anomaly_trainer.collector")

POLL_INTERVAL = 5  # seconds


# Features that depend on a specific gating counter advancing within the
# preprocessor's sliding window. Each tuple is
#   (gating_counter_fkey, emitted_feature_key).
# Populated from docs/ADR/anomaly_model_feature_set.md ("Training coverage
# gaps" section) and `_TEMPORAL_COUNTER_MAP` in the preprocessor. Used by
# the `--debug-counters` diagnostic to tell whether the trainer's traffic
# profile is exercising each path.
_TEMPORAL_GATING: list[tuple[str, str]] = [
    ("pcscf.script:register_time",                        "derived.pcscf_avg_register_time_ms"),
    ("icscf.cdp:replies_received",                        "icscf.cdp:average_response_time"),
    ("icscf.ims_icscf:uar_replies_received",              "icscf.ims_icscf:uar_avg_response_time"),
    ("icscf.ims_icscf:lir_replies_received",              "icscf.ims_icscf:lir_avg_response_time"),
    ("scscf.ims_auth:mar_replies_received",               "scscf.ims_auth:mar_avg_response_time"),
    ("scscf.ims_registrar_scscf:sar_replies_received",    "scscf.ims_registrar_scscf:sar_avg_response_time"),
]


async def collect_and_train(
    screener: AnomalyScreener,
    preprocessor: MetricPreprocessor,
    duration_seconds: int = 300,
    debug_counters: bool = False,
) -> int:
    """Poll metrics every 5 seconds and feed to the screener's learn().

    Runs for the specified duration. Returns the number of samples collected.

    Args:
        screener: AnomalyScreener instance to train.
        preprocessor: MetricPreprocessor instance (builds counter state over time).
        duration_seconds: How long to collect (should match traffic generator duration).
        debug_counters: When True, track per-snapshot whether each gating
            counter advanced (i.e. whether its derived feature made it into
            the snapshot). At end of run, prints a per-counter coverage
            report. Purpose: diagnose which paths the current traffic
            profile is exercising so we know whether training coverage is
            traffic-limited or filter-limited.

    Returns:
        Number of snapshots collected and fed to the model.
    """
    samples = 0
    start = time.time()
    # Per-gating-counter advance counts, when debug_counters is on.
    feature_present: dict[str, int] = {feat: 0 for _, feat in _TEMPORAL_GATING}
    prev_raw_values: dict[str, float] = {}
    counter_advanced: dict[str, int] = {gc: 0 for gc, _ in _TEMPORAL_GATING}

    log.info("Starting metric collection (every %ds for %ds)%s",
             POLL_INTERVAL, duration_seconds,
             " [debug-counters ON]" if debug_counters else "")

    while (time.time() - start) < duration_seconds:
        try:
            metrics_text = await v5_tools.get_nf_metrics()
            raw_metrics = parse_nf_metrics_text(metrics_text)
            features = preprocessor.process(raw_metrics)

            if features:
                screener.learn(features)
                samples += 1

                if debug_counters:
                    # (a) Did the emitted snapshot contain each gated feature?
                    for _, feat in _TEMPORAL_GATING:
                        if feat in features:
                            feature_present[feat] += 1

                    # (b) Did each gating counter advance since the prior snapshot?
                    # We re-read the raw values directly from raw_metrics rather
                    # than from preprocessor state so this probe is independent
                    # of the preprocessor's internal filtering.
                    for gc, _ in _TEMPORAL_GATING:
                        comp, _, key = gc.partition(".")
                        cdata = raw_metrics.get(comp)
                        if not isinstance(cdata, dict):
                            continue
                        m = cdata.get("metrics", cdata)
                        if not isinstance(m, dict):
                            continue
                        v = m.get(key)
                        if not isinstance(v, (int, float)):
                            continue
                        prev = prev_raw_values.get(gc)
                        if prev is not None and v > prev:
                            counter_advanced[gc] += 1
                        prev_raw_values[gc] = float(v)

                if samples % 10 == 0:
                    log.info("  collected %d samples (%d features each)",
                             samples, len(features))

        except Exception as e:
            log.warning("  metric collection error (continuing): %s", e)

        await asyncio.sleep(POLL_INTERVAL)

    log.info("Metric collection complete: %d samples over %.0fs",
             samples, time.time() - start)

    if debug_counters and samples > 0:
        _report_coverage(samples, counter_advanced, feature_present)

    return samples


def _report_coverage(
    samples: int,
    counter_advanced: dict[str, int],
    feature_present: dict[str, int],
) -> None:
    """Print a per-counter coverage report for the debug-counters run.

    Two numbers per counter:
      raw-advance %   — fraction of inter-snapshot steps where the raw
                        counter value increased. A direct measure of
                        traffic exposure.
      feature-emit %  — fraction of snapshots where the derived feature
                        survived the preprocessor's pre-filter. This is
                        what the screener/model actually sees.
    Gap between the two = the preprocessor window not being wide enough
    to smooth over bursty traffic.
    """
    log.info("================================================================")
    log.info("  DEBUG-COUNTERS: temporal-feature coverage over %d samples", samples)
    log.info("================================================================")
    log.info("  %-55s %10s %10s", "gating_counter → feature", "raw-adv", "feat-emit")
    for gc, feat in _TEMPORAL_GATING:
        raw_pct = 100.0 * counter_advanced[gc] / max(samples - 1, 1)
        feat_pct = 100.0 * feature_present[feat] / samples
        short = feat.split(".", 1)[-1][:55]
        log.info("  %-55s %9.1f%% %9.1f%%", short, raw_pct, feat_pct)
    log.info("----------------------------------------------------------------")
    log.info("  Interpretation:")
    log.info("    raw-adv near 0%%  → trainer traffic doesn't exercise this path")
    log.info("    raw-adv >0%% but feat-emit = 0%% → counter advanced some,")
    log.info("                                      but not every window (pre-filter sparsity)")
    log.info("    both >50%%         → covered; safe to trust for training")
    log.info("================================================================")
