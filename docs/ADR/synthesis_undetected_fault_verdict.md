# ADR: Synthesis emits `undetected_fault` when no hypothesis confirms; investigator probes signal OUT_OF_SCOPE as a static fact

**Date:** 2026-06-08
**Status:** Proposed
**Related:**
- Forcing run: [`agentic_ops_v7/docs/agent_logs/run_20260606_030818_pyhss_clock_skew_(observabilit.md`](../../agentic_ops_v7/docs/agent_logs/run_20260606_030818_pyhss_clock_skew_(observabilit.md) — v7 scored **0%** by promoting `nr_gnb` as the primary suspect despite all hypotheses ending DISPROVEN/INCONCLUSIVE.
- The scenario that exposed it: [`agentic_chaos/CDR/0001-novel-failure-scenarios.md`](../../agentic_chaos/CDR/0001-novel-failure-scenarios.md) §1 (PyHSS Clock Skew — designed as the first negative-control scenario in the library).
- Operator-scope documentation: `agentic_ops/models.py:27-35` — `AgentDeps.all_containers` deliberately excludes `nr_gnb`/UE containers ("outside the NOC boundary").
- Code paths affected:
  - `agentic_ops_v7/models.py:437-450` — `verdict_kind` Literal
  - `agentic_ops_v7/subagents/synthesis.py` — Synthesis prompt + emission
  - `agentic_ops_v7/subagents/investigator.py` — probe outcome classification
  - `agentic_ops_v7/blast_radius.py` — Phase 8 no-op path
  - `agentic_ops/tools.py:1071-1115` (`measure_rtt`) and `:204-241` (`get_network_status`) — tool error messages
  - `agentic_chaos/scorer.py` — scoring of the new verdict

---

## Decision

Two complementary changes, in priority order:

1. **Synthesis adds a single new verdict_kind, `undetected_fault`**, that the agent emits when investigation completed but no hypothesis was confirmed. The agent never claims "no fault exists" — only "I couldn't pinpoint a fault; please investigate further."

2. **Tool boundary (Tasks A + B):** `measure_rtt` and `get_network_status` return a distinct `OUT_OF_SCOPE` signal (instead of generic "unknown container") when probed for `nr_gnb` or the UE containers; the investigator's outcome classifier learns to use it as a stable, terminal signal rather than episodic ambiguity. This is the supporting fix that closes the proximate cause of the false promotion in the forcing run.

---

## Background — the forcing run

PyHSS Clock Skew (Observability) is a CDR-0001 §1 negative-control scenario: clock skew on PyHSS has no functional impact in this lab (counter-based SQN, cleartext Diameter, no Kamailio `date_check`). The expected agent verdict is "I couldn't find a fault — please investigate further." The agent's actual verdict was `promoted` naming `nr_gnb`, with reasoning *"All primary hypotheses were ultimately disproven or inconclusive, but cross-corroboration points to nr_gnb as the most likely source of the fault."*

The bug is structural: `verdict_kind` today has five values (`confirmed`, `promoted`, `inconclusive`, `localized`, `compound`), and **none of them lets Synthesis honestly say "I couldn't find anything."** The closest existing value, `inconclusive`, is used for procedural failures (tool errors, schema validation failures, model timeouts) — it means "investigation broke," not "investigation finished with no result." The LLM, faced with a schema that requires naming a culprit, picks the least-disconfirmed candidate. That is rational behavior given the schema; the fix is to extend the schema.

---

## The Synthesis change

`AgentDiagnosis.verdict_kind` gains one new value:

```python
verdict_kind: Literal[
    "confirmed", "promoted", "inconclusive", "localized", "compound",
    "undetected_fault",   # ← new
]
```

### When Synthesis MUST emit `undetected_fault`

Both of the following hold:

1. **No hypothesis was CONFIRMED.** Every Phase 5 sub-Investigator verdict (including any Phase 6.5 re-investigation) is DISPROVEN or INCONCLUSIVE.
2. **No KB event correlation produced a confirmed root cause.** Phase 2 Correlation Analyzer did not produce a high-confidence composite hypothesis that survived investigation.

When `undetected_fault` is emitted:

- `affected_components` is `[]`
- `localization` is `None`
- `additional_root_causes` is `[]`
- The verdict text follows a fixed shape: *"I was unable to detect a specific fault. Anomalous signals observed on \<NF list\> could not be localized to a confirmed root cause. Manual NOC review recommended."*

The framing is deliberate: **the agent never claims the stack is healthy.** It says "I couldn't find a fault" and defers to a human. This is the right humility level for an investigation tool — the operator decides whether the absence of detection means absence of problem, or whether further investigation is warranted.

### Decision tree at Synthesis-entry

```
if any sub-investigator verdict is CONFIRMED:
    → confirmed | localized | compound       (existing logic)
elif Phase 2 correlation produced a confirmed composite root cause:
    → promoted                               (existing logic)
else:
    → undetected_fault                       (NEW)
```

The existing `inconclusive` value stays in the enum for its current purpose: procedural failure mid-investigation. Different signal, different downstream action (retry vs. NOC review).

### Mechanical enforcement

One guardrail enforces:

**`synthesis_no_overclaim`** (post-LLM): if no hypothesis confirmed AND no correlation root cause AND the LLM emits `promoted`/`confirmed`/`localized`/`compound`, REJECT and resample once with the rejection reason injected. Second reject → orchestrator overrides verdict_kind to `undetected_fault` deterministically. Mirrors `synthesis_pool` pattern.

---

## Supporting change — investigator probes treat OUT_OF_SCOPE as a static fact

Today, when an investigator probes an out-of-scope target (`nr_gnb`, `e2e_ue1`, `e2e_ue2`), the tool returns `"Unknown target container 'X'. Known: …"` — the same message used for typos and made-up names. The investigator interprets it as an episodic gap and marks the verdict AMBIGUOUS/INCONCLUSIVE. In the forcing run, this turned a genuinely unreachable RAN probe into a "we still can't disprove this hypothesis" hedge, which Synthesis then read as "strongest remaining candidate."

The fix in two sub-tasks:

### Sub-task A — tool-boundary error messages name the boundary

Replace the generic rejection with a structured OUT_OF_SCOPE response in two tools.

**`measure_rtt`** (`agentic_ops/tools.py:1071, 1111`):

```python
_OUT_OF_SCOPE_CONTAINERS = {"nr_gnb", "e2e_ue1", "e2e_ue2"}

if target in _OUT_OF_SCOPE_CONTAINERS:
    return (
        f"OUT_OF_SCOPE: '{target}' lives outside the NOC's tool surface "
        f"(RAN/UE boundary). This is a STATIC architectural fact, not an "
        f"episodic gap — do not retry. Infer its state from in-scope "
        f"metrics:\n"
        f"  - gNB liveness/N2 association → AMF gauge `gnb` (1.0 = up)\n"
        f"  - UE attach state → AMF gauge `ran_ue` (count of attached UEs)\n"
        f"  - UE IMS registration → `run_kamcmd(pcscf, "
        f"'stats.get_statistics ims_usrloc_pcscf:')`\n"
        f"Use `get_nf_metrics(['amf'])` to read the AMF gauges."
    )
if target not in deps.all_containers:
    return f"Unknown target container '{target}'. Known: {', '.join(...)}"  # existing
```

The `OUT_OF_SCOPE:` prefix is a stable token the Investigator can pattern-match without parsing the full message.

**`get_network_status`** (`agentic_ops/tools.py:204-241`): add a stable `out_of_scope` key to the returned JSON:

```json
{
  "phase": "ready",
  "running": [...],
  "down_or_absent": [...],
  "containers": {...},
  "out_of_scope": {
    "nr_gnb": "RAN — outside NOC; infer via amf.gnb gauge",
    "e2e_ue1": "UE — outside NOC; infer via amf.ran_ue + pcscf usrloc",
    "e2e_ue2": "UE — outside NOC; infer via amf.ran_ue + pcscf usrloc"
  }
}
```

**Size:** ~30 LoC + a single-source `_OUT_OF_SCOPE_CONTAINERS` constant in `agentic_ops/models.py` alongside `all_containers`.

### Sub-task B — Investigator outcome classification distinguishes OUT_OF_SCOPE from AMBIGUOUS

The Investigator's probe-outcome classifier (`agentic_ops_v7/subagents/investigator.py`) today maps tool responses to `CONTRADICTS` / `SUPPORTS` / `AMBIGUOUS` / `tool_unavailable`. Add a fifth outcome `OUT_OF_SCOPE` for responses starting with `OUT_OF_SCOPE:` or whose JSON includes the `out_of_scope` key for the target.

Verdict-rollup rule:

> When a hypothesis's probes include `OUT_OF_SCOPE` outcomes AND in-scope evidence cited elsewhere in the investigation is consistent with the targeted NF being healthy, the verdict is **DISPROVEN** with reasoning *"target is out-of-scope for direct probes; in-scope inference (\<metric citation\>) is inconsistent with the hypothesis."*

With this rule, the forcing run's `h2: nr_gnb` would have been cleanly DISPROVEN (via the AMF metrics `gnb=1`, `ran_ue=2`) rather than INCONCLUSIVE. Synthesis would still emit `undetected_fault` — because no hypothesis was CONFIRMED — but the verdict tree feeding Synthesis would have been clean.

**Size:** ~20 LoC change to the classifier function + ~5 lines added to the Investigator's system prompt explaining the OUT_OF_SCOPE rule.

---

## Phase 8 (Blast Radius) handling

When `verdict_kind == "undetected_fault"`, Phase 8's deterministic compute short-circuits to an empty BlastRadius. Narrator emits:

> "No specific fault was localized during this episode. Anomalous signals were observed on \<NF list\> but were not attributed to a confirmed root cause. Manual NOC review recommended."

Without this no-op path, the existing narrator would hallucinate failing services as it did in the forcing run (line 627 of the episode markdown — claimed `VoNR voice calls: 🔴 failing` while observation logs showed all 3 calls succeeded).

---

## Scorer (`agentic_chaos/scorer.py`)

The LLM judge gets one new rubric case:

| Ground truth | Verdict emitted | Score |
|---|---|---|
| Real fault present | `undetected_fault` | Partial — honest hedge is better than fabrication but worse than correct localization |
| Negative control / no functional impact | `undetected_fault` | High — this is the correct outcome for the agent's epistemic position |
| Anything | `promoted`/`confirmed`/`localized` (wrong NF) | Existing — typically low/0% |

The agent is never rewarded for claiming "no fault exists" — the rubric simply rewards humble admission when the scenario was a negative control. Operators read the verdict and decide whether to escalate; the scorer measures whether the verdict was honest.

---

## Acceptance criteria

**Synthesis:**
- [ ] `AgentDiagnosis.verdict_kind` Literal includes `undetected_fault`
- [ ] Schema constraints enforce: `undetected_fault` requires `affected_components == []`, `localization is None`, `additional_root_causes == []`
- [ ] Synthesis prompt documents the decision tree and the "humble admission" framing
- [ ] `synthesis_no_overclaim` guardrail rejects `promoted`/`confirmed`/`localized`/`compound` when no hypothesis confirmed; falls through to deterministic `undetected_fault` on second reject
- [ ] Unit tests cover:
  - all-DISPROVEN / INCONCLUSIVE → `undetected_fault`
  - one CONFIRMED → existing verdict_kind path unchanged
  - confirmed correlation root cause → existing `promoted`

**Tool boundary (Tasks A + B):**
- [ ] `_OUT_OF_SCOPE_CONTAINERS = {"nr_gnb", "e2e_ue1", "e2e_ue2"}` lives in `agentic_ops/models.py` as the single source of truth
- [ ] `measure_rtt` emits the `OUT_OF_SCOPE:` response shape for those three names
- [ ] `get_network_status` JSON includes an `out_of_scope` block
- [ ] Investigator outcome classifier maps `OUT_OF_SCOPE:` responses to outcome `OUT_OF_SCOPE`
- [ ] Investigator rollup rule: OUT_OF_SCOPE + in-scope contradiction → DISPROVEN
- [ ] Unit tests cover both behaviors

**Phase 8:**
- [ ] `verdict_kind == "undetected_fault"` short-circuits to empty BlastRadius
- [ ] Narrator emits the "no specific fault localized; manual review recommended" one-liner

**Scorer:**
- [ ] LLM judge prompt updated with the rubric for `undetected_fault` on negative-control vs. real-fault scenarios

**End-to-end validation:**
- [ ] Re-run "PyHSS Clock Skew (Observability)" against v7. Expected: `verdict_kind="undetected_fault"`, scorer score substantially > 0% (a strict improvement over today's 0%).
- [ ] Re-run "Asymmetric Path Loss (AMF→gNB)" and existing real-fault scenarios (e.g. "MongoDB Gone", "P-CSCF Latency") against v7. Expected: no regression — `undetected_fault` doesn't fire because hypotheses confirm.

---

## Status After Review

Awaiting review. Two implementation passes recommended:

1. **Synthesis first.** On the forcing run, this alone flips the verdict from `promoted` (0%) to `undetected_fault` — a strict improvement even without Tasks A/B.
2. **Tasks A/B as the follow-up.** With these landed, the verdict tree feeding Synthesis is cleaner (no false INCONCLUSIVEs from out-of-scope probes), but the final verdict on the forcing run remains `undetected_fault` — because that's the correct answer when the agent can't pinpoint a fault, regardless of whether the underlying stack is actually healthy.
