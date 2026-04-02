"""
Agentic Ops v5 — 6-Phase Agent Pipeline.

Pipeline:
  Phase 1: TriageAgent (LLM)              → Collects metrics, topology, health
  Phase 2: PatternMatcherAgent (BaseAgent) → Deterministic signature matching
  Phase 3: AnomalyDetectorAgent (LLM)     → Ontology-guided anomaly analysis (optional)
  Phase 4: InstructionGeneratorAgent (LLM) → Synthesizes investigator instruction
  Phase 5: InvestigatorAgent (LLM)         → Verifies hypothesis with tools + OntologyConsultation
  Phase 6: SynthesisAgent (LLM)            → NOC-ready diagnosis
"""

__version__ = "5.1.0"
