"""EPIC-20 — Tests for task_grouping_service (LLM cluster+route)."""
import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.prompts.group_tasks import build_group_tasks_user_message
from backend.services.task_grouping_service import run_task_grouping


@pytest.mark.asyncio
@patch("backend.services.task_grouping_service.call_llm_raw", new_callable=AsyncMock)
async def test_groups_match_input_topics_and_tasks(mock_llm):
    mock_llm.return_value = json.dumps([
        {"task_ids": ["t1", "t2"], "target_topic": "ARM"},
        {"task_ids": ["t3"], "target_topic": "Stress Testing"},
    ])
    out = await run_task_grouping(
        ["ARM", "Stress Testing"],
        [
            {"id": "t1", "text": "rebuild ARM models", "origin": "new"},
            {"id": "t2", "text": "validate ARM against Q1", "origin": "previous"},
            {"id": "t3", "text": "stress test results", "origin": "new"},
        ],
        llm="openrouter",
        model="anthropic/claude-sonnet-4-6",
    )
    assert len(out["groups"]) == 2
    assert out["groups"][0]["target_topic"] == "ARM"
    assert out["groups"][0]["task_ids"] == ["t1", "t2"]
    assert out["unassigned"] == []
    assert out["rejected"] == []


@pytest.mark.asyncio
@patch("backend.services.task_grouping_service.call_llm_raw", new_callable=AsyncMock)
async def test_unassigned_tasks_returned_separately(mock_llm):
    mock_llm.return_value = json.dumps([{"task_ids": ["t1"], "target_topic": "ARM"}])
    out = await run_task_grouping(
        ["ARM"],
        [
            {"id": "t1", "text": "x", "origin": "new"},
            {"id": "t2", "text": "y", "origin": "new"},
        ],
        llm="openrouter",
        model="anthropic/claude-sonnet-4-6",
    )
    assert out["unassigned"] == ["t2"]


@pytest.mark.asyncio
@patch("backend.services.task_grouping_service.call_llm_raw", new_callable=AsyncMock)
async def test_unknown_target_topic_rejected(mock_llm):
    mock_llm.return_value = json.dumps([{"task_ids": ["t1"], "target_topic": "Made-Up"}])
    out = await run_task_grouping(
        ["ARM"],
        [{"id": "t1", "text": "x", "origin": "new"}],
        llm="openrouter",
        model="anthropic/claude-sonnet-4-6",
    )
    assert out["groups"] == []
    assert any("Made-Up" in r for r in out["rejected"])
    assert out["unassigned"] == ["t1"]


@pytest.mark.asyncio
@patch("backend.services.task_grouping_service.call_llm_raw", new_callable=AsyncMock)
async def test_duplicate_task_id_kept_in_first_group_only(mock_llm):
    mock_llm.return_value = json.dumps([
        {"task_ids": ["t1", "t2"], "target_topic": "ARM"},
        {"task_ids": ["t2", "t3"], "target_topic": "ARM"},
    ])
    out = await run_task_grouping(
        ["ARM"],
        [
            {"id": "t1", "text": "x", "origin": "new"},
            {"id": "t2", "text": "y", "origin": "new"},
            {"id": "t3", "text": "z", "origin": "new"},
        ],
        llm="openrouter",
        model="anthropic/claude-sonnet-4-6",
    )
    assert out["groups"][0]["task_ids"] == ["t1", "t2"]
    assert out["groups"][1]["task_ids"] == ["t3"]
    assert out["unassigned"] == []


@pytest.mark.asyncio
@patch("backend.services.task_grouping_service.call_llm_raw", new_callable=AsyncMock)
async def test_invalid_json_marks_all_unassigned(mock_llm):
    mock_llm.return_value = "not valid json"
    out = await run_task_grouping(
        ["ARM"],
        [{"id": "t1", "text": "x", "origin": "new"}],
        llm="openrouter",
        model="anthropic/claude-sonnet-4-6",
    )
    assert out["groups"] == []
    assert out["unassigned"] == ["t1"]


@pytest.mark.asyncio
@patch("backend.services.task_grouping_service.call_llm_raw", new_callable=AsyncMock)
async def test_dict_wrapper_unwrapped(mock_llm):
    """Some models wrap in {'groups': [...]} — unwrap defensively."""
    mock_llm.return_value = json.dumps({
        "groups": [{"task_ids": ["t1"], "target_topic": "ARM"}],
    })
    out = await run_task_grouping(
        ["ARM"],
        [{"id": "t1", "text": "x", "origin": "new"}],
        llm="openrouter",
        model="anthropic/claude-sonnet-4-6",
    )
    assert len(out["groups"]) == 1


def test_user_message_includes_topics_and_tasks():
    msg = build_group_tasks_user_message(
        ["ARM", "Stress"],
        [{"id": "t1", "text": "do thing", "origin": "new"}],
    )
    assert "- ARM" in msg
    assert "- Stress" in msg
    assert "[new] id=t1 :: do thing" in msg


def test_empty_tasks_returns_empty():
    import asyncio
    out = asyncio.run(run_task_grouping(["ARM"], [], llm="openrouter", model=None))
    assert out == {"groups": [], "unassigned": [], "rejected": []}


def test_empty_topics_marks_all_unassigned():
    import asyncio
    out = asyncio.run(run_task_grouping([], [{"id": "t1", "text": "x", "origin": "new"}], llm="openrouter", model=None))
    assert out["unassigned"] == ["t1"]
    assert "no topics" in out["rejected"][0]
