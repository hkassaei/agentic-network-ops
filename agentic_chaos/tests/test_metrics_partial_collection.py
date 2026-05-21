"""Partial-result behavior for `MetricsCollector.collect()`.

Pins the contract from ADR `docs/ADR/screener_starvation_partial_metric_collection.md`:
sub-collectors that exceed `_COLLECT_DEADLINE` are cancelled and their NFs
are simply absent from the snapshot; sub-collectors that completed in time
appear in the merged dict. The previous all-or-nothing `asyncio.gather`
pattern would have returned an empty dict in the same scenario, which is
the root cause of screener starvation.

Subprocess-cleanup behavior (the `_reap` helper) is tested indirectly:
the slow sub-collector here doesn't own a real `docker exec` process, so
the cancellation path exercises only the coroutine-level cleanup. A
stress test against a live stack (see runbook) is the right place to
verify zombie-process counts.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

# `gui/metrics.py` is loaded at runtime via the path indirection in
# `agentic_chaos/tools/observation_tools.py`. Mirror that here so the
# test exercises the same module the production code uses.
_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "gui"))


@pytest.mark.asyncio
async def test_partial_result_excludes_slow_collector(monkeypatch):
    """A sub-collector that exceeds _COLLECT_DEADLINE is dropped; others survive.

    Without the partial-result fix, the previous outer-`wait_for` cancelled
    every sub-collector together and `collect()` returned `{}`. After the
    fix, fast sub-collectors appear in the merged dict; the slow one's NF
    is simply absent.
    """
    import metrics as metrics_mod

    # Shorten the deadline so the test doesn't take 12 real seconds.
    monkeypatch.setattr(metrics_mod, "_COLLECT_DEADLINE", 0.5)

    collector = metrics_mod.MetricsCollector(env={})

    # Force a fresh collection (skip cache).
    collector._cache_ts = 0.0

    async def fast_prom():
        return {"amf": {"metrics": {"ran_ue": 2}, "badge": "2 UE", "source": "prom"}}

    async def slow_kam(container):
        # Sleeps well past the deadline. Must be cancellable.
        await asyncio.sleep(5)
        return {"metrics": {"foo": 1}, "badge": "", "source": "kamcmd"}

    async def fast_rtp():
        return {"metrics": {"current_sessions_own": 0}, "badge": "", "source": "rtp"}

    async def fast_pyhss():
        return {"metrics": {"ims_subscribers": 2}, "badge": "2 subs", "source": "api"}

    async def fast_mongo():
        return {"metrics": {"subscribers": 2}, "badge": "2 subs", "source": "mongosh"}

    monkeypatch.setattr(collector, "_collect_prometheus", fast_prom)
    monkeypatch.setattr(collector, "_collect_kamailio", slow_kam)
    monkeypatch.setattr(collector, "_collect_rtpengine", fast_rtp)
    monkeypatch.setattr(collector, "_collect_pyhss", fast_pyhss)
    monkeypatch.setattr(collector, "_collect_mongo", fast_mongo)

    merged = await collector.collect()

    # Fast collectors appear:
    assert "amf" in merged                 # from prometheus
    assert "rtpengine" in merged
    assert "pyhss" in merged
    assert "mongo" in merged

    # The three slow CSCF kamcmd collectors are absent (cancelled at deadline):
    assert "pcscf" not in merged
    assert "icscf" not in merged
    assert "scscf" not in merged

    # And critically — the returned dict is non-empty, which is the
    # whole point. Pre-fix, this same scenario returned `{}`.
    assert merged != {}


@pytest.mark.asyncio
async def test_all_fast_collectors_complete(monkeypatch):
    """When every sub-collector finishes well under the deadline,
    every NF appears in the merged dict (no behavioral regression
    on the happy path)."""
    import metrics as metrics_mod

    monkeypatch.setattr(metrics_mod, "_COLLECT_DEADLINE", 1.0)

    collector = metrics_mod.MetricsCollector(env={})
    collector._cache_ts = 0.0

    async def fast_prom():
        return {"amf": {"metrics": {"ran_ue": 2}, "badge": "", "source": "prom"}}

    async def fast_kam(container):
        return {"metrics": {f"{container}_foo": 1}, "badge": "", "source": "kamcmd"}

    async def fast_rtp():
        return {"metrics": {"a": 1}, "badge": "", "source": "rtp"}

    async def fast_pyhss():
        return {"metrics": {"ims_subscribers": 2}, "badge": "", "source": "api"}

    async def fast_mongo():
        return {"metrics": {"subscribers": 2}, "badge": "", "source": "mongo"}

    monkeypatch.setattr(collector, "_collect_prometheus", fast_prom)
    monkeypatch.setattr(collector, "_collect_kamailio", fast_kam)
    monkeypatch.setattr(collector, "_collect_rtpengine", fast_rtp)
    monkeypatch.setattr(collector, "_collect_pyhss", fast_pyhss)
    monkeypatch.setattr(collector, "_collect_mongo", fast_mongo)

    merged = await collector.collect()

    # All seven sources represented (amf comes from prom; the rest are
    # the NF-named entries we monkeypatched).
    assert "amf" in merged
    assert "pcscf" in merged
    assert "icscf" in merged
    assert "scscf" in merged
    assert "rtpengine" in merged
    assert "pyhss" in merged
    assert "mongo" in merged


@pytest.mark.asyncio
async def test_raising_collector_does_not_kill_snapshot(monkeypatch):
    """A sub-collector that raises an exception is logged and skipped;
    other sub-collectors' results still appear. This was already true
    pre-fix via `return_exceptions=True`, but the refactor must
    preserve it."""
    import metrics as metrics_mod

    monkeypatch.setattr(metrics_mod, "_COLLECT_DEADLINE", 1.0)

    collector = metrics_mod.MetricsCollector(env={})
    collector._cache_ts = 0.0

    async def fast_prom():
        return {"amf": {"metrics": {"ran_ue": 2}, "badge": "", "source": "prom"}}

    async def boom_kam(container):
        raise RuntimeError("simulated kamcmd connection refused")

    async def fast_rtp():
        return {"metrics": {"a": 1}, "badge": "", "source": "rtp"}

    async def fast_pyhss():
        return {"metrics": {"ims_subscribers": 2}, "badge": "", "source": "api"}

    async def fast_mongo():
        return {"metrics": {"subscribers": 2}, "badge": "", "source": "mongo"}

    monkeypatch.setattr(collector, "_collect_prometheus", fast_prom)
    monkeypatch.setattr(collector, "_collect_kamailio", boom_kam)
    monkeypatch.setattr(collector, "_collect_rtpengine", fast_rtp)
    monkeypatch.setattr(collector, "_collect_pyhss", fast_pyhss)
    monkeypatch.setattr(collector, "_collect_mongo", fast_mongo)

    merged = await collector.collect()

    # Raising collectors are omitted, not propagated.
    assert "pcscf" not in merged
    assert "icscf" not in merged
    assert "scscf" not in merged
    # Other collectors still landed.
    assert "amf" in merged
    assert "rtpengine" in merged
    assert "pyhss" in merged
    assert "mongo" in merged
