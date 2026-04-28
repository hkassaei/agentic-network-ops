## Batch run 2 results
 .venv/bin/python -m agentic_chaos list-episodes | head -n 13
  Agent   File                                               Duration   Faults   Score    Symptoms
  -----------------------------------------------------------------------------------------------
  v6      run_20260422_041716_cascading_ims_failure            333.5s  2        95%      True
  v6      run_20260422_040826_amf_restart_(upgrade_simulatio   313.8s  1        100%     True
  v6      run_20260422_040307_ims_network_partition            347.2s  2        20%      True
  v6      run_20260422_035715_dns_failure                      365.2s  1        90%      True
  v6      run_20260422_035105_mongodb_gone                     359.8s  1        40%      True
  v6      run_20260422_034500_call_quality_degradation         256.4s  1        15%      True
  v6      run_20260422_034039_data_plane_degradation           324.4s  1        26%      True
  v6      run_20260422_033509_hss_unresponsive                 367.4s  1        100%     True
  v6      run_20260422_032557_s_cscf_crash                     310.0s  1        100%     True
  v6      run_20260422_032042_p_cscf_latency                   336.4s  1        100%     True
  v6      run_20260422_031153_gnb_radio_link_failure           323.2s  1        60%      True

## Expected Improvements due to updates in ontology
Expected strong improvement

ims_network_partition (20 → 80-90% expected). Canonical case. Agent blamed HSS ("selectively failing to process I-CSCF requests"). ims_signaling_partition now has a cx_unaffected negative branch stating the
Cx path stays healthy — that's a direct rule-out of the wrong hypothesis. register_forward_fails_at_mw / invite_forward_fails_at_mw branches describe the actual mechanism. Negative branches + reverse-lookup
on register timing metrics should redirect NA.

mongodb_gone (40 → 80-90% expected). The original motivating case. Anomaly screener DID fire pcscf_sip_error_ratio=1.00. With the reverse-lookup tool, that metric now surfaces 4 branches across chains
including subscriber_data_store_unavailable.pcscf_n5_call_setup with mechanism and source_steps, plus the hss_cx_unaffected negative branch. The "blame HSS" pattern is directly suppressed.

data_plane_degradation (26 → 80%+ expected). Agent blamed SMF PFCP programming. UPF GTP-U per-UE drops fired as anomalies. Reverse-lookup on those metrics now surfaces n3_data_plane_degradation with
pfcp_unaffected and nf_control_plane_unaffected negative branches — direct rule-out of the SMF-PFCP hallucination.

Expected moderate improvement

gnb_radio_link_failure (60 → 80-90% expected). Agent wobbled between "AMF fault" and "partition." n2_connectivity_loss chain now has amf_unaffected and upf_unaffected negative branches that push the
diagnosis toward gNB rather than AMF. Reverse-lookup on ran_ue=0 / gnb=0 should surface these directly.

dns_failure (90 → 100% possible). Already high; dns_resolution_failure chain now has a data_plane_unaffected negative branch that cleans up the last 10%.

Uncertain / gated on tool invocation

call_quality_degradation (15%). The critical limitation: the anomaly screener detected nothing and the event aggregation fired nothing in this run. If NA starts cold with no fired events, the new
reverse-lookup tool isn't naturally triggered — the prompt rule for it reads "for any strongly-deviated metric," and here there were none surfaced to NA. So improvement hinges on whether NA's "no authored
branch matches → lower explanatory_fit" rule (principle #9) kicks in before it reaches for the stock "Diameter connectivity" prior it hallucinated before. Realistically: modest lift, maybe to 30-40%. The
deeper fix for this scenario is better metric_kb coverage of rtpengine so the screener catches the MOS drop.

ims_network_partition — same caveat. Also had zero anomalies fired in the Apr-22 run. NA went to "Diameter connectivity" from priors. My "strong improvement" prediction above assumes NA now reaches for
get_causal_chain_for_component(pcscf) when it forms a pcscf-implicating hypothesis. The prompt encourages this but doesn't mandate it. If NA skips the ontology tools because nothing fired, the lift is
smaller — maybe 50% instead of 90%.

Expected stable at ceiling

hss_unresponsive, s_cscf_crash, p_cscf_latency, amf_restart (100%). No regression expected; branch-first structure reinforces the reasoning paths that already worked.

cascading_ims_failure (95 → 100% possible). The new compound_error_surface branch explicitly labels the co-occurrence pattern. Minor lift.

Watch for

- A scenario where the agent picks the WRONG branch from a reverse-lookup match set (e.g., cdp:timeout surfaces 7 branches — if NA picks the wrong one without consulting discriminating_from, it could
regress). Check NA's supporting evidence cites the discriminating_from hint before committing.
- Prompts are longer now. If any 100%-scorer slips to 90%, that's the likely cause.

Net: I'd predict batch mean moves from ~71% (today) to ~82-85%, with the biggest jumps on ims_network_partition, mongodb_gone, and data_plane_degradation.

## Actual results
.venv/bin/python -m agentic_chaos list-episodes | head -n 13
Agent   File                                               Duration   Faults   Score    Symptoms
-----------------------------------------------------------------------------------------------
v6      run_20260423_204827_cascading_ims_failure            322.4s  2        100%     True
v6      run_20260423_203951_amf_restart_(upgrade_simulatio   293.3s  1        100%     True
v6      run_20260423_203452_ims_network_partition            296.0s  2        50%      True
v6      run_20260423_202950_dns_failure                      318.1s  1        100%     True
v6      run_20260423_202427_mongodb_gone                     316.9s  1        36%      True
v6      run_20260423_201905_call_quality_degradation         341.8s  1        15%      True
v6      run_20260423_201317_data_plane_degradation           347.6s  1        85%      True
v6      run_20260423_200724_hss_unresponsive                 396.2s  1        100%     True
v6      run_20260423_195611_s_cscf_crash                     343.6s  1        100%     True
v6      run_20260423_195022_p_cscf_latency                   290.3s  1        46%      True
v6      run_20260423_194244_gnb_radio_link_failure           343.4s  1        90%      True

## Prediction vs actual

Batch mean: 67.8% → 74.7% (+6.9). Directionally correct but diluted by two regressions I didn't predict.

┌────────────────────────┬───────┬───────────┬────────┬──────────────┐
│        Scenario        │ Prior │ Predicted │ Actual │   Verdict    │
├────────────────────────┼───────┼───────────┼────────┼──────────────┤
│ data_plane_degradation │ 26    │ 80%+      │ 85     │ ✓ hit        │
├────────────────────────┼───────┼───────────┼────────┼──────────────┤
│ ims_network_partition  │ 20    │ 80-90     │ 50     │ partial      │
├────────────────────────┼───────┼───────────┼────────┼──────────────┤
│ gnb_radio_link_failure │ 60    │ 80-90     │ 90     │ ✓ hit        │
├────────────────────────┼───────┼───────────┼────────┼──────────────┤
│ dns_failure            │ 90    │ 100       │ 100    │ ✓ hit        │
├────────────────────────┼───────┼───────────┼────────┼──────────────┤
│ cascading_ims_failure  │ 95    │ 100       │ 100    │ ✓ hit        │
├────────────────────────┼───────┼───────────┼────────┼──────────────┤
│ amf_restart            │ 100   │ 100       │ 100    │ ✓            │
├────────────────────────┼───────┼───────────┼────────┼──────────────┤
│ hss_unresponsive       │ 100   │ 100       │ 100    │ ✓            │
├────────────────────────┼───────┼───────────┼────────┼──────────────┤
│ s_cscf_crash           │ 100   │ 100       │ 100    │ ✓            │
├────────────────────────┼───────┼───────────┼────────┼──────────────┤
│ mongodb_gone           │ 40    │ 80-90     │ 36     │ ✗ regression │
├────────────────────────┼───────┼───────────┼────────┼──────────────┤
│ p_cscf_latency         │ 100   │ 100       │ 46     │ ✗ regression │
├────────────────────────┼───────┼───────────┼────────┼──────────────┤
│ call_quality           │ 15    │ 30-40     │ 15     │ ✗ flat       │
└────────────────────────┴───────┴───────────┴────────┴──────────────┘

Why each miss happened

1. p_cscf_latency (100 → 46): IG prompt bloat → empty structured output

The failing run shows Falsification Plans (Phase 4): *No output produced.* — same failure mode as the Flash-to-Pro incident we'd already fixed. All 3 NA hypotheses then came back INCONCLUSIVE from
investigators because they had no plan to execute. Same bug hit ims_network_partition. Two of 11 runs died here — directly caused by my additions to instruction_generator.md (rule #10 "Branch-anchored
probes" + the new "Flow and chain tools for plan construction" section). IG went from ~63 to 92 lines and apparently crossed a complexity threshold where even Pro flips into empty-schema emission on certain
inputs.

2. mongodb_gone (40 → 36): NA got it right, Investigator disproved the correct hypothesis

This is the more interesting failure. NA correctly generated h1 as mongo with fit=0.95 and a textbook-perfect statement citing the mongo → UDR → PCF → N5 → SIP 412 chain. The new ontology tooling worked. But
the Investigator DISPROVED h1 for the wrong reason:

- Probe: get_nf_metrics() on PCF.
- Observation: fivegs_pcffunction_pa_policyamassoreq = 40, _policyamassosucc = 40.
- Investigator's (wrong) conclusion: "100% success rate — PCF is functioning correctly."

Those are cumulative counters accumulated during the pre-fault healthy window, dominated by pre-fault traffic. The subscriber_data_store_unavailable.pcscf_n5_call_setup branch's observable_metrics explicitly
says "_req keeps incrementing, _succ does NOT increment" — a DELTA observation, not an absolute one. Principle #7 on the NA prompt ("Never compare two cumulative counters as a rate") is NOT on the
Investigator prompt. The Investigator happily used them as a rate.

So h1 got disproved, h3 ("P-CSCF HTTP client internal fault") survived by default, and the agent concluded P-CSCF was the root cause. The ontology work is being undone at Phase 5.

3. ims_network_partition (20 → 50): hit the same IG bug; NA direction also wobbled

Also had empty Phase 4 output. NA's hypotheses were also weaker than they should have been — h1 was "P-CSCF ↔ RTPEngine connectivity" (wrong), h2 was "HSS periodically unresponsive" (still the old HSS
hallucination). The reverse-lookup tool on cdp:timeout would have surfaced ims_signaling_partition.cx_unaffected as an authoritative rule-out for HSS. Either NA didn't call it or called it and ignored the
negative branch. Can't tell from the log because tool-call traces aren't fully rendered.

4. call_quality (15 → 15): metric_kb doesn't fire on rtpengine degradation

Anomaly screener detected NOTHING for this run. NA got symptoms from I-CSCF Diameter timeouts (noise from prior test traffic, I suspect) and pcscf connfail and went to HSS/PCF hypotheses. RTPEngine never
appeared in the hypothesis set. Reason: the migrated rtpengine metrics in metrics.yaml (mos, pps, loss, jitter) have expected/alarm_if/healthy.thresholds but no event_triggers — so the Phase 1 event
aggregator has nothing to emit for rtpengine. The screener's ML model isn't trained on rtpengine_mos as a salient feature, so it scores 0 for this scenario.

This isn't a causal-chain problem. It's a metric_kb coverage problem.

Improvements, priority-ordered

P0 — Restore IG below the complexity threshold

Immediate regression fix. Trim rule #10 from ~15 lines to 3-4. Merge its intent into the existing rule #9 since both are the same principle (anchor probes in authored ontology structure). Target: get IG back
to ≤ 70 lines. Expected recovery: p_cscf_latency back to 100, ims_network_partition to 80+. If the shorter prompt can't hold the branch guidance, move the detailed guidance into the prompts of downstream
agents (Investigator) who consume the plan — they have more prompt room.

P1 — Teach the Investigator the same cumulative-counter rule NA has

Add to investigator.md a rule mirroring NA principle #7: "A branch's observable_metrics that names two counters whose DIVERGENCE is the signal (e.g. policyamassoreq vs policyamassosucc) cannot be falsified
by reading their absolute equality on one snapshot. Cumulative counters accumulate pre-fault traffic. When a branch's mechanism describes a divergence post-fault, the probe must observe the post-fault delta
— check if both counters have changed between snapshots, or use a [derived] rate if available." Expected recovery: mongodb_gone back to 80%+, the correct h1 would no longer be disproved.

Related: we might also want a tool that returns recent-window deltas rather than just live values, so the investigator can verify divergence claims cheaply. Currently get_nf_metrics only returns lifetime
counters annotated with type; it doesn't compute deltas.

P2 — Add event_triggers for rtpengine quality metrics

Three triggers in metrics.yaml under the rtpengine NF:
- rtpengine_mos < 3.5 → ims.rtpengine.mos_degraded
- rtpengine_loss_pct > 5 → ims.rtpengine.packet_loss_high
- rtpengine_jitter > 20 → ims.rtpengine.jitter_high

Plus a new causal_chains.yaml entry rtpengine_media_degradation with branches vonr_mos_drop, rtp_jitter_noise, and explicit negatives sip_signaling_unaffected, n3_user_plane_unaffected. This directly
addresses call_quality.

P3 — Enforce negative-branch consultation in NA

The ims_network_partition NA still put pyhss in h2. With the cx_unaffected negative branch authored, the mechanism is there; the agent just didn't use it. Strengthen NA principle #9 from "check branches" to
"when a hypothesis implicates NF X, call find_chains_by_observable_metric on the triggering metrics; if a _unaffected branch explicitly rules out X, DROP that hypothesis and explain why." Make the
negative-branch handling mandatory rather than advisory.

P4 — Triangulation on symptom-clustered metrics

p_cscf_latency, even without the IG bug, had a bad NA direction: "P-CSCF connfail high → blame PCF." Principle #5 (triangulate directional probes) is the right rule but it's buried. Promote it into the
mandatory workflow: "Before naming any NF as the fault source based on a metric that measures X→Y interaction (like httpclient:connfail at X), you MUST name BOTH X and Y as candidates and defer to
triangulation." This reinforces principle #8 ("The observing NF can be the fault source").

Longer-term: observability of tool calls in the investigator

When a probe returns something like req=40, succ=40, the investigator should be able to ask compare_to_baseline(pcf, {policyamassoreq: 40, policyamassosucc: 40}) and get back that these don't move
independently in the window — but that tool is designed for absolute-value deviation, not deltas. A get_nf_metrics_delta(window_seconds=30) tool, if we had one, would let the investigator observe divergence
directly without LLM heuristics. Worth considering after P0-P3.

---
Recommended order of operations for you:
1. Fix IG prompt bloat (P0) — that alone probably recovers ~10 batch points.
2. Add the investigator cumulative-counter rule (P1) — recovers mongodb_gone.
3. Rerun the batch to confirm the regression is gone before layering P2-P4.
4. P2 (rtpengine event_triggers) is a discrete improvement that doesn't interact with the others; can land anytime.
5. P3 and P4 are prompt-only; add them together after P0-P2.