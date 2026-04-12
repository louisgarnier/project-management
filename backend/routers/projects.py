from typing import Literal

from backend.database.supabase_client import get_client
from backend.routers.artifact_types import seed_defaults
from backend.utils.logger import db_logger, get_logger
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

logger = get_logger("projects")
router = APIRouter(prefix="/api/projects", tags=["projects"])


class ProjectCreate(BaseModel):
    name: str
    description: str = ""


class ProjectUpdate(BaseModel):
    default_llm: Literal["groq", "claude", "openai"]


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
    result = (
        client.table("projects")
        .update(payload.model_dump())
        .eq("id", project_id)
        .execute()
    )
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
