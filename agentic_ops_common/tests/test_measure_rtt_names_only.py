"""Tests for the names-only contract on `measure_rtt`.

Per ADR `agent_tool_args_must_be_names_not_ips.md`, the agent-facing
`measure_rtt` accepts only container names — not IP literals. This
pins the contract:

  1. Both `container` and `target` are validated against the deployment
     topology before any shell command runs.
  2. IP-shaped strings are rejected with a corrective error message
     that tells the LLM what shape the argument should have.
  3. Unknown container names are rejected with a hint listing the
     known names.
  4. The deprecated `target_ip=` keyword alias still works for legacy
     v1.5/v2 callers, but is constrained the same way (IP-shaped
     values are rejected regardless of which keyword they came in on).
  5. The shell command is only built when validation has passed, and
     uses the container name directly (the kernel ping resolves it
     via docker's embedded DNS).

These tests stub the shell layer so they run without docker / without
a real stack. The test for the happy path verifies that the issued
`ping` command targets the **name**, not an IP.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import AsyncMock, patch

import pytest

from agentic_ops import tools as t
from agentic_ops.tools import _looks_like_ip


@dataclass
class _Deps:
    """Minimal AgentDeps stand-in for the tool's container-allowlist check."""
    all_containers: list[str] = field(default_factory=lambda: [
        "pcscf", "icscf", "scscf", "pyhss", "amf", "smf", "upf",
        "rtpengine", "nr_gnb", "dns",
    ])
    # The real AgentDeps has many other fields; measure_rtt only reads
    # `all_containers`, so this is sufficient.


# ─────────────────────────────────────────────────────────────────────
# _looks_like_ip — the IP-shape detector
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("value", [
    "172.22.0.8",
    "172.22.0.18",
    "10.0.0.1",
    "192.168.1.1",
    "127.0.0.1",
    "8.8.8.8",
    "0.0.0.0",
    "999.999.999.999",  # not a *valid* IP but still IP-shaped
])
def test_ip_shape_detector_matches_dotted_quad(value):
    assert _looks_like_ip(value)


@pytest.mark.parametrize("value", [
    "pyhss",
    "pcscf",
    "rtpengine",
    "icscf-1",
    "172.22.0",       # only 3 octets
    "172.22.0.8.9",   # 5 parts
    "abc.def.ghi.jkl",
    "172.22.0.abc",
    "",
    "172",
    "host-with-dots",
    "1.2.3",
])
def test_ip_shape_detector_rejects_non_ips(value):
    assert not _looks_like_ip(value)


# ─────────────────────────────────────────────────────────────────────
# Validation paths (no shell calls)
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_measure_rtt_rejects_ip_literal_target():
    """The failure mode this whole change closes: LLM passes an IP."""
    deps = _Deps()
    result = await t.measure_rtt(deps, container="icscf", target="172.22.0.18")
    assert "looks like an IP literal" in result
    assert "container NAME" in result
    assert "ADR" in result  # cite the ADR so the LLM understands


@pytest.mark.asyncio
async def test_measure_rtt_rejects_ip_literal_passed_via_deprecated_target_ip():
    """Legacy `target_ip=` kwarg is honored for the parameter name, but
    IP-shape rejection fires regardless of which arg name was used."""
    deps = _Deps()
    result = await t.measure_rtt(deps, container="icscf", target_ip="172.22.0.18")
    assert "looks like an IP literal" in result


@pytest.mark.asyncio
async def test_measure_rtt_rejects_unknown_source_container():
    deps = _Deps()
    result = await t.measure_rtt(deps, container="not_a_real_nf", target="pyhss")
    assert "Unknown source container" in result
    assert "not_a_real_nf" in result


@pytest.mark.asyncio
async def test_measure_rtt_rejects_unknown_target_container():
    deps = _Deps()
    result = await t.measure_rtt(deps, container="icscf", target="not_a_real_nf")
    assert "Unknown target container" in result
    assert "not_a_real_nf" in result


@pytest.mark.asyncio
async def test_measure_rtt_rejects_missing_target():
    """Calling with neither `target=` nor `target_ip=` is an error,
    not a silent default."""
    deps = _Deps()
    result = await t.measure_rtt(deps, container="icscf")  # no target
    assert "Missing `target`" in result


@pytest.mark.asyncio
async def test_measure_rtt_rejects_conflicting_target_and_target_ip():
    """Programmer error: passing both kwargs with different values."""
    deps = _Deps()
    result = await t.measure_rtt(
        deps, container="icscf", target="pyhss", target_ip="amf",
    )
    assert "Conflicting" in result


@pytest.mark.asyncio
async def test_measure_rtt_accepts_target_ip_as_alias_when_target_omitted():
    """Backward compat: v1.5/v2 wrappers that pass `target_ip=<NAME>`
    continue to work as long as the value is a valid name."""
    deps = _Deps()
    with patch.object(t, "_container_has_binary", new=AsyncMock(return_value=True)):
        with patch.object(t, "_shell", new=AsyncMock(return_value=(0, "rtt 0/0/0 ms"))) as shell:
            result = await t.measure_rtt(
                deps, container="icscf", target_ip="pyhss",
            )
            assert "rtt" in result
            # Crucial: the ping command targets the NAME, not the
            # original alias value transformed somehow.
            cmd = shell.await_args.args[0]
            assert "ping " in cmd
            assert " pyhss" in cmd
            assert "172.22" not in cmd  # no IP leaked into the shell


# ─────────────────────────────────────────────────────────────────────
# Happy path — shell command uses the NAME
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_measure_rtt_happy_path_pings_by_name():
    """The kernel ping inside the container resolves the name via docker
    DNS — the shell command must target the name, not an IP."""
    deps = _Deps()
    with patch.object(t, "_container_has_binary", new=AsyncMock(return_value=True)):
        with patch.object(t, "_shell", new=AsyncMock(return_value=(
            0,
            "66 packets transmitted, 66 received, 0% packet loss\n"
            "rtt min/avg/max/mdev = 0.05/0.10/0.30/0.04 ms",
        ))) as shell:
            result = await t.measure_rtt(deps, container="icscf", target="pyhss")
            assert "rtt min/avg" in result
            cmd = shell.await_args.args[0]
            # Source container is `icscf`; target is the `pyhss` NAME.
            assert "docker exec icscf ping" in cmd
            assert cmd.rstrip().endswith(" pyhss")
            assert "172.22" not in cmd, (
                "Shell command leaked an IP literal — the names-only "
                "contract requires the ping target to be a name."
            )


@pytest.mark.asyncio
async def test_measure_rtt_unreachable_reports_name():
    """The user-visible 'unreachable' message names the target by name,
    not by IP — keeps the output consistent with the input shape."""
    deps = _Deps()
    with patch.object(t, "_container_has_binary", new=AsyncMock(return_value=True)):
        with patch.object(t, "_shell", new=AsyncMock(return_value=(
            1,
            "PING pyhss: 66 packets transmitted, 0 received, 100% packet loss",
        ))):
            result = await t.measure_rtt(deps, container="icscf", target="pyhss")
            assert "UNREACHABLE" in result
            assert "pyhss" in result
            # No IP in the formatted error.
            assert "172.22" not in result


@pytest.mark.asyncio
async def test_measure_rtt_tool_unavailable_when_ping_missing():
    """ping binary missing inside the source container is a tool-
    unavailable signal — not silently treated as 100% loss."""
    deps = _Deps()
    with patch.object(t, "_container_has_binary", new=AsyncMock(return_value=False)):
        result = await t.measure_rtt(deps, container="icscf", target="pyhss")
        assert "PROBE_TOOL_UNAVAILABLE" in result or "tool_unavailable" in result.lower()
