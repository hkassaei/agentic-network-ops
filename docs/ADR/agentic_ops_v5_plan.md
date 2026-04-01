# ADR: Agentic Ops v5 — Deterministic Backbone & Lean Investigation

**Date:** 2026-03-31
**Status:** Proposed
**Context:** v4 multi-agent pipeline (7-phase) identified the "Physics" of the network but suffered from LLM meta-cognitive bypass, hallucination of evidence, and token inefficiency (40k+ tokens burned on dead traces).

---

## 1. Retrospective: Why v4 Underperformed

Despite adding a Network Topology tool and a Neo4j Ontology, v4 still struggled with a 60% success rate on critical scenarios (gNB kill). The failure modes were:

1.  **The "Optional Tool" Problem**: Triage and Synthesis agents treated the `query_ontology` tool as a suggestion. When the LLM saw interesting log noise, it bypassed the deterministic ontology findings in favor of its own (often wrong) causal reasoning.
2.  **Hallucination of Evidence**: Specialists (particularly `CoreSpecialist`) reported configuration values as "Evidence" without actually calling the `read_running_config` tool. The LLM filled in the blanks with plausible-sounding but non-existent data.
3.  **Inefficient Sequencing (The "Ghost" Tracer)**: The `EndToEndTracer` ran on every failure. During a RAN outage, it burned 30k+ tokens searching for SIP records that could not logically exist, creating "missing record" noise that misled downstream specialists.
4.  **Specialist Parallelism Conflict**: Parallel specialists (IMS vs. Core vs. Transport) investigated in silos. The IMS specialist would diagnose an application-layer "timeout" for a failure that the Transport specialist already identified as 100% packet loss.

---

## 2. V5 Design Principles: The "Deterministic Backbone"

The fundamental shift in v5 is moving from **LLM-driven reasoning** to **Orchestrator-driven verification**.

### Principle 1: Deterministic Diagnosis (Phase 0.5)
The Ontology is no longer a tool the LLM *chooses* to call. It is a **deterministic step in the Python Orchestrator**. 
*   **Action**: Orchestrator calls `OntologyClient.diagnose(metrics)` immediately after Triage.
*   **Result**: The "Ontology Hypothesis" is injected into the state as an established fact before any subsequent agents run.

### Principle 2: Short-Circuit Logic
The Orchestrator uses the Ontology's `confidence` and `failure_domain` to prune the pipeline.
*   **If RAN/Transport Outage**: Skip `EndToEndTracer` and `IMSSpecialist`.
*   **If SIP Processing Error**: Skip `DataPlaneProbe` and go straight to `IMSSpecialist`.

### Principle 3: The Hierarchy of Truth
Enforce a "Waterfall" investigation: **Transport > Core > Application**. An agent cannot investigate a higher layer until the Orchestrator/Specialist confirms the lower layer is "Green."

---

## 3. Proposed v5 Architecture (Lean Pipeline)

Consolidate 7 agents into **3 high-signal agents** managed by a smart Orchestrator.

### Phase 0: Triage (`TriageAgent`)
*   **Job**: Collect metrics, topology, and recent error log samples.
*   **Output**: Raw "Network Radiograph" state.

### Phase 0.5: Deterministic Analysis (Python Orchestrator)
*   **Job**: `Ontology.diagnose(state["triage"])`.
*   **Output**: Sets `state["ontology_hypothesis"]` (e.g., "N2 Connectivity Loss", confidence "Very High").
*   **Logic**: Orchestrator prunes the next steps.

### Phase 1: Targeted Investigation (`InvestigatorAgent`)
*   **Job**: A single high-capability agent (or sequential specialists) that is given the **Ontology Hypothesis**.
*   **Mandate**: "The Ontology suspects [X]. Use your tools to PROVE or DISPROVE this. Do not speculate on other layers until [X] is ruled out."
*   **Tools**: Full access (Transport, Core, IMS).

### Phase 2: Synthesis (`SynthesisAgent`)
*   **Job**: Final fact-check. Compares Investigator's tool output vs. Ontology's causal chain.
*   **Output**: NOC-ready report with "Hierarchy of Truth" applied.

---

## 4. Implementation Roadmap

1.  **Orchestrator Refactor**: Update `agentic_ops_v4/orchestrator.py` to include the `Phase 0.5` ontology lookup and short-circuit logic.
2.  **Specialist Consolidation**: Merge specialist prompts into a unified `investigator.md` that prioritizes bottom-up verification.
3.  **Hallucination Guardrails**: Add a "Proof Requirement" to the `InvestigatorAgent`—it must cite a `tool_call_id` for every configuration or metric claim it makes.
4.  **Short-Circuiting**: Implement logic to skip `EndToEndTracer` when `ran_ue=0` and `gnb=0`.

---

## 5. Expected Outcomes
*   **Accuracy**: 90%+ on known chaos scenarios by anchoring LLMs to ontology facts.
*   **Efficiency**: 40-50% reduction in token usage by eliminating redundant tracing and parallel specialist overlap.
*   **Reliability**: Elimination of "blame attribution" errors (blaming AMF for gNB outage).

---

## 6. Analysis: RAG vs. Ontology in RCA

Traditional Vector-RAG (semantic search) was evaluated for v5 and found to be **not suitable** for core RCA logic due to the requirement for protocol precision. In telecom, "similarity" (e.g., 401 vs 407 error codes) is not "truth."

### 6.1 Why Vector-RAG is Deferred
*   **Precision Loss**: Semantic search "smooths over" exact SIP codes and headers that are critical for state machine diagnosis.
*   **Causal Hallucinations**: Retrieving "similar" past RCAs based on keywords (like "timeout") can pull the LLM toward the wrong failure domain (e.g., Database vs. Transport).
*   **Structural Blindness**: RAG does not understand the hierarchical "Physics" of the protocol stack (L1 -> L4).

### 6.2 Future Iteration: Semantic Log Matching
While full RAG is rejected, a **targeted semantic lookup** for log messages will be explored in future iterations (v5.1+) to handle log variability:
*   **Use Case**: When a developer changes a log string (e.g., "SCTP refused" -> "Failed to bind SCTP"), regex-based matching in the Ontology fails.
*   **Proposed Implementation**: Use a small embedding model to calculate similarity between an unknown log and the `meaning` fields in `log_patterns.yaml`. If similarity > 0.9, the Ontology treats it as a deterministic match.
*   **Value**: Provides the "soft" matching of RAG with the "hard" causal logic of the Ontology.
