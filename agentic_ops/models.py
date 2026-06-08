"""
Pydantic models and dependency types for the Telecom Troubleshooting Agent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Operator-boundary constants — names that are explicitly OUT_OF_SCOPE
# for direct agent probes.
#
# Per ADR `synthesis_undetected_fault_verdict.md` (Task A): RAN equipment
# (`nr_gnb`) and customer UEs (`e2e_ue1`, `e2e_ue2`) live outside the NOC's
# tool surface. A real NOC running a 5G core has no shell on the gNB or
# on customer phones; the lab models that boundary by excluding them from
# `AgentDeps.all_containers`.
#
# Tools that accept a target-container argument (`measure_rtt`,
# `get_network_status`, etc.) return a structured `OUT_OF_SCOPE:` response
# for these names — a STATIC architectural signal the investigator can
# pattern-match without confusing it with episodic gaps (typo, container
# crashed, tool error). Single source of truth: this constant.
# ---------------------------------------------------------------------------

OUT_OF_SCOPE_CONTAINERS: frozenset[str] = frozenset({
    "nr_gnb",
    "e2e_ue1",
    "e2e_ue2",
})

# Per-name inference pointer — the in-scope probe the agent should reach
# for when it wants to assess state of an OUT_OF_SCOPE component.
# Surfaced verbatim in tool error messages and in `get_network_status`
# JSON so the agent has the redirection at the point of rejection.
OUT_OF_SCOPE_INFERENCE: dict[str, str] = {
    "nr_gnb":  "RAN — outside NOC; infer via amf.gnb gauge (1.0 = N2 association up)",
    "e2e_ue1": "UE — outside NOC; infer via amf.ran_ue gauge + run_kamcmd(pcscf, 'stats.get_statistics ims_usrloc_pcscf:')",
    "e2e_ue2": "UE — outside NOC; infer via amf.ran_ue gauge + run_kamcmd(pcscf, 'stats.get_statistics ims_usrloc_pcscf:')",
}


# ---------------------------------------------------------------------------
# Agent dependencies — injected into every tool via RunContext
# ---------------------------------------------------------------------------

@dataclass
class AgentDeps:
    """Shared dependencies available to all agent tools."""

    repo_root: Path
    """Path to the docker_open5gs repository root."""

    env: dict[str, str]
    """Merged environment variables from .env and e2e.env."""

    all_containers: list[str] = field(default_factory=lambda: [
        "mongo", "nrf", "scp", "ausf", "udr", "udm", "amf", "smf", "upf",
        "pcf", "dns", "mysql", "pyhss", "icscf", "scscf", "pcscf", "rtpengine",
    ])
    """Known container names visible to the RCA agent.

    Scoped to core + IMS containers only. The agent has no access to RAN (nr_gnb)
    or UE (e2e_ue1, e2e_ue2) containers — these are outside the NOC boundary.
    The agent must infer RAN/UE state from core-side metrics (ran_ue, gnb counts)."""

    pyhss_api: str = "http://localhost:8080"
    """PyHSS REST API base URL."""


# ---------------------------------------------------------------------------
# Structured output — what the agent produces
# ---------------------------------------------------------------------------

class TimelineEvent(BaseModel):
    """A single event in the cross-container investigation timeline."""

    timestamp: str
    """Timestamp as it appeared in the logs (not normalized)."""

    container: str
    """Which container produced this event."""

    event: str
    """What happened, in plain English."""


class Diagnosis(BaseModel):
    """Structured diagnosis produced by the agent."""

    summary: str
    """One-line summary of the issue."""

    timeline: list[TimelineEvent]
    """Chronological events across containers that tell the story."""

    root_cause: str
    """What went wrong and why."""

    affected_components: list[str]
    """Which containers/components are involved."""

    recommendation: str
    """What to do about it — actionable steps."""

    confidence: str
    """'high', 'medium', or 'low'."""

    explanation: str
    """Plain-English educational explanation for a telecom learner."""
