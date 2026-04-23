"""System-canonical artifact library entries. Seeded on startup (idempotent).

User edits to system entries are preserved — upsert only inserts rows that
don't exist by name. An admin "Reset library to system defaults" action can
explicitly re-apply the seed values (routers/library.py::reset_system_library).
"""

from backend.prompts.artifacts import DEFAULT_ARTIFACTS  # existing EPIC-11 constant

# Find by name helper
_ARTIFACTS_BY_NAME = {a["name"]: a for a in DEFAULT_ARTIFACTS}


def _prompt_for(name: str) -> str | None:
    return _ARTIFACTS_BY_NAME.get(name, {}).get("prompt")


SYSTEM_LIBRARY: list[dict] = [
    {
        "name": "Executive Summary",
        "description": "Prose recap of the call for quick scan.",
        "kind": "llm",
        "prompt": _prompt_for("Executive Summary"),
        "template_id": None,
        "llm": "openrouter",
        "model": "anthropic/claude-sonnet-4.6",
        "context_scope": "call",
        "is_system": True,
        "seeded_by_default": True,
    },
    {
        "name": "Next Steps & Action Items",
        "description": "Every action item across topics, grouped by topic, owner bolded.",
        "kind": "template",
        "prompt": None,
        "template_id": "next_steps",
        "llm": None,
        "model": None,
        "context_scope": "call",
        "is_system": True,
        "seeded_by_default": True,
    },
    {
        "name": "Questions for Stakeholders",
        "description": "Every open question across topics, grouped by topic.",
        "kind": "template",
        "prompt": None,
        "template_id": "questions_list",
        "llm": None,
        "model": None,
        "context_scope": "call",
        "is_system": True,
        "seeded_by_default": True,
    },
    {
        "name": "Email Summary (1-pager)",
        "description": "Professional email to the client summarising the call.",
        "kind": "llm",
        "prompt": _prompt_for("Email Summary (1-pager)"),
        "template_id": None,
        "llm": "openrouter",
        "model": "anthropic/claude-sonnet-4.6",
        "context_scope": "call",
        "is_system": True,
        "seeded_by_default": False,
    },
    {
        "name": "Email Follow-up (pre-next-call)",
        "description": "Short email sent between calls recapping agreed work.",
        "kind": "llm",
        "prompt": _prompt_for("Email Follow-up (pre-next-call)"),
        "template_id": None,
        "llm": "openrouter",
        "model": "anthropic/claude-sonnet-4.6",
        "context_scope": "call",
        "is_system": True,
        "seeded_by_default": False,
    },
    {
        "name": "Next Call Agenda",
        "description": "Open/in-progress topics as agenda; LLM writes intro + closing.",
        "kind": "hybrid",
        "prompt": '{"intro": "Write a 1-sentence intro for an agenda covering the following open/in-progress topics.", "closing": "Write a 1-sentence closing emphasising the most important topic for next call."}',
        "template_id": "agenda_skeleton",
        "llm": "openrouter",
        "model": "anthropic/claude-sonnet-4.6",
        "context_scope": "call",
        "is_system": True,
        "seeded_by_default": False,
    },
    {
        "name": "Risk Register",
        "description": "Topics with sentiment=concern or is_parked=true, with excerpts.",
        "kind": "template",
        "prompt": None,
        "template_id": "risk_register",
        "llm": None,
        "model": None,
        "context_scope": "project",
        "is_system": True,
        "seeded_by_default": False,
    },
    {
        "name": "Decisions Digest",
        "description": "All decisions across topics, call-scoped or project-scoped.",
        "kind": "template",
        "prompt": None,
        "template_id": "decisions_digest",
        "llm": None,
        "model": None,
        "context_scope": "call",
        "is_system": True,
        "seeded_by_default": False,
    },
]


def upsert_system_library(db) -> dict:
    """Idempotently insert SYSTEM_LIBRARY rows that don't already exist.

    Does NOT overwrite existing entries (user edits preserved). For explicit
    reset-to-defaults, use POST /api/library/reset-system which re-applies
    the original seed values.

    Returns {"inserted": N, "preserved": M}.
    """
    inserted = 0
    preserved = 0
    for entry in SYSTEM_LIBRARY:
        existing = (
            db.table("artifact_library")
            .select("id")
            .eq("name", entry["name"])
            .execute()
            .data
        )
        if existing:
            preserved += 1
            continue
        db.table("artifact_library").insert(entry).execute()
        inserted += 1
    return {"inserted": inserted, "preserved": preserved}
