"""Network topology — live 3GPP interface graph with link status."""

from __future__ import annotations
import sys
from ._common import _REPO_ROOT, _get_deps

_NOC_HIDDEN_NODES = {"nr_gnb", "e2e_ue1", "e2e_ue2"}
_BOUNDARY_LABELS = {"nr_gnb": "[RAN]", "e2e_ue1": "[UE]", "e2e_ue2": "[UE]"}


async def get_network_topology() -> str:
    """Get the live network topology: nodes, link status, and connectivity graph.

    Shows which containers are running/down, how they connect via 3GPP
    interfaces (N2, N4, Gm, Cx, etc.), and which links are active vs
    inactive. INACTIVE links mean a broken path.
    """
    gui_dir = str(_REPO_ROOT / "gui")
    if gui_dir not in sys.path:
        sys.path.insert(0, gui_dir)

    from topology import build_topology

    deps = _get_deps()
    topo = await build_topology(deps.env)

    visible_nodes = [n for n in topo.nodes if n.id not in _NOC_HIDDEN_NODES]
    hidden_status = {n.id: n.status for n in topo.nodes if n.id in _NOC_HIDDEN_NODES}

    by_layer: dict[str, list] = {}
    for n in visible_nodes:
        by_layer.setdefault(n.layer, []).append(n)

    lines = [f"Network Topology — Phase: {topo.phase}\n"]
    for layer in ["data", "core", "ims"]:
        nodes = by_layer.get(layer, [])
        if nodes:
            entries = [f"{n.label}({n.status})" for n in nodes]
            lines.append(f"  {layer}: {', '.join(entries)}")

    inactive: list[str] = []
    active: list[str] = []

    for e in topo.edges:
        if e.logical:
            continue
        src_hidden = e.source in _NOC_HIDDEN_NODES
        tgt_hidden = e.target in _NOC_HIDDEN_NODES
        src_label = _BOUNDARY_LABELS.get(e.source, e.source.upper())
        tgt_label = _BOUNDARY_LABELS.get(e.target, e.target.upper())
        if not src_hidden:
            node = next((n for n in visible_nodes if n.id == e.source), None)
            src_label = node.label if node else e.source.upper()
        if not tgt_hidden:
            node = next((n for n in visible_nodes if n.id == e.target), None)
            tgt_label = node.label if node else e.target.upper()
        link_str = f"  {e.label}: {src_label} → {tgt_label}"
        if not e.active:
            reasons = []
            if src_hidden and hidden_status.get(e.source) != "running":
                reasons.append(f"{src_label} not connected")
            elif not src_hidden:
                node = next((n for n in visible_nodes if n.id == e.source), None)
                if node and node.status != "running":
                    reasons.append(f"{src_label} is {node.status}")
            if tgt_hidden and hidden_status.get(e.target) != "running":
                reasons.append(f"{tgt_label} not connected")
            elif not tgt_hidden:
                node = next((n for n in visible_nodes if n.id == e.target), None)
                if node and node.status != "running":
                    reasons.append(f"{tgt_label} is {node.status}")
            reason = " — " + ", ".join(reasons) if reasons else ""
            inactive.append(f"{link_str} [INACTIVE{reason}]")
        else:
            active.append(f"{link_str} [active]")

    lines.append("")
    if inactive:
        lines.append(f"INACTIVE LINKS ({len(inactive)}):")
        lines.extend(inactive)
        lines.append("")
    lines.append(f"ACTIVE LINKS ({len(active)}):")
    lines.extend(active)
    return "\n".join(lines)
