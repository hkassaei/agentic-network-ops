"""
Investigation Director v5 — 7-Phase Agent Pipeline.

Pipeline:
  Phase 0: AnomalyScreener (ML, no LLM)   → River HalfSpaceTrees flags statistical anomalies
  Phase 1: NetworkAnalystAgent (LLM)       → Layer assessment informed by pre-screened anomalies
  Phase 2: PatternMatcherAgent (BaseAgent) → Deterministic signature matching
  Phase 3: InstructionGeneratorAgent (LLM) → Synthesizes investigator instruction
  Phase 4: InvestigatorAgent (LLM)         → Verifies hypothesis with tools + OntologyConsultation
  Phase 5: EvidenceValidatorAgent (BaseAgent) → Fact-checks claims against tool traces
  Phase 6: SynthesisAgent (LLM)            → NOC-ready diagnosis

The orchestrator is pure workflow plumbing — every agent is invoked via
_run_phase() with session isolation. Phase 0 (anomaly screening) runs
as plain Python, not an ADK agent.

Usage:
    from agentic_ops_v5.orchestrator import investigate
    result = await investigate("The 5G SA + IMS stack is experiencing issues.")
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from google.adk.agents.base_agent import BaseAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from .subagents.network_analyst import create_network_analyst
from .subagents.pattern_matcher import create_pattern_matcher
from .subagents.instruction_generator import create_instruction_generator
from .subagents.investigator import create_investigator_agent
from .subagents.evidence_validator import create_evidence_validator
from .subagents.synthesis import create_synthesis_agent
from .models import (
    InvestigationTrace,
    PhaseTrace,
    TokenBreakdown,
    ToolCallTrace,
)

log = logging.getLogger("v5.orchestrator")


# -------------------------------------------------------------------------
# Session-per-phase execution
# -------------------------------------------------------------------------

async def _run_phase(
    agent: BaseAgent,
    state: dict[str, Any],
    question: str,
    session_service: InMemorySessionService,
    on_event=None,
) -> tuple[dict[str, Any], list[PhaseTrace]]:
    """Run one agent in an isolated session, return updated state + traces."""
    runner = Runner(
        agent=agent,
        app_name="troubleshoot_v5",
        session_service=session_service,
    )

    session = await session_service.create_session(
        app_name="troubleshoot_v5",
        user_id="operator",
        state=dict(state),
    )

    phase_map: dict[str, PhaseTrace] = {}
    _SKIP = {"user"}

    async for event in runner.run_async(
        user_id="operator",
        session_id=session.id,
        new_message=types.Content(
            role="user",
            parts=[types.Part(text=question)],
        ),
    ):
        author = event.author or ""
        ts = event.timestamp if hasattr(event, "timestamp") and event.timestamp else time.time()

        if author in _SKIP:
            continue

        if author and author not in phase_map:
            phase_map[author] = PhaseTrace(agent_name=author, started_at=ts)
            log.info("  Phase started: %s", author)
            if on_event:
                try:
                    await on_event({"type": "phase_start", "agent": author})
                except Exception:
                    pass

        phase = phase_map.get(author)

        # Token accounting
        um = event.usage_metadata
        if um and phase:
            prompt = getattr(um, "prompt_token_count", 0) or 0
            completion = getattr(um, "candidates_token_count", 0) or 0
            thinking = getattr(um, "thoughts_token_count", 0) or 0
            total_evt = getattr(um, "total_token_count", 0) or 0
            phase.tokens.prompt += prompt
            phase.tokens.completion += completion
            phase.tokens.thinking += thinking
            phase.tokens.total += total_evt
            phase.llm_calls += 1

        # Tool call & result tracking + event streaming
        if event.content and event.content.parts:
            for part in event.content.parts:
                fc = getattr(part, "function_call", None)
                if fc and phase:
                    args_str = json.dumps(fc.args, default=str)[:200] if fc.args else ""
                    phase.tool_calls.append(ToolCallTrace(
                        name=fc.name, args=args_str, timestamp=ts,
                    ))
                    if on_event:
                        try:
                            await on_event({
                                "type": "tool_call", "agent": author,
                                "name": fc.name, "args": args_str,
                            })
                        except Exception:
                            pass

                fr = getattr(part, "function_response", None)
                if fr and phase and phase.tool_calls:
                    result_text = json.dumps(fr.response, default=str) if fr.response else ""
                    for tc in reversed(phase.tool_calls):
                        if tc.name == fr.name and tc.result_size == 0:
                            tc.result_size = len(result_text)
                            break
                    if on_event:
                        try:
                            await on_event({
                                "type": "tool_result", "agent": author,
                                "name": fr.name, "preview": result_text[:200],
                            })
                        except Exception:
                            pass

                if part.text and phase:
                    # Always keep the latest text — the last chunk is
                    # most likely the final answer.
                    phase.output_summary = part.text[:500]
                    if on_event:
                        try:
                            await on_event({
                                "type": "text", "agent": author,
                                "content": part.text[:300],
                            })
                        except Exception:
                            pass

        if event.actions and event.actions.state_delta and phase:
            for k in event.actions.state_delta:
                if k not in phase.state_keys_written:
                    phase.state_keys_written.append(k)

    # Merge state
    final_session = await session_service.get_session(
        app_name="troubleshoot_v5",
        user_id="operator",
        session_id=session.id,
    )
    updated_state = {**state, **final_session.state}

    # ADK output_key bug workaround: ADK filters out part.thought when
    # storing output_key (LlmAgent line 655).  If Gemini responds entirely
    # in thinking mode, the key is silently left as None.  Recover from
    # the text we captured in the event stream, or set a fallback so
    # downstream prompt templates ({key}) don't crash.
    output_key = getattr(agent, "output_key", None)
    if output_key and not updated_state.get(output_key):
        last_text = ""
        for phase in phase_map.values():
            if phase.output_summary:
                last_text = phase.output_summary
        if last_text:
            log.warning(
                "output_key %r was null — recovered from event stream", output_key)
            updated_state[output_key] = last_text
        else:
            log.error(
                "output_key %r was null and no text captured — "
                "agent %s produced no usable output", output_key, agent.name)
            updated_state[output_key] = (
                f"[{agent.name} produced no output — "
                f"possible ADK thinking-mode issue]"
            )

    now = time.time()
    traces = list(phase_map.values())
    for t in traces:
        t.finished_at = now
        t.duration_ms = int((t.finished_at - t.started_at) * 1000)

    return updated_state, traces


# -------------------------------------------------------------------------
# Public API
# -------------------------------------------------------------------------

def _accumulate_phase_traces(state: dict, new_traces: list) -> None:
    """Append serialized phase traces to state["phase_traces_so_far"].

    The EvidenceValidatorAgent reads this list to cross-check LLM
    claims against actual tool calls. Must run after every phase so
    downstream phases see the accumulated history.
    """
    current = state.get("phase_traces_so_far", []) or []
    for t in new_traces:
        # Use model_dump with mode='json' for clean serialization
        current.append(t.model_dump(mode="json") if hasattr(t, "model_dump") else dict(t))
    state["phase_traces_so_far"] = current


async def investigate(
    question: str,
    on_event=None,
    anomaly_window_hint_seconds: int = 300,
    metric_snapshots: list[dict] | None = None,
    observation_window_duration: int = 0,
    seconds_since_observation: int = 0,
) -> dict:
    """Run the v5 7-phase investigation pipeline.

    Phase 0: AnomalyScreener — statistical anomaly detection (ML, no LLM)
    Phase 1: NetworkAnalystAgent — layer assessment informed by pre-screened anomalies
    Phase 2: PatternMatcherAgent — deterministic signature matching
    Phase 3: InstructionGeneratorAgent — synthesize investigator instruction
    Phase 4: InvestigatorAgent — verify hypothesis with tools
    Phase 5: EvidenceValidatorAgent — fact-check claims against real tool calls
    Phase 6: SynthesisAgent — NOC-ready diagnosis (honors validation verdict)

    Args:
        question: The user's investigation question.
        on_event: Optional async callback for streaming events to the caller.
        anomaly_window_hint_seconds: Rough lookback hint for the agent's
            temporal reasoning (see docs/ADR/dealing_with_temporality_2.md).
        metric_snapshots: List of raw metric snapshot dicts collected during
            the observation period.
        observation_window_duration: How long (seconds) the observation traffic
            ran for. Used to tell agents the right Prometheus query window.
        seconds_since_observation: How many seconds ago the observation window
            ended. Used to offset Prometheus queries to the event timeframe.
    """
    # Compute the Prometheus lookback window that covers the observation period.
    # If the observation ran for 120s and ended 60s ago, agents should query
    # Prometheus with a window of at least 120+60=180s to capture the event.
    event_lookback_seconds = (observation_window_duration + seconds_since_observation
                              if observation_window_duration > 0
                              else anomaly_window_hint_seconds)

    session_service = InMemorySessionService()
    state: dict[str, Any] = {
        "user_question": question,
        "anomaly_window_hint_seconds": anomaly_window_hint_seconds,
        "event_lookback_seconds": event_lookback_seconds,
        "observation_window_duration": observation_window_duration,
        "seconds_since_observation": seconds_since_observation,
    }
    all_phases: list[PhaseTrace] = []
    invocation_order: list[str] = []
    run_start = time.time()

    log.info("Starting v5 investigation: %s", question[:100])

    # =================================================================
    # Phase 0: Anomaly Screener (ML, no LLM)
    # Loads pre-trained model from disk, processes metric snapshots
    # through a fresh preprocessor (building counter rates from
    # sequential snapshots), and scores against the model.
    # =================================================================
    try:
        from anomaly_trainer.persistence import load_model
        from .anomaly.preprocessor import MetricPreprocessor

        screener, _, meta = load_model()

        if screener is not None and screener.is_trained:
            phase0_start = time.time()
            if on_event:
                await on_event({"type": "phase_start", "agent": "AnomalyScreener"})

            log.info("Anomaly model loaded: %d samples, %d features (trained %s)",
                     meta.get("n_samples", 0), meta.get("n_features", 0),
                     meta.get("trained_at", "?"))

            # Determine snapshots to score
            snapshots = metric_snapshots or []

            if not snapshots:
                # No pre-collected snapshots — collect one live snapshot.
                # Less effective than extended observation but still useful.
                from .anomaly.preprocessor import parse_nf_metrics_text
                from . import tools as v5_tools
                log.info("No observation snapshots provided — collecting live snapshot")
                text = await v5_tools.get_nf_metrics()
                raw = parse_nf_metrics_text(text)
                snapshots = [{"_parsed": raw}]

            # Process all snapshots through a FRESH preprocessor.
            # Each sequential snapshot builds counter state, so by snapshot
            # ~3+ the rates are meaningful. We score the last few snapshots
            # and take the highest anomaly score.
            pp = MetricPreprocessor()
            best_report = None

            for i, snap in enumerate(snapshots):
                # Snapshots from ObservationTrafficAgent are in the format
                # {component: {metrics: {key: value}, badge: ..., source: ...}}
                # We need {component: {key: value}} for the preprocessor.
                raw_metrics = {}
                snap_timestamp = snap.get("_timestamp")
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

                features = pp.process(raw_metrics, timestamp=snap_timestamp)

                # Only score after the sliding window has enough samples
                # for smooth rates (window size = 6, so start scoring at 6+)
                if i >= 6 and features:
                    report = screener.score(features)
                    if best_report is None or report.overall_score > best_report.overall_score:
                        best_report = report

            if best_report is not None:
                state["anomaly_report"] = best_report.to_prompt_text()
                state["anomaly_flags"] = best_report.to_dict_list()
                log.info("Phase 0 (AnomalyScreener): %d flags, best score=%.3f "
                         "(%d snapshots processed)",
                         len(best_report.flags), best_report.overall_score,
                         len(snapshots))
            else:
                state["anomaly_report"] = (
                    "Anomaly screening produced no results "
                    f"({len(snapshots)} snapshots, need ≥3 for rate computation)."
                )
                log.info("Phase 0: insufficient snapshots for scoring (%d)", len(snapshots))

            phase0_duration = int((time.time() - phase0_start) * 1000)

            phase0_trace = PhaseTrace(
                agent_name="AnomalyScreener",
                started_at=phase0_start,
                finished_at=time.time(),
                duration_ms=phase0_duration,
            )
            n_flags = len(best_report.flags) if best_report else 0
            best_score = best_report.overall_score if best_report else 0.0
            phase0_trace.output_summary = (
                f"{n_flags} anomalies flagged (score={best_score:.3f})"
            )
            all_phases.append(phase0_trace)
            invocation_order.append("AnomalyScreener")

            if on_event and best_report:
                await on_event({
                    "type": "text", "agent": "AnomalyScreener",
                    "content": best_report.to_prompt_text()[:300],
                })
        else:
            log.info("No trained anomaly model found — Phase 0 skipped. "
                     "Run: python -m anomaly_trainer --duration 300")
            state["anomaly_report"] = (
                "Anomaly screening not available (no trained model). "
                "Run: python -m anomaly_trainer --duration 300"
            )

    except ImportError:
        log.info("anomaly_trainer module not available — Phase 0 skipped")
        state["anomaly_report"] = "Anomaly screening not available."
    except Exception as e:
        log.warning("AnomalyScreener failed (non-fatal): %s", e, exc_info=True)
        state["anomaly_report"] = f"Anomaly screening failed: {e}"

    # =================================================================
    # Phase 1: Network Analyst (LLM, informed by anomaly screening)
    # =================================================================
    try:
        state, traces = await _run_phase(
            create_network_analyst(), state, question, session_service, on_event)
        all_phases.extend(traces)
        invocation_order.extend(t.agent_name for t in traces)
        _accumulate_phase_traces(state, traces)
    except Exception as e:
        log.error("NetworkAnalystAgent failed: %s", e)
        state["network_analysis"] = f"Network analysis failed: {e}"

    # =================================================================
    # Phase 2: Pattern Matcher (deterministic BaseAgent)
    # =================================================================
    state, traces = await _run_phase(
        create_pattern_matcher(), state, question, session_service, on_event)
    all_phases.extend(traces)
    invocation_order.extend(t.agent_name for t in traces)
    _accumulate_phase_traces(state, traces)

    # =================================================================
    # Decide: should we run Phases 3+4 (Instruction Generator + Investigator)?
    #
    # If the Network Analyst already has a HIGH-confidence suspect with
    # definitive evidence (RED layer), running the Investigator adds no
    # value — it either re-runs the same tools or fabricates citations
    # from the upstream narrative. Skip both the Instruction Generator
    # (no point generating instructions for a skipped Investigator) and
    # the Investigator itself.
    #
    # Skip conditions (ALL must be true):
    #   1. Network Analyst produced a structured output (not a failure string)
    #   2. At least one suspect has "high" confidence
    #   3. At least one layer is rated RED
    #
    # When skipped, the Evidence Validator still runs (validating the
    # Network Analyst's evidence).
    # =================================================================
    investigator_skipped = False
    network_analysis = state.get("network_analysis")

    if isinstance(network_analysis, (dict, str)):
        na = network_analysis if isinstance(network_analysis, dict) else {}
        if isinstance(network_analysis, str):
            try:
                import json
                na = json.loads(network_analysis)
            except (json.JSONDecodeError, TypeError):
                na = {}

        suspects = na.get("suspect_components", [])
        layers = na.get("layer_status", {})

        has_high_suspect = any(
            (s.get("confidence", "").lower() == "high" if isinstance(s, dict) else False)
            for s in suspects
        )
        has_red_layer = any(
            (ls.get("rating", "").lower() == "red" if isinstance(ls, dict) else False)
            for ls in layers.values()
        )

        if has_high_suspect and has_red_layer:
            investigator_skipped = True

    if investigator_skipped:
        log.info("Phases 3+4 SKIPPED — Network Analyst has high-confidence "
                 "suspect with RED layer. Investigation would be redundant.")
        state["investigation_instruction"] = (
            "Instruction generation skipped: Network Analyst diagnosis is definitive."
        )
        state["investigation"] = (
            "Investigation skipped: Network Analyst produced a high-confidence "
            "diagnosis with definitive evidence (RED layer + high-confidence suspect). "
            "See Phase 1 analysis."
        )
        state["investigator_skipped"] = True
        if on_event:
            await on_event({
                "type": "phase_skip",
                "agent": "InstructionGeneratorAgent",
                "reason": "High-confidence diagnosis — investigation not needed",
            })
            await on_event({
                "type": "phase_skip",
                "agent": "InvestigatorAgent",
                "reason": "High-confidence diagnosis — investigation not needed",
            })
    else:
        # Phase 3: Instruction Generator (LLM)
        try:
            state, traces = await _run_phase(
                create_instruction_generator(), state, question, session_service, on_event)
            all_phases.extend(traces)
            invocation_order.extend(t.agent_name for t in traces)
            _accumulate_phase_traces(state, traces)
        except Exception as e:
            log.error("InstructionGeneratorAgent failed: %s", e)
            state["investigation_instruction"] = (
                "Instruction generation failed. Perform a full bottom-up investigation: "
                "transport first, then core, then application. Cite tool outputs."
            )

        # Phase 4: Investigator (LLM)
        try:
            state, traces = await _run_phase(
                create_investigator_agent(), state, question, session_service, on_event)
            all_phases.extend(traces)
            invocation_order.extend(t.agent_name for t in traces)
            _accumulate_phase_traces(state, traces)
        except Exception as e:
            log.error("InvestigatorAgent failed: %s", e)
            state["investigation"] = f"Investigation failed: {e}"

    # =================================================================
    # Phase 5: Evidence Validator (deterministic BaseAgent)
    # Cross-checks NetworkAnalyst + Investigator claims against the
    # actual tool-call trace. Never blocks Synthesis — writes a verdict
    # and confidence level into state for Synthesis to honor.
    # =================================================================
    try:
        state, traces = await _run_phase(
            create_evidence_validator(), state, question, session_service, on_event)
        all_phases.extend(traces)
        invocation_order.extend(t.agent_name for t in traces)
        _accumulate_phase_traces(state, traces)
    except Exception as e:
        log.error("EvidenceValidatorAgent failed: %s", e)
        state["evidence_validation"] = {
            "verdict": "severe",
            "investigator_confidence": "none",
            "summary": f"Evidence validation failed: {e}",
        }
        state["investigator_confidence"] = "none"

    # =================================================================
    # Phase 6: Synthesis (LLM) — reads evidence_validation from state
    # =================================================================
    try:
        state, traces = await _run_phase(
            create_synthesis_agent(), state, question, session_service, on_event)
        all_phases.extend(traces)
        invocation_order.extend(t.agent_name for t in traces)
        _accumulate_phase_traces(state, traces)
    except Exception as e:
        log.error("SynthesisAgent failed: %s", e)
        state["diagnosis"] = state.get("investigation", f"Synthesis failed: {e}")

    # =================================================================
    # Build investigation trace
    # =================================================================
    run_end = time.time()
    total_breakdown = TokenBreakdown()
    for p in all_phases:
        total_breakdown.prompt += p.tokens.prompt
        total_breakdown.completion += p.tokens.completion
        total_breakdown.thinking += p.tokens.thinking
        total_breakdown.total += p.tokens.total

    trace_obj = InvestigationTrace(
        question=question[:200],
        started_at=run_start,
        finished_at=run_end,
        duration_ms=int((run_end - run_start) * 1000),
        total_tokens=total_breakdown,
        phases=all_phases,
        invocation_chain=invocation_order,
    )

    log.info("Investigation trace: %d phases, %d total tokens, %d ms",
             len(all_phases), total_breakdown.total, trace_obj.duration_ms)
    for p in all_phases:
        log.info("  %-30s %6d ms  %7d tokens  %d tool calls  %d LLM calls",
                 p.agent_name, p.duration_ms, p.tokens.total,
                 len(p.tool_calls), p.llm_calls)

    # =================================================================
    # Assemble result
    # =================================================================
    result = {
        "anomaly_report": state.get("anomaly_report"),
        "anomaly_flags": state.get("anomaly_flags"),
        "network_analysis": state.get("network_analysis"),
        "pattern_match": state.get("pattern_match"),
        "investigation_instruction": state.get("investigation_instruction"),
        "evidence_validation": state.get("evidence_validation"),
        "investigator_confidence": state.get("investigator_confidence"),
        "investigation": state.get("investigation"),
        "diagnosis": state.get("diagnosis"),
        "events": [f"[{p.agent_name}] {p.output_summary}" for p in all_phases if p.output_summary],
        "total_tokens": total_breakdown.total,
        "investigation_trace": trace_obj.model_dump(),
    }

    log.info("Investigation complete. Total tokens: %d. Diagnosis: %s",
             total_breakdown.total, str(state.get("diagnosis", ""))[:200])
    return result
