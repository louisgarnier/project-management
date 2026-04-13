from typing import Literal

from backend.database.supabase_client import get_client
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

DEFAULT_TOPICS_PROMPT = {
    "name": "Topics Extraction",
    "prompt": (
        "You are an expert at extracting business topics from client call transcripts.\n\n"
        "Extract all key business topics discussed. For each topic return a JSON object matching:\n"
        '{"name":"string","summary":"string","follow_up_items":["string"],'
        '"decisions":["string"],"status":"open|in_progress|resolved",'
        '"owner":"Us|Client|Both","sentiment":"positive|neutral|concern"}\n\n'
        "Focus on: decisions made, open questions, action items, relationship dynamics, "
        "technical blockers.\n"
        'Be specific — "Pricing" not "Discussion", '
        '"API Integration Timeline" not "Technical".'
    ),
    "is_default": True,
    "category": "topics",
}


def seed_defaults(project_id: str) -> None:
    """Insert 6 default artifact types + 1 topics prompt for a newly created project."""
    client = get_client()
    artifact_rows = [{"project_id": project_id, "category": "artifacts", **t} for t in DEFAULT_ARTIFACT_TYPES]
    client.table("artifact_types").insert(artifact_rows).execute()
    topics_row = {"project_id": project_id, **DEFAULT_TOPICS_PROMPT}
    client.table("artifact_types").insert(topics_row).execute()
    db_logger.info(f"✅ [DB] Seeded 6 artifact types + 1 topics prompt for project: {project_id}")


class ArtifactTypeCreate(BaseModel):
    name: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    llm: Literal["groq", "deepseek", "claude", "openai"] | None = None


class ArtifactTypeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    prompt: str | None = Field(default=None, min_length=1)
    llm: Literal["groq", "deepseek", "claude", "openai"] | None = Field(default=None)


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
        .insert({
            "project_id": project_id,
            "name": payload.name,
            "prompt": payload.prompt,
            "is_default": False,
            "category": "artifacts",
            "llm": payload.llm,
        })
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
            client.table("artifact_types")
            .update(update)
            .eq("id", type_id)
            .execute()
        )
    except Exception as e:
        db_logger.error(f"❌ [DB] Failed to update artifact type {type_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {e}")
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
    deleted = client.table("artifacts").delete().eq("artifact_type_id", type_id).execute()
    db_logger.info(f"🗄️ [DB] Deleted {len(deleted.data)} artifacts referencing type: {type_id}")
    client.table("artifact_types").delete().eq("id", type_id).execute()
    db_logger.info(f"✅ [DB] Deleted artifact type: {type_id}")
    return Response(status_code=204)


@router.post("/projects/{project_id}/artifact-types/import", status_code=201)
def import_artifact_types(project_id: str, payload: ArtifactTypeImport):
    client = get_client()
    db_logger.info(f"🗄️ [DB] Importing {len(payload.type_ids)} artifact types into project: {project_id}")
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
