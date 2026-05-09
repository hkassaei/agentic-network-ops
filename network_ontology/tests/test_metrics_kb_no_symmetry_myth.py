"""Regression guard: the KB must never re-introduce the
uplink/downlink symmetry myth.

Per ADR `upf_directional_rates_in_dp_quality_gauges.md`, the false
claim that UPF in/out rates "should be roughly symmetric" or that
"asymmetry indicates directional faults" is removed from every UPF
metric block. This test fails on regression — anyone reintroducing
the false claim is caught at PR time.

The phrasings checked are the exact wording that has, in the past,
caused the LLM Investigator to misread normal UPF in/out asymmetry
(e.g. 8.9 in / 6.8 out under NULL_AUDIO voice) as packet loss and
disprove correct RTPEngine hypotheses.

Allow-list: the legitimate rtpengine disambiguator at line ~1524
("UPF N3 in/out symmetry further partitions the location...") uses
"symmetry" in a context-aware way that does not assert the myth —
it describes what symmetric vs asymmetric MEANS for fault
localization, given that errors_per_second is already known to be
zero. That entry is whitelisted by being scoped to the rtpengine NF
block; this test only scans the UPF NF block plus the cumulative
counters under it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml


_METRICS_YAML = (
    Path(__file__).resolve().parent.parent / "data" / "metrics.yaml"
)
_STACK_RULES_YAML = (
    Path(__file__).resolve().parent.parent / "data" / "stack_rules.yaml"
)

# Phrasings that have, in past KB versions, asserted the false
# uplink/downlink symmetry expectation. Each is a substring; presence
# in the UPF block (any field) fails the test.
_FORBIDDEN_PHRASES_IN_UPF = [
    "roughly symmetric",
    "symmetric with uplink",
    "in/out symmetry check",
    "asymmetry indicates directional faults",
    "Asymmetry = directional path",
    "Typically mirrors uplink",
    "mirrors uplink rate",
    "Asymmetry between these two is diagnostic",
    "Uplink and downlink typically move together",
]


def _walk_strings(obj, path=""):
    """Yield (json-pointer-style path, string value) for every string
    leaf in the nested object."""
    if isinstance(obj, str):
        yield path, obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from _walk_strings(v, f"{path}.{k}" if path else k)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            yield from _walk_strings(item, f"{path}[{i}]")


def test_upf_metric_block_contains_no_symmetry_myth():
    """Walk every string in the UPF NF block of metrics.yaml and
    assert none contains a forbidden phrase."""
    with _METRICS_YAML.open() as f:
        data = yaml.safe_load(f)

    upf_block = data["metrics"].get("upf")
    assert upf_block is not None, "UPF NF block missing from metrics.yaml"

    hits: list[str] = []
    for path, text in _walk_strings(upf_block, "metrics.upf"):
        for phrase in _FORBIDDEN_PHRASES_IN_UPF:
            if phrase.lower() in text.lower():
                hits.append(
                    f"  FOUND {phrase!r} at {path}\n"
                    f"    text excerpt: {text[:200]!r}"
                )

    if hits:
        pytest.fail(
            "Symmetry myth re-introduced in UPF metric block. The "
            "claim that uplink/downlink should be 'symmetric' or that "
            "asymmetry indicates loss/faults is structurally wrong "
            "and has caused the Investigator to misdiagnose multiple "
            "RTPEngine call-quality scenarios. Rewrite to: "
            "'asymmetry is structural, never alone evidence of loss; "
            "see stack rule upf_counters_are_directional.'\n"
            + "\n".join(hits)
        )


def test_stack_rules_yaml_does_not_assert_symmetry_as_health_signal():
    """The stack rule's prose may mention 'symmetry' when describing
    the cumulative-counter rule (the rule's whole point is that
    traffic profile determines ratio). What it MUST NOT do is assert
    that asymmetry indicates a health problem. Check that no rule's
    prose contains a phrase that would teach the agent to read
    asymmetry as a fault signal."""
    with _STACK_RULES_YAML.open() as f:
        data = yaml.safe_load(f)

    forbidden_in_stack_rules = [
        "asymmetry indicates packet loss",
        "asymmetry indicates loss",
        "asymmetry = loss",
        "asymmetry = drop",
        "asymmetry indicates a fault",
        "subtract to get loss",
    ]

    hits: list[str] = []
    for path, text in _walk_strings(data, "stack_rules"):
        for phrase in forbidden_in_stack_rules:
            if phrase.lower() in text.lower():
                hits.append(
                    f"  FOUND {phrase!r} at {path}\n"
                    f"    text: {text[:200]!r}"
                )
    assert not hits, "Stack rules YAML contains asymmetry-as-fault assertion:\n" + "\n".join(hits)


def test_smf_and_amf_blocks_contain_no_upf_symmetry_myth():
    """Adjacent NF blocks (smf, amf) reference UPF metrics in their
    related_metrics / disambiguators sections. Confirm no leak of
    the symmetry myth into those blocks either."""
    with _METRICS_YAML.open() as f:
        data = yaml.safe_load(f)

    hits: list[str] = []
    for nf_name in ("smf", "amf", "rtpengine", "pcscf", "icscf", "scscf"):
        block = data["metrics"].get(nf_name)
        if block is None:
            continue
        for path, text in _walk_strings(block, f"metrics.{nf_name}"):
            for phrase in (
                "Roughly symmetric with uplink",
                "should be symmetric",
                "in/out symmetry check",
            ):
                if phrase.lower() in text.lower():
                    hits.append(f"  FOUND {phrase!r} at {path}: {text[:160]!r}")
    assert not hits, "Symmetry myth leaked into adjacent NF block:\n" + "\n".join(hits)
