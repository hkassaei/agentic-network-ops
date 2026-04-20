"""CLI entry point for the anomaly model trainer.

Usage:
    python -m anomaly_trainer --duration 300

Requires:
    - The 5G SA + IMS stack running with UEs deployed and IMS-registered
    - The chaos framework venv (or any venv with river, pyod, agentic_ops_v5)
"""

import argparse
import asyncio
import logging
import sys
import time
from pathlib import Path

# Ensure repo root is on sys.path for imports
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


async def run_training(duration: int, output_dir: Path | None) -> None:
    from agentic_ops_common.anomaly import AnomalyScreener, MetricPreprocessor
    from anomaly_trainer.traffic import generate_traffic
    from anomaly_trainer.collector import collect_and_train
    from anomaly_trainer.persistence import save_model
    from common.stack_health import check_stack_health

    print(f"{'=' * 60}")
    print(f"  ANOMALY MODEL TRAINER")
    print(f"{'=' * 60}")
    print(f"  Duration:  {duration}s ({duration // 60}m {duration % 60}s)")
    print(f"  Output:    {output_dir or 'default (agentic_ops_v5/anomaly/baseline/)'}")
    print()
    print("  This will generate realistic IMS traffic (SIP REGISTER,")
    print("  VoNR calls) on the healthy stack while collecting metrics")
    print("  to train the anomaly detection model.")
    print()

    # Verify the stack is healthy before training
    healthy = await check_stack_health(purpose="anomaly model training")
    if not healthy:
        print("Aborted — stack must be healthy for training.")
        sys.exit(1)

    print()
    screener = AnomalyScreener()
    preprocessor = MetricPreprocessor()

    start = time.time()

    # Run traffic generation and metric collection concurrently
    print("Starting traffic generation + metric collection...")
    print()

    traffic_task = asyncio.create_task(generate_traffic(duration))
    collector_task = asyncio.create_task(
        collect_and_train(screener, preprocessor, duration)
    )

    # Wait for both to complete
    await asyncio.gather(traffic_task, collector_task)

    n_samples = collector_task.result()
    elapsed = time.time() - start

    print()
    print(f"{'=' * 60}")
    print(f"  TRAINING COMPLETE")
    print(f"{'=' * 60}")
    print(f"  Samples collected:  {n_samples}")
    print(f"  Features per sample: {len(screener._feature_keys or [])}")
    print(f"  Model ready:        {screener.is_trained}")
    print(f"  Duration:           {elapsed:.0f}s")
    print()

    if not screener.is_trained:
        print("  WARNING: Model not ready — too few samples.")
        print("  Try a longer duration (--duration 300).")
        sys.exit(1)

    # Save to disk
    out = save_model(
        screener,
        output_dir=output_dir,
        duration_seconds=int(elapsed),
        n_samples=n_samples,
    )

    print(f"  Model saved to: {out}")
    print()
    print("  To use with chaos tests:")
    print("    python -m agentic_chaos run 'P-CSCF Latency' --agent v5")
    print()
    print("  The chaos framework will auto-load the trained model.")


def main():
    parser = argparse.ArgumentParser(
        description="Train the anomaly detection model on healthy IMS traffic"
    )
    parser.add_argument(
        "--duration", type=int, default=1200,
        help="Training duration in seconds (default: 1200 = 20 minutes). "
             "Chosen to give enough samples after the temporal-metric "
             "pre-filter drops snapshots where the underlying counter did "
             "not advance. ADR: anomaly_training_zero_pollution.md"
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="Output directory for trained model (default: agentic_ops_v5/anomaly/baseline/)"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Enable debug logging"
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(name)s: %(message)s",
    )

    output_dir = Path(args.output) if args.output else None
    asyncio.run(run_training(args.duration, output_dir))


if __name__ == "__main__":
    main()
