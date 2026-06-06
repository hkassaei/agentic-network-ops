"""
Unit tests for the four CDR-0001 novel failure scenarios.

These tests exercise the new fault primitives and their verifiers with
the shell layer mocked — they validate command shape, parameter handling,
heal-command construction, and the precheck/fail-fast paths. They do NOT
require Docker, the stack, or network access.

Integration validation (running scenarios end-to-end against the live
stack) is a separate exercise — see CDR-0001 acceptance criteria.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


# =========================================================================
# Scenario A — Asymmetric Path Loss (peer_ip param on inject_packet_loss)
# =========================================================================

class TestAsymmetricPacketLoss:
    """Verify the `peer_ip` branch in inject_packet_loss builds the
    expected `tc prio` + `tc filter` + `netem loss` command chain."""

    @pytest.mark.asyncio
    async def test_peer_ip_none_uses_symmetric_path(self):
        """Without peer_ip, behavior must match the legacy symmetric tc qdisc."""
        from agentic_chaos.tools.network_tools import inject_packet_loss

        with patch("agentic_chaos.tools.network_tools.shell",
                   new_callable=AsyncMock) as mock_shell, \
             patch("agentic_chaos.tools.network_tools.docker_get_pid",
                   new_callable=AsyncMock) as mock_pid:
            mock_pid.return_value = 12345
            mock_shell.return_value = (0, "")

            result = await inject_packet_loss("amf", loss_pct=30)

        assert result["success"] is True
        assert "tc qdisc add dev eth0 root netem loss 30" in result["mechanism"]
        # No filter / no prio in the symmetric path
        assert "tc filter" not in result["mechanism"]
        assert "prio" not in result["mechanism"]
        assert result["heal_cmd"].endswith("tc qdisc del dev eth0 root")

    @pytest.mark.asyncio
    async def test_peer_ip_set_builds_filtered_chain(self):
        """With peer_ip, mechanism must install prio root + child netem +
        a u32 filter matching `dst <peer_ip>/32 flowid 1:1`."""
        from agentic_chaos.tools.network_tools import inject_packet_loss

        with patch("agentic_chaos.tools.network_tools.shell",
                   new_callable=AsyncMock) as mock_shell, \
             patch("agentic_chaos.tools.network_tools.docker_get_pid",
                   new_callable=AsyncMock) as mock_pid:
            mock_pid.return_value = 12345
            mock_shell.return_value = (0, "")

            result = await inject_packet_loss(
                "amf", loss_pct=60, peer_ip="172.22.0.23"
            )

        assert result["success"] is True
        m = result["mechanism"]
        # All three pieces of the chain must be present
        assert "tc qdisc add dev eth0 root handle 1: prio" in m
        assert "tc qdisc add dev eth0 parent 1:1 handle 10: netem loss 60" in m
        assert "tc filter add dev eth0 parent 1:0" in m
        assert "u32 match ip dst 172.22.0.23/32 flowid 1:1" in m
        # Heal still uses the single `tc qdisc del root` that tears the whole
        # prio tree down in one shot — same heal as symmetric.
        assert result["heal_cmd"].endswith("tc qdisc del dev eth0 root")

    @pytest.mark.asyncio
    async def test_peer_ip_validates_ip_format(self):
        """Invalid IPs must raise before any shell call."""
        from agentic_chaos.tools.network_tools import inject_packet_loss

        with patch("agentic_chaos.tools.network_tools.docker_get_pid",
                   new_callable=AsyncMock) as mock_pid:
            mock_pid.return_value = 12345
            with pytest.raises(ValueError, match="Invalid IP"):
                await inject_packet_loss("amf", loss_pct=60, peer_ip="not-an-ip")


# =========================================================================
# Scenario B — Selective Subscriber Corruption (corrupt_subscriber_credential)
# =========================================================================

class TestCorruptSubscriberCredential:

    @pytest.mark.asyncio
    async def test_invalid_imsi_raises(self):
        from agentic_chaos.tools.application_tools import corrupt_subscriber_credential
        with pytest.raises(ValueError, match="Invalid IMSI"):
            await corrupt_subscriber_credential("abc123")

    @pytest.mark.asyncio
    async def test_lookup_returns_no_row_fails_cleanly(self):
        """No matching IMSI → success=False, no UPDATE issued."""
        from agentic_chaos.tools.application_tools import corrupt_subscriber_credential
        with patch("agentic_chaos.tools.application_tools.shell",
                   new_callable=AsyncMock) as mock_shell:
            mock_shell.return_value = (0, "")  # empty lookup result

            result = await corrupt_subscriber_credential("001011234567891")

        assert result["success"] is False
        assert "No auc row" in result["detail"]
        # Only the lookup call should have happened — no UPDATE
        assert mock_shell.call_count == 1

    @pytest.mark.asyncio
    async def test_lookup_returns_invalid_hex_fails_cleanly(self):
        from agentic_chaos.tools.application_tools import corrupt_subscriber_credential
        with patch("agentic_chaos.tools.application_tools.shell",
                   new_callable=AsyncMock) as mock_shell:
            mock_shell.return_value = (0, "5\tnot_hex_data")

            result = await corrupt_subscriber_credential("001011234567891")

        assert result["success"] is False
        assert "32-char hex" in result["detail"]
        assert mock_shell.call_count == 1

    @pytest.mark.asyncio
    async def test_happy_path_corrupts_first_byte(self):
        """Successful corruption: K's first byte flipped (XOR 0x80), rest
        unchanged. Heal SQL restores the original K. With ue_container set,
        heal chains a docker restart."""
        from agentic_chaos.tools.application_tools import corrupt_subscriber_credential

        # Original K starts with 0x46 — XOR 0x80 → 0xC6
        original_ki = "465B5CE8B199B49FAA5F0A2EE238A6BC"

        with patch("agentic_chaos.tools.application_tools.shell",
                   new_callable=AsyncMock) as mock_shell:
            # First call (lookup) returns auc_id + ki; second (UPDATE) returns OK
            mock_shell.side_effect = [
                (0, f"5\t{original_ki}"),
                (0, ""),
            ]

            result = await corrupt_subscriber_credential(
                "001011234567891", ue_container="e2e_ue1"
            )

        assert result["success"] is True
        assert result["auc_id"] == "5"
        assert result["original_ki"] == original_ki
        # First byte 0x46 ^ 0x80 = 0xC6 ; rest unchanged
        assert result["corrupted_ki"] == "C6" + original_ki[2:]
        # UPDATE must reference the corrupted K and the auc_id
        assert "UPDATE auc SET ki =" in result["mechanism"]
        assert result["corrupted_ki"] in result["mechanism"]
        assert "WHERE auc_id = 5" in result["mechanism"]
        # CDR-0001 Task 1.1: mechanism MUST also restart the UE so the
        # corrupted K bites within the observation window — without this,
        # UE1 stays attached with cached NAS context and the fault is silent.
        assert "docker restart e2e_ue1" in result["mechanism"]
        # Heal must restore original AND restart the UE
        assert original_ki in result["heal_cmd"]
        assert "docker restart e2e_ue1" in result["heal_cmd"]
        # Still two shell calls: lookup + (UPDATE chained with restart in a
        # single shell.run() — the && chain is one invocation)
        assert mock_shell.call_count == 2

    @pytest.mark.asyncio
    async def test_invalid_ue_container_raises_before_any_sql(self):
        """ValueError must surface BEFORE any SQL is issued (so the DB is
        never left in a partially-corrupted state with no registered heal).
        """
        from agentic_chaos.tools.application_tools import corrupt_subscriber_credential

        with patch("agentic_chaos.tools.application_tools.shell",
                   new_callable=AsyncMock) as mock_shell:
            with pytest.raises(ValueError, match="Unsupported ue_container"):
                await corrupt_subscriber_credential(
                    "001011234567891", ue_container="random_container"
                )
            # No SQL must have been issued
            assert mock_shell.call_count == 0

    @pytest.mark.asyncio
    async def test_no_ue_container_omits_restart_from_mechanism(self):
        """When ue_container=None, inject only mutates the DB — neither
        mechanism nor heal restarts a UE. Documented as a foot-gun in the
        scenario description (fault will be observably silent)."""
        from agentic_chaos.tools.application_tools import corrupt_subscriber_credential

        original_ki = "465B5CE8B199B49FAA5F0A2EE238A6BC"
        with patch("agentic_chaos.tools.application_tools.shell",
                   new_callable=AsyncMock) as mock_shell:
            mock_shell.side_effect = [(0, f"5\t{original_ki}"), (0, "")]
            result = await corrupt_subscriber_credential(
                "001011234567891", ue_container=None
            )

        assert result["success"] is True
        assert "UPDATE auc SET ki =" in result["mechanism"]
        assert "docker restart" not in result["mechanism"]
        assert "docker restart" not in result["heal_cmd"]


class TestVerifySubscriberCredentialCorrupted:

    @pytest.mark.asyncio
    async def test_match_returns_verified(self):
        from agentic_chaos.tools.verification_tools import (
            verify_subscriber_credential_corrupted,
        )
        expected = "C65B5CE8B199B49FAA5F0A2EE238A6BC"
        with patch("agentic_chaos.tools.verification_tools.shell",
                   new_callable=AsyncMock) as mock_shell:
            mock_shell.return_value = (0, expected)

            result = await verify_subscriber_credential_corrupted(
                "001011234567891", expected
            )

        assert result["verified"] is True
        assert result["actual_ki"] == expected

    @pytest.mark.asyncio
    async def test_mismatch_returns_unverified(self):
        from agentic_chaos.tools.verification_tools import (
            verify_subscriber_credential_corrupted,
        )
        with patch("agentic_chaos.tools.verification_tools.shell",
                   new_callable=AsyncMock) as mock_shell:
            mock_shell.return_value = (0, "DIFFERENT_VALUE_HERE_NOT_EXPECTED")

            result = await verify_subscriber_credential_corrupted(
                "001011234567891", "EXPECTED_VALUE_HERE"
            )

        assert result["verified"] is False

    @pytest.mark.asyncio
    async def test_case_insensitive_compare(self):
        """K values are hex — comparison should not be case-sensitive."""
        from agentic_chaos.tools.verification_tools import (
            verify_subscriber_credential_corrupted,
        )
        with patch("agentic_chaos.tools.verification_tools.shell",
                   new_callable=AsyncMock) as mock_shell:
            mock_shell.return_value = (0, "abcdef0123456789abcdef0123456789")

            result = await verify_subscriber_credential_corrupted(
                "001011234567891", "ABCDEF0123456789ABCDEF0123456789"
            )

        assert result["verified"] is True


# =========================================================================
# Scenario C — Clock Skew via libfaketime
# =========================================================================

class TestInjectClockSkew:

    @pytest.mark.asyncio
    async def test_precheck_missing_libfaketime_fails_fast(self):
        """Container without libfaketime → success=False, no offset write."""
        from agentic_chaos.tools.time_tools import inject_clock_skew

        with patch("agentic_chaos.tools.time_tools.shell",
                   new_callable=AsyncMock) as mock_shell:
            mock_shell.return_value = (0, "MISSING")

            result = await inject_clock_skew("pyhss", skew_seconds=2820)

        assert result["success"] is False
        assert "libfaketime" in result["detail"]
        assert result["heal_cmd"] == "true"  # no-op heal
        # Only one shell call — the precheck. No offset write attempted.
        assert mock_shell.call_count == 1

    @pytest.mark.asyncio
    async def test_happy_path_writes_offset_file(self):
        """Container prepped for libfaketime → offset written to /etc/faketimerc."""
        from agentic_chaos.tools.time_tools import inject_clock_skew

        with patch("agentic_chaos.tools.time_tools.shell",
                   new_callable=AsyncMock) as mock_shell:
            mock_shell.side_effect = [
                (0, "READY"),  # precheck
                (0, ""),       # offset write
            ]

            result = await inject_clock_skew("pyhss", skew_seconds=2820)

        assert result["success"] is True
        assert "/etc/faketimerc" in result["mechanism"]
        assert "+2820s" in result["mechanism"]
        # Heal truncates the file
        assert "/etc/faketimerc" in result["heal_cmd"]
        assert ": >" in result["heal_cmd"]
        assert mock_shell.call_count == 2

    @pytest.mark.asyncio
    async def test_negative_skew_uses_minus_offset(self):
        from agentic_chaos.tools.time_tools import inject_clock_skew
        with patch("agentic_chaos.tools.time_tools.shell",
                   new_callable=AsyncMock) as mock_shell:
            mock_shell.side_effect = [(0, "READY"), (0, "")]
            result = await inject_clock_skew("pyhss", skew_seconds=-300)
        assert result["success"] is True
        # libfaketime sign convention: "-300s" for rewind
        assert "-300s" in result["mechanism"]


class TestVerifyClockSkew:

    @pytest.mark.asyncio
    async def test_clock_ahead_verifies(self):
        from agentic_chaos.tools.time_tools import verify_clock_skew

        with patch("agentic_chaos.tools.time_tools.shell",
                   new_callable=AsyncMock) as mock_shell:
            # Container clock 2900s ahead of host
            mock_shell.return_value = (0, "1812350000\n1812347100")

            result = await verify_clock_skew("pyhss", min_skew_seconds=2700)

        assert result["verified"] is True
        assert result["observed_skew_seconds"] >= 2700

    @pytest.mark.asyncio
    async def test_clock_in_sync_does_not_verify(self):
        from agentic_chaos.tools.time_tools import verify_clock_skew
        with patch("agentic_chaos.tools.time_tools.shell",
                   new_callable=AsyncMock) as mock_shell:
            # Container clock equals host
            mock_shell.return_value = (0, "1812347100\n1812347100")

            result = await verify_clock_skew("pyhss", min_skew_seconds=2700)

        assert result["verified"] is False
        assert abs(result["observed_skew_seconds"]) < 5


# =========================================================================
# Scenario D — PMTU Black-Hole
# =========================================================================

class TestInjectPmtuBlackhole:

    @pytest.mark.asyncio
    async def test_validates_mtu_range(self):
        from agentic_chaos.tools.datapath_tools import inject_pmtu_blackhole
        with pytest.raises(ValueError, match="mtu must be"):
            await inject_pmtu_blackhole("upf", mtu=100)
        with pytest.raises(ValueError, match="mtu must be"):
            await inject_pmtu_blackhole("upf", mtu=20000)

    @pytest.mark.asyncio
    async def test_validates_iface(self):
        from agentic_chaos.tools.datapath_tools import inject_pmtu_blackhole
        with pytest.raises(ValueError, match="Invalid iface"):
            await inject_pmtu_blackhole("upf", iface="eth0; rm -rf /")

    @pytest.mark.asyncio
    async def test_unreadable_mtu_fails_fast(self):
        """If `ip link show` fails or has no mtu in output → success=False."""
        from agentic_chaos.tools.datapath_tools import inject_pmtu_blackhole

        with patch("agentic_chaos.tools.datapath_tools.shell",
                   new_callable=AsyncMock) as mock_shell, \
             patch("agentic_chaos.tools.datapath_tools.docker_get_pid",
                   new_callable=AsyncMock) as mock_pid:
            mock_pid.return_value = 12345
            mock_shell.return_value = (1, "no such device")

            result = await inject_pmtu_blackhole("upf", mtu=1280)

        assert result["success"] is False
        assert "Could not read original MTU" in result["detail"]
        assert result["heal_cmd"] == "true"

    @pytest.mark.asyncio
    async def test_happy_path_builds_compound_mechanism(self):
        """Successful inject: mechanism contains MTU change + ICMP-v4 drop +
        ICMP-v6 drop. Heal restores original MTU and removes both rules."""
        from agentic_chaos.tools.datapath_tools import inject_pmtu_blackhole

        with patch("agentic_chaos.tools.datapath_tools.shell",
                   new_callable=AsyncMock) as mock_shell, \
             patch("agentic_chaos.tools.datapath_tools.docker_get_pid",
                   new_callable=AsyncMock) as mock_pid:
            mock_pid.return_value = 12345
            mock_shell.side_effect = [
                # _current_mtu() returns 1500
                (0, "2: eth0: <BROADCAST,MULTICAST,UP> mtu 1500 qdisc noqueue"),
                # Compound inject
                (0, ""),
            ]

            result = await inject_pmtu_blackhole("upf", mtu=1280)

        assert result["success"] is True
        assert result["original_mtu"] == 1500
        m = result["mechanism"]
        # MTU lowered
        assert "ip link set dev eth0 mtu 1280" in m
        # v4 ICMP frag-needed drop
        assert "iptables -A OUTPUT -p icmp --icmp-type fragmentation-needed -j DROP" in m
        # v6 packet-too-big drop (best-effort)
        assert "ip6tables -A OUTPUT -p icmpv6 --icmpv6-type packet-too-big -j DROP" in m

        # Heal restores original MTU AND removes both rules
        h = result["heal_cmd"]
        assert "ip link set dev eth0 mtu 1500" in h
        assert "iptables -D OUTPUT" in h
        assert "ip6tables -D OUTPUT" in h
        # Heal uses `|| true` so it's idempotent even when rules aren't present
        assert "|| true" in h


class TestVerifyPmtuBlackhole:

    @pytest.mark.asyncio
    async def test_both_components_present_verifies(self):
        from agentic_chaos.tools.datapath_tools import verify_pmtu_blackhole

        with patch("agentic_chaos.tools.datapath_tools.shell",
                   new_callable=AsyncMock) as mock_shell, \
             patch("agentic_chaos.tools.datapath_tools.docker_get_pid",
                   new_callable=AsyncMock) as mock_pid:
            mock_pid.return_value = 12345
            mock_shell.side_effect = [
                # _current_mtu() → 1280 (matches expected)
                (0, "2: eth0: <BROADCAST,MULTICAST,UP> mtu 1280 qdisc noqueue"),
                # iptables -S OUTPUT shows the DROP rule
                (0, "-A OUTPUT -p icmp -m icmp --icmp-type fragmentation-needed -j DROP"),
            ]

            result = await verify_pmtu_blackhole("upf", expected_mtu=1280)

        assert result["verified"] is True
        assert result["current_mtu"] == 1280
        assert result["ipt_rule_present"] is True

    @pytest.mark.asyncio
    async def test_mtu_present_but_no_iptables_rule_does_not_verify(self):
        """Partial inject — MTU lowered but iptables rule absent: not verified."""
        from agentic_chaos.tools.datapath_tools import verify_pmtu_blackhole

        with patch("agentic_chaos.tools.datapath_tools.shell",
                   new_callable=AsyncMock) as mock_shell, \
             patch("agentic_chaos.tools.datapath_tools.docker_get_pid",
                   new_callable=AsyncMock) as mock_pid:
            mock_pid.return_value = 12345
            mock_shell.side_effect = [
                (0, "2: eth0: <BROADCAST,MULTICAST,UP> mtu 1280 qdisc noqueue"),
                (0, "-A OUTPUT -j ACCEPT"),  # no frag-needed drop rule
            ]
            result = await verify_pmtu_blackhole("upf", expected_mtu=1280)

        assert result["verified"] is False
        assert result["current_mtu"] == 1280
        assert result["ipt_rule_present"] is False


# =========================================================================
# FaultInjector dispatch — wiring sanity for the three new fault types
# =========================================================================

class TestFaultInjectorDispatch:
    """Confirm the dispatch in fault_injector.py routes new fault types to
    the right tool functions."""

    @pytest.mark.asyncio
    async def test_dispatch_routes_subscriber_credential_corruption(self):
        from agentic_chaos.agents.fault_injector import FaultInjector
        from agentic_chaos.fault_registry import FaultRegistry
        injector = FaultInjector(registry=FaultRegistry())

        with patch(
            "agentic_chaos.agents.fault_injector.corrupt_subscriber_credential",
            new_callable=AsyncMock,
        ) as mock_fn:
            mock_fn.return_value = {"success": True, "mechanism": "x", "heal_cmd": "y", "detail": "ok"}
            await injector._dispatch_inject(
                "subscriber_credential_corruption",
                "pyhss",
                {"imsi": "001011234567891", "ue_container": "e2e_ue1"},
            )
        mock_fn.assert_called_once_with(
            imsi="001011234567891", ue_container="e2e_ue1"
        )

    @pytest.mark.asyncio
    async def test_dispatch_routes_clock_skew(self):
        from agentic_chaos.agents.fault_injector import FaultInjector
        from agentic_chaos.fault_registry import FaultRegistry
        injector = FaultInjector(registry=FaultRegistry())

        with patch(
            "agentic_chaos.tools.time_tools.inject_clock_skew",
            new_callable=AsyncMock,
        ) as mock_fn:
            mock_fn.return_value = {"success": True, "mechanism": "x", "heal_cmd": "y", "detail": "ok"}
            await injector._dispatch_inject(
                "clock_skew", "pyhss", {"skew_seconds": 2820}
            )
        mock_fn.assert_called_once_with("pyhss", skew_seconds=2820)

    @pytest.mark.asyncio
    async def test_dispatch_routes_pmtu_blackhole(self):
        from agentic_chaos.agents.fault_injector import FaultInjector
        from agentic_chaos.fault_registry import FaultRegistry
        injector = FaultInjector(registry=FaultRegistry())

        with patch(
            "agentic_chaos.tools.datapath_tools.inject_pmtu_blackhole",
            new_callable=AsyncMock,
        ) as mock_fn:
            mock_fn.return_value = {"success": True, "mechanism": "x", "heal_cmd": "y", "detail": "ok"}
            await injector._dispatch_inject(
                "pmtu_blackhole", "upf", {"mtu": 1280, "iface": "eth0"}
            )
        mock_fn.assert_called_once_with("upf", mtu=1280, iface="eth0")

    @pytest.mark.asyncio
    async def test_dispatch_passes_peer_ip_to_network_loss(self):
        from agentic_chaos.agents.fault_injector import FaultInjector
        from agentic_chaos.fault_registry import FaultRegistry
        injector = FaultInjector(registry=FaultRegistry())

        with patch(
            "agentic_chaos.agents.fault_injector.inject_packet_loss",
            new_callable=AsyncMock,
        ) as mock_fn:
            mock_fn.return_value = {"success": True, "mechanism": "x", "heal_cmd": "y", "detail": "ok"}
            await injector._dispatch_inject(
                "network_loss",
                "amf",
                {"loss_pct": 60, "peer_ip": "172.22.0.23"},
            )
        mock_fn.assert_called_once_with("amf", 60, peer_ip="172.22.0.23")

    @pytest.mark.asyncio
    async def test_dispatch_network_loss_backward_compatible_without_peer_ip(self):
        """Existing scenarios without peer_ip must still work — peer_ip defaults to None."""
        from agentic_chaos.agents.fault_injector import FaultInjector
        from agentic_chaos.fault_registry import FaultRegistry
        injector = FaultInjector(registry=FaultRegistry())

        with patch(
            "agentic_chaos.agents.fault_injector.inject_packet_loss",
            new_callable=AsyncMock,
        ) as mock_fn:
            mock_fn.return_value = {"success": True, "mechanism": "x", "heal_cmd": "y", "detail": "ok"}
            await injector._dispatch_inject(
                "network_loss", "upf", {"loss_pct": 30}
            )
        mock_fn.assert_called_once_with("upf", 30, peer_ip=None)


# =========================================================================
# Scenario library — sanity that the 4 new scenarios are well-formed
# =========================================================================

class TestNewScenariosWellFormed:
    """Spot-check the 4 new scenarios in the library have the params their
    fault primitives require."""

    def test_asymmetric_path_loss_has_peer_ip(self):
        from agentic_chaos.scenarios.library import get_scenario
        s = get_scenario("Asymmetric Path Loss (AMF→gNB)")
        spec = s.faults[0]
        assert spec.fault_type == "network_loss"
        assert spec.target == "amf"
        assert "peer_ip" in spec.params
        assert "loss_pct" in spec.params

    def test_selective_subscriber_corruption_has_imsi_and_ue(self):
        from agentic_chaos.scenarios.library import get_scenario
        s = get_scenario("Selective Subscriber Corruption (UE1)")
        spec = s.faults[0]
        assert spec.fault_type == "subscriber_credential_corruption"
        assert spec.target == "pyhss"
        assert spec.params.get("imsi") == "001011234567891"
        assert spec.params.get("ue_container") == "e2e_ue1"

    def test_pmtu_blackhole_has_mtu(self):
        from agentic_chaos.scenarios.library import get_scenario
        s = get_scenario("PMTU Black-Hole on N3")
        spec = s.faults[0]
        assert spec.fault_type == "pmtu_blackhole"
        assert spec.target == "upf"
        assert "mtu" in spec.params

    def test_clock_skew_has_skew_seconds(self):
        from agentic_chaos.scenarios.library import get_scenario
        s = get_scenario("PyHSS Clock Skew (Observability)")
        spec = s.faults[0]
        assert spec.fault_type == "clock_skew"
        assert spec.target == "pyhss"
        assert spec.params.get("skew_seconds") == 2820


# =========================================================================
# LIFECYCLE TESTS — full inject → verify → heal → post-heal verify
# =========================================================================
# These tests walk the complete state machine for each scenario with the
# shell layer mocked. They confirm that:
#   1. inject_X returns a heal_cmd
#   2. verify_X confirms the fault is present (using mocked "during fault"
#      shell output)
#   3. running the heal_cmd succeeds
#   4. verify_X confirms the fault is GONE (using mocked "post-heal" shell
#      output)
#
# No Docker, no live stack, no LLM. Pure framework-logic validation.
# Integration smoke-testing against the live stack is a separate exercise
# that the operator drives manually.

class TestLifecycleAsymmetricPathLoss:
    """Full inject → verify → heal → post-heal walk for asymmetric loss."""

    @pytest.mark.asyncio
    async def test_full_lifecycle(self):
        from agentic_chaos.tools.network_tools import inject_packet_loss
        from agentic_chaos.tools.verification_tools import verify_tc_active

        # Each call returns (rc, output). Sequence matches the actual call
        # order across the four lifecycle phases below.
        shell_calls = [
            (0, ""),  # phase 1 — inject: tc prio+filter+netem chain
            (0, "qdisc prio 1: root refcnt 2 bands 3 ...\n"
                "qdisc netem 10: parent 1:1 ... loss 60%"),  # phase 2 — verify during fault
            (0, ""),  # phase 3 — heal: tc qdisc del root
            (0, "qdisc noqueue 0: root refcnt 2"),  # phase 4 — verify post-heal (no netem)
        ]

        with patch("agentic_chaos.tools.network_tools.shell",
                   new_callable=AsyncMock) as mock_net_shell, \
             patch("agentic_chaos.tools.network_tools.docker_get_pid",
                   new_callable=AsyncMock) as mock_net_pid, \
             patch("agentic_chaos.tools.verification_tools.shell",
                   new_callable=AsyncMock) as mock_v_shell, \
             patch("agentic_chaos.tools.verification_tools.docker_get_pid",
                   new_callable=AsyncMock) as mock_v_pid:
            mock_net_pid.return_value = 12345
            mock_v_pid.return_value = 12345
            # Distribute the responses by which module makes the call
            mock_net_shell.side_effect = [shell_calls[0]]
            mock_v_shell.side_effect = [shell_calls[1], shell_calls[3]]

            # PHASE 1 — inject
            ir = await inject_packet_loss(
                "amf", loss_pct=60, peer_ip="172.22.0.23"
            )
            assert ir["success"] is True
            heal_cmd = ir["heal_cmd"]
            assert "tc qdisc del dev eth0 root" in heal_cmd

            # PHASE 2 — verify during fault (netem present)
            v_during = await verify_tc_active("amf")
            assert v_during["active"] is True, (
                "verifier should see the active qdisc during the fault"
            )
            assert v_during["qdisc_type"] == "netem"

            # PHASE 3 — heal (use a fresh mock to track the heal call's args)
            heal_mock = AsyncMock(return_value=shell_calls[2])
            with patch("agentic_chaos.tools._common.shell", heal_mock):
                from agentic_chaos.tools._common import shell as _shell
                rc, out = await _shell(heal_cmd, timeout=15)
            assert rc == 0
            heal_mock.assert_called_once()
            assert heal_cmd in heal_mock.call_args.args[0]

            # PHASE 4 — verify post-heal (no netem, only default qdisc)
            v_after = await verify_tc_active("amf")
            assert v_after["active"] is False, (
                "verifier MUST NOT see the qdisc after heal"
            )
            assert v_after["qdisc_type"] is None


class TestLifecycleSelectiveSubscriberCorruption:
    """Full inject → verify → heal → post-heal walk for K corruption.

    The mock shell sequence covers:
      1. inject SELECT (returns auc_id + original K)
      2. inject UPDATE (applies corrupted K)
      3. verify during fault (re-SELECT returns corrupted K)
      4. heal (UPDATE + docker restart chained — single shell call)
      5. post-heal verify (re-SELECT returns original K)
    """

    @pytest.mark.asyncio
    async def test_full_lifecycle(self):
        from agentic_chaos.tools.application_tools import (
            corrupt_subscriber_credential,
        )
        from agentic_chaos.tools.verification_tools import (
            verify_subscriber_credential_corrupted,
        )

        IMSI = "001011234567891"
        ORIGINAL_KI = "465B5CE8B199B49FAA5F0A2EE238A6BC"
        CORRUPTED_KI = "C6" + ORIGINAL_KI[2:]  # XOR 0x80 on first byte

        with patch("agentic_chaos.tools.application_tools.shell",
                   new_callable=AsyncMock) as mock_app_shell, \
             patch("agentic_chaos.tools.verification_tools.shell",
                   new_callable=AsyncMock) as mock_v_shell:

            # application_tools.shell calls: SELECT (lookup) + UPDATE (inject)
            mock_app_shell.side_effect = [
                (0, f"5\t{ORIGINAL_KI}"),  # SELECT
                (0, ""),                    # UPDATE
            ]
            # verification_tools.shell calls: verify-during-fault + post-heal verify
            mock_v_shell.side_effect = [
                (0, CORRUPTED_KI),  # K is now corrupted
                (0, ORIGINAL_KI),   # K restored after heal
            ]

            # PHASE 1 — inject
            ir = await corrupt_subscriber_credential(
                imsi=IMSI, ue_container="e2e_ue1"
            )
            assert ir["success"] is True
            assert ir["original_ki"].upper() == ORIGINAL_KI.upper()
            assert ir["corrupted_ki"].upper() == CORRUPTED_KI.upper()
            heal_cmd = ir["heal_cmd"]
            assert ORIGINAL_KI in heal_cmd
            assert "docker restart e2e_ue1" in heal_cmd

            # PHASE 2 — verify during fault: K matches corrupted value
            v_during = await verify_subscriber_credential_corrupted(
                IMSI, ir["corrupted_ki"]
            )
            assert v_during["verified"] is True
            assert v_during["actual_ki"].upper() == CORRUPTED_KI.upper()

            # PHASE 3 — heal (separate shell mock to capture invocation)
            heal_mock = AsyncMock(return_value=(0, "Query OK, 1 row affected"))
            with patch("agentic_chaos.tools._common.shell", heal_mock):
                from agentic_chaos.tools._common import shell as _shell
                rc, out = await _shell(heal_cmd, timeout=60)
            assert rc == 0
            heal_mock.assert_called_once()
            # Heal command must include both the restore SQL AND the UE restart
            assert ORIGINAL_KI in heal_mock.call_args.args[0]
            assert "docker restart e2e_ue1" in heal_mock.call_args.args[0]

            # PHASE 4 — post-heal verify: re-checking against the CORRUPTED
            # value MUST return verified=False (i.e. K is no longer corrupted)
            v_after = await verify_subscriber_credential_corrupted(
                IMSI, ir["corrupted_ki"]
            )
            assert v_after["verified"] is False, (
                "After heal, K must no longer match the corrupted value"
            )
            assert v_after["actual_ki"].upper() == ORIGINAL_KI.upper()


class TestLifecyclePmtuBlackhole:
    """Full inject → verify → heal → post-heal walk for the PMTU compound."""

    @pytest.mark.asyncio
    async def test_full_lifecycle(self):
        from agentic_chaos.tools.datapath_tools import (
            inject_pmtu_blackhole,
            verify_pmtu_blackhole,
        )

        ORIGINAL_MTU = 1500
        NEW_MTU = 1280

        with patch("agentic_chaos.tools.datapath_tools.shell",
                   new_callable=AsyncMock) as mock_shell, \
             patch("agentic_chaos.tools.datapath_tools.docker_get_pid",
                   new_callable=AsyncMock) as mock_pid:
            mock_pid.return_value = 12345

            # Full call sequence on datapath_tools.shell across the lifecycle:
            #   inject:
            #     1) ip -o link show dev eth0 → reports MTU 1500
            #     2) compound inject (mtu + iptables + ip6tables) → ok
            #   verify (during fault):
            #     3) ip -o link show dev eth0 → reports MTU 1280
            #     4) iptables -S OUTPUT → shows the frag-needed DROP rule
            #   heal (run via _common.shell — see below, NOT on this mock)
            #   verify (post-heal):
            #     5) ip -o link show dev eth0 → reports MTU 1500 (restored)
            #     6) iptables -S OUTPUT → no frag-needed DROP rule
            mock_shell.side_effect = [
                (0, f"2: eth0: <BROADCAST,MULTICAST,UP> mtu {ORIGINAL_MTU} qdisc noqueue"),
                (0, ""),
                (0, f"2: eth0: <BROADCAST,MULTICAST,UP> mtu {NEW_MTU} qdisc noqueue"),
                (0, "-A OUTPUT -p icmp -m icmp --icmp-type fragmentation-needed -j DROP"),
                (0, f"2: eth0: <BROADCAST,MULTICAST,UP> mtu {ORIGINAL_MTU} qdisc noqueue"),
                (0, "-A OUTPUT -j ACCEPT"),
            ]

            # PHASE 1 — inject
            ir = await inject_pmtu_blackhole("upf", mtu=NEW_MTU, iface="eth0")
            assert ir["success"] is True
            assert ir["original_mtu"] == ORIGINAL_MTU
            heal_cmd = ir["heal_cmd"]
            assert f"ip link set dev eth0 mtu {ORIGINAL_MTU}" in heal_cmd
            assert "iptables -D OUTPUT" in heal_cmd
            assert "ip6tables -D OUTPUT" in heal_cmd

            # PHASE 2 — verify during fault: MTU lowered + rule present
            v_during = await verify_pmtu_blackhole(
                "upf", iface="eth0", expected_mtu=NEW_MTU
            )
            assert v_during["verified"] is True
            assert v_during["current_mtu"] == NEW_MTU
            assert v_during["ipt_rule_present"] is True

            # PHASE 3 — heal (separate shell mock to capture invocation)
            heal_mock = AsyncMock(return_value=(0, ""))
            with patch("agentic_chaos.tools._common.shell", heal_mock):
                from agentic_chaos.tools._common import shell as _shell
                rc, out = await _shell(heal_cmd, timeout=30)
            assert rc == 0
            heal_mock.assert_called_once()

            # PHASE 4 — verify post-heal: MTU restored, rule gone
            v_after = await verify_pmtu_blackhole(
                "upf", iface="eth0", expected_mtu=NEW_MTU
            )
            # `verified` here means "fault is STILL present" — we want False
            assert v_after["verified"] is False
            assert v_after["current_mtu"] == ORIGINAL_MTU
            assert v_after["ipt_rule_present"] is False


class TestLifecyclePyhssClockSkew:
    """Full inject → verify → heal → post-heal walk for clock skew.

    Assumes the PyHSS container IS prepped for libfaketime (precheck returns
    READY). The unprepped-container path is covered by a separate test in
    TestInjectClockSkew above.
    """

    @pytest.mark.asyncio
    async def test_full_lifecycle(self):
        from agentic_chaos.tools.time_tools import (
            inject_clock_skew,
            verify_clock_skew,
        )

        SKEW_S = 2820  # +47 min

        with patch("agentic_chaos.tools.time_tools.shell",
                   new_callable=AsyncMock) as mock_shell:
            # Lifecycle call sequence on time_tools.shell:
            #   inject:
            #     1) precheck (libfaketime + writable faketimerc) → READY
            #     2) write `+2820s` to /etc/faketimerc → ok
            #   verify (during fault):
            #     3) docker exec date + host date → container 2820s ahead
            #   heal (run via _common.shell — separate mock below)
            #   verify (post-heal):
            #     4) docker exec date + host date → in sync
            mock_shell.side_effect = [
                (0, "READY"),
                (0, ""),
                # Two epoch seconds, container first, host second
                (0, "1812350000\n1812347180"),  # delta ≈ +2820s
                (0, "1812350200\n1812350198"),  # delta ≈ 0
            ]

            # PHASE 1 — inject
            ir = await inject_clock_skew("pyhss", skew_seconds=SKEW_S)
            assert ir["success"] is True
            assert "+2820s" in ir["mechanism"]
            heal_cmd = ir["heal_cmd"]
            assert "/etc/faketimerc" in heal_cmd

            # PHASE 2 — verify during fault: clock ≥ SKEW - 60s ahead
            v_during = await verify_clock_skew(
                "pyhss", min_skew_seconds=SKEW_S - 60
            )
            assert v_during["verified"] is True
            assert v_during["observed_skew_seconds"] >= SKEW_S - 60

            # PHASE 3 — heal
            heal_mock = AsyncMock(return_value=(0, ""))
            with patch("agentic_chaos.tools._common.shell", heal_mock):
                from agentic_chaos.tools._common import shell as _shell
                rc, out = await _shell(heal_cmd, timeout=10)
            assert rc == 0
            heal_mock.assert_called_once()

            # PHASE 4 — verify post-heal: clock is back in sync.
            # We pass the same min_skew threshold; `verified=False` means
            # the clock is NOT skewed anymore — the post-heal pass condition.
            v_after = await verify_clock_skew(
                "pyhss", min_skew_seconds=SKEW_S - 60
            )
            assert v_after["verified"] is False, (
                "Clock should be back in sync after heal"
            )
            assert abs(v_after["observed_skew_seconds"]) < 60


class TestHealCommandShape:
    """The heal_cmd recorded by each inject must be a valid, complete shell
    string that — when executed — reverses the fault. We can't run it in a
    unit test, but we CAN assert the command shape catches the bugs that
    would silently leave the stack broken."""

    @pytest.mark.asyncio
    async def test_asymmetric_heal_contains_root_qdisc_del(self):
        """`tc qdisc del dev eth0 root` tears the entire prio tree —
        including the child netem qdisc and the filter — in one shot."""
        from agentic_chaos.tools.network_tools import inject_packet_loss
        with patch("agentic_chaos.tools.network_tools.shell",
                   new_callable=AsyncMock) as mock_shell, \
             patch("agentic_chaos.tools.network_tools.docker_get_pid",
                   new_callable=AsyncMock) as mock_pid:
            mock_pid.return_value = 12345
            mock_shell.return_value = (0, "")
            r = await inject_packet_loss(
                "amf", loss_pct=60, peer_ip="172.22.0.23"
            )
        assert r["heal_cmd"].endswith("tc qdisc del dev eth0 root")

    @pytest.mark.asyncio
    async def test_credential_heal_restores_exact_original_k(self):
        """Heal SQL must reference the ORIGINAL K (not a placeholder) and
        scope to the specific auc_id (no `WHERE 1=1` foot-guns).

        Note: shlex.quote wraps the SQL string for safe shell execution,
        so we assert on substring presence rather than exact literal
        SQL form (the embedded single-quotes get shell-escaped).
        """
        from agentic_chaos.tools.application_tools import (
            corrupt_subscriber_credential,
        )
        ORIGINAL_KI = "465B5CE8B199B49FAA5F0A2EE238A6BC"
        with patch("agentic_chaos.tools.application_tools.shell",
                   new_callable=AsyncMock) as mock_shell:
            mock_shell.side_effect = [(0, f"5\t{ORIGINAL_KI}"), (0, "")]
            r = await corrupt_subscriber_credential(
                imsi="001011234567891", ue_container="e2e_ue1"
            )
        heal = r["heal_cmd"]
        # The heal is an UPDATE on the auc table that restores the original K
        # and is scoped to the one specific auc_id row.
        assert "UPDATE auc SET ki" in heal
        assert ORIGINAL_KI in heal
        assert "WHERE auc_id = 5" in heal
        # Explicit guard against the most dangerous accidental scope:
        assert "WHERE 1=1" not in heal
        # Heal must also restart the UE so AMF's cached security context is
        # cleared and UE1 re-attaches against the restored K.
        assert "docker restart e2e_ue1" in heal

        # CDR-0001 Task 1.1: the INJECT mechanism must ALSO restart the UE
        # (otherwise the fault is silent during the observation window).
        # Inject + heal are symmetric in this respect.
        mech = r["mechanism"]
        assert "UPDATE auc SET ki" in mech
        assert r["corrupted_ki"] in mech
        assert "WHERE auc_id = 5" in mech
        assert "docker restart e2e_ue1" in mech

    @pytest.mark.asyncio
    async def test_pmtu_heal_restores_snapshotted_mtu(self):
        """Heal must restore the ORIGINAL MTU snapshotted at inject time —
        not a hard-coded 1500 (which would be wrong on jumbo-frame setups)."""
        from agentic_chaos.tools.datapath_tools import inject_pmtu_blackhole
        with patch("agentic_chaos.tools.datapath_tools.shell",
                   new_callable=AsyncMock) as mock_shell, \
             patch("agentic_chaos.tools.datapath_tools.docker_get_pid",
                   new_callable=AsyncMock) as mock_pid:
            mock_pid.return_value = 12345
            # Pre-inject MTU is 9000 (jumbo) — heal MUST restore to 9000
            mock_shell.side_effect = [
                (0, "2: eth0: ... mtu 9000 qdisc noqueue"),
                (0, ""),
            ]
            r = await inject_pmtu_blackhole("upf", mtu=1280, iface="eth0")
        assert "ip link set dev eth0 mtu 9000" in r["heal_cmd"]
        # Heal of iptables rule must use `|| true` for idempotency
        assert "|| true" in r["heal_cmd"]

    @pytest.mark.asyncio
    async def test_clock_skew_heal_truncates_faketimerc(self):
        """Heal must truncate /etc/faketimerc (libfaketime treats empty as
        zero offset). Removing the file would break subsequent injects."""
        from agentic_chaos.tools.time_tools import inject_clock_skew
        with patch("agentic_chaos.tools.time_tools.shell",
                   new_callable=AsyncMock) as mock_shell:
            mock_shell.side_effect = [(0, "READY"), (0, "")]
            r = await inject_clock_skew("pyhss", skew_seconds=2820)
        assert "/etc/faketimerc" in r["heal_cmd"]
        # `: > <file>` truncates without removing
        assert ": >" in r["heal_cmd"]
        # Must NOT use `rm` — that would break re-injection
        assert " rm " not in r["heal_cmd"]
