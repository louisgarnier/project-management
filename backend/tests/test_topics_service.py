"""Tests for topics_service — new EPIC-15 schema + validator."""

import uuid

import pytest

from backend.services import topics_service


# ── _TOPIC_SCHEMA shape ─────────────────────────────────────────────────────

def test_topic_schema_describes_new_fields():
    """_TOPIC_SCHEMA must enumerate the v2 fields and OMIT the legacy ones."""
    schema = topics_service._TOPIC_SCHEMA
    for required in ("name", "importance", "key_terms", "evidence", "tasks"):
        assert required in schema, f"new field missing from schema string: {required}"
    for legacy in ("decisions", "follow_up_items", "open_questions", "rationale", "is_parked"):
        assert legacy not in schema, f"legacy field still in schema string: {legacy}"


# ── _validate_topic accepts a valid topic ──────────────────────────────────

def _valid_topic() -> dict:
    return {
        "name": "MC Mac memory issue",
        "importance": "high",
        "key_terms": ["MC Mac", "memory failure", "SO7 PA"],
        "evidence": [
            {
                "speaker": "Hassan",
                "quote": "the MC Mac is still failing on memory for the SO7 PA",
                "citation": "transcript 2026-04-13 · lines 145-148",
            }
        ],
        "tasks": [
            {
                "task": "investigate memory failure",
                "next_step": "Test boost flag + FVMAC on Mark's PA",
                "status": "open",
                "owner": "Nick",
            }
        ],
    }


def test_validate_topic_accepts_valid():
    ok, reason = topics_service._validate_topic(_valid_topic())
    assert ok, reason


# ── _validate_topic rejects empties ────────────────────────────────────────

def test_validate_topic_rejects_missing_evidence():
    t = _valid_topic()
    t["evidence"] = []
    ok, reason = topics_service._validate_topic(t)
    assert not ok
    assert "evidence" in reason


def test_validate_topic_rejects_missing_tasks():
    t = _valid_topic()
    t["tasks"] = []
    ok, reason = topics_service._validate_topic(t)
    assert not ok
    assert "tasks" in reason


def test_validate_topic_rejects_missing_key_terms():
    t = _valid_topic()
    t["key_terms"] = []
    ok, reason = topics_service._validate_topic(t)
    assert not ok
    assert "key_terms" in reason


def test_validate_topic_rejects_bad_importance():
    t = _valid_topic()
    t["importance"] = "urgent"
    ok, reason = topics_service._validate_topic(t)
    assert not ok
    assert "importance" in reason


def test_validate_topic_rejects_task_missing_next_step():
    t = _valid_topic()
    t["tasks"][0]["next_step"] = ""
    ok, reason = topics_service._validate_topic(t)
    assert not ok
    assert "next_step" in reason or "task" in reason


# ── _stamp_task_ids assigns a UUID to each task ───────────────────────────

def test_stamp_task_ids_adds_uuid():
    t = _valid_topic()
    stamped = topics_service._stamp_task_ids(t)
    for task in stamped["tasks"]:
        assert "task_id" in task
        uuid.UUID(task["task_id"])  # raises ValueError if not a UUID


def test_stamp_task_ids_preserves_existing_ids():
    t = _valid_topic()
    existing = str(uuid.uuid4())
    t["tasks"][0]["task_id"] = existing
    stamped = topics_service._stamp_task_ids(t)
    assert stamped["tasks"][0]["task_id"] == existing


# ── _status_rollup derives topic-level status from tasks ──────────────────

def test_status_rollup_all_resolved():
    tasks = [{"status": "resolved"}, {"status": "resolved"}]
    assert topics_service._status_rollup(tasks) == "resolved"


def test_status_rollup_any_open():
    tasks = [{"status": "open"}, {"status": "resolved"}]
    assert topics_service._status_rollup(tasks) == "open"


def test_status_rollup_any_in_progress_no_open():
    tasks = [{"status": "in_progress"}, {"status": "resolved"}]
    assert topics_service._status_rollup(tasks) == "in_progress"


def test_status_rollup_empty():
    assert topics_service._status_rollup([]) == "open"  # safety default
