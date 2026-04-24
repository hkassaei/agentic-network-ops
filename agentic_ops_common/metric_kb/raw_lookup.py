"""Raw Prometheus/kamcmd metric-name → KB-entry lookup.

`get_nf_metrics` and `get_dp_quality_gauges` return values under raw
metric names (`fivegs_ep_n3_gtp_indatapktn3upf`, `script:register_time`,
`core:rcv_requests_register`, …). The KB, in contrast, names metrics in
their *diagnostic* form — usually a derived per-UE rate, ratio, or
averaged value. This module bridges the two directions so a raw
counter in an agent-facing tool's output can be annotated with the
type, unit, and meaning from the correct KB entry (direct if the raw
metric itself has a KB entry, or indirectly via the derived form's
`raw_sources` list).

Two resolvers:
  - `resolve_raw(nf, raw_name, kb)`     — returns the KB entry + kind
  - `AnnotatedMetric`                    — dataclass carrying what the
                                           agent-facing renderer needs

Kinds:
  - "direct"   — the raw name IS the KB metric name (e.g. `ran_ue`)
  - "derived"  — the raw name feeds a derived KB metric; the raw
                 value alone is usually a cumulative lifetime counter
                 and should not be read as a rate
  - None       — no KB coverage
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from .feature_mapping import NF_LAYER
from .models import MetricEntry, MetricsKB

# Kinds of resolution.
ResolutionKind = Literal["direct", "derived"]


@dataclass
class AnnotatedMetric:
    """KB-sourced context for a raw metric name."""
    raw_name: str
    nf: str
    kb_metric_id: Optional[str]
    kind: Optional[ResolutionKind]  # "direct" | "derived" | None
    entry: Optional[MetricEntry]
    # When kind == "derived", this holds the raw counter's type — which
    # the KB author asserted by putting the name in `raw_sources`. For
    # nearly all derived-rate / per-UE forms, the raw source is a
    # CUMULATIVE counter. When we can't read it from the KB we fall
    # back to heuristics (see `_infer_raw_type`).
    raw_type: Optional[str] = None  # "counter" | "gauge" | "rate" | "ratio" | None


def resolve_raw(nf: str, raw_name: str, kb: MetricsKB) -> AnnotatedMetric:
    """Resolve `(nf, raw_name)` against the KB.

    Resolution order (derived-preferred):
      1. Derived — any KB entry under this NF lists `raw_name` in its
         `raw_sources`. Preferred because the derived form carries
         per-UE / rate / ratio semantics that a raw cumulative counter
         lacks on its own.
      2. Direct — `<layer>.<nf>.<raw_name>` is a KB metric (used for
         metrics that are diagnosed in raw form — `ran_ue`, `gnb`,
         `rtpengine_mos` — and for the migrated baseline metrics that
         don't have a derived per-UE form).
      3. Direct with name-normalization — common rewrites (strip
         Kamailio group prefix, known Prometheus prefixes).
      4. None.

    Derived wins over direct when both exist: after the baselines →
    metric_kb migration, many raw counters (`fivegs_ep_n3_gtp_*`,
    `core:rcv_requests_*`) have BOTH a direct KB entry AND a derived
    per-UE form that lists them in `raw_sources`. The derived form is
    the one agents should read; the direct entry is there to preserve
    the `expected` / `alarm_if` baseline-comparison data.
    """
    layer = NF_LAYER.get(nf)
    if layer is None:
        return AnnotatedMetric(raw_name=raw_name, nf=nf, kb_metric_id=None,
                               kind=None, entry=None)

    nf_block = kb.metrics.get(nf)
    if nf_block is None:
        return AnnotatedMetric(raw_name=raw_name, nf=nf, kb_metric_id=None,
                               kind=None, entry=None)

    # 1. Reverse index — does any KB entry list this raw_name in raw_sources?
    for metric_name, metric_entry in nf_block.metrics.items():
        if raw_name in metric_entry.raw_sources:
            return AnnotatedMetric(
                raw_name=raw_name, nf=nf,
                kb_metric_id=f"{layer}.{nf}.{metric_name}",
                kind="derived", entry=metric_entry,
                raw_type=_infer_raw_type(raw_name),
            )

    # 2. Direct lookup.
    entry = nf_block.metrics.get(raw_name)
    if entry is not None:
        return AnnotatedMetric(
            raw_name=raw_name, nf=nf,
            kb_metric_id=f"{layer}.{nf}.{raw_name}",
            kind="direct", entry=entry,
        )

    # 3. Normalized names.
    normalized = _normalize_raw_name(raw_name)
    if normalized and normalized != raw_name:
        entry = nf_block.metrics.get(normalized)
        if entry is not None:
            return AnnotatedMetric(
                raw_name=raw_name, nf=nf,
                kb_metric_id=f"{layer}.{nf}.{normalized}",
                kind="direct", entry=entry,
            )

    # 4. No coverage.
    return AnnotatedMetric(raw_name=raw_name, nf=nf, kb_metric_id=None,
                           kind=None, entry=None,
                           raw_type=_infer_raw_type(raw_name))


def _normalize_raw_name(raw_name: str) -> Optional[str]:
    """Strip predictable Prometheus / kamcmd prefixes.

    Examples:
      fivegs_ep_n3_gtp_indatapktn3upf  →  gtp_indatapktn3upf
      fivegs_upffunction_upf_sessionnbr → upf_sessionnbr
      fivegs_amffunction_rm_reginitreq → rm_reginitreq
      script:register_time             → register_time (group-prefix strip)
      core:rcv_requests_register       → rcv_requests_register
      ims_icscf:uar_timeouts           → uar_timeouts
    """
    prefixes = [
        "fivegs_ep_n3_",
        "fivegs_upffunction_",
        "fivegs_amffunction_",
        "fivegs_smffunction_",
        "fivegs_pcffunction_",
    ]
    for p in prefixes:
        if raw_name.startswith(p):
            return raw_name[len(p):]
    if ":" in raw_name:
        _, bare = raw_name.split(":", 1)
        return bare
    return None


def _infer_raw_type(raw_name: str) -> Optional[str]:
    """Heuristic inference when the KB can't tell us.

    Intentionally conservative — returns None when the name is
    ambiguous. The annotator prefers KB-derived types; this is only
    used for metrics with no KB coverage at all.
    """
    # Kamailio reply counters, cumulative counters
    if raw_name.startswith(("core:rcv_requests_",)):
        return "counter"
    if raw_name.startswith("sl:") and raw_name.endswith(("_replies",)):
        return "counter"
    if raw_name.startswith("script:") and raw_name.endswith(("_time", "_success")):
        return "counter"
    if raw_name.startswith("httpclient:conn"):
        return "counter"
    # Kamailio *_timeouts / *_replies_received
    if (
        raw_name.startswith(("ims_icscf:", "ims_auth:", "ims_registrar_scscf:"))
        and raw_name.endswith(("_timeouts", "_received", "_regs"))
    ):
        return "counter"
    # 5G core Prometheus packet counters
    if "fivegs_ep_n3_gtp_" in raw_name and ("indatapkt" in raw_name or "outdatapkt" in raw_name):
        return "counter"
    if raw_name.startswith("fivegs_") and raw_name.endswith(("req", "succ", "fail")):
        return "counter"
    # Gauges
    if raw_name in {"ran_ue", "gnb", "amf_session", "ues_active",
                    "bearers_active", "pfcp_sessions_active"}:
        return "gauge"
    if "sessionnbr" in raw_name or "_active" in raw_name:
        return "gauge"
    if raw_name.endswith(("_contacts",)):
        return "gauge"
    # Averages (instantaneous)
    if "avg_response_time" in raw_name or raw_name == "cdp:average_response_time":
        return "gauge"
    return None
