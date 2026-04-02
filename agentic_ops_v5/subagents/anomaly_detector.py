"""Phase 3: AnomalyDetectorAgent — ontology-guided anomaly analysis.

An LLM agent that uses ontology tools to analyze triage data when no
exact failure signature was matched. Groups anomalies by layer, identifies
suspect protocols and components, checks stack rules.

This is the "Tier 2" — between exact signature match and blind investigation.
"""

from __future__ import annotations
from pathlib import Path
from google.adk.agents import LlmAgent
from .. import tools

_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "anomaly_detector.md"


def create_anomaly_detector() -> LlmAgent:
    """Create the AnomalyDetectorAgent with all ontology tools."""
    return LlmAgent(
        name="AnomalyDetectorAgent",
        model="gemini-2.5-flash",
        instruction=_PROMPT_PATH.read_text(),
        description=(
            "Analyzes triage data using ontology tools to detect anomalies "
            "when no exact failure signature was matched. Groups findings by "
            "network layer and identifies suspect components."
        ),
        output_key="anomaly_analysis",
        tools=[
            tools.check_stack_rules,
            tools.compare_to_baseline,
            tools.interpret_log_message,
            tools.check_component_health,
            tools.get_disambiguation,
            tools.get_causal_chain,
            tools.get_causal_chain_for_component,
        ],
    )
