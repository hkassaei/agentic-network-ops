"""Tooling contract — drift guards.

Two cheap structural checks:
  1. Every NF Dockerfile in the v6 fleet contains the canonical apt
     install line returned by `apt_install_line()`. Drift dies in CI
     instead of silently shipping a barebones image.
  2. The Investigator prompt teaches the LLM to handle the
     PROBE_TOOL_UNAVAILABLE token. If the prompt drifts, the gating
     in agentic_ops/tools.py is wasted because the LLM won't know
     what to do with the token.

See docs/ADR/nf_container_diagnostic_tooling.md.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from network.tooling_contract import (
    DIAGNOSTIC_TOOLBELT,
    REQUIRED_BY_NF,
    apt_install_line,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


# Map container_name -> Dockerfile path. Some containers share a base
# image (e.g. amf and smf both run docker_open5gs from network/base/),
# so several entries point at the same Dockerfile — the test still
# covers every Dockerfile in the v6 fleet at least once.
_CONTAINER_DOCKERFILE: dict[str, Path] = {
    # Open5GS NFs run docker_open5gs (network/base/Dockerfile)
    "amf":  REPO_ROOT / "network/base/Dockerfile",
    "ausf": REPO_ROOT / "network/base/Dockerfile",
    "bsf":  REPO_ROOT / "network/base/Dockerfile",
    "nrf":  REPO_ROOT / "network/base/Dockerfile",
    "nssf": REPO_ROOT / "network/base/Dockerfile",
    "pcf":  REPO_ROOT / "network/base/Dockerfile",
    "scp":  REPO_ROOT / "network/base/Dockerfile",
    "smf":  REPO_ROOT / "network/base/Dockerfile",
    "smsc": REPO_ROOT / "network/base/Dockerfile",
    "udm":  REPO_ROOT / "network/base/Dockerfile",
    "udr":  REPO_ROOT / "network/base/Dockerfile",
    "upf":  REPO_ROOT / "network/base/Dockerfile",
    # IMS NFs run docker_kamailio (network/ims_base/Dockerfile)
    "icscf": REPO_ROOT / "network/ims_base/Dockerfile",
    "scscf": REPO_ROOT / "network/ims_base/Dockerfile",
    "pcscf": REPO_ROOT / "network/ims_base/Dockerfile",
    # Standalone-built NFs
    "dns":       REPO_ROOT / "network/dns/Dockerfile",
    "metrics":   REPO_ROOT / "network/metrics/Dockerfile",
    "mysql":     REPO_ROOT / "network/mysql/Dockerfile",
    "pyhss":     REPO_ROOT / "network/pyhss/Dockerfile",
    "rtpengine": REPO_ROOT / "network/rtpengine/Dockerfile",
    # UERANSIM RAN
    "nr_gnb":  REPO_ROOT / "network/ueransim/Dockerfile",
    "e2e_ue1": REPO_ROOT / "network/ueransim/Dockerfile",
    "e2e_ue2": REPO_ROOT / "network/ueransim/Dockerfile",
    # Optional (sa-vonr-ibcf-deploy.yaml)
    "ibcf": REPO_ROOT / "network/ibcf/Dockerfile",
}


def test_every_required_nf_has_a_dockerfile_mapping():
    """Sanity: every container in the contract has a known Dockerfile.
    If this fails, either add the mapping above or remove the entry
    from REQUIRED_BY_NF (and explain in the contract module's
    excluded-list comment why)."""
    missing = sorted(set(REQUIRED_BY_NF) - set(_CONTAINER_DOCKERFILE))
    assert not missing, (
        f"Containers in REQUIRED_BY_NF have no Dockerfile mapping in "
        f"this test: {missing}. Update _CONTAINER_DOCKERFILE."
    )


def test_canonical_install_line_is_consistent():
    """The shared apt line must include every binary's apt package
    exactly once, sorted, with --no-install-recommends."""
    line = apt_install_line()
    for entry in DIAGNOSTIC_TOOLBELT.values():
        assert entry["package_apt"] in line, (
            f"package {entry['package_apt']!r} missing from canonical "
            f"install line: {line}"
        )
    assert "--no-install-recommends" in line
    assert "rm -rf /var/lib/apt/lists/*" in line


@pytest.mark.parametrize("nf", sorted(set(_CONTAINER_DOCKERFILE.values())), ids=str)
def test_dockerfile_contains_canonical_install_line(nf: Path):
    """Every Dockerfile in the v6 fleet must contain the canonical
    install line. This is the drift guard: if someone edits a
    Dockerfile and accidentally drops the toolbelt line, this test
    fails before the change ships."""
    line = apt_install_line()
    assert nf.exists(), f"{nf} does not exist"
    contents = nf.read_text()
    assert line in contents, (
        f"{nf} is missing the canonical toolbelt install line. "
        f"Expected substring: {line!r}"
    )
