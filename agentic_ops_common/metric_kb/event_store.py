"""SQLite-backed event store.

Persists events fired by the trigger evaluator. Consumed by the correlation
engine and by the v6 agentic pipeline's Phase 1 (EventAggregator).

Schema is minimal — one `events` table, one `event_id_firing_state` table
for persistence tracking across evaluation passes.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("metric_kb.event_store")

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_DB_PATH = _REPO_ROOT / "agentic_ops_common" / "metric_kb" / "events.db"


# ----------------------------------------------------------------------------
# Event dataclass
# ----------------------------------------------------------------------------

@dataclass
class FiredEvent:
    """A single event fired by the evaluator.

    Persisted to the event store. Consumed by the correlation engine and by
    agent tools.
    """
    event_type: str          # <layer>.<nf>.<event_name>
    source_metric: str       # <layer>.<nf>.<metric_name>
    source_nf: str           # nf name
    timestamp: float         # when the event was first observed
    magnitude_payload: dict[str, Any] = field(default_factory=dict)
    episode_id: Optional[str] = None
    cleared_at: Optional[float] = None
    id: Optional[int] = None  # populated on insert

    def to_row(self) -> tuple:
        return (
            self.event_type,
            self.source_metric,
            self.source_nf,
            self.timestamp,
            json.dumps(self.magnitude_payload),
            self.episode_id,
            self.cleared_at,
        )


# ----------------------------------------------------------------------------
# Store
# ----------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type         TEXT NOT NULL,
    source_metric      TEXT NOT NULL,
    source_nf          TEXT NOT NULL,
    timestamp          REAL NOT NULL,
    magnitude_payload  TEXT NOT NULL,
    episode_id         TEXT,
    cleared_at         REAL
);

CREATE INDEX IF NOT EXISTS idx_events_episode
    ON events(episode_id, timestamp);

CREATE INDEX IF NOT EXISTS idx_events_type_episode
    ON events(event_type, episode_id);

CREATE INDEX IF NOT EXISTS idx_events_nf_episode
    ON events(source_nf, episode_id);
"""


class EventStore:
    """SQLite-backed event store.

    Thread-unsafe by default — each instance owns one connection. For the
    agent-driven evaluator model (one evaluation at a time), this is fine.
    """

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self._path = db_path or _DEFAULT_DB_PATH
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # --- Write ---

    def insert(self, event: FiredEvent) -> int:
        """Insert a fired event. Returns the inserted row id."""
        cur = self._conn.execute(
            """
            INSERT INTO events (event_type, source_metric, source_nf, timestamp,
                                magnitude_payload, episode_id, cleared_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            event.to_row(),
        )
        self._conn.commit()
        row_id = cur.lastrowid
        event.id = row_id
        log.debug("Inserted event %s (id=%s) at t=%s for episode=%s",
                  event.event_type, row_id, event.timestamp, event.episode_id)
        return row_id

    def mark_cleared(self, event_id: int, cleared_at: float) -> None:
        """Mark an event as cleared."""
        self._conn.execute(
            "UPDATE events SET cleared_at = ? WHERE id = ?",
            (cleared_at, event_id),
        )
        self._conn.commit()

    # --- Read ---

    def get_events(
        self,
        *,
        episode_id: Optional[str] = None,
        event_type: Optional[str] = None,
        source_nf: Optional[str] = None,
        since: Optional[float] = None,
        until: Optional[float] = None,
        include_cleared: bool = True,
    ) -> list[FiredEvent]:
        """Query the event store with flexible filters."""
        query = "SELECT * FROM events WHERE 1=1"
        args: list[Any] = []
        if episode_id is not None:
            query += " AND episode_id = ?"
            args.append(episode_id)
        if event_type is not None:
            query += " AND event_type = ?"
            args.append(event_type)
        if source_nf is not None:
            query += " AND source_nf = ?"
            args.append(source_nf)
        if since is not None:
            query += " AND timestamp >= ?"
            args.append(since)
        if until is not None:
            query += " AND timestamp <= ?"
            args.append(until)
        if not include_cleared:
            query += " AND cleared_at IS NULL"
        query += " ORDER BY timestamp ASC"

        cur = self._conn.execute(query, args)
        return [self._row_to_event(row) for row in cur.fetchall()]

    def latest_event_of_type(
        self, event_type: str, episode_id: Optional[str] = None
    ) -> Optional[FiredEvent]:
        """Return the most recent event of a given type (optionally scoped
        to an episode), or None if none exist.
        """
        query = "SELECT * FROM events WHERE event_type = ?"
        args: list[Any] = [event_type]
        if episode_id is not None:
            query += " AND episode_id = ?"
            args.append(episode_id)
        query += " ORDER BY timestamp DESC LIMIT 1"
        row = self._conn.execute(query, args).fetchone()
        return self._row_to_event(row) if row else None

    def count(self, *, episode_id: Optional[str] = None) -> int:
        """Count events, optionally scoped to an episode."""
        if episode_id is not None:
            cur = self._conn.execute(
                "SELECT COUNT(*) FROM events WHERE episode_id = ?",
                (episode_id,),
            )
        else:
            cur = self._conn.execute("SELECT COUNT(*) FROM events")
        return cur.fetchone()[0]

    # --- Helpers ---

    def _row_to_event(self, row: sqlite3.Row) -> FiredEvent:
        return FiredEvent(
            id=row["id"],
            event_type=row["event_type"],
            source_metric=row["source_metric"],
            source_nf=row["source_nf"],
            timestamp=row["timestamp"],
            magnitude_payload=json.loads(row["magnitude_payload"]),
            episode_id=row["episode_id"],
            cleared_at=row["cleared_at"],
        )

    def clear_all(self) -> None:
        """Dev-only: wipe every event. Useful in tests."""
        self._conn.execute("DELETE FROM events")
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "EventStore":
        return self

    def __exit__(self, *args) -> None:
        self.close()
