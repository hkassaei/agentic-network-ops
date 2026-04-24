"""Pydantic schemas for every YAML file the loader consumes.

Purpose: catch silent-drop bugs. When a YAML author adds a new field
(e.g. `source_steps` on a causal-chain branch) and the loader doesn't
know about it, the loader used to ignore it and the field vanished
before reaching Neo4j. The bug stayed silent because YAML parsing
still succeeded and no explicit check flagged the drop.

With these schemas, every YAML is validated on load. Unknown keys
at any level emit a logger WARNING with a path breadcrumb
(e.g. `causal_chains.hss_unreachable.observable_symptoms.cascading[0].fooz`).
The load continues — we don't want to block a reseed on a typo — but
the warning appears in the loader output and can be grepped by CI.

The models declare every key currently used in the authored YAMLs.
Extending a model is the signal to the author that a loader change is
needed: "I added a field to the YAML; does the loader know about it?"
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, ConfigDict

log = logging.getLogger("ontology.schema")


# =============================================================================
# Base model — `extra="allow"` keeps unknown fields reachable so walking
# the validated tree can report them. Validation never raises; the loader
# continues even when warnings fire.
# =============================================================================

class _Base(BaseModel):
    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)


# =============================================================================
# components.yaml
# =============================================================================

class UseCase(_Base):
    enabled: bool | None = None
    note: str | None = None


class Component(_Base):
    label: str | None = None
    layer: str | None = None
    role: str | None = None
    tgpp_role: str | None = None
    subsystem: str | None = None
    diagnostic: bool | None = None
    description: str | None = None
    protocols: list[str] | None = None
    use_cases: dict[str, UseCase] | None = None


class ComponentsFile(_Base):
    components: dict[str, Component]


# =============================================================================
# deployment.yaml
# =============================================================================

class DeploymentEntry(_Base):
    container_name: str | None = None
    grid_position: list[int] | str | None = None
    ip_env_key: str | None = None
    sublabel: str | None = None
    metrics_port: int | str | None = None  # informational; loader does not persist it today


class DeploymentFile(_Base):
    deployment: dict[str, DeploymentEntry]


# =============================================================================
# interfaces.yaml
# =============================================================================

class Interface(_Base):
    id: str
    name: str | None = None
    label: str | None = None
    description: str | None = None
    plane: str | None = None
    protocol: str | None = None
    source: str | None = None
    target: str | None = None
    transport: str | None = None
    logical: bool | None = None  # e.g. logical links not tied to a physical transport


class InterfacesFile(_Base):
    interfaces: list[Interface]


# =============================================================================
# causal_chains.yaml
# =============================================================================

class ImmediateSymptom(_Base):
    """Entry in observable_symptoms.immediate.

    Authors use a mix of shapes — metric-first, log-first, symptom-first,
    or from/to endpoint. All known keys are declared here; unknown keys
    warn.
    """
    metric: str | None = None
    log: str | None = None
    symptom: str | None = None
    source: str | None = None
    at: str | list[str] | None = None
    becomes: Any | None = None
    state: Any | None = None
    lag: str | None = None
    description: str | None = None
    affected: str | list[str] | None = None
    from_: str | None = None
    to: str | None = None
    note: str | None = None

    model_config = ConfigDict(extra="allow", populate_by_name=True, arbitrary_types_allowed=True)


class CascadingBranch(_Base):
    """Named branch of observable_symptoms.cascading.

    `branch` is a short id. `source_steps` are `flow_id.step_N` pointers
    into flows.yaml. Negative branches (names ending `_unaffected`,
    `_unchanged`, etc.) carry the same schema — negativity is an
    authoring convention, not a schema distinction.
    """
    branch: str | None = None
    condition: str | None = None
    effect: str | None = None
    description: str | None = None
    mechanism: str | None = None
    source_steps: list[str] | None = None
    observable_metrics: list[str] | None = None
    discriminating_from: str | None = None
    lag: str | None = None


class ObservableSymptoms(_Base):
    immediate: list[ImmediateSymptom] | None = None
    cascading: list[CascadingBranch] | None = None


class DiagnosticAction(_Base):
    tool: str | None = None
    tools: list[str] | None = None  # used in ims_signaling_chain_degraded variant
    args: dict[str, Any] | None = None
    purpose: str | None = None
    priority: int | None = None
    step: str | None = None


class ConvergencePoint(_Base):
    description: str | None = None
    paths_through_upf: list[str] | None = None
    paths_NOT_through_upf: list[str] | None = None


class CausalChain(_Base):
    description: str
    affected_interface: str | list[str] | None = None
    affected_protocol: str | list[str] | None = None
    failure_domain: str
    severity: str
    possible_causes: list[str] | None = None
    observable_symptoms: ObservableSymptoms | None = None
    diagnostic_approach: list[DiagnosticAction] | None = None
    key_diagnostic_signal: list[str] | None = None
    does_NOT_mean: list[str] | str | None = None
    hypothesis_testing: str | None = None
    convergence_point: ConvergencePoint | None = None


class CausalChainsFile(_Base):
    causal_chains: dict[str, CausalChain]


# =============================================================================
# flows.yaml
# =============================================================================

class FailureModeStructured(_Base):
    """Structured failure_mode entry (future migration shape per ADR
    flow-based-causal-chain-reasoning.md). Currently unused — every
    authored failure_mode is a plain string — but the schema accepts
    both shapes so the migration doesn't require a loader change."""
    when: str | None = None
    action: str | None = None
    observable: str | dict | list | None = None


class FlowStep(_Base):
    order: int
    from_: str | None = None
    to: str | None = None
    via: list[str] | None = None
    protocol: str | None = None
    interface: str | None = None
    label: str | None = None
    description: str | None = None
    detail: str | None = None
    failure_modes: list[str | FailureModeStructured] | None = None
    metrics_to_watch: list[str] | None = None
    implementation_ref: dict[str, Any] | None = None  # reserved for ADR follow-on

    model_config = ConfigDict(extra="allow", populate_by_name=True, arbitrary_types_allowed=True)


class FlowOutcome(_Base):
    success: str | None = None
    observable_metrics: list[str] | None = None


class Flow(_Base):
    name: str
    description: str | None = None
    use_case: str | None = None
    trigger: str | None = None
    display_order: int | None = None
    preconditions: list[str] | None = None
    steps: list[FlowStep]
    outcome: FlowOutcome | None = None


class FlowsFile(_Base):
    flows: dict[str, Flow]


# =============================================================================
# healthchecks.yaml
# =============================================================================

class HealthProbe(_Base):
    name: str | None = None
    tool: str | None = None
    args: dict[str, Any] | None = None
    cost: str | int | None = None
    description: str | None = None
    healthy_if: str | list | None = None
    unhealthy_if: str | list | None = None


class Disambiguation(_Base):
    scenario: str | None = None
    question: str | None = None
    if_healthy: str | None = None
    if_unhealthy: str | None = None


class HealthCheck(_Base):
    component: str
    healthy_criteria: list[str] | None = None
    degraded_indicators: list[str] | None = None
    down_indicators: list[str] | None = None
    probes: list[HealthProbe] | None = None
    disambiguates: list[Disambiguation] | None = None


class HealthChecksFile(_Base):
    healthchecks: dict[str, HealthCheck]


# =============================================================================
# log_patterns.yaml
# =============================================================================

class LogPattern(_Base):
    id: str
    pattern: str
    regex: str | None = None
    source: str | list[str] | None = None
    direction: str | None = None
    meaning: str
    is_benign: bool | None = None
    is_root_cause: bool | None = None
    does_NOT_mean: str | list[str] | None = None
    actual_implication: str | None = None
    baseline_note: str | None = None
    related_chain: str | None = None
    # Historically authored as either a prose string or a
    # `{tool, args, description}` dict. Both shapes accepted.
    diagnostic_action: str | dict[str, Any] | None = None
    evidence: str | None = None           # short prose rationale
    follow_the_chain: str | None = None   # next-step hint for investigation


class LogPatternsFile(_Base):
    log_patterns: list[LogPattern]


# =============================================================================
# symptom_signatures.yaml
# =============================================================================

class SignatureHypothesis(_Base):
    name: str | None = None
    test: str | None = None
    tools: list[str] | None = None


class Signature(_Base):
    diagnosis: str
    failure_domain: str
    # Authored as a categorical label (`very_high`, `high`, `medium`)
    # rather than a numeric score.
    confidence: str | float | int | None = None
    match_all: list[Any] | None = None
    match_any: list[Any] | None = None
    rule_out: list[Any] | None = None
    related_chain: str | None = None
    # Extended signature (ims_signaling_chain_degraded) with named
    # sub-hypotheses each carrying a test + tool list.
    hypotheses: list[SignatureHypothesis] | None = None


class SignaturesFile(_Base):
    signatures: dict[str, Signature]


# =============================================================================
# stack_rules.yaml
# =============================================================================

class StackRule(_Base):
    id: str
    rule: str
    condition: str
    implication: str
    priority: int | str | None = None
    invalidates: str | list[str] | None = None
    examples: list[str] | None = None  # illustrative cases; loader doesn't persist them


class StackRulesFile(_Base):
    stack_rules: list[StackRule]


# =============================================================================
# baselines.yaml
# =============================================================================

class BaselineMetric(_Base):
    expected: Any | None = None
    type: str | None = None
    alarm_if: str | None = None
    note: str | None = None
    is_pre_existing: bool | None = None
    typical_range: list[Any] | None = None
    description: str | None = None
    invariant: str | None = None
    condition: str | None = None
    scale_dependent: bool | None = None
    # Authored but not persisted by the loader today. Declared here so
    # the schema matches reality; remove the comment if a future change
    # starts persisting them.
    source: str | None = None
    during_call: Any | None = None
    thresholds: dict[str, Any] | None = None
    unit: str | None = None


class BaselineComponent(_Base):
    metrics: dict[str, BaselineMetric]


class BaselinesFile(_Base):
    baselines: dict[str, BaselineComponent]


# =============================================================================
# Dispatch — map YAML filenames to root models
# =============================================================================

_MODEL_BY_FILE: dict[str, type[_Base]] = {
    # baselines.yaml was retired in Phase 4 — its content is now in
    # metrics.yaml (metric_kb format). Not loaded by the ontology
    # loader anymore, so it is not registered here. The file itself
    # is kept on disk for one regression window so the user can
    # verify nothing broke before deleting it.
    "causal_chains.yaml": CausalChainsFile,
    "components.yaml": ComponentsFile,
    "deployment.yaml": DeploymentFile,
    "flows.yaml": FlowsFile,
    "healthchecks.yaml": HealthChecksFile,
    "interfaces.yaml": InterfacesFile,
    "log_patterns.yaml": LogPatternsFile,
    "stack_rules.yaml": StackRulesFile,
    "symptom_signatures.yaml": SignaturesFile,
}


# =============================================================================
# Unknown-key walker
# =============================================================================

def _walk_unknown_keys(node: Any, path: str, warnings: list[str]) -> None:
    """Recursively walk a pydantic-validated structure and collect
    unknown-key warnings (populated by pydantic's extra='allow').

    For BaseModel instances, `model_extra` contains fields not declared
    in the model — those are the unknowns we want to report. We then
    recurse into every field (declared or extra) to reach nested
    models and the dicts/lists within them.
    """
    if isinstance(node, BaseModel):
        extras = node.model_extra or {}
        declared = type(node).model_fields
        for extra_key in extras:
            # Pydantic exposes Python field aliases (e.g. `from_`) in the
            # declared fields; the raw YAML key (`from`) stays in extras.
            # Suppress those aliases — they are not unknowns, just alias
            # artifacts.
            if extra_key == "from" and "from_" in declared:
                continue
            warnings.append(f"{path}.{extra_key}")
        for field_name, field_info in declared.items():
            # Resolve the YAML key back from the python attribute name
            yaml_key = field_info.alias or field_name.rstrip("_")
            value = getattr(node, field_name)
            _walk_unknown_keys(value, f"{path}.{yaml_key}", warnings)
        # Also recurse into extras so nested unknowns (rare but possible)
        # are reached.
        for extra_key, extra_val in extras.items():
            _walk_unknown_keys(extra_val, f"{path}.{extra_key}", warnings)
    elif isinstance(node, dict):
        for k, v in node.items():
            _walk_unknown_keys(v, f"{path}.{k}", warnings)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            _walk_unknown_keys(v, f"{path}[{i}]", warnings)
    # Scalars: nothing to walk.


def validate_yaml(filename: str, data: Any) -> None:
    """Validate a YAML file's parsed contents against its declared
    schema and log WARNING lines for every unknown key.

    Never raises. If the top-level structure doesn't match (e.g. the
    YAML is empty or the root key is misspelled), emit one warning and
    return — the loader will either cope or fail loudly downstream,
    depending on the specific load_* function.

    Args:
        filename: YAML file basename (e.g. `"causal_chains.yaml"`).
                  Used to look up the model and as the warning root path.
        data: The parsed YAML contents (result of `yaml.safe_load`).
    """
    model_cls = _MODEL_BY_FILE.get(filename)
    if model_cls is None:
        log.debug("schema: no model registered for %s", filename)
        return
    if not isinstance(data, dict):
        log.warning("schema: %s: expected a mapping at the root, got %s",
                    filename, type(data).__name__)
        return

    try:
        validated = model_cls.model_validate(data)
    except Exception as exc:  # pydantic ValidationError or similar
        # Structural mismatches (required field missing, wrong type) are
        # loud — downstream loader code will fail anyway, but we want the
        # reason surfaced before that explosion.
        log.warning("schema: %s failed strict validation: %s", filename, exc)
        return

    warnings: list[str] = []
    _walk_unknown_keys(validated, filename.removesuffix(".yaml"), warnings)

    if warnings:
        log.warning(
            "schema: %s has %d unknown key(s) — loader will silently drop them "
            "unless you update network_ontology/schema.py AND the loader:",
            filename, len(warnings),
        )
        for w in warnings:
            log.warning("  unknown key: %s", w)
    else:
        log.info("schema: %s validated (no unknown keys).", filename)
