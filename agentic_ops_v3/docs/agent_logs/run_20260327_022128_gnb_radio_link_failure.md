# Episode Report: gNB Radio Link Failure

**Agent:** v3  
**Episode ID:** ep_20260327_021858_gnb_radio_link_failure  
**Date:** 2026-03-27T02:18:59.085383+00:00  
**Duration:** 148.9s  

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

## Symptoms Observed

Symptoms detected: **Yes**  
Observation iterations: 1

### Notable Log Lines

**amf:**
- `[32m03/26 22:18:59.170[0m: [[33mamf[0m] [1;32mINFO[0m: gNB-N2[172.22.0.23] connection refused!!! (../src/amf/amf-sm.c:997)`
**e2e_ue2:**
- `22:16:44.823           pjsua_core.c  .......TX 1051 bytes Response msg 200/UPDATE/cseq=1718 (tdta0x722350026c88) to UDP 172.22.0.21:5060:`
**icscf:**
- `[0;39;49m[0;36;49m 9(82) INFO: ims_icscf [cxdx_avp.c:140]: cxdx_get_avp(): cxdx_get_result_code: Failed finding avp`
- `[0;39;49m[0;36;49m10(83) INFO: ims_icscf [cxdx_avp.c:140]: cxdx_get_avp(): cxdx_get_result_code: Failed finding avp`
- `[0;39;49m[0;31;49m 1(74) ERROR: {1 1857 INVITE vDVm9oal4nXXdpmBR5lVpLs4WZLvL-xf initial_request} <script>: $ru => sip:001011234567891@ims.mnc001.mcc`
- `[0;39;49m[0;36;49m11(84) INFO: ims_icscf [cxdx_avp.c:140]: cxdx_get_avp(): cxdx_get_experimental_result_code: Failed finding avp`
- `[0;39;49m[0;36;49m12(85) INFO: ims_icscf [cxdx_avp.c:140]: cxdx_get_avp(): cxdx_get_result_code: Failed finding avp`
**nr_gnb:**
- `[2026-03-26 21:46:44.580] [ngap] [[31m[1merror[m] Unhandled NGAP initiating-message received (9)`
- `[2026-03-26 21:46:44.780] [ngap] [[31m[1merror[m] Unhandled NGAP initiating-message received (9)`
- `[2026-03-26 21:46:44.794] [ngap] [[31m[1merror[m] Unhandled NGAP initiating-message received (9)`
- `[2026-03-26 21:46:44.802] [ngap] [[31m[1merror[m] Unhandled NGAP initiating-message received (9)`
**pyhss:**
- `2026-03-26 22:18:59,500 INFO sqlalchemy.engine.Engine DESCRIBE `ims_hss_db`.`operation_log``
- `2026-03-26 22:18:59,500 INFO sqlalchemy.engine.Engine [raw sql] ()`
- `2026-03-26 22:18:59,503 INFO sqlalchemy.engine.Engine BEGIN (implicit)`
- `2026-03-26 22:18:59,503 INFO sqlalchemy.engine.Engine SELECT ims_subscriber.ims_subscriber_id AS ims_subscriber_ims_subscriber_id, ims_subscriber.msis`

## Ground Truth

**Failure domain:** data_plane  
**Protocol impact:** GTP-U  
**Affected components:** nr_gnb  
**Severity:** degraded

## Agent Diagnosis

**Model:** v3-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 141.2s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> Here is the final diagnosis of the RCA investigation.
> 
> ### Cause 1: Misconfigured Subscriber Profile in HSS (Primary)
> 
> *   **summary**: The S-CSCF is aborting registrations because the subscriber's profile fetched from the HSS is missing a required data parameter.
> *   **timeline**:
>     1.  UE sends a SIP REGISTER to the P-CSCF.
>     2.  P-CSCF successfully forwards the REGISTER to the S-CSCF.
>     3.  S-CSCF receives the REGISTER and queries the HSS for the user's profile.
>     4.  The S-CSCF attempts to match the user's Initial Filter Criteria (iFC) against its internal routing rules.
>     5.  The S-CSCF's configuration (`isc_match_filter_reg("0","location");`) requires a "location" parameter in the iFC.
>     6.  **Failure**: The subscriber's profile in the HSS lacks this "location" parameter, causing the match to fail.
>     7.  The S-CSCF logs "No REGISTER match found in filter criteria" and aborts processing without sending a SIP response.
>     8.  The P-CSCF times out waiting for a response.
> *   **root_cause**: A data misconfiguration exists in the HSS. The subscriber's Initial Filter Criteria (iFC) profile is missing a "location" parameter. The S-CSCF is configured to strictly require this parameter for processing REGISTER requests, and it aborts the entire flow when the parameter is not found in the data retrieved from the HSS.
> *   **affected_components**: `scscf`, `hss`
> *   **recommendation**: Update the affected subscriber profiles in the HSS database. The Initial Filter Criteria (iFC) for each user must be modified to include the required "location" parameter that the S-CSCF is configured to expect.
> *   **confidence**: high
> *   **explanation**: The root cause is a mismatch between S-CSCF configuration and HSS subscriber data. The S-CSCF is hard-coded to look for a "location" tag within the user profile it gets from the HSS during registration. For the failing user, this tag is missing from their profile data. This causes the S-CSCF to fail an internal check, log an error, and stop processing the registration entirely. Because it stops, it never sends a failure response, causing the P-CSCF to time out. The fix is to add the missing "location" data to the user's profile in the HSS.
> 
> ### Cause 2: Stale S-CSCF Assignment in HSS (Secondary)
> 
> *   **summary**: The subscriber's HSS record contains an invalid S-CSCF assignment timestamp from the future, which may disrupt registration state management.
> *   **timeline**:
>     1.  During a registration or re-registration attempt, the I-CSCF or S-CSCF queries the HSS for the user's current S-CSCF assignment.
>     2.  The HSS returns the user's data, which includes `scscf_timestamp: "2026-03-27T01:46:20Z"`.
>     3.  **Failure**: An IMS component may interpret this future timestamp as invalid or "stale," potentially leading it to reject the user's state as inconsistent.
> *   **root_cause**: The subscriber data in the HSS contains an anomalous `scscf_timestamp` with a value set in the future. This indicates data corruption or a bug in how timestamps are written to the HSS during previous registration events.
> *   **affected_components**: `hss`, `scscf`
> *   **recommendation**: Purge the invalid S-CSCF assignment data for the affected subscriber (IMSI '001011234567891') from the PyHSS database. This will force a clean registration where a new, valid S-CSCF is assigned with a correct timestamp.
> *   **confidence**: medium
> *   **explanation**: We discovered that the user's profile in the HSS has a timestamp from the future for its S-CSCF assignment. While not the direct cause of the "filter criteria" error, this is a significant data anomaly. It can cause unpredictable behavior in the IMS core, as components may see the user's registration state as invalid. This should be cleaned up to prevent future issues, but fixing the missing "location" parameter (Cause 1) will resolve the immediate registration failure.

### Scoring Breakdown

**Overall score: 0%**

**Scorer assessment:** The agent completely failed to identify the actual root cause, its affected components, the severity, or the type of fault, and was overconfident in its incorrect diagnosis.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | No | The agent completely missed the actual root cause, which was the killing of the 'nr_gnb' container, instead diagnosing HSS misconfigurations. |
| Component overlap | 0% | The agent did not identify the 'nr_gnb' container, which was the target of the injected fault. |
| Severity correct | No | The agent diagnosed a misconfiguration leading to registration failure, which is a functional impairment, not the complete outage implied by a container kill. |
| Fault type identified | No | The agent identified data misconfiguration/corruption as the fault type, not a container kill/crash. |
| Confidence calibrated | No | The agent expressed high confidence in a diagnosis that was entirely incorrect, indicating poor calibration. |

**Ranking:** The actual root cause was not identified or ranked by the agent.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 80,520 |
| Output tokens | 3,692 |
| Thinking tokens | 17,245 |
| **Total tokens** | **101,457** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| TriageAgent | 5,511 | 2 | 2 |
| EndToEndTracer | 50,791 | 4 | 5 |
| DispatchAgent | 3,423 | 0 | 1 |
| TransportSpecialist | 16,308 | 8 | 4 |
| SubscriberDataSpecialist | 5,538 | 1 | 2 |
| CoreSpecialist | 2,102 | 0 | 1 |
| IMSSpecialist | 12,085 | 2 | 3 |
| SynthesisAgent | 5,699 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 148.9s
