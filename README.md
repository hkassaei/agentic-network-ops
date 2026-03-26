# Agentic Network Ops

AI-powered troubleshooting platform for a 5G SA + IMS (VoNR) network stack. Includes a browser-based GUI, three generations of RCA agents, and a chaos engineering framework.

## Prerequisites

- Docker + Docker Compose v2.14+
- Python 3.10+
- For v1.5 agent (Claude): `ANTHROPIC_API_KEY`
- For v2/v3 agents + chaos engine (Vertex AI / Gemini):
  ```
  GOOGLE_CLOUD_PROJECT=<your-project>
  GOOGLE_CLOUD_LOCATION=<region>
  GOOGLE_GENAI_USE_VERTEXAI=TRUE
  ```

## GUI

The GUI is the main control surface. It deploys/tears down the stack, controls UEs, streams logs, shows live topology, and runs AI investigations — all from the browser.

### Setup

```bash
cd $HOME/agentic-network-ops

# Create venv and install deps
python3 -m venv gui/.venv
source gui/.venv/bin/activate
pip install -r gui/requirements.txt

# Start the server
python3 gui/server.py
```

Then open **http://localhost:8073** in your browser.

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
| v3 | Investigate V3 | Google ADK (Gemini) | Context-isolated multi-phase (latest) |

## E2E VoNR Voice Test

End-to-end voice call testing using UERANSIM (5G UE + gNB) with pjsua (PJSIP) for SIP/voice. Kamailio IMS authentication is relaxed from IMS-AKA to SIP Digest auth for testability.

### Quick Start (manual)

```bash
# 0. Build base images (one-time)
docker build -t docker_open5gs ./network/base
docker build -t docker_kamailio ./network/ims_base
docker build -t docker_ueransim ./network/ueransim

# 1. Start the 5G core + IMS stack
docker compose -f network/sa-vonr-deploy.yaml up -d

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
├── agentic_chaos/              # Fault injection + RCA challenge framework
│   ├── cli.py                  # CLI: run scenarios, list episodes, heal
│   ├── engine.py               # Fault injection engine (triple-lock safety)
│   └── scenarios/              # Pre-built failure scenarios
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
