"""Recorder rendering for `ContainerDeadHop` attributions.

Pinpoints the two markdown surfaces that need to handle the new
attribution variant:

  1. `_first_attributed_index` — must recognize `container_dead` as a
     load-bearing attribution (alongside drops/latency/link-loss),
     otherwise the 🎯 marker doesn't appear next to the dead hop.
  2. `_format_hop_attribution_detail` — must render a useful one-cell
     description ("container `exited`") rather than the fallback
     `_unknown_` placeholder.

Task #61: cascading scenarios where a container has been killed (e.g.
`Cascading IMS Failure` kills pyhss + injects scscf latency) must now
show the dead container explicitly in the per-hop walk table.
"""

from __future__ import annotations

from agentic_chaos.recorder import (
    _first_attributed_index,
    _format_hop_attribution_detail,
)


# ---------------------------------------------------------------------------
# _format_hop_attribution_detail — single-cell rendering
# ---------------------------------------------------------------------------


def test_container_dead_renders_status_in_bold():
    """Operator-readable form. Bold so it stands out in the walk table
    next to the (also-bold) latency / drop rows."""
    attr = {"kind": "container_dead", "status": "exited", "detail": "pyhss exited"}
    rendered = _format_hop_attribution_detail(attr)
    assert "container" in rendered
    assert "exited" in rendered
    assert "**" in rendered  # bold


def test_container_dead_renders_absent_status():
    """An `absent` container (no such name) renders with its sentinel
    status — distinguishable from `exited` so the operator knows
    whether the container was removed vs. exited."""
    attr = {"kind": "container_dead", "status": "absent"}
    rendered = _format_hop_attribution_detail(attr)
    assert "absent" in rendered


def test_container_dead_renders_unknown_status_field_gracefully():
    """Defensive: if the status key is missing (shouldn't happen in
    practice — the dataclass requires it), render '?' not crash."""
    attr = {"kind": "container_dead"}
    rendered = _format_hop_attribution_detail(attr)
    assert "?" in rendered


# ---------------------------------------------------------------------------
# _first_attributed_index — load-bearing-attribution membership
# ---------------------------------------------------------------------------


def test_first_attributed_index_recognizes_container_dead():
    """The dead-container row must be findable by the marker placer so
    the 🎯 lands on the right row in the rendered walk table.

    `first_hop` is the FLAT `{node, kind, iface}` shape that
    `agentic_ops_v7.orchestrator._path_walk_report_to_dict` actually
    emits. The legacy `{"hop": {...}}` nesting was the pre-fix bug that
    suppressed every 🎯 marker on every episode.
    """
    walk_hops = [
        {"hop": {"node": "a", "iface": "eth0"}, "attribution": {"kind": "clean"}},
        {
            "hop": {"node": "pyhss", "iface": "eth0"},
            "attribution": {"kind": "container_dead", "status": "exited"},
        },
        {"hop": {"node": "c", "iface": "eth0"}, "attribution": {"kind": "clean"}},
    ]
    first_hop = {"node": "pyhss", "kind": "container", "iface": "eth0"}
    assert _first_attributed_index(walk_hops, first_hop) == 1


def test_first_attributed_index_still_recognizes_legacy_attributions():
    """Pin that adding container_dead didn't drop any existing kinds
    from the recognized-attribution set."""
    walk_hops = [
        {
            "hop": {"node": "scscf", "iface": "eth0"},
            "attribution": {"kind": "latency_at_hop", "observed_delay_ms": 2000},
        },
    ]
    first_hop = {"node": "scscf", "kind": "container", "iface": "eth0"}
    assert _first_attributed_index(walk_hops, first_hop) == 0


def test_first_attributed_index_returns_negative_one_on_malformed_first_hop():
    """The legacy code accepted a nested `{"hop": {...}}` shape; today's
    code rejects it. A nested-shape input must not crash and must
    cleanly return -1 so the renderer falls through to the no-marker
    path rather than throwing.
    """
    walk_hops = [
        {
            "hop": {"node": "pyhss", "iface": "eth0"},
            "attribution": {"kind": "container_dead", "status": "exited"},
        },
    ]
    legacy_nested = {"hop": {"node": "pyhss", "iface": "eth0"}}
    assert _first_attributed_index(walk_hops, legacy_nested) == -1


def test_first_attributed_index_returns_negative_one_on_none_or_empty():
    """Defensive: no first_hop, empty dict, None — all return -1."""
    walk_hops = []
    assert _first_attributed_index(walk_hops, None) == -1
    assert _first_attributed_index(walk_hops, {}) == -1
    assert _first_attributed_index(walk_hops, {"node": "x"}) == -1  # missing iface
