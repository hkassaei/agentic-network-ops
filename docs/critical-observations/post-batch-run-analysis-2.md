# Post-Batch-Run Analysis #2 — v6 Across 11 Chaos Scenarios, After Scorer Fix + Log-Tool Removal

**Date:** 2026-04-22
**Agent version:** v6 (ADK + gemini-2.5-pro on every LlmAgent with `output_schema`, Synthesis + NA + Investigator + InstructionGenerator)
**Batch runner:** `scripts/run-all-chaos-scenarios.sh v6 --abort-on-unpropagated`
**Episode logs:** `agentic_ops_v6/docs/agent_logs/run_20260422_031153…_041716` (11 episodes)

**Preceding analysis:** [`post-batch-run-analysis.md`](post-batch-run-analysis.md) — the first batch baseline.

---

## Topline

**Mean score: 67.8 %** — down 15.8 points from the prior batch's 83.6%.

Before reading the regression as "the agent got worse," understand the three things that changed between the two batches:

1. **Scorer pinned on final `causes.root_cause`** (ADR: no specific file, recorded inline in `agentic_chaos/scorer.py`). Previous batch's scorer graded NA's intermediate output alongside the final diagnosis and picked the more favorable reading. Several prior 100%s were earned on NA reasoning, not on the operator-facing diagnosis.
2. **Log-search tools removed from the Investigator toolset** (ADR: `remove_log_probes_from_investigator.md`). Agent-authored grep patterns and "no matches" treated as strong evidence had been producing documented mis-diagnoses.
3. **Prompt revisions accumulated across NA, IG, Investigator, and Synthesis** — KB-annotated flags, evidence-weighting rules, activity-vs-drops discriminator, flow-anchored probes, silence-shaped evidence handling, and the Flash → Pro upgrade for IG.

The headline drop combines a strict grader revealing pre-existing Synthesis hedging, a handful of legit regressions, and known-structural failure modes that weren't mitigated by any of the prompt-layer work.

---

## Score distribution

| Scenario | This batch | Prev batch | Δ | Ground truth | Agent's final `causes.root_cause` | Correct? |
|---|---:|---:|---:|---|---|---|
| gNB Radio Link Failure | 60 % | 100 % | **−40** | `nr_gnb` | *"Multiple: AMF internal OR partition to nr_gnb"* | Partial (hedged) |
| P-CSCF Latency | 100 % | 100 % | 0 | `pcscf` | "network path between pcscf and pcf" | Yes |
| S-CSCF Crash | 100 % | 100 % | 0 | `scscf` | "scscf container exited" | Yes |
| HSS Unresponsive | 100 % | 100 % | 0 | `pyhss` | "pyhss application unresponsive" | Yes |
| Data Plane Degradation | 26 % | 10 % | +16 | `upf` | "smf failing to program upf" | **No** |
| Call Quality Degradation | 15 % | 90 % | **−75** | `rtpengine` | "I-CSCF ↔ HSS Diameter failure" | **No (completely missed)** |
| MongoDB Gone | 40 % | 30 % | +10 | `mongo` | "pyhss not responding to Cx queries" | **No (HSS hallucination returned)** |
| DNS Failure | 90 % | 100 % | −10 | `dns` | "dns container exited" | Yes (minor hedge) |
| IMS Network Partition | 20 % | 100 % | **−80** | Mw partition (pcscf ↔ icscf) | "I-CSCF ↔ HSS Diameter issue, two equally plausible hypotheses" | **No (wrong interface)** |
| AMF Restart | 100 % | 100 % | 0 | `amf` | "amf container exited" | Yes |
| Cascading IMS Failure | 95 % | 90 % | +5 | `pyhss` + scscf latency | "pyhss container exited" | Yes (missed secondary S-CSCF latency) |

**Biggest regressions:** IMS Network Partition (−80), Call Quality Degradation (−75), gNB Radio Link Failure (−40).
**Biggest improvements:** Data Plane Degradation (+16), MongoDB Gone (+10), Cascading IMS (+5).

---

## The three things that happened

### (1) The scorer fix surfaced real Synthesis hedging that was previously masked

The previous scorer saw both AGENT DIAGNOSIS and AGENT NETWORK ANALYSIS as peer inputs and graded `root_cause_correct` against whichever said something more favorable. Today's scorer is pinned strictly to the final `causes.root_cause` / `causes.affected_components` fields — the operator-facing output. When NA was right but Synthesis walked it back to a hedge, the old scorer gave credit; the new one doesn't.

**Three clear instances in this batch:**

- **gNB Radio Link Failure (−40).** NA h1: `fit=0.95, nf=nr_gnb, specific` — correct. All three Investigators returned NOT_DISPROVEN. Synthesis hedged: *"Multiple contributing factors prevent a single root cause determination. Primary suspects are: 1. An internal fault in the AMF … 2. A network partition between the AMF and the gNB."* The correct NF was named but shared billing with a wrong one. Previous scorer gave full credit; this one docked.

- **IMS Network Partition (−80).** Synthesis: *"The evidence is insufficient to isolate a single root cause. The fault lies in the Diameter communication between the I-CSCF and the HSS, with two equally plausible hypotheses remaining."* Neither of the two hypotheses it named is the actual fault (the simulated failure was a Mw partition between P-CSCF and I-CSCF). Note also that NA itself missed the correct framing this time — h3 (pcscf, fit=0.40) was the closest, never promoted.

- **DNS Failure (−10).** All three Investigators DISPROVED their assigned hypotheses. Synthesis still named DNS correctly in `root_cause` but hedged with *"it could not be confirmed with high confidence. `primary_suspect_nf`: `dns`, `icscf`."* Scorer appropriately docked a point for the co-listed `icscf`.

**This is the scorer doing its job**, not a regression in the agent itself. The corresponding Synthesis weakness — hedging when Investigators can't discriminate — is a real reasoning gap to address, separately.

### (2) Two scenarios really did regress, for reasons we understand

**Call Quality Degradation: 90 % → 15 %.** NA summary this run: *"The IMS core is impaired due to Diameter connectivity issues between the I-CSCF and HSS."* RTPEngine never appears in any hypothesis. This is the **RTPEngine invisibility problem** carried over from prior ADRs:

- ADR `remove_cumulative_rtpengine_features.md` removed all useful RTPEngine quality metrics from the anomaly model because their cumulative-lifetime semantics polluted cross-scenario runs.
- The only surviving RTPEngine feature is `errors_per_second_(total)`, which does not fire on forwarding-layer packet loss (RTPEngine's "errors" are session/control errors, not packet drops).
- 30% RTP packet loss is invisible to the screener. The Investigator can't diagnose what the pipeline doesn't surface.

The previous 90% was a lenient-scorer artifact — NA got partial credit for naming IMS impact even though the actual root cause was missed. **The true performance on this scenario is low and structural**, not a consequence of recent prompt edits. Unlocked only when rate-based RTPEngine features are added to the model.

**IMS Network Partition: 100 % → 20 %.** NA framed it as I-CSCF ↔ HSS Cx trouble (`h1 nf=icscf fit=0.80`, `h2 nf=pyhss fit=0.70`, `h3 nf=pcscf fit=0.40`). The actual fault is a Mw partition between P-CSCF and I-CSCF. NA hedged h3 toward the right area (pcscf) but with low fit; the Investigator's probes for h1/h2 came back NOT_DISPROVEN because there's no way to falsify a correctly-structured-but-vague internal-fault hypothesis from outside.

I cannot isolate whether the log-tool removal contributed. The previous run's NA may have had a different anomaly flag pattern that seeded a different framing. A single-run regression on a specific scenario isn't yet a pattern — worth re-running to confirm.

### (3) Two known-bad patterns recurred to form

**MongoDB Gone: 30 % → 40 %** (marginal improvement but still wrong). NA h1 this run: `fit=0.90, nf=pyhss, specificity=specific` — *"The HSS is unresponsive to the I-CSCF…"*. **This is the exact HSS hallucination the `subscriber_data_store_unavailable` causal-chain rewrite was supposed to prevent.**

Compared to the previous one-off run (`20260422_024538`, scored 100 %), where NA correctly named `nf=pcf` and walked the mongo → PCF → P-CSCF chain, this batch's NA reverted to the default HSS-blame pattern. The ontology has the right causal chain authored (in `causal_chains.yaml`), but NA didn't consult it or didn't pattern-match against it this time. **NA's framing is non-deterministic and prior-knowledge-biased** — a week of ontology authoring can be undone by one unlucky roll of the model.

**Data Plane Degradation: 10 % → 26 %** (marginal improvement). NA h1 correctly named UPF at fit=0.90. Investigator h1 then **DISPROVED** it with this reasoning:

> *"Probes show that the UPF is, in fact, receiving and transmitting packets, directly contradicting the hypothesis. The data plane is degraded, not completely down."*

This is the **activity-vs-drops misread** in its purest form: any non-zero traffic gets read as "working," even when it's 30 % of baseline. The Investigator ended up choosing SMF as NOT_DISPROVEN — wrong NF.

Both the NA prompt (principle #4 "low activity ≠ local fault") and the IG prompt (rule #7 "activity-vs-drops discriminator") have rules addressing this, and neither fired here. The prompt-layer mitigations aren't holding on this failure shape.

---

## Scenarios grouped by what drives their score

### Stable high performance — 5 scenarios at 95 % or 100 %

**P-CSCF Latency, S-CSCF Crash, HSS Unresponsive, AMF Restart, Cascading IMS Failure.**

Common pattern: **unambiguous root cause with a direct observable signal** — a container exited, a clear metric that only the true cause could produce, an RTT partition, a process crash. NA identifies cleanly, Investigator confirms with structured probes, Synthesis commits. No media-plane involvement, no compound faults, no subtle multi-hop causal chains.

These stayed at 100 % across both batches. **The agent is genuinely reliable on this class.**

### Structural diagnostic failures — pre-existing, no prompt fix closes them

- **Call Quality Degradation (15 %)** — blocked on RTPEngine features in the anomaly model (removed per ADR `remove_cumulative_rtpengine_features.md`, never replaced with rate-based equivalents). **Until the model can see RTP packet loss, this scenario will keep scoring poorly.**
- **Data Plane Degradation (26 %)** — activity-vs-drops discriminator in the prompt not firing. Investigator treats "non-zero pps" as "working" and moves on.
- **MongoDB Gone (40 %)** — HSS hallucination recurs. NA's default for any IMS Diameter-timeout pattern is to blame HSS; the mongo → PCF → P-CSCF chain is authored in the ontology but consulted inconsistently.

### Synthesis-hedge regressions — scorer-revealed, not agent-regressed

- **gNB Radio Link Failure (60 %)** — Synthesis listed two equally-plausible suspects when Investigators all came back NOT_DISPROVEN.
- **IMS Network Partition (20 %)** — Synthesis listed *"two equally plausible hypotheses"* after reasoning on the wrong interface.
- **DNS Failure (90 %)** — slight hedge with `[dns, icscf]` co-listed as primary suspects.

These share a Synthesis failure mode: **when Investigators return multiple NOT_DISPROVEN verdicts, Synthesis declines to discriminate.** The old scorer didn't penalize this because the right NF was mentioned somewhere. The new scorer does. Addressable with one Synthesis prompt rule, deferred until the batch stabilizes.

---

## What the log-tool removal actually bought

Narrow, measurable impact:

- **MongoDB Gone +10** (30 % → 40 %). The specific failure mode we targeted — Investigator disproving mongo hypotheses because `search_logs` came back empty — did not happen this batch. The agent's new failure mode on this scenario is different (NA never proposed the mongo hypothesis at all; it blamed HSS directly). So the log-tool removal closed one door and the agent found another.
- **Data Plane Degradation +16** (10 % → 26 %). Investigator couldn't use log-searches to "prove" UPF was fine via empty grep patterns, so the verdict was more honest about what the probes actually showed. Still wrong overall, but the specific grep-based false-disproof is gone.

**No regressions** I can attribute to the log removal with confidence. The regressions on ims_network_partition and gnb have explanations rooted in Synthesis hedging (scorer revelation) and NA non-determinism, not in lost log access.

Net: log-tool removal was a correct decision for its scope. It closed the specific failure class the ADR targeted. It wasn't a panacea for the other failure classes, and didn't claim to be.

---

## Net assessment

The batch tells a cleaner story than the headline number suggests:

1. **The agent is reliable on ~5/11 scenarios.** Container-exited / component-unreachable patterns with clean direct signals. 100 % on these is earned, not gifted by the scorer.

2. **The agent has 3 pre-existing structural blind spots** that no prompt-layer work has closed:
   - RTPEngine invisibility (model-level gap)
   - Activity-vs-drops discrimination at UPF (prompt rules present, not firing reliably)
   - HSS-default hallucination for IMS Diameter-timeout patterns (ontology has the right answer, NA doesn't consult it consistently)

3. **Synthesis hedges when Investigators can't discriminate.** Previously masked by the lenient scorer. Now visible and docked appropriately.

4. **NA output is non-deterministic enough to matter.** Same scenario, same stack, same prompt → week-apart 100 % and 40 % on MongoDB Gone. The ontology fixes for that scenario only help when NA happens to frame the hypothesis in a way that consults them.

The underlying agent performance is roughly consistent with the previous batch; the grade difference is about **grading honestly** rather than **performance regression.** That said, "consistent with 83.6 %" is not the same as "good enough" — half of the scenarios still have real diagnostic problems.

---

## Recommendations, in priority order

1. **Hold the line on prompt edits for 2-3 more batches.** We've made a lot of changes in a short window. Every prompt tweak has some probability of breaking structured output (see the IG Flash flakiness), and the signal gets noisier with each successive edit. Running the batch 2-3 times without changes will tell us whether 67.8 % is the real baseline or whether NA non-determinism is swinging it.

2. **Fix the structural blind spots, one at a time:**
   - **RTPEngine rate-based features in the anomaly model** — highest leverage, single-scenario unlock. ADR already discussed in prior conversations; `rate(rtpengine_packetloss_total)`, `rate(rtpengine_mos_total)`, `rate(rtpengine_jitter_total)` are the targets. Supersede the old `remove_cumulative_rtpengine_features.md` ADR.
   - **Ontology authoring for mongo's downstream consumers.** Encode the `mongo → UDR → PCF → P-CSCF N5` path into `components.yaml` as typed edges so NA's `get_flows_through_component` / `get_causal_chain_for_component` tools can return the right chain structurally. Stop relying on NA to reconstruct it from priors.
   - **UPF activity-vs-drops.** Needs a KB entry that explicitly distinguishes "percent packet loss at boundary" (requires baseline comparison) from "absolute volume" so the Investigator has a concrete discriminator to check rather than a vague prompt rule.

3. **Single Synthesis prompt rule: "commit, don't hedge."** When multiple NOT_DISPROVEN hypotheses survive, Synthesis must pick the one with highest NA `explanatory_fit` and commit with appropriate confidence. List others as alternatives in `recommendation`, not as co-equal root causes in `causes.root_cause`. Would recover 20-40 points on gNB Radio Link Failure and DNS Failure at minimum.

4. **Acknowledge NA non-determinism as a real variable.** Any single-batch result has sampling noise from NA framing differently across runs. Treat batch means as estimates with a confidence interval, not point values. Only trust improvements that reproduce across 2-3 batches; don't over-interpret regressions on a single batch.

---

## Score dashboard

```
Agent   Scenario                                             Duration   Score   Δ vs prev
-----   --------                                             --------   -----   ---------
v6      gNB Radio Link Failure                               323.2s       60%   −40
v6      P-CSCF Latency                                       336.4s      100%     0
v6      S-CSCF Crash                                         310.0s      100%     0
v6      HSS Unresponsive                                     367.4s      100%     0
v6      Data Plane Degradation                               324.4s       26%   +16
v6      Call Quality Degradation                             256.4s       15%   −75
v6      MongoDB Gone                                         359.8s       40%   +10
v6      DNS Failure                                          365.2s       90%   −10
v6      IMS Network Partition                                347.2s       20%   −80
v6      AMF Restart (Upgrade Simulation)                     313.8s      100%     0
v6      Cascading IMS Failure                                333.5s       95%    +5
-----   --------                                             --------   -----   ---------
                                                     Mean               67.8%
                                                     Prev mean          83.6%
```

---

## Appendix — What changed between the two batches

For reference when interpreting the score deltas:

**New or changed agent-facing logic since the previous batch:**

- Scorer: pinned on final `causes.root_cause` / `causes.affected_components`; NETWORK ANALYSIS section scoped to `layer_accuracy` only (ADR-level change inline in `scorer.py`).
- Log-search tools (`read_container_logs`, `search_logs`) removed from Investigator and IG toolsets (ADR: `remove_log_probes_from_investigator.md`).
- IG model upgraded from `gemini-2.5-flash` to `gemini-2.5-pro` (closed the recurring Flash + `output_schema` empty-output failures).
- Flow-query tools (`list_flows`, `get_flow`, `get_flows_through_component`) exposed to NA, IG, and Investigator (ADR: `flow-based-causal-chain-reasoning.md`).
- `flows.yaml` rewritten for N5 / WITH_RX-off semantics across ims_registration, vonr_call_setup, vonr_call_teardown, pdu_session_establishment, ue_deregistration, diameter_cx_authentication.
- `causal_chains.yaml`: `subscriber_data_store_unavailable` rewritten as a four-branch entry with `source_steps` cross-references.
- Investigator prompt: added localization rule (triangulation), negative-result interpretation, silence-shaped-evidence upstream-activity check, evidence-weighting rule. Tightened after the IG Flash break.
- IG prompt: triangulation-mandatory rule, activity-vs-drops discriminator, negative-result falsification weight, flow-anchored probes preference. Rule #7 rewritten tightly after the Flash break.
- NA prompt: "observing NF can be the fault source", "reading anomaly flags — meaning first, numbers second", cumulative-counter forbidden comparison, low-activity-upstream-starvation rule, source-side-vs-destination-side-latency rule.

**Unchanged:**
- AnomalyScreener model and feature set (same as prior batch).
- Ontology causal_chains for 5G-core failure scenarios (only the IMS chain was rewritten).
- Container stack and traffic generator.
- Scorer weights (0.40 × root_cause + …).

The 15.8 point mean drop reflects the combination of strict grading revealing Synthesis hedges, structural blind spots that no prompt change has closed, and ordinary NA sampling noise. No single change cleanly explains the full delta; the honest read is that the new scorer is showing us what the agent actually does, not hiding it behind generous credit.
