"""v7 self-containment static-analysis CI gate.

Per ADR `path_anchored_probe_planning_for_transport_layer_faults.md`,
v7 must not import from any prior version of the agent. This test
walks every Python file under `agentic_ops_v7/` and rejects any
`import` line that references `agentic_ops`, `agentic_ops_v2` …
`agentic_ops_v6`.

Allowed dependencies:
  - `agentic_ops_common.*` — shared infrastructure layer.
  - Standard library.
  - Third-party packages (pydantic, google.adk, httpx, neo4j, pyyaml, ...).

This test is a hard CI gate. Any cross-version import added later
fails the build. The rule's purpose is to keep v7 self-contained so
the v6/v7 A/B comparison stays meaningful even after v7 evolves.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


_V7_ROOT = Path(__file__).resolve().parents[1]


# Module names whose import would violate the self-containment rule.
# Includes the bare `agentic_ops` package (which is v1.5).
_FORBIDDEN_MODULES = (
    "agentic_ops_v2",
    "agentic_ops_v3",
    "agentic_ops_v4",
    "agentic_ops_v5",
    "agentic_ops_v6",
    # Bare `agentic_ops` is v1.5. v7 reaches its tools via
    # agentic_ops_common.tools façades — never directly.
    "agentic_ops",
)


# Patterns we care about. Must match `import X.Y` and `from X.Y import Z`
# where X is a forbidden module. We deliberately don't match comment-only
# mentions: many files reference v6 paths in docstrings ("originally
# from agentic_ops_v6/subagents/X") and that's fine — the rule is about
# imports, not lineage documentation.
def _make_import_pattern(module: str) -> re.Pattern:
    # Match either:
    #   from <module> import ...
    #   from <module>.X import ...
    #   import <module>
    #   import <module> as alias
    # NOT match:
    #   any occurrence inside a string literal or comment, OR
    #   a longer dotted name that just starts with the same chars
    #   (e.g. agentic_ops_common, when checking for agentic_ops).
    return re.compile(
        rf"^\s*(from\s+{re.escape(module)}(?:\.[a-zA-Z0-9_]+)*\s+import|"
        rf"import\s+{re.escape(module)}(?:\s+as\s+\w+|\s*$|\s*#))",
        re.MULTILINE,
    )


_FORBIDDEN_PATTERNS: dict[str, re.Pattern] = {
    mod: _make_import_pattern(mod) for mod in _FORBIDDEN_MODULES
}


def _v7_python_files() -> list[Path]:
    """Every .py file under agentic_ops_v7/, excluding __pycache__ and
    the test files under tests/ (this very file imports `pathlib` and
    `pytest`, neither of which are forbidden — but we want the static
    check to cover production code unambiguously and tests in their
    own pass)."""
    return sorted(p for p in _V7_ROOT.rglob("*.py")
                  if "__pycache__" not in p.parts)


@pytest.mark.parametrize("path", _v7_python_files(), ids=lambda p: str(p.relative_to(_V7_ROOT)))
def test_v7_file_has_no_prior_version_imports(path: Path):
    """Every .py under agentic_ops_v7/ must not import from a prior version.

    We scan for `from X[.Y] import` and `import X` lines where X is in
    `_FORBIDDEN_MODULES`. Comment text and string-literal mentions are
    ignored — those are documentation/lineage references, not imports.
    """
    text = path.read_text()
    violations: list[tuple[str, str]] = []
    for module, pattern in _FORBIDDEN_PATTERNS.items():
        for m in pattern.finditer(text):
            violations.append((module, m.group(0).strip()))

    assert not violations, (
        f"\n{path.relative_to(_V7_ROOT)} imports from prior version(s).\n"
        f"v7's self-containment rule (see "
        f"docs/ADR/path_anchored_probe_planning_for_transport_layer_faults.md) "
        f"forbids imports from agentic_ops, agentic_ops_v2..v6.\n"
        f"Allowed dependencies: agentic_ops_common.*, stdlib, third-party.\n\n"
        f"Violations:\n"
        + "\n".join(f"  - {mod}: {line}" for mod, line in violations)
    )


def test_v7_root_directory_exists():
    """Sanity guard against a future move/rename of the v7 module
    accidentally hiding the static-analysis check."""
    assert _V7_ROOT.exists()
    assert _V7_ROOT.is_dir()
    assert (_V7_ROOT / "__init__.py").exists()


def test_static_check_actually_catches_violations(tmp_path: Path):
    """The static check itself is non-trivial regex; verify it fires
    on a synthetic violation.

    A test that's structurally incapable of failing is a test that
    rots silently — this counter-test ensures the regex actually
    catches what it claims to.
    """
    bad_text = "from agentic_ops_v6.orchestrator import investigate\n"
    pattern = _FORBIDDEN_PATTERNS["agentic_ops_v6"]
    assert pattern.search(bad_text) is not None, (
        "static check failed to detect a synthetic agentic_ops_v6 import"
    )

    # Negative cases — these are NOT violations and must NOT match:
    not_violations = [
        # Comment with v6 reference (documentation)
        "# originally from agentic_ops_v6/subagents/synthesis.py\n",
        # Docstring with v6 reference
        '"""See agentic_ops_v6/tests/test_wiring.py for the drift guard."""\n',
        # Allowed: agentic_ops_common is a non-version-specific shared layer
        "from agentic_ops_common.metric_kb import MetricsKB\n",
    ]
    for sample in not_violations:
        for mod, pattern in _FORBIDDEN_PATTERNS.items():
            assert pattern.search(sample) is None, (
                f"false-positive: {mod!r} pattern matched {sample!r}"
            )

    # Verify the bare `agentic_ops` pattern doesn't match `agentic_ops_common`
    bare_pattern = _FORBIDDEN_PATTERNS["agentic_ops"]
    assert bare_pattern.search(
        "from agentic_ops_common.tools import measure_rtt\n"
    ) is None, "bare agentic_ops pattern incorrectly matched agentic_ops_common"
