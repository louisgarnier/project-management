from typing import Literal

from backend.database.supabase_client import get_client
from backend.prompts.call_topics import CALL_TOPICS_DEFAULT_PROMPT
from backend.utils.logger import db_logger
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api", tags=["artifact-types"])

DEFAULT_ARTIFACT_TYPES: list[dict] = [
    {
        "name": "Executive Summary",
        "prompt": (
            "Write a concise executive summary of this call in 3–5 bullet points. "
            "Use the Topics section to structure your summary around the key themes discussed. "
            "For each bullet: state the topic, what was decided or discussed, and its current status (open/resolved). "
            "Focus on decisions made, key outcomes, and overall direction."
        ),
        "is_default": True,
    },
    {
        "name": "Next Steps & Action Items",
        "prompt": (
            "Extract all action items and next steps from this call. "
            "Group them by topic (use the Topics section as your guide). "
            "For each item state: the topic it belongs to, what needs to be done, "
            "who is responsible (Us / Client / Both), and any deadline discussed. "
            "Prioritise items from topics with sentiment=concern or status=open."
        ),
        "is_default": True,
    },
    {
        "name": "Questions for Stakeholders",
        "prompt": (
            "List all open questions that remain unanswered after this call. "
            "Group them by topic (use the Topics section). "
            "For each question: state the topic, the question, and why it is blocking progress. "
            "Prioritise questions from topics that are open or in_progress."
        ),
        "is_default": True,
    },
    {
        "name": "Email Summary (1-pager)",
        "prompt": (
            "Write a professional 1-page email summarising this call for the client. "
            "Structure it around the topics discussed (use the Topics section). "
            "For each topic: briefly state what was discussed, any decisions made, and follow-up items. "
            "Close with a consolidated next steps section. "
            "Tone: clear and business-professional."
        ),
        "is_default": True,
    },
    {
        "name": "Email Follow-up (pre-next-call)",
        "prompt": (
            "Write a short follow-up email to send before the next call. "
            "For each open topic (from the Topics section), summarise: what was agreed, "
            "what each party should have completed before the next session, and what remains open. "
            "End with a proposed agenda for the next call based on in_progress and open topics."
        ),
        "is_default": True,
    },
    {
        "name": "Next Call Meeting Invite Topics",
        "prompt": (
            "Generate a structured agenda for the next call. "
            "Base it on the Topics section: include all open and in_progress topics, "
            "ordered by priority (concern sentiment first, then by calls_open descending). "
            "For each agenda item: topic name, brief context (1 sentence), and the specific question or decision needed."
        ),
        "is_default": True,
    },
]

DEFAULT_CALL_TOPICS_PROMPT = {
    "name": "Call Topics Extraction",
    "prompt": CALL_TOPICS_DEFAULT_PROMPT,
    "is_default": True,
    "category": "call_topics",
    "llm": "openrouter",
    "model": "anthropic/claude-sonnet-4.6",
}

DEFAULT_PROJECT_TOPICS_PROMPT = {
    "name": "Project Topics Merge",
    "prompt": (
        "You are an expert at matching client call topics to an existing project topic backlog.\n\n"
        "Given topics extracted from the current call and the existing project topic list, "
        "classify each topic:\n"
        '- "followed_up": call topics that match an existing project topic (same business subject, '
        "possibly different wording). Use the existing topic name exactly. Update summary, status, "
        "follow_up_items, and decisions with new information from this call.\n"
        '- "not_discussed": existing project topics not covered by any call topic.\n'
        '- "new_topics": call topics with no match in the existing project list.\n\n'
        "Be generous with matching — slightly different wording for the same business subject "
        "counts as a match."
    ),
    "is_default": True,
    "category": "project_topics",
}

DEFAULT_MERGE_VERIFICATION_PROMPT = {
    "name": "Merge Verification",
    "prompt": (
        "You are a quality reviewer for project topic data. You are given:\n"
        "1. A merged topic (the result of combining existing project data with new call data)\n"
        "2. The full call transcript\n"
        "3. The existing follow-up items and decisions from all source topics\n\n"
        "Your job: verify that the merged topic did NOT lose any important information.\n\n"
        "Check specifically:\n"
        "- Are ALL follow-up items from the sources preserved? If any are missing, add them back.\n"
        "- Are ALL decisions from the sources preserved? If any are missing, add them back.\n"
        "- Does the summary cover all key points discussed in the transcript for this topic?\n"
        "  If anything important was dropped, add it back.\n"
        "- Are specific details (names, dates, numbers, commitments) preserved?\n\n"
        "Return the corrected topic as JSON. If nothing was lost, return the topic unchanged.\n"
        "Do NOT remove or shorten anything. Only ADD back what was lost."
    ),
    "is_default": True,
    "category": "merge_verification",
}

DEFAULT_NOT_DISCUSSED_CHECK_PROMPT = {
    "name": "Not-Discussed Verification",
    "prompt": (
        "You are checking whether a project topic was actually discussed in a call transcript.\n"
        "Given the topic name, its latest summary, and the full call transcript, determine:\n"
        "1. Was this topic mentioned or discussed in the call? (yes/no)\n"
        "2. If yes, provide the relevant transcript excerpt.\n\n"
        'Return JSON: {"discussed": true/false, "transcript_excerpt": "..." or null, '
        '"reasoning": "one sentence explanation"}'
    ),
    "is_default": True,
    "category": "not_discussed_check",
}


def seed_defaults(project_id: str) -> None:
    """Insert artifact types + 2 workflow prompts for a newly created project.

    Artifact types are sourced from the global pool: all artifact_types with
    is_default=True and category='artifacts' across all projects, deduplicated
    by name (most recently created wins). Falls back to hardcoded DEFAULT_ARTIFACT_TYPES
    if no defaults exist yet (first project ever).
    """
    client = get_client()

    # Build artifact rows from global defaults pool
    existing_defaults = (
        client.table("artifact_types")
        .select("name, prompt, llm, context_scope")
        .eq("is_default", True)
        .eq("category", "artifacts")
        .order("created_at", desc=True)
        .execute()
        .data
    )

    seen_names: set[str] = set()
    deduped: list[dict] = []
    for row in existing_defaults:
        key = row["name"].lower().strip()
        if key not in seen_names:
            seen_names.add(key)
            deduped.append(row)

    if deduped:
        artifact_rows = [
            {"project_id": project_id, "category": "artifacts", "is_default": True, **r}
            for r in deduped
        ]
    else:
        # First project ever — seed from hardcoded defaults
        artifact_rows = [
            {"project_id": project_id, "category": "artifacts", **t}
            for t in DEFAULT_ARTIFACT_TYPES
        ]

    client.table("artifact_types").insert(artifact_rows).execute()
    client.table("artifact_types").insert(
        {"project_id": project_id, **DEFAULT_CALL_TOPICS_PROMPT}
    ).execute()
    client.table("artifact_types").insert(
        {"project_id": project_id, **DEFAULT_PROJECT_TOPICS_PROMPT}
    ).execute()
    client.table("artifact_types").insert(
        {"project_id": project_id, **DEFAULT_MERGE_VERIFICATION_PROMPT}
    ).execute()
    client.table("artifact_types").insert(
        {"project_id": project_id, **DEFAULT_NOT_DISCUSSED_CHECK_PROMPT}
    ).execute()
    db_logger.info(
        f"✅ [DB] Seeded {len(artifact_rows)} artifact types + 4 workflow prompts for project: {project_id}"
    )


class ArtifactTypeCreate(BaseModel):
    name: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    llm: Literal["groq", "deepseek", "claude", "openai"] | None = None
    context_scope: Literal["call", "project"] = "call"


class ArtifactTypeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    prompt: str | None = Field(default=None, min_length=1)
    llm: Literal["groq", "deepseek", "claude", "openai"] | None = Field(default=None)
    context_scope: Literal["call", "project"] | None = Field(default=None)
    is_default: bool | None = Field(default=None)


class ArtifactTypeImport(BaseModel):
    type_ids: list[str]


@router.get("/projects/{project_id}/artifact-types")
def list_artifact_types(project_id: str):
    client = get_client()
    db_logger.info(f"🗄️ [DB] Fetching artifact types for project: {project_id}")
    result = (
        client.table("artifact_types")
        .select("*")
        .eq("project_id", project_id)
        .order("created_at")
        .execute()
    )
    db_logger.info(f"✅ [DB] Retrieved {len(result.data)} artifact types")
    return result.data


@router.post("/projects/{project_id}/artifact-types", status_code=201)
def create_artifact_type(project_id: str, payload: ArtifactTypeCreate):
    client = get_client()
    db_logger.info(f"🗄️ [DB] Creating artifact type for project: {project_id}")
    result = (
        client.table("artifact_types")
        .insert(
            {
                "project_id": project_id,
                "name": payload.name,
                "prompt": payload.prompt,
                "is_default": False,
                "category": "artifacts",
                "llm": payload.llm,
                "context_scope": payload.context_scope,
            }
        )
        .execute()
    )
    db_logger.info(f"✅ [DB] Created artifact type: {result.data[0]['id']}")
    return result.data[0]


@router.patch("/projects/{project_id}/artifact-types/{type_id}")
def update_artifact_type(project_id: str, type_id: str, payload: ArtifactTypeUpdate):
    client = get_client()
    db_logger.info(f"🗄️ [DB] Updating artifact type: {type_id}")
    exists = (
        client.table("artifact_types")
        .select("id")
        .eq("id", type_id)
        .eq("project_id", project_id)
        .execute()
    )
    if not exists.data:
        raise HTTPException(status_code=404, detail="Artifact type not found")
    update = payload.model_dump(exclude_unset=True)
    if not update:
        raise HTTPException(status_code=422, detail="No fields to update")
    try:
        result = (
            client.table("artifact_types").update(update).eq("id", type_id).execute()
        )
    except Exception as e:
        db_logger.error(f"❌ [DB] Failed to update artifact type {type_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

    # If is_default is being toggled, cascade to all artifact types with the same name
    # so the default state is global (consistent across all projects)
    if "is_default" in update and result.data:
        artifact_name = result.data[0].get("name", "")
        if artifact_name:
            client.table("artifact_types").update(
                {"is_default": update["is_default"]}
            ).ilike("name", artifact_name).eq("category", "artifacts").neq(
                "id", type_id
            ).execute()
            db_logger.info(
                f"🗄️ [DB] Cascaded is_default={update['is_default']} to all '{artifact_name}' artifact types"
            )

    db_logger.info(f"✅ [DB] Updated artifact type: {type_id}")
    return result.data[0]


@router.delete("/projects/{project_id}/artifact-types/{type_id}", status_code=204)
def delete_artifact_type(project_id: str, type_id: str):
    client = get_client()
    db_logger.info(f"🗄️ [DB] Fetching artifact type for deletion: {type_id}")
    result = (
        client.table("artifact_types")
        .select("id")
        .eq("id", type_id)
        .eq("project_id", project_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Artifact type not found")
    # Delete all generated artifacts referencing this type (across all calls)
    deleted = (
        client.table("artifacts").delete().eq("artifact_type_id", type_id).execute()
    )
    db_logger.info(
        f"🗄️ [DB] Deleted {len(deleted.data)} artifacts referencing type: {type_id}"
    )
    client.table("artifact_types").delete().eq("id", type_id).execute()
    db_logger.info(f"✅ [DB] Deleted artifact type: {type_id}")
    return Response(status_code=204)


@router.post("/projects/{project_id}/artifact-types/import", status_code=201)
def import_artifact_types(project_id: str, payload: ArtifactTypeImport):
    client = get_client()
    db_logger.info(
        f"🗄️ [DB] Importing {len(payload.type_ids)} artifact types into project: {project_id}"
    )
    # Intentionally cross-project: fetch by ID only so users can import from any project.
    # Auth is enforced at the API gateway layer; open reads across projects are acceptable.
    source = (
        client.table("artifact_types")
        .select("name,prompt,llm")
        .in_("id", payload.type_ids)
        .execute()
    )
    if not source.data:
        raise HTTPException(status_code=404, detail="No matching artifact types found")
    copies = [
        {
            "project_id": project_id,
            "name": t["name"],
            "prompt": t["prompt"],
            "is_default": False,
            "category": "artifacts",
            "llm": t.get("llm"),
        }
        for t in source.data
    ]
    result = client.table("artifact_types").insert(copies).execute()
    db_logger.info(f"✅ [DB] Imported {len(result.data)} artifact types")
    return result.data


_DEFAULTS_BY_CATEGORY = {
    "call_topics": DEFAULT_CALL_TOPICS_PROMPT,
    "project_topics": DEFAULT_PROJECT_TOPICS_PROMPT,
    "merge_verification": DEFAULT_MERGE_VERIFICATION_PROMPT,
    "not_discussed_check": DEFAULT_NOT_DISCUSSED_CHECK_PROMPT,
}


@router.get("/artifact-types/defaults/{category}")
def get_default_for_category(category: str):
    """Return the canonical default artifact-type payload for a workflow category.
    Used by the 'Reset to default' button in the UI."""
    if category not in _DEFAULTS_BY_CATEGORY:
        raise HTTPException(status_code=404, detail=f"Unknown category: {category}")
    payload = _DEFAULTS_BY_CATEGORY[category].copy()
    payload.setdefault("llm", None)
    payload.setdefault("model", None)
    return payload
