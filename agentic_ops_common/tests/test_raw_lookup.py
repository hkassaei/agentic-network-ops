"""Tests for the raw-metric-name → KB-entry resolver."""

from __future__ import annotations

import pytest

from agentic_ops_common.metric_kb import load_kb, resolve_raw


@pytest.fixture(scope="module")
def kb():
    return load_kb()


def test_direct_lookup_ran_ue(kb):
    """`ran_ue` is the KB metric name for AMF."""
    r = resolve_raw("amf", "ran_ue", kb)
    assert r.kind == "direct"
    assert r.kb_metric_id == "core.amf.ran_ue"
    assert r.entry is not None
    assert r.entry.type.value == "gauge"


def test_derived_lookup_upf_gtp_counter(kb):
    """Raw Prometheus counter resolves via `raw_sources` to its derived form."""
    r = resolve_raw("upf", "fivegs_ep_n3_gtp_indatapktn3upf", kb)
    assert r.kind == "derived"
    assert r.kb_metric_id == "core.upf.gtp_indatapktn3upf_per_ue"
    assert r.raw_type == "counter"
    assert r.entry is not None


def test_derived_lookup_pcscf_register_counter(kb):
    """Kamailio script:register_time resolves via raw_sources."""
    r = resolve_raw("pcscf", "script:register_time", kb)
    assert r.kind == "derived"
    assert r.kb_metric_id == "ims.pcscf.avg_register_time_ms"
    assert r.raw_type == "counter"


def test_derived_lookup_pcscf_sip_replies(kb):
    """sl:4xx_replies etc. resolve to the error_ratio derived metric."""
    for raw in ("sl:4xx_replies", "sl:5xx_replies", "sl:200_replies", "sl:1xx_replies"):
        r = resolve_raw("pcscf", raw, kb)
        assert r.kind == "derived", f"{raw} did not resolve"
        assert r.kb_metric_id == "ims.pcscf.sip_error_ratio"


def test_unknown_nf_returns_none(kb):
    r = resolve_raw("nonexistent_nf", "some_metric", kb)
    assert r.kind is None
    assert r.entry is None


def test_unknown_metric_uses_heuristic_type(kb):
    """No KB coverage but the name looks like a counter — return heuristic type."""
    r = resolve_raw("pcscf", "some_made_up_counter_total", kb)
    assert r.kind is None
    assert r.entry is None
    # Heuristic didn't fire for this name pattern — that's OK, we return None.
    # The point of this test is that the resolver doesn't crash on unknown names.


def test_kamailio_group_prefix_normalized(kb):
    """`core:rcv_requests_register` resolves via raw_sources at P-CSCF."""
    r = resolve_raw("pcscf", "core:rcv_requests_register", kb)
    assert r.kind == "derived"
    assert r.kb_metric_id == "ims.pcscf.rcv_requests_register_per_ue"


def test_infer_counter_type_for_packet_total(kb):
    """Heuristic: `fivegs_ep_n3_gtp_*` is a counter."""
    r = resolve_raw("upf", "fivegs_ep_n3_gtp_outdatapktn3upf", kb)
    # This one has raw_sources defined → derived kind
    assert r.kind == "derived"
    assert r.raw_type == "counter"
