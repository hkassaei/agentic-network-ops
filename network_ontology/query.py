"""
Network Ontology Query API — Python interface for agent tools.

Provides high-level functions that translate agent observations into
ontology queries and return structured, actionable results.

Usage:
    from network_ontology.query import OntologyClient

    client = OntologyClient()
    result = client.match_symptoms({"ran_ue": 0, "gnb": 0})
    chain = client.get_causal_chain("gnb_down")
    meaning = client.interpret_log("SCTP connection refused", source="amf")
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

log = logging.getLogger("ontology.query")


class OntologyClient:
    """Query interface to the network ontology graph database."""

    def __init__(
        self,
        uri: str | None = None,
        auth: tuple[str, str] | None = None,
    ):
        from neo4j import GraphDatabase

        self._uri = uri or os.environ.get("NEO4J_URI", "bolt://localhost:7687")
        self._auth = auth or (
            os.environ.get("NEO4J_USER", "neo4j"),
            os.environ.get("NEO4J_PASSWORD", "ontology"),
        )
        self._driver = GraphDatabase.driver(self._uri, auth=self._auth)

    def close(self):
        self._driver.close()

    # -----------------------------------------------------------------
    # Causal Chain Queries
    # -----------------------------------------------------------------

    def get_causal_chain(self, chain_id: str) -> dict[str, Any] | None:
        """Get a complete causal chain by ID.

        Returns the chain with its immediate effects, cascading effects,
        symptoms at each node, does_NOT_mean warnings, and diagnostic actions.
        """
        with self._driver.session() as session:
            result = session.run("""
                MATCH (cc:CausalChain {id: $id})
                OPTIONAL MATCH (cc)-[cs:CAUSES_SYMPTOM]->(s:Symptom)
                RETURN cc, collect({symptom: s, order: cs.order, type: cs.type}) AS symptoms
            """, id=chain_id)

            record = result.single()
            if not record:
                return None

            cc = dict(record["cc"])
            symptoms = [
                {**dict(s["symptom"]), "order": s["order"], "type": s["type"]}
                for s in record["symptoms"]
                if s["symptom"] is not None
            ]
            symptoms.sort(key=lambda x: x.get("order", 999))

            return {
                **cc,
                "symptoms": symptoms,
            }

    def get_causal_chain_for_component(self, component: str) -> list[dict]:
        """Get all causal chains triggered by a specific component failure."""
        with self._driver.session() as session:
            result = session.run("""
                MATCH (cc:CausalChain)-[:TRIGGERS]->(c:Component {name: $name})
                OPTIONAL MATCH (cc)-[cs:CAUSES_SYMPTOM]->(s:Symptom)
                RETURN cc, collect({symptom: s, order: cs.order}) AS symptoms
                ORDER BY cc.severity DESC
            """, name=component)

            chains = []
            for record in result:
                cc = dict(record["cc"])
                symptoms = [
                    {**dict(s["symptom"]), "order": s["order"]}
                    for s in record["symptoms"]
                    if s["symptom"] is not None
                ]
                symptoms.sort(key=lambda x: x.get("order", 999))
                chains.append({**cc, "symptoms": symptoms})

            return chains

    # -----------------------------------------------------------------
    # Symptom Matching
    # -----------------------------------------------------------------

    def match_symptoms(self, observations: dict[str, Any]) -> list[dict]:
        """Match observed metrics/symptoms against known signatures.

        Args:
            observations: Dict of metric_name → value, plus optional keys:
                - container_status: {name: "exited"|"running"}
                - log_patterns_seen: [pattern_id, ...]

        Returns:
            Ranked list of matching signatures with diagnosis, confidence,
            and recommended diagnostic actions.
        """
        with self._driver.session() as session:
            # Get all signatures
            result = session.run("""
                MATCH (sig:Signature)
                OPTIONAL MATCH (sig)-[:IDENTIFIES]->(cc:CausalChain)
                RETURN sig, cc
            """)

            signatures = []
            for record in result:
                sig = dict(record["sig"])
                chain = dict(record["cc"]) if record["cc"] else None
                sig["causal_chain"] = chain
                signatures.append(sig)

        # Score each signature against observations
        scored = []
        for sig in signatures:
            score = self._score_signature(sig, observations)
            if score > 0:
                scored.append({
                    "signature_id": sig["id"],
                    "diagnosis": sig["diagnosis"],
                    "failure_domain": sig["failure_domain"],
                    "confidence": sig["confidence"],
                    "match_score": score,
                    "rule_out": sig.get("rule_out", []),
                    "causal_chain": sig.get("causal_chain"),
                })

        scored.sort(key=lambda x: (-x["match_score"], x["confidence"]))
        return scored

    def _score_signature(self, sig: dict, observations: dict) -> float:
        """Score how well observations match a signature. Returns 0.0-1.0."""
        score = 0.0
        total_criteria = 0

        # Check match_all criteria (stored as string representations)
        match_all = sig.get("match_all", [])
        if match_all:
            for criterion_str in match_all:
                total_criteria += 1
                if self._check_criterion(criterion_str, observations):
                    score += 1.0

            # All match_all criteria must pass
            if total_criteria > 0 and score < total_criteria:
                return 0.0

        # Check match_any criteria (bonus points)
        match_any = sig.get("match_any", [])
        any_matched = False
        for criterion_str in match_any:
            if self._check_criterion(criterion_str, observations):
                any_matched = True
                score += 0.5

        # If we had match_all criteria that all passed, return normalized score
        if total_criteria > 0:
            return min(score / max(total_criteria, 1), 1.0)

        # If only match_any, need at least one match
        if any_matched:
            return 0.5

        return 0.0

    def _check_criterion(self, criterion_str: str, observations: dict) -> bool:
        """Check a single criterion against observations.

        Criterion is stored as a string repr of a dict, e.g.:
        "{'metric': 'ran_ue', 'condition': '= 0'}"
        """
        try:
            import ast
            criterion = ast.literal_eval(criterion_str)
        except (ValueError, SyntaxError):
            return False

        if not isinstance(criterion, dict):
            return False

        # Metric-based check
        metric = criterion.get("metric")
        if metric and metric in observations:
            condition = criterion.get("condition", "")
            value = observations[metric]
            try:
                if condition.startswith("= "):
                    return float(value) == float(condition[2:])
                elif condition.startswith("> "):
                    return float(value) > float(condition[2:])
                elif condition.startswith("< "):
                    return float(value) < float(condition[2:])
                elif condition == "> 0":
                    return float(value) > 0
                elif condition == "= 0":
                    return float(value) == 0
            except (ValueError, TypeError):
                pass

        # Container status check
        container_status = criterion.get("container_status")
        if container_status and "container_status" in observations:
            obs_status = observations["container_status"]
            for name, expected in container_status.items():
                if obs_status.get(name) == expected:
                    return True

        # Log pattern check
        log_pattern = criterion.get("log_pattern")
        if log_pattern and "log_patterns_seen" in observations:
            return log_pattern in observations["log_patterns_seen"]

        return False

    # -----------------------------------------------------------------
    # Log Interpretation
    # -----------------------------------------------------------------

    def interpret_log(self, message: str, source: str | None = None) -> list[dict]:
        """Look up the semantic meaning of a log message.

        Returns matching log patterns with meaning, common misinterpretations,
        and diagnostic actions.
        """
        with self._driver.session() as session:
            if source:
                result = session.run("""
                    MATCH (lp:LogPattern)
                    WHERE lp.source CONTAINS $source
                    RETURN lp
                """, source=source)
            else:
                result = session.run("MATCH (lp:LogPattern) RETURN lp")

            patterns = [dict(record["lp"]) for record in result]

        # Filter by regex match
        import re
        matches = []
        for pat in patterns:
            regex = pat.get("regex", "")
            if regex:
                try:
                    if re.search(regex, message, re.IGNORECASE):
                        matches.append(pat)
                except re.error:
                    pass
            elif pat.get("pattern", "") in message:
                matches.append(pat)

        return matches

    # -----------------------------------------------------------------
    # Stack Rules
    # -----------------------------------------------------------------

    def get_stack_rules(self) -> list[dict]:
        """Get all stack rules ordered by priority."""
        with self._driver.session() as session:
            result = session.run("""
                MATCH (sr:StackRule)
                RETURN sr
                ORDER BY sr.priority ASC
            """)
            return [dict(record["sr"]) for record in result]

    def check_stack_rules(self, observations: dict) -> list[dict]:
        """Check which stack rules are triggered by current observations.

        Returns triggered rules in priority order. A triggered rule means
        the agent should stop certain investigation paths.
        """
        rules = self.get_stack_rules()
        triggered = []

        for rule in rules:
            rule_id = rule.get("id", "")

            # Check specific conditions
            if rule_id == "network_fault_is_root_cause":
                if observations.get("network_fault_confirmed"):
                    triggered.append(rule)

            elif rule_id == "unreachable_component_is_root_cause":
                unreachable = observations.get("unreachable_components", [])
                if unreachable:
                    triggered.append({**rule, "affected_components": unreachable})

            elif rule_id == "ran_down_invalidates_ims":
                if (observations.get("ran_ue") == 0
                        and observations.get("gnb") == 0):
                    triggered.append(rule)

            elif rule_id == "data_plane_dead_invalidates_sip":
                gtp_in = observations.get("fivegs_ep_n3_gtp_indatapktn3upf")
                gtp_out = observations.get("fivegs_ep_n3_gtp_outdatapktn3upf")
                sessions = observations.get("fivegs_upffunction_upf_sessionnbr", 0)
                if gtp_in == 0 and gtp_out == 0 and sessions > 0:
                    triggered.append(rule)

            elif rule_id == "upf_counters_are_directional":
                # Fires whenever both UPF directional counters are in
                # observations. Purpose: proactive education — tell the
                # agent these counters are independent directions and
                # can NEVER be subtracted to compute loss. Always-on
                # guidance, but attaches an asymmetry_pct so the agent
                # can see the magnitude of the (harmless) asymmetry.
                in_total = observations.get("fivegs_ep_n3_gtp_indatapktn3upf")
                out_total = observations.get("fivegs_ep_n3_gtp_outdatapktn3upf")

                if (in_total is not None and out_total is not None
                        and isinstance(in_total, (int, float))
                        and isinstance(out_total, (int, float))):

                    max_val = max(abs(in_total), abs(out_total))
                    if max_val > 0:
                        asymmetry_pct = round(
                            abs(in_total - out_total) / max_val * 100, 1
                        )
                    else:
                        asymmetry_pct = 0.0

                    # Severity escalates with asymmetry — above 30% the
                    # agent is most tempted to misread it as loss.
                    if asymmetry_pct >= 30:
                        severity = "high_temptation"
                        verdict = (
                            f"Asymmetry is {asymmetry_pct}% — HIGH temptation "
                            f"to misinterpret as packet loss. It is NOT. This "
                            f"asymmetry is structural (determined by historical "
                            f"traffic mix over the container's lifetime). DO NOT "
                            f"report the difference as loss. Use one of the "
                            f"correct_methods below for actual loss detection."
                        )
                    else:
                        severity = "informational"
                        verdict = (
                            f"Asymmetry is {asymmetry_pct}% — counters are "
                            f"roughly consistent. Regardless, these counters "
                            f"cannot be subtracted to compute loss under any "
                            f"circumstance. See correct_methods for actual "
                            f"loss detection."
                        )

                    correct_methods = [
                        "Same-direction rate comparison: "
                        "rate(fivegs_ep_n3_gtp_indatapktn3upf[2m]) vs expected "
                        "rate for current traffic (G.711 call = ~50 pps per direction)",
                        "RTCP-based voice quality: "
                        "rate(rtpengine_packetloss_total[2m]) / "
                        "rate(rtpengine_packetloss_samples_total[2m]) = "
                        "sampled loss fraction from RTCP reports",
                        "Interface drop counters on tc qdisc "
                        "(not currently exposed as a tool)",
                    ]

                    triggered.append({
                        **rule,
                        "in_total": in_total,
                        "out_total": out_total,
                        "asymmetry_pct": asymmetry_pct,
                        "severity": severity,
                        "verdict": verdict,
                        "correct_methods": correct_methods,
                    })

            elif rule_id == "idle_data_plane_is_normal":
                # Fires when any data plane throughput rate is present
                # in observations AND is near zero. The rule tells the
                # agent to cross-check call activity before flagging
                # zero throughput as a failure.
                #
                # Only checks rate/gauge metrics — NOT cumulative
                # counters like gtp_indatapktn3upf (which are always
                # non-zero on a warm stack and cannot detect idleness).
                rate_keys = [
                    "upf_kbps",        # from get_dp_quality_gauges
                    "rtpengine_pps",   # from get_dp_quality_gauges
                    "upf_in_pps",      # from get_dp_quality_gauges
                    "upf_out_pps",     # from get_dp_quality_gauges
                ]
                near_zero_rates = []
                for key in rate_keys:
                    val = observations.get(key)
                    if val is not None and isinstance(val, (int, float)) and val <= 0.5:
                        near_zero_rates.append(key)

                if near_zero_rates:
                    # Cross-check: is there any active call indicator?
                    activity_keys = [
                        "dialog_ng:active",      # Kamailio CSCFs
                        "owned_sessions",        # RTPEngine
                        "total_sessions",        # RTPEngine (gauge)
                        "rtpengine_active_sessions",  # data plane gauges
                    ]
                    any_activity = any(
                        (observations.get(k) or 0) > 0 for k in activity_keys
                    )
                    triggered.append({
                        **rule,
                        "near_zero_rates": near_zero_rates,
                        "active_call_detected": any_activity,
                        "verdict": (
                            "Active call detected — zero rates may be a real problem."
                            if any_activity
                            else "No active call — zero data plane rates are EXPECTED idle state. DO NOT flag as degraded."
                        ),
                    })

            elif rule_id == "baseline_delta_rule":
                # This rule is advisory — always include it as context
                triggered.append(rule)

        return triggered

    # -----------------------------------------------------------------
    # Baseline Queries
    # -----------------------------------------------------------------

    def get_baseline(self, component: str) -> dict[str, dict]:
        """Get expected baseline metrics for a component."""
        with self._driver.session() as session:
            result = session.run("""
                MATCH (c:Component {name: $name})-[:EXPOSES]->(m:Metric)
                RETURN m
            """, name=component)
            return {
                record["m"]["name"]: dict(record["m"])
                for record in result
            }

    def compare_to_baseline(
        self, component: str, current_metrics: dict[str, float]
    ) -> list[dict]:
        """Compare current metrics to baseline. Returns only anomalies."""
        baseline = self.get_baseline(component)
        anomalies = []

        for metric_name, current_value in current_metrics.items():
            if metric_name not in baseline:
                continue

            bl = baseline[metric_name]

            # Skip pre-existing known issues
            if bl.get("is_pre_existing"):
                range_low = bl.get("typical_range_low")
                range_high = bl.get("typical_range_high")
                if range_low is not None and range_high is not None:
                    if range_low <= current_value <= range_high:
                        continue  # Within known noisy range

            # Check against expected value
            expected = bl.get("expected")
            if expected and expected.isdigit():
                expected_val = float(expected)
                if current_value != expected_val:
                    anomalies.append({
                        "metric": metric_name,
                        "expected": expected_val,
                        "actual": current_value,
                        "alarm_if": bl.get("alarm_if", ""),
                        "note": bl.get("note", ""),
                    })

        return anomalies

    # -----------------------------------------------------------------
    # Health Checks
    # -----------------------------------------------------------------

    def get_healthcheck(self, component: str) -> dict | None:
        """Get the health check definition for a component.

        Returns probes (ordered cheapest-first), healthy/degraded/down
        criteria, and disambiguation scenarios.
        """
        with self._driver.session() as session:
            result = session.run("""
                MATCH (c:Component {name: $name})-[:HAS_HEALTHCHECK]->(hc:HealthCheck)
                RETURN hc
            """, name=component)
            record = result.single()
            if not record:
                return None
            return dict(record["hc"])

    def get_disambiguation(self, component: str, scenario: str) -> dict | None:
        """Look up what a health check result means for a specific ambiguous scenario.

        Args:
            component: The component to health-check
            scenario: Description of the ambiguous situation (e.g., "ran_ue = 0")

        Returns:
            Dict with if_healthy and if_unhealthy interpretations, or None.
        """
        import ast
        hc = self.get_healthcheck(component)
        if not hc:
            return None

        disambiguates = hc.get("disambiguates", [])
        for d_str in disambiguates:
            try:
                d = ast.literal_eval(d_str)
                if isinstance(d, dict) and scenario.lower() in d.get("scenario", "").lower():
                    return d
            except (ValueError, SyntaxError):
                continue
        return None

    # -----------------------------------------------------------------
    # Component Topology
    # -----------------------------------------------------------------

    # -----------------------------------------------------------------
    # Topology Queries (for GUI and agent tools)
    # -----------------------------------------------------------------

    def get_all_components(self) -> list[dict]:
        """Return all components with their static + deployment properties."""
        with self._driver.session() as session:
            result = session.run("""
                MATCH (c:Component)
                OPTIONAL MATCH (c)-[:PART_OF]->(s:Subsystem)
                RETURN c, s.name AS subsystem_name
            """)
            return [
                {**dict(record["c"]), "subsystem_name": record["subsystem_name"]}
                for record in result
            ]

    def get_vonr_components(self) -> list[dict]:
        """Return only the components relevant to VoNR evaluation.

        Filters out components where `use_cases.vonr.enabled: false` in
        the ontology (WebUI, Prometheus, Grafana, etc.). The result is
        the list of containers whose health an RCA agent should actually
        consider when assessing network state.

        Each entry includes: name, label, layer, role, container_name,
        subsystem, and the ontology note explaining its role.
        """
        components = self.get_all_components()
        relevant: list[dict] = []
        for comp in components:
            use_cases_raw = comp.get("use_cases", "{}")
            try:
                use_cases = (
                    json.loads(use_cases_raw)
                    if isinstance(use_cases_raw, str)
                    else use_cases_raw or {}
                )
            except (json.JSONDecodeError, TypeError):
                use_cases = {}

            vonr = use_cases.get("vonr", {})
            if not isinstance(vonr, dict):
                continue
            if not vonr.get("enabled", False):
                continue

            relevant.append({
                "name": comp.get("name", ""),
                "label": comp.get("label", ""),
                "layer": comp.get("layer", ""),
                "role": comp.get("role", ""),
                "container_name": comp.get("container_name", comp.get("name", "")),
                "subsystem": comp.get("subsystem", ""),
                "note": vonr.get("note", ""),
            })
        return relevant

    def get_all_interfaces(self) -> list[dict]:
        """Return all interfaces with source and target component names."""
        with self._driver.session() as session:
            result = session.run("""
                MATCH (src:Component)-[:CONNECTS_VIA]->(i:Interface)-[:PEERS_WITH]->(tgt:Component)
                RETURN i, src.name AS source, tgt.name AS target
            """)
            return [
                {**dict(record["i"]), "source": record["source"], "target": record["target"]}
                for record in result
            ]

    def get_topology_data(self) -> dict:
        """Return complete topology structure for GUI consumption.

        Returns:
            {"components": [...], "interfaces": [...], "subsystems": [...]}
        """
        components = self.get_all_components()
        interfaces = self.get_all_interfaces()

        with self._driver.session() as session:
            result = session.run("MATCH (s:Subsystem) RETURN s")
            subsystems = [dict(record["s"]) for record in result]

        return {
            "components": components,
            "interfaces": interfaces,
            "subsystems": subsystems,
        }

    # -----------------------------------------------------------------
    # Flow Queries
    # -----------------------------------------------------------------

    def get_all_flows(self) -> list[dict]:
        """Return all flow definitions (id, name, use_case, step count)."""
        with self._driver.session() as session:
            result = session.run("""
                MATCH (f:Flow)
                OPTIONAL MATCH (f)-[:HAS_STEP]->(fs:FlowStep)
                RETURN f, count(fs) AS step_count
                ORDER BY f.name
            """)
            return [
                {**dict(record["f"]), "step_count": record["step_count"]}
                for record in result
            ]

    def get_flow(self, flow_id: str) -> dict | None:
        """Return a complete flow with all steps ordered by step_order."""
        with self._driver.session() as session:
            # Get the flow node
            flow_result = session.run(
                "MATCH (f:Flow {id: $id}) RETURN f", id=flow_id
            )
            flow_record = flow_result.single()
            if not flow_record:
                return None
            flow = dict(flow_record["f"])

            # Get all steps ordered
            steps_result = session.run("""
                MATCH (f:Flow {id: $id})-[hs:HAS_STEP]->(fs:FlowStep)
                RETURN fs
                ORDER BY fs.step_order
            """, id=flow_id)

            flow["steps"] = [dict(record["fs"]) for record in steps_result]
            return flow

    def get_flows_through_component(self, component: str) -> list[dict]:
        """Return all flows that pass through a given component (as FROM, TO, or VIA)."""
        with self._driver.session() as session:
            result = session.run("""
                MATCH (c:Component {name: $name})
                MATCH (fs:FlowStep)-[:FROM|TO|VIA]->(c)
                MATCH (f:Flow)-[:HAS_STEP]->(fs)
                RETURN DISTINCT f.id AS flow_id, f.name AS flow_name,
                       fs.step_order AS step_order, fs.label AS step_label
                ORDER BY f.name, fs.step_order
            """, name=component)
            return [dict(record) for record in result]

    def get_component(self, name: str) -> dict | None:
        """Get a component with its interfaces and connected peers."""
        with self._driver.session() as session:
            result = session.run("""
                MATCH (c:Component {name: $name})
                OPTIONAL MATCH (c)-[:CONNECTS_VIA]->(i:Interface)-[:PEERS_WITH]->(peer:Component)
                RETURN c, collect({interface: i, peer: peer}) AS connections
            """, name=name)

            record = result.single()
            if not record:
                return None

            comp = dict(record["c"])
            connections = [
                {
                    "interface": dict(conn["interface"]),
                    "peer": dict(conn["peer"]),
                }
                for conn in record["connections"]
                if conn["interface"] is not None
            ]
            comp["connections"] = connections
            return comp

    def get_downstream_impact(self, component: str) -> dict:
        """Get all components affected if this component goes down."""
        with self._driver.session() as session:
            # Direct connections
            result = session.run("""
                MATCH (c:Component {name: $name})
                MATCH (c)-[:CONNECTS_VIA]->(i:Interface)-[:PEERS_WITH]->(peer:Component)
                RETURN i, peer
            """, name=component)

            affected = []
            for record in result:
                affected.append({
                    "component": dict(record["peer"])["name"],
                    "interface": dict(record["i"])["name"],
                    "protocol": dict(record["i"])["protocol"],
                })

            # Also check interfaces where this component is the target
            result2 = session.run("""
                MATCH (peer:Component)-[:CONNECTS_VIA]->(i:Interface)-[:PEERS_WITH]->(c:Component {name: $name})
                RETURN i, peer
            """, name=component)

            for record in result2:
                affected.append({
                    "component": dict(record["peer"])["name"],
                    "interface": dict(record["i"])["name"],
                    "protocol": dict(record["i"])["protocol"],
                })

            return {
                "component": component,
                "affected": affected,
            }

    # -----------------------------------------------------------------
    # Full Diagnostic Query (main agent entry point)
    # -----------------------------------------------------------------

    def diagnose(self, observations: dict[str, Any]) -> dict[str, Any]:
        """Main entry point for agent diagnosis.

        Takes a full observation dict (metrics, container status, log patterns)
        and returns:
        - Matched symptom signatures (ranked)
        - Triggered stack rules
        - Baseline anomalies
        - Recommended diagnostic actions

        This is what the query_ontology agent tool calls.
        """
        # 1. Match symptoms to known signatures
        matches = self.match_symptoms(observations)

        # 2. Check stack rules
        triggered_rules = self.check_stack_rules(observations)

        # 3. Compare metrics to baselines for flagged components
        anomalies = {}
        container_status = observations.get("container_status", {})
        for comp_name in container_status:
            comp_metrics = {
                k: v for k, v in observations.items()
                if isinstance(v, (int, float))
            }
            comp_anomalies = self.compare_to_baseline(comp_name, comp_metrics)
            if comp_anomalies:
                anomalies[comp_name] = comp_anomalies

        # 4. Suggest health checks for ambiguity resolution
        health_check_suggestions = []
        if matches:
            top_match = matches[0]
            chain = top_match.get("causal_chain")
            if chain:
                trigger_target = chain.get("trigger_target", "")
                targets = trigger_target.split(",") if trigger_target else []
                for target in targets:
                    target = target.strip()
                    hc = self.get_healthcheck(target)
                    if hc:
                        health_check_suggestions.append({
                            "component": target,
                            "probes": hc.get("probes", []),
                            "purpose": f"Disambiguate: is {target} healthy or is it the root cause?",
                        })

        # 5. Collect diagnostic actions from top matches
        diagnostic_actions = []
        for match in matches[:3]:  # Top 3
            chain = match.get("causal_chain")
            if chain:
                actions = chain.get("diagnostic_actions", [])
                if isinstance(actions, list):
                    diagnostic_actions.extend(actions)

        return {
            "matched_signatures": matches,
            "triggered_rules": triggered_rules,
            "baseline_anomalies": anomalies,
            "health_check_suggestions": health_check_suggestions,
            "diagnostic_actions": diagnostic_actions,
            "top_diagnosis": matches[0]["diagnosis"] if matches else "No matching signature found",
            "confidence": matches[0]["confidence"] if matches else "low",
        }
