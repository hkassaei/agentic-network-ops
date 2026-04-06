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
    """Render the NetworkAnalysis Pydantic dict as readable markdown."""
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

    # Suspect components
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

    # Investigation hint
    hint = data.get("investigation_hint", "")
    if hint:
        out.append(f"**Investigation hint:** {hint}")
        out.append("")

    # Tools called
    tools = data.get("tools_called") or []
    if tools:
        out.append(f"**Tools called:** {', '.join(tools)}")
        out.append("")

    return out


def _format_pattern_match(value) -> list[str]:
    """Render PatternMatcher JSON output as readable markdown."""
    data = _coerce_to_dict(value)
    if not data:
        return ["```", str(value)[:500], "```"]

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

    # Pipeline intermediate state — v5 5-phase pipeline
    challenge = episode.get("challenge_result") or {}

    network_analysis = challenge.get("network_analysis", "")
    lines.append("## Network Analysis (Phase 1)")
    lines.append("")
    if network_analysis:
        lines.extend(_format_network_analysis(network_analysis))
    else:
        lines.append("*No output produced.*")
    lines.append("")

    pattern_match = challenge.get("pattern_match", "")
    lines.append("## Pattern Match (Phase 2)")
    lines.append("")
    if pattern_match:
        lines.extend(_format_pattern_match(pattern_match))
    else:
        lines.append("*No output produced.*")
    lines.append("")

    investigation_instruction = challenge.get("investigation_instruction", "")
    lines.append("## Investigation Instruction (Phase 3)")
    lines.append("")
    if investigation_instruction:
        # Render as a blockquote, preserving line breaks
        for ln in str(investigation_instruction).splitlines():
            lines.append(f"> {ln}" if ln.strip() else ">")
    else:
        lines.append("*No output produced.*")
    lines.append("")

    # Legacy support: ontology_diagnosis from older v5 runs
    ontology_diag = challenge.get("ontology_diagnosis", "")
    if ontology_diag and not pattern_match:
        lines.append("## Ontology Analysis")
        lines.append("")
        lines.append(f"```")
        lines.append(ontology_diag)
        lines.append(f"```")
        lines.append("")

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

    ims_nfs = {"pcscf", "icscf", "scscf", "pyhss", "rtpengine"}
    core_nfs = {"amf", "smf", "upf", "nrf", "scp", "ausf", "udm", "udr", "pcf"}
    data_nfs = {"mongo", "mysql", "dns"}

    if targets & ims_nfs:
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
