"""Unit tests for the RAG episode parser.

R1 acceptance:
  - Parses at least one real v5, one v6, one v7 episode.
  - `parse_corpus()` returns the union without crashing.
  - The CLI `stats` command runs over real corpora end-to-end.
  - `RetrievedCase` render methods produce non-empty markdown.

Fixtures: we test directly against real episode files checked into
the repo so the parser stays honest about schema drift. If a fixture
file is renamed or removed, the test breaks loudly — fix the fixture
reference, don't loosen the test.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agentic_ops_common.rag import (
    FlagSummary,
    RetrievedCase,
    parse_corpus,
    parse_episode,
)
from agentic_ops_common.rag.parser import (
    _parse_v6_flags_from_markdown,
    _parse_anomaly_header,
    _split_metric_key,
    main as cli_main,
)

# Fixture episode files. One representative per agent version.
#
# v5 — minimal challenge_result, no screener output. Tests the "case
#      without flags" path.
# v6 — bullet-with-direction anomaly_report (the dominant format,
#      93/108 episodes). The older table-format episodes (5/108) are
#      covered by `test_v6_table_format_parser_handles_legacy_episodes`.
# v7 — episode with structured symptom_classification + walker output
#      populated.
_V5_FIXTURE = Path(
    "agentic_ops_v5/docs/agent_logs/run_20260401_023008_gnb_radio_link_failure.json"
)
_V6_FIXTURE = Path(
    "agentic_ops_v6/docs/agent_logs/run_20260420_210314_p_cscf_latency.json"
)
_V6_TABLE_FIXTURE = Path(
    "agentic_ops_v6/docs/agent_logs/run_20260420_040523_gnb_radio_link_failure.json"
)
_V7_FIXTURE = Path(
    "agentic_ops_v7/docs/agent_logs/run_20260509_140213_call_quality_degradation.json"
)

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _abs(rel: Path) -> Path:
    return _REPO_ROOT / rel


# ─────────────────────────────────────────────────────────────────────
# Per-version parse tests
# ─────────────────────────────────────────────────────────────────────


def test_parse_v5_episode_basics():
    """v5 has no screener output. Verifies the parser gracefully emits
    a case with empty flags + populated scenario/score/ground-truth."""
    case = parse_episode(_abs(_V5_FIXTURE))
    assert case is not None
    assert case.agent_version == "v5"
    assert case.parsed_from == "json"
    assert case.scenario_name  # non-empty
    assert isinstance(case.score_pct, int)
    assert 0 <= case.score_pct <= 100
    # v5 didn't record screener output
    assert case.anomaly_top_flags == []
    # v5 has rca_label so ground truth is populated
    assert case.ground_truth_affected_components
    assert case.ground_truth_failure_domain
    # v5 didn't run the classifier or walker
    assert case.classifier_label is None
    assert case.walker_localized is None


def test_parse_v6_episode_extracts_flags_from_markdown():
    """v6 stores anomaly_report as markdown; the regex parser must
    recover structured flags + the bucket header."""
    case = parse_episode(_abs(_V6_FIXTURE))
    assert case is not None
    assert case.agent_version == "v6"
    assert case.parsed_from == "json"
    # v6 episodes record screener output as markdown — parser must lift
    # at least one flag.
    assert len(case.anomaly_top_flags) >= 1
    flag = case.anomaly_top_flags[0]
    assert flag.metric
    assert flag.component
    assert flag.severity in ("HIGH", "MEDIUM", "LOW")
    assert flag.direction in ("spike", "drop", "shift", "zero")
    # v6 doesn't run the v7 classifier or walker
    assert case.classifier_label is None
    assert case.walker_localized is None


def test_v6_table_format_parser_handles_legacy_episodes():
    """Older v6 episodes use a markdown table for the anomaly report
    instead of bullet rows. The parser falls back to a table-aware
    extractor and infers direction from current vs learned-normal."""
    case = parse_episode(_abs(_V6_TABLE_FIXTURE))
    assert case is not None
    assert case.agent_version == "v6"
    assert len(case.anomaly_top_flags) >= 1
    # Direction is inferred from value comparison; for this fixture
    # several rows have learned_normal > 0 and current = 0, so 'drop'
    # is expected somewhere.
    directions = {f.direction for f in case.anomaly_top_flags}
    assert directions.issubset({"spike", "drop", "shift", "zero"})


def test_parse_v7_episode_uses_structured_classification():
    """v7 has symptom_classification with pre-bucketed flags + walker
    output. Verifies the structured path is used (richer than v6's regex)."""
    case = parse_episode(_abs(_V7_FIXTURE))
    assert case is not None
    assert case.agent_version == "v7"
    assert case.parsed_from == "json"
    assert case.anomaly_top_flags  # structured flags present
    # Walker output is populated for v7
    assert case.walker_localized is not None
    # Classifier label is one of the known values
    assert case.classifier_label in (
        "transport_layer", "application_layer", "mixed",
    )
    # v7 carries structured diagnosis fields
    assert case.diagnosis_verdict_kind is not None


# ─────────────────────────────────────────────────────────────────────
# Corpus walk
# ─────────────────────────────────────────────────────────────────────


def test_parse_corpus_walks_real_repo():
    """End-to-end corpus walk over all three agent_logs dirs.

    Acceptance: returns a non-empty list with cases from each version.
    Skip rate (cases that fail to parse) stays under 5% per R1's
    acceptance criteria.
    """
    roots = [
        _abs(Path("agentic_ops_v5/docs/agent_logs")),
        _abs(Path("agentic_ops_v6/docs/agent_logs")),
        _abs(Path("agentic_ops_v7/docs/agent_logs")),
    ]
    cases = parse_corpus(roots)
    assert cases, "Expected at least one parsed case"

    # At least one of each version present.
    versions = {c.agent_version for c in cases}
    assert versions == {"v5", "v6", "v7"}, (
        f"Expected v5/v6/v7 representation; got {versions}"
    )

    # Skip rate under 5%.
    from agentic_ops_common.rag.parser import _count_files
    total = _count_files(roots)
    skip_rate = (total - len(cases)) / total if total else 0
    assert skip_rate < 0.05, (
        f"Parser skip rate {skip_rate:.1%} exceeds R1's 5% threshold "
        f"({total - len(cases)} skipped of {total})"
    )


# ─────────────────────────────────────────────────────────────────────
# Schema render methods
# ─────────────────────────────────────────────────────────────────────


def test_render_for_prompt_default_includes_provenance():
    case = parse_episode(_abs(_V7_FIXTURE))
    assert case is not None
    rendered = case.render_for_prompt("default")
    assert case.case_id in rendered
    assert str(case.score_pct) in rendered
    assert case.source_episode_path in rendered, (
        "Default render must cite the source path for provenance"
    )


def test_render_for_prompt_compact_is_one_block():
    case = parse_episode(_abs(_V7_FIXTURE))
    assert case is not None
    rendered = case.render_for_prompt("compact")
    # Compact form fits on one paragraph (no markdown headers).
    assert "###" not in rendered
    assert case.case_id in rendered


def test_render_for_prompt_full_is_json():
    case = parse_episode(_abs(_V7_FIXTURE))
    assert case is not None
    rendered = case.render_for_prompt("full")
    assert "```json" in rendered
    assert case.case_id in rendered


def test_retrieval_key_text_concatenates_flag_signatures():
    case = parse_episode(_abs(_V7_FIXTURE))
    assert case is not None
    key = case.retrieval_key_text()
    assert key
    # Each flag signature should appear verbatim in the key.
    for flag in case.anomaly_top_flags:
        assert flag.signature() in key
    # Scenario suffix.
    assert f"scenario: {case.scenario_name}" in key


def test_flag_summary_signature_form():
    f = FlagSummary(
        metric="rtpengine_loss_ratio",
        component="derived",
        direction="spike",
        severity="MEDIUM",
    )
    assert f.signature() == "derived.rtpengine_loss_ratio:spike:MEDIUM"


# ─────────────────────────────────────────────────────────────────────
# Internal helper coverage
# ─────────────────────────────────────────────────────────────────────


def test_split_metric_key_on_first_dot():
    # The screener split rule: split on the FIRST dot.
    assert _split_metric_key("derived.rtpengine_loss_ratio") == (
        "derived", "rtpengine_loss_ratio",
    )
    assert _split_metric_key("normalized.icscf.cdp_replies_per_ue") == (
        "normalized", "icscf.cdp_replies_per_ue",
    )
    assert _split_metric_key("icscf.cdp:average_response_time") == (
        "icscf", "cdp:average_response_time",
    )
    # Unrecognized form: fall back to ('unknown', key)
    assert _split_metric_key("nodotskey") == ("unknown", "nodotskey")


def test_parse_v6_flags_from_markdown_handles_minimal_form():
    """The simplest legal flag row — metric + (severity, direction).
    Older v6 markdowns sometimes lack the value pair."""
    md = (
        "- **`derived.icscf_uar_timeout_ratio`** — current **0.30** vs "
        "learned baseline **0.00** (HIGH, spike).\n"
    )
    flags = _parse_v6_flags_from_markdown(md)
    assert len(flags) == 1
    assert flags[0].metric == "icscf_uar_timeout_ratio"
    assert flags[0].component == "derived"
    assert flags[0].direction == "spike"
    assert flags[0].severity == "HIGH"
    assert flags[0].current == 0.30
    assert flags[0].learned_normal == 0.0


def test_parse_anomaly_header_extracts_score_and_bucket():
    md = (
        "**ANOMALY DETECTED.** Overall anomaly score: 35.16 "
        "(per-bucket threshold: 26.31, context bucket (0, 1), "
        "trained on 323 healthy snapshots).\n"
    )
    score, bucket = _parse_anomaly_header(md)
    assert score == 35.16
    assert bucket == (0, 1)


def test_parse_anomaly_header_returns_none_when_absent():
    score, bucket = _parse_anomaly_header("no header text here")
    assert score is None
    assert bucket is None


# ─────────────────────────────────────────────────────────────────────
# CLI smoke test
# ─────────────────────────────────────────────────────────────────────


def test_cli_stats_runs_over_real_corpus(capsys):
    """The R1 smoke test — `python -m agentic_ops_common.rag.parser stats`
    must run to completion on the real repo."""
    rc = cli_main([
        "stats",
        str(_abs(Path("agentic_ops_v5/docs/agent_logs"))),
        str(_abs(Path("agentic_ops_v6/docs/agent_logs"))),
        str(_abs(Path("agentic_ops_v7/docs/agent_logs"))),
    ])
    assert rc == 0
    captured = capsys.readouterr()
    assert "Walked" in captured.out
    assert "Parsed:" in captured.out


def test_cli_show_renders_a_single_case(capsys):
    rc = cli_main(["show", str(_abs(_V7_FIXTURE)), "--verbosity", "compact"])
    assert rc == 0
    captured = capsys.readouterr()
    assert "v7/" in captured.out


def test_cli_show_returns_error_on_unparseable(capsys):
    rc = cli_main(["show", "/nonexistent/path/run_fake.json"])
    assert rc == 1
