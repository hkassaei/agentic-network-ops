"""Pin: every Synthesis-emitting code path writes BOTH state keys.

`state["diagnosis_structured"]` and `state["diagnosis_report"]` carry
the same payload (the post-Synthesis DiagnosisReport, dumped to JSON)
but feed distinct downstream consumers:

  - `diagnosis_structured` is for typed downstream tooling inside the
    orchestrator and the GUI.
  - `diagnosis_report` is the one `_build_result` surfaces into the
    result dict (orchestrator.py:3104). The chaos challenger
    (`agentic_chaos/agents/challenger.py:439`) forwards it into
    `challenge_result.diagnosis_report` in the episode JSON. The RAG
    parser (`agentic_ops_common/rag/parser.py:345`) and the chaos
    recorder (`agentic_chaos/recorder.py:747+`) both read from there.

Bug A (caught 2026-05-15): the application-layer Synthesis path at
`orchestrator.py:2770-2773` wrote only `diagnosis_structured`, leaving
`challenge_result.diagnosis_report = null` in every v7 app-layer
episode. That silently corrupted the v7 portion of the RAG corpus
from the May-10 batch onward. The localized branch at line 791-792
wrote both keys correctly. Fix was a 1-line addition to match.

This test pins the parallel-write invariant structurally so the bug
can't regress silently. It reads the orchestrator source and asserts
that every place which calls `_render_diagnosis_report_to_markdown`
(the marker for a Synthesis-emit code path) is immediately followed
by writes to BOTH state keys. Catches:

  - Removing the line we just added (regression on Bug A).
  - Adding a new Synthesis-emit branch that copies only one of the two
    writes (the failure shape of the original bug).

What this test does NOT catch:
  - A new Synthesis-emit path that bypasses
    `_render_diagnosis_report_to_markdown` entirely. The structural
    grep is anchored on that call. If a future refactor splits the
    render and the state-write apart, this test will silently start
    passing on paths it no longer covers. Flagged as a known coverage
    limit per the Rule-3 commitment in
    `docs/next-work-package.md`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


_ORCH_PATH = (
    Path(__file__).resolve().parents[1] / "orchestrator.py"
)


@pytest.fixture(scope="module")
def orch_source() -> str:
    return _ORCH_PATH.read_text(encoding="utf-8")


def _find_render_call_lines(source: str) -> list[int]:
    """Return 1-indexed line numbers of every
    `_render_diagnosis_report_to_markdown(` call site, excluding the
    function definition itself."""
    lines = source.splitlines()
    out: list[int] = []
    for i, ln in enumerate(lines, start=1):
        stripped = ln.lstrip()
        # Skip the function definition line.
        if stripped.startswith("def _render_diagnosis_report_to_markdown"):
            continue
        if "_render_diagnosis_report_to_markdown(" in ln:
            out.append(i)
    return out


def test_orchestrator_has_at_least_two_synthesis_emit_sites(orch_source: str):
    """Sanity: today the orchestrator has the localized Synthesis path
    (around line 788) AND the application-layer Synthesis path (around
    line 2770). If a future refactor collapses them into one helper,
    this test should fail loudly so the maintainer revisits the
    parallel-write invariant for the new shape rather than silently
    losing coverage."""
    call_sites = _find_render_call_lines(orch_source)
    assert len(call_sites) >= 2, (
        f"Expected at least 2 _render_diagnosis_report_to_markdown call "
        f"sites in orchestrator.py (localized + app-layer Synthesis); "
        f"found {len(call_sites)} at lines {call_sites}. If a refactor "
        f"merged them, update this test."
    )


def test_every_synthesis_emit_writes_both_state_keys(orch_source: str):
    """For every site where the orchestrator renders a DiagnosisReport
    to markdown, the surrounding window MUST contain writes to BOTH
    `state["diagnosis_structured"]` AND `state["diagnosis_report"]`.

    This is the load-bearing invariant. Both keys must be written
    together because downstream consumers (RAG parser, recorder,
    challenger forwarding) read `diagnosis_report` while in-orchestrator
    typed tooling reads `diagnosis_structured`. Writing only one is
    Bug A's failure mode.
    """
    lines = orch_source.splitlines()
    call_sites = _find_render_call_lines(orch_source)

    structured_re = re.compile(r'state\["diagnosis_structured"\]\s*=')
    report_re = re.compile(r'state\["diagnosis_report"\]\s*=')

    # Window: the render-call site itself plus the next 10 lines. The
    # known writes sit on the line immediately after the render-call,
    # but the LLM-output-sanitizer or future refactors could move them
    # a few lines down; 10 is generous without crossing into the next
    # function.
    WINDOW = 10
    failures: list[tuple[int, bool, bool]] = []
    for call_line in call_sites:
        end = min(call_line + WINDOW, len(lines))
        window_text = "\n".join(lines[call_line - 1:end])
        has_structured = bool(structured_re.search(window_text))
        has_report = bool(report_re.search(window_text))
        if not (has_structured and has_report):
            failures.append((call_line, has_structured, has_report))

    assert not failures, (
        "One or more Synthesis-emit sites in orchestrator.py is missing "
        "a parallel state-key write (Bug A failure mode — see "
        "docs/next-work-package.md). Sites:\n"
        + "\n".join(
            f"  line {ln}: has_structured={s}, has_report={r}"
            for ln, s, r in failures
        )
    )


def test_build_result_surfaces_diagnosis_report_key(orch_source: str):
    """`_build_result` MUST read `state.get('diagnosis_report')` into
    the result dict under the same key. This is the contract that
    every downstream consumer relies on; without it the parallel-write
    invariant above accomplishes nothing.

    Pin both halves: the read from state AND the key name in the dict.
    """
    # `_build_result` returns a dict literal that includes
    # `"diagnosis_report": state.get("diagnosis_report")`.
    pattern = re.compile(
        r'"diagnosis_report"\s*:\s*state\.get\(\s*"diagnosis_report"\s*\)'
    )
    assert pattern.search(orch_source), (
        "`_build_result` must surface `state['diagnosis_report']` into "
        "the result dict under the key `diagnosis_report`. Without this "
        "the parallel-write invariant above doesn't reach the chaos "
        "challenger / RAG parser / recorder. Bug A class regression."
    )
