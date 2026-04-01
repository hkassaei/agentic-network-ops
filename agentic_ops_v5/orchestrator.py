"""
Investigation Director v5 — Deterministic Backbone & Lean Investigation.

Pipeline:
  Phase 0:   TriageAgent (LLM)          → state["triage"]
  Phase 0.5: OntologyAnalysis (Python)   → state["ontology_diagnosis"], state["investigation_plan"]
  Phase 1:   InvestigatorAgent (LLM)     → state["investigation"]
  Phase 2:   SynthesisAgent (LLM)        → state["diagnosis"]

The key innovation: Phase 0.5 runs as pure Python code — no LLM involved.
The ontology diagnoses the failure deterministically, then the LLM verifies.

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

from .agents.triage import create_triage_agent
from .agents.investigator import create_investigator_agent
from .agents.synthesis import create_synthesis_agent
from .ontology_bridge import (
    collect_observations,
    run_deterministic_diagnosis,
    format_ontology_for_prompt,
)
from .models import (
    InvestigationTrace,
    PhaseTrace,
    TokenBreakdown,
    ToolCallTrace,
)

log = logging.getLogger("v5.orchestrator")


# -------------------------------------------------------------------------
# Session-per-phase execution (ported from v4, identical pattern)
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
                    if not phase.output_summary:
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

    now = time.time()
    traces = list(phase_map.values())
    for t in traces:
        t.finished_at = now
        t.duration_ms = int((t.finished_at - t.started_at) * 1000)

    return updated_state, traces


# -------------------------------------------------------------------------
# Public API
# -------------------------------------------------------------------------

async def investigate(question: str, on_event=None) -> dict:
    """Run the v5 deterministic backbone investigation.

    Pipeline:
      Phase 0:   TriageAgent (LLM) — collects metrics and topology
      Phase 0.5: OntologyAnalysis (Python) — deterministic diagnosis + short-circuit
      Phase 1:   InvestigatorAgent (LLM) — verifies ontology hypothesis
      Phase 2:   SynthesisAgent (LLM) — produces NOC-ready diagnosis
    """
    session_service = InMemorySessionService()
    state: dict[str, Any] = {"user_question": question}
    all_phases: list[PhaseTrace] = []
    invocation_order: list[str] = []
    run_start = time.time()

    log.info("Starting v5 investigation: %s", question[:100])

    # =================================================================
    # Phase 0: Triage (LLM) — collect metrics, topology, health
    # =================================================================
    state, traces = await _run_phase(
        create_triage_agent(), state, question, session_service, on_event)
    all_phases.extend(traces)
    invocation_order.extend(t.agent_name for t in traces)

    # =================================================================
    # Phase 0.5: Deterministic Ontology Analysis (Python, NOT LLM)
    # =================================================================
    phase05_start = time.time()

    if on_event:
        try:
            await on_event({"type": "phase_start", "agent": "OntologyAnalysis"})
        except Exception:
            pass

    # Collect structured observations directly from tools (not from triage text)
    try:
        observations = await collect_observations()
    except Exception as e:
        log.warning("Direct observation collection failed: %s — using triage text", e)
        observations = None

    # Run deterministic diagnosis
    ontology_result, investigation_plan = await run_deterministic_diagnosis(
        triage_text=state.get("triage", ""),
        observations=observations,
    )

    # Inject into state as established facts for downstream agents
    state["ontology_diagnosis"] = format_ontology_for_prompt(ontology_result)
    state["investigation_mandate"] = investigation_plan["mandate"]
    state["suggested_tools"] = ", ".join(investigation_plan.get("suggested_tools", []))
    state["investigation_plan"] = investigation_plan

    # Log what the ontology found
    log.info("  Ontology diagnosis: %s (confidence: %s, domain: %s)",
             ontology_result.get("top_diagnosis", "?"),
             ontology_result.get("confidence", "?"),
             investigation_plan.get("focus_domain", "?"))

    if on_event:
        try:
            await on_event({
                "type": "text", "agent": "OntologyAnalysis",
                "content": (
                    f"Diagnosis: {ontology_result.get('top_diagnosis', 'No match')} "
                    f"(confidence: {ontology_result.get('confidence', 'low')})\n"
                    f"Focus: {investigation_plan.get('focus_domain', 'unknown')}"
                ),
            })
        except Exception:
            pass

    # Create PhaseTrace for Phase 0.5 (no tokens — pure Python)
    phase05_trace = PhaseTrace(
        agent_name="OntologyAnalysis",
        started_at=phase05_start,
        finished_at=time.time(),
        duration_ms=int((time.time() - phase05_start) * 1000),
        tokens=TokenBreakdown(),  # Zero tokens — no LLM
        llm_calls=0,
        output_summary=f"{ontology_result.get('top_diagnosis', 'No match')} ({ontology_result.get('confidence', 'low')})",
        state_keys_written=["ontology_diagnosis", "investigation_mandate", "suggested_tools", "investigation_plan"],
    )
    all_phases.append(phase05_trace)
    invocation_order.append("OntologyAnalysis")

    # =================================================================
    # Phase 1: Investigator (LLM) — verify ontology hypothesis
    # =================================================================
    try:
        state, traces = await _run_phase(
            create_investigator_agent(), state, question, session_service, on_event)
        all_phases.extend(traces)
        invocation_order.extend(t.agent_name for t in traces)
    except Exception as e:
        log.error("InvestigatorAgent failed: %s", e)
        state["investigation"] = f"Investigation failed: {e}"
        if on_event:
            try:
                await on_event({"type": "text", "agent": "InvestigatorAgent",
                                "content": f"ERROR: {e}"})
            except Exception:
                pass

    # =================================================================
    # Phase 2: Synthesis (LLM) — produce final diagnosis
    # =================================================================
    try:
        state, traces = await _run_phase(
            create_synthesis_agent(), state, question, session_service, on_event)
        all_phases.extend(traces)
        invocation_order.extend(t.agent_name for t in traces)
    except Exception as e:
        log.error("SynthesisAgent failed: %s", e)
        # Fall back: use investigator output as diagnosis
        state["diagnosis"] = state.get("investigation", f"Synthesis failed: {e}")
        if on_event:
            try:
                await on_event({"type": "text", "agent": "SynthesisAgent",
                                "content": f"ERROR: {e}. Using investigator output as diagnosis."})
            except Exception:
                pass

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
        log.info("  %-25s %6d ms  %7d tokens  %d tool calls  %d LLM calls",
                 p.agent_name, p.duration_ms, p.tokens.total,
                 len(p.tool_calls), p.llm_calls)

    # =================================================================
    # Assemble result
    # =================================================================
    result = {
        "triage": state.get("triage"),
        "ontology_diagnosis": state.get("ontology_diagnosis"),
        "investigation_plan": state.get("investigation_plan"),
        "investigation": state.get("investigation"),
        "diagnosis": state.get("diagnosis"),
        "events": [f"[{p.agent_name}] {p.output_summary}" for p in all_phases if p.output_summary],
        "total_tokens": total_breakdown.total,
        "investigation_trace": trace_obj.model_dump(),
    }

    log.info("Investigation complete. Total tokens: %d. Diagnosis: %s",
             total_breakdown.total, str(state.get("diagnosis", ""))[:200])
    return result
