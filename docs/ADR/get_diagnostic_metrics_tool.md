# ADR: Replace `get_nf_metrics` in Agent Toolsets with a Curated `get_diagnostic_metrics`

**Date:** 2026-04-29
**Status:** Proposed — pending implementation.
**Supersedes (in part):** [`kb_backed_tool_outputs_and_no_raw_promql.md`](kb_backed_tool_outputs_and_no_raw_promql.md) — that ADR's KB-annotation of `get_nf_metrics` was a partial fix for the misread risk; this ADR addresses the residual misread + dead-counter + no-data problems by curating which metrics agents see at all.
**Related ADRs:**
- [`dealing_with_temporality_3.md`](dealing_with_temporality_3.md) — the time-awareness architecture this tool is built on top of. The new tool ships time-aware from day one.
- [`anomaly_model_feature_set.md`](anomaly_model_feature_set.md) — the 33 trained features, half of the new tool's output.
- [`anomaly_detector_replace_river_with_pyod.md`](anomaly_detector_replace_river_with_pyod.md) — the screener whose feature set defines "model features" for this tool.
- [`metric_knowledge_base_schema.md`](metric_knowledge_base_schema.md) — the metric_kb schema that gains a new `agent_exposed` field under this ADR.
- [`../critical-observations/run_20260429_175811_p_cscf_latency.md`](../../agentic_ops_v6/docs/agent_logs/run_20260429_175811_p_cscf_latency.md) — concrete episode where the agent navigated through 100+ raw metrics in `get_nf_metrics` output looking for diagnostic signal, and missed P-CSCF as a suspect despite the right counters being present.

---

## Decision

Introduce a new agent tool `get_diagnostic_metrics(at_time_ts: float | None = None)` that returns a **curated, opinionated** per-NF dictionary covering exactly the metrics that matter for agent reasoning. Two classes of content:

1. **Model features (~33)** — every key in `MetricPreprocessor.EXPECTED_FEATURE_KEYS`. Auto-derived; no hand-curation. These are "the screener's view of the world."
2. **Diagnostic supporting metrics (~10-15)** — explicitly KB-tagged via a new `agent_exposed: true` field on `metric_kb` entries. These are raw values that have proven load-bearing in the agent's hypothesis-confirmation/refutation chain — `pcscf.httpclient:connfail`, `*.dialog_ng:active`, `*.cdp:timeout`, etc.

Both classes get the same KB annotations as today's `get_nf_metrics`. The tool is **time-aware from day one** — `at_time_ts` propagates per [`dealing_with_temporality_3.md`](dealing_with_temporality_3.md).

`get_nf_metrics` stays in the codebase for the GUI / dashboards / internal use, but is **removed from the agents' tool list**. Agents only see `get_diagnostic_metrics`.

---

## Context

### What today's `get_nf_metrics` returns to the agent

About 100+ raw metric key/value pairs grouped by NF, with KB annotations applied per [`kb_backed_tool_outputs_and_no_raw_promql.md`](kb_backed_tool_outputs_and_no_raw_promql.md). The annotations correctly tag each value with its `[type, unit]` and a one-line meaning — but the underlying problems remain:

- **Lifetime cumulative counters** (~30 of them): get printed as bare numbers. Agents have repeatedly misread cumulative deltas as current rates ("9348 in vs 294 out = 97% drop"). KB annotation reduces this risk but doesn't eliminate it.
- **Dead-by-design counters** (~4): rtpengine-ctl's `Packets lost`, `average_packet_loss`, `packets_per_second_(total)`, `errors_per_second_(total)` — confirmed empirically (Apr-27) not to advance under our tc-egress fault mode. They print as 0 and the agent reads "no errors" → falsifies real hypotheses.
- **Reset-to-zero gauges**: Cx response times, MOS, jitter — display 0 when no events occurred in the window. Same "no data ≠ healthy" collision documented in the dp_quality_gauges layer-1 fix.
- **Raw size bloat**: agents navigate through dozens of metrics that aren't relevant to their hypothesis to find the few that are. Wastes tokens, increases noise-to-signal in the agent's reasoning.

### What the agent actually uses

Auditing saved run logs (about 22 chaos episodes), the agent's load-bearing tool readings concentrate in a small subset of metrics:

- The 33 model features (when present in `get_nf_metrics`'s output, in their underlying raw form).
- A handful of raw counters/gauges that are not in the model feature set but are diagnostic gold:
  - `pcscf.httpclient:connfail` / `connok` — N5 connection health.
  - `*.sl:4xx_replies`, `sl:5xx_replies` — SIP error responses.
  - `pcscf.dialog_ng:active` (raw count, not per-UE) — confirms calls are happening.
  - `*.usrloc:registered_contacts`, `usrloc_scscf:active_contacts` — confirms registrations.
  - `pcscf.tmx:active_transactions` — current SIP transaction load.
  - `*.cdp:timeout` (raw count) — Diameter timeout occurrences.
  - `*.script:register_attempts`, `script:register_success` — registration outcomes.
  - PCF `policyamassoreq` / `policyamassosucc` — N5 success rate.

That's ~10-15 metrics. Together with the 33 model features = ~45 total. Roughly half of what `get_nf_metrics` emits today, with the half that's been making the agent confused removed.

### Why this hasn't been a clean fix until now

Two earlier ADRs nudged the problem:

- [`kb_backed_tool_outputs_and_no_raw_promql.md`](kb_backed_tool_outputs_and_no_raw_promql.md) annotated `get_nf_metrics` outputs so agents see `[counter] — lifetime cumulative; not a current rate.` next to each cumulative counter. This helps but agents still ratio them.
- The Investigator's prompt was repeatedly tightened to discourage misreads. Same partial effect — prompt rules erode under load.

The structural problem is that `get_nf_metrics` was designed for a different consumer (the GUI dashboards), and we've been retrofitting it for agent use. A clean separation — different consumers get different views — is overdue.

---

## Why a new tool, not a modification of `get_nf_metrics`

Three reasons:

1. **`get_nf_metrics` has GUI consumers.** The Stack page (`gui/templates/stack.html`), live-metric panels, and operator dashboards all consume the unfiltered metric output. Restricting it would break these. They legitimately want the everything-view.

2. **Tool naming carries signal to the agent.** `get_diagnostic_metrics` reads, in the agent's prompt, as "this is what you should reason about for diagnosis." `get_nf_metrics` reads as "all the metrics for all the NFs" — and that semantic survives even with KB annotations layered on top.

3. **Behavioral isolation.** Removing `get_nf_metrics` from the agent's toolset entirely (and giving the agent only `get_diagnostic_metrics`) eliminates the "agent picks the noisier tool" failure mode. With both available, agents consistently reach for the catch-all when they should be using the curated view.

---

## The two classes of curated content, in detail

### Class 1: Model features

Every key in `agentic_ops_common.anomaly.preprocessor.EXPECTED_FEATURE_KEYS` (currently 33). These are the features the trained ECOD screener observes — by construction, the set of metrics that have been judged "worth reasoning about" by the model design. They cover:

- 8 timeout/error ratios (Cx UAR/LIR/MAR/SAR, registration reject, SIP error at I/P/S-CSCF, RTPEngine errors)
- 6 Cx response time gauges (UAR/LIR/MAR/SAR/CDP avg response time, P-CSCF register time)
- 9 per-UE normalized rates (REGISTER, INVITE, CDP replies at each CSCF, plus GTP-U at UPF)
- 3 SMF/UPF gauges (sessions per UE, bearers per UE, UPF activity ratio)
- 1 dialogs per UE
- 1 RTPEngine derived loss ratio
- 3 binary context features (calls_active, registration_in_progress, cx_active) — the [Option 1](anomaly_model_overflagging.md) state-conditioning features

For each model feature, the new tool emits:
- `value`: current (or at-time) value.
- `learned_normal`: the per-bucket mean from the trained screener (so the agent can compare "current vs trained baseline" in the same place).
- `kb_annotation`: type, unit, meaning, healthy range — same as today's `get_nf_metrics` annotation layer.
- `bucket`: the operational state bucket the value was observed in (relevant for context-conditional features).

### Class 2: Diagnostic supporting metrics

Metrics not in `EXPECTED_FEATURE_KEYS` but shown empirically to be load-bearing in the agent's reasoning chain. Tagged in the KB with a new field:

```yaml
# network_ontology/data/metrics.yaml
ims:
  pcscf:
    metrics:
      httpclient:connfail:
        type: counter
        agent_exposed: true                                          # ← new
        agent_purpose: |                                              # ← new
          Confirms whether P-CSCF can establish connections to its
          downstream HTTP services (PCF over N5, in our deployment).
          High counter value with low connok = N5 connection failure.
          Use to discriminate between "PCF is rejecting" (connections
          succeed, errors come from PCF itself) and "P-CSCF can't reach
          PCF" (connections fail entirely).
```

Initial seeding list (subject to refinement during implementation):

| KB id | Why it's diagnostic |
|---|---|
| `ims.pcscf.httpclient:connfail` | P-CSCF→PCF connection health |
| `ims.pcscf.httpclient:connok` | Counterpart to connfail; their ratio diagnoses N5 |
| `ims.pcscf.sl:4xx_replies` | P-CSCF SIP client errors |
| `ims.pcscf.sl:5xx_replies` | P-CSCF SIP server errors |
| `ims.pcscf.dialog_ng:active` | Raw active call count (not per-UE) |
| `ims.pcscf.tmx:active_transactions` | Current SIP transaction load |
| `ims.pcscf.ims_usrloc_pcscf:registered_contacts` | Raw registered UE count |
| `ims.scscf.ims_usrloc_scscf:active_contacts` | S-CSCF active contacts |
| `ims.icscf.cdp:timeout` | Cx timeout occurrences (raw) |
| `ims.scscf.cdp:timeout` | Cx timeout occurrences (raw) |
| `ims.pcscf.script:register_attempts` | REGISTER attempts |
| `ims.pcscf.script:register_success` | REGISTER successes |
| `core.pcf.fivegs_pcffunction_pa_policyamassoreq` | PCF policy requests received |
| `core.pcf.fivegs_pcffunction_pa_policyamassosucc` | PCF policy successes |
| `infrastructure.pyhss.ims_subscribers` | HSS subscriber count |

About 15 entries. Final list to be confirmed during implementation by an audit pass over saved run logs.

For each diagnostic supporting metric, the tool emits:
- `value`: current or at-time value.
- `kb_annotation`: type, unit, `agent_purpose` (the new field above; this replaces the generic `meaning.what_it_signals` for these specifically — `agent_purpose` is written for an agent reasoning about hypotheses, not for a human reading a dashboard).
- `historical_baseline` if the screener has it (for counters: a typical delta over the last training window; for gauges: the running mean).

---

## KB schema change

Add ONE field to `MetricEntry`:

```python
class MetricEntry(BaseModel):
    # ... existing fields ...
    
    # New: opt-in flag for the curated agent view. False/absent = not
    # exposed to agents in `get_diagnostic_metrics`. True = include in
    # the diagnostic supporting block.
    agent_exposed: bool = False
```

That's it. **No `agent_purpose` field.** Earlier iterations of this ADR proposed one; on review, it would duplicate content already authored across `description`, `meaning.what_it_signals` / `spike` / `drop` / `zero`, `healthy.typical_range` / `invariant`, `related_metrics` (with explicit `discriminator_for` relationship hints), `disambiguators`, and `tags`. The tool's render layer projects these existing fields into agent-readable output. A parallel `agent_purpose` field would invite drift — existing fields are the single source of truth.

For metrics where the agent needs **scale-dependent reading guidance** — `ran_ue`, `gnb`, `amf_session`, `fivegs_smffunction_sm_sessionnbr` — the right approach is the existing `tags` field: tag those metrics with `scale_dependent` and the render layer wraps the value with appropriate guidance ("check non-zero presence; absolute count varies by deployment").

Model features (the 33 in `EXPECTED_FEATURE_KEYS`) do NOT need `agent_exposed: true` — their inclusion in the new tool is automatic via the EXPECTED_FEATURE_KEYS membership check. Only the supporting metrics need explicit tagging.

---

## Tool API

```python
async def get_diagnostic_metrics(
    at_time_ts: float | None = None,
    nfs: list[str] | None = None,
) -> str:
    """Return the curated, agent-relevant metric view.
    
    Two classes of metrics are returned per NF:
    
      1. Model features — every metric the anomaly screener trains on,
         with current value + the screener's learned baseline. These
         answer "is anything statistically anomalous right now?"
      2. Diagnostic supporting metrics — KB-tagged metrics that have
         proven load-bearing in agent hypothesis-confirmation chains.
         These answer "given the hypothesis, what would we expect to
         see?"
    
    Args:
        at_time_ts: Unix timestamp to query at. None means now. Per
            `dealing_with_temporality_3.md`, when investigating an
            anomaly the agent should pass the screener's snapshot
            timestamp here, not now() — the screener's view of the
            failure window is the canonical reference.
        nfs: Optional filter — list of NF names to include. Default
            None returns all NFs the orchestrator is tracking.
    
    Returns:
        Per-NF text rendering with two clearly-labeled sections per NF:
        "MODEL FEATURES" and "DIAGNOSTIC SUPPORTING". Each metric line
        includes value, type/unit annotation, and a one-line agent-
        oriented purpose statement.
    """
```

### Output shape

```
DIAGNOSTIC METRICS (at_time = 2026-04-29T16:38:02Z, source: screener snapshot):

PCSCF:
  -- Model features --
    derived.pcscf_sip_error_ratio = 0.20 [ratio]
        learned_normal = 0.00 (bucket: (0,1))
        Sustained non-zero = P-CSCF or downstream rejecting requests.
    normalized.pcscf.dialogs_per_ue = 2.00 [derived, dialogs_per_ue]
        learned_normal = 0.48 (bucket: (1,1))
        Per-UE active call count.
    derived.pcscf_avg_register_time_ms = 0.00 [gauge, ms]
        learned_normal = 155.0 (bucket: (0,1))
        WARNING: register_attempts counter did NOT advance in this window;
        a value of 0 here means "no events," not "fast response."
    [... other model features ...]

  -- Diagnostic supporting --
    httpclient:connfail = 696 [counter]
        Confirms P-CSCF→PCF connection health. High value with low
        connok = N5 connection failure.
    httpclient:connok = 0 [counter]
        Counterpart to connfail.
    sl:4xx_replies = 12 [counter]
        P-CSCF SIP client errors.
    [... other supporting metrics ...]

ICSCF:
    [... same shape ...]
```

The two-section split is critical for the agent prompt's understanding: model features are for "is this anomalous?" reasoning, supporting metrics are for "what does the hypothesis predict, and do we see it?" reasoning.

### Time-awareness from day one

`at_time_ts: float | None = None` is on the signature from the first commit. Implementation:

- For Prometheus-backed metrics (5G core counters in model features, byte-volumes in UPF, etc.): emit PromQL with `@ at_time_ts` per [`dealing_with_temporality_3.md`](dealing_with_temporality_3.md) Layer 2.
- For container-state metrics (kamcmd outputs, rtpengine-ctl outputs): consult the closest `observation_snapshot` to `at_time_ts` per Layer 3. Return explicit "no historical snapshot near requested time" if outside the observation window.
- For computed model features (the screener's `derived.*` and `normalized.*`): replay the preprocessor's `process()` against the closest snapshot's raw metric values.

For `at_time_ts=None` (live mode), all three paths fall back to live data exactly as `get_nf_metrics` does today.

---

## Removing `get_nf_metrics` from agent tools

The four v6 LlmAgents that currently have `get_nf_metrics` in their tool list:

- `NetworkAnalystAgent` — calls it for hypothesis-formation evidence.
- `InvestigatorAgent` — calls it during probes.
- `OntologyConsultationAgent` — calls it (indirectly) when checking component health.
- `Synthesis` — does not have it; pure synthesis.

The change in each factory is mechanical: replace `tools.get_nf_metrics` with `tools.get_diagnostic_metrics` in the `tools=[...]` list.

`get_nf_metrics` itself stays in the `tools` package — it's still called by the GUI server (`gui/server.py`), the chaos framework's traffic generator (for verification snapshots), and `compare_to_baseline`'s baseline-collection path. Removing it from agent tool lists is a small, isolated change.

---

## Implementation plan — staged

Five steps, each independently testable. Layers 1-3 establish the time-awareness infrastructure that `dealing_with_temporality_3.md` will also consume — there is real synergy between the two ADRs and they should ship in coordinated order.

### Step 1: KB schema change

- Add `agent_exposed: bool = False` and `agent_purpose: Optional[str] = None` to `MetricEntry` in `agentic_ops_common/metric_kb/models.py`.
- Add the post-init validator that requires `agent_purpose` when `agent_exposed=True`.
- Bump KB schema version if any schema-version tracking is in place.
- Tests: a metric with `agent_exposed=True` but no `agent_purpose` raises ValidationError; existing KB loads without these fields succeed (backward-compatible).

**Cost**: ~30 lines + tests. No behavioral change yet.

### Step 2: Tag the initial diagnostic supporting set in metric_kb

Hand-author `agent_exposed: true` and `agent_purpose: ...` for ~15 metrics in `network_ontology/data/metrics.yaml`. List in the "Class 2: Diagnostic supporting metrics" table above; refine during this step by re-auditing run logs.

**Cost**: ~2 hours of careful authoring. No code change.

### Step 3: Implement `get_diagnostic_metrics` (live mode only)

- New file: `agentic_ops_common/tools/diagnostic_metrics.py`.
- Two private helpers: `_collect_model_features()` (calls preprocessor on a fresh metric snapshot) and `_collect_supporting_metrics(kb)` (queries the `agent_exposed=True` set).
- Top-level `get_diagnostic_metrics(at_time_ts=None, nfs=None)` orchestrates both, formats the output as documented above.
- Initial implementation: `at_time_ts` parameter accepted but raises `NotImplementedError` if non-None. Live mode (`at_time_ts=None`) works fully.
- Tests: live-mode happy path; model-feature subset assertions; supporting-metric subset assertions; NF filter; agent_exposed=False metrics absent.

**Cost**: ~250 lines + tests.

### Step 4: Wire `get_diagnostic_metrics` into agent tool lists; remove `get_nf_metrics`

Edit the four v6 LlmAgent factories. Update tests in `test_wiring.py` to assert the new tool is registered and `get_nf_metrics` is not. The `_InvestigatorTool` Literal in `models.py` (the constrained-decoder enum for the `FalsificationProbe.tool` field) needs the corresponding update.

**Cost**: ~30 lines across 4 factories + the Literal + tests. Mechanical.

### Step 5: Add time-aware mode

After [`dealing_with_temporality_3.md`](dealing_with_temporality_3.md) Layers 1-3 ship, extend `get_diagnostic_metrics` to use them:

- For Prometheus-backed metrics: use the time-anchored Prometheus tool path.
- For container-state metrics: consult `observation_snapshots` closest to `at_time_ts`.
- For computed model features: replay the preprocessor against the matched snapshot.
- Update Investigator prompt to instruct calling `get_diagnostic_metrics(at_time_ts=anomaly_screener_snapshot_ts)` for evidence about the failure window.

**Cost**: depends on Layer 1-3 shape; estimate ~150 lines of tool plumbing + prompt edits.

---

## What this fixes

- **The 100+ metric noise floor.** Agents see ~45 well-curated metrics with clear semantic roles, not 100+ raw values to navigate.
- **Lifetime-counter misreads.** The cumulative-counter family is largely absent from the curated view; what remains has KB annotation explaining its semantics.
- **Dead-counter false negatives.** `rtpengine.packets_lost` (the dead one), `packets_per_second_(total)`, `errors_per_second_(total)`, `average_packet_loss` — all four NOT in `agent_exposed: true` set. Agents stop reading "0" from them and concluding "all is well."
- **Tool-choice ambiguity.** With `get_nf_metrics` removed from the agent toolset, the agent has exactly one place to go for metric data. No "agent picks the noisier tool" failure.
- **Time-anchored evidence.** From the moment of shipping (Step 5), agent metric reads describe the failure window, not "now."

## What this does NOT fix

- **Stochastic LLM hypothesis ranking** — the call_quality_degradation 90→26 swing across runs. Documented in [`challenge_with_stochastic_LLM_behavior.md`](../critical-observations/challenge_with_stochastic_LLM_behavior.md). Independent of this ADR.
- **NA's flagged-NF blind spot** — the "an NF flagged with a direct symptom is a primary suspect, not symptomatic" pattern. Prompt-level work, separate.
- **Missing features** like DNS-direct metrics. Authoring item, separate.

---

## Risks

1. **Initial supporting set may be wrong.** The 15 diagnostic supporting metrics are a first guess. Some may not be diagnostic enough; some genuinely useful ones may be missed. Mitigation: the seeding pass in Step 2 starts from saved run logs (empirical), not from scratch. Plan to revise the set after one batch run with the new tool.

2. **`agent_purpose` needs to be agent-readable, not human-dashboard text.** Existing `meaning.what_it_signals` text is sometimes too dashboard-flavored to be useful in an agent prompt. Mitigation: the schema validator rejects empty `agent_purpose`; reviewers sanity-check each tag during the seeding pass.

3. **Removing `get_nf_metrics` from agents breaks anything that called it.** Mostly the prompts, which are documented and editable. The Investigator's `_InvestigatorTool` Literal needs updating so the constrained decoder doesn't try to emit `get_nf_metrics` as a probe tool name. Caught by the existing `test_falsification_probe_tool_enum_matches_investigator_tools` test in `test_wiring.py` — the test will fail loudly if drift occurs.

4. **Behavioral change in agent reasoning under the new tool.** The agent has been optimized (via prompt iterations) against the current `get_nf_metrics` shape. Restricting its view may cause regressions in cases where the agent was implicitly relying on a metric we didn't curate. Mitigation: validate against the saved Apr-29 batch episodes by re-running them after Step 4 ships and before Step 5 (time-aware) ships. Compare per-scenario scores.

5. **Time-aware mode (Step 5) blocks on `dealing_with_temporality_3.md` shipping.** That ADR is a peer of this one; both should ship in coordinated order. If the temporality work slips, Step 5 of this ADR slips with it. Acceptable — Steps 1-4 deliver the bulk of the noise-reduction value on their own.

---

## Open questions

1. **Supporting set scope.** Is 15 the right number? Could grow to 25 if we're more inclusive (e.g., add per-CSCF SIP method counters); could shrink to 10 if we're stricter. The Step 2 audit pass will confirm.

2. **Should `agent_purpose` replace or augment `meaning.what_it_signals`?** If they say roughly the same thing, having both is wasteful. If `agent_purpose` is consistently sharper, `meaning.what_it_signals` could be deprecated for `agent_exposed: true` metrics. Defer until the first batch of `agent_purpose` tags is written and we can compare.

3. **What about diagnostic metrics that aren't in metric_kb yet?** If an empirical audit identifies a useful metric that has no KB entry, we'd need to author the KB entry first before tagging. Worth tracking which "we'd want to expose this if it had KB coverage" candidates emerge during Step 2.

4. **Does the GUI need its own version of `get_diagnostic_metrics`?** The GUI has its own metric view (the live metrics panel on the stack page). It currently uses `get_nf_metrics` directly. If the GUI's needs ever diverge from the agent's, we may need a third tool. For now, the GUI keeps using `get_nf_metrics` and is unaffected.

5. **Should the tool also expose the screener's full flag list inline?** Today the screener's flags are in Phase 0's prompt to NA. The Investigator gets them indirectly. If `get_diagnostic_metrics` returned a `screener_flagged: true/false` annotation per model feature, the agent could see "this metric WAS flagged by the screener, here's its current value" in one place. Worth considering, but adds output volume.

---

## Why this is the right time to do this

- The new ECOD screener and the multi-phase trainer ship a clean, curated 33-feature set. The "Class 1: Model features" half of this tool is essentially free — auto-derived from existing infrastructure.
- The temporality-3 ADR establishes the time-anchoring infrastructure. The "Step 5: time-aware mode" half of this tool sits exactly on top of it.
- Today's batch run mean is 73.5%. The remaining structural ceiling is concentrated in scenarios where the agent's tool reads mislead it (call_quality_degradation, some mongodb_gone runs, the run_20260429_175811 P-CSCF case). The expected impact of giving the agent a curated view is meaningful uplift on these.

The two ADRs (this one and `dealing_with_temporality_3.md`) are mutually-reinforcing infrastructure changes that, together, define what "agents see when investigating" looks like going forward. Ship them together; the total is more than the sum. Both land in `agentic_ops_common/` (tools, KB, screener), so every agent version automatically inherits them — no parallel module needed.

## Implementation completed 2026-04-29

4. Step 1 — KB schema: agent_exposed: bool field on MetricEntry (no agent_purpose, leveraging existing KB fields).
5. Step 2 — Tagging: 16 metrics tagged agent_exposed: true; 4 tagged scale_dependent; new ims_registrar_scscf:sar_timeouts entry.
6. Step 3 — Live tool: get_diagnostic_metrics(at_time_ts, nfs) with two-block-per-NF rendering.
7. Step 4 — Wired in: Investigator + Network Analyst toolsets swapped from get_nf_metrics to get_diagnostic_metrics; prompt + Pydantic Literal updated.
8. Step 5 — Time-aware mode: Historical path replays snapshots through preprocessor; renderer handles both flat and {"metrics": ...} shapes; investigator prompt instructs
at_time_ts={anomaly_screener_snapshot_ts} for time-aware tools.

This was part of a bigger scope:

Final summary — all 8 architectural changes shipped:

dealing_with_temporality_3.md:
1. Layer 1 — Timestamp plumbing: Phase 0 captures anomaly_screener_snapshot_ts, anomaly_window_start_ts, anomaly_window_end_ts into orchestrator state.
2. Layer 2 — Time-anchored Prometheus: get_dp_quality_gauges accepts at_time_ts; _prom_query adds ?time= param; ratios return "N/A (no samples in window)" when denominator ≤ 0.
3. Layer 3 — Snapshot replay: snapshot_replay.py provides contextvar plumbing + match helpers; orchestrator publishes observation_snapshots so container-state tools can replay them.

get_diagnostic_metrics_tool.md:
4. Step 1 — KB schema: agent_exposed: bool field on MetricEntry (no agent_purpose, leveraging existing KB fields).
5. Step 2 — Tagging: 16 metrics tagged agent_exposed: true; 4 tagged scale_dependent; new ims_registrar_scscf:sar_timeouts entry.
6. Step 3 — Live tool: get_diagnostic_metrics(at_time_ts, nfs) with two-block-per-NF rendering.
7. Step 4 — Wired in: Investigator + Network Analyst toolsets swapped from get_nf_metrics to get_diagnostic_metrics; prompt + Pydantic Literal updated.
8. Step 5 — Time-aware mode: Historical path replays snapshots through preprocessor; renderer handles both flat and {"metrics": ...} shapes; investigator prompt instructs
at_time_ts={anomaly_screener_snapshot_ts} for time-aware tools.