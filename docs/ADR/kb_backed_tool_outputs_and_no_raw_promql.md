# ADR: KB-backed Tool Outputs and Removal of Raw PromQL

**Date:** 2026-04-20
**Status:** Accepted — implemented in agentic_ops_v6 + agentic_ops_common
**Supersedes (in part):** agent-facing `tools.query_prometheus`

**Context source (the run that prompted this):**
- [`agentic_ops_v6/docs/agent_logs/run_20260420_194707_p_cscf_latency.md`](../../agentic_ops_v6/docs/agent_logs/run_20260420_194707_p_cscf_latency.md) — P-CSCF 2000 ms latency injection where the NA misread lifetime cumulative counters (`9348 vs 294`) as a 97% live packet-drop ratio, and the Investigator hallucinated a non-existent Prometheus metric (`upf_rx_packets_n3_total`).

**Related:**
- [`metric_knowledge_base_schema.md`](metric_knowledge_base_schema.md) — the KB that now drives tool-output annotation.
- [`agentic_pipeline_v6_implementation.md`](agentic_pipeline_v6_implementation.md) — where the annotated tool outputs land in the pipeline.
- [`anomaly_model_feature_set.md`](anomaly_model_feature_set.md) — the derived/per-UE features that `raw_sources` resolve to.

---

## Summary

Two problems, one root cause, one ADR:

1. **Problem A — counter-as-rate misreadings.** NA divided two raw cumulative Prometheus counters (`fivegs_ep_n3_gtp_indatapktn3upf = 9348` / `fivegs_ep_n3_gtp_outdatapktn3upf = 294`) and concluded "97 % packet drop at the UPF." The asymmetry was accumulated lifetime noise (UERANSIM N3 keepalives, prior healthy runs) that had been present in the baseline too. The only correct current-activity reading was in the screener's per-UE normalized flags — which NA had access to but bypassed because the raw Prometheus snapshot felt more concrete.
2. **Problem B — Prometheus metric-name hallucination.** An Investigator queried `rate(upf_rx_packets_n3_total[120s])`. That metric does not exist in this stack (Open5GS uses `fivegs_ep_n3_gtp_*` names). Prometheus honestly returned *"No results … metric may not exist or have no data."* The Investigator marked the probe AMBIGUOUS and moved on, never recovering.

Both failures share a root cause: **agents received raw Prometheus values without the semantic context that the metric KB already carries.** The fix is to stop sending bare numbers — every metric an agent sees must arrive pre-annotated with its type, unit, and KB-sourced meaning, and the raw-PromQL escape hatch that enables hallucinated names must be closed.

---

## Decision

### 1. `get_nf_metrics` is now KB-backed.

Every metric returned by `get_nf_metrics` carries:

- A `[type, unit]` tag (`[counter]`, `[gauge, count]`, `[ratio]`, `[derived, packets_per_second]`, `[uncategorized]`).
- When the raw counter's diagnostic reading lives in a derived KB entry (per-UE rate, error ratio, average processing time, …), a `— see KB: \`<layer>.<nf>.<metric>\` for the diagnostic reading` pointer.
- A header block that states the semantics of each type tag — most importantly, that a bare `[counter]` value is a lifetime total and must not be compared against another counter as a rate.

Example (before):

```
UPF (via prometheus):
  fivegs_ep_n3_gtp_indatapktn3upf = 9371
  fivegs_ep_n3_gtp_outdatapktn3upf = 294
```

Example (after):

```
UPF (via prometheus):
  fivegs_ep_n3_gtp_indatapktn3upf = 9371  [counter]  — see KB: `core.upf.gtp_indatapktn3upf_per_ue` for the diagnostic reading (current value here is a lifetime total, not a rate).
  fivegs_ep_n3_gtp_outdatapktn3upf = 294  [counter]  — see KB: `core.upf.gtp_outdatapktn3upf_per_ue` for the diagnostic reading (current value here is a lifetime total, not a rate).
```

The annotation is driven by a reverse index built from a new `raw_sources: list[str]` field on `MetricEntry`. Each derived/per-UE/ratio KB entry declares which raw Prometheus or kamcmd names feed it; the tool looks the raw name up and surfaces the KB entry. Unannotated metrics fall back to heuristic type inference, or to `[uncategorized]` when even that fails.

### 2. `query_prometheus` is removed from the agent toolset.

`tools.query_prometheus` is no longer re-exported by `agentic_ops_common.tools.__init__` and is no longer included in the Investigator's `LlmAgent.tools` list. The backend implementation remains in `tools/metrics.py` for internal use (tests, future bespoke tooling), but **no agent can call it.**

Agents now have two metric-fetch tools, both KB-backed:

- `get_nf_metrics()` — KB-annotated snapshot across all NFs.
- `get_dp_quality_gauges(window_seconds)` — pre-computed RTPEngine + UPF data-plane rates (pps, KB/s, MOS, loss, jitter).

Both tools speak the KB's vocabulary. Neither accepts free-form metric names. Hallucination becomes mechanically impossible: the only metrics an agent can see are the ones the stack actually exports, and they arrive pre-labeled.

### 3. NA prompt principle #7 — never compare cumulative counters as a rate.

New rule, placed just before principle #8 ("The observing NF can be the fault source"):

> A `[counter]` value is a **monotonic lifetime total** accumulated since the container's last start. Its absolute value carries accumulated test-traffic noise (UERANSIM keepalives, prior healthy runs, etc.) and is NOT a current rate.
>
> **Forbidden reasoning:** *"Counter A = 9348 and counter B = 294; that's 32× asymmetry so 97 % is being dropped."* Two cumulative counter values DO NOT form a rate. The asymmetry you see is lifetime noise, not a live fault.
>
> When you want to reason about current rate, ratio, or asymmetry, use the screener's enriched flags, the `[derived]`/`[ratio]` entries in `get_nf_metrics`, `get_dp_quality_gauges`, or the derived KB entry named in each counter's `see KB: …` hint.

### 4. Investigator and IG prompts — drop `query_prometheus`.

Both prompts have been updated:

- Investigator's "Tool constraint" list no longer contains `query_prometheus`. A new sentence explains that `get_nf_metrics` is KB-annotated and there is no raw-PromQL escape hatch.
- Investigator's "Negative-result interpretation" rule no longer uses `query_prometheus` as its example — rewritten around *"metric missing from `get_nf_metrics`"*.
- IG's tool catalog drops the `query_prometheus` row and rewrites the `get_nf_metrics` / `get_dp_quality_gauges` descriptions to emphasize that they return KB-annotated values.

---

## Architecture — how the three signal layers now cooperate

This change tightens the division of labor we established in the previous run's post-mortem (`run_20260420_174306_p_cscf_latency.md`, "Post-Run Analysis — The Architectural Insight"):

| Layer | Role | Now plumbed through the KB |
|---|---|---|
| Anomaly model (River HalfSpaceTrees) | "Which numbers are statistically unusual right now?" | Yes — every flag is enriched with KB `meaning` + `healthy` before reaching NA. (ADR implicit; run `run_20260420_174306_p_cscf_latency.md`.) |
| Metric KB | "What does this metric / deviation / raw name mean?" | Yes — same enrichment for screener flags; **new:** the KB also drives tool-output annotation for `get_nf_metrics`. |
| Events / correlation engine | "Is there a named multi-metric / temporal / cross-NF pattern worth promoting to a composite hypothesis?" | Yes — event triggers and `correlates_with` already live in the KB. |

The recurring pattern is: **wherever an agent was reading bare numbers, interpose the KB.** The screener flags got `meaning` in the previous round; the tool outputs get `[type, unit, see KB]` in this round.

---

## Consequences

### Positive

- The 97% packet-drop misread is now mechanically unavailable. A cumulative counter is clearly labeled; the forbidden-reasoning rule in the NA prompt names the exact pattern and forbids it.
- Metric-name hallucination is gone. Agents cannot construct a PromQL expression; the only metrics they can see are ones the stack actually exports, already named in the real Prometheus namespace.
- All three signal layers (anomaly model, tool output, events) now carry KB semantics by default. The NA does not have to guess how to read a value.
- Future KB authoring is additive: adding `raw_sources` to more derived entries only improves coverage; unannotated raw metrics fall back to `[uncategorized]` rather than breaking.

### Negative / risk

- `query_prometheus` was a true escape hatch. An investigation that genuinely needs a rate over an arbitrary window on a non-standard label selector can no longer run it directly. In practice, every scenario we've evaluated is covered by `get_nf_metrics` + `get_dp_quality_gauges`; the existing anomaly screener already does rate computation on the feature set it trains on. If a future scenario needs bespoke PromQL, we will add a KB-backed targeted tool rather than reintroduce free-form queries.
- The annotation is only as good as the KB's `raw_sources` coverage. Metrics without a `raw_sources` entry and without a heuristic match are labeled `[uncategorized]` — less useful than a fully-annotated line, but still a clear signal to the agent that the value's semantics are unknown. This ADR ships with `raw_sources` populated for UPF GTP counters and the P-CSCF REGISTER/INVITE/SIP-reply counters (the ones that bit us); expanding coverage is a follow-on task, one NF at a time as we run more chaos scenarios.
- Heuristic type inference (`_infer_raw_type` in `raw_lookup.py`) is a pattern list. It covers today's naming conventions (Kamailio groups, Open5GS `fivegs_*`, common gauge suffixes). A new exporter with a different naming style would need either `raw_sources` authored in KB or a heuristic rule added.

### Alternatives considered and rejected

1. **Keep `query_prometheus` and add "preferred tools first" guidance to the prompt.** We tried softer versions of this already — telling the Investigator to use `get_nf_metrics` first, warning about metric names, adding a Negative-result interpretation rule. The run analyzed here is the evidence that prompt-only guardrails don't hold up under LLM autocomplete pressure. A mechanical block is more reliable than another line in a prompt.
2. **Add a `list_kb_metrics` discovery tool.** Proposed as option F in the run analysis. Rejected because discovery is already solved: `get_nf_metrics` returns every metric the stack exports, now with meaning. A separate discovery call is only needed if we re-admit free-form PromQL — which we are not.
3. **Only annotate, don't remove `query_prometheus`.** Considered. Rejected because annotation doesn't prevent hallucinated metric names — the failure mode is the agent writing a PromQL expression that *Prometheus* rejects, before annotation can help.
4. **Add KB entries for every raw Prometheus counter.** Considered. Rejected because it inverts the KB's design: the KB names metrics by their diagnostic form, not their transport form. A single raw counter may feed multiple derived entries (e.g., `sl:200_replies` feeds both `sip_error_ratio` and future `sip_success_rate`); `raw_sources` is a many-to-one mapping that preserves the KB's diagnostic-first naming.

---

## Implementation manifest

### New files

- `agentic_ops_common/metric_kb/raw_lookup.py` — `resolve_raw(nf, raw_name, kb)` → `AnnotatedMetric(kind, entry, raw_type)` with `direct` / `derived` / `None` kinds.
- `agentic_ops_common/tests/test_raw_lookup.py` — 8 tests covering direct, derived, Kamailio group-prefix, and heuristic paths.
- `agentic_ops_common/tests/test_metrics_annotation.py` — 4 tests covering the annotated `get_nf_metrics` wrapper (mocks the upstream collector).

### Changed files

- `agentic_ops_common/metric_kb/models.py` — `MetricEntry` gained optional `raw_sources: list[str]`.
- `agentic_ops_common/metric_kb/__init__.py` — exports `AnnotatedMetric`, `resolve_raw`.
- `agentic_ops_common/tools/metrics.py` — `get_nf_metrics()` now post-processes upstream output through the resolver, attaches header + per-metric tags and hints. `query_prometheus()` docstring marked INTERNAL.
- `agentic_ops_common/tools/__init__.py` — `query_prometheus` dropped from re-exports and from `__all__`.
- `agentic_ops_v6/subagents/investigator.py` — `tools.query_prometheus` removed from the Investigator's tool list.
- `agentic_ops_v6/prompts/investigator.md` — tool constraint rewritten; negative-result rule rewritten without PromQL example.
- `agentic_ops_v6/prompts/instruction_generator.md` — tool catalog drops `query_prometheus`; updated `get_nf_metrics`/`get_dp_quality_gauges` descriptions.
- `agentic_ops_v6/prompts/network_analyst.md` — new principle #7 (counters-as-rates forbidden); existing "observing NF" rule renumbered to #8.
- `network_ontology/data/metrics.yaml` — `raw_sources` authored on six metrics to date (UPF gtp counters, P-CSCF avg_register_time_ms, rcv_requests_register/invite, sip_error_ratio).

### Test delta

254 → 266 passed (5 skipped unchanged). 12 new tests total: 8 for the resolver, 4 for the annotated wrapper.

---

## Follow-on work

- Populate `raw_sources` on I-CSCF, S-CSCF, SMF, and RTPEngine derived entries as we exercise those scenarios. Each additional entry removes more `[uncategorized]` labels from agent-visible tool output.
- When `get_dp_quality_gauges` is next touched, align its output with the same `[type, unit]` convention so the two KB-backed tools present metrics in one consistent vocabulary.
- Validate the NA prompt's new principle #7 against the next P-CSCF latency run. If NA still attempts a counter/counter ratio despite the rule, escalate the enforcement — e.g. have the orchestrator reject hypotheses whose only support is a pair of `[counter]` values.
