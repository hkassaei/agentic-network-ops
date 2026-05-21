"""Tests for `get_deployment_config` — the tool that grounds agent
port/IP assertions in the deployment's actual configuration.

The tool is the structural half of the fix from ADR
`docs/ADR/stack_config_tool_for_agents.md`. Without it, the IG and
investigator default to IANA-standard ports (3868 for Diameter, 27017
for MongoDB, etc.) and produce fabricated "service not bound" faults
when the deployment uses non-standard ports.

These tests run against the REAL `network/.env` and
`network_ontology/data/deployment_metadata.yaml` in the repo so the
parser stays honest about schema drift. If a YAML file is renamed or
a key changes, the tests break loudly — fix the references, don't
loosen the test.
"""

from __future__ import annotations

import asyncio

import pytest

from agentic_ops_common.tools import get_deployment_config


# ─────────────────────────────────────────────────────────────────────
# The triggering-episode regression — PyHSS Diameter port
# ─────────────────────────────────────────────────────────────────────


def test_pyhss_diameter_port_resolves_from_env_not_iana_standard():
    """The triggering episode's failure mode: investigator assumed
    Diameter on PyHSS is bound to IANA-standard 3868. The deployment
    configures `PYHSS_BIND_PORT=3875` in `network/.env`. The tool
    must return 3875, with the env-key source attribution so the
    agent can cite where the value came from."""
    cfg = asyncio.run(get_deployment_config("pyhss"))
    assert "_error" not in cfg, cfg

    diameter_ports = [
        p for p in cfg["listening_ports"]
        if p.get("purpose", {}).get("protocol") == "diameter"
    ]
    assert len(diameter_ports) == 1, (
        f"Expected exactly one Diameter port for pyhss; got: {diameter_ports}"
    )

    diam = diameter_ports[0]
    assert diam["port"] == 3875, (
        f"PyHSS Diameter port must resolve to 3875 (deployment's "
        f"PYHSS_BIND_PORT), NOT the IANA-standard 3868. Got: {diam!r}"
    )
    assert diam["purpose"]["interface"] == "cx"
    assert diam["purpose"]["role"] == "server"
    assert "PYHSS_BIND_PORT" in diam["source"], (
        f"Source attribution must name the env-key the value came from; "
        f"got source={diam['source']!r}"
    )


def test_pyhss_returns_full_listener_set_for_healthy_check():
    """The triggering failure mode: the investigator saw a healthy
    PyHSS listener table (Diameter on 3875, REST on 8080, Redis on
    6379) and called it a fault because the WRONG expected port
    (3868) wasn't there. The tool must surface all the expected
    listeners — at minimum the Diameter port AND the REST API port —
    so the agent's interpretation has a complete reference."""
    cfg = asyncio.run(get_deployment_config("pyhss"))
    purposes = {
        p.get("purpose", {}).get("interface")
        for p in cfg["listening_ports"]
    }
    assert "cx" in purposes, f"Diameter Cx interface missing: {purposes}"
    assert "rest_api" in purposes, f"REST API missing: {purposes}"


def test_pyhss_ip_resolves_from_env():
    """The IP must resolve via the `ip_env_key` chain from
    deployment.yaml + network/.env."""
    cfg = asyncio.run(get_deployment_config("pyhss"))
    assert cfg["ip_env_key"] == "PYHSS_IP"
    assert cfg["ip"] == "172.22.0.18"
    assert cfg["container_name"] == "pyhss"


# ─────────────────────────────────────────────────────────────────────
# Literal-port path (env-key absent)
# ─────────────────────────────────────────────────────────────────────


def test_mongo_uses_literal_port_with_source_attribution():
    """MongoDB doesn't have an env-driven port; the metadata file
    declares 27017 as a literal. Source attribution must reflect that
    so the agent knows it didn't come from .env."""
    cfg = asyncio.run(get_deployment_config("mongo"))
    assert "_error" not in cfg
    ports = cfg["listening_ports"]
    assert len(ports) == 1
    assert ports[0]["port"] == 27017
    assert ports[0]["purpose"]["protocol"] == "mongodb"
    assert "literal" in ports[0]["source"].lower()


def test_upf_has_both_n3_and_n4_with_distinct_purposes():
    """UPF speaks PFCP on N4 to SMF (port 8805) AND GTP-U on N3 from
    gNB (port 2152). Both must be present, distinguishable by their
    structured purpose."""
    cfg = asyncio.run(get_deployment_config("upf"))
    by_interface = {
        p["purpose"]["interface"]: p
        for p in cfg["listening_ports"]
    }
    assert "n4" in by_interface
    assert "n3" in by_interface
    assert by_interface["n4"]["purpose"]["protocol"] == "pfcp"
    assert by_interface["n3"]["purpose"]["protocol"] == "gtp_u"


# ─────────────────────────────────────────────────────────────────────
# Defensive behavior
# ─────────────────────────────────────────────────────────────────────


def test_unknown_component_returns_error_dict_not_raise():
    """A typo'd or unsupported component name returns a structured
    `_error` rather than raising. Lets the agent recover gracefully
    without retrying with a different shape."""
    cfg = asyncio.run(get_deployment_config("nonexistent_nf"))
    assert "_error" in cfg
    assert cfg["component"] == "nonexistent_nf"


def test_component_name_is_case_insensitive():
    """Agents sometimes capitalize NF names ('PyHSS', 'AMF'). The
    tool normalizes to lowercase before lookup."""
    cfg_lower = asyncio.run(get_deployment_config("pyhss"))
    cfg_mixed = asyncio.run(get_deployment_config("PyHSS"))
    assert cfg_lower["component"] == cfg_mixed["component"] == "pyhss"
    assert cfg_lower["listening_ports"] == cfg_mixed["listening_ports"]


def test_purpose_structure_is_dict_not_string():
    """Per ADR design — purpose annotations are structured
    `{protocol, interface, role}` dicts, NOT flat tags. Catches a
    schema-drift regression toward flat strings."""
    cfg = asyncio.run(get_deployment_config("pyhss"))
    for port in cfg["listening_ports"]:
        assert isinstance(port["purpose"], dict), (
            f"purpose must be a dict, got {type(port['purpose'])}: "
            f"{port['purpose']!r}"
        )
        assert "protocol" in port["purpose"]
        assert "interface" in port["purpose"]
        assert "role" in port["purpose"]


def test_source_attribution_present_on_every_port():
    """Every port entry must have a `source` field naming the file
    and key the value came from. Important for the EvidenceValidator
    and for operators debugging the agent's reasoning chain."""
    cfg = asyncio.run(get_deployment_config("pyhss"))
    for port in cfg["listening_ports"]:
        assert port.get("source"), (
            f"port entry missing source attribution: {port!r}"
        )


def test_ontology_files_listed_in_result():
    """The `ontology_files` field tells the agent (and a human
    reading the trace) which ontology files fed the lookup. Pin it
    so future refactors don't drop the attribution."""
    cfg = asyncio.run(get_deployment_config("pyhss"))
    assert "network_ontology/data/deployment.yaml" in cfg["ontology_files"]
    assert "network_ontology/data/deployment_metadata.yaml" in cfg["ontology_files"]


# ─────────────────────────────────────────────────────────────────────
# Coverage smoke — every chaos-scenario NF has metadata
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("nf", [
    # NFs that appear as fault targets across the chaos scenarios.
    # Adding a new chaos target without metadata coverage should fail
    # this test loudly.
    "pyhss", "pcscf", "icscf", "scscf",
    "rtpengine",
    "mongo", "mysql", "dns",
    "amf", "smf", "upf",
    "nr_gnb",
])
def test_chaos_target_nf_has_at_least_one_port_with_purpose(nf):
    """Every NF used as a fault target in the chaos library should
    have at least one port entry with a populated purpose. This is
    the bar for L16 to do its job — without metadata, the lesson
    can't guide the agent away from IANA-standard priors."""
    cfg = asyncio.run(get_deployment_config(nf))
    assert "_error" not in cfg, (
        f"Chaos-target NF '{nf}' has no deployment metadata entry. "
        f"Add it to network_ontology/data/deployment_metadata.yaml."
    )
    assert cfg["listening_ports"], (
        f"NF '{nf}' has metadata entry but no listening_ports. Author "
        f"at least one port in deployment_metadata.yaml."
    )
    for port in cfg["listening_ports"]:
        purpose = port.get("purpose") or {}
        assert purpose.get("protocol"), (
            f"NF '{nf}' port {port.get('port')} missing purpose.protocol"
        )
        assert purpose.get("role"), (
            f"NF '{nf}' port {port.get('port')} missing purpose.role"
        )
