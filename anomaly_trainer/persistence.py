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

from agentic_ops_common.anomaly import AnomalyScreener

log = logging.getLogger("anomaly_trainer.persistence")

_DEFAULT_DIR = Path(__file__).resolve().parents[1] / "agentic_ops_common" / "anomaly" / "baseline"


class CoverageError(RuntimeError):
    """Raised when save_model refuses to persist a model whose trained
    feature set is missing keys listed in
    `MetricPreprocessor.EXPECTED_FEATURE_KEYS`. See
    docs/ADR/anomaly_model_feature_set.md "Training coverage gaps"."""


def _check_feature_coverage(
    trained_keys: list[str],
    *,
    allow_missing: bool,
) -> None:
    """Guard: refuse to persist a model whose trained feature set is
    missing any key declared in the preprocessor's expected set.

    Prevents silent-under-training regressions — e.g. the first-sample
    lock-in bug that left 6 temporal features unrepresented in the
    persisted metadata despite the model having been trained on them.

    `allow_missing=True` downgrades the error to a warning for
    legitimately experimental training profiles (e.g. a profile that
    intentionally omits a subsystem).
    """
    from agentic_ops_common.anomaly.preprocessor import EXPECTED_FEATURE_KEYS

    trained = set(trained_keys)
    missing = EXPECTED_FEATURE_KEYS - trained
    unexpected = trained - EXPECTED_FEATURE_KEYS

    if missing and not allow_missing:
        lines = [
            f"Refusing to save: trained feature set is missing "
            f"{len(missing)} key(s) declared in "
            f"MetricPreprocessor.EXPECTED_FEATURE_KEYS.",
            "",
            "Missing:",
        ]
        for k in sorted(missing):
            lines.append(f"  - {k}")
        lines.append("")
        lines.append(
            "Fixes (pick one):\n"
            "  1. Run a longer training session — some features may have "
            "had insufficient traffic to be observed.\n"
            "  2. Exercise the traffic path that drives those counters "
            "(e.g. full deregister/reregister for Cx Diameter).\n"
            "  3. If the feature was intentionally removed from the "
            "preprocessor, update EXPECTED_FEATURE_KEYS in the same "
            "commit that removed it.\n"
            "  4. Pass --allow-missing-features to override this guard "
            "for an intentional partial-coverage run (not recommended "
            "for models going into production pipelines)."
        )
        raise CoverageError("\n".join(lines))

    if missing and allow_missing:
        log.warning(
            "Feature-coverage guard OVERRIDDEN (--allow-missing-features): "
            "%d expected feature(s) not in trained set: %s",
            len(missing), sorted(missing),
        )

    if unexpected:
        # Not an error — the preprocessor may have emitted something new
        # that EXPECTED_FEATURE_KEYS hasn't caught up to. Surface it so
        # the author knows to update the declaration.
        log.warning(
            "Trained feature set has %d key(s) not in "
            "EXPECTED_FEATURE_KEYS — consider updating the declaration: %s",
            len(unexpected), sorted(unexpected),
        )


def save_model(
    screener: AnomalyScreener,
    output_dir: Path | None = None,
    duration_seconds: int = 0,
    n_samples: int = 0,
    *,
    allow_missing_features: bool = False,
) -> Path:
    """Save trained model to disk.

    Args:
        screener: Trained AnomalyScreener.
        output_dir: Directory to save to (created if needed).
        duration_seconds: Training duration for metadata.
        n_samples: Number of training samples for metadata.
        allow_missing_features: If True, downgrade the coverage guard
            from a hard refusal to a warning. Use only for experimental
            training profiles that intentionally omit part of the
            expected feature set.

    Returns:
        Path to the output directory.

    Raises:
        CoverageError: if the trained feature set is missing keys
            declared in EXPECTED_FEATURE_KEYS and `allow_missing_features`
            is False.
    """
    # `feature_keys` is derived from `_feature_means.keys()` — the union
    # of every feature the model actually learned across all samples,
    # not a snapshot of the first call. See screener.feature_keys.
    trained_keys = screener.feature_keys

    # Guard BEFORE writing anything — if coverage is insufficient, fail
    # loudly without overwriting the previous good model on disk.
    _check_feature_coverage(trained_keys, allow_missing=allow_missing_features)

    out = output_dir or _DEFAULT_DIR
    out.mkdir(parents=True, exist_ok=True)

    with open(out / "model.pkl", "wb") as f:
        pickle.dump(screener, f)

    meta = {
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": duration_seconds,
        "n_samples": n_samples,
        "n_features": len(trained_keys),
        "feature_keys": trained_keys,
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

    # Backward compatibility for models pickled when the anomaly module
    # lived at agentic_ops_v5.anomaly. Alias the old path to the new one
    # so pickle.load can resolve the class during unpickling. Safe because
    # the two modules are literally the same code (Phase 0 refactor moved
    # it; nothing changed functionally).
    import sys
    if "agentic_ops_v5.anomaly" not in sys.modules:
        import agentic_ops_common.anomaly as _new_anomaly
        import agentic_ops_common.anomaly.screener as _new_screener
        import agentic_ops_common.anomaly.preprocessor as _new_preprocessor
        sys.modules["agentic_ops_v5.anomaly"] = _new_anomaly
        sys.modules["agentic_ops_v5.anomaly.screener"] = _new_screener
        sys.modules["agentic_ops_v5.anomaly.preprocessor"] = _new_preprocessor

    with open(model_path, "rb") as f:
        screener = pickle.load(f)

    log.info("Loaded trained model from %s (trained %s, %d samples, %d features)",
             d, meta.get("trained_at", "?"), meta.get("n_samples", 0),
             meta.get("n_features", 0))

    return screener, None, meta
