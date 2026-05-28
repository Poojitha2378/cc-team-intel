"""Tests for the aggregation layer."""

from pathlib import Path

from cc_team_intel.parser import iter_records_from_jsonl
from cc_team_intel.aggregator import build_team_report, build_sessions

FIXTURE = Path(__file__).parent / "fixtures" / "sample.jsonl"


def _records(engineer="alice"):
    return list(iter_records_from_jsonl(FIXTURE, engineer=engineer, project_path="myproject"))


def test_build_sessions_groups_correctly():
    sessions = build_sessions(_records())
    # sample.jsonl has 2 unique session IDs
    assert len(sessions) == 2


def test_build_sessions_sums_cost():
    sessions = build_sessions(_records())
    total = sum(s.total_cost_usd for s in sessions)
    assert total > 0


def test_build_sessions_turn_count():
    sessions = build_sessions(_records())
    total_turns = sum(s.turn_count for s in sessions)
    assert total_turns == 3  # 3 assistant records


def test_team_report_totals():
    report = build_team_report(_records())
    assert report.total_sessions == 2
    assert report.total_turns == 3
    assert report.engineer_count == 1
    assert report.total_cost_usd > 0


def test_team_report_engineer_breakdown():
    report = build_team_report(_records())
    assert len(report.engineers) == 1
    assert report.engineers[0].engineer == "alice"


def test_team_report_model_breakdown():
    report = build_team_report(_records())
    assert "claude-sonnet-4-6" in report.model_breakdown
    assert "claude-opus-4-7" in report.model_breakdown


def test_team_report_multi_engineer():
    alice = list(iter_records_from_jsonl(FIXTURE, engineer="alice", project_path="proj-a"))
    bob = list(iter_records_from_jsonl(FIXTURE, engineer="bob", project_path="proj-b"))
    report = build_team_report(alice + bob)
    assert report.engineer_count == 2
    engineers = {e.engineer for e in report.engineers}
    assert engineers == {"alice", "bob"}


def test_cache_efficiency():
    report = build_team_report(_records())
    # cache_read_tokens > 0 in fixtures, so efficiency > 0
    assert report.cache_efficiency_pct > 0


def test_period_filter():
    from datetime import datetime, timezone
    report = build_team_report(
        _records(),
        period_start=datetime(2025, 5, 2, tzinfo=timezone.utc),
        period_end=datetime(2025, 5, 2, 23, 59, tzinfo=timezone.utc),
    )
    # Only sess_002 falls on May 2
    assert report.total_sessions == 1
