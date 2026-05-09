"""Guardrails — deterministic checks that wrap the LLM phases of the v6 pipeline.

This package consolidates the post-emit validators, replication / reconcilers,
and pre-emit constraint helpers that the orchestrator uses to keep stochastic
LLM output inside known-good bounds. Each guardrail is a pure-Python module
with one entrypoint per check; the orchestrator calls them between phases.

Design rationale and the per-decision scope live in
`docs/ADR/structural_guardrails_for_llm_pipeline.md`. The first PR landed
purely the extraction of code that was previously inlined in the
orchestrator (silent-bail retry, fan-out audit, minimum-tool-call check,
evidence-citation validator). Subsequent PRs add Decisions A, D, E, F.
"""
