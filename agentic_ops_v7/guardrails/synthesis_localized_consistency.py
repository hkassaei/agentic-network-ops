"""Localized-verdict consistency guardrail for Phase 7 Synthesis.

The unified Synthesis LLM agent reads one prompt that can produce four
verdict kinds: `confirmed`, `promoted`, `inconclusive`, `localized`.
The `localized` branch is reserved for transport-layer faults that the
deterministic path walker (Phase 0.6) has actually attributed to a
specific hop. The LLM is told this via the prompt's branch-select
directive — but prompt rules are soft, and the model has been observed
to emit `verdict_kind=localized` with completely fabricated kernel-
counter evidence even when:

  - The orchestrator never engaged Phase 0.6 (application-layer route).
  - Phase 0.6 ran but the walker returned `is_localized=False`
    (null-localization → fall-through to application-layer pipeline).

This guardrail makes the constraint mechanical. It runs AFTER the LLM
emits a `DiagnosisReport` and BEFORE the report is accepted into the
chaos episode log. The check is one structural invariant:

  If `report.verdict_kind == "localized"`, then `path_walk_report`
  must be present AND `path_walk_report["is_localized"] == True`.

Anything else is a hallucination — the LLM is inventing a localized
verdict that has no real path-walk attribution behind it. REJECT with
a directive that tells the resample what to do.

This is `pool_membership`'s analogue for the localized branch: pool
membership enforces the application-layer verdict-kind invariants;
this guardrail enforces the localized verdict-kind invariant. Both
are mechanical post-emit checks.
"""

from __future__ import annotations

from typing import Any, Optional

from .base import GuardrailResult, GuardrailVerdict
from ..models import DiagnosisReport


def lint_localized_verdict_consistency(
    report: DiagnosisReport,
    path_walk_report: Optional[dict[str, Any]],
) -> GuardrailResult[DiagnosisReport]:
    """Reject a `localized`-verdict diagnosis when the walker did not localize.

    Args:
      report: the LLM-emitted DiagnosisReport.
      path_walk_report: the path-walk report dict from `state["path_walk_report"]`.
        `None` when Phase 0.6 was skipped entirely (application-layer
        classification). The dict carries `is_localized: bool` and
        `first_attributed_hop: dict | None`.

    Returns PASS when:
      - verdict_kind is not `localized` (irrelevant — application-layer
        verdicts are governed by `synthesis_pool` and `confidence_cap`).
      - verdict_kind is `localized` AND the walker actually localized.

    Returns REJECT when:
      - verdict_kind is `localized` AND `path_walk_report` is None
        (the orchestrator never ran the walker — pure hallucination).
      - verdict_kind is `localized` AND `path_walk_report["is_localized"]`
        is False (the walker ran but null-localized; falling through to
        the application-layer pipeline means a localized verdict is
        invalid here).
    """
    if report.verdict_kind != "localized":
        return GuardrailResult(verdict=GuardrailVerdict.PASS, output=report)

    if path_walk_report is None:
        return GuardrailResult(
            verdict=GuardrailVerdict.REJECT,
            output=report,
            reason=(
                "You emitted `verdict_kind=\"localized\"` but the orchestrator "
                "did not run the transport-layer path walk for this episode. "
                "The `localized` verdict is reserved for cases where Phase 0.6's "
                "deterministic walker attributed a fault to a specific hop "
                "(`is_localized=True` with a populated `first_attributed_hop`). "
                "On the application-layer branch (which produced your input "
                "bundle), the valid verdict_kinds are `confirmed`, `promoted`, "
                "or `inconclusive`. Re-emit with one of those, picking your "
                "primary_suspect_nf from the candidate pool above, and "
                "removing any `localization` payload from the report."
            ),
            notes={
                "submitted_verdict_kind": report.verdict_kind,
                "submitted_primary_suspect_nf": report.primary_suspect_nf,
                "path_walk_engaged": False,
            },
        )

    if not path_walk_report.get("is_localized"):
        attribution = (path_walk_report.get("first_attributed_hop") or {}).get("node")
        return GuardrailResult(
            verdict=GuardrailVerdict.REJECT,
            output=report,
            reason=(
                "You emitted `verdict_kind=\"localized\"` but Phase 0.6's "
                "path walker returned null-localization — it walked the "
                "implicated flow and no hop's transport-layer telemetry "
                "attributed the fault (no kernel qdisc drops, no interface "
                "errors, no link rate-diff anomaly). The orchestrator fell "
                "through to the application-layer pipeline, which is the "
                "input bundle you are reading right now. Re-emit with "
                "`verdict_kind` in {confirmed, promoted, inconclusive} "
                "per the application-layer rules. Do not invent kernel "
                "counter evidence — if a hop had attributed the fault, "
                "the orchestrator would have routed to the localized-only "
                f"Synthesis path and your input bundle would contain a "
                f"populated Path-Walk Report. (Walker first_attributed_hop: "
                f"{attribution or 'None'}.)"
            ),
            notes={
                "submitted_verdict_kind": report.verdict_kind,
                "submitted_primary_suspect_nf": report.primary_suspect_nf,
                "path_walk_engaged": True,
                "path_walk_is_localized": False,
            },
        )

    # localized with a localized walker → consistent.
    return GuardrailResult(verdict=GuardrailVerdict.PASS, output=report)
