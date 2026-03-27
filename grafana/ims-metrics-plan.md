# IMS Grafana Dashboard — Metrics Plan

## Goal

Create a custom Grafana dashboard for IMS nodes (P-CSCF, I-CSCF, S-CSCF, RTPEngine, PyHSS) following the same overlay pattern as the 5G Core dashboard — stored in the parent repo, mounted via `docker-compose.grafana.yml`.

## Problem

IMS components do not expose Prometheus metrics endpoints. Grafana can only query Prometheus, so there is no data to display today.

| Component | Prometheus endpoint? | Current stats method |
|-----------|---------------------|----------------------|
| P-CSCF (Kamailio) | No — `xhttp_prom` module not compiled into `ims_base` image | `docker exec pcscf kamcmd stats.get_statistics all` |
| I-CSCF (Kamailio) | No — same reason | `docker exec icscf kamcmd stats.get_statistics all` |
| S-CSCF (Kamailio) | No — same reason | `docker exec scscf kamcmd stats.get_statistics all` |
| RTPEngine | No — `--prometheus-port` not set in startup flags | `docker exec rtpengine rtpengine-ctl list totals` |
| PyHSS | Built-in but disabled (`prometheus.enabled: False` in `network/pyhss/config.yaml`) | REST API `GET /ims_subscriber/list` |

The GUI's `network/operate/gui/metrics.py` works around this by shelling out to `docker exec`, but that approach is not available to Grafana/Prometheus.

## Options Considered

### Option 1: Lightweight exporter container (selected)

Add a small Python service in the parent repo that periodically runs `kamcmd` and `rtpengine-ctl` via `docker exec`, parses the output, and exposes it as Prometheus metrics on an HTTP endpoint. Prometheus scrapes this exporter like any other target.

**Pros:**
- Keeps the submodule completely untouched
- Follows the established parent-repo overlay pattern
- Single container covers all IMS components
- Reuses the same stat-parsing logic already proven in `metrics.py`

**Cons:**
- Requires `docker.sock` mount (or Docker API access) to run `docker exec`
- Adds one more container to the stack
- Slight latency vs native Prometheus endpoints (exec overhead)

### Option 2: Rebuild Kamailio with `xhttp_prom` module

Add `xhttp_prom` to `network/ims_base/modules.lst`, load the module in each CSCF kamailio config, and configure Prometheus scrape targets.

**Pros:** Native Prometheus metrics, no extra container.
**Cons:** Requires submodule changes (defeats the goal). Needs Kamailio image rebuild. Each CSCF config must be modified.

### Option 3: Enable PyHSS Prometheus only

Flip `prometheus.enabled: True` in `network/pyhss/config.yaml`. Only covers PyHSS, not Kamailio or RTPEngine.

**Pros:** Trivial change, built-in support.
**Cons:** Submodule change. Only solves 1 of 5 components.

## Selected: Option 1 — Exporter Container

## Implementation Plan

### 1. Exporter service (`grafana/ims-exporter/`)

- `exporter.py` — Python script using `prometheus_client` library
- Runs `docker exec` against each IMS container on a configurable interval (default 5s, matching Prometheus scrape interval)
- Exposes metrics on port 9092 (or configurable via env var)
- Parses the same stat keys already identified in `metrics.py`:

**Kamailio metrics to export (per CSCF):**

P-CSCF:
- `kamailio_pcscf_registered_contacts` — `ims_usrloc_pcscf:registered_contacts`
- `kamailio_pcscf_active_dialogs` — `dialog_ng:active`
- `kamailio_pcscf_register_requests` — `core:rcv_requests_register`
- `kamailio_pcscf_invite_requests` — `core:rcv_requests_invite`
- `kamailio_pcscf_bye_requests` — `core:rcv_requests_bye`
- `kamailio_pcscf_active_transactions` — `tmx:active_transactions`
- `kamailio_pcscf_1xx_replies` — `sl:1xx_replies`
- `kamailio_pcscf_200_replies` — `sl:200_replies`
- `kamailio_pcscf_4xx_replies` — `sl:4xx_replies`
- `kamailio_pcscf_5xx_replies` — `sl:5xx_replies`

I-CSCF:
- `kamailio_icscf_register_requests` — `core:rcv_requests_register`
- `kamailio_icscf_invite_requests` — `core:rcv_requests_invite`
- `kamailio_icscf_active_transactions` — `tmx:active_transactions`

S-CSCF:
- `kamailio_scscf_active_contacts` — `ims_usrloc_scscf:active_contacts`
- `kamailio_scscf_accepted_regs` — `ims_registrar_scscf:accepted_regs`
- `kamailio_scscf_active_dialogs` — `dialog_ng:active`
- `kamailio_scscf_register_requests` — `core:rcv_requests_register`
- `kamailio_scscf_invite_requests` — `core:rcv_requests_invite`
- `kamailio_scscf_active_transactions` — `tmx:active_transactions`

**RTPEngine metrics to export:**
- `rtpengine_current_sessions` — `current_sessions_own` or `current_sessions_total`
- `rtpengine_total_sessions` — `totalstats_total_sessions`
- `rtpengine_total_timeout_sessions` — `totalstats_total_timeout_sessions`
- `rtpengine_total_reject_sessions` — `totalstats_total_reject_sessions`

**PyHSS metrics to export:**
- `pyhss_ims_subscribers` — count from `GET /ims_subscriber/list`

### 2. Dockerfile (`grafana/ims-exporter/Dockerfile`)

Minimal Python image with `prometheus_client` and `aiohttp` (for PyHSS API calls). Mount `docker.sock` for exec access.

### 3. Compose override addition (`docker-compose.grafana.yml`)

Add the exporter service alongside the existing Grafana volume overrides:

```yaml
services:
  ims-exporter:
    build: ../grafana/ims-exporter/
    container_name: ims_exporter
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
    environment:
      - PYHSS_IP=${PYHSS_IP}
    expose:
      - "9092"
    networks:
      default:
        ipv4_address: ${IMS_EXPORTER_IP:-172.22.0.50}
```

### 4. Prometheus scrape config overlay

Add IMS exporter target to Prometheus. Since `prometheus.yml` is in the submodule, either:
- Use the same compose-override pattern to mount an additional scrape config
- Or inject via `docker cp` + reload (existing pattern)

Prometheus supports `--web.enable-lifecycle` for hot reload via `POST /-/reload`.

### 5. Dashboard JSON (`grafana/dashboards/ims_dashboard.json`)

Create dashboard with panels organized by component:

- **P-CSCF row:** Registered contacts (stat), active dialogs (stat), SIP requests by type (time series), reply codes (time series)
- **S-CSCF row:** Active contacts (stat), accepted registrations (stat), SIP requests (time series), active transactions (time series)
- **I-CSCF row:** Registration requests (stat), INVITE requests (stat), active transactions (stat)
- **RTPEngine row:** Current sessions (stat), total sessions over time (time series)
- **PyHSS row:** IMS subscriber count (stat)

Dashboard will be provisioned identically to 5G Core — placed in `grafana/dashboards/`, picked up by `custom_dashboards.yml` provider, displayed under the "5G Core" folder in Grafana.

### 6. Environment variable

Add `IMS_EXPORTER_IP` to `e2e.env` (parent repo) to avoid touching the submodule's `.env`.
