# ADR: Diagnostic Auto-Heal for Broken Stack State

**Date:** 2026-04-13
**Status:** Accepted

---

## Decision

Rewrote the `auto_heal_stack()` function in `common/stack_health.py` from a blind "redeploy UEs" approach to a diagnostic heal that analyzes which metrics are unhealthy and applies targeted fixes for each failure mode.

---

## Context

The stack health check runs before every chaos scenario and anomaly model training session. It compares six critical metrics against expected values:

| Metric | Expected | Source | Meaning |
|---|---|---|---|
| `ran_ue` | 2.0 | AMF | UEs attached to 5G |
| `gnb` | 1.0 | AMF | gNBs connected |
| `amf_session` | 4.0 | AMF | PDU sessions (2 UEs x 2 PDNs) |
| `fivegs_smffunction_sm_sessionnbr` | 4.0 | SMF | PDU sessions at SMF |
| `ims_usrloc_pcscf:registered_contacts` | 2.0 | P-CSCF | IMS-registered UEs at P-CSCF |
| `ims_usrloc_scscf:active_contacts` | 2.0 | S-CSCF | IMS-registered UEs at S-CSCF |

When the check fails, the user is offered an auto-heal option. The old implementation blindly redeployed UEs (`scripts/deploy-ues.sh`) and waited 60 seconds. This failed to fix the most common post-fault issues:

**Stale CSCF caches:** After a fault scenario, UEs re-register but old registration entries persist in P-CSCF/S-CSCF usrloc databases, doubling the contact count (4 instead of 2). Redeploying UEs adds new registrations on top of stale ones — making the problem worse.

**Diameter peer stuck in I_Open:** After PyHSS or CSCF restarts, the Diameter connection between I-CSCF/S-CSCF and HSS can get stuck in `I_Open` state instead of fully establishing. SIP REGISTERs then timeout (408) because the I-CSCF can't query the HSS. Redeploying UEs doesn't fix this — the Diameter peer needs to be re-established by restarting the CSCFs.

**Broken PDU sessions:** After an SMF crash (as seen in the Data Plane Degradation episodes), PDU session state is lost. The SMF shows zero sessions but the UEs think they're still attached. Redeploying UEs re-establishes sessions, but only if the SMF is actually running and healthy.

**Residual tc rules:** Previous chaos runs may leave tc netem rules on containers if the healer failed or the run was interrupted. These cause ongoing packet loss that makes the stack appear unhealthy even after UE redeployment.

---

## Design

The new `auto_heal_stack()` diagnoses what's broken and applies targeted fixes in sequence:

### Step 1: Clear residual tc rules

Before anything else, clear tc netem rules from all network-function containers. This eliminates lingering packet loss from previous chaos runs that could interfere with the heal process itself.

```python
for c in ["upf", "rtpengine", "pcscf", "icscf", "scscf", "pyhss",
           "amf", "smf", "nr_gnb"]:
    docker exec {c} tc qdisc del dev eth0 root
```

This is the same cleanup that `BaselineCollector` performs at the start of every scenario.

### Step 2: Diagnose failure category

The health check failures are classified into categories based on which metrics are wrong:

| Failed Metrics | Category | Root Cause |
|---|---|---|
| `registered_contacts`, `active_contacts` | IMS stale cache | CSCFs have stale/doubled usrloc entries |
| `amf_session`, `sm_sessionnbr` | Broken PDU sessions | SMF state lost (crash) or UEs not attached |
| `ran_ue` | Missing UEs | UE containers not running or not 5G-attached |

Multiple categories can be active simultaneously (e.g., stale IMS cache + broken PDU sessions after an SMF crash).

### Step 3: Fix IMS stale cache

If IMS contact metrics are wrong, restart P-CSCF, I-CSCF, and S-CSCF. This clears usrloc databases and forces a clean state. After restarting:

- Check the I-CSCF Diameter peer state via `kamcmd cdp.list_peers`
- If the peer is `I_Open` or `Closed` (not fully established), restart PyHSS to reset its Diameter listener, then restart the CSCFs again to reconnect

This sequence addresses the startup ordering dependency: CSCFs need PyHSS's Diameter service to be ready before they can establish the peer connection.

### Step 4: Restart UEs

If PDU sessions are broken, UEs are missing, or IMS cache was stale (which requires fresh registrations), restart both UE containers and wait 30 seconds for 5G attachment and PDU session establishment.

### Step 5: Force SIP re-registration

After UEs are attached, send `rr` (re-register) commands to both UEs via pjsua FIFO. This forces fresh SIP REGISTER transactions that traverse the full I-CSCF → HSS → S-CSCF path, populating the usrloc databases with current contacts.

### Step 6: Retry if needed

Check IMS registration metrics after the first attempt. If still not at expected values (race condition — registration may take a few seconds), retry the re-register command once with a longer wait.

---

## Failure mode coverage

| Scenario | Old Auto-Heal | New Auto-Heal |
|---|---|---|
| Stale CSCF contacts (4 instead of 2) | Redeploy UEs → makes it worse (6 contacts) | Restart CSCFs → clear usrloc → restart UEs → re-register |
| Diameter I_Open after restart | Not addressed → REGISTER timeout | Detect via kamcmd → restart PyHSS → restart CSCFs |
| SMF crash → zero sessions | Redeploy UEs → may fix if SMF is back | Clear tc → restart UEs → re-establish PDU sessions |
| Residual tc rules from previous run | Not addressed | Clear tc on all containers first |
| UE containers stopped | Redeploy UEs → works | Restart UEs → works |

---

## Implementation Notes

**Timeout handling:** Each `_shell()` call catches its own `asyncio.TimeoutError` and returns `(1, "timeout")` instead of propagating. This prevents a single slow docker restart from aborting the entire heal sequence. The default timeout is 60 seconds per command.

**Sequential CSCF restarts:** CSCFs are restarted one at a time (`docker restart pcscf`, then `docker restart icscf`, then `docker restart scscf`) rather than in a single `docker restart pcscf icscf scscf` call. Docker restart sends SIGTERM, waits for the container's stop timeout (default 10s), then SIGKILL — three containers sequentially in one command can exceed 30 seconds. Restarting individually keeps each call within timeout.

---

## Files Changed

- `common/stack_health.py` — rewrote `auto_heal_stack()` with diagnostic classification and targeted fixes; added `_shell()` helper with per-command timeout handling

---

## Related

- The `BaselineCollector` tc cleanup (from the scale-independent anomaly features ADR) performs the same tc rule clearing at the start of every scenario. The auto-heal does it additionally during the interactive health check, before the scenario even starts.
- The Diameter `I_Open` state issue is a known startup ordering problem in this stack, documented in the telco-grade resilience patterns ADR. Production networks solve this with the UDSF and Diameter peer recovery mechanisms; this lab stack requires manual restart sequencing.
