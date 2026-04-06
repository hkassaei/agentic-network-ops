# ADR: Anomaly Detection Layer — Time-Series ML over LLM for Metric Screening

**Date:** 2026-04-05
**Status:** Proposed
**Supersedes:** N/A
**Related:**
- `docs/ADR/v5_6phase_pipeline.md` — current 6-phase architecture
- `docs/ADR/data_plane_idle_stack_rule.md` — idle-state gate that contributed to the observability gap
- `docs/ADR/upf_counters_directional_stack_rule.md` — UPF counter asymmetry gate (same pattern: per-metric prompt engineering)

## Context

The v5 pipeline's NetworkAnalystAgent (Phase 1) uses an LLM to both **detect** metric anomalies and **interpret** them. This approach has repeatedly failed at the detection step, even when the anomalies were obvious to a human reading the same data.

### Critical observations that drove this decision

Two P-CSCF Latency scenario runs on 2026-04-05 exposed the fundamental limitation:

#### Run 1: `run_20260405_223112_p_cscf_latency` (500ms latency, scored 100%)

- **What the chaos framework did:** Injected 500ms egress delay on P-CSCF, then triggered fresh SIP REGISTER from both UEs via `ControlPlaneTrafficAgent` (the `rr` pjsua command). The registrations traversed the delayed P-CSCF path.
- **What was visible in metrics:** `tmx:active_transactions` would have been elevated during the REGISTER transaction window. `core:rcv_requests_register` deltas, `sl:200_replies` stalling — all available via `get_nf_metrics`.
- **What the NetworkAnalyst reported:** All layers GREEN. *"UEs are registered with the IMS. The media plane is idle, which is the expected state."* It looked at the cached `ims_usrloc_pcscf:registered_contacts=2` (stale from before fault injection) and ignored the transaction counters.
- **Why:** The 500ms registrations eventually completed (SIP T1=500ms, transaction timeout=32s), so by the time Phase 1 ran (~30s later), the evidence window had closed. The point-in-time snapshot looked healthy.
- **Scoring anomaly:** The agent scored 100% because the Investigator later found the latency via `measure_rtt` — but the diagnosis hallucinated the injection mechanism (`tc netem`, `tc qdisc show`) from LLM training knowledge, which the scorer didn't penalize.
- **Full analysis:** `agentic_ops_v5/docs/agent_logs/run_20260405_223112_p_cscf_latency.md`, Post-Run Analysis section.

#### Run 2: `run_20260405_231838_p_cscf_latency` (5000ms latency, scored 25%)

- **What the chaos framework did:** Same as Run 1 but with 5000ms delay (10x worse).
- **What was visible in metrics:** The chaos framework's `FaultPropagationVerifier` recorded clear symptoms in the episode:

  | Node | Metric | Baseline | Current | Delta |
  |------|--------|----------|---------|-------|
  | pcscf | `core:rcv_requests_register` | 10 | 30 | **+20** |
  | pcscf | `sl:1xx_replies` | 8 | 10 | **+2** |

  20 new REGISTER requests at P-CSCF in 30 seconds — the UEs sent 2 re-registrations but with 5000ms delay, SIP retransmission timers (T1=500ms) fired repeatedly. 20 REGISTERs with only 2 provisional replies and zero 200 OKs. **This is a screaming obvious anomaly** that any delta computation would catch.
- **What the NetworkAnalyst reported:** All layers GREEN. *"The network is healthy and operational... 2 UEs are registered."* Same blindness as Run 1.
- **What the Investigator did:** Ran `measure_rtt("pcscf", "172.22.0.19")`. With 5000ms delay, `ping -c 3 -W 2` (2-second timeout) timed out before the packet left. The tool reported "100% packet loss." The Investigator diagnosed total connectivity failure on two paths (P-CSCF→I-CSCF AND AMF→gNB), when only the P-CSCF had elevated latency. The AMF→gNB "100% packet loss" was either fabricated evidence or the agent ran the probe from the wrong container.
- **Final diagnosis:** *"100% packet loss on two critical communication paths, rendering 5G Core and IMS non-functional."* Score: 25%.
- **Full analysis:** `agentic_ops_v5/docs/agent_logs/run_20260405_231838_p_cscf_latency.md`, Post-Run Analysis section.

### Why the LLM fails at anomaly detection

The NetworkAnalyst prompt (`agentic_ops_v5/prompts/network_analyst.md`) is 163 lines long. It has:
- 38 lines for the idle data plane gate (added after a previous false-positive run)
- 20 lines for UPF counter asymmetry gate (added after another false-positive run)
- Zero lines for kamcmd SIP transaction counter interpretation

Every new metric class that the LLM fails to interpret requires adding more prompt-specific guidance — a per-metric "gate" that teaches the LLM what that specific metric means and how to reason about its values. This approach has four fundamental problems:

1. **Doesn't scale.** This stack has ~60 metrics across 9 instrumented components. VoLTE, data, and IoT use cases will add hundreds more. Writing a prompt gate for each metric is not feasible.

2. **Attention drift.** LLMs process metrics as text tokens. By the time it reads metric #200 in the `get_nf_metrics` output, it has forgotten metric #15. The `core:rcv_requests_register` jump from 10→30 was right there in the tool output and the LLM sailed past it.

3. **No statistical reasoning.** LLMs can't compute z-scores, detect distribution shifts, or track rate-of-change. They pattern-match on text, not numbers. A delta of +20 on a counter that was at 10 is a 200% increase — trivial arithmetic the LLM didn't perform.

4. **Counter semantics.** Counters (monotonically increasing values like `core:rcv_requests_register`) require delta computation to be meaningful. A point-in-time read of "30" tells the LLM nothing — it needs to know the previous value was "10" to detect the anomaly. The LLM has no mechanism for this; it receives a single snapshot.

### The pattern repeating

This is not the first time we've patched the LLM prompt to fix a specific metric-interpretation failure:

- `data_plane_idle_stack_rule.md` — added because the LLM flagged zero UPF throughput as a failure when no call was active
- `upf_counters_directional_stack_rule.md` — added because the LLM subtracted UPF ingress from egress counters and concluded "massive packet loss"
- Now: LLM missed 20 SIP REGISTER retransmissions because no one wrote a "kamcmd transaction counter gate"

Each fix is correct in isolation but the approach is unsustainable. We are manually encoding statistical reasoning into natural language, one metric at a time.

## Decision

**Separate anomaly detection (what changed?) from anomaly interpretation (what does it mean?).**

Detection is a math problem — algorithms do it perfectly, instantly, at any scale. Interpretation is a reasoning problem — that's where the LLM and ontology add value.

### Implementation: ML-Based Anomaly Detection

Rather than building a deterministic delta screener that still requires hand-curated baselines per metric (which doesn't scale to VoLTE/data/IoT use cases with hundreds of metrics each), go directly to a proper ML-based anomaly detection model that learns "normal" automatically from healthy-state observations.

### Library Evaluation

We evaluated 10 open-source Python anomaly detection libraries against these requirements:
- Python native, BSD/Apache licensed
- Active project (not abandoned/archived)
- Lightweight (no GPU, runs alongside aiohttp)
- Minimal configuration — works reasonably well out of the box
- Unsupervised — learns from healthy-state data, no labeled anomalies needed
- Fast inference — score hundreds of metrics in <1 second
- Handles gauges and counter-derived rates

| Library | Stars | Last Release | Active? | License | Time-Series Native | Streaming/Online | Dependencies | Verdict |
|---------|-------|-------------|---------|---------|-------------------|-----------------|--------------|---------|
| **PyOD** | 9.8K | v2.1.0 (Apr 2026) | Very active | BSD-2 | No (tabular) | Limited | Lightweight (sklearn, numba) | **Tier 1** — best for batch, zero-config ECOD algo |
| **River** | 5.8K | 0.23.0 (Nov 2025) | Very active | BSD-3 | Partial | **Yes** (core design) | **Lightest** (numpy, scipy, pandas) | **Tier 1** — best for streaming, HalfSpaceTrees |
| **Kats** | 6.3K | v0.2.0 (Mar 2022) | Internal Meta only | MIT | **Yes** (strongest) | No (batch) | **Very heavy** (PyTorch, fbprophet, pystan) | **ELIMINATED** — broken on Python 3.10+ |
| **STUMPY** | 4.1K | v1.14.1 (Feb 2026) | Very active | BSD-3 | **Yes** (matrix profile) | Yes (`stumpi`) | Very light (numpy, numba) | **Tier 2** — pattern anomalies, complements Tier 1 |
| **Merlion** | 4.5K | v2.0.2 (Feb 2023) | **ARCHIVED Mar 2026** | BSD-3 | Yes | Yes | Moderate | **DEAD** — do not use |
| **GluonTS** | 5.2K | 0.16.2 (Jun 2025) | Slowing | Apache-2.0 | Yes (forecasting) | No | **Heavy** (PyTorch) | Wrong tool — forecasting, not AD |
| **Alibi Detect** | 2.5K | v0.13.0 (Dec 2025) | Moderate | **BSL 1.1** | Yes | Limited | **Heavy** (transformers, opencv) | **DISQUALIFIED** — not open source |
| **TODS** | 1.7K | None | **Dead** (2023) | Apache-2.0 | Yes | No | Heavy (D3M) | Dead project |
| **ADTK** | 1.2K | v0.6.2 (Apr 2020) | **Dead** (2020) | MPL-2.0 | Yes | No | Lightweight | Dead project (6 years) |
| **Luminaire** | 801 | 0.4.3 (Jan 2024) | Dormant | Apache-2.0 | Yes | Limited | Moderate (outdated pins) | Dormant, dependency conflicts |
| **PySAD** | 285 | v0.3.4 (Jun 2025) | Low | BSD-3 | No | Yes | Moderate (hard PyOD pin) | Too small/risky as primary dep |

### Key findings: Merlion is dead, Kats is unusable

**Merlion:** Salesforce **archived** the repository on March 11, 2026. Last release was v2.0.2 in February 2023 — over 3 years ago. No bug fixes, no security patches, no Python compatibility updates. Cannot be used.

**Kats (Facebook/Meta):** Despite 6.3K stars and impressive algorithm breadth (CUSUM, BOCPD, Prophet-based detection, multivariate VAR, meta-learning), Kats is effectively unusable outside Meta's internal environment:
- **Last public release:** v0.2.0, March 2022 — over 4 years ago. No new PyPI release since.
- **Broken on Python 3.10+:** The published package pins `numpy>=1.21,<1.22`, `pandas<=1.3.5`, `statsmodels==0.12.2`, `fbprophet==0.7.1`, `pystan==2.19.1.1` — none of which work with modern Python.
- **Installation is broken:** The most-commented issue (#308, 26 comments) is "pip install kats fail." Multiple issues (#316, #317, #324, #330, #334, #335) report installation failures. The fbprophet/pystan dependency chain is notoriously fragile.
- **Heavy dependencies:** Requires PyTorch, fbprophet (deprecated), pystan 2.x (requires C++ compiler), ax-platform, gpytorch.
- **Not truly maintained for open-source users:** Recent commits are automated syncs from Meta's internal `fbcode` monorepo (bot commits for Black formatting, internal refactoring, Pyre type-checker fixes). Community PRs sit unreviewed for years (oldest from Oct 2021). External issues receive no maintainer response.
- **No streaming support:** Batch-only API despite BOCPD being theoretically an online algorithm.
- **Buggy multivariate support:** Open issues from 2021-2024 about multivariate detector errors remain unresolved.

Kats has the best native time-series handling (`TimeSeriesData` class) and the most diverse algorithm catalog of any evaluated library. But none of that matters if it can't be installed. It is a cautionary tale of an internal tool mirrored to GitHub without genuine open-source commitment.

### Recommended approach: River (primary) + PyOD (secondary)

**River** is the best fit for the streaming use case:

- **`learn_one()` / `score_one()` API** maps directly to the 5-second polling loop — feed each metrics snapshot as it arrives, the model updates incrementally
- **HalfSpaceTrees** algorithm is purpose-built for streaming multivariate anomaly detection — fast, low memory, minimal hyperparameter sensitivity
- **Lightest dependency footprint** of all evaluated options (numpy, scipy, pandas)
- Natural `dict` input format matches metric snapshots (`{metric_name: value, ...}`)
- BSD-3 licensed, very active community (5.8K stars, 80 commits in last 6 months)

**PyOD** as a secondary/validation detector:

- **ECOD algorithm** has literally zero hyperparameters — perfect for "no tuning" requirement
- Catches different anomaly types than HalfSpaceTrees (point anomalies in multivariate feature space vs. streaming distribution shifts)
- Fit on a sliding window of recent healthy data, re-fit periodically
- 9.8K stars, most mature library in this space

**Neither library handles counter-type metrics natively.** A thin preprocessing layer (~30 lines) must:
1. Maintain previous counter values in memory
2. Compute delta = current - previous (handling counter resets)
3. Compute rate = delta / interval_seconds
4. Feed rates (not raw counters) to the anomaly detector

This is actually preferable to a library guessing at counter semantics.

### Integration architecture

```
Metrics Collection (existing get_nf_metrics, get_dp_quality_gauges, every 5s)
    ↓
Preprocessing (new, ~30 lines)
    - Counters → compute delta/rate
    - Gauges → pass through
    - All → normalize to feature dict
    ↓
AnomalyScreenerAgent (new BaseAgent, no LLM)
    - River HalfSpaceTrees: learn_one() during healthy baseline, score_one() during monitoring
    - Optional: PyOD ECOD on sliding window for cross-validation
    - Output: [{metric, component, anomaly_score, severity, direction}]
    ↓
NetworkAnalyst LLM (existing — but now receives pre-flagged anomalies as context)
    → "These 3 metrics are anomalous: [list]. Interpret them using the ontology."
    → Uses ontology for causal reasoning, failure chain mapping
    ↓
Rest of v5 pipeline (unchanged)
```

The anomaly detector doesn't need to know what any metric **means** — it only detects statistical deviation from learned normal. The ontology + LLM handle meaning and causal reasoning. Clean separation of concerns.

### Training flow

1. **Healthy baseline collection:** During the `_pre_check_stack_health()` phase (already exists in `agentic_chaos/orchestrator.py`), collect 2-5 minutes of metrics at 5-second intervals. Feed each snapshot to River's `learn_one()`.
2. **Monitoring mode:** After fault injection, switch to `score_one()`. Anomaly scores above threshold trigger flagging.
3. **Continuous learning:** In the GUI's topology page, the 5-second polling loop can continuously train the model during normal operation, so the baseline adapts to the current deployment state.

### LLM hallucinating injection mechanisms

Split into its own ADR: `docs/ADR/agents_must_not_suggest_actions.md`

The Run 1 diagnosis referenced `tc netem` and `tc qdisc show` despite having no tool that reads tc rules. The LLM infers the mechanism from training knowledge. The Investigator and Synthesis prompts have been updated (as of 2026-04-06) with explicit constraints: *"Never reference simulation or injection mechanisms. Diagnose the observable failure mode, not the injection method."* See `docs/ADR/agents_must_not_suggest_actions.md` for details.

## Consequences

**Positive:**
- Anomaly detection becomes reliable, instant, and scales to any number of metrics
- LLM focuses on what it's good at: reasoning about flagged anomalies using domain knowledge
- New metrics/use cases (VoLTE, data, IoT) don't require per-metric prompt engineering — just run the system healthy for a few minutes and the model learns baselines automatically
- River's streaming API (`learn_one` / `score_one`) fits naturally into the existing 5-second polling loop
- Both River and PyOD are actively maintained, BSD-licensed, and lightweight

**Negative:**
- Requires collecting healthy-state training data per use case — adds a "calibration" step to deployment
- Adding a new agent phase increases pipeline latency slightly (though the BaseAgent runs in <100ms)
- Counter preprocessing layer must be built and maintained (not complex, but one more piece)
- Two new dependencies (river, pyod) added to requirements

**Risks:**
- Cold start: if the model hasn't seen enough healthy data, it may produce false positives or miss anomalies (mitigation: require minimum training window before enabling anomaly scoring; fall back to ontology baselines during cold start)
- Concept drift: if the network's normal behavior changes (e.g., more UEs added), the model needs to re-learn (mitigation: River's online learning continuously adapts; PyOD can be periodically re-fit)
- Anomaly score threshold tuning: while the algorithms are "zero config", the threshold for flagging anomalies may need tuning per deployment (mitigation: start with a conservative threshold; the ontology's `alarm_if` conditions provide a fallback for critical metrics)
