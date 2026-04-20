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

log = logging.getLogger("anomaly.preprocessor")

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
    "script:register_time",
    "script:register_success",
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
    "script:register_time",
    "script:register_success",
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
    # RTPEngine — only point-in-time gauges, NOT cumulative lifetime metrics.
    # Removed: average_packet_loss, packet_loss_standard_deviation, average_mos,
    # packets_lost, total_number_of_1_way_streams, total_relayed_packet_errors.
    # These are cumulative lifetime averages/counters that carry stale data from
    # previous chaos runs and poison the anomaly screener (see ADR:
    # remove_cumulative_rtpengine_features.md).
    "errors_per_second_(total)",
    "packets_per_second_(total)",
    "total_sessions",
    "owned_sessions",
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


# =========================================================================
# Temporal-metric pre-filter mapping (ADR: anomaly_training_zero_pollution.md)
# =========================================================================
# Time/duration metrics are semantically undefined when their underlying
# event counter did not advance. A response-time of 0 is not a value of
# zero — it means "no event happened, so the time is not applicable."
# For each temporal feature emitted by the preprocessor, we record the
# underlying counter whose advance is required for the feature to be
# valid in a given snapshot. When the counter didn't advance, the
# feature is omitted from that snapshot's feature vector entirely.
#
# Keys are the OUTPUT feature names. Values are the INPUT counter fkeys
# (i.e. "{component}.{metric}").
_TEMPORAL_COUNTER_MAP: dict[str, str] = {
    "icscf.ims_icscf:lir_avg_response_time":
        "icscf.ims_icscf:lir_replies_received",
    "icscf.ims_icscf:uar_avg_response_time":
        "icscf.ims_icscf:uar_replies_received",
    "icscf.cdp:average_response_time":
        "icscf.cdp:replies_received",
    "scscf.ims_auth:mar_avg_response_time":
        "scscf.ims_auth:mar_replies_received",
    "scscf.ims_registrar_scscf:sar_avg_response_time":
        "scscf.ims_registrar_scscf:sar_replies_received",
    "derived.pcscf_avg_register_time_ms":
        "pcscf.script:register_success",
}


# For rate-based features, map each output feature to its underlying
# cumulative counter. Used by the screener's silent-failure escalation
# to decide whether "current rate = 0" means "subsystem is quiet by
# nature" (no escalation) or "subsystem was active recently but has
# gone silent" (escalate to HIGH). Rate features themselves are never
# filtered out — 0 is a legitimate rate observation.
_RATE_COUNTER_MAP: dict[str, str] = {
    "normalized.pcscf.core:rcv_requests_register_per_ue":
        "pcscf.core:rcv_requests_register",
    "normalized.pcscf.core:rcv_requests_invite_per_ue":
        "pcscf.core:rcv_requests_invite",
    "normalized.icscf.core:rcv_requests_register_per_ue":
        "icscf.core:rcv_requests_register",
    "normalized.icscf.core:rcv_requests_invite_per_ue":
        "icscf.core:rcv_requests_invite",
    "normalized.scscf.core:rcv_requests_register_per_ue":
        "scscf.core:rcv_requests_register",
    "normalized.scscf.core:rcv_requests_invite_per_ue":
        "scscf.core:rcv_requests_invite",
    "normalized.icscf.cdp_replies_per_ue":
        "icscf.cdp:replies_received",
    "normalized.scscf.cdp_replies_per_ue":
        "scscf.cdp:replies_received",
    "normalized.upf.gtp_indatapktn3upf_per_ue":
        "upf.fivegs_ep_n3_gtp_indatapktn3upf",
    "normalized.upf.gtp_outdatapktn3upf_per_ue":
        "upf.fivegs_ep_n3_gtp_outdatapktn3upf",
}


# How many recent snapshot windows to consider when deciding a counter
# was "recently active." With a 6-sample rate window, looking at 2
# recent windows covers ~60 seconds of history, enough to distinguish
# steady-state silence from a just-went-silent failure.
_LIVENESS_LOOKBACK_WINDOWS = 2


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
        # Liveness signals computed during the most recent process() call.
        # Maps OUTPUT feature name → True if the feature's underlying counter
        # advanced in at least one of the last _LIVENESS_LOOKBACK_WINDOWS
        # snapshot pairs. Consumed by AnomalyScreener.score() for silent-
        # failure severity escalation. See ADR: anomaly_training_zero_pollution.md
        self._liveness: dict[str, bool] = {}

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

        # Reset liveness for this snapshot; populated as features are emitted.
        self._liveness = {}

        # Step 2: Extract UE counts for normalization
        ims_ue_count = raw_features.get("pcscf.ims_usrloc_pcscf:registered_contacts", 0)
        ran_ue_count = raw_features.get("amf.ran_ue", 0)

        # Step 3: Build scale-independent features
        features: dict[str, float] = {}

        # --- Category 1: Quality gauges (already scale-independent) ---
        _passthrough_gauges = [
            # RTPEngine quality
            # RTPEngine — only point-in-time gauges (not cumulative lifetime metrics)
            "rtpengine.errors_per_second_(total)",
            # Response times (latency, not volume)
            "icscf.cdp:average_response_time",
            "icscf.ims_icscf:uar_avg_response_time",
            "icscf.ims_icscf:lir_avg_response_time",
            "scscf.ims_auth:mar_avg_response_time",
            "scscf.ims_registrar_scscf:sar_avg_response_time",
            # Timeout counters removed from passthrough gauges — they are
            # cumulative counters that carry stale data from previous runs.
            # The derived ratio features (icscf_uar_timeout_ratio, etc.)
            # use the sliding-window rates of these counters instead,
            # which only reflect current state. See ADR:
            # remove_cumulative_timeout_counters.md
        ]
        for key in _passthrough_gauges:
            if key not in raw_features:
                continue
            # Pre-filter: omit response-time / duration metrics from this
            # snapshot when the underlying event counter did not advance.
            # A time-of-zero with no event is semantically "not applicable,"
            # not a valid observation. ADR: anomaly_training_zero_pollution.md
            counter_fkey = _TEMPORAL_COUNTER_MAP.get(key)
            if counter_fkey is not None:
                counter_advanced = rates.get(counter_fkey, 0) > 0
                if not counter_advanced:
                    continue
                # Emitted: mark live so silent-failure escalation can fire
                # if the same feature later reports 0 despite being live.
                self._liveness[key] = True
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

        # P-CSCF HTTP client failure ratio — intentionally excluded.
        # The P-CSCF's Rx/SCP connection has a baseline failure rate of ~84%
        # (deployment-specific: SCP timeouts on Rx AAR). This pre-existing noise
        # masks real faults. Calls still work without dedicated QoS bearers.

        # SIP error response ratio (4xx + 5xx vs total replies)
        for cscf in ["pcscf", "icscf", "scscf"]:
            err_rate = rates.get(f"{cscf}.sl:4xx_replies", 0) + rates.get(f"{cscf}.sl:5xx_replies", 0)
            ok_rate = rates.get(f"{cscf}.sl:200_replies", 0)
            total = err_rate + ok_rate + rates.get(f"{cscf}.sl:1xx_replies", 0)
            features[f"derived.{cscf}_sip_error_ratio"] = _safe_ratio(err_rate, total)

        # P-CSCF average registration time (ms per registration)
        # script:register_time is a CUMULATIVE counter (total ms across all
        # registrations), not a gauge. We compute avg time per registration
        # using the sliding window rates of both counters. When no new
        # REGISTERs completed in the window, the metric is omitted from this
        # snapshot entirely — "0 ms" would be a semantically wrong value for
        # "no events to average." ADR: anomaly_training_zero_pollution.md
        reg_time_rate = rates.get("pcscf.script:register_time", 0)
        reg_success_rate = rates.get("pcscf.script:register_success", 0)
        if reg_success_rate > 0:
            features["derived.pcscf_avg_register_time_ms"] = round(
                reg_time_rate / reg_success_rate, 1
            )
            self._liveness["derived.pcscf_avg_register_time_ms"] = True
        # else: feature omitted — counter did not advance this window

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

        # RTPEngine pps_per_session — intentionally excluded.
        # The packets_per_second_(total) gauge is a point-in-time value that
        # resets to 0 between snapshots faster than the collection interval.
        # It's always 0 in training data and provides no signal.

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
        # Note: health indicators (ran_ue, gnb, upf_sessions, ims_registered)
        # are intentionally NOT included as features. They bake in assumptions
        # about UE/gNB count that don't generalize — a production network has
        # varying UE counts. These values are used internally for per-UE
        # normalization but not fed to the anomaly model.

        # Populate liveness for rate features (never filtered; used only for
        # silent-failure severity escalation at scoring time). A rate feature
        # is "live" if its underlying counter advanced in any of the last
        # _LIVENESS_LOOKBACK_WINDOWS snapshot pairs — i.e., the subsystem
        # was recently active regardless of whether it's active right now.
        for feature_name, counter_fkey in _RATE_COUNTER_MAP.items():
            if feature_name not in features:
                continue
            self._liveness[feature_name] = self._counter_advanced_recently(
                counter_fkey, _LIVENESS_LOOKBACK_WINDOWS
            )

        return features

    def _counter_advanced_recently(self, counter_fkey: str, n_windows: int) -> bool:
        """Check whether a counter advanced in any of the last n snapshot pairs.

        Consults the ring buffer maintained for rate computation. Returns
        False if history is too short to answer.
        """
        if len(self._history) < n_windows + 1:
            return False
        recent = self._history[-(n_windows + 1):]
        for i in range(len(recent) - 1):
            _, counters_prev = recent[i]
            _, counters_curr = recent[i + 1]
            prev = counters_prev.get(counter_fkey, 0)
            curr = counters_curr.get(counter_fkey, 0)
            if curr > prev:
                return True
        return False

    def liveness_signals(self) -> dict[str, bool]:
        """Return per-feature liveness signals from the most recent process() call.

        Maps OUTPUT feature name → True if the feature's underlying counter
        showed activity in the recent window. Consumed by the screener's
        silent-failure severity escalation. Returns a copy; mutating it does
        not affect internal state.
        """
        return dict(self._liveness)

    def reset(self) -> None:
        """Reset state (e.g., between training and monitoring)."""
        self._history.clear()
        self._liveness.clear()


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
        # Key charset must include parens (RTPEngine: errors_per_second_(total),
        # packets_per_second_(kernel)), colons (Kamailio: cdp:replies_received),
        # and slashes (RTPEngine: mixed_kernel/userspace_media_streams). Earlier
        # versions of this regex only allowed word-chars + colons, silently
        # dropping every paren-containing RTPEngine metric.
        if current_component:
            metric_match = re.match(r'"?([\w:()/-]+)"?\s*[=:]\s*(-?\d+\.?\d*)', stripped)
            if metric_match:
                key = metric_match.group(1)
                try:
                    result[current_component][key] = float(metric_match.group(2))
                except ValueError:
                    pass

    return result
