"""Tests for the OUT_OF_SCOPE tool boundary (Task A of ADR
`synthesis_undetected_fault_verdict.md`).

Lives under `agentic_ops/tests/` (v1.5 namespace) because the tool
implementations live in `agentic_ops/tools.py` and the constants in
`agentic_ops/models.py`. v7's self-containment CI gate
(`agentic_ops_v7/tests/test_v7_has_no_prior_version_imports.py`)
forbids `from agentic_ops.X import Y` inside v7 — so these tests have
to live with the package they exercise.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from agentic_ops.models import (
    AgentDeps,
    OUT_OF_SCOPE_CONTAINERS,
    OUT_OF_SCOPE_INFERENCE,
)
from agentic_ops.tools import get_network_status, measure_rtt


class TestOutOfScopeContainersConstant:

    def test_constant_contains_ran_and_ues(self):
        assert "nr_gnb" in OUT_OF_SCOPE_CONTAINERS
        assert "e2e_ue1" in OUT_OF_SCOPE_CONTAINERS
        assert "e2e_ue2" in OUT_OF_SCOPE_CONTAINERS

    def test_inference_pointers_cover_every_oos_container(self):
        for c in OUT_OF_SCOPE_CONTAINERS:
            assert c in OUT_OF_SCOPE_INFERENCE
            assert len(OUT_OF_SCOPE_INFERENCE[c]) > 0

    def test_constant_is_immutable_frozenset(self):
        """Single source of truth — must be immutable so consumers can't
        accidentally mutate the global set."""
        assert isinstance(OUT_OF_SCOPE_CONTAINERS, frozenset)


class TestMeasureRttOutOfScope:

    @pytest.mark.asyncio
    async def test_oos_target_returns_oos_prefix(self):
        """The forcing-run failure mode: agent probes nr_gnb directly and
        gets a generic 'Unknown target container' that it interprets as
        episodic ambiguity. After Task A, the response carries a stable
        OUT_OF_SCOPE: prefix and the inference pointer."""
        deps = AgentDeps(repo_root=Path("."), env={})
        r = await measure_rtt(deps, "pcscf", "nr_gnb")
        assert r.startswith("OUT_OF_SCOPE:"), (
            f"Expected OUT_OF_SCOPE: prefix for nr_gnb, got: {r[:80]}"
        )
        assert "amf.gnb gauge" in r, "Must surface the inference pointer"
        assert "do not retry" in r.lower()

    @pytest.mark.asyncio
    async def test_oos_target_e2e_ue1(self):
        deps = AgentDeps(repo_root=Path("."), env={})
        r = await measure_rtt(deps, "pcscf", "e2e_ue1")
        assert r.startswith("OUT_OF_SCOPE:")
        assert "amf.ran_ue" in r or "ims_usrloc_pcscf" in r

    @pytest.mark.asyncio
    async def test_oos_source_returns_oos_prefix(self):
        """OUT_OF_SCOPE check applies to source containers too."""
        deps = AgentDeps(repo_root=Path("."), env={})
        r = await measure_rtt(deps, "e2e_ue1", "pyhss")
        assert r.startswith("OUT_OF_SCOPE:")

    @pytest.mark.asyncio
    async def test_unknown_container_still_rejects_generically(self):
        """Typos and made-up names still get the generic rejection — they
        are NOT operator-boundary cases."""
        deps = AgentDeps(repo_root=Path("."), env={})
        r = await measure_rtt(deps, "pcscf", "fake_container_name")
        assert r.startswith("Unknown target")
        assert "OUT_OF_SCOPE" not in r

    @pytest.mark.asyncio
    async def test_in_scope_target_does_not_return_oos(self):
        """In-scope containers proceed to the actual docker exec ping
        (which will fail in the test env without containers, but must
        NOT short-circuit with OUT_OF_SCOPE)."""
        deps = AgentDeps(repo_root=Path("."), env={})
        r = await measure_rtt(deps, "pcscf", "pyhss")
        assert not r.startswith("OUT_OF_SCOPE:"), (
            "In-scope container probes must not return OUT_OF_SCOPE"
        )


class TestGetNetworkStatusOutOfScope:

    @pytest.mark.asyncio
    async def test_status_json_includes_out_of_scope_block(self):
        deps = AgentDeps(repo_root=Path("."), env={})
        # Mock the docker inspect call so we don't depend on a running stack
        with patch(
            "agentic_ops.tools._container_status",
            new_callable=AsyncMock,
        ) as mock_status:
            mock_status.return_value = "absent"
            response = await get_network_status(deps)

        data = json.loads(response)
        assert "out_of_scope" in data, (
            "get_network_status JSON must surface the OUT_OF_SCOPE block "
            "so the agent never asks 'is nr_gnb missing because it crashed "
            "or because the tool doesn't track it?'"
        )
        assert set(data["out_of_scope"]) == {"nr_gnb", "e2e_ue1", "e2e_ue2"}
        for name, hint in data["out_of_scope"].items():
            assert "outside NOC" in hint

    @pytest.mark.asyncio
    async def test_oos_block_independent_of_phase(self):
        """OUT_OF_SCOPE block must appear regardless of stack health phase."""
        deps = AgentDeps(repo_root=Path("."), env={})
        with patch(
            "agentic_ops.tools._container_status",
            new_callable=AsyncMock,
        ) as mock_status:
            mock_status.return_value = "running"
            response = await get_network_status(deps)
        data = json.loads(response)
        assert "out_of_scope" in data
        assert data["out_of_scope"]  # non-empty
