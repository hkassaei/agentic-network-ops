"""Feature-key → KB-metric-id mapping.

Preprocessor feature keys (used by the anomaly screener and the trigger
evaluator) don't line up 1:1 with the KB's `<layer>.<nf>.<metric>`
namespace. This module centralizes the translation so every consumer
(trigger evaluator, flag enrichment, future lookups) uses the same
mapping logic.
"""

from __future__ import annotations

from typing import Optional


# Layer assignment per NF (matches components.yaml). Used for namespacing.
NF_LAYER: dict[str, str] = {
    "amf": "core",
    "smf": "core",
    "upf": "core",
    "pcf": "core",
    "ausf": "core",
    "udm": "core",
    "udr": "core",
    "nrf": "core",
    "pcscf": "ims",
    "icscf": "ims",
    "scscf": "ims",
    "pyhss": "ims",
    "rtpengine": "ims",
    "mongo": "infrastructure",
    "mysql": "infrastructure",
    "dns": "infrastructure",
    "nr_gnb": "ran",
}


def map_preprocessor_key_to_kb(fkey: str) -> Optional[str]:
    """Translate a preprocessor feature key to its KB metric id.

    Preprocessor emits keys like:
        amf.ran_ue
        icscf.cdp:average_response_time
        icscf.ims_icscf:uar_avg_response_time
        normalized.pcscf.dialogs_per_ue
        normalized.upf.gtp_indatapktn3upf_per_ue
        derived.pcscf_avg_register_time_ms
        derived.icscf_uar_timeout_ratio
        derived.upf_activity_during_calls
        rtpengine.errors_per_second_(total)

    KB uses <layer>.<nf>.<metric>, e.g. core.amf.ran_ue, ims.pcscf.dialogs_per_ue.
    Returns None for keys that don't map to any known KB entry.
    """
    if fkey.startswith("normalized."):
        rest = fkey[len("normalized."):]
        parts = rest.split(".", 1)
        if len(parts) != 2:
            return None
        nf, metric = parts
        layer = NF_LAYER.get(nf)
        if layer is None:
            return None
        clean_metric = metric.replace("core:", "")
        return f"{layer}.{nf}.{clean_metric}"

    if fkey.startswith("derived."):
        rest = fkey[len("derived."):]
        for nf in NF_LAYER:
            if rest.startswith(nf + "_"):
                layer = NF_LAYER[nf]
                metric = rest[len(nf) + 1:]
                return f"{layer}.{nf}.{metric}"
        return None

    parts = fkey.split(".", 1)
    if len(parts) != 2:
        return None
    nf, metric = parts
    layer = NF_LAYER.get(nf)
    if layer is None:
        return None
    if ":" in metric:
        group, bare = metric.split(":", 1)
        if group == "cdp" and bare == "average_response_time":
            return f"{layer}.{nf}.cdp_avg_response_time"
        if group.startswith("ims_") and bare.endswith("_response_time"):
            return f"{layer}.{nf}.{bare}"
        return None
    if nf == "rtpengine" and metric == "errors_per_second_(total)":
        return "ims.rtpengine.errors_per_second"
    return f"{layer}.{nf}.{metric}"
