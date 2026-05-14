"""Compound-verdict consistency guardrails for Phase 7 Synthesis.

When the classifier labels an episode `mixed` (per task #63's rule),
the v7 orchestrator runs BOTH the path walker AND the application-layer
pipeline and feeds both bundles into Synthesis. Synthesis can then emit
`verdict_kind=compound` to surface multiple distinct root causes that
span layers — see ADR `multi_fault_orchestration.md`.

The unified Synthesis prompt has a branch-select directive that picks
the `compound` rules when both inputs are populated. Prompt rules are
soft; the LLM has been observed to:

  - Emit `verdict_kind=compound` when only one branch's evidence was
    available (no walker, or no NA — i.e. degenerate to `localized` /
    application-layer rules).
  - Emit `verdict_kind=compound` with an empty `additional_root_causes`
    list — carries no compound information; should be `localized`.
  - Fabricate `RootCause` entries whose `evidence_source` points at
    nothing real in the input bundle.

These two guardrails are the mechanical post-emit invariants:

  `lint_compound_verdict_consistency`
      If `verdict_kind == "compound"`, both `path_walk_report.is_localized=True`
      AND `network_analysis` must be populated. Either missing → REJECT.

  `lint_compound_additional_causes`
      If `verdict_kind == "compound"`:
        - `additional_root_causes` must be non-empty (otherwise the
          verdict carries no compound information).
        - Each entry must not duplicate `primary_suspect_nf`.
        - Each entry's `evidence_source` must be one of the three
          documented sources. (The Pydantic Literal enforces this at
          parse time; we re-check defensively here.)

REJECT on any failure with a resample directive that names what to do.

PASS on every non-compound verdict_kind — these guardrails are the
compound branch's analogue of `lint_localized_verdict_consistency`.
"""

from __future__ import annotations

from typing import Any, Optional

from .base import GuardrailResult, GuardrailVerdict
from ..models import DiagnosisReport


_VALID_EVIDENCE_SOURCES = {"path_walk", "investigator", "anomaly_screener"}


def lint_compound_verdict_consistency(
    report: DiagnosisReport,
    path_walk_report: Optional[dict[str, Any]],
    network_analysis: Any,
) -> GuardrailResult[DiagnosisReport]:
    """Reject a `compound`-verdict diagnosis when one of the two bundles is absent.

    Args:
      report: the LLM-emitted DiagnosisReport.
      path_walk_report: the walker's report dict from
        `state["path_walk_report"]`. None when Phase 0.6 was skipped or
        the walker null-localized.
      network_analysis: the application-layer pipeline's NA output. Any
        truthy value (dict or non-empty string) means the application-
        layer bundle was produced and is available for compound
        synthesis. None or empty means the application-layer pipeline
        did not run — `compound` is invalid then.

    Returns PASS when `verdict_kind != "compound"` (this guardrail is
    a no-op for every other verdict_kind). Returns PASS when
    verdict_kind=compound AND both bundles are populated. Returns
    REJECT in every other compound case.
    """
    if report.verdict_kind != "compound":
        return GuardrailResult(verdict=GuardrailVerdict.PASS, output=report)

    walker_ok = bool(path_walk_report and path_walk_report.get("is_localized"))
    na_ok = bool(network_analysis)

    if walker_ok and na_ok:
        return GuardrailResult(verdict=GuardrailVerdict.PASS, output=report)

    # REJECT — figure out which side is missing and tell the resampler
    # what to do.
    if not walker_ok and not na_ok:
        reason = (
            "You emitted `verdict_kind=\"compound\"` but NEITHER the "
            "path-walk report NOR the application-layer pipeline produced "
            "evidence. `compound` is reserved for cases where BOTH branches "
            "fired and produced distinct root causes. Re-emit with "
            "`verdict_kind=\"inconclusive\"` and `primary_suspect_nf=null`."
        )
        guidance = "inconclusive"
    elif not walker_ok:
        reason = (
            "You emitted `verdict_kind=\"compound\"` but the path-walker "
            "did not localize a transport-layer fault (no kernel/element "
            "counter attribution). `compound` requires walker localization "
            "on the primary slot. The application-layer pipeline ran and "
            "produced hypotheses; re-emit with the application-layer "
            "rules (`verdict_kind` in {confirmed, promoted, inconclusive}), "
            "picking `primary_suspect_nf` from the candidate pool."
        )
        guidance = "application-layer"
    else:
        # NA bundle missing → compound impossible; degrade to localized.
        reason = (
            "You emitted `verdict_kind=\"compound\"` but the "
            "application-layer pipeline did not run (no `network_analysis` "
            "bundle in your input). `compound` requires both the walker "
            "AND the application-layer pipeline to have produced evidence. "
            "The walker localized — re-emit with `verdict_kind=\"localized\"` "
            "using the path-walk's attribution as the primary slot. Remove "
            "the `additional_root_causes` payload."
        )
        guidance = "localized"

    return GuardrailResult(
        verdict=GuardrailVerdict.REJECT,
        output=report,
        reason=reason,
        notes={
            "submitted_verdict_kind": report.verdict_kind,
            "submitted_primary_suspect_nf": report.primary_suspect_nf,
            "walker_localized": walker_ok,
            "network_analysis_present": na_ok,
            "rejection_branch": guidance,
        },
    )


def lint_compound_additional_causes(
    report: DiagnosisReport,
) -> GuardrailResult[DiagnosisReport]:
    """Reject a `compound`-verdict diagnosis whose `additional_root_causes` is malformed.

    Returns PASS when `verdict_kind != "compound"`. Returns PASS when
    the list is non-empty, contains no entry duplicating
    `primary_suspect_nf`, and every entry has a valid
    `evidence_source` (defense-in-depth — the Pydantic Literal also
    catches this at parse time).
    """
    if report.verdict_kind != "compound":
        return GuardrailResult(verdict=GuardrailVerdict.PASS, output=report)

    causes = report.additional_root_causes
    if not causes:
        return GuardrailResult(
            verdict=GuardrailVerdict.REJECT,
            output=report,
            reason=(
                "You emitted `verdict_kind=\"compound\"` but "
                "`additional_root_causes` is empty. The compound verdict "
                "carries no compound information then — it's equivalent "
                "to `localized`. Either:\n"
                "  - Populate `additional_root_causes` with at least one "
                "`RootCause` whose `primary_suspect_nf` differs from the "
                "primary slot, citing real evidence from the input bundle.\n"
                "  - Or re-emit with `verdict_kind=\"localized\"` if the "
                "walker is the only branch with strong evidence."
            ),
            notes={
                "submitted_verdict_kind": report.verdict_kind,
                "additional_root_causes_count": 0,
            },
        )

    primary = report.primary_suspect_nf
    for cause in causes:
        if cause.primary_suspect_nf == primary:
            return GuardrailResult(
                verdict=GuardrailVerdict.REJECT,
                output=report,
                reason=(
                    f"`additional_root_causes` contains an entry "
                    f"`primary_suspect_nf={cause.primary_suspect_nf!r}` "
                    f"that duplicates the primary slot. Every entry in "
                    f"`additional_root_causes` MUST name a DIFFERENT NF "
                    f"from the primary. Drop the duplicate or replace it "
                    f"with a distinct contributing root cause."
                ),
                notes={
                    "submitted_verdict_kind": report.verdict_kind,
                    "primary_suspect_nf": primary,
                    "duplicate_nf": cause.primary_suspect_nf,
                },
            )

        if cause.evidence_source not in _VALID_EVIDENCE_SOURCES:
            return GuardrailResult(
                verdict=GuardrailVerdict.REJECT,
                output=report,
                reason=(
                    f"`additional_root_causes` entry for "
                    f"`{cause.primary_suspect_nf}` has "
                    f"`evidence_source={cause.evidence_source!r}` which is "
                    f"not one of the documented sources "
                    f"{sorted(_VALID_EVIDENCE_SOURCES)}. Pick the source "
                    f"that actually backs this entry in the input bundle: "
                    f"`path_walk` (a walker hop attribution), "
                    f"`investigator` (an Investigator verdict in the "
                    f"candidate pool), or `anomaly_screener` (an anomaly "
                    f"flag from Phase 0)."
                ),
                notes={
                    "submitted_verdict_kind": report.verdict_kind,
                    "invalid_evidence_source": cause.evidence_source,
                },
            )

    return GuardrailResult(verdict=GuardrailVerdict.PASS, output=report)
