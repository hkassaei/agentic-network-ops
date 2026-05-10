# Episode Report: Data Plane Degradation

**Agent:** v7  
**Episode ID:** ep_20260510_183211_data_plane_degradation  
**Date:** 2026-05-10T18:32:12.889496+00:00  
**Duration:** 159.5s  

---

## Scenario

**Category:** network  
**Blast radius:** single_nf  
**Description:** Inject 30% packet loss on the UPF. RTP media streams will degrade, voice quality drops. Tests whether the stack detects and reports data plane quality issues.

## Faults Injected

- **network_loss** on `upf` — {'loss_pct': 30}

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

**ANOMALY DETECTED.** Overall anomaly score: 51.07 (per-bucket threshold: 26.31, context bucket (0, 1), trained on 323 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following metrics deviate from their learned-healthy baseline. Treat each as a semantic observation (meaning + numbers), not a number alone — the KB's interpretation is the authoritative reading.

- **`derived.rtpengine_loss_ratio`** (RTPEngine RTCP-reported per-RR average packet loss) — current **14.75 packets_per_rr** vs learned baseline **0.00 packets_per_rr** (MEDIUM, spike)
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

- **`normalized.icscf.core:rcv_requests_invite_per_ue`** (SIP INVITE rate per UE at I-CSCF) — current **0.01 requests_per_second** vs learned baseline **0.00 requests_per_second** (MEDIUM, spike)
    - **What it measures:** Health of call-setup forwarding P-CSCF → I-CSCF. Partition signature
same as REGISTER rate.
    - **Spike means:** Forwarding failure.
    - **Healthy typical range:** 0–0.2 requests_per_second
    - **Healthy invariant:** Per-UE rate. Tracks pcscf.invite rate.

- **`normalized.pcscf.core:rcv_requests_invite_per_ue`** (SIP INVITE rate per UE at P-CSCF) — current **0.03 requests_per_second** vs learned baseline **0.00 requests_per_second** (MEDIUM, spike)
    - **What it measures:** Call attempt rate from registered UEs. Unlike REGISTER (periodic),
INVITEs only fire when UEs place calls. Zero is normal during
quiet periods; nonzero INVITE with zero dialogs is the signature
of call setup failure.
    - **Spike means:** Fewer call attempts.
    - **Healthy typical range:** 0–0.2 requests_per_second
    - **Healthy invariant:** Per-UE rate.

- **`normalized.scscf.core:rcv_requests_invite_per_ue`** (SIP INVITE rate per UE at S-CSCF) — current **0.03 requests_per_second** vs learned baseline **0.00 requests_per_second** (MEDIUM, spike)
    - **What it measures:** S-CSCF participation in call setup. Zero when calls aren't being
placed OR S-CSCF not receiving forwarded INVITEs.
    - **Spike means:** Upstream forwarding issue.
    - **Healthy typical range:** 0–0.2 requests_per_second
    - **Healthy invariant:** Per-UE rate.

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

- **`normalized.upf.gtp_indatapktn3upf_per_ue`** (GTP-U uplink rate per UE (N3)) — current **2.79 packets_per_second** vs learned baseline **1.45 packets_per_second** (LOW, spike)
    - **What it measures:** Health of the uplink user-plane path gNB → UPF. Drops to near-zero
during RAN or N3 outage; stays nonzero during active calls or data
sessions. Decoupled from SIP signaling (signals data plane, not
control plane).
    - **Spike means:** Either UEs not generating uplink traffic (no calls/data) or N3 path is degraded.
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

- **`normalized.icscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at I-CSCF) — current **0.03 requests_per_second** vs learned baseline **0.06 requests_per_second** (LOW, drop)
    - **What it measures:** Health of the P-CSCF → I-CSCF forwarding path (Mw interface). When
this drops to zero while P-CSCF REGISTER rate is still non-zero,
it's the SIGNATURE of an IMS partition between P-CSCF and I-CSCF.
    - **Drop means:** Either UEs not registering at all, or P-CSCF isolated from I-CSCF.
    - **Healthy typical range:** 0–0.5 requests_per_second
    - **Healthy invariant:** Per-UE rate. Should closely track ims.pcscf.rcv_requests_register_per_ue.

- **`normalized.pcscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at P-CSCF) — current **0.03 requests_per_second** vs learned baseline **0.06 requests_per_second** (LOW, drop)
    - **What it measures:** How actively UEs are refreshing their IMS registrations with the
P-CSCF. REGISTERs arrive periodically (re-registration timer) plus
at attach. Sustained zero means UEs cannot reach P-CSCF OR the
UE-to-network SIP path is broken.
    - **Drop means:** No REGISTERs flowing. Unusual unless UEs are all deregistered.
    - **Healthy typical range:** 0–0.5 requests_per_second
    - **Healthy invariant:** Per-UE rate — same value at any deployment scale.

- **`normalized.scscf.cdp_replies_per_ue`** (S-CSCF CDP Diameter replies per UE) — current **0.03 replies_per_second_per_ue** vs learned baseline **0.06 replies_per_second_per_ue** (LOW, drop)
    - **What it measures:** Active S-CSCF Diameter traffic with HSS. Near-zero when registrations idle OR HSS partition.
    - **Drop means:** No active S-CSCF Diameter exchanges (idle or partitioned).
    - **Healthy typical range:** 0–1 replies_per_second_per_ue
    - **Healthy invariant:** Per-UE rate; varies with registration/auth load.


## Symptom Classifier (Phase 0.5)

**Label:** `mixed`  
**Flag counts:** transport=2, application=2, ambiguous=6

### Transport-bucket flags (2)

| Metric | Direction | Score | KB-driven reason |
|---|---|---:|---|
| `derived.rtpengine_loss_ratio` | spike | 4.59 | KB-labeled transport: ims.rtpengine.loss_ratio (spike, score=4.59) |
| `normalized.upf.gtp_indatapktn3upf_per_ue` | spike | 3.90 | KB-labeled transport: core.upf.gtp_indatapktn3upf_per_ue (spike, score=3.90) |

### Application-bucket flags (2)

| Metric | Direction | Score | KB-driven reason |
|---|---|---:|---|
| `normalized.smf.bearers_per_ue` | drop | 4.59 | KB-labeled application: core.smf.bearers_per_ue (drop, score=4.59) |
| `normalized.smf.sessions_per_ue` | drop | 4.59 | KB-labeled application: core.smf.sessions_per_ue (drop, score=4.59) |

### Ambiguous-bucket flags (6)

| Metric | Direction | Score | KB-driven reason |
|---|---|---:|---|
| `normalized.icscf.core:rcv_requests_invite_per_ue` | spike | 4.59 | KB-labeled mixed: ims.icscf.rcv_requests_invite_per_ue (spike, score=4.59) |
| `normalized.pcscf.core:rcv_requests_invite_per_ue` | spike | 4.59 | KB-labeled mixed: ims.pcscf.rcv_requests_invite_per_ue (spike, score=4.59) |
| `normalized.scscf.core:rcv_requests_invite_per_ue` | spike | 4.59 | KB-labeled mixed: ims.scscf.rcv_requests_invite_per_ue (spike, score=4.59) |
| `normalized.icscf.core:rcv_requests_register_per_ue` | drop | 3.50 | KB-labeled mixed: ims.icscf.rcv_requests_register_per_ue (drop, score=3.50) |
| `normalized.pcscf.core:rcv_requests_register_per_ue` | drop | 3.50 | KB-labeled mixed: ims.pcscf.rcv_requests_register_per_ue (drop, score=3.50) |
| `normalized.scscf.cdp_replies_per_ue` | drop | 3.50 | KB-labeled mixed: ims.scscf.cdp_replies_per_ue (drop, score=3.50) |

**Rationale:**

```
label=mixed. Both transport-layer (2) and application-layer (2) signals are load-bearing. Path walk runs first; falls through to the application-layer pipeline if the walk produces null localization.

Transport signals: derived.rtpengine_loss_ratio (spike, score=4.59) — KB-labeled transport: ims.rtpengine.loss_ratio (spike, score=4.59); normalized.upf.gtp_indatapktn3upf_per_ue (spike, score=3.90) — KB-labeled transport: core.upf.gtp_indatapktn3upf_per_ue (spike, score=3.90)

Application signals: normalized.smf.bearers_per_ue (drop, score=4.59) — KB-labeled application: core.smf.bearers_per_ue (drop, score=4.59); normalized.smf.sessions_per_ue (drop, score=4.59) — KB-labeled application: core.smf.sessions_per_ue (drop, score=4.59)

Ambiguous signals: normalized.icscf.core:rcv_requests_invite_per_ue (spike, score=4.59) — KB-labeled mixed: ims.icscf.rcv_requests_invite_per_ue (spike, score=4.59); normalized.pcscf.core:rcv_requests_invite_per_ue (spike, score=4.59) — KB-labeled mixed: ims.pcscf.rcv_requests_invite_per_ue (spike, score=4.59); normalized.scscf.core:rcv_requests_invite_per_ue (spike, score=4.59) — KB-labeled mixed: ims.scscf.rcv_requests_invite_per_ue (spike, score=4.59); normalized.icscf.core:rcv_requests_register_per_ue (drop, score=3.50) — KB-labeled mixed: ims.icscf.rcv_requests_register_per_ue (drop, score=3.50); normalized.pcscf.core:rcv_requests_register_per_ue (drop, score=3.50) — KB-labeled mixed: ims.pcscf.rcv_requests_register_per_ue (drop, score=3.50) [+1 more]
```

## Transport-Layer Route (Phase 0.6)

### Resolver

**Flow:** `vonr_media` (VoNR Media Path)  
**Direction:** both  
**Hop count:** 13

**Candidates considered:**

| Flow | Score |
|---|---:|
| `vonr_media` ← chosen | 14 |
| `data_pdu_session_user_traffic` | 7 |
| `vonr_call_teardown` | 5 |
| `vonr_call_setup` | 5 |
| `ims_registration` | 4 |

**Rationale:**

```
Resolved transport path to flow `vonr_media` (score=14, 13 hops on the walk). Load-bearing components: ['icscf', 'pcscf', 'rtpengine', 'scscf', 'smf', 'upf']. Other candidate flows considered: data_pdu_session_user_traffic=7, vonr_call_teardown=5, vonr_call_setup=5, ims_registration=4.
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
| 4 | `upf` | container | `eth0` | `drops_attributed_here` | `qdisc_netem`: 303 dropped, 39.3% |
| 5 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 6 | `rtpengine` | container | `eth0` | `clean` | _clean_ |
| 7 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 8 | `upf` | container | `eth0` | `drops_attributed_here` | `qdisc_netem`: 303 dropped, 39.2% |
| 9 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 10 | `nr_gnb` | container | `eth0` | `clean` | _clean_ |
| 11 | `docker_open5gs_default` | docker_bridge | `br-docker_open5gs` | `clean` | _clean_ |
| 12 | `e2e_ue2` | container | `eth0` | `clean` | _clean_ |

### Localized Synthesis

**Verdict:** `localized`  
**Primary suspect NF:** `upf`  
**Confidence:** high

**Summary:** Transport-layer fault localized to `upf[eth0]`: `qdisc_netem` reports 303 packets dropped (39.3%).

**Recommendation:** Inspect the `tc` queueing discipline on the `upf` container's `eth0` interface by running: `docker exec upf tc -s qdisc show dev eth0`.


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

**Failure domain:** data_plane  
**Protocol impact:** GTP-U  
**Affected components:** upf  
**Severity:** degraded

## Agent Diagnosis

**Model:** v7-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 26.6s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: Transport-layer fault localized to `upf[eth0]`: `qdisc_netem` reports 303 packets dropped (39.3%).
> - **timeline**:
>     1. Path walk initiated for flow `vonr_media` based on transport and application-layer signals indicating packet loss.
>     2. At hop 5, packet drops (303 packets, 39.3%) were attributed to the `upf` container's `eth0` interface via a `qdisc_netem` counter.
>     3. Path walk completed, localizing the transport-layer fault with high confidence.
> - **root_cause**: Kernel-level packet drop on the upf container's `eth0` interface, caused by a `tc netem` queueing discipline configured to introduce packet loss. (primary_suspect_nf: `upf`)
> - **affected_components**:
>     - `upf`: Root Cause
> - **recommendation**: Inspect the `tc` queueing discipline on the `upf` container's `eth0` interface by running: `docker exec upf tc -s qdisc show dev eth0`.
> - **confidence**: high
> - **verdict_kind**: localized
> - **explanation**: The path walk localized the fault to a single hop. 
> 
> ### Path walk — flow `vonr_media`
> 
> Walked 13 hop(s) in topology order. First-attributed hop: **upf[eth0]** (drops_attributed_here).
> 
> | # | hop | kind | iface | prober | attribution |
> |---|-----|------|-------|--------|-------------|
> | 1 | e2e_ue1 | container | eth0 | KernelHopProber | clean |
> | 2 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 3 | nr_gnb | container | eth0 | KernelHopProber | clean |
> | 4 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 5 | upf | container | eth0 | KernelHopProber | drops_attributed_here (qdisc_netem, 303 dropped, 39.3%) 🎯 |
> | 6 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 7 | rtpengine | container | eth0 | KernelHopProber | clean |
> | 8 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 9 | upf | container | eth0 | KernelHopProber | drops_attributed_here (qdisc_netem, 303 dropped, 39.2%) |
> | 10 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 11 | nr_gnb | container | eth0 | KernelHopProber | clean |
> | 12 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 13 | e2e_ue2 | container | eth0 | KernelHopProber | clean |
> 
> ### Attribution (verbatim transport-layer counter excerpt)
> 
> ```
> upf[eth0] qdisc=netem, authored loss=30%: sent=771 dropped=303 (39.30%)
> ---tc -s qdisc show dev eth0---
> qdisc netem 8006: root refcnt 9 limit 1000 loss 30%
>  Sent 236364 bytes 771 pkt (dropped 303, overlimits 0 requeues 0) 
>  backlog 0b 0p requeues 0
> ```
> 
> ### Classifier rationale
> 
> label=mixed. Both transport-layer (2) and application-layer (2) signals are load-bearing. Path walk runs first; falls through to the application-layer pipeline if the walk produces null localization.
> 
> Transport signals: derived.rtpengine_loss_ratio (spike, score=4.59) — KB-labeled transport: ims.rtpengine.loss_ratio (spike, score=4.59); normalized.upf.gtp_indatapktn3upf_per_ue (spike, score=3.90) — KB-labeled transport: core.upf.gtp_indatapktn3upf_per_ue (spike, score=3.90)
> 
> Application signals: normalized.smf.bearers_per_ue (drop, score=4.59) — KB-labeled application: core.smf.bearers_per_ue (drop, score=4.59); normalized.smf.sessions_per_ue (drop, score=4.59) — KB-labeled application: core.smf.sessions_per_ue (drop, score=4.59)
> 
> Ambiguous signals: normalized.icscf.core:rcv_requests_invite_per_ue (spike, score=4.59) — KB-labeled mixed: ims.icscf.rcv_requests_invite_per_ue (spike, score=4.59); normalized.pcscf.core:rcv_requests_invite_per_ue (spike, score=4.59) — KB-labeled mixed: ims.pcscf.rcv_requests_invite_per_ue (spike, score=4.59); normalized.scscf.core:rcv_requests_invite_per_ue (spike, score=4.59) — KB-labeled mixed: ims.scscf.rcv_requests_invite_per_ue (spike, score=4.59); normalized.icscf.core:rcv_requests_register_per_ue (drop, score=3.50) — KB-labeled mixed: ims.icscf.rcv_requests_register_per_ue (drop, score=3.50); normalized.pcscf.core:rcv_requests_register_per_ue (drop, score=3.50) — KB-labeled mixed: ims.pcscf.rcv_requests_register_per_ue (drop, score=3.50) [+1 more]

### Scoring Breakdown

**Overall score: 100%**

**Scorer assessment:** The agent provided an excellent and highly accurate diagnosis, correctly identifying the root cause, affected component, severity, and fault type with strong evidence and appropriate confidence.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | Yes | The agent correctly identified 'packet drop' on the 'upf' component, which directly matches the simulated failure mode of 'packet loss on the UPF'. The agent even correctly identified the underlying mechanism ('tc netem'), which is an observable network artifact. |
| Component overlap | 100% | The agent correctly identified 'upf' as the 'Root Cause' in its affected_components list, matching the primary affected component in the simulated failure. |
| Severity correct | Yes | The agent reported '303 packets dropped (39.3%)', which accurately reflects a degradation (packet loss) rather than a complete outage, aligning with the simulated 30% packet loss and degraded voice quality. |
| Fault type identified | Yes | The agent explicitly identified 'packet drop' and 'packet loss' in its summary and root cause, which is the exact observable fault type simulated. |
| Layer accuracy | Yes | The 'Classifier rationale' section indicates the agent correctly associated 'upf' with the 'core' layer ('KB-labeled transport: core.upf...'), which matches the ground truth for the UPF component. |
| Confidence calibrated | Yes | The agent stated 'high' confidence, which is appropriate given the accuracy and detail of its diagnosis across all dimensions, including specific packet drop counts and the underlying mechanism. |

**Ranking position:** #1 — The agent provided a single, clear root cause, which was correct.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 5,278 |
| Output tokens | 1,784 |
| Thinking tokens | 1,081 |
| **Total tokens** | **8,143** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| SymptomClassifier | 0 | 0 | 0 |
| PathResolver | 0 | 0 | 0 |
| PathWalkInvestigator | 0 | 0 | 0 |
| SynthesisAgent | 8,143 | 0 | 1 |
| Phase 7 Synthesis (localized)__guardrail | 0 | 0 | 0 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 159.5s
