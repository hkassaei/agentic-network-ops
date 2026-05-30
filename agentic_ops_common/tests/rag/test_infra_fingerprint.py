"""RAG infrastructure-NF fingerprint — index, query, end-to-end retrieval.

Pins ADR `rag_infrastructure_fingerprint_enrichment.md`:

  - `_extract_infra_status_from_faults` against real DNS / mongo / gNB
    container-kill JSON fixtures and a network-impairment negative
    fixture (network_latency yields {}).
  - `RetrievedCase.retrieval_key_text()` emits sorted `infra:<nf>:<status>`
    lines between flag signatures and the scenario suffix.
  - `_build_query_text_from_flags` honours `infra_status_hint=`; empty
    / None hint reproduces today's byte-for-byte output (backward-compat).
  - End-to-end: a synthetic corpus mixing one DNS case with four IMS-
    cascade lookalikes — a DNS-shaped query with `infra_status_hint=
    {"dns":"exited"}` retrieves the DNS case at rank 1. This is the
    regression test for the actual failure that motivated the ADR
    (run_20260530_011636_dns_failure ranked the real DNS precedent #4
    behind S-CSCF Crash / P-CSCF Latency / AMF Restart / Data Plane).
  - Audit trail: every `infra:` line in a parsed case traces back to a
    `fault_id` in the source episode's `faults[]` array.
"""

from __future__ import annotations

from pathlib import Path

from agentic_ops_common.rag.index import CaseIndex
from agentic_ops_common.rag.parser import (
    _extract_infra_status_from_faults,
    parse_episode,
)
from agentic_ops_common.rag.retriever import (
    _build_query_text_from_flags,
    EpisodeRetriever,
)
from agentic_ops_common.rag.schema import FlagSummary, RetrievedCase


# ──────────────────────────────────────────────────────────────────────
# Fixtures — minimal fault-block shapes mirroring real episode JSON
# ──────────────────────────────────────────────────────────────────────

def _fault(fault_type: str, target: str, verified: bool = True,
           verification_result: str = "Expected 'exited', got 'exited'") -> dict:
    return {
        "fault_id": f"f_{fault_type}_{target}",
        "fault_type": fault_type,
        "target": target,
        "params": {},
        "verified": verified,
        "verification_result": verification_result,
    }


def _episode(faults: list[dict]) -> dict:
    return {"faults": faults}


# ──────────────────────────────────────────────────────────────────────
# `_extract_infra_status_from_faults` — the index-side extraction rule
# ──────────────────────────────────────────────────────────────────────

def test_container_kill_dns_yields_infra_dns_exited():
    """The DNS scenario shape: container_kill on dns, verified down."""
    out = _extract_infra_status_from_faults(_episode([_fault("container_kill", "dns")]))
    assert out == {"dns": "exited"}


def test_container_kill_mongo_yields_infra_mongo_exited():
    out = _extract_infra_status_from_faults(_episode([_fault("container_kill", "mongo")]))
    assert out == {"mongo": "exited"}


def test_container_stop_treated_same_as_kill():
    """container_stop produces the same observable down state."""
    out = _extract_infra_status_from_faults(_episode([_fault("container_stop", "pcscf")]))
    assert out == {"pcscf": "exited"}


def test_v6_gnb_radio_link_kill_extracts_nr_gnb():
    """Pin against the random v6 fixture used in the ADR validation."""
    out = _extract_infra_status_from_faults(_episode([_fault("container_kill", "nr_gnb")]))
    assert out == {"nr_gnb": "exited"}


def test_network_latency_emits_no_infra_line():
    """Network impairments must NOT produce an `infra:` line — pcscf is
    still running, so the screener fingerprint is the right signal."""
    out = _extract_infra_status_from_faults(
        _episode([_fault("network_latency", "pcscf",
                         verification_result="Latency injected: 200ms")])
    )
    assert out == {}


def test_network_loss_emits_no_infra_line():
    out = _extract_infra_status_from_faults(
        _episode([_fault("network_loss", "upf",
                         verification_result="Loss injected: 5%")])
    )
    assert out == {}


def test_container_pause_emits_no_infra_line():
    """container_pause leaves the container running-but-blocked;
    get_network_status returns 'running', so emitting `infra:` would
    create a phantom match."""
    out = _extract_infra_status_from_faults(
        _episode([_fault("container_pause", "mongo",
                         verification_result="Paused successfully")])
    )
    assert out == {}


def test_unverified_kill_is_skipped():
    """If the chaos harness couldn't confirm the down state, do not
    poison the corpus with an unverified `infra:` line."""
    f = _fault("container_kill", "dns")
    f["verified"] = False
    out = _extract_infra_status_from_faults(_episode([f]))
    assert out == {}


def test_verification_result_without_exited_marker_is_skipped():
    """`verified=True` alone isn't enough — the result text must
    confirm the observed `exited` state."""
    f = _fault("container_kill", "dns",
               verification_result="Expected 'exited', got 'running'")
    out = _extract_infra_status_from_faults(_episode([f]))
    assert out == {}


def test_unknown_nf_target_is_dropped_defensively():
    """Targets outside the components allowlist are skipped to keep
    the corpus clean of junk strings."""
    out = _extract_infra_status_from_faults(
        _episode([_fault("container_kill", "totally_made_up_nf")])
    )
    assert out == {}


def test_no_faults_block_yields_empty_dict():
    """v5 cases / malformed JSON missing the `faults[]` key behave
    gracefully — empty dict, no exception."""
    assert _extract_infra_status_from_faults({}) == {}
    assert _extract_infra_status_from_faults({"faults": None}) == {}
    assert _extract_infra_status_from_faults({"faults": "not a list"}) == {}


def test_multiple_container_kills_all_captured():
    """Cascading-IMS-failure-style scenarios kill several containers;
    every verified one must appear."""
    out = _extract_infra_status_from_faults(_episode([
        _fault("container_kill", "scscf"),
        _fault("container_kill", "icscf"),
        _fault("container_kill", "pcscf"),
    ]))
    assert out == {"scscf": "exited", "icscf": "exited", "pcscf": "exited"}


# ──────────────────────────────────────────────────────────────────────
# `RetrievedCase.retrieval_key_text()` — index-side rendering
# ──────────────────────────────────────────────────────────────────────

def _case_with(infra_status: dict[str, str], flags=None,
               scenario_name="DNS Failure",
               classifier_label="mixed") -> RetrievedCase:
    return RetrievedCase(
        case_id="v7/test",
        source_episode_path="/tmp/test.json",
        agent_version="v7",
        parsed_from="json",
        scenario_name=scenario_name,
        score_pct=100,
        classifier_label=classifier_label,
        anomaly_top_flags=flags or [
            FlagSummary(metric="gtp_indatapktn3upf_per_ue",
                        component="core.upf",
                        direction="drop", severity="LOW"),
        ],
        infra_status=infra_status,
    )


def test_retrieval_key_text_emits_infra_lines_between_flags_and_scenario():
    case = _case_with({"dns": "exited"})
    text = case.retrieval_key_text()
    lines = text.split("\n")
    # Flag signature comes first.
    assert lines[0] == "core.upf.gtp_indatapktn3upf_per_ue:drop:LOW"
    # Then the infra line.
    assert "infra:dns:exited" in lines
    # Then the suffixes.
    assert lines[-2] == "scenario: DNS Failure"
    assert lines[-1] == "classifier: mixed"
    # Order: infra line between flags and scenario suffix.
    assert lines.index("infra:dns:exited") < lines.index("scenario: DNS Failure")


def test_retrieval_key_text_sorts_infra_lines_for_stability():
    """Multiple infra entries must serialise in sorted-key order so
    the same dict produces byte-identical retrieval-key text across
    rebuilds (TF-IDF determinism / cache stability)."""
    case = _case_with({"scscf": "exited", "icscf": "exited", "pcscf": "exited"})
    text = case.retrieval_key_text()
    infra_lines = [l for l in text.split("\n") if l.startswith("infra:")]
    assert infra_lines == [
        "infra:icscf:exited",
        "infra:pcscf:exited",
        "infra:scscf:exited",
    ]


def test_retrieval_key_text_empty_infra_status_unchanged():
    """Backward compat: a case with no infra_status produces a
    retrieval-key text byte-identical to the pre-ADR layout."""
    case = _case_with({})
    text = case.retrieval_key_text()
    # No `infra:` lines at all.
    assert "infra:" not in text
    # Flag + scenario + classifier — three lines exactly.
    assert text.split("\n") == [
        "core.upf.gtp_indatapktn3upf_per_ue:drop:LOW",
        "scenario: DNS Failure",
        "classifier: mixed",
    ]


# ──────────────────────────────────────────────────────────────────────
# `_build_query_text_from_flags` — runtime query rendering
# ──────────────────────────────────────────────────────────────────────

def test_query_with_infra_status_hint_includes_infra_line():
    flags = [{"component": "core.upf", "metric": "gtp_indatapktn3upf_per_ue",
              "direction": "drop", "severity": "LOW"}]
    text = _build_query_text_from_flags(
        flags, classifier_label="mixed",
        infra_status_hint={"dns": "exited"},
    )
    assert "infra:dns:exited" in text.split("\n")
    assert "classifier: mixed" in text


def test_query_without_infra_status_hint_unchanged_from_pre_adr():
    """Backward compat: omitting `infra_status_hint` reproduces the
    exact query string today's code builds. No regression on existing
    tests / behavior."""
    flags = [{"component": "core.upf", "metric": "gtp_indatapktn3upf_per_ue",
              "direction": "drop", "severity": "LOW"}]
    text_now = _build_query_text_from_flags(flags, classifier_label="mixed")
    text_old_shape = "core.upf.gtp_indatapktn3upf_per_ue:drop:LOW\nclassifier: mixed"
    assert text_now == text_old_shape


def test_query_with_empty_infra_status_hint_emits_no_infra_line():
    """Empty dict means "no infra fault observed" — must NOT emit an
    `infra:none` line (would match itself in the corpus)."""
    flags = [{"component": "core.upf", "metric": "gtp_indatapktn3upf_per_ue",
              "direction": "drop", "severity": "LOW"}]
    text = _build_query_text_from_flags(
        flags, classifier_label="mixed", infra_status_hint={},
    )
    assert "infra:" not in text
    assert text.split("\n") == [
        "core.upf.gtp_indatapktn3upf_per_ue:drop:LOW",
        "classifier: mixed",
    ]


def test_query_with_none_infra_status_hint_emits_no_infra_line():
    flags = [{"component": "core.upf", "metric": "gtp_indatapktn3upf_per_ue",
              "direction": "drop", "severity": "LOW"}]
    text = _build_query_text_from_flags(
        flags, classifier_label="mixed", infra_status_hint=None,
    )
    assert "infra:" not in text


def test_query_infra_lines_sorted_like_index_side():
    flags = [{"component": "core.upf", "metric": "gtp_indatapktn3upf_per_ue",
              "direction": "drop", "severity": "LOW"}]
    text = _build_query_text_from_flags(
        flags, infra_status_hint={"scscf": "exited", "icscf": "exited"},
    )
    infra_lines = [l for l in text.split("\n") if l.startswith("infra:")]
    assert infra_lines == ["infra:icscf:exited", "infra:scscf:exited"]


# ──────────────────────────────────────────────────────────────────────
# End-to-end retrieval — regression test for the actual ADR failure
# ──────────────────────────────────────────────────────────────────────

def _ims_cascade_flags() -> list[FlagSummary]:
    """The screener fingerprint shape that's common to many IMS-cascade
    scenarios (S-CSCF Crash, P-CSCF Latency, AMF Restart, DNS Failure)."""
    return [
        FlagSummary(metric="gtp_indatapktn3upf_per_ue",
                    component="core.upf", direction="drop", severity="LOW"),
        FlagSummary(metric="gtp_outdatapktn3upf_per_ue",
                    component="core.upf", direction="drop", severity="LOW"),
        FlagSummary(metric="bearers_per_ue",
                    component="core.smf", direction="shift", severity="MEDIUM"),
        FlagSummary(metric="rcv_requests_invite_per_ue",
                    component="ims.pcscf", direction="spike", severity="MEDIUM"),
    ]


def test_dns_query_with_infra_hint_retrieves_dns_case_at_rank_1():
    """Regression for run_20260530_011636_dns_failure: the actual DNS
    Failure precedent ranked #4 at 69% because the embedding had no
    discriminating token for "DNS exited" — the cascade signature it
    DID have (UPF GTP drops, P-CSCF INVITE spike, SMF shift) matches
    every infrastructure-cascade scenario equally well.

    With Lever 1: the `infra:dns:exited` token appears in the DNS case
    only, so cosine similarity dominates and the DNS case takes rank 1.
    """
    flags = _ims_cascade_flags()

    # One DNS case (with infra_status) + four lookalikes (without).
    cases = [
        _case_with({"dns": "exited"}, flags=flags,
                   scenario_name="DNS Failure"),
        _case_with({"scscf": "exited"}, flags=flags,
                   scenario_name="S-CSCF Crash"),
        _case_with({}, flags=flags, scenario_name="P-CSCF Latency"),
        _case_with({"amf": "exited"}, flags=flags,
                   scenario_name="AMF Restart"),
        _case_with({}, flags=flags, scenario_name="Data Plane Degradation"),
    ]
    # Set unique case_ids so we can identify the rank-1 hit unambiguously.
    for i, c in enumerate(cases):
        cases[i] = c.model_copy(update={"case_id": f"v7/case_{i}"})

    index = CaseIndex.build(cases, score_threshold=0)
    retriever = EpisodeRetriever(index)

    hits = retriever.retrieve_for_flags(
        flags,
        k=5,
        min_similarity=0.0,
        classifier_label="mixed",
        infra_status_hint={"dns": "exited"},
    )
    assert hits, "expected non-empty hits"
    assert hits[0].case.scenario_name == "DNS Failure", (
        f"expected DNS Failure at rank 1, got "
        f"{[h.case.scenario_name for h in hits]}"
    )


def test_dns_query_without_infra_hint_does_not_break_existing_retrieval():
    """Backward-compat sanity: omit the infra hint and retrieval still
    works (just doesn't get the boost). Asserts the API change is
    purely additive — no required parameter, no shape change."""
    flags = _ims_cascade_flags()
    cases = [
        _case_with({"dns": "exited"}, flags=flags, scenario_name="DNS Failure"),
        _case_with({"scscf": "exited"}, flags=flags, scenario_name="S-CSCF Crash"),
    ]
    for i, c in enumerate(cases):
        cases[i] = c.model_copy(update={"case_id": f"v7/case_{i}"})

    index = CaseIndex.build(cases, score_threshold=0)
    retriever = EpisodeRetriever(index)
    hits = retriever.retrieve_for_flags(
        flags, k=5, min_similarity=0.0, classifier_label="mixed",
    )
    # The point isn't which scenario wins (without infra hint they may
    # tie); the point is the call works and returns hits.
    assert len(hits) == 2


# ──────────────────────────────────────────────────────────────────────
# Audit trail — every `infra:` line traces back to a `fault_id`
# ──────────────────────────────────────────────────────────────────────

def test_parsed_case_infra_status_traces_back_to_fault_id():
    """Every emitted `infra:` line corresponds to a fault entry in the
    source episode JSON. We don't expose `fault_id` in `RetrievedCase`
    directly (the field is `fault_injected` which carries the full
    fault dicts), but the audit trail is: extracted target ∈
    {f['target'] for f in fault_injected}. This pin makes the
    invariant durable."""
    episode = _episode([_fault("container_kill", "dns")])
    extracted = _extract_infra_status_from_faults(episode)
    fault_targets = {f["target"] for f in episode["faults"]}
    for nf in extracted.keys():
        assert nf in fault_targets, (
            f"infra:{nf} has no corresponding fault_id in source episode"
        )


# ──────────────────────────────────────────────────────────────────────
# Real-episode parse — DNS run on disk
# ──────────────────────────────────────────────────────────────────────

def test_real_dns_episode_parses_to_infra_dns_exited():
    """Sanity check against the live `run_20260530_011636_dns_failure.json`
    on disk. If the parser produces a case at all, its infra_status must
    name dns as exited. Skipped if the file is missing (CI environments
    without the v7 logs)."""
    p = Path("agentic_ops_v7/docs/agent_logs/run_20260530_011636_dns_failure.json")
    if not p.exists():
        import pytest
        pytest.skip(f"{p} not present in this environment")
    case = parse_episode(p)
    if case is None:
        import pytest
        pytest.skip("parser returned None — episode score missing or malformed")
    assert case.infra_status == {"dns": "exited"}
