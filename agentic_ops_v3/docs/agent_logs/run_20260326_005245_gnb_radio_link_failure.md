# Episode Report: gNB Radio Link Failure

**Agent:** v3  
**Episode ID:** ep_20260326_005029_gnb_radio_link_failure  
**Date:** 2026-03-26T00:50:30.062827+00:00  
**Duration:** 134.5s  

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
- `[32m03/25 20:50:30.138[0m: [[33mamf[0m] [1;32mINFO[0m: gNB-N2[172.22.0.23] connection refused!!! (../src/amf/amf-sm.c:997)`
**e2e_ue1:**
- `20:46:26.366            pjsua_acc.c  Error sending keep-alive packet: Network is unreachable [status=120101]`
- `20:46:38.367            pjsua_acc.c  Error sending keep-alive packet: Network is unreachable [status=120101]`
- `20:46:52.367            pjsua_acc.c  Error sending keep-alive packet: Network is unreachable [status=120101]`
- `20:47:04.368            pjsua_acc.c  Error sending keep-alive packet: Network is unreachable [status=120101]`
- `20:47:18.368            pjsua_acc.c  Error sending keep-alive packet: Network is unreachable [status=120101]`
**e2e_ue2:**
- `20:47:05.056      tsx0x76a6a4038b98  ..Failed to send Request msg REGISTER/cseq=23992 (tdta0x76a6a400f608)! err=120101 (Network is unreachable)`
- `20:47:05.056            pjsua_acc.c  ....SIP registration failed, status=503 (Network is unreachable)`
- `20:47:05.056              sip_reg.c  .Error sending request: Network is unreachable`
**icscf:**
- `[0;39;49m[0;31;49m28(78) ERROR: cdp [receiver.c:1073]: peer_connect(): Timeout or error opening connection to to 172.22.0.18 port 3875 proto  >Opera`
- `[0;39;49m[0;31;49m28(78) ERROR: cdp [receiver.c:1073]: peer_connect(): Timeout or error opening connection to to 172.22.0.18 port 3875 proto  >Opera`
- `[0;39;49m[0;31;49m28(78) ERROR: cdp [receiver.c:1064]: peer_connect(): Error opening connection to to 172.22.0.18 port 3875 proto  >No route to host`
- `[0;39;49m[0;31;49m28(78) ERROR: cdp [receiver.c:1064]: peer_connect(): Error opening connection to to 172.22.0.18 port 3875 proto  >No route to host`
- `[0;39;49m[0;31;49m28(78) ERROR: cdp [receiver.c:1064]: peer_connect(): Error opening connection to to 172.22.0.18 port 3875 proto  >Connection refus`
**pyhss:**
- `2026-03-25 20:50:30,503 INFO sqlalchemy.engine.Engine BEGIN (implicit)`
- `2026-03-25 20:50:30,503 INFO sqlalchemy.engine.Engine SELECT ims_subscriber.ims_subscriber_id AS ims_subscriber_ims_subscriber_id, ims_subscriber.msis`
- `2026-03-25 20:50:30,503 INFO sqlalchemy.engine.Engine [cached since 2323s ago] (0, 200)`
**smf:**
- `[32m03/25 20:42:02.034[0m: [[33msbi[0m] [1;32mINFO[0m: [b6805032-27b3-41f1-9a04-3f025a6967cf] Setup NF Instance [type:PCF] (../lib/sbi/path.c:30`
- `[32m03/25 20:42:02.035[0m: [[33msbi[0m] [1;32mINFO[0m: [b6805032-27b3-41f1-9a04-3f025a6967cf] Setup NF Instance [type:PCF] (../lib/sbi/path.c:30`

## Ground Truth

**Failure domain:** data_plane  
**Protocol impact:** GTP-U  
**Affected components:** nr_gnb  
**Severity:** degraded

## Agent Diagnosis

**Model:** v3-adk/gemini-2.5-flash+gemini-2.5-pro  
**Time to diagnosis:** 126.6s

### Prompt to RCA Agent

```
The 5G SA + IMS stack is experiencing issues. Investigate and diagnose the root cause.

Recent error logs observed:
  [amf] [32m03/25 20:50:30.138[0m: [[33mamf[0m] [1;32mINFO[0m: gNB-N2[172.22.0.23] connection refused!!! (../src/amf/amf-sm.c:997)
  [icscf] [0;39;49m[0;31;49m28(78) ERROR: cdp [receiver.c:1073]: peer_connect(): Timeout or error opening connection to to 172.22.0.18 port 3875 proto  >Operation now in progress
  [icscf] [0;39;49m[0;31;49m28(78) ERROR: cdp [receiver.c:1073]: peer_connect(): Timeout or error opening connection to to 172.22.0.18 port 3875 proto  >Operation now in progress
  [icscf] [0;39;49m[0;31;49m28(78) ERROR: cdp [receiver.c:1064]: peer_connect(): Error opening connection to to 172.22.0.18 port 3875 proto  >No route to host
  [icscf] [0;39;49m[0;31;49m28(78) ERROR: cdp [receiver.c:1064]: peer_connect(): Error opening connection to to 172.22.0.18 port 3875 proto  >No route to host
  [icscf] [0;39;49m[0;31;49m28(78) ERROR: cdp [receiver.c:1064]: peer_connect(): Error opening connection to to 172.22.0.18 port 3875 proto  >Connection refused
  [pyhss] 2026-03-25 20:50:30,503 INFO sqlalchemy.engine.Engine BEGIN (implicit)
  [pyhss] 2026-03-25 20:50:30,503 INFO sqlalchemy.engine.Engine SELECT ims_subscriber.ims_subscriber_id AS ims_subscriber_ims_subscriber_id, ims_subscriber.msisdn AS ims_subscriber_msisdn, ims_subscriber.msisdn_list AS ims_subscriber_msisdn_list, ims_subscriber.imsi AS ims_subscriber_imsi, ims_subscriber.ifc_path AS ims_subscriber_ifc_path, ims_subscriber.pcscf AS ims_subscriber_pcscf, ims_subscriber.pcscf_realm AS ims_subscriber_pcscf_realm, ims_subscriber.pcscf_active_session AS ims_subscriber_pcscf_active_session, ims_subscriber.pcscf_timestamp AS ims_subscriber_pcscf_timestamp, ims_subscriber.pcscf_peer AS ims_subscriber_pcscf_peer, ims_subscriber.xcap_profile AS ims_subscriber_xcap_profile, ims_subscriber.sh_profile AS ims_subscriber_sh_profile, ims_subscriber.scscf AS ims_subscriber_scscf, ims_subscriber.scscf_timestamp AS ims_subscriber_scscf_timestamp, ims_subscriber.scscf_realm AS ims_subscriber_scscf_realm, ims_subscriber.scscf_peer AS ims_subscriber_scscf_peer, ims_subscriber.sh_template_path AS ims_subscriber_sh_template_path, ims_subscriber.last_modified AS ims_subscriber_last_modified 
  [pyhss] 2026-03-25 20:50:30,503 INFO sqlalchemy.engine.Engine [cached since 2323s ago] (0, 200)
  [smf] [32m03/25 20:42:02.034[0m: [[33msbi[0m] [1;32mINFO[0m: [b6805032-27b3-41f1-9a04-3f025a6967cf] Setup NF Instance [type:PCF] (../lib/sbi/path.c:307)
  [smf] [32m03/25 20:42:02.035[0m: [[33msbi[0m] [1;32mINFO[0m: [b6805032-27b3-41f1-9a04-3f025a6967cf] Setup NF Instance [type:PCF] (../lib/sbi/path.c:307)

```

**Diagnosis:**

> This report details two distinct, critical root causes for the service outage. The primary cause, investigated via the trace, is a failure in the IMS stack. A secondary, but equally critical, failure was identified in the 5G Core control plane.
> 
> ### Cause #1: HSS Diameter Service Not Listening
> 
> *   **summary**: The HSS service is not listening for Diameter connections, causing all IMS authentication requests from the I-CSCF to fail with "Connection refused."
> *   **timeline**:
>     *   (Trace Start) S-CSCF sends a Diameter User-Authorization-Request (UAR) to the I-CSCF for routing to the HSS.
>     *   (Failure Point) I-CSCF attempts to open a TCP connection to the HSS at `172.22.0.18:3875`.
>     *   `[icscf]` log: `ERROR: ... peer_connect(): Error opening connection to to 172.22.0.18 port 3875 proto >Connection refused`
>     *   (Result) The HSS OS kernel rejects the connection because no application is listening on port 3875. The UAR is dropped. The IMS registration times out and fails.
> *   **root_cause**: The `pyhss` container has started, and its backend database connection is active (per `sqlalchemy` logs), but the primary Diameter service has either failed to initialize or is misconfigured. It has not opened the required listening socket on port 3875 for the Diameter Cx interface. Therefore, while the HSS server is reachable on the network (IP layer), the specific service (application layer) required for IMS authentication is unavailable.
> *   **affected_components**: `icscf`, `pyhss` (HSS), `scscf`.
> *   **recommendation**: Investigate the `pyhss` service configuration. Ensure the Diameter interface is enabled and configured to listen on TCP port `3875` on all necessary network interfaces. Restart the `pyhss` container and check its startup logs for any errors related to Diameter socket binding.
> *   **confidence**: high
> *   **explanation**: The root cause of the IMS registration failure is that the HSS is not running its Diameter service correctly. Although the I-CSCF can reach the HSS server over the network, the HSS application itself isn't listening for connections on the designated Diameter port (3875). The server's operating system is therefore correctly rejecting the connection requests. This prevents the S-CSCF from authenticating users, causing all IMS registrations to fail. The fix is to ensure the HSS application is configured to listen on port 3875 and is started successfully.
> 
> ---
> 
> ### Cause #2: AMF Refusing gNB Control Plane Connection
> 
> *   **summary**: The AMF is actively refusing the N2 control plane connection from the gNB, preventing any UEs from attaching to the 5G network.
> *   **timeline**:
>     *   (Event Start) The gNB attempts to establish an SCTP-based N2 interface connection with the AMF.
>     *   `[amf]` `03/25 20:50:30.138`: log: `INFO: gNB-N2[172.22.0.23] connection refused!!!`
>     *   (Result) The N2 setup fails. The gNB cannot connect to the 5G Core. No UEs can perform initial registration or establish PDU sessions. This is reflected in the triage metric `amf_ran_ue_registered = 0.0`.
> *   **root_cause**: The AMF application is running but is explicitly rejecting the N2 setup request from the gNB. This is not a simple "port not listening" issue, but an application-level rejection. The cause is likely a misconfiguration in the AMF's N2 interface settings, such as an incorrect gNB IP address in an allow-list, a PLMN ID mismatch, or an issue with the SCTP configuration parameters.
> *   **affected_components**: `amf`, `gnb`.
> *   **recommendation**: Review the AMF configuration files related to the N2 interface. Verify that the gNB's IP address (`172.22.0.23`) is correctly configured and permitted. Check for any PLMN or TAC mismatches between the AMF and gNB configurations.
> *   **confidence**: high
> *   **explanation**: A second, independent failure is occurring in the 5G control plane. The AMF is rejecting the primary N2 connection from the gNB. This prevents any user equipment from attaching to the network in the first place, effectively cutting off access to all 5G services, including IMS. This is an application-level denial, not a simple network error, pointing to a specific misconfiguration within the AMF concerning its communication partner, the gNB. Even if the HSS issue were resolved, no users could register because they cannot first connect to the underlying 5G network.

### Scoring Breakdown

**Overall score: 40%**

**Scorer assessment:** The agent correctly identified affected components and the severity of the impact but failed to identify the actual root cause (gNB container kill) and the specific fault type, instead diagnosing two distinct misconfiguration issues with high confidence.

| Dimension | Result | Rationale |
|-----------|--------|-----------|
| Root cause correct | No | The agent failed to identify the actual injected fault, which was a 'container_kill' on the 'nr_gnb'. Instead, it diagnosed two distinct misconfiguration issues (HSS Diameter service not listening and AMF refusing gNB connection) as primary causes. |
| Component overlap | 100% | The agent correctly identified 'gnb' (nr_gnb) as an affected component in its second cause, which was the target of the injected fault. |
| Severity correct | Yes | The agent correctly assessed the impact as a 'service outage' and 'cutting off access to all 5G services', which aligns with the 'container_kill' fault causing an outage. |
| Fault type identified | No | The agent did not identify the fault type as a 'container_kill'; instead, it described application-level misconfigurations or service failures. |
| Confidence calibrated | No | The agent expressed 'high' confidence for both diagnoses, despite neither being the actual root cause or fault type, indicating poor calibration. |

**Ranking:** Neither of the agent's ranked causes was the correct root cause of the injected fault.


### Token Usage

| Metric | Count |
|--------|-------|
| Input tokens | 243,248 |
| Output tokens | 4,263 |
| Thinking tokens | 17,423 |
| **Total tokens** | **264,934** |

**Per-phase breakdown:**

| Phase | Tokens | Tool Calls | LLM Calls |
|-------|--------|------------|-----------|
| TriageAgent | 9,928 | 2 | 2 |
| EndToEndTracer | 174,859 | 6 | 7 |
| DispatchAgent | 5,502 | 0 | 1 |
| TransportSpecialist | 43,562 | 9 | 6 |
| IMSSpecialist | 24,162 | 3 | 4 |
| SynthesisAgent | 6,921 | 0 | 1 |


## Resolution

**Heal method:** scheduled  
**Recovery time:** 134.5s
