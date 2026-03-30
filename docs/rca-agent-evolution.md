# The Evolution of the RCA Agent — v1.5 to v4

How the Root Cause Analysis agent went from a single-agent conversation loop to a topology-aware, context-isolated multi-agent pipeline — and the hard lessons from production runs that drove each change.

---

## The Big Picture

| Version | Framework | Architecture | Key Innovation |
|---------|-----------|-------------|----------------|
| v1.5 | Pydantic AI | Single agent, conversation loop | Rich toolset + structured methodology in prompt |
| v2 | Google ADK | Multi-agent sequential pipeline | Phased investigation with parallel specialists |
| v3 | Google ADK | Context-isolated multi-phase | Fresh session per phase — no reasoning leakage |
| v4 | Google ADK | Topology-aware, context-isolated | Network graph as first signal + mandatory transport |

Each version was born from failures of the previous one. The progression tells a story about what LLMs are good at (pattern recognition, following structured prompts) and what they're bad at (diagnostic discipline, bottom-up reasoning, knowing when NOT to use a tool).

---

## V1.5 — The Single Agent

**Framework:** Pydantic AI
**Model:** `google-vertex:gemini-2.5-pro`
**Architecture:** One agent, one conversation, all 13 tools available at once

### How It Works

V1.5 is conceptually simple: a single LLM agent with a detailed system prompt (`prompts/system.md`, 11KB) encoding a 6-step investigation methodology:

1. **Discover + Metrics** — call `read_env_config`, `get_network_status`, `get_nf_metrics` to get the lay of the land
2. **Rule Out Network Faults** — call `check_tc_rules` and `measure_rtt` before touching application logs
3. **Trace IMS Signaling** — follow the SIP call flow through P/I/S-CSCF
4. **Extract Call-ID** — search across all containers for a specific transaction
5. **Check Infrastructure** — Kamailio state, running configs, process listeners
6. **Disconfirm** — before concluding, actively try to prove yourself wrong

The agent runs in Pydantic AI's native agentic loop: the LLM decides which tools to call, calls them, reasons over results, calls more tools, and eventually produces a structured `Diagnosis` output (summary, timeline, root cause, affected components, recommendation, confidence, explanation).

### The 13 Tools

| Tool | Purpose |
|------|---------|
| `read_env_config` | Discover live topology: IPs, PLMN, subscriber identities |
| `get_network_status` | Container running/exited/absent status + stack phase |
| `get_nf_metrics` | Full metrics snapshot (Prometheus + kamcmd + PyHSS + MongoDB) |
| `query_prometheus` | Custom PromQL queries |
| `read_container_logs` | Recent logs from a single container |
| `search_logs` | Cross-container pattern search |
| `query_subscriber` | MongoDB (5G) and PyHSS (IMS) subscriber records |
| `check_tc_rules` | Detect injected network faults (netem latency, loss) |
| `measure_rtt` | Measure actual RTT between containers |
| `check_process_listeners` | Show what ports/protocols processes listen on |
| `read_config` | Read config file from repo |
| `read_running_config` | Read actual config from running container |
| `run_kamcmd` | Kamailio runtime inspection (Diameter peers, usrloc, stats) |

### What Worked

The v1.5 agent scored **90%** on the UE1-calls-UE2 failure scenario after adding `read_running_config` and `check_process_listeners` (the original v1 scored 10% without those tools). The detailed system prompt with known failure patterns gave the agent a strong starting point.

### What Broke

- **Context window bloat** — every tool result stays in the conversation, and the LLM re-reads the entire history on each round. With 13 tools and verbose container logs, token usage hit 200K+ on complex scenarios.
- **No methodology enforcement** — the 6-step process is advisory. The agent could (and did) skip straight to reading I-CSCF logs without checking metrics first.
- **No pruning** — the agent ran all tools whether relevant or not. No way to say "data plane is fine, skip GTP investigation."
- **gNB Kill: 0-40% across 3 runs** — the agent never pinged the dead gNB. It had `measure_rtt` but didn't know when to use it. Burned 190K-243K tokens investigating the wrong containers.

The core realization: **a single agent can't reliably follow a complex methodology**. The prompt says "check both ends" but the LLM anchors on the first interesting error it finds. You can't prompt-engineer discipline — you have to enforce it in code.

---

## V2 — The Multi-Agent Pipeline

**Framework:** Google ADK (Agent Development Kit)
**Models:** gemini-2.5-flash (triage, dispatch, transport, subscriber) + gemini-2.5-pro (tracer, IMS, core, synthesis)
**Architecture:** SequentialAgent with 5 phases, ParallelAgent for specialists

### The Design Leap

V2 splits the single agent into a **structured pipeline** of specialized agents:

```
Phase 0: Triage        → "Radiograph" of the stack
Phase 1: Tracer        → Map the request path, find the failure point
Phase 2: Dispatcher    → Decide which specialists to run
Phase 2b: Specialists  → 4 parallel domain experts (IMS, Transport, Core, Subscriber Data)
Phase 3: Synthesis     → Merge findings into final diagnosis
```

Each phase has its own prompt, its own tools, and its own output model. The dispatcher acts as a gatekeeper — it reads triage + trace results and selects which specialists are relevant, avoiding wasted work.

### Structured State, Not Conversation History

V2 introduces typed data models for inter-phase communication:

- **TriageReport:** `stack_phase`, `anomalies[]`, `metrics_summary`, `recommended_next_phase`
- **TraceResult:** `call_id`, `nodes_that_saw_it[]`, `nodes_that_did_not[]`, `failure_point`, `error_messages`
- **SubDiagnosis:** `finding`, `evidence[]`, `raw_evidence_context`, `root_cause_candidate`, `disconfirm_check`, `confidence`
- **Diagnosis:** Same as v1.5 output (backward compatible with GUI)

### Domain Laws

Each specialist operates under explicit "laws" encoded in its prompt:

**IMS Specialist:**
1. Handshake Law — Diameter Cx must be `R_Open`
2. Registry Law — S-CSCF must have active usrloc contact
3. Transaction Law — every INVITE must produce a Final Response
4. State Law — stale dialog state blocks new registrations

**Transport Specialist:**
1. Listener Law — no process on port = packet dropped
2. Protocol Match Law — TCP sender + UDP receiver = message dropped
3. Reachability Law — bad routing = no delivery
4. Fragmentation Law — large packets without fallback = vanished

**Core Specialist:**
1. Attachment Law — UE must be in AMF `ran_ue` list
2. Session Law — no data plane without SMF/UPF PFCP session
3. Tunnel Law — sessions exist but GTP packets = 0 means "zombied" tunnel
4. Policy Law — PCF must authorize or no media flows

**Subscriber Data Specialist:**
1. Consistency Law — IMSI/MSISDN must match in both databases
2. Provisioning Law — VoNR needs the UE in IMS HSS too
3. Location Law — PyHSS must have non-stale S-CSCF address
4. Security Law — auth algorithms must match

### Hierarchy of Truth (Synthesis)

When specialists disagree, synthesis resolves conflicts using:
1. **Transport > Application** — if transport proves a packet couldn't reach a node, ignore app-layer theories
2. **Core > IMS** — if core data plane is dead, that's the root cause of SIP timeouts
3. **Evidence > Theory** — config lines and DB records always beat "absence of logs"

### What Worked

- **Parallel specialists** — IMS, Transport, Core, Subscriber Data all run concurrently, reducing wall-clock time
- **Raw evidence context** — each specialist includes 10-20 raw log lines so synthesis can fact-check interpretations
- **Estimated 3.2x token reduction** vs v1.5 (50K vs 159K) due to scoped tool access per agent

### What Broke

- **Context accumulation** — all agents share one ADK session. By the time synthesis runs, the conversation history contains every tool output from every prior phase. The reasoning from triage leaks into the tracer's context, which leaks into specialists.
- **Hallucination cascades** — if triage misidentifies an anomaly, the tracer anchors on it, the dispatcher routes based on it, and the specialist investigates the wrong thing. The error propagates through the entire pipeline because every agent sees every prior agent's reasoning.

This led directly to v3.

---

## V3 — Context Isolation

**Framework:** Google ADK
**Models:** Same flash/pro split as v2
**Architecture:** Same 5-phase pipeline, but each phase runs in a **fresh ADK session**

### The Key Insight

V3 changes one thing, but it's the most important thing: **context isolation**.

Instead of running all agents in a single ADK session where conversation history accumulates, each phase gets a fresh `InMemorySessionService` session. The only data that flows between phases is the structured state dict — never raw tool outputs or LLM reasoning.

```python
async def _run_phase(agent, state, question, session_service, on_event=None):
    # Create FRESH session seeded with current state
    session = await session_service.create_session(
        app_name="troubleshoot_v3",
        user_id="operator",
        state=dict(state),  # Copy to avoid mutation
    )
    # Run agent in isolated session
    async for event in runner.run_async(...):
        # ... track tool calls, tokens ...

    # Read final state — merge ONLY output keys, discard conversation history
    final_session = await session_service.get_session(...)
    updated_state = {**state, **final_session.state}
    return updated_state, traces
```

### What This Means in Practice

- **Triage** writes `state["triage"]` (a distilled health report, not 50K of raw metrics)
- **Tracer** receives `state["triage"]` as context, runs its own tools, writes `state["trace"]`
- **Specialists** receive `state["triage"]` + `state["trace"]` + `state["dispatch"]`, but NOT the raw logs or reasoning from earlier phases
- **Synthesis** receives all findings but NOT the tool outputs that produced them — only the specialist's distilled `SubDiagnosis` with `raw_evidence_context`

Each agent operates on a clean slate. If triage misinterprets a metric, the tracer won't be biased by triage's reasoning — only by the structured triage output.

### Mandatory Transport Rule

V3 also introduces a hard-coded safety rule:

```python
# Transport specialist is ALWAYS included even if dispatcher doesn't select it.
# The LLM tends to miss network-layer issues.
if "transport" not in selected:
    selected.append("transport")
```

This was born from repeated failures where the dispatcher fixated on application-layer symptoms and never dispatched transport — the only agent that could detect `tc netem` rules or UDP/TCP mismatches.

### Results

- **HSS Unresponsive: 100%** — clean failure, unambiguous metrics, perfect diagnosis
- **P-CSCF Latency: 0%** — blamed HSS subscriber profiles instead of injected latency
- **gNB Kill: 0-40%** — still struggled with the same scenario that broke v1.5

The isolation helped prevent hallucination cascades, but didn't fix the fundamental problem: **the agent doesn't know what to look at first**. Metrics-first triage is good, but without network topology awareness, the agent can't see which physical paths are broken.

---

## V4 — Topology Awareness

**Framework:** Google ADK
**Models:** gemini-2.5-flash (triage, tracer, dispatcher, transport, subscriber) + gemini-2.5-pro (IMS, core, synthesis)
**Architecture:** Same context-isolated 5-phase pipeline, plus network topology as first-class data

### The Innovation: Network Graph First

V4 adds one tool to triage that changes everything: `get_network_topology()`.

This tool builds a live network graph from the running containers, showing every 3GPP interface (N2, N4, Gm, Cx, SBI, etc.) and classifying each link as **ACTIVE** or **INACTIVE** with reasons:

```
INACTIVE LINKS (2):
  N2: AMF → [RAN] [INACTIVE — [RAN] not connected]
  Gm: PCSCF → [UE] [INACTIVE — [UE] not responding]

ACTIVE LINKS (14):
  SBI: AMF → PCF [active]
  Cx: ICSCF → PyHSS [active]
  ...
```

The triage prompt instructs: **"Call `get_network_topology` FIRST. INACTIVE links are your primary triage signal — they tell you exactly which paths are broken without reading a single log line."**

This is the "radiograph before the scalpel" principle — see the whole picture before drilling into any specific component.

### What Changed from V3

| Aspect | V3 | V4 |
|--------|----|----|
| Triage tools | 4 (metrics only) | 5 (adds `get_network_topology`) |
| Triage prompt | Metric-focused baseline | Topology-first, then metrics |
| First signal | "Compare metrics to Golden Flow" | "INACTIVE links are primary triage signal" |
| Transport tools | 5 tools incl. `run_kamcmd` | 4 tools (`run_kamcmd` removed after hallucination) |
| Code location | `network/operate/agentic_ops_v3/` (inside submodule) | `agentic_ops_v4/` (parent repo) |

### Toolset Refinement

V4 also refined which tools each specialist gets, based on post-run analyses:

**Transport Specialist lost `run_kamcmd`** — in the first Data Plane Degradation run, the transport agent used `run_kamcmd` to query Kamailio SIP stats, then hallucinated a port 6060 mismatch on S-CSCF. SIP-layer tools in the transport specialist caused it to investigate the wrong layer. After removing `run_kamcmd`, transport tokens dropped from 33K to 14K and SIP hallucinations stopped.

### Results and Remaining Gaps

**gNB Radio Link Failure: 0%** — Triage correctly identified INACTIVE links at the RAN level. But downstream specialists ignored the correct triage finding and chased pre-existing P-CSCF noise. Good input data doesn't guarantee good output.

**Data Plane Degradation (2 runs): 0%** — The core specialist was never dispatched in either run. The dispatcher saw IMS metric deltas and jitter buffer resets and attributed them to the application layer. Without the core specialist, nobody checked UPF metrics or `tc` rules — the only places where the 30% packet loss was visible.

### Known Issues (as of latest runs)

1. **Core specialist not mandatory** — unlike transport, core isn't force-included. Data plane faults on the UPF are invisible without it.
2. **Dispatcher doesn't map data plane symptoms** — jitter buffer resets and GTP counter anomalies are textbook data plane indicators, but the dispatcher prompt doesn't explicitly connect them to the core specialist.
3. **Triage lacks `check_tc_rules`** — if triage checked tc rules on containers showing metric changes, it would catch `netem loss 30%` immediately during Phase 0, before the pipeline even reaches dispatch.
4. **Specialists can ignore triage** — in the gNB run, triage correctly identified INACTIVE RAN links, but the specialists anchored on different signals and produced wrong diagnoses anyway.

---

## The Lessons

### What the LLM is good at
- Following structured prompts with clear "laws" and domain rules
- Pattern-matching against known failure signatures (Diameter down, container paused)
- Synthesizing findings when given correct inputs and a hierarchy of truth
- Reading and interpreting metrics when told exactly what healthy looks like

### What the LLM is bad at
- **Diagnostic discipline** — it won't reliably follow a bottom-up methodology (check network before application) without code enforcement
- **Knowing when to use tools** — having `measure_rtt` and `check_tc_rules` doesn't mean the agent will use them at the right time
- **Distinguishing baseline from anomaly** — pre-existing conditions (httpclient:connfail at 1,386) get treated as fault symptoms
- **Bottom-up reasoning** — the LLM is attracted to interesting application-layer errors and skips boring network checks
- **Absence as evidence** — "INVITE never reached UE2" is harder to detect than "UE2 rejected INVITE with 403"

### The meta-pattern

Every version change follows the same pattern:

1. Run the agent against a scenario
2. Watch it fail in a specific, instructive way
3. Realize the failure is structural, not prompt-fixable
4. Change the architecture to make that class of failure impossible

V1.5 → V2: "The agent can't follow a 6-step methodology" → **enforce phases in code**
V2 → V3: "Agents contaminate each other's reasoning" → **isolate sessions**
V3 → V4: "The agent can't see which paths are broken" → **give it the network graph**
V4 → ???: "The dispatcher doesn't select the right specialists" → **make core mandatory, add `check_tc_rules` to triage**

The architecture gets better not by making the LLM smarter, but by **removing the opportunities for it to be wrong**.

---

## File Locations

| Component | V1.5 | V2 | V3 | V4 |
|-----------|------|----|----|-----|
| Agent code | `agentic_ops/` | `network/operate/agentic_ops_v2/` | `network/operate/agentic_ops_v3/` | `agentic_ops_v4/` |
| Orchestrator | `agent.py` (Pydantic AI loop) | `orchestrator.py` | `orchestrator.py` | `orchestrator.py` |
| Tools | `tools.py` (13 tools) | `tools.py` (11 wrappers) | `tools.py` (11 wrappers) | `tools.py` (12 wrappers) |
| Prompts | `prompts/system.md` (1 file) | `prompts/*.md` (8 files) | `prompts/*.md` (8 files) | `prompts/*.md` (8 files) |
| Agent definitions | N/A (single agent) | `agents/` (8 files) | `agents/` (8 files) | `agents/` (8 files) |
| Data models | `models.py` | `models.py` | `models.py` | `models.py` |
| Run logs | `docs/agent_logs/` | `docs/agent_logs/` | `docs/agent_logs/` | `docs/agent_logs/` |
| GUI endpoint | `/ws/investigate` | `/ws/investigate-v2` | `/ws/investigate-v3` | `/ws/investigate-v4` |
