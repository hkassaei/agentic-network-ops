"""Pin: `affected_components` is strongly typed so Synthesis can't emit
the empty-element artifact `[{}]`.

Root-cause fix (replaces the earlier post-parse repair band-aid):
`DiagnosisReport.affected_components` is `list[AffectedComponent]` with
`name` and `role` as REQUIRED properties. The Synthesis agent runs under
controlled generation with this model as its `output_schema`, so the
derived JSON schema forces Gemini to populate `name`/`role` — the empty
`{}` element it used to produce (untyped `list[dict]` schema) is now
schema-invalid.

These tests pin the contract at the Pydantic layer (which is what the
schema is derived from):
  * the JSON schema declares name/role required + additionalProperties:false
  * `[{}]` is rejected at validation
  * dict inputs still coerce (existing call sites + valid LLM output)
  * model_dump round-trips to plain {name, role} dicts (episode JSON shape
    unchanged — the scorer and RAG parser read the serialized form)
  * empty list is still allowed (inconclusive verdicts)
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agentic_ops_v7.models import AffectedComponent, DiagnosisReport


def _base(**overrides) -> dict:
    payload = dict(
        summary="s",
        root_cause="rc",
        root_cause_confidence="high",
        verdict_kind="confirmed",
        recommendation="r",
        explanation="e",
    )
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# Schema-shape pins (what Gemini's controlled generation receives)
# ---------------------------------------------------------------------------


def test_affected_component_schema_requires_name_and_role():
    schema = AffectedComponent.model_json_schema()
    assert set(schema["required"]) == {"name", "role"}
    # additionalProperties:false → the model can't open an object with
    # unknown/zero keys; it must produce exactly name + role.
    assert schema.get("additionalProperties") is False
    # role is enum-constrained to the three valid values.
    assert set(schema["properties"]["role"]["enum"]) == {
        "Root Cause", "Secondary", "Symptomatic",
    }


def test_diagnosis_report_items_ref_affected_component():
    schema = DiagnosisReport.model_json_schema()
    items = schema["properties"]["affected_components"]["items"]
    assert items.get("$ref", "").endswith("AffectedComponent")


# ---------------------------------------------------------------------------
# Validation behavior
# ---------------------------------------------------------------------------


def test_empty_element_is_rejected():
    """The old bug shape `[{}]` must fail validation now."""
    with pytest.raises(ValidationError) as exc:
        DiagnosisReport(**_base(affected_components=[{}]))
    msg = str(exc.value)
    assert "name" in msg and "role" in msg


def test_dict_input_coerces_to_typed_component():
    """Existing call sites and valid LLM output pass dicts — Pydantic
    coerces them to AffectedComponent so nothing upstream breaks."""
    report = DiagnosisReport(**_base(
        affected_components=[{"name": "mongo", "role": "Root Cause"}],
    ))
    assert isinstance(report.affected_components[0], AffectedComponent)
    assert report.affected_components[0].name == "mongo"
    assert report.affected_components[0].role == "Root Cause"


def test_model_dump_round_trips_to_plain_dicts():
    """Episode JSON shape is unchanged — model_dump emits {name, role}
    dicts, which is what the scorer and RAG parser read."""
    report = DiagnosisReport(**_base(
        affected_components=[{"name": "pcscf", "role": "Root Cause"}],
    ))
    dumped = report.model_dump(mode="json")["affected_components"]
    assert dumped == [{"name": "pcscf", "role": "Root Cause"}]


def test_empty_list_still_allowed_for_inconclusive():
    """Inconclusive verdicts legitimately have no affected components —
    the empty list must remain valid (only the empty *element* is banned)."""
    report = DiagnosisReport(**_base(
        verdict_kind="inconclusive",
        primary_suspect_nf=None,
        affected_components=[],
    ))
    assert report.affected_components == []


def test_invalid_role_is_rejected():
    """role is enum-constrained — a free-text role fails validation rather
    than silently passing through."""
    with pytest.raises(ValidationError):
        DiagnosisReport(**_base(
            affected_components=[{"name": "mongo", "role": "Primary"}],
        ))
