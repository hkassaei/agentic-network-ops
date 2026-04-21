"""NF metrics — Prometheus, kamcmd, RTPEngine, PyHSS, MongoDB snapshots.

`get_nf_metrics` is KB-backed: every value returned is annotated with
its type (counter / gauge / ratio / derived), unit, and a short
semantic hint pulled from the metric KB. When a raw counter's
diagnostic reading lives in a derived KB entry (e.g. a per-UE rate),
the annotation says so explicitly — preventing agents from reading
lifetime cumulative counters as current rates.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from agentic_ops_common.metric_kb import (
    AnnotatedMetric,
    KBLoadError,
    MetricsKB,
    load_kb,
    resolve_raw,
)

from ._common import _t, _get_deps

_log = logging.getLogger("tools.metrics")

# Header the LLM reads once at the top of every `get_nf_metrics` payload.
# Small enough to not dilute the signal; sharp enough to prevent the
# "9348 in vs 294 out = 97% drop" kind of misreading.
_METRICS_HEADER = (
    "Each metric below is annotated with its [type, unit] and, where "
    "the KB has it, a short meaning. Types:\n"
    "  [counter]  — MONOTONIC LIFETIME TOTAL since the container's last "
    "start. A bare counter value does NOT represent a current rate; do "
    "not divide two counters and call the quotient a 'loss rate'. Use "
    "the derived/per-UE KB metric listed in 'see KB:' when present, or "
    "consult the anomaly screener's enriched flags for current activity.\n"
    "  [gauge]    — instantaneous current value (UE counts, session counts, "
    "etc.). Safe to compare across NFs.\n"
    "  [ratio]    — current proportion in [0, 1]. Already normalized.\n"
    "  [derived]  — rate/ratio computed over a sliding window. Safe to "
    "read as a current signal.\n"
    "When an entry has no KB coverage it is labeled [uncategorized]; "
    "treat its value with caution.\n"
)


def _kb() -> Optional[MetricsKB]:
    """Load the KB lazily, cached via module-level closure."""
    if not hasattr(_kb, "_cached"):
        try:
            _kb._cached = load_kb()  # type: ignore[attr-defined]
        except KBLoadError as e:
            _log.warning("KB unavailable for metrics annotation: %s", e)
            _kb._cached = None  # type: ignore[attr-defined]
    return _kb._cached  # type: ignore[attr-defined]


# Map the friendly NF-section headers emitted by the upstream collector
# to the KB's NF key. "PCSCF (via kamcmd):" → "pcscf". Case-insensitive.
_SECTION_RE = re.compile(r"^([A-Z][A-Z0-9_]*)(?:\s*\[[^\]]*\])?\s*\(via [^)]+\):", re.I)
_KEY_VALUE_RE = re.compile(r"^(\s+)([^=\s][^=]*?)\s*=\s*(.+)$")


def _annotate_line(line: str, current_nf: Optional[str], kb: MetricsKB) -> str:
    """Append KB annotation to a `  key = value` line."""
    m = _KEY_VALUE_RE.match(line)
    if not m or current_nf is None:
        return line
    indent, key, value = m.group(1), m.group(2).strip(), m.group(3)
    if key.startswith("_"):
        return line

    resolved = resolve_raw(current_nf, key, kb)
    tag = _format_tag(resolved)
    hint = _format_hint(resolved)

    suffix = f"  {tag}"
    if hint:
        suffix += f"  {hint}"
    return f"{indent}{key} = {value}{suffix}"


def _format_tag(resolved: AnnotatedMetric) -> str:
    """Produce the `[type, unit]` tag (or fallback)."""
    if resolved.kind == "direct" and resolved.entry is not None:
        t = resolved.entry.type.value
        u = resolved.entry.unit or ""
        return f"[{t}{', ' + u if u else ''}]"
    if resolved.kind == "derived":
        raw_t = resolved.raw_type or "counter"
        return f"[{raw_t}]"
    # No KB coverage — fall back to heuristic type if we have it.
    if resolved.raw_type:
        return f"[{resolved.raw_type}]"
    return "[uncategorized]"


def _format_hint(resolved: AnnotatedMetric) -> str:
    """Produce a short semantic pointer the agent can read."""
    if resolved.kind == "direct" and resolved.entry is not None:
        entry = resolved.entry
        if entry.meaning and entry.meaning.what_it_signals:
            # Keep it to one compact line.
            first = entry.meaning.what_it_signals.split(".")[0].strip()
            return f"— {first}."
        return ""
    if resolved.kind == "derived" and resolved.entry is not None:
        return (
            f"— see KB: `{resolved.kb_metric_id}` for the diagnostic reading "
            f"(current value here is a lifetime total, not a rate)."
        )
    if resolved.raw_type == "counter":
        return "— lifetime cumulative total; not a current rate."
    return ""


async def get_nf_metrics() -> str:
    """Get a full metrics snapshot across ALL network functions in one call.

    Collects from Prometheus (5G core), kamcmd (IMS Kamailio), RTPEngine,
    PyHSS, and MongoDB. This is the 'radiograph' — a quick health overview
    of the entire stack.

    The output is KB-annotated: every metric has a `[type, unit]` tag
    and (when covered) a one-line meaning. Use the tags to decide how
    to read the value — especially to avoid misreading raw cumulative
    counters as current rates.
    """
    raw = await _t.get_nf_metrics(_get_deps())
    kb = _kb()
    if kb is None or not raw or "metrics collected" not in raw.lower() and "\n" not in raw:
        # Either KB unavailable or a short error message — return as-is.
        return raw

    out_lines: list[str] = [_METRICS_HEADER]
    current_nf: Optional[str] = None
    for line in raw.splitlines():
        m = _SECTION_RE.match(line.strip())
        if m:
            current_nf = m.group(1).lower()
            out_lines.append(line)
            continue
        if current_nf is None:
            out_lines.append(line)
            continue
        out_lines.append(_annotate_line(line, current_nf, kb))

    return "\n".join(out_lines)


async def query_prometheus(query: str, window_seconds: int | None = None) -> str:
    """INTERNAL — raw PromQL access. Not exposed to investigation agents.

    Agents should use `get_nf_metrics` (current snapshot across all NFs)
    or `get_dp_quality_gauges` (pre-computed data-plane rates) instead.
    Those tools are KB-annotated and cannot return hallucinated metric
    names. Raw PromQL is retained only for internal tooling / tests that
    need bespoke queries.

    Args:
        query: PromQL query string. `{window}` placeholder is replaced
            with `{window_seconds}s` when provided.
        window_seconds: Optional lookback window for rate/range queries.
    """
    return await _t.query_prometheus(_get_deps(), query, window_seconds=window_seconds)
