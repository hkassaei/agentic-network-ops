# Episode Report: gNB Radio Link Failure

**Agent:** v7  
**Episode ID:** ep_20260521_015903_gnb_radio_link_failure  
**Date:** 2026-05-21T01:59:04.886194+00:00  
**Duration:** 481.9s  

---

## Scenario

**Category:** container  
**Blast radius:** single_nf  
**Description:** Kill the gNB to simulate a radio link failure. All UEs lose 5G registration, PDU sessions drop, and IMS SIP unregisters.

## Faults Injected

- **container_kill** on `nr_gnb`

## Baseline (Pre-Fault)

Stack phase before injection: **ready**
All containers running at baseline.

## Fault Propagation Verification

**Verdict:** ✅ `confirmed`

- **Propagation window:** 125s (ObservationTrafficAgent drove traffic for this window; verifier added wait=0s on top)
- **Nodes with significant deltas:** 1
- **Nodes with any drift:** 2

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 12.08 (per-bucket threshold: 11.07, context bucket (0, 0), trained on 323 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following metrics deviate from their learned-healthy baseline. Treat each as a semantic observation (meaning + numbers), not a number alone — the KB's interpretation is the authoritative reading.

- **`normalized.smf.bearers_per_ue`** (Active QoS bearers per UE) — current **0.00 count** vs learned baseline **2.48 count** (MEDIUM, drop)
    - **What it measures:** Per-UE count of active QoS bearers. Baseline reflects default
bearers; increments during VoNR calls indicate dedicated voice
bearers being set up. Drop during an active call = dedicated
bearer torn down unexpectedly (voice will fail).
    - **Drop means:** Lost bearers. If sustained during a call, voice path is broken.
    - **Healthy typical range:** 2–3.5 count
    - **Healthy invariant:** At rest: equals configured default bearers (typically 2 per UE).
During active VoNR call: +1 per caller. The per-UE ratio is the
invariant; absolute count scales with UE pool.

- **`normalized.smf.sessions_per_ue`** (PDU sessions per attached UE) — current **0.00 count** vs learned baseline **2.00 count** (MEDIUM, drop)
    - **What it measures:** Ratio of established PDU sessions to RAN-attached UEs. Constant under
healthy operation (depends on configured APNs per UE). Drift means
some UEs lost or failed to establish their sessions — usually points
to SMF or UPF control-plane issues, since attachment (ran_ue) is
independent of session establishment.
    - **Drop means:** Some UEs have fewer PDU sessions than they should. Likely SMF or PFCP (N4) issues.
    - **Healthy typical range:** 1.9–2.1 count
    - **Healthy invariant:** Constant equal to configured_apns_per_ue (typically 2). Scale-independent.

- **`normalized.upf.gtp_indatapktn3upf_per_ue`** (GTP-U uplink rate per UE (N3)) — current **0.00 packets_per_second** vs learned baseline **1.45 packets_per_second** (LOW, drop)
    - **What it measures:** Health of the uplink user-plane path gNB → UPF. Drops to near-zero
during RAN or N3 outage; stays nonzero during active calls or data
sessions. Decoupled from SIP signaling (signals data plane, not
control plane).
    - **Drop means:** Data plane dead on uplink — UPF receiving no packets from gNB.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE rate. Constant regardless of UE pool size. Rises during
active VoNR calls (~100 pps for G.711 voice) and data transfer.
Uplink and downlink (gtp_outdatapktn3upf_per_ue) are independent
directions whose ratio is determined entirely by the current
traffic profile — voice with NULL_AUDIO (this testbed),
signaling-only chatter, idle UEs, and asymmetric data sessions
all produce persistent in/out imbalance under healthy operation.
Asymmetry between uplink and downlink rates is NEVER, by itself,
evidence of packet loss — not at any magnitude, not under any
traffic mix. To detect actual loss, use the methods listed in
stack rule `upf_counters_are_directional` (same-direction rate
comparison, RTCP loss_ratio at RTPEngine, or tc qdisc drop
counters). Rate-based metrics like this one are usually MORE
informative than the underlying lifetime cumulative counter for
current-state failure detection.

- **`normalized.upf.gtp_outdatapktn3upf_per_ue`** (GTP-U downlink rate per UE (N3)) — current **0.00 packets_per_second** vs learned baseline **1.45 packets_per_second** (LOW, drop)
    - **What it measures:** Health of the downlink user-plane path UPF → gNB. Drops to
near-zero during a downlink-affecting RAN, N3, or UPF
outage; stays nonzero during active calls or data sessions.
Decoupled from SIP signaling. The cross-direction
relationship to uplink (gtp_indatapktn3upf_per_ue) reflects
current traffic profile, NOT data-plane health — voice
with NULL_AUDIO, signaling-only chatter, idle UEs, and
asymmetric data sessions all produce persistent in/out
imbalance under healthy operation. Use this metric for
same-direction collapse detection (a known-active downlink
collapsing toward zero); do NOT infer loss from
uplink-vs-downlink asymmetry — see stack rule
upf_counters_are_directional.
    - **Drop means:** No traffic leaving UPF toward RAN.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE rate. Constant regardless of UE pool size. Uplink
(gtp_indatapktn3upf_per_ue) and downlink are independent
directions whose ratio is determined entirely by the current
traffic profile — voice with NULL_AUDIO (this testbed),
signaling-only chatter, idle UEs, and asymmetric data
sessions all produce persistent in/out imbalance under
healthy operation. Asymmetry between uplink and downlink
rates is NEVER, by itself, evidence of packet loss — not
at any magnitude, not under any traffic mix. To detect
actual loss, use the methods listed in stack rule
`upf_counters_are_directional` (same-direction rate
comparison, RTCP loss_ratio at RTPEngine, or tc qdisc drop
counters). Rate-based metrics like this one are usually
MORE informative than the underlying lifetime cumulative
counter for current-state failure detection.


## Symptom Classifier (Phase 0.5)

**Label:** `mixed`  
**Flag counts:** transport=2, application=2, ambiguous=0

### Transport-bucket flags (2)

| Metric | Direction | Score | KB-driven reason |
|---|---|---:|---|
| `normalized.upf.gtp_indatapktn3upf_per_ue` | drop | 3.56 | KB-labeled transport: core.upf.gtp_indatapktn3upf_per_ue (drop, score=3.56) |
| `normalized.upf.gtp_outdatapktn3upf_per_ue` | drop | 0.03 | KB-labeled transport: core.upf.gtp_outdatapktn3upf_per_ue (drop, score=0.03) |

### Application-bucket flags (2)

| Metric | Direction | Score | KB-driven reason |
|---|---|---:|---|
| `normalized.smf.bearers_per_ue` | drop | 4.25 | KB-labeled application: core.smf.bearers_per_ue (drop, score=4.25) |
| `normalized.smf.sessions_per_ue` | drop | 4.25 | KB-labeled application: core.smf.sessions_per_ue (drop, score=4.25) |

**Rationale:**

```
label=mixed. Both transport-layer (2) and application-layer (2) signals are load-bearing. Path walk runs first; falls through to the application-layer pipeline if the walk produces null localization.

Transport signals: normalized.upf.gtp_indatapktn3upf_per_ue (drop, score=3.56) — KB-labeled transport: core.upf.gtp_indatapktn3upf_per_ue (drop, score=3.56); normalized.upf.gtp_outdatapktn3upf_per_ue (drop, score=0.03) — KB-labeled transport: core.upf.gtp_outdatapktn3upf_per_ue (drop, score=0.03)

Application signals: normalized.smf.bearers_per_ue (drop, score=4.25) — KB-labeled application: core.smf.bearers_per_ue (drop, score=4.25); normalized.smf.sessions_per_ue (drop, score=4.25) — KB-labeled application: core.smf.sessions_per_ue (drop, score=4.25)
```

## Transport-Layer Route (Phase 0.6)

### Resolver

**Flow:** `data_pdu_session_user_traffic` (Data PDU Session — User Traffic)  
**Direction:** both  
**Hop count:** 11

**Candidates considered:**

| Flow | Score |
|---|---:|
| `data_pdu_session_user_traffic` ← chosen | 12 |
| `vonr_media` | 12 |
| `pdu_session_establishment` | 4 |
| `ue_deregistration` | 4 |
| `ims_registration` | 2 |

**Rationale:**

```
Resolved transport path to flow `data_pdu_session_user_traffic` (score=12, 11 hops on the walk). Load-bearing components: ['smf', 'upf']. Other candidate flows considered: vonr_media=12, pdu_session_establishment=4, ue_deregistration=4, ims_registration=2.
```

### Walker

**Status:** ✅ **localized**
**First attributed hop:** `nr_gnb[eth0]`
**Window:** 5s  
**Walked flow:** `data_pdu_session_user_traffic`

**Per-hop results:**

| # | Node | Kind | Iface | Attribution | Detail |
|---:|---|---|---|---|---|
| 0 | `e2e_ue1` | container | `eth0` | `clean` | _clean_ |
| 1 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 2 | 🎯 `nr_gnb` | container | `eth0` | `container_dead` | **container `exited`** |
| 3 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 4 | `upf` | container | `eth0` | `clean` | _clean_ |
| 5 | `internet` | external_network | `eth0` | `inconclusive` | _no_prober_registered_: "no HopProber registered for kind='external_network'; registered kinds: ['contai |
| 6 | `upf` | container | `eth0` | `clean` | _clean_ |
| 7 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 8 | `nr_gnb` | container | `eth0` | `container_dead` | **container `exited`** |
| 9 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 10 | `e2e_ue1` | container | `eth0` | `clean` | _clean_ |

### Localized Synthesis

**Verdict:** `localized`  
**Primary suspect NF:** `nr_gnb`  
**Confidence:** high

**Summary:** Transport-layer fault localized to nr_gnb[eth0]: container_dead reports the container status as exited.

**Recommendation:** Verify nr_gnb container status: `docker ps -a | grep nr_gnb`.


## Event Aggregation (Phase 1)

**4 events fired during the observation window:**

- `core.amf.gnb_association_drop` (source: `core.amf.gnb`, nf: `amf`, t=1779328862.8)  [current_value=0.0, prior_stable_value=1.0]
- `core.amf.ran_ue_sudden_drop` (source: `core.amf.ran_ue`, nf: `amf`, t=1779328862.8)  [current_value=0.0, prior_stable_value=2.0, delta_percent=-100.0]
- `core.amf.ran_ue_full_loss` (source: `core.amf.ran_ue`, nf: `amf`, t=1779328862.8)  [current_value=0.0, prior_stable_value=2.0]
- `core.smf.sessions_per_ue_drop` (source: `core.smf.sessions_per_ue`, nf: `smf`, t=1779328862.8)  [current_value=0.0, prior_stable_value=2.0, delta_percent=-100.0]

## Correlation Analysis (Phase 2)

**Correlation engine produced 5 ranked composite hypotheses from 4 fired events (showing top 3 of 5):**

### H1: Total RAN outage
  - primary_nf: amf
  - explanatory_fit: 0.50 (2/4 events)
  - testability: 2 (2 disambiguating metrics)
  - supporting events: `core.amf.gnb_association_drop`, `core.amf.ran_ue_full_loss`
  - probes to discriminate:
      - Check core.amf.ran_ue → Whether N2 is dead (both zero) vs. AMF-side attach issue (gnb>0, ran_ue=0)
      - Check core.amf.gnb → gNB-side failure (gnb=0) vs. AMF-side attach-processing issue (gnb>0 but ran_ue=0)

### H2: Total RAN failure — gNB + UEs both gone
  - primary_nf: amf
  - explanatory_fit: 0.50 (2/4 events)
  - testability: 2 (2 disambiguating metrics)
  - supporting events: `core.amf.gnb_association_drop`, `core.amf.ran_ue_full_loss`
  - probes to discriminate:
      - Check core.amf.ran_ue → Whether N2 is dead (both zero) vs. AMF-side attach issue (gnb>0, ran_ue=0)
      - Check core.amf.gnb → gNB-side failure (gnb=0) vs. AMF-side attach-processing issue (gnb>0 but ran_ue=0)

### H3: RAN failure confirmed — gNB down, UEs followed
  - primary_nf: amf
  - explanatory_fit: 0.50 (2/4 events)
  - testability: 2 (2 disambiguating metrics)
  - supporting events: `core.amf.gnb_association_drop`, `core.amf.ran_ue_sudden_drop`
  - probes to discriminate:
      - Check core.amf.gnb → gNB-side failure (gnb=0) vs. AMF-side attach-processing issue (gnb>0 but ran_ue=0)
      - Check core.amf.ran_ue → Whether N2 is dead (both zero) vs. AMF-side attach issue (gnb>0, ran_ue=0)


## RAG & Operational Lessons (Phase 2.5)

### RAG retrieval — prior similar episodes

**Status:** `hits` — hits=5, top_sim=0.84, top_case=v7/ep_20260510_123737_gnb_radio_link_failure
**Index:** `/home/ehoskas/agentic-network-ops/rag_index`  **Corpus size:** 102 cases
**Classifier label used in retrieval:** `mixed`
**Retrieval params:** k=5, min_similarity=0.4
**Hits (5):**

| Rank | Sim | Case ID | Scenario | Ground truth | Primary suspect | Score |
|---:|---:|---|---|---|---|---:|
| 0 | 84% | `v7/ep_20260510_123737_gnb_radio_link_failure` | gNB Radio Link Failure | `nr_gnb` | `nr_gnb` | 100% |
| 1 | 78% | `v6/ep_20260429_155442_gnb_radio_link_failure` | gNB Radio Link Failure | `nr_gnb` | `nr_gnb` | 100% |
| 2 | 66% | `v6/ep_20260420_040102_gnb_radio_link_failure` | gNB Radio Link Failure | `nr_gnb` | `?` | 100% |
| 3 | 66% | `v6/ep_20260420_041956_gnb_radio_link_failure` | gNB Radio Link Failure | `nr_gnb` | `?` | 100% |
| 4 | 66% | `v6/ep_20260423_193657_gnb_radio_link_failure` | gNB Radio Link Failure | `nr_gnb` | `nr_gnb` | 90% |

*Rendered block injected into the NA prompt's `{prior_similar_episodes}` placeholder: 3585 chars. Source paths are inlined in the block so the EvidenceValidator can audit any case the NA cites.*

### Operational lessons — hand-authored rules corpus

**Status:** `injected` — lessons=16, chars=15678
**Path:** `/home/ehoskas/agentic-network-ops/agentic_ops_common/rag/lessons.yaml`  **Count:** 16  **Block size:** 15678 chars
**Injected lesson IDs:** `L01`, `L02`, `L03`, `L04`, `L05`, `L06`, `L07`, `L08`, `L09`, `L10`, `L11`, `L12`, `L13`, `L14`, `L15`, `L16`

### NA citations of the injected content

**No verbatim citations.** The NA's output text did not reference any retrieved case_id or any injected lesson_id verbatim. This does NOT prove the NA ignored the injected content — the model may have absorbed the patterns implicitly — but it does mean no audit trail links the NA's reasoning back to a specific case or lesson.

## Network Analysis (Phase 3)

**Summary:** The complete loss of the N2 association (gnb=0) and attached UEs (ran_ue=0) at the AMF, combined with nr_gnb being absent from the running containers list, indicates nr_gnb is the primary fault source; the observed drops in UPF N3 GTP rates and SMF session metrics are explicitly demoted as secondary downstream consequences of this total RAN outage.

**Ranked hypotheses:**

- **`h1`** (fit=1.00, nf=nr_gnb, specificity=specific):
    - **Statement:** nr_gnb is the source of the N2 association loss, the ran_ue full loss, and the N3 data plane outage.
    - **Supporting events:** `core.amf.gnb_association_drop`, `core.amf.ran_ue_sudden_drop`, `core.amf.ran_ue_full_loss`, `core.smf.sessions_per_ue_drop`
    - **Falsification probes:**
        - Verify nr_gnb container status to determine if it is exited or entirely absent.
        - Check AMF logs (amf_gnb_remove) to confirm the SCTP association drop originated from the gNB side.
- **`h2`** (fit=0.60, nf=amf, specificity=moderate):
    - **Statement:** amf is the source of the N2 association drop and the resulting ran_ue deregistration.
    - **Supporting events:** `core.amf.gnb_association_drop`, `core.amf.ran_ue_sudden_drop`, `core.amf.ran_ue_full_loss`
    - **Falsification probes:**
        - Check AMF logs for an SCTP listener failure or an AMF process restart.
        - Check if gNB is actively trying to reconnect to AMF but being refused.


## Falsification Plans (Phase 4)

**2 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `nr_gnb`)

**Hypothesis:** nr_gnb is the source of the N2 association loss, the ran_ue full loss, and the N3 data plane outage.

**Probes (4):**
1. **`get_network_status`** — Check the container status of nr_gnb to determine if it is exited or absent.
    - *Expected if hypothesis holds:* The probe's reading shows the nr_gnb container is absent or has exited.
    - *Falsifying observation:* The probe's reading shows the nr_gnb container is running normally.
2. **`get_diagnostic_metrics`** — Check core.amf.gnb on the AMF to confirm the loss of N2 association.
    - *Expected if hypothesis holds:* The probe's reading shows core.amf.gnb is 0, consistent with a total gNB loss.
    - *Falsifying observation:* The probe's reading shows core.amf.gnb > 0, inconsistent with the gNB being completely down.
3. **`measure_rtt`** — measure_rtt from amf to the IP of nr_gnb.
    - *Expected if hypothesis holds:* The probe shows 100% packet loss, consistent with nr_gnb being unreachable or down.
    - *Falsifying observation:* The probe shows successful pings to nr_gnb.
4. **`measure_rtt`** — measure_rtt from upf to the IP of nr_gnb (a different path).
    - *Expected if hypothesis holds:* The probe shows 100% packet loss, confirming the hypothesized element (nr_gnb) is globally unreachable.
    - *Falsifying observation:* The probe shows successful pings, indicating the original reading was attributable to the amf-gnb path, not nr_gnb itself.

*Notes:* Using get_network_status to directly observe nr_gnb state as the primary indicator, and supplementing with transport reachability from two different sources.

### Plan for `h2` (target: `amf`)

**Hypothesis:** amf is the source of the N2 association drop and the resulting ran_ue deregistration.

**Probes (3):**
1. **`check_process_listeners`** — Check if amf is listening on the SCTP port for N2 (port 38412).
    - *Expected if hypothesis holds:* The probe's reading shows no listening socket on the SCTP port, consistent with the amf being unable to accept N2 connections.
    - *Falsifying observation:* The probe's reading shows an active listening socket on the SCTP port, inconsistent with amf being the source of a listening failure.
2. **`get_network_status`** — Check the uptime and state of the amf container.
    - *Expected if hypothesis holds:* The probe's reading shows the amf container has recently restarted or is exited.
    - *Falsifying observation:* The probe's reading shows the amf container is running and has stable uptime.
3. **`get_diagnostic_metrics`** — Check core.amf.gnb and core.amf.ran_ue metrics.
    - *Expected if hypothesis holds:* The probe's reading shows core.amf.gnb > 0 but core.amf.ran_ue = 0, consistent with the amf maintaining the association but failing to process UE attaches.
    - *Falsifying observation:* The probe's reading shows core.amf.gnb = 0, which points to a total N2 loss rather than a UE-specific processing issue on the amf.

*Notes:* Testing the AMF's ability to accept connections via listeners and verifying if it is a general N2 failure or a UE-attach failure using metric disambiguation.


## Parallel Investigators (Phase 5)

**2 sub-Investigator verdict(s):** **1 NOT_DISPROVEN**, **1 DISPROVEN**

### `h1` — ✅ **NOT_DISPROVEN**

**Hypothesis:** nr_gnb is the source of the N2 association loss, the ran_ue full loss, and the N3 data plane outage.

**Reasoning:** [Multi-shot consensus — both shots returned NOT_DISPROVEN.]

Shot 1: The get_network_status probe revealed that nr_gnb is completely absent from the network's known containers list. Further measure_rtt probes from both the AMF and UPF to nr_gnb failed with an 'Unknown target container' error, confirming the container is no longer resolvable or present on the network. Additionally, diagnostic metrics on the AMF anchored at the anomaly timestamp confirm the loss of N2 with gnb=0 and ran_ue=0. All evidence strongly supports the hypothesis that nr_gnb is entirely down or absent.

Shot 2: The get_network_status probe confirms that the nr_gnb container is entirely absent from the active deployment, which aligns with a total gNB failure. The diagnostic metrics at the time of the anomaly show AMF's gnb counter at 0, confirming the complete loss of the N2 association. The measure_rtt probes failed to execute because the nr_gnb container could not be resolved, further demonstrating that the container has been completely removed or destroyed rather than just experiencing network isolation.

**Probes executed (4):**
- **Check the container status of nr_gnb to determine if it is exited or absent.** ✓ CONSISTENT
    - *Tool:* `get_network_status()`
    - *Observation:* [EVIDENCE: get_network_status() -> ""down_or_absent": []"] and nr_gnb is completely missing from the "running" list.
    - *Comment:* The container nr_gnb is neither running nor in the down list, indicating it has been completely removed or is entirely absent.
- **Check core.amf.gnb on the AMF to confirm the loss of N2 association.** ✓ CONSISTENT
    - *Tool:* `get_diagnostic_metrics(at_time_ts=1779328783.2325494, nfs=["amf"])`
    - *Observation:* [EVIDENCE: get_diagnostic_metrics(at_time_ts=1779328783.2325494, nfs=["amf"]) -> "gnb = 0 [gauge, count]"]
    - *Comment:* AMF diagnostic metrics explicitly show 0 active gNB associations and 0 RAN UEs, directly confirming the N2 loss at the anomaly timestamp.
- **measure_rtt from amf to the IP of nr_gnb.** ✓ CONSISTENT
    - *Tool:* `measure_rtt("amf", "nr_gnb")`
    - *Observation:* [EVIDENCE: measure_rtt("amf", "nr_gnb") -> "Unknown target container 'nr_gnb'."]
    - *Comment:* The AMF cannot resolve or reach nr_gnb because the container is completely absent.
- **measure_rtt from upf to the IP of nr_gnb (a different path).** ✓ CONSISTENT
    - *Tool:* `measure_rtt("upf", "nr_gnb")`
    - *Observation:* [EVIDENCE: measure_rtt("upf", "nr_gnb") -> "Unknown target container 'nr_gnb'."]
    - *Comment:* The UPF cannot resolve or reach nr_gnb because the container is absent, confirming this is a global absence and not a path-specific transport issue.

### `h2` — ❌ **DISPROVEN**

**Hypothesis:** amf is the source of the N2 association drop and the resulting ran_ue deregistration.

**Reasoning:** [Multi-shot consensus — both shots returned DISPROVEN.]

Shot 1: The get_network_status probe shows the amf container is running normally, contradicting a crash. The diagnostic metrics show gnb = 0 rather than gnb > 0 and ran_ue = 0, indicating a complete N2 association loss, not an AMF-side UE processing failure. Finally, the total absence of the nr_gnb container from the network confirms that the N2 drop and deregistration originated from the RAN itself crashing or disappearing, exonerating the AMF.

Shot 2: The AMF container is still running normally, contradicting the expectation that an AMF crash caused the N2 drop. Diagnostic metrics show gnb = 0, which contradicts the plan's expectation (gnb > 0) that the AMF maintained the N2 association but failed to process UEs. Furthermore, the complete absence of nr_gnb in the running containers list confirms that the N2 drop was caused by the gNB being removed, not an AMF-originated fault.

**Probes executed (3):**
- **Check if amf is listening on the SCTP port for N2 (port 38412).** ~ AMBIGUOUS
    - *Tool:* `check_process_listeners("amf")`
    - *Observation:* [EVIDENCE: check_process_listeners("amf") -> "tcp   LISTEN 0      5        172.22.0.10:7777... udp   UNCONN 0      0         127.0.0.11:47362"]
    - *Comment:* The output does not explicitly show SCTP listening sockets (likely a limitation of the ss tool in the container), making this specific listening check ambiguous. However, the process is actively running and listening on its TCP/UDP ports.
- **Check the uptime and state of the amf container.** ✗ CONTRADICTS
    - *Tool:* `get_network_status()`
    - *Observation:* [EVIDENCE: get_network_status() -> ""amf": "running""] and [EVIDENCE: get_network_status() -> nr_gnb is entirely missing from the running list and containers dict]
    - *Comment:* The amf container is running normally, refuting the expectation that it crashed or restarted. Furthermore, the complete absence of the nr_gnb container identifies the true source of the failure.
- **Check core.amf.gnb and core.amf.ran_ue metrics.** ✗ CONTRADICTS
    - *Tool:* `get_diagnostic_metrics(at_time_ts=1779328783.23255, nfs=["amf"])`
    - *Observation:* [EVIDENCE: get_diagnostic_metrics(at_time_ts=1779328783.23255, nfs=["amf"]) -> "gnb = 0 [gauge, count]" and "ran_ue = 0 [gauge, count]"]
    - *Comment:* The observation matches the falsifying condition: gnb=0 indicates a total N2 loss, which contradicts the hypothesis's prediction of an AMF-side UE processing issue where gnb>0 and ran_ue=0.

**Alternative suspects:** nr_gnb


## Evidence Validation (Phase 6)

**Overall verdict:** clean
**Overall confidence:** high

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 10 | 4/4 | clean | high |
| `InvestigatorAgent_h2` | 9 | 4/4 | clean | high |


## Ground Truth

**Failure domain:** data_plane  
**Protocol impact:** GTP-U  
**Affected components:** nr_gnb  
**Severity:** degraded

## Agent Diagnosis

**Model:** v7-adk/pro=gemini-3.1-pro-preview+flash=gemini-3.5-flash  
**Time to diagnosis:** 344.2s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: Transport-layer fault localized to nr_gnb[eth0]: container_dead reports the container status as exited.
> - **timeline**:
>     1. Path walk started for flow data_pdu_session_user_traffic.
>     2. Fault attributed at hop nr_gnb (container_dead) due to an exited state.
>     3. Walk ended with complete localization at nr_gnb with high confidence.
> - **root_cause**: The nr_gnb container has exited or been removed entirely, terminating the N2 association and dropping all attached UEs along with the data plane. (primary_suspect_nf: `nr_gnb`)
> - **affected_components**:
>     - `nr_gnb`: Root Cause
> - **recommendation**: Verify nr_gnb container status: `docker ps -a | grep nr_gnb`.
> - **confidence**: high
> - **verdict_kind**: localized
> - **explanation**: | # | hop | kind | iface | prober | attribution |
> |---|-----|------|-------|--------|-------------|
> | 1 | e2e_ue1 | container | eth0 | KernelHopProber | clean |
> | 2 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 3 | nr_gnb | container | eth0 | KernelHopProber | container_dead (status=exited) 🎯 |
> | 4 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 5 | upf | container | eth0 | KernelHopProber | clean |
> | 6 | internet | external_network | eth0 | <unregistered> | inconclusive (no_prober_registered) |
> | 7 | upf | container | eth0 | KernelHopProber | clean |
> | 8 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 9 | nr_gnb | container | eth0 | KernelHopProber | container_dead (status=exited) |
> | 10 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 11 | e2e_ue1 | container | eth0 | KernelHopProber | clean |
> 
> ```
> container 'nr_gnb' state is `exited` (expected `running`); probes cannot execute against a non-running container
> ```
> 
> Classifier rationale: label=mixed. Both transport-layer (2) and application-layer (2) signals are load-bearing. Path walk runs first; falls through to the application-layer pipeline if the walk produces null localization. Transport signals: normalized.upf.gtp_indatapktn3upf_per_ue (drop, score=3.56) — KB-labeled transport: core.upf.gtp_indatapktn3upf_per_ue (drop, score=3.56); normalized.upf.gtp_outdatapktn3upf_per_ue (drop, score=0.03) — KB-labeled transport: core.upf.gtp_outdatapktn3upf_per_ue (drop, score=0.03). Application signals: normalized.smf.bearers_per_ue (drop, score=4.25) — KB-labeled application: core.smf.bearers_per_ue (drop, score=4.25); normalized.smf.sessions_per_ue (drop, score=4.25) — KB-labeled application: core.smf.sessions_per_ue (drop, score=4.25).

### Scoring Breakdown

**Overall score: 96%**

**Scorer assessment:** The agent accurately diagnosed the gNB failure with high confidence using direct container status evidence.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | Yes | The agent correctly identified that the nr_gnb container exited, terminating the N2 association and dropping UEs. |
| Component overlap | 80% | The agent correctly identified nr_gnb as the primary root cause component. |
| Severity correct | Yes | The agent correctly assessed a complete outage due to the exited container. |
| Fault type identified | Yes | The agent identified the container as dead/exited, representing an unreachable state. |
| Layer accuracy | Yes | No layer status information was provided, so no misattribution occurred. |
| Confidence calibrated | Yes | High confidence is justified given the direct container status evidence. |

**Ranking position:** #1 — The correct root cause was identified as the primary suspect.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 355,105 |
| Output tokens | 7,564 |
| Thinking tokens | 32,847 |
| **Total tokens** | **395,516** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| SymptomClassifier | 0 | 0 | 0 |
| PathResolver | 0 | 0 | 0 |
| PathWalkInvestigator | 0 | 0 | 0 |
| EventAggregator | 0 | 0 | 0 |
| CorrelationAnalyzer | 0 | 0 | 0 |
| RAGRetriever | 0 | 0 | 0 |
| OperationalLessons | 0 | 0 | 0 |
| NetworkAnalystAgent | 97,528 | 6 | 3 |
| Phase 3 NetworkAnalyst__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 10,942 | 0 | 1 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 24,303 | 2 | 2 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| InvestigatorAgent_h1 | 46,852 | 5 | 3 |
| InvestigatorAgent_h1 | 69,122 | 5 | 3 |
| InvestigatorAgent_h1__reconciliation | 0 | 0 | 0 |
| InvestigatorAgent_h2 | 57,752 | 5 | 4 |
| InvestigatorAgent_h2 | 72,676 | 4 | 3 |
| InvestigatorAgent_h2__reconciliation | 0 | 0 | 0 |
| Phase5FanOutAudit | 0 | 0 | 0 |
| Phase6.5CandidatePool | 0 | 0 | 0 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 16,341 | 0 | 1 |
| Phase 7 Synthesis__guardrail | 0 | 0 | 0 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 481.9s
