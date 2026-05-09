"""Pure-Python evaluator for the `upf_counters_are_directional` rule.

Two fire conditions, one verdict template:

  - **Cumulative pair**: both `fivegs_ep_n3_gtp_indatapktn3upf` and
    `fivegs_ep_n3_gtp_outdatapktn3upf` present in observations. These
    are the lifetime-cumulative counters surfaced by `get_nf_metrics`.
    Their ratio is determined by the integral of all traffic that has
    flowed through the UPF — not by current behavior.
  - **Rate pair**: both `upf_in_pps` and `upf_out_pps` present in
    observations. These are the rate-windowed values surfaced by
    `get_dp_quality_gauges`. They reflect current throughput per
    direction over the probe's window — useful for activity reads,
    but the cross-direction asymmetry is STILL determined by the
    instantaneous traffic profile and is STILL not loss evidence on
    its own.

Both surfaces produce a verdict tagged `window_kind: cumulative` or
`window_kind: rate` so the agent (and downstream consumers) can see
which surface fired. When both pairs are present, BOTH verdicts fire —
the agent benefits from seeing the analysis on both surfaces and
understanding rate-based metrics' primacy for current-state failure
detection.

The asymmetry formula and severity gradient are identical across
surfaces. Severity escalates to `high_temptation` at >= 30%
asymmetry — empirically the regime where the agent is most likely
to misread the asymmetry as packet loss.

ADR: [`upf_directional_rates_in_dp_quality_gauges.md`](
docs/ADR/upf_directional_rates_in_dp_quality_gauges.md).
The original cumulative-only rule is in
[`upf_counters_directional_stack_rule.md`](
docs/ADR/upf_counters_directional_stack_rule.md).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

import yaml

_log = logging.getLogger("ontology.rules.upf_directional")

# Source of truth for the rule's prose lives in stack_rules.yaml.
_STACK_RULES_YAML = (
    Path(__file__).resolve().parent.parent / "data" / "stack_rules.yaml"
)
_RULE_ID = "upf_counters_are_directional"

# 30% asymmetry threshold escalates the verdict's severity. Documented
# rationale in `upf_counters_directional_stack_rule.md`.
_HIGH_TEMPTATION_THRESHOLD_PCT = 30.0

# The three correct loss-detection methods. Identical across both
# fire conditions — loss-detection is direction-and-window agnostic.
_CORRECT_METHODS: list[str] = [
    "Same-direction rate comparison: "
    "rate(fivegs_ep_n3_gtp_indatapktn3upf[2m]) vs expected "
    "rate for current traffic (G.711 call = ~50 pps per direction)",
    "RTCP-based voice quality: "
    "rate(rtpengine_packetloss_total[2m]) / "
    "rate(rtpengine_packetloss_samples_total[2m]) = "
    "sampled loss fraction from RTCP reports",
    "Interface drop counters on tc qdisc "
    "(not currently exposed as a tool)",
]


def _load_rule_prose() -> dict[str, Any]:
    """Read the rule's prose fields (rule, implication, examples,
    invalidates, priority) from stack_rules.yaml.

    Returns a dict with the same shape `OntologyClient.get_stack_rules`
    returns from Neo4j, modulo the lack of Neo4j-injected fields. If
    the YAML file is missing or doesn't contain the rule, returns a
    minimal stub so the evaluator still produces a coherent verdict.
    """
    try:
        with _STACK_RULES_YAML.open() as f:
            data = yaml.safe_load(f)
    except FileNotFoundError:
        _log.warning("stack_rules.yaml not found at %s", _STACK_RULES_YAML)
        return {"id": _RULE_ID}
    except yaml.YAMLError as e:
        _log.warning("stack_rules.yaml parse error: %s", e)
        return {"id": _RULE_ID}

    rules = (data or {}).get("stack_rules") or []
    for rule in rules:
        if isinstance(rule, dict) and rule.get("id") == _RULE_ID:
            return rule
    return {"id": _RULE_ID}


def _is_numeric(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _asymmetry_pct(in_val: float, out_val: float) -> float:
    """|in - out| / max(|in|, |out|) * 100, rounded to 1 decimal.

    When both values are zero, asymmetry is 0% (defined edge case;
    the rule still fires — the educational value is always relevant).
    """
    max_val = max(abs(in_val), abs(out_val))
    if max_val == 0:
        return 0.0
    return round(abs(in_val - out_val) / max_val * 100, 1)


def _build_verdict(
    in_val: float,
    out_val: float,
    asymmetry_pct: float,
    window_kind: str,
    in_key: str,
    out_key: str,
) -> dict[str, Any]:
    """Construct the verdict text for one fire condition.

    `window_kind` ∈ {"cumulative", "rate"} controls the wording so
    the agent sees explicitly whether the analysis is over a
    lifetime-counter pair or a rate-windowed pair.
    """
    if asymmetry_pct >= _HIGH_TEMPTATION_THRESHOLD_PCT:
        severity = "high_temptation"
        if window_kind == "rate":
            verdict_text = (
                f"Asymmetry is {asymmetry_pct}% across the rate window "
                f"({in_key}={in_val} vs {out_key}={out_val}) — HIGH "
                f"temptation to misinterpret as packet loss. It is NOT. "
                f"Asymmetry between independent traffic directions is "
                f"STRUCTURAL — voice with NULL_AUDIO, signaling-only "
                f"chatter, idle UEs, and asymmetric data sessions are "
                f"all valid healthy patterns with persistent in/out "
                f"imbalance. DO NOT report this asymmetry as loss. "
                f"Use one of the correct_methods below for actual "
                f"loss detection."
            )
        else:
            verdict_text = (
                f"Asymmetry is {asymmetry_pct}% — HIGH temptation "
                f"to misinterpret as packet loss. It is NOT. This "
                f"asymmetry is structural (determined by historical "
                f"traffic mix over the container's lifetime). DO NOT "
                f"report the difference as loss. Use one of the "
                f"correct_methods below for actual loss detection."
            )
    else:
        severity = "informational"
        if window_kind == "rate":
            verdict_text = (
                f"Asymmetry is {asymmetry_pct}% across the rate window "
                f"({in_key}={in_val} vs {out_key}={out_val}). "
                f"Regardless of magnitude, in/out rate asymmetry is "
                f"never, by itself, evidence of packet loss — voice "
                f"with NULL_AUDIO, signaling-only chatter, and "
                f"asymmetric data sessions all produce persistent "
                f"imbalance. See correct_methods for actual loss "
                f"detection."
            )
        else:
            verdict_text = (
                f"Asymmetry is {asymmetry_pct}% — counters are "
                f"roughly consistent. Regardless, these counters "
                f"cannot be subtracted to compute loss under any "
                f"circumstance. See correct_methods for actual "
                f"loss detection."
            )

    return {
        "in_key": in_key,
        "out_key": out_key,
        "in_total": in_val,
        "out_total": out_val,
        "asymmetry_pct": asymmetry_pct,
        "severity": severity,
        "verdict": verdict_text,
        "window_kind": window_kind,
        "correct_methods": list(_CORRECT_METHODS),
    }


def evaluate_upf_directional_rule(
    observations: dict[str, Any],
    *,
    rule_prose: Optional[dict[str, Any]] = None,
) -> list[dict[str, Any]]:
    """Evaluate the rule against an observations dict.

    Returns a list of triggered-rule verdicts (zero, one, or two —
    one per fire condition that matched). Each verdict is a dict in
    the same shape `OntologyClient.check_stack_rules` produces, with
    `window_kind` added so the consumer can distinguish cumulative
    vs rate analyses.

    When BOTH the cumulative pair and the rate pair are present, BOTH
    verdicts fire. This is intentional — the agent benefits from seeing
    the analysis on both surfaces, and rate-windowed values are usually
    more informative than cumulative counters for current-state
    failure detection.

    The rule's prose fields (rule, implication, examples) are loaded
    from stack_rules.yaml unless `rule_prose` is provided (used by
    `OntologyClient` to inject the Neo4j-loaded prose so the verdict
    matches the existing return shape exactly).
    """
    if rule_prose is None:
        rule_prose = _load_rule_prose()

    triggered: list[dict[str, Any]] = []

    # Cumulative pair.
    in_cum = observations.get("fivegs_ep_n3_gtp_indatapktn3upf")
    out_cum = observations.get("fivegs_ep_n3_gtp_outdatapktn3upf")
    if _is_numeric(in_cum) and _is_numeric(out_cum):
        verdict = _build_verdict(
            in_val=float(in_cum),
            out_val=float(out_cum),
            asymmetry_pct=_asymmetry_pct(float(in_cum), float(out_cum)),
            window_kind="cumulative",
            in_key="fivegs_ep_n3_gtp_indatapktn3upf",
            out_key="fivegs_ep_n3_gtp_outdatapktn3upf",
        )
        # Merge in the rule's prose fields (rule:, implication:, etc.)
        # so callers see the same shape OntologyClient produces.
        triggered.append({**rule_prose, **verdict})

    # Rate pair.
    in_rate = observations.get("upf_in_pps")
    out_rate = observations.get("upf_out_pps")
    if _is_numeric(in_rate) and _is_numeric(out_rate):
        verdict = _build_verdict(
            in_val=float(in_rate),
            out_val=float(out_rate),
            asymmetry_pct=_asymmetry_pct(float(in_rate), float(out_rate)),
            window_kind="rate",
            in_key="upf_in_pps",
            out_key="upf_out_pps",
        )
        triggered.append({**rule_prose, **verdict})

    return triggered
