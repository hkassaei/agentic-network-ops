"""Unit tests for the scenario library — no Docker needed."""

import pytest

from agentic_chaos.models import BlastRadius, FaultCategory
from agentic_chaos.scenarios.library import (
    SCENARIOS,
    get_scenario,
    list_scenarios,
)


class TestScenarioLibrary:
    def test_has_14_scenarios(self):
        # 11 baseline + 3 path-walk-ADR scenarios:
        #   Phase 5: P-CSCF Packet Loss
        #   Phase 6: RTPEngine Latency Injection, UPF Bandwidth Cap
        assert len(SCENARIOS) == 14

    def test_all_names_unique(self):
        names = list(SCENARIOS.keys())
        assert len(names) == len(set(names))

    def test_get_scenario_by_name(self):
        s = get_scenario("P-CSCF Latency")
        assert s.name == "P-CSCF Latency"
        assert s.category == FaultCategory.NETWORK

    def test_get_scenario_unknown_raises(self):
        with pytest.raises(KeyError, match="Unknown scenario"):
            get_scenario("Nonexistent Scenario")

    def test_list_scenarios_returns_all(self):
        items = list_scenarios()
        assert len(items) == 14
        assert all("name" in s for s in items)
        assert all("category" in s for s in items)

    def test_every_scenario_has_at_least_one_fault(self):
        for name, s in SCENARIOS.items():
            assert len(s.faults) >= 1, f"{name} has no faults"

    def test_every_scenario_has_description(self):
        for name, s in SCENARIOS.items():
            assert len(s.description) > 20, f"{name} has short description"

    def test_every_scenario_has_expected_symptoms(self):
        for name, s in SCENARIOS.items():
            assert len(s.expected_symptoms) >= 1, f"{name} has no expected symptoms"

    def test_every_fault_has_valid_type(self):
        valid_types = {
            "container_kill", "container_stop", "container_pause", "container_restart",
            "network_latency", "network_loss", "network_corruption",
            "network_bandwidth", "network_partition",
        }
        for name, s in SCENARIOS.items():
            for f in s.faults:
                assert f.fault_type in valid_types, (
                    f"{name}: unknown fault type '{f.fault_type}'"
                )

    def test_every_fault_target_is_known_container(self):
        from agentic_chaos.tools._common import ALL_CONTAINERS
        for name, s in SCENARIOS.items():
            for f in s.faults:
                assert f.target in ALL_CONTAINERS, (
                    f"{name}: unknown target '{f.target}'"
                )

    def test_network_latency_has_delay_param(self):
        for name, s in SCENARIOS.items():
            for f in s.faults:
                if f.fault_type == "network_latency":
                    assert "delay_ms" in f.params, f"{name}: latency missing delay_ms"
                    assert f.params["delay_ms"] > 0

    def test_network_loss_has_loss_param(self):
        for name, s in SCENARIOS.items():
            for f in s.faults:
                if f.fault_type == "network_loss":
                    assert "loss_pct" in f.params, f"{name}: loss missing loss_pct"
                    assert 0 < f.params["loss_pct"] <= 100

    def test_network_partition_has_target_ip(self):
        for name, s in SCENARIOS.items():
            for f in s.faults:
                if f.fault_type == "network_partition":
                    assert "target_ip" in f.params, f"{name}: partition missing target_ip"
                    # Validate IP format
                    import ipaddress
                    ipaddress.ip_address(f.params["target_ip"])

    def test_ttl_seconds_reasonable(self):
        for name, s in SCENARIOS.items():
            assert s.ttl_seconds >= 30, f"{name}: TTL too short"
            assert s.ttl_seconds <= 600, f"{name}: TTL too long"

    def test_blast_radius_categories(self):
        single = [s for s in SCENARIOS.values() if s.blast_radius == BlastRadius.SINGLE_NF]
        multi = [s for s in SCENARIOS.values() if s.blast_radius == BlastRadius.MULTI_NF]
        globe = [s for s in SCENARIOS.values() if s.blast_radius == BlastRadius.GLOBAL]

        assert len(single) >= 3, "Need at least 3 single-NF scenarios"
        assert len(multi) >= 2, "Need at least 2 multi-NF scenarios"
        assert len(globe) >= 1, "Need at least 1 global scenario"

    def test_pcscf_latency_has_escalation(self):
        s = get_scenario("P-CSCF Latency")
        assert s.escalation is True


class TestPCSCFPacketLoss:
    """The P-CSCF Packet Loss scenario authored in Phase 5 of ADR
    `path_anchored_probe_planning_for_transport_layer_faults.md`.

    This scenario is worked example 2 from the ADR — same fault class
    as Call Quality Degradation but on a signaling-plane container.
    The contract: v7's path walk localizes both this and Call Quality
    Degradation correctly; v6's per-NF hypothesis pipeline mis-diagnoses
    both.
    """

    def test_scenario_registered(self):
        s = get_scenario("P-CSCF Packet Loss")
        assert s.name == "P-CSCF Packet Loss"

    def test_targets_pcscf_with_30pct_loss(self):
        """The fault must be tc-netem 30% on pcscf to produce the
        symptom signature documented in the ADR."""
        s = get_scenario("P-CSCF Packet Loss")
        assert len(s.faults) == 1
        fault = s.faults[0]
        assert fault.fault_type == "network_loss"
        assert fault.target == "pcscf"
        assert fault.params.get("loss_pct") == 30

    def test_category_is_network(self):
        """The fault is transport-layer; that maps to FaultCategory.NETWORK."""
        s = get_scenario("P-CSCF Packet Loss")
        assert s.category == FaultCategory.NETWORK

    def test_blast_radius_is_single_nf(self):
        """tc-netem on a single container — single-NF blast radius."""
        s = get_scenario("P-CSCF Packet Loss")
        assert s.blast_radius == BlastRadius.SINGLE_NF

    def test_expected_symptoms_describe_signaling_path(self):
        """The symptom narrative names rate drops at icscf/scscf,
        latency spike at pcscf, and explicitly notes that data plane
        and Kamailio internal counters are unchanged. This is what
        operators read to ground-truth the agent's diagnosis."""
        s = get_scenario("P-CSCF Packet Loss")
        haystack = " | ".join(s.expected_symptoms).lower()
        # Signaling-rate drops at the downstream NFs
        assert "icscf" in haystack
        assert "scscf" in haystack
        # pcscf latency / register-time impact
        assert "pcscf" in haystack
        # Crucially: application metrics unchanged (the disambiguator
        # ADR's failure-mode signature)
        assert "errors_per_second" in haystack
        # Data plane untouched
        assert "data plane" in haystack or "upf" in haystack

    def test_observation_window_matches_call_quality_degradation(self):
        """The two worked-example scenarios should observe for the
        same window so v6 vs v7 comparisons aren't biased by
        different observation budgets."""
        pcscf = get_scenario("P-CSCF Packet Loss")
        cqd = get_scenario("Call Quality Degradation")
        assert pcscf.observation_traffic_seconds == cqd.observation_traffic_seconds
        assert pcscf.observation_window_seconds == cqd.observation_window_seconds

    def test_appears_in_run_all_chaos_scenarios_script(self):
        """The shell-script's batch list must include this scenario
        so `bash scripts/run-all-chaos-scenarios.sh v7` runs it."""
        from pathlib import Path
        repo_root = Path(__file__).resolve().parents[2]
        script = (repo_root / "scripts" / "run-all-chaos-scenarios.sh").read_text()
        assert '"P-CSCF Packet Loss"' in script, (
            "scripts/run-all-chaos-scenarios.sh's SCENARIOS list should "
            "include 'P-CSCF Packet Loss' so the chaos batch picks it up."
        )


class TestPhase6GeneralizationScenarios:
    """The two generalization scenarios authored in Phase 6 of ADR
    `path_anchored_probe_planning_for_transport_layer_faults.md`.

    These prove the path walk machinery generalizes beyond `netem loss`
    — it correctly localizes `netem delay` (RTPEngine Latency Injection)
    and `tbf rate cap` (UPF Bandwidth Cap) using the same abstractions.
    """

    def test_rtpengine_latency_injection_registered(self):
        s = get_scenario("RTPEngine Latency Injection")
        assert s.name == "RTPEngine Latency Injection"

    def test_rtpengine_latency_injection_uses_network_latency_fault(self):
        s = get_scenario("RTPEngine Latency Injection")
        assert len(s.faults) == 1
        fault = s.faults[0]
        assert fault.fault_type == "network_latency"
        assert fault.target == "rtpengine"
        assert fault.params.get("delay_ms") == 100

    def test_rtpengine_latency_injection_in_batch_script(self):
        from pathlib import Path
        repo_root = Path(__file__).resolve().parents[2]
        script = (repo_root / "scripts" / "run-all-chaos-scenarios.sh").read_text()
        assert '"RTPEngine Latency Injection"' in script

    def test_upf_bandwidth_cap_registered(self):
        s = get_scenario("UPF Bandwidth Cap")
        assert s.name == "UPF Bandwidth Cap"

    def test_upf_bandwidth_cap_uses_network_bandwidth_fault(self):
        s = get_scenario("UPF Bandwidth Cap")
        assert len(s.faults) == 1
        fault = s.faults[0]
        assert fault.fault_type == "network_bandwidth"
        assert fault.target == "upf"
        # Tight cap chosen to drop voice + signaling packets reliably.
        assert fault.params.get("rate_kbit") == 100

    def test_upf_bandwidth_cap_in_batch_script(self):
        from pathlib import Path
        repo_root = Path(__file__).resolve().parents[2]
        script = (repo_root / "scripts" / "run-all-chaos-scenarios.sh").read_text()
        assert '"UPF Bandwidth Cap"' in script

    def test_phase6_scenarios_match_phase5_observation_window(self):
        """All path-walk-ADR scenarios use the same observation budget
        so v6 vs v7 score comparisons aren't biased."""
        names = ["RTPEngine Latency Injection", "UPF Bandwidth Cap",
                 "P-CSCF Packet Loss", "Call Quality Degradation"]
        windows = [
            (s.observation_traffic_seconds, s.observation_window_seconds)
            for s in (get_scenario(n) for n in names)
        ]
        # All same.
        assert len(set(windows)) == 1, (
            f"observation budgets differ across path-walk scenarios: {windows}"
        )

    def test_phase6_scenarios_are_single_nf_blast_radius(self):
        """Both Phase 6 scenarios target a single container — they're
        focused proofs that the path walk localizes the right hop, not
        multi-NF cascade tests."""
        for name in ("RTPEngine Latency Injection", "UPF Bandwidth Cap"):
            s = get_scenario(name)
            assert s.blast_radius == BlastRadius.SINGLE_NF
