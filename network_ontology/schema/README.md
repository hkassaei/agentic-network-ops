# Network Ontology — Graph Schema

## Node Types

| Label | Description | Key Properties |
|-------|-------------|----------------|
| `Component` | A network function or infrastructure element | `name`, `role`, `layer`, `ip`, `container_name` |
| `Interface` | A 3GPP reference point between components | `id`, `name`, `protocol`, `transport`, `port` |
| `Protocol` | A protocol used on an interface | `name`, `layer` (L3/L4/L7), `transport` |
| `Metric` | A Prometheus metric or kamcmd stat | `name`, `source` (prometheus/kamcmd/api), `component` |
| `Symptom` | An observable effect of a failure | `id`, `description`, `metric`, `expected_value`, `observed_at` |
| `CausalChain` | A named failure scenario with cascading effects | `id`, `trigger_type`, `trigger_target`, `description` |
| `LogPattern` | A known log message with semantic annotation | `id`, `pattern`, `source`, `direction`, `meaning`, `is_benign` |
| `Signature` | A combination of symptoms identifying a fault | `id`, `diagnosis`, `confidence`, `failure_domain` |
| `StackRule` | A hard invariant about protocol layering | `id`, `rule`, `implication`, `priority` |

## Edge Types

| Relationship | From → To | Properties | Meaning |
|---|---|---|---|
| `CONNECTS_VIA` | Component → Interface | — | Component is an endpoint of this interface |
| `PEERS_WITH` | Interface → Component | `direction` (client/server/bidirectional) | The other end of the interface |
| `USES_PROTOCOL` | Interface → Protocol | — | Protocol used on this interface |
| `EXPOSES` | Component → Metric | — | Component produces this metric |
| `HEALTHY_VALUE` | Metric → — (self) | `expected`, `range_low`, `range_high`, `note` | Baseline value for this metric |
| `TRIGGERS` | CausalChain → Component | — | The component whose failure starts the chain |
| `CAUSES_SYMPTOM` | CausalChain → Symptom | `order`, `lag`, `condition` | A symptom produced by this failure |
| `OBSERVED_AT` | Symptom → Component | — | Where the symptom is visible |
| `COMMONLY_CONFUSED_WITH` | CausalChain → LogPattern | — | Log patterns that mislead investigators |
| `DOES_NOT_MEAN` | LogPattern → — (self) | `misinterpretation` | Common wrong interpretation |
| `DIAGNOSTIC_ACTION` | CausalChain → — (self) | `tool`, `args`, `description` | What to run to confirm/deny this chain |
| `MATCHES` | Signature → Symptom | — | A symptom that's part of this signature |
| `INVALIDATES` | StackRule → — (self) | `layer`, `condition` | What this rule blocks investigation of |
| `DEPENDS_ON` | Component → Component | `interface` | Component depends on another to function |

## Graph Traversal Patterns

### "gNB is down — what symptoms will I see?"
```cypher
MATCH (cc:CausalChain {trigger_target: "gnb"})
MATCH (cc)-[cs:CAUSES_SYMPTOM]->(s:Symptom)-[:OBSERVED_AT]->(c:Component)
RETURN c.name, s.description, s.metric, cs.lag
ORDER BY cs.order
```

### "I see ran_ue=0 and gnb=0 — what fault matches?"
```cypher
MATCH (sig:Signature)-[:MATCHES]->(s:Symptom)
WHERE s.metric IN ["ran_ue", "gnb"] AND s.expected_value = "0"
RETURN sig.diagnosis, sig.confidence, sig.failure_domain
```

### "AMF logged 'SCTP connection refused' — what does that mean?"
```cypher
MATCH (lp:LogPattern {source: "amf"})
WHERE lp.pattern CONTAINS "SCTP connection refused"
RETURN lp.meaning, lp.direction, lp.diagnostic_action
```

### "Is httpclient:connfail=1386 a real symptom or baseline noise?"
```cypher
MATCH (m:Metric {name: "httpclient:connfail"})
RETURN m.baseline_note, m.expected_range_low, m.expected_range_high
```
