"""Pin: `_parse_diagnosis_report` auto-repairs `affected_components` for
localized verdicts when the LLM left it empty or filled with empty dicts.

Triggered by `run_20260526_013942_upf_bandwidth_cap.md`: the walker
localized correctly at `upf[eth0]` with qdisc_tbf attribution, and
`localization.hop_node` was populated, but the LLM emitted
`affected_components: [{}]` (one empty dict) instead of
`[{"name": "upf", "role": "Root Cause"}]` as the prompt instructed.
The empty entry rendered as `'?': ?` in the episode markdown and
docked 20% off the score for no diagnostic reason — the localization
itself was correct.

The repair is deterministic: for localized verdicts where
`localization.hop_node` is set and `affected_components` is empty or
contains no entry with a valid `name`, replace it with a single entry
sourced from the localization's hop_node. Same principle as ADR
`path_prioritizer_walks_all_candidates.md`: move correctness off the
LLM and into deterministic code where the evidence already exists.
"""

from __future__ import annotations

import json

import pytest

from agentic_ops_v7.orchestrator import (
    _affected_components_is_empty_or_invalid,
    _parse_diagnosis_report,
)


def _localized_report_payload(**overrides) -> dict:
    """Build the JSON payload Synthesis would emit for a localized
    verdict with hop_node=upf, modulo the field(s) the test wants to
    vary. Mirrors the shape from the 5/26 upf_bandwidth_cap run."""
    payload = {
        "summary": "Transport-layer fault localized to upf[eth0]: "
                   "qdisc_tbf reports 329 packets dropped (191.3%).",
        "root_cause": "Kernel-level packet drop on upf's egress.",
        "root_cause_confidence": "high",
        "primary_suspect_nf": "upf",
        "verdict_kind": "localized",
        "affected_components": [{}],   # ← the LLM-miss the repair fixes
        "timeline": ["walk start", "attribution at upf", "walk end"],
        "recommendation": "Inspect tc qdisc on upf.",
        "explanation": "Per-hop walk-table; attribution at upf[eth0].",
        "localization": {
            "hop_node": "upf",
            "hop_kind": "container",
            "hop_iface": "eth0",
            "attribution_kind": "drops_attributed_here",
            "counter_kind": "qdisc_tbf",
            "dropped_pkts": 329,
            "dropped_pct": 1.913,
            "observed_delay_ms": None,
            "evidence": "upf[eth0] qdisc=tbf: sent=172 dropped=329 (191.28%)",
        },
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# Helper-function unit tests
# ---------------------------------------------------------------------------


def test_invalid_empty_list():
    assert _affected_components_is_empty_or_invalid([]) is True


def test_invalid_none():
    assert _affected_components_is_empty_or_invalid(None) is True


def test_invalid_single_empty_dict():
    """The exact shape the LLM emitted on the triggering run."""
    assert _affected_components_is_empty_or_invalid([{}]) is True


def test_invalid_dict_without_name_key():
    assert _affected_components_is_empty_or_invalid([{"role": "Root Cause"}]) is True


def test_invalid_dict_with_empty_name():
    assert _affected_components_is_empty_or_invalid([{"name": "", "role": "Root Cause"}]) is True


def test_valid_complete_dict():
    components = [{"name": "upf", "role": "Root Cause"}]
    assert _affected_components_is_empty_or_invalid(components) is False


def test_valid_when_any_entry_has_name():
    """If one entry is valid and others aren't, the list as a whole is valid —
    the repair targets the all-bad case, not partial cases."""
    components = [{}, {"name": "upf", "role": "Root Cause"}]
    assert _affected_components_is_empty_or_invalid(components) is False


# ---------------------------------------------------------------------------
# End-to-end: _parse_diagnosis_report applies the repair correctly
# ---------------------------------------------------------------------------


def test_localized_with_empty_dict_gets_repaired():
    """The triggering 5/26 case: LLM emits [{}] for a localized verdict
    with a valid localization. _parse_diagnosis_report repairs it to
    [{"name": <hop_node>, "role": "Root Cause"}].
    """
    payload = _localized_report_payload()  # default affected_components = [{}]
    report = _parse_diagnosis_report(json.dumps(payload))
    assert report.affected_components == [
        {"name": "upf", "role": "Root Cause"}
    ]


def test_localized_with_empty_list_gets_repaired():
    payload = _localized_report_payload(affected_components=[])
    report = _parse_diagnosis_report(json.dumps(payload))
    assert report.affected_components == [
        {"name": "upf", "role": "Root Cause"}
    ]


def test_localized_with_valid_components_is_not_modified():
    """When the LLM correctly populated affected_components, the repair
    must NOT touch it — operators see what the LLM wrote."""
    valid = [{"name": "upf", "role": "Root Cause"}]
    payload = _localized_report_payload(affected_components=valid)
    report = _parse_diagnosis_report(json.dumps(payload))
    assert report.affected_components == valid


def test_non_localized_verdict_is_not_repaired():
    """For verdict_kind != 'localized', the repair must not fire — those
    branches have different rules for affected_components (compound,
    confirmed, promoted, inconclusive) and the LLM is responsible for
    them. Repairing here could mask real LLM misses on those branches."""
    payload = _localized_report_payload(
        verdict_kind="inconclusive",
        affected_components=[{}],
    )
    report = _parse_diagnosis_report(json.dumps(payload))
    # Repair did NOT fire — the empty dict survives.
    assert report.affected_components == [{}]


def test_localized_without_localization_is_not_repaired():
    """If localization is None we can't recover hop_node, so don't fabricate
    a name. This is a defensive case — in practice the synthesis prompt
    requires localization on localized verdicts — but the repair must not
    crash or invent data when localization is missing."""
    payload = _localized_report_payload(
        affected_components=[{}],
        localization=None,
    )
    report = _parse_diagnosis_report(json.dumps(payload))
    assert report.affected_components == [{}]


def test_localized_with_partial_valid_entry_is_not_modified():
    """When affected_components has at least one entry with a valid name,
    the repair leaves the list alone — same rule as the helper-function
    unit test, end-to-end."""
    components = [{}, {"name": "upf", "role": "Root Cause"}]
    payload = _localized_report_payload(affected_components=components)
    report = _parse_diagnosis_report(json.dumps(payload))
    assert report.affected_components == components
