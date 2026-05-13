# ADR: Agent Tool Arguments Must Be Names, Not Network Addresses

**Date:** 2026-05-12
**Status:** Accepted (shipped same day; `measure_rtt` is the first and currently only enforcement point)
**Related:**
- Driving failure: [`../../agentic_ops_v7/docs/agent_logs/run_20260512_082224_hss_unresponsive.md`](../../agentic_ops_v7/docs/agent_logs/run_20260512_082224_hss_unresponsive.md) — HSS Unresponsive run where the Investigator hallucinated `172.22.0.8` as pyhss's IP, pinged the gNB (which is at that IP) instead, got clean RTT, and was led into a false diagnosis of "port-binding failure" with `medium` confidence. The diagnosis happened to land on the correct NF (pyhss) only because the re-investigation pipeline rescued it. The wrong-IP mistake added ~250K tokens of investigation overhead and forced multi-shot reconciliation to break a hallucinated-evidence tie.
- Companion analysis: [`../critical-observations/run_20260512_121509_hss_unresponsive.md`](../critical-observations/run_20260512_121509_hss_unresponsive.md) — the RAG-OFF half of the paired A/B which surfaced the IP-hallucination diagnosis.
- [`path_anchored_probe_planning_for_transport_layer_faults.md`](path_anchored_probe_planning_for_transport_layer_faults.md) — kernel-level transport diagnosis moved off the LLM and into the deterministic walker for similar reasons (LLM-judgment on container-naming was unreliable in v3's `TransportSpecialist`).
- [`structural_guardrails_for_llm_pipeline.md`](structural_guardrails_for_llm_pipeline.md) — general principle that load-bearing agent behavior must be enforced structurally, not by soft prompt rules. The names-only contract is a mechanical guardrail at the tool boundary.
- [`internal_taxonomy_must_not_leak_to_llm.md`](internal_taxonomy_must_not_leak_to_llm.md) — companion principle on what the LLM is allowed to see vs. produce.

---

## Decision

**No agent-facing tool argument may be a network address (IP, port, MAC, PID, file descriptor, etc.).** Every argument that identifies a system component or peer is a **name** drawn from the deployment topology. Where the underlying implementation requires an address, the tool resolves the name to an address at probe time — via DNS, configuration lookup, `docker inspect`, or whatever mechanism is appropriate — never by asking the LLM to provide the address.

Concretely, three coordinated changes shipped in this PR:

1. **`measure_rtt(container, target, ...)`** — the canonical first enforcement point. `target` is a container name; the docker network's embedded DNS at `127.0.0.11` resolves it inside the source container's `ping` invocation. The deprecated `target_ip` keyword alias remains for v1.5/v2 wrappers but is constrained the same way: IP-shaped strings are rejected regardless of which kwarg they came in on.
2. **`_looks_like_ip(value)`** — a mechanical IPv4-dotted-quad detector used to reject IP literals at the tool boundary with a corrective error that names the principle and points at this ADR.
3. **Names-only directive in the Investigator prompt** — `agentic_ops_v7/prompts/investigator.md` carries a one-paragraph rule under "Tool constraint" stating the principle in operator language, and the example invocation now reads `measure_rtt("pcscf", "icscf")` rather than `measure_rtt("pcscf", "172.22.0.19")`.

The contract is enforced at three layers:

| Layer | Mechanism | When it fires |
|---|---|---|
| Prompt | Names-only rule + name-shaped example | Before the LLM ever calls the tool — sets the right prior |
| Tool validation | `_looks_like_ip` + container-allowlist check | If the LLM still emits an IP, the tool rejects with a corrective error the LLM can read on the next sample |
| Test pinning | Parity test + unit tests | CI gate against accidental regression |

---

## Context

### The failure mode this closes

In `run_20260512_082224_hss_unresponsive`, the Investigator was assigned the hypothesis "HSS is unresponsive on Diameter Cx." The Instruction Generator's plan said `measure_rtt — from:'icscf', to:'pyhss'` — pyhss by **name**. The Investigator then made the call:

```python
measure_rtt(container='icscf', target_ip='172.22.0.8')
```

`172.22.0.8` is not pyhss — pyhss is at `172.22.0.18`. `172.22.0.8` is `nr_gnb`. The Investigator pinged nr_gnb, got a healthy reachability result (because gNB is reachable from icscf), and concluded "pyhss is reachable; the fault must be application-layer port-binding." This drove ~250K tokens of follow-up investigation and required the candidate-pool re-investigation pipeline to recover the correct NF.

The post-mortem traced this to three compounding structural choices:

1. **`measure_rtt`'s signature required a `target_ip: str`** with the docstring saying *"Target IP address to ping (e.g. '172.22.0.19')"*. The LLM read this as a hard contract: it must supply an IP.

2. **No tool in the Investigator's kit returns container IPs as primary output.** `get_network_status` returns container statuses (no IPs). `get_diagnostic_metrics` returns metric values. The only way to learn a container's IP is as a *side effect* of some other tool — `check_process_listeners` happens to surface bind addresses in its output strings. The agent must call a specific tool, in a specific order, before it can know any IP.

3. **The Investigator prompt's example showed `measure_rtt("pcscf", "172.22.0.19")`.** Per chance, `172.22.0.19` is pcscf's correct IP. The example teaches the LLM (a) IPs are in the `172.22.0.X` range and (b) IP literals are a legitimate way to specify the target. From there the LLM hallucinated a plausible-looking number for any other NF.

The result is a hallucination class that's mechanically inevitable: given a mandatory IP-typed argument and no reliable name→IP lookup, the LLM has to either remember from a prior call or guess. There is no third option, and "remember" requires probe-ordering discipline (read `check_process_listeners` *before* `measure_rtt`) the LLM doesn't reliably maintain.

### Why "let the agent see IPs in output but not produce them"

The principle is **asymmetric exposure**: the agent can *observe* IPs (when a tool returns them in its output text — `check_process_listeners` shows bind addresses, `get_diagnostic_metrics` may show source IPs in diagnostic strings) and can reason about them in its prose (a diagnosis recommendation may legitimately mention "pyhss at 172.22.0.18:3875"). What the agent **cannot do** is type an IP literal into any tool-call argument. The output channel is for human consumption; the tool-call channel is the structural contract.

This is the same shape as `internal_taxonomy_must_not_leak_to_llm.md` — the agent sees internal phase / decision labels in its scratch space but must not reference them in user-facing output. Here the direction is inverted: the agent sees IPs in tool output but must not use them in tool calls.

### Generalization

The driving failure was IPs, but the principle is broader: **any tool argument that identifies a discriminating component or resource is a name, not an address**. The full taxonomy:

| Argument kind | Today's status | Future enforcement |
|---|---|---|
| Container name | ✓ names-only (`container`, `target`, `nf`, etc.) | Stable |
| IP address | ✓ rejected at `measure_rtt` | Audit other tools |
| Container PID | Used internally (e.g. `_nsenter`) but never agent-facing | Stable |
| Network port number | Agent currently reads from `check_process_listeners` output; never writes one | Audit if any future tool adds a port argument |
| File path | Agent reads from `read_running_config` / `read_env_config` output; never writes one | Stable for now |
| qdisc handle / iptables chain | Agent never sees | Stable |

The audit step listed below will sweep agent-facing tools for any remaining cases where an LLM is asked to type a discriminating identifier other than a name.

---

## Design

### The IP-rejection contract

`measure_rtt(container, target, *, target_ip=None)` validates in this order:

1. **`container` must be in `deps.all_containers`.** Source container is always a name and was already validated.
2. **Reconcile `target` and the legacy `target_ip` alias.** If only `target_ip` is supplied, treat its value as `target`. If both are supplied with conflicting values, reject. If neither is supplied, reject.
3. **Mechanical IP-shape rejection.** `_looks_like_ip(target)` matches a dotted-quad of 1-3-digit numeric segments. If positive, reject with a corrective error that names the principle, gives an example call shape, and cites this ADR.
4. **`target` must be in `deps.all_containers`.** Catches typos and DNS aliases that aren't real containers.
5. **Toolbelt preflight.** `ping` must be installed in the source container; if not, return a `PROBE_TOOL_UNAVAILABLE` signal (same semantics as elsewhere).
6. **Issue the ping.** The shell command is `docker exec <container> ping -c N -i 0.1 -W 1 <target_name>`. The kernel resolves `<target_name>` via the container's `/etc/resolv.conf` (which docker writes to point at the embedded compose-network DNS at `127.0.0.11`).

The IP-rejection error message is deliberate:

```
target='172.22.0.18' looks like an IP literal. Pass a container NAME
instead (e.g. target='pyhss'). Container names are resolved to IPs by
the docker network's embedded DNS at probe time. If you don't know
which container owns this IP, infer it from a previous tool output
rather than guessing. (ADR: agent_tool_args_must_be_names_not_ips.md)
```

It names the principle (no IP literals), gives the corrective shape (pass a name), states the resolution mechanism (embedded DNS), prescribes the recovery if the agent thinks it needs an IP (read from a prior tool output, don't guess), and cites the ADR for further reference. On REJECT the LLM resamples; the corrective error appears in its context window via the standard tool-rejection feedback path.

### Why mechanical detection (regex), not strict IPv4 validation

The detector is `len(parts) == 4 and each part is 1-3 digits`. It accepts `999.999.999.999` (not a valid IP). This is intentional:

- The goal is to catch the LLM **typing something that looks like an IP**, not to validate IP correctness. A hallucinated near-IP like `172.22.0.99` is functionally the same failure mode whether or not `.99` exists on the network.
- False positives on real container names: a name like `1.2.3.4` would be rejected, but no legitimate container name in any deployment we work with is dotted-quad-shaped. Container names use letters, hyphens, underscores. The false-positive rate is structurally zero.

### Why `target_ip` is kept as a backward-compat alias

The shared `agentic_ops/tools.py:measure_rtt` is called from at least three places: the v1.5 wrapper in `agentic_ops/agent.py`, the v7 façade in `agentic_ops_common/tools/reachability.py`, and any external code that imports the function. Removing the `target_ip` kwarg outright would break those callers.

The compromise: accept both kwarg names; honor `target_ip=` only when `target=` is omitted; apply the IP-shape rejection to whichever value comes through. The deprecation does not affect agent-facing behavior (the agent sees only the v7 façade, which exposes `target`), and the alias gives external code an explicit migration path.

### Names-only directive in the Investigator prompt

A new paragraph under "Tool constraint" in `agentic_ops_v7/prompts/investigator.md`:

> **Every tool argument that identifies a component is a container NAME, not an IP address.** `measure_rtt(container='icscf', target='pyhss')` — both `container` and `target` are names; the underlying probe resolves names to IPs via the docker network's embedded DNS at runtime. You do not need to know any IP. If you find yourself reaching for an IP literal because "I think pyhss is at 172.22.0.X", stop — you would be hallucinating. Pass the container name and let the tool resolve it. IP literals are rejected at the tool boundary with a corrective error.

The wording is deliberate: it (a) states the rule mechanically, (b) gives a name-shaped example to overwrite any prior IP-shaped example the model may have absorbed, (c) calls out the failure mode by name (*"if you find yourself reaching for an IP literal because…"*), and (d) tells the agent the consequence of trying to bypass the rule.

### Test pinning

Three layers of test coverage:

- `agentic_ops_common/tests/test_measure_rtt_names_only.py` — 30 unit tests covering: IP-shape detector (positive and negative cases), IP-literal rejection on both `target` and `target_ip` kwargs, unknown source container, unknown target container, missing target, conflicting kwargs, the deprecated-alias backward-compat path, the happy path's shell-command shape (name in the ping invocation, no IP leak), the unreachable-message shape, and the `PROBE_TOOL_UNAVAILABLE` path.
- `agentic_ops_v7/tests/test_application_layer_parity_with_v6.py::test_v7_investigator_prompt_uses_names_not_ips_for_tool_args` — pins the names-only directive and forbids IP-shaped `measure_rtt(...)` examples in the v7 Investigator prompt.
- `agentic_ops_v7/tests/test_application_layer_parity_with_v6.py::_INTENTIONALLY_DIVERGENT` — adds `prompts/investigator.md` to the set of deliberately-divergent-from-v6 files, so the byte-for-byte parity check doesn't fail on the new directive.

---

## What this does NOT do

- **Does not remove IPs from tool *output*.** `check_process_listeners` still returns `tcp LISTEN 0 100 172.22.0.18:3875` in its observation text — that's a structural address surfaced by `ss`, and an operator reading the diagnosis benefits from seeing it.
- **Does not audit non-`measure_rtt` tools yet.** Other agent-facing tools are believed to be names-only already (the audit ran by hand: `check_tc_rules`, `check_process_listeners`, `get_diagnostic_metrics`, `get_network_status`, `run_kamcmd`, `read_running_config`, `query_subscriber`, `list_flows`, `get_flow`, `get_canonical_flows_through_component`, `get_active_flows_through_component`, `get_causal_chain`, `find_chains_by_observable_metric` — none take an IP argument). But a one-time audit is not the same as a permanent invariant — a follow-up should add a CI check that any *new* agent-facing tool's signature is reviewed for address-shaped arguments.
- **Does not address container-PID arguments.** PIDs are used internally (`nsenter -t <pid>`) but never asked of the LLM. A future telemetry-collection tool that wanted a PID argument would violate this principle; the audit should catch it.
- **Does not address IPs that appear in chaos-injection metadata.** Chaos faults like `network_partition` carry `target_ip` in their `params` dict. This is read by the chaos framework, not the agent — the agent never sees the fault metadata. No leak path.
- **Does not address ping latency for delay-only netem.** A separate concern (the KernelHopProber didn't catch the 60s delay on pyhss in the RAG-OFF run) that this ADR is independent of.

---

## Future work

### 1. Multi-homed container support

A container on multiple networks (e.g. `upf` is on `docker_open5gs_default` plus separate interfaces for N3 backhaul) has multiple IPs. `ping upf` resolves to the default-bridge IP only. For most diagnostic flows that's the right one, but a scenario that wants to test a specific non-default interface needs a way to express that.

**Right shape:** add an optional `target_interface: str` parameter — *still a name, still not an IP*. Example: `measure_rtt(container='smf', target='upf', target_interface='n3')`. The tool resolves `(upf, n3)` to the right IP via `docker inspect` or a deployment-topology lookup.

**Wrong shape (do not do):** allow IPs back as an escape hatch. The interface-name extension preserves the names-only invariant.

Defer until a scenario actually requires it. No current chaos scenario does.

### 2. External-reachability tool

If a future deployment tests connectivity to a real external service (e.g. cloud-hosted IMS peer, public DNS resolver, WAN gateway), a separate tool is needed. The current `measure_rtt` is scoped to **lab containers**. The right shape for the external case is:

```python
async def measure_external_reachability(
    container: str,                  # source name (as today)
    target_hostname: str,            # hostname or service name from the
                                     # deployment config — NOT an arbitrary
                                     # IP supplied by the LLM
) -> str: ...
```

The `target_hostname` is constrained to a deployment-configured allowlist (e.g. the configured external Cx peer, the configured upstream DNS server). The LLM picks from a known set; it doesn't write an IP or an arbitrary hostname. Same names-only principle, different lookup mechanism.

Defer until a scenario tests external reachability. Carrier-grade ADRs in the path-walk roadmap (BGP / IPsec / optical probers) will trigger this work.

### 3. Audit of all agent-facing tools for address-shaped arguments

The current audit was manual. A future PR should add a CI test that introspects every tool registered in any v-N agent's `tools=[...]` list, walks the function signature, and asserts no parameter named `*_ip`, `*_address`, `*_pid`, `*_port`, etc., is exposed without an exception in this ADR. The test is meant to fail loudly when a future contributor adds a new tool that accidentally re-introduces the pattern.

Mock signature for the eventual test:

```python
def test_no_agent_facing_tool_takes_an_address():
    forbidden_param_prefixes = ("ip_", "addr_", "address_", "pid_", "port_")
    forbidden_param_suffixes = ("_ip", "_addr", "_address", "_pid", "_port")
    exceptions = {
        # measure_rtt's deprecated `target_ip` alias is allowed because
        # the implementation rejects IP-shaped values at the tool boundary.
        ("measure_rtt", "target_ip"),
    }
    for tool in _all_agent_facing_tools():
        for name, param in inspect.signature(tool).parameters.items():
            if (name, tool.__name__) in exceptions:
                continue
            assert not any(name.startswith(p) for p in forbidden_param_prefixes)
            assert not any(name.endswith(s) for s in forbidden_param_suffixes)
```

### 4. Apply the same names-only rule to lesson / prior-case authoring

The RAG corpus carries `RetrievedCase` payloads with screener flag data, ground-truth NFs, and agent diagnoses. None currently leak IPs, but the lesson-authoring style guide should make this an explicit rule: lesson `rule:` and `applies_when:` fields name components and metrics, never IPs. The current 15-lesson corpus complies; future lessons must keep complying. Worth one line in `lessons.yaml`'s top-of-file comment.

### 5. Document the principle in the `agentic_ops_common` README

A short README section under `agentic_ops_common/tools/` titled "Names, not addresses" stating the principle and pointing at this ADR. Helps any future contributor adding a tool understand the convention before they reach for an IP argument out of habit.

---

## Acceptance evidence

- `agentic_ops_common/tests/test_measure_rtt_names_only.py`: **30/30 tests passing**.
- `agentic_ops_v7/tests/test_application_layer_parity_with_v6.py::test_v7_investigator_prompt_uses_names_not_ips_for_tool_args`: passing; pins the prompt directive and forbids future IP-shaped example regressions.
- Full v7 + common suite: **785 passed, 48 skipped, 3 xfailed**. The 3 xfailed remain the documented resolver-side B4-blocked cases; unrelated to this work.
- Manual review of `agentic_ops_v7/subagents/investigator.py:47-101` confirms no other agent-facing tool in the kit takes an IP argument.

---

## How to run the failing-case reproducer

To confirm the IP-rejection corrective signal in a live call:

```python
from agentic_ops import tools
class _D: all_containers = ["pcscf", "icscf", "pyhss"]
result = await tools.measure_rtt(_D(), container="icscf", target="172.22.0.18")
print(result)
# target='172.22.0.18' looks like an IP literal. Pass a container NAME
# instead (e.g. target='pyhss'). [...] (ADR: agent_tool_args_must_be_names_not_ips.md)
```

The error returns *in band* (as the tool's return value) so the LLM reads it on its next sample and can correct. There is no exception raised — the ADK probe loop sees a normal string return and the LLM is asked to retry with the corrective context. This matches the failure-feedback shape used elsewhere in the toolkit.
