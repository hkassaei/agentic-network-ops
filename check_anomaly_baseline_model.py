#!/usr/bin/env python3
"""Explore the trained anomaly detection model.

Usage:
    .venv/bin/python check_anomaly_baseline_model.py                    # list all features
    .venv/bin/python check_anomaly_baseline_model.py rtpengine          # filter by keyword
    .venv/bin/python check_anomaly_baseline_model.py --feature pcscf.script:register_time  # one feature detail
"""

import argparse
import json
import pickle
import statistics
import sys
from pathlib import Path

MODEL_PATH = Path("agentic_ops_v5/anomaly/baseline/model.pkl")
META_PATH = Path("agentic_ops_v5/anomaly/baseline/training_meta.json")


def load_model():
    with open(MODEL_PATH, "rb") as f:
        return pickle.load(f)


def print_header(screener):
    meta = {}
    if META_PATH.exists():
        with open(META_PATH) as f:
            meta = json.load(f)

    print(f"Training samples: {screener._training_samples}")
    print(f"Training duration: {meta.get('duration_seconds', '?')}s")
    print(f"Trained at: {meta.get('trained_at', '?')}")
    print(f"Features: {len(screener._feature_means)}")
    print(f"Threshold: {screener._threshold}")
    print()


def print_feature(key, values):
    mean = sum(values) / len(values)
    std = statistics.stdev(values) if len(values) >= 2 else 0
    mn = min(values)
    mx = max(values)
    nz = sum(1 for v in values if abs(v) > 0.001)
    print(f"{key:<60} {mean:>10.4f} {std:>10.4f} {mn:>10.4f} {mx:>10.4f} {nz:>5}/{len(values)}")


def main():
    parser = argparse.ArgumentParser(description="Explore the trained anomaly model")
    parser.add_argument("filter", nargs="?", default=None, help="Filter features by keyword")
    parser.add_argument("--feature", type=str, help="Show detailed stats for one feature")
    args = parser.parse_args()

    screener = load_model()
    print_header(screener)

    if args.feature:
        values = screener._feature_means.get(args.feature)
        if not values:
            print(f"Feature '{args.feature}' not found in model.")
            print(f"Available features containing '{args.feature.split('.')[-1]}':")
            for k in sorted(screener._feature_means):
                if args.feature.split(".")[-1] in k:
                    print(f"  {k}")
            sys.exit(1)
        print(f"{'Feature':<60} {'Mean':>10} {'StdDev':>10} {'Min':>10} {'Max':>10} {'Non-0':>8}")
        print("=" * 110)
        print_feature(args.feature, values)
        print()
        print(f"All {len(values)} values:")
        for i, v in enumerate(values):
            marker = " *" if abs(v) > 0.001 else ""
            print(f"  [{i:3d}] {v:.6f}{marker}")
        return

    print(f"{'Feature':<60} {'Mean':>10} {'StdDev':>10} {'Min':>10} {'Max':>10} {'Non-0':>8}")
    print("=" * 110)

    for key in sorted(screener._feature_means.keys()):
        if args.filter and args.filter.lower() not in key.lower():
            continue
        print_feature(key, screener._feature_means[key])


if __name__ == "__main__":
    main()
