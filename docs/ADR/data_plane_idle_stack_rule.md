# ADR: Data Plane Idle-State Stack Rule

**Date:** 2026-04-05
**Status:** Accepted
**Related:**
- Critical observation: [`docs/critical-observations/run_20260405_043504_p_cscf_latency.md`](../critical-observations/run_20260405_043504_p_cscf_latency.md)
- Depends on: [`dealing_with_temporality_2.md`](dealing_with_temporality_2.md) (time-windowed tools that produce the rate metrics this rule evaluates)
- Part of the v5 pipeline defined in: [`v5_5phase_pipeline.md`](v5_5phase_pipeline.md)

---

## Decision

Add a new stack rule `idle_data_plane_is_normal` to the network ontology (`stack_rules.yaml`) and teach the `NetworkAnalystAgent` to honor it before rating the Core or IMS layer as degraded based on zero data plane throughput.

The rule:

- **Fires** when any of the data plane rate metrics (`upf_kbps`, `upf_in_pps`, `upf_out_pps`, `rtpengine_pps`) is near zero (≤ 0.5) in the observations passed to `check_stack_rules`.
- **Cross-checks** whether any active call indicator is present: `dialog_ng:active > 0` at P-CSCF/S-CSCF, or `owned_sessions > 0` / `total_sessions > 0` at RTPEngine.
- **Returns a verdict** along with the triggered rule: either *"No active call — zero data plane rates are EXPECTED idle state. DO NOT flag as degraded"* or *"Active call detected — zero rates may be a real problem."*

The NetworkAnalystAgent's prompt gains an **Idle-state gate** in Step 3 that requires the agent to read this verdict and apply it before marking any layer YELLOW/RED on the basis of zero data plane metrics. If the rule fires with `active_call_detected: False`, the agent MUST rate Core and IMS as GREEN with respect to data plane metrics and MUST NOT list UPF or RTPEngine as suspect components.

## Context

On 2026-04-05, the `NetworkAnalystAgent` ran against a P-CSCF latency scenario (500ms latency injected on the `pcscf` container) and produced a diagnosis that scored **35%**. Full episode captured in [`docs/critical-observations/run_20260405_043504_p_cscf_latency.md`](../critical-observations/run_20260405_043504_p_cscf_latency.md).

The critical observation documents four separate failure modes in that run. This ADR addresses the first of them — the "idle data plane misread as failure" problem — which produced the following evidence in the agent's output:

> *"UPF out packets/sec: 0.0 from get_dp_quality_gauges(window_seconds=60)"*
> *"RTPEngine shows 0 packets/sec, indicating no voice media traffic is flowing"*

On this basis the agent rated the Core layer RED and listed UPF as a high-confidence suspect. But no voice call was actually in progress at the moment the agent queried the gauges. Zero throughput with no active call is the **expected idle state** — an idle network is a healthy network. The agent lacked any mechanism to distinguish "idle" from "broken" and defaulted to "broken."

### Why this is a structural problem

Four data plane rate metrics can all be near-zero legitimately:

| Metric | Zero when |
|---|---|
| `upf_kbps` | No voice call active (or call ended) |
| `upf_in_pps` | No uplink traffic (no active data session) |
| `upf_out_pps` | No downlink traffic |
| `rtpengine_pps` | No RTP media being relayed (no call) |

At the metric level, "idle voice network with 4 PDU sessions sitting quiet" and "broken UPF that dropped all traffic during an active call" look identical — both show zero throughput. The only way to tell them apart is to look at **call activity indicators** (`dialog_ng:active`, `rtpengine_sessions`) and cross-reference.

The agent, left to its own reasoning, did not perform this cross-reference. Neither did the ontology — before this ADR, there was no rule that told the agent to perform the check.

### Why this kept recurring

This is not the first time the agent made this error. The critical observation notes it was a repeat offense from the post-mortem of an earlier P-CSCF latency run. Prompt-level warnings alone have not been sufficient — the agent keeps defaulting to "zero throughput = failure" under the cognitive load of producing a layer-rated assessment. A prompt rule is a request; a stack rule that the agent is required to read and honor is a constraint the ontology enforces on the agent's reasoning.

### Why the existing ontology knowledge did not help

The ontology already contained descriptive notes about idle state in `baselines.yaml`:

```yaml
upf_kbps:
  during_call: 16
  alarm_if: "= 0 with active sessions (data plane dead) or < 10 during call (degraded)"

rtpengine_pps:
  description: "0 when no call is active. ~100 pps typical for G.711 voice..."
  during_call: 100

dialog_ng:active:
  description: "0 at rest, 2 during active call (one per direction)."
```

Line 115 of `baselines.yaml` is even explicit: *"These metrics are only meaningful during active VoNR calls."*

But baseline entries are descriptive documentation — they are not evaluated as rules. `compare_to_baseline` looks at metric-vs-expected values per component; it does not reason across metrics (e.g., "the data plane gauge is zero AND no call is active"). The knowledge existed; the reasoning glue did not.

Verified this gap during investigation: called `check_stack_rules` with the exact observations from the failing episode. Only `baseline_delta_rule` fired (a generic advisory rule). Nothing in the ontology specifically addressed the idle state pattern. Adding a dedicated rule closes that gap.

## Design

### The stack rule (`stack_rules.yaml`)

```yaml
- id: idle_data_plane_is_normal
  rule: "Zero data plane throughput (upf_kbps = 0, upf_in_pps / upf_out_pps = 0, rtpengine_pps = 0) is NORMAL when no voice call is active. Active PDU sessions alone do NOT require traffic — they just provide a path for traffic when a call is placed. An idle network is a healthy network."
  condition: "upf_kbps <= 0.5 OR rtpengine_pps <= 0.5 OR upf_in_pps <= 0.5 OR upf_out_pps <= 0.5"
  implication: "Before rating the CORE or IMS layer as degraded based on zero data plane throughput, you MUST verify a voice call is actually in progress. Check for active call indicators: rtpengine_sessions{type='own'} > 0 OR total_sessions > 0 (RTPEngine), OR dialog_ng:active > 0 at P-CSCF/S-CSCF. If no active call indicator is present, zero data plane throughput is the expected idle state. DO NOT rate any layer YELLOW or RED based on idle data plane metrics. DO NOT list UPF or RTPEngine as suspect components just because they are idle."
  priority: 2
  invalidates:
    - "data_plane_failure_analysis_without_active_call_check"
    - "treating_idle_rates_as_degradation"
  examples:
    - "upf_kbps=0 with 4 PDU sessions but dialog_ng:active=0 → idle, not broken"
    - "rtpengine_pps=0 with owned_sessions=0 → no call, media relay has nothing to relay"
    - "upf_in_pps=0 and upf_out_pps=0 during no-call period → expected baseline"
```

### The evaluator (`network_ontology/query.py`)

The stack rule checker in `OntologyClient.check_stack_rules` uses hardcoded per-rule Python evaluation logic. The new rule's evaluator:

1. Looks at four rate keys in the observations dict: `upf_kbps`, `rtpengine_pps`, `upf_in_pps`, `upf_out_pps`.
2. Collects which of these are present and ≤ 0.5 (the "near-zero" threshold).
3. If at least one is near zero, checks four activity indicators: `dialog_ng:active`, `owned_sessions`, `total_sessions`, `rtpengine_active_sessions`.
4. Returns the triggered rule with three extra fields:
   - `near_zero_rates` — list of which rate metrics are near zero
   - `active_call_detected` — boolean cross-check result
   - `verdict` — plain-English guidance string the agent can read directly

**Design choice — only rate metrics, not cumulative counters.** The rule does NOT look at `fivegs_ep_n3_gtp_indatapktn3upf` or `fivegs_ep_n3_gtp_outdatapktn3upf`. Those are lifetime cumulative counters that will be non-zero on any warm stack regardless of current traffic, and they cannot detect idleness. Only per-second rate metrics (from `get_dp_quality_gauges` / Prometheus `rate()`) can reliably distinguish "happening now" from "happened earlier."

**Design choice — threshold at 0.5, not 0.** A strict "equals zero" check would miss near-zero residual activity like SIP keep-alives or stray packets. A 0.5 pps floor treats anything below one packet per two seconds as "effectively idle" while still catching legitimate zero-throughput failures.

### The prompt gate (`network_analyst.md`)

Two updates to the NetworkAnalystAgent's instructions:

**Step 2 enhancement.** The prompt now explicitly tells the agent which keys to include when building the observations dict for `check_stack_rules`. This is critical because the rule only fires if the four rate keys are present in the dict — if the agent forgets them, the rule silently never fires and provides no guidance. The prompt lists data plane gauges, active call indicators, core health indicators, and pre-existing noise markers as REQUIRED dict contents.

**Step 3 idle-state gate.** A new mandatory subsection in "Rate each layer with evidence" that forces the agent to read the rule's `verdict` and `active_call_detected` fields before rating Core or IMS on data plane grounds. Three branches:

- `active_call_detected: False` → layer rated GREEN; UPF/RTPEngine NOT flagged as suspects
- `active_call_detected: True` → proceed with degraded rating
- Rule did not fire (rates are non-zero) → normal rating logic

The gate also incorporates two bonus "forbidden inference" rules from the same critical observation document: no subtracting cumulative UPF counters to fabricate a "loss" number, and no rating layers based on pre-existing baseline noise.

## Verification

Verified against three distinct scenarios after re-seeding the ontology:

| Scenario | Rule fires? | Verdict |
|---|---|---|
| Idle (no call, zero rates) | ✅ yes, `active_call_detected: False` | *"No active call — zero data plane rates are EXPECTED idle state. DO NOT flag as degraded."* |
| Active call + zero data plane (real fault) | ✅ yes, `active_call_detected: True` | *"Active call detected — zero rates may be a real problem."* |
| Healthy call (rates >> 0) | ❌ no | Rule does not fire — no false alarms on healthy networks |

All three scenarios produce the correct guidance. The failing scenario from the critical observation would have received the "DO NOT flag as degraded" verdict and the agent's Step 3 gate would have prevented the bad rating.

## Files Changed

- `network_ontology/data/stack_rules.yaml` — new `idle_data_plane_is_normal` rule added
- `network_ontology/query.py` — evaluator branch added to `OntologyClient.check_stack_rules` for the new rule
- `agentic_ops_v5/prompts/network_analyst.md`:
  - Step 2: expanded instructions for building the observations dict to include data plane gauge keys and active call indicators
  - Step 3: new **Idle-state gate** subsection that mandates honoring the rule's verdict before rating Core/IMS degraded
  - Step 3: new **Forbidden inferences** subsection addressing the counter-subtraction and pre-existing-noise mistakes (from the same critical observation)

## Alternatives Considered

1. **Prompt-only rule ("don't interpret zero as broken").** Rejected. The same warning was issued in an earlier post-mortem and the agent made the same mistake again. Prompts are soft constraints the agent can rationalize around under cognitive load. A structural ontology rule that the agent must read and honor is stronger — and the verdict string gives the agent a ready-made answer it cannot easily ignore.

2. **Change the data plane gauge tool to return a signal about idleness.** (e.g., `get_dp_quality_gauges` returns `"idle — no call active"` instead of numeric zeros.) Rejected. That would hide information the Investigator phase may need later, and couples call-detection logic to the wrong tool. The cleaner separation is: tool returns facts, ontology rule applies reasoning, agent consumes the rule verdict.

3. **Skip data plane metric collection entirely when no call is active.** Rejected. The agent needs to see zero throughput to confirm idle state — skipping the query would remove a useful signal. Also, knowing that rates are zero AND that no call is active is more informative than knowing nothing.

4. **Raise the near-zero threshold from 0.5 to a higher value (e.g., 5 pps).** Rejected for now. Current threshold correctly handles the observed failure modes. If future observations show the threshold is too tight, we can tune it — the rule is centralized in one place.

5. **Make the rule fire only when ALL four rate metrics are near-zero** (instead of ANY). Rejected. In real failure modes, only one direction or one component may be affected (e.g., `upf_out_pps = 0` with `upf_in_pps` still flowing). An ANY check surfaces the rule whenever idle/broken disambiguation is needed; the agent can still look at the full `near_zero_rates` list to understand which rates are affected.

## Follow-ups

This ADR addresses Issue 1 from the four-issue critical observation. Three remaining issues from the same document still need to be handled:

- **Issue 2: Cumulative counter subtraction** — partially addressed here (added as a "Forbidden inferences" prompt rule in Step 3), but no ontology enforcement. A dedicated stack rule that detects and warns against this pattern would be stronger.
- **Issue 3: Investigator made 0 tool calls; evidence fabricated in the final diagnosis** — most critical remaining issue. Needs Investigator prompt tightening, orchestrator-level enforcement of minimum tool calls, and recorder-level evidence citation validation.
- **Issue 4: Scenario design produces no signaling activity during the propagation window** — scenario-level fix, orthogonal to the agent changes.

Each deserves its own ADR/PR.
