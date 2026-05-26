"""
ChallengeAgent — invokes the agentic_ops troubleshooting agent to diagnose
the currently broken stack, then scores the diagnosis against ground truth.

The RCA agent sees the symptoms but does NOT know what fault was injected.
This creates a closed-loop eval framework for telecom RCA models.

Requires ANTHROPIC_API_KEY (or equivalent) for the troubleshooting agent.
If unavailable, Challenge Mode is skipped gracefully.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import AsyncGenerator

from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.genai import types


from ..scorer import score_diagnosis

log = logging.getLogger("chaos-agent.challenger")

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _get_v3_models() -> str:
    """Read the actual model names from v3 agent definitions.

    Used for v3/v4/v5/v6 reporting labels. v6 happens to share the same
    Pro+Flash model ids as v3 today, so its label is correct by
    coincidence; if v6 ever diverges this helper should be split.
    v7 uses `_get_v7_models()` instead.
    """
    try:
        ops_path = str(_REPO_ROOT)
        if ops_path not in sys.path:
            sys.path.insert(0, ops_path)

        from agentic_ops_v3.agents.triage import create_triage_agent
        from agentic_ops_v3.agents.synthesis import create_synthesis_agent

        models = set()
        for factory in [create_triage_agent, create_synthesis_agent]:
            agent = factory()
            if hasattr(agent, "model") and agent.model:
                models.add(str(agent.model))

        if models:
            return "+".join(sorted(models))
    except Exception:
        pass
    return "gemini-unknown"


def _get_v7_models() -> str:
    """Resolve the v7 Pro+Flash model ids at call time.

    Reads `agentic_ops_v7.model_config`, which honours the
    `GEMINI_PRO_MODEL` / `GEMINI_FLASH_MODEL` env vars. This runs after
    the v7 pipeline finishes, so the env state is identical to the env
    the subagents saw — the label always matches what was invoked.
    """
    try:
        ops_path = str(_REPO_ROOT)
        if ops_path not in sys.path:
            sys.path.insert(0, ops_path)
        from agentic_ops_v7.model_config import pro_model_id, flash_model_id
        return f"pro={pro_model_id()}+flash={flash_model_id()}"
    except Exception:
        return "gemini-unknown"


class ChallengeAgent(BaseAgent):
    """Invokes the RCA agent on the broken stack and scores its diagnosis."""

    name: str = "ChallengeAgent"
    description: str = (
        "Challenge Mode: invokes the troubleshooting agent to diagnose "
        "the injected fault, then scores the diagnosis."
    )

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        scenario = ctx.session.state.get("scenario", {})
        agent_version = ctx.session.state.get("agent_version", "v1.5")

        # Skip if --abort-on-unpropagated was set and the verifier
        # reported the fault didn't manifest. The Healer and Recorder
        # still run after this; only the expensive agent call is skipped.
        if ctx.session.state.get("episode_aborted", False):
            verification = ctx.session.state.get("fault_verification", {})
            yield Event(
                author=self.name,
                content=types.Content(
                    parts=[types.Part(text=(
                        f"Challenge Mode: skipped — fault verification "
                        f"verdict={verification.get('verdict', '?')}, "
                        f"--abort-on-unpropagated is set"
                    ))],
                ),
            )
            return

        # Check if the RCA agent is available
        if not self._rca_agent_available(agent_version):
            yield Event(
                author=self.name,
                content=types.Content(
                    parts=[types.Part(text=(
                        f"Challenge Mode: skipped ({agent_version} agent not available — "
                        "check API keys and imports)"
                    ))],
                ),
            )
            return

        log.info("Challenge Mode: invoking %s agent...", agent_version)

        # Pass episode_id to v6/v7 via env var so they can scope the event
        # store query. (v7 inherits v6's event-store wiring, so the same
        # env-var contract applies.)
        if agent_version in ("v6", "v7"):
            episode_id = ctx.session.state.get("episode_id", "unknown")
            import os as _os
            _os.environ["V6_EPISODE_ID"] = str(episode_id)
            log.info("Set V6_EPISODE_ID=%s for %s event store scoping",
                     episode_id, agent_version)

        faults_injected = ctx.session.state.get("faults_injected", [])
        anomaly_window_hint_seconds = int(
            ctx.session.state.get("anomaly_window_hint_seconds", 300)
        )
        observation_snapshots = ctx.session.state.get("observation_snapshots", [])
        observation_window_end = ctx.session.state.get("observation_window_end", 0)
        observation_window_duration = ctx.session.state.get("observation_window_duration", 0)
        if observation_snapshots:
            log.info("Passing %d observation snapshots to RCA agent "
                     "(window: %ds, ended %ds ago)",
                     len(observation_snapshots), observation_window_duration,
                     int(time.time() - observation_window_end) if observation_window_end else 0)

        question = self._build_question()

        start_time = time.time()
        # Compute how many seconds ago the observation window ended
        # so the agents can query Prometheus for the right timeframe
        seconds_since_observation = int(time.time() - observation_window_end) if observation_window_end else 0
        try:
            diagnosis_dict = await self._run_rca_agent(
                question, agent_version,
                anomaly_window_hint_seconds=anomaly_window_hint_seconds,
                metric_snapshots=observation_snapshots,
                observation_window_duration=observation_window_duration,
                seconds_since_observation=seconds_since_observation,
            )
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            log.error("RCA agent failed: %s\n%s", e, tb)
            yield Event(
                author=self.name,
                content=types.Content(
                    parts=[types.Part(text=f"Challenge Mode: RCA agent error — {e}\n{tb}")],
                ),
                actions=EventActions(state_delta={
                    "challenge_result": {
                        "rca_agent_model": f"{agent_version}-adk/error",
                        "diagnosis_text": f"RCA agent crashed: {e}",
                        "score": {"total_score": 0, "summary": f"Agent crashed: {e}"},
                        "time_to_diagnosis_seconds": 0,
                        "_error_traceback": tb,
                    }
                }),
            )
            return

        elapsed = time.time() - start_time

        # Get the raw diagnosis text for the LLM scorer
        diagnosis_text = diagnosis_dict.get("_raw_diagnosis", "")
        if not diagnosis_text:
            # Fallback: reconstruct from parsed fields
            diagnosis_text = diagnosis_dict.get("root_cause", diagnosis_dict.get("summary", ""))

        # Score the diagnosis using LLM judge
        network_analysis = diagnosis_dict.get("_network_analysis", "")
        score = await score_diagnosis(
            diagnosis_text=diagnosis_text,
            injected_faults=faults_injected,
            scenario=scenario,
            network_analysis=str(network_analysis) if network_analysis else "",
        )

        if agent_version == "v7":
            rca_model = f"v7-adk/{_get_v7_models()}"
        elif agent_version in ("v3", "v4", "v5", "v6"):
            rca_model = f"{agent_version}-adk/{_get_v3_models()}"
        else:
            rca_model = f"v1.5-pydantic/{os.environ.get('AGENT_MODEL', 'google-vertex:gemini-2.5-pro')}"

        token_usage = diagnosis_dict.get("_token_usage", {})

        challenge_result = {
            "rca_agent_model": rca_model,
            "prompt_to_agent": question,
            "diagnosis_text": diagnosis_text,
            "score": score,
            "time_to_diagnosis_seconds": round(elapsed, 1),
            "token_usage": token_usage,
            "anomaly_report": diagnosis_dict.get("_anomaly_report", ""),
            "network_analysis": diagnosis_dict.get("_network_analysis", ""),
            "pattern_match": diagnosis_dict.get("_pattern_match", ""),
            "investigation_instruction": diagnosis_dict.get("_investigation_instruction", ""),
            "investigation": diagnosis_dict.get("_investigation", ""),
            "evidence_validation": diagnosis_dict.get("_evidence_validation", ""),
            "fired_events": diagnosis_dict.get("_fired_events", ""),
            "correlation_analysis": diagnosis_dict.get("_correlation_analysis", ""),
            # v7 transport-layer pipeline outputs (Phase 0.5 + 0.6).
            # Populated for v7 runs that engaged the path-walk route;
            # None for application-layer v7 runs and for all v3-v6 runs.
            "symptom_classification": diagnosis_dict.get("_symptom_classification"),
            "resolved_path":          diagnosis_dict.get("_resolved_path"),
            "path_walk_report":       diagnosis_dict.get("_path_walk_report"),
            "path_walk_all_reports":  diagnosis_dict.get("_path_walk_all_reports"),
            "diagnosis_report":       diagnosis_dict.get("_diagnosis_report"),
            # v7 RAG observability (Phase 2.5 / 2.5b + post-Phase-3 citation
            # scan). Recorder reads these via challenge.get(...) to render
            # the "RAG & Operational Lessons" section. None when the
            # localized branch fired or RAG is disabled.
            "rag_retrieval_metadata":   diagnosis_dict.get("_rag_retrieval_metadata"),
            "lessons_injection_metadata": diagnosis_dict.get("_lessons_injection_metadata"),
            "rag_na_citations":         diagnosis_dict.get("_rag_na_citations"),
        }

        total = score.get("total_score", 0)
        msg = (
            f"Challenge Mode complete ({elapsed:.1f}s)\n"
            f"  Score: {total:.0%}\n"
            f"    Root cause correct: {score.get('root_cause_correct')}\n"
            f"    Component overlap:  {score.get('component_overlap', 0):.0%}\n"
            f"    Severity correct:   {score.get('severity_correct')}\n"
            f"    Layer accuracy:     {score.get('layer_accuracy')}\n"
            f"  Scorer summary: {score.get('summary', '?')}"
        )
        log.info("Challenge Mode: score=%.0f%%", total * 100)

        yield Event(
            author=self.name,
            content=types.Content(parts=[types.Part(text=msg)]),
            actions=EventActions(state_delta={"challenge_result": challenge_result}),
        )

    def _rca_agent_available(self, agent_version: str = "v1.5") -> bool:
        """Check if the specified RCA agent can be instantiated."""
        ops_path = str(_REPO_ROOT)
        if ops_path not in sys.path:
            sys.path.insert(0, ops_path)

        if agent_version in ("v3", "v4", "v5", "v6", "v7"):
            # v3/v4/v5/v6/v7 use Google ADK (Vertex AI)
            has_key = bool(
                os.environ.get("GOOGLE_CLOUD_PROJECT")
                or os.environ.get("GOOGLE_GENAI_USE_VERTEXAI")
            )
            if not has_key:
                return False
            try:
                if agent_version == "v7":
                    from agentic_ops_v7.orchestrator import investigate  # noqa: F401
                elif agent_version == "v6":
                    from agentic_ops_v6.orchestrator import investigate  # noqa: F401
                elif agent_version == "v5":
                    from agentic_ops_v5.orchestrator import investigate  # noqa: F401
                elif agent_version == "v4":
                    from agentic_ops_v4.orchestrator import investigate  # noqa: F401
                else:
                    from agentic_ops_v3.orchestrator import investigate  # noqa: F401
                return True
            except ImportError:
                return False
        else:
            # v1.5 uses Pydantic AI — defaults to Vertex AI (gemini-2.5-pro)
            # but can also use Anthropic via AGENT_MODEL env var
            has_key = bool(
                os.environ.get("GOOGLE_CLOUD_PROJECT")
                or os.environ.get("ANTHROPIC_API_KEY")
                or os.environ.get("AGENT_MODEL")
            )
            if not has_key:
                return False
            try:
                from agentic_ops.agent import create_agent  # noqa: F401
                return True
            except ImportError:
                return False

    def _build_question(self) -> str:
        """Build a blind diagnostic question for the RCA agent.

        The agent receives no hints about observed symptoms — it must
        discover everything on its own using its tools. This makes the
        challenge a true test of autonomous diagnostic ability.
        """
        return (
            "The 5G SA + IMS stack is experiencing issues. "
            "Investigate and diagnose the root cause."
        )

    async def _run_rca_agent(
        self, question: str, agent_version: str = "v1.5",
        anomaly_window_hint_seconds: int = 300,
        metric_snapshots: list | None = None,
        observation_window_duration: int = 0,
        seconds_since_observation: int = 0,
    ) -> dict:
        """Run the specified troubleshooting agent and return its diagnosis."""
        ops_path = str(_REPO_ROOT)
        if ops_path not in sys.path:
            sys.path.insert(0, ops_path)

        if agent_version in ("v3", "v4", "v5", "v6", "v7"):
            return await self._run_adk_agent(
                question, agent_version,
                anomaly_window_hint_seconds=anomaly_window_hint_seconds,
                metric_snapshots=metric_snapshots,
                observation_window_duration=observation_window_duration,
                seconds_since_observation=seconds_since_observation,
            )
        return await self._run_v15_agent(question)

    async def _run_v15_agent(self, question: str) -> dict:
        """Run the v1.5 (Pydantic AI) troubleshooting agent."""
        from agentic_ops.agent import create_agent
        from agentic_ops.models import AgentDeps
        from agentic_chaos.tools.observation_tools import _load_env

        env = _load_env()
        pyhss_api = f"http://{env.get('PYHSS_IP', '172.22.0.18')}:8080"
        deps = AgentDeps(repo_root=_REPO_ROOT, env=env, pyhss_api=pyhss_api)

        agent = create_agent()
        result = await agent.run(question, deps=deps)

        if result and result.output:
            out = result.output.model_dump()
            # Include the full diagnosis as raw text for the LLM scorer
            out["_raw_diagnosis"] = json.dumps(out, indent=2, default=str)
            # Attach token usage from pydantic-ai
            usage = result.usage()
            out["_token_usage"] = {
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "total_tokens": usage.input_tokens + usage.output_tokens,
                "requests": usage.requests,
                "tool_calls": usage.tool_calls,
            }
            return out

        return {"_raw_diagnosis": "Agent produced no output"}

    async def _run_adk_agent(
        self, question: str, version: str = "v3",
        anomaly_window_hint_seconds: int = 300,
        metric_snapshots: list | None = None,
        observation_window_duration: int = 0,
        seconds_since_observation: int = 0,
    ) -> dict:
        """Run an ADK multi-phase troubleshooting agent (v3, v4, v5, v6, or v7)."""
        if version == "v7":
            from agentic_ops_v7.orchestrator import investigate
            import os as _os
            # v7 inherits v6's episode-scoped event store; the env var is shared.
            episode_id = _os.environ.get("V6_EPISODE_ID")
            result = await investigate(
                question,
                anomaly_window_hint_seconds=anomaly_window_hint_seconds,
                metric_snapshots=metric_snapshots or [],
                observation_window_duration=observation_window_duration,
                seconds_since_observation=seconds_since_observation,
                episode_id=episode_id,
            )
        elif version == "v6":
            from agentic_ops_v6.orchestrator import investigate
            import os as _os
            # Pass the chaos episode_id via env so v6 can scope its event store query
            episode_id = _os.environ.get("V6_EPISODE_ID")
            result = await investigate(
                question,
                anomaly_window_hint_seconds=anomaly_window_hint_seconds,
                metric_snapshots=metric_snapshots or [],
                observation_window_duration=observation_window_duration,
                seconds_since_observation=seconds_since_observation,
                episode_id=episode_id,
            )
        elif version == "v5":
            from agentic_ops_v5.orchestrator import investigate
            result = await investigate(
                question,
                anomaly_window_hint_seconds=anomaly_window_hint_seconds,
                metric_snapshots=metric_snapshots or [],
                observation_window_duration=observation_window_duration,
                seconds_since_observation=seconds_since_observation,
            )
        elif version == "v4":
            from agentic_ops_v4.orchestrator import investigate
            result = await investigate(question)
        else:
            from agentic_ops_v3.orchestrator import investigate
            result = await investigate(question)

        # The raw diagnosis text — passed directly to the LLM scorer
        diagnosis_raw = str(result.get("diagnosis", ""))

        # Extract token usage from v3's investigation trace
        trace = result.get("investigation_trace", {})
        total_tokens_obj = trace.get("total_tokens", {})
        token_usage = {
            "input_tokens": total_tokens_obj.get("prompt", 0),
            "output_tokens": total_tokens_obj.get("completion", 0),
            "thinking_tokens": total_tokens_obj.get("thinking", 0),
            "total_tokens": total_tokens_obj.get("total", result.get("total_tokens", 0)),
        }
        # Include per-phase breakdown
        phases = trace.get("phases", [])
        if phases:
            token_usage["per_phase"] = [
                {
                    "agent": p.get("agent_name", "?"),
                    "tokens": p.get("tokens", {}).get("total", 0),
                    "tool_calls": len(p.get("tool_calls", [])),
                    "llm_calls": p.get("llm_calls", 0),
                }
                for p in phases
            ]

        return {
            "_raw_diagnosis": diagnosis_raw,
            "_token_usage": token_usage,
            "_anomaly_report": result.get("anomaly_report", ""),
            "_network_analysis": result.get("network_analysis", ""),
            "_pattern_match": result.get("pattern_match", ""),
            "_investigation_instruction": result.get("investigation_instruction", ""),
            "_investigation": result.get("investigation", ""),
            "_evidence_validation": result.get("evidence_validation", ""),
            # v6-native keys (populated by v6 orchestrator; empty for v5)
            "_fired_events": result.get("fired_events", ""),
            "_correlation_analysis": result.get("correlation_analysis", ""),
            # v7-native keys (populated by v7's Phase 0.5 + 0.6; None when
            # the application-layer pipeline ran without engaging the
            # transport-layer route). Surfaced so the live-stack contract
            # test runbook can verify them and so debug runs can see why
            # Phase 0.6 returned null localization.
            "_symptom_classification": result.get("symptom_classification"),
            "_resolved_path":          result.get("resolved_path"),
            "_path_walk_report":       result.get("path_walk_report"),
            # Per-flow walker reports keyed by flow_id — populated when the
            # prioritizer returned multiple candidates and the walker walked
            # them all in parallel. None when only one candidate was walked.
            # ADR: docs/ADR/path_prioritizer_walks_all_candidates.md
            "_path_walk_all_reports":  result.get("path_walk_all_reports"),
            "_diagnosis_report":       result.get("diagnosis_report"),
            # v7 RAG observability (Phase 2.5 / 2.5b + post-Phase-3 citation
            # scan). All three are None when the localized branch fired
            # (Phases 1-7 didn't run). Forwarded into challenge_result so
            # the recorder can render the "RAG & Operational Lessons"
            # section in the episode markdown.
            "_rag_retrieval_metadata":   result.get("rag_retrieval_metadata"),
            "_lessons_injection_metadata": result.get("lessons_injection_metadata"),
            "_rag_na_citations":         result.get("rag_na_citations"),
        }

    async def _run_live_impl(self, ctx):
        raise NotImplementedError
