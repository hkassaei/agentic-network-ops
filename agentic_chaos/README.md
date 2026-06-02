# Agentic Chaos

Controlled fault-injection platform for the 5G SA + IMS Docker stack. Injects faults, observes symptoms, records structured episodes, and **blindly** challenges an RCA agent to diagnose the failure — then scores that diagnosis against ground truth.

See the top-level [README](../README.md) for the broader system (network stack, GUI, ontology, agent generations). This document covers the chaos framework itself.

## Architecture

```
ChaosDirector (SequentialAgent)
  │
  ├── 1. BaselineCollector             → Pre-fault metrics + container status snapshot
  ├── 2. FaultInjector                 → Target → Inject → Verify (per fault)
  ├── 3. SymptomObserver               → Generate traffic, poll metrics/logs
  │       ├── ObservationTrafficAgent      (randomized SIP REGISTER + VoNR calls)
  │       ├── SymptomPoller                (detect propagation)
  │       └── EscalationChecker            (Boiling Frog: ramp severity if no symptoms)
  ├── 4. FaultPropagationVerifier      → Did the fault reach metrics/logs?
  ├── 5. ChallengeAgent                → Invoke RCA agent (v1.5–v7), score diagnosis
  ├── 6. Healer                        → Reverse every fault via SQLite registry
  └── 7. EpisodeRecorder               → Write episode JSON + markdown to disk
```

## Quick Start

Run from the **repo root** with the chaos venv activated.

```bash
cd $HOME/agentic-network-ops

# One-time venv setup
python3 -m venv agentic_chaos/.venv
source agentic_chaos/.venv/bin/activate
pip install -r agentic_chaos/requirements.txt

# Gemini / Vertex credentials (or source ops.env, which sets these)
set -a; source ops.env; set +a
```

The CLI:

```bash
# List the 14 pre-built scenarios
python -m agentic_chaos list-scenarios

# Run a scenario against an RCA agent version (v1.5 / v3 / v4 / v5 / v6 / v7)
python -m agentic_chaos run "DNS Failure"   --agent v7
python -m agentic_chaos run "P-CSCF Latency" --agent v6

# Skip the LLM call when faults don't propagate (saves Gemini tokens)
python -m agentic_chaos run "AMF Restart (Upgrade Simulation)" --agent v7 --abort-on-unpropagated

# Inspect recorded episodes (searches every agent_logs/ directory)
python -m agentic_chaos list-episodes
python -m agentic_chaos show-episode run_20260527_210520_mongodb_gone

# Emergency: heal everything still in the SQLite registry
python -m agentic_chaos heal-all

# Verbose
python -m agentic_chaos -v run "P-CSCF Latency" --agent v7
```

### Batch — run every scenario against one agent version

```bash
./scripts/run-all-chaos-scenarios.sh v7
./scripts/run-all-chaos-scenarios.sh v7 --abort-on-unpropagated
```

The batch runner sources `ops.env`, audits the diagnostic toolbelt across NFs (refuses to run if any NF is missing required probe binaries), iterates all 14 scenarios, and prints a final pass/fail table. The per-scenario `Healer` restores stack state between scenarios — no external redeploy needed.

## 14 Pre-Built Scenarios

| # | Scenario | Category | Blast Radius | What It Does |
|---|----------|----------|--------------|--------------|
| 1 | gNB Radio Link Failure | RAN | single | Kill gNB — UEs lose radio |
| 2 | P-CSCF Latency | IMS | single | Network latency on SIP edge proxy (escalating) |
| 3 | S-CSCF Crash | IMS | single | Kill SIP registrar / call controller |
| 4 | HSS Unresponsive | IMS | single | Pause PyHSS — Diameter Cx timeouts |
| 5 | Data Plane Degradation | core | single | Packet loss on UPF N3 |
| 6 | P-CSCF Packet Loss | IMS | single | Loss on SIP edge proxy |
| 7 | Call Quality Degradation | core | single | RTP-path packet loss (audible degradation) |
| 8 | RTPEngine Latency Injection | IMS | single | Media-plane latency via RTPEngine |
| 9 | UPF Bandwidth Cap | core | single | Bandwidth-limit N3 |
| 10 | MongoDB Gone | infra | global | Kill 5G subscriber datastore |
| 11 | DNS Failure | infra | global | Kill DNS — IMS service routing breaks |
| 12 | IMS Network Partition | IMS | multi | iptables partition: P-CSCF ↔ I/S-CSCF |
| 13 | AMF Restart (Upgrade Simulation) | core | single | Stop AMF temporarily |
| 14 | Cascading IMS Failure | IMS | multi | Kill HSS + latency on S-CSCF |

> Scenarios describe the **simulated failure mode** (what it looks like from outside), not the injection mechanism. RCA agents must diagnose the failure mode — the scorer evaluates against that, not against `container_kill` vs. `tc netem` vs. `iptables`.

Add a new scenario by appending a `Scenario(...)` in `scenarios/library.py`, then `python -m agentic_chaos list-scenarios` to confirm.

## Fault Types

```
CONTAINER                  NETWORK                    APPLICATION
─────────                  ───────                    ───────────
container_kill             network_latency            config corruption
container_stop             network_loss               subscriber deletion
container_pause            network_corruption         collection drop
container_restart          network_bandwidth
                           network_partition
```

Implementations live in `tools/docker_tools.py` (container actions), `tools/network_tools.py` (`tc netem`, `iptables` via `nsenter`), and `tools/application_tools.py` (app-level corruption).

## Safety: The Triple Lock

Every fault is protected by three independent mechanisms:

1. **SQLite registry** — Each fault is recorded **before** injection alongside its heal command. If injection fails, the row is cleaned up.
2. **TTL reaper** — A background task auto-heals faults that exceed their TTL (default 120 s; long-running scenarios override to 600 s).
3. **Signal handlers** — On SIGINT / SIGTERM / process exit, all live faults are healed synchronously. `heal-all` is the manual escape hatch.

The registry persists at `agentic_chaos/state.db` and survives process crashes; on next CLI invocation, leftover faults are surfaced and healable.

## Adaptive Escalation (Boiling Frog)

When `escalation=True` on a scenario, severity ramps progressively until symptoms appear:

```
Iteration 1: latency 100 ms → no symptoms → escalate
Iteration 2: latency 250 ms → no symptoms → escalate
Iteration 3: latency 500 ms → SIP T1 timer hit → SYMPTOMS DETECTED
```

This discovers the exact threshold at which protocols break. Used by `P-CSCF Latency` and other latency/loss scenarios.

## Challenge & Scoring

Every `run` invokes the configured RCA agent (`--agent`) after symptoms appear. The agent receives a **blind** prompt: *"The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause."* — no hints about what was injected.

An LLM judge (Gemini via Vertex) then compares the diagnosis against the simulated failure mode using a weighted rubric:

| Component | Weight |
|-----------|-------:|
| Root cause | 40% |
| Affected-components overlap | 25% |
| Severity | 15% |
| Fault type / failure mode | 10% |
| Confidence calibration | 10% |

Scores land in the episode under `challenge_result.score`.

## Episode Recording

Each run produces a structured JSON episode **plus** a human-readable markdown report. Episodes are written to the agent's logs directory:

```
agentic_ops_v1.5/docs/agent_logs/   (v1.5 is at agentic_ops/docs/agent_logs/)
agentic_ops_v3/docs/agent_logs/
agentic_ops_v4/docs/agent_logs/
agentic_ops_v5/docs/agent_logs/
agentic_ops_v6/docs/agent_logs/
agentic_ops_v7/docs/agent_logs/
```

(The legacy `agentic_chaos/episodes/` directory contains historical test-fixture episodes and is kept for backward compatibility; the active write path is per-agent.)

Episode JSON shape (abbreviated):

```json
{
  "schema_version": "1.0",
  "episode_id": "run_20260527_210520_mongodb_gone",
  "scenario": { "name": "MongoDB Gone", "category": "infra", "blast_radius": "global" },
  "baseline":  { "metrics": {...}, "container_status": {...} },
  "faults":    [{ "verified": true, "mechanism": "docker kill mongo", "ttl_seconds": 600 }],
  "observations": [{ "symptoms_detected": true, "metrics_delta": {...} }],
  "resolution": { "heal_method": "registry" },
  "rca_label":  { "root_cause": "...", "failure_domain": "infrastructure" },
  "challenge_result": {
    "diagnosis": { ... },
    "score": { "total_score": 0.87, "root_cause": 0.95, ... }
  }
}
```

These episodes also feed the **RAG case index** (see `rag_indexer/` at repo root): high-scoring runs become similar-case retrieval material for v7's RAG phase.

## Testing

```bash
# Unit tests (no Docker required)
python -m pytest agentic_chaos/tests/ -v -k "not e2e and not functional"

# Full suite — requires the stack running + Gemini credentials
python -m pytest agentic_chaos/tests/ -v
```

## GUI Integration

The GUI surfaces active faults on the topology overlay:

```
GET /api/chaos/faults  →  [{"fault_id": "...", "target": "pcscf", "fault_type": "network_latency", ...}]
```

Wired in `gui/server.py:handle_active_faults`. Faults appear as red badges on the topology while live.

## Prerequisites

- Python 3.10+ (venv at `agentic_chaos/.venv`)
- The 5G SA + IMS stack running (see top-level README — Deployment Guide)
- Docker + passwordless `sudo` for `nsenter`, `tc`, `iptables`
- Gemini via Vertex AI (`GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, `GOOGLE_GENAI_USE_VERTEXAI=TRUE`)
- `ANTHROPIC_API_KEY` only if you want to run `--agent v1.5` with Claude (everything else uses Gemini)
