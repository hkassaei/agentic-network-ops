"""Tests for the CaseIndex (R2's build/save/load/search seam).

The contracts that matter:

  1. **Score-threshold filtering** — cases below the threshold are
     excluded by `build()`. R2's whole point is to keep wrong-answer
     episodes out of the corpus.

  2. **Round-trip preservation** — `build → save → load → search`
     must return the same top hit (and the same similarity score)
     as `build → search` on the same query. If this fails, the
     persisted index is a different thing than the in-memory one,
     and the runtime retriever (R3) won't see what we intended.

  3. **Search ranking** — a query embedded from the same retrieval
     key as an indexed case should rank that case first.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

from agentic_ops_common.rag import CaseIndex, RetrievedCase, FlagSummary


def _make_case(case_id: str, *, score_pct: int, flags: list[tuple[str, str, str, str]],
               scenario_name: str = "Test Scenario") -> RetrievedCase:
    """Build a minimal RetrievedCase for testing.

    `flags`: list of (component, metric, direction, severity) tuples.
    """
    flag_summaries = [
        FlagSummary(component=c, metric=m, direction=d, severity=s)
        for (c, m, d, s) in flags
    ]
    return RetrievedCase(
        case_id=case_id,
        source_episode_path=f"/tmp/{case_id}.json",
        agent_version="v7",
        run_timestamp=datetime.now(timezone.utc),
        parsed_from="json",
        scenario_name=scenario_name,
        score_pct=score_pct,
        anomaly_top_flags=flag_summaries,
    )


@pytest.fixture
def synthetic_cases() -> list[RetrievedCase]:
    """Three high-quality + two low-quality synthetic cases."""
    return [
        _make_case(
            "v7/test_rtp_a", score_pct=100,
            scenario_name="Call Quality Degradation",
            flags=[
                ("derived", "rtpengine_loss_ratio", "spike", "MEDIUM"),
                ("normalized", "upf.gtp_indatapktn3upf_per_ue", "drop", "MEDIUM"),
            ],
        ),
        _make_case(
            "v7/test_rtp_b", score_pct=85,
            scenario_name="Call Quality Degradation",
            flags=[
                ("derived", "rtpengine_loss_ratio", "spike", "HIGH"),
                ("normalized", "upf.gtp_indatapktn3upf_per_ue", "drop", "MEDIUM"),
            ],
        ),
        _make_case(
            "v7/test_hss", score_pct=100,
            scenario_name="HSS Unresponsive",
            flags=[
                ("derived", "icscf_uar_timeout_ratio", "spike", "HIGH"),
                ("derived", "scscf_mar_timeout_ratio", "spike", "HIGH"),
            ],
        ),
        _make_case(
            "v7/test_fail_a", score_pct=30,
            scenario_name="Some Failure",
            flags=[("derived", "x", "spike", "LOW")],
        ),
        _make_case(
            "v7/test_fail_b", score_pct=75,
            scenario_name="Another Failure",
            flags=[("derived", "y", "drop", "LOW")],
        ),
    ]


# ─────────────────────────────────────────────────────────────────────
# Score-threshold filtering
# ─────────────────────────────────────────────────────────────────────


def test_build_filters_by_default_score_threshold(synthetic_cases):
    """Default threshold of 80 keeps the 3 high-quality cases and
    drops both low-quality ones."""
    idx = CaseIndex.build(synthetic_cases)
    assert len(idx.cases) == 3
    case_ids = {c.case_id for c in idx.cases}
    assert case_ids == {"v7/test_rtp_a", "v7/test_rtp_b", "v7/test_hss"}


def test_build_respects_custom_score_threshold(synthetic_cases):
    """Setting threshold=100 keeps only perfect-score cases."""
    idx = CaseIndex.build(synthetic_cases, score_threshold=100)
    assert len(idx.cases) == 2
    case_ids = {c.case_id for c in idx.cases}
    assert case_ids == {"v7/test_rtp_a", "v7/test_hss"}


def test_build_empty_corpus_produces_empty_index():
    idx = CaseIndex.build([])
    assert len(idx.cases) == 0
    assert idx.embeddings.size == 0
    # Search on an empty index returns no hits, no exception.
    assert idx.search("any query") == []


# ─────────────────────────────────────────────────────────────────────
# Search ranking
# ─────────────────────────────────────────────────────────────────────


def test_search_top_hit_for_rtpengine_query(synthetic_cases):
    """A query mentioning rtpengine_loss_ratio should retrieve the
    rtpengine cases first, not the HSS case."""
    idx = CaseIndex.build(synthetic_cases)
    hits = idx.search(
        "derived.rtpengine_loss_ratio:spike:MEDIUM\nscenario: Call Quality Degradation",
        k=3,
    )
    assert hits, "Expected non-empty hits for a query that exists in the corpus"
    top = hits[0]
    assert top.case.scenario_name == "Call Quality Degradation"
    assert top.similarity > 0.5, f"Top hit suspiciously weak: {top.similarity}"


def test_search_min_similarity_filters_weak_matches(synthetic_cases):
    """min_similarity=0.99 should drop weakly-similar hits."""
    idx = CaseIndex.build(synthetic_cases)
    hits = idx.search("totally unrelated query about nothing", k=5, min_similarity=0.99)
    assert hits == []


def test_search_results_are_ordered_by_descending_similarity(synthetic_cases):
    idx = CaseIndex.build(synthetic_cases)
    hits = idx.search(
        "derived.rtpengine_loss_ratio:spike:MEDIUM", k=5,
    )
    sims = [h.similarity for h in hits]
    assert sims == sorted(sims, reverse=True)


# ─────────────────────────────────────────────────────────────────────
# Save / load round-trip
# ─────────────────────────────────────────────────────────────────────


def test_save_load_round_trip_preserves_search_ranking(synthetic_cases, tmp_path):
    """The persisted index must rank queries the same way as the
    in-memory index it was built from."""
    idx_before = CaseIndex.build(synthetic_cases)
    query = "derived.rtpengine_loss_ratio:spike:MEDIUM"
    hits_before = idx_before.search(query, k=3)

    idx_before.save(tmp_path)
    idx_after = CaseIndex.load(tmp_path)
    hits_after = idx_after.search(query, k=3)

    assert len(hits_before) == len(hits_after)
    for h1, h2 in zip(hits_before, hits_after):
        assert h1.case.case_id == h2.case.case_id, (
            "round-trip changed search ranking"
        )
        # Allow 1e-5 numerical tolerance — the embedder is re-fit on
        # load so query encodings can drift slightly in the last bits.
        np.testing.assert_allclose(h1.similarity, h2.similarity, atol=1e-5)


def test_save_writes_expected_files(synthetic_cases, tmp_path):
    CaseIndex.build(synthetic_cases).save(tmp_path)
    expected = {"manifest.json", "cases.jsonl", "embeddings.npy"}
    assert {p.name for p in tmp_path.iterdir()} == expected


def test_load_raises_on_missing_manifest(tmp_path):
    with pytest.raises(FileNotFoundError, match="manifest.json"):
        CaseIndex.load(tmp_path)


def test_manifest_records_score_threshold(synthetic_cases, tmp_path):
    """Operators reading the manifest should see which threshold
    was used. Default is 80; custom values are preserved."""
    idx = CaseIndex.build(synthetic_cases, score_threshold=85)
    idx.save(tmp_path)
    loaded = CaseIndex.load(tmp_path)
    assert loaded.manifest.score_threshold == 85
    assert loaded.manifest.embedder_name == "tfidf-v1"
    assert loaded.manifest.case_count == len(loaded.cases)


# ─────────────────────────────────────────────────────────────────────
# End-to-end on the real corpus (smoke; skipped if absent)
# ─────────────────────────────────────────────────────────────────────


_REPO_ROOT = Path(__file__).resolve().parents[3]


def test_e2e_build_on_real_corpus_under_threshold(tmp_path):
    """The CLI's full path — parse all three agent_logs dirs, build,
    save, load, search. Validates the end-to-end shape against the
    real episode corpus."""
    from agentic_ops_common.rag import parse_corpus

    roots = [
        _REPO_ROOT / "agentic_ops_v5/docs/agent_logs",
        _REPO_ROOT / "agentic_ops_v6/docs/agent_logs",
        _REPO_ROOT / "agentic_ops_v7/docs/agent_logs",
    ]
    missing = [r for r in roots if not r.exists()]
    if missing:
        pytest.skip(f"Real corpus not available: {missing}")

    cases = parse_corpus(roots)
    assert len(cases) > 50, f"Real corpus suspiciously small: {len(cases)}"

    idx = CaseIndex.build(cases, score_threshold=80)
    assert len(idx.cases) > 0
    assert all(c.score_pct >= 80 for c in idx.cases)

    idx.save(tmp_path)
    loaded = CaseIndex.load(tmp_path)
    assert len(loaded.cases) == len(idx.cases)

    # A rtpengine-loss query should retrieve at least one Call Quality
    # Degradation case in the top-5.
    query = "derived.rtpengine_loss_ratio:spike:MEDIUM"
    hits = loaded.search(query, k=5)
    scenarios = [h.case.scenario_name for h in hits]
    assert any("Call Quality" in s for s in scenarios), (
        f"Top-5 hits for an rtpengine-loss query should include at least "
        f"one Call Quality Degradation case; got: {scenarios}"
    )
