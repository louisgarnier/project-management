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


def test_lineage_single_mn_merge_returns_sources():
    """Merged topic C with sources A and B → lineage = [C, A, B]."""
    db = _make_db(
        topics_by_id={
            "c":  {"id": "c",  "name": "API strategy",  "archived": False,
                   "merged_into_topic_id": None},
            "a":  {"id": "a",  "name": "REST API",      "archived": True,
                   "merged_into_topic_id": "c"},
            "b":  {"id": "b",  "name": "GraphQL API",   "archived": True,
                   "merged_into_topic_id": "c"},
        },
        sources_by_parent={
            "c": [
                {"id": "a", "name": "REST API",    "archived": True, "merged_into_topic_id": "c"},
                {"id": "b", "name": "GraphQL API", "archived": True, "merged_into_topic_id": "c"},
            ],
        },
    )

    result = get_topic_lineage("c", db)
    ids = [r["id"] for r in result]
    assert ids == ["c", "a", "b"]


def test_lineage_chain_of_merges_returns_full_chain():
    """Merge chain: a + b → ab (Call 2), then ab + c → abc (Call 3).
    get_topic_lineage(abc) = [abc, ab, c, a, b].
    """
    db = _make_db(
        topics_by_id={
            "abc": {"id": "abc", "name": "API+CLI",    "archived": False,
                    "merged_into_topic_id": None},
            "ab":  {"id": "ab",  "name": "API merged", "archived": True,
                    "merged_into_topic_id": "abc"},
            "c":   {"id": "c",   "name": "CLI",        "archived": True,
                    "merged_into_topic_id": "abc"},
            "a":   {"id": "a",   "name": "REST",       "archived": True,
                    "merged_into_topic_id": "ab"},
            "b":   {"id": "b",   "name": "GraphQL",    "archived": True,
                    "merged_into_topic_id": "ab"},
        },
        sources_by_parent={
            "abc": [
                {"id": "ab", "name": "API merged", "archived": True,  "merged_into_topic_id": "abc"},
                {"id": "c",  "name": "CLI",        "archived": True,  "merged_into_topic_id": "abc"},
            ],
            "ab": [
                {"id": "a", "name": "REST",    "archived": True, "merged_into_topic_id": "ab"},
                {"id": "b", "name": "GraphQL", "archived": True, "merged_into_topic_id": "ab"},
            ],
            "c": [],
        },
    )

    result = get_topic_lineage("abc", db)
    ids = [r["id"] for r in result]
    # BFS order: self, then children of self, then grandchildren
    assert ids == ["abc", "ab", "c", "a", "b"]


def test_lineage_cycle_guard_terminates():
    """If data is somehow cyclic (a → b, b → a), the walker must terminate.

    Real migrations forbid this by construction, but the guard is a defensive
    invariant.
    """
    db = _make_db(
        topics_by_id={
            "a": {"id": "a", "name": "A", "archived": False, "merged_into_topic_id": "b"},
            "b": {"id": "b", "name": "B", "archived": False, "merged_into_topic_id": "a"},
        },
        sources_by_parent={
            "a": [{"id": "b", "name": "B", "archived": False, "merged_into_topic_id": "a"}],
            "b": [{"id": "a", "name": "A", "archived": False, "merged_into_topic_id": "b"}],
        },
    )

    # Must terminate — not raise, not infinite-loop
    result = get_topic_lineage("a", db)
    ids = {r["id"] for r in result}
    assert ids == {"a", "b"}
