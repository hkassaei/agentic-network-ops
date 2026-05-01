"""Phase 5 fan-out audit — surface silent plan-drops and NF mismatches.

Original failure: run_20260430_013055_gnb_radio_link_failure had NA
produce 1 hypothesis (h1 nr_gnb) and IG produce 3 plans (h1, h2, h3 —
re-anchored on the correlation engine's H1/H2/H3 hypotheses, all
targeting amf instead of nr_gnb). The orchestrator ran 1 investigator
paired with a cross-NF-mismatched plan, and silently dropped the other
2 IG plans because no hypothesis matched their ids. None of this was
logged. The dropped plans represented LLM work that was paid for and
discarded; the NF mismatch produced an investigator verdict that probed
the wrong NF for the wrong hypothesis.

This audit covers three cases:
  1. Hypotheses without a matching plan — caller treats these as
     INCONCLUSIVE in Phase 5; summarized here for visibility.
  2. Plans without a matching hypothesis — silent drops. Each represents
     wasted IG output and possibly a sign that IG mis-read its inputs.
  3. NF mismatch between a hypothesis and its plan — the plan probes a
     different component than the hypothesis names.

The audit is structural / deterministic: it only inspects the typed
hypothesis and plan objects. It does not call any LLM. The orchestrator
consumes the result by emitting log warnings and writing a synthetic
PhaseTrace whose `output_summary` carries the findings into the
recorder.

PR 1 lifts the audit out of the orchestrator with no semantic change.
Decision A in `docs/ADR/structural_guardrails_for_llm_pipeline.md` will
extend this module with the partner-probe / triangulation checks that
today live as prose rules in the IG prompt.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..models import FalsificationPlan, Hypothesis


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
