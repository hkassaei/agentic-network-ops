# ADR: RAG infrastructure-NF fingerprint enrichment (`infra:<nf>:<status>` tokens)

**Date:** 2026-05-29
**Status:** Accepted (ready for implementation)
**Related:**
- The RAG implementation this modifies:
    - `agentic_ops_common/rag/schema.py:212–234` — `RetrievedCase.retrieval_key_text()` (per-case embedding text).
    - `agentic_ops_common/rag/retriever.py:258–285` — `_build_query_text_from_flags()` (runtime query construction).
    - `agentic_ops_common/rag/parser.py` — episode → `RetrievedCase` parser (the side that needs to learn to extract `infra:` facts from historical episodes).
    - `agentic_ops_common/rag/embedder.py` — TF-IDF embedder (unchanged; the fix is what we feed it, not how it embeds).
    - `agentic_ops_common/rag/index.py:263–317` — `CaseIndex.search()` (pure top-k cosine, no filter / no re-ranker; unchanged).
- The Phase 2.5 hook this extends:
    - `agentic_ops_v7/orchestrator.py:1385+` — `_phase25_rag_inject_prior_episodes`.
    - `agentic_ops_common/tools/container_status.py:7` — `get_network_status()`, the deterministic source of truth this ADR threads into the query.
- The episodes that motivate this:
    - `agentic_ops_v7/docs/agent_logs/run_20260530_011636_dns_failure.md` — NA correctly diagnosed DNS, but RAG retrieved S-CSCF Crash at **83%** as top hit; the actual DNS Failure precedent ranked **#4 at 69%**; **no verbatim citations** in NA output.
    - `agentic_ops_v7/docs/agent_logs/run_20260528_015404_mongodb_gone.md` — counter-example where RAG did help: top hit was a v6 mongodb_gone at **94%** because two near-identical prior cases exist in the corpus; lessons L10 + L03 were both cited.
- Sibling determinism-first arc this slots into: [`ig_probe_grounding_metric_inventory_and_liveness.md`](ig_probe_grounding_metric_inventory_and_liveness.md), [`blast_radius_downstream_impact_phase8.md`](blast_radius_downstream_impact_phase8.md). Same principle: **put the discriminating fact into the input the model sees — don't rely on the model to discover it via expensive exploration.**

---

## Decision

Add a new line-type, **`infra:<nf>:<status>`**, to the RAG case fingerprint (both the indexed corpus and the runtime query). Populate it from `get_network_status()` output — historical cases get back-filled from each episode's JSON trace; the live query gets a one-shot `get_network_status` call inserted at the top of Phase 2.5 whose result is threaded into both the RAG query *and* into `state` so the NetworkAnalyst can reuse it.

Effect: the DNS Failure query becomes `infra:dns:exited` (plus the existing flag signatures); the only cases in the corpus that contain `infra:dns:exited` are prior DNS failures. TF-IDF token-mass dilution stops mattering for the discriminating token because no S-CSCF Crash case contains it.

This is a structural fingerprint change, not a model change. The embedder stays TF-IDF, the retriever stays pure-cosine, the index format gains exactly one new line-type with the same `<key>:<value>:<value>` shape as the existing flag signatures.

---

## Context

### What already exists

The RAG fingerprint is dirt-simple. `RetrievedCase.retrieval_key_text()` builds:

```
<flag signature 1>      # e.g. core.upf.gtp_indatapktn3upf_per_ue:drop:LOW
<flag signature 2>
...
scenario: <scenario_name>
classifier: <classifier_label or 'unknown'>
```

`_build_query_text_from_flags()` builds the runtime query in **exactly the same shape** from the live screener's flags plus optional `scenario_hint` / `classifier_label`. Retrieval is pure top-k cosine with a `min_similarity` floor — no classifier filter, no NF filter, no re-ranker.

This is fine when two cases of the same fault type have similar screener fingerprints (mongo↔mongo: 94% top hit; the index does what we want). It breaks when the fault is an *infrastructure cascade* whose visible screener signature is dominated by downstream NF symptoms.

### The gap, made concrete by the DNS Failure run

The DNS run's flag set was:

| Flag | Signature |
|---|---|
| UPF GTP-U uplink drop | `core.upf.gtp_indatapktn3upf_per_ue:drop:LOW` |
| UPF GTP-U downlink drop | `core.upf.gtp_outdatapktn3upf_per_ue:drop:LOW` |
| SMF bearers shift | `core.smf.bearers_per_ue:shift:MEDIUM` |
| P-CSCF INVITE spike | `ims.pcscf.rcv_requests_invite_per_ue:spike:MEDIUM` |

These four signatures plus `scenario: dns_failure` and `classifier: mixed` formed the query. The TF-IDF top-5 returned:

| Rank | Sim | Case | Why it matched |
|---:|---:|---|---|
| 1 | 83% | `v6/ep_20260430_014002_s_cscf_crash` | S-CSCF crash cascade looks like IMS+core noise — overlapping signatures |
| 2 | 76% | `v6/ep_20260429_160332_p_cscf_latency` | IMS signaling errors with downstream effects — similar shape |
| 3 | 73% | `v7/ep_20260510_200052_amf_restart` | Core control-plane cascade — similar shape |
| 4 | 71% | `v7/ep_20260510_183211_data_plane_degradation` | UPF GTP drops dominate — similar shape |
| 5 | 69% | `v7/ep_20260510_194005_dns_failure` | Same scenario; lost to four near-misses |

The `scenario: dns_failure` suffix is one token competing against four flag-signature tokens; it gets washed out. The `classifier: mixed` suffix matches all five hits and adds no discrimination.

**Crucially: the embedding never sees `dns:exited`.** That fact only ever lived inside the NA's tool-observation history and the NA's `INFRASTRUCTURE evidence` block — both downstream of where RAG runs. The retriever cannot select on a feature it was never given.

The NA still diagnosed correctly (100% score) by exhausting 188K tokens and 7 tool calls discovering `dns:exited` itself. RAG didn't help; it also didn't hurt (no false hypothesis was suggested by the irrelevant top hits — NA's "no verbatim citations" tells us it ignored them). But the optimistic case ("retrieve a near-identical prior, anchor on it, converge in a fraction of the tokens") never fired.

The same shape applies to every infrastructure container that other NFs depend on: **mongo, hss, pcf-via-mongo, dns, smsc, possibly redis/postgres in future deployments.** Their failures express through downstream symptoms; their identity is in container-status, not in the metric-flag fingerprint.

## Design

### The new fingerprint line

A single new line-type, slotted between the flag signatures and the existing suffixes:

```
<flag signature 1>
<flag signature 2>
...
infra:<nf>:<status>            ← NEW; zero or more lines
...
scenario: <scenario_name>
classifier: <classifier_label or 'unknown'>
```

Where `<status>` is one of `exited`, `restarting`, `absent`. (Containers in `running` status do **not** get a line — would dilute and add no discrimination.) `<nf>` is the canonical NF name (mongo, dns, hss, …) — matched against the components.yaml allowlist to reject garbage.

This shape composes with the existing TF-IDF tokenizer cleanly: `infra:dns:exited` becomes its own token, indistinguishable in mechanism from `core.upf.gtp_indatapktn3upf_per_ue:drop:LOW`. No embedder change required.

### Per-case (index-side) extraction

Every chaos episode in the corpus already records its injected faults as structured ground truth. Both v6 and v7 JSON traces have the same shape:

```json
"faults": [{
  "fault_id":          "f_ddb82464",
  "fault_type":        "container_kill",
  "target":            "dns",
  "verified":          true,
  "verification_result":"Expected 'exited', got 'exited'"
}]
```

The parser at `agentic_ops_common/rag/parser.py` already walks every episode's JSON; the extraction is a flat read of `faults[]`, no log parsing, no NA-trace dependency, no regex on prose.

**Extraction rule:**

For each `fault` in `episode["faults"]`, emit `infra:<target>:exited` when **both** conditions hold:
1. `fault_type ∈ {"container_kill", "container_stop"}` — these are the fault types that produce a container down-state observable to `get_network_status`.
2. `verified is True` AND `verification_result` contains `"got 'exited'"` (or equivalent down-state phrasing) — i.e. the harness *observed* the down state at fault time, not just intended it.

All other fault types emit nothing:
- `network_latency` / `network_loss` / `network_partition` / `network_bandwidth` — network impairments; container stays running; the screener fingerprint is already the right signal.
- `container_pause` — running-but-blocked; `get_network_status` returns "running" so the runtime query wouldn't emit `infra:` for the live case anyway. Emitting it at index time would create a phantom match.

**Corpus inventory** (v6+v7, 264 fault entries):

| Fault type | Count | `infra:` line emitted? |
|---|---:|---|
| `container_kill` | 82 | ✅ `infra:<target>:exited` |
| `container_stop` | 11 | ✅ `infra:<target>:exited` (same observable state) |
| `container_pause` | 2 | ❌ none (running-but-blocked) |
| `network_latency` | 73 | ❌ none |
| `network_loss` | 60 | ❌ none |
| `network_partition` | 32 | ❌ none |
| `network_bandwidth` | 4 | ❌ none |

So ~93 of 264 fault entries produce a definitive `infra:` token in the backfill; the other ~171 correctly produce none. Every emitted token traces to a `fault_id` and a `verification_result` line — fully auditable.

Add the extracted statuses to `RetrievedCase` as a new field `infra_status: dict[str, Literal["exited","restarting","absent"]]` (typed; `extra="forbid"` per the affected-components convention). `retrieval_key_text()` emits one `infra:<nf>:<status>` line per entry, sorted for embedding stability. (`restarting` / `absent` are reserved for runtime — at index time, `verification_result` only confirms `exited`.)

### Per-query (runtime) extraction

Insert a tiny pre-step at the top of `_phase25_rag_inject_prior_episodes` in `orchestrator.py`:

```python
# Phase 2.5a — infra-status snapshot for both RAG and NA.
try:
    ns_json = await get_network_status()
    infra_status = parse_network_status(ns_json)    # -> {"dns": "exited", ...}
    state["infra_status"] = infra_status            # available to NA later
except Exception as e:
    log.warning("Phase 2.5a: get_network_status failed (non-fatal): %s", e)
    state["infra_status"] = {}
```

Then thread `infra_status` into `retrieve_for_flags(...)` via a new keyword (`infra_status_hint=`) that `_build_query_text_from_flags()` renders into the same `infra:<nf>:<status>` lines as the index side.

The DNS query becomes:

```
core.upf.gtp_indatapktn3upf_per_ue:drop:LOW
core.upf.gtp_outdatapktn3upf_per_ue:drop:LOW
core.smf.bearers_per_ue:shift:MEDIUM
ims.pcscf.rcv_requests_invite_per_ue:spike:MEDIUM
infra:dns:exited                              ← NEW, decisive
classifier: mixed
```

`infra:dns:exited` is a token that appears in **zero** non-DNS cases in the corpus. Even with TF-IDF's token-mass dilution, exact-match tokens with no competitors will dominate the similarity ranking.

### Why the two sides use different sources (and why that's correct)

| | Source | Confidence | Why this source |
|---|---|---|---|
| **Index time** | `scenario.faults[]` + `verification_result` from the episode JSON | 100% (test-harness ground truth) | We *know* what was injected and that the down-state was observed at fault time. No tool call, no NA-trace dependency. |
| **Runtime** | `get_network_status()` tool call in Phase 2.5 | 100% (direct Docker query) | The chaos scenario is *what we're trying to diagnose* — its identity is not knowable to RAG. The live observation is our only ground truth. |

Same token shape (`infra:<nf>:exited`) on both sides, different sources because the available ground truth differs by epoch. Cleanly separable; trivially testable on each side independently.

### Bonus from sharing the result with NA

`state["infra_status"]` is also injected into the NA prompt (new placeholder `{infra_status_snapshot}`) so the NA sees `dns:exited` *up front* rather than discovering it via 6–7 exploratory tool calls. Estimated savings on the DNS run: a meaningful fraction of the 188K NA tokens (one tool call replaces five). This isn't the primary motivation — the primary motivation is the RAG fix — but it's a no-cost upside from the same data.

### Backfill

The 102 existing cases in `rag_index/` need to be re-parsed once. The parser is already idempotent over `RetrievedCase`, so this is a one-shot rebuild:

```
python -m agentic_ops_common.rag.index --rebuild --source agentic_ops_v7/docs/agent_logs/ agentic_ops_v6/docs/agent_logs/
```

Backfill source is `episode["faults"]` (structured fault metadata, present and uniform across v6 and v7), applying the extraction rule above. No log parsing. No NA-trace dependency. Cases whose JSON lacks a `faults[]` block (early v5 cases) get no `infra:` lines — purely additive, no regression.

### Corpus sweep on rebuild

The rebuild is a full sweep of `agentic_ops_v6/docs/agent_logs/` and `agentic_ops_v7/docs/agent_logs/` — every episode pair on disk that the parser can extract a `RetrievedCase` from (i.e. has a recoverable score) is ingested. No hand-picked allowlist.

**Drift snapshot at ADR draft time:**
- 57 v7 episode pairs on disk; 31 of them post-date the most recent index snapshot (`rag_index.bak.20260520T025030Z/`). The active index reports 102 cases — meaningfully behind disk.
- Of the 57 v7 episodes, **21 will carry `infra:<nf>:exited` tokens** (19 `container_kill` + 2 `container_stop`); the other 36 are network impairments that correctly carry none.
- v6 numbers are stable (no recent additions) but go through the same parser pass to gain `infra:` tokens where applicable.

So this PR does two distinct things in one rebuild: (1) re-ingest the ~31 v7 episodes that accumulated since the last snapshot — a normal corpus-freshness operation that's overdue regardless of this ADR — and (2) emit `infra:<nf>:exited` tokens for every container-down case in the resulting corpus. The fingerprint enrichment is the substantive change; the corpus refresh is incidental but necessary.

## Trade-offs and limitations

- **One extra tool call per episode.** `get_network_status` is cheap (single Docker API call, no LLM, sub-second). The cost is fully amortized by the NA token savings when the NA reuses `state["infra_status"]`. Even without the NA reuse it's negligible relative to a 273K-token episode.
- **TF-IDF stays.** This ADR does not switch embedders. Neural embedders would not have fixed this case either — the failure was an absent feature, not a misread one. A future ADR can revisit the embedder once we exhaust what richer fingerprinting buys us.
- **`infra:` tokens only help when they exist.** For a fault that doesn't involve an exited container (`p_cscf_latency`, `upf_bandwidth_cap`, `pcf_loss`), the `infra_status` snapshot is empty, no `infra:` lines are added, and retrieval reverts to today's flag-signature behavior. This is correct: don't pollute the fingerprint with negatives.
- **Status vocabulary deliberately narrow.** `exited` / `restarting` / `absent` is enough to discriminate the cases that matter. Adding `unhealthy` / `running_but_failing` would require defining what those mean across container types and would re-introduce ambiguity. Out of scope.
- **No re-ranker.** Lever 2 from the discussion (soft re-rank by `classifier_label_match` + `down_container_set` Jaccard overlap) is **not** part of this ADR. Lever 1 is the structural fix; re-ranking is a safety net we can add after observing whether Lever 1 alone suffices. Keeping ADRs small and testable.
- **Backfill atomicity.** Re-building the index is destructive (replaces existing vectors). Plan: rebuild into `rag_index_v2/`, point `RAG_INDEX_DIR` at it, validate, then rename. Same pattern as the prior `rag_index.bak.<timestamp>/` snapshots already in the repo root.
- **Containers vs ontology NFs.** `get_network_status` returns container names; the corpus uses NF names. They mostly coincide (`dns`, `mongo`, `pcscf`, `scscf`, …) but a small normalization map may be needed (e.g. `mongodb` → `mongo`). The components.yaml NF set is the canonical allowlist; anything outside it gets dropped.
- **Doesn't help when the upstream-failed component isn't a container.** External services (an upstream IMS interconnect, a customer network, the public internet) won't show up in `get_network_status` at all. Out of scope; the existing `external_network` walker gap is the better place to address that.

## Implementation outline

1. **`agentic_ops_common/rag/schema.py`** — add `infra_status: dict[str, Literal["exited","restarting","absent"]] = Field(default_factory=dict)` to `RetrievedCase`. Extend `retrieval_key_text()` to emit `infra:<nf>:<status>` lines (sorted) between the flag signatures and the `scenario:` suffix. Round-trip JSON/parquet serialization tests.
2. **`agentic_ops_common/rag/parser.py`** — add `_extract_infra_status_from_faults(episode_json) -> dict[str, str]`. Read `episode["faults"]`; for each entry, emit `{target: "exited"}` when `fault_type ∈ {"container_kill", "container_stop"}` AND `verified is True` AND `verification_result` contains `"got 'exited'"`. Drop targets not in the components.yaml allowlist (defensive). Unit-test against fixtures from the DNS run (`infra:dns:exited`), the mongo run (`infra:mongo:exited`), a v6 container-kill case (`run_20260420_040523_gnb_radio_link_failure` → `infra:nr_gnb:exited`), and a network-impairment case (e.g. `p_cscf_latency` → `{}`).
3. **`agentic_ops_common/rag/retriever.py`** — add `infra_status_hint: dict[str, str] | None = None` to `retrieve_for_flags(...)` and to `_build_query_text_from_flags(...)`. Render to the same `infra:<nf>:<status>` lines as the index side. Empty / None = no lines emitted (no regression on today's behavior).
4. **`agentic_ops_common/rag/embedder.py`** — no changes. TF-IDF tokenizer already handles colon-delimited tokens.
5. **`agentic_ops_v7/orchestrator.py`** — at the top of `_phase25_rag_inject_prior_episodes`, run `get_network_status()` once, parse, write `state["infra_status"]`. Pass to `retrieve_for_flags(..., infra_status_hint=state["infra_status"])`. Add a small `PhaseTrace(agent_name="InfraStatusSnapshot")` so the run report shows what was captured. Non-fatal on tool failure (empty dict, RAG behaves as today).
6. **`agentic_ops_v7/prompts/network_analyst.md`** — add `{infra_status_snapshot}` as a **dedicated section** in the NA prompt (its own heading, e.g. `### Current container status`), rendered as a short NF/status list. When the snapshot is empty (all containers running/healthy), the section renders a single line such as "All network containers are running" — the section header still appears so the NA can rely on it always being present.
7. **`agentic_ops_v7/orchestrator.py`** — initialize `state["infra_status_snapshot"]` to "" at state-init (same discipline as `nf_metric_inventory` / `nf_liveness_probes` defaults).
8. **Index rebuild** — one-shot script invocation (above); re-snapshot the prior index under `rag_index.bak.<timestamp>/` per the existing convention.
9. **Corpus sweep** — the rebuild ingests every parseable episode in `agentic_ops_v6/docs/agent_logs/` and `agentic_ops_v7/docs/agent_logs/` (no hand-picked allowlist). At ADR draft time this pulls in ~31 v7 episodes that post-date the last index snapshot.
10. **Tests** —
    - Parser pin: DNS run yields `{"dns": "exited"}`; mongo run yields `{"mongo": "exited"}`; UPF bandwidth-cap yields `{}`.
    - Embedding pin: a `RetrievedCase` with `infra_status={"dns": "exited"}` emits `infra:dns:exited` in `retrieval_key_text()`, between flags and scenario suffix.
    - Retrieval pin: synthetic corpus containing one DNS case and four IMS-cascade cases — a query with the DNS run's exact flag set + `infra_status_hint={"dns":"exited"}` retrieves the DNS case at rank 1 (regression test for the actual failure this ADR fixes).
    - Backward-compat pin: empty `infra_status_hint=None` reproduces today's query string byte-for-byte (no regression on existing tests).
    - Phase 2.5 pin: `get_network_status` tool failure does not break Phase 2.5; `infra_status` ends up as `{}`; downstream behaves as today.
    - Audit-trail pin: every `infra:` line in a rebuilt case traces back to a `fault_id` in the source episode's `faults[]` array (assert by re-parsing a sample case and checking provenance).

## Validation target

- **Primary:** re-run a synthetic DNS scenario (or replay the existing run from JSON) against the rebuilt index. Top RAG hit should be a prior `dns_failure` case at ≥85% similarity, not an S-CSCF Crash or AMF Restart.
- **Mongo regression:** the mongodb_gone run should *not* lose its existing 94% top hit. The new `infra:mongo:exited` token in both index and query strengthens, not weakens, that match.
- **Negative-control:** a run with no exited containers (e.g. `p_cscf_latency`) should produce a query identical to today's (empty `infra_status_hint`), and retrieve the same top hits at the same similarities. Backward-compat is testable directly.
- **NA token reuse:** instrument the prompt to confirm `{infra_status_snapshot}` is rendered; spot-check that on a re-run of the DNS scenario the NA's tool-call count drops (the discovery work is now upfront).
- **Full test suites green** — `agentic_ops_v7`, `agentic_ops_common`, `agentic_chaos`. The pre-existing `test_list_scenarios_runs` failure (14 vs 11 scenarios) is unrelated.

## Out of scope

- Switching from TF-IDF to a neural embedder.
- Soft re-ranker on top of retrieval (Lever 2).
- Hard filter by `classifier_label`.
- Expanding the `infra:` status vocabulary beyond `exited`/`restarting`/`absent`.
- Extracting NF status from anything other than (a) `episode["faults"]` at index time and (b) `get_network_status()` at runtime — no log scraping, no NA-trace parsing, no markdown regex.
- Surfacing the `infra_status` snapshot to Phase 4 IG or Phase 8 Blast Radius (the NA already covers the diagnostic flow; IG gets its grounding via `nf_liveness_probes`).

## Resolved decisions (from review)

1. **Single emission per `infra:` line.** One `infra:<nf>:<status>` line per affected NF — no N× repetition. Discriminating power comes from corpus rarity (`infra:dns:exited` appears in zero non-DNS cases), not from token mass.
2. **NA-prompt rendering = dedicated section.** `{infra_status_snapshot}` lives under its own header in the NA prompt (e.g. `### Current container status`), short NF/status list. When empty, the section renders a single "all containers running" line so the header is always present and the NA can rely on it.
3. **Empty snapshot ⇒ absence of `infra:` lines in the query.** When `get_network_status` returns all-running/healthy, no `infra:` line is added to the RAG query. (An explicit `infra:none` token would match against itself in the corpus and could pull false-healthy precedents higher; absence is the correct encoding.)
4. **Soft re-ranker (Lever 2) is out of scope for this ADR.** This change is structural-fingerprint-only; whether a re-ranker adds further value is deferred until Lever 1 is in production and measured.
