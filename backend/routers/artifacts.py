import asyncio
import json
from typing import Literal

from backend.database.supabase_client import get_client
from backend.services.llm_service import generate_artifact
from backend.utils.logger import db_logger, get_logger
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

router = APIRouter(prefix="/api", tags=["artifacts"])
logger = get_logger("artifacts")


class ArtifactSelection(BaseModel):
    artifact_type_id: str
    mode: Literal["groq", "claude", "openai", "manual"]


class ArtifactSelectionsPayload(BaseModel):
    selections: list[ArtifactSelection]


@router.post("/calls/{call_id}/artifacts", status_code=201)
def create_artifact_selections(call_id: str, payload: ArtifactSelectionsPayload):
    """
    Create artifact rows for the given call. For each selection:
    - mode='claude'  → status='pending', content=None
    - mode='manual'  → status='done',    content=''
    prompt_used is snapshotted from the artifact type's current prompt.
    """
    client = get_client()

    # Verify call exists
    call_check = client.table("calls").select("id").eq("id", call_id).execute()
    if not call_check.data:
        raise HTTPException(status_code=404, detail="Call not found")

    db_logger.info(f"🗄️ [DB] Creating {len(payload.selections)} artifact selections for call: {call_id}")

    type_ids = [s.artifact_type_id for s in payload.selections]
    types_result = (
        client.table("artifact_types")
        .select("id,prompt")
        .in_("id", type_ids)
        .execute()
    )
    prompt_map = {t["id"]: t["prompt"] for t in types_result.data}

    rows = []
    for s in payload.selections:
        prompt = prompt_map.get(s.artifact_type_id, "")
        row = {
            "call_id": call_id,
            "artifact_type_id": s.artifact_type_id,
            "mode": s.mode,
            "prompt_used": prompt,
        }
        if s.mode == "manual":
            row["status"] = "done"
            row["content"] = ""
        else:
            row["status"] = "pending"
        rows.append(row)

    result = client.table("artifacts").insert(rows).execute()
    db_logger.info(f"✅ [DB] Created {len(result.data)} artifact rows for call: {call_id}")
    return result.data


@router.get("/calls/{call_id}/artifacts")
def list_artifacts(call_id: str):
    client = get_client()
    call_check = client.table("calls").select("id").eq("id", call_id).execute()
    if not call_check.data:
        raise HTTPException(status_code=404, detail="Call not found")
    db_logger.info(f"🗄️ [DB] Fetching artifacts for call: {call_id}")
    result = (
        client.table("artifacts")
        .select("*")
        .eq("call_id", call_id)
        .order("created_at")
        .execute()
    )
    db_logger.info(f"✅ [DB] Retrieved {len(result.data)} artifacts")
    return result.data


class ArtifactUpdate(BaseModel):
    content: str | None = None
    status: Literal["pending", "generating", "done", "error"] | None = None
    mode: Literal["groq", "claude", "openai", "manual"] | None = None


@router.patch("/artifacts/{artifact_id}")
def update_artifact(artifact_id: str, payload: ArtifactUpdate):
    client = get_client()
    db_logger.info(f"🗄️ [DB] Updating artifact: {artifact_id}")
    update = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not update:
        raise HTTPException(status_code=422, detail="No fields to update")
    result = client.table("artifacts").update(update).eq("id", artifact_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Artifact not found")
    db_logger.info(f"✅ [DB] Updated artifact: {artifact_id}")
    return result.data[0]


@router.delete("/artifacts/{artifact_id}", status_code=204)
def delete_artifact(artifact_id: str):
    client = get_client()
    db_logger.info(f"🗄️ [DB] Deleting artifact: {artifact_id}")
    result = client.table("artifacts").delete().eq("id", artifact_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Artifact not found")
    db_logger.info(f"✅ [DB] Deleted artifact: {artifact_id}")
    return Response(status_code=204)


@router.delete("/calls/{call_id}/artifacts", status_code=204)
def delete_call_artifacts(call_id: str):
    """Delete all artifacts for a call (used when resetting transcript)."""
    client = get_client()
    db_logger.info(f"🗄️ [DB] Deleting all artifacts for call: {call_id}")
    client.table("artifacts").delete().eq("call_id", call_id).execute()
    db_logger.info(f"✅ [DB] Deleted all artifacts for call: {call_id}")
    return Response(status_code=204)


@router.get("/calls/{call_id}/artifacts/stream")
async def stream_artifacts(call_id: str):
    """
    SSE endpoint. Generates all pending 'claude' artifacts in parallel.
    Emits per-artifact events:
      {"type":"status",  "artifact_id":"...", "status":"generating"}
      {"type":"done",    "artifact_id":"...", "content":"..."}
      {"type":"error",   "artifact_id":"...", "message":"..."}
    Final event: {"type":"complete"}
    """
    supabase = get_client()

    call_result = (
        supabase.table("calls")
        .select("id,transcript")
        .eq("id", call_id)
        .execute()
    )
    if not call_result.data:
        raise HTTPException(status_code=404, detail="Call not found")
    transcript = call_result.data[0].get("transcript") or ""

    artifacts_result = (
        supabase.table("artifacts")
        .select("id,prompt_used,mode")
        .eq("call_id", call_id)
        .eq("status", "pending")
        .execute()
    )
    pending = artifacts_result.data

    async def event_stream():
        if not pending:
            yield f"data: {json.dumps({'type': 'complete'})}\n\n"
            return

        queue: asyncio.Queue = asyncio.Queue()

        async def gen_one(artifact: dict) -> None:
            artifact_id = artifact["id"]
            prompt_used = artifact["prompt_used"]
            await queue.put({"type": "status", "artifact_id": artifact_id, "status": "generating"})
            supabase.table("artifacts").update({"status": "generating"}).eq("id", artifact_id).execute()
            try:
                content = await generate_artifact(prompt_used, transcript, artifact["mode"])
                supabase.table("artifacts").update(
                    {"status": "done", "content": content}
                ).eq("id", artifact_id).execute()
                await queue.put({"type": "done", "artifact_id": artifact_id, "content": content})
                db_logger.info(f"✅ [DB] Artifact done: {artifact_id}")
            except Exception as exc:
                msg = str(exc)
                supabase.table("artifacts").update(
                    {"status": "error", "error_message": msg}
                ).eq("id", artifact_id).execute()
                await queue.put({"type": "error", "artifact_id": artifact_id, "message": msg})
                db_logger.error(f"❌ [DB] Artifact error: {artifact_id} — {msg}")
            finally:
                await queue.put(None)

        tasks = [asyncio.create_task(gen_one(a)) for a in pending]
        completed = 0
        while completed < len(tasks):
            item = await queue.get()
            if item is None:
                completed += 1
            else:
                yield f"data: {json.dumps(item)}\n\n"

        yield f"data: {json.dumps({'type': 'complete'})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
