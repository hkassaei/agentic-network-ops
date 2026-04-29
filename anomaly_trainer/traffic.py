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


async def generate_random_traffic(duration_seconds: int = 300) -> None:
    """Generate randomized IMS traffic — the original training mode.

    Pre-Apr-28 trainer behavior. Snapshots are biased toward "calls active"
    because calls are placed frequently throughout the run, with brief idle
    gaps between activities. Kept available for comparison runs; the new
    multi-phase trainer (`generate_phased_traffic`) is preferred because
    it produces training data that spans every operational state the
    runtime can encounter, which the model needs in order to split on
    the new `context.*` features added in 2026-04-28.

    Traffic patterns:
      - SIP REGISTER from UE1 and/or UE2 (random intervals)
      - VoNR call UE1→UE2 (random duration 5-30s)
      - Idle gaps between activities (3-10s)
      - Occasionally both UEs re-register simultaneously
    """
    env = _load_env()
    ims_domain = _get_ims_domain(env)
    callee_imsi = env.get("UE2_IMSI", "001011234567892")

    log.info("Generating IMS traffic for %ds (domain=%s)", duration_seconds, ims_domain)

    elapsed = 0.0
    call_count = 0
    register_count = 0

    # Activity weights and waits tuned to minimize signaling-idle snapshots
    # during training. Previously, ~74% of training snapshots were SIP-idle
    # because 20% of time was explicit idle and most call time (hold phase)
    # saw no new signaling. These knobs collectively cut that to roughly
    # half. ADR: anomaly_training_zero_pollution.md
    while elapsed < duration_seconds:
        # Pick a random activity — idle weight reduced from 20 to 5.
        activity = random.choices(
            ["register_both", "register_ue1", "call", "idle"],
            weights=[20, 15, 45, 5],
        )[0]

        if activity == "register_both":
            log.info("[T+%.0fs] Re-registering both UEs", elapsed)
            await trigger_reregister("e2e_ue1")
            await asyncio.sleep(1)
            await trigger_reregister("e2e_ue2")
            register_count += 2
            # Post-register wait tightened from (3, 8) to (1, 3).
            wait = random.uniform(1, 3)
            await asyncio.sleep(wait)
            elapsed += wait + 1

        elif activity == "register_ue1":
            ue = random.choice(["e2e_ue1", "e2e_ue2"])
            log.info("[T+%.0fs] Re-registering %s", elapsed, ue)
            await trigger_reregister(ue)
            register_count += 1
            # Post-register wait tightened from (3, 6) to (1, 3).
            wait = random.uniform(1, 3)
            await asyncio.sleep(wait)
            elapsed += wait

        elif activity == "call":
            # Call hold shortened from (5, 30) to (5, 15) — same signaling
            # count per call, less dead SIP time during hold.
            call_duration = random.uniform(5, 15)
            log.info("[T+%.0fs] Placing VoNR call (hold %.0fs)", elapsed, call_duration)
            ok = await place_call(ims_domain, callee_imsi)
            if ok:
                call_count += 1
                await asyncio.sleep(call_duration)
                elapsed += call_duration
                await hangup()
                # Settle shortened from (3, 8) to (2, 4) for faster cycling.
                settle = random.uniform(2, 4)
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


# Backward-compatible alias. New callers should prefer the explicit
# `generate_random_traffic` or the new `generate_phased_traffic`.
generate_traffic = generate_random_traffic


# =========================================================================
# Multi-phase traffic generation (Option 1 from anomaly_model_overflagging.md)
# =========================================================================
# Drives the stack through 4 distinct operational phases so the trained
# model sees enough samples in each (calls × registration) combination to
# split on the new `context.*` features. Replaces the random-walk mode
# whose snapshots were biased toward "calls active" — a bias that made
# the model over-flag any runtime period when calls were quiet, for any
# reason (DNS down, network partition, etc.).
#
# Phase taxonomy (drops the original "Phase A — fully unregistered" since
# UEs are an IMS-registered precondition for the trainer):
#
#   Phase B — registration burst       calls=0, reg=1, cx=1
#   Phase C — idle-registered          calls=0, reg=0, cx=0
#   Phase D — active call (held)       calls=1, reg=0, cx=0
#   Phase E — call + register          calls=1, reg=1, cx=1
#
# Both Cx-quiet (C, D) and Cx-active (B, E) phases are exercised across
# both calls-active and calls-idle states, so the trees can split early
# on `context.calls_active` and `context.cx_active` independently.
# =========================================================================

# Default phase length. With a 5-second poll interval, 150s gives ~30
# samples per phase, which is the threshold we set in the validation
# step ("model trained on each context with at least 30 samples").
_PHASE_DURATION_DEFAULT = 150.0

# Re-register cadence inside Phase B (registration burst). Re-registers
# fire every ~6 seconds alternating UE1/UE2, faster than the 30s sliding
# rate window so the rate counter is consistently > 0.
_PHASE_B_REREGISTER_INTERVAL = 6.0

# Re-register cadence inside Phase E (call + register). Slightly slower
# than Phase B so the active-call dialogs aren't disturbed but the
# `context.registration_in_progress` flag still reads 1 over the rate
# window.
_PHASE_E_REREGISTER_INTERVAL = 12.0


async def _phase_b_registration_burst(duration: float) -> tuple[int, int]:
    """Phase B — UEs already registered, fire repeated re-registers.

    Result: `calls_active=0, registration=1, cx=1`. The model sees the
    "Cx is doing work but no calls" region of feature space.
    """
    log.info("=== Phase B: registration burst (%ds) ===", int(duration))
    start = asyncio.get_event_loop().time()
    register_count = 0
    next_ue = 0  # alternate UE1/UE2
    ues = ("e2e_ue1", "e2e_ue2")
    while (asyncio.get_event_loop().time() - start) < duration:
        ue = ues[next_ue]
        await trigger_reregister(ue)
        register_count += 1
        next_ue = 1 - next_ue
        await asyncio.sleep(_PHASE_B_REREGISTER_INTERVAL)
    return register_count, 0


async def _phase_c_idle_registered(duration: float) -> tuple[int, int]:
    """Phase C — quiet stack with registered UEs.

    Result: `calls_active=0, registration=0, cx=0`. The model sees the
    "everything quiet" baseline. SIP REGISTER refresh timers are
    typically 600s, so a 150s phase will not fire any background
    re-registrations.
    """
    log.info("=== Phase C: idle-registered (%ds) ===", int(duration))
    await asyncio.sleep(duration)
    return 0, 0


async def _phase_d_active_call(duration: float, ims_domain: str, callee_imsi: str) -> tuple[int, int]:
    """Phase D — single VoNR call held for the entire phase.

    Result: `calls_active=1, registration=0, cx=0`. The model sees the
    "call in progress, signaling quiet" region — the legitimate steady
    state during a call's hold phase.

    If the call setup fails, the phase logs a warning and sleeps the
    rest of the duration. The trainer's coverage guard will catch a
    persistent failure to enter this state when the model is saved.
    """
    log.info("=== Phase D: active call held (%ds) ===", int(duration))
    ok = await place_call(ims_domain, callee_imsi)
    if not ok:
        log.warning("Phase D: call setup failed, holding idle for the phase")
        await asyncio.sleep(duration)
        return 0, 0
    # Hold the call for the full phase, then hang up cleanly.
    await asyncio.sleep(duration)
    await hangup()
    # Brief settle to let dialog teardown clear before the next phase.
    await asyncio.sleep(2)
    return 0, 1


async def _phase_e_call_plus_register(
    duration: float, ims_domain: str, callee_imsi: str,
) -> tuple[int, int]:
    """Phase E — VoNR call held while re-registers fire periodically.

    Result: `calls_active=1, registration=1, cx=1`. The model sees the
    "call active AND signaling active" composite state — exercises every
    Cx counter while the dialog gauge is non-zero.
    """
    log.info("=== Phase E: call + re-registers (%ds) ===", int(duration))
    ok = await place_call(ims_domain, callee_imsi)
    if not ok:
        log.warning("Phase E: call setup failed, falling back to register-only burst")
        return await _phase_b_registration_burst(duration)

    register_count = 0
    next_ue = 0
    ues = ("e2e_ue1", "e2e_ue2")
    start = asyncio.get_event_loop().time()
    # First re-register slightly delayed so the call's own SAR/MAR
    # doesn't collide with the first triggered re-register.
    await asyncio.sleep(3)
    while (asyncio.get_event_loop().time() - start) < (duration - 3):
        ue = ues[next_ue]
        await trigger_reregister(ue)
        register_count += 1
        next_ue = 1 - next_ue
        await asyncio.sleep(_PHASE_E_REREGISTER_INTERVAL)
    await hangup()
    await asyncio.sleep(2)
    return register_count, 1


async def generate_phased_traffic(
    duration_seconds: int,
    *,
    phase_duration: float = _PHASE_DURATION_DEFAULT,
) -> None:
    """Drive the stack through B → C → D → E phases for the training run.

    Each phase runs for `phase_duration` seconds (default 150s, which is
    ~30 samples at the collector's 5-second poll interval). Total time
    for one full B→C→D→E cycle is ~4 × phase_duration plus minor
    transition overhead. If `duration_seconds` exceeds one cycle, the
    cycle repeats.

    Raises ValueError if `duration_seconds` is too short to complete
    even one full cycle — running an incomplete cycle would leave one
    or more contexts under-trained, defeating the purpose.
    """
    env = _load_env()
    ims_domain = _get_ims_domain(env)
    callee_imsi = env.get("UE2_IMSI", "001011234567892")

    cycle_seconds = phase_duration * 4
    if duration_seconds < cycle_seconds:
        raise ValueError(
            f"Phased traffic requires at least one full B→C→D→E cycle "
            f"({cycle_seconds:.0f}s with phase_duration={phase_duration}s); "
            f"got duration_seconds={duration_seconds}. Either lengthen the "
            f"run or shorten phase_duration."
        )

    log.info(
        "Generating phased IMS traffic: %ds total, %ds per phase "
        "(domain=%s)",
        duration_seconds, int(phase_duration), ims_domain,
    )

    cycle_index = 0
    total_calls = 0
    total_registers = 0
    start = asyncio.get_event_loop().time()

    while True:
        elapsed = asyncio.get_event_loop().time() - start
        # Stop only at cycle boundaries to keep training data balanced
        # across contexts. Going one phase past the deadline is OK; the
        # collector caps its own runtime and silently drops late samples.
        if elapsed >= duration_seconds and cycle_index > 0:
            break
        cycle_index += 1
        log.info("--- Cycle %d (T+%.0fs) ---", cycle_index, elapsed)

        regs, calls = await _phase_b_registration_burst(phase_duration)
        total_registers += regs
        total_calls += calls

        regs, calls = await _phase_c_idle_registered(phase_duration)
        total_registers += regs
        total_calls += calls

        regs, calls = await _phase_d_active_call(
            phase_duration, ims_domain, callee_imsi,
        )
        total_registers += regs
        total_calls += calls

        regs, calls = await _phase_e_call_plus_register(
            phase_duration, ims_domain, callee_imsi,
        )
        total_registers += regs
        total_calls += calls

    final_elapsed = asyncio.get_event_loop().time() - start
    log.info(
        "Phased traffic complete: %d cycles, %d calls, %d re-registrations "
        "over %.0fs",
        cycle_index, total_calls, total_registers, final_elapsed,
    )
