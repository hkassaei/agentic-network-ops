"""Probe-level tool_unavailable handling.

Verifies that:
  - `_container_has_binary` results are cached.
  - `measure_rtt` returns the PROBE_TOOL_UNAVAILABLE token when the
    target container is missing `ping` (the failure path the original
    `run_20260504_160632` incident hit).
  - `check_process_listeners` returns the same token when neither
    `ss` nor `netstat` is present.

The shell layer is mocked — we test the gating logic, not Docker.
See docs/ADR/nf_container_diagnostic_tooling.md.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from agentic_ops import tools
from agentic_ops.tools import (
    PROBE_TOOL_UNAVAILABLE_PREFIX,
    _BINARY_AVAILABILITY_CACHE,
)


class _Deps:
    """Minimal AgentDeps stand-in. The real one carries more fields,
    but the probe wrappers only read `all_containers`."""

    def __init__(self, containers: list[str]) -> None:
        self.all_containers = containers


@pytest.fixture(autouse=True)
def _clear_cache():
    """Each test starts with a fresh binary-availability cache so the
    mocks don't leak across cases."""
    _BINARY_AVAILABILITY_CACHE.clear()
    yield
    _BINARY_AVAILABILITY_CACHE.clear()


def _patch_shell(monkeypatch: pytest.MonkeyPatch, responder):
    """Replace tools._shell with `responder(cmd) -> (rc, output)`.

    `responder` may be a sync function returning the tuple or an async
    one — we wrap both into an async stub.
    """
    async def _stub(cmd: str, cwd: str | None = None) -> tuple[int, str]:
        result = responder(cmd)
        if asyncio.iscoroutine(result):
            return await result
        return result

    monkeypatch.setattr(tools, "_shell", _stub)


# ---------------------------------------------------------------------------
# _container_has_binary
# ---------------------------------------------------------------------------


def test_container_has_binary_caches(monkeypatch: pytest.MonkeyPatch) -> None:
    """Repeat checks on the same (container, binary) must hit the cache
    rather than re-shelling."""
    calls: list[str] = []

    def responder(cmd: str) -> tuple[int, str]:
        calls.append(cmd)
        return (0, "")

    _patch_shell(monkeypatch, responder)

    a = asyncio.run(tools._container_has_binary("rtpengine", "ping"))
    b = asyncio.run(tools._container_has_binary("rtpengine", "ping"))
    assert a is True and b is True
    assert len(calls) == 1, f"expected one shell call, got {len(calls)}: {calls}"


# ---------------------------------------------------------------------------
# measure_rtt gating
# ---------------------------------------------------------------------------


def test_measure_rtt_returns_tool_unavailable_when_ping_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The original failure: rtpengine has no ping. We must NOT silently
    return a generic failure string the LLM can read as ambiguous —
    instead surface the PROBE_TOOL_UNAVAILABLE token."""
    def responder(cmd: str) -> tuple[int, str]:
        if "command -v ping" in cmd:
            return (1, "")  # ping not present
        # The real ping invocation should never run in this test.
        raise AssertionError(f"unexpected shell call: {cmd}")

    _patch_shell(monkeypatch, responder)

    deps = _Deps(["rtpengine", "upf"])
    out = asyncio.run(tools.measure_rtt(deps, "rtpengine", "172.22.0.19"))

    assert out.startswith(PROBE_TOOL_UNAVAILABLE_PREFIX), out
    assert "ping" in out
    assert "rtpengine" in out


def test_measure_rtt_runs_ping_when_present(monkeypatch: pytest.MonkeyPatch) -> None:
    """Happy path: ping exists, the real RTT output reaches the LLM."""
    def responder(cmd: str) -> tuple[int, str]:
        if "command -v ping" in cmd:
            return (0, "")  # present
        if "ping -c 3" in cmd:
            return (0, "PING 172.22.0.19 ... rtt min/avg/max = 0.1/0.2/0.3 ms")
        raise AssertionError(f"unexpected shell call: {cmd}")

    _patch_shell(monkeypatch, responder)

    deps = _Deps(["rtpengine"])
    out = asyncio.run(tools.measure_rtt(deps, "rtpengine", "172.22.0.19"))

    assert "rtt min/avg/max" in out
    assert PROBE_TOOL_UNAVAILABLE_PREFIX not in out


def test_measure_rtt_unknown_container_short_circuits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Container-name validation runs before the binary preflight, so an
    unknown container produces a different (existing) error and never
    invokes the shell."""
    def responder(cmd: str) -> tuple[int, str]:
        raise AssertionError(f"shell should not be called: {cmd}")

    _patch_shell(monkeypatch, responder)

    deps = _Deps(["amf"])
    out = asyncio.run(tools.measure_rtt(deps, "rtpengine", "1.2.3.4"))

    assert "Unknown container" in out
    assert PROBE_TOOL_UNAVAILABLE_PREFIX not in out


# ---------------------------------------------------------------------------
# check_process_listeners gating
# ---------------------------------------------------------------------------


def test_check_process_listeners_tool_unavailable_when_neither_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If both ss and netstat are missing, return the PROBE_TOOL_UNAVAILABLE
    token — not the historical 'Neither ss nor netstat available' string,
    which the LLM was reading as soft non-evidence."""
    def responder(cmd: str) -> tuple[int, str]:
        if "command -v ss" in cmd or "command -v netstat" in cmd:
            return (1, "")
        raise AssertionError(f"unexpected shell call: {cmd}")

    _patch_shell(monkeypatch, responder)

    deps = _Deps(["pyhss"])
    out = asyncio.run(tools.check_process_listeners(deps, "pyhss"))

    assert out.startswith(PROBE_TOOL_UNAVAILABLE_PREFIX), out
    assert "pyhss" in out


def test_check_process_listeners_uses_ss_when_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def responder(cmd: str) -> tuple[int, str]:
        if "command -v ss" in cmd:
            return (0, "")
        if "ss -tulnp" in cmd:
            return (0, "Netid State Recv-Q Send-Q Local Address ...")
        raise AssertionError(f"unexpected shell call: {cmd}")

    _patch_shell(monkeypatch, responder)

    deps = _Deps(["amf"])
    out = asyncio.run(tools.check_process_listeners(deps, "amf"))

    assert "Netid" in out
    assert PROBE_TOOL_UNAVAILABLE_PREFIX not in out


def test_check_process_listeners_falls_back_to_netstat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ss missing but netstat present — fall back without surfacing as
    tool_unavailable. (Matches the historical fallback intent;
    confirmed by the gating change preserving it.)"""
    def responder(cmd: str) -> tuple[int, str]:
        if "command -v ss" in cmd:
            return (1, "")
        if "command -v netstat" in cmd:
            return (0, "")
        if "netstat -tulnp" in cmd:
            return (0, "Active Internet connections ...")
        raise AssertionError(f"unexpected shell call: {cmd}")

    _patch_shell(monkeypatch, responder)

    deps = _Deps(["amf"])
    out = asyncio.run(tools.check_process_listeners(deps, "amf"))

    assert "Active Internet connections" in out
    assert PROBE_TOOL_UNAVAILABLE_PREFIX not in out
