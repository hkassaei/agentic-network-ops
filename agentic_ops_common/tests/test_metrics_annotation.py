"""Tests for the KB-annotated `get_nf_metrics` wrapper."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from agentic_ops_common.tools import metrics as metrics_tool


_SAMPLE_COLLECTOR_OUTPUT = """
AMF [2 UE] (via prometheus):
  amf_session = 2
  gnb = 1
  ran_ue = 2

UPF [32 pkt] (via prometheus):
  _gauge_upf_kbps = 0.0
  fivegs_ep_n3_gtp_indatapktn3upf = 9371
  fivegs_ep_n3_gtp_outdatapktn3upf = 294
  fivegs_upffunction_upf_sessionnbr = 2

PCSCF (via kamcmd):
  core:rcv_requests_register = 88
  script:register_time = 52910
  sl:4xx_replies = 6
  sl:200_replies = 142
"""


def test_annotation_adds_tags_and_hints():
    with patch("agentic_ops_common.tools.metrics._t.get_nf_metrics") as mock:
        async def fake(_deps):
            return _SAMPLE_COLLECTOR_OUTPUT
        mock.side_effect = fake
        result = asyncio.run(metrics_tool.get_nf_metrics())

    # Header should appear once.
    assert "Types:" in result
    assert "[counter]" in result
    assert "[gauge]" in result

    # ran_ue resolves directly → [gauge, count]
    assert "ran_ue = 2  [gauge, count]" in result

    # Raw Prometheus counter resolves via raw_sources → [counter] with see KB: hint
    assert "fivegs_ep_n3_gtp_indatapktn3upf = 9371  [counter]" in result
    assert "see KB: `core.upf.gtp_indatapktn3upf_per_ue`" in result

    # Kamailio counter resolves via raw_sources → [counter] with see KB: hint
    assert "script:register_time = 52910  [counter]" in result
    assert "see KB: `ims.pcscf.avg_register_time_ms`" in result

    # SIP reply counter resolves to sip_error_ratio derived
    assert "sl:4xx_replies = 6  [counter]" in result


def test_annotation_leaves_unknown_metrics_with_fallback():
    output = """
UPF (via prometheus):
  some_made_up_metric = 42
"""
    with patch("agentic_ops_common.tools.metrics._t.get_nf_metrics") as mock:
        async def fake(_deps):
            return output
        mock.side_effect = fake
        result = asyncio.run(metrics_tool.get_nf_metrics())

    # Either [uncategorized] or a heuristic tag — but the line should not be unchanged.
    assert "some_made_up_metric = 42" in result
    assert "[uncategorized]" in result or "[counter]" in result or "[gauge]" in result


def test_annotation_preserves_section_headers():
    with patch("agentic_ops_common.tools.metrics._t.get_nf_metrics") as mock:
        async def fake(_deps):
            return _SAMPLE_COLLECTOR_OUTPUT
        mock.side_effect = fake
        result = asyncio.run(metrics_tool.get_nf_metrics())

    assert "AMF [2 UE] (via prometheus):" in result
    assert "UPF [32 pkt] (via prometheus):" in result
    assert "PCSCF (via kamcmd):" in result


def test_annotation_skips_private_keys():
    """Keys starting with `_` (like `_gauge_upf_kbps`) are left untouched."""
    with patch("agentic_ops_common.tools.metrics._t.get_nf_metrics") as mock:
        async def fake(_deps):
            return _SAMPLE_COLLECTOR_OUTPUT
        mock.side_effect = fake
        result = asyncio.run(metrics_tool.get_nf_metrics())

    # The line is present but not annotated with a type tag
    assert "_gauge_upf_kbps = 0.0" in result
    # No tag appended
    assert "_gauge_upf_kbps = 0.0  [" not in result
