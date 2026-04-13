import json
from typing import Optional

from backend.database.supabase_client import get_client
from backend.utils.logger import db_logger
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api", tags=["calls"])

STAGE_ORDER = ["transcript", "artifacts", "topics", "done"]


class CallCreate(BaseModel):
    title: str


class StageAdvance(BaseModel):
    new_stage: str


class TranscriptSubmit(BaseModel):
    transcript: str = Field(min_length=1)
    source_filename: Optional[str] = None


class TranscriptUpdate(BaseModel):
    transcript: str = Field(min_length=1)


@router.get("/projects/{project_id}/calls")
def list_calls(project_id: str):
    client = get_client()
    db_logger.info(f"🗄️ [DB] Fetching calls for project: {project_id}")
    result = client.table("calls").select("*").eq("project_id", project_id).execute()
    db_logger.info(f"✅ [DB] Retrieved {len(result.data)} calls")
    return result.data


@router.post("/projects/{project_id}/calls", status_code=201)
def create_call(project_id: str, payload: CallCreate):
    client = get_client()
    db_logger.info(f"🗄️ [DB] Creating call: {payload.title}")
    result = (
        client.table("calls")
        .insert(
            {
                "project_id": project_id,
                "title": payload.title,
                "kanban_stage": STAGE_ORDER[0],
            }
        )
        .execute()
    )
    db_logger.info(f"✅ [DB] Created call: {result.data[0]['id']}")
    return result.data[0]


@router.delete("/calls/{call_id}", status_code=204)
def delete_call(call_id: str):
    client = get_client()
    db_logger.info(f"🗄️ [DB] Deleting call: {call_id}")
    client.table("calls").delete().eq("id", call_id).execute()
    db_logger.info(f"✅ [DB] Deleted call: {call_id}")


@router.get("/calls/{call_id}")
def get_call(call_id: str):
    client = get_client()
    db_logger.info(f"🗄️ [DB] Fetching call: {call_id}")
    result = client.table("calls").select("*").eq("id", call_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Call not found")
    db_logger.info(f"✅ [DB] Retrieved call: {call_id}")
    return result.data[0]


@router.patch("/calls/{call_id}/stage")
def advance_stage(call_id: str, payload: StageAdvance):
    client = get_client()
    db_logger.info(f"🗄️ [DB] Fetching call for stage advance: {call_id}")
    result = client.table("calls").select("kanban_stage").eq("id", call_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Call not found")

    current_stage = result.data[0]["kanban_stage"]
    new_stage = payload.new_stage

    if current_stage not in STAGE_ORDER:
        raise HTTPException(
            status_code=422, detail=f"Call has unknown stage: {current_stage}"
        )

    if new_stage not in STAGE_ORDER:
        raise HTTPException(status_code=422, detail=f"Invalid stage: {new_stage}")

    current_idx = STAGE_ORDER.index(current_stage)
    new_idx = STAGE_ORDER.index(new_stage)

    if new_idx != current_idx + 1:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid stage transition: {current_stage} → {new_stage}. Must follow transcript → artifacts → topics → done",
        )

    db_logger.info(f"🗄️ [DB] Advancing call {call_id}: {current_stage} → {new_stage}")
    update_result = (
        client.table("calls")
        .update({"kanban_stage": new_stage})
        .eq("id", call_id)
        .execute()
    )
    db_logger.info(f"✅ [DB] Advanced stage: {call_id}")
    return update_result.data[0]


@router.post("/calls/{call_id}/transcript")
def submit_transcript(call_id: str, payload: TranscriptSubmit):
    client = get_client()
    db_logger.info(f"🗄️ [DB] Fetching call for transcript submission: {call_id}")
    result = client.table("calls").select("kanban_stage").eq("id", call_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Call not found")

    current_stage = result.data[0]["kanban_stage"]
    if current_stage != "transcript":
        raise HTTPException(
            status_code=409,
            detail=f"Call is already past the transcript stage (current: {current_stage})",
        )

    update_data: dict = {"transcript": payload.transcript, "kanban_stage": "artifacts"}
    if payload.source_filename:
        update_data["transcript_source"] = payload.source_filename

    db_logger.info(f"🗄️ [DB] Storing transcript and advancing call: {call_id}")
    update_result = (
        client.table("calls")
        .update(update_data)
        .eq("id", call_id)
        .execute()
    )
    db_logger.info(f"✅ [DB] Transcript stored, advanced to artifacts: {call_id}")
    return update_result.data[0]


@router.delete("/calls/{call_id}/transcript", status_code=200)
def reset_transcript(call_id: str):
    """Roll back a call from artifacts → transcript, clearing the transcript."""
    client = get_client()
    db_logger.info(f"🗄️ [DB] Fetching call for transcript reset: {call_id}")
    result = client.table("calls").select("kanban_stage").eq("id", call_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Call not found")

    current_stage = result.data[0]["kanban_stage"]
    if current_stage != "artifacts":
        raise HTTPException(
            status_code=409,
            detail=f"Transcript reset is only allowed from the artifacts stage (current: {current_stage})",
        )

    db_logger.info(f"🗄️ [DB] Resetting transcript for call: {call_id}")
    # supabase-py filters out None values from .update() payloads, so we bypass it
    # and send the raw JSON directly via the underlying httpx session to guarantee
    # that transcript and transcript_source are set to NULL in the database.
    payload = json.dumps(
        {"kanban_stage": "transcript", "transcript": None, "transcript_source": None}
    )
    response = client.postgrest.session.patch(
        f"/calls?id=eq.{call_id}",
        content=payload,
        headers={"Content-Type": "application/json", "Prefer": "return=representation"},
    )
    data = response.json()
    if not data:
        raise HTTPException(status_code=500, detail="Transcript reset failed")
    db_logger.info(f"✅ [DB] Transcript cleared, rolled back to transcript stage: {call_id}")
    return data[0]


@router.patch("/calls/{call_id}/transcript")
def update_transcript(call_id: str, payload: TranscriptUpdate):
    client = get_client()
    db_logger.info(f"🗄️ [DB] Fetching call for transcript update: {call_id}")
    result = client.table("calls").select("kanban_stage").eq("id", call_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Call not found")

    current_stage = result.data[0]["kanban_stage"]
    if current_stage == "transcript":
        raise HTTPException(
            status_code=409,
            detail="Call is at transcript stage — use POST /transcript to save and advance",
        )

    db_logger.info(f"🗄️ [DB] Updating transcript for call: {call_id}")
    update_result = (
        client.table("calls")
        .update({"transcript": payload.transcript})
        .eq("id", call_id)
        .execute()
    )
    db_logger.info(f"✅ [DB] Transcript updated: {call_id}")
    return update_result.data[0]
