"""EPIC-20 — Tests for finalized_topics_service (Stage 1 CRUD).

Diff-based save (2026-05-29): per-row insert/update/delete, no bulk insert.
The bulk delete-then-insert pattern was replaced because it cascade-wiped
all task_match_groups for the call on every save.
"""
from unittest.mock import MagicMock

from backend.services.finalized_topics_service import (
    FinalizedTopic,
    load_finalized_topics,
    save_finalized_topics,
)


def _fake_db_with_existing(existing_rows: list[dict]):
    """Build a MagicMock db whose select() returns the given existing rows."""
    db = MagicMock()
    # The path used inside save_finalized_topics:
    #   client.table("call_finalized_topics").select(...).eq(...).execute().data
    db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = existing_rows
    return db


def test_save_inserts_new_rows_when_no_existing():
    db = _fake_db_with_existing([])
    topics: list[FinalizedTopic] = [
        {"name": "ARM", "source": "existing", "topic_id": "uuid-1"},
        {"name": "Stress Testing", "source": "new", "topic_id": None, "v5_cluster_id": "c1"},
    ]
    result = save_finalized_topics("call-uuid", topics, db=db)
    assert result["saved"] == 2
    assert result["inserted"] == 2
    assert result["updated"] == 0
    assert result["deleted_with_cascade"] == 0
    # Collect every insert call's payload (one per topic in diff-save).
    insert_calls = db.table.return_value.insert.call_args_list
    inserted_names = [c.args[0]["name"] for c in insert_calls]
    inserted_positions = [c.args[0]["position"] for c in insert_calls]
    assert "ARM" in inserted_names
    assert "Stress Testing" in inserted_names
    assert 0 in inserted_positions and 1 in inserted_positions


def test_save_full_clear_triggers_bulk_delete():
    """Empty payload is the only path that still does the cascade-heavy delete.
    User explicitly removed every topic — the cascade is acceptable here."""
    db = _fake_db_with_existing([{"id": "x", "name": "old", "source": "existing", "topic_id": None, "v5_cluster_id": None, "position": 0}])
    result = save_finalized_topics("call-uuid", [], db=db)
    assert result["saved"] == 0
    assert result["deleted_with_cascade"] == 1
    db.table.return_value.insert.assert_not_called()
    # Bulk delete-by-call_id was issued.
    db.table.return_value.delete.return_value.eq.assert_called_with("call_id", "call-uuid")


def test_save_preserves_unchanged_rows():
    """Re-saving the same list with no changes must update existing rows by id,
    NOT delete-then-reinsert (which would cascade-wipe task_match_groups)."""
    existing = [
        {"id": "row-a", "name": "ARM", "source": "existing", "topic_id": "u1", "v5_cluster_id": None, "position": 0},
        {"id": "row-b", "name": "Stress", "source": "new", "topic_id": None, "v5_cluster_id": "c1", "position": 1},
    ]
    db = _fake_db_with_existing(existing)
    topics: list[FinalizedTopic] = [
        {"name": "ARM", "source": "existing", "topic_id": "u1"},
        {"name": "Stress", "source": "new", "topic_id": None, "v5_cluster_id": "c1"},
    ]
    result = save_finalized_topics("call-uuid", topics, db=db)
    assert result["inserted"] == 0
    assert result["updated"] == 2
    assert result["deleted_with_cascade"] == 0
    # No per-row delete was issued (id-targeted delete chain unused).
    db.table.return_value.insert.assert_not_called()


def test_save_rename_via_original_name_updates_existing_row():
    """A rename (_original_name present) must UPDATE the existing row in place,
    not delete it — otherwise the cascade wipes the renamed topic's task groups."""
    existing = [
        {"id": "row-a", "name": "ARM", "source": "existing", "topic_id": "u1", "v5_cluster_id": None, "position": 0},
    ]
    db = _fake_db_with_existing(existing)
    topics: list[FinalizedTopic] = [
        {"name": "ARM Composite", "source": "existing", "topic_id": "u1", "_original_name": "ARM"},
    ]
    result = save_finalized_topics("call-uuid", topics, db=db)
    assert result["inserted"] == 0
    assert result["updated"] == 1
    assert result["deleted_with_cascade"] == 0


def test_save_removes_only_topics_not_in_payload():
    """Removing one of two topics must delete ONLY that row (cascade fires only
    for the removed topic's task_match_groups), not all rows for the call."""
    existing = [
        {"id": "row-a", "name": "ARM", "source": "existing", "topic_id": "u1", "v5_cluster_id": None, "position": 0},
        {"id": "row-b", "name": "Stress", "source": "new", "topic_id": None, "v5_cluster_id": "c1", "position": 1},
    ]
    db = _fake_db_with_existing(existing)
    topics: list[FinalizedTopic] = [
        {"name": "ARM", "source": "existing", "topic_id": "u1"},  # only ARM kept
    ]
    result = save_finalized_topics("call-uuid", topics, db=db)
    assert result["updated"] == 1
    assert result["deleted_with_cascade"] == 1
    assert result["inserted"] == 0


def test_load_returns_ordered_list():
    db = MagicMock()
    db.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value.data = [
        {"id": "a", "name": "ARM", "source": "existing", "topic_id": "u1", "v5_cluster_id": None, "position": 0},
        {"id": "b", "name": "New Topic", "source": "new", "topic_id": None, "v5_cluster_id": "c1", "position": 1},
    ]
    out = load_finalized_topics("call-uuid", db=db)
    assert len(out) == 2
    assert out[0]["name"] == "ARM"
    assert out[0]["source"] == "existing"
    assert out[1]["v5_cluster_id"] == "c1"


def test_load_empty_when_no_rows():
    db = MagicMock()
    db.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value.data = None
    out = load_finalized_topics("call-uuid", db=db)
    assert out == []
