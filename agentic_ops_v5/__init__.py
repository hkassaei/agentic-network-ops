"""
Agentic Ops v5 — Deterministic Backbone & Lean Investigation.

Replaces v4's 8-agent LLM pipeline with a 3-agent pipeline backed by
a deterministic ontology analysis step (Phase 0.5). The ontology diagnoses
the failure in Python code, then the LLM verifies the hypothesis.

Pipeline:
  Phase 0:   TriageAgent (LLM)         → Collects metrics, topology, logs
  Phase 0.5: OntologyAnalysis (Python)  → Deterministic diagnosis + short-circuit
  Phase 1:   InvestigatorAgent (LLM)    → Proves/disproves ontology hypothesis
  Phase 2:   SynthesisAgent (LLM)       → NOC-ready diagnosis
"""

__version__ = "5.0.0"
