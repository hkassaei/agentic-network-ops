"""
Episode Recorder — assembles a complete Episode from session state and writes JSON + markdown.

This is the primary output product of the chaos platform. Each scenario run
produces two files per agent:
  1. JSON episode log — machine-readable record of everything that happened
  2. Markdown summary — plain-English analysis for human review

Files are written to the respective agent's log directory:
  - v1.5: agentic_ops/docs/agent_logs/
  - v3:   agentic_ops_v3/docs/agent_logs/
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator

from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.genai import types

log = logging.getLogger("chaos-agent.recorder")

_EPISODES_DIR = Path(__file__).resolve().parent / "episodes"
_OPERATE_DIR = Path(__file__).resolve().parents[1]  # operate/

_AGENT_LOG_DIRS = {
    "v1.5": _OPERATE_DIR / "agentic_ops" / "docs" / "agent_logs",
    "v3": _OPERATE_DIR / "agentic_ops_v3" / "docs" / "agent_logs",
    "v4": _OPERATE_DIR / "agentic_ops_v4" / "docs" / "agent_logs",
    "v5": _OPERATE_DIR / "agentic_ops_v5" / "docs" / "agent_logs",
    "v6": _OPERATE_DIR / "agentic_ops_v6" / "docs" / "agent_logs",
}


class EpisodeRecorder(BaseAgent):
    """Assembles a complete Episode from session.state and writes it to disk."""

    name: str = "EpisodeRecorder"
    description: str = "Records the complete chaos episode as a structured JSON file."

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        state = ctx.session.state

        episode_id = state.get("episode_id", "ep_unknown")
        scenario = state.get("scenario", {})
        baseline = state.get("baseline", {})
        faults_injected = state.get("faults_injected", [])
        observations = state.get("observations", [])
        resolution = state.get("resolution", {})

        # Compute duration
        start_ts = baseline.get("timestamp", "")
        end_ts = resolution.get("healed_at", "")
        duration = 0.0
        if start_ts and end_ts:
            try:
                start = datetime.fromisoformat(start_ts)
                end = datetime.fromisoformat(end_ts)
                duration = (end - start).total_seconds()
            except (ValueError, TypeError):
                pass

        # Build the RCA label from the scenario (ground truth)
        successful_faults = [f for f in faults_injected if f.get("success")]
        targets = list({f["target"] for f in successful_faults})
        rca_label = {
            "root_cause": scenario.get("description", ""),
            "affected_components": targets,
            "severity": "degraded" if successful_faults else "healthy",
            "failure_domain": _infer_failure_domain(scenario),
            "protocol_impact": _infer_protocol_impact(scenario),
        }

        episode = {
            "schema_version": "1.0",
            "episode_id": episode_id,
            "timestamp": baseline.get("timestamp", datetime.now(timezone.utc).isoformat()),
            "duration_seconds": duration,
            "scenario": scenario,
            "baseline": baseline,
            "faults": successful_faults,
            "fault_verification": state.get("fault_verification"),
            "observations": observations,
            "resolution": resolution,
            "rca_label": rca_label,
            "challenge_result": state.get("challenge_result"),
        }

        # Determine output directory based on agent version
        agent_version = state.get("agent_version", "v1.5")
        agent_logs_dir = _AGENT_LOG_DIRS.get(agent_version, _EPISODES_DIR)
        agent_logs_dir.mkdir(parents=True, exist_ok=True)

        # Build filename from scenario slug
        slug = scenario.get("name", "unknown").lower().replace(" ", "_").replace("-", "_")[:30]
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        base_name = f"run_{ts}_{slug}"

        # Write JSON to agent logs directory
        json_path = agent_logs_dir / f"{base_name}.json"
        with open(json_path, "w") as f:
            json.dump(episode, f, indent=2, default=str)

        # Generate and write markdown summary
        md_path = agent_logs_dir / f"{base_name}.md"
        md_content = _generate_markdown_summary(episode, agent_version)
        with open(md_path, "w") as f:
            f.write(md_content)

        log.info("Episode recorded: %s (%.1fs, %d faults, %d observations)",
                 json_path, duration, len(successful_faults), len(observations))
        log.info("Markdown summary: %s", md_path)

        msg = (
            f"Episode recorded ({agent_version}):\n"
            f"  JSON: {json_path}\n"
            f"  Summary: {md_path}\n"
            f"  Duration: {duration:.1f}s\n"
            f"  Faults: {len(successful_faults)}\n"
            f"  Observations: {len(observations)}\n"
            f"  Symptoms detected: {any(o.get('symptoms_detected') for o in observations)}"
        )

        yield Event(
            author=self.name,
            content=types.Content(parts=[types.Part(text=msg)]),
            actions=EventActions(state_delta={
                "episode": episode,
                "episode_path": str(json_path),
                "markdown_path": str(md_path),
            }),
        )

    async def _run_live_impl(self, ctx):
        raise NotImplementedError


# -------------------------------------------------------------------------
# Formatters for structured v5 pipeline output
# -------------------------------------------------------------------------

_RATING_ICON = {"green": "🟢", "yellow": "🟡", "red": "🔴"}


def _extract_rating(rating) -> str:
    """Normalize a rating value to a lowercase string.

    Handles:
      - plain strings: 'green', 'GREEN', 'Green'
      - enum objects: LayerRating.GREEN → 'green'
      - enum repr strings that slipped through: 'LayerRating.GREEN' → 'green'
    """
    if rating is None:
        return ""
    # If it's an Enum instance, use its value
    if hasattr(rating, "value"):
        return str(rating.value).lower()
    s = str(rating).lower()
    # Strip "classname." prefix if present
    if "." in s:
        s = s.split(".", 1)[1]
    return s


def _coerce_to_dict(value) -> dict | None:
    """Accept a dict, a JSON string, or a Python repr and return a dict or None."""
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return None
    s = value.strip()
    if not s:
        return None
    # Try JSON first
    try:
        return json.loads(s)
    except (json.JSONDecodeError, ValueError):
        pass
    # Fall back to ast.literal_eval for Python repr (e.g. {'foo': <Enum.X>})
    try:
        import ast
        # Strip enum reprs like <LayerRating.RED: 'red'> → 'red'
        import re
        cleaned = re.sub(r"<\w+\.\w+:\s*('[^']*'|\"[^\"]*\")>", r"\1", s)
        parsed = ast.literal_eval(cleaned)
        return parsed if isinstance(parsed, dict) else None
    except (ValueError, SyntaxError):
        return None


def _format_network_analysis(value) -> list[str]:
    """Render the NetworkAnalysis Pydantic dict as readable markdown.

    Handles both v5 schema (suspect_components + investigation_hint) and
    v6 schema (hypotheses with falsification_probes).
    """
    data = _coerce_to_dict(value)
    if not data:
        # Not parseable — fall back to raw text in a code block
        return ["```", str(value)[:800], "```"]

    out: list[str] = []

    summary = data.get("summary", "")
    if summary:
        out.append(f"**Summary:** {summary}")
        out.append("")

    # Layer status table
    layer_status = data.get("layer_status", {}) or {}
    if layer_status:
        out.append("**Layer status:**")
        out.append("")
        out.append("| Layer | Rating | Note |")
        out.append("|---|---|---|")
        for layer in ["infrastructure", "ran", "core", "ims"]:
            ls = layer_status.get(layer, {})
            if not isinstance(ls, dict):
                continue
            rating = _extract_rating(ls.get("rating"))
            icon = _RATING_ICON.get(rating, "")
            note = (ls.get("note") or "").replace("|", "\\|")
            out.append(f"| **{layer}** | {icon} {rating.upper()} | {note} |")
        out.append("")

        # Evidence per non-green layer
        for layer in ["infrastructure", "ran", "core", "ims"]:
            ls = layer_status.get(layer, {})
            if not isinstance(ls, dict):
                continue
            rating = _extract_rating(ls.get("rating"))
            if rating == "green":
                continue
            evidence = ls.get("evidence") or []
            if not evidence:
                continue
            out.append(f"**{layer.upper()} evidence:**")
            for item in evidence:
                out.append(f"- {item}")
            out.append("")

    # v5: Suspect components
    suspects = data.get("suspect_components") or []
    if suspects:
        out.append("**Suspect components:**")
        out.append("")
        for s in suspects:
            if not isinstance(s, dict):
                continue
            name = s.get("name", "?")
            conf = s.get("confidence", "?")
            reason = s.get("reason", "")
            out.append(f"- **{name}** ({conf}): {reason}")
        out.append("")

    # v6: Ranked hypotheses
    hypotheses = data.get("hypotheses") or []
    if hypotheses:
        out.append("**Ranked hypotheses:**")
        out.append("")
        for h in hypotheses:
            if not isinstance(h, dict):
                continue
            hid = h.get("id", "?")
            statement = h.get("statement", "")
            nf = h.get("primary_suspect_nf", "?")
            fit = h.get("explanatory_fit", 0.0)
            spec = h.get("specificity", "?")
            support = h.get("supporting_events") or []
            probes = h.get("falsification_probes") or []
            try:
                fit_str = f"{float(fit):.2f}"
            except (TypeError, ValueError):
                fit_str = "?"
            out.append(f"- **`{hid}`** (fit={fit_str}, nf={nf}, specificity={spec}):")
            out.append(f"    - **Statement:** {statement}")
            if support:
                out.append(
                    "    - **Supporting events:** "
                    + ", ".join(f"`{s}`" for s in support)
                )
            if probes:
                out.append("    - **Falsification probes:**")
                for p in probes:
                    out.append(f"        - {p}")
        out.append("")

    # Investigation hint (v5 only)
    hint = data.get("investigation_hint", "")
    if hint:
        out.append(f"**Investigation hint:** {hint}")
        out.append("")

    # Tools called (v5 only)
    tools = data.get("tools_called") or []
    if tools:
        out.append(f"**Tools called:** {', '.join(tools)}")
        out.append("")

    return out


def _format_pattern_match(value) -> list[str]:
    """Render the Phase-2 output as readable markdown.

    Handles both:
      - v5 PatternMatcher JSON (dict with matched/top_diagnosis/confidence)
      - v6 CorrelationAnalyzer rendered markdown (plain text)
    """
    # v6: correlation analyzer produces plain markdown text directly
    if isinstance(value, str) and value.strip().startswith("**"):
        return [value]

    data = _coerce_to_dict(value)
    if not data:
        # Plain markdown rendering (v6) — return as-is, no code-block wrapping
        return [str(value)] if value else []

    out: list[str] = []

    matched = data.get("matched", False)
    top = data.get("top_diagnosis", "?")
    confidence = data.get("confidence", "?")
    failure_domain = data.get("failure_domain", "?")

    status_icon = "✅" if matched else "❌"
    out.append(f"**{status_icon} Match:** {top}")
    out.append("")
    out.append(f"- **Confidence:** {confidence}")
    out.append(f"- **Failure domain:** {failure_domain}")

    sigs = data.get("matched_signatures") or []
    if sigs and isinstance(sigs[0], dict):
        out.append(f"- **Matched signatures:** {len(sigs)}")
        for sig in sigs[:3]:
            sid = sig.get("signature_id", "?")
            score = sig.get("match_score", "?")
            out.append(f"  - `{sid}` (score: {score})")

    anomalies = data.get("baseline_anomalies") or {}
    if anomalies:
        count = sum(len(v) for v in anomalies.values() if isinstance(v, list))
        out.append(f"- **Baseline anomalies:** {count} metrics across {len(anomalies)} components")

    out.append("")
    return out


def _format_investigation_instruction(value) -> list[str]:
    """Render Phase 3 output.

    v5: plain text instruction (one block).
    v6: FalsificationPlanSet dict with plans list — one plan per hypothesis.
    """
    data = _coerce_to_dict(value)
    if data and isinstance(data.get("plans"), list):
        # v6 shape
        out: list[str] = []
        plans = data.get("plans") or []
        if not plans:
            return ["*(No falsification plans generated.)*"]
        out.append(f"**{len(plans)} falsification plan(s) — one per hypothesis:**")
        out.append("")
        for plan in plans:
            if not isinstance(plan, dict):
                continue
            hid = plan.get("hypothesis_id", "?")
            stmt = plan.get("hypothesis_statement", "")
            nf = plan.get("primary_suspect_nf", "?")
            probes = plan.get("probes") or []
            notes = plan.get("notes", "")
            out.append(f"### Plan for `{hid}` (target: `{nf}`)")
            out.append("")
            if stmt:
                out.append(f"**Hypothesis:** {stmt}")
                out.append("")
            out.append(f"**Probes ({len(probes)}):**")
            for i, p in enumerate(probes, 1):
                if not isinstance(p, dict):
                    continue
                tool = p.get("tool", "?")
                args_hint = p.get("args_hint", "")
                exp_hold = p.get("expected_if_hypothesis_holds", "")
                falsify = p.get("falsifying_observation", "")
                out.append(f"{i}. **`{tool}`** — {args_hint}")
                if exp_hold:
                    out.append(f"    - *Expected if hypothesis holds:* {exp_hold}")
                if falsify:
                    out.append(f"    - *Falsifying observation:* {falsify}")
            if notes:
                out.append("")
                out.append(f"*Notes:* {notes}")
            out.append("")
        return out
    # v5 fallback — blockquote plain text
    out = []
    for ln in str(value).splitlines():
        out.append(f"> {ln}" if ln.strip() else ">")
    return out


def _format_investigation(value) -> list[str]:
    """Render Phase 4 output.

    v5: plain text investigation report with [EVIDENCE: ...] citations.
    v6: JSON list of InvestigatorVerdict (one per hypothesis).
    """
    # Try to parse v6 verdict list
    verdicts: list[dict] = []
    if isinstance(value, list):
        verdicts = [v for v in value if isinstance(v, dict)]
    elif isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                verdicts = [v for v in parsed if isinstance(v, dict)]
        except (json.JSONDecodeError, ValueError):
            pass

    if verdicts:
        out: list[str] = []
        # Summary counts per verdict type
        counts: dict[str, int] = {}
        for v in verdicts:
            key = v.get("verdict", "?")
            counts[key] = counts.get(key, 0) + 1
        summary = ", ".join(f"**{c} {k}**" for k, c in counts.items())
        out.append(f"**{len(verdicts)} sub-Investigator verdict(s):** {summary}")
        out.append("")
        for v in verdicts:
            hid = v.get("hypothesis_id", "?")
            stmt = v.get("hypothesis_statement", "")
            verdict = v.get("verdict", "?")
            reasoning = v.get("reasoning", "")
            probes = v.get("probes_executed") or []
            alts = v.get("alternative_suspects") or []
            icon = {
                "DISPROVEN": "❌", "NOT_DISPROVEN": "✅",
                "INCONCLUSIVE": "❓",
            }.get(verdict, "")
            out.append(f"### `{hid}` — {icon} **{verdict}**")
            out.append("")
            if stmt:
                out.append(f"**Hypothesis:** {stmt}")
                out.append("")
            if reasoning:
                out.append(f"**Reasoning:** {reasoning}")
                out.append("")
            if probes:
                out.append(f"**Probes executed ({len(probes)}):**")
                for p in probes:
                    if not isinstance(p, dict):
                        continue
                    desc = p.get("probe_description", "")
                    tool = p.get("tool_call", "")
                    obs = p.get("observation", "")
                    cmp = p.get("compared_to_expected", "?")
                    note = p.get("commentary", "")
                    cmp_icon = {
                        "CONSISTENT": "✓", "CONTRADICTS": "✗", "AMBIGUOUS": "~",
                    }.get(cmp, "")
                    out.append(f"- **{desc}** {cmp_icon} {cmp}")
                    if tool:
                        out.append(f"    - *Tool:* `{tool}`")
                    if obs:
                        # Truncate very long observations
                        obs_short = obs if len(obs) <= 400 else obs[:400] + "…"
                        out.append(f"    - *Observation:* {obs_short}")
                    if note:
                        out.append(f"    - *Comment:* {note}")
                out.append("")
            if alts:
                out.append(f"**Alternative suspects:** {', '.join(alts)}")
                out.append("")
        return out

    # v5 fallback — blockquote plain text
    out = []
    for ln in str(value).splitlines():
        out.append(f"> {ln}" if ln.strip() else ">")
    return out


def _format_evidence_validation(value) -> list[str]:
    """Render Phase 5/6 output.

    v5: dict with verdict/investigator_confidence/matched/total_citations/summary.
    v6: dict with overall_verdict/overall_confidence/per_agent list/summary.
    """
    data = _coerce_to_dict(value)
    if not data:
        return [str(value)]

    out: list[str] = []

    # v6 shape
    if "per_agent" in data:
        out.append(f"**Overall verdict:** {data.get('overall_verdict', '?')}")
        out.append(f"**Overall confidence:** {data.get('overall_confidence', '?')}")
        out.append("")
        per_agent = data.get("per_agent") or []
        if per_agent:
            out.append("**Per sub-Investigator:**")
            out.append("")
            out.append("| Agent | Tool Calls | Citations | Verdict | Confidence |")
            out.append("|---|---|---|---|---|")
            for p in per_agent:
                if not isinstance(p, dict):
                    continue
                name = p.get("agent_name", "?")
                tcs = p.get("tool_calls_made", "?")
                cits = f"{p.get('citations_matched', '?')}/{p.get('citations_found', '?')}"
                verdict = p.get("verdict", "?")
                conf = p.get("confidence", "?")
                out.append(f"| `{name}` | {tcs} | {cits} | {verdict} | {conf} |")
                notes = p.get("notes") or []
                for n in notes:
                    out.append(f"|  |  |  |  | *{n}* |")
            out.append("")
        return out

    # v5 shape
    out.append(f"**Verdict:** {data.get('verdict', '?')}")
    out.append(f"**Investigator confidence:** {data.get('investigator_confidence', '?')}")
    out.append(f"**Citations:** {data.get('matched', 0)}/{data.get('total_citations', 0)} verified")
    if data.get('investigator_made_zero_calls'):
        out.append("")
        out.append("**WARNING:** Investigator made ZERO tool calls — all evidence citations are fabricated.")
    summary = data.get('summary', '')
    if summary:
        out.append("")
        out.append(f"```\n{summary}\n```")
    return out


def _render_v5_pipeline(challenge: dict) -> list[str]:
    """v5 pipeline layout: 6 phases, PatternMatcher at Phase 2."""
    out: list[str] = []

    anomaly_report = challenge.get("anomaly_report", "")
    out.append("## Anomaly Screening (Phase 0)")
    out.append("")
    out.append(str(anomaly_report) if anomaly_report else "*No anomaly screening output.*")
    out.append("")

    network_analysis = challenge.get("network_analysis", "")
    out.append("## Network Analysis (Phase 1)")
    out.append("")
    if network_analysis:
        out.extend(_format_network_analysis(network_analysis))
    else:
        out.append("*No output produced.*")
    out.append("")

    pattern_match = challenge.get("pattern_match", "")
    out.append("## Pattern Match (Phase 2)")
    out.append("")
    if pattern_match:
        out.extend(_format_pattern_match(pattern_match))
    else:
        out.append("*No output produced.*")
    out.append("")

    investigation_instruction = challenge.get("investigation_instruction", "")
    out.append("## Investigation Instruction (Phase 3)")
    out.append("")
    if investigation_instruction:
        out.extend(_format_investigation_instruction(investigation_instruction))
    else:
        out.append("*No output produced.*")
    out.append("")

    investigation = challenge.get("investigation", "")
    out.append("## Investigation (Phase 4)")
    out.append("")
    if investigation:
        out.extend(_format_investigation(investigation))
    else:
        out.append("*No investigation output produced.*")
    out.append("")

    evidence_validation = challenge.get("evidence_validation", "")
    out.append("## Evidence Validation (Phase 5)")
    out.append("")
    if evidence_validation:
        out.extend(_format_evidence_validation(evidence_validation))
    else:
        out.append("*No evidence validation output.*")
    out.append("")
    return out


def _render_v6_pipeline(challenge: dict) -> list[str]:
    """v6 pipeline layout: 8 phases with distinct Events + Correlation steps.

    Section numbering matches v6's execution order:
      0 AnomalyScreener  → 1 EventAggregator → 2 CorrelationAnalyzer
      → 3 NetworkAnalyst → 4 InstructionGenerator → 5 Investigator × N
      → 6 EvidenceValidator → 7 Synthesis (rendered as Agent Diagnosis)
    """
    out: list[str] = []

    # Phase 0 — Anomaly Screener (ML, no LLM)
    anomaly_report = challenge.get("anomaly_report", "")
    out.append("## Anomaly Screening (Phase 0)")
    out.append("")
    out.append(str(anomaly_report) if anomaly_report else "*No anomaly screening output.*")
    out.append("")

    # Phase 1 — Event Aggregator (Python, reads fired events from store)
    fired_events = challenge.get("fired_events", "")
    out.append("## Event Aggregation (Phase 1)")
    out.append("")
    out.append(
        str(fired_events) if fired_events else "*No events aggregated from the event store.*"
    )
    out.append("")

    # Phase 2 — Correlation Analyzer (Python, runs correlation engine)
    correlation_analysis = challenge.get("correlation_analysis", "")
    # Fall back to `pattern_match` for backward compat in case orchestrator
    # maps correlation output there too.
    if not correlation_analysis:
        correlation_analysis = challenge.get("pattern_match", "")
    out.append("## Correlation Analysis (Phase 2)")
    out.append("")
    if correlation_analysis:
        out.extend(_format_pattern_match(correlation_analysis))
    else:
        out.append("*No correlation analysis produced.*")
    out.append("")

    # Phase 3 — Network Analyst (LLM, ranked hypothesis former)
    network_analysis = challenge.get("network_analysis", "")
    out.append("## Network Analysis (Phase 3)")
    out.append("")
    if network_analysis:
        out.extend(_format_network_analysis(network_analysis))
    else:
        out.append("*No output produced.*")
    out.append("")

    # Phase 4 — Instruction Generator (LLM, per-hypothesis falsification plans)
    investigation_instruction = challenge.get("investigation_instruction", "")
    out.append("## Falsification Plans (Phase 4)")
    out.append("")
    if investigation_instruction:
        out.extend(_format_investigation_instruction(investigation_instruction))
    else:
        out.append("*No output produced.*")
    out.append("")

    # Phase 5 — Parallel Sub-Investigators
    investigation = challenge.get("investigation", "")
    out.append("## Parallel Investigators (Phase 5)")
    out.append("")
    if investigation:
        out.extend(_format_investigation(investigation))
    else:
        out.append("*No investigation output produced.*")
    out.append("")

    # Phase 6 — Evidence Validator (per-sub-Investigator citation check)
    evidence_validation = challenge.get("evidence_validation", "")
    out.append("## Evidence Validation (Phase 6)")
    out.append("")
    if evidence_validation:
        out.extend(_format_evidence_validation(evidence_validation))
    else:
        out.append("*No evidence validation output.*")
    out.append("")

    # Phase 7 — Synthesis is rendered below as "Agent Diagnosis" in the
    # unchanged shared section.
    return out


def _generate_markdown_summary(episode: dict, agent_version: str) -> str:
    """Generate a plain-English markdown summary of the episode."""
    scenario = episode.get("scenario", {})
    baseline = episode.get("baseline", {})
    faults = episode.get("faults", [])
    observations = episode.get("observations", [])
    resolution = episode.get("resolution", {})
    rca_label = episode.get("rca_label", {})
    challenge = episode.get("challenge_result")

    lines = [
        f"# Episode Report: {scenario.get('name', 'Unknown Scenario')}",
        "",
        f"**Agent:** {agent_version}  ",
        f"**Episode ID:** {episode.get('episode_id', '?')}  ",
        f"**Date:** {episode.get('timestamp', '?')}  ",
        f"**Duration:** {episode.get('duration_seconds', 0):.1f}s  ",
        "",
        "---",
        "",
        "## Scenario",
        "",
        f"**Category:** {scenario.get('category', '?')}  ",
        f"**Blast radius:** {scenario.get('blast_radius', '?')}  ",
        f"**Description:** {scenario.get('description', '?')}",
        "",
    ]

    # Faults injected
    lines.append("## Faults Injected")
    lines.append("")
    if faults:
        for f in faults:
            params_str = ""
            if f.get("params"):
                params_str = f" — {f['params']}"
            lines.append(
                f"- **{f.get('fault_type', '?')}** on `{f.get('target', '?')}`{params_str}"
            )
    else:
        lines.append("No faults were successfully injected.")
    lines.append("")

    # Baseline
    lines.append("## Baseline (Pre-Fault)")
    lines.append("")
    stack_phase = baseline.get("stack_phase", "?")
    lines.append(f"Stack phase before injection: **{stack_phase}**")
    container_status = baseline.get("container_status", {})
    if container_status:
        down = [c for c, s in container_status.items() if s != "running"]
        if down:
            lines.append(f"Containers not running at baseline: {', '.join(down)}")
        else:
            lines.append("All containers running at baseline.")
    lines.append("")

    # Fault Propagation Verification
    verification = episode.get("fault_verification") or {}
    if verification:
        verdict = verification.get("verdict", "?")
        verdict_icon = {
            "confirmed": "✅",
            "inconclusive": "⚠️",
            "not_observed": "❌",
        }.get(verdict, "?")
        lines.append("## Fault Propagation Verification")
        lines.append("")
        lines.append(f"**Verdict:** {verdict_icon} `{verdict}`")
        lines.append("")
        lines.append(f"- **Wait:** {verification.get('wait_seconds', '?')}s")
        lines.append(f"- **Actual elapsed:** {verification.get('elapsed_seconds', '?')}s")
        lines.append(
            f"- **Nodes with significant deltas:** "
            f"{len(verification.get('filtered_deltas', {}))}"
        )
        lines.append(
            f"- **Nodes with any drift:** "
            f"{verification.get('raw_delta_node_count', '?')}"
        )
        if verification.get("aborted"):
            lines.append(
                "- **⚠️ Episode aborted** — `--abort-on-unpropagated` was set"
            )
        lines.append("")

    # Symptoms observed
    lines.append("## Symptoms Observed")
    lines.append("")
    symptoms_detected = any(o.get("symptoms_detected") for o in observations)
    lines.append(f"Symptoms detected: **{'Yes' if symptoms_detected else 'No'}**  ")
    lines.append(f"Observation iterations: {len(observations)}")
    lines.append("")

    # Collect notable log samples and metrics deltas
    all_logs: dict[str, list[str]] = {}
    all_deltas: dict[str, dict] = {}
    for obs in observations:
        for container, log_lines in obs.get("log_samples", {}).items():
            all_logs.setdefault(container, []).extend(log_lines)
        for node, delta in obs.get("metrics_delta", {}).items():
            all_deltas.setdefault(node, {}).update(delta)

    if all_deltas:
        lines.append("### Metrics Changes")
        lines.append("")
        lines.append("| Node | Metric | Baseline | Current | Delta |")
        lines.append("|------|--------|----------|---------|-------|")
        for node, deltas in sorted(all_deltas.items()):
            for metric, vals in deltas.items():
                b = vals.get("baseline", "?")
                c = vals.get("current", "?")
                d = vals.get("delta", "?")
                lines.append(f"| {node} | {metric} | {b} | {c} | {d} |")
        lines.append("")

    # Notable log lines omitted from report — they contain stale logs
    # from previous runs and are not useful for diagnosis evaluation.

    # Pipeline intermediate state. v5 and v6 have genuinely different phase
    # layouts (v5 has 6 phases, v6 has 8 with Events + Correlation added
    # and NA shifted to Phase 3). Branch on agent_version so each version
    # renders its own pipeline faithfully.
    challenge = episode.get("challenge_result") or {}
    if agent_version == "v6":
        lines.extend(_render_v6_pipeline(challenge))
    else:
        lines.extend(_render_v5_pipeline(challenge))

    # Ground truth
    lines.append("## Ground Truth")
    lines.append("")
    lines.append(f"**Failure domain:** {rca_label.get('failure_domain', '?')}  ")
    lines.append(f"**Protocol impact:** {rca_label.get('protocol_impact', '?')}  ")
    lines.append(f"**Affected components:** {', '.join(rca_label.get('affected_components', []))}  ")
    lines.append(f"**Severity:** {rca_label.get('severity', '?')}")
    lines.append("")

    # Agent diagnosis and scoring
    lines.append("## Agent Diagnosis")
    lines.append("")
    if challenge:
        lines.append(f"**Model:** {challenge.get('rca_agent_model', '?')}  ")
        lines.append(
            f"**Time to diagnosis:** {challenge.get('time_to_diagnosis_seconds', 0):.1f}s"
        )
        lines.append("")

        # Show the prompt/context passed to the RCA agent
        prompt = challenge.get("prompt_to_agent", "")
        if prompt:
            lines.append("### Prompt to RCA Agent")
            lines.append("")
            lines.append(f"```")
            lines.append(prompt)
            lines.append(f"```")
            lines.append("")

        # Show the full diagnosis text
        diagnosis_text = challenge.get("diagnosis_text", "")
        if diagnosis_text:
            lines.append(f"**Diagnosis:**")
            lines.append("")
            lines.append(f"> {diagnosis_text.replace(chr(10), chr(10) + '> ')}")
            lines.append("")

        # Scoring breakdown with rationales from LLM judge
        score = challenge.get("score", {})
        if score:
            total = score.get("total_score", 0)
            lines.append("### Scoring Breakdown")
            lines.append("")
            lines.append(f"**Overall score: {total:.0%}**")
            lines.append("")

            # Summary from the LLM judge
            scorer_summary = score.get("summary", "")
            if scorer_summary:
                lines.append(f"**Scorer assessment:** {scorer_summary}")
                lines.append("")

            lines.append("| Dimension | Result | Rationale |")
            lines.append("|-----------|--------|-----------|")
            lines.append(
                f"| Root cause correct | {'Yes' if score.get('root_cause_correct') else 'No'} "
                f"| {score.get('root_cause_rationale', '')} |"
            )
            lines.append(
                f"| Component overlap | {score.get('component_overlap', 0):.0%} "
                f"| {score.get('component_rationale', '')} |"
            )
            lines.append(
                f"| Severity correct | {'Yes' if score.get('severity_correct') else 'No'} "
                f"| {score.get('severity_rationale', '')} |"
            )
            lines.append(
                f"| Fault type identified | {'Yes' if score.get('fault_type_identified') else 'No'} "
                f"| {score.get('fault_type_rationale', '')} |"
            )
            lines.append(
                f"| Layer accuracy | {'Yes' if score.get('layer_accuracy') else 'No'} "
                f"| {score.get('layer_accuracy_rationale', '')} |"
            )
            lines.append(
                f"| Confidence calibrated | {'Yes' if score.get('confidence_calibrated') else 'No'} "
                f"| {score.get('confidence_rationale', '')} |"
            )
            lines.append("")

            # Ranking position (for multi-candidate diagnoses)
            ranking = score.get("ranking_position")
            if ranking is not None:
                lines.append(
                    f"**Ranking position:** #{ranking} — {score.get('ranking_rationale', '')}"
                )
            elif score.get("ranking_rationale"):
                lines.append(
                    f"**Ranking:** {score.get('ranking_rationale', '')}"
                )
            lines.append("")

        # Token usage
        token_usage = challenge.get("token_usage", {})
        if token_usage:
            lines.append("")
            lines.append("### Token Usage")
            lines.append("")
            total_tokens = token_usage.get("total_tokens", 0)
            input_tokens = token_usage.get("input_tokens", 0)
            output_tokens = token_usage.get("output_tokens", 0)
            thinking_tokens = token_usage.get("thinking_tokens", 0)
            lines.append(f"| Metric | Count |")
            lines.append(f"|--------|-------|")
            lines.append(f"| Input tokens | {input_tokens:,} |")
            lines.append(f"| Output tokens | {output_tokens:,} |")
            if thinking_tokens:
                lines.append(f"| Thinking tokens | {thinking_tokens:,} |")
            lines.append(f"| **Total tokens** | **{total_tokens:,}** |")
            if token_usage.get("requests"):
                lines.append(f"| LLM requests | {token_usage['requests']} |")
            if token_usage.get("tool_calls"):
                lines.append(f"| Tool calls | {token_usage['tool_calls']} |")
            lines.append("")

            # Per-phase breakdown (v3 only)
            per_phase = token_usage.get("per_phase", [])
            if per_phase:
                lines.append("**Per-phase breakdown:**")
                lines.append("")
                lines.append("| Phase | Tokens | Tool Calls | LLM Calls |")
                lines.append("|-------|--------|------------|-----------|")
                for p in per_phase:
                    lines.append(
                        f"| {p.get('agent', '?')} | {p.get('tokens', 0):,} "
                        f"| {p.get('tool_calls', 0)} | {p.get('llm_calls', 0)} |"
                    )
                lines.append("")
    else:
        lines.append("Challenge mode was not run — no agent diagnosis available.")
    lines.append("")

    # Resolution
    lines.append("## Resolution")
    lines.append("")
    lines.append(f"**Heal method:** {resolution.get('heal_method', '?')}  ")
    lines.append(f"**Recovery time:** {resolution.get('recovery_time_seconds', 0):.1f}s")
    lines.append("")

    return "\n".join(lines)


def _infer_failure_domain(scenario: dict) -> str:
    """Infer the failure domain from the scenario's targets."""
    targets = set()
    for f in scenario.get("faults", []):
        targets.add(f.get("target", ""))

    ims_signaling_nfs = {"pcscf", "icscf", "scscf", "pyhss"}
    media_nfs = {"rtpengine"}
    core_nfs = {"amf", "smf", "upf", "nrf", "scp", "ausf", "udm", "udr", "pcf"}
    data_nfs = {"mongo", "mysql", "dns"}

    if targets & media_nfs:
        return "ims_media"
    if targets & ims_signaling_nfs:
        return "ims_signaling"
    if targets & {"upf", "nr_gnb"}:
        return "data_plane"
    if targets & core_nfs:
        return "core_control_plane"
    if targets & data_nfs:
        return "data_layer"
    return "unknown"


def _infer_protocol_impact(scenario: dict) -> str:
    """Infer the primary protocol impact from the scenario's targets."""
    targets = set()
    for f in scenario.get("faults", []):
        targets.add(f.get("target", ""))

    if targets & {"rtpengine"}:
        return "RTP"
    if targets & {"pcscf", "icscf", "scscf"}:
        return "SIP"
    if targets & {"pyhss"}:
        return "Diameter"
    if targets & {"upf", "nr_gnb"}:
        return "GTP-U"
    if targets & {"amf"}:
        return "NGAP"
    if targets & {"smf"}:
        return "PFCP"
    return "multiple"
