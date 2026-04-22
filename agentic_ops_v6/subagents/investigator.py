"""Investigator — per-hypothesis falsifier.

Each sub-Investigator is created fresh per hypothesis. Prompt is parameterized
with the hypothesis and plan.
"""

from __future__ import annotations

from pathlib import Path

from google.adk.agents import LlmAgent
from google.adk.tools import AgentTool

from agentic_ops_common import tools

from ..models import InvestigatorVerdict
from .ontology_consultation import create_ontology_consultation_agent

_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "investigator.md"


def create_investigator_agent(name: str = "InvestigatorAgent") -> LlmAgent:
    """Create a sub-Investigator bound to a specific hypothesis.

    Template vars in the prompt (hypothesis_id, hypothesis_statement,
    primary_suspect_nf, falsification_plan, network_analysis) are populated
    by the orchestrator when running this sub-agent.
    """
    ontology = create_ontology_consultation_agent()

    return LlmAgent(
        name=name,
        model="gemini-2.5-pro",
        instruction=_PROMPT_PATH.read_text(),
        description=(
            "Falsifies one specific hypothesis by running targeted probes "
            "from the assigned falsification plan. Emits a structured "
            "InvestigatorVerdict."
        ),
        output_key="investigator_verdict",
        output_schema=InvestigatorVerdict,
        tools=[
            # All diagnostic tools. `query_prometheus` is intentionally
            # absent — agents must use `get_nf_metrics` / `get_dp_quality_gauges`
            # which are KB-annotated and cannot return hallucinated names.
            tools.measure_rtt,
            tools.check_process_listeners,
            tools.get_nf_metrics,
            tools.get_dp_quality_gauges,
            tools.get_network_status,
            tools.run_kamcmd,
            tools.read_running_config,
            tools.read_container_logs,
            tools.search_logs,
            tools.read_env_config,
            tools.query_subscriber,
            # Flow tools for mechanism-walk falsification: pull the
            # full flow for the procedure the hypothesis implicates,
            # then step through its `failure_modes` to identify the
            # exact log line / metric / SIP response code you should
            # see at each step if the hypothesis is true.
            tools.list_flows,
            tools.get_flow,
            tools.get_flows_through_component,
            AgentTool(ontology, skip_summarization=True),
        ],
    )
