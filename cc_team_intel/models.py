"""Pydantic data models for cc-team-intel."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Pricing table (per-million-token, USD)
# Updated: 2025-05
# ---------------------------------------------------------------------------

MODEL_PRICING: Dict[str, Dict[str, float]] = {
    "claude-opus-4-7": {
        "input": 15.00,
        "output": 75.00,
        "cache_read": 1.50,
        "cache_write": 18.75,
    },
    "claude-opus-4-6": {
        "input": 15.00,
        "output": 75.00,
        "cache_read": 1.50,
        "cache_write": 18.75,
    },
    "claude-sonnet-4-6": {
        "input": 3.00,
        "output": 15.00,
        "cache_read": 0.30,
        "cache_write": 3.75,
    },
    "claude-sonnet-4-5": {
        "input": 3.00,
        "output": 15.00,
        "cache_read": 0.30,
        "cache_write": 3.75,
    },
    "claude-haiku-4-5": {
        "input": 0.80,
        "output": 4.00,
        "cache_read": 0.08,
        "cache_write": 1.00,
    },
    "claude-haiku-4-5-20251001": {
        "input": 0.80,
        "output": 4.00,
        "cache_read": 0.08,
        "cache_write": 1.00,
    },
}

DEFAULT_PRICING = {"input": 3.00, "output": 15.00, "cache_read": 0.30, "cache_write": 3.75}


def compute_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> float:
    """Return cost in USD for a single API call."""
    pricing = MODEL_PRICING.get(model, DEFAULT_PRICING)
    m = 1_000_000
    return (
        input_tokens * pricing["input"] / m
        + output_tokens * pricing["output"] / m
        + cache_read_tokens * pricing["cache_read"] / m
        + cache_write_tokens * pricing["cache_write"] / m
    )


# ---------------------------------------------------------------------------
# Core records
# ---------------------------------------------------------------------------


class UsageRecord(BaseModel):
    """One assistant turn extracted from a JSONL file."""

    session_id: str
    request_id: Optional[str] = None
    timestamp: datetime
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    project_path: str = ""
    engineer: str = "unknown"
    cost_usd: float = 0.0


class SessionSummary(BaseModel):
    """Aggregated stats for one Claude Code session."""

    session_id: str
    engineer: str
    project_path: str
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    total_cost_usd: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_read_tokens: int = 0
    total_cache_write_tokens: int = 0
    model_mix: dict[str, float] = Field(default_factory=dict)
    turn_count: int = 0

    @property
    def cache_efficiency(self) -> float:
        total = self.total_input_tokens + self.total_cache_read_tokens
        return self.total_cache_read_tokens / total if total > 0 else 0.0


class EngineerSummary(BaseModel):
    """Rolled-up stats for one engineer across all their sessions."""

    engineer: str
    total_cost_usd: float = 0.0
    session_count: int = 0
    total_turns: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_read_tokens: int = 0
    total_cache_write_tokens: int = 0
    model_mix: dict[str, float] = Field(default_factory=dict)
    project_breakdown: dict[str, float] = Field(default_factory=dict)
    daily_spend: dict[str, float] = Field(default_factory=dict)

    @property
    def cache_efficiency(self) -> float:
        total = self.total_input_tokens + self.total_cache_read_tokens
        return self.total_cache_read_tokens / total if total > 0 else 0.0

    @property
    def avg_cost_per_session(self) -> float:
        return self.total_cost_usd / self.session_count if self.session_count > 0 else 0.0


class ProjectSummary(BaseModel):
    """Rolled-up stats for one project directory."""

    project_path: str
    total_cost_usd: float = 0.0
    session_count: int = 0
    engineer_breakdown: dict[str, float] = Field(default_factory=dict)
    model_mix: dict[str, float] = Field(default_factory=dict)


class TeamReport(BaseModel):
    """Full team-level cost intelligence report."""

    generated_at: datetime = Field(default_factory=datetime.utcnow)
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
    total_cost_usd: float = 0.0
    total_sessions: int = 0
    total_turns: int = 0
    engineer_count: int = 0
    engineers: list[EngineerSummary] = Field(default_factory=list)
    projects: list[ProjectSummary] = Field(default_factory=list)
    model_breakdown: dict[str, float] = Field(default_factory=dict)
    daily_spend: dict[str, float] = Field(default_factory=dict)
    cache_efficiency_pct: float = 0.0
    cost_brief: Optional[str] = None
