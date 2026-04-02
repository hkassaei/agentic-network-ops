"""OntologyConsultationAgent — LLM-backed ontology advisor available as AgentTool.

Used by the InvestigatorAgent (Phase 3) for follow-up ontology queries
during investigation. Wraps all ontology tools (symptom matching, health
checks, causal reasoning, log interpretation) behind a single agent
interface that reasons about which ontology query to run.
"""

from __future__ import annotations
from pathlib import Path
from google.adk.agents import LlmAgent
from .. import tools

_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "ontology_consultation.md"


def create_ontology_consultation_agent() -> LlmAgent:
    """Create the OntologyConsultationAgent for use as an AgentTool.

    This agent has access to all ontology tools and can answer follow-up
    ontology queries during the investigation phase.
    """
    return LlmAgent(
        name="OntologyConsultationAgent",
        model="gemini-2.5-flash",
        instruction=_PROMPT_PATH.read_text(),
        description=(
            "Consults the network ontology to match symptoms, check causal chains, "
            "interpret log messages, and resolve diagnostic ambiguity. Use this when "
            "you encounter new symptoms during investigation that need ontology guidance."
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
        ],
    )
