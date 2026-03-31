// ============================================================================
// Network Ontology — Neo4j Schema Constraints & Indexes
// ============================================================================
// Run once after creating the database.
// These ensure data integrity and query performance.

// ---------------------------------------------------------------------------
// Node uniqueness constraints (also create indexes automatically)
// ---------------------------------------------------------------------------

// Components: NFs, infrastructure, external endpoints
CREATE CONSTRAINT component_name IF NOT EXISTS
  FOR (c:Component) REQUIRE c.name IS UNIQUE;

// Interfaces: 3GPP reference points (N2, N4, Gm, Cx, etc.)
CREATE CONSTRAINT interface_id IF NOT EXISTS
  FOR (i:Interface) REQUIRE i.id IS UNIQUE;

// Metrics: Prometheus metric names and kamcmd stat keys
CREATE CONSTRAINT metric_name IF NOT EXISTS
  FOR (m:Metric) REQUIRE m.name IS UNIQUE;

// Log patterns: known log messages with semantic annotations
CREATE CONSTRAINT log_pattern_id IF NOT EXISTS
  FOR (lp:LogPattern) REQUIRE lp.id IS UNIQUE;

// Causal chains: named failure scenarios
CREATE CONSTRAINT causal_chain_id IF NOT EXISTS
  FOR (cc:CausalChain) REQUIRE cc.id IS UNIQUE;

// Symptoms: observable effects of failures
CREATE CONSTRAINT symptom_id IF NOT EXISTS
  FOR (s:Symptom) REQUIRE s.id IS UNIQUE;

// Symptom signatures: combinations of symptoms that identify a fault
CREATE CONSTRAINT signature_id IF NOT EXISTS
  FOR (sig:Signature) REQUIRE sig.id IS UNIQUE;

// Stack rules: hard invariants about protocol layering
CREATE CONSTRAINT stack_rule_id IF NOT EXISTS
  FOR (sr:StackRule) REQUIRE sr.id IS UNIQUE;

// Health checks: per-component diagnostic definitions
CREATE CONSTRAINT healthcheck_id IF NOT EXISTS
  FOR (hc:HealthCheck) REQUIRE hc.id IS UNIQUE;

// Protocols
CREATE CONSTRAINT protocol_name IF NOT EXISTS
  FOR (p:Protocol) REQUIRE p.name IS UNIQUE;

// ---------------------------------------------------------------------------
// Additional indexes for common query patterns
// ---------------------------------------------------------------------------

CREATE INDEX component_layer IF NOT EXISTS
  FOR (c:Component) ON (c.layer);

CREATE INDEX symptom_metric IF NOT EXISTS
  FOR (s:Symptom) ON (s.metric);

CREATE INDEX log_pattern_source IF NOT EXISTS
  FOR (lp:LogPattern) ON (lp.source);

CREATE INDEX causal_chain_trigger IF NOT EXISTS
  FOR (cc:CausalChain) ON (cc.trigger_type);
