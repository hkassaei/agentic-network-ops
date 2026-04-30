# Challenge: Stochastic LLM Behavior — Part II: The Prompt-Engineering Ceiling

**Date:** 2026-04-30
**Agent version:** v6 (ADK 1.31.1 + gemini-2.5-pro on NA / IG / Investigator / Synthesis, gemini-2.5-flash on OntologyConsultation)
**Status:** Open observation — companion to [`challenge_with_stochastic_LLM_behavior.md`](challenge_with_stochastic_LLM_behavior.md). Establishes the case for tomorrow's structural work captured in [`../ADR/structural_guardrails_for_llm_pipeline.md`](../ADR/structural_guardrails_for_llm_pipeline.md).
**Series:** Part 2 of N — Part I documented run-to-run variance on the same scenario; Part II documents the systematic interpretive errors that no amount of prompt engineering reliably eliminates.

---

## Topline

Part I observed that two runs of the same scenario can score 90% and 26% with no infrastructure change — the agent's reasoning chain happens to roll differently each time. Part II observes a sharper version of the same problem: **even when the prompt explicitly forbids a failure mode, the agent re-commits the failure mode probabilistically, because next-token prediction has no internal world-model to enforce the rule against.**

This session worked through three iterations of the same scenario (`call_quality_degradation` — 30% packet loss injected on RTPEngine via `tc`):

| Run | Score | What happened |
|---|---|---|
| `run_20260429_233451` | crashed | All 3 sub-Investigators crashed on missing `{anomaly_screener_snapshot_ts}` template var. Fixed by orchestrator state plumbing. |
| `run_20260429_235421` | **21%** | Investigators ran. h2 (RTPEngine) disproven by `measure_rtt(upf → rtpengine_ip)` showing 33% loss — agent interpreted as "path loss = upstream issue", missing that 30% ingress drop at RTPEngine produces identical ping output to link loss. |
| `run_20260430_010013` | **36%** | After IG prompt update mandating triangulation + `conflates_with` field on probes. IG correctly added a partner probe (`measure_rtt(pcscf → rtpengine_ip)`). Both probes showed 33% loss — mechanically localizing to RTPEngine. **Investigator still disproved h2** — this time on the grounds that the hypothesis statement said "internal fault" while the evidence pointed to "network ingress". Same component, different layer; agent treated layer mismatch as falsification. |

Three rounds of prompt updates moved the score from 21% to 36%. The right answer is RTPEngine. The agent has now seen the right evidence twice in a row and rationalized away the right answer twice in a row, in two structurally different ways.

---

## What's new in Part II

Part I's argument: the same scenario produces different scores because the agent's reasoning chain happens to roll differently each time. The fix proposed: better orchestration around hypothesis ranking + Synthesis confidence calibration.

Part II's sharper argument: **even when the agent has the right evidence in front of it AND the prompt has been updated to forbid the specific misinterpretation, the agent recommits the misinterpretation in adjacent ways, because the LLM is not running a model of the physical world — it is generating sentences whose distribution looks like network-debugging sentences.**

Three layers of evidence:

### Layer 1 — The agent reaches for the wrong tool even when the KB has the right one

In `run_20260430_010013`, the IG's plan for h2 (RTPEngine) used `get_dp_quality_gauges` as its primary RTPEngine probe. That tool returns RTCP-reported `loss_ratio` — a *downstream* signal that RTPEngine *receives from* receivers. It is not RTPEngine's own internal error counter.

The KB has the right metric documented at `network_ontology/data/metrics.yaml:1431-1491`:

> `ims.rtpengine.errors_per_second` — "measures rtpengine's internal relay errors. **It is orthogonal to network-layer packet loss: iptables/tc dropping packets upstream produces high loss_ratio with errors_per_second staying at 0.**"

That's exactly the disambiguator h2 needed. `errors_per_second > 0` = RTPEngine's user-space relay logic is failing (true "internal bug"). `errors_per_second = 0` while `loss_ratio > 0` = drops at rtpengine's NIC/tc/kernel level — *which is the actual injected fault.*

The IG didn't reach for it because:

1. **Tool gravity.** `get_dp_quality_gauges` is in the IG's tool table as the canonical "data plane probe". The IG defaults to it for any data-plane question rather than asking "is there an X-internal counter via `get_diagnostic_metrics(nfs=['X'])`?"
2. **No KB query for disambiguators.** The IG made 2 tool calls in that run; neither was `find_chains_by_observable_metric(rtpengine_loss_ratio)`, which would have surfaced the `disambiguators:` block pointing at `errors_per_second`.
3. **Conflation of "loss observed at X" with "loss caused by X".** The IG treated `loss_ratio` (downstream signal) and an internal error counter as interchangeable.

The KB has the answer; the LLM didn't query for it. Asking the LLM to query the KB more reliably is another prompt rule. Adding the rule reduces but does not eliminate the failure mode.

### Layer 2 — The agent interprets composite measurements as if they were not composite

In `run_20260429_235421`, h2's plan included a single directional probe `measure_rtt(upf → rtpengine_ip)`. The result was 33% loss. The Investigator wrote:

> "The test showed 33.3% packet loss on the network path from the UPF to RTPEngine. This contradicts the expectation of a clean path, which would be necessary to isolate the fault to RTPEngine alone. This suggests a network issue or a problem upstream of RTPEngine."

The injected fault was 30% ingress drop on RTPEngine via `tc`. Ping echo-requests arrive at RTPEngine's NIC and get dropped by the tc qdisc on ingress, producing exactly the observed 33% loss. The drop is *at RTPEngine*. But the agent interpreted "loss between A and B" as "loss on the path", because in its training corpus ping is described as a "network path test" and the dominant linguistic association is RTT-loss → path-loss.

The fix shipped between runs `_235421` and `_010013`: rewrote the IG prompt's rule #6 from "directional probes" to "compositional probes", added a `conflates_with` field on the probe schema, replaced the prompt's only `measure_rtt` example with two placeholder shapes (binary single-element vs. multi-element-path), updated the tool docstring to describe RTT readings as a composition over source-stack + path + target-stack, and added an Investigator-side rule on consuming `conflates_with`.

In the next run, **the IG correctly added the triangulation partner probe** (`measure_rtt(pcscf → rtpengine_ip)`). The mechanical localization was now unambiguous: both paths from disjoint sources to the same target showed 33% loss → loss is at the target, not at any source's egress and not on either path. The fix worked on the IG side.

But:

### Layer 3 — When mechanical localization succeeds, the agent finds a different reason to disprove the right answer

Reading the Investigator's reasoning on h2 in `run_20260430_010013`:

> "A 33% packet loss was also observed on the path from P-CSCF to RTPEngine. This reinforces that the issue is not isolated to the UPF-RTPEngine path and points towards either a broader network problem **or an issue with RTPEngine's network ingress, but in either case, it's not an internal processing bug**." (emphasis added)

The agent correctly localized to *RTPEngine's network ingress* — and disproved the hypothesis on the grounds that the hypothesis statement specified "internal fault, due to a bug or resource issue", and "network ingress" was categorized as not-internal-bug.

Same component (RTPEngine). Same physical fault (drops at the container's network ingress). The Investigator correctly identified WHERE the drops happen and disproved the hypothesis because it disagreed with the *adjective* attached to the hypothesis statement. `tc` runs at the kernel level on the same container; user-space code is at a different layer of the same container. Both are "internal to RTPEngine" in any operationally-meaningful sense.

This led to a second prompt update (NA principle #10 + Investigator inclusive-interpretation rule) telling the NA not to use mechanism-scoping language ("internal", "due to overload", "due to bug") in hypothesis statements, and telling the Investigator to interpret "X is the source" inclusively across every layer of X. We will see whether the next run holds.

But the structural problem is now clear: **each fix is a workaround for a specific failure mode at a specific layer of the chain. The next failure mode is one rule deeper.**

---

## Why prompt engineering scales sub-linearly

Across this session and the previous one, the v6 prompts have accumulated:

- IG rule #6 — compositional probes need a partner (was: directional probes need triangulation)
- IG rule #7 — activity-vs-drops discriminator
- IG rule #8 — negative-result falsification weight
- IG rule #9 — flow-anchored probes
- IG rule #10 — branch-anchored probes
- NA principle #1 — upstream silent ≠ downstream noisy
- NA principle #2 — cross-layer signatures
- NA principle #3 — silent-failure semantics
- NA principle #4 — low activity ≠ local fault
- NA principle #5 — source-side vs destination-side latency
- NA principle #6 — meaning first, numbers second
- NA principle #7 — never compare two cumulative counters as a rate
- NA principle #8 — observing NF can be the fault source
- NA principle #9 — anchor hypotheses in causal chain branches
- NA principle #10 — statements name WHAT/WHERE not HOW
- Investigator: localization rule, negative-result interpretation, evidence weighting, silence-shaped upstream-activity check, hypothesis-statements-name-location

Each rule fixes the failure mode it was written for, drifts a little on adjacent ones, and adds linear cost forever. Each token in the prompt competes with every other token for the model's attention budget. The agent's compliance with any one rule is probabilistic — and *cross-rule* compliance (where two rules constrain the same decision) compounds the probabilities downward.

In `run_20260430_010013`, IG rule #6 (compositional probes need a partner) was followed correctly. NA principle #10 (no mechanism scope) had not yet been added at that run, but principle #8 (observing NF can be the fault source) was already there — and the NA still wrote h2 as "RTPEngine has an internal fault dropping packets internally due to a bug or resource issue", which is exactly the mechanism-scoping principle #10 was about to forbid. The NA produced a violation of a forthcoming rule because the existing rules don't cover this surface area, and the LLM doesn't generalize.

Three rounds of fixes moved the score from 21% to 36%. The trajectory is positive, but flatter each round. The next round is where the asymptote will start to dominate.

---

## The structural insight

LLMs do not model the world. They produce text whose conditional distribution is shaped by a training corpus. When asked to "reason about where packet loss originates," the LLM is not simulating NICs and tc qdiscs — it is generating sentences that look like network-debugging sentences. Most of the time the linguistic pattern matches the physics; sometimes (this scenario, repeatedly) it doesn't, and there is no internal world-model to catch the discrepancy.

No amount of prompt prose installs a world-model retroactively. Each rule we add is a workaround for a specific failure mode the corpus didn't already cover.

**Where the system has gotten more reliable, in this codebase and in this session, is precisely where load has been moved OUT of the LLM and INTO deterministic structure:**

- Pydantic schemas (forecloses invented tool names, missing fields, zero-probe plans)
- Phase decomposition (small windows of context per LLM call instead of one super-prompt)
- The KB (the ontology answers questions the LLM would otherwise hallucinate)
- Schema sentinels (timestamp plumbing, `conflates_with`, minimum-tool-call guardrails)
- Programmatic post-checks (the IG retry guard, the EvidenceValidator's tool-call counting, container-state pre-check + auto-restart)

The pattern is: **LLM proposes; deterministic layer accepts, rejects, or repairs.** That is the only stable trajectory I know for this class of system.

---

## Forward-pointer to tomorrow's structural work

The four moves below break the prompt-engineering ceiling by replacing prose-rules with structure. Captured in the placeholder ADR [`structural_guardrails_for_llm_pipeline.md`](../ADR/structural_guardrails_for_llm_pipeline.md):

1. **Post-IG validator** — rejects any plan whose probes have non-empty `conflates_with` without a partner probe. Currently the rule is in prose; the IG sometimes complies. A validator makes compliance mandatory and resamples on failure.
2. **Typed probe selection** — instead of free-forming probes, give the IG `select_probes(hypothesis) → [Probe]` that enumerates KB-authored disambiguators (the `disambiguators:` field exists on every metric in `metrics.yaml`). The LLM picks from a candidate list it cannot expand. This is exactly how `errors_per_second` would have shown up automatically in h2's plan.
3. **Multi-shot Investigator consensus** — same plan, two seeds; disagreement → INCONCLUSIVE. Cuts variance, exposes brittle interpretations rather than ratifying them with high confidence.
4. **Hypothesis-statement linter** — regex-flag mechanism words ("internal", "overload", "crash", "due to bug") and reject before NA returns. Removes "the agent forgot rule #10" from the failure-mode catalogue entirely.

Each is more upfront work and lower marginal cost forever. Each replaces "hope the LLM behaves" with "structure forbids it from misbehaving."

---

## Related observations

- [`challenge_with_stochastic_LLM_behavior.md`](challenge_with_stochastic_LLM_behavior.md) — Part I: run-to-run variance on the same scenario. The variance documented in Part I and the systematic interpretive errors documented in Part II are two faces of the same underlying property: the LLM's outputs are samples from a distribution shaped by training, not deductions from a world-model.
- [`../ADR/dealing_with_temporality_3.md`](../ADR/dealing_with_temporality_3.md) — fixed one specific structural failure (temporal blindness across phases). Same pattern: load moved out of the LLM (now phase 0 stamps a canonical timestamp; LLM doesn't have to remember to query historically).
- [`../ADR/get_diagnostic_metrics_tool.md`](../ADR/get_diagnostic_metrics_tool.md) — replaced the ~150-metric `get_nf_metrics` dump with curated KB-tagged output. Same pattern: load moved out of the LLM (it no longer has to scan a wall of text and pick the right metric; the KB tagging does the picking).
- [`../ADR/structural_guardrails_for_llm_pipeline.md`](../ADR/structural_guardrails_for_llm_pipeline.md) — the placeholder ADR capturing tomorrow's four structural fixes.
