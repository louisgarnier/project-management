from typing import Literal

from backend.database.supabase_client import get_client
from backend.prompts.artifacts import DEFAULT_ARTIFACTS
from backend.prompts.call_topics import CALL_TOPICS_DEFAULT_PROMPT
from backend.prompts.merge_verification import MERGE_VERIFICATION_DEFAULT_PROMPT
from backend.prompts.not_discussed_check import NOT_DISCUSSED_DEFAULT_PROMPT
from backend.prompts.project_topics import PROJECT_TOPICS_DEFAULT_PROMPT
from backend.utils.logger import db_logger
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api", tags=["artifact-types"])

DEFAULT_ARTIFACT_TYPES: list[dict] = [
    {
        **t,
        "is_default": True,
        "llm": "openrouter",
        "model": "anthropic/claude-sonnet-4.6",
    }
    for t in DEFAULT_ARTIFACTS
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
    "prompt": PROJECT_TOPICS_DEFAULT_PROMPT,
    "is_default": True,
    "category": "project_topics",
    "llm": None,
    "model": None,
}

DEFAULT_MERGE_VERIFICATION_PROMPT = {
    "name": "Merge Verification",
    "prompt": MERGE_VERIFICATION_DEFAULT_PROMPT,
    "is_default": True,
    "category": "merge_verification",
    "llm": "openrouter",
    "model": "anthropic/claude-sonnet-4.6",
}

DEFAULT_NOT_DISCUSSED_CHECK_PROMPT = {
    "name": "Not-Discussed Verification",
    "prompt": NOT_DISCUSSED_DEFAULT_PROMPT,
    "is_default": True,
    "category": "not_discussed_check",
    "llm": "openrouter",
    "model": "google/gemini-2.5-pro",
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
    llm: Literal["groq", "deepseek", "claude", "openai", "openrouter"] | None = None
    model: str | None = None
    context_scope: Literal["call", "project"] = "call"


class ArtifactTypeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    prompt: str | None = Field(default=None, min_length=1)
    llm: Literal["groq", "deepseek", "claude", "openai", "openrouter"] | None = Field(
        default=None
    )
    model: str | None = Field(default=None)
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
                "model": payload.model,
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
        .select("name,prompt,llm,model")
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
            "model": t.get("model"),
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
