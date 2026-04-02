"""Shared utilities for all v5 tool modules."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Setup import path for agentic_ops v1.5 base tools
_REPO_ROOT = Path(__file__).resolve().parents[2]
_OPS_PATH = str(_REPO_ROOT)
if _OPS_PATH not in sys.path:
    sys.path.insert(0, _OPS_PATH)

from agentic_ops import tools as _t  # noqa: E402
from agentic_ops.models import AgentDeps  # noqa: E402

_MAX_OUTPUT_BYTES = 10_240  # 10 KB


def _truncate_output(text: str, max_bytes: int = _MAX_OUTPUT_BYTES) -> str:
    """Keep the tail (most recent lines), discard oldest lines from the top."""
    if len(text.encode("utf-8")) <= max_bytes:
        return text

    lines = text.splitlines(keepends=True)
    kept: list[str] = []
    total = 0
    for line in reversed(lines):
        line_bytes = len(line.encode("utf-8"))
        if total + line_bytes > max_bytes:
            break
        kept.append(line)
        total += line_bytes

    kept.reverse()
    omitted = len(lines) - len(kept)
    prefix = f"... truncated ({omitted} older lines omitted). Use grep to narrow your search.\n"
    return prefix + "".join(kept)


_deps: AgentDeps | None = None


def _get_deps() -> AgentDeps:
    global _deps
    if _deps is not None:
        return _deps

    env: dict[str, str] = {**os.environ}
    for p in [_REPO_ROOT / "network" / ".env", _REPO_ROOT / "e2e.env"]:
        if p.exists():
            for line in p.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()

    _deps = AgentDeps(
        repo_root=_REPO_ROOT,
        env=env,
        pyhss_api=f"http://{env.get('PYHSS_IP', '172.22.0.18')}:8080",
    )
    return _deps
