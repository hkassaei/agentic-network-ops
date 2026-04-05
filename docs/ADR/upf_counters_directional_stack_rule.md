# ADR: UPF Directional Counters Stack Rule

**Date:** 2026-04-05
**Status:** Accepted
**Related:**
- Critical observation: [`docs/critical-observations/run_20260405_043504_p_cscf_latency.md`](../critical-observations/run_20260405_043504_p_cscf_latency.md) (Issue 2)
- Companion ADR: [`data_plane_idle_stack_rule.md`](data_plane_idle_stack_rule.md) (same pattern, addresses Issue 1 from the same critical observation)
- Part of the v5 pipeline defined in: [`v5_5phase_pipeline.md`](v5_5phase_pipeline.md)

---

## Decision

Add a new stack rule `upf_counters_are_directional` to the network ontology (`stack_rules.yaml`) and teach the `NetworkAnalystAgent` to honor its verdict before making any claim about packet loss based on UPF GTP-U counters.

The rule:

- **Fires** whenever both `fivegs_ep_n3_gtp_indatapktn3upf` (uplink) and `fivegs_ep_n3_gtp_outdatapktn3upf` (downlink) are present in the observations dict passed to `check_stack_rules`.
- **Computes** an asymmetry percentage: `|in - out| / max(in, out) * 100`.
- **Escalates severity**: `high_temptation` when asymmetry ≥ 30% (the agent is most likely to misread it as loss), `informational` otherwise.
- **Returns a verdict** with plain-English guidance and a `correct_methods` list enumerating the three valid techniques for actual loss detection.

The NetworkAnalystAgent's prompt gains a **UPF counter asymmetry gate** in Step 3 that mandates honoring this rule's verdict. The agent MAY cite the raw counter values as context, but MUST NOT report any difference between them as packet loss. Loss claims are only valid when backed by one of the three correct detection methods.

## Context

On 2026-04-05, running the P-CSCF latency chaos scenario, the `NetworkAnalystAgent` produced this evidence line in its layer rating:

> *"UPF ingress packet total (3423) is more than double the egress total (1267) from get_nf_metrics, indicating massive packet loss."*

On this basis the agent rated the Core layer RED and listed UPF as a high-confidence suspect. The full episode and post-run analysis are captured in [`docs/critical-observations/run_20260405_043504_p_cscf_latency.md`](../critical-observations/run_20260405_043504_p_cscf_latency.md) as Issue 2.

This reasoning is **structurally wrong**, not merely inaccurate:

- `fivegs_ep_n3_gtp_indatapktn3upf` measures **uplink**: GTP-U packets received from the gNB (UE → UPF → external networks).
- `fivegs_ep_n3_gtp_outdatapktn3upf` measures **downlink**: GTP-U packets sent to the gNB (external networks → UPF → UE).

These are **independent traffic directions** accumulated over the container's entire lifetime. The difference between them reflects whatever traffic mix has historically flowed through the UPF, not any loss. Different traffic patterns produce wildly different directional ratios:

| Traffic type | Expected in/out ratio |
|---|---|
| TCP bulk download | ~1:20 (way more downlink) |
| TCP bulk upload | ~20:1 (way more uplink) |
| VoNR voice call (G.711) | ~1:1 (roughly symmetric) |
| SIP signaling at rest | ~1:1 (small, roughly symmetric) |
| Mixed browsing | ~1:10 (downlink-dominated) |

A cumulative counter pair reflects the integral of all these over time. `in=3423, out=1267` has many innocent explanations and provides **zero evidence** about packet loss. You cannot compute loss by subtracting these counters under any circumstance.

### Why this is a repeat offense

This exact misinterpretation was flagged in a previous post-mortem (run_20260405_015216_p_cscf_latency.md) and addressed via a prompt-level "Forbidden inferences" bullet that said *"Do NOT compute packet loss by subtracting cumulative UPF ingress and egress counters."*

The agent made the same error again on the very next chaos run. This is the same pattern as the idle-state issue from the companion ADR: **prompt warnings are soft constraints the agent rationalizes around under cognitive load.** A structural ontology rule that delivers a machine-evaluated verdict the agent must read is strictly stronger, and that's what worked for the idle rule.

### Why the ontology didn't already catch this

Before this ADR, `check_stack_rules` had no entry that addressed UPF counter semantics. The closest existing rule was `data_plane_dead_invalidates_sip` (condition: `gtp_indatapktn3upf = 0 AND gtp_outdatapktn3upf = 0`), which only fires when both counters are zero — the wrong check for detecting counter-subtraction misinterpretation. No rule existed to tell the agent "these are directional counters and cannot be subtracted."

The semantic information (that these are directional) exists in the baseline descriptions and metric tooltips in the ontology, but descriptive metadata is not evaluated as guidance — only rules in `stack_rules.yaml` actually make it to the agent via `check_stack_rules`.

## Design

### What the rule cannot and will not do

An important honest limitation: **you cannot reliably detect asymmetric packet loss from cumulative counters alone.** Whatever ratio you observe is the integral of all traffic that has ever flowed through the UPF. The rule does not try to determine whether a given asymmetry is "anomalous" based on the counter values themselves, because the honest answer is you can't tell.

What the rule CAN do:
1. **Forbid** the subtraction shortcut (the part the agent keeps doing wrong).
2. **Prescribe** the three correct techniques for actual loss detection (the part the agent needs to learn).
3. **Measure** the asymmetry percentage so the agent can see the magnitude of the (harmless) pattern it is tempted to misinterpret.
4. **Escalate severity** when the asymmetry exceeds 30% — not because 30% is anomalous, but because that's when the agent is most likely to be fooled into claiming loss.

### The stack rule (`stack_rules.yaml`)

```yaml
- id: upf_counters_are_directional
  rule: "The UPF GTP-U cumulative counters fivegs_ep_n3_gtp_indatapktn3upf (uplink: gNB→UPF) and fivegs_ep_n3_gtp_outdatapktn3upf (downlink: UPF→gNB) measure INDEPENDENT traffic directions over the container's lifetime. Their ratio is determined by whatever traffic has flowed historically... Asymmetry between these counters is STRUCTURAL, not pathological. You CANNOT compute packet loss by subtracting one from the other."
  condition: "both fivegs_ep_n3_gtp_indatapktn3upf and fivegs_ep_n3_gtp_outdatapktn3upf present in observations"
  implication: "FORBIDDEN INFERENCE: Do NOT report the difference between in and out counters as 'packet loss'... For actual packet loss detection, use one of these CORRECT methods: (1) rate() comparisons within the SAME direction over a time window... (2) RTCP-based metrics from RTPEngine... (3) Interface-level drop counters on the tc qdisc..."
  priority: 2
  invalidates:
    - "packet_loss_from_cumulative_counter_subtraction"
    - "in_minus_out_as_loss_calculation"
  examples:
    - "in=3423, out=1267 → 65% asymmetry — STRUCTURAL (probably TCP downloads dominated lifetime), NOT loss"
    - "in=5000, out=4900 → roughly symmetric — consistent with voice or idle traffic"
    - "in=100, out=5000 → 98% asymmetry — STRUCTURAL (probably TCP downloads), still NOT loss evidence"
    - "During active G.711 call: rate(in[2m])=20 pps vs expected 50 pps → THIS would indicate loss (same-direction rate comparison)"
```

### The evaluator (`network_ontology/query.py`)

The rule's Python evaluator in `OntologyClient.check_stack_rules`:

1. Reads both counter values from the observations dict. If either is missing, the rule does not fire.
2. Computes `asymmetry_pct = |in_total - out_total| / max(in_total, out_total) * 100`, rounded to one decimal.
3. Assigns severity:
   - `high_temptation` when asymmetry ≥ 30% (the agent is most likely to misread).
   - `informational` otherwise (still fires, but with a gentler verdict).
4. Constructs a plain-English `verdict` string tailored to the severity — explicitly telling the agent *"DO NOT report the difference as loss"* in the high-temptation case.
5. Returns a hardcoded `correct_methods` list with three entries: same-direction rate comparison, RTCP-based loss fraction, and tc qdisc drop counters.

The rule output has six fields beyond the base rule: `in_total`, `out_total`, `asymmetry_pct`, `severity`, `verdict`, `correct_methods`. The agent reads these directly — no inference required.

### Design choice — always fire when both counters are present

Unlike the idle-state rule (which only fires when rates are near-zero), this rule fires **whenever both counters are in the observations**. Rationale: the counters are virtually always present in `get_nf_metrics` output, and the rule's educational value is always relevant. There is no case where subtracting them would be valid — the always-fire design means the agent always sees the warning when it sees the counters.

The severity gradient (`informational` vs `high_temptation`) serves as the noise-vs-signal control: when asymmetry is low, the verdict is a gentle reminder; when asymmetry is high (≥30%), the verdict escalates to a loud prohibition. This keeps the guidance proportional to the risk of misinterpretation.

### Design choice — 30% threshold for high_temptation

Chosen empirically from the failing episode's data point (63% asymmetry). Any threshold below 30% would also fire on legitimate voice-call-dominated traffic patterns (which produce small asymmetries), generating noise. Any threshold above 50% would miss the exact failure case we're addressing. 30% is a middle ground that catches the dangerous cases without over-escalating on mild asymmetries.

### The prompt gate (`network_analyst.md`)

Two updates to the NetworkAnalystAgent's instructions:

**Step 2 enhancement.** Added an explicit REQUIRED bullet in the observations-dict guidance:

> **UPF directional GTP counters** (BOTH are REQUIRED): `fivegs_ep_n3_gtp_indatapktn3upf` (uplink total) AND `fivegs_ep_n3_gtp_outdatapktn3upf` (downlink total). These trigger the `upf_counters_are_directional` rule, which tells you how these counters work and how to correctly detect packet loss. Always include both.

Without this, the agent might send only one counter (or neither) to `check_stack_rules`, and the rule would silently never fire.

**Step 3 gate.** New subsection **"UPF counter asymmetry gate (MANDATORY before claiming packet loss)"** that requires the agent to:

1. Read the rule's output fields (`asymmetry_pct`, `severity`, `verdict`, `correct_methods`).
2. Treat the verdict as authoritative — the agent MAY cite raw counter values as context but MUST NOT cite the difference as loss.
3. Only accept loss claims from one of the three `correct_methods`: same-direction rate comparison, RTCP-based loss fraction, or tc qdisc drop counters.

The gate also preserves the separate bullet about pre-existing baseline noise, which is a distinct forbidden inference with its own rationale.

## Verification

Verified against five distinct scenarios after re-seeding the ontology:

| Scenario | Rule fires? | asymmetry_pct | severity |
|---|---|---|---|
| Failing episode (in=3423, out=1267) | ✅ | 63.0% | `high_temptation` |
| Roughly symmetric (in=5000, out=4900) | ✅ | 2.0% | `informational` |
| Extreme TCP-download pattern (in=100, out=5000) | ✅ | 98.0% | `high_temptation` |
| Only one counter present | ❌ (correct — both required) | — | — |
| No counters at all | ❌ (correct — not in observations) | — | — |

All five scenarios produce the correct behavior. The failing scenario from the critical observation would have received a `high_temptation` verdict explicitly telling the agent *"Asymmetry is 63.0% — HIGH temptation to misinterpret as packet loss. It is NOT. This asymmetry is structural... DO NOT report the difference as loss."*

## Files Changed

- `network_ontology/data/stack_rules.yaml` — new `upf_counters_are_directional` rule (brings total to 13 stack rules).
- `network_ontology/query.py` — evaluator branch added to `OntologyClient.check_stack_rules`. Computes asymmetry, assigns severity, constructs verdict, returns `correct_methods` list.
- `agentic_ops_v5/prompts/network_analyst.md`:
  - Step 2: added REQUIRED bullet for including both UPF directional counters in the observations dict.
  - Step 3: new **"UPF counter asymmetry gate (MANDATORY before claiming packet loss)"** subsection that mandates honoring the rule's verdict before any loss claim.

## Alternatives Considered

1. **Prompt-only rule ("don't subtract the counters").** Rejected. This was already tried after the first P-CSCF latency post-mortem and failed on the very next run. Soft prompt constraints don't hold under cognitive load. The structural ontology rule is strictly stronger because the agent must read it and it delivers a concrete verdict the agent cannot rationalize around.

2. **Detect "anomalous asymmetry" based on the counter values alone.** Rejected as structurally impossible. The honest answer is you cannot tell from cumulative counters whether a given asymmetry is anomalous — the ratio just reflects the historical traffic mix. Pretending otherwise would give the agent false confidence and produce its own class of wrong diagnoses.

3. **Fire the rule only when asymmetry exceeds a threshold.** Rejected in favor of always-fire-with-severity-gradient. An always-on rule is always educational, and the severity gradient lets the verdict scale with risk. A threshold-only approach would leave the agent without guidance for moderate asymmetries where misinterpretation is still possible.

4. **Add a derived "packet_loss_calculated_correctly" metric that the agent queries instead.** Rejected as over-engineering. The existing tools (`query_prometheus` for rate queries, `get_dp_quality_gauges` for RTCP-based loss) already expose the correct methods. The rule simply tells the agent which existing tools to use for this specific question.

5. **Expose tc qdisc drop counters as a dedicated tool.** Potentially valuable but out of scope for this ADR. Added to the follow-ups list.

## Follow-ups

This ADR addresses **Issue 2** from the four-issue critical observation. Progress on the full list:

- ✅ **Issue 1** — Idle data plane misread as failure → addressed in [`data_plane_idle_stack_rule.md`](data_plane_idle_stack_rule.md).
- ✅ **Issue 2** — Cumulative counter subtraction → addressed in this ADR.
- ⬜ **Issue 3** — Investigator made 0 tool calls; evidence fabricated in the final diagnosis. **Most critical remaining issue.** Needs Investigator prompt tightening, orchestrator-level enforcement of minimum tool calls, and recorder-level evidence citation validation.
- ⬜ **Issue 4** — Scenario design: no signaling activity during the propagation window. Requires scenario-level changes to trigger fresh SIP traffic during the `fault_propagation_time` wait.

Additional follow-ups specific to this ADR:
- **Expose tc qdisc drop counters as a dedicated tool.** Would enable the third correct loss-detection method listed in the rule. Currently the agent can only use methods 1 and 2 in practice.
- **Add a corresponding rule for RTPEngine bytes_total counters.** RTPEngine also has directional byte counters that could fall into the same trap. Consider whether a similar rule is warranted if the agent starts misinterpreting them.
