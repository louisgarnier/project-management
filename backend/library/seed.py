"""System-canonical artifact library entries. Seeded on startup (idempotent).

The library holds both Tier-2 artifact prompts (category='artifacts') and
Tier-1 workflow prompts (category='call_topics' | 'project_topics' |
'merge_verification' | 'not_discussed_check'). Tier-1 entries give users a
single place to edit the canonical prompts that drive extraction / matching /
verification; per-project copies are seeded from these entries, and Reset-to-
default on any project pulls the current library version.

User edits to system entries are preserved — upsert only inserts rows that
don't exist by name. An admin "Reset library to system defaults" action can
explicitly re-apply the seed values (routers/library.py::reset_system_library).
"""

from backend.prompts.artifacts import DEFAULT_ARTIFACTS  # existing EPIC-11 constant
from backend.prompts.call_topics import (
    CALL_TOPICS_V2_PROMPT_BODY,
    CALL_TOPICS_V3_PROMPT_BODY,
)
from backend.prompts.chronology import (
    CHRONOLOGY_NARRATIVE_PROMPT_BODY,
    CHRONOLOGY_RAG_VERIFICATION_PROMPT_BODY,
)
from backend.prompts.merge_verification import MERGE_VERIFICATION_DEFAULT_PROMPT
from backend.prompts.not_discussed_check import NOT_DISCUSSED_DEFAULT_PROMPT
from backend.prompts.project_topics import PROJECT_TOPICS_DEFAULT_PROMPT

# Find by name helper
_ARTIFACTS_BY_NAME = {a["name"]: a for a in DEFAULT_ARTIFACTS}


def _prompt_for(name: str) -> str | None:
    return _ARTIFACTS_BY_NAME.get(name, {}).get("prompt")


SYSTEM_LIBRARY: list[dict] = [
    # ── Tier 1: Workflow prompts (always present, editable via /library) ──
    {
        "name": "Call Topics — v3 (open questions + decisions)",
        "description": (
            "Runs at the Call Topics stage. Extends v2 with two new arrays per topic: "
            "open_questions[] (uncertainties to resolve) and decisions[] (explicit agreements). "
            "DUAL-CLASSIFY rule: investigative tasks (investigate/verify/check/confirm) go into "
            "BOTH tasks[] and open_questions[]. Decisions[] requires verbatim evidence + explicit "
            "closure phrasing — guards against hallucinated soft-agreement decisions. "
            "Rejects topics with all three arrays empty (tasks + open_questions + decisions)."
        ),
        "kind": "llm",
        "prompt": CALL_TOPICS_V3_PROMPT_BODY,
        "template_id": None,
        "llm": "openrouter",
        "model": "deepseek/deepseek-v3.2",
        "context_scope": "this_call_topics",
        "category": "call_topics",
        "is_system": True,
        "seeded_by_default": True,
    },
    {
        "name": "Call Topics — v2 (synthetic, evidence-anchored)",
        "description": (
            "Runs at the Call Topics stage. Extracts SHORT, evidence-anchored topics — "
            "every topic carries verbatim transcript quotes, key terms for matching, and a "
            "list of tasks (each with next-step, status, owner). Replaces EPIC-11's "
            "3-section anchor structure (decisions/follow-ups/open-questions). "
            "Rejects topics without evidence or tasks. "
            "Superseded by v3 — kept available as a fallback."
        ),
        "kind": "llm",
        "prompt": CALL_TOPICS_V2_PROMPT_BODY,
        "template_id": None,
        "llm": "openrouter",
        "model": "deepseek/deepseek-v3.2",
        "context_scope": "this_call_topics",
        "category": "call_topics",
        "is_system": True,
        "seeded_by_default": False,
    },
    {
        "name": "Project Topics Merge (base instructions)",
        "description": "Instructs the model how to combine a new call's topic with the matching existing project topic during merge — which decisions/actions to preserve, how to evolve the summary.",
        "kind": "llm",
        "prompt": PROJECT_TOPICS_DEFAULT_PROMPT,
        "template_id": None,
        "llm": "openrouter",
        "model": "deepseek/deepseek-v3.2",
        "context_scope": "this_call_topics",
        "category": "project_topics",
        "is_system": True,
        "seeded_by_default": False,
    },
    {
        "name": "Merge Verification",
        "description": "Quality-reviews a merged topic against source evidence (transcript + lineage). Detects dropped follow-ups / decisions / summary details and adds them back.",
        "kind": "llm",
        "prompt": MERGE_VERIFICATION_DEFAULT_PROMPT,
        "template_id": None,
        "llm": "openrouter",
        "model": "deepseek/deepseek-v3.2",
        "context_scope": "this_call_topics",
        "category": "merge_verification",
        "is_system": True,
        "seeded_by_default": False,
    },
    {
        "name": "Not-Discussed Verification",
        "description": "For each project topic not surfaced in the current call's extraction, runs a second-pass check against the transcript to confirm it truly wasn't discussed (catches missed mentions).",
        "kind": "llm",
        "prompt": NOT_DISCUSSED_DEFAULT_PROMPT,
        "template_id": None,
        "llm": "openrouter",
        "model": "deepseek/deepseek-v3.2",
        "context_scope": "this_call_topics",
        "category": "not_discussed_check",
        "is_system": True,
        "seeded_by_default": False,
    },

    # ── Tier 2: Artifact prompts (user-generatable) ──
    {
        "name": "Executive Summary",
        "description": "Prose recap of the call for quick scan. LLM runs your prompt with the transcript + extracted call topics (or project-scope: transcript + full project topic lineage) as context.",
        "kind": "llm",
        "prompt": _prompt_for("Executive Summary"),
        "template_id": None,
        "llm": "openrouter",
        "model": "deepseek/deepseek-v3.2",
        "context_scope": "this_call_topics",
        "category": "artifacts",
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
        "context_scope": "this_call_topics",
        "category": "artifacts",
        "is_system": True,
        "seeded_by_default": True,
    },
    {
        "name": "Questions for Stakeholders",
        "description": "Every open question across topics, grouped by topic. Pure Python — pulls open_questions[] from topic_updates, no LLM call.",
        "kind": "template",
        "prompt": None,
        "template_id": "questions_list",
        "llm": None,
        "model": None,
        "context_scope": "this_call_topics",
        "category": "artifacts",
        "is_system": True,
        "seeded_by_default": True,
    },
    {
        "name": "Email Summary (1-pager)",
        "description": "Professional email to the client summarising the call. LLM — full regeneration from transcript + call topics.",
        "kind": "llm",
        "prompt": _prompt_for("Email Summary (1-pager)"),
        "template_id": None,
        "llm": "openrouter",
        "model": "deepseek/deepseek-v3.2",
        "context_scope": "this_call_topics",
        "category": "artifacts",
        "is_system": True,
        "seeded_by_default": False,
    },
    {
        "name": "Email Follow-up (pre-next-call)",
        "description": "Short email sent between calls recapping agreed work. LLM — full regeneration from transcript + call topics.",
        "kind": "llm",
        "prompt": _prompt_for("Email Follow-up (pre-next-call)"),
        "template_id": None,
        "llm": "openrouter",
        "model": "deepseek/deepseek-v3.2",
        "context_scope": "this_call_topics",
        "category": "artifacts",
        "is_system": True,
        "seeded_by_default": False,
    },
    {
        "name": "Next Call Agenda",
        "description": "HYBRID — Python template renders agenda bullets from open/in-progress topics; LLM writes a 1-sentence intro and 1-sentence closing using your prompts.",
        "kind": "hybrid",
        "prompt": '{"intro": "Write a 1-sentence intro for an agenda covering the following open/in-progress topics.", "closing": "Write a 1-sentence closing emphasising the most important topic for next call."}',
        "template_id": "agenda_skeleton",
        "llm": "openrouter",
        "model": "deepseek/deepseek-v3.2",
        "context_scope": "all_project_topics",
        "category": "artifacts",
        "is_system": True,
        "seeded_by_default": False,
    },
    {
        "name": "Risk Register",
        "description": "Template — filters topics with sentiment=concern OR is_parked=true, renders with summary + transcript excerpt. Scope=project, so it spans all calls.",
        "kind": "template",
        "prompt": None,
        "template_id": "risk_register",
        "llm": None,
        "model": None,
        "context_scope": "all_project_topics",
        "category": "artifacts",
        "is_system": True,
        "seeded_by_default": False,
    },
    {
        "name": "Decisions Digest",
        "description": "Template — every topic's decisions[], grouped by topic. Default scope=call; flip to project for a full-project digest.",
        "kind": "template",
        "prompt": None,
        "template_id": "decisions_digest",
        "llm": None,
        "model": None,
        "context_scope": "this_call_topics",
        "category": "artifacts",
        "is_system": True,
        "seeded_by_default": False,
    },
    {
        "name": "Chronology Narrative",
        "description": (
            "Runs at project_updates commit, per (topic, call). Writes a 2-3 sentence "
            "log entry summarising what happened to the topic in this call. Anchored "
            "in the transcript evidence; hard-capped at 400 characters. Frozen at "
            "commit — never regenerated unless manually re-triggered."
        ),
        "kind": "llm",
        "prompt": CHRONOLOGY_NARRATIVE_PROMPT_BODY,
        "template_id": None,
        "llm": "openrouter",
        "model": "deepseek/deepseek-v3.2",
        "context_scope": "this_call_topics",
        "category": "chronology",
        "is_system": True,
        "seeded_by_default": True,
    },
    {
        "name": "RAG Verification",
        "description": (
            "Audits a chronology narrative against the transcript excerpt it summarises. "
            "Returns 'verified' or a drift note pinpointing unsupported claims. "
            "Refuses to default to 'verified' on empty/short input — guards against "
            "hallucinated verifications."
        ),
        "kind": "llm",
        "prompt": CHRONOLOGY_RAG_VERIFICATION_PROMPT_BODY,
        "template_id": None,
        "llm": "openrouter",
        "model": "deepseek/deepseek-v3.2",
        "context_scope": "this_call_topics",
        "category": "chronology",
        "is_system": True,
        "seeded_by_default": True,
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
