"""NetworkAnalyst — ranked-hypothesis former."""

from __future__ import annotations

from pathlib import Path

from google.adk.agents import LlmAgent
from google.adk.tools import AgentTool

from agentic_ops_common import tools

from ..models import NetworkAnalystReport
from ..retry_config import make_retry_model
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
        # Gemini model wrapper carries retry_options for 429 / 408 / 5xx
        # transparently — see retry_config.py.
        model=make_retry_model("gemini-2.5-pro"),
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
            # Reverse lookup: given a deviated metric, find the causal-chain
            # branches whose observable_metrics name it — plus the flow
            # steps each branch is anchored to. Strong support for
            # anchoring hypotheses in authored ontology branches rather
            # than LLM priors.
            tools.find_chains_by_observable_metric,
            # Flow tools: use `get_flows_through_component` to understand
            # what's downstream of a suspect NF when forming hypotheses.
            # `list_flows` surfaces the available flow ids so the agent
            # doesn't invent them. Deep flow walks belong in the
            # Investigator; NA should stay at the overview level.
            tools.list_flows,
            tools.get_flows_through_component,
            AgentTool(ontology, skip_summarization=True),
        ],
    )
