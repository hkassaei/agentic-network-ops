"""IG-side guardrails: fan-out audit + Decision A's two sub-checks.

This module hosts three deterministic checks against IG output:

  * `audit_fanout` (PR 1) — Phase-5 fan-out sanity over (hypotheses,
    plans): silent plan-drops, hypotheses-without-plan, and NF
    mismatches between a hypothesis and its plan. Runs after IG has
    emitted; the orchestrator surfaces findings via log warnings and a
    synthetic PhaseTrace.

  * `lint_ig_plan` sub-check A1 (PR 4 — Decision A1) — partner-probe
    coverage. Compositional probes (whose readings are a function of
    multiple elements) need a partner probe whose path differs in the
    hypothesis's primary suspect NF. Without that, the Investigator
    cannot localize which element owns any deviation it sees.

  * `lint_ig_plan` sub-check A2 (PR 4 — Decision A2) — IG-statement
    linter. Mechanism-scoping language in `expected_if_hypothesis_holds`
    or `falsifying_observation` re-introduces the layer scope that
    Decision D shut down at the NA stage. The motivating evidence:
    `run_20260501_012613_data_plane_degradation` — NA's three
    statements were clean, but IG's h1 plan wrote
    "falsifying_observation: high RTT or packet loss → points to a
    transport network issue rather than a UPF-internal fault" and the
    Investigator faithfully concluded DISPROVEN on a layer mismatch.

The fan-out audit and `lint_ig_plan` are independent — the fan-out
audit runs after Phase-5 fan-out, while `lint_ig_plan` runs immediately
after IG emit and BEFORE Phase-5 fan-out. Both live here because their
inputs are typed plan / hypothesis objects.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..models import (
    FalsificationPlan,
    FalsificationPlanSet,
    FalsificationProbe,
    Hypothesis,
)
from ._mechanism_scope import BASE_PATTERNS, scan
from .base import GuardrailResult, GuardrailVerdict


@dataclass
class FanoutAuditResult:
    selected_hypotheses: list[Hypothesis] = field(default_factory=list)
    plans: list[FalsificationPlan] = field(default_factory=list)
    hyps_without_plan: list[Hypothesis] = field(default_factory=list)
    plans_without_hyp: list[str] = field(default_factory=list)
    # Each entry: (hypothesis_id, hypothesis_nf, plan_nf)
    nf_mismatches: list[tuple[str, str, str]] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return (
            not self.hyps_without_plan
            and not self.plans_without_hyp
            and not self.nf_mismatches
        )

    def render_summary(self) -> str:
        """Render the audit as a single string for PhaseTrace.output_summary.

        The orchestrator currently emits "all matched" when clean and
        a semicolon-joined finding list otherwise. Preserve that exact
        format so the recorder output is byte-identical to the
        pre-extraction version.
        """
        if self.is_clean:
            return "all matched"
        lines: list[str] = []
        if self.plans_without_hyp:
            lines.append(
                f"DROPPED PLANS (no matching NA hypothesis id): "
                f"{self.plans_without_hyp}"
            )
        if self.hyps_without_plan:
            lines.append(
                f"HYPOTHESES WITHOUT PLAN (forced INCONCLUSIVE): "
                f"{[h.id for h in self.hyps_without_plan]}"
            )
        for hid, hyp_nf, plan_nf in self.nf_mismatches:
            lines.append(
                f"NF MISMATCH on {hid}: hypothesis names {hyp_nf}, "
                f"plan probes {plan_nf}"
            )
        return "; ".join(lines)


def audit_fanout(
    selected_hypotheses: list[Hypothesis],
    plans: list[FalsificationPlan],
) -> FanoutAuditResult:
    """Compute the fan-out audit over (hypotheses, plans).

    Pure function: no logging, no PhaseTrace creation. Caller decides
    how to surface the findings (orchestrator emits log warnings + a
    synthetic PhaseTrace; future callers may surface differently).
    """
    plans_by_id = {p.hypothesis_id: p for p in plans}
    hypothesis_ids = {h.id for h in selected_hypotheses}
    plan_ids = set(plans_by_id.keys())

    hyps_without_plan = [
        h for h in selected_hypotheses if h.id not in plan_ids
    ]
    plans_without_hyp = [pid for pid in plan_ids if pid not in hypothesis_ids]
    nf_mismatches: list[tuple[str, str, str]] = []
    for h in selected_hypotheses:
        plan = plans_by_id.get(h.id)
        if plan is not None and plan.primary_suspect_nf != h.primary_suspect_nf:
            nf_mismatches.append(
                (h.id, h.primary_suspect_nf, plan.primary_suspect_nf)
            )

    return FanoutAuditResult(
        selected_hypotheses=selected_hypotheses,
        plans=plans,
        hyps_without_plan=hyps_without_plan,
        plans_without_hyp=plans_without_hyp,
        nf_mismatches=nf_mismatches,
    )


# ============================================================================
# Decision A — lint_ig_plan: A1 (partner probe) + A2 (IG-statement linter)
# ============================================================================

# Tools whose readings compose contributions from more than one element.
# Sub-check A1 fires when a probe using one of these has empty
# `conflates_with`, OR when a probe with non-empty `conflates_with` lacks
# at least one other probe in the same plan that could serve as its
# disambiguation partner.
_COMPOSITIONAL_TOOLS: frozenset[str] = frozenset({
    "measure_rtt",
})


# Sub-check A2 IG-specific extensions on top of the shared base
# blocklist. These phrases are how the IG re-introduces layer scope
# that NA's statement left out:
#
#   * `<NF>-internal fault` / `<NF>-internal X` — the canonical pattern
#     observed in run_20260501_012613. Parameterized over the known NF
#     list to catch the NF-name variants without relying on a generic
#     "internal" hit (which the base list already has, but is too noisy
#     when it stands alone).
#   * `application-layer`, `application layer`, `process-level`,
#     `user-space-only` — IG-favored ways to scope the mechanism to the
#     app layer at the named NF.
#   * `kernel-only`, `transport-only` — the inverse: pre-committing to
#     transport when the hypothesis didn't.
#
# The NF-parameterized list is built lazily so we don't pay for it at
# import time and so the known NF list is always pulled fresh from the
# Pydantic Literal (single source of truth).
def _build_ig_specific_patterns() -> list[tuple[str, re.Pattern[str]]]:
    """Build IG-specific regex patterns. Combines the small set of
    layer-scoping phrases with NF-parameterized `<NF>-internal X`
    patterns over every known NF name from models._KnownNF."""
    patterns: list[tuple[str, re.Pattern[str]]] = [
        ("application-layer",
            re.compile(r"\bapplication[\- ]layer\b", re.IGNORECASE)),
        ("process-level",
            re.compile(r"\bprocess[\- ]level\b", re.IGNORECASE)),
        ("user-space-only",
            re.compile(r"\buser[\- ]space[\- ]only\b", re.IGNORECASE)),
        ("kernel-only",
            re.compile(r"\bkernel[\- ]only\b", re.IGNORECASE)),
        ("transport-only",
            re.compile(r"\btransport[\- ]only\b", re.IGNORECASE)),
    ]

    # Pull the known NF list from the Hypothesis schema. Importing here
    # rather than at module top avoids a hard dependency cycle if the
    # models module ever needs to import from guardrails.
    from typing import get_args

    from ..models import Hypothesis as _H

    nf_field = _H.model_fields["primary_suspect_nf"]
    nf_names: list[str] = []
    try:
        nf_names = list(get_args(nf_field.annotation))
    except Exception:
        pass

    # `<NF>-internal fault`, `<NF>-internal X`, `<NF>-internal` —
    # parameterized per NF. Each becomes one labeled pattern so the
    # rejection reason names the exact NF the IG layer-scoped.
    for nf in nf_names:
        nf_escaped = re.escape(nf)
        patterns.append((
            f"{nf}-internal fault",
            re.compile(rf"\b{nf_escaped}[\- ]internal fault\b", re.IGNORECASE),
        ))
        patterns.append((
            f"{nf}-internal",
            re.compile(rf"\b{nf_escaped}[\- ]internal\b", re.IGNORECASE),
        ))

    return patterns


_IG_SPECIFIC_PATTERNS: list[tuple[str, re.Pattern[str]]] = _build_ig_specific_patterns()

# Combined blocklist applied to IG `expected_if_hypothesis_holds` and
# `falsifying_observation` text. Order: IG-specific first (so
# NF-specific matches like "upf-internal fault" appear before the
# generic "internal" hit), then base patterns.
_IG_BLOCKLIST: list[tuple[str, re.Pattern[str]]] = (
    _IG_SPECIFIC_PATTERNS + BASE_PATTERNS
)


@dataclass
class _ProbeFinding:
    """One sub-check's finding on one probe of one plan."""
    plan_id: str
    plan_nf: str
    probe_index: int
    probe: FalsificationProbe
    # A1 findings:
    missing_conflates_with: bool = False
    no_partner_probe: bool = False
    # A2 findings: per-field hit lists. Empty list = clean for that field.
    expected_hits: list[str] = field(default_factory=list)
    falsifying_hits: list[str] = field(default_factory=list)

    @property
    def has_a1_finding(self) -> bool:
        return self.missing_conflates_with or self.no_partner_probe

    @property
    def has_a2_finding(self) -> bool:
        return bool(self.expected_hits) or bool(self.falsifying_hits)

    @property
    def has_any_finding(self) -> bool:
        return self.has_a1_finding or self.has_a2_finding


def lint_ig_plan(
    plan_set: FalsificationPlanSet,
) -> GuardrailResult[FalsificationPlanSet]:
    """Decision A — post-IG linter.

    Runs both sub-checks in one pass over the plan set. Returns PASS
    when no probe has any finding, REJECT otherwise. The rejection
    reason is structured per-probe so IG's resample sees exactly which
    probe of which plan failed which sub-check.

    A1 (partner-probe coverage) and A2 (mechanism-scoping linter) both
    contribute findings to the same `GuardrailResult`. The runner
    treats any finding as REJECT — IG must fix every flagged probe on
    resample. This avoids two separate REJECT cycles for what's
    structurally one round of feedback.
    """
    findings: list[_ProbeFinding] = []
    for plan in plan_set.plans:
        # A1: check each probe against the compositional-probe rules.
        for idx, probe in enumerate(plan.probes):
            f = _ProbeFinding(
                plan_id=plan.hypothesis_id,
                plan_nf=plan.primary_suspect_nf,
                probe_index=idx,
                probe=probe,
            )
            _apply_a1_checks(f, plan)
            _apply_a2_checks(f)
            if f.has_any_finding:
                findings.append(f)

    if not findings:
        return GuardrailResult(
            verdict=GuardrailVerdict.PASS,
            output=plan_set,
        )

    reason = _build_ig_rejection_reason(findings)
    notes = {
        "flagged_probes_count": len(findings),
        "per_probe": [
            {
                "plan_id": f.plan_id,
                "plan_nf": f.plan_nf,
                "probe_index": f.probe_index,
                "tool": f.probe.tool,
                "missing_conflates_with": f.missing_conflates_with,
                "no_partner_probe": f.no_partner_probe,
                "expected_hits": f.expected_hits,
                "falsifying_hits": f.falsifying_hits,
            }
            for f in findings
        ],
    }
    return GuardrailResult(
        verdict=GuardrailVerdict.REJECT,
        output=plan_set,
        reason=reason,
        notes=notes,
    )


def _apply_a1_checks(f: _ProbeFinding, plan: FalsificationPlan) -> None:
    """Sub-check A1 — partner-probe coverage for compositional probes.

    Two flag conditions:
      * Compositional tool with empty `conflates_with` → IG asserted
        false uniqueness or forgot to populate the field.
      * Compositional tool with non-empty `conflates_with` but no other
        compositional probe in the plan that could serve as its
        partner. Heuristic: at least one other probe in the same plan
        must use a compositional tool. PR 4 ships this approximation;
        a stricter "differs in the named NF" check requires the IG to
        emit `path_elements`, which is a schema change deferred.
    """
    probe = f.probe
    if probe.tool not in _COMPOSITIONAL_TOOLS:
        return

    if not probe.conflates_with:
        f.missing_conflates_with = True
        return

    # Has conflates_with — needs a partner. Look for any OTHER
    # compositional probe in the plan.
    others = [
        p for i, p in enumerate(plan.probes)
        if i != f.probe_index and p.tool in _COMPOSITIONAL_TOOLS
    ]
    if not others:
        f.no_partner_probe = True


def _apply_a2_checks(f: _ProbeFinding) -> None:
    """Sub-check A2 — mechanism-scoping linter on probe text fields."""
    probe = f.probe
    f.expected_hits = scan(probe.expected_if_hypothesis_holds, _IG_BLOCKLIST)
    f.falsifying_hits = scan(probe.falsifying_observation, _IG_BLOCKLIST)


def _build_ig_rejection_reason(findings: list[_ProbeFinding]) -> str:
    """Assemble the IG-facing rejection feedback. Per-probe breakdown
    grouped by plan, with the offending phrases / missing partners
    quoted, the required shape stated, and a per-probe example
    correction grounded in the plan's primary_suspect_nf."""
    parts: list[str] = [
        "Your previous FalsificationPlanSet was REJECTED by the post-IG "
        "linter. The linter enforces two structural rules on every plan:",
        "",
        "  (A1) Compositional probes (measure_rtt etc.) need a partner "
        "probe whose path differs in the hypothesis's primary suspect "
        "NF. Without one, the Investigator cannot localize which "
        "element owns any deviation seen by the first probe.",
        "  (A2) Probe `expected_if_hypothesis_holds` and "
        "`falsifying_observation` text must NOT scope the mechanism. "
        "Phrases like `<NF>-internal fault`, `application-layer`, "
        "`process-level`, etc. re-introduce the layer scope that the "
        "NA-side linter (Decision D) shut down at the hypothesis-"
        "statement stage. The Investigator interprets your "
        "expected/falsifying text literally, so layer scope here turns "
        "into a layer-mismatch DISPROVEN on what was the right NF.",
        "",
    ]

    # Group findings by plan_id for readability.
    by_plan: dict[str, list[_ProbeFinding]] = {}
    for f in findings:
        by_plan.setdefault(f.plan_id, []).append(f)

    for plan_id in sorted(by_plan.keys()):
        plan_findings = by_plan[plan_id]
        plan_nf = plan_findings[0].plan_nf
        parts.append(
            f"Plan `{plan_id}` (primary_suspect_nf={plan_nf}):"
        )
        for f in plan_findings:
            parts.append(
                f"  Probe #{f.probe_index} (tool={f.probe.tool}):"
            )
            if f.missing_conflates_with:
                parts.append(
                    f"    [A1] Compositional tool `{f.probe.tool}` "
                    f"with empty `conflates_with`. Either this probe's "
                    f"reading uniquely identifies {plan_nf} (in which "
                    f"case the tool isn't really compositional and you "
                    f"should pick a non-compositional tool), or you "
                    f"need to populate `conflates_with` with the other "
                    f"elements whose contribution could produce the "
                    f"same reading AND add a partner probe whose path "
                    f"differs in {plan_nf}."
                )
            if f.no_partner_probe:
                parts.append(
                    f"    [A1] Compositional tool with non-empty "
                    f"`conflates_with` but no partner probe in the "
                    f"plan. Add a second compositional probe whose "
                    f"path shares some elements with this one and "
                    f"differs in {plan_nf}, so the two readings "
                    f"together localize which element owns the "
                    f"deviation."
                )
            if f.expected_hits:
                hits = ", ".join(f"'{h}'" for h in f.expected_hits)
                parts.append(
                    f"    [A2] `expected_if_hypothesis_holds` "
                    f"contained mechanism-scoping phrase(s): {hits}"
                )
                parts.append(
                    f"      Offending text: \"{f.probe.expected_if_hypothesis_holds}\""
                )
            if f.falsifying_hits:
                hits = ", ".join(f"'{h}'" for h in f.falsifying_hits)
                parts.append(
                    f"    [A2] `falsifying_observation` "
                    f"contained mechanism-scoping phrase(s): {hits}"
                )
                parts.append(
                    f"      Offending text: \"{f.probe.falsifying_observation}\""
                )
            if f.has_a2_finding:
                bad, good = _build_a2_example_correction(f)
                parts.append(f"    Required shape: clean text that names the OBSERVABLE the probe checks for, without scoping the layer.")
                parts.append(f"    Example correction:")
                parts.append(f"      Bad:  \"{bad}\"")
                parts.append(f"      Good: \"{good}\"")
        parts.append("")

    parts.append(
        "Resample with corrected probes. For A1: add the missing "
        "partner probe or populate `conflates_with`. For A2: rewrite "
        "the flagged text to name what the probe is OBSERVING (a "
        "metric value, a counter rate, a packet count) without naming "
        "WHICH LAYER of the NF the observation came from. The "
        "Investigator will localize the layer; you don't need to."
    )

    return "\n".join(parts)


def _build_a2_example_correction(f: _ProbeFinding) -> tuple[str, str]:
    """Return a (bad, good) example pair for one probe's A2 finding.

    `bad` quotes the worst-flagged field (falsifying takes precedence
    over expected since that's where the IG most often inverts the test
    framing). `good` is a generic clean rewrite anchored on the plan's
    NF — concrete enough for IG to imitate, generic enough to not
    pre-commit to a specific observable.
    """
    bad: str
    if f.falsifying_hits:
        bad = f.probe.falsifying_observation
    else:
        bad = f.probe.expected_if_hypothesis_holds

    nf = f.plan_nf
    good = (
        f"The probe's reading is inconsistent with {nf} being the source "
        f"(e.g. the metric stays at its healthy baseline, or the loss is "
        f"observed on a path that does not traverse {nf})."
    )
    return bad, good
