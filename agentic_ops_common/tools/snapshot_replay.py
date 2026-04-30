"""Snapshot-replay infrastructure for time-aware tools.

Per ADR `dealing_with_temporality_3.md` Layer 3, container-state
tools (kamcmd / rtpengine-ctl / pyhss / mongo) cannot natively
return historical state — they query the live in-process state at
call time. But the chaos framework's `ObservationTrafficAgent`
records the same data every 5s during the observation window into
`observation_snapshots`. This module exposes the matching helpers
so a time-aware tool can answer "what did this NF look like at
T?" instead of "what does this NF look like now?".

Two layers of plumbing here:

  - `set_observation_snapshots()` / `get_observation_snapshots()`
    — a contextvar carrying the snapshots from the orchestrator
    down into tool calls. The orchestrator populates it once per
    investigation; every tool call inside that investigation reads
    from it. Tools therefore don't need to change their function
    signature to accept snapshots — keeping the agent-facing API
    unchanged.

  - `find_closest_snapshot()` / `extract_metric_from_snapshot()`
    — pure helpers for matching a requested timestamp to a
    recorded snapshot, with explicit handling of "no snapshot
    within tolerance" (return None — the caller decides whether
    to fall back to live data or surface a "not available
    historically" error).

Snapshot format (matches what `ObservationTrafficAgent` writes):

    {
      "_timestamp": <float>,            # wall-clock at collection
      "amf":   {"metrics": {...}},
      "smf":   {"metrics": {...}},
      ...
      "pcscf": {"metrics": {...}},
    }

The "metrics" wrapping is consistent with `MetricsCollector.collect()`'s
output, which is what the framework feeds into observation_snapshots.
"""

from __future__ import annotations

import contextvars
from typing import Any, Optional


# 5s polling resolution → 5s drift tolerance. A request for ts=T finds
# the snapshot within ±5s of T; further than that, return None and
# let the caller surface the gap.
_MAX_SNAPSHOT_DRIFT_S = 5.0


# Contextvar carrying the observation snapshots for the current
# investigation. Default empty list so calling get_observation_snapshots()
# from a context with no plumbing returns cleanly.
_observation_snapshots_var: contextvars.ContextVar[list[dict[str, Any]]] = (
    contextvars.ContextVar("observation_snapshots", default=[])
)


def set_observation_snapshots(
    snapshots: Optional[list[dict[str, Any]]],
) -> None:
    """Register snapshots for tool calls in this context.

    Call once at the start of an investigation (the v6 orchestrator's
    `investigate()` entry point). The chaos framework provides these
    via the `metric_snapshots` kwarg passed in from challenger.py.

    Pass None or empty to clear (e.g., between unrelated investigations).
    """
    _observation_snapshots_var.set(list(snapshots) if snapshots else [])


def get_observation_snapshots() -> list[dict[str, Any]]:
    """Return whatever snapshots the orchestrator has registered for
    this context. Empty list when none have been set."""
    return _observation_snapshots_var.get()


def find_closest_snapshot(
    snapshots: list[dict[str, Any]],
    at_time_ts: float,
    max_drift_seconds: float = _MAX_SNAPSHOT_DRIFT_S,
) -> Optional[dict[str, Any]]:
    """Return the snapshot with `_timestamp` closest to `at_time_ts`,
    or None if no snapshot is within `max_drift_seconds`.

    None means "we don't have data for that moment" — the caller
    should NOT silently fall back to live data without surfacing the
    gap, because that defeats the time-anchoring contract.

    Snapshots without a usable `_timestamp` are skipped silently —
    they shouldn't exist in well-formed observation data.
    """
    if not snapshots:
        return None

    closest = None
    best_drift = float("inf")
    for snap in snapshots:
        ts = snap.get("_timestamp")
        if not isinstance(ts, (int, float)):
            continue
        drift = abs(float(ts) - at_time_ts)
        if drift < best_drift:
            best_drift = drift
            closest = snap

    if closest is None or best_drift > max_drift_seconds:
        return None
    return closest


def extract_metric_from_snapshot(
    snapshot: dict[str, Any],
    nf: str,
    metric_name: str,
) -> Optional[float]:
    """Pull a single raw metric value from a snapshot.

    Returns None if the NF or the metric is absent from the snapshot.
    The snapshot's per-NF dict can be either flat (`{key: value}`) or
    wrapped (`{"metrics": {key: value}}`) — both shapes are accepted
    to match what `MetricsCollector.collect()` actually produces.
    """
    nf_data = snapshot.get(nf)
    if not isinstance(nf_data, dict):
        return None
    metrics = nf_data.get("metrics", nf_data) if "metrics" in nf_data else nf_data
    if not isinstance(metrics, dict):
        return None
    val = metrics.get(metric_name)
    if not isinstance(val, (int, float)) or isinstance(val, bool):
        return None
    return float(val)


def extract_nf_metrics(
    snapshot: dict[str, Any],
    nf: str,
) -> dict[str, float]:
    """Pull all raw numeric metrics for one NF from a snapshot.

    Returns an empty dict if the NF is absent or has no numeric
    metrics. Non-numeric values (badge strings, etc.) are filtered out.
    """
    nf_data = snapshot.get(nf)
    if not isinstance(nf_data, dict):
        return {}
    metrics = nf_data.get("metrics", nf_data) if "metrics" in nf_data else nf_data
    if not isinstance(metrics, dict):
        return {}
    return {
        k: float(v) for k, v in metrics.items()
        if isinstance(v, (int, float)) and not isinstance(v, bool)
        and not k.startswith("_")
    }
