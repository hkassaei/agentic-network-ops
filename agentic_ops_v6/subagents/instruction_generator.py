"""InstructionGenerator — per-hypothesis falsification plan builder."""

from __future__ import annotations

from pathlib import Path

from google.adk.agents import LlmAgent

from agentic_ops_common import tools

from ..models import FalsificationPlanSet
from ..retry_config import make_retry_model

_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "instruction_generator.md"


def create_instruction_generator() -> LlmAgent:
    """Create the v6 InstructionGenerator.

    Takes: network_analysis, correlation_analysis, fired_events (template vars).
    Produces: FalsificationPlanSet with one plan per hypothesis.
    """
    return LlmAgent(
        name="InstructionGeneratorAgent",
        # Upgraded from gemini-2.5-flash: Flash + output_schema produced
        # repeated structured-output failures (empty FalsificationPlanSet,
        # zero tool calls, single LLM call) once the prompt accumulated
        # past ~80 lines of rules. Pro tolerates the complexity; the
        # other pipeline LlmAgents (NetworkAnalyst, Investigator,
        # Synthesis) all use Pro for the same reason.
        # Gemini model wrapper carries retry_options for 429 / 408 / 5xx
        # transparently — see retry_config.py.
        model=make_retry_model("gemini-2.5-pro"),
        instruction=_PROMPT_PATH.read_text(),
        description=(
            "Generates one focused falsification plan per NA hypothesis. "
            "Each plan targets ≥2 probes (target 3) with KB disambiguators "
            "as the discriminating questions."
        ),
        output_key="falsification_plan_set",
        output_schema=FalsificationPlanSet,
        tools=[
            tools.get_causal_chain,
            tools.get_causal_chain_for_component,
            # Reverse lookup: pull the branch whose observable_metrics
            # matches a deviated metric mentioned in the hypothesis;
            # its `observable_metrics` list feeds directly into probe
            # design, and its `discriminating_from` hint sharpens
            # falsification.
            tools.find_chains_by_observable_metric,
            tools.get_network_topology,
            tools.get_vonr_components,
            # Flow tools help design probes: `get_flows_through_component`
            # reveals which flows touch the suspect NF so probes can be
            # targeted at specific steps. `get_flow` returns the step
            # sequence so the plan can reference the exact `failure_modes`
            # the Investigator will later verify against.
            tools.list_flows,
            tools.get_flow,
            tools.get_flows_through_component,
        ],
    )
