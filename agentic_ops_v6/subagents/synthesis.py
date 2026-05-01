"""Synthesis — aggregates N per-hypothesis verdicts into a NOC diagnosis."""

from __future__ import annotations

from pathlib import Path

from google.adk.agents import LlmAgent

from ..models import DiagnosisReport
from ..retry_config import make_retry_model

_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "synthesis.md"


def create_synthesis_agent() -> LlmAgent:
    """Create the v6 Synthesis agent.

    Output is a structured `DiagnosisReport` (PR 5.5b). Switching from
    plain markdown to structured output enables the candidate-pool
    membership constraint (Decision E) to be enforced mechanically by
    the post-emit guardrail. The orchestrator renders the structured
    report back to markdown via `_render_diagnosis_report_to_markdown`
    so the chaos `EpisodeRecorder` and `score_diagnosis` continue to
    receive the prose form they expect.
    """
    return LlmAgent(
        name="SynthesisAgent",
        # Gemini model wrapper carries retry_options for 429 / 408 / 5xx
        # transparently — see retry_config.py.
        model=make_retry_model("gemini-2.5-pro"),
        instruction=_PROMPT_PATH.read_text(),
        description=(
            "Aggregates per-hypothesis Investigator verdicts into a NOC-ready "
            "diagnosis with root cause, confidence, and verification advice."
        ),
        output_key="diagnosis",
        output_schema=DiagnosisReport,
        tools=[],  # pure synthesis
    )
