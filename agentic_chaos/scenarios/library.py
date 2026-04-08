"""
Scenario Library — 10 curated failure scenarios for the 5G SA + IMS stack.

Each scenario is a Scenario object ready to pass to run_scenario().
Scenarios are organized by blast radius: single NF → multi-NF → global.

Usage:
    from agentic_chaos.scenarios.library import SCENARIOS, get_scenario

    scenario = get_scenario("P-CSCF Latency")
    episode = await run_scenario(scenario)

IPs are from .env — hardcoded here because the scenario library is a
static definition. If IPs change, update these constants.
"""

from __future__ import annotations

from ..models import BlastRadius, FaultCategory, FaultSpec, Scenario

# -------------------------------------------------------------------------
# IPs from .env (used by network partition scenarios)
# -------------------------------------------------------------------------
_ICSCF_IP = "172.22.0.19"
_SCSCF_IP = "172.22.0.20"
_PCSCF_IP = "172.22.0.21"
_MYSQL_IP = "172.22.0.17"

# -------------------------------------------------------------------------
# Single-NF scenarios
# -------------------------------------------------------------------------

gnb_radio_link_failure = Scenario(
    name="gNB Radio Link Failure",
    description=(
        "Kill the gNB to simulate a radio link failure. All UEs lose 5G "
        "registration, PDU sessions drop, and IMS SIP unregisters."
    ),
    category=FaultCategory.CONTAINER,
    blast_radius=BlastRadius.SINGLE_NF,
    faults=[
        FaultSpec(fault_type="container_kill", target="nr_gnb", ttl_seconds=600),
    ],
    expected_symptoms=[
        "UEs lose RAN connection",
        "PDU sessions dropped",
        "SIP REGISTER expires without renewal",
        "gNB disappears from AMF",
    ],
    # Self-evident: killing the gNB collapses NGAP, AMF session count, and
    # connected-UE gauges immediately — but traffic generation still helps
    # the anomaly screener observe the impact pattern.
    required_traffic="none",
    observation_traffic_seconds=120,
    observation_window_seconds=30,
    ttl_seconds=600,
)

pcscf_latency = Scenario(
    name="P-CSCF Latency",
    description=(
        "Inject 500ms latency on the P-CSCF (SIP edge proxy). SIP T1 timer "
        "is 500ms, so REGISTER transactions will start timing out. Tests "
        "IMS resilience to WAN-like latency on the signaling path."
    ),
    category=FaultCategory.NETWORK,
    blast_radius=BlastRadius.SINGLE_NF,
    faults=[
        FaultSpec(
            fault_type="network_latency",
            target="pcscf",
            params={"delay_ms": 2000, "jitter_ms": 50},
            ttl_seconds=600,
        ),
    ],
    expected_symptoms=[
        "SIP REGISTER 408 Request Timeout",
        "Kamailio tm transaction timeouts",
        "IMS registration failures at UEs",
    ],
    # Control-plane fault: without a fresh REGISTER, existing cached
    # registrations stay put and 500ms of latency on the edge proxy
    # produces zero observable symptoms. ControlPlaneTrafficAgent forces
    # UE re-registration so new SIP transactions traverse the delayed path.
    required_traffic="control_plane",
    # Extended observation: generate 2 minutes of IMS traffic under the fault
    # while collecting metric snapshots for the anomaly screener.
    observation_traffic_seconds=120,
    escalation=True,
    observation_window_seconds=30,
    ttl_seconds=600,
)

scscf_crash = Scenario(
    name="S-CSCF Crash",
    description=(
        "Kill the S-CSCF (Serving-CSCF). This is the core SIP registrar and "
        "call controller. All IMS authentication stops, new registrations "
        "are impossible, and active calls will eventually drop."
    ),
    category=FaultCategory.CONTAINER,
    blast_radius=BlastRadius.SINGLE_NF,
    faults=[
        FaultSpec(fault_type="container_kill", target="scscf", ttl_seconds=600),
    ],
    expected_symptoms=[
        "IMS authentication fails (no MAR/MAA)",
        "New SIP REGISTER rejected or times out",
        "Active SIP dialogs expire",
        "I-CSCF cannot route to S-CSCF",
    ],
    # Control-plane fault: killing S-CSCF has no impact on existing
    # cached registrations until a new REGISTER needs routing through
    # I-CSCF → S-CSCF. Traffic generation exposes the outage.
    required_traffic="control_plane",
    observation_traffic_seconds=120,
    observation_window_seconds=30,
    ttl_seconds=600,
)

hss_unresponsive = Scenario(
    name="HSS Unresponsive",
    description=(
        "Inject 60-second outbound delay on the HSS (PyHSS). The HSS container "
        "is running, the process is alive, and the IP is reachable — but all "
        "Diameter responses are delayed by 60 seconds, far exceeding the Cx "
        "Diameter timeout. Tests how the I-CSCF and S-CSCF handle a Diameter "
        "peer that accepts connections but never responds in time."
    ),
    category=FaultCategory.NETWORK,
    blast_radius=BlastRadius.SINGLE_NF,
    faults=[
        FaultSpec(
            fault_type="network_latency",
            target="pyhss",
            params={"delay_ms": 60000, "jitter_ms": 0},
            ttl_seconds=600,
        ),
    ],
    expected_symptoms=[
        "Diameter UAR/UAA timeout at I-CSCF",
        "Diameter MAR/MAA timeout at S-CSCF",
        "SIP REGISTER stalls (waiting for Diameter)",
        "CDP peer state changes",
    ],
    # Control-plane fault: 60s latency on HSS only matters if somebody
    # is actually making Diameter queries. Traffic generation fires UAR/MAR
    # through the delayed path and exposes the timeout.
    required_traffic="control_plane",
    observation_traffic_seconds=120,
    observation_window_seconds=30,
    ttl_seconds=600,
)

data_plane_degradation = Scenario(
    name="Data Plane Degradation",
    description=(
        "Inject 30% packet loss on the UPF. RTP media streams will degrade, "
        "voice quality drops. Tests whether the stack detects and reports "
        "data plane quality issues."
    ),
    category=FaultCategory.NETWORK,
    blast_radius=BlastRadius.SINGLE_NF,
    faults=[
        FaultSpec(
            fault_type="network_loss",
            target="upf",
            params={"loss_pct": 30},
            ttl_seconds=600,
        ),
    ],
    expected_symptoms=[
        "RTP packet loss on voice calls",
        "GTP-U packet counters anomaly",
        "Potential call quality degradation",
    ],
    # User-plane fault: packet loss on UPF requires active RTP media
    # flowing through the data path. Traffic generation includes VoNR
    # calls so RTCP MOS/jitter/loss metrics reflect the degradation.
    required_traffic="user_plane",
    requires_active_call=True,  # legacy flag, kept in sync for back-compat
    observation_traffic_seconds=120,
    observation_window_seconds=30,
    ttl_seconds=600,
)


# -------------------------------------------------------------------------
# Global scenarios
# -------------------------------------------------------------------------

mongodb_gone = Scenario(
    name="MongoDB Gone",
    description=(
        "Kill MongoDB — the 5G core subscriber data store. UDR loses its "
        "backend, new PDU sessions cannot be created, and subscriber "
        "queries fail. Existing sessions may survive briefly."
    ),
    category=FaultCategory.CONTAINER,
    blast_radius=BlastRadius.GLOBAL,
    faults=[
        FaultSpec(fault_type="container_kill", target="mongo", ttl_seconds=600),
    ],
    expected_symptoms=[
        "UDR connection errors to MongoDB",
        "New PDU session creation fails",
        "5G subscriber queries fail",
        "AMF registration may still work (cached)",
    ],
    # Control-plane fault: killing MongoDB doesn't affect cached 5G
    # sessions. Traffic generation forces fresh SIP REGISTERs that
    # need PyHSS → MongoDB subscriber lookups, exposing the outage.
    required_traffic="control_plane",
    observation_traffic_seconds=120,
    observation_window_seconds=30,
    ttl_seconds=600,
)

dns_failure = Scenario(
    name="DNS Failure",
    description=(
        "Kill the DNS server. IMS domain resolution breaks — SIP routing "
        "depends on DNS NAPTR/SRV records for the IMS domain. All new "
        "SIP transactions that require DNS resolution will fail."
    ),
    category=FaultCategory.CONTAINER,
    blast_radius=BlastRadius.GLOBAL,
    faults=[
        FaultSpec(fault_type="container_kill", target="dns", ttl_seconds=600),
    ],
    expected_symptoms=[
        "IMS domain unresolvable",
        "SIP routing failures",
        "Kamailio DNS lookup errors",
        "New registrations fail",
    ],
    # Control-plane fault: DNS lookups only happen on new SIP
    # transactions. Traffic generation forces Kamailio to resolve the
    # IMS domain and surfaces the NAPTR/SRV failure.
    required_traffic="control_plane",
    observation_traffic_seconds=120,
    observation_window_seconds=30,
    ttl_seconds=600,
)


# -------------------------------------------------------------------------
# Multi-NF scenarios
# -------------------------------------------------------------------------

ims_network_partition = Scenario(
    name="IMS Network Partition",
    description=(
        "Partition the P-CSCF from both the I-CSCF and S-CSCF using iptables "
        "DROP rules. SIP signaling between the edge proxy and the core IMS "
        "is completely severed. Tests IMS behavior under a network split."
    ),
    category=FaultCategory.NETWORK,
    blast_radius=BlastRadius.MULTI_NF,
    faults=[
        FaultSpec(
            fault_type="network_partition",
            target="pcscf",
            params={"target_ip": _ICSCF_IP},
            ttl_seconds=600,
        ),
        FaultSpec(
            fault_type="network_partition",
            target="pcscf",
            params={"target_ip": _SCSCF_IP},
            ttl_seconds=600,
        ),
    ],
    expected_symptoms=[
        "SIP signaling severed (P-CSCF → I/S-CSCF)",
        "New REGISTER and INVITE fail",
        "Kamailio tm transaction timeouts",
        "Active calls may survive briefly (RTP via UPF, not CSCFs)",
    ],
    # Control-plane fault: iptables DROP on the CSCF-to-CSCF path only
    # breaks things if new SIP transactions try to traverse it.
    required_traffic="control_plane",
    observation_traffic_seconds=120,
    observation_window_seconds=30,
    ttl_seconds=600,
)

amf_restart = Scenario(
    name="AMF Restart (Upgrade Simulation)",
    description=(
        "Stop the AMF for 10 seconds, then restart it. Simulates a rolling "
        "upgrade of the access and mobility management function. UEs will "
        "temporarily lose their 5G NAS connection and must re-attach."
    ),
    category=FaultCategory.CONTAINER,
    blast_radius=BlastRadius.MULTI_NF,
    faults=[
        FaultSpec(
            fault_type="container_stop",
            target="amf",
            params={"timeout": 10},
            ttl_seconds=600,
        ),
    ],
    expected_symptoms=[
        "UEs lose NAS connection",
        "NGAP association dropped at gNB",
        "UEs must re-register after AMF recovers",
        "Temporary PDU session disruption",
    ],
    # Self-evident: stopping the AMF drops NGAP associations and AMF
    # session/UE count gauges go to zero immediately. Traffic generation
    # helps the anomaly screener capture the full impact pattern.
    required_traffic="none",
    observation_traffic_seconds=120,
    observation_window_seconds=45,
    ttl_seconds=600,
)

cascading_ims_failure = Scenario(
    name="Cascading IMS Failure",
    description=(
        "Kill PyHSS AND add 2-second latency to the S-CSCF. This simulates "
        "a cascading failure: the HSS is gone (no Diameter auth) AND the "
        "S-CSCF is degraded (slow SIP processing). Total IMS outage."
    ),
    category=FaultCategory.COMPOUND,
    blast_radius=BlastRadius.MULTI_NF,
    faults=[
        FaultSpec(fault_type="container_kill", target="pyhss", ttl_seconds=600),
        FaultSpec(
            fault_type="network_latency",
            target="scscf",
            params={"delay_ms": 2000},
            ttl_seconds=600,
        ),
    ],
    expected_symptoms=[
        "Diameter completely down (HSS killed)",
        "SIP transactions extremely slow (2s latency on S-CSCF)",
        "Total IMS registration failure",
        "No voice calls possible",
    ],
    # Control-plane fault: both HSS kill and S-CSCF latency only bite
    # when new SIP/Diameter transactions flow. Traffic generation
    # exposes the total IMS outage.
    required_traffic="control_plane",
    challenge_mode=True,
    observation_traffic_seconds=120,
    observation_window_seconds=30,
    ttl_seconds=600,
)


# -------------------------------------------------------------------------
# Registry
# -------------------------------------------------------------------------

SCENARIOS: dict[str, Scenario] = {
    s.name: s
    for s in [
        gnb_radio_link_failure,
        pcscf_latency,
        scscf_crash,
        hss_unresponsive,
        data_plane_degradation,
        mongodb_gone,
        dns_failure,
        ims_network_partition,
        amf_restart,
        cascading_ims_failure,
    ]
}


def get_scenario(name: str) -> Scenario:
    """Look up a scenario by name. Raises KeyError if not found."""
    if name not in SCENARIOS:
        available = "\n  ".join(sorted(SCENARIOS.keys()))
        raise KeyError(f"Unknown scenario '{name}'. Available:\n  {available}")
    return SCENARIOS[name]


def list_scenarios() -> list[dict]:
    """Return a summary list of all scenarios."""
    return [
        {
            "name": s.name,
            "category": s.category.value,
            "blast_radius": s.blast_radius.value,
            "faults": len(s.faults),
            "description": s.description[:80] + "..." if len(s.description) > 80 else s.description,
        }
        for s in SCENARIOS.values()
    ]
