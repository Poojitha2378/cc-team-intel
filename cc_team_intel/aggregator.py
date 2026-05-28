"""Aggregate UsageRecords into SessionSummary, EngineerSummary, and TeamReport."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Iterable

from .models import (
    EngineerSummary,
    ProjectSummary,
    SessionSummary,
    TeamReport,
    UsageRecord,
)


def _date_key(ts: datetime) -> str:
    return ts.strftime("%Y-%m-%d")


def build_sessions(records: Iterable[UsageRecord]) -> list[SessionSummary]:
    """Roll up records into per-session summaries."""
    sessions: dict[str, SessionSummary] = {}

    for r in records:
        # Key by (engineer, session_id) so two engineers with the same session UUID don't collide.
        key = (r.engineer, r.session_id)
        if key not in sessions:
            sessions[key] = SessionSummary(
                session_id=r.session_id,
                engineer=r.engineer,
                project_path=r.project_path,
            )
        s = sessions[key]

        if s.start_time is None or r.timestamp < s.start_time:
            s.start_time = r.timestamp
        if s.end_time is None or r.timestamp > s.end_time:
            s.end_time = r.timestamp

        s.total_cost_usd += r.cost_usd
        s.total_input_tokens += r.input_tokens
        s.total_output_tokens += r.output_tokens
        s.total_cache_read_tokens += r.cache_read_tokens
        s.total_cache_write_tokens += r.cache_write_tokens
        s.turn_count += 1
        s.model_mix[r.model] = s.model_mix.get(r.model, 0.0) + r.cost_usd

    return list(sessions.values())


def build_team_report(
    records: Iterable[UsageRecord],
    period_start: datetime | None = None,
    period_end: datetime | None = None,
) -> TeamReport:
    """Build a full TeamReport from raw usage records."""
    record_list = list(records)

    # Filter by period if specified
    if period_start or period_end:
        filtered = []
        for r in record_list:
            ts = r.timestamp
            if period_start and ts < period_start:
                continue
            if period_end and ts > period_end:
                continue
            filtered.append(r)
        record_list = filtered

    sessions = build_sessions(record_list)

    # Engineer aggregation
    eng_map: dict[str, EngineerSummary] = {}
    for s in sessions:
        e = s.engineer
        if e not in eng_map:
            eng_map[e] = EngineerSummary(engineer=e)
        eng = eng_map[e]
        eng.total_cost_usd += s.total_cost_usd
        eng.session_count += 1
        eng.total_turns += s.turn_count
        eng.total_input_tokens += s.total_input_tokens
        eng.total_output_tokens += s.total_output_tokens
        eng.total_cache_read_tokens += s.total_cache_read_tokens
        eng.total_cache_write_tokens += s.total_cache_write_tokens
        for model, cost in s.model_mix.items():
            eng.model_mix[model] = eng.model_mix.get(model, 0.0) + cost
        eng.project_breakdown[s.project_path] = (
            eng.project_breakdown.get(s.project_path, 0.0) + s.total_cost_usd
        )
        if s.start_time:
            dk = _date_key(s.start_time)
            eng.daily_spend[dk] = eng.daily_spend.get(dk, 0.0) + s.total_cost_usd

    # Project aggregation
    proj_map: dict[str, ProjectSummary] = {}
    for s in sessions:
        p = s.project_path
        if p not in proj_map:
            proj_map[p] = ProjectSummary(project_path=p)
        proj = proj_map[p]
        proj.total_cost_usd += s.total_cost_usd
        proj.session_count += 1
        proj.engineer_breakdown[s.engineer] = (
            proj.engineer_breakdown.get(s.engineer, 0.0) + s.total_cost_usd
        )
        for model, cost in s.model_mix.items():
            proj.model_mix[model] = proj.model_mix.get(model, 0.0) + cost

    # Team-level rollup
    total_cost = sum(r.cost_usd for r in record_list)
    total_input = sum(r.input_tokens for r in record_list)
    total_cache_read = sum(r.cache_read_tokens for r in record_list)

    model_breakdown: dict[str, float] = {}
    daily_spend: dict[str, float] = {}
    for r in record_list:
        model_breakdown[r.model] = model_breakdown.get(r.model, 0.0) + r.cost_usd
        dk = _date_key(r.timestamp)
        daily_spend[dk] = daily_spend.get(dk, 0.0) + r.cost_usd

    total_tokens = total_input + total_cache_read
    cache_eff = total_cache_read / total_tokens if total_tokens > 0 else 0.0

    # Determine period bounds from data if not specified
    all_ts = [r.timestamp for r in record_list if r.timestamp]
    p_start = period_start or (min(all_ts) if all_ts else None)
    p_end = period_end or (max(all_ts) if all_ts else None)

    return TeamReport(
        generated_at=datetime.now(tz=timezone.utc),
        period_start=p_start,
        period_end=p_end,
        total_cost_usd=total_cost,
        total_sessions=len(sessions),
        total_turns=sum(s.turn_count for s in sessions),
        engineer_count=len(eng_map),
        engineers=sorted(eng_map.values(), key=lambda e: e.total_cost_usd, reverse=True),
        projects=sorted(proj_map.values(), key=lambda p: p.total_cost_usd, reverse=True),
        model_breakdown=model_breakdown,
        daily_spend=dict(sorted(daily_spend.items())),
        cache_efficiency_pct=cache_eff * 100,
    )
