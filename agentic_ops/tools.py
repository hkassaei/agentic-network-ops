"""
Tool implementations for the Telecom Troubleshooting Agent.

Each tool is an async function that receives RunContext[AgentDeps] and returns
data for the LLM to reason about. Tools shell out to Docker CLI for container
access and read files from the repository for configuration.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx

from .models import AgentDeps

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_MAX_OUTPUT_LINES = 500


async def _shell(cmd: str, cwd: str | None = None) -> tuple[int, str]:
    """Run a shell command and return (returncode, combined output)."""
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        cwd=cwd,
    )
    stdout, _ = await proc.communicate()
    return proc.returncode or 0, stdout.decode(errors="replace")


def _truncate(text: str, max_lines: int = _MAX_OUTPUT_LINES) -> str:
    """Truncate output if it exceeds max_lines, with a warning."""
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    truncated = lines[:max_lines]
    truncated.append(f"\n... truncated ({len(lines) - max_lines} more lines). Refine your query to see more specific results.")
    return "\n".join(truncated)


# ---------------------------------------------------------------------------
# Diagnostic toolbelt preflight
# ---------------------------------------------------------------------------
#
# Any probe that shells into a container must call _container_has_binary
# first; if the binary is missing, return PROBE_TOOL_UNAVAILABLE_PREFIX +
# explanation rather than a generic failure. The v6 Investigator prompt
# teaches the LLM to map this token to ProbeResult.outcome="tool_unavailable",
# which the confidence-cap guardrail then excludes from evidence-strength
# computation.
#
# See docs/ADR/nf_container_diagnostic_tooling.md.

PROBE_TOOL_UNAVAILABLE_PREFIX = "PROBE_TOOL_UNAVAILABLE:"

# Cache `command -v` results for the lifetime of the process. Containers
# do not gain or lose binaries mid-run, so re-checking is wasted overhead
# and adds Docker latency to every probe.
_BINARY_AVAILABILITY_CACHE: dict[tuple[str, str], bool] = {}


async def _container_has_binary(container: str, binary: str) -> bool:
    """Return True iff `binary` is on PATH inside `container`.

    Result is cached per (container, binary) for the lifetime of the
    process. The audit script
    (`scripts/audit-container-tooling.sh`) is the deploy-time version
    of the same check; this helper is the runtime version that gates
    probe execution.
    """
    key = (container, binary)
    if key in _BINARY_AVAILABILITY_CACHE:
        return _BINARY_AVAILABILITY_CACHE[key]
    rc, _ = await _shell(
        f"docker exec {container} sh -c 'command -v {binary} >/dev/null 2>&1'"
    )
    available = rc == 0
    _BINARY_AVAILABILITY_CACHE[key] = available
    return available


def _tool_unavailable(container: str, binary: str, probe: str) -> str:
    """Render the standard PROBE_TOOL_UNAVAILABLE message for a probe.

    Format chosen so the v6 Investigator's prompt can pattern-match
    the prefix and emit ProbeResult(outcome='tool_unavailable'). The
    message names the probe and the missing binary so the
    Investigator can surface the gap in its reasoning text.
    """
    return (
        f"{PROBE_TOOL_UNAVAILABLE_PREFIX} {probe} cannot run on container "
        f"`{container}` — required binary `{binary}` is not present. "
        "The probe did not execute. Treat this as no evidence — "
        "neither confirms nor contradicts the hypothesis. "
        "(Toolbelt contract violated; see "
        "docs/ADR/nf_container_diagnostic_tooling.md.)"
    )


# Config file paths relative to repo root, keyed by component name.
_CONFIG_PATHS: dict[str, str] = {
    "amf": "amf/amf.yaml",
    "smf": "smf/smf.yaml",
    "upf": "upf/upf.yaml",
    "pcscf": "pcscf/pcscf.cfg",
    "scscf": "scscf/scscf.cfg",
    "icscf": "icscf/icscf.cfg",
    "pyhss": "pyhss/config.yaml",
    "dns": "dns/named.conf",
    "dns-ims-zone": "dns/ims_zone",
    "ueransim-gnb": "ueransim/ueransim-gnb.yaml",
    "ueransim-ue": "ueransim/ueransim-ue.yaml",
}


# ---------------------------------------------------------------------------
# Tool 1: read_container_logs
# ---------------------------------------------------------------------------

async def read_container_logs(
    deps: AgentDeps,
    container: str,
    tail: int = 200,
    grep: str | None = None,
    since_seconds: int | None = None,
) -> str:
    """Read recent logs from a Docker container.

    Args:
        deps: Agent dependencies.
        container: Container name (e.g. 'pcscf', 'scscf', 'amf', 'upf').
        tail: Number of recent lines to return (default 200). Ignored if
            since_seconds is set AND grep is not set (in which case all
            matching lines in the time window are returned).
        grep: Optional pattern to filter log lines (case-insensitive).
        since_seconds: Only return log lines written in the last N seconds.
            Translates to `docker logs --since Ns`. When set, this supersedes
            tail as the primary filter — use it to avoid stale historical
            lines. Prefer this for time-bounded investigations.

    Returns:
        The log output as a string. Error message if container not found.
    """
    if container not in deps.all_containers:
        return f"Unknown container '{container}'. Known containers: {', '.join(deps.all_containers)}"

    # Build docker logs command. --since and --tail can coexist: --since
    # filters by time first, then --tail limits the tail of that window.
    if since_seconds is not None and since_seconds > 0:
        cmd = f"docker logs --since {int(since_seconds)}s --tail {tail} {container} 2>&1"
    else:
        cmd = f"docker logs --tail {tail} {container} 2>&1"

    if grep:
        cmd += f" | grep -i -- {_shell_quote(grep)}"

    rc, output = await _shell(cmd)
    if rc != 0 and "No such container" in output:
        return f"Container '{container}' not found (not running or does not exist)."

    return _truncate(output.strip()) or "(no log output)"


# ---------------------------------------------------------------------------
# Tool 2: read_config
# ---------------------------------------------------------------------------

async def read_config(
    deps: AgentDeps,
    component: str,
) -> str:
    """Read the configuration file for a network component.

    Args:
        deps: Agent dependencies.
        component: One of: amf, smf, upf, pcscf, scscf, icscf, pyhss,
                   dns, dns-ims-zone, ueransim-gnb, ueransim-ue.

    Returns:
        The full configuration file content, or an error message.
    """
    rel_path = _CONFIG_PATHS.get(component)
    if rel_path is None:
        return f"Unknown component '{component}'. Valid components: {', '.join(sorted(_CONFIG_PATHS.keys()))}"

    config_path = deps.repo_root / rel_path
    if not config_path.exists():
        return f"Config file not found: {config_path}"

    return config_path.read_text(errors="replace")


# ---------------------------------------------------------------------------
# Tool 3: get_network_status
# ---------------------------------------------------------------------------

async def get_network_status(
    deps: AgentDeps,
) -> str:
    """Get the status of all network containers.

    Args:
        deps: Agent dependencies.

    Returns:
        JSON string with phase and per-container status.
    """
    tasks = {}
    for name in deps.all_containers:
        tasks[name] = asyncio.create_task(_container_status(name))

    results = {}
    for name, task in tasks.items():
        results[name] = await task

    running = [n for n, s in results.items() if s == "running"]
    down = [n for n, s in results.items() if s != "running"]

    core = {"mongo", "nrf", "scp", "ausf", "udr", "udm", "amf", "smf", "upf",
            "pcf", "dns", "mysql", "pyhss", "icscf", "scscf", "pcscf", "rtpengine"}
    core_up = core.issubset(set(running))

    if core_up:
        phase = "ready"
    else:
        phase = "down"

    summary = {
        "phase": phase,
        "running": running,
        "down_or_absent": down,
        "containers": results,
    }
    return json.dumps(summary, indent=2)


async def _container_status(name: str) -> str:
    rc, output = await _shell(f"docker inspect -f '{{{{.State.Status}}}}' {name}")
    if rc != 0:
        return "absent"
    return output.strip()


# ---------------------------------------------------------------------------
# Tool 4: query_subscriber
# ---------------------------------------------------------------------------

async def query_subscriber(
    deps: AgentDeps,
    imsi: str,
    domain: str = "both",
) -> str:
    """Query subscriber data from 5G core (MongoDB) and/or IMS (PyHSS).

    Args:
        deps: Agent dependencies.
        imsi: The subscriber's IMSI (e.g. '001011234567891').
        domain: 'core' for 5G only, 'ims' for IMS only, 'both' for both.

    Returns:
        JSON string with subscriber profiles from the requested domains.
    """
    result: dict = {}

    if domain in ("core", "both"):
        mongo_cmd = (
            f"docker exec -i mongo mongosh --quiet open5gs --eval "
            f"\"JSON.stringify(db.subscribers.findOne({{imsi: '{imsi}'}}))\""
        )
        rc, output = await _shell(mongo_cmd)
        if rc == 0 and output.strip() and output.strip() != "null":
            try:
                result["core_5g"] = json.loads(output.strip())
            except json.JSONDecodeError:
                result["core_5g"] = output.strip()
        else:
            result["core_5g"] = None
            result["core_5g_note"] = f"Subscriber {imsi} NOT FOUND in Open5GS MongoDB. This means the UE cannot attach to the 5G core."

    if domain in ("ims", "both"):
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                # PyHSS subscriber
                resp = await client.get(f"{deps.pyhss_api}/subscriber/imsi/{imsi}")
                if resp.status_code == 200:
                    result["ims_subscriber"] = resp.json()
                else:
                    result["ims_subscriber"] = None
                    result["ims_note"] = f"Subscriber {imsi} NOT FOUND in PyHSS. This means the UE cannot register with IMS for voice calls."

                # IMS subscriber details
                resp2 = await client.get(f"{deps.pyhss_api}/ims_subscriber/ims_subscriber_imsi/{imsi}")
                if resp2.status_code == 200:
                    result["ims_details"] = resp2.json()
        except httpx.ConnectError:
            result["ims_error"] = f"Cannot connect to PyHSS API at {deps.pyhss_api}. Is the pyhss container running?"
        except httpx.TimeoutException:
            result["ims_error"] = f"PyHSS API timeout at {deps.pyhss_api}."

    return json.dumps(result, indent=2, default=str)


# ---------------------------------------------------------------------------
# Tool 5: read_env_config
# ---------------------------------------------------------------------------

async def read_env_config(
    deps: AgentDeps,
) -> str:
    """Read network topology and UE credentials from environment files.

    Args:
        deps: Agent dependencies.

    Returns:
        JSON string with network topology, UE info, and IMS domain.
    """
    env = deps.env
    mcc = env.get("MCC", "001")
    mnc = env.get("MNC", "01")
    if len(mnc) == 3:
        ims_domain = f"ims.mnc{mnc}.mcc{mcc}.3gppnetwork.org"
    else:
        ims_domain = f"ims.mnc0{mnc}.mcc{mcc}.3gppnetwork.org"

    # Extract key IPs
    network = {
        "mcc": mcc,
        "mnc": mnc,
        "ims_domain": ims_domain,
        "test_network": env.get("TEST_NETWORK", "172.22.0.0/24"),
    }
    # Collect all *_IP variables
    for key, val in sorted(env.items()):
        if key.endswith("_IP"):
            network[key.lower()] = val

    ue1 = {
        "imsi": env.get("UE1_IMSI", ""),
        "msisdn": env.get("UE1_MSISDN", ""),
        "ip": env.get("UE1_IP", ""),
    }
    ue2 = {
        "imsi": env.get("UE2_IMSI", ""),
        "msisdn": env.get("UE2_MSISDN", ""),
        "ip": env.get("UE2_IP", ""),
    }

    result = {
        "network": network,
        "ue1": ue1,
        "ue2": ue2,
        "ims_domain": ims_domain,
    }
    return json.dumps(result, indent=2)


# ---------------------------------------------------------------------------
# Tool 6: search_logs
# ---------------------------------------------------------------------------

async def search_logs(
    deps: AgentDeps,
    pattern: str,
    containers: list[str] | None = None,
    since: str | None = None,
) -> str:
    """Search for a pattern across multiple container logs.

    Unlike read_container_logs which reads the tail of one container,
    this tool searches across all (or specified) containers for a
    specific pattern. Essential for tracing a SIP Call-ID, IMSI, or
    error keyword across the entire stack.

    Args:
        deps: Agent dependencies.
        pattern: Search pattern (case-insensitive). Can be a Call-ID,
                 IMSI, SIP method, error keyword, etc.
        containers: Optional list of containers to search. If None,
                    searches all known containers.
        since: Optional time filter for docker logs (e.g. '5m', '1h').

    Returns:
        Matching lines grouped by container, with container name prefix.
    """
    targets = containers or deps.all_containers

    # Validate container names
    invalid = [c for c in targets if c not in deps.all_containers]
    if invalid:
        return f"Unknown containers: {', '.join(invalid)}. Known: {', '.join(deps.all_containers)}"

    # Search in parallel
    async def _search_one(container: str) -> tuple[str, str]:
        since_flag = f"--since {since}" if since else ""
        cmd = f"docker logs {since_flag} {container} 2>&1 | grep -i -- {_shell_quote(pattern)}"
        rc, output = await _shell(cmd)
        lines = output.strip()
        if not lines:
            return container, ""
        # Prefix each line with container name
        prefixed = "\n".join(f"[{container}] {line}" for line in lines.splitlines())
        return container, prefixed

    tasks = [_search_one(c) for c in targets]
    results = await asyncio.gather(*tasks)

    all_matches = []
    for container, output in results:
        if output:
            all_matches.append(output)

    if not all_matches:
        searched = ", ".join(targets)
        return f"No matches for '{pattern}' in containers: {searched}"

    combined = "\n".join(all_matches)
    return _truncate(combined)


# ---------------------------------------------------------------------------
# Tool 7: query_prometheus
# ---------------------------------------------------------------------------

async def query_prometheus(
    deps: AgentDeps,
    query: str,
    window_seconds: int | None = None,
) -> str:
    """Query Prometheus for 5G core NF metrics using PromQL.

    **Call this EARLY in every investigation.** Prometheus metrics are the fastest
    way to triage — a 3-second query replaces 30 minutes of log analysis.
    Metrics tell you WHAT is broken. Logs tell you WHY. Start with WHAT.

    The stack scrapes metrics from AMF, SMF, UPF, PCF every 5 seconds.

    Args:
        deps: Agent dependencies.
        window_seconds: Optional lookback window in seconds for rate/range
            queries. When set, the tool substitutes the placeholder token
            `{window}` in your query with `{window_seconds}s`. Example:
            `rate(rtpengine_packets_total[{window}])` with window_seconds=120
            becomes `rate(rtpengine_packets_total[120s])`. If the query
            already contains an explicit range selector (e.g. `[60s]`) the
            window_seconds value is ignored.
        query: A PromQL query string. Common queries:

            Data plane health (check FIRST for call/connectivity issues):
              fivegs_ep_n3_gtp_indatapktn3upf — GTP incoming packets at UPF (0 = data plane dead)
              fivegs_ep_n3_gtp_outdatapktn3upf — GTP outgoing packets at UPF

            Session counts:
              fivegs_upffunction_upf_sessionnbr — UPF active sessions
              fivegs_smffunction_sm_sessionnbr — SMF active sessions

            UE/gNB counts:
              ran_ue — RAN-connected UEs at AMF
              gnb — connected gNBs at AMF
              amf_session — AMF session count

            Registration stats:
              fivegs_amffunction_rm_reginitreq — 5G NAS initial registration requests
              fivegs_amffunction_rm_reginitsucc — 5G NAS initial registration successes
              fivegs_amffunction_amf_authreq — authentication requests
              fivegs_amffunction_amf_authfail — authentication failures

            PDU session stats:
              fivegs_smffunction_sm_pdusessioncreationreq — PDU session requests
              fivegs_smffunction_sm_pdusessioncreationsucc — PDU session successes

            PCF policy sessions:
              fivegs_pcffunction_pa_sessionnbr — PCF policy sessions

    Returns:
        Query result as formatted text showing metric name, labels, and value.
        Returns error message if Prometheus is unreachable.
    """
    prom_ip = deps.env.get("METRICS_IP", "172.22.0.36")
    prom_url = f"http://{prom_ip}:9090"

    # Substitute {window} placeholder in query with the window_seconds value
    if window_seconds is not None and "{window}" in query:
        query = query.replace("{window}", f"{int(window_seconds)}s")

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{prom_url}/api/v1/query",
                params={"query": query},
            )
            if resp.status_code != 200:
                return f"Prometheus returned HTTP {resp.status_code}: {resp.text[:200]}"

            body = resp.json()
            status = body.get("status", "")
            if status != "success":
                return f"Prometheus query failed: {body.get('error', 'unknown error')}"

            results = body.get("data", {}).get("result", [])
            if not results:
                return f"No results for query '{query}'. The metric may not exist or have no data."

            # Format results as readable text
            lines = []
            for r in results:
                metric = r.get("metric", {})
                value = r.get("value", [None, None])
                metric_name = metric.get("__name__", query)
                labels = {k: v for k, v in metric.items() if k != "__name__"}
                label_str = ", ".join(f"{k}={v}" for k, v in labels.items())
                val = value[1] if len(value) > 1 else "?"
                if label_str:
                    lines.append(f"{metric_name}{{{label_str}}} = {val}")
                else:
                    lines.append(f"{metric_name} = {val}")

            return "\n".join(lines)

    except httpx.ConnectError:
        return f"Cannot connect to Prometheus at {prom_url}. Is the metrics container running?"
    except httpx.TimeoutException:
        return f"Prometheus query timed out at {prom_url}."
    except Exception as e:
        return f"Prometheus query error: {e}"


# ---------------------------------------------------------------------------
# Tool 8: get_nf_metrics
# ---------------------------------------------------------------------------

async def get_nf_metrics(
    deps: AgentDeps,
) -> str:
    """Get a full metrics snapshot across ALL network functions in one call.

    Collects metrics from:
      - Prometheus (AMF, SMF, UPF, PCF) — 5G core KPIs
      - Kamailio kamcmd (P-CSCF, I-CSCF, S-CSCF) — IMS stats
      - RTPEngine rtpengine-ctl — media relay stats
      - PyHSS REST API — IMS subscriber count
      - MongoDB — 5G subscriber count

    This is the "radiograph" — a quick health overview of the entire stack.
    Use this BEFORE diving into logs. If a metric is zero when it should be
    nonzero (e.g., GTP packets = 0 but sessions > 0), that's an anomaly
    worth investigating.

    Returns:
        JSON object with per-NF metrics, badges, and data sources.
        Each NF entry has: {metrics: {key: value}, badge: "summary", source: "prometheus|kamcmd|api"}
    """
    import sys
    gui_dir = str(deps.repo_root / "gui")
    if gui_dir not in sys.path:
        sys.path.insert(0, gui_dir)

    try:
        from metrics import MetricsCollector
        env = deps.env
        collector = MetricsCollector(env)
        collector._cache_ts = 0.0  # Force fresh collection
        data = await asyncio.wait_for(collector.collect(), timeout=15)

        if not data:
            return "No metrics collected. Prometheus and/or containers may be down."

        # Format as readable text
        lines = []
        for nf, info in sorted(data.items()):
            badge = info.get("badge", "")
            source = info.get("source", "?")
            metrics = info.get("metrics", {})
            badge_str = f" [{badge}]" if badge else ""
            lines.append(f"\n{nf.upper()}{badge_str} (via {source}):")
            for k, v in sorted(metrics.items()):
                if k.startswith("_"):
                    continue
                lines.append(f"  {k} = {v}")

        return "\n".join(lines)

    except asyncio.TimeoutError:
        return "Metrics collection timed out (15s). Some NFs may be unreachable."
    except ImportError as e:
        return f"Cannot import MetricsCollector: {e}"
    except Exception as e:
        return f"Metrics collection error: {e}"


# ---------------------------------------------------------------------------
# Tool 9: run_kamcmd (renumbered from 7)
# ---------------------------------------------------------------------------

async def run_kamcmd(
    deps: AgentDeps,
    container: str,
    command: str,
) -> str:
    """Run a kamcmd command inside a Kamailio container (pcscf, icscf, scscf).

    This provides access to Kamailio's internal runtime state that is NOT
    visible in logs or config files: Diameter peer status, usrloc registered
    contacts, transaction stats, shared memory usage, dialog state, etc.

    Args:
        deps: Agent dependencies.
        container: Kamailio container name ('pcscf', 'icscf', or 'scscf').
        command: kamcmd command string. Common commands:
            - cdp.list_peers — Diameter peer connections and state
            - ulscscf.showimpu <sip:imsi@domain> — S-CSCF registration lookup
            - stats.get_statistics all — all Kamailio stats
            - tm.stats — SIP transaction statistics
            - dlg.list — active SIP dialogs

    Returns:
        Command output as string, or error message.
    """
    valid_containers = {"pcscf", "icscf", "scscf"}
    if container not in valid_containers:
        return f"Container must be one of {valid_containers}, got '{container}'"

    if container not in deps.all_containers:
        return f"Container '{container}' not in known containers list"

    cmd = f"docker exec {container} kamcmd {command}"
    rc, output = await _shell(cmd)

    if rc != 0 and "not found" in output:
        return f"kamcmd command '{command}' not found. Try: cdp.list_peers, stats.get_statistics all, tm.stats"

    result = _truncate(output.strip()) or "(no output)"

    # Annotate I_Open Diameter peer state — this is a known cosmetic artifact
    # of the PyHSS/Kamailio interop in this stack, not a real failure.
    if "cdp" in command and "I_Open" in result:
        result += (
            "\n\n--- NOTE ---\n"
            "I_Open is a KNOWN BENIGN display artifact in this stack. "
            "Kamailio's CDP module shows I_Open for PyHSS peers even when "
            "the Diameter connection is fully functional. This has been "
            "verified: PyHSS processes 242+ Diameter messages/hour on these "
            "connections, and UE registration (UAR/UAA, MAR/SAR) succeeds. "
            "Do NOT treat I_Open as a root cause. To verify the connection "
            "is working, check PyHSS logs for recent Diameter message processing."
        )

    return result


# ---------------------------------------------------------------------------
# Tool 8: read_running_config
# ---------------------------------------------------------------------------

async def read_running_config(
    deps: AgentDeps,
    container: str,
    grep: str | None = None,
) -> str:
    """Read the ACTUAL configuration from a running container (not the repo copy).

    This reads the config that the process is currently using, which may differ
    from the repo version if the container was restarted from a volume mount
    or if runtime changes were applied.

    Use this when you need to verify what config a container is ACTUALLY running
    with, especially for settings like udp_mtu_try_proto, auth algorithms, etc.

    Args:
        deps: Agent dependencies.
        container: Container name.
        grep: Optional pattern to filter config lines (case-insensitive).

    Returns:
        Config content (or filtered lines), or error message.
    """
    # Map containers to their config file paths inside the container
    config_paths = {
        "pcscf": "/etc/kamailio_pcscf/kamailio_pcscf.cfg",
        "icscf": "/etc/kamailio_icscf/kamailio_icscf.cfg",
        "scscf": "/etc/kamailio_scscf/kamailio_scscf.cfg",
        "amf": "/open5gs/install/etc/open5gs/amf.yaml",
        "smf": "/open5gs/install/etc/open5gs/smf.yaml",
        "upf": "/open5gs/install/etc/open5gs/upf.yaml",
    }

    config_path = config_paths.get(container)
    if not config_path:
        return f"No known config path for container '{container}'. Known: {', '.join(sorted(config_paths.keys()))}"

    if grep:
        cmd = f"docker exec {container} grep -in -- {_shell_quote(grep)} {config_path}"
    else:
        cmd = f"docker exec {container} cat {config_path}"

    rc, output = await _shell(cmd)
    if rc != 0:
        return f"Failed to read config from {container}:{config_path} — {output.strip()}"

    return _truncate(output.strip()) or "(empty config or no matches)"


# ---------------------------------------------------------------------------
# Tool 9: check_process_listeners
# ---------------------------------------------------------------------------

async def check_process_listeners(
    deps: AgentDeps,
    container: str,
) -> str:
    """Check what network ports and protocols a container's processes are listening on.

    Shows UDP and TCP listeners. Essential for diagnosing transport mismatches
    — e.g., when a SIP proxy sends via TCP but the UE only listens on UDP.

    Args:
        deps: Agent dependencies.
        container: Container name.

    Returns:
        Output of ss -tulnp showing all listeners, or error message.
    """
    if container not in deps.all_containers:
        return f"Unknown container '{container}'. Known: {', '.join(deps.all_containers)}"

    # Toolbelt preflight — try ss first, fall back to netstat. If neither
    # is present we surface PROBE_TOOL_UNAVAILABLE so the Investigator
    # records ProbeResult.outcome='tool_unavailable' rather than reading
    # an empty result as soft non-evidence.
    has_ss = await _container_has_binary(container, "ss")
    if has_ss:
        cmd = f"docker exec {container} ss -tulnp"
    else:
        if not await _container_has_binary(container, "netstat"):
            return _tool_unavailable(container, "ss/netstat", "check_process_listeners")
        cmd = f"docker exec {container} netstat -tulnp"

    rc, output = await _shell(cmd)
    if rc != 0:
        return f"Listener check failed on {container}: {output.strip()}"

    return output.strip() or "(no listeners found)"


# ---------------------------------------------------------------------------
# Tool 10: check_tc_rules
# ---------------------------------------------------------------------------

async def check_tc_rules(
    deps: AgentDeps,
    container: str,
) -> str:
    """Check for active traffic control (tc) rules on a container's network interface.

    This detects injected network faults: latency (netem delay), packet loss
    (netem loss), bandwidth limits (tbf), or corruption (netem corrupt).

    **CRITICAL: Call this FIRST on any container showing timeouts or slow
    responses.** A tc netem rule is the #1 cause of latency-induced timeouts
    in this environment. If tc rules are present, they are almost certainly
    the root cause — do not investigate application-layer issues until you
    have ruled out tc rules.

    In a healthy Docker network, RTT between containers is <1ms. If you see
    netem delay rules, that explains any timeout behavior.

    Args:
        deps: Agent dependencies.
        container: Container name (e.g. 'pcscf', 'upf', 'scscf').

    Returns:
        tc qdisc output showing active rules. "noqueue" or "fq_codel" means
        no artificial rules are present. "netem" or "tbf" means a fault is
        active.
    """
    if container not in deps.all_containers:
        return f"Unknown container '{container}'. Known: {', '.join(deps.all_containers)}"

    # Get the container's PID to enter its network namespace
    rc, pid_out = await _shell(f"docker inspect -f '{{{{.State.Pid}}}}' {container}")
    pid = pid_out.strip()
    if rc != 0 or not pid or pid == "0":
        return f"Cannot get PID for container '{container}' — is it running? (status: {pid_out.strip()})"

    cmd = f"sudo nsenter -t {pid} -n tc qdisc show dev eth0"
    rc, output = await _shell(cmd)

    if rc != 0:
        return f"Failed to check tc rules on {container}: {output.strip()}"

    result = output.strip()
    if not result:
        return f"No tc rules found on {container} (interface may not exist)."

    # Annotate the result for the LLM
    if "netem" in result:
        result += "\n\n⚠ NETEM RULES DETECTED — this container has artificial network faults (latency/loss/corruption) injected."
    elif "tbf" in result:
        result += "\n\n⚠ TBF RULES DETECTED — this container has artificial bandwidth limits."
    else:
        result += "\n\n✓ No artificial network faults detected on this container."

    return result


# ---------------------------------------------------------------------------
# Tool 11: measure_rtt
# ---------------------------------------------------------------------------

def measure_rtt_sample_size(loss_threshold: float) -> int:
    """Sample size that detects loss >= `loss_threshold` with false-negative
    probability <= 0.001.

    Derivation: P(no drops in N samples | true loss = p) = (1-p)^N. Solving
    (1-p)^N <= 0.001 for N gives N >= log(0.001) / log(1-p). We ceil to the
    next integer.

    Examples (rounded):
        threshold 0.30 -> N = 20  (~2 s at -i 0.1)
        threshold 0.10 -> N = 66  (~7 s)
        threshold 0.01 -> N = 688 (~69 s)

    The 3-ping default of the previous implementation had a 34% false-
    negative rate against a 30% loss fault — coin-flip — and was the
    immediate cause of the 2026-05-06 rtpengine mis-diagnosis. See ADR
    `path_anchored_probe_planning_for_transport_layer_faults.md`.

    Raises ValueError if threshold is outside (0, 1).
    """
    import math
    if not (0.0 < loss_threshold < 1.0):
        raise ValueError(
            f"loss_threshold must be in (0, 1); got {loss_threshold!r}"
        )
    return math.ceil(math.log(0.001) / math.log(1.0 - loss_threshold))


async def measure_rtt(
    deps: AgentDeps,
    container: str,
    target: str | None = None,
    loss_threshold: float = 0.10,
    *,
    target_ip: str | None = None,
) -> str:
    """Measure round-trip time and packet loss from a container to a peer container.

    In a healthy Docker bridge network, RTT between any two containers is
    <1ms. Elevated RTT (>10ms) indicates abnormal latency or congestion;
    non-zero packet loss indicates transport-layer degradation.

    Both arguments are **container names**, not IP addresses. The peer
    is resolved via the docker network's embedded DNS (`127.0.0.11`),
    which works regardless of any application-level DNS state. Per
    ADR `agent_tool_args_must_be_names_not_ips.md`, no agent-facing
    tool argument accepts an IP literal — the LLM has no reliable
    mechanism to know which IP belongs to which container, and prior
    failure analysis showed it would hallucinate IPs from training-data
    priors when forced to type one.

    Sample size is **derived from `loss_threshold`** so the probe is
    statistically capable of detecting the loss rate it claims to test for:

        loss_threshold=0.30 -> 20 packets   (~2 s)   detects >=30% loss reliably
        loss_threshold=0.10 -> 66 packets   (~7 s)   detects >=10% loss reliably (default)
        loss_threshold=0.01 -> 688 packets  (~69 s)  detects >=1%  loss reliably

    The previous `-c 3` default is gone — it was statistically incapable of
    detecting a 30% loss fault (false-negative rate 34%). See ADR
    `path_anchored_probe_planning_for_transport_layer_faults.md`.

    For exact, sample-size-free localization of kernel-level qdisc drops on
    a known path, prefer the path-walk probes (`get_qdisc_drops`,
    `get_interface_drops`) over `measure_rtt`. `measure_rtt` is the right
    tool when the question is "is this end-to-end path lossy at >= X%."

    Args:
        deps: Agent dependencies.
        container: Source container name (e.g. 'pcscf', 'icscf').
        target: Target container name (e.g. 'pyhss', 'rtpengine'). MUST be
            a name registered in the deployment topology. IP literals are
            rejected with a corrective error message.
        loss_threshold: Detection-threshold for loss. Sample size is set so
            the probe almost-never (P <= 0.001) misses a true loss rate at
            or above this threshold. Default 0.10.
        target_ip: **Deprecated.** Kept temporarily as a keyword-only
            alias so legacy v1.5/v2 wrappers continue to work. Pass
            `target=` instead; passing an IP literal (e.g. '172.22.0.19')
            via either argument is rejected.

    Returns:
        Ping output with RTT statistics + per-N loss summary, or an error
        message identifying what went wrong (unknown container, IP
        literal supplied, ping binary missing, etc.).
    """
    if container not in deps.all_containers:
        return (
            f"Unknown source container '{container}'. "
            f"Known: {', '.join(deps.all_containers)}"
        )

    # Reconcile the new `target` parameter with the deprecated
    # `target_ip` alias. New callers should pass `target=`; old callers
    # passing `target_ip=` get a single deprecation log + their request
    # honored. Passing both is treated as a programming error.
    if target is None and target_ip is not None:
        target = target_ip
    elif target is not None and target_ip is not None and target != target_ip:
        return (
            "Conflicting `target` and `target_ip` arguments supplied. "
            "Pass only `target=` (a container name)."
        )
    if not target:
        return (
            "Missing `target` argument. Pass `target=<container_name>` "
            "(e.g. target='pyhss'). IP literals are not accepted — see "
            "ADR agent_tool_args_must_be_names_not_ips.md."
        )

    # Mechanical IP-shape rejection. Catches the failure mode observed in
    # run_20260512_082224_hss_unresponsive (RAG-ON HSS-Unresponsive case),
    # where the Investigator hallucinated `172.22.0.8` as pyhss's IP and
    # consequently pinged nr_gnb. The corrective error names the
    # principle the LLM is violating and tells it what shape the
    # argument should have.
    if _looks_like_ip(target):
        return (
            f"target={target!r} looks like an IP literal. Pass a container "
            f"NAME instead (e.g. target='pyhss'). Container names are "
            f"resolved to IPs by the docker network's embedded DNS at "
            f"probe time. If you don't know which container owns this "
            f"IP, infer it from a previous tool output rather than "
            f"guessing. (ADR: agent_tool_args_must_be_names_not_ips.md)"
        )

    if target not in deps.all_containers:
        return (
            f"Unknown target container '{target}'. "
            f"Known: {', '.join(deps.all_containers)}"
        )

    # Toolbelt preflight — distinguish "ping isn't installed" (no
    # signal) from "ping ran and saw 100% loss" (strong contradicting
    # signal). Without this, both paths land on the same generic
    # failure string and the Investigator silently chains on a probe
    # that didn't run.
    if not await _container_has_binary(container, "ping"):
        return _tool_unavailable(container, "ping", "measure_rtt")

    n = measure_rtt_sample_size(loss_threshold)
    # -i 0.1 (100ms inter-packet interval) keeps wall-time bounded;
    # -W 1 (1s per-packet wait) keeps probes responsive even when
    # part of the path is dropping. The peer is named, not IP'd; the
    # kernel ping uses the container's `/etc/resolv.conf` (which docker
    # writes to point at 127.0.0.11, the embedded compose-network DNS).
    cmd = f"docker exec {container} ping -c {n} -i 0.1 -W 1 {target}"
    rc, output = await _shell(cmd)

    if rc != 0 and "100% packet loss" in output:
        return (
            f"Target '{target}' is UNREACHABLE from '{container}' "
            f"(0/{n} packets received):\n{output.strip()}"
        )
    if rc != 0:
        return f"Ping failed from '{container}' to '{target}': {output.strip()}"

    return (
        f"[loss_threshold={loss_threshold}, sample_size={n}]\n"
        f"{output.strip()}"
    )


def _looks_like_ip(value: str) -> bool:
    """Return True iff `value` matches an IPv4 dotted-quad shape.

    Used by `measure_rtt` to reject IP literals at the agent boundary.
    Intentionally permissive on octet validation (any 1-3 digit groups
    separated by dots) — we want to catch hallucinated "near-IPs" like
    `172.22.0.99` even if the network doesn't actually have a host
    there. False positives on real container names are not a concern;
    no legitimate container name contains four dot-separated digit
    groups.
    """
    parts = value.split(".")
    if len(parts) != 4:
        return False
    for part in parts:
        if not (1 <= len(part) <= 3) or not part.isdigit():
            return False
    return True


# ---------------------------------------------------------------------------
# Path-walk probe wrappers
#
# Per ADR `path_anchored_probe_planning_for_transport_layer_faults.md`,
# these wrappers extract structured drop / error / rate counters from
# kernel and bridge telemetry. Probers in
# `agentic_ops_common/path_walk/probers/*` use them; v7's PathWalkInvestigator
# composes prober output into a PathWalkReport.
#
# Returns are typed dicts (Python's TypedDict not used to avoid a hard
# typing-extensions floor; consumers treat the result shape as documented).
# Failure modes:
#   - tool_unavailable: dict with key "_error" == "tool_unavailable" and
#     "missing_binary" naming the binary; mirrors PROBE_TOOL_UNAVAILABLE
#     semantics so probers can map cleanly to InconclusiveHop.
#   - other failures: dict with "_error" carrying the message.
# ---------------------------------------------------------------------------

import re as _re


async def get_qdisc_drops(container: str, iface: str = "eth0") -> dict:
    """Read per-qdisc drop counters at a container's interface.

    Wraps `tc -s qdisc show dev <iface>` inside the container's network
    namespace. Returns a structured dict with the qdisc kind, packets
    sent, packets dropped, and drop fraction.

    For tc netem `loss N%` faults this is the source of truth — the
    kernel's exact counter, no statistical sampling required.

    Returns dict with keys:
        qdisc_kind:   "netem" | "tbf" | "fq_codel" | "noqueue" | ...
        sent_pkts:    int
        dropped_pkts: int
        dropped_pct:  float | None  (None when sent_pkts == 0)
        loss_pct:     float | None  (the netem `loss N%` parameter, if authored)
        delay_ms:     float | None  (the netem `delay Nms` parameter, if authored)
        raw:          str  (full tc -s output)
        _error:       str  (when probe could not run; absent on success)
    """
    if not await _container_has_binary(container, "tc"):
        return {
            "_error": "tool_unavailable",
            "missing_binary": "tc",
            "container": container,
        }

    cmd = f"docker exec {container} tc -s qdisc show dev {iface}"
    rc, output = await _shell(cmd)
    if rc != 0:
        return {
            "_error": f"tc qdisc show failed (rc={rc}): {output.strip()}",
            "container": container,
            "iface": iface,
            "raw": output,
        }

    raw = output.strip()
    qdisc_kind = _parse_qdisc_kind(raw)
    sent_pkts, dropped_pkts = _parse_qdisc_pkt_counters(raw)
    dropped_pct = (dropped_pkts / sent_pkts) if sent_pkts > 0 else None
    loss_pct = _parse_netem_loss_pct(raw)
    delay_ms = _parse_netem_delay_ms(raw)

    return {
        "qdisc_kind": qdisc_kind,
        "sent_pkts": sent_pkts,
        "dropped_pkts": dropped_pkts,
        "dropped_pct": dropped_pct,
        "loss_pct": loss_pct,
        "delay_ms": delay_ms,
        "raw": raw,
    }


def _parse_qdisc_kind(raw: str) -> str:
    """Identify the root qdisc kind from `tc -s qdisc show` output.

    Output line shape: `qdisc <kind> <handle>: root <opts>...`. We pick
    the first matching qdisc declaration; deep-tree qdiscs are a follow-up.
    """
    m = _re.search(r"^qdisc\s+(\S+)\s+", raw, _re.MULTILINE)
    return m.group(1) if m else "unknown"


def _parse_qdisc_pkt_counters(raw: str) -> tuple[int, int]:
    """Parse `Sent N bytes M pkt (dropped K, ...)` from tc -s output.

    Returns (sent_pkts, dropped_pkts). Returns (0, 0) if the line isn't
    found.
    """
    m = _re.search(
        r"Sent\s+\d+\s+bytes\s+(\d+)\s+pkt\s+\(dropped\s+(\d+),", raw
    )
    if m:
        return int(m.group(1)), int(m.group(2))
    return 0, 0


def _parse_netem_loss_pct(raw: str) -> float | None:
    """Extract the authored `loss N%` parameter from a netem qdisc, if any."""
    m = _re.search(r"loss\s+([\d.]+)%", raw)
    return float(m.group(1)) / 100.0 if m else None


def _parse_netem_delay_ms(raw: str) -> float | None:
    """Extract the authored `delay Nms` parameter from a netem qdisc, if any."""
    m = _re.search(r"delay\s+([\d.]+)\s*ms", raw)
    return float(m.group(1)) if m else None


async def get_interface_drops(container: str, iface: str = "eth0") -> dict:
    """Read interface-level RX/TX counters at a container's interface.

    Wraps `ip -s link show dev <iface>`. Catches drops not tied to a
    qdisc (ring-buffer overrun, NIC errors).

    Returns dict with keys:
        rx_pkts, rx_bytes, rx_errors, rx_dropped:  int
        tx_pkts, tx_bytes, tx_errors, tx_dropped:  int
        raw: str
        _error: str  (when probe could not run; absent on success)
    """
    if not await _container_has_binary(container, "ip"):
        return {
            "_error": "tool_unavailable",
            "missing_binary": "ip",
            "container": container,
        }

    cmd = f"docker exec {container} ip -s link show dev {iface}"
    rc, output = await _shell(cmd)
    if rc != 0:
        return {
            "_error": f"ip link show failed (rc={rc}): {output.strip()}",
            "container": container,
            "iface": iface,
            "raw": output,
        }

    raw = output.strip()
    rx = _parse_ip_link_stats_block(raw, "RX")
    tx = _parse_ip_link_stats_block(raw, "TX")
    return {
        "rx_bytes":   rx[0],
        "rx_pkts":    rx[1],
        "rx_errors":  rx[2],
        "rx_dropped": rx[3],
        "tx_bytes":   tx[0],
        "tx_pkts":    tx[1],
        "tx_errors":  tx[2],
        "tx_dropped": tx[3],
        "raw": raw,
    }


def _parse_ip_link_stats_block(raw: str, direction: str) -> tuple[int, int, int, int]:
    """Parse a `RX:` or `TX:` block from `ip -s link show` output.

    `ip -s link show` prints:
        RX:  bytes packets errors dropped overrun mcast
             12345 678     0      0       0       0
        TX:  bytes packets errors dropped carrier collsns
             67890 123     0      0       0       0

    We return (bytes, packets, errors, dropped). Order is determined by
    the header on systems where iproute2 changed column ordering, but
    the four columns we care about are reliably the first four numbers.
    Returns (0, 0, 0, 0) if the block isn't found.
    """
    m = _re.search(
        rf"{direction}:.*?\n\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)",
        raw,
        _re.DOTALL,
    )
    if m:
        return (int(m.group(1)), int(m.group(2)),
                int(m.group(3)), int(m.group(4)))
    return 0, 0, 0, 0


async def get_link_rate_diff(
    container_a: str,
    iface_a: str,
    container_b: str,
    iface_b: str,
    direction: str = "a_to_b",
    window_seconds: int = 5,
) -> dict:
    """Compare same-direction packet rates at two adjacent hops.

    For an A->B direction, we sample TX(A, iface_a) and RX(B, iface_b)
    over `window_seconds`, compute per-second rates, and report the
    difference. A meaningful TX > RX delta attributes loss to the link
    between A and B.

    The implementation takes two interface-counter snapshots
    `window_seconds` apart and computes the delta — same shape as the
    preprocessor's rate windows elsewhere in this codebase.

    Returns dict with keys:
        direction:           "a_to_b" | "b_to_a"
        window_seconds:      int
        tx_rate_pkts_per_s:  float
        rx_rate_pkts_per_s:  float
        diff_pkts_per_s:     float  (tx_rate - rx_rate)
        attributed_loss_pct: float | None  (diff / tx_rate, when tx_rate > 0)
        evidence:            str  (verbatim two-snapshot comparison)
        _error:              str  (when probe could not run; absent on success)
    """
    if direction not in ("a_to_b", "b_to_a"):
        return {"_error": f"invalid direction {direction!r}; expected 'a_to_b' or 'b_to_a'"}

    # Sample t0
    a0 = await get_interface_drops(container_a, iface_a)
    b0 = await get_interface_drops(container_b, iface_b)
    if "_error" in a0:
        return {"_error": f"hop A unreachable: {a0['_error']}", "side": "a", "underlying": a0}
    if "_error" in b0:
        return {"_error": f"hop B unreachable: {b0['_error']}", "side": "b", "underlying": b0}

    import asyncio as _asyncio
    await _asyncio.sleep(window_seconds)

    # Sample t1
    a1 = await get_interface_drops(container_a, iface_a)
    b1 = await get_interface_drops(container_b, iface_b)
    if "_error" in a1 or "_error" in b1:
        return {
            "_error": "second-snapshot read failed",
            "a1_error": a1.get("_error"),
            "b1_error": b1.get("_error"),
        }

    if direction == "a_to_b":
        tx_delta = a1["tx_pkts"] - a0["tx_pkts"]
        rx_delta = b1["rx_pkts"] - b0["rx_pkts"]
        tx_label = f"{container_a}[{iface_a}].tx_pkts"
        rx_label = f"{container_b}[{iface_b}].rx_pkts"
    else:
        tx_delta = b1["tx_pkts"] - b0["tx_pkts"]
        rx_delta = a1["rx_pkts"] - a0["rx_pkts"]
        tx_label = f"{container_b}[{iface_b}].tx_pkts"
        rx_label = f"{container_a}[{iface_a}].rx_pkts"

    tx_rate = tx_delta / window_seconds if window_seconds > 0 else 0.0
    rx_rate = rx_delta / window_seconds if window_seconds > 0 else 0.0
    diff = tx_rate - rx_rate
    attributed_loss = (diff / tx_rate) if tx_rate > 0 else None

    evidence = (
        f"window={window_seconds}s direction={direction}\n"
        f"  {tx_label}: delta={tx_delta} pkts, rate={tx_rate:.2f} pps\n"
        f"  {rx_label}: delta={rx_delta} pkts, rate={rx_rate:.2f} pps\n"
        f"  diff: {diff:.2f} pps "
        f"({attributed_loss * 100:.1f}% attributed loss)"
        if attributed_loss is not None else
        f"window={window_seconds}s direction={direction}\n"
        f"  {tx_label}: delta={tx_delta} pkts, rate={tx_rate:.2f} pps\n"
        f"  {rx_label}: delta={rx_delta} pkts, rate={rx_rate:.2f} pps\n"
        f"  diff: {diff:.2f} pps (no traffic in window — attribution unavailable)"
    )

    return {
        "direction": direction,
        "window_seconds": window_seconds,
        "tx_rate_pkts_per_s": tx_rate,
        "rx_rate_pkts_per_s": rx_rate,
        "diff_pkts_per_s": diff,
        "attributed_loss_pct": attributed_loss,
        "evidence": evidence,
    }


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _shell_quote(s: str) -> str:
    """Minimal shell quoting for grep patterns."""
    import shlex
    return shlex.quote(s)
