"""Tests for the `agent_exposed` field on MetricEntry.

Per ADR `get_diagnostic_metrics_tool.md`, metric_kb gains one new
opt-in flag — `agent_exposed: bool` — that controls inclusion in the
`get_diagnostic_metrics` tool's "diagnostic supporting" block.

No accompanying `agent_purpose` field: existing KB fields
(`description`, `meaning.*`, `healthy.*`, `related_metrics`,
`disambiguators`, `tags`) already carry the diagnostic content the
tool's render layer needs. Adding a parallel field would duplicate
content and invite drift.

These tests cover:
  1. Default value (backward-compat: existing KB entries without the
     field load successfully).
  2. The full project KB still loads under the new schema.
"""

from __future__ import annotations

from agentic_ops_common.metric_kb.models import (
    Healthy,
    MetricEntry,
    MetricType,
    Source,
)


def _minimal_entry(**overrides) -> MetricEntry:
    """Build a minimally-valid MetricEntry that the test can mutate."""
    base = dict(
        source=Source.KAMCMD,
        type=MetricType.COUNTER,
        description="test metric",
        healthy=Healthy(scale_independent=True),
    )
    base.update(overrides)
    return MetricEntry(**base)


# ============================================================================
# Defaults (backward-compatibility with the existing KB)
# ============================================================================

def test_agent_exposed_defaults_to_false():
    """Backward-compat: existing KB entries don't carry this new
    field. They must load without errors and default to "not exposed
    to agents"."""
    e = _minimal_entry()
    assert e.agent_exposed is False


def test_agent_exposed_can_be_set_true():
    """Setting `agent_exposed=True` is sufficient — no companion field
    required. The tool's render layer projects existing KB content
    (description, meaning, healthy, related_metrics, etc.) for any
    metric tagged this way."""
    e = _minimal_entry(agent_exposed=True)
    assert e.agent_exposed is True


# ============================================================================
# Live project KB still loads
# ============================================================================

def test_full_project_kb_loads_under_new_schema():
    """The full network_ontology/data/metrics.yaml (~hundreds of
    entries authored over time, none yet tagged agent_exposed=True)
    must still load cleanly under the new schema. Backward-compat
    guard: the new field defaults in, no existing entry breaks."""
    from agentic_ops_common.metric_kb import load_kb

    kb = load_kb()  # raises KBLoadError on validation failure
    # Sanity: at least one metric entry came through.
    assert kb.metrics, "KB loaded with no metrics — something else is wrong"

    # ADR `expose_kb_disambiguators_to_investigator.md` (2026-05-06)
    # expanded agent_exposed coverage to every metric with authored
    # `meaning` or `disambiguators` content (30 entries flipped from
    # false→true), bringing the total to ~46. Previous range was
    # 10–40; bumped to 10–70 to accommodate the deliberate expansion
    # plus modest future growth, without losing the noise-detection
    # bound at the upper end. The tighter contract (rich-content
    # entries MUST be exposed) is enforced separately in
    # `test_kb_authoring_invariants.py`.
    exposed_count = 0
    exposed_ids: list[str] = []
    for nf, nf_block in kb.metrics.items():
        for mname, entry in nf_block.metrics.items():
            if entry.agent_exposed:
                exposed_count += 1
                exposed_ids.append(f"{nf_block.layer.value}.{nf}.{mname}")

    assert 10 <= exposed_count <= 70, (
        f"Expected 10–70 metrics tagged agent_exposed=True; got "
        f"{exposed_count}. If you intentionally trimmed or expanded "
        f"the supporting set, update this range. Currently exposed: "
        f"{sorted(exposed_ids)}"
    )

    # Spot-check: a few canonical members must always be present —
    # they are repeatedly load-bearing in saved run logs and removing
    # them would silently regress agent diagnostic capability.
    canonical_must_have = {
        "ims.pcscf.httpclient:connfail",   # P-CSCF→PCF connection health
        "ims.pcscf.sl:4xx_replies",         # SIP client errors
        "ims.icscf.cdp:timeout",            # Cx timeouts (I-CSCF)
        "core.amf.ran_ue",                  # RAN attached check
    }
    missing_canonical = canonical_must_have - set(exposed_ids)
    assert not missing_canonical, (
        f"Canonical agent_exposed metrics missing from KB: "
        f"{sorted(missing_canonical)}. These have been load-bearing "
        f"in real diagnostic runs; they should not be silently dropped."
    )
