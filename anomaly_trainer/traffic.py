"""Traffic generator — produces realistic IMS traffic patterns on a healthy stack.

Generates randomized sequences of:
  - SIP REGISTER (UE re-registration)
  - VoNR call setup + hold + hangup
  - Idle periods between activities

Uses the existing pjsua FIFO commands from the chaos framework's
application_tools module. The network must have UEs deployed and
IMS-registered before running.
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import shlex
from pathlib import Path

log = logging.getLogger("anomaly_trainer.traffic")

_REPO_ROOT = Path(__file__).resolve().parents[1]
_PJSUA_FIFO = "/tmp/pjsua_cmd"


def _load_env() -> dict[str, str]:
    """Load .env and e2e.env."""
    env: dict[str, str] = {**os.environ}
    for envfile in [_REPO_ROOT / "network" / ".env", _REPO_ROOT / "e2e.env"]:
        if envfile.exists():
            for line in envfile.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
    return env


def _get_ims_domain(env: dict[str, str]) -> str:
    """Derive the IMS domain from MCC/MNC."""
    mcc = env.get("MCC", "001")
    mnc = env.get("MNC", "01")
    if len(mnc) == 3:
        return f"ims.mnc{mnc}.mcc{mcc}.3gppnetwork.org"
    return f"ims.mnc0{mnc}.mcc{mcc}.3gppnetwork.org"


async def _shell(cmd: str) -> tuple[int, str]:
    """Run a shell command, return (rc, combined output)."""
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    stdout, _ = await proc.communicate()
    return proc.returncode or 0, stdout.decode(errors="replace").strip()


async def _send_pjsua_cmd(container: str, cmd: str) -> bool:
    """Send a command to a UE's pjsua FIFO."""
    safe = shlex.quote(container)
    rc, out = await _shell(f'docker exec {safe} bash -c "echo {cmd} >> {_PJSUA_FIFO}"')
    return rc == 0


async def trigger_reregister(container: str = "e2e_ue1") -> bool:
    """Force a fresh SIP REGISTER from a UE."""
    ok = await _send_pjsua_cmd(container, "rr")
    if ok:
        log.debug("  re-register triggered on %s", container)
    return ok


async def place_call(ims_domain: str, callee_imsi: str) -> bool:
    """Place a VoNR call from UE1 to UE2. Returns True if call reaches CONFIRMED."""
    call_uri = f"sip:{callee_imsi}@{ims_domain}"
    log.debug("  placing call: %s", call_uri)

    # Send 'm' (make-call menu)
    if not await _send_pjsua_cmd("e2e_ue1", "m"):
        return False
    await asyncio.sleep(2)

    # Send the SIP URI
    rc, _ = await _shell(
        f"docker exec e2e_ue1 bash -c \"echo '{call_uri}' >> {_PJSUA_FIFO}\""
    )
    if rc != 0:
        return False

    # Poll for CONFIRMED state (max 30s)
    for _ in range(15):
        await asyncio.sleep(2)
        rc, logs = await _shell("docker logs --tail 20 e2e_ue1 2>&1")
        if "CONFIRMED" in logs:
            log.debug("  call CONFIRMED")
            return True

    log.warning("  call did not reach CONFIRMED within 30s")
    return False


async def hangup() -> bool:
    """Hang up the active call on UE1."""
    ok = await _send_pjsua_cmd("e2e_ue1", "h")
    if ok:
        log.debug("  hangup sent")
    return ok


async def generate_traffic(duration_seconds: int = 300) -> None:
    """Generate realistic randomized IMS traffic for the specified duration.

    Traffic patterns:
      - SIP REGISTER from UE1 and/or UE2 (random intervals)
      - VoNR call UE1→UE2 (random duration 5-30s)
      - Idle gaps between activities (3-10s)
      - Occasionally both UEs re-register simultaneously

    The goal is to keep the network rarely idle during the training window,
    exercising the full IMS signaling and data plane paths.
    """
    env = _load_env()
    ims_domain = _get_ims_domain(env)
    callee_imsi = env.get("UE2_IMSI", "001011234567892")

    log.info("Generating IMS traffic for %ds (domain=%s)", duration_seconds, ims_domain)

    elapsed = 0.0
    call_count = 0
    register_count = 0

    while elapsed < duration_seconds:
        # Pick a random activity
        activity = random.choices(
            ["register_both", "register_ue1", "call", "idle"],
            weights=[20, 15, 45, 20],
        )[0]

        if activity == "register_both":
            log.info("[T+%.0fs] Re-registering both UEs", elapsed)
            await trigger_reregister("e2e_ue1")
            await asyncio.sleep(1)
            await trigger_reregister("e2e_ue2")
            register_count += 2
            wait = random.uniform(3, 8)
            await asyncio.sleep(wait)
            elapsed += wait + 1

        elif activity == "register_ue1":
            ue = random.choice(["e2e_ue1", "e2e_ue2"])
            log.info("[T+%.0fs] Re-registering %s", elapsed, ue)
            await trigger_reregister(ue)
            register_count += 1
            wait = random.uniform(3, 6)
            await asyncio.sleep(wait)
            elapsed += wait

        elif activity == "call":
            call_duration = random.uniform(5, 30)
            log.info("[T+%.0fs] Placing VoNR call (hold %.0fs)", elapsed, call_duration)
            ok = await place_call(ims_domain, callee_imsi)
            if ok:
                call_count += 1
                await asyncio.sleep(call_duration)
                elapsed += call_duration
                await hangup()
                # Brief settling time after hangup
                settle = random.uniform(3, 8)
                await asyncio.sleep(settle)
                elapsed += settle
            else:
                log.warning("[T+%.0fs] Call setup failed — continuing", elapsed)
                wait = random.uniform(5, 10)
                await asyncio.sleep(wait)
                elapsed += wait

        else:  # idle
            idle_time = random.uniform(3, 10)
            log.info("[T+%.0fs] Idle for %.0fs", elapsed, idle_time)
            await asyncio.sleep(idle_time)
            elapsed += idle_time

    log.info("Traffic generation complete: %d calls, %d registrations over %.0fs",
             call_count, register_count, elapsed)
