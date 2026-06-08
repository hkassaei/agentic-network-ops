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
  - root_cause_correct:    Did the agent identify the simulated failure mode? (LLM)
  - component_overlap:     Did it name the right affected component(s)? (MECHANICAL)
  - severity_correct:      Did it assess severity accurately? (LLM)
  - fault_type_identified: Did it identify the observable class of failure? (LLM)
  - confidence_calibrated: Is confidence justified by evidence quality? (LLM)
  - ranking_position:      Where did the correct cause rank? (LLM, unweighted)

Score arithmetic is MECHANICAL, never LLM-driven (2026-05). The LLM judge
returns only the semantic boolean verdicts; Python computes:
  * `component_overlap` — a structured comparison of the ground-truth NF(s)
    against the diagnosis's `affected_components` roles (Root Cause = 1.0,
    present-but-not-root = 0.3, absent = 0.0). This was previously an LLM
    guess and produced values that contradicted the rubric (a clean
    Root-Cause placement scored 0.75).
  * `total_score` — the weighted sum below, ALWAYS recomputed. The LLM used
    to emit its own total, which contradicted its own per-dimension verdicts
    (4×Yes + component 0.75 reported as 75% instead of 94%).

`layer_accuracy` was removed (2026-05): only 0.05 weight, most machinery,
penalized defensible boundary calls. Its weight folded into component_overlap
(0.20 → 0.25). Five weighted dimensions remain:
  total_score = 0.40·root_cause + 0.25·component_overlap + 0.15·severity
              + 0.10·fault_type + 0.10·confidence
"""

from __future__ import annotations

import json
import logging
import os

from agentic_ops_v7.model_config import flash_model_id

log = logging.getLogger("chaos-scorer")

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
   `explanation` fields. Score every dimension strictly against this final
   diagnosis — an agent may reason correctly mid-pipeline and then walk it
   back to a wrong conclusion; the operator only sees the final diagnosis.

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

   **Special case — `verdict_kind: "undetected_fault"`** (ADR
   `synthesis_undetected_fault_verdict.md`). When the agent's diagnosis
   carries `verdict_kind: "undetected_fault"`, the agent is explicitly
   saying "I could not pinpoint a fault; please investigate further" —
   the humble admission, not a fabricated culprit.

   **Score `root_cause_correct=False` regardless of scenario class.**
   `root_cause_correct` measures whether the agent IDENTIFIED the
   simulated failure mode. An `undetected_fault` verdict explicitly
   does not identify anything — the agent abstained. Even on a
   negative-control scenario where the operationally-correct posture
   IS abstention, the agent didn't say "PyHSS clock skew, no
   functional impact" — it said "I couldn't find anything." Those
   are different claims and only the first one identifies the
   simulated failure mode.

   **But the `root_cause_rationale` field MUST distinguish honest
   hedging from fabrication.** This is the load-bearing scoring
   signal for the operational difference between two failure modes
   that both score False on this dimension:

   - **`undetected_fault` (honest hedge)** — the agent acknowledged
     it could not pinpoint a fault. Operationally safe; defers to
     a human. Rationale should say something like: *"Agent emitted
     `undetected_fault` and did not identify the simulated failure
     mode (X). False on this dimension, but the agent honestly
     hedged rather than fabricating a wrong culprit — meaningfully
     better than the prior failure mode where the agent named a
     wrong NF as the root cause."*

   - **`promoted`/`confirmed` with WRONG NF (fabrication)** —
     the agent named a culprit that does not match the simulated
     failure mode. Operationally dangerous; would trigger
     remediation against an innocent component. Rationale should
     say: *"Agent fabricated NF-X as the root cause; the simulated
     failure mode was Y. False on this dimension AND operationally
     unsafe — a wrong-culprit diagnosis is worse than abstention."*

   The boolean is False either way, but the rationale carries the
   operational distinction for downstream evaluators (humans
   reviewing scorecards, dashboards summarizing run quality, etc.).

2. **severity_correct** (bool): Did the agent's severity assessment match the
   actual impact? A complete outage (container killed, network partitioned) =
   "down"/"outage"/"unreachable"/"100% loss". A degradation (packet loss,
   latency) = "degraded"/"slow"/"impaired"/"quality issues".

3. **fault_type_identified** (bool): Did the agent identify the OBSERVABLE
   class of failure? Score based on what can be observed from the network:
   - Component unreachable: "down"/"unreachable"/"not responding"/"100% packet loss"
   - Network degradation: "packet loss"/"latency"/"delay"/"congestion"
   - Service partition: "partitioned"/"unreachable"/"isolated"
   - Service hang: "unresponsive"/"timeout"/"hung"
   Do NOT require the agent to name the simulation mechanism (container_kill,
   tc netem, docker pause).

4. **confidence_calibrated** (bool): Is the agent's stated confidence level
   appropriate given the quality of its diagnosis? High confidence + correct
   diagnosis with tool evidence = well calibrated. High confidence + wrong
   diagnosis = poorly calibrated.

5. **ranking_position** (int or null): If the agent returned multiple ranked
   candidates, what position (1-based) is the correct cause? 1 = top,
   null = correct cause not listed.

NOTE: You do NOT score component overlap or the total score. Those are
computed MECHANICALLY in Python from the structured diagnosis and the
ground truth — they are not LLM judgments. Score only the dimensions
above, which require semantic judgment.

## Output Format

Return ONLY a JSON object (no markdown fences, no extra text):

{
  "root_cause_correct": true/false,
  "root_cause_rationale": "...",
  "severity_correct": true/false,
  "severity_rationale": "...",
  "fault_type_identified": true/false,
  "fault_type_rationale": "...",
  "confidence_calibrated": true/false,
  "confidence_rationale": "...",
  "ranking_position": 1/2/3/null,
  "ranking_rationale": "...",
  "summary": "One-sentence overall assessment"
}
"""


# Map injection mechanisms to observable failure descriptions
_FAULT_TYPE_DESCRIPTIONS = {
    "container_kill": "Component completely unreachable (down/not responding)",
    "container_stop": "Component temporarily unavailable (stopped, may recover)",
    "container_pause": "Component unresponsive (appears running but not processing requests)",
    "container_restart": "Component temporarily disrupted (brief outage, then recovery)",
    "network_latency": "Elevated network latency on the component's interfaces",
    "network_loss": (
        "Packet loss on the component's network path. If a peer_ip parameter is "
        "set, loss applies ONLY in the egress direction toward that peer — the "
        "reverse direction (peer→component) is unaffected. The discriminating "
        "signal is bidirectional probe divergence: ping FROM A gives one answer; "
        "ping FROM B gives a different answer for the same link."
    ),
    "network_corruption": "Packet corruption on the component's network path",
    "network_bandwidth": "Bandwidth constraint on the component's network path",
    "network_partition": "Network partition — component isolated from specified peers",
    "config_corruption": "Configuration error causing service malfunction",
    "subscriber_delete": "Subscriber data missing from database",
    "collection_drop": "Database collection/table dropped",
    # CDR-0001 novel fault types
    "subscriber_credential_corruption": (
        "One specific subscriber's authentication credential (K) is corrupted in "
        "the HSS. THAT subscriber fails AKA with MAC failure; all OTHER "
        "subscribers continue working normally. The blast radius is per-IMSI, "
        "not per-NF. Container health stays green; aggregate auth metrics may "
        "not cross anomaly thresholds. Per-subscriber comparison is the "
        "diagnostic — one UE breaks, the other works."
    ),
    "clock_skew": (
        "One NF's wall clock is significantly skewed from peers. In this lab "
        "(PyHSS counter-based SQN; cleartext SCTP Diameter; no Kamailio "
        "date_check module loaded), this is OBSERVABILITY-ONLY — no functional "
        "impact. Log timestamps and Diameter Session-Id high-32 fields drift; "
        "UE registrations and calls continue normally. The CORRECT diagnosis "
        "is 'no functional fault; clock-drift observability anomaly on <NF>.' "
        "Diagnosing a functional PyHSS auth outage or Diameter outage on this "
        "signature is a FALSE POSITIVE."
    ),
    "pmtu_blackhole": (
        "Path MTU Discovery is defeated by lowered MTU + dropped ICMP "
        "fragmentation-needed replies. Small packets pass; large packets "
        "(over ~1240 B) are silently dropped. Voice (small RTP ~200 B) is "
        "unaffected; large SIP INVITEs with full SDP, NAS QoS containers, "
        "and other large signaling messages vanish. The discriminator is "
        "PAYLOAD SIZE — 'voice works but signaling fails' is the diagnostic "
        "shape that maps to no other failure mode."
    ),
}


# Score weights. Single source of truth — used by the deterministic
# total computation. Must sum to 1.0.
_SCORE_WEIGHTS = {
    "root_cause_correct": 0.40,
    "component_overlap": 0.25,
    "severity_correct": 0.15,
    "fault_type_identified": 0.10,
    "confidence_calibrated": 0.10,
}


def _mechanical_component_overlap(
    gt_nfs: set[str], diagnosis_report: dict | None,
) -> tuple[float, str]:
    """Compute component_overlap deterministically — NOT an LLM judgment.

    Compares the ground-truth affected NF(s) against the diagnosis's
    structured root-cause set (primary_suspect_nf + any affected_component
    tagged "Root Cause"). Per ground-truth NF:
      Root Cause          → 1.0
      present, other role → 0.3   (saw it, mis-ranked the causal role)
      absent              → 0.0
    component_overlap is the mean over the ground-truth NFs. Downstream
    components in the diagnosis are not penalized.
    """
    if not gt_nfs:
        return 0.0, "No ground-truth components to compare."

    dr = diagnosis_report or {}
    affected = dr.get("affected_components") or []
    roots: set[str] = {
        c.get("name") for c in affected
        if isinstance(c, dict) and c.get("role") == "Root Cause" and c.get("name")
    }
    primary = dr.get("primary_suspect_nf")
    if primary:
        roots.add(primary)
    others: set[str] = {
        c.get("name") for c in affected
        if isinstance(c, dict) and c.get("name")
    } - roots

    scores: list[float] = []
    detail: list[str] = []
    for nf in sorted(gt_nfs):
        if nf in roots:
            scores.append(1.0)
            detail.append(f"{nf}=Root Cause (1.0)")
        elif nf in others:
            scores.append(0.3)
            detail.append(f"{nf}=secondary/symptomatic (0.3)")
        else:
            scores.append(0.0)
            detail.append(f"{nf}=absent (0.0)")

    overlap = round(sum(scores) / len(scores), 3)
    rationale = (
        f"Mechanical comparison: ground truth {sorted(gt_nfs)} vs diagnosis "
        f"root cause(s) {sorted(roots) or '[]'}. " + "; ".join(detail) + "."
    )
    return overlap, rationale


def _compute_total_score(parsed: dict) -> float:
    """Deterministic weighted sum — never trust an LLM-emitted total."""
    return round(
        sum(_SCORE_WEIGHTS[k] * float(parsed.get(k, False) or 0)
            for k in _SCORE_WEIGHTS),
        3,
    )


async def score_diagnosis(
    diagnosis_text: str,
    injected_faults: list[dict],
    scenario: dict,
    diagnosis_report: dict | None = None,
) -> dict:
    """Score an RCA diagnosis.

    The semantic dimensions (root_cause_correct, severity_correct,
    fault_type_identified, confidence_calibrated, ranking_position) are
    judged by an LLM against the SIMULATED FAILURE MODE. `component_overlap`
    and `total_score` are computed MECHANICALLY in Python — the LLM never
    does the arithmetic or the structured component comparison.

    Args:
        diagnosis_text: The agent's raw diagnosis output (for the LLM judge).
        injected_faults: Fault dicts with target/fault_type/params. The
            `target`s are the ground-truth affected components.
        scenario: The scenario dict with name, description, expected_symptoms.
        diagnosis_report: The structured DiagnosisReport dict (primary_suspect_nf
            + affected_components). Used for the mechanical component_overlap.
    """
    # Build ground truth focused on the simulated failure mode
    fault_descriptions = []
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

    ground_truth += (
        "\n\nNote: The agent cannot see HOW the failure was injected "
        "(container kill, tc netem, etc.). Score based on whether the agent "
        "correctly identified the failure from the network's observable perspective."
    )

    user_message = (
        f"## SIMULATED FAILURE\n\n{ground_truth}\n\n"
        f"## AGENT DIAGNOSIS\n\n{diagnosis_text}"
    )

    # Ground-truth affected NFs = the fault targets.
    gt_nfs = {f.get("target") for f in injected_faults if f.get("target")}

    try:
        result = await _call_scorer_llm(user_message)
    except Exception as e:
        log.error("LLM scorer failed, falling back to zero score: %s", e)
        return _fallback_score(str(e))

    # MECHANICAL dimensions — computed in Python, never by the LLM.
    overlap, overlap_rationale = _mechanical_component_overlap(gt_nfs, diagnosis_report)
    result["component_overlap"] = overlap
    result["component_rationale"] = overlap_rationale
    result["total_score"] = _compute_total_score(result)

    log.info(
        "Score: %.0f%% (root_cause=%s, components=%.0f%% [mechanical])",
        result["total_score"] * 100,
        result.get("root_cause_correct"),
        overlap * 100,
    )
    return result


async def _call_scorer_llm(user_message: str) -> dict:
    """Call the LLM scorer and parse the response."""
    from google import genai
    from google.genai import types

    client = genai.Client(
        vertexai=os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").upper() == "TRUE",
        project=os.environ.get("GOOGLE_CLOUD_PROJECT"),
        location=os.environ["GOOGLE_CLOUD_LOCATION"],
    )

    response = await client.aio.models.generate_content(
        model=flash_model_id(),
        contents=user_message,
        config=types.GenerateContentConfig(
            system_instruction=_SCORER_PROMPT,
            temperature=0.0,
            response_mime_type="application/json",
        ),
    )

    text = response.text.strip()
    parsed = json.loads(text)

    # The LLM judges ONLY the semantic boolean dimensions. component_overlap
    # and total_score are computed mechanically by the caller — if the model
    # emits them anyway, drop them so they can't leak into the result.
    parsed.pop("component_overlap", None)
    parsed.pop("total_score", None)

    required_bools = ["root_cause_correct", "severity_correct",
                      "fault_type_identified", "confidence_calibrated"]
    for key in required_bools:
        if key not in parsed:
            parsed[key] = False

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
        "confidence_calibrated": False,
        "confidence_rationale": "Scorer failed",
        "ranking_position": None,
        "ranking_rationale": "Scorer failed",
        "total_score": 0.0,
        "summary": f"LLM scorer failed: {error_msg}",
    }
