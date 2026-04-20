"""NetworkAnalyst — ranked-hypothesis former."""

from __future__ import annotations

from pathlib import Path

from google.adk.agents import LlmAgent
from google.adk.tools import AgentTool

from agentic_ops_common import tools

from ..models import NetworkAnalystReport
from .ontology_consultation import create_ontology_consultation_agent

_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "network_analyst.md"


def create_network_analyst() -> LlmAgent:
    """Create the v6 NetworkAnalyst.

    Takes: anomaly_report, fired_events, correlation_analysis (template vars).
    Produces: NetworkAnalystReport with ranked hypotheses.
    """
    ontology = create_ontology_consultation_agent()

    return LlmAgent(
        name="NetworkAnalystAgent",
        model="gemini-2.5-pro",
        instruction=_PROMPT_PATH.read_text(),
        description=(
            "Forms ranked hypotheses over events + correlation output + "
            "KB semantics for the v6 pipeline."
        ),
        output_key="network_analysis",
        output_schema=NetworkAnalystReport,
        tools=[
            # Diagnostic tools for confirmation before committing
            tools.get_nf_metrics,
            tools.get_dp_quality_gauges,
            tools.get_network_status,
            tools.measure_rtt,
            tools.get_network_topology,
            tools.get_vonr_components,
            tools.check_stack_rules,
            tools.compare_to_baseline,
            tools.get_causal_chain_for_component,
            AgentTool(ontology, skip_summarization=True),
        ],
    )
