"""Regression guard: the ontology schema validator must WARN when
an unknown key slips into a YAML file. Prevents the silent-drop
class of bug where a YAML author adds a field and the loader
ignores it.
"""

from __future__ import annotations

import copy
import logging

import pytest
import yaml


def _load_real(name: str) -> dict:
    """Load the real authored YAML so tests start from a known-good tree."""
    from pathlib import Path
    here = Path(__file__).resolve()
    data_dir = here.parents[2] / "network_ontology" / "data"
    with open(data_dir / name) as f:
        return yaml.safe_load(f)


def _captured_warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]


def test_all_real_yamls_validate_clean(caplog: pytest.LogCaptureFixture):
    """Authored YAMLs must produce zero unknown-key warnings.

    If this test fires, either (a) you just added a field to a YAML
    and forgot to update network_ontology/schema.py, or (b) you
    renamed/misspelled an existing field. Both are silent-drop risks.
    """
    from network_ontology.schema import validate_yaml, _MODEL_BY_FILE

    caplog.set_level(logging.WARNING, logger="ontology.schema")
    for filename in _MODEL_BY_FILE:
        validate_yaml(filename, _load_real(filename))

    warnings = _captured_warnings(caplog)
    assert warnings == [], (
        f"Authored YAML has unknown keys the schema doesn't know about:\n"
        + "\n".join(warnings)
    )


def test_unknown_key_deep_in_cascading_branch_warns(caplog: pytest.LogCaptureFixture):
    """A field added to an existing cascading branch must surface as a
    warning with a path breadcrumb that names the chain, the branch
    index, and the unknown key. Same shape as the mongodb_gone bug
    that motivated this guard.
    """
    from network_ontology.schema import validate_yaml

    data = copy.deepcopy(_load_real("causal_chains.yaml"))
    data["causal_chains"]["hss_unreachable"] \
        ["observable_symptoms"]["cascading"][0]["SILENTLY_DROPPED_FIELD"] = "x"

    caplog.set_level(logging.WARNING, logger="ontology.schema")
    validate_yaml("causal_chains.yaml", data)
    messages = _captured_warnings(caplog)

    assert any("SILENTLY_DROPPED_FIELD" in m for m in messages), messages
    assert any("hss_unreachable" in m for m in messages), messages
    assert any("cascading[0]" in m for m in messages), messages


def test_unknown_key_at_chain_level_warns(caplog: pytest.LogCaptureFixture):
    from network_ontology.schema import validate_yaml

    data = copy.deepcopy(_load_real("causal_chains.yaml"))
    data["causal_chains"]["hss_unreachable"]["NEW_CHAIN_LEVEL_KEY"] = []

    caplog.set_level(logging.WARNING, logger="ontology.schema")
    validate_yaml("causal_chains.yaml", data)

    assert any("NEW_CHAIN_LEVEL_KEY" in m for m in _captured_warnings(caplog))


def test_unknown_key_on_flow_step_warns(caplog: pytest.LogCaptureFixture):
    from network_ontology.schema import validate_yaml

    data = copy.deepcopy(_load_real("flows.yaml"))
    data["flows"]["vonr_call_setup"]["steps"][0]["HYPOTHETICAL"] = 42

    caplog.set_level(logging.WARNING, logger="ontology.schema")
    validate_yaml("flows.yaml", data)
    msgs = _captured_warnings(caplog)

    assert any("HYPOTHETICAL" in m for m in msgs), msgs
    assert any("vonr_call_setup" in m for m in msgs), msgs
    assert any("steps[0]" in m for m in msgs), msgs


def test_validator_never_raises(caplog: pytest.LogCaptureFixture):
    """Structural mismatches (wrong type, missing required field) must
    NOT raise — they warn and return. The loader is never blocked by
    schema validation; it is always a diagnostic layer."""
    from network_ontology.schema import validate_yaml

    # Missing required field `description` on a chain
    data = copy.deepcopy(_load_real("causal_chains.yaml"))
    del data["causal_chains"]["hss_unreachable"]["description"]

    caplog.set_level(logging.WARNING, logger="ontology.schema")
    # Should not raise
    validate_yaml("causal_chains.yaml", data)

    # And it should have warned — even if the wording differs, the
    # filename is always in the message
    assert any("causal_chains.yaml" in m for m in _captured_warnings(caplog))
