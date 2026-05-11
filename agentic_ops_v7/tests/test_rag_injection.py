"""Tests for the Phase 2.5 RAG injection helper.

The helper plumbs the `EpisodeRetriever` into the orchestrator: it
turns live screener flags into a markdown block of retrieved prior
cases that the Phase 3 NA prompt substitutes via the
`{prior_similar_episodes}` placeholder.

The contracts that matter:

  1. **Graceful degradation** — no RAG index, no retriever, no flags,
     or any internal exception → state stays at the empty default,
     a PhaseTrace records what happened. The orchestrator does not
     crash; downstream Phase 3 NA runs without prior-case context.

  2. **State init** — `state["prior_similar_episodes"]` is always
     initialized to "" so ADK template substitution resolves cleanly
     even when RAG is off.

  3. **Successful injection** — when an index exists and flags are
     present, the helper writes a non-empty block citing source
     paths and similarity scores.

  4. **Config discipline** — the RAG_INDEX_DIR env var controls
     the index path; sentinel values ("off") disable RAG.

The end-to-end test against the real corpus is gated on the corpus
being available; CI without the chaos-log artifacts skips it cleanly.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from agentic_ops_common.rag import (
    CaseIndex,
    FlagSummary,
    RetrievedCase,
    parse_corpus,
    reset_default_retriever_cache,
)
from agentic_ops_common.models import PhaseTrace
from agentic_ops_v7.orchestrator import (
    _RAG_INDEX_ENV_VAR,
    _phase25_rag_inject_prior_episodes,
    _resolve_rag_index_dir,
)


_REPO_ROOT = Path(__file__).resolve().parents[2]


# ─────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────


def _synthetic_case(case_id: str, *, score_pct: int, scenario: str,
                    flags: list[tuple[str, str, str, str]]) -> RetrievedCase:
    return RetrievedCase(
        case_id=case_id,
        source_episode_path=f"/tmp/{case_id}.json",
        agent_version="v7",
        run_timestamp=datetime.now(timezone.utc),
        parsed_from="json",
        scenario_name=scenario,
        score_pct=score_pct,
        anomaly_top_flags=[
            FlagSummary(component=c, metric=m, direction=d, severity=s)
            for (c, m, d, s) in flags
        ],
    )


@pytest.fixture
def small_index_dir(tmp_path) -> Path:
    """A synthetic 3-case index, saved to disk and ready to be loaded
    by the helper. Covers the rtpengine-loss / HSS-timeout / register-
    rate patterns the orchestrator might query against."""
    cases = [
        _synthetic_case(
            "v7/test_rtp", score_pct=100,
            scenario="Call Quality Degradation",
            flags=[
                ("derived", "rtpengine_loss_ratio", "spike", "MEDIUM"),
                ("normalized", "upf.gtp_indatapktn3upf_per_ue", "drop", "MEDIUM"),
            ],
        ),
        _synthetic_case(
            "v7/test_hss", score_pct=100,
            scenario="HSS Unresponsive",
            flags=[
                ("derived", "icscf_uar_timeout_ratio", "spike", "HIGH"),
                ("derived", "scscf_mar_timeout_ratio", "spike", "HIGH"),
            ],
        ),
        _synthetic_case(
            "v7/test_register", score_pct=100,
            scenario="P-CSCF Packet Loss",
            flags=[
                ("normalized", "pcscf.core:rcv_requests_register_per_ue", "drop", "MEDIUM"),
                ("normalized", "icscf.core:rcv_requests_register_per_ue", "drop", "MEDIUM"),
            ],
        ),
    ]
    CaseIndex.build(cases).save(tmp_path)
    return tmp_path


@pytest.fixture(autouse=True)
def _clean_retriever_cache_and_env(monkeypatch):
    """Ensure each test starts with a clean retriever singleton and
    no inherited RAG_INDEX_DIR env var."""
    reset_default_retriever_cache()
    monkeypatch.delenv(_RAG_INDEX_ENV_VAR, raising=False)
    yield
    reset_default_retriever_cache()


# ─────────────────────────────────────────────────────────────────────
# Config resolution
# ─────────────────────────────────────────────────────────────────────


def test_resolve_index_dir_returns_none_when_no_env_and_no_default(monkeypatch, tmp_path):
    """No env var, no rag_index/ at repo root → RAG disabled."""
    monkeypatch.delenv(_RAG_INDEX_ENV_VAR, raising=False)
    # Patch the default-relative resolution by patching __file__'s
    # parent's parent? Simpler: just rely on a clean repo where
    # rag_index/ probably doesn't exist either. If it does, this
    # test isn't meaningful — skip in that case.
    default = _REPO_ROOT / "rag_index"
    if default.exists():
        pytest.skip("rag_index/ exists at repo root; can't test the 'no default' branch")
    assert _resolve_rag_index_dir() is None


def test_resolve_index_dir_uses_env_var(monkeypatch, tmp_path):
    monkeypatch.setenv(_RAG_INDEX_ENV_VAR, str(tmp_path))
    result = _resolve_rag_index_dir()
    assert result == tmp_path


@pytest.mark.parametrize("sentinel", ["off", "none", "disabled", "OFF", "None"])
def test_resolve_index_dir_disabled_by_sentinel(monkeypatch, sentinel):
    monkeypatch.setenv(_RAG_INDEX_ENV_VAR, sentinel)
    assert _resolve_rag_index_dir() is None


# ─────────────────────────────────────────────────────────────────────
# Helper graceful-degradation paths
# ─────────────────────────────────────────────────────────────────────


def test_helper_no_op_when_rag_disabled(monkeypatch):
    """Sentinel env var → state unchanged, trace says rag_disabled."""
    monkeypatch.setenv(_RAG_INDEX_ENV_VAR, "off")
    state = {"prior_similar_episodes": "", "anomaly_flags": [{"component": "x", "metric": "y", "direction": "spike", "severity": "HIGH"}]}
    traces: list[PhaseTrace] = []
    _phase25_rag_inject_prior_episodes(state, traces)
    assert state["prior_similar_episodes"] == ""
    assert len(traces) == 1
    assert traces[0].agent_name == "RAGRetriever"
    assert traces[0].output_summary == "rag_disabled"


def test_helper_no_op_when_index_missing(monkeypatch, tmp_path):
    """Env var points to a missing path → graceful no-op."""
    monkeypatch.setenv(_RAG_INDEX_ENV_VAR, str(tmp_path / "does_not_exist"))
    state = {"prior_similar_episodes": "", "anomaly_flags": [{"component": "x", "metric": "y", "direction": "spike", "severity": "HIGH"}]}
    traces: list[PhaseTrace] = []
    _phase25_rag_inject_prior_episodes(state, traces)
    assert state["prior_similar_episodes"] == ""
    assert "index_not_loaded" in traces[0].output_summary


def test_helper_no_op_when_no_anomaly_flags(monkeypatch, small_index_dir):
    """Index loads fine but state has no anomaly_flags → no_hits."""
    monkeypatch.setenv(_RAG_INDEX_ENV_VAR, str(small_index_dir))
    state = {"prior_similar_episodes": "", "anomaly_flags": []}
    traces: list[PhaseTrace] = []
    _phase25_rag_inject_prior_episodes(state, traces)
    assert state["prior_similar_episodes"] == ""
    assert traces[0].output_summary.startswith("no_flags")


def test_helper_no_op_when_no_hits_above_threshold(monkeypatch, small_index_dir):
    """Flags present but none match any indexed case strongly enough → no_hits."""
    monkeypatch.setenv(_RAG_INDEX_ENV_VAR, str(small_index_dir))
    state = {
        "prior_similar_episodes": "",
        "anomaly_flags": [
            # Made-up metric that's not in the indexed corpus' flags.
            {"component": "xyzunknown", "metric": "completely_made_up",
             "direction": "spike", "severity": "LOW"},
        ],
    }
    traces: list[PhaseTrace] = []
    _phase25_rag_inject_prior_episodes(state, traces)
    assert state["prior_similar_episodes"] == ""
    assert traces[0].output_summary.startswith("no_hits")


# ─────────────────────────────────────────────────────────────────────
# Helper successful injection
# ─────────────────────────────────────────────────────────────────────


def test_helper_injects_block_when_flags_match_index(monkeypatch, small_index_dir):
    """The happy path: flags match indexed cases → state gets a
    rendered block citing source paths."""
    monkeypatch.setenv(_RAG_INDEX_ENV_VAR, str(small_index_dir))
    state = {
        "prior_similar_episodes": "",
        "anomaly_flags": [
            {"component": "derived", "metric": "rtpengine_loss_ratio",
             "direction": "spike", "severity": "MEDIUM"},
            {"component": "normalized", "metric": "upf.gtp_indatapktn3upf_per_ue",
             "direction": "drop", "severity": "MEDIUM"},
        ],
    }
    traces: list[PhaseTrace] = []
    _phase25_rag_inject_prior_episodes(state, traces)

    assert state["prior_similar_episodes"], "Expected non-empty injection"
    block = state["prior_similar_episodes"]
    assert "## Prior similar episodes" in block
    # Provenance — at least one source path appears.
    assert "/tmp/v7/test_rtp.json" in block

    # Trace records what was retrieved.
    assert traces[0].output_summary.startswith("hits=")
    assert "top_sim=" in traces[0].output_summary
    assert "top_case=v7/test_rtp" in traces[0].output_summary


def test_helper_passes_classifier_label_when_available(monkeypatch, small_index_dir):
    """The classifier label, when present in state, biases retrieval
    toward scenario-matched cases."""
    monkeypatch.setenv(_RAG_INDEX_ENV_VAR, str(small_index_dir))
    state = {
        "prior_similar_episodes": "",
        "anomaly_flags": [
            {"component": "derived", "metric": "rtpengine_loss_ratio",
             "direction": "spike", "severity": "MEDIUM"},
        ],
        "symptom_classification": {"label": "transport_layer"},
    }
    traces: list[PhaseTrace] = []
    _phase25_rag_inject_prior_episodes(state, traces)
    assert state["prior_similar_episodes"]
    assert "test_rtp" in state["prior_similar_episodes"]


def test_helper_ignores_invalid_classifier_label(monkeypatch, small_index_dir):
    """Defensive: an unexpected classifier label shape is dropped
    silently (the retrieval still succeeds without the hint)."""
    monkeypatch.setenv(_RAG_INDEX_ENV_VAR, str(small_index_dir))
    state = {
        "prior_similar_episodes": "",
        "anomaly_flags": [
            {"component": "derived", "metric": "rtpengine_loss_ratio",
             "direction": "spike", "severity": "MEDIUM"},
        ],
        "symptom_classification": {"label": "weird_unrecognized_label"},
    }
    traces: list[PhaseTrace] = []
    _phase25_rag_inject_prior_episodes(state, traces)
    assert state["prior_similar_episodes"]  # still injected


# ─────────────────────────────────────────────────────────────────────
# Orchestrator state initialization
# ─────────────────────────────────────────────────────────────────────


def test_state_init_includes_prior_similar_episodes():
    """Test the orchestrator initializes the new state key with an
    empty default, so ADK template substitution always resolves."""
    # The state dict literal is built inside `investigate()`; we
    # check by reading the source and asserting the key is present
    # at init time. This is a static check — full state-init testing
    # would require running the orchestrator's investigate() entrypoint.
    orchestrator_source = (
        _REPO_ROOT / "agentic_ops_v7" / "orchestrator.py"
    ).read_text()
    assert '"prior_similar_episodes": ""' in orchestrator_source, (
        "State init must include prior_similar_episodes: \"\" "
        "so the NA prompt's {prior_similar_episodes} placeholder "
        "resolves to an empty string when RAG is disabled."
    )


def test_na_prompt_references_prior_similar_episodes_placeholder():
    """The placeholder must appear in the prompt; otherwise the helper
    populates a state key that nothing reads."""
    prompt = (_REPO_ROOT / "agentic_ops_v7" / "prompts" / "network_analyst.md").read_text()
    assert "{prior_similar_episodes}" in prompt, (
        "NA prompt must declare {prior_similar_episodes} for the "
        "state injection to take effect."
    )


# ─────────────────────────────────────────────────────────────────────
# End-to-end against the real corpus
# ─────────────────────────────────────────────────────────────────────


def test_e2e_helper_against_built_real_corpus(monkeypatch, tmp_path):
    """Walk the real corpus, build an index in tmp_path, point env var
    at it, then run the helper with a realistic flag list and assert
    the rendered block names a Call Quality Degradation episode."""
    roots = [
        _REPO_ROOT / "agentic_ops_v5/docs/agent_logs",
        _REPO_ROOT / "agentic_ops_v6/docs/agent_logs",
        _REPO_ROOT / "agentic_ops_v7/docs/agent_logs",
    ]
    missing = [r for r in roots if not r.exists()]
    if missing:
        pytest.skip(f"Real corpus not available: {missing}")

    cases = parse_corpus(roots)
    CaseIndex.build(cases).save(tmp_path)
    monkeypatch.setenv(_RAG_INDEX_ENV_VAR, str(tmp_path))

    state = {
        "prior_similar_episodes": "",
        "anomaly_flags": [
            {"component": "derived", "metric": "rtpengine_loss_ratio",
             "direction": "spike", "severity": "MEDIUM"},
            {"component": "normalized",
             "metric": "upf.gtp_indatapktn3upf_per_ue",
             "direction": "drop", "severity": "MEDIUM"},
        ],
        "symptom_classification": {"label": "mixed"},
    }
    traces: list[PhaseTrace] = []
    _phase25_rag_inject_prior_episodes(state, traces)

    block = state["prior_similar_episodes"]
    assert block, "Expected non-empty injection against real corpus"
    assert "Call Quality Degradation" in block, (
        "Top hits for an rtpengine-loss query should include at least "
        "one Call Quality Degradation case from the real corpus."
    )
    assert traces[0].output_summary.startswith("hits=")
