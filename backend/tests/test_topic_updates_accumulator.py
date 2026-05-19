"""Tests for topic_updates_accumulator.accumulate_into_project_state (Story 15.7)."""

import asyncio
import pytest

from backend.services import topic_updates_accumulator


def _make_fake_db_with_touched(touched):
    """A db whose table("topic_updates").select(...).eq("call_id", X).execute() returns `touched`."""
    class _Tbl:
        def __init__(self, name): self.name = name
        def select(self, _cols): return self
        def eq(self, _k, _v): return self
        def execute(self):
            return type("R", (), {"data": touched if self.name == "topic_updates" else []})()

    class _DB:
        def table(self, n): return _Tbl(n)
    return _DB()


@pytest.mark.asyncio
async def test_accumulator_respects_concurrency_bound(monkeypatch):
    """Even with 30 touched topics, no more than 8 LLM calls run concurrently."""
    concurrent = 0
    max_seen = 0

    async def fake_gen(_topic_id, _call_id, _db):
        nonlocal concurrent, max_seen
        concurrent += 1
        max_seen = max(max_seen, concurrent)
        await asyncio.sleep(0.01)
        concurrent -= 1
        return ("ok", "verified")

    monkeypatch.setattr(
        topic_updates_accumulator, "generate_chronology_cell", fake_gen
    )

    touched = [{"id": f"row-{i}", "topic_id": f"topic-{i}", "call_id": "c"} for i in range(30)]
    db = _make_fake_db_with_touched(touched)

    result = await topic_updates_accumulator.accumulate_into_project_state("c", db)
    assert max_seen <= 8, f"Concurrency exceeded bound: peak={max_seen}"
    assert result["topics_touched"] == 30


@pytest.mark.asyncio
async def test_accumulator_runs_chronology_for_every_touched_topic(monkeypatch):
    """Every touched topic gets exactly one chronology call."""
    calls_made = []

    async def fake_gen(topic_id, call_id, _db):
        calls_made.append((topic_id, call_id))
        return ("n", "verified")

    monkeypatch.setattr(
        topic_updates_accumulator, "generate_chronology_cell", fake_gen
    )

    touched = [
        {"id": "r1", "topic_id": "T1", "call_id": "c"},
        {"id": "r2", "topic_id": "T2", "call_id": "c"},
        {"id": "r3", "topic_id": "T3", "call_id": "c"},
    ]
    db = _make_fake_db_with_touched(touched)

    await topic_updates_accumulator.accumulate_into_project_state("c", db)
    assert sorted(calls_made) == [("T1", "c"), ("T2", "c"), ("T3", "c")]


@pytest.mark.asyncio
async def test_accumulator_returns_zero_when_no_touched_topics():
    """Empty topic_updates → returns 0, no LLM calls."""
    db = _make_fake_db_with_touched([])
    result = await topic_updates_accumulator.accumulate_into_project_state("c", db)
    assert result["topics_touched"] == 0
    assert result["wall_clock_ms"] >= 0


@pytest.mark.asyncio
async def test_accumulator_catches_per_topic_chronology_failure(monkeypatch):
    """If chronology_service raises (despite its own try/except), accumulator catches and moves on."""
    async def fake_gen_raises(topic_id, _call_id, _db):
        if topic_id == "T2":
            raise RuntimeError("simulated bug")
        return ("ok", "verified")

    monkeypatch.setattr(
        topic_updates_accumulator, "generate_chronology_cell", fake_gen_raises
    )

    touched = [
        {"id": "r1", "topic_id": "T1", "call_id": "c"},
        {"id": "r2", "topic_id": "T2", "call_id": "c"},
        {"id": "r3", "topic_id": "T3", "call_id": "c"},
    ]
    db = _make_fake_db_with_touched(touched)

    # Should NOT raise; should complete all 3 topics
    result = await topic_updates_accumulator.accumulate_into_project_state("c", db)
    assert result["topics_touched"] == 3
