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


from backend.services.topic_lineage import get_lineage_topic_updates


def _make_db_with_updates(topics_by_id, sources_by_parent, updates_by_topic_id, calls_by_id):
    """Extend the topics-only mock to also respond to topic_updates and calls queries."""
    db = _make_db(topics_by_id, sources_by_parent)

    original_side = db.table.side_effect

    def table_side(name):
        if name == "topic_updates":
            t = MagicMock()
            select = MagicMock()
            t.select.return_value = select

            def in_side(col, values):
                assert col == "topic_id"
                result = MagicMock()
                order = MagicMock()
                result.order.return_value = order
                rows = []
                for tid in values:
                    rows.extend(updates_by_topic_id.get(tid, []))
                rows = sorted(rows, key=lambda r: r["created_at"])
                order.execute.return_value.data = rows
                return result

            select.in_.side_effect = in_side
            return t

        if name == "calls":
            t = MagicMock()
            select = MagicMock()
            t.select.return_value = select

            def eq_side(col, val):
                assert col == "id"
                result = MagicMock()
                result.execute.return_value.data = (
                    [calls_by_id[val]] if val in calls_by_id else []
                )
                return result

            select.eq.side_effect = eq_side
            return t

        return original_side(name)

    db.table.side_effect = table_side
    return db


def test_lineage_updates_ordered_chronologically_and_enriched():
    """Updates from ancestor topic_a and merged topic_c should come back in
    call-time order, each row tagged with source_topic_id/name and call_title.
    """
    db = _make_db_with_updates(
        topics_by_id={
            "c": {"id": "c", "name": "API strategy", "archived": False,
                  "merged_into_topic_id": None},
            "a": {"id": "a", "name": "REST API",     "archived": True,
                  "merged_into_topic_id": "c"},
        },
        sources_by_parent={
            "c": [{"id": "a", "name": "REST API", "archived": True,
                   "merged_into_topic_id": "c"}],
        },
        updates_by_topic_id={
            "a": [
                {"topic_id": "a", "call_id": "call-1", "summary": "REST raised",
                 "transcript_excerpt": "we picked REST", "follow_up_items": [],
                 "decisions": [], "created_at": "2026-04-01T10:00:00Z"},
            ],
            "c": [
                {"topic_id": "c", "call_id": "call-2", "summary": "merged",
                 "transcript_excerpt": "merged API discussion", "follow_up_items": [],
                 "decisions": [], "created_at": "2026-04-08T10:00:00Z"},
                {"topic_id": "c", "call_id": "call-3", "summary": "confirmed REST",
                 "transcript_excerpt": "final REST decision", "follow_up_items": [],
                 "decisions": [], "created_at": "2026-04-15T10:00:00Z"},
            ],
        },
        calls_by_id={
            "call-1": {"id": "call-1", "title": "Kickoff"},
            "call-2": {"id": "call-2", "title": "Review"},
            "call-3": {"id": "call-3", "title": "Decision"},
        },
    )

    result = get_lineage_topic_updates("c", db)

    assert [r["call_title"] for r in result] == ["Kickoff", "Review", "Decision"]
    assert [r["source_topic_id"] for r in result] == ["a", "c", "c"]
    assert [r["source_topic_name"] for r in result] == ["REST API", "API strategy", "API strategy"]
    # Original fields preserved
    assert result[0]["transcript_excerpt"] == "we picked REST"


from backend.services.topic_lineage import build_lineage_evidence_block


def test_evidence_block_includes_ancestor_provenance_line():
    """When evidence comes from an archived ancestor, the block includes a
    'from archived topic: {name}' provenance line so the LLM understands where
    the excerpt came from.
    """
    db = _make_db_with_updates(
        topics_by_id={
            "c": {"id": "c", "name": "API strategy", "archived": False,
                  "merged_into_topic_id": None},
            "a": {"id": "a", "name": "REST API",     "archived": True,
                  "merged_into_topic_id": "c"},
        },
        sources_by_parent={
            "c": [{"id": "a", "name": "REST API", "archived": True,
                   "merged_into_topic_id": "c"}],
        },
        updates_by_topic_id={
            "a": [{"topic_id": "a", "call_id": "call-1", "summary": "REST raised",
                   "transcript_excerpt": "we picked REST", "follow_up_items": ["spike"],
                   "decisions": [], "created_at": "2026-04-01T10:00:00Z"}],
            "c": [{"topic_id": "c", "call_id": "call-2", "summary": "Merged API",
                   "transcript_excerpt": "consolidating endpoints", "follow_up_items": [],
                   "decisions": ["go REST"], "created_at": "2026-04-08T10:00:00Z"}],
        },
        calls_by_id={
            "call-1": {"id": "call-1", "title": "Kickoff"},
            "call-2": {"id": "call-2", "title": "Review"},
        },
    )

    block = build_lineage_evidence_block("API strategy", "c", db)

    # Header present
    assert 'API strategy' in block
    # Call 1 section — from ancestor → provenance line present
    assert 'Kickoff' in block
    assert 'from archived topic: REST API' in block
    assert 'we picked REST' in block
    assert 'spike' in block  # follow-up preserved
    # Call 2 section — from current topic → NO provenance line
    assert 'Review' in block
    assert 'consolidating endpoints' in block
    assert 'go REST' in block
    # Provenance only attached to ancestor row, not to self row
    review_idx = block.index('Review')
    post_review = block[review_idx:]
    assert 'from archived topic' not in post_review


def test_evidence_block_returns_fallback_when_no_history():
    """Topic exists but no topic_updates rows → clean fallback line."""
    db = _make_db_with_updates(
        topics_by_id={"x": {"id": "x", "name": "New topic", "archived": False,
                            "merged_into_topic_id": None}},
        sources_by_parent={},
        updates_by_topic_id={},
        calls_by_id={},
    )

    block = build_lineage_evidence_block("New topic", "x", db)
    assert block == '== Topic: "New topic" ==\n(No historical excerpts available)\n'


from backend.services.topic_lineage import get_lineage_match_groups


def _make_db_with_match_groups(topics_by_id, sources_by_parent,
                                groups_by_call, calls_by_id):
    """Mock DB that serves topic_match_groups as well as topics + calls."""
    db = _make_db(topics_by_id, sources_by_parent)
    original_side = db.table.side_effect

    def table_side(name):
        if name == "topic_match_groups":
            t = MagicMock()
            select = MagicMock()
            t.select.return_value = select
            # All groups returned; filtering is done in the helper
            all_groups = [g for groups in groups_by_call.values() for g in groups]
            select.execute.return_value.data = all_groups
            return t
        if name == "calls":
            t = MagicMock()
            select = MagicMock()
            t.select.return_value = select

            def eq_side(col, val):
                result = MagicMock()
                result.execute.return_value.data = (
                    [calls_by_id[val]] if val in calls_by_id else []
                )
                return result

            select.eq.side_effect = eq_side
            return t
        return original_side(name)

    db.table.side_effect = table_side
    return db


def test_lineage_match_groups_returns_groups_touching_any_ancestor():
    """A match group in Call 2 that references archived source 'a' must be
    returned when querying lineage of the merged topic 'c'.
    """
    db = _make_db_with_match_groups(
        topics_by_id={
            "c": {"id": "c", "name": "API", "archived": False,
                  "merged_into_topic_id": None},
            "a": {"id": "a", "name": "REST", "archived": True,
                  "merged_into_topic_id": "c"},
        },
        sources_by_parent={
            "c": [{"id": "a", "name": "REST", "archived": True,
                   "merged_into_topic_id": "c"}],
        },
        groups_by_call={
            "call-1": [{"call_id": "call-1", "project_topic_ids": ["a"],
                        "call_topic_names": ["REST decision"],
                        "created_at": "2026-04-01T10:00:00Z"}],
            "call-2": [{"call_id": "call-2", "project_topic_ids": ["c"],
                        "call_topic_names": ["API follow-up"],
                        "created_at": "2026-04-08T10:00:00Z"}],
            "call-3": [{"call_id": "call-3",
                        "project_topic_ids": ["unrelated-id"],
                        "call_topic_names": ["something else"],
                        "created_at": "2026-04-15T10:00:00Z"}],
        },
        calls_by_id={
            "call-1": {"id": "call-1", "title": "Kickoff"},
            "call-2": {"id": "call-2", "title": "Review"},
            "call-3": {"id": "call-3", "title": "Other"},
        },
    )

    result = get_lineage_match_groups("c", db)

    assert [g["call_title"] for g in result] == ["Kickoff", "Review"]
    assert [g["project_topic_ids"] for g in result] == [["a"], ["c"]]


def test_build_block_for_merged_topic_includes_call1_excerpt_from_archived_source():
    """End-to-end: Call 1 raised topic 'a'. Call 2 M:N-merged a+b into c.
    At Call 3, building the evidence block for 'c' must include Call 1's
    transcript_excerpt (which lives on archived topic 'a'), tagged with the
    archived-source provenance line.
    """
    db = _make_db_with_updates(
        topics_by_id={
            "c": {"id": "c", "name": "API strategy", "archived": False,
                  "merged_into_topic_id": None},
            "a": {"id": "a", "name": "REST API",     "archived": True,
                  "merged_into_topic_id": "c"},
            "b": {"id": "b", "name": "GraphQL API",  "archived": True,
                  "merged_into_topic_id": "c"},
        },
        sources_by_parent={
            "c": [
                {"id": "a", "name": "REST API",    "archived": True, "merged_into_topic_id": "c"},
                {"id": "b", "name": "GraphQL API", "archived": True, "merged_into_topic_id": "c"},
            ],
        },
        updates_by_topic_id={
            "a": [{"topic_id": "a", "call_id": "call-1",
                   "summary": "REST raised",
                   "transcript_excerpt": "TEAM PICKED REST IN CALL ONE",
                   "follow_up_items": ["spike"], "decisions": [],
                   "created_at": "2026-04-01T10:00:00Z"}],
            "b": [{"topic_id": "b", "call_id": "call-1",
                   "summary": "GraphQL considered",
                   "transcript_excerpt": "GRAPHQL MENTIONED IN CALL ONE",
                   "follow_up_items": [], "decisions": [],
                   "created_at": "2026-04-01T10:30:00Z"}],
            "c": [{"topic_id": "c", "call_id": "call-2",
                   "summary": "Merged API",
                   "transcript_excerpt": "CALL TWO CONSOLIDATION",
                   "follow_up_items": [], "decisions": ["go REST"],
                   "created_at": "2026-04-08T10:00:00Z"}],
        },
        calls_by_id={
            "call-1": {"id": "call-1", "title": "Kickoff"},
            "call-2": {"id": "call-2", "title": "Consolidation"},
        },
    )

    block = build_lineage_evidence_block("API strategy", "c", db)

    # Every call's excerpt appears
    assert "TEAM PICKED REST IN CALL ONE" in block
    assert "GRAPHQL MENTIONED IN CALL ONE" in block
    assert "CALL TWO CONSOLIDATION" in block
    # Provenance lines on ancestor rows
    assert "from archived topic: REST API" in block
    assert "from archived topic: GraphQL API" in block
    # Merged-row (c) has no provenance line
    lines = block.split("\n")
    for i, ln in enumerate(lines):
        if "Consolidation" in ln:
            next_line = lines[i + 1] if i + 1 < len(lines) else ""
            assert "from archived topic" not in next_line
            break
