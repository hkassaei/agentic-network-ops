"""Tests for the container-state pre-check + recovery added to
`common/stack_health.py`.

The metric-based HEALTH_CHECKS alone could not catch a mid-batch
container crash (e.g. SCP exiting) because the affected NFs don't
expose any of the six tracked metrics. These tests cover the new
`check_containers_running()` and `restart_exited_containers()`
helpers that close that gap.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest


# ============================================================================
# REQUIRED_CONTAINERS — must stay in sync with gui/server.py
# ============================================================================

def test_required_containers_match_gui_list():
    """The chaos framework's pre-check and the GUI's stack page both
    track the same list of "must be running" containers. They are
    deliberately duplicated (rather than imported from a shared module)
    because each side has its own reasons for the list, but they
    should never drift apart in practice.

    If this test fails, decide which list is canonical and reconcile —
    but do not silently let the two diverge.
    """
    from common.stack_health import (
        REQUIRED_CONTAINERS as health_required,
        GNB_CONTAINER as health_gnb,
        UE_CONTAINERS as health_ues,
    )

    # Pull the GUI's list by parsing the source — gui/server.py
    # intentionally has no test-friendly export, but the constant is
    # at module scope so we can grab it without importing aiohttp.
    from pathlib import Path
    import re
    src = (Path(__file__).resolve().parents[2]
           / "gui" / "server.py").read_text()
    m = re.search(
        r'REQUIRED_CONTAINERS\s*=\s*\[(.*?)\]',
        src, re.DOTALL,
    )
    assert m, "couldn't locate REQUIRED_CONTAINERS in gui/server.py"
    gui_required = re.findall(r'"([^"]+)"', m.group(1))

    assert set(health_required) == set(gui_required), (
        f"common/stack_health.py REQUIRED_CONTAINERS = {sorted(health_required)} "
        f"vs gui/server.py REQUIRED_CONTAINERS = {sorted(gui_required)} — "
        f"these must stay in sync"
    )

    # gNB is a single container; the GUI keeps it separate too.
    assert "nr_gnb" == health_gnb
    assert {"e2e_ue1", "e2e_ue2"} == set(health_ues)


# ============================================================================
# `_container_status` — the docker inspect helper
# ============================================================================

@pytest.mark.asyncio
async def test_container_status_returns_running_when_inspect_succeeds():
    """`docker inspect` returns rc=0 with 'running' on stdout → status
    is 'running'."""
    from common import stack_health

    async def fake_shell(cmd, timeout=5):
        return 0, "running"

    with patch.object(stack_health, "_shell", side_effect=fake_shell):
        s = await stack_health._container_status("scp")
        assert s == "running"


@pytest.mark.asyncio
async def test_container_status_returns_exited_for_crashed_container():
    """A crashed container leaves an 'exited' status — this is the
    common SCP-crash case the whole work item exists to catch."""
    from common import stack_health

    async def fake_shell(cmd, timeout=5):
        return 0, "exited"

    with patch.object(stack_health, "_shell", side_effect=fake_shell):
        s = await stack_health._container_status("scp")
        assert s == "exited"


@pytest.mark.asyncio
async def test_container_status_returns_absent_when_container_does_not_exist():
    """If `docker inspect` fails (rc != 0), the container is treated
    as absent. This covers both "never deployed" and "removed via
    docker rm" cases — both require an operator-driven re-deploy."""
    from common import stack_health

    async def fake_shell(cmd, timeout=5):
        return 1, "Error: No such object: bogus"

    with patch.object(stack_health, "_shell", side_effect=fake_shell):
        s = await stack_health._container_status("bogus")
        assert s == "absent"


@pytest.mark.asyncio
async def test_container_status_handles_empty_inspect_output():
    """Defensive: if inspect succeeds but returns empty stdout (rare
    but possible during very fast container state transitions),
    treat as absent rather than passing the empty string upstream."""
    from common import stack_health

    async def fake_shell(cmd, timeout=5):
        return 0, ""

    with patch.object(stack_health, "_shell", side_effect=fake_shell):
        s = await stack_health._container_status("racy")
        assert s == "absent"


# ============================================================================
# `check_containers_running` — the gate function
# ============================================================================

@pytest.mark.asyncio
async def test_check_containers_running_returns_empty_when_all_running():
    """The success path: every container in
    REQUIRED + GNB + UES is running → empty dict."""
    from common import stack_health

    async def fake_status(name):
        return "running"

    with patch.object(stack_health, "_container_status", side_effect=fake_status):
        non_running = await stack_health.check_containers_running()
        assert non_running == {}


@pytest.mark.asyncio
async def test_check_containers_running_flags_one_exited_container():
    """The SCP-crash case: 16 of 17 containers running, SCP exited →
    return value contains exactly that one entry. The orchestrator
    relies on the empty/non-empty distinction to gate scenarios."""
    from common import stack_health

    async def fake_status(name):
        return "exited" if name == "scp" else "running"

    with patch.object(stack_health, "_container_status", side_effect=fake_status):
        non_running = await stack_health.check_containers_running()
        assert non_running == {"scp": "exited"}


@pytest.mark.asyncio
async def test_check_containers_running_flags_multiple_classes_of_failure():
    """Mixed failure modes — exited core NF, absent UE — both reported.
    Each gets a status string so the operator/log can see WHY."""
    from common import stack_health

    async def fake_status(name):
        return {
            "scp": "exited",
            "e2e_ue2": "absent",
        }.get(name, "running")

    with patch.object(stack_health, "_container_status", side_effect=fake_status):
        non_running = await stack_health.check_containers_running()
        assert non_running == {"scp": "exited", "e2e_ue2": "absent"}


# ============================================================================
# `restart_exited_containers` — the recovery action
# ============================================================================

@pytest.mark.asyncio
async def test_restart_exited_containers_uses_docker_start_for_exited():
    """An 'exited' container is restartable via `docker start` — the
    container still exists in the docker engine, just stopped. This is
    the most common case after a crash during a chaos scenario."""
    from common import stack_health

    shell_calls: list[str] = []

    async def fake_shell(cmd, timeout=30):
        shell_calls.append(cmd)
        return 0, ""

    # After restart, container becomes running.
    async def fake_status(name):
        return "running"

    async def fake_sleep(_):
        return

    with patch.object(stack_health, "_shell", side_effect=fake_shell), \
         patch.object(stack_health, "_container_status", side_effect=fake_status), \
         patch.object(stack_health.asyncio, "sleep", side_effect=fake_sleep):
        result = await stack_health.restart_exited_containers({"scp": "exited"})

    assert any("docker start scp" in c for c in shell_calls), (
        f"expected `docker start scp`, got commands: {shell_calls}"
    )
    assert result == {}, "container should be running after restart"


@pytest.mark.asyncio
async def test_restart_exited_containers_does_not_attempt_to_start_absent():
    """An 'absent' container has been removed from the docker engine
    entirely. `docker start` won't help — only re-deploy via the
    appropriate compose file does. We log the absent container loudly
    and leave it for the operator to handle. Returning the absent
    container in the post-restart status prevents the pre-check from
    proceeding silently."""
    from common import stack_health

    shell_calls: list[str] = []

    async def fake_shell(cmd, timeout=30):
        shell_calls.append(cmd)
        return 0, ""

    # SCP stays absent (can't be recovered without a re-deploy);
    # every other container in the gate set is running normally —
    # this is the realistic state where one container has been
    # removed entirely while the rest of the stack is healthy.
    async def fake_status(name):
        return "absent" if name == "scp" else "running"

    async def fake_sleep(_):
        return

    with patch.object(stack_health, "_shell", side_effect=fake_shell), \
         patch.object(stack_health, "_container_status", side_effect=fake_status), \
         patch.object(stack_health.asyncio, "sleep", side_effect=fake_sleep):
        result = await stack_health.restart_exited_containers({"scp": "absent"})

    assert not any("docker start scp" in c for c in shell_calls), (
        f"should NOT have run `docker start scp` for absent container; "
        f"commands: {shell_calls}"
    )
    assert result == {"scp": "absent"}, (
        "absent container must still be reported in the post-restart status "
        "so the pre-check can refuse to proceed"
    )


@pytest.mark.asyncio
async def test_restart_exited_containers_handles_paused_via_unpause():
    """A paused container is recovered with `docker unpause`, not
    `docker start`. Edge case but worth getting right — `docker start`
    on a paused container is a no-op and would silently leave the
    container in paused state."""
    from common import stack_health

    shell_calls: list[str] = []

    async def fake_shell(cmd, timeout=10):
        shell_calls.append(cmd)
        return 0, ""

    async def fake_status(name):
        return "running"

    async def fake_sleep(_):
        return

    with patch.object(stack_health, "_shell", side_effect=fake_shell), \
         patch.object(stack_health, "_container_status", side_effect=fake_status), \
         patch.object(stack_health.asyncio, "sleep", side_effect=fake_sleep):
        result = await stack_health.restart_exited_containers({"upf": "paused"})

    assert any("docker unpause upf" in c for c in shell_calls), (
        f"expected `docker unpause upf`, got commands: {shell_calls}"
    )
    assert not any("docker start upf" in c for c in shell_calls)


@pytest.mark.asyncio
async def test_restart_exited_containers_short_circuits_on_empty_input():
    """If nothing was non-running, the helper must do no shell work
    at all — no spurious `docker start` calls, no 20-second sleep."""
    from common import stack_health

    shell_calls: list[str] = []

    async def fake_shell(cmd, timeout=30):
        shell_calls.append(cmd)
        return 0, ""

    sleep_calls: list[float] = []

    async def fake_sleep(secs):
        sleep_calls.append(secs)

    with patch.object(stack_health, "_shell", side_effect=fake_shell), \
         patch.object(stack_health.asyncio, "sleep", side_effect=fake_sleep):
        result = await stack_health.restart_exited_containers({})

    assert shell_calls == []
    assert sleep_calls == []
    assert result == {}
