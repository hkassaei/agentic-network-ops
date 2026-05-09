# ADR: Path-Anchored Probe Planning for Transport-Layer Faults

**Date:** 2026-05-08
**Status:** Proposed
**Related:**
- Failing run: [`../../agentic_ops_v6/docs/agent_logs/run_20260506_132418_call_quality_degradation.md`](../../agentic_ops_v6/docs/agent_logs/run_20260506_132418_call_quality_degradation.md). Ground truth: 30% packet loss on `rtpengine` egress. Agent's diagnosis: UPF (incorrect, "promoted" with low confidence). The full disambiguator-rendering ADR was implemented and active during this run, and the LLM still mis-diagnosed — see Context for the structural reason.
- [`expose_kb_disambiguators_to_investigator.md`](expose_kb_disambiguators_to_investigator.md) — KB-content rendering fix; necessary but, on its own, insufficient when the fault is below the application layer. This ADR layers on top.
- [`falsifier_investigator_and_rag.md`](falsifier_investigator_and_rag.md) — defines the per-NF hypothesis / falsification-plan model this ADR carves out for the *transport-layer* class only.
- [`upf_directional_rates_in_dp_quality_gauges.md`](upf_directional_rates_in_dp_quality_gauges.md), [`upf_counters_directional_stack_rule.md`](upf_counters_directional_stack_rule.md) — companion KB rules for directional reasoning; the path-walk machinery this ADR builds is the natural home for those rules.
- [`structural_guardrails_for_llm_pipeline.md`](structural_guardrails_for_llm_pipeline.md) — general principle that load-bearing pipeline behavior must be enforced structurally, not by soft prompt rules.
- [`nf_container_diagnostic_tooling.md`](nf_container_diagnostic_tooling.md) — toolbelt audit and `outcome="tool_unavailable"` semantics; the path walk piggybacks on the toolbelt to guarantee `tc`, `ip`, `ss` are uniformly available at every container hop.

---

## Decision

We classify faults the agent must diagnose into two structurally distinct families and route each through the right-shaped pipeline:

- **Application-layer faults** — the cause lives in an NF's process: stuck Diameter peer, misconfigured Kamailio, broken Python in a CSCF script, exhausted DB connection pool, bad cache state, mis-provisioned subscriber. NF-level metrics see the cause directly. The current v6 NA → IG → Investigator → Synthesis pipeline is right-shaped for this class and stays unchanged.
- **Transport-layer faults** — *below-application network-layer faults*: the cause lives below the application's `recv()`/`send()` API. Kernel qdisc drops, NIC errors, container bridge / vSwitch issues, ToR/leaf/spine switch port discards, router congestion or BGP withdraw, VPN gateway IPsec or MTU problems, optical-layer BER/LOS, WAN transit loss. NF application metrics see only the *downstream consequence* (timeouts, retransmits, rate drops), never the cause. The right-shaped pipeline for this class is a deterministic path walk over the implicated topology, querying each hop's transport-layer telemetry directly. **This is what the ADR introduces.**

Concretely, six coordinated changes:

1. A deterministic **symptom classifier** (Phase 0.5, no LLM) labels the screener output as `application_layer | transport_layer | mixed`. Routing follows the label.
2. For `transport_layer` symptoms, a **path resolver** turns the implicated flow (resolved from KB authoring) into an ordered list of `(hop, hop_kind)` entries.
3. A **`HopProber` abstraction** lets the same path-walk machinery run over heterogeneous hop types. Lab implementations: `KernelHopProber` (containers), `DockerBridgeProber` (the host bridge between containers). Carrier-grade implementations are out of scope for this PR but the abstraction is open: `SNMPHopProber`, `IPsecHopProber`, `OpticalHopProber`, `BGPSessionProber`, `WANSyntheticProber` are sketched in Design so future deployments add probers without redesigning the walker.
4. A **`PathWalkInvestigator`** (Python, non-LLM) executes a fixed probe set per hop in topology order. Probes return structured `HopAttribution` values; the walk does not free-text reason about them.
5. **Synthesis** gains a `localized` verdict-kind. For transport-layer paths it consumes the `PathWalkReport` directly and emits a hop-attributed diagnosis with kernel/network-element evidence inlined.
6. **Probabilistic probes** (`measure_rtt`, future loss-rate probes) get a sample size derived from the loss-detection threshold, replacing the current `-c 3` default. The 3-ping mode is deleted.

We ship this as a **new, fully self-contained v7 agent module** alongside frozen v6. v6 stays as the known baseline; v7 introduces the dual-pipeline routing (classifier + transport-layer path walk + application-layer fallback). The chaos suite runs both side-by-side on every scenario, producing direct empirical comparison on transport-layer faults (where v7 should decisively win) and on application-layer faults (where v7 must not regress). See the **Evolving v6 vs introducing v7** section below for the trade-off analysis and why A/B comparability is the decisive factor.

**v7 self-containment rule (load-bearing).** `agentic_ops_v7/` is **not allowed to import from any prior version** (`agentic_ops`, `agentic_ops_v2` … `agentic_ops_v6`). Its only allowed dependencies are:

- `agentic_ops_common/` — shared infrastructure (models, KB loader, tool façades, the new `path_walk/` package).
- `agentic_ops/tools.py` — the common diagnostic tool surface.
- Standard library, third-party packages already used by the project (pydantic, google-adk, etc.).

Any code from v6 that v7 needs is **copied** into `agentic_ops_v7/`, not imported. The two modules diverge from day one. The cost is duplication of the application-layer phase implementations; the benefit is that v7 can be reasoned about, tested, and evolved without any latent dependency on a prior version's internals. v6 stays frozen; v7 stays self-contained; the A/B comparison stays meaningful even after v7 starts to evolve independently.

## Context

### What we mean by "transport-layer fault"

A transport-layer fault is any cause-of-failure that lives **below the boundary at which an NF's application code calls `recv()` or `send()`**. The defining property is: the NF's application code, no matter how well instrumented, cannot directly observe the cause — only its downstream consequences (timeouts, retransmits, missing packets reported by peers, latency increases). The exact counter that says "packets were dropped here" lives in the kernel, in a network-element MIB, in an optical-transport telemetry feed, or in a BGP route table — not in the NF's process.

In the docker_open5gs lab the universe of transport hops is small: container kernels (qdisc, interface ring buffer, conntrack) and the Docker bridge on the host. In a carrier-grade deployment the same definition spans a much richer set of hops:

| Hop kind | Lives at | "Did packets drop here?" telemetry |
|---|---|---|
| **Container kernel** | NF container's network namespace | `tc -s qdisc show <iface>`, `ip -s link show <iface>`, `cat /proc/net/dev` |
| **Host bridge / vSwitch** | Hypervisor or bare-metal host | `bridge -s link show`, `iptables -L -v -n`, `conntrack -S`, `ovs-ofctl dump-flows` for OVS |
| **NIC / SR-IOV VF** | Host kernel + hardware | `ethtool -S <iface>`, vendor PMD counters, `dropwatch` |
| **Top-of-rack (ToR) / leaf switch** | Datacenter L2/L3 fabric | SNMP `IF-MIB::ifInDiscards`, `ifOutDiscards`, `ifInErrors`, `ifOutErrors`; vendor MIBs for buffer/queue depth and tail drops; gNMI/NETCONF telemetry on modern fabric |
| **Spine / aggregation** | Datacenter fabric | Same MIBs; ECMP-hash imbalance shows up as flow-affinity loss |
| **WAN edge router** | Site egress | SNMP + BGP session state (BMP, BGP-LS); withdrawn prefixes blackhole traffic |
| **VPN gateway** | Site-to-site IPsec/SD-WAN | IPsec SA counters (encrypt/decrypt errors, replay-window failures), MTU mismatches that drop above-PMTU packets when DF is set, vendor SA-state telemetry |
| **Optical / photonic** | DWDM / OTN transport | TL1, OpenROADM, NETCONF for OSC and OCh — LOS, LOF, BER, FEC errors, OSNR margin |
| **Internet transit / public peering** | ISP backbones | Mostly opaque; localized via bidirectional synthetic active probes from each endpoint, RIPE Atlas-style measurement, or path-aware tracing (`mtr`, paris-traceroute) |
| **DPI / firewall / load balancer** | Inline middleboxes | Vendor session-table state, policy-drop counters, DDoS-protection silent drops |

The unifying property across all these is that **every hop has, somewhere, an exact counter for "packets that died here"**. The application doesn't have it; the transport layer does. The agent's job for this fault class is to find that counter and read it — not to hypothesize about NF behavior.

### Worked example 1 — the rtpengine 30% loss case (data-plane symptom)

The fault: `tc qdisc add dev eth0 root netem loss 30%` inside the rtpengine container. Putting a packet-probability filter on rtpengine's egress qdisc means every packet leaving eth0 (RTP, RTCP, ICMP, ARP, control plane, all of it) has a 30% chance of being silently dropped by the kernel before it ever reaches the wire.

On the VoNR media path UE_A → gNB → UPF → rtpengine → UPF → gNB → UE_B:

- Packets arriving INTO rtpengine (UPF→rtpengine direction) are unaffected — netem is on egress.
- Packets leaving rtpengine (rtpengine→UPF direction) have ~30% silently dropped.
- RTPEngine's user-space relay code never sees the drop. It hands the packet to `sendto()`, the kernel acks the queue, then drops it. From rtpengine's POV the call ran perfectly.
- On the receiver, RTCP Receiver Reports come back: "I lost N packets." rtpengine aggregates those into `loss_ratio` → 25.67 in the failing run.
- `rtpengine.errors_per_second` is rtpengine's internal relay-loop counter (malformed RTP, session-not-found, etc.). It is structurally incapable of seeing kernel-level qdisc drops. It will read 0 forever under this fault.

So the visible footprint is exactly:
- RTCP-reported loss spikes at the source-of-the-RTCP (rtpengine).
- Audio quality at the receiver degrades.
- Application metrics inside rtpengine and UPF look fine — they account packets they handled, not packets the kernel quietly threw away.

The agent's pipeline ran as: NA hypothesizes UPF (h1) and rtpengine (h2). IG writes per-NF plans using NF-application metrics (`errors_per_second`, GTP rates) and a 3-ping `measure_rtt`. Investigator returns DISPROVEN on both. Synthesis promotes UPF as the most-cited alt-suspect. Final answer: UPF (wrong).

`tc -s qdisc show dev eth0` inside rtpengine would have printed `qdisc netem ... loss 30%   Sent 8721 pkt (dropped 2616, ...)`. The kernel knew exactly. The agent never asked.

### Worked example 2 — the same fault, but on P-CSCF (signaling-plane symptom)

Same fault, different container: `tc qdisc add dev eth0 root netem loss 30%` on P-CSCF. The fault class is identical; only the symptom-surface changes.

Path for SIP REGISTER from UE_A: UE_A → gNB → UPF → **P-CSCF → I-CSCF → S-CSCF → HSS** (Diameter MAR) → S-CSCF → I-CSCF → P-CSCF → UE_A.

P-CSCF runs Kamailio over UDP. With 30% egress loss:

- 30% of REGISTERs forwarded P-CSCF → I-CSCF are lost in the kernel after Kamailio's `sendto()` returns success.
- Kamailio's outbound transaction state thinks the message went out; SIP T1 (500 ms) fires; it retransmits; second copy has 70% chance of getting through; backoff continues to T1·64 ≈ 32 s before transaction timeout.
- 30% of P-CSCF → UE responses are lost too. UE retransmits its REGISTER. P-CSCF receives the duplicate, processes it, attempts to forward — that copy also has 70% per-attempt success.
- End-to-end registration latency goes up. Some registrations time out and fail entirely. The chain to I-CSCF/S-CSCF/HSS is starved at ~70% rate.

Symptoms the screener would flag:
- `pcscf.rcv_requests_register_per_ue` — receiving side roughly normal (UE retransmits keep arrivals up).
- `icscf.rcv_requests_register_per_ue` — drops to ~70% (P-CSCF→I-CSCF egress is the lossy direction).
- `scscf.rcv_requests_register_per_ue` — drops further (compounded across legs).
- `pcscf.avg_register_time_ms` — way up (multiple retransmit cycles per successful registration).
- `pcscf.errors_per_second` (Kamailio's internal counter) — mostly unchanged, because Kamailio is processing every received message correctly. The kernel-level send-drops aren't visible to Kamailio.

The current v6 pipeline runs the same shape of failure mode it did for rtpengine:

- NA hypothesizes from the rate-drop signature. Candidates: "P-CSCF↔I-CSCF partition" (the existing IMS-partition scenario template), "I-CSCF processing slow", "P-CSCF degraded".
- IG writes per-NF plans. For "P-CSCF↔I-CSCF partition": `measure_rtt(pcscf, icscf_ip)` with `-c 3`. P(0 drops at 30%) = 0.343 — coin flip, very likely false-negative.
- For "I-CSCF processing slow": `check_process_listeners(icscf)`, `get_diagnostic_metrics(icscf)`. I-CSCF is processing what it gets; metrics look fine.
- For "P-CSCF degraded": `run_kamcmd`, `get_diagnostic_metrics(pcscf)`. Kamailio looks fine.
- Investigator returns DISPROVEN across the board. Synthesis can't localize.

`tc -s qdisc show dev eth0` inside P-CSCF would have printed `qdisc netem ... loss 30%   Sent N pkt (dropped 0.30N, ...)`. Identical evidence to the rtpengine case. Same path-walk localizes both.

### Why this is one class, not two

The two cases above span the data plane and the signaling plane. The symptoms manifest in different metrics. The implicated paths differ. The application code differs (rtpengine relay vs. Kamailio SIP forwarder). And yet the *fault* is the same: a kernel-level egress drop on one hop, invisible to that hop's application, visible only to the kernel's qdisc counter. Any per-NF hypothesis pipeline asking application-layer questions will fail symmetrically on both — no matter how well the KB explains application metrics.

The class is best named for what it *is*, not for which plane the symptom lives in: **transport-layer faults**, defined as faults whose root cause lives below the application's `recv()`/`send()` API. The correct localization mechanism is the same in both cases: walk the implicated path, ask each hop's transport-layer telemetry "did packets die here?", attribute the loss to the first hop that says yes.

### How an experienced NOC engineer approaches it

A senior network engineer looking at *either* the rtpengine RTCP-loss spike or the P-CSCF→I-CSCF rate drop reasons the same way:

1. **Pin the symptom to a path.** Symptom names a chain. RTCP loss at rtpengine names the media path; REGISTER-rate drop between P-CSCF and I-CSCF names the SIP signaling path. Either way, the path is finite and known.

2. **Bisect the path with link-layer probes.** At each hop on the path, reach for the probes that are *exact* about packet loss at that hop:
   - `tc -s qdisc show dev <iface>` — per-qdisc statistics with kernel-level drop counters. Zero false-negative rate by construction.
   - `ip -s link show dev <iface>` — interface-level RX/TX errors and dropped counters. Catches drops not associated with a qdisc (ring buffer overrun, etc.).
   - Adjacent-hop same-direction comparison: hop N's TX rate vs hop N+1's RX rate over the same window. Mismatch attributes loss to the link between them.

3. **In a carrier network, the bisection extends past containers.** The engineer adds:
   - SNMP `IF-MIB::ifInDiscards` / `ifOutDiscards` polling at every switch port on the path.
   - Optical telemetry (TL1, NETCONF) for fiber/DWDM segments.
   - BGP session state for any segment that depends on dynamic routing.
   - Active synthetic probes from both endpoints when the middle is opaque (transit ASes).

4. **First hop in topology order with anomalous drops is the answer.** Total time: ~20 seconds to a few minutes (depending on how many SNMP polls), zero hypotheses, zero ambiguity. The kernel and the network elements are sources of truth; the engineer just queries them.

What the engineer pointedly does *not* do:

- **Does not equate reachability with non-loss.** A 3-ping test from rtpengine to UPF returning 0/3 dropped tells you UPF is reachable at all. It tells you nothing about whether the link is dropping a fixed fraction of packets, because the sample is too small. Reachability and loss-rate are different questions.
- **Does not look at application-layer error counts to falsify a kernel- or network-layer fault.** `errors_per_second` counts errors the *application* generates. tc netem drops, switch port discards, IPsec replay-failures all happen *below* the application — `sendto()` returns success and the byte just disappears. There is no application-layer metric that responds. Falsifying "is the application at fault" with application metrics is a meaningful question; falsifying "is there transport-layer loss on this hop" with application metrics is structurally backwards.
- **Does not scale sample size by guesswork.** 30% loss cannot be detected by 3 ICMP samples — the no-drop probability is 0.7³ ≈ 34%. The engineer either uses an exact counter (qdisc, ifInDiscards) or sends enough probes to discriminate the fault rate of interest.

### Why per-NF hypothesis generation fails for this class

The current pipeline's unit of work is "test NF X." Phase 3 (NA) ranks NFs by suspicion; Phase 4 (IG) writes a falsification plan per NF; Phase 5 (Investigator) runs probes targeted at that NF. Probe candidates within a per-NF plan are NF-state metrics: container running, application errors, request rates, internal counters — the things the KB catalogs *for that NF*.

For a transport-layer fault, this shape is structurally wrong in three independent ways:

1. **The fault location does not align with the unit of work.** A kernel-level qdisc drop is named by `(container, interface, qdisc)`; a switch-port drop is named by `(switch, port)`; an IPsec replay failure by `(gateway, SA-id)`. A per-NF hypothesis like "rtpengine is the source" or "P-CSCF is the source" reduces this to a coarser unit and the probes it implies are NF-application-state, which is the wrong layer. The right unit is *hop on path*; the planner has no way to express that today.

2. **NF-application metrics are blind to below-application faults by construction.** rtpengine's `errors_per_second`, Kamailio's transaction counters, UPF's GTP application counters all account for what their *processes* did. The transport layer below them quietly drops packets without notifying the process. No matter how rich the KB rendering on these metrics is, they simply do not respond to this fault class. Falsifying "is X the source of transport loss" using only X's application metrics is mechanically incapable of producing a true verdict.

3. **Reachability probes are mis-targeted as loss probes, and undersampled.** When the per-NF plan does reach for a network-layer probe, it picks `measure_rtt` to test "is NF reachable" as a proxy for "does the link to NF drop packets." With `-c 3`, the false-negative rate against a 30% loss fault is 34%. Even with adequate sample size, "is X reachable" is the wrong question: a 30%-lossy link is reachable. The engineer's probes (qdisc counters, interface drops, SNMP polls, same-direction rate diffs) are exact; the agent's is a coin flip.

The combined effect on a transport-layer scenario is exactly what we observed in the rtpengine run, and exactly what we'd predict for the P-CSCF tc-netem case if it were run today. Even with the disambiguator ADR fully landed (and it is — see [`expose_kb_disambiguators_to_investigator.md`](expose_kb_disambiguators_to_investigator.md)), the LLM is solving the wrong problem with the wrong probes. KB-rendering improvements help an Investigator that is asking application-layer questions; they don't change which questions the Investigator asks.

### Why path-anchored is the right shape

The whole class of transport-layer faults shares a structural signature: *packets reported missing somewhere on a known path*. The path is in the ontology already. Each hop on the path has, at its native layer, an exact counter for "packets that died here." Walking the path with hop-uniform telemetry queries turns a hypothesis-search problem into a deterministic localization problem.

The shift is from "which NF is at fault" (search) to "where on the path is the loss" (localization). A localization is cheaper, more reliable, and explains itself ("packets entered hop N at rate X, exited at rate Y, the qdisc/SNMP/IPsec counter at hop N reported (X − Y) drops"). It generalizes naturally to any fault below the application:

- `netem loss` / `netem corrupt` → kernel qdisc drop counters at the originating hop.
- `netem delay` → per-hop RTT samples or kernel queueing latency.
- `tbf` rate cap → per-hop throughput observation against advertised capacity.
- Switch port drops (carrier) → SNMP `ifInDiscards` / `ifOutDiscards` jump at the offending port.
- IPsec replay or MTU drops (carrier VPN GW) → IPsec SA counters.
- Optical degradation → BER/FEC error count past threshold on the affected OCh.
- BGP withdraw blackhole → BGP table at the upstream hop shows route absent for the affected prefix.

The lab gets a small set of probers; carrier deployments add probers as the topology requires. The walker, the path resolver, the localization rule, and the Synthesis output shape are *the same in both deployments*.

The per-NF hypothesis flow is still right for *NF-internal application faults* — a stuck Diameter peer, a misconfigured Kamailio module, a process that crashed but is restarting, a poisoned cache. Those faults manifest in NF state, and the existing pipeline diagnoses them well. This ADR does not change that flow. It carves out the transport-layer class — which has a different fault locus and a different set of right-shaped probes — into a separate, deterministic mechanism.

## Design

### Symptom classifier (`agentic_ops_v6/symptom_classifier.py`, new)

A deterministic Python classifier runs immediately after Phase 0 (AnomalyScreener) and before NetworkAnalyst. Inputs: the screener's anomalous-metric list with their KB entries. Output: one of `{application_layer, transport_layer, mixed}` plus rationale.

Classification rule:

- **`transport_layer`** — there is at least one load-bearing anomaly metric whose KB-attached signature is *aggregate transport quantity* (a packet/transaction *rate*, end-to-end *latency*, RTCP-reported *loss_ratio*, transaction *round-trip time*) AND the NFs implicated by that metric show *no application-layer smoking gun* (no application-error spike, no internal-state anomaly) at comparable magnitude. Rephrased: "the symptom is downstream effects of packets going missing, but no NF is internally complaining."
- **`application_layer`** — load-bearing anomaly metrics are NF-internal (process state, configuration, application errors, internal counters with no `plane` tag), with no transport-quantity rate-drops/latency-spikes that aren't explainable as direct application output.
- **`mixed`** — both signatures co-load-bearing. Common when a transport-layer fault is severe enough to cause secondary application-layer symptoms (a Kamailio module reporting timeouts because its outbound socket is lossy).

The classifier is a small set of rules over KB-typed metrics, not a heuristic ML classifier. It is auditable — every classification produces a one-paragraph rationale citing the metrics and KB tags it weighed. Tests pin the classification of every existing chaos scenario.

For `transport_layer` and `mixed`, the orchestrator runs the path-walk pipeline. For `mixed`, the path walk runs first; if it localizes the fault, that's the answer; if it returns null localization, the application-layer pipeline runs as fallback to investigate the secondary application symptoms. For `application_layer`, the existing v6 NA → IG → Investigator → Synthesis pipeline runs unchanged.

### Path resolver (`agentic_ops_v6/path_resolver.py`, new)

For a transport-layer symptom, identify the implicated path:

1. From the screener's load-bearing anomalies, look up each metric's KB-attached `flows` association.
2. Score each associated flow by the count of load-bearing metrics it covers, tie-broken by flow specificity (a more concrete flow like `vonr_media` beats a broader flow like `pdu_session_data`).
3. Resolve the winning flow's steps into an ordered hop list using ontology-authored topology. Each hop is a `(node, hop_kind, iface)` triple.

In the lab, this produces e.g. for the VoNR media path:

```
[
  Hop(node="e2e_ue1",  kind=container,     iface="eth0"),
  Hop(node="bridge",   kind=docker_bridge, iface="docker0"),
  Hop(node="nr_gnb",   kind=container,     iface="eth0"),
  Hop(node="bridge",   kind=docker_bridge, iface="docker0"),
  Hop(node="upf",      kind=container,     iface="eth0"),
  Hop(node="bridge",   kind=docker_bridge, iface="docker0"),
  Hop(node="rtpengine",kind=container,     iface="eth0"),
  Hop(node="bridge",   kind=docker_bridge, iface="docker0"),
  ... (return path)
]
```

In a carrier deployment, the same resolver, given a richer ontology, produces:

```
[
  Hop(node="ue-eNB",            kind=radio_ran),
  Hop(node="leaf-sw-ran-01",    kind=l2_switch, port="eth1/3"),
  Hop(node="spine-sw-01",       kind=l2_switch, port="eth0/12"),
  Hop(node="upf-host-A",        kind=host_kernel, iface="ens1f0"),
  Hop(node="upf",               kind=container, iface="eth0"),
  Hop(node="ipsec-gw-east",     kind=vpn_gateway, sa_id="..."),
  Hop(node="optical-segment-3", kind=optical_segment),
  ... etc.
]
```

The path is direction-aware. For RTCP-loss-at-rtpengine the loss-bearing direction is "everything past rtpengine's egress toward the receiver." The walker traverses both directions and reports per-direction attribution.

The ontology gains an optional `iface` and required `hop_kind` per flow step. For the lab, `eth0` is the default interface and `container` the default kind; carrier deployments author the richer topology in the same place.

### `HopProber` abstraction (`agentic_ops_common/path_walk/probers/`, new)

The walker calls `prober.probe(hop, window) -> HopAttribution` for each hop. Each `HopProber` implementation knows how to query its hop kind for transport-layer telemetry. The contract is fixed; the implementation differs.

Lab probers (shipped in this ADR's PR):

| Prober | Hop kinds | What it reads |
|---|---|---|
| `KernelHopProber` | `container`, `host_kernel` | `tc -s qdisc show <iface>` (qdisc kind, `Sent`, `dropped`, `overlimits`); `ip -s link show <iface>` (rx/tx errors, dropped); `cat /proc/net/dev` as fallback. |
| `DockerBridgeProber` | `docker_bridge` | Drops into the host network namespace; reads `bridge -s link show`, `iptables -L -v -n` (drop-rule packet counts), `conntrack -S` for table-overflow drops. |

Carrier-grade probers (sketched signatures; out of scope for this PR; future ADRs add them as deployments need):

| Prober | Hop kinds | What it would read |
|---|---|---|
| `SNMPHopProber` | `l2_switch`, `l3_router`, `wan_edge` | SNMP polls `IF-MIB::ifInDiscards`, `ifOutDiscards`, `ifInErrors`, `ifOutErrors`; vendor MIBs for queue-depth and tail-drop counters; gNMI/NETCONF for modern fabric. |
| `IPsecHopProber` | `vpn_gateway` | IPsec SA counters (encrypt/decrypt errors, replay failures); MTU-mismatch silent-drop detection by comparing pre/post-encap PMTU. |
| `OpticalHopProber` | `optical_segment` | TL1 / OpenROADM / NETCONF for OCh and OSC: LOS, LOF, BER, FEC errors, OSNR margin. |
| `BGPSessionProber` | `wan_edge`, `peer_router` | BMP / BGP-LS for session state and route-table presence; BGP withdraw of an affected prefix is a blackhole signature. |
| `WANSyntheticProber` | `transit_segment` | Active probes from both endpoints (paris-traceroute, mtr, RIPE Atlas-like measurement) when the middle is opaque. Localizes loss to a transit AS by per-hop RTT and loss attribution. |
| `MiddleboxProber` | `firewall`, `load_balancer`, `dpi` | Vendor session-table state; policy-drop counters; DDoS-protection silent-drop counters. |

The abstraction is open. Each prober is a class implementing one method:

```python
class HopProber(Protocol):
    async def probe(
        self,
        hop: Hop,
        window_seconds: int,
        anchor_ts: float | None,
    ) -> HopAttribution: ...
```

`HopAttribution` is a closed enum:

- `clean(evidence)` — counters report no drops at this hop.
- `drops_attributed_here(kind, count, fraction, evidence)` — exact attribution. `kind` ∈ {`qdisc_netem`, `qdisc_tbf`, `iface_dropped`, `iface_error`, `switch_discard`, `ipsec_replay`, `optical_ber`, ...}. `evidence` carries the verbatim counter excerpt.
- `drops_attributed_to_inbound_link(observed_loss_pct, evidence)` — derived from same-direction TX(prev) vs RX(this) rate diff over the window. Loss is on the link between hops, not at either endpoint.
- `inconclusive(reason)` — prober failed to run (toolbelt gap closed by [`nf_container_diagnostic_tooling.md`](nf_container_diagnostic_tooling.md), SNMP unreachable, vendor API down). Surfaced explicitly, never silently rebranded.

Per-hop probes are composable: the walker can call multiple probers per hop (a `host_kernel` hop gets `KernelHopProber` and could be extended with `DockerBridgeProber`-style host inspection). Attributions from multiple probers on the same hop are combined: any `drops_attributed_here` wins; otherwise `clean` if all probers say clean; otherwise `inconclusive`.

### Hop-uniform probe contract for the lab

For the lab, every hop yields three structured returns from `KernelHopProber` (or `DockerBridgeProber` for bridge hops):

1. **`get_qdisc_drops(node, iface)`** — wraps `tc -s qdisc show dev <iface>` inside the container's network namespace (or the host's, for bridges). Returns: `{qdisc_kind, sent_pkts, dropped_pkts, dropped_pct, raw}`. Existing `check_tc_rules` covers presence detection; this probe extracts the numeric drop counter.
2. **`get_interface_drops(node, iface)`** — wraps `ip -s link show dev <iface>`. Returns: `{rx_pkts, rx_dropped, rx_errors, tx_pkts, tx_dropped, tx_errors}`. Catches drops not tied to a qdisc (overrun, buffer full).
3. **`get_link_rate_diff(hop_n, hop_n+1, direction, window_s)`** — for adjacent hops, sample packet counters over a window and compute per-direction delta. Loss between hops: `tx_rate(N) - rx_rate(N+1) > threshold` for direction N→N+1. Implementation reuses the Prometheus rate query plumbing.

These are *hop-uniform* — same probes at every kernel-or-bridge hop on every transport-layer investigation. No per-NF authoring, no LLM probe-pick.

### Sample-calibrated probabilistic probes

The existing `measure_rtt` uses `ping -c 3 -W 10`. For path-walk investigations it's redundant — exact counters are enough. But probabilistic probes still apply outside the path walk (NF-state checks, follow-up after path-walk localization), and the `-c 3` default is unsafe regardless of pipeline.

Rule: a probabilistic loss probe targeting a fault rate threshold `p_min` chooses sample size `N = ceil(log(0.001) / log(1 - p_min))` so the false-negative rate (no drops observed when ground truth ≥ `p_min`) is ≤ 0.001:

| Fault rate threshold | Sample size N | Wall-time at -i 0.1 |
|---|---|---|
| ≥ 30% loss | 20 | 2 s |
| ≥ 10% loss | 66 | 6.6 s |
| ≥ 1% loss  | 689 | 69 s |
| ≥ 0.1% loss | 6905 | 690 s |

`measure_rtt`'s default becomes `≥ 10%` threshold (N=66, ~7 s). The `-c 3` mode is deleted, not parameterized — there is no fault threshold for which 3 samples are appropriate. The probe takes an explicit `loss_threshold: float` argument the IG (or a future planner) can override.

### Path-walk Investigator (`agentic_ops_v6/subagents/path_walk_investigator.py`, new)

A new sub-investigator mode replaces the LLM-driven Investigator for transport-layer plans. It is *not* an LLM agent — it's a Python runner that:

1. Iterates the resolved hop list in topology order.
2. At each hop, picks the right `HopProber`(s) via the hop's `kind` and runs them.
3. For adjacent hops, runs the appropriate link-rate-diff probe.
4. Emits a `PathWalkReport` with one `HopAttribution` per hop and per inter-hop link.

No LLM calls. The walk runs in seconds for the lab; minutes worst-case in carrier deployments depending on SNMP polling latency.

### Synthesis: localization, not voting (`agentic_ops_v6/subagents/synthesis.py`, modified)

For transport-layer symptoms, Synthesis consumes the `PathWalkReport` directly and emits:

- `verdict_kind: "localized"` (new value alongside `confirmed`, `promoted`, `inconclusive`).
- `primary_suspect_nf: <node>` — the first hop in topology order with `drops_attributed_here`. (For bridge or switch hops, `primary_suspect_nf` carries the bridge/switch identifier; the field name is kept for compatibility.)
- `localization: {hop, kind, evidence}` — the verbatim counter excerpt that proves the diagnosis.
- `root_cause_confidence: high` when a hop attributes drops via an exact counter (kernel/SNMP/IPsec/optical). The kernel and network elements are sources of truth; this is not a probabilistic claim. Confidence drops to `medium` when attribution is via inter-hop rate diff (the diff is statistical at small windows) and to `low` for inconclusive walks.
- A walk-table in the explanation showing every hop's attribution, in order. Operators read it as a path bisection report, not an LLM essay.

If no hop attributes drops AND no inter-hop link attributes drops, the report carries `localization: null` and the orchestrator falls back to the existing application-layer pipeline. The fallback is rare for true transport-layer faults; it exists so the path-walk's negative result doesn't dead-end the investigation.

### v7's pipeline shape, contrasted with v6

v6's phase structure (frozen as baseline; the chaos suite continues to run it for comparison):

```
Phase 0   AnomalyScreener
Phase 1   EventAggregator
Phase 2   CorrelationAnalyzer
Phase 3   NetworkAnalyst (LLM)
Phase 4   InstructionGenerator (LLM, per-NF)
Phase 5   Investigator (LLM, per-NF, multi-shot consensus)
Phase 6   EvidenceValidator
Phase 6.5 CandidatePool / Re-investigation
Phase 7   Synthesis (LLM)
```

v7's phase structure (new module, dual-pipeline routing):

```
Phase 0    AnomalyScreener                                 ┐
Phase 0.5  SymptomClassifier (NEW, deterministic)          │ Run for every episode
Phase 1    EventAggregator                                 │
Phase 2    CorrelationAnalyzer                             ┘

if classifier == application_layer:
    Phase 3   NetworkAnalyst (LLM)                         ┐
    Phase 4   InstructionGenerator (LLM)                   │ Imported from v6;
    Phase 5   Investigator (LLM, multi-shot)               │ functionally identical
    Phase 6   EvidenceValidator                            │ to v6's pipeline
    Phase 6.5 CandidatePool / Re-investigation             │
    Phase 7   Synthesis (LLM)                              ┘

elif classifier in (transport_layer, mixed):
    Phase 3'   PathResolver (NEW, deterministic)           ┐
    Phase 4'   PathWalkInvestigator (NEW, deterministic)   │ New transport-layer
    Phase 7'   Synthesis (LLM, with localized verdict)     ┘ branch — v7-only

    if mixed and localization is null:
        fall through to application_layer pipeline as fallback
```

For the application-layer branch, v7 carries its own **copies** of v6's phase implementations: NetworkAnalyst, InstructionGenerator, Investigator (with multi-shot consensus), EvidenceValidator, CandidatePool/Re-investigation, Synthesis, and all guardrails (`investigator_consensus`, `confidence_cap`, `synthesis_pool`, `na_linter`, `probe_selection`, etc.). At v7's creation these files are bit-for-bit copies of their v6 counterparts (modulo the `localized` verdict extension to Synthesis). From there forward, v7 evolves independently — there is no import path from v7 back to v6. This is the v7 self-containment rule stated in the Decision section.

Initial behavioral equivalence between v7's application-layer branch and v6 is verifiable: at copy-time, v7's application-layer behavior on application-layer scenarios is identical to v6's by construction. A regression test (`test_application_layer_parity_with_v6`) runs the same application-layer chaos scenario through both versions and asserts diagnosis equivalence at copy-time; over time the test is expected to weaken as v7 evolves application-layer logic the chaos suite has surfaced room to improve, but the test stays valuable as a tripwire — any *unintentional* divergence at the time the file is copied (e.g. a prompt-string that didn't get carried across) fails CI.

The transport-layer branch is entirely new code in v7. The path resolver, the `HopProber` registry, the `PathWalkInvestigator`, and the `localized`-verdict Synthesis path live in `agentic_ops_v7/`. Reusable pieces — the probers, the new probe wrappers in `agentic_ops/tools.py`, the path-walk model types (`Hop`, `HopAttribution`, `PathWalkReport`) — live under `agentic_ops_common/` so a future v8 can build on them without depending on v7. v6 itself is not modified.

### Why deterministic, not LLM-mediated

The whole point of the path walk is that the OS / network elements / vendor APIs already have the answer. The kernel knows exactly how many packets it dropped on which qdisc. SNMP returns exact `ifInDiscards` numbers. An IPsec SA's counter is the IPsec stack's ground truth. Adding an LLM in the middle of "ask the source-of-truth, then report" introduces variance in a place that has zero variance to begin with — an LLM might mis-cite, mis-summarize, or hallucinate an extra hop. None of those failure modes can occur in a Python loop over a fixed hop list with structured probe returns.

The LLM contribution to v6 — generating hypotheses, picking probes, interpreting results — is genuinely valuable when the question is "what's wrong" and the search space is unbounded. For transport-layer localization the search space is bounded (hops on the implicated flow) and the ground truth is structured (kernel/SNMP/vendor counters). LLM mediation here is overhead with no upside.

## Evolving v6 vs introducing v7

This is a substantial change. Two reasonable paths:

### Option A — Introduce v7 (chosen)

Stand up `agentic_ops_v7/` as a new, **fully self-contained** module. v7 owns the dual-pipeline routing as its primary identity ("v7: classifier-driven pipeline with deterministic transport-layer localization on top of a copy of v6's per-NF falsifier"). v6 stays frozen as a known baseline. The chaos suite runs both side-by-side, scoring each independently.

For the application-layer branch, v7 carries its own **copies** of v6's phase implementations — NetworkAnalyst, InstructionGenerator, Investigator, EvidenceValidator, CandidatePool/Re-investigation, Synthesis, and all guardrails. v7 does not import from v6 (or any prior version). At v7's creation the copies are bit-for-bit; from there v7 evolves independently. Only the classifier, path resolver, path-walk Investigator, and the `localized`-verdict Synthesis extension are *net new* code; the rest is duplicated from v6.

The duplication is intentional. The cost is real (more lines of code; future application-layer ADRs that should affect both versions have to be applied twice during the comparison period). The benefit is that v7's behavior is fully determined by code inside `agentic_ops_v7/` plus shared infrastructure (`agentic_ops_common/`, `agentic_ops/tools.py`), with no latent coupling to v6's internal choices that could shift if v6 were ever unfrozen.

**Pros:**
- **Direct A/B comparability.** Every chaos scenario produces two independent scores: v6's and v7's. Transport-layer scenarios should show v7 localizing correctly while v6 mis-diagnoses (the rtpengine and P-CSCF cases in Context); application-layer scenarios should show v6 and v7 producing equivalent diagnoses (because v7's application-layer phases are bit-for-bit copies of v6's at v7 creation). The chaos suite's existing per-version scoring tables make the win/loss visible at a glance.
- **Empirical case for the change.** The ADR's central claim — that the path-walk improves diagnosis quality on transport-layer faults without regressing application-layer faults — is verifiable from the chaos suite output once both versions are running. We don't need to *argue* the path-walk is better; we publish the scores.
- **Sharper narrative.** v7 has a clean identity ("classifier-driven, deterministic for transport-layer, LLM-driven for application-layer") that captures the architectural shift in one line. New version, new identity, easier to reason about during reviews and onboarding.
- **Permission to drop v6 vestiges in v7.** Some IG complexity exists in v6 specifically to compensate for transport-layer scenarios it can't really handle (per-NF plans that try to falsify transport faults with NF metrics). v7 doesn't run that path for transport-layer symptoms, so when v7 eventually replaces v6 the complexity can retire cleanly.
- **Continuity of v6 logs.** v6 keeps writing to `agentic_ops_v6/docs/agent_logs/` unchanged; v7 writes to `agentic_ops_v7/docs/agent_logs/`. Pre-this-ADR trend analysis on v6 stays valid; v7's logs accumulate from day one as the new evidence base.

**Cons:**
- **Doubles maintenance.** Two pipelines, two test suites, two scoring runs in every chaos batch. Because v7 is self-contained (no imports from v6), future application-layer ADRs that should land in both versions have to be applied to each module separately during the v6/v7 comparison period. Changes to the transport-layer pipeline land in v7 only. The `agentic_ops_common/` layer is shared and benefits both versions when it changes (e.g., the path-walk probers, the new probe wrappers in `agentic_ops/tools.py`, the toolbelt audit) — but `agentic_ops_common/` is, by design, a small surface; most ADR changes are version-local.
- **Token cost.** The chaos runner today runs `v3, v4, v5, v6` in parallel; adding v7 means every chaos batch costs ~25% more LLM tokens. This is bounded and visible; we accept it for the comparability benefit.
- **Some plumbing duplication.** v7 needs its own orchestrator, agent registry entry, agent_log writer wiring, and GUI menu entry. Most of this is config and small adapters — not real architectural duplication — but it's real lines of code.

### Option B — Evolve v6

Land the symptom classifier, path resolver, hop-prober abstraction, path-walk investigator, and Synthesis change inside the existing v6 module tree. v6's external interface stays the same; internally it gains the dual-pipeline routing.

**Pros:**
- **Additive change.** The application-layer pipeline is untouched. Existing tests stay valid; new tests cover the new branch.
- **Lower token cost in the chaos suite.** No second version to score against.
- **Continuity of a single agent identity.** "v6 with transport-layer path walk" is one thing; v6 vs v7 splits the identity.
- **Faster to operator value.** Land in one PR; operators get the fix on transport-layer scenarios without waiting for a v7 module to mature.

**Cons (decisive):**
- **No A/B comparison.** "v6 with the new path walk" can't be directly compared to "v6 without it" because they're the same module at different commits. The chaos suite can compare against earlier versions (v3, v4, v5), but those have their own architectural differences confounding the comparison. The empirical case for *this specific change* becomes argumentative rather than measured.
- **Risk of silent regression on application-layer scenarios.** If the orchestrator's dual-pipeline routing has a bug that affects classification or fall-through behavior, application-layer scenarios might silently degrade in v6. With v7 as a separate module and v6 frozen, the regression surface is contained: v7 might have bugs, v6 doesn't change.
- **v6 grows in conceptual scope.** "v6: structurally guarded falsifier-investigator pipeline" becomes "v6: structurally guarded falsifier-investigator pipeline, plus deterministic transport-layer path walk." Less crisp; reviewers and operators have to load both ideas at once.

### Recommendation

**Introduce v7.** The decisive factor is empirical comparability. With v6 frozen as a known baseline and v7 introduced as a separate agent module, the chaos suite produces direct A/B measurements on every scenario: which version localizes correctly, which version's diagnosis matches ground truth, time-to-diagnosis, and token cost. For an architectural change of this scale — adding a deterministic non-LLM pipeline alongside the existing LLM-driven one — anecdotal "it should work better" is not enough. The chaos suite needs to *prove* the path-walk improves diagnosis quality on transport-layer scenarios without regressing application-layer scenarios, and the only way to prove that is to run both versions side-by-side on the same scenario set and compare scores.

The maintenance cost (carrying parallel pipelines, applying future ADR changes to both) is real but bounded. v6's existing structural guardrails — multi-shot consensus, confidence cap, tool_unavailable filtering, evidence validator, candidate-pool linter — exist as **copies** in v7 from day one (v7 is self-contained; it does not import from v6), and continue to apply to v7's application-layer branch. Because v7 carries its own copies, future application-layer ADRs that should land in both versions have to be applied to each module separately during the comparison period — a real cost, but one that's contained by the policy that v6 stays frozen (so in practice most application-layer ADRs land in v7 only). Transport-layer ADRs always land in v7 only. The chaos suite already runs v3, v4, v5, v6 in parallel, so adding v7 follows an established pattern at a known incremental cost (~25% more tokens per chaos batch).

Once v7's scoring decisively beats v6 on transport-layer scenarios across the full chaos suite (and matches it on application-layer scenarios) for a sustained period, the project can deprecate v6 — the same pattern v3 → v4 → v5 → v6 has followed historically. Until then, both versions run side-by-side to keep the empirical evidence for the change visible in every chaos run.

## Verification

### Unit tests

1. **`test_symptom_classifier`** — feed synthetic screener outputs (one per fault class) and assert the classifier returns the expected `{application_layer, transport_layer, mixed}`. Cover at minimum: rtpengine packet loss (transport_layer), P-CSCF packet loss (transport_layer), UPF data-plane outage (transport_layer), gNB radio failure (mixed — RAN+transport), HSS unresponsive (application_layer), MongoDB gone (application_layer), MariaDB connection-pool exhausted (application_layer), IMS partition (transport_layer), AMF restart (application_layer), DNS failure (transport_layer for dns hop, application_layer for resolution-cache symptom), Cascading IMS failure (mixed). Each is a fixture under `tests/fixtures/screener_outputs/`.

2. **`test_path_resolver_resolves_vonr_media`** — feed the rtpengine-loss screener fixture, assert the resolved hop list matches the documented VoNR media path.

3. **`test_path_resolver_resolves_ims_signaling`** — feed the P-CSCF-loss screener fixture, assert the hop list covers the SIP signaling path P-CSCF ↔ I-CSCF ↔ S-CSCF.

4. **`test_path_resolver_picks_most_specific_flow`** — multiple flows could match; assert the most metric-specific is chosen.

5. **`test_kernel_hop_prober_returns_structured`** — for each probe (`get_qdisc_drops`, `get_interface_drops`, `get_link_rate_diff`), feed a synthetic container response and assert the structured return matches the schema. Covers tool_unavailable cases per the toolbelt ADR.

6. **`test_docker_bridge_prober_returns_structured`** — same shape for the host-bridge prober. Synthetic `bridge`, `iptables`, `conntrack` outputs.

7. **`test_path_walk_localizes_qdisc_drop`** — synthesize a hop list where one hop's `KernelHopProber` returns `dropped_pkts > 0`; assert `PathWalkReport` attributes `drops_attributed_here` to that hop and `clean` to all others.

8. **`test_path_walk_localizes_inter_hop_link_drop`** — synthesize counter rates where TX(N) > RX(N+1); assert `drops_attributed_to_inbound_link` on hop N+1.

9. **`test_path_walk_no_attribution_returns_null_localization`** — all hops clean; assert `localization: null` and the orchestrator escalates to the application-layer fallback.

10. **`test_sample_size_calibration`** — call `measure_rtt(loss_threshold=0.30)`, assert it issues `ping -c 20`. Same for 0.10 → 66, 0.01 → 689. Hard-fail if anyone reintroduces `-c 3`.

11. **`test_hop_prober_protocol_compliance`** — every prober class implements `probe(hop, window_seconds, anchor_ts) -> HopAttribution`. Static check across all `HopProber` subclasses, runs at import time.

### End-to-end regression — the contract for this ADR

Two scenarios must pass when run against v7 (lab deployment, full chaos run); v6 is run on the same scenarios as the comparison baseline (and is expected to fail both — the failing rtpengine run already demonstrates this for scenario A; scenario B is new and predicted to fail v6 by the same mechanism):

**A. `Call Quality Degradation` (the originally-failing rtpengine 30% loss):**

- Symptom classified as `transport_layer`.
- Path resolved to the VoNR media flow's hop list.
- `PathWalkReport.attributions` shows `clean` for every hop except `rtpengine[eth0]`, which shows `drops_attributed_here(kind=qdisc_netem, fraction ≈ 0.30 ± 0.05)`.
- `verdict_kind == "localized"`.
- `primary_suspect_nf == "rtpengine"`.
- `root_cause_confidence == "high"`.
- Episode log captures the verbatim `tc -s qdisc show` excerpt as evidence.

**B. New scenario: `P-CSCF Packet Loss` (the worked example in Context):**

A new chaos scenario `pcscf_packet_loss` injects `tc qdisc add dev eth0 root netem loss 30%` on the pcscf container.

- Symptom classified as `transport_layer`.
- Path resolved to the IMS signaling flow.
- `PathWalkReport.attributions` shows `clean` for every hop except `pcscf[eth0]`, which shows `drops_attributed_here`.
- `primary_suspect_nf == "pcscf"`, `verdict_kind == "localized"`, `root_cause_confidence == "high"`.

The two together prove the path walk works for a data-plane and a signaling-plane case with no special-casing. A CI hook runs both nightly (or on-demand against a deployed stack) and fails the build on any assertion violation. This is the explicit "the verdict on h1 must not be DISPROVEN" check the disambiguator ADR specified but never executed — re-stated and enforced.

### Generalization tests

To prove path-walk generalizes across transport-layer fault types, four more scenarios join the regression set:

1. **Latency injection on rtpengine** (`netem delay 100ms`) — `get_qdisc_drops` reports 0 dropped, but the qdisc dump names `delay 100ms`. `HopAttribution` carries `latency_at_hop` (sibling of `drops_attributed_here`); localization still names rtpengine.

2. **Bandwidth cap on UPF eth0** (`tbf rate 100kbit`) — `get_qdisc_drops` reports drops on UPF's tbf qdisc (tbf drops over-rate packets). Localization names UPF.

3. **Docker bridge degraded** (`iptables -A FORWARD ... -m statistic --mode random --probability 0.3 -j DROP` on the host bridge) — every container hop's qdisc clean, but `get_link_rate_diff` reports loss between the affected hops AND `DockerBridgeProber` finds the iptables rule with non-zero packet count. Localization names the bridge segment.

4. **`P-CSCF Diameter peer slow` (application-layer, negative test)** — P-CSCF is up but its Diameter peer connection to PCF is degraded due to a misconfigured SCTP timer (synthetic). Classifier returns `application_layer`; path walk is not invoked; existing v6 NA → IG → Investigator pipeline runs. Asserts the classifier correctly *doesn't* over-trigger on application-layer faults.

If any of these four regress, the path-walk machinery has a structural gap and the ADR's claim of generalization is violated.

### Why these tests are sufficient

The unit tests cover the classifier, resolver, walker, and probers in isolation. The two regression scenarios pin both a data-plane and a signaling-plane case of the same fault class. The four generalization scenarios prove the mechanism extends to other transport-layer fault types and that the classifier doesn't false-positive on application-layer faults. Together they form a contract: transport-layer symptoms localize deterministically, application-layer symptoms keep their LLM-driven flow, and any future regression on either side fails CI.

## Files Changed

### New: `agentic_ops_v7/` module

- `agentic_ops_v7/__init__.py` (new) — module entry point and agent-registry registration as `v7`.
- `agentic_ops_v7/__main__.py` (new) — CLI shim mirroring `agentic_ops_v6/__main__.py`.
- `agentic_ops_v7/orchestrator.py` (new) — Phase 0.5 classifier; routes `transport_layer`/`mixed` to the path-walk branch; routes `application_layer` to v7's own copy of the v6 application-layer phases. v7 owns its own orchestration; v6's orchestrator is not modified.
- `agentic_ops_v7/symptom_classifier.py` (new) — deterministic classifier over screener output.
- `agentic_ops_v7/path_resolver.py` (new) — flow → ordered hop list, with hop_kind annotations.
- `agentic_ops_v7/subagents/path_walk_investigator.py` (new) — Python (non-LLM) walker that drives `HopProber`s in topology order and emits `PathWalkReport`.
- `agentic_ops_v7/subagents/synthesis.py` (new, modified copy of v6's) — handles `localized` verdict in addition to `confirmed`/`promoted`/`inconclusive`; renders walk-table in explanation; bypasses per-NF candidate-pool logic for the `localized` kind. Application-layer verdicts pass through the same code paths as v6's synthesis (since this file is a modified copy of v6's, not an import).
- `agentic_ops_v7/prompts/synthesis.md` (new, modified copy of v6's) — one paragraph teaching Synthesis to render `localized` verdicts as path-bisection reports.
- `agentic_ops_v7/models.py` (new) — re-exports v6's models with extensions: adds `Hop`, `HopAttribution`, `PathWalkReport`; extends `DiagnosisReport.verdict_kind` with `localized`; adds `localization` field. v6's models are not changed.
- `agentic_ops_v7/docs/agent_logs/` (new directory) — v7's episode logs land here; v6's logs continue to land in `agentic_ops_v6/docs/agent_logs/`. Pre-existing trend analysis on v6 stays valid.

### v7 application-layer phases (copied from v6, no imports)

v7 carries its own copies of v6's application-layer phase files. **No `from agentic_ops_v6 import …` lines exist anywhere in `agentic_ops_v7/`** — this is enforced by a static-analysis test (see Tests below). The copy targets:

```
# Copied verbatim from agentic_ops_v6/ at v7 creation, then evolves
# independently inside agentic_ops_v7/.

agentic_ops_v7/subagents/network_analyst.py
agentic_ops_v7/subagents/instruction_generator.py
agentic_ops_v7/subagents/investigator.py
agentic_ops_v7/subagents/ontology_consultation.py
agentic_ops_v7/guardrails/investigator_consensus.py
agentic_ops_v7/guardrails/investigator_minimum.py
agentic_ops_v7/guardrails/confidence_cap.py
agentic_ops_v7/guardrails/synthesis_pool.py
agentic_ops_v7/guardrails/ig_validator.py
agentic_ops_v7/guardrails/na_linter.py
agentic_ops_v7/guardrails/na_ranking.py
agentic_ops_v7/guardrails/probe_selection.py
agentic_ops_v7/guardrails/evidence_citations.py
agentic_ops_v7/guardrails/base.py
agentic_ops_v7/retry_config.py
agentic_ops_v7/prompts/network_analyst.md
agentic_ops_v7/prompts/instruction_generator.md
agentic_ops_v7/prompts/investigator.md
agentic_ops_v7/prompts/synthesis.md       (modified — adds `localized` verdict handling)
agentic_ops_v7/prompts/ontology_consultation.md
agentic_ops_v7/models.py                  (modified — adds Hop, HopAttribution, PathWalkReport, `localized` verdict_kind)
```

The Synthesis prompt and `models.py` are the only initially-modified files; everything else starts as a verbatim copy. Future application-layer ADRs that target both v6 and v7 land in each module independently. This is the cost of self-containment, accepted explicitly per the v7 self-containment rule in the Decision section.

A static-analysis test (`test_v7_has_no_prior_version_imports`) walks every `*.py` under `agentic_ops_v7/` and rejects any `import` line referencing `agentic_ops_v6`, `agentic_ops_v5`, `agentic_ops_v4`, `agentic_ops_v3`, `agentic_ops_v2`, or the bare `agentic_ops` package (which is v1.5). Allowed dependencies for v7 are:

- `agentic_ops_common.*` — the shared infrastructure layer (models, KB loader, tool façades like `agentic_ops_common.tools.reachability`, the new `agentic_ops_common.path_walk` package).
- Standard library.
- Third-party packages already used by the project (`pydantic`, `google.adk`, `httpx`, `neo4j`, `pyyaml`, etc.).

Tool calls reach `agentic_ops/tools.py` only transitively, via `agentic_ops_common` façades — v7 never imports from `agentic_ops` directly. The static-analysis test is a hard CI gate; introducing a cross-version import fails the build.

### Shared infrastructure

- `agentic_ops_common/path_walk/` (new package, used by v7 and any future version that adds path-walk support):
  - `probers/__init__.py` — `HopProber` Protocol.
  - `probers/kernel.py` — `KernelHopProber` (for `container` and `host_kernel` hop kinds).
  - `probers/docker_bridge.py` — `DockerBridgeProber` (for `docker_bridge` hop kind).
  - `probers/registry.py` — hop_kind → prober dispatch.
- `agentic_ops/tools.py` — add `get_qdisc_drops`, `get_interface_drops`, `get_link_rate_diff` (structured wrappers around the existing ad-hoc calls). `measure_rtt` reworked to take `loss_threshold` and remove the `-c 3` default. (These changes land in shared code; v6 and v7 both pick them up. The reworked `measure_rtt` is backward-compatible — callers without `loss_threshold` get the new safe default at N=66.)
- `agentic_ops_common/tools/reachability.py` — façade updates for the new probes.

### Tests

- `agentic_ops_v7/tests/test_symptom_classifier.py` (new).
- `agentic_ops_v7/tests/test_path_resolver.py` (new).
- `agentic_ops_v7/tests/test_path_walk_investigator.py` (new).
- `agentic_ops_v7/tests/test_orchestrator_routing.py` (new) — asserts classifier output routes to the right branch; asserts `mixed` falls through to application-layer when localization is null.
- `agentic_ops_v7/tests/test_application_layer_parity_with_v6.py` (new) — runs application-layer chaos scenarios (e.g. `HSS Unresponsive`, `MongoDB Gone`, `AMF Restart`) through both v6 and v7 and asserts the diagnoses match at copy-time. v7 has its own copies of the application-layer phases (no v6 imports), so this test is a tripwire: at v7 creation it must pass by construction; over time the test is expected to need updates as v7 evolves application-layer logic, but any *unintentional* divergence (e.g. a copy that didn't carry a prompt-string verbatim) fails CI immediately.
- `agentic_ops_v7/tests/test_v7_has_no_prior_version_imports.py` (new) — static-analysis test enforcing the v7 self-containment rule. Walks every `*.py` under `agentic_ops_v7/`; fails on any `import` referencing `agentic_ops_v6`, `agentic_ops_v5`, `agentic_ops_v4`, `agentic_ops_v3`, `agentic_ops_v2`, or `agentic_ops` (v1.5). Hard CI gate.
- `agentic_ops_common/tests/test_kernel_hop_prober.py` (new).
- `agentic_ops_common/tests/test_docker_bridge_prober.py` (new).
- `agentic_ops_common/tests/test_measure_rtt_sample_calibration.py` (new) — sample-size derivation; hard-fail on any reintroduction of `-c 3`.

### Chaos scenarios

- `agentic_chaos/scenarios/pcscf_packet_loss.py` (new) — the second regression scenario (worked example 2 in Context).
- `agentic_chaos/scenarios/rtpengine_latency_injection.py`, `upf_bandwidth_cap.py`, `bridge_loss.py`, `pcscf_diameter_peer_slow.py` (new) — the four generalization scenarios.
- `agentic_chaos/tests/test_path_walk_e2e.py` (new) — runs all six scenarios against a live stack, comparing v6 and v7 scoring per scenario.

### Chaos runner and GUI

- `scripts/run-all-chaos-scenarios.sh` — already accepts `--agent <version>`. No code change needed; operators add `v7` to their batch invocation. The README and any documented `agent_version` lists gain `v7`.
- `gui/server.py` — the AI Investigation tabs currently expose v1.5/v3/v4/v5/v6; add v7 to the menu. Small wiring change in the tab definitions.
- `agentic_chaos/scoring/` (existing) — extend the per-version score tables to include v7. The output structure (per-scenario × per-version) already supports an arbitrary version count.

### Ontology / KB

- `network_ontology/data/flows/vonr_media.yaml`, `ims_registration.yaml`, `pdu_session_data.yaml` — author per-step `iface` and `hop_kind`. Schema extension covered in a small companion KB-authoring change. (Both v6 and v7 read the ontology, but only v7's path resolver consumes the new fields. v6's ontology consumers ignore them.)
- `network_ontology/data/topology.yaml` (new) — hop list including bridge segments and host kernels for path resolution; future PRs extend with switch/router authoring for carrier-grade deployments.

### Documentation

- `docs/ADR/metric_knowledge_base_schema.md` — append the `hop_kind` schema extension and the `flows[].steps[].iface` field.
- `docs/operators/agent_versions.md` (new or updated) — describe v7's behavior, the v6-vs-v7 A/B-comparison story, and the deprecation trigger ("when v7 decisively beats v6 across the full chaos suite for N consecutive runs, deprecate v6").

### What is *not* changed

- **No edits to `agentic_ops_v6/`.** v6 is frozen. This is structurally important: the v6 vs v7 comparison is only meaningful if v6 is unchanged across the comparison runs. Any future v6 evolution would invalidate prior A/B measurements.
- **No edits to v3/v4/v5.** They continue to run in the chaos suite as the existing baselines.
- **No imports from any prior version into v7.** This is the v7 self-containment rule. v7 carries its own copies of the application-layer phases it inherited from v6 and evolves them independently. Enforced by `test_v7_has_no_prior_version_imports`. No exceptions.
- **No new dependencies in `agentic_ops_common/` that reach back into a prior version.** The shared layer must remain version-neutral. If a future ADR proposes adding common helpers, those helpers may not import from any `agentic_ops_v*` module.

## Alternatives Considered

1. **Inline a warning tag on the value line for known "zero is not exoneration" metrics.** Rejected. This was the prior round's proposal — adding `[⚠ zero is not exoneration]` to the `errors_per_second` header line so the LLM cannot quote the value without the warning. It addresses one metric's failure mode in one symptom class, doesn't generalize to the next transport-layer scenario (delay, bandwidth cap, switch port discard), and keeps the planner in per-NF hypothesis mode where the right probes (qdisc, interface counters, SNMP) aren't even on the candidate list. It treats a symptom of the wrong-shape pipeline, not the cause.

2. **Frame the class as "data-plane" only.** Rejected after the P-CSCF tc-netem worked example showed the same fault class manifesting in the signaling plane. Naming the class for which plane the symptom lives in produces an artificial split and a fix that handles only half the class. The right boundary is the application's `recv()`/`send()` API — above it is application-layer, below it is transport-layer, regardless of whether the affected packets carry RTP or SIP.

3. **Keep per-NF hypothesis generation but require the IG to add a tc-qdisc probe to every transport-shaped plan.** Rejected. The IG already has `check_tc_rules` available and chose not to use it. Mandating it via prompt creates a fragile rule that future prompt edits can erode. The structural fix is to remove the IG from this code path entirely, not to add one more rule it must follow.

4. **Run the path walk *in addition to* the per-NF hypotheses, and let Synthesis pick.** Rejected. Wastes tokens (3 LLM-driven Investigators + 1 deterministic walk for every transport-layer scenario), introduces ambiguity when they disagree, and concedes the planner's primary-shape question. If the path walk is right for transport-layer symptoms, run it alone and skip the wrong-shape work.

5. **Make the path walk an LLM-driven agent that reads the hop list and decides which probes to run.** Rejected. The hop list is fixed, the probe set per hop is fixed by hop_kind, and the kernel/network elements return ground truth. The only LLM contribution would be loop-iteration order or probe selection — both uniform by construction. Adding an LLM here is variance-injection without upside.

6. **Evolve v6 in place rather than introducing v7.** Rejected. The change is architecturally additive (the application-layer pipeline can be left unchanged) and the in-place evolution is technically feasible. But empirical comparability is the decisive concern: the chaos suite cannot directly score "v6 with the path walk" against "v6 without it" if both are the same module at different commits, and the ADR's central claim — that the path walk improves transport-layer diagnosis without regressing application-layer diagnosis — needs to be measured, not argued. Standing up v7 as a separate module with v6 frozen as baseline produces the empirical evidence in every chaos run. See "Evolving v6 vs introducing v7" above for the full trade-off analysis. The maintenance cost (~25% additional tokens per chaos batch, parallel test surfaces) is real but bounded and follows the established v3 → v4 → v5 → v6 versioning pattern.

7. **Implement only `KernelHopProber` and skip the bridge prober.** Rejected. Container kernels cover the most common chaos faults but not all real-world ones — Docker bridge issues (iptables-rule loss, MTU mismatch, conntrack overflow) are a real failure mode in this lab and the closest analog to switch-port issues in carrier networks. Shipping both probers establishes the abstraction (multiple hop kinds) and forces the design to handle hop-type heterogeneity from day one. Future SNMP/IPsec/optical probers slot in without rework.

8. **Author per-flow tc-qdisc-as-a-flow-step in the ontology so the existing flow-walk tools naturally emit qdisc probes.** Rejected as redundant with the path resolver. The ontology's flow steps describe protocol behavior (SIP REGISTER, Diameter MAR, GTP-U Encap), not link-layer transport. Conflating the two would muddy the flow schema for a feature only this ADR uses. The path resolver derives the link-layer hop list *from* the flow's component list; the flow stays clean.

## Follow-ups

- **Carrier-grade hop probers.** `SNMPHopProber`, `IPsecHopProber`, `OpticalHopProber`, `BGPSessionProber`, `WANSyntheticProber`, `MiddleboxProber`. Each is a separate ADR with its own scenario authoring and verification. The abstraction lands now; carrier deployments add probers as the topology requires.

- **Author per-flow interface and hop_kind in the ontology.** This PR ships sane defaults (`eth0`, `container`) for the lab. A follow-up KB-authoring pass populates explicit values for `vonr_media`, `ims_registration`, `pdu_session_data`, `s6a_diameter`, and other major flows.

- **Loss attribution to specific qdisc class on hops with deep qdisc trees.** Today's probe returns the root qdisc's drop counter. Containers and switches can have hierarchical qdiscs (htb / prio with children); a fault could be on a leaf class. A follow-up walks the qdisc tree and attributes to the deepest non-zero `dropped` counter. Out of scope here; lab faults all use root-qdisc.

- **Fold `check_tc_rules` (presence detection) into `get_qdisc_drops` (counter extraction) as one tool.** Cleanup, not a behavior change. Out of scope for this ADR.

- **Active-probing extension in carrier deployments.** When a transit segment is opaque, both endpoints emit synthetic probes and a localization function attributes loss to a transit AS by per-hop RTT and loss profile. Out of scope here; the abstraction (`WANSyntheticProber`) is named for it.

- **Operator-facing "why this verdict is high-confidence" rendering.** The path walk's verdict derives from kernel/SNMP/vendor counters, which is a stronger evidentiary base than LLM per-NF reasoning. The Synthesis output should make this difference visible — attaching the verbatim counter excerpt as evidence and noting "kernel-reported, exact" in the confidence rationale. Cosmetic but operator-relevant.

- **A second-tier deterministic Investigator for application-layer "obvious" faults.** Some application-layer symptoms have similarly deterministic localization (process not running → restart it; subscriber missing in HSS → re-provision it). The pattern of "use an LLM where the search space is unbounded; use deterministic probes where the answer is queryable" generalizes beyond transport-layer. A future ADR explores which application-layer scenarios qualify.

- **Phase 6 deferred — bridge-level loss chaos scenario.** The ADR's Phase 6 listed `bridge_loss` as a generalization scenario (`iptables -A FORWARD -m statistic --mode random --probability 0.3 -j DROP` on the host bridge). Implementing this requires a new `bridge_loss` fault_type in the chaos framework: an injector that nsenters the host network namespace, an iptables rule manager, and a verifier that distinguishes this from the existing `network_partition` fault type. The DockerBridgeProber's iptables/conntrack parsers are already verified by unit tests with synthetic input (`agentic_ops_common/tests/test_docker_bridge_prober.py`), so the localization logic is locked in; the live chaos scenario is the missing piece. Tracked as a follow-up to keep Phase 6 tractable.

- **Phase 6 deferred — `pcscf_diameter_peer_slow` synthetic application-layer fault.** The ADR's Phase 6 listed this as the negative test for the classifier's transport-layer over-triggering. Implementing it requires either container-internal config tampering (modify Kamailio's Diameter timer settings live, then revert) or a new fault type that misconfigures peer-NF reachability without dropping packets. The negative-test intent is satisfied today by Phase 3's existing application-layer fixtures (`MongoDB Gone`, `AMF Restart`, `HSS Unresponsive`) — the integration tests in `agentic_ops_v7/tests/test_transport_layer_pipeline_integration.py::test_application_layer_fixtures_dont_classify_as_transport_layer` and `::test_hss_unresponsive_falls_through_when_path_walk_finds_nothing` verify that the classifier doesn't over-trigger and that null-localization falls through cleanly. Authoring `pcscf_diameter_peer_slow` as a dedicated chaos scenario is tracked as a follow-up that strengthens the empirical case but isn't load-bearing for the ADR's contract.

## Implementation Plan

The work lands in 7 phases. Each phase is a single PR with green CI before the next starts. Phase 1 is foundation (no agent change). Phase 2 establishes v7 as a parity-with-v6 module. Phases 3–4 add the transport-layer pipeline. Phases 5–6 prove the contract and the generalization. Phase 7 is operational integration.

### Phase 1 — Shared foundations + lab probers

**Goal.** Land everything `agentic_ops_v7/` will need in shared infrastructure (`agentic_ops_common/`, `agentic_ops/tools.py`, ontology). No agent changes; no v7 module yet. Probers and tools work standalone, smoke-testable against the running lab stack.

**Deliverables.**
- `agentic_ops_common/path_walk/` (new package):
  - `__init__.py` — exports.
  - `protocol.py` — `HopProber` Protocol + `Hop`, `HopAttribution`, `PathWalkReport` dataclasses.
  - `probers/kernel.py` — `KernelHopProber` for `container` and `host_kernel` hop kinds.
  - `probers/docker_bridge.py` — `DockerBridgeProber` for `docker_bridge` hop kind. Drops into the host network namespace; reads `bridge -s link show`, `iptables -L -v -n`, `conntrack -S`.
  - `probers/registry.py` — hop_kind → prober dispatch.
- `agentic_ops/tools.py` — three new structured-return wrappers:
  - `get_qdisc_drops(container, iface) → {qdisc_kind, sent_pkts, dropped_pkts, dropped_pct, raw}`.
  - `get_interface_drops(container, iface) → {rx/tx_pkts, rx/tx_dropped, rx/tx_errors}`.
  - `get_link_rate_diff(hop_n, hop_n_plus_1, direction, window_s) → {tx_rate, rx_rate, diff, attributed_loss_pct}`.
  - `measure_rtt` reworked: deletes `-c 3 -W 10` default; takes `loss_threshold: float` (default `0.10`); derives sample size via `N = ceil(log(0.001) / log(1 - loss_threshold))`; uses `-i 0.1 -W 1`.
- `agentic_ops_common/tools/reachability.py` — façade updates to expose the new probes.
- `network_ontology/data/flows/vonr_media.yaml`, `ims_registration.yaml`, `pdu_session_data.yaml` — author per-step `iface` and `hop_kind`.
- `network_ontology/data/topology.yaml` (new) — bridge segments and host kernels for path resolution.
- `docs/ADR/metric_knowledge_base_schema.md` — appends the `hop_kind` schema field and `flows[].steps[].iface` field.

**Verification.**
- *Unit:* `test_kernel_hop_prober_returns_structured` — synthetic `tc -s qdisc show` and `ip -s link show` outputs; assert structured returns match schema. Covers tc-netem present/absent, drops zero/non-zero, and tool_unavailable cases per the toolbelt ADR.
- *Unit:* `test_docker_bridge_prober_returns_structured` — synthetic `bridge`, `iptables`, `conntrack` outputs.
- *Unit:* `test_measure_rtt_sample_calibration` — call `measure_rtt(loss_threshold=0.30)` issues `ping -c 20`; `0.10` → `66`; `0.01` → `689`. Hard-fail on any reintroduction of `-c 3`.
- *Unit:* `test_hop_prober_protocol_compliance` — every prober class implements `probe(hop, window_seconds, anchor_ts) → HopAttribution`. Static check at import time.
- *Integration:* against the live stack with chaos `Call Quality Degradation` injected, run `KernelHopProber.probe(rtpengine, eth0)` directly from a Python REPL; assert it returns `drops_attributed_here(kind=qdisc_netem, fraction ≈ 0.30)`. This validates the whole probe stack end-to-end before the agent uses it.

**Exit criteria.** All unit tests pass. The integration smoke test against a running lab stack with rtpengine tc-netem injection produces correct localization. No agent uses any of this yet — v6 is unchanged; v7 doesn't exist.

### Phase 2 — v7 module scaffolding (application-layer-only mode)

**Goal.** `agentic_ops_v7/` exists as a fully self-contained module. v7 runs in the chaos suite and produces diagnoses byte-equivalent to v6 on every scenario (because its application-layer phases are bit-for-bit copies of v6's). No transport-layer pipeline yet — every classification routes to application-layer.

**Deliverables.**
- `agentic_ops_v7/__init__.py`, `__main__.py` — module entry + CLI shim.
- `agentic_ops_v7/orchestrator.py` — runs Phase 0–7 (existing v6 phase shape) using v7's own copies. No classifier yet.
- `agentic_ops_v7/subagents/network_analyst.py`, `instruction_generator.py`, `investigator.py`, `synthesis.py`, `ontology_consultation.py` — copied verbatim from v6.
- `agentic_ops_v7/guardrails/*.py` — copied verbatim from v6.
- `agentic_ops_v7/retry_config.py` — copied verbatim.
- `agentic_ops_v7/prompts/*.md` — copied verbatim except `synthesis.md`, which gets the `localized`-verdict paragraph appended (the verdict isn't emitted yet but the prompt shape is in place).
- `agentic_ops_v7/models.py` — copied from v6, then extended with `Hop`, `HopAttribution`, `PathWalkReport`, and `localized` value added to `DiagnosisReport.verdict_kind` literal. Adds `localization` optional field to `DiagnosisReport`.
- `agentic_ops_v7/docs/agent_logs/` — empty directory; v7's episode logs land here from its first run.
- `agentic_chaos/agents.py` (or wherever the agent registry lives) — `v7` registered.
- `gui/templates/investigate.html` (or equivalent) — `v7` tab added.
- `agentic_ops_v7/tests/test_v7_has_no_prior_version_imports.py` — static-analysis test (the load-bearing CI gate).

**Verification.**
- *Static:* `test_v7_has_no_prior_version_imports` passes. Walks every `*.py` under `agentic_ops_v7/`; rejects any `import` referencing `agentic_ops_v6`, `agentic_ops_v5`, `agentic_ops_v4`, `agentic_ops_v3`, `agentic_ops_v2`, or bare `agentic_ops`.
- *Functional parity:* `test_application_layer_parity_with_v6` runs three application-layer chaos scenarios (`HSS Unresponsive`, `MongoDB Gone`, `AMF Restart`) through both v6 and v7 in sequence, asserts that `primary_suspect_nf`, `verdict_kind`, and `root_cause_confidence` match. Synthesis text doesn't have to match verbatim (LLM non-determinism), but the structured verdict fields must.
- *Smoke:* chaos suite invocation `bash scripts/run-all-chaos-scenarios.sh v7` runs end-to-end against a deployed lab; produces episode logs in `agentic_ops_v7/docs/agent_logs/`; the parity test confirms diagnoses match v6.
- *Existing tests stay green:* every existing test suite (v6, agentic_ops_common, agentic_chaos) continues to pass.

**Exit criteria.** v7 runs the full chaos suite. On every scenario, v7's diagnosis matches v6's structured fields. Static-analysis test enforces self-containment. v7 is now an empirical baseline equal to v6 — every subsequent phase's improvement is measured against it directly.

### Phase 3 — SymptomClassifier (observation-only)

**Goal.** Add `Phase 0.5 SymptomClassifier` to v7's orchestrator. Classify every screener output into `application_layer | transport_layer | mixed`. **Log the classification but do not route on it** — every scenario still goes through the application-layer pipeline. This validates classifier accuracy in real chaos runs without changing v7's behavior.

**Deliverables.**
- `agentic_ops_v7/symptom_classifier.py` — deterministic Python classifier over screener output. Inputs: anomalous-metric list with KB entries. Outputs: label + one-paragraph rationale.
- `agentic_ops_v7/orchestrator.py` — runs the classifier after Phase 0; stores result in episode metadata; does not route on it.
- `agentic_ops_v7/tests/fixtures/screener_outputs/` — fixture screener outputs for each chaos scenario in the suite (`call_quality_degradation`, `pcscf_packet_loss` (synthetic), `data_plane_degradation`, `hss_unresponsive`, `mongo_gone`, `amf_restart`, `dns_failure`, `ims_partition`, `cascading_ims_failure`, `gnb_radio_link_failure`, `s_cscf_crash`, `p_cscf_latency`).

**Verification.**
- *Unit:* `test_symptom_classifier_per_scenario` — parametrized over every fixture; asserts classifier returns the expected label. Coverage: rtpengine packet loss (transport_layer), P-CSCF packet loss (transport_layer), UPF data-plane outage (transport_layer), gNB radio failure (mixed), HSS unresponsive (application_layer), MongoDB gone (application_layer), AMF restart (application_layer), DNS failure (transport_layer), IMS partition (transport_layer), Cascading IMS failure (mixed), S-CSCF crash (application_layer), P-CSCF latency (application_layer or mixed depending on signature).
- *Unit:* `test_symptom_classifier_emits_rationale` — every classification carries a non-empty rationale that names the load-bearing metrics it weighed.
- *Integration:* run the full chaos suite with v7; for each scenario, inspect the episode log's `classification` field; assert the label matches the fixture-based expectation. This catches drift between fixture and live screener behavior.
- *Application-layer parity:* the Phase 2 parity test still passes. Classifier output is metadata-only at this phase; routing is unchanged.

**Exit criteria.** Classifier classifies every chaos scenario correctly. v7's behavior (routing, diagnoses) is identical to Phase 2. The classification log is now usable evidence for Phase 4's routing decisions.

### Phase 4 — PathResolver + PathWalkInvestigator + routing (the contract phase)

**Goal.** Activate the transport-layer pipeline. v7's orchestrator now routes `transport_layer` and `mixed` classifications to the path walk; `application_layer` continues through the existing pipeline. The rtpengine 30% loss scenario localizes correctly to `rtpengine[eth0]` with `verdict_kind=localized` and `confidence=high`.

**Deliverables.**
- `agentic_ops_v7/path_resolver.py` — flow → ordered hop list. Reads ontology flows + topology.yaml; resolves to `[Hop(node, kind, iface), ...]`.
- `agentic_ops_v7/subagents/path_walk_investigator.py` — Python (non-LLM) walker. Iterates hop list in topology order; calls the right `HopProber` per hop_kind from the registry; runs `get_link_rate_diff` between adjacent hops; emits `PathWalkReport` with one `HopAttribution` per hop and per inter-hop link.
- `agentic_ops_v7/subagents/synthesis.py` — handles `localized` verdict. Reads `PathWalkReport`; emits `DiagnosisReport` with `verdict_kind=localized`, `primary_suspect_nf` from first hop with `drops_attributed_here`, `localization` field carrying the verbatim counter excerpt, `confidence=high` for exact-counter attributions.
- `agentic_ops_v7/orchestrator.py` — wires classifier → routing. `transport_layer` → path walk → synthesis. `mixed` → path walk; if `localization is None` → fall through to application-layer pipeline.

**Verification.**
- *Unit:* `test_path_resolver_resolves_vonr_media` — feed the rtpengine-loss screener fixture; assert hop list matches `[e2e_ue1, bridge, nr_gnb, bridge, upf, bridge, rtpengine, bridge, ...]`.
- *Unit:* `test_path_resolver_resolves_ims_signaling` — feed the P-CSCF-loss fixture; assert hop list covers P-CSCF ↔ I-CSCF ↔ S-CSCF.
- *Unit:* `test_path_resolver_picks_most_specific_flow` — multiple flows could match; assert most metric-specific is chosen.
- *Unit:* `test_path_walk_localizes_qdisc_drop` — synthesize hop attributions where one hop returns `dropped_pkts > 0`; assert `PathWalkReport.first_attributed_hop` is that hop.
- *Unit:* `test_path_walk_localizes_inter_hop_link_drop` — TX(N) > RX(N+1); assert `drops_attributed_to_inbound_link` on hop N+1.
- *Unit:* `test_path_walk_no_attribution_returns_null_localization` — all hops clean, no link drops; `localization=None`; orchestrator falls back to application-layer pipeline.
- *Unit:* `test_synthesis_renders_localized_verdict` — synthesize a `PathWalkReport` with one attributed hop; assert `DiagnosisReport.verdict_kind=localized`, `primary_suspect_nf=<hop.node>`, walk-table in explanation.
- **E2E regression A — the contract test:** run `Call Quality Degradation` (rtpengine 30% loss) on v7. Assert: classifier=`transport_layer`; path resolved to VoNR media flow; `PathWalkReport.attributions[rtpengine]=drops_attributed_here(qdisc_netem, 0.30 ± 0.05)`; `verdict_kind=localized`; `primary_suspect_nf=rtpengine`; `confidence=high`; episode log contains verbatim `tc -s qdisc show` excerpt.
- *Application-layer parity:* the Phase 2 parity test still passes.

**Exit criteria.** The originally-failing run passes on v7. The application-layer pipeline behavior is unchanged. The empirical case for the change is now visible: v6 runs the same scenario and mis-diagnoses; v7 localizes correctly.

### Phase 5 — P-CSCF chaos scenario (the second contract test)

**Goal.** Author the P-CSCF tc-netem chaos scenario from Worked Example 2 in the ADR. Both worked examples now pass on v7 and fail on v6.

**Deliverables.**
- `agentic_chaos/scenarios/pcscf_packet_loss.py` (new) — injects `tc qdisc add dev eth0 root netem loss 30%` on the pcscf container; verifies fault propagation; observes for the SIP signaling-rate-drop signature; heals by removing the qdisc.
- Scenario registered in the chaos suite scenario list.

**Verification.**
- *Chaos scenario self-test:* the scenario runs end-to-end (inject → verify propagation → observe → heal) against a healthy stack; heal restores the pre-fault state.
- **E2E regression B:** run `P-CSCF Packet Loss` on v7. Assert: classifier=`transport_layer`; path resolved to IMS signaling flow; `PathWalkReport.attributions[pcscf]=drops_attributed_here`; `verdict_kind=localized`; `primary_suspect_nf=pcscf`; `confidence=high`.
- *Comparison:* run the same scenario on v6 and assert it does *not* localize correctly. (We expect v6 to either DISPROVEN-cascade like the rtpengine case, or land on a wrong NF; either way the comparison data is captured for the A/B story.)
- *Generalization sanity:* the rtpengine regression A still passes after this change.

**Exit criteria.** Both contract scenarios (rtpengine, P-CSCF) pass on v7 and fail on v6. The "same fault class spans data and signaling planes" thesis is empirically proven.

### Phase 6 — Generalization scenarios

**Goal.** Prove the path-walk machinery generalizes beyond `netem loss`. Four new scenarios cover delay, bandwidth cap, bridge-level loss, and an application-layer negative-test that must NOT trigger the path walk.

**Deliverables.**
- `agentic_chaos/scenarios/rtpengine_latency_injection.py` — `tc qdisc add dev eth0 root netem delay 100ms` on rtpengine. Path walk must localize via `latency_at_hop` (sibling of `drops_attributed_here` on `HopAttribution`).
- `agentic_chaos/scenarios/upf_bandwidth_cap.py` — `tc qdisc add dev eth0 root tbf rate 100kbit burst 32kb latency 400ms` on upf. Path walk must localize via tbf's `dropped` counter.
- `agentic_chaos/scenarios/bridge_loss.py` — `iptables -A FORWARD -m statistic --mode random --probability 0.3 -j DROP` on the host bridge. `KernelHopProber` returns clean for every container; `DockerBridgeProber` finds the iptables rule with non-zero packet count; `get_link_rate_diff` shows TX(rtpengine) > RX(upf). Localization names the bridge segment.
- `agentic_chaos/scenarios/pcscf_diameter_peer_slow.py` — synthetic application-layer fault: misconfigure P-CSCF's Rx/Diameter timers so PCF interactions slow without actual packet loss. Classifier MUST return `application_layer`; path walk must NOT run. Existing v7 NA → IG → Investigator pipeline diagnoses normally.
- `HopAttribution.latency_at_hop(observed_delay_ms, evidence)` — new variant on the closed enum, populated by `KernelHopProber` when qdisc kind is `netem` and a `delay` parameter is present.

**Verification.**
- *E2E:* each generalization scenario runs against v7; the assertions pass. Specifically:
  - rtpengine_latency_injection: v7 reports `latency_at_hop` on rtpengine with `~100ms`, `verdict_kind=localized`, `primary_suspect_nf=rtpengine`.
  - upf_bandwidth_cap: v7 reports `drops_attributed_here(qdisc_tbf, ...)` on upf, `primary_suspect_nf=upf`.
  - bridge_loss: v7 reports either `drops_attributed_to_inbound_link` on the affected hops with bridge-prober evidence, or `drops_attributed_here(iptables_drop)` on the bridge node depending on which side fires first; either way, `primary_suspect_nf=bridge` (not a container).
  - pcscf_diameter_peer_slow: classifier=`application_layer`; path walk does not run; v7 produces an application-layer diagnosis (whatever it diagnoses — this is a negative test for over-triggering, not for diagnosis correctness).
- *Comparison data:* same four scenarios run on v6; results recorded. Expectation: v6 fails the three transport-layer ones; v6 may or may not correctly diagnose pcscf_diameter_peer_slow (that depends on existing v6 behavior; it's not a v7 win/loss).
- Application-layer parity (the negative test) still passes.

**Exit criteria.** All four generalization scenarios pass their assertions on v7. The classifier doesn't false-positive on the application-layer scenario. The hop-prober abstraction is empirically proven to extend to delay, rate-cap, and bridge-level faults.

### Phase 7 — Operational integration

**Goal.** v7 becomes part of the standard operational toolchain. Chaos batches include it by default; scoring tables present v6-vs-v7 comparison; operators understand when to use which.

**Deliverables.**
- `scripts/run-all-chaos-scenarios.sh` — accept `v7` as a valid `--agent` value; include both v6 and v7 in the default-batch invocation script (for nightly CI).
- `agentic_chaos/scoring/` — extend the per-version score table to include v7 alongside existing v3/v4/v5/v6. The `list-episodes` output and the per-scenario summary table render v6 and v7 side-by-side.
- `gui/templates/investigate.html` and `gui/static/js/investigate.js` — add v7 tab; same shape as the v6 tab.
- `gui/server.py` — register v7 WebSocket investigation handler.
- `docs/operators/agent_versions.md` (new or updated) — describe v7's behavior, the v6-vs-v7 A/B story, classifier-driven routing, and the v6-deprecation trigger ("when v7 decisively beats v6 on the full chaos suite for N consecutive nightly runs, deprecate v6").
- `agentic_chaos/reports/` — a small report generator that pulls the latest N episode logs from `agentic_ops_v6/docs/agent_logs/` and `agentic_ops_v7/docs/agent_logs/`, computes per-scenario score deltas, and emits a markdown comparison table.
- CI configuration — nightly chaos batch runs both v6 and v7; report is checked into a known location for review.

**Verification.**
- *Smoke:* GUI's Investigate page shows v7 tab; v7 tab successfully runs an investigation against the live stack; episode log lands in `agentic_ops_v7/docs/agent_logs/`.
- *Smoke:* `scripts/run-all-chaos-scenarios.sh v7` runs cleanly from operator workstation.
- *Smoke:* nightly CI batch produces v6 and v7 episode logs; the comparison-report generator renders a table; the table shows v7 winning on transport-layer scenarios (rtpengine, P-CSCF, plus the generalization three) and matching v6 on application-layer scenarios.
- *Documentation:* `docs/operators/agent_versions.md` is reviewed and merged.

**Exit criteria.** v7 is operationally first-class. Every nightly chaos run produces direct v6-vs-v7 measurements. The deprecation trigger for v6 is well-defined and visible.

### Phase ordering and parallelism

| Phase | Depends on | Can run in parallel with |
|---|---|---|
| 1 | (none) | — |
| 2 | 1 (only because v7's models import path-walk types) | KB authoring inside Phase 1 |
| 3 | 2 | — |
| 4 | 1 (probers), 2 (v7 module), 3 (classifier) | — |
| 5 | 4 | — |
| 6 | 4 (path walk active), 5 (regression contract proven) | Phase 7 docs |
| 7 | 6 | — |

Phases 1 and 2 are the most independent and could land within the same week. Phases 3–4 are the heart of the architectural change. Phases 5–6 prove the contract and generalization. Phase 7 is integration.

### What deliberately isn't in scope here

- Carrier-grade probers (`SNMPHopProber`, `IPsecHopProber`, `OpticalHopProber`, etc.) — separate ADRs and PRs as deployments need them. The abstraction lands in Phase 1; carrier probers slot in without rework.
- Deprecating v6 — happens after sustained empirical evidence from Phase 7's nightly comparison. Not a phase of this ADR.
- Folding `check_tc_rules` into `get_qdisc_drops` — listed as a follow-up in the ADR; cleanup, no behavior change.
- Application-layer ADRs that should land in both v6 and v7 — those are separate ADRs; the policy is "land in v7 only since v6 is frozen," but specific exceptions handle as they arise.
