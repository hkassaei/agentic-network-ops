"""Pure-Python evaluators for stack rules.

Each rule module exposes a top-level `evaluate(observations) -> list[dict]`
function that returns triggered-rule verdicts in the same shape
`OntologyClient.check_stack_rules` produces — but without any Neo4j
dependency. Rule prose (rule:, implication:, examples:) is read
directly from `network_ontology/data/stack_rules.yaml` so there is
exactly one source of truth.

Rationale: rule evaluation is a pure function of (observations, rule
data). Coupling it to Neo4j made the rules unreachable from
lightweight tools (e.g. `get_dp_quality_gauges`) that don't carry a
graph-database dependency. Extracting the logic lets every consumer —
the agent-facing `check_stack_rules` tool, the data-plane probe, the
network-analyst — call the same evaluator with the same shape.

ADR: `expose_kb_disambiguators_to_investigator.md` (companion pattern;
RTPEngine errors/loss),
`upf_directional_rates_in_dp_quality_gauges.md` (this module's
motivating ADR).
"""

from .upf_directional import evaluate_upf_directional_rule

__all__ = ["evaluate_upf_directional_rule"]
