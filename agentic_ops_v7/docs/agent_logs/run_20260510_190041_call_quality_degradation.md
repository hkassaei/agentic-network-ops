# Episode Report: Call Quality Degradation

**Agent:** v7  
**Episode ID:** ep_20260510_185748_call_quality_degradation  
**Date:** 2026-05-10T18:57:49.585110+00:00  
**Duration:** 171.8s  

---

## Scenario

**Category:** network  
**Blast radius:** single_nf  
**Description:** Inject 30% packet loss on RTPEngine — the media relay for VoNR voice calls. RTP packets are dropped after RTPEngine receives them, degrading voice quality (MOS drop, jitter increase, audible artifacts). SIP signaling and 5G core are completely unaffected because they don't traverse RTPEngine. Tests whether the agent can diagnose a pure media-path fault without IMS signaling noise.

## Faults Injected

- **network_loss** on `rtpengine` — {'loss_pct': 30}

## Baseline (Pre-Fault)

Stack phase before injection: **ready**
All containers running at baseline.

## Fault Propagation Verification

**Verdict:** ✅ `confirmed`

- **Wait:** 0s
- **Actual elapsed:** 0.0s
- **Nodes with significant deltas:** 5
- **Nodes with any drift:** 5

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 49.82 (per-bucket threshold: 28.18, context bucket (1, 1), trained on 323 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following metrics deviate from their learned-healthy baseline. Treat each as a semantic observation (meaning + numbers), not a number alone — the KB's interpretation is the authoritative reading.

- **`derived.rtpengine_loss_ratio`** (RTPEngine RTCP-reported per-RR average packet loss) — current **50.04 packets_per_rr** vs learned baseline **0.00 packets_per_rr** (MEDIUM, spike)
    - **What it measures:** Live measure of media-plane packet loss as observed by
the far end of each call (via RTCP RRs) and aggregated
into per-RR mean. Zero during healthy traffic regardless
of call volume; rises when receivers report missing
packets. Magnitude scales with loss intensity, so a
higher value indicates more packets lost per report.
    - **Spike means:** Receivers are reporting packet loss back to rtpengine.
Could be loss on the rtpengine container's egress
(iptables / tc / interface congestion), loss anywhere
upstream of the receiver, or — with simultaneous UPF
counter degradation — loss on the N3 path.
    - **Healthy typical range:** 0–0.1 packets_per_rr

- **`derived.upf_activity_during_calls`** (UPF activity consistency with active dialogs) — current **0.03 ratio** vs learned baseline **0.54 ratio** (MEDIUM, drop)
    - **What it measures:** Cross-layer consistency check between IMS dialog state and UPF
throughput. A drop while dialogs_per_ue is non-zero is a
smoking-gun signal for media-plane failure independent of signaling.
    - **Drop means:** Active calls reported but no media flowing — media path broken (UPF, RTPEngine, or N3 packet loss).
    - **Healthy typical range:** 0.3–1 ratio
    - **Healthy invariant:** 1.0 when traffic fully follows active calls; 0.0 when signaling says active but data plane is silent.

- **`normalized.icscf.cdp_replies_per_ue`** (I-CSCF Diameter reply rate per UE) — current **0.08 replies_per_second_per_ue** vs learned baseline **0.03 replies_per_second_per_ue** (MEDIUM, spike)
    - **What it measures:** Liveness of the I-CSCF↔HSS Cx path. Drops to 0 when HSS is unreachable OR when no signaling is occurring at the I-CSCF (idle or upstream P-CSCF partitioned).
    - **Spike means:** Either HSS is unreachable or upstream signaling has stopped reaching I-CSCF.
    - **Healthy typical range:** 0–1 replies_per_second_per_ue

- **`normalized.icscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at I-CSCF) — current **0.12 requests_per_second** vs learned baseline **0.06 requests_per_second** (MEDIUM, spike)
    - **What it measures:** Health of the P-CSCF → I-CSCF forwarding path (Mw interface). When
this drops to zero while P-CSCF REGISTER rate is still non-zero,
it's the SIGNATURE of an IMS partition between P-CSCF and I-CSCF.
    - **Spike means:** Forwarding issue on the Mw interface, or P-CSCF stopped forwarding.
    - **Healthy typical range:** 0–0.5 requests_per_second
    - **Healthy invariant:** Per-UE rate. Should closely track ims.pcscf.rcv_requests_register_per_ue.

- **`normalized.pcscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at P-CSCF) — current **0.12 requests_per_second** vs learned baseline **0.06 requests_per_second** (MEDIUM, spike)
    - **What it measures:** How actively UEs are refreshing their IMS registrations with the
P-CSCF. REGISTERs arrive periodically (re-registration timer) plus
at attach. Sustained zero means UEs cannot reach P-CSCF OR the
UE-to-network SIP path is broken.
    - **Spike means:** Fewer REGISTERs than expected — UE connectivity or P-CSCF reachability issue.
    - **Healthy typical range:** 0–0.5 requests_per_second
    - **Healthy invariant:** Per-UE rate — same value at any deployment scale.

- **`normalized.scscf.cdp_replies_per_ue`** (S-CSCF CDP Diameter replies per UE) — current **0.12 replies_per_second_per_ue** vs learned baseline **0.06 replies_per_second_per_ue** (MEDIUM, spike)
    - **What it measures:** Active S-CSCF Diameter traffic with HSS. Near-zero when registrations idle OR HSS partition.
    - **Spike means:** Diameter peering loss with HSS.
    - **Healthy typical range:** 0–1 replies_per_second_per_ue
    - **Healthy invariant:** Per-UE rate; varies with registration/auth load.

- **`normalized.scscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at S-CSCF) — current **0.12 requests_per_second** vs learned baseline **0.06 requests_per_second** (MEDIUM, spike)
    - **What it measures:** Health of the I-CSCF → S-CSCF forwarding path. Drop to zero while
I-CSCF is receiving REGISTERs = S-CSCF-side issue (crashed, or
I-CSCF → S-CSCF path broken).
    - **Spike means:** I-CSCF not forwarding or S-CSCF not receiving.
    - **Healthy typical range:** 0–0.5 requests_per_second
    - **Healthy invariant:** Per-UE rate. Tracks icscf.register rate.

- **`normalized.smf.bearers_per_ue`** (Active QoS bearers per UE) — current **3.50 count** vs learned baseline **2.48 count** (MEDIUM, shift)
    - **What it measures:** Per-UE count of active QoS bearers. Baseline reflects default
bearers; increments during VoNR calls indicate dedicated voice
bearers being set up. Drop during an active call = dedicated
bearer torn down unexpectedly (voice will fail).
    - **Shift means:** Expected during VoNR calls (1 extra bearer per active call).
    - **Healthy typical range:** 2–3.5 count
    - **Healthy invariant:** At rest: equals configured default bearers (typically 2 per UE).
During active VoNR call: +1 per caller. The per-UE ratio is the
invariant; absolute count scales with UE pool.

- **`normalized.upf.gtp_indatapktn3upf_per_ue`** (GTP-U uplink rate per UE (N3)) — current **1.57 packets_per_second** vs learned baseline **1.45 packets_per_second** (MEDIUM, shift)
    - **What it measures:** Health of the uplink user-plane path gNB → UPF. Drops to near-zero
during RAN or N3 outage; stays nonzero during active calls or data
sessions. Decoupled from SIP signaling (signals data plane, not
control plane).
    - **Shift means:** Either UEs not generating uplink traffic (no calls/data) or N3 path is degraded.
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

- **`normalized.upf.gtp_outdatapktn3upf_per_ue`** (GTP-U downlink rate per UE (N3)) — current **1.25 packets_per_second** vs learned baseline **1.45 packets_per_second** (MEDIUM, shift)
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
    - **Shift means:** Downlink data plane degraded ON THIS DIRECTION SPECIFICALLY
— UPF is not forwarding toward gNB at the rate consistent
with the current traffic profile. To confirm loss (vs a
traffic-profile shift that just lowered downlink demand),
cross-check RTCP loss_ratio at RTPEngine and the same-
direction expected rate per stack rule
upf_counters_are_directional.
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
**Flag counts:** transport=4, application=1, ambiguous=5

### Transport-bucket flags (4)

| Metric | Direction | Score | KB-driven reason |
|---|---|---:|---|
| `derived.rtpengine_loss_ratio` | spike | 4.28 | KB-labeled transport: ims.rtpengine.loss_ratio (spike, score=4.28) |
| `derived.upf_activity_during_calls` | drop | 4.28 | KB-labeled transport: core.upf.activity_during_calls (drop, score=4.28) |
| `normalized.upf.gtp_indatapktn3upf_per_ue` | shift | 4.28 | KB-labeled transport: core.upf.gtp_indatapktn3upf_per_ue (shift, score=4.28) |
| `normalized.upf.gtp_outdatapktn3upf_per_ue` | shift | 4.28 | KB-labeled transport: core.upf.gtp_outdatapktn3upf_per_ue (shift, score=4.28) |

### Application-bucket flags (1)

| Metric | Direction | Score | KB-driven reason |
|---|---|---:|---|
| `normalized.smf.bearers_per_ue` | shift | 4.28 | KB-labeled application: core.smf.bearers_per_ue (shift, score=4.28) |

### Ambiguous-bucket flags (5)

| Metric | Direction | Score | KB-driven reason |
|---|---|---:|---|
| `normalized.icscf.cdp_replies_per_ue` | spike | 4.28 | KB-labeled mixed: ims.icscf.cdp_replies_per_ue (spike, score=4.28) |
| `normalized.icscf.core:rcv_requests_register_per_ue` | spike | 4.28 | KB-labeled mixed: ims.icscf.rcv_requests_register_per_ue (spike, score=4.28) |
| `normalized.pcscf.core:rcv_requests_register_per_ue` | spike | 4.28 | KB-labeled mixed: ims.pcscf.rcv_requests_register_per_ue (spike, score=4.28) |
| `normalized.scscf.cdp_replies_per_ue` | spike | 4.28 | KB-labeled mixed: ims.scscf.cdp_replies_per_ue (spike, score=4.28) |
| `normalized.scscf.core:rcv_requests_register_per_ue` | spike | 4.28 | KB-labeled mixed: ims.scscf.rcv_requests_register_per_ue (spike, score=4.28) |

**Rationale:**

```
label=mixed. Both transport-layer (4) and application-layer (1) signals are load-bearing. Path walk runs first; falls through to the application-layer pipeline if the walk produces null localization.

Transport signals: derived.rtpengine_loss_ratio (spike, score=4.28) — KB-labeled transport: ims.rtpengine.loss_ratio (spike, score=4.28); derived.upf_activity_during_calls (drop, score=4.28) — KB-labeled transport: core.upf.activity_during_calls (drop, score=4.28); normalized.upf.gtp_indatapktn3upf_per_ue (shift, score=4.28) — KB-labeled transport: core.upf.gtp_indatapktn3upf_per_ue (shift, score=4.28); normalized.upf.gtp_outdatapktn3upf_per_ue (shift, score=4.28) — KB-labeled transport: core.upf.gtp_outdatapktn3upf_per_ue (shift, score=4.28)

Application signals: normalized.smf.bearers_per_ue (shift, score=4.28) — KB-labeled application: core.smf.bearers_per_ue (shift, score=4.28)

Ambiguous signals: normalized.icscf.cdp_replies_per_ue (spike, score=4.28) — KB-labeled mixed: ims.icscf.cdp_replies_per_ue (spike, score=4.28); normalized.icscf.core:rcv_requests_register_per_ue (spike, score=4.28) — KB-labeled mixed: ims.icscf.rcv_requests_register_per_ue (spike, score=4.28); normalized.pcscf.core:rcv_requests_register_per_ue (spike, score=4.28) — KB-labeled mixed: ims.pcscf.rcv_requests_register_per_ue (spike, score=4.28); normalized.scscf.cdp_replies_per_ue (spike, score=4.28) — KB-labeled mixed: ims.scscf.cdp_replies_per_ue (spike, score=4.28); normalized.scscf.core:rcv_requests_register_per_ue (spike, score=4.28) — KB-labeled mixed: ims.scscf.rcv_requests_register_per_ue (spike, score=4.28)
```

## Transport-Layer Route (Phase 0.6)

### Resolver

**Flow:** `vonr_media` (VoNR Media Path)  
**Direction:** both  
**Hop count:** 13

**Candidates considered:**

| Flow | Score |
|---|---:|
| `vonr_media` ← chosen | 20 |
| `data_pdu_session_user_traffic` | 13 |
| `vonr_call_teardown` | 5 |
| `vonr_call_setup` | 5 |
| `ims_registration` | 4 |

**Rationale:**

```
Resolved transport path to flow `vonr_media` (score=20, 13 hops on the walk). Load-bearing components: ['icscf', 'pcscf', 'rtpengine', 'scscf', 'smf', 'upf']. Other candidate flows considered: data_pdu_session_user_traffic=13, vonr_call_teardown=5, vonr_call_setup=5, ims_registration=4.
```

### Walker

**Status:** ✅ **localized**
**First attributed hop:** `?[?]`
**Window:** 5s  
**Walked flow:** `vonr_media`

**Per-hop results:**

| # | Node | Kind | Iface | Attribution | Detail |
|---:|---|---|---|---|---|
| 0 | `e2e_ue1` | container | `eth0` | `clean` | _clean_ |
| 1 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 2 | `nr_gnb` | container | `eth0` | `clean` | _clean_ |
| 3 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 4 | `upf` | container | `eth0` | `clean` | _clean_ |
| 5 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 6 | `rtpengine` | container | `eth0` | `drops_attributed_here` | `qdisc_netem`: 295 dropped, 44.4% |
| 7 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 8 | `upf` | container | `eth0` | `clean` | _clean_ |
| 9 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 10 | `nr_gnb` | container | `eth0` | `clean` | _clean_ |
| 11 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 12 | `e2e_ue2` | container | `eth0` | `clean` | _clean_ |

### Localized Synthesis

**Verdict:** `localized`  
**Primary suspect NF:** `rtpengine`  
**Confidence:** high

**Summary:** Transport-layer fault localized to rtpengine[eth0]: qdisc_netem reports 295 packets dropped (44.4%).

**Recommendation:** Inspect the active queueing disciplines on the rtpengine container's eth0 interface by running `docker exec rtpengine tc -s qdisc show dev eth0`.


## Event Aggregation (Phase 1)

*No events aggregated — Phase 0.6 localized, app-layer pipeline did not run.*

## Correlation Analysis (Phase 2)

*No correlation analysis — Phase 0.6 localized, app-layer pipeline did not run.*

## Network Analysis (Phase 3)

*No NA output — Phase 0.6 localized, app-layer pipeline did not run.*

## Falsification Plans (Phase 4)

*No falsification plans — Phase 0.6 localized, app-layer pipeline did not run.*

## Parallel Investigators (Phase 5)

*No sub-Investigator output — Phase 0.6 localized, app-layer pipeline did not run.*

## Evidence Validation (Phase 6)

*No evidence validation — Phase 0.6 localized, app-layer pipeline did not run.*

## Ground Truth

**Failure domain:** ims_media  
**Protocol impact:** RTP  
**Affected components:** rtpengine  
**Severity:** degraded

## Agent Diagnosis

**Model:** v7-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 40.1s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: Transport-layer fault localized to rtpengine[eth0]: qdisc_netem reports 295 packets dropped (44.4%).
> - **timeline**:
>     1. Path walk initiated for transport flow `vonr_media` based on transport-layer signals.
>     2. Packet drops (295 dropped, 44.4%) attributed to hop 7, rtpengine[eth0], via qdisc_netem counters.
>     3. Path walk completed, localizing the fault with high confidence to a misconfigured network emulation rule.
> - **root_cause**: Kernel-level packet drop on the rtpengine container's `eth0` interface, caused by a `netem` queueing discipline configured for 30% packet loss, which resulted in an observed drop rate of 44.4%. (primary_suspect_nf: `rtpengine`)
> - **affected_components**:
>     - `rtpengine`: Root Cause
> - **recommendation**: Inspect the active queueing disciplines on the rtpengine container's eth0 interface by running `docker exec rtpengine tc -s qdisc show dev eth0`.
> - **confidence**: high
> - **verdict_kind**: localized
> - **explanation**: A deterministic path walk on the `vonr_media` flow localized the fault to hop 7, the `rtpengine` container. The walk attributed the issue to `drops_attributed_here` based on a `qdisc_netem` counter on the `eth0` interface, which showed 295 dropped packets (44.4% loss). This transport-layer analysis pinpointed the issue, overriding ambiguous application-layer signals. The classifier initiated the walk due to a spike in `rtpengine_loss_ratio`.
> 
> Verbatim counter evidence from `rtpengine[eth0]`:
> ```
> rtpengine[eth0] qdisc=netem, authored loss=30%: sent=665 dropped=295 (44.36%)
> ---tc -s qdisc show dev eth0---
> qdisc netem 8008: root refcnt 9 limit 1000 loss 30%
>  Sent 619708 bytes 665 pkt (dropped 295, overlimits 0 requeues 0) 
>  backlog 0b 0p requeues 0
> ```

### Scoring Breakdown

**Overall score: 100%**

**Scorer assessment:** The agent provided an exceptionally accurate and detailed diagnosis, correctly identifying the root cause, affected component, severity, and fault type with high confidence. It even pinpointed the specific mechanism of the packet loss.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | Yes | The agent correctly identified the root cause as kernel-level packet drops on the rtpengine container's eth0 interface, caused by a netem queueing discipline configured for packet loss. This directly matches the simulated failure mode of 30% packet loss on RTPEngine. |
| Component overlap | 100% | The agent correctly identified 'rtpengine' as the 'Root Cause' in its affected_components list, which is the primary affected component in the simulated failure. |
| Severity correct | Yes | The simulated failure was a 30% packet loss, leading to call quality degradation. The agent's diagnosis of 'packet drop' and '44.4% loss' accurately reflects a degradation, not a complete outage, aligning with the actual impact. |
| Fault type identified | Yes | The agent explicitly identified 'packet drop' and 'packet loss' as the fault type, which is precisely what was simulated and observable from the network. |
| Layer accuracy | Yes | No layer status information was provided in the agent's diagnosis, so no misattribution can be detected. Therefore, it is scored as true. |
| Confidence calibrated | Yes | The agent stated 'high' confidence, which is appropriate given the extreme accuracy and detail of its diagnosis, including identifying the specific mechanism (netem) and interface (eth0) responsible for the packet loss. |

**Ranking position:** #1 — The agent provided a single, clear root cause which was correct.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 5,309 |
| Output tokens | 800 |
| Thinking tokens | 3,824 |
| **Total tokens** | **9,933** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| SymptomClassifier | 0 | 0 | 0 |
| PathResolver | 0 | 0 | 0 |
| PathWalkInvestigator | 0 | 0 | 0 |
| SynthesisAgent | 9,933 | 0 | 1 |
| Phase 7 Synthesis (localized)__guardrail | 0 | 0 | 0 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 171.8s
