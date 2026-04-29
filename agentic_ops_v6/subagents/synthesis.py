"""Synthesis — aggregates N per-hypothesis verdicts into a NOC diagnosis."""

from __future__ import annotations

from pathlib import Path

from google.adk.agents import LlmAgent

from ..retry_config import make_retry_config

_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "synthesis.md"


def create_synthesis_agent() -> LlmAgent:
    """Create the v6 Synthesis agent.

    Output is plain markdown (not structured), because the ChallengeAgent's
    scorer reads the raw diagnosis text. Matches v5 contract.
    """
    return LlmAgent(
        name="SynthesisAgent",
        model="gemini-2.5-pro",
        instruction=_PROMPT_PATH.read_text(),
        description=(
            "Aggregates per-hypothesis Investigator verdicts into a NOC-ready "
            "diagnosis with root cause, confidence, and verification advice."
        ),
        output_key="diagnosis",
        tools=[],  # pure synthesis
        # Enable client-side retry on 429 / 408 / 5xx per Google ADK
        # docs (error-code-429-resource_exhausted). See retry_config.py.
        generate_content_config=make_retry_config(),
    )
