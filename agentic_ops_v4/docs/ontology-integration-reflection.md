# Why Giving an LLM a Knowledge Graph Tool Doesn't Work

**Date:** 2026-03-31
**Context:** First run of v4 with the network ontology available as agent tools

---

## What We Built

We built a network ontology — a Neo4j graph database encoding the entire causal structure of a 5G SA + IMS network: component topology, failure mode chains, log semantics, symptom signatures, protocol stack rules, and health check protocols. It's the distilled knowledge from 10+ failed RCA runs and five detailed postmortems.

Then we wired it into the v4 agent as tools: `query_ontology`, `interpret_log_message`, `check_component_health`, `get_causal_chain`. We gave these tools to the TriageAgent and the SynthesisAgent — the two agents best positioned to use domain knowledge.

## What Happened

The gNB was killed. Triage correctly saw INACTIVE N2/N3 links and `ran_ue=0`. The definitive RAN failure signature — the exact pattern encoded in the ontology with `confidence: very_high`.

The agent never called the ontology.

Instead, it passed the raw triage findings downstream. The IMSSpecialist consumed 34K tokens hallucinating an HSS iFC issue. The TransportSpecialist consumed 58K tokens (36% of the entire budget) investigating the wrong thing. The CoreSpecialist was dispatched but made zero tool calls. The SynthesisAgent had `query_ontology` in its toolset and never used it.

The agent ranked the correct diagnosis (RAN disconnected) as Cause #2, behind the hallucinated iFC issue as Cause #1. Score: 60% — better than the 0% runs without the ontology being available, but still wrong.

## The Mistake

We treated domain knowledge as an optional tool the LLM can choose to ignore. This is the same mistake we've made in every version of the agent — believing that giving the LLM access to the right information is sufficient. It isn't.

The history is instructive:

- **v1.5:** Gave the agent `measure_rtt` and `check_tc_rules`. Agent never used them at the right time. Score: 0-40% on gNB kill.
- **v2:** Gave specialists "domain laws" in their prompts. Specialists ignored them when real symptoms were more interesting. Score: 0%.
- **v3:** Gave triage a "Golden Flow Baseline" to compare against. Triage noted the anomalies but downstream agents fixated on noise. Score: 0%.
- **v4:** Gave triage the network topology graph. Triage correctly identified INACTIVE links, then specialists ignored the finding and chased pre-existing P-CSCF noise. Score: 0%.
- **v4 + ontology tools:** Gave triage and synthesis `query_ontology`. Neither called it. Score: 60% (better, but still wrong primary cause).

The pattern: every version adds more information to the LLM's reach, and every version the LLM finds a way to not use it. The information isn't the bottleneck — the decision to use it is.

## Why LLMs Don't Use Tools Reliably

An LLM deciding whether to call a tool is making a meta-cognitive decision: "Do I need external help, or can I reason about this myself?" LLMs consistently overestimate their ability to reason about domain-specific causal chains. When the triage agent sees `ran_ue=0`, it doesn't think "I should query the ontology for what this means" — it thinks "I know what this means" and generates a plausible-sounding (but often wrong) interpretation.

This isn't a prompt engineering problem. We've tried:
- Telling the agent to "always check metrics first" → ignored when interesting logs appear
- Telling the agent to "call check_tc_rules FIRST" → called 5th, after 4 other tools
- Giving the agent domain laws → overridden by the LLM's own reasoning
- Making tools available → tools sit unused

The LLM treats every tool as optional because it always has the option of reasoning without it. And reasoning feels productive — the LLM generates confident-sounding analysis that happens to be wrong.

## The Correct Architecture

The ontology should not be a tool the LLM can call. It should be a **deterministic step in the orchestrator** that runs automatically, in code, and injects its results into the agent's context as established facts.

```
Current (broken):
  Phase 0: Triage collects metrics
  Phase 0.5: (nothing — LLM was supposed to call ontology but didn't)
  Phase 1: Tracer gets raw triage output, no ontology context
  Phase 2: Dispatcher routes based on LLM reasoning about symptoms
  Phase 3: Specialists investigate whatever they want

Proposed (deterministic):
  Phase 0: Triage collects metrics
  Phase 0.5: ORCHESTRATOR (Python, not LLM) calls ontology.diagnose(metrics)
             → Returns: "N2 connectivity loss, confidence: very_high"
             → Injects into state as established fact
  Phase 1: Tracer sees "ontology diagnosis: RAN failure (very_high)" in its context
  Phase 2: Dispatcher sees the ontology result — routes to core, not IMS
  Phase 3: Specialists see "the ontology already identified this as RAN failure"
```

The difference: the ontology result isn't a suggestion the LLM can ignore — it's a fact in the state that every downstream agent reads. The LLM's role shrinks from "decide what the symptoms mean" to "verify the ontology's hypothesis and explain it."

## The Broader Lesson

This is the same lesson the entire v1-v4 evolution teaches, stated more sharply:

**If a decision can be made deterministically, it must not be delegated to an LLM.**

The ontology encodes deterministic knowledge: "if ran_ue=0 AND gnb=0, this is RAN failure with very_high confidence." There is no ambiguity, no judgment call, no need for LLM reasoning. Making the LLM the gatekeeper for this lookup is like making a poet the gatekeeper for a database query — they might get around to it, but they'd rather write about it first.

The LLM is valuable for:
- Interpreting ambiguous situations the ontology can't resolve
- Explaining findings in plain language
- Investigating novel failures not in the ontology
- Executing diagnostic steps and reporting results

The LLM is not valuable for:
- Deciding whether to consult the knowledge base (answer: always)
- Reasoning about causal chains (the ontology has them pre-computed)
- Interpreting log messages (the ontology has semantic annotations)
- Distinguishing baseline noise from real symptoms (the ontology has baselines)

Every piece of deterministic domain knowledge we move out of the LLM's judgment and into code is a class of errors we eliminate permanently.

## Next Step

Implement the deterministic ontology lookup in `orchestrator.py`. After triage, the orchestrator (Python) calls `ontology.diagnose()` with the collected metrics, checks stack rules, compares to baselines, and injects the results into `state["ontology_diagnosis"]`. No LLM involved in this step. The LLM only engages when the ontology returns ambiguous results or no match.

This is the v4 → v5 transition: from "ontology as tool" to "ontology as backbone."
