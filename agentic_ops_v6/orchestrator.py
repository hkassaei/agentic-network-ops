"""v6 orchestrator — 9-phase pipeline with parallel per-hypothesis Investigators.

Pipeline:
  Phase 0    AnomalyScreener           (ML, no LLM)
  Phase 1    EventAggregator           (reads fired events from store)
  Phase 2    CorrelationAnalyzer       (runs correlation engine, feeds NA)
  Phase 3    NetworkAnalyst            (ranked hypotheses over KB + events + correlation)
  Phase 4    InstructionGenerator      (one falsification plan per hypothesis)
  Phase 5    Investigator × N          (parallel sub-agents, one per hypothesis)
  Phase 6.5  CandidatePool + bounded   (Decision E aggregator; re-investigates the top
             re-investigation            promoted suspect when the verdict tree has zero
                                         NOT_DISPROVEN survivors)
  Phase 6.6  EvidenceValidator         (per-sub-investigator citation check; PR 5.5a
                                         moved this AFTER 6.5 so it covers the
                                         re-investigation Investigator's trace)
  Phase 7    Synthesis                 (aggregates N verdicts into NOC diagnosis)

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

from .guardrails.empty_output import (
    IG_OUTPUT_KEY as _IG_OUTPUT_KEY,
    INVESTIGATOR_OUTPUT_KEY as _INVESTIGATOR_OUTPUT_KEY,
    NA_OUTPUT_KEY as _NA_OUTPUT_KEY,
    SYNTHESIS_OUTPUT_KEY as _SYNTHESIS_OUTPUT_KEY,
    ig_output_present as _ig_output_present,
    output_present as _output_present,
    run_ig_with_retry as _ig_retry_impl,
    run_phase_with_empty_output_retry as _empty_output_retry_impl,
)
from .guardrails.evidence_citations import validate_evidence
from .guardrails.ig_validator import audit_fanout, lint_ig_plan
from .guardrails.investigator_minimum import (
    MIN_TOOL_CALLS_PER_INVESTIGATOR,
    apply_min_tool_call_guardrail,
)
from .guardrails.na_linter import lint_na_hypotheses
from .guardrails.na_ranking import (
    get_known_nfs,
    lint_na_ranking_coverage,
)
from .guardrails.runner import GUARDRAIL_REASON_KEY, run_phase_with_guardrail
from .guardrails.confidence_cap import cap_synthesis_confidence
from .guardrails.synthesis_pool import (
    CandidatePool,
    compute_candidate_pool,
    lint_synthesis_pool_membership,
)
from .guardrails.base import GuardrailVerdict
from .models import (
    CorrelationAnalysis,
    DiagnosisReport,
    FalsificationPlan,
    FalsificationPlanSet,
    Hypothesis,
    InvestigatorVerdict,
    NetworkAnalystReport,
)
from .subagents.correlation_analyzer import analyze_correlations
from .subagents.event_aggregator import aggregate_episode_events
from .subagents.instruction_generator import create_instruction_generator
from .subagents.investigator import create_investigator_agent
from .subagents.network_analyst import create_network_analyst
from .subagents.synthesis import create_synthesis_agent

log = logging.getLogger("v6.orchestrator")


MAX_PARALLEL_INVESTIGATORS = 3


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


# The output-key constants and the empty-output retry helpers were
# extracted to `guardrails/empty_output.py` (see import block above).
# Thin pass-through wrappers below preserve the orchestrator's
# pre-extraction call signatures so test_ig_retry_guard.py and other
# call sites continue to work without modification.


async def _run_phase_with_empty_output_retry(
    agent_factory,
    state: dict[str, Any],
    question: str,
    session_service: InMemorySessionService,
    on_event,
    output_key: str,
    phase_label: str,
) -> tuple[dict[str, Any], list[PhaseTrace], bool]:
    """Pass-through to `guardrails.empty_output.run_phase_with_empty_output_retry`.

    Injects this module's `_run_phase` so the guardrail module stays
    free of orchestrator imports.
    """
    return await _empty_output_retry_impl(
        agent_factory=agent_factory,
        state=state,
        question=question,
        session_service=session_service,
        on_event=on_event,
        output_key=output_key,
        phase_label=phase_label,
        run_phase=_run_phase,
    )


async def _run_ig_with_retry(
    state: dict[str, Any],
    question: str,
    session_service: InMemorySessionService,
    on_event,
    all_phases: list[PhaseTrace],
) -> tuple[dict[str, Any], FalsificationPlanSet]:
    """Pass-through to `guardrails.empty_output.run_ig_with_retry`.

    Injects the orchestrator-side dependencies (`_run_phase`, the
    trace accumulator, the IG factory, the plan-set parser, and the
    empty-plan sentinel) so the guardrail module stays decoupled.
    """
    return await _ig_retry_impl(
        state=state,
        question=question,
        session_service=session_service,
        on_event=on_event,
        all_phases=all_phases,
        run_phase=_run_phase,
        accumulate_traces=_accumulate_phase_traces,
        create_instruction_generator=create_instruction_generator,
        parse_plan_set=_parse_plan_set,
        empty_plan_set=_empty_plan_set,
    )


# ============================================================================
# Phase 0 — AnomalyScreener
# ============================================================================

async def _phase0_anomaly_screener(
    state: dict,
    metric_snapshots: Optional[list[dict]],
    all_phases: list,
) -> None:
    """Run the anomaly screener. Same logic as v5; outputs `anomaly_report`.

    Also captures the canonical anomaly-window timestamps that downstream
    phases use to anchor their queries (per ADR
    `dealing_with_temporality_3.md`):
      * `state["anomaly_window_start_ts"]` — earliest snapshot timestamp
        in the observation window the screener consumed.
      * `state["anomaly_window_end_ts"]` — latest snapshot timestamp.
      * `state["anomaly_screener_snapshot_ts"]` — timestamp of the
        specific snapshot that produced the highest anomaly score
        (the canonical "what time should phases ask about?" value).

    All three are floats (seconds since epoch). Absent from state if
    Phase 0 produced no scoring snapshots (e.g. no trained model).
    """
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
            # No real timestamp available for the synthetic single-snapshot
            # fallback. Use phase0_start so downstream queries have *some*
            # anchor; worst case it's slightly stale relative to the actual
            # metric collection moment.
            snapshots = [{"_parsed": raw, "_timestamp": phase0_start}]

        pp = MetricPreprocessor()
        best_report = None
        # Track the timestamp of the snapshot that produced `best_report`
        # — this becomes `anomaly_screener_snapshot_ts`. Initialized to
        # None; set the first time a snapshot scores.
        best_snap_ts: Optional[float] = None
        # Track the time-extent of the snapshots actually consumed (skipping
        # the first 6 warm-up samples — see the rate-window comment below).
        scored_snap_timestamps: list[float] = []
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
            # i < 6 is rate-window warmup (the preprocessor needs at least
            # 6 samples to compute sliding-window rates; earlier ones
            # produce empty feature dicts).
            if i >= 6 and features:
                report = screener.score(features, liveness=pp.liveness_signals())
                if isinstance(snap_ts, (int, float)):
                    scored_snap_timestamps.append(float(snap_ts))
                if best_report is None or report.overall_score > best_report.overall_score:
                    best_report = report
                    if isinstance(snap_ts, (int, float)):
                        best_snap_ts = float(snap_ts)

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

            # Anomaly-window timestamps (ADR: dealing_with_temporality_3.md
            # Layer 1). These are the canonical reference for any
            # downstream phase asking "what time should I query?". For
            # now they're just stored in state — Layer 2 of the same ADR
            # will start consuming them in time-anchored Prometheus
            # queries; Layer 3 in snapshot-replay; Layer 4 in agent
            # prompts.
            if scored_snap_timestamps:
                state["anomaly_window_start_ts"] = min(scored_snap_timestamps)
                state["anomaly_window_end_ts"] = max(scored_snap_timestamps)
            if best_snap_ts is not None:
                state["anomaly_screener_snapshot_ts"] = best_snap_ts
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
    anomaly_window_start_ts: float = 0.0,
    anomaly_window_end_ts: float = 0.0,
    anomaly_screener_snapshot_ts: float = 0.0,
    on_event=None,
) -> list[InvestigatorVerdict]:
    """Spawn one sub-Investigator per hypothesis, run in parallel, return
    verdicts. Applies the minimum-tool-call guardrail per sub-agent.

    The `anomaly_*_ts` timestamps come from Phase 0 and are forwarded
    into each sub-Investigator's session state so the prompt's
    `{anomaly_screener_snapshot_ts}` template (per ADR
    `dealing_with_temporality_3.md`) resolves. 0.0 sentinel = "no
    anchor available; fall back to live mode" (the prompt instructs
    the agent to drop `at_time_ts` in that case).
    """
    # Cap at MAX_PARALLEL_INVESTIGATORS
    selected_hypotheses = hypotheses[:MAX_PARALLEL_INVESTIGATORS]
    plans_by_id = {p.hypothesis_id: p for p in plans}

    # Fan-out audit — surfaces silent plan-drops and hypothesis/plan NF
    # mismatches. The structural check lives in
    # `guardrails/ig_validator.py`; the orchestrator surfaces the
    # findings via log warnings (preserved verbatim for backward
    # compat with run-log consumers) and a synthetic PhaseTrace below.
    audit = audit_fanout(selected_hypotheses, plans)

    log.info(
        "Phase 5 fan-out audit — %d NA hypothesis(es), %d IG plan(s); "
        "running %d sub-Investigator(s).",
        len(selected_hypotheses), len(plans), len(selected_hypotheses),
    )
    if audit.hyps_without_plan:
        log.warning(
            "Phase 5 fan-out: %d hypothesis(es) have no matching plan and "
            "will return INCONCLUSIVE: %s",
            len(audit.hyps_without_plan),
            [h.id for h in audit.hyps_without_plan],
        )
    if audit.plans_without_hyp:
        log.warning(
            "Phase 5 fan-out: %d IG plan(s) have no matching NA hypothesis "
            "and were SILENTLY DROPPED: %s. This usually means IG produced "
            "plans for hypothesis ids that NA did not emit (e.g., copied "
            "ids from the correlation engine's output instead of NA's).",
            len(audit.plans_without_hyp), audit.plans_without_hyp,
        )
    for hid, hyp_nf, plan_nf in audit.nf_mismatches:
        log.warning(
            "Phase 5 fan-out: hypothesis %s names primary_suspect_nf=%s but "
            "the matching plan targets primary_suspect_nf=%s. The plan's "
            "probes will run against %s while the hypothesis is about %s.",
            hid, hyp_nf, plan_nf, plan_nf, hyp_nf,
        )

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

        # Build prompt state
        plan_dict = plan.model_dump()
        sub_state: dict[str, Any] = {
            "hypothesis_id": h.id,
            "hypothesis_statement": h.statement,
            "primary_suspect_nf": h.primary_suspect_nf,
            "falsification_plan": json.dumps(plan_dict, indent=2),
            "network_analysis": network_analysis_text,
            "anomaly_window_start_ts": anomaly_window_start_ts,
            "anomaly_window_end_ts": anomaly_window_end_ts,
            "anomaly_screener_snapshot_ts": anomaly_screener_snapshot_ts,
        }

        question = f"Falsify hypothesis {h.id}: {h.statement}"

        # Same empty-output silent-bail can hit a sub-Investigator. The
        # existing parse-error path below would catch it as a JSON
        # parse failure and force INCONCLUSIVE — but only after
        # consuming the run with no retry. With the generic retry
        # guard, we get a second chance to produce a verdict before
        # falling through.
        state_after, traces, _success = await _run_phase_with_empty_output_retry(
            agent_factory=lambda: create_investigator_agent(name=agent_name),
            state=sub_state,
            question=question,
            session_service=session_service,
            on_event=on_event,
            output_key=_INVESTIGATOR_OUTPUT_KEY,
            phase_label=f"Phase 5 {agent_name}",
        )

        # Parse the verdict
        verdict_raw = state_after.get(_INVESTIGATOR_OUTPUT_KEY)
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

        # Mechanical guardrail: force INCONCLUSIVE if below minimum
        # tool calls. Lives in `guardrails/investigator_minimum.py`.
        #
        # `traces` may contain MULTIPLE PhaseTrace entries with the same
        # agent_name when the empty-output retry kicked in (one per
        # attempt). We aggregate tool counts across all matching traces
        # so a retry-then-succeed path correctly counts the successful
        # attempt's probes — pre-PR-9.5 the `next(...)` form returned
        # the FIRST matching trace (always the failed-empty attempt
        # when a retry happened), forcing INCONCLUSIVE despite the
        # retry's successful probes (run_20260501_042127_call_quality_degradation
        # h1 made 0 calls on attempt 1 + 3 calls on attempt 2 → was
        # incorrectly forced INCONCLUSIVE).
        tool_call_count = sum(
            len(t.tool_calls)
            for t in traces
            if t.agent_name == agent_name
        )
        verdict = apply_min_tool_call_guardrail(
            verdict,
            agent_name=agent_name,
            tool_call_count=tool_call_count,
            hypothesis_id=h.id,
            hypothesis_statement=h.statement,
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

    # Surface the fan-out audit into the recorded report. A PhaseTrace
    # with a synthetic agent_name preserves the audit alongside the
    # other phase entries the recorder iterates over. Empty/clean
    # audits are still recorded (output_summary="all matched") so the
    # absence of a warning in a report is meaningful.
    audit_trace = PhaseTrace(
        agent_name="Phase5FanOutAudit",
        started_at=time.time(),
        finished_at=time.time(),
        duration_ms=0,
        output_summary=audit.render_summary(),
    )
    all_phases.append(audit_trace)

    return verdicts


# ============================================================================
# Phase 6.5 — Bounded re-investigation (Decision E, PR 5)
# ============================================================================

# Hard cap on per-scenario re-investigation cycles. The ADR requires this
# to be bounded so the candidate-pool path cannot loop indefinitely on a
# scenario whose alt_suspect chain keeps re-promoting new NFs.
MAX_REINVESTIGATION_CYCLES = 1


async def _run_bounded_reinvestigation(
    promoted_nf: str,
    original_hypotheses: list[Hypothesis],
    state: dict[str, Any],
    question: str,
    session_service: InMemorySessionService,
    on_event,
    all_phases: list[PhaseTrace],
) -> InvestigatorVerdict:
    """Run one extra IG → Investigator cycle on a promoted-suspect NF.

    Triggered by Decision E's candidate-pool aggregator when the
    verdict tree has zero NOT_DISPROVEN survivors but ≥1 alt_suspect
    crossed the corroboration threshold. Goal: produce a structurally-
    clean NOT_DISPROVEN (or DISPROVEN) verdict on the promoted NF so
    Synthesis can ratify it with calibrated confidence rather than
    inferring it from `alternative_suspects` prose.

    The re-investigation reuses every existing safeguard:
      * Decision A's lint_ig_plan via run_phase_with_guardrail
      * Empty-output retry on both IG and Investigator
      * Minimum-tool-call check on the Investigator

    Bounded by MAX_REINVESTIGATION_CYCLES at the call site.

    The synthetic Hypothesis built here uses the clean
    `<NF> is the source of <observable>` shape — same shape Decision D
    teaches NA via shape hint. Bypasses Pydantic validation
    (model_construct) only because the schema requires
    falsification_probes >=1 and we hand a generic seed; the IG agent
    re-derives concrete probes from the hypothesis text.
    """
    log.info(
        "Decision E — running bounded re-investigation on promoted "
        "suspect '%s' (no NOT_DISPROVEN survivors in original verdict tree)",
        promoted_nf,
    )

    # Construct a synthetic Hypothesis. The statement follows the
    # Decision-D-clean shape so downstream agents inherit the same
    # interpretation discipline.
    synthetic_id = f"h_promoted_{promoted_nf}"
    synthetic_statement = (
        f"{promoted_nf} is the source of the anomaly named in the "
        f"alternative_suspects of the original verdict tree."
    )
    # Use model_construct to bypass falsification_probes min_length=1.
    # IG will generate the actual probes from the statement.
    promoted_hypothesis = Hypothesis.model_construct(
        id=synthetic_id,
        statement=synthetic_statement,
        primary_suspect_nf=promoted_nf,
        supporting_events=[],
        explanatory_fit=0.85,
        falsification_probes=["<promoted suspect — IG to design probes>"],
        specificity="specific",
    )

    # Build a minimal NetworkAnalystReport for IG to read.
    synthetic_na = NetworkAnalystReport.model_construct(
        summary=(
            f"Re-investigation on promoted alt-suspect '{promoted_nf}'. "
            "Original verdict tree had zero NOT_DISPROVEN survivors but "
            "this NF was named in DISPROVEN verdicts' alternative_suspects "
            "with sufficient corroboration to warrant direct investigation."
        ),
        layer_status={},
        hypotheses=[promoted_hypothesis],
    )
    rendered_na = _pretty_print_na_report(synthetic_na, [promoted_hypothesis])

    # Build a fresh state for the IG sub-call. We carry forward the
    # correlation/events context so IG can still walk the KB if needed,
    # but replace network_analysis with the single-hypothesis rendering.
    ig_state = dict(state)
    ig_state["network_analysis"] = rendered_na
    # Reset the rejection-reason on each new phase entry so the
    # template substitution starts clean.
    ig_state[GUARDRAIL_REASON_KEY] = ""
    # Drop the previous IG output_key so empty-output detection works
    # cleanly on this fresh attempt.
    ig_state.pop(_IG_OUTPUT_KEY, None)

    ig_state, ig_traces, ig_success, plan_set = await run_phase_with_guardrail(
        agent_factory=create_instruction_generator,
        state=ig_state,
        question=question,
        session_service=session_service,
        on_event=on_event,
        output_key=_IG_OUTPUT_KEY,
        phase_label="Phase 6.5 Reinvestigation IG",
        run_phase=_run_phase,
        parser=_parse_plan_set,
        guardrail=lint_ig_plan,
        max_resamples=1,
        on_guardrail_exhausted="accept",
    )
    all_phases.extend(ig_traces)

    if not ig_success or not plan_set or not plan_set.plans:
        log.warning(
            "Decision E — IG could not produce a plan for promoted suspect "
            "'%s'; returning INCONCLUSIVE re-investigation verdict.",
            promoted_nf,
        )
        return InvestigatorVerdict(
            hypothesis_id=synthetic_id,
            hypothesis_statement=synthetic_statement,
            verdict="INCONCLUSIVE",
            reasoning=(
                f"Re-investigation on promoted suspect '{promoted_nf}' "
                "failed at the InstructionGenerator step (empty output or "
                "unparseable plan). No probes were run."
            ),
        )

    plan = plan_set.plans[0]
    agent_name = f"InvestigatorAgent_{synthetic_id}"

    # Build the Investigator sub-state using the same pattern as the
    # Phase 5 fan-out helper.
    sub_state: dict[str, Any] = {
        "hypothesis_id": synthetic_id,
        "hypothesis_statement": synthetic_statement,
        "primary_suspect_nf": promoted_nf,
        "falsification_plan": json.dumps(plan.model_dump(), indent=2),
        "network_analysis": rendered_na,
        "anomaly_window_start_ts": float(state.get("anomaly_window_start_ts", 0.0) or 0.0),
        "anomaly_window_end_ts": float(state.get("anomaly_window_end_ts", 0.0) or 0.0),
        "anomaly_screener_snapshot_ts": float(state.get("anomaly_screener_snapshot_ts", 0.0) or 0.0),
    }

    sub_state, inv_traces, _ = await _run_phase_with_empty_output_retry(
        agent_factory=lambda: create_investigator_agent(name=agent_name),
        state=sub_state,
        question=f"Falsify hypothesis {synthetic_id}: {synthetic_statement}",
        session_service=session_service,
        on_event=on_event,
        output_key=_INVESTIGATOR_OUTPUT_KEY,
        phase_label=f"Phase 6.5 {agent_name}",
    )
    all_phases.extend(inv_traces)

    # Parse verdict (mirrors run_one in _run_parallel_investigators).
    verdict_raw = sub_state.get(_INVESTIGATOR_OUTPUT_KEY)
    try:
        if isinstance(verdict_raw, str):
            verdict_dict = json.loads(verdict_raw)
        else:
            verdict_dict = verdict_raw or {}
        verdict = InvestigatorVerdict(**verdict_dict)
    except Exception as e:
        log.warning(
            "Decision E — failed to parse re-investigation verdict from %s: %s",
            agent_name, e,
        )
        verdict = InvestigatorVerdict(
            hypothesis_id=synthetic_id,
            hypothesis_statement=synthetic_statement,
            verdict="INCONCLUSIVE",
            reasoning=f"Failed to parse Investigator output: {e}",
        )

    # Min-tool-call guardrail (same as Phase 5 fan-out). Aggregate
    # tool counts across all matching traces — see the comment in
    # `run_one` above for the retry-aggregation rationale (PR 9.5 fix).
    tool_call_count = sum(
        len(t.tool_calls)
        for t in inv_traces
        if t.agent_name == agent_name
    )
    verdict = apply_min_tool_call_guardrail(
        verdict,
        agent_name=agent_name,
        tool_call_count=tool_call_count,
        hypothesis_id=synthetic_id,
        hypothesis_statement=synthetic_statement,
    )

    log.info(
        "Decision E — re-investigation on '%s' returned verdict=%s",
        promoted_nf, verdict.verdict,
    )
    return verdict


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

    # Make observation snapshots available to time-aware tools via the
    # snapshot-replay contextvar (ADR `dealing_with_temporality_3.md`
    # Layer 3). Tools that take an `at_time_ts` parameter can call
    # `get_observation_snapshots()` to fetch the recorded history,
    # find the closest snapshot to the requested time, and read NF
    # state historically — without us having to thread the snapshot
    # list through every tool's signature.
    from agentic_ops_common.tools.snapshot_replay import set_observation_snapshots
    set_observation_snapshots(metric_snapshots)

    session_service = InMemorySessionService()
    state: dict[str, Any] = {
        "episode_id": episode_id,
        "question": question,
        "anomaly_window_hint_seconds": anomaly_window_hint_seconds,
        "observation_window_duration": observation_window_duration,
        "seconds_since_observation": seconds_since_observation,
        "event_lookback_seconds": max(300, observation_window_duration),
        "anomaly_window_hint_seconds": anomaly_window_hint_seconds,
        # Anomaly-window timestamps initialized to 0.0 sentinel so ADK
        # template substitution in agent prompts (notably the
        # Investigator's `{anomaly_screener_snapshot_ts}` reference)
        # always resolves. Phase 0 will overwrite with real values
        # when it finds a scoring snapshot. The Investigator prompt
        # treats 0.0 as "no anchor available, fall back to live mode".
        # ADR: dealing_with_temporality_3.md Layer 1.
        "anomaly_window_start_ts": 0.0,
        "anomaly_window_end_ts": 0.0,
        "anomaly_screener_snapshot_ts": 0.0,
        # Guardrail rejection reason — empty on first attempt of every
        # phase, populated by `run_phase_with_guardrail` on resample.
        # Initialized here so ADK template substitution (notably NA's
        # `{guardrail_rejection_reason}` reference per Decision D) always
        # resolves to a string instead of failing on a missing key.
        GUARDRAIL_REASON_KEY: "",
        # Candidate pool (Decision E, PR 5) — empty on first run, populated
        # by Phase 6.5 between EvidenceValidator and Synthesis. Initialized
        # here so the Synthesis prompt's `{candidate_pool}` template
        # always resolves.
        "candidate_pool": "",
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
    # Two layered guards run on NA's output:
    #
    #   (a) Empty-output retry (existing). Run 20260430_020337
    #       scored 15% because NA made 7 tool calls and 7 LLM calls but
    #       emitted nothing — ADK silently bailed on the empty final
    #       response and Phase 4 ran with no `network_analysis` to
    #       read. The retry helper detects this and resamples once.
    #       On both-attempts-empty, we write a phase-appropriate
    #       sentinel that downstream parsing handles cleanly (empty
    #       `hypotheses` list → "no testable hypotheses" diagnosis).
    #
    #   (b) Hypothesis-statement linter (Decision D — PR 2). Rejects
    #       NA reports whose hypothesis statements contain
    #       mechanism-scoping language ("internal fault", "due to
    #       overload", "not forwarding", etc.). On REJECT the runner
    #       resamples NA once with a per-hypothesis bad/good example
    #       correction injected via `{guardrail_rejection_reason}`.
    #
    #   (c) Ranking-coverage linter (Decision H — PR 9). For every
    #       Phase-0 anomaly flag classified as `direct` (the metric
    #       measures the named NF's own state), the named NF must
    #       appear as `primary_suspect_nf` of a hypothesis with
    #       fit ≥ 0.7 OR be named in `summary` with explicit demotion
    #       reasoning. Closes the wrong-NF-ranking failure exposed by
    #       `run_20260501_032822_call_quality_degradation`.
    #
    #   Policy on second still-rejected output is "accept" (not
    #   "fail") — a slightly mis-ranked NA report is worse than a
    #   clean one but better than no NA report. The runner writes a
    #   structured warning to `state["guardrail_warnings"]` and a
    #   synthetic PhaseTrace so the recorder surfaces the outcome.
    #
    # The two NA-side guardrails are composed: D runs first; H runs
    # only on D's PASS path.
    _known_nfs = get_known_nfs()
    # KB is loaded best-effort here so Decision H can read
    # `MetricEntry.flag_kind` overrides; on KB load failure the
    # classifier falls back to its naming-pattern heuristic.
    try:
        _ranking_kb = load_kb()
    except Exception as _e:
        log.warning(
            "Decision H — KB load failed (%s); ranking linter will "
            "fall back to naming-pattern heuristic only.",
            _e,
        )
        _ranking_kb = None

    def _na_combined_guardrail(report):
        d_result = lint_na_hypotheses(report)
        if d_result.verdict is not GuardrailVerdict.PASS:
            return d_result
        return lint_na_ranking_coverage(
            report=report,
            anomaly_flags=state.get("anomaly_flags") or [],
            kb=_ranking_kb,
            known_nfs=_known_nfs,
        )

    state, na_traces, na_success, na_report = await run_phase_with_guardrail(
        agent_factory=create_network_analyst,
        state=state,
        question=question,
        session_service=session_service,
        on_event=on_event,
        output_key=_NA_OUTPUT_KEY,
        phase_label="Phase 3 NetworkAnalyst",
        run_phase=_run_phase,
        parser=_parse_network_analysis,
        guardrail=_na_combined_guardrail,
        max_resamples=1,
        on_guardrail_exhausted="accept",
    )
    all_phases.extend(na_traces)
    _accumulate_phase_traces(state, na_traces)
    if not na_success:
        state[_NA_OUTPUT_KEY] = json.dumps({
            "summary": (
                "NetworkAnalyst produced empty output on two consecutive "
                "attempts. ADK's silent-bail on empty Gemini final-response "
                "(agents/llm_agent.py:__maybe_save_output_to_state) prevented "
                "the schema-validation error from surfacing. No hypotheses "
                "were produced; the pipeline will skip the Investigator phase."
            ),
            "layer_status": {},
            "hypotheses": [],
        })
        # Re-parse the sentinel we just wrote so the rest of the phase
        # sees the same shape it did before this PR.
        na_report = _parse_network_analysis(state.get(_NA_OUTPUT_KEY))
    elif na_report is None:
        # Parser returned None for some reason (shouldn't happen since we
        # wired `parser=_parse_network_analysis`, but defensive). Fall
        # back to direct parse so downstream code is unchanged.
        na_report = _parse_network_analysis(state.get(_NA_OUTPUT_KEY))
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

    # Two layered guards run on IG's output:
    #
    #   (a) Empty-output retry. ADK's `LlmAgent` silently bails on an
    #       empty Gemini final-response chunk; this produced a
    #       tool_calls=0, llm_calls=1 IG run on
    #       run_20260429_031341_call_quality_degradation, leaving
    #       state[_IG_OUTPUT_KEY] unset and making Phase 5 run with no
    #       plan. Detect-and-resample once. On both-attempts-empty,
    #       write the IG-specific sentinel below so Phase 5 sees
    #       plans=[] cleanly instead of fabricating citations from
    #       missing state.
    #
    #   (b) IG-statement linter (Decision A — PR 4). Sub-check A1
    #       (partner probe) + A2 (mechanism-scoping linter on
    #       expected_if_hypothesis_holds and falsifying_observation).
    #       Closes the leak PR 2 left at the IG stage:
    #       run_20260501_012613 had clean NA statements but IG h1
    #       wrote "rather than a UPF-internal fault" which the
    #       Investigator faithfully treated as a falsifying condition.
    #       On REJECT, resample IG once with the per-probe rejection
    #       reason injected via `{guardrail_rejection_reason}`. On
    #       still-rejected second attempt, accept-with-warning
    #       (synthetic PhaseTrace + state["guardrail_warnings"] entry)
    #       — a slightly mis-framed plan is worse than a clean one but
    #       better than a hard pipeline failure.
    state, ig_traces, ig_success, plan_set = await run_phase_with_guardrail(
        agent_factory=create_instruction_generator,
        state=state,
        question=question,
        session_service=session_service,
        on_event=on_event,
        output_key=_IG_OUTPUT_KEY,
        phase_label="Phase 4 InstructionGenerator",
        run_phase=_run_phase,
        parser=_parse_plan_set,
        guardrail=lint_ig_plan,
        max_resamples=1,
        on_guardrail_exhausted="accept",
    )
    all_phases.extend(ig_traces)
    _accumulate_phase_traces(state, ig_traces)
    if not ig_success:
        # Empty-output exhausted both attempts. Write the IG-specific
        # sentinel so the recorder shows the failure verbatim and Phase
        # 5 runs with plans=[] rather than fabricating citations.
        state[_IG_OUTPUT_KEY] = json.dumps({
            "plans": [],
            "_orchestrator_note": (
                "InstructionGenerator produced empty output on two consecutive "
                "attempts. ADK's silent-bail on empty Gemini final-response "
                "(agents/llm_agent.py:__maybe_save_output_to_state) prevented "
                "the schema-validation error from surfacing. No falsification "
                "plan was generated; Phase 5 ran with no probes."
            ),
        })
        plan_set = _empty_plan_set()
    elif plan_set is None:
        # Defensive: parser path should always return a (possibly
        # empty) FalsificationPlanSet, but if it returned None for
        # some reason fall back to direct parse.
        plan_set = _parse_plan_set(state.get(_IG_OUTPUT_KEY))

    # -------- Phase 5: Parallel Investigators --------
    # Forward anomaly-window timestamps so each sub-Investigator's
    # session state can resolve `{anomaly_screener_snapshot_ts}` in
    # the prompt (ADR dealing_with_temporality_3.md Layer 1).
    verdicts = await _run_parallel_investigators(
        hypotheses, plan_set.plans,
        network_analysis_text=state.get("network_analysis", ""),
        session_service=session_service,
        all_phases=all_phases,
        anomaly_window_start_ts=float(state.get("anomaly_window_start_ts", 0.0) or 0.0),
        anomaly_window_end_ts=float(state.get("anomaly_window_end_ts", 0.0) or 0.0),
        anomaly_screener_snapshot_ts=float(state.get("anomaly_screener_snapshot_ts", 0.0) or 0.0),
        on_event=on_event,
    )
    state["investigator_verdicts"] = json.dumps(
        [v.model_dump() for v in verdicts], indent=2,
    )

    # -------- Phase 6.5: Candidate-pool aggregator + bounded re-investigation --------
    # Decision E (PR 5). Walk the verdict tree, build a ranked
    # candidate pool from NOT_DISPROVEN survivors plus alt_suspects
    # that crossed the corroboration threshold. If the pool has zero
    # NOT_DISPROVEN survivors but ≥1 promoted suspect, run one bounded
    # re-investigation cycle (IG + Investigator) on the top-ranked
    # promoted NF. The new verdict joins the verdict list and Synthesis
    # ratifies it normally instead of inferring from `alternative_suspects`
    # prose. The full pool is also rendered into state["candidate_pool"]
    # so the Synthesis prompt's `{candidate_pool}` template substitutes.
    pool = compute_candidate_pool(verdicts, hypotheses)
    pool_trace = PhaseTrace(
        agent_name="Phase6.5CandidatePool",
        started_at=time.time(),
        finished_at=time.time(),
        duration_ms=0,
        output_summary=(
            f"survivors={len(pool.survivors)}, "
            f"promoted={len(pool.promoted)}, "
            f"needs_reinvestigation={pool.needs_reinvestigation}"
        ),
    )
    all_phases.append(pool_trace)

    if pool.needs_reinvestigation and pool.top_promoted is not None:
        log.info(
            "Decision E — verdict tree has zero NOT_DISPROVEN; "
            "bounded re-investigation on '%s' (top-ranked promoted suspect).",
            pool.top_promoted.nf,
        )
        new_verdict = await _run_bounded_reinvestigation(
            promoted_nf=pool.top_promoted.nf,
            original_hypotheses=hypotheses,
            state=state,
            question=question,
            session_service=session_service,
            on_event=on_event,
            all_phases=all_phases,
        )
        verdicts.append(new_verdict)
        # Re-render the verdict list into state so Synthesis sees the
        # augmented evidence.
        state["investigator_verdicts"] = json.dumps(
            [v.model_dump() for v in verdicts], indent=2,
        )
        # Re-compute the pool so the prompt rendering reflects the
        # new survivor (or new DISPROVEN) the re-investigation produced.
        pool = compute_candidate_pool(verdicts, hypotheses)

    state["candidate_pool"] = pool.render_for_prompt()

    # -------- Phase 6.6: Evidence Validator --------
    # Moved here from its original Phase-6 slot in PR 5.5a so that EV
    # also covers the re-investigation Investigator's tool-call trace.
    # Previously EV ran before Phase 6.5, which meant a re-investigation
    # verdict could carry fabricated citations through Synthesis without
    # being challenged. `investigator_outputs` is rebuilt from the
    # (possibly-augmented) `verdicts` list so the re-investigation
    # verdict is included.
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
    # Three layered guards on Synthesis output:
    #   (a) Empty-output retry — same silent-bail ADK pattern as NA / IG.
    #   (b) Pool-membership guardrail (Decision E, PR 5.5b) — Synthesis
    #       emits a structured `DiagnosisReport` (output_schema) and the
    #       guardrail rejects any `primary_suspect_nf` that isn't in the
    #       Phase-6.5 candidate pool. REJECT path with one resample.
    #   (c) Confidence cap (Decision F, PR 3) — after pool membership
    #       passes, compute the supporting verdict's evidence-strength
    #       (CONSISTENT / CONTRADICTS / AMBIGUOUS counts) and cap
    #       `root_cause_confidence` accordingly. REPAIR path — silent
    #       rewrite + cap note appended to `explanation`. The
    #       diagnosed NF stands; only the confidence claim gets
    #       corrected.
    # The composed guardrail closure runs (b) first; on PASS it runs
    # (c); on REJECT it returns the membership rejection.
    def _synthesis_combined_guardrail(report):
        membership = lint_synthesis_pool_membership(report, pool)
        if membership.verdict is not GuardrailVerdict.PASS:
            return membership
        return cap_synthesis_confidence(
            report,
            verdicts=verdicts,
            hypotheses=hypotheses,
            pool=pool,
        )

    state, syn_traces, syn_success, diagnosis_report = await run_phase_with_guardrail(
        agent_factory=create_synthesis_agent,
        state=state,
        question=question,
        session_service=session_service,
        on_event=on_event,
        output_key=_SYNTHESIS_OUTPUT_KEY,
        phase_label="Phase 7 Synthesis",
        run_phase=_run_phase,
        parser=_parse_diagnosis_report,
        # Closure binds the (possibly re-investigation-augmented) pool
        # AND the verdicts list so both pool-membership and the
        # confidence cap can run without threading parameters through
        # `run_phase_with_guardrail`'s single-arg guardrail signature.
        guardrail=_synthesis_combined_guardrail,
        max_resamples=1,
        on_guardrail_exhausted="accept",
    )
    all_phases.extend(syn_traces)
    _accumulate_phase_traces(state, syn_traces)

    if not syn_success or diagnosis_report is None:
        # Empty-output retry exhausted both attempts (or parser fell
        # through). Render a sentinel so the recorder shows the failure
        # cleanly instead of a blank diagnosis section.
        diagnosis_report = _empty_diagnosis_report(
            "Synthesis produced empty output on two consecutive attempts. "
            "ADK's silent-bail on empty Gemini final-response prevented "
            "the diagnosis from being written. Inspect the per-Investigator "
            "verdicts and EvidenceValidator output above to derive the "
            "diagnosis manually."
        )

    # Replace state["diagnosis"] with the markdown rendering. The chaos
    # `EpisodeRecorder` and `score_diagnosis` both read this as plain
    # text, so we render the structured report back to markdown. The
    # structured form is preserved separately for any downstream tooling
    # that wants typed access.
    state[_SYNTHESIS_OUTPUT_KEY] = _render_diagnosis_report_to_markdown(
        diagnosis_report,
    )
    state["diagnosis_structured"] = diagnosis_report.model_dump(mode="json")

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


def _empty_diagnosis_report(reason: str) -> DiagnosisReport:
    """Sentinel DiagnosisReport for empty-output / parse-failure paths.

    `verdict_kind` is forced to `inconclusive` and `primary_suspect_nf`
    to None so the pool-membership guardrail passes (empty pool +
    inconclusive is the only valid combination on the no-pool branch).
    `model_construct` bypasses the typed `_KnownNF` constraint on
    `primary_suspect_nf` since None is already a valid value but we
    want to skip Pydantic's full validation pipeline on the sentinel.
    """
    return DiagnosisReport.model_construct(
        summary=reason,
        root_cause="Synthesis sentinel — see summary",
        root_cause_confidence="low",
        primary_suspect_nf=None,
        verdict_kind="inconclusive",
        affected_components=[],
        timeline=[],
        recommendation="Manual investigation required.",
        explanation=reason,
    )


def _parse_diagnosis_report(raw: Any) -> DiagnosisReport:
    """Parse Synthesis's structured output into a DiagnosisReport.

    Returns the empty sentinel on missing/unparseable input — the pool
    guardrail then sees `verdict_kind=inconclusive` and passes (empty
    pool branch).
    """
    if raw is None:
        return _empty_diagnosis_report("Synthesis produced no output")
    try:
        if isinstance(raw, str):
            data = json.loads(raw)
        else:
            data = raw
        return DiagnosisReport(**data)
    except Exception as e:
        log.warning("Could not parse Synthesis output: %s", e)
        return _empty_diagnosis_report(f"Synthesis output unparseable: {e}")


def _render_diagnosis_report_to_markdown(report: DiagnosisReport) -> str:
    """Render the structured DiagnosisReport back to the markdown shape
    the chaos `EpisodeRecorder` and `score_diagnosis` expect.

    Format mirrors the previous plain-markdown Synthesis output so
    downstream consumers (recorder template, LLM-judge scorer) keep
    receiving the prose form they were built against.
    """
    lines: list[str] = ["### causes"]
    lines.append(f"- **summary**: {report.summary}")
    if report.timeline:
        lines.append("- **timeline**:")
        for i, t in enumerate(report.timeline, 1):
            lines.append(f"    {i}. {t}")
    else:
        lines.append("- **timeline**: []")
    rc_line = f"- **root_cause**: {report.root_cause}"
    if report.primary_suspect_nf:
        rc_line += f" (primary_suspect_nf: `{report.primary_suspect_nf}`)"
    lines.append(rc_line)
    if report.affected_components:
        lines.append("- **affected_components**:")
        for c in report.affected_components:
            name = c.get("name", "?") if isinstance(c, dict) else str(c)
            role = c.get("role", "?") if isinstance(c, dict) else "?"
            lines.append(f"    - `{name}`: {role}")
    else:
        lines.append("- **affected_components**: []")
    lines.append(f"- **recommendation**: {report.recommendation}")
    lines.append(f"- **confidence**: {report.root_cause_confidence}")
    lines.append(f"- **verdict_kind**: {report.verdict_kind}")
    lines.append(f"- **explanation**: {report.explanation}")
    return "\n".join(lines)


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
        # Structured warnings raised by guardrails whose resample budget
        # was exhausted but whose policy is "accept" (e.g. the NA
        # hypothesis-statement linter — Decision D / PR 2). Empty list
        # when every guardrail PASSED on first or second attempt.
        "guardrail_warnings": list(state.get("guardrail_warnings", [])),
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
