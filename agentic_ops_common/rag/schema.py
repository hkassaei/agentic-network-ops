"""RAG corpus schema — one retrievable case + its embedded representation.

Two Pydantic models live here:

  `FlagSummary`    — a compact view of one anomaly-screener flag row.
                     Three load-bearing fields (metric, direction,
                     severity) define the retrieval signature; the rest
                     are render-only.

  `RetrievedCase`  — one episode rendered as a retrievable unit. Holds
                     the case's identity (file path, agent version,
                     timestamp), scenario, ground truth, screener
                     output, downstream agent diagnosis, and score.

The two render methods on `RetrievedCase` formalize the seam between
schema and downstream RAG steps:

  `retrieval_key_text()`   — the string R2 embeds into the vector store.
                              Built from the case's flag signatures plus
                              weak suffixes for scenario + classifier.
  `render_for_prompt(...)` — the markdown chunk R4 injects into agent
                              prompts at retrieval time.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class FlagSummary(BaseModel):
    """One row from the anomaly screener's flagged metrics.

    The fields are deliberately a strict subset of what the screener
    emits (see `agentic_ops_common.anomaly.screener.AnomalyFlag`):
    only what's needed to build the retrieval key and render the case.
    Current / learned / anomaly_score are kept as Optional because v5
    episodes don't record screener output and older v6 markdown
    formats vary in how they spell the value pair.
    """

    metric: str = Field(
        ...,
        description=(
            "Metric name as the screener emits it — e.g. "
            "'rtpengine_loss_ratio' (after splitting off the "
            "'derived'/'normalized' component prefix) or "
            "'cdp:average_response_time'."
        ),
    )
    component: str = Field(
        ...,
        description=(
            "Component name as the screener emits it — typically the NF "
            "('icscf', 'rtpengine') or the preprocessor namespace "
            "('derived', 'normalized', 'context')."
        ),
    )
    direction: str = Field(
        ...,
        description="One of: spike | drop | shift | zero.",
    )
    severity: str = Field(
        ...,
        description="HIGH | MEDIUM | LOW.",
    )
    current: Optional[float] = None
    learned_normal: Optional[float] = None
    anomaly_score: Optional[float] = None

    def signature(self) -> str:
        """Compact retrieval-key form: ``component.metric:direction:severity``.

        This is the string that gets concatenated into the case's
        retrieval-key text. Stable across agent versions because it
        excludes value pairs (which vary with traffic conditions) and
        bucket information (which is v7-specific).
        """
        return f"{self.component}.{self.metric}:{self.direction}:{self.severity}"


class RetrievedCase(BaseModel):
    """One retrievable unit in the RAG case corpus.

    Built from a single chaos-episode file (`run_*.json` preferred,
    `run_*.md` fallback). Carries everything a downstream RAG step
    needs to embed it into a vector store (`retrieval_key_text`) and
    to render it back into an agent prompt at retrieval time
    (`render_for_prompt`).

    Field set is conservative: optional everywhere except the fields
    we always need to identify and validate the case. `score_pct` is
    required because R2's corpus filter (`score >= 80`) reads it; a
    parseable episode without a score isn't usable as a retrievable
    case and the parser should return `None` for it.
    """

    # ── Identity / provenance ────────────────────────────────────────
    case_id: str = Field(
        ...,
        description=(
            "Deterministic identifier — '<agent_version>/<episode_id>'. "
            "Stable across re-indexing so FAISS upserts replace in place."
        ),
    )
    source_episode_path: str = Field(
        ...,
        description=(
            "Absolute path to the episode file the case was parsed "
            "from. Rendered into the prompt for provenance so EV "
            "can audit the case the NA cited."
        ),
    )
    agent_version: Literal["v5", "v6", "v7"] = Field(
        ...,
        description=(
            "Inferred from the episode-file path "
            "(`.../agentic_ops_v{N}/docs/agent_logs/...`)."
        ),
    )
    run_timestamp: Optional[datetime] = None
    parsed_from: Literal["json", "markdown"] = Field(
        ...,
        description=(
            "Which file the parser actually read. JSON is preferred; "
            "markdown fallback is rare and signals reduced field coverage."
        ),
    )

    # ── Scenario context ─────────────────────────────────────────────
    scenario_name: str = Field(
        ...,
        description="Human-readable scenario name, e.g. 'Call Quality Degradation'.",
    )
    scenario_category: Optional[str] = Field(
        default=None,
        description="Scenario category: 'network' | 'ims' | 'data_layer' | …",
    )
    fault_injected: list[dict] = Field(
        default_factory=list,
        description=(
            "Raw fault descriptors from the chaos framework — "
            "[{fault_type, target, params, mechanism, ...}, ...]."
        ),
    )

    # ── Ground truth (from `rca_label`) ──────────────────────────────
    ground_truth_failure_domain: Optional[str] = None
    ground_truth_affected_components: list[str] = Field(default_factory=list)
    ground_truth_severity: Optional[str] = None
    ground_truth_root_cause_text: Optional[str] = Field(
        default=None,
        description=(
            "Free-text root cause description from rca_label.root_cause. "
            "One-paragraph framing of what was actually broken."
        ),
    )

    # ── Anomaly screener output (load-bearing for retrieval key) ─────
    anomaly_top_flags: list[FlagSummary] = Field(
        default_factory=list,
        description=(
            "The flags the screener surfaced for this episode. Empty "
            "for v5 (no screener output recorded). For v7, sourced "
            "from symptom_classification's pre-bucketed flag lists; "
            "for v6, regex-extracted from the anomaly_report markdown."
        ),
    )
    overall_anomaly_score: Optional[float] = None
    anomaly_bucket: Optional[tuple[int, int]] = Field(
        default=None,
        description="v7-only — the (calls_active, registration_in_progress) bucket.",
    )

    # ── Classifier / walker output (v7 only) ─────────────────────────
    classifier_label: Optional[Literal[
        "transport_layer", "application_layer", "mixed"
    ]] = None
    walker_localized: Optional[bool] = None
    walker_attributed_hop_node: Optional[str] = None
    resolved_flow_id: Optional[str] = None

    # ── Agent's diagnosis ────────────────────────────────────────────
    diagnosis_summary: Optional[str] = None
    diagnosis_primary_suspect_nf: Optional[str] = None
    diagnosis_verdict_kind: Optional[str] = Field(
        default=None,
        description="confirmed | promoted | inconclusive | localized — agent-emitted.",
    )
    diagnosis_confidence: Optional[Literal["high", "medium", "low"]] = None

    # ── Scoring (corpus-filter signal) ───────────────────────────────
    score_pct: int = Field(
        ...,
        ge=0, le=100,
        description=(
            "Score as integer percent (0-100). Source: rca scoring's "
            "`total_score` field (originally on a 0.0-1.0 scale)."
        ),
    )
    fault_type_correct: Optional[bool] = None

    # ── Cost ─────────────────────────────────────────────────────────
    total_tokens: Optional[int] = None

    # ─────────────────────────────────────────────────────────────────
    # Render methods — schema/usage seam for R2 (embedding) + R4 (prompt)
    # ─────────────────────────────────────────────────────────────────

    def retrieval_key_text(self) -> str:
        """The string R2 embeds into the vector store.

        Layout:

          <flag signature 1>
          <flag signature 2>
          ...
          scenario: <scenario_name>
          classifier: <classifier_label or 'unknown'>

        Flag signatures are the load-bearing similarity signal; the
        scenario and classifier suffixes are weak tie-breakers for
        cases whose flag patterns are identical but routing context
        differs (e.g. a screener pattern that classifies `transport`
        in v7 but had no classifier in v6).
        """
        lines: list[str] = []
        for flag in self.anomaly_top_flags:
            lines.append(flag.signature())
        lines.append(f"scenario: {self.scenario_name}")
        lines.append(f"classifier: {self.classifier_label or 'unknown'}")
        return "\n".join(lines)

    def render_for_prompt(self, verbosity: str = "default") -> str:
        """The markdown chunk R4 injects into an agent prompt.

        Verbosity levels:

          'compact'  — one-paragraph summary suitable for many cases
                       packed into a single prompt section.
          'default'  — multi-line semantic block; ~250 tokens. Right
                       fit when injecting 3-5 cases.
          'full'     — every populated field, including raw flag rows.
                       Reserved for diagnostic / audit views.

        Every render includes the source episode path as a citation
        so the EvidenceValidator can audit any prior-case the NA
        references.
        """
        if verbosity == "compact":
            return self._render_compact()
        if verbosity == "full":
            return self._render_full()
        return self._render_default()

    # ── Internal renderers ──────────────────────────────────────────

    def _render_compact(self) -> str:
        flag_sigs = ", ".join(f.signature() for f in self.anomaly_top_flags[:5])
        if len(self.anomaly_top_flags) > 5:
            flag_sigs += f", … (+{len(self.anomaly_top_flags) - 5} more)"
        gt_nf = (
            ", ".join(self.ground_truth_affected_components)
            if self.ground_truth_affected_components else "?"
        )
        return (
            f"**{self.case_id}** ({self.agent_version}, score "
            f"{self.score_pct}%) — scenario `{self.scenario_name}`. "
            f"Flags: {flag_sigs or '(none recorded)'}. "
            f"Ground truth: `{gt_nf}` "
            f"({self.ground_truth_failure_domain or '?'}). "
            f"Agent picked: `{self.diagnosis_primary_suspect_nf or '?'}` "
            f"({self.diagnosis_verdict_kind or '?'})."
        )

    def _render_default(self) -> str:
        lines: list[str] = []
        lines.append(f"### Prior case `{self.case_id}` (score {self.score_pct}%)")
        lines.append(
            f"- **Scenario:** {self.scenario_name}"
            + (f" ({self.scenario_category})" if self.scenario_category else "")
        )
        if self.ground_truth_affected_components:
            lines.append(
                f"- **Ground truth:** `{', '.join(self.ground_truth_affected_components)}` "
                f"(failure_domain={self.ground_truth_failure_domain or '?'}, "
                f"severity={self.ground_truth_severity or '?'})"
            )
        if self.anomaly_top_flags:
            sigs = [f.signature() for f in self.anomaly_top_flags[:8]]
            lines.append(f"- **Screener flags:** {', '.join(sigs)}")
        if self.classifier_label:
            lines.append(f"- **Classifier label:** `{self.classifier_label}`")
        if self.walker_localized is not None:
            outcome = (
                f"localized at `{self.walker_attributed_hop_node}`"
                if self.walker_localized else "null localization"
            )
            lines.append(f"- **Walker:** {outcome}")
        if self.diagnosis_primary_suspect_nf or self.diagnosis_verdict_kind:
            lines.append(
                f"- **Agent diagnosis:** primary_suspect=`"
                f"{self.diagnosis_primary_suspect_nf or '?'}`, "
                f"verdict_kind=`{self.diagnosis_verdict_kind or '?'}`, "
                f"confidence={self.diagnosis_confidence or '?'}"
            )
        lines.append(f"- *source: {self.source_episode_path}*")
        return "\n".join(lines)

    def _render_full(self) -> str:
        # Pydantic v2: model_dump_json is the canonical full-form view.
        # Wrapped in a fenced code block for prompt-injection safety.
        return (
            f"### Prior case `{self.case_id}` (full payload)\n"
            "```json\n"
            f"{self.model_dump_json(indent=2)}\n"
            "```"
        )
