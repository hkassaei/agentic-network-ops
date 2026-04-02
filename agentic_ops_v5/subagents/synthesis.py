"""Phase 4: Synthesis Agent — pure text synthesis, no tools."""

from __future__ import annotations
from pathlib import Path
from google.adk.agents import LlmAgent

_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "synthesis.md"


def create_synthesis_agent() -> LlmAgent:
    return LlmAgent(
        name="SynthesisAgent",
        model="gemini-2.5-pro",
        instruction=_PROMPT_PATH.read_text(),
        description="Synthesizes investigation findings into a final NOC-ready diagnosis.",
        output_key="diagnosis",
        tools=[],
    )
