"""Phase 1: NetworkAnalystAgent — merged data collection + anomaly analysis.

Replaces the former TriageAgent + AnomalyDetectorAgent with a single agent
that:
  1. Collects data via mandatory tool calls (topology, metrics, status, DP gauges)
  2. Compares observations to ontology baselines and stack rules
  3. Rates each layer (infrastructure, RAN, core, IMS) with evidence
  4. Identifies suspect components and writes an investigation hint

Output is a structured NetworkAnalysis Pydantic model, enforced via
ADK's output_schema. ADK's _output_schema_processor handles the
tools+schema combination by injecting a set_model_response synthetic
tool, so the model can call regular tools AND produce structured JSON.

Merging these phases also practically eliminates the ADK thinking-mode
output_key bug: Step 1 requires five tool calls, which guarantees the
model's final event is a non-thought response.
"""

from __future__ import annotations
from pathlib import Path

from google.adk.agents import LlmAgent

from .. import tools
from ..models import NetworkAnalysis

_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "network_analyst.md"


def create_network_analyst() -> LlmAgent:
    """Create the NetworkAnalystAgent (Phase 1)."""
    return LlmAgent(
        name="NetworkAnalystAgent",
        model="gemini-2.5-pro",
        instruction=_PROMPT_PATH.read_text(),
        description=(
            "Collects network state AND produces a structured layer-rated "
            "assessment in one pass. Replaces TriageAgent + AnomalyDetectorAgent."
        ),
        output_key="network_analysis",
        output_schema=NetworkAnalysis,
        tools=[
            # Scope definition (Step 0 — must be first)
            tools.get_vonr_components,
            # Data collection (Step 1)
            tools.get_network_topology,
            tools.get_network_status,
            tools.get_nf_metrics,
            tools.get_dp_quality_gauges,
            # Transport probing (Step 1b — probe screener-flagged components)
            tools.measure_rtt,
            # Ontology comparison (Step 2)
            tools.compare_to_baseline,
            tools.check_stack_rules,
            tools.check_component_health,
            tools.get_causal_chain_for_component,
            # Environment (optional context)
            tools.read_env_config,
        ],
    )
