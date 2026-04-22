"""
Challenge Mode Scorer — LLM-based evaluation of RCA agent diagnosis.

The chaos platform injects faults to SIMULATE real-world failure modes. The
scorer evaluates the agent against the SIMULATED FAILURE MODE (what went wrong
from the network's perspective), NOT the injection mechanism (how we broke it).

Example: "Kill gNB to simulate a radio link failure"
  - The agent should diagnose: "radio link failure" / "RAN unreachable" / "N2 connectivity loss"
  - The agent should NOT need to know: "container was killed"
  - The scorer accepts any semantically equivalent description of the failure mode

Scoring dimensions:
  - root_cause_correct:    Did the agent identify the simulated failure mode?
  - component_overlap:     Did it name the right affected component(s)?
  - severity_correct:      Did it assess severity accurately?
  - fault_type_identified: Did it identify the observable class of failure?
  - layer_accuracy:        Did it attribute components to the correct ontology layers?
  - confidence_calibrated: Is confidence justified by evidence quality?
  - ranking_position:      Where did the correct cause rank in the agent's list?
"""

from __future__ import annotations

import json
import logging
import os

log = logging.getLogger("chaos-scorer")

_SCORER_MODEL = "gemini-2.5-flash"

# Component → ontology layer mapping (from network_ontology/data/components.yaml)
_COMPONENT_ONTOLOGY_LAYER = {
    "mongo": "infrastructure",
    "mysql": "infrastructure",
    "dns": "infrastructure",
    "webui": "infrastructure",
    "nrf": "core",
    "scp": "core",
    "ausf": "core",
    "udm": "core",
    "udr": "core",
    "amf": "core",
    "smf": "core",
    "pcf": "core",
    "upf": "core",
    "nssf": "core",
    "bsf": "core",
    "pcscf": "ims",
    "icscf": "ims",
    "scscf": "ims",
    "pyhss": "ims",
    "smsc": "ims",
    "rtpengine": "ims",
    "nr_gnb": "ran",
    "e2e_ue1": "ue",
    "e2e_ue2": "ue",
}

_SCORER_PROMPT = """\
You are an evaluation judge for a telecom troubleshooting agent. Your job is to
score how well the agent diagnosed a failure in a 5G SA + IMS network stack.

IMPORTANT CONTEXT: The failure was created by a chaos testing platform that uses
simulation techniques (killing containers, injecting tc netem rules, pausing
processes) to reproduce real-world failure modes. The agent has NO visibility
into the simulation mechanism — it can only observe the network from the
perspective of a NOC operator.

Therefore, you MUST score the agent against the SIMULATED FAILURE MODE (what
the failure looks like from the network), NOT the injection mechanism (how the
platform created it).

Example: If the platform killed a gNB container to simulate a radio link
failure, the agent should be scored on whether it diagnosed "radio link failure"
/ "RAN unreachable" / "N2 connectivity loss" / "gNB not responding" — NOT on
whether it said "container was killed."

You will receive:
1. SIMULATED FAILURE — what failure mode was being simulated and what the agent
   should have been able to observe
2. AGENT DIAGNOSIS — the agent's FINAL diagnosis, produced by the Synthesis
   agent after all investigation. This is the operator-facing output and is
   the AUTHORITATIVE artifact for scoring. It contains a `causes` block with
   `summary`, `root_cause`, `affected_components`, `confidence`, and
   `explanation` fields.
3. AGENT NETWORK ANALYSIS (optional) — the pipeline's intermediate Phase-3
   output, which contains a layer-status table. This is REASONING, not
   CONCLUSION. Use it ONLY for the `layer_accuracy` dimension. Do NOT use it
   to infer `root_cause_correct`, `component_overlap`, `severity_correct`,
   `fault_type_identified`, `confidence_calibrated`, or `ranking_position` —
   for all of those, evaluate strictly against the final AGENT DIAGNOSIS.

   Why this matters: an agent may correctly identify the right cause in
   Phase-3 reasoning and then walk it back to a different (wrong) conclusion
   in its final diagnosis. The operator only sees the final diagnosis. If the
   final `causes.root_cause` disagrees with what `NETWORK ANALYSIS` suggested,
   score the final diagnosis — not the intermediate reasoning.

Score the diagnosis on these dimensions:

## Scoring Dimensions

1. **root_cause_correct** (bool): Did the agent identify the simulated failure
   mode as the root cause? Evaluate strictly against the **final AGENT DIAGNOSIS**
   — specifically the `causes.root_cause` field, supported by
   `causes.summary` and `causes.explanation`. Do NOT score True based on what
   the NETWORK ANALYSIS section said; that's intermediate reasoning, not the
   agent's conclusion.

   Semantic equivalence counts — the agent doesn't need to use the exact same
   words. Accept any conclusion that describes the same observable failure
   from the network's perspective.

   Examples of EQUIVALENT final diagnoses for "radio link failure":
   - "RAN is unreachable" ✓
   - "N2 connectivity loss between gNB and AMF" ✓
   - "gNB not responding, 100% packet loss" ✓
   - "Transport failure on N2 path" ✓
   - "gNB container killed" ✓ (more specific than needed, but correct)

   Examples of WRONG final diagnoses:
   - "I-CSCF misconfiguration" ✗ (wrong component, wrong failure mode)
   - "HSS subscriber profile incomplete" ✗ (unrelated)

   **Walk-back test.** If the NETWORK ANALYSIS section said cause X but the
   final `causes.root_cause` section said cause Y (Y ≠ X), and Y is wrong,
   score **False** — the agent walked back its correct reasoning to a wrong
   conclusion. The operator-facing output is what matters.

   **Multiple candidates in the final diagnosis.** If the `causes` block
   itself lists multiple candidates (e.g. two root causes, or `root_cause`
   names one NF while `affected_components` lists a different NF as "Root
   Cause"), the correct cause must be named as the PRIMARY root cause to
   score True. Ties, ambiguity, or "root cause is undetermined" are scored
   False even if the correct NF appears elsewhere in the block.

2. **component_overlap** (float 0.0-1.0): Did the agent correctly identify
   the affected component(s)? Evaluate against the final AGENT DIAGNOSIS's
   `causes.affected_components` list. Score 1.0 if the primary affected
   component is listed as **"Root Cause"** in that list (not merely as
   "Secondary", "Symptomatic", or "Symptom"). Do NOT penalize for also
   listing cascading/downstream components — that shows correct causal
   reasoning.

   If the primary affected component appears in `affected_components` only
   as "Symptomatic" / "Secondary" while a different NF is labeled "Root
   Cause", score proportionally (e.g. 0.3) — the agent saw the component
   was involved but mis-ranked the causal role. Do NOT award 1.0 in that
   case just because the NF name appears somewhere in the block.

3. **severity_correct** (bool): Did the agent's severity assessment match the
   actual impact? A complete outage (container killed, network partitioned) =
   "down"/"outage"/"unreachable"/"100% loss". A degradation (packet loss,
   latency) = "degraded"/"slow"/"impaired"/"quality issues".

4. **fault_type_identified** (bool): Did the agent identify the OBSERVABLE
   class of failure? Score based on what can be observed from the network:
   - Component unreachable: "down"/"unreachable"/"not responding"/"100% packet loss"
   - Network degradation: "packet loss"/"latency"/"delay"/"congestion"
   - Service partition: "partitioned"/"unreachable"/"isolated"
   - Service hang: "unresponsive"/"timeout"/"hung"
   Do NOT require the agent to name the simulation mechanism (container_kill,
   tc netem, docker pause).

5. **layer_accuracy** (bool): Did the agent correctly attribute the affected
   component(s) to their correct ontology layer in the layer status assessment?

   This is the ONLY dimension where the NETWORK ANALYSIS section is an
   authoritative input — layer ratings live there, not in the final
   `causes` block. Each component belongs to a specific layer per the
   network ontology. The ground truth section below specifies each affected
   component's ontology layer. The NETWORK ANALYSIS section contains a
   layer-status table with ratings per layer.

   Score True if EITHER:
   - The agent's layer ratings correctly place the primary affected
     component(s) under their ontology layer (e.g., rating the "ims" layer
     RED when the affected component is an IMS component), OR
   - No layer status information is available in the diagnosis (no
     misattribution can be detected).

   Score False if the agent attributed a component's failure to the WRONG
   layer. For example: rating the "infrastructure" layer RED because of an
   HSS failure, when the ontology defines HSS as an IMS component. The
   nature of the failure (e.g., network unreachability) does NOT determine
   the component's layer — a network-level failure of an IMS component is
   still an IMS-layer problem.

6. **confidence_calibrated** (bool): Is the agent's stated confidence level
   appropriate given the quality of its diagnosis? High confidence + correct
   diagnosis with tool evidence = well calibrated. High confidence + wrong
   diagnosis = poorly calibrated.

7. **ranking_position** (int or null): If the agent returned multiple ranked
   candidates, what position (1-based) is the correct cause? 1 = top,
   null = correct cause not listed.

## Output Format

Return ONLY a JSON object (no markdown fences, no extra text):

{
  "root_cause_correct": true/false,
  "root_cause_rationale": "...",
  "component_overlap": 0.0-1.0,
  "component_rationale": "...",
  "severity_correct": true/false,
  "severity_rationale": "...",
  "fault_type_identified": true/false,
  "fault_type_rationale": "...",
  "layer_accuracy": true/false,
  "layer_accuracy_rationale": "...",
  "confidence_calibrated": true/false,
  "confidence_rationale": "...",
  "ranking_position": 1/2/3/null,
  "ranking_rationale": "...",
  "total_score": 0.0-1.0,
  "summary": "One-sentence overall assessment"
}

Compute total_score as:
  0.40 × root_cause_correct
+ 0.20 × component_overlap
+ 0.15 × severity_correct
+ 0.10 × fault_type_identified
+ 0.05 × layer_accuracy
+ 0.10 × confidence_calibrated
"""


# Map injection mechanisms to observable failure descriptions
_FAULT_TYPE_DESCRIPTIONS = {
    "container_kill": "Component completely unreachable (down/not responding)",
    "container_stop": "Component temporarily unavailable (stopped, may recover)",
    "container_pause": "Component unresponsive (appears running but not processing requests)",
    "container_restart": "Component temporarily disrupted (brief outage, then recovery)",
    "network_latency": "Elevated network latency on the component's interfaces",
    "network_loss": "Packet loss on the component's network path",
    "network_corruption": "Packet corruption on the component's network path",
    "network_bandwidth": "Bandwidth constraint on the component's network path",
    "network_partition": "Network partition — component isolated from specified peers",
    "config_corruption": "Configuration error causing service malfunction",
    "subscriber_delete": "Subscriber data missing from database",
    "collection_drop": "Database collection/table dropped",
}


async def score_diagnosis(
    diagnosis_text: str,
    injected_faults: list[dict],
    scenario: dict,
    network_analysis: str = "",
) -> dict:
    """Score an RCA diagnosis using an LLM judge.

    The scorer evaluates against the SIMULATED FAILURE MODE, not the
    injection mechanism.

    Args:
        diagnosis_text: The agent's raw diagnosis output.
        injected_faults: List of fault dicts with target, fault_type, params.
        scenario: The scenario dict with name, description, expected_symptoms.
        network_analysis: The agent's network analysis output (contains
            layer_status ratings). Used for scoring layer_accuracy.
    """
    # Build ground truth focused on the simulated failure mode
    fault_descriptions = []
    layer_ground_truth = []
    for f in injected_faults:
        fault_type = f.get("fault_type", "?")
        target = f.get("target", "?")
        params = f.get("params", {})
        observable = _FAULT_TYPE_DESCRIPTIONS.get(fault_type, fault_type)

        # Include params that describe the observable effect
        if fault_type == "network_latency" and "delay_ms" in params:
            delay_ms = params["delay_ms"]
            if delay_ms >= 10000:
                observable = (
                    f"Extreme network latency ({delay_ms}ms delay) on the component's "
                    f"interfaces — functionally equivalent to unreachability for "
                    f"real-time protocols (SIP timers ~500ms, Diameter timers ~5-30s). "
                    f"Standard diagnostic probes (ping with 10s timeout) will report "
                    f"100% packet loss because the delay exceeds the probe timeout. "
                    f"The agent may correctly describe this as 'unreachable' or "
                    f"'unresponsive' — this is an acceptable interpretation."
                )
            else:
                observable += f" ({delay_ms}ms delay)"
        elif fault_type == "network_loss" and "loss_pct" in params:
            observable += f" ({params['loss_pct']}% packet loss)"
        elif fault_type == "network_partition" and "target_ip" in params:
            observable += f" (isolated from {params['target_ip']})"

        fault_descriptions.append(
            f"- Component '{target}': {observable}"
        )

        # Build ontology layer ground truth for each target
        ontology_layer = _COMPONENT_ONTOLOGY_LAYER.get(target)
        if ontology_layer:
            layer_ground_truth.append(
                f"- '{target}' belongs to the **{ontology_layer}** layer"
            )

    scenario_desc = scenario.get("description", "?")
    expected_symptoms = scenario.get("expected_symptoms", [])

    ground_truth = (
        f"Scenario: {scenario.get('name', '?')}\n"
        f"Description: {scenario_desc}\n"
        f"\nSimulated failure mode (what the agent should observe):\n"
        + "\n".join(fault_descriptions) + "\n"
        f"\nExpected observable symptoms:\n"
        + "\n".join(f"- {s}" for s in expected_symptoms)
    )

    if layer_ground_truth:
        ground_truth += (
            "\n\nComponent ontology layers (ground truth for layer_accuracy scoring):\n"
            + "\n".join(layer_ground_truth)
        )

    ground_truth += (
        "\n\nNote: The agent cannot see HOW the failure was injected "
        "(container kill, tc netem, etc.). Score based on whether the agent "
        "correctly identified the failure from the network's observable perspective."
    )

    user_message = (
        f"## SIMULATED FAILURE\n\n{ground_truth}\n\n"
        f"## AGENT DIAGNOSIS\n\n{diagnosis_text}"
    )

    if network_analysis:
        user_message += (
            "\n\n## AGENT NETWORK ANALYSIS (for layer_accuracy ONLY)\n\n"
            "This is intermediate Phase-3 reasoning, NOT the agent's final\n"
            "diagnosis. Use it ONLY for the `layer_accuracy` dimension. For\n"
            "`root_cause_correct`, `component_overlap`, and all other\n"
            "dimensions, score against the AGENT DIAGNOSIS above.\n\n"
            f"{network_analysis}"
        )

    try:
        result = await _call_scorer_llm(user_message)
        log.info(
            "LLM score: %.0f%% (root_cause=%s, components=%.0f%%)",
            result.get("total_score", 0) * 100,
            result.get("root_cause_correct"),
            result.get("component_overlap", 0) * 100,
        )
        return result
    except Exception as e:
        log.error("LLM scorer failed, falling back to zero score: %s", e)
        return _fallback_score(str(e))


async def _call_scorer_llm(user_message: str) -> dict:
    """Call the LLM scorer and parse the response."""
    from google import genai
    from google.genai import types

    client = genai.Client(
        vertexai=os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").upper() == "TRUE",
        project=os.environ.get("GOOGLE_CLOUD_PROJECT"),
        location=os.environ.get("GOOGLE_CLOUD_LOCATION", "northamerica-northeast1"),
    )

    response = await client.aio.models.generate_content(
        model=_SCORER_MODEL,
        contents=user_message,
        config=types.GenerateContentConfig(
            system_instruction=_SCORER_PROMPT,
            temperature=0.0,
            response_mime_type="application/json",
        ),
    )

    text = response.text.strip()
    parsed = json.loads(text)

    # Validate and ensure required fields
    required_bools = ["root_cause_correct", "severity_correct",
                      "fault_type_identified", "layer_accuracy",
                      "confidence_calibrated"]
    for key in required_bools:
        if key not in parsed:
            parsed[key] = False

    if "component_overlap" not in parsed:
        parsed["component_overlap"] = 0.0

    if "total_score" not in parsed:
        parsed["total_score"] = round(
            0.40 * float(parsed.get("root_cause_correct", False))
            + 0.20 * float(parsed.get("component_overlap", 0))
            + 0.15 * float(parsed.get("severity_correct", False))
            + 0.10 * float(parsed.get("fault_type_identified", False))
            + 0.05 * float(parsed.get("layer_accuracy", False))
            + 0.10 * float(parsed.get("confidence_calibrated", False)),
            3,
        )

    return parsed


def _fallback_score(error_msg: str) -> dict:
    """Return a zero score when the LLM scorer fails."""
    return {
        "root_cause_correct": False,
        "root_cause_rationale": f"Scorer failed: {error_msg}",
        "component_overlap": 0.0,
        "component_rationale": "Scorer failed",
        "severity_correct": False,
        "severity_rationale": "Scorer failed",
        "fault_type_identified": False,
        "fault_type_rationale": "Scorer failed",
        "layer_accuracy": False,
        "layer_accuracy_rationale": "Scorer failed",
        "confidence_calibrated": False,
        "confidence_rationale": "Scorer failed",
        "ranking_position": None,
        "ranking_rationale": "Scorer failed",
        "total_score": 0.0,
        "summary": f"LLM scorer failed: {error_msg}",
    }
