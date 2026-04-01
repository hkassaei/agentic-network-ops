# Episode Report: gNB Radio Link Failure

**Agent:** v4  
**Episode ID:** ep_20260331_190421_gnb_radio_link_failure  
**Date:** 2026-03-31T19:04:22.535800+00:00  
**Duration:** 170.9s  

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
- `[32m03/31 14:58:06.376[0m: [[33mamf[0m] [1;32mINFO[0m: gNB-N2[172.22.0.23] connection refused!!! (../src/amf/amf-sm.c:997)`
- `[32m03/31 15:00:07.269[0m: [[33mamf[0m] [1;32mINFO[0m: gNB-N2[172.22.0.23] connection refused!!! (../src/amf/amf-sm.c:997)`
- `[32m03/31 15:02:33.326[0m: [[33mamf[0m] [1;32mINFO[0m: gNB-N2[172.22.0.23] connection refused!!! (../src/amf/amf-sm.c:997)`
- `[32m03/31 15:04:22.603[0m: [[33mamf[0m] [1;32mINFO[0m: gNB-N2[172.22.0.23] connection refused!!! (../src/amf/amf-sm.c:997)`
**e2e_ue1:**
- `15:02:40.810            pjsua_acc.c  ...SIP registration failed, status=408 (Request Timeout)`
**e2e_ue2:**
- `15:02:22.904            pjsua_acc.c  ...SIP registration failed, status=408 (Request Timeout)`
- `[2026-03-31 15:02:34.798] [rrc] [[36mdebug[m] Signal lost for cell[6], total [0] cells in coverage`
- `[2026-03-31 15:02:34.799] [nas] [[31m[1merror[m] PLMN selection failure, no cells in coverage`
- `[2026-03-31 15:02:35.788] [rrc] [[33m[1mwarning[m] Acceptable cell selection failed, no cell is in coverage`
- `[2026-03-31 15:02:35.788] [rrc] [[31m[1merror[m] Cell selection failure, no suitable or acceptable cell found`
**icscf:**
- `[0;39;49m[0;31;49m28(73) ERROR: cdp [receiver.c:1064]: peer_connect(): Error opening connection to to 172.22.0.18 port 3875 proto  >Connection refus`
- `[0;39;49m[0;36;49m 9(54) INFO: ims_icscf [cxdx_avp.c:140]: cxdx_get_avp(): cxdx_get_result_code: Failed finding avp`
- `[0;39;49m[0;36;49m10(55) INFO: ims_icscf [cxdx_avp.c:140]: cxdx_get_avp(): cxdx_get_result_code: Failed finding avp`

## Ground Truth

**Failure domain:** data_plane  
**Protocol impact:** GTP-U  
**Affected components:** nr_gnb  
**Severity:** degraded

## Agent Diagnosis

**Model:** v4-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 159.9s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.
```

**Diagnosis:**

> Based on the provided evidence and specialist findings, I have identified two distinct root causes for the observed issues. The primary cause, directly addressed by the specialists, relates to an IMS registration failure, while a secondary, more fundamental issue exists with the 5G network's access layer.
> 
> ### Cause 1: Incomplete Subscriber Profile in HSS
> 
> *   **summary**: The S-CSCF is rejecting IMS registration attempts because the subscriber's profile in the HSS is incomplete. The Initial Filter Criteria (iFC) required to process the REGISTER message is missing, preventing the S-CSCF from handling the registration request.
> *   **timeline**: 
>     1.  A REGISTER message for the subscriber is received by the `scscf`.
>     2.  The `scscf` retrieves the subscriber's profile from the `pyhss` (HSS).
>     3.  The `scscf` processes the request and discovers that the iFC associated with the profile (`default_ifc.xml`) does not contain a required trigger for the REGISTER method.
>     4.  The `scscf` logs the error "No REGISTER match found in filter criteria" and rejects the registration.
> *   **root_cause**: This is a service provisioning failure. The subscriber's profile in the HSS database (`pyhss`) has not been correctly configured for IMS services. It points to a generic, default iFC file (`default_ifc.xml`) instead of a service-specific one. This default file lacks the necessary rule that instructs the S-CSCF on how to process an incoming `REGISTER` event, forcing a rejection.
> *   **affected_components**: 
>     *   `scscf`
>     *   `pyhss`
> *   **recommendation**: The subscriber's profile must be corrected in the HSS (`pyhss`). A complete Initial Filter Criteria (iFC) XML file, which includes a trigger for the `<method>REGISTER</method>`, needs to be created and associated with the subscriber's profile, replacing the incorrect `default_ifc.xml` reference.
> *   **confidence**: high
> *   **explanation**: The IMS registration is failing due to a simple data error. When a user registers, the S-CSCF (a key IMS component) queries the HSS (the user database) for a "recipe" called an iFC that tells it how to handle the request. For this user, the recipe is missing the step for "REGISTER". Without this instruction, the S-CSCF doesn't know what to do and safely rejects the request. The fix is to update the user's profile in the database with the correct, complete recipe.
> 
> ### Cause 2: RAN Disconnected from 5G Core
> 
> *   **summary**: The Radio Access Network (RAN), which connects user devices to the core, is completely disconnected. This is a critical failure that prevents any UE from attaching to the 5G network, establishing a data connection, or accessing any services.
> *   **timeline**: 
>     1.  The Triage report is generated, collecting status from all network components.
>     2.  The report identifies that the N2 link (RAN to AMF) and N3 link (RAN to UPF) are both `INACTIVE`.
>     3.  Metrics from the AMF (`ran_ue = 0.0`) confirm that no UEs are attached to the network via the RAN.
> *   **root_cause**: The gNodeB (the 5G base station component of the RAN) has no transport connection to the core network. It cannot communicate with the AMF for control plane signaling or the UPF for user data plane traffic. The underlying cause for the disconnection is not specified but is likely a configuration error on the gNB/core or a fundamental networking issue between the components.
> *   **affected_components**: 
>     *   `nr-gnb`
>     *   `amf`
>     *   `upf`
> *   **recommendation**: The connectivity between the RAN and the 5G Core must be restored.
>     1.  Verify the `nr-gnb` container/process is running.
>     2.  Check the gNB's startup logs for errors related to SCTP (N2) or GTP (N3) connection establishment.
>     3.  Confirm that the gNB's configuration contains the correct IP addresses for the AMF and UPF.
>     4.  Verify basic network reachability (e.g., using ping) from the gNB's host to the core component hosts.
> *   **confidence**: high
> *   **explanation**: This is a fundamental transport-layer failure. No users can connect to the 5G network because the radio access network (the cell tower) is completely disconnected from the main core network. All services, including IMS, are inaccessible to real users until this link is restored. You must investigate why the `nr-gnb` cannot establish a connection with the `amf` and `upf`. Checking the gNB's status, logs, and network configuration would be the first steps.

### Scoring Breakdown

**Overall score: 60%**

**Scorer assessment:** The agent correctly identified the technical root cause and affected component for the injected fault, but incorrectly prioritized it as a secondary issue behind an unrelated IMS problem.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | No | The agent correctly identified the gNB disconnection as a root cause (Cause 2), which is a direct result of the injected fault, but it was ranked as a 'secondary' issue, not the primary one. |
| Component overlap | 100% | The agent correctly identified 'nr-gnb' as an affected component in Cause 2, which directly matches the injected target 'nr_gnb'. |
| Severity correct | Yes | The agent described the gNB issue as a 'critical failure' preventing UE attachment, which accurately reflects the impact of a container kill (outage). |
| Fault type identified | Yes | The agent's recommendation to 'Verify the nr-gnb container/process is running' strongly implies that the container being down or killed is the underlying issue, correctly identifying the class of failure. |
| Confidence calibrated | Yes | The agent expressed 'high' confidence for Cause 2, which was largely correct in identifying the component, severity, and hinting at the fault type. |

**Ranking position:** #2 — The correct root cause (RAN Disconnected) was listed as the second candidate ('secondary') by the agent.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 131,333 |
| Output tokens | 5,169 |
| Thinking tokens | 23,835 |
| **Total tokens** | **160,337** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| TriageAgent | 11,761 | 2 | 3 |
| EndToEndTracer | 31,193 | 3 | 4 |
| DispatchAgent | 3,543 | 0 | 1 |
| IMSSpecialist | 34,423 | 7 | 8 |
| TransportSpecialist | 58,266 | 8 | 9 |
| SubscriberDataSpecialist | 9,376 | 1 | 2 |
| CoreSpecialist | 3,787 | 0 | 1 |
| SynthesisAgent | 7,988 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 170.9s
