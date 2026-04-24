from typing import Literal

from backend.database.supabase_client import get_client
from backend.utils.logger import db_logger
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SystemSettingsPayload(BaseModel):
    default_llm: (
        Literal["groq", "deepseek", "claude", "openai", "openrouter"] | None
    ) = None
    default_model: str | None = None


@router.get("")
def get_system_settings():
    """Return the singleton system_settings row (id=1)."""
    client = get_client()
    rows = client.table("system_settings").select("*").eq("id", 1).execute().data
    if not rows:
        # Row missing — fall back to sensible defaults (migration should have seeded it)
        return {"default_llm": "openrouter", "default_model": "deepseek/deepseek-v3.2"}
    return rows[0]


@router.patch("")
def patch_system_settings(payload: SystemSettingsPayload):
    """Update the singleton system_settings row. Only fields set in the payload are updated."""
    client = get_client()
    update = payload.model_dump(exclude_unset=True)
    if not update:
        raise HTTPException(status_code=422, detail="No fields to update")
    from datetime import datetime, timezone

    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = client.table("system_settings").update(update).eq("id", 1).execute()
    db_logger.info(f"🗄️ [Settings] Updated system_settings: {update}")
    if not result.data:
        raise HTTPException(
            status_code=404, detail="system_settings row missing — run migration 024"
        )
    return result.data[0]
