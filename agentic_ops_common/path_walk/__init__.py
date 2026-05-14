"""Path-walk machinery — types, prober contract, lab probers, registry.

See ADR `path_anchored_probe_planning_for_transport_layer_faults.md`.

Public surface:
    Hop, HopKind                — topology entry types
    HopAttribution              — closed-enum of per-hop verdicts:
                                  CleanHop, DropsAttributedHere,
                                  DropsAttributedToInboundLink,
                                  LatencyAtHop, InconclusiveHop,
                                  ContainerDeadHop
    HopRecord, PathWalkReport   — walker output
    HopProber                   — Protocol every prober implements
    KernelHopProber             — lab prober (containers, host kernel)
    DockerBridgeProber          — lab prober (host bridge)
    prober_for_kind(...)        — registry dispatch
"""

from .protocol import (
    CleanHop,
    ContainerDeadHop,
    DropsAttributedHere,
    DropsAttributedToInboundLink,
    Hop,
    HopAttribution,
    HopKind,
    HopProber,
    HopRecord,
    InconclusiveHop,
    LatencyAtHop,
    PathWalkReport,
)

# Probers + registry land below; importing them at the package level
# is convenient for the walker. The registry import is lazy (function
# call) to avoid pulling probe execution dependencies at import time.
from .probers.kernel import KernelHopProber  # noqa: E402
from .probers.docker_bridge import DockerBridgeProber  # noqa: E402
from .probers.registry import prober_for_kind  # noqa: E402

__all__ = [
    "CleanHop",
    "ContainerDeadHop",
    "DockerBridgeProber",
    "DropsAttributedHere",
    "DropsAttributedToInboundLink",
    "Hop",
    "HopAttribution",
    "HopKind",
    "HopProber",
    "HopRecord",
    "InconclusiveHop",
    "KernelHopProber",
    "LatencyAtHop",
    "PathWalkReport",
    "prober_for_kind",
]
