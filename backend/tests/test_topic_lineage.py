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


# ---------------------------------------------------------------------------
# Story 10.6 / Fix 6.1 — Call Topics Extraction vocabulary hint
# ---------------------------------------------------------------------------

import asyncio
from unittest.mock import patch, AsyncMock


def _make_extraction_db(project_id: str, transcript: str, existing_topic_names: list[str]):
    """Build a MagicMock DB compatible with extract_call_topics's queries:
       - calls.select(...).eq(id, call_id) → [{project_id, transcript}]
       - artifact_types.select(...).eq(project_id).eq(category).order.limit → []
       - projects.select(...).eq(id).execute → [{default_llm, context}]
       - topics.select('name').eq(project_id).eq(archived, False) → existing names
    """
    db = MagicMock()

    def table_side(name):
        t = MagicMock()
        if name == "calls":
            (
                t.select.return_value
                 .eq.return_value
                 .execute.return_value
                 .data
            ) = [{"project_id": project_id, "transcript": transcript}]
            return t
        if name == "artifact_types":
            (
                t.select.return_value
                 .eq.return_value
                 .eq.return_value
                 .order.return_value
                 .limit.return_value
                 .execute.return_value
                 .data
            ) = []
            return t
        if name == "projects":
            (
                t.select.return_value
                 .eq.return_value
                 .execute.return_value
                 .data
            ) = [{"default_llm": "groq", "context": ""}]
            return t
        if name == "topics":
            # .select("name").eq("project_id", X).eq("archived", False).execute()
            (
                t.select.return_value
                 .eq.return_value
                 .eq.return_value
                 .execute.return_value
                 .data
            ) = [{"name": n} for n in existing_topic_names]
            return t
        return t

    db.table.side_effect = table_side
    return db


def test_extraction_prompt_includes_vocabulary_hint_when_topics_exist():
    """Fix 6.1: existing project topic names are passed as a vocabulary hint
    right before the transcript.
    """
    from backend.services.topics_service import extract_call_topics

    db = _make_extraction_db(
        project_id="proj-1",
        transcript="We discussed API design and billing tiers.",
        existing_topic_names=["API design", "Billing tier"],
    )

    captured = {}

    async def fake_llm(prompt, llm, *, model=None):
        captured["prompt"] = prompt
        return []

    with patch("backend.services.topics_service.get_client", return_value=db), \
         patch("backend.services.topics_service._call_llm",
               new=AsyncMock(side_effect=fake_llm)):
        asyncio.run(extract_call_topics("call-1"))

    prompt = captured["prompt"]
    assert "Existing project topic names" in prompt
    assert "- API design" in prompt
    assert "- Billing tier" in prompt
    assert "Transcript:" in prompt
    # Vocabulary hint appears immediately before the Transcript: section
    assert prompt.index("Existing project topic names") < prompt.index("Transcript:")


def test_extraction_prompt_has_no_vocabulary_hint_when_no_prior_topics():
    """Fix 6.1: call-1 (empty project) → prompt unchanged, no vocab header."""
    from backend.services.topics_service import extract_call_topics

    db = _make_extraction_db(
        project_id="proj-1",
        transcript="Kickoff call.",
        existing_topic_names=[],
    )

    captured = {}

    async def fake_llm(prompt, llm, *, model=None):
        captured["prompt"] = prompt
        return []

    with patch("backend.services.topics_service.get_client", return_value=db), \
         patch("backend.services.topics_service._call_llm",
               new=AsyncMock(side_effect=fake_llm)):
        asyncio.run(extract_call_topics("call-1"))

    assert "Existing project topic names" not in captured["prompt"]


# ---------------------------------------------------------------------------
# Story 10.6 / Fix 6.4 — Merge Verification: ancestor evidence + full transcript
# ---------------------------------------------------------------------------

def _make_verify_db(project_id: str, transcript: str):
    """Minimal DB mock for _verify_merged_topics.

    Responses needed:
      - calls.select(project_id, transcript).eq(id).execute → [{project_id, transcript}]
      - artifact_types.select(prompt, llm).eq.eq.order.limit.execute → []
        (so it falls through to the default verify_instructions)
      - projects.select(default_llm).eq(id).execute → [{default_llm: 'groq'}]
      - topic_match_groups.select.eq(call_id).execute → []
      - calls.select(pending_topics).eq(id).execute → [{pending_topics: []}]
      - _get_previous_topics queries (topics.select... + topic_updates.select...)
        → empty lists (we don't exercise the source-list fallback path here)
    """
    db = MagicMock()

    def table_side(name):
        t = MagicMock()
        if name == "calls":
            (
                t.select.return_value
                 .eq.return_value
                 .execute.return_value
                 .data
            ) = [{
                "project_id": project_id,
                "transcript": transcript,
                "pending_topics": [],
            }]
            return t
        if name == "artifact_types":
            (
                t.select.return_value
                 .eq.return_value
                 .eq.return_value
                 .order.return_value
                 .limit.return_value
                 .execute.return_value
                 .data
            ) = []
            return t
        if name == "projects":
            (
                t.select.return_value
                 .eq.return_value
                 .execute.return_value
                 .data
            ) = [{"default_llm": "groq"}]
            return t
        if name == "topic_match_groups":
            (
                t.select.return_value
                 .eq.return_value
                 .execute.return_value
                 .data
            ) = []
            return t
        if name == "topics":
            (
                t.select.return_value
                 .eq.return_value
                 .eq.return_value
                 .execute.return_value
                 .data
            ) = []
            return t
        if name == "topic_updates":
            (
                t.select.return_value
                 .eq.return_value
                 .order.return_value
                 .limit.return_value
                 .execute.return_value
                 .data
            ) = []
            return t
        return t

    db.table.side_effect = table_side
    return db


def test_merge_verification_prompt_includes_ancestor_lineage_block():
    """Fix 6.4: when the merged topic has a topic_id, the verification prompt
    contains the ancestor-aware evidence block (not the flat source-lists path),
    and the full transcript is passed (no 8000-char truncation).
    """
    from backend.services.topics_service import _verify_merged_topics

    # Transcript longer than 8000 chars with a unique marker at the END
    marker = "END_MARKER_XYZ_12345"
    transcript = ("A" * 9000) + " " + marker

    db = _make_verify_db("proj-1", transcript)

    captured = {}

    async def fake_llm(prompt, llm, *, model=None):
        captured["prompt"] = prompt
        return {"name": "API", "summary": "ok", "follow_up_items": [],
                "decisions": [], "status": "open", "owner": "Us",
                "sentiment": "neutral"}

    def fake_evidence_block(name, topic_id, _db):
        return (
            f'== Topic: "{name}" — Per-Call Evidence ==\n\n'
            f'--- Kickoff ---\n'
            f'(from archived topic: REST API)\n'
            f'Transcript: we picked REST\n'
            f'Summary: REST raised\n'
        )

    merged = [{
        "topic_id": "c",
        "name": "API",
        "summary": "merged",
        "follow_up_items": [],
        "decisions": [],
        "status": "open",
        "owner": "Us",
        "sentiment": "neutral",
    }]

    with patch("backend.services.topics_service.get_client", return_value=db), \
         patch("backend.services.topics_service.build_lineage_evidence_block",
               side_effect=fake_evidence_block), \
         patch("backend.services.topics_service._call_llm",
               new=AsyncMock(side_effect=fake_llm)):
        asyncio.run(_verify_merged_topics("call-1", merged))

    prompt = captured["prompt"]
    # Lineage block present
    assert '== Topic: "API" — Per-Call Evidence ==' in prompt
    assert "(from archived topic: REST API)" in prompt
    # Full transcript present — the unique end marker must survive (no :8000 cut)
    assert marker in prompt
    # Section heading updated
    assert "Current call full transcript" in prompt


def test_merge_verification_prompt_falls_back_to_flat_lists_when_no_topic_id():
    """Fix 6.4: merged topic with topic_id=None (brand-new M:N merge result)
    must NOT call the lineage helper and must use the flat source lists instead.
    """
    from backend.services.topics_service import _verify_merged_topics

    db = _make_verify_db("proj-1", "short transcript")

    captured = {}

    async def fake_llm(prompt, llm, *, model=None):
        captured["prompt"] = prompt
        return {"name": "New M:N", "summary": "ok", "follow_up_items": [],
                "decisions": [], "status": "open", "owner": "Us",
                "sentiment": "neutral"}

    lineage_calls = {"count": 0}

    def fake_evidence_block(*args, **kwargs):
        lineage_calls["count"] += 1
        return "SHOULD_NOT_APPEAR"

    merged = [{
        "topic_id": None,
        "name": "New M:N",
        "summary": "merged",
        "follow_up_items": [],
        "decisions": [],
        "status": "open",
        "owner": "Us",
        "sentiment": "neutral",
    }]

    with patch("backend.services.topics_service.get_client", return_value=db), \
         patch("backend.services.topics_service.build_lineage_evidence_block",
               side_effect=fake_evidence_block), \
         patch("backend.services.topics_service._call_llm",
               new=AsyncMock(side_effect=fake_llm)):
        asyncio.run(_verify_merged_topics("call-1", merged))

    # Did not crash. Did not call lineage helper.
    assert lineage_calls["count"] == 0
    prompt = captured["prompt"]
    assert "SHOULD_NOT_APPEAR" not in prompt
    # Uses flat source lists path instead
    assert "Source follow-up items" in prompt
    assert "Source decisions" in prompt


def test_merge_verification_rejects_hallucinated_bucket_shape():
    """Regression: on 2026-04-24, `_verify_merged_topics` silently substituted
    a bucket-shaped LLM hallucination (`{topic_id, new_topics, followed_up,
    not_discussed}`) into `merge_cache`, corrupting two items for the puoihug
    project. Downstream the UI rendered phantom "Not discussed" rows and
    `validate-updates` threw 7 pydantic TopicUpdate errors.

    Guard: when the LLM returns a dict missing required topic fields
    (name/summary/follow_up_items/decisions/status/owner/sentiment), the
    verifier MUST keep the original merged topic and skip substitution.
    """
    from backend.services.topics_service import _verify_merged_topics

    db = _make_verify_db("proj-1", "some transcript content")

    async def hallucinated_llm(prompt, llm, *, model=None):
        # Simulate the bucket-shape hallucination observed in prod
        return {
            "new_topics": [],
            "followed_up": [],
            "not_discussed": [],
        }

    original = {
        "topic_id": "topic-good",
        "name": "Risk Model Selection",
        "summary": "Team weighing LMAC vs Monte Carlo Mac — benchmark pending.",
        "follow_up_items": ["Nick: run benchmark"],
        "decisions": ["Phase 2 gated on benchmark"],
        "open_questions": [],
        "status": "open",
        "owner": "Us",
        "sentiment": "concern",
        "is_parked": False,
        "importance": "high",
        "rationale": "All 4 criteria met",
    }

    with patch("backend.services.topics_service.get_client", return_value=db), \
         patch("backend.services.topics_service.build_lineage_evidence_block",
               return_value="(evidence)"), \
         patch("backend.services.topics_service._call_llm",
               new=AsyncMock(side_effect=hallucinated_llm)):
        result = asyncio.run(_verify_merged_topics("call-1", [original]))

    assert len(result) == 1
    kept = result[0]
    # Original topic preserved, NOT replaced with the bucket-shape garbage
    assert kept["name"] == "Risk Model Selection", (
        f"Expected original topic kept; got substituted shape with keys={list(kept.keys())}"
    )
    assert "new_topics" not in kept, (
        "Hallucinated bucket fields must not leak into the verified topic"
    )
    assert "followed_up" not in kept
    # topic_id preserved
    assert kept["topic_id"] == "topic-good"


# ---------------------------------------------------------------------------
# Story 10.6 / Fix 6.5 — get_project_topics_lineage_context
# ---------------------------------------------------------------------------

def test_get_project_topics_lineage_context_returns_evidence_blocks_per_open_topic():
    """Fix 6.5: one block per open/in_progress topic, resolved topics skipped,
    sections joined with '\\n\\n---\\n\\n', empty → ''.
    """
    from backend.services import topics_service

    open_topics = [
        {"topic_id": "t1", "name": "API design", "status": "open",
         "owner": "Us", "sentiment": "neutral",
         "summary": "", "follow_up_items": [], "decisions": []},
        {"topic_id": "t2", "name": "Billing tier", "status": "in_progress",
         "owner": "Client", "sentiment": "concern",
         "summary": "", "follow_up_items": [], "decisions": []},
        {"topic_id": "t3", "name": "Old thing", "status": "resolved",
         "owner": "Us", "sentiment": "neutral",
         "summary": "", "follow_up_items": [], "decisions": []},
    ]

    def fake_evidence_block(name, topic_id, db):
        return f"EVIDENCE_FOR_{topic_id}"

    db = MagicMock()

    with patch.object(topics_service, "_get_previous_topics",
                      return_value=open_topics), \
         patch.object(topics_service, "build_lineage_evidence_block",
                      side_effect=fake_evidence_block):
        out = topics_service.get_project_topics_lineage_context("proj-1", db)

    # Both open topics present
    assert "EVIDENCE_FOR_t1" in out
    assert "EVIDENCE_FOR_t2" in out
    # Resolved topic excluded
    assert "EVIDENCE_FOR_t3" not in out
    # Sections separated by the explicit separator
    assert "\n\n---\n\n" in out


def test_get_project_topics_lineage_context_returns_empty_string_when_no_open_topics():
    from backend.services import topics_service

    with patch.object(topics_service, "_get_previous_topics", return_value=[]):
        out = topics_service.get_project_topics_lineage_context("proj-1", MagicMock())

    assert out == ""

