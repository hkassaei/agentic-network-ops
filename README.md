# Agentic Network Ops

AI-powered troubleshooting platform for a 5G SA + IMS (VoNR) network stack. Includes a browser-based GUI, three generations of RCA agents, and a chaos engineering framework.

## Prerequisites

- Docker + Docker Compose v2.14+
- Python 3.10+
- For v1.5/v2/v3/v4 agents + chaos engine (Vertex AI / Gemini):
  ```
  export GOOGLE_CLOUD_PROJECT=<your-project>
  export GOOGLE_CLOUD_LOCATION=<region>
  export GOOGLE_GENAI_USE_VERTEXAI=TRUE
  ```

## Getting Started

### 1. Configure environment variables

```bash
cp ops.env.example ops.env
```

Edit `ops.env` with your values:

| Variable | Required for | Example |
|---|---|---|
| `GOOGLE_CLOUD_PROJECT` | RCA agents v3/v4 | `my-gcp-project` |
| `GOOGLE_CLOUD_LOCATION` | RCA agents v3/v4 | `northamerica-northeast1` |
| `GOOGLE_GENAI_USE_VERTEXAI` | RCA agents v3/v4 | `TRUE` |
| `ANTHROPIC_API_KEY` | RCA agent v1.5 (optional, for Claude) | `sk-ant-...` |

`ops.env` is listed in `.gitignore` and is never committed.

### 2. Set up and start the operations layer

```bash
# Create GUI venv and install deps (one-time)
python3 -m venv gui/.venv
source gui/.venv/bin/activate
pip install -r gui/requirements.txt

# Start the ops layer (Neo4j + GUI)
./scripts/start-ops.sh
```

This brings up the GUI (Python process), Neo4j ontology database, and ontology loader — without starting the network stack. You can then deploy the network and UEs from the GUI.

| Service | URL | Credentials |
|---|---|---|
| GUI | http://localhost:8073 | — |
| Neo4j Browser | http://localhost:7474 | `neo4j` / `ontology` |
| Grafana | http://localhost:3000 | `open5gs` / `open5gs` (available after network starts) |

### 3. Deploy the network from the GUI

Open http://localhost:8073 and use the **Deploy Full Stack** button in the Stack Controls tab. This builds Docker images, starts the 5G core + IMS stack, provisions subscribers, and deploys UEs — all streamed in real-time.

Or start the network manually (with custom Grafana dashboards):

```bash
docker compose -p vonr \
  -f network/sa-vonr-deploy.yaml \
  -f grafana-dashboards.yaml \
  up -d
```

## GUI

The GUI is the main control surface. It deploys/tears down the stack, controls UEs, streams logs, shows live topology, and runs AI investigations — all from the browser at **http://localhost:8073**.

### Tabs

1. **Stack Controls** — Deploy/teardown the full 5G+IMS stack or just the UEs (streams progress over WebSocket)
2. **UE Control** — Call, Hangup, Answer, Hold/Unhold buttons for UE1 and UE2
3. **Live Logs** — Streams docker logs from UEs with color-coded SIP/NAS events
4. **Topology** — Live network graph showing container status and fault overlays
5. **AI Investigation** — Free-text troubleshooting, routed to one of three agent versions

### Running Agentic Ops via GUI

1. Deploy the stack using **"Deploy Full Stack"** in Stack Controls
2. Once up, switch to the **AI Investigation** tab
3. Type a question like *"UE1 can't register. What's wrong?"*
4. The GUI streams the agent's thinking, tool calls, and final diagnosis in real-time

### Agent Versions

| Version | Tab | Engine | Description |
|---------|-----|--------|-------------|
| v1.5 | Investigate | Pydantic AI (Claude/Gemini) | Single agent with tools |
| v2 | Investigate V2 | Google ADK (Gemini) | Multi-phase pipeline with specialist agents |
| v3 | Investigate V3 | Google ADK (Gemini) | Context-isolated multi-phase |
| v4 | Investigate V4 | Google ADK (Gemini 2.5) | Topology-aware, context-isolated multi-phase with dynamic specialist dispatch (latest) |

## E2E VoNR Voice Test

End-to-end voice call testing using UERANSIM (5G UE + gNB) with pjsua (PJSIP) for SIP/voice. Kamailio IMS authentication is relaxed from IMS-AKA to SIP Digest auth for testability.

### Quick Start (manual)

```bash
# 0. Build base images (one-time)
docker build -t docker_open5gs ./network/base
docker build -t docker_kamailio ./network/ims_base
docker build -t docker_ueransim ./network/ueransim

# 1. Start the ops layer, then deploy the network from the GUI
cp ops.env.example ops.env  # Edit with your GCP project + API keys
./scripts/start-ops.sh
# Open http://localhost:8073 → Deploy Full Stack
# Or start the network manually:
docker compose -p vonr -f network/sa-vonr-deploy.yaml -f grafana-dashboards.yaml up -d

# 2. Build the pjsua-enabled UERANSIM image
./scripts/build.sh

# 3. Run the full e2e test (provisions, configures, deploys UEs, waits for registration)
./scripts/e2e-vonr-test.sh

# 4. Tear down everything
./scripts/teardown.sh
```

Or just use the GUI — the **Deploy Full Stack** button runs the same flow.

### What the Deploy Script Does

`scripts/e2e-vonr-test.sh` automates the full flow:

1. Builds Docker images if missing
2. Starts 5G core + IMS stack (17 containers), verifies all are running
3. Builds the pjsua-enabled UERANSIM image
4. Copies modified Kamailio configs into P-CSCF and S-CSCF (disables IPsec, switches to MD5 auth)
5. Provisions two test subscribers in Open5GS (MongoDB) and PyHSS (REST API)
6. Starts the gNB
7. Deploys two UERANSIM UE containers with pjsua
8. Polls until both UEs show IMS registration success

Each UE container:
- Starts UERANSIM `nr-ue` → attaches to 5G core → establishes two PDU sessions (internet + IMS)
- Waits for the IMS APN TUN interface to come up (192.168.101.x)
- Starts pjsua bound to the IMS TUN interface → registers with P-CSCF through the full data plane

### Data Path

All SIP and RTP traffic traverses the complete 5G stack:

```
pjsua → uesimtun1 (IMS APN) → UERANSIM nr-ue → gNB → AMF/UPF → P-CSCF → IMS
```

Nothing bypasses the core network.

### What's Modified vs. Original

Only two Kamailio config files are changed (originals are never touched):

| File | Change | Why |
|------|--------|-----|
| `kamailio/pcscf/pcscf.cfg` | `WITH_IPSEC` commented out | pjsua doesn't support IPsec SA negotiation |
| `kamailio/scscf/scscf.cfg` | `REG_AUTH_DEFAULT_ALG` set to `"MD5"` | pjsua uses SIP Digest auth, not IMS-AKA/Milenage |

The teardown script restores the originals automatically.

### Test Subscribers

Defined in `e2e.env`:

| | UE1 (Caller) | UE2 (Callee) |
|---|---|---|
| IMSI | 001011234567891 | 001011234567892 |
| MSISDN | 0100001111 | 0100002222 |
| Container IP | 172.22.0.50 | 172.22.0.51 |

## Agentic Chaos (Fault Injection + RCA Challenge)

A chaos engineering framework that injects controlled faults into the running stack, observes symptoms, then challenges an RCA agent to diagnose the root cause — blind, with no hints. The agent's diagnosis is scored against ground truth by an LLM judge.

### How It Works

1. **Baseline** — Captures pre-fault metrics and container state
2. **Inject** — Applies one or more faults from the scenario (container kill, network latency, config corruption, etc.)
3. **Observe** — Polls metrics and logs until symptoms appear or timeout
4. **Challenge** — Prompts the RCA agent with a blind question: *"The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause."* The agent must discover everything using its own tools
5. **Score** — An LLM judge compares the diagnosis against ground truth (40% root cause, 25% component overlap, 15% severity, 10% fault type, 10% confidence calibration)
6. **Heal** — Reverses all faults via triple-lock safety (SQLite registry + TTL reaper + signal handlers)
7. **Record** — Writes a structured JSON episode + markdown report

### Safety

Every injected fault is registered in SQLite before injection. A background TTL reaper auto-heals after 120s. SIGINT/SIGTERM handlers heal all faults on exit. Run `heal-all` if anything gets stuck.

### Setup

The chaos CLI runs independently from the GUI. It must run from the **repo root**.

```bash
cd $HOME/agentic-network-ops

# Create a dedicated venv (one-time)
python3 -m venv agentic_chaos/.venv
source agentic_chaos/.venv/bin/activate
pip install -r agentic_chaos/requirements.txt

# Set Vertex AI credentials (required for the RCA agents and LLM scorer)
export GOOGLE_CLOUD_PROJECT="<your-project>"
export GOOGLE_CLOUD_LOCATION="<region>"
export GOOGLE_GENAI_USE_VERTEXAI="TRUE"
```

#### Additional setup for v5 agent (ontology-backed)

v5 requires the Neo4j ontology database to be running and seeded:

```bash
# Activate the chaos venv
source agentic_chaos/.venv/bin/activate

# neo4j driver is already in requirements.txt — verify it's installed
pip install neo4j

# Start the ops layer (includes Neo4j)
./scripts/start-ops.sh

# Seed the ontology database (run once, or after ontology YAML changes)
python -m network_ontology --uri bolt://localhost:7687 --reset -v
```

### CLI Usage

The stack must be up (via GUI or scripts) before running scenarios. Always run from the **repo root** with the chaos venv activated.

```bash
# List available scenarios
python -m agentic_chaos list-scenarios

# Run a scenario (challenges the RCA agent and scores the diagnosis)
python -m agentic_chaos run "DNS Failure" --agent v1.5
python -m agentic_chaos run "P-CSCF Latency" --agent v3
python -m agentic_chaos run "Data Plane Degradation" --agent v4
python -m agentic_chaos run "gNB Radio Link Failure" --agent v5

# List recorded episodes
python -m agentic_chaos list-episodes

# Show a specific episode
python -m agentic_chaos show-episode run_20260324_143022_pcscf_latency

# Emergency: heal all active faults
python -m agentic_chaos heal-all

# Verbose logging
python -m agentic_chaos -v run "P-CSCF Latency" --agent v1.5
```

### Scenarios

| Scenario | Category | Blast Radius | What It Does |
|----------|----------|--------------|--------------|
| gNB Radio Link Failure | RAN | single | Kills the gNB container |
| P-CSCF Latency | IMS | single | Adds network latency to P-CSCF |
| S-CSCF Crash | IMS | single | Stops the S-CSCF container |
| HSS Unresponsive | IMS | single | Pauses PyHSS |
| Data Plane Degradation | core | single | Packet loss/latency on UPF |
| MongoDB Gone | infra | global | Stops MongoDB (affects all NFs) |
| DNS Failure | infra | global | Kills the DNS container |
| IMS Network Partition | IMS | multi | Network partition between IMS components |
| AMF Restart | core | single | Restarts AMF (simulates upgrade) |
| Cascading IMS Failure | IMS | multi | Multiple IMS faults in sequence |

## Operations Layer (`network-ops.yaml`)

Everything on top of the upstream `docker_open5gs` network stack is managed by a single `network-ops.yaml` compose file. This keeps the submodule untouched while providing a clean, containerized operations layer.

The operations layer is split into two compose files:

| Component | Type | Port | How to start |
|-----------|------|------|-------------|
| GUI | Python process (host) | 8073 | `./scripts/start-ops.sh` or `python3 gui/server.py` |
| Neo4j ontology | Docker (`network-ops.yaml`) | 7474, 7687 | `./scripts/start-ops.sh` |
| Ontology loader | Docker (one-shot) | — | Runs automatically with Neo4j |
| Grafana overrides | Docker (`grafana-dashboards.yaml`) | 3000 | Paired with network stack |

### Custom Grafana Dashboards

Custom dashboards in `grafana/dashboards/` are mounted into Grafana via `grafana-dashboards.yaml`. This file is always paired with the network stack:

```bash
docker compose -p vonr -f network/sa-vonr-deploy.yaml -f grafana-dashboards.yaml up -d
```

| Dashboard | File |
|-----------|------|
| 5G Core | `grafana/dashboards/5g_core_dashboard.json` |
| IMS | Planned — see `grafana/ims-metrics-plan.md` |

To add a new dashboard: drop a JSON file in `grafana/dashboards/` and restart Grafana.

### Network Ontology

The ontology is a Neo4j graph database encoding the network's component topology, causal failure chains, log semantics, symptom signatures, and protocol stack rules. It replaces LLM causal reasoning with pre-computed domain knowledge.

YAML source files live in `network_ontology/data/`. The `ontology-loader` container seeds Neo4j automatically on startup. See `docs/network-ontology-brainstorm.md` for design details.

## Directory Structure

```
agentic-network-ops/
├── gui/                        # Browser-based GUI (Python aiohttp + vanilla JS)
│   ├── server.py               # Backend: REST + WebSocket handlers
│   ├── index.html              # Single-page app frontend
│   ├── metrics.py              # Prometheus metrics collector
│   ├── topology.py             # Network topology builder
│   └── requirements.txt        # Python deps (aiohttp, pydantic-ai, google-adk)
├── agentic_ops/                # v1.5: Single Pydantic AI agent
│   ├── agent.py                # Agent definition + tool wiring
│   ├── tools.py                # Docker/network inspection tools
│   └── prompts/system.md       # System prompt
├── agentic_ops_v2/             # v2: Multi-agent ADK pipeline
│   ├── orchestrator.py         # Triage → Trace → Dispatch → Specialists → Synthesis
│   └── agents/                 # Specialist agent definitions
├── agentic_ops_v3/             # v3: Context-isolated multi-phase
│   ├── orchestrator.py         # Same pipeline, fresh sessions per phase
│   └── agents/                 # Specialist agent definitions
├── agentic_ops_v4/             # v4: Topology-aware multi-phase (latest)
│   ├── orchestrator.py         # Session-per-phase + dynamic specialist dispatch
│   ├── agents/                 # 8 agents: triage, tracer, dispatcher, 4 specialists, synthesis
│   └── tools.py                # Reuses v1.5 tools + get_network_topology
├── agentic_chaos/              # Fault injection + RCA challenge framework
│   ├── cli.py                  # CLI: run scenarios, list episodes, heal
│   ├── engine.py               # Fault injection engine (triple-lock safety)
│   └── scenarios/              # Pre-built failure scenarios
├── network-ops.yaml             # Docker Compose: operations layer (GUI, ontology)
├── grafana-dashboards.yaml      # Docker Compose override: custom Grafana dashboards
├── ops.env.example             # Template for ops.env (API keys, GCP project)
├── grafana/                    # Custom Grafana dashboards (overlay on submodule)
│   ├── dashboards/             # Dashboard JSON files
│   │   └── 5g_core_dashboard.json
│   ├── custom_dashboards.yaml  # Provisioning config for custom dashboards
│   └── ims-metrics-plan.md     # Plan for IMS metrics exporter
├── network_ontology/           # Network domain knowledge graph
│   ├── data/                   # YAML source files (components, causal chains, etc.)
│   ├── schema/                 # Neo4j graph schema
│   ├── loader.py               # Seeds Neo4j from YAML
│   ├── query.py                # Python query API for agents
│   └── Dockerfile              # One-shot loader container
├── network/                    # Full 5G SA + IMS stack (from docker_open5gs)
│   ├── sa-vonr-deploy.yaml     # Docker Compose: core + IMS (17 containers)
│   ├── nr-gnb.yaml             # Docker Compose: gNB
│   └── .env                    # Network topology (IPs, MCC/MNC, subnets)
├── e2e-vonr.yaml               # Docker Compose: test UEs
├── e2e.env                     # Test subscriber credentials
├── ueransim/                   # UERANSIM + pjsua image and configs
│   ├── Dockerfile              # Extends docker_ueransim with pjsua
│   └── pjsua_entrypoint.sh    # Waits for IMS bearer, registers with P-CSCF
├── kamailio/                   # Modified Kamailio configs for digest auth
│   ├── pcscf/                  # P-CSCF: IPsec disabled
│   └── scscf/                  # S-CSCF: MD5 auth
└── scripts/                    # Orchestration scripts
    ├── e2e-vonr-test.sh        # Full deploy + test (10-step super script)
    ├── deploy-ues.sh           # Deploy UEs on existing stack
    ├── teardown-ues.sh         # Teardown UEs only
    ├── teardown-stack.sh       # Teardown core + IMS + gNB
    ├── teardown.sh             # Teardown everything
    ├── build.sh                # Build docker_ueransim_pjsua image
    └── provision.sh            # Provision test subscribers
```
