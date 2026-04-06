"""Persistence — save and load trained anomaly models to/from disk.

Artifacts saved:
  - model.pkl: Trained River HalfSpaceTrees model + AnomalyScreener wrapper
  - training_meta.json: Metadata (when, how many samples, features, etc.)

The preprocessor is NOT persisted — it is created fresh at scoring time
and fed sequential metric snapshots to build counter rates. This avoids
stale counter state from the training period.
"""

from __future__ import annotations

import json
import logging
import pickle
from datetime import datetime, timezone
from pathlib import Path

from agentic_ops_v5.anomaly import AnomalyScreener

log = logging.getLogger("anomaly_trainer.persistence")

_DEFAULT_DIR = Path(__file__).resolve().parents[1] / "agentic_ops_v5" / "anomaly" / "baseline"


def save_model(
    screener: AnomalyScreener,
    output_dir: Path | None = None,
    duration_seconds: int = 0,
    n_samples: int = 0,
) -> Path:
    """Save trained model to disk.

    Args:
        screener: Trained AnomalyScreener.
        output_dir: Directory to save to (created if needed).
        duration_seconds: Training duration for metadata.
        n_samples: Number of training samples for metadata.

    Returns:
        Path to the output directory.
    """
    out = output_dir or _DEFAULT_DIR
    out.mkdir(parents=True, exist_ok=True)

    with open(out / "model.pkl", "wb") as f:
        pickle.dump(screener, f)

    meta = {
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": duration_seconds,
        "n_samples": n_samples,
        "n_features": len(screener._feature_keys or []),
        "feature_keys": screener._feature_keys or [],
        "model_ready": screener.is_trained,
        "training_samples": screener.training_samples,
    }
    with open(out / "training_meta.json", "w") as f:
        json.dump(meta, f, indent=2)

    # Clean up stale preprocessor.pkl if it exists from a previous version
    stale_pp = out / "preprocessor.pkl"
    if stale_pp.exists():
        stale_pp.unlink()

    log.info("Model saved to %s (%d samples, %d features)",
             out, n_samples, meta["n_features"])
    return out


def load_model(
    model_dir: Path | None = None,
) -> tuple[AnomalyScreener | None, None, dict]:
    """Load trained model from disk.

    Args:
        model_dir: Directory to load from.

    Returns:
        (screener, None, metadata) — screener is None if no model exists.
        Second element is always None (preprocessor is no longer persisted).
    """
    d = model_dir or _DEFAULT_DIR

    meta_path = d / "training_meta.json"
    model_path = d / "model.pkl"

    if not meta_path.exists() or not model_path.exists():
        log.warning("No trained model found at %s", d)
        return None, None, {}

    with open(meta_path) as f:
        meta = json.load(f)

    with open(model_path, "rb") as f:
        screener = pickle.load(f)

    log.info("Loaded trained model from %s (trained %s, %d samples, %d features)",
             d, meta.get("trained_at", "?"), meta.get("n_samples", 0),
             meta.get("n_features", 0))

    return screener, None, meta
