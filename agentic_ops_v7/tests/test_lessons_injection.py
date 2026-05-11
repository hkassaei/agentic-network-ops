"""Tests for the Phase 2.5b operational-lessons injection helper.

The helper loads the YAML corpus once per process and writes the
rendered markdown block into `state["operational_lessons"]` for the
Phase 3 NA prompt to substitute via the `{operational_lessons}`
placeholder.

The contracts that matter:

  1. **Always-inject** when the default corpus exists — the helper
     populates the state key with a non-empty block on a normal run.
  2. **Per-process caching** — re-running the helper with the same
     path doesn't re-parse the YAML; the cached block is used.
  3. **Graceful degradation** — missing YAML, malformed entries,
     sentinel env var all leave the state key empty without raising.
  4. **Env var override** — `LESSONS_YAML_PATH` overrides the default.
  5. **State init invariant** — the orchestrator initializes
     `state["operational_lessons"] = ""` so ADK substitution resolves
     even when the helper hasn't run.
  6. **NA prompt declares the placeholder** — without that, the
     injection writes a state key nothing reads.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agentic_ops_common.models import PhaseTrace
from agentic_ops_v7.orchestrator import (
    _LESSONS_PATH_ENV_VAR,
    _phase25_inject_operational_lessons,
    _reset_lessons_cache,
    _resolve_lessons_path,
)


_REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _clean_lessons_cache_and_env(monkeypatch):
    """Reset the module-level lesson cache + env var between tests."""
    _reset_lessons_cache()
    monkeypatch.delenv(_LESSONS_PATH_ENV_VAR, raising=False)
    yield
    _reset_lessons_cache()


# ─────────────────────────────────────────────────────────────────────
# Config resolution
# ─────────────────────────────────────────────────────────────────────


def test_resolve_lessons_path_defaults_to_shipped_yaml():
    """No env var → use the shipped lessons.yaml in agentic_ops_common."""
    p = _resolve_lessons_path()
    assert p is not None
    assert p.name == "lessons.yaml"
    assert p.parent.name == "rag"


def test_resolve_lessons_path_respects_env_var(monkeypatch, tmp_path):
    monkeypatch.setenv(_LESSONS_PATH_ENV_VAR, str(tmp_path / "custom.yaml"))
    p = _resolve_lessons_path()
    assert p == tmp_path / "custom.yaml"


@pytest.mark.parametrize("sentinel", ["off", "none", "disabled", "OFF"])
def test_resolve_lessons_path_disabled_by_sentinel(monkeypatch, sentinel):
    monkeypatch.setenv(_LESSONS_PATH_ENV_VAR, sentinel)
    assert _resolve_lessons_path() is None


# ─────────────────────────────────────────────────────────────────────
# Happy path — shipped corpus
# ─────────────────────────────────────────────────────────────────────


def test_helper_injects_shipped_lessons():
    """Default config + shipped lessons.yaml → state gets a non-empty
    rendered block, trace records the count."""
    state = {"operational_lessons": ""}
    traces: list[PhaseTrace] = []
    _phase25_inject_operational_lessons(state, traces)
    block = state["operational_lessons"]
    assert block, "Expected non-empty injection from shipped lessons.yaml"
    assert "## Operational lessons" in block
    # At least one well-known lesson id should appear.
    assert "L01" in block
    assert traces[0].agent_name == "OperationalLessons"
    assert traces[0].output_summary.startswith("lessons=")


def test_helper_caches_render_across_calls():
    """Second call hits the cache; trace says `injected_from_cache`."""
    state1 = {"operational_lessons": ""}
    traces1: list[PhaseTrace] = []
    _phase25_inject_operational_lessons(state1, traces1)
    assert "lessons=" in traces1[0].output_summary

    state2 = {"operational_lessons": ""}
    traces2: list[PhaseTrace] = []
    _phase25_inject_operational_lessons(state2, traces2)
    assert state2["operational_lessons"] == state1["operational_lessons"]
    assert traces2[0].output_summary.startswith("injected_from_cache")


# ─────────────────────────────────────────────────────────────────────
# Graceful degradation
# ─────────────────────────────────────────────────────────────────────


def test_helper_no_op_when_lessons_disabled(monkeypatch):
    monkeypatch.setenv(_LESSONS_PATH_ENV_VAR, "off")
    state = {"operational_lessons": ""}
    traces: list[PhaseTrace] = []
    _phase25_inject_operational_lessons(state, traces)
    assert state["operational_lessons"] == ""
    assert traces[0].output_summary == "lessons_disabled"


def test_helper_no_op_when_yaml_missing(monkeypatch, tmp_path):
    monkeypatch.setenv(_LESSONS_PATH_ENV_VAR, str(tmp_path / "missing.yaml"))
    state = {"operational_lessons": ""}
    traces: list[PhaseTrace] = []
    _phase25_inject_operational_lessons(state, traces)
    assert state["operational_lessons"] == ""
    assert "yaml_unreadable" in traces[0].output_summary


def test_helper_no_op_on_malformed_yaml(monkeypatch, tmp_path):
    """A corrupted YAML file → no-op, trace says unreadable."""
    p = tmp_path / "bad.yaml"
    p.write_text("lessons:\n  - id: x\n  this is not valid: [[[")
    monkeypatch.setenv(_LESSONS_PATH_ENV_VAR, str(p))
    state = {"operational_lessons": ""}
    traces: list[PhaseTrace] = []
    _phase25_inject_operational_lessons(state, traces)
    assert state["operational_lessons"] == ""
    assert "yaml_unreadable" in traces[0].output_summary


def test_helper_uses_custom_yaml_when_env_var_set(monkeypatch, tmp_path):
    """An alternate YAML at a path of our choosing loads + renders."""
    p = tmp_path / "alt.yaml"
    p.write_text(
        "lessons:\n"
        "  - id: ALT01\n"
        "    title: Alternate lesson\n"
        "    rule: Apply the alternate rule.\n"
    )
    monkeypatch.setenv(_LESSONS_PATH_ENV_VAR, str(p))
    state = {"operational_lessons": ""}
    traces: list[PhaseTrace] = []
    _phase25_inject_operational_lessons(state, traces)
    assert "ALT01" in state["operational_lessons"]
    assert "Alternate lesson" in state["operational_lessons"]


# ─────────────────────────────────────────────────────────────────────
# State init + NA prompt invariants (static checks against source files)
# ─────────────────────────────────────────────────────────────────────


def test_state_init_includes_operational_lessons():
    """The orchestrator's `investigate()` state-init must include
    `operational_lessons: ""` so ADK template substitution always
    resolves, even when lessons are disabled."""
    source = (_REPO_ROOT / "agentic_ops_v7" / "orchestrator.py").read_text()
    assert '"operational_lessons": ""' in source, (
        "State init must include operational_lessons: \"\" so the NA "
        "prompt's {operational_lessons} placeholder resolves even "
        "when lessons are disabled."
    )


def test_na_prompt_references_operational_lessons_placeholder():
    """The placeholder must appear in the NA prompt; otherwise the
    helper populates a state key that nothing reads."""
    prompt = (
        _REPO_ROOT / "agentic_ops_v7" / "prompts" / "network_analyst.md"
    ).read_text()
    assert "{operational_lessons}" in prompt, (
        "NA prompt must declare {operational_lessons} for the state "
        "injection to take effect."
    )
    # The accompanying guidance section must also be present — the
    # placeholder without guidance is just noise.
    assert "Operational lessons" in prompt
