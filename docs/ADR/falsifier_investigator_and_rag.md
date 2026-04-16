# ADR: Falsifier Investigator + Episode-Memory RAG

**Date:** 2026-04-16
**Status:** Proposed
**Supersedes:** [`conditional_investigator_skip.md`](conditional_investigator_skip.md) — the unconditional skip it introduced is the root problem this ADR addresses.
**Related:**
- [`evidence_validator_agent.md`](evidence_validator_agent.md) — 6-phase pipeline definition
- [`v5_6phase_pipeline.md`](v5_6phase_pipeline.md) — current pipeline layout
- [`../critical-observations/run_20260415_032202_ims_network_partition.md`](../critical-observations/run_20260415_032202_ims_network_partition.md) — triggering episode (20% score)

---

## Decision

Rework the orchestration so that the Network Analyst's confidence no longer gates the Investigator. Split the rework into two independent tracks, landed sequentially:

- **Track 1 — Falsifier Investigator.** Remove the always-skip. Always run the Investigator, but redefine its job as *falsifying the Network Analyst's primary suspect*. Output is not a new diagnosis; it is either "NA's suspect was not falsified" (confirm) or "NA's suspect was falsified — here is the disconfirming evidence" (reject).
- **Track 2 — Episode-Memory RAG (two retrievers).** Insert a retrieval phase between the Anomaly Screener and the Network Analyst. Two parallel retrievers feed the NA complementary context: nearest-neighbor historical episodes (ground truth only, not prior diagnoses) and curated "known trap" snippets extracted from post-run analyses.

Track 1 ships first. Track 2 begins only after Track 1 produces measurable quality improvement on the existing episode corpus.

---

## Context

### Why the always-skip is broken

[`conditional_investigator_skip.md`](conditional_investigator_skip.md) introduced a skip gate:

> Skip when (1) NA produced structured output AND (2) ≥1 suspect is HIGH confidence AND (3) ≥1 layer is RED.

Across every episode in `agentic_ops_v5/docs/agent_logs/` from 2026-04-14 onward, the gate fires. The Network Analyst prompt is strong enough that it almost always produces a HIGH suspect + RED layer. This is fine when NA is right — and it usually is. It is fatal when NA is *confidently wrong*.

Triggering episode (`run_20260415_032202_ims_network_partition.md`, score 20%):

- Injected fault: iptables DROP between P-CSCF ↔ I-CSCF and P-CSCF ↔ S-CSCF.
- NA diagnosis: RTPEngine packet loss. Confidence HIGH. Layer IMS RED.
- Actual trigger: `rtpengine.average_packet_loss = 8.0` was a **stale cumulative lifetime average** carried over from prior chaos runs — not a live signal. The anomaly screener flagged it, the NA anchored on it, and the skip gate fired before anyone checked P-CSCF ↔ I-CSCF connectivity.
- `measure_rtt("pcscf", "172.22.0.19")` would have shown 100% loss. No one called it.

The structural problem: **the skip gate uses NA's self-reported confidence to decide whether to double-check NA**. Any input that fools the NA simultaneously disables the check.

### Why NA-as-hypothesis-generator (the ultimate goal) is not Track 1

Rewriting the NA to emit hypotheses instead of diagnoses touches every downstream agent: the Investigator prompt, the Synthesis prompt, the output schema, the scorer. Large blast radius, hard to roll back. Track 1 gets 80% of the value with a surgical change to the orchestrator and the Investigator prompt. Track 2 (hypothesis-mode NA) can build on Track 1 once the falsifier loop is proven.

### Why RAG is a separate track, not the first one

RAG adds generality (works for any failure mode) but has a sharp anchoring risk: if retrieval is keyed on the anomaly screener's flagged-metrics signature, the stale `rtpengine.average_packet_loss` signal will retrieve episodes where that metric *was* the correct answer, reinforcing the wrong conclusion. The retrieval design needs care — specifically the split into (a) analogs (ground truth only) and (b) curated traps. That work is independent of the falsifier loop and can be validated separately.

---

## Track 1 — Falsifier Investigator

### Goal
Catch the "confidently wrong NA" case without rewriting the NA. Generalize across failure modes — the Investigator's job is always the same regardless of which layer/component the NA named.

### Design

**Orchestration change.** Remove the skip condition from `orchestrator.py`. The Investigator always runs.

**Investigator prompt change.** Reframe from "independent reasoner" to "falsifier." The Investigator is given:
- The NA's primary suspect and its supporting evidence
- An explicit directive: *your goal is to disprove this suspect, not to re-confirm it*
- A falsification protocol: identify adjacent components (upstream and downstream in the signaling/data chain), probe their state with tools the NA did not use, and report findings

**Output contract.**
```
Verdict: NOT_FALSIFIED | FALSIFIED | INCONCLUSIVE
Primary evidence examined: [list of tool calls with results]
Falsification attempts: [what was checked to try to disprove the suspect]
Alternative suspects surfaced (if FALSIFIED): [new candidates with evidence]
```

**Synthesis change.** The Synthesis agent reads the Verdict:
- `NOT_FALSIFIED` → use NA's diagnosis as-is, tag confidence `high`
- `FALSIFIED` → use the Investigator's alternative suspects; NA's diagnosis is demoted
- `INCONCLUSIVE` → use NA's diagnosis but tag confidence `medium` with a note

**Evidence Validator change.** Remove the `investigator_skipped` branch — it is no longer needed. The validator returns to its original two-phase validation (NA + Investigator citations).

### Why this generalizes

The falsifier's job description is independent of the failure domain. "Probe adjacent components the NA did not probe" applies equally to IMS partitions, data plane degradation, RAN failures, and infrastructure outages. We are not hard-coding "check RTT between CSCFs" — we are telling the Investigator to find what the NA missed, whatever that happens to be.

### Success metric

Re-run the corpus in `agentic_ops_v5/docs/agent_logs/` and compare scores:
- The 100% episodes should stay at 100% (the falsifier confirms the suspect).
- The failing episode (032202, 20%) should improve — the falsifier should at minimum surface P-CSCF connectivity issues via adjacent-component probes.
- Token cost increases by ~one Investigator run per episode; acceptable if score distribution improves.

### Resolved design decisions

- **Instruction Generator is ontology-driven.** The IG consults the ontology (`get_causal_chain_for_component` and related helpers) to pick adjacent components for the falsification plan. Generality lives in the ontology, not in the prompt.
- **INCONCLUSIVE caps confidence at medium.** No retry loop, no second-suspect falsification in Track 1. If this proves insufficient, future work may either (a) have the Investigator falsify the NA's second-ranked suspect, or (b) skip ahead to Track 3 (NA-as-hypothesis-generator).
- **Minimum probe count is 2, default 3.** The Investigator must probe at least 2 adjacent components. If the ontology returns ≥3 adjacent components for the suspect, the default target is 3. Early stopping is not allowed below the minimum even if the first probe finds no contradiction.

### Out of scope for Track 1

- Changing the NA prompt or output schema
- Changing the Pattern Matcher
- Adding new tools
- Adding retrieval / RAG
- Falsifying NA's second-ranked suspect (deferred; see resolved decisions)

---

## Track 2 — Episode-Memory RAG (two retrievers)

Starts only after Track 1 ships and measurably improves scores on the existing corpus.

### Goal
Give the NA historical context about failure patterns without importing past misdiagnoses.

### Design

A new phase between AnomalyScreener (Phase 0) and NetworkAnalyst (Phase 1): **EpisodeMemoryRetriever**. Two retrievers run in parallel and their outputs are merged into the NA prompt alongside the screener report.

**Retriever A — Analog Episodes.**
- Corpus: all episode `.md` files in `agentic_ops_v5/docs/agent_logs/` and `agentic_ops_v4/docs/agent_logs/`.
- Retrieval key: anomaly screener signature (flagged component + metric + severity).
- Returned fields: **ground truth only** (`Ground Truth` section — failure domain, protocol impact, affected components, severity). Not the diagnosis, not the NA's suspects.
- Purpose: "episodes with a similar symptom pattern were actually caused by X, Y, or Z."

**Retriever B — Known Traps.**
- Corpus: `Post-Run Analysis` sections from episodes in `docs/critical-observations/`.
- Retrieval key: same anomaly screener signature.
- Returned fields: structured trap snippets extracted from post-run analyses (e.g., "stale cumulative rtpengine metrics can anchor diagnosis on the wrong component").
- Purpose: "when you see this pattern, here is the mistake past runs made — do not repeat it."

### Prerequisite: post-run analysis coverage

Most episodes under `agentic_ops_v5/docs/agent_logs/` do not yet have post-run analysis. Before Track 2 can ship, the operator must curate post-run analyses for a meaningful subset of the corpus — particularly for episodes where the diagnosis was wrong or marginal. This is a manual / semi-automated effort tracked separately.

### Anchoring risk and mitigations

- **Risk:** retrieval on symptom signature returns episodes where the *symptom* pattern matched but the *cause* differed, anchoring the NA.
- **Mitigations:**
  - Retriever A withholds past diagnoses and returns ground truth only — the NA sees "past failures with this signature had diverse root causes" rather than "past failures with this signature were diagnosed as X."
  - Retriever B explicitly surfaces traps, not answers. It tells the NA what to *check*, not what to *conclude*.
  - Retrieval output is capped in size so it does not dominate the NA's context.

### Success metric

After Track 1 is stable, re-run the corpus with the RAG phase enabled and compare against the Track-1-only baseline. Expected improvement: episodes where the screener's top flag is a known trap (stale metrics, scale-dependent features) should no longer anchor the NA on the wrong suspect.

### Out of scope for Track 2

- Online learning / updating the retrieval index during a run
- Embedding every tool-call output
- Retrieving for any phase other than NA

---

## Sequencing and kill switches

1. **Track 1 implementation** lands behind a feature flag (`FALSIFIER_INVESTIGATOR=1`). The always-skip remains the default until the flag is flipped. This lets us A/B the corpus.
2. **Track 1 validation** runs the corpus with the flag on, compares scores, and only then promotes the flag to default-on.
3. **Post-run analysis backfill** begins in parallel with Track 1 validation. No orchestrator changes required.
4. **Track 2 implementation** begins only after Track 1 is default-on and stable. The retrieval phase also lands behind a flag (`EPISODE_MEMORY_RAG=1`).

If Track 1 regresses overall scores, revert the flag and revisit the Investigator prompt before pursuing Track 2.

---

## Files that will change

**Track 1:**
- `agentic_ops_v5/orchestrator.py` — remove the skip gate (or gate it on the feature flag), always route through Investigator
- `agentic_ops_v5/prompts/investigator.md` — rewrite as falsifier protocol
- `agentic_ops_v5/prompts/instruction_generator.md` — re-scope to "generate falsification plan for NA's primary suspect"
- `agentic_ops_v5/prompts/synthesis.md` — branch on falsifier verdict
- `agentic_ops_v5/subagents/evidence_validator.py` — remove `investigator_skipped` branch once flag is default-on

**Track 2 (later):**
- `agentic_ops_v5/subagents/episode_memory.py` — new
- `agentic_ops_v5/prompts/network_analyst.md` — add retrieved-context section
- `agentic_ops_v5/orchestrator.py` — wire new phase
- `docs/critical-observations/` — backfilled post-run analyses
