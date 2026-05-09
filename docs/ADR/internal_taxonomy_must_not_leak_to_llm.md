# ADR: Internal Validator Taxonomy Must Not Reach the LLM

**Date:** 2026-05-06
**Status:** Proposed
**Related:**
- Critical observation: [`../critical-observations/why_agent_fails_with_dataplane_failure_scenarios.md`](../critical-observations/why_agent_fails_with_dataplane_failure_scenarios.md) — Bonus issue: "References to ADR decisions leaking in Agent's reasoning".
- Post-investigation analysis (2026-05-06, in-conversation): traced the leak from `agentic_ops_v6/prompts/instruction_generator.md:18` (which exposes `A1`/`A2` rule labels in the resample template) through `agentic_ops_v6/guardrails/ig_validator.py` (which authors them) to the LLM-emitted plan notes in `agentic_ops_v6/docs/agent_logs/run_20260504_160632_call_quality_degradation.md:205,222,239`.
- [`structural_guardrails_for_llm_pipeline.md`](structural_guardrails_for_llm_pipeline.md) — the ADR that introduced the `A1`/`A2`/Decision-letter taxonomy, intended for engineers, that has since leaked into LLM-facing surfaces.

---

## Decision

Implementation labels for guardrails (`A1`, `A2`, "Decision A," "Decision G," "linter feedback," "guardrail," "ADR," etc.) belong in code, ADRs, and engineer-facing logs only. They must never appear in any string the LLM reads, and must never appear in any string the LLM emits. Three coordinated changes ship together:

1. **Strip identifier labels from validator-authored feedback at the source.** `agentic_ops_v6/guardrails/ig_validator.py` (and every sibling under `agentic_ops_v6/guardrails/`) emit feedback strings that today carry `[A1]`, `[A2]`, `Decision X`, etc. as prefixes. Rewrite the emit functions to produce **only** the descriptive content (the offending phrase, the bad/good shape, the corrective example) without any identifier. Identifiers stay in the code's logging output (`logger.info(f"[A1] rejected …")`) and in the validator's structured return type (so engineers reading the trace can still see which rule fired) — but the LLM-facing string carries none of them.
2. **Rewrite the resample prompt templates to drop the taxonomy.** `agentic_ops_v6/prompts/instruction_generator.md` line 18 explicitly hands `A1` and `A2` to the LLM as part of the resample feedback context. Rewrite the resample-context paragraph to describe what the feedback contains (the offending phrase, the corrective shape, an example) without naming the validator rules. Sweep every prompt under `agentic_ops_v6/prompts/` and `agentic_ops_v6/subagents/` for the same pattern (see Audit below).
3. **Add a structural output sanitizer.** A new module `agentic_ops_v6/guardrails/llm_output_sanitizer.py` runs over every LLM-emitted artifact destined for the user-facing report (Synthesis output, IG plan `notes` fields, Investigator reasoning text) and rejects-with-rewrite any artifact containing the leaked-taxonomy regex (`\b(?:Decision\s+[A-Z]|A[0-9]+|D[0-9]+|linter\s+feedback|guardrail(?:\s+rejection)?|ADR(?:[\s_-][a-z_]+)?)\b`). The rejection forces a resample with feedback that says only "remove implementation references from your output" — without itself naming what was leaked, so the sanitizer cannot teach the LLM the taxonomy by example.

The triplet — source-strip, prompt-strip, output-sanitizer — closes both directions: the LLM never sees the labels (so it cannot learn them), and any latent learning is caught at the output gate before it reaches the user-facing report.

## Context

`agentic_ops_v6/prompts/instruction_generator.md:18`:

> *"If the section above is non-empty, your previous FalsificationPlanSet was REJECTED by the post-IG linter (Decision A). Read the per-plan, per-probe feedback carefully — it names the offending sub-check (A1 = missing partner probe, A2 = mechanism-scoping language in expected/falsifying text), quotes the exact phrase that fired, and gives a concrete bad/good example."*

This paragraph hands the LLM a vocabulary for talking about its own failures using the project's internal taxonomy. The validator at `agentic_ops_v6/guardrails/ig_validator.py` then populates `{guardrail_rejection_reason}` with strings that begin `[A1] Compositional tool …` or `[A2] Mechanism-scoping language detected: …`. The LLM resamples, sees the labels, and now thinks of its plan's defects in terms of A1 and A2.

Several iterations later, the LLM generates plans that reference its own corrections in those terms. From `agentic_ops_v6/docs/agent_logs/run_20260504_160632_call_quality_degradation.md:205, 222, 239`:

> *"This plan uses a compositional probe pair (icscf->pyhss and scscf->pyhss) to isolate the HSS component, addressing **linter feedback A1**."*
>
> *"This plan addresses **linter feedback A1 and A2**. Probe 1 avoids mechanism-scoping language by checking a specific metric."*
>
> *"This plan uses a compositional probe pair to test network paths to the I-CSCF from its peers (P-CSCF, S-CSCF), addressing **linter feedback A1**."*

The `notes` field of a falsification plan is rendered into the user-facing episode report. The internal taxonomy of a Python guardrail is now appearing in user-readable text. That's the surface symptom; the underlying cause is that the prompt taught the LLM the vocabulary in the first place.

### Why the labels exist at all

The labels (A1, A2, Decision A through H, etc.) are useful for engineers tracing why a plan was rejected — when reading code, ADRs, or structured logs, they are a stable cross-reference. They earn their keep in `agentic_ops_v6/guardrails/` and in [`structural_guardrails_for_llm_pipeline.md`](structural_guardrails_for_llm_pipeline.md). The mistake was extending that audience to the LLM.

### Why both source-strip AND output-sanitizer are needed

Source-strip alone: removes the labels from current prompts and validator output, but does not protect against future drift (a developer adding a new validator forgets the convention) or against any latent learning the LLM has already absorbed from training-data-adjacent surfaces. The sanitizer is a structural backstop.

Output-sanitizer alone: catches leaks at the gate but does not stop the LLM from generating leaked text in the first place (which costs tokens to produce-then-reject and degrades resample quality). The source-strip closes the upstream cause.

The two are complementary, not redundant.

### Why the sanitizer's rejection feedback must be content-blind

If the sanitizer says *"your output contained the string 'A1' — remove it,"* it has just taught the LLM that "A1" is meaningful. The rejection feedback must be deliberately uninformative — *"remove implementation references and rewrite the artifact in domain terms only."* The LLM's resample now uses fewer implementation terms because it has fewer specific things to remove, not because it learned a new taxonomy from the rejection.

## Design

### Validator-side strip (`agentic_ops_v6/guardrails/`)

Every guardrail under `agentic_ops_v6/guardrails/` follows the same emit pattern:

```python
# Today (offending shape):
return GuardrailResult(
    passed=False,
    feedback=f"[A1] Compositional tool `{tool}` needs a partner probe. "
             f"Bad: `{bad}`. Good: `{good}`.",
    rule_id="A1",
)
```

Rewritten to:

```python
return GuardrailResult(
    passed=False,
    feedback=(
        f"Compositional tool `{tool}` needs a partner probe to triangulate "
        f"the result. The current plan offers only one side of the "
        f"comparison.\n"
        f"Example of insufficient: `{bad}`.\n"
        f"Example of sufficient: `{good}`."
    ),
    rule_id="A1",  # retained — engineer-facing, never LLM-facing
)
```

Two structural rules for the rewrite:

- The `rule_id` field stays in the typed return value for engineer-facing logs and trace aggregation. The `feedback` string never embeds it.
- Feedback is written in domain terms only: "compositional tool," "partner probe," "mechanism-scoping language" — these are concepts the LLM should know from the prompts. They are not implementation labels.

Files affected (full list to be derived from a grep, but minimum set):

- `agentic_ops_v6/guardrails/ig_validator.py`
- `agentic_ops_v6/guardrails/na_ranking.py`
- `agentic_ops_v6/guardrails/mechanism_grounding.py`
- `agentic_ops_v6/guardrails/synthesis_pool.py`
- `agentic_ops_v6/guardrails/confidence_cap.py`

### Prompt-side strip (`agentic_ops_v6/prompts/`)

`agentic_ops_v6/prompts/instruction_generator.md:18` rewrite:

> *If the section above is non-empty, your previous FalsificationPlanSet was rejected. Read the per-plan, per-probe feedback carefully — it quotes the exact phrase that fired the rejection and gives a concrete bad/good shape. Address each issue in your resample by replacing the rejected phrase with the corrective shape; do not reference this feedback or the rejection process in your output.*

Two pieces of work:

- The substantive rewrite as above (no `Decision A`, no `A1`, no `A2`, no "linter").
- A trailing instruction — "do not reference this feedback or the rejection process in your output" — which tells the LLM that internal mechanisms are not part of the artifact it's producing. This is light belt-and-suspenders against latent learning.

A grep over `agentic_ops_v6/prompts/` for the patterns `Decision\s+[A-Z]`, `\bA[0-9]\b`, `\bD[0-9]\b`, `linter`, `guardrail`, `ADR` enumerates every leakage site. Each is rewritten in the same PR.

### Output sanitizer (`agentic_ops_v6/guardrails/llm_output_sanitizer.py`)

```python
LEAK_PATTERN = re.compile(
    r"\b(?:"
    r"Decision\s+[A-Z]"      # "Decision A", "Decision G"
    r"|A[0-9]+"              # "A1", "A2"
    r"|D[0-9]+"              # any future Decision-X / sub-check tags
    r"|linter\s+feedback"
    r"|linter\s+rejection"
    r"|guardrail(?:\s+(?:rejection|feedback|warning))?"
    r"|ADR(?:[\s_-][a-z_]+)?"
    r")\b",
    re.IGNORECASE,
)

def sanitize_artifact(text: str) -> SanitizationResult:
    if LEAK_PATTERN.search(text):
        return SanitizationResult(
            passed=False,
            # deliberately uninformative — see ADR rationale.
            feedback=(
                "Your artifact contains references to internal "
                "implementation mechanisms. Rewrite using domain terms "
                "only — describe what the plan / hypothesis / diagnosis "
                "DOES, not how it was produced or validated."
            ),
        )
    return SanitizationResult(passed=True, feedback=None)
```

Composition points (`agentic_ops_v6/orchestrator.py`):

- After IG plan emission — runs over each `FalsificationPlan.notes` field.
- After Investigator emission — runs over `InvestigatorVerdict.reasoning`.
- After Synthesis emission — runs over the `DiagnosisReport.explanation` and `recommendation` fields.

The sanitizer composes with existing per-stage guardrails the way Decision A's IG validator and Decision G's mechanism-grounding linter already compose (see [`structural_guardrails_for_llm_pipeline.md`](structural_guardrails_for_llm_pipeline.md)). It runs last in each stage's chain, after the substantive linters have passed — so a plan that fails A1/A2 isn't simultaneously rejected for taxonomy leak.

The sanitizer's REJECT triggers a resample, capped at one resample (matching the existing per-stage resample budget). On second REJECT, the sanitizer writes a structured warning to `state["guardrail_warnings"]` and accepts the artifact — same accept-with-warning policy used by Decisions D and H.

### Audit and prevention pass

A grep-based unit test (`agentic_ops_v6/tests/test_no_taxonomy_leakage_in_prompts.py`) runs `LEAK_PATTERN` over every `.md` file under `agentic_ops_v6/prompts/` and every Python string literal under `agentic_ops_v6/subagents/`. CI fails on any hit. This protects against future drift — adding a new guardrail with a leaky prompt is caught at PR-review time.

Code comments and ADRs are explicitly out of scope: the test only scans LLM-facing surfaces. The audit script in CI uses an allowlist of file patterns (`agentic_ops_v6/prompts/**/*.md` and string literals in `agentic_ops_v6/subagents/**/*.py`), not the whole repo.

### Why ship source-strip, prompt-strip, output-sanitizer, and audit test together

Each addresses a different failure mode:

- Validator-side strip: closes the upstream feed.
- Prompt-side strip: closes the LLM's training surface.
- Output sanitizer: closes the user-facing report.
- Audit test: prevents regression.

Splitting them across PRs leaves latent leakage paths open — for example, source-strip without output-sanitizer means existing in-flight conversations (long-running sessions) could continue to leak from cached prompt context. The four pieces protect each other.

## Verification

After implementation:

1. Run a re-test of the IG resample path: force a Decision-A rejection by submitting a plan with mechanism-scoping language; confirm the resample feedback the LLM sees contains no `[A1]`, `[A2]`, `Decision A`, `linter`, or `guardrail` substrings. Engineer-facing logs still contain `rule_id="A1"` for trace aggregation.
2. Run a full chaos scenario (e.g. `call_quality_degradation`); grep the resulting episode report for the leak pattern. Zero hits required.
3. Forced regression: temporarily author a plan note that says "addresses linter feedback A1." Run it through the IG path; confirm the sanitizer rejects, the resample feedback is the content-blind variant, and on second-REJECT the warning lands in `state["guardrail_warnings"]`.
4. CI: the prompt-audit test runs and passes; introducing the offending paragraph from `instruction_generator.md:18` (now removed) into any prompt fails CI.

Plus:

- `test_validator_feedback_is_content_only`: each guardrail's `GuardrailResult.feedback` against representative inputs contains no leak-pattern hit; `rule_id` field still set.
- `test_sanitizer_rejects_taxonomy`: every entry in a curated leak corpus (one per pattern variant) triggers REJECT with the content-blind feedback.
- `test_sanitizer_passes_clean_text`: legitimate domain terms (`hypothesis`, `falsification plan`, `compositional probe`, `mechanism`) pass cleanly.
- `test_no_taxonomy_leakage_in_prompts`: the prompt-audit grep across `agentic_ops_v6/prompts/` and `agentic_ops_v6/subagents/` returns zero hits.

## Files Changed

- `agentic_ops_v6/guardrails/ig_validator.py`, `na_ranking.py`, `mechanism_grounding.py`, `synthesis_pool.py`, `confidence_cap.py` — strip taxonomy labels from `feedback` strings; preserve `rule_id` field.
- `agentic_ops_v6/guardrails/llm_output_sanitizer.py` — new module.
- `agentic_ops_v6/orchestrator.py` — wire the sanitizer into IG, Investigator, and Synthesis stages.
- `agentic_ops_v6/prompts/instruction_generator.md` — rewrite the resample-context paragraph (line 18 area); grep-and-rewrite any sibling leak.
- `agentic_ops_v6/prompts/investigator.md`, `network_analyst.md`, `synthesis.md` (and any others under `agentic_ops_v6/prompts/`) — same grep-and-rewrite pass.
- `agentic_ops_v6/subagents/instruction_generator.py`, `investigator.py`, `network_analyst.py`, `synthesis.py` — same grep over Python string literals; rewrite any leaky inline prompt construction.
- Tests as listed in Verification, including the CI-enforcing `test_no_taxonomy_leakage_in_prompts.py`.

## Alternatives Considered

1. **Output sanitizer alone, leave the prompts and validator alone.** Rejected. The LLM still sees the labels, still produces them, and the sanitizer rejects-then-resamples — wasteful in tokens and degrades resample quality. The source-strip is cheap and closes the cause.

2. **Strip the prompts but not the validator output.** Rejected. The LLM sees the validator's `feedback` string during resample; that's the most direct training surface. Stripping the prompt without stripping the validator output reaches the LLM via a slightly slower path, but it still reaches.

3. **Have the sanitizer's rejection feedback name the offending phrase ("you used 'A1' — remove it").** Rejected — see "Why the sanitizer's rejection feedback must be content-blind" in the Context section. The rejection becomes a teaching moment for exactly the wrong vocabulary.

4. **Allow the labels in `notes` but strip them at report-rendering time.** Rejected. Same problem on a different axis: the labels live in the artifact (which is then queryable, indexable, replayable in subsequent sessions). The structural fix is to never produce them.

5. **Have the LLM emit machine-readable rule references in a structured side-channel and only render domain terms in user-facing text.** Rejected as over-engineering. The LLM does not need to track which rule it addressed; the engineer-facing logs already record `rule_id` from the validator side. Adding a side-channel for the LLM to emit it back is ceremony.

## Follow-ups

- Once the audit test is in place, watch for new leak patterns in subsequent Decisions (this codebase has Decisions A through H today; the next ones will accrue new labels). The audit pattern may need extending. Tracked in the audit test itself, not as a separate ADR item.
- Consider whether the same content-blind rejection pattern should apply to other internal-mechanism leaks — e.g., the LLM citing "the orchestrator," "phase 5," "the synthesis stage" by their pipeline names. Out of scope for this ADR; the leakage pattern is narrower right now and an over-aggressive sanitizer would catch legitimate domain text.
