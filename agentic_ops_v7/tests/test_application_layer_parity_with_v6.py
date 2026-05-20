"""v7 application-layer parity with v6 (copy-time tripwire).

Per Phase 2 of ADR `path_anchored_probe_planning_for_transport_layer_faults.md`,
v7 carries its own copies of v6's application-layer phase
implementations. At v7 creation these files are bit-for-bit copies
(modulo deliberately authored extensions in models.py and the
synthesis prompt). This test is the tripwire that catches any
*unintentional* divergence — e.g. a copy that didn't carry a docstring,
a guardrail file that wasn't copied, a prompt that drifted.

Behavioral parity (running real chaos scenarios through both versions
and asserting equivalent diagnoses) requires a live lab stack and
GCP/Vertex credentials; that runs as a nightly CI batch (Phase 7).
This test runs in plain pytest and covers the structural shape:
imports, model fields, prompt files, guardrail files, deliberate diffs.

Allowed deliberate diffs (Phase 2 + Phase 3 unified-Synthesis rework):
  - models.py: `verdict_kind` literal gains "localized";
                `localization` field added;
                new `Localization` Pydantic model.
  - prompts/synthesis.md: rewritten with branch-select directive at
                top routing the LLM to either application-layer rules
                or the localized-verdict rules per a populated
                `{path_walk_for_synthesis}` placeholder. (Phase 2
                started as an append-only edit; Phase 3 reshapes the
                prompt's structure when the unified Synthesis flow
                landed — the localized-verdict section was no longer
                a tail-appended afterthought but a co-equal branch.)
  - guardrails/synthesis_pool.py + guardrails/confidence_cap.py:
                gain explicit `verdict_kind == "localized"` PASS
                short-circuits at function entry. ADR-mandated:
                "downstream guardrails recognize the verdict_kind
                and short-circuit" (line 111 of the ADR).
  - __main__.py: CLI usage strings say v7 instead of v6.
  - __init__.py: replaced with the v7 module docstring.

Anything else divergent is a bug.
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest

_V6_ROOT = Path(__file__).resolve().parents[2] / "agentic_ops_v6"
_V7_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Module presence — v7 has the same submodule shape as v6
# ---------------------------------------------------------------------------


_REQUIRED_FILES = [
    "__init__.py",
    "__main__.py",
    "orchestrator.py",
    "models.py",
    "retry_config.py",
    "subagents/__init__.py",
    "subagents/correlation_analyzer.py",
    "subagents/event_aggregator.py",
    "subagents/instruction_generator.py",
    "subagents/investigator.py",
    "subagents/network_analyst.py",
    "subagents/ontology_consultation.py",
    "subagents/synthesis.py",
    "guardrails/__init__.py",
    "guardrails/_mechanism_scope.py",
    "guardrails/base.py",
    "guardrails/confidence_cap.py",
    "guardrails/empty_output.py",
    "guardrails/evidence_citations.py",
    "guardrails/ig_validator.py",
    "guardrails/investigator_consensus.py",
    "guardrails/investigator_minimum.py",
    "guardrails/llm_output_sanitizer.py",
    "guardrails/mechanism_grounding.py",
    "guardrails/na_linter.py",
    "guardrails/na_ranking.py",
    "guardrails/probe_selection.py",
    "guardrails/runner.py",
    "guardrails/synthesis_pool.py",
    "prompts/instruction_generator.md",
    "prompts/investigator.md",
    "prompts/network_analyst.md",
    "prompts/ontology_consultation.md",
    "prompts/synthesis.md",
]


@pytest.mark.parametrize("rel_path", _REQUIRED_FILES)
def test_v7_has_same_files_as_v6(rel_path: str):
    """Every file v6 ships, v7 ships too. Catches a missed copy."""
    v7_path = _V7_ROOT / rel_path
    v6_path = _V6_ROOT / rel_path
    assert v6_path.exists(), f"v6 reference file missing: {rel_path}"
    assert v7_path.exists(), (
        f"v7 missing required copy of v6 file: {rel_path}\n"
        f"v7 must carry its own copy of every v6 application-layer phase "
        f"file (see ADR path_anchored_probe_planning_for_transport_layer_faults.md)."
    )


# ---------------------------------------------------------------------------
# File content parity — most files are byte-for-byte copies
# ---------------------------------------------------------------------------


# Files that legitimately diverge from v6 at v7 creation or during
# Phase 3+ wiring. Each entry should have a corresponding deliberate-
# divergence test below that pins the *expected* shape of the diff,
# so accidental drift in those files still fails CI.
_INTENTIONALLY_DIVERGENT = {
    "__init__.py",            # replaced with v7 module docstring
    "__main__.py",            # CLI string says v7 instead of v6
    "models.py",              # adds Localization, `localized` literal
    "prompts/synthesis.md",   # branch-select directive + localized-verdict rules
    "orchestrator.py",        # Phase 3: invokes _phase05_symptom_classifier
    # Phase 3 unified-Synthesis rework — the ADR mandates that
    # downstream guardrails recognize `verdict_kind == "localized"`
    # and short-circuit. Pinned by deliberate-divergence tests below.
    "guardrails/synthesis_pool.py",
    "guardrails/confidence_cap.py",
    # R4 — RAG injection of prior similar episodes into NA's input
    # bundle. The prompt gains a `{prior_similar_episodes}` placeholder
    # plus guidance on how to read prior cases. Pinned by deliberate-
    # divergence test below.
    "prompts/network_analyst.md",
    # ADR `agent_tool_args_must_be_names_not_ips.md` — the prompt now
    # carries a names-only rule for tool args + updated example showing
    # `measure_rtt(\"pcscf\", \"icscf\")` instead of an IP literal.
    # Pinned by deliberate-divergence test below. The investigator
    # prompt also carries the "Verify deployment-specific assumptions"
    # section (ADR `stack_config_tool_for_agents.md`) — pinned by
    # `test_v7_investigator_prompt_has_deployment_config_rule` below.
    "prompts/investigator.md",
    # ADR `make_gemini_model_version_configurable` (commit 7edacd7) —
    # every subagent's model parameter was lifted from a literal to an
    # env-driven value. v7 carries the change; v6 doesn't.
    "subagents/network_analyst.py",
    "subagents/ontology_consultation.py",
    "subagents/synthesis.py",
    # Two subagents diverge for an additional reason: ADR
    # `stack_config_tool_for_agents.md` wires `get_deployment_config`
    # into the IG and Investigator toolsets. v6 doesn't have the tool.
    # Divergence pinned by `test_v7_*_has_deployment_config_in_toolset`
    # below.
    "subagents/instruction_generator.py",
    "subagents/investigator.py",
}


@pytest.mark.parametrize("rel_path", [p for p in _REQUIRED_FILES if p not in _INTENTIONALLY_DIVERGENT])
def test_v7_file_matches_v6_byte_for_byte(rel_path: str):
    """Every non-deliberately-divergent file matches v6 byte-for-byte.

    The path-walk machinery is shared via `agentic_ops_common.path_walk`;
    v7 doesn't need to *modify* v6's NA/IG/Investigator/EvidenceValidator/
    guardrails to land Phase 2. They start identical to v6 and evolve
    independently from there.

    A failure here means either:
        (a) someone modified a v7 file before this test was set up;
        (b) the file should be added to _INTENTIONALLY_DIVERGENT with
            a comment explaining why it's allowed to differ.
    """
    v7_text = (_V7_ROOT / rel_path).read_text()
    v6_text = (_V6_ROOT / rel_path).read_text()
    assert v7_text == v6_text, (
        f"{rel_path}: v7 has diverged from v6 unintentionally.\n"
        f"If this is a deliberate v7-only change, add the path to "
        f"_INTENTIONALLY_DIVERGENT with a comment in this test file "
        f"(and ideally update Phase 2's deliberate-diff list in the ADR)."
    )


# ---------------------------------------------------------------------------
# Deliberate-divergence tests — the listed exceptions diverge in
# specific, documented ways and not others.
# ---------------------------------------------------------------------------


def test_v7_init_has_self_containment_docstring():
    """v7's __init__.py replaces v6's with a docstring describing v7
    and citing the self-containment rule. This is intended."""
    text = (_V7_ROOT / "__init__.py").read_text().lower()
    assert "v7" in text
    assert "self-containment" in text or "self-contained" in text
    assert "agentic_ops_common" in text


def test_v7_main_says_v7_not_v6():
    """The CLI usage strings should say v7."""
    text = (_V7_ROOT / "__main__.py").read_text()
    assert "agentic_ops_v7" in text
    assert "agentic_ops_v6" not in text


def test_v7_models_extends_verdict_kind_with_localized():
    """v7 models add `localized` to the DiagnosisReport.verdict_kind
    literal. Other fields and types stay equivalent to v6."""
    from agentic_ops_v7.models import DiagnosisReport
    # The verdict_kind annotation should accept "localized".
    field = DiagnosisReport.model_fields["verdict_kind"]
    # Pydantic v2 stores the literal type's args on the annotation.
    annotation = field.annotation
    # Walk the Literal's args to find "localized".
    import typing as _typing
    args = _typing.get_args(annotation)
    assert "localized" in args, (
        f"v7's DiagnosisReport.verdict_kind should accept 'localized'; "
        f"got: {args}"
    )


def test_v7_models_adds_localization_field():
    """v7's DiagnosisReport gains a `localization` field for the
    path-walk attribution payload."""
    from agentic_ops_v7.models import DiagnosisReport, Localization
    assert "localization" in DiagnosisReport.model_fields
    # Default is None; populated only on `localized` verdict_kind.
    field = DiagnosisReport.model_fields["localization"]
    assert field.default is None


def test_v7_localization_model_has_required_fields():
    """The path-walk Pydantic model surface must carry the fields the
    walker emits."""
    from agentic_ops_v7.models import Localization
    expected_fields = {
        "hop_node", "hop_kind", "hop_iface",
        "attribution_kind", "counter_kind",
        "dropped_pkts", "dropped_pct",
        "observed_delay_ms", "evidence",
    }
    actual = set(Localization.model_fields.keys())
    missing = expected_fields - actual
    assert not missing, f"Localization model missing fields: {missing}"


def test_v7_synthesis_prompt_has_localized_paragraph():
    """The synthesis prompt must teach the LLM how to render
    `localized` verdicts. Without this, even if the orchestrator
    routes to the path walk, Synthesis won't know what to do with
    the new verdict_kind."""
    text = (_V7_ROOT / "prompts" / "synthesis.md").read_text()
    assert "localized" in text.lower()
    assert "path-walk" in text.lower() or "path walk" in text.lower()
    assert "localization" in text.lower()


def test_v7_orchestrator_wires_phase05_symptom_classifier():
    """Phase 3 wires the SymptomClassifier into the v7 orchestrator
    immediately after Phase 0. The orchestrator file legitimately
    diverges from v6 because of this wiring; this test pins the
    expected shape of the divergence so accidental drift still
    fails CI."""
    text = (_V7_ROOT / "orchestrator.py").read_text()
    # Phase 0.5 function and its call must both be present.
    assert "_phase05_symptom_classifier" in text, (
        "v7 orchestrator should define and call _phase05_symptom_classifier"
    )
    # The classifier's import must reach symptom_classifier under v7,
    # not under v6 (v7 self-containment rule).
    assert "from .symptom_classifier import classify" in text, (
        "v7 orchestrator should import classify from its own "
        "symptom_classifier module via a relative import"
    )
    # Phase 0 -> 0.5 -> 1 ordering at the main-pipeline call sites.
    # We use the most-specific substring per phase so we hit the
    # call (not the function definition).
    phase0_call = text.find("await _phase0_anomaly_screener(state")
    phase05_call = text.find("_phase05_symptom_classifier(state, all_phases)")
    phase1_call = text.find("_phase1_event_aggregator(episode_id")
    assert phase0_call > 0, "phase 0 call site missing"
    assert phase05_call > 0, "phase 0.5 call site missing"
    assert phase1_call > 0, "phase 1 call site missing"
    assert phase0_call < phase05_call < phase1_call, (
        f"orchestration call-site order broken: phase0={phase0_call}, "
        f"phase05={phase05_call}, phase1={phase1_call}"
    )


def test_v7_synthesis_prompt_carries_load_bearing_v6_content():
    """The Phase-3 rework reshapes the prompt's structure (branch-select
    directive at top, path-walk placeholder, localized-verdict section
    rewritten as a co-equal branch). The strict "starts-with v6
    byte-for-byte" check from Phase 2 no longer applies, but the
    application-layer rules v6 carries must still be present — the
    LLM still emits `confirmed`/`promoted`/`inconclusive` verdicts on
    the app-layer branch unchanged.

    This test pins the load-bearing v6 content (template substitution
    placeholders, verdict-aggregation rule headers, evidence-validation
    cap, observation-only constraint, output-format schema rules) so
    accidental rewrites of the application-layer rules still fail CI.
    """
    v7_text = (_V7_ROOT / "prompts" / "synthesis.md").read_text()
    # ADK template-substitution placeholders the orchestrator populates
    # for the app-layer branch — every one must remain.
    for placeholder in (
        "{network_analysis}", "{correlation_analysis}",
        "{investigator_verdicts}", "{evidence_validation}",
        "{candidate_pool}",
    ):
        assert placeholder in v7_text, (
            f"v7's synthesis.md missing app-layer placeholder {placeholder} "
            "— the application-layer branch can no longer substitute its "
            "input bundle."
        )
    # Load-bearing v6 rule headers — these drive application-layer verdict
    # aggregation and must survive the Phase-3 rework.
    for marker in (
        "Verdict aggregation rule",
        "Evidence validation cap",
        "Observation-only constraint",
        "Output format",
        "Pool membership",
    ):
        assert marker in v7_text, (
            f"v7's synthesis.md missing load-bearing v6 section "
            f"`{marker}` — the application-layer rules must still be "
            "intact."
        )


def test_v7_synthesis_prompt_has_path_walk_placeholder():
    """Phase-3 unified-Synthesis rework: the prompt reads the path-walk
    bundle via the new `{path_walk_for_synthesis}` placeholder. The
    orchestrator populates it on the localized branch and leaves it
    empty on the app-layer branch. Without this placeholder the LLM
    has no way to consume the path-walk report."""
    v7_text = (_V7_ROOT / "prompts" / "synthesis.md").read_text()
    assert "{path_walk_for_synthesis}" in v7_text, (
        "v7's synthesis.md must declare the `{path_walk_for_synthesis}` "
        "template substitution — this is how the orchestrator hands the "
        "path-walk report to the unified Synthesis LLM."
    )


def test_v7_synthesis_pool_guardrail_short_circuits_localized():
    """Phase-3 unified-Synthesis rework: pool-membership doesn't apply
    to localized verdicts (the candidate pool is a per-NF construct
    from the app-layer pipeline; the localized branch names a hop, not
    an NF from a pool). The ADR mandates that this guardrail recognize
    the verdict_kind and short-circuit."""
    text = (_V7_ROOT / "guardrails" / "synthesis_pool.py").read_text()
    assert 'report.verdict_kind == "localized"' in text, (
        "v7's synthesis_pool.py must short-circuit on "
        "`verdict_kind == \"localized\"` per ADR "
        "path_anchored_probe_planning_for_transport_layer_faults.md."
    )


def test_v7_na_prompt_has_prior_similar_episodes_placeholder():
    """R4 — RAG injection adds a `{prior_similar_episodes}` placeholder
    + guidance section to the NA prompt. The orchestrator's
    `_phase25_rag_inject_prior_episodes` populates the state key the
    placeholder reads. Without this placeholder the injection is dead."""
    text = (_V7_ROOT / "prompts" / "network_analyst.md").read_text()
    assert "{prior_similar_episodes}" in text, (
        "v7's network_analyst.md must declare the "
        "`{prior_similar_episodes}` template substitution — this is "
        "how the orchestrator hands retrieved prior cases to the NA."
    )
    # Carry the guidance section that teaches the NA how to read
    # prior cases without copying them blindly. Without this the
    # placeholder is just dangling text.
    assert "Prior similar episodes" in text


def test_v7_investigator_prompt_uses_names_not_ips_for_tool_args():
    """ADR `agent_tool_args_must_be_names_not_ips.md` — the Investigator
    prompt must teach the names-only rule and use a name-shaped example
    for `measure_rtt`. An IP-shaped example primes the LLM to fabricate
    plausible-looking IPs (observed failure mode: run_20260512_082224
    hallucinated 172.22.0.8 as pyhss's IP)."""
    text = (_V7_ROOT / "prompts" / "investigator.md").read_text()
    # The prompt carries an explicit names-only directive somewhere.
    assert "container NAME" in text or "container name" in text and "not an IP" in text, (
        "v7's investigator.md must teach the names-only rule explicitly. "
        "See ADR agent_tool_args_must_be_names_not_ips.md."
    )
    # The example invocation does not contain a 172.22.0.* IP literal.
    import re as _re
    assert not _re.search(r"measure_rtt\([^)]*172\.22\.\d+\.\d+", text), (
        "v7's investigator.md still has an IP-shaped example for "
        "measure_rtt. Replace with a container name (e.g. "
        "measure_rtt(\"pcscf\", \"icscf\"))."
    )


def test_v7_confidence_cap_guardrail_short_circuits_localized():
    """Phase-3 unified-Synthesis rework: the confidence-cap evidence-
    strength computation reads InvestigatorVerdict probe-result counts,
    which the path walk doesn't produce. The ADR mandates that this
    guardrail recognize the verdict_kind and short-circuit."""
    text = (_V7_ROOT / "guardrails" / "confidence_cap.py").read_text()
    assert 'report.verdict_kind == "localized"' in text, (
        "v7's confidence_cap.py must short-circuit on "
        "`verdict_kind == \"localized\"` per ADR "
        "path_anchored_probe_planning_for_transport_layer_faults.md."
    )


# ---------------------------------------------------------------------------
# v7 imports cleanly — sanity check
# ---------------------------------------------------------------------------


def test_v7_orchestrator_imports():
    """The orchestrator must import without error from a clean process.

    A regression in any phase implementation that v7 carries (an
    accidentally edited guardrail, a model that no longer fits, etc.)
    typically surfaces here as an ImportError or pydantic validation.
    """
    mod = importlib.import_module("agentic_ops_v7.orchestrator")
    assert hasattr(mod, "investigate"), (
        "v7's orchestrator must expose the `investigate` async entry "
        "point matching v6's contract."
    )


def test_v7_models_imports():
    mod = importlib.import_module("agentic_ops_v7.models")
    for cls in ("DiagnosisReport", "Hypothesis", "InvestigatorVerdict",
                "ProbeResult", "FalsificationPlan", "Localization"):
        assert hasattr(mod, cls), f"v7.models missing {cls}"


def test_v7_subagents_import():
    for sub in ("network_analyst", "instruction_generator", "investigator",
                "synthesis", "ontology_consultation", "correlation_analyzer",
                "event_aggregator"):
        importlib.import_module(f"agentic_ops_v7.subagents.{sub}")


def test_v7_guardrails_import():
    for g in ("base", "confidence_cap", "empty_output", "evidence_citations",
              "ig_validator", "investigator_consensus", "investigator_minimum",
              "llm_output_sanitizer", "mechanism_grounding", "na_linter",
              "na_ranking", "probe_selection", "runner", "synthesis_pool"):
        importlib.import_module(f"agentic_ops_v7.guardrails.{g}")


# ---------------------------------------------------------------------------
# Deliberate-divergence pins for ADR `stack_config_tool_for_agents.md`.
# The Investigator and IG toolsets gain `get_deployment_config`; the
# Investigator prompt gains a "Verify deployment-specific assumptions"
# section. Without these pins, accidental drift (removing the tool from
# the toolset, dropping the prompt section) would not be caught by the
# byte-for-byte parity test because both files are in the divergent
# allowlist.
# ---------------------------------------------------------------------------


def test_v7_investigator_toolset_has_get_deployment_config():
    """ADR `stack_config_tool_for_agents.md` wires the new tool into
    the v7 Investigator toolset. Drift here re-opens the failure mode
    where the investigator hallucinates port-binding faults by relying
    on IANA-standard priors instead of the deployment's actual config.
    """
    src = (_V7_ROOT / "subagents" / "investigator.py").read_text()
    assert "tools.get_deployment_config" in src, (
        "v7 Investigator toolset must include `tools.get_deployment_config` "
        "per ADR `stack_config_tool_for_agents.md`. Without it the "
        "Investigator falls back to IANA priors when asserting port "
        "bindings."
    )


def test_v7_instruction_generator_toolset_has_get_deployment_config():
    """Same ADR wires the tool into the IG toolset so plans can ground
    "Expected if hypothesis holds" / "Falsifying observation" criteria
    in actual configured port values, not IANA defaults."""
    src = (_V7_ROOT / "subagents" / "instruction_generator.py").read_text()
    assert "tools.get_deployment_config" in src, (
        "v7 InstructionGenerator toolset must include "
        "`tools.get_deployment_config` per ADR "
        "`stack_config_tool_for_agents.md`."
    )


def test_v7_synthesis_prompt_compound_requires_distinct_second_nf():
    """The compound branch's entry condition is NOT "both bundles
    populated" — it's "both bundles populated AND the app-layer pipeline
    implicates a distinct second NF." Without that distinction the LLM
    over-fires `compound` on single-fault scenarios where the walker and
    the app-layer pipeline merely converge on the same NF.

    Triggering run: `run_20260520_212351_hss_unresponsive` — the LLM
    emitted `verdict_kind=compound, additional_root_causes=[]` on a
    scenario where the walker localized pyhss AND the app-layer
    pipeline confirmed the same pyhss. The compound-consistency
    guardrail REJECTed twice; `on_guardrail_exhausted=accept` let the
    invalid shape through. The fix is the prompt directive — this
    test pins it.

    See `agentic_ops_v7/prompts/synthesis.md` and the post-run
    analysis in `docs/critical-observations/`.
    """
    text = (_V7_ROOT / "prompts" / "synthesis.md").read_text()

    # The load-bearing directive — branch-2 produces EITHER localized
    # OR compound depending on whether a distinct second NF exists.
    assert "DIFFERENT" in text or "distinct" in text.lower(), (
        "synthesis.md must explicitly say compound requires a "
        "DIFFERENT / distinct second NF beyond the walker's hop."
    )

    # The fallback rule the LLM must follow when the application-layer
    # pipeline only confirms the walker's NF.
    assert "same NF" in text.lower() or "single root cause" in text.lower(), (
        "synthesis.md must teach the 'walker and app-layer named the "
        "same NF → emit localized' fallback. Without it the LLM "
        "over-fires `compound` on single-fault scenarios."
    )

    # Explicit warning against the resample-with-same-shape trap.
    # The triggering run showed the LLM resampling to the same invalid
    # compound shape because the prompt didn't tell it what to do on
    # REJECT. The directive must surface that path.
    assert "resample" in text.lower(), (
        "synthesis.md must address the resample behavior after a "
        "compound-consistency REJECT — change verdict_kind, do not "
        "retry the same shape."
    )


def test_v7_investigator_prompt_has_deployment_config_rule():
    """The investigator prompt carries a 'Verify deployment-specific
    assumptions' section per ADR `stack_config_tool_for_agents.md`.
    Pure-principle text — no specific NF/port/run names. Pin the
    section header and the load-bearing requirement that any port /
    IP / container-name claim must trace back to a config lookup or
    probe data."""
    src = (_V7_ROOT / "prompts" / "investigator.md").read_text()
    assert "Verify deployment-specific assumptions" in src, (
        "Investigator prompt missing the 'Verify deployment-specific "
        "assumptions' section per ADR `stack_config_tool_for_agents.md`."
    )
    assert "get_deployment_config" in src, (
        "Investigator prompt must reference the `get_deployment_config` "
        "tool by name in the deployment-assumptions rule."
    )
    # Pin that the rule remains principle-only — no hard-coded port
    # numbers. Naming a specific port in the prompt does not generalize
    # across deployments and re-introduces the failure mode this rule
    # was written to close. NF names appear elsewhere in the prompt for
    # legitimate reasons (e.g. the names-only-args tool examples), so a
    # blanket NF-name check would be too aggressive — the port-number
    # check is the load-bearing one for this ADR's failure mode.
    assert "3868" not in src and "3875" not in src, (
        "Investigator prompt must NOT name specific port numbers in "
        "the deployment-assumptions rule — the rule has to generalize "
        "across deployments. Found a specific port number in the prompt."
    )
