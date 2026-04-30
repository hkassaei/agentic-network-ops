# Episode Report: gNB Radio Link Failure

**Agent:** v6  
**Episode ID:** ep_20260430_012500_gnb_radio_link_failure  
**Date:** 2026-04-30T01:25:02.903300+00:00  
**Duration:** 351.6s  

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

- **Wait:** 0s
- **Actual elapsed:** 0.0s
- **Nodes with significant deltas:** 2
- **Nodes with any drift:** 4

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

## Anomaly Screening (Phase 0)

**ANOMALY DETECTED.** Overall anomaly score: 27.03 (per-bucket threshold: 25.22, context bucket (1, 0), trained on 323 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following metrics deviate from their learned-healthy baseline. Treat each as a semantic observation (meaning + numbers), not a number alone — the KB's interpretation is the authoritative reading.

- **`derived.upf_activity_during_calls`** (UPF activity consistency with active dialogs) — current **0.00 ratio** vs learned baseline **0.54 ratio** (MEDIUM, drop)
    - **What it measures:** Cross-layer consistency check between IMS dialog state and UPF
throughput. A drop while dialogs_per_ue is non-zero is a
smoking-gun signal for media-plane failure independent of signaling.
    - **Drop means:** Active calls reported but no media flowing — media path broken (UPF, RTPEngine, or N3 packet loss).
    - **Healthy typical range:** 0.3–1 ratio
    - **Healthy invariant:** 1.0 when traffic fully follows active calls; 0.0 when signaling says active but data plane is silent.

- **`normalized.pcscf.dialogs_per_ue`** (Active SIP dialogs per registered UE at P-CSCF) — current **3.00 count** vs learned baseline **0.48 count** (MEDIUM, spike)
    - **What it measures:** How many calls per user are currently in progress at the P-CSCF.
Going to zero from a non-zero baseline means calls have ended
(normal) OR call setup is failing system-wide (degradation).
Together with rcv_requests_* it discriminates the two.
    - **Spike means:** Calls ending or setup failing.
    - **Healthy typical range:** 0–1 count
    - **Healthy invariant:** Per-UE — scale-independent. 0 at rest, ~1 per active VoNR call.

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

- **`normalized.upf.gtp_indatapktn3upf_per_ue`** (GTP-U uplink rate per UE (N3)) — current **0.00 packets_per_second** vs learned baseline **1.45 packets_per_second** (MEDIUM, drop)
    - **What it measures:** Health of the uplink user-plane path gNB → UPF. Drops to near-zero
during RAN or N3 outage; stays nonzero during active calls or data
sessions. Decoupled from SIP signaling (signals data plane, not
control plane).
    - **Drop means:** Data plane dead on uplink — UPF receiving no packets from gNB.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE — constant regardless of UE pool size. Rises during active VoNR calls (~100 pps for G.711 voice) and data transfer.

- **`normalized.upf.gtp_outdatapktn3upf_per_ue`** (GTP-U downlink rate per UE (N3)) — current **0.00 packets_per_second** vs learned baseline **1.45 packets_per_second** (LOW, drop)
    - **What it measures:** Health of the downlink user-plane path UPF → gNB. Typically mirrors
uplink rate during calls/data; asymmetry indicates directional
faults (e.g., UPF receiving from internet but not forwarding).
    - **Drop means:** No traffic leaving UPF toward RAN.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE — constant regardless of UE pool size. Roughly symmetric with uplink during healthy calls.

- **`context.cx_active`** — current **0.00** vs learned baseline **0.59** (LOW, drop). *(No KB context available — interpret from the metric name.)*

- **`normalized.icscf.cdp_replies_per_ue`** (I-CSCF Diameter reply rate per UE) — current **0.00 replies_per_second_per_ue** vs learned baseline **0.03 replies_per_second_per_ue** (LOW, drop)
    - **What it measures:** Liveness of the I-CSCF↔HSS Cx path. Drops to 0 when HSS is unreachable OR when no signaling is occurring at the I-CSCF (idle or upstream P-CSCF partitioned).
    - **Drop means:** No Cx replies in the window. Could be healthy idle OR a Cx-path fault.
    - **Healthy typical range:** 0–1 replies_per_second_per_ue

- **`normalized.icscf.core:rcv_requests_invite_per_ue`** (SIP INVITE rate per UE at I-CSCF) — current **0.00 requests_per_second** vs learned baseline **0.00 requests_per_second** (LOW, drop)
    - **What it measures:** Health of call-setup forwarding P-CSCF → I-CSCF. Partition signature
same as REGISTER rate.
    - **Drop means:** Either no calls attempted or P-CSCF→I-CSCF partition.
    - **Healthy typical range:** 0–0.2 requests_per_second
    - **Healthy invariant:** Per-UE rate. Tracks pcscf.invite rate.

- **`normalized.pcscf.core:rcv_requests_invite_per_ue`** (SIP INVITE rate per UE at P-CSCF) — current **0.00 requests_per_second** vs learned baseline **0.00 requests_per_second** (LOW, drop)
    - **What it measures:** Call attempt rate from registered UEs. Unlike REGISTER (periodic),
INVITEs only fire when UEs place calls. Zero is normal during
quiet periods; nonzero INVITE with zero dialogs is the signature
of call setup failure.
    - **Drop means:** No calls being placed. Normal at rest.
    - **Healthy typical range:** 0–0.2 requests_per_second
    - **Healthy invariant:** Per-UE rate.


## Event Aggregation (Phase 1)

**5 events fired during the observation window:**

- `core.amf.gnb_association_drop` (source: `core.amf.gnb`, nf: `amf`, t=1777512421.4)  [current_value=0.0, prior_stable_value=1.0]
- `core.amf.ran_ue_sudden_drop` (source: `core.amf.ran_ue`, nf: `amf`, t=1777512421.4)  [current_value=0.0, prior_stable_value=2.0, delta_percent=-100.0]
- `core.amf.ran_ue_full_loss` (source: `core.amf.ran_ue`, nf: `amf`, t=1777512421.4)  [current_value=0.0, prior_stable_value=2.0]
- `core.smf.sessions_per_ue_drop` (source: `core.smf.sessions_per_ue`, nf: `smf`, t=1777512421.4)  [current_value=0.0, prior_stable_value=2.0, delta_percent=-100.0]
- `core.upf.activity_during_calls_collapsed` (source: `core.upf.activity_during_calls`, nf: `upf`, t=1777512421.4)  [current_value=0.0]

## Correlation Analysis (Phase 2)

**Correlation engine produced 5 ranked composite hypotheses from 5 fired events (showing top 3 of 5):**

### H1: Total RAN outage
  - primary_nf: amf
  - explanatory_fit: 0.40 (2/5 events)
  - testability: 2 (2 disambiguating metrics)
  - supporting events: `core.amf.gnb_association_drop`, `core.amf.ran_ue_full_loss`
  - probes to discriminate:
      - Check core.amf.ran_ue → Whether N2 is dead (both zero) vs. AMF-side attach issue (gnb>0, ran_ue=0)
      - Check core.amf.gnb → gNB-side failure (gnb=0) vs. AMF-side attach-processing issue (gnb>0 but ran_ue=0)

### H2: Total RAN failure — gNB + UEs both gone
  - primary_nf: amf
  - explanatory_fit: 0.40 (2/5 events)
  - testability: 2 (2 disambiguating metrics)
  - supporting events: `core.amf.gnb_association_drop`, `core.amf.ran_ue_full_loss`
  - probes to discriminate:
      - Check core.amf.ran_ue → Whether N2 is dead (both zero) vs. AMF-side attach issue (gnb>0, ran_ue=0)
      - Check core.amf.gnb → gNB-side failure (gnb=0) vs. AMF-side attach-processing issue (gnb>0 but ran_ue=0)

### H3: RAN failure confirmed — gNB down, UEs followed
  - primary_nf: amf
  - explanatory_fit: 0.40 (2/5 events)
  - testability: 2 (2 disambiguating metrics)
  - supporting events: `core.amf.gnb_association_drop`, `core.amf.ran_ue_sudden_drop`
  - probes to discriminate:
      - Check core.amf.ran_ue → Whether N2 is dead (both zero) vs. AMF-side attach issue (gnb>0, ran_ue=0)
      - Check core.amf.gnb → gNB-side failure (gnb=0) vs. AMF-side attach-processing issue (gnb>0 but ran_ue=0)

**1 events unmatched by any composite hypothesis** (may indicate gaps in the KB's correlates_with or truly independent events):
  - `core.upf.activity_during_calls_collapsed` (nf: `upf`)

## Network Analysis (Phase 3)

**Summary:** The root cause of the outage is a complete failure of the RAN, as the gNB component (nr_gnb) is not running, severing all connectivity between UEs and the core network.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** |   |  |
| **ran** | 🔴 RED | The gNB component is down, causing a total network outage. |
| **core** | 🟡 YELLOW | Core components are running but are non-operational and starved of traffic due to the RAN failure. |
| **ims** | 🟡 YELLOW | IMS components are running but cannot process calls without a functional data plane and user registration, both of which depend on the RAN. |

**RAN evidence:**
- get_network_status shows the nr_gnb container is not in the 'running' list.
- get_network_topology reports N2, N3, and Air Interface links as INACTIVE because the [RAN] is not connected.

**CORE evidence:**
- AMF metrics 'gnb' and 'ran_ue' are both 0.
- SMF and UPF per-UE metrics are 0, indicating no attached users or traffic.

**IMS evidence:**
- upf_activity_during_calls is 0, indicating no media plane traffic.

**Ranked hypotheses:**

- **`h1`** (fit=1.00, nf=nr_gnb, specificity=specific):
    - **Statement:** The gNB (Radio Access Network) is down. This has caused a total loss of N2 (control plane) and N3 (user plane) connectivity, leading to a full detachment of all UEs and a cessation of all user and signaling traffic through the core.
    - **Supporting events:** `core.amf.gnb_association_drop`, `core.amf.ran_ue_full_loss`, `core.smf.sessions_per_ue_drop`, `core.upf.activity_during_calls_collapsed`
    - **Falsification probes:**
        - Check if the 'nr_gnb' container process is running and has active SCTP associations to the AMF.


## Falsification Plans (Phase 4)

**3 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `amf`)

**Hypothesis:** Total RAN outage

**Probes (3):**
1. **`get_network_status`** — Check status of all network functions, especially 'nr_gnb'
    - *Expected if hypothesis holds:* The 'nr_gnb' container has an 'exited' or 'down' status.
    - *Falsifying observation:* The 'nr_gnb' container is 'running'.
2. **`check_process_listeners`** — Check for SCTP associations from the gNB on the AMF's N2 interface (port 38412).
    - *Expected if hypothesis holds:* No active SCTP association from the gNB's IP address.
    - *Falsifying observation:* An active SCTP association from the gNB's IP is present.
3. **`get_dp_quality_gauges`** — Get data plane quality metrics over the last 60 seconds.
    - *Expected if hypothesis holds:* All data plane metrics (packets/sec, kbps) are zero.
    - *Falsifying observation:* Non-zero data plane traffic is observed.

*Notes:* This plan tests the hypothesis of a total RAN outage by checking the gNB process status, control-plane connectivity at the AMF, and user-plane traffic at the UPF.

### Plan for `h2` (target: `amf`)

**Hypothesis:** Total RAN failure — gNB + UEs both gone

**Probes (3):**
1. **`measure_rtt`** — From 'amf' container to 'nr_gnb' container's IP address.
    - *Expected if hypothesis holds:* 100% packet loss or host unreachable.
    - *Falsifying observation:* Successful ping replies are received.
2. **`measure_rtt`** — From 'smf' container to 'nr_gnb' container's IP address.
    - *Expected if hypothesis holds:* 100% packet loss or host unreachable.
    - *Falsifying observation:* Successful ping replies are received. If this succeeds while the AMF->gNB ping fails, it falsifies the 'total gNB failure' and points to a network partition.
3. **`read_running_config`** — Read the gNB's configuration file to check the configured AMF address.
    - *Expected if hypothesis holds:* The tool command fails because the 'nr_gnb' container is not running.
    - *Falsifying observation:* The tool returns the gNB's configuration. This proves the container is running. A subsequent check on the config content can reveal a misconfiguration (e.g., wrong AMF IP) as the cause.

*Notes:* This plan focuses on network reachability to falsify the 'gNB gone' hypothesis. It uses a partner probe to distinguish a full gNB failure from a network path issue.

### Plan for `h3` (target: `amf`)

**Hypothesis:** RAN failure confirmed — gNB down, UEs followed

**Probes (3):**
1. **`get_network_status`** — Check the running status of the 'nr_gnb' container.
    - *Expected if hypothesis holds:* The 'nr_gnb' container status is 'exited' or not running.
    - *Falsifying observation:* The 'nr_gnb' container is running.
2. **`check_process_listeners`** — Check for listening processes on the 'nr_gnb' container, specifically for the N2 SCTP port (38412).
    - *Expected if hypothesis holds:* The tool fails to connect or returns an empty list, as the container is down.
    - *Falsifying observation:* The 'nr_gnb' container is listening on the N2 port. This shows the gNB process is up and ready for a connection from the AMF.
3. **`read_running_config`** — Read the AMF's configuration file to verify its list of gNB peers.
    - *Expected if hypothesis holds:* The AMF config should correctly list the now-unreachable gNB.
    - *Falsifying observation:* The AMF configuration is missing the gNB's details or has incorrect information (e.g., wrong IP). This would point to an AMF-side misconfiguration.

*Notes:* This hypothesis has a causal component ('gNB down, UEs followed'). This plan aims to falsify the premise ('gNB down') by checking process status, listener ports on the gNB, and related configuration on the AMF.


## Parallel Investigators (Phase 5)

**1 sub-Investigator verdict(s):** **1 DISPROVEN**

### `h1` — ❌ **DISPROVEN**

**Hypothesis:** The gNB (Radio Access Network) is down. This has caused a total loss of N2 (control plane) and N3 (user plane) connectivity, leading to a full detachment of all UEs and a cessation of all user and signaling traffic through the core.

**Reasoning:** The hypothesis of a total RAN outage with a complete cessation of all traffic is contradicted by direct observation of the data plane. While probes targeting the gNB process status and control plane connectivity at the AMF were consistent with an outage, data plane quality metrics at the UPF showed continued traffic flow at the time of the anomaly. This falsifies the claim that all user traffic had ceased.

**Probes executed (3):**
- **Check status of all network functions, especially 'nr_gnb'** ✓ CONSISTENT
    - *Tool:* `print(default_api.get_network_status())`
    - *Observation:* [EVIDENCE: get_network_status() -> '... "running": [..., "upf", ...], "down_or_absent": [] ...'] The 'nr_gnb' container is not listed in the output, implying it is not running.
    - *Comment:* The gNB container being absent is consistent with the hypothesis that the RAN is down. This aligns with the expected observation.
- **Check for SCTP associations from the gNB on the AMF's N2 interface (port 38412).** ✓ CONSISTENT
    - *Tool:* `print(default_api.check_process_listeners(container='amf'))`
    - *Observation:* [EVIDENCE: check_process_listeners("amf") -> '... tcp   LISTEN 0      5        172.22.0.10:7777 ...'] The output shows no process listening on the SCTP port 38412 for the N2 interface.
    - *Comment:* The absence of an N2 SCTP listener on the AMF is consistent with a loss of control plane connectivity from the gNB, as stated in the hypothesis.
- **Get data plane quality metrics over the last 60 seconds.** ✗ CONTRADICTS
    - *Tool:* `print(default_api.get_dp_quality_gauges(at_time_ts=1777512343.1873913, window_seconds=60))`
    - *Observation:* [EVIDENCE: get_dp_quality_gauges(at_time_ts=1777512343.1873913, window_seconds=60) -> 'UPF: in packets/sec: 5.5, out packets/sec: 5.5, active sessions: 8']
    - *Comment:* The hypothesis predicts a total cessation of user traffic. The observation of 5.5 packets/sec and 8 active sessions on the UPF directly contradicts this prediction. This indicates that the N3 user plane was not completely down.

**Alternative suspects:** amf


## Evidence Validation (Phase 6)

**Overall verdict:** clean
**Overall confidence:** high

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 3 | 3/3 | clean | high |


## Ground Truth

**Failure domain:** data_plane  
**Protocol impact:** GTP-U  
**Affected components:** nr_gnb  
**Severity:** degraded

## Agent Diagnosis

**Model:** v6-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 202.1s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: The primary hypothesis of a total network outage due to RAN failure has been disproven, as evidence shows some data plane traffic remains despite the gNB being down; the root cause is now uncertain.
> - **timeline**:
>     1. The AMF first observed a drop in its gNB associations (`core.amf.gnb_association_drop`).
>     2. This was followed by a complete loss of all UEs connected via the RAN (`core.amf.ran_ue_full_loss`).
>     3. The SMF subsequently saw a drop in PDU sessions (`core.smf.sessions_per_ue_drop`).
>     4. Finally, data plane activity at the UPF collapsed (`core.upf.activity_during_calls_collapsed`).
> - **root_cause**: The initial hypothesis set provided by the analysis was proven incorrect. The investigation surfaced the `amf` as an alternative suspect for further investigation.
> - **affected_components**:
>     - `nr_gnb`: Secondary (Confirmed to be down, but its failure does not explain all symptoms)
>     - `amf`: Root Cause (Suspected alternative, requires further investigation)
>     - `core` (smf, upf): Symptomatic
>     - `ims`: Symptomatic
> - **recommendation**: Verify the status of the `nr_gnb` and `amf` components. Investigate the source and nature of the residual traffic observed at the UPF, as this contradicted the initial assumption of a total data plane outage and is key to understanding the true fault.
> - **confidence**: low
> - **explanation**: The initial analysis pointed conclusively to the gNB (`nr_gnb`) in the Radio Access Network being down, causing a total outage. Investigation confirmed that the `nr_gnb` process is not running and that its control plane connection to the AMF is gone. However, the governing hypothesis was formally **disproven** because it stated that **all** user traffic would cease, which was contradicted by direct observation of lingering active sessions and packet flow at the UPF. Because all initial hypotheses were disproven, confidence in the root cause is low. The investigation should pivot to the alternative suspect, the `amf`, and focus on explaining the unexpected residual data plane activity.

### Scoring Breakdown

**Overall score: 31%**

**Scorer assessment:** The agent correctly identified the fault type and layer of the affected component, and its confidence was calibrated. However, it incorrectly disproved the gNB as the root cause and misidentified the severity of the outage, leading to a low overall score.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | No | The simulated failure was a gNB radio link failure, meaning the 'nr_gnb' was the root cause. The agent explicitly states that the initial hypothesis (gNB down) was 'disproven' and pivots to the 'amf' as the root cause, which is incorrect. The agent was misled by 'lingering active sessions and packet flow at the UPF' to conclude the gNB could not be the sole root cause. |
| Component overlap | 30% | The primary affected component is 'nr_gnb'. The agent lists 'nr_gnb' in 'affected_components' but labels it as 'Secondary' and states its failure 'does not explain all symptoms'. It labels 'amf' as the 'Root Cause'. This indicates the component was identified but its causal role was mis-ranked. |
| Severity correct | No | The simulated failure was a complete outage ('All UEs lose 5G registration, PDU sessions drop'). The agent initially identified it as a 'total outage' but then 'disproved' this due to 'lingering active sessions and packet flow', concluding it was not a total outage. This is incorrect; the failure resulted in a complete loss of service for UEs. |
| Fault type identified | Yes | The agent correctly identified the fault type for the gNB, stating 'Investigation confirmed that the `nr_gnb` process is not running and that its control plane connection to the AMF is gone,' which aligns with a component being unreachable/not responding. |
| Layer accuracy | Yes | The 'nr_gnb' belongs to the 'ran' layer. The agent's network analysis correctly rated the 'ran' layer as 'red' and attributed it to the gNB being down. |
| Confidence calibrated | Yes | The agent's diagnosis was largely incorrect regarding the root cause and severity. However, it explicitly stated 'confidence: low' and explained that 'all initial hypotheses were disproven,' indicating an appropriate level of uncertainty given its incorrect conclusion. |

**Ranking:** The correct root cause ('nr_gnb') was not identified as the primary root cause. Instead, 'amf' was identified as the 'Root Cause'.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 121,408 |
| Output tokens | 3,300 |
| Thinking tokens | 16,454 |
| **Total tokens** | **141,162** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| EventAggregator | 0 | 0 | 0 |
| CorrelationAnalyzer | 0 | 0 | 0 |
| NetworkAnalystAgent | 62,681 | 4 | 5 |
| InstructionGeneratorAgent | 31,675 | 1 | 2 |
| InvestigatorAgent_h1 | 41,612 | 3 | 4 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 5,194 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 351.6s
