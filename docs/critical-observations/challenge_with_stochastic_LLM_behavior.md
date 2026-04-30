# Challenge: Stochastic LLM Behavior on Identical Scenarios

**Date:** 2026-04-29
**Agent version:** v6 (ADK 1.31.1 + gemini-2.5-pro on NA / IG / Investigator / Synthesis, gemini-2.5-flash on OntologyConsultation)
**Status:** Open question — placeholder, not an action plan. Capture this so we come back to it after the more concrete fixes ship.

---

## Topline

The same scenario, run twice on the same code, scored **90%** and then **26%**. That's a 64-point swing on a single re-run with no infrastructure change. Both runs went through every phase cleanly (no 429, no IG empty output, no missing screener flags). The difference is entirely in how the agent's reasoning chain happened to roll on each attempt.

This is a **structural variance issue** in the diagnostic pipeline, not a bug in any single phase. Even with the screener, retry, IG-guard, and ECOD fixes shipped today, the upper bound on diagnosis quality is dragged down by the agent's stochastic hypothesis-ranking and synthesis behavior.

| Episode | Time | Score | Verdict |
|---|---|---|---|
| [`run_20260429_160907_p_cscf_latency`](../../agentic_ops_v6/docs/agent_logs/run_20260429_160907_p_cscf_latency.md) | 16:09 | **90%** | Correctly identified P-CSCF latency |
| [`run_20260429_175811_p_cscf_latency`](../../agentic_ops_v6/docs/agent_logs/run_20260429_175811_p_cscf_latency.md) | 17:58 | **26%** | Wrongly blamed S-CSCF for "partial failure dropping REGISTERs" |

Same scenario (`P-CSCF Latency`, `tc netem` injecting latency on the P-CSCF container). Same model. Same screener, same retry config, same ADK version. ~2 hours apart.

---

## What the failed run actually did

The 17:58 run produced a high-quality, internally-consistent diagnostic chain that landed on the wrong NF. Every phase did its job; the chain just oriented the wrong way at the top.

**Phase 0 (Anomaly Screener)** correctly placed `derived.pcscf_sip_error_ratio = 0.20 (MEDIUM, spike)` as the **top flag** in the report — the strongest direct signal that something is wrong at P-CSCF specifically.

**Phase 3 (NetworkAnalyst)** read that flag and ranked three hypotheses:
- `h1` PCF (fit=0.90) — *"P-CSCF rejecting because PCF auth is failing"*
- `h2` pyhss (fit=0.40)
- `h3` scscf (fit=0.30)

**P-CSCF was not in the hypothesis list at all.** NA interpreted `pcscf_sip_error_ratio` as a *symptom* P-CSCF was reporting about its downstream PCF, not a sign P-CSCF itself was the problem.

**Phase 5 (Investigators)** disproved h1 and h2 cleanly with strong evidence (PCF metrics show 100% success — its 18 received requests all processed; HSS RTT is sub-millisecond; Diameter timeouts are zero). h3 (S-CSCF) survived only because it found a registration-count discrepancy (I-CSCF received 23, S-CSCF received 14) — but the discrepancy is itself a downstream effect of P-CSCF latency causing transaction timeouts before all REGISTERs propagate the chain.

**Phase 7 (Synthesis)** chose `h3 (scscf)` as the final answer because it was the only `NOT_DISPROVEN` hypothesis. Confidence: high. Score: 26%.

The mechanical chain was sound. The diagnostic vocabulary chosen at Phase 3 just didn't include the right answer.

---

## The two failure patterns visible in this episode

### Pattern A — NA blind spot: "the flagged NF IS the cause"

When P-CSCF (or any specific NF) fires a direct symptom flag, NA tends to interpret the flag as "this NF is *reporting* a problem from somewhere else" rather than "this NF *has* a problem." The result is hypothesis lists that surround the actual cause without ever naming it.

This pattern is visible across multiple runs:
- `call_quality_degradation` (rtpengine fault → NA blames UPF)
- `p_cscf_latency` 17:58 (P-CSCF fault → NA blames PCF)
- `mongodb_gone` 16:43 (90% → 46% regression on Apr-29 batch — same family)

It does not show on every run — the 16:09 P-CSCF run got it right. The pattern is *probabilistic*, not deterministic.

### Pattern B — Synthesis ignores `alternative_suspects` from disproven hypotheses

The 17:58 run is especially telling because the **right answer was inside the run's evidence**. The h1 investigator's verdict explicitly noted:

> *"The discrepancy between P-CSCF's 696 connection failures and PCF's 18 received requests points to a connectivity or configuration issue upstream of the PCF."*
> 
> **Alternative suspects:** `pcscf`

So an Investigator already wrote down that P-CSCF was the likely real culprit. That hint was structured data on the verdict object. Synthesis didn't read it. It only consulted the verdict tree — DISPROVEN / NOT_DISPROVEN — and picked the only `NOT_DISPROVEN` it had.

This is a real signal getting dropped on the floor at the synthesis step. Even when the underlying probes have correctly identified the suspect, the diagnosis can land elsewhere because the synthesis prompt doesn't promote `alternative_suspects` into the candidate set.

---

## Why the obvious fixes are Hail Marys

When the user asked what to do, three options came up. Two are weak:

### Option 1 — Strengthen NA prompt to always rank flagged NFs as primary suspects (rejected)

Sketch: *"If a Phase 0 flag fires directly on an NF, that NF must appear as a primary or secondary hypothesis."*

Why this is a Hail Mary: it patches one specific failure mode (the "NF reports vs NF is" interpretation flip) but doesn't address the underlying issue. The same prompt could *also* push NA toward over-ranking flagged NFs in scenarios where the flagged NF is genuinely just symptomatic. We'd be trading one class of error for another, with no principled way to know which side of the trade-off we're on without batch evidence over many runs. Prompt-engineering whack-a-mole with high variance.

### Option 2 — Re-run scenarios and average (rejected)

Sketch: run each scenario N times and report mean + stdev to smooth over single-roll variance.

Why this is a Hail Mary: useful for *evaluation* (knowing the true average score on a scenario), useless for *operation*. A real operator running diagnostics in production gets one shot. Averaging hides the variance, doesn't fix it. The system still produces wrong answers a meaningful fraction of the time.

### Option 3 — Synthesis consults `alternative_suspects` (kept as the principled fix)

Sketch: when no hypothesis is definitively `NOT_DISPROVEN`, OR when the evidence in disproven hypotheses points elsewhere, Synthesis should read `alternative_suspects` from the disproven verdicts and consider those as candidate root causes — possibly issuing a re-investigation request before committing to a final diagnosis.

Why this is principled: it uses signal that the agents are *already producing* but is being thrown away. It doesn't push NA to hallucinate suspects it didn't propose; it surfaces the actual evidence the Investigators uncovered. The `alternative_suspects` field is structured data, not free text, so the synthesis logic can consume it deterministically.

---

## The broader question this run is a placeholder for

> **What does Synthesis do when no hypothesis is solid?**

Two failure modes belong to this category:

1. **All hypotheses disproven** (none survived investigation). Today: Synthesis gives up and writes a low-confidence "investigation inconclusive" diagnosis. But the disproven verdicts may collectively point to a root cause that wasn't initially hypothesized — the alternative_suspects pattern shipped here.

2. **All hypotheses are weakly NOT_DISPROVEN** (e.g. all three hypotheses survived but none were strongly confirmed because the probes were inconclusive). Today: Synthesis picks the highest-fit one and ratifies it with high confidence — too high for the actual evidence. The 17:58 P-CSCF run is partly an instance of this: only one hypothesis survived, but it survived weakly (one consistent probe, one contradicting, one supportive only of a "partial failure" framing), and Synthesis still rated it high-confidence.

A solid solution should:
- Promote `alternative_suspects` from disproven hypotheses into the candidate set when no strong NOT_DISPROVEN exists.
- Optionally trigger a *targeted re-investigation* on the promoted suspect rather than committing to it directly. (Bounded: max one re-investigation per scenario, otherwise we have unbounded loops.)
- Calibrate Synthesis confidence to the actual strength of the evidence — a single-NOT_DISPROVEN-but-weakly-supported hypothesis should not produce `confidence: high`.

These are prompt + orchestration changes, not screener or model architecture changes. They live in `agentic_ops_v6/orchestrator.py` (re-investigation orchestration) and `agentic_ops_v6/prompts/synthesis.md` (confidence calibration + alternative_suspects consumption).

---

## Why this is a placeholder, not a build item right now

Three reasons to defer:

1. **Today's batch already moved the mean from 65.6% → 73.5%** on the back of the screener / retry / IG-guard / container-pre-check fixes. The variance issue documented here is now a larger-relative share of the remaining error budget, but in absolute terms the system is producing better results than it was 24 hours ago.

2. **The required design work is non-trivial.** A re-investigation loop changes orchestration topology, has resource-budget implications (more LLM calls per scenario), and needs careful guards against infinite loops or runaway cost. Deserves its own ADR.

3. **More single-scenario re-runs first will tell us the magnitude of the variance problem.** A 64-point swing on one scenario is alarming, but until we have N=5+ runs of the same scenario we don't know the actual distribution. The variance might be normal (broad with thick tails) or might cluster bimodally (gets it right or gets it badly wrong). Different distributions imply different fixes.

When we come back to this, the work breaks into roughly:

- Capture variance distribution: run 4-5 high-impact scenarios 5x each, plot per-scenario score histograms.
- Audit `alternative_suspects` usage: how often do disproven Investigators surface a correct suspect that Synthesis ignored?
- Design the re-investigation loop in an ADR.
- Implement.
- Validate against the variance distribution captured in step 1.

---

## Related observations

- [`anomaly_model_overflagging.md`](../ADR/anomaly_model_overflagging.md) — the structural ceiling at 65–75% identified in this ADR was about screener-driven misattribution. With that fixed today, the ceiling has moved up but a new structural ceiling (driven by NA hypothesis-ranking + Synthesis variance) is visible.
- [`anomaly_detector_replace_river_with_pyod.md`](../ADR/anomaly_detector_replace_river_with_pyod.md) — the screener replacement that lifted the previous ceiling. The variance issue documented here is independent.
- [`falsifier_investigator_and_rag.md`](../ADR/falsifier_investigator_and_rag.md) — earlier work that introduced the `alternative_suspects` field on Investigator verdicts. The data is being captured; it's just not being consumed.
