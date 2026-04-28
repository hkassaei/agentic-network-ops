"""v6 orchestrator — 8-phase pipeline with parallel per-hypothesis Investigators.

Pipeline:
  Phase 0  AnomalyScreener           (ML, no LLM)
  Phase 1  EventAggregator           (reads fired events from store)
  Phase 2  CorrelationAnalyzer       (runs correlation engine, feeds NA)
  Phase 3  NetworkAnalyst            (ranked hypotheses over KB + events + correlation)
  Phase 4  InstructionGenerator      (one falsification plan per hypothesis)
  Phase 5  Investigator × N          (parallel sub-agents, one per hypothesis)
  Phase 6  EvidenceValidator         (per-sub-investigator citation check)
  Phase 7  Synthesis                 (aggregates N verdicts into NOC diagnosis)

Notes:
  - The agentic_chaos framework is expected to invoke the metric-KB trigger
    evaluator during its baseline/injection/observation phases, BEFORE this
    orchestrator runs. This pipeline is a CONSUMER of the event store, not
    a producer. If no events are available, Phase 1 still runs but yields
    an empty event list and the pipeline continues with a warning.
  - MAX_PARALLEL_INVESTIGATORS = 3. If NA produces more hypotheses, only the
    top 3 by ranking are investigated.
  - Mechanical guardrail: any sub-Investigator making <2 tool calls has its
    verdict forced to INCONCLUSIVE.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any, Optional

from google.adk.agents.base_agent import BaseAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from agentic_ops_common.metric_kb import (
    EventStore,
    KBLoadError,
    enrich_anomaly_report,
    load_kb,
)
from agentic_ops_common.models import (
    InvestigationTrace,
    PhaseTrace,
    TokenBreakdown,
    ToolCallTrace,
)

from .models import (
    CorrelationAnalysis,
    FalsificationPlan,
    FalsificationPlanSet,
    Hypothesis,
    InvestigatorVerdict,
    NetworkAnalystReport,
)
from .subagents.correlation_analyzer import analyze_correlations
from .subagents.evidence_validator import validate_evidence
from .subagents.event_aggregator import aggregate_episode_events
from .subagents.instruction_generator import create_instruction_generator
from .subagents.investigator import create_investigator_agent
from .subagents.network_analyst import create_network_analyst
from .subagents.synthesis import create_synthesis_agent

log = logging.getLogger("v6.orchestrator")


MAX_PARALLEL_INVESTIGATORS = 3
MIN_TOOL_CALLS_PER_INVESTIGATOR = 2


# ============================================================================
# Phase runner — mirrors v5's pattern
# ============================================================================

async def _run_phase(
    agent: BaseAgent,
    state: dict[str, Any],
    question: str,
    session_service: InMemorySessionService,
    on_event=None,
) -> tuple[dict[str, Any], list[PhaseTrace]]:
    """Run one agent in an isolated session, return updated state + trace."""
    runner = Runner(
        agent=agent, app_name="v6", session_service=session_service,
    )
    session = await session_service.create_session(
        app_name="v6", user_id="v6_op", state=dict(state),
    )

    phase_map: dict[str, PhaseTrace] = {}
    _SKIP = {"user"}

    async for event in runner.run_async(
        user_id="v6_op",
        session_id=session.id,
        new_message=types.Content(role="user", parts=[types.Part(text=question)]),
    ):
        author = event.author or ""
        ts = event.timestamp if hasattr(event, "timestamp") and event.timestamp else time.time()

        if author in _SKIP:
            continue

        if author and author not in phase_map:
            phase_map[author] = PhaseTrace(agent_name=author, started_at=ts)
            if on_event:
                try:
                    await on_event({"type": "phase_start", "agent": author})
                except Exception:
                    pass

        phase = phase_map.get(author)

        # Collect function calls + token usage
        if event.content and event.content.parts:
            for part in event.content.parts:
                if hasattr(part, "function_call") and part.function_call:
                    fc = part.function_call
                    if phase:
                        args_str = ""
                        try:
                            args_str = json.dumps(dict(fc.args or {}))
                        except Exception:
                            args_str = str(fc.args or {})
                        phase.tool_calls.append(ToolCallTrace(
                            name=fc.name, args=args_str, timestamp=ts,
                        ))
                if hasattr(part, "function_response") and part.function_response:
                    fr = part.function_response
                    if fr and phase and phase.tool_calls:
                        for tc in reversed(phase.tool_calls):
                            if tc.name == fr.name:
                                # Record result size
                                try:
                                    tc.result_size = len(str(fr.response or ""))
                                except Exception:
                                    pass
                                break

        if event.usage_metadata and phase:
            try:
                phase.tokens.prompt += int(event.usage_metadata.prompt_token_count or 0)
                phase.tokens.completion += int(event.usage_metadata.candidates_token_count or 0)
                phase.tokens.thinking += int(event.usage_metadata.thoughts_token_count or 0)
                phase.tokens.total += int(event.usage_metadata.total_token_count or 0)
                phase.llm_calls += 1
            except Exception:
                pass

        # Track state writes for this phase
        if event.actions and event.actions.state_delta and phase:
            for key in event.actions.state_delta:
                if key not in phase.state_keys_written:
                    phase.state_keys_written.append(key)

    # Gather final state
    final_session = await session_service.get_session(
        app_name="v6", user_id="v6_op", session_id=session.id,
    )
    updated_state = dict(final_session.state)

    traces = list(phase_map.values())
    now = time.time()
    for t in traces:
        t.finished_at = now
        t.duration_ms = int((t.finished_at - t.started_at) * 1000)

    return updated_state, traces


def _accumulate_phase_traces(state: dict, new_traces: list) -> None:
    current = state.get("phase_traces_so_far", []) or []
    for t in new_traces:
        current.append(t.model_dump(mode="json") if hasattr(t, "model_dump") else dict(t))
    state["phase_traces_so_far"] = current


# ============================================================================
# Phase 0 — AnomalyScreener
# ============================================================================

async def _phase0_anomaly_screener(
    state: dict,
    metric_snapshots: Optional[list[dict]],
    all_phases: list,
) -> None:
    """Run the anomaly screener. Same logic as v5; outputs `anomaly_report`."""
    try:
        from anomaly_trainer.persistence import load_model
        from agentic_ops_common.anomaly.preprocessor import MetricPreprocessor

        screener, _, meta = load_model()
        if screener is None or not screener.is_trained:
            log.info("No trained anomaly model — Phase 0 skipped")
            state["anomaly_report"] = "Anomaly screening not available (no trained model)."
            return

        phase0_start = time.time()
        snapshots = metric_snapshots or []
        if not snapshots:
            from agentic_ops_common.anomaly.preprocessor import parse_nf_metrics_text
            from agentic_ops_common import tools as common_tools
            text = await common_tools.get_nf_metrics()
            raw = parse_nf_metrics_text(text)
            snapshots = [{"_parsed": raw}]

        pp = MetricPreprocessor()
        best_report = None
        for i, snap in enumerate(snapshots):
            raw_metrics = {}
            snap_ts = snap.get("_timestamp")
            for comp, data in snap.items():
                if comp.startswith("_"):
                    if comp == "_parsed":
                        raw_metrics = snap["_parsed"]
                        break
                    continue
                if isinstance(data, dict) and "metrics" in data:
                    raw_metrics[comp] = data["metrics"]
                elif isinstance(data, dict):
                    raw_metrics[comp] = data
            features = pp.process(raw_metrics, timestamp=snap_ts)
            if i >= 6 and features:
                report = screener.score(features, liveness=pp.liveness_signals())
                if best_report is None or report.overall_score > best_report.overall_score:
                    best_report = report

        if best_report is not None:
            # Enrich flags with KB semantic context so the NA sees *what
            # the deviation means* instead of only *which numbers moved*.
            # KB load is best-effort — if it fails, we still emit the
            # numeric-only report rather than dropping anomaly signals.
            try:
                kb = load_kb()
                enrich_anomaly_report(best_report, kb)
            except KBLoadError as e:
                log.warning("KB unavailable for anomaly flag enrichment: %s", e)
            except Exception as e:
                log.warning(
                    "Anomaly flag enrichment failed (non-fatal): %s", e,
                    exc_info=True,
                )
            state["anomaly_report"] = best_report.to_prompt_text()
            state["anomaly_flags"] = best_report.to_dict_list()
        else:
            state["anomaly_report"] = (
                f"Anomaly screening produced no results ({len(snapshots)} snapshots)."
            )

        phase0_duration = int((time.time() - phase0_start) * 1000)
        phase0_trace = PhaseTrace(
            agent_name="AnomalyScreener",
            started_at=phase0_start,
            finished_at=time.time(),
            duration_ms=phase0_duration,
        )
        n_flags = len(best_report.flags) if best_report else 0
        best_score = best_report.overall_score if best_report else 0.0
        phase0_trace.output_summary = f"{n_flags} anomalies flagged (score={best_score:.3f})"
        all_phases.append(phase0_trace)

    except ImportError as e:
        log.warning("Phase 0 skipped — ImportError: %s", e)
        state["anomaly_report"] = f"Anomaly screening not available: ImportError ({e})"
    except Exception as e:
        log.warning("AnomalyScreener failed (non-fatal): %s", e, exc_info=True)
        state["anomaly_report"] = f"Anomaly screening failed: {e}"


# ============================================================================
# Phase 1 + 3 — Events + Correlation (Python only, no LLM)
# ============================================================================

def _phase1_event_aggregator(
    episode_id: str, all_phases: list,
) -> tuple[list, str]:
    phase_start = time.time()
    try:
        events, rendered = aggregate_episode_events(episode_id=episode_id)
    except Exception as e:
        log.warning("EventAggregator failed: %s", e)
        events, rendered = [], f"EventAggregator error: {e}"
    trace = PhaseTrace(
        agent_name="EventAggregator",
        started_at=phase_start,
        finished_at=time.time(),
        duration_ms=int((time.time() - phase_start) * 1000),
        output_summary=f"{len(events)} events",
    )
    all_phases.append(trace)
    return events, rendered


def _phase2_correlation_analyzer(
    events: list, episode_id: str, all_phases: list,
) -> CorrelationAnalysis:
    phase_start = time.time()
    try:
        kb = load_kb()
        analysis = analyze_correlations(kb, events, episode_id=episode_id)
    except KBLoadError as e:
        log.warning("Correlation analyzer: KB load failed: %s", e)
        analysis = CorrelationAnalysis(
            episode_id=episode_id,
            events_considered=len(events),
            hypotheses_text=f"KB unavailable: {e}",
        )
    except Exception as e:
        log.warning("CorrelationAnalyzer failed: %s", e, exc_info=True)
        analysis = CorrelationAnalysis(
            episode_id=episode_id,
            events_considered=len(events),
            hypotheses_text=f"Correlation error: {e}",
        )
    trace = PhaseTrace(
        agent_name="CorrelationAnalyzer",
        started_at=phase_start,
        finished_at=time.time(),
        duration_ms=int((time.time() - phase_start) * 1000),
        output_summary=(
            f"top='{analysis.top_statement}' "
            f"fit={analysis.top_explanatory_fit:.2f}"
            if analysis.top_statement else "no hypothesis"
        ),
    )
    all_phases.append(trace)
    return analysis


# ============================================================================
# Phase 5 — Parallel Investigators
# ============================================================================

async def _run_parallel_investigators(
    hypotheses: list[Hypothesis],
    plans: list[FalsificationPlan],
    network_analysis_text: str,
    session_service: InMemorySessionService,
    all_phases: list,
    on_event=None,
) -> list[InvestigatorVerdict]:
    """Spawn one sub-Investigator per hypothesis, run in parallel, return
    verdicts. Applies the minimum-tool-call guardrail per sub-agent.
    """
    # Cap at MAX_PARALLEL_INVESTIGATORS
    selected_hypotheses = hypotheses[:MAX_PARALLEL_INVESTIGATORS]
    plans_by_id = {p.hypothesis_id: p for p in plans}

    async def run_one(h: Hypothesis) -> tuple[InvestigatorVerdict, list[PhaseTrace]]:
        plan = plans_by_id.get(h.id)
        if plan is None:
            log.warning("No plan for hypothesis %s — skipping", h.id)
            return (
                InvestigatorVerdict(
                    hypothesis_id=h.id,
                    hypothesis_statement=h.statement,
                    verdict="INCONCLUSIVE",
                    reasoning="No falsification plan was generated for this hypothesis.",
                ),
                [],
            )

        agent_name = f"InvestigatorAgent_{h.id}"
        agent = create_investigator_agent(name=agent_name)

        # Build prompt state
        plan_dict = plan.model_dump()
        sub_state: dict[str, Any] = {
            "hypothesis_id": h.id,
            "hypothesis_statement": h.statement,
            "primary_suspect_nf": h.primary_suspect_nf,
            "falsification_plan": json.dumps(plan_dict, indent=2),
            "network_analysis": network_analysis_text,
        }

        question = f"Falsify hypothesis {h.id}: {h.statement}"
        state_after, traces = await _run_phase(
            agent, sub_state, question, session_service, on_event,
        )

        # Parse the verdict
        verdict_raw = state_after.get("investigator_verdict")
        try:
            if isinstance(verdict_raw, str):
                verdict_dict = json.loads(verdict_raw)
            else:
                verdict_dict = verdict_raw or {}
            verdict = InvestigatorVerdict(**verdict_dict)
        except Exception as e:
            log.warning("Failed to parse verdict from %s: %s", agent_name, e)
            verdict = InvestigatorVerdict(
                hypothesis_id=h.id,
                hypothesis_statement=h.statement,
                verdict="INCONCLUSIVE",
                reasoning=f"Failed to parse Investigator output: {e}",
            )

        # Mechanical guardrail: force INCONCLUSIVE if below minimum tool calls
        inv_trace = next(
            (t for t in traces if t.agent_name == agent_name), None,
        )
        tool_call_count = len(inv_trace.tool_calls) if inv_trace else 0
        if tool_call_count < MIN_TOOL_CALLS_PER_INVESTIGATOR:
            log.warning(
                "Sub-Investigator %s made %d tool calls (<%d) — "
                "forcing verdict to INCONCLUSIVE",
                agent_name, tool_call_count, MIN_TOOL_CALLS_PER_INVESTIGATOR,
            )
            verdict = InvestigatorVerdict(
                hypothesis_id=h.id,
                hypothesis_statement=h.statement,
                verdict="INCONCLUSIVE",
                reasoning=(
                    f"Mechanical guardrail: {agent_name} made only "
                    f"{tool_call_count} tool call(s); minimum is "
                    f"{MIN_TOOL_CALLS_PER_INVESTIGATOR}. "
                    "Self-reported output was discarded."
                ),
            )

        return verdict, traces

    # Fan out in parallel
    results = await asyncio.gather(
        *[run_one(h) for h in selected_hypotheses],
        return_exceptions=True,
    )

    verdicts: list[InvestigatorVerdict] = []
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            log.error("Sub-Investigator for %s crashed: %s",
                      selected_hypotheses[i].id, r)
            verdicts.append(InvestigatorVerdict(
                hypothesis_id=selected_hypotheses[i].id,
                hypothesis_statement=selected_hypotheses[i].statement,
                verdict="INCONCLUSIVE",
                reasoning=f"Sub-agent crashed: {r}",
            ))
        else:
            v, traces = r
            verdicts.append(v)
            all_phases.extend(traces)

    return verdicts


# ============================================================================
# Public API
# ============================================================================

async def investigate(
    question: str,
    on_event=None,
    anomaly_window_hint_seconds: int = 300,
    metric_snapshots: Optional[list[dict]] = None,
    observation_window_duration: int = 0,
    seconds_since_observation: int = 0,
    episode_id: Optional[str] = None,
) -> dict:
    """Run the v6 8-phase pipeline.

    Returns a dict matching the v5 contract expected by the chaos framework:
      - diagnosis: str (plain markdown)
      - investigation_trace: dict with phases, total_tokens, etc.
    """
    run_start = time.time()
    episode_id = episode_id or os.environ.get("V6_EPISODE_ID", "v6_unknown")

    log.info("Starting v6 investigation for episode=%s", episode_id)

    session_service = InMemorySessionService()
    state: dict[str, Any] = {
        "episode_id": episode_id,
        "question": question,
        "anomaly_window_hint_seconds": anomaly_window_hint_seconds,
        "observation_window_duration": observation_window_duration,
        "seconds_since_observation": seconds_since_observation,
        "event_lookback_seconds": max(300, observation_window_duration),
        "anomaly_window_hint_seconds": anomaly_window_hint_seconds,
    }

    all_phases: list[PhaseTrace] = []

    # -------- Phase 0: Anomaly screener --------
    await _phase0_anomaly_screener(state, metric_snapshots, all_phases)

    # -------- Phase 1: Event aggregator --------
    events, rendered_events = _phase1_event_aggregator(episode_id, all_phases)
    state["fired_events"] = rendered_events
    state["fired_event_count"] = len(events)

    # -------- Phase 2: CorrelationAnalyzer (Python, feeds NA) --------
    correlation = _phase2_correlation_analyzer(events, episode_id, all_phases)
    state["correlation_analysis"] = correlation.hypotheses_text

    # -------- Phase 3: NetworkAnalyst --------
    try:
        state, traces = await _run_phase(
            create_network_analyst(), state, question, session_service, on_event,
        )
        all_phases.extend(traces)
        _accumulate_phase_traces(state, traces)
    except Exception as e:
        log.error("NetworkAnalyst failed: %s", e, exc_info=True)
        state["network_analysis"] = json.dumps({
            "summary": f"NA failed: {e}",
            "layer_status": {},
            "hypotheses": [],
        })

    # Parse NA output into typed model
    na_report = _parse_network_analysis(state.get("network_analysis"))
    hypotheses = _rank_and_cap_hypotheses(na_report.hypotheses)
    log.info("NA produced %d hypotheses; investigating top %d",
             len(na_report.hypotheses), len(hypotheses))

    # Preserve the NA report in structured form for the episode recorder.
    # The state["network_analysis"] slot is about to be overwritten with
    # markdown text so downstream LLM prompts (IG, Investigator, Synthesis)
    # can read a prompt-friendly rendering. The recorder needs the dict
    # form to render a proper ranked-hypotheses table — otherwise it falls
    # back to a truncated code-block dump of the markdown.
    na_for_report = na_report.model_copy(update={"hypotheses": hypotheses})
    state["network_analysis_structured"] = na_for_report.model_dump(mode="json")

    if not hypotheses:
        log.warning("No testable hypotheses from NA — skipping Investigator phase")
        state["diagnosis"] = _render_no_hypotheses_diagnosis(na_report)
        return _build_result(state, all_phases, run_start)

    # -------- Phase 4: InstructionGenerator --------
    # Render hypotheses back into state as a prompt-friendly structure
    state["network_analysis"] = _pretty_print_na_report(na_report, hypotheses)
    try:
        state, traces = await _run_phase(
            create_instruction_generator(), state, question,
            session_service, on_event,
        )
        all_phases.extend(traces)
        _accumulate_phase_traces(state, traces)
    except Exception as e:
        log.error("InstructionGenerator failed: %s", e, exc_info=True)
        state["falsification_plan_set"] = json.dumps({"plans": []})

    plan_set = _parse_plan_set(state.get("falsification_plan_set"))

    # -------- Phase 5: Parallel Investigators --------
    verdicts = await _run_parallel_investigators(
        hypotheses, plan_set.plans,
        network_analysis_text=state.get("network_analysis", ""),
        session_service=session_service,
        all_phases=all_phases,
        on_event=on_event,
    )
    state["investigator_verdicts"] = json.dumps(
        [v.model_dump() for v in verdicts], indent=2,
    )

    # -------- Phase 6: Evidence Validator --------
    phase_start = time.time()
    phase_trace_dicts = [t.model_dump(mode="json") for t in all_phases]
    investigator_outputs = [
        {**v.model_dump(), "agent_name": f"InvestigatorAgent_{v.hypothesis_id}"}
        for v in verdicts
    ]
    ev_result = validate_evidence(phase_trace_dicts, investigator_outputs)
    state["evidence_validation"] = json.dumps(ev_result.to_dict(), indent=2)
    ev_trace = PhaseTrace(
        agent_name="EvidenceValidator",
        started_at=phase_start,
        finished_at=time.time(),
        duration_ms=int((time.time() - phase_start) * 1000),
        output_summary=(
            f"overall={ev_result.overall_verdict}, "
            f"confidence={ev_result.overall_confidence}"
        ),
    )
    all_phases.append(ev_trace)

    # -------- Phase 7: Synthesis --------
    try:
        state, traces = await _run_phase(
            create_synthesis_agent(), state, question,
            session_service, on_event,
        )
        all_phases.extend(traces)
        _accumulate_phase_traces(state, traces)
    except Exception as e:
        log.error("Synthesis failed: %s", e, exc_info=True)
        state["diagnosis"] = f"Synthesis failed: {e}"

    return _build_result(state, all_phases, run_start)


# ============================================================================
# Helpers
# ============================================================================

def _empty_na_report(reason: str) -> NetworkAnalystReport:
    """Sentinel "NA produced nothing usable" value the orchestrator can
    pass downstream when NA fails. The live schema now requires
    `summary` to be non-empty and `hypotheses` to have at least 1
    entry, so a plain `NetworkAnalystReport(summary="...")` with no
    hypotheses no longer instantiates via normal validation. Use
    `model_construct` to bypass — downstream code reads `.hypotheses`
    as `[]`, which the orchestrator already handles by skipping
    Phase 4 with the "No testable hypotheses" branch.
    """
    return NetworkAnalystReport.model_construct(
        summary=reason, layer_status={}, hypotheses=[],
    )


def _parse_network_analysis(raw: Any) -> NetworkAnalystReport:
    """Parse the NA's structured output into a NetworkAnalystReport.

    Returns a validation-bypassed empty sentinel when the input is
    missing or invalid. Validation can fail under the tightened
    schema (min_length=1 hypotheses, _KnownNF Literal, etc.) when
    Gemini's `tools + output_schema` short-circuit produces malformed
    output — the same pathology that caused the Apr-28 p_cscf_latency
    regression. Downstream sees `.hypotheses == []` and skips Phase 4.
    """
    if raw is None:
        return _empty_na_report("NA produced no output")
    try:
        if isinstance(raw, str):
            data = json.loads(raw)
        else:
            data = raw
        return NetworkAnalystReport(**data)
    except Exception as e:
        log.warning("Could not parse NA output: %s", e)
        return _empty_na_report(f"NA output unparseable: {e}")


def _empty_plan_set() -> FalsificationPlanSet:
    """Sentinel "no plan" value the orchestrator can pass to Phase 5
    when IG failed. The live schema now requires `plans` to have at
    least 1 entry, which would block `FalsificationPlanSet(plans=[])`
    from instantiating via normal validation — use model_construct to
    bypass. Downstream readers see `.plans == []` and skip.
    """
    return FalsificationPlanSet.model_construct(plans=[])


def _parse_plan_set(raw: Any) -> FalsificationPlanSet:
    """Parse the IG's structured output into a FalsificationPlanSet.

    Returns a validation-bypassed empty sentinel when the input is
    missing/invalid. The orchestrator then passes `.plans == []` to
    Phase 5, which turns every hypothesis into an INCONCLUSIVE verdict
    with "no falsification plan was generated." Downstream agents and
    the recorder both handle that case cleanly. The tightened schema
    still guarantees that any value IG *does* successfully produce is
    well-formed.
    """
    if raw is None:
        return _empty_plan_set()
    try:
        if isinstance(raw, str):
            data = json.loads(raw)
        else:
            data = raw
        return FalsificationPlanSet(**data)
    except Exception as e:
        log.warning("Could not parse IG output: %s", e)
        return _empty_plan_set()


def _rank_and_cap_hypotheses(hypotheses: list[Hypothesis]) -> list[Hypothesis]:
    """Apply ranking rule: drop untestable, sort, cap at MAX_PARALLEL_INVESTIGATORS."""
    testable = [h for h in hypotheses if h.falsification_probes]
    specificity_weight = {"specific": 3, "moderate": 2, "vague": 1}
    testable.sort(
        key=lambda h: (
            -h.explanatory_fit,
            -len(h.falsification_probes),
            -specificity_weight.get(h.specificity, 2),
        )
    )
    return testable[:MAX_PARALLEL_INVESTIGATORS]


def _pretty_print_na_report(
    na: NetworkAnalystReport, hypotheses: list[Hypothesis],
) -> str:
    """Render the NA report as markdown for prompt injection to downstream phases."""
    lines = [f"**Summary:** {na.summary}", ""]
    if na.layer_status:
        lines.append("**Layer status:**")
        for layer, status in na.layer_status.items():
            lines.append(f"  - {layer}: {status.rating} — {status.note}")
        lines.append("")
    lines.append(f"**Top {len(hypotheses)} hypotheses (ranked, testable only):**")
    for h in hypotheses:
        lines.append(f"- `{h.id}` (fit={h.explanatory_fit:.2f}, "
                     f"nf={h.primary_suspect_nf}, "
                     f"specificity={h.specificity}):")
        lines.append(f"    statement: {h.statement}")
        lines.append(f"    supporting events: {', '.join(h.supporting_events)}")
        lines.append(f"    falsification probes:")
        for p in h.falsification_probes:
            lines.append(f"      - {p}")
    return "\n".join(lines)


def _render_no_hypotheses_diagnosis(na: NetworkAnalystReport) -> str:
    return f"""### causes
- **summary**: {na.summary}
- **timeline**: []
- **root_cause**: Unknown — NetworkAnalyst produced no testable hypotheses.
- **affected_components**: []
- **recommendation**: Manual investigation required. Re-run when more events are available.
- **confidence**: low
- **explanation**: The v6 pipeline received insufficient evidence to form testable hypotheses. Either no events fired during the observation window or none of the NA's candidate hypotheses had identifiable falsification probes. Review the anomaly screener output and event store directly.
"""


def _build_result(
    state: dict, all_phases: list[PhaseTrace], run_start: float,
) -> dict:
    run_end = time.time()
    total = TokenBreakdown()
    for p in all_phases:
        total.prompt += p.tokens.prompt
        total.completion += p.tokens.completion
        total.thinking += p.tokens.thinking
        total.total += p.tokens.total

    invocation_order = [p.agent_name for p in all_phases]
    trace = InvestigationTrace(
        question=state.get("question", "")[:200],
        started_at=run_start,
        finished_at=run_end,
        duration_ms=int((run_end - run_start) * 1000),
        total_tokens=total,
        phases=all_phases,
        invocation_chain=invocation_order,
    )
    # Surface per-phase outputs at the top level so the chaos framework's
    # EpisodeRecorder can render them. The recorder's template reads these
    # keys by name (inherited from v5). We map v6's structure onto those
    # v5-era names:
    #   - anomaly_report        ← Phase 0
    #   - pattern_match         ← Phase 2 (correlation analyzer output —
    #                              analogous role: produces hypotheses from
    #                              pre-agent structured reasoning)
    #   - network_analysis      ← Phase 3 (NA's ranked hypothesis report)
    #   - investigation_instruction ← Phase 4 (falsification plan set)
    #   - investigation         ← Phase 5 (aggregated sub-Investigator verdicts)
    #   - evidence_validation   ← Phase 6
    anomaly_report = state.get("anomaly_report", "")
    # Prefer the structured NA dict for the recorder. The markdown form under
    # `network_analysis` exists only so downstream LLM prompts have a
    # prompt-friendly rendering; rendering it via the recorder yields a
    # truncated code-block dump.
    na_structured = state.get("network_analysis_structured")
    if na_structured is not None:
        network_analysis = _prettify_json_state(na_structured)
    else:
        network_analysis = _prettify_json_state(state.get("network_analysis"))
    correlation_analysis = state.get("correlation_analysis", "")
    plan_set = _prettify_json_state(state.get("falsification_plan_set"))
    investigator_verdicts = _prettify_json_state(state.get("investigator_verdicts"))
    evidence_validation = _prettify_json_state(state.get("evidence_validation"))

    return {
        "diagnosis": state.get("diagnosis", ""),
        "investigation_trace": trace.model_dump(mode="json"),
        "total_tokens": total.total,
        "state_keys": sorted(state.keys()),
        # ─── v6 per-phase outputs for the chaos EpisodeRecorder ─────────
        # The recorder's v6 layout (see recorder._render_v6_pipeline) reads
        # these by name. Kept as v6-native labels, not v5 synonyms.
        "anomaly_report": anomaly_report,                 # Phase 0
        "fired_events": state.get("fired_events", ""),    # Phase 1
        "fired_event_count": state.get("fired_event_count", 0),
        "correlation_analysis": correlation_analysis,     # Phase 2
        "network_analysis": network_analysis,             # Phase 3
        "investigation_instruction": plan_set,            # Phase 4
        "investigation": investigator_verdicts,           # Phase 5
        "evidence_validation": evidence_validation,       # Phase 6
        # Synthesis output (Phase 7) = `diagnosis` above.
    }


def _prettify_json_state(raw: Any) -> str:
    """Render a state value as pretty-printed text for the episode recorder.

    State values can be:
      - dicts (Pydantic .model_dump() output from structured agents)
      - JSON strings (ADK sometimes stores structured output as strings)
      - plain strings (Synthesis, manual renderings)
      - None (phase didn't run)
    """
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    try:
        return json.dumps(raw, indent=2, default=str)
    except Exception:
        return str(raw)
