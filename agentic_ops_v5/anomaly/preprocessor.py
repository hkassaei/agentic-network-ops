"""Metric preprocessor — converts raw metric snapshots into feature dicts.

Feature engineering for anomaly detection in a 5G SA + IMS (VoNR) network.
All features are designed to be SCALE-INDEPENDENT — they produce the same
values whether the network has 2 UEs or 2000 UEs.

Three categories of features:

1. QUALITY FEATURES — inherently scale-independent gauges
   average_mos, average_packet_loss, packet_loss_standard_deviation,
   average_jitter, response times. These are 0 (or 4.0 for MOS) when
   healthy regardless of UE count.

2. ERROR RATIO FEATURES — derived from counter pairs, always in [0, 1]
   diameter_timeout_ratio = timeouts / (timeouts + replies)
   registration_rejection_ratio = rejected / (rejected + accepted)
   httpclient_failure_ratio = connfail / (connfail + connok)
   These measure "what % of requests fail" — same answer at any scale.

3. PER-UE NORMALIZED RATES — counter rates divided by registered UE count
   register_rate_per_ue, invite_rate_per_ue, gtp_rate_per_ue
   These measure "how much traffic is each UE generating" — stable
   across different UE populations.
"""

from __future__ import annotations

import logging
import time
from typing import Any

log = logging.getLogger("v5.anomaly.preprocessor")

# =========================================================================
# Counter definitions — metrics that monotonically increase
# =========================================================================

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
    # I-CSCF
    "ims_icscf:uar_timeouts",
    "ims_icscf:lir_timeouts",
    "ims_icscf:uar_replies_received",
    "ims_icscf:lir_replies_received",
    # S-CSCF
    "ims_auth:mar_timeouts",
    "ims_auth:mar_replies_received",
    "ims_registrar_scscf:sar_timeouts",
    "ims_registrar_scscf:sar_replies_received",
]

_COUNTER_SET = set(_COUNTER_PATTERNS)


def _is_counter(key: str) -> bool:
    """Check if a metric key is a known counter."""
    return key in _COUNTER_SET


# =========================================================================
# Metrics to collect — superset needed for feature derivation
# =========================================================================

# We collect more metrics than we feed to the model. Some are only used
# as inputs to derived features (e.g., connfail + connok → failure_ratio).
_COLLECT_METRICS = {
    # AMF
    "ran_ue", "gnb", "amf_session",
    # SMF
    "fivegs_smffunction_sm_sessionnbr", "bearers_active", "pfcp_sessions_active",
    "ues_active",
    # UPF
    "fivegs_upffunction_upf_sessionnbr",
    "fivegs_ep_n3_gtp_indatapktn3upf",
    "fivegs_ep_n3_gtp_outdatapktn3upf",
    # P-CSCF
    "ims_usrloc_pcscf:registered_contacts",
    "core:rcv_requests_register",
    "core:rcv_requests_invite",
    "core:rcv_requests_bye",
    "sl:1xx_replies",
    "sl:200_replies",
    "sl:4xx_replies",
    "sl:5xx_replies",
    "dialog_ng:active",
    "httpclient:connfail",
    "httpclient:connok",
    # I-CSCF
    "cdp:timeout",
    "cdp:average_response_time",
    "cdp:replies_received",
    "ims_icscf:uar_timeouts",
    "ims_icscf:lir_timeouts",
    "ims_icscf:uar_avg_response_time",
    "ims_icscf:lir_avg_response_time",
    "ims_icscf:uar_replies_received",
    "ims_icscf:lir_replies_received",
    # S-CSCF
    "ims_usrloc_scscf:active_contacts",
    "ims_registrar_scscf:accepted_regs",
    "ims_registrar_scscf:rejected_regs",
    "ims_registrar_scscf:sar_avg_response_time",
    "ims_auth:mar_timeouts",
    "ims_auth:mar_avg_response_time",
    "ims_auth:mar_replies_received",
    "ims_registrar_scscf:sar_timeouts",
    "ims_registrar_scscf:sar_replies_received",
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


# Sliding window size for rate computation. Instead of instantaneous
# point-to-point deltas (which produce sparse 0/spike patterns on bursty
# counter data), we compute rates over a rolling window of the last N
# samples. With 5-second collection intervals and a window of 6 samples,
# the effective window is ~30 seconds. A register event that happened
# anywhere in the last 30 seconds produces a non-zero rate in every
# snapshot, giving the model smooth, mostly non-zero features.
_RATE_WINDOW_SAMPLES = 6


class MetricPreprocessor:
    """Converts raw per-component metric dicts into scale-independent features.

    All output features are designed to produce the same values regardless
    of UE count. Counter-derived rates are normalized per registered UE.
    Error ratios are computed from counter pairs. Quality gauges are passed
    through directly.

    Rate computation uses a sliding window (last N samples) instead of
    instantaneous point-to-point deltas to smooth bursty counter data.

    Usage:
        pp = MetricPreprocessor()
        features = pp.process({"pcscf": {"core:rcv_requests_register": 10, ...}, ...})
    """

    def __init__(self) -> None:
        # Ring buffer of (timestamp, {fkey: counter_value}) for sliding window rates
        self._history: list[tuple[float, dict[str, float]]] = []

    def process(self, raw_metrics: dict[str, dict[str, Any]], timestamp: float | None = None) -> dict[str, float]:
        """Convert raw metrics snapshot to a scale-independent feature dict.

        Args:
            raw_metrics: {component_name: {metric_key: value, ...}, ...}
            timestamp: Optional epoch timestamp for this snapshot. Critical
                       when replaying stored snapshots to avoid inflated rates.

        Returns:
            Flat dict of scale-independent features.
        """
        now = timestamp or time.time()

        # Step 1: Collect raw gauge values and current counter values
        raw_features: dict[str, float] = {}
        current_counters: dict[str, float] = {}

        for component, comp_data in raw_metrics.items():
            if not isinstance(comp_data, dict):
                continue
            # Handle both formats:
            #   {key: value, ...}  — flat (from orchestrator pre-unwrap)
            #   {metrics: {key: value}, badge: ..., source: ...}  — from snapshot_metrics()
            metrics = comp_data.get("metrics", comp_data) if "metrics" in comp_data else comp_data
            if not isinstance(metrics, dict):
                continue
            for key, value in metrics.items():
                if key.startswith("_"):
                    continue
                if not isinstance(value, (int, float)):
                    continue
                if key not in _COLLECT_METRICS:
                    continue

                fkey = f"{component}.{key}"
                raw_features[fkey] = float(value)

                if _is_counter(key):
                    current_counters[fkey] = float(value)

        # Step 2: Update history ring buffer and compute sliding window rates
        self._history.append((now, current_counters))
        if len(self._history) > _RATE_WINDOW_SAMPLES + 1:
            self._history.pop(0)

        rates: dict[str, float] = {}
        if len(self._history) >= 2:
            # Compare current counters against the oldest sample in the window
            oldest_time, oldest_counters = self._history[0]
            window_dt = now - oldest_time
            if window_dt > 0:
                for fkey, current_val in current_counters.items():
                    oldest_val = oldest_counters.get(fkey)
                    if oldest_val is not None:
                        delta = max(0.0, current_val - oldest_val)
                        rates[fkey] = round(delta / window_dt, 4)
                    else:
                        rates[fkey] = 0.0

        # Step 2: Extract UE counts for normalization
        ims_ue_count = raw_features.get("pcscf.ims_usrloc_pcscf:registered_contacts", 0)
        ran_ue_count = raw_features.get("amf.ran_ue", 0)

        # Step 3: Build scale-independent features
        features: dict[str, float] = {}

        # --- Category 1: Quality gauges (already scale-independent) ---
        _passthrough_gauges = [
            # RTPEngine quality
            "rtpengine.average_mos",
            "rtpengine.average_packet_loss",
            "rtpengine.average_jitter_(reported)",
            "rtpengine.packet_loss_standard_deviation",
            "rtpengine.packets_lost",
            "rtpengine.total_number_of_1_way_streams",
            "rtpengine.errors_per_second_(total)",
            "rtpengine.total_relayed_packet_errors",
            # Response times (latency, not volume)
            "icscf.cdp:average_response_time",
            "icscf.ims_icscf:uar_avg_response_time",
            "icscf.ims_icscf:lir_avg_response_time",
            "scscf.ims_auth:mar_avg_response_time",
            "scscf.ims_registrar_scscf:sar_avg_response_time",
            # Timeout counters (absolute, not rate — a single timeout is notable)
            "icscf.cdp:timeout",
            "icscf.ims_icscf:uar_timeouts",
            "icscf.ims_icscf:lir_timeouts",
            "scscf.ims_auth:mar_timeouts",
        ]
        for key in _passthrough_gauges:
            if key in raw_features:
                features[key] = raw_features[key]

        # --- Category 2: Error ratios (scale-independent, [0, 1]) ---

        # I-CSCF Diameter timeout ratios
        features["derived.icscf_uar_timeout_ratio"] = _safe_ratio(
            rates.get("icscf.ims_icscf:uar_timeouts", 0),
            rates.get("icscf.ims_icscf:uar_timeouts", 0) + rates.get("icscf.ims_icscf:uar_replies_received", 0),
        )
        features["derived.icscf_lir_timeout_ratio"] = _safe_ratio(
            rates.get("icscf.ims_icscf:lir_timeouts", 0),
            rates.get("icscf.ims_icscf:lir_timeouts", 0) + rates.get("icscf.ims_icscf:lir_replies_received", 0),
        )

        # S-CSCF MAR/SAR timeout ratios
        features["derived.scscf_mar_timeout_ratio"] = _safe_ratio(
            rates.get("scscf.ims_auth:mar_timeouts", 0),
            rates.get("scscf.ims_auth:mar_timeouts", 0) + rates.get("scscf.ims_auth:mar_replies_received", 0),
        )
        features["derived.scscf_sar_timeout_ratio"] = _safe_ratio(
            rates.get("scscf.ims_registrar_scscf:sar_timeouts", 0),
            rates.get("scscf.ims_registrar_scscf:sar_timeouts", 0) + rates.get("scscf.ims_registrar_scscf:sar_replies_received", 0),
        )

        # S-CSCF registration rejection ratio
        features["derived.scscf_registration_reject_ratio"] = _safe_ratio(
            rates.get("scscf.ims_registrar_scscf:rejected_regs", 0),
            rates.get("scscf.ims_registrar_scscf:rejected_regs", 0) + rates.get("scscf.ims_registrar_scscf:accepted_regs", 0),
        )

        # P-CSCF HTTP client failure ratio
        connfail_rate = rates.get("pcscf.httpclient:connfail", 0)
        connok_rate = rates.get("pcscf.httpclient:connok", 0)
        features["derived.pcscf_httpclient_failure_ratio"] = _safe_ratio(
            connfail_rate, connfail_rate + connok_rate,
        )

        # SIP error response ratio (4xx + 5xx vs total replies)
        for cscf in ["pcscf", "icscf", "scscf"]:
            err_rate = rates.get(f"{cscf}.sl:4xx_replies", 0) + rates.get(f"{cscf}.sl:5xx_replies", 0)
            ok_rate = rates.get(f"{cscf}.sl:200_replies", 0)
            total = err_rate + ok_rate + rates.get(f"{cscf}.sl:1xx_replies", 0)
            features[f"derived.{cscf}_sip_error_ratio"] = _safe_ratio(err_rate, total)

        # --- Category 3: Per-UE normalized rates ---

        # IMS signaling rates per registered UE
        for cscf in ["pcscf", "icscf", "scscf"]:
            for counter in ["core:rcv_requests_register", "core:rcv_requests_invite"]:
                rate = rates.get(f"{cscf}.{counter}", 0)
                features[f"normalized.{cscf}.{counter}_per_ue"] = (
                    round(rate / ims_ue_count, 4) if ims_ue_count >= 1 else 0.0
                )

        # Diameter replies per UE
        for cscf in ["icscf", "scscf"]:
            rate = rates.get(f"{cscf}.cdp:replies_received", 0)
            features[f"normalized.{cscf}.cdp_replies_per_ue"] = (
                round(rate / ims_ue_count, 4) if ims_ue_count >= 1 else 0.0
            )

        # UPF GTP-U rates per attached UE
        for direction in ["indatapktn3upf", "outdatapktn3upf"]:
            rate = rates.get(f"upf.fivegs_ep_n3_gtp_{direction}", 0)
            features[f"normalized.upf.gtp_{direction}_per_ue"] = (
                round(rate / ran_ue_count, 4) if ran_ue_count >= 1 else 0.0
            )

        # RTPEngine packets per session (if sessions active)
        rtp_sessions = raw_features.get("rtpengine.owned_sessions", 0)
        rtp_pps = raw_features.get("rtpengine.packets_per_second_(total)", 0)
        if rtp_sessions >= 1:
            features["normalized.rtpengine.pps_per_session"] = round(rtp_pps / rtp_sessions, 4)
        else:
            features["normalized.rtpengine.pps_per_session"] = 0.0

        # --- Category 4: Per-UE normalized gauges ---

        # Sessions per UE (should be ~2 PDU sessions per UE in this stack)
        sessions = raw_features.get("smf.fivegs_smffunction_sm_sessionnbr",
                                     raw_features.get("smf.ues_active", 0))
        features["normalized.smf.sessions_per_ue"] = (
            round(sessions / ran_ue_count, 2) if ran_ue_count >= 1 else 0.0
        )
        bearers = raw_features.get("smf.bearers_active", 0)
        features["normalized.smf.bearers_per_ue"] = (
            round(bearers / ran_ue_count, 2) if ran_ue_count >= 1 else 0.0
        )

        # Active dialogs per UE (should be 0 or ~1 during calls)
        dialogs = raw_features.get("pcscf.dialog_ng:active", 0)
        features["normalized.pcscf.dialogs_per_ue"] = (
            round(dialogs / ims_ue_count, 2) if ims_ue_count >= 1 else 0.0
        )

        # --- Category 5: Derived composite features ---

        # UPF activity during active calls
        active_calls = max(
            raw_features.get("pcscf.dialog_ng:active", 0),
            raw_features.get("scscf.dialog_ng:active", 0),
        )
        upf_in_rate = rates.get("upf.fivegs_ep_n3_gtp_indatapktn3upf", 0)
        upf_out_rate = rates.get("upf.fivegs_ep_n3_gtp_outdatapktn3upf", 0)
        upf_total_rate = upf_in_rate + upf_out_rate

        if active_calls > 0:
            expected_pps = active_calls * 100
            features["derived.upf_activity_during_calls"] = min(
                1.0, upf_total_rate / expected_pps if expected_pps > 0 else 0
            )
        else:
            features["derived.upf_activity_during_calls"] = 1.0

        # Infrastructure health (binary-ish)
        features["health.ran_ue"] = raw_features.get("amf.ran_ue", 0)
        features["health.gnb"] = raw_features.get("amf.gnb", 0)
        features["health.upf_sessions"] = raw_features.get("upf.fivegs_upffunction_upf_sessionnbr", 0)
        features["health.ims_registered"] = ims_ue_count

        return features

    def reset(self) -> None:
        """Reset state (e.g., between training and monitoring)."""
        self._history.clear()


def _safe_ratio(numerator: float, denominator: float) -> float:
    """Compute ratio safely, returning 0.0 when denominator is 0."""
    if denominator <= 0:
        return 0.0
    return round(min(1.0, numerator / denominator), 4)


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
    import re
    result: dict[str, dict[str, float]] = {}
    current_component: str | None = None

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        # Component header: "AMF [2 UE] (via prometheus):" or "PCSCF (via kamcmd):"
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
