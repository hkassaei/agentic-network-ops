# ADR: Multi-Page GUI Rearchitecture

**Status:** Implemented (2026-04-02)

## Context

`gui/index.html` was 2600+ lines with all CSS, HTML, and JS in one file. The topology D3.js code was duplicated in `flows.html`. This refactoring split it into focused pages with shared components per the plan in `docs/plans/gui-flow-visualization.md` section 2.2/2.3.

## Decision

Split the monolithic single-page app into a multi-page architecture with shared CSS/JS components.

## Final Structure

```
gui/
├── server.py                      # Extended with page routes (/topology, /flows, /investigate, /logs)
├── static/
│   ├── css/
│   │   └── style.css              # All CSS extracted from index.html + nav styles (623 lines)
│   ├── js/
│   │   ├── common.js              # Shared: WS_BASE, API_BASE, escapeHtml, pollStatus, formatMetric* (85 lines)
│   │   ├── topology.js            # D3.js topology: renderTopology, gridToSvg, tooltips, constants (261 lines)
│   │   ├── controls.js            # Stack deploy/teardown + UE actions + modal (96 lines)
│   │   ├── logs.js                # Log viewer: connectLogWs, appendLog, extractEvent, explainLogs (278 lines)
│   │   ├── investigate.js         # All investigation modals: v1.5, v3, v4/v5 with shared renderers (458 lines)
│   │   └── flow-viewer.js         # Flow animation: step-through, dot animation, playback (420 lines)
│   └── lib/
│       └── d3.v7.min.js
├── templates/
│   ├── dashboard.html             # / — stack controls, UE controls, log panels (241 lines)
│   ├── topology.html              # /topology — D3.js topology + metrics detail + gauges (344 lines)
│   ├── flows.html                 # /flows — sidebar + topology + animation + detail (119 lines)
│   ├── investigate.html           # /investigate — tabbed v1.5/v3/v4/v5 interface (231 lines)
│   └── logs.html                  # /logs — full-screen UE log viewer (112 lines)
├── index.html                     # Redirect to / (backward compat)
├── flows.html                     # Redirect to /flows (backward compat)
├── metrics.py
├── topology.py
└── requirements.txt
```

## Pages and JS Mapping

| Page | Route | JS files loaded |
|------|-------|-----------------|
| Dashboard | `/` | common.js, controls.js, logs.js, investigate.js |
| Topology | `/topology` | common.js, topology.js |
| Flows | `/flows` | common.js, topology.js, flow-viewer.js |
| Investigate | `/investigate` | common.js, investigate.js |
| Logs | `/logs` | common.js, logs.js |

## Key Design Decisions

- **No server-side templating**: Each page is a complete HTML document with shared CSS/JS via `<link>`/`<script>` tags. aiohttp serves them as `web.FileResponse`. The nav bar is duplicated in each page rather than using a template engine.
- **No base.html**: Originally planned but dropped. Each page includes its own `<nav>` and `<head>`. This is simpler and avoids adding a template engine dependency.
- **topology.js is the single source of truth**: `renderTopology(svgSelector, topo, opts)` is called from both the topology page and the flows page, eliminating the D3.js duplication that existed between the old index.html and flows.html.
- **Investigate page is inline, not modal**: On the dedicated `/investigate` page, investigation forms are always visible (no modal overlay needed). On the dashboard, they still use modal overlays.
- **Old files kept as redirects**: `gui/index.html` and `gui/flows.html` redirect to `/` and `/flows` respectively for backward compatibility.

## Server Routes

```python
# Page routes
app.router.add_get("/", handle_index)                    # → templates/dashboard.html
app.router.add_get("/topology", handle_topology_page)    # → templates/topology.html
app.router.add_get("/flows", handle_flows_page)          # → templates/flows.html
app.router.add_get("/investigate", handle_investigate_page)  # → templates/investigate.html
app.router.add_get("/logs", handle_logs_page)            # → templates/logs.html
```

## What Changed

- `gui/index.html` (2550 lines) → redirect stub (10 lines)
- `gui/flows.html` (577 lines) → redirect stub (7 lines)
- New: 7 shared JS files in `gui/static/js/`
- New: 5 page templates in `gui/templates/`
- New: shared CSS in `gui/static/css/style.css`
- Updated: `gui/server.py` with 4 new page route handlers
