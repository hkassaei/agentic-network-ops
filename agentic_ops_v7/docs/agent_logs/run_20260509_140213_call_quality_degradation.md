# Episode Report: Call Quality Degradation

**Agent:** v7  
**Episode ID:** ep_20260509_135947_call_quality_degradation  
**Date:** 2026-05-09T13:59:48.410398+00:00  
**Duration:** 144.5s  

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
- **Nodes with significant deltas:** 4
- **Nodes with any drift:** 5

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 56.93 (per-bucket threshold: 28.18, context bucket (1, 1), trained on 323 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following metrics deviate from their learned-healthy baseline. Treat each as a semantic observation (meaning + numbers), not a number alone — the KB's interpretation is the authoritative reading.

- **`derived.rtpengine_loss_ratio`** (RTPEngine RTCP-reported per-RR average packet loss) — current **24.30 packets_per_rr** vs learned baseline **0.00 packets_per_rr** (MEDIUM, spike)
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

- **`normalized.icscf.cdp_replies_per_ue`** (I-CSCF Diameter reply rate per UE) — current **0.09 replies_per_second_per_ue** vs learned baseline **0.03 replies_per_second_per_ue** (MEDIUM, spike)
    - **What it measures:** Liveness of the I-CSCF↔HSS Cx path. Drops to 0 when HSS is unreachable OR when no signaling is occurring at the I-CSCF (idle or upstream P-CSCF partitioned).
    - **Spike means:** Either HSS is unreachable or upstream signaling has stopped reaching I-CSCF.
    - **Healthy typical range:** 0–1 replies_per_second_per_ue

- **`normalized.icscf.core:rcv_requests_invite_per_ue`** (SIP INVITE rate per UE at I-CSCF) — current **0.03 requests_per_second** vs learned baseline **0.00 requests_per_second** (MEDIUM, spike)
    - **What it measures:** Health of call-setup forwarding P-CSCF → I-CSCF. Partition signature
same as REGISTER rate.
    - **Spike means:** Forwarding failure.
    - **Healthy typical range:** 0–0.2 requests_per_second
    - **Healthy invariant:** Per-UE rate. Tracks pcscf.invite rate.

- **`normalized.icscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at I-CSCF) — current **0.12 requests_per_second** vs learned baseline **0.06 requests_per_second** (MEDIUM, spike)
    - **What it measures:** Health of the P-CSCF → I-CSCF forwarding path (Mw interface). When
this drops to zero while P-CSCF REGISTER rate is still non-zero,
it's the SIGNATURE of an IMS partition between P-CSCF and I-CSCF.
    - **Spike means:** Forwarding issue on the Mw interface, or P-CSCF stopped forwarding.
    - **Healthy typical range:** 0–0.5 requests_per_second
    - **Healthy invariant:** Per-UE rate. Should closely track ims.pcscf.rcv_requests_register_per_ue.

- **`normalized.pcscf.core:rcv_requests_invite_per_ue`** (SIP INVITE rate per UE at P-CSCF) — current **0.06 requests_per_second** vs learned baseline **0.00 requests_per_second** (MEDIUM, spike)
    - **What it measures:** Call attempt rate from registered UEs. Unlike REGISTER (periodic),
INVITEs only fire when UEs place calls. Zero is normal during
quiet periods; nonzero INVITE with zero dialogs is the signature
of call setup failure.
    - **Spike means:** Fewer call attempts.
    - **Healthy typical range:** 0–0.2 requests_per_second
    - **Healthy invariant:** Per-UE rate.

- **`normalized.pcscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at P-CSCF) — current **0.12 requests_per_second** vs learned baseline **0.06 requests_per_second** (MEDIUM, spike)
    - **What it measures:** How actively UEs are refreshing their IMS registrations with the
P-CSCF. REGISTERs arrive periodically (re-registration timer) plus
at attach. Sustained zero means UEs cannot reach P-CSCF OR the
UE-to-network SIP path is broken.
    - **Spike means:** Fewer REGISTERs than expected — UE connectivity or P-CSCF reachability issue.
    - **Healthy typical range:** 0–0.5 requests_per_second
    - **Healthy invariant:** Per-UE rate — same value at any deployment scale.

- **`normalized.pcscf.dialogs_per_ue`** (Active SIP dialogs per registered UE at P-CSCF) — current **2.00 count** vs learned baseline **0.48 count** (MEDIUM, spike)
    - **What it measures:** How many calls per user are currently in progress at the P-CSCF.
Going to zero from a non-zero baseline means calls have ended
(normal) OR call setup is failing system-wide (degradation).
Together with rcv_requests_* it discriminates the two.
    - **Spike means:** Calls ending or setup failing.
    - **Healthy typical range:** 0–1 count
    - **Healthy invariant:** Per-UE — scale-independent. 0 at rest, ~1 per active VoNR call.

- **`normalized.scscf.cdp_replies_per_ue`** (S-CSCF CDP Diameter replies per UE) — current **0.12 replies_per_second_per_ue** vs learned baseline **0.06 replies_per_second_per_ue** (MEDIUM, spike)
    - **What it measures:** Active S-CSCF Diameter traffic with HSS. Near-zero when registrations idle OR HSS partition.
    - **Spike means:** Diameter peering loss with HSS.
    - **Healthy typical range:** 0–1 replies_per_second_per_ue
    - **Healthy invariant:** Per-UE rate; varies with registration/auth load.

- **`normalized.scscf.core:rcv_requests_invite_per_ue`** (SIP INVITE rate per UE at S-CSCF) — current **0.06 requests_per_second** vs learned baseline **0.00 requests_per_second** (MEDIUM, spike)
    - **What it measures:** S-CSCF participation in call setup. Zero when calls aren't being
placed OR S-CSCF not receiving forwarded INVITEs.
    - **Spike means:** Upstream forwarding issue.
    - **Healthy typical range:** 0–0.2 requests_per_second
    - **Healthy invariant:** Per-UE rate.

- **`normalized.scscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at S-CSCF) — current **0.12 requests_per_second** vs learned baseline **0.06 requests_per_second** (MEDIUM, spike)
    - **What it measures:** Health of the I-CSCF → S-CSCF forwarding path. Drop to zero while
I-CSCF is receiving REGISTERs = S-CSCF-side issue (crashed, or
I-CSCF → S-CSCF path broken).
    - **Spike means:** I-CSCF not forwarding or S-CSCF not receiving.
    - **Healthy typical range:** 0–0.5 requests_per_second
    - **Healthy invariant:** Per-UE rate. Tracks icscf.register rate.


## Symptom Classifier (Phase 0.5)

**Label:** `transport_layer`  
**Flag counts:** transport=1, application=0, ambiguous=9

### Transport-bucket flags (1)

| Metric | Direction | Score | KB-driven reason |
|---|---|---:|---|
| `derived.rtpengine_loss_ratio` | spike | 4.28 | KB-labeled transport: ims.rtpengine.loss_ratio (spike, score=4.28) |

### Ambiguous-bucket flags (9)

| Metric | Direction | Score | KB-driven reason |
|---|---|---:|---|
| `normalized.icscf.cdp_replies_per_ue` | spike | 4.28 | KB-labeled mixed: ims.icscf.cdp_replies_per_ue (spike, score=4.28) |
| `normalized.icscf.core:rcv_requests_invite_per_ue` | spike | 4.28 | KB-labeled mixed: ims.icscf.rcv_requests_invite_per_ue (spike, score=4.28) |
| `normalized.icscf.core:rcv_requests_register_per_ue` | spike | 4.28 | KB-labeled mixed: ims.icscf.rcv_requests_register_per_ue (spike, score=4.28) |
| `normalized.pcscf.core:rcv_requests_invite_per_ue` | spike | 4.28 | KB-labeled mixed: ims.pcscf.rcv_requests_invite_per_ue (spike, score=4.28) |
| `normalized.pcscf.core:rcv_requests_register_per_ue` | spike | 4.28 | KB-labeled mixed: ims.pcscf.rcv_requests_register_per_ue (spike, score=4.28) |
| `normalized.pcscf.dialogs_per_ue` | spike | 4.28 | KB-labeled mixed: ims.pcscf.dialogs_per_ue (spike, score=4.28) |
| `normalized.scscf.cdp_replies_per_ue` | spike | 4.28 | KB-labeled mixed: ims.scscf.cdp_replies_per_ue (spike, score=4.28) |
| `normalized.scscf.core:rcv_requests_invite_per_ue` | spike | 4.28 | KB-labeled mixed: ims.scscf.rcv_requests_invite_per_ue (spike, score=4.28) |
| `normalized.scscf.core:rcv_requests_register_per_ue` | spike | 4.28 | KB-labeled mixed: ims.scscf.rcv_requests_register_per_ue (spike, score=4.28) |

**Rationale:**

```
label=transport_layer. 1 transport-layer signal(s); no application-layer smoking guns. Routes to the deterministic path walk (see ADR path_anchored_probe_planning_for_transport_layer_faults.md).

Transport signals: derived.rtpengine_loss_ratio (spike, score=4.28) — KB-labeled transport: ims.rtpengine.loss_ratio (spike, score=4.28)

Ambiguous signals: normalized.icscf.cdp_replies_per_ue (spike, score=4.28) — KB-labeled mixed: ims.icscf.cdp_replies_per_ue (spike, score=4.28); normalized.icscf.core:rcv_requests_invite_per_ue (spike, score=4.28) — KB-labeled mixed: ims.icscf.rcv_requests_invite_per_ue (spike, score=4.28); normalized.icscf.core:rcv_requests_register_per_ue (spike, score=4.28) — KB-labeled mixed: ims.icscf.rcv_requests_register_per_ue (spike, score=4.28); normalized.pcscf.core:rcv_requests_invite_per_ue (spike, score=4.28) — KB-labeled mixed: ims.pcscf.rcv_requests_invite_per_ue (spike, score=4.28); normalized.pcscf.core:rcv_requests_register_per_ue (spike, score=4.28) — KB-labeled mixed: ims.pcscf.rcv_requests_register_per_ue (spike, score=4.28) [+4 more]
```

## Transport-Layer Route (Phase 0.6)

### Resolver

**Flow:** `vonr_media` (VoNR Media Path)  
**Direction:** both  
**Hop count:** 13

**Candidates considered:**

| Flow | Score |
|---|---:|
| `vonr_media` ← chosen | 7 |
| `vonr_call_teardown` | 4 |
| `vonr_call_setup` | 4 |
| `ims_registration` | 3 |
| `diameter_cx_authentication` | 2 |

**Rationale:**

```
Resolved transport path to flow `vonr_media` (score=7, 13 hops on the walk). Load-bearing components: ['icscf', 'pcscf', 'rtpengine', 'scscf']. Other candidate flows considered: vonr_call_teardown=4, vonr_call_setup=4, ims_registration=3, diameter_cx_authentication=2.
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
| 6 | `rtpengine` | container | `eth0` | `drops_attributed_here` | `qdisc_netem`: 496 dropped, 40.7% |
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

**Summary:** Transport-layer fault localized to rtpengine[eth0]: qdisc_netem reports 496 packets dropped (40.7%).

**Recommendation:** Inspect tc qdisc on rtpengine: `docker exec rtpengine tc -s qdisc show dev eth0`. If the qdisc is from a chaos injection, run the heal step. If it's authored, audit the configuration.


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
**Time to diagnosis:** 2.9s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ## Transport-layer path walk — flow `vonr_media`
> 
> Walked 13 hop(s) in topology order. First-attributed hop: **rtpengine[eth0]** (drops_attributed_here).
> 
> | # | hop | kind | iface | prober | attribution |
> |---|-----|------|-------|--------|-------------|
> | 1 | e2e_ue1 | container | eth0 | KernelHopProber | clean |
> | 2 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 3 | nr_gnb | container | eth0 | KernelHopProber | clean |
> | 4 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 5 | upf | container | eth0 | KernelHopProber | clean |
> | 6 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 7 | rtpengine | container | eth0 | KernelHopProber | drops_attributed_here (qdisc_netem, 496 dropped, 40.7%) 🎯 |
> | 8 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 9 | upf | container | eth0 | KernelHopProber | clean |
> | 10 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 11 | nr_gnb | container | eth0 | KernelHopProber | clean |
> | 12 | docker_open5gs_default | docker_bridge | br-docker_open5gs | DockerBridgeProber | clean |
> | 13 | e2e_ue2 | container | eth0 | KernelHopProber | clean |
> 
> ## Localization (verbatim evidence)
> 
> ```
> rtpengine[eth0] qdisc=netem, authored loss=30%: sent=1218 dropped=496 (40.72%)
> ---tc -s qdisc show dev eth0---
> qdisc netem 8050: root refcnt 9 limit 1000 loss 30%
>  Sent 642023 bytes 1218 pkt (dropped 496, overlimits 0 requeues 0) 
>  backlog 0b 0p requeues 0
> ```
> 
> ## Classifier rationale
> 
> label=transport_layer. 1 transport-layer signal(s); no application-layer smoking guns. Routes to the deterministic path walk (see ADR path_anchored_probe_planning_for_transport_layer_faults.md).
> 
> Transport signals: derived.rtpengine_loss_ratio (spike, score=4.28) — KB-labeled transport: ims.rtpengine.loss_ratio (spike, score=4.28)
> 
> Ambiguous signals: normalized.icscf.cdp_replies_per_ue (spike, score=4.28) — KB-labeled mixed: ims.icscf.cdp_replies_per_ue (spike, score=4.28); normalized.icscf.core:rcv_requests_invite_per_ue (spike, score=4.28) — KB-labeled mixed: ims.icscf.rcv_requests_invite_per_ue (spike, score=4.28); normalized.icscf.core:rcv_requests_register_per_ue (spike, score=4.28) — KB-labeled mixed: ims.icscf.rcv_requests_register_per_ue (spike, score=4.28); normalized.pcscf.core:rcv_requests_invite_per_ue (spike, score=4.28) — KB-labeled mixed: ims.pcscf.rcv_requests_invite_per_ue (spike, score=4.28); normalized.pcscf.core:rcv_requests_register_per_ue (spike, score=4.28) — KB-labeled mixed: ims.pcscf.rcv_requests_register_per_ue (spike, score=4.28) [+4 more]

### Scoring Breakdown

**Overall score: 100%**

**Scorer assessment:** The agent provided a perfect diagnosis, accurately identifying the root cause, affected component, severity, fault type, and layer with strong, verifiable evidence.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | Yes | The agent's diagnosis explicitly identifies 'packet loss' on the 'rtpengine' component, with specific percentages (30-40%) and attribution to a 'qdisc_netem' rule. This perfectly matches the simulated failure mode of 30% packet loss on RTPEngine. |
| Component overlap | 100% | The agent precisely identifies 'rtpengine' as the component where packet drops are attributed, making it the primary affected component and correctly identified as the root cause. |
| Severity correct | Yes | The agent identifies a significant packet loss (30-40%), which correctly corresponds to a 'degradation' in call quality rather than a complete outage, matching the simulated 'Call Quality Degradation' scenario. |
| Fault type identified | Yes | The agent explicitly identifies 'packet loss' as the fault type, providing quantitative evidence ('496 dropped', '40.7%', 'loss 30%') and linking it to the 'qdisc_netem' mechanism. |
| Layer accuracy | Yes | The agent's 'Classifier rationale' correctly labels the 'rtpengine.loss_ratio' metric as belonging to the 'ims' layer, which aligns with the ground truth that 'rtpengine' is an IMS component. |
| Confidence calibrated | Yes | The agent provides highly specific and verifiable evidence, including exact packet drop counts, percentages, and the underlying 'qdisc_netem' configuration. This definitive evidence justifies a high confidence in its diagnosis. |

**Ranking position:** #1 — The agent presents a single, clear, and correct diagnosis for the root cause without multiple ranked candidates.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 0 |
| Output tokens | 0 |
| **Total tokens** | **0** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| SymptomClassifier | 0 | 0 | 0 |
| PathResolver | 0 | 0 | 0 |
| PathWalkInvestigator | 0 | 0 | 0 |
| LocalizedSynthesis | 0 | 0 | 0 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 144.5s
