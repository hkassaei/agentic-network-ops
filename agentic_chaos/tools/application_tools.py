"""
Application-level fault injection tools — config corruption, DB faults.

These tools modify application state (configs, database records) rather than
infrastructure (containers, network). They are more surgical but harder to
reverse cleanly.

Every mutating function returns a dict with:
  - success: bool
  - mechanism: str (exact command or action taken)
  - heal_cmd: str (command to reverse, if possible)
  - detail: str (output or description)
"""

from __future__ import annotations

import logging
import shlex

from ._common import shell, validate_container

log = logging.getLogger("chaos-tools.application")


# -------------------------------------------------------------------------
# MongoDB (5G core subscriber store)
# -------------------------------------------------------------------------

async def delete_subscriber_mongo(imsi: str) -> dict:
    """Delete a subscriber from the Open5GS MongoDB database.

    Args:
        imsi: IMSI string (e.g. '001011234567891').

    Returns:
        {success, mechanism, heal_cmd, detail}
    """
    if not imsi.isdigit() or len(imsi) < 10:
        raise ValueError(f"Invalid IMSI: '{imsi}' (must be 10-15 digits)")

    safe_imsi = shlex.quote(imsi)
    mechanism = (
        f"docker exec mongo mongosh --quiet --eval "
        f"\"db.subscribers.deleteOne({{imsi: {safe_imsi}}})\" open5gs"
    )
    rc, output = await shell(mechanism)

    # There's no simple heal for deletion — would need the full subscriber doc
    return {
        "success": rc == 0 and "deletedCount" in output,
        "mechanism": mechanism,
        "heal_cmd": "# Manual: re-provision subscriber via provision.sh",
        "detail": output,
    }


async def count_subscribers_mongo() -> dict:
    """Count subscribers in the Open5GS MongoDB database.

    Returns:
        {success, count, detail}
    """
    mechanism = (
        "docker exec mongo mongosh --quiet --eval "
        "\"db.subscribers.countDocuments()\" open5gs"
    )
    rc, output = await shell(mechanism)

    count = None
    if rc == 0 and output.strip().isdigit():
        count = int(output.strip())

    return {
        "success": count is not None,
        "count": count,
        "detail": output,
    }


async def drop_collection_mongo(collection: str = "subscribers") -> dict:
    """Drop a MongoDB collection. DESTRUCTIVE — use with extreme caution.

    Args:
        collection: Collection name (default 'subscribers').

    Returns:
        {success, mechanism, heal_cmd, detail}
    """
    safe_col = shlex.quote(collection)
    mechanism = (
        f"docker exec mongo mongosh --quiet --eval "
        f"\"db.{safe_col}.drop()\" open5gs"
    )
    rc, output = await shell(mechanism)

    return {
        "success": rc == 0,
        "mechanism": mechanism,
        "heal_cmd": "# Manual: re-provision all subscribers via provision.sh",
        "detail": output,
    }


# -------------------------------------------------------------------------
# PyHSS (IMS subscriber store)
# -------------------------------------------------------------------------

async def corrupt_subscriber_credential(
    imsi: str,
    ue_container: str | None = None,
) -> dict:
    """Corrupt one subscriber's K (authentication key) in PyHSS's MySQL.

    Targets exactly one row in the `auc` table — UE1 fails authentication
    while every other UE keeps working. Per CDR-0001 §2 and Task 1.1.

    Mechanism (per CDR-0001 Task 1.1):
      1. SELECT the current `ki` for the IMSI (snapshotted for heal).
      2. Flip the high bit of the first hex byte (XOR 0x80) — guaranteed
         different, still a valid 32-char hex string. Won't collide with
         the UE's actual SIM key.
      3. UPDATE auc SET ki = <corrupted> WHERE auc_id = <id>.
      4. **If a UE container is given, chain `docker restart <ue>` into
         the inject mechanism itself.** Without this, UE1 stays attached
         using its cached NAS security context — the corrupted K only
         bites on the next periodic NAS auth, which is HOURS away (much
         longer than the 120 s observation window). With the restart,
         UE1 boots fresh, tries to attach with its USIM K against the
         now-corrupted HSS K, AKA fails, AMF logs `5GMM cause #20 MAC
         failure`. Symptoms surface within ~15-25 s of inject.
      5. Heal command restores the original ki and restarts the UE again
         so AMF re-attaches cleanly against the restored K (otherwise
         AMF's cached security context — now pointing at the corrupted
         K — keeps the UE in the failed state).

    Args:
        imsi: Target subscriber IMSI (e.g. '001011234567891').
        ue_container: Optional UE container to restart at inject AND heal
            (e.g. 'e2e_ue1'). When omitted, the inject only mutates the
            DB — the fault will be observably silent until next periodic
            re-auth.

    Returns:
        {success, mechanism, heal_cmd, detail, original_ki, corrupted_ki, auc_id}
    """
    if not imsi.isdigit() or not (10 <= len(imsi) <= 15):
        raise ValueError(f"Invalid IMSI: '{imsi}' (must be 10-15 digits)")

    # Validate ue_container up-front (used in both mechanism and heal).
    # An invalid name caught late would leave the DB corrupted with no
    # registered heal — fail fast before any SQL is issued.
    if ue_container is not None and ue_container not in ("e2e_ue1", "e2e_ue2"):
        raise ValueError(f"Unsupported ue_container: {ue_container}")

    safe_imsi = shlex.quote(imsi)
    db_args = "-u pyhss -pims_db_pass ims_hss_db"

    # Step 1: look up auc_id and current ki via a JOIN over auc + subscriber.
    # `-N -B` strips column headers and uses tab separation for easy parsing.
    select_sql = (
        f"SELECT a.auc_id, a.ki FROM auc a "
        f"JOIN subscriber s ON s.auc_id = a.auc_id "
        f"WHERE s.imsi = {safe_imsi};"
    )
    lookup_cmd = (
        f"docker exec mysql mysql {db_args} -N -B -e {shlex.quote(select_sql)}"
    )
    rc, out = await shell(lookup_cmd)
    if rc != 0:
        return {
            "success": False,
            "mechanism": lookup_cmd,
            "heal_cmd": "true",  # no-op heal
            "detail": f"Lookup failed (rc={rc}): {out[:200]}",
        }

    rows = [line.strip() for line in out.splitlines() if line.strip()]
    if not rows:
        return {
            "success": False,
            "mechanism": lookup_cmd,
            "heal_cmd": "true",
            "detail": f"No auc row for IMSI {imsi}",
        }
    parts = rows[0].split()
    if len(parts) < 2:
        return {
            "success": False,
            "mechanism": lookup_cmd,
            "heal_cmd": "true",
            "detail": f"Unexpected lookup output: {rows[0]!r}",
        }
    auc_id, original_ki = parts[0], parts[1]

    # Step 2: compute corrupted K — flip high bit of the first byte
    if len(original_ki) != 32 or not all(c in "0123456789abcdefABCDEF" for c in original_ki):
        return {
            "success": False,
            "mechanism": lookup_cmd,
            "heal_cmd": "true",
            "detail": f"Original ki is not 32-char hex: {original_ki!r}",
        }
    first_byte = int(original_ki[:2], 16)
    corrupted_first = f"{first_byte ^ 0x80:02X}"
    corrupted_ki = corrupted_first + original_ki[2:]

    # Step 3: apply UPDATE — and, if a UE container is given, also restart
    # it to force re-attach with the corrupted K (CDR-0001 Task 1.1).
    update_sql = f"UPDATE auc SET ki = '{corrupted_ki}' WHERE auc_id = {auc_id};"
    mechanism = (
        f"docker exec mysql mysql {db_args} -e {shlex.quote(update_sql)}"
    )
    if ue_container:
        mechanism = f"{mechanism} && docker restart {ue_container}"

    # Step 4: build heal — restore K, and bounce the UE for a clean re-attach
    # against the restored K (symmetric with the inject's restart).
    heal_sql = f"UPDATE auc SET ki = '{original_ki}' WHERE auc_id = {auc_id};"
    heal_cmd = (
        f"docker exec mysql mysql {db_args} -e {shlex.quote(heal_sql)}"
    )
    if ue_container:
        heal_cmd = f"{heal_cmd} && docker restart {ue_container}"

    rc, output = await shell(mechanism)
    return {
        "success": rc == 0,
        "mechanism": mechanism,
        "heal_cmd": heal_cmd,
        "detail": (
            f"Corrupted K for IMSI {imsi} (auc_id={auc_id}). "
            f"Original snapshotted in heal_cmd."
        ),
        # Surfaced for the verifier:
        "original_ki": original_ki,
        "corrupted_ki": corrupted_ki,
        "auc_id": auc_id,
    }


async def delete_subscriber_pyhss(
    subscriber_id: int, pyhss_ip: str = "172.22.0.18"
) -> dict:
    """Delete an IMS subscriber from PyHSS via REST API.

    Args:
        subscriber_id: PyHSS subscriber ID (integer).
        pyhss_ip: PyHSS IP address.

    Returns:
        {success, mechanism, heal_cmd, detail}
    """
    subscriber_id = int(subscriber_id)
    url = f"http://{pyhss_ip}:8080/ims_subscriber/{subscriber_id}"
    mechanism = f"curl -s -X DELETE {shlex.quote(url)}"
    rc, output = await shell(mechanism)

    return {
        "success": rc == 0 and "error" not in output.lower(),
        "mechanism": mechanism,
        "heal_cmd": "# Manual: re-provision IMS subscriber via provision.sh",
        "detail": output,
    }


async def count_subscribers_pyhss(pyhss_ip: str = "172.22.0.18") -> dict:
    """Count IMS subscribers in PyHSS via REST API.

    Returns:
        {success, count, detail}
    """
    url = f"http://{pyhss_ip}:8080/ims_subscriber/list"
    mechanism = f"curl -s {shlex.quote(url)}"
    rc, output = await shell(mechanism, timeout=5)

    count = None
    if rc == 0:
        try:
            import json
            data = json.loads(output)
            if isinstance(data, list):
                count = len(data)
        except (json.JSONDecodeError, ValueError):
            pass

    return {
        "success": count is not None,
        "count": count,
        "detail": f"{count} IMS subscribers" if count is not None else output[:200],
    }


# -------------------------------------------------------------------------
# Config corruption
# -------------------------------------------------------------------------

async def corrupt_config(
    container: str, config_path: str, search: str, replace: str
) -> dict:
    """Corrupt a config value inside a running container using Python str.replace().

    Uses `docker exec python3 -c ...` instead of sed to avoid regex escaping
    pitfalls. Does NOT restart the container — caller must restart for the
    change to take effect.

    Args:
        container: Container name.
        config_path: Path to the config file inside the container.
        search: Exact string to find (literal, not regex).
        replace: String to replace with.

    Returns:
        {success, mechanism, heal_cmd, detail}
    """
    validate_container(container)
    safe_container = shlex.quote(container)
    safe_path = shlex.quote(config_path)
    safe_search = shlex.quote(search)
    safe_replace = shlex.quote(replace)

    # Use Python inside the container for safe string replacement (no regex edge cases)
    py_script = (
        f"p={safe_path}; "
        f"t=open(p).read(); "
        f"n=t.replace({safe_search},{safe_replace}); "
        f"open(p,'w').write(n); "
        f"print(f'replaced {{t.count({safe_search})}} occurrences')"
    )
    mechanism = f"docker exec {safe_container} python3 -c {shlex.quote(py_script)}"

    # Heal command: reverse the replacement
    py_heal = (
        f"p={safe_path}; "
        f"t=open(p).read(); "
        f"n=t.replace({safe_replace},{safe_search}); "
        f"open(p,'w').write(n); "
        f"print(f'restored {{t.count({safe_replace})}} occurrences')"
    )
    heal_cmd = f"docker exec {safe_container} python3 -c {shlex.quote(py_heal)}"

    rc, output = await shell(mechanism)
    return {
        "success": rc == 0,
        "mechanism": mechanism,
        "heal_cmd": heal_cmd,
        "detail": output or "Config modified",
    }


# -------------------------------------------------------------------------
# VoNR call setup/teardown (for data plane scenarios)
# -------------------------------------------------------------------------

_CALL_SETUP_TIMEOUT = 30  # seconds to wait for call to connect
_PJSUA_FIFO = "/tmp/pjsua_cmd"


async def establish_vonr_call(ims_domain: str, callee_imsi: str) -> dict:
    """Initiate a VoNR call from UE1 to UE2 via pjsua FIFO.

    Sends the make-call command to UE1's pjsua instance, dials UE2's SIP URI,
    and waits for the call to reach CONFIRMED state.

    Args:
        ims_domain: IMS domain (e.g. 'ims.mnc001.mcc001.3gppnetwork.org').
        callee_imsi: Callee's IMSI (e.g. '001011234567892').

    Returns:
        {success, call_uri, detail}
    """
    import asyncio

    call_uri = f"sip:{callee_imsi}@{ims_domain}"

    # Step 1: Send 'm' to enter the make-call menu
    rc, out = await shell(
        f'docker exec e2e_ue1 bash -c "echo m >> {_PJSUA_FIFO}"'
    )
    if rc != 0:
        return {"success": False, "call_uri": call_uri, "detail": f"Failed to send make-call command: {out}"}

    # Wait for pjsua to show the dial prompt
    await asyncio.sleep(3)

    # Step 2: Send the SIP URI to dial
    rc, out = await shell(
        f"docker exec e2e_ue1 bash -c \"echo '{call_uri}' >> {_PJSUA_FIFO}\""
    )
    if rc != 0:
        return {"success": False, "call_uri": call_uri, "detail": f"Failed to send dial command: {out}"}

    # Step 3: Poll UE1 logs for call confirmation
    elapsed = 0
    poll_interval = 2
    while elapsed < _CALL_SETUP_TIMEOUT:
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

        rc, logs = await shell(
            "docker logs --tail 20 e2e_ue1 2>&1"
        )
        if "CONFIRMED" in logs:
            log.info("VoNR call established: %s → CONFIRMED", call_uri)
            return {
                "success": True,
                "call_uri": call_uri,
                "detail": "Call established and in CONFIRMED state",
            }

    # Timeout — call didn't connect
    return {
        "success": False,
        "call_uri": call_uri,
        "detail": f"Call setup timed out after {_CALL_SETUP_TIMEOUT}s — call did not reach CONFIRMED state",
    }


async def hangup_call() -> dict:
    """Hang up the active VoNR call on UE1 via pjsua FIFO.

    Returns:
        {success, detail}
    """
    rc, out = await shell(
        f'docker exec e2e_ue1 bash -c "echo h >> {_PJSUA_FIFO}"'
    )
    if rc != 0:
        return {"success": False, "detail": f"Failed to send hangup command: {out}"}

    log.info("VoNR call hangup sent")
    return {"success": True, "detail": "Hangup command sent"}


# -------------------------------------------------------------------------
# Control-plane traffic stimulation (for signaling fault scenarios)
# -------------------------------------------------------------------------

async def trigger_sip_reregister(ue_container: str = "e2e_ue1") -> dict:
    """Force a fresh SIP REGISTER from a UE via pjsua's 'rr' command.

    Writes the 'rr' (re-register) command to the UE's pjsua FIFO. The UE
    will send a new REGISTER transaction through the full IMS signaling
    chain: P-CSCF → I-CSCF → S-CSCF → HSS (Diameter UAR/MAR) → back.

    Use this to generate control-plane traffic during fault propagation
    windows for scenarios that target the signaling path (P-CSCF latency,
    S-CSCF crash, HSS unresponsive, DNS failure, IMS partition, etc.).
    Without fresh signaling, latency and connectivity faults on IMS
    components produce no observable symptoms — existing registrations
    stay cached and nothing exercises the affected path.

    Args:
        ue_container: UE container name (e.g. 'e2e_ue1', 'e2e_ue2').

    Returns:
        {success, detail}
    """
    safe_container = shlex.quote(ue_container)
    rc, out = await shell(
        f'docker exec {safe_container} bash -c "echo rr >> {_PJSUA_FIFO}"'
    )
    if rc != 0:
        return {
            "success": False,
            "detail": f"Failed to send rr command to {ue_container}: {out}",
        }

    log.info("SIP re-register triggered on %s", ue_container)
    return {
        "success": True,
        "detail": f"Re-register command sent to {ue_container}",
    }
