# VoNR Learning Tool — GUI

A multi-page browser-based GUI for deploying, controlling, and observing the full 5G SA + IMS + VoNR stack.

## Quick Start

```bash
# From the repo root
python3 -m venv gui/.venv
source gui/.venv/bin/activate
pip install -r gui/requirements.txt

python3 gui/server.py
```

Open http://localhost:8073 in your browser.

## Pages

| Route | Template | JS files | Description |
|-------|----------|----------|-------------|
| `/` | `dashboard.html` | common, controls, logs, investigate | Stack deploy/teardown, UE controls, live logs |
| `/topology` | `topology.html` | common, topology | D3.js live network graph with metrics + detail panel |
| `/flows` | `flows.html` | common, topology, flow-viewer | Animated protocol flow step-through |
| `/investigate` | `investigate.html` | common, investigate | Tabbed v1.5/v3/v4/v5 AI investigation |
| `/logs` | `logs.html` | common, logs | Full-screen UE log viewer with filtering |

## Architecture

The GUI is a multi-page app with shared CSS/JS components:

```
gui/
├── server.py                      # aiohttp backend: REST + WebSocket + page routes
├── templates/                     # Page HTML templates (complete HTML documents)
│   ├── dashboard.html             # / — stack controls, UE panels, live logs
│   ├── topology.html              # /topology — D3.js topology + metrics detail
│   ├── flows.html                 # /flows — protocol flow animation
│   ├── investigate.html           # /investigate — v1.5/v3/v4/v5 tabs
│   └── logs.html                  # /logs — full-screen UE log viewer
├── static/
│   ├── css/style.css              # All shared styles
│   ├── js/
│   │   ├── common.js              # Shared: WS_BASE, API_BASE, escapeHtml, pollStatus
│   │   ├── topology.js            # D3.js topology renderer (single source of truth)
│   │   ├── controls.js            # Stack deploy/teardown + UE actions + modal
│   │   ├── logs.js                # Log streaming, classification, timeline events
│   │   ├── investigate.js         # All investigation modals: v1.5, v3, v4/v5
│   │   └── flow-viewer.js         # Flow step-through animation + dot animation
│   └── lib/d3.v7.min.js           # D3.js v7 library
├── index.html                     # Redirect to / (backward compat)
├── flows.html                     # Redirect to /flows (backward compat)
├── metrics.py                     # Prometheus metrics collector
├── topology.py                    # Network topology builder (ontology → YAML → fallback)
└── requirements.txt               # Python deps
```

Each page is a complete HTML document that includes the shared CSS/JS via `<link>` and `<script>` tags. No server-side templating — pages are served as static files via `web.FileResponse`.

## Features

- **Deploy Stack** — full stack from scratch (core + IMS + gNB + UEs), streamed over WebSocket
- **Deploy UEs** — provisions and starts UEs on an already-running stack
- **Tear Down UEs** — stops UEs, restores Kamailio configs, cleans up subscribers
- **Tear Down Stack** — stops gNB and core + IMS containers
- **UE Controls** — call, hang up, answer, hold/unhold via pjsua commands
- **Live Logs** — streams `docker logs -f` with noise filtering and color-coded SIP/NAS events
- **Event Timeline** — extracts key milestones (registration, PDU sessions, call state changes)
- **D3.js Topology** — live network graph with SBI bus, plane-filtered edges, metrics badges, detail panel with sparklines
- **Protocol Flows** — animated step-through of IMS Registration, VoNR Call Setup, etc.
- **AI Explain** — sends logs to Claude Code CLI for a plain-English explanation
- **AI Investigation** — free-text troubleshooting via v1.5/v3/v4/v5 agents over WebSocket

## Requirements

- Python 3.10+
- Docker and Docker Compose
- Claude Code CLI installed and authenticated (for the AI Explain feature)
- Neo4j running (for ontology-powered features; optional)

## Port

Default: `8073`. Override with `GUI_PORT` environment variable.
