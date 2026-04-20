"""Phase 3: InstructionGeneratorAgent — falsification-plan generator.

Reads the Network Analyst's primary suspect, consults the ontology (causal
chain + topology) to identify adjacent components, and produces a plan that
directs the Investigator to falsify the NA's hypothesis.
"""

from __future__ import annotations
from pathlib import Path
from google.adk.agents import LlmAgent
from agentic_ops_common import tools

_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "instruction_generator.md"


def create_instruction_generator() -> LlmAgent:
    """Create the InstructionGeneratorAgent.

    Has read-only ontology/topology tools so it can pick adjacent components
    for the Investigator's falsification probes.
    """
    return LlmAgent(
        name="InstructionGeneratorAgent",
        model="gemini-2.5-flash",
        instruction=_PROMPT_PATH.read_text(),
        description=(
            "Generates a falsification plan for the Investigator: picks "
            "ontology-derived adjacent components to probe for disconfirming "
            "evidence against the Network Analyst's primary suspect."
        ),
        output_key="investigation_instruction",
        tools=[
            tools.get_causal_chain_for_component,
            tools.get_network_topology,
            tools.get_vonr_components,
        ],
    )
