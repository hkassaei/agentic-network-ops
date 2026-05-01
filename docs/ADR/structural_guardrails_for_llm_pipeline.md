# ADR: Structural Guardrails for the LLM Pipeline

**Date:** 2026-04-30
**Last revised:** 2026-05-01 — implementation underway. PRs 1 and 2 shipped (refactor + Decision D). Build sequence reordered post-PR-2 based on real-run evidence; Decision A expanded to include an IG-statement linter sub-check.
**Status:** Build in progress. Captures six structural moves motivated by the observations in [`../critical-observations/challenge_with_stochastic_LLM_behavior.md`](../critical-observations/challenge_with_stochastic_LLM_behavior.md) (Part I, Synthesis-stage failure modes) and [`../critical-observations/challenge_with_stochastic_LLM_behavior_part_II.md`](../critical-observations/challenge_with_stochastic_LLM_behavior_part_II.md) (Part II, NA / IG / Investigator-stage failure modes).
**Related ADRs:**
- [`falsifier_investigator_and_rag.md`](falsifier_investigator_and_rag.md) — Investigator + plan architecture this ADR proposes hardening.
- [`get_diagnostic_metrics_tool.md`](get_diagnostic_metrics_tool.md) — KB-curated tool layer that ADR-2 below (typed probe selection) builds on.
- [`dealing_with_temporality_3.md`](dealing_with_temporality_3.md) — same structural pattern (move load out of the LLM into deterministic plumbing).
- [`anomaly_model_overflagging.md`](anomaly_model_overflagging.md) — earlier ceiling-breaking work on the screener.

---

## Status of this ADR

Originally a placeholder; now actively being built. The framing question this ADR commits to:

> *Where in the v6 pipeline can we replace a prose rule with a deterministic check, a structured choice, or a redundancy mechanism, such that the LLM cannot violate the rule even probabilistically?*

If a proposed fix can be expressed as "tell the LLM to do X better," it does NOT belong in this ADR. The pattern this ADR encodes is **LLM proposes; deterministic layer accepts, rejects, or repairs.**

### What's shipped

- **PR 1 (2026-04-30) — Refactor.** Created `agentic_ops_v6/guardrails/`, extracted the existing inlined safeguards from `orchestrator.py` (silent-bail retry, fan-out audit, minimum-tool-call check, evidence-citation validator), and added `runner.run_phase_with_guardrail` as the composition point for future deterministic guardrails. No behavior change; orchestrator dropped from 1213 → 1054 lines.
- **PR 2 (2026-04-30) — Decision D.** NA hypothesis-statement linter. Rejects mechanism-scoping language in `Hypothesis.statement` with a per-hypothesis bad/good shape hint; resamples NA once on REJECT; accepts-with-warning on second REJECT (synthetic PhaseTrace + `state["guardrail_warnings"]` for episode log surfacing).

### What's next (revised order)

The original ordering (D → F → A → E → C → B) was based on per-PR effort. Real-run evidence from `run_20260501_012613_data_plane_degradation` (post-PR-2) showed that:

1. The mechanism-scoping failure mode the ADR targets relocated from NA (where Decision D shut it down) to IG's `expected_if_hypothesis_holds` and `falsifying_observation` text. PR 2's linter passed all three NA statements, and the IG re-introduced the scope downstream — so closing the leak requires lifting Decision D's mechanism into Decision A.
2. Decision F applied alone over an all-DISPROVEN verdict tree forces `inconclusive` even when the diagnosis recovered correctly via `alternative_suspects`. F's value is conditional on Decision E producing clean NOT_DISPROVEN survivors first.

The revised sequence is:
1. **PR 4 — Decision A (extended)** with the IG-statement linter sub-check. Closes the leak PR 2 left open.
2. **PR 5 — Decision E.** Candidate-pool aggregator + bounded re-investigation. Creates the clean NOT_DISPROVEN survivors that F's cap operates on.
3. **PR 3 — Decision F.** Confidence cap. Moved later than its original slot because it needs E's output to be useful.
4. **PR 6 — Decision C.** Multi-shot Investigator consensus.
5. **PR 7 — Decision B.** Typed probe selection from KB. Heaviest, last.

The detailed rationale for the reorder lives in the `Implementation ordering` section near the end of this ADR.

---

## Context

The v6 pipeline has accumulated ~25 prompt rules across NA, IG, Investigator, and Synthesis. Each rule fixes a specific failure mode. Rule compliance is probabilistic, attention budgets are finite, and cross-rule compliance compounds the probabilities downward. The session preceding this ADR worked through three iterations of `call_quality_degradation` (RTPEngine 30% packet loss). Score moved 21% → 36% across two prompt-rule rounds. The next round is where the asymptote starts to dominate.

The observations that motivate this ADR — that the LLM does not model the world, that no prompt rule installs a world-model retroactively, and that the same scenario re-run produces a 64-point score swing on stochastic hypothesis-ranking and Synthesis behavior — are captured at length in [`../critical-observations/challenge_with_stochastic_LLM_behavior.md`](../critical-observations/challenge_with_stochastic_LLM_behavior.md) (Part I) and [`../critical-observations/challenge_with_stochastic_LLM_behavior_part_II.md`](../critical-observations/challenge_with_stochastic_LLM_behavior_part_II.md) (Part II). Read both first; this ADR assumes their conclusions.

The six moves below are ordered by pipeline stage (A/B = IG, C = Investigator, D = NA, E/F = Synthesis) and within each stage by how much load they take off the LLM. Build order is deliberately not specified — each is independently useful and they compose well.

---

## Decision A — Post-IG validator

A single `lint_ig_plan` guardrail with two sub-checks, both running on every `FalsificationPlanSet` before it leaves Phase 4. Sub-check A1 was the original Decision A scope; A2 was added 2026-05-01 after `run_20260501_012613_data_plane_degradation` showed the mechanism-scoping failure mode that PR 2 closed at the NA stage relocating to IG.

### Sub-check A1 — Partner-probe / triangulation

**Rule today (prose):** IG rule #6 says compositional probes (whose reading composes contributions from more than one element) MUST be paired with a partner probe whose path differs in the element the hypothesis names, and the probe MUST populate `conflates_with` listing the alternative explanations.

**Failure mode:** IG sometimes writes the partner probe; sometimes it doesn't. When it doesn't, the Investigator declares DISPROVEN on a single compositional reading, repeating the failure mode rule #6 was written to prevent.

**Proposed structure:** A deterministic post-IG validator. The validator checks:

1. For every probe with non-empty `conflates_with`, does the same plan contain at least one other probe whose tool-call args produce a path that differs in the hypothesis's primary suspect NF and shares at least one of the elements named in `conflates_with`? If not, reject.
2. For every probe whose tool is structurally compositional (`measure_rtt`, request-response timings, ratios across a boundary — defined in a small static map keyed on tool name) but has `conflates_with: []`, flag the plan: either the IG asserted false uniqueness or the IG forgot to populate the field. Reject either way.

### Sub-check A2 — IG-statement linter (added 2026-05-01)

**Rule today (prose):** IG prompt inherits NA principle #10 implicitly — write probe `expected_if_hypothesis_holds` and `falsifying_observation` text inclusively over every layer of the named NF.

**Failure mode:** IG re-introduces mechanism scope that NA's Decision-D-shipped statement no longer carries. In `run_20260501_012613_data_plane_degradation` (post-PR-2), NA's three statements were all clean of mechanism words (PR 2's linter PASSED them on first attempt with zero LLM cost). IG then wrote h1's plan with:

```
measure_rtt(nr_gnb → upf)
  expected_if_hypothesis_holds: Low RTT and no packet loss
  falsifying_observation:       High RTT or packet loss → points to a
                                transport network issue rather than a
                                UPF-internal fault.
```

For "UPF is the source" interpreted inclusively, this is **inverted** — UPF being the source should expect *high* loss on probes to UPF (because the loss IS at UPF). IG narrowed h1 to "UPF application processing" silently via the *"rather than a UPF-internal fault"* phrasing. The Investigator then dutifully ran the probes, found 33% loss on N3 and N4 paths, and concluded DISPROVEN because IG had pre-committed to that conclusion in the falsifying-observation text.

**Proposed structure:** Same blocklist-based regex linter as Decision D, applied to two more fields per probe. Sub-check A2 inspects every `FalsificationProbe.expected_if_hypothesis_holds` and `FalsificationProbe.falsifying_observation` for mechanism-scoping language. Reuses the `na_linter` blocklist plus a small IG-specific extension:

- All Decision D phrases (`internal`, `due to overload`, `not forwarding`, etc.).
- `<NF>-internal fault`, `<NF>-internal`, `<NF>-internal X` (parameterized over the known NF list) — the canonical "IG mid-plan re-scopes" phrase.
- `application-layer`, `application layer`, `process-level`, `user-space-only`.
- `kernel-only`, `transport-only` (the inverse: pre-committing to layer when the hypothesis didn't).

On rejection, the IG-statement reason carries the same shape-hint pattern as Decision D — quote the offending phrase, show the required shape (`expected_if_hypothesis_holds` text framed inclusively over every layer of the NF), give a per-probe bad/good example.

### Common to A1 and A2

**Resample policy:** Same as Decision D. On REJECT, resample IG once with the structured reason injected as `{guardrail_rejection_reason}` in the IG prompt. On second REJECT, accept-with-warning (synthetic PhaseTrace + `state["guardrail_warnings"]` entry). The accept-with-warning policy applies to both sub-checks — a slightly mis-framed plan is worse than a clean one but better than a hard pipeline failure.

**Open design questions:**
- The A1 static "compositional tools" map needs the right keys. `measure_rtt` is obvious; does any other tool currently produce a compositional reading? (Probably no, but worth a short audit.)
- A1 validator-level path inference. The validator needs to compare probe paths to detect "shares some elements, differs in named element" without re-running the topology graph in Python. Two cheap approaches: (a) require the IG to label probes with `path_elements: [<source>, <link>, <target>]` and check set membership; (b) infer paths from `args_hint` regex, accepting some false negatives. Option (a) is cleaner; option (b) is faster to ship.
- A2 false-positive risk on phrases like *"the kernel-layer drop interpretation would falsify the application-layer hypothesis"* — meta-commentary that names the layer for legitimate disambiguation purposes. Mitigation: the linter only fires when the layer-scoping phrase appears in the probe's *expected* or *falsifying* text, not in `args_hint` or notes. If false positives still surface, tighten the regex with negative-lookbehind on common meta-commentary patterns.
- A1 + A2 share one runner pass over the plan set. Both sub-checks emit findings into the same `GuardrailResult.notes` so the rejection reason is a single coherent message rather than two passes that compete for NA's resample attention.

**Expected impact:** A1 covers the original Decision A target (run_20260429_235421 single-direction-probe failure). A2 covers the run_20260501_012613 failure where NA was clean but IG re-scoped — this is the primary residual after PR 2 and the reason A jumped to position 1 in the revised order.

---

## Decision B — Typed probe selection

**Rule today (prose):** IG prompt encourages the IG to call `find_chains_by_observable_metric(metric)` to surface KB-authored disambiguators when designing probes.

**Failure mode:** IG usually doesn't make the KB query. In `run_20260430_010013` IG made 2 tool calls; neither was the KB lookup that would have surfaced `errors_per_second` as the right RTPEngine-internal disambiguator. Result: IG free-formed a probe (`get_dp_quality_gauges`) that doesn't actually probe RTPEngine internals.

**Proposed structure:** A typed function `select_probes(hypothesis: Hypothesis) → list[ProbeCandidate]` exposed as a tool to the IG (or, more strongly, called *for* the IG by the orchestrator and injected into the prompt as a structured candidate list). Implementation:

1. For the hypothesis's `primary_suspect_nf` and any metrics named in the hypothesis statement / supporting events, walk the KB:
   - `find_chains_by_observable_metric` for every metric mentioned.
   - `disambiguators` block on the metric's `MetricEntry`.
   - `discriminating_from` hints on adjacent causal-chain branches.
2. Convert each KB-authored disambiguator into a structured `ProbeCandidate` with the tool, args, expected-when-confirming, expected-when-falsifying, and `conflates_with` populated by the KB content (the KB already says "errors_per_second is orthogonal to network-layer packet loss" — that's `conflates_with: []` on errors_per_second, vs. `conflates_with: [<list>]` on loss_ratio).
3. The IG's job becomes: pick from this candidate list, optionally rank, and return. The IG cannot expand the list; it cannot invent probes the KB doesn't authorize.

The LLM is now constrained to a typed selection problem (which it is good at) instead of an open-ended generation problem (which it is unreliable at).

**Open design questions:**
- Do we require the IG to use *only* `select_probes` output, or can it supplement with free-form probes? Strict-only is more reliable but coupled tightly to KB completeness — gaps in the KB become unfixable in a run. Hybrid with a "if the KB has nothing for this metric, free-form is OK" fallback is more pragmatic but reintroduces the failure mode for any KB gap.
- KB coverage audit. The `disambiguators` field exists on most metrics but quality varies. A coverage report would tell us which metrics need work before this can be the *only* probe source.
- The `select_probes` function needs to compose probes across multiple metrics in the hypothesis. A naive "one probe per metric" output may miss the cross-metric disambiguators that are the strongest probes (e.g., "loss_ratio high AND errors_per_second zero → tc/iptables drop, not application bug" is a two-metric reading).
- Should `select_probes` return the candidates ranked, or unranked? Ranked saves the IG cognitive work but assumes the KB encodes ranking; unranked gives the IG agency but reintroduces variance.

**Expected impact:** Largest potential lift of the four. Removes the "IG reaches for the wrong tool" failure mode entirely for any hypothesis whose primary metric has KB-authored disambiguators. Lifts the floor on probe quality from "whatever the IG free-forms" to "whatever the KB authorizes." Couples KB quality directly to diagnosis quality, which is the right coupling — KB content is human-curated and reliable, LLM choice is not.

---

## Decision C — Multi-shot Investigator consensus

**Rule today (prose):** None — single-shot Investigator verdicts are the only mechanism today.

**Failure mode:** Single-shot LLM verdicts are samples from a distribution. Two runs of the same plan can produce DISPROVEN and NOT_DISPROVEN respectively, with high confidence in both. The pipeline today ratifies whichever one happened to fire. The Synthesis agent then writes high-confidence diagnoses on what is fundamentally a coin-flip outcome.

**Proposed structure:** Run each Investigator twice with different seeds (or different temperature, if seeds aren't honored). Compare verdicts:

- Both DISPROVEN → DISPROVEN, with the union of `alternative_suspects`.
- Both NOT_DISPROVEN → NOT_DISPROVEN, with the union of probe interpretations.
- Disagreement → INCONCLUSIVE, with reasoning that names the disagreement explicitly.

The cost is 2x LLM calls per Investigator. Per scenario with 3 hypotheses, this adds ~3 sub-Investigator runs to the budget. At current pricing (~$0.20-0.40 per run for gemini-2.5-pro at the prompt sizes we're seeing), this is +$0.60-1.20 per scenario. Tolerable for the runs we make.

**Open design questions:**
- Does ADK / Gemini API honor seed for reproducibility, or do we have to use temperature variation? Temperature variation is more predictable but conflates "the same prompt produces different output" with "the prompts are slightly different." Need a quick experiment.
- Tie-breaking on partial agreement. If both verdicts are NOT_DISPROVEN but their reasoning paths cite different probes, do we keep both reasonings and let Synthesis pick? Or pick one canonical?
- Three-shot vs two-shot. Two-shot only catches binary disagreement; three-shot lets us do majority voting. Three-shot is +50% cost for marginal improvement; probably not worth it at current variance levels.
- Whether to short-circuit: if the first verdict is INCONCLUSIVE, do we skip the second run? Probably yes (an INCONCLUSIVE first run already concedes the verdict; second run can't make it worse).

**Expected impact:** Catches the "Investigator confidently disproves the right answer for a brittle reason" failure mode (run_20260429_235421 h2 disproven on path-loss interpretation; run_20260430_010013 h2 disproven on layer mismatch). Both of those would likely have surfaced as INCONCLUSIVE under multi-shot rather than DISPROVEN, which is a strictly better outcome — Synthesis can then escalate or downgrade confidence appropriately. Variance reduction, not bias correction.

---

## Decision D — Hypothesis-statement linter

**Rule today (prose):** NA principle #10 forbids mechanism-scoping language ("internal", "due to overload", "crash", "due to bug") in hypothesis statements. Investigator companion rule says interpret "X is the source" inclusively across every layer of X.

**Failure mode:** NA sometimes complies, sometimes doesn't. The statement is a free-text field; the LLM can write anything. When it writes "RTPEngine has an internal fault dropping packets due to a bug or resource issue", downstream consumers (IG, Investigator) take that scoping seriously even when the Investigator-side prompt rule says interpret inclusively. The interpretive rule is a backstop, not a guarantee.

**Proposed structure:** A deterministic linter that runs on every NA `Hypothesis.statement` before NA returns. The linter:

1. Tokenizes the statement.
2. Flags occurrences of mechanism-scoping words / phrases. Initial blocklist (open to extension):
   - `internal`, `internally`, `internal fault`, `internal bug`
   - `due to a bug`, `due to a resource issue`, `due to resource exhaustion`
   - `due to overload`, `overwhelmed by`, `flooded with`
   - `due to a crash`, `crashed`, `not running`
   - `due to a configuration error`, `misconfigured`, `due to misconfiguration`
   - `due to <NF> being`, `because <NF> is`
3. On any flag, reject the NA report and resample with the flagged phrase quoted in the rejection reason: "Hypothesis <id> statement contained '<phrase>'. Rewrite to name the observable that's wrong and the component the fault originates at, without scoping the mechanism. See NA principle #10 for the rule and bad/good examples."

Rationale: a regex check over a known-finite vocabulary is deterministic. The LLM cannot "forget rule #10" if the linter rejects every output that violates it. The blocklist starts conservative and grows as we observe new mechanism words in the wild.

**Open design questions:**
- False positives. "The metric is internal to the NF" is a legitimate use of "internal" that the linter would flag. Mitigation: require context-aware regex (`\binternal fault\b`, `\binternally\b` near a verb phrase). Trade-off: more false negatives.
- Where does the linter live? Cleanest is in the orchestrator's NA-output parsing layer. Less clean but more flexible: as a Pydantic validator on `Hypothesis.statement`. Pydantic-level validation runs at the schema-decode step in Gemini's constrained decoder — which means the LLM gets immediate feedback during generation. Worth investigating whether ADK's structured-output supports this depth of constraint.
- Composability with the IG / Investigator inclusive-interpretation rules already shipped today. The linter is upstream of both; if the linter does its job, the downstream rules can be relaxed (or removed entirely as redundant). Worth a deferred decision.

**Expected impact:** Smallest of the four NA/IG/Investigator-stage moves. Removes one specific class of failure (NA writes a mechanism-scoped statement, Investigator disproves the right component on a layer mismatch). The downstream Investigator rule shipped today is a partial backstop; the linter would make the failure mode mechanically impossible.

---

## Decision E — Synthesis candidate-pool constraint

**Rule today (prose, partial):** Part I shipped a "Synthesis should consult `alternative_suspects` from disproven verdicts" prompt pattern. It's prose; compliance is probabilistic. The structured `alternative_suspects` field is already populated on the Investigator's verdict object, but Synthesis is free to ignore it.

**Failure mode:** When all hypotheses are DISPROVEN, or when only a weak NOT_DISPROVEN survives, Synthesis ratifies whatever it has — even when the disproven verdicts collectively name a real culprit that wasn't initially hypothesized. The 17:58 P-CSCF run is the canonical example: an Investigator verdict on the disproven `h1 (PCF)` explicitly wrote *"Alternative suspects: pcscf"* with citing evidence, and Synthesis still picked the only NOT_DISPROVEN survivor (S-CSCF) and scored 26%. The right answer was inside the run's structured data; the synthesis step dropped it on the floor.

This is one of the two Synthesis failure modes named in Part I:

> *All hypotheses disproven (none survived investigation). Today: Synthesis gives up and writes a low-confidence "investigation inconclusive" diagnosis. But the disproven verdicts may collectively point to a root cause that wasn't initially hypothesized — the alternative_suspects pattern.*

**Proposed structure:** A deterministic pre-Synthesis aggregator computes a `candidate_pool: list[NF]` from the verdict tree:

1. Every hypothesis with verdict `NOT_DISPROVEN` → its primary suspect NF.
2. Every NF named in `alternative_suspects` of ≥2 disproven verdicts (cross-corroboration threshold).
3. Every NF named in `alternative_suspects` of ≥1 disproven verdict where the verdict cites concrete evidence (single-strong-cite threshold — defined as the verdict's `reasoning` field referencing the alternative suspect by name with a metric or log citation).

The Synthesis structured-output schema is then changed so `final_diagnosis.suspect` is a typed enum populated from `candidate_pool`. The LLM cannot pick a suspect outside that pool. Three branches:

- **Pool non-empty, ≥1 NOT_DISPROVEN** → Synthesis picks normally from the pool.
- **Pool non-empty but all members are *promoted* (no NOT_DISPROVEN)** → orchestrator triggers one bounded re-investigation cycle on the top-ranked promoted suspect. One IG plan, one Investigator pass, hard-cap budget. The re-investigation's verdict rejoins the pool, and Synthesis runs once more on the augmented pool.
- **Pool empty** → Synthesis is forced to emit `INCONCLUSIVE`. The schema branch removes the high-confidence option entirely.

This makes "Synthesis ignored `alternative_suspects`" mechanically impossible — the field is no longer optional reading, it's a typed input to the candidate enum.

**Open design questions:**
- Cross-corroboration threshold. Is "≥2 disproven verdicts naming the same NF" the right bar, or is "≥1 strong-cite" sufficient on its own? Strong-cite is more permissive (one Investigator that did its job carefully can promote); cross-corroboration is more conservative (requires multiple independent Investigators to converge). Probably both, with strong-cite as the OR-branch.
- Re-investigation budget. One round seems right (matches Part I's bounded-loop guidance). What about scoring — does the re-investigated suspect's verdict get equal weight to the originally-investigated ones? Probably yes; they used the same Investigator with the same probe machinery.
- Tie-breaking on the promoted-suspect rank when multiple NFs cross the threshold. Most-cited-by-verdicts? First-mentioned? Depth-in-causal-chain? Probably most-cited; falls back to NA's original `fit` score on the parent hypothesis.
- Schema mechanics. The Synthesis structured output today is a free-form `final_diagnosis` object. Switching to an enum-typed `suspect` field requires regenerating the schema per-run (since the enum values are dynamic). ADK / Gemini constrained decoding supports dynamic enums via Pydantic union types, but this needs a quick proof. If it doesn't work cleanly, the fallback is post-emit validation: reject any Synthesis output whose `suspect` isn't in `candidate_pool` and resample once.

**Expected impact:** Directly addresses Part I's first Synthesis failure mode. The 17:58 P-CSCF run would have promoted `pcscf` into the candidate pool from the disproven `h1` verdict's `alternative_suspects`, and either Synthesis would have picked it directly (since the pool would contain `pcscf` plus a weakly-NOT_DISPROVEN `scscf`) or the bounded re-investigation would have run on `pcscf` and produced a strong NOT_DISPROVEN verdict. Either way, the floor on "wrong NF in the hypothesis list" runs is meaningfully higher.

---

## Decision F — Evidence-strength confidence cap

**Rule today (prose):** Synthesis prompt asks for calibrated confidence. Compliance is variable. There is no deterministic check that a high-confidence verdict is actually justified by the underlying probe evidence.

**Failure mode:** A single weakly-NOT_DISPROVEN verdict gets ratified at high confidence by Synthesis. The 17:58 P-CSCF run is partly an instance of this: only one hypothesis survived, but it survived weakly (one consistent probe, one contradicting, one supportive only of a "partial failure" framing), and Synthesis still rated it high-confidence. This is Part I's second Synthesis failure mode:

> *All hypotheses are weakly NOT_DISPROVEN (e.g. all three hypotheses survived but none were strongly confirmed because the probes were inconclusive). Today: Synthesis picks the highest-fit one and ratifies it with high confidence — too high for the actual evidence.*

The high-confidence-on-thin-evidence pattern is exactly the failure mode rule D's linter pattern was designed for, but applied to NA mechanism-scoping. F applies the same pattern to Synthesis confidence.

**Proposed structure:** A deterministic per-verdict evidence-strength score computed from structured probe-result fields the Investigator already emits. Inputs:

- `probes_consistent / probes_total` — fraction of probes whose readings support the hypothesis.
- `probes_contradicting > 0` — any probe whose reading contradicts the hypothesis is a strong cap signal.
- `triangulated == False` for compositional probes — composes with Decision A. A compositional probe without its partner is not adequate evidence regardless of its reading.
- `inconclusive_probes / probes_total` — too many INCONCLUSIVE probes means the hypothesis didn't actually get tested.

These collapse into an enum: `STRONG`, `MODERATE`, `WEAK`, `NONE` per verdict. Synthesis's `confidence` field is then capped post-emit by a deterministic table:

| Strongest verdict's evidence-strength | Max permitted Synthesis confidence |
|---|---|
| STRONG | high |
| MODERATE | medium |
| WEAK | low |
| NONE | inconclusive (forced) |

The cap runs as a post-Synthesis validator. If the LLM emits `confidence: high` but the strongest verdict's evidence-strength is WEAK, the validator deterministically rewrites the output to `confidence: low` and appends a structured note: `confidence_capped_by_evidence_strength: true`. No resample needed; the LLM's verdict choice stands, only its confidence rating gets corrected.

This is the same pattern as Decision D's linter, applied to a different field. The inputs are all already structured data on the verdict object — no LLM judgment is being second-guessed, only the emit-side rating that the LLM reliably miscalibrates.

**Open design questions:**
- Threshold tuning. The mapping from `(probes_consistent, probes_contradicting, triangulated, inconclusive)` → `STRONG/MODERATE/WEAK/NONE` is the load-bearing decision. Initial proposal: STRONG iff `probes_consistent ≥ 2 AND probes_contradicting == 0 AND triangulated == True`; WEAK iff `probes_consistent < 2 OR probes_contradicting > 0`; NONE iff `inconclusive_probes / probes_total > 0.5`. These thresholds want a small batch of historical runs to validate.
- Composition with multi-shot Investigator (Decision C). C produces verdicts with disagreement-aware reasoning. Does the evidence-strength score need to factor in C's agreement signal? Probably yes: a NOT_DISPROVEN that emerged only because two of three Investigator shots disagreed should not score STRONG even if the surviving shot's probes look clean.
- Rewrite vs reject. The proposal is to silently downgrade confidence and emit a structured note. Alternative: reject and resample the Synthesis with the cap reason injected ("Your previous diagnosis claimed high confidence, but the strongest verdict's evidence-strength is WEAK. Re-emit with confidence ≤ low."). Resample is cleaner for downstream consumers (the output looks normal); silent rewrite is cheaper and the structured note gives downstream tooling enough signal. Probably silent-rewrite-with-note for cost reasons.
- Whether the cap also forces Synthesis to surface uncertainty in the diagnosis text. A cap on the `confidence` enum doesn't automatically rewrite the `reasoning` field to match. If the reasoning is written like a confident assertion but the confidence enum says "low", consumers see a mixed signal. Probably acceptable for the placeholder phase; revisit if downstream tooling gets confused.

**Expected impact:** Directly addresses Part I's second Synthesis failure mode. The 17:58 run would have hit `WEAK` on its sole surviving verdict (one consistent probe + one contradicting + one only-partially-supportive) and the high-confidence claim would have been deterministically capped to `low`. That alone wouldn't change the diagnosed NF, but it would change the *score signal* the operator sees — a low-confidence S-CSCF diagnosis is correctly flagged as fragile and primes the operator to look harder, where a high-confidence S-CSCF diagnosis ratifies the wrong answer with false certainty. Composes strongly with Decision E: when E promotes an alternative suspect into the pool, F ensures the Synthesis output on that re-investigated suspect is also evidence-calibrated.

---

## Implementation ordering

The original ordering (D → F → A → E → C → B) was based on per-PR effort. After PRs 1 and 2 shipped on 2026-04-30, the data plane degradation re-run on 2026-05-01 (`run_20260501_012613_data_plane_degradation`) showed two things that forced a reorder:

1. **Decision D worked exactly as designed at the NA stage.** All three NA hypothesis statements passed the linter on first attempt with zero LLM cost. The mechanism-scoping failure mode the ADR targets did NOT recur in NA's output.
2. **The same failure mode showed up at the IG stage instead.** IG re-introduced layer-scoping in `expected_if_hypothesis_holds` and `falsifying_observation` text — h1's RTT probe expected "low RTT" for "UPF is the source", which inverts the test under inclusive interpretation. The Investigator faithfully executed IG's mis-framed plan and marked h1 DISPROVEN. The diagnosis text recovered the right answer via `alternative_suspects`, but the verdict tree read all-DISPROVEN with confidence `low` — a misleading mismatch. (Score: 90% from a generous scorer; pipeline confidence signal: low.)

Two implications:

- The mechanism-scoping leak isn't fully closed until the Decision D pattern is applied to IG's plan text too. **Sub-check A2 was added to Decision A as a result.**
- Decision F applied alone over the all-DISPROVEN tree from this run would force the cap to `inconclusive`, weakening a diagnosis that recovered correctly. **F's value is conditional on Decision E producing clean NOT_DISPROVEN survivors first** (via the candidate-pool aggregator's bounded re-investigation path).

### Revised build order

| PR | Decision | Effort | Why this position |
|---|---|---|---|
| ✅ PR 1 | (refactor) | shipped 2026-04-30 | Created `guardrails/`, extracted existing safeguards, added `runner.run_phase_with_guardrail` |
| ✅ PR 2 | D | shipped 2026-04-30 | NA hypothesis-statement linter |
| **PR 4** | **A (extended: A1 + A2)** | medium | Highest-priority residual after PR 2. A2 closes the IG-side mechanism-scoping leak that broke `run_20260501_012613`; A1 covers the original triangulation-failure target. Same module, same blocklist as Decision D — small extension with disproportionate impact |
| **PR 5** | **E** | medium-high | Candidate-pool aggregator + bounded re-investigation. Creates the clean NOT_DISPROVEN survivors that Synthesis-stage decisions operate on. Closes the verdict-tree-vs-diagnosis mismatch directly |
| **PR 3** | **F** | low (compute) but conditional | Confidence cap. Deferred from its original second-position slot to here because its inputs (clean NOT_DISPROVEN survivors with structured probe evidence) only exist after E is in place. F over an all-DISPROVEN tree forces `inconclusive` on correct-via-recovery diagnoses — a Pareto-worse outcome |
| **PR 6** | C | medium | Multi-shot Investigator consensus. Variance-reduction; lower priority while the dominant residuals are systemic-bias rather than variance |
| **PR 7** | B | large | Typed probe selection from KB. Heaviest design; depends on KB coverage. Ships last after the cheaper structural fixes have set the floor and exposed which KB gaps are blocking |

### Sequencing principles surfaced from PR 2's evidence

1. **Close downstream leaks before tightening downstream caps.** A patch that prevents the wrong scope from entering the pipeline is strictly more useful than one that adjusts confidence on a diagnosis derived from already-corrupted plans.
2. **Caps need clean inputs.** F (confidence cap) over an all-DISPROVEN tree is a downgrade-only instrument and can punish correct recoveries. F + E together is what Part I's failure modes actually need.
3. **The mechanism-scoping pattern is the same shape at every stage.** Decision D's na_linter, Decision A's sub-check A2, and any future Investigator-side variant all share one regex blocklist and one shape-hint generator. Code reuse is high; cost of adding the next stage's variant is low.

### Why not do all of them at once

Each PR changes the pipeline's failure-mode distribution. Shipping them serially produces per-fix signal: after PR 4, what residual remains? After PR 5, does the verdict tree become coherent with the final diagnosis? Shipping them in parallel makes the next round of regression analysis substantially harder to attribute. The reorder above was only possible because PRs 1+2 shipped first and produced a single concrete failure example that named the next priority.

---

## Non-goals of this ADR

- **Replacing the LLM agents.** The agents are still doing useful work — generating hypothesis statements, walking causal chains, interpreting probe results, synthesizing diagnoses. The six moves above harden their outputs without removing them.
- **Eliminating prompt rules.** Some prompt rules will remain — particularly interpretive ones the Investigator uses on probe results, and the NA hypothesis-ranking heuristics. The ADR claims structural fixes scale better than prose for *constraint-shaped* failure modes (the IG must include a partner probe; the NA must not use scope words; Synthesis must not pick a suspect outside the candidate pool; Synthesis must not claim high confidence on weak evidence). It does NOT claim every prompt rule should be replaced.
- **Solving NA-stage hypothesis-ranking variance.** Part I documented run-to-run variance at two stages: NA hypothesis-ranking ("flagged NF is the cause" vs "flagged NF is the reporter") and Synthesis confidence calibration. Decisions E and F together address the Synthesis-stage failures (E creates clean NOT_DISPROVEN survivors; F caps confidence on them) — neither in isolation is sufficient. Decision C (multi-shot consensus) addresses Investigator-stage variance. NA-stage hypothesis-ranking variance — the original "P-CSCF was not in the hypothesis list at all" failure — remains unaddressed by this ADR; it likely needs its own structural move (e.g. a deterministic post-NA validator that requires every Phase-0-flagged NF to appear as a primary or secondary hypothesis, with explicit reasoning if NA opted to interpret the flag as a downstream symptom).

---

## Validation method — DEFERRED

When this becomes a build item, the validation pattern should mirror what worked for the temporality fixes:

1. Capture a baseline batch (current pipeline, ~10 runs across 3-4 scenarios, score distribution).
2. Ship one Decision (probably D first).
3. Capture a post-fix batch (~10 runs same scenarios).
4. Compare distributions; if the floor moved up without the ceiling moving down, ship the next.
5. Repeat for each Decision.

The point of this pattern is that prompt rules tend to introduce drift on adjacent failure modes, but structural constraints generally don't. Per-batch comparison should reveal whether each Decision is genuinely a Pareto improvement or if it traded one failure mode for another.

## Implementation Decision

Superseded — see the **Implementation ordering** section above for the current build sequence. The original sequence pinned in this section was D → F → A → E → C → B, ordered by per-PR effort. Real-run evidence after PRs 1 and 2 shipped (specifically `run_20260501_012613_data_plane_degradation`) forced the reorder to A (extended) → E → F → C → B. The full rationale lives in *Implementation ordering › Revised build order*.

---

## References

- Part I: [`../critical-observations/challenge_with_stochastic_LLM_behavior.md`](../critical-observations/challenge_with_stochastic_LLM_behavior.md)
- Part II: [`../critical-observations/challenge_with_stochastic_LLM_behavior_part_II.md`](../critical-observations/challenge_with_stochastic_LLM_behavior_part_II.md)
- The temporality work that established the "move load out of the LLM" pattern: [`dealing_with_temporality_3.md`](dealing_with_temporality_3.md)
- The diagnostic-tool work that did the same thing for tool output curation: [`get_diagnostic_metrics_tool.md`](get_diagnostic_metrics_tool.md)
