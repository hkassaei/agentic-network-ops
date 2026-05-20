# Next Work Package — RAG / Observability Bug Audit + Evidence-Grounded NA

**Date:** 2026-05-15
**Status:** Awaiting decision on path forward
**Trigger:** Session on `run_20260514_222937_data_plane_degradation` (Data Plane Degradation single-fault scenario, 100% score, 434K tokens — see below for why the score number masks real issues)

---

## Context — what surfaced

Across four runs (cascading_ims_failure ×2, data_plane_degradation ×2) we uncovered **six distinct silently-shipped bugs** spanning RAG, observability, and the recorder layer. All caught by manual inspection of episode markdown, not by automated tests. Two are still un-fixed:

- **Bug A** (`agentic_ops_v7/orchestrator.py`): the application-layer Synthesis path writes `state["diagnosis_structured"]` but NOT `state["diagnosis_report"]`. Result: every v7 app-layer episode has `challenge_result.diagnosis_report = null` in its serialized JSON. This corrupted the entire v7 portion of the indexed RAG corpus from the May-10 batch onward.
- **Bug B** (`agentic_ops_common/rag/parser.py`): the RAG parser reads `primary_suspect_nf` only from `challenge_result.diagnosis_report.primary_suspect_nf`, which is a v7-only structured key. v6 episodes have free-text `diagnosis_text` carrying the same info but the parser has no fallback. Result: every v6 corpus entry shows `?` in the "Primary suspect" column the NA reads.

Together these two bugs are why `run_20260514_222937` saw a RAG hits table where four of five "Primary suspect" cells were `?` — and where the only populated cell (`rtpengine` from a call-quality-degradation case) likely contributed to the ghost-rtpengine hypothesis pollution captured separately in [`ADR/na_evidence_grounding.md`](ADR/na_evidence_grounding.md).

The remaining four bugs are already fixed in code (tests pinned) but are listed below so the audit is complete.

---

## Pending bug fixes (priority order)

> **Status update (2026-05-20):** Bug A, Bug B, and the index rebuild (step 3) are all done. RAG corpus null-rate for `primary_suspect`: **95% → 25%** (102 indexed cases; v7 fully populated, v6 80% populated, v5 48% populated). Only step 4 (na_evidence_grounding ADR implementation) remains.

### 1. Bug A — write `diagnosis_report` on the app-layer Synthesis path

**Location:** `agentic_ops_v7/orchestrator.py:2770-2773`

**Current:**
```python
state[_SYNTHESIS_OUTPUT_KEY] = _render_diagnosis_report_to_markdown(diagnosis_report)
state["diagnosis_structured"] = diagnosis_report.model_dump(mode="json")
# state["diagnosis_report"] is never written here — bug
```

**Fix:** add the parallel line that the localized branch already has at `orchestrator.py:789-792`:
```python
state["diagnosis_report"] = diagnosis_report.model_dump(mode="json")
```

**Scope:** one-line addition, no schema change. After this lands, every future v7 app-layer episode will have populated `diagnosis_report` in its JSON, which is what the RAG parser and `_build_result()` already read.

**Walk:** `_build_result` (`orchestrator.py:2961`) reads `state.get("diagnosis_report")` → episode JSON's `challenge_result.diagnosis_report`. Recorder consumes via `_render_v7_pipeline` / `_format_localized_diagnosis`. RAG parser consumes via `parse_episode → diagnosis_primary`. Test gates: `agentic_ops_v7/tests/test_orchestrator_*` if they exist; otherwise integration regression by running any scenario and grep'ing the resulting JSON for `"diagnosis_report": null` (should not appear post-fix).

---

### 2. Bug B — parser fallback for v6 (and old v7) primary_suspect_nf

**Location:** `agentic_ops_common/rag/parser.py:347`

**Current:**
```python
diagnosis_primary = dr.get("primary_suspect_nf") if isinstance(dr, dict) else None
```

**Fix:** add two fallback paths in order:

1. **Affected components.** Read `challenge_result.diagnosis_report.affected_components` (if dict) or parse the markdown `affected_components` list in `diagnosis_text` for the entry with `role: "Root Cause"`. Take that NF.
2. **Regex on diagnosis_text.** Look for `(primary_suspect_nf:\s*` `` `<nf>` `` `)` — the pattern v7's markdown renderer emits in the rendered `root_cause` line. Works for v7 cases that pre-date Bug A's fix (the markdown renderer was producing this pattern even while the structured key was unset in state).

The two fallbacks complement: affected_components is the most reliable for v6 (it's structurally present in the markdown), regex on diagnosis_text catches old-v7 cases where the markdown was rendered but the structured key wasn't surfaced.

**Scope:** one helper function (~30 lines), two new call-sites in the parser, plus unit tests on hand-shaped v6 and old-v7 episode JSONs.

**Walk:** `parse_episode` → `RetrievedCase.diagnosis_primary_suspect_nf` → RAG search payload → recorder rendering. After this fix, the RAG index must be rebuilt (`python -m rag_indexer`) so the corpus picks up the new parser output.

---

### 3. Rebuild RAG index

After Bug A + Bug B land. Run from repo root:
```
python -m rag_indexer
```

The current index is at `rag_index/` (manifest tracks corpus size = 97 cases). After rebuild, the corpus should have populated `diagnosis_primary_suspect_nf` for the substantial majority of entries — both v6 (via affected_components fallback) and v7 (via the new orchestrator write going forward, plus the markdown-regex fallback for already-indexed v7 cases).

**Sanity check:** spot-grep the new index for `"diagnosis_primary_suspect_nf": null` and confirm the count drops dramatically vs. the current index.

---

### 4. Land the `na_evidence_grounding` ADR

ADR drafted at [`docs/ADR/na_evidence_grounding.md`](ADR/na_evidence_grounding.md). Two coupled changes:

1. **Prompt rule** in `agentic_ops_v7/prompts/network_analyst.md` — the evidence-grounded NF directive + ghost-rtpengine counter-example.
2. **Mechanical guardrail** `lint_na_evidence_grounding` in `agentic_ops_v7/guardrails/na_evidence_grounding.py` — REJECT any `Hypothesis.primary_suspect_nf` outside the grounded set ({Phase-0 flag NFs} ∪ {Phase-1 event NFs} ∪ {Phase-0.6 walker-attributed NFs}). Wires into Phase 3 between Decision D (mechanism-scoping) and Decision H (ranking-coverage).

This is the structural fix for RAG-induced hypothesis pollution observed in `run_20260514_222937`. Bug A + Bug B's fixes will reduce the *pressure* on this guardrail by giving the NA better RAG signal upstream, but the guardrail is the load-bearing structural defense.

**Open questions in the ADR** still to resolve:
- Permit ambiguous-bucket NFs in grounded set? (Drafted: yes — defer tightening.)
- Require demotion keywords for `summary`-mentioned ungrounded NFs? (Drafted: no — defer.)
- Integration test pins "h1 != rtpengine" or "h1 == upf"? (Drafted: not-equal — more robust to LLM variance.)

---

## Already-fixed bugs (audit complete, listed for the record)

These are fixed in code with regression tests pinned. Listed so the audit history is complete.

| # | Bug | Location | Fix | Pinning test |
|---|---|---|---|---|
| ✅ | Challenger shim dropped 3 RAG observability keys | `agentic_chaos/agents/challenger.py:412-433` and `:187-209` | Added missing forward-write entries | `test_challenger_rag_observability_forwarding.py` |
| ✅ | Walker `?[?]` header — shape mismatch between orchestrator's flat dict and recorder's nested-read | `agentic_chaos/recorder.py:1272-1273` + `_first_attributed_index` + 🎯 marker placement | Recorder reads flat keys directly | `test_recorder_first_attributed_hop_header.py` |
| ✅ | Citation detector missed `falsification_probes` and layer-status `evidence` bullets | `agentic_ops_v7/orchestrator.py:_collect_na_text_fields` | Added both fields to collected text | `test_rag_observability.py::test_citation_detection_finds_lesson_id_in_falsification_probe` |
| ✅ | 200K per-episode token cap on `mixed` runs — wrong granularity (whole-run, not Synthesis-call) and wrong threshold (sized to no-fanout figure) | `agentic_ops_v7/orchestrator.py:2597-2628` (removed) | Cap removed entirely; ADR post-mortem written | n/a — removed code |
| ✅ | **Bug A** — app-layer Synthesis path wrote `state["diagnosis_structured"]` only, not `state["diagnosis_report"]`. Result: every v7 app-layer episode had `challenge_result.diagnosis_report = null` in its JSON, corrupting the v7 portion of the indexed RAG corpus from May-10 onward | `agentic_ops_v7/orchestrator.py:2770-2785` | 1-line addition matching localized branch at line 792 | `test_diagnosis_report_state_writes.py` (3 structural pins; mutation-verified) |
| ✅ | **Bug B** — parser only read `primary_suspect_nf` from structured `diagnosis_report`. v6 episodes (no structured output) and old-v7 episodes (where Bug A left it null) showed `?` in the "Primary suspect" column. Corpus population rate jumped 0% → 75% for v6 and partial → 81% for v7 after fix | `agentic_ops_common/rag/parser.py:42-119, 360-393` | New `_extract_primary_suspect_from_diagnosis_text` helper with two fallback strategies (affected_components Root Cause entry, v7 inline `(primary_suspect_nf: \`<nf>\`)` suffix); filtered against `_KNOWN_NFS` allowlist | `test_parser.py` (8 new tests covering v6/old-v7/inconclusive/helper paths) |

---

## Workflow gaps that produced these bugs

This bug-pattern is the *consistent shape* of bugs in this codebase right now, not coincidence. Six distinct issues across the RAG + observability surface, all latent for weeks, all caught by inspection rather than testing.

Three durable workflow rules committed to (going forward):

### Rule 1 — End-to-end render after any shared-schema change

Unit tests pass on data shapes I author. They miss shape mismatches with *consumers* I don't author. Specifically: the `?[?]` header bug, the `?` primary-suspect column, and the missing L04 citation were all *visible on inspection of any real episode markdown*. They were invisible only to unit tests of the producer side.

**Rule:** after any change to a state key, Pydantic field, or serialization shape touched by RAG / recorder / observability, run a live scenario and read the rendered markdown end-to-end before declaring done. Five-second eyeball, not "tests pass."

### Rule 2 — Walk all consumers of every state-key write

This is the [`CLAUDE.md`](../CLAUDE.md) rule about propagating changes fully. I keep falsifying it in practice.

The `diagnosis_report` bug: I copied the localized path's two-line write (`state["diagnosis_structured"] = ...; state["diagnosis_report"] = ...`) into the compound path. I never asked "why does the localized path write two keys with the same value? What downstream reads each one?" If I had, I'd have grep'd for `state["diagnosis_report"]` consumers, hit the parser and recorder, and noticed the app-layer path was the only one not writing it.

**Rule:** for any state-key write, grep all readers before declaring done — not just the producer side. State explicitly which consumers were verified and which were left to integration testing.

### Rule 3 — State coverage limits explicitly

The RAG parser's docstring literally says "v7 has structured; v6 only has diagnosis_text" — I knew v6 wouldn't get primary_suspect_nf populated. I didn't surface this as a known gap in a PR/commit/summary. Result: the user discovered the consequence (every v6 RAG hit shows `?`) by manual inspection six weeks later.

**Rule:** when shipping anything with known coverage limits, the limits go in the PR summary / commit message / Slack-style update — same prominence as the feature. "RAG parser handles v7 structured output; v6 cases will show `?` in primary-suspect column until fallback lands" — one sentence, costs nothing, surfaces the gap.

---

## Decision point — choose path

### Path A — Fix and ship

1. Land Bug A (1-line orchestrator add)
2. Land Bug B (parser fallbacks + tests)
3. Rebuild RAG index
4. Re-run a representative scenario; confirm the "Primary suspect" column populates across all hits
5. Implement the `na_evidence_grounding` ADR

Estimated work: ~2-3 hours. Reduces RAG noise + closes the ghost-hypothesis failure mode.

### Path B — Pause and audit

Run through every shared schema / state key / serialization shape touched in the past 2 weeks (path-walk serialization, RAG parser, citation detector, recorder rendering, classifier serialization, compound-verdict additions). Produce a complete list of consumer mismatches and silent gaps before any more code changes.

Estimated work: ~2 hours of just reading + grep, then triage what's worth fixing now vs. what can wait. Breaks the pattern instead of working around it.

**Recommendation when revisiting:** Path B first. Path A first gets value faster but it keeps the pattern alive — the next session will find the next hidden bug. Path B is the higher-confidence move.

---

## Pointers

- Triggering run (Data Plane Degradation): [`agentic_ops_v7/docs/agent_logs/run_20260514_222937_data_plane_degradation.md`](../agentic_ops_v7/docs/agent_logs/run_20260514_222937_data_plane_degradation.md)
- ADR for the evidence-grounding fix: [`docs/ADR/na_evidence_grounding.md`](ADR/na_evidence_grounding.md)
- ADR for the multi-fault orchestration (now landed): [`docs/ADR/multi_fault_orchestration.md`](ADR/multi_fault_orchestration.md)
- ADR for the original RAG retrieval (referenced): [`docs/ADR/rag_episode_retrieval_and_lesson_injection.md`](ADR/rag_episode_retrieval_and_lesson_injection.md)
- The pattern of bugs documented above: this file's §Already-fixed bugs table is the audit trail; future sessions should consult it before assuming the surface is healthy.
