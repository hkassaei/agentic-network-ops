"""PathWalkInvestigator — Python (non-LLM) walker for transport-layer paths.

Per ADR `path_anchored_probe_planning_for_transport_layer_faults.md`,
when the SymptomClassifier labels an episode `transport_layer` (or
`mixed`) and the PathResolver produced an ordered hop list, this
walker traverses the list and produces a structured `PathWalkReport`.

The walker is deliberately deterministic — no LLM, no narrative
reasoning. The kernel and network elements are the source of truth
for "did packets die at this hop"; adding an LLM in the middle of
"ask the source-of-truth, then report" is variance-injection without
upside (see ADR §"Why deterministic, not LLM-mediated").

Walk algorithm:

  1. For each hop in topology order:
       - dispatch via `prober_for_kind(hop.kind)`
       - run `prober.probe(hop, window_seconds, anchor_ts)`
       - record the resulting `HopAttribution`
  2. For each adjacent pair of CONTAINER hops:
       - run `get_link_rate_diff(prev, curr, "a_to_b", window)` and
         optionally `"b_to_a"` to attribute loss to a link rather
         than to either endpoint
       - record as a synthetic `bridge`-pseudo-hop attribution if
         the link diff exceeds a noise floor
  3. Emit `PathWalkReport` with the full ordered record list.

The walker stops short-circuiting on first attribution because the
bisection report's value is the *whole walk* — operators want to see
that every other hop is clean, not just that one hop dropped. Total
runtime in the lab: a few hundred milliseconds for ~15 hops; minutes
worst-case in carrier deployments depending on SNMP polling latency.

Failure paths:
  - A prober that raises gets recorded as `InconclusiveHop(reason="prober_raised")`.
  - Probers returning `InconclusiveHop` (e.g. tool_unavailable per the
    toolbelt ADR) are recorded as-is — never silently rebranded to
    clean.
  - An empty hop list is rejected at the public entry point: callers
    get an exception so a bug in the resolver is loud, not silent.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from agentic_ops_common.path_walk import (
    DropsAttributedToInboundLink,
    Hop,
    HopRecord,
    InconclusiveHop,
    PathWalkReport,
    prober_for_kind,
)


log = logging.getLogger("agentic_ops_v7.path_walk_investigator")


# Default window for rate-based probes (link-rate-diff, etc.). 5 s is
# enough for the docker_open5gs lab where chaos faults inject ≥5 pps;
# carrier deployments may want longer windows for low-rate flows.
DEFAULT_WINDOW_SECONDS = 5

# Noise floor for inter-hop link-rate-diff attribution. Below this
# threshold we don't claim "the link is dropping" — small TX/RX
# imbalances from sample timing alone happen routinely.
LINK_LOSS_NOISE_FLOOR_PCT = 0.05  # 5%


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def walk_path(
    flow_id: str,
    hops: list[Hop],
    anchor_ts: Optional[float] = None,
    window_seconds: int = DEFAULT_WINDOW_SECONDS,
    direction: str = "both",
    enable_inter_hop_diff: bool = True,
) -> PathWalkReport:
    """Walk a resolved path and produce a structured report.

    Args:
        flow_id: The flow whose hop list this walks (e.g. "vonr_media").
        hops:    Ordered list of `Hop` from the path resolver.
        anchor_ts: Optional anomaly-window timestamp for time-aware probes.
        window_seconds: Sampling window for rate-based probes.
        direction: "uplink" | "downlink" | "both" — labels the report.
        enable_inter_hop_diff: When True, run `get_link_rate_diff`
            between adjacent container hops. Off lets unit tests
            exercise per-hop probing without paying the rate-diff cost.

    Returns:
        PathWalkReport with one HopRecord per hop. The report's
        `is_localized` / `first_attributed_hop` accessors drive
        Synthesis's `localized` verdict.

    Raises:
        ValueError: hops list is empty (resolver bug).
    """
    if not hops:
        raise ValueError(
            "PathWalkInvestigator was given an empty hop list — "
            "the path resolver should have returned None instead."
        )

    log.info(
        "PathWalkInvestigator: walking flow=%s, %d hops, window=%ds",
        flow_id, len(hops), window_seconds,
    )
    records = await _walk_hops(hops, window_seconds, anchor_ts)
    if enable_inter_hop_diff:
        records = await _augment_with_inter_hop_diff(
            records, window_seconds, anchor_ts,
        )

    report = PathWalkReport(
        flow_id=flow_id,
        direction=direction,
        hops=records,
        anchor_ts=anchor_ts,
        window_seconds=window_seconds,
    )
    log.info(
        "PathWalkInvestigator: localized=%s, first_attributed=%s",
        report.is_localized,
        report.first_attributed_hop.hop.node if report.first_attributed_hop else None,
    )
    return report


# ---------------------------------------------------------------------------
# Per-hop walk
# ---------------------------------------------------------------------------


async def _walk_hops(
    hops: list[Hop],
    window_seconds: int,
    anchor_ts: Optional[float],
) -> list[HopRecord]:
    """Run every hop's registered prober. One probe call per hop."""
    out: list[HopRecord] = []
    for hop in hops:
        try:
            prober = prober_for_kind(hop.kind)
        except KeyError as e:
            # Topology authored a hop_kind for which no prober is
            # registered. Surface explicitly — the walker doesn't
            # silently skip topology authoring bugs.
            out.append(HopRecord(
                hop=hop,
                attribution=InconclusiveHop(
                    reason="no_prober_registered",
                    detail=str(e),
                ),
                prober="<unregistered>",
            ))
            continue

        try:
            attribution = await prober.probe(hop, window_seconds, anchor_ts)
        except Exception as e:
            log.warning(
                "Prober raised on hop %s[%s]: %s",
                hop.node, hop.iface, e, exc_info=True,
            )
            attribution = InconclusiveHop(
                reason="prober_raised",
                detail=f"{type(e).__name__}: {e}",
            )

        prober_name = type(prober).__name__
        out.append(HopRecord(hop=hop, attribution=attribution, prober=prober_name))
    return out


# ---------------------------------------------------------------------------
# Inter-hop link-rate-diff augmentation
# ---------------------------------------------------------------------------


async def _augment_with_inter_hop_diff(
    records: list[HopRecord],
    window_seconds: int,
    anchor_ts: Optional[float],
) -> list[HopRecord]:
    """Where two adjacent CONTAINER records both came back clean,
    sample link-rate-diff between them. If the diff exceeds the
    noise floor, attribute the loss to the inbound link of the
    second record.

    Bridge hops (which sit between every container pair in the lab)
    are NOT modified here — `DockerBridgeProber` already attributes
    bridge-side iptables/conntrack drops directly. This augmentation
    catches the case where neither container's qdisc/iface drops
    anything but their TX/RX delta is non-trivial — i.e. loss
    happened on the link itself, not at either endpoint.

    The lab's "loss between containers" scenarios are rare (Phase 6's
    bridge_loss generalization scenario is the load-bearing one);
    this hook makes that scenario localizable today.
    """
    from agentic_ops_common.tools.reachability import get_link_rate_diff

    augmented = list(records)
    for i in range(len(augmented) - 1):
        prev_rec = augmented[i]
        curr_rec = augmented[i + 1]

        # Only run between two CLEAN container hops. Skip bridges,
        # already-attributed hops, and inconclusive ones.
        if prev_rec.hop.kind != "container" or curr_rec.hop.kind != "container":
            continue
        if prev_rec.attribution.kind != "clean":
            continue
        if curr_rec.attribution.kind != "clean":
            continue

        try:
            diff = await get_link_rate_diff(
                container_a=prev_rec.hop.node,
                iface_a=prev_rec.hop.iface,
                container_b=curr_rec.hop.node,
                iface_b=curr_rec.hop.iface,
                direction="a_to_b",
                window_seconds=window_seconds,
            )
        except Exception as e:
            log.warning(
                "get_link_rate_diff raised on %s -> %s: %s",
                prev_rec.hop.node, curr_rec.hop.node, e, exc_info=True,
            )
            continue

        if "_error" in diff:
            log.info(
                "link-rate-diff unavailable on %s -> %s: %s",
                prev_rec.hop.node, curr_rec.hop.node, diff["_error"],
            )
            continue

        attributed_loss = diff.get("attributed_loss_pct")
        if attributed_loss is None or attributed_loss < LINK_LOSS_NOISE_FLOOR_PCT:
            continue

        # Replace the curr_rec's attribution with a link-drop one.
        log.info(
            "link-rate-diff attributes %.1f%% loss on %s -> %s link",
            attributed_loss * 100,
            prev_rec.hop.node, curr_rec.hop.node,
        )
        augmented[i + 1] = HopRecord(
            hop=curr_rec.hop,
            attribution=DropsAttributedToInboundLink(
                observed_loss_pct=attributed_loss,
                tx_rate=diff.get("tx_rate_pkts_per_s", 0.0),
                rx_rate=diff.get("rx_rate_pkts_per_s", 0.0),
                evidence=diff.get("evidence", ""),
            ),
            prober="get_link_rate_diff",
        )
    return augmented
