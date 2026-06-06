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
_NR_GNB_IP = "172.22.0.23"

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
    observation_traffic_seconds=120,
    observation_window_seconds=30,
    ttl_seconds=600,
)

pcscf_latency = Scenario(
    name="P-CSCF Latency",
    description=(
        "Inject 2000ms latency (with 50ms jitter) on the P-CSCF (SIP edge "
        "proxy). SIP transactions will experience severe delays as every "
        "message entering and leaving the P-CSCF is delayed, compounding "
        "across multiple round-trips in the IMS registration chain. Tests "
        "IMS resilience to high latency on the signaling edge."
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
    observation_traffic_seconds=120,
    observation_window_seconds=30,
    ttl_seconds=600,
)

hss_unresponsive = Scenario(
    name="HSS Unresponsive",
    description=(
        "Inject 60-second outbound delay on the HSS (PyHSS), making it "
        "functionally unreachable for all real-time protocols. The HSS "
        "container is running and the process is alive, but all network "
        "responses are delayed by 60 seconds — far exceeding Diameter Cx "
        "timeouts (5-30s) and standard probe timeouts (10s). From the "
        "perspective of diagnostic tools and IMS peers, the HSS appears "
        "completely unresponsive or unreachable."
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
        "measure_rtt to HSS shows 100% packet loss (60s delay exceeds 10s probe timeout)",
        "HSS appears unreachable/unresponsive despite container running",
    ],
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
    observation_traffic_seconds=120,
    observation_window_seconds=30,
    ttl_seconds=600,
)

rtpengine_latency_injection = Scenario(
    name="RTPEngine Latency Injection",
    description=(
        "Inject 100ms latency on RTPEngine egress. Same fault locus as "
        "Call Quality Degradation (rtpengine container, kernel-level "
        "qdisc) but the manifestation is delay rather than drop. Tests "
        "v7's path-walk generalization from `drops_attributed_here` to "
        "`latency_at_hop` — both are first-class HopAttribution variants. "
        "Operators see audio jitter / one-way audio rather than gappy "
        "audio. v7's `KernelHopProber` reads the qdisc's authored "
        "`delay 100ms` parameter and v7's unified Synthesis LLM emits "
        "verdict_kind=localized with attribution_kind=latency_at_hop. "
        "v6's per-NF pipeline mis-diagnoses for the same reason it "
        "mis-diagnoses Call Quality Degradation: rtpengine.errors_per_second "
        "stays at 0 (the relay loop sees no errors), and 3-ping measure_rtt "
        "is too undersampled to reliably distinguish 100ms latency from "
        "Docker-bridge baseline."
    ),
    category=FaultCategory.NETWORK,
    blast_radius=BlastRadius.SINGLE_NF,
    faults=[
        FaultSpec(
            fault_type="network_latency",
            target="rtpengine",
            params={"delay_ms": 100, "jitter_ms": 0},
            ttl_seconds=600,
        ),
    ],
    expected_symptoms=[
        "RTCP one-way RTT spikes by ~100ms (one direction; symmetric "
        "delay would double)",
        "Audio jitter increases at receiver UE",
        "rtpengine.errors_per_second UNCHANGED (relay loop is healthy)",
        "rtpengine.loss_ratio UNCHANGED (delay does not drop packets)",
        "UPF GTP counters UNAFFECTED (delay is on rtpengine egress only)",
        "SIP signaling UNAFFECTED (doesn't traverse rtpengine)",
    ],
    observation_traffic_seconds=120,
    observation_window_seconds=30,
    ttl_seconds=600,
)

upf_bandwidth_cap = Scenario(
    name="UPF Bandwidth Cap",
    description=(
        "Cap UPF egress at 100 kbit/s with a tc tbf qdisc. The cap is "
        "deliberately tight — VoNR media (G.711 ~64 kbit/s per direction "
        "at 100 pps) plus signaling traffic exceeds the budget; tbf drops "
        "over-rate packets. Tests v7's path walk localizing a "
        "bandwidth-induced drop counter at a tbf qdisc, complementing "
        "the netem-loss case. The KernelHopProber distinguishes "
        "qdisc_tbf from qdisc_netem in the counter_kind field. v6 "
        "would see UPF GTP counters drop and likely diagnose UPF "
        "correctly by NF, but with low confidence and without naming "
        "the qdisc — v7 names the qdisc and the exact dropped count."
    ),
    category=FaultCategory.NETWORK,
    blast_radius=BlastRadius.SINGLE_NF,
    faults=[
        FaultSpec(
            fault_type="network_bandwidth",
            target="upf",
            params={"rate_kbit": 100},
            ttl_seconds=600,
        ),
    ],
    expected_symptoms=[
        "upf.gtp_outdatapktn3upf_per_ue drops below baseline (egress capped)",
        "upf.gtp_indatapktn3upf_per_ue partially drops (depends on "
        "direction the cap applies to)",
        "Voice quality degrades — overflow packets dropped",
        "tbf qdisc reports non-zero `dropped` counter on UPF eth0",
    ],
    observation_traffic_seconds=120,
    observation_window_seconds=30,
    ttl_seconds=600,
)

pcscf_packet_loss = Scenario(
    name="P-CSCF Packet Loss",
    description=(
        "Inject 30% packet loss on the P-CSCF (SIP edge proxy) — the "
        "same fault class as Call Quality Degradation but on a "
        "signaling-plane container. Packets leaving P-CSCF (REGISTER "
        "forwards to I-CSCF, 401/200 responses to UEs) are silently "
        "dropped by the kernel after Kamailio's sendto() returns "
        "success. SIP retransmission timers (T1 = 500 ms) absorb "
        "some of the loss; a meaningful fraction of registrations "
        "still time out. This is the second worked example in ADR "
        "`path_anchored_probe_planning_for_transport_layer_faults.md` "
        "— it proves that the same fault class manifests in the "
        "signaling plane and that v7's path walk localizes both "
        "data-plane (Call Quality Degradation) and signaling-plane "
        "(this scenario) instances of it correctly. v6's per-NF "
        "hypothesis pipeline mis-diagnoses both."
    ),
    category=FaultCategory.NETWORK,
    blast_radius=BlastRadius.SINGLE_NF,
    faults=[
        FaultSpec(
            fault_type="network_loss",
            target="pcscf",
            params={"loss_pct": 30},
            ttl_seconds=600,
        ),
    ],
    expected_symptoms=[
        "pcscf.avg_register_time_ms spikes (UE retransmissions before success)",
        "icscf.rcv_requests_register_per_ue drops to ~70% of baseline",
        "scscf.rcv_requests_register_per_ue drops further (compounded)",
        "IMS registration completion rate drops",
        "Kamailio internal counters (pcscf.errors_per_second) UNCHANGED — "
        "kernel-level drops are below the application's `sendto()` boundary",
        "Data plane (UPF GTP counters, RTPEngine) UNAFFECTED — media path "
        "doesn't traverse P-CSCF",
        "Diameter timeout-ratio metrics may spike if registration cascades "
        "fail before HSS responses come back",
    ],
    observation_traffic_seconds=120,
    observation_window_seconds=30,
    ttl_seconds=600,
)

call_quality_degradation = Scenario(
    name="Call Quality Degradation",
    description=(
        "Inject 30% packet loss on RTPEngine — the media relay for VoNR "
        "voice calls. RTP packets are dropped after RTPEngine receives them, "
        "degrading voice quality (MOS drop, jitter increase, audible "
        "artifacts). SIP signaling and 5G core are completely unaffected "
        "because they don't traverse RTPEngine. Tests whether the agent can "
        "diagnose a pure media-path fault without IMS signaling noise."
    ),
    category=FaultCategory.NETWORK,
    blast_radius=BlastRadius.SINGLE_NF,
    faults=[
        FaultSpec(
            fault_type="network_loss",
            target="rtpengine",
            params={"loss_pct": 30},
            ttl_seconds=600,
        ),
    ],
    expected_symptoms=[
        "RTPEngine packets_lost increases",
        "RTPEngine average_packet_loss rises",
        "RTPEngine average_mos drops below 3.5",
        "RTPEngine packet_loss_standard_deviation spikes",
        "RTPEngine 1-way streams may appear",
        "UPF GTP-U counters unaffected",
        "IMS signaling (SIP, Diameter) unaffected",
    ],
    observation_traffic_seconds=120,
    observation_window_seconds=30,
    ttl_seconds=600,
)


# -------------------------------------------------------------------------
# Novel scenarios (CDR-0001 — added 2026-06-05)
# -------------------------------------------------------------------------

asymmetric_path_loss_amf_to_gnb = Scenario(
    name="Asymmetric Path Loss (AMF→gNB)",
    description=(
        "Apply 60% packet loss to AMF's egress destined for the gNB IP "
        "ONLY — packets from AMF to gNB are lossy; packets from gNB to "
        "AMF are clean. Implemented via `tc prio` + `tc filter dst "
        "$NR_GNB_IP/32 → flowid 1:1` + `netem loss 60%` on class 1:1, "
        "so only matching flows hit the netem qdisc. From the gNB's "
        "POV: AMF-originated SCTP heartbeats are dropped, NGAP DL NAS "
        "messages don't arrive, association marked DOWN. From AMF's "
        "POV: gNB-originated SCTP heartbeats arrive cleanly, NGAP "
        "association looks UP. The two sides disagree about whether "
        "they are connected. This is the FIRST scenario where "
        "`ping nr_gnb FROM amf` and `ping amf FROM nr_gnb` produce "
        "divergent answers — breaks the agent's implicit symmetric-"
        "reachability assumption. CDR-0001 §3."
    ),
    category=FaultCategory.NETWORK,
    blast_radius=BlastRadius.MULTI_NF,
    faults=[
        FaultSpec(
            fault_type="network_loss",
            target="amf",
            params={"loss_pct": 60, "peer_ip": _NR_GNB_IP},
            ttl_seconds=600,
        ),
    ],
    expected_symptoms=[
        "SCTP heartbeats AMF→gNB: 60% lost; gNB→AMF: clean",
        "gNB declares NGAP association DOWN after ~3 missed heartbeats",
        "AMF still considers the gNB association UP",
        "`ping nr_gnb` FROM amf: ~60% loss",
        "`ping amf` FROM nr_gnb: 0% loss (the discriminating signal)",
        "New UE attaches: Initial UE Message reaches AMF, "
        "Authentication Request never reaches UE → UE retries at "
        "T3510 (15s) until cell re-select",
        "Existing PDU sessions: intact (N3 data plane is UPF↔gNB, "
        "not AMF↔gNB)",
        "Container health, CPU, memory: nominal everywhere",
    ],
    observation_traffic_seconds=120,
    observation_window_seconds=30,
    ttl_seconds=600,
)

selective_subscriber_corruption_ue1 = Scenario(
    name="Selective Subscriber Corruption (UE1)",
    description=(
        "Corrupt UE1's K (long-term authentication key) in PyHSS's MySQL "
        "`auc` table while leaving UE2 untouched. UE2 calls work end-to-"
        "end. UE1 enters a registration loop and never completes "
        "Authentication — AMF logs 5GMM cause #20 (MAC failure). The "
        "first scenario where the failure is PER-SUBSCRIBER, not per-"
        "NF: every container is healthy, every link is clean, the "
        "aggregate `pyhss_auth_failures_total` ticks too slowly to "
        "cross the screener threshold over a 2-min observation "
        "window. The fault lives in DATA, not infrastructure. Forces "
        "the agent to compare UE1 vs UE2 side-by-side and reach for "
        "`query_subscriber` for the diverging UE. Heal restores the "
        "original K from the snapshot taken at inject time, then "
        "restarts UE1's container to clear AMF's cached security "
        "context. CDR-0001 §2."
    ),
    category=FaultCategory.APPLICATION,
    blast_radius=BlastRadius.SINGLE_NF,
    faults=[
        FaultSpec(
            fault_type="subscriber_credential_corruption",
            target="pyhss",
            params={"imsi": "001011234567891", "ue_container": "e2e_ue1"},
            ttl_seconds=600,
        ),
    ],
    expected_symptoms=[
        "UE1 NAS Authentication Response carries wrong RES → AMF "
        "logs `5GMM cause #20 MAC failure`",
        "UE1 reattach loop: RRC Connection Setup repeatedly for "
        "UE1's TMSI",
        "UE2: green across the board, IMS registration steady, "
        "calls work",
        "`ran_ue` gauge oscillates between 1.0 and 2.0 as UE1 retries",
        "`ims_usrloc_pcscf:registered_contacts` settles at 1.0 (UE2 only)",
        "All container health: green. PyHSS itself is fine.",
        "Aggregate `pyhss_auth_failures_total` ticks slowly — may not "
        "cross screener threshold; per-IMSI counter would (we don't "
        "currently expose one — see CDR-0001 implementation notes)",
    ],
    observation_traffic_seconds=120,
    observation_window_seconds=30,
    ttl_seconds=600,
)

pmtu_blackhole_n3 = Scenario(
    name="PMTU Black-Hole on N3",
    description=(
        "Drop UPF's eth0 MTU from 1500 to 1280 and add iptables "
        "rules that silently drop outbound ICMP `fragmentation-"
        "needed` replies. Path MTU Discovery is defeated: large "
        "packets are dropped silently and the sender never learns "
        "to shrink them. Voice (small RTP ~200 B) sounds perfect. "
        "Large SIP INVITEs with full SDP, NAS messages with QoS "
        "rules, and any payload over ~1240 B vanish. The classic "
        "PMTU black-hole pattern: voice works, signaling fails. "
        "First scenario with a SIZE-DEPENDENT failure mode — every "
        "existing scenario degrades all packets uniformly. Forces "
        "v7 to reason about packet-size as a fault axis, "
        "distinguishing it from loss (which would affect both "
        "voice and signaling proportionally), partition (which "
        "would kill both), and latency (which would degrade voice "
        "quality first). CDR-0001 §4.\n\n"
        "WHY eth0 IS N3 in this lab (CDR-0001 Task 1.2): the UPF's "
        "GTP-U endpoint binds and advertises on `UPF_IP=172.22.0.8` "
        "(see `network/.env` and `network/upf/upf.yaml` gtpu.server "
        "block). 172.22.0.8 is the docker bridge address that the "
        "upf container exposes on eth0 — so all N3 GTP-U traffic "
        "between gNB (172.22.0.23) and UPF rides eth0. The TUN "
        "interfaces `ogstun` and `ogstun2` are the INNER APN "
        "delivery points (where the UPF emits decapsulated user "
        "traffic), not part of the N3 GTP-U path. To verify on a "
        "different deployment: `docker exec upf ip route` should "
        "show 172.22.0.0/24 via eth0 — that's the N3 link to gNB."
    ),
    category=FaultCategory.COMPOUND,
    blast_radius=BlastRadius.SINGLE_NF,
    faults=[
        FaultSpec(
            fault_type="pmtu_blackhole",
            target="upf",
            params={"mtu": 1280, "iface": "eth0"},
            ttl_seconds=300,
        ),
    ],
    expected_symptoms=[
        "Voice calls in progress (small RTP): perfectly clean",
        "`fivegs_ep_n3_gtp_indatapktn3upf` continues incrementing "
        "(small packets pass)",
        "New VoNR call setup: large SIP INVITE never arrives, "
        "UAC retransmits, 408 Request Timeout",
        "Re-INVITE on hold/resume: dies the same way",
        "New PDU Session Establishment with full QoS: NAS Accept "
        "dropped, session never completes",
        "`tcpdump` on UPF N3: large packets enter, no ICMP-Frag-Needed "
        "leaves, senders retransmit indefinitely",
        "Container health, NF Prometheus: green — no counter says "
        "'I dropped a too-big packet'",
    ],
    observation_traffic_seconds=120,
    observation_window_seconds=30,
    ttl_seconds=300,
)

pyhss_clock_skew_observability = Scenario(
    name="PyHSS Clock Skew (Observability)",
    description=(
        "Step PyHSS's wall clock forward by 47 minutes via libfaketime. "
        "Verified in CDR-0001 §1: this lab's PyHSS uses pure counter-"
        "based SQN (no time dependency), Diameter Cx is cleartext SCTP "
        "(no certs), and Kamailio's `date_check` module is not loaded. "
        "Result: NO functional impact. All UE registrations and calls "
        "continue working. The fault is purely OBSERVABILITY-degrading "
        "— PyHSS log timestamps and Diameter Session-Id high-32 fields "
        "drift 47 minutes into the future. The screener and the "
        "log-correlation surface will look anomalous, but no protocol "
        "actually breaks. NEGATIVE-CONTROL test: the correct v7 verdict "
        "is INCONCLUSIVE / 'observability anomaly, no functional fault.' "
        "If v7 hallucinates a PyHSS auth or Diameter outage to explain "
        "the timestamp drift, that's a false-positive failure mode we "
        "need to harden against. **Requires one-time PyHSS Dockerfile "
        "prep (libfaketime + LD_PRELOAD + /etc/faketimerc); see "
        "CDR-0001 §1 Injection mechanism.** Without prep, fault injection "
        "fails fast with a clear message; heal is a harmless no-op."
    ),
    category=FaultCategory.APPLICATION,
    blast_radius=BlastRadius.SINGLE_NF,
    faults=[
        FaultSpec(
            fault_type="clock_skew",
            target="pyhss",
            params={"skew_seconds": 2820},  # +47 min
            ttl_seconds=600,
        ),
    ],
    expected_symptoms=[
        "PyHSS `date` is 47 min ahead of every other NF",
        "PyHSS log timestamps appear in the future",
        "Diameter Session-Id high-32 carries future-relative values "
        "(cosmetic)",
        "All UE registrations + calls continue working normally",
        "5G-AKA functions normally (PyHSS uses counter-based SQN)",
        "SIP Digest auth functions normally (Kamailio date_check not loaded)",
        "Container health, CPU, memory: nominal everywhere",
        "CORRECT diagnosis is 'no functional fault' — not a PyHSS outage",
    ],
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
        pcscf_packet_loss,
        call_quality_degradation,
        rtpengine_latency_injection,
        upf_bandwidth_cap,
        # CDR-0001 — novel scenarios (2026-06-05)
        asymmetric_path_loss_amf_to_gnb,
        selective_subscriber_corruption_ue1,
        pmtu_blackhole_n3,
        pyhss_clock_skew_observability,
        # Global
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
