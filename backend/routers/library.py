from typing import Literal

from backend.database.supabase_client import get_client
from backend.library.seed import SYSTEM_LIBRARY
from backend.utils.logger import db_logger
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/library", tags=["library"])


class LibraryEntryCreate(BaseModel):
    name: str = Field(min_length=1)
    description: str = ""
    kind: Literal["llm", "template", "hybrid"] = "llm"
    prompt: str | None = None
    template_id: str | None = None
    llm: str | None = None
    model: str | None = None
    context_scope: Literal["call", "project"] = "call"
    seeded_by_default: bool = False


class LibraryEntryUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    prompt: str | None = None
    llm: str | None = None
    model: str | None = None
    context_scope: Literal["call", "project"] | None = None
    seeded_by_default: bool | None = None


@router.get("")
def list_library():
    client = get_client()
    db_logger.info("🗄️ [DB] Fetching artifact library")
    result = (
        client.table("artifact_library")
        .select("*")
        .order("is_system", desc=True)
        .execute()
    )
    return result.data


@router.post("", status_code=201)
def create_library_entry(payload: LibraryEntryCreate):
    client = get_client()
    db_logger.info(f"🗄️ [DB] Creating library entry: {payload.name}")
    row = payload.model_dump()
    row["is_system"] = False  # user-published entries are never system
    result = client.table("artifact_library").insert(row).execute()
    return result.data[0]


@router.patch("/{entry_id}")
def patch_library_entry(entry_id: str, payload: LibraryEntryUpdate):
    client = get_client()
    update = payload.model_dump(exclude_unset=True)
    if not update:
        raise HTTPException(status_code=422, detail="No fields to update")
    result = (
        client.table("artifact_library").update(update).eq("id", entry_id).execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Library entry not found")
    return result.data[0]


@router.delete("/{entry_id}", status_code=204)
def delete_library_entry(entry_id: str):
    client = get_client()
    row = (
        client.table("artifact_library")
        .select("id, is_system")
        .eq("id", entry_id)
        .execute()
        .data
    )
    if not row:
        raise HTTPException(status_code=404, detail="Library entry not found")
    if row[0].get("is_system"):
        raise HTTPException(
            status_code=403,
            detail="System library entries cannot be deleted. Use POST /api/library/reset-system to restore defaults.",
        )
    client.table("artifact_library").delete().eq("id", entry_id).execute()
    return Response(status_code=204)


@router.post("/reset-system")
def reset_system_library():
    """Overwrite all is_system=true rows with original SYSTEM_LIBRARY values.
    User edits to system entries are reverted. User-published entries untouched.
    """
    client = get_client()
    updated = 0
    for entry in SYSTEM_LIBRARY:
        client.table("artifact_library").update(entry).eq(
            "name", entry["name"]
        ).execute()
        updated += 1
    return {"updated": updated}
