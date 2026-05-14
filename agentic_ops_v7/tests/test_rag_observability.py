"""Tests for the new RAG observability surface (R4/R5 follow-up).

The orchestrator now writes three keys into state for every
investigation that ran Phase 2.5 (RAG + lessons) and Phase 3 (NA):

  state["rag_retrieval_metadata"]    — what the retriever did
  state["lessons_injection_metadata"] — what the lesson loader did
  state["rag_na_citations"]           — what the NA actually cited

These tests pin the shape of each metadata blob across all reachable
paths, plus the citation-detection logic itself.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from agentic_ops_common.models import PhaseTrace
from agentic_ops_v7.orchestrator import (
    _LESSONS_PATH_ENV_VAR,
    _RAG_INDEX_ENV_VAR,
    _collect_na_text_fields,
    _detect_rag_citations_in_na,
    _phase25_inject_operational_lessons,
    _phase25_rag_inject_prior_episodes,
    _reset_lessons_cache,
)
from agentic_ops_common.rag import CaseIndex, FlagSummary, RetrievedCase
from agentic_ops_common.rag.retriever import reset_default_retriever_cache


_REPO_ROOT = Path(__file__).resolve().parents[2]


# ─────────────────────────────────────────────────────────────────────
# Fixtures — minimal synthetic corpus / classification + cache reset
# ─────────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _isolate_caches(monkeypatch):
    reset_default_retriever_cache()
    _reset_lessons_cache()
    monkeypatch.delenv(_RAG_INDEX_ENV_VAR, raising=False)
    monkeypatch.delenv(_LESSONS_PATH_ENV_VAR, raising=False)
    yield
    reset_default_retriever_cache()
    _reset_lessons_cache()


def _synthetic_case(case_id, *, scenario, score_pct, gt_components,
                    suspect, flags) -> RetrievedCase:
    from datetime import datetime, timezone
    return RetrievedCase(
        case_id=case_id,
        source_episode_path=f"/tmp/{case_id.replace('/', '_')}.json",
        agent_version="v7",
        run_timestamp=datetime.now(timezone.utc),
        parsed_from="json",
        scenario_name=scenario,
        score_pct=score_pct,
        ground_truth_affected_components=gt_components,
        ground_truth_failure_domain="ims_signaling",
        diagnosis_primary_suspect_nf=suspect,
        anomaly_top_flags=[
            FlagSummary(component=c, metric=m, direction=d, severity=s)
            for (c, m, d, s) in flags
        ],
    )


@pytest.fixture
def small_index_dir(tmp_path):
    cases = [
        _synthetic_case(
            "v7/test_hss", scenario="HSS Unresponsive", score_pct=100,
            gt_components=["pyhss"], suspect="pyhss",
            flags=[
                ("derived", "icscf_uar_timeout_ratio", "spike", "HIGH"),
                ("derived", "scscf_mar_timeout_ratio", "spike", "HIGH"),
            ],
        ),
        _synthetic_case(
            "v7/test_rtp", scenario="Call Quality Degradation", score_pct=100,
            gt_components=["rtpengine"], suspect="rtpengine",
            flags=[
                ("derived", "rtpengine_loss_ratio", "spike", "MEDIUM"),
            ],
        ),
    ]
    CaseIndex.build(cases).save(tmp_path)
    return tmp_path


# ─────────────────────────────────────────────────────────────────────
# RAG retrieval metadata — every status path
# ─────────────────────────────────────────────────────────────────────


def test_rag_metadata_records_rag_disabled(monkeypatch):
    monkeypatch.setenv(_RAG_INDEX_ENV_VAR, "off")
    state, traces = {}, []
    _phase25_rag_inject_prior_episodes(state, traces)
    meta = state["rag_retrieval_metadata"]
    assert meta["status"] == "rag_disabled"
    assert meta["hits"] == []


def test_rag_metadata_records_index_not_loaded(monkeypatch, tmp_path):
    monkeypatch.setenv(_RAG_INDEX_ENV_VAR, str(tmp_path / "nope"))
    state, traces = {}, []
    _phase25_rag_inject_prior_episodes(state, traces)
    meta = state["rag_retrieval_metadata"]
    assert meta["status"] == "index_not_loaded"
    assert "nope" in meta["summary"]


def test_rag_metadata_records_no_flags(monkeypatch, small_index_dir):
    monkeypatch.setenv(_RAG_INDEX_ENV_VAR, str(small_index_dir))
    state = {"anomaly_flags": []}
    traces = []
    _phase25_rag_inject_prior_episodes(state, traces)
    meta = state["rag_retrieval_metadata"]
    assert meta["status"] == "no_flags"
    assert meta["corpus_size"] >= 1
    assert meta["hits"] == []


def test_rag_metadata_records_no_hits(monkeypatch, small_index_dir):
    """Flags present but nothing matches strongly enough — clean
    'no_hits' status with the query context preserved."""
    monkeypatch.setenv(_RAG_INDEX_ENV_VAR, str(small_index_dir))
    state = {
        "anomaly_flags": [
            {"component": "completely", "metric": "unrelated_metric",
             "direction": "spike", "severity": "LOW"},
        ],
        "symptom_classification": {"label": "application_layer"},
    }
    traces = []
    _phase25_rag_inject_prior_episodes(state, traces)
    meta = state["rag_retrieval_metadata"]
    assert meta["status"] == "no_hits"
    assert meta["classifier_label"] == "application_layer"
    assert meta["anomaly_flag_count"] == 1


def test_rag_metadata_records_hits_with_full_payload(
    monkeypatch, small_index_dir,
):
    """The happy path: each retrieved hit carries case_id, similarity,
    scenario, ground truth, primary suspect, source path."""
    monkeypatch.setenv(_RAG_INDEX_ENV_VAR, str(small_index_dir))
    state = {
        "anomaly_flags": [
            {"component": "derived", "metric": "icscf_uar_timeout_ratio",
             "direction": "spike", "severity": "HIGH"},
            {"component": "derived", "metric": "scscf_mar_timeout_ratio",
             "direction": "spike", "severity": "HIGH"},
        ],
        "symptom_classification": {"label": "mixed"},
    }
    traces = []
    _phase25_rag_inject_prior_episodes(state, traces)
    meta = state["rag_retrieval_metadata"]
    assert meta["status"] == "hits"
    assert meta["hits"], "Expected non-empty hits payload"
    h0 = meta["hits"][0]
    # Every key the recorder reads must be present.
    for key in (
        "rank", "similarity", "case_id", "scenario_name",
        "ground_truth_affected_components", "agent_version",
        "score_pct", "diagnosis_primary_suspect_nf",
        "source_episode_path",
    ):
        assert key in h0, f"missing key in hits payload: {key!r}"
    # Top hit is the HSS Unresponsive case.
    assert "test_hss" in h0["case_id"]
    assert h0["scenario_name"] == "HSS Unresponsive"
    assert "pyhss" in h0["ground_truth_affected_components"]


# ─────────────────────────────────────────────────────────────────────
# Lessons metadata — every status path
# ─────────────────────────────────────────────────────────────────────


def test_lessons_metadata_records_disabled(monkeypatch):
    monkeypatch.setenv(_LESSONS_PATH_ENV_VAR, "off")
    state, traces = {}, []
    _phase25_inject_operational_lessons(state, traces)
    meta = state["lessons_injection_metadata"]
    assert meta["status"] == "lessons_disabled"
    assert meta["lesson_ids"] == []
    assert meta["lesson_count"] == 0


def test_lessons_metadata_records_yaml_unreadable(monkeypatch, tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("lessons:\n  - id: x\n  not valid: [[[")
    monkeypatch.setenv(_LESSONS_PATH_ENV_VAR, str(bad))
    state, traces = {}, []
    _phase25_inject_operational_lessons(state, traces)
    meta = state["lessons_injection_metadata"]
    assert meta["status"] == "yaml_unreadable"
    assert "bad.yaml" in meta["summary"]


def test_lessons_metadata_records_injected_with_ids():
    """The shipped default lessons.yaml — exercises the full happy path."""
    state, traces = {}, []
    _phase25_inject_operational_lessons(state, traces)
    meta = state["lessons_injection_metadata"]
    assert meta["status"] == "injected"
    assert meta["lesson_count"] >= 10
    assert "L01" in meta["lesson_ids"]
    assert meta["block_chars"] > 1000


def test_lessons_metadata_records_injected_from_cache(monkeypatch, tmp_path):
    """Second call to the same path hits the cache + records the cache
    status; lesson_ids still populated from the cache value."""
    yaml = tmp_path / "alt.yaml"
    yaml.write_text(
        "lessons:\n"
        "  - id: ALT01\n"
        "    title: Test\n"
        "    rule: Apply it.\n"
    )
    monkeypatch.setenv(_LESSONS_PATH_ENV_VAR, str(yaml))

    state1, traces1 = {}, []
    _phase25_inject_operational_lessons(state1, traces1)
    assert state1["lessons_injection_metadata"]["status"] == "injected"

    state2, traces2 = {}, []
    _phase25_inject_operational_lessons(state2, traces2)
    meta = state2["lessons_injection_metadata"]
    assert meta["status"] == "injected_from_cache"
    assert meta["lesson_ids"] == ["ALT01"]


# ─────────────────────────────────────────────────────────────────────
# NA citation detection
# ─────────────────────────────────────────────────────────────────────


class _FakeHypothesis:
    def __init__(self, statement, supporting_events=()):
        self.statement = statement
        self.supporting_events = list(supporting_events)


class _FakeLayerStatus:
    def __init__(self, note=""):
        self.note = note


class _FakeNAReport:
    def __init__(self, *, summary="", layer_status=None, hypotheses=()):
        self.summary = summary
        self.layer_status = layer_status or {}
        self.hypotheses = list(hypotheses)


def test_collect_na_text_concatenates_all_text_fields():
    na = _FakeNAReport(
        summary="A summary mentioning L01.",
        layer_status={"ims": _FakeLayerStatus("Layer note about v7/ep_xyz.")},
        hypotheses=[_FakeHypothesis("h1 statement L14")],
    )
    text = _collect_na_text_fields(na)
    assert "L01" in text
    assert "v7/ep_xyz" in text
    assert "L14" in text


def test_citation_detection_finds_verbatim_case_ids():
    na = _FakeNAReport(
        summary=(
            "Based on prior case v7/ep_20260510_185748_call_quality_degradation, "
            "the rtpengine pattern matches."
        ),
        hypotheses=[_FakeHypothesis("rtpengine fault")],
    )
    result = _detect_rag_citations_in_na(
        na_report=na,
        retrieved_case_ids=[
            "v7/ep_20260510_185748_call_quality_degradation",
            "v7/ep_unrelated_case",
        ],
        injected_lesson_ids=[],
    )
    assert result["cited_case_ids"] == [
        "v7/ep_20260510_185748_call_quality_degradation",
    ]
    assert result["any_citation"] is True


def test_citation_detection_finds_lesson_ids_only_when_in_corpus():
    """Hallucinated lesson_ids (e.g. L99) that aren't in the corpus
    are filtered out — only intersected ids are reported."""
    na = _FakeNAReport(
        summary="Applying L01 and L14 here. Also mentioning L99 (not real).",
        hypotheses=[_FakeHypothesis("test")],
    )
    result = _detect_rag_citations_in_na(
        na_report=na,
        retrieved_case_ids=[],
        injected_lesson_ids=["L01", "L02", "L14", "L15"],
    )
    assert result["cited_lesson_ids"] == ["L01", "L14"]
    assert "L99" not in result["cited_lesson_ids"]
    assert result["any_citation"] is True


def test_citation_detection_returns_empty_lists_when_no_citations():
    na = _FakeNAReport(
        summary="A diagnosis with no citations at all.",
        hypotheses=[_FakeHypothesis("clean hypothesis")],
    )
    result = _detect_rag_citations_in_na(
        na_report=na,
        retrieved_case_ids=["v7/case_a"],
        injected_lesson_ids=["L01"],
    )
    assert result["cited_case_ids"] == []
    assert result["cited_lesson_ids"] == []
    assert result["any_citation"] is False


def test_citation_detection_handles_none_na_report_gracefully():
    """A missing NA report (e.g., NA emitted nothing on both attempts)
    must not crash the scanner — return empty lists."""
    result = _detect_rag_citations_in_na(
        na_report=None,
        retrieved_case_ids=["v7/case_a"],
        injected_lesson_ids=["L01"],
    )
    assert result == {
        "cited_case_ids": [],
        "cited_lesson_ids": [],
        "any_citation": False,
    }


def test_citation_detection_finds_both_kinds_simultaneously():
    na = _FakeNAReport(
        summary="Per case v7/case_a and lesson L14, the HSS is the suspect.",
        hypotheses=[_FakeHypothesis("h1")],
    )
    result = _detect_rag_citations_in_na(
        na_report=na,
        retrieved_case_ids=["v7/case_a", "v7/case_b"],
        injected_lesson_ids=["L01", "L14"],
    )
    assert result["cited_case_ids"] == ["v7/case_a"]
    assert result["cited_lesson_ids"] == ["L14"]
    assert result["any_citation"] is True


# ─────────────────────────────────────────────────────────────────────
# Recorder rendering — sanity tests on the three subsections
# ─────────────────────────────────────────────────────────────────────


def test_recorder_renders_rag_disabled_section():
    from agentic_chaos.recorder import _format_rag_observability
    section = _format_rag_observability(
        rag_metadata={"status": "rag_disabled", "summary": "rag_disabled", "hits": []},
        lessons_metadata={
            "status": "lessons_disabled", "summary": "lessons_disabled",
            "lesson_ids": [], "lesson_count": 0, "block_chars": 0,
        },
        na_citations={"cited_case_ids": [], "cited_lesson_ids": [], "any_citation": False},
    )
    text = "\n".join(section)
    assert "RAG retrieval" in text
    assert "Operational lessons" in text
    assert "NA citations" in text
    assert "rag_disabled" in text
    assert "lessons_disabled" in text
    assert "No verbatim citations" in text


def test_recorder_renders_hits_table_with_similarity_percent():
    from agentic_chaos.recorder import _format_rag_observability
    section = _format_rag_observability(
        rag_metadata={
            "status": "hits", "summary": "hits=2, top_sim=0.62",
            "index_dir": "/tmp/rag_index",
            "corpus_size": 97,
            "anomaly_flag_count": 3,
            "classifier_label": "mixed",
            "k": 5, "min_similarity": 0.4,
            "block_chars": 14400,
            "hits": [
                {
                    "rank": 0, "similarity": 0.6234,
                    "case_id": "v7/test_a", "scenario_name": "HSS Unresponsive",
                    "ground_truth_affected_components": ["pyhss"],
                    "ground_truth_failure_domain": "ims_signaling",
                    "agent_version": "v7", "score_pct": 100,
                    "diagnosis_primary_suspect_nf": "pyhss",
                    "source_episode_path": "/tmp/test_a.json",
                },
                {
                    "rank": 1, "similarity": 0.4501,
                    "case_id": "v7/test_b", "scenario_name": "Cascading IMS",
                    "ground_truth_affected_components": ["pyhss", "scscf"],
                    "ground_truth_failure_domain": "ims_signaling",
                    "agent_version": "v7", "score_pct": 100,
                    "diagnosis_primary_suspect_nf": "pyhss",
                    "source_episode_path": "/tmp/test_b.json",
                },
            ],
        },
        lessons_metadata={
            "status": "injected", "summary": "lessons=15, chars=14400",
            "path": "/tmp/lessons.yaml", "lesson_ids": ["L01", "L14"],
            "lesson_count": 2, "block_chars": 14400,
        },
        na_citations={
            "cited_case_ids": ["v7/test_a"],
            "cited_lesson_ids": ["L14"],
            "any_citation": True,
        },
    )
    text = "\n".join(section)
    assert "| Rank | Sim | Case ID" in text  # table header
    assert "62%" in text and "45%" in text   # similarity rendered as %
    assert "v7/test_a" in text and "v7/test_b" in text
    # Lessons block rendered with IDs.
    assert "L01" in text and "L14" in text
    # NA citation block shows the cited case + lesson.
    assert "Cited case IDs" in text
    assert "Cited lesson IDs" in text


def test_recorder_renders_localized_branch_as_did_not_run():
    """When the localized branch fired, Phase 2.5 + NA didn't run — all
    three metadata blobs are None and the section says so explicitly."""
    from agentic_chaos.recorder import _format_rag_observability
    section = _format_rag_observability(
        rag_metadata=None, lessons_metadata=None, na_citations=None,
    )
    text = "\n".join(section)
    assert "did not run" in text
    assert "localized" in text  # the explanation references the localized branch
