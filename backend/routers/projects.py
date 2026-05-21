from typing import Literal, Optional

from backend.database.supabase_client import get_client
from backend.routers.artifact_types import seed_defaults
from backend.utils.logger import db_logger, get_logger
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
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

    # Apply system_settings defaults so new projects inherit org-level LLM
    # config (e.g. openrouter/deepseek-v3.2). Without this, projects.default_llm
    # falls back to the legacy column default 'groq' which has tight TPM caps
    # that fail on realistic transcript sizes.
    insert_payload = payload.model_dump()
    try:
        settings_row = (
            client.table("system_settings").select("default_llm, default_model").limit(1).execute().data
        )
        if settings_row:
            s = settings_row[0]
            if s.get("default_llm"):
                insert_payload["default_llm"] = s["default_llm"]
            if s.get("default_model"):
                insert_payload["default_model"] = s["default_model"]
    except Exception as e:
        logger.warning(f"⚠️ [Project] could not read system_settings defaults: {e}")

    result = client.table("projects").insert(insert_payload).execute()
    project = result.data[0]
    db_logger.info(f"✅ [DB] Created project: {project['id']} (llm={project.get('default_llm')!r}, model={project.get('default_model')!r})")
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
