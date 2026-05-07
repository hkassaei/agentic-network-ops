# ADR: Metric Knowledge Base — Schema Draft

**Date:** 2026-04-17 (schema); 2026-04-19 (open questions resolved)
**Status:** Accepted (schema finalized; content migration and implementation are follow-ups)
**Related:**
- [`anomaly_model_feature_set.md`](anomaly_model_feature_set.md) — companion doc, describes the 29 DERIVED features the anomaly model sees. Remains authoritative for model features.
- [`agentic_reasoning_capability_gaps.md`](agentic_reasoning_capability_gaps.md) — Gap 3 ("per-metric semantic interpretation") motivates this.
- `network_ontology/data/baselines.yaml` — current source this KB will eventually replace (minimal cleanup landed; full replacement pending this schema's approval).

---

## Scope

This ADR proposes a **schema** for a structured knowledge base that describes every RAW metric the system collects. It does not propose content migration. Authoring content against the schema is a follow-up task, to be done per-metric with review.

**Important scope boundary:** the KB describes metrics and emits **events** when notable state transitions occur. It does NOT declare alarms. Alarms require operational context (planned change windows, subscriber lifecycle activity, coordinated multi-metric correlation) that is beyond any single NF's visibility. That layer is a separate component — see [`alarm_correlation_engine.md`](alarm_correlation_engine.md) (stub).

The KB is not a replacement for `anomaly_model_feature_set.md`. The two serve different consumers and will coexist:

| Document | Describes | Consumer | Baselines source |
|---|---|---|---|
| `anomaly_model_feature_set.md` | 29 derived/normalized features fed to HalfSpaceTrees | Anomaly model operators; agents reasoning about screener output | Trained-model statistics |
| Metric Knowledge Base (this ADR) | Every raw metric the system collects from NFs | Agents reasoning about raw metrics via `get_nf_metrics`, NOC engineers | Domain-expert invariants |

Cross-references between the two are first-class: a KB entry that feeds a model feature names the feature; a feature in the model doc names the underlying raw metric(s).

---

## Why a new structure

`baselines.yaml` today mixes three concerns: (a) metric descriptions, (b) test-stack-specific expected values, (c) alarm thresholds. Its biggest problems:

1. **Scale-dependent baselines.** `ran_ue: expected: 2` is only valid for the 2-UE test stack. Real deployments differ; agents trained on this file carry false assumptions. The recent minimal cleanup annotated these but did not structurally fix them.
2. **Inconsistent field use.** Some entries have `typical_range`, some have `expected`, some have both, some have thresholds-with-tiers (MOS), some just a `description`. No predictable shape.
3. **No explicit semantics.** Entries describe WHAT the metric is but rarely what a deviation MEANS about the NF's responsibility. The agent relies on the LLM's prior knowledge.
4. **No cross-references.** Related metrics (e.g., `icscf.cdp:average_response_time` ↔ `icscf.ims_icscf:uar_avg_response_time`) are structurally independent; the relationship lives only in prose.
5. **No link to the anomaly model.** A reader of `baselines.yaml` cannot tell which raw metrics feed which model features.

The proposed schema fixes all five.

---

## Design principles

1. **Every entry is scale-independent.** Where an absolute number is deployment-specific, it is expressed as an invariant relationship to other metrics or configuration (e.g., `amf_session == ran_ue * configured_apns_per_ue`).
2. **Semantics are explicit.** Each entry has a `meaning` block that describes what a change in the metric tells you about the NF — a spike means X; a drop means Y.
3. **Orthogonal layer and plane classification.** `layer` (infrastructure / ran / core / ims) captures where the NF sits in the hierarchy — same taxonomy as `components.yaml`. `plane` (control / user / media) captures what kind of traffic the metric reflects. Filtering metrics by plane lets the reasoner answer questions like "is signaling clean but data plane broken?" mechanically.
4. **Events, not alarms.** The KB captures event triggers — conditions under which a metric emits a structured event. It does NOT declare alarms. A metric emitting `ran_ue_sudden_drop` is a fact; whether that event is alarming depends on correlation with other events and operational context that no single metric can know. That decision lives in a separate layer.
5. **State categories (when useful) are observation-level, not severity-level.** MOS tiers (excellent / good / poor) describe what state the metric is in, not how alarmed the operator should be.
6. **Relationships are explicit.** Related metrics, composite metrics, and derived features are first-class links.
7. **Pre-existing noise is a first-class concept.** Deployment-specific quirks (e.g., the pcscf httpclient noise floor) are flagged so agents can ignore them without rediscovering.
8. **Everything referenced by the reasoner is queryable.** The schema is YAML; loader produces a typed object model similar to the other ontology files.

---

## Top-level schema

```yaml
# metrics.yaml — structure mirrors baselines.yaml's hierarchy for consistency
metrics:
  <nf_name>:                        # e.g., amf, pcscf, icscf, rtpengine
    layer: <layer>                   # infrastructure | ran | core | ims
    metrics:
      <metric_key>:                  # raw metric name as emitted
        # --- Identity ---
        display_name: "<human-friendly name>"
        source: <source_type>        # prometheus | kamcmd | rtpengine_ctl | mongosh | api | derived
        type: <type>                 # gauge | counter | ratio | derived
        unit: <unit_or_null>         # ms | packets_per_second | percent | count | null
        protocol: <protocol>         # Diameter/Cx | SIP/Mw | GTP-U/N3 | NGAP/N2 | null if N/A
        interface: <3gpp_interface>  # Cx | Mw | N2 | N3 | null
        plane: <plane>               # control | user | media
                                     # Orthogonal to layer. What kind of traffic
                                     # does THIS METRIC reflect? (Not a property of the
                                     # NF — a property of the metric.)
                                     #   control: signaling (SIP, Diameter, NGAP, NAS, PFCP)
                                     #   user:    bearer/data traffic (GTP-U on N3, N6)
                                     #   media:   RTP/RTCP media streams (relay/transcoding)
                                     # Most NFs in this stack collect metrics in a single
                                     # plane (CSCFs → control; RTPEngine → media). UPF is
                                     # the main cross-plane case (GTP-U counters are user;
                                     # PFCP session-state gauges are arguably control).

        # --- Semantics ---
        description: |
          Narrative description. What the metric measures, where it comes from
          operationally. Not agent-reasoning guidance.
        meaning:
          what_it_signals: |
            What a CHANGE in this metric tells the reasoner about the NF's
            current state and responsibility. This is the interpretation layer.
          spike: "What a sudden increase implies"
          drop: "What a sudden decrease implies"
          zero: "What current=0 implies"
          steady_non_zero: "What stable non-zero value implies (for ratios/gauges)"

        # --- Healthy expectations ---
        healthy:
          scale_independent: <bool>
          typical_range: [<low>, <high>]   # null if highly variable
          invariant: |
            For scale-dependent metrics: the relationship that IS invariant,
            expressed in terms of other metrics or configuration.
            Example: "amf_session == ran_ue * configured_apns_per_ue"
          pre_existing_noise: |
            Optional. Deployment-specific baseline noise that agents should
            ignore. e.g. "This stack has a persistent 1300-1500 baseline
            due to SCP_BIND_IP placeholder; only alert if delta > 100."

        # --- State categories (optional) ---
        # Descriptive bands that partition the value range into named states.
        # Useful for metrics where a band-change is semantically meaningful
        # (e.g., MOS moving from "good" to "poor"). Not a severity ranking —
        # just a way to name regions of the value range.
        state_categories:
          - name: <category_name>             # e.g., excellent, good, poor
            condition: ">= <value>"
            meaning: "<what being in this band indicates>"

        # --- Event triggers (structured) ---
        # Conditions under which a metric emits a structured event for the
        # alarm correlation engine to consume. Events are FACTS, not alarms.
        # The correlation engine combines events with operational context
        # (change windows, subscriber lifecycle, planned activities) and
        # correlates across NFs to decide whether an alarm should fire.
        #
        # Each trigger MUST include at least one of:
        #   - a temporal predicate (transition from prior state)
        #   - a correlation predicate (joint condition with another metric)
        #   - a lifecycle predicate (only applies in a named phase)
        # Raw snapshot predicates like "current = 0" are observations, not
        # triggers — they produce false events during startup or idle periods.
        event_triggers:
          - id: <unique_event_type>            # globally unique event identifier
            trigger: "<expression in the event DSL — see below>"
            clear_condition: "<expression>"    # optional — when the event is resolved
            persistence: <duration>            # optional — must hold this long before firing
            local_meaning: |
              What this event tells you about THIS metric's state. Does NOT
              claim alarming significance. Does NOT attribute cause.
            magnitude_captured:                # fields the event payload carries
              - current_value
              - prior_stable_value
              - delta_absolute
              - delta_percent
              - first_observed_at
            correlates_with:                   # HINTS for the correlation engine
              - event_id: <other_event_id>
                composite_interpretation: "<what the combination suggests>"

        # --- Relationships ---
        related_metrics:                 # metrics whose interpretation depends on this one
          - metric: <another_metric_key>
            relationship: "<describe: e.g., 'composite_of', 'derived_from', 'correlated_with', 'discriminator_for'>"
            use: |
              How to use them together when reasoning.
        composite_of: [<metric_keys>]    # if this metric is an average/rate computed from others
        feeds_model_features:            # cross-reference to anomaly_model_feature_set.md
          - <feature_name>
            # e.g., this raw counter is the source of the sliding-window rate feature

        # --- Probing ---
        how_to_verify_live:              # when metric is suspicious, how to confirm it's real
          tool: <tool_name>
          args_hint: "<guidance>"
        disambiguators:                  # other metrics that distinguish causes when this deviates
          - metric: <other_metric>
            separates: "<hypothesis A> vs. <hypothesis B>"

        # --- Metadata ---
        applicable_use_cases: [<list>]   # e.g., [vonr, 5g_core, ims_signaling]
        deprecated: <bool>
        tags: [<list>]                   # searchable tags
```

### Field conventions

- All top-level blocks (`identity`, `semantics`, `healthy`, `state_categories`, `event_triggers`, `relationships`, `probing`, `metadata`) are OPTIONAL *individually*. Every entry should have at minimum: `description`, `type`, `source`, and either `healthy.typical_range` or `healthy.invariant`.
- `layer` and `plane` are ORTHOGONAL. `layer` is structural — a property of the NF, matches `components.yaml`'s classification. `plane` is functional — a property of the METRIC, not the NF. Most NFs in the current stack emit metrics in a single plane (CSCFs → control; RTPEngine → media). The clearest cross-plane NF would be a gNB (NGAP on N2 + GTP-U on N3), though we don't collect gNB metrics directly. UPF is the one NF we collect from that could plausibly span control and user planes.
- `scale_independent: true` requires NOT setting `invariant` (the metric doesn't have one — it's already scale-free).
- `scale_independent: false` REQUIRES setting `invariant`.
- `feeds_model_features` is the primary cross-reference to `anomaly_model_feature_set.md`. A feature in the model doc that references a raw metric MUST have a corresponding raw-metric entry here pointing back.
- `meaning.zero` is load-bearing for silent-failure reasoning. Explicit because it's often ambiguous ("metric is 0" can mean "subsystem idle" or "subsystem dead").
- `event_triggers[].id` uses the globally unique namespace `<layer>.<NF>.<event_name>` (e.g., `core.amf.ran_ue_sudden_drop`, `ims.icscf.cdp_latency_elevated`). This matches the metric-identifier convention and makes event provenance obvious in correlation logs.
- `event_triggers[].trigger` **never** has a severity or alarm field. Any severity or alarm classification is the correlation engine's job, with access to context the KB doesn't have.
- `state_categories` are observation bands, not alarms. "MOS is in the `poor` band" is a fact about the metric's current state; whether that's alarming depends on whether calls are active, whether this is planned, etc.
- `meaning.what_it_signals` and other narrative fields: keep to **3-5 sentences** as a general rule. Long enough to capture nuance (when to trust the zero, when the composite differs from the sum of its parts), short enough to be read as context rather than studied.

### Event-trigger DSL and storage

The trigger expression language is formally Python-expression syntax, parsed and evaluated by [`simpleeval`](https://github.com/danthedeckie/simpleeval). Expressions call registered predicate functions against a `MetricContext` object that provides current value, history access, and related-metric lookup. Authors in YAML write readable expressions; the loader parses and validates them at load time.

**Registered predicates:**

Predicates on the current value — native Python operators: `==`, `!=`, `>`, `<`, `>=`, `<=`.

Temporal predicates:
- `prior_stable(window='5m')` — median of the metric during the last window, filtered to stable periods.
- `value_at_time_ago('60s')` — the metric's value that far in the past.
- `dropped_by(current, baseline, fraction)` — boolean: decrease of more than `fraction` from `baseline`.
- `increased_by(current, baseline, fraction)` — inverse of `dropped_by`.
- `sustained(predicate_result, min_duration='60s')` — the predicate has held true for at least the duration.
- `persistence(min_duration='60s')` — shorthand for `sustained` applied to the whole trigger condition.
- `rate_of_change(window='5m')` — first derivative over the window.
- `no_prior_stable(gt=0)` — the metric has never had a stable non-zero baseline (e.g., startup, never-deployed).

Correlation predicates — reference other metrics by their namespaced KB key:
- `related('core.amf.gnb') == 0` — joint condition on another metric's current value.

Lifecycle predicates:
- `phase == 'steady_state'`, `phase == 'startup'`, `phase == 'draining'`.
- Phase comes from an out-of-band deployment-state signal; source TBD, not in scope here.

Composition uses Python boolean operators: `and`, `or`, `not`, parentheses.

**Example compound trigger (in the actual syntax the evaluator consumes):**
```
current == 0 and prior_stable(window='5m') > 0 and persistence(min_duration='60s') and not (phase == 'startup')
```

**Why `simpleeval` specifically:** it parses to Python AST, restricts operators to a safe whitelist (no `eval`, `exec`, import, attribute access), and lets us register predicate functions without grammar changes. It's actively maintained, small, and familiar. If we outgrow it, the AST shape is standard Python — we can swap in a Lark grammar or a pydantic-validated structured form later without rewriting the trigger corpus.

### Storage backing the DSL

`simpleeval` evaluates expressions; the data behind each predicate comes from a three-tier storage picture:

```
┌─────────────────────────────┐
│ simpleeval evaluator        │  ← expression parsing only
│ (trigger DSL)               │
└─────────┬───────────────────┘
          │ calls predicates
          ▼
┌─────────────────────────────┐
│ Predicate functions         │
│ (prior_stable, dropped_by,  │
│  persistence, ...)          │
└─────────┬───────────────────┘
          │ queries
          ▼
┌─────────────────────────────┐       ┌───────────────────────────┐
│ MetricHistoryStore          │       │ Event Store (SQLite → PG) │
│   ├─ Prometheus backend     │       │ Persisted fired events    │
│   └─ In-memory ring buffer  │       │ for correlation engine    │
│ (already exist)             │       │ (new component)           │
└─────────────────────────────┘       └───────────────────────────┘
```

1. **Metric time-series — long-window history: Prometheus.** Already running at 5-second resolution with 15-day default retention. Predicates like `prior_stable(window='5m')`, `rate_of_change(window='10m')`, `value_at_time_ago('1m')` translate internally to PromQL queries against the HTTP API. No new infrastructure.

   *Coverage caveat:* not every metric in the KB is in Prometheus today. Most Kamailio fields accessible via `kamcmd` (e.g., `core:rcv_requests_register`, `cdp:average_response_time`, `dialog_ng:active`) are only available via the CLI. Closing this gap with a `kamailio-mod-prometheus` exporter is the cleaner long-term path — afterwards every KB metric is uniformly queryable via PromQL. Short-term, the `MetricHistoryStore` abstraction supports both a Prometheus backend and a kamcmd-polling fallback, so authoring is not blocked on exporter work.

2. **Short-window / in-agent state: the preprocessor's in-memory ring buffer.** Already exists (`MetricPreprocessor._history`), holds ~30 seconds of recent snapshots. Predicates with short windows hit this directly.

3. **Event store — persisted fired events: new, SQLite-backed.** When a trigger fires, the event is persisted so the correlation engine can reason over event timelines ("which events fired in the last 5 minutes?", "did these two fire within 10 seconds of each other?"). Event rate is low; SQLite is sufficient for single-node dev, upgradable to Postgres when multi-host matters. Minimal schema: `events(id, event_type, source_metric, source_nf, timestamp, magnitude_payload_json, cleared_at)`.

Only the event store is new infrastructure. The rest exists.

### Relationship types (enum)

`related_metrics[].relationship` must be one of:

| Value | Meaning |
|---|---|
| `composite_of` | This metric is numerically composed of the related one (e.g., P-CSCF register time decomposes into UAR + MAR + SAR + SIP forwarding). |
| `derived_from` | This metric is computed from the related one (e.g., a rate feature derived from a cumulative counter). |
| `normalized_from` | This metric is a per-UE normalization of the related one. |
| `correlated_with` | Moves together in healthy or faulty state; no strict composition. |
| `discriminator_for` | Inspecting this metric helps distinguish hypotheses about the related one. |
| `upstream_of` | Precedes in the causal/flow chain. |
| `downstream_of` | Inverse of `upstream_of`. |
| `peer_of` | Same metric at a different NF (e.g., `rcv_requests_register` at I-CSCF vs. S-CSCF). |

Schema validation rejects any other value. Extending the enum is an explicit ADR revision, not an author-time decision.

### Schema validation

**Pydantic as the primary loader; export JSON Schema for editor tooling.**

- `network_ontology/metrics_loader.py` defines pydantic v2 models mirroring the YAML structure. Loading a YAML file runs pydantic validation; type errors, enum-violations, missing-required-fields, and unknown-field errors are caught at load time with line references.
- `metrics_loader.py` includes a `generate_json_schema()` function that produces the JSON Schema via `ModelClass.model_json_schema()`. Checked into the repo as `network_ontology/schema/metrics.schema.json` for editor integration (VS Code, IntelliJ YAML plugins use it for autocomplete and inline validation).
- Cross-reference validation (e.g., `feeds_model_features` points to a feature that exists in `anomaly_model_feature_set.md`; `correlates_with.event_id` points to an event that exists somewhere in the KB) runs as a post-load pass, reporting dangling references.

### Disambiguators — clarifying the reasoning-time role

`disambiguators` and `correlates_with` both point to related metrics or events, but they serve different consumers at different moments:

- **`correlates_with`** — for the **correlation engine at event-firing time**. "Events A and B firing together mean X." The engine asks: given a set of fired events, what's the composite meaning?
- **`disambiguators`** — for the **active reasoner (Network Analyst, Investigator, human operator) at diagnosis time**. "You're uncertain about why THIS metric moved; these other metrics would narrow your hypothesis tree." The reasoner asks: which metrics would discriminate between my candidate causes?

**Concrete example.** Agent observes `ims.icscf.cdp:average_response_time` at 600ms (baseline ~51ms). Two plausible hypotheses:

- **H1:** HSS is slow — Diameter path intact, HSS processing under load. All queries complete, just slowly.
- **H2:** HSS is partially unreachable — some Diameter packets dropping, some queries timing out.

Both hypotheses are consistent with the elevated response time alone. The disambiguator entry tells the reasoner exactly what to check next:

```yaml
disambiguators:
  - metric: ims.icscf.uar_timeout_ratio
    separates: "HSS slow (ratio=0, all replies received) vs. partial partition (ratio>0, some timeouts)"
  - metric: ims.scscf.mar_avg_response_time
    separates: "I-CSCF↔HSS leg only (only cdp at icscf spikes) vs. HSS-wide (both CSCF response times spike)"
```

The reasoner reads this and plans its probes: "fetch `icscf.uar_timeout_ratio` — if 0, it's H1; if >0, it's H2." This is orthogonal to any event firing; the agent may be reasoning about the metric because the screener surfaced it, not because a trigger fired.

Keep both: different consumers, different moments in the reasoning process, cheap to author.

---

## Worked examples

### Example 1 — Simple scale-dependent gauge

```yaml
amf:
  layer: core
  metrics:
    ran_ue:
      display_name: "RAN-attached UEs"
      source: prometheus
      type: gauge
      unit: count
      protocol: NGAP
      interface: N2
      plane: control

      description: |
        Count of UEs currently attached to the 5G RAN via this AMF, reported
        by the AMF Prometheus endpoint. Incremented on successful attach,
        decremented on detach.

      meaning:
        what_it_signals: |
          Fundamental RAN health indicator. Any UE that successfully completed
          initial registration appears here; any UE that lost the N2 association
          disappears within seconds.
        drop: "UEs losing RAN access. Partial drop = scattered UE issues; total drop = N2/gNB-wide failure."
        zero: "Total RAN failure — N2 association down, gNB crashed, or AMF isolated from RAN."

      healthy:
        scale_independent: false
        typical_range: null
        invariant: |
          Equals configured UE pool size in healthy steady state.
          Closely tracks pcscf.ims_usrloc_pcscf:registered_contacts in VoNR mode
          (IMS-registered count should equal or be just below RAN-attached count).

      event_triggers:
        - id: core.amf.ran_ue_sudden_drop
          trigger: "dropped_by(current, prior_stable(window='5m'), 0.2) and persistence(min_duration='60s')"
          clear_condition: "sustained(current >= 0.9 * prior_stable(window='5m'), min_duration='60s')"
          local_meaning: |
            RAN-attached UE count decreased sharply from a previously stable
            baseline and stayed down. Does NOT attribute cause — could be RAN
            failure, subscriber offboarding, maintenance, AMF-side attach
            processing, or normal detach flow.
          magnitude_captured: [current_value, prior_stable_value, delta_absolute, delta_percent, first_observed_at]
          correlates_with:
            - event_id: core.amf.gnb_association_drop
              composite_interpretation: "gNB/N2 failure — RAN access lost"
            - event_id: infrastructure.mongo.subscribers_decrease
              composite_interpretation: "Planned offboarding — benign"
            - event_id: infrastructure.pyhss.subscribers_decrease
              composite_interpretation: "Planned offboarding — benign"
            - event_id: core.amf.process_restart
              composite_interpretation: "Expected transient during AMF lifecycle event"
            - event_id: core.smf.ues_active_drop
              composite_interpretation: "Coordinated UE loss across AMF and SMF — likely RAN-side"

        - id: core.amf.ran_ue_full_loss
          trigger: "current == 0 and prior_stable(window='5m') > 0 and persistence(min_duration='30s') and not (phase == 'startup')"
          clear_condition: "sustained(current > 0, min_duration='30s')"
          local_meaning: |
            All previously-attached UEs have disappeared from the AMF. Not
            emitted during startup (when zero is expected).
          magnitude_captured: [current_value, prior_stable_value, first_observed_at]
          correlates_with:
            - event_id: core.amf.gnb_association_drop
              composite_interpretation: "Total RAN failure — both gNB and UEs gone"
            - event_id: infrastructure.mongo.subscribers_decrease
              composite_interpretation: "Full subscriber base offboarded — benign"

      related_metrics:
        - metric: amf.gnb
          relationship: discriminator_for
          use: "If ran_ue drops but gnb stays stable, UEs are losing attachment (subscriber-level issue); if both drop, gNB is down."
        - metric: smf.ues_active
          relationship: correlated_with
          use: "Should match ran_ue in steady state. Drift indicates PDU-session-establishment problems."
        - metric: pcscf.ims_usrloc_pcscf:registered_contacts
          relationship: correlated_with
          use: "In VoNR mode, IMS registrations typically equal RAN attachments within a few seconds lag."

      how_to_verify_live:
        tool: get_nf_metrics
        args_hint: "Fetch AMF snapshot; compare with gnb value. Follow up with check_process_listeners on nr_gnb if both are 0."

      disambiguators:
        - metric: amf.gnb
          separates: "gNB-side failure (gnb=0) vs. AMF-side attach-processing issue (gnb>0)"

      applicable_use_cases: [5g_core, vonr]
      tags: [ran, attachment, liveness]
```

### Example 2 — Scale-independent latency gauge with composite/feeds relationships

```yaml
icscf:
  layer: ims
  metrics:
    "cdp:average_response_time":
      display_name: "I-CSCF Diameter Average Response Time"
      source: kamcmd
      type: gauge
      unit: ms
      protocol: Diameter
      interface: Cx
      plane: control

      description: |
        Average response time across all Diameter operations the I-CSCF
        issues toward HSS (UAR + LIR), reported by Kamailio's cdp module.

      meaning:
        what_it_signals: |
          Reflects the responsiveness of the Cx path and HSS processing speed.
          A spike without timeouts = pure latency; a spike WITH rising
          timeout_ratio = approaching the request timeout ceiling.
        spike: "HSS slow, network latency to HSS, or HSS overload."
        drop: "Cannot be less than baseline — only spikes are informative."
        zero: "No Diameter responses received (HSS partitioned or down), OR pre-filter omitted this snapshot because no CDP replies arrived. Check liveness."

      healthy:
        scale_independent: true
        typical_range: [30, 100]
        invariant: null

      event_triggers:
        - id: ims.icscf.cdp_latency_elevated
          trigger: "sustained(current > 200, min_duration='60s')"
          clear_condition: "sustained(current <= 150, min_duration='60s')"
          local_meaning: |
            I-CSCF Diameter response time has risen above typical ranges
            for more than a minute. Does NOT attribute cause — could be HSS
            slow, path latency, or request-rate stress at HSS.
          magnitude_captured: [current_value, baseline_mean, delta_percent, first_observed_at]
          correlates_with:
            - event_id: ims.icscf.uar_timeouts_observed
              composite_interpretation: "HSS approaching timeout ceiling — overload or partial partition"
            - event_id: ims.scscf.mar_latency_elevated
              composite_interpretation: "HSS-wide slowness — affects both I-CSCF and S-CSCF Cx paths"

        - id: ims.icscf.cdp_latency_critical
          trigger: "sustained(current > 500, min_duration='30s') or current > 5 * baseline_mean"
          clear_condition: "sustained(current <= 200, min_duration='60s')"
          local_meaning: |
            Severe I-CSCF Diameter latency. Either HSS is heavily overloaded
            or the Cx path itself is degrading.
          magnitude_captured: [current_value, baseline_mean, delta_percent, first_observed_at]
          correlates_with:
            - event_id: ims.icscf.uar_timeouts_observed
              composite_interpretation: "Approaching full partition — timeouts coexisting with high latency"
            - event_id: infrastructure.pyhss.unreachable
              composite_interpretation: "Upstream HSS-backend failure"

      related_metrics:
        - metric: icscf.ims_icscf:uar_avg_response_time
          relationship: composite_of
          use: "cdp:average is a weighted mean of UAR + LIR response times. Inspect both when cdp spikes."
        - metric: icscf.ims_icscf:lir_avg_response_time
          relationship: composite_of
          use: "Same — check if the spike is UAR-specific, LIR-specific, or both."
        - metric: derived.icscf_uar_timeout_ratio
          relationship: discriminator_for
          use: "Latency vs. timeout — see alarm_conditions above."

      feeds_model_features:
        - icscf.cdp:average_response_time
        # direct — same key appears in the model's feature set

      how_to_verify_live:
        tool: measure_rtt
        args_hint: "measure_rtt(\"icscf\", <pyhss_ip>) to check transport-layer health to HSS. Complements the Diameter-level measurement."

      disambiguators:
        - metric: derived.icscf_uar_timeout_ratio
          separates: "overload/latency (ratio=0) vs. partial partition (ratio>0)"
        - metric: scscf.ims_auth:mar_avg_response_time
          separates: "I-CSCF↔HSS link issue (only cdp at icscf spikes) vs. HSS-wide issue (both I-CSCF and S-CSCF Diameter latencies spike)"

      applicable_use_cases: [vonr, ims_signaling]
      tags: [ims, diameter, latency, hss_facing]
```

### Example 3 — Composite/derived metric (feeds model)

Note: derived metrics live under the NF they characterize, not in a separate `derived:` grouping. Full namespace is `<layer>.<NF>.<metric_name>`; the model-feature cross-reference preserves the model's original feature key (`derived.pcscf_avg_register_time_ms`).

```yaml
pcscf:
  layer: ims
  metrics:
    avg_register_time_ms:
      display_name: "P-CSCF Average SIP REGISTER Processing Time"
      source: derived
      type: derived
      unit: ms
      protocol: SIP
      interface: Mw
      plane: control

      description: |
        Computed as rate(pcscf.script:register_time) / rate(pcscf.script:register_success)
        over the 30-second sliding window. Omitted when no new REGISTERs completed
        (pre-filter per ADR anomaly_training_zero_pollution.md).

      meaning:
        what_it_signals: |
          End-to-end cost of a successful SIP REGISTER through the IMS signaling
          chain. Dominated by the four Diameter round-trips (UAR+LIR+MAR+SAR)
          plus SIP forwarding overhead P-CSCF ↔ I-CSCF ↔ S-CSCF.
        spike: |
          Latency injected on the REGISTER path. Compare against individual
          Diameter response times: if they match the composite spike, HSS path
          is the cause; if they don't, the extra latency is on a SIP hop
          (P-CSCF↔I-CSCF or I-CSCF↔S-CSCF).
        drop: "Rarely interesting — shorter REGISTERs don't indicate faults."
        zero: "No new REGISTERs completed in window. Feature is omitted from snapshot entirely (pre-filter). Liveness tells you whether subsystem is quiet or broken."

      healthy:
        scale_independent: true
        typical_range: [150, 350]
        invariant: |
          Approximately equal to sum of the four HSS Diameter round-trips:
          uar_avg_response_time + lir_avg_response_time + mar_avg_response_time + sar_avg_response_time.
          Large positive delta between composite and sum = SIP-path latency.

      event_triggers:
        - id: ims.pcscf.register_time_elevated
          trigger: "sustained(current > 500, min_duration='60s') or current > 2 * baseline_mean"
          clear_condition: "sustained(current <= 400, min_duration='60s')"
          local_meaning: |
            SIP REGISTER processing time at P-CSCF has risen above typical.
            Does NOT attribute where on the register path. The REGISTER path
            spans P-CSCF → I-CSCF → HSS (UAR, LIR) → S-CSCF → HSS (MAR, SAR).
          magnitude_captured: [current_value, baseline_mean, delta_percent, first_observed_at]
          correlates_with:
            - event_id: ims.icscf.cdp_latency_elevated
              composite_interpretation: "HSS path dominates — delay is on Diameter legs"
            - event_id: ims.scscf.mar_latency_elevated
              composite_interpretation: "HSS path dominates — specifically S-CSCF legs"

        - id: ims.pcscf.register_time_critical
          trigger: "sustained(current > 2000, min_duration='30s')"
          clear_condition: "sustained(current <= 500, min_duration='60s')"
          local_meaning: |
            REGISTER processing time is catastrophically elevated. Either a
            huge latency injection on the P-CSCF interface or all-legs HSS
            path collapse.
          magnitude_captured: [current_value, baseline_mean, delta_percent, first_observed_at]
          correlates_with:
            - event_id: ims.pcscf.interface_loss
              composite_interpretation: "Latency is on the P-CSCF interface itself"
            - event_id: infrastructure.pyhss.unreachable
              composite_interpretation: "Backend HSS-side collapse"

      composite_of:
        - ims.pcscf.script:register_time
        - ims.pcscf.script:register_success

      feeds_model_features:
        - derived.pcscf_avg_register_time_ms

      related_metrics:
        - metric: ims.icscf.uar_avg_response_time
          relationship: composite_of
          use: "Component of REGISTER path; if register_time spikes but uar stays low, latency is NOT on the UAR leg."
        - metric: ims.scscf.mar_avg_response_time
          relationship: composite_of
          use: "Same reasoning for MAR leg."
        - metric: ims.scscf.sar_avg_response_time
          relationship: composite_of
          use: "Same reasoning for SAR leg."

      disambiguators:
        - metric: "sum(ims.icscf.uar_avg_response_time, ims.icscf.lir_avg_response_time, ims.scscf.mar_avg_response_time, ims.scscf.sar_avg_response_time)"
          separates: "HSS-side latency (sum matches register_time) vs. SIP-path latency (sum << register_time)"

      applicable_use_cases: [vonr, ims_signaling]
      tags: [ims, sip, registration, composite, diameter]
```

### Example 4 — Tiered thresholds (MOS)

```yaml
rtpengine:
  layer: ims
  metrics:
    rtpengine_mos:
      display_name: "Mean Opinion Score (recent)"
      source: prometheus
      type: derived
      unit: mos
      protocol: RTP
      interface: N6
      plane: media

      description: |
        Computed as rate(rtpengine_mos_total) / rate(rtpengine_mos_samples_total)
        over 30-second window. Reflects VoIP voice quality only during the
        recent window — NOT a cumulative lifetime average.

      meaning:
        what_it_signals: |
          Directly reflects perceived voice quality on the media plane.
          Derived from RTCP reports (packet loss, jitter, latency).
        drop: "Voice quality degradation — investigate RTP path for loss, jitter, or RTPEngine issues."
        zero: "No RTCP reports received OR no active calls. Check upstream dialog state."

      healthy:
        scale_independent: true
        typical_range: [4.0, 4.5]
        invariant: null

      state_categories:
        - name: excellent
          condition: "current >= 4.3"
          meaning: "toll quality, no perceptible degradation"
        - name: good
          condition: "current >= 4.0"
          meaning: "minor degradation, acceptable for VoIP"
        - name: acceptable
          condition: "current >= 3.5"
          meaning: "noticeable degradation, still usable"
        - name: poor
          condition: "current >= 3.0"
          meaning: "significant quality issues, user complaints likely"
        - name: unusable
          condition: "current < 3.0"
          meaning: "severe degradation, call effectively broken"

      event_triggers:
        - id: ims.rtpengine.mos_degraded
          trigger: "sustained(current < 3.5, min_duration='30s') and related('ims.rtpengine.active_sessions') > 0"
          clear_condition: "sustained(current >= 4.0, min_duration='30s')"
          local_meaning: |
            MOS has dropped into the 'poor' or 'unusable' band during an
            active call. Media-plane degradation, but the metric does not
            attribute which component on the media path is responsible.
          magnitude_captured: [current_value, baseline_mean, active_sessions_at_event, first_observed_at]
          correlates_with:
            - event_id: ims.rtpengine.errors_per_sec_nonzero
              composite_interpretation: "Active RTP relay errors — RTPEngine is likely the fault point"
            - event_id: core.upf.pps_asymmetry
              composite_interpretation: "UPF dropping packets — upstream of RTPEngine"
            - event_id: ran.nr_gnb.data_plane_degradation
              composite_interpretation: "Upstream RAN loss — affects RTP packets in transit"

        - id: ims.rtpengine.mos_unusable
          trigger: "sustained(current < 3.0, min_duration='15s') and related('ims.rtpengine.active_sessions') > 0"
          clear_condition: "sustained(current >= 3.5, min_duration='30s')"
          local_meaning: |
            MOS has collapsed into the 'unusable' band. Voice calls are
            effectively broken from a user perspective.
          magnitude_captured: [current_value, active_sessions_at_event, first_observed_at]
          correlates_with:
            - event_id: ims.rtpengine.errors_per_sec_nonzero
              composite_interpretation: "Severe RTP relay failure"

      related_metrics:
        - metric: rtpengine.errors_per_second_(total)
          relationship: correlated_with
          use: "Rising errors/sec alongside falling MOS = active RTP loss; falling MOS with errors=0 = jitter or transcoding issues."
        - metric: normalized.upf.gtp_outdatapktn3upf_per_ue
          relationship: discriminator_for
          use: "MOS drop + UPF in/out pps asymmetry at UPF = loss AT UPF, not RTPEngine."

      feeds_model_features: []   # NOT in the anomaly model — available only via get_dp_quality_gauges tool

      how_to_verify_live:
        tool: get_dp_quality_gauges
        args_hint: "Primary source. Returns rate-based MOS, loss, jitter, plus UPF in/out for cross-check."

      applicable_use_cases: [vonr]
      tags: [rtp, media_plane, voice_quality]
```

---

## Relationship to `anomaly_model_feature_set.md`

Both docs remain. Each has a distinct job:

- **Metric KB:** exhaustive catalog of raw metrics with semantics, scale invariants, and cross-references. Grows as we collect new metrics. Source of truth for agent reasoning about raw data from `get_nf_metrics`.
- **Feature set reference:** the 29 derived features the anomaly model sees, with trained statistics that update on every retrain. Source of truth for screener output interpretation.

**Cross-reference convention:**
- A KB entry with `feeds_model_features: [<feature>]` declares which model features use it.
- An `anomaly_model_feature_set.md` entry whose row references a raw metric source should link to the KB entry.
- For derived/composite model features (e.g., `derived.pcscf_avg_register_time_ms`), the KB has its own entry describing the derivation; the feature set doc describes only the model statistics.

---

## What this schema does NOT include

- **Alarms.** The KB emits events. Alarm decisions require correlating events across NFs, factoring operational context (change windows, planned subscriber-lifecycle activity, maintenance), and applying business/SLA rules. That is the responsibility of the alarm correlation engine — see [`alarm_correlation_engine.md`](alarm_correlation_engine.md).
- **Severity classifications at the metric level.** Neither the event triggers nor the state categories carry severity. Severity is a downstream judgment the correlation engine makes with full context.
- **Deployment-specific values** (IPs, ports, container names): those live in `deployment.yaml`.
- **Failure-mode descriptions** (cause → effect chains): those live in `causal_chains.yaml`. The KB links via `disambiguators` and `correlates_with.composite_interpretation`, but does not duplicate cause narratives.
- **Procedure flows** (step-by-step signaling): those live in `flows.yaml`.
- **Healthcheck procedures**: those live in `healthchecks.yaml`. The KB links via `how_to_verify_live`.
- **Historical episode data**: that's the Track 2 RAG corpus.
- **Trained-model statistics**: those live in `anomaly_model_feature_set.md` and the model pickle.

---

## Migration plan (not part of this ADR)

Once the schema is approved:

1. Create `network_ontology/data/metrics.yaml` with the schema locked.
2. Migrate entries from `baselines.yaml` in batches, one NF at a time, with review per NF.
3. Add loader support in `network_ontology/` (parallel to existing loaders).
4. Expose new ontology tools: `get_metric_semantics(metric)`, `find_disambiguators(metric, observations)`, `list_feeds_model_features(metric)`.
5. Once migration is complete and tools are live, deprecate `baselines.yaml` with a cutover date.
6. Update `anomaly_model_feature_set.md` to backreference KB entries for raw-metric sources.

---

## Resolved design decisions

All seven open questions from the initial draft were resolved on 2026-04-19.

1. **Event-trigger expression language and storage.** Adopt [`simpleeval`](https://github.com/danthedeckie/simpleeval) as the expression evaluator. Trigger strings in YAML are Python-expression syntax that parses to AST and evaluates against registered predicate functions (`prior_stable`, `dropped_by`, `sustained`, `persistence`, `rate_of_change`, `value_at_time_ago`, `no_prior_stable`, `related`). Data behind predicates comes from a three-tier storage picture: Prometheus (already running, 5-second resolution, long-window history), the preprocessor's in-memory ring buffer (already exists, short-window), and a new SQLite-backed event store (persists fired events for the correlation engine). Full picture in the "Event-trigger DSL and storage" section. The only new infrastructure is the event store. Kamailio Prometheus exporter work is a coverage follow-up.

2. **Event identifier namespace.** Namespace is `<layer>.<NF>.<event_name>` — e.g., `core.amf.ran_ue_sudden_drop`, `ims.icscf.cdp_latency_elevated`. Matches the metric-identifier convention and makes event provenance obvious in correlation logs. All examples updated.

3. **`meaning.what_it_signals` length.** General rule: 3-5 sentences. Long enough to capture nuance (when to trust the zero, when the composite differs from the sum of its parts), short enough to be read as context rather than studied. Existing examples kept as the calibration point.

4. **Relationship types are a formal enum.** Eight values: `composite_of`, `derived_from`, `normalized_from`, `correlated_with`, `discriminator_for`, `upstream_of`, `downstream_of`, `peer_of`. Schema validation rejects any other value. Extending the enum is an explicit ADR revision, not an author-time decision. Full definitions in the "Relationship types (enum)" section.

5. **Schema validation.** Pydantic (v2) as the primary loader; export JSON Schema via `model_json_schema()` for editor tooling. Loader runs at load time and surfaces type, enum, and required-field errors with line references. A post-load pass validates cross-references (`feeds_model_features`, `correlates_with.event_id`, `disambiguators.metric`). Full details in the "Schema validation" section.

6. **Derived metrics live under their owning NF.** A metric like `derived.pcscf_avg_register_time_ms` (the model feature key) lives in the KB as `ims.pcscf.avg_register_time_ms` — under the `pcscf` NF with `type: derived` and `source: derived`. No separate `derived:` pseudo-NF. The original model feature key is preserved in `feeds_model_features` for cross-reference. Example 3 reflects this.

7. **Keep both `correlates_with` and `disambiguators`.** Different consumers at different moments: `correlates_with` is for the correlation engine at event-firing time ("events A and B firing together mean X"); `disambiguators` is for the active reasoner at diagnosis time ("go check this other metric to discriminate H1 from H2"). Concrete example in the "Disambiguators — clarifying the reasoning-time role" section.

---

## Authoring rule: rich-content metrics must be `agent_exposed: true`

Added 2026-05-06 per ADR [`expose_kb_disambiguators_to_investigator.md`](expose_kb_disambiguators_to_investigator.md).

**Rule.** Any metric entry with authored `meaning` content (`what_it_signals` plus any of `zero` / `spike` / `drop` / `steady_non_zero`) OR authored `disambiguators` content MUST have `agent_exposed: true`.

**Why.** The `agent_exposed` flag exists to gate duplicates and implementation-detail metrics out of agent-facing tools, NOT to gate the KB's reasoning. A metric that an engineer took the time to author rich semantic content for is, by the very act of authoring, declared load-bearing for agent reasoning. Keeping the flag at `false` while authoring `meaning` or `disambiguators` is incoherent — it tells the renderer to surface no semantics for a metric whose semantics were specifically authored.

The original gap (audited 2026-05-06): 30 metrics across the KB carried authored `meaning` and/or `disambiguators` content while sitting at `agent_exposed: false`. The `get_diagnostic_metrics` supporting block never surfaced them; the LLM never read the disambiguators that would have prevented the RTPEngine call-quality misdiagnosis pattern documented in [`../critical-observations/why_agent_fails_with_dataplane_failure_scenarios.md`](../critical-observations/why_agent_fails_with_dataplane_failure_scenarios.md).

**Enforcement.** `agentic_ops_common/tests/test_kb_authoring_invariants.py::test_every_metric_with_authored_content_is_agent_exposed` walks the loaded KB at test time and fails CI on any violation. Adding a new metric with `meaning` or `disambiguators` but without `agent_exposed: true` is a CI-blocking error at PR time.

**When `agent_exposed: false` IS appropriate.** Bare counter entries that exist for raw-lookup tooling (Prometheus exporter aliases, deprecated raw counters retained for compatibility) and have no authored `meaning` / `disambiguators` content can stay at `false`. Such entries are not subject to this rule.
