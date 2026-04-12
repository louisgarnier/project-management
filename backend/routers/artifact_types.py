from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from backend.database.supabase_client import get_client
from backend.utils.logger import db_logger

router = APIRouter(prefix="/api", tags=["artifact-types"])

DEFAULT_ARTIFACT_TYPES = [
    {
        "name": "Executive Summary",
        "prompt": "Write a concise executive summary of this call in 3–5 bullet points. Focus on decisions made, key outcomes, and the overall direction agreed upon.",
        "is_default": True,
    },
    {
        "name": "Next Steps & Action Items",
        "prompt": "Extract all action items and next steps from this call. For each item, state: what needs to be done, who is responsible (if mentioned), and any deadline discussed.",
        "is_default": True,
    },
    {
        "name": "Questions for Stakeholders",
        "prompt": "List all open questions that remain unanswered after this call and should be raised with stakeholders before the next session.",
        "is_default": True,
    },
    {
        "name": "Email Summary (1-pager)",
        "prompt": "Write a professional 1-page email summarising this call for the client. Include: context, key discussion points, decisions made, and next steps. Tone: clear and business-professional.",
        "is_default": True,
    },
    {
        "name": "Email Follow-up (pre-next-call)",
        "prompt": "Write a short follow-up email to send before the next call. Summarise what was agreed, what each party should have completed, and confirm the agenda for the next session.",
        "is_default": True,
    },
    {
        "name": "Next Call Meeting Invite Topics",
        "prompt": "Generate a structured agenda for the next call based on open items, unresolved questions, and planned next steps from this call.",
        "is_default": True,
    },
]


def seed_defaults(project_id: str) -> None:
    """Insert 6 default artifact types for a newly created project."""
    client = get_client()
    rows = [{"project_id": project_id, **t} for t in DEFAULT_ARTIFACT_TYPES]
    client.table("artifact_types").insert(rows).execute()
    db_logger.info(f"✅ [DB] Seeded 6 default artifact types for project: {project_id}")


class ArtifactTypeCreate(BaseModel):
    name: str = Field(min_length=1)
    prompt: str = Field(min_length=1)


class ArtifactTypeUpdate(BaseModel):
    name: str | None = None
    prompt: str | None = None


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
    update = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not update:
        raise HTTPException(status_code=422, detail="No fields to update")
    result = (
        client.table("artifact_types")
        .update(update)
        .eq("id", type_id)
        .execute()
    )
    db_logger.info(f"✅ [DB] Updated artifact type: {type_id}")
    return result.data[0]


@router.delete("/projects/{project_id}/artifact-types/{type_id}", status_code=204)
def delete_artifact_type(project_id: str, type_id: str):
    client = get_client()
    db_logger.info(f"🗄️ [DB] Fetching artifact type for deletion: {type_id}")
    result = (
        client.table("artifact_types")
        .select("is_default")
        .eq("id", type_id)
        .eq("project_id", project_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Artifact type not found")
    if result.data[0]["is_default"]:
        raise HTTPException(status_code=403, detail="Cannot delete a default artifact type")
    client.table("artifact_types").delete().eq("id", type_id).execute()
    db_logger.info(f"✅ [DB] Deleted artifact type: {type_id}")
    return Response(status_code=204)


@router.post("/projects/{project_id}/artifact-types/import", status_code=201)
def import_artifact_types(project_id: str, payload: ArtifactTypeImport):
    client = get_client()
    db_logger.info(f"🗄️ [DB] Importing {len(payload.type_ids)} artifact types into project: {project_id}")
    source = (
        client.table("artifact_types")
        .select("name,prompt")
        .in_("id", payload.type_ids)
        .execute()
    )
    if not source.data:
        raise HTTPException(status_code=404, detail="No matching artifact types found")
    copies = [
        {"project_id": project_id, "name": t["name"], "prompt": t["prompt"], "is_default": False}
        for t in source.data
    ]
    result = client.table("artifact_types").insert(copies).execute()
    db_logger.info(f"✅ [DB] Imported {len(result.data)} artifact types")
    return result.data
