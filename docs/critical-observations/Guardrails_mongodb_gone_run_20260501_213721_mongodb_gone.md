# Episode Report: MongoDB Gone

**Agent:** v6  
**Episode ID:** ep_20260501_212815_mongodb_gone  
**Date:** 2026-05-01T21:28:17.770604+00:00  
**Duration:** 543.3s  

---

## Scenario

**Category:** container  
**Blast radius:** global  
**Description:** Kill MongoDB — the 5G core subscriber data store. UDR loses its backend, new PDU sessions cannot be created, and subscriber queries fail. Existing sessions may survive briefly.

## Faults Injected

- **container_kill** on `mongo`

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

**ANOMALY DETECTED.** Overall anomaly score: 32.22 (per-bucket threshold: 26.31, context bucket (0, 1), trained on 323 healthy snapshots). The current metric pattern is statistically different from the learned healthy baseline. Something in the network has changed.

The following metrics deviate from their learned-healthy baseline. Treat each as a semantic observation (meaning + numbers), not a number alone — the KB's interpretation is the authoritative reading.

- **`derived.pcscf_sip_error_ratio`** (P-CSCF SIP error response ratio) — current **0.25 ratio** vs learned baseline **0.00 ratio** (MEDIUM, spike)
    - **What it measures:** Proportion of SIP responses that are errors. Zero is the healthy
baseline; any sustained non-zero value means P-CSCF or something
downstream is rejecting requests.
    - **Spike means:** Errors flowing back — downstream CSCFs or HSS rejecting.
    - **Healthy typical range:** 0–0 ratio
    - **Healthy invariant:** Zero in healthy operation.

- **`normalized.pcscf.core:rcv_requests_invite_per_ue`** (SIP INVITE rate per UE at P-CSCF) — current **0.02 requests_per_second** vs learned baseline **0.00 requests_per_second** (MEDIUM, spike)
    - **What it measures:** Call attempt rate from registered UEs. Unlike REGISTER (periodic),
INVITEs only fire when UEs place calls. Zero is normal during
quiet periods; nonzero INVITE with zero dialogs is the signature
of call setup failure.
    - **Spike means:** Fewer call attempts.
    - **Healthy typical range:** 0–0.2 requests_per_second
    - **Healthy invariant:** Per-UE rate.

- **`normalized.upf.gtp_indatapktn3upf_per_ue`** (GTP-U uplink rate per UE (N3)) — current **0.08 packets_per_second** vs learned baseline **1.45 packets_per_second** (MEDIUM, drop)
    - **What it measures:** Health of the uplink user-plane path gNB → UPF. Drops to near-zero
during RAN or N3 outage; stays nonzero during active calls or data
sessions. Decoupled from SIP signaling (signals data plane, not
control plane).
    - **Drop means:** Data plane dead on uplink — UPF receiving no packets from gNB.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE — constant regardless of UE pool size. Rises during active VoNR calls (~100 pps for G.711 voice) and data transfer.

- **`normalized.upf.gtp_outdatapktn3upf_per_ue`** (GTP-U downlink rate per UE (N3)) — current **0.06 packets_per_second** vs learned baseline **1.45 packets_per_second** (LOW, drop)
    - **What it measures:** Health of the downlink user-plane path UPF → gNB. Typically mirrors
uplink rate during calls/data; asymmetry indicates directional
faults (e.g., UPF receiving from internet but not forwarding).
    - **Drop means:** No traffic leaving UPF toward RAN.
    - **Healthy typical range:** 0–10 packets_per_second
    - **Healthy invariant:** Per-UE — constant regardless of UE pool size. Roughly symmetric with uplink during healthy calls.

- **`normalized.icscf.cdp_replies_per_ue`** (I-CSCF Diameter reply rate per UE) — current **0.02 replies_per_second_per_ue** vs learned baseline **0.03 replies_per_second_per_ue** (LOW, drop)
    - **What it measures:** Liveness of the I-CSCF↔HSS Cx path. Drops to 0 when HSS is unreachable OR when no signaling is occurring at the I-CSCF (idle or upstream P-CSCF partitioned).
    - **Drop means:** No Cx replies in the window. Could be healthy idle OR a Cx-path fault.
    - **Healthy typical range:** 0–1 replies_per_second_per_ue

- **`normalized.icscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at I-CSCF) — current **0.03 requests_per_second** vs learned baseline **0.06 requests_per_second** (LOW, shift)
    - **What it measures:** Health of the P-CSCF → I-CSCF forwarding path (Mw interface). When
this drops to zero while P-CSCF REGISTER rate is still non-zero,
it's the SIGNATURE of an IMS partition between P-CSCF and I-CSCF.
    - **Shift means:** Forwarding issue on the Mw interface, or P-CSCF stopped forwarding.
    - **Healthy typical range:** 0–0.5 requests_per_second
    - **Healthy invariant:** Per-UE rate. Should closely track ims.pcscf.rcv_requests_register_per_ue.

- **`normalized.pcscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at P-CSCF) — current **0.03 requests_per_second** vs learned baseline **0.06 requests_per_second** (LOW, shift)
    - **What it measures:** How actively UEs are refreshing their IMS registrations with the
P-CSCF. REGISTERs arrive periodically (re-registration timer) plus
at attach. Sustained zero means UEs cannot reach P-CSCF OR the
UE-to-network SIP path is broken.
    - **Shift means:** Fewer REGISTERs than expected — UE connectivity or P-CSCF reachability issue.
    - **Healthy typical range:** 0–0.5 requests_per_second
    - **Healthy invariant:** Per-UE rate — same value at any deployment scale.

- **`normalized.scscf.cdp_replies_per_ue`** (S-CSCF CDP Diameter replies per UE) — current **0.03 replies_per_second_per_ue** vs learned baseline **0.06 replies_per_second_per_ue** (LOW, shift)
    - **What it measures:** Active S-CSCF Diameter traffic with HSS. Near-zero when registrations idle OR HSS partition.
    - **Shift means:** Diameter peering loss with HSS.
    - **Healthy typical range:** 0–1 replies_per_second_per_ue
    - **Healthy invariant:** Per-UE rate; varies with registration/auth load.

- **`normalized.scscf.core:rcv_requests_register_per_ue`** (SIP REGISTER rate per UE at S-CSCF) — current **0.03 requests_per_second** vs learned baseline **0.06 requests_per_second** (LOW, shift)
    - **What it measures:** Health of the I-CSCF → S-CSCF forwarding path. Drop to zero while
I-CSCF is receiving REGISTERs = S-CSCF-side issue (crashed, or
I-CSCF → S-CSCF path broken).
    - **Shift means:** I-CSCF not forwarding or S-CSCF not receiving.
    - **Healthy typical range:** 0–0.5 requests_per_second
    - **Healthy invariant:** Per-UE rate. Tracks icscf.register rate.

- **`normalized.smf.bearers_per_ue`** (Active QoS bearers per UE) — current **2.00 count** vs learned baseline **2.48 count** (LOW, shift)
    - **What it measures:** Per-UE count of active QoS bearers. Baseline reflects default
bearers; increments during VoNR calls indicate dedicated voice
bearers being set up. Drop during an active call = dedicated
bearer torn down unexpectedly (voice will fail).
    - **Shift means:** Expected during VoNR calls (1 extra bearer per active call).
    - **Healthy typical range:** 2–3.5 count
    - **Healthy invariant:** At rest: equals configured default bearers (typically 2 per UE).
During active VoNR call: +1 per caller. The per-UE ratio is the
invariant; absolute count scales with UE pool.


## Event Aggregation (Phase 1)

No events fired during this episode. Either no metric KB triggers matched, or the episode encountered no meaningful state transitions.

## Correlation Analysis (Phase 2)

No events fired — correlation engine had nothing to work with.

## Network Analysis (Phase 3)

**Summary:** The MongoDB container has exited, causing failures in the PCF and UDR network functions, which has led to a widespread outage affecting both the control (IMS) and data planes.

**Layer status:**

| Layer | Rating | Note |
|---|---|---|
| **infrastructure** | 🔴 RED | The core database service (MongoDB) for multiple NFs is down. |
| **ran** | 🟢 GREEN | No direct evidence of a RAN issue. The problems appear to start in the core. |
| **core** | 🔴 RED | The data plane is down and session management is failing. This is a direct result of PCF and UDR failures caused by the MongoDB outage. |
| **ims** | 🔴 RED | IMS signaling is failing for registrations and call invites, with high SIP error rates at the P-CSCF and Diameter failures downstream. |

**INFRASTRUCTURE evidence:**
- mongo container is exited

**CORE evidence:**
- normalized.upf.gtp_indatapktn3upf_per_ue drop
- normalized.upf.gtp_outdatapktn3upf_per_ue drop
- normalized.smf.bearers_per_ue shift

**IMS evidence:**
- derived.pcscf_sip_error_ratio spike
- normalized.icscf.cdp_replies_per_ue drop
- normalized.scscf.cdp_replies_per_ue shift

**Ranked hypotheses:**

- **`h1`** (fit=1.00, nf=mongo, specificity=specific):
    - **Statement:** The MongoDB container, a critical backend for multiple network functions, is the source of the anomaly. Its failure is causing dependent NFs including PCF and UDR to lose access to their data, leading to the observed network-wide failure.
    - **Falsification probes:**
        - Executing 'docker ps' on the host shows the mongo container is running.
        - A health check from a component that uses MongoDB (e.g., PCF) to its MongoDB instance succeeds.
- **`h2`** (fit=0.90, nf=pcf, specificity=specific):
    - **Statement:** The PCF is the source of the anomalous SIP errors and data plane failure. This is observed in the high SIP error ratio at the P-CSCF and the collapse of GTP traffic at the UPF.
    - **Falsification probes:**
        - Live probes of the PCF's Npcf interface from the SMF show successful session management policy responses.
        - Live probes of the PCF's Rx interface from the P-CSCF show successful policy authorization responses.
- **`h3`** (fit=0.80, nf=udr, specificity=specific):
    - **Statement:** The UDR is the source of the IMS registration and authentication failures. This is observed in the drop in Diameter replies from the HSS/UDM to the I-CSCF and S-CSCF during registration procedures.
    - **Falsification probes:**
        - Live probes of the UDR's Nudr interface from the UDM show successful subscriber data retrieval.
        - The UDR's internal logs show successful queries and no errors related to its database connection.


## Falsification Plans (Phase 4)

**3 falsification plan(s) — one per hypothesis:**

### Plan for `h1` (target: `mongo`)

**Hypothesis:** The MongoDB container, a critical backend for multiple network functions, is the source of the anomaly. Its failure is causing dependent NFs including PCF and UDR to lose access to their data, leading to the observed network-wide failure.

**Probes (3):**
1. **`get_network_status`** — Check the status of the 'mongo' container.
    - *Expected if hypothesis holds:* The 'mongo' container has an 'exited' status.
    - *Falsifying observation:* The 'mongo' container has a 'running' status.
2. **`check_process_listeners`** — container='mongo'
    - *Expected if hypothesis holds:* The command returns an empty list of listeners, indicating the mongod process is not active.
    - *Falsifying observation:* The probe's reading is inconsistent with mongo being the source (e.g. it shows the mongod process listening on its default port).
3. **`get_diagnostic_metrics`** — Get metrics for PCF, which depends on MongoDB.
    - *Expected if hypothesis holds:* Metrics from PCF show a high rate of database connection errors or timeouts.
    - *Falsifying observation:* The probe's reading is inconsistent with mongo being the source (e.g. PCF metrics show no database-related errors).

*Notes:* This plan directly checks the state of the MongoDB container and the impact on a dependent network function (PCF).

### Plan for `h2` (target: `pcf`)

**Hypothesis:** The PCF is the source of the anomalous SIP errors and data plane failure. This is observed in the high SIP error ratio at the P-CSCF and the collapse of GTP traffic at the UPF.

**Probes (3):**
1. **`get_network_status`** — Check the status of the 'mongo' container, a critical dependency for PCF.
    - *Expected if hypothesis holds:* The 'mongo' container has a 'running' status. If it were down, the root cause would not be PCF itself.
    - *Falsifying observation:* The 'mongo' container has an 'exited' status, which would strongly suggest the root cause is upstream of PCF, thus falsifying this hypothesis.
2. **`get_diagnostic_metrics`** — Get metrics for 'smf' and 'pcf' to check the Npcf interface.
    - *Expected if hypothesis holds:* SMF's metrics show failures for requests towards PCF, and PCF's metrics show a high error rate for policy decisions.
    - *Falsifying observation:* The probe's reading is inconsistent with pcf being the source (e.g. SMF's metrics show successful policy responses from PCF).
3. **`get_diagnostic_metrics`** — Get metrics for 'pcscf' and 'pcf' to check the Rx interface.
    - *Expected if hypothesis holds:* P-CSCF's metrics show a high error rate for Rx requests towards PCF.
    - *Falsifying observation:* The probe's reading is inconsistent with pcf being the source (e.g. P-CSCF's metrics show successful Rx interactions with PCF).

*Notes:* This plan aims to falsify that PCF is the *source* by checking its own dependencies and its interfaces with SMF and P-CSCF.

### Plan for `h3` (target: `udr`)

**Hypothesis:** The UDR is the source of the IMS registration and authentication failures. This is observed in the drop in Diameter replies from the HSS/UDM to the I-CSCF and S-CSCF during registration procedures.

**Probes (3):**
1. **`get_network_status`** — Check the status of the 'mongo' container, a critical dependency for UDR.
    - *Expected if hypothesis holds:* The 'mongo' container has a 'running' status. If it were down, the root cause would not be UDR itself.
    - *Falsifying observation:* The 'mongo' container has an 'exited' status, which would strongly suggest the root cause is upstream of UDR, thus falsifying this hypothesis.
2. **`get_diagnostic_metrics`** — Get metrics for 'udm' and 'udr' to check the Nudr interface.
    - *Expected if hypothesis holds:* UDM's metrics show failures for requests towards UDR, and UDR's metrics show a high error rate for data retrieval.
    - *Falsifying observation:* The probe's reading is inconsistent with udr being the source (e.g. UDM's metrics show successful data retrieval from UDR).
3. **`query_subscriber`** — imsi='<any known IMSI>'
    - *Expected if hypothesis holds:* The query fails or times out, indicating a problem in the subscriber data lookup chain (HSS-UDM-UDR).
    - *Falsifying observation:* The query successfully returns subscriber data, which would indicate the HSS-UDM-UDR chain is functional.

*Notes:* This plan aims to falsify that UDR is the *source* by checking its own dependencies and its primary interface with UDM. It also includes a subscriber query to test the end-to-end subscriber data path.


## Parallel Investigators (Phase 5)

**4 sub-Investigator verdict(s):** **1 INCONCLUSIVE**, **2 DISPROVEN**, **1 NOT_DISPROVEN**

### `h1` — ❓ **INCONCLUSIVE**

**Hypothesis:** The MongoDB container, a critical backend for multiple network functions, is the source of the anomaly. Its failure is causing dependent NFs including PCF and UDR to lose access to their data, leading to the observed network-wide failure.

**Reasoning:** [Multi-shot consensus — DISAGREEMENT. Shot 1 returned DISPROVEN; shot 2 returned NOT_DISPROVEN. Two independent samples of the same Investigator on the same plan reached opposite conclusions. The reconciler forces verdict to INCONCLUSIVE because we cannot trust either shot in isolation when the underlying LLM judgment is unstable.]

Shot 1 (DISPROVEN): The investigation confirmed that the MongoDB container has exited. However, a probe of PCF's metrics, a key dependent network function, showed no signs of failure. At the time of the anomaly, PCF's counters for policy association requests and successes were equal, which contradicts the hypothesis that MongoDB's failure was causing dependent NFs to lose data access and fail.

Shot 2 (NOT_DISPROVEN): All three probes were executed. The first two probes confirmed the core assertion of the hypothesis: the MongoDB container has failed. The third probe, intended to check for downstream impact on the PCF, was ambiguous; the available metrics were cumulative counters which do not effectively show an error rate at the time of the anomaly. Since no evidence contradicts the hypothesis and its central claim is proven true, the hypothesis is NOT_DISPROVEN.

**Probes executed (3):**
- **Check the status of the 'mongo' container.** ✓ CONSISTENT
    - *Tool:* `print(default_api.get_network_status())`
    - *Observation:* [EVIDENCE: get_network_status() -> "{
  \"phase\": \"down\", ... \"down_or_absent\": [\n    \"mongo\"\n  ], ... \"mongo\": \"exited\" ...}"]
    - *Comment:* The MongoDB container status is 'exited', which is consistent with the hypothesis that it has failed.
- **Check if the mongod process is listening for connections.** ✓ CONSISTENT
    - *Tool:* `print(default_api.check_process_listeners(container = "mongo"))`
    - *Observation:* [EVIDENCE: check_process_listeners(container="mongo") -> "Error response from daemon: container 82bf8ab4243865d6a9f478b57b81678b989fdef512c96605f0eab1a0d7c80e80 is not running"]
    - *Comment:* The tool failed because the container is not running, which confirms the mongod process is not active and cannot be listening. This is consistent with the hypothesis.
- **Get diagnostic metrics for PCF to check for database connection issues.** ✗ CONTRADICTS
    - *Tool:* `print(default_api.get_diagnostic_metrics(at_time_ts = 1777670994.4465818, nfs = ["pcf"]))`
    - *Observation:* [EVIDENCE: get_diagnostic_metrics(at_time_ts=1777670994.4465818, nfs=["pcf"]) -> "fivegs_pcffunction_pa_policyamassoreq = 12 [counter]...fivegs_pcffunction_pa_policyamassosucc = 12 [counter]"]
    - *Comment:* The metrics show that the number of successful AM policy associations equals the number of requests. This indicates PCF is not experiencing database access failures, which directly contradicts the hypothesis's claimed impact on dependent NFs.

### `h2` — ❌ **DISPROVEN**

**Hypothesis:** The PCF is the source of the anomalous SIP errors and data plane failure. This is observed in the high SIP error ratio at the P-CSCF and the collapse of GTP traffic at the UPF.

**Reasoning:** [Multi-shot consensus — both shots returned DISPROVEN.]

Shot 1: The investigation revealed that the 'mongo' container, a critical dependency for the PCF, had an 'exited' status at the time of the anomaly. This directly contradicts the hypothesis that the PCF is the *source* of the failure. The observed SIP errors at the P-CSCF are symptoms of PCF's failure, but the root cause is the unavailability of its database, MongoDB. The PCF is affected, but it is not the origin of the fault.

Shot 2: The investigation revealed that the 'mongo' container, a critical dependency for the PCF, had an 'exited' status during the anomaly. This indicates the root cause of the failure is upstream of the PCF, falsifying that PCF is the source. Further, metrics from the PCF's interface with the SMF showed no errors, contradicting the expectation of a PCF-originated failure.

**Probes executed (3):**
- **Check the status of the 'mongo' container, a critical dependency for PCF.** ✗ CONTRADICTS
    - *Tool:* `default_api.get_network_status()`
    - *Observation:* [EVIDENCE: get_network_status() -> "'containers': {'mongo': 'exited'}"]
    - *Comment:* The falsifying observation was met. The 'mongo' container, which the PCF relies on, was not running. This indicates the root cause is upstream of the PCF, falsifying the hypothesis that PCF is the source.
- **Get metrics for 'smf' and 'pcf' to check the Npcf interface.** ~ AMBIGUOUS
    - *Tool:* `default_api.get_diagnostic_metrics(at_time_ts=1777670994.4465818, nfs=['smf', 'pcf'])`
    - *Observation:* [EVIDENCE: get_diagnostic_metrics(at_time_ts=1777670994.4465818, nfs=['smf', 'pcf']) -> "pcf: fivegs_pcffunction_pa_policyamassosucc = 12 [counter] smf: fivegs_smffunction_sm_sessionnbr = 4 [counter]"]
    - *Comment:* The metrics for SMF and PCF were inconclusive. They did not show explicit errors on the Npcf interface, but the traffic volume was low. This neither strongly supports nor contradicts the hypothesis, but the evidence from other probes is much clearer.
- **Get metrics for 'pcscf' and 'pcf' to check the Rx interface.** ✓ CONSISTENT
    - *Tool:* `default_api.get_diagnostic_metrics(at_time_ts=1777670994.4465818, nfs=['pcscf', 'pcf'])`
    - *Observation:* [EVIDENCE: get_diagnostic_metrics(at_time_ts=1777670994.4465818, nfs=['pcscf', 'pcf']) -> "pcscf: httpclient:connfail = 74 [counter], httpclient:connok = 0 [counter]"]
    - *Comment:* P-CSCF metrics show a high number of HTTP client connection failures and zero successful connections. This is consistent with PCF being unavailable, as the Rx interface is HTTP-based. However, combined with the knowledge that 'mongo' is down, this is seen as a symptom, not a source failure at PCF.

**Alternative suspects:** mongo

### `h3` — ❌ **DISPROVEN**

**Hypothesis:** The UDR is the source of the IMS registration and authentication failures. This is observed in the drop in Diameter replies from the HSS/UDM to the I-CSCF and S-CSCF during registration procedures.

**Reasoning:** [Multi-shot consensus — both shots returned DISPROVEN.]

Shot 1: The investigation revealed that the 'mongo' container, a critical dependency for the UDR, had an "exited" status. This was confirmed by a `get_network_status` call. A subsequent subscriber query failed with a message indicating that the subscriber could not be found in the MongoDB, directly implicating the database, not the UDR, as the failure point. Therefore, the UDR is not the *source* of the failures; it is a victim of the database outage.

Shot 2: The evidence strongly indicates that the root cause of the failure is not the UDR itself, but its database dependency, MongoDB. The 'mongo' container was found to be in an 'exited' state, which would cause any dependent service like the UDR to fail. This is further supported by the `query_subscriber` tool, which failed to retrieve 5G core data stored in MongoDB, while successfully retrieving IMS data from a separate, functional database (PyHSS/MySQL).

**Probes executed (3):**
- **Check the status of the 'mongo' container, a critical dependency for UDR.** ✗ CONTRADICTS
    - *Tool:* `print(default_api.get_network_status())`
    - *Observation:* [EVIDENCE: get_network_status() -> "{'containers': {'mongo': 'exited'}}"]
    - *Comment:* The 'mongo' container has an 'exited' status. The hypothesis expects it to be running, as a failure of this dependency would mean UDR is not the root cause. This observation directly falsifies the hypothesis.
- **Get metrics for 'udm' and 'udr' to check the Nudr interface.** ~ AMBIGUOUS
    - *Tool:* `print(default_api.get_diagnostic_metrics(at_time_ts=1777670994.4465818, nfs=['udm', 'udr']))`
    - *Observation:* [EVIDENCE: get_diagnostic_metrics(at_time_ts=1777670994.4465818, nfs=['udm', 'udr']) -> 'DIAGNOSTIC METRICS (anchored at ts=1777670994)...']
    - *Comment:* The tool returned no specific metrics for UDM and UDR. This is likely because the components were unable to report metrics due to the underlying database failure. While not directly contradicting, it does not support the hypothesis and is consistent with the 'mongo' failure.
- **Query subscriber data for a known IMSI.** ✗ CONTRADICTS
    - *Tool:* `print(default_api.query_subscriber(imsi='001011234567891'))`
    - *Observation:* [EVIDENCE: query_subscriber(imsi='001011234567891') -> '{"core_5g": null, "core_5g_note": "Subscriber 001011234567891 NOT FOUND in Open5GS MongoDB..."}']
    - *Comment:* The query for 5G core subscriber data failed, but the error explicitly states the subscriber was not found in 'Open5GS MongoDB'. This indicates the problem is with the database backend (mongo), not the UDR service itself, thus falsifying the hypothesis that UDR is the source.

**Alternative suspects:** mongo

### `h_promoted_mongo` — ✅ **NOT_DISPROVEN**

**Hypothesis:** mongo is the source of the anomaly named in the alternative_suspects of the original verdict tree.

**Reasoning:** All three probes executed were either consistent with or did not contradict the hypothesis. The first probe confirmed that the 'mongo' container was in an 'exited' state, which directly supports the hypothesis that it is the source of the anomaly. The second probe, which failed because the container was not running, is also consistent with this finding. The final probe for metrics from dependent network functions (UDM, UDR, AUSF) returned no data, which is ambiguous but does not falsify the hypothesis, as a non-functional database would likely lead to failures in these components, potentially affecting their metric reporting.

**Probes executed (3):**
- **Check status of the 'mongo' container.** ✓ CONSISTENT
    - *Tool:* `default_api.get_network_status()`
    - *Observation:* [EVIDENCE: get_network_status() -> "'containers': {'mongo': 'exited'}"]
    - *Comment:* The mongo container is not running. This is direct evidence supporting the hypothesis that it is the source of a problem.
- **Check for listening ports on the 'mongo' container.** ✓ CONSISTENT
    - *Tool:* `default_api.check_process_listeners(container='mongo')`
    - *Observation:* [EVIDENCE: check_process_listeners("mongo") -> "Error response from daemon: container 82bf8ab4243865d6a9f478b57b81678b989fdef512c96605f0eab1a0d7c80e80 is not running"]
    - *Comment:* The tool failed because the container is not running. This is an expected consequence of the container being in an 'exited' state and is consistent with the hypothesis.
- **Check for database-related errors in the metrics of core network functions that depend on a database, such as UDM, UDR, and AUSF.** ~ AMBIGUOUS
    - *Tool:* `default_api.get_diagnostic_metrics(at_time_ts=1777670994.4465818, nfs=['udm', 'udr', 'ausf'])`
    - *Observation:* [EVIDENCE: get_diagnostic_metrics(at_time_ts=1777670994.4465818, nfs=['udm', 'udr', 'ausf']) -> "DIAGNOSTIC METRICS (anchored at ts=1777670994)..."]
    - *Comment:* The tool returned no metrics for the specified network functions. While this doesn't directly confirm database errors, it does not contradict the hypothesis. A failure of the mongo database would likely cause service disruptions in UDM, UDR, and AUSF, which could result in a lack of metric data.


## Evidence Validation (Phase 6)

**Overall verdict:** clean
**Overall confidence:** high

**Per sub-Investigator:**

| Agent | Tool Calls | Citations | Verdict | Confidence |
|---|---|---|---|---|
| `InvestigatorAgent_h1` | 6 | 3/3 | clean | high |
| `InvestigatorAgent_h2` | 5 | 3/3 | clean | high |
| `InvestigatorAgent_h3` | 7 | 3/3 | clean | high |
| `InvestigatorAgent_h_promoted_mongo` | 3 | 3/3 | clean | high |


## Ground Truth

**Failure domain:** data_layer  
**Protocol impact:** multiple  
**Affected components:** mongo  
**Severity:** degraded

## Agent Diagnosis

**Model:** v6-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 398.5s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> ### causes
> - **summary**: The MongoDB container, a critical database dependency for multiple core network functions, has exited, causing a cascading failure in the UDR and PCF that has led to a widespread outage of both control plane (IMS) and data plane services.
> - **timeline**:
>     1. The 'mongo' container exits unexpectedly.
>     2. The PCF and UDR network functions lose connectivity to their backend database.
>     3. The UDR can no longer serve subscriber data, causing IMS registration and authentication procedures at the UDM to fail.
>     4. The PCF can no longer serve policy, causing P-CSCF requests on the Rx interface to fail and SMF session management procedures to fail.
>     5. As a result, new IMS registrations and calls fail, and data plane traffic at the UPF collapses.
> - **root_cause**: The 'mongo' container has exited, causing its dependent network functions (including PCF and UDR) to lose database access and fail. (primary_suspect_nf: `mongo`)
> - **affected_components**:
>     - `mongo`: Root Cause
>     - `pcf`: Secondary
>     - `udr`: Secondary
>     - `pcscf`: Symptomatic
>     - `udm`: Symptomatic
>     - `upf`: Symptomatic
> - **recommendation**: The 'mongo' container is confirmed to be in an 'exited' state. The operator should inspect the container's logs to determine the reason for its unexpected termination.
> - **confidence**: medium
> - **verdict_kind**: confirmed
> - **explanation**: The investigation confirmed that the 'mongo' database container, a dependency for several network functions, is the root cause of the outage. Hypotheses pointing to the PCF and UDR as the source were disproven when investigation revealed that their upstream dependency, MongoDB, had failed. An initial direct investigation of MongoDB was inconclusive due to conflicting reports. However, a subsequent, focused re-investigation provided unambiguous evidence that the 'mongo' container was not running. This confirms it as the source of the cascading failures observed in the PCF, UDR, and downstream IMS and data plane components. Confidence is set to medium due to the initial inconclusive finding, which warrants careful verification.

### Scoring Breakdown

**Overall score: 100%**

**Scorer assessment:** The agent provided an excellent diagnosis, correctly identifying the root cause, affected components, severity, and fault type, with accurate layer attribution and calibrated confidence.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | Yes | The agent correctly identified 'mongo' container exiting as the root cause, which directly matches the simulated failure mode. |
| Component overlap | 100% | The agent correctly identified 'mongo' as the 'Root Cause' in the affected_components list. |
| Severity correct | Yes | The agent correctly described the impact as a 'widespread outage' and 'data plane traffic at the UPF collapses', which aligns with the simulated complete unreachability and failure of new sessions. |
| Fault type identified | Yes | The agent identified the fault type as the 'mongo' container being 'exited' and 'not running', which accurately describes the observable state of the component (unreachable/down). |
| Layer accuracy | Yes | The agent's network analysis correctly attributed the 'mongo container is exited' evidence to the 'infrastructure' layer, which matches the ground truth for MongoDB's ontology layer. |
| Confidence calibrated | Yes | The agent's confidence is 'medium', which is well-calibrated given its explanation of initial inconclusive findings followed by unambiguous evidence. Acknowledging past uncertainty while reaching a correct conclusion demonstrates good calibration. |

**Ranking position:** #1 — The agent provided a single, clear root cause in its final diagnosis, which was correct.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 377,105 |
| Output tokens | 12,024 |
| Thinking tokens | 36,671 |
| **Total tokens** | **425,800** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| AnomalyScreener | 0 | 0 | 0 |
| EventAggregator | 0 | 0 | 0 |
| CorrelationAnalyzer | 0 | 0 | 0 |
| NetworkAnalystAgent | 27,563 | 3 | 2 |
| Phase 3 NetworkAnalyst__guardrail | 0 | 0 | 0 |
| NetworkAnalystAgent | 47,824 | 3 | 4 |
| Phase 3 NetworkAnalyst__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 20,816 | 3 | 2 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| InstructionGeneratorAgent | 26,706 | 1 | 2 |
| Phase 4 InstructionGenerator__guardrail | 0 | 0 | 0 |
| InvestigatorAgent_h1 | 20,902 | 3 | 2 |
| InvestigatorAgent_h1 | 40,842 | 3 | 4 |
| InvestigatorAgent_h1__reconciliation | 0 | 0 | 0 |
| InvestigatorAgent_h2 | 31,213 | 2 | 3 |
| InvestigatorAgent_h2 | 44,066 | 3 | 4 |
| InvestigatorAgent_h2__reconciliation | 0 | 0 | 0 |
| InvestigatorAgent_h3 | 43,360 | 3 | 4 |
| InvestigatorAgent_h3 | 56,525 | 4 | 5 |
| InvestigatorAgent_h3__reconciliation | 0 | 0 | 0 |
| Phase5FanOutAudit | 0 | 0 | 0 |
| Phase6.5CandidatePool | 0 | 0 | 0 |
| InstructionGeneratorAgent | 18,413 | 1 | 2 |
| Phase 6.5 Reinvestigation IG__guardrail | 0 | 0 | 0 |
| InvestigatorAgent_h_promoted_mongo | 38,535 | 3 | 4 |
| EvidenceValidator | 0 | 0 | 0 |
| SynthesisAgent | 9,035 | 0 | 1 |
| Phase 7 Synthesis__guardrail | 0 | 0 | 0 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 543.3s

---

# Guardrail Impact Analysis (added 2026-05-01)

This section documents how the structural guardrails shipped per
`docs/ADR/structural_guardrails_for_llm_pipeline.md` shaped this run.
Recorded here because this run is the cleanest in-the-wild
demonstration so far of the full guardrail stack working as a
designed system rather than as independent checks.

## Score history for this scenario

`MongoDB Gone` (container_kill on `mongo`) is one of the harder
scenarios in the chaos library because it produces cross-cutting
symptoms: the actual fault is at the data layer (infrastructure),
but the surface symptoms hit P-CSCF, I-CSCF, S-CSCF, UPF, and SMF
through different dependency paths (PCF → mongo, UDR → mongo). Prior
v6 runs against this scenario have swung wildly:

| Date | Score | Diagnosis |
|---|---|---|
| 2026-04-23 | 36% | Wrong NF — *"P-CSCF has an internal fault in its HTTP client"* |
| 2026-04-24 | 100% | Correct |
| 2026-04-28 | 90% | Mongo named with caveats |
| 2026-04-29 | 46% | *"Could not be determined"* — NA hypothesis set was inconclusive |
| 2026-04-30 | 95% | UDR named (one hop off mongo) |
| **2026-05-01 (this run)** | **100%** | Clean: mongo as Root Cause, calibrated confidence, full cascade documented |

The variance from 36% → 100% across prior runs is exactly the
structural noise the ADR was trying to eliminate. This run shows the
shipped guardrail stack pinning a difficult scenario at 100% rather
than rolling the dice on each invocation.

## Per-phase guardrail activity

| Phase | Activity | Which guardrail fired |
|---|---|---|
| **Phase 3 NA** | 2 LLM calls (lines 428, 430) | One of D / H / G triggered a resample. Both NA emits had mongo at fit=1.0 + clean cascade reasoning, so the resample either caught a borderline issue on the first emit or the linter chain (D → H → G) collectively forced a tighter rewrite |
| **Phase 4 IG** | 2 LLM calls (lines 432, 434) | Decision A's `lint_ig_plan` rejected the first plan and accepted the second with warning (the `Phase 4 InstructionGenerator__guardrail` traces appear on both attempts, matching the REJECT-then-accept pattern from prior runs) |
| **Phase 5 h1 multi-shot** | **DISAGREEMENT** — shot 1 DISPROVEN, shot 2 NOT_DISPROVEN | **Decision C (PR 6) caught real LLM variance.** Reconciler forced INCONCLUSIVE rather than ratifying a coin-flip outcome. This is the canonical use case |
| **Phase 5 h2 multi-shot** | Both shots DISPROVEN — agreement | Reconciler merged the reasoning + alt_suspects=[mongo] from both shots. Same outcome as single-shot would have produced; multi-shot adds confidence here |
| **Phase 5 h3 multi-shot** | Both shots DISPROVEN — agreement | Same as h2; alt_suspects=[mongo] |
| **Phase 6.5 candidate pool** | Pool composition: 0 NOT_DISPROVEN, mongo cited 2x in alt_suspects (h2 + h3), strong-cite in both verdicts' reasoning | **Decision E (PR 5) aggregator promoted mongo** → triggered bounded re-investigation |
| **Re-investigation** | Synthetic `h_promoted_mongo` hypothesis → fresh IG plan → single-shot Investigator on mongo → **NOT_DISPROVEN** | Pool re-rendered with mongo as SURVIVOR; Synthesis sees a structurally clean answer instead of inferring from `alternative_suspects` prose |
| **Phase 6.6 EvidenceValidator** | overall=clean, confidence=high (line 340) | EV ran AFTER 6.5 (PR 5.5a) and saw all four sub-Investigator traces including the re-investigation — citation check covers the full investigation |
| **Phase 7 Synthesis** | confidence=medium, verdict_kind=confirmed (line 390) | **Decision F (PR 3) confidence cap applied** — supporting evidence had AMBIGUOUS probes mixed in (re-investigation's metric probe was AMBIGUOUS), evidence-strength = MODERATE → cap from `high` to `medium`. Synthesis explicitly cites *"initial inconclusive finding, which warrants careful verification"* in its explanation, indicating the cap reasoning rode through to the final diagnosis text |

## The h1 multi-shot disagreement

This is the most instructive event in the run. Same plan, same
prompt, two independent samples of the Investigator, opposite
verdicts:

> **Shot 1 (DISPROVEN):** *"At the time of the anomaly, PCF's
> counters for policy association requests and successes were equal,
> which contradicts the hypothesis that MongoDB's failure was
> causing dependent NFs to lose data access and fail."*

> **Shot 2 (NOT_DISPROVEN):** *"Two probes confirmed the core
> assertion: the MongoDB container has failed. The third probe was
> ambiguous; the available metrics were cumulative counters which do
> not effectively show an error rate at the time of the anomaly."*

Both shots saw the same `get_diagnostic_metrics` output:
```
fivegs_pcffunction_pa_policyamassoreq = 12 [counter]
fivegs_pcffunction_pa_policyamassosucc = 12 [counter]
```

The disagreement is over what the `[counter]` annotation MEANS:

* **Shot 1's reading:** "12 successful out of 12 requests = no
  failures, so MongoDB outage isn't impacting PCF."
* **Shot 2's reading:** "These are cumulative counters from process
  start. They don't tell us whether errors occurred at the moment of
  the anomaly. The cumulative-equality means nothing about
  current-window behavior."

Shot 2 is correct — Open5GS Prometheus counters monotonically
increase from process startup. A cumulative-equal read is consistent
with both "everything healthy" and "the failure happened in the
last 60s and the counter just hasn't decremented (because it can't,
it's monotonic)."

**This is exactly the kind of judgment call that single-shot
ratifies arbitrarily.** With multi-shot:

* **If shot 1 had won single-shot:** Synthesis would see h1 (mongo)
  DISPROVEN, h2 DISPROVEN, h3 DISPROVEN. With the candidate pool
  promoting mongo from h2+h3 alt_suspects, the bounded
  re-investigation might still rescue it — but Synthesis's
  explanation would carry the cumulative-counter misread as
  "evidence against mongo," producing a less coherent narrative.

* **If shot 2 had won single-shot:** Synthesis would see h1 (mongo)
  NOT_DISPROVEN with high evidence-strength, ratify mongo at high
  confidence. Right answer, but no signal that the underlying
  judgment had a coin-flip quality.

The forced INCONCLUSIVE → candidate pool → re-investigation path
produces a structurally cleaner outcome than either single-shot
branch would have:

1. INCONCLUSIVE on h1 admits the LLM judgment was unstable.
2. Candidate pool aggregator independently promotes mongo via h2/h3
   alt_suspects (no dependency on h1's outcome).
3. Re-investigation runs a fresh probe set on the explicit mongo
   hypothesis.
4. NOT_DISPROVEN on `h_promoted_mongo` is the structurally clean
   answer Synthesis ratifies.
5. Confidence cap downgrades to `medium` because the full evidence
   chain has friction (the AMBIGUOUS probe in re-investigation, the
   prior INCONCLUSIVE on h1).

The system converts noisy LLM judgment into a structured,
recoverable, and honestly-calibrated diagnosis.

## Composition: PR 5 + PR 6 + PR 3 as a designed system

This run shows the three Synthesis-stage / Phase-5-stage decisions
working in concert, not as independent guardrails:

**Decision C (PR 6) — variance reduction.** Catches the cumulative-
counter interpretation disagreement on h1. Without C, single-shot
would have ratified one or the other arbitrarily. C produces an
INCONCLUSIVE that *invites* downstream recovery rather than papering
over uncertainty.

**Decision E (PR 5) — verdict-tree-vs-diagnosis recovery.**
Triggered by C's INCONCLUSIVE plus the all-DISPROVEN tree on h2/h3.
Walks alt_suspects, promotes mongo on cross-corroboration (cited in
both h2 and h3 with strong-cite reasoning in both), runs a bounded
re-investigation. The re-investigation produces the clean
NOT_DISPROVEN that C/h1 couldn't.

**Decision F (PR 3) — confidence calibration.** The full evidence
chain isn't STRONG (h1 had a multi-shot disagreement, the
re-investigation's metric probe was AMBIGUOUS). F caps Synthesis's
emitted `high` to `medium`. The diagnosis text is correct; the
confidence is honest about the route it took to get there.

Each one alone helps less; together they convert the kind of
LLM-judgment instability documented in Part I of the
`challenge_with_stochastic_LLM_behavior.md` observations into a
structured, predictable outcome.

The "system" framing matters because it changes how we should think
about future Decisions:

* Decisions D / A2 / G / H prevent specific failure modes (mechanism
  scoping, IG re-scoping, narrative fabrication, NA mis-ranking).
  They're orthogonal — each closes a specific leak.
* Decisions C / E / F are *coupled* — they form a recovery pipeline
  for stochastic instability. C generates the signal (INCONCLUSIVE
  on disagreement) that E acts on (re-investigate); F calibrates the
  confidence on E's output. Removing any one of the three breaks
  the chain.

## What's still wanting

The h1 disagreement traces back to a probe-design issue:
`get_diagnostic_metrics` returns cumulative counters with no
window-rate framing. Shot 1 read them as point-in-time error rates;
shot 2 read them as cumulative-since-start values. Neither reading
is wrong in isolation — the probe spec didn't specify which
interpretation to use.

This is the kind of ambiguity Decision B (typed probe selection
from KB) would address. A KB-curated probe spec for *"test whether
MongoDB-dependent NFs are failing"* would explicitly specify:
* The right metric (probably `*_per_second_rate` derived metrics, or
  a window-delta on the cumulative counter).
* The expected reading direction in the anomaly window.
* The conflates_with that flags the cumulative-counter ambiguity.

Without B, NA + IG + Investigator collectively re-derive probe specs
each run, and the cumulative-vs-rate interpretation is left as an
implicit judgment call. Decision B would remove that judgment call
by authoring the right probe shape in the KB once and surfacing it
through `select_probes`.

This is the natural next item on the build queue.

## Cross-references

- ADR: `docs/ADR/structural_guardrails_for_llm_pipeline.md`
- Part I motivating observations: `docs/critical-observations/challenge_with_stochastic_LLM_behavior.md`
- Part II motivating observations: `docs/critical-observations/challenge_with_stochastic_LLM_behavior_part_II.md`
- Prior MongoDB Gone runs (variance baseline): `agentic_ops_v6/docs/agent_logs/run_20260423_*` through `run_20260430_*`
- Decision C implementation: `agentic_ops_v6/guardrails/investigator_consensus.py`
- Decision E implementation: `agentic_ops_v6/guardrails/synthesis_pool.py`
- Decision F implementation: `agentic_ops_v6/guardrails/confidence_cap.py`
