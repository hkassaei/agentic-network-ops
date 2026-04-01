"""Phase 1: Investigator Agent — unified, mandate-driven verification."""

from __future__ import annotations
from pathlib import Path
from google.adk.agents import LlmAgent
from .. import tools

_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "investigator.md"


def create_investigator_agent() -> LlmAgent:
    """Create the unified InvestigatorAgent with ALL diagnostic tools.

    The agent's behavior is steered by the ontology mandate injected into
    its prompt context via state placeholders, not by tool filtering.
    """
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
            # Ontology reference (for consulting during investigation)
            tools.interpret_log_message,
            tools.check_component_health,
            tools.get_causal_chain,
        ],
    )
