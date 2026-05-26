# ADR: Path Resolver — NF-Burden Scoring Replaces Observable-Metrics Token Matching

**Date:** 2026-05-22
**Status:** ⛔ **OBSOLETE — Superseded by [`path_prioritizer_walks_all_candidates.md`](path_prioritizer_walks_all_candidates.md) (2026-05-25)**

---

## ⚠️ This ADR was implemented, tested, and reverted in the same session. Read the box below before reading anything else.

### Summary of what happened

The NF-burden scoring formula proposed below was implemented in full, including the tied-set walking infrastructure. End-to-end testing surfaced **5 real regressions** in `test_path_resolver.py` that the ADR's "no regression on happy paths" claim hadn't anticipated:

| Test that broke | Pre-fix pick (correct) | Post-fix pick (wrong) | Score |
|---|---|---|---|
| `f1_does_not_regress[upf_bandwidth_cap]` | `data_pdu_session_user_traffic` | `ims_registration` | 23 vs 12 |
| `f1_does_not_regress[data_plane_degradation]` | `vonr_media` | `ims_registration` | 19 vs 14 |
| `f1_does_not_regress[call_quality_degradation]` | `vonr_media` | `ims_registration` | similar |
| `classification_roundtrip_preserves_resolver_input` | `vonr_media` | `vonr_call_teardown` | 20 vs 14 |
| `f1_resolver_picks_right_flow[ims_network_partition]` (5/10) | `ims_registration` (xfail flipped) | `pdu_session_establishment` | 17 vs 15 |

### Why the formula failed — the symmetry insight

The ADR's "validation walkthrough" (Design section, case 5) asserted that `upf_bandwidth_cap` would correctly resolve to `data_pdu_session_user_traffic` because it was a "pure UPF fault" with only UPF flags. **That assertion was false.** The actual saved 5/10 episode JSON shows:

```
upf_bandwidth_cap flags:
  transport (2):  upf.gtp_indatapktn3upf_per_ue, upf.gtp_outdatapktn3upf_per_ue
  application (1): smf.bearers_per_ue
  ambiguous (5):  icscf.cdp_replies_per_ue, icscf.rcv_requests_register_per_ue,
                  pcscf.rcv_requests_register_per_ue, scscf.cdp_replies_per_ue,
                  scscf.rcv_requests_register_per_ue
```

The 5 CSCF flags are **downstream consequences** of the UPF bandwidth cap (call setup retries, register-rate drops). They are legitimately flagged. Under NF-burden scoring, those 5 ambiguous flags each contribute weight 1 to flows whose hop list contains their NF — adding +5 to `ims_registration` (which contains all three CSCFs). The IMS flow scores 23 vs `data_pdu`'s 12 and wins, even though the fault is on UPF.

**This is the same downstream-consequence problem the ADR set out to fix, just in the opposite direction.** The original problem was "UPF GTP flags are downstream of an IMS fault but vote for data-plane flows" (p_cscf_latency). NF-burden scoring fixed THAT direction but introduced the symmetric problem: "CSCF flags are downstream of a UPF fault but vote for IMS flows" (upf_bandwidth_cap).

**The IMS flow's hop list spans both IMS NFs and UPF, so any additive NF-counting formula will always vote for it when both layers' NFs are flagged — regardless of which side is upstream-causative.**

The ADR's mistake was reasoning about NF-burden in the abstract instead of running the formula against the actual saved episode JSON before writing the validation walkthrough. The "pure UPF fault" hypothesis was a reasoning artifact, not a property of real data.

### What we learned and where to go next

The localization-correctness contract cannot live in a static scoring formula that treats every flagged NF as equally implicating. Either:
- Encode causal precedence (KB-driven topological priors that say "UPF flagged + IMS flagged ⇒ data plane is upstream-causative"), which is a much larger redesign, OR
- Stop trying to force selection at the scoring layer. Let the deterministic walker probe the candidates and report which one(s) actually contain the fault.

The successor ADR ([`path_prioritizer_walks_all_candidates.md`](path_prioritizer_walks_all_candidates.md)) takes the second path: the resolver becomes a **prioritizer** that ranks evidence-bearing candidates; the walker walks **all** surviving candidates (up to a hard cap of 5) in parallel; correctness moves to the walker.

### What was reverted

All four implementation files (`path_resolver.py`, `orchestrator.py:Phase 0.6`, `agentic_chaos/recorder.py`, `test_path_resolver.py`) were reverted to HEAD. The screener-starvation work that landed in the same session was preserved (already committed as `1fa9615`). This ADR file is retained as a record of the attempt and the symmetry lesson — read but do not implement.

---

**Date:** 2026-05-22
**Original Status:** Proposed (now obsolete)
**Related:**
- Triggering episodes (Gemini-3.1 batch, 5/21):
    - [`agentic_ops_v7/docs/agent_logs/run_20260521_021756_p_cscf_latency.md`](../../agentic_ops_v7/docs/agent_logs/run_20260521_021756_p_cscf_latency.md) — resolver picked `data_pdu_session_user_traffic` (score 12) over the correct `ims_registration` (score 8); walker null-localized; app-layer recovered (100% final score, ~30k extra tokens spent).
    - [`agentic_ops_v7/docs/agent_logs/run_20260521_022431_s_cscf_crash.md`](../../agentic_ops_v7/docs/agent_logs/run_20260521_022431_s_cscf_crash.md) — same 12 vs 8 split, same mis-pick; 88% final score.
    - [`agentic_ops_v7/docs/agent_logs/run_20260521_130330_ims_network_partition.md`](../../agentic_ops_v7/docs/agent_logs/run_20260521_130330_ims_network_partition.md) — same 12 vs 8 split; 96% final score.
- Earlier batch cases pinned as xfails in `agentic_ops_v7/tests/test_path_resolver.py:494-536` (`_F1_BROKEN_CASES`): three of the four are the same mechanism as the 5/21 batch above — confirming this is a recurring structural failure, not a one-time symptom.
- [`docs/work-plan-may-11.md`](../work-plan-may-11.md) §B4 — the screener-side fix path the original author chose to defer to. This ADR argues that the resolver-side fix is feasible *and* preferable.
- [`anomaly_model_overflagging.md`](anomaly_model_overflagging.md) — the screener model design that produces the legitimately-correct UPF GTP transport flags whose downstream-consequence interpretation breaks the resolver.
- [`flow-based-causal-chain-reasoning.md`](flow-based-causal-chain-reasoning.md) — the ADR that introduces flows as first-class topological objects the resolver consumes.
- [`path_anchored_probe_planning_for_transport_layer_faults.md`](path_anchored_probe_planning_for_transport_layer_faults.md) — the transport-layer pipeline this resolver feeds. Wrong-flow selection silently degrades that pipeline's value.
- [`rag_episode_retrieval_and_lesson_injection.md`](rag_episode_retrieval_and_lesson_injection.md) — lesson L09 ("upstream silent vs. downstream noisy is a partition signature") is the operational principle this ADR encodes structurally into the resolver. Today L09 lives only in the RAG block; this ADR makes the resolver apply it deterministically before the LLM ever sees the case.
- [`screener_starvation_partial_metric_collection.md`](screener_starvation_partial_metric_collection.md) — sibling resolver/Phase 0 fix; both are pre-LLM determinism improvements.

---

## Decision

Replace the `observable_metrics`-blob token-matching component of `_score_flows` (in `agentic_ops_v7/path_resolver.py`) with **NF-burden scoring**: each flagged metric votes for the flow(s) whose hop list contains the NF the flag is on, weighted by the same per-bucket weights (transport=5, application=3, ambiguous=1). The component-overlap term is unchanged.

This is the structural encoding of operational lesson L09 in the resolver: a flow is implicated by the NFs in its hop list that show evidence of fault, not by whether the flow author happened to list the moving metrics in their `observable_metrics` blob.

Pair it with two coupled changes:

- **Flip the three `_F1_BROKEN_CASES` xfail entries to expected-to-pass** in `agentic_ops_v7/tests/test_path_resolver.py:494-536`. The xfail reasons explicitly cite "Needs B4 (screener over-flagging fix)" — under NF-burden scoring those cases pass without any screener-side change.

- **Walk all tied flows instead of using `display_order` as a final tie-break.** When the resolver's sort priorities 1–4 (score, transport-bucket-NF-in-flow, application-bucket-NF-in-flow, component-count-ASC) still leave two or more flows tied at the top, the resolver returns the *whole tied set* and Phase 0.6 walks each tied flow. The walker's per-hop attributions are the ground truth for which flow (if any) actually contains the fault — and when nothing in the evidence can rank the tied flows, the right answer is to let the deterministic prober disambiguate, not to fall back on an arbitrary authoring-order integer. `display_order` is removed from the scoring tuple entirely.

We deliberately *do not* extend this ADR to cover the fourth pinned-xfail case (`rtpengine_latency_injection`). That case has a different root cause (the screener has no rtpengine-direct latency feature, so rtpengine never gets flagged at all and no scoring mechanism can recover it). It needs a screener-feature ADR, not a resolver change.

## Context

### The failure mechanism — verified by manual scoring

`_score_flows` at `agentic_ops_v7/path_resolver.py:367-393` computes:

```
score = _COMPONENT_WEIGHT (=2) * component_score
      + _BUCKET_WEIGHTS["transport"] (=5)    * transport_flag_hits
      + _BUCKET_WEIGHTS["application"] (=3)  * application_flag_hits
      + _BUCKET_WEIGHTS["ambiguous"] (=1)    * ambiguous_flag_hits
```

Where:
- `component_score` = number of load-bearing NFs (the union of NFs the screener flagged, recovered via `_flag_nf_metric`) that appear in the flow's hop list.
- `*_flag_hits` = number of unique flagged metrics from that bucket whose token (short or `nf.metric` dotted form) appears in the flow's `observable_metrics` blob (`_count_unique_flag_hits`, `_flow_observable_metrics_blob`).

This formulation has a structural flaw: **the `*_flag_hits` term rewards flows whose `observable_metrics` blob — a free-text descriptor authored at flow-spec time — happens to contain a string match for a flagged metric**, even when the metric in question is on an NF that is NOT in the flow's hop list, or is in the hop list only as a downstream consumer.

Concrete trace on `run_20260521_021756_p_cscf_latency` (ground truth: pcscf fault):

The screener fired 9 flags, bucketed as:
- Transport (2): `upf.gtp_indatapktn3upf_per_ue` drop, `upf.gtp_outdatapktn3upf_per_ue` drop — both anomaly_score 4.59
- Application (1): `smf.bearers_per_ue` shift — anomaly_score 0.01 (negligible)
- Ambiguous (6): `icscf.cdp_replies_per_ue`, `icscf.rcv_requests_register_per_ue`, `scscf.cdp_replies_per_ue`, `scscf.rcv_requests_register_per_ue`, `pcscf.rcv_requests_register_per_ue`, `context.cx_active` — all anomaly_score 4.59 or 2.65

Load-bearing NF set: `{upf, smf, icscf, scscf, pcscf}` (context.cx_active has no NF).

Score computation for each flow:

| Flow | hop list ∩ load-bearing | component_score×2 | transport_hits×5 | ambiguous_hits×1 | **Total** |
|---|---|---:|---:|---:|---:|
| `data_pdu_session_user_traffic` | `{upf}` (1) | 2 | 10 (both UPF GTP flags' tokens appear in `core.upf.gtp_indatapktn3upf_per_ue` / `core.upf.gtp_outdatapktn3upf_per_ue` literal strings in the blob) | 0 (CSCF flag tokens don't appear in the data-plane blob) | **12** |
| `vonr_media` | `{upf}` (1) | 2 | 10 (same UPF GTP token match) | 0 | **12** |
| `ims_registration` | `{upf, icscf, scscf, pcscf}` (4) | 8 | 0 (UPF GTP tokens absent from the IMS blob, which lists `ims_usrloc_pcscf:registered_contacts` etc.) | 0 (the IMS flag tokens use `rcv_requests_register_per_ue` shape which doesn't match the `script:register_success` shape in the blob) | **8** |

`ims_registration` has **4× the load-bearing-NF coverage** but loses 8 to 12 because of the `+10` boost from the two UPF GTP transport flags whose tokens text-match the data-plane flow's blob.

The same exact 12-vs-8 split repeats verbatim for `run_20260521_022431_s_cscf_crash` and `run_20260521_130330_ims_network_partition`. Three of the four current wrong-flow cases share **identical** scoring breakdowns.

### Why the deferred fix (B4) is hard

The existing xfail reasons cite "Needs B4 (screener over-flagging fix when only IMS metrics are also moving)." But B4 is structurally hard:

1. **The screener uses ECOD (statistical), not rule-based.** Adding "only flag UPF when UPF is the cause" requires either (a) retraining the bucket model with conditional features that encode "IMS is also active," or (b) hand-authored suppression rules that the screener applies post-scoring. (a) is a model-engineering effort with its own correctness risk; (b) reintroduces the per-scenario hand-authoring B4 was supposed to avoid.
2. **The KB labels UPF GTP as `transport` correctly.** Those metrics DO move under N3 packet loss / UPF egress drops. The label isn't wrong; it's just under-specified for the downstream-symptom interpretation.
3. **The UPF GTP drops are real.** IMS signaling collapse genuinely causes call setup to fail and N3 traffic to dry up. The signal isn't spurious. Suppressing it would lose information.

The actual mistake isn't the flag firing — it's treating that flag as a fault *locator* rather than a downstream *symptom*. **The resolver is the right place to apply that distinction**, because it's the layer that converts "evidence about which NFs are moving" into "which flow to walk." That conversion is exactly where the upstream-vs-downstream distinction matters.

The operational lesson L09 already encodes this principle for the NA. The proposed fix lifts it from "LLM-prompt-readable lesson" to "deterministic scoring rule applied before the LLM ever sees the case."

### Scope of impact across the recent batch

| Run | Wrong-flow mechanism | Fixable by NF-burden scoring? | Score the run achieved despite wrong flow |
|---|---|---|---:|
| `run_20260521_021756_p_cscf_latency` | 12 vs 8 (UPF GTP boost) | ✓ yes | 100% (app-layer recovered) |
| `run_20260521_022431_s_cscf_crash` | 12 vs 8 (UPF GTP boost) | ✓ yes | 88% (app-layer recovered) |
| `run_20260521_130330_ims_network_partition` | 12 vs 8 (UPF GTP boost) | ✓ yes | 96% (app-layer recovered) |
| `run_20260521_033823_rtpengine_latency_injection` | Different — rtpengine never flagged | ✗ no (needs screener feature) | 75% (app-layer partially recovered) |

End-to-end scores aren't catastrophic because the LLM app-layer fallback recovers the diagnosis. But each wrong-flow run carries a real cost:

- **The walker's deterministic high-confidence localization is wasted.** The walker is the cheapest, most-trustworthy phase. When it walks the wrong flow, it null-localizes and the pipeline falls through to LLM reasoning that should have been confirmation rather than recovery.
- **~30k extra tokens per run.** The NA + Investigator phases consume substantially more tokens recovering the diagnosis than they would corroborating a walker-localized one.
- **The walker's "no drops attributed on data_pdu" output is mildly misleading to the NA.** It correctly tells the NA the data plane is clean, but it tells the NA *nothing* about whether pcscf is clean — because pcscf wasn't on the walked path. The NA has to derive "investigate pcscf" from scratch, with a missing-evidence shape that pre-prejudices it against IMS hypotheses.

## Design

### The new scoring formula

```python
# Per-flag NF-and-bucket vector — built once.
# Each flag contributes its bucket weight to the NF it's flagged on.
def _per_nf_flag_burden(c: SymptomClassification) -> dict[str, int]:
    """Map NF name → sum of bucket weights across that NF's flags.

    Each flag is resolved to (nf, metric_short) via `_flag_nf_metric` and
    contributes bucket_weight to nf's entry. Flags without a recoverable
    NF (e.g. `context.cx_active`) are skipped — they vote for no flow.
    """
    weights = {"transport": 5, "application": 3, "ambiguous": 1}
    burden: dict[str, int] = {}
    for bucket_name, flags in (
        ("transport",   c.transport_flags),
        ("application", c.application_flags),
        ("ambiguous",   c.ambiguous_flags),
    ):
        w = weights[bucket_name]
        for fb in flags:
            nf, _metric = _flag_nf_metric(fb)
            if nf:
                burden[nf] = burden.get(nf, 0) + w
    return burden


def _score_flows(
    flows: dict,
    load_bearing: set[str],
    classification: SymptomClassification,
) -> list[tuple[str, int, tuple]]:
    """Score every flow by:
       score = _COMPONENT_WEIGHT * component_score
             + sum over NFs in flow's hop list of nf_burden[nf]

    Returns a list of (flow_id, score, sort_key) sorted by sort_key DESC.
    Callers compare sort_keys to detect tied top candidates — flows
    sharing the top sort_key all get walked (see `resolve_path`).

    component_score is unchanged — it rewards flows whose hop list
    overlaps with the union of flagged NFs. The new NF-burden term
    weights that overlap by per-flag bucket weight, replacing the old
    observable_metrics-blob token-matching term.
    """
    _COMPONENT_WEIGHT = 2
    nf_burden = _per_nf_flag_burden(classification)

    scored: list[tuple[str, int, tuple]] = []
    for flow_id, flow_def in flows.items():
        components = _flow_components(flow_def)
        component_score = len(components & load_bearing)

        burden_in_flow = sum(nf_burden.get(nf, 0) for nf in components)

        score = _COMPONENT_WEIGHT * component_score + burden_in_flow
        if score == 0:
            continue

        # Tie-break vector — four priorities, all designed to be SEMANTIC.
        # `display_order` is gone: it was an arbitrary authoring-order
        # integer with no decision content. When priorities 1-4 still tie,
        # the walker walks ALL tied flows (see `resolve_path`) — letting
        # the deterministic prober disambiguate, not a flow author's
        # YAML field ordering.
        #
        #   1. score                            (descending)
        #   2. transport-bucket NF in flow      (descending; 1 > 0)
        #   3. application-bucket NF in flow    (descending; 1 > 0)
        #   4. component count                  (ascending; smaller = more specific)
        #
        # Bucket-affinity tie-breaks (2, 3) are reformulated against NF
        # hop-list membership (instead of blob token presence) but preserve
        # the same intent: prefer flows containing transport-flagged NFs
        # over application-flagged-only flows when the score ties.
        transport_in_flow = _flow_contains_bucket_nf(
            components, classification.transport_flags,
        )
        app_in_flow = _flow_contains_bucket_nf(
            components, classification.application_flags,
        )
        sort_key = (
            -score,                                  # 1. score DESC
            0 if transport_in_flow else 1,           # 2. transport-NF first
            0 if app_in_flow else 1,                 # 3. app-NF next
            len(components),                         # 4. fewer components first
        )
        scored.append((flow_id, score, sort_key))

    scored.sort(key=lambda t: t[2])
    return scored


def _flow_contains_bucket_nf(
    components: set[str], flag_buckets,
) -> bool:
    """True iff any flag in this bucket is on an NF that is in the flow's
    hop list. Used for the bucket-affinity tie-break."""
    for fb in flag_buckets:
        nf, _ = _flag_nf_metric(fb)
        if nf and nf in components:
            return True
    return False
```

Inside `resolve_path`, after calling `_score_flows`:

```python
def resolve_path(...) -> Optional[ResolvedPath]:
    ...
    candidates = _score_flows(flows, load_bearing, classification)
    if not candidates:
        return None

    top_sort_key = candidates[0][2]
    tied_flow_ids = [
        flow_id for flow_id, _score, sk in candidates if sk == top_sort_key
    ]
    chosen_flow_id = tied_flow_ids[0]   # any; Phase 0.6 walks all of them
    hops = _expand_flow_to_hops(flows[chosen_flow_id], nodes_topology)

    tied_alternative_hops = {
        fid: _expand_flow_to_hops(flows[fid], nodes_topology)
        for fid in tied_flow_ids[1:]
    }

    return ResolvedPath(
        flow_id=chosen_flow_id,
        hops=hops,
        candidate_flows=[(fid, s) for fid, s, _sk in candidates],
        tied_alternative_hops=tied_alternative_hops,   # new
        ...
    )
```

The two removed helpers — `_metrics_from_bucket`, `_count_unique_flag_hits`, `_flow_observable_metrics_blob`, `_load_bearing_metrics_by_bucket` — go away. `_load_bearing_components` and `_flag_nf_metric` are unchanged.

### Walking the tied set in Phase 0.6

`ResolvedPath` gains one new field — `tied_alternative_hops: dict[str, list[Hop]]` — keyed by flow_id. Empty dict means "no tie; the chosen flow is the unique winner."

Phase 0.6 (`_phase06_transport_layer_route` in `agentic_ops_v7/orchestrator.py`) invokes the walker once for the chosen flow and once per tied alternative, producing one `PathWalkReport` per walked flow. Synthesis aggregates:

| Walker outcomes across tied flows | Synthesis verdict |
|---|---|
| Exactly one flow's walk produces `drops_attributed_here` or `latency_at_hop` | `localized` at that hop. Other flows' null-localizations are recorded as "ruled out by walk" in the episode log. |
| Two or more flows attribute to *different* NFs | `compound` verdict — multi-fault path. Handled by the existing [`multi_fault_orchestration.md`](multi_fault_orchestration.md) machinery. |
| All flows null-localize | Same as today's null-localization: fall through to application-layer. The episode log records that N flows were walked and none attributed. |

This is a strict superset of today's behavior: when there's no tie (the common case), exactly one flow is walked and the behavior is identical to the pre-fix path. When there's a tie, the walker spends a small additional amount of probing budget per tied flow to produce a disambiguating result.

### Validation walkthrough — all four cases plus the regression-protector

The NF-burden of each scenario is computed once; the per-flow score is then the sum of in-flow burden plus the component-overlap term.

**1. p_cscf_latency (and identically: s_cscf_crash, ims_network_partition)**

NF-burden: `{upf: 2×5=10, icscf: 2×1=2, scscf: 2×1=2, pcscf: 1×1=1, smf: 1×3=3}`

| Flow | NFs in hop list ∩ flagged | component×2 | NF-burden in flow | **Total** |
|---|---|---:|---:|---:|
| `data_pdu_session_user_traffic` | `{upf}` | 2 | 10 | 12 |
| `vonr_media` | `{upf}` | 2 | 10 | 12 |
| `ims_registration` | `{upf, icscf, scscf, pcscf}` | 8 | 10+2+2+1=15 | **23** ✓ wins |

The IMS flow wins by 11 points. Tie-break never engages.

**2. rtpengine_latency_injection (still expected to mis-resolve under this fix; out of scope)**

The screener emits 0 flags on rtpengine for delay-only injection. NF-burden: `{upf: 5, icscf: 9, pcscf: 9, scscf: 9}` (one transport flag on upf, nine ambiguous flags spread across the CSCFs and pcscf dialogs counter).

| Flow | NFs in hop list ∩ flagged | component×2 | NF-burden in flow | **Total** |
|---|---|---:|---:|---:|
| `vonr_media` (the correct flow) | `{upf}` | 2 | 5 | 7 |
| `ims_registration` | `{upf, icscf, pcscf, scscf}` | 8 | 5+9+9+9=32 | 40 (wins, incorrect) |

The fix doesn't help here. This is the documented out-of-scope case — needs a screener-feature change to flag rtpengine-specific latency.

**3. Regression-protector: rtpengine_loss (single transport flag on `rtpengine.loss_ratio`)**

NF-burden: `{rtpengine: 5}`

| Flow | NFs in hop list ∩ flagged | component×2 | NF-burden in flow | **Total** |
|---|---|---:|---:|---:|
| `vonr_media` | `{rtpengine}` | 2 | 5 | **7** ✓ wins |
| `vonr_call_teardown` | ∅ (no rtpengine in hop list, CSCFs aren't flagged) | 0 | 0 | filtered (0) |
| `ims_registration` | ∅ | 0 | 0 | filtered (0) |

The original author's regression concern — `vonr_call_teardown` beating `vonr_media` on CSCF component overlap when component_weight was bumped — does not arise under NF-burden scoring. Flags on rtpengine vote *only* for flows containing rtpengine. **No regression.**

**4. Pure data-plane fault (e.g., `data_plane_degradation`, ground truth: UPF)**

NF-burden: `{upf: 5+5=10, rtpengine: 5}` (typical: two UPF GTP transport flags plus an rtpengine loss-ratio transport flag).

| Flow | NFs in hop list ∩ flagged | component×2 | NF-burden in flow | **Total** |
|---|---|---:|---:|---:|
| `vonr_media` | `{upf, rtpengine}` | 4 | 10+5=15 | **19** ✓ wins |
| `data_pdu_session_user_traffic` | `{upf}` | 2 | 10 | 12 |
| `ims_registration` | `{upf}` | 2 | 10 | 12 |

`vonr_media` correctly wins because the rtpengine flag votes for it specifically.

**5. Pure UPF fault with no rtpengine flag (e.g., `upf_bandwidth_cap`)**

NF-burden: `{upf: 5+5=10}`.

| Flow | NFs in hop list ∩ flagged | component×2 | NF-burden in flow | **Total** | tie-break |
|---|---|---:|---:|---:|---|
| `data_pdu_session_user_traffic` | `{upf}` | 2 | 10 | 12 | smallest hop count → **wins** |
| `vonr_media` | `{upf}` | 2 | 10 | 12 | next |
| `ims_registration` | `{upf}` | 2 | 10 | 12 | largest hop count → last |

Three-way tie broken by component-count-ASC (smaller, more specific flows win). `data_pdu_session_user_traffic` is the right answer for a pure data-plane PDU-session bandwidth cap. ✓

### What's lost: the `observable_metrics` blob signal

The removed `*_flag_hits` term was rewarding flows whose author explicitly listed a flagged metric in their `observable_metrics` blob. That had one useful job: capture the flow author's modeling intent ("for VoNR media, watch these specific metrics").

NF-burden scoring drops that signal. The argument for dropping it is that **the signal is largely redundant** with hop-list membership:

- A flow whose author would list `rtpengine.loss_ratio` in `observable_metrics` is a flow whose hop list contains `rtpengine`. NF-burden captures that via hop-list membership.
- A flow whose author would list `upf.gtp_indatapktn3upf_per_ue` is one whose hop list contains `upf`. Same coverage.

The cases where the observable_metrics signal added independent information are the very cases where it goes wrong: when a downstream-consumer NF's metric appears in a flow's blob (because the flow author thought "this metric is observable in this flow") even though the metric's movement actually indicates an upstream fault that's outside this flow's hop list. Removing the blob-matching is removing exactly the source of the failure mode.

If a future flow author wants to express "this metric is the highest-signal observable for THIS flow," the right home for that signal is the flow's tie-break metadata or a new `primary_observables` field — not as an additive score term that competes with hop-list membership. Out of scope for this ADR.

## Trade-offs and limitations

- **Tie-break behavior changes.** Today's bucket-affinity tie-breaks check whether *any* flag's token appears in the flow's blob. The proposed tie-break checks whether any flag's NF is in the flow's hop list. The intent is the same; the test surface differs. The xfail-flip in `test_path_resolver.py` will catch regressions on the bucket-affinity dimension.

- **Flags without a resolvable NF are silent voters.** `context.cx_active` and similar synthetic features that don't map to a single NF contribute nothing to NF-burden. They still contribute to `_load_bearing_components` only if they happen to resolve to an NF name (they don't, today). Concretely: `context.*` flags no longer add the +1 ambiguous boost they used to add via blob-token matching to flows whose blob mentions "cx" or similar. That's a small dampening on synthetic-feature signals; acceptable given those features are not designed as fault locators.

- **The fix doesn't unblock `rtpengine_latency_injection`.** Documented out of scope. The case needs a screener-feature change (an rtpengine-side latency-measurement feature) — the resolver cannot recover from "no flag on the faulted NF."

- **No protection against future screener over-flagging on new metric/NF combinations.** This ADR fixes the specific failure mode where downstream-consumer transport flags dominate the upstream IMS flow. If a future screener change creates a new over-flagging pattern on a different downstream signal, NF-burden scoring will mitigate it (because the upstream-NF flag burden still votes for the right flow) but won't eliminate it (the downstream-NF burden still counts). The mitigation is principled, not absolute.

- **The xfail re-baselining is a behavior change visible to anyone reading the test file.** It implies the original author's "needs B4" assertion was overcautious; we should be clear in the PR description that the fix is *resolver-side*, not *screener-side*, and that the choice of layer was a design decision that updates the work plan's B4 framing.

- **Walking N tied flows costs N walker invocations per chaos scenario when ties hit.** The walker is deterministic, no-LLM, and dominated by per-hop probing time (kernel-hop prober + docker-bridge prober). Each per-flow walk is currently ~5–10 seconds wall-clock against the live stack. So a 2-way tie adds ~5–10s to Phase 0.6; a 3-way tie adds ~15–20s. Acceptable: walker time is negligible compared to the LLM phases (NA + Investigators run 60–180s per scenario), and the alternative was either an arbitrary `display_order` pick (wrong with 50% probability when tied) or a tie-break heuristic we'd have to justify in a follow-up ADR. Empirically, ties past priority 4 are rare — most chaos scenarios resolve to a single winner. We can revisit if a chaos batch shows wide ties as the common case.

- **Compound verdicts can now originate from the walker, not only from app-layer reasoning.** If two tied flows attribute to two different NFs, Synthesis emits `compound` — which has a load-bearing existing prompt directive ([`multi_fault_orchestration.md`](multi_fault_orchestration.md)). That directive currently expects compound verdicts to be assembled from walker-localized + app-layer findings, not from two walker findings. Verify the prompt and the consistency guardrail still work cleanly when the compound's source is "walker + walker" instead of "walker + app-layer." Likely fine — `additional_root_causes` entries just need `evidence_source=walker` for both — but worth confirming in the implementation.

## Implementation outline

1. **`agentic_ops_v7/path_resolver.py`**
    - Add `_per_nf_flag_burden(c)` helper.
    - Add `_flow_contains_bucket_nf(components, bucket_flags)` helper.
    - Rewrite `_score_flows` per the formula above; change its signature from `(flows, load_bearing, metrics_by_bucket)` to `(flows, load_bearing, classification)`. Return shape changes from `list[(flow_id, score)]` to `list[(flow_id, score, sort_key)]` so callers can detect ties.
    - Remove `_metrics_from_bucket`, `_count_unique_flag_hits`, `_flow_observable_metrics_blob`, `_load_bearing_metrics_by_bucket`, `_load_bearing_metrics`.
    - Update `resolve_path` to detect tied top-scorers (matching `sort_key`), expand each tied alternative to a hop list, and stash them on the returned `ResolvedPath`.
2. **`agentic_ops_v7/path_resolver.py` — `ResolvedPath` shape**
    - Add `tied_alternative_hops: dict[str, list[Hop]]` field. Empty dict when there's a unique top scorer (the common case).
    - Episode-log serializer must surface this field so operators can see "the walker walked these N tied flows" in the rendered markdown.
3. **`agentic_ops_v7/orchestrator.py` — Phase 0.6**
    - `_phase06_transport_layer_route` currently walks one flow. Extend it to walk the chosen flow plus every entry in `resolved_path.tied_alternative_hops`, producing one `PathWalkReport` per walked flow. Tag each report with its flow_id.
    - Synthesis aggregates per the table above. Single-attribution → `localized`. Multi-attribution-different-NFs → `compound`. All-null → fall through to app-layer.
    - `short_circuit_on_localize` semantics under the tied-set case: short-circuit only if exactly one walker attributed; otherwise (compound or all-null) fall through. Document this in the routing comment.
4. **`agentic_ops_v7/tests/test_path_resolver.py`**
    - Flip the three xfail entries (`p_cscf_packet_loss` is already passing per F1; `p_cscf_latency`, `ims_network_partition` flip from xfail to expected-to-pass). The `rtpengine_latency_injection` entry stays xfail with its existing reason updated to reference this ADR.
    - Add new pin tests using the four 5/21-batch episode files referenced in this ADR, to lock in the post-fix behavior end-to-end.
    - Add a parameterized test that constructs a synthetic two-flow tie (identical NF coverage, identical scores) and asserts the resolver returns *both* flows with non-empty `tied_alternative_hops`.
5. **`agentic_chaos/recorder.py`**
    - Render `tied_alternative_hops` in the episode markdown's "Transport-Layer Route (Phase 0.6)" section: list the tied flow IDs that were walked alongside the chosen flow, and per-flow walker outcomes.
6. **No prompt or KB changes.** No schema migration. No RAG-corpus rebuild. The compound-verdict path is already in place from [`multi_fault_orchestration.md`](multi_fault_orchestration.md); verify the prompt directive doesn't assume "compound source is walker + app-layer specifically."
7. **Comment hygiene.** Remove the "cases the current weighting CANNOT fix" paragraph at `path_resolver.py:360-366` and the F1 weight-tuning comments at `path_resolver.py:344-358`; replace with a brief comment pointing to this ADR for the rationale of NF-burden scoring and walk-all-tied behavior.

## Validation target

- All 285 existing tests in the `agentic_ops_v7` suite pass.
- All 15 `test_screener_ecod` tests pass (unaffected).
- The three previously-xfail `_F1_BROKEN_CASES` flip to passing.
- A new parameterized test against the four 5/21 episode files (`run_20260521_021756`, `_022431`, `_130330`, `_033823`) confirms: the first three pick `ims_registration`; the fourth remains an xfail with its updated reason.
- A new synthetic-tie test asserts the resolver returns multiple tied flows in `tied_alternative_hops` when scoring is genuinely undifferentiable past priority 4.
- A new Phase 0.6 integration test feeds the resolver a tied set and asserts that the walker is invoked once per tied flow, and that Synthesis routes correctly under each of the three walker-outcome cases (single-attribution → localized, multi-attribution → compound, all-null → fall through).
- Re-run the four scenarios against a freshly-deployed stack to confirm end-to-end pickup of the right flow and walker localization at the correct NF. Expected token savings: ~30k per case for the three fixable ones.
- Spot-check: re-run one of the cases that's currently working cleanly (e.g., `data_plane_degradation` at 90% score) and confirm no regression — the chosen flow stays the same and `tied_alternative_hops` stays empty.

## Out of scope

- **Screener feature additions for rtpengine latency.** Needs a separate ADR.
- **The `observable_metrics` blob as a first-class scoring signal.** If we want to bring back flow-author-encoded "primary observables" for a flow, do it as a structured field with explicit semantics, not as a free-text additive score term. Out of scope.
- **Anomaly-score (severity) weighting of NF burden.** Currently each flag contributes the same bucket weight regardless of its individual anomaly_score. We could multiply by `flag.anomaly_score` to let higher-severity flags vote more strongly. Defer — the current bucket weighting is doing the heavy lifting; severity weighting is a refinement worth evaluating empirically after this fix lands.
- **Replacing the bucket weights with KB-driven NF-layer priors.** A future ADR could express "an IMS-layer NF with a flag has higher fault-locator prior than a CORE-layer NF whose metric also moved" via an explicit topological prior. That's a richer model; the current bucket weights are a reasonable proxy and let this ADR stay scoped.

## Open questions resolved

1. **Should `_flag_nf_metric` be relied upon to recover the NF for every flag, or should we also pull from `flag.component` directly when `kb_metric_id` is unset?** Today `_flag_nf_metric` already handles both paths (`kb_metric_id` preferred, `flag.component` fallback). The fix as drafted inherits that. Answer: leave as-is — the existing fallback is sufficient.

2. **Should the `score == 0` filter at the end of `_score_flows` stay?** Today any flow that didn't match the blob OR the components gets filtered out. Under NF-burden scoring, a flow scores zero only if its hop list has no overlap with any flagged NF — which is the right filter ("don't propose flows that can't possibly explain the evidence"). Answer: keep.

3. **Should the bucket-affinity tie-break re-check NF presence per bucket (as drafted), or check per-flow burden contribution from each bucket?** The latter is more discriminating (e.g., a flow with 10 transport-burden beats a flow with 5 transport-burden). The former is simpler and matches the existing intent. Answer: simpler.

4. **Should `display_order` be the final tie-break, or should we add anomaly_score weighting in?** Answer: **neither — walk all tied paths.** When priorities 1–4 (score, transport-bucket-NF-in-flow, application-bucket-NF-in-flow, component-count) still leave multiple flows tied at the top, the resolver returns the whole tied set and Phase 0.6 walks each one. The walker's per-hop attributions are the ground truth for which flow (if any) actually contains the fault. `display_order` was an arbitrary authoring-order integer with no decision content; replacing it with anomaly-score weighting would introduce a heuristic we'd have to justify against future failure modes. Letting the deterministic prober disambiguate is principled and turns a tie into evidence rather than a guess. The walker cost is bounded — see Trade-offs.

5. **Should we also remove the now-unused `_load_bearing_metrics` flat-union helper?** It's currently used only as a "thin compatibility wrapper" per its docstring. Nothing in the rewritten code path calls it. Answer: remove with the rest, keep `_load_bearing_components` only.
