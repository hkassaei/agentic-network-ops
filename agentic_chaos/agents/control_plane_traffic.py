"""
ControlPlaneTrafficAgent — generate fresh SIP signaling after fault injection.

Many IMS failure scenarios target the control plane (P-CSCF latency, S-CSCF
crash, HSS unresponsive, IMS partition, DNS failure, MongoDB gone, cascading
IMS failure). Without fresh signaling traffic, these faults produce no
observable symptoms: existing UE registrations remain cached and nothing
exercises the affected path.

This agent forces a fresh SIP REGISTER transaction from each UE by writing
the 'rr' command to pjsua's FIFO. The re-registration flows through the
full IMS signaling chain (P-CSCF → I-CSCF → S-CSCF → HSS via Diameter),
which is now sitting behind the injected fault — producing the timeouts,
errors, or stalls that the FaultPropagationVerifier and the RCA agent are
supposed to see.

Runs between FaultInjector and FaultPropagationVerifier so the traffic hits
the stack AFTER the fault is in place. Controlled by
scenario.required_traffic == "control_plane" — skips otherwise.
"""

from __future__ import annotations

import asyncio
import logging
from typing import AsyncGenerator

from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.genai import types

from ..tools.application_tools import trigger_sip_reregister

log = logging.getLogger("chaos-agent.control-plane-traffic")


# UE containers that pjsua runs in. Both UEs are re-registered so the
# affected path sees >1 transaction — one UE's re-register landing in a
# lucky code path doesn't mask the fault.
_UE_CONTAINERS = ("e2e_ue1", "e2e_ue2")

# Pause after sending 'rr' so the REGISTER has time to actually traverse
# the IMS chain (P-CSCF → I-CSCF → Diameter to HSS → S-CSCF → back). On a
# healthy stack this completes in <1s; under the fault it may never
# complete, but we still want the transaction in flight before the
# FaultPropagationVerifier starts measuring.
_REGISTER_PROPAGATION_SECONDS = 3


class ControlPlaneTrafficAgent(BaseAgent):
    """Triggers fresh SIP REGISTER from both UEs after fault injection."""

    name: str = "ControlPlaneTrafficAgent"
    description: str = (
        "Generates fresh SIP signaling traffic for control-plane fault scenarios."
    )

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        scenario = ctx.session.state.get("scenario", {})
        required_traffic = scenario.get("required_traffic", "none")

        if required_traffic != "control_plane":
            yield Event(
                author=self.name,
                content=types.Content(
                    parts=[types.Part(text=(
                        f"Control-plane traffic: skipped — required_traffic="
                        f"'{required_traffic}' does not need SIP signaling"
                    ))],
                ),
            )
            return

        log.info(
            "Triggering fresh SIP REGISTER from %d UE(s) to exercise "
            "the fault path...", len(_UE_CONTAINERS),
        )

        results: list[str] = []
        any_success = False
        for ue in _UE_CONTAINERS:
            result = await trigger_sip_reregister(ue)
            if result["success"]:
                any_success = True
                results.append(f"{ue}=OK")
                log.info("  %s: re-register triggered", ue)
            else:
                results.append(f"{ue}=FAIL({result['detail'][:80]})")
                log.warning("  %s: re-register FAILED — %s", ue, result["detail"])

        # Give the REGISTER transactions a moment to propagate through
        # the IMS signaling chain before the verifier starts its window.
        if any_success:
            log.info(
                "Waiting %ds for REGISTER transactions to propagate through IMS...",
                _REGISTER_PROPAGATION_SECONDS,
            )
            await asyncio.sleep(_REGISTER_PROPAGATION_SECONDS)

        msg = (
            f"Control-plane traffic: re-register sent to "
            f"{len(_UE_CONTAINERS)} UE(s) [{', '.join(results)}]"
        )
        yield Event(
            author=self.name,
            content=types.Content(parts=[types.Part(text=msg)]),
            actions=EventActions(state_delta={
                "control_plane_traffic_triggered": any_success,
            }),
        )

    async def _run_live_impl(self, ctx):
        raise NotImplementedError
