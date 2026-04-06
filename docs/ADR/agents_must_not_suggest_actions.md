# ADR: RCA Agents Must Not Suggest State-Changing Actions

**Date:** 2026-04-06
**Status:** Implemented (2026-04-06)
**Related:**
- `docs/ADR/anomaly_detection_layer.md` — parent ADR where this issue was first identified
- `agentic_ops_v5/docs/agent_logs/run_20260405_223112_p_cscf_latency.md` — Run 1 (500ms latency, scored 100%)
- `agentic_ops_v5/docs/agent_logs/run_20260405_231838_p_cscf_latency.md` — Run 2 (5000ms latency, scored 25%)

## Context

RCA agents in the v5 pipeline are **diagnostic observers**. They collect metrics, read logs, probe connectivity, query the ontology, and reason about what they find. They have no tools to modify the network — no ability to place calls, restart containers, change configs, or inject/remove faults. This is by design: the operator makes decisions and takes actions; the agent provides diagnosis.

However, in two consecutive P-CSCF Latency scenario runs on 2026-04-05, both the NetworkAnalystAgent (Phase 1) and the InstructionGeneratorAgent (Phase 4) suggested state-changing actions that the agent cannot execute and should not recommend.

### Evidence from Run 1 (`run_20260405_223112_p_cscf_latency`)

The NetworkAnalystAgent's `investigation_hint` output:

> If a problem is still suspected, attempt to place a VoNR call. If the call fails, re-run this analysis during the active call attempt to capture in-progress failures.

The InstructionGeneratorAgent propagated this directly into its Phase 4 output:

> **ACTION:** Attempt to place a VoNR call. If the call fails, **immediately re-run this analysis during the active call attempt** to capture in-progress failures and metrics.

### Evidence from Run 2 (`run_20260405_231838_p_cscf_latency`)

The InstructionGeneratorAgent again recommended:

> If an active test call is feasible, initiate one and monitor all relevant KPIs and logs in real-time to reproduce the issue and identify the failure point.

### Why this is wrong

1. **The agent has no tool to place a call.** VoNR calls are placed via the GUI's `/api/ue/{ue}/call` endpoint or via pjsua shell commands (`echo m >> /tmp/pjsua_cmd`). None of the v5 agents have access to either mechanism. Suggesting an action the agent cannot take wastes the Investigator's reasoning budget and may lead it to hallucinate having taken the action.

2. **The chaos framework had already generated traffic.** The P-CSCF Latency scenario has `required_traffic="control_plane"`, which triggers the `ControlPlaneTrafficAgent` to send `rr` (re-register) commands to both UEs *before* the RCA agent is invoked. Fresh SIP REGISTER transactions had already traversed the delayed P-CSCF path. The symptoms were already present in the metrics — the agent just didn't detect them (see `docs/ADR/anomaly_detection_layer.md`). Suggesting "generate traffic to surface symptoms" when traffic was already generated indicates the agent doesn't know what has already been done.

3. **Agents should never recommend remediation actions.** Beyond call placement, the same principle applies to: restarting containers, modifying configs, removing tc rules, clearing databases, re-provisioning subscribers. The agent's job ends at diagnosis. The operator decides what to do about it. An agent that says "remove the traffic shaping rule using `tc qdisc del dev eth0 root`" (as happened in Run 1) is overstepping its role and — worse — leaking knowledge of the injection mechanism.

### Why the LLM does this

The LLM draws on general NOC (Network Operations Center) knowledge from training data. In real NOC playbooks, the troubleshooting flow often includes "if passive observation is inconclusive, trigger synthetic traffic" and "recommended remediation: restart the affected service." These are reasonable suggestions for a human operator but inappropriate for a diagnostic agent that:
- Has a fixed, read-only toolset
- Runs in an automated pipeline (not an interactive session with a human)
- Must not modify the system under observation (doing so would invalidate the diagnosis)

The prompts are permissive by omission — they define what the agent *should* do (collect, analyze, cite evidence) but never explicitly state what it *must not* do.

## Decision

All RCA agent prompts must include an explicit constraint prohibiting state-changing action suggestions. The constraint must be:
- Present in every agent that produces text output (NetworkAnalyst, InstructionGenerator, Investigator, Synthesis)
- Framed as a hard rule, not a suggestion
- Specific enough to cover the observed violations (call placement, container restart, config modification, tc rule removal)

### Prompt language

Add the following to `network_analyst.md`, `instruction_generator.md`, `investigator.md`, and `synthesis.md`:

```
## Observation-Only Constraint (MANDATORY)

You are a passive diagnostic observer. You MUST NOT suggest, recommend, or instruct
any action that modifies the network state. This includes but is not limited to:
- Placing or initiating voice calls, data sessions, or SIP transactions
- Restarting, stopping, or killing containers or processes
- Modifying configuration files or environment variables
- Adding, removing, or changing network rules (routing, firewall, traffic shaping)
- Re-provisioning subscribers or clearing databases
- Re-running the analysis pipeline or "trying again"

Your role ends at diagnosis. The operator decides what actions to take.
If you cannot determine the root cause from available observations, say so explicitly
and explain what additional data points would help — but do not suggest generating
that data by modifying the system.
```

### Affected prompts

| Prompt file | Current state | What to add |
|---|---|---|
| `agentic_ops_v5/prompts/network_analyst.md` | No action constraint. `investigation_hint` field is free-form text where the LLM suggested "place a VoNR call." | Add the constraint in the Rules section. Also add to Step 4 (investigation hint): "The hint must describe what to OBSERVE, not what to DO." |
| `agentic_ops_v5/prompts/instruction_generator.md` | No action constraint. Rule 3 ("If everything looks green...") says "Perform a full bottom-up investigation" which is appropriate, but the LLM adds its own action suggestions on top. | Add the constraint before the Rules section. |
| `agentic_ops_v5/prompts/investigator.md` | Has evidence rules and hierarchy of truth but no action constraint. The LLM recommended `docker exec pcscf tc qdisc del dev eth0 root` in Run 1. | Add the constraint after the Evidence Rules section. |
| `agentic_ops_v5/prompts/synthesis.md` | No action constraint. The Synthesis agent produces the final `recommendation` field which is where remediation advice ends up. | Add the constraint with a specific carve-out: "The `recommendation` field should describe what the operator should INVESTIGATE further or VERIFY, not what they should change." |

## Consequences

**Positive:**
- Eliminates a class of hallucinated actions that waste investigation budget
- Prevents the Investigator from believing it has taken an action it cannot take
- Prevents remediation advice from leaking injection mechanism knowledge (e.g., "remove the tc netem rule")
- Makes the agent's role unambiguous: observe, analyze, diagnose — never act

**Negative:**
- The agent can no longer suggest useful next steps for the operator (e.g., "try placing a call to reproduce"). This is acceptable — the operator knows their own playbook. The agent's value is in diagnosis, not operational guidance.
- The `recommendation` field in the diagnosis output becomes narrower in scope. It should suggest what to verify or investigate further, not what to fix.
