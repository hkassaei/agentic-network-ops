"""Phase 2: PatternMatcherAgent — deterministic signature matching.

A BaseAgent (no LLM) that collects structured observations from the
network and queries the ontology for matching failure signatures.
Fast, reliable, and deterministic.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, AsyncGenerator

from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.genai import types

log = logging.getLogger("v5.pattern_matcher")


class PatternMatcherAgent(BaseAgent):
    """Deterministic pattern matching against ontology failure signatures."""

    name: str = "PatternMatcherAgent"
    description: str = (
        "Collects structured observations from the network and matches them "
        "against known failure signatures in the ontology. Deterministic — no LLM."
    )

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:

        # 1. Collect observations directly from network tools
        try:
            observations = await _collect_observations()
            log.info("Collected %d observations", len(observations))
        except Exception as e:
            log.warning("Observation collection failed: %s", e)
            observations = {}

        # 2. Query ontology for matching signatures
        diagnosis: dict[str, Any] = {}
        try:
            from network_ontology.query import OntologyClient
            client = OntologyClient()
            diagnosis = client.diagnose(observations)
            client.close()
            log.info("Ontology diagnosis: %s (confidence: %s)",
                     diagnosis.get("top_diagnosis", "?"),
                     diagnosis.get("confidence", "?"))
        except ImportError:
            log.warning("network_ontology not available — no pattern matching")
        except Exception as e:
            log.warning("Ontology query failed: %s", e)

        # 3. Build result
        matched_sigs = diagnosis.get("matched_signatures", [])
        top_sig = matched_sigs[0] if matched_sigs else None

        result = {
            "matched": bool(matched_sigs),
            "top_diagnosis": diagnosis.get("top_diagnosis", "No matching signature found"),
            "confidence": diagnosis.get("confidence", "low"),
            "failure_domain": top_sig.get("failure_domain", "unknown") if top_sig else "unknown",
            "matched_signatures": matched_sigs,
            "baseline_anomalies": diagnosis.get("baseline_anomalies", {}),
            "health_check_suggestions": diagnosis.get("health_check_suggestions", []),
            "diagnostic_actions": diagnosis.get("diagnostic_actions", []),
            "observations": observations,
        }

        # 4. Format summary for display
        summary = f"Pattern match: {result['top_diagnosis']} (confidence: {result['confidence']})"
        if result["baseline_anomalies"]:
            anomaly_count = sum(len(v) for v in result["baseline_anomalies"].values())
            summary += f"\nBaseline anomalies: {anomaly_count} metrics deviate from expected"

        # 5. Yield event with state_delta
        yield Event(
            author=self.name,
            content=types.Content(parts=[types.Part(text=summary)]),
            actions=EventActions(state_delta={
                "pattern_match": json.dumps(result, default=str),
            }),
        )

    async def _run_live_impl(self, ctx):
        raise NotImplementedError


def create_pattern_matcher() -> PatternMatcherAgent:
    """Create the PatternMatcherAgent."""
    return PatternMatcherAgent()


# -------------------------------------------------------------------------
# Observation collection helpers (moved from consultation.py)
# -------------------------------------------------------------------------

async def _collect_observations() -> dict[str, Any]:
    """Collect raw observations directly from network tools."""
    from agentic_ops_common import tools

    metrics_text, status_text = await asyncio.gather(
        tools.get_nf_metrics(),
        tools.get_network_status(),
    )

    observations: dict[str, Any] = {}
    observations.update(_parse_metrics_text(metrics_text))
    observations["container_status"] = _parse_network_status(status_text)
    return observations


def _parse_metrics_text(text: str) -> dict[str, Any]:
    """Extract metric values from get_nf_metrics() output.

    Handles Prometheus style (ran_ue = 2.0) and Kamailio style (cdp:timeout = 0.0).
    """
    metrics: dict[str, Any] = {}
    for match in re.finditer(r'"?([\w:]+)"?\s*[=:]\s*(-?\d+\.?\d*)', text):
        key, val = match.group(1), match.group(2)
        if val in ("running", "exited", "absent", "paused"):
            continue
        try:
            metrics[key] = float(val)
        except ValueError:
            pass
    return metrics


def _parse_network_status(text: str) -> dict[str, str]:
    """Extract container statuses from get_network_status() output."""
    status: dict[str, str] = {}
    for match in re.finditer(r'"?(\w+)"?\s*:\s*"?(running|exited|absent|paused)"?', text):
        name, state = match.group(1), match.group(2)
        if name in ("phase", "status", "health"):
            continue
        status[name] = state
    return status
