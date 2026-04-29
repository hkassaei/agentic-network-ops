"""Backup-on-save regression guard.

Ensures `anomaly_trainer.persistence.save_model` copies an existing
on-disk model.pkl + training_meta.json to `*.bak.<utc_timestamp>`
siblings before overwriting them. Lets operators compare batch results
against the previous baseline without making a manual copy. Default
is `backup_existing=True`; the `--no-backup-existing` CLI flag opts out.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch


def _fake_screener(trained_features: list[str]):
    """A minimal stand-in — same shape as the one in
    test_anomaly_save_coverage_guard.py."""
    s = MagicMock()
    s.feature_keys = sorted(trained_features)
    s.is_trained = True
    s.training_samples = 100
    return s


def _seed_existing_model(out_dir: Path) -> tuple[Path, Path]:
    """Create dummy `model.pkl` + `training_meta.json` in out_dir to
    simulate a prior trained model. Returns the two paths."""
    model = out_dir / "model.pkl"
    meta = out_dir / "training_meta.json"
    model.write_bytes(b"OLD_MODEL_BYTES")
    meta.write_text('{"trained_at":"2026-04-01T00:00:00+00:00"}')
    return model, meta


def test_backup_default_creates_bak_files_when_existing_model_present():
    """With `backup_existing=True` (default) and an existing model.pkl
    + training_meta.json on disk, save_model copies both to .bak.* files
    BEFORE overwriting. The original (now-overwritten) files contain
    the new model; the .bak.* files contain the prior bytes."""
    from anomaly_trainer.persistence import save_model
    from agentic_ops_common.anomaly.preprocessor import EXPECTED_FEATURE_KEYS

    screener = _fake_screener(list(EXPECTED_FEATURE_KEYS))

    with tempfile.TemporaryDirectory() as td:
        out_dir = Path(td)
        old_model, old_meta = _seed_existing_model(out_dir)
        old_model_bytes = old_model.read_bytes()
        old_meta_text = old_meta.read_text()

        # No-op the actual pickle.dump so the test is hermetic — we only
        # care that the backups got created with the prior contents,
        # not that the new model serializes correctly.
        with patch("anomaly_trainer.persistence.pickle.dump"):
            save_model(screener, output_dir=out_dir, n_samples=100)

        # Backups must have the prior bytes/text.
        bak_models = list(out_dir.glob("model.pkl.bak.*"))
        bak_metas = list(out_dir.glob("training_meta.json.bak.*"))
        assert len(bak_models) == 1, (
            f"expected exactly one model.pkl backup, got {bak_models}"
        )
        assert len(bak_metas) == 1, (
            f"expected exactly one training_meta.json backup, got {bak_metas}"
        )
        assert bak_models[0].read_bytes() == old_model_bytes
        assert bak_metas[0].read_text() == old_meta_text


def test_no_backup_skips_bak_files():
    """With `backup_existing=False`, no .bak.* files are created."""
    from anomaly_trainer.persistence import save_model
    from agentic_ops_common.anomaly.preprocessor import EXPECTED_FEATURE_KEYS

    screener = _fake_screener(list(EXPECTED_FEATURE_KEYS))

    with tempfile.TemporaryDirectory() as td:
        out_dir = Path(td)
        _seed_existing_model(out_dir)

        with patch("anomaly_trainer.persistence.pickle.dump"):
            save_model(
                screener, output_dir=out_dir, n_samples=100,
                backup_existing=False,
            )

        assert list(out_dir.glob("*.bak.*")) == []


def test_backup_skipped_when_no_existing_model():
    """First-time run — directory empty, nothing to back up. Must not
    create empty .bak.* files."""
    from anomaly_trainer.persistence import save_model
    from agentic_ops_common.anomaly.preprocessor import EXPECTED_FEATURE_KEYS

    screener = _fake_screener(list(EXPECTED_FEATURE_KEYS))

    with tempfile.TemporaryDirectory() as td:
        out_dir = Path(td)
        # Note: no _seed_existing_model — directory is empty.

        with patch("anomaly_trainer.persistence.pickle.dump"):
            save_model(screener, output_dir=out_dir, n_samples=100)

        assert list(out_dir.glob("*.bak.*")) == []


def test_backup_skipped_when_coverage_gate_fails():
    """If the EXPECTED_FEATURE_KEYS coverage gate fails, save_model
    raises BEFORE any file I/O — no backup, no overwrite. Critical
    invariant: the previous good model on disk is preserved exactly
    as it was."""
    from anomaly_trainer.persistence import save_model, CoverageError
    from agentic_ops_common.anomaly.preprocessor import EXPECTED_FEATURE_KEYS

    # Drop 3 features → triggers CoverageError before any file write.
    under_trained = sorted(EXPECTED_FEATURE_KEYS)[:-3]
    screener = _fake_screener(under_trained)

    with tempfile.TemporaryDirectory() as td:
        out_dir = Path(td)
        old_model, old_meta = _seed_existing_model(out_dir)
        old_model_bytes = old_model.read_bytes()

        try:
            save_model(screener, output_dir=out_dir, n_samples=100)
            raise AssertionError("expected CoverageError")
        except CoverageError:
            pass

        # No backups should have been created.
        assert list(out_dir.glob("*.bak.*")) == []
        # And the original model.pkl is byte-identical.
        assert old_model.read_bytes() == old_model_bytes
