"""Pin the scorer's MECHANICAL score computation.

Score arithmetic is deterministic, never LLM-driven (2026-05):
  * `component_overlap` — structured comparison of ground-truth NF(s) vs the
    diagnosis's root-cause set (Root Cause = 1.0, present-not-root = 0.3,
    absent = 0.0).
  * `total_score` — the weighted sum below, ALWAYS recomputed (never the
    LLM's self-reported total).

    0.40 root_cause + 0.25 component + 0.15 severity
  + 0.10 fault_type + 0.10 confidence = 1.00

Triggered by run_20260527_192736_mongodb_gone: a clean Root-Cause
diagnosis scored 75% because (a) the LLM judged component_overlap=0.75 on
a correct placement and (b) the scorer trusted the LLM's self-reported
total, which contradicted its own per-dimension verdicts (4×Yes + 0.75
should be 94%, not 75%). Both are now mechanical.
"""

from __future__ import annotations

import inspect

from agentic_chaos import scorer
from agentic_chaos.scorer import (
    _compute_total_score,
    _fallback_score,
    _mechanical_component_overlap,
    _SCORE_WEIGHTS,
    score_diagnosis,
)


def test_weights_sum_to_one():
    assert round(sum(_SCORE_WEIGHTS.values()), 6) == 1.0


def test_fallback_has_no_layer_accuracy():
    fb = _fallback_score("boom")
    assert "layer_accuracy" not in fb
    assert fb["total_score"] == 0.0


def test_score_diagnosis_signature_takes_diagnosis_report_not_network_analysis():
    params = set(inspect.signature(score_diagnosis).parameters)
    assert "network_analysis" not in params
    assert params == {
        "diagnosis_text", "injected_faults", "scenario", "diagnosis_report",
    }


# ---------------------------------------------------------------------------
# Mechanical total_score
# ---------------------------------------------------------------------------


def test_total_is_recomputed_not_trusted_from_llm():
    """The headline mongodb_gone bug: every dimension positive (4×Yes +
    component 1.0) must compute to 100%, regardless of any LLM-emitted total."""
    parsed = {
        "root_cause_correct": True,
        "component_overlap": 1.0,
        "severity_correct": True,
        "fault_type_identified": True,
        "confidence_calibrated": True,
        # An LLM-emitted (wrong) total must be ignored — _compute_total_score
        # reads only the dimensions.
        "total_score": 0.75,
    }
    assert _compute_total_score(parsed) == 1.0


def test_total_with_partial_component():
    parsed = {
        "root_cause_correct": True,
        "component_overlap": 0.75,
        "severity_correct": True,
        "fault_type_identified": True,
        "confidence_calibrated": True,
    }
    # 0.40 + 0.1875 + 0.15 + 0.10 + 0.10 = 0.9375
    assert _compute_total_score(parsed) == 0.938


# ---------------------------------------------------------------------------
# Mechanical component_overlap
# ---------------------------------------------------------------------------


def test_component_overlap_root_cause_is_one():
    """mongodb_gone: mongo is the Root Cause → 1.0, not 0.75."""
    dr = {
        "primary_suspect_nf": "mongo",
        "affected_components": [
            {"name": "mongo", "role": "Root Cause"},
            {"name": "udr", "role": "Secondary"},
            {"name": "pcscf", "role": "Symptomatic"},
        ],
    }
    overlap, rationale = _mechanical_component_overlap({"mongo"}, dr)
    assert overlap == 1.0
    assert "Root Cause" in rationale


def test_component_overlap_present_but_not_root_is_partial():
    dr = {
        "primary_suspect_nf": "pcscf",
        "affected_components": [
            {"name": "pcscf", "role": "Root Cause"},
            {"name": "mongo", "role": "Symptomatic"},
        ],
    }
    # Ground truth is mongo but the diagnosis called pcscf the root cause;
    # mongo appears only as Symptomatic → 0.3.
    overlap, _ = _mechanical_component_overlap({"mongo"}, dr)
    assert overlap == 0.3


def test_component_overlap_absent_is_zero():
    dr = {
        "primary_suspect_nf": "pcscf",
        "affected_components": [{"name": "pcscf", "role": "Root Cause"}],
    }
    overlap, _ = _mechanical_component_overlap({"mongo"}, dr)
    assert overlap == 0.0


def test_component_overlap_primary_suspect_counts_as_root():
    """Even with an empty affected_components list, primary_suspect_nf
    naming the GT NF earns full credit."""
    dr = {"primary_suspect_nf": "mongo", "affected_components": []}
    overlap, _ = _mechanical_component_overlap({"mongo"}, dr)
    assert overlap == 1.0


def test_component_overlap_no_diagnosis_report_is_zero():
    overlap, _ = _mechanical_component_overlap({"mongo"}, None)
    assert overlap == 0.0


def test_component_overlap_multi_gt_is_mean():
    """Compound ground truth: average per-NF credit."""
    dr = {
        "primary_suspect_nf": "pyhss",
        "affected_components": [
            {"name": "pyhss", "role": "Root Cause"},
            {"name": "scscf", "role": "Symptomatic"},
        ],
    }
    # pyhss = Root Cause (1.0), scscf present-not-root (0.3) → mean 0.65
    overlap, _ = _mechanical_component_overlap({"pyhss", "scscf"}, dr)
    assert overlap == 0.65


# ---------------------------------------------------------------------------
# LLM no longer scores the mechanical fields
# ---------------------------------------------------------------------------


def test_prompt_does_not_ask_llm_for_component_or_total():
    prompt = scorer._SCORER_PROMPT
    # The LLM is explicitly told NOT to score these.
    assert "do not score component overlap or the total" in prompt.lower()
    assert "layer_accuracy" not in prompt
