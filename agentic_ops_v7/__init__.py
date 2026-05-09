"""agentic_ops v7 — classifier-driven pipeline with deterministic transport-layer localization.

v7 carves out **transport-layer faults** (kernel qdisc drops, NIC errors,
bridge / vSwitch issues, switch port discards, IPsec replay failures, BGP
withdraw blackholes — anything below the application's recv()/send() API)
from the per-NF LLM-driven hypothesis pipeline and routes them through a
deterministic path walk that asks each hop's native transport-layer
telemetry "did packets die here?".

Application-layer faults (stuck Diameter peer, misconfigured Kamailio,
etc.) continue through the inherited NA -> IG -> Investigator -> Synthesis
pipeline that v7 carries as its own copy of v6's phase implementations.

**Self-containment rule (load-bearing):** v7 is *not allowed to import
from any prior version*. Allowed dependencies are `agentic_ops_common.*`,
standard library, and third-party packages. Code from v6 that v7 needs is
copied here, not imported. See ADR
`docs/ADR/path_anchored_probe_planning_for_transport_layer_faults.md`
for the rationale and the static-analysis CI gate that enforces the rule
(`tests/test_v7_has_no_prior_version_imports.py`).
"""
