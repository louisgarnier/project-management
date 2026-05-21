"""Tests for SYSTEM_LIBRARY seed — EPIC-15 model flip + v2 call_topics entry."""

import pytest

from backend.library.seed import SYSTEM_LIBRARY, upsert_system_library


# ── Model flip ────────────────────────────────────────────────────────────


_ALLOWED_MODELS = {"deepseek/deepseek-v3.2", "anthropic/claude-sonnet-4-6"}


def test_every_llm_or_hybrid_entry_uses_openrouter_deepseek():
    """G8 / FR-13 — every system seed LLM/hybrid entry defaults to openrouter+deepseek (or claude-sonnet for EPIC-16 RAG entries)."""
    for entry in SYSTEM_LIBRARY:
        if entry["kind"] in ("llm", "hybrid"):
            assert entry["llm"] == "openrouter", (
                f"{entry['name']}: expected llm=openrouter, got {entry['llm']!r}"
            )
            assert entry["model"] in _ALLOWED_MODELS, (
                f"{entry['name']}: expected model in {_ALLOWED_MODELS}, got {entry['model']!r}"
            )


def test_template_entries_have_no_llm():
    """Template kind has no LLM call — model/llm fields stay None."""
    for entry in SYSTEM_LIBRARY:
        if entry["kind"] == "template":
            assert entry["llm"] is None, f"{entry['name']}: template should not have llm"
            assert entry["model"] is None, f"{entry['name']}: template should not have model"


# ── v2 call_topics entry ──────────────────────────────────────────────────


def test_v2_call_topics_entry_exists_and_is_default():
    """FR-14 — v2 entry exists and is seeded_by_default=true."""
    matches = [
        e for e in SYSTEM_LIBRARY
        if e["category"] == "call_topics" and e["seeded_by_default"]
    ]
    assert len(matches) == 1, (
        f"expected exactly one default call_topics entry, got {len(matches)}: "
        f"{[m['name'] for m in matches]}"
    )
    entry = matches[0]
    name_lower = entry["name"].lower()
    assert any(tag in name_lower for tag in ("v2", "v3", "v4", "evidence-anchored", "task-centric"))
    assert entry["kind"] == "llm"
    assert entry["llm"] == "openrouter"
    assert entry["model"] == "deepseek/deepseek-v3.2"
    assert entry["prompt"] and len(entry["prompt"]) > 200  # non-trivial body
    # Anti-pattern marker from the v2 rubric
    assert "ANTI-PATTERN" in entry["prompt"], "v2 entry should carry the EPIC-15 anti-pattern marker"


def test_only_one_call_topics_default():
    """No two call_topics entries can both be seeded_by_default=true."""
    defaults = [
        e for e in SYSTEM_LIBRARY
        if e["category"] == "call_topics" and e["seeded_by_default"]
    ]
    assert len(defaults) == 1


# ── Workflow prompt categories — all 5 present ───────────────────────────


def test_all_workflow_categories_present():
    """One Tier-1 entry per workflow category, plus the artifacts category."""
    categories = {e["category"] for e in SYSTEM_LIBRARY}
    for c in ("call_topics", "project_topics", "merge_verification", "not_discussed_check", "artifacts"):
        assert c in categories, f"missing category in seed: {c}"


# ── Idempotent upsert — preserves existing rows ──────────────────────────


def test_upsert_preserves_existing_rows():
    """upsert_system_library inserts only entries that don't exist by name."""
    existing_names = {e["name"] for e in SYSTEM_LIBRARY[:3]}  # pretend the first 3 already exist

    class _Tbl:
        def __init__(self, _n):
            self._filters = []
            self._insert_payload = None

        def select(self, *_a, **_kw):
            return self

        def eq(self, col, val):
            self._filters.append((col, val))
            return self

        def insert(self, payload):
            self._insert_payload = payload
            return self

        def execute(self):
            class _R:
                pass

            r = _R()
            name = next((v for c, v in self._filters if c == "name"), None)
            if self._insert_payload is None:
                # SELECT
                r.data = [{"id": "existing"}] if name in existing_names else []
            else:
                # INSERT
                r.data = [{"id": "new", **self._insert_payload}]
            return r

    class _DB:
        def table(self, n):
            return _Tbl(n)

    result = upsert_system_library(_DB())
    assert result["preserved"] == 3, result
    assert result["inserted"] == len(SYSTEM_LIBRARY) - 3, result


def test_upsert_does_not_modify_projects():
    """Story 15.2 NG10 — upsert touches only artifact_library, never projects."""
    touched_tables: list[str] = []

    class _Tbl:
        def __init__(self, n):
            touched_tables.append(n)
            self._payload = None

        def select(self, *_a, **_kw):
            return self

        def eq(self, *_a, **_kw):
            return self

        def insert(self, p):
            self._payload = p
            return self

        def execute(self):
            class _R:
                data = []
            return _R()

    class _DB:
        def table(self, n):
            return _Tbl(n)

    upsert_system_library(_DB())
    assert all(t == "artifact_library" for t in touched_tables), (
        f"upsert touched non-artifact_library table(s): {set(touched_tables) - {'artifact_library'}}"
    )


def test_three_new_rag_workflow_entries_seeded():
    """EPIC-16: verify_new_topic, verify_not_discussed, extract_topic_updates exist as system seeded_by_default entries."""
    from backend.library.seed import SYSTEM_LIBRARY
    cats = {e["category"] for e in SYSTEM_LIBRARY if e.get("is_system") and e.get("seeded_by_default")}
    assert "verify_new_topic" in cats
    assert "verify_not_discussed" in cats
    assert "extract_topic_updates" in cats


def test_old_workflow_prompts_not_seeded_by_default():
    """EPIC-16: project_topics / merge_verification / not_discussed_check (old) must no longer be seeded_by_default=True."""
    from backend.library.seed import SYSTEM_LIBRARY
    for e in SYSTEM_LIBRARY:
        if e["category"] in ("project_topics", "merge_verification", "not_discussed_check"):
            assert e.get("seeded_by_default") is False, f"{e['category']} should no longer be seeded by default"
            assert e.get("is_system") is False, f"{e['category']} should no longer be is_system=True"
