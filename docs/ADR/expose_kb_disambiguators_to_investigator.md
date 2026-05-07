# ADR: Expose KB Disambiguators to the Investigator at the Point of Observation

**Date:** 2026-05-06
**Status:** Proposed
**Related:**
- Critical observation: [`../critical-observations/why_agent_fails_with_dataplane_failure_scenarios.md`](../critical-observations/why_agent_fails_with_dataplane_failure_scenarios.md) — Issue 1: "Absence of RTPEngine internal error" surfaced this; the post-investigation revealed it as a systemic gap, not an RTPEngine-specific one.
- Post-investigation analysis (2026-05-06, in-conversation): KB audit (corrected via `python3 -c` walk over `network_ontology/data/metrics.yaml`) showed **17 of 19 metrics with authored `disambiguators` blocks are not agent-exposed**, and a further **13 metrics with authored `meaning` blocks (but no disambiguators) are also not agent-exposed** — total of **30 metrics with rich KB content that never reaches the LLM via the supporting block**. Even the 2 currently agent-exposed entries with disambiguators (`amf.gnb`, `amf.ran_ue`) lose their content because the supporting-block renderer also drops it. Root cause: two truncating renderers plus an `agent_exposed` flag mis-applied.
- [`rtpengine_loss_ratio_feature.md`](rtpengine_loss_ratio_feature.md) — empirical record that `errors_per_second_(total)` does not respond to tc-injected egress loss; this ADR uses RTPEngine as the worked example but applies to every disambiguator-bearing metric in the KB.
- [`get_diagnostic_metrics_tool.md`](get_diagnostic_metrics_tool.md) — the tool surface this ADR modifies.
- [`metric_knowledge_base_schema.md`](metric_knowledge_base_schema.md) — the schema this ADR honors (`disambiguators`, `meaning.zero`, `meaning.spike`, `meaning.shift`, `agent_exposed`).
- [`data_plane_quality_gauges.md`](data_plane_quality_gauges.md) — the second tool surface this ADR modifies.

---

## Decision

Surface every metric value the Investigator sees with its full KB-authored semantic block: the complete `what_it_signals` text, the value-specific interpretation (`meaning.zero` / `meaning.spike` / `meaning.shift` selected by current value vs healthy range), and every `disambiguators` entry with the partner metric's current value inlined. This applies to **every metric in the KB**, not just the rtpengine pair. The KB already contains the right reasoning across all 32 metrics; the wiring layer must stop hiding it.

Three coordinated changes ship together:

1. **Replace both truncating renderers in `agentic_ops_common/tools/diagnostic_metrics.py` with a single unified helper `_render_metric_with_full_kb_block`** that honors the full KB content for every metric, regardless of which surface (Model-features block or Diagnostic-supporting block) brought it in. The renderer iterates the KB's `disambiguators` list — each entry already names a partner via `metric: <kb_id>` — and inlines the partner's current value from the same snapshot.
2. **Set `agent_exposed: true` on all 30 KB metrics that have authored `meaning` content but currently lack the flag** (17 with disambiguators + 13 with meaning-only). The flag's purpose is to gate noise out of agent-facing output; metrics with full KB content are by definition not noise. The flag stays in the schema (KB authors may still mark a metric as not-exposed for rare deduplication cases), but its default behavior aligns with the authoring signal.
3. **Extend `get_dp_quality_gauges` (`agentic_ops_common/tools/data_plane.py`) to call the same renderer for the metrics it surfaces** so the data-plane probe carries the same KB depth as the diagnostic-metrics probe. RTPEngine `loss_ratio` and `errors_per_second` co-render in this output via the disambiguator pointer they already share in the KB; no per-tool special-casing.

The Investigator prompt (`agentic_ops_v6/prompts/investigator.md`) gains one paragraph naming the disambiguator pattern. The structural change does the work; the prompt sentence is the pointer.

## Context

Reading the rtpengine episode `run_20260502_172113_call_quality_degradation.md` produced a localized hypothesis: "the LLM doesn't see the rtpengine errors-vs-loss disambiguator." That hypothesis is correct but understates the scale by an order of magnitude.

### KB inventory

| Property | Count |
|---|---|
| Total metric entries in `network_ontology/data/metrics.yaml` | 108 |
| `agent_exposed: true` | 16 (2 with `meaning`+`disambiguators`: `amf.gnb`, `amf.ran_ue`; 14 "bare" exposed entries with no rich KB content) |
| With authored `meaning` block | 32 |
| With authored `disambiguators` block | 19 |
| With `meaning` + `disambiguators` but **not** agent-exposed | **17** |
| With `meaning` only (no disambiguators) but **not** agent-exposed | **13** |
| **Total metrics with rich content not reaching the LLM via the supporting block** | **30** |

The 17 disambiguator-bearing metrics that are NOT agent-exposed:

- I-CSCF (5): `cdp_avg_response_time`, `rcv_requests_invite_per_ue`, `rcv_requests_register_per_ue`, `uar_timeout_ratio`, `lir_timeout_ratio`
- P-CSCF (4): `avg_register_time_ms`, `dialogs_per_ue`, `rcv_requests_invite_per_ue`, `rcv_requests_register_per_ue`
- RTPEngine (2): `errors_per_second`, `loss_ratio`
- S-CSCF (2): `mar_avg_response_time`, `rcv_requests_register_per_ue`
- SMF (1): `sessions_per_ue`
- UPF (3): `gtp_indatapktn3upf_per_ue`, `gtp_outdatapktn3upf_per_ue`, `activity_during_calls`

The 13 meaning-only metrics that are NOT agent-exposed:

- I-CSCF (4): `lir_avg_response_time`, `sip_error_ratio`, `uar_avg_response_time`, `cdp_replies_per_ue`
- P-CSCF (1): `sip_error_ratio`
- S-CSCF (7): `mar_timeout_ratio`, `sar_timeout_ratio`, `cdp_replies_per_ue`, `rcv_requests_invite_per_ue`, `registration_reject_ratio`, `sar_avg_response_time`, `sip_error_ratio`
- SMF (1): `bearers_per_ue`

### What's authored, and what reaches the LLM

The disambiguator content on these 17 metrics is exactly the reasoning the Investigator needs at the point of observation:

- I-CSCF `cdp_avg_response_time` → `disambiguators[uar_timeout_ratio].separates: "Pure HSS latency vs. HSS partial partition"` and `disambiguators[scscf.mar_avg_response_time].separates: "I-CSCF↔HSS only ... vs. HSS-wide (both CSCF response times spike)"`.
- S-CSCF `mar_timeout_ratio` → `disambiguators[icscf.uar_timeout_ratio].use: "Both timeout types confirm HSS partition"`.
- UPF `gtp_indatapktn3upf_per_ue` → `disambiguators[gtp_outdatapktn3upf_per_ue].use: "Asymmetry between these two is diagnostic for directional faults"` (and the partner ADR `upf_directional_rates_in_dp_quality_gauges.md` rewrites this exact pair to remove the false symmetry claim).
- RTPEngine `errors_per_second` → the two disambiguator entries quoted in the previous version of this ADR.

None of this content reaches the LLM. The rendering layer truncates it on every path:

`agentic_ops_common/tools/diagnostic_metrics.py:397-422` (Model-features path):

```python
if entry and entry.meaning and entry.meaning.what_it_signals:
    first_sentence = entry.meaning.what_it_signals.split(".")[0].strip()
    if first_sentence:
        lines.append(f"        {first_sentence}.")
```

First sentence of `what_it_signals` only. No `meaning.zero`, `meaning.spike`, `meaning.shift`. No `disambiguators`. For `errors_per_second`, the first sentence reads as a complete description of relay-loop errors — the crucial follow-on sentences ("insensitive to packet loss occurring elsewhere," "= 0 does NOT exonerate") are stripped.

`agentic_ops_common/tools/diagnostic_metrics.py:425-490` (Diagnostic-supporting path, the `agent_exposed=true` branch):

```python
if entry.description:
    first_sentence = entry.description.split(".")[0].strip()
    if first_sentence:
        lines.append(f"        {first_sentence}.")
```

First sentence of `description` only. Same pattern, different field. Disambiguators never read.

The conclusion is plain: **the entire `disambiguators` schema is dead text as far as the LLM is concerned.** Engineers authored 19 disambiguator blocks; the LLM has read zero of them. The two disambiguator-bearing metrics with `agent_exposed: true` (`amf.gnb`, `amf.ran_ue`) are exposed in name only — the supporting renderer still drops their disambiguator content. The remaining 14 currently agent-exposed entries are bare counters (`httpclient:connfail`, `sl:4xx_replies`, `cdp:timeout`, etc.) with no `meaning` or `disambiguators` to drop, so they're not affected by the truncation; they are simply unaffected.

### Why this manifested as an RTPEngine bug

The RTPEngine call-quality scenario reruns frequently and has a clear ground truth (tc loss on one container's veth), so its mis-diagnoses are visible. The same systemic issue is silently in play whenever the Investigator looks at any Diameter timeout, any SIP error ratio, any UPF rate metric, any P-CSCF / I-CSCF / S-CSCF interaction. The LLM is operating on truncated metric semantics across every IMS scenario this stack runs — 30 metrics' worth of authored content, hidden.

### Why this is a structural, not a prompt, fix

A prompt-level rule ("when you see a metric value, also recall its disambiguator") would have to install 19 disambiguator pairs into the LLM's working memory and survive cognitive load. That fails for the same reasons every soft prompt rule fails — see [`upf_counters_directional_stack_rule.md`](upf_counters_directional_stack_rule.md) and [`structural_guardrails_for_llm_pipeline.md`](structural_guardrails_for_llm_pipeline.md). The right fix is to never present a value without its disambiguator — the agent doesn't need to remember a rule when the rule is on the same line as the value.

This is a tool-output design problem, not a prompt-engineering problem.

### Why one fix covers all 30 metrics with rich content

Every disambiguator entry across the KB has the same shape:

```yaml
disambiguators:
- metric: <other_kb_id>
  separates: <free text>
```

A single renderer that iterates this list, looks up the partner's current value from the same snapshot the metric came from, and inlines `vs <partner_kb_id> (current = <partner_value>): <separates text>` works uniformly for I-CSCF Diameter timeouts, S-CSCF SAR latencies, UPF directional rates, RTPEngine errors, and every other entry. The same renderer also emits the full `meaning.*` block for the 13 metrics that have meaning but no disambiguators — they get the `what_it_signals` + `meaning.zero/spike/shift/drop` content rendered in full. There is no per-NF or per-metric special-casing required. The fix is a renderer rewrite plus an `agent_exposed` flag flip; both are bounded mechanical changes.

## Design

### Renderer rewrite (`agentic_ops_common/tools/diagnostic_metrics.py`)

Replace `_render_model_feature` and `_render_supporting_metric` with a single helper `_render_metric_with_full_kb_block(kb_id, value, kb, raw_snapshot, learned_means)`. Output shape per metric:

```
<fkey> = <value> [<type>, <unit>]
    learned_normal = <learned>            (when present)
    healthy_range  = [low, high]          (from KB; always present when KB has it)
    interpretation = <selected from meaning.zero | meaning.spike | meaning.shift | meaning.drop
                      based on whether value is below, above, or within healthy_range>
    what_it_signals: <full multi-sentence text — never truncated>
    NOTE: <healthy.pre_existing_noise, when present>
    disambiguators:
      vs <partner_kb_id> (current = <partner_value> | not in snapshot):
        <separates text>
      vs <partner_kb_id> (current = <partner_value> | not in snapshot):
        <separates text>
```

Behavior contract:

- `what_it_signals` is rendered in full. The first-sentence shortcut is removed from both render paths.
- The value-specific interpretation is selected deterministically from `meaning`:
  - `value == 0` and `healthy.typical_range[0] == 0` and `meaning.zero` present → render `meaning.zero`.
  - `value > healthy.typical_range[1]` → render `meaning.spike` (or `meaning.shift` if `spike` absent).
  - `value < healthy.typical_range[0]` (non-zero) → render `meaning.drop` (or `meaning.shift` if `drop` absent).
  - Within healthy range with significant baseline drift → `meaning.shift`.
  - No matching authored variant → omit the `interpretation` line cleanly. (The KB does not promise every metric authored every variant.)
- Every entry in `disambiguators` is rendered. The partner's current value is fetched from the same `raw_snapshot` (or `features` map for model-feature partners) using the partner's KB id; the lookup is uniform and does not require the partner to be in the same NF.
- `entry.description` and `entry.healthy.pre_existing_noise` continue to render (the latter is the famous `httpclient:connfail` baseline trap and similar — already first-sentence-truncated; the rewrite renders them in full).
- The same helper is used by the Model-features path AND the Diagnostic-supporting path. The two blocks still exist (they describe different sources — preprocessor outputs vs raw kamcmd/Prometheus values), but the per-entry rendering is identical.

The helper is wired into `_render_two_block_per_nf` (`diagnostic_metrics.py:286`) replacing the existing branch logic. The two `feats_by_nf` / `supporting_by_nf` paths converge on the same renderer call.

### KB flag flip (`network_ontology/data/metrics.yaml`)

Set `agent_exposed: true` on every metric that has authored `meaning` content (whether or not it also has `disambiguators`). The 30 affected metrics are enumerated in the Context inventory above (17 with disambiguators + 13 with meaning-only). The flip is mechanical — no other field changes. The KB gains a brief authoring rule documented in [`metric_knowledge_base_schema.md`](metric_knowledge_base_schema.md): *"Any metric with authored `meaning` or `disambiguators` content should be `agent_exposed: true`. The flag exists to suppress duplicates or implementation-detail metrics, not to gate the KB's reasoning."*

A new unit test `test_kb_authoring_invariants` enforces the rule going forward: any metric entry with `meaning` or `disambiguators` populated but `agent_exposed: false` (or unset) fails the test. This catches future drift at PR time, not in production.

### `get_dp_quality_gauges` change (`agentic_ops_common/tools/data_plane.py`)

After computing the per-NF gauge values, the probe routes each value through the same `_render_metric_with_full_kb_block` helper used by `get_diagnostic_metrics`. The probe contributes the values; the renderer contributes the KB depth. Specifically:

- RTPEngine block emits `errors_per_second` and `loss_ratio` together (the disambiguator pointer between them does the pairing structurally — no co_render_with field needed).
- UPF block emits `gtp_indatapktn3upf_per_ue` and `gtp_outdatapktn3upf_per_ue` together with the rule verdict from [`upf_directional_rates_in_dp_quality_gauges.md`](upf_directional_rates_in_dp_quality_gauges.md) inlined; the disambiguator entry between the pair adds its own `separates:` text on top.
- The Prometheus query template at lines 22-39 is extended to fetch the metrics needed for the disambiguator partners (today only one direction is queried for some entries).

### Investigator prompt update (`agentic_ops_v6/prompts/investigator.md`)

One paragraph under the existing "How to read tool output" section:

> *Every metric value rendered to you carries its own KB block — `what_it_signals`, the interpretation matching the current value, and a `disambiguators` list with each partner metric's current value already filled in. Read the disambiguators **before** treating any single value (especially a zero) as confirmation or falsification. Disambiguators are the KB's authoritative reading of how this metric behaves with respect to nearby metrics; they were authored precisely to prevent the local-zero-as-exoneration trap and equivalent local-misread traps for latency, timeout, and rate metrics across every NF.*

No more than that.

### Why no `co_render_with` schema field

The previous draft of this ADR proposed adding `co_render_with: list[str]` to pair RTPEngine errors and loss explicitly. With the systemic framing, that is redundant: the `disambiguators` list already names every partner metric via its `metric:` field on every entry. The renderer derives the pairing from the disambiguator pointer; no new schema field, no per-pair authoring step.

The dropped field saves work and removes a duplicate source of truth.

### What this does NOT change

- KB authoring effort. `meaning` and `disambiguators` are already populated for the metrics that matter. This ADR honors them; it does not require new authoring.
- The model feature set. Every metric that's currently a model feature stays one; the renderer change only affects how its value reaches the LLM.
- The set of probes the Investigator can call. Every existing probe keeps its name and signature.
- The two-block layout (Model features vs Diagnostic supporting). Both blocks still exist; both call the same per-entry renderer. The blocks describe data provenance, not rendering depth.

## Verification

The verification bar this ADR sets: **every single metric in the KB renders every authored field in full to the LLM, with zero truncation, and a regression on any one of them fails CI.** Sampling is forbidden. The previous truncation went undetected for weeks because no test enumerated the full set; this ADR makes that impossible.

### Per-metric exhaustiveness (the headline test)

A single parametrized test, `test_every_kb_metric_renders_in_full`, enumerates **every metric entry with authored `meaning` content in `network_ontology/data/metrics.yaml` at test-collection time** (not a hand-curated list — discovered by walking the loaded `MetricsKB`) and runs one parametrized case per metric. The current count is 32 metrics with `meaning` (out of 108 total entries; the bare-counter entries without rich KB content are not in scope for the renderer-depth test). If a metric is added to the KB with authored `meaning`, the test grows automatically. If an entry is renamed, the test fails until the rename is consistent.

For each metric, the test loads a synthetic snapshot containing that metric's value plus the values of every metric named in its `disambiguators[].metric` pointers, calls `_render_metric_with_full_kb_block`, and asserts every one of the following invariants on the rendered output:

1. **`what_it_signals` rendered verbatim.** The KB string (after stripping leading/trailing whitespace and collapsing internal whitespace) appears in the rendered output. No first-sentence shortcut. No length cap. No paraphrase.
2. **`description` rendered verbatim.** Same rule. (The supporting renderer's `description.split(".")[0]` truncation is gone and stays gone.)
3. **Every authored variant of `meaning.*` is reachable.** For each variant the KB entry authored (`zero`, `spike`, `shift`, `drop`, `nominal`, etc.), driving the synthetic value into the regime that selects that variant must produce the verbatim variant text in the rendered output. The test loops over the variants the KB authored for this entry and asserts each one renders correctly under its triggering value.
4. **Every `disambiguators` entry rendered verbatim.** For every entry in the metric's `disambiguators` list, the rendered output contains the partner's KB id, the partner's current value from the snapshot, AND the verbatim `separates` text. Missing any one of the three is a failure. The count of disambiguator blocks rendered must equal `len(entry.disambiguators)` exactly — not "≥ 1," not "approximately."
5. **`healthy.pre_existing_noise` rendered verbatim** (when present). The `httpclient:connfail` baseline trap is the canonical example; today's renderer truncates it to first sentence, the new renderer must not.
6. **`healthy.typical_range` rendered.** Always, when present. The agent reads "current = X vs healthy [low, high]" as a unit and the range is non-optional context.
7. **No string-shortening operations applied to any KB-sourced field.** The test introspects the rendered output's substrings against the source KB strings character-by-character. If `len(rendered_field) < len(kb_field)` for any KB-sourced field, the test fails with the per-character diff.

The test runs `pytest --tb=short` and reports per-metric pass/fail. A passing run shows ≥32 PASSED (one per `meaning`-bearing metric). A failure shows exactly which metric and which invariant.

### Anti-truncation source-level guards

A second test, `test_renderer_source_contains_no_truncation_patterns`, is a static-analysis guard over `agentic_ops_common/tools/diagnostic_metrics.py` and `agentic_ops_common/tools/data_plane.py`. It rejects any of the following patterns in the source:

- `\.split\(\s*["']\.["']\s*\)\s*\[\s*0\s*\]` — first-sentence shortcut (the current bug).
- `\.partition\(\s*["']\.["']\s*\)` — same shape, different stdlib call.
- `\[\s*:\s*\d+\s*\]` applied to any variable whose name contains `description`, `meaning`, `signal`, `noise`, `separates`, `disamb`, `what_it`, `interpretation` — a slice on a KB-sourced string.
- `\.splitlines\(\)\s*\[\s*0\s*\]` — first-line shortcut.
- Any literal `MAX_LEN`, `MAX_CHARS`, `truncate`, or `…` near a KB field reference.

The static check fails CI before the parametrized test even runs. Adding a new truncation pattern to the source is caught at PR review.

### KB authoring invariant

`test_kb_authoring_invariants` enforces that **every** KB entry with authored `meaning` or `disambiguators` content has `agent_exposed: true`. This is the test that would have caught today's gap before it shipped: 17 entries with `disambiguators` and 13 more with `meaning`-only — 30 entries total — would all fail today. After the ADR's KB flip, all 32 `meaning`-bearing entries (including the 2 already-exposed `gnb`/`ran_ue`) pass. Future entries authored without the flag fail at CI.

### Per-metric inventory snapshot

A test, `test_kb_metric_inventory_snapshot`, asserts the exact count and identifier list of disambiguator-bearing metrics matches a snapshot file `tests/snapshots/kb_metric_inventory.txt`. Adding a metric to the KB requires updating the snapshot in the same PR — making the addition visible at review time and forcing the author to confirm the new entry is fully authored. Removing a metric requires snapshot update too. The snapshot is the canonical "what does the KB cover" inventory.

### Routing coverage

`test_dp_quality_gauges_routes_every_metric_through_full_renderer` enumerates every metric `get_dp_quality_gauges` is documented to emit, runs the probe, and asserts the output for each metric contains the same KB depth signature (full `what_it_signals` + every disambiguator) that the parametrized test verified. No metric the probe emits may bypass the unified renderer.

### End-to-end on real episodes

After the unit tests pass, re-run two real chaos scenarios and assert directly on the resulting episode logs:

1. `run_20260502_172113_call_quality_degradation` (RTPEngine 30% loss) re-run — the Investigator's tool output for `rtpengine` must contain both `errors_per_second_(total)` and `loss_ratio` with the full disambiguator block inlined; the verdict on `h1` must not be DISPROVEN.
2. A chaos scenario exercising HSS or CSCF metrics (e.g., `hss_unresponsive`, `p_cscf_latency`) — the Investigator's tool output for the load-bearing metric of that scenario must contain the full `what_it_signals` and all authored disambiguators with partner values inlined.

These end-to-end checks are corroborating evidence; the per-metric parametrized test is the contract.

### Summary of the test set

| Test | Scope | Failure mode it prevents |
|---|---|---|
| `test_every_kb_metric_renders_in_full` (parametrized over all 32) | Per-metric, every authored field | Any single metric losing any field — including the rtpengine case that started this |
| `test_renderer_source_contains_no_truncation_patterns` | Renderer source | A future edit reintroducing `.split(".")[0]` or any sibling shortcut |
| `test_kb_authoring_invariants` | KB authoring | A new metric authored with disambiguators but `agent_exposed: false` |
| `test_kb_metric_inventory_snapshot` | KB inventory | A metric being added or removed silently |
| `test_dp_quality_gauges_routes_every_metric_through_full_renderer` | Probe routing | A probe-local renderer being added that bypasses the unified helper |
| End-to-end re-runs | Pipeline | Behavior regression that the unit tests can't catch |

## Files Changed

- `agentic_ops_common/tools/diagnostic_metrics.py` — replace `_render_model_feature` and `_render_supporting_metric` with `_render_metric_with_full_kb_block`. Update `_render_two_block_per_nf` to call it from both branches. Remove first-sentence truncation throughout.
- `agentic_ops_common/tools/data_plane.py` — route every emitted metric through `_render_metric_with_full_kb_block`. Extend the Prometheus query template to fetch metrics needed for disambiguator partners.
- `network_ontology/data/metrics.yaml` — set `agent_exposed: true` on the 29 metrics enumerated in Context (the full list is in the audit script; this is a mechanical edit).
- `network_ontology/tests/test_metrics_kb.py` — new `test_kb_authoring_invariants` (meaning/disambiguators → agent_exposed) and `test_kb_metric_inventory_snapshot` (exact count and identifier list of disambiguator-bearing metrics).
- `network_ontology/tests/snapshots/kb_metric_inventory.txt` — canonical inventory the snapshot test pins. Updates require explicit PR review.
- `agentic_ops_common/tools/tests/test_diagnostic_metrics.py` — `test_every_kb_metric_renders_in_full` (parametrized over the full KB; one case per metric; per-field verbatim assertions for `what_it_signals`, `description`, every authored `meaning.*` variant, every `disambiguators` entry, `healthy.pre_existing_noise`, `healthy.typical_range`); `test_disambiguator_partner_inlined`; `test_renderer_source_contains_no_truncation_patterns` (static-analysis guard rejecting `.split(".")[0]`, `.partition(".")`, `[:N]` slices on KB-sourced strings, `.splitlines()[0]`, `MAX_LEN`/`MAX_CHARS`/`truncate`/`…` near KB field references).
- `agentic_ops_common/tools/tests/test_data_plane.py` — `test_dp_quality_gauges_routes_every_metric_through_full_renderer` enumerating every emitted metric and asserting the same KB depth signature.
- `agentic_ops_v6/prompts/investigator.md` — one-paragraph addition under the tool-output reading section.
- `docs/ADR/metric_knowledge_base_schema.md` — append the authoring rule (any metric with `meaning` or `disambiguators` is `agent_exposed: true`).

## Alternatives Considered

1. **Fix only the RTPEngine pair (the original ADR draft).** Rejected after the systemic finding. Patching one metric pair leaves 29 others with the same defect, manifesting in every IMS scenario this stack runs. The renderer rewrite is the same work; the KB flip is mechanical; doing only RTPEngine guarantees re-encountering the issue on the next chaos scenario.

2. **Add a `co_render_with` schema field for explicit pairings.** Rejected as redundant with the existing `disambiguators[].metric` pointer. Two sources of truth for the same relationship invite drift. The renderer reads disambiguators directly.

3. **Prompt-level fix: tell the Investigator to always check disambiguators.** Rejected for the canonical reason — soft prompt rules don't survive cognitive load, and this ADR would have to install 31 partner pairings into the LLM's working memory simultaneously. Documented at length in [`structural_guardrails_for_llm_pipeline.md`](structural_guardrails_for_llm_pipeline.md).

4. **Make the renderer truncate `what_it_signals` to a longer fixed length (e.g., first three sentences).** Rejected as arbitrary. Some `what_it_signals` are short; some need every sentence; cutting at any fixed boundary loses load-bearing content for some entries. Render in full and let the KB authors keep them appropriately sized.

5. **Drop `agent_exposed` entirely; render every KB entry with content.** Considered. Rejected for now — there are legitimate uses of `agent_exposed: false` (an authored entry that's a duplicate of another, or a metric kept in the KB for engineer reference but not for agent reasoning). The flag stays; the authoring rule says "if you wrote disambiguators, set the flag true," enforced by the new test. Future cleanup may collapse this further if the false case turns out to have no real use.

6. **Move the rendering depth into the prompt instead of the tool output.** Rejected. The prompt is shared across episodes; the metric values are per-episode. Carrying KB depth in the prompt requires either a static prompt table (which becomes stale) or per-episode prompt construction (which loses caching). The tool output is the right place — it's already per-episode, already has the values, and now has the KB depth alongside.

## Follow-ups

- Once the unified renderer is in place, audit `get_nf_metrics` for the same truncation pattern (the function is older and predates the KB depth this ADR introduces). The renderer helper is reusable; the audit is a follow-up to confirm whether the same change applies. Out of scope for this ADR.
- Reconsider whether the Model-features and Diagnostic-supporting blocks should remain visually separate now that they render with identical depth. The blocks describe data provenance (preprocessor output vs raw snapshot), which is engineer-relevant but may not earn its keep in agent-facing output. Out of scope.
- Author `disambiguators` blocks for the small number of KB entries that have `meaning` but no disambiguators (currently 1 of 32). The renderer handles their absence cleanly; this is an authoring follow-up, not a code change.
