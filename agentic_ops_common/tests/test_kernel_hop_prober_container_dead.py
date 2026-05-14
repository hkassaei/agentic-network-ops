"""KernelHopProber must surface dead containers as `ContainerDeadHop`.

Regression target: run_20260514_193941_cascading_ims_failure.md, where
hops 16/22/26 of the `pyhss` container (which was killed by the chaos
scenario) all reported `inconclusive: tool_unavailable: required binary
'tc' missing in container 'pyhss'`. This was indistinguishable from the
healthy steady-state output — the pyhss image *never* has tc installed
— so the localized synthesis missed the dead container entirely and
the cascading scenario scored 15%.

Per task #61 of the team task tracker, the prober now checks
`docker inspect <container>` BEFORE the qdisc/iface probes and returns
`ContainerDeadHop(status=...)` for any State.Status other than
`running`.

The prober's `get_container_status` call is mocked here at the module
boundary so we test the attribution logic without touching real
containers.
"""

from __future__ import annotations

import asyncio

from agentic_ops_common.path_walk import (
    ContainerDeadHop,
    InconclusiveHop,
    Hop,
    KernelHopProber,
)


def _hop(node: str = "pyhss", iface: str = "eth0") -> Hop:
    return Hop(node=node, kind="container", iface=iface)


def _patch_status(monkeypatch, status: str) -> None:
    """Replace `get_container_status` in the kernel-prober module with a stub."""
    from agentic_ops_common.path_walk.probers import kernel

    async def status_stub(container: str) -> str:
        return status

    monkeypatch.setattr(kernel, "get_container_status", status_stub)


def _patch_probes(monkeypatch, qdisc_result: dict, iface_result: dict) -> None:
    """Stub the qdisc/iface tools so the prober gets predictable results.

    Mirrors the helper in test_kernel_hop_prober — duplicated here so this
    file stays self-contained and doesn't drag in unrelated fixtures.
    """
    from agentic_ops_common.path_walk.probers import kernel

    async def qdisc_stub(container, iface):
        return qdisc_result

    async def iface_stub(container, iface):
        return iface_result

    monkeypatch.setattr(kernel, "get_qdisc_drops", qdisc_stub)
    monkeypatch.setattr(kernel, "get_interface_drops", iface_stub)


# ---------------------------------------------------------------------------
# The regression: container exited → ContainerDeadHop, not InconclusiveHop
# ---------------------------------------------------------------------------


def test_kernel_prober_attributes_exited_container_to_container_dead(monkeypatch):
    """The exact attack from run_20260514_193941_cascading_ims_failure.

    Pre-fix the pyhss container's qdisc probe would have hit the
    `_container_has_binary` check, found `tc` missing, and emitted
    `InconclusiveHop(reason="tool_unavailable")`. Post-fix the
    container-status check fires first and returns `ContainerDeadHop`.
    """
    _patch_status(monkeypatch, status="exited")
    # qdisc/iface stubs should NEVER be called — the prober must
    # short-circuit on the status check. We still patch them so a
    # regression that calls through gets a clear assertion failure.

    async def must_not_run_qdisc(container, iface):
        raise AssertionError(
            "qdisc probe ran against a non-running container "
            "(should have short-circuited at the status check)"
        )

    async def must_not_run_iface(container, iface):
        raise AssertionError(
            "iface probe ran against a non-running container "
            "(should have short-circuited at the status check)"
        )

    from agentic_ops_common.path_walk.probers import kernel
    monkeypatch.setattr(kernel, "get_qdisc_drops", must_not_run_qdisc)
    monkeypatch.setattr(kernel, "get_interface_drops", must_not_run_iface)

    prober = KernelHopProber()
    attribution = asyncio.run(prober.probe(_hop("pyhss"), 5, None))

    assert attribution.kind == "container_dead"
    assert isinstance(attribution, ContainerDeadHop)
    assert attribution.status == "exited"
    assert "pyhss" in attribution.detail
    assert "exited" in attribution.detail


def test_kernel_prober_attributes_absent_container_to_container_dead(monkeypatch):
    """`absent` (the sentinel for "no such container") behaves the same
    as `exited` — the container is not running, so probes can't run."""
    _patch_status(monkeypatch, status="absent")

    prober = KernelHopProber()
    attribution = asyncio.run(prober.probe(_hop("ghost"), 5, None))

    assert isinstance(attribution, ContainerDeadHop)
    assert attribution.status == "absent"


def test_kernel_prober_attributes_paused_container_to_container_dead(monkeypatch):
    """`paused` is also non-running. The dataclass is intentionally
    permissive about the status string so future Docker statuses
    (`removing`, `dead`, etc.) are caught by the same branch."""
    _patch_status(monkeypatch, status="paused")

    prober = KernelHopProber()
    attribution = asyncio.run(prober.probe(_hop("pyhss"), 5, None))

    assert isinstance(attribution, ContainerDeadHop)
    assert attribution.status == "paused"


# ---------------------------------------------------------------------------
# Current behavior preserved: running + tc missing is still tool_unavailable
# ---------------------------------------------------------------------------


def test_kernel_prober_running_container_with_tc_missing_is_still_inconclusive(monkeypatch):
    """The OLD behavior — running pyhss, tc binary missing — still
    produces `InconclusiveHop(reason="tool_unavailable")`. This is what
    we want: a healthy container that just lacks the probe binary is
    a real toolbelt gap, not a container-death.

    Without this test, a future refactor could accidentally map both
    cases to container_dead and lose the distinction the whole task
    was about creating.
    """
    _patch_status(monkeypatch, status="running")
    _patch_probes(
        monkeypatch,
        qdisc_result={
            "_error": "tool_unavailable",
            "missing_binary": "tc",
            "container": "pyhss",
        },
        iface_result={},
    )

    prober = KernelHopProber()
    attribution = asyncio.run(prober.probe(_hop("pyhss"), 5, None))

    assert attribution.kind == "inconclusive"
    assert isinstance(attribution, InconclusiveHop)
    assert attribution.reason == "tool_unavailable"
    assert "'tc'" in attribution.detail


def test_kernel_prober_running_container_normal_path_still_clean(monkeypatch):
    """A running container with healthy probes still produces CleanHop —
    the status check is additive, not behavior-changing for the happy path."""
    _patch_status(monkeypatch, status="running")
    _patch_probes(
        monkeypatch,
        qdisc_result={
            "qdisc_kind": "noqueue",
            "sent_pkts": 100,
            "dropped_pkts": 0,
            "dropped_pct": 0.0,
            "loss_pct": None,
            "delay_ms": None,
            "raw": "qdisc noqueue 0: root refcnt 2",
        },
        iface_result={
            "rx_bytes": 1, "rx_pkts": 1, "rx_errors": 0, "rx_dropped": 0,
            "tx_bytes": 1, "tx_pkts": 1, "tx_errors": 0, "tx_dropped": 0,
            "raw": "...",
        },
    )

    prober = KernelHopProber()
    attribution = asyncio.run(prober.probe(_hop("pyhss"), 5, None))

    assert attribution.kind == "clean"
