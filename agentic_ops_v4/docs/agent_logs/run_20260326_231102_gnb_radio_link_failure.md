# V4 Agent Analysis — gNB Radio Link Failure

**Scenario:** gNB Radio Link Failure (gNB container killed)
**Date:** 2026-03-26
**Agent:** v4 (topology-aware, context-isolated multi-agent)
**Tokens:** 84,126 | **Duration:** 101s | **Tool calls:** 13 | **LLM calls:** 19

## Pipeline Execution

| Phase | Duration | Tokens | Tool Calls | LLM Calls |
|-------|----------|--------|------------|-----------|
| Triage | 17.1s | 9,722 | 2 | 3 |
| EndToEndTracer | 19.5s | 33,110 | 5 | 6 |
| Dispatch | 9.1s | 3,210 | 0 | 1 |
| Transport | 23.4s | 23,687 | 5 | 5 |
| IMS | 23.3s | 5,953 | 1 | 2 |
| Core | 23.4s | 2,088 | **0** | 1 |
| Synthesis | 31.4s | 6,356 | 0 | 1 |

## The Big Win: Topology-Aware Triage

The topology tool transformed triage. It called `get_network_topology` first, immediately saw:

```
INACTIVE LINKS (4):
  Air Interface: [UE] → [RAN] [INACTIVE — [RAN] not connected]  (x2)
  N2 (NGAP): [RAN] → AMF [INACTIVE — [RAN] not connected]
  N3 (GTP-U): [RAN] → UPF [INACTIVE — [RAN] not connected]
```

Then correlated with metrics: `ran_ue = 0.0`, `gnb = 0.0`. The triage report correctly concluded: **"The primary issue is that the RAN is not connected to the 5G Core."**

Compare with v3's triage on the same scenario, which flagged "only 17 containers" and missed the RAN disconnection entirely. The topology tool is exactly the improvement we were going for.

## Where It Went Wrong

### 1. Core Specialist hallucinated evidence (the worst error)

The Core Specialist made **zero tool calls** — it never read a single config file. Yet it confidently stated:

> "The AMF configuration shows `ngap_ip_list` is set to `192.168.16.208`, but it should be on the `192.168.18.x` subnet"

The IP `192.168.16.208` doesn't exist anywhere in this stack. The AMF's actual ngap IP is `172.22.0.10`. The agent fabricated technical evidence to build a plausible-sounding but completely wrong diagnosis. The actual cause was simply: the gNB container was killed.

### 2. Specialists chased pre-existing noise instead of the actual fault

Two out of three specialists (Transport + IMS) focused on `httpclient:connfail = 1004` — the P-CSCF to SCP heartbeat issue that is a known pre-existing cosmetic problem. They spent 29K tokens (35% of total) investigating something that existed before the fault was injected. None of them investigated the RAN disconnection, which the triage had already correctly identified.

### 3. Tracer burned tokens on a dead trail

The tracer spent 33K tokens (39% of total budget) across 5 tool calls searching for SIP transactions that don't exist — there's no SIP traffic when the RAN is down. It should have recognized the triage already identified a RAN-level failure and that SIP tracing is irrelevant.

### 4. Final diagnosis was wrong

Synthesis produced two root causes:
- AMF misconfigured to listen on wrong subnet — **hallucinated, wrong**
- P-CSCF can't connect to SCP — **pre-existing noise, not the injected fault**

The actual answer: **"The gNB is absent, which severed the N2 and N3 interfaces."** The triage knew this but the pipeline lost it.

## V4 vs V3 on Same Scenario

| | V3 | V4 |
|---|---|---|
| Tokens | 114,713 | 84,126 (27% less) |
| Triage identified RAN issue | No | **Yes** |
| Correct root cause in final diagnosis | No | No |
| Hallucinated evidence | Yes (Diameter I_Open) | Yes (AMF ngap_ip) |

## Lessons / What Needs Fixing

### 1. Core Specialist must use tools before making claims
Making claims about config values with 0 tool calls is unacceptable. The specialist prompts need a rule: **"Never claim a config value without reading it with `read_running_config` or `read_config`. If you make a claim about a specific setting, you must show evidence from a tool call."**

### 2. Distinguish new faults from pre-existing noise
`httpclient:connfail = 1004` is a high accumulating counter, which screams "pre-existing." The triage should flag this pattern, and the dispatch should deprioritize it vs. the INACTIVE links which are the acute signal. A counter at 1004 didn't jump from 0 in the last few minutes — it's been accumulating since container startup.

### 3. Tracer should short-circuit on infrastructure failures
When triage identifies INACTIVE links at the RAN/infrastructure layer, tracing SIP transactions is pointless. The tracer prompt needs a rule: **"If triage shows INACTIVE links at the RAN or infrastructure layer, skip SIP tracing and report the topology finding directly as the trace result."**

## Bottom Line

The topology tool fixed the **input** — triage is now the strongest phase and correctly identified the RAN disconnection immediately. But the **pipeline squandered the good triage** — the downstream agents chased noise (httpclient) and hallucinated evidence (AMF IP) instead of following the triage's lead. The fix is in the specialist and tracer prompts, not the tooling.
