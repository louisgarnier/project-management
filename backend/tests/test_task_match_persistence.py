"""EPIC-19 — Tests for task-level match group persistence."""
from unittest.mock import MagicMock
from backend.services.task_match_persistence import (
    save_task_match_groups, load_task_match_groups, TaskMatchGroup,
)


def _fake_db():
    db = MagicMock()
    return db


def test_save_task_match_groups_persists_n_to_m_binding():
    db = _fake_db()
    groups = [
        TaskMatchGroup(
            kind="binding",
            call_task_refs=[{"call_topic_name": "ARM", "task_id": "t1"}, {"call_topic_name": "ARM", "task_id": "t2"}],
            project_task_refs=[{"project_topic_id": "p-arm", "task_id": "pt1"}],
        )
    ]
    result = save_task_match_groups(call_id="c-1", groups=groups, db=db)
    assert result["saved"] == 1
    db.table.assert_any_call("topic_match_groups")
    insert_call = db.table.return_value.insert.call_args
    inserted = insert_call.args[0]
    assert inserted["kind"] == "binding"
    assert len(inserted["call_task_refs"]) == 2
    assert len(inserted["project_task_refs"]) == 1


def test_save_task_match_groups_deletes_previous_groups_first():
    db = _fake_db()
    save_task_match_groups(call_id="c-1", groups=[], db=db)
    db.table.return_value.delete.return_value.eq.assert_called_with("call_id", "c-1")


def test_save_task_match_groups_topic_merge_kind():
    db = _fake_db()
    groups = [
        TaskMatchGroup(
            kind="topic_merge",
            call_task_refs=[],
            project_task_refs=[{"project_topic_id": "p-a"}, {"project_topic_id": "p-b"}],
        )
    ]
    save_task_match_groups(call_id="c-1", groups=groups, db=db)
    inserted = db.table.return_value.insert.call_args.args[0]
    assert inserted["kind"] == "topic_merge"


def test_save_task_match_groups_persists_target_topic_name():
    db = _fake_db()
    groups = [
        TaskMatchGroup(
            kind="binding",
            call_task_refs=[{"call_topic_name": "X", "task_id": "t1"}],
            project_task_refs=[{"project_topic_id": "p1", "task_id": "pt1"}],
            target_topic_name="Brand New Topic",
        )
    ]
    save_task_match_groups("c-1", groups, db=db)
    inserted = db.table.return_value.insert.call_args.args[0]
    assert inserted["target_topic_name"] == "Brand New Topic"


def test_save_task_match_groups_target_topic_name_none_when_not_set():
    db = _fake_db()
    groups = [
        TaskMatchGroup(
            kind="binding",
            call_task_refs=[{"call_topic_name": "Y", "task_id": "t2"}],
            project_task_refs=[{"project_topic_id": "p2", "task_id": "pt2"}],
        )
    ]
    save_task_match_groups("c-1", groups, db=db)
    inserted = db.table.return_value.insert.call_args.args[0]
    assert inserted["target_topic_name"] is None
