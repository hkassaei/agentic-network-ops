"""Single source of truth for v7's Gemini model selection.

Every v7 subagent picks one of two "slots":
  - pro   — high-reasoning workloads (investigator, synthesis, network
            analyst, instruction generator)
  - flash — lightweight / structured-output workloads (ontology
            consultation, chaos LLM scorer)

The model id for each slot is read from the environment at call time.
If unset, the in-code defaults below take effect. This means a single
sweep can switch the model family for every v7 subagent (and the chaos
scorer) by exporting two variables — no source edits required:

    GEMINI_PRO_MODEL=gemini-3.1-pro \\
    GEMINI_FLASH_MODEL=gemini-3.1-flash \\
    GOOGLE_CLOUD_LOCATION=global \\
    ./scripts/run-all-chaos-scenarios.sh --agent v7 ...

Reading the env at call time (not import time) is deliberate: tests
monkeypatch the env before invoking a factory, and the chaos runner
launches sub-runs with different env without restarting Python.

The chaos ChallengeAgent reads pro_model_id() + flash_model_id() when
it builds the episode's rca_agent_model label, so each episode JSON /
markdown records exactly which ids were resolved at run time.
"""

from __future__ import annotations

import os

from .retry_config import make_retry_model

_DEFAULT_PRO = "gemini-2.5-pro"
_DEFAULT_FLASH = "gemini-2.5-flash"


def pro_model_id() -> str:
    return os.environ.get("GEMINI_PRO_MODEL", _DEFAULT_PRO)


def flash_model_id() -> str:
    return os.environ.get("GEMINI_FLASH_MODEL", _DEFAULT_FLASH)


def pro_model():
    """Gemini wrapper for the 'pro' slot, with shared retry policy."""
    return make_retry_model(pro_model_id())


def flash_model():
    """Gemini wrapper for the 'flash' slot, with shared retry policy."""
    return make_retry_model(flash_model_id())
