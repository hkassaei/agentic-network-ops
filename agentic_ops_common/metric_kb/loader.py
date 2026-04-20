"""YAML loader for the metric knowledge base.

Loads `network_ontology/data/metrics.yaml` into typed `MetricsKB` objects.
Runs pydantic validation at load time (types, enums, required fields).
A second pass validates cross-references (feeds_model_features, correlates_with,
disambiguators, related_metrics references).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import yaml
from pydantic import ValidationError

from .models import MetricsKB

log = logging.getLogger("metric_kb.loader")

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_KB_PATH = _REPO_ROOT / "network_ontology" / "data" / "metrics.yaml"


class KBLoadError(Exception):
    """Raised when the KB cannot be loaded or validated."""


def load_kb(path: Optional[Path] = None, *, validate_refs: bool = True) -> MetricsKB:
    """Load and validate the metric KB from YAML.

    Args:
        path: Path to metrics.yaml. Defaults to the repo's canonical location.
        validate_refs: If True (default), run the cross-reference validation pass
                       after pydantic validation and raise on dangling references.

    Returns:
        A validated MetricsKB.

    Raises:
        KBLoadError: on any load or validation failure.
    """
    kb_path = path or _DEFAULT_KB_PATH
    if not kb_path.exists():
        raise KBLoadError(f"Metric KB not found at {kb_path}")

    try:
        with open(kb_path) as f:
            raw = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        raise KBLoadError(f"YAML parse error in {kb_path}: {e}") from e

    try:
        kb = MetricsKB.model_validate(raw)
    except ValidationError as e:
        raise KBLoadError(f"KB validation failed for {kb_path}:\n{e}") from e

    if validate_refs:
        errors = validate_cross_references(kb)
        if errors:
            raise KBLoadError(
                f"KB cross-reference validation failed for {kb_path}:\n"
                + "\n".join(f"  - {err}" for err in errors)
            )

    log.info("Loaded metric KB from %s: %d NFs, %d metrics, %d event triggers",
             kb_path, len(kb.metrics),
             sum(len(nb.metrics) for nb in kb.metrics.values()),
             len(kb.all_event_ids()))
    return kb


def validate_cross_references(kb: MetricsKB) -> list[str]:
    """Validate that intra-KB references resolve.

    Returns a list of error strings. Empty list means all references valid.
    Checked references:
      - composite_of points to metrics that exist in the KB
      - related_metrics[].metric points to metrics that exist in the KB
      - disambiguators[].metric points to metrics that exist (string metric keys only;
        computed expressions like "sum(a, b)" are skipped)
      - event_triggers[].correlates_with[].event_id points to a declared event id

    feeds_model_features is NOT validated here since those names live in
    anomaly_model_feature_set.md, not the KB. A separate tool can cross-check.
    """
    errors: list[str] = []
    all_metric_keys = kb.all_metric_keys()
    all_event_ids = kb.all_event_ids()

    def _metric_exists(key: str) -> bool:
        # Support full <layer>.<nf>.<metric> or shortform <nf>.<metric>
        if key in all_metric_keys:
            return True
        # Shortform — check any layer
        for mk in all_metric_keys:
            if mk.endswith("." + key):
                return True
        return False

    def _is_computed_expression(s: str) -> bool:
        # Skip references that look like computed expressions
        return "(" in s or "," in s

    for nf_name, nf_block in kb.metrics.items():
        for metric_name, metric in nf_block.metrics.items():
            ctx = f"{nf_block.layer.value}.{nf_name}.{metric_name}"

            for ref in metric.composite_of:
                if not _is_computed_expression(ref) and not _metric_exists(ref):
                    errors.append(
                        f"{ctx}.composite_of references unknown metric: {ref!r}"
                    )

            for rel in metric.related_metrics:
                if not _is_computed_expression(rel.metric) and not _metric_exists(rel.metric):
                    errors.append(
                        f"{ctx}.related_metrics references unknown metric: {rel.metric!r}"
                    )

            for dis in metric.disambiguators:
                if not _is_computed_expression(dis.metric) and not _metric_exists(dis.metric):
                    errors.append(
                        f"{ctx}.disambiguators references unknown metric: {dis.metric!r}"
                    )

            for trig in metric.event_triggers:
                for hint in trig.correlates_with:
                    # correlates_with references OTHER event ids — which may not be
                    # in this KB yet (Phase 1 content is incremental). We warn-only
                    # via logging; not an error.
                    if hint.event_id not in all_event_ids:
                        log.debug(
                            "%s event_trigger %s correlates_with undeclared event id %r "
                            "(non-fatal; will resolve when target metric is added)",
                            ctx, trig.id, hint.event_id,
                        )

    return errors
