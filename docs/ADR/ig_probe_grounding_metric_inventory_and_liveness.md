# ADR: Ground IG Probe Selection in the KB — Metric Inventory + Liveness Probes

**Date:** 2026-05-27
**Status:** Proposed
**Related:**
- Triggering episode: [`agentic_ops_v7/docs/agent_logs/run_20260527_210520_mongodb_gone.md`](../../agentic_ops_v7/docs/agent_logs/run_20260527_210520_mongodb_gone.md) — a slam-dunk diagnosis (`get_network_status: "mongo": "exited"`) had its confidence dragged down because the IG proposed two *unviable* probes that returned no signal → AMBIGUOUS:
    - `check_process_listeners("mongo")` → `PROBE_TOOL_UNAVAILABLE` (can't exec a killed container; minimal image lacks `ss`/`netstat`).
    - `get_diagnostic_metrics(["pcf","udr"])` for "datastore connection error counters" — PCF exposes only `fivegs_pcffunction_pa_*` policy counters; **UDR exposes no metrics at all**; that counter does not exist in this stack.
- The existing KB-candidate injection this extends: `agentic_ops_v7/guardrails/probe_selection.py` builds `{probe_candidates}` from `MetricEntry.how_to_verify_live` (coverage ~29%, per `orchestrator.py:2644`), injected at Phase 4. When coverage is empty for an NF (mongo/pcf/udr have none), the IG free-forms — and free-forming is ungrounded.
- KB data sources this grounds against: `network_ontology/data/metrics.yaml` (per-NF metric inventory via `MetricsKB.metrics[nf].metrics`) and `network_ontology/data/healthchecks.yaml` (per-NF liveness `probes` + `down_indicators`).
- IG guardrail this extends: `agentic_ops_v7/guardrails/ig_validator.py`.
- Sibling determinism-first ADRs: this is the same principle as the blast-radius and scoring work — **don't let the LLM invent; ground it in KB facts and enforce structurally.**

---

## Decision

Ground the InstructionGenerator's probe selection in two KB facts it currently ignores, so it stops proposing probes that cannot produce a signal:

1. **Metric inventory** — inject, per hypothesis NF, the full list of metrics that NF actually exposes (from the metric KB), and constrain metric probes to target only those. An NF that exposes no fitting metric gets no metric probe.

2. **Liveness probes** — inject, per hypothesis NF, the KB-authored healthcheck/liveness probe (from `healthchecks.yaml`), and for hypotheses claiming the NF is down / exited / crashed, require that probe (or `get_network_status`) and forbid in-container probes (`check_process_listeners`, `run_kamcmd`, `read_running_config`) that need the container alive.

Each grounding has three parts, mirroring the existing `{probe_candidates}` mechanism:
- **Deterministic injection** (orchestrator computes from the KB, injects into the IG prompt) — the primary mechanism; the grounding is always present.
- **Prompt rule** — tells the IG to obey the injected grounding.
- **Guardrail** (extends `ig_validator`) — structurally rejects a plan that violates the grounding and resamples once, so adherence isn't left to the model's goodwill.

Scope is fixes (1) and (2) only. The confidence-calculation fix (treating "couldn't test" differently from "tested, unclear") and raising `how_to_verify_live` authoring coverage are out of scope.

## Context

The IG generates falsification probes grounded in (a) the **tool-name list** — Rule 3 stops it inventing fake tool names — and (b) causal-chains/flows. It is NOT grounded in what each NF can actually *report*. Two gaps produced the two unviable probes:

**Gap A — no metric-inventory grounding.** The IG free-formed `get_diagnostic_metrics(["pcf","udr"])` looking for a "datastore connection error counter." `get_diagnostic_metrics` is a real tool, so Rule 3 passed it — but the metric it asked for doesn't exist on PCF/UDR (verified: PCF exposes 7 policy-association counters, UDR exposes none). The probe ran, returned "no model features," and scored AMBIGUOUS. The IG invented a plausible 3GPP-prior metric that this stack doesn't emit.

**Gap B — no liveness grounding.** The IG free-formed `check_process_listeners("mongo")`. The tool is real (Rule 3 passed it), but mongo was *killed* — you can't exec into an exited container, and the minimal mongo image lacks `ss`/`netstat` → `PROBE_TOOL_UNAVAILABLE` → AMBIGUOUS. The IG has no `get_network_status` in its toolset and the prompt has no rule against in-container probes for down NFs. The KB's *own* healthcheck for mongo authors the right liveness probe — `query_subscriber` ("Returns subscriber record" / "Timeout or connection error") — which the IG never consulted, because healthcheck probes aren't surfaced to it.

Both probes are **tool-valid but data-unviable**: the tool exists, the target (a dead container / a non-existent metric) yields no signal. They drag confidence down even though `get_network_status` already established the root cause with certainty.

The root enabler is sparse `how_to_verify_live` coverage (~29%): mongo/pcf/udr have no KB candidate probes, so the IG free-forms, and the free-form path has zero viability grounding.

## Design

### Grounding 1 — metric inventory

**Inject `{nf_metric_inventory}`.** At Phase 4, for each ranked hypothesis's `primary_suspect_nf`, the orchestrator reads `kb.metrics[nf].metrics` and renders a compact block:

```
Metrics exposed by `pcf` (the only metrics a metric probe on pcf can read):
  - fivegs_pcffunction_pa_policyamassocnbr — active AM policy associations
  - fivegs_pcffunction_pa_sessionnbr — active SM policy associations
  - … (7 total)
Metrics exposed by `udr`: NONE — udr emits no metrics in this deployment.
  Do not propose a metric probe against udr.
```

Unlike `how_to_verify_live` (~29% coverage), the metric inventory is **100% of what exists** — every metric in the KB. This is a reference constraint, not a candidate list.

**Prompt rule.** A metric probe (`get_nf_metrics`, `get_diagnostic_metrics`, `get_dp_quality_gauges`) MUST target a metric listed for that NF in `{nf_metric_inventory}`. If the NF exposes no metric that bears on the hypothesis, do NOT propose a metric probe for it — choose a different probe class (liveness, cross-NF triangulation) or omit. Never name a metric from 3GPP priors that isn't in the inventory.

**Guardrail (ig_validator extension).** For each metric-tool probe, resolve the NF(s) it targets (from `tool_args` / probe text) and reject if: the NF exposes no metrics (e.g. udr), or the probe names a metric token absent from that NF's KB inventory. Token/inventory matching, same approach as the blast-radius grounding guardrail. Reject → resample once with the offending probe quoted.

### Grounding 2 — liveness probes

**Inject `{nf_liveness_probes}`.** For each hypothesis's `primary_suspect_nf`, read `healthchecks.yaml` (directly, no Neo4j — same precedent as `path_prioritizer`/`blast_radius`) and render the NF's authored liveness probe(s) + down-indicators:

```
Liveness check for `mongo` (KB-authored):
  probe: query_subscriber(imsi=…, domain=core) — healthy if returns a record,
         unhealthy if timeout/connection error.
  down_indicators: "Connection refused or timeout".
  Container-state check: get_network_status() (running/exited).
```

**Prompt rule.** For a hypothesis claiming the NF is **down / exited / crashed / unreachable** (container-state failure), the decisive probe is the KB liveness probe above and/or `get_network_status()`. Do NOT propose in-container probes — `check_process_listeners`, `run_kamcmd`, `read_running_config`, `read_env_config` — for a down NF: they require the container to be alive and will return `PROBE_TOOL_UNAVAILABLE`, which is no signal, not a falsification.

**Guardrail.** When a plan's hypothesis is a down-class claim (detected from statement keywords OR the NF's ontology layer being NA-rated `red`), reject **any** in-container probe that targets the down suspect NF. **As-built note (diverges from the original draft):** the rejection is *unconditional* — it fires even when the plan also includes a valid liveness probe. The original draft only rejected when the plan *lacked* a liveness probe, but the triggering 5/27 mongodb_gone plan included `get_network_status` *and* `check_process_listeners`; the useless listener probe still produced the AMBIGUOUS outcome that dragged confidence, so the presence of a liveness probe must not excuse a dead-container in-container probe. An in-container probe targeting a *different, live* NF (e.g. `run_kamcmd` on pcscf to read a downstream effect during a mongo-down hypothesis) is allowed. Reject → resample once.

### Why injection (not new tools)

The IG could be given `get_nf_metric_inventory(nf)` / `get_healthcheck(nf)` tools, but a tool the model may forget to call is weaker than context that is always present. Injection is deterministic, mirrors the proven `{probe_candidates}` path, and pairs naturally with a guardrail that validates against the same KB the injection was built from.

### KB sourcing

- Metric inventory: `agentic_ops_common.metric_kb.load_kb()` → `kb.metrics[nf].metrics` (already loaded in-process for the screener; no Neo4j).
- Liveness probes: read `network_ontology/data/healthchecks.yaml` directly (`doc.get("healthchecks", doc)`), deterministic and testable, consistent with how `blast_radius.py` reads `flows.yaml`/`components.yaml`.

## Trade-offs and limitations

- **Guardrail precision is token-based, not semantic.** Resolving "which metric/NF does this free-form probe target" from probe prose is best-effort (same limitation as the blast-radius grounding guardrail). The deterministic *injection* is the primary mechanism; the guardrail is a backstop that reliably catches the clear cases (metric probe on an NF with zero metrics; in-container probe on a down NF) but may miss cleverly-worded edge cases. Acceptable — it strictly reduces unviable probes.
- **Liveness/down-class detection is heuristic.** Keying off NA down-ratings + healthcheck `down_indicators` + statement keywords ("exited", "crashed", "down", "unreachable") will catch the common cases; a hypothesis phrased obliquely might slip the guardrail (still gets the injected grounding + prompt rule).
- **Bounded by KB authoring.** If `healthchecks.yaml` lacks an NF or `metrics.yaml` is incomplete, the grounding for that NF is thin. This is the correct under-constrain-rather-than-misdirect failure mode and surfaces authoring gaps.
- **Does not fix the confidence drag directly.** Even with fixes 1+2, if some other probe legitimately comes back AMBIGUOUS, confidence still dips. The separate confidence-calc fix (out of scope here) is what would stop "couldn't test" from weighing like "tested, unclear." Fixes 1+2 attack the *generation* of unviable probes, which is the larger lever.
- **Prompt growth.** Two new injected blocks add to the IG prompt. They're compact (per-NF, only for the ranked hypotheses) and replace free-form guesswork, so the net effect on plan quality is positive.

## Implementation outline (as built)

1. **New module `agentic_ops_v7/guardrails/probe_grounding.py`** (NOT an extension of `probe_selection.py`/`ig_validator.py` — kept separate so the grounding concern and its guardrail are self-contained):
    - `metric_inventory_for_nf(nf, kb)`, `liveness_probes_for_nf(nf)`, `liveness_tool_names_for_nf(nf)` — KB lookups (`healthchecks.yaml` read directly, cached).
    - `render_metric_inventory_for_prompt(hypotheses, kb)` → `{nf_metric_inventory}`.
    - `render_liveness_probes_for_prompt(hypotheses)` → `{nf_liveness_probes}`.
    - `statement_is_down_class`, `is_down_class`, `red_layer_nfs(na_report)` — down-class detection.
    - `lint_ig_probe_grounding(plan_set, kb=None, na_red_nfs=None)` → the guardrail.
    - **Metric tools checked** = `{get_diagnostic_metrics, get_dp_quality_gauges}` (the only NF-targeted metric tools in the Investigator's literal; `get_nf_metrics` is not a registered tool here). **In-container tools** = `{check_process_listeners, run_kamcmd, read_running_config, read_env_config}`.
    - **NF universe** for resolving which NF(s) a probe targets is `components.yaml` keys ∪ metric-KB keys — broader than the metric KB alone, so an NF that exposes *no* metrics (e.g. `udr`, which has no metric block) is still recognized when a probe names it and correctly flagged as "exposes no metrics."
2. **`agentic_ops_v7/orchestrator.py`** — at the Phase 4 candidate-injection site, compute and inject `nf_metric_inventory` + `nf_liveness_probes` into state (defaulted to `""` at the state-init site so the prompt always renders), and compute `state["_na_red_nfs"]` from `na_report.layer_status`. `_ig_combined_guardrail(plan_set, na_red_nfs=None)` runs `lint_ig_probe_grounding` after the A1/A2 lint and before the sanitizer; both IG call sites (main Phase 4 + Phase 6.5 re-investigation) pass `na_red_nfs=set(state.get("_na_red_nfs") or [])`.
3. **`agentic_ops_v7/prompts/instruction_generator.md`** — the two `{...}` placeholders and the two grounding rules. Registered as deliberately-divergent from v6 (`test_application_layer_parity_with_v6.py`) with a pin test.
4. **Tests** (`agentic_ops_v7/tests/test_probe_grounding.py`, 12 cases): inventory lookups (pcf 7 / udr none / mongo subscribers); mongo liveness = `query_subscriber` not `check_process_listeners`; renderers flag udr; down-class keyword detection; metric probe vs udr rejected; metric probe naming no real pcf metric rejected; metric probe naming a real pcf metric passes; in-container probe on down mongo rejected — **including when `get_network_status` is also present**; in-container probe on a *different live* NF allowed; NA-`red`-layer triggers down-class without a keyword.

**Known limitation (as built):** the Phase 6.5 re-investigation IG reuses the injected blocks from the main Phase 4, which can be stale if its hypotheses target different NFs. The *guardrail* still enforces correctly (it loads the KB fresh and validates against whichever NF each probe names), so this only weakens the prompt-side hint for re-investigation, not the enforcement. Re-injecting per re-investigation is a follow-up if that path proves noisy.

## Validation target

- Re-run mongodb_gone: the IG no longer proposes `get_diagnostic_metrics` against udr (no metrics) or `check_process_listeners` on exited mongo; it proposes the KB liveness probe (`query_subscriber`) / `get_network_status` instead. The Investigator gets corroborating signal rather than two AMBIGUOUS no-signals; confidence is not artificially dragged down.
- Full `agentic_ops_v7` + `agentic_chaos` suites green; the existing `{probe_candidates}` behavior and `lint_ig_plan` A1/A2 checks unaffected.

## Out of scope

- Confidence-calc fix (treat `PROBE_TOOL_UNAVAILABLE` / "no such metric" as *unmeasurable*, excluded from the evidence-strength denominator). Separate ADR.
- Reducing IG over-generation (3 hypotheses where 1 sufficed) — a different lever.
- Authoring more `how_to_verify_live` coverage (29% → higher) — valuable but orthogonal; this ADR makes the free-form path safe regardless.

## Why this isn't already solved by `{probe_candidates}`

The IG already receives `{probe_candidates}` (built by `probe_selection.py` from each NF's hand-authored `how_to_verify_live` annotations). It did not prevent the two unviable probes because it is a fundamentally different kind of mechanism — a sparse, opt-in, positive *suggestion* with no enforcement. When coverage is empty (mongo/pcf/udr have none), the prompt **explicitly licenses free-forming**, and nothing validates what gets free-formed. This grounding is the complement: a complete, derived, negative *constraint* with a guardrail.

| aspect | `{probe_candidates}` (exists) | `{nf_metric_inventory}` (this ADR) |
|---|---|---|
| Says | "here are *good* probes" | "here is *everything this NF can report*" |
| Source | hand-authored `how_to_verify_live` | derived from the metric KB's actual keys |
| Coverage | ~29% (opt-in per metric) | 100% by construction |
| Nature | positive suggestion ("prefer") | negative constraint ("may not go outside") |
| Empty case | explicit license to free-form | the constraint still applies |
| Enforcement | none | guardrail rejects out-of-inventory probes |

The liveness grounding has the same shape against `healthchecks.yaml`, which (unlike `how_to_verify_live`) is authored per-NF and well-covered — mongo's liveness probe is `query_subscriber`, the only viable check for a data store with no metrics and no in-container tooling.

## Resolved decisions (from review)

1. **Separate `{nf_liveness_probes}` block** (not folded into `{probe_candidates}`). The down-NF prompt rule and the liveness guardrail both need an unambiguous "the liveness probe for this NF is X" to point at and enforce against; a merged candidate list doesn't provide that.
2. **Reject-and-resample** for both groundings (matching the existing A1/A2 IG guardrails), since the failure modes are concrete and mechanically detectable.
3. **Down-class detection = NA layer `red` rating + healthcheck `down_indicators` + statement keywords.** Statement keywords (`exited`/`crashed`/`killed`/`down`/`unreachable`/…) are read from `plan.hypothesis_statement`; NA-`red`-layer NFs are computed from `na_report.layer_status` mapped to NFs via `components.yaml` and threaded into the guardrail as `na_red_nfs`.
4. **`mongo`'s liveness probe is `query_subscriber`** (per `healthchecks.yaml`) — confirmed as the only viable liveness check (mongo exposes one metric, `subscribers`, and a killed container can't be exec'd into), so the guardrail accepts `query_subscriber` / `get_network_status` and rejects `check_process_listeners` on a down mongo.
