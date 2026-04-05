"""Log search — read and search container logs."""

from __future__ import annotations
from ._common import _t, _get_deps, _truncate_output


async def read_container_logs(
    container: str,
    tail: int = 200,
    grep: str | None = None,
    since_seconds: int | None = None,
) -> str:
    """Read recent logs from a Docker container.

    Args:
        container: Container name (e.g. 'pcscf', 'scscf', 'amf').
        tail: Number of recent lines to return (default 200).
        grep: Optional pattern to filter log lines (case-insensitive).
        since_seconds: Only return log lines from the last N seconds. Use
            this to avoid stale historical lines from previous runs.
            Translates to `docker logs --since Ns`. Prefer this for
            time-bounded investigations — a typical starting value is 120
            (2 minutes). Widen to 300 or 900 only if nothing is found.
    """
    result = await _t.read_container_logs(
        _get_deps(), container, tail=tail, grep=grep, since_seconds=since_seconds,
    )
    if not grep:
        return _truncate_output(result)
    return result


async def search_logs(pattern: str, containers: list[str] | None = None, since: str | None = None) -> str:
    """Search for a pattern across multiple container logs.

    Args:
        pattern: Search pattern (case-insensitive). Can be a Call-ID,
                 IMSI, SIP method, error keyword, etc.
        containers: Optional list of containers to search. Searches all if None.
        since: Optional time filter (e.g. '5m', '1h').
    """
    result = await _t.search_logs(_get_deps(), pattern, containers, since)
    return _truncate_output(result)
