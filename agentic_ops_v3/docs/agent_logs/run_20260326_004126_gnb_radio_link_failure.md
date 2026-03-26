# Episode Report: gNB Radio Link Failure

**Agent:** v3  
**Episode ID:** ep_20260326_003858_gnb_radio_link_failure  
**Date:** 2026-03-26T00:38:59.480013+00:00  
**Duration:** 145.7s  

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
- `[32m03/25 20:21:52.206[0m: [[33msbi[0m] [1;32mINFO[0m: [b6805032-27b3-41f1-9a04-3f025a6967cf] Setup NF Instance [type:PCF] (../lib/sbi/path.c:30`
- `[32m03/25 20:38:59.603[0m: [[33mamf[0m] [1;32mINFO[0m: gNB-N2[172.22.0.23] connection refused!!! (../src/amf/amf-sm.c:997)`
**e2e_ue1:**
- `[2026-03-25 20:21:50.326] [nas] [[36mdebug[m] Initial registration required due to [DUE-TO-SERVICE_REJECT]`
**e2e_ue2:**
- `20:37:06.431            pjsua_acc.c  ...SIP registration failed, status=408 (Request Timeout)`
**icscf:**
- `[0;39;49m[0;31;49m28(78) ERROR: cdp [receiver.c:1073]: peer_connect(): Timeout or error opening connection to to 172.22.0.18 port 3875 proto  >Opera`
- `[0;39;49m[0;31;49m28(78) ERROR: cdp [receiver.c:1073]: peer_connect(): Timeout or error opening connection to to 172.22.0.18 port 3875 proto  >Opera`
- `[0;39;49m[0;31;49m28(78) ERROR: cdp [receiver.c:1064]: peer_connect(): Error opening connection to to 172.22.0.18 port 3875 proto  >No route to host`
- `[0;39;49m[0;31;49m28(78) ERROR: cdp [receiver.c:1064]: peer_connect(): Error opening connection to to 172.22.0.18 port 3875 proto  >No route to host`
- `[0;39;49m[0;31;49m28(78) ERROR: cdp [receiver.c:1064]: peer_connect(): Error opening connection to to 172.22.0.18 port 3875 proto  >Connection refus`
**nr_gnb:**
- `[2026-03-25 20:36:35.933] [gtp] [[31m[1merror[m] Uplink data failure, PDU session not found. UE[1] PSI[2]`
- `[2026-03-25 20:36:37.340] [gtp] [[31m[1merror[m] Uplink data failure, PDU session not found. UE[2] PSI[2]`
- `[2026-03-25 20:36:37.934] [gtp] [[31m[1merror[m] Uplink data failure, PDU session not found. UE[1] PSI[2]`
- `[2026-03-25 20:36:41.933] [gtp] [[31m[1merror[m] Uplink data failure, PDU session not found. UE[1] PSI[2]`
- `[2026-03-25 20:36:45.933] [gtp] [[31m[1merror[m] Uplink data failure, PDU session not found. UE[1] PSI[2]`
**smf:**
- `[32m03/25 19:52:55.606[0m: [[33msmf[0m] [1;33mERROR[0m: No N1N2MessageTransferRspData [status:504] (../src/smf/namf-handler.c:61)`
- `[32m03/25 19:52:55.778[0m: [[33msmf[0m] [1;33mERROR[0m: No N1N2MessageTransferRspData [status:504] (../src/smf/namf-handler.c:61)`
- `[32m03/25 19:52:55.801[0m: [[33msmf[0m] [1;33mERROR[0m: No N1N2MessageTransferRspData [status:504] (../src/smf/namf-handler.c:61)`
- `[32m03/25 19:52:55.815[0m: [[33msmf[0m] [1;33mERROR[0m: No N1N2MessageTransferRspData [status:504] (../src/smf/namf-handler.c:61)`
- `[32m03/25 19:55:14.603[0m: [[33msmf[0m] [1;33mERROR[0m: No N1N2MessageTransferRspData [status:504] (../src/smf/namf-handler.c:61)`

## Ground Truth

**Failure domain:** data_plane  
**Protocol impact:** GTP-U  
**Affected components:** nr_gnb  
**Severity:** degraded

## Agent Diagnosis

**Model:** v3-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 137.3s

**Diagnosis:**

> Based on my analysis of the specialist findings, there are two distinct and independent root causes for the observed failures. The 5G Core failure is the most foundational, preventing any user from accessing the network, while the IMS Core failure would prevent IMS services even if the 5G network were healthy.
> 
> ### **Identified Cause 1 (Most Probable Root Cause)**
> 
> *   **summary**: The 5G Access and Mobility Management Function (AMF) is not listening on its N2 interface port (SCTP/38412). This prevents the gNB from establishing a control plane connection, which is a prerequisite for any UE to attach to the 5G network.
> *   **timeline**:
>     1.  `[nr_gnb]` (at `172.22.0.23`) attempts to establish an SCTP connection to the `[amf]` for the N2 interface.
>     2.  `[amf]` The host operating system receives the connection request but, finding no process listening on SCTP port 38412, rejects it.
>     3.  `20:38:59.603` `[amf]` The AMF application logs that a connection from the gNB was refused, a symptom of the missing listener.
>     4.  `20:21:50.326` `[e2e_ue1]` The UE's attempt to attach to the network fails, resulting in a "SERVICE\_REJECT" because it cannot communicate with a functional AMF.
> *   **root_cause**: The AMF application process is not bound to SCTP port 38412. This is a violation of the **Listener Law**: a node cannot process a request if no service is listening on the target port and protocol. The "Connection refused" error is the OS kernel's direct response to this condition, making this a definitive transport-layer failure that precedes any application-level logic.
> *   **affected_components**: `amf`, `nr_gnb`, `e2e_ue1`, `smf`
> *   **recommendation**: Restart the `amf` container process. Verify its configuration to ensure it is set to listen for N2 connections on SCTP port 38412 on its designated network interface.
> *   **confidence**: high
> *   **explanation**: The primary reason for the total network outage is a failure within the AMF. The gNB, which connects cell phones to the core network, is trying to talk to the AMF, but the AMF isn't "picking up the phone." Our transport analysis confirms no service is listening on the required N2 port (SCTP/38412) inside the AMF container. This `Connection refused` error at the transport layer is blocking all UEs from attaching to the network, which is why `ran_ue` is zero and why subsequent PDU session and data plane failures are occurring.
> 
> ### **Identified Cause 2**
> 
> *   **summary**: The IMS Home Subscriber Server (HSS) is not listening on its Diameter port (TCP/3875). This prevents the I-CSCF from authenticating users, causing all IMS registration attempts to fail with a timeout.
> *   **timeline**:
>     1.  `[e2e_ue2]` A user equipment attempts to register with the IMS network by sending a SIP `REGISTER` request.
>     2.  `[pcscf]` The P-CSCF receives the `REGISTER` and forwards it to the `[icscf]`.
>     3.  `[icscf]` To authorize the user and find their assigned S-CSCF, the I-CSCF attempts to open a TCP connection to the `[pyhss]` (HSS) at `172.22.0.18:3875`.
>     4.  `[icscf]` logs show the connection is refused (`Connection refused`). The HSS host kernel rejects the connection because no process is listening on port 3875.
>     5.  `20:37:06.431` `[e2e_ue2]` The SIP transaction times out because the I-CSCF never gets a response from the HSS and cannot proceed. The UE receives a `408 (Request Timeout)`.
> *   **root_cause**: The HSS application process (`pyhss`) is not bound to TCP port 3875. Similar to the AMF issue, this is a direct violation of the **Listener Law**. The I-CSCF's `Connection refused` and `No route to host` logs, coupled with the trace showing a failed Diameter UAR, are direct evidence of this transport-level failure.
> *   **affected_components**: `pyhss`, `icscf`, `pcscf`, `e2e_ue2`
> *   **recommendation**: Restart the `pyhss` container process. Verify its configuration to ensure it is correctly bound and listening for Diameter connections on TCP port 3875.
> *   **confidence**: high
> *   **explanation**: Separately from the 5G core issue, the IMS system is also down. When a user tries to register for voice or messaging services, the I-CSCF must check their profile in the HSS database. However, the HSS is not listening for these requests on its standard Diameter port (TCP/3875). The logs definitively show a "Connection refused" error, confirming a transport-level problem. Without access to the HSS, no user can be authenticated, and all IMS registrations will fail.

### Scoring Breakdown

**Overall score: 40%**

**Scorer assessment:** The agent completely missed the actual root cause of the gNB container kill, instead fabricating two distinct 'listener law' violations for the AMF and HSS, despite correctly identifying the 'nr_gnb' as an affected component and assessing the severity as an outage.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | No | The agent failed to identify the actual injected fault, which was a 'container_kill' on the 'nr_gnb' container, instead diagnosing two 'listener law' violations on the AMF and HSS. |
| Component overlap | 100% | The agent correctly listed 'nr_gnb' as an affected component in its primary diagnosis, which was the sole injected target. |
| Severity correct | Yes | The agent's assessment of a 'total network outage' or 'system down' aligns with the severe impact of a container kill, even though it attributed it to the wrong root cause. |
| Fault type identified | No | The agent identified 'listener law' violations and 'connection refused' errors, which are application/service configuration issues, not a 'container_kill' fault type. |
| Confidence calibrated | No | The agent expressed 'high' confidence in a diagnosis that was entirely incorrect regarding the root cause and fault type, indicating poor calibration. |

**Ranking:** Neither of the two causes identified by the agent was correct.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 162,540 |
| Output tokens | 5,321 |
| Thinking tokens | 22,319 |
| **Total tokens** | **190,180** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| TriageAgent | 9,776 | 2 | 2 |
| EndToEndTracer | 104,011 | 7 | 8 |
| DispatchAgent | 6,933 | 0 | 1 |
| TransportSpecialist | 28,626 | 6 | 5 |
| IMSSpecialist | 9,950 | 1 | 2 |
| SubscriberDataSpecialist | 7,126 | 0 | 1 |
| CoreSpecialist | 14,529 | 2 | 3 |
| SynthesisAgent | 9,229 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 145.7s
