"""
CallSetupAgent / CallTeardownAgent — establish and tear down a VoNR call.

Used by data plane scenarios that need active RTP traffic flowing through
the UPF before fault injection. Without an active call, packet loss on
the UPF produces zero observable symptoms.

Controlled by scenario.requires_active_call — skips if False.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import AsyncGenerator

from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.genai import types

from ..tools.application_tools import establish_vonr_call, hangup_call
from ..tools.observation_tools import _load_env

log = logging.getLogger("chaos-agent.call-setup")


def _get_ims_domain(env: dict[str, str]) -> str:
    """Derive the IMS domain from MCC/MNC in the environment."""
    mcc = env.get("MCC", "001")
    mnc = env.get("MNC", "01")
    if len(mnc) == 3:
        return f"ims.mnc{mnc}.mcc{mcc}.3gppnetwork.org"
    return f"ims.mnc0{mnc}.mcc{mcc}.3gppnetwork.org"


class CallSetupAgent(BaseAgent):
    """Establishes a VoNR call between UE1 and UE2 before fault injection."""

    name: str = "CallSetupAgent"
    description: str = "Establishes a VoNR call for data plane scenarios."

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        scenario = ctx.session.state.get("scenario", {})

        # Support both the new required_traffic field and the legacy
        # requires_active_call boolean. A scenario only needs user-plane
        # traffic (active call) if explicitly marked so.
        required_traffic = scenario.get("required_traffic", "none")
        legacy_flag = scenario.get("requires_active_call", False)
        needs_active_call = required_traffic == "user_plane" or legacy_flag

        if not needs_active_call:
            yield Event(
                author=self.name,
                content=types.Content(
                    parts=[types.Part(text=(
                        f"Call setup: skipped — required_traffic="
                        f"'{required_traffic}' does not need user-plane traffic"
                    ))],
                ),
            )
            return

        log.info("Establishing VoNR call for user-plane scenario...")

        env = _load_env()
        ims_domain = _get_ims_domain(env)
        callee_imsi = env.get("UE2_IMSI", "001011234567892")

        result = await establish_vonr_call(ims_domain, callee_imsi)

        if result["success"]:
            # Wait for call to stabilize before fault injection.
            # RTCP reports (MOS, jitter, loss) are sent every ~5 seconds.
            # Prometheus scrapes every 5 seconds. A 20-second delay ensures
            # at least 3-4 RTCP samples are in Prometheus so rate() queries
            # return meaningful data when the triage agent calls
            # get_dp_quality_gauges after fault injection.
            import asyncio
            log.info("Call established, waiting 20s for media to stabilize...")
            await asyncio.sleep(20)
            msg = f"Call setup: VoNR call established and stabilized ({result['call_uri']})"
            log.info(msg)
        else:
            msg = f"Call setup: FAILED — {result['detail']}"
            log.warning(msg)

        yield Event(
            author=self.name,
            content=types.Content(parts=[types.Part(text=msg)]),
            actions=EventActions(state_delta={
                "call_active": result["success"],
                "call_uri": result.get("call_uri", ""),
            }),
        )

    async def _run_live_impl(self, ctx):
        raise NotImplementedError


class CallTeardownAgent(BaseAgent):
    """Hangs up the active VoNR call after healing."""

    name: str = "CallTeardownAgent"
    description: str = "Tears down the VoNR call after the scenario completes."

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        if not ctx.session.state.get("call_active", False):
            yield Event(
                author=self.name,
                content=types.Content(
                    parts=[types.Part(text="Call teardown: skipped (no active call)")],
                ),
            )
            return

        log.info("Tearing down VoNR call...")

        result = await hangup_call()

        if result["success"]:
            msg = "Call teardown: hangup sent"
            log.info(msg)
        else:
            msg = f"Call teardown: hangup failed — {result['detail']}"
            log.warning(msg)

        yield Event(
            author=self.name,
            content=types.Content(parts=[types.Part(text=msg)]),
            actions=EventActions(state_delta={"call_active": False}),
        )

    async def _run_live_impl(self, ctx):
        raise NotImplementedError
