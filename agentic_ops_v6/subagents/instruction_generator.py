"""InstructionGenerator — per-hypothesis falsification plan builder."""

from __future__ import annotations

from pathlib import Path

from google.adk.agents import LlmAgent

from agentic_ops_common import tools

from ..models import FalsificationPlanSet

_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "instruction_generator.md"


def create_instruction_generator() -> LlmAgent:
    """Create the v6 InstructionGenerator.

    Takes: network_analysis, correlation_analysis, fired_events (template vars).
    Produces: FalsificationPlanSet with one plan per hypothesis.
    """
    return LlmAgent(
        name="InstructionGeneratorAgent",
        model="gemini-2.5-flash",
        instruction=_PROMPT_PATH.read_text(),
        description=(
            "Generates one focused falsification plan per NA hypothesis. "
            "Each plan targets ≥2 probes (target 3) with KB disambiguators "
            "as the discriminating questions."
        ),
        output_key="falsification_plan_set",
        output_schema=FalsificationPlanSet,
        tools=[
            tools.get_causal_chain_for_component,
            tools.get_network_topology,
            tools.get_vonr_components,
        ],
    )
