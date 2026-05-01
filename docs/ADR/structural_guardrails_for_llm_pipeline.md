# ADR: Structural Guardrails for the LLM Pipeline

**Date:** 2026-04-30
**Last revised:** 2026-05-01 — implementation underway. PRs 1, 2, 4, 5, 5.5a, 5.5b, 3, 9, 6, and 8 shipped (refactor + Decision D + Decision A extended + Decision E + E hardening + Decision F + Decision H + Decision C + Decision G simpler form). Build sequence reordered post-PR-2 based on real-run evidence; Decision A expanded to include an IG-statement linter sub-check; **Decision G added** (mechanism-claim grounding) after `run_20260501_022351_data_plane_degradation` exposed an NA fabrication failure mode; **Decision H added** (NA direct-vs-derived ranking) after `run_20260501_032822_call_quality_degradation` exposed an NA-stage ranking failure. PR 6 (multi-shot Investigator consensus) shipped with two follow-on bug fixes — runner empty-output retry on resample and EvidenceValidator trace aggregation. PR 8 shipped Decision G's blocklist-only form (PR 8.5 deferred for the KB-grounding constructive-feedback variant — see Implementation ordering for trigger conditions).
**Status:** Build in progress. Captures eight structural moves motivated by the observations in [`../critical-observations/challenge_with_stochastic_LLM_behavior.md`](../critical-observations/challenge_with_stochastic_LLM_behavior.md) (Part I, Synthesis-stage failure modes) and [`../critical-observations/challenge_with_stochastic_LLM_behavior_part_II.md`](../critical-observations/challenge_with_stochastic_LLM_behavior_part_II.md) (Part II, NA / IG / Investigator-stage failure modes).
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
- **PR 4 (2026-05-01) — Decision A (extended).** Post-IG validator with two sub-checks: A1 (partner-probe / triangulation coverage on compositional probes) and A2 (mechanism-scoping linter on `expected_if_hypothesis_holds` and `falsifying_observation` text). Validated on `run_20260501_022351_data_plane_degradation`: score moved from 90% (misleading low confidence on a correct-via-recovery diagnosis) to 100% (calibrated high confidence on a clean NOT_DISPROVEN). The same run also exposed a NEW failure mode that motivated Decision G — see below.
- **PR 5 (2026-05-01) — Decision E.** Synthesis candidate-pool aggregator + bounded re-investigation. New `guardrails/synthesis_pool.py` walks the verdict tree post-Phase-6 and computes a ranked `CandidatePool` from NOT_DISPROVEN survivors plus alt-suspects that crossed the corroboration threshold (≥2 mentions OR named in verdict reasoning). When the pool has zero survivors but ≥1 promoted suspect, a new Phase 6.5 runs one bounded IG → Investigator cycle on the top-ranked promoted NF, reusing every existing safeguard (Decision A's `lint_ig_plan`, empty-output retry, min-tool-call check). The pool is also rendered into `state["candidate_pool"]` and fed to Synthesis via prompt template; Synthesis's verdict aggregation rule was rewritten to treat candidate-pool membership as the structural answer source. PR 5 ships prompt-side enforcement only on pool membership; structural post-emit validation lands in PR 5.5b.
- **PR 5.5a (2026-05-01) — E hardening (EV ordering).** Moved EvidenceValidator from Phase 6 (before re-investigation) to Phase 6.6 (after re-investigation) so its citation check covers the re-investigation Investigator's tool-call trace. Pipeline diagram in `orchestrator.py` docstring updated to reflect the 9-phase ordering.
- **PR 5.5b (2026-05-01) — E hardening (strict pool validation).** Converted Synthesis from plain-markdown to structured `DiagnosisReport` output. Added typed `primary_suspect_nf: _KnownNF | None` and `verdict_kind: Literal["confirmed", "promoted", "inconclusive"]` fields. New `lint_synthesis_pool_membership` guardrail rejects any `primary_suspect_nf` that isn't a CandidatePool member (when pool is non-empty), with branch-specific reasoning: empty pool requires `verdict_kind="inconclusive"` + `primary_suspect_nf=None`; non-empty pool with `verdict_kind` in `{confirmed, promoted}` requires the NF to be in the pool. New `_render_diagnosis_report_to_markdown` converts the structured report back to the prose form the chaos `EpisodeRecorder` and `score_diagnosis` expect; `state["diagnosis_structured"]` carries the typed form alongside.
- **PR 3 (2026-05-01) — Decision F.** Confidence cap. New `guardrails/confidence_cap.py` computes per-verdict `EvidenceStrength` (STRONG / MODERATE / WEAK / NONE) from the supporting verdict's `probes_executed` outcomes (CONSISTENT / CONTRADICTS / AMBIGUOUS counts), or from the promoted suspect's `cite_count` + `strong_cited_in` length. Caps `root_cause_confidence` per the ADR's table (STRONG→high, MODERATE→medium, WEAK→low, NONE→low). REPAIR pattern (silent rewrite + structured note appended to `explanation`); the diagnosed NF stands, only the confidence claim gets corrected. Composed with PR 5.5b's pool-membership guardrail in `orchestrator.py` Phase 7 so both checks run on every Synthesis emit.
- **PR 9 (2026-05-01) — Decision H.** NA direct-vs-derived ranking guardrail. Added `flag_kind: Optional[Literal["direct", "derived", "cross_layer"]]` to `MetricEntry` (default None — heuristic fallback when not authored). New `guardrails/na_ranking.py` classifies anomaly flags via KB-authored `flag_kind` or a naming-pattern heuristic (`_during_`/`_consistency`/`_path_` → cross_layer; `derived.<nf>_*` and `normalized.<nf>.*` → direct; else derived). For every direct flag, the linter requires the named NF to be `primary_suspect_nf` of a hypothesis with `fit ≥ 0.8` (tightened from 0.7 in a follow-up after `run_20260501_042127` showed rtpengine slipping through at exactly 0.70 with invented demotion reasoning) OR named in `summary` with explicit demotion reasoning (substring match on NF name + any of {`demoted`, `downstream`, `observer`, `reporter`, `secondary`, `consequence`, `symptom`, …}). Composed with Decision D in `orchestrator.py` Phase 3 — D runs first, H runs on D's PASS path. Same accept-with-warning policy.
- **PR 6 (2026-05-01) — Decision C.** Multi-shot Investigator consensus. New `guardrails/investigator_consensus.py` exposes `reconcile_verdicts(shots) → ReconciliationResult` with kind in `{single_shot, agreement, disagreement, inconclusive_pass_through}`. Each Investigator runs twice on the same plan (sequentially within a hypothesis, parallel across hypotheses). Both DISPROVEN → DISPROVEN with union of `alternative_suspects`. Both NOT_DISPROVEN → NOT_DISPROVEN with merged reasoning. Disagreement → forced INCONCLUSIVE with both shot reasonings quoted. Short-circuit on shot-1 INCONCLUSIVE saves the second LLM call. Configurable via `MULTI_SHOT_INVESTIGATORS = True` (default). Cost: roughly 2x Phase 5 LLM tokens. Two follow-on bug fixes shipped in the same session: (1) `run_phase_with_guardrail`'s resample path now uses `run_phase_with_empty_output_retry` for symmetry with the initial call (uncovered by `run_20260501_135059` where IG resample silent-bailed and the runner bailed without retrying); (2) `EvidenceValidator` aggregates `tool_calls` across all matching agent-name traces (was using `setdefault` and keeping only the first — would have hidden shot 2's tool calls from EV's citation check). Validated on `run_20260501_153627_call_quality_degradation`: multi-shot reconciliation fired correctly on both hypotheses (both shots agreed NOT_DISPROVEN); the same run surfaced an unrelated open question about Decision H's closure invocation that's currently being diagnosed via INFO-level logging.
- **PR 8 (2026-05-01) — Decision G (simpler form).** Mechanism-claim grounding linter, shipped as the blocklist-only variant of the ADR's two-part design. New `guardrails/mechanism_grounding.py` adds `lint_mechanism_grounding(report) → GuardrailResult[NetworkAnalystReport]` with a regex blocklist of *narrative*-mechanism phrases distinct from Decision D's *layer-scoping* set. Pattern set is intentionally narrower than the ADR draft to limit false positives — phrase-level only (`traffic storm`, `is overloaded by`, `network partition`, `cascade failure`, `running out of`, `meltdown`, etc.); bare words like `partition`, `cascading`, `storm`, `exhausted`, `collapse` are excluded because they have legitimate technical uses in this domain (3GPP partition events, "cascade of REGISTERs", "metric collapse"). Composed into the existing `_na_combined_guardrail` closure as the third check (D → H → G); each runs only on PASS of the previous. Same accept-with-warning policy. Smoke-tested on the canonical `run_20260501_022351` traffic-storm fabrication — REJECTs with hits `traffic storm` and `is overloaded by`. **Deferred to PR 8.5:** the KB-grounding constructive-feedback variant — see Implementation ordering for trigger conditions and rationale.

### What's next (revised order)

The original ordering (D → F → A → E → C → B) was based on per-PR effort. Real-run evidence has reshuffled it twice:

1. After PR 2, `run_20260501_012613_data_plane_degradation` showed the mechanism-scoping failure mode relocating from NA (where D shut it down) to IG's probe text. → Decision A bumped to PR 4 with sub-check A2.
2. After PR 4, `run_20260501_022351_data_plane_degradation` showed a different failure mode — NA *fabricating* a mechanism narrative ("traffic storm overloading the UPF") that the blocklist-based linters cannot catch because the words aren't on any blocklist. The diagnosis still scored 100% on a generous scorer, but the mechanism in the diagnosis text is confabulated. → Decision G added.
3. Decision F applied alone over an all-DISPROVEN verdict tree forces `inconclusive` even when the diagnosis recovered correctly via `alternative_suspects`. F's value is conditional on Decision E producing clean NOT_DISPROVEN survivors first.

The remaining sequence (after PRs 5, 5.5a, 5.5b, 3, 9, 6, and 8 shipped) is:
1. **PR 8.5 — Decision G hardening (KB-grounding).** Conditional follow-up on PR 8: extend the narrative-blocklist linter with a KB-grounding check that, on a flagged hypothesis, walks `Hypothesis.supporting_events` + `find_chains_by_observable_metric(<metric>)` and surfaces the KB-authored mechanisms in the rejection reason — turning "your mechanism is fabricated" into "here's what mechanisms the KB authorizes for this metric, pick from these." Trigger condition for prioritizing this: NA's resamples after PR 8 produce poor rewrites (chronic accept-with-warning, or rewrites that just relocate the fabrication elsewhere). PR 8 ships without it because the blocklist alone provides the structural REJECT; the KB-grounding adds constructive feedback that may not be necessary.
2. **PR 7 — Decision B.** Typed probe selection from KB. Heaviest, last.

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
- Schema mechanics. The Synthesis output today is plain markdown, not a typed Pydantic model — `create_synthesis_agent()` has no `output_schema`. Switching to a structured `DiagnosisReport` with an enum-typed `primary_suspect_nf` field is the cleanest way to enforce pool membership mechanically. Either (a) regenerate the Pydantic schema per-run with the candidate pool as the dynamic enum values (ADK / Gemini constrained decoding supports this via Pydantic union types but needs a quick proof), or (b) emit the field as a free `_KnownNF` literal and post-emit-validate against `candidate_pool` with a one-shot resample. **Status: scheduled for PR 5.5b — see Implementation ordering › Decision E hardening.** PR 5 ships with prompt-side enforcement only ("You MUST diagnose from the candidate pool"); the structural enforcement is the follow-up.

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

## Decision G — Mechanism-claim grounding (added 2026-05-01)

**Rule today (prose):** NA principle #10 says don't scope the mechanism in `Hypothesis.statement`. Decisions D and A2 enforce this on a known set of *blocklist* phrases (`internal`, `due to overload`, `not forwarding`, etc.). Neither addresses NA *fabricating* a mechanism narrative whose words aren't on any blocklist.

**Failure mode — the fabrication problem.** NA reads an anomaly metric, leaps to a plausible-sounding mechanism story, and writes it into the hypothesis statement as fact. Downstream agents (IG, Investigator, Synthesis) then propagate the fabricated mechanism without ever testing it. Probes get framed as "is the named NF affected?" — which is true regardless of mechanism — and the unverified mechanism rides through to the final diagnosis.

The canonical example is `run_20260501_022351_data_plane_degradation` (post-PR-4):

- **Actual fault:** tc-netem injecting 30% loss at the kernel layer of the UPF veth. No traffic storm, no overload. The kernel is just dropping 30% of packets, indiscriminately.
- **Phase 0 flagged:** `normalized.upf.gtp_indatapktn3upf_per_ue` at **11.40 pps** vs learned baseline 1.45 pps (8x). The screener's own `Healthy invariant` comment notes the metric *"Rises during active VoNR calls (~100 pps for G.711 voice)"* — so 11.4 pps during active calls is actually **low**, not a storm.
- **NA's leap:** *"The UPF is overloaded by a massive GTP-U traffic storm on the N3 interface, causing extreme packet loss."* "Traffic storm" appears nowhere in the metric semantics, the KB's causal chains, or the supporting events — it's an LLM-prior narrative invented to explain the 8x-of-the-wrong-baseline reading.
- **What the Investigator probed:** RTT from N3 + N4 paths, both showed 33% loss → "UPF is the source." Five CONSISTENT probes for h1, none of which actually tested the storm claim. The probes confirmed *that loss happens at UPF* (true), not *that a storm caused it* (false).
- **Final diagnosis:** *"A massive GTP-U traffic storm overloaded the User Plane Function (UPF), causing extreme packet loss"* — the storm framing rode all the way through. Score: 100% (the scorer was generous on the mechanism interpretation; UPF was correctly identified).

The structural pattern:
1. Screener flags an anomaly metric.
2. NA invents a plausible mechanism story.
3. IG writes probes that test "is the NF affected?", not "does the mechanism story hold?".
4. Investigator reads the probes as CONSISTENT (because the NF *is* affected, regardless of mechanism).
5. Synthesis ratifies the invented mechanism because nothing falsified it.
6. The generous scorer rewards correct NF identification, masking the confabulation.

This is **right for the wrong reasons**. The diagnosis names the right NF but invents a fake "why."

**Proposed structure:** A two-part guardrail running post-NA, after Decision D's blocklist check passes:

1. **Mechanism-narrative detector** — a small lexicon of *narrative* mechanism words distinct from Decision D's *layer-scoping* words. Initial set:
   - `traffic storm`, `flood`, `flooded` (volume narratives)
   - `is overloaded by`, `overloaded`, `overload condition` (load narratives — note: `due to overload` is already on D's list, but the bare-word and `is overloaded by` variants are not)
   - `congestion`, `congested`, `congestive failure` (congestion narratives)
   - `partition`, `partitioned`, `network partition` (partitioning narratives)
   - `cascading`, `cascaded`, `cascade failure` (cascade narratives)
   - `exhaustion`, `exhausted`, `running out of` (resource narratives)
   - `meltdown`, `breakdown`, `collapse`, `storm`, `surge`, `spike-induced` (failure-mode narratives)

   When any of these phrases appears in `Hypothesis.statement`, the second part fires.

2. **KB-grounding check** — for any hypothesis flagged in part 1, verify that the claimed mechanism is supported by KB content:
   - At least one event in `Hypothesis.supporting_events` whose KB metadata (`MetricEntry.deviation_meaning` or the fired-event's interpretive text) names that mechanism, OR
   - At least one causal-chain branch reachable via `find_chains_by_observable_metric(<metric>)` whose `mechanism` field names that mechanism.

   If neither holds, the hypothesis fails grounding. REJECT the NA report and resample with the rejection reason injected:

   > Hypothesis `h1` claims mechanism `traffic storm` for the deviation in `gtp_indatapktn3upf_per_ue`. The KB does not list this mechanism for this metric. Authored mechanisms for this metric (per `find_chains_by_observable_metric`):
   >   - `n3_data_plane_degradation` (mechanism: "packet loss on the gNB→UPF transport path")
   >   - `upf_user_plane_failure` (mechanism: "UPF cannot egress to the data network")
   > Either pick one of the KB-authored mechanisms (and reflect it in `supporting_events`) or rewrite the statement without naming a mechanism (per principle #10 — "<NF> is the source of <observable>" without scoping the HOW).

The accept-with-warning policy from PR 2 / PR 4 applies on second REJECT.

**Open design questions:**

- *Blocklist vs grounding-check.* The two-part design above uses the narrative-word list only as a *trigger* for the grounding check. A simpler version drops the grounding check and just blocklists the narrative words like Decision D does. The simpler version is cheaper but loses the constructive feedback ("here's what the KB says is plausible") — IG / NA would resample with no guidance about which mechanism *would* be acceptable. The two-part design pays one extra KB lookup per flagged hypothesis but produces the same shape-hint quality as Decisions D and A2.
- *KB coverage.* Like Decision B, this Decision is only as strong as the KB's mechanism authorship. A metric whose KB entry doesn't name any mechanism would force NA to either drop the mechanism word or resample indefinitely. Mitigation: the accept-with-warning policy is still the backstop; if the KB has nothing to say, the resample fails too and we fall back to today's behavior with a structured warning.
- *Relationship to Decision B.* Decision B authors candidate probes from KB content. Decision G authors mechanism-claim *guards* from KB content. The two share the same dependency (KB mechanism authorship being curated and current) but operate at different stages. G is cheaper to ship — regex + targeted KB lookup. B is heavier — full probe-candidate generation. Build G first, use it to surface KB gaps that would block B, fix those gaps, then ship B with confidence the KB is ready.
- *False positive risk.* Some narrative words have legitimate uses: "the diameter cascade" (a 3GPP procedure name), "the cascade of REGISTERs after failover" (legitimate description of a known procedure), "this is a cascading IMS failure scenario" (referring to the chaos scenario name itself). Mitigation: as with Decision A's word-boundary regexes, narrow the patterns and add negative-lookbehind on common legitimate collocations. Track false positives in `state["guardrail_warnings"]` and tighten over time.
- *Compose with Decision E?* When NA's mechanism claim fails grounding and accept-with-warning fires, the imperfect statement still flows downstream. Decision E's candidate-pool aggregator might still recover the right NF via `alternative_suspects` — but the diagnosis text will still carry the fabricated mechanism. To clean that up, Synthesis would need to read `state["guardrail_warnings"]` and elide the mechanism narrative from its rendered diagnosis. Out of scope for G's first ship; track as follow-up.

**Expected impact:** Directly addresses the fabrication failure mode named above. The `run_20260501_022351_data_plane_degradation` h1 statement *"UPF is overloaded by a massive GTP-U traffic storm"* would be flagged on `traffic storm` and `is overloaded by`. The grounding check would query the KB for `gtp_indatapktn3upf_per_ue`'s authored mechanisms, find that "traffic storm" is not among them, and resample NA with a constructive shape hint listing the KB-authored alternatives. The resample would land on a clean statement like *"UPF is the source of the elevated GTP-U packet loss observed in `core.upf.activity_during_calls_collapsed`"* — naming observable + component without inventing a mechanism. Downstream agents inherit the cleaner framing; the diagnosis text loses its fabrication; the score becomes a *true* 100% rather than a generous-scorer 100%.

### Implementation status (2026-05-01)

**PR 8 shipped the simpler form** — part 1 (narrative-blocklist regex) only. The two-part design's part 2 (KB-grounding lookup that surfaces authorized mechanisms in the rejection reason) was deferred to PR 8.5 with explicit trigger conditions.

**What PR 8 ships:**
- `guardrails/mechanism_grounding.py` — `lint_mechanism_grounding(report)` running a regex blocklist of narrative-mechanism phrases.
- Pattern set is intentionally narrower than this section's "Initial set" above. Phrase-level patterns only (`traffic storm`, `is overloaded by`, `network partition`, `cascade failure`, `running out of`, `meltdown`, `breakdown of`, etc.). Bare words like `partition`, `cascading`, `storm`, `exhausted`, `collapse`, `flood` were excluded after the false-positive analysis above showed they have legitimate domain uses (3GPP partition events, "cascade of REGISTERs after failover", "metric collapse").
- Composed into the `_na_combined_guardrail` closure as the third post-NA check (D → H → G); each runs only on the previous's PASS. Same accept-with-warning policy.
- Validated via 33 unit tests covering: clean PASS, 19 narrative-phrase REJECT cases, 6 false-positive guards, multi-hypothesis flagging, dynamic bad/good example generation, and replay of the canonical motivating run.

**What was deferred to PR 8.5:**
- The KB-grounding part of the two-part design — the "constructive feedback" path that would enrich the rejection reason with KB-authored mechanism alternatives.
- Reasons for deferral: (a) the KB lookup requires async Neo4j queries (`find_chains_by_observable_metric`) that would add latency to the synchronous closure; (b) the blocklist alone provides the structural REJECT, which is the primary ADR goal; (c) constructive feedback is a quality-of-resample improvement, not a correctness improvement — its value is conditional on whether NA's resamples after PR 8 produce poor rewrites.
- **Trigger condition for prioritizing PR 8.5:** real-run evidence that NA's post-rejection resamples chronically produce accept-with-warning outcomes, or rewrites that just relocate the fabricated mechanism elsewhere in the statement. Until that signal appears, the simpler form is sufficient.

**Cumulative effect with prior PRs:** Decision G's blocklist now catches a class of fabrication that Decisions D and A2 cannot (their patterns are different — D / A2 catch *layer scoping*; G catches *narrative invention*). On scenarios where NA's mechanism prior was the load-bearing failure (the data plane case), G short-circuits the fabrication before it propagates to IG's plan, the Investigator's verdict reasoning, or Synthesis's diagnosis text.

---

## Decision H — NA direct-vs-derived ranking guardrail (added 2026-05-01)

**Rule today (prose):** None at the structural level. Today's NA prompt has principle #7 (*"Match each flag to at most one hypothesis. Flags clustering on the same NF are a strong signal the NF itself is the fault source"*) and principle #8 (*"the observing NF can be the fault source"*), but neither requires NA to weight a *direct-measurement* flag on NF X above a *derived* flag involving NF X. The relative ranking is left to the LLM's judgment — and the LLM gets it wrong on a meaningful fraction of runs.

**Failure mode — wrong NF survives investigation.** When Phase 0 emits both a direct flag on the actual culprit AND a derived flag on a downstream-symptom NF, NA can mis-rank. The downstream-symptom NF gets the top hypothesis, its Investigator survives investigation (because the symptom is real at that NF), and Synthesis ratifies the wrong NF with high confidence per its Case A rule (*"sole-surviving hypothesis is the root cause with high confidence"*).

The canonical example is `run_20260501_032822_call_quality_degradation` (post-PR-5):

- **Actual fault:** tc-netem injecting 30% loss on RTPEngine's container network.
- **Phase 0 flagged BOTH:**
  - **Direct:** `derived.rtpengine_loss_ratio = 23.35` (RTPEngine's own RTCP-receiver-reported loss measurement — a direct observation at RTPEngine).
  - **Derived:** `derived.upf_activity_during_calls = 0.04` (a cross-layer ratio of UPF traffic against active dialog count — a *consequence* of media-plane breakdown, not a measurement of UPF's own behavior).
- **The KB even said it.** The metric entry on `rtpengine_loss_ratio` lists the chaos-injected scenario first: *"Could be loss on the rtpengine container's egress (iptables / tc / interface congestion), loss anywhere upstream of the receiver, or — with simultaneous UPF counter degradation — loss on the N3 path."*
- **NA's mis-ranking:** h1 = UPF (fit=0.90), h2 = RTPEngine (fit=0.60), h3 = UPF-RTPEngine path (fit=0.40). The derived flag drove h1.
- **Investigator outcome:** h1 (UPF) NOT_DISPROVEN on a misread of `get_dp_quality_gauges` (Investigator interpreted UPF's `in 18.1 / out 14.7 pps` asymmetry as "UPF is dropping internally" when it's actually a measurement artifact). h2 (RTPEngine) DISPROVEN because the Investigator didn't run a triangulation probe. h3 (path) DISPROVEN — but its Investigator coincidentally ran `measure_rtt(pcscf, rtpengine)`, found 33% loss, and put `rtpengine` in `alternative_suspects`. Right answer arrived in the wrong hypothesis's alt-suspects field.
- **Decision E aggregator:** Pool = `[upf SURVIVOR, rtpengine PROMOTED]`. Survivor present → no re-investigation triggered (per E's contract). Synthesis read Case A and ratified `upf` with high confidence.
- **Final score: 21%.** Wrong NF, high (mis-calibrated) confidence.

The structural pattern: **direct-measurement flags carry stronger evidential weight than derived/cross-layer flags, but today's NA ranking gives them no priority by default.** This is the residual that the ADR's Non-goals section previously left explicitly unaddressed — Decision H closes it.

**Proposed structure:** A deterministic post-NA validator that runs after Decision D's blocklist check and Decision G's grounding check pass. Two parts:

1. **Direct-vs-derived flag classifier** — partition the Phase-0 anomaly flags into:
   - `direct` — the metric is a measurement OF the named NF's own state (e.g. `rtpengine_loss_ratio` is RTPEngine's RTCP reports about its own peers; `pcscf_processing_time` is P-CSCF's own internal timing). Authored on the metric's KB entry as `flag_kind: "direct"`.
   - `derived` — the metric is a cross-layer or composite signal whose source could be any NF in the composing path (e.g. `upf_activity_during_calls` is a ratio of UPF throughput to IMS dialog count — RTPEngine's loss can collapse it, UPF's loss can collapse it, the gNB's loss can collapse it). Authored as `flag_kind: "derived"` or `"cross_layer"`.

   The classifier reads the KB entry per flagged metric and labels the flag accordingly. Metrics whose KB entry doesn't carry the `flag_kind` field default to `derived` — conservative: an unlabeled flag doesn't earn priority weight.

2. **Ranking-coverage check** — for every direct flag, the named NF must:
   - (a) Be the `primary_suspect_nf` of at least one ranked hypothesis with `explanatory_fit ≥ 0.7`, OR
   - (b) The NA `summary` field must contain explicit reasoning naming why this NF was demoted (e.g. *"RTPEngine's loss ratio was treated as a downstream report because <evidence X>"*). Detected via substring match on the NF name AND any of {*demoted, downstream, observer, reporter, secondary, ruled out*}.

   If neither (a) nor (b) holds for any direct flag, REJECT the NA report and resample with the rejection reason injected:

   > Direct-measurement flag `rtpengine_loss_ratio` fires on `rtpengine`, but no hypothesis names `rtpengine` as `primary_suspect_nf` with `fit ≥ 0.7`, and the report `summary` does not name `rtpengine` with demotion reasoning. Direct flags carry stronger evidential weight than derived flags — promote `rtpengine` to a primary or co-primary hypothesis, OR include explicit reasoning in `summary` for why this direct flag should be treated as a downstream report.

The accept-with-warning policy from PR 2 / PR 4 / PR 5 applies on second REJECT.

**Open design questions:**

- *KB metadata coverage.* H requires every metric the screener might flag to carry a `flag_kind: "direct" | "derived" | "cross_layer"` field. Some metrics are obviously direct (named after the NF that owns them — `pcscf_processing_time`, `upf_n6_tx_errors`); others are obviously derived (anything in `derived.*` namespace, anything labeled `cross_layer` in its `What it measures` text). A coverage audit is needed before H ships, similar to the audit Decision G needs. The fallback (unlabeled → `derived`) is conservative; H's REJECT will fire less often than ideal until the KB is fully labeled, but it won't false-positive.
- *Threshold tuning.* `fit ≥ 0.7` is a starting heuristic. Too low (0.5) admits weak rankings; too high (0.9) is unrealistic when NA legitimately distributes weight across cascade hypotheses. The Apr-30 / May-1 runs that scored well had primary fit values of 0.85-0.90, so 0.7 leaves enough room for legitimate variation while still catching the 0.60 mis-rank in the call_quality_degradation run.
- *Demotion-reasoning detection.* The substring-match approach (NF name + any of {*demoted, downstream, …*}) is approximate. A better long-term form is structured: require NA to emit a typed `demoted_nfs: list[{nf, reason}]` field on the report when it intentionally treats a direct-flagged NF as a downstream observer. Defer to a follow-up.
- *Composes with Decisions D, E, G.* H is upstream of E (NA runs before Phase 6.5's pool aggregator). When H is in place, E's pool composition changes: NA's hypothesis list more often contains the actual culprit, so E's promoted-suspect path fires less often. D and G remain orthogonal — D blocks mechanism-scoping phrases, G blocks fabricated mechanism narratives, H ranks NFs correctly.
- *Why post-NA, not pre-NA?* Pre-NA enforcement would require the orchestrator to compute candidate NFs from direct flags and inject them as required hypotheses. Doable, but harder and less LLM-shaped. Post-NA REJECT-and-resample is the consistent pattern with D / A2 / G — let NA produce, validate against deterministic constraint, resample with structured feedback.

**Expected impact:** Directly addresses the wrong-NF-ranking failure exposed by the call_quality_degradation run. The linter would have flagged `rtpengine_loss_ratio` (direct flag on RTPEngine) and rejected the NA report because `rtpengine` was not in any hypothesis with `fit ≥ 0.7`. NA's resample would have either bumped RTPEngine to h1 (fit ≥ 0.7), making the Investigator probe RTPEngine more rigorously, OR included explicit demotion reasoning that downstream agents (and the human reviewer) can audit. Score floor for this scenario rises from 21% to whatever a properly-ranked RTPEngine hypothesis lands at — likely 70-100% depending on Investigator probe quality.

---

## Implementation ordering

The original ordering (D → F → A → E → C → B) was based on per-PR effort. Real-run evidence has reshuffled it three times:

1. **After PR 2 (`run_20260501_012613_data_plane_degradation`):** Decision D worked exactly as designed at the NA stage — all three statements passed the linter on first attempt with zero LLM cost. But the same mechanism-scoping failure mode showed up at the IG stage: IG re-introduced layer-scoping in `expected_if_hypothesis_holds` and `falsifying_observation` text, the Investigator marked h1 DISPROVEN on a layer mismatch, and the verdict tree was misleading (3 DISPROVEN with diagnosis still landing on UPF via `alternative_suspects`, score 90% but confidence `low`). → **Decision A bumped to PR 4 with sub-check A2.**
2. **After PR 4 (`run_20260501_022351_data_plane_degradation`):** PR 4 closed the layer-scoping leak — IG resampled, Investigator returned a clean NOT_DISPROVEN on h1, Synthesis hit calibrated high confidence, score 100%. But the same run exposed a NEW failure mode: NA *fabricated* a mechanism narrative ("traffic storm overloading the UPF") that the blocklist-based linters cannot catch because the words aren't on any blocklist. The 100% score was generous — UPF was correctly identified, but the mechanism in the diagnosis text is confabulated. → **Decision G added.**
3. **After PR 5 (`run_20260501_032822_call_quality_degradation`):** PR 5's bounded re-investigation only fires when the verdict tree is all-DISPROVEN. This run had a survivor (h1 UPF NOT_DISPROVEN) — but the WRONG NF survived. NA mis-ranked: a `direct` flag on RTPEngine (`rtpengine_loss_ratio`) lost to a `derived` flag involving UPF (`upf_activity_during_calls`). RTPEngine got h2 (fit=0.60) when it should have been h1 (fit ≥ 0.85). The h1 (UPF) Investigator survived investigation on a misread of `dp_quality_gauges`, the h2 (RTPEngine) Investigator lacked triangulation, and Synthesis ratified UPF with high confidence per Case A. Score 21%, wrong NF entirely. The Decision E candidate pool DID include RTPEngine as a PROMOTED member (via h3's strong-cite), but `pool.has_survivor=True` meant no re-investigation triggered, and Synthesis trusted the survivor. → **Decision H added.**

Implications carrying forward:

- Each shipped PR closes one residual and exposes the next. Sequencing by per-PR effort is unstable; sequencing by per-PR evidence is what produces continued gains.
- Decision F applied alone over an all-DISPROVEN tree forces `inconclusive`, weakening a diagnosis that recovered correctly. **F's value is conditional on Decision E producing clean NOT_DISPROVEN survivors first** (via the candidate-pool aggregator's bounded re-investigation path).

### Revised build order

| PR | Decision | Effort | Why this position |
|---|---|---|---|
| ✅ PR 1 | (refactor) | shipped 2026-04-30 | Created `guardrails/`, extracted existing safeguards, added `runner.run_phase_with_guardrail` |
| ✅ PR 2 | D | shipped 2026-04-30 | NA hypothesis-statement linter |
| ✅ PR 4 | A (extended: A1 + A2) | shipped 2026-05-01 | Closed the IG-side mechanism-scoping leak from `run_20260501_012613`. Validated on `run_20260501_022351`: 90% → 100% score with calibrated confidence. Same run exposed the NA fabrication failure that motivated Decision G |
| ✅ PR 5 | E | shipped 2026-05-01 | Candidate-pool aggregator + bounded re-investigation. Creates the clean NOT_DISPROVEN survivors that Synthesis-stage decisions operate on. Closes the verdict-tree-vs-diagnosis mismatch directly |
| ✅ PR 5.5a | E hardening (EV ordering) | shipped 2026-05-01 | Moved EvidenceValidator from Phase 6 (before re-investigation) to Phase 6.6 (after re-investigation) so its citation check covers the re-investigation Investigator's trace |
| ✅ PR 5.5b | E hardening (strict pool validation) | shipped 2026-05-01 | Converted Synthesis to structured `DiagnosisReport` output with typed `primary_suspect_nf: _KnownNF` and `verdict_kind` fields. New `lint_synthesis_pool_membership` guardrail rejects out-of-pool NFs; markdown renderer preserves the prose form for the recorder/scorer |
| ✅ PR 3 | F | shipped 2026-05-01 | Confidence cap. New `guardrails/confidence_cap.py` computes evidence-strength from the supporting verdict's CONSISTENT/CONTRADICTS/AMBIGUOUS counts and caps `root_cause_confidence` via the STRONG→high / MODERATE→medium / WEAK→low / NONE→low table. REPAIR pattern (silent rewrite + cap note appended to `explanation`); composed with PR 5.5b's pool-membership guardrail in Phase 7 |
| ✅ PR 9 | H | shipped 2026-05-01 | NA direct-vs-derived ranking guardrail. Added `flag_kind` to `MetricEntry` (optional; default None falls back to a naming-pattern heuristic). For every direct-flag NF, requires either `fit ≥ 0.8` placement OR explicit demotion reasoning in `summary`. Composed with Decision D in Phase 3. Threshold tightened from 0.7 → 0.8 in a follow-up bug fix after `run_20260501_042127` showed rtpengine slipping through at exactly 0.70 with invented demotion reasoning |
| ✅ PR 6 | C | shipped 2026-05-01 | Multi-shot Investigator consensus. New `guardrails/investigator_consensus.py` reconciles 2 verdicts: agreement → merged reasoning + union of alt_suspects; disagreement → forced INCONCLUSIVE; INCONCLUSIVE-touching → INCONCLUSIVE. Short-circuit on shot-1 INCONCLUSIVE saves the second LLM call. Two follow-on bug fixes (resample empty-output retry symmetry; EV trace aggregation) shipped in the same session. Validated on `run_20260501_153627_call_quality_degradation`: multi-shot reconciliation fired correctly |
| ✅ PR 8 | G (simpler form) | shipped 2026-05-01 | Mechanism-claim grounding linter — blocklist-only variant of the ADR's two-part design. New `guardrails/mechanism_grounding.py` rejects narrative-mechanism phrases (`traffic storm`, `is overloaded by`, `network partition`, `cascade failure`, etc.) on `Hypothesis.statement`. Phrase-level patterns only — bare words like `partition`, `cascading`, `storm` excluded to limit false positives. Composed into `_na_combined_guardrail` as third check (D → H → G). Smoke-tested on `run_20260501_022351` traffic-storm fabrication — REJECTs with hits `traffic storm` + `is overloaded by` |
| **PR 8.5** | G hardening (KB-grounding) | medium | Conditional follow-up on PR 8: extend the blocklist linter with a KB-grounding check. On a flagged hypothesis, walk `Hypothesis.supporting_events` and `find_chains_by_observable_metric(<metric>)` to collect KB-authored mechanisms, then include them in the rejection reason as constructive feedback — turning "your mechanism is fabricated" into "here's what the KB authorizes, pick from these." Requires async Neo4j queries inside the linter (latency cost). **Trigger condition for prioritizing this:** NA's resamples after PR 8 produce poor rewrites — chronic accept-with-warning, or rewrites that relocate the fabrication. PR 8 ships without it because the blocklist alone provides the structural REJECT; KB-grounding adds polish that may not be needed |
| **PR 7** | B | large | Typed probe selection from KB. Heaviest design; depends on KB coverage. Ships last after the cheaper structural fixes have set the floor and after G + H have exposed which KB gaps need filling |

### Sequencing principles surfaced from real-run evidence

1. **Close downstream leaks before tightening downstream caps.** A patch that prevents the wrong scope from entering the pipeline is strictly more useful than one that adjusts confidence on a diagnosis derived from already-corrupted plans.
2. **Caps need clean inputs.** F (confidence cap) over an all-DISPROVEN tree is a downgrade-only instrument and can punish correct recoveries. F + E together is what Part I's failure modes actually need.
3. **The mechanism-scoping pattern is the same shape at every stage.** Decision D's na_linter, Decision A's sub-check A2, and any future Investigator-side variant all share one regex blocklist and one shape-hint generator. Code reuse is high; cost of adding the next stage's variant is low.
4. **Blocklists catch named failure modes; KB grounding catches *invented* failure modes.** Decisions D and A2 enforce a known set of mechanism-scoping phrases; they cannot catch creative fabrications like "traffic storm" that bypass the wordlist. Decision G is the first ADR move that requires the LLM's mechanism claim to be supported by external evidence (KB) rather than blocked by a phrase list. Decision B extends the same pattern to the entire probe-design step.

### Why not do all of them at once

Each PR changes the pipeline's failure-mode distribution. Shipping them serially produces per-fix signal: after PR 4, what residual remains? (Answer surfaced 2026-05-01: NA fabrication.) After PR 5, does the verdict tree become coherent with the final diagnosis? Shipping them in parallel makes the next round of regression analysis substantially harder to attribute. The reorder above was only possible because each PR shipped first and produced a single concrete failure example that named the next priority.

---

## Non-goals of this ADR

- **Replacing the LLM agents.** The agents are still doing useful work — generating hypothesis statements, walking causal chains, interpreting probe results, synthesizing diagnoses. The seven moves above harden their outputs without removing them.
- **Eliminating prompt rules.** Some prompt rules will remain — particularly interpretive ones the Investigator uses on probe results, and the NA hypothesis-ranking heuristics. The ADR claims structural fixes scale better than prose for *constraint-shaped* failure modes (the IG must include a partner probe; the NA must not use scope words; the NA must not invent mechanisms the KB doesn't authorize; Synthesis must not pick a suspect outside the candidate pool; Synthesis must not claim high confidence on weak evidence). It does NOT claim every prompt rule should be replaced.
- **Solving full NA-stage hypothesis-ranking variance.** Part I documented run-to-run variance at two stages: NA hypothesis-ranking ("flagged NF is the cause" vs "flagged NF is the reporter") and Synthesis confidence calibration. The Synthesis-stage failures are addressed by Decisions E and F together (E creates clean NOT_DISPROVEN survivors; F caps confidence on them) — neither in isolation is sufficient. Decision C (multi-shot consensus) addresses Investigator-stage variance. **The direct-vs-derived flag-ranking variant of NA-stage ranking is now addressed by Decision H** (added 2026-05-01 after `run_20260501_032822_call_quality_degradation`). Other NA-stage ranking variants — e.g. Part I's original "P-CSCF was not in the hypothesis list at all" failure where the right NF is missing entirely from NA's output — remain partially addressed by H (if the missing NF was flagged by Phase 0 as `direct`, H requires it to appear in the hypothesis list) but not fully (NF flagged only via correlation hints, not a direct flag, can still be missed). The general "ensure every plausibly-implicated NF appears somewhere in NA's ranked list" guardrail is still out of scope.

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

Superseded — see the **Implementation ordering** section above for the current build sequence. The original sequence pinned in this section was D → F → A → E → C → B, ordered by per-PR effort. Real-run evidence after each shipped PR reshuffled it three times — first to A (extended) → E → F → C → B after `run_20260501_012613_data_plane_degradation`, then to E → F → C → G → B after `run_20260501_022351_data_plane_degradation` exposed the NA fabrication failure mode (Decision G added), and most recently to F → H → C → G → B after `run_20260501_032822_call_quality_degradation` exposed the NA direct-vs-derived ranking failure (Decision H added). PRs 1, 2, 4, 5, 5.5a, 5.5b, 3, 9, 6, and 8 have shipped; the remaining queue is the conditional PR 8.5 (Decision G hardening — KB-grounding) and PR 7 (Decision B — typed probe selection from KB). The full rationale lives in *Implementation ordering › Revised build order*.

---

## References

- Part I: [`../critical-observations/challenge_with_stochastic_LLM_behavior.md`](../critical-observations/challenge_with_stochastic_LLM_behavior.md)
- Part II: [`../critical-observations/challenge_with_stochastic_LLM_behavior_part_II.md`](../critical-observations/challenge_with_stochastic_LLM_behavior_part_II.md)
- The temporality work that established the "move load out of the LLM" pattern: [`dealing_with_temporality_3.md`](dealing_with_temporality_3.md)
- The diagnostic-tool work that did the same thing for tool output curation: [`get_diagnostic_metrics_tool.md`](get_diagnostic_metrics_tool.md)
