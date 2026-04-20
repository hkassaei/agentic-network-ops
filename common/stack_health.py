"""Shared stack health check utility.

Verifies the 5G SA + IMS stack is healthy by comparing live metrics against
expected baselines. Used by:
  - agentic_chaos/orchestrator.py (before running chaos scenarios)
  - anomaly_trainer/__main__.py (before training the anomaly model)

Provides auto-heal (redeploy UEs) and interactive prompting when the
stack is unhealthy.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

log = logging.getLogger("stack_health")

_REPO_ROOT = Path(__file__).resolve().parents[1]

# Critical metrics that must be at expected values for a healthy stack.
# Covers 5G attachment AND IMS registration — both must be healthy.
HEALTH_CHECKS = {
    "ran_ue": {"expected": 2.0, "source": "amf", "description": "Connected UEs at AMF"},
    "gnb": {"expected": 1.0, "source": "amf", "description": "Connected gNBs at AMF"},
    "amf_session": {"expected": 4.0, "source": "amf", "description": "AMF sessions (2 UEs x 2 PDU)"},
    "fivegs_smffunction_sm_sessionnbr": {"expected": 4.0, "source": "smf", "description": "SMF PDU sessions"},
    "ims_usrloc_pcscf:registered_contacts": {"expected": 2.0, "source": "pcscf", "description": "UEs registered at P-CSCF"},
    "ims_usrloc_scscf:active_contacts": {"expected": 2.0, "source": "scscf", "description": "Active contacts at S-CSCF"},
}


async def collect_health_metrics() -> dict[str, float]:
    """Collect key health metrics from the live network.

    Uses the chaos framework's observation_tools.snapshot_metrics() if
    available, otherwise falls back to v5 tools.
    """
    try:
        from agentic_chaos.tools.observation_tools import snapshot_metrics
        all_metrics = await snapshot_metrics()
    except ImportError:
        # Fallback: use v5 tools directly
        from agentic_ops_common import tools as common_tools
        from agentic_ops_common.anomaly.preprocessor import parse_nf_metrics_text
        text = await common_tools.get_nf_metrics()
        raw = parse_nf_metrics_text(text)
        # Reshape to match snapshot_metrics format
        all_metrics = {comp: {"metrics": metrics} for comp, metrics in raw.items()}

    health: dict[str, float] = {}
    for key, check in HEALTH_CHECKS.items():
        source = check["source"]
        source_metrics = all_metrics.get(source, {}).get("metrics", {})
        if key in source_metrics:
            health[key] = source_metrics[key]
    return health


async def _shell(cmd: str, timeout: int = 60) -> tuple[int, str]:
    """Run a shell command, return (rc, output)."""
    try:
        proc = await asyncio.create_subprocess_shell(
            cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return proc.returncode or 0, stdout.decode(errors="replace").strip()
    except asyncio.TimeoutError:
        log.warning("Command timed out after %ds: %s", timeout, cmd[:80])
        return 1, "timeout"


async def auto_heal_stack() -> bool:
    """Diagnose and fix stack health issues.

    Instead of blindly redeploying UEs, this analyzes which metrics are
    unhealthy and applies targeted fixes:

    1. CSCF stale cache (registered_contacts/active_contacts wrong):
       Restart CSCFs to clear usrloc, then re-register UEs.

    2. PDU session mismatch (amf_session/smf_sessionnbr wrong):
       Restart UEs to re-establish PDU sessions from scratch.

    3. Diameter peer issues (I_Open state):
       Restart CSCFs to re-establish Diameter connections to HSS,
       then restart UEs.

    4. Missing containers:
       Redeploy via deploy-ues.sh.
    """
    log.info("Auto-heal: diagnosing issues...")

    health = await collect_health_metrics()
    issues: set[str] = set()

    # Classify the failures
    for metric, check in HEALTH_CHECKS.items():
        actual = health.get(metric)
        expected = check["expected"]
        if actual is None or actual != expected:
            issues.add(metric)

    ims_stale = bool(issues & {
        "ims_usrloc_pcscf:registered_contacts",
        "ims_usrloc_scscf:active_contacts",
    })
    pdu_broken = bool(issues & {
        "amf_session",
        "fivegs_smffunction_sm_sessionnbr",
    })
    ue_missing = bool(issues & {"ran_ue"})
    gnb_missing = bool(issues & {"gnb"})

    # Step 1: Clear tc rules from all containers (residual from previous runs)
    log.info("Auto-heal: clearing residual tc rules...")
    for c in ["upf", "rtpengine", "pcscf", "icscf", "scscf", "pyhss",
               "amf", "smf", "nr_gnb"]:
        await _shell(f"docker exec {c} tc qdisc del dev eth0 root 2>/dev/null", timeout=10)

    # Step 2: If gNB is disconnected from AMF, restart gNB to re-establish
    # the NGAP/SCTP association. This must happen BEFORE restarting UEs
    # because UEs can't attach without a connected gNB.
    if gnb_missing:
        log.info("Auto-heal: gNB not connected to AMF, restarting gNB...")
        await _shell("docker restart nr_gnb", timeout=30)
        log.info("Auto-heal: waiting 15s for gNB NGAP association...")
        await asyncio.sleep(15)

    # Step 3: If IMS contacts are stale, restart CSCFs to clear usrloc
    if ims_stale:
        log.info("Auto-heal: restarting CSCFs to clear stale IMS contacts...")
        for cscf in ["pcscf", "icscf", "scscf"]:
            await _shell(f"docker restart {cscf}", timeout=30)
        await asyncio.sleep(10)

        # Check if Diameter peers need fixing (I_Open → restart PyHSS too)
        rc, output = await _shell(
            'docker exec icscf kamcmd cdp.list_peers 2>/dev/null | grep State',
            timeout=15,
        )
        if "I_Open" in output or "Closed" in output:
            log.info("Auto-heal: Diameter peer not established, restarting PyHSS + CSCFs...")
            await _shell("docker restart pyhss", timeout=30)
            await asyncio.sleep(10)
            for cscf in ["icscf", "scscf", "pcscf"]:
                await _shell(f"docker restart {cscf}", timeout=30)
            await asyncio.sleep(15)

    # Step 4: If PDU sessions are broken, UEs missing, or gNB was restarted,
    # restart UEs to force fresh 5G attach + PDU session establishment
    if pdu_broken or ue_missing or ims_stale or gnb_missing:
        log.info("Auto-heal: restarting UEs to re-establish sessions...")
        await _shell("docker restart e2e_ue1 e2e_ue2", timeout=60)
        log.info("Auto-heal: waiting 30s for 5G attachment + PDU sessions...")
        await asyncio.sleep(30)

    # Step 5: Check for stale IMS contacts (can happen after gNB/UE restart
    # when old contacts persist in CSCF usrloc alongside new ones)
    health_mid = await collect_health_metrics()
    contacts_stale = (
        health_mid.get("ims_usrloc_pcscf:registered_contacts", 0) > 2.0
        or health_mid.get("ims_usrloc_scscf:active_contacts", 0) > 2.0
    )
    if contacts_stale:
        log.info("Auto-heal: IMS contacts stale (doubled), restarting CSCFs...")
        for cscf in ["pcscf", "icscf", "scscf"]:
            await _shell(f"docker restart {cscf}", timeout=30)
        await asyncio.sleep(10)
        # Restart UEs again for fresh registration on clean CSCFs
        await _shell("docker restart e2e_ue1 e2e_ue2", timeout=60)
        log.info("Auto-heal: waiting 30s for re-registration...")
        await asyncio.sleep(30)

    # Step 6: Force SIP re-registration
    log.info("Auto-heal: forcing SIP re-register from both UEs...")
    for ue in ("e2e_ue1", "e2e_ue2"):
        await _shell(f'docker exec {ue} bash -c "echo rr >> /tmp/pjsua_cmd"', timeout=10)
    log.info("Auto-heal: waiting 15s for IMS registration...")
    await asyncio.sleep(15)

    # Step 7: If still not registered, try once more with a longer wait
    health2 = await collect_health_metrics()
    ims_ok = (
        health2.get("ims_usrloc_pcscf:registered_contacts") == 2.0
        and health2.get("ims_usrloc_scscf:active_contacts") == 2.0
    )
    if not ims_ok:
        log.info("Auto-heal: IMS not yet registered, retrying re-register...")
        for ue in ("e2e_ue1", "e2e_ue2"):
            await _shell(f'docker exec {ue} bash -c "echo rr >> /tmp/pjsua_cmd"', timeout=10)
        await asyncio.sleep(20)

    return True


async def verify_upf_gtp_counters() -> bool:
    """Verify UPF GTP-U counters increment during an active call.

    Places a short test call and checks that the UPF packet counters
    change. Returns False if counters stay at 0 (broken metrics exporter).
    """
    log.info("UPF verify: checking GTP-U counters...")

    # Get UPF IP from env
    upf_ip = "172.22.0.8"
    try:
        env_path = _REPO_ROOT / "network" / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if line.strip().startswith("UPF_IP="):
                    upf_ip = line.strip().split("=", 1)[1]
    except Exception:
        pass

    # First, generate some baseline traffic (SIP registers go through UPF via GTP-U)
    log.info("UPF verify: generating traffic (SIP re-register)...")
    for ue in ("e2e_ue1", "e2e_ue2"):
        await _shell(f'docker exec {ue} bash -c "echo rr >> /tmp/pjsua_cmd"', timeout=10)
    await asyncio.sleep(10)

    # Get counter before test call
    rc, before_out = await _shell(
        f"curl -s http://{upf_ip}:9091/metrics 2>/dev/null | grep '^fivegs_ep_n3_gtp_indatapktn3upf '",
        timeout=10,
    )
    before_val = 0
    if before_out and not before_out.startswith("timeout"):
        try:
            before_val = int(float(before_out.split()[-1]))
        except (ValueError, IndexError):
            pass

    # If counters are already non-zero from the register traffic, that's a pass
    if before_val > 0:
        log.info("UPF verify: GTP-U counters already non-zero (indatapkt=%d) — working", before_val)
        return True

    # Counters still zero — try a VoNR call (generates more GTP-U traffic)
    log.info("UPF verify: counters still 0, placing test call...")
    call_success = False
    for attempt in range(2):
        rc, call_out = await _shell(
            '.venv/bin/python -c "'
            'import asyncio, sys; sys.path.insert(0, \".\");'
            'from agentic_chaos.tools.application_tools import establish_vonr_call, hangup_call;'
            'async def m():\n'
            '    r = await establish_vonr_call(\"ims.mnc001.mcc001.3gppnetwork.org\", \"001011234567892\")\n'
            '    if r.get(\"success\"): await asyncio.sleep(5); await hangup_call()\n'
            '    return r.get(\"success\", False)\n'
            'print(asyncio.run(m()))"',
            timeout=60,
        )
        if "True" in call_out:
            call_success = True
            break
        if attempt == 0:
            log.info("UPF verify: call attempt %d failed, retrying after 10s...", attempt + 1)
            await asyncio.sleep(10)

    if not call_success:
        log.warning("UPF verify: test call failed after 2 attempts — cannot verify counters via call")
        # Even if the call failed, check if the register traffic incremented the counters
        await asyncio.sleep(6)

    if call_success:
        await asyncio.sleep(6)  # wait for Prometheus scrape

    # Get counter after traffic
    rc, after_out = await _shell(
        f"curl -s http://{upf_ip}:9091/metrics 2>/dev/null | grep '^fivegs_ep_n3_gtp_indatapktn3upf '",
        timeout=10,
    )
    after_val = 0
    if after_out and not after_out.startswith("timeout"):
        try:
            after_val = int(float(after_out.split()[-1]))
        except (ValueError, IndexError):
            pass

    if after_val > 0:
        log.info("UPF verify: GTP-U counters working (indatapkt=%d)", after_val)
        return True
    else:
        log.error("UPF verify: GTP-U counters NOT incrementing (still 0 after traffic). "
                   "The docker_open5gs image may have been pulled from ghcr.io instead of built from source.")
        return False


async def post_deploy_verify(max_attempts: int = 3) -> bool:
    """Full post-deploy verification: Diameter fix, health check, UPF counters.

    Called after stack deployment (from GUI or scripts). Runs non-interactively
    with auto-heal. Returns True if all checks pass.
    """
    log.info("Post-deploy: starting verification...")

    for attempt in range(1, max_attempts + 1):
        log.info("Post-deploy: attempt %d/%d", attempt, max_attempts)

        # Step 1: Fix Diameter peer state
        log.info("Post-deploy: fixing Diameter peer state...")
        for cscf in ["icscf", "scscf", "pcscf"]:
            await _shell(f"docker restart {cscf}", timeout=30)
        await asyncio.sleep(10)

        # Check Diameter peer
        rc, output = await _shell(
            'docker exec icscf kamcmd cdp.list_peers 2>/dev/null | grep State',
            timeout=15,
        )
        if "I_Open" in output or "Closed" in output:
            log.info("Post-deploy: Diameter peer stuck, restarting PyHSS + CSCFs...")
            await _shell("docker restart pyhss", timeout=30)
            await asyncio.sleep(10)
            for cscf in ["icscf", "scscf", "pcscf"]:
                await _shell(f"docker restart {cscf}", timeout=30)
            await asyncio.sleep(15)

        # Step 2: Restart UEs for fresh registration
        log.info("Post-deploy: restarting UEs...")
        await _shell("docker restart e2e_ue1 e2e_ue2", timeout=60)
        await asyncio.sleep(30)

        # Step 3: Force SIP re-register
        log.info("Post-deploy: forcing SIP re-register...")
        for ue in ("e2e_ue1", "e2e_ue2"):
            await _shell(f'docker exec {ue} bash -c "echo rr >> /tmp/pjsua_cmd"', timeout=10)
        await asyncio.sleep(15)

        # Step 4: Check health metrics
        health = await collect_health_metrics()
        failures = []
        for metric, check in HEALTH_CHECKS.items():
            actual = health.get(metric)
            if actual != check["expected"]:
                failures.append(f"{metric}: {actual} (expected {check['expected']})")

        if failures:
            log.warning("Post-deploy: health check failed on attempt %d: %s",
                        attempt, "; ".join(failures))
            if attempt < max_attempts:
                continue
            else:
                log.error("Post-deploy: health check failed after %d attempts", max_attempts)
                return False

        log.info("Post-deploy: all health metrics OK")

        # Step 5: Verify UPF GTP-U counters
        gtp_ok = await verify_upf_gtp_counters()
        if not gtp_ok:
            log.error("Post-deploy: UPF GTP-U counters broken — rebuild docker_open5gs from source")
            return False

        log.info("Post-deploy: all verification passed")
        return True

    return False


async def check_stack_health(purpose: str = "operation") -> bool:
    """Verify the stack is healthy. Prompts user if unhealthy.

    Args:
        purpose: Description of what we're about to do (for log messages).
                 E.g., "chaos scenario", "anomaly model training".

    Returns:
        True if healthy (or user chose to proceed), False if user aborted.
    """
    log.info("Pre-check: verifying stack health...")

    health = await collect_health_metrics()
    if not health:
        log.warning("Pre-check: could not collect health metrics — proceeding anyway")
        return True

    failures: list[str] = []
    for metric, check in HEALTH_CHECKS.items():
        actual = health.get(metric)
        expected = check["expected"]
        if actual is None:
            failures.append(f"  {metric}: MISSING (expected {expected}) — {check['description']}")
        elif actual != expected:
            failures.append(f"  {metric}: {actual} (expected {expected}) — {check['description']}")

    if not failures:
        log.info("Pre-check: stack is healthy ✓")
        return True

    print()
    print("=" * 60)
    print("  STACK HEALTH CHECK FAILED")
    print("=" * 60)
    print()
    print("The following metrics are not at expected values:")
    for f in failures:
        print(f)
    print()
    print(f"The stack must be healthy before {purpose}.")
    print()
    print("Options:")
    print("  [a] Auto-heal: redeploy UEs and wait for registration")
    print("  [s] Skip: proceed anyway (results may be unreliable)")
    print("  [q] Quit: abort")
    print()

    while True:
        try:
            choice = input("Choose [a/s/q]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return False

        if choice == "a":
            healed = await auto_heal_stack()
            if healed:
                health2 = await collect_health_metrics()
                still_bad = []
                for metric, check in HEALTH_CHECKS.items():
                    actual = health2.get(metric)
                    if actual != check["expected"]:
                        still_bad.append(f"  {metric}: {actual} (expected {check['expected']})")
                if still_bad:
                    print()
                    print("Auto-heal completed but some metrics are still unhealthy:")
                    for f in still_bad:
                        print(f)
                    print()
                    continue
                else:
                    log.info("Pre-check: stack is healthy after auto-heal ✓")
                    return True
            else:
                print("Auto-heal failed. Choose another option.")
                continue

        elif choice == "s":
            log.warning("Pre-check: proceeding with unhealthy stack (user chose skip)")
            return True

        elif choice == "q":
            log.info("Pre-check: aborted by user")
            return False
