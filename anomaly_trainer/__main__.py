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


async def run_training(
    duration: int,
    output_dir: Path | None,
    *,
    debug_counters: bool = False,
    skip_save: bool = False,
    allow_missing_features: bool = False,
) -> None:
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
    if debug_counters:
        print(f"  Mode:      DEBUG-COUNTERS (coverage diagnostic)"
              f"{' — not saving model' if skip_save else ''}")
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
        collect_and_train(screener, preprocessor, duration,
                          debug_counters=debug_counters)
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
    print(f"  Features learned:    {len(screener.feature_keys)}")
    print(f"  Model ready:        {screener.is_trained}")
    print(f"  Duration:           {elapsed:.0f}s")
    print()

    if not screener.is_trained:
        print("  WARNING: Model not ready — too few samples.")
        print("  Try a longer duration (--duration 300).")
        sys.exit(1)

    if skip_save:
        print("  --skip-save set — model NOT persisted (diagnostic run only).")
        return

    # Save to disk. The guard inside save_model() will refuse to persist
    # if the trained feature set is missing any keys declared in
    # preprocessor.EXPECTED_FEATURE_KEYS (unless --allow-missing-features
    # is set). On failure, the existing on-disk model is preserved.
    from anomaly_trainer.persistence import CoverageError
    try:
        out = save_model(
            screener,
            output_dir=output_dir,
            duration_seconds=int(elapsed),
            n_samples=n_samples,
            allow_missing_features=allow_missing_features,
        )
    except CoverageError as exc:
        print()
        print("=" * 60)
        print("  COVERAGE GUARD FAILED — model NOT saved")
        print("=" * 60)
        print(str(exc))
        print()
        print("  The previous model on disk is preserved.")
        sys.exit(2)

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
    parser.add_argument(
        "--debug-counters", action="store_true",
        help="Log per-window advancement of the 6 gating counters (Cx "
             "Diameter response-time features, pcscf register_time). "
             "Prints a coverage table at the end. Use this to diagnose "
             "whether the current traffic profile is exercising every "
             "path the preprocessor is designed to observe. "
             "See docs/ADR/anomaly_model_feature_set.md "
             "'Training coverage gaps' for context."
    )
    parser.add_argument(
        "--skip-save", action="store_true",
        help="Run the full traffic + collection loop but do NOT overwrite "
             "the saved model. Use with --debug-counters for a pure "
             "diagnostic run that does not perturb the trained model."
    )
    parser.add_argument(
        "--allow-missing-features", action="store_true",
        help="Override the feature-coverage guard in save_model(). By "
             "default the trainer refuses to persist a model whose "
             "trained feature set is missing any key declared in "
             "MetricPreprocessor.EXPECTED_FEATURE_KEYS (see docs/ADR/"
             "anomaly_model_feature_set.md 'Training coverage gaps'). "
             "Use this flag only for intentional partial-coverage runs; "
             "do NOT use for production training."
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(name)s: %(message)s",
    )

    output_dir = Path(args.output) if args.output else None
    asyncio.run(run_training(
        args.duration, output_dir,
        debug_counters=args.debug_counters,
        skip_save=args.skip_save,
        allow_missing_features=args.allow_missing_features,
    ))


if __name__ == "__main__":
    main()
