from typing import Literal

from backend.database.supabase_client import get_client
from backend.prompts.artifacts import DEFAULT_ARTIFACTS
from backend.prompts.call_topics import CALL_TOPICS_V2_PROMPT_BODY
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
    "prompt": CALL_TOPICS_V2_PROMPT_BODY,
    "is_default": True,
    "category": "call_topics",
    "llm": None,
    "model": None,
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
    "llm": None,
    "model": None,
}

DEFAULT_NOT_DISCUSSED_CHECK_PROMPT = {
    "name": "Not-Discussed Verification",
    "prompt": NOT_DISCUSSED_DEFAULT_PROMPT,
    "is_default": True,
    "category": "not_discussed_check",
    "llm": None,
    "model": None,
}


def seed_defaults(project_id: str) -> None:
    """Seed a new project with workflow prompts + default artifact types.
    Failures on individual inserts are logged but do not abort the whole seed —
    a partial project is better than none, and the user can fix gaps manually.
    """
    client = get_client()

    # Tier 1 — workflow prompts (EPIC-11 pattern)
    for workflow_prompt in (
        DEFAULT_CALL_TOPICS_PROMPT,
        DEFAULT_PROJECT_TOPICS_PROMPT,
        DEFAULT_MERGE_VERIFICATION_PROMPT,
        DEFAULT_NOT_DISCUSSED_CHECK_PROMPT,
    ):
        try:
            client.table("artifact_types").insert(
                {"project_id": project_id, **workflow_prompt}
            ).execute()
        except Exception as e:
            db_logger.warning(
                f"⚠️ [seed_defaults] Tier-1 insert failed ({workflow_prompt.get('name')!r}): {e}"
            )

    # Tier 2 — library-backed artifact types with seeded_by_default=true
    try:
        seeded = (
            client.table("artifact_library")
            .select(
                "id, name, description, kind, prompt, template_id, llm, model, context_scope"
            )
            .eq("seeded_by_default", True)
            .execute()
            .data
        )
    except Exception as e:
        db_logger.warning(f"⚠️ [seed_defaults] artifact_library read failed: {e}")
        seeded = []

    inserted = 0
    for entry in seeded:
        try:
            # artifact_types CHECK may still use the legacy ('call', 'project')
            # enum even though artifact_library accepts the Phase 2 enum.
            # Map Phase 2 values back to 'call' for compatibility.
            cs = entry.get("context_scope") or "call"
            if cs in {"this_call_transcript", "all_call_transcripts"}:
                cs = "call"
            client.table("artifact_types").insert(
                {
                    "project_id": project_id,
                    "name": entry["name"],
                    "prompt": entry.get("prompt"),
                    "is_default": True,
                    "category": "artifacts",
                    "kind": entry["kind"],
                    "template_id": entry.get("template_id"),
                    "library_ref_id": entry["id"],
                    "llm": entry.get("llm"),
                    "model": entry.get("model"),
                    "context_scope": cs,
                }
            ).execute()
            inserted += 1
        except Exception as e:
            db_logger.warning(
                f"⚠️ [seed_defaults] Tier-2 insert failed ({entry.get('name')!r}): {e}"
            )

    db_logger.info(
        f"✅ [DB] Seeded project {project_id}: workflow prompts attempted + {inserted}/{len(seeded)} library artifacts inserted"
    )


class ArtifactTypeCreate(BaseModel):
    name: str = Field(min_length=1)
    prompt: str | None = Field(default=None)
    llm: Literal["groq", "deepseek", "claude", "openai", "openrouter"] | None = None
    model: str | None = None
    context_scope: Literal["call", "project"] = "call"
    kind: Literal["llm", "template", "hybrid"] = "llm"
    template_id: str | None = None
    library_ref_id: str | None = None


class ArtifactTypeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    prompt: str | None = Field(default=None)
    llm: Literal["groq", "deepseek", "claude", "openai", "openrouter"] | None = Field(
        default=None
    )
    model: str | None = Field(default=None)
    context_scope: Literal["call", "project"] | None = Field(default=None)
    is_default: bool | None = Field(default=None)
    kind: Literal["llm", "template", "hybrid"] | None = Field(default=None)
    template_id: str | None = Field(default=None)
    library_ref_id: str | None = Field(default=None)


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
                "kind": payload.kind,
                "template_id": payload.template_id,
                "library_ref_id": payload.library_ref_id,
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

    Source-of-truth order:
      1. artifact_library row where category matches + is_system=True — this is
         the user-editable canonical. Takes precedence so that edits on /library
         propagate to Reset-to-default everywhere.
      2. Python constant in _DEFAULTS_BY_CATEGORY — fallback if library row
         missing (e.g. migration 023 not yet run, or startup seed failed).
    """
    if category not in _DEFAULTS_BY_CATEGORY:
        raise HTTPException(status_code=404, detail=f"Unknown category: {category}")

    # 1. Try the library first
    try:
        client = get_client()
        lib_rows = (
            client.table("artifact_library")
            .select("name, prompt, llm, model, context_scope, kind, template_id")
            .eq("category", category)
            .eq("is_system", True)
            .limit(1)
            .execute()
            .data
        )
        if lib_rows:
            lib = lib_rows[0]
            return {
                "name": lib["name"],
                "prompt": lib.get("prompt"),
                "is_default": True,
                "category": category,
                "llm": lib.get("llm"),
                "model": lib.get("model"),
                "context_scope": lib.get("context_scope", "call"),
                "kind": lib.get("kind", "llm"),
                "template_id": lib.get("template_id"),
            }
    except Exception as e:
        db_logger.warning(
            f"⚠️ [Defaults] Library lookup failed for category={category}: {e}"
        )

    # 2. Fallback to hardcoded Python constants
    payload = _DEFAULTS_BY_CATEGORY[category].copy()
    payload.setdefault("llm", None)
    payload.setdefault("model", None)
    return payload


class FromLibraryPayload(BaseModel):
    library_id: str


@router.post("/projects/{project_id}/artifact-types/from-library", status_code=201)
def add_from_library(project_id: str, payload: FromLibraryPayload):
    """Copy a library entry into this project's artifact_types."""
    client = get_client()
    lib_rows = (
        client.table("artifact_library")
        .select("*")
        .eq("id", payload.library_id)
        .execute()
        .data
    )
    if not lib_rows:
        raise HTTPException(status_code=404, detail="Library entry not found")
    lib = lib_rows[0]
    row = {
        "project_id": project_id,
        "name": lib["name"],
        "prompt": lib.get("prompt"),
        "is_default": False,
        "category": "artifacts",
        "llm": lib.get("llm"),
        "model": lib.get("model"),
        "context_scope": lib.get("context_scope", "call"),
        "kind": lib["kind"],
        "template_id": lib.get("template_id"),
        "library_ref_id": lib["id"],
    }
    result = client.table("artifact_types").insert(row).execute()
    db_logger.info(
        f"✅ [DB] Added artifact type '{lib['name']}' from library to project {project_id}"
    )
    return result.data[0]


@router.get("/artifact-types/{type_id}/library-source")
def get_library_source(type_id: str):
    """Fetch the library entry this artifact type was copied from.
    If library_ref_id is NULL, fall back to matching by name against is_system=true entries
    (so existing projects predating EPIC-12 can still reset to defaults)."""
    client = get_client()
    type_rows = (
        client.table("artifact_types")
        .select("library_ref_id, name")
        .eq("id", type_id)
        .execute()
        .data
    )
    if not type_rows:
        raise HTTPException(status_code=404, detail="Artifact type not found")
    ref_id = type_rows[0].get("library_ref_id")
    if not ref_id:
        # Fallback: match by name against system library
        name = type_rows[0].get("name", "")
        name_match = (
            client.table("artifact_library")
            .select("*")
            .eq("name", name)
            .eq("is_system", True)
            .execute()
            .data
        )
        if not name_match:
            raise HTTPException(status_code=404, detail="No library source linked")
        return name_match[0]
    lib_rows = (
        client.table("artifact_library").select("*").eq("id", ref_id).execute().data
    )
    if not lib_rows:
        raise HTTPException(status_code=404, detail="Library entry no longer exists")
    return lib_rows[0]


class PublishPayload(BaseModel):
    name: str = Field(min_length=1)
    description: str = ""


@router.post("/artifact-types/{type_id}/publish-to-library", status_code=201)
def publish_to_library(type_id: str, payload: PublishPayload):
    """Copy this artifact type into the library as a user-published entry.
    Sets the source artifact_type.library_ref_id to the new library entry's id.
    Restricted to kind='llm' artifact types (templates/hybrids need Python code)."""
    client = get_client()
    type_rows = (
        client.table("artifact_types").select("*").eq("id", type_id).execute().data
    )
    if not type_rows:
        raise HTTPException(status_code=404, detail="Artifact type not found")
    t = type_rows[0]
    if t.get("kind") != "llm":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot publish kind='{t.get('kind')}' artifacts to library. Only LLM artifacts can be published.",
        )
    entry = {
        "name": payload.name,
        "description": payload.description,
        "kind": "llm",
        "prompt": t.get("prompt"),
        "template_id": None,
        "llm": t.get("llm"),
        "model": t.get("model"),
        "context_scope": t.get("context_scope", "call"),
        "is_system": False,
        "seeded_by_default": False,
    }
    result = client.table("artifact_library").insert(entry).execute()
    new_lib = result.data[0]
    # Link source back to new library entry so Reset works
    client.table("artifact_types").update({"library_ref_id": new_lib["id"]}).eq(
        "id", type_id
    ).execute()
    db_logger.info(
        f"✅ [DB] Published artifact type {type_id} to library as '{payload.name}'"
    )
    return new_lib


class PreviewPayload(BaseModel):
    call_id: str


@router.post("/artifact-types/{type_id}/preview")
def preview_artifact(type_id: str, payload: PreviewPayload):
    """Render the template part of this artifact type for a given call.
    Template kind: returns the full renderer output.
    Hybrid kind: returns just the template skeleton (no LLM intro/closing).
    LLM kind: returns 400 — nothing to preview without an LLM call."""
    from backend.services.template_service import render_template_for_preview

    client = get_client()
    type_rows = (
        client.table("artifact_types").select("*").eq("id", type_id).execute().data
    )
    if not type_rows:
        raise HTTPException(status_code=404, detail="Artifact type not found")
    t = type_rows[0]
    if t.get("kind") == "llm":
        raise HTTPException(
            status_code=400,
            detail="Cannot preview an LLM artifact. Preview only works for template/hybrid kinds.",
        )
    try:
        content = render_template_for_preview(t, payload.call_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"content": content}
