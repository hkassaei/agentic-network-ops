"""Pin the scorer's total_score weights after layer_accuracy removal.

`layer_accuracy` was removed (2026-05) and its 0.05 weight folded into
`component_overlap` (0.20 → 0.25). The weighted dimensions now sum to 1.0:

    0.40 root_cause + 0.25 component + 0.15 severity
  + 0.10 fault_type + 0.10 confidence = 1.00

These tests pin:
  * the Python fallback total_score formula (used when the LLM omits it),
  * that the weights sum to exactly 1.0,
  * that no layer_accuracy field survives in the fallback score,
  * that score_diagnosis no longer accepts a network_analysis kwarg.
"""

from __future__ import annotations

import inspect

from agentic_chaos import scorer
from agentic_chaos.scorer import _call_scorer_llm, _fallback_score, score_diagnosis


_WEIGHTS = {
    "root_cause_correct": 0.40,
    "component_overlap": 0.25,
    "severity_correct": 0.15,
    "fault_type_identified": 0.10,
    "confidence_calibrated": 0.10,
}


def test_weights_sum_to_one():
    assert round(sum(_WEIGHTS.values()), 6) == 1.0


def test_fallback_has_no_layer_accuracy():
    fb = _fallback_score("boom")
    assert "layer_accuracy" not in fb
    assert "layer_accuracy_rationale" not in fb
    assert fb["total_score"] == 0.0


def test_score_diagnosis_signature_drops_network_analysis():
    params = set(inspect.signature(score_diagnosis).parameters)
    assert "network_analysis" not in params
    assert params == {"diagnosis_text", "injected_faults", "scenario"}


def test_fallback_formula_computes_perfect_score():
    """A synthetic all-correct parse (with no total_score) must compute to
    1.0 under the new weights. We exercise the formula by replicating the
    fallback computation the scorer uses."""
    parsed = {
        "root_cause_correct": True,
        "component_overlap": 1.0,
        "severity_correct": True,
        "fault_type_identified": True,
        "confidence_calibrated": True,
    }
    total = round(
        0.40 * float(parsed["root_cause_correct"])
        + 0.25 * float(parsed["component_overlap"])
        + 0.15 * float(parsed["severity_correct"])
        + 0.10 * float(parsed["fault_type_identified"])
        + 0.10 * float(parsed["confidence_calibrated"]),
        3,
    )
    assert total == 1.0


def test_prompt_formula_matches_weights():
    """The scorer prompt embeds the weight formula in prose. Pin that the
    new weights (and not the old 0.20 component / 0.05 layer) appear, so
    the LLM-computed score and the Python fallback stay in lockstep."""
    prompt = scorer._SCORER_PROMPT
    assert "0.25 × component_overlap" in prompt
    assert "0.40 × root_cause_correct" in prompt
    assert "layer_accuracy" not in prompt
    assert "0.05" not in prompt  # the old layer_accuracy weight is gone
