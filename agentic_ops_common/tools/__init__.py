"""v5 tools — split by purpose, re-exported here for backward compatibility."""

# Network diagnostic tools
from .topology import get_network_topology
# query_prometheus is intentionally NOT re-exported at this level. It is
# retained in `metrics.py` for internal callers (tests / bespoke tooling)
# but agents must use `get_nf_metrics` or `get_dp_quality_gauges`, which
# are KB-annotated and impervious to metric-name hallucination.
from .metrics import get_nf_metrics
from .container_status import get_network_status
# read_container_logs / search_logs are intentionally NOT re-exported at this
# level. They are retained in `log_search.py` for non-agent callers (scripts,
# tests) but removed from agent-facing toolsets in the v6 pipeline per ADR
# remove_log_probes_from_investigator.md — agent-authored grep patterns
# were repeatedly unreliable and empty log searches were mis-read as
# strong-negative evidence.
from .log_search import read_container_logs, search_logs
from .reachability import measure_rtt, check_process_listeners, check_tc_rules
from .config_inspection import read_config, read_running_config, read_env_config
from .kamailio_state import run_kamcmd
from .subscriber_lookup import query_subscriber

# Ontology tools
from .symptom_matching import match_symptoms, check_stack_rules, compare_to_baseline
from .log_interpretation import interpret_log_message
from .health_checks import check_component_health, get_disambiguation
from .causal_reasoning import (
    get_causal_chain,
    get_causal_chain_for_component,
    find_chains_by_observable_metric,
)
from .flows import list_flows, get_flow, get_flows_through_component
from .data_plane import get_dp_quality_gauges
# get_diagnostic_metrics is the curated agent-facing successor to
# get_nf_metrics: returns model features (the screener's view) +
# diagnostic supporting metrics (KB-tagged via agent_exposed=True).
# Step 4 of the diagnostic-tool ADR removes get_nf_metrics from
# agent toolsets and routes the agent through this tool exclusively.
from .diagnostic_metrics import get_diagnostic_metrics
from .vonr_scope import get_vonr_components

__all__ = [
    "get_network_topology",
    "get_nf_metrics",
    "get_network_status",
    "measure_rtt", "check_process_listeners", "check_tc_rules",
    "read_config", "read_running_config", "read_env_config",
    "run_kamcmd",
    "query_subscriber",
    "match_symptoms", "check_stack_rules", "compare_to_baseline",
    "interpret_log_message",
    "check_component_health", "get_disambiguation",
    "get_causal_chain", "get_causal_chain_for_component", "find_chains_by_observable_metric",
    "list_flows", "get_flow", "get_flows_through_component",
    "get_dp_quality_gauges",
    "get_diagnostic_metrics",
    "get_vonr_components",
]
