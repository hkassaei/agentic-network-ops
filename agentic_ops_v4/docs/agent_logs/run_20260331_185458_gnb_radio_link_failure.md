# Episode Report: gNB Radio Link Failure

**Agent:** v4  
**Episode ID:** ep_20260331_185453_gnb_radio_link_failure  
**Date:** 2026-03-31T18:54:54.715480+00:00  
**Duration:** 2.6s  

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
- `[32m03/31 14:54:54.793[0m: [[33mamf[0m] [1;32mINFO[0m: gNB-N2[172.22.0.23] connection refused!!! (../src/amf/amf-sm.c:997)`
**e2e_ue1:**
- `14:51:23.946            pjsua_acc.c  ...SIP registration failed, status=408 (Request Timeout)`
**e2e_ue2:**
- `14:51:23.478            pjsua_acc.c  ...SIP registration failed, status=408 (Request Timeout)`
**icscf:**
- `[0;39;49m[0;31;49m28(73) ERROR: cdp [receiver.c:1064]: peer_connect(): Error opening connection to to 172.22.0.18 port 3875 proto  >Connection refus`
- `[0;39;49m[0;36;49m 9(54) INFO: ims_icscf [cxdx_avp.c:140]: cxdx_get_avp(): cxdx_get_result_code: Failed finding avp`
- `[0;39;49m[0;36;49m10(55) INFO: ims_icscf [cxdx_avp.c:140]: cxdx_get_avp(): cxdx_get_result_code: Failed finding avp`
**nr_gnb:**
- `[2026-03-31 13:54:44.605] [rls] [[36mdebug[m] UE[1] signal lost`
- `[2026-03-31 14:04:01.771] [rls] [[36mdebug[m] UE[2] signal lost`
- `[2026-03-31 14:04:02.775] [rls] [[36mdebug[m] UE[1] signal lost`
- `[2026-03-31 14:21:14.791] [rls] [[36mdebug[m] UE[4] signal lost`

## Ground Truth

**Failure domain:** data_plane  
**Protocol impact:** GTP-U  
**Affected components:** nr_gnb  
**Severity:** degraded

## Agent Diagnosis

Challenge mode was not run — no agent diagnosis available.

## Resolution

**Heal method:** scheduled  
**Recovery time:** 2.6s
