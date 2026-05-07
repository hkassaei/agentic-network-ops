"""KB authoring invariants and inventory snapshot.

Per ADR `expose_kb_disambiguators_to_investigator.md`:

  - Any metric entry with authored `meaning` content (`what_it_signals`
    + at least one of `zero` / `spike` / `drop` / `steady_non_zero`) or
    authored `disambiguators` content MUST have `agent_exposed: true`.
    The flag exists to suppress duplicate / implementation-detail
    entries from agent-facing tools, NOT to gate the KB's reasoning.
    These two tests are the regression guard that would have caught
    the original 30-metric gap before it shipped — see the ADR's
    Context section for the audit.

  - The set of metric ids in the KB is pinned by a checked-in snapshot
    file `tests/snapshots/kb_metric_inventory.txt`. Adding or removing
    a metric requires an explicit snapshot update in the same PR — so
    additions are visible at review time and the author has to confirm
    the new entry is fully authored.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agentic_ops_common.metric_kb import load_kb


# ============================================================================
# Authoring invariant: meaning OR disambiguators ⇒ agent_exposed: true
# ============================================================================

def test_every_metric_with_authored_content_is_agent_exposed():
    """If a metric entry has `meaning` or `disambiguators` populated,
    its content is considered load-bearing for the agent and the entry
    MUST have `agent_exposed: true`. The diagnostic_metrics renderer
    only surfaces the rich KB content via the agent_exposed-gated
    supporting block; an unflipped flag hides authored reasoning from
    the LLM.

    Pre-fix this test would have failed on 30 entries (17 with
    disambiguators, 13 with meaning-only). Post-fix every entry with
    rich content passes. Future regressions are caught at PR time.
    """
    kb = load_kb()
    violations: list[str] = []
    for nf_name, nf_block in kb.metrics.items():
        layer = nf_block.layer.value
        for metric_name, entry in nf_block.metrics.items():
            full_id = f"{layer}.{nf_name}.{metric_name}"
            has_meaning = entry.meaning is not None
            has_disamb = bool(entry.disambiguators)
            if (has_meaning or has_disamb) and not entry.agent_exposed:
                violations.append(
                    f"  {full_id}: meaning={has_meaning} "
                    f"disambiguators={has_disamb} agent_exposed=False"
                )
    assert not violations, (
        "KB authoring invariant violated — metrics with authored "
        "meaning/disambiguators content must have agent_exposed: true. "
        "Set the flag on each entry below:\n" + "\n".join(violations)
    )


def test_authoring_invariant_catches_a_synthetic_violation():
    """Sanity check: the invariant test actually fails when violated.

    Constructs a synthetic KB-shaped object with a meaning-bearing
    entry that has agent_exposed=False, then runs the same check.
    """
    from agentic_ops_common.metric_kb.models import (
        Healthy,
        Meaning,
        MetricEntry,
        MetricType,
        Source,
    )

    bad_entry = MetricEntry(
        source=Source.PROMETHEUS,
        type=MetricType.GAUGE,
        description="x",
        meaning=Meaning(what_it_signals="Synthetic.", zero="z"),
        healthy=Healthy(scale_independent=True),
        agent_exposed=False,
    )
    # The entry must be flagged as a violation by the same condition
    # the production test uses.
    has_meaning = bad_entry.meaning is not None
    has_disamb = bool(bad_entry.disambiguators)
    assert (has_meaning or has_disamb) and not bad_entry.agent_exposed


# ============================================================================
# Inventory snapshot — the canonical metric set
# ============================================================================

_SNAPSHOT_PATH = (
    Path(__file__).parent / "snapshots" / "kb_metric_inventory.txt"
)


def _current_inventory() -> list[str]:
    """Return the sorted full-id list of every metric in the KB."""
    kb = load_kb()
    ids: list[str] = []
    for nf_name, nf_block in kb.metrics.items():
        layer = nf_block.layer.value
        for metric_name in nf_block.metrics.keys():
            ids.append(f"{layer}.{nf_name}.{metric_name}")
    return sorted(ids)


def test_kb_metric_inventory_matches_snapshot():
    """The set of metric ids in the KB must match the checked-in
    snapshot exactly. Adding or removing a metric requires updating
    `tests/snapshots/kb_metric_inventory.txt` in the same PR.

    This makes inventory changes visible at review time — silent
    additions can't slip past, and removals force the author to
    confirm no consumer depends on the removed id.
    """
    if not _SNAPSHOT_PATH.exists():
        pytest.fail(
            f"Inventory snapshot missing at {_SNAPSHOT_PATH}. "
            f"Run scripts/update_kb_inventory_snapshot.py to author "
            f"it, or check it in by hand from `_current_inventory()`."
        )
    expected = _SNAPSHOT_PATH.read_text().splitlines()
    expected = [line for line in expected if line and not line.startswith("#")]
    actual = _current_inventory()
    if expected != actual:
        added = sorted(set(actual) - set(expected))
        removed = sorted(set(expected) - set(actual))
        msg = ["KB inventory does not match snapshot."]
        if added:
            msg.append(f"  Added (not in snapshot): {added}")
        if removed:
            msg.append(f"  Removed (in snapshot, not in KB): {removed}")
        msg.append(
            f"  If the change is intentional, update {_SNAPSHOT_PATH}."
        )
        pytest.fail("\n".join(msg))
