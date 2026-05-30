"""Episode → RetrievedCase parser.

Walks chaos-episode files under any `docs/agent_logs/` directory and
produces `RetrievedCase` instances. JSON is the source of truth;
markdown fallback exists only for episodes where the paired JSON is
missing or unreadable.

Per-agent-version parsing rules:

  v7  — symptom_classification carries pre-bucketed structured flags
        (transport_flags / application_flags / ambiguous_flags) plus
        kb_metric_id. Richest source.
  v6  — anomaly_report is a markdown string. Regex-extract metric,
        direction, severity. Optional current / learned_normal value
        pairs are parsed when present.
  v5  — challenge_result is minimal (no screener output). `anomaly_top_flags`
        is empty; cases are still usable for scenario-scoped retrieval.

Skip rule: a case is dropped (parser returns None) when the score
cannot be extracted. Without a score we can't responsibly include the
case in the corpus (R2's corpus filter relies on `score_pct`).
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Optional

from .schema import FlagSummary, RetrievedCase

log = logging.getLogger("agentic_ops_common.rag.parser")


# Canonical NF allowlist used to filter primary-suspect extractions from
# free-text diagnosis prose. Mirrors `agentic_ops_v7/models.py:_KnownNF`
# — the parallel maintenance burden is accepted because:
#   - agentic_ops_common cannot import from agentic_ops_v7 (v7
#     self-containment rule, per ADR
#     path_anchored_probe_planning_for_transport_layer_faults.md).
#   - The failure mode if these drift is a *false negative* (a real NF
#     gets rejected → recorder shows `?`) — visible and debuggable.
#     The other direction (junk string accepted into corpus) would
#     silently corrupt the column the NA reads.
# Keep in sync manually when the v7 NF list changes.
_KNOWN_NFS: frozenset[str] = frozenset({
    "amf", "smf", "upf", "pcf", "ausf", "udm", "udr", "nrf",
    "pcscf", "icscf", "scscf", "pyhss", "rtpengine",
    "mongo", "mysql", "dns",
    "nr_gnb",
})


# Matches the v7 markdown renderer's pattern:
#   - **root_cause**: ... (primary_suspect_nf: `<nf>`)
# Used as the second fallback when extracting primary suspect from
# free-text diagnosis_text. v6 episodes never produced this pattern;
# v7 episodes always do via _render_diagnosis_report_to_markdown.
_V7_PRIMARY_SUSPECT_INLINE_RE = re.compile(
    r"primary_suspect_nf:\s*`([a-z0-9_]+)`",
    re.IGNORECASE,
)


# Matches a single affected_components markdown bullet:
#   - `<nf>`: Root Cause
# The role marker after the colon is matched case-insensitively but
# must start with "root cause" — "Root Cause", "ROOT CAUSE", and
# "Root Cause (notes...)" all match; "Secondary" and "Symptomatic" do
# not. Used as the FIRST fallback because it's the only path that
# works for both v6 and old-v7 episodes.
_AFFECTED_COMPONENT_ROOT_CAUSE_RE = re.compile(
    r"^\s*-\s*`([a-z0-9_]+)`\s*:\s*root\s+cause",
    re.IGNORECASE | re.MULTILINE,
)


def _extract_primary_suspect_from_diagnosis_text(text: str) -> Optional[str]:
    r"""Extract ``primary_suspect_nf`` from a free-text diagnosis blob.

    Two fallback strategies in order:

      1. **affected_components markdown list.** Scan for the first
         bullet tagged "Root Cause" — shape ``- `<nf>`: Root Cause``.
         Works for both v6 (whose `diagnosis_text` is the agent's only
         output) and old-v7 (pre-Bug-A, whose structured
         `diagnosis_report` was unset but `diagnosis_text` was
         rendered). Most reliable because the role-marker is
         structural-ish, not free prose.

      2. **v7 inline ``(primary_suspect_nf: `<nf>`)``.** v7's markdown
         renderer emits this suffix on the `root_cause` line. Catches
         old-v7 episodes where the affected_components list happened
         to be empty or the renderer skipped it. Will not match v6 —
         v6 had no inline suffix.

    Extracted name is filtered against ``_KNOWN_NFS`` so junk tokens
    (e.g. an LLM-emitted ``` `unknown`: Root Cause ```) don't poison
    the corpus. Returns ``None`` if neither fallback yielded a
    recognized NF.

    Background: Bug B in ``docs/next-work-package.md``. The default
    path in ``parse_episode`` reads ``diagnosis_report.primary_suspect_nf``
    directly; this helper is consulted only when that structured key
    is absent (v6 always, old-v7 until Bug-A's fix re-indexes).
    """
    if not text:
        return None

    # Fallback 1 — affected_components Root Cause entry.
    m = _AFFECTED_COMPONENT_ROOT_CAUSE_RE.search(text)
    if m:
        nf = m.group(1).lower()
        if nf in _KNOWN_NFS:
            return nf

    # Fallback 2 — v7 inline suffix.
    m = _V7_PRIMARY_SUSPECT_INLINE_RE.search(text)
    if m:
        nf = m.group(1).lower()
        if nf in _KNOWN_NFS:
            return nf

    return None


# ── Agent-version detection ──────────────────────────────────────────

_AGENT_VERSION_RE = re.compile(r"agentic_ops_(v\d+)")


def _detect_agent_version(path: Path) -> Optional[str]:
    """Infer agent version from the episode file's path.

    Looks for the `agentic_ops_vN` segment. Returns 'v5' / 'v6' / 'v7'
    or None if the path is unrecognized.
    """
    m = _AGENT_VERSION_RE.search(str(path))
    if not m:
        return None
    v = m.group(1)
    return v if v in ("v5", "v6", "v7") else None


# ── v6 anomaly_report markdown parser ────────────────────────────────

# Matches lines like:
#   - **`derived.rtpengine_loss_ratio`** ... (HIGH, spike) ...
#   - **`icscf.cdp:average_response_time`** (...) — current **75 ms** vs learned baseline **62 ms** (MEDIUM, shift)
#
# Captures: full_key (group 1), severity (group 2), direction (group 3).
# The full key is split on the first '.' into (component, metric).
_FLAG_LINE_RE = re.compile(
    r"- \*\*`([^`]+)`\*\*.*?\(([A-Z]+),\s*(\w+)\)",
    re.DOTALL,
)

# Optional value extraction — best-effort; some markdown variants omit
# units, scientific notation, or use commas. We tolerate failure.
_FLAG_VALUES_RE = re.compile(
    r"current\s+\*\*([0-9.+-eE]+)"
    r"(?:\s+[^\s*]+)?"
    r"\*\*"
    r"\s+vs\s+learned baseline\s+\*\*([0-9.+-eE]+)",
)

# `**ANOMALY DETECTED.** Overall anomaly score: 49.82 (per-bucket
# threshold: 28.18, context bucket (1, 1), ...)
_HEADER_RE = re.compile(
    r"Overall anomaly score:\s+([0-9.+-eE]+).*?"
    r"context bucket \((\d+),\s*(\d+)\)",
    re.DOTALL,
)

# Older v6 markdown uses a markdown table instead of bullet rows:
#   | Component | Metric | Current | Learned Normal | Severity |
#   |-----------|--------|---------|---------------|----------|
#   | normalized | upf.gtp_indatapktn3upf_per_ue | 0.00 | 3.42 | MEDIUM |
#
# The table form has no `direction` column; we infer direction from
# the current-vs-learned comparison.
_TABLE_HEADER_RE = re.compile(
    r"\|\s*Component\s*\|\s*Metric\s*\|\s*Current\s*\|\s*Learned Normal\s*\|\s*Severity\s*\|",
)
_TABLE_ROW_RE = re.compile(
    r"\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([0-9.+-eE]+)\s*\|\s*([0-9.+-eE]+)\s*\|\s*([A-Z]+)\s*\|",
)


def _split_metric_key(key: str) -> tuple[str, str]:
    """Split 'component.rest_of_metric' on the first dot.

    Mirrors the screener's own split (`screener.py:_attribute_anomalies`).
    Falls back to ('unknown', key) for un-dotted keys.
    """
    parts = key.split(".", 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return "unknown", key


def _parse_v6_flags_from_markdown(anomaly_report: str) -> list[FlagSummary]:
    r"""Regex-extract flag rows from a v6 anomaly_report markdown blob.

    v6 emits one of two formats:

      - Bullet-with-direction (majority — ~93/108 episodes): each flag
        is a `- **\`component.metric\`** ... (SEVERITY, direction)` row.
      - Table form (older — ~5/108 episodes): a markdown table with
        `Component | Metric | Current | Learned Normal | Severity`.
        No direction column; we infer it from the value comparison.

    The remaining v6 episodes have anomaly_report blurbs that don't
    name specific metrics ("no single metric dominates"); those
    correctly yield empty flag lists.
    """
    flags: list[FlagSummary] = []
    if not anomaly_report:
        return flags

    # Bullet form takes precedence — newer and richer.
    blocks = re.split(r"\n(?=- \*\*`)", anomaly_report)
    for block in blocks:
        m = _FLAG_LINE_RE.search(block)
        if not m:
            continue
        full_key, severity, direction = m.group(1), m.group(2), m.group(3)
        component, metric = _split_metric_key(full_key)

        current: Optional[float] = None
        learned: Optional[float] = None
        v = _FLAG_VALUES_RE.search(block)
        if v:
            try:
                current = float(v.group(1))
                learned = float(v.group(2))
            except (ValueError, TypeError):
                pass

        flags.append(FlagSummary(
            metric=metric,
            component=component,
            direction=direction,
            severity=severity,
            current=current,
            learned_normal=learned,
        ))

    if flags:
        return flags

    # Table form — older v6 episodes. The `Component | Metric | ...`
    # header is the discriminator; we then iterate over rows.
    if not _TABLE_HEADER_RE.search(anomaly_report):
        return flags

    for line in anomaly_report.splitlines():
        if "Component" in line and "Metric" in line:
            continue  # header
        if set(line.strip()) <= {"|", "-", " "}:
            continue  # separator
        m = _TABLE_ROW_RE.search(line)
        if not m:
            continue
        component = m.group(1).strip()
        metric = m.group(2).strip()
        try:
            current = float(m.group(3))
            learned = float(m.group(4))
        except (ValueError, TypeError):
            current, learned = None, None
        severity = m.group(5).strip()

        # Infer direction from current vs learned. Mirrors the
        # screener's own logic (`_attribute_anomalies`): >1.5x = spike,
        # <0.5x = drop, mean-zero + nonzero current = spike, else shift.
        direction = "shift"
        if current is not None and learned is not None:
            if learned > 0 and current > learned * 1.5:
                direction = "spike"
            elif learned > 0 and current < learned * 0.5:
                direction = "drop"
            elif learned == 0 and current > 0:
                direction = "spike"

        flags.append(FlagSummary(
            metric=metric,
            component=component,
            direction=direction,
            severity=severity,
            current=current,
            learned_normal=learned,
        ))

    return flags


def _parse_anomaly_header(anomaly_report: str) -> tuple[Optional[float], Optional[tuple[int, int]]]:
    """Pull overall_anomaly_score and (calls, reg) bucket from the header line."""
    if not anomaly_report:
        return None, None
    m = _HEADER_RE.search(anomaly_report)
    if not m:
        return None, None
    try:
        score = float(m.group(1))
        bucket = (int(m.group(2)), int(m.group(3)))
        return score, bucket
    except (ValueError, TypeError):
        return None, None


# ── v7 symptom_classification reader ─────────────────────────────────

def _parse_v7_flags_from_classification(symptom_classification: dict) -> list[FlagSummary]:
    """Pull structured flags from v7's symptom_classification dict.

    The three bucket lists carry the same shape — each entry is an
    AnomalyFlag's `to_dict()` output augmented with `bucket` and
    `reason`. We flatten across buckets and emit FlagSummaries in the
    original ECOD-rank order across buckets (transport first, then
    application, then ambiguous — matching the recorder convention).
    """
    flags: list[FlagSummary] = []
    for bucket_key in ("transport_flags", "application_flags", "ambiguous_flags"):
        for entry in symptom_classification.get(bucket_key, []) or []:
            try:
                flags.append(FlagSummary(
                    metric=entry.get("metric", ""),
                    component=entry.get("component", ""),
                    direction=entry.get("direction", "shift"),
                    severity=entry.get("severity", "LOW"),
                    current=entry.get("current"),
                    learned_normal=entry.get("learned_normal"),
                    anomaly_score=entry.get("anomaly_score"),
                ))
            except Exception as e:
                log.debug("Skipping malformed flag in %s: %s", bucket_key, e)
    return flags


# ── Score extraction ─────────────────────────────────────────────────

def _extract_score_pct(score_obj: object) -> Optional[int]:
    """Pull the 0-100 score from a `challenge_result.score` payload.

    The chaos framework records `total_score` on a 0.0-1.0 scale. We
    multiply and round. Returns None when the payload doesn't carry
    a usable value.
    """
    if not isinstance(score_obj, dict):
        return None
    raw = score_obj.get("total_score")
    if raw is None:
        return None
    try:
        return int(round(float(raw) * 100))
    except (ValueError, TypeError):
        return None


def _extract_fault_type_correct(score_obj: object) -> Optional[bool]:
    if not isinstance(score_obj, dict):
        return None
    v = score_obj.get("fault_type_identified")
    return bool(v) if v is not None else None


# ── Infrastructure-NF status extraction ──────────────────────────────
#
# ADR: rag_infrastructure_fingerprint_enrichment.md
#
# Backfill source: every chaos episode JSON carries a `faults[]` block
# with structured fault metadata + a `verification_result` field that
# records the observed container state at fault time. This is the
# ground-truth signal — far more reliable than scraping NA tool traces
# or markdown.
#
# Extraction rule: emit `{target: "exited"}` when
#   1. fault_type ∈ {"container_kill", "container_stop"}, AND
#   2. verified is True, AND
#   3. verification_result contains "got 'exited'" (the harness's
#      observed-state confirmation).
# All other fault types (network impairments, container_pause) emit
# nothing — the screener fingerprint is already the right signal for
# those, and adding an `infra:` line would create phantom matches.

# Fault types that, when verified-down, mean the container produced
# the down state observable to `get_network_status()`.
_INFRA_DOWN_FAULT_TYPES: frozenset[str] = frozenset({
    "container_kill", "container_stop",
})

# The verification_result phrasing the chaos harness writes when a
# container reached the `exited` state. Matched as a substring so
# adjacent phrasing changes don't break extraction.
_VERIFIED_EXITED_MARKER = "got 'exited'"


def _extract_infra_status_from_faults(
    episode_data: dict,
) -> dict[str, str]:
    """Extract `{nf: "exited"}` entries from an episode's faults[] block.

    Only emits an entry when ALL three conditions hold:
      - `fault_type` ∈ {container_kill, container_stop}
      - `verified` is True
      - `verification_result` contains "got 'exited'"

    Targets not in `_KNOWN_NFS` are dropped defensively — protects the
    corpus from junk strings if a scenario library entry ever names a
    target that isn't a recognized NF.

    Returns `{}` for episodes with no infra-down faults (network
    impairments, healthy baselines, missing `faults[]`).
    """
    out: dict[str, str] = {}
    faults = episode_data.get("faults") or []
    if not isinstance(faults, list):
        return out
    for fault in faults:
        if not isinstance(fault, dict):
            continue
        fault_type = fault.get("fault_type")
        if fault_type not in _INFRA_DOWN_FAULT_TYPES:
            continue
        if fault.get("verified") is not True:
            continue
        vr = fault.get("verification_result") or ""
        if not isinstance(vr, str) or _VERIFIED_EXITED_MARKER not in vr:
            continue
        target = fault.get("target")
        if not isinstance(target, str) or not target:
            continue
        target = target.lower()
        if target not in _KNOWN_NFS:
            continue
        out[target] = "exited"
    return out


# ── JSON parser ──────────────────────────────────────────────────────

def _parse_json(path: Path) -> Optional[RetrievedCase]:
    """Parse a `run_*.json` episode file into a RetrievedCase."""
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        log.warning("malformed_json: %s — %s", path, e)
        return None

    agent_version = _detect_agent_version(path)
    if agent_version is None:
        log.warning("unknown_agent_version: %s", path)
        return None

    cr = data.get("challenge_result") or {}
    score_pct = _extract_score_pct(cr.get("score"))
    if score_pct is None:
        log.warning("no_score: %s", path)
        return None

    scenario = data.get("scenario") or {}
    scenario_name = scenario.get("name") or path.stem
    scenario_category = scenario.get("category")

    rca_label = data.get("rca_label") or {}

    # Flags: v7 path uses symptom_classification (structured);
    # v6 path regex-parses the anomaly_report markdown blob;
    # v5 has no screener output.
    flags: list[FlagSummary] = []
    anomaly_bucket: Optional[tuple[int, int]] = None
    overall_anomaly_score: Optional[float] = None
    sc = cr.get("symptom_classification")
    if isinstance(sc, dict) and any(
        sc.get(k) for k in ("transport_flags", "application_flags", "ambiguous_flags")
    ):
        flags = _parse_v7_flags_from_classification(sc)
    ar = cr.get("anomaly_report")
    if isinstance(ar, str) and ar:
        # Both the header line and (for v6) the flag rows live in the
        # rendered markdown. Header parsing is cheap and always tried.
        overall_anomaly_score, anomaly_bucket = _parse_anomaly_header(ar)
        if not flags:
            flags = _parse_v6_flags_from_markdown(ar)

    # Walker / classifier output (v7 only).
    classifier_label = sc.get("label") if isinstance(sc, dict) else None
    pwr = cr.get("path_walk_report") or {}
    walker_localized: Optional[bool] = None
    walker_attributed_hop_node: Optional[str] = None
    if isinstance(pwr, dict) and pwr:
        walker_localized = pwr.get("is_localized")
        fah = pwr.get("first_attributed_hop")
        if isinstance(fah, dict):
            walker_attributed_hop_node = fah.get("node")
    resolved_flow_id: Optional[str] = None
    # Phase 0.6 output key was renamed `resolved_path` → `prioritized_paths`
    # (ADR path_prioritizer_walks_all_candidates.md). New episodes carry
    # `prioritized_paths`; fall back to `resolved_path` for pre-rename
    # episodes already in the corpus. The internal `flow_id` key (the
    # primary candidate) is unchanged in both shapes.
    rp = cr.get("prioritized_paths") or cr.get("resolved_path")
    if isinstance(rp, dict):
        resolved_flow_id = rp.get("flow_id")

    # Diagnosis. Three input shapes the parser must handle:
    #   (a) new-v7 (post-Bug-A's fix at orchestrator.py:2783): both
    #       `diagnosis_report` (structured) AND `diagnosis_text`
    #       (rendered markdown) are populated. Trust the structured
    #       fields end-to-end — `verdict_kind` is the authoritative
    #       marker; a structured `primary_suspect_nf=None` means the
    #       agent legitimately emitted an inconclusive verdict and
    #       we MUST NOT fall back to text scraping (which might
    #       surface a lower-confidence guess).
    #   (b) old-v7 (pre-Bug-A's fix): `diagnosis_report` is null
    #       because Bug A left the state key unwritten on the
    #       app-layer Synthesis path; `diagnosis_text` is populated
    #       by the markdown renderer. Fall back to the text parser
    #       to recover the primary suspect.
    #   (c) v6: never had structured `diagnosis_report`. `diagnosis_text`
    #       is the agent's only output. Same fallback as (b).
    #
    # The discriminator between (a) and (b)/(c) is whether `dr` has a
    # populated `verdict_kind` — that field is set by every structured
    # output regardless of conclusiveness, and unset when the key
    # itself is missing.
    dr = cr.get("diagnosis_report") or {}
    diagnosis_text = cr.get("diagnosis_text") if isinstance(cr.get("diagnosis_text"), str) else ""
    diagnosis_summary = dr.get("summary") if isinstance(dr, dict) else None
    diagnosis_verdict = dr.get("verdict_kind") if isinstance(dr, dict) else None
    diagnosis_confidence = dr.get("root_cause_confidence") if isinstance(dr, dict) else None

    # Structured-output authoritative path (case a). Anything that
    # populates `verdict_kind` is trusted end-to-end — including a
    # legitimate `primary_suspect_nf=None` for inconclusive verdicts.
    # Otherwise (cases b and c) fall back to scraping `diagnosis_text`
    # for an `affected_components: ... Root Cause` entry, then the v7
    # inline `(primary_suspect_nf: ...)` suffix.
    if isinstance(dr, dict) and diagnosis_verdict is not None:
        diagnosis_primary = dr.get("primary_suspect_nf")
    else:
        diagnosis_primary = _extract_primary_suspect_from_diagnosis_text(
            diagnosis_text,
        )

    tokens = cr.get("token_usage") or {}
    total_tokens = tokens.get("total_tokens") if isinstance(tokens, dict) else None

    timestamp_raw = data.get("timestamp")
    run_timestamp: Optional[datetime] = None
    if timestamp_raw:
        try:
            run_timestamp = datetime.fromisoformat(timestamp_raw)
        except (ValueError, TypeError):
            pass

    episode_id = data.get("episode_id") or path.stem
    case_id = f"{agent_version}/{episode_id}"

    try:
        return RetrievedCase(
            case_id=case_id,
            source_episode_path=str(path.resolve()),
            agent_version=agent_version,
            run_timestamp=run_timestamp,
            parsed_from="json",
            scenario_name=scenario_name,
            scenario_category=scenario_category,
            fault_injected=list(data.get("faults") or []),
            ground_truth_failure_domain=rca_label.get("failure_domain"),
            ground_truth_affected_components=list(rca_label.get("affected_components") or []),
            ground_truth_severity=rca_label.get("severity"),
            ground_truth_root_cause_text=rca_label.get("root_cause"),
            anomaly_top_flags=flags,
            overall_anomaly_score=overall_anomaly_score,
            anomaly_bucket=anomaly_bucket,
            classifier_label=classifier_label if classifier_label in (
                "transport_layer", "application_layer", "mixed"
            ) else None,
            walker_localized=walker_localized,
            walker_attributed_hop_node=walker_attributed_hop_node,
            resolved_flow_id=resolved_flow_id,
            diagnosis_summary=diagnosis_summary,
            diagnosis_primary_suspect_nf=diagnosis_primary,
            diagnosis_verdict_kind=diagnosis_verdict,
            diagnosis_confidence=diagnosis_confidence if diagnosis_confidence in (
                "high", "medium", "low"
            ) else None,
            score_pct=score_pct,
            fault_type_correct=_extract_fault_type_correct(cr.get("score")),
            total_tokens=total_tokens,
            infra_status=_extract_infra_status_from_faults(data),
        )
    except Exception as e:
        log.warning("validation_failed: %s — %s", path, e)
        return None


# ── Markdown fallback parser ─────────────────────────────────────────

_MD_SCENARIO_RE = re.compile(r"^# Episode Report: (.+)$", re.MULTILINE)
_MD_SCORE_RE = re.compile(r"\*\*Overall score:\s*(\d+)%\*\*")
_MD_GROUND_TRUTH_RE = re.compile(
    r"## Ground Truth.*?"
    r"\*\*Failure domain:\*\*\s*([^\n]+).*?"
    r"\*\*Affected components:\*\*\s*([^\n]+)",
    re.DOTALL,
)
_MD_SEVERITY_RE = re.compile(r"\*\*Severity:\*\*\s*([^\n]+)")
_MD_AGENT_RE = re.compile(r"\*\*Agent:\*\*\s*(v\d+)")


def _parse_markdown(path: Path) -> Optional[RetrievedCase]:
    """Best-effort fallback when JSON is missing. Reduced field coverage."""
    try:
        text = path.read_text()
    except OSError as e:
        log.warning("markdown_unreadable: %s — %s", path, e)
        return None

    agent_version = _detect_agent_version(path) or (
        _MD_AGENT_RE.search(text).group(1) if _MD_AGENT_RE.search(text) else None
    )
    if agent_version not in ("v5", "v6", "v7"):
        log.warning("unknown_agent_version_md: %s", path)
        return None

    m_score = _MD_SCORE_RE.search(text)
    if not m_score:
        log.warning("no_score_md: %s", path)
        return None
    score_pct = int(m_score.group(1))

    m_scenario = _MD_SCENARIO_RE.search(text)
    scenario_name = m_scenario.group(1).strip() if m_scenario else path.stem

    failure_domain = None
    affected_components: list[str] = []
    severity = None
    m_gt = _MD_GROUND_TRUTH_RE.search(text)
    if m_gt:
        failure_domain = m_gt.group(1).strip()
        affected_components = [
            c.strip() for c in m_gt.group(2).split(",") if c.strip()
        ]
    m_sev = _MD_SEVERITY_RE.search(text)
    if m_sev:
        severity = m_sev.group(1).strip()

    # Try to lift screener flags from the anomaly-screening section if
    # present. v5 markdown won't have it.
    flags: list[FlagSummary] = []
    ar_section_match = re.search(
        r"## Anomaly Screening.*?(?=^## )", text, re.MULTILINE | re.DOTALL,
    )
    if ar_section_match:
        flags = _parse_v6_flags_from_markdown(ar_section_match.group(0))

    case_id = f"{agent_version}/{path.stem}"
    try:
        return RetrievedCase(
            case_id=case_id,
            source_episode_path=str(path.resolve()),
            agent_version=agent_version,
            parsed_from="markdown",
            scenario_name=scenario_name,
            anomaly_top_flags=flags,
            ground_truth_failure_domain=failure_domain,
            ground_truth_affected_components=affected_components,
            ground_truth_severity=severity,
            score_pct=score_pct,
        )
    except Exception as e:
        log.warning("validation_failed_md: %s — %s", path, e)
        return None


# ── Public API ───────────────────────────────────────────────────────

def parse_episode(path: Path | str) -> Optional[RetrievedCase]:
    """Parse one episode file into a RetrievedCase, or None if unparseable.

    Accepts a `.json` path or a `.md` path. When given `.md`, the
    parser checks for a paired `.json` and prefers it. Markdown
    fallback runs only when no paired JSON exists or the JSON parse
    fails.
    """
    path = Path(path)
    if not path.exists():
        log.warning("missing_file: %s", path)
        return None

    if path.suffix == ".json":
        return _parse_json(path)
    if path.suffix == ".md":
        json_path = path.with_suffix(".json")
        if json_path.exists():
            result = _parse_json(json_path)
            if result is not None:
                return result
            # JSON existed but failed to parse — fall through to markdown.
        return _parse_markdown(path)
    log.warning("unrecognized_extension: %s", path)
    return None


def parse_corpus(roots: list[Path | str]) -> list[RetrievedCase]:
    """Walk every `run_*.json` (preferred) or `run_*.md` under each root.

    Per directory: collect all `.json` files, then add any `.md` files
    that don't have a paired `.json`. This guarantees we never
    double-count an episode that ships both forms.

    Returns the populated cases. Per-file skip reasons are logged at
    WARNING level; counts of skipped files are surfaced by the CLI.
    """
    out: list[RetrievedCase] = []
    for root_raw in roots:
        root = Path(root_raw)
        if not root.exists():
            log.warning("root_missing: %s", root)
            continue

        json_files = sorted(root.glob("run_*.json"))
        json_stems = {p.stem for p in json_files}
        md_only = [
            p for p in sorted(root.glob("run_*.md"))
            if p.stem not in json_stems
        ]

        for p in json_files:
            case = parse_episode(p)
            if case is not None:
                out.append(case)

        for p in md_only:
            case = parse_episode(p)
            if case is not None:
                out.append(case)
    return out


# ── CLI ──────────────────────────────────────────────────────────────

def _print_stats(cases: list[RetrievedCase]) -> None:
    """Render a tally of parsed cases. Smoke-test surface for R1."""
    if not cases:
        print("Parsed 0 cases.")
        return

    by_agent = Counter(c.agent_version for c in cases)
    by_source = Counter(c.parsed_from for c in cases)
    by_agent_source = Counter(
        (c.agent_version, c.parsed_from) for c in cases
    )

    score_bands = Counter()
    for c in cases:
        if c.score_pct == 100:
            score_bands["100%"] += 1
        elif c.score_pct >= 80:
            score_bands["80-99%"] += 1
        elif c.score_pct >= 60:
            score_bands["60-79%"] += 1
        elif c.score_pct >= 40:
            score_bands["40-59%"] += 1
        elif c.score_pct >= 20:
            score_bands["20-39%"] += 1
        else:
            score_bands["<20%"] += 1

    print(f"Parsed: {len(cases)}")
    for v in ("v5", "v6", "v7"):
        if by_agent.get(v):
            json_n = by_agent_source.get((v, "json"), 0)
            md_n = by_agent_source.get((v, "markdown"), 0)
            print(f"  {v}: {by_agent[v]} (json={json_n}, markdown={md_n})")

    print(f"\nScore distribution (parsed cases):")
    for band in ("100%", "80-99%", "60-79%", "40-59%", "20-39%", "<20%"):
        n = score_bands.get(band, 0)
        if n:
            print(f"  {band:<10}{n:>4}")

    print(f"\nFlag coverage:")
    with_flags = sum(1 for c in cases if c.anomaly_top_flags)
    print(f"  cases with structured flags: {with_flags}/{len(cases)}")

    print(f"\nWalker outcomes (v7 only):")
    v7 = [c for c in cases if c.agent_version == "v7"]
    if v7:
        localized = sum(1 for c in v7 if c.walker_localized is True)
        null_loc = sum(1 for c in v7 if c.walker_localized is False)
        unknown = sum(1 for c in v7 if c.walker_localized is None)
        print(f"  localized: {localized}, null: {null_loc}, no_walk_run: {unknown}")


def _count_files(roots: list[Path]) -> int:
    """Count all `run_*.json` + `run_*.md` files (de-duped by stem per dir)."""
    total = 0
    for root in roots:
        if not root.exists():
            continue
        json_stems = {p.stem for p in root.glob("run_*.json")}
        total += len(json_stems)
        # md files without a paired json
        total += sum(
            1 for p in root.glob("run_*.md") if p.stem not in json_stems
        )
    return total


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m agentic_ops_common.rag.parser",
        description=(
            "Parse chaos-episode files into RetrievedCases. "
            "`stats` runs over a corpus and prints a tally; `show` "
            "parses one episode and prints its rendered form."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_stats = sub.add_parser(
        "stats",
        help="Walk one or more `docs/agent_logs/` dirs and print tally.",
    )
    p_stats.add_argument("roots", nargs="+", type=Path)

    p_show = sub.add_parser(
        "show",
        help="Parse one episode file and print its rendered form.",
    )
    p_show.add_argument("episode", type=Path)
    p_show.add_argument(
        "--verbosity", choices=("compact", "default", "full"),
        default="default",
    )

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

    if args.command == "stats":
        total_files = _count_files([Path(r) for r in args.roots])
        cases = parse_corpus(args.roots)
        skipped = total_files - len(cases)
        print(f"Walked {total_files} episode files.")
        _print_stats(cases)
        if skipped > 0:
            skip_pct = (skipped / total_files * 100) if total_files else 0
            print(f"\nSkipped: {skipped} ({skip_pct:.1f}%)")
            print("(see WARNING-level log for per-file reasons)")
        return 0

    if args.command == "show":
        case = parse_episode(args.episode)
        if case is None:
            print(f"Could not parse: {args.episode}", file=sys.stderr)
            return 1
        print(case.render_for_prompt(args.verbosity))
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
