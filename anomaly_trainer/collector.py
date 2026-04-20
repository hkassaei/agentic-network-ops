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


async def collect_and_train(
    screener: AnomalyScreener,
    preprocessor: MetricPreprocessor,
    duration_seconds: int = 300,
) -> int:
    """Poll metrics every 5 seconds and feed to the screener's learn().

    Runs for the specified duration. Returns the number of samples collected.

    Args:
        screener: AnomalyScreener instance to train.
        preprocessor: MetricPreprocessor instance (builds counter state over time).
        duration_seconds: How long to collect (should match traffic generator duration).

    Returns:
        Number of snapshots collected and fed to the model.
    """
    samples = 0
    start = time.time()

    log.info("Starting metric collection (every %ds for %ds)", POLL_INTERVAL, duration_seconds)

    while (time.time() - start) < duration_seconds:
        try:
            metrics_text = await v5_tools.get_nf_metrics()
            raw_metrics = parse_nf_metrics_text(metrics_text)
            features = preprocessor.process(raw_metrics)

            if features:
                screener.learn(features)
                samples += 1

                if samples % 10 == 0:
                    log.info("  collected %d samples (%d features each)",
                             samples, len(features))

        except Exception as e:
            log.warning("  metric collection error (continuing): %s", e)

        await asyncio.sleep(POLL_INTERVAL)

    log.info("Metric collection complete: %d samples over %.0fs",
             samples, time.time() - start)
    return samples
