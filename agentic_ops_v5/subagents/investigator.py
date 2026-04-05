"""Phase 3: Investigator Agent — unified, mandate-driven verification.

Uses AgentTool to wrap the OntologyConsultationAgent, allowing the
investigator to consult the ontology for follow-up queries mid-investigation.
"""

from __future__ import annotations
from pathlib import Path
from google.adk.agents import LlmAgent
from google.adk.tools import AgentTool
from .. import tools
from .ontology_consultation import create_ontology_consultation_agent

_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "investigator.md"


def create_investigator_agent() -> LlmAgent:
    """Create the unified InvestigatorAgent.

    The agent has all network diagnostic tools plus the OntologyConsultationAgent
    as an AgentTool for follow-up ontology queries during investigation.
    """
    ontology_agent = create_ontology_consultation_agent()

    return LlmAgent(
        name="InvestigatorAgent",
        model="gemini-2.5-pro",
        instruction=_PROMPT_PATH.read_text(),
        description="Unified investigator: verifies ontology hypothesis across all network layers.",
        output_key="investigation",
        tools=[
            # Transport layer
            tools.measure_rtt,
            tools.check_process_listeners,
            # Core layer
            tools.query_prometheus,
            tools.get_nf_metrics,
            tools.get_dp_quality_gauges,
            tools.get_network_status,
            # Application layer (IMS)
            tools.run_kamcmd,
            tools.read_running_config,
            # Logs
            tools.read_container_logs,
            tools.search_logs,
            # Environment
            tools.read_env_config,
            # Subscriber data
            tools.query_subscriber,
            # Ontology consultation (sub-agent for follow-up queries)
            AgentTool(ontology_agent, skip_summarization=True),
        ],
    )
