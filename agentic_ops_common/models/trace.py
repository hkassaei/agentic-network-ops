"""Shared trace models used across agent versions.

These represent the record of an investigation's execution: which phases ran,
what tools each called, how long each took, token consumption. They have no
dependency on any specific agent version — any orchestrator (v5, v6, future)
can populate them.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class TokenBreakdown(BaseModel):
    prompt: int = 0
    completion: int = 0
    thinking: int = 0
    total: int = 0


class ToolCallTrace(BaseModel):
    name: str
    args: str = ""
    result_size: int = 0
    timestamp: float = 0.0


class PhaseTrace(BaseModel):
    agent_name: str
    started_at: float = 0.0
    finished_at: float = 0.0
    duration_ms: int = 0
    tokens: TokenBreakdown = Field(default_factory=TokenBreakdown)
    tool_calls: list[ToolCallTrace] = Field(default_factory=list)
    llm_calls: int = 0
    output_summary: str = ""
    state_keys_written: list[str] = Field(default_factory=list)


class InvestigationTrace(BaseModel):
    question: str = ""
    started_at: float = 0.0
    finished_at: float = 0.0
    duration_ms: int = 0
    total_tokens: TokenBreakdown = Field(default_factory=TokenBreakdown)
    phases: list[PhaseTrace] = Field(default_factory=list)
    invocation_chain: list[str] = Field(default_factory=list)
