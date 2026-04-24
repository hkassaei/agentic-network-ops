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
            # All diagnostic tools. Two tools are intentionally absent:
            #   - `query_prometheus`: removed per ADR kb_backed_tool_outputs_and_no_raw_promql.md
            #     (agents use `get_nf_metrics` / `get_dp_quality_gauges` instead,
            #     which are KB-annotated and cannot return hallucinated names).
            #   - `read_container_logs` / `search_logs`: removed per ADR
            #     remove_log_probes_from_investigator.md (agent-authored grep
            #     patterns are unreliable and "no matches" is mis-read as
            #     strong contradicting evidence; the recurring mongodb_gone
            #     mis-diagnoses traced directly to this).
            tools.measure_rtt,
            tools.check_process_listeners,
            tools.get_nf_metrics,
            tools.get_dp_quality_gauges,
            tools.get_network_status,
            tools.run_kamcmd,
            tools.read_running_config,
            tools.read_env_config,
            tools.query_subscriber,
            # Flow tools for mechanism-walk falsification: pull the
            # full flow for the procedure the hypothesis implicates,
            # then step through its `failure_modes` to identify the
            # exact metric / SIP response code / container status you
            # should see at each step if the hypothesis is true.
            tools.list_flows,
            tools.get_flow,
            tools.get_flows_through_component,
            # Causal-chain tools: agent can read the full branch-first
            # chain for its hypothesis (mechanism, source_steps,
            # discriminating_from) to know what a clean/contradicting
            # observation looks like without asking the OntologyAgent.
            tools.get_causal_chain,
            tools.find_chains_by_observable_metric,
            AgentTool(ontology, skip_summarization=True),
        ],
    )
