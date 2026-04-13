# ADR: Telco-Grade Resilience Patterns — SMF State Recovery and CSCF Cache Consistency

**Date:** 2026-04-12
**Status:** Reference (design guidance for future production hardening)
**Related:**
- Episode that surfaced the gap: [`docs/critical-observations/run_20260413_024554_data_plane_degradation.md`](../critical-observations/run_20260413_024554_data_plane_degradation.md)
- Prior critical observation on UPF packet loss effects: [`docs/critical-observations/run_20260409_231143_data_plane_degradation.md`](../critical-observations/run_20260409_231143_data_plane_degradation.md)

---

## Context

During the Data Plane Degradation chaos scenario (run_20260413_024554), 30% packet loss on the UPF caused a cascading SMF crash — the SMF hit a fatal assertion (`ogs_nas_build_qos_flow_descriptions: Assertion 'num_of_flow_description' failed` at `../lib/nas/5gs/types.c:413`) due to inconsistent QoS flow state caused by PFCP message loss on the N4 interface.

After the SMF was manually restarted, two problems remained:

1. **SMF had zero state** — no active UEs, no bearers, no PFCP sessions. All PDU session context was lost with the crash. The only recovery path was restarting the UEs to force fresh PDU session establishment from scratch.

2. **CSCFs had stale registration caches** — `ims_usrloc_pcscf:registered_contacts` showed 4 (expected 2) and `ims_usrloc_scscf:active_contacts` showed 4 (expected 2). The UEs had re-registered without the previous registrations being deregistered, doubling the contact count. The only fix was restarting the CSCFs to clear the stale entries.

Both problems stem from the same architectural gap: **this lab stack treats NF session state as in-process memory with no external persistence or synchronization.** This ADR documents the 3GPP-defined mechanisms that production networks use to solve these problems, as a reference for future production hardening.

---

## Part 1: SMF State Recovery — UDSF and PFCP Session Adoption

### The Problem

When the SMF crashes, all PDU session context is lost: SUPI-to-session mappings, IP address allocations, QoS flow state, PFCP session bindings to the UPF, and PCF policy associations. The UPF still has its forwarding rules (PDRs/FARs) installed, and the GTP-U tunnels between gNB and UPF are still up, but no SMF is managing them. UEs must re-register and re-establish PDU sessions from scratch.

### 3GPP Solution: Unstructured Data Storage Function (UDSF)

**TS 23.501 clause 6.2.10** defines the UDSF — a network function purpose-built for externalized NF state storage. Any NF can use UDSF to persist its session context so that a peer instance can recover or take over without UE involvement.

**Service API:** Nudsf (defined in **TS 29.598**). The UDSF exposes a simple key-value storage API:
- `Nudsf_DataRepository_Create` — store a record
- `Nudsf_DataRepository_Query` — retrieve by key
- `Nudsf_DataRepository_Update` — modify existing record
- `Nudsf_DataRepository_Delete` — remove record

**How SMF uses UDSF for crash recovery:**

1. **During normal operation**, the SMF writes its PDU session context to the UDSF after every state change — session creation, modification, QoS flow setup, IP address allocation, PFCP session binding. The context is keyed by SUPI + PDU session ID.

2. **State content stored per session:**
   - SUPI and PDU session ID
   - DNN and S-NSSAI (network slice)
   - UPF selection and PFCP session details (F-SEID, PDRs, FARs)
   - QoS rules and flow descriptions
   - IP address allocation (IPv4/IPv6)
   - PCF policy association context
   - AMF association (serving AMF address)

3. **On SMF failure**, the AMF detects the SMF is unresponsive via NF heartbeat failure or NRF status notification (**TS 23.501 clause 5.21** — NF status subscription). The AMF selects a new SMF instance via NRF discovery (Nnrf_NFDiscovery).

4. **The new SMF retrieves session context from UDSF** using the SUPI + PDU session ID. It reconstructs its internal state machine from the stored data without any UE interaction.

5. **The new SMF re-establishes control over the UPF** via PFCP (see next section).

6. **The UE is completely unaware.** The GTP-U data plane tunnel (gNB ↔ UPF) was never interrupted. The UE's IP address, QoS flows, and PDU session all remain intact.

**Spec references:**
- **TS 23.501 clause 6.2.10** — UDSF architecture and role
- **TS 23.502 clause 4.3.4** — SMF context transfer procedures
- **TS 29.598** — Nudsf service API specification

### N+K Redundancy Model

Production SMFs run in an **N+K pool** behind the NRF:

- **N active instances** handle sessions, all registered with the NRF as available SMF instances
- **K standby instances** are warm and ready to take over
- The AMF selects an SMF via NRF service discovery. If the selected SMF fails, the AMF queries the NRF again and gets a different instance from the pool
- Session state in UDSF is keyed by SUPI + session ID, **not by SMF instance** — any SMF in the pool can read and adopt any session
- NRF subscription mechanism (**TS 23.501 clause 5.21**) provides real-time NF status change notifications so the AMF learns about SMF failures without polling

### PFCP Session Recovery (TS 29.244)

The PFCP protocol has built-in mechanisms for handling SMF restarts at the association level:

**Recovery Timestamp IE (TS 29.244 clause 8.2.25):**
- Every PFCP Association Setup Request carries a Recovery Timestamp — the time when the PFCP entity last restarted
- When a new SMF establishes a PFCP association with the UPF, the UPF compares the Recovery Timestamp with the previous one from the old SMF
- A different timestamp signals that the SMF restarted, and the UPF can take appropriate action (e.g., marking orphaned sessions)

**PFCP Session Set Deletion (TS 29.244 clause 7.4.14):**
- The UPF can delete all sessions belonging to a failed SMF, identified by its F-SEID (Fully-qualified SEID)
- Alternatively, the new SMF can adopt existing sessions by sending a PFCP Session Modification Request with its own F-SEID, effectively transferring ownership

**Session Adoption Flow:**
1. New SMF reads PDU session context from UDSF (knows UPF address, original F-SEID, PDR/FAR details)
2. New SMF establishes PFCP association with the UPF (new Recovery Timestamp)
3. New SMF sends PFCP Session Modification for each adopted session, updating the F-SEID to its own
4. UPF continues forwarding with the same PDRs/FARs — only the controlling SMF identity has changed
5. Data plane is never interrupted

**Spec reference:** **TS 29.244** — PFCP protocol specification (clauses 7.4.14, 8.2.25)

### AMF-SMF Context Restoration

When the AMF needs to redirect a UE's session management to a new SMF (**TS 23.502 clause 4.3.4**):

1. AMF sends `Nsmf_PDUSession_CreateSMContext` to the new SMF with a `SmContextCreateData` that includes the old SM context reference
2. The new SMF uses this reference to retrieve the full context from UDSF
3. The new SMF responds to the AMF with the new SM context reference
4. All subsequent session management for this UE goes to the new SMF
5. The UE is not involved in this transfer

### What Open5GS Lacks

Open5GS does not implement:
- **UDSF** — all session state is in-process memory, lost on crash
- **N+K pooling** — single SMF instance, no standby
- **PFCP session recovery** — no session adoption by a replacement SMF
- **AMF-SMF context transfer** — AMF cannot redirect an existing session to a new SMF

This is why recovering from the SMF crash in the chaos episode required restarting UEs.

---

## Part 2: IMS CSCF Cache Consistency

### The Problem

CSCFs (P-CSCF, I-CSCF, S-CSCF) cache registration state in memory — which UEs are registered, their contact URIs, which S-CSCF serves them. When an NF restarts or a UE's registration state changes without proper notification, these caches become stale. In the chaos episode, UEs re-registered after the SMF crash without the old registrations being deregistered, resulting in doubled contact counts (4 instead of 2).

### Mechanism 1: SIP Registration Event Package (RFC 3680 + TS 24.229)

**TS 24.229 clause 5.4.2** defines how CSCFs use the SIP `reg` event package (RFC 3680) to maintain cache consistency:

**Subscription flow:**
1. During initial IMS registration, after the S-CSCF accepts the REGISTER (200 OK), the P-CSCF sends a **SIP SUBSCRIBE** to the S-CSCF for the `reg` event package for that user's IMPU
2. The S-CSCF accepts the subscription and immediately sends a **NOTIFY** with the current registration state (`active`, contact URIs, expiry time)
3. On any registration state change (re-registration, deregistration, expiry, administrative deregistration), the S-CSCF sends a new NOTIFY to all subscribers

**S-CSCF restart recovery:**
- When the S-CSCF restarts, all subscriptions are lost
- The S-CSCF can send a NOTIFY with `Subscription-State: terminated` and `state="terminated"` to all P-CSCFs (if it remembers the subscription targets from external storage)
- P-CSCFs clear their caches for those users
- On the next incoming request for those users, the P-CSCF routes via the I-CSCF, which queries the HSS afresh

**P-CSCF restart recovery:**
- When the P-CSCF restarts, it has no subscriptions and no cached registrations
- When a new request arrives for a UE that the P-CSCF thinks is unregistered, it forwards to the I-CSCF
- The I-CSCF queries the HSS (Diameter LIR — Location-Info-Request) to find the current S-CSCF
- Routing continues normally; the P-CSCF re-learns the UE's state from the 200 OK response and re-establishes the `reg` event subscription

**Spec references:**
- **TS 24.229 clause 5.4.2** — P-CSCF registration event subscription procedures
- **RFC 3680** — SIP Event Package for Registrations
- **RFC 3265** — SIP-Specific Event Notification (base framework)

### Mechanism 2: HSS as Authoritative Source (Diameter Cx)

The HSS is the single source of truth for IMS registration state. The Diameter Cx interface (**TS 29.228/29.229**) provides the mechanisms:

**S-CSCF → HSS: Server-Assignment-Request (SAR)**
- When the S-CSCF assigns itself to serve a user, it sends a SAR to the HSS
- The HSS records the S-CSCF address as the serving CSCF for that IMPU
- Assignment types include: `REGISTRATION`, `RE_REGISTRATION`, `UNREGISTERED_USER`, `USER_DEREGISTRATION`

**I-CSCF → HSS: Location-Info-Request (LIR)**
- When the I-CSCF needs to route a request (REGISTER or INVITE), it queries the HSS with an LIR
- The HSS returns the currently assigned S-CSCF address
- This always returns fresh data — the I-CSCF never relies on cached S-CSCF assignments

**I-CSCF → HSS: User-Authorization-Request (UAR)**
- During registration, the I-CSCF sends a UAR to check if the user exists and whether an S-CSCF is already assigned
- The HSS returns the assigned S-CSCF or indicates that the I-CSCF should select one

**S-CSCF crash recovery via HSS:**
1. Old S-CSCF crashes
2. The HSS still has the old S-CSCF recorded as the serving CSCF
3. When the UE's registration timer fires and it re-REGISTERs, the REGISTER reaches the I-CSCF
4. I-CSCF sends UAR to HSS — HSS returns the old (now dead) S-CSCF address
5. I-CSCF forwards REGISTER to the old S-CSCF address — SIP timeout (no response)
6. I-CSCF can either retry with a different S-CSCF or the HSS can reassign via a new UAR/SAR cycle
7. The new S-CSCF sends SAR to update the HSS, and the registration completes

**Spec references:**
- **TS 29.228** — Cx and Dx interfaces (signaling flows and procedures)
- **TS 29.229** — Cx and Dx interfaces (data types and message formats)

### Mechanism 3: Registration Expiry as Self-Healing

IMS registrations have a finite expiry (typically 3600 seconds, configured per deployment). Even without any explicit recovery mechanism, stale caches self-heal:

1. The UE's registration timer fires and it sends a fresh SIP REGISTER
2. The REGISTER traverses the full path: UE → P-CSCF → I-CSCF → HSS (UAR) → S-CSCF → HSS (MAR/SAR) → 200 OK back
3. All caches along the path are updated with current state
4. Stale entries for the old registration expire naturally when their timer runs out
5. The doubled contacts resolve to the correct count after one registration cycle

The 3600-second expiry means worst-case recovery is ~1 hour. Production deployments can tune this lower (e.g., 600s) at the cost of increased signaling load.

### What This Lab Stack Lacks

- **No `reg` event subscriptions** — the P-CSCF does not SUBSCRIBE to the S-CSCF for registration events (the Kamailio IMS modules support this but it's not configured)
- **No HSS-driven reassignment** — PyHSS stores the S-CSCF assignment but doesn't automatically clear it on S-CSCF failure
- **3600-second registration expiry** — too long to wait for self-healing during testing
- **No administrative deregistration** — no mechanism to force-clear stale registrations from CSCFs without restarting them

---

## Summary: Lab Stack vs Production Resilience

| Problem | Lab Stack Behavior | Production (3GPP) Mechanism | Spec Reference |
|---|---|---|---|
| SMF crash → lost sessions | All state lost, UEs must re-register | UDSF stores state externally; new SMF reads it; UE unaware | TS 23.501 cl. 6.2.10, TS 29.598 |
| SMF redundancy | Single instance, no failover | N+K pool behind NRF; any instance serves any session | TS 23.501 cl. 5.21 |
| PFCP session recovery | UPF sessions orphaned | New SMF adopts sessions via PFCP Session Modification with updated F-SEID | TS 29.244 cl. 7.4.14, 8.2.25 |
| AMF → SMF redirect | Not supported | Nsmf_PDUSession_CreateSMContext with old context ref; new SMF reads from UDSF | TS 23.502 cl. 4.3.4 |
| CSCF stale contacts | Manual CSCF restart | `reg` event NOTIFY clears P-CSCF cache automatically | TS 24.229 cl. 5.4.2, RFC 3680 |
| S-CSCF crash → routing | I-CSCF routes to dead S-CSCF, times out | I-CSCF queries HSS (LIR); HSS reassigns; new S-CSCF takes over | TS 29.228, TS 29.229 |
| Registration self-healing | Wait 3600s or restart UEs | Timer-based re-REGISTER refreshes all caches; tunable expiry | TS 24.229 |

## Design Principle

**No network function should be the sole owner of state that matters.** The 3GPP architecture enforces this through three complementary patterns:

1. **State externalization** (UDSF) — session state is persisted outside the NF so any instance can recover it
2. **Authoritative source** (HSS for IMS, UDR for 5GC) — routing and identity decisions always trace back to a centralized database that survives individual NF failures
3. **Timer-based self-healing** (registration expiry, PFCP heartbeat) — even without active recovery, the system converges to a correct state within one timer cycle

These patterns are why production 5G/IMS networks achieve five-nines availability despite individual NF crashes being routine operational events.
