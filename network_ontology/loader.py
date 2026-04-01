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
        return yaml.safe_load(f)


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
    """Load Component nodes from components.yaml."""
    data = _load_yaml("components.yaml")
    for name, comp in data["components"].items():
        tx.run("""
            MERGE (c:Component {name: $name})
            SET c.label = $label,
                c.layer = $layer,
                c.role = $role,
                c.ip = $ip,
                c.description = $description,
                c.protocols = $protocols
        """,
            name=name,
            label=comp["label"],
            layer=comp["layer"],
            role=comp["role"],
            ip=comp.get("ip", ""),
            description=comp.get("description", ""),
            protocols=comp.get("protocols", []),
        )

        # Create Metric nodes for components with metrics_port
        if comp.get("metrics_port"):
            tx.run("""
                MATCH (c:Component {name: $name})
                SET c.metrics_port = $port
            """, name=name, port=comp["metrics_port"])

    count = len(data["components"])
    log.info("Loaded %d components.", count)


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
    """Load CausalChain nodes and symptom relationships from causal_chains.yaml."""
    data = _load_yaml("causal_chains.yaml")
    for chain_id, chain in data["causal_chains"].items():
        # Create CausalChain node
        affected_interface = chain.get("affected_interface", "")
        if isinstance(affected_interface, list):
            affected_interface = ",".join(affected_interface)

        possible_causes = chain.get("possible_causes", [])

        tx.run("""
            MERGE (cc:CausalChain {id: $id})
            SET cc.description = $description,
                cc.affected_interface = $affected_interface,
                cc.affected_protocol = $affected_protocol,
                cc.failure_domain = $failure_domain,
                cc.severity = $severity,
                cc.possible_causes = $possible_causes
        """,
            id=chain_id,
            description=chain["description"],
            affected_interface=affected_interface,
            affected_protocol=chain.get("affected_protocol", ""),
            failure_domain=chain["failure_domain"],
            severity=chain["severity"],
            possible_causes=possible_causes,
        )

        # Create Symptom nodes from observable_symptoms.immediate
        observable = chain.get("observable_symptoms", {})
        for i, effect in enumerate(observable.get("immediate", [])):
            symptom_id = f"{chain_id}_imm_{i}"
            metric = effect.get("metric", effect.get("log", ""))
            at = effect.get("at", "")
            if isinstance(at, list):
                at = ",".join(at)

            tx.run("""
                MERGE (s:Symptom {id: $sid})
                SET s.metric = $metric,
                    s.expected_value = $becomes,
                    s.lag = $lag,
                    s.description = $description,
                    s.observed_at = $at,
                    s.type = 'immediate'
            """,
                sid=symptom_id,
                metric=str(metric),
                becomes=str(effect.get("becomes", effect.get("state", ""))),
                lag=str(effect.get("lag", "")),
                description=str(effect.get("description", "")),
                at=at,
            )

            tx.run("""
                MATCH (cc:CausalChain {id: $chain_id})
                MATCH (s:Symptom {id: $sid})
                MERGE (cc)-[:CAUSES_SYMPTOM {order: $order, type: 'immediate'}]->(s)
            """, chain_id=chain_id, sid=symptom_id, order=i)

        # Create Symptom nodes from observable_symptoms.cascading
        for i, effect in enumerate(observable.get("cascading", [])):
            symptom_id = f"{chain_id}_casc_{i}"
            tx.run("""
                MERGE (s:Symptom {id: $sid})
                SET s.condition = $condition,
                    s.description = $description,
                    s.lag = $lag,
                    s.type = 'cascading'
            """,
                sid=symptom_id,
                condition=effect.get("condition", ""),
                description=effect.get("effect", effect.get("description", "")),
                lag=str(effect.get("lag", "")),
            )

            tx.run("""
                MATCH (cc:CausalChain {id: $chain_id})
                MATCH (s:Symptom {id: $sid})
                MERGE (cc)-[:CAUSES_SYMPTOM {order: $order, type: 'cascading'}]->(s)
            """, chain_id=chain_id, sid=symptom_id, order=100 + i)

        # Store does_NOT_mean
        does_not_mean = chain.get("does_NOT_mean", [])
        if does_not_mean:
            tx.run("""
                MATCH (cc:CausalChain {id: $chain_id})
                SET cc.does_not_mean = $dnm
            """, chain_id=chain_id, dnm=does_not_mean)

        # Store diagnostic_approach
        for j, action in enumerate(chain.get("diagnostic_approach", [])):
            tx.run("""
                MATCH (cc:CausalChain {id: $chain_id})
                SET cc.diagnostic_actions = coalesce(cc.diagnostic_actions, []) + [$action]
            """, chain_id=chain_id, action=str(action))

        # Store key_diagnostic_signal
        signals = chain.get("key_diagnostic_signal", [])
        if signals:
            tx.run("""
                MATCH (cc:CausalChain {id: $chain_id})
                SET cc.key_diagnostic_signal = $signals
            """, chain_id=chain_id, signals=signals)

    count = len(data["causal_chains"])
    log.info("Loaded %d causal chains.", count)


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
        session.execute_write(load_interfaces)
        session.execute_write(load_causal_chains)
        session.execute_write(load_log_patterns)
        session.execute_write(load_signatures)
        session.execute_write(load_stack_rules)
        session.execute_write(load_healthchecks)
        session.execute_write(load_baselines)

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

    load_all(uri=args.uri, auth=(args.user, args.password), reset=args.reset)


if __name__ == "__main__":
    main()
