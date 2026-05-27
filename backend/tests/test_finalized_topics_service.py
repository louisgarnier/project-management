"""EPIC-20 — Tests for finalized_topics_service (Stage 1 CRUD)."""
from unittest.mock import MagicMock

from backend.services.finalized_topics_service import (
    FinalizedTopic,
    load_finalized_topics,
    save_finalized_topics,
)


def _fake_db():
    return MagicMock()


def test_save_inserts_rows_with_position():
    db = _fake_db()
    topics: list[FinalizedTopic] = [
        {"name": "ARM", "source": "existing", "topic_id": "uuid-1"},
        {"name": "Stress Testing", "source": "new", "topic_id": None, "v5_cluster_id": "c1"},
    ]
    result = save_finalized_topics("call-uuid", topics, db=db)
    assert result["saved"] == 2
    inserted_rows = db.table.return_value.insert.call_args.args[0]
    assert inserted_rows[0]["name"] == "ARM"
    assert inserted_rows[0]["position"] == 0
    assert inserted_rows[1]["name"] == "Stress Testing"
    assert inserted_rows[1]["position"] == 1
    assert inserted_rows[1]["source"] == "new"


def test_save_deletes_previous_entries_first():
    db = _fake_db()
    save_finalized_topics("call-uuid", [], db=db)
    db.table.return_value.delete.return_value.eq.assert_called_with("call_id", "call-uuid")
    # Empty list → no insert call
    db.table.return_value.insert.assert_not_called()


def test_load_returns_ordered_list():
    db = _fake_db()
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
    db = _fake_db()
    db.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value.data = None
    out = load_finalized_topics("call-uuid", db=db)
    assert out == []
