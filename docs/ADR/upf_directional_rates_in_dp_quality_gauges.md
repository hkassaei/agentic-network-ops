# ADR: Extend UPF Directional-Counter Rule to Rate-Windowed Probes and Strip the Symmetry Myth from the KB

**Date:** 2026-05-06
**Status:** Proposed
**Related:**
- Critical observation: [`../critical-observations/why_agent_fails_with_dataplane_failure_scenarios.md`](../critical-observations/why_agent_fails_with_dataplane_failure_scenarios.md) — Issue 2: "UPF uplink and downlink asymmetry misinterpretation".
- Post-investigation analysis (2026-05-06, in-conversation): traced the symmetry myth to `network_ontology/data/metrics.yaml:2670-2671` and the rule-coverage gap to `agentic_ops_common/tools/data_plane.py:92-196` not invoking the existing `upf_counters_are_directional` stack rule.
- [`upf_counters_directional_stack_rule.md`](upf_counters_directional_stack_rule.md) — the original rule this ADR extends. The original rule fires on cumulative counters in `get_nf_metrics`; this ADR extends the same prohibition to the rate-windowed values returned by `get_dp_quality_gauges`.
- [`data_plane_quality_gauges.md`](data_plane_quality_gauges.md) — the probe surface this ADR modifies.
- [`scenario_traffic_generation.md`](scenario_traffic_generation.md) — context on why this testbed produces structurally asymmetric in/out (NULL_AUDIO voice in `ueransim/pjsua_entrypoint.sh`).

---

## Decision

Stop the Investigator from reading UPF in/out asymmetry as packet loss. Three coordinated changes ship as one PR:

1. **Strip the false symmetry invariant from the metric KB.** `network_ontology/data/metrics.yaml:2670-2671` says *"Roughly symmetric with uplink during healthy calls"* for `gtp_outdatapktn3upf_per_ue` (and the matching line for the uplink). Rewrite the invariant to state plainly that asymmetry between these two metrics is a function of traffic profile and never, by itself, evidence of loss. The same rewrite goes to the cumulative counter pair and the per-UE rate pair.
2. **Extend the `upf_counters_are_directional` stack rule to fire on rate-windowed values** (the kind `get_dp_quality_gauges` returns), not only on cumulative `get_nf_metrics` counters. Add a parallel rule branch keyed on `upf_in_pps` / `upf_out_pps` from the rate probe. Same machine-evaluated verdict, same `correct_methods` list, same severity gradient.
3. **Inline the rule's verdict into `get_dp_quality_gauges` output.** Whenever the probe emits a UPF in/out pair, it must emit the rule's verdict in the same response — not behind a separate `check_stack_rules` call the Investigator has to remember. The verdict is rendered next to the values, the same way ADR [`expose_kb_disambiguators_to_investigator.md`](expose_kb_disambiguators_to_investigator.md) does for RTPEngine errors/loss.

The Investigator prompt (`agentic_ops_v6/prompts/investigator.md`) gains one short paragraph naming the prohibition and pointing at the three correct loss-detection methods. This is the pointer; the structural change does the work.

## Context

[`upf_counters_directional_stack_rule.md`](upf_counters_directional_stack_rule.md) fixed this exact failure pattern for the NetworkAnalystAgent in April 2026. The rule fires on the cumulative counters surfaced by `get_nf_metrics` and forbids the subtraction shortcut. It worked: NA stopped misreading cumulative in/out asymmetry as loss.

The current failure relocated the same misinterpretation to the **Investigator stage**, where the agent reaches for `get_dp_quality_gauges` (rate-windowed pps over a window, default 120s), not `get_nf_metrics` (cumulative counters). The existing stack rule's pattern key (`fivegs_ep_n3_gtp_indatapktn3upf` / `fivegs_ep_n3_gtp_outdatapktn3upf`) does not match the rate-windowed values (`upf_in_pps` / `upf_out_pps`) emitted by `data_plane.py`. Rule never fires. Investigator reads `in: 8.9 / out: 6.8` and concludes "UPF dropping ~24% of packets" — the same conceptual error the rule was built to prevent, against a probe the rule doesn't cover.

The KB compounds the problem. `network_ontology/data/metrics.yaml:2670-2671` (the per-UE downlink rate metric):

> *"invariant: Per-UE — constant regardless of UE pool size. Roughly symmetric with uplink during healthy calls."*

That sentence is plain wrong for this testbed. UEs run `pjsua` with `NULL_AUDIO=yes` (`ueransim/pjsua_entrypoint.sh:71-72`), which means there is no real bidirectional G.711 media — only signaling chatter and RTP stubs. ~25% in/out imbalance (8.9 vs 6.8 pps) is the **expected steady state** of this stack, not a fault signature. The anomaly screener prints this string verbatim into every episode report, and the Investigator inherits it as a load-bearing assumption.

The companion failure modes show up in:

- `run_20260502_172113_call_quality_degradation.md:208-219` — Investigator disproves `h1` (RTPEngine) on the strength of "8.9 in vs 6.8 out → UPF dropping packets," then promotes UPF as the alternative suspect.
- `run_20260504_151835_call_quality_degradation.md` — same pattern, same probe, same conclusion.
- `run_20260504_160632_call_quality_degradation.md:40-42` — RTPEngine hypothesis disproven; alternative-path probes failed for tooling reasons (covered separately in [`nf_container_diagnostic_tooling.md`](nf_container_diagnostic_tooling.md)), so the Investigator has nothing to revise its UPF inference against.

### Why the existing stack rule didn't catch this

`network_ontology/data/stack_rules.yaml` rule `upf_counters_are_directional`:

- Fires only when **both** `fivegs_ep_n3_gtp_indatapktn3upf` and `fivegs_ep_n3_gtp_outdatapktn3upf` are present in the observations dict passed to `check_stack_rules`.
- These are the **cumulative counter** names. They appear in `get_nf_metrics` output.
- `get_dp_quality_gauges` returns a different shape (rate-windowed pps under different keys), and the Investigator typically doesn't make a separate `check_stack_rules` call against the rate output.

The rule's prohibition is correct; its trigger pattern is too narrow.

### Why the KB sentence has to go, not just be qualified

Once a sentence like "Roughly symmetric with uplink during healthy calls" appears in a metric description, every downstream surface that renders KB metadata will reproduce it. Editing one downstream rendering doesn't help — the next surface will pick it up again. The single source of truth is the KB entry; that's the only place the wrong claim has to be removed.

## Design

### KB rewrite (`network_ontology/data/metrics.yaml`)

Two metrics with their `healthy.invariant` rewritten:

`core.upf.gtp_outdatapktn3upf_per_ue` (currently lines 2670-2671):

```yaml
healthy:
  invariant: |
    Per-UE rate. Constant regardless of UE pool size. The relationship
    between this rate and uplink (gtp_indatapktn3upf_per_ue) reflects the
    traffic profile flowing through the UPF in this window — voice with
    real bidirectional media is roughly symmetric, but voice with signaling-
    only payloads, idle UEs, and asymmetric data sessions are all valid
    healthy patterns with persistent in/out imbalance. Asymmetry between
    uplink and downlink rates is NEVER, by itself, evidence of packet
    loss. To detect actual loss, use the methods listed in stack rule
    `upf_counters_are_directional`.
```

`core.upf.gtp_indatapktn3upf_per_ue` gets the symmetric rewrite. Same edit applied to the cumulative-counter pair (`fivegs_ep_n3_gtp_indatapktn3upf` / `..._out...`) so all four metrics speak with one voice.

The "roughly symmetric" claim is removed everywhere it appears in the KB. A grep over `network_ontology/data/` for `roughly symmetric|symmetric with|in/out symmetry` is part of the implementation checklist.

### Stack rule extension (`network_ontology/data/stack_rules.yaml` and `network_ontology/query.py`)

The existing `upf_counters_are_directional` rule keeps its current behavior on cumulative counters. A new fire-condition is added to the same rule (one rule, two fire conditions, one verdict template):

```yaml
- id: upf_counters_are_directional
  rule: "<existing prose, unchanged>"
  conditions:
    - all_present: [fivegs_ep_n3_gtp_indatapktn3upf, fivegs_ep_n3_gtp_outdatapktn3upf]
      window_kind: cumulative
    - all_present: [upf_in_pps, upf_out_pps]
      window_kind: rate
  implication: "<existing FORBIDDEN INFERENCE prose, unchanged>"
  correct_methods: [<unchanged list of three methods>]
  priority: 2
```

Evaluator (`OntologyClient.check_stack_rules` in `network_ontology/query.py`) handles the second condition by reading `upf_in_pps` / `upf_out_pps` from the observations dict. Asymmetry-percentage formula identical (`|in - out| / max(in, out) * 100`). Severity gradient identical (`high_temptation` ≥ 30%, `informational` otherwise). Verdict template adjusted to name the rate keys when the rate condition fires; otherwise unchanged. The verdict's `window_kind: cumulative|rate` is added so the agent knows which surface produced it.

The 30% threshold from the original rule is kept (rationale already documented in [`upf_counters_directional_stack_rule.md`](upf_counters_directional_stack_rule.md)).

### `get_dp_quality_gauges` change (`agentic_ops_common/tools/data_plane.py`)

After computing `upf_in_pps` and `upf_out_pps`, the probe calls `OntologyClient.check_stack_rules` with both values in the observations dict and renders the verdict inline. The output shape becomes:

```
UPF (window=120s):
    in  packets/sec : 8.9
    out packets/sec : 6.8
    asymmetry        : 23.6%   (|in - out| / max)
    rule verdict     : upf_counters_are_directional [severity=informational, window_kind=rate]
                       Asymmetry between in/out rates is structural, not loss.
                       Same-direction rate, RTCP loss_ratio, or tc qdisc drop
                       counters are the three valid loss-detection methods.
                       DO NOT report this asymmetry as packet loss.
```

The verdict is part of the probe's output, not a thing the Investigator must remember to fetch. This is the same delivery pattern as ADR [`expose_kb_disambiguators_to_investigator.md`](expose_kb_disambiguators_to_investigator.md): the warning rides with the value.

When asymmetry crosses 30% the verdict text becomes the `high_temptation` variant — louder, same content. When asymmetry is small the `informational` variant is rendered (still rendered — the educational value is always relevant, see the original ADR's "always fire when both counters are present" design choice).

### Investigator prompt update (`agentic_ops_v6/prompts/investigator.md`)

One paragraph under "How to read tool output":

> *UPF in/out packet rates in `get_dp_quality_gauges` (and the matching cumulative counters in `get_nf_metrics`) are independent traffic directions. Their difference is structural, never loss evidence on its own. The probe will print the `upf_counters_are_directional` rule's verdict inline; the verdict is authoritative — read it before any reasoning about UPF behavior. To detect actual loss, use one of the three methods named in the verdict (same-direction rate comparison, RTCP-derived loss_ratio, or tc qdisc drop counters).*

That's it. No further phases.

### Why ship the KB rewrite, the rule extension, and the inline rendering together

Each one alone is incomplete:

- KB rewrite alone: removes the false invariant from anomaly-screener output, but Investigator still sees `in: 8.9 / out: 6.8` from `get_dp_quality_gauges` with no warning attached.
- Rule extension alone: rule fires only if the Investigator manually calls `check_stack_rules` with the rate values, which it has no reason to do.
- Inline rendering alone: the rendering pulls the rule verdict, but the rule still doesn't match the rate keys, so the verdict is empty.

The three changes form one functional unit. Splitting them gains nothing.

## Verification

On a re-run of `run_20260502_172113_call_quality_degradation` (RTPEngine 30% packet loss):

1. `get_dp_quality_gauges` output for the UPF block contains the asymmetry percentage, the rule verdict text, and the `correct_methods` reference — without the Investigator having to call `check_stack_rules` separately.
2. The Investigator's verdict on `h1` (RTPEngine) does NOT cite UPF in/out asymmetry as loss evidence. (If it does, this ADR has failed at the rendering layer.)
3. Anomaly screener output for `gtp_outdatapktn3upf_per_ue` no longer contains "Roughly symmetric with uplink." A grep for that string over `agentic_ops_v6/docs/agent_logs/run_2026*.md` produced after the change must return zero hits in the per-bucket descriptions.

Plus:

- `test_check_stack_rules`: `upf_counters_are_directional` fires on both the cumulative-counter shape and the rate-pps shape, with `window_kind` correctly tagged in the verdict.
- `test_dp_quality_gauges_renders_upf_rule_verdict`: the probe output contains the verdict, the asymmetry percentage, and the `correct_methods` reference.
- `test_kb_does_not_claim_symmetry`: a regex check across `network_ontology/data/metrics.yaml` failing on any occurrence of `roughly symmetric|symmetric with` in the UPF metric descriptions or invariants.

## Files Changed

- `network_ontology/data/metrics.yaml` — rewrite `healthy.invariant` for `gtp_indatapktn3upf` and `gtp_outdatapktn3upf` (cumulative + per-UE rate variants — four metrics total).
- `network_ontology/data/stack_rules.yaml` — `upf_counters_are_directional` gains a second fire condition keyed on `upf_in_pps` / `upf_out_pps` and `window_kind: rate`.
- `network_ontology/query.py` — `OntologyClient.check_stack_rules` evaluator handles both fire conditions and includes `window_kind` in the verdict.
- `agentic_ops_common/tools/data_plane.py` — `get_dp_quality_gauges` calls `check_stack_rules` with both rate values and renders the verdict inline in the UPF block.
- `agentic_ops_v6/prompts/investigator.md` — one paragraph under "How to read tool output."
- Tests: `network_ontology/tests/test_stack_rules.py`, `agentic_ops_common/tools/tests/test_data_plane.py`, plus a regex-grep test added to `network_ontology/tests/test_metrics_kb.py`.

## Alternatives Considered

1. **Add a fresh stack rule rather than extending the existing one.** Rejected. The prohibition, the `correct_methods` list, the severity gradient, and the failing-mode it prevents are all identical for cumulative and rate values. Two rules with identical bodies and prose drift apart over time. One rule with two fire conditions stays consistent.

2. **Keep the "roughly symmetric" line in the KB but qualify it ("during real bidirectional voice").** Rejected. Every consumer of the KB metadata will render the qualified version, and the LLM will read past the qualifier under load. The sentence has no defenders — remove it. If a future deployment runs real bidirectional voice and observers want a symmetry expectation, they can author it back in with explicit conditional triggers and a qualifier the renderer must honor.

3. **Add a prompt-level "do not infer loss from in/out asymmetry" rule and skip the structural change.** Rejected for the canonical reason: prompt rules are soft constraints, the Investigator routinely violates them ([`upf_counters_directional_stack_rule.md`](upf_counters_directional_stack_rule.md), [`structural_guardrails_for_llm_pipeline.md`](structural_guardrails_for_llm_pipeline.md)). Whatever this ADR ships must be machine-evaluated and inline.

4. **Hide the UPF in/out values from `get_dp_quality_gauges` entirely and only expose `loss_ratio`.** Rejected. The values are useful (they confirm UPF is forwarding non-zero traffic, which rules out a dead-data-plane fault). The fix is to render them with the rule's verdict, not to suppress them.

5. **Detect when the asymmetry is "anomalous" using a learned baseline of typical asymmetry.** Rejected as not generalizing — same reasoning as the original ADR. Whatever baseline you learn is the integral of historical traffic mix; it's not a property of the deployment that survives a workload shift. The honest answer is "you cannot tell loss from asymmetry," and the rule encodes exactly that.

## Follow-ups

- Once both UPF and RTPEngine value renderings carry inline KB verdicts (this ADR + [`expose_kb_disambiguators_to_investigator.md`](expose_kb_disambiguators_to_investigator.md)), audit `get_nf_metrics` and the other tool surfaces for similar "metric value rendered without its KB-authored interpretation" gaps. Not in this ADR's scope.
- Expose tc qdisc drop counters as a first-class probe (currently the third `correct_method` is theoretically available but has no dedicated tool). The original `upf_counters_directional_stack_rule.md` already lists this as a follow-up; this ADR does not move it forward.
