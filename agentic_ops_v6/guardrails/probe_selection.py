"""Decision B — Typed probe selection from KB (PR 7).

Failure mode (per ADR Decision B): IG free-forms probes from LLM
priors instead of selecting from the KB-authored disambiguators that
exist for many metrics. The `find_chains_by_observable_metric` and
`disambiguators` machinery is in the prompt as a recommendation, but
IG often skips it. The result is probes that don't actually
discriminate the right hypotheses.

Canonical example (`run_20260501_213721_mongodb_gone`): h1 multi-shot
disagreement on `fivegs_pcffunction_pa_policyamassoreq` — shot 1 read
the cumulative counter as "12 succ / 12 req = no failures"; shot 2
read it as "cumulative-since-process-start, doesn't tell us about the
anomaly window." A KB-curated probe spec for this metric would have
explicitly framed the rate-window vs. cumulative-counter distinction
in `args_hint` and `expected_if_hypothesis_holds`, removing the
judgment call.

PR 7 ships the **hybrid version** of Decision B per the ADR's open
question: `select_probes(hypothesis, kb)` returns a list of
KB-sourced `ProbeCandidate` objects that the orchestrator injects
into IG's session state. IG sees the candidates as a recommended
source and is prompted to prefer them when applicable, but is NOT
prevented from authoring free-form probes when the KB has no
candidates for a given hypothesis (KB coverage is currently 29% for
`how_to_verify_live` and 18% for `disambiguators`, so strict-only
would force most hypotheses to fall through to no-plan).

Synchronous, no Neo4j coupling. Reads `MetricEntry.how_to_verify_live`
and `MetricEntry.disambiguators` from the in-memory `MetricsKB`.
Chain-lookup augmentation via `find_chains_by_observable_metric` is
deferred (would require async + Neo4j; same trade-off as PR 8.5's
KB-grounding deferral).

When KB coverage is gappy on a hypothesis's NF, `select_probes`
returns an empty list. The orchestrator surfaces this as "no KB
candidates" in the IG prompt block, which IG reads as license to
free-form. The empty-list signal also serves as the empirical KB
coverage audit the ADR called for: scenarios that consistently get
"no KB candidates" reveal which NFs need authoring next.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import get_args

from agentic_ops_common.metric_kb.models import MetricEntry, MetricsKB

from ..models import Hypothesis


# Investigator tool names — pulled fresh from the schema so we don't
# admit ProbeCandidates whose `tool` isn't actually in the
# Investigator's toolset (would cause Pydantic validation failure
# downstream when IG copies it into a FalsificationProbe).
def _known_investigator_tools() -> set[str]:
    """Return the set of valid `_InvestigatorTool` Literal values."""
    from typing import get_args as _get_args
    from ..models import FalsificationProbe
    tool_field = FalsificationProbe.model_fields["tool"]
    try:
        return set(_get_args(tool_field.annotation))
    except Exception:
        return set()


_INVESTIGATOR_TOOLS = _known_investigator_tools()


# Maximum candidates returned per hypothesis. The IG prompt has a
# limited attention budget; a curated short list is more useful
# than a long unfiltered one.
_MAX_CANDIDATES_PER_HYPOTHESIS = 8


@dataclass
class ProbeCandidate:
    """A KB-sourced probe spec ready for IG to copy into a
    `FalsificationProbe`.

    Mirrors the FalsificationProbe shape so IG can lift fields directly
    without re-deriving anything. The `source_metric` and
    `via` fields are traceability-only — they don't go into the
    final FalsificationProbe but are surfaced in the IG prompt
    so the agent (and human reviewers) can see WHICH KB entry
    authored each candidate.
    """
    tool: str
    args_hint: str
    expected_if_hypothesis_holds: str
    falsifying_observation: str
    conflates_with: list[str] = field(default_factory=list)
    # Traceability — not part of the FalsificationProbe schema.
    source_metric: str = ""  # e.g. "amf.gnb"
    via: str = ""            # "primary" or "disambiguator(<source>)"


def select_probes(
    hypothesis: Hypothesis,
    kb: MetricsKB,
    max_candidates: int = _MAX_CANDIDATES_PER_HYPOTHESIS,
) -> list[ProbeCandidate]:
    """Build a curated list of KB-sourced probe candidates for a
    hypothesis.

    Walk:
      1. The primary_suspect_nf's NFBlock — every metric with
         `how_to_verify_live` populated yields a candidate.
      2. Each primary-NF metric's `disambiguators` — for the metric
         each disambiguator points at, look it up across all NFBlocks
         and build another candidate from ITS `how_to_verify_live`.

    Deduplicate by (tool, args_hint). Filter out any candidate whose
    tool isn't in the Investigator's toolset (the IG schema enforces
    this). Truncate to `max_candidates`.

    Returns an empty list if the KB has no relevant entries — the
    orchestrator surfaces this to IG as "no KB candidates" so the
    agent knows to free-form.
    """
    nf = hypothesis.primary_suspect_nf
    nf_block = kb.metrics.get(nf)
    if nf_block is None:
        return []

    candidates: list[ProbeCandidate] = []
    seen_keys: set[tuple[str, str]] = set()

    def _add(c: ProbeCandidate) -> None:
        if c.tool not in _INVESTIGATOR_TOOLS:
            return
        key = (c.tool, c.args_hint)
        if key in seen_keys:
            return
        seen_keys.add(key)
        candidates.append(c)

    # Pass 1 — primary-NF metrics with how_to_verify_live.
    for metric_name, metric in nf_block.metrics.items():
        if metric.how_to_verify_live is None:
            continue
        c = _build_candidate(
            metric=metric,
            source_metric=f"{nf}.{metric_name}",
            via="primary",
        )
        if c is not None:
            _add(c)

    # Pass 2 — disambiguators surface other metrics that discriminate.
    # The `disambiguator.metric` field references a metric by id — we
    # try a few resolution paths to find it in the KB.
    for metric_name, metric in nf_block.metrics.items():
        for disamb in metric.disambiguators:
            target_entry, target_id = _resolve_metric(kb, disamb.metric)
            if target_entry is None or target_entry.how_to_verify_live is None:
                continue
            c = _build_candidate(
                metric=target_entry,
                source_metric=target_id,
                via=f"disambiguator(via {nf}.{metric_name})",
                separates_hint=disamb.separates,
            )
            if c is not None:
                _add(c)

    return candidates[:max_candidates]


def _resolve_metric(
    kb: MetricsKB,
    metric_id: str,
) -> tuple[MetricEntry | None, str]:
    """Look up a disambiguator's referenced metric.

    Disambiguator metric ids in YAML come in several shapes:
      - `<layer>.<nf>.<metric>` (e.g. `core.amf.ran_ue`)
      - `<nf>.<metric>` (e.g. `amf.ran_ue`)
      - bare `<metric>` (e.g. `ran_ue`)
    The KB's `get_metric` handles the first two; we add a bare-name
    fallback that scans all NFBlocks for the metric name.
    """
    entry = kb.get_metric(metric_id)
    if entry is not None:
        return entry, metric_id
    # Bare-name fallback — scan all NFBlocks for a metric with this name.
    bare = metric_id.split(".")[-1]
    for nf, block in kb.metrics.items():
        if bare in block.metrics:
            return block.metrics[bare], f"{nf}.{bare}"
    return None, metric_id


def _build_candidate(
    metric: MetricEntry,
    source_metric: str,
    via: str,
    separates_hint: str = "",
) -> ProbeCandidate | None:
    """Construct a ProbeCandidate from a MetricEntry's
    `how_to_verify_live` + `meaning` + `healthy` fields.

    Returns None if `how_to_verify_live` is missing (caller filtered
    this already, but defensive).
    """
    probing = metric.how_to_verify_live
    if probing is None:
        return None

    tool = probing.tool
    args_hint = probing.args_hint or ""

    expected = _build_expected_text(metric, source_metric)
    falsifying = _build_falsifying_text(metric, source_metric)

    # Traceability — append the disambiguator-separates hint to the
    # expected text when this candidate came from a disambiguator path.
    if separates_hint:
        expected = (
            f"{expected} "
            f"[disambiguator hint: {separates_hint}]"
        )

    return ProbeCandidate(
        tool=tool,
        args_hint=args_hint,
        expected_if_hypothesis_holds=expected,
        falsifying_observation=falsifying,
        conflates_with=[],  # populated by Decision A1 / the IG; PR 7 leaves empty
        source_metric=source_metric,
        via=via,
    )


def _build_expected_text(metric: MetricEntry, source_metric: str) -> str:
    """Construct the `expected_if_hypothesis_holds` text from
    MetricEntry.meaning fields.

    Uses spike / drop / zero text — whichever is non-empty — to give
    IG concrete framing for what the probe should observe when the
    hypothesis is true. Falls back to a generic "metric deviates from
    healthy" if no meaning text is authored.
    """
    parts: list[str] = [
        f"Probe reads `{source_metric}` (KB-authored verification path)."
    ]
    if metric.meaning is not None:
        spike = (metric.meaning.spike or "").strip()
        drop = (metric.meaning.drop or "").strip()
        zero = (metric.meaning.zero or "").strip()
        directional = []
        if spike:
            directional.append(f"spike: {spike}")
        if drop:
            directional.append(f"drop: {drop}")
        if zero:
            directional.append(f"zero: {zero}")
        if directional:
            parts.append(
                "If the hypothesis holds, expect a deviation matching "
                "one of: " + " | ".join(directional)
            )
        else:
            parts.append(
                "If the hypothesis holds, expect a deviation from the "
                "metric's healthy baseline."
            )
    else:
        parts.append(
            "If the hypothesis holds, expect a deviation from the "
            "metric's healthy baseline."
        )
    return " ".join(parts)


def _build_falsifying_text(metric: MetricEntry, source_metric: str) -> str:
    """Construct the `falsifying_observation` text from
    MetricEntry.healthy fields."""
    if metric.healthy is None:
        return (
            f"Probe reads `{source_metric}` and finds the metric within "
            "its expected baseline range."
        )
    parts: list[str] = []
    typical = getattr(metric.healthy, "typical_range", None)
    invariant = getattr(metric.healthy, "invariant", None)
    if typical:
        parts.append(f"value within typical range {typical}")
    if invariant:
        parts.append(f"invariant holds: {invariant}")
    if parts:
        return (
            f"Probe reads `{source_metric}` and finds: "
            + "; ".join(parts) + "."
        )
    return (
        f"Probe reads `{source_metric}` and finds the metric within "
        "its expected baseline range."
    )


# ============================================================================
# Rendering for IG prompt injection
# ============================================================================


def render_candidates_for_prompt(
    candidates_by_hypothesis: dict[str, list[ProbeCandidate]],
) -> str:
    """Render per-hypothesis ProbeCandidate lists as the structured
    text block IG sees in its `{probe_candidates}` template variable.

    Format chosen to be unambiguous and short — IG already reads
    thousands of lines of context; this stays compact while making
    the structural intent ("here are KB-curated probes you should
    prefer") visually prominent.
    """
    if not candidates_by_hypothesis:
        return "(no hypotheses)"

    lines: list[str] = []
    for hid, candidates in candidates_by_hypothesis.items():
        lines.append(f"### Candidates for `{hid}`")
        if not candidates:
            lines.append(
                "  (no KB-authored probe candidates for this hypothesis's "
                "primary_suspect_nf — KB coverage gap. Free-form your "
                "probes per the standard rules.)"
            )
            lines.append("")
            continue
        for i, c in enumerate(candidates, 1):
            lines.append(
                f"  {i}. `{c.tool}` — args_hint: \"{c.args_hint}\""
            )
            lines.append(f"     source: {c.source_metric} (via {c.via})")
            lines.append(f"     expected_if_hypothesis_holds: {c.expected_if_hypothesis_holds}")
            lines.append(f"     falsifying_observation: {c.falsifying_observation}")
        lines.append("")

    return "\n".join(lines)
