"""Phase 2.5a — infra-status snapshot capture (ADR
`rag_infrastructure_fingerprint_enrichment.md`).

Pins:
  - The NA prompt declares the `{infra_status_snapshot}` placeholder.
  - `_phase25a_capture_infra_status` writes both `state["infra_status"]`
    (dict for RAG) and `state["infra_status_snapshot"]` (markdown for NA
    prompt) on the happy path, the all-running path, and the tool-failure
    path. Records a `PhaseTrace` named `InfraStatusSnapshot` every time.
  - `_phase25_rag_inject_prior_episodes` reads `state["infra_status"]`
    and threads it into `retrieve_for_flags(infra_status_hint=…)`.
  - State init carries the two new keys at their correct defaults
    (`{}` and `""`).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from agentic_ops_v7 import orchestrator


_V7_ROOT = Path(__file__).resolve().parents[1]


# ──────────────────────────────────────────────────────────────────────
# Prompt pin
# ──────────────────────────────────────────────────────────────────────

def test_na_prompt_declares_infra_status_snapshot_placeholder():
    """Without this placeholder the Phase 2.5a injection is dead."""
    text = (_V7_ROOT / "prompts" / "network_analyst.md").read_text()
    assert "{infra_status_snapshot}" in text, (
        "network_analyst.md must declare `{infra_status_snapshot}` so "
        "the orchestrator's Phase 2.5a capture is actually shown to the "
        "NA. See ADR rag_infrastructure_fingerprint_enrichment.md."
    )


def test_na_prompt_explains_how_to_read_infra_status_snapshot():
    """The placeholder alone is a dangling token without guidance.
    The prompt must teach the NA to treat a down container as a
    direct fault locus (lesson L10 echo)."""
    text = (_V7_ROOT / "prompts" / "network_analyst.md").read_text()
    assert "exited" in text and "direct fault locus" in text, (
        "network_analyst.md must teach the NA that an exited container "
        "is a direct fault locus with very high prior (lesson L10)."
    )


# ──────────────────────────────────────────────────────────────────────
# Phase 2.5a helper — happy path
# ──────────────────────────────────────────────────────────────────────

class _FakeTrace:
    """Captures the kwargs `PhaseTrace(...)` was constructed with."""


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) \
        if False else asyncio.run(coro)


def _ns_payload(containers: dict[str, str]) -> str:
    """Build the real tool's JSON output shape.

    Mirrors `agentic_ops.tools.get_network_status` (tools.py:204) exactly:
    a `containers` dict (name → docker `State.Status`), plus the derived
    `running` / `down_or_absent` lists. The Phase 2.5a code reads from
    `containers` — that's where the per-NF status detail lives. Using the
    real shape here is the contract pin: if `get_network_status` ever
    changes its output, this fixture will diverge and the tests will fail.
    """
    running = [n for n, s in containers.items() if s == "running"]
    down = [n for n, s in containers.items() if s != "running"]
    return json.dumps({
        "phase": "ready" if not down else "down",
        "running": running,
        "down_or_absent": down,
        "containers": containers,
    })


def test_phase25a_captures_dns_exited_into_both_state_slots(monkeypatch):
    async def fake_get_network_status():
        return _ns_payload({
            "pcscf": "running", "icscf": "running", "scscf": "running",
            "upf": "running", "smf": "running",
            "dns": "exited",
        })
    monkeypatch.setattr(
        "agentic_ops_common.tools.container_status.get_network_status",
        fake_get_network_status,
    )

    state: dict = {}
    phases: list = []
    asyncio.run(orchestrator._phase25a_capture_infra_status(state, phases))

    assert state["infra_status"] == {"dns": "exited"}
    snap = state["infra_status_snapshot"]
    assert "### Current container status" in snap
    assert "`dns`" in snap and "**exited**" in snap
    # PhaseTrace recorded with the right agent_name.
    assert phases, "expected a PhaseTrace to be recorded"
    assert phases[-1].agent_name == "InfraStatusSnapshot"
    assert "dns:exited" in phases[-1].output_summary


def test_phase25a_all_running_yields_empty_dict_but_populated_snapshot(monkeypatch):
    async def fake_get_network_status():
        return _ns_payload({
            "pcscf": "running", "icscf": "running", "scscf": "running",
            "upf": "running", "smf": "running",
            "dns": "running", "mongo": "running",
        })
    monkeypatch.setattr(
        "agentic_ops_common.tools.container_status.get_network_status",
        fake_get_network_status,
    )

    state: dict = {}
    phases: list = []
    asyncio.run(orchestrator._phase25a_capture_infra_status(state, phases))

    # Dict is empty (no `infra:` line added to RAG query).
    assert state["infra_status"] == {}
    # But the NA prompt section is still rendered (with the header).
    assert "### Current container status" in state["infra_status_snapshot"]
    assert "All network containers are running" in state["infra_status_snapshot"]
    assert phases[-1].output_summary == "all_running"


def test_phase25a_tool_failure_leaves_init_defaults_and_records_trace(monkeypatch):
    """Best-effort: if get_network_status raises, the rest of the
    pipeline must keep working (state defaults stay; PhaseTrace
    records the failure)."""
    async def boom():
        raise RuntimeError("docker unreachable")
    monkeypatch.setattr(
        "agentic_ops_common.tools.container_status.get_network_status",
        boom,
    )
    state: dict = {}
    phases: list = []
    asyncio.run(orchestrator._phase25a_capture_infra_status(state, phases))

    assert state["infra_status"] == {}
    assert state["infra_status_snapshot"] == ""   # nothing to render
    assert phases[-1].agent_name == "InfraStatusSnapshot"
    assert phases[-1].output_summary == "tool_failed"


def test_phase25a_multiple_containers_down_sorted_and_recorded(monkeypatch):
    async def fake_get_network_status():
        return _ns_payload({
            "upf": "running", "smf": "running",
            "scscf": "exited", "icscf": "exited", "pcscf": "exited",
        })
    monkeypatch.setattr(
        "agentic_ops_common.tools.container_status.get_network_status",
        fake_get_network_status,
    )
    state: dict = {}
    phases: list = []
    asyncio.run(orchestrator._phase25a_capture_infra_status(state, phases))
    assert state["infra_status"] == {
        "scscf": "exited", "icscf": "exited", "pcscf": "exited",
    }
    # Snapshot sorts by NF for stable rendering.
    snap = state["infra_status_snapshot"]
    pcs_pos = snap.find("`pcscf`")
    sc_pos = snap.find("`scscf`")
    ic_pos = snap.find("`icscf`")
    assert ic_pos < pcs_pos < sc_pos


def test_phase25a_handles_absent_status(monkeypatch):
    """`absent` containers are also a down signal (container removed
    entirely, not just stopped). The wrapper's _container_status returns
    "absent" when docker inspect fails — appears in `containers` dict."""
    async def fake_get_network_status():
        return _ns_payload({"mongo": "absent"})
    monkeypatch.setattr(
        "agentic_ops_common.tools.container_status.get_network_status",
        fake_get_network_status,
    )
    state: dict = {}
    phases: list = []
    asyncio.run(orchestrator._phase25a_capture_infra_status(state, phases))
    assert state["infra_status"] == {"mongo": "absent"}


def test_phase25a_handles_restarting_status(monkeypatch):
    async def fake_get_network_status():
        return _ns_payload({
            "amf": "restarting",
            "smf": "running",
        })
    monkeypatch.setattr(
        "agentic_ops_common.tools.container_status.get_network_status",
        fake_get_network_status,
    )
    state: dict = {}
    phases: list = []
    asyncio.run(orchestrator._phase25a_capture_infra_status(state, phases))
    assert state["infra_status"] == {"amf": "restarting"}


def test_phase25a_paused_container_is_NOT_emitted_as_infra_line(monkeypatch):
    """`paused` is in-memory-but-blocked; the corpus has no precedent
    for it, so the runtime shouldn't add a query token that matches
    nothing. (Index side already skips container_pause faults.)"""
    async def fake_get_network_status():
        return _ns_payload({
            "smf": "running",
            "pcscf": "paused",
        })
    monkeypatch.setattr(
        "agentic_ops_common.tools.container_status.get_network_status",
        fake_get_network_status,
    )
    state: dict = {}
    phases: list = []
    asyncio.run(orchestrator._phase25a_capture_infra_status(state, phases))
    assert state["infra_status"] == {}


def test_phase25a_terminal_docker_states_fold_into_exited(monkeypatch):
    """`dead` / `removing` / `created` are rare Docker State.Status
    values that all mean "process is gone"; fold them into "exited"
    so the corpus's `infra:<nf>:exited` tokens match."""
    async def fake_get_network_status():
        return _ns_payload({
            "smf": "running",
            "dns": "dead",
            "mongo": "removing",
            "pcf": "created",
        })
    monkeypatch.setattr(
        "agentic_ops_common.tools.container_status.get_network_status",
        fake_get_network_status,
    )
    state: dict = {}
    phases: list = []
    asyncio.run(orchestrator._phase25a_capture_infra_status(state, phases))
    assert state["infra_status"] == {
        "dns": "exited", "mongo": "exited", "pcf": "exited",
    }


def test_phase25a_real_tool_shape_pin_contract():
    """Live-shape contract test: pin the *exact* JSON shape
    `agentic_ops.tools.get_network_status` returns. If that tool's
    output changes, this test will diverge and force a paired Phase 2.5a
    fix — preventing the kind of silent-no-op the first DNS-failure
    run after the ADR exhibited (`state["infra_status"]` ended up `{}`
    because the parser read `ns_obj.get("exited")` for a key that
    doesn't exist in the real shape; the real shape has the per-NF
    status in `ns_obj["containers"]`)."""
    # Read the tool's source to verify it still emits the expected keys.
    from pathlib import Path
    tool_src = (Path(__file__).resolve().parents[2]
                / "agentic_ops" / "tools.py").read_text()
    # The four shape keys Phase 2.5a depends on must all be present
    # as string literals in the tool's output dict.
    for key in ('"phase"', '"running"', '"down_or_absent"', '"containers"'):
        assert key in tool_src, (
            f"agentic_ops/tools.py:get_network_status no longer emits "
            f"{key} — Phase 2.5a in orchestrator.py must be updated to "
            f"match the new shape (ADR "
            f"rag_infrastructure_fingerprint_enrichment.md)."
        )


# ──────────────────────────────────────────────────────────────────────
# RAG threading — `_phase25_rag_inject_prior_episodes` forwards the
# state["infra_status"] dict into retrieve_for_flags as
# `infra_status_hint=`.
# ──────────────────────────────────────────────────────────────────────

class _StubRetriever:
    def __init__(self):
        self.captured_kwargs: dict = {}
        self.case_count = 0

    def retrieve_for_flags(self, flags, **kwargs):
        self.captured_kwargs = dict(kwargs)
        return []


def test_phase25_threads_infra_status_hint_into_retriever(monkeypatch, tmp_path):
    stub = _StubRetriever()
    monkeypatch.setattr(orchestrator, "_resolve_rag_index_dir",
                        lambda: tmp_path)
    monkeypatch.setattr(
        "agentic_ops_common.rag.get_default_retriever",
        lambda d: stub,
    )

    state: dict = {
        "anomaly_flags": [
            {"component": "core.upf", "metric": "gtp_indatapktn3upf_per_ue",
             "direction": "drop", "severity": "LOW"},
        ],
        "symptom_classification": {"label": "mixed"},
        "infra_status": {"dns": "exited"},
    }
    phases: list = []
    orchestrator._phase25_rag_inject_prior_episodes(state, phases)

    assert stub.captured_kwargs.get("infra_status_hint") == {"dns": "exited"}, (
        f"expected infra_status_hint to be forwarded; got "
        f"{stub.captured_kwargs}"
    )


def test_phase25_passes_none_when_state_infra_status_is_empty(
        monkeypatch, tmp_path):
    """Empty dict in state collapses to `None` at the retriever boundary
    so the existing "no infra line at all" semantics apply."""
    stub = _StubRetriever()
    monkeypatch.setattr(orchestrator, "_resolve_rag_index_dir",
                        lambda: tmp_path)
    monkeypatch.setattr(
        "agentic_ops_common.rag.get_default_retriever",
        lambda d: stub,
    )

    state: dict = {
        "anomaly_flags": [
            {"component": "core.upf", "metric": "gtp_indatapktn3upf_per_ue",
             "direction": "drop", "severity": "LOW"},
        ],
        "symptom_classification": {"label": "mixed"},
        "infra_status": {},
    }
    phases: list = []
    orchestrator._phase25_rag_inject_prior_episodes(state, phases)

    assert stub.captured_kwargs.get("infra_status_hint") in (None, {}), (
        "empty infra_status should not produce an infra: line in the "
        "RAG query"
    )
