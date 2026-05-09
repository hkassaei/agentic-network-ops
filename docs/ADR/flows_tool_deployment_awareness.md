# ADR: Make `get_flows_through_component` Honestly Canonical, and Add a Live-Activity Companion

**Date:** 2026-05-06
**Status:** Proposed
**Related:**
- Critical observation: [`../critical-observations/why_agent_fails_with_dataplane_failure_scenarios.md`](../critical-observations/why_agent_fails_with_dataplane_failure_scenarios.md) — Bonus issue: "get_flows_through_component probe".
- Post-investigation analysis (2026-05-06, in-conversation): traced the implementation to `agentic_ops_common/tools/flows.py:75-99`; confirmed the tool is a static ontology lookup, not deployment introspection. Tool description in `agentic_ops_v6/prompts/investigator.md:65` and `agentic_ops_v6/prompts/instruction_generator.md:56` does not state this scope.
- [`flow-based-causal-chain-reasoning.md`](flow-based-causal-chain-reasoning.md) — the design that introduced flow-based reasoning; this ADR refines its tool surface.
- [`falsifier_investigator_and_rag.md`](falsifier_investigator_and_rag.md) — Investigator architecture that consumes the flow tool's output.

---

## Decision

Disambiguate the flow tool surface so the Investigator and InstructionGenerator cannot confuse "the procedure the ontology says runs through this NF" with "the procedure currently active in this deployment." Two coordinated changes ship together:

1. **Rename the existing tool to `get_canonical_flows_through_component` and rewrite its description, docstring, and output payload to be honestly named as a static ontology lookup.** The output payload includes a leading `source: "network_ontology"` field and a top-of-output disclaimer line so the LLM sees "canonical" on every invocation, not just in the prompt. All callers (prompts, IG, Investigator subagent code) update to the new name in the same PR. No alias, no compatibility shim — the rename is the point.
2. **Add a new, deployment-aware companion tool `get_active_flows_through_component(nf, at_time_ts, window_seconds)`** that intersects the canonical flow set with live activity signals from Prometheus (per-flow indicator metrics) and returns only the flows with non-zero activity in the window. This is the tool the Investigator should reach for when the question is "what is *actually* happening through this NF right now."

The Investigator and InstructionGenerator prompts (`agentic_ops_v6/prompts/investigator.md`, `agentic_ops_v6/prompts/instruction_generator.md`) gain explicit guidance distinguishing the two tools and naming when each is appropriate.

## Context

`get_flows_through_component` is implemented in `agentic_ops_common/tools/flows.py:75-99` as:

```python
async def get_flows_through_component(component: str) -> str:
    flows = OntologyClient.get_flows_through_component(component)
    return json.dumps([
        {"flow_id": f.id, "flow_name": f.name,
         "step_order": s.order, "step_label": s.label}
        for f in flows for s in f.steps if s.touches(component)
    ])
```

The data source is `network_ontology/data/flows.yaml` — a curated KB of canonical procedure flows (REGISTER, INVITE, vonr_call_setup, etc.). It is **not** a query against the live deployment. There is no Prometheus query, no SIP rate check, no activity verification. The tool returns the same JSON regardless of what the stack is currently doing.

The tool's description in `agentic_ops_v6/prompts/investigator.md:65`:

> *"`get_flows_through_component(nf)` — lists every flow that touches the given NF, with step positions. Use this when a hypothesis names an NF and you want to see every procedure whose failure modes mention it."*

And in `agentic_ops_v6/prompts/instruction_generator.md:56`:

> *"`get_flows_through_component(nf)` — returns every flow touching a given NF, with step positions."*

Neither description says the data is canonical / static / ontology-derived. The agent reads "every flow touching this NF" and the implicit assumption is that "touching" means in the present tense. The critical observation flagged this:

> *"The probe `get_flows_through_component` appears in several falsification plans. How is it actually used by Investigator agent? It's quite good if used to understand what the flow looks like with the goal of checking relevant metrics or containers along the way. But if it is used to generically reason about containers communicating with one another during a particular flow, as opposed to this particular deployment and failure scenario, then it needs to be refined."*

The risk pattern: an Investigator pulls the canonical flows for `pcscf`, sees that `vonr_call_setup` and `emergency_call` and `ue_register` all touch P-CSCF, and reasons as if all three are currently active even though only one (or none) might be. That reasoning shape produces hypotheses that look plausible against the canonical text but fail against the actual stack state.

### Why a rename rather than a docstring tweak

The single most reliable way to keep the LLM from conflating canonical and live is to put "canonical" in the tool name. The LLM types the tool name into its tool call; the typing is a forced moment of explicit semantic choice. A docstring or prompt sentence is read once and forgotten by the next sample.

The cost of the rename is bounded: the call sites are the prompts and the Investigator's tool-binding code. Both are edited in the same PR.

### Why a separate live-activity tool, not a parameter on the canonical tool

A boolean flag (`live=True`) on the existing tool would put the live-activity logic behind a parameter, and the LLM would have to remember to set it. Two distinct tools with distinct names mirror the distinction the LLM has to make in its head — pick the tool that matches the question, no flag to forget.

The live-activity tool also has a different signature (it needs a timestamp and a window), which fits poorly as an optional argument.

## Design

### `get_canonical_flows_through_component`

`agentic_ops_common/tools/flows.py` — the existing function is renamed; its docstring and output are rewritten:

```python
async def get_canonical_flows_through_component(component: str) -> str:
    """Return canonical procedure flows from the network ontology that
    pass through the given NF.

    SOURCE: network_ontology/data/flows.yaml (static curated KB).
    SCOPE: This is a reference lookup. It does NOT verify whether any
           returned flow is currently active in the deployment. Use
           `get_active_flows_through_component` to determine live
           activity.

    Use this to: enumerate the procedures whose failure modes touch this
    NF, walk each flow's steps and metrics for hypothesis development,
    and identify which observable signals would change at each step.

    Do NOT use this to: claim a flow is currently executing, infer that
    UEs are currently in a specific call state, or assert traffic is
    flowing along a specific path right now.
    """
    flows = OntologyClient.get_flows_through_component(component)
    return json.dumps({
        "source": "network_ontology",
        "scope": "canonical (NOT live deployment state)",
        "component": component,
        "flows": [
            {"flow_id": f.id, "flow_name": f.name,
             "step_order": s.order, "step_label": s.label,
             "failure_modes": [fm.id for fm in s.failure_modes]}
            for f in flows for s in f.steps if s.touches(component)
        ],
    }, indent=2)
```

The output payload now leads with `source` and `scope` keys before the flow list. The LLM sees "canonical (NOT live deployment state)" on every probe response, not only in the prompt. The `failure_modes` field is added to the per-step record because that's the actual point of the tool — walk failure modes for hypothesis development — and surfacing them inline saves a follow-up query.

### `get_active_flows_through_component`

New function in `agentic_ops_common/tools/flows.py`:

```python
async def get_active_flows_through_component(
    component: str,
    at_time_ts: float,
    window_seconds: int = 120,
) -> str:
    """Return canonical flows that are CURRENTLY active in the deployment,
    based on per-flow activity indicators measured over the given window.

    For each canonical flow that touches the NF, this tool evaluates the
    flow's `activity_indicator` (a Prometheus expression authored in the
    KB — typically a rate of a specific SIP method, GTP-U packet, or
    Diameter command) over [at_time_ts - window_seconds, at_time_ts]. A
    flow is "active" iff the indicator is above its KB-authored
    activity_threshold over the window.
    """
```

This requires one KB schema addition: every entry in `network_ontology/data/flows.yaml` gains an `activity_indicator` field — a Prometheus expression and a numeric threshold:

```yaml
- id: vonr_call_setup
  name: VoNR call setup
  activity_indicator:
    expr: 'rate(kamailio_core_rcv_requests_total{method="INVITE"}[{w}s])'
    threshold_gt: 0.0
  steps: …
```

The new tool's output:

```json
{
  "source": "live (Prometheus over window)",
  "scope": "deployment activity at at_time_ts ± window_seconds",
  "component": "pcscf",
  "window_seconds": 120,
  "active_flows": [
    {"flow_id": "vonr_call_setup", "flow_name": "VoNR call setup",
     "indicator_value": 0.06, "indicator_expr": "...", "active": true,
     "steps_touching_nf": [...]}
  ],
  "inactive_flows": [
    {"flow_id": "emergency_call", "flow_name": "Emergency call",
     "indicator_value": 0.0, "indicator_expr": "...", "active": false}
  ]
}
```

Inactive flows are returned (not omitted) so the LLM can see the negative result — "ue_register has zero activity in this window" is itself a piece of evidence the Investigator might want to cite.

### Prompt updates

`agentic_ops_v6/prompts/investigator.md` (replace the existing flows-tool description with):

> *Two flow tools, distinct purposes:*
>
> *— `get_canonical_flows_through_component(nf)` returns reference procedure flows from the network ontology that touch the named NF, with step positions and per-step failure modes. This is a KB lookup; it does NOT verify any flow is currently active. Use it to develop hypotheses (which procedures' failure modes match the observed symptoms) and to walk a flow's steps for probe selection.*
>
> *— `get_active_flows_through_component(nf, at_time_ts, window_seconds)` returns the same flows BUT filtered against live Prometheus activity indicators in the given window. Use it when the question is "what is actually happening through this NF right now," for example before claiming a specific procedure is exhibiting a fault, or when ruling out a hypothesis whose flow is not active.*

`agentic_ops_v6/prompts/instruction_generator.md` gets the same paragraph in its tool-listing section.

### Why both functions live in the same module

They share the canonical-flow data structure. Splitting them across modules would force every caller to import two files for what is conceptually one concept (procedure flows, with two views). Co-locating keeps the source of truth (canonical flow definitions) adjacent to its live-activity wrapper.

### Migration: no alias, single PR

The rename is a hard cut. `get_flows_through_component` is removed; every caller updates to `get_canonical_flows_through_component` in the same PR. No deprecation alias, no compatibility shim. The current consumer set is small and entirely in this repo:

- `agentic_ops_v6/prompts/investigator.md:65`
- `agentic_ops_v6/prompts/instruction_generator.md:56`
- `agentic_ops_v6/subagents/investigator.py` (tool registration)
- `agentic_ops_v6/subagents/instruction_generator.py` (tool registration)
- Any tests that mock the tool name.

A grep for `get_flows_through_component` over `agentic_ops_v6/` and `agentic_ops_common/` enumerates the full call graph; the rename is mechanical.

## Verification

After implementation:

1. Probe the Investigator on the `run_20260502_172113` re-run against a hypothesis that names rtpengine. Confirm that any flow-tool call uses the explicit canonical or active name, and that the canonical-tool output payload includes the `source`/`scope` lines.
2. `get_active_flows_through_component(pcscf, at_time_ts, 120)` against a stack with a live VoNR call returns `vonr_call_setup` in `active_flows` and (typically) `emergency_call` in `inactive_flows`.
3. `get_active_flows_through_component(pcscf, at_time_ts, 120)` during baseline (no calls) returns an empty `active_flows` list and the full canonical set in `inactive_flows`.

Plus:

- `test_canonical_flows_payload_shape`: payload contains `source`, `scope`, `component`, `flows`; `scope` string contains the literal "NOT live deployment state."
- `test_active_flows_filters_by_indicator`: with mock Prometheus values, an indicator above threshold lands in `active_flows`, below in `inactive_flows`; both lists are present.
- `test_no_legacy_name`: a grep over the repo for `get_flows_through_component\b` (without `canonical_` or `active_` prefixes) returns zero results outside this ADR file.

## Files Changed

- `agentic_ops_common/tools/flows.py` — rename existing function to `get_canonical_flows_through_component`; rewrite docstring and output payload; add `get_active_flows_through_component`.
- `network_ontology/data/flows.yaml` — every flow entry gains an `activity_indicator` block (`expr` + `threshold_gt`). Authored from existing per-flow signaling/data-plane signatures already documented in the KB.
- `network_ontology/schema.py` — `FlowEntry` schema gains `activity_indicator: ActivityIndicator | None` (None permitted for flows where no indicator is meaningful, e.g. failure-only flows).
- `network_ontology/query.py` — `OntologyClient` exposes `get_active_flows_through_component`; the Prometheus query path reuses the existing client used by `get_dp_quality_gauges`.
- `agentic_ops_v6/prompts/investigator.md`, `agentic_ops_v6/prompts/instruction_generator.md` — replace existing flow-tool description with the two-tool paragraph.
- `agentic_ops_v6/subagents/investigator.py`, `agentic_ops_v6/subagents/instruction_generator.py` — update tool registration to bind both names.
- Tests as listed in Verification.

## Alternatives Considered

1. **Add only the live tool; leave the existing one named as-is.** Rejected. Two tools with overlapping names ("flows" vs "active_flows") still leave the existing one ambiguously scoped. The rename is the structural fix; the new tool is the additional capability.

2. **Keep `get_flows_through_component` as an alias for the canonical tool.** Rejected. Aliases mean the LLM can pick either name and get the same result, which preserves the original ambiguity rather than resolving it. Hard cut, single PR.

3. **Add a `live=True` parameter to the existing tool instead of a separate function.** Rejected. The two views have different signatures (the live view needs a timestamp and a window) and different output shapes (active/inactive partition). A flag hides the semantic distinction the prompt is trying to teach.

4. **Compute live activity inside the canonical tool and merge the two payloads.** Rejected. Conflates the source of truth (KB) with a secondary observation (live metrics). The Investigator should be able to consult the canonical view without hitting Prometheus, and should be able to ask "what's active" without re-fetching canonical context.

5. **Author the activity indicators in `flows.yaml` lazily (only for the flows we currently care about).** Rejected. A partially-populated `activity_indicator` field invites the same reasoning trap on a different axis ("the tool returned no active flows for this NF — is the NF idle, or did the indicator just not exist?"). Authoring the indicator for every canonical flow is bounded one-time work; doing it lazily produces ongoing confusion.

## Follow-ups

- Once both flow tools are in place, audit the InstructionGenerator's plan output for falsification probes that name `get_canonical_flows_through_component` when the question is actually about live state. Tighten via the existing IG validator if a pattern emerges.
- Consider whether `get_active_flows_through_component` should also report **degraded** activity (indicator above zero but below the typical healthy range from the metric KB). This would be a third state alongside active/inactive. Not in this ADR's scope; would extend the indicator schema with a healthy range.
