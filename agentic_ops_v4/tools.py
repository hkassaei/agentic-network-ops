"""
Tool wrappers for v4 agents — reuses v1.5 tools plus topology-aware tooling.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Setup import path for agentic_ops
_REPO_ROOT = Path(__file__).resolve().parents[1]
_OPS_PATH = str(_REPO_ROOT)
if _OPS_PATH not in sys.path:
    sys.path.insert(0, _OPS_PATH)

from agentic_ops import tools as _t
from agentic_ops.models import AgentDeps

# -------------------------------------------------------------------------
# Output truncation
# -------------------------------------------------------------------------

_MAX_OUTPUT_BYTES = 10_240  # 10 KB


def _truncate_output(text: str, max_bytes: int = _MAX_OUTPUT_BYTES) -> str:
    """Keep the tail (most recent lines), discard oldest lines from the top.

    Docker logs are chronological — the most recent entries at the bottom are
    the ones relevant to the failure. Truncation preserves the tail and cuts
    at the nearest line boundary.
    """
    if len(text.encode("utf-8")) <= max_bytes:
        return text

    lines = text.splitlines(keepends=True)

    # Walk backward from the end, accumulating lines
    kept: list[str] = []
    total = 0
    for line in reversed(lines):
        line_bytes = len(line.encode("utf-8"))
        if total + line_bytes > max_bytes:
            break
        kept.append(line)
        total += line_bytes

    kept.reverse()
    omitted = len(lines) - len(kept)
    prefix = f"... truncated ({omitted} older lines omitted). Use grep to narrow your search.\n"
    return prefix + "".join(kept)


# -------------------------------------------------------------------------
# Module-level deps (loaded once, cached)
# -------------------------------------------------------------------------

_deps: AgentDeps | None = None


def _get_deps() -> AgentDeps:
    global _deps
    if _deps is not None:
        return _deps

    env: dict[str, str] = {**os.environ}
    for p in [_REPO_ROOT / "network" / ".env", _REPO_ROOT / "e2e.env"]:
        if p.exists():
            for line in p.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()

    _deps = AgentDeps(
        repo_root=_REPO_ROOT,
        env=env,
        pyhss_api=f"http://{env.get('PYHSS_IP', '172.22.0.18')}:8080",
    )
    return _deps


# -------------------------------------------------------------------------
# Tool wrappers — each is ADK LlmAgent compatible
# -------------------------------------------------------------------------

async def read_container_logs(container: str, tail: int = 200, grep: str | None = None) -> str:
    """Read recent logs from a Docker container.

    Args:
        container: Container name (e.g. 'pcscf', 'scscf', 'amf').
        tail: Number of recent lines to return (default 200).
        grep: Optional pattern to filter log lines (case-insensitive).
    """
    result = await _t.read_container_logs(_get_deps(), container, tail, grep)
    if not grep:
        return _truncate_output(result)
    return result


async def read_config(component: str) -> str:
    """Read the configuration file for a network component from the repo.

    Args:
        component: One of: amf, smf, upf, pcscf, scscf, icscf, pyhss,
                   dns, dns-ims-zone, ueransim-gnb, ueransim-ue.
    """
    return await _t.read_config(_get_deps(), component)


async def get_network_status() -> str:
    """Get the status of all network containers (running/exited/absent).

    Returns JSON with phase ('ready'/'partial'/'down') and per-container status.
    """
    return await _t.get_network_status(_get_deps())


async def query_subscriber(imsi: str, domain: str = "both") -> str:
    """Query subscriber data from 5G core (MongoDB) and/or IMS (PyHSS).

    Args:
        imsi: The subscriber's IMSI (e.g. '001011234567891').
        domain: 'core' for 5G only, 'ims' for IMS only, 'both' for both.
    """
    return await _t.query_subscriber(_get_deps(), imsi, domain)


async def read_env_config() -> str:
    """Read network topology, IPs, PLMN, and UE credentials from environment files.

    Call this to discover the live topology: IPs, subscriber identities, IMS domain.
    """
    return await _t.read_env_config(_get_deps())


async def search_logs(pattern: str, containers: list[str] | None = None, since: str | None = None) -> str:
    """Search for a pattern across multiple container logs.

    Args:
        pattern: Search pattern (case-insensitive). Can be a Call-ID,
                 IMSI, SIP method, error keyword, etc.
        containers: Optional list of containers to search. Searches all if None.
        since: Optional time filter (e.g. '5m', '1h').
    """
    result = await _t.search_logs(_get_deps(), pattern, containers, since)
    return _truncate_output(result)


async def query_prometheus(query: str) -> str:
    """Query Prometheus for 5G core NF metrics using PromQL.

    Args:
        query: PromQL query string.
    """
    return await _t.query_prometheus(_get_deps(), query)


async def get_nf_metrics() -> str:
    """Get a full metrics snapshot across ALL network functions in one call.

    Collects from Prometheus (5G core), kamcmd (IMS Kamailio), RTPEngine,
    PyHSS, and MongoDB. This is the 'radiograph' — a quick health overview
    of the entire stack.
    """
    return await _t.get_nf_metrics(_get_deps())


async def run_kamcmd(container: str, command: str) -> str:
    """Run a kamcmd command inside a Kamailio container to inspect runtime state.

    Args:
        container: Kamailio container ('pcscf', 'icscf', or 'scscf').
        command: kamcmd command. Examples:
            - cdp.list_peers — Diameter peer connections and state
            - ulscscf.showimpu sip:imsi@domain — S-CSCF registration lookup
            - stats.get_statistics all — all stats
    """
    return await _t.run_kamcmd(_get_deps(), container, command)


async def read_running_config(container: str, grep: str | None = None) -> str:
    """Read the ACTUAL config from a running container (not the repo copy).

    Args:
        container: Container name (pcscf, icscf, scscf, amf, smf, upf).
        grep: Optional pattern to filter config lines (case-insensitive).
              ALWAYS use grep to avoid dumping entire config files.
    """
    return await _t.read_running_config(_get_deps(), container, grep)


async def check_process_listeners(container: str) -> str:
    """Check what ports and protocols a container's processes are listening on.

    Args:
        container: Container name (e.g. 'pcscf', 'scscf', 'amf').
    """
    return await _t.check_process_listeners(_get_deps(), container)


async def check_tc_rules(container: str) -> str:
    """Check for active traffic control (tc) rules on a container's network interface.

    CRITICAL: Call this FIRST on any container showing timeouts. Detects
    injected latency (netem delay), packet loss (netem loss), bandwidth
    limits (tbf), or corruption. If netem/tbf rules are present, they are
    the root cause — do not investigate application-layer issues.

    Args:
        container: Container name (e.g. 'pcscf', 'upf', 'scscf').
    """
    return await _t.check_tc_rules(_get_deps(), container)


async def measure_rtt(container: str, target_ip: str) -> str:
    """Measure round-trip time (RTT) from a container to a target IP.

    Normal Docker bridge RTT is <1ms. Elevated RTT (>10ms) indicates
    abnormal latency or congestion. Use to confirm tc netem faults.

    Args:
        container: Source container name (e.g. 'pcscf', 'icscf').
        target_ip: Target IP address to ping (e.g. '172.22.0.19').
    """
    return await _t.measure_rtt(_get_deps(), container, target_ip)


# -------------------------------------------------------------------------
# Topology tool (v4-only)
# -------------------------------------------------------------------------

# Nodes outside the NOC boundary — filtered from the topology view.
# Edges TO these nodes are kept but the external endpoint is shown as
# an opaque boundary label (e.g. "[RAN]") so the agent can see that
# an interface has no peer without seeing the actual container.
_NOC_HIDDEN_NODES = {"nr_gnb", "e2e_ue1", "e2e_ue2"}
_BOUNDARY_LABELS = {
    "nr_gnb": "[RAN]",
    "e2e_ue1": "[UE]",
    "e2e_ue2": "[UE]",
}


async def get_network_topology() -> str:
    """Get the live network topology: nodes, link status, and connectivity graph.

    Shows which containers are running/down, how they connect via 3GPP
    interfaces (N2, N4, Gm, Cx, etc.), and which links are active vs
    inactive. Use this FIRST to understand the network structure and
    identify broken paths.

    INACTIVE links mean a broken path — the single strongest triage signal.
    """
    gui_dir = str(_REPO_ROOT / "gui")
    if gui_dir not in sys.path:
        sys.path.insert(0, gui_dir)

    from topology import build_topology

    deps = _get_deps()
    topo = await build_topology(deps.env)

    # Partition nodes into visible (NOC) and hidden (boundary)
    visible_nodes = [n for n in topo.nodes if n.id not in _NOC_HIDDEN_NODES]
    hidden_status = {n.id: n.status for n in topo.nodes if n.id in _NOC_HIDDEN_NODES}

    # Group visible nodes by layer
    by_layer: dict[str, list] = {}
    for n in visible_nodes:
        by_layer.setdefault(n.layer, []).append(n)

    lines = [f"Network Topology — Phase: {topo.phase}\n"]

    # Nodes by layer
    layer_order = ["data", "core", "ims"]
    for layer in layer_order:
        nodes = by_layer.get(layer, [])
        if not nodes:
            continue
        entries = [f"{n.label}({n.status})" for n in nodes]
        lines.append(f"  {layer}: {', '.join(entries)}")

    # Partition edges into inactive and active
    inactive: list[str] = []
    active: list[str] = []

    for e in topo.edges:
        if e.logical:
            continue  # Skip N1 NAS logical edges

        src_hidden = e.source in _NOC_HIDDEN_NODES
        tgt_hidden = e.target in _NOC_HIDDEN_NODES

        # Build display names — replace hidden nodes with boundary labels
        src_label = _BOUNDARY_LABELS.get(e.source, e.source.upper())
        tgt_label = _BOUNDARY_LABELS.get(e.target, e.target.upper())

        # For visible nodes, use the node label from topology
        if not src_hidden:
            node = next((n for n in visible_nodes if n.id == e.source), None)
            src_label = node.label if node else e.source.upper()
        if not tgt_hidden:
            node = next((n for n in visible_nodes if n.id == e.target), None)
            tgt_label = node.label if node else e.target.upper()

        link_str = f"  {e.label}: {src_label} → {tgt_label}"

        if not e.active:
            # Explain why inactive
            reasons = []
            if src_hidden and hidden_status.get(e.source) != "running":
                reasons.append(f"{src_label} not connected")
            elif not src_hidden:
                node = next((n for n in visible_nodes if n.id == e.source), None)
                if node and node.status != "running":
                    reasons.append(f"{src_label} is {node.status}")
            if tgt_hidden and hidden_status.get(e.target) != "running":
                reasons.append(f"{tgt_label} not connected")
            elif not tgt_hidden:
                node = next((n for n in visible_nodes if n.id == e.target), None)
                if node and node.status != "running":
                    reasons.append(f"{tgt_label} is {node.status}")
            reason = " — " + ", ".join(reasons) if reasons else ""
            inactive.append(f"{link_str} [INACTIVE{reason}]")
        else:
            active.append(f"{link_str} [active]")

    lines.append("")
    if inactive:
        lines.append(f"INACTIVE LINKS ({len(inactive)}):")
        lines.extend(inactive)
        lines.append("")

    lines.append(f"ACTIVE LINKS ({len(active)}):")
    lines.extend(active)

    return "\n".join(lines)


# -------------------------------------------------------------------------
# Network Ontology tool (v4 — knowledge graph queries)
# -------------------------------------------------------------------------

async def query_ontology(
    observations_json: str,
) -> str:
    """Query the network ontology for diagnosis based on observed symptoms.

    The ontology encodes pre-computed causal chains, log semantics, symptom
    signatures, and protocol stack rules for the 5G SA + IMS stack. It
    replaces open-ended LLM reasoning about causality with deterministic
    pattern matching.

    Args:
        observations_json: JSON string with observed state. Keys:
            - Metric names with current values (e.g. "ran_ue": 0, "gnb": 0)
            - "container_status": {"nr_gnb": "exited", "amf": "running", ...}
            - "log_patterns_seen": ["amf_sctp_refused", "ue_jitter_buffer_reset"]
            - "tc_rules_found": true/false (if check_tc_rules found netem/tbf)

    Returns:
        Structured diagnosis including matched signatures, triggered stack
        rules, baseline anomalies, and recommended diagnostic actions.
    """
    import json as _json

    try:
        observations = _json.loads(observations_json)
    except _json.JSONDecodeError:
        return "ERROR: observations_json must be valid JSON"

    try:
        from network_ontology.query import OntologyClient
        client = OntologyClient()
        result = client.diagnose(observations)
        client.close()
        return _json.dumps(result, indent=2, default=str)
    except ImportError:
        return "ERROR: network_ontology package not installed. Run: pip install -e network_ontology/"
    except Exception as e:
        return f"ERROR: Ontology query failed: {e}"


async def interpret_log_message(
    message: str,
    source: str = "",
) -> str:
    """Look up the semantic meaning of a log message in the network ontology.

    The ontology contains annotated log patterns with their actual meaning,
    common misinterpretations, and diagnostic actions. This prevents the
    most common agent failure: misinterpreting log messages.

    Args:
        message: The log message text to interpret.
        source: Optional container name that produced the log (e.g. "amf", "icscf").

    Returns:
        Matching patterns with meaning, does_NOT_mean warnings, and actions.
    """
    import json as _json

    try:
        from network_ontology.query import OntologyClient
        client = OntologyClient()
        matches = client.interpret_log(message, source=source or None)
        client.close()

        if not matches:
            return "No matching log pattern found in ontology."

        results = []
        for m in matches:
            entry = {
                "pattern": m.get("pattern"),
                "meaning": m.get("meaning"),
                "is_benign": m.get("is_benign", False),
                "does_NOT_mean": m.get("does_not_mean", []),
                "actual_implication": m.get("actual_implication", ""),
                "is_root_cause": m.get("is_root_cause"),
            }
            results.append(entry)

        return _json.dumps(results, indent=2, default=str)
    except ImportError:
        return "ERROR: network_ontology package not installed."
    except Exception as e:
        return f"ERROR: Log interpretation failed: {e}"


async def check_component_health(component: str) -> str:
    """Look up the health check protocol for a component from the ontology,
    then explain what probes to run and how to interpret results.

    Use this to resolve ambiguity: when symptoms could point to multiple
    failure modes, a health check on a suspected component determines
    whether it is the root cause or an innocent bystander.

    Example: ran_ue=0 could mean "gNB is down" OR "AMF crashed."
    Health-checking AMF resolves this — if AMF is healthy, the problem
    is upstream at the gNB.

    Args:
        component: Component name (e.g. "amf", "upf", "pcscf", "nr_gnb", "pyhss").

    Returns:
        Health check protocol with probes (ordered cheapest-first),
        healthy/degraded/down criteria, and disambiguation guidance.
    """
    import json as _json

    try:
        from network_ontology.query import OntologyClient
        client = OntologyClient()
        hc = client.get_healthcheck(component)
        client.close()

        if not hc:
            return f"No health check defined for component '{component}'."

        return _json.dumps(hc, indent=2, default=str)
    except ImportError:
        return "ERROR: network_ontology package not installed."
    except Exception as e:
        return f"ERROR: Health check query failed: {e}"


async def get_causal_chain(component: str) -> str:
    """Get the pre-computed causal failure chain for a component.

    Returns what happens when this component fails: immediate effects on
    connected interfaces, cascading effects on downstream components,
    observable symptoms at each node, and common misinterpretations to avoid.

    Args:
        component: Component name (e.g. "nr_gnb", "upf", "pcscf", "scscf").

    Returns:
        Complete causal chain with symptoms, does_NOT_mean warnings, and
        diagnostic actions.
    """
    import json as _json

    try:
        from network_ontology.query import OntologyClient
        client = OntologyClient()
        chains = client.get_causal_chain_for_component(component)
        client.close()

        if not chains:
            return f"No causal chain found for component '{component}'."

        return _json.dumps(chains, indent=2, default=str)
    except ImportError:
        return "ERROR: network_ontology package not installed."
    except Exception as e:
        return f"ERROR: Causal chain query failed: {e}"
