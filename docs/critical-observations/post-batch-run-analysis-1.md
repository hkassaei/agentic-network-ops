# Post-Batch-Run Analysis — v6 Across 11 Chaos Scenarios

**Date:** 2026-04-21
**Agent version:** v6 (ADK + gemini-2.5-flash/pro)
**Batch runner:** `scripts/run-all-chaos-scenarios.sh v6 --abort-on-unpropagated`
**Episode logs:** `agentic_ops_v6/docs/agent_logs/run_20260421_02285[6]…_0325[3]…`

---

## Topline

**Mean score: 83.6 %** across 11 scenarios — above the 80 % target.

| Score | Count | Scenarios |
|---|---|---|
| 100 % | 7 | gNB Radio Link Failure, P-CSCF Latency, S-CSCF Crash, HSS Unresponsive, DNS Failure, IMS Network Partition, AMF Restart |
| 90 %  | 2 | Call Quality Degradation, Cascading IMS Failure |
| 30 %  | 1 | MongoDB Gone |
| 10 %  | 1 | Data Plane Degradation |

Two scenarios previously in the 20–60 % range moved to 100 % / 90 % after the recent wave of plumbing work.

---

## What the recent plumbing work bought

- **P-CSCF Latency: 60 % → 100 %.** The `avg_register_time_ms` denominator fix (success → incoming-attempts), KB-backed anomaly flag enrichment, and NA principle #7 ("counters are not rates") worked together. NA named P-CSCF as the fault source; the Investigator triangulated via cross-path RTT; Synthesis held confidence appropriate to the evidence.
- **Call Quality Degradation: 25 % → 90 %.** Correct root cause on **RTPEngine** this time, not UPF. The single docked point was calibration — the diagnosis named a correct primary (RTP packet loss) but invented a secondary signaling fault that wasn't in the scenario. That's prompt-layer noise, not a model gap.
- **S-CSCF Crash, HSS Unresponsive, AMF Restart, IMS Network Partition, DNS Failure, gNB Radio Link Failure** — all 100 %. These were generally correct before the recent work and remain correct.

---

## The two scenarios still below target — and why they're interesting

### 1. Data Plane Degradation — 10 %

30 % packet loss injected on UPF. NA's Phase 3 framing:

> Summary: IMS registration is failing due to the HSS being unresponsive to Diameter requests, which prevents users from making VoNR calls and leads to an inactive data plane.

The screener flagged `normalized.upf.gtp_outdatapktn3upf_per_ue near-zero` and `bearers_per_ue shifted down`, and NA labeled the core as **yellow — symptom of IMS control plane failure**. None of the three hypotheses targeted UPF; all three targeted HSS / signaling. The 30 % loss was real, the screener saw it, NA's framing rule swallowed it.

**Root cause in the reasoning layer:** NA principle #4 ("Low activity ≠ local fault — upstream-starvation rule") is over-broad. It collapses *any* low UPF throughput into "upstream signaling never sent work." But UPF-with-established-bearers + asymmetric throughput (in ≈ N, out ≈ 0.7·N) is categorically different from UPF-with-no-sessions + both sides near zero. The rule needs to discriminate on **volume and symmetry of the delta**, not on absolute low values alone.

### 2. MongoDB Gone — 30 %

NA's Phase 3 actually nailed it:

> h1 (fit=0.90, nf=mongo): The HSS is unresponsive to the I-CSCF's Diameter UAR because its own backend database, MongoDB, is down.

But Investigator h1 **disproved it**. The decisive probe was `query_subscriber("001011234567891")`, which returned `core_5g: null` ("NOT FOUND in Open5GS MongoDB") *plus* `ims_subscriber: {...}` (found). The Investigator read the split as "IMS HSS uses a separate database from the 5G core's mongo" — and in our stack that's partly true (pyhss uses MySQL for subscriber data; mongo is Open5GS CN's store). The 5G-side subscriber lookup fails, the IMS-side lookup succeeds, so the "HSS depends on mongo" hypothesis *appears* disproven from the evidence.

The simulated failure mode does cause visible SIP 4xx via some mongo-dependent path, but the ontology doesn't encode which NFs beyond the 5G core actually depend on mongo. **The agent reasoned correctly from evidence; the ontology was too coarse.**

The fix is in `network_ontology/data/components.yaml` — enumerate mongo's dependents accurately so the Investigator's "HSS uses a different DB" conclusion is gated on the correct dependency graph.

---

## Secondary observations

- **`measure_rtt` triangulation is failing silently** on pyhss and occasionally on UPF because `ping` isn't installed in those containers. Shows up in 4+ runs as AMBIGUOUS reverse-RTT probes. Not scoring-relevant today but eats probe budget. A one-line Dockerfile add (or a `nc`/python-ICMP fallback in the tool) closes it.
- **Cascading IMS Failure (90 %)** — correctly identified HSS-down as the primary cause; missed the *additional* S-CSCF latency in the same compound fault. Medium confidence appropriately flagged the incomplete diagnosis. This is the ideal behavior for a compound fault the correlation engine isn't yet taught to compose.
- **Hallucinated secondary faults** appear in 3 runs (call_quality, ims_partition, data_plane). All three invent a "plausible" signaling issue adjacent to the real fault. Low/medium confidence usually catches it in scoring, but it adds noise in the diagnosis text and alternative_suspects lists.

---

## Where to push next

In priority order of expected score lift:

1. **Tighten NA principle #4 (activity-vs-drops) with a volume + symmetry gate.** Upstream starvation looks like *both* in and out low with low absolute volume; local drop looks like *in high / out low*. The current rule only tests absolute low values. Would flip `data_plane_degradation` without risking the P-CSCF-latency-style upstream-starvation case.
2. **Expand `components.yaml` dependency edges** so mongo's dependents (and any other cross-layer DB / cache / auth dependencies) are enumerated. Would flip `mongodb_gone` without hand-crafting scenario-specific rules.
3. **Hallucination guardrail in Synthesis** — forbid adding to `root_cause` / `affected_components` any NF that isn't anchored to a fired event or a cited tool observation. Would clean up the three runs that contain invented secondary faults.
4. **Install `ping` in pyhss + upf** (1-line stack-side Dockerfile add). Removes the silent AMBIGUOUS probes that currently cost ~1 probe per triangulation attempt against those NFs.

---

## Score dashboard

```
Agent   Scenario                                             Duration   Score
-----   --------                                             --------   -----
v6      gNB Radio Link Failure                               293.7s     100%
v6      P-CSCF Latency                                       279.8s     100%
v6      S-CSCF Crash                                         249.0s     100%
v6      HSS Unresponsive                                     308.8s     100%
v6      Data Plane Degradation                               265.1s      10%
v6      Call Quality Degradation                             298.2s      90%
v6      MongoDB Gone                                         302.7s      30%
v6      DNS Failure                                          262.2s     100%
v6      IMS Network Partition                                314.6s     100%
v6      AMF Restart (Upgrade Simulation)                     259.0s     100%
v6      Cascading IMS Failure                                268.0s      90%
-----   --------                                             --------   -----
                                                     Mean              83.6%
```
