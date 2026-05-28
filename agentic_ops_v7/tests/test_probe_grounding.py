"""IG probe-grounding — metric inventory + liveness, renderers + guardrail.

Pins ADR ig_probe_grounding_metric_inventory_and_liveness.md against the two
real failure modes from run_20260527_210520_mongodb_gone:
  * a metric probe targeting udr (which exposes no metrics),
  * `check_process_listeners` on a down/exited mongo (in-container, no signal).
"""

from __future__ import annotations

from agentic_ops_common.metric_kb import load_kb
from agentic_ops_v7.guardrails.base import GuardrailVerdict
from agentic_ops_v7.guardrails.probe_grounding import (
    liveness_tool_names_for_nf,
    lint_ig_probe_grounding,
    metric_inventory_for_nf,
    render_liveness_probes_for_prompt,
    render_metric_inventory_for_prompt,
    statement_is_down_class,
)
from agentic_ops_v7.models import (
    FalsificationPlan,
    FalsificationPlanSet,
    FalsificationProbe,
)

_KB = load_kb()


def _probe(tool, args_hint="", expected="", falsifying="") -> FalsificationProbe:
    return FalsificationProbe(
        tool=tool, args_hint=args_hint,
        expected_if_hypothesis_holds=expected or "x",
        falsifying_observation=falsifying or "y",
    )


def _plan(nf, statement, probes) -> FalsificationPlan:
    return FalsificationPlan(
        hypothesis_id="h1", hypothesis_statement=statement,
        primary_suspect_nf=nf, probes=probes,
    )


def _set(*plans) -> FalsificationPlanSet:
    return FalsificationPlanSet(plans=list(plans))


class _H:
    def __init__(self, nf):
        self.primary_suspect_nf = nf


# ---------------------------------------------------------------------------
# KB lookups
# ---------------------------------------------------------------------------


def test_metric_inventory_pcf_udr_mongo():
    assert len(metric_inventory_for_nf("pcf", _KB)) == 7
    assert metric_inventory_for_nf("udr", _KB) == {}      # UDR exposes none
    assert set(metric_inventory_for_nf("mongo", _KB)) == {"subscribers"}


def test_mongo_liveness_is_query_subscriber_not_listeners():
    tools = liveness_tool_names_for_nf("mongo")
    assert "query_subscriber" in tools
    assert "get_network_status" in tools
    assert "check_process_listeners" not in tools


def test_renderers_nonempty_and_flag_udr():
    hyps = [_H("pcf"), _H("udr"), _H("mongo")]
    inv = render_metric_inventory_for_prompt(hyps, _KB)
    assert "Metrics exposed by `pcf`" in inv
    assert "NONE" in inv and "`udr`" in inv          # udr flagged as no-metrics
    liv = render_liveness_probes_for_prompt([_H("mongo")])
    assert "query_subscriber" in liv
    assert "get_network_status" in liv


def test_statement_down_class_detection():
    assert statement_is_down_class("The mongo container is in an exited state.")
    assert statement_is_down_class("pyhss crashed and is not responding")
    assert not statement_is_down_class("pcscf is experiencing elevated SIP error ratio")


# ---------------------------------------------------------------------------
# Metric-inventory guardrail
# ---------------------------------------------------------------------------


def test_metric_probe_against_udr_is_rejected():
    """The exact mongodb_gone bad probe: get_diagnostic_metrics on udr/pcf
    looking for a datastore connection error counter."""
    plan = _plan(
        "mongo", "The mongo container is exited",
        [
            _probe("get_network_status", expected="mongo exited"),
            _probe(
                "get_diagnostic_metrics",
                args_hint="fetch pcf and udr datastore connection error counters",
                expected="udr shows datastore connection errors",
                falsifying="no datastore errors at udr",
            ),
        ],
    )
    res = lint_ig_probe_grounding(_set(plan), kb=_KB)
    assert res.verdict is GuardrailVerdict.REJECT
    assert any("udr" in f for f in res.notes["grounding_findings"])


def test_metric_probe_naming_real_metric_passes():
    plan = _plan(
        "pcf", "pcf policy associations dropping",
        [
            _probe(
                "get_diagnostic_metrics",
                args_hint="read pcf fivegs_pcffunction_pa_sessionnbr",
                expected="fivegs_pcffunction_pa_sessionnbr drops to 0",
                falsifying="fivegs_pcffunction_pa_sessionnbr steady",
            ),
            _probe("measure_rtt", args_hint="pcscf -> pcf"),
        ],
    )
    res = lint_ig_probe_grounding(_set(plan), kb=_KB)
    assert res.verdict is GuardrailVerdict.PASS


# ---------------------------------------------------------------------------
# Liveness guardrail
# ---------------------------------------------------------------------------


def test_in_container_probe_on_down_mongo_is_rejected():
    """check_process_listeners on an exited mongo, with no liveness probe."""
    plan = _plan(
        "mongo", "The mongo container is in an exited state",
        [
            _probe("check_process_listeners", args_hint="check mongo listeners"),
            _probe("measure_rtt", args_hint="pcf -> mongo"),
        ],
    )
    res = lint_ig_probe_grounding(_set(plan), kb=_KB)
    assert res.verdict is GuardrailVerdict.REJECT
    assert any("down/exited" in f and "mongo" in f
               for f in res.notes["grounding_findings"])


def test_down_mongo_with_liveness_probe_passes():
    """Using the KB liveness probe (query_subscriber) makes it pass."""
    plan = _plan(
        "mongo", "The mongo container is in an exited state",
        [
            _probe("query_subscriber", args_hint="query a known subscriber"),
            _probe("get_network_status", expected="mongo exited"),
        ],
    )
    res = lint_ig_probe_grounding(_set(plan), kb=_KB)
    assert res.verdict is GuardrailVerdict.PASS


def test_in_container_probe_rejected_even_with_liveness_present():
    """The 5/27 mongodb_gone shape: the plan DID include get_network_status,
    but ALSO check_process_listeners on the exited mongo. The useless
    listener probe must still be rejected (it drags confidence via an
    AMBIGUOUS outcome), not waved through because a liveness probe exists."""
    plan = _plan(
        "mongo", "The mongo container is in an exited state",
        [
            _probe("get_network_status", expected="mongo exited"),
            _probe("check_process_listeners", args_hint="check listening ports on mongo"),
        ],
    )
    res = lint_ig_probe_grounding(_set(plan), kb=_KB)
    assert res.verdict is GuardrailVerdict.REJECT
    assert any("check_process_listeners" in f for f in res.notes["grounding_findings"])


def test_in_container_probe_on_other_nf_for_down_hypothesis_allowed():
    """A down-mongo hypothesis may still run an in-container probe on a
    DIFFERENT, live NF (e.g. run_kamcmd on pcscf to see downstream effect)."""
    plan = _plan(
        "mongo", "The mongo container is in an exited state",
        [
            _probe("get_network_status", expected="mongo exited"),
            _probe("run_kamcmd", args_hint="pcscf stats.get_statistics — downstream effect"),
        ],
    )
    res = lint_ig_probe_grounding(_set(plan), kb=_KB)
    assert res.verdict is GuardrailVerdict.PASS


def test_in_container_probe_on_non_down_hypothesis_is_allowed():
    """run_kamcmd on pcscf for a NON-down (degradation) hypothesis is fine —
    the liveness rule only fires for down-class claims."""
    plan = _plan(
        "pcscf", "pcscf is rejecting SIP requests with elevated error ratio",
        [
            _probe("run_kamcmd", args_hint="pcscf stats.get_statistics"),
            _probe("measure_rtt", args_hint="pcscf -> icscf"),
        ],
    )
    res = lint_ig_probe_grounding(_set(plan), kb=_KB)
    assert res.verdict is GuardrailVerdict.PASS


def test_na_red_layer_triggers_down_class_without_keyword():
    """Even without a statement keyword, an NF whose layer the NA rated
    red is treated as down-class."""
    plan = _plan(
        "mongo", "mongo is the source of subscriber lookup failures",  # no keyword
        [
            _probe("check_process_listeners", args_hint="check mongo listeners"),
            _probe("measure_rtt", args_hint="pcf -> mongo"),
        ],
    )
    # mongo's layer is `infrastructure`; mark it red.
    res = lint_ig_probe_grounding(_set(plan), kb=_KB, na_red_nfs={"mongo"})
    assert res.verdict is GuardrailVerdict.REJECT
