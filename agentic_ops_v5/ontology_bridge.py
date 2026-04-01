"""
Ontology Bridge — Phase 0.5 Deterministic Analysis.

This is the core architectural innovation of v5. It sits between the
triage LLM agent (Phase 0) and the investigator LLM agent (Phase 1),
running as PURE PYTHON CODE with zero LLM involvement.

It collects structured metrics directly from the network tools (not
from the triage LLM's text output), queries the ontology for matching
failure signatures, checks protocol stack rules, and computes an
investigation plan that steers the downstream LLM.

The key principle: "If a decision can be made deterministically,
it must not be delegated to an LLM."
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

log = logging.getLogger("v5.ontology_bridge")


# -------------------------------------------------------------------------
# Observation Collection (direct from tools, not from LLM text)
# -------------------------------------------------------------------------

async def collect_observations() -> dict[str, Any]:
    """Collect raw observations directly from network tools.

    Bypasses the triage LLM entirely for ontology input. The triage agent's
    text output is still used for human-readable context downstream, but
    the ontology gets clean structured data.
    """
    from . import tools

    metrics_text, status_text = await asyncio.gather(
        tools.get_nf_metrics(),
        tools.get_network_status(),
    )

    observations: dict[str, Any] = {}

    # Parse metrics from the structured output
    observations.update(_parse_metrics_text(metrics_text))

    # Parse container status
    observations["container_status"] = _parse_network_status(status_text)

    return observations


def _parse_metrics_text(text: str) -> dict[str, Any]:
    """Extract metric values from get_nf_metrics() output.

    The output is structured as JSON-like blocks per component.
    We extract known metric names and their float values.
    """
    metrics: dict[str, Any] = {}

    # Pattern: "metric_name": value or metric_name = value
    for match in re.finditer(
        r'"?(\w+)"?\s*[:=]\s*(-?\d+\.?\d*)', text
    ):
        key, val = match.group(1), match.group(2)
        try:
            metrics[key] = float(val)
        except ValueError:
            pass

    return metrics


def _parse_network_status(text: str) -> dict[str, str]:
    """Extract container statuses from get_network_status() output."""
    status: dict[str, str] = {}

    # Pattern: "container_name": "running" or container_name: running
    for match in re.finditer(
        r'"?(\w+)"?\s*:\s*"?(running|exited|absent|paused)"?', text
    ):
        name, state = match.group(1), match.group(2)
        # Skip non-container keys
        if name in ("phase", "status", "health"):
            continue
        status[name] = state

    return status


# -------------------------------------------------------------------------
# Deterministic Diagnosis
# -------------------------------------------------------------------------

async def run_deterministic_diagnosis(
    triage_text: str,
    observations: dict[str, Any] | None = None,
) -> tuple[dict, dict]:
    """Run the full deterministic ontology analysis (Phase 0.5).

    Args:
        triage_text: The triage agent's free-text output (for fallback parsing).
        observations: Pre-collected structured observations. If None, collected
                      from triage text as fallback.

    Returns:
        (ontology_diagnosis, investigation_plan)
    """
    try:
        from network_ontology.query import OntologyClient
    except ImportError:
        log.warning("network_ontology not available — skipping Phase 0.5")
        return _unavailable_result()

    # If no pre-collected observations, parse from triage text
    if observations is None:
        observations = _parse_triage_for_observations(triage_text)

    try:
        client = OntologyClient()
    except Exception as e:
        log.warning("Neo4j connection failed: %s — skipping Phase 0.5", e)
        return _unavailable_result()

    try:
        # 1. Full diagnosis: match symptoms, check rules, compare baselines
        diagnosis = client.diagnose(observations)

        # 2. Enrich observations with derived facts for deeper rule checking
        enriched = _enrich_observations(observations, diagnosis)
        triggered_rules = client.check_stack_rules(enriched)

        # 3. Get health check suggestions
        health_checks = diagnosis.get("health_check_suggestions", [])

        # 4. Compute investigation plan from diagnosis
        plan = _compute_investigation_plan(diagnosis, triggered_rules, observations)

        ontology_result = {
            "matched_signatures": diagnosis.get("matched_signatures", []),
            "triggered_rules": triggered_rules,
            "baseline_anomalies": diagnosis.get("baseline_anomalies", {}),
            "health_check_suggestions": health_checks,
            "diagnostic_actions": diagnosis.get("diagnostic_actions", []),
            "top_diagnosis": diagnosis.get("top_diagnosis", "No match"),
            "confidence": diagnosis.get("confidence", "low"),
        }

        return ontology_result, plan

    except Exception as e:
        log.warning("Ontology diagnosis failed: %s — proceeding without", e)
        return _unavailable_result()
    finally:
        try:
            client.close()
        except Exception:
            pass


def _unavailable_result() -> tuple[dict, dict]:
    """Return a safe fallback when the ontology is unavailable."""
    return (
        {
            "matched_signatures": [],
            "triggered_rules": [],
            "baseline_anomalies": {},
            "health_check_suggestions": [],
            "diagnostic_actions": [],
            "top_diagnosis": "Ontology unavailable — full investigation required",
            "confidence": "low",
        },
        _full_investigation_plan(),
    )


def _parse_triage_for_observations(triage_text: str) -> dict[str, Any]:
    """Fallback: extract metric values from triage agent's free-text output."""
    obs: dict[str, Any] = {}
    for match in re.finditer(r"(\w+)\s*[=:]\s*(\d+\.?\d*)", triage_text):
        key, val = match.group(1), float(match.group(2))
        obs[key] = val
    # Container status
    container_status: dict[str, str] = {}
    for match in re.finditer(
        r"(\w+)\s*(?:\(|is\s+)(running|exited|absent|paused)", triage_text
    ):
        container_status[match.group(1)] = match.group(2)
    if container_status:
        obs["container_status"] = container_status
    return obs


# -------------------------------------------------------------------------
# Observation Enrichment
# -------------------------------------------------------------------------

def _enrich_observations(observations: dict, diagnosis: dict) -> dict:
    """Add derived facts to observations based on initial diagnosis."""
    enriched = dict(observations)

    sigs = diagnosis.get("matched_signatures", [])
    if sigs:
        top = sigs[0]
        domain = top.get("failure_domain", "")
        confidence = top.get("confidence", "")

        if domain in ("ran", "transport", "data_plane") and confidence in ("very_high", "high"):
            enriched["network_fault_confirmed"] = True

    # Mark unreachable components
    status = observations.get("container_status", {})
    unreachable = [name for name, s in status.items() if s in ("exited", "absent")]
    if unreachable:
        enriched["unreachable_components"] = unreachable

    return enriched


# -------------------------------------------------------------------------
# Investigation Plan Computation (short-circuit logic)
# -------------------------------------------------------------------------

def _compute_investigation_plan(
    diagnosis: dict,
    triggered_rules: list[dict],
    observations: dict,
) -> dict:
    """Compute which tools/layers to investigate based on ontology results.

    This is the short-circuit logic: high-confidence diagnoses skip
    irrelevant investigation paths entirely.
    """
    sigs = diagnosis.get("matched_signatures", [])
    top = sigs[0] if sigs else None

    if not top:
        return _full_investigation_plan()

    domain = top.get("failure_domain", "unknown")
    confidence = top.get("confidence", "low")
    hypothesis = top.get("diagnosis", "")

    plan = {
        "focus_domain": domain,
        "hypothesis": hypothesis,
        "confidence": confidence,
        "triggered_rules": [r.get("id", "") for r in triggered_rules],
        "mandate": "",
        "suggested_tools": [],
    }

    # --- RAN failure (very_high/high confidence) ---
    if domain == "ran" and confidence in ("very_high", "high"):
        plan["mandate"] = (
            f"ESTABLISHED FACT: The ontology diagnosed '{hypothesis}' "
            f"with {confidence} confidence. RAN failure confirmed. "
            "ALL IMS symptoms are secondary effects "
            "(stack rule: ran_down_invalidates_ims). "
            "Your ONLY job: verify the RAN failure using the tools below, "
            "then explain the cascading impact. Do NOT investigate IMS or SIP."
        )
        plan["suggested_tools"] = [
            "measure_rtt", "get_nf_metrics", "get_network_status",
            "read_container_logs",
        ]

    # --- Data plane failure ---
    elif domain == "data_plane":
        plan["mandate"] = (
            f"ESTABLISHED FACT: The ontology diagnosed '{hypothesis}' "
            f"with {confidence} confidence. Data plane issue detected. "
            "SIP timeouts are CONSEQUENCES, not causes "
            "(stack rule: data_plane_dead_invalidates_sip). "
            "Your ONLY job: verify the data plane issue. "
            "Do NOT investigate SIP or Kamailio."
        )
        plan["suggested_tools"] = [
            "measure_rtt", "get_nf_metrics", "query_prometheus",
            "read_container_logs",
        ]

    # --- Transport fault ---
    elif domain == "transport":
        plan["mandate"] = (
            f"ESTABLISHED FACT: The ontology diagnosed '{hypothesis}' "
            f"with {confidence} confidence. Transport-layer fault detected. "
            "Application-layer symptoms are SECONDARY "
            "(stack rule: transport_over_application). "
            "Verify the transport issue first. Only investigate application "
            "layer if transport is confirmed clean."
        )
        plan["suggested_tools"] = [
            "measure_rtt", "check_process_listeners",
            "read_running_config", "read_container_logs",
        ]

    # --- IMS signaling ---
    elif domain == "ims_signaling":
        plan["mandate"] = (
            f"ESTABLISHED FACT: The ontology diagnosed '{hypothesis}' "
            f"with {confidence} confidence. IMS signaling issue suspected. "
            "However, per Hierarchy of Truth, you MUST first verify transport "
            "layer is clean (measure_rtt to affected nodes) before investigating "
            "SIP/Diameter. If transport is broken, STOP and report that instead."
        )
        plan["suggested_tools"] = [
            "measure_rtt",
            "run_kamcmd", "read_running_config",
            "search_logs", "read_container_logs",
            "check_process_listeners",
        ]

    # --- Infrastructure (DNS, MongoDB) ---
    elif domain == "infrastructure":
        plan["mandate"] = (
            f"ESTABLISHED FACT: The ontology diagnosed '{hypothesis}' "
            f"with {confidence} confidence. Infrastructure component failure. "
            "Verify which component is down and confirm cascading impact."
        )
        plan["suggested_tools"] = [
            "get_network_status", "get_nf_metrics",
            "read_container_logs",
        ]

    # --- Unknown or low confidence ---
    else:
        return _full_investigation_plan(hypothesis, confidence)

    return plan


def _full_investigation_plan(
    hypothesis: str = "", confidence: str = "low"
) -> dict:
    """Return a plan for full bottom-up investigation (no short-circuit)."""
    if hypothesis:
        mandate = (
            f"The ontology's best guess is '{hypothesis}' "
            f"(confidence: {confidence}). This is uncertain. "
            "Perform a thorough bottom-up investigation: transport first, "
            "then core, then application. Cite tool outputs for every claim."
        )
    else:
        mandate = (
            "The ontology found no matching failure signature. "
            "Perform a bottom-up investigation: check transport first, "
            "then core, then application layer. Cite tool outputs for every claim."
        )

    return {
        "focus_domain": "unknown",
        "hypothesis": hypothesis or "No matching signature",
        "confidence": confidence,
        "triggered_rules": [],
        "mandate": mandate,
        "suggested_tools": [
            "measure_rtt", "check_process_listeners",
            "read_running_config", "read_container_logs",
            "search_logs", "run_kamcmd", "query_prometheus",
            "get_nf_metrics", "get_network_status",
        ],
    }


# -------------------------------------------------------------------------
# Formatting for LLM prompts
# -------------------------------------------------------------------------

def format_ontology_for_prompt(ontology_result: dict) -> str:
    """Format ontology diagnosis as readable text for LLM context injection."""
    lines = []

    top = ontology_result.get("top_diagnosis", "No match")
    confidence = ontology_result.get("confidence", "low")
    lines.append(f"Top Diagnosis: {top} (confidence: {confidence})")

    sigs = ontology_result.get("matched_signatures", [])
    if sigs:
        sig_names = [f"{s['signature_id']} (score: {s.get('match_score', '?')})" for s in sigs[:3]]
        lines.append(f"Matched Signatures: {', '.join(sig_names)}")

    rules = ontology_result.get("triggered_rules", [])
    if rules:
        rule_ids = [r.get("id", "?") for r in rules]
        lines.append(f"Triggered Rules: {', '.join(rule_ids)}")

    anomalies = ontology_result.get("baseline_anomalies", {})
    if anomalies:
        for comp, items in anomalies.items():
            for item in items:
                lines.append(
                    f"Baseline Anomaly: {comp}.{item['metric']} "
                    f"expected={item['expected']}, actual={item['actual']}"
                )

    actions = ontology_result.get("diagnostic_actions", [])
    if actions:
        lines.append("Suggested Actions:")
        for a in actions[:5]:
            lines.append(f"  - {a}")

    health = ontology_result.get("health_check_suggestions", [])
    if health:
        for h in health:
            lines.append(f"Health Check: {h.get('component', '?')} — {h.get('purpose', '')}")

    return "\n".join(lines)
