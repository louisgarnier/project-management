import json
from typing import Literal, Optional

from backend.database.supabase_client import get_client
from backend.services.topics_service import rollback_to_stage
from backend.utils.logger import db_logger
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api", tags=["calls"])

STAGE_ORDER = ["transcript", "call_topics", "project_topics", "artifacts", "done"]


class CallCreate(BaseModel):
    title: str



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

    # 0. Get project_id and created_at before deleting
    call_row = client.table("calls").select("project_id, created_at").eq("id", call_id).execute().data
    if not call_row:
        raise HTTPException(status_code=404, detail="Call not found")
    project_id = call_row[0]["project_id"]
    created_at = call_row[0]["created_at"]

    # 1a. Find all following calls (same project, created after this one) and roll them back
    #     to call_topics so their transcripts/extracted topics are preserved but all
    #     project-level data (matching, updates, artifacts) is cleared.
    following_calls = (
        client.table("calls")
        .select("id")
        .eq("project_id", project_id)
        .gt("created_at", created_at)
        .order("created_at")
        .execute()
        .data
    )
    for fc in following_calls:
        try:
            rollback_to_stage(fc["id"], "call_topics")
            db_logger.info(f"🗄️ [DB] Cascade-rolled back following call to call_topics: {fc['id']}")
        except Exception as e:
            db_logger.warning(f"⚠️ [DB] Could not cascade-rollback call {fc['id']}: {e}")

    # 1b. Record which topics had updates for this call before cascade-delete removes them
    updates_before = (
        client.table("topic_updates")
        .select("topic_id")
        .eq("call_id", call_id)
        .execute()
        .data
    )
    affected_topic_ids = list({r["topic_id"] for r in updates_before})

    # 2. Delete call — cascades: topic_updates deleted, first_raised_call_id set to NULL
    client.table("calls").delete().eq("id", call_id).execute()
    db_logger.info(f"✅ [DB] Deleted call: {call_id}")

    # 3. Recalculate calls_open for affected topics; delete orphans with no remaining updates
    for topic_id in affected_topic_ids:
        remaining = (
            client.table("topic_updates")
            .select("status")
            .eq("topic_id", topic_id)
            .execute()
            .data
        )
        if not remaining:
            # Topic only existed in the deleted call — remove it entirely
            client.table("topics").delete().eq("id", topic_id).execute()
            db_logger.info(f"🗄️ [DB] Deleted orphan topic (no remaining updates): {topic_id}")
        else:
            calls_open = sum(1 for r in remaining if r["status"] in ("open", "in_progress"))
            client.table("topics").update({"calls_open": calls_open}).eq("id", topic_id).execute()
            db_logger.info(f"🗄️ [DB] Recalculated calls_open={calls_open} for topic: {topic_id}")


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
def advance_stage(call_id: str):
    client = get_client()
    db_logger.info(f"🗄️ [DB] Fetching call for stage advance: {call_id}")
    result = client.table("calls").select("kanban_stage").eq("id", call_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Call not found")

    current_stage = result.data[0]["kanban_stage"]

    if current_stage not in STAGE_ORDER:
        raise HTTPException(
            status_code=422, detail=f"Call has unknown stage: {current_stage}"
        )

    current_idx = STAGE_ORDER.index(current_stage)
    if current_idx >= len(STAGE_ORDER) - 1:
        raise HTTPException(status_code=422, detail="Call is already at the final stage")

    new_stage = STAGE_ORDER[current_idx + 1]

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

    update_data: dict = {"transcript": payload.transcript, "kanban_stage": "call_topics"}
    if payload.source_filename:
        update_data["transcript_source"] = payload.source_filename

    db_logger.info(f"🗄️ [DB] Storing transcript and advancing call: {call_id}")
    update_result = (
        client.table("calls")
        .update(update_data)
        .eq("id", call_id)
        .execute()
    )
    db_logger.info(f"✅ [DB] Transcript stored, advanced to call_topics: {call_id}")
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
    if current_stage not in ("artifacts", "project_topics", "transcript"):
        raise HTTPException(
            status_code=409,
            detail=f"Transcript reset is only allowed from the artifacts or transcript stage (current: {current_stage})",
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

    update_data: dict = {"transcript": payload.transcript}

    # When editing transcript on a done call, mark topics and artifacts as stale
    if current_stage == "done":
        update_data["topics_stale"] = True
        db_logger.info(f"⚠️ [DB] Setting topics_stale=True for call: {call_id}")
        artifacts = (
            client.table("artifacts")
            .select("id")
            .eq("call_id", call_id)
            .execute()
            .data
        )
        artifact_ids = [a["id"] for a in artifacts]
        if artifact_ids:
            client.table("artifacts").update({"status": "stale"}).in_("id", artifact_ids).execute()
            db_logger.info(f"⚠️ [DB] Marked {len(artifact_ids)} artifacts stale: {call_id}")

    db_logger.info(f"🗄️ [DB] Updating transcript for call: {call_id}")
    update_result = (
        client.table("calls")
        .update(update_data)
        .eq("id", call_id)
        .execute()
    )
    db_logger.info(f"✅ [DB] Transcript updated: {call_id}")
    return update_result.data[0]


@router.post("/calls/{call_id}/lock")
def lock_call(call_id: str):
    client = get_client()
    result = client.table("calls").update({"is_locked": True}).eq("id", call_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Call not found")
    db_logger.info(f"🔒 [DB] Call locked: {call_id}")
    return result.data[0]


@router.post("/calls/{call_id}/unlock")
def unlock_call(call_id: str):
    client = get_client()
    result = client.table("calls").update({"is_locked": False}).eq("id", call_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Call not found")
    db_logger.info(f"🔓 [DB] Call unlocked: {call_id}")
    return result.data[0]


@router.post("/calls/{call_id}/clear_stale")
def clear_topics_stale(call_id: str):
    """Clear the topics_stale flag after topics have been re-reviewed."""
    client = get_client()
    result = client.table("calls").update({"topics_stale": False}).eq("id", call_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Call not found")
    db_logger.info(f"✅ [DB] topics_stale cleared: {call_id}")
    return result.data[0]


_ROLLBACK_STAGE_ORDER = [
    "transcript",
    "call_topics",
    "project_matching",
    "project_updates",
    "artifacts",
    "done",
]


class RollbackPayload(BaseModel):
    target_stage: Literal[
        "transcript", "call_topics", "project_matching", "project_updates", "artifacts"
    ]


@router.post("/calls/{call_id}/rollback")
def rollback_call(call_id: str, payload: RollbackPayload):
    """Roll a call back to an earlier stage, cascading cleanups as required."""
    client = get_client()

    # 1. Verify call exists
    result = client.table("calls").select("kanban_stage").eq("id", call_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Call not found")

    current_stage = result.data[0]["kanban_stage"]

    # 2. Verify target is strictly earlier than current stage
    if current_stage not in _ROLLBACK_STAGE_ORDER:
        raise HTTPException(
            status_code=422,
            detail=f"Call has unknown stage '{current_stage}' — cannot determine rollback validity",
        )
    current_idx = _ROLLBACK_STAGE_ORDER.index(current_stage)
    target_idx = _ROLLBACK_STAGE_ORDER.index(payload.target_stage)

    if current_idx <= target_idx:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot roll back to '{payload.target_stage}': "
                f"call is already at or before that stage (current: '{current_stage}')"
            ),
        )

    db_logger.info(f"🔄 [DB] Rolling back call {call_id}: {current_stage} → {payload.target_stage}")
    result = rollback_to_stage(call_id, payload.target_stage)
    db_logger.info(f"✅ [DB] Rollback complete: {call_id} → {payload.target_stage}")

    # Cascade: roll back all later calls in the same project to call_topics
    call_row = client.table("calls").select("project_id, created_at").eq("id", call_id).execute().data
    if call_row:
        project_id = call_row[0]["project_id"]
        created_at = call_row[0]["created_at"]
        later_calls = (
            client.table("calls")
            .select("id, kanban_stage")
            .eq("project_id", project_id)
            .gt("created_at", created_at)
            .order("created_at")
            .execute()
            .data
        )
        _STAGE_ORDER = ["transcript", "call_topics", "project_matching", "project_updates", "artifacts", "done"]
        for lc in later_calls:
            if _STAGE_ORDER.index(lc["kanban_stage"]) > _STAGE_ORDER.index("call_topics"):
                rollback_to_stage(lc["id"], "call_topics")
                db_logger.info(f"🔄 [DB] Cascade-rolled back later call {lc['id']} to call_topics")

    return result
