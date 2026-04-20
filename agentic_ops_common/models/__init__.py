"""Shared models used across agent versions."""

from .trace import (
    InvestigationTrace,
    PhaseTrace,
    ToolCallTrace,
    TokenBreakdown,
)

__all__ = [
    "InvestigationTrace",
    "PhaseTrace",
    "ToolCallTrace",
    "TokenBreakdown",
]
