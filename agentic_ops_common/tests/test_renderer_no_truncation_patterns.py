"""Static-analysis guard against truncation patterns in the renderer.

Per ADR `expose_kb_disambiguators_to_investigator.md`, the renderer
implementation files (`agentic_ops_common/tools/diagnostic_metrics.py`
and `agentic_ops_common/tools/data_plane.py`) must not contain any
of the following patterns, because each one is a known way to lose
KB-authored content silently:

  - `.split(".")[0]`         — first-sentence shortcut (the canonical
                                bug this ADR fixes).
  - `.partition(".")`        — same shape, different stdlib call.
  - `.splitlines()[0]`       — first-line shortcut.
  - `[:N]` on KB-sourced strings — naked slice, easy to introduce by
                                accident.
  - `MAX_LEN` / `MAX_CHARS` / `truncate(...)` / `…` near KB field
                                references — explicit length caps.

The check runs over the literal source files, not their imports, so
a future edit that reintroduces any pattern fails CI before any
runtime test executes.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[2]
_FILES_UNDER_GUARD = [
    _REPO_ROOT / "agentic_ops_common" / "tools" / "diagnostic_metrics.py",
    _REPO_ROOT / "agentic_ops_common" / "tools" / "data_plane.py",
]

# Patterns that MUST NOT appear in the renderer source. Each tuple is
# (compiled_regex, human-readable name, rationale).
_FORBIDDEN_PATTERNS: list[tuple[re.Pattern, str, str]] = [
    (
        re.compile(r"""\.split\(\s*['"]\.['"]\s*\)\s*\[\s*0\s*\]"""),
        "first-sentence-via-split-on-period",
        "the original truncation that hid 30 metrics' worth of "
        "authored disambiguator content from the LLM",
    ),
    (
        re.compile(r"""\.partition\(\s*['"]\.['"]\s*\)"""),
        "first-sentence-via-partition",
        "alternate stdlib shape with the same effect as split[0]",
    ),
    (
        re.compile(r"""\.splitlines\s*\(\s*\)\s*\[\s*0\s*\]"""),
        "first-line-via-splitlines",
        "drops every line after the first — same family of bug",
    ),
    (
        re.compile(r"""\bMAX_(?:LEN|CHARS|LENGTH)\b"""),
        "MAX_LEN-style length cap",
        "explicit length cap near KB rendering — no KB field has a "
        "max length, the renderer must not impose one",
    ),
    (
        re.compile(r"""\btruncate\s*\("""),
        "truncate(...) call",
        "every truncate() call against KB-sourced text is a regression",
    ),
    (
        re.compile(r"""…"""),
        "ellipsis character (\\u2026)",
        "Unicode ellipsis is the visible signature of a string cut "
        "short for display",
    ),
]


# Regex that catches `[:N]` slicing applied to a variable whose name
# suggests KB-sourced text. Naming-sensitive so we don't false-positive
# on legitimate slices on lists / non-text data.
_SLICE_VAR_NAMES = (
    "description", "meaning", "signal", "noise", "separates",
    "disamb", "what_it", "interpretation", "kb_text", "rendered",
)
_SLICE_PATTERN = re.compile(
    r"""\b(?:""" + "|".join(_SLICE_VAR_NAMES) + r""")\w*\s*\[\s*:\s*\d+\s*\]"""
)


@pytest.mark.parametrize("path", _FILES_UNDER_GUARD, ids=lambda p: p.name)
def test_no_forbidden_truncation_patterns(path: Path):
    """Each renderer source file must contain no truncation pattern.

    A failure tells the engineer exactly which pattern matched at
    which line. The fix is to remove the pattern; the test must NOT
    be loosened to accommodate a new truncation."""
    if not path.exists():
        pytest.fail(f"Renderer source file missing: {path}")
    src = path.read_text()
    hits: list[str] = []
    for pat, name, rationale in _FORBIDDEN_PATTERNS:
        for m in pat.finditer(src):
            line_no = src[: m.start()].count("\n") + 1
            line = src.splitlines()[line_no - 1]
            hits.append(
                f"  {path.name}:{line_no}  matched={name!r}\n"
                f"    line: {line.strip()}\n"
                f"    why:  {rationale}"
            )
    if hits:
        pytest.fail(
            f"Forbidden truncation pattern(s) in {path.name}:\n"
            + "\n".join(hits)
        )


@pytest.mark.parametrize("path", _FILES_UNDER_GUARD, ids=lambda p: p.name)
def test_no_slice_on_kb_named_strings(path: Path):
    """`[:N]` slicing on a variable named like a KB field is a likely
    accidental truncation. Names checked: """ + ", ".join(_SLICE_VAR_NAMES)
    if not path.exists():
        pytest.fail(f"Renderer source file missing: {path}")
    src = path.read_text()
    hits: list[str] = []
    for m in _SLICE_PATTERN.finditer(src):
        line_no = src[: m.start()].count("\n") + 1
        line = src.splitlines()[line_no - 1]
        hits.append(
            f"  {path.name}:{line_no}  match={m.group(0)!r}\n"
            f"    line: {line.strip()}"
        )
    if hits:
        pytest.fail(
            "Suspicious `[:N]` slice on KB-named variable in "
            f"{path.name}:\n" + "\n".join(hits)
        )


def test_guard_actually_fires_on_synthetic_violation(tmp_path: Path):
    """Sanity check: the static-analysis guard must reject a file
    that contains a forbidden pattern. Sets up a temporary file and
    asserts the regex engine catches it."""
    bad = tmp_path / "bad_renderer.py"
    bad.write_text(
        "def f(x):\n"
        "    return x.description.split('.')[0]\n"
    )
    src = bad.read_text()
    # Re-use the same regex set the production guard uses.
    assert any(
        pat.search(src) for pat, _, _ in _FORBIDDEN_PATTERNS
    ), "guard regex set failed to match a known-bad sample"
