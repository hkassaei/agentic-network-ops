"""HopProber registry — hop_kind → prober dispatch.

The walker calls `prober_for_kind(hop.kind)` to get the right prober
implementation for each hop. Registration is import-time: every prober
class is registered against its `supported_kinds` tuple. Future
carrier-grade probers register themselves the same way.

Multiple probers can register for the same hop_kind; the walker
composes their attributions per the rules in
`agentic_ops_common.path_walk.protocol.HopAttribution` (any
`drops_attributed_here` wins; otherwise `clean` if all clean;
otherwise `inconclusive`). Today every kind has a single registered
prober.

If `prober_for_kind` is asked about an unregistered hop_kind, it raises
`KeyError` — the walker treats this as a topology-authoring bug, not a
runtime gap. Authoring a flow with `hop_kind: l3_router` requires a
registered `SNMPHopProber`; until that ADR lands, the path resolver
must not produce hops of that kind.
"""

from __future__ import annotations

from ..protocol import HopKind, HopProber
from .docker_bridge import DockerBridgeProber
from .kernel import KernelHopProber


# kind -> list of prober instances (currently always 1 per kind).
_REGISTRY: dict[HopKind, list[HopProber]] = {}


def _register(prober: HopProber) -> None:
    for kind in prober.supported_kinds:
        _REGISTRY.setdefault(kind, []).append(prober)


# Lab probers — registered at import time.
_register(KernelHopProber())
_register(DockerBridgeProber())


def prober_for_kind(kind: HopKind) -> HopProber:
    """Return the registered prober for `kind`.

    Raises KeyError if no prober is registered. Today this means the
    path resolver produced a hop for a kind the lab doesn't ship a
    prober for (e.g. `l3_router` before `SNMPHopProber` lands). A
    follow-up ADR adds the prober and the path resolver gains the
    capability simultaneously.
    """
    if kind not in _REGISTRY:
        raise KeyError(
            f"no HopProber registered for kind={kind!r}; "
            f"registered kinds: {sorted(_REGISTRY)}"
        )
    return _REGISTRY[kind][0]


def all_probers_for_kind(kind: HopKind) -> list[HopProber]:
    """Return every prober registered for `kind`.

    The walker uses this when `compose_probers=True` — multiple probers
    on one hop. Today each kind has one prober; the function is here
    so the walker's composition logic doesn't have to special-case
    single-prober kinds.
    """
    return list(_REGISTRY.get(kind, []))


def registered_kinds() -> list[HopKind]:
    """Return all hop kinds with at least one registered prober.

    Used by `test_hop_prober_protocol_compliance` to assert coverage
    against the set of kinds the path resolver may produce.
    """
    return sorted(_REGISTRY)
