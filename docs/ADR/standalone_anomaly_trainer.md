# ADR: Standalone Anomaly Model Trainer — Separation of Training from Testing

**Date:** 2026-04-06
**Status:** Implemented
**Supersedes:** The inline training approach in `docs/ADR/anomaly_detection_layer.md` (Phase 0 training during `_pre_check_stack_health()`)
**Related:**
- `docs/ADR/anomaly_detection_layer.md` — parent ADR for the anomaly detection layer
- `agentic_ops_v5/docs/agent_logs/run_20260406_171720_p_cscf_latency.md` — 1500ms run, score 0% (screener produced 0 flags)
- `agentic_ops_v5/docs/agent_logs/run_20260406_180817_p_cscf_latency.md` — 5000ms run, score 60% (screener produced 0 flags)

## Context

The initial implementation of the anomaly detection layer (per `anomaly_detection_layer.md`) trained the River HalfSpaceTrees model inline during the chaos framework's `_pre_check_stack_health()` phase. This approach had three fatal flaws that surfaced during the first real test runs:

### Flaw 1: Training on an idle stack is useless

The model was trained on 24 snapshots of a healthy **idle** stack — all counter rates were 0, all gauges were constant. The model learned that "normal" = silence. When the fault was injected and traffic was generated, the model compared "active traffic with fault" against "silence" — but both active-traffic-with-fault and active-traffic-without-fault deviate equally from silence. The model couldn't distinguish healthy traffic from degraded traffic because it had never seen healthy traffic.

Evidence: Both test runs showed `AnomalyScreener | 0 | 0 | 0` — zero flags despite dramatic metric changes (16 REGISTER retransmissions, 3 active transactions) that the chaos framework's own `FaultPropagationVerifier` easily detected.

### Flaw 2: Preprocessor state was lost between training and scoring

The `MetricPreprocessor` builds counter state (previous values for delta computation) during training. But Phase 0 scoring in the v5 orchestrator created a **new** preprocessor from scratch, losing all counter state. The first (and only) scoring snapshot produced all-zero counter rates — identical to the training data — so the score was always 0.

### Flaw 3: High-dimensional feature space diluted detection

With 143 raw features (most constant), HalfSpaceTrees' random axis-aligned splits rarely straddled the anomalous dimensions. Testing confirmed: 143 features → score 0.095 (below threshold); 5 focused features → score 0.992 (perfect detection).

## Decision

**Separate anomaly model training from chaos testing entirely.** Training becomes a standalone, independent phase that:

1. **Generates realistic IMS traffic** on a healthy stack (SIP REGISTER, VoNR calls, hang-ups, idle periods) — not silence
2. **Collects metrics during active traffic** so the model learns what healthy registrations, healthy calls, and healthy idle look like
3. **Persists the trained model to disk** for reuse across all chaos scenarios
4. **Is run once** (or periodically), not on every test run

### Why training must be separate from testing

1. **The model represents the network's healthy baseline, not a specific test's baseline.** Different scenarios inject different faults, but they all compare against the same "healthy" reference. Train once, reuse across all scenarios.

2. **Training takes time (5 minutes) and shouldn't delay every test run.** Loading from disk takes <1 second.

3. **Training requires active traffic that modifies stack state.** Placing calls and hanging up leaves traces (dialog counters, RTP stats). This would contaminate the chaos framework's pre-fault baseline snapshot.

4. **Reproducibility.** A persisted model gives consistent behavior across runs. Inline training produces slightly different models each time due to timing jitter.

5. **Training traffic must be richer than any single scenario generates.** The P-CSCF Latency scenario only triggers re-registration. The Data Plane Degradation scenario only needs an active call. The trained model must have seen BOTH patterns, plus idle, to detect anomalies in any context.

## Implementation

### New module: `anomaly_trainer/`

Located at the repo root (not under `agentic_ops_v5/` since it's independent of the agent version).

```
anomaly_trainer/
├── __init__.py        # Module docstring
├── __main__.py        # CLI entry point
├── traffic.py         # IMS traffic generator (SIP REGISTER, VoNR calls, random patterns)
├── collector.py       # Metric collector (5s polls → preprocessor → screener.learn())
└── persistence.py     # Save/load trained model artifacts to/from disk
```

### CLI

```bash
# Train the model (requires stack + UEs running and IMS-registered)
source agentic_chaos/.venv/bin/activate
python -m anomaly_trainer --duration 300

# With debug logging
python -m anomaly_trainer --duration 300 -v

# Custom output directory
python -m anomaly_trainer --duration 300 --output /path/to/model/
```

### Traffic generation patterns

The trainer generates randomized realistic IMS traffic for the full training duration:

| Activity | Weight | Duration | What it exercises |
|----------|--------|----------|-------------------|
| Register both UEs | 20% | 3-8s gap | SIP REGISTER rates, 200 OK rates, Diameter UAR/MAR/SAR at I-CSCF/S-CSCF |
| Register one UE | 15% | 3-6s gap | Same, but asymmetric |
| VoNR call | 45% | 5-30s hold + 3-8s settle | dialog_ng:active, RTP pps, bearers_active, QoS flows |
| Idle | 20% | 3-10s | Establishes the idle baseline between activities |

This ensures the model sees the full envelope of healthy behavior: registration bursts, call setup/teardown, active media, and idle periods.

### Persisted artifacts

```
agentic_ops_v5/anomaly/baseline/
├── model.pkl             # Trained AnomalyScreener (River model + feature means)
├── preprocessor.pkl      # MetricPreprocessor (counter state from last training snapshot)
└── training_meta.json    # Metadata: when trained, samples, features, model readiness
```

### Feature filtering

Only diagnostically important metrics are included (34 features instead of 143):
- AMF: ran_ue, gnb, amf_session
- SMF: sessions, bearers, PFCP sessions
- UPF: sessions, GTP-U packet rates
- P-CSCF: REGISTER rate, reply rates, active transactions, contacts, dialogs
- I-CSCF: Diameter timeouts, response times
- S-CSCF: contacts, registration rates, Diameter timeouts
- RTPEngine: MOS, pps, packet loss, sessions
- PyHSS/MongoDB: subscriber counts

This keeps the feature space small enough for HalfSpaceTrees to build effective splits.

### Chaos framework integration

`_train_anomaly_model()` in `agentic_chaos/orchestrator.py` was replaced with `_load_anomaly_model()`:

```python
def _load_anomaly_model() -> None:
    from anomaly_trainer.persistence import load_model
    screener, pp, meta = load_model()
    if screener is None:
        log.warning("No trained model. Run: python -m anomaly_trainer --duration 300")
        return
    challenger._trained_anomaly_screener = screener
    challenger._trained_preprocessor = pp
```

No training during the test. Load from disk in <1 second.

### V5 orchestrator Phase 0

Phase 0 uses the loaded preprocessor (which carries counter state from the last healthy training snapshot) to compute meaningful deltas:

```
Training end:  pcscf.core:rcv_requests_register = 50 (after all healthy traffic)
Scoring:       pcscf.core:rcv_requests_register = 66 (after fault + retransmissions)
                → delta = 16, rate = 16/30s = 0.53/s (trained normal: ~0.1/s during registration bursts)
                → anomaly flagged
```

## Consequences

**Positive:**
- Model trained on realistic active traffic — can distinguish healthy vs degraded patterns
- Training separated from testing — no overhead per test run, reproducible results
- Persisted model reusable across all chaos scenarios
- Feature space reduced from 143 to 34 — HalfSpaceTrees detection is effective
- Preprocessor counter state preserved — meaningful deltas during scoring

**Negative:**
- Extra manual step before first test run (`python -m anomaly_trainer --duration 300`)
- Model must be re-trained when: network topology changes, new NFs added, codec config changes, subscriber count changes
- Pickle-based persistence ties the model to the Python/River version it was trained with

**Risks:**
- If the model is stale (trained days ago on a different stack state), it may produce false positives or miss anomalies. Mitigation: `training_meta.json` records when the model was trained; the chaos framework can warn if it's old.
- If UEs aren't IMS-registered when training starts, the traffic generator will fail. Mitigation: the trainer will log failures and continue; the CLI prints prerequisites.
