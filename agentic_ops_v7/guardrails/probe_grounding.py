"""Ground IG probe selection in KB facts — metric inventory + liveness probes.

Two grounding mechanisms that close the free-form hole `{probe_candidates}`
leaves open (see ADR ig_probe_grounding_metric_inventory_and_liveness.md):

  1. Metric inventory — the COMPLETE set of metrics each NF exposes
     (derived from the metric KB, 100% coverage), injected as
     `{nf_metric_inventory}`. A metric probe may only target a metric in
     that NF's inventory.

  2. Liveness probes — the KB-authored healthcheck probe(s) per NF (from
     `healthchecks.yaml`), injected as `{nf_liveness_probes}`. For a
     hypothesis claiming the NF is down/exited/crashed, the decisive probe
     is the KB liveness probe or `get_network_status` — never an
     in-container probe that needs the container alive.

The renderers build the injected prompt blocks; `lint_ig_probe_grounding`
is the reject-and-resample guardrail that enforces both groundings
structurally. Contrast with `probe_selection.py`'s `{probe_candidates}`:

  | aspect       | {probe_candidates}            | {nf_metric_inventory}          |
  |--------------|-------------------------------|--------------------------------|
  | says         | "here are GOOD probes"        | "here is EVERYTHING NF reports"|
  | source       | hand-authored how_to_verify_live | derived from metric KB keys  |
  | coverage     | ~29% (opt-in)                 | 100% by construction           |
  | nature       | positive suggestion (prefer)  | negative constraint (may-not)  |
  | enforcement  | none                          | guardrail rejects out-of-set   |
"""

from __future__ import annotations

import re
from pathlib import Path as _PathLib
from typing import Optional

import yaml

from agentic_ops_common.metric_kb.models import MetricsKB

from ..models import FalsificationPlanSet
from .base import GuardrailResult, GuardrailVerdict

_DATA_DIR = _PathLib(__file__).resolve().parents[2] / "network_ontology" / "data"
_HEALTHCHECKS_PATH = _DATA_DIR / "healthchecks.yaml"
_COMPONENTS_PATH = _DATA_DIR / "components.yaml"

# Investigator tools that read metrics — a probe using one of these must
# target a metric that actually exists for the NF it names.
_METRIC_TOOLS = {"get_diagnostic_metrics", "get_dp_quality_gauges"}

# Investigator tools that exec INSIDE a container — they cannot produce a
# signal on a stopped/exited container.
_IN_CONTAINER_TOOLS = {
    "check_process_listeners", "run_kamcmd", "read_running_config", "read_env_config",
}

# Tools that establish liveness without needing the container alive.
_GENERIC_LIVENESS_TOOLS = {"get_network_status"}

# Keywords in a hypothesis statement that mark a container-state / liveness
# failure (NF is down rather than degraded).
_DOWN_KEYWORDS = (
    "exited", "exit", "crashed", "killed", "is down", "went down", "down ",
    "unreachable", "not running", "not responding", "stopped", "dead",
    "offline", "container is gone", "container gone",
)

_healthchecks_cache: Optional[dict] = None
_components_cache: Optional[dict] = None


def _load_healthchecks() -> dict:
    global _healthchecks_cache
    if _healthchecks_cache is None:
        doc = yaml.safe_load(_HEALTHCHECKS_PATH.read_text()) or {}
        _healthchecks_cache = doc.get("healthchecks", doc) or {}
    return _healthchecks_cache


def _load_components() -> dict:
    global _components_cache
    if _components_cache is None:
        doc = yaml.safe_load(_COMPONENTS_PATH.read_text()) or {}
        _components_cache = doc.get("components", doc) or {}
    return _components_cache


# ---------------------------------------------------------------------------
# KB lookups
# ---------------------------------------------------------------------------


def metric_inventory_for_nf(nf: str, kb: MetricsKB) -> dict[str, str]:
    """Map metric_name → one-line meaning for every metric the NF exposes.
    Empty dict when the NF has no metrics block in the KB."""
    block = kb.metrics.get(nf)
    if block is None:
        return {}
    out: dict[str, str] = {}
    for name, entry in block.metrics.items():
        desc = getattr(entry, "description", "") or ""
        if not desc and getattr(entry, "meaning", None) is not None:
            desc = getattr(entry.meaning, "what_it_signals", "") or ""
        out[name] = " ".join(desc.split())[:110]
    return out


def liveness_probes_for_nf(nf: str) -> list[dict]:
    """The KB-authored healthcheck probes for an NF (tool/healthy_if/...)."""
    hc = _load_healthchecks().get(nf) or {}
    return hc.get("probes", []) or []


def liveness_tool_names_for_nf(nf: str) -> set[str]:
    """Tool names the KB authors as this NF's liveness probes, plus the
    generic container-state tool. For mongo this is {query_subscriber,
    get_network_status} — and NOT check_process_listeners."""
    tools = {p.get("tool") for p in liveness_probes_for_nf(nf) if p.get("tool")}
    return tools | _GENERIC_LIVENESS_TOOLS


def _down_indicators_for_nf(nf: str) -> list[str]:
    return (_load_healthchecks().get(nf) or {}).get("down_indicators", []) or []


def nf_layers() -> dict[str, str]:
    """nf → ontology layer, from components.yaml."""
    return {
        nf: (spec or {}).get("layer", "")
        for nf, spec in _load_components().items()
    }


# ---------------------------------------------------------------------------
# Prompt-block renderers (the injected grounding)
# ---------------------------------------------------------------------------


def render_metric_inventory_for_prompt(hypotheses, kb: MetricsKB) -> str:
    if not hypotheses:
        return "(no hypotheses)"
    lines: list[str] = []
    for nf in _distinct_nfs(hypotheses):
        inv = metric_inventory_for_nf(nf, kb)
        lines.append(f"### Metrics exposed by `{nf}`")
        if not inv:
            lines.append(
                f"  NONE — `{nf}` emits no metrics in this deployment. Do NOT "
                f"propose a metric probe (`get_diagnostic_metrics` / "
                f"`get_dp_quality_gauges`) against `{nf}`; use a liveness or "
                f"cross-NF probe instead."
            )
        else:
            lines.append(
                f"  A metric probe on `{nf}` may ONLY target a metric below "
                f"(do not invent metric names from 3GPP priors):"
            )
            for name, desc in inv.items():
                lines.append(f"  - `{name}`" + (f" — {desc}" if desc else ""))
        lines.append("")
    return "\n".join(lines)


def render_liveness_probes_for_prompt(hypotheses) -> str:
    if not hypotheses:
        return "(no hypotheses)"
    lines: list[str] = []
    for nf in _distinct_nfs(hypotheses):
        probes = liveness_probes_for_nf(nf)
        down = _down_indicators_for_nf(nf)
        lines.append(f"### Liveness check for `{nf}` (KB-authored)")
        if probes:
            for p in probes:
                args = p.get("args")
                args_s = f"(args={args})" if args else ""
                lines.append(
                    f"  - probe: `{p.get('tool', '?')}`{args_s} — "
                    f"healthy if: {p.get('healthy_if', '?')}; "
                    f"unhealthy if: {p.get('unhealthy_if', '?')}"
                )
        else:
            lines.append(
                f"  No KB healthcheck authored for `{nf}` — use "
                f"`get_network_status()` for container state."
            )
        if down:
            lines.append(f"  down_indicators: {'; '.join(down)}")
        lines.append(
            f"  Container-state check: `get_network_status()`. For a "
            f"hypothesis claiming `{nf}` is down / exited / crashed, use the "
            f"probe(s) above and/or `get_network_status` — NOT in-container "
            f"probes (`check_process_listeners` / `run_kamcmd` / "
            f"`read_running_config`), which return no signal on a stopped "
            f"container."
        )
        lines.append("")
    return "\n".join(lines)


def _distinct_nfs(hypotheses) -> list[str]:
    seen: list[str] = []
    for h in hypotheses:
        nf = getattr(h, "primary_suspect_nf", None)
        if nf and nf not in seen:
            seen.append(nf)
    return seen


# ---------------------------------------------------------------------------
# Down-class detection
# ---------------------------------------------------------------------------


def statement_is_down_class(statement: str) -> bool:
    s = (statement or "").lower()
    return any(k in s for k in _DOWN_KEYWORDS)


def is_down_class(
    plan, na_red_nfs: Optional[set[str]] = None,
) -> bool:
    """A plan is down-class if its hypothesis claims the NF is down — by
    statement keywords, by the NA rating the NF's layer `red`, or by the
    NF carrying healthcheck down_indicators together with a down-keyword.
    """
    nf = plan.primary_suspect_nf
    if statement_is_down_class(plan.hypothesis_statement):
        return True
    if na_red_nfs and nf in na_red_nfs:
        return True
    return False


def red_layer_nfs(na_report) -> set[str]:
    """NFs whose ontology layer the NA rated `red`. Used to feed
    `na_red_nfs` into the liveness check."""
    if na_report is None:
        return set()
    red_layers: set[str] = set()
    for ls in getattr(na_report, "layer_status", []) or []:
        if getattr(ls, "rating", "") == "red":
            red_layers.add((getattr(ls, "layer", "") or "").lower())
    if not red_layers:
        return set()
    return {
        nf for nf, layer in nf_layers().items()
        if (layer or "").lower() in red_layers
    }


# ---------------------------------------------------------------------------
# Guardrail
# ---------------------------------------------------------------------------


def _probe_text(probe) -> str:
    return " ".join([
        probe.args_hint or "",
        probe.expected_if_hypothesis_holds or "",
        probe.falsifying_observation or "",
    ]).lower()


def _nfs_named_in(text: str, nf_universe: set[str]) -> set[str]:
    return {nf for nf in nf_universe if re.search(rf"\b{re.escape(nf)}\b", text)}


def lint_ig_probe_grounding(
    plan_set: FalsificationPlanSet,
    kb: Optional[MetricsKB] = None,
    na_red_nfs: Optional[set[str]] = None,
) -> GuardrailResult:
    """Reject plans whose probes are not grounded in KB facts:

    Metric check  — a metric-tool probe targeting an NF that exposes no
      metrics, or naming no actual metric of that NF, is rejected.
    Liveness check — a down-class hypothesis whose plan uses an in-container
      probe on the suspect NF but includes no liveness probe
      (`get_network_status` or the NF's KB healthcheck tool) is rejected.

    Reject → the orchestrator resamples once with the findings injected.
    """
    if kb is None:
        try:
            from agentic_ops_common.metric_kb import load_kb
            kb = load_kb()
        except Exception:
            # Without the KB we can still run the liveness check.
            kb = None

    # NF universe = all known components (so an NF with NO metrics block,
    # like udr, is still recognized when a probe names it) ∪ metric-KB NFs.
    nf_universe = set(_load_components().keys())
    if kb is not None:
        nf_universe |= set(kb.metrics.keys())
    findings: list[str] = []

    for plan in plan_set.plans:
        plan_nf = plan.primary_suspect_nf

        # --- Metric-inventory check ---
        if kb is not None:
            for idx, probe in enumerate(plan.probes):
                if probe.tool not in _METRIC_TOOLS:
                    continue
                text = _probe_text(probe)
                targets = _nfs_named_in(text, nf_universe) or {plan_nf}
                for nf in sorted(targets):
                    inv = metric_inventory_for_nf(nf, kb)
                    if not inv:
                        findings.append(
                            f"[{plan.hypothesis_id}] probe #{idx} (`{probe.tool}`) "
                            f"targets `{nf}`, which exposes NO metrics in this "
                            f"deployment. Drop this probe or use a liveness / "
                            f"cross-NF probe."
                        )
                    elif not any(m.lower() in text for m in inv):
                        sample = ", ".join(list(inv)[:6])
                        findings.append(
                            f"[{plan.hypothesis_id}] probe #{idx} (`{probe.tool}`) "
                            f"on `{nf}` names no actual `{nf}` metric — it is "
                            f"probing for a metric that does not exist here. "
                            f"`{nf}` exposes only: {sample}."
                        )

        # --- Liveness check ---
        # For a down/exited hypothesis, an in-container probe TARGETING the
        # down NF cannot run on a stopped container (no process to exec,
        # minimal images lack ss/netstat) → it returns PROBE_TOOL_UNAVAILABLE,
        # which is no signal, not a falsification. Reject it regardless of
        # whether a liveness probe is also present — the useless probe still
        # drags confidence via an AMBIGUOUS outcome. Point at the KB liveness
        # probe / get_network_status instead.
        if is_down_class(plan, na_red_nfs):
            liveness_hint = ", ".join(sorted(liveness_tool_names_for_nf(plan_nf)))
            for i, probe in enumerate(plan.probes):
                if probe.tool not in _IN_CONTAINER_TOOLS:
                    continue
                targets = _nfs_named_in(_probe_text(probe), nf_universe)
                # No NF named → assume it targets the plan's suspect NF.
                if plan_nf in targets or not targets:
                    findings.append(
                        f"[{plan.hypothesis_id}] is a down/exited hypothesis "
                        f"for `{plan_nf}`, but probe #{i} (`{probe.tool}`) is "
                        f"an in-container probe on `{plan_nf}` — it cannot run "
                        f"on a stopped container (returns no signal). Use a "
                        f"liveness probe instead: {liveness_hint}."
                    )

    if not findings:
        return GuardrailResult(verdict=GuardrailVerdict.PASS, output=plan_set)

    reason = (
        "IG probe-grounding rejected — probes must be grounded in metrics "
        "each NF actually exposes and in KB-authored liveness probes:\n  - "
        + "\n  - ".join(findings)
    )
    return GuardrailResult(
        verdict=GuardrailVerdict.REJECT,
        output=plan_set,
        reason=reason,
        notes={"grounding_findings": findings},
    )
