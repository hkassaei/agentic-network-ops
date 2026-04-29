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
    mode: str = "phased",
    debug_counters: bool = False,
    skip_save: bool = False,
    allow_missing_features: bool = False,
    backup_existing: bool = True,
) -> None:
    from agentic_ops_common.anomaly import AnomalyScreener, MetricPreprocessor
    from anomaly_trainer.traffic import (
        generate_phased_traffic,
        generate_random_traffic,
    )
    from anomaly_trainer.collector import collect_and_train
    from anomaly_trainer.persistence import save_model
    from common.stack_health import check_stack_health

    print(f"{'=' * 60}")
    print(f"  ANOMALY MODEL TRAINER")
    print(f"{'=' * 60}")
    print(f"  Duration:  {duration}s ({duration // 60}m {duration % 60}s)")
    print(f"  Mode:      {mode}")
    print(f"  Output:    {output_dir or 'default (agentic_ops_v5/anomaly/baseline/)'}")
    if debug_counters:
        print(f"  Mode:      DEBUG-COUNTERS (coverage diagnostic)"
              f"{' — not saving model' if skip_save else ''}")
    print()
    if mode == "phased":
        print("  Phased traffic: cycles the stack through B → C → D → E")
        print("    Phase B  registration burst   calls=0, reg=1, cx=1")
        print("    Phase C  idle-registered      calls=0, reg=0, cx=0")
        print("    Phase D  active call held     calls=1, reg=0, cx=0")
        print("    Phase E  call + re-registers  calls=1, reg=1, cx=1")
        print("  Required so the new context.* features have data to split on.")
    else:
        print("  Random traffic: legacy mode — biased toward calls-active.")
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

    if mode == "phased":
        traffic_coro = generate_phased_traffic(duration)
    else:
        traffic_coro = generate_random_traffic(duration)
    traffic_task = asyncio.create_task(traffic_coro)
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
    print(f"  Duration:           {elapsed:.0f}s")
    print()

    if n_samples < 10:
        print("  WARNING: Model not ready — too few samples (<10).")
        print("  Try a longer duration (--duration 1200).")
        sys.exit(1)

    # ----------------------------------------------------------------------
    # Finalize training. Fits the per-bucket ECOD models on the
    # accumulated training data and derives per-bucket runtime anomaly
    # cutoffs from each bucket's training-score distribution. Until
    # this runs, `screener.is_trained` is False and `score()` returns
    # an empty report.
    # ADR: anomaly_detector_replace_river_with_pyod.md
    # ----------------------------------------------------------------------
    print("  Finalizing training (fitting per-bucket ECOD models)...")
    screener.finalize_training()
    print(f"  Model ready:        {screener.is_trained}")
    print()

    # ----------------------------------------------------------------------
    # Context-coverage gate (Option 1 sanity check).
    # The 3 `context.*` features only carry signal if training spans
    # both 0 and 1 in each. If the running mean is pinned at the
    # extremes, the screener can't route between buckets meaningfully.
    # ADR: anomaly_model_overflagging.md, "Update 2026-04-28: re-framing
    # the fix space" / Option 1.
    # ----------------------------------------------------------------------
    context_failed = False
    print("  Context-feature coverage check:")
    print(f"  {'feature':<40} {'mean':>8}  {'min':>5}  {'max':>5}  {'verdict':<10}")
    for ckey in (
        "context.calls_active",
        "context.registration_in_progress",
        "context.cx_active",
    ):
        vals = screener._feature_means.get(ckey, [])
        if not vals:
            print(f"  {ckey:<40} {'—':>8}  {'—':>5}  {'—':>5}  MISSING")
            context_failed = True
            continue
        mean = sum(vals) / len(vals)
        vmin = min(vals)
        vmax = max(vals)
        # Acceptable: mean roughly balanced, both extremes seen.
        ok = (0.15 <= mean <= 0.85) and (vmin == 0.0) and (vmax == 1.0)
        verdict = "OK" if ok else "FAIL"
        if not ok:
            context_failed = True
        print(f"  {ckey:<40} {mean:>8.2f}  {vmin:>5.0f}  {vmax:>5.0f}  {verdict}")

    # ----------------------------------------------------------------------
    # Per-bucket coverage gate.
    # Each (calls_active, registration_in_progress) bucket needs enough
    # training samples for its ECOD's empirical CDFs to be meaningful.
    # If a bucket is under-trained, runtime samples landing in it will
    # fall back to the default bucket — not a hard failure but worth
    # flagging loudly. The 60-sample threshold = 2 phase cycles at
    # 30 samples per phase.
    # ADR: anomaly_detector_replace_river_with_pyod.md, step 4.
    # ----------------------------------------------------------------------
    bucket_failed = False
    print()
    print("  Per-bucket sample-count check:")
    print(f"  {'bucket (calls,reg)':<22} {'samples':>10}  {'verdict':<10}")
    bucket_min = 60
    for bucket, count in screener.bucket_sample_counts.items():
        ok = count >= bucket_min
        verdict = "OK" if ok else "FAIL"
        if not ok:
            bucket_failed = True
        label = f"{bucket}"
        print(f"  {label:<22} {count:>10}  {verdict}  (min {bucket_min})")

    if context_failed or bucket_failed:
        print()
        print("  COVERAGE GUARD FAILED — model NOT saved.")
        if context_failed:
            print("  At least one context.* feature did not span 0→1 with a")
            print("  reasonable mean during training.")
        if bucket_failed:
            print("  At least one (calls_active, registration_in_progress)")
            print(f"  bucket has fewer than {bucket_min} training samples.")
        print("  Likely causes:")
        print("    - Trainer stuck in a single phase (try --mode phased)")
        print("    - --duration too short to complete enough B→C→D→E cycles")
        print("    - Phase D / E call setup failing (check pjsua FIFO)")
        print("  Running a batch against this model would route most runtime")
        print("  samples to under-trained or fallback buckets. Re-run training")
        print("  after fixing the coverage gap.")
        print()
        print("  The previous model on disk is preserved.")
        sys.exit(3)

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
            backup_existing=backup_existing,
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
        "--duration", type=int, default=1800,
        help="Training duration in seconds (default: 1800 = 30 minutes = "
             "3 full B→C→D→E phase cycles). Each cycle delivers ~30 "
             "samples per state bucket, so 3 cycles gives ~90 per "
             "bucket — comfortably above the per-bucket coverage gate's "
             "60-sample minimum, and enough resolution that the per-"
             "bucket 99th-percentile training-score threshold is stable "
             "against outliers. 1200s also works (~60 per bucket) but "
             "the threshold is wobblier. ADRs: "
             "anomaly_training_zero_pollution.md, "
             "anomaly_detector_replace_river_with_pyod.md."
    )
    parser.add_argument(
        "--mode", choices=["phased", "random"], default="phased",
        help="Traffic generation mode (default: phased). 'phased' cycles "
             "the stack through registration-burst / idle-registered / "
             "active-call / call+register phases so the trained model has "
             "data in every operational state — required for the new "
             "context.* features to carry signal. 'random' is the legacy "
             "calls-biased mode, kept for comparison runs only. "
             "ADR: anomaly_model_overflagging.md, Option 1."
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
    parser.add_argument(
        "--no-backup-existing", action="store_true",
        help="Skip the automatic backup of the existing on-disk model "
             "before overwriting. By default, save_model copies the "
             "current model.pkl and training_meta.json to "
             "<name>.bak.<utc_timestamp> siblings before writing the new "
             "model. The backup lets you compare batch results against "
             "the previous baseline without making a manual copy. Pass "
             "this flag only if you're deliberately discarding the old "
             "model (e.g. running on a fresh stack with no prior model)."
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(name)s: %(message)s",
    )

    output_dir = Path(args.output) if args.output else None
    asyncio.run(run_training(
        args.duration, output_dir,
        mode=args.mode,
        debug_counters=args.debug_counters,
        skip_save=args.skip_save,
        allow_missing_features=args.allow_missing_features,
        backup_existing=not args.no_backup_existing,
    ))


if __name__ == "__main__":
    main()
