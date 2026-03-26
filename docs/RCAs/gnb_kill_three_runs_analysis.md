# When an AI Troubleshooting Agent Can't See a Dead Radio Tower

*Three attempts to diagnose a killed gNB — and what they reveal about how AI agents reason (and fail to reason) about network failures.*

---

## The Setup

We're building AI agents that troubleshoot a live 5G SA + IMS network stack — the kind that runs voice-over-NR (VoNR) calls. The stack has ~20 Docker containers: a 5G core (AMF, SMF, UPF), an IMS layer (P-CSCF, I-CSCF, S-CSCF, PyHSS), and a simulated radio network (gNB + two UEs).

To test how well these agents diagnose faults, we built a chaos testing platform that injects controlled failures and then unleashes the agent on the broken stack. The agent sees metrics, logs, configs, and can run diagnostic commands — but it has to figure out what's wrong on its own.

For this test, we simulated the most basic radio failure: **we killed the gNB container**. In a real network, this is equivalent to a cell tower going offline. Every UE loses connectivity. Every call drops. It's the most fundamental failure in a mobile network.

Here's the catch: **the agent doesn't have direct access to the gNB or UE containers.** This simulates a real NOC (Network Operations Center) boundary — the operator manages the core and IMS infrastructure, but the RAN is on the other side of the fence. The agent must infer that the gNB is down from core-side evidence.

A human engineer would look at the AMF metrics, see `ran_ue = 0` and `gnb = 0`, and say: "The gNB is gone." It takes about three seconds. Let's see how the AI agent did.

---

## The Evidence (What the Agent Could See)

Across all three runs, the agent had access to these signals:

**Metrics:**
- `AMF: ran_ue = 0` — zero UEs attached (normally 2)
- `AMF: gnb = 0` — zero gNBs connected (normally 1)
- `SMF: sm_sessionnbr = 0` (or 4 in the first run — stale sessions)
- `UPF: gtp_indatapktn3upf = 14872` — GTP counter frozen (no new traffic)
- `P-CSCF: registered_contacts = 0` — no IMS registrations

**Logs (from core containers):**
- `[amf] gNB-N2[172.22.0.23] connection refused!!!`
- `[smf] ERROR: No N1N2MessageTransferRspData [status:504]`
- `[icscf] ERROR: peer_connect(): Connection refused / No route to host` (to HSS at port 3875)

**Available tools:**
- `check_tc_rules(container)` — check for network faults
- `measure_rtt(container, target_ip)` — ping between containers
- `check_process_listeners(container)` — check what's listening
- `read_running_config(container, grep)` — read config
- `get_network_status()` — check container states
- `get_nf_metrics()` — full metrics snapshot
- All the usual log reading and search tools

---

## Run 1: "The AMF Is Not Listening"

**Agent's conclusion:** The AMF is not listening on SCTP port 38412. The gNB can't connect because the AMF has a listener problem.

**What actually happened:** The agent read the AMF log `gNB-N2[172.22.0.23] connection refused!!!` and inverted the direction. This log means "the AMF tried to reach the gNB at 172.22.0.23 and was refused" — because the gNB is dead. The agent interpreted it as "the gNB tried to reach the AMF and was refused" — because the AMF isn't listening.

The TransportSpecialist ran `check_process_listeners("amf")` to verify its theory. The AMF *is* listening on SCTP/38412. But by that point, the agent was already committed to its hypothesis and somehow reconciled the contradictory evidence.

**What the agent should have done:** `measure_rtt("amf", "172.22.0.23")` — ping the gNB's IP from the AMF. Result: 100% packet loss. The gNB is unreachable. Case closed.

**Token cost:** 190,180 tokens. Time: 137 seconds. Score: 40%.

---

## Run 2: "It's a Reporting Issue"

**Agent's conclusion:** The `ran_ue = 0` metric is probably a reporting inconsistency, not a real failure. The real problem is the I_Open Diameter state between I-CSCF and HSS.

**What actually happened:** In this run, stale PDU sessions (4) were still present because the implicit deregistration timers hadn't expired yet. So the agent saw `ran_ue = 0` but `sm_sessionnbr = 4` and concluded the metrics were inconsistent rather than recognizing the signature of an abrupt RAN failure: sessions linger because there was no graceful teardown.

The TransportSpecialist made **15 tool calls** — measuring RTT between every pair of IMS containers (pcscf↔icscf↔scscf) in every direction. All sub-millisecond. All completely irrelevant to a gNB failure. It never once tested reachability to 172.22.0.23.

The triage agent didn't even call `get_network_status()` — it only checked metrics, so it never discovered which containers were running.

**Token cost:** 100,440 tokens. Score: worse than Run 1 (I_Open ranked as primary cause above the gNB issue).

---

## Run 3: "The AMF Process Is Dead"

**Agent's conclusion:** The AMF process has crashed and cannot read its configuration file. This is the root cause of the total outage.

**What actually happened:** By this run, we waited for all stale sessions to expire. The metrics were clean: `ran_ue = 0`, `sm_sessionnbr = 0`, `registered_contacts = 0`. The CoreSpecialist tried `read_running_config("amf", grep="GNB_HOST")` — which returned nothing because Open5GS doesn't use a `GNB_HOST` parameter (it uses `ngap.server.address`). The agent interpreted "no config output" as "the AMF can't read its config file" and concluded the process was dead. The AMF was running fine the entire time.

The EndToEndTracer burned **170,890 tokens** — over 70% of the total budget — reading up to 2000 lines of P-CSCF and I-CSCF logs, tracing a stale SIP Call-ID through the IMS signaling chain. This had nothing to do with the gNB being down.

**Token cost:** 243,259 tokens. Time: unknown. Score: 0%.

---

## The Pattern

Three runs. Three different wrong conclusions. But the same underlying failure every time:

### The agent never pings the remote endpoint

When the AMF logs `connection refused` from IP 172.22.0.23, a human's first instinct is: "Is 172.22.0.23 even reachable?" The agent's first instinct is: "What's wrong with the AMF's configuration?"

The tool exists (`measure_rtt`). The IP is right there in the log. One call — `measure_rtt("amf", "172.22.0.23")` — would return 100% packet loss and immediately prove the gNB is unreachable. The agent never made this call across any of the three runs.

### The agent investigates where errors are logged, not the failure path

The TransportSpecialist checked tc rules and RTT on `amf`, `icscf`, `scscf`, `pcscf` — containers that are reporting errors. It never checked the path between the AMF and the gNB because the gNB isn't producing errors (it's dead — dead things don't log).

### The agent treats metrics as unreliable instead of reading them

A human sees `ran_ue = 0` and thinks "the RAN is down." The agent sees `ran_ue = 0` with `sm_sessionnbr = 4` and thinks "the metrics are inconsistent." The mismatch is actually the most diagnostic signal available — it's the fingerprint of an abrupt RAN failure where sessions persist because there was no graceful teardown.

### The agent's reasoning is inverted

"Connection refused from X" means X is unreachable. The agent reads it as "we refused X's connection." This directional inversion turns a clear signal into a misleading one and sends the investigation down the wrong path.

---

## What This Teaches Us About AI Agents in Network Operations

### 1. Tools aren't enough — diagnostic reflexes matter

The agent had every tool it needed. `measure_rtt` would have solved this in one call. But having a tool and knowing *when* to use it are different things. The agent lacks the diagnostic reflex that experienced engineers develop through years of troubleshooting: "If a connection is refused, verify the remote endpoint is reachable before investigating local configuration."

This reflex can't be reliably taught through prompts alone. We tried. The agent still doesn't do it. It may need to be enforced in code — a mandatory reachability check on any IP that appears in a "connection refused" or "connection timeout" error.

### 2. Bottom-up investigation is critical but hard to enforce

Every experienced network engineer knows: check the physical/network layer before the application layer. A dead container, a network partition, or injected latency will produce application-layer symptoms that look identical to misconfigurations. If you start at the application layer, you'll chase ghosts.

The agent knows this rule (it's in the prompt). It even has a "Network-First Law" in the TransportSpecialist. But when the triage hands it a list of application-layer errors (Diameter AVP failures, SIP registration timeouts), the agent follows the errors instead of the methodology.

### 3. The NOC boundary makes diagnosis harder — as it should

With full container visibility (Run 0, not shown here), the agent scored 100% in 23K tokens — it saw `nr_gnb: exited` and immediately concluded the gNB was down. Without that direct signal, the same fault becomes an inference problem, and the agent fails repeatedly.

This is realistic. Real NOC agents don't have SSH access to every cell tower. They must reason from core-side evidence. The fact that the agent can't do this reliably is a genuine capability gap, not a test design issue.

### 4. Token cost correlates with wrongness

| Run | Tokens | Score | Notes |
|-----|--------|-------|-------|
| Full visibility | 23,638 | 100% | Saw `nr_gnb: exited`, done |
| Run 1 (NOC view) | 190,180 | 40% | Wrong root cause, right component |
| Run 2 (NOC view) | 100,440 | ~20% | I_Open ranked above gNB |
| Run 3 (NOC view) | 243,259 | 0% | Fabricated AMF crash |

The more wrong the agent is, the more tokens it burns. When the answer is obvious, the pipeline is short and cheap. When the agent is confused, it spirals — reading thousands of log lines, tracing stale Call-IDs, measuring RTT between containers that aren't involved. Confusion is expensive.

---

## What We're Doing About It

This analysis surfaced three concrete improvements we're implementing:

1. **Mandatory reachability check**: When the agent encounters "connection refused" or "connection timeout" to an IP address, it must test reachability to that IP before investigating local configuration. This will be enforced in code, not just in prompts.

2. **Triage must call `get_network_status()`**: The triage agent should always check which containers are running, not just metrics. In two of three runs, it skipped this step entirely.

3. **Stale log filtering**: The observation system needs to filter logs to the current episode time window. Hours-old errors from previous test runs contaminated every investigation.

These are engineering fixes, not prompt tweaks. The lesson from these three runs is that you can't prompt your way out of missing diagnostic reflexes — you have to build them into the pipeline.

---

*This analysis is part of an ongoing evaluation of AI troubleshooting agents against a live 5G SA + IMS stack using controlled fault injection. The evaluation framework, agent architectures, and all episode logs are maintained in the [docker_open5gs](https://github.com/herlesupreern/docker_open5gs) repository.*
