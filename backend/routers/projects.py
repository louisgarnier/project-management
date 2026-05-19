from datetime import datetime, timezone
from io import BytesIO
from typing import Literal, Optional

from backend.database.supabase_client import get_client
from backend.exporters.xlsx_tracker import build_tracker_xlsx
from backend.routers.artifact_types import seed_defaults
from backend.services.export_service import _slugify
from backend.utils.logger import db_logger, get_logger
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

logger = get_logger("projects")
router = APIRouter(prefix="/api/projects", tags=["projects"])


class ProjectCreate(BaseModel):
    name: str
    description: str = ""


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    description: str | None = None
    context: Optional[str] = None
    default_llm: Optional[Literal["groq", "claude", "openai", "openrouter"]] = None
    default_model: str | None = None


@router.get("")
def list_projects():
    client = get_client()
    db_logger.info("🗄️ [DB] Fetching all projects")
    result = client.table("projects").select("*").execute()
    db_logger.info(f"✅ [DB] Retrieved {len(result.data)} projects")
    return result.data


@router.post("", status_code=201)
def create_project(payload: ProjectCreate):
    client = get_client()
    db_logger.info(f"🗄️ [DB] Creating project: {payload.name}")
    result = client.table("projects").insert(payload.model_dump()).execute()
    project = result.data[0]
    db_logger.info(f"✅ [DB] Created project: {project['id']}")
    seed_defaults(project["id"])
    return project


@router.get("/{project_id}")
def get_project(project_id: str):
    client = get_client()
    db_logger.info(f"🗄️ [DB] Fetching project: {project_id}")
    result = client.table("projects").select("*").eq("id", project_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Project not found")
    return result.data[0]


@router.patch("/{project_id}")
def update_project(project_id: str, payload: ProjectUpdate):
    client = get_client()
    db_logger.info(f"🗄️ [DB] Updating project: {project_id}")
    update_data = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=422, detail="No fields to update")
    try:
        result = (
            client.table("projects").update(update_data).eq("id", project_id).execute()
        )
    except Exception as e:
        logger.error(f"❌ [DB] Failed to update project {project_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {e}")
    if not result.data:
        raise HTTPException(status_code=404, detail="Project not found")
    db_logger.info(f"✅ [DB] Updated project: {project_id}")
    return result.data[0]


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: str):
    client = get_client()
    db_logger.info(f"🗄️ [DB] Deleting project: {project_id}")
    result = client.table("projects").delete().eq("id", project_id).execute()
    if not result.data:
        db_logger.warning(f"⚠️ [DB] Project not found: {project_id}")
        raise HTTPException(status_code=404, detail="Project not found")
    db_logger.info(f"✅ [DB] Deleted project: {project_id}")
    return Response(status_code=204)


@router.get("/{project_id}/tracker-data")
def get_tracker_data(project_id: str):
    """Per-(topic, call) data for the Project Tracker sub-views (Story 15.8).

    Returns the same shape the xlsx exporter consumes — one entry per topic,
    each with a `calls[]` list of per-call topic_updates (chronology_narrative,
    rag_verification_note, tasks, open_questions, decisions, evidence).
    """
    client = get_client()
    db_logger.info(f"🗄️ [DB] Fetching tracker data for project: {project_id}")
    rows = client.table("projects").select("id").eq("id", project_id).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    from backend.services.project_tracker_data import list_project_topics_with_call_history
    data = list_project_topics_with_call_history(project_id)
    db_logger.info(f"✅ [DB] Tracker data: {len(data)} topics for project {project_id}")
    return data


@router.get("/{project_id}/export.xlsx")
def export_tracker_xlsx(project_id: str):
    """Streaming xlsx download for the project tracker (Story 15.8)."""
    client = get_client()
    rows = client.table("projects").select("name").eq("id", project_id).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    project_name = rows[0]["name"]
    try:
        blob = build_tracker_xlsx(project_id)
    except Exception as e:
        logger.exception(f"❌ [Export] xlsx build failed for project={project_id}: {e}")
        raise HTTPException(status_code=500, detail="xlsx generation failed")
    slug = _slugify(project_name)
    iso_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    filename = f"{slug}-tracker-{iso_date}.xlsx"
    return StreamingResponse(
        BytesIO(blob),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
