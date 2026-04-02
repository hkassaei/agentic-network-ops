"""Phase 4: InstructionGeneratorAgent — synthesizes investigation instructions.

An LLM agent that reads all prior context (triage, pattern match, anomaly
analysis) and generates a crisp, focused instruction for the Investigator.
No tools — pure text synthesis.
"""

from __future__ import annotations
from pathlib import Path
from google.adk.agents import LlmAgent

_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "instruction_generator.md"


def create_instruction_generator() -> LlmAgent:
    """Create the InstructionGeneratorAgent."""
    return LlmAgent(
        name="InstructionGeneratorAgent",
        model="gemini-2.5-flash",
        instruction=_PROMPT_PATH.read_text(),
        description=(
            "Synthesizes triage data, pattern match results, and anomaly "
            "analysis into a crisp, focused instruction for the Investigator."
        ),
        output_key="investigation_instruction",
        tools=[],
    )
