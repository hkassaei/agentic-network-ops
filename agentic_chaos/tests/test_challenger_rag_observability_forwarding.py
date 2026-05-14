"""Regression test for the challenger shim's forwarding of v7 RAG
observability keys.

Background — the bug this pins against:

  The v7 orchestrator's `_build_result()` returns three keys for the
  Phase 2.5 / 2.5b / post-NA observability surface:
      - rag_retrieval_metadata
      - lessons_injection_metadata
      - rag_na_citations

  Between the orchestrator and the recorder sits the challenger
  (`agentic_chaos/agents/challenger.py`), which translates orchestrator
  output into the `challenge_result` dict the recorder reads. That
  translation is hand-written — every key is enumerated twice (once
  with a `_` prefix in `diagnosis_dict`, once without in
  `challenge_result`). When the observability keys were added to the
  orchestrator they weren't added to the challenger shim, and the
  recorder silently rendered the "Phase 2.5 did not run for this
  episode — typically because Phase 0.6's walker localized the fault"
  placeholder for an episode where Phase 0.6 was actually skipped
  (label=application_layer) and Phase 2.5 did run.

  See run_20260513_153832_cascading_ims_failure.{md,json} where the
  JSON has zero occurrences of these three keys despite the orchestrator
  code being committed and the observability tests passing.

These tests pin both layers of the challenger shim by reading the
source. They run without docker, async, or imports of the v7 stack,
so they fail fast in CI if a future refactor drops the wiring again.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


_CHALLENGER_PATH = (
    Path(__file__).resolve().parents[1] / "agents" / "challenger.py"
)


@pytest.fixture(scope="module")
def challenger_source() -> str:
    return _CHALLENGER_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Layer 1: diagnosis_dict (underscored keys read from orchestrator result)
# ---------------------------------------------------------------------------

# The three keys that must appear in the `diagnosis_dict` builder around
# the bottom of `_run_rca_agent`. Each maps `_<name>` to
# `result.get("<name>")`.
_DIAGNOSIS_DICT_KEYS = [
    ("_rag_retrieval_metadata", "rag_retrieval_metadata"),
    ("_lessons_injection_metadata", "lessons_injection_metadata"),
    ("_rag_na_citations", "rag_na_citations"),
]


@pytest.mark.parametrize("dict_key,result_key", _DIAGNOSIS_DICT_KEYS)
def test_diagnosis_dict_reads_observability_key_from_result(
    challenger_source: str, dict_key: str, result_key: str,
) -> None:
    """Each observability key must be read from `result.get(<name>)`."""
    pattern = rf'"{re.escape(dict_key)}":\s*result\.get\("{re.escape(result_key)}"\)'
    assert re.search(pattern, challenger_source), (
        f"`diagnosis_dict` builder is missing "
        f'`"{dict_key}": result.get("{result_key}")` — the challenger '
        f"will drop the orchestrator's {result_key} on the floor and "
        f"the recorder will render the misleading 'Phase 2.5 did not "
        f"run' placeholder."
    )


# ---------------------------------------------------------------------------
# Layer 2: challenge_result (recorder-facing keys read from diagnosis_dict)
# ---------------------------------------------------------------------------

# The three keys that must appear in the `challenge_result` builder. Each
# maps the unprefixed key to `diagnosis_dict.get("_<name>")`.
_CHALLENGE_RESULT_KEYS = [
    ("rag_retrieval_metadata", "_rag_retrieval_metadata"),
    ("lessons_injection_metadata", "_lessons_injection_metadata"),
    ("rag_na_citations", "_rag_na_citations"),
]


@pytest.mark.parametrize("result_key,dict_key", _CHALLENGE_RESULT_KEYS)
def test_challenge_result_forwards_observability_key(
    challenger_source: str, result_key: str, dict_key: str,
) -> None:
    """Each observability key must be forwarded into `challenge_result`."""
    pattern = (
        rf'"{re.escape(result_key)}":\s*diagnosis_dict\.get\("{re.escape(dict_key)}"\)'
    )
    assert re.search(pattern, challenger_source), (
        f"`challenge_result` builder is missing "
        f'`"{result_key}": diagnosis_dict.get("{dict_key}")` — the '
        f"recorder reads via `challenge.get(\"{result_key}\")` and "
        f"will see None even though the orchestrator emitted the "
        f"observability metadata."
    )


# ---------------------------------------------------------------------------
# Recorder side: the recorder reads from these keys
# ---------------------------------------------------------------------------

_RECORDER_PATH = (
    Path(__file__).resolve().parents[1] / "recorder.py"
)


def test_recorder_reads_observability_keys_from_challenge_result() -> None:
    """The recorder must read all three keys from the challenge_result
    dict. If any read is dropped the section will silently render the
    'did not run' placeholder for episodes that actually did run."""
    recorder_source = _RECORDER_PATH.read_text(encoding="utf-8")
    for key in (
        "rag_retrieval_metadata",
        "lessons_injection_metadata",
        "rag_na_citations",
    ):
        pattern = rf'challenge\.get\("{re.escape(key)}"\)'
        assert re.search(pattern, recorder_source), (
            f"recorder.py does not read challenge.get(\"{key}\") — "
            f"the corresponding observability subsection will always "
            f"render the 'did not run' placeholder."
        )
