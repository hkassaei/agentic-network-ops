"""Tests for EpisodeRetriever (R3).

The retriever is the seam between the persisted index and the agent
prompt construction. The contracts that matter:

  1. **Graceful missing-index handling** — `try_from_path()` and
     `get_default_retriever()` return `None` rather than raising when
     the index isn't there. The orchestrator opts into RAG; it
     shouldn't fail when RAG isn't set up.

  2. **Multi-shape flag ingestion** — `retrieve_for_flags()` accepts
     `AnomalyFlag` (live screener), `FlagSummary` (RAG schema), and
     plain dict (orchestrator state's serialized form). They must all
     produce equivalent retrieval keys when their fields agree.

  3. **Prompt block format** — `render_hits_for_prompt()` produces a
     non-empty markdown chunk citing source paths (provenance is
     non-negotiable per the work plan), or an empty string when
     there are no hits to inject.

  4. **Singleton caching** — `get_default_retriever()` doesn't
     reload the index from disk twice for the same path within a
     process. Reloads are explicit via `refresh=True`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from agentic_ops_common.anomaly.screener import AnomalyFlag, FlagKBContext
from agentic_ops_common.rag import (
    CaseIndex,
    EpisodeRetriever,
    FlagSummary,
    RetrievedCase,
    get_default_retriever,
    parse_corpus,
    reset_default_retriever_cache,
)


# ─────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────


def _make_case(case_id: str, *, score_pct: int, scenario: str,
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
def synthetic_cases() -> list[RetrievedCase]:
    return [
        _make_case("v7/rtp_a", score_pct=100, scenario="Call Quality Degradation",
                   flags=[("derived", "rtpengine_loss_ratio", "spike", "MEDIUM"),
                          ("normalized", "upf.gtp_indatapktn3upf_per_ue", "drop", "MEDIUM")]),
        _make_case("v7/rtp_b", score_pct=85, scenario="Call Quality Degradation",
                   flags=[("derived", "rtpengine_loss_ratio", "spike", "HIGH")]),
        _make_case("v7/hss_a", score_pct=100, scenario="HSS Unresponsive",
                   flags=[("derived", "icscf_uar_timeout_ratio", "spike", "HIGH"),
                          ("derived", "scscf_mar_timeout_ratio", "spike", "HIGH")]),
    ]


@pytest.fixture
def saved_index_dir(synthetic_cases, tmp_path) -> Path:
    """Build and persist a synthetic index; return the directory."""
    idx = CaseIndex.build(synthetic_cases)
    idx.save(tmp_path)
    return tmp_path


@pytest.fixture(autouse=True)
def _clear_retriever_singleton_cache():
    """Keep tests from leaking cached retrievers across each other."""
    reset_default_retriever_cache()
    yield
    reset_default_retriever_cache()


# ─────────────────────────────────────────────────────────────────────
# Constructors
# ─────────────────────────────────────────────────────────────────────


def test_init_from_caseindex(synthetic_cases):
    idx = CaseIndex.build(synthetic_cases)
    r = EpisodeRetriever(idx)
    assert r.case_count == len(idx.cases)
    assert r.index is idx


def test_from_path_loads_persisted_index(saved_index_dir):
    r = EpisodeRetriever.from_path(saved_index_dir)
    assert r.case_count > 0


def test_from_path_raises_on_missing_dir(tmp_path):
    with pytest.raises(FileNotFoundError):
        EpisodeRetriever.from_path(tmp_path / "nonexistent")


def test_try_from_path_returns_none_on_missing_dir(tmp_path):
    r = EpisodeRetriever.try_from_path(tmp_path / "nonexistent")
    assert r is None


def test_try_from_path_returns_none_on_unreadable_dir(tmp_path):
    """A directory without a manifest is treated as unreadable —
    same outcome as missing."""
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    r = EpisodeRetriever.try_from_path(empty_dir)
    assert r is None


# ─────────────────────────────────────────────────────────────────────
# retrieve()
# ─────────────────────────────────────────────────────────────────────


def test_retrieve_delegates_to_index_search(synthetic_cases):
    r = EpisodeRetriever(CaseIndex.build(synthetic_cases))
    hits = r.retrieve(
        "derived.rtpengine_loss_ratio:spike:MEDIUM", k=2, min_similarity=0.0,
    )
    assert hits
    assert hits[0].case.scenario_name == "Call Quality Degradation"


def test_retrieve_applies_min_similarity_floor(synthetic_cases):
    r = EpisodeRetriever(CaseIndex.build(synthetic_cases))
    hits = r.retrieve("totally unrelated", k=5, min_similarity=0.99)
    assert hits == []


# ─────────────────────────────────────────────────────────────────────
# retrieve_for_flags() — multi-shape ingestion
# ─────────────────────────────────────────────────────────────────────


def test_retrieve_for_flags_accepts_anomaly_flags(synthetic_cases):
    """AnomalyFlag is the live screener's representation."""
    r = EpisodeRetriever(CaseIndex.build(synthetic_cases))
    live_flags = [
        AnomalyFlag(
            metric="rtpengine_loss_ratio", component="derived",
            current=25.0, learned_normal=0.0,
            anomaly_score=4.5, severity="MEDIUM", direction="spike",
            kb_context=FlagKBContext(kb_metric_id="ims.rtpengine.loss_ratio"),
        ),
    ]
    hits = r.retrieve_for_flags(live_flags, min_similarity=0.0)
    assert hits
    assert hits[0].case.scenario_name == "Call Quality Degradation"


def test_retrieve_for_flags_accepts_flag_summaries(synthetic_cases):
    """FlagSummary is the RAG schema's representation."""
    r = EpisodeRetriever(CaseIndex.build(synthetic_cases))
    summary_flags = [
        FlagSummary(
            component="derived", metric="rtpengine_loss_ratio",
            direction="spike", severity="MEDIUM",
        ),
    ]
    hits = r.retrieve_for_flags(summary_flags, min_similarity=0.0)
    assert hits
    assert hits[0].case.scenario_name == "Call Quality Degradation"


def test_retrieve_for_flags_accepts_dicts(synthetic_cases):
    """Dict shape — what `AnomalyReport.to_dict_list()` emits + what
    saved-state serialization round-trips through JSON."""
    r = EpisodeRetriever(CaseIndex.build(synthetic_cases))
    dict_flags = [
        {"component": "derived", "metric": "rtpengine_loss_ratio",
         "direction": "spike", "severity": "MEDIUM"},
    ]
    hits = r.retrieve_for_flags(dict_flags, min_similarity=0.0)
    assert hits
    assert hits[0].case.scenario_name == "Call Quality Degradation"


def test_retrieve_for_flags_equivalent_across_shapes(synthetic_cases):
    """All three shapes carrying equivalent flag data should produce
    identical retrieval ranking."""
    r = EpisodeRetriever(CaseIndex.build(synthetic_cases))
    common = ("derived", "rtpengine_loss_ratio", "spike", "MEDIUM")

    anomaly = [AnomalyFlag(
        metric=common[1], component=common[0],
        current=25.0, learned_normal=0.0, anomaly_score=4.5,
        severity=common[3], direction=common[2],
    )]
    summary = [FlagSummary(
        component=common[0], metric=common[1],
        direction=common[2], severity=common[3],
    )]
    raw = [{
        "component": common[0], "metric": common[1],
        "direction": common[2], "severity": common[3],
    }]

    hits_a = r.retrieve_for_flags(anomaly, min_similarity=0.0)
    hits_s = r.retrieve_for_flags(summary, min_similarity=0.0)
    hits_r = r.retrieve_for_flags(raw, min_similarity=0.0)

    ids_a = [h.case.case_id for h in hits_a]
    ids_s = [h.case.case_id for h in hits_s]
    ids_r = [h.case.case_id for h in hits_r]
    assert ids_a == ids_s == ids_r


def test_retrieve_for_flags_empty_input_returns_empty(synthetic_cases):
    r = EpisodeRetriever(CaseIndex.build(synthetic_cases))
    assert r.retrieve_for_flags([]) == []


def test_retrieve_for_flags_scenario_hint_changes_query():
    """Adding `scenario_hint` shifts the retrieval ranking — that's
    the seam the orchestrator uses to bias retrieval toward
    scenario-matched prior episodes (when it knows the scenario)."""
    cases = [
        _make_case("v7/a", score_pct=100, scenario="Call Quality Degradation",
                   flags=[("normalized", "smf.bearers_per_ue", "shift", "LOW")]),
        _make_case("v7/b", score_pct=100, scenario="AMF Restart",
                   flags=[("normalized", "smf.bearers_per_ue", "shift", "LOW")]),
    ]
    r = EpisodeRetriever(CaseIndex.build(cases))
    common_flag = [FlagSummary(
        component="normalized", metric="smf.bearers_per_ue",
        direction="shift", severity="LOW",
    )]

    cq_hits = r.retrieve_for_flags(
        common_flag, k=2, min_similarity=0.0,
        scenario_hint="Call Quality Degradation",
    )
    amf_hits = r.retrieve_for_flags(
        common_flag, k=2, min_similarity=0.0,
        scenario_hint="AMF Restart",
    )

    # The scenario hint should pull each query toward its matching
    # case as the top hit.
    assert cq_hits[0].case.scenario_name == "Call Quality Degradation"
    assert amf_hits[0].case.scenario_name == "AMF Restart"


# ─────────────────────────────────────────────────────────────────────
# render_hits_for_prompt()
# ─────────────────────────────────────────────────────────────────────


def test_render_hits_for_prompt_empty_returns_empty_string():
    """Empty hits → empty string. Caller's prompt template substitutes
    a 'no prior episode' note in this case."""
    assert EpisodeRetriever.render_hits_for_prompt([]) == ""


def test_render_hits_for_prompt_includes_similarity_percent(synthetic_cases):
    r = EpisodeRetriever(CaseIndex.build(synthetic_cases))
    hits = r.retrieve("derived.rtpengine_loss_ratio:spike:MEDIUM",
                      k=2, min_similarity=0.0)
    rendered = EpisodeRetriever.render_hits_for_prompt(hits)
    assert "## Prior similar episodes" in rendered
    assert "similarity" in rendered.lower()
    assert "%" in rendered
    # Provenance — each hit's source path must appear so the
    # downstream EvidenceValidator can audit it.
    for h in hits:
        assert h.case.source_episode_path in rendered


def test_render_hits_for_prompt_custom_header_used(synthetic_cases):
    r = EpisodeRetriever(CaseIndex.build(synthetic_cases))
    # min_similarity=0.0 because the synthetic corpus is small and the
    # tokenizer doesn't always cross the 0.65 floor; we want non-empty
    # hits here so the render-block format assertion is reachable.
    hits = r.retrieve("derived.rtpengine_loss_ratio:spike:MEDIUM",
                      k=1, min_similarity=0.0)
    assert hits  # guard against the floor changing in future
    rendered = EpisodeRetriever.render_hits_for_prompt(
        hits, header="## Custom Header",
    )
    assert rendered.startswith("## Custom Header")


def test_render_hits_for_prompt_compact_verbosity(synthetic_cases):
    """The compact verbosity skips per-case headers (each case fits
    on one paragraph) — useful when packing many cases tightly."""
    r = EpisodeRetriever(CaseIndex.build(synthetic_cases))
    hits = r.retrieve("derived.rtpengine_loss_ratio:spike:MEDIUM",
                      k=3, min_similarity=0.0)
    assert hits
    rendered = EpisodeRetriever.render_hits_for_prompt(
        hits, verbosity="compact",
    )
    # Per-case rendering should not use the "### Prior case" header
    # in compact verbosity (only the per-hit "Rank N — similarity ..."
    # headers should be present).
    assert "### Prior case" not in rendered
    assert "### Rank 1 — similarity" in rendered


# ─────────────────────────────────────────────────────────────────────
# get_default_retriever()
# ─────────────────────────────────────────────────────────────────────


def test_default_retriever_caches_same_path(saved_index_dir):
    r1 = get_default_retriever(saved_index_dir)
    r2 = get_default_retriever(saved_index_dir)
    assert r1 is r2, "Same path should return the cached retriever instance"


def test_default_retriever_refresh_reloads(saved_index_dir):
    r1 = get_default_retriever(saved_index_dir)
    r2 = get_default_retriever(saved_index_dir, refresh=True)
    assert r1 is not r2, "refresh=True should rebuild the cache entry"


def test_default_retriever_returns_none_for_missing_path(tmp_path):
    r = get_default_retriever(tmp_path / "nonexistent")
    assert r is None


def test_default_retriever_caches_negative_result_separately(tmp_path, saved_index_dir):
    """Calling with a missing path then a real path should yield
    None first, then a real retriever — caching shouldn't poison
    different paths."""
    r1 = get_default_retriever(tmp_path / "missing")
    r2 = get_default_retriever(saved_index_dir)
    assert r1 is None
    assert r2 is not None


# ─────────────────────────────────────────────────────────────────────
# End-to-end on the real corpus
# ─────────────────────────────────────────────────────────────────────


_REPO_ROOT = Path(__file__).resolve().parents[3]


def test_e2e_retriever_against_real_corpus(tmp_path):
    """Full path: parse → index → save → load via retriever → query
    with live AnomalyFlag → top hit is a Call Quality Degradation
    episode."""
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
    retriever = EpisodeRetriever.from_path(tmp_path)
    assert retriever.case_count > 0

    live_flags = [
        AnomalyFlag(
            metric="rtpengine_loss_ratio", component="derived",
            current=25.0, learned_normal=0.0,
            anomaly_score=4.5, severity="MEDIUM", direction="spike",
            kb_context=FlagKBContext(kb_metric_id="ims.rtpengine.loss_ratio"),
        ),
        AnomalyFlag(
            metric="upf.gtp_indatapktn3upf_per_ue", component="normalized",
            current=0.06, learned_normal=1.45,
            anomaly_score=3.2, severity="MEDIUM", direction="drop",
            kb_context=FlagKBContext(kb_metric_id="core.upf.gtp_indatapktn3upf_per_ue"),
        ),
    ]
    hits = retriever.retrieve_for_flags(
        live_flags, k=3, min_similarity=0.3,
        scenario_hint="Call Quality Degradation",
        classifier_label="mixed",
    )
    assert hits, "Expected real-corpus retrieval to return hits"
    assert any("Call Quality" in h.case.scenario_name for h in hits), (
        f"Top-3 hits for an rtpengine-loss query should include a "
        f"Call Quality Degradation case; got: "
        f"{[h.case.scenario_name for h in hits]}"
    )

    rendered = retriever.render_hits_for_prompt(hits)
    assert rendered
    assert "Call Quality" in rendered
