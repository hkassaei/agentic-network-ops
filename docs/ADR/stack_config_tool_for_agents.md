# ADR: Deployment-Config Tool — Ground Agent Assumptions in Deployment Reality

**Date:** 2026-05-20
**Status:** Proposed
**Related:**
- Triggering episode: [`docs/critical-observations/run_20260520_190753_hss_unresponsive_gemini_hallunicated.md`](../critical-observations/run_20260520_190753_hss_unresponsive_gemini_hallunicated.md) — HSS Unresponsive scenario where the investigator hallucinated a second root cause ("HSS not listening on Diameter port 3868") because it defaulted to IANA-standard ports instead of the deployment's actual `PYHSS_BIND_PORT=3875`. The walker correctly localized the real fault (60s netem latency); the application-layer pipeline fabricated a phantom co-fault that propagated through multi-shot consensus, both Synthesis shots, and the compound-consistency guardrail.
- [`na_evidence_grounding.md`](na_evidence_grounding.md) — addresses a sibling failure mode (NA names NFs that aren't in the live evidence). This ADR addresses NA / IG / Investigator naming *deployment-configurable values* that don't match the stack's actual configuration.
- [`structural_guardrails_for_llm_pipeline.md`](structural_guardrails_for_llm_pipeline.md) — load-bearing pipeline behavior is enforced structurally. The fix here is partly a new tool (structural) and partly a prompt rule + lesson (soft) — both layers needed.
- Existing config-inspection tools at `agentic_ops_common/tools/config_inspection.py` — `read_config`, `read_running_config`, `read_env_config`. These exist and are in the investigator's toolset, but their shape (raw text dumps) and the absence of a prompt rule telling the agent *when* to consult them combined to make them silently unused on the triggering episode.

---

## Decision

Introduce a new agent-facing tool, `get_deployment_config(component)`, that returns a **structured, targeted lookup** of the deployment's actual configuration for one network function — ports, IPs, key dependencies, the source file the value came from. The tool is wired into both the InstructionGenerator and Investigator toolsets in v7.

Pair it with two coupled changes:

1. **A generalizable operational lesson** in `agentic_ops_common/rag/lessons.yaml` about the *class* of failure: service ports, IPs, and interface bindings are deployment-specific; the agent must consult the stack config via `get_deployment_config` before asserting a service is or is not bound to a port. **Deliberately not a hard-wired cheat-sheet entry** like "PyHSS uses 3875." Cheat-sheet lessons don't generalize across deployments, create a maintenance burden when the stack changes, and pollute the lesson corpus with stack-specific noise instead of teaching principle.

2. **A prompt rule in `agentic_ops_v7/prompts/investigator.md`**, written as pure principle (no specific episode, NF, or port reference), that requires the investigator to call `get_deployment_config` before asserting any service-bound-to-port claim and to trace every port / IP / container-name citation in its reasoning back to either a deployment-config call or the probe data itself.

The structural component (the tool) makes verification cheap. The lesson and prompt rule make consulting it habitual. Either alone is insufficient — without the tool, the existing `read_env_config` dumps the whole env file and the agent ignores it; without the rule, the tool is available but the agent's IANA prior wins.

We deliberately do not add a guardrail to *verify* the investigator's port claims post-emit — that's the right kind of structural check, but it requires either an LLM judge (re-introducing the variance the guardrail is supposed to bound) or a curated per-NF expected-port table (back to the cheat-sheet failure mode). Lower-cost path first: give the agent the right tool and tell it to use it.

## Context

### The failure mode

On `run_20260520_190753_hss_unresponsive`, the chaos scenario injected a single fault — 60-second outbound delay on PyHSS via `tc netem`. The walker correctly localized the fault at `pyhss[eth0]` with `latency_at_hop qdisc_netem_delay 60000.0 ms`. The orchestrator routed `mixed` (per the classifier), the application-layer pipeline ran, and the InstructionGenerator emitted a falsification plan for h1 that included this probe (run markdown line 311-312):

> *Expected if hypothesis holds:* A process is listening on the Diameter port (3868), but is internally stalled or unable to process requests.
> *Falsifying observation:* No process is listening on the Diameter port (3868), indicating the application did not bind its network socket.

The probe ran. `check_process_listeners` returned (line 357):

```
tcp LISTEN 172.22.0.18:3875  → python3 (pid=30)   ← Diameter listener (configured port)
tcp LISTEN 0.0.0.0:8080      → python3 (pid=22)   ← HSS HTTP API
tcp LISTEN 0.0.0.0:6379      → redis-server       ← Redis cache
```

This is exactly what a **healthy** PyHSS looks like in this stack: Diameter on 3875 bound to the right IP, REST API on 8080, Redis on 6379. The investigator looked at this and concluded the HSS isn't bound, then added a second root cause to the diagnosis — citing the same `check_process_listeners` output as evidence for a fault that doesn't exist.

The actual configuration:
- `network/.env`: `PYHSS_BIND_PORT=3875`
- `network/pyhss/config.yaml`: `bind_port: PYHSS_BIND_PORT` (template-substituted)

PyHSS's Diameter port in this deployment is 3875, not the IANA-standard 3868. The investigator had no way to know that without consulting the stack config — and didn't.

### Where the failure propagated

Five places, none of which caught it:

1. **Phase 4 IG plan** baked in the wrong port assumption (the falsifying-observation criterion mentions 3868 by name).
2. **Phase 5 multi-shot Investigators** both reached the same wrong conclusion on the same evidence.
3. **Phase 7 Synthesis** emitted `verdict_kind=compound` with the hallucinated finding as `additional_root_causes`.
4. **The compound-consistency guardrail** passed — the entry was structurally valid (cited `evidence_source: investigator`); the guardrail doesn't verify semantic correctness of the investigator's interpretation.
5. **The recommendation field** leaks the confusion to the operator: "investigate the pyhss application's logs and configuration to determine why it is not listening on the Diameter port 3868." A human following that recommendation chases a phantom.

### Why existing tools didn't help

The investigator's toolset already includes `read_env_config` and `read_running_config`. They were not used in this run. Two reasons:

1. **Shape mismatch.** `read_env_config()` returns the entire env file as raw text — dozens of lines, no targeting. To answer "what port should PyHSS be on?" the agent would have to read the whole file and search for the right variable. High cognitive load for a quick fact-check, easy to skip in favor of training-corpus priors.

2. **No prompt rule.** The investigator prompt doesn't include "before asserting a service is/isn't bound to a port, verify the deployment's actual port assignment." The IANA-standard prior wins by default.

The existing tools are honest about *exposing* the data; they aren't shaped for the *question* the agent needs to ask. That's the gap a new structured-lookup tool closes.

### Why this is a generalizable problem, not a one-off about port 3868

Every component in the stack has deployment-configurable values: ports, IPs, container names, interface names, dependency endpoints, credential paths. Any of these could be the target of a future investigator probe whose assertion ("X service is/isn't bound to Y") depends on knowing the configured value. Examples:

- `KAMAILIO_*` SIP listening ports
- `MONGO_HOST` / `MONGO_PORT` for UDR's database endpoint
- `RTPENGINE_NG_PORT` for the rtpengine control protocol
- `NRF_*`, `SMF_*`, `UPF_*` SBI endpoint configuration
- Container name overrides that differ from default `service_name` values

The triggering episode happens to be about Diameter 3868 vs. 3875. The pattern is much broader. A hard-wired lesson ("PyHSS uses 3875") closes the one specific instance. A tool + a generalizable lesson closes the class.

## Design

### The tool — `get_deployment_config(component)`

Signature:

```python
async def get_deployment_config(component: str) -> dict[str, Any]:
    """Return the deployment-configured values for one network component.

    Consolidates three existing sources of truth into one structured,
    targeted lookup:
      1. `network/.env` — template variables (PYHSS_BIND_PORT, PYHSS_IP, ...)
      2. `network/<component>/config.yaml` — service config with env
         vars substituted, returning the *resolved* values
      3. `network_ontology/data/deployment.yaml` — existing per-component
         deployment bindings (ip_env_key, container_name)
      4. `network_ontology/data/deployment_metadata.yaml` — new file
         (this ADR) carrying per-component port semantics: which
         configured port serves which protocol / role

    Returns a structured dict keyed by stable field names:
        {
            "component": "pyhss",
            "container_name": "pyhss",
            "ip": "172.22.0.18",
            "listening_ports": [
                {
                    "port": 3875,
                    "transport": "tcp",
                    "purpose": {
                        "protocol": "diameter",
                        "interface": "cx",
                        "role": "server",
                    },
                    "source": "network/.env: PYHSS_BIND_PORT",
                },
                {
                    "port": 8080,
                    "transport": "tcp",
                    "purpose": {
                        "protocol": "http",
                        "interface": "rest_api",
                        "role": "server",
                    },
                    "source": "network/pyhss/config.yaml: api.bind_port",
                },
            ],
            "config_files": [
                "network/.env",
                "network/pyhss/config.yaml",
            ],
        }

    The `purpose` field is the load-bearing one — structured key:value
    pairs (protocol / interface / role) rather than a flat tag string
    let the agent answer questions like "which port serves the Cx
    interface on this NF?" with a deterministic lookup that doesn't
    depend on IANA priors. The structured shape also leaves room for
    future fields (e.g. `direction`, `peer_role`) without breaking
    the schema.

    Source attribution per port (`source` field) tells the agent — and
    the operator reading the trace — exactly which file and key the
    value came from. Important for the EvidenceValidator and for
    debugging the agent's reasoning chain.

    Args:
        component: Canonical NF name (amf, smf, upf, pcscf, scscf,
            icscf, pyhss, rtpengine, mongo, mysql, dns, nr_gnb, ...)

    Returns:
        Structured dict per the schema above. Raises if the component
        name is unknown to the ontology.
    """
```

Three design choices worth flagging:

- **Structured output, not raw text.** Every field has a stable name. The LLM doesn't have to parse free-form config to extract a value.
- **The `purpose` annotation is structured (protocol / interface / role), not a flat tag.** Flat tags ("diameter", "sbi") work for the simplest lookups, but structured key:value pairs let downstream reasoning ask richer questions ("which port is this NF's *server* side of the *Cx* interface?") and leave room to add fields without breaking the schema.
- **Source attribution per port.** Each port entry's `source` field names the file and key the value came from. EvidenceValidator can audit it; operators reading the trace can grep to the source themselves.

**Downstream consumers are NOT in this tool's output.** Component-to-component dependency information already lives in the ontology — `network_ontology/data/causal_chains.yaml` (failure-mode cascades) and `network_ontology/data/flows.yaml` (protocol-flow participation). Folding it into `get_deployment_config` would duplicate that data with no benefit. If the agent needs "which NFs consume X?", that's a separate lookup over the existing causal-chains / flows surface — out of scope for this ADR.

The tool is read-only and side-effect-free. Like `get_network_status`, `get_network_topology`, and the other inspection tools, it runs in <100ms (file read + YAML parse) and doesn't depend on the stack being healthy.

### The lesson — generalizable, not hard-wired

Added to `agentic_ops_common/rag/lessons.yaml` as L16. Approximate shape (final wording during implementation):

> **L16 — Deployment-configurable values must be verified, not assumed.** Service ports, IPs, container names, and interface bindings are deployment-specific and vary across environments. Before asserting that "service X is/isn't listening on port Y" or "component A talks to component B at address Z," consult `get_deployment_config(component)` to read the deployment's actual configuration. IANA-standard port assignments, container-name defaults, and training-corpus knowledge about common protocol bindings are priors — useful for forming hypotheses, but they MUST be verified against the live deployment configuration before being asserted as evidence in a probe interpretation or hypothesis statement.

The lesson is deliberately framed as a class of behavior, not a list of facts. It tells the agent *when* and *how* to consult the tool, not what values to expect. It does NOT name specific ports, NFs, or runs — those would be cheat-sheet content that fails to generalize across deployments and across new failure modes. Maintenance cost: zero — the tool returns whatever the config says, and the rule applies to any deployment-configurable value the stack adds in the future.

### The prompt rule

Added to `agentic_ops_v7/prompts/investigator.md` as a new section under "Probe interpretation". The prompt text is **pure principle** — no episode names, no specific port numbers, no specific NFs. Naming a particular case in a prompt rule does not generalize: future deployments, future protocols, and future port assignments will all differ from any worked example we hard-code. The rule is about the *class* of reasoning the investigator must apply, not a list of facts to memorize.

> ### Verify deployment-specific assumptions before asserting them
>
> Probes like `check_process_listeners`, `read_running_config`, and `measure_rtt` return data that depends on deployment-specific values — listening ports, target IPs, service endpoints. Service-port assignments and bindings vary by deployment and may diverge from IANA standards, training-corpus defaults, or common conventions.
>
> Before you assert "service X is not listening on port Y," "component A is not reachable at address Z," or any similar claim about a configured value, call `get_deployment_config(component)` to read the deployment's actual configuration for that component. The tool returns structured information about each component's listening ports (with per-port `purpose: {protocol, interface, role}` annotations), IPs, and source-file attribution.
>
> Whenever you cite a port number, container name, or IP in a hypothesis statement or probe interpretation, your reasoning must trace back to one of:
>
>   - a `get_deployment_config` call,
>   - a `read_env_config` call,
>   - a `read_running_config` call, or
>   - a value the probe itself returned.
>
> IANA-standard port numbers and training-corpus knowledge of common protocol bindings are NOT acceptable sources for assertions about THIS deployment. They are priors for hypothesis-forming only.

### Where the tool wires in

`agentic_ops_common/tools/__init__.py` — re-export `get_deployment_config` alongside the other inspection tools.

Two consumer agents add it to their toolsets:

- `agentic_ops_v7/subagents/investigator.py` — added to the `tools=[...]` list alongside `read_running_config` and `read_env_config`.
- `agentic_ops_v7/subagents/instruction_generator.py` — added so the IG can ground its plan's expectations (the "Expected if hypothesis holds" / "Falsifying observation" criteria) in actual configured values, not IANA standards.

The NA might also benefit but is out of scope for this ADR — NA's failure modes around deployment-specific values haven't shown up in the runs analyzed so far. If a future run surfaces an NA hallucination tied to a port assumption, wire it in then.

## Trade-offs and limitations

**The tool can only return what the config files contain.** If a value is dynamic (set at runtime, e.g. an ephemeral port chosen at process startup), `get_deployment_config` won't catch it. The agent should fall back to `check_process_listeners` or the probe data directly. The tool is for *intended* configuration; the probes are for *observed* runtime state. The lesson explicitly says: "consult the stack config before asserting a service is/isn't bound" — not "trust the stack config over the probe."

**The `purpose` annotation requires curation.** Mapping "this port serves the `cx` interface of the `diameter` protocol in `server` role" needs a per-component metadata file. The file lives at `network_ontology/data/deployment_metadata.yaml` alongside the rest of the ontology data (components.yaml, deployment.yaml, causal_chains.yaml, flows.yaml). This is the one place where deployment-specific knowledge re-enters the system — but it lives in a versioned, reviewable ontology file rather than in the lesson corpus or the agent's prompt. Maintenance cost is bounded: adding a new component is a small entry; modifying a port assignment in `network/.env` requires no metadata change because the purpose annotation is bound to the *kind of service*, not the port number.

**The compound-consistency guardrail still won't catch interpretation errors.** Even after this ADR lands, an investigator that runs `get_deployment_config`, gets `port=3875, purpose=diameter`, and *still* concludes "Diameter not bound" would not be caught structurally. That's a separate, harder problem (LLM judging LLM interpretations of probe output). The lesson-and-prompt approach here addresses the more common case where the agent never asked the question; the harder case of "agent asked and got the right answer but ignored it" stays in the failure budget until we have stronger evidence it's a recurring pattern.

**Doesn't replace the existing `read_env_config` / `read_running_config` tools.** Those keep their value for cases where the agent wants the raw config text (e.g. checking a kamailio routing-script syntax). `get_deployment_config` is the targeted-lookup interface for "what's the actual port/IP/binding for component X."

## Implementation outline

Land in this order. No code changes during ADR review — only after the design is signed off.

1. **Define the per-component metadata** — new YAML file at `network_ontology/data/deployment_metadata.yaml` mapping each NF to its port purposes (structured `{protocol, interface, role}` per port) and the env / config-file keys those ports resolve from. Hand-authored once; lives alongside the rest of the ontology data files. Schema validated by a Pydantic loader analogous to the existing `components.yaml` / `deployment.yaml` loaders.
2. **Implement `get_deployment_config`** — function in `agentic_ops_common/tools/deployment_config.py` that reads `network/.env`, the relevant `network/<component>/config.yaml`, the existing `network_ontology/data/deployment.yaml`, and the new `deployment_metadata.yaml`. Applies env-var substitution. Returns the structured dict per §The tool. Unit tests against the real `network/` directory in the repo.
3. **Re-export through `agentic_ops_common/tools/__init__.py`** — alongside `get_network_status`, `read_env_config`, etc.
4. **Wire into investigator + IG toolsets** — add to `tools=[...]` lists in the v7 subagent factories.
5. **Update the investigator prompt** — new "Verify deployment-specific assumptions" section per §The prompt rule (pure principle; no episode names or specific port values).
6. **Add lesson L16** to `agentic_ops_common/rag/lessons.yaml`. Rebuild the lessons cache (currently module-loaded once per process; the existing observability machinery will surface the new lesson ID in future runs).
7. **Integration test** — synthetic InvestigatorAgent invocation that fakes a `check_process_listeners` output where the actual configured port (per `deployment_metadata.yaml`) is present but a different IANA-standard port is absent. Assert that the post-fix investigator's verdict consults `get_deployment_config`, recognizes the listener IS the configured one, and does not fabricate a "service not bound" claim.

Total scope: 1 new tool file (~80 LOC), 1 new ontology file (`deployment_metadata.yaml`, ~50–80 lines YAML for the current NF set), 4 small files touched (toolset wiring + prompt + lesson + tests).

## Validation target

After the ADR's implementation lands, re-run the HSS Unresponsive scenario (the triggering episode for this ADR; see the §Related links). Expectation:

- The IG's plan and the Investigator's probes consult `get_deployment_config(<NF>)` before generating any falsifying-criterion or hypothesis statement that names a port number.
- The returned `listening_ports` show the deployment's actual configured ports with their structured `purpose` annotations.
- The investigator's hypothesis-statement / verdict-reasoning text traces port claims back to either the `get_deployment_config` output or the probe output — not to IANA standards.
- Synthesis emits `verdict_kind=localized` (single fault, walker's latency attribution) — NOT `compound` with a fabricated "service not bound" second root cause.
- The recommendation field tells the operator about the actual fault only — no phantom port investigation.

If the run still produces a compound verdict citing a port the agent never grounded in the deployment config, the lesson + prompt rule weren't enough; escalate to a structural guardrail that compares investigator port assertions against `get_deployment_config` output (the harder follow-up flagged in §Trade-offs).

## Out of scope

- **Backporting to v5/v6.** Those agent versions are frozen; their port-related failure modes are historical. The tool can be exposed but the prompt rules and lessons should not be added there.
- **NA-side prompt rules.** NA hasn't been observed making deployment-specific assertions about ports yet. Add the rule if a future run surfaces it.
- **A guardrail that judges the investigator's interpretation.** Flagged in §Trade-offs as the next-tier defense if the lesson-and-prompt layer proves insufficient. Hold for empirical evidence.
- **Dynamic-config introspection** (live ports chosen at runtime). The probe data already covers this; the deployment-config tool is for *intended* configuration.
- **Auto-discovering port purposes via probes.** Possible — e.g. infer "this port is Diameter" by sending a Diameter handshake and seeing if it responds. Over-engineered for the current failure-rate; revisit if the curated metadata becomes a maintenance pain point.

## Resolved decisions (from review)

- **Tool name: `get_deployment_config`** (not `get_stack_config`, not `get_service_config`).
- **Metadata file path: `network_ontology/data/deployment_metadata.yaml`** — lives with the rest of the ontology data files, not under `agentic_ops_common/tools/`.
- **`purpose` annotation is structured `{protocol, interface, role}`**, not flat tags. Leaves room to add fields without breaking the schema.
- **Downstream-consumer info is NOT in `get_deployment_config`'s return.** Component-to-component dependency information already lives in `network_ontology/data/causal_chains.yaml` (failure-mode cascades) and `network_ontology/data/flows.yaml` (protocol-flow participation). Surfacing it would duplicate that data with no benefit. A separate lookup over the existing ontology surface is the right place if and when the agent needs "which NFs consume X?"
- **Lesson L16 is pure principle.** No specific run, NF, or port reference. Same for the prompt rule. Naming a specific failure mode in any rule that the LLM ingests does not generalize — it teaches one fact instead of one class of reasoning.

No remaining open questions blocking implementation. Wording of the prompt rule and the lesson can be refined in the PR.
