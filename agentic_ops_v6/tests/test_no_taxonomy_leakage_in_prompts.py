"""CI-enforcing audit test: prompts and prompt-adjacent surfaces must
not contain references to the project's internal validator taxonomy
(Decision-letter labels, A1/A2 sub-check ids, "linter feedback",
"guardrail rejection", named ADR filenames, pipeline phase numbers).

Scope: only LLM-facing surfaces are audited. Code comments, module
docstrings on internal Python files, and `# ...` source comments are
explicitly out of scope per the ADR (`internal_taxonomy_must_not_leak_to_llm.md`).

What IS audited:
- Every `.md` file under `agentic_ops_v6/prompts/`.
- Every Pydantic `Field(description=...)` argument and every
  user-facing class docstring under `agentic_ops_v6/models.py` (these
  serialize into the JSON schema that's sent to the LLM as part of
  structured output).

A failing assertion here usually means a developer added a new prompt
section or a new Pydantic field that re-introduced taxonomy. The fix
is to rewrite the offending text in domain terms only, mirroring the
guidance in `docs/ADR/internal_taxonomy_must_not_leak_to_llm.md`.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from agentic_ops_v6.guardrails.llm_output_sanitizer import LEAK_PATTERN

_V6_ROOT = Path(__file__).resolve().parents[1]
_PROMPTS_DIR = _V6_ROOT / "prompts"
_MODELS_PATH = _V6_ROOT / "models.py"


def _gather_prompt_files() -> list[Path]:
    return sorted(_PROMPTS_DIR.glob("*.md"))


@pytest.mark.parametrize("prompt_path", _gather_prompt_files(),
                         ids=lambda p: p.name)
def test_prompt_md_has_no_taxonomy_leak(prompt_path: Path) -> None:
    """No prompt .md may reference the internal validator taxonomy."""
    text = prompt_path.read_text(encoding="utf-8")
    hits = LEAK_PATTERN.findall(text)
    assert not hits, (
        f"{prompt_path.relative_to(_V6_ROOT)} contains internal-taxonomy "
        f"references that must be rewritten in domain terms only: "
        f"{sorted(set(hits))}"
    )


def _extract_llm_facing_strings_from_models() -> list[tuple[str, str]]:
    """Return (location, string) pairs for every LLM-visible string
    literal in models.py — class docstrings (used as JSON schema title /
    description) and `Field(description=...)` arguments.

    Out of scope: regular module-level comments, function docstrings,
    private helper docstrings.
    """
    source = _MODELS_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    out: list[tuple[str, str]] = []

    for node in ast.walk(tree):
        # Pydantic class docstrings — emitted as the model's JSON
        # schema description.
        if isinstance(node, ast.ClassDef):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                out.append((f"class {node.name} docstring", doc))

        # Field(description="...") — emitted as property description.
        if isinstance(node, ast.Call):
            func = node.func
            is_field_call = (
                (isinstance(func, ast.Name) and func.id == "Field")
                or (isinstance(func, ast.Attribute)
                    and func.attr == "Field")
            )
            if not is_field_call:
                continue
            for kw in node.keywords:
                if kw.arg != "description":
                    continue
                # Resolve a Constant or a parenthesized concatenation
                # of Constants.
                value = _resolve_string_expr(kw.value)
                if value is not None:
                    out.append((
                        f"Field(description=...) at line {kw.value.lineno}",
                        value,
                    ))
    return out


def _resolve_string_expr(node: ast.expr) -> str | None:
    """Return the string value of a literal-string expression, or None
    if the node is not a literal-string expression. Handles a single
    `Constant` or implicit concatenation via parenthesized adjacent
    literals (which the parser already folds into a single Constant)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def test_models_field_descriptions_have_no_taxonomy_leak() -> None:
    """Pydantic class docstrings and Field descriptions reach the LLM
    via structured-output JSON schema — they must be taxonomy-free."""
    pairs = _extract_llm_facing_strings_from_models()
    assert pairs, "expected to extract at least one LLM-facing string"
    leaky: list[tuple[str, list[str]]] = []
    for location, text in pairs:
        hits = LEAK_PATTERN.findall(text)
        if hits:
            leaky.append((location, sorted(set(hits))))
    assert not leaky, (
        "models.py LLM-facing strings contain internal-taxonomy "
        f"references: {leaky}"
    )


def test_leak_pattern_passes_legitimate_domain_terms() -> None:
    """Sanity-check the regex: legitimate domain terms must NOT match
    so we don't false-positive the audit."""
    legitimate = [
        "hypothesis",
        "falsification plan",
        "compositional probe",
        "mechanism scoping",
        "primary suspect NF",
        "anomaly screener",
        "investigator verdict",
        "candidate pool",
        "amf",
        "RTPEngine",
        "5GC",
        # Words that contain forbidden substrings but aren't actual hits:
        "Adriatic",       # contains "ADR" but not a leak
        "padron",         # contains "ADR" with letter neighbours
        "data",           # contains "A" but A0+ requires digit
    ]
    for term in legitimate:
        assert not LEAK_PATTERN.search(term), (
            f"legitimate domain term {term!r} false-positived against "
            f"LEAK_PATTERN — the regex needs to be tightened"
        )


@pytest.mark.parametrize("leaky", [
    "Decision A",
    "Decision G",
    "addresses linter feedback A1",
    "the post-IG linter rejection",
    "guardrail rejection",
    "removed per ADR remove_log_probes_from_investigator.md",
    "Phase 6.5 candidate pool",
    "PR 5.5b ships the structured output",
    "sub-check A2",
])
def test_leak_pattern_catches_known_leaks(leaky: str) -> None:
    """Each known leak shape (one per ADR pattern variant) must fire."""
    assert LEAK_PATTERN.search(leaky), (
        f"LEAK_PATTERN failed to catch known leak {leaky!r}"
    )
