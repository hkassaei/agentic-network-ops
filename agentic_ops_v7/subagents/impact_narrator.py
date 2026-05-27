"""Phase 8b — impact narrator.

A pure narrator: given the deterministically-computed `BlastRadius`, write
human-readable prose for the report's Blast Radius section. It is NOT an
analyst — it may not introduce any NF/flow/service not in the structured
object, may not change the failing/degraded/at_risk tags, and may not
invent numbers, causes, or durations. The grounding guardrail
(`guardrails/impact_grounding.py`) enforces this structurally; this module
just supplies the prompt and the LLM call.

Uses a direct genai call on the flash model (mirrors `agentic_chaos/scorer.py`)
— the task is leaf prose generation with no tools, so the full ADK
agent/runner machinery isn't warranted.

ADR: docs/ADR/blast_radius_downstream_impact_phase8.md
"""

from __future__ import annotations

import json
import logging
import os

from ..model_config import flash_model_id
from ..models import BlastRadius

log = logging.getLogger("impact-narrator")

_SYSTEM_INSTRUCTION = """\
You are a network operations report writer. You are given a STRUCTURED
blast-radius object that upstream analysis computed deterministically, plus
the diagnosis summary. Write a short "Downstream Impact" narrative for the
report.

You are a NARRATOR, not an analyst. Absolute constraints:
- Use ONLY the network functions, flows, and services that appear in the
  provided blast_radius object. Do NOT name any NF, procedure, or service
  that is not in it.
- Do NOT change or re-infer status. The failing / degraded / at_risk tags
  are fixed by upstream analysis — describe them, never override them.
- "at_risk" means: the procedure depends on the failed component but no
  degradation was observed this episode. Describe it as a potential/at-risk
  consequence, never as a confirmed failure.
- Do NOT invent numbers, subscriber counts, SLAs, durations, or root causes.

Write two short paragraphs:
1. NOC-facing: which procedures/NFs are affected and at what status.
2. One plain-language sentence a non-engineer can read, naming the affected
   services and whether they are failing, degraded, or at risk.

Return ONLY a JSON object: {"narrative": "<your text>"}
"""


async def narrate_impact(
    blast_radius: BlastRadius,
    diagnosis_summary: str,
    extra_instruction: str = "",
) -> str:
    """Produce the narrative prose. Raises on transport/parse failure so the
    caller can fall back to the deterministic template.

    `extra_instruction` is appended on a resample after a grounding
    rejection (carries the offending references back to the model).
    """
    from google import genai
    from google.genai import types

    client = genai.Client(
        vertexai=os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").upper() == "TRUE",
        project=os.environ.get("GOOGLE_CLOUD_PROJECT"),
        location=os.environ["GOOGLE_CLOUD_LOCATION"],
    )

    payload = {
        "diagnosis_summary": diagnosis_summary,
        "blast_radius": blast_radius.model_dump(mode="json"),
    }
    contents = json.dumps(payload, indent=2, default=str)
    if extra_instruction:
        contents += f"\n\nSTRICT CORRECTION: {extra_instruction}"

    response = await client.aio.models.generate_content(
        model=flash_model_id(),
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=_SYSTEM_INSTRUCTION,
            temperature=0.0,
            response_mime_type="application/json",
        ),
    )
    data = json.loads(response.text.strip())
    return str(data.get("narrative", "")).strip()
