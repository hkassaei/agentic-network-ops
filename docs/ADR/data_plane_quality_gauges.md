# ADR: Data Plane Quality Gauges — RTPEngine pps/MOS + UPF KB/s

**Date:** 2026-04-02
**Status:** Amended (2026-04-02)

---

## Decision

Add data plane quality gauges to the monitoring and agent tooling stack. The gauges measure RTPEngine media quality (pps, MOS, packet loss, jitter) and UPF throughput (KB/s on voice bearer).

### Amended Decision: Prometheus-Native Integration

The initial implementation used a custom `get_dp_quality_gauges` agent tool that collected a single snapshot via `MetricsCollector`. Testing revealed two fundamental problems:

1. **Single snapshots are meaningless.** The agent sees `pps = 54` but has no idea if that's degraded — it doesn't know the healthy value was 100. Without a time-series comparison, the gauge is just a number with no context.

2. **MOS from `list totals` is a cumulative average**, not a real-time per-call value. After 317 healthy samples at MOS 4.3, a degraded call barely moves the average. It's useless as a real-time degradation signal.

**The fix:** Export RTPEngine metrics to Prometheus by exposing its built-in HTTP metrics endpoint. This means:

- **Time-series queries become native PromQL** — agents use the existing `query_prometheus()` tool with queries like `rate(rtpengine_packets_total[30s])` or `delta(rtpengine_pps[1m])` to detect trends
- **Trend detection is a query**, not custom code — `rtpengine_pps < 80 AND rtpengine_pps offset 1m > 95` detects a drop from healthy to degraded
- **No custom gauge tool needed** — `get_dp_quality_gauges` is retired in favor of standard PromQL queries via `query_prometheus()`
- **No custom history storage** — Prometheus already stores 5-second resolution time-series with configurable retention
- **Alerting comes for free** — Prometheus alertmanager can fire on MOS < 3.5
- **UPF byte-volume rates** are computed natively via `rate()` instead of hand-rolled two-snapshot deltas in Python

### Implementation Plan

1. **Expose RTPEngine HTTP metrics port** — The config already has `listen-http = localhost:2225`. Change the container to bind this to the Docker network so Prometheus can scrape it.
2. **Add RTPEngine as a Prometheus scrape target** — Add to the Prometheus config alongside the existing Open5GS NF targets.
3. **Retire custom gauge infrastructure** — Remove `get_dp_quality_gauges` tool, `data_plane_gauges()` method, `/api/data-plane-gauges` endpoint. The GUI gauge strip switches to polling Prometheus directly.
4. **Update triage prompt** — Instead of calling a custom tool, the triage agent uses `query_prometheus()` for data plane quality, same as it does for all other NF metrics.
5. **Add PromQL queries to ontology** — The baselines already define thresholds (MOS < 3.5 = alarm). Add the corresponding PromQL queries agents should use to check them.

## Context

### The Problem: A 0% Score on a Detectable Fault

On 2026-04-02, RCA agent v5 scored **0%** on the "Data Plane Degradation" chaos scenario — 30% packet loss injected on the UPF during an active VoNR call. The agent diagnosed a PyHSS Diameter failure with high confidence. The full post-mortem is in `agentic_ops_v5/docs/agent_logs/run_20260402_162230_data_plane_degradation.md`.

The root cause of the misdiagnosis was not bad reasoning — the agent's logic was internally consistent. The failure was upstream: **the agent had no metrics that could reveal data plane quality degradation.**

The only UPF metric available was a cumulative GTP-U packet counter, which showed a delta of +1 during the observation window. Cumulative counters don't reveal packet loss — they still increment, just fewer packets get through. Meanwhile, IMS control plane metrics (INVITE counts, dialog state, response times) changed dramatically due to the call setup that preceded the observation window, pulling the agent's attention toward the IMS layer.

The UE pjsua logs clearly showed `pkt loss=368 (51.1%)`, but UE logs are inaccessible to the agent by design (NOC responsibility isolation). The agent needed a signal source it could actually access.

### What Was Already There But Not Tapped

**RTPEngine** was sitting in the media path with rich quality data — packets/sec, bytes/sec, MOS, jitter, packet loss — all available via `rtpengine-ctl list totals`. However:
- The existing `_collect_rtpengine()` in `gui/metrics.py` was calling `rtpengine-ctl` **without the required `-ip` and `-port` flags** (the CLI listens on `172.22.0.16:9901`, not the default `localhost:9900`). It had been silently failing and returning empty metrics since day one.
- Even if it had worked, the raw totals were collected but no gauge values (pps, MOS) were promoted for easy consumption.

**UPF Prometheus** exposed byte-volume counters per QoS flow (`fivegs_ep_n3_gtp_indatavolumeqosleveln3upf{qfi="1"}`), but these were not queried by the metrics collector. Only packet counters were collected, and those were presented as raw cumulative values with no rate computation.

## Implementation

### Infrastructure: RTPEngine → Prometheus

RTPEngine has a built-in Prometheus HTTP endpoint (`listen-http`) that exposes 170 metrics. It was configured but not exposed outside the container.

**Changes to expose it:**

1. **`network/rtpengine/rtpengine_init.sh`** — Added `--listen-http=$INTERFACE:9091` to the rtpengine process command. Binds the metrics endpoint to the Docker network IP on port 9091 (same port as Open5GS NFs).

2. **`network/metrics/prometheus.yml`** — Added `rtpengine` scrape job:
   ```yaml
   - job_name: 'rtpengine'
     static_configs:
       - targets: ['RTPENGINE_IP:9091']
   ```

3. **`network/metrics/metrics_init.sh`** — Added `sed` substitution for the `RTPENGINE_IP` placeholder.

Prometheus now scrapes RTPEngine every 5 seconds alongside AMF, SMF, UPF, and PCF.

### Agent Tool: `get_dp_quality_gauges()`

**File:** `agentic_ops_v5/tools/data_plane.py`

A single tool that fires 15 PromQL queries against Prometheus in parallel, computes derived values (MOS, loss, jitter as recent averages), and returns a pre-formatted plain-text report. The agent calls one function with no parameters — all PromQL complexity is hidden inside the tool.

**Window:** Fixed at 30 seconds. This is 6 Prometheus scrape intervals, enough for a stable rate while reflecting current state. The agent doesn't choose the window — it always gets "what does the data plane look like right now."

#### The 15 PromQL Queries

**RTPEngine media quality (9 queries):**

| Key | PromQL | Purpose |
|-----|--------|---------|
| `rtp_pps` | `rate(rtpengine_packets_total{type="userspace"}[30s])` | Media packet rate — the primary throughput indicator |
| `rtp_bytes_ps` | `rate(rtpengine_bytes_total{type="userspace"}[30s])` | Media byte rate, converted to KB/s |
| `rtp_sessions` | `rtpengine_sessions{type="own"}` | Active call count (gauge, not a rate) |
| `rtp_mos_rate` | `rate(rtpengine_mos_total[30s])` | Rate of MOS sum accumulation |
| `rtp_mos_samples_rate` | `rate(rtpengine_mos_samples_total[30s])` | Rate of MOS sample accumulation |
| `rtp_loss_rate` | `rate(rtpengine_packetloss_total[30s])` | Rate of packet loss sum accumulation |
| `rtp_loss_samples_rate` | `rate(rtpengine_packetloss_samples_total[30s])` | Rate of loss sample accumulation |
| `rtp_jitter_rate` | `rate(rtpengine_jitter_total[30s])` | Rate of jitter sum accumulation |
| `rtp_jitter_samples_rate` | `rate(rtpengine_jitter_samples_total[30s])` | Rate of jitter sample accumulation |

MOS, loss, and jitter are derived as `rate(sum) / rate(samples)`. This gives the **recent** average over the 30s window, not the cumulative historical average. This is critical — the cumulative `Average MOS` from `list totals` was useless because it was diluted by hundreds of past healthy samples. The rate-of-sum / rate-of-samples approach isolates the quality during the current window.

**UPF data plane throughput (6 queries):**

| Key | PromQL | Purpose |
|-----|--------|---------|
| `upf_in_pps` | `rate(fivegs_ep_n3_gtp_indatapktn3upf[30s])` | GTP-U incoming packet rate |
| `upf_out_pps` | `rate(fivegs_ep_n3_gtp_outdatapktn3upf[30s])` | GTP-U outgoing packet rate |
| `upf_in_bps` | `rate(fivegs_ep_n3_gtp_indatavolumeqosleveln3upf{qfi="1"}[30s])` | Voice bearer (QFI=1) incoming byte rate |
| `upf_out_bps` | `rate(fivegs_ep_n3_gtp_outdatavolumeqosleveln3upf{qfi="1"}[30s])` | Voice bearer (QFI=1) outgoing byte rate |
| `upf_sessions` | `fivegs_upffunction_upf_sessionnbr` | Active PDU sessions (gauge) |

UPF metrics were already in Prometheus (scraped since day one on port 9091). No infrastructure changes needed — the tool just queries them with `rate()` instead of reading raw cumulative counters.

The in/out split is intentional: if `upf_in_kbps >> upf_out_kbps`, traffic enters the UPF but doesn't exit — directly pinpointing the UPF as the loss point.

#### What the Tool Returns

```
Data Plane Quality Gauges (last 30s):

  RTPEngine:
    packets/sec    : 54.2
    throughput     : 4.31 KB/s
    MOS (recent)   : 3.1
    loss (recent)  : 28.4
    jitter (recent): 2.3
    active sessions: 1

  UPF:
    in  packets/sec: 52.1
    out packets/sec: 36.5
    in  throughput : 8.2 KB/s
    out throughput : 5.7 KB/s
    active sessions: 4
```

All values are per-second rates over the last 30 seconds. MOS, loss, and jitter are recent averages (not cumulative). All queries fire in parallel (~1 Prometheus round trip). The agent reads plain numbers — no PromQL knowledge required.

### Where the Gauges Are Exposed

| Consumer | Mechanism | File |
|----------|-----------|------|
| RCA agents | `get_dp_quality_gauges()` tool on TriageAgent + InvestigatorAgent | `agentic_ops_v5/tools/data_plane.py` |
| Prometheus | Native scrape of RTPEngine + existing UPF scrape | `network/metrics/prometheus.yml` |
| GUI | Gauge strip below header (via MetricsCollector, which also reads RTPEngine CLI for backward compatibility) | `gui/index.html`, `gui/server.py` |

### Files Modified

**Prometheus integration:**
- **`network/rtpengine/rtpengine_init.sh`**: Added `--listen-http` flag to expose Prometheus metrics on Docker network.
- **`network/metrics/prometheus.yml`**: Added `rtpengine` scrape job.
- **`network/metrics/metrics_init.sh`**: Added `RTPENGINE_IP` sed substitution.

**Agent tool:**
- **`agentic_ops_v5/tools/data_plane.py`**: Rewrote to query Prometheus directly with 15 parallel PromQL queries over a 30s window. No MetricsCollector dependency.
- **`agentic_ops_v5/tools/__init__.py`**: Exports `get_dp_quality_gauges`.
- **`agentic_ops_v5/subagents/triage.py`**: Tool in TriageAgent's tool list.
- **`agentic_ops_v5/subagents/investigator.py`**: Tool in InvestigatorAgent's tool list.
- **`agentic_ops_v5/prompts/triage.md`**: Prompt instructs triage agent to call the tool as step 3 of data collection.

**GUI (from initial implementation, still in place):**
- **`gui/metrics.py`**: Fixed RTPEngine CLI connection (`-ip`/`-port`); added UPF byte-volume queries; MOS parser deduplication fix.
- **`gui/server.py`**: `/api/data-plane-gauges` endpoint.
- **`gui/index.html`**: CSS gauge strip with color-coded thresholds.

**Ontology:**
- **`network_ontology/data/baselines.yaml`**: Added `rtpengine` section with MOS thresholds (excellent ≥4.3, good ≥4.0, acceptable ≥3.5, poor ≥3.0, unusable <3.0), pps/loss/jitter expected values, and UPF KB/s gauge.

## How This Enables Better Agent Decisions

### Before: Blind Spot

The agent's only data plane signal was cumulative GTP-U packet counts. These are useless for detecting degradation:

| Metric | Healthy | 30% Loss | Agent sees |
|--------|---------|----------|------------|
| `gtp_indatapktn3upf` | 3000 → 3050 (+50) | 3000 → 3035 (+35) | "Both increased. Fine." |

The agent couldn't distinguish healthy from degraded because cumulative counters always go up. The initial snapshot-based tool didn't help either — the agent saw `pps = 54` but had no reference point to know that was degraded.

### After: Rates Over a Window

The tool returns per-second rates over the last 30 seconds. The agent sees the current data plane state:

| Gauge | Healthy Call | 30% Loss | What the agent sees |
|-------|-------------|----------|---------------------|
| RTP pps | ~100 | ~54 | Reduced packet rate during active call |
| RTP MOS (recent) | 4.3 | ~3.1 | MOS below 3.5 — quality degraded |
| RTP loss (recent) | 0 | ~28 | Active packet loss on media path |
| UPF in KB/s | ~8 | ~8 | Traffic entering UPF normally |
| UPF out KB/s | ~8 | ~5.7 | Traffic exiting UPF is lower — loss at UPF |

The in/out asymmetry at the UPF is the strongest signal: traffic goes in but less comes out. Combined with RTPEngine showing reduced pps and elevated loss, the agent has multiple corroborating signals pointing to data plane degradation at the UPF.

The tool's docstring teaches the LLM what to look for:

```
Use this to detect data plane degradation:
- RTP pps drops during active call = packet loss on media path
- UPF out KB/s << UPF in KB/s = packet loss at the UPF
- MOS dropping below 3.5 = voice quality degradation
- UPF pps = 0 with active sessions = data plane dead
```

### Why Recent MOS Matters

The initial implementation used cumulative `Average MOS` from RTPEngine's `list totals` — a historical average across ALL past sessions. After 317 healthy samples at MOS 4.3, a degraded call barely moved the number. Useless.

The Prometheus-native approach computes MOS as `rate(rtpengine_mos_total[30s]) / rate(rtpengine_mos_samples_total[30s])`. This gives the average MOS **only from RTCP reports received in the last 30 seconds** — isolating the current call's quality from historical data. During a 30% loss scenario, this drops to ~3.1 while the cumulative average would still show ~4.2.

### What This Doesn't Fix

Two other problems from the post-mortem remain for future work:

1. **Call setup noise in the observation window.** The chaos framework's observation window still captures call setup artifacts. A stabilization delay after `CallSetupAgent` would prevent this.

2. **Pre-existing anomaly confusion.** The agent still can't distinguish pre-existing conditions (e.g. `uar_timeouts=2` at baseline) from fault-induced symptoms. The anomaly detector should only flag metrics that changed after injection.

## Alternatives Considered

1. **Custom `get_dp_quality_gauges` agent tool (initial implementation):** Collected a single snapshot via `MetricsCollector` and returned raw gauge values. Rejected after testing — single snapshots give no trend context, and the agent couldn't distinguish degraded from healthy without a reference point. Also required custom history storage, a separate API endpoint, and a dedicated tool, all duplicating what Prometheus already provides.

2. **Custom tool with built-in sampling window:** The tool would sleep for N seconds, take two snapshots, and compute deltas. Would work but re-invents time-series storage, blocks the agent during the sleep, and doesn't compose with PromQL's native rate/delta/offset capabilities.

3. **Scrape pjsua RTP stats from UE containers:** Would give the most accurate per-call quality data, but violates the NOC access isolation design — agents don't have access to UE/RAN logs.

4. **Prometheus-native via RTPEngine HTTP metrics (chosen):** RTPEngine already has a built-in Prometheus endpoint (`listen-http`). Exposing it to the Docker network and adding it as a scrape target gives full time-series data with zero custom code. Agents use `query_prometheus()` — no new tools, no custom history, no separate endpoints. Rate computation, trend detection, and alerting are native PromQL.
