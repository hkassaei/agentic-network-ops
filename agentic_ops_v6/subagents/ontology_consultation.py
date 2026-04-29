"""OntologyConsultationAgent — wraps ontology tools behind a single agent."""

from __future__ import annotations

from pathlib import Path

from google.adk.agents import LlmAgent

from agentic_ops_common import tools

from ..retry_config import make_retry_model

_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "ontology_consultation.md"


def create_ontology_consultation_agent() -> LlmAgent:
    return LlmAgent(
        name="OntologyConsultationAgent",
        # Gemini model wrapper carries retry_options for 429 / 408 / 5xx
        # transparently — see retry_config.py.
        model=make_retry_model("gemini-2.5-flash"),
        instruction=_PROMPT_PATH.read_text(),
        description=(
            "Consults the network ontology. Matches symptoms, checks stack "
            "rules, interprets log messages, resolves diagnostic ambiguity."
        ),
        tools=[
            tools.match_symptoms,
            tools.check_stack_rules,
            tools.compare_to_baseline,
            tools.interpret_log_message,
            tools.check_component_health,
            tools.get_disambiguation,
            tools.get_causal_chain,
            tools.get_causal_chain_for_component,
            tools.find_chains_by_observable_metric,
        ],
    )
