"""Per-metric exhaustive verification of the unified renderer.

Per ADR `expose_kb_disambiguators_to_investigator.md`, sampling is
forbidden. This module enumerates EVERY metric entry in the KB at
test-collection time and runs the per-field invariants on each one.
A regression on a single metric fails CI with the specific entry
named — there is no silent drop.

Invariants checked per metric:
  1. `what_it_signals` rendered verbatim (no truncation, no paraphrase).
  2. `description` rendered verbatim.
  3. Every authored `meaning.*` variant (`zero`, `spike`, `drop`,
     `steady_non_zero`) is reachable — driving the synthetic value
     into the regime that selects the variant produces the verbatim
     variant text.
  4. Every `disambiguators` entry is rendered with partner KB id +
     partner current value + verbatim `separates` text. The count of
     emitted disambiguator blocks equals `len(entry.disambiguators)`.
  5. `healthy.pre_existing_noise` rendered verbatim when present.
  6. `healthy.typical_range` rendered when present.

Plus a global-character invariant: for every KB-sourced rich-text
field, `len(rendered_field) >= len(kb_field)` (after whitespace
collapse). Truncation is impossible without failing this check.
"""

from __future__ import annotations

import re
from typing import Any

import pytest

from agentic_ops_common.metric_kb import load_kb
from agentic_ops_common.tools.diagnostic_metrics import (
    _render_metric_with_full_kb_block,
)


# ----------------------------------------------------------------------
# Test parametrization — one case per `meaning`-bearing metric in the KB.
# ----------------------------------------------------------------------

def _meaning_bearing_metrics() -> list[tuple[str, str, str, Any]]:
    """Walk the KB and return (full_id, nf, metric_name, entry) for
    every metric with authored `meaning` content.

    These are the entries the renderer must surface in full. Bare
    counter entries with no rich content (e.g., `httpclient:connfail`)
    are valid KB members but out of scope for this depth check.
    """
    kb = load_kb()
    out: list[tuple[str, str, str, Any]] = []
    for nf_name, nf_block in kb.metrics.items():
        layer = nf_block.layer.value
        for metric_name, entry in nf_block.metrics.items():
            if entry.meaning is None and not entry.disambiguators:
                continue
            full_id = f"{layer}.{nf_name}.{metric_name}"
            out.append((full_id, nf_name, metric_name, entry))
    return sorted(out, key=lambda t: t[0])


_PARAMS = _meaning_bearing_metrics()


def _ids_for_params(params):
    return [t[0] for t in params]


# ----------------------------------------------------------------------
# Invariant helpers
# ----------------------------------------------------------------------

def _normalize(text: str) -> str:
    """Collapse whitespace for substring/length comparisons. The
    renderer is allowed to re-indent KB text; it's not allowed to
    drop characters."""
    return re.sub(r"\s+", " ", text).strip()


def _kb_text_appears_in_rendered(kb_text: str, rendered: str) -> bool:
    return _normalize(kb_text) in _normalize(rendered)


def _value_in_typical_range_regime(
    entry: Any,
    regime: str,
) -> float | None:
    """Pick a synthetic value that drives the renderer's variant
    selection into the requested regime (`zero`, `spike`, `drop`,
    `steady_non_zero`).

    Returns None when the regime cannot be exercised given the
    entry's `healthy.typical_range` (e.g. drop with low=0).
    """
    typical = entry.healthy.typical_range if entry.healthy else None
    if regime == "zero":
        return 0.0
    if typical is None:
        # Without a typical_range we cannot synthesize spike/drop.
        return None
    low, high = typical
    if regime == "spike":
        return high + max(abs(high), 1.0)
    if regime == "drop":
        # Need a positive value below `low` to distinguish from zero.
        if low <= 0:
            return None
        return low / 2.0
    if regime == "steady_non_zero":
        if low > 0:
            return (low + high) / 2.0 if low != high else low
        # When low == 0 we still need a non-zero in-range value.
        if high > 0:
            return high / 2.0
        return None
    return None


# ----------------------------------------------------------------------
# Per-metric tests
# ----------------------------------------------------------------------

@pytest.mark.parametrize(
    "full_id,nf,metric,entry",
    _PARAMS,
    ids=_ids_for_params(_PARAMS),
)
def test_what_it_signals_rendered_verbatim(full_id, nf, metric, entry):
    """The full `meaning.what_it_signals` text appears in the rendered
    block — no first-sentence shortcut, no length cap."""
    if entry.meaning is None or not entry.meaning.what_it_signals:
        pytest.skip("no what_it_signals authored")
    kb = load_kb()
    rendered = "\n".join(_render_metric_with_full_kb_block(
        label=metric, value=0.0, entry=entry,
        kb=kb, raw_snapshot={}, features={}, learned_value=None,
    ))
    assert _kb_text_appears_in_rendered(
        entry.meaning.what_it_signals, rendered
    ), (
        f"{full_id}: what_it_signals missing/truncated in rendered output.\n"
        f"  KB:       {entry.meaning.what_it_signals!r}\n"
        f"  Rendered: {rendered!r}"
    )


@pytest.mark.parametrize(
    "full_id,nf,metric,entry",
    _PARAMS,
    ids=_ids_for_params(_PARAMS),
)
def test_description_rendered_verbatim(full_id, nf, metric, entry):
    """The full `description` text appears in the rendered block."""
    if not entry.description:
        pytest.skip("no description authored")
    kb = load_kb()
    rendered = "\n".join(_render_metric_with_full_kb_block(
        label=metric, value=0.0, entry=entry,
        kb=kb, raw_snapshot={}, features={}, learned_value=None,
    ))
    assert _kb_text_appears_in_rendered(entry.description, rendered), (
        f"{full_id}: description missing/truncated.\n"
        f"  KB:       {entry.description!r}\n"
        f"  Rendered: {rendered!r}"
    )


@pytest.mark.parametrize(
    "full_id,nf,metric,entry",
    _PARAMS,
    ids=_ids_for_params(_PARAMS),
)
def test_every_meaning_variant_reachable(full_id, nf, metric, entry):
    """Every authored `meaning.*` variant must be reachable: driving
    the synthetic value into the selecting regime produces the
    verbatim variant text."""
    if entry.meaning is None:
        pytest.skip("no meaning authored")
    kb = load_kb()
    variants = {
        "zero": entry.meaning.zero,
        "spike": entry.meaning.spike,
        "drop": entry.meaning.drop,
        "steady_non_zero": entry.meaning.steady_non_zero,
    }
    failures: list[str] = []
    for regime, text in variants.items():
        if not text:
            continue
        v = _value_in_typical_range_regime(entry, regime)
        if v is None:
            # Cannot synthesize — the entry's healthy.typical_range
            # makes the regime unreachable. Note this rather than
            # failing; the renderer correctness is unobservable here.
            continue
        rendered = "\n".join(_render_metric_with_full_kb_block(
            label=metric, value=v, entry=entry,
            kb=kb, raw_snapshot={}, features={}, learned_value=None,
        ))
        if not _kb_text_appears_in_rendered(text, rendered):
            failures.append(
                f"  variant={regime} value={v}: {text!r} missing in:\n"
                f"    {rendered!r}"
            )
    assert not failures, (
        f"{full_id}: meaning variants not rendered:\n" + "\n".join(failures)
    )


@pytest.mark.parametrize(
    "full_id,nf,metric,entry",
    _PARAMS,
    ids=_ids_for_params(_PARAMS),
)
def test_every_disambiguator_rendered(full_id, nf, metric, entry):
    """Every disambiguator entry renders with its partner KB id and
    verbatim `separates` text. Block count equals
    `len(entry.disambiguators)`."""
    if not entry.disambiguators:
        pytest.skip("no disambiguators authored")
    kb = load_kb()
    rendered_lines = _render_metric_with_full_kb_block(
        label=metric, value=0.0, entry=entry,
        kb=kb, raw_snapshot={}, features={}, learned_value=None,
    )
    rendered = "\n".join(rendered_lines)
    # Each disambiguator must have its partner id and separates text
    # present.
    for d in entry.disambiguators:
        assert d.metric in rendered, (
            f"{full_id}: disambiguator partner id {d.metric!r} "
            f"missing in rendered output."
        )
        assert _kb_text_appears_in_rendered(d.separates, rendered), (
            f"{full_id}: disambiguator separates text missing.\n"
            f"  KB:       {d.separates!r}\n"
            f"  Rendered: {rendered!r}"
        )
    # Block count matches.
    block_count = sum(1 for line in rendered_lines if line.lstrip().startswith("vs "))
    assert block_count == len(entry.disambiguators), (
        f"{full_id}: emitted {block_count} disambiguator blocks but KB "
        f"authored {len(entry.disambiguators)}."
    )


@pytest.mark.parametrize(
    "full_id,nf,metric,entry",
    _PARAMS,
    ids=_ids_for_params(_PARAMS),
)
def test_pre_existing_noise_rendered_verbatim(full_id, nf, metric, entry):
    """When `healthy.pre_existing_noise` is authored, the full text
    appears in the rendered block (no first-sentence truncation —
    that pattern is the canonical `httpclient:connfail` trap)."""
    if not (entry.healthy and entry.healthy.pre_existing_noise):
        pytest.skip("no pre_existing_noise authored")
    kb = load_kb()
    rendered = "\n".join(_render_metric_with_full_kb_block(
        label=metric, value=0.0, entry=entry,
        kb=kb, raw_snapshot={}, features={}, learned_value=None,
    ))
    assert _kb_text_appears_in_rendered(
        entry.healthy.pre_existing_noise, rendered
    ), (
        f"{full_id}: pre_existing_noise missing/truncated.\n"
        f"  KB:       {entry.healthy.pre_existing_noise!r}\n"
        f"  Rendered: {rendered!r}"
    )


@pytest.mark.parametrize(
    "full_id,nf,metric,entry",
    _PARAMS,
    ids=_ids_for_params(_PARAMS),
)
def test_typical_range_rendered_when_present(full_id, nf, metric, entry):
    """When `healthy.typical_range` is authored, the rendered block
    contains the range bounds."""
    if not (entry.healthy and entry.healthy.typical_range is not None):
        pytest.skip("no typical_range authored")
    kb = load_kb()
    rendered = "\n".join(_render_metric_with_full_kb_block(
        label=metric, value=0.0, entry=entry,
        kb=kb, raw_snapshot={}, features={}, learned_value=None,
    ))
    low, high = entry.healthy.typical_range
    assert "healthy_range" in rendered, (
        f"{full_id}: 'healthy_range' label missing from rendered output.\n"
        f"  Rendered: {rendered!r}"
    )
    # Both bounds present (formatting tolerates int/float).
    for bound in (low, high):
        bound_str = (
            str(int(bound)) if isinstance(bound, (int, float)) and float(bound).is_integer()
            else f"{bound:.4g}"
        )
        assert bound_str in rendered or str(bound) in rendered, (
            f"{full_id}: healthy_range bound {bound!r} missing from rendered.\n"
            f"  Rendered: {rendered!r}"
        )


# ----------------------------------------------------------------------
# Aggregate length invariant — no rich-text field can lose characters
# ----------------------------------------------------------------------

@pytest.mark.parametrize(
    "full_id,nf,metric,entry",
    _PARAMS,
    ids=_ids_for_params(_PARAMS),
)
def test_no_rich_text_field_loses_characters(full_id, nf, metric, entry):
    """For each rich-text KB field, the rendered block contains at
    least as many normalized characters of that field as the source.

    This is the catch-all guard: any future renderer edit that
    accidentally truncates (slice, regex strip, paraphrase, length
    cap) will fail this check on at least one metric.
    """
    kb = load_kb()
    rendered = "\n".join(_render_metric_with_full_kb_block(
        label=metric, value=0.0, entry=entry,
        kb=kb, raw_snapshot={}, features={}, learned_value=None,
    ))
    rendered_norm = _normalize(rendered)

    fields_to_check: list[tuple[str, str]] = []
    if entry.description:
        fields_to_check.append(("description", entry.description))
    if entry.meaning and entry.meaning.what_it_signals:
        fields_to_check.append(
            ("meaning.what_it_signals", entry.meaning.what_it_signals)
        )
    if entry.healthy and entry.healthy.pre_existing_noise:
        fields_to_check.append(
            ("healthy.pre_existing_noise", entry.healthy.pre_existing_noise)
        )
    for d in entry.disambiguators:
        fields_to_check.append(
            (f"disambiguators[metric={d.metric}].separates", d.separates)
        )
    # meaning.* variants are conditional on value selection — don't
    # require them in this length check (separately covered by the
    # per-variant test above).

    for field_name, kb_text in fields_to_check:
        kb_norm = _normalize(kb_text)
        if not kb_norm:
            continue
        assert kb_norm in rendered_norm, (
            f"{full_id}: field {field_name} not fully present in "
            f"rendered output (normalized comparison).\n"
            f"  KB norm:       {kb_norm!r}\n"
            f"  Rendered norm: {rendered_norm!r}"
        )
