# CDR-0001: Four Novel Failure Scenarios for the Chaos Library

**Date:** 2026-06-02
**Status:** Proposed
**Author:** NOC review
**Related:**
- Existing scenario library: `agentic_chaos/scenarios/library.py` (14 scenarios as of this CDR)
- Fault primitives: `agentic_chaos/tools/{docker,network,application}_tools.py`
- v7 reasoning surface this is meant to stress: `agentic_ops_v7/symptom_classifier.py`, `agentic_ops_common/path_walk/`, `network_ontology/data/causal_chains.yaml`, `network_ontology/data/metrics.yaml`
- v7 path-walk ADR: `docs/ADR/path_prioritizer_walks_all_candidates.md`

---

## Context

The current chaos library has 14 scenarios that exercise the RCA pipeline broadly, but they all sit inside three implicit assumptions:

1. **Space-only faults.** Every scenario degrades a *NF* or a *link* — never a clock, never a counter, never a sequence number. The temporal dimension is untouched.
2. **Global (per-system) faults.** Every scenario either takes the whole VoNR service down or leaves it green. There is no scenario where one UE works and the other doesn't.
3. **Symmetric, payload-uniform faults.** Every `tc netem` rule is symmetric and uniform across packet sizes. The agent's mental model of reachability is bidirectional-by-construction; it never has to ask "in which direction?" or "at what packet size?"

These three assumptions are NOC fairy tales. Real 3 a.m. pages overwhelmingly come from failures that violate exactly these assumptions — clock drift on a Diameter peer, a corrupt subscriber row, asymmetric routing after an SDN reconvergence, an MTU mismatch on a new IPSec tunnel. None of them are in the library.

This CDR proposes four scenarios that each break a different one of those assumptions:

| # | Scenario | Assumption it breaks | New reasoning forced |
|---|----------|---------------------|----------------------|
| 1 | NTP Clock Skew on PyHSS | Space-only | Temporal reasoning |
| 2 | Selective Subscriber Corruption | Global | Per-subscriber comparison |
| 3 | Asymmetric Path Loss (AMF→gNB) | Symmetric | Directional probing |
| 4 | PMTU Black-Hole on N3 | Payload-uniform | Size-stratified reasoning |

Each one is grounded in a documented production failure pattern. Each one extends — but does not replace — an existing fault primitive. Each one targets a *named* capability gap in the current v7 pipeline.

---

## Scenario 1 — NTP Clock Skew on PyHSS

### One-liner

Step PyHSS's wall clock forward by 47 minutes while leaving every other container in sync. Existing 5G NAS and IMS sessions keep working. New registrations fail with cryptic Diameter / SIP authentication errors that don't look like anything the agent has seen before.

### Why this scenario matters — a brief history of clock skew in telecom

Clocks are the silent third-rail of telco operations. Three reasons:

1. **5G NR TDD radio frames are time-aligned across cells.** ±1.5 µs is the typical inter-cell synchronization budget (3GPP TS 38.133 §7.5). When base-station Stratum-1 timing wanders past that, neighboring cells transmit on top of each other during the same TDD subframe — uplink and downlink collide.

2. **Diameter sessions carry timestamps.** Session-Id (RFC 6733 §8.8) embeds a `<DiameterIdentity>;<high32>;<low32>;<optional value>` quadruple where the 64-bit number is "monotonically increasing, but the value SHOULD be derived from local time." When two Diameter peers disagree by tens of minutes on time, retransmission, log correlation, and accounting all start lying.

3. **5G-AKA SQN management is timestamp-flavored.** TS 33.102 §6.3.5 defines the SQN windowing scheme; large clock drift on the HSS makes the SQN-out-of-sync recovery path the *normal* path. The Authentication Reject reason code "MAC failure" / "Synch failure" looks indistinguishable from a real credential compromise — but the actual cause is the clock.

**Production precedents:**

- **The 2012 leap second.** Linux kernel `hrtimer` bug caused `futex_wait` loops to spin a CPU to 100%. Reddit, LinkedIn, Mozilla, Foursquare, and a number of telco platforms running on Linux took hours to recover. The fix was `date -s "$(date)"` — literally setting the clock to itself, to nudge the kernel out of the bad state. Many ops teams learned that night that "we have monitoring on every NF" doesn't help if the monitoring agent's *own* clock is broken.

- **GPS Week Number Rollover — April 6, 2019.** The GPS week-number field is 10 bits and wraps every 1024 weeks (≈19.7 years). Receivers without firmware updates jumped back ~19 years on April 6, 2019. Many cellular base stations use GPS-disciplined oscillators as Stratum-1 references; carriers that hadn't audited their receiver firmware saw localized outages. Same root cause as the 1999 rollover, just two decades later.

- **General industry pattern.** GPS receivers lose lock during severe ionospheric storms (Kp ≥ 7). When the holdover oscillator drifts past the TDD budget, cells start transmitting at the wrong time. Symptom at the NOC: random handover failures and uplink throughput collapse in specific cell sectors — not in a pattern that maps to any one piece of equipment. The clue is in `gpsd` logs, which nobody looks at first.

The general lesson: **clock faults look like crypto faults, routing faults, or radio faults — anything but what they are.** They are perfectly designed to mislead the first three hypotheses an engineer (or an LLM) reaches for.

### What this scenario tests in v7

The v7 pipeline has no notion of time as a fault axis. `symptom_classifier.py` buckets symptoms into `transport_layer` / `application_layer` / `mixed` — there is no `time_sync` bucket. The `metric_inventory` per NF doesn't expose `clock_offset_seconds`. The Investigator's standard probes (`ping`, `dig`, `curl`, log greps) won't surface the skew because they don't read `date`.

If v7 diagnoses this correctly without ontology / KB additions, that is genuinely impressive emergent reasoning. The more likely outcome — v7 misattributes to "credential corruption" or "Diameter peer link failure" — is itself the most useful possible signal: it tells us exactly which ontology entry we need to add (`time_sync` failure mode, with `clock_offset_seconds` as the diagnostic metric).

### Injection mechanism

**Approach A — Container with `SYS_TIME` capability (preferred if PyHSS image rebuild is acceptable):**

```bash
# Add to pyhss compose service:
#   cap_add: [SYS_TIME]
# Then:
docker exec pyhss date -s "@$(( $(date +%s) + 2820 ))"   # +47 min
```

**Approach B — `libfaketime` LD_PRELOAD (no host-side capabilities needed):**

```bash
# Inject by restarting PyHSS with LD_PRELOAD set, or via runtime FAKETIME file:
docker exec pyhss sh -c 'echo "+47m" > /etc/faketime.rc'
docker exec pyhss kill -HUP 1                              # PyHSS re-reads on signal
```

**Approach C — Pure netem-equivalent for clocks (no container modification):** Patch `chrony`/`ntpd` egress to drop or delay, and rely on PyHSS's own NTP client to drift naturally over hours. Too slow for a chaos run; rejected.

**New fault primitive:** `clock_skew` in a new `tools/time_tools.py`. Signature:

```python
async def inject_clock_skew(
    target: str,
    skew_seconds: int,           # positive = forward, negative = backward
    ttl_seconds: int = 600,
    method: str = "faketime",    # "faketime" | "sys_time"
) -> Fault: ...
```

### Expected symptoms

| Surface | Observation |
|---------|-------------|
| Existing UE1 / UE2 NAS + IMS sessions | Green. Calls in progress continue. `ims_usrloc_pcscf:registered_contacts == 2.0` stays steady. **This is the misleading signal.** |
| New UE registration attempts | Fail at Authentication stage. AMF logs `5GMM cause #20 (MAC failure)` or `#21 (Synch failure)` depending on which side rejects. |
| PyHSS Diameter logs | Session-Id timestamps 47 min in the future; CSCFs and AUSF process MAR/SAR responses but `pyhss_diameter_response_latency_ms` shows wild values because the latency calc uses local-now minus response-timestamp. |
| IMS digest auth (if a SIP REGISTER is retried) | `Date` header drift > RFC 3261 §20.17 tolerance — Kamailio may 400-reject. |
| `docker exec pyhss date` vs other NFs | Discrepancy obvious — but only if the agent thinks to ask. |
| All container health checks | Green. CPU, memory, restart count: nominal. |

### Ground-truth label

```yaml
root_cause: pyhss_clock_skew
failure_domain: infrastructure / time_sync
severity: degraded                              # new-attach-only; existing sessions unaffected
affected_components: [pyhss]
fault_type: clock_skew
mechanism: libfaketime +47m
discriminating_signal: clock_offset_seconds(pyhss) >> clock_offset_seconds(peers)
```

### Heal procedure

```bash
# Approach A:
docker exec pyhss ntpdate -u pool.ntp.org \
  || docker exec pyhss date -s "@$(date +%s)"   # restore from host now

# Approach B:
docker exec pyhss rm /etc/faketime.rc
docker exec pyhss kill -HUP 1

# Universal fallback (recorded in SQLite registry):
docker restart pyhss                            # clock re-syncs from host on boot
```

Heal is idempotent. TTL reaper auto-heals at 600 s if the run is interrupted.

### Implementation notes

- Toolbelt audit (`scripts/audit-container-tooling.sh`) must add `date` (universal) and ideally `ntpq` / `chronyc` to the required binary list for time-sensitive NFs.
- Add `clock_offset_seconds` to `network_ontology/data/metrics.yaml` per NF, with `fault_layer: infrastructure` and `agent_exposed: true`. Source can be a one-liner sidecar that polls `(date +%s) - $(curl -s host_time_endpoint)`.
- Add a `time_sync` failure mode to `causal_chains.yaml` with observable symptoms (MAC failure on new attaches, session-id drift, large delta vs. peers).

---

## Scenario 2 — Selective Subscriber Corruption (UE1 only)

### One-liner

Corrupt UE1's K (long-term key) in PyHSS's MySQL while leaving UE2 untouched. UE2 calls work end-to-end. UE1 enters a registration loop and never completes Authentication.

### Why this matters

**Per-subscriber failures are how real telcos fail in production.** Whole-NF outages are dramatic and rare; per-subscriber outages are routine and chronic. Their typical causes:

- Botched OSS/BSS provisioning runs that update some subscribers and skip others
- HSS↔HLR replication lag during a regional failover
- A bad CRUD operation from a customer-care console (somebody types the wrong IMSI into the K-edit field)
- MongoDB / MySQL chunk split or shard migration that leaves a partition with stale data

The NOC pattern is unmistakable: tickets arrive from individual customers (or a small subset — e.g. "all customers provisioned between 02:00–02:15"), every probe of the network itself comes back green, every NF reports healthy, and the first three hypotheses (RAN issue, congestion, IMS routing) all fail one by one until somebody finally diffs HSS rows.

### What this scenario tests in v7

v7's `symptom_classifier` and the upstream `AnomalyScreener` operate on **aggregate** Prometheus metrics. The screener flags "something is off at PyHSS" if `pyhss_auth_failures_total` ticks up — but if only one UE in the pool is affected, the ticking is so slow that it doesn't cross the anomaly threshold on a 2-minute observation window. The screener may return `clean`. The agent never gets called, or gets called with no flags.

The reasoning v7 needs to acquire:

- **Compare UE1's trajectory against UE2's.** Two UEs is the smallest possible "control vs. treatment" experiment. If UE1's `nas_registration_attempts_per_minute` is 10× UE2's, the difference itself is the signal.
- **Treat per-UE counter divergence as a primary symptom**, not as noise to average across.
- **Inspect subscriber data directly** — `query_subscriber` exists in the tool surface; it must be reached for when the divergence is per-UE.

This scenario is the smallest possible forcing function for adding a `selective` blast-radius value and a per-subscriber dimension to the symptom signatures.

### Injection mechanism

**Existing primitive extension.** `application_tools.py` already has subscriber-side actions (`subscriber deletion`, `config corruption`). Add one sibling:

```python
async def corrupt_subscriber_credential(
    imsi: str,
    field: str = "k",               # or "opc"
    ttl_seconds: int = 600,
) -> Fault:
    # 1. Snapshot original value into the fault row (for heal)
    # 2. Compute corrupted value: flip bytes 4..8 of the hex string
    # 3. UPDATE pyhss.subscribers SET k=? WHERE imsi=?
    # 4. Record heal SQL in SQLite registry
```

Target: `IMSI=001011234567891` (UE1 from `e2e.env`). Mutation: flip 4 bytes of the K column. TTL: 600 s.

Why MySQL and not Mongo: the lab uses PyHSS, whose canonical subscriber store is MySQL. (If we ever swap to Open5GS HSS with Mongo subscribers, the same pattern applies with `db.subscribers.updateOne({imsi: …}, {$set: {…}})`.)

### Expected symptoms

| Surface | Observation |
|---------|-------------|
| UE2 (IMSI ...892) | Fully operational. Can register, place, and receive VoNR calls. |
| UE1 (IMSI ...891) | Authentication Response carries RES the AUSF can't match → `5GMM cause #20 (MAC failure)`. RRC connection drops; UE retries every T3510 (15 s). |
| `ran_ue` gauge | Oscillates between 1.0 and 2.0 as UE1 retries. |
| `ims_usrloc_pcscf:registered_contacts` | 1.0 (UE2 only). |
| All container health checks | Green. CPU, memory, restart count: nominal. PyHSS itself is fine. |
| Aggregate `pyhss_auth_failures_total` | Slowly ticking — but maybe not above the screener's threshold over a short observation window. |
| `gnb` connectivity | Green. The fault is post-RRC, at NAS auth. |

### Ground-truth label

```yaml
root_cause: subscriber_data_corruption
failure_domain: subscriber_database / pyhss
severity: partial                                # one of two UEs affected
affected_components: [pyhss]
affected_subscribers: ["001011234567891"]
fault_type: subscriber_credential_corruption
mechanism: SQL UPDATE of K field for one row
discriminating_signal: nas_auth_failures_per_imsi diverges between UE1 and UE2
```

### Heal procedure

Captured at injection time, executed in the heal step:

```sql
-- Heal command stored in SQLite fault registry at inject time:
UPDATE subscribers SET k = '<original_k_hex>' WHERE imsi = '001011234567891';
```

After the heal SQL runs, UE1 still has a stale security context cached in AMF. The cleanest recovery is to bounce UE1's RRC connection (`docker restart e2e_ue1`) so it re-attaches from scratch. The healer should do this automatically when the fault type is `subscriber_credential_corruption`.

### Implementation notes

- Add `selective` to the `BlastRadius` enum in `agentic_chaos/models.py`.
- Add `affected_subscribers: list[str]` to the `Scenario` model and `RcaLabel`. Scorer must accept this as a new dimension.
- Add a `per_subscriber` symptom-signature shape to `network_ontology/data/symptom_signatures.yaml`: "auth-failure rate diverges between subscribers" → "subscriber data corruption".
- Add `nas_auth_failures_per_imsi` (or equivalent) to the AMF metrics exporter, or expose via PyHSS logs grep. This is the only metric that *cleanly* discriminates this fault from a global PyHSS failure.

---

## Scenario 3 — Asymmetric Path Loss (AMF → gNB egress only)

### One-liner

Apply 60% packet loss to AMF's outbound traffic destined for the gNB IP. AMF receives NGAP messages from the gNB perfectly fine. The gNB receives almost nothing back. After three missed SCTP heartbeats, the gNB declares the AMF association DOWN; AMF still thinks the association is UP. New UE attaches enter a black hole.

### Why this matters

Asymmetric path degradation is one of the most operationally infuriating failures because **it breaks the most fundamental assumption an operator brings to a ticket: "if A can ping B, B can ping A."** Real causes:

- SDN underlays where forward and reverse paths take different routes (ECMP hash on a 5-tuple that's not reversible)
- Cross-AZ links in cloud VoNR deployments where one AZ has clean queues and the other is congested
- One-way BFD failure on a router that doesn't propagate the failure into the routing table
- Asymmetric MPLS LSPs where one direction terminates on a degraded line card
- IPsec re-keying where one SA expires before the other (you can encrypt outbound but not decrypt inbound, or vice versa)

The classic NOC story: a customer reports "calls drop after 30 seconds." Ops pings the customer's gateway — perfect. Pings from the gateway back — also perfect, *if launched manually*. Real RTP one-way, however, is in the ditch. The clue is in per-direction interface counters, but every standard reachability probe is two-way by design and averages out the asymmetry.

### What this scenario tests in v7

The v7 path-walk machinery (`agentic_ops_common/path_walk/`) is genuinely good — but every existing scenario has reachability that is either *fully present* or *fully broken*, never directional. The `HopProber` protocol has a direction field in spirit but no scenario exercises it.

The reasoning v7 needs:

- **Probe from both endpoints, not one.** Currently the path walker probes from a single vantage. This scenario will only diagnose correctly if the agent probes the same edge from both sides and treats divergent results as the signal — not as noise to be reconciled.
- **Read SCTP / TCP association state from both sides** and treat "one side says UP, other says DOWN" as discriminating evidence.

### Injection mechanism

**Existing primitive extension.** `network_loss` already wraps `tc qdisc add … netem loss`. Adding a `tc filter` matching `dst $GNB_IP` on AMF's egress qdisc makes the loss apply only to packets headed for the gNB. Egress is one-way at the qdisc layer, so this is naturally directional — no reverse-path rule is needed.

```bash
# Inside AMF container's network namespace (via nsenter):
GNB_IP=$(grep ^GNB_IP network/.env | cut -d= -f2)
IFACE=eth0
tc qdisc add dev $IFACE root handle 1: prio
tc filter add dev $IFACE parent 1:0 protocol ip prio 1 \
    u32 match ip dst $GNB_IP/32 flowid 1:1
tc qdisc add dev $IFACE parent 1:1 handle 10: netem loss 60%
```

**Parameter knob:** `direction` flag on the existing `network_loss` fault spec — `"egress" | "ingress" | "both"` (default `both`). Default behavior is unchanged for existing scenarios.

### Expected symptoms

| Surface | Observation |
|---------|-------------|
| SCTP heartbeats gNB → AMF | Arrive cleanly. AMF logs them as INFO. |
| SCTP heartbeats AMF → gNB | 60% lost. After 3–5 misses, gNB declares the AMF association DOWN. |
| `ping nr_gnb` from inside AMF container | 60% loss. |
| `ping amf` from inside nr_gnb container | **0% loss.** This is the trap — a symmetric reachability probe gives opposite answers from the two endpoints. |
| New UE attaches | Initial UE Message reaches AMF; AMF generates Authentication Request; message lost on egress. UE retries at T3510 (15 s) — also lost. Eventually UE aborts and re-selects cell. |
| Existing PDU sessions | Intact. Data plane is N3 (UPF↔gNB), not N2 (AMF↔gNB); UPF doesn't talk to AMF directly. |
| `gnb` Prometheus gauge | 1.0 from gNB's POV, 0.0 from AMF's POV. Disagreement is the signal. |

### Ground-truth label

```yaml
root_cause: asymmetric_path_degradation
failure_domain: transport / n2
severity: degraded                          # new attaches fail; in-flight PDU sessions unaffected
affected_components: [amf, nr_gnb]
fault_type: network_loss_directional
direction: amf_to_gnb_egress
loss_percent: 60
discriminating_signal: ping_loss(amf→gnb) >> ping_loss(gnb→amf)
```

### Heal procedure

```bash
# Inside AMF netns:
tc qdisc del dev $IFACE root
```

Idempotent (`tc qdisc del` succeeds even if no qdisc is present, except for `root` which may need a sanity check). The fault registry records the exact `tc` deletion sequence at injection time; heal replays it.

### Implementation notes

- Add `direction: str` to `FaultSpec` for `network_loss` / `network_latency` (default `both`). One line in `models.py`; the conditional in `network_tools.py` is small.
- The `path_walk` engine already has a hop-traversal abstraction (`HopProber`). It needs a `probe_both_directions: bool` flag and a "report divergence" output type. Roughly: `HopRecord` gains an optional `reverse_loss_pct` and `reverse_latency_ms`.
- v7's `symptom_classifier` needs an `asymmetric` symptom bucket — distinct from `transport_layer` (which currently presumes symmetric loss).

---

## Scenario 4 — PMTU Black-Hole on N3

### One-liner

Drop the MTU on UPF's N3 interface from 1500 to 1280 and silently drop the ICMP "fragmentation needed" replies that would normally tell senders to back off. Small RTP packets (≈200 B) pass cleanly — voice calls in progress sound fine. SIP messages with full SDP, NAS messages with QoS rules, and any payload over ~1240 B are silently dropped.

### Why this matters

The PMTU black-hole is one of the most operationally famous bugs in IP networking. The combination "MTU mismatch + ICMP-Frag-Needed filtered" defeats Path MTU Discovery and creates failures that depend on **payload size**, which is a dimension no operator instinctively reaches for.

Real causes in telco operations:

- A new IPsec tunnel adds 56 bytes of overhead; nobody updates the inner MTU
- A VxLAN-encapsulated overlay reduces effective MTU by 50 bytes
- A "security hardening" change blanket-drops ICMP at the edge, killing PMTUD as collateral damage
- MPLS LSP with insufficient buffer headroom on a transit router
- Cloud VPC peering across regions where one region has jumbo frames and the other doesn't

The classic operational signature: voice calls — which use small (160–200 B) RTP packets — sound perfect. Video, file transfer, large SIP messages with full SDP bodies, IPSec re-keying messages, and BGP UPDATE messages over ~1240 B fail silently. The NOC sees "voice works but signaling doesn't" — a symptom pattern that maps to *no other failure mode*. Diagnosis takes hours unless someone thinks to inspect by packet size.

### What this scenario tests in v7

v7 has **no payload-size axis at all**. Every metric in `metrics.yaml` is a count, rate, or histogram of latency — never of packet size. Every symptom signature in `symptom_signatures.yaml` treats packets as undifferentiated. The reasoning v7 needs:

- Notice that **some things work and others don't, with the discriminator being payload size, not endpoint or direction.**
- Reach for `tcpdump -nn -v` or interface counters (`ip -s link`) and look at the **packet-size distribution**, not just totals.
- Treat "voice OK, signaling fails" as a coherent diagnostic shape rather than two independent failures.

This scenario is the smallest possible forcing function for adding a size-stratified counter to the data-plane metric set and a `size_dependent` symptom-signature shape to the ontology.

### Injection mechanism

**New compound primitive: `pmtu_blackhole`.** Two operations applied together, undone together:

```bash
N3_IFACE=$(get_n3_iface_for upf)             # from deployment.yaml
# 1) Lower MTU
nsenter -t $(docker inspect -f '{{.State.Pid}}' upf) -n \
    ip link set dev $N3_IFACE mtu 1280
# 2) Silently drop ICMP Frag-Needed replies that would let PMTUD work
nsenter -t $(docker inspect -f '{{.State.Pid}}' upf) -n \
    iptables -A OUTPUT -p icmp --icmp-type fragmentation-needed -j DROP
nsenter -t $(docker inspect -f '{{.State.Pid}}' upf) -n \
    ip6tables -A OUTPUT -p icmpv6 --icmpv6-type packet-too-big -j DROP || true
```

TTL: 300 s. Both operations must succeed for injection to count as verified; if either fails, the fault registry rolls back.

### Expected symptoms

| Surface | Observation |
|---------|-------------|
| Voice calls in progress (small RTP) | Perfect. `ms_call_quality` gauges stay green. RTP RFC 3550 jitter unchanged. |
| `fivegs_ep_n3_gtp_indatapktn3upf` | Continues to increment — small packets are passing. |
| New VoNR call setup (SIP INVITE with full SDP, ~1400 B) | INVITE never arrives at the callee's P-CSCF. UAC retransmits at T1, T2, T4. Eventually 408 Request Timeout. **New calls fail at SDP exchange.** |
| Re-INVITE on mid-call hold | Dies — large SIP message dropped. Hold/resume hangs. |
| New PDU Session Establishment with full QoS rules | NAS PDU Session Establishment Accept (large) dropped. Session never completes. |
| `tcpdump` on UPF N3 (if the agent reaches for it) | Large packets enter, no ICMP-Frag-Needed leaves, senders retransmit indefinitely. |
| Container health, NF Prometheus | Green across the board. No counter reports "I dropped a too-big packet." |

### Ground-truth label

```yaml
root_cause: pmtu_blackhole
failure_domain: data_plane / n3
severity: degraded                          # voice OK; signaling and PDU setup fail
affected_components: [upf]
fault_type: pmtu_blackhole
mechanism: ip link mtu 1280 + iptables -j DROP icmp frag-needed
discriminating_signal: packet_size_distribution shows bimodal pass/fail at ~1240 B threshold
```

### Heal procedure

```bash
# Restore MTU
nsenter -t $PID -n ip link set dev $N3_IFACE mtu 1500
# Flush iptables rule
nsenter -t $PID -n iptables -D OUTPUT -p icmp --icmp-type fragmentation-needed -j DROP
nsenter -t $PID -n ip6tables -D OUTPUT -p icmpv6 --icmpv6-type packet-too-big -j DROP || true
```

Recorded as a two-step heal in the fault registry. Idempotent: re-running heal on an already-healed fault is a no-op (iptables `-D` on a missing rule fails harmlessly, MTU set to existing value is a no-op).

### Implementation notes

- New compound primitive: `pmtu_blackhole` in a new `tools/datapath_tools.py` (or extend `network_tools.py`).
- Add a size-stratified counter to UPF: either via a `tc -s qdisc` derived gauge or a synthetic eBPF tracer that bucketizes packet sizes. Without this, the agent can diagnose only via `tcpdump` interpretation, which is brittle.
- Add a `size_dependent` symptom-signature shape to `symptom_signatures.yaml`: "small packets pass, large packets dropped" → "PMTU black-hole or fragmentation drop". This is the new ontology entry the scenario is meant to motivate.
- Toolbelt audit must confirm `iptables`, `ip6tables`, `nsenter`, `tcpdump` are present on the UPF container — most already required, `ip6tables` is the only addition.

---

## Implementation Roadmap

Ordered by cheapest-first / earliest payoff:

| # | Scenario | Effort | Net new code | KB additions | Earliest meaningful return |
|---|----------|--------|--------------|--------------|-----------------------------|
| 1 | Asymmetric Path Loss | Small | ~30 LoC (`direction` arg to existing `network_loss`) | `asymmetric` symptom bucket | First scenario to expose path-walk single-direction bias |
| 2 | Selective Subscriber Corruption | Medium | ~80 LoC (new `application_tools` action + snapshot/restore + healer special case) | `selective` blast radius + `per_subscriber` symptom shape | First scenario to force per-UE divergence reasoning |
| 3 | NTP Clock Skew | Medium | ~100 LoC (new `time_tools.py`, `libfaketime` plumbing, audit-tooling additions) | `time_sync` failure mode + `clock_offset_seconds` metric | First time-domain fault; high learning value |
| 4 | PMTU Black-Hole | Medium | ~80 LoC (compound primitive in `datapath_tools.py`) + a size-stratified counter | `size_dependent` symptom shape; new size-bucket metric | Forces size-aware reasoning; most "creative" expected behavior from v7 |

Total: roughly one engineer-week to implement all four end-to-end, including the ontology additions and the toolbelt-audit updates. The two `Medium` ones could be split across two engineers in parallel; the `Small` one is genuinely a few hours including a test run.

### Why these four together

Each one breaks a different implicit assumption of the v7 pipeline:

- **Asymmetric Path Loss** — symmetric reachability
- **Selective Subscriber Corruption** — global blast radius
- **NTP Clock Skew** — space-only failures
- **PMTU Black-Hole** — payload-uniform failures

None of the four reduces to any of the others. Each one names a *specific* ontology / metric / classifier gap. After these four land, the agent should be substantially more robust to the classes of failure that NOCs actually call out at 3 a.m.

---

## Open Questions

1. **Should clock skew be tested on more than one NF?** PyHSS is the highest-payoff target (Diameter session timestamps + IMS Date headers). AMF / AUSF are also interesting (5G-AKA SQN management). Recommend starting with PyHSS, adding AMF as a v2 variant.

2. **For Selective Subscriber Corruption — should we extend to "selective by APN" or "selective by RAT" as variants?** Both are realistic (per-APN policy provisioning bugs, RAT-specific subscriber attribute mismatches). Defer until the core scenario lands; either extension is a one-knob change after.

3. **PMTU — do we also want a "fragmentation works but is slow" variant?** I.e., MTU lowered but ICMP replies allowed, so PMTUD works but adds round-trips. That's a degraded-mode rather than a black-hole. Worth a follow-up CDR.

4. **Should the scorer be extended with new fault-type categories before we run these?** Likely yes for `clock_skew` and `subscriber_credential_corruption` — without scorer categories they'll get bucketed as `unknown` and the LLM judge will mis-score. Asymmetric and PMTU might fit under existing `network_loss` + a discriminator, but a fresh category for each is cleaner.

---

## Acceptance Criteria

For each of the four scenarios, "shipped" means:

- [ ] Scenario added to `agentic_chaos/scenarios/library.py`
- [ ] Fault primitive(s) implemented in the appropriate `tools/*_tools.py`, with corresponding heal logic and registry-recorded heal command
- [ ] Ontology additions landed in `network_ontology/data/` and re-seeded (`./scripts/reseed-ontology.sh`)
- [ ] Toolbelt audit (`scripts/audit-container-tooling.sh`) updated for any new required binaries
- [ ] Scorer categories added where applicable
- [ ] At least one successful end-to-end run against v7 from a healthy stack, with the episode JSON + markdown written to `agentic_ops_v7/docs/agent_logs/`
- [ ] At least one chaos batch run (`./scripts/run-all-chaos-scenarios.sh v7`) completes with the new scenario included
- [ ] Heal is verified idempotent — running heal twice on the same fault produces no errors

---

## Status After Review

Awaiting review. Comments inline or as a follow-up CDR.
