"""Tests for the JSONL parser."""

from pathlib import Path

import pytest

from cc_team_intel.parser import iter_records_from_jsonl
from cc_team_intel.models import compute_cost

FIXTURE = Path(__file__).parent / "fixtures" / "sample.jsonl"


def test_parser_yields_only_assistant_records():
    records = list(iter_records_from_jsonl(FIXTURE, engineer="alice"))
    assert len(records) == 3  # 3 assistant records, 1 user record skipped


def test_parser_sets_engineer():
    records = list(iter_records_from_jsonl(FIXTURE, engineer="alice"))
    assert all(r.engineer == "alice" for r in records)


def test_parser_extracts_tokens():
    records = list(iter_records_from_jsonl(FIXTURE, engineer="alice"))
    first = records[0]
    assert first.input_tokens == 1000
    assert first.output_tokens == 500
    assert first.cache_write_tokens == 200
    assert first.cache_read_tokens == 300


def test_parser_computes_nonzero_cost():
    records = list(iter_records_from_jsonl(FIXTURE, engineer="alice"))
    assert all(r.cost_usd > 0 for r in records)


def test_parser_model_field():
    records = list(iter_records_from_jsonl(FIXTURE, engineer="alice"))
    models = {r.model for r in records}
    assert "claude-sonnet-4-6" in models
    assert "claude-opus-4-7" in models


def test_compute_cost_sonnet():
    cost = compute_cost("claude-sonnet-4-6", 1_000_000, 0)
    assert abs(cost - 3.0) < 0.001


def test_compute_cost_cache_read():
    cost = compute_cost("claude-sonnet-4-6", 0, 0, cache_read_tokens=1_000_000)
    assert abs(cost - 0.30) < 0.001


def test_compute_cost_unknown_model_uses_default():
    cost = compute_cost("claude-unknown-99", 1_000_000, 0)
    assert cost > 0
