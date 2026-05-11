# ADR: Retrieval-Augmented Generation for the NetworkAnalyst — Episode Cases + Operational Lessons

**Date:** 2026-05-11
**Status:** Proposed (R1-R5 shipped; live-batch validation pending)
**Related:**
- [`anomaly_detection_layer.md`](anomaly_detection_layer.md), [`model_feature_state_revision_B.md`](model_feature_state_revision_B.md) — the screener whose flag output drives both the retrieval key and the over-flagging failure mode (B4) that this ADR mitigates at the LLM-reasoning layer.
- [`path_anchored_probe_planning_for_transport_layer_faults.md`](path_anchored_probe_planning_for_transport_layer_faults.md) — defines the v7 orchestration pipeline this ADR plugs into (Phase 2.5 / 2.5b between Correlation and NetworkAnalyst).
- [`structural_guardrails_for_llm_pipeline.md`](structural_guardrails_for_llm_pipeline.md) — general principle that load-bearing pipeline behavior must be enforced structurally, not by soft prompt rules. The lesson corpus is the *soft* counterpart that complements the structural guardrails for failure modes that cannot be expressed as a mechanical post-emit check.
- [`evidence_citation_enforcement.md`](evidence_citation_enforcement.md) — every retrieved case carries a `source_episode_path`; cited cases are auditable. Same provenance discipline extends to lesson citations via `sources:` fields.
- [`internal_taxonomy_must_not_leak_to_llm.md`](internal_taxonomy_must_not_leak_to_llm.md) — the lessons carry hand-authored guidance for the NA, not ADR labels or internal phase names.
- Driving failure batches:
  - [`../../agentic_ops_v7/docs/agent_logs/run_20260510_121231_p_cscf_latency.md`](../../agentic_ops_v7/docs/agent_logs/run_20260510_121231_p_cscf_latency.md) — Synthesis hallucination (B2) + NA direction-inversion (B3) on a single run.
  - [`../../agentic_ops_v7/docs/agent_logs/run_20260510_185152_p_cscf_packet_loss.md`](../../agentic_ops_v7/docs/agent_logs/run_20260510_185152_p_cscf_packet_loss.md) — 100% by hallucination at 709K tokens; the bottom-of-batch costs that motivate evidence-based NA augmentation.
- Driving work-plan: [`../work-plan-may-11.md`](../work-plan-may-11.md), specifically the "Fix (RAG)" section listing R1-R7.

---

## Decision

We augment the v7 NetworkAnalyst with two complementary information channels that draw on the existing chaos-run history and curated operator knowledge:

1. **Episode case retrieval (R1-R4).** Past chaos episodes are parsed into structured `RetrievedCase` units and indexed by anomaly-screener signature. At runtime, before Phase 3 NA, the orchestrator retrieves the top-K most-similar prior cases and injects them into the NA prompt as a `### Prior similar episodes` section. The NA reads ground-truth and prior-diagnosis evidence about flag patterns like the one in front of it. **Retrieval-based; per-investigation.**

2. **Operational lesson injection (R5).** A curated YAML corpus of 15 hand-authored rules ("UPF in/out asymmetry is not loss", "rtpengine.errors_per_second is blind to qdisc drops", etc.) is rendered into a `### Operational lessons` block and concatenated into every NA prompt. The NA treats these as hard rules outranking its priors. **Always-inject; per-process (cached).**

Both injections are **best-effort, graceful-degrading, and version-agnostic.** Missing index → cases section empty. Missing YAML → lessons section empty. The NA prompt's substitution always resolves; the prompt's own guidance tells the NA how to handle each section's absence.

All RAG infrastructure lives under **`agentic_ops_common/rag/`** — not under `agentic_ops_v7/` — so future agent generations (v8+) inherit it without re-implementing.

Concretely, five coordinated changes shipped as R1-R5:

| Step | What | Where |
|---|---|---|
| **R1** | `RetrievedCase` / `FlagSummary` Pydantic schemas + episode parser (`parse_episode`, `parse_corpus`) handling v5/v6/v7 JSON + markdown fallback | `agentic_ops_common/rag/{schema.py, parser.py}` |
| **R2** | TF-IDF `Embedder` protocol + `CaseIndex` (build/save/load/search) + `rag_indexer/` top-level invokable module (`python -m rag_indexer`) | `agentic_ops_common/rag/{embedder.py, index.py}`, `rag_indexer/{__init__.py, __main__.py}` |
| **R3** | `EpisodeRetriever` runtime API with `try_from_path` graceful loader + `retrieve_for_flags` multi-shape ingestion + `render_hits_for_prompt` provenance-citing markdown renderer + module-level cache | `agentic_ops_common/rag/retriever.py` |
| **R4** | `{prior_similar_episodes}` placeholder + `_phase25_rag_inject_prior_episodes` orchestrator helper + `RAG_INDEX_DIR` / `RAG_MIN_SIMILARITY` env-var config | `agentic_ops_v7/orchestrator.py`, `agentic_ops_v7/prompts/network_analyst.md` |
| **R5** | `Lesson` schema + 15-lesson `lessons.yaml` corpus + `_phase25_inject_operational_lessons` orchestrator helper + `LESSONS_YAML_PATH` env var + `{operational_lessons}` NA-prompt placeholder | `agentic_ops_common/rag/{lessons.py, lessons.yaml}`, `agentic_ops_v7/orchestrator.py`, `agentic_ops_v7/prompts/network_analyst.md` |

The two channels are deliberately distinct: cases are *empirical evidence* (this is what we saw before with similar flags), lessons are *prescriptive rules* (here is how to read this kind of signal). The NA prompt has separate guidance for each.

---

## Context

### What problem this solves

By the 2026-05-10 chaos batch the v7 pipeline was bimodal:

- **Walker-localized scenarios** (data_plane_degradation, call_quality_degradation, upf_bandwidth_cap) scored 100% at 8-13K tokens — the deterministic path-walk pipeline working as designed.
- **App-layer-fallback scenarios** scored 5% to 100% with high variance and 160-700K tokens per run.

Within the app-layer-fallback group, the dominant failure modes weren't reasoning errors per se — they were **evidence-pattern recall failures**:

- **B3 (NetworkAnalyst direction-inversion).** Across multiple runs the NA wrote "extreme spike in UPF's ingress traffic rate" while the screener clearly emitted `direction=drop, current=0.06, learned_normal=1.45`. The error wasn't logic; it was *reading the screener literally*.
- **B4 (UPF GTP over-flagging).** When the screener emits two UPF GTP transport-bucket flags in a registration-only state, the NA over-implicates UPF — even though the same flag pattern in prior runs has always meant something else (signaling fault, application-layer crash, etc.).
- The "wrong-flow resolver" failures (Fix (1) in the work plan) get the walker to walk the wrong path; the NA then has to recover the diagnosis at the application layer with degraded evidence.

These are not problems Gemini-2.5-Pro lacks the capacity to solve — they are problems where the NA, looking at a single anomaly report in isolation, makes a plausible-but-wrong inference that *the very same evidence pattern, when seen across 100+ prior runs in the corpus, would have warned against*. Retrieval-augmented generation is the right shape: hand the NA the empirical history every time.

Concurrently, certain hard-won operator knowledge has accumulated in stack rules, KB notes, ADR sections, and post-mortems that the NA prompt does not currently surface in a form the LLM can rely on. The lesson corpus formalizes that knowledge as durable, citation-keyed rules.

### What's already in place

The work to make RAG possible was already done at the data-collection layer:

- **A non-trivial corpus exists.** 182 episode files across v5/v6/v7 (108+19+55), 4.1M of markdown + 9.7M of JSON. Of those, 97 score ≥ 80% and are corpus-eligible as positive examples.
- **The episode JSON has the structured fields RAG needs.** `challenge_result.{anomaly_report, symptom_classification, path_walk_report, diagnosis_report, score}` plus the top-level `rca_label` (ground truth) and `scenario`. R1 parses these cleanly for v6 and v7; v5 markdown fallback handles the older format.
- **`fault_layer` labels exist on every metric** (per [`model_feature_state_revision_B.md`](model_feature_state_revision_B.md) → KB additions), so retrieval keys carry semantically meaningful signatures.

The missing piece was the indexer + retriever + injection glue — which is what R1-R5 ship.

### Why not fine-tuning

Considered and rejected as the primary path:

- **Corpus is too small.** 182 episodes ≪ the ≥1000-10000 high-quality examples Vertex AI's Gemini supervised tuning needs to meaningfully move a frontier model.
- **Iteration speed.** Adding a new episode → indexed in minutes (RAG) vs. tuning cycle of weeks.
- **Failure shape mismatch.** Fine-tuning is good at teaching style/format/terminology. The failure modes here are evidence-pattern recall — exactly what RAG is shaped for.

Fine-tuning remains a deferred option for narrow, well-scoped corrections after RAG validation. See "Open work" below.

---

## Design

### Architecture

```
Phase 0    AnomalyScreener
Phase 0.5  SymptomClassifier
Phase 0.6  PathWalk (conditional)
Phase 1    Events
Phase 2    Correlation
Phase 2.5  RAGRetriever          ─ retrieve top-K prior cases (R3+R4)
Phase 2.5b OperationalLessons    ─ render lesson corpus (R5)
Phase 3    NetworkAnalyst (LLM)
              prompt substitutes {prior_similar_episodes} + {operational_lessons}
Phase 4..7   ... unchanged
```

Phase 2.5 / 2.5b are **deterministic Python steps** — no LLM, no tool calls, no API. The cost is parsing/embedding + a few hundred KB of disk I/O at first call. Subsequent investigations in the same process hit the cached retriever / cached rendered-lessons block.

### Two corpora, one orchestration

| Aspect | Corpus A — Episode cases | Corpus B — Operational lessons |
|---|---|---|
| **Source** | Parsed `run_*.{json,md}` files from `agentic_ops_v{5,6,7}/docs/agent_logs/` | Hand-authored `lessons.yaml` |
| **Schema** | `RetrievedCase` (case_id, source_episode_path, scenario, ground_truth_*, anomaly_top_flags, diagnosis_*, score_pct, …) | `Lesson` (id, title, rule, applies_when, rationale, sources) |
| **Eligibility** | `score_pct ≥ 80` (R2 filter). Wrong-answer episodes are excluded as positive examples; below-threshold cases need hand-distilled analysis (R5-extension territory) before they enter. | All hand-authored entries are trusted. |
| **Selection** | Top-K cosine similarity against the live screener's flag signature, filtered by `min_similarity` (default 0.40). | Always-inject all. Tiny corpus (≤30); injection budget < 4K tokens. |
| **Provenance** | `source_episode_path` on every case; cited by `case_id` in NA hypotheses. | `sources:` list per lesson; cited by `id` (`L01`, …) in NA hypotheses. |
| **Trustworthiness** | Empirical (what we observed). The NA prompt instructs it to read the case's `Ground truth` and `Agent diagnosis` together — a mismatch teaches what NOT to commit to. | Prescriptive (what the operator knows). The NA prompt treats lessons as hard rules. |
| **Update cycle** | Rebuild index after each chaos batch. | Manually edit the YAML when new patterns are discovered. |
| **Token budget at injection** | ~250 tokens/case × 5 = ~1250 tokens | ~14.4K chars / ~3500 tokens (15 lessons) |

The two corpora have different shapes precisely because they're different kinds of evidence. Forcing both through the same retrieval mechanism would have meant one of them degrading: either cases would have to be summarized like lessons (losing per-episode specificity), or lessons would be retrieval-gated (risking miss when the rule applies but the trigger language isn't in the live flag signature).

### Retrieval mechanism — TF-IDF over numpy cosine

The work plan named FAISS + `sentence-transformers/all-mpnet-base-v2` as the default stack. We **shipped TF-IDF + scikit-learn instead**. Three reasons:

1. **Corpus shape is structured, not prose.** Retrieval keys are flag-signature lists (`derived.rtpengine_loss_ratio:spike:MEDIUM` × N + scenario suffix + classifier suffix). TF-IDF treats each signature substring as a token and IDF-weights "appears in everything" tokens down — exactly the right behavior for separating distinctive flag combinations from boilerplate UPF-GTP-everywhere noise. Semantic embedding models add little here.
2. **Corpus size is two orders of magnitude below the FAISS break-even point.** 97 cases × 309-dim TF-IDF vectors fit in 120KB of RAM; cosine similarity via `numpy.dot` runs in <50ms. FAISS's nearest-neighbour speedup is irrelevant.
3. **Zero new dependencies.** `scikit-learn` is already installed; adding `torch` (`sentence-transformers` transitively requires it) would add ~1GB to the venv for no practical benefit.

The `Embedder` Protocol leaves room to swap in a richer backend without touching the index or retriever:

```python
class Embedder(Protocol):
    name: str
    @property
    def embed_dim(self) -> int: ...
    def fit(self, corpus: Sequence[str]) -> None: ...
    def encode(self, texts: Sequence[str]) -> np.ndarray: ...
```

When the corpus grows past ~5K cases, or when query-side semantic richness becomes load-bearing (e.g. when free-text queries from another agent need to retrieve cases), the protocol accepts a `GeminiEmbedder` or `SentenceTransformerEmbedder` drop-in.

### Why always-inject for lessons (and not retrieve)

The work plan implied lessons would be retrieval-gated too. We chose always-inject for these reasons:

- **Corpus is tiny and durable.** 15 lessons × ~250 tokens = ~3500 tokens — well within the NA prompt's budget. Stability matters more than minimality at this size.
- **Trigger language doesn't match flag signatures cleanly.** A lesson like "Upstream silent ≠ downstream noisy" applies whenever the NA is forming a hypothesis from a signaling-chain rate drop — but its trigger isn't a single flag signature. Retrieval-by-flag-similarity would miss the case where the lesson applies but the live flags don't textually overlap with the lesson's prose.
- **Reliability matters more than per-prompt parsimony.** A lesson that fires only when retrieval surfaces it is a lesson that the NA cannot rely on. Always-inject removes the "did the right lesson get retrieved?" failure mode entirely.
- **Trivial to escalate to retrieval later.** When the corpus crosses ~30 lessons, gating by `applies_when`-based retrieval becomes worthwhile — the lesson schema already has the field; only the orchestrator helper changes.

### Provenance discipline (load-bearing)

Both injections cite their sources in machine-readable form:

- Every `RetrievedCase.render_for_prompt()` block includes a `source: <absolute episode path>` line. The NA prompt instructs the LLM to cite cases by `case_id` (e.g. `v7/ep_20260510_185748_call_quality_degradation`) when their evidence shapes a hypothesis. The EvidenceValidator can resolve the citation, read the source episode, and audit.
- Every `Lesson` carries a `sources:` list (ADR paths, stack-rule YAML keys, run logs). The NA prompt instructs the LLM to cite lessons by `id` (e.g. `L01`, `L14`). The auditor can resolve the id, find the lesson's `sources:`, and trace the rule back to its origin.

This is the [`evidence_citation_enforcement.md`](evidence_citation_enforcement.md) discipline extended to retrieved knowledge. A diagnosis that cites a case or lesson is grounded in something an auditor can find.

### Graceful degradation contract

Every path through Phase 2.5 / 2.5b has a defined no-op behavior:

| Condition | State outcome | PhaseTrace summary |
|---|---|---|
| `RAG_INDEX_DIR` unset and `<repo>/rag_index/` missing | `prior_similar_episodes = ""` | `rag_disabled` |
| `RAG_INDEX_DIR=off` (or `none` / `disabled`) | `prior_similar_episodes = ""` | `rag_disabled` |
| Index path set but missing on disk | `prior_similar_episodes = ""` | `index_not_loaded:<path>` |
| State has no `anomaly_flags` | `prior_similar_episodes = ""` | `no_flags (corpus_size=N)` |
| Retrieve raises | `prior_similar_episodes = ""` | `retrieve_raised:<exc>` |
| No hits above `RAG_MIN_SIMILARITY` (default 0.40) | `prior_similar_episodes = ""` | `no_hits (k=5, min_sim=0.40, corpus_size=N)` |
| Hits retrieved | `prior_similar_episodes` populated | `hits=N, top_sim=X.XX, top_case=v7/...` |
| `LESSONS_YAML_PATH=off` (or sentinel) | `operational_lessons = ""` | `lessons_disabled` |
| Lessons YAML missing or malformed | `operational_lessons = ""` | `yaml_unreadable:<path>` |
| Lessons loaded | `operational_lessons` populated; cached | `lessons=N, chars=M` (first call) or `injected_from_cache` (subsequent) |

The NA prompt's substitution always resolves; the prompt's own guidance covers the empty case ("If the section is empty, ignore it and reason from the inputs above"). The orchestrator never crashes because RAG isn't configured.

### Module location — `agentic_ops_common/rag/`

All RAG infrastructure lives under `agentic_ops_common/` (the shared-infrastructure root), **not** under `agentic_ops_v7/`. Rationale mirrors the v7 self-containment rule's converse: shared infrastructure that future agent generations will want goes under `agentic_ops_common`. v8 (and beyond) get RAG for free — only the orchestrator-side injection helpers are version-specific. The episode parser, schema, indexer, retriever, embedder, and lesson loader are version-agnostic.

The only v7-specific code is:

- `agentic_ops_v7/orchestrator.py::_phase25_rag_inject_prior_episodes` and `_phase25_inject_operational_lessons` (Phase 2.5 / 2.5b helpers).
- `agentic_ops_v7/prompts/network_analyst.md` (NA prompt placeholders + guidance).

A v8 orchestrator would re-implement the helpers (5 LOC each) and add the placeholders to its NA prompt. The corpora and the schema stay shared.

### Configuration

Two env vars, both opt-out by default:

| Variable | Default | Effect |
|---|---|---|
| `RAG_INDEX_DIR` | `<repo_root>/rag_index/` if exists, else off | Override index path or disable via sentinel (`off`/`none`/`disabled`) |
| `RAG_MIN_SIMILARITY` | `0.40` (empirical — top similarities top out at 0.45-0.55 on the 2026-05-10 corpus) | Tighten (`0.6`) for stricter retrieval or loosen (`0.2`) for more inclusive context |
| `LESSONS_YAML_PATH` | `agentic_ops_common/rag/lessons.yaml` | Override path or disable via sentinel |

For an A/B comparison run against a no-RAG baseline:

```bash
export RAG_INDEX_DIR=off
export LESSONS_YAML_PATH=off
# Run the chaos batch; both injections will be silently disabled.
```

The PhaseTrace records `rag_disabled` and `lessons_disabled` so the episode log shows the configuration honestly.

---

## What it does NOT do

- **No fine-tuning.** As discussed in Context. Deferred.
- **No retrieval for Synthesis (yet).** R7 in the work plan extends to Phase 7 if R6 measurement shows lift. The retriever API is already there; only the wiring is deferred.
- **No automatic ingestion of failed episodes.** The R2 corpus filter (`score ≥ 80`) is strict — sub-80% cases are excluded because, without explicit "this is what went wrong and why" annotation, they teach the wrong pattern. A `retrospective_agent` to auto-generate such annotations is a deferred option (`R5.X` per the work plan).
- **No prompt-side memory of which cases were already cited.** Each investigation retrieves independently. If the NA cites the same case across two investigations in the same session, the case appears twice. This is acceptable because each investigation is logically independent.
- **No re-ranking based on temporal recency.** Older cases score the same as recent ones. If a system invariant changes (e.g., a KB metric is renamed), old cases referencing the old name will produce stale advice. The expectation is that the index is rebuilt regularly enough that stale cases drop out of the top-K naturally.
- **No retrieval-augmented Investigator or IG.** RAG augments NA only. IG/Investigator are mechanically scoped (probe-tool, hypothesis-bound) and benefit less from prior-case context. Could be reconsidered if measurement shows surprise.

---

## Acceptance evidence

R1-R5 are accepted by:

- **286 tests passing** across `agentic_ops_v7/tests/` + `agentic_ops_common/tests/rag/` (3 xfailed in resolver — unrelated, documented).
- **Parser skip rate 0%** on the 182-episode corpus.
- **Index built cleanly** over the real corpus: 97 cases pass the score-filter, 309-dim TF-IDF vocab, 0% skip during embedding.
- **Smoke retrieval result.** A query built from a live rtpengine-loss-style flag set returns Call Quality Degradation episodes as the top-3 hits with similarity 0.53-0.63 — the right semantic neighborhood.
- **Lesson corpus** loads cleanly (15 lessons, all with unique ids, all with non-empty rule + title, rendered block under the 20K-char budget).
- **NA prompt parity test** updated to list the prompt changes as intentional R4/R5 divergences from v6.
- **Graceful degradation paths** exercised by tests: missing index, missing YAML, sentinel env var, empty corpus, malformed YAML, sentinel min-similarity floor, no flags in state.

What's *not yet* accepted is the **operational lift**. R6 (the live chaos batch run with all injections enabled) is the validation step. Expected effects:

- Direct: the `p_cscf_packet_loss` hallucination (B2 — already addressed by the Synthesis guardrail) is paired with the NA's improved priors via L11/L12 and the prior `Call Quality Degradation` case retrieval.
- Direct: L01 (read direction literally) targets B3 head-on.
- Direct: L03 (UPF over-flagging) targets B4 head-on.
- Indirect: prior-case retrieval shifts the NA's first-attempt hypothesis priors toward the historical answer for similar flag patterns.

The transformational batch is the one *after* B4 (screener over-flagging) is also addressed at the source; RAG amplifies what's possible at the LLM-reasoning layer but cannot manufacture evidence the screener didn't surface.

---

## Open work / deferred items

- **R6 — live batch run.** Build the index over the latest corpus, run the 14-scenario chaos batch with RAG enabled, compare per-scenario scores and token counts against the 2026-05-10 baseline. Decide R7 from results.
- **R7 — extend retrieval to Synthesis.** Phase 7 Synthesis could also benefit from prior-verdict-tree context. The retriever API already accepts arbitrary query text; the orchestrator wiring is similar in shape to R4 but at a different phase. Conditional on R6 showing NA-side lift.
- **Retrospective-agent for failed episodes.** A one-shot LLM pass over each failed (score < 80%) episode that generates a "this is what went wrong and what the right answer was" annotation. Adds the failed episodes to the corpus as corrective lessons. ~$0.50-2 in API costs for all 130 sub-80% v6+v7 episodes via Gemini Pro. Hand-review before they enter.
- **Lesson retrieval / triggers.** When the lesson corpus crosses ~30 entries, gate injection by an `applies_when`-based retrieval pass. The schema already has the field; only the orchestrator helper changes. The current always-inject approach is fine until then.
- **Embedder upgrade path.** When/if the case corpus grows past ~5K units, swap the `TfidfEmbedder` for `GeminiEmbedder` (semantic, via `google.genai`'s `text-embedding-004`). The `Embedder` Protocol absorbs the change without touching index callers.
- **Cross-version case sharing.** v8 will inherit the same RAG infrastructure. The case corpus is version-tagged but otherwise version-neutral; a v7 case is still useful context for a v8 NA. The lesson corpus is unambiguously shared.
- **Index lifecycle automation.** Right now the index is built manually via `python -m rag_indexer`. A nightly batch step (or a post-chaos-run hook) that rebuilds the index would close the loop so the latest episodes are always retrievable.

---

## Files

### New (R1-R5)

```
agentic_ops_common/rag/__init__.py              # package init + re-exports
agentic_ops_common/rag/schema.py                # FlagSummary, RetrievedCase
agentic_ops_common/rag/parser.py                # parse_episode, parse_corpus, CLI
agentic_ops_common/rag/embedder.py              # Embedder Protocol, TfidfEmbedder
agentic_ops_common/rag/index.py                 # CaseIndex (build/save/load/search), IndexManifest, SearchHit
agentic_ops_common/rag/retriever.py             # EpisodeRetriever, get_default_retriever, cache helpers
agentic_ops_common/rag/lessons.py               # Lesson schema, load_lessons, render_lessons_for_prompt
agentic_ops_common/rag/lessons.yaml             # 15 hand-authored operational rules

rag_indexer/__init__.py                         # top-level invokable module
rag_indexer/__main__.py                         # `python -m rag_indexer` entry point

agentic_ops_common/tests/rag/test_parser.py     # R1 tests (17)
agentic_ops_common/tests/rag/test_embedder.py   # R2 tests — embedder (6)
agentic_ops_common/tests/rag/test_index.py      # R2 tests — index (11)
agentic_ops_common/tests/rag/test_retriever.py  # R3 tests (22)
agentic_ops_common/tests/rag/test_lessons.py    # R5 tests — schema/loader (16)

agentic_ops_v7/tests/test_rag_injection.py      # R4 orchestrator wiring (17)
agentic_ops_v7/tests/test_lessons_injection.py  # R5 orchestrator wiring (16)
```

### Modified

```
agentic_ops_v7/orchestrator.py                  # Phase 2.5 + 2.5b helpers + state init + env-var config
agentic_ops_v7/prompts/network_analyst.md       # {prior_similar_episodes} + {operational_lessons} placeholders + guidance
agentic_ops_v7/tests/test_application_layer_parity_with_v6.py  # NA prompt added to _INTENTIONALLY_DIVERGENT + pinning test
```

### Test footprint

```
286 passed, 3 xfailed   (full v7 + RAG suite)
105 passed              (all RAG tests in agentic_ops_common)
```

The 3 xfailed remain the documented resolver-side cases that need a separate fix (Fix (4) — screener bucket (0,1) over-flagging) to unblock. They are unrelated to this ADR.

---

## How to run with RAG

```bash
# Build the index (one-shot; rebuild after each chaos batch).
# Defaults: sources = agentic_ops_v{5,6,7}/docs/agent_logs,
#           output = <repo>/rag_index/, score_threshold = 80.
uv run python -m rag_indexer

# Run chaos as usual — RAG auto-discovers rag_index/ at repo root.
# Lessons load from the shipped lessons.yaml by default.

# To disable for an A/B baseline:
export RAG_INDEX_DIR=off
export LESSONS_YAML_PATH=off
```

The episode log's per-phase breakdown will show `RAGRetriever` and `OperationalLessons` rows recording exactly what was injected on each run.
