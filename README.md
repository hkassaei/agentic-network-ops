# Agentic Network Ops

AI-powered troubleshooting platform for a 5G SA + IMS (VoNR) network stack. Built around three pillars:

1. **A live 5G SA + IMS lab** — Open5GS core, Kamailio IMS, UERANSIM gNB/UEs, plus a built-in voice path (pjsua over the IMS APN) for end-to-end VoNR call testing.
2. **An operations layer** — a multi-page browser GUI, a Neo4j-backed network ontology, a Prometheus/Grafana metrics stack, and seven generations of RCA agents (v1.5, v2, v3, v4, v5, v6, v7) that diagnose live faults.
3. **A chaos framework** — controlled fault injection (container kill, `tc netem`, partitions, escalation) with an LLM judge that scores each agent's diagnosis against ground truth.

Audience: telecom engineers and NOC operators who want to stand up the stack, place real VoNR calls through it, inject failures, and watch an LLM-powered RCA pipeline diagnose them.

---

## Table of Contents

1. [System Architecture](#system-architecture)
2. [Component Reference](#component-reference)
3. [Prerequisites](#prerequisites)
4. [Deployment Guide](#deployment-guide)
5. [Running RCA Investigations](#running-rca-investigations)
6. [Running Chaos Scenarios](#running-chaos-scenarios)
7. [Network Ontology](#network-ontology)
8. [Directory Structure](#directory-structure)

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                  Agentic Intelligence Layer                              │
│                                                                          │
│   v1.5    v2    v3    v4    v5    v6    v7  ← RCA agent generations     │
│   (CLI/GUI)   (GUI: v1.5,v3,v4,v5)   (CLI-only: v6, v7)                 │
│                                                                          │
│   agentic_ops_common  (shared infrastructure)                            │
│   ├── metric_kb       Trigger-based event store over metrics.yaml        │
│   ├── anomaly         River + PyOD (ECOD) statistical screener           │
│   ├── correlation     Deterministic event → composite-hypothesis ranker  │
│   ├── path_walk       Transport-layer hop probers (kernel/bridge)        │
│   ├── rag             Past-episode retrieval (TF-IDF over agent_logs/)   │
│   ├── tools           30+ KB-filtered diagnostic tools for agents        │
│   └── models          Shared trace schema (PhaseTrace, ToolCallTrace…)   │
└─────────────────────────┬───────────────────────────────────────────────┘
                          │ reads/writes
                          ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                  Operations Layer                                        │
│                                                                          │
│   GUI (aiohttp + D3.js)        Neo4j Ontology       Grafana + Prom       │
│   ├── /topology  D3 live map   ├── components       ├── 5G core dash     │
│   ├── /          UE controls   ├── interfaces       └── (IMS planned)    │
│   ├── /flows     6 protocol    ├── flows            Anomaly model         │
│   │             flow animator  ├── causal chains    ├── trainer (River)   │
│   ├── /investigate v1.5–v5    ├── log patterns     └── baseline corpus   │
│   └── /stack     deploy/heal   ├── stack rules                            │
│                                ├── metrics KB                             │
│                                └── deployment cfg                         │
└─────────────────────────┬───────────────────────────────────────────────┘
                          │ inspects / controls
                          ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                  VoNR Network Stack (17 containers)                      │
│                                                                          │
│   5G Core (Open5GS)          IMS (Kamailio)          RAN / UEs            │
│   ├── AMF, AUSF, NRF         ├── P-CSCF              ├── gNB (UERANSIM)   │
│   ├── SMF, UPF, PCF          ├── I-CSCF              ├── UE1 + pjsua      │
│   ├── UDM, UDR, BSF          ├── S-CSCF              └── UE2 + pjsua      │
│   ├── NSSF                   ├── PyHSS (Diameter Cx) Datastores            │
│   └── (eUPF optional)        └── RTPEngine           ├── MongoDB          │
│                                                       └── MySQL (PyHSS)   │
└─────────────────────────────────────────────────────────────────────────┘
```

**Data flow.** Open5GS NFs and Kamailio CSCFs export Prometheus metrics; the GUI polls these and surfaces them as topology badges and tooltips. The anomaly model trains on healthy traffic and flags deviations during chaos. Agents consume the live metrics, the ontology, and structured tool outputs — never raw shell.

**Operational layers.** The 5G stack and the operations layer are decoupled. You can bring up the ops layer (Neo4j + GUI) without the network, deploy the network from the GUI, and tear either side down independently.

---

## Component Reference

### RCA Agent Generations

Each agent is a complete pipeline; later versions do not replace earlier ones — they coexist for comparison.

| Version | Engine | Pipeline | Status |
|---------|--------|----------|--------|
| v1.5 | Pydantic AI (Claude or Gemini) | Single agent + tools | GUI + CLI |
| v2 | Google ADK (Gemini) | 4-phase: Triage → Trace → Dispatch (parallel specialists) → Synthesis | CLI |
| v3 | Google ADK (Gemini) | Context-isolated multi-phase (fresh sessions per phase) | GUI + CLI |
| v4 | Google ADK (Gemini 2.5) | Topology-aware, dynamic specialist dispatch | GUI + CLI |
| v5 | Google ADK (Gemini 2.5) | 7-phase ontology-powered: Anomaly Screener (ML) → Network Analyst → Pattern Matcher → Instruction Generator → Investigator → Evidence Validator → Synthesis | GUI + CLI |
| v6 | Google ADK (Gemini 2.5) | **Parallel multi-hypothesis**: one focused Investigator sub-agent per hypothesis (max 3), each with its own falsification plan; reconciled via consensus + evidence-citation guardrails | CLI |
| v7 | Google ADK (Gemini 2.5 Pro + Flash) | **Determinism-first 8-phase**: Anomaly Screener → Symptom Classifier (KB) → Path Prioritizer + Path-Walk Investigator (transport-layer short-circuit) → Event Aggregator → Correlation Analyzer → RAG injection → Network Analyst → Instruction Generator → Investigators × N (multi-shot consensus) → Evidence Validator → Synthesis → Blast-Radius / Impact Narrator | CLI |

**v7 highlights** (latest, default for new work):

- **Determinism over LLM judgment** wherever possible — path prioritization, symptom classification, event correlation, blast-radius, and 20+ guardrails are all mechanical. The LLM is used only for semantic synthesis with bounded Pydantic schemas.
- **Transport-layer short-circuit.** If the screener and KB-driven symptom classifier agree the fault is transport-layer (e.g. partition, packet loss, latency), v7 walks the top-5 candidate flows hop-by-hop with kernel/bridge probers and reports a localized fault — no LLM hypothesis loop needed.
- **Multi-shot Investigator consensus.** Each hypothesis is probed twice (when shot 1 is non-INCONCLUSIVE); verdicts reconcile via a guardrail.
- **Probe grounding.** The Instruction Generator's falsification probes are grounded in `metric_inventory` + `nf_liveness_probes` per NF; the IG cannot ask the Investigator to query metrics or run probes that don't exist on the target container.
- **Blast-radius reasoning (Phase 8).** Once a root cause is named, v7 computes downstream impact deterministically from `flows.yaml` + `components.yaml`, then renders prose for NOC and non-engineer audiences via the flash model.
- **Model configuration.** Two slots — `pro` and `flash` — overridable via `GEMINI_PRO_MODEL` / `GEMINI_FLASH_MODEL`. Defaults: `gemini-2.5-pro` and `gemini-2.5-flash`. See `agentic_ops_v7/model_config.py`.

### Shared Infrastructure — `agentic_ops_common`

Cross-version package used by v6 and v7 (and adoptable by older agents). Replaces per-version copies of preprocessing, KB access, and tool wrappers:

| Submodule | Purpose |
|-----------|---------|
| `metric_kb/` | Loads `network_ontology/data/metrics.yaml` into a typed KB. Provides trigger evaluation (`simpleeval`), an `EventStore` (SQLite) for fired events during chaos episodes, feature mapping, and flag enrichment. |
| `anomaly/` | `AnomalyScreener` (River HalfSpaceTrees + PyOD ECOD), `MetricPreprocessor` for normalizing Prometheus counters into model features. |
| `correlation/` | `correlate_episode()` — ranks composite hypotheses from fired metric-KB events. Used by v6/v7 Phase 2. |
| `path_walk/` | `HopProber` protocol, `KernelHopProber`, `DockerBridgeProber`. Inspect container networks for drops, latency, and reachability without invoking the LLM. |
| `rag/` | `EpisodeRetriever` — TF-IDF index over past chaos episodes for similar-fault retrieval. Output lives in `rag_index/`; rebuild via `scripts/rebuild_rag_index.py` or `python -m rag_indexer`. |
| `tools/` | 30+ agent-facing tools — `get_diagnostic_metrics`, `get_dp_quality_gauges`, `get_deployment_config`, container/log inspection, reachability probes, KB-backed flow steps. All KB-filtered so agents see annotated metrics, not raw Prometheus. |
| `models/` | `InvestigationTrace`, `PhaseTrace`, `ToolCallTrace`, `TokenBreakdown` — shared trace schema for episode logs and the RAG corpus. |

### GUI

Multi-page web app at **http://localhost:8073** (aiohttp + vanilla JS + D3.js):

| Route | Nav label | Description |
|-------|-----------|-------------|
| `/topology` | **Network** | D3.js live topology with metric badges, click-to-open detail panel (metrics + ontology-backed tooltips + live logs), plane filters, RTP/UPF data-plane gauge strip |
| `/` | **UEs** | UE1/UE2 call controls (call, hangup, answer, hold), live log stream with event timeline, AI log explain |
| `/flows` | **Protocol Flows** | Animated step-through of 6 procedures: IMS Registration, VoNR Call Setup, VoNR Call Teardown, PDU Session Establishment, UE Deregistration, Diameter Cx Authentication |
| `/investigate` | **Investigate** | Tabbed interface for **v1.5 / v3 / v4 / v5** with streamed phase / tool-call / diagnosis output. **v6 and v7 are CLI-only** at present. |
| `/stack` | **Stack** | Deploy / teardown for stack + UEs, container health by layer, ontology DB maintenance (re-seed from YAML) |

All pages share a common nav bar with active-page highlighting and a live `N/N Ready` status pill. Every metric tooltip in the detail panels pulls from the ontology (`network_ontology/data/metrics.yaml`) via `/api/metric-descriptions` — single source of truth.

### Chaos Framework — `agentic_chaos`

Injects a controlled fault, generates traffic and waits for symptoms, then **blindly** challenges an RCA agent and scores the diagnosis. Pipeline:

```
BaselineCollector → FaultInjector → SymptomObserver (with optional Boiling-Frog escalation)
                  → ChallengeAgent (invokes RCA agent) → Scorer (LLM judge vs. ground truth)
                  → Healer (reverse faults via SQLite registry) → EpisodeRecorder
```

**Triple-lock safety.** Every fault is registered in SQLite before injection. A background TTL reaper auto-heals after 120s. SIGINT/SIGTERM handlers heal all live faults on exit. `heal-all` is the manual escape hatch.

**Boiling-Frog escalation.** Scenarios with `escalation=True` (e.g. P-CSCF Latency) ramp severity progressively (100 ms → 250 ms → 500 ms …) until symptoms appear — useful for discovering protocol-break thresholds.

**Scoring.** An LLM judge compares the agent's diagnosis against the simulated failure mode using a weighted rubric (root cause 40%, component overlap 25%, severity 15%, fault type 10%, confidence calibration 10%).

**14 pre-built scenarios** (single NF → multi-NF cascades):

| # | Scenario | Category | Blast Radius |
|---|----------|----------|--------------|
| 1 | gNB Radio Link Failure | RAN | single |
| 2 | P-CSCF Latency | IMS | single |
| 3 | S-CSCF Crash | IMS | single |
| 4 | HSS Unresponsive | IMS | single |
| 5 | Data Plane Degradation | core | single |
| 6 | P-CSCF Packet Loss | IMS | single |
| 7 | Call Quality Degradation | core | single |
| 8 | RTPEngine Latency Injection | IMS | single |
| 9 | UPF Bandwidth Cap | core | single |
| 10 | MongoDB Gone | infra | global |
| 11 | DNS Failure | infra | global |
| 12 | IMS Network Partition | IMS | multi |
| 13 | AMF Restart (Upgrade Simulation) | core | single |
| 14 | Cascading IMS Failure | IMS | multi |

> Scenarios describe the **simulated failure mode** (what it looks like externally), not the injection mechanism. RCA agents must diagnose the failure mode from observable evidence — the scorer evaluates against the failure mode, not the mechanism.

---

## Prerequisites

- Docker + Docker Compose v2.14+
- Python 3.10+
- For RCA agents (v1.5/v3/v4/v5/v6/v7) and the chaos LLM scorer:
  - A Google Cloud project with Vertex AI enabled and a region selected (Gemini access)
  - Optionally: an Anthropic API key for v1.5 with Claude

---

## Deployment Guide

### 1. Configure environment variables

```bash
cp ops.env.example ops.env
```

Edit `ops.env`:

| Variable | Required for | Example |
|----------|--------------|---------|
| `GOOGLE_CLOUD_PROJECT` | All Gemini-backed agents + chaos scorer | `my-gcp-project` |
| `GOOGLE_CLOUD_LOCATION` | All Gemini-backed agents + chaos scorer | `northamerica-northeast1` |
| `GOOGLE_GENAI_USE_VERTEXAI` | All Gemini-backed agents + chaos scorer | `TRUE` |
| `GEMINI_PRO_MODEL` | v7 (optional model override) | `gemini-2.5-pro` |
| `GEMINI_FLASH_MODEL` | v7 (optional model override) | `gemini-2.5-flash` |
| `ANTHROPIC_API_KEY` | v1.5 with Claude (optional) | `sk-ant-…` |
| `NEO4J_USER` / `NEO4J_PASSWORD` / `NEO4J_URI` | Ontology DB | `neo4j` / `ontology` / `bolt://ontology:7687` |
| `GUI_PORT` | GUI listen port | `8073` |

`ops.env` is gitignored.

Authenticate to GCP once:

```bash
gcloud auth application-default login
gcloud config set project "$GOOGLE_CLOUD_PROJECT"
```

### 2. Build images from source (critical)

The Open5GS base image **must be built from source** — the upstream pre-built image at `ghcr.io/herlesupreeth/docker_open5gs:master` has GTP-U packet counters disabled (`#if 0` in `src/upf/gtp-path.c`, see Open5GS issues #2210 / #2219). Our Dockerfile re-enables them via `sed`. Without this patch, `fivegs_ep_n3_gtp_indatapktn3upf` and `fivegs_ep_n3_gtp_outdatapktn3upf` stay at zero, which breaks the anomaly model, the data-plane scenarios, and the chaos scorer.

```bash
# Open5GS core/IMS base — DO NOT pull from ghcr.io, build locally
docker build -t docker_open5gs ./network/base

# IMS / Kamailio
docker build -t docker_kamailio ./network/ims_base

# RAN / UEs
docker build -t docker_ueransim ./network/ueransim
docker build -t docker_ueransim_pjsua ./network/operate/ueransim

# Supporting
docker build -t docker_dns       ./network/dns
docker build -t docker_rtpengine ./network/rtpengine
docker build -t docker_mysql     ./network/mysql
docker build -t docker_metrics   ./network/metrics
```

Safe to pull from ghcr.io: `docker_kamailio`, `docker_pyhss`, `docker_ueransim`. **`docker_open5gs` must be built locally.**

### 3. Start the operations layer (Neo4j + GUI)

```bash
# One-time: create the GUI venv
python3 -m venv gui/.venv
source gui/.venv/bin/activate
pip install -r gui/requirements.txt

# Bring up Neo4j + ontology-loader
docker compose -f network-ops.yaml up -d

# Start the GUI on http://localhost:8073
python3 gui/server.py
```

| Service | URL | Credentials |
|---------|-----|-------------|
| GUI | http://localhost:8073 | — |
| Neo4j Browser | http://localhost:7474 | `neo4j` / `ontology` |
| Grafana | http://localhost:3000 | `open5gs` / `open5gs` (after the network is up) |

### 4. Deploy the VoNR stack

**Option A — from the GUI (recommended).**
Open http://localhost:8073 → **Stack** page → **Build & Deploy Stack**. Streams build + start logs live. Includes core, IMS, gNB, UEs, and the post-deploy Diameter-fix + health check.

**Option B — scripted (full e2e voice test).**

```bash
./scripts/e2e-vonr-test.sh
```

Does the 10-step deploy: builds images if missing → starts core+IMS (17 containers) → builds the pjsua-enabled UE image → patches Kamailio configs (disables IPsec, switches to MD5 digest auth for pjsua compatibility) → provisions two test subscribers (Open5GS Mongo + PyHSS REST) → starts the gNB → deploys both UEs → polls until both IMS-register.

**Option C — manual Compose.**

```bash
# Core + IMS (17 containers), with custom Grafana dashboards mounted
docker compose -p vonr \
  -f network/sa-vonr-deploy.yaml \
  -f grafana-dashboards.yaml up -d

# gNB
cd network && docker compose -f nr-gnb.yaml up -d && cd ..

# UEs (env vars must be exported for compose variable interpolation)
set -a; source network/.env; source e2e.env; set +a
docker compose -f e2e-vonr.yaml up -d
```

### 5. Post-deploy verification

After a fresh deploy, the I-CSCF / S-CSCF Diameter peer state often gets stuck in `I_Open` because the CSCFs start before PyHSS's Diameter service is ready. SIP REGISTER then fails with 408 timeout. The post-deploy verifier handles this automatically:

```bash
./scripts/post-deploy-verify.sh
```

It audits the diagnostic toolbelt (the binaries `ping`, `dig`, `mongo`, `mysql`, etc. that the Investigator depends on inside every NF), restarts the CSCFs to recover Diameter peers, rechecks the six critical health metrics, and verifies UPF GTP-U counters are incrementing on a test call. Auto-heal retries up to 3 times before failing.

The six health metrics it checks:

| Metric | Expected | Meaning |
|--------|----------|---------|
| `ran_ue` | 2.0 | Both UEs attached to 5G |
| `gnb` | 1.0 | gNB connected to AMF |
| `amf_session` | 4.0 | 4 PDU sessions (2 UEs × 2 APNs) |
| `fivegs_smffunction_sm_sessionnbr` | 4.0 | SMF confirms 4 PDU sessions |
| `ims_usrloc_pcscf:registered_contacts` | 2.0 | Both UEs IMS-registered at P-CSCF |
| `ims_usrloc_scscf:active_contacts` | 2.0 | Both UEs IMS-registered at S-CSCF |

If the UPF counter check fails after a successful call, the `docker_open5gs` image was pulled from ghcr.io instead of built. Rebuild it and redeploy.

### 6. Train the anomaly model

The anomaly screener must be trained on a healthy stack with active traffic. The trainer drives randomized IMS traffic (SIP REGISTER + VoNR calls) while collecting metric snapshots.

```bash
.venv/bin/python -m anomaly_trainer --duration 600
```

Output lands in `agentic_ops_v5/anomaly/baseline/` (`model.pkl` + `training_meta.json`); v5/v6/v7 load it at orchestrator startup. Retrain after any of:

- Rebuilding the stack
- Changing the number of UEs
- Modifying topology or NF configuration
- Adding new metrics to the anomaly preprocessor

### 7. (Optional) Rebuild the RAG case index

v7 uses past chaos episodes as similar-case retrieval. To rebuild the index from `agentic_ops_v{5,6,7}/docs/agent_logs/`:

```bash
python -m rag_indexer
# or
python scripts/rebuild_rag_index.py
```

Defaults: 80% score threshold, snapshots the existing `rag_index/` to `rag_index.bak.<UTC-timestamp>/` before overwriting.

### Teardown

```bash
./scripts/teardown-stack.sh   # Core + IMS + gNB
./scripts/teardown-ues.sh     # UEs only
./scripts/teardown-ops.sh     # GUI + Neo4j (add --purge to delete Neo4j volume)
./scripts/teardown.sh         # Everything
```

---

## Running RCA Investigations

### From the GUI (v1.5 / v3 / v4 / v5)

1. Make sure the stack is deployed and healthy (Stack page → green pills, or `post-deploy-verify.sh`).
2. Navigate to **Investigate**.
3. Pick a version tab and ask a blind question — e.g. *"UE1 can't register. What's wrong?"*
4. The GUI streams the agent's phase events, tool calls, intermediate hypotheses, and the final diagnosis.

### From the CLI (any version, including v6/v7)

```bash
# v7 (latest)
python -m agentic_ops_v7 "UE1 cannot place a VoNR call — investigate"

# v6
python -m agentic_ops_v6 "Investigate registration failures across both UEs"

# Older
python -m agentic_ops_v5 "..."
python -m agentic_ops_v4 "..."
```

Each generation writes a structured episode JSON + markdown report to `agentic_ops_v{N}/docs/agent_logs/run_<UTC>_<scenario_slug>.{json,md}`.

---

## Running Chaos Scenarios

The chaos CLI runs independently of the GUI. **Run it from the repo root** with the chaos venv activated.

```bash
cd $HOME/agentic-network-ops

# One-time venv setup
python3 -m venv agentic_chaos/.venv
source agentic_chaos/.venv/bin/activate
pip install -r agentic_chaos/requirements.txt

# Gemini credentials (or source ops.env, which has them)
set -a; source ops.env; set +a
```

### Single scenario

```bash
# List the 14 scenarios
python -m agentic_chaos list-scenarios

# Run a scenario against an RCA agent version
python -m agentic_chaos run "DNS Failure"          --agent v7
python -m agentic_chaos run "P-CSCF Latency"       --agent v6
python -m agentic_chaos run "S-CSCF Crash"         --agent v5
python -m agentic_chaos run "gNB Radio Link Failure" --agent v4

# Save tokens when faults don't propagate (skip the LLM call)
python -m agentic_chaos run "AMF Restart (Upgrade Simulation)" --agent v7 --abort-on-unpropagated

# Inspect episode results
python -m agentic_chaos list-episodes
python -m agentic_chaos show-episode run_20260527_210520_mongodb_gone

# Emergency: heal everything still in the SQLite registry
python -m agentic_chaos heal-all

# Verbose
python -m agentic_chaos -v run "P-CSCF Latency" --agent v7
```

Supported `--agent` values: `v1.5`, `v3`, `v4`, `v5`, `v6`, `v7`.

### Batch — run every scenario against one agent

```bash
./scripts/run-all-chaos-scenarios.sh v7
# or to skip the LLM when faults don't propagate
./scripts/run-all-chaos-scenarios.sh v7 --abort-on-unpropagated
```

The batch runner:

- Sources `ops.env` so Vertex / Gemini credentials reach the Python subprocess
- Audits the per-NF diagnostic toolbelt (`scripts/audit-container-tooling.sh`) — refuses to start if any NF is missing a binary the Investigator depends on
- Iterates all 14 scenarios, each one going through its built-in `baseline → inject → observe → challenge → heal → record` pipeline (no external redeploy is needed between scenarios — the per-scenario healer restores state)
- Sets `CHAOS_AUTO_HEAL=1` so pre-check failures auto-heal once non-interactively (some scenarios leave the stack briefly unhealthy while UEs re-register)
- Prints a final pass / fail table and points you at `list-episodes` for scores

Episode files: `agentic_ops_v<version>/docs/agent_logs/run_<UTC>_<scenario>.{json,md}`.

---

## Network Ontology

The ontology is a Neo4j graph encoding everything agents and the GUI reason about — components, interfaces, protocol flows, failure modes, metric semantics, log patterns, healthchecks, deployment metadata. It is the **single source of truth** that replaces LLM causal guesswork with pre-computed knowledge.

YAML source files in `network_ontology/data/`:

| File | Contents |
|------|----------|
| `components.yaml` | Network functions — 3GPP role, layer, subsystem, protocols, diagnostic commands |
| `deployment.yaml` | Per-deployment bindings — IPs (env keys), container names, metrics ports, grid positions |
| `deployment_metadata.yaml` | **Port semantics** — per-NF listening ports tagged with `{protocol, interface, role}`; consumed by the `get_deployment_config` tool so agents don't fabricate ports from training priors |
| `interfaces.yaml` | Interfaces between NFs (N1/N2/N3, SBI, Diameter Cx, SIP Mw, etc.) |
| `flows.yaml` | 6 protocol flows (IMS Registration, VoNR Call Setup, VoNR Call Teardown, PDU Session Establishment, UE Deregistration, Diameter Cx Authentication); also drives `/flows` GUI animation |
| `causal_chains.yaml` | Failure modes — observable symptoms, possible causes, diagnostic approaches |
| `log_patterns.yaml` | Annotated log patterns with meaning and common misinterpretations |
| `symptom_signatures.yaml` | Pre-computed symptom → fault signatures for deterministic matching (v5 PatternMatcher) |
| `stack_rules.yaml` | Protocol-stack invariants for sanity checking |
| `healthchecks.yaml` | Per-component health checks with disambiguation logic |
| `baselines.yaml` | Legacy healthy baselines + metric descriptions (now superseded by `metrics.yaml` for v6/v7) |
| `metrics.yaml` | **Metric KB** — per-metric `fault_layer`, `healthy` invariants, alarm predicates, `agent_exposed` flag; consumed by `agentic_ops_common.metric_kb` for trigger evaluation and event aggregation |
| `topology.yaml` | Component adjacency for path-walk reasoning (v7 Phase 0.6) |

Query API: `network_ontology/query.py` — `OntologyClient` with `diagnose()`, `match_symptoms()`, `check_stack_rules()`, `get_healthcheck()`, `get_all_flows()`, etc. Used by v5/v6/v7 and the GUI flows/topology APIs.

After editing any ontology YAML, re-seed:

```bash
# From the GUI: Stack → Re-seed Ontology
# Or:
./scripts/reseed-ontology.sh
```

See `docs/network-ontology-brainstorm.md` for design and `docs/ADR/v5_6phase_pipeline.md` / `agentic_ops_v6_plan.md` / `path_prioritizer_walks_all_candidates.md` / `blast_radius_downstream_impact_phase8.md` for how each generation consumes it.

---

## E2E VoNR Voice Test

End-to-end voice calls use UERANSIM (5G UE + gNB) with pjsua (PJSIP) for SIP/voice. Kamailio is reconfigured from IMS-AKA to SIP Digest auth for testability — pjsua doesn't speak IMS-AKA/Milenage and doesn't support IPsec SA negotiation.

| File | Change vs. upstream | Why |
|------|---------------------|-----|
| `kamailio/pcscf/pcscf.cfg` | `WITH_IPSEC` commented out | pjsua doesn't do IPsec SA negotiation |
| `kamailio/scscf/scscf.cfg` | `REG_AUTH_DEFAULT_ALG` = `"MD5"` | pjsua uses SIP Digest, not IMS-AKA |

Originals are never touched in place; the teardown script restores them.

### Data path

```
pjsua → uesimtun1 (IMS APN) → UERANSIM nr-ue → gNB → AMF/UPF → P-CSCF → IMS
```

Nothing bypasses the core. SIP and RTP both traverse the full 5G stack.

### Test subscribers (defined in `e2e.env`)

|  | UE1 (caller) | UE2 (callee) |
|--|--------------|--------------|
| IMSI | 001011234567891 | 001011234567892 |
| MSISDN | 0100001111 | 0100002222 |
| Container IP | 172.22.0.50 | 172.22.0.51 |

---

## Directory Structure

```
agentic-network-ops/
├── gui/                          # aiohttp + vanilla JS multi-page GUI
│   ├── server.py                 # REST + WebSocket handlers, page routing
│   ├── templates/                # topology / dashboard / flows / investigate / stack
│   ├── static/                   # CSS, D3-based topology renderer, flow animator
│   ├── metrics.py                # Prometheus + kamcmd + rtpengine-ctl collector
│   └── topology.py               # Ontology → YAML → fallback topology builder
│
├── agentic_ops/                  # v1.5 — Pydantic AI single agent
├── agentic_ops_v2/               # v2  — 4-phase ADK pipeline
├── agentic_ops_v3/               # v3  — context-isolated multi-phase
├── agentic_ops_v4/               # v4  — topology-aware multi-phase
├── agentic_ops_v5/               # v5  — 7-phase ontology-powered + anomaly screener
├── agentic_ops_v6/               # v6  — parallel multi-hypothesis investigators
├── agentic_ops_v7/               # v7  — determinism-first 8-phase + path walking + blast radius
│   ├── orchestrator.py
│   ├── subagents/                # network_analyst, instruction_generator, investigator,
│   │                             # path_walk_investigator, correlation_analyzer, event_aggregator,
│   │                             # ontology_consultation, synthesis, impact_narrator
│   ├── guardrails/               # 20+ mechanical validators (ig_validator, probe_grounding,
│   │                             # evidence_citations, investigator_consensus, synthesis_pool, …)
│   ├── path_prioritizer.py       # Deterministic flow scoring
│   ├── symptom_classifier.py     # KB-driven transport/application/mixed classification
│   ├── blast_radius.py           # Phase 8: deterministic downstream-impact compute
│   └── model_config.py           # pro + flash model slots (env-overridable)
│
├── agentic_ops_common/           # Shared across v6 / v7 (adoptable elsewhere)
│   ├── metric_kb/                # metrics.yaml loader, trigger eval, EventStore
│   ├── anomaly/                  # River + PyOD screener, preprocessor
│   ├── correlation/              # Event → ranked composite-hypothesis engine
│   ├── path_walk/                # Kernel + bridge hop probers
│   ├── rag/                      # Past-episode retriever (TF-IDF)
│   ├── tools/                    # 30+ KB-filtered agent tools
│   └── models/                   # Shared trace schema
│
├── agentic_chaos/                # Fault-injection + RCA-challenge framework
│   ├── cli.py                    # list-scenarios / run / list-episodes / show-episode / heal-all
│   ├── orchestrator.py           # baseline → inject → observe → challenge → score → heal → record
│   ├── fault_registry.py         # SQLite-backed triple-lock safety
│   ├── scorer.py                 # LLM judge (weighted rubric)
│   ├── recorder.py               # Episode JSON + markdown
│   ├── scenarios/library.py      # 14 pre-built scenarios
│   ├── agents/                   # baseline, fault_injector, escalation, observation_traffic,
│   │                             # control_plane_traffic, fault_propagation_verifier,
│   │                             # challenger, healer, call_setup
│   └── tools/                    # docker_tools, network_tools (tc/iptables), application_tools, …
│
├── anomaly_trainer/              # `python -m anomaly_trainer --duration 600`
│   ├── traffic.py                # SIP REGISTER + VoNR call generator
│   ├── collector.py              # 5 s metric polling → River model
│   └── persistence.py            # Save/load trained model
│
├── rag_indexer/                  # `python -m rag_indexer` — rebuild rag_index/ from agent_logs/
├── rag_index/                    # Persisted TF-IDF index (rebuilt; .bak.<UTC>/ snapshots)
│
├── common/                       # Cross-component utilities (e.g. stack_health, auto-heal)
│
├── network/                      # Open5GS-based 5G SA + IMS stack (submodule overlay)
│   ├── sa-vonr-deploy.yaml       # Core + IMS (17 containers)
│   ├── nr-gnb.yaml               # gNB
│   ├── base/                     # Open5GS Dockerfile (with GTP-U counter patch)
│   ├── ims_base/                 # Kamailio Dockerfile
│   └── .env                      # Topology env (IPs, MCC/MNC, subnets)
│
├── network_ontology/             # Neo4j-backed network knowledge graph
│   ├── data/                     # 13 YAML files (components, flows, metrics, deployment, …)
│   ├── schema/                   # Neo4j constraints
│   ├── loader.py                 # Seeds Neo4j from YAML
│   ├── query.py                  # OntologyClient — query API
│   ├── __main__.py               # CLI entry
│   └── Dockerfile                # One-shot loader container
│
├── grafana/
│   ├── dashboards/               # Custom dashboards (5G core; IMS planned)
│   └── custom_dashboards.yaml
│
├── kamailio/                     # Modified P-CSCF / S-CSCF configs for SIP Digest auth
├── ueransim/                     # pjsua-enabled UE image + per-UE init scripts
├── e2e-vonr.yaml                 # Compose: test UEs
├── e2e.env                       # Test subscriber credentials
│
├── network-ops.yaml              # Compose: Neo4j ontology + one-shot loader
├── grafana-dashboards.yaml       # Compose overlay for custom Grafana dashboards
├── ops.env.example               # Template for ops.env (GCP project, Gemini config, Neo4j)
│
├── scripts/
│   ├── e2e-vonr-test.sh             # Full deploy + e2e voice-test super-script
│   ├── post-deploy-verify.sh        # Toolbelt audit + Diameter fix + health + GTP counters
│   ├── audit-container-tooling.sh   # Verifies each NF has required diagnostic binaries
│   ├── run-all-chaos-scenarios.sh   # Batch-run all 14 scenarios against one agent version
│   ├── rebuild_rag_index.py         # Rebuild rag_index/ from agent_logs/
│   ├── migrate_baselines_to_metric_kb.py   # baselines.yaml → metrics.yaml migration
│   ├── reseed-ontology.sh           # Reload Neo4j from YAML (~3 s, no image rebuild)
│   ├── deploy-ontology-db.sh        # Bring up Neo4j alone
│   ├── deploy-ues.sh                # Deploy UEs against an existing stack
│   ├── build.sh / provision.sh      # Build base images / provision test subscribers
│   ├── run-e2e-vonr.sh              # Thin wrapper around e2e-vonr-test.sh
│   ├── teardown-ues.sh              # UE containers only
│   ├── teardown-stack.sh            # Core + IMS + gNB
│   ├── teardown-ops.sh              # GUI + Neo4j (--purge wipes Neo4j data)
│   └── teardown.sh                  # Everything
│
└── docs/
    ├── ADR/                      # Architecture decision records (60+ ADRs)
    ├── RCAs/                     # Post-run root cause analyses
    ├── critical-observations/    # Notable chaos run observations
    ├── bugs/                     # Bug investigations
    ├── runbooks/                 # Operational runbooks
    ├── plans/                    # Feature/implementation plans
    └── blog/                     # Long-form writeups
```

---

## Where to Look Next

- **Want to read why v7 is structured the way it is?** Start with `docs/ADR/agentic_ops_v6_plan.md`, then `path_prioritizer_walks_all_candidates.md`, `ig_probe_grounding_metric_inventory_and_liveness.md`, and `blast_radius_downstream_impact_phase8.md`.
- **Want to understand the ontology design?** `docs/network-ontology-brainstorm.md` and `docs/ontology-rework-plan.md`.
- **Want to see real RCA episodes?** `agentic_ops_v7/docs/agent_logs/` (most recent + most informative) and `agentic_ops_v6/docs/agent_logs/`.
- **Want to add a new chaos scenario?** `agentic_chaos/scenarios/library.py` — append a `Scenario(...)`, then `python -m agentic_chaos list-scenarios` to confirm it shows up.
- **Hit a stale Diameter peer or stuck registration after deploy?** Re-run `./scripts/post-deploy-verify.sh` — auto-heals up to 3 times.
