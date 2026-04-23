from unittest.mock import MagicMock

from backend.library.seed import SYSTEM_LIBRARY, upsert_system_library


def test_system_library_has_8_entries():
    assert len(SYSTEM_LIBRARY) == 8


def test_system_library_seeded_by_default_count():
    """Exactly 3 entries are seeded by default (per spec §4.3)."""
    seeded = [e for e in SYSTEM_LIBRARY if e["seeded_by_default"]]
    assert len(seeded) == 3
    names = {e["name"] for e in seeded}
    assert names == {
        "Executive Summary",
        "Next Steps & Action Items",
        "Questions for Stakeholders",
    }


def test_system_library_kinds():
    kinds = {e["name"]: e["kind"] for e in SYSTEM_LIBRARY}
    assert kinds["Executive Summary"] == "llm"
    assert kinds["Next Steps & Action Items"] == "template"
    assert kinds["Questions for Stakeholders"] == "template"
    assert kinds["Email Summary (1-pager)"] == "llm"
    assert kinds["Email Follow-up (pre-next-call)"] == "llm"
    assert kinds["Next Call Agenda"] == "hybrid"
    assert kinds["Risk Register"] == "template"
    assert kinds["Decisions Digest"] == "template"


def test_upsert_new_entries_inserts_all():
    db = MagicMock()
    # Simulate empty library — every name check returns no row
    db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = (
        []
    )
    result = upsert_system_library(db)
    assert result["inserted"] == 8
    assert result["preserved"] == 0


def test_upsert_preserves_existing_entries():
    db = MagicMock()
    # Simulate library already has all 8 entries — every name lookup returns a row
    db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"id": "existing-uuid"}
    ]
    result = upsert_system_library(db)
    assert result["inserted"] == 0
    assert result["preserved"] == 8
