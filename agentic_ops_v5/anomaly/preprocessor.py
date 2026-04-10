"""Metric preprocessor — converts raw metric snapshots into feature dicts.

Handles two metric types:
  - Counters (monotonically increasing) → converted to delta/rate per interval
  - Gauges (point-in-time values) → passed through as-is

The preprocessor maintains state between calls to compute deltas.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

log = logging.getLogger("v5.anomaly.preprocessor")

# Metric keys known to be counters (monotonically increasing).
# Rates are computed as delta / interval_seconds.
_COUNTER_PATTERNS = [
    # AMF
    "fivegs_amffunction_rm_reginitreq",
    "fivegs_amffunction_rm_reginitsucc",
    "fivegs_amffunction_amf_authreq",
    "fivegs_amffunction_amf_authfail",
    "fivegs_amffunction_amf_authreject",
    # SMF
    "fivegs_smffunction_sm_pdusessioncreationreq",
    "fivegs_smffunction_sm_pdusessioncreationsucc",
    # UPF
    "fivegs_ep_n3_gtp_indatapktn3upf",
    "fivegs_ep_n3_gtp_outdatapktn3upf",
    "fivegs_ep_n3_gtp_indatavolumeqosleveln3upf",
    "fivegs_ep_n3_gtp_outdatavolumeqosleveln3upf",
    # PCF
    "fivegs_pcffunction_pa_policyamassoreq",
    "fivegs_pcffunction_pa_policyamassosucc",
    "fivegs_pcffunction_pa_policysmassoreq",
    "fivegs_pcffunction_pa_policysmassosucc",
    # Kamailio — SIP counters
    "core:rcv_requests_register",
    "core:rcv_requests_invite",
    "core:rcv_requests_bye",
    "core:rcv_requests_options",
    "sl:1xx_replies",
    "sl:200_replies",
    "sl:4xx_replies",
    "sl:5xx_replies",
    "httpclient:connfail",
    "httpclient:connok",
    # Kamailio — Diameter counters
    "cdp:replies_received",
    "cdp:replies_response_time",
    # S-CSCF registration counters
    "ims_registrar_scscf:accepted_regs",
    "ims_registrar_scscf:rejected_regs",
]

_COUNTER_SET = set(_COUNTER_PATTERNS)


def _is_counter(key: str) -> bool:
    """Check if a metric key is a known counter."""
    return key in _COUNTER_SET


# Metrics that are diagnostically important for anomaly detection.
# Only these are included in the feature dict passed to the ML model.
# This keeps the feature space small enough for HalfSpaceTrees to be
# effective (~30-40 features instead of 143).
_DIAGNOSTIC_METRICS = {
    # AMF
    "ran_ue", "gnb", "amf_session",
    # SMF
    "fivegs_smffunction_sm_sessionnbr", "bearers_active", "pfcp_sessions_active",
    # UPF
    "fivegs_upffunction_upf_sessionnbr",
    "fivegs_ep_n3_gtp_indatapktn3upf",   # counter → rate
    "fivegs_ep_n3_gtp_outdatapktn3upf",  # counter → rate
    # P-CSCF
    "ims_usrloc_pcscf:registered_contacts",
    "core:rcv_requests_register",  # counter → rate
    "core:rcv_requests_invite",    # counter → rate
    "sl:1xx_replies",              # counter → rate
    "sl:200_replies",              # counter → rate
    "sl:4xx_replies",              # counter → rate
    "sl:5xx_replies",              # counter → rate
    "tmx:active_transactions",
    "dialog_ng:active",
    "httpclient:connfail",         # counter → rate
    # I-CSCF
    "cdp:timeout",
    "cdp:average_response_time",
    "ims_icscf:uar_timeouts",
    "ims_icscf:lir_timeouts",
    # S-CSCF
    "ims_usrloc_scscf:active_contacts",
    "ims_registrar_scscf:accepted_regs",  # counter → rate
    "ims_registrar_scscf:rejected_regs",  # counter → rate
    "ims_auth:mar_timeouts",
    "cdp:replies_received",               # counter → rate
    # RTPEngine
    "average_mos",
    "packets_per_second_(total)",
    "average_packet_loss",
    "average_jitter_(reported)",
    "total_sessions",
    "owned_sessions",
    "packets_lost",
    "total_number_of_1_way_streams",
    "total_relayed_packet_errors",
    "errors_per_second_(total)",
    "packet_loss_standard_deviation",
    # PyHSS
    "ims_subscribers",
    # MongoDB
    "subscribers",
}


def _is_diagnostic(key: str) -> bool:
    """Check if a metric is in the diagnostic set."""
    return key in _DIAGNOSTIC_METRICS


class MetricPreprocessor:
    """Converts raw per-component metric dicts into flat feature dicts.

    Usage:
        pp = MetricPreprocessor()
        features = pp.process({"pcscf": {"core:rcv_requests_register": 10, ...}, ...})
        # Returns: {"pcscf.core:rcv_requests_register_rate": 0.0, ...}
    """

    def __init__(self) -> None:
        self._prev_values: dict[str, float] = {}
        self._prev_time: float | None = None

    def process(self, raw_metrics: dict[str, dict[str, Any]]) -> dict[str, float]:
        """Convert raw metrics snapshot to a flat feature dict.

        Args:
            raw_metrics: {component_name: {metric_key: value, ...}, ...}
                         as returned by the pattern_matcher's _collect_observations
                         or parsed from get_nf_metrics() output.

        Returns:
            Flat dict: {"component.metric_key": value, ...}
            Counters are converted to rates (per second).
            Gauges are passed through.
            Keys starting with '_' are skipped (internal computed metrics).
        """
        now = time.time()
        dt = (now - self._prev_time) if self._prev_time else None
        features: dict[str, float] = {}

        for component, metrics in raw_metrics.items():
            if not isinstance(metrics, dict):
                continue
            for key, value in metrics.items():
                if key.startswith("_"):
                    continue
                if not isinstance(value, (int, float)):
                    continue
                if not _is_diagnostic(key):
                    continue

                fkey = f"{component}.{key}"

                if _is_counter(key):
                    # Convert counter to rate
                    prev = self._prev_values.get(fkey)
                    if prev is not None and dt and dt > 0:
                        delta = max(0.0, value - prev)  # handle counter reset
                        rate = delta / dt
                        features[f"{fkey}_rate"] = round(rate, 4)
                    else:
                        features[f"{fkey}_rate"] = 0.0
                    self._prev_values[fkey] = value
                else:
                    # Gauge — pass through
                    features[fkey] = float(value)

        self._prev_time = now
        return features

    def reset(self) -> None:
        """Reset state (e.g., between training and monitoring)."""
        self._prev_values.clear()
        self._prev_time = None


def parse_nf_metrics_text(text: str) -> dict[str, dict[str, float]]:
    """Parse the text output of get_nf_metrics() into structured per-component dicts.

    Handles the actual output format:
        AMF [2 UE] (via prometheus):
          amf_session = 4.0
          gnb = 1.0

        PCSCF [2 reg] (via kamcmd):
          core:rcv_requests_register = 10.0

    Returns: {component_name: {metric_key: value, ...}, ...}
    """
    result: dict[str, dict[str, float]] = {}
    current_component: str | None = None

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        # Component header: "AMF [2 UE] (via prometheus):" or "PCSCF (via kamcmd):"
        # Also handles: "=== pcscf ===" or "pcscf:"
        header_match = re.match(
            r"^([A-Za-z_]\w*)\s*(?:\[.*?\])?\s*(?:\(.*?\))?\s*:\s*$", stripped
        )
        if header_match:
            current_component = header_match.group(1).lower()
            if current_component not in result:
                result[current_component] = {}
            continue

        # Also match bare headers: "=== pcscf ===" or "--- amf ---"
        bare_header = re.match(r"^[=\-]+\s*(\w+)\s*[=\-]+$", stripped)
        if bare_header:
            current_component = bare_header.group(1).lower()
            if current_component not in result:
                result[current_component] = {}
            continue

        # Metric value lines: "  key = value" or "  key: value"
        if current_component:
            metric_match = re.match(r'"?([\w:]+)"?\s*[=:]\s*(-?\d+\.?\d*)', stripped)
            if metric_match:
                key = metric_match.group(1)
                try:
                    result[current_component][key] = float(metric_match.group(2))
                except ValueError:
                    pass

    return result
