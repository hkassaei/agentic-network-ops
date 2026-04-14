"""
ObservationTrafficAgent — generate extended IMS traffic under fault conditions
and collect metric snapshots for the anomaly screener.

Runs AFTER the FaultPropagationVerifier confirms the fault is active, and
BEFORE the ChallengeAgent invokes the RCA agent. Generates randomized IMS
traffic (SIP REGISTER, VoNR calls) for a configurable duration while
collecting metric snapshots every 5 seconds.

The collected snapshots are stored in session state as `observation_snapshots`
and passed to the v5 investigate() pipeline, where Phase 0 (AnomalyScreener)
scores them against the pre-trained healthy-state model to detect anomalies.

Duration is controlled by scenario.observation_traffic_seconds (default: 120).

This is a general-purpose capability: any scenario can set
observation_traffic_seconds to enable extended traffic generation and
metric collection under fault conditions.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import AsyncGenerator

from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.genai import types

from ..tools.application_tools import (
    trigger_sip_reregister,
    establish_vonr_call,
    hangup_call,
)
from ..tools.observation_tools import snapshot_metrics, _load_env

log = logging.getLogger("chaos-agent.observation-traffic")

_UE_CONTAINERS = ("e2e_ue1", "e2e_ue2")
_METRIC_POLL_INTERVAL = 5  # seconds


def _get_ims_domain(env: dict[str, str]) -> str:
    mcc = env.get("MCC", "001")
    mnc = env.get("MNC", "01")
    if len(mnc) == 3:
        return f"ims.mnc{mnc}.mcc{mcc}.3gppnetwork.org"
    return f"ims.mnc0{mnc}.mcc{mcc}.3gppnetwork.org"


class ObservationTrafficAgent(BaseAgent):
    """Generates extended IMS traffic under fault conditions + collects metrics.

    After the fault verifier confirms the fault is active, this agent:
    1. Generates randomized IMS traffic (REGISTER, VoNR calls) for the
       configured duration
    2. Collects metric snapshots every 5 seconds throughout
    3. Stores the snapshots in session state for the anomaly screener
    """

    name: str = "ObservationTrafficAgent"
    description: str = (
        "Generates extended IMS traffic under fault conditions while "
        "collecting metric snapshots for the anomaly screener."
    )

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        scenario = ctx.session.state.get("scenario", {})
        duration = scenario.get("observation_traffic_seconds", 0)

        if duration <= 0:
            yield Event(
                author=self.name,
                content=types.Content(
                    parts=[types.Part(text=(
                        "Observation traffic: skipped — "
                        "observation_traffic_seconds not set"
                    ))],
                ),
            )
            return

        # Skip if episode was aborted
        if ctx.session.state.get("episode_aborted", False):
            yield Event(
                author=self.name,
                content=types.Content(
                    parts=[types.Part(text="Observation traffic: skipped — episode aborted")],
                ),
            )
            return

        log.info("Starting observation traffic generation for %ds...", duration)

        env = _load_env()
        ims_domain = _get_ims_domain(env)
        callee_imsi = env.get("UE2_IMSI", "001011234567892")

        # Record the observation window timestamps
        observation_start = time.time()

        # Run traffic generation and metric collection concurrently.
        # Both tasks are wrapped in try/except to prevent crashes from
        # killing the entire pipeline (which would skip the ChallengeAgent).
        snapshots: list[dict] = []
        traffic_task = asyncio.create_task(
            self._generate_traffic(duration, ims_domain, callee_imsi)
        )
        collector_task = asyncio.create_task(
            self._collect_metrics(duration, snapshots)
        )

        results = await asyncio.gather(traffic_task, collector_task, return_exceptions=True)
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                task_name = "traffic generation" if i == 0 else "metric collection"
                log.warning("ObservationTrafficAgent: %s failed: %s", task_name, r)

        observation_end = time.time()
        elapsed_since_start = int(observation_end - observation_start)

        log.info("Observation traffic complete: %d metric snapshots collected "
                 "over %ds", len(snapshots), elapsed_since_start)

        msg = (
            f"Observation traffic: generated IMS traffic for {elapsed_since_start}s, "
            f"collected {len(snapshots)} metric snapshots"
        )
        yield Event(
            author=self.name,
            content=types.Content(parts=[types.Part(text=msg)]),
            actions=EventActions(state_delta={
                "observation_snapshots": snapshots,
                "observation_window_start": observation_start,
                "observation_window_end": observation_end,
                "observation_window_duration": elapsed_since_start,
            }),
        )

    async def _generate_traffic(
        self, duration: int, ims_domain: str, callee_imsi: str
    ) -> None:
        """Generate randomized IMS traffic for the specified duration.

        Uses wall-clock time (not accumulated sleep time) to ensure the
        traffic generator runs for exactly the specified duration, regardless
        of how long individual operations take (e.g., failed VoNR calls
        timeout after 30s under fault conditions).
        """
        start = time.time()
        call_count = 0
        register_count = 0

        while (time.time() - start) < duration:
            remaining = duration - (time.time() - start)
            if remaining < 3:
                break

            activity = random.choices(
                ["register_both", "register_one", "call", "idle"],
                weights=[20, 15, 45, 20],
            )[0]

            elapsed = time.time() - start

            if activity == "register_both":
                log.debug("[T+%.0fs] Re-registering both UEs", elapsed)
                await trigger_sip_reregister("e2e_ue1")
                await asyncio.sleep(1)
                await trigger_sip_reregister("e2e_ue2")
                register_count += 2
                await asyncio.sleep(random.uniform(3, 8))

            elif activity == "register_one":
                ue = random.choice(list(_UE_CONTAINERS))
                log.debug("[T+%.0fs] Re-registering %s", elapsed, ue)
                await trigger_sip_reregister(ue)
                register_count += 1
                await asyncio.sleep(random.uniform(3, 6))

            elif activity == "call":
                if remaining < 15:
                    # Not enough time for a call — do a register instead
                    await trigger_sip_reregister("e2e_ue1")
                    register_count += 1
                    await asyncio.sleep(3)
                    continue

                call_duration = random.uniform(5, min(20, remaining - 10))
                log.debug("[T+%.0fs] Placing VoNR call (hold %.0fs)", elapsed, call_duration)
                result = await establish_vonr_call(ims_domain, callee_imsi)
                if result.get("success"):
                    call_count += 1
                    await asyncio.sleep(call_duration)
                    await hangup_call()
                    await asyncio.sleep(random.uniform(3, 6))
                else:
                    log.debug("[T+%.0fs] Call failed (expected under fault)", time.time() - start)
                    await asyncio.sleep(random.uniform(3, 6))

            else:  # idle
                idle_time = random.uniform(3, 8)
                log.debug("[T+%.0fs] Idle for %.0fs", elapsed, idle_time)
                await asyncio.sleep(idle_time)

        actual_duration = int(time.time() - start)
        log.info("Traffic generation done: %d calls, %d registrations in %ds",
                 call_count, register_count, actual_duration)

    async def _collect_metrics(
        self, duration: int, snapshots: list[dict]
    ) -> None:
        """Collect metric snapshots every 5 seconds for the duration."""
        start = time.time()
        while (time.time() - start) < duration:
            try:
                metrics = await snapshot_metrics()
                if metrics:
                    metrics["_timestamp"] = time.time()
                    snapshots.append(metrics)
            except Exception as e:
                log.warning("Metric collection error: %s", e)

            await asyncio.sleep(_METRIC_POLL_INTERVAL)

        log.info("Metric collection done: %d snapshots", len(snapshots))

    async def _run_live_impl(self, ctx):
        raise NotImplementedError
