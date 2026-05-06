# AMBR end-to-end — 4G and 5G

A practical guide for both audiences:

- **Product managers** translating customer rate-cap requirements into a feature ask.
- **System architects** wiring the actual NF interactions and enforcement points.

AMBR (Aggregate Maximum Bit Rate) is how the network caps **non-GBR** traffic — best-effort data — at two scopes: per *session/APN* and per *subscriber*. GBR traffic (e.g. VoLTE/VoNR voice on QCI/5QI 1) is governed separately by per-flow MBR/GBR, not AMBR.

This document covers, for each generation:

1. The NFs involved and their role.
2. A simplified mental model.
3. How AMBR is **provisioned** (operator-side, before any UE shows up).
4. How it is **dynamically updated** by the policy NF (PCRF in 4G, PCF in 5G).
5. How it is **distributed** to all enforcement points during attach / registration.
6. How it is **enforced** at runtime.

---

## 1. AMBR scopes — naming cheat sheet

| Scope | 4G name | 5G name | Applies to |
|---|---|---|---|
| Per data network | **APN-AMBR** | **Session-AMBR** | All non-GBR bearers/flows of one APN/DNN |
| Per subscriber | **UE-AMBR** | **UE-AMBR** | All non-GBR bearers/flows of the UE on the radio |
| Per flow (not AMBR) | MBR / GBR | MBR / GBR | A single GBR bearer / QoS flow |

The semantics carry over cleanly between generations — the *plumbing* changes.

---

## 2. NFs involved per generation

### 4G (EPS) — APN-AMBR + UE-AMBR

| NF | Role in AMBR | Repo dir |
|---|---|---|
| **HSS (PyHSS)** | Subscription store. Holds **UE-AMBR** (per-subscriber) and **APN-AMBR** (per APN). Sends both to MME on attach via S6a `Update-Location-Answer`. | `network/pyhss`, `network/hss` |
| **PCRF** | Optional dynamic policy. Can override APN-AMBR over Gx (CCA-I / RAR) to PGW-C. Authoritative when present. | `network/pcrf` (and PyHSS PCRF) |
| **MME** | Computes the *used* UE-AMBR (min of subscribed UE-AMBR and the sum of APN-AMBRs across active non-GBR PDN connections). Pushes APN-AMBR to SGW/PGW via S11/S5 GTP-C `Create Session Request`, and pushes UE-AMBR to the eNB via S1AP `Initial Context Setup`. | `network/mme` |
| **SGW-C / SGW-U** | Pass-through. Carries the APN-AMBR IE on S11/S5 but does **not** enforce. | `network/sgwc`, `network/sgwu` |
| **PGW-C** (combined into Open5GS SMF) | Receives APN-AMBR from MME (and possibly PCRF). Programs PGW-U to enforce DL APN-AMBR; signals UL APN-AMBR back to UE via NAS. | `network/smf` (acts as SMF+PGW-C) |
| **PGW-U** (combined into Open5GS UPF) | **Enforcement point for APN-AMBR DL** on the SGi side, across the aggregate of non-GBR EPS bearers of that APN. | `network/upf` (acts as UPF+PGW-U) |
| **eNB** | **Enforcement point for UE-AMBR** (UL & DL on the radio, across all of the UE's non-GBR DRBs). | `network/srsenb`, `network/oai` |
| **UE** | **Enforcement point for APN-AMBR UL** per PDN connection, using the value the MME sent over NAS. | `network/srslte` (srsUE) |

### 5G (5GC) — Session-AMBR + UE-AMBR

| NF | Role in AMBR | Repo dir |
|---|---|---|
| **UDR** | Persistent subscription store. Holds **Subscribed-UE-AMBR** in AM data and **Session-AMBR** per (DNN, S-NSSAI) in SM data. | `network/udr` |
| **UDM** | Exposes UDR data via Nudm_SDM. AM Subscription Data → AMF (Subscribed-UE-AMBR); SM Subscription Data → SMF (Session-AMBR). | `network/udm` |
| **PCF** | Optional dynamic authorization. Can authorize/override **Session-AMBR** to SMF over Npcf_SMPolicyControl, and UE policy to AMF. | `network/pcf` |
| **AMF** | Pulls Subscribed-UE-AMBR from UDM at registration, computes the *used* UE-AMBR, and signals it to NG-RAN over N2 (`Initial Context Setup` / `PDU Session Resource Setup`). | `network/amf` |
| **SMF** | Gets Session-AMBR (UDM default, PCF override). Pushes it to **UPF over N4/PFCP as a QER**, to the **UE over NAS**, and to the **gNB over N2** as part of the QoS Flow profile. | `network/smf` |
| **UPF** | **Enforcement point for Session-AMBR DL** on N6 — implemented as a session-level QER summing non-GBR QoS flows of that PDU session. | `network/upf`, `network/eupf` |
| **gNB (NG-RAN)** | **Enforcement point for UE-AMBR** (UL & DL on the radio, across all non-GBR QoS flows of the UE). | `network/srsgnb`, `network/oaignb`, UERANSIM |
| **UE** | **Enforcement point for Session-AMBR UL** per PDU session (NAS-signaled value), and respects the UE-AMBR cap that the gNB schedules to. | `network/ueransim` |

**Not on the AMBR path** (stated explicitly so you don't go looking for hooks there): NRF, NSSF, AUSF, SCP, BSF in 5G; the IMS plane in either generation. IMS uses dedicated bearers / GBR flows on QCI/5QI 1 with per-flow MBR/GBR.

---

## 3. Simplified mental model

**4G:** *HSS provides the budget → MME apportions and signals → PGW-U polices DL APN-AMBR, eNB polices UE-AMBR on the air, UE polices UL APN-AMBR.*

**5G:** *UDR/UDM provide the budget → PCF can rewrite it → AMF and SMF distribute it → UPF polices DL Session-AMBR (per PDU session), gNB polices UE-AMBR on the air, UE polices UL Session-AMBR.*

The shape is identical: **storage → (optional policy override) → control-plane distribution → three enforcement points (UE, RAN, UPF/PGW-U).**

---

## 4. 4G — sequence flows

### 4.1 Provisioning (operator-side, no UE involved yet)

The operator writes the per-APN and per-subscriber caps into the HSS database. No live network signaling — this is purely populating the source of truth that will be consulted on the next attach.

```mermaid
sequenceDiagram
    actor Op as Operator / OSS
    participant HSS as HSS (PyHSS)
    participant DB as HSS Subscriber DB

    Op->>HSS: REST/CLI: define APN<br/>(e.g. apn_ambr_dl, apn_ambr_ul)
    HSS->>DB: persist APN profile
    Op->>HSS: REST/CLI: create subscriber<br/>(IMSI, K/OPc, ue_ambr_dl, ue_ambr_ul, apn_list)
    HSS->>DB: persist subscriber profile
    Note over HSS,DB: Source of truth now contains:<br/>• per-APN APN-AMBR<br/>• per-subscriber UE-AMBR
```

In this repo, this is exactly what `scripts/provision.sh` does via PyHSS REST: `POST /apn/` with `apn_ambr_dl/ul`, then subscriber creation with `ue_ambr_dl/ul`.

### 4.2 Optional dynamic update via PCRF

The PCRF can override APN-AMBR at session start (CCA-I) or **mid-session** (RAR) — useful for time-of-day shaping, fair-use throttling, or operator-driven boost.

```mermaid
sequenceDiagram
    participant PCRF
    participant PGW as PGW-C
    participant PGWU as PGW-U
    participant SGW as SGW
    participant MME
    participant UE

    Note over PCRF,UE: Mid-session APN-AMBR change driven by PCRF
    PCRF->>PGW: Gx RAR (QoS-Information:<br/>new APN-AMBR-UL/DL)
    PGW-->>PCRF: Gx RAA
    PGW->>PGWU: update DL rate limiter<br/>(new APN-AMBR-DL)
    PGW->>SGW: GTP-C Update Bearer Request<br/>(new APN-AMBR)
    SGW->>MME: Update Bearer Request
    MME->>UE: NAS Modify EPS Bearer Context Request<br/>(new APN-AMBR for UL)
    UE-->>MME: Modify EPS Bearer Context Accept
    MME-->>SGW: Update Bearer Response
    SGW-->>PGW: Update Bearer Response
    Note over UE,PGWU: All three enforcement points<br/>now using the new APN-AMBR
```

If the PCRF override is sent at *initial* attach instead, it rides on Gx CCA-I within the flow shown in §4.3, and the UE simply gets the post-override value in its NAS Attach Accept.

### 4.3 Distribution at UE attach

```mermaid
sequenceDiagram
    participant UE
    participant eNB
    participant MME
    participant HSS as HSS (PyHSS)
    participant SGW as SGW
    participant PGW as PGW (SMF in Open5GS)
    participant PGWU as PGW-U (UPF)
    participant PCRF

    UE->>eNB: RRC Connection Setup
    UE->>MME: NAS Attach Request
    MME->>HSS: S6a Update-Location-Request
    HSS-->>MME: ULA + Subscription Data<br/>(UE-AMBR, APN-AMBR per APN)
    Note over MME: Compute used UE-AMBR =<br/>min(subscribed UE-AMBR,<br/>Σ APN-AMBR of active non-GBR PDNs)
    MME->>SGW: S11 Create Session Request (APN-AMBR)
    SGW->>PGW: S5 Create Session Request (APN-AMBR)
    PGW->>PCRF: Gx CCR-Initial
    PCRF-->>PGW: Gx CCA-Initial<br/>(may override APN-AMBR)
    PGW->>PGWU: install DL rate limiter<br/>(final APN-AMBR-DL)
    PGW-->>SGW: Create Session Response (final APN-AMBR)
    SGW-->>MME: Create Session Response
    MME->>eNB: S1AP Initial Context Setup<br/>(UE-AMBR for radio policing,<br/>NAS Attach Accept inside)
    eNB->>UE: RRC Reconfig + NAS Attach Accept<br/>(APN-AMBR for UL policing)
    UE-->>eNB: RRC Reconfig Complete
    eNB-->>MME: S1AP Initial Context Setup Response
    Note over UE,PGWU: Three enforcement points now armed:<br/>UE (UL APN-AMBR), eNB (UE-AMBR UL+DL),<br/>PGW-U (DL APN-AMBR)
```

### 4.4 Enforcement at runtime

```mermaid
sequenceDiagram
    participant UE
    participant eNB
    participant SGW
    participant PGWU as PGW-U
    participant PDN as PDN (Internet)

    Note over UE,PDN: Uplink path
    UE->>UE: Token-bucket police<br/>per PDN connection ≤ APN-AMBR-UL
    UE->>eNB: PDCP packets within UL APN-AMBR
    eNB->>eNB: Schedule UE's non-GBR DRBs<br/>aggregate ≤ UE-AMBR (UL)
    eNB->>SGW: GTP-U
    SGW->>PGWU: GTP-U
    PGWU->>PDN: SGi (no AMBR cap on UL —<br/>UE already shaped it)

    Note over UE,PDN: Downlink path
    PDN->>PGWU: SGi (uncapped from internet)
    PGWU->>PGWU: Token-bucket police<br/>aggregate of non-GBR bearers<br/>of this APN ≤ APN-AMBR-DL
    PGWU->>SGW: GTP-U (within APN-AMBR-DL)
    SGW->>eNB: GTP-U
    eNB->>eNB: Schedule UE's non-GBR DRBs<br/>aggregate ≤ UE-AMBR (DL)
    eNB->>UE: PDCP packets

    Note right of PGWU: Excess DL bytes are dropped<br/>(or marked, depending on policy)
    Note right of UE: Excess UL bytes are dropped at UE<br/>before they hit the air interface
```

---

## 5. 5G — sequence flows

### 5.1 Provisioning (operator-side, no UE involved yet)

```mermaid
sequenceDiagram
    actor Op as Operator / OSS
    participant UDM
    participant UDR
    participant DB as UDR Backend (e.g. MongoDB)

    Op->>UDM: Nudm_PP / WebUI:<br/>create subscriber
    UDM->>UDR: Nudr write — AM data<br/>(Subscribed-UE-AMBR)
    UDR->>DB: persist
    Op->>UDM: Define DNN/S-NSSAI session profile<br/>(Session-AMBR UL/DL)
    UDM->>UDR: Nudr write — SM data<br/>(per-DNN/S-NSSAI Session-AMBR)
    UDR->>DB: persist
    Note over UDM,DB: Source of truth now contains:<br/>• Subscribed-UE-AMBR<br/>• per-(DNN, S-NSSAI) Session-AMBR
```

In Open5GS specifically, the WebUI / direct MongoDB write into `subscriber.slice[].session[].ambr.{downlink,uplink}.{value,unit}` is the Session-AMBR; the Subscribed-UE-AMBR sits at the slice/subscription level. This repo's `scripts/provision.sh` writes these via Mongo seed.

### 5.2 Optional dynamic update via PCF

```mermaid
sequenceDiagram
    participant PCF
    participant SMF
    participant UPF
    participant AMF
    participant gNB
    participant UE

    Note over PCF,UE: Mid-session Session-AMBR change driven by PCF
    PCF->>SMF: Npcf_SMPolicyControl_UpdateNotify<br/>(new Session-AMBR)
    SMF-->>PCF: 200 OK
    SMF->>UPF: N4 Session Modification<br/>(QER update — new Session-AMBR-DL)
    UPF-->>SMF: PFCP Response
    SMF->>AMF: Namf_Communication_N1N2MessageTransfer<br/>(N1 SM: Session-AMBR for UE,<br/>N2 SM: Session-AMBR for gNB)
    AMF->>gNB: N2 PDU Session Resource Modify Request<br/>(new Session-AMBR)
    gNB->>UE: RRC Reconfig + NAS PDU Session<br/>Modification Command (new Session-AMBR)
    UE-->>gNB: RRC Reconfig Complete
    gNB-->>AMF: N2 PDU Session Resource Modify Response
    Note over UE,UPF: All three enforcement points<br/>now using the new Session-AMBR
```

PCF can equally rewrite Session-AMBR at PDU Session creation time — that path is shown inline in §5.3.

### 5.3 Distribution — Registration + PDU Session Establishment

5G splits AMBR distribution into two phases because UE-AMBR is set at registration, but Session-AMBR is set per PDU session.

#### Phase 1 — Registration (carries Subscribed-UE-AMBR to AMF)

```mermaid
sequenceDiagram
    participant UE
    participant gNB
    participant AMF
    participant AUSF
    participant UDM
    participant UDR

    UE->>gNB: RRC Setup
    UE->>AMF: NAS Registration Request
    AMF->>AUSF: Nausf_UEAuthentication
    AUSF-->>AMF: Auth Result
    AMF->>UDM: Nudm_SDM_Get<br/>(Access & Mobility Subscription)
    UDM->>UDR: Nudr Query (AM data)
    UDR-->>UDM: AM Subscription Data<br/>(Subscribed-UE-AMBR)
    UDM-->>AMF: Subscription Data
    Note over AMF: Store Subscribed-UE-AMBR<br/>in UE context — used as<br/>cap for "used UE-AMBR"
    AMF-->>UE: NAS Registration Accept
```

At this point AMF *knows* the cap but hasn't told the gNB yet — there are no PDU sessions to schedule.

#### Phase 2 — PDU Session Establishment (carries Session-AMBR everywhere; pushes UE-AMBR to gNB)

```mermaid
sequenceDiagram
    participant UE
    participant gNB
    participant AMF
    participant SMF
    participant UDM
    participant UDR
    participant PCF
    participant UPF

    UE->>AMF: NAS PDU Session Establishment Request
    AMF->>SMF: Nsmf_PDUSession_CreateSMContext
    SMF->>UDM: Nudm_SDM_Get (Session Mgmt)
    UDM->>UDR: Nudr Query (SM data)
    UDR-->>UDM: SM Subscription Data<br/>(Session-AMBR per DNN/S-NSSAI)
    UDM-->>SMF: SM Subscription Data
    SMF->>PCF: Npcf_SMPolicyControl_Create
    PCF-->>SMF: SM Policy Decision<br/>(may override Session-AMBR)
    SMF->>UPF: N4 Session Establishment<br/>(QER with Session-AMBR<br/>for non-GBR aggregate, DL)
    UPF-->>SMF: PFCP Response
    SMF-->>AMF: CreateSMContext Response<br/>(N1 SM container — Session-AMBR for UE;<br/>N2 SM info — Session-AMBR for gNB)
    Note over AMF: Recompute used UE-AMBR =<br/>min(Subscribed-UE-AMBR,<br/>Σ Session-AMBR of active non-GBR sessions)
    AMF->>gNB: N2 PDU Session Resource Setup Request<br/>(Session-AMBR + UE-AMBR)
    gNB->>UE: RRC Reconfig + NAS PDU Session<br/>Establishment Accept (Session-AMBR for UL)
    UE-->>gNB: RRC Reconfig Complete
    gNB-->>AMF: N2 PDU Session Resource Setup Response
    Note over UE,UPF: Three enforcement points armed:<br/>UE (UL Session-AMBR), gNB (UE-AMBR UL+DL),<br/>UPF (DL Session-AMBR via QER)
```

### 5.4 Enforcement at runtime

```mermaid
sequenceDiagram
    participant UE
    participant gNB
    participant UPF
    participant DN as Data Network

    Note over UE,DN: Uplink path
    UE->>UE: Token-bucket police<br/>per PDU session ≤ Session-AMBR-UL
    UE->>gNB: PDCP packets within UL Session-AMBR
    gNB->>gNB: Schedule UE's non-GBR QoS flows<br/>aggregate ≤ UE-AMBR (UL)
    gNB->>UPF: GTP-U over N3
    UPF->>DN: N6 (no AMBR cap on UL —<br/>UE already shaped it)

    Note over UE,DN: Downlink path
    DN->>UPF: N6 (uncapped from internet)
    UPF->>UPF: Apply session QER<br/>aggregate of non-GBR flows<br/>≤ Session-AMBR-DL
    UPF->>gNB: GTP-U over N3 (within Session-AMBR-DL)
    gNB->>gNB: Schedule UE's non-GBR flows<br/>aggregate ≤ UE-AMBR (DL)
    gNB->>UE: PDCP packets

    Note right of UPF: Excess DL bytes dropped/marked<br/>by the QER on the PDU session
    Note right of UE: Excess UL bytes dropped at UE<br/>before they hit the air interface
```

---

## 6. How AMBR appears in *this repo* today

For a quick orientation when implementing or testing AMBR features here:

- **5G subscriber data (Open5GS Mongo)** — set by `scripts/provision.sh`, in the canonical Open5GS schema shape: `slice[].session[].ambr.{downlink,uplink}.{value,unit}` for Session-AMBR; `unit: 3` = Mbps, `unit: 1` = Kbps. Default in this repo: 1 Mbps DL / 1 Mbps UL on `internet` and `ims` DNNs.
- **4G subscriber data (PyHSS REST)** — `POST /apn/` with `apn_ambr_dl` / `apn_ambr_ul`; subscriber record carries `ue_ambr_dl` / `ue_ambr_ul`. Default in this repo: `0` on all four (= unlimited per PyHSS convention).
- **Per-flow MBR/GBR (dedicated bearer for IMS)** — provisioned at the same time, as `pcc_rule[].qos.{mbr,gbr}` on the `ims` session: 128 Kbps each direction for QCI/5QI 1.
- **No GUI surface for AMBR editing today.** The `gui/` shows flows and topology but does not expose AMBR knobs; changes are made by re-running provisioning or hitting PyHSS / Mongo directly.
- **PCF/PCRF dynamic override is *capability present, paths quiet*.** PyHSS and Open5GS PCF are deployed; the current chaos scenarios do not exercise mid-session AMBR rewrites. A new chaos scenario along this axis would be a clean way to validate §4.2 / §5.2 end-to-end.

---

## 7. Decision-making cheat sheet

For a PM gathering customer requirements, the right question to ask is: *"At which scope do you want the cap?"*

| Customer ask | Scope | Knob |
|---|---|---|
| "Cap each enterprise sub-connection (e.g. their IoT slice) at 100 Mbps." | Per DNN/APN | Session-AMBR (5G) / APN-AMBR (4G) |
| "Cap a subscriber's total best-effort across *all* their connections at 50 Mbps." | Per UE | UE-AMBR (both gens) |
| "Cap a single video/voice flow at exactly 4 Mbps, guaranteed." | Per flow | MBR + GBR on a dedicated bearer / QoS flow — **not AMBR** |
| "Drop their cap dynamically when a fair-use threshold is hit." | Per session, mid-session | PCF/PCRF override path (§4.2 / §5.2) |
| "Reset their cap at billing-cycle rollover." | Per session, scheduled | PCF/PCRF push driven by OSS/charging |

For a system architect, the matching design questions are: *Which NF holds truth? Who can override it? Who actually enforces it?* — the three columns of every table in §2.
