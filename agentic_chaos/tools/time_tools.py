"""
Clock-skew fault primitive — uses `libfaketime` LD_PRELOAD in the target container.

Per CDR-0001 §1 (PyHSS Clock Skew, observability-disruption variant):
the target container must be built with libfaketime pre-loaded and a
writable timestamp file. Specifically:

    # In the target container's Dockerfile:
    RUN apt-get install -y libfaketime && \
        touch /etc/faketimerc && chmod 666 /etc/faketimerc
    ENV LD_PRELOAD=/usr/lib/x86_64-linux-gnu/faketime/libfaketime.so.1 \
        FAKETIME_NO_CACHE=1 \
        FAKETIME_TIMESTAMP_FILE=/etc/faketimerc

With `FAKETIME_NO_CACHE=1` set, libfaketime re-reads `/etc/faketimerc`
on every gettimeofday() call — changes take effect without a process
restart. Writing `+47m` advances the clock by 47 minutes; writing an
empty file (or `+0`) restores the real clock.

If the target container isn't prepped for libfaketime, injection fails
fast with a clear message and the heal step is a harmless no-op.

NOTE: stepping the host clock via `date -s` is rejected because Docker
containers share the host kernel clock by default — a host-clock step
would affect every other container too.
"""

from __future__ import annotations

import logging
import shlex

from ._common import shell, validate_container

log = logging.getLogger("chaos-tools.time")


_FAKETIMERC_PATH = "/etc/faketimerc"


async def inject_clock_skew(target: str, skew_seconds: int) -> dict:
    """Skew the target container's clock by `skew_seconds` via libfaketime.

    Args:
        target: Container name (must be prepped for libfaketime — see
            module docstring).
        skew_seconds: Positive = clock advances; negative = clock rewinds.

    Returns:
        {success, mechanism, heal_cmd, detail}
    """
    safe_target = validate_container(target)
    skew = int(skew_seconds)

    # libfaketime offset syntax: "+47m" or "-3h" etc. Seconds work as "+2820s".
    offset = f"{'+' if skew >= 0 else ''}{skew}s"

    # Step 1: confirm libfaketime is wired up. Check that LD_PRELOAD in the
    # target's PID-1 environ references faketime, and that /etc/faketimerc
    # exists and is writable. We bail with a clear message otherwise.
    precheck_cmd = (
        f"docker exec {safe_target} sh -c '"
        f"grep -q faketime /proc/1/environ "
        f"&& test -w {_FAKETIMERC_PATH} "
        f"&& echo READY || echo MISSING'"
    )
    rc, out = await shell(precheck_cmd)
    if rc != 0 or "READY" not in out:
        return {
            "success": False,
            "mechanism": precheck_cmd,
            "heal_cmd": "true",  # no-op — nothing was changed
            "detail": (
                f"Container '{target}' is not configured for libfaketime "
                f"clock skew. Required: LD_PRELOAD=libfaketime in PID-1 env, "
                f"writable {_FAKETIMERC_PATH}. See CDR-0001 §1."
            ),
        }

    # Step 2: write the offset
    mechanism = (
        f"docker exec {safe_target} sh -c "
        f"{shlex.quote(f'echo {offset} > {_FAKETIMERC_PATH}')}"
    )
    # Heal: truncate the file (libfaketime treats empty as no offset)
    heal_cmd = (
        f"docker exec {safe_target} sh -c "
        f"{shlex.quote(f': > {_FAKETIMERC_PATH}')}"
    )

    rc, output = await shell(mechanism)
    return {
        "success": rc == 0,
        "mechanism": mechanism,
        "heal_cmd": heal_cmd,
        "detail": f"Wrote '{offset}' to {_FAKETIMERC_PATH} in {target}",
    }


async def verify_clock_skew(target: str, min_skew_seconds: int) -> dict:
    """Verify the target container's clock is at least `min_skew_seconds`
    ahead of the host clock.

    Args:
        target: Container name.
        min_skew_seconds: Minimum expected skew (positive = ahead).

    Returns:
        {verified: bool, observed_skew_seconds: int | None, detail}
    """
    safe_target = validate_container(target)

    # Read both clocks back-to-back. The race window between the two `date`
    # calls is well under a second — far smaller than the threshold values
    # we care about (typically thousands of seconds).
    cmd = (
        f"docker exec {safe_target} date +%s "
        f"&& date +%s"
    )
    rc, out = await shell(cmd)
    if rc != 0:
        return {
            "verified": False,
            "observed_skew_seconds": None,
            "detail": f"Failed to read clocks (rc={rc}): {out[:200]}",
        }
    lines = [l.strip() for l in out.splitlines() if l.strip().isdigit()]
    if len(lines) < 2:
        return {
            "verified": False,
            "observed_skew_seconds": None,
            "detail": f"Unexpected clock output: {out!r}",
        }
    container_now = int(lines[0])
    host_now = int(lines[1])
    skew = container_now - host_now
    verified = skew >= min_skew_seconds
    return {
        "verified": verified,
        "observed_skew_seconds": skew,
        "detail": (
            f"Container clock {skew:+d}s vs host "
            f"(threshold: >= {min_skew_seconds:+d}s) — "
            f"{'verified' if verified else 'NOT verified'}"
        ),
    }
