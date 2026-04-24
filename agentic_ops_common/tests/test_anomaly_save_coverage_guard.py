"""Regression guard for the anomaly trainer's feature-coverage check.

Ensures that `anomaly_trainer.persistence.save_model` refuses to
persist a model whose trained feature set is missing keys declared
in `MetricPreprocessor.EXPECTED_FEATURE_KEYS`. Prevents the
first-sample-lock-in class of bug (see ADR `anomaly_model_feature_set.md`
"Training coverage gaps") from silently producing an under-trained
model in CI or a future training run.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest


def _fake_screener(trained_features: list[str]):
    """A stand-in for AnomalyScreener — only the attributes save_model
    reads are wired up."""
    s = MagicMock()
    s.feature_keys = sorted(trained_features)
    s.is_trained = True
    s.training_samples = 100
    return s


def test_save_refuses_when_expected_features_missing():
    """If the trained feature set is missing any EXPECTED_FEATURE_KEYS
    entry, save_model raises CoverageError and doesn't touch disk."""
    from anomaly_trainer.persistence import save_model, CoverageError
    from agentic_ops_common.anomaly.preprocessor import EXPECTED_FEATURE_KEYS

    # Simulate the first-sample-lock-in bug: trained set missing the 6
    # temporal features. Take EXPECTED minus those six.
    temporal = {
        "derived.pcscf_avg_register_time_ms",
        "icscf.cdp:average_response_time",
        "icscf.ims_icscf:uar_avg_response_time",
        "icscf.ims_icscf:lir_avg_response_time",
        "scscf.ims_auth:mar_avg_response_time",
        "scscf.ims_registrar_scscf:sar_avg_response_time",
    }
    under_trained = list(EXPECTED_FEATURE_KEYS - temporal)
    screener = _fake_screener(under_trained)

    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp) / "baseline"
        with pytest.raises(CoverageError) as excinfo:
            save_model(screener, output_dir=out_dir, n_samples=100)

        msg = str(excinfo.value)
        # Message names the missing features so the operator can act.
        for k in temporal:
            assert k in msg, f"missing feature {k!r} should be named in the error"

        # Critical: nothing written to disk. Previous good model preserved.
        assert not (out_dir / "model.pkl").exists()
        assert not (out_dir / "training_meta.json").exists()


def test_save_succeeds_when_all_expected_features_present():
    """Full EXPECTED_FEATURE_KEYS coverage → save proceeds."""
    from anomaly_trainer.persistence import save_model
    from agentic_ops_common.anomaly.preprocessor import EXPECTED_FEATURE_KEYS

    screener = _fake_screener(list(EXPECTED_FEATURE_KEYS))
    # Mocked screener won't pickle cleanly — stub pickle.dump for the
    # scope of this test by using a screener that DOES pickle.
    import pickle
    screener.__reduce__ = lambda: (MagicMock, ())

    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp) / "baseline"
        # We only need the guard to pass; that's what we're testing.
        # The actual pickle + metadata write is exercised by the
        # existing integration path and doesn't need re-coverage here.
        # Replace save_model's pickle.dump with a no-op to keep the
        # test hermetic.
        import anomaly_trainer.persistence as pers
        real_dump = pers.pickle.dump
        pers.pickle.dump = lambda obj, f: f.write(b"")
        try:
            out = save_model(screener, output_dir=out_dir, n_samples=100)
            assert out == out_dir
            assert (out_dir / "model.pkl").exists()
            meta = json.loads((out_dir / "training_meta.json").read_text())
            assert meta["n_features"] == len(EXPECTED_FEATURE_KEYS)
            assert set(meta["feature_keys"]) == set(EXPECTED_FEATURE_KEYS)
        finally:
            pers.pickle.dump = real_dump


def test_allow_missing_features_downgrades_to_warning(caplog):
    """--allow-missing-features lets the save proceed and emits a
    WARNING instead of raising. Used for experimental training runs."""
    from anomaly_trainer.persistence import save_model
    from agentic_ops_common.anomaly.preprocessor import EXPECTED_FEATURE_KEYS

    under_trained = sorted(EXPECTED_FEATURE_KEYS)[:-3]  # drop 3 features
    screener = _fake_screener(under_trained)

    import anomaly_trainer.persistence as pers
    real_dump = pers.pickle.dump
    pers.pickle.dump = lambda obj, f: f.write(b"")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "baseline"
            import logging
            caplog.set_level(logging.WARNING, logger="anomaly_trainer.persistence")
            # Should not raise
            save_model(screener, output_dir=out_dir, n_samples=100,
                       allow_missing_features=True)
            # Should log a warning naming the override
            assert any("OVERRIDDEN" in r.getMessage() for r in caplog.records)
    finally:
        pers.pickle.dump = real_dump


def test_unexpected_extra_features_produce_warning_not_error(caplog):
    """If the trained set includes a feature NOT in EXPECTED_FEATURE_KEYS
    (someone added a feature to the preprocessor and forgot to update
    the declaration), save succeeds but a WARNING fires naming the
    stragglers."""
    from anomaly_trainer.persistence import save_model
    from agentic_ops_common.anomaly.preprocessor import EXPECTED_FEATURE_KEYS

    trained = list(EXPECTED_FEATURE_KEYS) + ["derived.hypothetical_new_feature"]
    screener = _fake_screener(trained)

    import anomaly_trainer.persistence as pers
    real_dump = pers.pickle.dump
    pers.pickle.dump = lambda obj, f: f.write(b"")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "baseline"
            import logging
            caplog.set_level(logging.WARNING, logger="anomaly_trainer.persistence")
            save_model(screener, output_dir=out_dir, n_samples=100)
            msgs = [r.getMessage() for r in caplog.records]
            assert any("derived.hypothetical_new_feature" in m for m in msgs), msgs
            assert any("EXPECTED_FEATURE_KEYS" in m for m in msgs)
    finally:
        pers.pickle.dump = real_dump
