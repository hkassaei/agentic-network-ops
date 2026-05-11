"""Lesson schema + YAML loader + prompt-block renderer.

A `Lesson` is a hand-authored operational rule the LLM should
internalize when reasoning. Lessons distill the failure modes seen
in past chaos batches (B3 direction-reading, B4 over-flagging, etc.)
plus the load-bearing principles in the stack rules and ADRs.

The corpus is small (10-15 lessons) and durable, so R5 ships an
**always-inject** flow rather than retrieval: every NA prompt gets
all lessons concatenated into the `{operational_lessons}` placeholder.
A future expansion to retrieval-based lesson selection slots in
without changing the lesson schema or the NA-prompt contract — only
the orchestrator's lesson-injection helper changes.

YAML format (`agentic_ops_common/rag/lessons.yaml`):

    lessons:
      - id: L01
        title: One-line summary
        rule: >
          1-3 sentence rule the LLM should apply.
        rationale: >
          Why this rule exists, sourced from incident or principle.
        applies_when: >
          When this rule is relevant. Operator-facing description,
          not a machine-readable trigger.
        sources:
          - docs/ADR/some_adr.md
          - agentic_ops_v7/docs/agent_logs/run_<id>.md

The `sources` field is provenance — the LLM can cite a lesson by
its `id`, and a downstream guardrail or auditor can trace the rule
back to where it came from.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field

log = logging.getLogger("agentic_ops_common.rag.lessons")


class Lesson(BaseModel):
    """One hand-authored operational rule."""

    id: str = Field(
        ...,
        min_length=1,
        description=(
            "Short, stable identifier the LLM can cite when applying "
            "the rule. Convention: `L<NN>` (L01, L02, …) but any "
            "non-empty string is accepted."
        ),
    )
    title: str = Field(
        ...,
        min_length=1,
        description="One-line summary that conveys the rule's headline.",
    )
    rule: str = Field(
        ...,
        min_length=1,
        description=(
            "The actual rule the LLM should apply, 1-3 sentences. "
            "Phrased as instruction or invariant, not as observation. "
            "Imperative mood preferred: \"Do not infer X from Y.\""
        ),
    )
    rationale: str = Field(
        default="",
        description=(
            "Why the rule exists. Optional but recommended — gives "
            "the LLM enough context to apply the rule on edge cases "
            "rather than rote-matching."
        ),
    )
    applies_when: str = Field(
        default="",
        description=(
            "When this rule is relevant. Operator-facing description "
            "of the situation; not a machine-readable trigger. The "
            "LLM uses this to decide whether the rule fires for the "
            "current input."
        ),
    )
    sources: list[str] = Field(
        default_factory=list,
        description=(
            "Provenance — paths to ADRs, run logs, stack-rule entries, "
            "or other authoritative places the rule was derived from. "
            "An auditor or EvidenceValidator can cross-reference these."
        ),
    )

    def render_for_prompt(self) -> str:
        """Render this lesson as a markdown block for prompt injection."""
        lines: list[str] = []
        lines.append(f"### `{self.id}` — {self.title}")
        lines.append("")
        lines.append(f"**Rule.** {self.rule.strip()}")
        if self.applies_when.strip():
            lines.append("")
            lines.append(f"**Applies when.** {self.applies_when.strip()}")
        if self.rationale.strip():
            lines.append("")
            lines.append(f"**Why.** {self.rationale.strip()}")
        if self.sources:
            lines.append("")
            lines.append(
                "**Sources:** " + ", ".join(f"`{s}`" for s in self.sources)
            )
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────
# YAML loader
# ─────────────────────────────────────────────────────────────────────


def load_lessons(path: Path | str) -> list[Lesson]:
    """Load lesson units from a YAML file.

    YAML schema:

        lessons:
          - id: L01
            title: ...
            rule: ...
            ...

    Returns the parsed list (empty if the file has no `lessons:` key).
    Raises `FileNotFoundError` if the path doesn't exist — callers
    that want graceful degradation should use `try_load_lessons`.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Lessons YAML not found: {path}")

    doc = yaml.safe_load(path.read_text()) or {}
    raw_lessons = doc.get("lessons", []) or []
    if not isinstance(raw_lessons, list):
        raise ValueError(
            f"Expected `lessons:` to be a list in {path}; got {type(raw_lessons).__name__}"
        )

    lessons: list[Lesson] = []
    for i, raw in enumerate(raw_lessons):
        if not isinstance(raw, dict):
            log.warning(
                "Skipping non-dict lesson entry at index %d in %s: %r",
                i, path, raw,
            )
            continue
        try:
            lessons.append(Lesson(**raw))
        except Exception as e:
            log.warning(
                "Skipping malformed lesson entry at index %d in %s: %s",
                i, path, e,
            )
    return lessons


def try_load_lessons(path: Path | str) -> Optional[list[Lesson]]:
    """Load lessons, returning None on any failure. For orchestrator
    callers that treat missing/broken lessons as "lessons disabled"."""
    try:
        return load_lessons(path)
    except FileNotFoundError as e:
        log.info("Lessons unavailable: %s; lessons disabled.", e)
        return None
    except Exception as e:
        log.warning(
            "Lessons load failed for %s: %s; lessons disabled.",
            path, e, exc_info=True,
        )
        return None


# ─────────────────────────────────────────────────────────────────────
# Rendering
# ─────────────────────────────────────────────────────────────────────


def render_lessons_for_prompt(
    lessons: list[Lesson],
    *,
    header: str = "## Operational lessons",
) -> str:
    """Render all lessons as one markdown block for prompt injection.

    Returns the empty string for empty input — the caller's prompt
    template can substitute a "no lessons available" note in that
    case (though in practice the lesson corpus is small and stable,
    so empty input is rare).

    Layout:

      ## Operational lessons
      *(N hand-authored operational rules distilled from past chaos
      batches + stack-rule principles. Apply these as hard rules; the
      principles below come second. Cite a lesson by its `id` when
      its evidence shapes your hypothesis.)*

      ### `L01` — Title
      **Rule.** ...
      **Applies when.** ...
      **Why.** ...
      **Sources:** `path1`, `path2`

      ### `L02` — Title
      ...
    """
    if not lessons:
        return ""

    lines: list[str] = [header, ""]
    lines.append(
        f"*({len(lessons)} hand-authored operational rule(s) distilled from "
        f"past chaos batches and stack-rule principles. Apply these as hard "
        f"rules; the principles below come second. Cite a lesson by its "
        f"`id` when its evidence shapes your hypothesis.)*"
    )
    lines.append("")

    for lesson in lessons:
        lines.append(lesson.render_for_prompt())
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


# ─────────────────────────────────────────────────────────────────────
# Default path
# ─────────────────────────────────────────────────────────────────────


DEFAULT_LESSONS_PATH: Path = Path(__file__).resolve().parent / "lessons.yaml"
"""Default location of the lesson corpus. The orchestrator's
`LESSONS_YAML_PATH` env var overrides this — see
`agentic_ops_v7/orchestrator.py:_resolve_lessons_path`."""
