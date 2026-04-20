from unittest.mock import MagicMock

from backend.services.topic_lineage import get_topic_lineage


def _make_db(topics_by_id: dict, sources_by_parent: dict | None = None):
    """Build a MagicMock DB whose topics table responds to .eq('id', ...) and
    .eq('merged_into_topic_id', ...) based on the provided fixtures.
    """
    sources_by_parent = sources_by_parent or {}
    db = MagicMock()

    def table_side(name):
        table = MagicMock()
        if name != "topics":
            return table
        select = MagicMock()
        table.select.return_value = select

        def eq_side(col, val):
            result = MagicMock()
            if col == "id":
                result.execute.return_value.data = (
                    [topics_by_id[val]] if val in topics_by_id else []
                )
            elif col == "merged_into_topic_id":
                result.execute.return_value.data = sources_by_parent.get(val, [])
            else:
                result.execute.return_value.data = []
            return result

        select.eq.side_effect = eq_side
        return table

    db.table.side_effect = table_side
    return db


def test_lineage_no_merges_returns_self_only():
    db = _make_db(
        topics_by_id={
            "t1": {"id": "t1", "name": "API design", "archived": False,
                   "merged_into_topic_id": None},
        },
        sources_by_parent={},  # no topics point to t1 via merged_into_topic_id
    )

    result = get_topic_lineage("t1", db)

    assert result == [
        {"id": "t1", "name": "API design", "archived": False,
         "merged_into_topic_id": None}
    ]
