"""EventAggregator — reads fired events from the store for the current episode.

Not an LLM. Called by the orchestrator as a plain function to populate
session state with events that downstream phases consume.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from agentic_ops_common.metric_kb import EventStore, FiredEvent

log = logging.getLogger("v6.event_aggregator")


def aggregate_episode_events(
    episode_id: str, store_path: Optional[str] = None,
) -> tuple[list[FiredEvent], str]:
    """Read all events for an episode, return (events, rendered_text).

    The rendered_text is a pretty-printed summary ready to inject into
    LLM prompts as the `{fired_events}` template variable.
    """
    store = EventStore(store_path)
    try:
        events = store.get_events(episode_id=episode_id)
    finally:
        store.close()

    log.info("EventAggregator: %d events for episode %s",
             len(events), episode_id)

    if not events:
        return [], (
            "No events fired during this episode. Either no metric KB "
            "triggers matched, or the episode encountered no meaningful "
            "state transitions."
        )

    lines = [f"**{len(events)} events fired during the observation window:**\n"]
    for e in events:
        line = (
            f"- `{e.event_type}` (source: `{e.source_metric}`, "
            f"nf: `{e.source_nf}`, t={e.timestamp:.1f})"
        )
        if e.magnitude_payload:
            # Show 2-3 key magnitude fields
            parts = []
            for k in ["current_value", "prior_stable_value", "delta_percent"]:
                if k in e.magnitude_payload and e.magnitude_payload[k] is not None:
                    v = e.magnitude_payload[k]
                    parts.append(f"{k}={v}")
            if parts:
                line += "  [" + ", ".join(parts) + "]"
        lines.append(line)

    return events, "\n".join(lines)
