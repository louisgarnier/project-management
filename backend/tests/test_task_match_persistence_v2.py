"""EPIC-20 — Tests for the new finalized_topic_id + group_kind columns
on task_match_persistence.

Complements test_task_match_persistence.py (EPIC-19 tests). The legacy
columns + kind='binding'/'topic_merge' continue to work — verified there.
"""
from unittest.mock import MagicMock

from backend.services.task_match_persistence import (
    TaskMatchGroup,
    _infer_group_kind,
    save_task_match_groups,
    load_task_match_groups,
)


def _fake_db():
    return MagicMock()


def test_save_persists_finalized_topic_id_and_group_kind():
    """EPIC-20: each group has exactly one finalized_topic_id + a group_kind."""
    db = _fake_db()
    groups: list[TaskMatchGroup] = [
        TaskMatchGroup(
            finalized_topic_id="ft-1",
            group_kind="new_only",
            call_task_refs=[{"task_id": "t1"}],
            project_task_refs=[],
        ),
        TaskMatchGroup(
            finalized_topic_id="ft-2",
            group_kind="mixed",
            call_task_refs=[{"task_id": "t2"}],
            project_task_refs=[{"project_topic_id": "p1", "task_id": "pt1"}],
        ),
    ]
    save_task_match_groups("c1", groups, db=db)
    # The last insert call captures the second group
    last_insert = db.table.return_value.insert.call_args.args[0]
    assert last_insert["finalized_topic_id"] == "ft-2"
    assert last_insert["group_kind"] == "mixed"


def test_save_infers_group_kind_when_not_provided():
    """If caller doesn't set group_kind, derive from refs."""
    db = _fake_db()
    groups: list[TaskMatchGroup] = [
        TaskMatchGroup(
            finalized_topic_id="ft-1",
            call_task_refs=[{"task_id": "t1"}],
            project_task_refs=[],
        ),
    ]
    save_task_match_groups("c1", groups, db=db)
    inserted = db.table.return_value.insert.call_args.args[0]
    assert inserted["group_kind"] == "new_only"


def test_infer_kind_old_only():
    g: TaskMatchGroup = TaskMatchGroup(
        call_task_refs=[],
        project_task_refs=[{"project_topic_id": "p1", "task_id": "pt1"}],
    )
    assert _infer_group_kind(g) == "old_only"


def test_infer_kind_new_only():
    g: TaskMatchGroup = TaskMatchGroup(
        call_task_refs=[{"task_id": "t1"}],
        project_task_refs=[],
    )
    assert _infer_group_kind(g) == "new_only"


def test_infer_kind_mixed():
    g: TaskMatchGroup = TaskMatchGroup(
        call_task_refs=[{"task_id": "t1"}],
        project_task_refs=[{"project_topic_id": "p1", "task_id": "pt1"}],
    )
    assert _infer_group_kind(g) == "mixed"


def test_load_returns_epic20_columns():
    db = _fake_db()
    db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {
            "id": "g1",
            "kind": "binding",
            "call_task_refs": [{"task_id": "t1"}],
            "project_task_refs": [],
            "target_topic_name": None,
            "finalized_topic_id": "ft-1",
            "group_kind": "new_only",
        }
    ]
    out = load_task_match_groups("c1", db=db)
    assert len(out) == 1
    assert out[0]["finalized_topic_id"] == "ft-1"
    assert out[0]["group_kind"] == "new_only"
