"""Data plane quality gauges — RTPEngine + UPF via Prometheus.

Queries Prometheus for real-time data plane health over a 30-second
window. Returns RTPEngine media quality (pps, MOS, packet loss, jitter)
and UPF throughput (pps, KB/s in/out) as pre-computed rates.

Backed by Prometheus scraping RTPEngine's native /metrics endpoint
and the existing Open5GS UPF exporter — no custom collection needed.

Metrics with a matching KB entry are rendered through the unified
`_render_metric_with_full_kb_block` helper from `diagnostic_metrics.py`,
so the LLM sees the full authored semantics — `what_it_signals`, the
value-specific `meaning.*` variant, every `disambiguators` entry — at
the point of observation. See ADR
`expose_kb_disambiguators_to_investigator.md`.
"""

from __future__ import annotations

import httpx

from ._common import _get_deps
from agentic_ops_common.metric_kb import load_kb
from agentic_ops_common.tools.diagnostic_metrics import (
    _render_metric_with_full_kb_block,
)

_DEFAULT_WINDOW_SECONDS = 120

# PromQL query templates — `{w}` is substituted with the caller's window.
# Each rate() query uses the caller-selected window to compute per-second
# values. Instant gauges (rtp_sessions, upf_sessions) do not use a window.
_QUERY_TEMPLATES = {
    # RTPEngine media quality
    "rtp_pps": 'rate(rtpengine_packets_total{{type="userspace"}}[{w}s])',
    "rtp_bytes_ps": 'rate(rtpengine_bytes_total{{type="userspace"}}[{w}s])',
    "rtp_sessions": 'rtpengine_sessions{{type="own"}}',
    "rtp_mos_rate": "rate(rtpengine_mos_total[{w}s])",
    "rtp_mos_samples_rate": "rate(rtpengine_mos_samples_total[{w}s])",
    "rtp_loss_rate": "rate(rtpengine_packetloss_total[{w}s])",
    "rtp_loss_samples_rate": "rate(rtpengine_packetloss_samples_total[{w}s])",
    "rtp_jitter_rate": "rate(rtpengine_jitter_total[{w}s])",
    "rtp_jitter_samples_rate": "rate(rtpengine_jitter_samples_total[{w}s])",
    # UPF data plane
    "upf_in_pps": "rate(fivegs_ep_n3_gtp_indatapktn3upf[{w}s])",
    "upf_out_pps": "rate(fivegs_ep_n3_gtp_outdatapktn3upf[{w}s])",
    "upf_in_bps": 'rate(fivegs_ep_n3_gtp_indatavolumeqosleveln3upf{{qfi="1"}}[{w}s])',
    "upf_out_bps": 'rate(fivegs_ep_n3_gtp_outdatavolumeqosleveln3upf{{qfi="1"}}[{w}s])',
    "upf_sessions": "fivegs_upffunction_upf_sessionnbr",
}


def _build_queries(window_seconds: int) -> dict[str, str]:
    """Substitute the window into each template."""
    return {k: v.format(w=window_seconds) for k, v in _QUERY_TEMPLATES.items()}


import logging

_log = logging.getLogger("dp-gauges")


async def _prom_query(
    client: httpx.AsyncClient,
    url: str,
    query: str,
    at_time_ts: float | None = None,
) -> float:
    """Run a single PromQL instant query, return scalar or 0.

    When `at_time_ts` is provided, the query is evaluated at that
    Unix timestamp instead of "now" — Prometheus's `?time=` parameter.
    The PromQL string itself is unchanged; the API endpoint just
    interprets it as if the clock said `at_time_ts`. This is the
    Layer 2 entry point for the time-aware investigation architecture
    (ADR `dealing_with_temporality_3.md`).
    """
    try:
        params: dict[str, str | float] = {"query": query}
        if at_time_ts is not None:
            params["time"] = at_time_ts
        resp = await client.get(f"{url}/api/v1/query", params=params)
        if resp.status_code != 200:
            _log.warning("Prometheus HTTP %d for query: %s", resp.status_code, query[:80])
            return 0
        body = resp.json()
        results = body.get("data", {}).get("result", [])
        if results:
            val = float(results[0]["value"][1])
            if val != 0:
                _log.debug("Query %s = %s", query[:60], val)
            return val
        _log.debug("Empty result for: %s", query[:60])
    except Exception as e:
        _log.warning("Prometheus query failed: %s — %s", query[:60], e)
    return 0


def _safe_div(numerator: float, denominator: float) -> float:
    return round(numerator / denominator, 2) if denominator > 0 else 0


async def get_dp_quality_gauges(
    window_seconds: int = _DEFAULT_WINDOW_SECONDS,
    at_time_ts: float | None = None,
) -> str:
    """Get data plane quality gauges over a window.

    Queries Prometheus for RTPEngine media quality and UPF throughput
    rates. Returns pre-computed values — no PromQL knowledge needed.

    Args:
        window_seconds: Lookback window in seconds for all rate() queries.
            Default 120 (2 minutes). Start narrow. Widen to 300 (5 min)
            or 900 (15 min) only if nothing interesting is found at the
            default window. Values less than 10 are clamped to 10.
        at_time_ts: Optional Unix timestamp to anchor the query at. When
            None (default), the rate window is `[now - window_seconds,
            now]`. When set, the rate window is
            `[at_time_ts - window_seconds, at_time_ts]` — useful when
            investigating an anomaly that happened a minute ago and
            traffic has since stopped (the screener captured the
            failure at a known timestamp, see ADR
            `dealing_with_temporality_3.md`). Pass the orchestrator's
            `anomaly_screener_snapshot_ts` here to anchor on the
            screener's reading.

    Gauges returned:
      RTPEngine: packets/sec, KB/s, MOS (recent), packet loss (recent),
                 jitter (recent), active sessions
      UPF:       packets/sec in/out, KB/s in/out, active sessions

    Use this to detect data plane degradation:
    - RTP pps drops during active call = packet loss on media path
    - UPF out KB/s << UPF in KB/s = packet loss at the UPF
    - MOS dropping below 3.5 = voice quality degradation
    - UPF pps = 0 with active sessions = data plane dead
    """
    window_seconds = max(10, int(window_seconds))
    queries = _build_queries(window_seconds)

    deps = _get_deps()
    prom_ip = deps.env.get("METRICS_IP", "172.22.0.36")
    prom_url = f"http://{prom_ip}:9090"

    try:
        import asyncio
        async with httpx.AsyncClient(timeout=5.0) as client:
            keys = list(queries.keys())
            values = await asyncio.gather(
                *(_prom_query(client, prom_url, q, at_time_ts=at_time_ts)
                  for q in queries.values())
            )
            results = dict(zip(keys, values))

    except Exception as e:
        return f"Data plane gauge error: cannot reach Prometheus at {prom_url}: {e}"

    # Compute derived values. The MOS / loss / jitter ratios are
    # explicitly rendered as "N/A (no samples in window)" when the
    # denominator's rate is zero — without this, a 0 in the numerator
    # is indistinguishable from "loss = 0%" (healthy) vs "no media
    # flowing in this window" (which is what produced the disproven-
    # by-stale-data verdict in run_20260429_163802 — see ADR
    # `dealing_with_temporality_3.md` Layer 1 motivation).
    rtp_pps = round(results["rtp_pps"], 1)
    rtp_kbps = round(results["rtp_bytes_ps"] / 1024, 2)
    rtp_sessions = int(results["rtp_sessions"])
    rtp_mos = _ratio_or_no_data(results["rtp_mos_rate"], results["rtp_mos_samples_rate"])
    rtp_loss = _ratio_or_no_data(results["rtp_loss_rate"], results["rtp_loss_samples_rate"])
    rtp_jitter = _ratio_or_no_data(results["rtp_jitter_rate"], results["rtp_jitter_samples_rate"])
    rtp_loss_value = _ratio_or_none(results["rtp_loss_rate"], results["rtp_loss_samples_rate"])

    upf_in_pps = round(results["upf_in_pps"], 1)
    upf_out_pps = round(results["upf_out_pps"], 1)
    upf_in_kbps = round(results["upf_in_bps"] / 1024, 2)
    upf_out_kbps = round(results["upf_out_bps"] / 1024, 2)
    upf_sessions = int(results["upf_sessions"])

    if at_time_ts is None:
        header = f"Data Plane Quality Gauges (last {window_seconds}s):"
    else:
        # Surface the anchor in the header so the agent can verify it
        # asked the question it intended to ask.
        header = (
            f"Data Plane Quality Gauges (window: {window_seconds}s, "
            f"anchored at ts={at_time_ts:.0f}):"
        )

    # Load the KB so we can route metrics with rich content through the
    # unified renderer. KB load failure is non-fatal — we fall back to
    # plain rendering so the probe still produces useful output.
    try:
        kb = load_kb()
    except Exception:
        kb = None

    lines = [
        header,
        "",
        "  RTPEngine:",
        f"    packets/sec    : {rtp_pps}",
        f"    throughput     : {rtp_kbps} KB/s",
        f"    MOS (recent)   : {rtp_mos}",
    ]
    # `loss (recent)` has a rich KB entry with disambiguators that point
    # the LLM at errors_per_second and UPF directional rates — exactly
    # the reasoning that prevents the false-DISPROVEN trap documented in
    # ADR `expose_kb_disambiguators_to_investigator.md`. Route through
    # the unified renderer so the disambiguator block appears inline.
    lines.extend(_render_kb_metric_block(
        label="loss (recent)",
        kb_id="ims.rtpengine.loss_ratio",
        value=rtp_loss_value,
        plain_value_str=rtp_loss,
        kb=kb,
    ))
    lines.extend([
        f"    jitter (recent): {rtp_jitter}",
        f"    active sessions: {rtp_sessions}",
        "",
        "  UPF:",
        f"    in  packets/sec: {upf_in_pps}",
        f"    out packets/sec: {upf_out_pps}",
        f"    in  throughput : {upf_in_kbps} KB/s",
        f"    out throughput : {upf_out_kbps} KB/s",
        f"    active sessions: {upf_sessions}",
    ])
    # Append the upf_counters_are_directional verdict in the rate-window
    # form. The agent must never read in/out asymmetry as packet loss;
    # the verdict says so explicitly with the asymmetry % and the three
    # correct loss-detection methods inline. See ADR
    # `upf_directional_rates_in_dp_quality_gauges.md`.
    lines.extend(_render_upf_directional_verdict(
        upf_in_pps=upf_in_pps,
        upf_out_pps=upf_out_pps,
        window_seconds=window_seconds,
    ))
    return "\n".join(lines)


def _render_upf_directional_verdict(
    *,
    upf_in_pps: float,
    upf_out_pps: float,
    window_seconds: int,
) -> list[str]:
    """Render the upf_counters_are_directional rule's verdict for the
    rate-windowed pair, inline with the UPF block.

    The pure evaluator at `network_ontology.rules.upf_directional`
    handles asymmetry computation and severity selection; this
    function only concerns itself with formatting.

    On evaluator-import failure, emit a single line noting the rule
    was unavailable — the probe must keep producing values regardless.
    """
    try:
        from network_ontology.rules import evaluate_upf_directional_rule
    except Exception as e:
        return [
            "    rule verdict   : (upf_counters_are_directional "
            f"unavailable: {e})"
        ]

    verdicts = evaluate_upf_directional_rule({
        "upf_in_pps": upf_in_pps,
        "upf_out_pps": upf_out_pps,
    })
    if not verdicts:
        # Should not happen given numeric values were passed, but
        # defensive — if the evaluator returned nothing, surface it.
        return ["    rule verdict   : (upf_counters_are_directional did not fire)"]

    v = verdicts[0]
    lines = [
        f"    asymmetry      : {v['asymmetry_pct']}%   (|in - out| / max)",
        (
            f"    rule verdict   : upf_counters_are_directional "
            f"[severity={v['severity']}, window_kind={v['window_kind']}]"
        ),
    ]
    # The verdict text can be multi-line; render each line indented.
    for vline in v["verdict"].rstrip().splitlines():
        lines.append(f"                     {vline}")
    lines.append("    correct_methods (for actual loss detection):")
    for i, method in enumerate(v["correct_methods"], start=1):
        # Each method may be multi-line; indent continuation lines.
        method_lines = method.splitlines() or [method]
        lines.append(f"      {i}. {method_lines[0]}")
        for cont in method_lines[1:]:
            lines.append(f"         {cont}")
    return lines


def _render_kb_metric_block(
    *,
    label: str,
    kb_id: str,
    value: float | None,
    plain_value_str: str,
    kb,
) -> list[str]:
    """Render a data-plane gauge through the unified KB-block helper.

    `value` is the numeric value (or None when the gauge resolved to
    "N/A — no samples in window"). `plain_value_str` is the human-
    readable string the probe already computed (e.g. "25.05" or
    "N/A (no samples in window)") — used as a header line so the
    existing UI shape is preserved when the KB is unavailable or the
    metric has no rich content.

    Behavior:
      - KB unavailable OR no entry for kb_id: emit a single
        plain-rendered line (`    label : plain_value_str`).
      - Entry present: emit the same header line plus the unified
        renderer's full block (what_it_signals, meaning.*, every
        disambiguator). Disambiguator partner lookups resolve via the
        renderer's snapshot/feature lookup; the data-plane probe
        passes empty maps, so partner values surface as "not in
        snapshot" — the disambiguator TEXT still renders in full.
    """
    header_line = f"    {label}  : {plain_value_str}"
    if kb is None:
        return [header_line]
    entry = kb.get_metric(kb_id)
    if entry is None:
        return [header_line]
    block = _render_metric_with_full_kb_block(
        label=label,
        value=value,
        entry=entry,
        kb=kb,
        raw_snapshot={},
        features={},
        learned_value=None,
    )
    # The unified renderer's first line is `    label = value [...]`,
    # which duplicates the header in a different shape. Preserve the
    # probe's existing `label : value_str` header (so MOS / loss
    # rendering look uniform), then append everything but the
    # renderer's own header line.
    if block:
        return [header_line] + block[1:]
    return [header_line]


def _ratio_or_no_data(numerator: float, denominator: float) -> str:
    """Render a per-sample average like MOS, loss-per-RR, or jitter-per-RR.

    When the denominator (samples_rate) is zero, NO samples landed in
    the window — the ratio is undefined. Today's `_safe_div` collapses
    this case to `0`, which agents have repeatedly read as "0% loss /
    silence is good" when it actually means "no data in window /
    nothing to measure." Render it explicitly as N/A so the agent
    can't conflate the two.

    See ADR `dealing_with_temporality_3.md` (Layer 1 motivation
    section) and `run_20260429_163802_call_quality_degradation.md`.
    """
    if denominator <= 0:
        return "N/A (no samples in window)"
    return f"{numerator / denominator:.2f}"


def _ratio_or_none(numerator: float, denominator: float) -> float | None:
    """Companion to `_ratio_or_no_data` that returns the numeric ratio
    or None (rather than the human-readable string).

    Used by the KB-routing path so the unified renderer can apply the
    `meaning.*` variant selection on a real number, falling through to
    "value not available" when the window had no samples.
    """
    if denominator <= 0:
        return None
    return numerator / denominator
