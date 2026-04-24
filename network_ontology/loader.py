"""
Neo4j Loader — Seeds the graph database from YAML source files.

Usage:
    python -m network_ontology.loader [--uri bolt://localhost:7687] [--reset]

Idempotent: uses MERGE (not CREATE) so re-running is safe.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import yaml

log = logging.getLogger("ontology.loader")

_DATA_DIR = Path(__file__).resolve().parent / "data"
_SCHEMA_DIR = Path(__file__).resolve().parent / "schema"


def _load_yaml(name: str) -> dict:
    path = _DATA_DIR / name
    with open(path) as f:
        data = yaml.safe_load(f)
    # Schema check: warn on unknown keys. Never blocks the load — the
    # goal is to surface silent-drop bugs (YAML author added a field,
    # loader doesn't know about it) without failing a reseed for what
    # might be a harmless typo.
    try:
        from .schema import validate_yaml
        validate_yaml(name, data)
    except Exception as exc:  # pragma: no cover — defensive
        log.warning("schema validation for %s raised unexpectedly: %s", name, exc)
    return data


def load_constraints(tx):
    """Run schema constraint and index creation."""
    schema_file = _SCHEMA_DIR / "constraints.cypher"
    text = schema_file.read_text()
    for statement in text.split(";"):
        stmt = statement.strip()
        if stmt and not stmt.startswith("//"):
            tx.run(stmt)
    log.info("Schema constraints and indexes created.")


def load_components(tx):
    """Load Component nodes from components.yaml (static structure only)."""
    data = _load_yaml("components.yaml")
    for name, comp in data["components"].items():
        # Serialize use_cases as JSON string for Neo4j storage
        import json
        use_cases_json = json.dumps(comp.get("use_cases", {}))

        tx.run("""
            MERGE (c:Component {name: $name})
            SET c.label = $label,
                c.layer = $layer,
                c.role = $role,
                c.tgpp_role = $tgpp_role,
                c.subsystem = $subsystem,
                c.diagnostic = $diagnostic,
                c.description = $description,
                c.protocols = $protocols,
                c.use_cases = $use_cases
        """,
            name=name,
            label=comp["label"],
            layer=comp["layer"],
            role=comp["role"],
            tgpp_role=comp.get("tgpp_role", ""),
            subsystem=comp.get("subsystem", ""),
            diagnostic=comp.get("diagnostic", False),
            description=comp.get("description", ""),
            protocols=comp.get("protocols", []),
            use_cases=use_cases_json,
        )

    count = len(data["components"])
    log.info("Loaded %d components.", count)


def load_subsystems(tx):
    """Create Subsystem nodes and PART_OF relationships from component subsystem fields."""
    data = _load_yaml("components.yaml")

    # Collect unique subsystem names
    subsystems = set()
    for comp in data["components"].values():
        sub = comp.get("subsystem")
        if sub:
            subsystems.add(sub)

    # Create Subsystem nodes
    for name in subsystems:
        tx.run("MERGE (s:Subsystem {name: $name})", name=name)

    # Create PART_OF relationships
    for comp_name, comp in data["components"].items():
        sub = comp.get("subsystem")
        if sub:
            tx.run("""
                MATCH (c:Component {name: $comp})
                MATCH (s:Subsystem {name: $sub})
                MERGE (c)-[:PART_OF]->(s)
            """, comp=comp_name, sub=sub)

    log.info("Loaded %d subsystems with PART_OF relationships.", len(subsystems))


def load_deployment(tx):
    """Enrich Component nodes with deployment-specific data from deployment.yaml."""
    path = _DATA_DIR / "deployment.yaml"
    if not path.exists():
        log.info("No deployment.yaml found, skipping deployment enrichment.")
        return

    with open(path) as f:
        data = yaml.safe_load(f)

    count = 0
    for comp_name, deploy in data.get("deployment", {}).items():
        grid = deploy.get("grid_position", [0, 0])
        tx.run("""
            MATCH (c:Component {name: $name})
            SET c.ip_env_key = $ip_env_key,
                c.container_name = $container_name,
                c.metrics_port = $metrics_port,
                c.grid_row = $grid_row,
                c.grid_slot = $grid_slot,
                c.sublabel = $sublabel
        """,
            name=comp_name,
            ip_env_key=deploy.get("ip_env_key", ""),
            container_name=deploy.get("container_name", comp_name),
            metrics_port=deploy.get("metrics_port"),
            grid_row=grid[0] if len(grid) > 0 else 0,
            grid_slot=grid[1] if len(grid) > 1 else 0,
            sublabel=deploy.get("sublabel", ""),
        )
        count += 1

    log.info("Enriched %d components with deployment data.", count)


def load_interfaces(tx):
    """Load Interface nodes and CONNECTS_VIA/PEERS_WITH edges from interfaces.yaml."""
    data = _load_yaml("interfaces.yaml")
    for iface in data["interfaces"]:
        # Create Interface node
        tx.run("""
            MERGE (i:Interface {id: $id})
            SET i.name = $name,
                i.protocol = $protocol,
                i.transport = $transport,
                i.plane = $plane,
                i.label = $label,
                i.description = $description,
                i.logical = $logical
        """,
            id=iface["id"],
            name=iface["name"],
            protocol=iface["protocol"],
            transport=str(iface.get("transport", "")),
            plane=iface["plane"],
            label=iface["label"],
            description=iface.get("description", ""),
            logical=iface.get("logical", False),
        )

        # CONNECTS_VIA: source → interface
        tx.run("""
            MATCH (c:Component {name: $source})
            MATCH (i:Interface {id: $iface_id})
            MERGE (c)-[:CONNECTS_VIA]->(i)
        """, source=iface["source"], iface_id=iface["id"])

        # PEERS_WITH: interface → target
        tx.run("""
            MATCH (i:Interface {id: $iface_id})
            MATCH (c:Component {name: $target})
            MERGE (i)-[:PEERS_WITH]->(c)
        """, iface_id=iface["id"], target=iface["target"])

    count = len(data["interfaces"])
    log.info("Loaded %d interfaces with edges.", count)


def load_causal_chains(tx):
    """Load CausalChain nodes and symptom relationships from causal_chains.yaml.

    The cascading_symptoms structure is "branch-first": each entry is a
    named branch describing one cascading consequence path, carrying its
    own mechanism, flow source_steps, observable_metrics, and (optional)
    discriminating_from hint. Negative branches (condition/effect pairs
    that explicitly rule out a plausible-but-wrong interpretation) are
    first-class — load them with the same shape so agents can see them.
    """
    import json
    data = _load_yaml("causal_chains.yaml")
    for chain_id, chain in data["causal_chains"].items():
        # --- CausalChain node ---------------------------------------------
        affected_interface = chain.get("affected_interface", "")
        if isinstance(affected_interface, list):
            affected_interface = ",".join(affected_interface)

        affected_protocol = chain.get("affected_protocol", "")
        if isinstance(affected_protocol, list):
            affected_protocol = ",".join(affected_protocol)

        convergence = chain.get("convergence_point")
        convergence_json = json.dumps(convergence) if convergence else ""

        tx.run("""
            MERGE (cc:CausalChain {id: $id})
            SET cc.description = $description,
                cc.affected_interface = $affected_interface,
                cc.affected_protocol = $affected_protocol,
                cc.failure_domain = $failure_domain,
                cc.severity = $severity,
                cc.possible_causes = $possible_causes,
                cc.convergence_point_json = $convergence_json,
                cc.hypothesis_testing = $hypothesis_testing
        """,
            id=chain_id,
            description=chain["description"],
            affected_interface=affected_interface,
            affected_protocol=affected_protocol,
            failure_domain=chain["failure_domain"],
            severity=chain["severity"],
            possible_causes=chain.get("possible_causes", []),
            convergence_json=convergence_json,
            hypothesis_testing=chain.get("hypothesis_testing", "") or "",
        )

        # --- Immediate symptoms -------------------------------------------
        # Accepted key variants:
        #   {metric, becomes|state, at, lag, description}
        #   {symptom, source, at?, affected?, note?}
        #   {log, at}
        #   {from, to, affected}
        observable = chain.get("observable_symptoms", {}) or {}
        for i, effect in enumerate(observable.get("immediate", []) or []):
            symptom_id = f"{chain_id}_imm_{i}"
            at = effect.get("at", "")
            if isinstance(at, list):
                at = ",".join(at)
            affected = effect.get("affected", [])
            if isinstance(affected, list):
                affected = ",".join(affected)

            tx.run("""
                MERGE (s:Symptom {id: $sid})
                SET s.type = 'immediate',
                    s.metric = $metric,
                    s.log_pattern = $log_pattern,
                    s.symptom_text = $symptom_text,
                    s.expected_value = $becomes,
                    s.source_tool = $source_tool,
                    s.observed_at = $at,
                    s.affected = $affected,
                    s.from_component = $from_comp,
                    s.to_component = $to_comp,
                    s.note = $note,
                    s.lag = $lag,
                    s.description = $description
            """,
                sid=symptom_id,
                metric=str(effect.get("metric", "")),
                log_pattern=str(effect.get("log", "")),
                symptom_text=str(effect.get("symptom", "")),
                becomes=str(effect.get("becomes", effect.get("state", ""))),
                source_tool=str(effect.get("source", "")),
                at=at,
                affected=affected,
                from_comp=str(effect.get("from", "")),
                to_comp=str(effect.get("to", "")),
                note=str(effect.get("note", "")),
                lag=str(effect.get("lag", "")),
                description=str(effect.get("description", "")),
            )
            tx.run("""
                MATCH (cc:CausalChain {id: $chain_id})
                MATCH (s:Symptom {id: $sid})
                MERGE (cc)-[:CAUSES_SYMPTOM {order: $order, type: 'immediate'}]->(s)
            """, chain_id=chain_id, sid=symptom_id, order=i)

        # --- Cascading symptoms (branch-first) ----------------------------
        # New shape: {branch, condition, effect, mechanism, source_steps,
        #             observable_metrics, discriminating_from}
        # source_steps are stored as a list of "flow.step_N" string refs;
        # the explicit (Symptom)-[:DERIVES_FROM_STEP]->(FlowStep) edges
        # are wired up by `link_symptoms_to_flow_steps` after flows load.
        for i, effect in enumerate(observable.get("cascading", []) or []):
            symptom_id = f"{chain_id}_casc_{i}"
            branch_name = effect.get("branch", "") or ""
            source_steps = effect.get("source_steps", []) or []
            observable_metrics = effect.get("observable_metrics", []) or []
            # Flatten observable_metrics entries to strings (YAML authors
            # sometimes write commented or structured entries)
            observable_metrics = [str(m) for m in observable_metrics]

            tx.run("""
                MERGE (s:Symptom {id: $sid})
                SET s.type = 'cascading',
                    s.branch = $branch,
                    s.condition = $condition,
                    s.description = $description,
                    s.mechanism = $mechanism,
                    s.source_steps = $source_steps,
                    s.observable_metrics = $observable_metrics,
                    s.discriminating_from = $discriminating_from,
                    s.lag = $lag
            """,
                sid=symptom_id,
                branch=str(branch_name),
                condition=str(effect.get("condition", "")),
                description=str(effect.get("effect", effect.get("description", ""))),
                mechanism=str(effect.get("mechanism", "")),
                source_steps=[str(s) for s in source_steps],
                observable_metrics=observable_metrics,
                discriminating_from=str(effect.get("discriminating_from", "")),
                lag=str(effect.get("lag", "")),
            )
            tx.run("""
                MATCH (cc:CausalChain {id: $chain_id})
                MATCH (s:Symptom {id: $sid})
                MERGE (cc)-[:CAUSES_SYMPTOM {order: $order, type: 'cascading', branch: $branch}]->(s)
            """, chain_id=chain_id, sid=symptom_id, order=100 + i, branch=str(branch_name))

        # --- does_NOT_mean (chain-level, for chains that retain it) -------
        does_not_mean = chain.get("does_NOT_mean", [])
        if does_not_mean:
            if isinstance(does_not_mean, str):
                does_not_mean = [does_not_mean]
            tx.run("""
                MATCH (cc:CausalChain {id: $chain_id})
                SET cc.does_not_mean = $dnm
            """, chain_id=chain_id, dnm=[str(x) for x in does_not_mean])

        # --- diagnostic_approach ------------------------------------------
        # Each action is a dict {tool, args?, purpose, priority} (or the
        # ims_signaling_chain_degraded variant with {tools, step, ...}).
        # Serialize each as JSON so the structure roundtrips cleanly to
        # the agent-facing tool output.
        actions = chain.get("diagnostic_approach", []) or []
        actions_json = [json.dumps(a, default=str) for a in actions]
        if actions_json:
            tx.run("""
                MATCH (cc:CausalChain {id: $chain_id})
                SET cc.diagnostic_approach_json = $actions_json
            """, chain_id=chain_id, actions_json=actions_json)

        # --- key_diagnostic_signal ----------------------------------------
        signals = chain.get("key_diagnostic_signal", []) or []
        if signals:
            tx.run("""
                MATCH (cc:CausalChain {id: $chain_id})
                SET cc.key_diagnostic_signal = $signals
            """, chain_id=chain_id, signals=[str(s) for s in signals])

    count = len(data["causal_chains"])
    log.info("Loaded %d causal chains.", count)


def link_symptoms_to_flow_steps(tx):
    """Wire Symptom.source_steps string refs to FlowStep nodes.

    Must run after load_flows, since FlowStep nodes don't exist before
    that. The ref format is `"<flow_id>.step_<order>"` (matching the
    step node id `{flow_id}_step_{order}`). Missing refs are warned
    but not fatal — loader continues.
    """
    # Gather all symptoms that have non-empty source_steps
    result = tx.run("""
        MATCH (s:Symptom)
        WHERE s.source_steps IS NOT NULL AND size(s.source_steps) > 0
        RETURN s.id AS sid, s.source_steps AS refs
    """)
    rows = [(r["sid"], r["refs"]) for r in result]

    linked = 0
    missing = []
    for sid, refs in rows:
        for ref in refs:
            # "vonr_call_setup.step_2" → "vonr_call_setup_step_2"
            if "." not in ref:
                missing.append((sid, ref, "malformed (no dot)"))
                continue
            flow_id, step_suffix = ref.split(".", 1)
            step_node_id = f"{flow_id}_{step_suffix}"
            r = tx.run("""
                MATCH (s:Symptom {id: $sid})
                MATCH (fs:FlowStep {id: $step_id})
                MERGE (s)-[:DERIVES_FROM_STEP {ref: $ref}]->(fs)
                RETURN count(fs) AS n
            """, sid=sid, step_id=step_node_id, ref=ref)
            n = r.single()["n"]
            if n:
                linked += 1
            else:
                missing.append((sid, ref, f"no FlowStep with id {step_node_id}"))

    log.info("Linked %d Symptom→FlowStep relationships.", linked)
    if missing:
        for sid, ref, reason in missing:
            log.warning("source_steps link skipped: %s -> %s (%s)", sid, ref, reason)


def load_log_patterns(tx):
    """Load LogPattern nodes from log_patterns.yaml."""
    data = _load_yaml("log_patterns.yaml")
    for pat in data["log_patterns"]:
        source = pat.get("source", [])
        if isinstance(source, list):
            source = ",".join(source)

        does_not_mean = pat.get("does_NOT_mean", [])
        if isinstance(does_not_mean, str):
            does_not_mean = [does_not_mean]

        tx.run("""
            MERGE (lp:LogPattern {id: $id})
            SET lp.pattern = $pattern,
                lp.regex = $regex,
                lp.source = $source,
                lp.direction = $direction,
                lp.meaning = $meaning,
                lp.is_benign = $is_benign,
                lp.does_not_mean = $does_not_mean,
                lp.actual_implication = $actual_implication,
                lp.is_root_cause = $is_root_cause,
                lp.baseline_note = $baseline_note
        """,
            id=pat["id"],
            pattern=pat["pattern"],
            regex=pat.get("regex", ""),
            source=source,
            direction=pat.get("direction"),
            meaning=pat["meaning"],
            is_benign=pat.get("is_benign", False),
            does_not_mean=does_not_mean,
            actual_implication=pat.get("actual_implication", ""),
            is_root_cause=pat.get("is_root_cause"),
            baseline_note=pat.get("baseline_note", ""),
        )

        # Link to related causal chain
        related = pat.get("related_chain")
        if related:
            tx.run("""
                MATCH (lp:LogPattern {id: $lp_id})
                MATCH (cc:CausalChain {id: $cc_id})
                MERGE (lp)-[:INDICATES]->(cc)
            """, lp_id=pat["id"], cc_id=related)

    count = len(data["log_patterns"])
    log.info("Loaded %d log patterns.", count)


def load_signatures(tx):
    """Load Signature nodes from symptom_signatures.yaml."""
    data = _load_yaml("symptom_signatures.yaml")
    for sig_id, sig in data["signatures"].items():
        tx.run("""
            MERGE (sig:Signature {id: $id})
            SET sig.diagnosis = $diagnosis,
                sig.failure_domain = $failure_domain,
                sig.confidence = $confidence
        """,
            id=sig_id,
            diagnosis=sig["diagnosis"],
            failure_domain=sig["failure_domain"],
            confidence=sig["confidence"],
        )

        # Link to related causal chain
        related = sig.get("related_chain")
        if related:
            tx.run("""
                MATCH (sig:Signature {id: $sig_id})
                MATCH (cc:CausalChain {id: $cc_id})
                MERGE (sig)-[:IDENTIFIES]->(cc)
            """, sig_id=sig_id, cc_id=related)

        # Store match criteria as properties
        match_all = sig.get("match_all", [])
        match_any = sig.get("match_any", [])
        rule_out = sig.get("rule_out", [])

        tx.run("""
            MATCH (sig:Signature {id: $sig_id})
            SET sig.match_all = $match_all,
                sig.match_any = $match_any,
                sig.rule_out = $rule_out
        """,
            sig_id=sig_id,
            match_all=[str(m) for m in match_all],
            match_any=[str(m) for m in match_any],
            rule_out=[str(r) for r in rule_out],
        )

    count = len(data["signatures"])
    log.info("Loaded %d symptom signatures.", count)


def load_stack_rules(tx):
    """Load StackRule nodes from stack_rules.yaml."""
    data = _load_yaml("stack_rules.yaml")
    for rule in data["stack_rules"]:
        invalidates = rule.get("invalidates", [])
        if isinstance(invalidates, str):
            invalidates = [invalidates]

        tx.run("""
            MERGE (sr:StackRule {id: $id})
            SET sr.rule = $rule,
                sr.condition = $condition,
                sr.implication = $implication,
                sr.priority = $priority,
                sr.invalidates = $invalidates
        """,
            id=rule["id"],
            rule=rule["rule"],
            condition=rule["condition"],
            implication=rule["implication"],
            priority=rule["priority"],
            invalidates=invalidates,
        )

    count = len(data["stack_rules"])
    log.info("Loaded %d stack rules.", count)


def load_healthchecks(tx):
    """Load HealthCheck nodes and link to Components from healthchecks.yaml."""
    data = _load_yaml("healthchecks.yaml")
    for check_id, check in data["healthchecks"].items():
        # Create HealthCheck node
        tx.run("""
            MERGE (hc:HealthCheck {id: $id})
            SET hc.component = $component,
                hc.healthy_criteria = $healthy_criteria,
                hc.degraded_indicators = $degraded_indicators,
                hc.down_indicators = $down_indicators
        """,
            id=check_id,
            component=check["component"],
            healthy_criteria=check.get("healthy_criteria", []),
            degraded_indicators=check.get("degraded_indicators", []),
            down_indicators=check.get("down_indicators", []),
        )

        # Link to component
        tx.run("""
            MATCH (hc:HealthCheck {id: $hc_id})
            MATCH (c:Component {name: $comp})
            MERGE (c)-[:HAS_HEALTHCHECK]->(hc)
        """, hc_id=check_id, comp=check["component"])

        # Store probes
        for i, probe in enumerate(check.get("probes", [])):
            tx.run("""
                MATCH (hc:HealthCheck {id: $hc_id})
                SET hc.probes = coalesce(hc.probes, []) + [$probe]
            """, hc_id=check_id, probe=str(probe))

        # Store disambiguates
        for disamb in check.get("disambiguates", []):
            tx.run("""
                MATCH (hc:HealthCheck {id: $hc_id})
                SET hc.disambiguates = coalesce(hc.disambiguates, []) + [$disamb]
            """, hc_id=check_id, disamb=str(disamb))

    count = len(data["healthchecks"])
    log.info("Loaded %d health checks.", count)


def load_flows(tx):
    """Load Flow and FlowStep nodes from flows.yaml."""
    path = _DATA_DIR / "flows.yaml"
    if not path.exists():
        log.info("No flows.yaml found, skipping flow loading.")
        return

    data = _load_yaml("flows.yaml")
    import json

    for flow_id, flow in data.get("flows", {}).items():
        # Create Flow node
        tx.run("""
            MERGE (f:Flow {id: $id})
            SET f.name = $name,
                f.description = $description,
                f.use_case = $use_case,
                f.trigger = $trigger,
                f.display_order = $display_order,
                f.preconditions = $preconditions,
                f.outcome_success = $outcome_success,
                f.outcome_metrics = $outcome_metrics
        """,
            id=flow_id,
            name=flow["name"],
            description=flow.get("description", ""),
            use_case=flow.get("use_case", ""),
            trigger=flow.get("trigger", ""),
            display_order=flow.get("display_order", 99),
            preconditions=flow.get("preconditions", []),
            outcome_success=flow.get("outcome", {}).get("success", ""),
            outcome_metrics=flow.get("outcome", {}).get("observable_metrics", []),
        )

        # Create FlowStep nodes
        for step in flow.get("steps", []):
            step_id = f"{flow_id}_step_{step['order']}"
            via = step.get("via", [])
            failure_modes = step.get("failure_modes", [])
            metrics_to_watch = step.get("metrics_to_watch", [])

            tx.run("""
                MERGE (fs:FlowStep {id: $id})
                SET fs.flow_id = $flow_id,
                    fs.step_order = $order,
                    fs.from_component = $from_comp,
                    fs.to_component = $to_comp,
                    fs.via = $via,
                    fs.protocol = $protocol,
                    fs.interface = $interface,
                    fs.label = $label,
                    fs.description = $description,
                    fs.detail = $detail,
                    fs.failure_modes = $failure_modes,
                    fs.metrics_to_watch = $metrics_to_watch
            """,
                id=step_id,
                flow_id=flow_id,
                order=step["order"],
                from_comp=step["from"],
                to_comp=step["to"],
                via=via,
                protocol=step.get("protocol", ""),
                interface=step.get("interface", ""),
                label=step.get("label", ""),
                description=step.get("description", ""),
                detail=step.get("detail", ""),
                failure_modes=failure_modes,
                metrics_to_watch=metrics_to_watch,
            )

            # HAS_STEP: Flow → FlowStep
            tx.run("""
                MATCH (f:Flow {id: $flow_id})
                MATCH (fs:FlowStep {id: $step_id})
                MERGE (f)-[:HAS_STEP {order: $order}]->(fs)
            """, flow_id=flow_id, step_id=step_id, order=step["order"])

            # FROM: FlowStep → Component
            tx.run("""
                MATCH (fs:FlowStep {id: $step_id})
                MATCH (c:Component {name: $comp})
                MERGE (fs)-[:FROM]->(c)
            """, step_id=step_id, comp=step["from"])

            # TO: FlowStep → Component
            tx.run("""
                MATCH (fs:FlowStep {id: $step_id})
                MATCH (c:Component {name: $comp})
                MERGE (fs)-[:TO]->(c)
            """, step_id=step_id, comp=step["to"])

            # VIA: FlowStep → Component (intermediate hops)
            for via_comp in via:
                tx.run("""
                    MATCH (fs:FlowStep {id: $step_id})
                    MATCH (c:Component {name: $comp})
                    MERGE (fs)-[:VIA]->(c)
                """, step_id=step_id, comp=via_comp)

    flow_count = len(data.get("flows", {}))
    step_count = sum(len(f.get("steps", [])) for f in data.get("flows", {}).values())
    log.info("Loaded %d flows with %d steps.", flow_count, step_count)


def load_baselines(tx):
    """Load baseline metric values from baselines.yaml as properties on Component/Metric nodes."""
    data = _load_yaml("baselines.yaml")
    for comp_name, comp in data["baselines"].items():
        for metric_name, metric_data in comp.get("metrics", {}).items():
            # Create Metric node
            tx.run("""
                MERGE (m:Metric {name: $name})
                SET m.component = $component,
                    m.expected = $expected,
                    m.type = $type,
                    m.alarm_if = $alarm_if,
                    m.note = $note,
                    m.is_pre_existing = $is_pre_existing,
                    m.typical_range_low = $range_low,
                    m.typical_range_high = $range_high
            """,
                name=metric_name,
                component=comp_name,
                expected=str(metric_data.get("expected", "")),
                type=metric_data.get("type", "gauge"),
                alarm_if=metric_data.get("alarm_if", ""),
                note=metric_data.get("note", ""),
                is_pre_existing=metric_data.get("is_pre_existing", False),
                range_low=metric_data.get("typical_range", [None, None])[0] if isinstance(metric_data.get("typical_range"), list) else None,
                range_high=metric_data.get("typical_range", [None, None])[1] if isinstance(metric_data.get("typical_range"), list) else None,
            )

            # EXPOSES: component → metric
            tx.run("""
                MATCH (c:Component {name: $comp})
                MATCH (m:Metric {name: $metric})
                MERGE (c)-[:EXPOSES]->(m)
            """, comp=comp_name, metric=metric_name)

    log.info("Loaded baseline metrics.")


def reset_database(session):
    """Delete all nodes and relationships."""
    session.run("MATCH (n) DETACH DELETE n")
    log.info("Database reset — all nodes and relationships deleted.")


def load_all(uri: str = "bolt://localhost:7687", auth: tuple = ("neo4j", "ontology"), reset: bool = False):
    """Load all ontology data into Neo4j."""
    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(uri, auth=auth)

    with driver.session() as session:
        if reset:
            reset_database(session)

        session.execute_write(load_constraints)
        session.execute_write(load_components)
        session.execute_write(load_subsystems)
        session.execute_write(load_deployment)
        session.execute_write(load_interfaces)
        session.execute_write(load_causal_chains)
        session.execute_write(load_log_patterns)
        session.execute_write(load_signatures)
        session.execute_write(load_stack_rules)
        session.execute_write(load_healthchecks)
        # baselines.yaml was retired in Phase 4 — all 77 entries were
        # migrated into network_ontology/data/metrics.yaml (metric_kb
        # format), and `compare_to_baseline` now reads from the Python
        # MetricsKB instead of Neo4j :Metric nodes. Leaving this call
        # disabled rather than removing the function means a one-line
        # rollback is possible if any regression appears.
        # session.execute_write(load_baselines)
        session.execute_write(load_flows)
        # Must run after load_flows: needs FlowStep nodes to exist.
        session.execute_write(link_symptoms_to_flow_steps)

    driver.close()
    log.info("Ontology loading complete.")


def main():
    parser = argparse.ArgumentParser(description="Load network ontology into Neo4j")
    parser.add_argument("--uri", default="bolt://localhost:7687", help="Neo4j Bolt URI")
    parser.add_argument("--user", default="neo4j", help="Neo4j username")
    parser.add_argument("--password", default="ontology", help="Neo4j password")
    parser.add_argument("--reset", action="store_true", help="Delete all data before loading")
    parser.add_argument("-v", "--verbose", action="store_true", help="Debug logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(name)s: %(message)s",
    )
    # Suppress noisy neo4j driver logs unless verbose
    if not args.verbose:
        logging.getLogger("neo4j").setLevel(logging.ERROR)

    load_all(uri=args.uri, auth=(args.user, args.password), reset=args.reset)


if __name__ == "__main__":
    main()
