# ADR: Flow-Based Causal-Chain Reasoning — Two Complementary Views, Both Implementation-Anchored

**Date:** 2026-04-21 (revised 2026-04-23)
**Status:** Partially shipped — tool layer, ontology corrections, and `source_steps` rollout across all 12 causal chains landed. Remaining work is loader support and the structured `failure_modes` migration with its accompanying IG/reverse-lookup tooling. See [Implementation manifest](#implementation-manifest) for specifics.

**Context source (the run that prompted this):**
- [`docs/critical-observations/run_20260421_030339_mongodb_gone.md`](../critical-observations/run_20260421_030339_mongodb_gone.md) — MongoDB container kill; v6 agent scored 30% by hallucinating a `mongo → HSS` dependency the ontology doesn't assert and missing the real `mongo → UDR → PCF → N5 App Session Create → SIP 412 at P-CSCF` chain entirely.

**Related:**
- [`metric_knowledge_base_schema.md`](metric_knowledge_base_schema.md) — parallel authoring discipline for metrics.
- [`kb_backed_tool_outputs_and_no_raw_promql.md`](kb_backed_tool_outputs_and_no_raw_promql.md) — prior work grounding tool outputs in the KB.
- `network_ontology/data/flows.yaml` — protocol-level call flows.
- `network_ontology/data/causal_chains.yaml` — failure propagation scenarios.
- `network_ontology/query.py` — Neo4j-backed query layer (flow queries already implemented).
- `agentic_ops_common/tools/causal_reasoning.py` — existing agent-facing wrapper for causal chains (to be mirrored for flows).

---

## Context

### The concrete failure

MongoDB was killed. The v6 agent observed `mongo container exited` correctly but misdiagnosed the root cause as *"an undetermined fault within the HSS (pyhss)"* and explicitly falsified the correct hypothesis. Score: 30%.

Two distinct problems combined to produce this:

1. **NA reached past the ontology for a generic LLM prior.** NA's Phase 3 summary asserted *"mongo → HSS unresponsive"* — a dependency that **does not exist** in `components.yaml`. The ontology is explicit: mongo is UDR's backend (5G core); pyhss uses mysql. NA never invoked `get_causal_chain_for_component` or the `OntologyConsultationAgent`; it borrowed a textbook assumption about HSS being MongoDB-backed (common in other deployments but not ours).

2. **The ontology's authored causal chains miss the edge that actually matters.** `causal_chains.yaml`'s `subscriber_data_store_unavailable` entry traced `mongo → UDR → SMF new-session failure` — the canonical 3GPP consequence. It did NOT trace the real chain driving 100% of observed SIP error load in this scenario: `mongo → UDR → PCF → P-CSCF N5 App Session Create failure → send_reply("412") → SIP error`. This branch was silently absent (subsequently filled in during the corrections this ADR mandates).

Even a disciplined NA that dutifully consulted the ontology would have produced an incomplete story — the ontology did not encode the branch that explains the symptom.

### The deeper finding

Inspecting the Kamailio P-CSCF route files (`network/pcscf/route/mo.cfg`, `mt.cfg`, `register.cfg`) together with `pcscf_init.sh` reveals:

- **`WITH_RX` is compiled OUT** in 5G mode (`pcscf_init.sh` rewrites the define). The `Rx_AAR` call in `mo.cfg`'s `onreply_route[MO_reply]` — which would fire on 180/183/200-with-SDP and call `dlg_terminate("all", "Sorry no QoS available")` on failure — is dead code in this deployment.
- **`WITH_N5` is compiled IN**. The active policy path is `route[N5_INIT_REQ]` / `route[N5_INIT_MT_REQ]` / `route[N5_REG_PCF_POLICY_AUTH]`, which issue HTTP/2 POSTs to the PCF at `/npcf-policyauthorization/v1/app-sessions` via SCP. On non-201 responses the P-CSCF calls `send_reply("412", "Register N5 QoS authorization failed")` and stops forwarding the INVITE (or, for REGISTER, intercepts the 200 OK on the reply path).

Critically, both `Rx_AAR` and `N5_INIT_REQ` are **gates on call setup** — not post-establishment enhancements. The mechanism differs (Diameter vs. HTTP/2 SBI; `dlg_terminate` vs. `send_reply("412")`) but the causal shape is the same: PCF failure ⇒ SIP error upstream on every call attempt.

`flows.yaml`'s `vonr_call_setup` originally placed Rx AAR as step **#10, after "Call established."** The textbook-canonical ordering, not what the code does, and the wrong protocol for our stack entirely. The two diverge in a way that matters for reasoning: a pipeline that reads the flow as ground truth concludes "policy-authorization failure would degrade dedicated QoS but not cause SIP errors" — exactly the inference gap that let NA hallucinate HSS as the fault source instead of tracing through PCF.

Generalized: **our ontology content (flows + causal chains + metric meaning blocks) is largely a textbook 3GPP skeleton with stack-specific numeric observations sprinkled in.** Where the textbook matches our code, the ontology serves the agent well. Where the textbook abstracts over implementation-specific code paths, the ontology is silent or subtly wrong, and the agent either (a) reaches past the ontology for LLM priors, or (b) reaches a confidently-wrong conclusion because the ontology looked authoritative.

An *authoritative-looking but subtly wrong* ontology is worse than no ontology, because it removes the pressure to verify.

---

## Decision

Keep both `flows.yaml` and `causal_chains.yaml` as first-class ontology artifacts. They are **not redundant** — they serve different reasoning phases. But they must be authored with discipline and exposed to agents through dedicated tools.

### 1. The two files have distinct roles

**`flows.yaml` — mechanism-level, temporally-ordered view.** Nodes are NFs; edges are protocol interactions (SIP, Diameter, GTP). Steps carry `failure_modes` that describe what a reader of the code would see happen when that step's code path errors. This is the **forward-walking mechanism model** — used by the Investigator to verify hypotheses: *"if candidate failure F is true, what should happen at step N? What log line? What SIP response code?"*

**`causal_chains.yaml` — failure-indexed, symptom-aggregated view.** Named failure scenarios (`hss_unreachable`, `subscriber_data_store_unavailable`, …) with `possible_causes`, `observable_symptoms`, and `diagnostic_approach`. This is the **reverse-indexing hypothesis-generation model** — used by NA to map from observed symptoms back to candidate root causes, and by the IG to design discriminating probes.

| Phase | View used | Why |
|---|---|---|
| NA — hypothesis generation | causal_chains | "Which failure pattern matches these symptoms?" — symptom → cause reverse lookup, pre-computed |
| IG — probe design | causal_chains.diagnostic_approach + flows.failure_modes | High-level probe plan + code-path-specific expected evidence |
| Investigator — falsification | flows | Forward walk through mechanism; check every step's expected `failure_modes` against what probes see |
| Synthesis | both | Causal chains give the failure taxonomy; flows give step-by-step consistency check |

Asking flows to serve hypothesis generation means tracing every flow backward from every deviated metric — slow, token-heavy, error-prone. Asking causal chains to serve falsification means reasoning from high-level abstractions without touching the code paths — which is exactly what produced the HSS hallucination in this run. Neither can cover the other's job efficiently.

### 2. Authoring discipline — both files must be implementation-anchored

Textbook-shaped authoring is the root cause of this run's score. Future authoring must satisfy:

**`flows.yaml` steps.** Every step whose behavior is enacted by our code carries an `implementation_ref` pointer — file + approximate location + symbol. Line numbers are discouraged (they churn); file + symbol is enough for a reader to find the code. `failure_modes` for each step must enumerate the **actual error branches in the code**, not imagined 3GPP fallbacks. Example:

```yaml
- order: 2
  label: "N5 App Session Create (originating) — QoS authorization"
  from: pcscf
  to: pcf
  via: [scp]
  protocol: HTTP/2 SBI
  interface: N5
  implementation_ref:
    file: "network/pcscf/route/mo.cfg"
    symbol: "route[N5_INIT_REQ]"
  failure_modes:
    - when: "PCF returns non-201 (or POST times out)"
      action: 'send_reply("412", "Register N5 QoS authorization failed")'
      observable: "SIP 412 returned to caller; INVITE never forwarded upstream; pcscf_sip_error_ratio rises toward 1.00"
```

The "voice uses default bearer" textbook fallback is NOT what our code does. That line is removed. Note that `Rx_AAR` does exist in the Kamailio source but is behind `#!ifdef WITH_RX`, which the 5G-mode init script disables — a code reader who only skimmed function names without checking compile flags would document the wrong protocol, exactly the kind of trap this discipline exists to catch.

**`causal_chains.yaml` entries** must include a `source_steps` reference on every `observable_symptoms` entry — pointing at the specific flow step whose `failure_modes` enumerate that symptom. Example:

```yaml
subscriber_data_store_unavailable:
  observable_symptoms:
    cascading:
      - symptom: "SMF new PDU session creation falls back to local default policy"
        source_steps: [pdu_session_establishment.step_3]
      - symptom: "pcscf_sip_error_ratio = 1.00 on every INVITE (SIP 412)"
        source_steps: [vonr_call_setup.step_2, vonr_call_setup.step_9]
        mechanism: "UDR blind → PCF returns non-201 on N5 POST → P-CSCF send_reply('412')"
```

The `source_steps` cross-reference is what keeps the two files from drifting. An observable symptom in a causal chain must be traceable to a concrete flow-step `failure_mode`. Discipline during authoring — plus the fact that an unreferenced step becomes invisible to `get_flows_through_component` — is the current enforcement mechanism.

### 3. Expose flows to agents through dedicated tools

The data layer already existed — `network_ontology/query.py` provides `get_all_flows()`, `get_flow(flow_id)`, `get_flows_through_component(component)` against the Neo4j-loaded ontology. But no agent-facing tool wrapped them, so nothing in the agent pipeline could reach them.

**Shipped:** three thin wrappers in `agentic_ops_common/tools/flows.py`, mirroring the shape of the existing `tools/causal_reasoning.py`:

```python
async def list_flows() -> str:
    """List every protocol flow in the ontology (id, name, use_case, step_count)."""

async def get_flow(flow_id: str) -> str:
    """Get a protocol flow with all its ordered steps, including each step's
    protocol, interface, failure_modes, and metrics_to_watch. (implementation_ref
    will be surfaced here once it's added to the underlying YAML.)"""

async def get_flows_through_component(component: str) -> str:
    """List all flows that pass through a given NF, with step positions.
    Useful for 'if this NF fails, what's downstream?' reasoning."""
```

Exported through `agentic_ops_common/tools/__init__.py`, wired into the NetworkAnalyst, InstructionGenerator, and Investigator tool lists per the reasoning-phase mapping (NA → list + through-component; IG → all three; Investigator → all three), and referenced in all three prompts with flow-anchored-probe guidance.

---

## Consequences

### Positive

- **The ontology becomes trustworthy as a reference for reasoning.** Implementation-anchored flows + cross-referenced causal chains mean the agent can consult the ontology with confidence that what it finds reflects the code, not a textbook abstraction. Hallucination pressure drops because the agent has an authoritative answer to reach for instead of generic priors.
- **Each reasoning phase gets the right shape of data.** NA gets pre-computed symptom→cause indexes (fast hypothesis generation). Investigator gets forward-walking mechanism detail (precise falsification). No phase is forced to do work in a representation that's wrong for its task.
- **Divergences between ontology and code become easier to spot.** With `source_steps` in place, a causal-chain branch points at a concrete flow step; a reader (or a future tool) can walk from branch to step and compare the declared `observable_metrics` against the step's `failure_modes`. Still manual for now — automated enforcement is not in scope at this stage.
- **The `mongodb_gone` 30% score is addressable at the ontology layer.** Add the `vonr_call_setup.step_9a` Rx AAR step with its real `failure_modes`; add the `source_steps: [...step_9a...]` entry to `subscriber_data_store_unavailable.observable_symptoms`; expose flows through the new tools. NA will then find the correct chain; Investigator will verify via real code-path observables.

### Negative / risk

- **Authoring cost rises.** Every flow step eventually needs an `implementation_ref` review pass; every causal-chain observable_symptom needs a `source_steps` cross-reference. This is mostly one-off work to bring current content up to standard, then ongoing discipline on new entries. Drift risk is real and mitigated only by author discipline at this stage.
- **Requires the Neo4j ontology loader to understand the new fields.** `implementation_ref`, `source_steps`, and the structured `failure_modes.{when, action, observable}` shape need loader support in `network_ontology/loader.py` so they survive the YAML → Neo4j → query roundtrip.
- **`implementation_ref` line numbers will churn.** Keeping line numbers up to date is brittle. Policy: author the `file` and `symbol` fields; omit `lines`. A reader can grep for the symbol.
- **The `get_flow()` / `get_flows_through_component()` outputs will be larger than causal-chain outputs.** A 10-step flow with nested `failure_modes` is non-trivial JSON. Worth a `verbosity` arg on `get_flow` (e.g. `summary` vs `full`) if token budget becomes an issue.

### Alternatives considered

1. **Drop `causal_chains.yaml` entirely; generate causal chains on-demand from flows.** A tool `get_causal_chain_for_component(nf)` would programmatically walk every flow, collect `failure_modes` that implicate `nf`, and synthesize the chain at inference time. Rejected because (a) `possible_causes` — the *why* of component failure (OOM, disk full, etc.) — is not in flows and belongs at the causal-chain level; (b) cross-flow aggregation at inference time is expensive in tokens and prone to LLM summarization error; (c) hand-authored `diagnostic_approach` (probe ordering for a named failure) is higher-leverage than scattered flow-level probe hints.
2. **Drop `flows.yaml`; keep only causal_chains.** Rejected because the Investigator's forward-walk falsification phase genuinely needs step-by-step mechanism, not aggregated symptoms. Without flows the agent falls back to "does this pattern feel consistent?" — exactly the NA failure mode we're trying to eliminate.
3. **Merge both into a single unified model per-NF.** Rejected because a component-centric view (failure profile per NF) loses the temporal/protocol sequencing that makes flows useful for mechanism walks. Two files is two orthogonal indexes into the same underlying truth.

---

## Implementation manifest

### Shipped

**Tool layer**
- `agentic_ops_common/tools/flows.py` (new) — three agent-facing wrappers: `list_flows`, `get_flow`, `get_flows_through_component`. Each delegates to `network_ontology.query.OntologyClient` and JSON-serializes. Returns helpful error strings on missing flow ids / empty results / Neo4j unavailability rather than raising.
- `agentic_ops_common/tools/__init__.py` — re-exports the three new functions and adds them to `__all__`.
- `agentic_ops_common/tests/test_flows_tool.py` (new) — 9 tests covering JSON shape, empty-result hints, missing-id hints, error swallowing, ImportError handling, and the package re-export. Mocks the `OntologyClient` so tests run without Neo4j.

**Agent wiring**
- `agentic_ops_v6/subagents/network_analyst.py` — added `list_flows` + `get_flows_through_component` (overview-level; NA doesn't walk full flows).
- `agentic_ops_v6/subagents/instruction_generator.py` — added all three (for flow-anchored probe design).
- `agentic_ops_v6/subagents/investigator.py` — added all three (for forward mechanism-walk falsification).

**Prompt updates**
- `agentic_ops_v6/prompts/investigator.md` — new "Mechanism walks via flow tools" subsection; explicit preference for flow-anchored probes.
- `agentic_ops_v6/prompts/instruction_generator.md` — new rule #9 ("Flow-anchored probes — strongly preferred") and a "Flow tools for plan construction" section.
- `agentic_ops_v6/prompts/network_analyst.md` — paragraph added to the Mandatory-workflow section telling NA to call `get_flows_through_component(nf)` when naming an NF as fault source, with explicit guidance to stay at the overview level.

**Flow content corrections** (`network_ontology/data/flows.yaml`)
- `ims_registration` rewritten: removed bogus NRF discovery step; split MAR/SAR into the real two-pass REGISTER (first REGISTER → MAR → 401 challenge → second REGISTER with digest → SAR → 200 OK); replaced the old "Rx AAR" step 10 with N5 App Session Create (HTTP/2 SBI via SCP), with `send_reply("412")` failure mode.
- `vonr_call_setup` rewritten: inserted two N5 App Session Create steps (originating and terminating) as gates on INVITE forwarding; removed the misordered Rx AAR step; added N5 PATCH details to the response path; corrected metric name `rtpengine:current_sessions` → `rtpengine_sessions`.
- `vonr_call_teardown` step 6 rewritten from "Rx STR" to "N5 App Session Delete" with the real `"we dont have AppSessionID"` silent-skip failure mode.
- `pdu_session_establishment` / `ue_deregistration` — added missing `via: [scp]` on all SBI steps; documented SMF's local-policy fallback on PCF failure.
- `diameter_cx_authentication` — clarified UAR is skipped on fast-path re-registration when I-CSCF has a cached S-CSCF list.

**Causal-chain content correction** (`network_ontology/data/causal_chains.yaml`)
- `subscriber_data_store_unavailable` rewritten as a four-branch entry (`smf_pdu_session`, `pcscf_n5_call_setup`, `pcscf_n5_registration`, `hss_cx_unaffected` — the last is an explicit anti-hallucination negative claim). Every `observable_symptoms` entry that references a flow step carries a `source_steps` cross-reference into the corrected flows.
- **All 11 remaining causal chains upgraded to the same multi-branch + `source_steps` shape** (2026-04-23). Chains upgraded: `n2_connectivity_loss` (6 branches), `n3_data_plane_degradation` (4), `n3_data_plane_outage` (4), `ims_signaling_chain_degraded` (4), `scscf_unreachable` (5), `hss_unreachable` (6), `ims_signaling_partition` (5), `sip_transport_mismatch` (4), `dns_resolution_failure` (4), `amf_service_disruption` (5), `cascading_ims_outage` (4). Each branch carries `mechanism`, `observable_metrics`, and where applicable `discriminating_from` hints grounded in the actual Kamailio route config (`mo.cfg`, `mt.cfg`, `register.cfg`, I-CSCF UAR/LIR, S-CSCF MAR/SAR) and Open5GS source behavior (e.g. `amf_gnb_remove()` on SCTP loss, SMF local-policy fallback, UDR/PyHSS backend split). Each chain includes at least one explicit negative branch (e.g. `hss_cx_unaffected`, `data_plane_unaffected_during_blip`, `cx_unaffected`) to suppress common LLM hallucinations observed in prior batch runs. 104 ontology-common tests still pass.

### Not yet started

- **`implementation_ref` fields on flow steps.** No flow step carries one today. Policy (per this ADR): author `{file, symbol}`, omit line numbers. Ordering of rollout: start with the flows we've already rewritten (`vonr_call_setup`, `ims_registration`, `vonr_call_teardown`), then expand.
- **Loader support for the new fields.** `network_ontology/loader.py` needs to understand `implementation_ref`, `source_steps`, and the structured `failure_modes` shape so they survive the YAML → Neo4j → query roundtrip. Until the loader knows about a field, it's invisible to the agent-facing tools. This is the choke point for everything below.
- **Structured `failure_modes.{when, action, observable}` migration in `flows.yaml`.** See the dedicated section below — not started (the earlier claim that N5 steps already used this shape was stale; a grep confirms every `failure_modes` entry in the file today is a plain arrow-separated string). This is a larger piece of work with its own design questions and is scoped separately.

---

## Follow-on work

- **Loader + `implementation_ref` rollout.** Land the loader change for `implementation_ref` / `source_steps` / structured `failure_modes`, then start annotating the already-audited IMS flows (`vonr_call_setup`, `ims_registration`, `vonr_call_teardown`). This removes the "plausible but unverifiable" quality from flow content the agent currently has to take on faith.
- **Structured `failure_modes` migration in `flows.yaml`** — see the [next section](#structured-failure_modes-migration-design-notes) for the scoped design. This is the highest-leverage remaining piece because it unlocks both deterministic IG probe generation and the reverse-lookup tool.
- **Revisit `metrics.yaml` `meaning.*` blocks under the same discipline** — where a metric's reading depends on specific code behavior (like `pcscf_avg_register_time_ms`'s stall-signature semantics), anchor the `meaning.{spike,drop,zero}` text to the actual code path that produces it.
- **`components.yaml` dependency edges as typed graph edges** — they're currently prose-only (e.g. *"Provides data access to MongoDB for UDM and PCF"*). Structuring these would let `get_flows_through_component` extend into `get_dependents_of_component` without re-parsing English, and would catch "mongo → HSS"-style hallucinations mechanically (the edge simply wouldn't exist).

---

## Structured `failure_modes` migration (design notes)

**Not started. Design-only; implementation deferred.**

### Current state

Every `failure_modes` entry in `network_ontology/data/flows.yaml` is today a plain arrow-separated string. Example (`vonr_call_setup.step_2`, the N5 App Session Create):

```yaml
failure_modes:
  - "PCF unreachable → N5 POST times out → P-CSCF sends SIP 412, pcscf_sip_error_ratio spikes"
  - "UDR/MongoDB down → PCF cannot fetch subscriber policy → non-201 → SIP 412"
  - "SCP down or misconfigured → httpclient:connfail increments"
```

The causal antecedent, the code-path reaction, and the resulting observable are all concatenated into one string. Agents currently parse these with an LLM and extract the pieces on demand.

### Target state

```yaml
failure_modes:
  - when: "PCF unreachable (connect refused or HTTP/2 GOAWAY from SCP)"
    action: |
      P-CSCF's route[N5_INIT_REQ] treats the non-201 branch as a
      hard failure and calls send_reply("412","Register N5 QoS
      authorization failed"). INVITE is never relayed upstream.
    observable:
      metrics:
        - derived.pcscf_sip_error_ratio     # → 1.00
        - httpclient:connfail               # increments per attempt
      sip_response: 412
  - when: "UDR/MongoDB down, PCF reachable"
    action: |
      PCF accepts the N5 POST but cannot fetch subscriber policy
      from UDR; responds with non-201 (typically 500 or 404).
      P-CSCF same send_reply("412") branch.
    observable:
      metrics:
        - derived.pcscf_sip_error_ratio
        - fivegs_pcffunction_pa_policyamassoreq  # keeps incrementing
        - fivegs_pcffunction_pa_policyamassosucc # does NOT increment
      sip_response: 412
      discriminating_from: "PCF-unreachable branch: here connfail does NOT spike; the request lands at PCF but returns non-201."
```

### Why this is worth doing

The pure LLM-parsing delta is small — LLMs extract metric names from arrow-separated strings reliably. The value is in *what the structure lets us build around the LLM*:

**1. Deterministic IG probe generation.** The Instruction Generator currently extracts metric names from prose to populate probes. With structured `observable.metrics` it lifts the list verbatim. That tightens rule #8 in `prompts/instruction_generator.md` ("Negative-result falsification weight") — a probe is demonstrably keyed to a declared observable, not an LLM guess about what to watch. It also lets us pre-render, at loader time, a `probes_hint` block inside each step that IG can paste into its plan without any LLM re-synthesis.

**2. Reverse lookup.** A new tool of shape:

```python
async def get_flow_steps_with_observable(metric: str) -> str:
    """Given a metric name (or substring), return every flow step
    whose failure_modes declare this metric as an observable, with
    the associated `when` (cause) for each match."""
```

…would answer "which failure modes is this fired anomaly consistent with?" as a deterministic index lookup rather than an LLM inference over the full flow corpus. This feeds NA hypothesis generation directly: when the correlator reports `derived.pcscf_sip_error_ratio = 1.00`, the reverse-lookup returns every `when:` that lists it, and NA's candidate set starts from ground truth instead of from prior matching.

Today the same question requires NA to scan prose across many flow steps and pattern-match the metric name buried in a string — error-prone and token-heavy. The structured form makes it a dict lookup.

### What needs to happen (in order)

1. **Loader accepts both shapes.** `network_ontology/loader.py` must handle a `failure_modes` entry being either a string (keep the legacy arrow-format as a single opaque `description`) or a dict with `{when, action, observable}`. Survives YAML → Neo4j → query roundtrip. No schema break — both forms coexist during migration.
2. **`get_flow()` / `get_flows_through_component()` surface the structure.** Currently these wrappers pass through whatever the Neo4j client returns. Once the loader emits structured dicts, the wrappers need to preserve them without collapsing to strings. A `verbosity` arg on `get_flow` (mentioned as a Consequence risk above) becomes relevant here — the full structured form is larger.
3. **Migrate a focused first tranche.** Pick the 6–8 highest-value steps: the four N5 steps (`vonr_call_setup.step_2`, `.step_9`, `ims_registration.step_9`, `vonr_call_teardown.step_6`), the Cx steps (`ims_registration.step_3`/`.step_4`/`.step_8`, `diameter_cx_authentication.*`), and the NGAP handover step (`ue_registration.step_2`). These are the ones every recent scoring failure has touched. Migrate opportunistically beyond that.
4. **Add `get_flow_steps_with_observable` reverse-lookup tool.** New function in `agentic_ops_common/tools/flows.py`, wired to Neo4j, exposed to NA (and possibly IG). Tests that mock the client. Requires step 1 (loader) and at least a partial step 3 (enough structured content to return useful results).
5. **Update IG prompt** to lift `observable.metrics` directly into probes when a step has structured failure_modes, falling back to string-parsing when it doesn't. Small prompt delta; the real work is upstream.

### Explicit non-goals (at this stage)

- **No CI enforcement.** Per-user direction, we are relying on authoring discipline rather than building a cross-reference linter. Drift risk is acknowledged and accepted at this stage.
- **No full-corpus migration in one pass.** Both shapes coexist in the loader. A step stays on plain strings until someone has a reason to audit it. The reverse-lookup tool returns useful results as soon as the first tranche is structured; later tranches incrementally improve its recall.
- **No schema enforcement of `observable.metrics` against `metric_kb`.** That is a natural follow-on but depends on this work landing first; deferred.

### Risk

Structuring `failure_modes` without also building the reverse-lookup tool and updating the IG prompt to consume the new shape is **pure reformatting**. The LLM's ability to read the old strings is not the bottleneck. The gain comes from the tools that sit on top of the structure — if those tools don't ship, the structural work is wasted effort. Treat the migration + tool + prompt update as a single deliverable, not three independent ones.
