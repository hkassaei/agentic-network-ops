"""Tests for the Lesson schema + YAML loader + prompt renderer.

The contracts that matter:

  1. **Schema validation** — required fields (`id`, `title`, `rule`) raise
     on empty input; optional fields default cleanly.
  2. **YAML round-trip** — a well-formed YAML file loads into a list of
     Lesson objects with stable ordering and all fields populated.
  3. **Graceful failure** — missing file, malformed entries, wrong
     top-level shape are surfaced via `try_load_lessons` returning None
     (or `load_lessons` raising), without bringing down the orchestrator.
  4. **Render output** — non-empty lesson list produces non-empty
     markdown; empty list produces empty string (so the caller's prompt
     template can substitute a "no lessons" note).
  5. **Default corpus is loadable** — the shipped `lessons.yaml` parses
     cleanly and yields at least 10 lessons (R5 acceptance threshold).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agentic_ops_common.rag import (
    DEFAULT_LESSONS_PATH,
    Lesson,
    load_lessons,
    render_lessons_for_prompt,
    try_load_lessons,
)


# ─────────────────────────────────────────────────────────────────────
# Schema validation
# ─────────────────────────────────────────────────────────────────────


def test_lesson_minimal_construction():
    """A Lesson needs at minimum id + title + rule; optional fields
    default cleanly."""
    L = Lesson(id="L01", title="Title", rule="Do the thing.")
    assert L.id == "L01"
    assert L.title == "Title"
    assert L.rule == "Do the thing."
    assert L.rationale == ""
    assert L.applies_when == ""
    assert L.sources == []


def test_lesson_rejects_empty_required_fields():
    with pytest.raises(Exception):
        Lesson(id="", title="t", rule="r")
    with pytest.raises(Exception):
        Lesson(id="L01", title="", rule="r")
    with pytest.raises(Exception):
        Lesson(id="L01", title="t", rule="")


def test_lesson_render_includes_all_populated_fields():
    L = Lesson(
        id="L01",
        title="Read direction literally",
        rule="Do not invert.",
        applies_when="When you see a direction flag.",
        rationale="Past failures show inversion is common.",
        sources=["docs/foo.md", "agentic_ops_v7/bar.py"],
    )
    rendered = L.render_for_prompt()
    assert "L01" in rendered
    assert "Read direction literally" in rendered
    assert "Do not invert." in rendered
    assert "When you see a direction flag." in rendered
    assert "Past failures show inversion is common." in rendered
    assert "docs/foo.md" in rendered
    assert "agentic_ops_v7/bar.py" in rendered


def test_lesson_render_omits_empty_optional_sections():
    L = Lesson(id="L01", title="X", rule="Y.")
    rendered = L.render_for_prompt()
    assert "L01" in rendered
    assert "**Rule.**" in rendered
    # Optional sections should NOT appear when their content is empty.
    assert "**Applies when.**" not in rendered
    assert "**Why.**" not in rendered
    assert "**Sources:**" not in rendered


# ─────────────────────────────────────────────────────────────────────
# YAML loader
# ─────────────────────────────────────────────────────────────────────


def test_load_lessons_from_synthetic_yaml(tmp_path):
    yaml_text = """
lessons:
  - id: T01
    title: Test lesson 1
    rule: Apply rule 1.
  - id: T02
    title: Test lesson 2
    rule: Apply rule 2.
    rationale: Test rationale.
    applies_when: Test trigger.
    sources:
      - docs/foo.md
"""
    p = tmp_path / "lessons.yaml"
    p.write_text(yaml_text)
    lessons = load_lessons(p)
    assert len(lessons) == 2
    assert lessons[0].id == "T01"
    assert lessons[1].id == "T02"
    assert lessons[1].sources == ["docs/foo.md"]


def test_load_lessons_raises_on_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_lessons(tmp_path / "nonexistent.yaml")


def test_load_lessons_handles_missing_lessons_key(tmp_path):
    """Empty YAML or YAML without `lessons:` returns an empty list."""
    p = tmp_path / "empty.yaml"
    p.write_text("# nothing here\nother_key: value\n")
    assert load_lessons(p) == []


def test_load_lessons_raises_on_wrong_top_level_type(tmp_path):
    """`lessons:` must be a list."""
    p = tmp_path / "wrong.yaml"
    p.write_text("lessons:\n  this_is_a_dict: not_a_list\n")
    with pytest.raises(ValueError, match="list"):
        load_lessons(p)


def test_load_lessons_skips_malformed_entries(tmp_path):
    """A malformed entry (missing required field) is logged and
    skipped; well-formed entries before/after still load."""
    yaml_text = """
lessons:
  - id: OK1
    title: Good lesson
    rule: Apply it.
  - id: BROKEN
    # missing title and rule
  - id: OK2
    title: Another good lesson
    rule: Apply this too.
"""
    p = tmp_path / "mixed.yaml"
    p.write_text(yaml_text)
    lessons = load_lessons(p)
    assert len(lessons) == 2
    assert {L.id for L in lessons} == {"OK1", "OK2"}


def test_try_load_lessons_returns_none_on_missing(tmp_path):
    result = try_load_lessons(tmp_path / "nonexistent.yaml")
    assert result is None


def test_try_load_lessons_returns_none_on_corrupted(tmp_path):
    p = tmp_path / "corrupt.yaml"
    p.write_text("lessons:\n  - id: x\n  this is not valid yaml at all: [[[")
    result = try_load_lessons(p)
    assert result is None


# ─────────────────────────────────────────────────────────────────────
# Render
# ─────────────────────────────────────────────────────────────────────


def test_render_empty_lesson_list_returns_empty_string():
    assert render_lessons_for_prompt([]) == ""


def test_render_non_empty_includes_header_and_count():
    lessons = [
        Lesson(id="L01", title="T1", rule="R1."),
        Lesson(id="L02", title="T2", rule="R2."),
    ]
    rendered = render_lessons_for_prompt(lessons)
    assert "## Operational lessons" in rendered
    assert "2 hand-authored" in rendered
    assert "L01" in rendered
    assert "L02" in rendered


def test_render_custom_header_used():
    lessons = [Lesson(id="L01", title="T", rule="R.")]
    rendered = render_lessons_for_prompt(lessons, header="## Custom Header")
    assert rendered.startswith("## Custom Header")


# ─────────────────────────────────────────────────────────────────────
# Default corpus (shipped lessons.yaml)
# ─────────────────────────────────────────────────────────────────────


def test_default_lessons_yaml_loads_cleanly():
    """The shipped lessons corpus is the production artifact — it
    must parse without warnings and yield the expected count."""
    assert DEFAULT_LESSONS_PATH.exists(), (
        f"Shipped lessons.yaml not found at {DEFAULT_LESSONS_PATH}"
    )
    lessons = load_lessons(DEFAULT_LESSONS_PATH)
    # R5 acceptance: 10-15 lessons.
    assert 10 <= len(lessons) <= 20, (
        f"Expected 10-20 lessons in the shipped corpus; got {len(lessons)}"
    )


def test_default_lessons_have_unique_ids():
    """Lesson ids are citation keys — the corpus must not have
    duplicates."""
    lessons = load_lessons(DEFAULT_LESSONS_PATH)
    ids = [L.id for L in lessons]
    assert len(ids) == len(set(ids)), (
        f"Duplicate ids in lessons.yaml: "
        f"{[i for i in ids if ids.count(i) > 1]}"
    )


def test_default_lessons_all_have_rule_and_title():
    """The corpus has no half-authored entries — every lesson has
    a rule and title."""
    lessons = load_lessons(DEFAULT_LESSONS_PATH)
    for L in lessons:
        assert L.rule.strip(), f"Lesson {L.id} has empty rule"
        assert L.title.strip(), f"Lesson {L.id} has empty title"


def test_default_lessons_renders_under_budget():
    """The always-inject block size shouldn't blow up the NA prompt.
    R5 budget: ~3500 tokens ≈ 15K chars at our text density."""
    lessons = load_lessons(DEFAULT_LESSONS_PATH)
    block = render_lessons_for_prompt(lessons)
    assert len(block) < 20_000, (
        f"Lessons block is {len(block)} chars — exceeds the 20K budget. "
        f"Trim lessons or move to retrieval-based injection."
    )
